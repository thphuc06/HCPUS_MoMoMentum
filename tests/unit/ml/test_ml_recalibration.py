"""Hiệu chỉnh lại sau Monte Carlo (#25): PAV cho `p_shortfall`, CQR bất đối xứng cho dải số dư hũ dày, hũ thưa không nêu ngày cạn.
Mọi thứ sau công tắc `recalibrate` của hiệu chỉnh; số đo ở docs/research/backtest-final.md mục "Hiệu chỉnh CQR và PAV"."""

from __future__ import annotations

from dataclasses import replace

import pytest
from ml_helpers import inputs, jar, with_config

from yofina_ml import contract
from yofina_ml.api import forecast_user, runout_date_shown, update_forecast
from yofina_ml.backtest import recalibrate as recal
from yofina_ml.calibration import KINDS, calibration_from_dict
from yofina_ml.calibration import default as _default
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


def test_hieu_chinh_mac_dinh_hai_p_tho_khac_nhau_cua_hu_day_ra_hai_phan_tram_khac_nhau():
    # Bảng PAV hũ dày của lần sinh đầu (#25) có đoạn phẳng: p thô 0,311 đến 0,405 đều thành 0,306, nên what-if đổi số dư
    # trong đoạn đó báo % không đổi. Hiệu chỉnh mặc định (tệp sinh lại) không được làm mất khác biệt này.
    raw, pub = [], []
    for balance in (560_000, 580_000):
        inp = inputs((jar("an_uong", n=150, seed=1, balance=balance),))
        raw.append(_run(inp, False).jars[0].summary.p_shortfall)
        on = _run(inp, True).jars[0].summary
        assert on.series_kind == "dense"
        pub.append(on.p_shortfall)
    assert 0.311 <= raw[1] < raw[0] <= 0.405
    assert pub[1] < pub[0]


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


def test_cqr_qua_api_doi_dai_hu_day_giu_p50_va_khong_ap_cho_hu_thua():
    # hũ dày chi đều 40.000 mỗi ngày nên đơn vị ngày h là 40.000 x h; hệ số dưới 0,5 và trên 0,2 ở mọi mốc
    day = jar("an_uong", n=60, spend=(40_000,) * 60, balance=3_000_000)
    thua = jar("giai_tri", n=60, seed=2, p=0.2, med=90_000, balance=700_000)
    table = {"cqr": {"h": [1, 30], "lo": [0.5, 0.5], "hi": [0.2, 0.2]}}
    inp = inputs((day, thua))
    off = _run(inp, False, dense=table, sparse=table)
    on = _run(inp, True, dense=table, sparse=table)
    assert [j.summary.series_kind for j in on.jars] == ["dense", "sparse"]
    d_off, d_on = off.jars[0].days[9], on.jars[0].days[9]  # ngày 10: đơn vị 400.000
    assert d_off.balance_p10_vnd - d_on.balance_p10_vnd == 200_000
    assert d_on.balance_p90_vnd - d_off.balance_p90_vnd == 80_000
    assert [d.balance_p50_vnd for d in on.jars[0].days] == [
        d.balance_p50_vnd for d in off.jars[0].days
    ]
    assert on.jars[0].summary.runout_date == off.jars[0].summary.runout_date
    assert on.jars[1].days == off.jars[1].days  # hũ thưa: không áp CQR dù hiệu chỉnh có bảng


def test_cqr_chon_bang_theo_do_dai_lich_su_cua_hu():
    # hai nhóm (Mondrian): dưới 100 ngày lịch sử dùng bảng thứ nhất (dưới 0,5), từ 100 ngày dùng bảng thứ hai (dưới 0,25)
    table = {
        "cqr": [
            {"h": [1, 30], "lo": [0.5, 0.5], "hi": [0.0, 0.0], "min_history_days": 0},
            {"h": [1, 30], "lo": [0.25, 0.25], "hi": [0.0, 0.0], "min_history_days": 100},
        ]
    }
    for n, shift in ((60, 200_000), (120, 100_000)):  # ngày 10, đơn vị 40.000 x 10
        inp = inputs((jar("an_uong", n=n, spend=(40_000,) * n, balance=3_000_000),))
        off, on = _run(inp, False, dense=table), _run(inp, True, dense=table)
        assert off.jars[0].days[9].balance_p10_vnd - on.jars[0].days[9].balance_p10_vnd == shift


