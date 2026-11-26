"""Xử lý chuỗi tiếng Việt dùng chung: bỏ dấu, đọc số tiền, tách số tiền để kiểm căn cứ, đọc hạn mục tiêu (đường lùi), dữ kiện của một
ngày đã tính từ đặc tả.

Đây là mã ngôn ngữ chung chung (không chứa câu hỏi hay số của persona).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from yofina_agent.notices import STRESS_CHIP_VALUE
from yofina_core.clock import payday_in_month
from yofina_core.dates import ResolvedDate
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


#: Số nhỏ nhất được coi là tiền khi đơn vị gõ KHÔNG DẤU ("dong", "d"): cùng ngưỡng với số không đơn vị.
PLAIN_DONG_MIN_VND = 1_000


def _is_dong_unit(typed: str, value: Decimal) -> bool:
    """Đơn vị "d"/"dong" (sau khi bỏ dấu) có thật là "đồng" không, xét chữ người dùng gõ `typed`.

    Bỏ dấu thì "dòng" (5 dòng chờ duyệt) trùng "đồng", nên:
    - có chữ "đ" ("đồng", "đ", "Đ"): là tiền;
    - có dấu nhưng không có "đ" ("dòng", "dông"): không phải tiền;
    - không dấu ("dong", "d"): là tiền chỉ khi giá trị từ 1.000 đồng, mức tiền nhỏ nhất còn tiêu được. "5 dong" có thể là "5 dòng"
      gõ không dấu, còn "50000 dong" thì không thể là số dòng nào hợp lý.
    """
    if "đ" in typed.lower():
        return True
    if not typed.isascii():
        return False
    return value >= PLAIN_DONG_MIN_VND


def extract_amounts(text: str) -> list[tuple[int, float]]:
    """Mọi số tiền trong `text`, theo thứ tự xuất hiện, dạng (giá trị VND, sai số do làm tròn).

    Sai số: số có đơn vị làm tròn tới nhiều nhất một chữ số thập phân của đơn vị
    (`format_vnd_short`), số đầy đủ chính xác tới 0,5 đồng. Bỏ qua số không đơn vị nhỏ hơn 1.000
    (số đếm, phần trăm, ngày), số trong ngày tháng và năm. Đơn vị "đồng"/"đ" phải có chữ "đ", hoặc gõ không dấu
    với giá trị từ 1.000 (`_is_dong_unit`): "5 dòng" không phải 5 ₫.
    """
    t, pos = _mapped(text, collapse=False)
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
        if unit in ("d", "dong"):
            plain = _to_decimal(m["num"], has_unit=True)
            typed = text[pos[m.start("unit")] : pos[m.end("unit") - 1] + 1]
            if plain is None or not _is_dong_unit(typed, plain[0]):
                unit = None  # "dòng", "5 dong": đọc như số không đơn vị (số nhỏ bị bỏ)
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


# --- hạn mục tiêu người dùng nói ("cuối tháng này", "31/12", "6 tháng nữa") ---------------------------------
_ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")
#: dd/mm[/yyyy]; không nhận số theo sau là đơn vị tiền ("1.5 triệu" là số tiền, không phải 1/5)
_DMY_RE = re.compile(
    rf"(?<![\d/.\-])(\d{{1,2}})[/.\-](\d{{1,2}})(?:[/.\-](\d{{4}}|\d{{2}}))?(?![\d/.\-])"
    rf"(?!\s*(?:{_UNIT_RE})(?![a-z]))"
)
_YEAR = r"(?: nam (\d{4}|nay|sau|toi))?"
_DAY_MONTH_RE = re.compile(rf"\bngay (\d{{1,2}}) thang (\d{{1,2}}){_YEAR}\b")
_OFFSET_RE = re.compile(r"(?<!thang )(?<!ngay )\b(\d{1,3}) (ngay|tuan|thang|nam) (?:nua|toi|sau)\b")
#: hạn là một khoảng thời gian tính từ hôm nay: "trong 3 tháng", "trong vòng 2 tuần" (cùng nghĩa với "3 tháng nữa")
_WITHIN_RE = re.compile(r"\btrong(?: vong)? (\d{1,3}) (ngay|tuan|thang|nam)\b")
#: cả cụm hạn (router chép riêng cụm chỉ thời gian vào date_text) chỉ là một khoảng thời gian: "3 tháng". Chỉ khớp TRỌN cụm, nên
#: khoảng thời gian giữa câu ("để dành 3 tháng lương") không thành hạn.
_DURATION_RE = re.compile(r"(\d{1,3}) (ngay|tuan|thang|nam)")
_END_OF_MONTH_N_RE = re.compile(rf"\b(?:cuoi|het) thang (\d{{1,2}}){_YEAR}\b")
_MONTH_N_RE = re.compile(rf"\bthang (\d{{1,2}}){_YEAR}\b")
_NEXT_MONTH_RE = re.compile(r"\b(?:cuoi|het) thang (?:sau|toi)\b|\bthang (?:sau|toi)\b")
_END_OF_MONTH_RE = re.compile(r"\b(?:cuoi|het) thang(?: nay)?\b")
_NEXT_YEAR_RE = re.compile(r"\b(?:cuoi|het) nam (?:sau|toi)\b|\bnam (?:sau|toi)\b")
_END_OF_YEAR_RE = re.compile(r"\b(?:cuoi|het) nam(?: nay)?\b")
_ALNUM = re.compile(r"[a-z0-9₫]")


def _mapped(text: str, *, collapse: bool) -> tuple[str, list[int]]:
    """`strip_accents(text)` (collapse=False) hoặc `normalize(text)` (collapse=True), kèm vị trí trong `text` của từng ký tự.

    Để cắt lại đúng cụm chữ người dùng gõ (còn dấu) từ chỗ khớp trên chuỗi đã bỏ dấu.
    """
    out: list[str] = []
    pos: list[int] = []
    gap = False
    for i, ch in enumerate(text):
        for c in strip_accents(ch):
            if not collapse:
                out.append(c)
                pos.append(i)
            elif _ALNUM.match(c):
                if gap and out:
                    out.append(" ")
                    pos.append(i)
                gap = False
                out.append(c)
                pos.append(i)
            else:
                gap = True
    return "".join(out), pos


def _add_months(day: date, months: int) -> date:
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    return payday_in_month(day.day, year, month + 1)


def _month_end(year: int, month: int) -> date:
    return payday_in_month(31, year, month)


def _year_of(token: str | None, today: date) -> int | None:
    if token is None:
        return None
    if token == "nay":
        return today.year
    if token in ("sau", "toi"):
        return today.year + 1
    return int(token) + (2000 if len(token) == 2 else 0)


def _on_or_next_year(today: date, make: Callable[[int], date], year: int | None) -> date:
    """Ngày trong năm `year`; không nói năm mà ngày đó đã qua (hoặc là hôm nay) thì lấy năm sau."""
    found = make(year if year is not None else today.year)
    return make(today.year + 1) if year is None and found <= today else found


def _goal_date_match(text: str) -> tuple[Callable[[date], date], tuple[int, int]] | None:
    """Cách nói hạn đầu tiên nhận ra: (hàm đổi ra ngày theo hôm nay, vị trí [đầu, cuối) của cụm trong `text`). None nếu không có.

    Hàm đổi ngày ném `ValueError` với ngày không có thật (31/02, tháng 13).
    """
    raw, raw_pos = _mapped(text, collapse=False)
    words, word_pos = _mapped(text, collapse=True)

    def span(pos: list[int], m: re.Match[str]) -> tuple[int, int]:
        return pos[m.start()], pos[m.end() - 1] + 1

    if m := _ISO_DATE_RE.search(raw):
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        return (lambda _today: date(y, mo, d)), span(raw_pos, m)
    m, pos = _DMY_RE.search(raw), raw_pos
    if m is None:
        m, pos = _DAY_MONTH_RE.search(words), word_pos
    if m is not None:
        d, mo, year_token = int(m[1]), int(m[2]), m[3]
        return (
            lambda today: _on_or_next_year(today, lambda y: date(y, mo, d), _year_of(year_token, today))
        ), span(pos, m)
    if m := _OFFSET_RE.search(words) or _WITHIN_RE.search(words) or _DURATION_RE.fullmatch(words):
        n, unit = int(m[1]), m[2]
        if unit in ("ngay", "tuan"):
            days = n * (7 if unit == "tuan" else 1)
            return (lambda today: today + timedelta(days=days)), span(word_pos, m)
        months = n * (12 if unit == "nam" else 1)
        return (lambda today: _add_months(today, months)), span(word_pos, m)
    if m := _END_OF_MONTH_N_RE.search(words) or _MONTH_N_RE.search(words):
        mo, year_token = int(m[1]), m[2]
        return (
            lambda today: _on_or_next_year(today, lambda y: _month_end(y, mo), _year_of(year_token, today))
        ), span(word_pos, m)

    def next_month_end(today: date) -> date:
        year, month = divmod(today.year * 12 + today.month, 12)  # tháng kế tiếp (0-based)
        return _month_end(year, month + 1)

    keyword_rules: tuple[tuple[re.Pattern[str], Callable[[date], date]], ...] = (
        (_NEXT_MONTH_RE, next_month_end),
        (_END_OF_MONTH_RE, lambda today: _month_end(today.year, today.month)),
        (_NEXT_YEAR_RE, lambda today: date(today.year + 1, 12, 31)),
        (_END_OF_YEAR_RE, lambda today: date(today.year, 12, 31)),
    )
    for pattern, resolve in keyword_rules:
        if m := pattern.search(words):
            return resolve, span(word_pos, m)
    return None


def parse_goal_date(text: str, today: date, *, whole: bool = False) -> date | None:
    """Hạn mục tiêu người dùng nói ("cuối tháng này", "31/12", "6 tháng nữa", "trong 3 tháng", "tháng 3 năm sau") -> ngày, tính theo ngày
    mô phỏng `today`.

    Chỉ nhận cách nói rõ ràng; không đọc được hoặc ngày không sau hôm nay thì None (người gọi nói rõ, không đoán). `whole=True`: chỉ nhận
    khi luật đọc được TRỌN cụm (mọi chữ của `text` nằm trong phần khớp), để cụm có chữ luật không hiểu ("đầu năm sau", "ngày 15 tháng
    sau") không bị đọc thành một ngày khác. Với hạn mục tiêu, đây chỉ là đường lùi khi router không trả đặc tả hạn (`date_spec`, tính
    bằng `yofina_core.dates.resolve_date`), và là ngày ứng viên cho chip khi đặc tả không tính được (V1, #39).

    >>> parse_goal_date("cuối tháng sau", date(2026, 11, 21))
    datetime.date(2026, 12, 31)
    >>> parse_goal_date("đầu năm sau", date(2026, 11, 21), whole=True) is None
    True
    """
    found = _goal_date_match(text)
    if found is None:
        return None
    resolve, (start, end) = found
    if whole and normalize(text[:start] + " " + text[end:]):
        return None
    try:
        when = resolve(today)
    except ValueError:  # 31/02, tháng 13...
        return None
    return when if when > today else None


def goal_date_phrase(text: str) -> str | None:
    """Cụm chữ chỉ hạn trong câu, giữ nguyên chữ người dùng gõ ("Lập lộ trình ... trước cuối tháng này" -> "cuối tháng này").

    Cùng luật với `parse_goal_date` nên `parse_goal_date(goal_date_phrase(câu), hôm_nay)` cho cùng ngày với cả câu. Chưa đổi ra ngày
    (cần ngày mô phỏng); None nếu câu không có cách nói hạn nào nhận ra được.
    """
    found = _goal_date_match(text)
    if found is None:
        return None
    start, end = found[1]
    return text[start:end].strip() or None


# --- ngày đã tính từ đặc tả (`yofina_core.dates.resolve_date`), làm dữ kiện cho model viết câu trả lời ------------------------------------
_WEEKDAYS = ("thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật")


def _dmy(day: date) -> str:
    return f"{day.day:02d}/{day.month:02d}/{day.year}"


def resolved_date_facts(resolved: ResolvedDate) -> dict[str, Any]:
    """Dữ kiện có cấu trúc của một ngày tính từ đặc tả, cho người viết câu trả lời (writer, Analyst): ngày (dd/mm/yyyy và dd/mm, thứ, số
    ngày tới đó) và các trường giải thích của phép tính (mốc đã dùng và ngày của mốc, trước mốc hay không, kỳ, năm Tết và tên năm, ngày
    lương, độ lệch đã quy đổi, lần gần nhất sau hôm nay, đã về cuối tháng), để câu trả lời nói được hạn theo cách người dùng nói kèm
    đúng ngày. Ngày ở dạng chữ có sẵn để bước kiểm số của người viết tìm thấy; không có câu viết sẵn."""
    out: dict[str, Any] = {
        "date_text": _dmy(resolved.date),
        "day_month_text": f"{resolved.date.day:02d}/{resolved.date.month:02d}",
        "weekday_text": _WEEKDAYS[resolved.weekday - 1],
        "days_from_today": resolved.days_from_today,
        "anchor": resolved.anchor,
        "anchor_date_text": _dmy(resolved.anchor_date),
        "before_anchor": resolved.before,
    }
    if resolved.period is not None:
        out["period"] = resolved.period
        out["period_offset"] = resolved.period_offset or 0
    if (tet := resolved.lunar_new_year) is not None:
        out["lunar_new_year"] = {"name": tet.name, "date_text": _dmy(tet.date), "year": tet.year}
    if resolved.payday_day is not None:
        out["payday_day"] = resolved.payday_day
    if resolved.offset is not None:
        out["offset"] = {"months": resolved.offset.months, "days": resolved.offset.days}
    if resolved.next_occurrence:
        out["next_occurrence"] = True
    if resolved.month_end_clamped:
        out["month_end_clamped"] = True
    return out
