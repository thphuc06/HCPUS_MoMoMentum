"""Dựng các thành phần từ cấu hình môi trường (một lần mỗi môi trường thực thi Lambda). Chỉ mã vỏ Lambda gọi, không có logic nghiệp vụ."""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from yofina_core.config import Config
from yofina_core.db import DataApi
from yofina_forecast.events import ForecastEventPublisher
from yofina_forecast.idempotency import IdempotencyStore
from yofina_forecast.repo import ForecastRepo
from yofina_forecast.runner import Pipeline
from yofina_forecast.settings import ForecastSettings

logging.getLogger().setLevel(os.environ.get("YOFINA_LOG_LEVEL", "INFO"))


@lru_cache(maxsize=1)
def settings() -> ForecastSettings:
    return ForecastSettings.from_config()


@lru_cache(maxsize=1)
def db() -> DataApi:
    return DataApi.from_config()


@lru_cache(maxsize=1)
def pipeline() -> Pipeline:
    s = settings()
    return Pipeline(
        ForecastRepo(db()),
        s,
        ForecastEventPublisher(s.event_bus_name, region=Config().region()),
    )


@lru_cache(maxsize=1)
def idempotency() -> IdempotencyStore:
    s = settings()
    return IdempotencyStore(
        s.idempotency_table,
        ttl_seconds=s.idempotency_ttl_seconds,
        lease_seconds=s.idempotency_lease_seconds,
        region=Config().region(),
    )
