"""Ý định `behavior` (phase 5 luồng B, F7): câu hỏi về thói quen chi tiêu của chính người dùng -> khối `behavior_insight`.

Luồng một lượt (không gọi model ngoài router):

1. `forecast___get_behavior_profile` (chỉ đọc hồ sơ batch đêm đã tính; mỗi số trong câu nhận xét đã qua kiểm căn cứ lúc tính).
2. Chọn MỘT nhận xét bằng mã theo `insight_kind` router trích từ câu hỏi (khía cạnh thói quen được hỏi): có nhận xét đúng loại
   thì lấy nhận xét đó; hỏi chung (null) thì lấy nhận xét quan trọng nhất (đầu danh sách).
3. Phát khối `behavior_insight` (`yofina_core.blocks.build_behavior_insight`) TRƯỚC kết quả tool, rồi một câu chữ do mã dựng từ chính
   câu nhận xét và việc cần làm của hồ sơ (không có số nào ngoài số của hồ sơ, nên không cần Writer hay Verifier).

Hồ sơ chưa sẵn sàng (`ready` sai) không phải lỗi: khối `notice` loại `low_data` kèm câu của hồ sơ ("cần thêm N ngày"), không bịa nhận
xét. Tool lỗi thì đi đường lỗi chung của lượt (`Turn.tool_failure`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from yofina_agent.tools import ContractMismatch, ToolOutcome
from yofina_core import blocks as B
from yofina_core.errors import ErrorCode

if TYPE_CHECKING:
    from yofina_agent.schemas import IntentResult
    from yofina_agent.turn import Turn

TOOL = "get_behavior_profile"
TARGET = "forecast"
#: lỗi nghiệp vụ là trạng thái trống (chưa khai lương): notice `info`, không phải `error`
EMPTY_CODES = frozenset({ErrorCode.PROFILE_INCOMPLETE.value})
NOT_READY_TITLE = "Chưa đủ dữ liệu về thói quen chi tiêu"

#: tên khía cạnh để nói rõ khi hồ sơ chưa có nhận xét đúng loại được hỏi (mọi giá trị của `BehaviorInsightKind`)
TOPIC_TEXT = {
    "bnpl_usage": "việc dùng Trả sau",
    "weekday_pattern": "ngày trong tuần",
    "payday_cycle": "nhịp chi theo kỳ lương",
    "time_of_day": "giờ chi tiêu trong ngày",
    "spending_cluster": "những ngày chi đậm",
    "category_trend": "xu hướng của một nhóm chi tiêu",
}


def pick_insight(data: Mapping[str, Any], kind: str | None) -> tuple[Mapping[str, Any], bool]:
    """(nhận xét được chọn, có đúng loại được hỏi không). Hồ sơ phải sẵn sàng (có ít nhất một nhận xét)."""
    insights: Sequence[Mapping[str, Any]] = data["insights"]
    if kind is not None:
        hit = next((i for i in insights if i["kind"] == kind), None)
        if hit is not None:
            return hit, True
    return insights[0], kind is None


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def insight_block(outcome: ToolOutcome, trace_id: str, kind: str | None) -> list[B.BehaviorInsightBlock]:
    """Khối `behavior_insight` của nhận xét được chọn; hồ sơ chưa sẵn sàng thì không có khối (không phải lỗi hợp đồng)."""
    payload = outcome.payload or {}
    try:
        data = payload["data"]
        if not data["ready"]:
            return []
        insight, _ = pick_insight(data, kind)
        return [
            B.build_behavior_insight(
                data=B.behavior_insight_data(data, insight["insight_id"]),
                trace_id=trace_id,
                source_tool=outcome.name,
                as_of=_instant(payload["as_of"]),
                app_date=date.fromisoformat(payload["app_date"]),
            )
        ]
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ContractMismatch(f"get_behavior_profile sai hợp đồng: {exc}") from exc


def compact_profile(payload: Mapping[str, Any], kind: str | None) -> dict[str, Any]:
    """Bản gọn cho TOOL_CALL_RESULT (model không đọc lại; chỉ để vết của lượt)."""
    data = payload["data"]
    out: dict[str, Any] = {"ready": bool(data["ready"]), "headline": data["headline"], "history_days": data["history_days"]}
    if data["ready"]:
        insight, matched = pick_insight(data, kind)
        out.update(
            insight_id=insight["insight_id"],
            kind=insight["kind"],
            matched=matched,
            insight_count=len(data["insights"]),
            next_step=data["next_step"]["label"],
        )
    return out


def answer_text(data: Mapping[str, Any], kind: str | None) -> str:
    """Câu trả lời do mã dựng: câu nhận xét, (nếu hỏi một chủ đề mà hồ sơ không có) một câu nói rõ chưa thấy, và việc nên làm."""
    insight, matched = pick_insight(data, kind)
    parts: list[str] = []
    if not matched and kind is not None:
        parts.append(f"Mình chưa thấy thói quen nào rõ về {TOPIC_TEXT[kind]} trong dữ liệu của bạn.")
        parts.append(f"Điều nổi bật nhất là: {insight['headline']}")
    else:
        parts.append(str(insight["headline"]))
    if insight.get("detail"):
        parts.append(str(insight["detail"]))
    parts.append(f"Việc nên làm: {data['next_step']['label']}.")
    return " ".join(p if p.endswith((".", "!", "?")) else p + "." for p in parts)


async def answer(turn: Turn, r: IntentResult, question: str) -> None:
    """Bộ xử lý ý định `behavior` của `Turn`."""
    kind = r.params.insight_kind
    res = await turn.call_tool_retry(
        TOOL,
        {},
        target=TARGET,
        compact=lambda o: compact_profile(o.payload or {}, kind),
        block=lambda o, trace_id: insight_block(o, trace_id, kind),
    )
    if not res.outcome.ok:
        turn.tool_failure(res.outcome, empty_codes=EMPTY_CODES)
        return
    data = (res.outcome.payload or {})["data"]
    if not data["ready"]:
        turn.emit_notice(
            kind="low_data",
            code=None,
            title=NOT_READY_TITLE,
            message=str(data["headline"]),
            degraded_reason="short_history",
            block_id=f"notice:{turn.trace_id}:behavior_not_ready",
        )
        return
    await turn.emit_fixed_text(answer_text(data, kind))


__all__ = ["TOPIC_TEXT", "answer", "answer_text", "compact_profile", "insight_block", "pick_insight"]
