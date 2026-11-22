"""Bộ phân loại dự phòng dựa trên luật (SUY GIẢM CÓ KIỂM SOÁT, không phải đường chính).

Chỉ dùng khi router bằng LLM không gọi được (chạm trần lượt gọi, mọi model lỗi, JSON hỏng).
Mục đích duy nhất: vẫn nhận ra mấy ý định mà agent có tool tất định cho (số dư, giao dịch, dự báo một hũ, chuyển hũ, what-if và kiểm tra trước khi chi), để người dùng nhận được
thẻ số liệu thật từ tool thay vì luồng rỗng. Không phải nhánh riêng cho câu nào: luật chỉ dựa trên
từ khóa chung về số dư / giao dịch / dự báo (cạn, trụ được, bao lâu) / chuyển tiền, và tên hũ vẫn được ánh xạ bằng dữ liệu tool.
Câu không khớp luật nào trả `None`: agent hiện thông báo "chưa xử lý được" chứ không đoán.
"""

from __future__ import annotations

import re

from yofina_agent.schemas import IntentParams, IntentResult
from yofina_agent.textutil import normalize, parse_amount_vnd

_BALANCE = ("so du", "con bao nhieu", "con lai bao nhieu", "cac hu", "hu cua minh", "tong tien")
_TRANSACTIONS = ("giao dich", "lich su", "da tieu", "chi tieu gan day", "chi gan day", "vua tieu")
_OBLIGATIONS = ("den han", "sap den han", "khoan phai tra", "no cua minh", "nghia vu")
_FORECAST = (
    "du bao",
    "tru duoc",
    "bao lau",
    "het tien",
    "can tien",
    "du toi ky luong",
    "du den ky luong",
)
_FORECAST_WHEN = re.compile(r"\b(?:khi nao|bao gio)\b.*\b(?:can|het)\b")  # "khi nào hũ X cạn"
_WHAT_IF = re.compile(r"\b(?:neu|gia su)\b.*\b(?:thi sao|thi the nao|se ra sao)\b|\bthi sao\b|\bgia su\b")
_AFFORD = ("co on khong", "du tien", "kiem tra", "tra duoc khong", "co nen chi", "quet")
_CREDIT = ("tra sau", "bnpl", "mua truoc tra sau")
_MOVE_VERB = ("chuyen", "dieu chuyen", "rut tu", "doi tien")
_AMOUNT_TOKEN = re.compile(r"\d[\d.,]*\s*(?:k|nghin|ngan|trieu|tr|ty|ti|d|dong|vnd)?\b")
_FROM_TO = re.compile(r"\b(?:tu|rut tu)\s+(?P<src>.+?)\s+(?:sang|vao|den|qua)\s+(?P<dst>.+)$")
_TO_FROM = re.compile(r"\b(?:sang|vao|den|qua)\s+(?P<dst>.+?)\s+tu\s+(?P<src>.+)$")


def _has(norm: str, words: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", norm) for w in words)


def _clean_jar(fragment: str) -> str | None:
    return _AMOUNT_TOKEN.sub(" ", fragment).strip() or None


def _result(intent: str, **params: object) -> IntentResult:
    return IntentResult(
        intent=intent,  # type: ignore[arg-type]
        params=IntentParams(**params),  # type: ignore[arg-type]
        confidence=0.3,  # luật dự phòng: không bao giờ tự tin như model
        needs_clarification=False,
    )


def classify_by_rules(text: str) -> IntentResult | None:
    """Ý định bằng luật khi model không dùng được. Câu không khớp luật nào trả `None`."""
    norm = normalize(text)
    if not norm:
        return None
    amount = parse_amount_vnd(text)
    credit = _has(norm, _CREDIT)
    if _has(norm, _MOVE_VERB):
        m = _FROM_TO.search(norm) or _TO_FROM.search(norm)
        if m:
            return _result(
                "move",
                from_jar_text=_clean_jar(m["src"]),
                to_jar_text=_clean_jar(m["dst"]),
                amount_vnd=amount,
            )
        if amount is not None:  # "chuyển 250k cho bạn": không phải chuyển giữa hũ, là kiểm tra trước khi chi
            return _result("affordability", amount_vnd=amount, funding="credit" if credit else None)
        return _result("move")
    if _WHAT_IF.search(norm):
        return _result(
            "what_if",
            amount_vnd=amount,
            funding="credit" if credit else None,
            scenario_kind="bnpl_purchase" if credit else None,
        )
    if _has(norm, _AFFORD) and amount is not None:
        return _result("affordability", amount_vnd=amount, funding="credit" if credit else None)
    if _has(norm, _FORECAST) or _FORECAST_WHEN.search(norm):
        return _result("lookup", lookup_kind="forecast")
    if _has(norm, _TRANSACTIONS):
        return _result("lookup", lookup_kind="transactions")
    if _has(norm, _OBLIGATIONS):
        return _result("lookup", lookup_kind="obligations")
    if _has(norm, _BALANCE):
        return _result("lookup", lookup_kind="balance")
    return None
