"""Điểm vào của Lambda `yofina-classify`: consumer SQS của `transaction.recorded` cần phân loại. Xem `yofina_classify/consumer.py`."""

from __future__ import annotations

from typing import Any

from yofina_classify import bootstrap
from yofina_classify.consumer import process_records


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    report = process_records(
        event.get("Records", []),
        bootstrap.service(),
        bootstrap.idempotency(),
        max_receive_count=bootstrap.settings().max_receive_count,
    )
    return report.sqs_response()
