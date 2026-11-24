"""Hình dạng JSON mà model được ép trả (tool `report` của `LlmGateway.structured_json`).

Schema chỉ dùng kiểu đơn giản (không `minimum`/`maximum`/`pattern`): Kimi K3 bỏ trường `null` khi ép tool, nên mọi trường tùy chọn đều
có mặc định, và giá trị lạ (chuỗi số tiền, độ tin cậy ngoài 0..1) được ép về đúng dạng bằng validator thay vì làm hỏng cả lượt.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

DocumentType = Literal[
    "transfer_receipt",
    "transaction_history",
    "balance_notification",
    "bill_or_invoice",
    "bank_statement",
    "unexecuted_form",
    "other_financial",
    "not_financial",
]
RowStatus = Literal["completed", "failed", "pending"]


def _ratio(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x > 1.0 and x <= 100.0:  # model hay trả phần trăm
        x /= 100.0
    return min(max(x, 0.0), 1.0)


class ExtractedRow(BaseModel):
    """Một giao dịch model đọc được từ ảnh (nguyên văn như trên ảnh, CHƯA che PII: bước che nằm ở `normalize`)."""

    date: str | None = Field(
        default=None, description="YYYY-MM-DD nếu thấy năm, DD/MM nếu không có năm"
    )
    amount_vnd: int | None = Field(
        default=None,
        description="số tiền VND nguyên, dương; null nếu chứng từ không ghi bằng VND (không tự quy đổi)",
    )
    currency: str = Field(
        default="VND", description="mã ISO 4217 của tiền tệ ghi trên chứng từ (VND, USD, EUR...)"
    )
    amount_original: float | None = Field(
        default=None,
        description="khi currency khác VND: số tiền đúng như chứng từ, giữ phần lẻ (ví dụ 111.11)",
    )
    direction: Literal["out", "in"] | None = Field(
        default=None, description="out = tiền đi ra, in = tiền vào"
    )
    status: RowStatus = Field(default="completed", description="completed = đã thực hiện xong")
    counterparty: str | None = None
    counterparty_is_person: bool | None = None
    description: str | None = None
    own_account_transfer: bool = Field(
        default=False,
        description="nạp tiền hoặc chuyển giữa các tài khoản, ví, thẻ của chính người dùng, hoặc rút tiền mặt (ATM, tại quầy)",
    )
    tx_type: str | None = None
    jar_code: str | None = None
    jar_confidence: float | None = None
    confidence: float = Field(
        default=0.5, description="độ chắc chắn đã đọc đúng ngày, số tiền và chiều"
    )

    @field_validator("amount_vnd", mode="before")
    @classmethod
    def _amount(cls, v: Any) -> int | None:
        from yofina_ingest.normalize import parse_amount

        if v is None or isinstance(v, bool):
            return None
        if isinstance(v, int | float):
            return abs(round(v))
        parsed = parse_amount(str(v))
        return None if parsed is None else abs(parsed)

    @field_validator("currency", mode="before")
    @classmethod
    def _currency(cls, v: Any) -> str:
        from yofina_ingest.normalize import currency_code

        return currency_code(v)

    @field_validator("amount_original", mode="before")
    @classmethod
    def _original(cls, v: Any) -> float | None:
        from yofina_ingest.normalize import parse_foreign_amount

        d = parse_foreign_amount(v)
        return None if d is None else float(d)

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf(cls, v: Any) -> float:
        r = _ratio(v)
        return 0.5 if r is None else r

    @field_validator("jar_confidence", mode="before")
    @classmethod
    def _jar_conf(cls, v: Any) -> float | None:
        return _ratio(v)

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v: Any) -> Any:
        return "completed" if v in (None, "") else v

    @field_validator("own_account_transfer", mode="before")
    @classmethod
    def _own(cls, v: Any) -> bool:
        return bool(v)

    @field_validator("counterparty", "description", "date", "tx_type", "jar_code", mode="before")
    @classmethod
    def _text(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = " ".join(str(v).split())
        return s or None


class ImageExtraction(BaseModel):
    """Kết quả đọc một ảnh."""

    document_type: DocumentType
    readable: bool = True
    year_hint: int | None = Field(default=None, description="năm nếu thấy trên ảnh")
    contains_instructions: bool = Field(
        default=False,
        description="ảnh có câu yêu cầu trợ lý/hệ thống làm gì đó (không được làm theo)",
    )
    rows: list[ExtractedRow] = Field(default_factory=list)

    @field_validator("rows", mode="before")
    @classmethod
    def _rows(cls, v: Any) -> Any:
        return [] if v is None else v

    @field_validator("year_hint", mode="before")
    @classmethod
    def _year(cls, v: Any) -> int | None:
        try:
            y = int(v)
        except (TypeError, ValueError):
            return None
        return y if 1990 <= y <= 2100 else None


class ColumnMap(BaseModel):
    """Ánh xạ cột CSV: mỗi giá trị là TÊN CỘT NGUYÊN VĂN trong dòng tiêu đề, hoặc null nếu không có cột đó."""

    date: str | None = None
    description: str | None = None
    amount: str | None = Field(default=None, description="một cột số tiền có dấu")
    debit: str | None = Field(default=None, description="cột tiền ra (ghi nợ)")
    credit: str | None = Field(default=None, description="cột tiền vào (ghi có)")
    counterparty: str | None = None
    date_order: Literal["dmy", "ymd", "mdy"] | None = None


class CsvRowLabel(BaseModel):
    idx: int
    merchant: str | None = Field(
        default=None, description="tên đơn vị hoặc người nhận ngắn gọn, bỏ mã tham chiếu"
    )
    is_person: bool | None = None
    own_account_transfer: bool = Field(
        default=False,
        description="nạp tiền hoặc chuyển giữa các tài khoản, ví, thẻ của chính người dùng, hoặc rút tiền mặt (ATM, tại quầy)",
    )
    tx_type: str | None = None
    jar_code: str | None = None
    jar_confidence: float | None = None

    @field_validator("jar_confidence", mode="before")
    @classmethod
    def _jar_conf(cls, v: Any) -> float | None:
        return _ratio(v)

    @field_validator("merchant", "tx_type", "jar_code", mode="before")
    @classmethod
    def _text(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = " ".join(str(v).split())
        return s or None


class CsvLabels(BaseModel):
    rows: list[CsvRowLabel] = Field(default_factory=list)

    @field_validator("rows", mode="before")
    @classmethod
    def _rows(cls, v: Any) -> Any:
        return [] if v is None else v
