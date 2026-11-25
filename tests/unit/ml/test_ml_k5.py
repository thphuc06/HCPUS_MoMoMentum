"""K5 (#26): cảnh báo hũ cạn, hai định nghĩa "đúng" và hai baseline trên số dư kịch bản. Số đo ở docs/research/backtest-final.md
mục "K5"."""

from __future__ import annotations

import pytest

from yofina_ml.backtest import k5

# Một hũ, chân trời 6 ngày, 4 ngày trước kỳ lương (chỉ số 0..3; chỉ số 4 là ngày lương), chi TB 100 mỗi ngày.
#   Kịch bản 1: số dư 300, chi thật 50, 150, 150 -> số dư 250, 100, -50: cạn thật ngày 2, trước lương.
#     burn-rate 300 - 100 x (i + 1) <= 0 ở i = 2 -> báo ngày 2. Sản phẩm (p 0,6, ngày 3) báo. Seasonal naive p 0,1 < 0,2: không báo.
#   Kịch bản 2: số dư 600, cùng chi thật -> số dư thấp nhất 250, không cạn trong 6 ngày.
#     burn-rate cạn ngày 5 = sau lương: không báo. Sản phẩm (p 0,3, ngày 3) và seasonal naive (p 0,5, ngày 0) báo nhầm.
#   Kịch bản 3: số dư 300, chi thật 0, 0, 0, 100, 400 -> số dư 200 ở ngày 3, -200 ở ngày 4: cạn thật đúng ngày lương.
#     burn-rate báo ngày 2 (lệch 2), sản phẩm (p 0,4, ngày 3) lệch 1, seasonal naive (p 0,25, ngày 0) lệch 4.
SPEND_1 = (50, 150, 150, 0, 0, 0)
SPEND_3 = (0, 0, 0, 100, 400, 0)
CASES = (
    (300, SPEND_1, {"product": (0.6, 3), "seasonal_naive": (0.1, 1)}),
    (600, SPEND_1, {"product": (0.3, 3), "seasonal_naive": (0.5, 0)}),
    (300, SPEND_3, {"product": (0.4, 3), "seasonal_naive": (0.25, 0)}),
)


def _rows():
    rows = []
    for b, spend, models in CASES:
        rows += k5.scenario_rows(
            b=b,
            window=4,
            true_spend=spend,
            scale=100.0,
            models=models,
            tight=0.2,
            tags={"length": 120, "kind": "dense"},
        )
    return rows


def test_k5_hai_dinh_nghia_va_hai_baseline_tren_chuoi_tinh_tay():
    cell = k5.summarize(_rows())["120"]["dense"]
    assert set(cell) == {"product", "seasonal_naive", "burn_rate"}

    br = cell["burn_rate"]  # báo kịch bản 1 (lệch 0) và 3 (lệch 2)
    assert (br["n"], br["n_warn"]) == (3, 2)
    assert br["def1"] == pytest.approx(1.0)  # cả hai trong +-3 ngày
    assert br["mae_days"] == pytest.approx(1.0)
    assert br["lead_median_def1"] == pytest.approx(4.0)  # cạn sau 3 và 5 ngày
    assert br["def2"] == pytest.approx(0.5)  # chỉ kịch bản 1 cạn trước lương
    assert br["lead_median_def2"] == pytest.approx(3.0)
    assert br["recall"] == pytest.approx(1.0)  # một ca cạn trước lương, đã báo

    pr = cell["product"]  # báo cả ba: lệch 1, không cạn, lệch 1
    assert pr["n_warn"] == 3
    assert pr["def1"] == pytest.approx(2 / 3)
    assert pr["mae_days"] == pytest.approx(1.0)  # chỉ tính ca có ngày cạn thật
    assert pr["lead_median_def1"] == pytest.approx(4.0)
    assert pr["def2"] == pytest.approx(1 / 3)
    assert pr["lead_median_def2"] == pytest.approx(3.0)
    assert pr["recall"] == pytest.approx(1.0)

    sn = cell["seasonal_naive"]  # báo kịch bản 2 (không cạn) và 3 (lệch 4)
    assert sn["n_warn"] == 2
    assert sn["def1"] == pytest.approx(0.0) and sn["def2"] == pytest.approx(0.0)
    assert sn["mae_days"] == pytest.approx(4.0)
    assert sn["lead_median_def1"] is None and sn["lead_median_def2"] is None
    assert sn["recall"] == pytest.approx(0.0)  # ca cạn trước lương duy nhất không được báo


def test_k5_thu_kich_ban_tren_persona_tong_hop_chay_nho():
    from yofina_ml.backtest import common

    ps = [common.persona("hurdle_lognormal", "office", 201)]
    rows = k5.collect(ps, lengths=(120,), n_paths=200, first_origin=200, step=40)
    assert rows and {r["method"] for r in rows} == {"product", "seasonal_naive", "burn_rate"}
    assert all(r["window"] >= k5.MIN_WINDOW for r in rows)
    # số dư kịch bản b = alpha x chi TB x w nên burn-rate cạn ở ngày ceil(alpha x w) - 1: báo trước lương đúng khi alpha <= 1
    br = [r for r in rows if r["method"] == "burn_rate"]
    assert br and all(r["warn"] == (r["alpha"] <= 1.0) for r in br)
    out = k5.summarize(rows)
    assert set(out) == {"120"} and set(out["120"]) <= {"dense", "sparse"}
    assert "| 120 |" in k5.render({"summary": out, "calibration": {"version": "v", "recalibrate": True,
                                   "pav_kinds": []}, "rows": len(rows), "seconds": 0})  # fmt: skip
