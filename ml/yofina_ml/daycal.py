"""Đặc trưng lịch của từng ngày: thứ, cuối tuần, số ngày kể từ ngày lương, ô (cuối tuần x nửa đầu kỳ lương).

Thuần hàm trên ngày mô phỏng; không đọc đồng hồ. Luật ngày lương giống `yofina_core.clock.payday_in_month` (ngày lương lớn
hơn số ngày của tháng thì lấy ngày cuối tháng) nhưng cài lại ở đây vì gói ML chỉ được phụ thuộc numpy và scipy.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

import numpy as np

N_CELLS = 4  # (cuối tuần: 0/1) x (nửa đầu kỳ lương: 0/1) -> chỉ số = 2 * cuối_tuần + nửa_đầu


def _last_day(year: int, month: int) -> int:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return (nxt - timedelta(days=1)).day


def payday_in_month(payday_day: int, year: int, month: int) -> date:
    return date(year, month, min(payday_day, _last_day(year, month)))


def latest_payday(payday_day: int, d: date) -> date:
    """Ngày lương gần nhất không sau `d`."""
    this_month = payday_in_month(payday_day, d.year, d.month)
    if this_month <= d:
        return this_month
    year, month = (d.year - 1, 12) if d.month == 1 else (d.year, d.month - 1)
    return payday_in_month(payday_day, year, month)


@dataclass(frozen=True)
class DayFeatures:
    """Đặc trưng của một dãy ngày liên tiếp hoặc rời; các mảng cùng độ dài."""

    weekday: np.ndarray  # 0 = thứ hai
    weekend: np.ndarray  # bool
    early: np.ndarray  # bool: số ngày kể từ ngày lương <= early_days
    since_payday: np.ndarray  # int
    cell: np.ndarray  # int8 trong 0..3

    def __len__(self) -> int:
        return len(self.cell)

    def __getitem__(self, sl: slice) -> DayFeatures:
        return DayFeatures(
            self.weekday[sl], self.weekend[sl], self.early[sl], self.since_payday[sl], self.cell[sl]
        )


def make_features(dates: Sequence[date], payday_day: int, early_days: int) -> DayFeatures:
    n = len(dates)
    weekday = np.fromiter((d.weekday() for d in dates), dtype=np.int64, count=n)
    since = np.fromiter((_since(payday_day, d) for d in dates), dtype=np.int64, count=n)
    weekend = weekday >= 5
    early = since <= early_days
    cell = (2 * weekend.astype(np.int8) + early.astype(np.int8)).astype(np.int8)
    return DayFeatures(weekday, weekend, early, since, cell)


@lru_cache(maxsize=4096)
def _since(payday_day: int, d: date) -> int:
    return (d - latest_payday(payday_day, d)).days


def date_range_features(start: date, n_days: int, payday_day: int, early_days: int) -> DayFeatures:
    """Đặc trưng của `n_days` ngày liên tiếp bắt đầu từ `start`."""
    return make_features([start + timedelta(days=i) for i in range(n_days)], payday_day, early_days)
