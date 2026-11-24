"""Kiểm và chuẩn hóa bản ghi lượt (`audit___record_turn`) trước khi ghi vào `audit_events` (event_type `agent_turn`).

Đối xứng với `trace.py` (phía đọc): cùng các mô hình `DataUsed`, `RuleCheck`, `ExplainConfidence` của `yofina_core.blocks`, nên thứ được
ghi chắc chắn đọc lại được. Hàm thuần (không I/O). Danh tính (`user_id`) KHÔNG nằm trong đây: Lambda lấy từ interceptor/JWT.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from yofina_core.blocks import DataUsed, ExplainConfidence, RuleCheck
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.wallet import AUDIT_INTENTS

TRACE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
OUTCOMES = ("ok", "rejected", "error")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BlockRef(_Strict):
    id: Annotated[str, Field(min_length=1, max_length=128)]
    type: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=40)]


class Step(_Strict):
    """Một bước của lượt (`TraceStep`). Bước có `step` là tên đầy đủ của tool (`<target>___<tool>`) là MỘT lần gọi tool, kèm
    `status` và `code` khi lỗi (phase 5: màn trace và tỷ lệ lỗi tool của bảng vận hành đọc từ đây)."""

    step: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
    ms: Annotated[int, Field(ge=0)]
    status: Literal["ok", "error", "denied"] | None = None
    code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]*$", max_length=40)] | None = None


class Usage(_Strict):
    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    model_calls: Annotated[int, Field(ge=0)]
    cache_read_tokens: Annotated[int, Field(ge=0)] | None = None


class TurnRecord(_Strict):
    """Các trường của bản ghi lượt. `user_id` cố ý không có và `parse_turn_record` bỏ mọi khóa ngoài danh sách này."""

    trace_id: str
    conversation_id: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    intent: str | None = None
    outcome: str
    code: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    data_used: Annotated[list[DataUsed], Field(min_length=1, max_length=20)]
    rules_checked: Annotated[list[RuleCheck], Field(max_length=20)]
    confidence: ExplainConfidence
    blocks_emitted: Annotated[list[BlockRef], Field(max_length=40)]
    token_usage: Usage
    step_timings: Annotated[list[Step], Field(max_length=30)]
    duration_ms: Annotated[int, Field(ge=0, le=2_147_483_647)]


FIELDS = frozenset(TurnRecord.model_fields)


def parse_turn_record(args: Mapping[str, Any]) -> dict[str, Any]:
    """Trả dict đã kiểm, dạng JSON, đúng cột của `audit_events`. Sai dạng thì PARAMS_INVALID (không lộ nội dung)."""
    clean = {k: v for k, v in args.items() if k in FIELDS and v is not None and v != ""}
    try:
        rec = TurnRecord.model_validate(clean)
    except ValidationError as exc:
        where = ".".join(str(p) for p in exc.errors()[0].get("loc", ()))
        raise YofinaError(
            ErrorCode.PARAMS_INVALID, f"Bản ghi lượt không hợp lệ ({where or 'record'})."
        ) from None
    if not TRACE_ID_RE.fullmatch(rec.trace_id):
        raise YofinaError(ErrorCode.PARAMS_INVALID, "trace_id không hợp lệ.")
    if rec.outcome not in OUTCOMES:
        raise YofinaError(ErrorCode.PARAMS_INVALID, "outcome phải là ok, rejected hoặc error.")
    if rec.intent is not None and rec.intent not in AUDIT_INTENTS:
        raise YofinaError(ErrorCode.PARAMS_INVALID, "intent không hợp lệ.")
    return rec.model_dump(mode="json", exclude_none=True)
