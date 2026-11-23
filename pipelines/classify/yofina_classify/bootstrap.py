"""Dựng các thành phần từ cấu hình môi trường (một lần mỗi môi trường thực thi Lambda). Chỉ mã vỏ Lambda gọi, không có logic nghiệp vụ."""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from yofina_classify.adapters import GatewayEmbedder, GatewayJudge
from yofina_classify.idempotency import IdempotencyStore
from yofina_classify.pipeline import Classifier
from yofina_classify.repo import ClassifyRepo, PgLabelIndex
from yofina_classify.service import ClassifyService
from yofina_classify.settings import ClassifySettings
from yofina_core.config import Config
from yofina_core.db import DataApi
from yofina_core.llm import LlmGateway
from yofina_ledger.classify_config import load_thresholds
from yofina_ledger.events import EventPublisher

logging.getLogger().setLevel(os.environ.get("YOFINA_LOG_LEVEL", "INFO"))


@lru_cache(maxsize=1)
def settings() -> ClassifySettings:
    return ClassifySettings.from_config()


@lru_cache(maxsize=1)
def service() -> ClassifyService:
    s = settings()
    db = DataApi.from_config()
    gateway = LlmGateway()
    classifier = Classifier(
        load_thresholds(), PgLabelIndex(db), GatewayEmbedder(gateway), GatewayJudge(gateway)
    )
    return ClassifyService(
        ClassifyRepo(db, s.tz, reference_cache_seconds=s.reference_cache_seconds),
        classifier,
        EventPublisher(s.event_bus_name, region=Config().region()),
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
