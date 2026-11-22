"""Các mô hình dự báo chi tiêu NGÀY của một hũ (cài `ForecastModel` của `types.py`).

Mỗi mô hình có hai mặt:
- `fit(y, f_hist)` trả một `Marginal` (phân phối biên theo ngày, xem `marginals.py`): đường mà `forecast.py`, ACI và
  Monte Carlo dùng;
- `predict(history, history_start, future_dates, payday_dates, levels)`: đúng chữ ký `ForecastModel.predict` của hợp
  đồng, trả ma trận phân vị VND nguyên, để cắm model khác hoặc đo backtest.

Ba mô hình: `HurdleCalendarModel` (mặc định), `SeasonalNaiveModel` (baseline), `ColdStartRulesModel` (cổng khởi đầu lạnh).
`select_model` chọn theo số ngày lịch sử của hũ.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from yofina_ml.daycal import DayFeatures, make_features
from yofina_ml.marginals import (
    TABLE_LEVELS,
    ColdStartMarginal,
    HurdleMarginal,
    Marginal,
    SeasonalNaiveMarginal,
    make_cold_start,
    make_hurdle,
    quantile_table,
    weighted_grid,
)
from yofina_ml.params import MLParams

HURDLE = "hurdle_calendar"
SEASONAL_NAIVE = "seasonal_naive"
COLD_START = "cold_start_rules"
MODEL_VERSION = "0.2.0"


def _infer_payday_day(payday_dates: tuple[date, ...], fallback: int | None) -> int:
    if fallback is not None:
        return fallback
    return payday_dates[0].day if payday_dates else 1


class _CalendarBase:
    """Phần chung: dựng đặc trưng lịch và cài `predict` theo giao diện hợp đồng."""

    name: str

    def __init__(self, params: MLParams | None = None, payday_day: int | None = None) -> None:
        self.params = params or MLParams()
        self.payday_day = payday_day

    def fit(self, y: np.ndarray, f_hist: DayFeatures) -> Marginal:
        raise NotImplementedError

    def predict(
        self,
        history: tuple[int, ...],
        history_start: date,
        future_dates: tuple[date, ...],
        payday_dates: tuple[date, ...],
        levels: tuple[float, ...],
    ) -> tuple[tuple[int, ...], ...]:
        pday = _infer_payday_day(payday_dates, self.payday_day)
        n = len(history)
        hist_dates = [history_start + timedelta(days=i) for i in range(n)]
        f_hist = make_features(hist_dates, pday, self.params.early_days)
        f_fut = make_features(list(future_dates), pday, self.params.early_days)
        marg = self.fit(np.asarray(history, dtype=float), f_hist)
        table = quantile_table(marg, f_fut, np.asarray(levels, dtype=float))
        table = np.maximum.accumulate(np.rint(np.maximum(table, 0.0)), axis=1)
        return tuple(tuple(int(x) for x in row) for row in table)


class HurdleCalendarModel(_CalendarBase):
    """Hurdle theo lịch: P(có chi) theo ô (cuối tuần x nửa đầu kỳ lương) làm trơn Beta, số tiền bootstrap có trọng số.

    Đây là phần của spike (`spikes/ml-forecasting/forecasters.py::hurdle_forecast`) được viết lại theo hướng giải tích:
    phân vị của hỗn hợp "0 với xác suất 1-p, ngược lại lấy từ phân phối số tiền" tính thẳng (không lấy mẫu 4.000 lần
    mỗi ngày như spike), nên không có nhiễu mẫu và nhanh hơn. Thêm so với spike: trọng số mũ theo tuổi (thích nghi sau điểm
    gãy) và phân phối số tiền riêng cho từng ô khi đủ mẫu.
    """

    name = HURDLE

    @staticmethod
    def _effect_amount_grid(
        yw: np.ndarray, pos: np.ndarray, w: np.ndarray, cell: np.ndarray, prm: MLParams
    ) -> np.ndarray:
        """Lưới phân vị số tiền (4, M + 1) theo mô hình nhân: số tiền = hệ số ô x phần dư chung, hệ số ô = exp(b_cuối_tuần,
        b_nửa_đầu) ước lượng bằng hồi quy log có trọng số (co về 0). Mượn sức giữa các ô nên ô hiếm (cuối tuần đầu kỳ lương)
        vẫn có hiệu ứng đúng thay vì rơi về phân phối chung (làm dự báo tổng bị thấp)."""
        m = prm.amount_grid
        wk = (cell // 2).astype(float)
        ea = (cell % 2).astype(float)
        la = np.log(np.maximum(yw[pos], 1.0))
        wp, wkp, eap = w[pos], wk[pos], ea[pos]
        beta = np.zeros(2)
        if len(la) >= 5:
            x = np.stack([np.ones_like(la), wkp, eap], axis=1)
            xtwx = x.T @ (x * wp[:, None])
            xtwy = x.T @ (wp * la)
            xtwx[1, 1] += float(prm.amount_effect_shrink)
            xtwx[2, 2] += float(prm.amount_effect_shrink)
            beta = np.linalg.solve(xtwx, xtwy)[1:]
        scale_i = np.exp(beta[0] * wkp + beta[1] * eap)
        base = weighted_grid(yw[pos] / scale_i, wp, m)
        out = np.empty((4, m + 1))
        for c in range(4):
            out[c] = base * float(np.exp(beta[0] * (c // 2) + beta[1] * (c % 2)))
        return out

    def fit(self, y: np.ndarray, f_hist: DayFeatures) -> HurdleMarginal:
        prm = self.params
        n_all = len(y)
        lo = max(0, n_all - prm.fit_window_days)
        yw = np.asarray(y[lo:], dtype=float)
        cell = f_hist.cell[lo:n_all]
        n = len(yw)
        if prm.halflife_days:
            age = (n - 1) - np.arange(n)
            w = 0.5 ** (age / float(prm.halflife_days))
        else:
            w = np.ones(n)
        pos = yw > 0
        k_all = float(w[pos].sum())
        n_w = float(w.sum())
        a_all, b_all = k_all + prm.beta_a, (n_w - k_all) + prm.beta_b
        a = np.empty(4)
        b = np.empty(4)
        amt = np.empty((4, prm.amount_grid + 1))
        if prm.amount_effect_shrink is not None:
            amt_grid = self._effect_amount_grid(yw, pos, w, cell, prm)
        else:
            grid_all = weighted_grid(yw[pos], w[pos], prm.amount_grid)
            amt_grid = None
        p_all = a_all / (a_all + b_all)
        for c in range(4):
            m = cell == c
            kc = float(w[m & pos].sum())
            nc = float(w[m].sum())
            if prm.cell_shrink_days is not None:
                kappa = float(prm.cell_shrink_days)
                a[c], b[c] = kc + kappa * p_all, (nc - kc) + kappa * (1.0 - p_all)
            elif int(m.sum()) >= prm.min_cell_days:
                a[c], b[c] = kc + prm.beta_a, nc - kc + prm.beta_b
            else:
                a[c], b[c] = a_all, b_all
            if amt_grid is not None:
                amt[c] = amt_grid[c]
            else:
                mp = m & pos
                if int(mp.sum()) >= prm.min_cell_positives:
                    amt[c] = weighted_grid(yw[mp], w[mp], prm.amount_grid)
                else:
                    amt[c] = grid_all
        pday = self.payday_day if self.payday_day is not None else 1
        return make_hurdle(a, b, amt, pday, prm.early_days)


class SeasonalNaiveModel(_CalendarBase):
    """Baseline: giá trị cùng thứ của tuần trước; khoảng từ phân vị của y_t - y_{t-7} trong cửa sổ."""

    name = SEASONAL_NAIVE

    def fit(self, y: np.ndarray, f_hist: DayFeatures) -> SeasonalNaiveMarginal:
        prm = self.params
        yw = np.asarray(y[-prm.fit_window_days :], dtype=float)
        wd = f_hist.weekday[len(f_hist) - len(yw) :]
        mean = float(yw.mean()) if len(yw) else 0.0
        last = np.full(7, mean)
        for d in range(7):
            idx = np.nonzero(wd == d)[0]
            if len(idx):
                last[d] = yw[idx[-1]]
        short = yw - np.median(yw) if len(yw) else np.zeros(1)
        diff = yw[7:] - yw[:-7] if len(yw) > 7 else short
        resid = np.quantile(diff, TABLE_LEVELS) if len(diff) else np.zeros(len(TABLE_LEVELS))
        return SeasonalNaiveMarginal(last_week=np.rint(last), resid=np.rint(resid))


class ColdStartRulesModel(_CalendarBase):
    """Cổng khởi đầu lạnh: ít ngày lịch sử thì dùng luật và trung bình nhóm, ghi rõ là ước lượng ban đầu.

    Prior: chi trung bình mỗi ngày = tỷ lệ chi của loại hũ (`cold_spend_ratio`, cấu hình) x ngân sách kỳ lương của hũ
    / số ngày trong kỳ. Ngân sách là phần lương của hũ (nếu horizon có ngày lương) hoặc số dư hiện tại. Dữ liệu của chính
    hũ được pha vào theo sức nặng `cold_prior_days` (như thêm ngần ấy ngày prior): có ít dữ liệu thì gần prior, có nhiều
    thì gần dữ liệu. Hình dạng: hurdle với số tiền lognormal (sigma prior pha với sigma đo được nếu đủ mẫu).
    """

    name = COLD_START

    def __init__(
        self,
        params: MLParams | None = None,
        payday_day: int | None = None,
        *,
        kind: str = "spending",
        monthly_budget_vnd: float = 0.0,
    ) -> None:
        super().__init__(params, payday_day)
        self.kind = kind
        self.monthly_budget_vnd = float(max(monthly_budget_vnd, 0.0))

    def fit(self, y: np.ndarray, f_hist: DayFeatures) -> ColdStartMarginal:
        prm = self.params
        y = np.asarray(y, dtype=float)
        n = len(y)
        ratio = prm.cold_spend_ratio.get(self.kind, 0.0)
        mu0 = ratio * self.monthly_budget_vnd / prm.cold_cycle_days
        k0 = prm.cold_prior_days
        mu = (float(y.sum()) + k0 * mu0) / (n + k0)
        pos = y[y > 0]
        p = (len(pos) + k0 * prm.cold_p0) / (n + k0) if mu0 > 0 or len(pos) else 0.0
        if mu <= 0.5 or p <= 0:
            return make_cold_start(0.0, 0.0, prm.cold_sigma0, 1.0, 1.0)
        p = min(max(p, 0.02), 1.0)
        # trung bình số tiền khi có chi, rồi quy ra trung vị lognormal
        sigma = prm.cold_sigma0
        if len(pos) >= 5:
            s_own = float(np.log(pos).std(ddof=1))
            sigma = float(np.sqrt((len(pos) * s_own**2 + k0 * sigma**2) / (len(pos) + k0)))
        mean_pos = mu / p
        # chuẩn hóa hệ số lịch để E[chi/ngày] = mu: trung bình của hệ số trên các ô gần đúng 1,05 nên bỏ qua (prior thô)
        median = mean_pos * float(np.exp(-0.5 * sigma**2))
        return make_cold_start(p, median, sigma, prm.cold_weekend_mult, prm.cold_early_mult)


def select_model(
    history_days: int,
    *,
    cold_start_min_days: int,
    params: MLParams,
    payday_day: int,
    kind: str,
    monthly_budget_vnd: float,
    override: str | None = None,
) -> _CalendarBase:
    """Chọn mô hình theo số ngày lịch sử của hũ: dưới ngưỡng thì khởi đầu lạnh; từ ngưỡng thì hurdle theo lịch
    (hoặc seasonal naive nếu `override`, để so baseline). Ngưỡng là `cold_start_min_days` của cấu hình."""
    if history_days < cold_start_min_days:
        return ColdStartRulesModel(
            params, payday_day, kind=kind, monthly_budget_vnd=monthly_budget_vnd
        )
    if override == SEASONAL_NAIVE:
        return SeasonalNaiveModel(params, payday_day)
    if override not in (None, HURDLE):
        raise ValueError(f"model không biết: {override}")
    return HurdleCalendarModel(params, payday_day)
