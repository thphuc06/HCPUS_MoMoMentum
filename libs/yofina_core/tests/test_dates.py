"""`yofina_core.dates`: ngày tính từ đặc tả có cấu trúc (issue #39). Hàm thuần, `today` là ngày mô phỏng truyền vào."""

from __future__ import annotations

import copy
import inspect
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from yofina_core import dates as D
from yofina_core.dates import DateResolveError, DateSpec, parse_spec, resolve_date
from yofina_core.errors import ErrorCode

TODAY = date(2026, 11, 26)  # thứ Năm


def at(spec: dict, today: date = TODAY, payday_day: int | None = None) -> date:
    return resolve_date(spec, today, payday_day=payday_day).date


def err(spec: dict, today: date = TODAY, payday_day: int | None = None) -> DateResolveError:
    with pytest.raises(DateResolveError) as e:
        resolve_date(spec, today, payday_day=payday_day)
    return e.value


def test_hom_nay_la_thu_nam():
    assert TODAY.isoweekday() == 4


# --- cộng tháng: giữ ngày, vượt cuối tháng thì về cuối tháng -------------------------------------------------
@pytest.mark.parametrize(
    ("start", "months", "expected", "clamped"),
    [
        (date(2027, 1, 31), 1, date(2027, 2, 28), True),
        (date(2028, 1, 31), 1, date(2028, 2, 29), True),  # năm nhuận
        (date(2027, 3, 31), 1, date(2027, 4, 30), True),
        (date(2027, 1, 15), 1, date(2027, 2, 15), False),
        (date(2026, 12, 31), 2, date(2027, 2, 28), True),
        (date(2026, 12, 31), 12, date(2027, 12, 31), False),
        (date(2027, 8, 31), 6, date(2028, 2, 29), True),
        (date(2027, 11, 30), 3, date(2028, 2, 29), True),
        (date(2027, 11, 29), 3, date(2028, 2, 29), False),
        (date(2027, 5, 31), -1, date(2027, 4, 30), True),
        (date(2027, 3, 31), -13, date(2026, 2, 28), True),
    ],
)
def test_cong_thang_giu_ngay_vuot_cuoi_thang_ve_cuoi_thang(start, months, expected, clamped):
    assert D.add_months(start, months) == (expected, clamped)
    if expected >= TODAY and start >= TODAY:
        spec = {
            "anchor": "date",
            "day": start.day,
            "month": start.month,
            "year": start.year,
            "offset": {"months": months},
        }
        res = resolve_date(spec, TODAY)
        assert res.date == expected and res.offset is not None and res.offset.months == months
        assert bool(res.month_end_clamped) == clamped


# --- năm nhuận -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("spec", "today", "expected"),
    [
        (
            {"anchor": "date", "day": 29, "month": 2, "year": 2028, "offset": {"years": 1}},
            TODAY,
            date(2029, 2, 28),
        ),
        (
            {"anchor": "date", "day": 29, "month": 2, "year": 2028, "offset": {"years": 4}},
            TODAY,
            date(2032, 2, 29),
        ),
        (
            {"anchor": "date", "day": 29, "month": 2},
            TODAY,
            date(2028, 2, 29),
        ),  # thiếu năm: năm nhuận gần nhất
        (
            {"anchor": "date", "day": 29, "month": 2},
            date(2028, 2, 29),
            date(2032, 2, 29),
        ),  # hôm nay không tính
        ({"anchor": "end_of", "period": "month"}, date(2028, 2, 10), date(2028, 2, 29)),
        ({"anchor": "end_of", "period": "month"}, date(2027, 2, 10), date(2027, 2, 28)),
        ({"anchor": "end_of", "period": "month", "period_offset": 3}, TODAY, date(2027, 2, 28)),
        ({"anchor": "end_of", "period": "month", "period_offset": 15}, TODAY, date(2028, 2, 29)),
    ],
)
def test_nam_nhuan(spec, today, expected):
    assert at(spec, today) == expected


