"""Sự kiện của ledger lên EventBridge bus `yofina-bus` (contracts/events/*.schema.json).

Quy tắc (contracts/README.md, mục "Sự kiện"):
- Phát SAU khi transaction DB commit, mỗi lần ghi một sự kiện (lần chia lương: `salary.confirmed` cộng `transaction.recorded`).
- Phát thất bại KHÔNG làm hỏng thao tác ghi: log JSON và một metric EMF `EventPublishFailed` (CloudWatch đọc từ log, không cần
  quyền `PutMetricData`); service ghi thêm một dòng `audit_events` mã `error` để nightly bù.
- Không PII: chỉ id, mã hũ và số tiền; không tên người nhận, không số tài khoản, không token.
- Ngày trong sự kiện là ngày mô phỏng của người dùng; consumer không dùng đồng hồ hệ thống.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from yofina_core.blocks import format_instant

log = logging.getLogger("yofina.ledger.events")

SOURCE = "yofina.ledger"
EVENT_VERSION = 1
METRIC_NAMESPACE = "Yofina/Ledger"


@dataclass(frozen=True)
class Event:
    detail_type: str
    detail: dict[str, Any]


def _put(detail: dict[str, Any], **optional: Any) -> dict[str, Any]:
    detail.update({k: v for k, v in optional.items() if v is not None})
    return detail


def _effects(deltas: Mapping[str, int], balances: Mapping[str, int]) -> list[dict[str, Any]]:
    return [
        {"jar_code": code, "delta_vnd": int(delta), "balance_after_vnd": int(balances[code])}
        for code, delta in deltas.items()
        if code in balances
    ]


def transaction_recorded(
    *,
    user_id: str,
    trace_id: str | None,
    transaction_id: str,
    event_id: str | None = None,
    occurred_at: datetime,
    app_date: date,
    kind: str,
    tx_type: str,
    funding_source: str,
    amount_vnd: int,
    jar_codes: Sequence[str],
    deltas: Mapping[str, int],
    balances: Mapping[str, int],
    payee_id: str | None = None,
    obligation_id: str | None = None,
    needs_classification: bool | None = None,
) -> Event:
    """`transaction.recorded`: một lần ghi sổ cái đã commit. `event_id` mặc định bằng `transaction_id`."""
    codes = list(dict.fromkeys(jar_codes))
    return Event(
        "transaction.recorded",
        _put(
            {
                "v": EVENT_VERSION,
                "event_id": event_id or transaction_id,
                "user_id": user_id,
                "transaction_id": transaction_id,
                "occurred_at": format_instant(occurred_at),
                "app_date": app_date.isoformat(),
                "kind": kind,
                "tx_type": tx_type,
                "funding_source": funding_source,
                "amount_vnd": int(amount_vnd),
                "jar_codes": codes,
                "effects": _effects(deltas, balances),
            },
            trace_id=trace_id,
            payee_id=payee_id,
            obligation_id=obligation_id,
            needs_classification=needs_classification or None,
        ),
    )


def salary_confirmed(
    *,
    user_id: str,
    trace_id: str | None,
    salary_event_id: str,
    occurred_at: datetime,
    app_date: date,
    period_date: date,
    decision: str,
    amount_vnd: int,
    salary_updated: bool,
    deltas: Mapping[str, int],
    balances: Mapping[str, int],
) -> Event:
    """`salary.confirmed`: `jar_codes` là các hũ NHẬN tiền (rỗng khi giữ ở Tiền vào khác)."""
    received = {c: d for c, d in deltas.items() if d > 0}
    return Event(
        "salary.confirmed",
        _put(
            {
                "v": EVENT_VERSION,
                "event_id": salary_event_id,
                "user_id": user_id,
                "salary_event_id": salary_event_id,
                "occurred_at": format_instant(occurred_at),
                "app_date": app_date.isoformat(),
                "period_date": period_date.isoformat(),
                "decision": decision,
                "amount_vnd": int(amount_vnd),
                "salary_updated": bool(salary_updated),
                "jar_codes": list(received),
                "effects": _effects(deltas, balances),
            },
            trace_id=trace_id,
        ),
    )


def obligation_changed(
    *,
    user_id: str,
    trace_id: str | None,
    obligation_id: str,
    occurred_at: datetime,
    app_date: date,
    change: str,
    kind: str,
    pay_jar: str | None = None,
    due_date: date | None = None,
) -> Event:
    """`obligation.changed`: `event_id` mới mỗi lần (một nghĩa vụ đổi nhiều lần)."""
    return Event(
        "obligation.changed",
        _put(
            {
                "v": EVENT_VERSION,
                "event_id": str(uuid.uuid4()),
                "user_id": user_id,
                "obligation_id": obligation_id,
                "occurred_at": format_instant(occurred_at),
                "app_date": app_date.isoformat(),
                "change": change,
                "kind": kind,
            },
            trace_id=trace_id,
            pay_jar=pay_jar,
            due_date=due_date.isoformat() if due_date else None,
        ),
    )


def profile_updated(
    *,
    user_id: str,
    trace_id: str | None,
    occurred_at: datetime,
    app_date: date,
    fields: Sequence[str],
) -> Event:
    """`profile.updated`: yêu cầu tính lại dự báo MỌI hũ; `event_id` mới mỗi lần."""
    return Event(
        "profile.updated",
        _put(
            {
                "v": EVENT_VERSION,
                "event_id": str(uuid.uuid4()),
                "user_id": user_id,
                "occurred_at": format_instant(occurred_at),
                "app_date": app_date.isoformat(),
                "fields": list(dict.fromkeys(fields)),
            },
            trace_id=trace_id,
        ),
    )


def _emf(name: str, detail_type: str, **extra: Any) -> str:
    """Một dòng log theo Embedded Metric Format: CloudWatch tách thành metric `name` (không cần PutMetricData)."""
    return json.dumps(
        {
            "_aws": {
                "Timestamp": int(time.time() * 1000),
                "CloudWatchMetrics": [
                    {
                        "Namespace": METRIC_NAMESPACE,
                        "Dimensions": [["DetailType"]],
                        "Metrics": [{"Name": name, "Unit": "Count"}],
                    }
                ],
            },
            "DetailType": detail_type,
            name: 1,
            **extra,
        },
        ensure_ascii=False,
    )


class EventPublisher:
    """Phát sự kiện lên bus. `bus_name` rỗng thì chỉ log (môi trường chưa có bus); lỗi không bao giờ ném ra ngoài."""

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

    def publish(self, events: Iterable[Event], *, trace_id: str | None = None) -> bool:
        """Trả True nếu mọi sự kiện đã lên bus. Thất bại (kể cả một phần) thì log và metric rồi trả False."""
        items = list(events)
        if not items:
            return True
        if not self.bus_name:
            log.warning(
                json.dumps(
                    {"msg": "event_bus_not_configured", "types": [e.detail_type for e in items]}
                )
            )
            return False
        try:
            resp = self.client.put_events(
                Entries=[
                    {
                        "EventBusName": self.bus_name,
                        "Source": SOURCE,
                        "DetailType": e.detail_type,
                        "Detail": json.dumps(e.detail, ensure_ascii=False),
                    }
                    for e in items
                ]
            )
        except Exception as exc:
            for e in items:
                log.error(
                    _emf(
                        "EventPublishFailed",
                        e.detail_type,
                        msg="event_publish_failed",
                        trace_id=trace_id,
                        error=type(exc).__name__,
                    )
                )
            return False
        failed = int(resp.get("FailedEntryCount", 0))
        entries = resp.get("Entries", [])
        ok = True
        for e, r in zip(items, entries, strict=False):
            if r.get("ErrorCode"):
                ok = False
                log.error(
                    _emf(
                        "EventPublishFailed",
                        e.detail_type,
                        msg="event_publish_failed",
                        trace_id=trace_id,
                        error=str(r.get("ErrorCode")),
                    )
                )
            else:
                log.info(
                    _emf("EventPublished", e.detail_type, msg="event_published", trace_id=trace_id)
                )
        return ok and failed == 0