# --- hũ thưa không nêu ngày cạn cụ thể ---------------------------------------------------------------------------
def test_hu_thua_bao_khong_hien_ngay_can_khi_bat_va_van_giu_runout_date():
    thua = jar("giai_tri", n=60, seed=2, p=0.3, med=90_000, balance=100_000)
    inp = inputs((jar("an_uong", n=60, seed=1, balance=200_000, med=60_000), thua,
                  jar("nghia_vu", n=60, seed=3, kind="obligation", p=0.0, balance=2_000_000)))  # fmt: skip
    off, on = _run(inp, False), _run(inp, True)
    assert [j.summary.series_kind for j in on.jars] == ["dense", "sparse", "sparse"]
    assert on.run.params["show_runout_date"] == {
        "an_uong": True,
        "giai_tri": False,  # hũ thưa: bên dùng hiện "có thể cạn trước ngày lương" kèm %
        "nghia_vu": True,  # hũ nghĩa vụ: ngày cạn đi theo lịch nghĩa vụ nên vẫn nêu
    }
    assert [runout_date_shown(on, c) for c in ("an_uong", "giai_tri")] == [True, False]
    # tương thích ngược: trường cũ giữ nguyên giá trị, tắt công tắc thì không có khóa và mọi hũ nêu ngày như trước
    assert off.jars[1].summary.runout_date is not None
    assert on.jars[1].summary.runout_date == off.jars[1].summary.runout_date
    assert "show_runout_date" not in off.run.params
    assert all(runout_date_shown(off, j.summary.jar_code) for j in off.jars)


def test_chinh_nhanh_giu_co_khong_hien_ngay_cho_hu_duoc_tinh_lai():
    inp = with_config(inputs(), probability_enabled=True, extra=_cal(True))
    upd = update_forecast(inp, forecast_user(inp), ["giai_tri"])
    assert contract.check_result(inp, upd, subset=True) == []
    assert upd.run.params["show_runout_date"] == {"giai_tri": False}


def test_bo_kiem_hop_dong_bat_co_hien_ngay_sai_dang():
    inp = with_config(inputs(), probability_enabled=True, extra=_cal(True))
    res = forecast_user(inp)
    bad = replace(
        res, run=replace(res.run, params={**res.run.params, "show_runout_date": {"an_uong": "co"}})
    )
    assert any("show_runout_date" in e for e in contract.check_result(inp, bad))


# --- công tắc tắt: hồi quy -----------------------------------------------------------------------------------------
_TABLES = {
    "dense": {
        "p_isotonic": {"x": [0.0, 1.0], "y": [0.6, 0.6]},
        "cqr": {"h": [1, 30], "lo": [0.5, 0.5], "hi": [0.2, 0.2]},
    },
    "sparse": {"p_isotonic": {"x": [0.0, 1.0], "y": [0.6, 0.6]}},
}


def _without_new_keys(cal: dict) -> dict:
    """Tệp hiệu chỉnh như trước #25: không có `recalibrate`, `p_isotonic`, `cqr`."""
    out = {k: v for k, v in cal.items() if k != "recalibrate"}
    for k in KINDS:
        out[k] = {kk: vv for kk, vv in cal[k].items() if kk not in ("p_isotonic", "cqr")}
    return out


def _with_tables(cal: dict, recalibrate: bool) -> dict:
    out = {**cal, "recalibrate": recalibrate}
    for k, extra in _TABLES.items():
        out[k] = {**cal[k], **extra}
    return out


def test_tat_cong_tac_thi_dau_ra_giong_het_tep_hieu_chinh_cu(monkeypatch):
    old = _without_new_keys(_default.CALIBRATION)
    gate_off = {k: {"probability_min_history_days": 0} for k in ("dense", "sparse")}
    inp = with_config(inputs(), probability_enabled=True, extra={"calibration": gate_off})
    monkeypatch.setattr(_default, "CALIBRATION", old)
    before = forecast_user(inp)
    monkeypatch.setattr(_default, "CALIBRATION", _with_tables(old, recalibrate=False))
    off = forecast_user(inp)
    assert off.jars == before.jars
    assert {k: v for k, v in off.run.params.items() if k != "calibration"} == {
        k: v for k, v in before.run.params.items() if k != "calibration"
    }
    # cùng các bảng đó mà bật công tắc thì đầu ra đổi (phép so ở trên không rỗng nghĩa)
    monkeypatch.setattr(_default, "CALIBRATION", _with_tables(old, recalibrate=True))
    assert forecast_user(inp).jars != before.jars


# --- Calibration: to_dict / from_dict ----------------------------------------------------------------------------
def test_hieu_chinh_khu_hoi_khoa_moi_va_tep_cu_thieu_khoa_thi_nhu_truoc():
    old = _without_new_keys(_default.CALIBRATION)
    legacy = calibration_from_dict(old)
    assert legacy.recalibrate is False
    assert all(
        legacy.for_kind(k).p_isotonic is None and legacy.for_kind(k).cqr is None for k in KINDS
    )
    assert legacy.to_dict()["dense"]["cqr"] is None and legacy.to_dict()["recalibrate"] is False

    cal = calibration_from_dict(_with_tables(old, recalibrate=True))
    d = cal.to_dict()
    assert d["recalibrate"] is True
    assert d["dense"]["cqr"] == [
        {"h": [1, 30], "lo": [0.5, 0.5], "hi": [0.2, 0.2], "scale_days": 28, "min_history_days": 0}
    ]
    assert (
        d["sparse"]["p_isotonic"] == {"x": [0.0, 1.0], "y": [0.6, 0.6]}
        and d["sparse"]["cqr"] is None
    )
    assert calibration_from_dict(d) == cal
    # đè một phần: khóa vắng giữ bảng của gốc, khóa có giá trị None thì bỏ riêng bảng đó
    over = calibration_from_dict({"dense": {"cqr": None}}, base=cal)
    assert over.recalibrate is True and over.dense.cqr is None
    assert over.dense.p_isotonic == cal.dense.p_isotonic and over.sparse == cal.sparse


