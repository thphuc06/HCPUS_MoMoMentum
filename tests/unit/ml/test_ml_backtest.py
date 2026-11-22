"""Bộ sinh dữ liệu tổng hợp và khung backtest (chạy nhỏ để kiểm khói; số đo thật ở docs/research/backtest-phase-2.md)."""

from __future__ import annotations

import numpy as np
import pytest

from yofina_ml import contract, synth
from yofina_ml.backtest import calibrate as cal
from yofina_ml.backtest import common, report, studies
from yofina_ml.backtest import evaluate as ev
from yofina_ml.backtest.cli import probability_gate
from yofina_ml.synth.base import OBLIGATION_JAR, build_inputs
from yofina_ml.types import ForecastConfig

CASES = [(fam, cfg) for fam in synth.FAMILIES for cfg in synth.config_names(fam)]


def test_moi_ho_co_it_nhat_ba_cau_hinh_va_hai_ho_khac_nhau():
    assert set(synth.FAMILIES) == {"hurdle_lognormal", "shopping_sessions"}
    assert all(len(synth.config_names(f)) >= 3 for f in synth.FAMILIES)
    a = synth.generate("hurdle_lognormal", "office", 1)
    b = synth.generate("shopping_sessions", "grocer_office", 1)
    assert not np.array_equal(a.jar("an_uong").spend, b.jar("an_uong").spend)


@pytest.mark.parametrize(("fam", "cfg"), CASES)
def test_bo_sinh_tat_dinh_theo_seed_va_so_cai_nhat_quan(fam, cfg):
    a, b = synth.generate(fam, cfg, 5), synth.generate(fam, cfg, 5)
    c = synth.generate(fam, cfg, 6)
    for ja, jb in zip(a.jars, b.jars, strict=True):
        assert np.array_equal(ja.spend, jb.spend)
    assert any(not np.array_equal(x.spend, y.spend) for x, y in zip(a.jars, c.jars, strict=True))
    assert np.array_equal(a.obligation_paid, b.obligation_paid)
    # sổ cái: số dư_t - số dư_{t-1} = phần lương chia - chi (hoặc nghĩa vụ)
    for j in a.jars:
        bal = a.balances[j.code]
        out = a.obligation_paid if j.code == OBLIGATION_JAR else j.spend
        inflow = np.rint(a.salary_vnd * j.split_percent / 100.0).astype(np.int64)
        assert np.array_equal(np.diff(bal), (inflow - out)[1:])
        assert (j.spend >= 0).all()
    assert abs(sum(j.split_percent for j in a.jars) - 100) < 1e-9
    assert a.break_index is not None and 0 < a.break_index < a.n_days


@pytest.mark.parametrize(("fam", "cfg"), CASES)
def test_dau_vao_dung_tu_persona_qua_bo_kiem_hop_dong(fam, cfg):
    p = common.persona(fam, cfg, 7)
    for o in (25, 120, 250):
        inp = build_inputs(p, o, 30, ForecastConfig(n_paths=200, seed=1))
        assert contract.check_inputs(inp) == []
        assert len(inp.jars) == 7 and inp.payday_day == p.payday_day


def test_hai_ho_khac_hat_nhan_nhau_ve_cau_truc_ngay_chi():
    """Họ (ii) có chi theo phiên (khoảng cách đều), họ (i) theo xác suất theo ngày: hũ ăn uống có ngày 0 khác bản chất."""
    a = synth.generate("hurdle_lognormal", "office", 3).jar("an_uong").spend
    b = synth.generate("shopping_sessions", "night_shift", 3).jar("an_uong").spend
    assert (a == 0).mean() < 0.1 < (b == 0).mean()


def test_evaluate_va_summarize_chay_nho():
    ps = [
        common.persona("hurdle_lognormal", "office", 201),
        common.persona("shopping_sessions", "grocer_office", 201),
    ]
    rows = ev.evaluate(ps, n_paths=200, first_origin=200, step=40)
    assert rows and {r["family"] for r in rows} == {"hurdle_lognormal", "shopping_sessions"}
    s = ev.summarize(rows)
    assert {"hurdle_lognormal", "shopping_sessions", "all"} == set(s["by_family"])
    dense = s["by_family"]["all"].get("spending")
    assert dense and 0 < dense["all"]["rel_pl_product"] < 3
    assert 0 <= dense["all"]["cov_cum30"] <= 1
    assert "|" in report.render_daily(s) and "|" in report.render_cum(s)


def test_hieu_chinh_chon_cap_gan_muc_tieu_nhat_tren_luoi():
    ps = [common.persona("hurdle_lognormal", "office", 101)]
    units = cal.collect_units(ps, [100, 160, 220])
    assert units and {u.kind for u in units} <= {"dense", "sparse", "cold_start"}
    res = (
        cal.calibrate([u for u in units if u.kind == "dense"], n_paths=300)
        if any(u.kind == "dense" for u in units)
        else {"kinds": {}}
    )
    for v in res["kinds"].values():
        assert 0 <= v["rho"] < 1 and v["level_sigma"] >= 0
        assert len(v["cov_after"]) == 3
    grid = {
        (0.0, 0.0): np.array([0.5, 0.5, 0.5]),
        (0.2, 0.3): np.array([0.8, 0.8, 0.8]),
        (0.4, 0.3): np.array([0.9, 0.9, 0.9]),
    }
    assert cal.choose(grid) == (0.2, 0.3)
    assert cal.objective(np.array([0.8, 0.8, 0.8])) == 0


def test_cong_xac_suat_chi_bat_khi_do_phu_trong_dai_va_co_ky_nang():
    ok = [
        {"family": f, "bucket": "dense", "cum30_in": 1.0 if i % 5 else 0.0}
        for f in ("a", "b")
        for i in range(100)
    ]
    short = [
        {"bucket": "dense", "p": 0.0 if i % 2 else 1.0, "event": 0.0 if i % 2 else 1.0}
        for i in range(100)
    ]
    g = probability_gate(ok, short)
    assert g["dense"]["ok"] and g["dense"]["cov30"]["all"] == pytest.approx(0.8)
    bad = [{"family": "a", "bucket": "dense", "cum30_in": 1.0}] * 100
    assert not probability_gate(bad, short)["dense"]["ok"]
    useless = [{"bucket": "dense", "p": 0.5, "event": float(i % 2)} for i in range(100)]
    assert not probability_gate(ok, useless)["dense"]["ok"]  # không hơn tần suất chung


def test_do_tin_cay_xac_suat_hut():
    rows = [
        {"p": p, "event": float(e)}
        for p, e in [(0.05, 0), (0.05, 0), (0.95, 1), (0.95, 1), (0.5, 1), (0.5, 0)]
    ]
    r = ev.reliability(rows)
    assert r["n"] == 6 and 0 < r["brier"] < r["brier_climatology"]
    assert ev.reliability([]) == {}


def test_khao_sat_do_dai_lich_su_va_ablation_chay_nho():
    ps = [common.persona("shopping_sessions", "student_allowance", 201)]
    sh = studies.short_history(ps, lengths=(14, 60), windows=2)
    assert set(sh) == {14, 60} and set(sh[14]) == {
        "hurdle_calendar",
        "seasonal_naive",
        "cold_start_rules",
    }
    assert sh[14]["seasonal_naive"]["rel_pl"] == pytest.approx(1.0)
    ab = studies.ablation(ps, step=60)
    assert set(ab) == set(studies.ABLATIONS)
    assert "|" in report.render_short(sh) and "|" in report.render_ablation(ab)