def test_ngay_29_thang_2_cua_nam_khong_nhuan_la_tham_so_sai():
    e = err({"anchor": "date", "day": 29, "month": 2, "year": 2027})
    assert e.code is ErrorCode.PARAMS_INVALID and e.field == "day"
    e = err({"anchor": "date", "day": 29, "month": 2, "period": "year", "period_offset": 1})
    assert e.code is ErrorCode.PARAMS_INVALID and e.field == "day"


# --- quý: đầu, cuối quý sau và cuối quý này từ mọi tháng ----------------------------------------------------
QUARTERS = {
    1: (date(2026, 4, 1), date(2026, 6, 30), date(2026, 3, 31)),
    4: (date(2026, 7, 1), date(2026, 9, 30), date(2026, 6, 30)),
    7: (date(2026, 10, 1), date(2026, 12, 31), date(2026, 9, 30)),
    10: (date(2027, 1, 1), date(2027, 3, 31), date(2026, 12, 31)),
}


@pytest.mark.parametrize("month", range(1, 13))
def test_quy_sau_tu_moi_thang(month):
    today = date(2026, month, 15)
    next_start, next_end, this_end = QUARTERS[3 * ((month - 1) // 3) + 1]
    assert at({"anchor": "start_of", "period": "quarter", "period_offset": 1}, today) == next_start
    assert at({"anchor": "end_of", "period": "quarter", "period_offset": 1}, today) == next_end
    assert at({"anchor": "end_of", "period": "quarter"}, today) == this_end
    assert at({"anchor": "end_of", "period": "quarter", "period_offset": 0}, today) == this_end


def test_quy_xa_va_dau_quy_nay_da_qua():
    assert at({"anchor": "start_of", "period": "quarter", "period_offset": 5}) == date(2028, 1, 1)
    assert at({"anchor": "end_of", "period": "quarter", "period_offset": 4}) == date(2027, 12, 31)
    e = err({"anchor": "start_of", "period": "quarter"})
    assert e.code is ErrorCode.DATE_IN_PAST and e.resolved_date == date(2026, 10, 1)


# --- tuần (thứ Hai tới Chủ nhật), tháng, năm ----------------------------------------------------------------
@pytest.mark.parametrize(
    ("spec", "today", "expected"),
    [
        ({"anchor": "start_of", "period": "week", "period_offset": 1}, TODAY, date(2026, 11, 30)),
        ({"anchor": "end_of", "period": "week"}, TODAY, date(2026, 11, 29)),
        ({"anchor": "end_of", "period": "week", "period_offset": 1}, TODAY, date(2026, 12, 6)),
        (
            {"anchor": "start_of", "period": "week"},
            date(2026, 11, 30),
            date(2026, 11, 30),
        ),  # hôm nay thứ Hai
        (
            {"anchor": "end_of", "period": "week"},
            date(2026, 11, 29),
            date(2026, 11, 29),
        ),  # hôm nay Chủ nhật
        (
            {"anchor": "start_of", "period": "week", "period_offset": 1},
            date(2026, 12, 30),
            date(2027, 1, 4),
        ),
        ({"anchor": "today", "offset": {"weeks": 2}}, TODAY, date(2026, 12, 10)),
        (
            {"anchor": "today", "offset": {"weeks": 0.5}},
            TODAY,
            date(2026, 11, 30),
        ),  # 3,5 ngày làm tròn lên 4
        ({"anchor": "end_of", "period": "month"}, TODAY, date(2026, 11, 30)),
        ({"anchor": "start_of", "period": "month", "period_offset": 1}, TODAY, date(2026, 12, 1)),
        ({"anchor": "end_of", "period": "month", "period_offset": 1}, TODAY, date(2026, 12, 31)),
        ({"anchor": "start_of", "period": "year", "period_offset": 1}, TODAY, date(2027, 1, 1)),
        ({"anchor": "end_of", "period": "year"}, TODAY, date(2026, 12, 31)),
        ({"anchor": "end_of", "period": "year", "period_offset": 1}, TODAY, date(2027, 12, 31)),
        (
            {"anchor": "start_of", "period": "year", "period_offset": 1, "offset": {"days": -1}},
            TODAY,
            date(2026, 12, 31),
        ),
        ({"anchor": "today"}, TODAY, TODAY),
        ({"anchor": "today", "offset": {"days": 10}}, TODAY, date(2026, 12, 6)),
        ({"anchor": "today", "offset": {"months": 2}}, TODAY, date(2027, 1, 26)),
        ({"anchor": "today", "offset": {"years": 1, "months": 2}}, TODAY, date(2028, 1, 26)),
    ],
)
def test_tuan_thang_nam(spec, today, expected):
    assert at(spec, today) == expected


def test_tuan_bat_dau_thu_hai_ket_thuc_chu_nhat():
    for i in range(14):
        today = TODAY + timedelta(days=i)
        start = at({"anchor": "start_of", "period": "week", "period_offset": 1}, today)
        end = at({"anchor": "end_of", "period": "week", "period_offset": 1}, today)
        assert start.isoweekday() == 1 and end.isoweekday() == 7 and (end - start).days == 6
        assert 1 <= (start - today).days <= 7


# --- độ lệch có phần lẻ: quy đổi rõ ràng --------------------------------------------------------------------
@pytest.mark.parametrize(
    ("offset", "months", "days", "expected"),
    [
        ({"years": 1.5}, 18, 0, date(2028, 5, 26)),
        ({"years": 0.25}, 3, 0, date(2027, 2, 26)),
        ({"months": 1.5}, 1, 15, date(2027, 1, 10)),
        ({"months": 1.25}, 1, 8, date(2027, 1, 3)),  # 7,5 ngày làm tròn ra xa 0
        ({"years": 1, "months": 6}, 18, 0, date(2028, 5, 26)),
        ({"weeks": 1.5}, 0, 11, date(2026, 12, 7)),  # 10,5 ngày -> 11
        ({"days": 2.4}, 0, 2, date(2026, 11, 28)),
        ({"years": 2, "weeks": 1, "days": 1}, 24, 8, date(2028, 12, 4)),
    ],
)
def test_do_lech_thap_phan_quy_doi(offset, months, days, expected):
    res = resolve_date({"anchor": "today", "offset": offset}, TODAY)
    assert res.date == expected
    assert (res.offset.months, res.offset.days) == (months, days)


def test_do_lech_am_va_le():
    # 31/03/2027 lùi 1,5 tháng: lùi 1 tháng (về 28/02, cuối tháng) rồi lùi 15 ngày
    res = resolve_date(
        {"anchor": "date", "day": 31, "month": 3, "year": 2027, "offset": {"months": -1.5}}, TODAY
    )
    assert res.date == date(2027, 2, 13) and (res.offset.months, res.offset.days) == (-1, -15)
    assert res.month_end_clamped is True
    assert at({"anchor": "lunar_new_year", "offset": {"weeks": -2}}) == date(2027, 1, 23)


def test_do_lech_bang_khong_thi_khong_ghi_offset():
    res = resolve_date({"anchor": "today", "offset": {"days": 0, "months": 0}}, TODAY)
    assert res.date == TODAY and res.offset is None
    assert "offset" not in res.to_wire()


# --- ngày cụ thể thiếu năm hoặc thiếu tháng: lần gần nhất SAU hôm nay -----------------------------------------
@pytest.mark.parametrize(
    ("spec", "expected", "clamped"),
    [
        ({"anchor": "date", "day": 15, "month": 3}, date(2027, 3, 15), False),
        (
            {"anchor": "date", "day": 26, "month": 11},
            date(2027, 11, 26),
            False,
        ),  # đúng hôm nay: lấy năm sau
        ({"anchor": "date", "day": 25, "month": 11}, date(2027, 11, 25), False),  # đã qua trong năm
        ({"anchor": "date", "day": 27, "month": 11}, date(2026, 11, 27), False),
        ({"anchor": "date", "day": 1, "month": 1}, date(2027, 1, 1), False),
        ({"anchor": "date", "day": 31, "month": 12}, date(2026, 12, 31), False),
        ({"anchor": "date", "day": 30}, date(2026, 11, 30), False),
        ({"anchor": "date", "day": 26}, date(2026, 12, 26), False),
        ({"anchor": "date", "day": 5}, date(2026, 12, 5), False),
        ({"anchor": "date", "day": 31}, date(2026, 11, 30), True),  # tháng 11 không có ngày 31
    ],
)
def test_ngay_cu_the_thieu_nam_hoac_thang(spec, expected, clamped):
    res = resolve_date(spec, TODAY)
    assert res.date == expected and res.next_occurrence is True
    assert bool(res.month_end_clamped) == clamped


def test_chi_co_ngay_31_hom_nay_cuoi_thang_thi_sang_thang_sau():
    assert at({"anchor": "date", "day": 31}, date(2026, 11, 30)) == date(2026, 12, 31)
    assert at({"anchor": "date", "day": 30}, date(2027, 2, 28)) == date(2027, 3, 30)


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ({"anchor": "date", "day": 15, "period": "month", "period_offset": 1}, date(2026, 12, 15)),
        ({"anchor": "date", "day": 31, "period": "month", "period_offset": 3}, date(2027, 2, 28)),
        (
            {"anchor": "date", "day": 15, "month": 3, "period": "year", "period_offset": 1},
            date(2027, 3, 15),
        ),
        ({"anchor": "date", "day": 20, "month": 12, "period": "year"}, date(2026, 12, 20)),
        ({"anchor": "date", "day": 15, "month": 6, "year": 2027}, date(2027, 6, 15)),
    ],
)
def test_ngay_cu_the_theo_thang_hoac_nam_tuong_doi(spec, expected):
    res = resolve_date(spec, TODAY)
    assert res.date == expected and res.next_occurrence is None


