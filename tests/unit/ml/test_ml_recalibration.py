"""Hiệu chỉnh lại sau Monte Carlo (#25): PAV cho `p_shortfall`, CQR bất đối xứng cho dải số dư hũ dày, hũ thưa không nêu ngày cạn.
Mọi thứ sau công tắc `recalibrate` của hiệu chỉnh; số đo ở docs/research/backtest-final.md mục "Hiệu chỉnh CQR và PAV"."""

from __future__ import annotations

import pytest
from ml_helpers import inputs, jar, with_config

from yofina_ml import contract
from yofina_ml.api import forecast_user
from yofina_ml.recalibration import fit_isotonic


def _cal(recalibrate: bool, **kinds) -> dict:
    gate_off = {k: {"probability_min_history_days": 0} for k in ("dense", "sparse")}
    for k, v in kinds.items():
        gate_off[k] = {**gate_off[k], **v}
    return {"calibration": {"recalibrate": recalibrate, **gate_off}}


def _run(inp, recalibrate: bool, **kinds):
    inp = with_config(inp, probability_enabled=True, extra=_cal(recalibrate, **kinds))
    res = forecast_user(inp)
    assert contract.check_result(inp, res) == []
    return res


# --- PAV ---------------------------------------------------------------------------------------------------
def test_pav_gop_khoi_vi_pham_thu_tu_thanh_trung_binh():
    # ví dụ tính tay: 0,1 -> 1 và 0,2 -> 0 ngược chiều nên gộp thành 0,5; hai điểm sau đã tăng dần
    iso = fit_isotonic([0.1, 0.2, 0.3, 0.4], [1.0, 0.0, 1.0, 1.0])
    assert [iso(p) for p in (0.1, 0.2, 0.3, 0.4)] == pytest.approx([0.5, 0.5, 1.0, 1.0])
    assert iso(0.0) == pytest.approx(0.5) and iso(1.0) == pytest.approx(1.0)  # ngoài khoảng giữ giá trị đầu mút


def test_pav_xac_suat_hut_hu_day_qua_bang_hieu_chinh_va_trang_thai_theo_so_moi():
    inp = inputs((jar("an_uong", n=60, seed=1, balance=3_000_000),))
    flat = {"p_isotonic": {"x": [0.0, 1.0], "y": [0.6, 0.6]}}
    raw = _run(inp, False, dense=flat).jars[0].summary
    assert raw.series_kind == "dense" and raw.p_shortfall < 0.2 and raw.status == "ok"
    s = _run(inp, True, dense=flat).jars[0].summary
    assert s.p_shortfall == 0.6 and s.status == "short"


def test_pav_khong_cham_so_du_am_da_hut_chac_chan():
    inp = inputs((jar("an_uong", n=60, seed=1, balance=-50_000),))
    s = _run(inp, True, dense={"p_isotonic": {"x": [0.0, 1.0], "y": [0.3, 0.3]}}).jars[0].summary
    assert s.p_shortfall == 1.0 and s.status == "short"
