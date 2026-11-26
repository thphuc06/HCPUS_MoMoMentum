"""Tính một ngày dương lịch từ đặc tả có cấu trúc (issue #39).

Model hiểu cách người dùng nói về thời gian và điền `DateSpec`; phép tính lịch (độ dài tháng, năm nhuận, tuần, quý, Tết âm lịch)
do hàm tất định ở đây làm. Dùng chung cho tool Gateway `knowledge___resolve_date` (Lambda ledger) và cho mã của agent trong tiến
trình. Hàm thuần: không đọc đồng hồ hệ thống; `today` là ngày mô phỏng của người dùng (`clock.app_today`, ADR-0003) do người gọi
truyền vào, ngày lương cũng vậy.

Thứ tự tính: mốc (`anchor`) -> cộng độ lệch (`offset`: phần tháng trước, phần ngày sau) -> `before` (lùi một ngày) -> kiểm không
trước hôm nay.

- Cộng tháng giữ ngày trong tháng; ngày vượt số ngày của tháng đích thì lấy ngày cuối tháng (31/01 + 1 tháng = 28/02 hoặc 29/02).
- Phần lẻ của độ lệch quy đổi cố định: một năm là 12 tháng; phần lẻ của tổng số tháng tính 30 ngày mỗi tháng; một tuần là 7 ngày;
  tổng số ngày làm tròn tới ngày, nửa ngày làm tròn ra xa 0 (1,5 năm = 18 tháng; 1,5 tháng = 1 tháng 15 ngày).
- Tuần từ thứ Hai tới Chủ nhật; quý là ba tháng bắt đầu từ tháng 1, 4, 7, 10. `period_offset` đếm kỳ từ kỳ chứa hôm nay.
- Ngày cụ thể thiếu năm (hoặc thiếu tháng), Tết không nêu năm: lấy lần gần nhất SAU hôm nay (hôm nay không tính).
- Mùng 1 Tết là dữ liệu tra (`lunar_new_year.json`, có nguồn), không tính lịch âm bằng mã; năm ngoài bảng là `LUNAR_YEAR_UNSUPPORTED`.
- Đặc tả sai là `PARAMS_INVALID` kèm `field`; mốc ngày lương khi chưa khai ngày lương là `PROFILE_INCOMPLETE`; kết quả trước hôm
  nay là `DATE_IN_PAST` (không tự dời, bên gọi hỏi lại người dùng; lỗi mang `resolved_date`).
"""

from __future__ import annotations

import calendar
import datetime as dt
import json
import math
import re
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from functools import cache
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict

from yofina_core.clock import next_payday
from yofina_core.errors import ErrorCode, YofinaError

Anchor = Literal["today", "next_payday", "start_of", "end_of", "lunar_new_year", "date"]
Period = Literal["week", "month", "quarter", "year"]
ANCHORS: tuple[str, ...] = get_args(Anchor)
PERIODS: tuple[str, ...] = get_args(Period)
#: trường của đặc tả, đúng thứ tự của `DateSpec` (cũng là tham số của tool `knowledge___resolve_date`, trừ `user_id`)
SPEC_FIELDS = (
    "anchor",
    "period",
    "period_offset",
    "lunar_year",
    "day",
    "month",
    "year",
    "offset",
    "before",
)
OFFSET_UNITS = ("years", "months", "weeks", "days")
#: trần trị tuyệt đối của từng thành phần độ lệch (khoảng 100 năm)
MAX_OFFSET = {"years": 100, "months": 1200, "weeks": 5300, "days": 36600}
#: số chữ số lẻ tối đa của độ lệch (Cedar của AgentCore Policy giữ số `number` ở 4 chữ số lẻ)
MAX_OFFSET_DECIMALS = 4
MAX_PERIOD_OFFSET = 1200
MIN_YEAR, MAX_YEAR = 1900, 2200
#: phần lẻ của tổng số tháng đổi ra ngày theo số này
DAYS_PER_FRACTIONAL_MONTH = 30
LUNAR_FILE = "lunar_new_year.json"
LUNAR_TIMEZONE = "UTC+7"

