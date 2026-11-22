"""Điểm vào của Lambda `yofina-forecast`: target `forecast` của AgentCore Gateway (tool `forecast___get_forecast`)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from yofina_forecast import bootstrap
from yofina_forecast.tool import ForecastReader, ReadSettings, handle_gateway
from yofina_ledger.repo import LedgerRepo


@lru_cache(maxsize=1)
def _reader() -> ForecastReader:
    s = bootstrap.settings()
    return ForecastReader(
        LedgerRepo(bootstrap.db()), ReadSettings(s.freshness_seconds, s.app_timezone)
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return handle_gateway(event, context, _reader(), bootstrap.pipeline())
