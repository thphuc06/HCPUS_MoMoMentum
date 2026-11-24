"""Worker của một job nạp: S3 ObjectCreated -> SQS -> hàm này (`gateway/tools/ingest/handler_worker.py` gọi `handle_sqs`).

Một bản tin SQS (thân là thông báo S3) xử lý như sau:

1. Khóa S3 `{prefix}{user_id}/{job_id}` cho biết người dùng và job; job phải ở `awaiting_upload` và `s3_key` đã lưu phải trùng khóa này,
   không thì BỎ QUA (tải lại cùng URL, khóa lạ, bản tin kiểm tra của S3).
2. Đọc tệp, băm `content_sha256`: trùng nội dung với job còn sống khác thì job này `rejected` (`INGEST_DUPLICATE_FILE`).
3. `queued` -> `processing`, trích dòng (`extract.extract_rows`, che PII ngay, gán hũ bằng bộ phân loại phase 4 với nhãn k-NN và lịch sử
   của chính người dùng), khử trùng với sổ cái (`app_find_ingest_matches`),
   ghi `ingest_rows`, tính độ phủ hiện tại, job sang `review`. Tệp gốc xóa khỏi S3 sau khi đọc xong (không giữ ảnh).
4. Lỗi vĩnh viễn (tệp không đọc được, không phải tài chính, hết hạn mức model) -> job `rejected`/`failed` với mã lỗi, bản tin coi như xong.
   Lỗi tạm thời (Aurora đang dậy, model nghẽn) -> ném lại để SQS giao lại; đến lần giao cuối thì job được đánh dấu `failed` TRƯỚC khi bản
   tin vào DLQ, nên người dùng không kẹt ở `processing`. Trả `batchItemFailures` theo từng bản tin (partial batch response).
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from yofina_core.clock import app_today
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.ingest import IngestSettings, content_sha256, coverage_ratio, row_dedupe_key
from yofina_core.llm import LlmGateway
from yofina_core.params import fold_text
from yofina_core.pii import PiiPolicy
from yofina_ingest.context import ExtractContext, jars_from_rows
from yofina_ingest.extract import (
    ERROR_CODE_OF,
    Candidate,
    ExtractError,
    ExtractionResult,
    extract_rows,
)
from yofina_ingest.repo import IngestRepo
from yofina_ingest.settings import IngestRuntime

log = logging.getLogger("yofina.ingest.worker")

#: lỗi tạm thời: giao lại thay vì đánh dấu job hỏng ngay
TRANSIENT_CODES = {ErrorCode.DATABASE_UNAVAILABLE}
SQS_RECEIVE_COUNT = "ApproximateReceiveCount"


class JobSkipped(Exception):
    """Bản tin không ứng với việc cần làm (job không còn chờ tệp, khóa lạ). Không phải lỗi."""


@dataclass
class Outcome:
    status: str  # processed | skipped | failed | rejected
    job_id: str | None = None
    detail: str | None = None


class Storage:
    """Phần S3 mà worker cần (thay bằng giả trong test)."""

    def __init__(self, client: Any = None, region: str | None = None) -> None:
        self._client = client
        self._region = region

    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("s3", region_name=self._region)
        return self._client

    def get(self, bucket: str, key: str, max_bytes: int) -> bytes:
        """Đọc tối đa `max_bytes + 1` byte (thừa thì người gọi biết là quá lớn mà không phải đọc cả tệp)."""
        resp = self.client.get_object(Bucket=bucket, Key=key, Range=f"bytes=0-{max_bytes}")
        return resp["Body"].read()

    def delete(self, bucket: str, key: str) -> None:
        self.client.delete_object(Bucket=bucket, Key=key)


def parse_key(key: str, prefix: str) -> tuple[str, str] | None:
    """`(user_id, job_id)` từ khóa `{prefix}{user_id}/{job_id}`; None nếu sai dạng."""
    if not key.startswith(prefix):
        return None
    rest = key[len(prefix) :].split("/")
    if len(rest) != 2 or not rest[0] or not rest[1]:
        return None
    try:
        import uuid

        uuid.UUID(rest[1])
    except ValueError:
        return None
    return rest[0], rest[1]


def s3_records(body: Mapping[str, Any]) -> list[tuple[str, str]]:
    """`[(bucket, key)]` của mọi bản ghi `ObjectCreated` trong thân bản tin SQS (thông báo S3). Bản tin kiểm tra thì rỗng."""
    out = []
    for rec in body.get("Records") or []:
        s3 = rec.get("s3") or {}
        bucket = (s3.get("bucket") or {}).get("name")
        key = (s3.get("object") or {}).get("key")
        if bucket and key and str(rec.get("eventName", "")).startswith("ObjectCreated"):
            out.append((bucket, urllib.parse.unquote_plus(key)))
    return out


class Worker:
    def __init__(
        self,
        repo: IngestRepo,
        storage: Storage,
        runtime: IngestRuntime,
        *,
        gateway: LlmGateway | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repo = repo
        self.storage = storage
        self.rt = runtime
        self.gateway = gateway
        self._clock = clock or (lambda: datetime.now(UTC))

    # --- ngữ cảnh ------------------------------------------------------------------------------------------------------------
    def build_context(self, uid: str, today: date, display_name: str | None) -> ExtractContext:
        jars = jars_from_rows(self.repo.jar_rows(uid))
        try:
            payees = self.repo.payee_names(uid)
        except YofinaError:
            payees = []
        self_names = [display_name] if display_name else []
        return ExtractContext(
            jars=jars,
            type_map=self.repo.tx_types(),
            rules=self.repo.rules(uid),
            policy=PiiPolicy.build(keep=payees, self_names=self_names),
            today=today,
            settings=self.rt.settings,
            user_id=uid,
            store=self.repo.label_store(),
            tz=ZoneInfo(self.rt.app_timezone),
        )

    # --- một tệp -------------------------------------------------------------------------------------------------------------
    def process_object(self, bucket: str, key: str, *, last_attempt: bool = False) -> Outcome:
        ids = parse_key(key, self.rt.upload_prefix)
        if ids is None or bucket != self.rt.bucket:
            log.info(json.dumps({"msg": "ingest_skip", "why": "foreign_key"}))
            return Outcome("skipped", detail="foreign_key")
        uid, job_id = ids
        try:
            return self._process(uid, job_id, bucket, key, last_attempt)
        except YofinaError as exc:
            if exc.code in TRANSIENT_CODES:
                if last_attempt:
                    self._fail(
                        uid, job_id, exc.code.value, "Hệ thống đang bận, hãy thử lại sau ít phút."
                    )
                raise
            self._fail(uid, job_id, "INTERNAL_ERROR")
            return Outcome("failed", job_id, str(exc.code))
        except Exception:
            log.exception("ingest_unhandled job=%s", job_id)
            if last_attempt:
                self._fail(uid, job_id, "INTERNAL_ERROR")
            raise

    def _fail(self, uid: str, job_id: str, code: str, message: str | None = None) -> None:
        try:
            self.repo.update_job(
                uid,
                job_id,
                "failed",
                patch={
                    "error_code": code,
                    "error_message": message or "Không xử lý được tệp này. Hãy thử lại sau.",
                },
            )
        except Exception:
            log.exception("ingest_mark_failed_error job=%s", job_id)

    def _reject(
        self, uid: str, job_id: str, code: str, message: str, *, status: str = "rejected"
    ) -> Outcome:
        self.repo.update_job(
            uid, job_id, status, patch={"error_code": code, "error_message": message[:280]}
        )
        return Outcome(status, job_id, code)

    def _process(self, uid: str, job_id: str, bucket: str, key: str, last_attempt: bool) -> Outcome:
        found = self.repo.get_job(uid, job_id, row_limit=1)
        if found is None:
            return Outcome("skipped", job_id, "job_not_found")
        job, _ = found
        # `awaiting_upload` là lần đầu; `queued`/`processing` là lần giao lại sau lỗi tạm thời (tệp gốc còn nguyên trên S3)
        if (
            job["status"] not in ("awaiting_upload", "queued", "processing")
            or job.get("s3_key") != key
        ):
            log.info(
                json.dumps(
                    {"msg": "ingest_skip", "why": "job_not_awaiting", "status": job["status"]}
                )
            )
            return Outcome("skipped", job_id, "job_not_awaiting")
        status = job["status"]
        settings: IngestSettings = self.rt.settings
        kind = job["source_kind"]
        max_bytes = settings.max_bytes(kind)
        try:
            data = self.storage.get(bucket, key, max_bytes)
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404"):
                return Outcome("skipped", job_id, "object_missing")
            raise
        if len(data) > max_bytes:
            return self._reject(
                uid, job_id, "INGEST_TOO_LARGE", "Tệp lớn hơn giới hạn cho phép.", status="rejected"
            )
        sha = content_sha256(data)
        dup = self.repo.find_job_by_content(uid, sha)
        if dup is not None and str(dup["id"]) != job_id:
            self._delete_object(bucket, key)
            return self._reject(
                uid, job_id, "INGEST_DUPLICATE_FILE", "Tệp này đã được nạp rồi (cùng nội dung)."
            )
        if status == "awaiting_upload":
            try:
                queued = self.repo.update_job(
                    uid, job_id, "queued", 5, {"content_sha256": sha, "size_bytes": len(data)}
                )
            except (
                YofinaError
            ) as exc:  # khóa duy nhất theo nội dung: hai tệp giống nhau tới cùng lúc
                if exc.code != ErrorCode.INTERNAL_ERROR:
                    raise
                return self._reject(
                    uid, job_id, "INGEST_DUPLICATE_FILE", "Tệp này đã được nạp rồi (cùng nội dung)."
                )
            if queued is None:
                return Outcome("skipped", job_id, "job_state_changed")
            status = "queued"
        if status == "queued":
            self.repo.update_job(uid, job_id, "processing", 15)

        user = self.repo.user(uid)
        now = self._clock()
        today = app_today(
            user.clock_offset_days if user else 0, now, ZoneInfo(self.rt.app_timezone)
        )
        ctx = self.build_context(uid, today, user.display_name if user else None)
        try:
            result = extract_rows(
                data,
                filename="",
                content_type=job["mime"],
                ctx=ctx,
                gateway=self.gateway,
                source_kind=kind,
            )
        except ExtractError as exc:
            if exc.code == "model_failed" and not last_attempt:
                raise  # model nghẽn: giao lại bản tin (tệp gốc giữ nguyên)
            self._delete_object(bucket, key)
            outcome_status = (
                "failed" if exc.code in ("budget_exceeded", "model_failed") else "rejected"
            )
            return self._reject(
                uid,
                job_id,
                ERROR_CODE_OF.get(exc.code, "INTERNAL_ERROR"),
                exc.message,
                status=outcome_status,
            )
        self.repo.update_job(
            uid, job_id, "processing", 70, {"model": (result.model or "")[:80] or None}
        )
        self._store(uid, job_id, sha, result, now)
        self._delete_object(bucket, key)
        return Outcome("processed", job_id)

    def _delete_object(self, bucket: str, key: str) -> None:
        try:
            self.storage.delete(bucket, key)
        except Exception:
            log.warning(json.dumps({"msg": "ingest_delete_object_failed"}))

    # --- khử trùng và ghi ----------------------------------------------------------------------------------------------------
    def _store(
        self, uid: str, job_id: str, sha: str, result: ExtractionResult, now: datetime
    ) -> None:
        window = self.rt.settings.ingest_dedupe_window_days
        cands = result.candidates
        matches = self.repo.find_matches(
            uid,
            [
                {
                    "idx": c.seq,
                    "app_date": c.app_date.isoformat(),
                    "amount_vnd": c.amount_vnd,
                    "counterparty": fold_text(c.counterparty or ""),
                    "kind": c.kind,
                }
                for c in cands
            ],
            window,
        )
        best = pick_matches(matches)
        rows = [to_row(c, sha, best.get(c.seq)) for c in cands]
        self.repo.update_job(uid, job_id, "processing", 85)
        ids = self.repo.insert_rows(uid, job_id, rows)
        stored = {r["seq"]: r for r in rows if r["seq"] in ids}
        n_dup = sum(1 for r in stored.values() if r["review_status"] == "duplicate")
        n_auto = sum(1 for r in stored.values() if r["review_status"] == "auto_added")
        n_review = len(stored) - n_dup
        facts = self.repo.coverage_facts(
            uid, now, self.rt.app_timezone, self.rt.forecast_history_window_days
        )
        patch: dict[str, Any] = {
            "rows_total": len(stored),
            "rows_auto_added": n_auto,
            "rows_review": n_review,
            "rows_duplicate": n_dup,
        }
        cov = coverage_ratio(facts)
        if cov is not None:
            patch["coverage_before"] = cov
        if not stored:  # mọi dòng đã có trong hệ thống (khóa khử trùng): không còn gì để duyệt
            self.repo.update_job(
                uid,
                job_id,
                "rejected",
                patch={
                    "error_code": "INGEST_DUPLICATE_FILE",
                    "error_message": "Mọi dòng trong tệp này đã được nạp trước đó.",
                },
            )
            return
        self.repo.update_job(uid, job_id, "review", 100, patch)


def pick_matches(matches: Sequence[Mapping[str, Any]]) -> dict[int, Mapping[str, Any]]:
    """Giao dịch trùng gần ngày nhất cho từng ứng viên; đối tác khớp được ưu tiên (hàm DB đã sắp, đây chọn lại cho chắc)."""
    best: dict[int, Mapping[str, Any]] = {}
    for m in matches:
        idx = int(m["idx"])
        cur = best.get(idx)
        key = (not bool(m["counterparty_match"]), abs(int(m["day_diff"])))
        if cur is None or key < (not bool(cur["counterparty_match"]), abs(int(cur["day_diff"]))):
            best[idx] = m
    return best


def to_row(c: Candidate, sha: str, match: Mapping[str, Any] | None) -> dict[str, Any]:
    """Dòng cho `app_insert_ingest_rows`. Dòng trùng sổ cái thành `duplicate` (không chọn sẵn, không chốt được)."""
    row: dict[str, Any] = {
        "seq": c.seq,
        "kind": c.kind,
        "app_date": c.app_date.isoformat(),
        "amount_vnd": c.amount_vnd,
        "counterparty": c.counterparty,
        "description": c.description,
        "extract_confidence": c.extract_confidence,
        "suggested_jar_code": c.jar_code if c.kind == "expense" else None,
        "jar_confidence": c.jar_confidence if c.kind == "expense" and c.jar_code else None,
        "jar_source": c.jar_source if c.kind == "expense" and c.jar_code else None,
        "tx_type": c.tx_type,
        "dedupe_key": row_dedupe_key(
            app_date=c.app_date,
            amount_vnd=c.amount_vnd,
            counterparty=c.counterparty,
            content_sha256=sha,
            seq=c.seq,
        ),
    }
    if match is not None:
        row["review_status"] = "duplicate"
        row["duplicate_of_transaction_id"] = str(match["transaction_id"])
    else:
        row["review_status"] = "auto_added" if c.auto_add else "pending"
    return row


def handle_sqs(
    event: Mapping[str, Any], worker: Worker, *, max_receive_count: int
) -> dict[str, Any]:
    """Xử lý một lô bản tin SQS; trả `batchItemFailures` (chỉ các bản tin cần giao lại)."""
    failures: list[dict[str, str]] = []
    for rec in event.get("Records") or []:
        mid = rec.get("messageId", "")
        try:
            body = json.loads(rec.get("body") or "{}")
        except ValueError:
            log.error(json.dumps({"msg": "ingest_bad_body", "message_id": mid}))
            continue  # bản tin hỏng không bao giờ sửa được bằng cách giao lại
        receive = int((rec.get("attributes") or {}).get(SQS_RECEIVE_COUNT, "1") or 1)
        last = receive >= max_receive_count
        try:
            for bucket, key in s3_records(body):
                out = worker.process_object(bucket, key, last_attempt=last)
                log.info(
                    json.dumps(
                        {
                            "msg": "ingest_done",
                            "outcome": out.status,
                            "detail": out.detail,
                            "job_id": out.job_id,
                        }
                    )
                )
        except Exception as exc:
            log.warning(
                json.dumps(
                    {
                        "msg": "ingest_retry",
                        "message_id": mid,
                        "error": type(exc).__name__,
                        "receive": receive,
                    }
                )
            )
            failures.append({"itemIdentifier": mid})
    return {"batchItemFailures": failures}
