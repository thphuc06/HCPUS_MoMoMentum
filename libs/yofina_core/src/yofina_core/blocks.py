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
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from yofina_core.confirm import MOVE_BETWEEN_JARS, normalize_params, params_hash
from yofina_core.money import format_vnd, to_vnd

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


Block = Annotated[
    JarSummaryBlock | ConfirmBlock | ReceiptBlock | NoticeBlock, Field(discriminator="type")
]
BLOCK_ADAPTER: TypeAdapter[Any] = TypeAdapter(Block)

#: type -> model, cùng thứ tự với `contracts/blocks/block.schema.json`.
BLOCK_MODELS: dict[str, type[_BlockBase]] = {
    "jar_summary": JarSummaryBlock,
    "confirm": ConfirmBlock,
    "receipt": ReceiptBlock,
    "notice": NoticeBlock,
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
