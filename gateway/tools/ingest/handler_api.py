"""Điểm vào của Lambda `yofina-ingest-api`: sáu route `/ingest/*` của HTTP API `yofina-api` (payload v2).

Dịch vụ được dựng một lần cho mỗi môi trường thực thi (cache boto3, khóa HMAC, kết nối Data API). Danh tính là claim `sub` của JWT authorizer.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from yofina_ingest.api import IngestApi, s3_presigner
from yofina_ingest.repo import IngestRepo
from yofina_ingest.rest import handle_http
from yofina_ingest.settings import IngestRuntime

from yofina_core.config import Config
from yofina_core.confirm import ConfirmService
from yofina_core.db import DataApi
from yofina_ledger.forecast_client import ForecastClient

logging.getLogger().setLevel(os.environ.get("YOFINA_LOG_LEVEL", "INFO"))

_API: IngestApi | None = None


def get_api() -> IngestApi:
    global _API
    if _API is None:
        cfg = Config()
        rt = IngestRuntime.from_config(cfg)
        forecast = (
            ForecastClient(
                rt.forecast_function_name,
                region=cfg.region(),
                sync_timeout_seconds=rt.forecast_sync_timeout_seconds,
            )
            if rt.forecast_function_name
            else None
        )
        _API = IngestApi(
            IngestRepo(DataApi.from_config(cfg)),
            ConfirmService.from_config(cfg),
            rt,
            presigner=s3_presigner(cfg.region()),
            forecast_trigger=forecast.request if forecast else None,
        )
    return _API


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return handle_http(event, get_api())
