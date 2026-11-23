"""Consumer SQS của đường sự kiện (Lambda `yofina-on-transaction`): sự kiện ledger -> dự báo cập nhật.

Luật xử lý (contracts/README.md, mục "Sự kiện"):

| Sự kiện | Việc |
|---|---|
| `transaction.recorded` | chỉnh NHANH các hũ trong `jar_codes` (`update_forecast`); khoản mua bằng hạn mức (`funding_source` credit) không đổi số dư hũ nên bỏ qua (nghĩa vụ mới đã có sự kiện `obligation.changed`); dòng gắn nghĩa vụ (`obligation_id`) làm đổi lịch nên chạy ĐẦY ĐỦ; dòng ngoài ví (`funding_source` external, nạp từ tệp) không đổi số dư nhưng đổi lịch sử chi nên chạy ĐẦY ĐỦ |
| `salary.confirmed`, `obligation.changed`, `profile.updated` | chạy ĐẦY ĐỦ mọi hũ |

Sau bước dự báo, mỗi người dùng có thêm bước "nghi đổi hành vi" (`change.suspect_and_store`: CUSUM trên chuỗi chi theo tuần, ghi
`behavior_flags` trạng thái suspected, KHÔNG phát sự kiện; PELT xác nhận là việc của batch đêm). Lỗi của bước này không làm hỏng việc
cập nhật dự báo đã xong: ghi log và metric `ChangeSuspectFailed`, sự kiện vẫn `done`.

Nhiều sự kiện của cùng một người dùng trong một lô được gộp thành MỘT lần chạy (hợp các hũ; chỉ cần một sự kiện đòi chạy đầy đủ là
chạy đầy đủ). Idempotency theo `event_id` (DynamoDB, `idempotency.py`): sự kiện đã `done` thì bỏ qua; lỗi thì nhả khóa và báo lỗi từng mục
(partial batch response) để SQS giao lại; quá `maxReceiveCount` thì vào DLQ (có alarm).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from yofina_core.errors import ErrorCode, YofinaError
from yofina_forecast import change
from yofina_forecast.events import BadEvent, LedgerEvent, emf, parse_envelope
from yofina_forecast.idempotency import Claim, IdempotencyStore
from yofina_forecast.runner import Pipeline

log = logging.getLogger("yofina.forecast.consumer")

FULL_EVENT_TYPES = ("salary.confirmed", "obligation.changed", "profile.updated")


@dataclass(frozen=True)
class Plan:
    """Việc cần làm cho một nhóm sự kiện của một người dùng."""

    full: bool
    jars: tuple[str, ...]

    @property
    def nothing(self) -> bool:
        return not self.full and not self.jars


def plan_event(ev: LedgerEvent) -> Plan:
    """Một sự kiện -> việc cần làm (xem bảng ở đầu module)."""
    if ev.detail_type in FULL_EVENT_TYPES:
        return Plan(True, ())
    d = ev.detail
    if d.get("obligation_id"):
        return Plan(True, ())
    if d.get("funding_source") == "credit":
        return Plan(False, ())
    if d.get("funding_source") == "external":
        # chi hoặc thu ngoài ví (nạp từ tệp, migration 0050): số dư hũ không đổi nhưng lịch sử chi và độ phủ dữ liệu đổi,
        # nên phải fit lại (chạy ĐẦY ĐỦ), không chỉnh nhanh trên phân phối cũ.
        return Plan(True, ())
    jars = tuple(dict.fromkeys(str(c) for c in d.get("jar_codes") or ()))
    return Plan(False, jars)


def merge_plans(plans: Iterable[Plan]) -> Plan:
    full, jars = False, []
    for p in plans:
        full = full or p.full
        jars.extend(j for j in p.jars if j not in jars)
    return Plan(full, tuple(jars))


@dataclass
class _Item:
    record_id: str
    event: LedgerEvent


@dataclass
class BatchReport:
    """Kết quả một lô (để log và test): mục lỗi trả cho SQS, các đếm theo loại."""

    failures: list[str] = field(default_factory=list)
    processed: int = 0
    duplicates: int = 0
    skipped: int = 0
    runs: list[dict[str, Any]] = field(default_factory=list)
    #: kết quả bước "nghi đổi hành vi" của từng người dùng (`ChangeReport.to_dict`)
    changes: list[dict[str, Any]] = field(default_factory=list)

    def sqs_response(self) -> dict[str, Any]:
        return {"batchItemFailures": [{"itemIdentifier": i} for i in self.failures]}


def process_records(
    records: Sequence[Mapping[str, Any]],
    pipeline: Pipeline,
    idem: IdempotencyStore,
    *,
    now: datetime | None = None,
    change_store: change.FlagStore | None = None,
) -> BatchReport:
    """Xử lý một lô tin nhắn SQS. Không ném ngoại lệ: lỗi từng mục vào `failures` (partial batch response).

    `change_store` thay kho `behavior_flags` mặc định (kho Aurora của `pipeline.repo`); chỉ test dùng."""
    report = BatchReport()
    parsed: list[_Item] = []
    seen: set[str] = set()
    for rec in records:
        rid = str(rec.get("messageId", ""))
        try:
            ev = parse_envelope(rec.get("body", ""))
        except BadEvent as exc:
            log.error(json.dumps({"msg": "bad_event", "record": rid, "error": str(exc)}))
            report.failures.append(rid)  # không thử lại được: chuyển DLQ sau maxReceiveCount
            continue
        if ev.event_id in seen:  # cùng event_id trong một lô: chỉ xử lý một lần
            report.duplicates += 1
            continue
        seen.add(ev.event_id)
        parsed.append(_Item(rid, ev))

    by_user: dict[str, list[_Item]] = {}
    for item in parsed:
        by_user.setdefault(item.event.user_id, []).append(item)

    for user_id, items in by_user.items():
        _process_user(
            user_id, items, pipeline, idem, report, now or datetime.now(UTC), change_store
        )
    return report


def _process_user(
    user_id: str,
    items: list[_Item],
    pipeline: Pipeline,
    idem: IdempotencyStore,
    report: BatchReport,
    now: datetime,
    change_store: change.FlagStore | None = None,
) -> None:
    claimed: list[_Item] = []
    for item in items:
        try:
            state = idem.claim(item.event.event_id, user_id=user_id)
        except Exception as exc:  # DynamoDB lỗi: thử lại lần sau
            log.error(json.dumps({"msg": "idempotency_error", "error": type(exc).__name__}))
            report.failures.append(item.record_id)
            continue
        if state is Claim.DUPLICATE:
            report.duplicates += 1
            log.info(json.dumps({"msg": "duplicate_event", "event_id": item.event.event_id}))
        elif state is Claim.BUSY:
            report.failures.append(item.record_id)  # đang được xử lý ở nơi khác: giao lại sau
        else:
            claimed.append(item)
    if not claimed:
        return

    for item in claimed:
        at = item.event.occurred_at
        if at is not None:
            lag_ms = max((now - at).total_seconds() * 1000, 0)
            log.info(
                emf(
                    "EventLagMs",
                    round(lag_ms, 1),
                    "Milliseconds",
                    DetailType=item.event.detail_type,
                )
            )

    plan = merge_plans(plan_event(i.event) for i in claimed)
    run_id: str | None = None
    try:
        if plan.nothing:
            report.skipped += len(claimed)
        else:
            out = pipeline.run_user(
                user_id,
                trigger="event",
                jar_codes=plan.jars or None,
                force_full=plan.full,
                source_event_id=claimed[-1].event.event_id,
            )
            report.runs.append(out.to_dict())
            run_id = out.run_id
            if out.status == "skipped":
                report.skipped += len(claimed)
    except YofinaError as exc:
        if exc.code in (ErrorCode.PROFILE_INCOMPLETE, ErrorCode.FORECAST_UNAVAILABLE):
            # người dùng chưa khai đủ: không có gì để dự báo, không phải lỗi (sự kiện profile.updated sẽ tới sau)
            report.skipped += len(claimed)
        else:
            _fail(claimed, idem, report, exc)
            return
    except Exception as exc:
        _fail(claimed, idem, report, exc)
        return
    if not plan.nothing:
        _suspect_changes(user_id, plan, pipeline, report, change_store)
    for item in claimed:
        try:
            idem.complete(item.event.event_id, run_id=run_id)
        except (
            Exception
        ) as exc:  # đã tính xong; lần giao lại sẽ tính lại (an toàn vì tính lại không cộng dồn)
            log.error(
                json.dumps({"msg": "idempotency_complete_error", "error": type(exc).__name__})
            )
            report.failures.append(item.record_id)
            continue
        report.processed += 1


def _suspect_changes(
    user_id: str,
    plan: Plan,
    pipeline: Pipeline,
    report: BatchReport,
    store: change.FlagStore | None,
) -> None:
    """Bước "nghi đổi hành vi" sau dự báo. KHÔNG BAO GIỜ ném ra: dự báo đã ghi xong, một lỗi ở đây không được làm sự kiện bị giao lại."""
    try:
        out = change.suspect_and_store(
            pipeline, user_id, pipeline.now(), plan.jars or None, store=store
        )
        if out.checked or out.suspected or out.errors:
            report.changes.append(out.to_dict())
    except Exception as exc:
        log.error(
            json.dumps(
                {"msg": "change_suspect_failed", "error": f"{type(exc).__name__}: {exc}"[:300]}
            )
        )
        log.error(emf("ChangeSuspectFailed", 1, error=type(exc).__name__))


def _fail(items: list[_Item], idem: IdempotencyStore, report: BatchReport, exc: Exception) -> None:
    log.error(
        json.dumps(
            {
                "msg": "event_processing_failed",
                "error": f"{type(exc).__name__}: {exc}"[:300],
                "events": [i.event.event_id for i in items],
            }
        ),
        exc_info=not isinstance(exc, YofinaError),
    )
    for item in items:
        idem.release(item.event.event_id)
        report.failures.append(item.record_id)
