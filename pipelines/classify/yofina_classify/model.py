"""Kiểu dữ liệu của phân hũ tự động (không I/O)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

#: nguồn của một bằng chứng; ánh xạ sang `transactions.classified_by` ở `decide.classified_by_of`
SOURCES = ("type_map", "rule", "embedding", "llm", "history")


@dataclass(frozen=True)
class TxFacts:
    """Dữ kiện của MỘT giao dịch cần phân loại (số tiền dương; tên đối tác CHƯA che)."""

    transaction_id: str
    user_id: str
    kind: str
    amount_vnd: int
    occurred_at: datetime
    app_date: date
    tx_type: str
    funding_source: str
    counterparty: str | None
    note: str | None
    payee_id: str | None
    is_person: bool
    jar_code: str | None  # hũ hiện tại
    in_unclassified: bool  # hũ hiện tại là hũ hệ thống Chưa phân loại


@dataclass(frozen=True)
class JarInfo:
    code: str
    name: str
    kind: str
    balance_vnd: int


@dataclass(frozen=True)
class TypeInfo:
    tx_type: str
    label: str
    direction: str
    default_jar_code: str | None


@dataclass(frozen=True)
class RuleHit:
    match_type: str  # payee | merchant
    key: str  # payee_id hoặc merchant_key
    jar_code: str


@dataclass
class UserContext:
    """Ngữ cảnh người dùng cho một lần phân loại."""

    jars: dict[str, JarInfo]  # hũ người dùng (không có hũ hệ thống)
    type_map: dict[str, TypeInfo]
    rule: RuleHit | None
    #: ngưỡng tự gán riêng của người nhận (payees.auto_min_confidence), None nếu chưa nâng
    payee_auto_min: float | None
    #: với đối tác không phải người nhận đã lưu: số luật `once` cùng khóa đối tác (số lần người dùng tự tay xử lý)
    merchant_corrections: int
    #: số giao dịch trước cùng người nhận (hoặc cùng đối tác) theo hũ (không tính Chưa phân loại)
    history: dict[str, int]
    tz: ZoneInfo


@dataclass(frozen=True)
class Neighbor:
    jar_code: str
    similarity: float  # 1 - khoảng cách cosine
    source: str = "user"


@dataclass(frozen=True)
class ExactLabel:
    jar_code: str
    source: str  # user | seed
    rank: int  # 0 = mới nhất


@dataclass(frozen=True)
class Evidence:
    jar: str
    p: float
    source: str  # một trong SOURCES
    detail: str = ""
    #: số đo thô sinh ra bằng chứng (k-NN: độ giống, biên; model: độ chắc báo): để hiệu chỉnh trên bộ kiểm
    features: tuple[float, ...] = ()


@dataclass(frozen=True)
class Verdict:
    """Kết quả của model nhỏ (đã kiểm: mã hũ thuộc danh sách của người dùng)."""

    jar_code: str | None
    confidence: float
    runner_up: str | None = None


@dataclass
class Decision:
    jar: str | None
    confidence: float
    tier: str  # auto | review | ask
    classified_by: str | None
    #: hũ ứng viên theo thứ tự giảm dần (cả hũ thắng); dùng cho gợi ý hỏi gộp
    candidates: list[tuple[str, float]]
    evidence: list[Evidence] = field(default_factory=list)
    #: bước cuối cùng đã chạy: type_map | rule | embedding | llm | none
    stage: str = "none"
    note: str = ""
    #: (text_norm, model, vector) nếu đã nhúng
    embedding: tuple[str, str, list[float]] | None = None
    llm_called: bool = False
    llm_error: str | None = None

    @property
    def assigned(self) -> bool:
        return self.tier in ("auto", "review") and self.jar is not None
