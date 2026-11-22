"""Lịch nghĩa vụ và lương dùng chung ledger và dự báo: chu kỳ, kẹp cuối tháng, nghĩa vụ quá hạn, mốc trên biểu đồ."""

from __future__ import annotations

from datetime import date

import pytest

from yofina_core.schedule import (
    advance_due,
    bnpl_due_date,
    build_timeline_events,
    expand_due_dates,
    first_due_from_day,
    midpoint,
)


def test_chu_ky_ke_tiep():
    assert advance_due(date(2026, 1, 31), "monthly", 31) == date(2026, 2, 28)
    assert advance_due(date(2026, 2, 28), "monthly", 31) == date(
        2026, 3, 31
    )  # giữ due_day gốc, không trôi
    assert advance_due(date(2026, 12, 6), "monthly", 6) == date(2027, 1, 6)
    assert advance_due(date(2026, 11, 21), "weekly", None) == date(2026, 11, 28)
    assert advance_due(date(2024, 2, 29), "yearly", None) == date(2025, 2, 28)
    assert advance_due(date(2026, 11, 21), "once", None) is None


def test_han_dau_tien_tu_due_day():
    assert first_due_from_day(21, date(2026, 11, 21)) == date(
        2026, 11, 21
    )  # hôm nay đúng ngày đó thì lấy hôm nay
    assert first_due_from_day(20, date(2026, 11, 21)) == date(2026, 12, 20)
    assert first_due_from_day(31, date(2026, 12, 1)) == date(2026, 12, 31)
    assert first_due_from_day(30, date(2027, 1, 31)) == date(2027, 2, 28)


def test_han_tra_sau_la_due_day_ke_tiep_sau_ngay_mua():
    assert bnpl_due_date(5, date(2026, 11, 21)) == date(2026, 12, 5)
    assert bnpl_due_date(5, date(2026, 12, 5)) == date(
        2027, 1, 5
    )  # mua đúng ngày 5 thì sang tháng sau
    assert bnpl_due_date(5, date(2026, 12, 4)) == date(2026, 12, 5)
    assert bnpl_due_date(5, date(2026, 12, 31)) == date(2027, 1, 5)


def test_mo_rong_chu_ky_trong_horizon():
    first, through = date(2026, 11, 22), date(2026, 12, 21)
    assert expand_due_dates(date(2026, 11, 26), "monthly", 26, first=first, through=through) == [
        date(2026, 11, 26)
    ]
    assert expand_due_dates(date(2026, 12, 6), "monthly", 6, first=first, through=through) == [
        date(2026, 12, 6)
    ]
    assert expand_due_dates(date(2027, 1, 6), "monthly", 6, first=first, through=through) == []
    weekly = expand_due_dates(date(2026, 11, 22), "weekly", None, first=first, through=through)
    assert weekly == [
        date(2026, 11, 22),
        date(2026, 11, 29),
        date(2026, 12, 6),
        date(2026, 12, 13),
        date(2026, 12, 20),
    ]
    assert expand_due_dates(date(2026, 12, 5), "once", None, first=first, through=through) == [
        date(2026, 12, 5)
    ]


def test_nghia_vu_qua_han_tinh_vao_ngay_dau_roi_theo_chu_ky():
    first, through = date(2026, 11, 22), date(2026, 12, 21)
    out = expand_due_dates(date(2026, 11, 10), "monthly", 10, first=first, through=through)
    assert out == [first, date(2026, 12, 10)]
    assert expand_due_dates(date(2026, 11, 10), "once", None, first=first, through=through) == [
        first
    ]
    # kỳ kế tiếp trùng ngày đầu thì không đếm hai lần
    assert expand_due_dates(
        date(2026, 11, 15), "weekly", None, first=first, through=date(2026, 11, 22)
    ) == [first]


def test_trung_diem_lam_tron_xuong():
    assert midpoint(300_000, 450_000) == 375_000 and midpoint(1, 2) == 1


@pytest.mark.parametrize("origin", [date(2026, 11, 21)])
def test_moc_bieu_do_cua_hu_hoa_don(origin):
    obligations = [
        {
            "name": "Tiền điện",
            "amount_vnd": 375_000,
            "amount_max_vnd": 450_000,
            "cycle": "monthly",
            "due_day": 26,
            "due_date": date(2026, 11, 26),
            "pay_jar_code": "hoa_don",
            "status": "active",
        },
        {
            "name": "Tiền thuê phòng",
            "amount_vnd": 2_000_000,
            "cycle": "monthly",
            "due_day": 6,
            "due_date": date(2026, 12, 6),
            "pay_jar_code": "hoa_don",
            "status": "active",
        },
        {
            "name": "Netflix",
            "amount_vnd": 180_000,
            "cycle": "monthly",
            "due_day": 15,
            "due_date": date(2026, 12, 15),
            "pay_jar_code": "giai_tri",
            "status": "active",
        },
        {
            "name": "Đã hủy",
            "amount_vnd": 1,
            "cycle": "monthly",
            "due_day": 7,
            "due_date": date(2026, 12, 7),
            "pay_jar_code": "hoa_don",
            "status": "cancelled",
        },
        {
            "name": "Trả sau",
            "amount_vnd": 1_000_000,
            "cycle": "once",
            "due_date": date(2026, 12, 5),
            "pay_jar_code": None,
            "status": "active",
        },
    ]
    shares = [
        ("hoa_don", 31),
        ("an_uong", 30),
        ("di_lai", 7),
        ("giai_tri", 7),
        ("du_lich", 10),
        ("du_phong", 10),
        ("nghia_vu", 5),
    ]
    ev = build_timeline_events(
        jar_code="hoa_don", obligations=obligations, origin=origin, horizon_days=30, default_pay_jar="nghia_vu",
        salary_vnd=9_000_000, payday_day=5, split_shares=shares, salary_label="Lương về",
    )  # fmt: skip
    assert [(e.date.isoformat(), e.kind, e.label, e.amount_vnd, e.amount_max_vnd) for e in ev] == [
        ("2026-11-26", "obligation", "Tiền điện", 375_000, 450_000),
        ("2026-12-05", "salary", "Lương về", 2_790_000, None),
        ("2026-12-06", "obligation", "Tiền thuê phòng", 2_000_000, None),
    ]
    # nghĩa vụ không có hũ trả được gán cho hũ nghĩa vụ đầu tiên
    nv = build_timeline_events(
        jar_code="nghia_vu", obligations=obligations, origin=origin, horizon_days=30, default_pay_jar="nghia_vu",
        salary_vnd=9_000_000, payday_day=5, split_shares=shares, salary_label="Lương về",
    )  # fmt: skip
    assert [(e.label, e.amount_vnd) for e in nv] == [("Trả sau", 1_000_000), ("Lương về", 450_000)]
    # không có hũ nghĩa vụ thì không mô phỏng khoản chưa gán
    none = build_timeline_events(
        jar_code="nghia_vu", obligations=obligations, origin=origin, horizon_days=30, default_pay_jar=None,
        salary_vnd=9_000_000, payday_day=5, split_shares=shares, salary_label="Lương về",
    )  # fmt: skip
    assert all(e.label != "Trả sau" for e in none)
