"""Khối UI: model Pydantic khớp `contracts/blocks/*.schema.json` và hàm dựng khối.

Nguồn sự thật là JSON Schema trong `contracts/blocks/`. Các model ở đây viết tay và được test
đối chiếu với schema (hình dạng và fixture dùng chung, xem `tests/unit/test_contracts_blocks.py`).
Frontend dùng Zod sinh từ cùng schema (`scripts/gen_contracts.mjs`).

Nguyên tắc: **số trong khối do code dựng từ kết quả tool/sổ cái**, không do LLM viết. Các hàm
`build_*` nhận số thật (int, Decimal hoặc chuỗi numeric của Data API) và tự dựng `fallback_text`.

Quy tắc `id` (ổn định trong một lượt, cùng id thì khối sau thay khối trước):
- jar_summary: `jar_summary:{trace_id}`
- confirm:     `confirm:{trace_id}:{params_hash[:12]}`
- receipt:     `receipt:{transaction_id}`
- notice:      `notice:{trace_id}:{code hoặc kind}`
- confirm_action: `confirm:{trace_id}:{params_hash[:12]}` (cùng tiền tố `confirm:` với khối confirm)
- receipt_action: `receipt:{tool}:{reference_id}` hoặc `receipt:{tool}:{trace_id}`
- forecast_timeline: `forecast_timeline:{trace_id}:{jar_code}`
- proactive_card: `proactive_card:{trace_id}:{kind}`
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from yofina_core.confirm import (
    MOVE_BETWEEN_JARS,
    hash_normalized_params,
    normalize_params,
    params_hash,
)
from yofina_core.money import format_vnd, to_vnd
from yofina_core.wallet import GENERIC_ACTION_TOOLS

SCHEMA_VERSION = 1
MAX_VND = 99_999_999_999_999

# --- kiểu cơ bản (khớp envelope.schema.json#/$defs) ---------------------------------------
Vnd = Annotated[int, Field(ge=0, le=MAX_VND)]
VndPositive = Annotated[int, Field(ge=1, le=MAX_VND)]
JarCode = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
BlockId = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")]
TraceId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
FallbackText = Annotated[str, Field(min_length=1, max_length=280)]
IsoDate = Annotated[str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")]
IsoDateTime = Annotated[
    str,
    Field(
        pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})$"
    ),
]
JarName = Annotated[str, Field(min_length=1, max_length=40)]
KeyName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")]
Summary = Annotated[str, Field(min_length=1, max_length=120)]
ToolName = Literal["move_between_jars"]


class _Strict(BaseModel):
    """`extra=forbid` giống `additionalProperties: false`: phía sinh dữ liệu phải chặt."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Source(_Strict):
    tool: Annotated[str, Field(min_length=1, max_length=80)]
    as_of: IsoDateTime
    app_date: IsoDate


class _BlockBase(_Strict):
    v: Literal[1]
    id: BlockId
    trace_id: TraceId
    fallback_text: FallbackText
    source: Source


# --- jar_summary --------------------------------------------------------------------------
class JarBalance(_Strict):
    code: JarCode
    name: JarName
    color_key: KeyName
    icon_key: KeyName
    balance_vnd: Vnd
    split_percent: Annotated[float, Field(ge=0, le=100)]


class JarSummaryData(_Strict):
    jars: Annotated[list[JarBalance], Field(max_length=20)]
    jars_total_vnd: Vnd


class JarSummaryBlock(_BlockBase):
    type: Literal["jar_summary"]
    data: JarSummaryData


# --- confirm ------------------------------------------------------------------------------
class MoveParams(_Strict):
    from_jar: JarCode
    to_jar: JarCode
    amount_vnd: VndPositive


class JarChange(_Strict):
    code: JarCode
    name: JarName
    before_vnd: Vnd
    after_vnd: Vnd


class ConfirmPreview(_Strict):
    # `from` là từ khóa Python: dùng alias.
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, populate_by_name=True)
    from_: JarChange = Field(alias="from")
    to: JarChange


class ConfirmData(_Strict):
    tool: ToolName
    params: MoveParams
    params_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    summary: Summary
    preview: ConfirmPreview
    expires_at: IsoDateTime


class ConfirmBlock(_BlockBase):
    type: Literal["confirm"]
    data: ConfirmData


