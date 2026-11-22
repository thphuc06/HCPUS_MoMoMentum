"""Thành phần của gói ML: lịch, biên, mô hình, ACI, Monte Carlo, cổng chất lượng, hiệu chỉnh, ràng buộc gói."""

from __future__ import annotations

import ast
import re
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest
from conftest import REPO

from yofina_ml import daycal
from yofina_ml.aci import horizon_bins, run_aci
from yofina_ml.calibration import (
    SeriesCalibration,
    calibrated_config,
    default_calibration,
    resolve_calibration,
)
from yofina_ml.marginals import (
    ColdStartMarginal,
    HurdleMarginal,
    SeasonalNaiveMarginal,
    marginal_from_state,
    quantile_table,
)
from yofina_ml.models import (
    ColdStartRulesModel,
    HurdleCalendarModel,
    SeasonalNaiveModel,
    select_model,
)
from yofina_ml.montecarlo import (
    SimSpec,
    draw_paths,
    jar_seed_sequence,
    simulate_jar,
    summarize_paths,
)
from yofina_ml.params import MLParams
from yofina_ml.quality import band_for, data_coverage, min_band, status_for
from yofina_ml.types import CoverageInputs, ForecastConfig, ForecastModel

ML = REPO / "ml" / "yofina_ml"
START = date(2026, 1, 1)


# --- lịch ------------------------------------------------------------------------------------------------
def test_ngay_luong_ket_cuoi_thang_ngan_va_so_ngay_ke_tu_luong():
    assert daycal.payday_in_month(31, 2026, 2) == date(2026, 2, 28)
    assert daycal.latest_payday(5, date(2026, 11, 21)) == date(2026, 11, 5)
    assert daycal.latest_payday(5, date(2026, 11, 4)) == date(2026, 10, 5)
    assert daycal.latest_payday(31, date(2026, 3, 1)) == date(2026, 2, 28)
    f = daycal.make_features([date(2026, 11, 5), date(2026, 11, 12), date(2026, 11, 13)], 5, 7)
    assert f.since_payday.tolist() == [0, 7, 8]
    assert f.early.tolist() == [True, True, False]
    sat = daycal.make_features([date(2026, 11, 21)], 5, 7)  # thứ bảy, nửa sau kỳ lương
    assert sat.weekend.tolist() == [True] and sat.cell.tolist() == [2]


# --- biên và mô hình --------------------------------------------------------------------------------------
def _hist(n=120, seed=0):
    rng = np.random.default_rng(seed)
    y = np.where(
        rng.random(n) < 0.7, np.round(40_000 * np.exp(0.5 * rng.standard_normal(n)), -3), 0.0
    )
    f = daycal.date_range_features(START, n, 5, 7)
    return y, f


def test_hurdle_phan_vi_khong_giam_khong_am_va_state_khu_hoi_khong_doi():
    y, f = _hist()
    m = HurdleCalendarModel(MLParams(), 5).fit(y, f)
    fut = daycal.date_range_features(START + timedelta(days=120), 30, 5, 7)
    levels = np.array([0.05, 0.1, 0.3, 0.5, 0.7, 0.9, 0.99])
    tab = quantile_table(m, fut, levels)
    assert (tab >= 0).all() and (np.diff(tab, axis=1) >= -1e-9).all()
    m2 = marginal_from_state(m.state())
    assert isinstance(m2, HurdleMarginal)
    assert np.array_equal(quantile_table(m2, fut, levels), tab)


def test_hurdle_xac_suat_co_chi_khop_tan_suat_va_trung_vi_khong_khi_thua():
    y = np.zeros(100)
    y[::10] = 50_000  # 10% ngày có chi
    f = daycal.date_range_features(START, 100, 5, 7)
    m = HurdleCalendarModel(MLParams(cell_shrink_days=None, halflife_days=None), 5).fit(y, f)
    fut = daycal.date_range_features(START + timedelta(days=100), 14, 5, 7)
    tab = quantile_table(m, fut, np.array([0.5, 0.95]))
    assert (tab[:, 0] == 0).all()  # trung vị 0
    assert (tab[:, 1] == 50_000).all()  # mọi khoản có chi đều 50.000


def test_hurdle_giu_dung_hieu_ung_lich_khi_co_du_lieu():
    n = 240
    f = daycal.date_range_features(START, n, 5, 7)
    y = np.where(f.weekend, 100_000.0, 0.0)  # chỉ chi vào cuối tuần
    p = (
        HurdleCalendarModel(MLParams(), 5).fit(y, f).p
    )  # mặc định co ô về xác suất chung (kappa = 20)
    assert min(p[2], p[3]) > 0.45 and max(p[0], p[1]) < 0.15
    raw = HurdleCalendarModel(MLParams(cell_shrink_days=None), 5).fit(y, f).p
    assert min(raw[2], raw[3]) > 0.8 and max(raw[0], raw[1]) < 0.1


