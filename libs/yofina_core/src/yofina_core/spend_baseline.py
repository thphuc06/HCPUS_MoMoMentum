"""Mức nền bền của chi tiêu theo hũ (issue #39, chủ dự án chốt 26/11): sàn thiết yếu, sàn chi và đích tự tính của hũ Dự phòng tính từ mức
nền của CHÍNH người dùng, không từ chi trung bình của cửa sổ gần nhất. Một đợt tiêu tăng (tháng Tết, đám cưới, hai tuần ăn ngoài nhiều) là
dữ kiện cho agent nói với người dùng, không thành sàn cứng ép Dự phòng và mục tiêu.

Dùng chung cho bộ tối ưu phân bổ của Lambda forecast (`yofina_forecast.allocation`) và đề xuất tỷ lệ của ledger
(`yofina_ledger.split_proposal`): một công thức, một bộ mặc định (zip ledger không có `yofina_forecast`).

- **Chuỗi vào**: chi từng NGÀY của một hũ (cũ tới mới, không thủng ngày, ngày cuối là hôm qua), như chuỗi `spend` hay `essential_spend` của
  hàm DB `app_get_forecast_context` (không gồm khoản gắn nghĩa vụ). Giá trị âm coi là 0.
- **Tuần** cắt LÙI từ ngày cuối nên mọi tuần đủ 7 ngày và tuần mới nhất kết thúc hôm qua (cùng cách cắt với bộ phát hiện đổi hành vi
  `yofina_ml.change`). Chỉ lấy tối đa `weeks` tuần gần nhất; trong cửa sổ đó bỏ các tuần đầu CHƯA CÓ CHI (hũ mới tạo, hũ mới dùng lại
  sau một thời gian không chi), như bộ phát hiện bỏ các tuần đầu chưa có chi.
- **Mức nền** = trung vị chi theo tuần của các tuần đó x `month_days` / 7, làm tròn tới đồng. Trung vị nên một đợt tăng ngắn hơn nửa cửa
  sổ không kéo mức nền lên; một nhịp mới giữ quá nửa cửa sổ thì thành mức nền mới.
- **Lùi về cách cũ** khi cửa sổ còn dưới `min_weeks` tuần tính từ tuần có chi đầu tiên, hoặc khi trung vị bằng 0 (hũ thưa: từ nửa số tuần
  trở lên không chi, như hũ mua vé tháng bốn tuần một lần; trung vị 0 không phải mức chi của hũ đó): mức chi điển hình là chi trung bình
  `fallback_days` ngày gần nhất x `month_days` (cách tính trước 26/11, `recent_monthly`). Cổng dữ liệu khác của người gọi (số ngày lịch
  sử tối thiểu của sàn chi) giữ nguyên.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import Any

WEEK_DAYS = 7
#: cửa sổ mức nền: từng này tuần gần nhất (mặc định chung của LP và ledger; khóa cấu hình `allocation_spend_baseline_weeks`)
DEFAULT_BASELINE_WEEKS = 12
#: số tuần có chi tối thiểu trong cửa sổ để dùng mức nền; ít hơn thì lùi về chi trung bình của cửa sổ gần nhất (khóa cấu hình
#: `allocation_spend_baseline_min_weeks`). 6 tuần: cùng số tuần tối thiểu của bộ phát hiện đổi hành vi (`min_weeks_total` trong
#: `yofina_ml/change_defaults.json`), và là số tuần nhỏ nhất mà trung vị không bị một đợt tăng hai tuần kéo lên
DEFAULT_BASELINE_MIN_WEEKS = 6


def _amounts(daily: Sequence[Any]) -> list[int]:
    return [max(int(Decimal(str(v if v is not None else 0)).to_integral_value()), 0) for v in daily]


def weekly_totals(daily: Sequence[Any], weeks: int, *, skip_leading_zero: bool = True) -> list[int]:
    """Chi theo tuần (cũ tới mới) của tối đa `weeks` tuần đủ 7 ngày gần nhất, cắt lùi từ ngày cuối; mặc định bỏ các tuần đầu chưa có chi
    (`skip_leading_zero` False: giữ đủ các tuần, để vị trí tuần ứng với `week_start`)."""
    x = _amounts(daily)
    n = min(len(x) // WEEK_DAYS, max(weeks, 0))
    end = len(x)
    out = [sum(x[end - WEEK_DAYS * (i + 1) : end - WEEK_DAYS * i]) for i in range(n)][::-1]
    while skip_leading_zero and out and out[0] == 0:
        out.pop(0)
    return out


def week_start(last_day: date, n_weeks: int, index: int) -> date:
    """Ngày đầu của tuần `index` (0 là tuần cũ nhất) trong `n_weeks` tuần cắt lùi, tuần mới nhất kết thúc `last_day`."""
    return last_day - timedelta(days=WEEK_DAYS * (n_weeks - index) - 1)


def baseline_monthly(daily: Sequence[Any], *, weeks: int, min_weeks: int, month_days: int) -> int | None:
    """Mức nền bền mỗi tháng (trung vị chi theo tuần quy về tháng, xem docstring module); None khi chưa đủ `min_weeks` tuần có chi hoặc
    trung vị bằng 0 (hũ thưa)."""
    totals = weekly_totals(daily, weeks)
    if not totals or len(totals) < max(min_weeks, 1):
        return None
    mid = median(totals)
    if mid <= 0:
        return None
    return round(mid * month_days / WEEK_DAYS)


def recent_monthly(daily: Sequence[Any], window_days: int, month_days: int) -> int:
    """Chi trung bình `window_days` ngày gần nhất x `month_days` (mức chi gần đây; cách tính mức chi điển hình trước 26/11). Chưa có
    ngày nào thì 0."""
    tail = _amounts(daily)[-window_days:] if window_days > 0 else []
    if not tail:
        return 0
    return round(sum(tail) / len(tail) * month_days)


@dataclass(frozen=True)
class BaselineSettings:
    """Tham số của mức nền: cửa sổ và số tuần tối thiểu, số ngày một tháng, cửa sổ của cách lùi (chi trung bình gần đây)."""

    weeks: int
    min_weeks: int
    month_days: int
    fallback_days: int

    def __post_init__(self) -> None:
        if self.weeks < 1 or not 1 <= self.min_weeks <= self.weeks or self.month_days < 1 or self.fallback_days < 1:
            raise ValueError("tham số mức nền chi không hợp lệ")

    @property
    def window_days(self) -> int:
        """Số ngày lịch sử cần đọc để thấy đủ cửa sổ mức nền."""
        return self.weeks * WEEK_DAYS


@dataclass(frozen=True)
class SpendLevel:
    """Mức chi điển hình mỗi tháng của một hũ dùng cho sàn: `monthly_vnd`; `robust` là đã tính được mức nền bền (False: lùi về chi
    trung bình gần đây vì chưa đủ tuần)."""

    monthly_vnd: int
    robust: bool


def typical_monthly(daily: Sequence[Any], settings: BaselineSettings) -> SpendLevel:
    """Mức chi điển hình cho sàn: mức nền bền khi đủ tuần, không thì chi trung bình `fallback_days` ngày gần nhất."""
    base = baseline_monthly(
        daily, weeks=settings.weeks, min_weeks=settings.min_weeks, month_days=settings.month_days
    )
    if base is not None:
        return SpendLevel(base, True)
    return SpendLevel(recent_monthly(daily, settings.fallback_days, settings.month_days), False)


__all__ = [
    "DEFAULT_BASELINE_MIN_WEEKS",
    "DEFAULT_BASELINE_WEEKS",
    "WEEK_DAYS",
    "BaselineSettings",
    "SpendLevel",
    "baseline_monthly",
    "recent_monthly",
    "typical_monthly",
    "week_start",
    "weekly_totals",
]
