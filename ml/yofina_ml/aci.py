"""Adaptive Conformal Inference (ACI) tự viết cho khoảng P10-P90 theo ngày.

Gibbs và Candès (2021, arXiv 2106.00170): giữ một mức sai alpha_t và cập nhật `alpha_{t+1} = alpha_t + gamma (alpha - err_t)`,
với err_t = 1 nếu giá trị thật rơi ngoài khoảng; thiếu phủ thì alpha_t giảm (khoảng rộng ra), thừa phủ thì tăng (hẹp lại).
Zaffran và cộng sự (2022, ICML, arXiv 2202.07282): gamma nhỏ cho khoảng ổn định, gamma lớn thích nghi nhanh nhưng
khoảng nở và dao động; spike của dự án (docs/research/spike-ml-forecasting.md §5) đo gamma 0,005-0,01 là điểm tốt.

Cài đặt ở đây là dạng "mức phân vị": khoảng ở bước horizon h là [q(alpha_t / 2), q(1 - alpha_t / 2)] của chính phân phối biên
của mô hình (không cộng độ lệch kiểu CQR), nên không cần tập điểm sai số hiệu chỉnh và dùng được cả khi lịch sử ngắn.
Một alpha_t cho mỗi nhóm horizon (1-7, 8-14, 15+ ngày; `MLParams.aci_bins`), kẹp trong [aci_alpha_min, aci_alpha_max].

Vì `forecast_user` thuần hàm và không nhận các dự báo cũ, "dòng thời gian trực tuyến" được dựng lại bằng backtest
rolling-origin NỘI BỘ trên chính lịch sử của hũ: lần lượt mỗi `aci_step_days` ngày fit mô hình trên phần đã qua, phát khoảng
cho horizon kế, rồi cập nhật alpha_t theo thứ tự ngày khi giá trị thật đã biết (phản hồi trễ như trong vận hành thật).
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from yofina_ml.daycal import DayFeatures
from yofina_ml.marginals import Marginal
from yofina_ml.params import MLParams

FitFn = Callable[[np.ndarray, DayFeatures], Marginal]


def horizon_bins(horizons: np.ndarray, edges: tuple[int, ...]) -> np.ndarray:
    """Chỉ số nhóm horizon cho horizon 1, 2, ...: nhóm 0 là h <= edges[0], nhóm 1 là edges[0] < h <= edges[1], ..."""
    return np.searchsorted(np.asarray(edges), horizons, side="left")


def run_aci(
    y: np.ndarray,
    f: DayFeatures,
    fit: FitFn,
    params: MLParams,
    gamma: float,
    alpha_target: float,
) -> np.ndarray:
    """Trả mảng alpha_t cuối cùng theo nhóm horizon (độ dài len(aci_bins) + 1) để dùng cho dự báo kế tiếp.

    `y` là chi tiêu từng ngày của hũ (cũ -> mới), `f` đặc trưng lịch của các ngày đó (độ dài >= len(y)).
    gamma <= 0 hoặc lịch sử quá ngắn thì giữ nguyên alpha_target (không hiệu chỉnh).
    """
    n = len(y)
    nb = len(params.aci_bins) + 1
    alpha = np.full(nb, float(alpha_target))
    if gamma <= 0 or n <= params.aci_min_train_days + 1 or not np.any(y > 0):
        return alpha
    horizon = min(params.aci_horizon_days, n - 1)
    bins = horizon_bins(np.arange(1, horizon + 1), params.aci_bins)
    start = max(params.aci_min_train_days, n - params.aci_lookback_days)
    pending: list[tuple[int, int, float, float]] = []  # (ngày mục tiêu, nhóm, cận dưới, cận trên)

    def settle(upto: int) -> None:
        due = sorted((p for p in pending if p[0] < upto), key=lambda p: p[0])
        if not due:
            return
        pending[:] = [p for p in pending if p[0] >= upto]
        for t, b, lo, hi in due:
            err = 0.0 if lo <= y[t] <= hi else 1.0
            alpha[b] = min(
                max(alpha[b] + gamma * (alpha_target - err), params.aci_alpha_min),
                params.aci_alpha_max,
            )

    for m in range(start, n, params.aci_step_days):
        settle(m)
        hmax = min(horizon, n - m)
        marg = fit(y[:m], f[:m])
        fut = f[m : m + hmax]
        a_h = alpha[bins[:hmax]]
        lo = np.asarray(marg.ppf((a_h / 2.0)[None, :], fut))[0]
        hi = np.asarray(marg.ppf((1.0 - a_h / 2.0)[None, :], fut))[0]
        for h in range(hmax):
            pending.append((m + h, int(bins[h]), float(lo[h]), float(hi[h])))
    settle(n)
    return alpha


def interval_levels(alpha: np.ndarray, horizon_days: int, edges: tuple[int, ...]) -> np.ndarray:
    """alpha_t của từng ngày horizon 1..horizon_days (nhóm cuối kéo dài ra mọi horizon dài hơn)."""
    return alpha[horizon_bins(np.arange(1, horizon_days + 1), edges)]
