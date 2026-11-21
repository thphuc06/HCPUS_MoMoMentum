"""Đường vào HTTP API (payload v2) của Lambda ledger.

Danh tính CHỈ lấy từ claim `sub` của JWT authorizer (`requestContext.authorizer.jwt.claims`); không
endpoint nào đọc `user_id` từ thân yêu cầu (trường lạ trong thân bị bỏ qua). JWT authorizer của API
Gateway đã xác thực chữ ký, `iss`, hạn và `client_id`/`aud` trước khi tới đây.
Lỗi: `{"error": {"code", "message", "trace_id"}}`, status theo `yofina_core.errors.HTTP_STATUS`.
"""

from __future__ import annotations

import base64
import json
import logging
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
from yofina_ledger.service import LedgerService

log = logging.getLogger("yofina.ledger.rest")

_HEADERS = {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"}


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
    ctx = event.get("requestContext", {})
    return ctx.get("authorizer", {}).get("jwt", {}).get("claims", {}) or {}


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


def handle_http(event: Mapping[str, Any], service: LedgerService) -> dict[str, Any]:
    started = time.perf_counter()
    http = event.get("requestContext", {}).get("http", {})
    method = str(http.get("method", "")).upper()
    path = str(event.get("rawPath") or http.get("path") or "").rstrip("/") or "/"
    route = f"{method} {path}"
    trace_id = trace_id_from_traceparent(_header(event, "traceparent")) or new_trace_id()
    outcome = "UNKNOWN"
    try:
        sub = _claims(event).get("sub")
        if not isinstance(sub, str) or not sub:
            raise YofinaError(ErrorCode.UNAUTHENTICATED, "Thiếu hoặc sai thông tin đăng nhập.")
        status, body = _dispatch(route, event, sub, trace_id, service)
        outcome = str(status)
        return response(status, body)
    except YofinaError as exc:
        outcome = str(exc.code)
        return error_response(exc.code, exc.message, trace_id)
    except Exception:
        outcome = "INTERNAL_ERROR"
        log.exception("rest_unhandled route=%s trace_id=%s", route, trace_id)
        return error_response(ErrorCode.INTERNAL_ERROR, "Có lỗi hệ thống, thử lại sau.", trace_id)
    finally:
        log.info(
            json.dumps(
                {
                    "msg": "rest_request",
                    "route": route,
                    "trace_id": trace_id,
                    "outcome": outcome,
                    "ms": round((time.perf_counter() - started) * 1000, 1),
                }
            )
        )


def _dispatch(
    route: str, event: Mapping[str, Any], sub: str, trace_id: str, service: LedgerService
) -> tuple[int, dict[str, Any]]:
    if route == "GET /jars":
        return 200, service.jars_response(sub, trace_id=trace_id)

    if route == "POST /confirmations":
        body = _body(event)
        issued = service.issue_confirmation(
            sub,
            tool=body.get("tool"),
            params=_params(body),
            client_params_hash=body.get("params_hash"),
            trace_id=trace_id,
            conversation_id=body.get("conversation_id"),
            confirm_block_id=body.get("confirm_block_id"),
        )
        return 200, {
            "confirm_token": issued.token,
            "expires_at": format_instant(issued.expires_at),
            "ttl_seconds": issued.ttl_seconds,
            "tool": issued.tool,
            "params": issued.params,
            "params_hash": issued.params_hash,
        }

    if route == "POST /actions":
        body = _body(event)
        if body.get("tool") != "move_between_jars":
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Tool không được hỗ trợ.")
        token = body.get("confirm_token")
        if token is not None and not isinstance(token, str):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "confirm_token phải là chuỗi.")
        receipt = service.apply_move(
            sub,
            _params(body),
            token,
            trace_id=trace_id,
            channel="rest",
            source_tool="rest:POST /actions",
            conversation_id=body.get("conversation_id"),
            confirm_block_id=body.get("confirm_block_id"),
        )
        return 200, block_to_wire(receipt)

    if route == "GET /conversations":
        query = event.get("queryStringParameters") or {}
        return 200, service.conversations_response(sub, limit=query.get("limit"))

    if route.startswith("GET /conversations/"):
        # HTTP API đã giải mã tham số đường dẫn: lấy từ pathParameters, không tự tách chuỗi
        conv = (event.get("pathParameters") or {}).get("conversation_id")
        return 200, service.conversation_response(sub, conv)

    if route == "POST /demo/reset":
        from personas import parse_groups_claim, persona_from_groups

        groups = parse_groups_claim(_claims(event).get("cognito:groups"))
        persona = persona_from_groups(groups)
        if persona is None:
            raise YofinaError(
                ErrorCode.FORBIDDEN,
                "Tài khoản này không phải tài khoản demo nên không đặt lại được.",
            )
        return 200, service.reset_demo(sub, persona, trace_id=trace_id)

    raise YofinaError(ErrorCode.PARAMS_INVALID, "Đường dẫn không tồn tại.")


def _params(body: Mapping[str, Any]) -> Mapping[str, Any]:
    params = body.get("params")
    if not isinstance(params, dict):
        raise YofinaError(ErrorCode.PARAMS_INVALID, "Thiếu params.")
    return params
