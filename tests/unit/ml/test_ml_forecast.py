"""`forecast_user` và `update_forecast`: tất định, bất biến, cổng khởi đầu lạnh, chỉnh nhanh, hợp đồng, ca biên."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta

import pytest
from conftest import BASE
from jsonschema import Draft202012Validator
from ml_helpers import APP_DATE, inputs, jar, obligation, salary, with_config

from yofina_ml import contract, serde
from yofina_ml.api import forecast_user, update_forecast
from yofina_ml.types import CoverageInputs, ForecastConfig

PROB_ON = {"calibration": {"dense": {"probability_ok": True}, "sparse": {"probability_ok": True}}}


def _ok(inp, res, **kw):
    assert contract.check_result(inp, res, **kw) == []


# --- tất định và hợp đồng ---------------------------------------------------------------------------------
def test_cung_dau_vao_cung_ket_qua_va_doi_seed_doi_ket_qua():
    inp = inputs()
    a, b = forecast_user(inp), forecast_user(inp)
    assert a == b
    _ok(inp, a)
    c = forecast_user(with_config(inp, seed=6))
    assert c != a
    assert c.run.seed == 6


def test_seed_none_van_tat_dinh_va_ghi_none():
    inp = with_config(inputs(), seed=None)
    a, b = forecast_user(inp), forecast_user(inp)
    assert a == b and a.run.seed is None
    _ok(inp, a)


def test_ket_qua_chuyen_json_va_hop_le_voi_schema(registry):
    inp = inputs()
    res = forecast_user(inp)
    obj = serde.forecast_result_to_dict(res)
    json.dumps(obj)  # params phải là JSON thuần
    v = Draft202012Validator(
        {"$ref": f"{BASE}/ml/forecast_io.schema.json#/$defs/ForecastResult"}, registry=registry
    )
    assert list(v.iter_errors(obj)) == []
    assert serde.forecast_result_to_dict(serde.forecast_result_from_dict(obj)) == obj
    vi = Draft202012Validator(
        {"$ref": f"{BASE}/ml/forecast_io.schema.json#/$defs/ForecastInputs"}, registry=registry
    )
    assert list(vi.iter_errors(serde.forecast_inputs_to_dict(inp))) == []


def test_params_ghi_chan_doan_va_trang_thai_tung_hu():
    res = forecast_user(inputs())
    p = res.run.params
    assert {
        "calibration",
        "aci_gamma",
        "jar_state",
        "jar_models",
        "payday_day",
        "data_coverage_formula",
    } <= set(p)
    assert set(p["jar_state"]) == {"an_uong", "giai_tri", "nghia_vu"}
    assert p["jar_state"]["an_uong"]["marginal"]["type"] == "hurdle_calendar"
    assert res.run.model == "hurdle_calendar" and res.run.model_version


# --- bất biến phân vị, lịch tất định -----------------------------------------------------------------------
def test_khong_co_chi_thi_so_du_chi_theo_lich_dung_ngay():
    j = jar(
        "du_phong", n=40, spend=(0,) * 40, balance=1_000_000, kind="saving",
        inflows=(salary(10, 3_000_000),),
        outflows=(obligation(5, 500_000), obligation(20, 150_000, 100_000, 200_000, "Điện")),
    )  # fmt: skip
    inp = inputs((j,))
    res = forecast_user(inp)
    _ok(inp, res)
    days = res.jars[0].days
    for i, d in enumerate(days, start=1):
        assert d.spend_p10_vnd == d.spend_p50_vnd == d.spend_p90_vnd == 0
        base = 1_000_000 - (500_000 if i >= 5 else 0) + (3_000_000 if i >= 10 else 0)
        if i < 20:
            assert d.balance_p10_vnd == d.balance_p50_vnd == d.balance_p90_vnd == base
        else:  # nghĩa vụ theo khoảng: lấy mẫu đều trong [100k, 200k]
            assert (
                base - 200_000
                <= d.balance_p10_vnd
                <= d.balance_p50_vnd
                <= d.balance_p90_vnd
                <= base - 100_000
            )
    assert res.jars[0].summary.runout_date is None and res.jars[0].summary.status == "ok"


def test_nghia_vu_va_luong_roi_dung_ngay_trong_duong_trung_vi():
    inp = inputs()
    res = forecast_user(inp)
    nv = next(jf for jf in res.jars if jf.summary.jar_code == "nghia_vu")
    days = {d.date: d for d in nv.days}
    d4, d5 = days[APP_DATE + timedelta(days=4)], days[APP_DATE + timedelta(days=5)]
    assert (
        d4.balance_p50_vnd - d5.balance_p50_vnd == 1_200_000
    )  # tiền trọ ra đúng ngày 5, không ngày khác
    au = next(jf for jf in res.jars if jf.summary.jar_code == "an_uong")
    adays = {d.date: d for d in au.days}
    d13, d14 = adays[APP_DATE + timedelta(days=13)], adays[APP_DATE + timedelta(days=14)]
    assert (
        d14.balance_p50_vnd - d13.balance_p50_vnd > 2_000_000
    )  # lương 3tr vào ngày lương, trừ chi ngày


def test_ngay_can_la_ngay_dau_tien_p50_so_du_khong_duong():
    inp = inputs((jar("an_uong", n=60, seed=1, balance=200_000, med=60_000),))
    res = forecast_user(inp)
    _ok(inp, res)
    s, days = res.jars[0].summary, res.jars[0].days
    first = next((d.date for d in days if d.balance_p50_vnd <= 0), None)
    assert s.runout_date == first and first is not None
    assert all(d.balance_p50_vnd > 0 for d in days if d.date < first)


def test_hu_du_tien_khong_can_va_trang_thai_ok():
    inp = inputs((jar("an_uong", n=60, seed=1, balance=500_000_000),))
    res = forecast_user(inp)
    s = res.jars[0].summary
    assert s.runout_date is None and s.status == "ok"


def test_so_du_am_thi_thieu_hut_chac_chan():
    inp = with_config(
        inputs((jar("an_uong", n=60, seed=1, balance=-100_000),)),
        extra=PROB_ON,
        probability_enabled=True,
    )
    res = forecast_user(inp)
    _ok(inp, res)
    s = res.jars[0].summary
    assert (
        s.status == "short"
        and s.p_shortfall == 1.0
        and s.runout_date == APP_DATE + timedelta(days=1)
    )


def test_so_du_bang_0_hut_ngay_neu_con_chi_tieu():
    inp = inputs((jar("an_uong", n=60, seed=1, balance=0, p=1.0),))
    res = forecast_user(inp)
    _ok(inp, res)
    assert res.jars[0].summary.runout_date == APP_DATE + timedelta(days=1)


@pytest.mark.parametrize("kind", ["saving", "spending"])
def test_so_du_bang_0_khong_gi_rut_tien_thi_khong_co_ngay_can(kind):
    """Hũ 0 ₫ không có chi tiêu trong lịch sử và không có khoản đến hạn (hũ tiết kiệm vừa thêm, issue #39): số dư không bao giờ giảm,
    nên không "cạn ngày mai"; chạy nhanh cũng vậy. Có khoản đến hạn thì có tiền bị rút: hũ đã ở ngưỡng cạn nên cạn từ ngày mai như cũ."""
    empty = jar("dau_tu", n=60, spend=(0,) * 60, balance=0, kind=kind)
    inp = inputs((empty,))
    res = forecast_user(inp)
    _ok(inp, res)
    s = res.jars[0].summary
    assert s.runout_date is None and s.status == "ok"
    assert all(d.balance_p50_vnd == 0 for d in res.jars[0].days)
    assert update_forecast(inp, res, ["dau_tu"]).jars[0].summary.runout_date is None
    due = forecast_user(inputs((replace(empty, outflows=(obligation(6, 200_000),)),)))
    assert due.jars[0].summary.runout_date == APP_DATE + timedelta(days=1)

# --- xác suất hụt và độ tin cậy -----------------------------------------------------------------------------
def test_chi_phat_xac_suat_khi_bat_va_hieu_chuan_dat():
    base = inputs()
    off = forecast_user(base)
    assert all(
        not jf.summary.show_probability and jf.summary.p_shortfall is None for jf in off.jars
    )
    only_flag = forecast_user(
        with_config(
            base,
            probability_enabled=True,
            extra={
                "calibration": {
                    "dense": {"probability_ok": False},
                    "sparse": {"probability_ok": False},
                }
            },
        )
    )
    assert all(
        not jf.summary.show_probability for jf in only_flag.jars
    )  # cờ bật nhưng hiệu chỉnh chưa đạt: không phát
    inp = with_config(base, probability_enabled=True, extra=PROB_ON)
    on = forecast_user(inp)
    _ok(inp, on)
    shown = [jf.summary for jf in on.jars if jf.summary.show_probability]
    assert shown and all(0 <= s.p_shortfall <= 1 and s.p_shortfall_se >= 0 for s in shown)
    # status không phụ thuộc việc có hiện xác suất hay không
    assert [jf.summary.status for jf in on.jars] == [jf.summary.status for jf in off.jars]


def _gate(dense_days: int, sparse_days: int) -> dict:
    return {
        "calibration": {
            "dense": {"probability_ok": True, "probability_min_history_days": dense_days},
            "sparse": {"probability_ok": True, "probability_min_history_days": sparse_days},
        }
    }


def _two_jars(n: int) -> tuple:
    return (
        jar("an_uong", n=n, seed=1, balance=900_000),
        jar("giai_tri", n=n, seed=2, p=0.2, med=90_000, balance=700_000),
    )


def test_hu_lich_su_duoi_nguong_cua_loai_hu_thi_an_xac_suat_giu_nhan_va_trang_thai():
    inp = with_config(inputs(_two_jars(60)), probability_enabled=True, extra=_gate(40, 90))
    res = forecast_user(inp)
    _ok(inp, res)
    by = {jf.summary.jar_code: jf.summary for jf in res.jars}
    dense, sparse = by["an_uong"], by["giai_tri"]
    assert dense.series_kind == "dense" and sparse.series_kind == "sparse"
    assert dense.show_probability and dense.p_shortfall is not None  # 60 >= 40: hũ dày vẫn hiện %
    assert not sparse.show_probability and sparse.p_shortfall is None  # 60 < 90: hũ thưa ẩn %
    assert sparse.p_shortfall_se is None
    # ẩn % không làm mất nhãn tin cậy và trạng thái hũ: trạng thái giống hệt khi không có cổng lịch sử
    ungated = forecast_user(with_config(inp, extra=_gate(0, 0)))
    ref = {jf.summary.jar_code: jf.summary for jf in ungated.jars}
    assert sparse.status == ref["giai_tri"].status
    assert sparse.confidence_band in ("low", "medium", "high")


def test_hu_thua_du_lich_su_tu_nguong_thi_hien_xac_suat():
    inp = with_config(inputs(_two_jars(90)), probability_enabled=True, extra=_gate(40, 90))
    res = forecast_user(inp)
    _ok(inp, res)
    assert all(jf.summary.show_probability for jf in res.jars)  # đúng bằng ngưỡng là đủ


@pytest.mark.parametrize(("n", "dense_shown", "sparse_shown"), [(47, True, False), (120, True, True)])
def test_hieu_chinh_mac_dinh_tai_khoan_lich_su_ngan_khong_thay_xac_suat_hu_thua(
    n, dense_shown, sparse_shown
):
    # BR-31 (#9), số đo ở docs/research/backtest-final.md: ở 47 ngày lịch sử dải 30 ngày của hũ thưa chỉ phủ 0,68 (cổng
    # [0,75; 0,85]) nên ẩn %, hũ dày phủ 0,78 nên vẫn hiện; tới 120 ngày hũ thưa phủ 0,77 thì hiện lại
    inp = with_config(inputs(_two_jars(n)), probability_enabled=True)
    res = forecast_user(inp)
    _ok(inp, res)
    by = {jf.summary.jar_code: jf.summary for jf in res.jars}
    assert (by["an_uong"].series_kind, by["giai_tri"].series_kind) == ("dense", "sparse")
    assert by["an_uong"].show_probability is dense_shown
    assert by["giai_tri"].show_probability is sparse_shown
    assert (by["giai_tri"].p_shortfall is None) is (not sparse_shown)


def test_chinh_nhanh_tu_lan_chay_cu_chua_co_nguong_lich_su_van_an_xac_suat():
    inp = with_config(inputs(_two_jars(60)), probability_enabled=True, extra=_gate(40, 90))
    prev = forecast_user(inp)
    old_cal = {
        k: ({kk: vv for kk, vv in v.items() if kk != "probability_min_history_days"}
            if isinstance(v, dict) else v)
        for k, v in prev.run.params["calibration"].items()
    }  # fmt: skip
    old = replace(prev, run=replace(prev.run, params={**prev.run.params, "calibration": old_cal}))
    res = update_forecast(inp, old, ["giai_tri"])
    s = next(jf.summary for jf in res.jars if jf.summary.jar_code == "giai_tri")
    assert not s.show_probability and s.p_shortfall is None


def test_xac_suat_hut_tang_khi_so_du_giam():
    ps = []
    for bal in (3_000_000, 1_500_000, 600_000):
        inp = with_config(
            inputs((jar("an_uong", n=60, seed=1, balance=bal),)),
            extra=PROB_ON,
            probability_enabled=True,
        )
        ps.append(forecast_user(inp).jars[0].summary.p_shortfall)
    assert ps[0] <= ps[1] <= ps[2] and ps[2] > ps[0]


def test_do_phu_du_lieu_va_nhan_tin_cay():
    full = CoverageInputs(
        income_vnd=10_000_000,
        spend_vnd=6_000_000,
        balance_start_vnd=1_000_000,
        balance_end_vnd=5_000_000,
    )
    res = forecast_user(inputs(coverage=full))
    assert res.run.data_coverage == 1.0 and "clamp" in res.run.params["data_coverage_formula"]
    low = CoverageInputs(
        income_vnd=10_000_000,
        spend_vnd=1_000_000,
        balance_start_vnd=1_000_000,
        balance_end_vnd=1_500_000,
    )
    res_low = forecast_user(inputs(coverage=low))
    assert res_low.run.data_coverage == 0.15 and res_low.run.confidence_label == "low"
    assert all(jf.summary.confidence_band == "low" for jf in res_low.jars)
    none = forecast_user(inputs(coverage=CoverageInputs(0, 0, 0, 0)))
    assert (
        none.run.data_coverage is None and none.run.confidence_label == "medium"
    )  # thiếu dữ kiện: không lên Cao


def test_nhom_cao_can_du_ngay_do_phu_va_hieu_chuan():
    cov = CoverageInputs(10_000_000, 6_000_000, 1_000_000, 5_000_000)
    j = jar("an_uong", n=90, seed=1, balance=900_000)
    ok = with_config(
        inputs((j,), coverage=cov), extra={"calibration": {"dense": {"probability_ok": True}}}
    )
    assert forecast_user(ok).run.confidence_label == "high"
    bad = with_config(
        inputs((j,), coverage=cov), extra={"calibration": {"dense": {"probability_ok": False}}}
    )
    assert forecast_user(bad).run.confidence_label == "medium"


# --- cổng khởi đầu lạnh ------------------------------------------------------------------------------------
def test_khoi_dau_lanh_uoc_luong_ban_dau():
    j = jar("an_uong", n=12, seed=1, balance=500_000, inflows=(salary(14),))
    inp = with_config(inputs((j,)), probability_enabled=True, extra=PROB_ON)
    res = forecast_user(inp)
    _ok(inp, res)
    s = res.jars[0].summary
    assert (
        res.run.is_initial_estimate
        and res.run.confidence_label == "low"
        and res.run.model == "cold_start_rules"
    )
    assert s.series_kind == "cold_start" and s.confidence_band == "low"
    assert not s.show_probability and s.p_shortfall is None  # kể cả khi cờ bật
    assert res.run.history_days == 12


def test_hu_it_lich_su_trong_tai_khoan_du_lich_su_la_cold_start_rieng():
    a = jar("an_uong", n=80, seed=1, balance=900_000)
    b = jar("moi", n=10, seed=2, balance=300_000, inflows=(salary(14, 1_000_000),))
    inp = inputs((a, b))
    res = forecast_user(inp)
    _ok(inp, res)
    assert not res.run.is_initial_estimate and res.run.history_days == 80
    kinds = {jf.summary.jar_code: jf.summary for jf in res.jars}
    assert kinds["moi"].series_kind == "cold_start" and kinds["moi"].confidence_band == "low"
    assert kinds["an_uong"].series_kind in ("dense", "sparse")
    assert res.run.params["jar_models"] == {"an_uong": "hurdle_calendar", "moi": "cold_start_rules"}


def test_nguong_cold_start_la_cau_hinh():
    j = jar("an_uong", n=30, seed=1)
    low = forecast_user(with_config(inputs((j,)), cold_start_min_days=21))
    high = forecast_user(with_config(inputs((j,)), cold_start_min_days=45))
    assert not low.run.is_initial_estimate and low.jars[0].summary.series_kind != "cold_start"
    assert high.run.is_initial_estimate and high.jars[0].summary.series_kind == "cold_start"


def test_khoi_dau_lanh_theo_ngan_sach_phan_bo():
    """Prior nhóm: hũ có phần lương lớn thì dự báo chi cao hơn; hũ tiết kiệm không có ngân sách chi thì chi bằng 0."""
    small = jar("a", n=0, spend=(), balance=0, inflows=(salary(14, 1_000_000),))
    big = jar("b", n=0, spend=(), balance=0, inflows=(salary(14, 6_000_000),))
    sav = jar("c", n=0, spend=(), balance=0, kind="saving", inflows=(salary(14, 6_000_000),))
    res = forecast_user(inputs((small, big, sav)))
    tot = [sum(d.spend_p50_vnd + d.spend_p90_vnd for d in jf.days) for jf in res.jars]
    assert tot[1] > tot[0] > 0 and tot[2] == 0
    assert res.run.history_days == 0 and res.run.is_initial_estimate


# --- chỉnh nhanh ------------------------------------------------------------------------------------------
def test_chinh_nhanh_cung_dau_vao_cho_dung_so_cua_forecast_user():
    inp = inputs()
    full = forecast_user(inp)
    upd = update_forecast(inp, full, ["giai_tri", "an_uong"])
    _ok(inp, upd, subset=True)
    assert [jf.summary.jar_code for jf in upd.jars] == ["giai_tri", "an_uong"]
    by = {jf.summary.jar_code: jf for jf in full.jars}
    for jf in upd.jars:
        assert jf == by[jf.summary.jar_code]  # cùng phân phối, cùng dãy ngẫu nhiên => y hệt


def test_chinh_nhanh_so_du_moi_dich_chuyen_dung_bang_chenh_lech_nho_crn():
    inp = inputs()
    full = forecast_user(inp)
    moved = replace(
        inp,
        jars=tuple(
            replace(j, balance_vnd=j.balance_vnd - 200_000) if j.code == "an_uong" else j
            for j in inp.jars
        ),
    )
    upd = update_forecast(moved, full, ["an_uong"])
    _ok(moved, upd, subset=True)
    old = next(jf for jf in full.jars if jf.summary.jar_code == "an_uong")
    new = upd.jars[0]
    for a, b in zip(old.days, new.days, strict=True):
        assert (
            a.balance_p10_vnd - b.balance_p10_vnd,
            a.balance_p50_vnd - b.balance_p50_vnd,
            a.balance_p90_vnd - b.balance_p90_vnd,
        ) == (200_000,) * 3
        assert (a.spend_p10_vnd, a.spend_p50_vnd, a.spend_p90_vnd) == (
            b.spend_p10_vnd,
            b.spend_p50_vnd,
            b.spend_p90_vnd,
        )
    assert new.summary.start_balance_vnd == old.summary.start_balance_vnd - 200_000
    assert upd.run.model == full.run.model


def test_chinh_nhanh_ngay_can_som_hon_khi_chi_them():
    inp = inputs((jar("an_uong", n=60, seed=1, balance=1_500_000),))
    full = forecast_user(inp)
    spent = replace(inp, jars=(replace(inp.jars[0], balance_vnd=1_500_000 - 600_000),))
    upd = update_forecast(spent, full, ["an_uong"])
    a, b = full.jars[0].summary.runout_date, upd.jars[0].summary.runout_date
    assert b is not None and (a is None or b < a)


def test_chinh_nhanh_hu_khong_co_trong_previous_hoac_inputs_thi_keyerror():
    inp = inputs()
    full = forecast_user(inp)
    with pytest.raises(KeyError):
        update_forecast(inp, full, ["khong_co"])
    only_one = replace(full, jars=full.jars[:1])
    with pytest.raises(KeyError):
        update_forecast(inp, only_one, ["giai_tri"])


def test_chinh_nhanh_thieu_trang_thai_roi_ve_ba_phan_vi():
    inp = inputs((jar("an_uong", n=60, seed=1, balance=900_000),))
    full = forecast_user(inp)
    stripped = replace(full, run=replace(full.run, params={}))
    upd = update_forecast(inp, stripped, ["an_uong"])
    _ok(inp, upd, subset=True)
    a, b = full.jars[0], upd.jars[0]
    assert [(d.spend_p10_vnd, d.spend_p50_vnd, d.spend_p90_vnd) for d in a.days] == [
        (d.spend_p10_vnd, d.spend_p50_vnd, d.spend_p90_vnd) for d in b.days
    ]
    assert (
        abs(a.days[-1].balance_p50_vnd - b.days[-1].balance_p50_vnd)
        < 0.35 * abs(a.days[0].balance_p50_vnd - a.days[-1].balance_p50_vnd) + 1
    )


def test_chinh_nhanh_sang_ngay_hom_sau_van_dat_hop_dong():
    inp = inputs()
    full = forecast_user(inp)
    nxt = replace(
        inp,
        app_date=APP_DATE + timedelta(days=1),
        horizon_days=29,
        payday_dates=tuple(d for d in inp.payday_dates if d > APP_DATE + timedelta(days=1)),
        jars=tuple(
            replace(
                j,
                history_start=j.history_start,
                daily_spend_vnd=(*j.daily_spend_vnd, 50_000),
                inflows=j.inflows,
                outflows=tuple(f for f in j.outflows),
            )
            for j in inp.jars
        ),
    )
    assert contract.check_inputs(nxt) == []
    upd = update_forecast(nxt, full, ["an_uong"])
    _ok(nxt, upd, subset=True)
    assert upd.jars[0].days[0].date == APP_DATE + timedelta(days=2)


# --- common random numbers -------------------------------------------------------------------------------
def test_hu_khac_khong_lam_doi_so_ngau_nhien_cua_hu_nay():
    base = inputs()
    other = replace(
        base,
        jars=tuple(
            replace(j, daily_spend_vnd=tuple(v + 1000 for v in j.daily_spend_vnd))
            if j.code == "giai_tri"
            else j
            for j in base.jars
        ),
    )
    a = next(jf for jf in forecast_user(base).jars if jf.summary.jar_code == "an_uong")
    b = next(jf for jf in forecast_user(other).jars if jf.summary.jar_code == "an_uong")
    assert a == b


def test_n_paths_khac_nhau_cho_cung_trung_vi_gan_nhau():
    inp = inputs((jar("an_uong", n=60, seed=1, balance=900_000),))
    a = forecast_user(with_config(inp, n_paths=1000)).jars[0].days[-1].balance_p50_vnd
    b = forecast_user(with_config(inp, n_paths=8000)).jars[0].days[-1].balance_p50_vnd
    assert abs(a - b) < 0.15 * abs(b) + 150_000


# --- ca biên ----------------------------------------------------------------------------------------------
def test_hu_khong_co_lich_su():
    j = jar("moi", n=0, spend=(), balance=250_000)
    inp = inputs((j,))
    res = forecast_user(inp)
    _ok(inp, res)
    assert res.run.history_days == 0 and res.run.is_initial_estimate


def test_lich_su_toan_0_du_dai():
    inp = inputs((jar("an_uong", n=60, spend=(0,) * 60, balance=100_000),))
    res = forecast_user(inp)
    _ok(inp, res)
    assert all(d.spend_p90_vnd == 0 for d in res.jars[0].days)
    assert res.jars[0].summary.runout_date is None


def test_horizon_qua_ky_luong_va_hai_ky_luong():
    j = jar(
        "an_uong",
        n=60,
        seed=1,
        balance=300_000,
        inflows=(salary(10, 2_000_000), salary(40, 2_000_000)),
    )
    inp = inputs((j,), horizon=60, payday_offset=10)
    assert len(inp.payday_dates) == 2
    res = forecast_user(inp)
    _ok(inp, res)
    assert len(res.jars[0].days) == 60


def test_horizon_ngan_hon_ngay_luong():
    inp = inputs((jar("an_uong", n=60, seed=1, balance=900_000),), horizon=7, payday_offset=20)
    res = forecast_user(inp)
    _ok(inp, res)
    assert res.jars[0].summary.days_to_payday == 20 and len(res.jars[0].days) == 7


def test_ngay_luong_la_ngay_mai_khong_co_ngay_nao_truoc_ky_luong():
    j = jar("an_uong", n=60, seed=1, balance=1_000, p=1.0)
    inp = with_config(inputs((j,), payday_offset=1), extra=PROB_ON, probability_enabled=True)
    res = forecast_user(inp)
    _ok(inp, res)
    assert (
        res.jars[0].summary.p_shortfall == 0.0
    )  # số dư chưa âm và không có ngày nào trước kỳ lương để hụt


def test_horizon_1_va_90():
    for h in (1, 90):
        inp = inputs(
            (jar("an_uong", n=60, seed=1, balance=900_000),),
            horizon=h,
            payday_offset=1 if h == 1 else 14,
        )
        res = forecast_user(inp)
        _ok(inp, res)
        assert len(res.jars[0].days) == h


def test_tham_so_ml_ghi_de_qua_extra_va_khoa_la_bi_tu_choi():
    inp = inputs((jar("an_uong", n=60, seed=1),))
    res = forecast_user(with_config(inp, extra={"ml": {"fit_window_days": 30}}))
    _ok(inp, res)
    with pytest.raises(ValueError):
        forecast_user(with_config(inp, extra={"ml": {"khong_co": 1}}))


def test_model_baseline_seasonal_naive_chon_duoc_qua_extra():
    inp = with_config(inputs((jar("an_uong", n=60, seed=1),)), extra={"model": "seasonal_naive"})
    res = forecast_user(inp)
    _ok(inp, res)
    assert res.run.model == "seasonal_naive"
    assert res.run.params["jar_state"]["an_uong"]["marginal"]["type"] == "seasonal_naive"
    upd = update_forecast(inp, res, ["an_uong"])
    assert upd.jars[0] == res.jars[0]
    with pytest.raises(ValueError):
        forecast_user(with_config(inp, extra={"model": "khong_co"}))


def test_rho_cau_hinh_ghi_de_hieu_chuan():
    inp = inputs((jar("an_uong", n=60, seed=1, balance=900_000),))
    a = forecast_user(with_config(inp, rho=0.0))
    b = forecast_user(with_config(inp, rho=0.8))
    assert (
        a.run.params["calibration"]["dense"]["rho"] == 0.0
        and b.run.params["calibration"]["dense"]["rho"] == 0.8
    )
    wa = a.jars[0].days[-1].balance_p90_vnd - a.jars[0].days[-1].balance_p10_vnd
    wb = b.jars[0].days[-1].balance_p90_vnd - b.jars[0].days[-1].balance_p10_vnd
    assert wb > wa  # tương quan dương giữa các ngày làm khoảng tổng rộng hơn


def test_cau_hinh_mac_dinh_khong_doi_kieu():
    assert isinstance(ForecastConfig().n_paths, int)
