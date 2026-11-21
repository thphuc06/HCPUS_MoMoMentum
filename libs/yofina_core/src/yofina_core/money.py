"""Số tiền VND: chuyển về số nguyên và định dạng hiển thị.

Quy ước toàn dự án (xem contracts/README.md): tiền luôn là **số nguyên VND**. Trong Python dùng
`int` hoặc `Decimal`; không dùng `float` (bị từ chối để khỏi làm tròn ngầm). Aurora trả
`numeric` dưới dạng chuỗi, nên `to_vnd` cũng nhận `str`.

Hai kiểu hiển thị theo thiết kế Figma:
- `format_vnd`: "1.200.000 ₫" (thẻ, biên nhận).
- `format_vnd_short`: "1,2 triệu" (câu hỏi, lời giải thích).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CURRENCY_SYMBOL = "₫"

_ONE_DECIMAL = Decimal("0.1")
_UNITS: tuple[tuple[int, str], ...] = ((10**3, "nghìn"), (10**6, "triệu"), (10**9, "tỷ"))


def to_vnd(value: int | Decimal | str) -> int:
    """Đổi về số nguyên VND; ném lỗi nếu có phần lẻ hoặc kiểu không hợp lệ.

    >>> to_vnd(Decimal("1200000"))
    1200000
    """
    if isinstance(value, (bool, float)):
        raise TypeError(
            f"Số tiền VND không nhận {type(value).__name__}; dùng int, Decimal hoặc str"
        )
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            value = Decimal(value.strip())
        except InvalidOperation as exc:
            raise ValueError(f"Chuỗi không phải số tiền: {value!r}") from exc
    if isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise ValueError(f"Số tiền VND phải là số nguyên, nhận {value}")
        return int(value)
    raise TypeError(f"Số tiền VND không nhận {type(value).__name__}")


def _group_thousands(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def format_vnd(value: int | Decimal | str) -> str:
    """'1.200.000 ₫'. Số âm có dấu '-' đứng trước."""
    n = to_vnd(value)
    sign = "-" if n < 0 else ""
    return f"{sign}{_group_thousands(abs(n))} {CURRENCY_SYMBOL}"


def format_vnd_short(value: int | Decimal | str) -> str:
    """'1,2 triệu', '250 nghìn', '2 tỷ'; dưới 1.000 thì '500 ₫'.

    Làm tròn nửa lên đến một chữ số thập phân; dùng dấu phẩy thập phân kiểu Việt Nam.
    Nếu làm tròn chạm 1.000 đơn vị thì nhảy lên đơn vị lớn hơn (999.999 -> '1 triệu').
    """
    n = to_vnd(value)
    sign = "-" if n < 0 else ""
    a = abs(n)
    if a < 1000:
        return f"{sign}{a} {CURRENCY_SYMBOL}"
    for i, (unit, name) in enumerate(_UNITS):
        q = (Decimal(a) / unit).quantize(_ONE_DECIMAL, rounding=ROUND_HALF_UP)
        if q < 1000 or i == len(_UNITS) - 1:
            whole, frac = divmod(q, 1)
            text = _group_thousands(int(whole))
            if frac:
                text += "," + str(int(frac * 10))
            return f"{sign}{text} {name}"
    raise AssertionError("không tới được")  # pragma: no cover