# --- receipt ------------------------------------------------------------------------------
class JarAfter(_Strict):
    code: JarCode
    name: JarName
    balance_after_vnd: Vnd


class ReceiptData(_Strict):
    tool: ToolName
    transaction_id: Annotated[
        str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    ]
    occurred_at: IsoDateTime
    app_date: IsoDate
    amount_vnd: VndPositive
    summary: Summary
    from_jar: JarAfter
    to_jar: JarAfter


class ReceiptBlock(_BlockBase):
    type: Literal["receipt"]
    data: ReceiptData


# --- notice -------------------------------------------------------------------------------
NoticeKind = Literal["out_of_scope", "degraded", "low_data", "error"]


class NoticeData(_Strict):
    kind: NoticeKind
    title: Annotated[str, Field(min_length=1, max_length=80)]
    message: Annotated[str, Field(min_length=1, max_length=280)]
    code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]*$")] | None = None


class NoticeBlock(_BlockBase):
    type: Literal["notice"]
    data: NoticeData


# --- forecast_timeline ---------------------------------------------------------------------
VndSigned = Annotated[int, Field(ge=-MAX_VND, le=MAX_VND)]
Ratio = Annotated[float, Field(ge=0, le=1)]
Uuid = Annotated[
    str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
]
JarStatus = Literal["ok", "tight", "short"]
ConfidenceBand = Literal["high", "medium", "low"]


class ForecastJar(_Strict):
    code: JarCode
    name: JarName
    color_key: KeyName
    icon_key: KeyName


class ForecastPayday(_Strict):
    date: IsoDate
    days_until: Annotated[int, Field(ge=0, le=400)]


class ForecastDay(_Strict):
    date: IsoDate
    p10_vnd: VndSigned
    p50_vnd: VndSigned
    p90_vnd: VndSigned


class ForecastEvent(_Strict):
    date: IsoDate
    kind: Literal["obligation", "salary"]
    label: Annotated[str, Field(min_length=1, max_length=60)]
    amount_vnd: VndPositive
    amount_max_vnd: VndPositive | None = None


class ForecastTimelineData(_Strict):
    jar: ForecastJar
    status: JarStatus
    origin_date: IsoDate
    start_balance_vnd: VndSigned
    horizon_days: Annotated[int, Field(ge=1, le=90)]
    payday: ForecastPayday
    runout_date: IsoDate | None = None
    p_shortfall: Ratio | None = None
    p_shortfall_se: Ratio | None = None
    confidence_band: ConfidenceBand
    coverage: Ratio | None = None
    history_days: Annotated[int, Field(ge=0)]
    is_initial_estimate: bool
    model: Annotated[str, Field(min_length=1, max_length=40)]
    computed_at: IsoDateTime
    stale: bool
    days: Annotated[list[ForecastDay], Field(min_length=1, max_length=90)]
    events: Annotated[list[ForecastEvent], Field(max_length=60)]


class ForecastTimelineBlock(_BlockBase):
    type: Literal["forecast_timeline"]
    data: ForecastTimelineData


# --- proactive_card ------------------------------------------------------------------------
ProactiveKind = Literal[
    "runout_warning", "obligation_due", "salary_pending", "review_needed", "low_data"
]
ProactiveActionKind = Literal[
    "open_forecast", "confirm_salary", "review_unclassified", "open_obligations",
    "ask_why", "snooze", "mute_kind",
]  # fmt: skip


class ProactiveAction(_Strict):
    kind: ProactiveActionKind
    label: Annotated[str, Field(min_length=1, max_length=40)]
    jar_code: JarCode | None = None
    prompt: Annotated[str, Field(min_length=1, max_length=200)] | None = None


class ProactiveCardData(_Strict):
    kind: ProactiveKind
    status: JarStatus
    title: Annotated[str, Field(min_length=1, max_length=80)]
    reason: Annotated[str, Field(min_length=1, max_length=200)]
    jar_code: JarCode | None = None
    actions: Annotated[list[ProactiveAction], Field(min_length=1, max_length=4)]


class ProactiveCardBlock(_BlockBase):
    type: Literal["proactive_card"]
    data: ProactiveCardData


# --- confirm_action ------------------------------------------------------------------------
ConfirmActionTool = Literal[
    "record_transaction", "assign_jar", "update_profile", "save_jars", "confirm_salary"
]


