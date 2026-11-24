"""Đường vào AgentCore Gateway (Lambda target `ingest`) của Lambda `yofina-ingest-api`: ba tool `ingest___*` của agent.

- Tên tool: `context.client_context.custom["bedrockAgentCoreToolName"]`, cắt tiền tố `ingest___` (như ledger).
- `user_id` lấy từ `event`: interceptor của Gateway ghi đè nó bằng `sub` của JWT trước khi tới đây, Cedar (`gateway/policies/*.cedar`)
  kiểm lại `user_id == principal.id`. Lambda không thấy JWT. Tham số lạ bị bỏ qua.
- Kết quả theo `contracts/tools/ingest.results.schema.json`; lỗi nghiệp vụ là kết quả thành công của Lambda:
  `{"status": "ERROR", "code", "message"}`.
- `start_job` KHÔNG tạo job, không ghi: tệp chỉ tải lên được từ màn hình (người dùng chọn tệp và đồng ý).
- `get_job_status` trả `review` là ĐÚNG `data` của khối `ingest_review` (nội dung dòng đã che PII và là DỮ LIỆU, không phải chỉ dẫn).
- `confirm_rows` là tool GHI: không `confirm_token` thì KHÔNG ghi, trả `NEEDS_CONFIRMATION` với `ConfirmActionData`; có token thì đi
  đúng `IngestApi.apply_action` của `POST /ingest/actions` (cùng khóa HMAC, cùng bảng `jti`, dùng một lần), trả `ReceiptActionData`.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any

from yofina_core.blocks import block_to_wire, build_confirm_action, format_instant, new_trace_id
from yofina_core.errors import ErrorCode, ToolStatus, YofinaError
from yofina_core.ingest import CONSENT_SOURCE_OF, INGEST_TOOLS, SOURCE_KINDS, TARGET
from yofina_core.wallet import CONFIRM_ROWS
from yofina_ingest.api import IngestApi

log = logging.getLogger("yofina.ingest.gateway")

TOOL_PREFIX = f"{TARGET}___"
#: đường dẫn màn Nạp dữ liệu của frontend (`frontend/src/router.tsx`)
UPLOAD_PATH = "/ingest"

#: tham số mỗi tool nhận (khớp `contracts/tools/ingest.json`, trừ `user_id` do interceptor ghi đè)
ARG_KEYS: dict[str, tuple[str, ...]] = {
    "start_job": ("source_kind",),
    "get_job_status": ("job_id",),
    CONFIRM_ROWS: ("job_id", "rows", "reject_row_ids", "confirm_token"),
}
assert tuple(ARG_KEYS) == INGEST_TOOLS


def is_gateway_event(event: Mapping[str, Any]) -> bool:
    """Sự kiện HTTP API có `requestContext.http`; sự kiện của Gateway là chính tham số của tool."""
    ctx = event.get("requestContext")
    return not (isinstance(ctx, Mapping) and "http" in ctx)


def tool_name(context: Any) -> str:
    custom = dict(getattr(getattr(context, "client_context", None), "custom", None) or {})
    full = str(custom.get("bedrockAgentCoreToolName", ""))
    return full[len(TOOL_PREFIX) :] if full.startswith(TOOL_PREFIX) else full.split("___")[-1]


def error_result(code: ErrorCode, message: str) -> dict[str, Any]:
    return {"status": str(ToolStatus.ERROR), "code": str(code), "message": message}


def handle_gateway(event: Mapping[str, Any], context: Any, api: IngestApi) -> dict[str, Any]:
    started = time.perf_counter()
    tool = tool_name(context)
    trace_id = new_trace_id()
    outcome = "UNKNOWN"
    try:
        user_id = event.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            raise YofinaError(ErrorCode.UNAUTHENTICATED, "Thiếu thông tin người dùng.")
        if tool not in ARG_KEYS:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Tool không tồn tại.")
        args = {k: event[k] for k in ARG_KEYS[tool] if k in event}
        result = IngestTools(api).run(tool, user_id, args, trace_id)
        outcome = str(result["status"])
        return result
    except YofinaError as exc:
        outcome = str(exc.code)
        return error_result(exc.code, exc.message)
    except Exception:
        outcome = "INTERNAL_ERROR"
        log.exception("ingest_gateway_unhandled tool=%s trace_id=%s", tool, trace_id)
        return error_result(ErrorCode.INTERNAL_ERROR, "Có lỗi hệ thống, thử lại sau.")
    finally:
        log.info(
            json.dumps(
                {
                    "msg": "ingest_gateway_call",
                    "tool": tool,
                    "trace_id": trace_id,
                    "outcome": outcome,
                    "ms": round((time.perf_counter() - started) * 1000, 1),
                }
            )
        )


class IngestTools:
    """Ba tool của target `ingest` trên cùng `IngestApi` với REST (một nguồn nghiệp vụ, hai đường vào)."""

    def __init__(self, api: IngestApi) -> None:
        self.api = api

    def run(self, tool: str, uid: str, args: Mapping[str, Any], trace_id: str) -> dict[str, Any]:
        if tool == "start_job":
            return self.start_job(uid, args.get("source_kind"))
        if tool == "get_job_status":
            return self.get_job_status(uid, args.get("job_id"), trace_id=trace_id)
        return self.confirm_rows(uid, args, trace_id=trace_id)

    def _envelope(self, uid: str) -> tuple[datetime, date, dict[str, str]]:
        """(bây giờ, ngày mô phỏng, `as_of`/`app_date` của kết quả). Tài khoản chưa có hồ sơ thì PROFILE_INCOMPLETE."""
        user = self.api._user(uid)
        now = self.api.now()
        today = self.api._today(user, now)
        return now, today, {"as_of": format_instant(now), "app_date": today.isoformat()}

    def _latest_job(self, uid: str) -> Mapping[str, Any] | None:
        jobs = self.api.repo.list_jobs(uid, 1)
        return jobs[0] if jobs else None

    # --- start_job ---------------------------------------------------------------------------------------------------------
    def start_job(self, uid: str, source_kind: Any) -> dict[str, Any]:
        if source_kind in (None, ""):
            kinds: tuple[str, ...] = SOURCE_KINDS
        elif source_kind in SOURCE_KINDS:
            kinds = (str(source_kind),)
        else:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "source_kind phải là image hoặc csv.")
        _, _, env = self._envelope(uid)
        s = self.api.rt.settings
        consents = self.api.repo.consents(uid)

        def missing(kind: str) -> bool:
            row = consents.get(CONSENT_SOURCE_OF[kind])
            return row is None or row.get("revoked_at") is not None

        data: dict[str, Any] = {
            "upload_path": UPLOAD_PATH,
            "limits": [
                {"source_kind": k, "max_bytes": s.max_bytes(k), "mime_types": list(s.mime_types[k])}
                for k in kinds
            ],
            # không nêu loại tệp: màn hình hỏi đồng ý nếu MỘT trong hai nguồn chưa được đồng ý
            "consent_required": any(missing(k) for k in kinds),
        }
        latest = self._latest_job(uid)
        if latest is not None:
            data["latest_job_id"] = str(latest["id"])
            data["latest_job_status"] = latest["status"]
        return {"status": str(ToolStatus.OK), **env, "data": data}

    # --- get_job_status ----------------------------------------------------------------------------------------------------
    def get_job_status(self, uid: str, job_id: Any, *, trace_id: str) -> dict[str, Any]:
        _, _, env = self._envelope(uid)
        if job_id in (None, ""):
            latest = self._latest_job(uid)
            if latest is None:
                raise YofinaError(
                    ErrorCode.INGEST_JOB_NOT_FOUND, "Bạn chưa nạp ảnh hay tệp sao kê nào."
                )
            job_id = str(latest["id"])
        out = self.api.get_job(
            uid, job_id, trace_id=trace_id, source_tool=f"{TOOL_PREFIX}get_job_status"
        )
        data: dict[str, Any] = {
            k: out[k] for k in ("job_id", "status", "source_kind", "progress", "rows_total")
        }
        if out.get("error_code"):
            data["error_code"] = out["error_code"]
        if "review" in out:
            data["review"] = out["review"]["data"]
        if "coverage_change" in out:
            data["coverage_change"] = out["coverage_change"]["data"]
        return {"status": str(ToolStatus.OK), **env, "data": data}

    # --- confirm_rows ------------------------------------------------------------------------------------------------------
    def confirm_rows(self, uid: str, args: Mapping[str, Any], *, trace_id: str) -> dict[str, Any]:
        params = {k: args[k] for k in ("job_id", "rows", "reject_row_ids") if k in args}
        params.setdefault("rows", [])
        params.setdefault("reject_row_ids", [])
        token = args.get("confirm_token")
        source_tool = f"{TOOL_PREFIX}{CONFIRM_ROWS}"
        if token in (None, ""):
            norm, preview = self.api.preview_confirmation(uid, tool=CONFIRM_ROWS, params=params)
            now, today, env = self._envelope(uid)
            block = build_confirm_action(
                tool=CONFIRM_ROWS,
                params=norm,
                summary=preview["summary"],
                changes=preview["changes"],
                warnings=preview.get("warnings", ()),
                trace_id=trace_id,
                source_tool=source_tool,
                as_of=now,
                app_date=today,
                expires_at=now + timedelta(seconds=self.api.rt.offer_ttl_seconds),
            )
            return {
                "status": str(ToolStatus.NEEDS_CONFIRMATION),
                **env,
                "data": block_to_wire(block)["data"],
            }
        if not isinstance(token, str):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "confirm_token phải là chuỗi.")
        receipt = self.api.apply_action(
            uid,
            tool=CONFIRM_ROWS,
            params=params,
            confirm_token=token,
            trace_id=trace_id,
            source_tool=source_tool,
        )
        return {
            "status": str(ToolStatus.OK),
            "as_of": receipt.source.as_of,
            "app_date": receipt.source.app_date,
            "data": block_to_wire(receipt)["data"],
        }