def test_hurdle_khong_lech_ve_tong_khi_co_hieu_ung_cuoi_tuan_va_dau_ky_luong():
    """Quá trình dừng có hiệu ứng nhân theo ô (cuối tuần 1,3; nửa đầu kỳ lương 1,6): tổng kỳ vọng 30 ngày của mô hình phải
    gần tổng thật (mô hình số tiền theo hệ số ô, không để ô hiếm rơi về phân phối chung)."""
    rng = np.random.default_rng(0)
    n = 420
    f = daycal.date_range_features(START, n, 5, 7)
    true_mean = np.where(f.weekend, 1.3, 1.0) * np.where(f.early, 1.6, 1.0) * 40_000
    sig = 0.45
    ratios = []
    for _ in range(12):
        amt = true_mean / np.exp(0.5 * sig**2) * np.exp(sig * rng.standard_normal(n))
        y = np.where(rng.random(n) < 0.97, amt, 0.0)
        for o in range(120, 380, 20):
            m = HurdleCalendarModel(MLParams(), 5).fit(y[:o], f[:o])
            cells = f.cell[o + 1 : o + 31]
            # trung bình của hàm phân vị = tích phân (quy tắc hình thang) trên lưới
            g = m.amt
            mean_amt = (g.sum(axis=1) - 0.5 * (g[:, 0] + g[:, -1])) / (g.shape[1] - 1)
            ratios.append(
                (m.p[cells] * mean_amt[cells]).sum() / (0.97 * true_mean[o + 1 : o + 31]).sum()
            )
    assert 0.95 < float(np.mean(ratios)) < 1.05


def test_model_cam_vao_duoc_theo_giao_dien_hop_dong():
    for cls in (HurdleCalendarModel, SeasonalNaiveModel, ColdStartRulesModel):
        assert isinstance(cls(MLParams(), 5), ForecastModel)
    y, _ = _hist()
    m = HurdleCalendarModel(MLParams(), 5)
    fut = tuple(START + timedelta(days=120 + i) for i in range(7))
    tab = m.predict(tuple(int(v) for v in y), START, fut, (), (0.1, 0.5, 0.9))
    assert len(tab) == 7 and all(len(r) == 3 for r in tab)
    assert all(isinstance(v, int) and 0 <= r[0] <= r[1] <= r[2] for r in tab for v in r)


def test_seasonal_naive_lap_lai_gia_tri_cung_thu_tuan_truoc():
    n = 70
    f = daycal.date_range_features(START, n, 5, 7)
    y = (np.arange(n) % 7 + 1) * 10_000.0  # mẫu tuần cố định
    m = SeasonalNaiveModel(MLParams(), 5).fit(y, f)
    assert isinstance(m, SeasonalNaiveMarginal)
    fut = daycal.date_range_features(START + timedelta(days=n), 14, 5, 7)
    tab = quantile_table(m, fut, np.array([0.5]))[:, 0]
    want = ((np.arange(n, n + 14) % 7) + 1) * 10_000.0
    assert np.allclose(tab, want)  # sai khác mùa vụ toàn 0 nên khoảng bằng điểm
    assert isinstance(marginal_from_state(m.state()), SeasonalNaiveMarginal)


def test_khoi_dau_lanh_theo_ngan_sach_va_pha_du_lieu_rieng():
    y, f = _hist(10)
    prm = MLParams()
    none = ColdStartRulesModel(prm, 5, kind="spending", monthly_budget_vnd=0).fit(
        np.zeros(5), f[:5]
    )
    assert none.p == 0 and quantile_table(none, f[:3], np.array([0.5, 0.9])).sum() == 0
    a = ColdStartRulesModel(prm, 5, kind="spending", monthly_budget_vnd=3_000_000).fit(
        np.zeros(0), f[:0]
    )
    b = ColdStartRulesModel(prm, 5, kind="spending", monthly_budget_vnd=6_000_000).fit(
        np.zeros(0), f[:0]
    )
    assert isinstance(a, ColdStartMarginal) and b.median_vnd > a.median_vnd
    sav = ColdStartRulesModel(prm, 5, kind="saving", monthly_budget_vnd=6_000_000).fit(
        np.zeros(0), f[:0]
    )
    assert sav.p == 0
    own = ColdStartRulesModel(prm, 5, kind="spending", monthly_budget_vnd=3_000_000).fit(
        y * 20, f[:10]
    )
    assert own.median_vnd > a.median_vnd  # dữ liệu chi nhiều hơn prior kéo mô hình lên
    assert isinstance(marginal_from_state(a.state()), ColdStartMarginal)


