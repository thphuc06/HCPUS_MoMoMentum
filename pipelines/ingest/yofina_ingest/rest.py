"""Đường vào HTTP API (payload v2) của Lambda `yofina-ingest-api`: sáu route `/ingest/*`.

Danh tính CHỈ lấy từ claim `sub` của JWT authorizer; không endpoint nào đọc `user_id` từ thân yêu cầu. Lỗi:
`{"error": {"code", "message", "trace_id"}}`, status theo `yofina_core.errors.HTTP_STATUS` (cùng quy ước với Lambda ledger).
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from collections.abc import Mapping
from typing import Any

from yofina_core.blocks import (
    block_to_wire,
    format_instant,
    new_trace_id,
    trace_id_from_traceparent,
)
from yofina_core.errors import HTTP_STATUS, ErrorCode, YofinaError
from yofina_ingest.api import IngestApi

log = logging.getLogger("yofina.ingest.rest")

_HEADERS = {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"}
_ROW_JAR = re.compile(r"^/ingest/rows/([^/]+)/jar$")
_JOB = re.compile(r"^/ingest/jobs/([^/]+)$")


def response(status: int, body: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": dict(_HEADERS),
        "body": json.dumps(body, ensure_ascii=False),
    }


def error_response(code: ErrorCode, message: str, trace_id: str) -> dict[str, Any]:
    return response(
        HTTP_STATUS[code], {"error": {"code": str(code), "message": message, "trace_id": trace_id}}
    )


def _claims(event: Mapping[str, Any]) -> Mapping[str, Any]:
    return (
        event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {}) or {}
    )


def _body(event: Mapping[str, Any]) -> dict[str, Any]:
    raw = event.get("body")
    if raw in (None, ""):
        return {}
    try:
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode("utf-8")
        data = json.loads(raw)
    except ValueError:
        raise YofinaError(
            ErrorCode.PARAMS_INVALID, "Thân yêu cầu không phải JSON hợp lệ."
        ) from None
    if not isinstance(data, dict):
        raise YofinaError(ErrorCode.PARAMS_INVALID, "Thân yêu cầu phải là một đối tượng JSON.")
    return data


def _header(event: Mapping[str, Any], name: str) -> str | None:
    for k, v in (event.get("headers") or {}).items():
        if k.lower() == name:
            return v
    return None


def handle_http(event: Mapping[str, Any], api: IngestApi) -> dict[str, Any]:
    started = time.perf_counter()
    http = event.get("requestContext", {}).get("http", {})
    method = str(http.get("method", "")).upper()
    path = str(event.get("rawPath") or http.get("path") or "").rstrip("/") or "/"
    trace_id = trace_id_from_traceparent(_header(event, "traceparent")) or new_trace_id()
    outcome = "UNKNOWN"
    try:
        sub = _claims(event).get("sub")
        if not isinstance(sub, str) or not sub:
            raise YofinaError(ErrorCode.UNAUTHENTICATED, "Thiếu hoặc sai thông tin đăng nhập.")
        status, body = _dispatch(method, path, event, sub, trace_id, api)
        outcome = str(status)
        return response(status, body)
    except YofinaError as exc:
        outcome = str(exc.code)
        return error_response(exc.code, exc.message, trace_id)
    except Exception:
        outcome = "INTERNAL_ERROR"
        log.exception("ingest_rest_unhandled route=%s %s trace_id=%s", method, path, trace_id)
        return error_response(ErrorCode.INTERNAL_ERROR, "Có lỗi hệ thống, thử lại sau.", trace_id)
    finally:
        log.info(
            json.dumps(
                {
                    "msg": "ingest_rest_request",
                    "route": f"{method} {re.sub(r'[0-9a-fA-F-]{36}', '{id}', path)}",
                    "trace_id": trace_id,
                    "outcome": outcome,
                    "ms": round((time.perf_counter() - started) * 1000, 1),
                }
            )
        )


def _params(body: Mapping[str, Any]) -> Any:
    params = body.get("params")
    if not isinstance(params, dict):
        raise YofinaError(ErrorCode.PARAMS_INVALID, "Thiếu params.")
    return params


def _dispatch(
    method: str, path: str, event: Mapping[str, Any], sub: str, trace_id: str, api: IngestApi
) -> tuple[int, dict[str, Any]]:
    q = event.get("queryStringParameters") or {}
    if method == "POST" and path == "/ingest/uploads":
        return 200, api.create_upload(sub, _body(event), trace_id=trace_id)
    if method == "GET" and path == "/ingest/jobs":
        return 200, api.list_jobs(sub, q.get("limit"))
    if method == "GET" and (m := _JOB.match(path)):
        raw = (event.get("pathParameters") or {}).get("job_id") or m.group(1)
        return 200, api.get_job(sub, raw, trace_id=trace_id)
    if method == "POST" and (m := _ROW_JAR.match(path)):
        raw = (event.get("pathParameters") or {}).get("row_id") or m.group(1)
        return 200, api.set_row_jar(sub, raw, _body(event))
    if method == "POST" and path == "/ingest/confirmations":
        body = _body(event)
        issued, preview = api.issue_confirmation(
            sub,
            tool=body.get("tool"),
            params=_params(body),
            client_params_hash=body.get("params_hash"),
            trace_id=trace_id,
        )
        return 200, {
            "confirm_token": issued.token,
            "expires_at": format_instant(issued.expires_at),
            "ttl_seconds": issued.ttl_seconds,
            "tool": issued.tool,
            "params": issued.params,
            "params_hash": issued.params_hash,
            "preview": preview,
        }
    if method == "POST" and path == "/ingest/actions":
        body = _body(event)
        token = body.get("confirm_token")
        if token is not None and not isinstance(token, str):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "confirm_token phải là chuỗi.")
        receipt = api.apply_action(
            sub, tool=body.get("tool"), params=_params(body), confirm_token=token, trace_id=trace_id
        )
        return 200, block_to_wire(receipt)
    raise YofinaError(ErrorCode.PARAMS_INVALID, "Đường dẫn không tồn tại.")
