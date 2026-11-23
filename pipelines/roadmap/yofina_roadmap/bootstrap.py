"""Dựng các client một lần cho mỗi môi trường thực thi Lambda."""

from __future__ import annotations

import logging
import os
from functools import lru_cache

import boto3
from botocore.config import Config as BotoConfig
from yofina_agent.settings import AgentSettings

from yofina_core.config import SSM_PREFIX_ENV, Config
from yofina_core.db import DataApi
from yofina_roadmap.repo import RoadmapRepo
from yofina_roadmap.runner import RoadmapRunner
from yofina_roadmap.settings import RoadmapSettings

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def runner() -> RoadmapRunner:
    cfg = Config()
    settings = RoadmapSettings.from_config(cfg)
    lambda_client = boto3.client(
        "lambda",
        region_name=cfg.region(),
        config=BotoConfig(
            connect_timeout=settings.invoke_connect_timeout_seconds,
            read_timeout=settings.invoke_read_timeout_seconds,
            retries={"total_max_attempts": 1},
        ),
    )
    # Chỉ dùng cấu hình của lõi. Không tra Gateway và guardrail của chat qua SSM.
    agent = AgentSettings.load({k: v for k, v in os.environ.items() if k != SSM_PREFIX_ENV})
    log.info("roadmap_consumer_ready bus=%s", settings.event_bus_name)
    return RoadmapRunner(
        RoadmapRepo(DataApi.from_config(cfg), settings.running_lease_seconds),
        settings,
        agent,
        lambda_client,
    )
