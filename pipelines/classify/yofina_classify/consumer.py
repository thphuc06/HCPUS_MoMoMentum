"""Consumer SQS của Lambda `yofina-classify`: sự kiện `transaction.recorded` có `needs_classification` -> phân loại một giao dịch.

Mỗi bản tin một giao dịch, độc lập nhau (không gộp theo người dùng). Idempotency theo `event_id` (DynamoDB, `idempotency.py`): sự kiện đã `done`
bị bỏ qua; đang xử lý ở nơi khác (`BUSY`) hoặc lỗi hạ tầng thì báo lỗi từng mục (partial batch response) để SQS giao lại; quá `maxReceiveCount`
vào DLQ (có alarm). Giao dịch người dùng đã tự chọn hũ bị bỏ qua (`ClassifyService`). Lỗi tạm thời của model (`AllModelsFailed`) được thử lại cho
tới lần giao cuối, rồi SUY GIẢM: giao dịch ở lại Chưa phân loại và vào hỏi gộp (không mất, không kẹt DLQ vì model nghẽn).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from yofina_classify.idempotency import Claim, IdempotencyStore
from yofina_classify.service import ClassifyService

log = logging.getLogger("yofina.classify.consumer")

LEDGER_SOURCE = "yofina.ledger"
DETAIL_TYPE = "transaction.recorded"
RECEIVE_COUNT_ATTR = "ApproximateReceiveCount"


class BadEvent(ValueError):
    """Thân tin nhắn không phải sự kiện hợp lệ (không thử lại được: chuyển DLQ sau maxReceiveCount)."""


@dataclass(frozen=True)
class TxEvent:
    event_id: str
    user_id: str
    transaction_id: str
    trace_id: str | None
    needs_classification: bool


def parse_event(body: str | Mapping[str, Any]) -> TxEvent:
    try:
        env = json.loads(body) if isinstance(body, str) else dict(body)
    except ValueError as exc:
        raise BadEvent("thân tin nhắn không phải JSON") from exc
    if (
        not isinstance(env, dict)
        or env.get("detail-type") != DETAIL_TYPE
        or env.get("source") != LEDGER_SOURCE
    ):
        raise BadEvent(f"không phải {DETAIL_TYPE} của {LEDGER_SOURCE}")
    d = env.get("detail")
    if not isinstance(d, dict):
        raise BadEvent("thiếu detail")
    ids = [d.get("event_id"), d.get("user_id"), d.get("transaction_id")]
    if not all(isinstance(x, str) and x for x in ids):
        raise BadEvent("thiếu event_id, user_id hoặc transaction_id")
    trace = d.get("trace_id")
    return TxEvent(
        ids[0],
        ids[1],
        ids[2],
        trace if isinstance(trace, str) and trace else None,
        bool(d.get("needs_classification")),
    )


@dataclass
class BatchReport:
    failures: list[str] = field(default_factory=list)
    assigned: int = 0
    asked: int = 0
    skipped: int = 0
    duplicates: int = 0

    def sqs_response(self) -> dict[str, Any]:
        return {"batchItemFailures": [{"itemIdentifier": i} for i in self.failures]}


def process_records(
    records: Sequence[Mapping[str, Any]],
    service: ClassifyService,
    idem: IdempotencyStore,
    *,
    max_receive_count: int,
) -> BatchReport:
    """Xử lý một lô bản tin SQS. Không ném ngoại lệ: lỗi từng mục vào `failures`."""
    report = BatchReport()
    seen: set[str] = set()
    for rec in records:
        rid = str(rec.get("messageId", ""))
        try:
            ev = parse_event(rec.get("body", ""))
        except BadEvent as exc:
            log.error(json.dumps({"msg": "bad_event", "record": rid, "error": str(exc)}))
            report.failures.append(rid)
            continue
        if not ev.needs_classification:
            report.skipped += 1  # luật EventBridge đã lọc; phòng thủ
            continue
        if ev.event_id in seen:
            report.duplicates += 1
            continue
        seen.add(ev.event_id)
        try:
            state = idem.claim(ev.event_id, user_id=ev.user_id)
        except Exception as exc:
            log.error(json.dumps({"msg": "idempotency_error", "error": type(exc).__name__}))
            report.failures.append(rid)
            continue
        if state is Claim.DUPLICATE:
            report.duplicates += 1
            continue
        if state is Claim.BUSY:
            report.failures.append(rid)
            continue
        receive = int((rec.get("attributes") or {}).get(RECEIVE_COUNT_ATTR, 1) or 1)
        try:
            out = service.run(
                ev.user_id,
                ev.transaction_id,
                trace_id=ev.trace_id,
                degrade_on_transient=receive >= max_receive_count,
            )
        except Exception as exc:
            log.error(
                json.dumps(
                    {
                        "msg": "classify_failed",
                        "event_id": ev.event_id,
                        "error": f"{type(exc).__name__}: {exc}"[:300],
                    }
                ),
                exc_info=True,
            )
            idem.release(ev.event_id)
            report.failures.append(rid)
            continue
        try:
            idem.complete(ev.event_id)
        except (
            Exception
        ) as exc:  # đã phân loại xong; lần giao lại sẽ thấy giao dịch đã có hũ và bỏ qua
            log.error(
                json.dumps({"msg": "idempotency_complete_error", "error": type(exc).__name__})
            )
        if out.status == "assigned":
            report.assigned += 1
        elif out.status == "asked":
            report.asked += 1
        else:
            report.skipped += 1
    return report