class ActionChange(_Strict):
    label: Annotated[str, Field(min_length=1, max_length=60)]
    before: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    after: Annotated[str, Field(min_length=1, max_length=120)]


class ConfirmActionData(_Strict):
    tool: ConfirmActionTool
    params: dict[str, Any]
    params_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    summary: Summary
    changes: Annotated[list[ActionChange], Field(min_length=1, max_length=20)]
    warnings: (
        Annotated[list[Annotated[str, Field(min_length=1, max_length=140)]], Field(max_length=5)]
        | None
    ) = None
    expires_at: IsoDateTime


class ConfirmActionBlock(_BlockBase):
    type: Literal["confirm_action"]
    data: ConfirmActionData


# --- receipt_action ------------------------------------------------------------------------
class ReceiptDetail(_Strict):
    label: Annotated[str, Field(min_length=1, max_length=60)]
    value: Annotated[str, Field(min_length=1, max_length=120)]


class ReceiptFollowUp(_Strict):
    kind: Literal["confirm_salary", "review_unclassified"]
    label: Annotated[str, Field(min_length=1, max_length=80)]
    salary_event_id: Uuid | None = None
    expected_vnd: VndPositive | None = None
    received_vnd: VndPositive | None = None
    deviation_percent: Annotated[float, Field(ge=-100000, le=100000)] | None = None
    ask_update_salary: bool | None = None


class JarBalanceAfter(_Strict):
    code: JarCode
    name: JarName
    balance_after_vnd: VndSigned


class ReceiptActionData(_Strict):
    tool: ConfirmActionTool
    reference_id: Uuid | None = None
    occurred_at: IsoDateTime
    app_date: IsoDate
    amount_vnd: VndPositive | None = None
    summary: Summary
    jars_after: Annotated[list[JarBalanceAfter], Field(max_length=20)]
    details: Annotated[list[ReceiptDetail], Field(max_length=20)]
    follow_up: ReceiptFollowUp | None = None


class ReceiptActionBlock(_BlockBase):
    type: Literal["receipt_action"]
    data: ReceiptActionData


Block = Annotated[
    JarSummaryBlock
    | ConfirmBlock
    | ReceiptBlock
    | NoticeBlock
    | ForecastTimelineBlock
    | ProactiveCardBlock
    | ConfirmActionBlock
    | ReceiptActionBlock,
    Field(discriminator="type"),
]
BLOCK_ADAPTER: TypeAdapter[Any] = TypeAdapter(Block)

#: type -> model, cùng thứ tự với `contracts/blocks/block.schema.json`.
BLOCK_MODELS: dict[str, type[_BlockBase]] = {
    "jar_summary": JarSummaryBlock,
    "confirm": ConfirmBlock,
    "receipt": ReceiptBlock,
    "notice": NoticeBlock,
    "forecast_timeline": ForecastTimelineBlock,
    "proactive_card": ProactiveCardBlock,
    "confirm_action": ConfirmActionBlock,
    "receipt_action": ReceiptActionBlock,
}


def parse_block(obj: Mapping[str, Any]) -> _BlockBase:
    """Kiểm một khối đã biết (ném `pydantic.ValidationError` nếu sai)."""
    return BLOCK_ADAPTER.validate_python(obj)


def block_to_wire(block: _BlockBase) -> dict[str, Any]:
    """Dạng JSON gửi đi: bỏ trường tùy chọn vắng (không phát `null`), `from` thay `from_`."""
    return block.model_dump(mode="json", by_alias=True, exclude_none=True)


# --- trace id -----------------------------------------------------------------------------
_TRACEPARENT_RE = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$")


def trace_id_from_traceparent(header: str | None) -> str | None:
    """Lấy trace-id (32 hex) từ header W3C `traceparent`; không hợp lệ thì trả None."""
    if not header:
        return None
    m = _TRACEPARENT_RE.match(header.strip().lower())
    if not m or set(m.group(1)) == {"0"}:
        return None
    return m.group(1)


def new_trace_id() -> str:
    """trace id do server sinh khi client không gửi `traceparent` (REST)."""
    return uuid.uuid4().hex