def test_ngay_cu_the_khong_co_that_la_tham_so_sai():
    for spec in (
        {"anchor": "date", "day": 31, "month": 4},
        {"anchor": "date", "day": 30, "month": 2},
        {"anchor": "date", "day": 31, "month": 6, "year": 2027},
    ):
        e = err(spec)
        assert e.code is ErrorCode.PARAMS_INVALID and e.field == "day", spec


# --- Tết âm lịch: dữ liệu tra -------------------------------------------------------------------------------
TET = {
    2026: (date(2026, 2, 17), "Bính Ngọ"),
    2027: (date(2027, 2, 6), "Đinh Mùi"),
    2028: (date(2028, 1, 26), "Mậu Thân"),
    2029: (date(2029, 2, 13), "Kỷ Dậu"),
    2030: (date(2030, 2, 2), "Canh Tuất"),  # Việt Nam UTC+7; Trung Quốc 03/02
    2031: (date(2031, 1, 23), "Tân Hợi"),
    2032: (date(2032, 2, 11), "Nhâm Tý"),
    2033: (date(2033, 1, 31), "Quý Sửu"),
    2034: (date(2034, 2, 19), "Giáp Dần"),
    2035: (date(2035, 2, 8), "Ất Mão"),
}


@pytest.mark.parametrize("year", sorted(TET))
def test_tet_cac_nam_trong_bang(year):
    day, name = TET[year]
    tet = D.lunar_new_year(year)
    assert (tet.year, tet.date, tet.name) == (year, day, name)
    res = resolve_date({"anchor": "lunar_new_year", "lunar_year": year}, date(2026, 1, 1))
    assert res.date == day and res.lunar_new_year == tet
    before = resolve_date(
        {"anchor": "lunar_new_year", "lunar_year": year, "before": True}, date(2026, 1, 1)
    )
    assert (
        before.date == day - timedelta(days=1)
        and before.anchor_date == day
        and before.before is True
    )


