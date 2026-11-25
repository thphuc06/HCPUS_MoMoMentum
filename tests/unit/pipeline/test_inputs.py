"""Dựng `ForecastInputs` từ dữ liệu một người dùng (hàm thuần): lịch sử, lương chia theo hũ, mở rộng nghĩa vụ, độ phủ, cấu hình."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from pipeline_helpers import APP_DATE, context_rows, jar_row, make_settings

from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.wallet import split_amount
from yofina_forecast.inputs import Context, build_inputs, expand_obligations, user_seed
from yofina_ml.api import forecast_user
from yofina_ml.calibration import calibrated_config
from yofina_ml.contract import check_inputs


def build(rows=None, **kw):
    ctx = Context.from_rows(rows if rows is not None else context_rows())
    assert ctx is not None
    return build_inputs(ctx, make_settings(**kw), "user-a", n_paths=500)


def test_inputs_dung_hop_dong_va_ngay_goc():
    built = build()
    inp = built.inputs
    assert check_inputs(inp) == []
    assert inp.app_date == APP_DATE and inp.horizon_days == 30
    assert inp.next_payday == date(2026, 12, 5) and inp.payday_day == 5
    assert inp.payday_dates == (date(2026, 12, 5),)
    assert built.jar_codes == ("an_uong", "giai_tri", "nghia_vu")
    for j in inp.jars:
        assert j.history_start + timedelta(days=j.history_days) == APP_DATE and j.history_days == 47
        assert all(isinstance(v, int) and v >= 0 for v in j.daily_spend_vnd)
    assert inp.coverage is not None and inp.coverage.income_vnd == 18_000_000


def test_luong_chia_theo_hu_bang_split_amount_vao_dung_ngay_luong():
    inp = build().inputs
    want = split_amount(9_000_000, [("an_uong", 60), ("giai_tri", 20), ("nghia_vu", 20)])
    for j in inp.jars:
        assert [(f.date, f.amount_vnd, f.kind) for f in j.inflows] == [
            (date(2026, 12, 5), want[j.code], "salary")
        ]


def test_nghia_vu_mo_rong_chu_ky_va_gan_hu_mac_dinh():
    inp = build().inputs
    nv = next(j for j in inp.jars if j.code == "nghia_vu")
    got = [(f.date, f.amount_vnd, f.label) for f in nv.outflows]
    # tiền điện hằng tháng ngày 26 (26/11; 26/12 vượt horizon 30 ngày), trả sau một lần ngày 5/12 gán cho hũ nghĩa vụ đầu tiên
    assert got == [
        (date(2026, 11, 26), 375_000, "Tiền điện"),
        (date(2026, 12, 5), 1_000_000, "Trả sau (mô phỏng)"),
    ]
    elec = nv.outflows[0]
    assert (elec.amount_min_vnd, elec.amount_max_vnd) == (300_000, 450_000)
    assert elec.ref_id == "00000000-0000-0000-0000-000000000001"
    assert all(not j.outflows for j in inp.jars if j.code != "nghia_vu")


def test_nghia_vu_qua_han_tinh_vao_ngay_dau_va_bo_nghia_vu_khong_gan_duoc():
    flows, unassigned = expand_obligations(
        [
            {"id": "a", "name": "Quá hạn", "amount_vnd": 100, "due_date": "2026-11-10",
             "cycle": "once", "due_day": None, "pay_jar_code": "x"},
            {"id": "b", "name": "Mồ côi", "amount_vnd": 50, "due_date": "2026-11-25",
             "cycle": "once", "due_day": None, "pay_jar_code": None},
        ],
        ["x"],
        None,  # không có hũ nghĩa vụ mặc định
        APP_DATE,
        30,
    )  # fmt: skip
    assert [f.date for f in flows["x"]] == [APP_DATE + timedelta(days=1)]
    assert unassigned == ["Mồ côi"]


def test_ghi_chu_nghia_vu_khong_gan_duoc_vao_notes():
    rows = context_rows(jars=[jar_row("an_uong", "spending", 1, 100, 1, [1] * 47)])
    built = build(rows)
    assert set(built.notes["unassigned_obligations"]) == {"Tiền điện", "Trả sau (mô phỏng)"}


def test_hat_ngau_nhien_tat_dinh_theo_nguoi_dung():
    assert user_seed("a") == user_seed("a") != user_seed("b")
    assert 0 <= user_seed("sub-xyz") < 2**31
    assert build().inputs == build().inputs  # cùng dữ liệu cho cùng đầu vào, kể cả hạt


def test_cau_hinh_lay_tu_settings_va_cong_tac_xac_suat():
    on = build().inputs.config
    assert on.n_paths == 500 and on.seed == user_seed("user-a")
    assert on.cold_start_min_days == 21 and on.short_threshold == 0.5 and on.tight_threshold == 0.2
    assert on.probability_enabled is calibrated_config().probability_enabled
    off = build(probability_enabled=False).inputs.config
    assert off.probability_enabled is False  # công tắc cấu hình tắt được dù hiệu chỉnh cho phép
    custom = build(short_threshold=0.6, tight_threshold=0.3, cold_start_min_days=10).inputs.config
    assert (custom.short_threshold, custom.tight_threshold, custom.cold_start_min_days) == (
        0.6,
        0.3,
        10,
    )


def test_lich_su_ngan_va_dem_so_0():
    rows = context_rows(days=5)
    for r in rows:
        if r["section"] == "jar":
            r["payload"]["spend"] = [10, 20]  # thiếu so với 5 ngày: đệm 0 ở đầu
    inp = build(rows).inputs
    assert inp.jars[0].daily_spend_vnd == (0, 0, 0, 10, 20)
    zero = build(context_rows(days=0)).inputs
    assert all(j.history_days == 0 for j in zero.jars)


def test_ho_so_chua_khai_luong_thi_profile_incomplete():
    for kw in ({"salary": None}, {"payday": None}):
        with pytest.raises(YofinaError) as e:
            build(context_rows(**kw))
        assert e.value.code == ErrorCode.PROFILE_INCOMPLETE


def test_ty_le_chia_khong_du_100_khong_mo_phong_luong():
    jars = [
        jar_row("a", "spending", 10, 40, 1, [1] * 47),
        jar_row("b", "spending", 10, 40, 2, [1] * 47),
    ]
    built = build(context_rows(jars=jars, obligations=[]))
    assert built.notes["salary_split_invalid"] is True
    assert all(not j.inflows for j in built.inputs.jars)


def test_chi_hu_nguoi_dung_duoc_du_bao_hu_he_thong_bi_loai():
    jars = [
        jar_row("an_uong", "spending", 100, 100, 1, [1] * 47),
        jar_row("tien_vao_khac", "system", 5, 0, 1000, [0] * 47),
        jar_row("chua_phan_loai", "system", -180, 0, 1001, [0] * 47),
    ]
    built = build(context_rows(jars=jars, obligations=[]))
    assert built.jar_codes == ("an_uong",)


def test_co_truncated_khi_ham_db_cham_tran():
    assert build(context_rows(spend_rows=5000)).notes["spend_truncated"] is True
    assert "spend_truncated" not in build().notes


def test_khong_co_hu_nao_thi_forecast_unavailable():
    with pytest.raises(YofinaError) as e:
        build(context_rows(jars=[jar_row("tien_vao_khac", "system", 0, 0, 1, [])]))
    assert e.value.code == ErrorCode.FORECAST_UNAVAILABLE


def test_context_rong_la_none():
    assert Context.from_rows([]) is None


def test_nguong_lich_su_cua_cong_xac_suat_ghi_de_duoc_qua_cau_hinh():
    # BR-31: ngưỡng số ngày lịch sử để hiện % theo loại hũ, mặc định theo backtest, cấu hình ghi đè được
    strict = build(
        probability_min_history_days_dense=400, probability_min_history_days_sparse=400
    ).inputs
    res = forecast_user(strict)
    assert all(not jf.summary.show_probability and jf.summary.p_shortfall is None for jf in res.jars)
    assert all(jf.summary.confidence_band in ("low", "medium", "high") for jf in res.jars)
    loose = build(probability_min_history_days_dense=21, probability_min_history_days_sparse=21).inputs
    shown = [jf.summary for jf in forecast_user(loose).jars if jf.summary.show_probability]
    assert shown and all(s.p_shortfall is not None for s in shown)  # 47 ngày >= 21: được hiện %