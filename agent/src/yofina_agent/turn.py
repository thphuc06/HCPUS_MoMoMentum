"""Một lượt hội thoại: mã điều khiển thứ tự + tự phát event AG-UI ("Cách B" của docs/research/strands-agui.md).

Vì sao không dùng `StrandsAgent` của `ag-ui-strands` (Cách A): router, đường nhanh một tool, khối UI, đường suy
giảm và `turn_blocks` đều nằm *ngoài* vòng lặp của một Agent, và cần giữ đúng thứ tự event (khối UI trước
`TOOL_CALL_RESULT`, luôn kết thúc bằng `RUN_FINISHED`, không bao giờ luồng rỗng). Strands vẫn được dùng cho
`MCPClient` (tool), `Agent` viết câu trả lời, và `Model` đo đếm (`MeteredModel`).

Luồng (mã điều khiển, không để LLM quyết định thứ tự):

    RUN_STARTED
      -> router (model nhỏ, JSON ép tool) | nếu không gọi được: bộ phân loại dự phòng bằng luật
      -> ý định:
           balance_lookup      get_jar_balances  -> khối jar_summary -> câu trả lời ngắn
           transactions_lookup get_jar_balances (ánh xạ tên hũ) + query_transactions -> câu trả lời ngắn
           move_between_jars   get_jar_balances (ánh xạ tên hũ) + move_between_jars KHÔNG token
                               -> NEEDS_CONFIRMATION -> khối confirm -> câu nhắc xác nhận
           out_of_scope        khối notice + câu nói rõ giới hạn
           chitchat            câu trả lời ngắn
      -> khối notice (nếu suy giảm) -> lưu turn_blocks -> RUN_FINISHED

Agent không bao giờ điền cờ xác nhận hay token; đường ghi thật do frontend gọi REST (ADR-0002).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ag_ui.core import BaseEvent, RunAgentInput

from yofina_agent import events as ev
from yofina_agent import notices
from yofina_agent.compact import compact_confirm, compact_jars, compact_transactions
from yofina_agent.fallback import classify_by_rules
from yofina_agent.identity import Identity
from yofina_agent.jars import JarMatch, resolve_jar
from yofina_agent.router import RouterOutput, route
from yofina_agent.settings import AgentSettings
from yofina_agent.store import TurnBlockStore
from yofina_agent.tools import (
    ContractMismatch,
    GatewayTools,
    ToolKind,
    ToolOutcome,
    confirm_block,
    jar_summary_block,
)
from yofina_agent.writer import check_grounding, write_stream
from yofina_core import blocks as B
from yofina_core.clock import app_timezone
from yofina_core.errors import ErrorCode
from yofina_core.llm import AllModelsFailed, LlmGateway, ModelBudgetExceeded, TurnScope

log = logging.getLogger("yofina.agent.turn")

_DONE = object()


@dataclass
class TurnDeps:
    """Thứ lượt hội thoại cần; test thay `tools_factory`/`llm`/`store`, mã sản phẩm dùng giá trị thật."""

    settings: AgentSettings
    llm: Callable[[], LlmGateway]  # tạo lười: đọc cấu hình/SSM sau khi đã phát RUN_STARTED
    store: TurnBlockStore
    tools_factory: Callable[[Identity], GatewayTools]
    now: Callable[[], datetime] = lambda: datetime.now(UTC)


@dataclass
class CallResult:
    outcome: ToolOutcome
    compact: dict[str, Any] | None
    block: B.JarSummaryBlock | B.ConfirmBlock | None


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

    # --- phát event -------------------------------------------------------------------------
    def emit(self, event: BaseEvent) -> None:
        self.queue.put_nowait(event)

    def emit_block(self, block: B.JarSummaryBlock | B.ConfirmBlock | B.NoticeBlock) -> None:
        wire = B.block_to_wire(block)
        self.blocks[wire["id"]] = wire
        self.emit(ev.block_snapshot(wire))

    def emit_notice(
        self, *, kind: B.NoticeKind, code: str | None, title: str, message: str
    ) -> None:
        self.emit_block(
            B.build_notice(
                kind=kind,
                title=title,
                message=message,
                trace_id=self.trace_id,
                source_tool="agent",
                as_of=self.d.now(),
                app_date=self.app_date or datetime.now(app_timezone()).date(),
                code=code,
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
            self.emit_notice(kind="degraded", code=self.degrade_code, title=title, message=message)
            self.degrade_noticed = True

    def tool_failure(self, outcome: ToolOutcome) -> None:
        """Lỗi tool -> khối `notice` (kind `error`), dùng đúng thông điệp an toàn của tool."""
        code = outcome.code or ErrorCode.INTERNAL_ERROR.value
        self.emit_notice(
            kind="error",
            code=code,
            title=notices.ERROR_TITLES.get(code, notices.DEFAULT_ERROR_TITLE),
            message=outcome.message or notices.GENERIC_ERROR_MESSAGE,
        )

    # --- gọi tool ---------------------------------------------------------------------------
    async def call_tool(
        self,
        short_name: str,
        args: dict[str, Any],
        *,
        compact: Callable[[ToolOutcome], dict[str, Any]] | None = None,
        block: Callable[[ToolOutcome, str], Any] | None = None,
    ) -> CallResult:
        """TOOL_CALL_START/ARGS/END -> gọi Gateway -> [ACTIVITY_SNAPSHOT khối] -> TOOL_CALL_RESULT bản gọn.

        Khối UI phát **trước** `TOOL_CALL_RESULT`; model chỉ thấy bản gọn.
        """
        name = self.s.tool(short_name)
        tcid = ev.new_id("tc-")
        self.emit(ev.tool_call_start(tcid, name))
        if args:
            self.emit(ev.tool_call_args(tcid, args))
        self.emit(ev.tool_call_end(tcid))

        self.tool_calls += 1
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
                if (
                    not finished
                ):  # bị hủy/hết giờ/lỗi bất ngờ giữa chừng: vẫn đóng tool call cho hợp lệ
                    interrupted = {
                        "status": "ERROR",
                        "code": ErrorCode.INTERNAL_ERROR.value,
                        "message": notices.GENERIC_ERROR_MESSAGE,
                    }
                    self.emit(ev.tool_call_result(tcid, interrupted))

        built_block = None
        compact_view: dict[str, Any] | None = None
        if outcome.ok:
            try:
                if block is not None:
                    built_block = block(outcome, self.trace_id)
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
                built_block = compact_view = None
        if outcome.payload and isinstance(outcome.payload.get("app_date"), str):
            with contextlib.suppress(ValueError):
                self.app_date = date.fromisoformat(outcome.payload["app_date"])
        if built_block is not None:
            self.emit_block(built_block)
        if outcome.ok:
            result_view = (
                compact_view if compact_view is not None else {"status": outcome.payload["status"]}
            )
        else:
            result_view = {"status": "ERROR", "code": outcome.code, "message": outcome.message}
        self.emit(ev.tool_call_result(tcid, result_view))
        return CallResult(outcome, compact_view, built_block)

    async def ensure_jars(self) -> CallResult:
        """Danh sách hũ của chính người dùng (để ánh xạ tên hũ và lấy ngày mô phỏng); gọi một lần mỗi lượt."""
        if self._jars is None:
            self._jars = await self.call_tool(
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
                        "degraded": self.degrade_code is not None,
                        "model_calls": self.scope.calls,
                        "tool_calls": self.tool_calls,
                    },
                    usage=self.scope.usage_by_model(),
                )
            )
            self.queue.put_nowait(_DONE)

    async def persist(self) -> None:
        """Lưu lượt (kể cả lượt suy giảm hoặc chỉ có chữ). Lỗi lưu không làm hỏng lượt."""
        assistant_text = "\n\n".join(self.assistant_parts)
        if not (self.blocks or self.user_text or assistant_text):
            return
        try:
            await asyncio.wait_for(
                self.d.store.save(
                    tools=self.tools,
                    conversation_id=self.conversation_id,
                    trace_id=self.trace_id,
                    blocks=list(self.blocks.values()),
                    user_text=self.user_text,
                    assistant_text=assistant_text,
                ),
                timeout=self.s.turn_blocks_timeout_seconds,
            )
        except Exception as exc:
            log.warning(json.dumps({"event": "turn_blocks_error", "error": repr(exc)[:200]}))

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
        question, index = found
        self.user_text = question
        history = ev.format_history(
            self.run_input,
            before_index=index,
            max_messages=self.s.history_messages,
            max_chars=self.s.history_chars_per_message,
        )

        await self.ensure_llm()
        routed = await self.classify(question, history)
        if routed is None:
            return
        self.intent = routed.intent
        handler = {
            "balance_lookup": self.on_balance,
            "transactions_lookup": self.on_transactions,
            "move_between_jars": self.on_move,
            "out_of_scope": self.on_out_of_scope,
            "chitchat": self.on_chitchat,
        }[routed.intent]
        await handler(routed, question)

    async def classify(self, question: str, history: str) -> RouterOutput | None:
        """Router bằng LLM; không gọi được thì bộ phân loại dự phòng bằng luật (suy giảm có kiểm soát)."""
        if not self.llm_down:
            try:
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

    # --- các ý định -------------------------------------------------------------------------
    async def on_balance(self, r: RouterOutput, question: str) -> None:
        res = await self.call_tool(
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

    async def on_transactions(self, r: RouterOutput, question: str) -> None:
        jars = await self.ensure_jars()
        if not jars.outcome.ok:
            self.tool_failure(jars.outcome)
            return
        args: dict[str, Any] = {}
        want = r.jar_text or (
            question if self.llm_down else None
        )  # suy giảm: dò tên hũ trong cả câu
        if want:
            match = resolve_jar(want, self._jar_rows)
            if match.status == "ok":
                args["jar"] = match.code
            elif r.jar_text:
                await self.ask_which_jar("hũ cần tra giao dịch", r.jar_text, match, question)
                return
        limit = r.limit if r.limit and r.limit > 0 else self.s.transactions_default_limit
        args["limit"] = min(limit, self.s.transactions_max_limit)
        if r.days_back and r.days_back > 0 and self.app_date:
            args["to_date"] = self.app_date.isoformat()
            args["from_date"] = (self.app_date - timedelta(days=r.days_back)).isoformat()
        names = {j["code"]: j["name"] for j in self._jar_rows}
        res = await self.call_tool(
            "query_transactions",
            args,
            compact=lambda o: compact_transactions(o.payload or {}, names, args["limit"]),
        )
        if not res.outcome.ok:
            self.tool_failure(res.outcome)
            return
        assert res.compact is not None
        await self.write("transactions", question, res.compact)

    async def on_move(self, r: RouterOutput, question: str) -> None:
        missing = not (r.from_jar_text and r.to_jar_text and r.amount_vnd and r.amount_vnd > 0)
        if r.needs_clarification or missing:
            await self.ask_move_details(r, question)
            return
        jars = await self.ensure_jars()
        if not jars.outcome.ok:
            self.tool_failure(jars.outcome)
            return
        src = resolve_jar(r.from_jar_text, self._jar_rows)
        dst = resolve_jar(r.to_jar_text, self._jar_rows)
        for label, text, match in (
            ("hũ nguồn", r.from_jar_text, src),
            ("hũ đích", r.to_jar_text, dst),
        ):
            if match.status != "ok":
                await self.ask_which_jar(label, text or "", match, question)
                return
        if src.code == dst.code:
            await self.ask_which_jar(
                "hai hũ khác nhau (hũ nguồn và hũ đích đang trùng)", "", JarMatch("none"), question
            )
            return
        assert r.amount_vnd is not None
        res = await self.call_tool(
            "move_between_jars",
            {"from_jar": src.code, "to_jar": dst.code, "amount_vnd": r.amount_vnd},
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

    async def on_out_of_scope(self, r: RouterOutput, question: str) -> None:
        title, message = notices.OUT_OF_SCOPE
        self.emit_notice(kind="out_of_scope", code=None, title=title, message=message)
        if r.reply:
            await self.emit_fixed_text(r.reply)
        else:
            await self.write("out_of_scope", question, {})

    async def on_chitchat(self, r: RouterOutput, question: str) -> None:
        if r.reply:
            await self.emit_fixed_text(r.reply)
        else:
            await self.write("chitchat", question, {})

    # --- hỏi lại ----------------------------------------------------------------------------
    async def ask_move_details(self, r: RouterOutput, question: str) -> None:
        await self.emit_fixed_text(r.reply or notices.ASK_MOVE_DETAILS)

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
