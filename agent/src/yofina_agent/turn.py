"""Một lượt hội thoại: mã điều khiển thứ tự + tự phát event AG-UI ("Cách B" của docs/research/strands-agui.md).

Vì sao không dùng `StrandsAgent` của `ag-ui-strands` (Cách A): router, đường nhanh một tool, khối UI, đường suy giảm và `turn_blocks` đều nằm *ngoài*
vòng lặp của một Agent, và cần giữ đúng thứ tự event (khối UI trước `TOOL_CALL_RESULT`, luôn kết thúc bằng `RUN_FINISHED`, không bao giờ luồng rỗng).
Strands vẫn được dùng cho `MCPClient` (tool), `Agent` viết câu trả lời, và `Model` đo đếm (`MeteredModel`).

Luồng (mã điều khiển, không để LLM quyết định thứ tự):

    RUN_STARTED
      -> L0: che PII (yofina_core.pii) -> router (model nhỏ, ép tool) song song với Guardrail đầu vào
         (router lỗi: bộ phân loại dự phòng bằng luật; Guardrail chặn: coi như ngoài phạm vi)
      -> thiếu ô bắt buộc (số tiền, cách trả, hũ): khối `clarify` đúng một câu, kết thúc lượt (lượt sau router ghép với câu trước)
      -> ý định:
           lookup (balance|transactions|forecast|obligations)   đường nhanh: một tool + một câu của model nhỏ
           what_if            L2 Orchestrator -> tool song song -> run_scenario -> khối số liệu -> L3 Analyst -> L4 Verifier -> L5 Composer (whatif.py)
           affordability      affordability_check -> khối affordability_card ngay -> model nhỏ viết 2 câu trong thời hạn (quá hạn/lỗi: bỏ phần lời)
           profile_update     update_profile KHÔNG token -> khối confirm_action
           move               get_jar_balances + move_between_jars KHÔNG token -> khối confirm
           out_of_scope       notice + suggestions (không có câu do model viết)
           chitchat           câu của router (đã qua kiểm số và Guardrail) hoặc model nhỏ
      -> khối notice (nếu suy giảm) -> lưu turn_blocks + bản ghi lượt -> RUN_FINISHED

Agent không bao giờ điền cờ xác nhận hay token; đường ghi thật do frontend gọi REST (ADR-0002).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ag_ui.core import BaseEvent, RunAgentInput

from yofina_agent import events as ev
from yofina_agent import notices, trace
from yofina_agent.clarify import resolve_clarify
from yofina_agent.compact import (
    compact_affordability,
    compact_confirm,
    compact_confirm_action,
    compact_forecast,
    compact_jars,
    compact_obligations,
    compact_resilience,
    compact_roadmap,
    compact_stress,
    compact_transactions,
)
from yofina_agent.fallback import classify_by_rules
from yofina_agent.guardrail import Guardrail, GuardrailResult
from yofina_agent.identity import Identity
from yofina_agent.jars import JarMatch, resolve_jar
from yofina_agent.roadmap_agent import UserGoal, build_roadmap
from yofina_agent.router import merge_pending, pending_params, route
from yofina_agent.schemas import (
    ClarifyChipIn,
    ClarifyRequest,
    Intent,
    IntentParams,
    IntentResult,
    Verdict,
)
from yofina_agent.settings import AgentSettings
from yofina_agent.store import (
    TurnBlockStore,
    TurnRecordStore,
    UnconfiguredTurnRecordStore,
)
from yofina_agent.textutil import match_shock_id, normalize, parse_amount_vnd, parse_goal_date
from yofina_agent.tools import (
    ContractMismatch,
    GatewayTools,
    ToolKind,
    ToolOutcome,
    affordability_block,
    confirm_action_block,
    confirm_block,
    forecast_block,
    jar_summary_block,
    resilience_block,
    roadmap_block,
    stress_block,
)
from yofina_agent.verifier import Allowed, NumericGrounding
from yofina_agent.whatif import WhatIfState, run_what_if
from yofina_agent.writer import PHASE4_TASKS, check_grounding, has_ungrounded_numbers, write_stream
from yofina_core import blocks as B
from yofina_core.clock import app_timezone
from yofina_core.errors import ErrorCode
from yofina_core.llm import AllModelsFailed, LlmGateway, ModelBudgetExceeded, TurnScope
from yofina_core.money import format_vnd, format_vnd_short
from yofina_core.pii import mask_pii
from yofina_core.resilience import load_shock_set
from yofina_core.roadmap import JobStage, Roadmap, RoadmapReasonCode
from yofina_core.suitability import SuitabilityVerdict

log = logging.getLogger("yofina.agent.turn")

_DONE = object()

#: lỗi tạm thời của tool đáng thử lại một lần (lỗi nghiệp vụ như hết tiền, từ chối quyền thì không)
_TRANSIENT_CODES = {
    ErrorCode.DATABASE_UNAVAILABLE.value,
    ErrorCode.INTERNAL_ERROR.value,
    ErrorCode.RATE_LIMITED.value,
}
#: Lỗi nghiệp vụ của tool phase 4 (điểm, cú sốc) thực chất là trạng thái trống: khối `notice` kind `info`, không phải `error`.
_EMPTY_STATE_CODES = frozenset(
    {ErrorCode.PROFILE_INCOMPLETE.value, ErrorCode.FORECAST_UNAVAILABLE.value}
)
#: Lộ trình: chỉ chưa khai lương là trạng thái trống; FORECAST_UNAVAILABLE ở đây là lỗi gọi bộ tối ưu (forecast_client).
_ROADMAP_EMPTY_CODES = frozenset({ErrorCode.PROFILE_INCOMPLETE.value})
_DEGRADED_REASON = {
    ErrorCode.MODEL_BUDGET_EXCEEDED.value: "model_budget",
    ErrorCode.RATE_LIMITED.value: "model_error",
    ErrorCode.INTERNAL_ERROR.value: "model_error",
    "NUMERIC_UNVERIFIED": "verifier_failed",
}
_PENDING_INTENTS = {"what_if", "affordability", "move", "profile_update"}


@dataclass
class TurnDeps:
    """Thứ lượt hội thoại cần; test thay `tools_factory`/`llm`/`store`, mã sản phẩm dùng giá trị thật."""

    settings: AgentSettings
    llm: Callable[[], LlmGateway]  # tạo lười: đọc cấu hình/SSM sau khi đã phát RUN_STARTED
    store: TurnBlockStore
    tools_factory: Callable[[Identity], GatewayTools]
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    guardrail: Guardrail | None = None  # None: không lọc (test hoặc chưa cấu hình)
    records: TurnRecordStore = field(default_factory=UnconfiguredTurnRecordStore)


@dataclass
class CallResult:
    outcome: ToolOutcome
    compact: dict[str, Any] | None
    blocks: list[Any] = field(default_factory=list)

    @property
    def block(self) -> Any:
        return self.blocks[0] if self.blocks else None


def _jar_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(j) for j in payload["data"]["jars"]]


class Turn:
    def __init__(
        self,
        deps: TurnDeps,
        run_input: RunAgentInput,
        identity: Identity,
        *,
        trace_id: str,
        conversation_id: str,
    ) -> None:
        self.d, self.s = deps, deps.settings
        self.run_input, self.identity = run_input, identity
        self.trace_id, self.conversation_id = trace_id, conversation_id
        self.queue: asyncio.Queue[Any] = asyncio.Queue()
        self.scope = TurnScope(self.s.max_model_calls_per_turn)
        self.tools = deps.tools_factory(identity)
        self.blocks: dict[str, dict[str, Any]] = {}  # id khối -> dạng dây (giữ thứ tự phát)
        self.user_text = ""
        self.history = ""
        self.assistant_parts: list[str] = []  # các tin nhắn chữ đã phát, để lưu cùng lượt
        self.intent: str | None = None
        self.tool_calls = 0
        self.llm_down = False
        self.degrade_code: str | None = None
        self.degrade_noticed = False
        self.app_date: date | None = None
        self._llm: LlmGateway | None = None
        self._jars: CallResult | None = None
        self._jar_rows: list[dict[str, Any]] = []
        # dấu vết cho bản ghi lượt
        self._t0 = time.perf_counter()
        self.steps: list[trace.TurnStep] = []  # theo thứ tự bắt đầu; mỗi lần gọi tool một bước (call_tool)
        self.tool_log: list[ToolOutcome] = []
        self.compacts: dict[str, dict[str, Any]] = {}
        self.bases: list[Mapping[str, Any]] = []
        self.suitability: list[SuitabilityVerdict] = []
        self.extra_rules: dict[str, B.RuleCheck] = {}
        self.verified: bool | None = None
        self.outcome = "ok"
        self.outcome_code: str | None = None
        self.whatif: WhatIfState | None = None
        self.guardrail_reason: str | None = None

    # --- dấu vết ----------------------------------------------------------------------------
    @contextlib.contextmanager
    def step(self, name: str) -> Iterator[None]:
        """Đo một bước; bước giữ chỗ trong `steps` lúc BẮT ĐẦU nên lần gọi tool bên trong (kể cả song song) đứng sau nó."""
        entry = trace.TurnStep(name)
        self.steps.append(entry)
        started = time.perf_counter()
        try:
            yield
        finally:
            entry.ms = int((time.perf_counter() - started) * 1000)

    def note_basis(self, basis: Mapping[str, Any] | None) -> None:
        """Ghi cơ sở của dự báo (độ tin cậy) và phát `notice` độ tin cậy thấp nếu dữ liệu ít hoặc chỉ là ước lượng ban đầu."""
        if not basis:
            return
        self.bases.append(basis)
        if basis["is_initial_estimate"] or int(basis["history_days"]) < self.s.low_data_days:
            t, m = notices.LOW_DATA
            self.emit_notice(
                kind="low_data", code=None, title=t, message=m, degraded_reason="short_history", block_id=f"notice:{self.trace_id}:short_history"
            )
        elif (coverage := basis.get("coverage")) is not None and float(coverage) < self.s.low_coverage_threshold:
            t, m = notices.LOW_COVERAGE
            self.emit_notice(
                kind="low_data", code=None, title=t, message=m, degraded_reason="low_coverage", block_id=f"notice:{self.trace_id}:low_coverage"
            )

    def record_verdict(self, verdict: Verdict, checked: list[tuple[Any, SuitabilityVerdict]]) -> None:
        self.suitability = [v for _, v in checked]
        self.verified = verdict.ok
        self.extra_rules["numeric_grounding"] = B.RuleCheck(
            rule_id="numeric_grounding",
            label="Số liệu có căn cứ",
            outcome="pass" if verdict.grounding.ok else "fail",
            detail=f"Đã kiểm {verdict.grounding.checked_count} con số trong lời giải thích.",
        )

    def compact_of(self, short_name: str) -> dict[str, Any] | None:
        return self.compacts.get(short_name)

    def grounding_payloads(self) -> list[Any]:
        return [o.payload for o in self.tool_log if o.kind is ToolKind.OK and o.payload]

    @property
    def jar_rows(self) -> list[dict[str, Any]]:
        return self._jar_rows

    def model_calls_left(self) -> int:
        if self.llm_down:
            return 0
        cap = self.scope.max_calls
        return 10**6 if cap is None else max(cap - self.scope.calls, 0)

    def degrade_if_no_model(self) -> None:
        if self.degrade_code is None:
            self.degrade_code = ErrorCode.MODEL_BUDGET_EXCEEDED.value

    def block_app_date(self) -> date:
        return self.app_date or datetime.now(app_timezone()).date()

    # --- phát event -------------------------------------------------------------------------
    def emit(self, event: BaseEvent) -> None:
        self.queue.put_nowait(event)

    def emit_block(self, block: B._BlockBase) -> None:
        wire = B.block_to_wire(block)
        self.blocks[wire["id"]] = wire
        self.emit(ev.block_snapshot(wire))

    def emit_notice(
        self,
        *,
        kind: B.NoticeKind,
        code: str | None,
        title: str,
        message: str,
        retryable: bool | None = None,
        degraded_reason: str | None = None,
        missing: list[str] | None = None,
        suggestions: list[dict[str, str]] | None = None,
        block_id: str | None = None,
    ) -> None:
        self.emit_block(
            B.build_notice(
                kind=kind,
                title=title,
                message=message,
                trace_id=self.trace_id,
                source_tool="agent",
                as_of=self.d.now(),
                app_date=self.block_app_date(),
                code=code,
                retryable=retryable,
                degraded_reason=degraded_reason,
                missing=missing,
                suggestions=suggestions,
                block_id=block_id,
            )
        )

    async def emit_text(self, chunks: AsyncIterator[str]) -> str:
        """Phát một tin nhắn chữ từ các mẩu; luôn đóng tin nhắn kể cả khi bị lỗi/hủy giữa chừng."""
        mid, started, parts = ev.new_id("msg-"), False, []
        try:
            async for delta in chunks:
                if not started:
                    self.emit(ev.text_start(mid))
                    started = True
                self.emit(ev.text_content(mid, delta))
                parts.append(delta)
        finally:
            if started:
                self.emit(ev.text_end(mid))
            if parts:
                self.assistant_parts.append("".join(parts))
        return "".join(parts)

    async def emit_fixed_text(self, text: str) -> None:
        async def one() -> AsyncIterator[str]:
            yield text

        await self.emit_text(one())

    # --- suy giảm ---------------------------------------------------------------------------
    @property
    def llm(self) -> LlmGateway:
        assert self._llm is not None, "gọi ensure_llm() trước"
        return self._llm

    async def ensure_llm(self) -> None:
        """Nạp cổng model (đọc cấu hình/SSM, tạo client) trong luồng nền để không chặn event loop."""
        if self._llm is None and not self.llm_down:
            try:
                self._llm = await asyncio.to_thread(self.d.llm)
            except Exception as exc:  # thiếu/sai cấu hình model: suy giảm, không sập lượt
                self.llm_failed(exc)
                self.llm_down = True

    def llm_failed(self, exc: BaseException) -> None:
        """Model không gọi được: ghi nhận lý do để cuối lượt hiện một khối `notice`."""
        if isinstance(exc, ModelBudgetExceeded):
            code, down = ErrorCode.MODEL_BUDGET_EXCEEDED, exc.reason != "turn_limit"
        elif isinstance(exc, AllModelsFailed):
            code, down = ErrorCode.RATE_LIMITED, True
        else:
            code, down = ErrorCode.INTERNAL_ERROR, False
        self.llm_down = self.llm_down or down
        self.degrade_code = self.degrade_code or code.value
        log.warning(
            json.dumps(
                {
                    "event": "llm_degraded",
                    "code": code.value,
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                },
                ensure_ascii=False,
            )
        )

    def flush_degraded_notice(self, *, message_override: tuple[str, str] | None = None) -> None:
        if self.degrade_code and not self.degrade_noticed:
            title, message = message_override or notices.DEGRADED.get(
                self.degrade_code, notices.DEGRADED[ErrorCode.INTERNAL_ERROR]
            )
            self.emit_notice(
                kind="degraded",
                code=self.degrade_code,
                title=title,
                message=message,
                degraded_reason=_DEGRADED_REASON.get(self.degrade_code),
                retryable=self.degrade_code != ErrorCode.MODEL_BUDGET_EXCEEDED.value,
            )
            self.degrade_noticed = True

    def tool_failure(
        self,
        outcome: ToolOutcome,
        *,
        retryable: bool | None = None,
        empty_codes: frozenset[str] = frozenset(),
    ) -> None:
        """Lỗi tool -> khối `notice`, dùng đúng thông điệp an toàn của tool. Kind `error`, trừ khi tool trả lỗi nghiệp vụ có mã trong
        `empty_codes` (trạng thái trống như chưa khai lương, chưa có dự báo): kind `info`, vì đó không phải lỗi."""
        code = outcome.code or ErrorCode.INTERNAL_ERROR.value
        self.outcome, self.outcome_code = "error", code
        transient = outcome.kind is ToolKind.UNAVAILABLE or code in _TRANSIENT_CODES
        empty = outcome.kind is ToolKind.TOOL_ERROR and code in empty_codes
        self.emit_notice(
            kind="info" if empty else "error",
            code=code,
            title=notices.ERROR_TITLES.get(code, notices.DEFAULT_ERROR_TITLE),
            message=outcome.message or notices.GENERIC_ERROR_MESSAGE,
            retryable=retryable if retryable is not None else (transient or None),
            degraded_reason="tool_error" if transient else None,
        )

    # --- gọi tool ---------------------------------------------------------------------------
    async def call_tool(
        self,
        short_name: str,
        args: dict[str, Any],
        *,
        compact: Callable[[ToolOutcome], dict[str, Any]] | None = None,
        block: Callable[[ToolOutcome, str], Any] | None = None,
        target: str = "ledger",
        emit: bool = True,
    ) -> CallResult:
        """TOOL_CALL_START/ARGS/END -> gọi Gateway -> [ACTIVITY_SNAPSHOT khối] -> TOOL_CALL_RESULT bản gọn.

        Khối UI phát **trước** `TOOL_CALL_RESULT`; model chỉ thấy bản gọn. `block` trả một khối hoặc danh sách khối. `emit=False`: dựng khối
        nhưng chưa phát (người gọi tự phát, ví dụ khối xác nhận đi sau khối `options`).
        """
        name = self.s.tool(short_name, target=target)
        tcid = ev.new_id("tc-")
        self.emit(ev.tool_call_start(tcid, name))
        if args:
            self.emit(ev.tool_call_args(tcid, args))
        self.emit(ev.tool_call_end(tcid))

        self.tool_calls += 1
        # một bước của bản ghi lượt cho MỖI lần gọi (giữ chỗ lúc bắt đầu, nên lượt song song vẫn theo thứ tự gọi); chỉ tên, thời lượng,
        # trạng thái, mã lỗi: không tham số, không kết quả
        tstep = trace.TurnStep(trace.tool_step_name(target, short_name))
        self.steps.append(tstep)
        started = time.perf_counter()
        if self.tool_calls > self.s.max_tool_calls_per_turn:
            outcome = ToolOutcome(
                name,
                ToolKind.UNAVAILABLE,
                code=ErrorCode.RATE_LIMITED.value,
                message=notices.GENERIC_ERROR_MESSAGE,
                detail="vượt trần số tool call mỗi lượt",
            )
        else:
            finished = False
            try:
                outcome = await self.tools.call(name, args)
                finished = True
            finally:
                tstep.ms = int((time.perf_counter() - started) * 1000)
                if not finished:  # bị hủy/hết giờ/lỗi bất ngờ giữa chừng: vẫn đóng tool call cho hợp lệ
                    tstep.status, tstep.code = "error", ErrorCode.INTERNAL_ERROR.value
                    interrupted = {
                        "status": "ERROR",
                        "code": ErrorCode.INTERNAL_ERROR.value,
                        "message": notices.GENERIC_ERROR_MESSAGE,
                    }
                    self.emit(ev.tool_call_result(tcid, interrupted))

        built: list[Any] = []
        compact_view: dict[str, Any] | None = None
        if outcome.ok:
            try:
                if block is not None:
                    made = block(outcome, self.trace_id)
                    built = list(made) if isinstance(made, (list, tuple)) else [made]
                if compact is not None:
                    compact_view = compact(outcome)
            except (ContractMismatch, KeyError, ValueError) as exc:
                outcome = ToolOutcome(
                    name,
                    ToolKind.BAD_RESULT,
                    code=ErrorCode.INTERNAL_ERROR.value,
                    message=notices.GENERIC_ERROR_MESSAGE,
                    detail=str(exc)[:300],
                    args=args,
                )
                built, compact_view = [], None
        tstep.status, tstep.code = trace.tool_status(outcome)  # sau khi dựng khối: kết quả sai hợp đồng là `error`
        if outcome.payload and isinstance(outcome.payload.get("app_date"), str):
            with contextlib.suppress(ValueError):
                self.app_date = date.fromisoformat(outcome.payload["app_date"])
        self.tool_log.append(outcome)
        if compact_view is not None:
            self.compacts[short_name] = compact_view
        if emit:
            for b in built:
                self.emit_block(b)
        if outcome.ok:
            result_view = (
                compact_view if compact_view is not None else {"status": outcome.payload["status"]}
            )
        else:
            result_view = {"status": "ERROR", "code": outcome.code, "message": outcome.message}
        self.emit(ev.tool_call_result(tcid, result_view))
        return CallResult(outcome, compact_view, built)

    async def call_tool_retry(
        self, short_name: str, args: dict[str, Any], *, retry: bool = True, **kw: Any
    ) -> CallResult:
        """`call_tool`, thử lại tối đa `tool_retry_attempts` lần khi lỗi tạm thời (hết giờ, dịch vụ chưa sẵn sàng)."""
        res = await self.call_tool(short_name, args, **kw)
        if not retry:
            return res
        for _ in range(self.s.tool_retry_attempts):
            o = res.outcome
            transient = o.kind is ToolKind.UNAVAILABLE or (
                o.kind in (ToolKind.TOOL_ERROR, ToolKind.BAD_RESULT) and o.code in _TRANSIENT_CODES
            )
            if o.ok or not transient or self.tool_calls >= self.s.max_tool_calls_per_turn:
                break
            log.info(json.dumps({"event": "tool_retry", "tool": o.name, "code": o.code}))
            res = await self.call_tool(short_name, args, **kw)
        return res

    async def ensure_jars(self) -> CallResult:
        """Danh sách hũ của chính người dùng (để ánh xạ tên hũ và lấy ngày mô phỏng); gọi một lần mỗi lượt."""
        if self._jars is None:
            self._jars = await self.call_tool_retry(
                "get_jar_balances", {}, compact=lambda o: compact_jars(o.payload or {}), block=None
            )
            if self._jars.outcome.ok:
                self._jar_rows = _jar_rows(self._jars.outcome.payload or {})
        return self._jars

    def emit_jars_block(self) -> None:
        """Hiện thẻ số dư từ lần đọc hũ đã có (dùng khi cần cho người dùng thấy số)."""
        if self._jars and self._jars.outcome.ok:
            with contextlib.suppress(ContractMismatch):
                self.emit_block(jar_summary_block(self._jars.outcome, self.trace_id))

    # --- viết câu trả lời -------------------------------------------------------------------
    async def write(self, task: str, question: str, compact: Mapping[str, Any]) -> None:
        if self.llm_down:
            return
        if task in PHASE4_TASKS:
            await self.write_buffered(
                task, question, compact, timeout=None, max_tokens=self.s.writer_max_tokens
            )
            return
        try:
            text = await self.emit_text(
                write_stream(
                    self.llm,
                    task=task,
                    question=question,
                    compact=compact,
                    scope=self.scope,
                    max_tokens=self.s.writer_max_tokens,
                    turn_limit=self.s.writer_turn_limit,
                    output_token_limit=self.s.writer_output_token_limit,
                )
            )
        except Exception as exc:
            self.llm_failed(exc)
            return
        if text and (bad := check_grounding(text, compact)):
            log.warning(json.dumps({"event": "numeric_ungrounded", "values": bad[:5]}))
            self.degrade_code = self.degrade_code or "NUMERIC_UNVERIFIED"

    async def write_buffered(
        self, task: str, question: str, compact: Mapping[str, Any], *, timeout: float | None, max_tokens: int
    ) -> None:
        """Kiểm trọn phần lời trước khi phát. Bỏ phần lời nếu quá hạn hoặc gặp lỗi."""
        if self.llm_down or self.model_calls_left() < 1:
            return

        async def collect() -> str:
            parts = []
            async for delta in write_stream(
                self.llm,
                task=task,
                question=question,
                compact=compact,
                scope=self.scope,
                max_tokens=max_tokens,
                turn_limit=self.s.writer_turn_limit,
                output_token_limit=self.s.writer_output_token_limit,
            ):
                parts.append(delta)
            return "".join(parts)

        try:
            text = await asyncio.wait_for(collect(), timeout=timeout)
        except TimeoutError:
            log.info(json.dumps({"event": "writer_timeout", "task": task, "seconds": timeout}))
            return
        except Exception as exc:
            self.llm_failed(exc)
            return
        if not text.strip():
            return
        if check_grounding(text, compact) or (
            task in PHASE4_TASKS and has_ungrounded_numbers(text, compact)
        ):
            log.warning(json.dumps({"event": "numeric_ungrounded", "task": task}))
            return
        gr = await self.check_output(text)
        if gr is not None and gr.blocked:
            return
        await self.emit_fixed_text(text)

    async def check_output(self, text: str) -> GuardrailResult | None:
        """Guardrail đầu ra cho văn bản hoàn chỉnh trước khi phát (None nếu không có guardrail)."""
        g = self.d.guardrail
        if g is None or not g.enabled:
            return None
        with self.step("guardrail_out"):
            res = await g.check(mask_pii(text).text, "OUTPUT")
        self.extra_rules["guardrail_output"] = B.RuleCheck(
            rule_id="guardrail_output",
            label="Lọc nội dung đầu ra",
            outcome="fail" if res.blocked else "pass",
        )
        return res

    # --- điều khiển -------------------------------------------------------------------------
    async def execute(self) -> None:
        try:
            try:
                async with asyncio.timeout(self.s.run_timeout_seconds):
                    await self.flow()
            except TimeoutError:
                log.warning(
                    json.dumps({"event": "turn_timeout", "seconds": self.s.run_timeout_seconds})
                )
                self.degrade_code = self.degrade_code or ErrorCode.RATE_LIMITED.value
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("lượt hội thoại lỗi ngoài dự kiến")
                self.degrade_code = self.degrade_code or ErrorCode.INTERNAL_ERROR.value
            self.flush_degraded_notice()
            await self.persist()
        finally:
            with contextlib.suppress(Exception):
                await self.tools.aclose()
            self.emit(
                ev.run_finished(
                    self.run_input,
                    result={
                        "trace_id": self.trace_id,
                        "intent": self.intent,
                        # suy giảm: model lỗi (degrade_code) hoặc Verifier rơi vào đường dự phòng (verified=False, như bản ghi lượt)
                        "degraded": self.degrade_code is not None or self.verified is False,
                        "model_calls": self.scope.calls,
                        "tool_calls": self.tool_calls,
                        "verifier_rounds": self.whatif.attempts if self.whatif else 0,
                    },
                    usage=self.scope.usage_by_model(),
                )
            )
            self.queue.put_nowait(_DONE)

    def turn_record(self) -> dict[str, Any]:
        """Bản ghi lượt (`agent_turn`): một lần mỗi lượt, do mã dựng từ dấu vết, không do LLM viết."""
        extra = list(self.extra_rules.values())
        outcome = self.outcome
        if self.intent == "out_of_scope" and outcome == "ok":
            outcome = "rejected"
        measured_bases = [b for b in self.bases if b.get("coverage") is not None]
        record = trace.build_record(
            trace_id=self.trace_id,
            conversation_id=self.conversation_id,
            intent=self.intent,
            outcome=outcome,
            code=self.outcome_code or self.degrade_code,
            outcomes=self.tool_log,
            suitability=self.suitability,
            extra_rules=extra,
            bases=measured_bases,
            blocks=list(self.blocks.values()),
            usage_by_model=self.scope.usage_by_model(),
            model_calls=self.scope.calls,
            steps=self.steps,
            duration_ms=int((time.perf_counter() - self._t0) * 1000),
            verified=self.verified,
        )
        tool_steps = sum(trace.TOOL_SEP in s.step for s in self.steps)
        kept = sum(trace.TOOL_SEP in s["step"] for s in record["step_timings"])
        if kept < tool_steps:  # quá maxItems của `TraceStep[]`: đã bỏ bớt lần gọi `ok` lặp lại (trace.step_timings)
            log.info(json.dumps({"event": "trace_steps_truncated", "tool_calls": tool_steps, "kept": kept}))
        if self.intent == "resilience" and self.bases and not measured_bases:
            basis = self.bases[0]
            record["confidence"] = B.ExplainConfidence(
                band=basis["confidence_band"],
                reasons=[f"Dự báo dựa trên {basis['history_days']} ngày dữ liệu."],
            ).model_dump()
        return record

    async def persist(self) -> None:
        """Lưu lượt (kể cả lượt suy giảm hoặc chỉ có chữ) và bản ghi lượt. Lỗi lưu không làm hỏng lượt."""
        assistant_text = "\n\n".join(self.assistant_parts)
        jobs = []
        if self.blocks or self.user_text or assistant_text:
            jobs.append(
                self.d.store.save(
                    tools=self.tools,
                    conversation_id=self.conversation_id,
                    trace_id=self.trace_id,
                    blocks=list(self.blocks.values()),
                    user_text=self.user_text,
                    assistant_text=assistant_text,
                )
            )
        if self.intent is not None:
            jobs.append(self.d.records.save(tools=self.tools, record=self.turn_record()))
        if not jobs:
            return
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*jobs, return_exceptions=True),
                timeout=max(self.s.turn_blocks_timeout_seconds, self.s.turn_record_timeout_seconds),
            )
        except TimeoutError:
            log.warning(json.dumps({"event": "turn_persist_timeout"}))
            return
        for r in results:
            if isinstance(r, BaseException):
                log.warning(json.dumps({"event": "turn_persist_error", "error": repr(r)[:200]}))

    async def flow(self) -> None:
        found = ev.last_user_text(self.run_input)
        if found is None:
            self.emit_notice(
                kind="error",
                code=ErrorCode.PARAMS_INVALID.value,
                title=notices.DEFAULT_ERROR_TITLE,
                message=notices.EMPTY_INPUT_MESSAGE,
            )
            return
        raw_question, index = found
        # L0: che PII trước khi vào LLM, vào log và vào bản lưu
        question = mask_pii(raw_question).text
        self.user_text = question
        self.history = mask_pii(
            ev.format_history(
                self.run_input,
                before_index=index,
                max_messages=self.s.history_messages,
                max_chars=self.s.history_chars_per_message,
            )
        ).text

        await self.ensure_llm()
        routed = await self.classify_guarded(question, self.history)
        if routed is None:
            return
        self.intent = routed.intent
        if await self.answer_keep_previous(routed, question, index):
            return
        # Câu trả lời cụt cho khối `clarify`: giữ tham số của câu đang chờ (số tiền, người nhận, hũ...) bằng mã, không trông vào model nhớ.
        routed = merge_pending(routed, question, self.pending_params_before(index))
        handler = self._intent_handlers()[routed.intent]
        # Handler tự kiểm mã cú sốc và chọn thao tác với lộ trình.
        if routed.intent not in ("stress", "roadmap") and (
            req := resolve_clarify(routed) or await self.unknown_jar_clarify(routed)
        ):
            await self.emit_clarify(req, routed)
            return
        await handler(routed, question)

    def _intent_handlers(self) -> dict[Intent, Callable[[IntentResult, str], Awaitable[None]]]:
        return {
            "lookup": self.on_lookup,
            "what_if": self.on_what_if,
            "affordability": self.on_affordability,
            "profile_update": self.on_profile_update,
            "move": self.on_move,
            "out_of_scope": self.on_out_of_scope,
            "chitchat": self.on_chitchat,
            "resilience": self.on_resilience,
            "stress": self.on_stress,
            "roadmap": self.on_roadmap,
        }

    def pending_params_before(self, index: int) -> dict[str, Any] | None:
        """Tham số (đọc bằng mã) của câu đang chờ trả lời câu hỏi lại, từ các tin trước `index` (bỏ dòng hệ thống, đã che PII)."""
        msgs = [
            (m.role, mask_pii(ev.message_text(m)).text)
            for m in self.run_input.messages[:index]
            if m.role in ("user", "assistant") and ev.message_text(m)
        ]
        return pending_params(msgs, marker_excluded=notices.KEEP_PREVIOUS_MARKER)

    async def answer_keep_previous(self, routed: IntentResult, question: str, index: int) -> bool:
        """Người dùng trả lời câu "vẫn giữ khoản trước chứ" (lượt trước agent hỏi để gộp kịch bản). True nếu đã xử lý lượt.

        Router chỉ quyết định GIỮ hay BỎ (đo trên model thật: đúng ổn định); khoản MỚI lấy lại bằng cách chạy what-if trên chính câu hỏi
        "nếu ... thì sao" trước đó của người dùng (câu đứng riêng thì Orchestrator dựng đúng), không nhờ model ghép hai câu có hai số tiền.
        Bấm chip thì giữ/bỏ theo đúng chuỗi chip. Guardrail chặn (ra out_of_scope) thì không đi đường này.
        """
        pending = ev.pending_question_before(self.run_input, before_index=index, marker=notices.KEEP_PREVIOUS_MARKER)
        if pending is None or routed.intent == "out_of_scope":
            return False
        chips = [c["value"] for c in notices.KEEP_PREVIOUS_CHIPS]
        if question.strip() == chips[0]:
            keep: bool | None = True
        elif question.strip() == chips[1]:
            keep = False
        else:
            keep = routed.params.keep_previous if routed.intent == "what_if" else None
        if keep is None:
            return False
        pending_q = mask_pii(ev.message_text(self.run_input.messages[pending])).text
        pending_history = mask_pii(
            ev.format_history(
                self.run_input,
                before_index=pending,
                max_messages=self.s.history_messages,
                max_chars=self.s.history_chars_per_message,
            )
        ).text
        self.intent = "what_if"
        r = IntentResult(
            intent="what_if",
            params=IntentParams(keep_previous=keep),
            confidence=routed.confidence,
            needs_clarification=False,
        )
        self.whatif = await run_what_if(self, r, pending_q, pending_history)
        if self.whatif.spec is None and not self.whatif.handled:
            t, m = notices.SCENARIO_UNBUILDABLE
            self.emit_notice(kind="error", code=ErrorCode.SCENARIO_INVALID.value, title=t, message=m)
        return True

    async def classify_guarded(self, question: str, history: str) -> IntentResult | None:
        """Router song song với Guardrail đầu vào. Guardrail chặn thì coi là ngoài phạm vi (kết quả của router bị bỏ)."""
        g = self.d.guardrail
        gtask = None
        if g is not None and g.enabled:
            gtask = asyncio.create_task(self._timed_guardrail(g, question))
        routed = await self.classify(question, history)
        if gtask is not None:
            gr = await gtask
            self.extra_rules["guardrail_input"] = B.RuleCheck(
                rule_id="guardrail_input",
                label="Lọc nội dung đầu vào",
                outcome="fail" if gr.blocked else "pass",
            )
            if gr.blocked:
                self.guardrail_reason = gr.reason
                return IntentResult(
                    intent="out_of_scope", params=IntentParams(), confidence=1.0, needs_clarification=False
                )
        return routed

    async def _timed_guardrail(self, g: Guardrail, text: str) -> GuardrailResult:
        with self.step("guardrail_in"):
            return await g.check(text, "INPUT")

    async def classify(self, question: str, history: str) -> IntentResult | None:
        """Khớp cú sốc theo cấu hình trước, sau đó dùng router LLM hoặc luật dự phòng."""
        if (shock_id := match_shock_id(question)) is not None:
            return IntentResult(
                intent="stress",
                params=IntentParams(shock_id=shock_id),
                confidence=1.0,
                needs_clarification=False,
            )
        if not self.llm_down:
            try:
                with self.step("router"):
                    res = await route(
                        self.llm,
                        question,
                        history,
                        max_attempts=self.s.router_max_attempts,
                        max_tokens=self.s.router_max_tokens,
                        scope=self.scope,
                    )
                return res.value
            except (
                Exception
            ) as exc:  # ModelBudgetExceeded, AllModelsFailed, StructuredOutputError, lỗi mạng...
                self.llm_failed(exc)
        fallback = classify_by_rules(question)
        log.info(
            json.dumps(
                {"event": "router_fallback", "intent": fallback.intent if fallback else None}
            )
        )
        if fallback is None:
            self.flush_degraded_notice(message_override=notices.DEGRADED["NOT_UNDERSTOOD"])
        else:
            self.intent = fallback.intent
        return fallback

    # --- tra cứu (đường nhanh) --------------------------------------------------------------
    async def on_lookup(self, r: IntentResult, question: str) -> None:
        kind = r.params.lookup_kind or "balance"
        await {
            "balance": self.on_balance,
            "transactions": self.on_transactions,
            "forecast": self.on_forecast,
            "obligations": self.on_obligations,
        }[kind](r, question)

    async def on_balance(self, r: IntentResult, question: str) -> None:
        res = await self.call_tool_retry(
            "get_jar_balances",
            {},
            compact=lambda o: compact_jars(o.payload or {}),
            block=jar_summary_block,
        )
        if not res.outcome.ok:
            self.tool_failure(res.outcome)
            return
        assert res.compact is not None
        await self.write("balance", question, res.compact)

    async def on_obligations(self, r: IntentResult, question: str) -> None:
        res = await self.call_tool_retry(
            "get_obligations", {}, compact=lambda o: compact_obligations(o.payload or {})
        )
        if not res.outcome.ok:
            self.tool_failure(res.outcome)
            return
        assert res.compact is not None
        await self.write("obligations", question, res.compact)

    async def on_transactions(self, r: IntentResult, question: str) -> None:
        p = r.params
        jars = await self.ensure_jars()
        if not jars.outcome.ok:
            self.tool_failure(jars.outcome)
            return
        args: dict[str, Any] = {}
        want = p.jar_text or (
            question if self.llm_down else None
        )  # suy giảm: dò tên hũ trong cả câu
        if want:
            match = resolve_jar(want, self._jar_rows)
            if match.status == "ok":
                args["jar"] = match.code
            elif p.jar_text:
                await self.ask_which_jar("hũ cần tra giao dịch", p.jar_text, match, question)
                return
        limit = p.limit if p.limit and p.limit > 0 else self.s.transactions_default_limit
        args["limit"] = min(limit, self.s.transactions_max_limit)
        if p.days_back and p.days_back > 0 and self.app_date:
            args["to_date"] = self.app_date.isoformat()
            args["from_date"] = (self.app_date - timedelta(days=p.days_back)).isoformat()
        names = {j["code"]: j["name"] for j in self._jar_rows}
        res = await self.call_tool_retry(
            "query_transactions",
            args,
            compact=lambda o: compact_transactions(o.payload or {}, names, args["limit"]),
        )
        if not res.outcome.ok:
            self.tool_failure(res.outcome)
            return
        assert res.compact is not None
        await self.write("transactions", question, res.compact)

    async def on_forecast(self, r: IntentResult, question: str) -> None:
        """Dự báo MỘT hũ: ánh xạ tên hũ bằng dữ liệu của tool, gọi `forecast___get_forecast`, phát khối `forecast_timeline` (số của tool)
        rồi để model nhỏ viết 1 đến 2 câu từ bản gọn."""
        jars = await self.ensure_jars()
        if not jars.outcome.ok:
            self.tool_failure(jars.outcome)
            return
        p = r.params
        want = p.jar_text or (
            question if self.llm_down else None
        )  # suy giảm: dò tên hũ trong cả câu
        match = resolve_jar(want, self._jar_rows) if want else JarMatch("empty")
        if match.status != "ok":
            await self.ask_which_jar("hũ cần xem dự báo", p.jar_text or "", match, question)
            return
        res = await self.call_tool_retry(
            "get_forecast",
            {"jar": match.code},
            target="forecast",
            compact=lambda o: compact_forecast(o.payload or {}),
            block=forecast_block,
        )
        if not res.outcome.ok:
            self.tool_failure(res.outcome)
            return
        assert res.compact is not None
        self.note_basis(_forecast_basis(res.outcome.payload))
        await self.write("forecast", question, res.compact)

    async def on_resilience(self, r: IntentResult, question: str) -> None:
        res = await self.call_tool_retry(
            "get_resilience_score",
            {},
            target="forecast",
            compact=lambda o: compact_resilience(o.payload or {}),
            block=resilience_block,
        )
        if not res.outcome.ok:
            self.tool_failure(res.outcome, empty_codes=_EMPTY_STATE_CODES)
            return
        assert res.compact is not None and isinstance(res.block, B.ResilienceScoreBlock)
        self.note_basis(res.block.data.basis.model_dump())
        await self.write("resilience", question, res.compact)

    async def on_stress(self, r: IntentResult, question: str) -> None:
        shocks = load_shock_set()
        shock_id = r.params.shock_id
        if shock_id is None or shocks.get(shock_id) is None:
            await self.emit_clarify(
                ClarifyRequest(
                    slot="other",
                    question=notices.STRESS_QUESTION,
                    chips=[
                        ClarifyChipIn(label=shock.label[:40], value=notices.STRESS_CHIP_VALUE.format(label=shock.label))
                        for shock in shocks.shocks[:6]
                    ],
                ),
                r,
            )
            return
        res = await self.call_tool_retry(
            "stress_test",
            {"shock_id": shock_id},
            target="forecast",
            compact=lambda o: compact_stress(o.payload or {}),
            block=stress_block,
        )
        if not res.outcome.ok:
            self.tool_failure(res.outcome, empty_codes=_EMPTY_STATE_CODES)
            return
        assert res.compact is not None
        await self.write("stress", question, res.compact)

    async def on_roadmap(self, r: IntentResult, question: str) -> None:
        # Muốn sửa một bước ("giảm số tiền ở bước ..."): chat chưa có tool sửa bước, nên chỉ ra bước khớp và chỗ sửa.
        if _asks_step_edit(question):
            await self.on_roadmap_step_edit(r, question)
            return
        # Người dùng nói mục tiêu trong câu: lập lộ trình theo mục tiêu đó (roadmap không bao giờ hỏi lại).
        goal = await self.roadmap_user_goal(r.params)
        create = r.params.roadmap_action == "create" or goal is not None
        which = "latest" if create else self.s.roadmap_default_which
        res = await self.call_tool_retry(
            "get_roadmap",
            {"which": which},
            target="planner",
            compact=lambda o: compact_roadmap(o.payload or {}),
            block=roadmap_block,
            emit=not create,
        )
        if res.outcome.code == ErrorCode.ROADMAP_NOT_FOUND.value:
            latest = res.outcome if which == "latest" else None
            await self.on_roadmap_missing(r, question, latest_outcome=latest, user_goal=goal)
            return
        if not res.outcome.ok:
            self.tool_failure(res.outcome)
            return
        if create:
            base, versions = await self.roadmap_base(res.outcome)
            await self.generate_roadmap(
                "user_request", question, latest_outcome=base, user_goal=goal, versions=versions
            )
            return
        assert res.compact is not None
        await self.write("roadmap", question, res.compact)

    async def on_roadmap_step_edit(self, r: IntentResult, question: str) -> None:
        """Đọc lộ trình ĐANG DÙNG (trang Lộ trình mở đúng bản này và có nút Sửa từng bước), chỉ ra bước khớp câu người dùng bằng mã
        rồi nói sửa ở đâu. Không lưu gì, không nói là đã sửa; không khớp bước nào thì nói rõ. Lời đáp dựng bằng mã."""
        res = await self.call_tool_retry(
            "get_roadmap",
            {"which": "active"},
            target="planner",
            compact=lambda o: compact_roadmap(o.payload or {}),
            block=roadmap_block,
        )
        if res.outcome.code == ErrorCode.ROADMAP_NOT_FOUND.value:
            await self.emit_fixed_text(notices.ROADMAP_EDIT_NO_ROADMAP)
            return
        if not res.outcome.ok or (roadmap := _roadmap_of(res.outcome)) is None:
            self.tool_failure(res.outcome)
            return
        await self.ensure_jars()  # tên hũ để khớp câu người dùng; đọc hỏng thì vẫn khớp được theo loại bước hoặc số thứ tự
        names = {str(j["code"]): str(j["name"]) for j in self._jar_rows}
        matches, mentioned = _match_steps(roadmap, question, names)
        wanted = r.params.amount_vnd or parse_amount_vnd(question)
        amount = format_vnd(wanted) if wanted else None
        if not matches:
            about = f" (bước có hũ {', '.join(names[c] for c in mentioned)})" if mentioned else ""
            await self.emit_fixed_text(
                notices.ROADMAP_EDIT_NONE.format(version=roadmap.version, about=about)
            )
            return
        if len(matches) == 1:
            phase, step = matches[0]
            detail = (f"{format_vnd(step.amount_vnd)}, " if step.amount_vnd else "") + f"giai đoạn “{phase.title}”"
            head = notices.ROADMAP_EDIT_MATCH.format(title=step.title, detail=detail, version=roadmap.version)
        else:
            titles = "; ".join(f"“{step.title}”" for _, step in matches[:3])
            head = notices.ROADMAP_EDIT_MANY.format(
                count=len(matches), version=roadmap.version, titles=titles
            )
        how = (
            notices.ROADMAP_EDIT_HOW_AMOUNT.format(amount=amount) if amount else notices.ROADMAP_EDIT_HOW
        )
        await self.emit_fixed_text(f"{head} {how}")

    async def roadmap_base(self, latest: ToolOutcome) -> tuple[ToolOutcome, _RoadmapVersions]:
        """Bản gốc cho lần lập lại và các phiên bản liên quan, đọc TRƯỚC khi lưu.

        Lưu một bản mới làm bản `proposed` đang chờ bị bỏ (`discarded`, `app_save_roadmap` của migration 0052), nên phải biết bản đó
        để nói cho người dùng. Bản mới nhất không phải bản đang dùng (đang chờ chọn, hoặc đã bị bỏ hay bị thay) thì đọc bản đang
        dùng làm gốc như job sinh lại: lưu dựa trên một bản đã bỏ thì `save_roadmap` trả ROADMAP_VERSION_CONFLICT.
        """
        newest = _roadmap_of(latest)
        if newest is None:
            return latest, _RoadmapVersions()
        if newest.status == "active":
            return latest, _RoadmapVersions(active_version=newest.version)
        pending = newest if newest.status == "proposed" else None
        versions = _RoadmapVersions(
            pending_version=pending.version if pending else None,
            pending_reason=pending.reason.code if pending else None,
        )
        res = await self.call_tool_retry("get_roadmap", {"which": "active"}, target="planner", emit=False)
        active = _roadmap_of(res.outcome)
        if active is None or active.status != "active":
            return latest, versions
        return res.outcome, replace(versions, active_version=active.version)

    async def roadmap_user_goal(self, p: IntentParams) -> UserGoal | None:
        """Đổi mục tiêu router trích (amount_vnd, jar_text, date_text) ra mã hũ và ngày ISO bằng mã. Chỉ nhận hũ kind `saving`.

        Không dùng được thì bỏ mục tiêu và nói rõ bằng một câu cố định (không hỏi lại). Không lưu gì vào hũ.
        """
        if p.amount_vnd is None and not p.date_text:
            return None
        jars = await self.ensure_jars()
        if not jars.outcome.ok:
            return None  # build_roadmap đọc lại hũ và báo lỗi của tool
        match = resolve_jar(p.jar_text, self._jar_rows)
        if match.status != "ok":
            note = (
                _GOAL_NO_JAR
                if match.status == "empty"
                else _GOAL_UNKNOWN_JAR.format(typed=(p.jar_text or "")[:40])
            )
            await self.emit_fixed_text(note)
            return None
        row = next(j for j in self._jar_rows if j["code"] == match.code)
        name = str(row["name"])
        if row.get("kind") != "saving":
            await self.emit_fixed_text(_GOAL_NOT_SAVING.format(name=name))
            return None
        target_date: date | None = None
        if p.date_text:
            today = self.app_date or self.block_app_date()
            target_date = parse_goal_date(p.date_text, today)
            if target_date is None:
                await self.emit_fixed_text(
                    _GOAL_BAD_DATE.format(typed=p.date_text[:40], name=name)
                )
                if p.amount_vnd is None:
                    return None
        if p.amount_vnd is None and row.get("goal_vnd") is None:
            await self.emit_fixed_text(_GOAL_NO_AMOUNT.format(name=name))
            return None
        return UserGoal(
            jar=str(match.code),
            target_vnd=p.amount_vnd,
            target_date=target_date.isoformat() if target_date else None,
        )

    async def on_roadmap_missing(
        self,
        r: IntentResult,
        question: str,
        *,
        latest_outcome: ToolOutcome | None = None,
        user_goal: UserGoal | None = None,
    ) -> None:
        await self.generate_roadmap(
            "initial", question, latest_outcome=latest_outcome, user_goal=user_goal
        )

    async def generate_roadmap(
        self,
        reason_code: RoadmapReasonCode,
        question: str,
        *,
        behavior_flag_id: str | None = None,
        shock_id: str | None = None,
        latest_outcome: ToolOutcome | None = None,
        user_goal: UserGoal | None = None,
        versions: _RoadmapVersions | None = None,
    ) -> None:
        await self.ensure_llm()
        # Lượt lập lộ trình dùng trần tool call riêng: mỗi bước tốn một lượt check_suitability mỗi vòng (Lambda tất định, các bước
        # của một vòng chạy song song). Trần lượt gọi model giữ nguyên (TurnScope).
        if self.s.roadmap_max_tool_calls_per_turn > self.s.max_tool_calls_per_turn:
            self.s = replace(self.s, max_tool_calls_per_turn=self.s.roadmap_max_tool_calls_per_turn)
        # Lượt đã đọc hũ (đổi mục tiêu sang mã hũ): build_roadmap dùng lại lần đọc đó, không tốn thêm tool call.
        cached_jars = self._jars.outcome if self._jars is not None and self._jars.outcome.ok else None

        async def call(short_name: str, args: dict[str, Any], target: str) -> ToolOutcome:
            if short_name == "get_jar_balances" and cached_jars is not None:
                return cached_jars
            if self.tool_calls >= self.s.max_tool_calls_per_turn:
                return ToolOutcome(
                    self.s.tool(short_name, target=target), ToolKind.UNAVAILABLE,
                    code=ErrorCode.RATE_LIMITED.value, message=notices.GENERIC_ERROR_MESSAGE,
                )
            # Lưu có thể đã commit khi mất kết nối. Chỉ lõi xử lý retry khi có xung đột rõ ràng.
            res = await self.call_tool_retry(
                short_name, args, target=target, retry=short_name != "save_roadmap"
            )
            return res.outcome

        with contextlib.ExitStack() as spans:
            def on_stage(stage: JobStage, _progress: int) -> None:
                spans.close()
                spans.enter_context(self.step(f"roadmap_{stage}"))

            result = await build_roadmap(
                call, None if self.llm_down else self.llm, self.s, self.scope,
                reason_code=reason_code, behavior_flag_id=behavior_flag_id, shock_id=shock_id,
                on_stage=on_stage,
                # lần đọc hũ dùng lại không tính vào trần, nên ngân sách bước bằng lượt không đọc hũ trước
                tool_calls_left=self.s.max_tool_calls_per_turn - self.tool_calls + int(cached_jars is not None),
                latest_outcome=latest_outcome, user_goal=user_goal,
            )
        self.suitability.extend(result.suitability)
        if result.model_error is not None:
            self.llm_failed(result.model_error)
        if result.model_budget_exhausted:
            self.degrade_if_no_model()
        if result.outcome is None:
            if self.degrade_code is not None:
                self.flush_degraded_notice(message_override=notices.ROADMAP_UNBUILDABLE)
            else:
                self.outcome, self.outcome_code = "error", ErrorCode.ROADMAP_INVALID.value
                title, message = notices.ROADMAP_UNBUILDABLE
                self.emit_notice(kind="error", code=self.outcome_code, title=title, message=message)
            return
        if not result.outcome.ok:
            self.tool_failure(result.outcome, empty_codes=_ROADMAP_EMPTY_CODES)
            return
        try:
            block = roadmap_block(result.outcome, self.trace_id)
        except ContractMismatch as exc:
            self.tool_failure(ToolOutcome(
                result.outcome.name, ToolKind.BAD_RESULT,
                code=ErrorCode.INTERNAL_ERROR.value, detail=str(exc),
            ))
            return
        self.verified = True
        self.emit_block(block)
        versions_note = self.roadmap_versions_note(block.data, versions)
        # Lời kết dựng bằng mã từ dữ liệu khối: lượt lập thường đã dùng hết trần lượt gọi model (router + phác thảo + vòng sửa) nên
        # writer bị bỏ qua và trợ lý chỉ còn khối (Runtime v20). Dựng bằng mã thì luôn có, đúng số và không tốn lượt gọi model.
        goal = _user_goal_compact(user_goal, self._jar_rows) if user_goal is not None else None
        await self.emit_fixed_text(
            _roadmap_closing(block.data, versions_note.get("active_version"), goal)
        )

    def roadmap_versions_note(
        self, saved: B.RoadmapData, versions: _RoadmapVersions | None
    ) -> dict[str, Any]:
        """Nói rõ bản vừa lưu đứng ở đâu so với các phiên bản khác: khối `notice` (info) khi nó thay bản đề xuất đang chờ, và các
        trường cho câu trả lời (bản đang dùng, bản bị thay). Số phiên bản lấy từ get_roadmap đã đọc trước khi lưu."""
        if versions is None:
            return {}
        out: dict[str, Any] = {}
        if saved.status == "proposed" and versions.active_version is not None:
            out["active_version"] = versions.active_version
        old = versions.pending_version
        if old is None or saved.version <= old:
            return out
        reason = notices.ROADMAP_REASON_LABELS.get(versions.pending_reason or "", notices.ROADMAP_REASON_FALLBACK)
        out["replaced_proposal"] = {"version": old, "reason": reason}
        message = notices.ROADMAP_PROPOSAL_REPLACED.format(old=old, reason=reason)
        if "active_version" in out:
            message += " " + notices.ROADMAP_PROPOSED_NEXT.format(active=out["active_version"])
        self.emit_notice(
            kind="info",
            code="ROADMAP_PROPOSAL_REPLACED",
            title=notices.ROADMAP_PROPOSAL_REPLACED_TITLE,
            message=message,
        )
        return out

    # --- what-if và kiểm tra trước khi quẹt -------------------------------------------------
    async def on_what_if(self, r: IntentResult, question: str) -> None:
        self.whatif = await run_what_if(self, r, question, self.history)
        if self.whatif.spec is not None or self.whatif.handled:
            return
        # Không dựng được kịch bản (model hỏng và kiểu kịch bản không có đường dựng bằng mã): món mua thì vẫn cho thẻ kiểm tra tất định
        # (cùng số với POST /affordability), không thì nói thật là chưa dựng được.
        if r.params.amount_vnd and r.params.scenario_kind in (None, "one_time_purchase", "bnpl_purchase"):
            await self.on_affordability(r, question)
            return
        t, m = notices.SCENARIO_UNBUILDABLE
        self.emit_notice(kind="error", code=ErrorCode.SCENARIO_INVALID.value, title=t, message=m)

    async def on_affordability(self, r: IntentResult, question: str) -> None:
        """F3 trong chat: `affordability_check` -> khối `affordability_card` NGAY -> model nhỏ viết 2 câu trong thời hạn (lỗi/quá hạn: bỏ lời)."""
        p = r.params
        args: dict[str, Any] = {"amount_vnd": p.amount_vnd}
        if p.funding:
            args["funding_source"] = p.funding
        if p.label:
            args["label"] = p.label[:60]
        if p.jar_text:
            jars = await self.ensure_jars()
            if jars.outcome.ok and (m := resolve_jar(p.jar_text, self._jar_rows)).status == "ok":
                args["jar"] = m.code
        res = await self.call_tool_retry(
            "affordability_check",
            args,
            target="forecast",
            compact=lambda o: compact_affordability(o.payload or {}),
            block=affordability_block,
        )
        if not res.outcome.ok:
            self.tool_failure(res.outcome)
            return
        assert res.compact is not None
        data = (res.outcome.payload or {}).get("data") or {}
        self.note_basis(data.get("basis"))
        await self.write_buffered(
            "affordability",
            question,
            res.compact,
            timeout=self.s.affordability_text_timeout_seconds,
            max_tokens=self.s.affordability_text_max_tokens,
        )

    # --- khai báo hồ sơ ---------------------------------------------------------------------
    async def on_profile_update(self, r: IntentResult, question: str) -> None:
        """`update_profile` KHÔNG token -> khối `confirm_action` (chưa lưu gì cho tới khi người dùng bấm Xác nhận)."""
        p = r.params
        args: dict[str, Any] = {}
        if p.salary_vnd:
            args["monthly_salary_vnd"] = p.salary_vnd
        if p.payday_day:
            args["payday_day"] = p.payday_day
        if p.obligation_name:
            obl: dict[str, Any] = {"op": "upsert", "name": p.obligation_name, "amount_vnd": p.amount_vnd, "cycle": "monthly"}
            if p.due_day:
                obl["due_day"] = p.due_day
            existing = await self.call_tool_retry("get_obligations", {}, compact=lambda o: compact_obligations(o.payload or {}))
            match = _match_obligation(p.obligation_name, existing.outcome.payload) if existing.outcome.ok else None
            if match is not None:
                obl["obligation_id"] = match["id"]  # sửa khoản đã có, không tạo trùng
            elif p.obligation_kind is not None:
                obl["kind"] = p.obligation_kind
            else:
                await self.emit_clarify(_kind_question(), r)
                return
            args["obligation"] = obl
        res = await self.call_tool_retry(
            "update_profile", args, compact=lambda o: compact_confirm_action((o.payload or {})["data"]), block=confirm_action_block
        )
        o = res.outcome
        if o.kind is ToolKind.NEEDS_CONFIRMATION and res.compact is not None:
            await self.write("confirm_action", question, res.compact)
        elif o.kind is ToolKind.OK:
            log.error(json.dumps({"event": "write_ok_without_token", "tool": o.name}))
            self.emit_notice(
                kind="error",
                code=ErrorCode.INTERNAL_ERROR.value,
                title=notices.DEFAULT_ERROR_TITLE,
                message=notices.GENERIC_ERROR_MESSAGE,
            )
        else:
            self.tool_failure(o)

    # --- chuyển hũ --------------------------------------------------------------------------
    async def on_move(self, r: IntentResult, question: str) -> None:
        p = r.params
        jars = await self.ensure_jars()
        if not jars.outcome.ok:
            self.tool_failure(jars.outcome)
            return
        src = resolve_jar(p.from_jar_text, self._jar_rows)
        dst = resolve_jar(p.to_jar_text, self._jar_rows)
        for label, text, match in (
            ("hũ nguồn", p.from_jar_text, src),
            ("hũ đích", p.to_jar_text, dst),
        ):
            if match.status != "ok":
                await self.ask_which_jar(label, text or "", match, question)
                return
        if src.code == dst.code:
            await self.ask_which_jar(
                "hai hũ khác nhau (hũ nguồn và hũ đích đang trùng)", "", JarMatch("none"), question
            )
            return
        assert p.amount_vnd is not None
        res = await self.call_tool_retry(
            "move_between_jars",
            {"from_jar": src.code, "to_jar": dst.code, "amount_vnd": p.amount_vnd},
            compact=lambda o: compact_confirm((o.payload or {})["data"]),
            block=confirm_block,
        )
        o = res.outcome
        if o.kind is ToolKind.NEEDS_CONFIRMATION and res.compact is not None:
            await self.write("confirm_move", question, res.compact)
        elif o.kind is ToolKind.OK:
            # Hợp đồng: không có confirm_token thì tool không được ghi. Kết quả OK nghĩa là lỗi nghiêm trọng.
            log.error(json.dumps({"event": "move_ok_without_token", "tool": o.name}))
            self.emit_notice(
                kind="error",
                code=ErrorCode.INTERNAL_ERROR.value,
                title=notices.DEFAULT_ERROR_TITLE,
                message=notices.GENERIC_ERROR_MESSAGE,
            )
        else:
            if o.code == ErrorCode.INSUFFICIENT_FUNDS.value:
                self.emit_jars_block()
            self.tool_failure(o)

    # --- ngoài phạm vi và xã giao -----------------------------------------------------------
    async def on_out_of_scope(self, r: IntentResult, question: str) -> None:
        """`notice` (giới hạn) + `suggestions` (việc làm được). Không có câu do model viết: lời từ chối là chuỗi sản phẩm, không thể lọt mã chứng khoán.

        Ngoại lệ: router xếp ngoài phạm vi nhưng vẫn trích được dấu hiệu chi tiêu của chính người dùng (số tiền, món, loại mua) và Guardrail
        KHÔNG chặn: có thể router hiểu nhầm (lỗi thật 23/11: "đi du lịch 5 triệu" sau chuỗi câu khác). Khi đó hỏi xác nhận một câu kèm chip
        thay vì từ chối cứng; câu ngoài phạm vi thật (cổ phiếu, vay, dữ liệu người khác) router không trích tham số chi tiêu nên vẫn bị từ chối.
        """
        if self.guardrail_reason is None and (req := spending_confirm_request(r)) is not None:
            await self.emit_clarify(req, r)
            return
        title, message = notices.OUT_OF_SCOPE
        self.emit_notice(kind="out_of_scope", code=None, title=title, message=message)
        self.emit_block(
            B.build_suggestions(
                context="out_of_scope",
                title=notices.SUGGESTIONS_TITLE,
                can_do=list(notices.CAN_DO),
                cannot_do=list(notices.CANNOT_DO),
                items=list(notices.SUGGESTION_ITEMS),
                trace_id=self.trace_id,
                source_tool="agent",
                as_of=self.d.now(),
                app_date=self.block_app_date(),
            )
        )

    async def on_chitchat(self, r: IntentResult, question: str) -> None:
        """Lời của router chỉ được phát khi mọi số trong đó có căn cứ (câu hỏi, lịch sử có dòng "Ứng dụng") và qua Guardrail."""
        if r.reply:
            ok = NumericGrounding.check(
                {"reply": r.reply}, Allowed.from_payloads([], [question, self.history])
            ).ok
            gr = await self.check_output(r.reply) if ok else None
            if ok and not (gr is not None and gr.blocked):
                await self.emit_fixed_text(r.reply)
                return
        await self.write("chitchat", question, {})

    # --- hỏi lại ----------------------------------------------------------------------------
    async def jar_chips(self) -> list[ClarifyChipIn]:
        """Chip là các hũ CÓ THẬT của người dùng (không có dữ liệu hũ thì không chip, không bịa)."""
        jars = await self.ensure_jars()
        if not jars.outcome.ok:
            return []
        rows = [j for j in self._jar_rows if j.get("name")]
        return [ClarifyChipIn(label=str(j["name"])[:40], value=f"Hũ {j['name']}"[:80]) for j in rows[:6]]

    async def unknown_jar_clarify(self, r: IntentResult) -> ClarifyRequest | None:
        """Tên hũ người dùng gõ mà không khớp hũ nào (hoặc khớp nhiều hũ): hỏi lại đúng một câu kèm chip hũ thật,
        thay vì lặng lẽ bỏ tên đó và đoán (F3). `move` và `lookup` đã có đường hỏi lại riêng (`ask_which_jar`)."""
        if r.intent not in ("affordability", "what_if"):
            return None
        p = r.params
        typed = [t for t in (p.jar_text, p.from_jar_text, p.to_jar_text) if t]
        if not typed:
            return None
        jars = await self.ensure_jars()
        if not jars.outcome.ok:
            return None  # lỗi đọc hũ: để tool lỗi báo đúng chỗ của nó
        bad = next((t for t in typed if resolve_jar(t, self._jar_rows).status != "ok"), None)
        if bad is None:
            return None
        name = bad.replace("?", " ").strip()[:40]
        question = notices.UNKNOWN_JAR_QUESTION.format(name=name) if name else notices.UNKNOWN_JAR_QUESTION_NO_NAME
        return ClarifyRequest(slot="jar", question=question, chips=await self.jar_chips())

    async def emit_clarify(self, req: ClarifyRequest, r: IntentResult) -> None:
        """Khối `clarify` đúng một câu hỏi kèm chip; kết thúc lượt (lượt sau người dùng trả lời, router ghép với câu trước)."""
        chips = [_readable_amount_chip(c) for c in req.chips]
        if req.slot == "jar" and not chips:
            chips = await self.jar_chips()  # hỏi hũ nào thì chip là các hũ thật
        self.emit_block(
            B.build_clarify(
                question=req.question,
                slot=req.slot,
                chips=[
                    {"id": f"c{i + 1}", "label": c.label, "value": c.value or c.label}
                    for i, c in enumerate(chips)
                ],
                trace_id=self.trace_id,
                source_tool="agent",
                as_of=self.d.now(),
                app_date=self.block_app_date(),
                pending_intent=r.intent if r.intent in _PENDING_INTENTS else None,
                allow_free_text=True,
            )
        )

    async def ask_which_jar(self, label: str, typed: str, match: JarMatch, question: str) -> None:
        """Không ánh xạ được tên hũ: hiện số dư các hũ thật của người dùng và hỏi lại."""
        self.emit_jars_block()
        names = {j["code"]: j["name"] for j in self._jar_rows}
        facts = {
            "van_de": f"Chưa xác định được {label}" + (f" từ chữ '{typed}'" if typed else ""),
            "cac_hu_hien_co": list(names.values()),
            "co_the_la": [names[c] for c in match.candidates if c in names],
        }
        await self.write("clarify", question, facts)


def _forecast_basis(payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """`ForecastBasis` từ kết quả `get_forecast` (cùng trường với khối what-if)."""
    d = (payload or {}).get("data")
    if not d:
        return None
    return {
        "confidence_band": d["confidence_band"],
        "is_initial_estimate": d["is_initial_estimate"],
        "history_days": d["history_days"],
        "coverage": d["coverage"],
        "stale": d["stale"],
    }


# --- mục tiêu người dùng nói khi lập lộ trình (chỉ handler roadmap dùng) -----------------------------
_GOAL_NO_JAR = "Bạn chưa nói mục tiêu này thuộc hũ nào nên mình lập lộ trình theo các mục tiêu đã khai ở hũ."
_GOAL_UNKNOWN_JAR = "Mình chưa tìm thấy hũ “{typed}” nên lập lộ trình theo các mục tiêu đã khai ở hũ."
_GOAL_NOT_SAVING = (
    "Hũ {name} không phải hũ tiết kiệm nên mình không đặt mục tiêu này cho hũ đó. "
    "Lộ trình bên dưới dùng các mục tiêu đã khai ở hũ tiết kiệm."
)
_GOAL_BAD_DATE = "Mình chưa đọc được hạn “{typed}” nên dùng hạn đã khai ở hũ {name}, nếu có."
_GOAL_NO_AMOUNT = "Hũ {name} chưa có số tiền mục tiêu nên mình chưa đặt hạn này. Bạn cho mình biết số tiền muốn gom nhé."


@dataclass(frozen=True)
class _RoadmapVersions:
    """Các phiên bản đọc trước khi lưu bản lập lại: bản đang dùng và bản đề xuất đang chờ (sẽ bị bỏ khi lưu bản mới)."""

    active_version: int | None = None
    pending_version: int | None = None
    pending_reason: str | None = None


def _roadmap_of(outcome: ToolOutcome) -> Roadmap | None:
    if not outcome.ok:
        return None
    try:
        return Roadmap.model_validate((outcome.payload or {}).get("data"))
    except ValueError:
        return None


def _user_goal_compact(goal: UserGoal, jar_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Mục tiêu người dùng nói, cho model viết câu trả lời (số và ngày đúng dạng để kiểm căn cứ)."""
    name = next((str(j["name"]) for j in jar_rows if j["code"] == goal.jar), goal.jar)
    out: dict[str, Any] = {"jar": name}
    if goal.target_vnd is not None:
        out["target_text"] = format_vnd(goal.target_vnd)
        out["target_short_text"] = format_vnd_short(goal.target_vnd)
    if goal.target_date is not None:
        when = date.fromisoformat(goal.target_date)
        out["target_date_text"] = f"{when.day:02d}/{when.month:02d}/{when.year}"
        out["target_day_month_text"] = f"{when.day:02d}/{when.month:02d}"
    return out


