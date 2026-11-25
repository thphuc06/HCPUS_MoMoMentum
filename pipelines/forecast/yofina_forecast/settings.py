"""Cấu hình của pipeline dự báo: toàn bộ lấy từ biến môi trường `YOFINA_*` do CDK đặt (hoặc SSM qua `YOFINA_SSM_PREFIX`).

Không có giá trị mặc định gắn với môi trường; thiếu thì `ConfigError` (master-plan: "không hardcode"). Ngưỡng của mô hình
(đủ/sát/hụt, nhóm tin cậy) đi vào `ForecastConfig` ở `inputs.py`; ML không tự đặt ngưỡng.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from zoneinfo import ZoneInfo

from yofina_core.config import Config
from yofina_ml.allocation import AllocationParams

#: Tham số bộ tối ưu phân bổ (phase 4 luồng A). TẤT CẢ là giá trị mô phỏng, chưa hiệu chỉnh trên người dùng thật. Mỗi tham số đọc
#: được từ biến `YOFINA_ALLOCATION_<TÊN>` (hoặc SSM) để chỉnh mà không sửa mã; thiếu thì dùng giá trị này.
#: Nguồn: tỷ lệ mức phạt theo ưu tiên (nghĩa vụ 1e6 > thiết yếu 1e5 > mục tiêu) và trọng số dự phòng 3 > mục tiêu 2 > giải trí 1 lấy từ
#: spike `spikes/ml-forecasting/s8_lp.py` (ca 2c); các tham số còn lại do dự án chọn.
DEFAULT_ALLOCATION_PARAMS = AllocationParams(
    month_days=30,  # quy ước tháng 30 ngày, cùng `yofina_planner.facts.MONTH_DAYS`
    rounding_step_vnd=1000,  # làm tròn số tiền đề xuất tới nghìn đồng
    relax_delay_months=6,  # vòng nới lùi hạn mục tiêu thêm từng này tháng
    discretionary_max_cut_percent=50.0,  # vòng chặt: hũ không thiết yếu chỉ bị cắt tối đa từng này % mức hiện tại
    essential_floor_percent=80.0,  # sàn của hũ chi tiêu thiết yếu: từng này % mức chi trung bình hằng tháng
    weight_discretionary=1.0,
    weight_goal=2.0,
    weight_essential=2.5,
    weight_emergency=3.0,
    penalty_obligation_floor=1e6,
    penalty_essential_floor=1e5,
    penalty_goal_need=1e3,
    stay_epsilon=1e-6,  # giữ phần tiền chưa ai cần ở trạng thái chưa phân bổ thay vì dồn bừa vào một hũ
)
#: hũ chi tiêu thiết yếu theo mẫu hũ mặc định (`db/seed/jar_templates.sql`: ăn uống, đi lại, hóa đơn); hũ người dùng tự thêm thì không
#: thiết yếu. Đọc được từ `YOFINA_ESSENTIAL_JAR_CODES` (cách nhau bằng dấu phẩy).
DEFAULT_ESSENTIAL_JAR_CODES = ("an_uong", "di_lai", "hoa_don", "chi_hang_ngay")


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
    #: số đường Monte Carlo của `run_scenario` (baseline và kịch bản dùng CÙNG dãy số ngẫu nhiên)
    scenario_n_paths: int = 5000
    #: giữ từng này kịch bản mới nhất của mỗi người dùng (dữ liệu dẫn xuất, dọn bằng `app_prune_scenarios`)
    scenario_keep: int = 50
    #: kiểm tra trước khi quẹt: hụt khi số dư P50 sau khi chi xuống dưới ngưỡng này (VND) ở bất kỳ ngày nào trước kỳ lương
    affordability_short_p50_floor_vnd: int = 0
    #: sát khi không hụt nhưng số dư P10 (kịch bản xấu) sau khi chi xuống dưới ngưỡng này (VND) trước kỳ lương
    affordability_tight_p10_floor_vnd: int = 0
    #: giữ bảng tra (biểu phí) trong bộ nhớ bao lâu (giây)
    reference_cache_seconds: int = 300
    #: điểm chống chịu: kỳ tính (ngày) của chi tiêu mỗi ngày, nghĩa vụ và tỷ lệ trên thu nhập; cũng là cửa sổ lịch sử lấy trung bình chi tiêu
    resilience_window_days: int = 30
    #: hũ chi tiêu được coi là thiết yếu khi tối ưu phân bổ (mã hũ)
    essential_jar_codes: tuple[str, ...] = DEFAULT_ESSENTIAL_JAR_CODES
    #: số tháng của lộ trình khi `optimize_allocation` không nói rõ
    allocation_horizon_months: int = 3
    allocation: AllocationParams = field(default=DEFAULT_ALLOCATION_PARAMS)

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
            scenario_n_paths=cfg.get_int("forecast_scenario_n_paths"),
            scenario_keep=cfg.get_int("forecast_scenario_keep"),
            affordability_short_p50_floor_vnd=cfg.get_int("affordability_short_p50_floor_vnd"),
            affordability_tight_p10_floor_vnd=cfg.get_int("affordability_tight_p10_floor_vnd"),
            reference_cache_seconds=cfg.get_int("reference_cache_seconds"),
            resilience_window_days=cfg.get_int("resilience_window_days", default=30),
            essential_jar_codes=tuple(
                c.strip()
                for c in str(
                    cfg.get("essential_jar_codes", default=",".join(DEFAULT_ESSENTIAL_JAR_CODES))
                ).split(",")
                if c.strip()
            ),
            allocation_horizon_months=cfg.get_int("allocation_horizon_months", default=3),
            allocation=_allocation_params(cfg),
        )


def _allocation_params(cfg: Config) -> AllocationParams:
    """`DEFAULT_ALLOCATION_PARAMS`, từng trường ghi đè được bằng `allocation_<tên>` (số nguyên hoặc số thực theo kiểu của trường)."""
    values = {}
    for f in fields(AllocationParams):
        default = getattr(DEFAULT_ALLOCATION_PARAMS, f.name)
        cast = int if isinstance(default, int) and not isinstance(default, bool) else float
        values[f.name] = cfg.get(f"allocation_{f.name}", default=default, cast=cast)
    return AllocationParams(**values)
