"""Điểm vào Lambda yofina-roadmap-regen cho EventBridge và SQS."""

from __future__ import annotations

import logging
from typing import Any

from yofina_roadmap import bootstrap
from yofina_roadmap.events import parse_event
from yofina_roadmap.repo import JobBusy

log = logging.getLogger(__name__)


def _process(body: Any) -> str:
    event = parse_event(body)
    if event.job_id is None and event.trigger is None:
        return "skipped"
    return bootstrap.runner().process(event)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    if "Records" not in event:
        return {"status": _process(event)}

    failures = []
    for record in event["Records"]:
        record_id = record["messageId"]
        try:
            _process(record["body"])
        except JobBusy:
            failures.append({"itemIdentifier": record_id})
        except Exception as exc:
            log.warning("roadmap_event_retry record=%s type=%s", record_id, type(exc).__name__)
            failures.append({"itemIdentifier": record_id})
    return {"batchItemFailures": failures}