def _roadmap_closing(
    data: B.RoadmapData, active_version: int | None, goal: Mapping[str, Any] | None
) -> str:
    """Lời kết ngắn của lượt lập lộ trình, chỉ từ dữ liệu khối vừa lưu và phiên bản đang dùng đã đọc trước khi lưu: bản này là gì,
    bản nào đang dùng, khả năng kịp mục tiêu, bước tiếp theo của người dùng."""
    counts = {
        "version": data.version,
        "phases": len(data.phases),
        "steps": sum(len(phase.steps) for phase in data.phases),
    }
    parts: list[str] = []
    if data.status == "proposed":
        parts.append(notices.ROADMAP_CLOSING_PROPOSED.format(**counts))
        if active_version is not None:
            parts.append(notices.ROADMAP_CLOSING_IN_USE.format(active=active_version))
    elif data.status == "active":
        parts.append(notices.ROADMAP_CLOSING_ACTIVE.format(**counts))
    else:
        parts.append(notices.ROADMAP_CLOSING_OTHER.format(**counts))
    goal_text = None
    if goal is not None and goal.get("target_text"):
        goal_text = f"{goal['target_text']} cho hũ {goal['jar']}"
        if goal.get("target_date_text"):
            goal_text += f" trước {goal['target_date_text']}"
    goal_said = data.feasibility == "infeasible" and goal_text is not None
    if goal_said:
        parts.append(notices.ROADMAP_CLOSING_GOAL_INFEASIBLE.format(goal=goal_text))
    else:
        parts.append(notices.ROADMAP_CLOSING_FEASIBILITY[data.feasibility])
    if data.alternatives:
        parts.append(notices.ROADMAP_CLOSING_ALTERNATIVES.format(count=len(data.alternatives)))
    if goal_said:
        parts.append(notices.ROADMAP_CLOSING_GOAL_NOTE_SHORT)
    elif goal_text:
        parts.append(notices.ROADMAP_CLOSING_GOAL_NOTE.format(goal=goal_text))
    proposed_with_active = data.status == "proposed" and active_version is not None
    parts.append(
        notices.ROADMAP_CLOSING_NEXT_COMPARE if proposed_with_active else notices.ROADMAP_CLOSING_NEXT_REVIEW
    )
    return " ".join(parts)


