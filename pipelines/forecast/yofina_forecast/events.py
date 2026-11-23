"""Sự kiện của pipeline: phát `forecast.updated` (source `yofina.forecast`) và đọc phong bì EventBridge của sự kiện ledger.

Quy tắc (contracts/README.md, mục "Sự kiện"): phát SAU khi transaction DB commit; phát thất bại KHÔNG làm hỏng lần chạy (log JSON và
metric EMF `ForecastEventPublishFailed`, nightly bù). Không PII: chỉ id, mã hũ, nhãn. Ngày trong sự kiện là ngày mô phỏng.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from yofina_core.blocks import format_instant

log = logging.getLogger("yofina.forecast.events")

SOURCE = "yofina.forecast"
LEDGER_SOURCE = "yofina.ledger"
EVENT_VERSION = 1
METRIC_NAMESPACE = "Yofina/Forecast"
#: sự kiện của ledger mà consumer nghe, và cách xử lý (xem `consumer.py`)
LEDGER_EVENT_TYPES = (
    "transaction.recorded",
    "salary.confirmed",
    "obligation.changed",
    "profile.updated",
)


def emf(name: str, value: float, unit: str = "Count", **dimensions: str) -> str:
    """Một dòng log theo Embedded Metric Format: CloudWatch tách thành metric (không cần PutMetricData)."""
    body: dict[str, Any] = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": METRIC_NAMESPACE,
                    "Dimensions": [list(dimensions)] if dimensions else [[]],
                    "Metrics": [{"Name": name, "Unit": unit}],
                }
            ],
        },
        name: value,
    }
    body.update(dimensions)
    return json.dumps(body, ensure_ascii=False)


@dataclass(frozen=True)
class LedgerEvent:
    """Một sự kiện ledger đã đọc từ phong bì EventBridge (đã kiểm các trường tối thiểu)."""

    detail_type: str
    event_id: str
    user_id: str
    detail: Mapping[str, Any]

    @property
    def occurred_at(self) -> datetime | None:
        raw = self.detail.get("occurred_at")
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00")) if raw else None
        except ValueError:
            return None


class BadEvent(ValueError):
    """Thân tin nhắn không phải sự kiện ledger hợp lệ (không thử lại được, chuyển DLQ)."""


def parse_envelope(body: str | Mapping[str, Any]) -> LedgerEvent:
    """Phong bì EventBridge (`detail-type`, `source`, `detail`) -> `LedgerEvent`."""
    try:
        env = json.loads(body) if isinstance(body, str) else dict(body)
    except ValueError as exc:
        raise BadEvent("thân tin nhắn không phải JSON") from exc
    if not isinstance(env, dict):
        raise BadEvent("phong bì không phải đối tượng")
    detail_type, detail = env.get("detail-type"), env.get("detail")
    if detail_type not in LEDGER_EVENT_TYPES or env.get("source") != LEDGER_SOURCE:
        raise BadEvent(f"loại sự kiện không xử lý: {detail_type!r}")
    if not isinstance(detail, dict):
        raise BadEvent("thiếu detail")
    event_id, user_id = detail.get("event_id"), detail.get("user_id")
    if not isinstance(event_id, str) or not event_id or not isinstance(user_id, str) or not user_id:
        raise BadEvent("thiếu event_id hoặc user_id")
    return LedgerEvent(detail_type, event_id, user_id, detail)


class ForecastEventPublisher:
    """Phát sự kiện của pipeline lên bus. `bus_name` rỗng thì chỉ log; lỗi không bao giờ ném ra ngoài."""

    def __init__(self, bus_name: str, client: Any = None, *, region: str | None = None) -> None:
        self.bus_name = bus_name
        self._client = client
        self._region = region

    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("events", region_name=self._region)
        return self._client

    def forecast_updated(
        self,
        *,
        user_id: str,
        run_id: str,
        computed_at: datetime,
        app_date: Any,
        trigger: str,
        jar_codes: Sequence[str],
        is_initial_estimate: bool,
        confidence_label: str,
        parent_event_id: str | None = None,
        trace_id: str | None = None,
    ) -> bool:
        detail: dict[str, Any] = {
            "v": EVENT_VERSION,
            "event_id": run_id,
            "user_id": user_id,
            "run_id": run_id,
            "computed_at": format_instant(computed_at),
            "app_date": app_date.isoformat(),
            "trigger": trigger,
            "jar_codes": list(dict.fromkeys(jar_codes)),
            "is_initial_estimate": bool(is_initial_estimate),
            "confidence_label": confidence_label,
        }
        if parent_event_id:
            detail["parent_event_id"] = parent_event_id
        if trace_id:
            detail["trace_id"] = trace_id
        return self._put("forecast.updated", detail, "ForecastEventPublishFailed")

    def behavior_changed(
        self,
        *,
        user_id: str,
        flag_id: str,
        occurred_at: datetime,
        app_date: Any,
        jar_code: str,
        direction: str,
        old_weekly_vnd: int,
        new_weekly_vnd: int,
        weeks_held: int,
        change_point_date: Any = None,
        trace_id: str | None = None,
    ) -> bool:
        """Phát `behavior.changed` (contracts/events/behavior.changed.schema.json): điểm gãy hành vi của MỘT hũ đã được PELT XÁC
        NHẬN. `event_id` bằng `flag_id` nên phát lại cùng một dấu hiệu cho cùng event_id (consumer dedupe). Dấu hiệu "nghi" (CUSUM)
        KHÔNG phát sự kiện này. Không PII."""
        detail: dict[str, Any] = {
            "v": EVENT_VERSION,
            "event_id": flag_id,
            "user_id": user_id,
            "occurred_at": format_instant(occurred_at),
            "app_date": app_date.isoformat(),
            "flag_id": flag_id,
            "jar_code": jar_code,
            "direction": direction,
            "old_weekly_vnd": int(old_weekly_vnd),
            "new_weekly_vnd": int(new_weekly_vnd),
            "method": "pelt",
            "weeks_held": int(weeks_held),
        }
        if change_point_date is not None:
            detail["change_point_date"] = change_point_date.isoformat()
        if trace_id:
            detail["trace_id"] = trace_id
        return self._put("behavior.changed", detail, "BehaviorEventPublishFailed")

    def _put(self, detail_type: str, detail: Mapping[str, Any], failure_metric: str) -> bool:
        if not self.bus_name:
            log.warning(json.dumps({"msg": "event_bus_not_configured", "type": detail_type}))
            return False
        try:
            resp = self.client.put_events(
                Entries=[
                    {
                        "EventBusName": self.bus_name,
                        "Source": SOURCE,
                        "DetailType": detail_type,
                        "Detail": json.dumps(detail, ensure_ascii=False),
                    }
                ]
            )
            ok = int(resp.get("FailedEntryCount", 0)) == 0
        except Exception as exc:
            log.error(emf(failure_metric, 1, error=type(exc).__name__))
            return False
        if not ok:
            log.error(emf(failure_metric, 1, error="EntryRejected"))
        return ok
