"""Hỗ trợ test của agent. Mọi đối tượng giả (client Bedrock, bộ đếm, tool, writer) chỉ sống ở đây."""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from ag_ui.core import RunAgentInput
from yofina_agent import events as ev
from yofina_agent.identity import Identity
from yofina_agent.settings import AgentSettings
from yofina_agent.store import UnconfiguredTurnBlockStore
from yofina_agent.tools import ToolOutcome, classify_result
from yofina_agent.turn import Turn, TurnDeps, drain_background, stream_turn

from yofina_core.config import Config
from yofina_core.llm import BudgetCapReached, LlmGateway, LlmSettings, ModelSpec

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "contracts" / "fixtures" / "tools"
PREFIX = "ledger___"


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def make_jwt(sub: str = "user-a", **claims: Any) -> str:
    def seg(obj: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{seg({'alg': 'none'})}.{seg({'sub': sub, **claims})}.sig"


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def mcp_ok(payload: dict[str, Any]) -> dict[str, Any]:
    """Dáng kết quả `MCPClient.call_tool_async` khi Lambda trả JSON (Gateway bọc thành text)."""
    return {"status": "success", "toolUseId": "t", "content": [{"text": json.dumps(payload)}]}


class FakeTools:
    """Thay `GatewayTools`: trả kết quả theo từng tool (qua `classify_result` thật), ghi lại các lần gọi."""

    def __init__(self, results: dict[str, Any] | None = None) -> None:
        base = {
            "get_jar_balances": lambda args: classify_result(
                "x", mcp_ok(fixture("get_jar_balances.ok.json"))
            ),
            "query_transactions": lambda args: classify_result(
                "x", mcp_ok(fixture("query_transactions.ok.json"))
            ),
            "move_between_jars": lambda args: classify_result(
                "x", mcp_ok(fixture("move_between_jars.needs_confirmation.json"))
            ),
            "get_forecast": lambda args: classify_result(
                "x", mcp_ok(fixture("get_forecast.ok.json"))
            ),
            # phase 3
            "get_obligations": lambda args: classify_result("x", mcp_ok(fixture("get_obligations.ok.json"))),
            "get_fee_schedule": lambda args: classify_result("x", mcp_ok(fixture("get_fee_schedule.ok.json"))),
            "run_scenario": lambda args: classify_result("x", mcp_ok(fixture("run_scenario.ok_bnpl.json"))),
            # cuộc trò chuyện chưa có kịch bản nào (test gộp tự đặt kết quả riêng)
            "list_scenarios": lambda args: classify_result(
                "x", mcp_ok({"status": "OK", "as_of": "2026-11-21T02:00:00Z", "app_date": "2026-11-21", "data": {"scenarios": []}})
            ),
            "check_suitability": lambda args: classify_result("x", mcp_ok(fixture("check_suitability.ok.json"))),
            # phase 6 (luồng K): what-if khoản chi đọc thói quen chi tiêu để cá nhân hóa kết luận
            "get_behavior_profile": lambda args: classify_result("x", mcp_ok(fixture("get_behavior_profile.ok.json"))),
            "affordability_check": lambda args: classify_result("x", mcp_ok(fixture("affordability_check.ok.json"))),
            "update_profile": lambda args: classify_result("x", mcp_ok(fixture("update_profile.needs_confirmation.json"))),
            "schedule_nudge": lambda args: classify_result("x", mcp_ok(fixture("schedule_nudge.needs_confirmation.json"))),
        }
        self.results = {**base, **(results or {})}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        short = name.split("___", 1)[-1]  # `ledger___x` hoặc `forecast___x`
        self.calls.append((short, dict(arguments)))
        res = self.results[short]
        outcome = res(arguments) if callable(res) else res
        outcome.name, outcome.args = name, dict(arguments)
        return outcome

    async def aclose(self) -> None:
        self.closed = True


class FakeBedrock:
    """Client Bedrock giả: mỗi phần tử của `script` là phản hồi hoặc ngoại lệ."""

    def __init__(self, script: list[Any]) -> None:
        self.script, self.calls = list(script), []

    def converse(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(kw)
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class FakeUsage:
    def __init__(self, caps_hit: set[str] | None = None) -> None:
        self.caps_hit, self.calls = caps_hit or set(), []

    def consume(self, *, day: str, model: str, cap: int, ttl_epoch: int) -> int:
        self.calls.append(model)
        if model in self.caps_hit:
            raise BudgetCapReached(model)
        return len(self.calls)


_LEGACY_INTENT = {
    "balance_lookup": ("lookup", "balance"),
    "transactions_lookup": ("lookup", "transactions"),
    "forecast_lookup": ("lookup", "forecast"),
    "move_between_jars": ("move", None),
}
_PARAM_KEYS = (
    "jar_text", "from_jar_text", "to_jar_text", "amount_vnd", "days_back", "limit", "funding", "scenario_kind",
    "label", "date_text", "salary_vnd", "payday_day", "obligation_name", "obligation_kind", "due_day", "keep_previous",
    "shock_id", "roadmap_action", "insight_kind", "fee_topic", "ingest_action", "currency", "amount_original", "tx_type",
    "spend_jar_code", "memory_action", "answers_pending", "date_spec",
)  # fmt: skip


#: Lần đọc ví ở đầu mỗi lượt có router gọi model (danh sách hũ cho router chọn hũ chi theo ý định, #39): tool call đầu tiên của lượt,
#: phần sau của lượt dùng lại kết quả này.
JARS_READ = ("get_jar_balances", {})
JARS_READ_TOOL = PREFIX + "get_jar_balances"


def route_response(**fields: Any) -> dict[str, Any]:
    """Phản hồi của router giả. Nhận cả tên ý định cũ của phase 1 và 2 (`balance_lookup`...) và đổi sang `IntentResult` của phase 3."""
    intent = fields.pop("intent")
    lookup_kind = fields.pop("lookup_kind", None)
    if intent in _LEGACY_INTENT:
        intent, lk = _LEGACY_INTENT[intent]
        lookup_kind = lookup_kind or lk
    clarify = fields.pop("clarify", None)
    reply = fields.pop("reply", None)
    confidence = fields.pop("confidence", 0.9)
    needs = fields.pop("needs_clarification", clarify is not None)
    params = {k: fields.pop(k) for k in _PARAM_KEYS if k in fields}
    if lookup_kind:
        params["lookup_kind"] = lookup_kind
    if fields:
        raise AssertionError(f"trường lạ cho route_response: {sorted(fields)}")
    out: dict[str, Any] = {"intent": intent, "params": params, "confidence": confidence, "needs_clarification": needs}
    if clarify is not None:
        out["clarify"] = clarify
    if reply is not None:
        out["reply"] = reply
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"toolUse": {"toolUseId": "r1", "name": "route", "input": out}}],
            }
        },
        "usage": {"inputTokens": 100, "outputTokens": 20},
        "stopReason": "tool_use",
    }


