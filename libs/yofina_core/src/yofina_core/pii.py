"""Che PII (thông tin định danh) trong văn bản người dùng gõ vào, TRƯỚC khi vào LLM, log hay bộ nhớ.

Guardrails không có mẫu PII Việt Nam, nên việc che nằm ở mã: số điện thoại, CCCD/CMND, số tài khoản ngân hàng, số thẻ, email.
Che bằng thẻ giữ chỗ (`[SĐT]`, `[CCCD]`, `[STK]`, `[THẺ]`, `[EMAIL]`), không bao giờ bỏ chữ trống để câu vẫn đọc được.

Số tiền KHÔNG được che: người dùng gõ "1200000" hay "15.000.000" là số tiền. Vì vậy dãy chữ số chỉ bị che khi có dạng đặc trưng
(đầu số điện thoại Việt Nam, đúng 12 chữ số, từ 10 chữ số liền không phân tách) hoặc đi sau từ khóa ("stk", "số tài khoản", "cmnd"...).
Đây là bộ lọc theo mẫu, không phải bảo đảm tuyệt đối; lớp phòng thủ khác là agent không bao giờ ghi nội dung chat vào log.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

#: tên loại -> thẻ giữ chỗ
PLACEHOLDERS: dict[str, str] = {
    "phone": "[SĐT]",
    "national_id": "[CCCD]",
    "account": "[STK]",
    "card": "[THẺ]",
    "email": "[EMAIL]",
}

_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w])")
# Thẻ: 13–19 chữ số, nhóm 4 chữ số cách nhau bằng khoảng trắng hoặc gạch.
_CARD = re.compile(r"(?<!\d)(?:\d{4}[ -]){3}\d{1,7}(?!\d)")
# Số điện thoại Việt Nam: +84/84/0 + đầu số 3,5,7,8,9 + 8 chữ số; cho phép dấu chấm, gạch, khoảng trắng giữa nhóm.
_PHONE = re.compile(r"(?<![\d.])(?:\+?84|0)[ .-]?[35789](?:[ .-]?\d){8}(?![\d])")
# Từ khóa đi trước số: (khoá, loại). Khoảng cách tối đa 25 ký tự không phải chữ số.
_KEYWORD_ID = re.compile(
    r"(?P<kw>cccd|cmnd|cmt|can cuoc|căn cước|chung minh|chứng minh|so dinh danh|số định danh)\D{0,25}?(?P<num>\d{9}|\d{12})(?!\d)",
    re.IGNORECASE,
)
_KEYWORD_ACCOUNT = re.compile(
    r"(?P<kw>stk|so tai khoan|số tài khoản|so tk|số tk|account number)\D{0,12}?(?P<num>\d{8,19})(?!\d)",
    re.IGNORECASE,
)
_ID12 = re.compile(r"(?<![\d.,])\d{12}(?![\d])")
_LONG = re.compile(r"(?<![\d.,])\d{10,19}(?![\d])")


@dataclass
class MaskResult:
    text: str
    counts: Counter[str] = field(default_factory=Counter)

    @property
    def changed(self) -> bool:
        return bool(self.counts)


def _sub(pattern: re.Pattern[str], text: str, kind: str, counts: Counter[str]) -> str:
    def repl(_: re.Match[str]) -> str:
        counts[kind] += 1
        return PLACEHOLDERS[kind]

    return pattern.sub(repl, text)


def _sub_keyword(
    pattern: re.Pattern[str], text: str, kind_of: Callable[[str], str], counts: Counter[str]
) -> str:
    """Che chỉ phần số, giữ nguyên từ khóa để câu vẫn đọc được."""

    def repl(m: re.Match[str]) -> str:
        kind = kind_of(m.group("num"))
        counts[kind] += 1
        start = m.start("num") - m.start()
        return m.group(0)[:start] + PLACEHOLDERS[kind]

    return pattern.sub(repl, text)


def mask_pii(text: str) -> MaskResult:
    """Che PII trong `text`. Trả văn bản đã che và số lần che theo loại."""
    counts: Counter[str] = Counter()
    out = _sub(_EMAIL, text, "email", counts)
    out = _sub(_CARD, out, "card", counts)
    out = _sub(_PHONE, out, "phone", counts)
    out = _sub_keyword(_KEYWORD_ID, out, lambda _n: "national_id", counts)
    out = _sub_keyword(_KEYWORD_ACCOUNT, out, lambda _n: "account", counts)
    out = _sub(_ID12, out, "national_id", counts)  # đúng 12 chữ số liền: CCCD
    out = _sub(_LONG, out, "account", counts)  # từ 10 chữ số liền không phân tách: số tài khoản
    return MaskResult(out, counts)


def mask_text(text: str) -> str:
    """Rút gọn của `mask_pii` khi chỉ cần chuỗi."""
    return mask_pii(text).text


__all__ = ["PLACEHOLDERS", "MaskResult", "mask_pii", "mask_text"]