def test_chon_mo_hinh_theo_so_ngay_lich_su():
    prm = MLParams()
    kw = {
        "cold_start_min_days": 21,
        "params": prm,
        "payday_day": 5,
        "kind": "spending",
        "monthly_budget_vnd": 1e6,
    }
    assert select_model(20, **kw).name == "cold_start_rules"
    assert select_model(21, **kw).name == "hurdle_calendar"
    assert select_model(60, override="seasonal_naive", **kw).name == "seasonal_naive"
    assert (
        select_model(5, override="seasonal_naive", **kw).name == "cold_start_rules"
    )  # cổng lạnh thắng baseline
    with pytest.raises(ValueError):
        select_model(60, override="x", **kw)


# --- ACI --------------------------------------------------------------------------------------------------
class _FixedNarrow:
    """Biên giả luôn hẹp hơn thực tế: mọi giá trị nằm trong [0, 1] nhưng dữ liệu lớn hơn nhiều."""

    name = "narrow"

    def ppf(self, u, f, p=None):
        return np.broadcast_to(u * 1.0, u.shape).astype(float)

    def state(self):
        return {}


class _FixedWide(_FixedNarrow):
    def ppf(self, u, f, p=None):
        return np.where(u > 0.5, 1e9, 0.0)


def _aci_data(n=150):
    rng = np.random.default_rng(1)
    return rng.uniform(1_000, 2_000, n), daycal.date_range_features(START, n + 40, 5, 7)


def test_aci_gamma_0_hoac_lich_su_ngan_khong_hieu_chinh():
    y, f = _aci_data()
    prm = MLParams()
    a = run_aci(y, f, lambda yy, ff: _FixedNarrow(), prm, 0.0, 0.2)
    assert (a == 0.2).all()
    b = run_aci(y[:20], f, lambda yy, ff: _FixedNarrow(), prm, 0.01, 0.2)
    assert (b == 0.2).all()
    c = run_aci(np.zeros(100), f, lambda yy, ff: _FixedNarrow(), prm, 0.01, 0.2)
    assert (c == 0.2).all()  # chuỗi toàn 0 không có gì để hiệu chỉnh


def test_aci_khoang_qua_hep_thi_alpha_giam_va_bi_kep_o_san():
    y, f = _aci_data()
    prm = MLParams()
    a = run_aci(y, f, lambda yy, ff: _FixedNarrow(), prm, 0.01, 0.2)
    assert (a < 0.2).all() and (a >= prm.aci_alpha_min - 1e-12).all()
    big = run_aci(y, f, lambda yy, ff: _FixedNarrow(), prm, 0.5, 0.2)
    assert (big == prm.aci_alpha_min).all()  # gamma lớn: chạm sàn, không nở vô hạn


def test_aci_khoang_qua_rong_thi_alpha_tang_va_bi_kep_o_tran():
    y, f = _aci_data()
    prm = MLParams()
    a = run_aci(y, f, lambda yy, ff: _FixedWide(), prm, 0.05, 0.2)
    assert (a > 0.2).all() and (a <= prm.aci_alpha_max + 1e-12).all()


def test_aci_gan_dung_muc_tieu_khi_bien_dung():
    rng = np.random.default_rng(0)
    n = 400
    f = daycal.date_range_features(START, n + 40, 5, 7)
    y = np.where(
        rng.random(n) < 0.9, np.round(40_000 * np.exp(0.5 * rng.standard_normal(n)), -3), 0.0
    )
    prm = replace(MLParams(), aci_lookback_days=300)
    model = HurdleCalendarModel(prm, 5)
    a = run_aci(y, f, model.fit, prm, 0.01, 0.2)
    assert ((a > 0.08) & (a < 0.45)).all()


def test_nhom_horizon():
    assert horizon_bins(np.array([1, 7, 8, 14, 15, 30]), (7, 14)).tolist() == [0, 0, 1, 1, 2, 2]


# --- Monte Carlo -----------------------------------------------------------------------------------------
def _spec(balance=500_000.0, sparse=False, ranged=(), n_days=30, med=60_000.0):
    f = daycal.date_range_features(START, n_days, 5, 7)
    y, fh = _hist(100, seed=3)
    marg = HurdleCalendarModel(MLParams(), 5).fit(y * (med / 40_000), fh)
    return SimSpec(balance, marg, f, sparse, np.zeros(n_days), np.zeros(n_days), tuple(ranged), 15)