def tool_response(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Phản hồi giả của model khi bị ép gọi tool `name` với `payload` (planner, Analyst...)."""
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"toolUse": {"toolUseId": f"t-{name}", "name": name, "input": payload}}],
            }
        },
        "usage": {"inputTokens": 300, "outputTokens": 80},
        "stopReason": "tool_use",
    }


def make_llm(
    script: list[Any], usage: FakeUsage | None = None, rpm: int = 0
) -> tuple[LlmGateway, FakeBedrock, FakeUsage]:
    client, usage = FakeBedrock(script), usage or FakeUsage()
    settings = LlmSettings(
        roles={
            "small": (
                ModelSpec("m-small-a", rpm=rpm, daily_cap=100),
                ModelSpec("m-small-b", rpm=rpm, daily_cap=100),
            ),
            "planner": (ModelSpec("m-plan", rpm=rpm, daily_cap=100),),
        }
    )
    gw = LlmGateway(
        settings, config=Config({"YOFINA_REGION": "ap-southeast-1"}), client=client, usage=usage
    )
    return gw, client, usage


def agent_settings(**over: Any) -> AgentSettings:
    base = AgentSettings.load({"YOFINA_GATEWAY_URL": "http://gateway.invalid/mcp"})
    return AgentSettings(**{**base.__dict__, **over})


def run_input(
    text: str | None = "xin chào",
    *,
    messages: list[dict[str, Any]] | None = None,
    context: list[dict[str, str]] | None = None,
    **extra: Any,
) -> RunAgentInput:
    msgs = (
        messages
        if messages is not None
        else ([{"id": "m1", "role": "user", "content": text}] if text else [])
    )
    return RunAgentInput.model_validate(
        {
            "threadId": "thread-1",
            "runId": "run-1",
            "state": {},
            "messages": msgs,
            "tools": [],
            "context": context or [],
            "forwardedProps": extra.get("forwarded_props", {}),
        }
    )


class FakeWriter:
    """Thay `write_stream`: ghi lại (task, compact) và stream đoạn chữ cho trước hoặc ném lỗi."""

    def __init__(
        self, text: str | list[str] = "Đã xong.", error: BaseException | None = None
    ) -> None:
        self.chunks = [text] if isinstance(text, str) else text
        self.error, self.calls = error, []

    def __call__(self, gateway: LlmGateway, **kw: Any) -> AsyncIterator[str]:
        self.calls.append(kw)

        async def gen() -> AsyncIterator[str]:
            for i, c in enumerate(self.chunks):
                yield c
                if self.error and i == 0:
                    raise self.error
            if self.error and not self.chunks:
                raise self.error

        return gen()


async def collect(turn: Turn) -> list[Any]:
    # RUN_STARTED do lớp gọi (app.py) phát trước khi nạp cấu hình; test mô phỏng đúng như vậy
    events = [ev.run_started(turn.run_input), *[e async for e in stream_turn(turn)]]
    await drain_background()  # ghi lượt chạy nền sau RUN_FINISHED (#11): chờ xong để test đọc được
    return events


def run_turn(
    text: str | None,
    *,
    llm: tuple[LlmGateway, Any, Any] | None = None,
    tools: FakeTools | None = None,
    monkeypatch: pytest.MonkeyPatch | None = None,
    writer: FakeWriter | None = None,
    settings: AgentSettings | None = None,
    messages: list[dict[str, Any]] | None = None,
    store: Any = None,
    guardrail: Any = None,
    records: Any = None,
    context: list[dict[str, str]] | None = None,
) -> tuple[list[Any], FakeTools, FakeWriter]:
    tools = tools or FakeTools()
    writer = writer or FakeWriter()
    if monkeypatch is not None:
        monkeypatch.setattr("yofina_agent.turn.write_stream", writer)
    gateway = llm[0] if llm else make_llm([])[0]
    deps = TurnDeps(
        settings=settings or agent_settings(),
        llm=lambda: gateway,
        store=store or UnconfiguredTurnBlockStore(),
        tools_factory=lambda identity: tools,  # type: ignore[arg-type,return-value]
        guardrail=guardrail,
        **({"records": records} if records is not None else {}),
    )
    turn = Turn(
        deps,
        run_input(text, messages=messages, context=context),
        Identity("user-a", make_jwt("user-a")),
        trace_id="8f3a21c94b7e4d0aa1c25e6f7b8c9d01",
        conversation_id="session-1",
    )
    return run(collect(turn)), tools, writer


def types(events: list[Any]) -> list[str]:
    return [e.type.value for e in events]


def blocks_of(events: list[Any]) -> list[dict[str, Any]]:
    return [e.content for e in events if e.type.value == "ACTIVITY_SNAPSHOT"]


def check_agui_order(events: list[Any]) -> None:
    """Kiểm quy tắc thứ tự mà `@ag-ui/client` áp dụng cho các event ta phát."""
    t = types(events)
    assert t, "luồng rỗng"
    assert t[0] == "RUN_STARTED"
    assert t[-1] in {"RUN_FINISHED", "RUN_ERROR"}
    assert sum(x in {"RUN_FINISHED", "RUN_ERROR"} for x in t) == 1
    open_msg: str | None = None
    open_tools: dict[str, str] = {}
    ended_tools: set[str] = set()
    for e in events[1:-1]:
        k = e.type.value
        if k == "TEXT_MESSAGE_START":
            assert open_msg is None and not open_tools, "tin nhắn chữ lồng nhau"
            open_msg = e.message_id
        elif k == "TEXT_MESSAGE_CONTENT":
            assert open_msg == e.message_id
        elif k == "TEXT_MESSAGE_END":
            assert open_msg == e.message_id
            open_msg = None
        elif k == "TOOL_CALL_START":
            assert open_msg is None, "tool call khi tin nhắn chữ đang mở"
            open_tools[e.tool_call_id] = e.tool_call_name
        elif k == "TOOL_CALL_ARGS":
            assert e.tool_call_id in open_tools
        elif k == "TOOL_CALL_END":
            assert e.tool_call_id in open_tools
            ended_tools.add(e.tool_call_id)
        elif k == "TOOL_CALL_RESULT":
            assert e.tool_call_id in ended_tools
            open_tools.pop(e.tool_call_id)
            json.loads(e.content)  # nội dung là chuỗi JSON
    assert open_msg is None and not open_tools, "còn tin nhắn/tool call chưa đóng"


class FakeRecords:
    """Thay `TurnRecordStore`: ghi lại các bản ghi lượt."""

    def __init__(self) -> None:
        self.saved: list[dict[str, Any]] = []

    async def save(self, *, tools: Any, record: dict[str, Any]) -> bool:
        self.saved.append(record)
        return True


class FakeGuardrailClient:
    """Client bedrock-runtime giả cho `ApplyGuardrail`: chặn khi văn bản chứa một trong `block_words`."""

    def __init__(self, block_words: tuple[str, ...] = (), error: BaseException | None = None) -> None:
        self.block_words, self.error, self.calls = block_words, error, []

    def apply_guardrail(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(kw)
        if self.error:
            raise self.error
        text = kw["content"][0]["text"]["text"].lower()
        if any(w in text for w in self.block_words):
            return {
                "action": "GUARDRAIL_INTERVENED",
                "assessments": [{"topicPolicy": {"topics": [{"name": "specific-investment-advice", "type": "DENY", "action": "BLOCKED"}]}}],
            }
        return {"action": "NONE", "assessments": []}


def make_guardrail(client: Any, **over: Any) -> Any:
    from yofina_agent.guardrail import Guardrail

    st = agent_settings(guardrail_enabled=True, guardrail_id="gr-test", guardrail_version="1", **over)
    return Guardrail(st, region="ap-southeast-1", client=client)
