"""Điểm vào của Lambda `yofina-ledger`: một mã, hai đường vào.

- HTTP API (payload v2): sự kiện có `requestContext.http`; danh tính là claim `sub` của JWT authorizer.
- AgentCore Gateway: sự kiện là tham số của tool (kèm `user_id` do interceptor ghi đè); tên tool ở
  `context.client_context.custom["bedrockAgentCoreToolName"]`.
Dịch vụ được dựng một lần cho mỗi môi trường thực thi (cache boto3, khóa HMAC, kết nối).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from yofina_core.config import Config
from yofina_core.confirm import ConfirmService
from yofina_core.db import DataApi
from yofina_ledger.events import EventPublisher
from yofina_ledger.gateway_api import handle_gateway
from yofina_ledger.repo import LedgerRepo
from yofina_ledger.rest_api import handle_http
from yofina_ledger.service import LedgerService
from yofina_ledger.settings import LedgerSettings

logging.getLogger().setLevel(os.environ.get("YOFINA_LOG_LEVEL", "INFO"))

_SERVICE: LedgerService | None = None


def get_service() -> LedgerService:
    global _SERVICE
    if _SERVICE is None:
        settings = LedgerSettings.from_config()
        _SERVICE = LedgerService(
            LedgerRepo(DataApi.from_config()),
            ConfirmService.from_config(),
            settings,
            events=EventPublisher(settings.event_bus_name, region=Config().region()),
        )
    return _SERVICE


def is_http_event(event: dict[str, Any]) -> bool:
    ctx = event.get("requestContext")
    return isinstance(ctx, dict) and "http" in ctx


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    service = get_service()
    if is_http_event(event):
        return handle_http(event, service)
    return handle_gateway(event, context, service)
