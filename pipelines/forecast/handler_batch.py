"""Điểm vào của Lambda `yofina-forecast-batch` (batch đêm, đặt lại demo, tính lại khi đọc cũ). Xem `yofina_forecast/batch.py`."""

from __future__ import annotations

from typing import Any

from yofina_forecast import bootstrap
from yofina_forecast.batch import handle_batch


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return handle_batch(event, bootstrap.pipeline())
