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
