"""Hiệu chỉnh mặc định do backtest sinh ra. KHÔNG SỬA TAY: chạy `uv run scripts/ml_backtest.py --write-calibration`
(rho, level_sigma, probability_ok) và `uv run scripts/ml_history_gate.py --write-calibration` (probability_min_history_days).

Số đo và phương pháp ở docs/research/backtest-phase-2.md và docs/research/backtest-final.md.
"""

CALIBRATION = {
    "version": "phase2-2026-11-22",
    "dense": {
        "rho": 0.0,
        "level_sigma": 0.25,
        "probability_ok": True,
        "probability_min_history_days": 47,
    },
    "sparse": {
        "rho": 0.0,
        "level_sigma": 0.0,
        "probability_ok": True,
        "probability_min_history_days": 120,
    },
    "cold_start": {"rho": 0.8, "level_sigma": 0.8, "probability_ok": False},
    "meta": {
        "method": "chọn (rho, level_sigma) theo độ phủ P10-P90 của tổng chi cộng dồn 7/14/30 "
        "ngày, trọng số 0,2/0,3/0,5",
        "families": ["hurdle_lognormal", "shopping_sessions"],
        "calibration_seeds": [101, 102, 103, 104],
        "heldout_seeds": [201, 202, 203, 204, 205, 206],
        "prob_band_h30": [0.75, 0.85],
        "gate": {
            "dense": {
                "cov30": {
                    "hurdle_lognormal": 0.7868252516010978,
                    "shopping_sessions": 0.8229598893499308,
                    "all": 0.8012114537444934,
                },
                "brier": 0.16103016468401488,
                "brier_climatology": 0.24958195713160405,
                "ok": True,
            },
            "sparse": {
                "cov30": {
                    "hurdle_lognormal": 0.7801583605030274,
                    "shopping_sessions": 0.8104886769964244,
                    "all": 0.7965265866209262,
                },
                "brier": 0.16235007653766415,
                "brier_climatology": 0.21979082141685313,
                "ok": True,
            },
        },
        "cov_after": {
            "dense": [0.8209825145711906, 0.8059950041631974, 0.8001665278934221],
            "sparse": [0.8900288554023725, 0.8714331516511703, 0.8185315806348189],
            "cold_start": [0.9138888888888889, 0.8097222222222222, 0.7527777777777778],
        },
        "cov_before_rho0_3": {
            "dense": [0.8226477935054122, 0.7710241465445462, 0.7060782681099084],
            "sparse": [0.8900288554023725, 0.8714331516511703, 0.8185315806348189],
            "cold_start": [0.6277777777777778, 0.5305555555555556, 0.46805555555555556],
        },
        "history_gate": {
            "method": "lịch sử cắt còn L ngày (studies._truncate), origin chung từ "
            "ngày 120 bước 7, chân trời 30, 2000 đường, cổng lịch sử tắt "
            "khi đo",
            "heldout_seeds": [201, 202, 203, 204, 205, 206],
            "prob_band_h30": [0.75, 0.85],
            "thresholds": {"dense": 47, "sparse": 120},
            "cov30": {
                "30": {"dense": 0.756, "sparse": 0.603, "obligation": 0.728},
                "47": {"dense": 0.782, "sparse": 0.677, "obligation": 0.728},
                "60": {"dense": 0.796, "sparse": 0.711, "obligation": 0.728},
                "75": {"dense": 0.807, "sparse": 0.732, "obligation": 0.728},
                "90": {"dense": 0.814, "sparse": 0.747, "obligation": 0.728},
                "105": {"dense": 0.813, "sparse": 0.757, "obligation": 0.728},
                "120": {"dense": 0.81, "sparse": 0.767, "obligation": 0.728},
                "full": {"dense": 0.804, "sparse": 0.787, "obligation": 0.728},
            },
        },
    },
}
