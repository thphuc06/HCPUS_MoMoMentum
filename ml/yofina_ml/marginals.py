"""Phân phối biên của chi tiêu NGÀY theo từng ngày (hàm phân vị `ppf`), cho ba cách mô hình hóa.

Mỗi "biên" mô tả phân phối chi tiêu của một hũ cho mọi ngày tương lai chỉ từ vài tham số nhỏ (`state()` là JSON thuần), nên:
- bảng phân vị trả cho cột `spend_p10/p50/p90` suy ra bằng `ppf` tại các mức;
- Monte Carlo lấy mẫu bằng `ppf(u)` với u từ copula (hũ dày) hoặc độc lập (hũ thưa), không phải nội suy bảng 13 mức;
- đường sự kiện (`update_forecast`) dựng lại ĐÚNG biên đó từ `state` đã ghi trong `RunMeta.params`, không fit lại.

Ba loại:
- `HurdleMarginal`: xác suất có chi theo ô lịch (Beta posterior) x phân phối số tiền bootstrap (lưới phân vị có trọng số).
- `ColdStartMarginal`: luật + trung bình nhóm: hurdle với số tiền lognormal, tham số suy từ prior nhóm và ngân sách hũ.
- `SeasonalNaiveMarginal`: baseline: giá trị cùng thứ của tuần trước cộng phân vị của sai khác mùa vụ.

Tiền là float trong tính toán; làm tròn về VND nguyên ở lớp ngoài.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
from scipy.special import ndtri

from yofina_ml.daycal import N_CELLS, DayFeatures

# Các mức dùng để lưu sai khác mùa vụ của seasonal naive và để dựng lại phân vị từ bảng.
TABLE_LEVELS = np.array(
    [0.01, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95, 0.98, 0.99]
)  # fmt: skip


class Marginal(Protocol):
    name: str

    def ppf(self, u: np.ndarray, f: DayFeatures, p: np.ndarray | None = None) -> np.ndarray:
        """Phân vị chi tiêu ngày tại mức `u` (hình (N, H) hoặc (K, H), cột j ứng ngày j của `f`). `p` (tùy chọn,
        hình (H,) hoặc (N, H)) ghi đè xác suất có chi; chỉ hurdle dùng."""
        ...

    def state(self) -> dict[str, Any]: ...


def quantile_table(m: Marginal, f: DayFeatures, levels: np.ndarray) -> np.ndarray:
    """Bảng phân vị (H, K) của biên `m` cho các ngày của `f`."""
    h = len(f)
    u = np.repeat(np.asarray(levels, dtype=float)[:, None], h, axis=1)
    return np.asarray(m.ppf(u, f)).T


def interp_table(u: np.ndarray, q: np.ndarray, levels: np.ndarray) -> np.ndarray:
    """Nội suy tuyến tính hàm phân vị từ bảng (H, K) tại u (N, H); ngoại suy tuyến tính hai đầu, cắt ở 0."""
    k = len(levels)
    i = np.clip(np.searchsorted(levels, u, side="right"), 1, k - 1)
    hh = np.arange(q.shape[0])[None, :]
    lo, hi = levels[i - 1], levels[i]
    w = (u - lo) / (hi - lo)
    return np.maximum(q[hh, i - 1] * (1 - w) + q[hh, i] * w, 0.0)


def weighted_grid(values: np.ndarray, weights: np.ndarray, n_intervals: int) -> np.ndarray:
    """Hàm phân vị có trọng số của `values` trên lưới đều n_intervals + 1 điểm trong [0, 1] (nội suy giữa các điểm
    CDF kiểu "điểm giữa"); rỗng thì toàn 0."""
    if len(values) == 0:
        return np.zeros(n_intervals + 1)
    order = np.argsort(values, kind="stable")
    v, w = values[order].astype(float), weights[order].astype(float)
    cw = np.cumsum(w)
    cdf = (cw - 0.5 * w) / cw[-1]
    return np.interp(np.linspace(0.0, 1.0, n_intervals + 1), cdf, v)


# =====================================================================================
# Hurdle theo lịch
# =====================================================================================
@dataclass(frozen=True)
class HurdleMarginal:
    """Mỗi ô lịch c có Beta(a_c, b_c) cho xác suất có chi và một lưới phân vị số tiền `amt[c]` (khi có chi)."""

    a: np.ndarray  # (4,) tham số posterior của xác suất có chi
    b: np.ndarray  # (4,)
    amt: np.ndarray  # (4, M + 1) phân vị số tiền (VND) khi có chi, tăng dần theo cột
    payday_day: int
    early_days: int
    name: str = "hurdle_calendar"

    @property
    def p(self) -> np.ndarray:
        return self.a / (self.a + self.b)

    @property
    def has_amounts(self) -> bool:
        return bool(self.amt.max() > 0)

    def ppf(self, u: np.ndarray, f: DayFeatures, p: np.ndarray | None = None) -> np.ndarray:
        if not self.has_amounts:
            return np.zeros_like(u, dtype=float)
        cells = f.cell
        p_d = self.p[cells] if p is None else p
        thr = 1.0 - p_d
        v = np.clip((u - thr) / np.maximum(p_d, 1e-12), 0.0, 1.0)
        m = self.amt.shape[1] - 1
        pos = v * m
        i0 = np.minimum(pos.astype(np.int64), m - 1)
        frac = pos - i0
        g = self.amt[cells]  # (H, M + 1)
        hh = np.arange(len(cells))[None, :]
        out = g[hh, i0] * (1.0 - frac) + g[hh, i0 + 1] * frac
        return np.where(u > thr, out, 0.0)

    def state(self) -> dict[str, Any]:
        return {
            "type": "hurdle_calendar",
            "payday_day": int(self.payday_day),
            "early_days": int(self.early_days),
            "a": [float(x) for x in self.a],
            "b": [float(x) for x in self.b],
            "amt": [[int(x) for x in row] for row in self.amt],
        }

    @staticmethod
    def from_state(s: dict[str, Any]) -> HurdleMarginal:
        return HurdleMarginal(
            a=np.array(s["a"], dtype=float),
            b=np.array(s["b"], dtype=float),
            amt=np.array(s["amt"], dtype=float),
            payday_day=int(s["payday_day"]),
            early_days=int(s["early_days"]),
        )


def make_hurdle(
    a: np.ndarray, b: np.ndarray, amt: np.ndarray, payday_day: int, early_days: int
) -> HurdleMarginal:
    """Dựng biên hurdle với giá trị đã làm tròn đúng độ chính xác của `state()` (để dựng lại từ state cho kết quả y hệt)."""
    return HurdleMarginal(
        a=np.round(np.asarray(a, dtype=float), 4),
        b=np.round(np.asarray(b, dtype=float), 4),
        amt=np.rint(np.asarray(amt, dtype=float)),
        payday_day=payday_day,
        early_days=early_days,
    )


# =====================================================================================
# Khởi đầu lạnh: luật + trung bình nhóm
# =====================================================================================
@dataclass(frozen=True)
class ColdStartMarginal:
    p: float  # xác suất có chi trong một ngày thường
    median_vnd: float  # trung vị số tiền khi có chi, ngày thường
    sigma: float  # sigma lognormal
    weekend_mult: float
    early_mult: float
    name: str = "cold_start_rules"

    def ppf(self, u: np.ndarray, f: DayFeatures, p: np.ndarray | None = None) -> np.ndarray:
        if self.p <= 0 or self.median_vnd <= 0:
            return np.zeros_like(u, dtype=float)
        thr = 1.0 - self.p
        v = np.clip((u - thr) / self.p, 1e-9, 1.0 - 1e-9)
        mult = np.where(f.weekend, self.weekend_mult, 1.0) * np.where(f.early, self.early_mult, 1.0)
        out = self.median_vnd * mult * np.exp(self.sigma * ndtri(v))
        return np.where(u > thr, out, 0.0)

    def state(self) -> dict[str, Any]:
        return {
            "type": "cold_start_rules",
            "p": self.p,
            "median_vnd": self.median_vnd,
            "sigma": self.sigma,
            "weekend_mult": self.weekend_mult,
            "early_mult": self.early_mult,
        }

    @staticmethod
    def from_state(s: dict[str, Any]) -> ColdStartMarginal:
        return ColdStartMarginal(
            p=float(s["p"]),
            median_vnd=float(s["median_vnd"]),
            sigma=float(s["sigma"]),
            weekend_mult=float(s["weekend_mult"]),
            early_mult=float(s["early_mult"]),
        )


def make_cold_start(
    p: float, median_vnd: float, sigma: float, weekend_mult: float, early_mult: float
) -> ColdStartMarginal:
    return ColdStartMarginal(
        p=round(float(p), 6),
        median_vnd=round(float(median_vnd), 1),
        sigma=round(float(sigma), 6),
        weekend_mult=round(float(weekend_mult), 6),
        early_mult=round(float(early_mult), 6),
    )


# =====================================================================================
# Seasonal naive (baseline)
# =====================================================================================
@dataclass(frozen=True)
class SeasonalNaiveMarginal:
    """Điểm dự báo = giá trị gần nhất của cùng thứ trong tuần; khoảng = phân vị của sai khác mùa vụ y_t - y_{t-7}
    (kiểu conformal, không giả định chuẩn)."""

    last_week: np.ndarray  # (7,) giá trị gần nhất của từng thứ
    resid: np.ndarray  # (K,) phân vị của sai khác mùa vụ tại TABLE_LEVELS
    name: str = "seasonal_naive"

    def table(self, f: DayFeatures) -> np.ndarray:
        q = self.last_week[f.weekday][:, None] + self.resid[None, :]
        return np.maximum.accumulate(np.maximum(q, 0.0), axis=1)

    def ppf(self, u: np.ndarray, f: DayFeatures, p: np.ndarray | None = None) -> np.ndarray:
        return interp_table(u, self.table(f), TABLE_LEVELS)

    def state(self) -> dict[str, Any]:
        return {
            "type": "seasonal_naive",
            "last_week": [int(x) for x in self.last_week],
            "resid": [int(x) for x in self.resid],
        }

    @staticmethod
    def from_state(s: dict[str, Any]) -> SeasonalNaiveMarginal:
        return SeasonalNaiveMarginal(
            last_week=np.array(s["last_week"], dtype=float), resid=np.array(s["resid"], dtype=float)
        )


def marginal_from_state(s: dict[str, Any]) -> Marginal:
    kind = s["type"]
    if kind == "hurdle_calendar":
        return HurdleMarginal.from_state(s)
    if kind == "cold_start_rules":
        return ColdStartMarginal.from_state(s)
    if kind == "seasonal_naive":
        return SeasonalNaiveMarginal.from_state(s)
    raise KeyError(f"loại biên không biết: {kind}")


__all__ = [
    "N_CELLS",
    "TABLE_LEVELS",
    "ColdStartMarginal",
    "HurdleMarginal",
    "Marginal",
    "SeasonalNaiveMarginal",
    "interp_table",
    "make_cold_start",
    "make_hurdle",
    "marginal_from_state",
    "quantile_table",
    "weighted_grid",
]
