"""Tiện ích cho test tích hợp của Gateway và Runtime (chỉ dùng trong tests/, không phải mã sản phẩm).

- `GatewayClient`: client MCP thật (gói `mcp`, streamable HTTP) với access token Cognito; trả kết quả tool đã
  giải JSON, hoặc `McpFailure` khi Gateway từ chối bằng lỗi giao thức (Cedar: -32002).
- `invoke_agent`: gọi Runtime thật qua HTTP (`.../runtimes/<ARN url-encode>/invocations?qualifier=DEFAULT`) với
  Bearer access token, session id và `traceparent`, đọc luồng SSE AG-UI.
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx


class McpFailure(Exception):
    """Lỗi giao thức JSON-RPC từ Gateway (ví dụ -32002 Tool Execution Denied)."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code, self.message = code, message


def _flatten(exc: BaseException):
    yield exc
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            yield from _flatten(sub)


def _unwrap(exc: BaseException) -> BaseException:
    from mcp.shared.exceptions import MCPError

    for e in _flatten(exc):
        if isinstance(e, MCPError):
            return McpFailure(e.code, e.message)
    return exc


@dataclass
class ToolReply:
    is_error: bool
    text: str
    data: Any = None  # JSON của text khi parse được

    @property
    def status(self) -> str | None:
        return self.data.get("status") if isinstance(self.data, dict) else None


class GatewayClient:
    def __init__(self, url: str, token: str) -> None:
        self.url, self.token = url, token

    async def _session(self, fn):
        import httpx2
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with (
            httpx2.AsyncClient(
                headers={"Authorization": f"Bearer {self.token}"}, timeout=60.0
            ) as client,
            streamable_http_client(self.url, http_client=client) as streams,
            ClientSession(streams[0], streams[1]) as session,
        ):
            await session.initialize()
            return await fn(session)

    def _run(self, fn):
        try:
            return asyncio.run(self._session(fn))
        except BaseException as exc:
            raise _unwrap(exc) from None

    def tool_names(self) -> list[str]:
        async def fn(s):
            return [t.name for t in (await s.list_tools()).tools]

        return self._run(fn)

    def tools(self) -> list[Any]:
        async def fn(s):
            return (await s.list_tools()).tools

        return self._run(fn)

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> ToolReply:
        async def fn(s):
            res = await s.call_tool(name, arguments or {})
            text = "".join(getattr(c, "text", "") for c in res.content)
            try:
                data = json.loads(text)
            except ValueError:
                data = None
            is_error = getattr(res, "is_error", None)
            if is_error is None:
                is_error = getattr(res, "isError", False)
            return ToolReply(bool(is_error), text, data)

        return self._run(fn)


def raw_gateway_post(url: str, token: str | None, body: dict[str, Any]) -> httpx.Response:
    """POST JSON-RPC thô (để thấy HTTP status khi token sai)."""
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.post(url, headers=headers, json=body, timeout=60)


# --- Runtime ------------------------------------------------------------------------------------
SESSION_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"


def new_session_id() -> str:
    return str(uuid.uuid4())  # 36 ký tự, thỏa yêu cầu 33 đến 256


def new_traceparent() -> tuple[str, str]:
    trace_id = uuid.uuid4().hex
    return trace_id, f"00-{trace_id}-{uuid.uuid4().hex[:16]}-01"


@dataclass
class AgentRun:
    status: int
    events: list[dict[str, Any]] = field(default_factory=list)
    t_first_event: float | None = None
    total: float = 0.0
    raw: str = ""
    trace_id: str = ""
    session_id: str = ""
    response_headers: dict[str, str] = field(default_factory=dict)

    @property
    def types(self) -> list[str]:
        return [e.get("type", "?") for e in self.events]

    @property
    def text(self) -> str:
        return "".join(
            e.get("delta", "") for e in self.events if e.get("type") == "TEXT_MESSAGE_CONTENT"
        )

    @property
    def blocks(self) -> list[dict[str, Any]]:
        return [e["content"] for e in self.events if e.get("type") == "ACTIVITY_SNAPSHOT"]

    def blocks_of(self, block_type: str) -> list[dict[str, Any]]:
        return [b for b in self.blocks if b.get("type") == block_type]

    @property
    def finished(self) -> dict[str, Any] | None:
        done = [e for e in self.events if e.get("type") == "RUN_FINISHED"]
        return done[-1] if done else None


def runtime_url(arn: str) -> str:
    return (
        "https://bedrock-agentcore.ap-southeast-1.amazonaws.com/runtimes/"
        f"{urllib.parse.quote(arn, safe='')}/invocations?qualifier=DEFAULT"
    )


def invoke_agent(
    url: str,
    token: str | None,
    text: str | None,
    *,
    session_id: str | None = None,
    messages: list[dict[str, Any]] | None = None,
    forwarded_props: dict[str, Any] | None = None,
    thread_id: str | None = None,
    timeout: float = 120.0,
    extra_headers: dict[str, str] | None = None,
    client: httpx.Client | None = None,
) -> AgentRun:
    """Một lượt AG-UI qua Runtime. `messages` đầy đủ lịch sử nếu cần; mặc định một tin nhắn người dùng."""
    sid = session_id or new_session_id()
    trace_id, traceparent = new_traceparent()
    msgs = (
        messages
        if messages is not None
        else [{"id": f"m-{uuid.uuid4().hex[:8]}", "role": "user", "content": text}]
    )
    body = {
        "threadId": thread_id or sid,
        "runId": f"r-{uuid.uuid4().hex[:8]}",
        "state": {},
        "messages": msgs,
        "tools": [],
        "context": [],
        "forwardedProps": forwarded_props or {},
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        SESSION_HEADER: sid,
        "traceparent": traceparent,
        **(extra_headers or {}),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    run = AgentRun(status=0, trace_id=trace_id, session_id=sid)
    t0 = time.perf_counter()
    c = client or httpx.Client(timeout=timeout)
    try:
        with c.stream("POST", url, headers=headers, json=body) as r:
            run.status = r.status_code
            run.response_headers = {k.lower(): v for k, v in r.headers.items()}
            buf = ""
            for chunk in r.iter_text():
                buf += chunk
                while "\n\n" in buf:
                    frame, buf = buf.split("\n\n", 1)
                    for line in frame.split("\n"):
                        if line.startswith("data:"):
                            try:
                                ev = json.loads(line[5:])
                            except ValueError:
                                ev = {"type": "UNPARSEABLE", "raw": line[5:200]}
                            ev["_t"] = round(time.perf_counter() - t0, 3)
                            run.events.append(ev)
                            if run.t_first_event is None:
                                run.t_first_event = ev["_t"]
            run.raw = buf[:500]
    finally:
        if client is None:
            c.close()
    run.total = round(time.perf_counter() - t0, 3)
    return run
