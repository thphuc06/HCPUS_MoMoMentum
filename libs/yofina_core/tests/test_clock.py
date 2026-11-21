from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from yofina_core.clock import app_timezone, app_today, clock_offset_for

VN = app_timezone()


def test_app_today_cong_offset_vao_ngay_theo_gio_viet_nam():
    now = datetime(2026, 12, 10, 3, 0, tzinfo=UTC)  # 10:00 ngày 10/12 ở Việt Nam
    assert app_today(0, now) == date(2026, 12, 10)
    assert app_today(-19, now) == date(2026, 11, 21)
    assert app_today(5, now) == date(2026, 12, 15)


def test_ranh_gioi_ngay_theo_mui_gio_ung_dung_khong_theo_utc():
    # 17:30 UTC = 00:30 hôm sau ở UTC+7
    now = datetime(2026, 12, 9, 17, 30, tzinfo=UTC)
    assert app_today(0, now) == date(2026, 12, 10)
    # cùng một thời điểm biểu diễn ở múi giờ khác phải cho cùng kết quả
    other = now.astimezone(timezone(timedelta(hours=-8)))
    assert app_today(0, other) == date(2026, 12, 10)


def test_chuyen_tz_tuong_minh():
    now = datetime(2026, 12, 9, 17, 30, tzinfo=UTC)
    assert app_today(0, now, tz=UTC) == date(2026, 12, 9)


def test_clock_offset_for_dua_ngay_mo_phong_ve_ngay_neo():
    anchor = date(2026, 11, 21)
    now = datetime(2026, 12, 10, 3, 0, tzinfo=UTC)
    offset = clock_offset_for(anchor, now)
    assert offset == -19
    assert app_today(offset, now) == anchor


def test_sau_khi_dat_lai_ngay_mo_phong_troi_theo_thoi_gian_that():
    anchor = date(2026, 11, 21)
    t0 = datetime(2026, 12, 10, 3, 0, tzinfo=UTC)
    offset = clock_offset_for(anchor, t0)
    assert app_today(offset, t0 + timedelta(days=3)) == date(2026, 11, 24)
    assert app_today(offset, t0 + timedelta(hours=10)) == date(2026, 11, 21)


def test_tu_choi_datetime_khong_co_mui_gio():
    naive = datetime(2026, 12, 10, 3, 0)
    with pytest.raises(ValueError):
        app_today(0, naive)
    with pytest.raises(ValueError):
        clock_offset_for(date(2026, 11, 21), naive)