#: trường riêng của từng mốc (ngoài `offset`, `before` dùng chung); trường khác đi kèm mốc là PARAMS_INVALID
_ANCHOR_FIELDS: dict[str, frozenset[str]] = {
    "today": frozenset(),
    "next_payday": frozenset(),
    "start_of": frozenset({"period", "period_offset"}),
    "end_of": frozenset({"period", "period_offset"}),
    "lunar_new_year": frozenset({"lunar_year", "period", "period_offset"}),
    "date": frozenset({"day", "month", "year", "period", "period_offset"}),
}
_MAX_DAY_OF_MONTH = {
    m: calendar.monthrange(2000, m)[1] for m in range(1, 13)
}  # 2000 là năm nhuận: tháng 2 có 29
_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DateOffset(_Model):
    """Độ lệch cộng vào mốc; mỗi thành phần có thể âm hoặc có phần lẻ (tối đa 4 chữ số lẻ)."""

    years: Decimal | None = None
    months: Decimal | None = None
    weeks: Decimal | None = None
    days: Decimal | None = None


class DateSpec(_Model):
    """Đặc tả ngày có cấu trúc. Dựng bằng `parse_spec` (kiểm đủ luật); dựng thẳng thì `resolve_date` vẫn kiểm lại."""

    anchor: Anchor
    period: Period | None = None
    period_offset: int | None = None
    lunar_year: int | None = None
    day: int | None = None
    month: int | None = None
    year: int | None = None
    offset: DateOffset | None = None
    before: bool = False


class LunarNewYear(_Model):
    """Mùng 1 Tết của một năm: `year` là năm dương lịch chứa ngày đó, `name` là tên can chi của năm âm lịch bắt đầu từ đó."""

    year: int
    date: dt.date
    name: str


class NormalizedOffset(_Model):
    """Độ lệch đã quy đổi và đã cộng: số tháng (cộng trước) và số ngày (cộng sau), có dấu."""

    months: int
    days: int


