"""Đồng hồ mô phỏng (ADR-0003): mọi nơi cần "hôm nay" đều gọi `app_today`.

Mỗi người dùng có `clock_offset_days` (cột `users.clock_offset_days`). Ngày mô phỏng =
ngày hiện tại theo múi giờ ứng dụng + offset. Khi bấm "Đặt lại dữ liệu", offset được đặt sao cho
ngày mô phỏng quay về ngày neo (`clock_offset_for`), rồi ngày mô phỏng trôi theo thời gian thật.

Các hàm ở đây **thuần**: không đọc đồng hồ hệ thống; người gọi truyền `now` (có múi giờ).
Ngày neo và múi giờ là cấu hình (xem `yofina_core.config`), không gắn cứng ở đây.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

# Chỉ là tên gợi ý cho cấu hình `app_timezone`; các hàm bên dưới nhận tz tường minh.
DEFAULT_TIMEZONE_NAME = "Asia/Ho_Chi_Minh"


def app_timezone(name: str = DEFAULT_TIMEZONE_NAME) -> ZoneInfo:
    return ZoneInfo(name)


def _require_aware(now: datetime) -> None:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("`now` phải có múi giờ (aware datetime)")


def app_today(clock_offset_days: int, now: datetime, tz: tzinfo | None = None) -> date:
    """Ngày mô phỏng của một người dùng tại thời điểm `now`.

    >>> from datetime import timezone
    >>> app_today(-19, datetime(2026, 12, 10, 3, 0, tzinfo=timezone.utc))
    datetime.date(2026, 11, 21)
    """
    _require_aware(now)
    zone = tz if tz is not None else app_timezone()
    return now.astimezone(zone).date() + timedelta(days=clock_offset_days)


def clock_offset_for(target_app_date: date, now: datetime, tz: tzinfo | None = None) -> int:
    """Offset để `app_today(offset, now)` trả về `target_app_date` (dùng khi đặt lại dữ liệu)."""
    _require_aware(now)
    zone = tz if tz is not None else app_timezone()
    return (target_app_date - now.astimezone(zone).date()).days


# --- ngày lương (đồng hồ mô phỏng: người gọi truyền `today` = `app_today(...)`, không đọc đồng hồ hệ thống) ---
def _last_day_of_month(year: int, month: int) -> int:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return (nxt - timedelta(days=1)).day


def payday_in_month(payday_day: int, year: int, month: int) -> date:
    """Ngày lương của một tháng. Ngày lương lớn hơn số ngày của tháng thì lấy ngày cuối tháng
    (lương ngày 31 về ngày 30/11, 28/2 hoặc 29/2).

    >>> payday_in_month(31, 2026, 11)
    datetime.date(2026, 11, 30)
    """
    if not 1 <= payday_day <= 31:
        raise ValueError("payday_day phải trong khoảng 1..31")
    return date(year, month, min(payday_day, _last_day_of_month(year, month)))


def next_payday(payday_day: int, today: date) -> date:
    """Ngày lương KẾ TIẾP: ngày lương sớm nhất **sau** `today` (hôm nay là ngày lương thì lấy tháng sau).

    >>> next_payday(5, date(2026, 11, 21))
    datetime.date(2026, 12, 5)
    >>> next_payday(5, date(2026, 12, 5))
    datetime.date(2027, 1, 5)
    """
    this_month = payday_in_month(payday_day, today.year, today.month)
    if this_month > today:
        return this_month
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return payday_in_month(payday_day, year, month)


def latest_payday(payday_day: int, today: date) -> date:
    """Ngày lương gần nhất **không sau** `today` (đầu kỳ lương hiện tại; hôm nay là ngày lương thì lấy hôm nay).

    >>> latest_payday(5, date(2026, 11, 21))
    datetime.date(2026, 11, 5)
    """
    this_month = payday_in_month(payday_day, today.year, today.month)
    if this_month <= today:
        return this_month
    year, month = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    return payday_in_month(payday_day, year, month)


def payday_dates(payday_day: int, after: date, through: date) -> list[date]:
    """Mọi ngày lương trong khoảng (`after`, `through`], tăng dần. Dùng để dựng lịch lương của dự báo.

    >>> payday_dates(5, date(2026, 11, 21), date(2027, 1, 20))
    [datetime.date(2026, 12, 5), datetime.date(2027, 1, 5)]
    """
    out: list[date] = []
    cursor = next_payday(payday_day, after)
    while cursor <= through:
        out.append(cursor)
        cursor = next_payday(payday_day, cursor)
    return out
