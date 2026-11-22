"""Điểm vào của Lambda `yofina-on-transaction`: consumer SQS của sự kiện ledger. Xem `yofina_forecast/consumer.py`."""

from __future__ import annotations

from typing import Any

from yofina_forecast import bootstrap
from yofina_forecast.consumer import process_records


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    report = process_records(
        event.get("Records", []), bootstrap.pipeline(), bootstrap.idempotency()
    )
    return report.sqs_response()
