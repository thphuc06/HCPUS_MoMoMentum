"""Xử lý chuỗi tiếng Việt dùng chung: bỏ dấu, đọc số tiền, tách số tiền để kiểm căn cứ.

Đây là mã ngôn ngữ chung chung (không chứa câu hỏi hay số của persona).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from decimal import Decimal

from yofina_agent.notices import STRESS_CHIP_VALUE
from yofina_core.resilience import load_shock_set

_UNITS: dict[str, int] = {
    "k": 1_000,
    "nghin": 1_000,
    "ngan": 1_000,
    "tr": 1_000_000,
    "trieu": 1_000_000,
    "ty": 1_000_000_000,
    "ti": 1_000_000_000,
    "d": 1,
    "dong": 1,
    "vnd": 1,
    "₫": 1,
}
_UNIT_RE = "|".join(sorted(map(re.escape, _UNITS), key=len, reverse=True))
# số (có thể có nhóm nghìn hoặc phần thập phân) + đơn vị tùy chọn; "1tr5" và "1 triệu rưỡi" xử lý riêng
_AMOUNT_RE = re.compile(
    rf"(?<![\d/\-.,])(?P<num>\d{{1,3}}(?:[.,]\d{{3}})+|\d+(?:[.,]\d+)?)(?![\d/\-]\d)"
    rf"\s*(?P<unit>{_UNIT_RE})?(?![a-z])"
)
_GLUED_RE = re.compile(
    r"(?<![\d.,])(?P<a>\d+)\s*(?P<unit>tr|trieu|k|nghin|ty)\s*(?P<b>\d+)(?!\d*[a-z])"
)
_HALF_RE = re.compile(r"(?<![\d.,])(?P<a>\d+)\s*(?P<unit>trieu|tr|nghin|ty)\s*ruoi")


def strip_accents(text: str) -> str:
    """Hạ chữ thường, bỏ dấu, `đ` -> `d` (giữ ký hiệu `₫`)."""
    text = text.replace("đ", "d").replace("Đ", "d")
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower()


def normalize(text: str) -> str:
    """Bỏ dấu, hạ chữ thường, gộp mọi ký tự không phải chữ/số/₫ thành một khoảng trắng."""
    return re.sub(r"[^a-z0-9₫]+", " ", strip_accents(text)).strip()


_GROUPED_RE = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")


def _to_decimal(num: str, *, has_unit: bool) -> tuple[Decimal, int] | None:
    """(giá trị, số chữ số thập phân). Nhóm nghìn kiểu 1.200.000 -> số nguyên."""
    if _GROUPED_RE.match(num):
        return Decimal(re.sub(r"[.,]", "", num)), 0
    if re.search(r"[.,]", num):
        if not has_unit:
            return None  # "1,5" không đơn vị: không phải số tiền
        whole, frac = re.split(r"[.,]", num)
        return Decimal(f"{whole}.{frac}"), len(frac)
    return Decimal(num), 0


def extract_amounts(text: str) -> list[tuple[int, float]]:
    """Mọi số tiền trong `text`, theo thứ tự xuất hiện, dạng (giá trị VND, sai số do làm tròn).

    Sai số: số có đơn vị làm tròn tới nhiều nhất một chữ số thập phân của đơn vị
    (`format_vnd_short`), số đầy đủ chính xác tới 0,5 đồng. Bỏ qua số không đơn vị nhỏ hơn 1.000
    (số đếm, phần trăm, ngày), số trong ngày tháng và năm.
    """
    t = strip_accents(text)
    found: list[tuple[int, int, float]] = []  # (vị trí, giá trị, sai số)
    consumed: list[tuple[int, int]] = []

    def taken(pos: int) -> bool:
        return any(s <= pos < e for s, e in consumed)

    for m in _HALF_RE.finditer(t):
        mult = _UNITS[m["unit"]]
        found.append((m.start(), int(Decimal(m["a"]) * mult + mult // 2), 0.05 * mult))
        consumed.append(m.span())
    for m in _GLUED_RE.finditer(t):
        if taken(m.start()):
            continue
        mult = _UNITS[m["unit"]]
        value = (Decimal(m["a"]) + Decimal(f"0.{m['b']}")) * mult
        found.append((m.start(), int(value), 0.5 * mult / 10 ** max(len(m["b"]), 1)))
        consumed.append(m.span())
    for m in _AMOUNT_RE.finditer(t):
        if taken(m.start()):
            continue
        unit = m["unit"]
        parsed = _to_decimal(m["num"], has_unit=bool(unit))
        if parsed is None:
            continue
        value, decimals = parsed
        if unit is None:
            if value < 1000 or 1900 <= value <= 2100:
                continue
            found.append((m.start(), int(value), 0.5))
            continue
        mult = _UNITS[unit]
        tol = 0.5 if mult == 1 else 0.5 * mult / 10 ** max(decimals, 1)
        found.append((m.start(), int(value * mult), tol))
    found.sort()
    return [(value, tol) for _, value, tol in found]


def parse_amount_vnd(text: str) -> int | None:
    """Số tiền đầu tiên trong câu (VND, nguyên) hoặc None.

    >>> parse_amount_vnd("chuyển 100 nghìn")
    100000
    >>> parse_amount_vnd("1tr5")
    1500000
    """
    amounts = extract_amounts(text)
    return amounts[0][0] if amounts else None


def match_shock_id(text: str) -> str | None:
    """Khớp value chip hoặc nguyên nhãn cú sốc. Khoản tiền do người dùng nhập dành cho what-if."""
    norm = normalize(text)
    shocks = load_shock_set().shocks
    for shock in shocks:
        if norm == normalize(STRESS_CHIP_VALUE.format(label=shock.label)):
            return shock.shock_id
    matches = [shock for shock in shocks if f" {normalize(shock.label)} " in f" {norm} "]
    if len(matches) == 1 and parse_amount_vnd(text) is None:
        return matches[0].shock_id
    return None


def ungrounded_amounts(text: str, allowed: Iterable[int]) -> list[int]:
    """Các số tiền trong `text` không khớp (trong sai số làm tròn) với số nào trong `allowed`."""
    allowed = list(allowed)
    return [
        value
        for value, tol in extract_amounts(text)
        if not any(abs(value - a) <= max(tol, 0.5) for a in allowed)
    ]
