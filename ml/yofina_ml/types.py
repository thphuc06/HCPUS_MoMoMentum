"""Kiểu dữ liệu vào và ra của dự báo (hợp đồng ML <-> pipeline). Chỉ có kiểu, KHÔNG có thuật toán.

Mô tả đầy đủ, quy ước và ánh xạ sang bảng ở `ml/README.md` mục "Giao diện" và `contracts/README.md`.
Dạng JSON (để lưu vết, test và gọi qua ranh giới tiến trình) ở `contracts/ml/forecast_io.schema.json`;
chuyển qua lại bằng `yofina_ml.serde`.

Quy ước:
- Tiền là `int` VND, không dùng `float`. Ngày là `datetime.date` theo **ngày mô phỏng** của người dùng (ADR-0003);
  gói này không bao giờ đọc đồng hồ hệ thống, mọi "hôm nay" là `ForecastInputs.app_date`.
- Chuỗi theo ngày đi từ cũ tới mới.
- Mọi giá trị cấu hình (số đường mô phỏng, ngưỡng) đi vào qua `ForecastConfig`; gói này không tự đặt ngưỡng
  trong mã. Các giá trị mặc định ở đây chỉ để dev và test; môi trường thật lấy từ `yofina_core.config`.
- Kiểu dữ liệu là dataclass bất biến (frozen) với tuple, an toàn để băm và chia sẻ giữa các luồng.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, Protocol, runtime_checkable

# --- tập giá trị (khớp CHECK ở db/migrations/0006_forecast.sql và enum ở contracts/) -------------
JarKind = Literal["spending", "saving", "obligation"]  # hũ hệ thống không được dự báo
JarStatus = Literal["ok", "tight", "short"]  # đủ, sát, hụt
ConfidenceBand = Literal["high", "medium", "low"]  # Cao, Vừa, Thấp
SeriesKind = Literal["dense", "sparse", "cold_start"]
FlowKind = Literal["obligation", "salary"]
ForecastModelName = str  # ví dụ "hurdle_calendar", "seasonal_naive", "cold_start_rules"; khớp ^[a-z][a-z0-9_]{0,39}$


# =====================================================================================
# Đầu vào
# =====================================================================================
@dataclass(frozen=True)
class ScheduledFlow:
    """Một khoản tiền vào hoặc ra biết trước của MỘT hũ, đã được pipeline mở rộng theo lịch trong horizon.

    `kind` salary: phần lương của hũ (lương x tỷ lệ chia, vào số dư ngày `date`). `kind` obligation: nghĩa vụ trả bằng hũ
    này (ra khỏi số dư ngày `date`). Nghĩa vụ có khoảng thì engine lấy mẫu số tiền trong [min, max]; vắng thì tất định
    bằng `amount_vnd`. Luật mở rộng chu kỳ nằm ở pipeline (ml/README.md), không nằm ở đây.
    """

    date: date
    kind: FlowKind
    label: str
    amount_vnd: int
    amount_min_vnd: int | None = None
    amount_max_vnd: int | None = None
    ref_id: str | None = None
    original_due_date: date | None = None  # obligation_id; vắng với lương


@dataclass(frozen=True)
class JarInput:
    """Dữ liệu của một hũ: số dư, lịch sử chi tiêu theo ngày, lịch tiền vào và ra biết trước."""

    code: str
    kind: JarKind
    balance_vnd: int  # số dư hiện tại, tính tới hết ngày app_date; có thể là 0
    split_percent: float
    history_start: date  # ngày của phần tử đầu của daily_spend_vnd
    #: chi tiêu mỗi ngày (>= 0) từ history_start tới app_date - 1 (ngày đã khép), cũ -> mới, KHÔNG thủng ngày
    #: (ngày không chi là 0). Chỉ gồm dòng chi trừ tiền hũ và không gắn nghĩa vụ (hàm DB app_get_daily_spend).
    daily_spend_vnd: tuple[int, ...]
    inflows: tuple[ScheduledFlow, ...] = ()
    outflows: tuple[ScheduledFlow, ...] = ()
    purpose: str | None = None

    @property
    def history_days(self) -> int:
        return len(self.daily_spend_vnd)


@dataclass(frozen=True)
class CoverageInputs:
    """Dữ kiện để tính độ phủ dữ liệu: phần thu nhập giải thích được bằng chi tiêu đã ghi và số dư.

    Tổng trên MỌI hũ (kể cả hũ hệ thống) trong cửa sổ lịch sử: `income_vnd` lương đã nhận, `spend_vnd` chi tiêu đã ghi,
    `balance_start_vnd` tổng số dư đầu cửa sổ, `balance_end_vnd` tổng số dư hiện tại. Công thức mặc định:
    `data_coverage = clamp((spend + balance_end - balance_start) / income, 0, 1)`; `income_vnd` bằng 0 thì None.
    """

    income_vnd: int
    spend_vnd: int
    balance_start_vnd: int
    balance_end_vnd: int


@dataclass(frozen=True)
class ForecastConfig:
    """Tham số chạy. Pipeline đọc từ cấu hình (SSM/`yofina_core.config`) rồi truyền vào; không gắn cứng trong ML.

    Mặc định chỉ để dev và test.
    """

    n_paths: int = 5000  # số đường Monte Carlo (batch đêm 10.000, what-if 5.000)
    seed: int | None = (
        None  # None: ngẫu nhiên không tái lập; có giá trị: tái lập được (test, backtest)
    )
    cold_start_min_days: int = (
        21  # dưới ngưỡng này (theo history_days của cả tài khoản) là "ước lượng ban đầu"
    )
    aci_gamma: float = 0.01  # tốc độ thích nghi của ACI (0,005 đến 0,01)
    coverage_target: float = 0.80  # độ phủ danh định của khoảng P10 đến P90
    short_threshold: float = 0.5  # p_shortfall >= ngưỡng này: status short
    tight_threshold: float = 0.2  # p_shortfall >= ngưỡng này (và dưới short): status tight
    probability_enabled: bool = (
        False  # pipeline đặt true khi backtest tuần gần nhất đạt độ phủ mục tiêu (0,75 đến 0,85)
    )
    band_high_min_days: int = (
        60  # đủ lịch sử để nhóm Cao (kèm độ phủ dữ liệu đạt band_high_min_coverage)
    )
    band_high_min_coverage: float = 0.7
    band_medium_min_days: int = 21  # đủ lịch sử để nhóm Vừa
    rho: float | None = (
        None  # hệ số tương quan giữa các ngày; None: engine chọn theo backtest đã hiệu chỉnh
    )
    extra: dict[str, Any] = field(
        default_factory=dict
    )  # tham số riêng của model, ghi vào RunMeta.params


@dataclass(frozen=True)
class ForecastInputs:
    """Đầu vào của `forecast_user`: mọi thứ cần để dự báo MỘT người dùng, đã đọc xong từ DB."""

    app_date: date  # "hôm nay" mô phỏng; ngày dự báo đầu tiên là app_date + 1
    horizon_days: int  # 1 đến 90, mặc định sản phẩm là 30
    next_payday: date  # ngày lương kế tiếp (yofina_core.clock.next_payday); mốc "trước kỳ lương"
    payday_dates: tuple[date, ...]  # mọi ngày lương trong (app_date, app_date + horizon]
    jars: tuple[JarInput, ...]  # chỉ hũ spending, saving, obligation
    coverage: CoverageInputs | None = None
    config: ForecastConfig = field(default_factory=ForecastConfig)
    #: ngày lương hằng tháng (1..31, lớn hơn số ngày của tháng thì lấy ngày cuối tháng). TÙY CHỌN (thêm ở phase 2 luồng B):
    #: model dùng để biết mỗi ngày lịch sử nằm ở đâu trong kỳ lương (nửa đầu hay nửa sau). Vắng thì suy ra từ
    #: `next_payday.day` (sai chỉ khi ngày lương kế tiếp bị kẹp cuối tháng ngắn, ví dụ lương ngày 31 rơi vào 28/2).
    payday_day: int | None = None


# =====================================================================================
# Đầu ra (khớp bảng forecasts, forecast_jar_summaries, forecast_runs)
# =====================================================================================
@dataclass(frozen=True)
class DayQuantiles:
    """Một dòng của bảng `forecasts`: phân vị chi tiêu NGÀY và phân vị SỐ DƯ cuối ngày (đã tính nghĩa vụ và lương).

    Bất biến: spend_p10 <= spend_p50 <= spend_p90 và đều >= 0; balance_p10 <= balance_p50 <= balance_p90 (số dư có thể âm).
    """

    date: date
    spend_p10_vnd: int
    spend_p50_vnd: int
    spend_p90_vnd: int
    balance_p10_vnd: int
    balance_p50_vnd: int
    balance_p90_vnd: int


@dataclass(frozen=True)
class JarSummary:
    """Một dòng của bảng `forecast_jar_summaries`.

    `p_shortfall` là None khi và chỉ khi `show_probability` là False (ràng buộc CHECK của DB): chỉ phát xác suất khi
    `config.probability_enabled`, không phải ước lượng ban đầu, và hũ có đủ `probability_min_history_days` ngày lịch sử của loại
    chuỗi (hiệu chỉnh, BR-31); còn lại để None và chỉ có `confidence_band`.
    `runout_date` là ngày cạn dự kiến trong horizon (ngày đầu tiên số dư P50 chạm 0 hoặc thấp hơn); None nếu không cạn.
    `p_shortfall` là xác suất số dư hũ xuống dưới 0 ít nhất một ngày từ app_date + 1 tới trước ngày lương kế (`next_payday`).
    """

    jar_code: str
    start_balance_vnd: int
    payday_date: date
    days_to_payday: int
    runout_date: date | None
    p_shortfall: float | None
    p_shortfall_se: float | None
    status: JarStatus
    confidence_band: ConfidenceBand
    show_probability: bool
    series_kind: SeriesKind


@dataclass(frozen=True)
class JarForecast:
    summary: JarSummary
    days: tuple[
        DayQuantiles, ...
    ]  # đúng horizon_days dòng, ngày app_date + 1 tới app_date + horizon_days


@dataclass(frozen=True)
class RunMeta:
    """Phần metadata của một dòng `forecast_runs` mà ML quyết định. Pipeline thêm user_id, computed_at, trigger,
    parent_run_id, source_event_id khi ghi."""

    model: ForecastModelName
    model_version: str | None
    app_date: date
    horizon_days: int
    history_days: int  # lớn nhất trong history_days của các hũ (số ngày lịch sử của cả tài khoản)
    data_coverage: float | None
    confidence_label: ConfidenceBand
    is_initial_estimate: bool  # history_days < config.cold_start_min_days
    n_paths: int | None
    seed: int | None
    params: dict[str, Any] = field(
        default_factory=dict
    )  # rho đã chọn, hệ số nới, gamma...: chẩn đoán, JSON thuần


@dataclass(frozen=True)
class ForecastResult:
    run: RunMeta
    jars: tuple[JarForecast, ...]  # một phần tử mỗi hũ đầu vào được dự báo (cùng thứ tự đầu vào)


# =====================================================================================
# Giao diện hàm (cài ở yofina_ml.api; luồng ML thay thân hàm, giữ chữ ký)
# =====================================================================================
@runtime_checkable
class ForecastModel(Protocol):
    """Một mô hình dự báo chi tiêu NGÀY của một hũ (hurdle theo lịch, seasonal naive, ...). `predict` trả bảng phân vị
    chi tiêu ngày cho `future_dates`; cột là các mức phân vị `levels` (tăng dần, trong (0, 1)). Monte Carlo nằm ở tầng trên,
    dùng bảng này, không nằm trong model."""

    name: ForecastModelName

    def predict(
        self,
        history: tuple[int, ...],
        history_start: date,
        future_dates: tuple[date, ...],
        payday_dates: tuple[date, ...],
        levels: tuple[float, ...],
    ) -> tuple[tuple[int, ...], ...]:
        """Trả ma trận [len(future_dates)][len(levels)] chi tiêu VND nguyên, không âm, tăng dần theo `levels`."""
        ...
