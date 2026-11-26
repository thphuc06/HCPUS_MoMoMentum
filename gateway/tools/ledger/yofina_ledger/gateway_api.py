"""Đường vào AgentCore Gateway (Lambda target) của Lambda ledger.

- Tên tool: `context.client_context.custom["bedrockAgentCoreToolName"]`, cắt tiền tố `ledger___`.
- `user_id` lấy từ `event`: interceptor của Gateway ghi đè nó bằng `sub` của JWT trước khi tới đây
  (spike Gateway §3a). Lambda không thấy JWT. Tham số lạ bị bỏ qua (Gateway không từ chối chúng).
- Kết quả theo `contracts/tools/ledger.results.schema.json`; lỗi nghiệp vụ là kết quả thành công
  của Lambda: `{"status": "ERROR", "code", "message"}`.
- Mười tool (đúng thứ tự `yofina_core.wallet.LEDGER_TOOLS`): năm tool đọc, bốn tool ghi, `save_turn`. Tool ghi KHÔNG có
  `confirm_token` thì không ghi, trả `NEEDS_CONFIRMATION` kèm bản xem trước. `save_jars` và `confirm_salary` chỉ có ở REST.
- Phase 3: Lambda này CŨNG phục vụ ba target Gateway `planner` (`check_suitability`, `schedule_nudge`), `knowledge`
  (`get_fee_schedule`, `get_exchange_rate`, `resolve_date`) và `audit` (`get_trace`, `record_turn`) theo quyết định của người điều phối (không có Lambda riêng). Tên tool của các
  target đó là duy nhất trong Gateway nên phân biệt theo tên (phần sau `___`). `schedule_nudge` là tool GHI qua token như các
  tool ghi khác.
- Phase 4: target `planner` thêm `optimize_allocation` (proxy sang Lambda forecast), `save_roadmap` (ghi, KHÔNG qua token, chạy lại
  suitability cho từng bước), `get_roadmap`; logic ở `roadmap_service.py`.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping
from typing import Any

from yofina_core.blocks import block_to_wire, new_trace_id
from yofina_core.confirm import MOVE_BETWEEN_JARS
from yofina_core.errors import ErrorCode, ToolStatus, YofinaError
from yofina_core.wallet import AGENT_WRITE_TOOLS, PLANNER_WRITE_TOOLS
from yofina_knowledge.dates import TOOL_ARGS as RESOLVE_DATE_ARGS
from yofina_ledger.roadmap_service import roadmap_ops
from yofina_ledger.service import PLANNER_PREFIX, TOOL_PREFIX, LedgerService

log = logging.getLogger("yofina.ledger.gateway")

#: phase 4: ba tool của target `planner` về lộ trình. `optimize_allocation` là proxy sang Lambda forecast (N1), `save_roadmap` ghi KHÔNG
#: qua token (không đổi số dư; chạy lại suitability cho từng bước), `get_roadmap` đọc.
ROADMAP_TOOLS = ("optimize_allocation", "save_roadmap", "get_roadmap")

_ARG_KEYS: dict[str, tuple[str, ...]] = {
    "get_jar_balances": (),
    "query_transactions": ("jar", "kind", "tx_type", "from_date", "to_date", "limit", "cursor"),
    "get_cashflow_summary": ("from_date", "to_date"),
    "get_obligations": ("status", "within_days", "limit"),
    "get_unclassified": ("limit",),
    "update_profile": (
        "display_name",
        "monthly_salary_vnd",
        "payday_day",
        "risk_tolerance",
        "obligation",
        "confirm_token",
    ),
    "record_transaction": (
        "kind",
        "amount_vnd",
        "jar",
        "tx_type",
        "funding",
        "pay_jar",
        "payee_id",
        "counterparty",
        "note",
        "obligation_id",
        "client_ref",
        "confirm_token",
    ),
    MOVE_BETWEEN_JARS: ("from_jar", "to_jar", "amount_vnd", "confirm_token"),
    "assign_jar": ("transaction_id", "jar", "remember", "confirm_token"),
    "save_turn": ("conversation_id", "trace_id", "user_text", "assistant_text", "blocks"),
    # --- phase 3: target planner, knowledge, audit (chạy chung Lambda này) ---
    "check_suitability": ("proposal", "scenario_id"),
    "schedule_nudge": (
        "op",
        "kind",
        "fire_on",
        "jar_code",
        "note",
        "scenario_id",
        "nudge_id",
        "confirm_token",
    ),
    "get_fee_schedule": ("fee_type", "product"),
    "get_exchange_rate": ("currency", "date", "amount"),
    "resolve_date": RESOLVE_DATE_ARGS,
    # --- phase 4: target planner (lộ trình; chạy chung Lambda này) ---
    "optimize_allocation": ("horizon_months", "goals", "shock_id", "allow_relaxation"),
    "save_roadmap": (
        "reason_code",
        "based_on_version",
        "behavior_flag_id",
        "feasibility",
        "goals",
        "phases",
        "alternatives",
    ),
    "get_roadmap": ("version", "which"),
    "get_trace": ("trace_id",),
    "record_turn": (
        "trace_id",
        "conversation_id",
        "intent",
        "outcome",
        "code",
        "data_used",
        "rules_checked",
        "confidence",
        "blocks_emitted",
        "token_usage",
        "step_timings",
        "duration_ms",
    ),
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
        return exc.tool_result()
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
        return service.query_transactions_result(user_id, **args)
    if tool == "get_cashflow_summary":
        return service.cashflow_result(user_id, **args)
    if tool == "get_obligations":
        resp = service.obligations_response(user_id, include_credit_line=True, **args)
        data: dict[str, Any] = {
            "obligations": resp["obligations"],
            "total_due_vnd": resp["total_due_vnd"],
        }
        if "credit_line" in resp:
            data["credit_line"] = resp["credit_line"]
        return {
            "status": str(ToolStatus.OK),
            "as_of": resp["as_of"],
            "app_date": resp["app_date"],
            "data": data,
        }
    if tool == "get_unclassified":
        return service.unclassified_result(user_id, **args)
    if tool == "save_turn":
        return service.save_turn_result(user_id, **args)
    if tool == "check_suitability":
        return service.check_suitability_result(user_id, **args)
    if tool == "get_fee_schedule":
        return service.fee_schedule_result(
            user_id, product=args.get("product"), fee_type=args.get("fee_type")
        )
    if tool == "get_exchange_rate":
        return service.exchange_rate_result(user_id, **args)
    if tool == "resolve_date":
        return service.resolve_date_result(user_id, **args)
    if tool == "get_trace":
        return service.trace_result(user_id, args.get("trace_id"))
    if tool in ROADMAP_TOOLS:
        ops = roadmap_ops(service)
        if tool == "optimize_allocation":
            return ops.optimize_allocation_result(user_id, **args)
        if tool == "save_roadmap":
            return ops.save_roadmap_result(user_id, trace_id=trace_id, **args)
        return ops.get_roadmap_result(user_id, **args)
    if tool == "record_turn":
        return service.record_turn_result(user_id, **args)
    # tool ghi: move_between_jars, update_profile, record_transaction, assign_jar, schedule_nudge
    assert tool == MOVE_BETWEEN_JARS or tool in AGENT_WRITE_TOOLS or tool in PLANNER_WRITE_TOOLS
    prefix = PLANNER_PREFIX if tool in PLANNER_WRITE_TOOLS else TOOL_PREFIX
    token = args.pop("confirm_token", None)
    if token in (None, ""):
        return service.needs_confirmation_for(user_id, tool, args, trace_id=trace_id)
    if not isinstance(token, str):
        raise YofinaError(ErrorCode.PARAMS_INVALID, "confirm_token phải là chuỗi.")
    receipt = service.apply_action(
        user_id,
        tool,
        args,
        token,
        trace_id=trace_id,
        channel="gateway",
        source_tool=f"{prefix}{tool}",
    )
    return {
        "status": str(ToolStatus.OK),
        "as_of": receipt.source.as_of,
        "app_date": receipt.source.app_date,
        "data": block_to_wire(receipt)["data"],
    }
