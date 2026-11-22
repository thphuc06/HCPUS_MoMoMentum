"""Tiện ích dùng chung của `run_scenario` và `affordability_check`: thứ tự trạng thái đủ/sát/hụt, ngày, nhãn tiếng Việt.

Mọi hàm thuần. Ngưỡng đủ/sát/hụt KHÔNG nằm ở đây: nằm ở cấu hình (`ForecastSettings.affordability_*`, `ForecastConfig`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

STATUS_RANK = {"ok": 0, "tight": 1, "short": 2}
STATUS_WORD = {"ok": "Đủ", "tight": "Sát", "short": "Hụt"}
BAND_RANK = {"low": 0, "medium": 1, "high": 2}


def worst(statuses: Sequence[str]) -> str:
    """Trạng thái nặng nhất (hụt > sát > đủ); rỗng thì đủ."""
    return max(statuses, key=lambda s: STATUS_RANK[s], default="ok")


def best(statuses: Sequence[str]) -> str:
    return min(statuses, key=lambda s: STATUS_RANK[s], default="ok")


def min_band(bands: Sequence[str]) -> str:
    return min(bands, key=lambda b: BAND_RANK[b], default="low")


def dm(value: date | str) -> str:
    d = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    return f"{d.day:02d}/{d.month:02d}"


def to_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def int_of(value: Any) -> int:
    """Số tiền từ Decimal, chuỗi hoặc số thực JSON thành số nguyên VND."""
    from decimal import Decimal

    if value is None:
        return 0
    return int(Decimal(str(value)).to_integral_value())


def row_date(row: Mapping[str, Any], key: str) -> date | None:
    return to_date(row.get(key))
