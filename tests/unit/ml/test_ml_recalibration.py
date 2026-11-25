"""Hiệu chỉnh lại sau Monte Carlo (#25): PAV cho `p_shortfall`, CQR bất đối xứng cho dải số dư hũ dày, hũ thưa không nêu ngày cạn.
Mọi thứ sau công tắc `recalibrate` của hiệu chỉnh; số đo ở docs/research/backtest-final.md mục "Hiệu chỉnh CQR và PAV"."""

from __future__ import annotations

import pytest
from ml_helpers import inputs, jar, with_config

from yofina_ml import contract
from yofina_ml.api import forecast_user
from yofina_ml.recalibration import CQRBand, apply_cqr, fit_cqr, fit_isotonic


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
    # ngoài khoảng giữ giá trị đầu mút
    assert iso(0.0) == pytest.approx(0.5) and iso(1.0) == pytest.approx(1.0)


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


# --- CQR bất đối xứng ----------------------------------------------------------------------------------------
def test_cqr_hoc_rieng_do_lech_duoi_va_tren_bang_bac_thu_tu_hieu_chinh():
    # Ngày 1, chi TB 1 (điểm không bị chuẩn hóa), dải [0; 10], mỗi đuôi 0,2: hạng ceil((9 + 1) x 0,8) = 8 trong 9 điểm.
    #   điểm dưới P10 - y = 4, 2, -1, -3, -5, -7, -9, -11, -14 -> sắp tăng, thứ 8 là 2
    #   điểm trên y - P90 = -14, -12, -9, -7, -5, -3, -1, 1, 4 -> thứ 8 là 1
    # Ngày 2, chi TB 500 nên đơn vị là 500 x 2 = 1.000, dải [1.000; 3.000], 4 điểm: hạng ceil(5 x 0,8) = 4 (lớn nhất).
    #   điểm dưới (1.000 - y) / 1.000 = 1; -0,5; -1,5; -2,5 -> 1;  điểm trên (y - 3.000) / 1.000 = -3; -1,5; -0,5; 0,5 -> 0,5
    y1 = [-4, -2, 1, 3, 5, 7, 9, 11, 14]
    y2 = [0, 1_500, 2_500, 3_500]
    band = fit_cqr(
        h=[1] * 9 + [2] * 4,
        lower=[0] * 9 + [1_000] * 4,
        upper=[10] * 9 + [3_000] * 4,
        truth=y1 + y2,
        scale=[1.0] * 9 + [500.0] * 4,
        tail=0.2,
    )
    assert band.h == (1, 2)
    assert band.lo == pytest.approx((2.0, 1.0)) and band.hi == pytest.approx((1.0, 0.5))


def test_cqr_doi_dai_theo_chi_tb_nhan_so_ngay_va_giu_thu_tu_phan_vi():
    band = CQRBand(h=(1, 2), lo=(2.0, -10.0), hi=(1.0, 0.5))
    p10, p90 = apply_cqr(band, [100, 100, 100], [150, 150, 150], [200, 200, 200], scale=10.0)
    # ngày 1: đơn vị 10 -> P10 100 - 20 = 80, P90 200 + 10 = 210
    # ngày 2: đơn vị 20 -> P10 100 + 200 = 300 vượt P50 nên kẹp về 150, P90 200 + 10 = 210
    # ngày 3 (sau nút cuối, giữ hệ số của ngày 2): đơn vị 30 -> P10 kẹp 150, P90 200 + 15 = 215
    assert list(p10) == [80, 150, 150] and list(p90) == [210, 210, 215]
