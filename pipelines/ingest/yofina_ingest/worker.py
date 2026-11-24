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
import re
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
from yofina_ingest.fx import FxConverter
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
        fx: FxConverter | None = None,
    ) -> None:
        self.repo = repo
        self.storage = storage
        self.rt = runtime
        self.gateway = gateway
        self._clock = clock or (lambda: datetime.now(UTC))
        #: bộ quy đổi ngoại tệ; vắng thì bộ của tiến trình với nguồn tỷ giá thật (`yofina_ingest.fx.default_converter`)
        self.fx = fx

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
            fx=self.fx,
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
        self,
        uid: str,
        job_id: str,
        code: str,
        message: str,
        *,
        status: str = "rejected",
        reason: str | None = None,
    ) -> Outcome:
        patch = {"error_code": code, "error_message": message[:280]}
        if reason:
            patch["error_reason"] = reason
        self.repo.update_job(uid, job_id, status, patch=patch)
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
                reason=exc.reason,
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
        # dòng ngoại tệ chưa có số VND không so được với sổ cái (khóa so là số tiền)
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
                if c.amount_vnd is not None
            ],
            window,
        )
        tx_ids = sorted({str(m["transaction_id"]) for m in matches})
        details = self.repo.matched_transactions(uid, tx_ids) if tx_ids else {}
        best = pick_matches(matches, {c.seq: c for c in cands}, window, details)
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


#: Nguồn trả của giao dịch TRONG ví (hũ, Trả sau). Ví ghi giao dịch lúc thanh toán, nên ảnh chụp hay bản xuất của CÙNG khoản đó mang
#: cùng ngày. Lệch tối đa `WALLET_MAX_DAY_DIFF` ngày (qua nửa đêm), không phải cả cửa sổ: cửa sổ khử trùng dành cho độ trễ ghi sổ giữa
#: hai chứng từ ngân hàng (biên lai và sao kê của cùng một lần chuyển). Một khoản trên sao kê ngân hàng không thể đồng thời trừ vào hũ
#: trong ví: HIGHLANDS COFFEE 45.000 ₫ ngày 31/10 của `c01` (mã FT riêng) và Highlands Coffee 45.000 ₫ trả từ hũ của `vy` ngày 29/10
#: là hai lần mua.
WALLET_FUNDING = frozenset({"jar", "credit"})
WALLET_MAX_DAY_DIFF = 1
#: Khi một bên KHÔNG BIẾT đối tác (đã che "N***" hay rỗng) và nội dung không gần giống: chỉ coi là trùng một giao dịch ngoài ví khi số
#: tiền đủ lớn để khó trùng ngẫu nhiên (tiền phòng, học phí, lương...) và lệch ngày không quá `UNKNOWN_PARTY_MAX_DAY_DIFF`. Khoản nhỏ
#: (cà phê, xe ôm) cùng số tiền rất thường gặp: không ẩn, để người dùng duyệt.
UNKNOWN_PARTY_LARGE_VND = 500_000
UNKNOWN_PARTY_MAX_DAY_DIFF = 1
#: Nội dung "gần giống": tỷ lệ từ chung trên tập từ ngắn hơn (overlap coefficient), sau khi bỏ từ chung của mọi nội dung ngân hàng.
TEXT_MIN_OVERLAP = 0.6
#: Từ xuất hiện trong gần như mọi nội dung chuyển khoản hay thanh toán (đã bỏ dấu, chữ thường): không phân biệt được hai khoản.
# fmt: off
GENERIC_TOKENS = frozenset({
    "ck", "chuyen", "khoan", "tien", "thanh", "toan", "qr", "tt", "gd", "giao", "dich", "nd", "noi", "dung", "ref", "ft",
    "mbvcb", "vcb", "ibft", "napas", "internet", "banking", "ib", "sms", "tk", "stk", "so", "tai", "cho", "den", "tu", "toi",
    "gui", "nhan", "va", "cua", "thang", "nam", "ngay", "vn", "the", "atm", "pay", "payment", "transfer",
})
# fmt: on


def known_party(name: str | None) -> str | None:
    """Đối tác đã chuẩn hóa, hoặc None khi KHÔNG BIẾT: rỗng hay đã che (`N***`, `[STK]`). Hai tên đã che cùng chữ cái đầu không phải
    là cùng một người, nên không dùng để so."""
    folded = fold_text(name or "")
    if not folded or "*" in folded or "[" in folded:
        return None
    return folded


def text_tokens(*parts: str | None) -> frozenset[str]:
    """Từ phân biệt được của đối tác và nội dung: tách theo mọi ký tự không phải chữ hay số, bỏ từ có chữ số (mã tham chiếu, số tài
    khoản đã che, "T11"), từ một ký tự (chữ cái của tên đã che) và `GENERIC_TOKENS`."""
    out: set[str] = set()
    for part in parts:
        for tok in re.split(r"[\W_]+", fold_text(part or "")):
            if len(tok) < 2 or any(ch.isdigit() for ch in tok) or tok in GENERIC_TOKENS:
                continue
            out.add(tok)
    return frozenset(out)


