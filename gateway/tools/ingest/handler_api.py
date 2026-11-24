"""Điểm vào của Lambda `yofina-ingest-api`: một mã, hai đường vào.

- HTTP API (payload v2): sáu route `/ingest/*` của `yofina-api`; sự kiện có `requestContext.http`, danh tính là claim `sub` của JWT
  authorizer.
- AgentCore Gateway (target `ingest`): ba tool `ingest___start_job`, `ingest___get_job_status`, `ingest___confirm_rows`; sự kiện là tham
  số của tool (kèm `user_id` do interceptor ghi đè), tên tool ở `context.client_context.custom["bedrockAgentCoreToolName"]`.

Dịch vụ được dựng một lần cho mỗi môi trường thực thi (cache boto3, khóa HMAC, kết nối Data API).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from yofina_ingest.api import IngestApi, s3_presigner
from yofina_ingest.gateway_api import handle_gateway, is_gateway_event
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
    if is_gateway_event(event):
        return handle_gateway(event, context, get_api())
    return handle_http(event, get_api())