class ResolvedDate(_Model):
    """Ngày tính được và các trường giải thích (`ResolvedDateData` của `contracts/tools/knowledge.results.schema.json`)."""

    date: dt.date
    today: dt.date
    #: thứ trong tuần theo ISO: 1 thứ Hai ... 7 Chủ nhật
    weekday: int
    days_from_today: int
    anchor: Anchor
    #: ngày của mốc, trước khi cộng độ lệch và trước `before`
    anchor_date: dt.date
    period: Period | None = None
    period_offset: int | None = None
    payday_day: int | None = None
    lunar_new_year: LunarNewYear | None = None
    #: True khi mốc là lần gần nhất sau hôm nay vì đặc tả không nêu năm (hoặc tháng, hoặc năm Tết)
    next_occurrence: bool | None = None
    offset: NormalizedOffset | None = None
    #: True khi một ngày trong tháng vượt số ngày của tháng nên đã lấy ngày cuối tháng
    month_end_clamped: bool | None = None
    before: bool

    def to_wire(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class DateResolveError(YofinaError):
    """Lỗi có mã của phép tính ngày. `resolved_date`: ngày đã tính khi lỗi là DATE_IN_PAST (để bên gọi hỏi lại cho đúng)."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        field: str | None = None,
        resolved_date: dt.date | None = None,
    ) -> None:
        super().__init__(code, message, field=field)
        self.resolved_date = resolved_date


def _invalid(field: str | None, message: str) -> DateResolveError:
    return DateResolveError(
        ErrorCode.PARAMS_INVALID,
        message,
        field=field if field and _FIELD_RE.fullmatch(field) else None,
    )


# --- bảng Tết ------------------------------------------------------------------------------------------------
def parse_lunar_table(obj: Mapping[str, Any]) -> dict[int, LunarNewYear]:
    """Kiểm bảng Mùng 1 Tết đã nạp từ JSON: giờ Việt Nam, có nguồn, năm liên tục tăng dần, ngày rơi trong 21/01..20/02 của
    chính năm đó, có tên năm. Sai thì `ValueError`."""
    if obj.get("timezone") != LUNAR_TIMEZONE:
        raise ValueError(f"bảng Tết phải tính theo {LUNAR_TIMEZONE}")
    sources = obj.get("sources") or []
    if not sources or not all(
        isinstance(s, Mapping) and s.get("name") and str(s.get("url", "")).startswith("https://")
        for s in sources
    ):
        raise ValueError("bảng Tết phải ghi nguồn (tên và đường dẫn https)")
    rows = [LunarNewYear.model_validate(r) for r in obj.get("years") or []]
    if not rows:
        raise ValueError("bảng Tết rỗng")
    table: dict[int, LunarNewYear] = {}
    for i, r in enumerate(rows):
        if r.year != rows[0].year + i:
            raise ValueError(f"năm {r.year}: bảng Tết phải liên tục, tăng dần")
        if r.date.year != r.year or not dt.date(r.year, 1, 21) <= r.date <= dt.date(r.year, 2, 20):
            raise ValueError(f"năm {r.year}: Mùng 1 Tết phải trong 21/01..20/02 của năm đó")
        if not r.name.strip():
            raise ValueError(f"năm {r.year}: thiếu tên năm")
        table[r.year] = r
    return table


@cache
def lunar_new_years() -> Mapping[int, LunarNewYear]:
    """Bảng Mùng 1 Tết đóng gói cùng module (`lunar_new_year.json`), theo năm."""
    raw = json.loads(Path(__file__).with_name(LUNAR_FILE).read_text(encoding="utf-8"))
    return parse_lunar_table(raw)


def _range_text() -> str:
    years = list(lunar_new_years())
    return f"{years[0]}–{years[-1]}"


def lunar_new_year(year: int) -> LunarNewYear:
    """Mùng 1 Tết của năm dương lịch `year`; năm ngoài bảng là LUNAR_YEAR_UNSUPPORTED."""
    found = lunar_new_years().get(year)
    if found is None:
        raise DateResolveError(
            ErrorCode.LUNAR_YEAR_UNSUPPORTED,
            f"Chưa tra được ngày Tết năm {year}: lịch Tết của Yofina chỉ có các năm {_range_text()}.",
            field="lunar_year",
        )
    return found


def next_lunar_new_year(today: dt.date) -> LunarNewYear:
    """Mùng 1 Tết gần nhất SAU `today`; hết bảng là LUNAR_YEAR_UNSUPPORTED."""
    for tet in lunar_new_years().values():
        if tet.date > today:
            return tet
    raise DateResolveError(
        ErrorCode.LUNAR_YEAR_UNSUPPORTED,
        f"Chưa tra được ngày Tết sắp tới: lịch Tết của Yofina chỉ có các năm {_range_text()}.",
        field="lunar_year",
    )


# --- đọc đặc tả ----------------------------------------------------------------------------------------------
def _int(values: Mapping[str, Any], name: str, lo: int, hi: int) -> int | None:
    v = values.get(name)
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise _invalid(name, f"{name} phải là số nguyên từ {lo} tới {hi}.")
    return v


def _offset_part(unit: str, v: Any) -> Decimal | None:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float, Decimal)):
        raise _invalid("offset", f"offset.{unit} phải là số.")
    if isinstance(v, float) and not math.isfinite(v):
        raise _invalid("offset", f"offset.{unit} phải là số hữu hạn.")
    value = Decimal(str(v)) if isinstance(v, float) else Decimal(v)
    if not value.is_finite():
        raise _invalid("offset", f"offset.{unit} phải là số hữu hạn.")
    value = value.normalize()
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -MAX_OFFSET_DECIMALS:
        raise _invalid("offset", f"offset.{unit} có tối đa {MAX_OFFSET_DECIMALS} chữ số lẻ.")
    if abs(value) > MAX_OFFSET[unit]:
        raise _invalid("offset", f"offset.{unit} chỉ trong khoảng ±{MAX_OFFSET[unit]}.")
    return value if value != 0 else None


def _offset(raw: Any) -> DateOffset | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise _invalid("offset", "offset phải là đối tượng có years, months, weeks, days.")
    unknown = sorted(str(k) for k in raw if k not in OFFSET_UNITS)
    if unknown:
        raise _invalid(
            "offset",
            f"offset không có thành phần {unknown[0][:40]}; chỉ có years, months, weeks, days.",
        )
    parts = {u: _offset_part(u, raw.get(u)) for u in OFFSET_UNITS}
    return DateOffset(**parts) if any(v is not None for v in parts.values()) else None


def parse_spec(raw: Mapping[str, Any]) -> DateSpec:
    """Đặc tả (JSON của tool hoặc của router) -> `DateSpec`, kiểm kiểu và luật kết hợp trường. Giá trị null coi như vắng.
    Sai thì DateResolveError(PARAMS_INVALID) với `field` là trường sai và câu tiếng Việt nói cách sửa."""
    if not isinstance(raw, Mapping):
        raise _invalid(None, "Đặc tả ngày phải là một đối tượng.")
    values = {str(k): v for k, v in raw.items() if v is not None}
    unknown = sorted(k for k in values if k not in SPEC_FIELDS)
    if unknown:
        raise _invalid(unknown[0], f"Đặc tả ngày không có trường {unknown[0][:40]}.")
    anchor = values.get("anchor")
    if not isinstance(anchor, str) or anchor not in ANCHORS:
        raise _invalid("anchor", f"anchor phải là một trong: {', '.join(ANCHORS)}.")
    period = values.get("period")
    if period is not None and (not isinstance(period, str) or period not in PERIODS):
        raise _invalid("period", f"period phải là một trong: {', '.join(PERIODS)}.")
    period_offset = _int(values, "period_offset", -MAX_PERIOD_OFFSET, MAX_PERIOD_OFFSET)
    lunar_year = _int(values, "lunar_year", 1, 9999)
    day = _int(values, "day", 1, 31)
    month = _int(values, "month", 1, 12)
    year = _int(values, "year", MIN_YEAR, MAX_YEAR)
    before = values.get("before", False)
    if not isinstance(before, bool):
        raise _invalid("before", "before phải là true hoặc false.")
    offset = _offset(values.get("offset"))

    for name in ("period", "period_offset", "lunar_year", "day", "month", "year"):
        if name in values and name not in _ANCHOR_FIELDS[anchor]:
            raise _invalid(name, f"{name} không dùng với anchor {anchor}.")
    if period_offset is not None and period is None:
        raise _invalid("period_offset", "period_offset chỉ dùng kèm period.")
    if anchor in ("start_of", "end_of") and period is None:
        raise _invalid("period", f"anchor {anchor} cần period ({', '.join(PERIODS)}).")
    if anchor == "lunar_new_year":
        if period not in (None, "year"):
            raise _invalid("period", "Với anchor lunar_new_year, period chỉ là year.")
        if lunar_year is not None and period is not None:
            raise _invalid("lunar_year", "Nêu lunar_year hoặc period year, không nêu cả hai.")
    if anchor == "date":
        if day is None:
            raise _invalid("day", "anchor date cần day (ngày trong tháng).")
        if period not in (None, "month", "year"):
            raise _invalid("period", "Với anchor date, period chỉ là month hoặc year.")
        if period == "month" and month is not None:
            raise _invalid("month", "period month đã chọn tháng; bỏ month.")
        if period is not None and year is not None:
            raise _invalid("year", "period đã chọn năm; bỏ year.")
        if (period == "year" or year is not None) and month is None:
            raise _invalid("month", "Cần month khi đã có năm.")
        if month is not None and day > _MAX_DAY_OF_MONTH[month]:
            raise _invalid("day", f"Tháng {month} không có ngày {day}.")
    return DateSpec(
        anchor=anchor,  # type: ignore[arg-type]
        period=period,
        period_offset=period_offset,
        lunar_year=lunar_year,
        day=day,
        month=month,
        year=year,
        offset=offset,
        before=before,
    )


# --- lịch ----------------------------------------------------------------------------------------------------
def _last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _shift_month(year: int, month: int, k: int) -> tuple[int, int]:
    y, m0 = divmod(year * 12 + month - 1 + k, 12)
    return y, m0 + 1


def _day_in_month(year: int, month: int, day: int) -> tuple[dt.date, bool]:
    last = _last_day(year, month)
    return dt.date(year, month, min(day, last)), day > last


def add_months(day: dt.date, months: int) -> tuple[dt.date, bool]:
    """Cộng `months` tháng (có thể âm), giữ ngày trong tháng; vượt số ngày của tháng đích thì ngày cuối tháng.
    Trả (ngày, đã về cuối tháng hay không)."""
    y, m = _shift_month(day.year, day.month, months)
    return _day_in_month(y, m, day.day)


def period_bounds(today: dt.date, period: str, k: int = 0) -> tuple[dt.date, dt.date]:
    """Ngày đầu và ngày cuối của kỳ thứ `k` tính từ kỳ chứa `today` (0 kỳ này, 1 kỳ sau, -1 kỳ trước)."""
    if period == "week":
        start = today - dt.timedelta(days=today.weekday()) + dt.timedelta(weeks=k)
        return start, start + dt.timedelta(days=6)
    if period == "month":
        y, m = _shift_month(today.year, today.month, k)
        return dt.date(y, m, 1), dt.date(y, m, _last_day(y, m))
    if period == "quarter":
        y, q = divmod(today.year * 4 + (today.month - 1) // 3 + k, 4)
        first = 3 * q + 1
        return dt.date(y, first, 1), dt.date(y, first + 2, _last_day(y, first + 2))
    if period == "year":
        return dt.date(today.year + k, 1, 1), dt.date(today.year + k, 12, 31)
    raise ValueError(f"period lạ: {period}")


def _exact_date(year: int, month: int, day: int) -> dt.date:
    try:
        return dt.date(year, month, day)
    except ValueError:
        raise _invalid("day", f"Năm {year} không có ngày {day:02d}/{month:02d}.") from None


def _anchor(
    s: DateSpec, today: dt.date, payday_day: int | None
) -> tuple[dt.date, dict[str, Any], bool]:
    """(ngày của mốc, trường giải thích riêng của mốc, đã về cuối tháng hay không)."""
    if s.anchor == "today":
        return today, {}, False
    if s.anchor == "next_payday":
        if payday_day is None:
            raise DateResolveError(
                ErrorCode.PROFILE_INCOMPLETE,
                "Bạn chưa khai ngày nhận lương nên chưa tính được ngày lương kế tiếp.",
            )
        return next_payday(payday_day, today), {"payday_day": payday_day}, False
    k = s.period_offset or 0
    if s.anchor in ("start_of", "end_of"):
        assert s.period is not None
        start, end = period_bounds(today, s.period, k)
        return (
            (start if s.anchor == "start_of" else end),
            {"period": s.period, "period_offset": k},
            False,
        )
    if s.anchor == "lunar_new_year":
        if s.lunar_year is not None:
            tet = lunar_new_year(s.lunar_year)
            return tet.date, {"lunar_new_year": tet}, False
        if s.period == "year":
            tet = lunar_new_year(today.year + k)
            return tet.date, {"lunar_new_year": tet, "period": "year", "period_offset": k}, False
        tet = next_lunar_new_year(today)
        return tet.date, {"lunar_new_year": tet, "next_occurrence": True}, False
    # anchor date
    assert s.day is not None
    if s.period == "month":
        y, m = _shift_month(today.year, today.month, k)
        day, clamped = _day_in_month(y, m, s.day)
        return day, {"period": "month", "period_offset": k}, clamped
    if s.period == "year":
        assert s.month is not None
        return (
            _exact_date(today.year + k, s.month, s.day),
            {"period": "year", "period_offset": k},
            False,
        )
    if s.year is not None:
        assert s.month is not None
        return _exact_date(s.year, s.month, s.day), {}, False
    if s.month is not None:
        for year in range(
            today.year, today.year + 9
        ):  # chín năm đủ gặp một năm nhuận cho ngày 29/02
            try:
                found = dt.date(year, s.month, s.day)
            except ValueError:
                continue
            if found > today:
                return found, {"next_occurrence": True}, False
        raise _invalid("day", f"Không có ngày {s.day:02d}/{s.month:02d} nào trong chín năm tới.")
    for months_ahead in (0, 1):
        y, m = _shift_month(today.year, today.month, months_ahead)
        found, clamped = _day_in_month(y, m, s.day)
        if found > today:
            return found, {"next_occurrence": True}, clamped
    raise AssertionError("tháng sau luôn có ngày sau hôm nay")  # pragma: no cover


def _normalized(offset: DateOffset | None) -> NormalizedOffset | None:
    if offset is None:
        return None
    years, months, weeks, days = (getattr(offset, u) or Decimal(0) for u in OFFSET_UNITS)
    total_months = years * 12 + months
    whole_months = int(total_months)  # cắt về phía 0: phần lẻ giữ dấu
    total_days = (total_months - whole_months) * DAYS_PER_FRACTIONAL_MONTH + weeks * 7 + days
    whole_days = int(total_days.to_integral_value(rounding=ROUND_HALF_UP))
    return NormalizedOffset(months=whole_months, days=whole_days)


def resolve_date(
    spec: DateSpec | Mapping[str, Any], today: dt.date, payday_day: int | None = None
) -> ResolvedDate:
    """Ngày tính từ đặc tả, kèm trường giải thích có cấu trúc. `today`: ngày mô phỏng của người dùng; `payday_day`: ngày nhận lương
    đã khai (cần cho mốc next_payday). Lỗi: DateResolveError với PARAMS_INVALID, PROFILE_INCOMPLETE, LUNAR_YEAR_UNSUPPORTED,
    DATE_IN_PAST."""
    s = parse_spec(spec.model_dump(exclude_none=True) if isinstance(spec, DateSpec) else spec)
    anchor_date, extra, clamped = _anchor(s, today, payday_day)
    offset = _normalized(s.offset)
    try:
        result = anchor_date
        if offset is not None and offset.months:
            result, month_clamped = add_months(result, offset.months)
            clamped = clamped or month_clamped
        if offset is not None:
            result += dt.timedelta(days=offset.days)
        if s.before:
            result -= dt.timedelta(days=1)
    except (OverflowError, ValueError):
        raise _invalid("offset", "Ngày tính ra nằm ngoài khoảng lịch tính được.") from None
    if result < today:
        raise DateResolveError(
            ErrorCode.DATE_IN_PAST,
            f"Ngày tính ra là {result:%d/%m/%Y}, đã qua so với hôm nay ({today:%d/%m/%Y}).",
            resolved_date=result,
        )
    return ResolvedDate(
        date=result,
        today=today,
        weekday=result.isoweekday(),
        days_from_today=(result - today).days,
        anchor=s.anchor,
        anchor_date=anchor_date,
        offset=offset,
        month_end_clamped=True if clamped else None,
        before=s.before,
        **extra,
    )
