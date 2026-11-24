"""Ý định `knowledge` (phase 5, luồng C thu gọn): hỏi phí của Trả sau (mô phỏng) kèm nguồn. Không có RAG, không tìm kiếm tài liệu.

Luồng (mã điều khiển, KHÔNG có lượt model nào):

    `knowledge___get_fee_schedule` (biểu phí CÓ CẤU TRÚC, bảng `fee_schedules`)
      -> chọn các dòng phí theo `fee_topic` router trích (khớp THUỘC TÍNH của dòng: chu kỳ, điều kiện; không gắn cứng mã phí)
      -> khối `citation` (`yofina_core.blocks.build_citation`): tên nguồn, đường dẫn, ngày hiệu lực CHÉP từ chính các dòng đó
      -> câu trả lời dựng bằng mã: số tiền và điều kiện lấy từ `amount_vnd`, `rate_percent`, `condition_note` của dòng

Câu hỏi về một loại phí mà bảng không có dòng nào khớp (ví dụ phí trả chậm khi bảng chưa có dòng điều kiện `overdue`), hay về một
điều khoản ngoài bốn loại (`fee_topic="other"`): nói rõ là chưa có nguồn cho khoản đó, KHÔNG bịa số hay nguồn; vẫn liệt kê các phí đang
hiệu lực kèm trích dẫn của chúng (khối `citation` chỉ chứa nguồn và loại phí mà tool đã trả).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from yofina_agent.tools import ToolOutcome
from yofina_core import blocks as B
from yofina_core.errors import ErrorCode
from yofina_core.money import format_vnd

if TYPE_CHECKING:
    from yofina_agent.schemas import IntentResult
    from yofina_agent.turn import Turn

#: `fee_topic` của router -> `period` của dòng phí (phí trả chậm khớp theo điều kiện `overdue`; "other" không khớp dòng nào)
_TOPIC_PERIOD = {"monthly": "per_month", "per_transaction": "per_transaction", "once": "once"}
_PERIOD_TEXT = {"per_month": "mỗi tháng", "per_transaction": "mỗi giao dịch", "once": "một lần"}
_CONCEPT_LABEL = {
    "late": "phí trả chậm",
    "monthly": "phí hằng tháng",
    "per_transaction": "phí theo từng giao dịch",
    "once": "phí một lần",
    "other": "khoản bạn hỏi",
}


def matches(fee: Mapping[str, Any], concept: str) -> bool:
    if concept == "late":
        return fee["condition_code"] == "overdue"
    if fee["condition_code"] == "overdue":
        return False
    return _TOPIC_PERIOD.get(concept) == fee["period"]


def select_fees(
    fees: Sequence[Mapping[str, Any]], concepts: Sequence[str]
) -> tuple[list[str], list[str]]:
    """(loại phí cần trích dẫn theo thứ tự của bảng, khái niệm người dùng hỏi mà bảng không có). Không hỏi loại cụ thể: mọi phí."""
    if not concepts:
        return [f["fee_type"] for f in fees], []
    wanted: list[str] = []
    missing: list[str] = []
    for c in concepts:
        hit = [f["fee_type"] for f in fees if matches(f, c)]
        if not hit:
            missing.append(c)
        wanted += [t for t in hit if t not in wanted]
    return wanted, missing


def _date_vn(iso: str) -> str:
    return "/".join(reversed(iso.split("-")))


def fee_sentence(fee: Mapping[str, Any]) -> str:
    if fee.get("amount_vnd") is not None:
        amount = format_vnd(fee["amount_vnd"])
    elif fee.get("rate_percent") is not None:
        amount = f"{fee['rate_percent']:g}%".replace(".", ",")
    else:
        amount = "không ghi số tiền"
    text = f"{amount} {_PERIOD_TEXT.get(fee['period'], '')}".strip()
    if fee.get("condition_note"):
        text += f" ({fee['condition_note'].rstrip('.')})"
    return text


def answer_text(data: Mapping[str, Any], cited: Sequence[str], missing: Sequence[str]) -> str:
    """Câu trả lời từ đúng các dòng phí đã trích dẫn: số, chu kỳ, điều kiện, tên nguồn và ngày hiệu lực đều của tool."""
    product = data["product_label"]
    by_type = {f["fee_type"]: f for f in data["fees"]}
    parts: list[str] = []
    if missing:
        names = ", ".join(_CONCEPT_LABEL[c] for c in missing)
        parts.append(
            f"Biểu phí {product} mình có hiện chưa có {names}, nên mình không đưa số hay nguồn cho khoản đó."
        )
    lines = [by_type[t] for t in cited]
    if lines:
        lead = "Các phí đang hiệu lực" if (missing or len(lines) > 1) else "Phí"
        body = "; ".join(fee_sentence(f) for f in lines)
        parts.append(f"{lead} của {product}: {body}.")
        sources = list(dict.fromkeys((f["source_name"], f["effective_from"]) for f in lines))
        src = "; ".join(f"{name}, hiệu lực từ {_date_vn(eff)}" for name, eff in sources)
        parts.append(f"Nguồn: {src}.")
    return " ".join(parts)


def citation_for(outcome: ToolOutcome, trace_id: str, fee_types: Sequence[str]) -> B.CitationBlock:
    """Khối `citation` của các loại phí đã chọn, dựng từ chính kết quả OK của `get_fee_schedule` (không qua model)."""
    return B.build_citation(result=outcome.payload or {}, trace_id=trace_id, fee_types=fee_types)


async def on_knowledge(turn: Turn, r: IntentResult, question: str) -> None:
    concepts = [r.params.fee_topic] if r.params.fee_topic else []

    def pick(outcome: ToolOutcome) -> tuple[list[str], list[str]]:
        fees = (outcome.payload or {})["data"]["fees"]
        cited, missing = select_fees(fees, concepts)
        if missing:
            # hỏi khoản bảng không có: vẫn trích dẫn các phí đang hiệu lực (không bao giờ trích nguồn cho khoản không có)
            cited = cited or [f["fee_type"] for f in fees]
        return cited, missing

    # khối `citation` phát TRƯỚC `TOOL_CALL_RESULT` như mọi khối dựng từ kết quả tool
    res = await turn.call_tool_retry(
        "get_fee_schedule",
        {},
        target="knowledge",
        compact=lambda o: _compact((o.payload or {})["data"]),
        block=lambda o, trace_id: citation_for(o, trace_id, pick(o)[0]),
    )
    if not res.outcome.ok:
        turn.tool_failure(
            res.outcome, empty_codes=frozenset({ErrorCode.FEE_SCHEDULE_NOT_FOUND.value})
        )
        return
    cited, missing = pick(res.outcome)
    data = (res.outcome.payload or {})["data"]
    await turn.emit_fixed_text(answer_text(data, cited, missing))


def _compact(data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": "OK",
        "product_label": data["product_label"],
        "fees": [
            {
                k: f[k]
                for k in (
                    "fee_type",
                    "amount_vnd",
                    "rate_percent",
                    "period",
                    "condition_code",
                    "effective_from",
                )
                if k in f
            }
            for f in data["fees"]
        ],
    }