def test_bang_tet_du_10_nam_lien_tuc_dung_can_chi_va_khoang_ngay():
    table = D.lunar_new_years()
    assert list(table) == list(range(2026, 2036))
    stems = ["Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý"]
    branches = ["Tý", "Sửu", "Dần", "Mão", "Thìn", "Tỵ", "Ngọ", "Mùi", "Thân", "Dậu", "Tuất", "Hợi"]
    for year, tet in table.items():
        assert tet.name == f"{stems[(year - 4) % 10]} {branches[(year - 4) % 12]}"
        assert date(year, 1, 21) <= tet.date <= date(year, 2, 20)


def test_file_du_lieu_tet_co_nguon():
    raw = json.loads(
        Path(inspect.getfile(D)).with_name("lunar_new_year.json").read_text(encoding="utf-8")
    )
    assert raw["timezone"] == "UTC+7"
    assert raw["sources"] and all(
        s["url"].startswith("https://") and s["name"] for s in raw["sources"]
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda o: o["years"].pop(3),  # thiếu một năm
        lambda o: o["years"][0].update(date="2026-03-01"),  # ngoài khoảng 21/01..20/02
        lambda o: o["years"][1].update(date="2026-02-06"),  # sai năm
        lambda o: o["years"].reverse(),
        lambda o: o.update(sources=[]),
        lambda o: o.update(timezone="UTC+8"),
        lambda o: o["years"][2].update(name=""),
    ],
)
def test_bang_tet_sai_bi_tu_choi(mutate):
    raw = json.loads(
        Path(inspect.getfile(D)).with_name("lunar_new_year.json").read_text(encoding="utf-8")
    )
    bad = copy.deepcopy(raw)
    mutate(bad)
    with pytest.raises(ValueError):
        D.parse_lunar_table(bad)


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (TODAY, date(2027, 2, 6)),
        (date(2026, 1, 10), date(2026, 2, 17)),
        (date(2027, 2, 6), date(2028, 1, 26)),  # hôm nay là Mùng 1: lấy Tết sau
        (date(2027, 2, 5), date(2027, 2, 6)),
    ],
)
def test_tet_khong_neu_nam_la_tet_gan_nhat_sau_hom_nay(today, expected):
    res = resolve_date({"anchor": "lunar_new_year"}, today)
    assert res.date == expected and res.next_occurrence is True


