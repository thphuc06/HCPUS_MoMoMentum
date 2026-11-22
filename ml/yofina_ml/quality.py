"""Cổng chất lượng: độ phủ dữ liệu, nhãn tin cậy, trạng thái đủ/sát/hụt.

Mọi ngưỡng lấy từ `ForecastConfig` và `MLParams`; ở đây chỉ có luật.
"""

from __future__ import annotations

from yofina_ml.calibration import Calibration
from yofina_ml.params import MLParams
from yofina_ml.types import ConfidenceBand, CoverageInputs, ForecastConfig, JarStatus

COVERAGE_FORMULA = "clamp((spend + balance_end - balance_start) / income, 0, 1)"
_RANK = {"low": 0, "medium": 1, "high": 2}
_BY_RANK: tuple[ConfidenceBand, ...] = ("low", "medium", "high")


def data_coverage(cov: CoverageInputs | None) -> float | None:
    """Phần thu nhập giải thích được bằng chi tiêu đã ghi và biến động số dư (công thức mặc định của hợp đồng).

    Lương đã nhận bằng 0 (hoặc không có dữ kiện) thì không tính được: None. Làm tròn 3 chữ số (cột numeric(4,3))."""
    if cov is None or cov.income_vnd <= 0:
        return None
    raw = (cov.spend_vnd + cov.balance_end_vnd - cov.balance_start_vnd) / cov.income_vnd
    return round(min(max(raw, 0.0), 1.0), 3)


def band_for(
    history_days: int,
    coverage: float | None,
    probability_ok: bool,
    cfg: ForecastConfig,
    prm: MLParams,
) -> ConfidenceBand:
    """Nhóm tin cậy từ số ngày lịch sử, độ phủ dữ liệu và việc backtest cho thấy khoảng dự báo đạt độ phủ mục tiêu.

    - Thấp: dưới `band_medium_min_days`, hoặc độ phủ dữ liệu dưới `band_medium_min_coverage`.
    - Cao: từ `band_high_min_days` ngày, độ phủ dữ liệu >= `band_high_min_coverage` VÀ khoảng đã hiệu chỉnh đạt.
    - Vừa: còn lại (kể cả khi chưa biết độ phủ dữ liệu: thiếu dữ kiện thì không lên Cao).
    """
    if history_days < cfg.band_medium_min_days:
        return "low"
    if coverage is not None and coverage < prm.band_medium_min_coverage:
        return "low"
    if (
        history_days >= cfg.band_high_min_days
        and coverage is not None
        and coverage >= cfg.band_high_min_coverage
        and probability_ok
    ):
        return "high"
    return "medium"


def min_band(a: ConfidenceBand, b: ConfidenceBand) -> ConfidenceBand:
    return _BY_RANK[min(_RANK[a], _RANK[b])]


def status_for(p_shortfall: float, cfg: ForecastConfig) -> JarStatus:
    if p_shortfall >= cfg.short_threshold:
        return "short"
    if p_shortfall >= cfg.tight_threshold:
        return "tight"
    return "ok"


def dense_probability_ok(cal: Calibration) -> bool:
    return cal.dense.probability_ok
