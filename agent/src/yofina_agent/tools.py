"""Gọi tool qua AgentCore Gateway bằng `strands.tools.mcp.MCPClient`, và dựng khối UI từ kết quả.

Quy tắc:
- Token của người dùng được chuyển **nguyên** cho Gateway qua header `Authorization` của MCP client.
  Agent không bao giờ gửi `user_id` (interceptor ở Gateway ghi đè từ chính JWT này).
- Kết quả tool được đọc thành `ToolOutcome` có kiểu. Mọi lỗi (tool trả `status: ERROR`, Cedar từ chối
  bằng JSON-RPC `-32002`, hết giờ, kết quả sai hợp đồng) thành `ToolOutcome` chứ không ném ra ngoài;
  luồng gọi đổi chúng thành khối `notice`.
- Số trong khối do `yofina_core.blocks.build_*` dựng từ kết quả tool; LLM không thấy khối.

Spike Gateway (docs/research/spike-agentcore-gateway-identity.md §3.4): Cedar từ chối là lỗi giao thức
(HTTP 200, `error.code = -32002`), client `mcp` ném `ExceptionGroup(McpError)`. `MCPClient.call_tool_async`
của Strands nuốt ngoại lệ đó thành một kết quả lỗi chỉ có chuỗi "Tool execution failed: ..." (mất mã),
nên `_GatewayMCPClient` giữ lại ngoại lệ gốc qua hook `_handle_tool_execution_error` để phân loại.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import ValidationError

from yofina_agent import notices
from yofina_agent.identity import Identity
from yofina_core import blocks as B
from yofina_core.errors import ErrorCode

log = logging.getLogger("yofina.agent.tools")

DENIED_JSONRPC_CODE = -32002  # Gateway: "Tool Execution Denied" (Cedar)
INVALID_TOKEN_JSONRPC_CODE = (
    -32001
)  # Gateway: "Invalid Bearer token" lúc mở phiên MCP (token hết hạn/sai)


class ToolKind(StrEnum):
    OK = "ok"
    NEEDS_CONFIRMATION = "needs_confirmation"
    TOOL_ERROR = "tool_error"  # tool trả status ERROR (lỗi nghiệp vụ) hoặc Gateway từ chối tham số
    DENIED = "denied"  # Cedar/Gateway từ chối (JSON-RPC -32002)
    UNAVAILABLE = "unavailable"  # không kết nối được hoặc hết giờ
    BAD_RESULT = "bad_result"  # kết quả không đọc được hoặc sai hợp đồng


@dataclass
class ToolOutcome:
    name: str
    kind: ToolKind
    payload: dict[str, Any] | None = None  # JSON nguyên văn của tool khi đọc được
    code: str | None = None  # ErrorCode khi lỗi
    message: str | None = None  # thông điệp tiếng Việt an toàn để hiện cho người dùng
    detail: str | None = None  # chi tiết kỹ thuật, chỉ để log
    args: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.kind in (ToolKind.OK, ToolKind.NEEDS_CONFIRMATION)


# --- phân loại kết quả (hàm thuần, có unit test) ---------------------------------------------
def _flatten(exc: BaseException) -> Iterator[BaseException]:
    yield exc
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            yield from _flatten(sub)
    if exc.__cause__ is not None:
        yield from _flatten(exc.__cause__)


def _error_code_of(value: Any) -> str:
    try:
        return ErrorCode(value).value
    except ValueError:
        return ErrorCode.INTERNAL_ERROR.value


def classify_exception(name: str, exc: BaseException) -> ToolOutcome:
    from mcp.shared.exceptions import MCPError

    flat = list(_flatten(exc))
    detail = "; ".join(
        f"{type(e).__name__}: {e}" for e in flat if not isinstance(e, BaseExceptionGroup)
    )[:400]
    for e in flat:
        if isinstance(e, MCPError):
            # Token hết hạn cũng có thể ra `-32002 insufficient_scope` (HTTP 403, thông điệp gây hiểu nhầm):
            # đó là phiên đăng nhập hết hạn, không phải Cedar từ chối (đã thử, spike-vertical-slice.md).
            if "insufficient_scope" in str(e.message):
                return ToolOutcome(
                    name,
                    ToolKind.TOOL_ERROR,
                    code=ErrorCode.UNAUTHENTICATED.value,
                    message=notices.SESSION_EXPIRED_MESSAGE,
                    detail=f"MCP {e.code}: {e.message}"[:400],
                )
            if e.code == DENIED_JSONRPC_CODE:
                return ToolOutcome(
                    name,
                    ToolKind.DENIED,
                    code=ErrorCode.FORBIDDEN.value,
                    message=notices.FORBIDDEN_MESSAGE,
                    detail=f"MCP {e.code}: {e.message}"[:400],
                )
            if e.code == INVALID_TOKEN_JSONRPC_CODE and "token" in str(e.message).lower():
                return ToolOutcome(
                    name,
                    ToolKind.TOOL_ERROR,
                    code=ErrorCode.UNAUTHENTICATED.value,
                    message=notices.SESSION_EXPIRED_MESSAGE,
                    detail=f"MCP {e.code}: {e.message}"[:400],
                )
            return ToolOutcome(
                name,
                ToolKind.TOOL_ERROR,
                code=ErrorCode.INTERNAL_ERROR.value,
                message=notices.GENERIC_ERROR_MESSAGE,
                detail=f"MCP {e.code}: {e.message}"[:400],
            )
    return ToolOutcome(
        name,
        ToolKind.UNAVAILABLE,
        code=ErrorCode.DATABASE_UNAVAILABLE.value,
        message=notices.UNAVAILABLE_MESSAGE,
        detail=detail,
    )


def classify_result(
    name: str, result: Mapping[str, Any] | None, exception: BaseException | None = None
) -> ToolOutcome:
    """Đổi kết quả của `MCPClient.call_tool_async` (và ngoại lệ gốc nếu có) thành `ToolOutcome`."""
    if exception is not None:
        return classify_exception(name, exception)

    def bad(detail: str) -> ToolOutcome:
        return ToolOutcome(
            name,
            ToolKind.BAD_RESULT,
            code=ErrorCode.INTERNAL_ERROR.value,
            message=notices.GENERIC_ERROR_MESSAGE,
            detail=detail,
        )

    if result is None:
        return bad("không có kết quả")
    text = "".join(c.get("text", "") for c in result.get("content", []) if isinstance(c, Mapping))
    if result.get("status") == "error" or result.get("isError"):
        code = (
            ErrorCode.PARAMS_INVALID if "ValidationException" in text else ErrorCode.INTERNAL_ERROR
        )
        return ToolOutcome(
            name,
            ToolKind.TOOL_ERROR,
            code=code.value,
            message=notices.GENERIC_ERROR_MESSAGE,
            detail=text[:400],
        )
    payload: Any = result.get("structuredContent")
    if not (isinstance(payload, dict) and "status" in payload):
        try:
            payload = json.loads(text)
        except ValueError:
            payload = None
    if not isinstance(payload, dict):
        return bad(f"không phải JSON: {text[:200]!r}")
    status = payload.get("status")
    if status == "OK":
        return ToolOutcome(name, ToolKind.OK, payload=payload)
    if status == "NEEDS_CONFIRMATION":
        return ToolOutcome(name, ToolKind.NEEDS_CONFIRMATION, payload=payload)
    if status == "ERROR":
        message = str(payload.get("message") or notices.GENERIC_ERROR_MESSAGE)[:280]
        return ToolOutcome(
            name,
            ToolKind.TOOL_ERROR,
            payload=payload,
            code=_error_code_of(payload.get("code")),
            message=message,
        )
    return bad(f"status lạ: {status!r}")


# --- client Gateway ---------------------------------------------------------------------------
def _make_mcp_client(url: str, headers: dict[str, str], startup_timeout: int) -> Any:
    from strands.tools.mcp import MCPClient

    class _GatewayMCPClient(MCPClient):
        """MCPClient giữ lại ngoại lệ gốc của lần gọi tool gần nhất (xem docstring của module)."""

        last_exception: BaseException | None = None

        def _handle_tool_execution_error(self, tool_use_id: str, exception: Exception) -> Any:
            self.last_exception = exception
            return super()._handle_tool_execution_error(tool_use_id, exception)

    return _GatewayMCPClient(
        url=url,
        headers=headers,
        startup_timeout=startup_timeout,
        application_name="yofina-agent",
    )


class GatewayTools:
    """Một kết nối MCP tới Gateway cho **một lượt hội thoại** (token của đúng người dùng đó).

    Kết nối mở lười ở lần gọi tool đầu tiên và đóng ở `aclose()`. Gọi tuần tự.
    """

    def __init__(
        self,
        url: str | None,
        identity: Identity,
        *,
        call_timeout: float,
        startup_timeout: float,
        client_factory: Callable[[str, dict[str, str], int], Any] = _make_mcp_client,
    ) -> None:
        self._url, self._identity = url, identity
        self._call_timeout, self._startup_timeout = call_timeout, startup_timeout
        self._factory = client_factory
        self._client: Any | None = None

    async def _ensure(self) -> Any:
        if self._client is None:
            if not self._url:
                raise RuntimeError("Thiếu YOFINA_GATEWAY_URL")
            client = self._factory(
                self._url,
                {"Authorization": self._identity.authorization},
                int(self._startup_timeout),
            )
            await asyncio.to_thread(client.start)
            self._client = client
        return self._client

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        outcome = await self._call(name, arguments)
        outcome.args = dict(arguments)
        log.log(
            logging.INFO if outcome.ok else logging.WARNING,
            json.dumps(
                {
                    "event": "tool_call",
                    "tool": name,
                    "kind": outcome.kind.value,
                    "code": outcome.code,
                    "detail": outcome.detail,
                },
                ensure_ascii=False,
            ),
        )
        return outcome

    async def _call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        try:
            client = await self._ensure()
        except Exception as exc:  # không kết nối/khởi tạo được phiên MCP
            outcome = classify_exception(name, exc)
            if (
                outcome.code == ErrorCode.UNAUTHENTICATED.value
            ):  # token hết hạn/sai: cần đăng nhập lại
                return outcome
            return ToolOutcome(  # lỗi khác lúc mở phiên: dịch vụ chưa sẵn sàng
                name,
                ToolKind.UNAVAILABLE,
                code=ErrorCode.DATABASE_UNAVAILABLE.value,
                message=notices.UNAVAILABLE_MESSAGE,
                detail=f"không mở được phiên MCP: {type(exc).__name__}: {exc}"[:400],
            )
        client.last_exception = None
        try:
            result = await asyncio.wait_for(
                client.call_tool_async(
                    f"tool-{uuid.uuid4().hex[:12]}",
                    name,
                    arguments,
                    read_timeout_seconds=timedelta(seconds=self._call_timeout),
                ),
                timeout=self._call_timeout + 5,
            )
        except Exception as exc:
            return classify_exception(name, exc)
        return classify_result(name, result, getattr(client, "last_exception", None))

    async def aclose(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                await asyncio.to_thread(client.stop, None, None, None)
            except Exception as exc:  # đóng kết nối không được làm hỏng lượt
                log.warning("đóng MCP client lỗi: %r", exc)


# --- dựng khối từ kết quả tool ----------------------------------------------------------------
class ContractMismatch(ValueError):
    """Kết quả tool không khớp hợp đồng (contracts/tools/ledger.results.schema.json)."""


def _parse_instant(value: str) -> datetime:
    return datetime.fromisoformat(value)


def jar_summary_block(outcome: ToolOutcome, trace_id: str) -> B.JarSummaryBlock:
    payload = outcome.payload or {}
    try:
        data = B.JarSummaryData.model_validate(payload["data"])
        return B.build_jar_summary(
            jars=[j.model_dump() for j in data.jars],
            trace_id=trace_id,
            source_tool=outcome.name,
            as_of=_parse_instant(payload["as_of"]),
            app_date=date.fromisoformat(payload["app_date"]),
        )
    except (KeyError, ValueError, ValidationError) as exc:
        raise ContractMismatch(f"get_jar_balances sai hợp đồng: {exc}") from exc


def confirm_block(outcome: ToolOutcome, trace_id: str) -> B.ConfirmBlock:
    """Khối `confirm` từ `NEEDS_CONFIRMATION`: dựng bằng `build_confirm` rồi đối chiếu với tool.

    Dữ liệu hiển thị và `params_hash` do **code** tính lại từ tham số tool trả; nếu lệch với `data` của
    tool thì coi là sai hợp đồng (không phát khối mà người dùng sẽ ký nhầm). Agent không điền cờ xác
    nhận hay token nào: đường ghi thật do frontend gọi REST.
    """
    payload = outcome.payload or {}
    try:
        d = B.ConfirmData.model_validate(payload["data"])
        block = B.build_confirm(
            tool=d.tool,
            params=d.params.model_dump(),
            from_jar={
                "code": d.preview.from_.code,
                "name": d.preview.from_.name,
                "balance_vnd": d.preview.from_.before_vnd,
            },
            to_jar={
                "code": d.preview.to.code,
                "name": d.preview.to.name,
                "balance_vnd": d.preview.to.before_vnd,
            },
            trace_id=trace_id,
            source_tool=outcome.name,
            as_of=_parse_instant(payload["as_of"]),
            app_date=date.fromisoformat(payload["app_date"]),
            expires_at=_parse_instant(d.expires_at),
        )
    except (KeyError, ValueError, ValidationError) as exc:
        raise ContractMismatch(f"move_between_jars sai hợp đồng: {exc}") from exc
    if block.data.params_hash != d.params_hash:
        raise ContractMismatch("params_hash của tool không khớp tham số (không phát khối xác nhận)")
    if block.data.preview != d.preview:
        raise ContractMismatch("bản xem trước của tool không khớp tính toán lại")
    return block


def forecast_block(outcome: ToolOutcome, trace_id: str) -> B.ForecastTimelineBlock:
    """Khối `forecast_timeline` từ kết quả `forecast___get_forecast`: `data` của tool ĐÃ là `ForecastTimelineData`, nên chỉ kiểm
    hợp đồng rồi bọc (số trong khối là số của tool, không tính lại, không do model viết)."""
    payload = outcome.payload or {}
    try:
        return B.build_forecast_timeline_from_data(
            data=payload["data"],
            trace_id=trace_id,
            source_tool=outcome.name,
            as_of=_parse_instant(payload["as_of"]),
            app_date=date.fromisoformat(payload["app_date"]),
        )
    except (KeyError, ValueError, ValidationError) as exc:
        raise ContractMismatch(f"get_forecast sai hợp đồng: {exc}") from exc


def confirm_action_block(outcome: ToolOutcome, trace_id: str) -> B.ConfirmActionBlock:
    """Khối `confirm_action` từ `NEEDS_CONFIRMATION` của tool ghi KHÁC chuyển hũ (update_profile, schedule_nudge...).

    `params_hash` do code tính lại từ chính `params` tool trả; lệch với `data` của tool thì coi là sai hợp đồng. Agent không điền token."""
    payload = outcome.payload or {}
    try:
        d = B.ConfirmActionData.model_validate(payload["data"])
        block = B.build_confirm_action(
            tool=d.tool,
            params=d.params,
            summary=d.summary,
            changes=[c.model_dump(exclude_none=True) for c in d.changes],
            trace_id=trace_id,
            source_tool=outcome.name,
            as_of=_parse_instant(payload["as_of"]),
            app_date=date.fromisoformat(payload["app_date"]),
            expires_at=_parse_instant(d.expires_at),
            warnings=d.warnings or (),
        )
    except (KeyError, ValueError, ValidationError) as exc:
        raise ContractMismatch(f"{outcome.name} sai hợp đồng xác nhận: {exc}") from exc
    if block.data.params_hash != d.params_hash:
        raise ContractMismatch("params_hash của tool không khớp tham số (không phát khối xác nhận)")
    return block


def affordability_block(outcome: ToolOutcome, trace_id: str) -> B.AffordabilityCardBlock:
    """Khối `affordability_card` từ `forecast___affordability_check` (cùng số với `POST /affordability`, không qua model)."""
    payload = outcome.payload or {}
    try:
        return B.build_affordability_card(
            data=payload["data"],
            trace_id=trace_id,
            source_tool=outcome.name,
            as_of=_parse_instant(payload["as_of"]),
            app_date=date.fromisoformat(payload["app_date"]),
        )
    except (KeyError, ValueError, ValidationError) as exc:
        raise ContractMismatch(f"affordability_check sai hợp đồng: {exc}") from exc


def resilience_block(outcome: ToolOutcome, trace_id: str) -> B.ResilienceScoreBlock:
    payload = outcome.payload or {}
    try:
        return B.build_resilience_score(
            data=payload["data"],
            trace_id=trace_id,
            source_tool=outcome.name,
            as_of=_parse_instant(payload["as_of"]),
            app_date=date.fromisoformat(payload["app_date"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractMismatch(f"get_resilience_score sai hợp đồng: {exc}") from exc


def stress_block(outcome: ToolOutcome, trace_id: str) -> B.StressResultBlock:
    payload = outcome.payload or {}
    try:
        return B.build_stress_result(
            data=payload["data"],
            trace_id=trace_id,
            source_tool=outcome.name,
            as_of=_parse_instant(payload["as_of"]),
            app_date=date.fromisoformat(payload["app_date"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractMismatch(f"stress_test sai hợp đồng: {exc}") from exc


def roadmap_block(outcome: ToolOutcome, trace_id: str) -> B.RoadmapBlock:
    payload = outcome.payload or {}
    try:
        return B.build_roadmap(
            data=payload["data"],
            trace_id=trace_id,
            source_tool=outcome.name,
            as_of=_parse_instant(payload["as_of"]),
            app_date=date.fromisoformat(payload["app_date"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractMismatch(f"get_roadmap sai hợp đồng: {exc}") from exc


def scenario_blocks(outcome: ToolOutcome, trace_id: str) -> list[B.ForecastTimelineBlock | B.ObligationImpactBlock]:
    """Các khối số liệu của `forecast___run_scenario`: `forecast_timeline` trước-sau (hũ bị tác động nhiều nhất trước) rồi `obligation_impact`."""
    payload = outcome.payload or {}
    try:
        as_of, app_date = _parse_instant(payload["as_of"]), date.fromisoformat(payload["app_date"])
        data = payload["data"]
        out: list[B.ForecastTimelineBlock | B.ObligationImpactBlock] = [
            B.build_forecast_timeline_from_data(
                data=t, trace_id=trace_id, source_tool=outcome.name, as_of=as_of, app_date=app_date
            )
            for t in data["timelines"]
        ]
        if data.get("obligation_impact"):
            out.append(
                B.build_obligation_impact(
                    data=data["obligation_impact"],
                    trace_id=trace_id,
                    source_tool=outcome.name,
                    as_of=as_of,
                    app_date=app_date,
                )
            )
        return out
    except (KeyError, ValueError, ValidationError) as exc:
        raise ContractMismatch(f"run_scenario sai hợp đồng: {exc}") from exc
