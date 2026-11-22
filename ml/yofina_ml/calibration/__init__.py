"""Hiệu chỉnh khoảng tổng nhiều ngày: tham số do backtest rolling-origin sinh ra (`default.py`), không gắn cứng rải rác.

Với mỗi loại chuỗi (`dense`, `sparse`, `cold_start`) có ba thứ:
- `rho`: hệ số tương quan AR(1) của copula Gaussian giữa các ngày (hũ dày và khởi đầu lạnh); hũ thưa không dùng copula.
- `level_sigma`: độ lệch chuẩn (log) của hệ số MỨC chung của cả horizon (mỗi đường mô phỏng nhân chi tiêu với
  exp(sigma * xi - sigma^2 / 2), trung bình 1). Đây là cách bắt "sai lệch mức kéo dài cả 30 ngày" mà tương quan lag-1
  không bắt được (spike ML §3.2); chọn theo độ phủ tổng cộng dồn trên backtest.
- `probability_ok`: backtest giữ-ra-ngoài cho thấy độ phủ khoảng 80% của tổng 30 ngày nằm trong [0,75; 0,85] thì mới được
  phát xác suất hụt; không thì chỉ phát nhóm Cao/Vừa/Thấp.

Ghi đè khi gọi: `ForecastConfig.extra["calibration"] = {"dense": {"rho": 0.5, ...}}` (dùng cho backtest và thử nghiệm).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from yofina_ml.calibration import default as _default
from yofina_ml.types import ForecastConfig

KINDS = ("dense", "sparse", "cold_start")


@dataclass(frozen=True)
class SeriesCalibration:
    rho: float
    level_sigma: float
    probability_ok: bool


@dataclass(frozen=True)
class Calibration:
    version: str
    dense: SeriesCalibration
    sparse: SeriesCalibration
    cold_start: SeriesCalibration

    def for_kind(self, kind: str) -> SeriesCalibration:
        return getattr(self, kind)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"version": self.version}
        for k in KINDS:
            c = self.for_kind(k)
            out[k] = {
                "rho": c.rho,
                "level_sigma": c.level_sigma,
                "probability_ok": c.probability_ok,
            }
        return out


def calibration_from_dict(o: dict[str, Any], base: Calibration | None = None) -> Calibration:
    """Dựng `Calibration` từ dict; khóa vắng lấy từ `base` (nếu có)."""
    kw: dict[str, Any] = {"version": str(o.get("version", base.version if base else "custom"))}
    for k in KINDS:
        src = o.get(k)
        prev = base.for_kind(k) if base else None
        if src is None and prev is None:
            raise KeyError(f"thiếu hiệu chỉnh cho {k}")
        if src is None:
            kw[k] = prev
            continue
        cur = prev or SeriesCalibration(0.0, 0.0, False)
        kw[k] = SeriesCalibration(
            rho=float(src.get("rho", cur.rho)),
            level_sigma=float(src.get("level_sigma", cur.level_sigma)),
            probability_ok=bool(src.get("probability_ok", cur.probability_ok)),
        )
    return Calibration(**kw)


def default_calibration() -> Calibration:
    return calibration_from_dict(_default.CALIBRATION)


def resolve_calibration(config: ForecastConfig) -> Calibration:
    """Hiệu chỉnh áp dụng cho một lần chạy: mặc định do backtest sinh, ghi đè bởi `config.extra["calibration"]`,
    rồi `config.rho` (nếu có) ghi đè ρ của hũ dày và khởi đầu lạnh."""
    cal = default_calibration()
    over = config.extra.get("calibration")
    if over:
        cal = calibration_from_dict(over, base=cal)
    if config.rho is not None:
        cal = replace(
            cal,
            dense=replace(cal.dense, rho=float(config.rho)),
            cold_start=replace(cal.cold_start, rho=float(config.rho)),
        )
    return cal


def calibrated_config(**overrides: Any) -> ForecastConfig:
    """`ForecastConfig` với `probability_enabled` đặt theo kết quả backtest (bật khi hũ dày đạt độ phủ mục tiêu).
    Pipeline có thể dùng hàm này làm gốc rồi ghi đè `seed`, `n_paths`... Chỉ là tiện ích: ngưỡng sản phẩm vẫn do
    pipeline đọc từ cấu hình."""
    cal = default_calibration()
    base = ForecastConfig(probability_enabled=cal.dense.probability_ok)
    return replace(base, **overrides)