def test_hat_giong_tat_dinh_theo_seed_ngay_goc_ma_hu():
    a = jar_seed_sequence(7, date(2026, 11, 21), "an_uong").generate_state(4)
    assert (a == jar_seed_sequence(7, date(2026, 11, 21), "an_uong").generate_state(4)).all()
    for other in (
        jar_seed_sequence(8, date(2026, 11, 21), "an_uong"),
        jar_seed_sequence(7, date(2026, 11, 22), "an_uong"),
        jar_seed_sequence(7, date(2026, 11, 21), "di_chuyen"),
    ):
        assert (a != other.generate_state(4)).any()
    assert (
        jar_seed_sequence(None, date(2026, 11, 21), "x").generate_state(2)
        == jar_seed_sequence(0, date(2026, 11, 21), "x").generate_state(2)
    ).all()


def test_so_ngau_nhien_khong_phu_thuoc_so_du_hay_lich():
    ss = jar_seed_sequence(1, date(2026, 11, 21), "a")
    s1 = _spec(balance=100.0)
    s2 = replace(_spec(balance=9e9), inflow=np.ones(30) * 5.0)
    d1, d2 = draw_paths(s1, 0.3, 500, ss), draw_paths(s2, 0.3, 500, ss)
    assert np.array_equal(d1.spend, d2.spend) and np.array_equal(d1.xi, d2.xi)


def test_ar1_copula_tao_tuong_quan_giua_cac_ngay_va_rho_0_la_doc_lap():
    ss = jar_seed_sequence(1, date(2026, 11, 21), "a")
    spec = _spec(med=40_000.0)
    dep = draw_paths(spec, 0.8, 4000, ss).spend
    ind = draw_paths(spec, 0.0, 4000, ss).spend
    r = lambda x: np.corrcoef(x[:, 5], x[:, 6])[0, 1]  # noqa: E731
    assert r(dep) > 0.4 and abs(r(ind)) < 0.08
    assert dep.sum(1).std() > ind.sum(1).std() * 1.3  # phương sai tổng lớn hơn khi tương quan dương


def test_he_so_muc_lam_rong_khoang_tong_nhung_giu_trung_binh():
    ss = jar_seed_sequence(1, date(2026, 11, 21), "a")
    spec = _spec()
    base = simulate_jar(spec, SeriesCalibration(0.0, 0.0, False), 4000, ss)
    wide = simulate_jar(spec, SeriesCalibration(0.0, 0.4, False), 4000, ss)
    assert wide.balance_p90[-1] - wide.balance_p10[-1] > base.balance_p90[-1] - base.balance_p10[-1]
    from yofina_ml.montecarlo import balance_from_draws

    d = draw_paths(spec, 0.0, 4000, ss)
    m0 = balance_from_draws(spec, d, 0.0)[:, -1].mean()
    m1 = balance_from_draws(spec, d, 0.4)[:, -1].mean()
    assert (
        abs(m1 - m0) < 0.03 * abs(spec.balance_vnd - m0) + 5_000
    )  # trung bình chi gần như không đổi (nhân tử có kỳ vọng 1)


def test_hu_thua_mo_phong_hurdle_truc_tiep_cho_xac_suat_co_chi_dung():
    n = 200
    f = daycal.date_range_features(START, n, 5, 7)
    y = np.zeros(n)
    y[::20] = 300_000
    marg = HurdleCalendarModel(MLParams(), 5).fit(y, f)
    spec = SimSpec(
        0.0,
        marg,
        daycal.date_range_features(START, 30, 5, 7),
        True,
        np.zeros(30),
        np.zeros(30),
        (),
        15,
    )
    sp = draw_paths(spec, 0.5, 6000, jar_seed_sequence(1, date(2026, 11, 21), "t")).spend
    freq = (sp > 0).mean()
    assert 0.03 < freq < 0.09  # xác suất posterior ~ 5%
    assert np.allclose(sp[sp > 0], 300_000.0)