def texts_similar(a: frozenset[str], b: frozenset[str]) -> bool:
    if not a or not b:
        return False
    common = a & b
    return bool(common) and len(common) / min(len(a), len(b)) >= TEXT_MIN_OVERLAP


def is_duplicate_match(
    m: Mapping[str, Any],
    candidate: Candidate | None,
    existing: Mapping[str, Any] | None,
    window_days: int,
) -> bool:
    """Một giao dịch đã có (cùng chiều, cùng số tiền, lệch ngày trong cửa sổ, do `app_find_ingest_matches` lọc) có thật là CÙNG khoản
    với dòng nạp `candidate` không. `existing`: đối tác (`merchant`) và ghi chú (`note`) của giao dịch đó (`IngestRepo.matched_transactions`).

    1. Lệch ngày: giao dịch trong ví (`WALLET_FUNDING`) tối đa `WALLET_MAX_DAY_DIFF`, giao dịch ngoài ví tối đa cửa sổ khử trùng.
    2. Hai bên đều BIẾT đối tác: trùng khi và chỉ khi đối tác khớp (`counterparty_match` của hàm DB). Cùng số tiền ở cửa hàng khác là
       khoản khác: sao kê `c01` có 5 dòng bị đánh trùng giả theo cách cũ (Circle K 56.000 ₫ với GrabFood 56.000 ₫ hôm sau, Be 26.000 ₫
       với GrabFood cùng ngày...). Đối tác ngắn hơn 3 ký tự ("Be") hàm DB không so được nên không bao giờ khớp: dòng đó vào hàng chờ.
    3. Một bên KHÔNG BIẾT đối tác (`known_party`): đối tác đã che hay rỗng không phải là "khác". Trùng khi nội dung và đối tác gần giống
       (`texts_similar`), hoặc khi cả hai ở ngoài ví, số tiền từ `UNKNOWN_PARTY_LARGE_VND` và lệch ngày không quá
       `UNKNOWN_PARTY_MAX_DAY_DIFF`. Ca thật: ảnh `s02` (tiền phòng 1.500.000 ₫, đối tác "N***", "MINH CK tien phong thang 11") đã
       chốt, rồi dòng 15 của `c01` ("MBVCB.3765569.CK tien phong T11", bộ đọc CSV lấy đối tác "TIEN PHONG") cùng ngày 01/11.
    4. Không đọc được giao dịch đã có (`existing` None): chỉ tin đối tác khớp của hàm DB.
    """
    diff = abs(int(m["day_diff"]))
    wallet = m.get("funding_source") in WALLET_FUNDING
    limit = min(window_days, WALLET_MAX_DAY_DIFF) if wallet else window_days
    if diff > limit:
        return False
    if existing is None:
        return bool(m["counterparty_match"])
    cand_cp = candidate.counterparty if candidate else None
    cand_desc = candidate.description if candidate else None
    if known_party(cand_cp) and known_party(existing.get("merchant")):
        return bool(m["counterparty_match"])
    if texts_similar(
        text_tokens(cand_cp, cand_desc), text_tokens(existing.get("merchant"), existing.get("note"))
    ):
        return True
    amount = candidate.amount_vnd if candidate else 0
    return not wallet and amount >= UNKNOWN_PARTY_LARGE_VND and diff <= UNKNOWN_PARTY_MAX_DAY_DIFF


def pick_matches(
    matches: Sequence[Mapping[str, Any]],
    candidates: Mapping[int, Candidate] | None = None,
    window_days: int = 30,
    details: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[int, Mapping[str, Any]]:
    """Giao dịch trùng gần ngày nhất cho từng ứng viên, chỉ trong các khớp được `is_duplicate_match` nhận; đối tác khớp được ưu tiên
    (hàm DB đã sắp, đây chọn lại cho chắc). `candidates`: dòng nạp theo `idx`; `details`: đối tác và ghi chú của giao dịch đã có theo id
    (vắng: chỉ tin `counterparty_match`)."""
    best: dict[int, Mapping[str, Any]] = {}
    for m in matches:
        idx = int(m["idx"])
        existing = details.get(str(m["transaction_id"])) if details is not None else None
        if not is_duplicate_match(m, (candidates or {}).get(idx), existing, window_days):
            continue
        cur = best.get(idx)
        key = (not bool(m["counterparty_match"]), abs(int(m["day_diff"])))
        if cur is None or key < (not bool(cur["counterparty_match"]), abs(int(cur["day_diff"]))):
            best[idx] = m
    return best


def to_row(c: Candidate, sha: str, match: Mapping[str, Any] | None) -> dict[str, Any]:
    """Dòng cho `app_insert_ingest_rows`. Dòng trùng sổ cái thành `duplicate` (không chọn sẵn, không chốt được). Dòng ngoại tệ mang
    `fx`; chưa có tỷ giá thì không có `amount_vnd` và khóa khử trùng tính với số tiền 0 (khóa vẫn duy nhất nhờ `content_sha256` và
    `seq`, và là khóa của dòng sổ cái khi chốt)."""
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
            amount_vnd=c.amount_vnd or 0,
            counterparty=c.counterparty,
            content_sha256=sha,
            seq=c.seq,
        ),
    }
    if c.fx is not None:
        row["fx"] = c.fx.to_json()
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