# --- người dùng muốn sửa một bước của lộ trình (chỉ handler roadmap dùng) ------------------------------
#: câu nói về MỘT bước và có động từ sửa ("giảm số tiền ở bước ...", "sửa bước ..."), so trên chữ đã bỏ dấu. Câu có "lập" là lập
#: (lại) lộ trình, không phải sửa bước.
_STEP_WORD_RE = re.compile(r"\bbuoc\b")
_EDIT_VERB_RE = re.compile(r"\b(?:sua|chinh|doi|giam|tang|bot|xoa|bo)\b")
_CREATE_WORD_RE = re.compile(r"\blap\b")
_STEP_ORDINAL_RE = re.compile(r"\bbuoc (?:thu )?(\d{1,2})\b")
#: từ chỉ loại bước (chữ đã bỏ dấu) -> các `kind` khớp; chỉ dùng để thu hẹp khi nhiều bước cùng khớp hũ.
_STEP_KIND_WORDS: tuple[tuple[re.Pattern[str], frozenset[str]], ...] = (
    (re.compile(r"\b(?:de danh|danh|tiet kiem|chuyen)\b"), frozenset({"set_aside", "pay_obligation"})),
    (re.compile(r"\b(?:tra|nghia vu|den han)\b"), frozenset({"pay_obligation"})),
    (re.compile(r"\b(?:giam chi|cat giam|bot chi)\b"), frozenset({"cut_spending"})),
    (re.compile(r"\bty le\b"), frozenset({"adjust_split"})),
    (re.compile(r"\bnhac\b"), frozenset({"remind"})),
    (re.compile(r"\b(?:muc tieu|lui han)\b"), frozenset({"review_goal"})),
)


