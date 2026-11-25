"""Hiệu chỉnh khoảng tổng nhiều ngày: tham số do backtest rolling-origin sinh ra (`default.py`), không gắn cứng rải rác.

Với mỗi loại chuỗi (`dense`, `sparse`, `cold_start`) có ba thứ:
- `rho`: hệ số tương quan AR(1) của copula Gaussian giữa các ngày (hũ dày và khởi đầu lạnh); hũ thưa không dùng copula.
- `level_sigma`: độ lệch chuẩn (log) của hệ số MỨC chung của cả horizon (mỗi đường mô phỏng nhân chi tiêu với
  exp(sigma * xi - sigma^2 / 2), trung bình 1). Đây là cách bắt "sai lệch mức kéo dài cả 30 ngày" mà tương quan lag-1
  không bắt được (spike ML §3.2); chọn theo độ phủ tổng cộng dồn trên backtest.
- `probability_ok`: backtest giữ-ra-ngoài cho thấy độ phủ khoảng 80% của tổng 30 ngày nằm trong [0,75; 0,85] thì mới được
  phát xác suất hụt; không thì chỉ phát nhóm Cao/Vừa/Thấp.
- `probability_min_history_days`: độ phủ trên chỉ đạt khi hũ có từ ngần này ngày lịch sử (BR-31, đo theo độ dài lịch sử ở
  docs/research/backtest-final.md); hũ ít lịch sử hơn thì ẩn % dù `probability_ok` đúng. Dùng `probability_ok_at(history_days)`.

Ghi đè khi gọi: `ForecastConfig.extra["calibration"] = {"dense": {"rho": 0.5, ...}}` (dùng cho backtest và thử nghiệm).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from yofina_ml.calibration import default as _default
from yofina_ml.recalibration import Isotonic
from yofina_ml.types import ForecastConfig

KINDS = ("dense", "sparse", "cold_start")


@dataclass(frozen=True)
class SeriesCalibration:
    rho: float
    level_sigma: float
    probability_ok: bool
    probability_min_history_days: int = 0
    #: PAV cho p_shortfall (#25), chỉ áp khi `Calibration.recalibrate`
    p_isotonic: Isotonic | None = None

    def probability_ok_at(self, history_days: int) -> bool:
        """Khoảng của loại chuỗi này đã đạt độ phủ mục tiêu ở độ dài lịch sử `history_days` (được phát %)."""
        return self.probability_ok and history_days >= self.probability_min_history_days


@dataclass(frozen=True)
class Calibration:
    version: str
    dense: SeriesCalibration
    sparse: SeriesCalibration
    cold_start: SeriesCalibration
    #: công tắc hiệu chỉnh sau Monte Carlo (#25): PAV, CQR, ẩn ngày cạn hũ thưa
    recalibrate: bool = False

    def for_kind(self, kind: str) -> SeriesCalibration:
        return getattr(self, kind)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"version": self.version, "recalibrate": self.recalibrate}
        for k in KINDS:
            c = self.for_kind(k)
            out[k] = {
                "rho": c.rho,
                "level_sigma": c.level_sigma,
                "probability_ok": c.probability_ok,
                "probability_min_history_days": c.probability_min_history_days,
                "p_isotonic": c.p_isotonic.to_dict() if c.p_isotonic else None,
            }
        return out


def _opt(src: dict[str, Any], key: str, parse: Any, cur: Any) -> Any:
    """Khóa vắng thì giữ giá trị gốc; có khóa mà giá trị None thì bỏ (tắt riêng phần đó)."""
    if key not in src:
        return cur
    return None if src[key] is None else parse(src[key])


def calibration_from_dict(o: dict[str, Any], base: Calibration | None = None) -> Calibration:
    """Dựng `Calibration` từ dict; khóa vắng lấy từ `base` (nếu có)."""
    kw: dict[str, Any] = {
        "version": str(o.get("version", base.version if base else "custom")),
        "recalibrate": bool(o.get("recalibrate", base.recalibrate if base else False)),
    }
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
            probability_min_history_days=int(
                src.get("probability_min_history_days", cur.probability_min_history_days)
            ),
            p_isotonic=_opt(src, "p_isotonic", Isotonic.from_dict, cur.p_isotonic),
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