# --- cổng PAV theo từng loại hũ (backtest) --------------------------------------------------------------------
#: dải hũ dày sau CQR qua mọi điều kiện của công tắc, để test chỉ xét phần PAV
_BANDS_OK = {
    "47": {"cov30": 0.81},
    "120": {
        "cov30": 0.80,
        "cov30_by_family": {"hurdle_lognormal": 0.79, "shopping_sessions": 0.81},
        "below_p10_30": 0.10,
        "above_p90_30": 0.10,
    },
    "full": {"cov30": 0.79},
}


def _sf(cells: dict[str, dict[str, tuple[float | None, float]]]) -> dict:
    """{độ dài: {loại hũ: (sai lệch lớn nhất, Brier)}} theo dạng của `shortfall_summary`."""
    return {
        length: {k: {"max_gap": g, "brier": b} for k, (g, b) in kinds.items()}
        for length, kinds in cells.items()
    }


def test_cong_pav_bo_loai_hu_lam_tang_sai_lech_va_giu_loai_tot_hon():
    # số của tập kiểm #25: hũ dày ở 120 ngày sai lệch 0,070 -> 0,100 dù Brier giảm nhẹ; hũ thưa 0,049 -> 0,025
    before = _sf({
        "47": {"dense": (0.070, 0.1643)},
        "120": {"dense": (0.070, 0.1609), "sparse": (0.049, 0.1711)},
        "full": {"dense": (0.090, 0.1653), "sparse": (0.044, 0.1666)},
    })  # fmt: skip
    after = _sf({
        "47": {"dense": (0.053, 0.1638)},
        "120": {"dense": (0.100, 0.1607), "sparse": (0.025, 0.1701)},
        "full": {"dense": (0.092, 0.1651), "sparse": (0.022, 0.1660)},
    })  # fmt: skip
    g = recal.gate(_BANDS_OK, before, after)
    assert g["ok"] is True  # công tắc (CQR) vẫn bật
    assert g["pav"]["dense"]["ok"] is False
    assert g["pav"]["sparse"]["ok"] is True


def test_cong_pav_bo_loai_hu_lam_tang_brier_hoac_thieu_so_sai_lech():
    # hũ dày: sai lệch giảm nhưng Brier tăng; hũ thưa: không ô nào đủ 30 ca nên không có sai lệch để so
    before = _sf({"120": {"dense": (0.070, 0.1600), "sparse": (None, 0.1700)}})
    after = _sf({"120": {"dense": (0.030, 0.1601), "sparse": (None, 0.1600)}})
    g = recal.gate(_BANDS_OK | {"47": {"cov30": 0.80}}, before, after)
    assert g["pav"]["dense"]["ok"] is False
    assert g["pav"]["sparse"]["ok"] is False


def test_tep_hieu_chinh_sinh_lai_bo_bang_pav_cua_loai_khong_qua_cong_va_giu_cqr():
    iso = {"x": [0.0, 1.0], "y": [0.1, 0.9]}
    cqr = [
        {"h": [1, 30], "lo": [0.1, 0.2], "hi": [0.0, -0.1], "scale_days": 28, "min_history_days": 0}
    ]
    sf = _sf({"120": {"dense": (0.07, 0.16), "sparse": (0.05, 0.17)}})
    band = {k: 0.1 for k in ("cov30", "below_p10_30", "above_p90_30", "width30")}
    result = {
        "method": "thử",
        "calibration_seeds": [101],
        "heldout_seeds": [201],
        "tables": {"dense": {"cqr": cqr, "p_isotonic": iso}, "sparse": {"p_isotonic": iso}},
        "gate": {
            "checks": {},
            "ok": True,
            "pav": {"dense": {"checks": {}, "ok": False}, "sparse": {"checks": {}, "ok": True}},
        },
        "bands": {"before": {"120": band}, "after": {"120": band}},
        "shortfall": {"before": sf, "after": sf},
    }
    # tệp hiện hành còn bảng PAV hũ dày của lần sinh trước: phải bị bỏ, không giữ lại bảng cũ
    current = {
        "version": "v",
        "dense": {"rho": 0.0, "p_isotonic": {"x": [0.0, 1.0], "y": [0.3, 0.3]}},
        "sparse": {"rho": 0.0},
        "cold_start": {"rho": 0.8},
    }
    payload = recal.calibration_payload(current, result)
    assert payload["recalibrate"] is True
    assert payload["dense"]["cqr"] == cqr and "p_isotonic" not in payload["dense"]
    assert payload["sparse"]["p_isotonic"] == iso
    assert calibration_from_dict(payload).dense.p_isotonic is None
