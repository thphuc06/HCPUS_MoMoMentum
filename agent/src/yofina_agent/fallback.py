"""Bộ phân loại dự phòng dựa trên luật (SUY GIẢM CÓ KIỂM SOÁT, không phải đường chính).

Chỉ dùng khi router bằng LLM không gọi được (chạm trần lượt gọi, mọi model lỗi, JSON hỏng).
Mục đích duy nhất: vẫn nhận ra mấy ý định mà agent có tool tất định cho (số dư, giao dịch, dự báo một hũ, chuyển hũ), để người dùng nhận được
thẻ số liệu thật từ tool thay vì luồng rỗng. Không phải nhánh riêng cho câu nào: luật chỉ dựa trên
từ khóa chung về số dư / giao dịch / dự báo (cạn, trụ được, bao lâu) / chuyển tiền, và tên hũ vẫn được ánh xạ bằng dữ liệu tool.
Câu không khớp luật nào trả `None`: agent hiện thông báo "chưa xử lý được" chứ không đoán.
"""

from __future__ import annotations

import re

from yofina_agent.router import RouterOutput
from yofina_agent.textutil import normalize, parse_amount_vnd

_BALANCE = ("so du", "con bao nhieu", "con lai bao nhieu", "cac hu", "hu cua minh", "tong tien")
_TRANSACTIONS = ("giao dich", "lich su", "da tieu", "chi tieu gan day", "chi gan day", "vua tieu")
_FORECAST = (
    "du bao",
    "tru duoc",
    "bao lau",
    "het tien",
    "can tien",
    "du toi ky luong",
    "du den ky luong",
)
_FORECAST_WHEN = re.compile(
    r"\b(?:khi nao|bao gio)\b.*\b(?:can|het)\b"
)  # "khi nào hũ X cạn", "bao giờ hết"
_MOVE_VERB = ("chuyen", "dieu chuyen", "rut tu", "doi tien")
_AMOUNT_TOKEN = re.compile(r"\d[\d.,]*\s*(?:k|nghin|ngan|trieu|tr|ty|ti|d|dong|vnd)?\b")
_FROM_TO = re.compile(r"\b(?:tu|rut tu)\s+(?P<src>.+?)\s+(?:sang|vao|den|qua)\s+(?P<dst>.+)$")
_TO_FROM = re.compile(r"\b(?:sang|vao|den|qua)\s+(?P<dst>.+?)\s+tu\s+(?P<src>.+)$")


def _has(norm: str, words: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", norm) for w in words)


def _clean_jar(fragment: str) -> str | None:
    return _AMOUNT_TOKEN.sub(" ", fragment).strip() or None


def classify_by_rules(text: str) -> RouterOutput | None:
    norm = normalize(text)
    if not norm:
        return None
    if _has(norm, _MOVE_VERB):
        m = _FROM_TO.search(norm) or _TO_FROM.search(norm)
        return RouterOutput(
            intent="move_between_jars",
            from_jar_text=_clean_jar(m["src"]) if m else None,
            to_jar_text=_clean_jar(m["dst"]) if m else None,
            amount_vnd=parse_amount_vnd(text),
        )
    if _has(norm, _FORECAST) or _FORECAST_WHEN.search(norm):
        return RouterOutput(intent="forecast_lookup")
    if _has(norm, _TRANSACTIONS):
        return RouterOutput(intent="transactions_lookup")
    if _has(norm, _BALANCE):
        return RouterOutput(intent="balance_lookup")
    return None