def test_truoc_tet_la_ngay_truoc_mung_1_va_giai_thich_du_cho_writer():
    res = resolve_date({"anchor": "lunar_new_year", "before": True}, TODAY)
    assert res.to_wire() == {
        "date": "2027-02-05",
        "today": "2026-11-26",
        "weekday": 5,
        "days_from_today": 71,
        "anchor": "lunar_new_year",
        "anchor_date": "2027-02-06",
        "lunar_new_year": {"year": 2027, "date": "2027-02-06", "name": "Đinh Mùi"},
        "next_occurrence": True,
        "before": True,
    }


def test_tet_nam_tuong_doi():
    assert at({"anchor": "lunar_new_year", "period": "year", "period_offset": 1}) == date(
        2027, 2, 6
    )
    assert at({"anchor": "lunar_new_year", "period": "year", "period_offset": 2}) == date(
        2028, 1, 26
    )
    e = err({"anchor": "lunar_new_year", "period": "year"})  # Tết 2026 đã qua
    assert e.code is ErrorCode.DATE_IN_PAST and e.resolved_date == date(2026, 2, 17)


@pytest.mark.parametrize(
    ("spec", "today"),
    [
        ({"anchor": "lunar_new_year", "lunar_year": 2025}, date(2024, 6, 1)),
        ({"anchor": "lunar_new_year", "lunar_year": 2036}, TODAY),
        ({"anchor": "lunar_new_year"}, date(2035, 3, 1)),  # Tết kế tiếp (2036) ngoài bảng
        ({"anchor": "lunar_new_year", "period": "year", "period_offset": 10}, TODAY),
    ],
)
def test_nam_ngoai_bang_tet_la_loi_co_ma(spec, today):
    e = err(spec, today)
    assert e.code is ErrorCode.LUNAR_YEAR_UNSUPPORTED
    assert "2026" in e.message and "2035" in e.message


def test_tet_nam_nay_da_qua_thi_bao_qua_khu_khong_tu_doi():
    e = err({"anchor": "lunar_new_year", "lunar_year": 2026, "before": True})
    assert e.code is ErrorCode.DATE_IN_PAST and e.resolved_date == date(2026, 2, 16)


