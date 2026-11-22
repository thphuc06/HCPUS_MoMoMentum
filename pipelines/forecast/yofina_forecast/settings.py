"""Cấu hình của pipeline dự báo: toàn bộ lấy từ biến môi trường `YOFINA_*` do CDK đặt (hoặc SSM qua `YOFINA_SSM_PREFIX`).

Không có giá trị mặc định gắn với môi trường; thiếu thì `ConfigError` (master-plan: "không hardcode"). Ngưỡng của mô hình
(đủ/sát/hụt, nhóm tin cậy) đi vào `ForecastConfig` ở `inputs.py`; ML không tự đặt ngưỡng.
"""

from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo

from yofina_core.config import Config


@dataclass(frozen=True)
class ForecastSettings:
    horizon_days: int
    #: lấy lịch sử chi tiêu tối đa từng này ngày gần nhất (ML dùng tối đa 180 ngày để fit, 150 ngày cho ACI)
    history_window_days: int
    n_paths_full: int
    n_paths_fast: int
    cold_start_min_days: int
    aci_gamma: float
    coverage_target: float
    short_threshold: float
    tight_threshold: float
    band_high_min_days: int
    band_high_min_coverage: float
    band_medium_min_days: int
    #: công tắc xác suất: tắt thì không bao giờ hiện p_shortfall (chỉ nhóm Cao/Vừa/Thấp), bất kể kết quả hiệu chỉnh
    probability_enabled: bool
    #: giữ từng này lần chạy mới nhất của mỗi người dùng (cộng lần chạy mới nhất của từng hũ)
    keep_runs: int
    #: đường chỉnh nhanh chỉ dùng khi lần chạy trước của hũ trẻ hơn từng này giây; cũ hơn thì chạy đầy đủ
    fast_max_age_seconds: int
    #: lần chạy kích hoạt do đọc (trigger read) bị bỏ qua nếu đã có lần chạy trẻ hơn từng này giây (chống bão tính lại)
    recompute_guard_seconds: int
    #: quá hạn này (giây) thì dự báo bị coi là cũ (dùng chung giá trị với ledger)
    freshness_seconds: int
    app_timezone: str
    event_bus_name: str
    idempotency_table: str
    idempotency_ttl_seconds: int
    #: một sự kiện đang được xử lý giữ "khóa thuê" từng này giây; quá hạn thì lần giao lại được giành khóa
    idempotency_lease_seconds: int
    #: số người dùng tối đa batch đêm liệt kê
    nightly_max_users: int

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)

    @classmethod
    def from_config(cls, cfg: Config | None = None) -> ForecastSettings:
        cfg = cfg or Config()
        return cls(
            horizon_days=cfg.get_int("forecast_horizon_days"),
            history_window_days=cfg.get_int("forecast_history_window_days"),
            n_paths_full=cfg.get_int("forecast_n_paths_full"),
            n_paths_fast=cfg.get_int("forecast_n_paths_fast"),
            cold_start_min_days=cfg.get_int("forecast_cold_start_min_days"),
            aci_gamma=float(cfg.get("forecast_aci_gamma")),
            coverage_target=float(cfg.get("forecast_coverage_target")),
            short_threshold=float(cfg.get("forecast_short_threshold")),
            tight_threshold=float(cfg.get("forecast_tight_threshold")),
            band_high_min_days=cfg.get_int("forecast_band_high_min_days"),
            band_high_min_coverage=float(cfg.get("forecast_band_high_min_coverage")),
            band_medium_min_days=cfg.get_int("forecast_band_medium_min_days"),
            probability_enabled=cfg.get_bool("forecast_probability_enabled"),
            keep_runs=cfg.get_int("forecast_keep_runs"),
            fast_max_age_seconds=cfg.get_int("forecast_fast_max_age_seconds"),
            recompute_guard_seconds=cfg.get_int("forecast_recompute_guard_seconds"),
            freshness_seconds=cfg.get_int("forecast_freshness_seconds"),
            app_timezone=cfg.get("app_timezone"),
            event_bus_name=cfg.get("event_bus_name", default=""),
            idempotency_table=cfg.get("forecast_idempotency_table", default=""),
            idempotency_ttl_seconds=cfg.get_int("forecast_idempotency_ttl_seconds"),
            idempotency_lease_seconds=cfg.get_int("forecast_idempotency_lease_seconds"),
            nightly_max_users=cfg.get_int("forecast_nightly_max_users"),
        )