def _asks_step_edit(question: str) -> bool:
    text = normalize(question)
    return bool(
        _STEP_WORD_RE.search(text) and _EDIT_VERB_RE.search(text) and not _CREATE_WORD_RE.search(text)
    )


def _match_steps(
    roadmap: Roadmap, question: str, jar_names: Mapping[str, str]
) -> tuple[list[tuple[Any, Any]], list[str]]:
    """Các bước (giai đoạn, bước) khớp câu người dùng, bằng mã: số thứ tự "bước N", rồi hũ được nhắc (hũ nhận trước hũ nguồn), rồi
    loại bước để thu hẹp. Trả kèm mã các hũ được nhắc (để nói rõ khi không khớp)."""
    text = f" {normalize(question)} "
    steps = [(phase, step) for phase in roadmap.phases for step in phase.steps]
    if (ordinal := _STEP_ORDINAL_RE.search(text)) is not None:
        index = int(ordinal.group(1)) - 1
        return ([steps[index]] if 0 <= index < len(steps) else []), []
    mentioned = [
        code
        for code, name in jar_names.items()
        if (norm := normalize(name)) and len(norm) >= 3 and f" {norm} " in text
    ]
    kinds: set[str] = set()
    for pattern, matched in _STEP_KIND_WORDS:
        if pattern.search(text):
            kinds |= matched
    if mentioned:
        scored = [
            (2 if step.to_jar_code in mentioned else 1 if step.jar_code in mentioned else 0, phase, step)
            for phase, step in steps
        ]
        best = max(score for score, _, _ in scored)
        candidates = [(phase, step) for score, phase, step in scored if best and score == best]
    else:
        candidates = [(phase, step) for phase, step in steps if kinds and step.kind in kinds]
    narrowed = [(phase, step) for phase, step in candidates if step.kind in kinds]
    return (narrowed or candidates), mentioned