# --- ngày lương kế ------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("payday", "today", "expected"),
    [
        (5, TODAY, date(2026, 12, 5)),
        (26, TODAY, date(2026, 12, 26)),  # hôm nay là ngày lương: kỳ sau
        (27, TODAY, date(2026, 11, 27)),
        (31, date(2027, 2, 10), date(2027, 2, 28)),
        (31, date(2026, 12, 31), date(2027, 1, 31)),
    ],
)
def test_moc_ngay_luong_ke(payday, today, expected):
    res = resolve_date({"anchor": "next_payday"}, today, payday_day=payday)
    assert res.date == expected and res.payday_day == payday and res.anchor_date == expected


def test_truoc_ngay_luong_va_chua_khai_ngay_luong():
    assert at({"anchor": "next_payday", "before": True}, payday_day=5) == date(2026, 12, 4)
    assert at({"anchor": "next_payday", "offset": {"months": 1}}, payday_day=5) == date(2027, 1, 5)
    e = err({"anchor": "next_payday"})
    assert e.code is ErrorCode.PROFILE_INCOMPLETE
    assert at({"anchor": "today"}, payday_day=None) == TODAY  # mốc khác không cần ngày lương


# --- kết quả quá khứ -> lỗi có mã -----------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("spec", "resolved"),
    [
        ({"anchor": "today", "offset": {"days": -1}}, date(2026, 11, 25)),
        ({"anchor": "today", "before": True}, date(2026, 11, 25)),
        ({"anchor": "date", "day": 1, "month": 1, "year": 2026}, date(2026, 1, 1)),
        ({"anchor": "date", "day": 15, "period": "month"}, date(2026, 11, 15)),
        ({"anchor": "start_of", "period": "month"}, date(2026, 11, 1)),
        ({"anchor": "end_of", "period": "week", "period_offset": -1}, date(2026, 11, 22)),
    ],
)
def test_ket_qua_qua_khu_la_loi_co_ma_khong_tu_doi(spec, resolved):
    e = err(spec)
    assert e.code is ErrorCode.DATE_IN_PAST and e.resolved_date == resolved
    assert resolved.strftime("%d/%m/%Y") in e.message
    assert e.tool_result()["code"] == "DATE_IN_PAST"


def test_hom_nay_khong_phai_qua_khu():
    res = resolve_date({"anchor": "end_of", "period": "week"}, date(2026, 11, 29))
    assert res.date == date(2026, 11, 29) and res.days_from_today == 0


# --- đặc tả sai: PARAMS_INVALID kèm tên trường ---------------------------------------------------------------
@pytest.mark.parametrize(
    ("spec", "field"),
    [
        ({}, "anchor"),
        ({"anchor": "tomorrow"}, "anchor"),
        ({"anchor": 1}, "anchor"),
        ({"anchor": "start_of"}, "period"),
        ({"anchor": "end_of", "period": "decade"}, "period"),
        ({"anchor": "today", "period_offset": 1}, "period_offset"),
        ({"anchor": "start_of", "period": "month", "period_offset": True}, "period_offset"),
        ({"anchor": "start_of", "period": "month", "period_offset": 1.5}, "period_offset"),
        ({"anchor": "start_of", "period": "month", "period_offset": "1"}, "period_offset"),
        ({"anchor": "today", "day": 3}, "day"),
        ({"anchor": "today", "period": "month"}, "period"),
        ({"anchor": "next_payday", "lunar_year": 2027}, "lunar_year"),
        ({"anchor": "start_of", "period": "month", "day": 3}, "day"),
        ({"anchor": "date"}, "day"),
        ({"anchor": "date", "day": 0}, "day"),
        ({"anchor": "date", "day": 32}, "day"),
        ({"anchor": "date", "day": 3, "month": 13}, "month"),
        ({"anchor": "date", "day": 3, "year": 2027}, "month"),
        ({"anchor": "date", "day": 3, "month": 2, "year": 1800}, "year"),
        ({"anchor": "date", "day": 3, "period": "week"}, "period"),
        ({"anchor": "date", "day": 3, "month": 2, "period": "month", "period_offset": 1}, "month"),
        ({"anchor": "date", "day": 3, "month": 2, "year": 2027, "period": "year"}, "year"),
        ({"anchor": "date", "day": 3, "period": "year", "period_offset": 1}, "month"),
        ({"anchor": "lunar_new_year", "period": "month"}, "period"),
        ({"anchor": "lunar_new_year", "lunar_year": 2027, "period": "year"}, "lunar_year"),
        ({"anchor": "lunar_new_year", "lunar_year": "2027"}, "lunar_year"),
        ({"anchor": "today", "offset": 3}, "offset"),
        ({"anchor": "today", "offset": {"hours": 3}}, "offset"),
        ({"anchor": "today", "offset": {"days": "3"}}, "offset"),
        ({"anchor": "today", "offset": {"days": True}}, "offset"),
        ({"anchor": "today", "offset": {"days": 1.23456}}, "offset"),
        ({"anchor": "today", "offset": {"years": 101}}, "offset"),
        ({"anchor": "today", "offset": {"days": float("nan")}}, "offset"),
        ({"anchor": "today", "before": "yes"}, "before"),
        ({"anchor": "today", "today": "2020-01-01"}, "today"),
    ],
)
def test_dac_ta_sai_la_tham_so_sai_kem_ten_truong(spec, field):
    e = err(spec)
    assert e.code is ErrorCode.PARAMS_INVALID and e.field == field, (spec, e.field, e.message)
    assert 0 < len(e.message) <= 280


