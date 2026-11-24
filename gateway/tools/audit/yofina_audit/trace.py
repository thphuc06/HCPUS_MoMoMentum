"""Dựng `TraceData` (khối `explain` + chi tiết kỹ thuật) từ bản ghi lượt trong `audit_events` (`event_type = 'agent_turn'`).

Bản ghi lượt do agent ghi MỘT lần cuối lượt (migration 0010); hàm này CHỈ ĐỌC lại và dựng khối, không tính thêm gì, nên số hiển thị
ở bảng "Vì sao" chính là thứ lượt đó đã dùng. Phần nào bản ghi thiếu thì dùng giá trị trung tính có nói rõ (không bịa dữ liệu).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from pydantic import ValidationError

from yofina_audit.record import Step
from yofina_core.blocks import (
    DataUsed,
    ExplainConfidence,
    ExplainData,
    RuleCheck,
    block_to_wire,
    build_explain,
    format_instant,
)

_OUTCOMES = ("ok", "rejected", "error")
NO_DATA_LABEL = "Lượt này không dùng số liệu nào của bạn"
NO_CONFIDENCE_REASON = "Lượt này không ghi nhận cơ sở độ tin cậy."


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _valid(model: type[Any], items: list[Any]) -> list[Any]:
    """Giữ phần tử đúng hình dạng, bỏ phần tử hỏng (một dòng hỏng không được làm mất cả bảng giải thích)."""
    out = []
    for it in items:
        try:
            out.append(model.model_validate(it))
        except ValidationError:
            continue
    return out


def _steps(value: Any) -> list[dict[str, Any]]:
    """`step_timings` đúng `TraceStep` (tối đa 30), giữ `status` và `code` của bước là một lần gọi tool; bước hỏng thì bỏ."""
    return [s.model_dump(exclude_none=True) for s in _valid(Step, _list(value))][:30]


def build_trace_data(
    row: Mapping[str, Any],
    *,
    request_trace_id: str,
    source_tool: str,
    now: datetime,
    app_date: date,
) -> dict[str, Any]:
    trace_id = str(row["trace_id"])
    created = row["created_at"]
    data_used = _valid(DataUsed, _list(row.get("data_used")))[:20] or [
        DataUsed(label=NO_DATA_LABEL, tool="none")
    ]
    rules = _valid(RuleCheck, _list(row.get("rules_checked")))[:20]
    conf_raw = row.get("confidence")
    try:
        confidence = ExplainConfidence.model_validate(conf_raw)
    except ValidationError:
        confidence = ExplainConfidence(band="low", reasons=[NO_CONFIDENCE_REASON])
    explain = build_explain(
        data=ExplainData(
            subject_trace_id=trace_id,
            data_used=data_used,
            rules_checked=rules,
            confidence=confidence,
        ),
        trace_id=request_trace_id,
        source_tool=source_tool,
        as_of=now,
        app_date=app_date,
    )
    usage = row.get("token_usage")
    detail: dict[str, Any] = {
        "blocks_emitted": [
            {"id": str(b["id"]), "type": str(b["type"])}
            for b in _list(row.get("blocks_emitted"))
            if isinstance(b, Mapping) and "id" in b and "type" in b
        ][:40],
        "token_usage": (
            {k: int(v) for k, v in usage.items() if isinstance(v, int)}
            if isinstance(usage, Mapping)
            else {"input_tokens": 0, "output_tokens": 0, "model_calls": 0}
        ),
        "step_timings": _steps(row.get("step_timings")),
        "duration_ms": int(row["duration_ms"]) if row.get("duration_ms") is not None else 0,
    }
    for key in ("input_tokens", "output_tokens", "model_calls"):
        detail["token_usage"].setdefault(key, 0)
    if row.get("intent"):
        detail["intent"] = str(row["intent"])
    outcome = row.get("outcome")
    detail["outcome"] = outcome if outcome in _OUTCOMES else "ok"
    return {
        "trace_id": trace_id,
        "created_at": format_instant(created) if isinstance(created, datetime) else str(created),
        "explain": block_to_wire(explain),
        "detail": detail,
    }
