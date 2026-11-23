"""Điểm vào của Lambda `yofina-forecast`: target `forecast` của AgentCore Gateway (tool `forecast___get_forecast`, `forecast___run_scenario`,
`forecast___list_scenarios`, `forecast___affordability_check`, `forecast___get_resilience_score`, `forecast___stress_test`) và đường
REST `POST /affordability`, `GET /resilience`, `GET /resilience/shocks`, `POST /resilience/stress` của HTTP API."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from yofina_forecast import bootstrap
from yofina_forecast.afford import AffordabilityEngine
from yofina_forecast.resilience import ResilienceEngine
from yofina_forecast.scenario import ScenarioEngine
from yofina_forecast.stress import StressEngine
from yofina_forecast.tool import ForecastReader, ReadSettings, handle_gateway, handle_http
from yofina_ledger.refdata import ReferenceData
from yofina_ledger.repo import LedgerRepo


@lru_cache(maxsize=1)
def _repo() -> LedgerRepo:
    return LedgerRepo(bootstrap.db())


@lru_cache(maxsize=1)
def _reader() -> ForecastReader:
    s = bootstrap.settings()
    return ForecastReader(_repo(), ReadSettings(s.freshness_seconds, s.app_timezone))


@lru_cache(maxsize=1)
def _ref() -> ReferenceData:
    return ReferenceData(_repo(), bootstrap.settings().reference_cache_seconds)  # type: ignore[arg-type]


@lru_cache(maxsize=1)
def _scenario() -> ScenarioEngine:
    return ScenarioEngine(bootstrap.pipeline(), _repo(), _ref(), bootstrap.settings())


@lru_cache(maxsize=1)
def _afford() -> AffordabilityEngine:
    return AffordabilityEngine(bootstrap.pipeline(), _repo(), _ref(), bootstrap.settings())


@lru_cache(maxsize=1)
def _resilience() -> ResilienceEngine:
    return ResilienceEngine(bootstrap.pipeline())


@lru_cache(maxsize=1)
def _stress() -> StressEngine:
    return StressEngine(bootstrap.pipeline(), _resilience())


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    ctx = event.get("requestContext")
    if isinstance(ctx, dict) and "http" in ctx:
        return handle_http(event, _afford(), _resilience(), _stress())
    return handle_gateway(
        event,
        context,
        _reader(),
        bootstrap.pipeline(),
        _scenario(),
        _afford(),
        _resilience(),
        _stress(),
    )