def test_dac_ta_khong_phai_doi_tuong():
    with pytest.raises(DateResolveError) as e:
        parse_spec(["today"])  # type: ignore[arg-type]
    assert e.value.code is ErrorCode.PARAMS_INVALID


def test_gia_tri_null_coi_nhu_vang():
    spec = {"anchor": "today", "period": None, "day": None, "offset": None, "before": None}
    assert at(spec) == TODAY


def test_nhan_ca_model_da_dung_san():
    spec = parse_spec(
        {"anchor": "end_of", "period": "quarter", "period_offset": 1, "offset": {"days": -1}}
    )
    assert isinstance(spec, DateSpec)
    assert resolve_date(spec, TODAY).date == date(2027, 3, 30)
    assert (
        parse_spec(spec.model_dump(exclude_none=True)) == spec
    )  # dump rồi parse lại ra đúng đặc tả


def test_truong_dac_ta_khop_model():
    assert tuple(DateSpec.model_fields) == D.SPEC_FIELDS
    assert set(D.OFFSET_UNITS) == set(D.DateOffset.model_fields)
    assert D.ANCHORS == ("today", "next_payday", "start_of", "end_of", "lunar_new_year", "date")
    assert D.PERIODS == ("week", "month", "quarter", "year")


# --- giải thích có cấu trúc ---------------------------------------------------------------------------------
def test_giai_thich_cua_moc_ky_va_do_lech():
    res = resolve_date(
        {"anchor": "start_of", "period": "quarter", "period_offset": 1, "offset": {"years": 1.5}},
        TODAY,
    )
    assert res.to_wire() == {
        "date": "2028-07-01",
        "today": "2026-11-26",
        "weekday": 6,
        "days_from_today": (date(2028, 7, 1) - TODAY).days,
        "anchor": "start_of",
        "anchor_date": "2027-01-01",
        "period": "quarter",
        "period_offset": 1,
        "offset": {"months": 18, "days": 0},
        "before": False,
    }


def test_giai_thich_ngay_luong_va_cuoi_thang():
    wire = resolve_date({"anchor": "next_payday"}, TODAY, payday_day=5).to_wire()
    assert (
        wire["payday_day"] == 5 and wire["anchor"] == "next_payday" and "lunar_new_year" not in wire
    )
    wire = resolve_date(
        {"anchor": "date", "day": 31, "period": "month", "period_offset": 3}, TODAY
    ).to_wire()
    assert wire["month_end_clamped"] is True and wire["date"] == "2027-02-28"


def test_tat_dinh_khong_doc_dong_ho_he_thong():
    src = inspect.getsource(D)
    for needle in ("date.today(", "datetime.now(", "time.time(", "datetime.today("):
        assert needle not in src
    spec = {"anchor": "lunar_new_year", "before": True, "offset": {"weeks": -1}}
    assert resolve_date(spec, TODAY) == resolve_date(spec, TODAY)