# --- dựng khối ----------------------------------------------------------------------------
def format_instant(value: datetime) -> str:
    """RFC 3339 ở UTC, giây, hậu tố Z (ví dụ `2026-11-21T03:00:00Z`)."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Thời điểm phải có múi giờ")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _source(tool: str, as_of: datetime, app_date: date) -> Source:
    return Source(tool=tool, as_of=format_instant(as_of), app_date=app_date.isoformat())


def _percent(value: int | float | Decimal | str) -> float:
    p = Decimal(str(value))
    return int(p) if p == p.to_integral_value() else float(p)  # type: ignore[return-value]


def _jar_row(row: Mapping[str, Any]) -> JarBalance:
    return JarBalance(
        code=row["code"],
        name=row["name"],
        color_key=row["color_key"],
        icon_key=row["icon_key"],
        balance_vnd=to_vnd(row["balance_vnd"]),
        split_percent=_percent(row["split_percent"]),
    )


def build_jar_summary(
    *,
    jars: Iterable[Mapping[str, Any]],
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    block_id: str | None = None,
) -> JarSummaryBlock:
    """Khối số dư các hũ. `jars` theo thứ tự hiển thị; mỗi dòng gồm code, name, color_key,
    icon_key, balance_vnd, split_percent (giá trị đọc từ DB, tiền có thể là Decimal/chuỗi)."""
    rows = [_jar_row(r) for r in jars]
    total = sum(r.balance_vnd for r in rows)
    text = f"Số dư {len(rows)} hũ, tổng {format_vnd(total)}." if rows else "Bạn chưa có hũ nào."
    return JarSummaryBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"jar_summary:{trace_id}",
        type="jar_summary",
        trace_id=trace_id,
        fallback_text=text,
        source=_source(source_tool, as_of, app_date),
        data=JarSummaryData(jars=rows, jars_total_vnd=total),
    )


def build_confirm(
    *,
    tool: str,
    params: Mapping[str, Any],
    from_jar: Mapping[str, Any],
    to_jar: Mapping[str, Any],
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    expires_at: datetime,
    block_id: str | None = None,
) -> ConfirmBlock:
    """Khối xác nhận cho `move_between_jars`.

    `params` được chuẩn hóa ở đây và `params_hash` tính từ chính bản đã chuẩn hóa, nên khối luôn
    chứa đúng thứ sẽ được ký. `from_jar`/`to_jar` là dòng hũ hiện tại (code, name, balance_vnd).
    Ném `ParamsError` nếu tham số sai, `ValueError` nếu hũ không khớp tham số hoặc không đủ tiền
    (tool phải trả INSUFFICIENT_FUNDS trước khi tới đây).
    """
    if tool != MOVE_BETWEEN_JARS:
        raise ValueError(f"build_confirm chưa hỗ trợ tool {tool!r}")
    norm = normalize_params(tool, params)
    if from_jar["code"] != norm["from_jar"] or to_jar["code"] != norm["to_jar"]:
        raise ValueError("Hũ truyền vào không khớp tham số đã chuẩn hóa")
    amount = norm["amount_vnd"]
    before_from, before_to = to_vnd(from_jar["balance_vnd"]), to_vnd(to_jar["balance_vnd"])
    if before_from < amount:
        raise ValueError("Hũ nguồn không đủ số dư; không dựng khối xác nhận")
    digest = params_hash(tool, norm)
    summary = f"Chuyển {format_vnd(amount)} từ {from_jar['name']} sang {to_jar['name']}"
    return ConfirmBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"confirm:{trace_id}:{digest[:12]}",
        type="confirm",
        trace_id=trace_id,
        fallback_text=f"{summary}. Cần bạn xác nhận trên ứng dụng.",
        source=_source(source_tool, as_of, app_date),
        data=ConfirmData(
            tool=tool,
            params=MoveParams(**norm),
            params_hash=digest,
            summary=summary,
            preview=ConfirmPreview(
                from_=JarChange(
                    code=norm["from_jar"],
                    name=from_jar["name"],
                    before_vnd=before_from,
                    after_vnd=before_from - amount,
                ),
                to=JarChange(
                    code=norm["to_jar"],
                    name=to_jar["name"],
                    before_vnd=before_to,
                    after_vnd=before_to + amount,
                ),
            ),
            expires_at=format_instant(expires_at),
        ),
    )


def build_receipt(
    *,
    tool: str,
    transaction_id: str,
    occurred_at: datetime,
    app_date: date,
    amount_vnd: int | Decimal | str,
    from_jar: Mapping[str, Any],
    to_jar: Mapping[str, Any],
    trace_id: str,
    source_tool: str,
    block_id: str | None = None,
) -> ReceiptBlock:
    """Biên nhận. `from_jar`/`to_jar` là hũ sau khi commit (code, name, balance_vnd = số dư sau)."""
    if tool != MOVE_BETWEEN_JARS:
        raise ValueError(f"build_receipt chưa hỗ trợ tool {tool!r}")
    amount = to_vnd(amount_vnd)
    summary = f"Đã chuyển {format_vnd(amount)} từ {from_jar['name']} sang {to_jar['name']}"
    return ReceiptBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"receipt:{transaction_id}",
        type="receipt",
        trace_id=trace_id,
        fallback_text=f"{summary}.",
        source=_source(source_tool, occurred_at, app_date),
        data=ReceiptData(
            tool=tool,
            transaction_id=transaction_id,
            occurred_at=format_instant(occurred_at),
            app_date=app_date.isoformat(),
            amount_vnd=amount,
            summary=summary,
            from_jar=JarAfter(
                code=from_jar["code"],
                name=from_jar["name"],
                balance_after_vnd=to_vnd(from_jar["balance_vnd"]),
            ),
            to_jar=JarAfter(
                code=to_jar["code"],
                name=to_jar["name"],
                balance_after_vnd=to_vnd(to_jar["balance_vnd"]),
            ),
        ),
    )


def build_notice(
    *,
    kind: NoticeKind,
    title: str,
    message: str,
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    code: str | None = None,
    block_id: str | None = None,
) -> NoticeBlock:
    """Thông báo trạng thái. `message` do code/cấu hình cung cấp, không chứa số liệu tài chính."""
    return NoticeBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"notice:{trace_id}:{code or kind}",
        type="notice",
        trace_id=trace_id,
        fallback_text=message,
        source=_source(source_tool, as_of, app_date),
        data=NoticeData(kind=kind, title=title, message=message, code=code),
    )


# --- dựng khối phase 2 ---------------------------------------------------------------------
def _clip(text: str, limit: int) -> str:
    """Cắt chuỗi hiển thị về `limit` ký tự (thêm dấu ba chấm nếu bị cắt)."""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _date_text(value: date | str) -> str:
    """`date` hoặc chuỗi YYYY-MM-DD thành chuỗi ngày hợp đồng."""
    return value.isoformat() if isinstance(value, date) else str(value)


def _dm(value: date | str) -> str:
    """'23/11' từ ngày YYYY-MM-DD (dùng trong câu hiển thị)."""
    d = value if isinstance(value, date) else date.fromisoformat(str(value))
    return f"{d.day:02d}/{d.month:02d}"


def _instant_text(value: datetime | str) -> str:
    """Thời điểm của hàng đọc từ Data API (datetime hoặc chuỗi `YYYY-MM-DD HH:MM:SS[.ffffff]` ở UTC,
    không hậu tố) thành RFC 3339 `...Z`."""
    if isinstance(value, datetime):
        return format_instant(value)
    text = str(value).strip().replace(" ", "T")
    if text.endswith("Z") or "+" in text[10:] or "-" in text[10:]:
        return format_instant(datetime.fromisoformat(text.replace("Z", "+00:00")))
    return format_instant(datetime.fromisoformat(text).replace(tzinfo=UTC))


def _ratio(value: Any) -> float:
    return float(Decimal(str(value)))


def build_confirm_action(
    *,
    tool: str,
    params: Mapping[str, Any],
    summary: str,
    changes: Iterable[Mapping[str, Any]],
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    expires_at: datetime,
    warnings: Iterable[str] = (),
    block_id: str | None = None,
) -> ConfirmActionBlock:
    """Khối xác nhận cho tool ghi KHÔNG phải chuyển hũ.

    `params` phải là bản ĐÃ chuẩn hóa theo hợp đồng (contracts/README.md, mục "Chuẩn hóa tham số"; việc
    chuẩn hóa từng tool nằm ở tầng ledger). `params_hash` tính từ chính bản này bằng
    `hash_normalized_params`, nên khối luôn chứa đúng thứ sẽ được ký. `changes` mỗi phần tử gồm
    `label`, `after` và tùy chọn `before` (chuỗi đã định dạng sẵn). Ném `ValueError` nếu tool không dùng khối này.
    """
    if tool not in GENERIC_ACTION_TOOLS:
        raise ValueError(f"build_confirm_action không hỗ trợ tool {tool!r}")
    digest = hash_normalized_params(tool, params)
    summary = _clip(summary, 120)
    return ConfirmActionBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"confirm:{trace_id}:{digest[:12]}",
        type="confirm_action",
        trace_id=trace_id,
        fallback_text=_clip(f"{summary}. Cần bạn xác nhận trên ứng dụng.", 280),
        source=_source(source_tool, as_of, app_date),
        data=ConfirmActionData(
            tool=tool,  # type: ignore[arg-type]
            params=dict(params),
            params_hash=digest,
            summary=summary,
            changes=[ActionChange(**c) for c in changes],
            warnings=list(warnings) or None,
            expires_at=format_instant(expires_at),
        ),
    )


def build_receipt_action(
    *,
    tool: str,
    occurred_at: datetime,
    app_date: date,
    summary: str,
    trace_id: str,
    source_tool: str,
    reference_id: str | None = None,
    amount_vnd: int | Decimal | str | None = None,
    jars_after: Iterable[Mapping[str, Any]] = (),
    details: Iterable[Mapping[str, str]] = (),
    follow_up: Mapping[str, Any] | None = None,
    block_id: str | None = None,
) -> ReceiptActionBlock:
    """Biên nhận của tool ghi KHÔNG phải chuyển hũ. `jars_after`: mỗi hũ có code, name, balance_vnd (số dư sau,
    có thể âm với hũ Chưa phân loại). `details`: các dòng `{label, value}` đã định dạng. Ném `ValueError` nếu
    tool không dùng khối này."""
    if tool not in GENERIC_ACTION_TOOLS:
        raise ValueError(f"build_receipt_action không hỗ trợ tool {tool!r}")
    summary = _clip(summary, 120)
    return ReceiptActionBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"receipt:{tool}:{reference_id or trace_id}",
        type="receipt_action",
        trace_id=trace_id,
        fallback_text=_clip(f"{summary}.", 280),
        source=_source(source_tool, occurred_at, app_date),
        data=ReceiptActionData(
            tool=tool,  # type: ignore[arg-type]
            reference_id=reference_id,
            occurred_at=format_instant(occurred_at),
            app_date=app_date.isoformat(),
            amount_vnd=None if amount_vnd is None else to_vnd(amount_vnd),
            summary=summary,
            jars_after=[
                JarBalanceAfter(
                    code=j["code"], name=j["name"], balance_after_vnd=to_vnd(j["balance_vnd"])
                )
                for j in jars_after
            ],
            details=[ReceiptDetail(**d) for d in details],
            follow_up=ReceiptFollowUp(**follow_up) if follow_up else None,
        ),
    )


def _forecast_sentence(
    name: str,
    status: str,
    runout: date | str | None,
    payday: date | str,
    stale: bool,
    initial: bool,
) -> str:
    if status == "short" and runout:
        gap = (date.fromisoformat(_date_text(payday)) - date.fromisoformat(_date_text(runout))).days
        text = (
            f"Hũ {name} dự kiến cạn ngày {_dm(runout)}, còn {gap} ngày tới kỳ lương {_dm(payday)}."
        )
    elif status == "short":
        text = f"Hũ {name} dự kiến hụt trước kỳ lương {_dm(payday)}."
    elif status == "tight":
        text = f"Hũ {name} sát: dự kiến còn rất ít tiền trước kỳ lương {_dm(payday)}."
    else:
        text = f"Hũ {name} đủ tới kỳ lương {_dm(payday)}."
    if initial:
        text += " Đây là ước lượng ban đầu."
    if stale:
        text += " Số liệu đã cũ."
    return _clip(text, 280)


def build_forecast_timeline(
    *,
    jar: Mapping[str, Any],
    summary: Mapping[str, Any],
    days: Iterable[Mapping[str, Any]],
    events: Iterable[Mapping[str, Any]],
    stale: bool,
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    block_id: str | None = None,
) -> ForecastTimelineBlock:
    """Khối dự báo của MỘT hũ từ các hàng đọc ở DB, dùng chung cho màn hình và chat.

    - `jar`: code, name, color_key, icon_key.
    - `summary`: một hàng của `app_get_forecast_summaries` (computed_at, run_app_date, model, horizon_days,
      history_days, data_coverage, is_initial_estimate, start_balance_vnd, payday_date, days_to_payday,
      runout_date, p_shortfall, p_shortfall_se, status, confidence_band, show_probability).
    - `days`: các hàng của `app_get_forecast_series` (day, balance_p10_vnd, balance_p50_vnd, balance_p90_vnd).
    - `events`: mốc đã ghép từ nghĩa vụ và lịch lương, mỗi mốc có date, kind, label, amount_vnd, amount_max_vnd tùy chọn.
    - `p_shortfall` chỉ được phát khi `show_probability` đúng và có giá trị (quy tắc hiển thị của hợp đồng).
    Tiền Data API trả dạng chuỗi hoặc Decimal đều được; số âm giữ nguyên dấu.
    """
    show_p = bool(summary.get("show_probability")) and summary.get("p_shortfall") is not None
    runout = summary.get("runout_date")
    coverage = summary.get("data_coverage")
    payday = _date_text(summary["payday_date"])
    data = ForecastTimelineData(
        jar=ForecastJar(
            code=jar["code"], name=jar["name"], color_key=jar["color_key"], icon_key=jar["icon_key"]
        ),
        status=summary["status"],
        origin_date=_date_text(summary["run_app_date"]),
        start_balance_vnd=to_vnd(summary["start_balance_vnd"]),
        horizon_days=int(summary["horizon_days"]),
        payday=ForecastPayday(date=payday, days_until=int(summary["days_to_payday"])),
        runout_date=_date_text(runout) if runout else None,
        p_shortfall=_ratio(summary["p_shortfall"]) if show_p else None,
        p_shortfall_se=(
            _ratio(summary["p_shortfall_se"])
            if show_p and summary.get("p_shortfall_se") is not None
            else None
        ),
        confidence_band=summary["confidence_band"],
        coverage=_ratio(coverage) if coverage is not None else None,
        history_days=int(summary["history_days"]),
        is_initial_estimate=bool(summary["is_initial_estimate"]),
        model=summary["model"],
        computed_at=_instant_text(summary["computed_at"]),
        stale=stale,
        days=[
            ForecastDay(
                date=_date_text(d["day"]),
                p10_vnd=to_vnd(d["balance_p10_vnd"]),
                p50_vnd=to_vnd(d["balance_p50_vnd"]),
                p90_vnd=to_vnd(d["balance_p90_vnd"]),
            )
            for d in days
        ],
        events=[
            ForecastEvent(
                date=_date_text(e["date"]),
                kind=e["kind"],
                label=e["label"],
                amount_vnd=to_vnd(e["amount_vnd"]),
                amount_max_vnd=(
                    to_vnd(e["amount_max_vnd"]) if e.get("amount_max_vnd") is not None else None
                ),
            )
            for e in events
        ],
    )
    return ForecastTimelineBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"forecast_timeline:{trace_id}:{data.jar.code}",
        type="forecast_timeline",
        trace_id=trace_id,
        fallback_text=_forecast_sentence(
            data.jar.name, data.status, data.runout_date, payday, stale, data.is_initial_estimate
        ),
        source=_source(source_tool, as_of, app_date),
        data=data,
    )


def build_proactive_card(
    *,
    kind: str,
    status: str,
    title: str,
    reason: str,
    actions: Iterable[Mapping[str, Any]],
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    jar_code: str | None = None,
    block_id: str | None = None,
) -> ProactiveCardBlock:
    """Thẻ chủ động (một việc). `title` và `reason` do code dựng từ số liệu thật, không do LLM viết;
    `actions` đứng đầu là hành động chính (mỗi phần tử: kind, label, jar_code tùy chọn, prompt tùy chọn)."""
    return ProactiveCardBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"proactive_card:{trace_id}:{kind}",
        type="proactive_card",
        trace_id=trace_id,
        fallback_text=_clip(f"{title}. {reason}", 280),
        source=_source(source_tool, as_of, app_date),
        data=ProactiveCardData(
            kind=kind,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            title=title,
            reason=reason,
            jar_code=jar_code,
            actions=[ProactiveAction(**a) for a in actions],
        ),
    )
