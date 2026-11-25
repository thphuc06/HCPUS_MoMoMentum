"""Nghiệp vụ của các route `/ingest/*` (Lambda `yofina-ingest-api`): không biết gì về HTTP.

- `user_id` luôn là đối số tường minh (claim `sub` của JWT); không bao giờ lấy từ thân yêu cầu.
- Ghi sổ cái CHỈ qua `apply_action` (tool `confirm_rows`): cùng luồng token với ledger (`yofina_core.confirm`: cùng khóa HMAC, cùng bảng
  `jti`, dùng một lần). Không token thì không ghi gì.
- "Hôm nay" luôn là `app_today(clock_offset_days, now, tz)`, không gọi `date.today()`.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from yofina_core.blocks import (
    block_to_wire,
    build_receipt_action,
    format_instant,
)
from yofina_core.clock import app_today
from yofina_core.confirm import (
    ConfirmService,
    ParamsError,
    hash_normalized_params,
    normalize_params,
)
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.ingest import (
    CONSENT_SOURCE_OF,
    SOURCE_KINDS,
    build_coverage_change,
    build_ingest_review,
    coverage_ratio,
)
from yofina_core.money import format_vnd
from yofina_core.params import JAR_CODE_RE
from yofina_core.quota import UPLOAD, AccountQuota
from yofina_core.quota import shared as shared_quota
from yofina_core.wallet import CONFIRM_ROWS, INGEST_ACTION_TOOLS
from yofina_ingest.context import jars_from_rows
from yofina_ingest.repo import IngestRepo, UserContext, row_amount
from yofina_ingest.settings import IngestRuntime

log = logging.getLogger("yofina.ingest.api")

LIST_DEFAULT_LIMIT = 10
LIST_MAX_LIMIT = 20
REVIEW_ROW_LIMIT = 500
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

Presigner = Callable[[str, str, str, int, int], Mapping[str, Any]]
ForecastTrigger = Callable[[str, str], bool]


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return format_instant(value if value.tzinfo else value.replace(tzinfo=UTC))
    text = str(value).strip().replace(" ", "T")
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return format_instant(dt if dt.tzinfo else dt.replace(tzinfo=UTC))


def _uuid(name: str, raw: Any, *, code: ErrorCode = ErrorCode.PARAMS_INVALID) -> str:
    if not isinstance(raw, str) or not _UUID.match(raw):
        raise YofinaError(code, f"{name} không hợp lệ.")
    return raw.lower()


def s3_presigner(region: str, client: Any = None) -> Presigner:
    """Presigned POST của S3 (SigV4): khóa, Content-Type và kích thước (`content-length-range`) bị ép trong policy đã ký."""

    def make(bucket: str, key: str, mime: str, max_bytes: int, ttl: int) -> Mapping[str, Any]:
        nonlocal client
        if client is None:
            import boto3
            from botocore.config import Config as BotoConfig

            client = boto3.client(
                "s3",
                region_name=region,
                config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "virtual"}),
            )
        return client.generate_presigned_post(
            Bucket=bucket,
            Key=key,
            Fields={"Content-Type": mime},
            Conditions=[{"Content-Type": mime}, ["content-length-range", 1, max_bytes]],
            ExpiresIn=ttl,
        )

    return make


class IngestApi:
    def __init__(
        self,
        repo: IngestRepo,
        confirm: ConfirmService,
        runtime: IngestRuntime,
        *,
        presigner: Presigner,
        forecast_trigger: ForecastTrigger | None = None,
        clock: Callable[[], datetime] | None = None,
        upload_quota: AccountQuota | None = None,
    ) -> None:
        self.repo = repo
        self.confirm = confirm
        self.rt = runtime
        self._presign = presigner
        self._forecast = forecast_trigger
        self._clock = clock or (lambda: datetime.now(UTC))
        # None: trần nạp tệp của tiến trình (`yofina_core.quota.shared`, bảng `YOFINA_USAGE_TABLE`; vắng thì tắt), tạo lười
        self._upload_quota = upload_quota

    # --- tiện ích ----------------------------------------------------------------------------------------------------------
    def now(self) -> datetime:
        return self._clock()

    def _user(self, uid: str) -> UserContext:
        u = self.repo.user(uid)
        if u is None:
            # tài khoản chưa có hồ sơ (chưa onboarding): chưa có hũ nào để nạp vào
            raise YofinaError(
                ErrorCode.PROFILE_INCOMPLETE,
                "Hãy hoàn tất thiết lập tài khoản trước khi nạp dữ liệu.",
            )
        return u

    def _today(self, user: UserContext, now: datetime):
        return app_today(user.clock_offset_days, now, self.rt.tz)

    # --- POST /ingest/uploads ------------------------------------------------------------------------------------------------
    def create_upload(self, uid: str, body: Mapping[str, Any], *, trace_id: str) -> dict[str, Any]:
        s = self.rt.settings
        kind = body.get("source_kind")
        mime = body.get("mime")
        size = body.get("size_bytes")
        consent = body.get("consent")
        if kind not in SOURCE_KINDS:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "source_kind phải là image hoặc csv.")
        if not isinstance(mime, str) or not 3 <= len(mime) <= 100:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Thiếu mime của tệp.")
        if isinstance(size, bool) or not isinstance(size, int) or size < 1:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "size_bytes phải là số nguyên dương.")
        if consent is not None and not isinstance(consent, bool):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "consent phải là true hoặc false.")
        mime = mime.split(";")[0].strip().lower()
        allowed = s.mime_types[kind]
        if mime not in allowed:
            raise YofinaError(ErrorCode.INGEST_UNSUPPORTED_TYPE, "Loại tệp này chưa được hỗ trợ.")
        max_bytes = s.max_bytes(kind)
        if size > max_bytes:
            raise YofinaError(
                ErrorCode.INGEST_TOO_LARGE,
                f"Tệp lớn hơn giới hạn {max_bytes // 1000} KB của loại này.",
            )
        self._user(uid)
        source = CONSENT_SOURCE_OF[kind]
        have = self.repo.consents(uid).get(source)
        if have is None or have.get("revoked_at") is not None:
            if consent is not True:
                raise YofinaError(
                    ErrorCode.CONSENT_REQUIRED,
                    "Bạn cần đồng ý cho Yofina đọc loại tệp này trước khi tải lên.",
                )
            self.repo.grant_consent(uid, source, s.ingest_consent_version)
        # Trần nạp tệp theo tài khoản mỗi ngày (#13): sau mọi bước kiểm (yêu cầu hỏng, chưa đồng ý thì không tính), trước khi tạo
        # job và ký URL. Chạm trần thì DAILY_QUOTA_EXCEEDED (429): không job, không URL; các route đọc khác không bị ảnh hưởng.
        (self._upload_quota or shared_quota(UPLOAD)).take(uid)
        # Ledger cũ đặt lại demo mà không xóa bảng nạp: dọn job mồ côi để nạp lại cùng tệp không vướng khóa trùng
        healed = self.repo.heal_after_reset(uid)
        if healed:
            log.info(json.dumps({"msg": "ingest_healed_after_reset", "jobs": healed}))
        job_id = str(uuid.uuid4())
        key = f"{self.rt.upload_prefix}{uid}/{job_id}"
        self.repo.create_job(uid, job_id, kind, key, mime, size)
        ttl = s.ingest_upload_url_ttl_seconds
        post = self._presign(self.rt.bucket, key, mime, max_bytes, ttl)
        return {
            "job_id": job_id,
            "key": key,
            "url": post["url"],
            "fields": dict(post["fields"]),
            "expires_at": format_instant(self.now() + timedelta(seconds=ttl)),
            "max_bytes": max_bytes,
            "mime_types": list(allowed),
        }

    # --- GET /ingest/jobs, GET /ingest/jobs/{id} -----------------------------------------------------------------------------
    def list_jobs(self, uid: str, limit: Any = None) -> dict[str, Any]:
        n = LIST_DEFAULT_LIMIT
        if limit not in (None, ""):
            try:
                n = int(limit)
            except (TypeError, ValueError):
                raise YofinaError(ErrorCode.PARAMS_INVALID, "limit phải là số nguyên.") from None
            if not 1 <= n <= LIST_MAX_LIMIT:
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID, f"limit phải từ 1 đến {LIST_MAX_LIMIT}."
                )
        jobs = []
        for r in self.repo.list_jobs(uid, n):
            item: dict[str, Any] = {
                "job_id": str(r["id"]),
                "status": r["status"],
                "source_kind": r["source_kind"],
                "progress": int(r["progress"]),
                "rows_total": int(r["rows_total"]),
                "created_at": _iso(r["created_at"]),
                "updated_at": _iso(r.get("finished_at") or r["created_at"]),
            }
            if r.get("error_code"):
                item["error_code"] = r["error_code"]
            if r.get("finished_at"):
                item["finished_at"] = _iso(r["finished_at"])
            jobs.append(item)
        return {"jobs": jobs}

    def get_job(
        self,
        uid: str,
        job_id_raw: Any,
        *,
        trace_id: str,
        source_tool: str = "rest:GET /ingest/jobs",
    ) -> dict[str, Any]:
        job_id = _uuid("job_id", job_id_raw, code=ErrorCode.INGEST_JOB_NOT_FOUND)
        found = self.repo.get_job(uid, job_id, REVIEW_ROW_LIMIT)
        if found is None:
            raise YofinaError(ErrorCode.INGEST_JOB_NOT_FOUND, "Không tìm thấy lần nạp này.")
        job, rows = found
        out: dict[str, Any] = {
            "job_id": job_id,
            "status": job["status"],
            "source_kind": job["source_kind"],
            "progress": int(job["progress"]),
            "rows_total": int(job["rows_total"]),
            "created_at": _iso(job["created_at"]),
            "updated_at": _iso(job["updated_at"]),
        }
        if job.get("error_code"):
            out["error_code"] = job["error_code"]
        if job.get("error_message"):
            out["error_message"] = job["error_message"]
        if job.get("error_reason"):
            out["error_reason"] = job["error_reason"]
        if job.get("finished_at"):
            out["finished_at"] = _iso(job["finished_at"])
        if job["status"] in ("review", "done"):
            user = self._user(uid)
            now = self.now()
            app_date = self._today(user, now)
            jars = self.repo.jar_rows(uid)
            block = build_ingest_review(
                job=job,
                rows=rows,
                jars=jars,
                trace_id=trace_id,
                source_tool=source_tool,
                as_of=now,
                app_date=app_date,
            )
            out["review"] = block_to_wire(block)
            if job["status"] == "done":
                approved = [r for r in rows if r["review_status"] == "approved"]
                names = {j["code"]: j["name"] for j in jars}
                codes: list[str] = []
                for r in approved:
                    c = r.get("suggested_jar_code")
                    if r["kind"] == "expense" and c and c not in codes:
                        codes.append(c)
                cov = build_coverage_change(
                    job_id=job_id,
                    before=_f(job.get("coverage_before")),
                    after=_f(job.get("coverage_after")),
                    rows_added=len(approved),
                    external_spend_added_vnd=sum(
                        int(r["amount_vnd"]) for r in approved if r["kind"] == "expense"
                    ),
                    external_income_added_vnd=sum(
                        int(r["amount_vnd"]) for r in approved if r["kind"] == "income"
                    ),
                    jars_affected=[{"code": c, "name": names.get(c, c)} for c in codes],
                    # lần chốt đã yêu cầu tính lại dự báo; trạng thái từng lần gọi không lưu lại
                    forecast_refresh="queued" if self._forecast is not None else "skipped",
                    trace_id=trace_id,
                    source_tool=source_tool,
                    as_of=now,
                    app_date=app_date,
                )
                out["coverage_change"] = block_to_wire(cov)
        return out

    # --- POST /ingest/rows/{row_id}/jar --------------------------------------------------------------------------------------
    def set_row_jar(self, uid: str, row_id_raw: Any, body: Mapping[str, Any]) -> dict[str, Any]:
        row_id = _uuid("row_id", row_id_raw, code=ErrorCode.INGEST_JOB_NOT_FOUND)
        jar = body.get("jar")
        if not isinstance(jar, str) or not JAR_CODE_RE.match(jar):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Mã hũ không hợp lệ.")
        res = self.repo.set_row_jar(uid, row_id, jar)
        jars = {j["code"]: j for j in jars_from_rows(self.repo.jar_rows(uid))}
        if res is None:
            state = self.repo.row_state(uid, row_id)
            if state is None:
                raise YofinaError(ErrorCode.INGEST_JOB_NOT_FOUND, "Không tìm thấy dòng này.")
            if state["kind"] != "expense":
                raise YofinaError(ErrorCode.PARAMS_INVALID, "Dòng thu không có hũ để đổi.")
            if state["job_status"] != "review" or state["review_status"] not in (
                "auto_added",
                "pending",
            ):
                raise YofinaError(ErrorCode.INGEST_JOB_NOT_READY, "Dòng này không còn đổi hũ được.")
            raise YofinaError(ErrorCode.JAR_NOT_FOUND, "Không tìm thấy hũ này.")
        j = jars.get(jar)
        if j is None:  # hũ vừa bị xóa giữa hai lệnh gọi
            raise YofinaError(ErrorCode.JAR_NOT_FOUND, "Không tìm thấy hũ này.")
        return {
            "row_id": row_id,
            "suggested_jar": {k: j[k] for k in ("code", "name", "color_key", "icon_key")},
            "jar_source": "user",
        }

    # --- chốt dòng: xác nhận rồi thực hiện ------------------------------------------------------------------------------------
    @staticmethod
    def _normalize(tool: Any, params: Any) -> dict[str, Any]:
        if tool not in INGEST_ACTION_TOOLS:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Tool không được hỗ trợ ở đường dẫn này.")
        if not isinstance(params, Mapping):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Thiếu params.")
        try:
            return normalize_params(CONFIRM_ROWS, params)
        except ParamsError as exc:
            raise YofinaError(ErrorCode.PARAMS_INVALID, str(exc)) from exc

    def _prepare(self, uid: str, norm: Mapping[str, Any]) -> dict[str, Any]:
        """Kiểm trạng thái job và dòng (đọc, không ghi) rồi tính phần xem trước. Ném `YofinaError` nếu không chốt được."""
        found = self.repo.get_job(uid, norm["job_id"], REVIEW_ROW_LIMIT)
        if found is None:
            raise YofinaError(ErrorCode.INGEST_JOB_NOT_FOUND, "Không tìm thấy lần nạp này.")
        job, rows = found
        if job["status"] == "done":
            raise YofinaError(
                ErrorCode.ALREADY_APPLIED, "Lần nạp này đã được chốt rồi. Chưa ghi thêm gì."
            )
        if job["status"] != "review":
            raise YofinaError(
                ErrorCode.INGEST_JOB_NOT_READY, "Lần nạp này chưa đọc xong nên chưa chốt được."
            )
        by_id = {str(r["id"]): r for r in rows}
        jars = {j["code"]: j for j in jars_from_rows(self.repo.jar_rows(uid))}
        spend = income = count = fx_estimates = 0
        affected: list[str] = []
        for item in norm["rows"]:
            r = by_id.get(item["row_id"])
            if r is None:
                raise YofinaError(ErrorCode.PARAMS_INVALID, "Có dòng không thuộc lần nạp này.")
            if r["review_status"] not in ("auto_added", "pending"):
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID,
                    "Dòng đã được xử lý hoặc là dòng trùng nên không chốt được.",
                )
            count += 1
            amount = row_amount(r, item.get("amount_vnd"))
            if r.get("fx") is not None and "amount_vnd" not in item:
                fx_estimates += 1
            if r["kind"] == "expense":
                jar = item.get("jar") or r.get("suggested_jar_code")
                if not jar:
                    raise YofinaError(
                        ErrorCode.PARAMS_INVALID, "Dòng chi cần chọn hũ trước khi ghi."
                    )
                if jar not in jars:
                    raise YofinaError(ErrorCode.JAR_NOT_FOUND, "Không tìm thấy hũ đã chọn.")
                spend += amount
                if jar not in affected:
                    affected.append(jar)
            else:
                income += amount
        for rid in norm["reject_row_ids"]:
            if rid not in by_id:
                raise YofinaError(ErrorCode.PARAMS_INVALID, "Có dòng không thuộc lần nạp này.")
        return {
            "count": count,
            "spend": spend,
            "income": income,
            "jars": [jars[c] for c in affected],
            "rejected": len(norm["reject_row_ids"]),
            "fx_estimates": fx_estimates,
        }

    def _coverage_preview(
        self, uid: str, spend: int, income: int
    ) -> tuple[float | None, float | None]:
        facts = self.repo.coverage_facts(
            uid, self.now(), self.rt.app_timezone, self.rt.forecast_history_window_days
        )
        if not facts:
            return None, None
        before = coverage_ratio(facts)
        after_facts = dict(facts)
        after_facts["spend_vnd"] = facts["spend_vnd"] + spend
        after_facts["income_vnd"] = facts["income_vnd"] + income
        return before, coverage_ratio(after_facts)

    def issue_confirmation(
        self, uid: str, *, tool: Any, params: Any, client_params_hash: Any, trace_id: str
    ) -> tuple[Any, dict[str, Any]]:
        """Người dùng bấm "Xem lại": kiểm nghiệp vụ, tính xem trước, ký token cho (người, tool, tham số). Không ghi gì."""
        norm, preview = self.preview_confirmation(uid, tool=tool, params=params)
        digest = hash_normalized_params(CONFIRM_ROWS, norm)
        if client_params_hash and client_params_hash != digest:
            raise YofinaError(
                ErrorCode.PARAMS_MISMATCH,
                "Tham số khác với khối xác nhận bạn đang xem; hãy hỏi lại.",
            )
        return self.confirm.issue(uid, CONFIRM_ROWS, norm), preview

    def preview_confirmation(
        self, uid: str, *, tool: Any, params: Any
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Chuẩn hóa, kiểm nghiệp vụ và tính bản xem trước (`summary`, `changes`, `warnings`) của một lần chốt. Không ghi gì, không
        ký token: REST `POST /ingest/confirmations` ký thêm token, tool Gateway `confirm_rows` không token chỉ trả bản xem trước."""
        norm = self._normalize(tool, params)
        prep = self._prepare(uid, norm)
        before, after = self._coverage_preview(uid, prep["spend"], prep["income"])
        changes: list[dict[str, str]] = [
            {"label": "Thêm vào lịch sử chi tiêu", "after": f"{prep['count']} dòng ngoài ví"},
        ]
        if prep["spend"]:
            changes.append({"label": "Chi ngoài ví", "after": format_vnd(prep["spend"])})
        if prep["income"]:
            changes.append({"label": "Thu ngoài ví", "after": format_vnd(prep["income"])})
        changes.append({"label": "Số dư các hũ", "before": "Giữ nguyên", "after": "Không đổi"})
        if before is not None and after is not None:
            changes.append(
                {
                    "label": "Độ phủ dữ liệu",
                    "before": f"{round(before * 100)}%",
                    "after": f"{round(after * 100)}%",
                }
            )
        preview: dict[str, Any] = {
            "summary": f"Thêm {prep['count']} dòng ngoài ví vào lịch sử, số dư hũ không đổi"[:120],
            "changes": changes[:20],
        }
        warnings: list[str] = []
        if prep["rejected"]:
            warnings.append(f"{prep['rejected']} dòng sẽ được bỏ qua, không ghi vào lịch sử.")
        if prep["fx_estimates"]:
            warnings.append(
                f"{prep['fx_estimates']} dòng ngoại tệ dùng số VND ước tính theo tỷ giá bán; sao kê thẻ có thể khác do phí."
            )
        if warnings:
            preview["warnings"] = warnings
        return norm, preview

    def apply_action(
        self,
        uid: str,
        *,
        tool: Any,
        params: Any,
        confirm_token: str | None,
        trace_id: str,
        source_tool: str = "rest:POST /ingest/actions",
    ) -> Any:
        """Chốt dòng (cần token): chuẩn hóa, kiểm chữ ký/hạn/người/tool/hash, kiểm nghiệp vụ, RỒI MỚI tiêu `jti`, ghi một transaction,
        tính lại dự báo (không bao giờ làm hỏng việc đã ghi), trả `receipt_action` kèm `coverage_change`."""
        norm = self._normalize(tool, params)
        if confirm_token in (None, ""):
            raise YofinaError(
                ErrorCode.NEEDS_CONFIRMATION, "Thao tác này cần bạn xác nhận trước khi thực hiện."
            )
        payload = self.confirm.verify(confirm_token, sub=uid, tool=CONFIRM_ROWS, params=norm)
        try:
            self._prepare(uid, norm)
        except YofinaError as exc:
            if (
                exc.code == ErrorCode.ALREADY_APPLIED
            ):  # token dùng lại sau khi đã chốt: báo TOKEN_REUSED nếu token đã dùng
                self.confirm.consume(payload)
            raise
        self.confirm.consume(payload)
        user = self._user(uid)
        now = self.now()
        app_date = self._today(user, now)
        out = self.repo.confirm_rows(
            uid,
            job_id=norm["job_id"],
            approvals={r["row_id"]: r.get("jar") for r in norm["rows"]},
            amounts={r["row_id"]: r["amount_vnd"] for r in norm["rows"] if "amount_vnd" in r},
            reject_ids=norm["reject_row_ids"],
            now=now,
            tz=self.rt.app_timezone,
            window_days=self.rt.forecast_history_window_days,
            trace_id=trace_id,
            params=norm,
        )
        queued = False
        if self._forecast is not None:
            try:
                queued = bool(self._forecast(uid, "manual"))
            except Exception:  # không bao giờ làm hỏng việc đã ghi
                log.warning(json.dumps({"msg": "ingest_forecast_trigger_failed"}))
        names = {j["code"]: j["name"] for j in jars_from_rows(self.repo.jar_rows(uid))}
        cov = build_coverage_change(
            job_id=norm["job_id"],
            before=out.coverage_before,
            after=out.coverage_after,
            rows_added=out.rows_added,
            external_spend_added_vnd=out.external_spend_added_vnd,
            external_income_added_vnd=out.external_income_added_vnd or None,
            jars_affected=[{"code": c, "name": names.get(c, c)} for c in out.jar_codes],
            forecast_refresh="queued" if queued else "skipped",
            trace_id=trace_id,
            source_tool=source_tool,
            as_of=now,
            app_date=app_date,
        )
        details = [{"label": "Số dòng đã thêm", "value": str(out.rows_added)}]
        if out.external_spend_added_vnd:
            details.append(
                {"label": "Chi ngoài ví", "value": format_vnd(out.external_spend_added_vnd)}
            )
        if out.external_income_added_vnd:
            details.append(
                {"label": "Thu ngoài ví", "value": format_vnd(out.external_income_added_vnd)}
            )
        details.append({"label": "Số dư các hũ", "value": "Không đổi"})
        if out.coverage_before is not None and out.coverage_after is not None:
            details.append(
                {
                    "label": "Độ phủ dữ liệu",
                    "value": f"{round(out.coverage_before * 100)}% lên {round(out.coverage_after * 100)}%",
                }
            )
        return build_receipt_action(
            tool=CONFIRM_ROWS,
            occurred_at=now,
            app_date=app_date,
            summary=f"Đã thêm {out.rows_added} dòng ngoài ví vào lịch sử chi tiêu",
            trace_id=trace_id,
            source_tool=source_tool,
            reference_id=norm["job_id"],
            amount_vnd=out.external_spend_added_vnd or None,
            jars_after=[],
            details=details,
            coverage_change=cov,
        )


def _f(v: Any) -> float | None:
    return None if v is None else float(v)
