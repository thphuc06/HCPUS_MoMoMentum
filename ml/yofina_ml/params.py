"""Tham số thuật toán của gói ML (khác `ForecastConfig`: đó là ngưỡng sản phẩm do pipeline truyền vào).

`MLParams` gom mọi hằng số của thuật toán (cửa sổ lịch sử, ô lịch, prior khởi đầu lạnh, bước ACI...) vào MỘT chỗ,
có tên và có mô tả, để không rải số trong mã. Mặc định là giá trị đã dùng khi đo backtest
(`docs/research/backtest-phase-2.md`); đổi bằng `ForecastConfig.extra["ml"] = {...}` (khóa không biết thì báo lỗi).

Tham số HIỆU CHỈNH theo backtest (ρ, độ nới mức, cổng xác suất) KHÔNG nằm ở đây mà ở `yofina_ml.calibration`, vì chúng do
backtest sinh ra chứ không do người chọn.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any


def _default_spend_ratio() -> dict[str, float]:
    # Tỷ lệ phần phân bổ kỳ lương của hũ mà người dùng thường tiêu hết (prior nhóm cho khởi đầu lạnh).
    # Hũ tiết kiệm và hũ nghĩa vụ không chi tùy ý (nghĩa vụ đã nằm ở lịch outflows).
    return {"spending": 0.85, "saving": 0.0, "obligation": 0.0}


@dataclass(frozen=True)
class MLParams:
    # --- lịch: ô = (cuối tuần?) x (nửa đầu kỳ lương?) ---------------------------------------------
    early_days: int = 7  # ngày tính từ ngày lương <= giá trị này là "nửa đầu kỳ lương"

    # --- hurdle theo lịch ---------------------------------------------------------------------------
    fit_window_days: int = 180  # chỉ dùng tối đa ngần này ngày gần nhất
    halflife_days: float | None = (
        180.0  # trọng số mũ theo tuổi (nửa đời); None: không giảm trọng số
    )
    min_cell_days: int = 8  # ô có ít ngày hơn thì dùng xác suất của toàn cửa sổ
    min_cell_positives: int = 15  # ô có ít ngày có chi hơn thì dùng phân phối số tiền chung
    beta_a: float = (
        1.0  # prior Beta(a, b) của xác suất có chi toàn cửa sổ (trung bình posterior (k+a)/(n+a+b))
    )
    beta_b: float = 2.0
    #: co ô về xác suất chung: p_ô = (k_ô + kappa p_chung) / (n_ô + kappa); None thì ô dùng prior Beta(a, b) riêng
    cell_shrink_days: float | None = 20.0
    #: số tiền theo ô: log(số tiền) = mức + hiệu ứng cuối tuần + hiệu ứng nửa đầu kỳ lương (hồi quy có trọng số, co hiệu ứng
    #: về 0 với sức nặng này tính bằng số ngày có chi); phần dư lấy chung. None thì dùng lưới riêng của ô khi đủ
    #: `min_cell_positives` mẫu, không đủ thì lưới chung
    amount_effect_shrink: float | None = 10.0
    amount_grid: int = 32  # số khoảng của lưới phân vị số tiền (lưới có amount_grid + 1 điểm)
    sparse_zero_share: float = (
        0.5  # tỷ lệ ngày không chi vượt ngưỡng này: hũ thưa (mô phỏng hurdle trực tiếp)
    )

    # --- khởi đầu lạnh: luật + trung bình nhóm ------------------------------------------------------
    cold_cycle_days: int = 30  # phân bổ kỳ lương trải đều trên ngần này ngày
    cold_spend_ratio: dict[str, float] = field(default_factory=_default_spend_ratio)
    cold_p0: float = 0.7  # prior xác suất có chi trong ngày của nhóm
    cold_sigma0: float = 0.7  # prior sigma lognormal của số tiền
    cold_weekend_mult: float = 1.2  # nhân số tiền ngày cuối tuần
    cold_early_mult: float = 1.1  # nhân số tiền nửa đầu kỳ lương
    cold_prior_days: float = 14.0  # sức nặng của prior, tính bằng "số ngày tương đương"

    # --- ACI theo ngày (mức phân vị, một alpha cho mỗi nhóm horizon) ---------------------------------
    aci_bins: tuple[int, ...] = (7, 14)  # biên trên của nhóm horizon 1..7, 8..14, còn lại 15+
    aci_alpha_min: float = 0.02  # kẹp alpha để khoảng không nở vô hạn (mức phân vị >= 0,01)
    aci_alpha_max: float = 0.5
    aci_step_days: int = 7  # khoảng cách giữa hai origin của backtest nội bộ
    aci_lookback_days: int = 150  # backtest nội bộ chỉ lùi ngần này ngày
    aci_min_train_days: int = 28  # origin sớm nhất cần ngần này ngày lịch sử để fit
    aci_horizon_days: int = 30  # horizon tối đa của backtest nội bộ

    # --- Monte Carlo --------------------------------------------------------------------------------
    min_paths: int = 100  # n_paths nhỏ hơn thì nâng lên (sai số chuẩn quá lớn)

    # --- nhãn tin cậy -------------------------------------------------------------------------------
    band_medium_min_coverage: float = 0.4  # độ phủ dữ liệu dưới ngưỡng này thì nhãn tin cậy là Thấp

    # --- ngày cạn: ngày đầu tiên số dư P50 <= ngưỡng này --------------------------------------------
    runout_balance_threshold_vnd: int = 0

    @classmethod
    def from_extra(cls, extra: dict[str, Any] | None) -> MLParams:
        """Đọc ghi đè từ `ForecastConfig.extra["ml"]`. Khóa lạ thì ValueError (tránh gõ sai tên mà không biết)."""
        over = (extra or {}).get("ml") or {}
        known = {f.name for f in fields(cls)}
        unknown = set(over) - known
        if unknown:
            raise ValueError(f"MLParams không có tham số {sorted(unknown)}")
        merged = dict(over)
        if "aci_bins" in merged:
            merged["aci_bins"] = tuple(merged["aci_bins"])
        if "cold_spend_ratio" in merged:
            merged["cold_spend_ratio"] = {**_default_spend_ratio(), **merged["cold_spend_ratio"]}
        return cls(**merged)