def _match_obligation(name: str, payload: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """Khoản nghĩa vụ ĐÃ KHAI cùng tên (so khớp không dấu); tránh tạo khoản trùng khi người dùng nói lại số tiền."""
    want = normalize(name)
    for o in ((payload or {}).get("data") or {}).get("obligations", []):
        if o.get("source") == "bnpl_auto" or o.get("status") not in (None, "active"):
            continue
        have = normalize(o["name"])
        if want and (want == have or want in have or have in want):
            return o
    return None


def _readable_amount_chip(chip: ClarifyChipIn) -> ClarifyChipIn:
    """Chip số tiền mà router để dạng số trần ("250000"): đổi nhãn và chữ gửi đi sang chữ người đọc được ("250 nghìn").

    Câu trả lời đó quay lại router như người dùng gõ; `parse_amount_vnd` đọc được cả hai dạng. Chip đã là chữ thì giữ nguyên.
    """

    def readable(text: str | None) -> str | None:
        if text is None or not text.strip().isdigit():
            return text
        amount = parse_amount_vnd(text)
        if not amount:
            return text
        short = format_vnd_short(amount)  # làm tròn một chữ số thập phân: chỉ dùng khi không đổi số tiền
        return short if parse_amount_vnd(short) == amount else format_vnd(amount)

    return ClarifyChipIn(label=readable(chip.label) or chip.label, value=readable(chip.value))


def _kind_question() -> ClarifyRequest:
    from yofina_agent.schemas import ClarifyChipIn

    c = notices.CLARIFY["obligation_kind"]
    return ClarifyRequest(
        slot="other",
        question=c["question"],
        chips=[ClarifyChipIn(label=x["label"], value=x["value"]) for x in c["chips"]],
    )


def spending_confirm_request(r: IntentResult) -> ClarifyRequest | None:
    """Câu hỏi xác nhận khi router xếp ngoài phạm vi mà vẫn trích được dấu hiệu chi tiêu (None nếu không có dấu hiệu đó).

    Dấu hiệu: số tiền, tên món hoặc loại kịch bản mua hàng. Câu ngoài phạm vi thật (cổ phiếu, vay, thời tiết...) router trả `params` rỗng
    (đo trên Nova 2 Lite 23/11), nên không vào đây. Nhãn dựng bằng mã từ tham số, không do model viết.
    """
    from yofina_agent.schemas import ClarifyChipIn

    p = r.params
    if r.intent != "out_of_scope":
        return None
    spending = p.amount_vnd is not None or (p.label or "").strip() or p.scenario_kind in (
        "one_time_purchase", "bnpl_purchase", "recurring_expense",
    )  # fmt: skip
    if not spending:
        return None
    what = " ".join(x for x in ((p.label or "").strip()[:40], format_vnd(p.amount_vnd) if p.amount_vnd else "") if x)
    question = (
        notices.CONFIRM_SPENDING_QUESTION.format(what=what) if what else notices.CONFIRM_SPENDING_QUESTION_NO_NAME
    )
    return ClarifyRequest(
        slot="other",
        question=question[:200],
        chips=[ClarifyChipIn(label=c["label"], value=c["value"]) for c in notices.CONFIRM_SPENDING_CHIPS],
    )


async def stream_turn(turn: Turn) -> AsyncIterator[BaseEvent]:
    """Chạy lượt hội thoại như một tác vụ nền và chuyển event ra ngay khi có (người gọi đã phát RUN_STARTED).

    Client ngắt kết nối (generator bị đóng) thì hủy tác vụ. Mọi đường đều kết thúc bằng `RUN_FINISHED`
    do `Turn.execute` phát; không có đường nào trả luồng rỗng.
    """
    task = asyncio.create_task(turn.execute())
    try:
        while True:
            item = await turn.queue.get()
            if item is _DONE:
                break
            yield item
    finally:
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
