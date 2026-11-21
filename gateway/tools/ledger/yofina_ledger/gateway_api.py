"""Đường vào AgentCore Gateway (Lambda target) của Lambda ledger.

- Tên tool: `context.client_context.custom["bedrockAgentCoreToolName"]`, cắt tiền tố `ledger___`.
- `user_id` lấy từ `event`: interceptor của Gateway ghi đè nó bằng `sub` của JWT trước khi tới đây
  (spike Gateway §3a). Lambda không thấy JWT. Tham số lạ bị bỏ qua (Gateway không từ chối chúng).
- Kết quả theo `contracts/tools/ledger.results.schema.json`; lỗi nghiệp vụ là kết quả thành công
  của Lambda: `{"status": "ERROR", "code", "message"}`.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping
from typing import Any

from yofina_core.blocks import new_trace_id
from yofina_core.confirm import MOVE_BETWEEN_JARS
from yofina_core.errors import ErrorCode, ToolStatus, YofinaError
from yofina_ledger.service import TOOL_PREFIX, LedgerService

log = logging.getLogger("yofina.ledger.gateway")

_ARG_KEYS: dict[str, tuple[str, ...]] = {
    "get_jar_balances": (),
    "query_transactions": ("jar", "from_date", "to_date", "limit"),
    MOVE_BETWEEN_JARS: ("from_jar", "to_jar", "amount_vnd", "confirm_token"),
    "save_turn": ("conversation_id", "trace_id", "user_text", "assistant_text", "blocks"),
}


def tool_name(context: Any) -> str:
    custom = dict(getattr(getattr(context, "client_context", None), "custom", None) or {})
    full = str(custom.get("bedrockAgentCoreToolName", ""))
    return full.split(TOOL_PREFIX, 1)[1] if full.startswith(TOOL_PREFIX) else full.split("___")[-1]


def error_result(code: ErrorCode, message: str) -> dict[str, Any]:
    return {"status": str(ToolStatus.ERROR), "code": str(code), "message": message}


def handle_gateway(
    event: Mapping[str, Any], context: Any, service: LedgerService
) -> dict[str, Any]:
    started = time.perf_counter()
    tool = tool_name(context)
    trace_id = new_trace_id()
    outcome = "UNKNOWN"
    try:
        user_id = event.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            raise YofinaError(ErrorCode.UNAUTHENTICATED, "Thiếu thông tin người dùng.")
        if tool not in _ARG_KEYS:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Tool không tồn tại.")
        args = {k: event[k] for k in _ARG_KEYS[tool] if k in event}
        result = _run(service, tool, user_id, args, trace_id)
        outcome = str(result["status"])
        return result
    except YofinaError as exc:
        outcome = str(exc.code)
        return error_result(exc.code, exc.message)
    except Exception:
        outcome = "INTERNAL_ERROR"
        log.exception("gateway_unhandled tool=%s trace_id=%s", tool, trace_id)
        return error_result(ErrorCode.INTERNAL_ERROR, "Có lỗi hệ thống, thử lại sau.")
    finally:
        log.info(
            json.dumps(
                {
                    "msg": "gateway_call",
                    "tool": tool,
                    "trace_id": trace_id,
                    "outcome": outcome,
                    "ms": round((time.perf_counter() - started) * 1000, 1),
                }
            )
        )


def _run(
    service: LedgerService, tool: str, user_id: str, args: dict[str, Any], trace_id: str
) -> dict[str, Any]:
    if tool == "get_jar_balances":
        return service.get_jar_balances_result(user_id, trace_id=trace_id)
    if tool == "query_transactions":
        return service.query_transactions_result(
            user_id,
            jar=args.get("jar"),
            from_date=args.get("from_date"),
            to_date=args.get("to_date"),
            limit=args.get("limit"),
        )
    if tool == "save_turn":
        return service.save_turn_result(user_id, **args)
    # move_between_jars
    token = args.get("confirm_token")
    if token in (None, ""):
        return service.needs_confirmation_result(user_id, args, trace_id=trace_id)
    if not isinstance(token, str):
        raise YofinaError(ErrorCode.PARAMS_INVALID, "confirm_token phải là chuỗi.")
    receipt = service.apply_move(
        user_id,
        args,
        token,
        trace_id=trace_id,
        channel="gateway",
        source_tool=f"{TOOL_PREFIX}{MOVE_BETWEEN_JARS}",
    )
    return {
        "status": str(ToolStatus.OK),
        "as_of": receipt.source.as_of,
        "app_date": receipt.source.app_date,
        "data": receipt.data.model_dump(mode="json"),
    }