def test_tom_tat_xac_suat_hut_ngay_can_va_phan_vi_so_du():
    spec = _spec(balance=300_000.0)
    bal = np.tile(np.linspace(300_000, -300_000, 30), (100, 1))
    s = summarize_paths(bal, replace(spec, window=20), 0.0)
    assert s.p_shortfall == 1.0 and s.p_shortfall_se == 0.0
    assert s.runout_index == int(np.nonzero(np.linspace(300_000, -300_000, 30) <= 0)[0][0])
    assert (s.balance_p10 == s.balance_p50).all()
    spec0 = replace(spec, window=0)
    assert summarize_paths(bal, spec0, 0.0).p_shortfall == 0.0
    assert summarize_paths(bal, replace(spec, balance_vnd=-1.0), 0.0).p_shortfall == 1.0


# --- chất lượng, hiệu chỉnh, tham số -------------------------------------------------------------------------
def test_do_phu_du_lieu_cong_thuc_va_kep():
    assert data_coverage(None) is None and data_coverage(CoverageInputs(0, 5, 0, 0)) is None
    assert data_coverage(CoverageInputs(100, 80, 10, 10)) == 0.8
    assert data_coverage(CoverageInputs(100, 300, 0, 0)) == 1.0
    assert data_coverage(CoverageInputs(100, 0, 500, 0)) == 0.0
    assert data_coverage(CoverageInputs(3, 1, 0, 0)) == 0.333


def test_nhan_tin_cay_theo_luat():
    cfg, prm = ForecastConfig(), MLParams()
    assert band_for(10, 0.9, True, cfg, prm) == "low"
    assert band_for(40, 0.2, True, cfg, prm) == "low"
    assert band_for(40, None, True, cfg, prm) == "medium"
    assert band_for(40, 0.9, True, cfg, prm) == "medium"
    assert band_for(90, 0.9, True, cfg, prm) == "high"
    assert band_for(90, 0.9, False, cfg, prm) == "medium"
    assert min_band("high", "low") == "low" and min_band("medium", "high") == "medium"


def test_trang_thai_theo_hai_nguong():
    cfg = ForecastConfig()
    assert [status_for(p, cfg) for p in (0.0, 0.19, 0.2, 0.49, 0.5, 1.0)] == [
        "ok",
        "ok",
        "tight",
        "tight",
        "short",
        "short",
    ]


def test_hieu_chinh_mac_dinh_hop_le_va_ghi_de():
    cal = default_calibration()
    for k in ("dense", "sparse", "cold_start"):
        c = cal.for_kind(k)
        assert 0 <= c.rho < 1 and c.level_sigma >= 0
    cfg = ForecastConfig(extra={"calibration": {"dense": {"rho": 0.55}}}, rho=None)
    assert resolve_calibration(cfg).dense.rho == 0.55
    assert resolve_calibration(cfg).sparse == cal.sparse
    assert resolve_calibration(ForecastConfig(rho=0.7)).cold_start.rho == 0.7
    assert calibrated_config(seed=3).probability_enabled == cal.dense.probability_ok
    assert calibrated_config(seed=3).seed == 3


def test_params_ghi_de_va_khoa_la():
    assert MLParams.from_extra({"ml": {"early_days": 5, "aci_bins": [5, 10]}}).aci_bins == (5, 10)
    assert (
        MLParams.from_extra({"ml": {"cold_spend_ratio": {"saving": 0.1}}}).cold_spend_ratio[
            "spending"
        ]
        == 0.85
    )
    with pytest.raises(ValueError):
        MLParams.from_extra({"ml": {"sai_ten": 1}})


# --- ràng buộc của gói sản phẩm --------------------------------------------------------------------------------
PRODUCT_FILES = sorted(
    p for p in ML.rglob("*.py") if not {"backtest", "synth"} & set(p.relative_to(ML).parts)
)
ALLOWED = {"numpy", "scipy", "yofina_ml"}


def _imports(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.add(node.module.split(".")[0])
    return out


@pytest.mark.parametrize("path", PRODUCT_FILES, ids=lambda p: str(p.relative_to(ML)))
def test_ma_san_pham_chi_phu_thuoc_numpy_scipy_va_thu_vien_chuan(path):
    import sys

    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    extra = _imports(path) - stdlib - ALLOWED
    assert not extra, f"{path.name} import ngoài numpy/scipy: {extra}"
    text = path.read_text(encoding="utf-8")
    assert not re.search(
        r"\b(date\.today|datetime\.now|datetime\.utcnow|time\.time)\(", text
    )  # ADR-0003
    assert "yofina_ml.backtest" not in text and "yofina_ml.synth" not in text


def test_ma_san_pham_khong_co_so_persona_demo():
    for p in PRODUCT_FILES:
        text = p.read_text(encoding="utf-8").lower()
        for word in ("minh", "khoa ", "figma", "23/11"):
            assert word not in text.replace("khoa học", ""), f"{p.name}: {word}"
