"""Entrypoint ASGI theo hợp đồng AgentCore Runtime giao thức AG-UI: `POST /invocations` (SSE) và `GET /ping`.

- Danh tính: `sub` lấy từ header `Authorization` (JWT đã được Runtime xác minh; xem `identity`). **Không** nhận
  `user_id` từ payload; token được chuyển nguyên cho Gateway.
- `trace_id`: từ header `traceparent` (client sinh; Runtime giữ nguyên trace-id). Conversation id: session id của
  Runtime (`X-Amzn-Bedrock-AgentCore-Runtime-Session-Id`), nếu thiếu thì `threadId`.
- Làm nóng: `forwardedProps.warmup = true` -> chỉ nạp cấu hình và tạo client, **không gọi model, không gọi tool**.
- CORS do dịch vụ AgentCore xử lý (spike Runtime §3); app không thêm `CORSMiddleware` (vô tác dụng).
- Request sai (thiếu/sai token, JSON hỏng) trả lỗi HTTP có thân JSON `{"error": {code, message}}`; từ lúc luồng SSE
  đã mở, mọi lỗi đều thành khối `notice` + `RUN_FINISHED`, không bao giờ luồng rỗng.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from ag_ui.core import BaseEvent, RunAgentInput
from ag_ui.encoder import EventEncoder
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from yofina_agent import events as ev
from yofina_agent.identity import Identity, Unauthenticated, identity_from_authorization
from yofina_agent.guardrail import Guardrail
from yofina_agent.settings import AgentSettings
from yofina_agent.store import TurnBlockStore, TurnRecordStore, make_record_store, make_store
from yofina_agent.tools import GatewayTools
from yofina_agent.turn import Turn, TurnDeps, background_busy, stream_turn
from yofina_core.blocks import new_trace_id, trace_id_from_traceparent
from yofina_core.config import Config, ConfigError
from yofina_core.errors import ErrorCode
from yofina_core.llm import LlmGateway, get_gateway

log = logging.getLogger("yofina.agent.app")

SESSION_HEADER = "x-amzn-bedrock-agentcore-runtime-session-id"


class AgentRuntime:
    """Giữ cấu hình và các thành phần dùng chung của tiến trình; mọi thứ tạo lười (nhẹ lúc import)."""

    def __init__(
        self,
        settings: AgentSettings | None = None,
        *,
        llm: Callable[[], LlmGateway] = get_gateway,
        store: TurnBlockStore | None = None,
        tools_factory: Callable[[Identity], GatewayTools] | None = None,
        guardrail: Guardrail | None = None,
        records: TurnRecordStore | None = None,
    ) -> None:
        self._settings = settings
        self._llm, self._store, self._tools_factory = llm, store, tools_factory
        self._guardrail, self._records = guardrail, records

    @property
    def settings(self) -> AgentSettings:
        if self._settings is None:
            self._settings = AgentSettings.load()
        return self._settings

    def deps(self) -> TurnDeps:
        s = self.settings
        if self._store is None:
            self._store = make_store(s.turn_blocks_tool)
        factory = self._tools_factory or (
            lambda identity: GatewayTools(
                s.gateway_url,
                identity,
                call_timeout=s.tool_timeout_seconds,
                startup_timeout=s.tool_startup_timeout_seconds,
            )
        )
        if self._records is None:
            self._records = make_record_store(s.turn_record_tool)
        if self._guardrail is None:
            try:
                region = Config().region()
            except ConfigError:
                region = ""  # không có Region thì Guardrail không dùng được; model cũng không gọi được nên lỗi sẽ hiện ở chỗ đó
            self._guardrail = Guardrail(s, region=region)
        return TurnDeps(
            settings=s,
            llm=self._llm,
            store=self._store,
            tools_factory=factory,
            guardrail=self._guardrail,
            records=self._records,
        )

    def warm(self) -> dict[str, Any]:
        """Nạp cấu hình, tạo client Bedrock/DynamoDB, import Strands. Không gọi model hay tool."""
        started = time.perf_counter()
        gateway = self._llm()
        _ = gateway.client, gateway.usage
        import strands
        import strands.tools.mcp  # noqa: F401

        deps = self.deps()
        if deps.guardrail is not None and deps.guardrail.enabled:
            _ = deps.guardrail.client  # tạo client bedrock-runtime trước (không gọi ApplyGuardrail)
        return {"warm": True, "guardrail": bool(deps.guardrail and deps.guardrail.enabled), "ms": int((time.perf_counter() - started) * 1000)}


def _error(status: int, code: ErrorCode, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"error": {"code": code.value, "message": message}}
    )


def create_app(runtime: AgentRuntime | None = None) -> FastAPI:
    rt = runtime or AgentRuntime()
    app = FastAPI(title="Yofina agent", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/ping")
    async def ping() -> dict[str, Any]:
        # HealthyBusy khi còn ghi lượt/bộ nhớ nền sau RUN_FINISHED: Runtime giữ phiên tới khi ghi xong (#11).
        # Không gửi `time_of_last_update`: giờ tăng ở mỗi ping làm phiên không bao giờ hết idle (runtime-long-run.html).
        return {"status": "HealthyBusy" if background_busy() else "Healthy"}

    @app.post("/invocations")
    async def invocations(request: Request) -> Any:
        try:
            identity = identity_from_authorization(request.headers.get("authorization"))
        except Unauthenticated as exc:
            return _error(401, ErrorCode.UNAUTHENTICATED, str(exc))
        try:
            run_input = RunAgentInput.model_validate(await request.json())
        except (ValueError, ValidationError) as exc:
            return _error(
                422, ErrorCode.PARAMS_INVALID, f"Payload AG-UI không hợp lệ: {str(exc)[:200]}"
            )

        encoder = EventEncoder(accept=request.headers.get("accept"))
        trace_id = trace_id_from_traceparent(request.headers.get("traceparent")) or new_trace_id()
        conversation_id = request.headers.get(SESSION_HEADER) or run_input.thread_id
        props = run_input.forwarded_props if isinstance(run_input.forwarded_props, dict) else {}

        async def events() -> AsyncIterator[BaseEvent]:
            finished = False
            started = False
            try:
                # RUN_STARTED đi trước mọi thứ nặng (nạp cấu hình/SSM, tạo client): event đầu tới nhanh ở phiên lạnh.
                yield ev.run_started(run_input)
                started = True
                if props.get("warmup"):
                    info = await asyncio.to_thread(rt.warm)
                    yield ev.run_finished(run_input, result=info, usage=[])
                    finished = True
                    return
                deps = await asyncio.to_thread(rt.deps)
                turn = Turn(
                    deps, run_input, identity, trace_id=trace_id, conversation_id=conversation_id
                )
                async for event in stream_turn(turn):
                    yield event
                    finished = event.type.value in {"RUN_FINISHED", "RUN_ERROR"}
            except Exception as exc:
                log.exception("lỗi trước/giữa luồng")
                if not started:
                    yield ev.run_started(run_input)
                if not finished:
                    yield ev.run_error(
                        f"Lỗi hệ thống: {type(exc).__name__}", ErrorCode.INTERNAL_ERROR.value
                    )

        async def sse() -> AsyncIterator[str]:
            async for event in events():
                yield encoder.encode(event)

        log.info(
            json.dumps(
                {
                    "event": "invocation",
                    "trace_id": trace_id,
                    "session_id": conversation_id,
                    "thread_id": run_input.thread_id,
                    "warmup": bool(props.get("warmup")),
                    "messages": len(run_input.messages),
                }
            )
        )
        return StreamingResponse(
            sse(),
            media_type=encoder.get_content_type(),
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()
