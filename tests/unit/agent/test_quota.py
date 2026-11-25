"""Trần lượt chat theo tài khoản mỗi ngày (#13, B4): chạm trần thì lượt kết thúc bằng một `notice`, không gọi model hay tool."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agent_helpers import (
    FakeTools,
    FakeWriter,
    agent_settings,
    blocks_of,
    collect,
    make_jwt,
    make_llm,
    route_response,
    run,
    run_input,
)

from yofina_agent.identity import Identity
from yofina_agent.store import UnconfiguredTurnBlockStore
from yofina_agent.turn import Turn, TurnDeps
from yofina_core.llm import BudgetCapReached
from yofina_core.quota import AccountQuota

NOW = datetime(2026, 12, 3, 3, 0, tzinfo=UTC)  # 10:00 giờ Việt Nam


class CountingUsage:
    """Bộ đếm giả cùng giao kèo với `DynamoUsageStore.consume` (tăng nguyên tử, đủ trần thì ném)."""

    def __init__(self) -> None:
        self.counts: dict[tuple[str, str], int] = {}

    def consume(self, *, day: str, model: str, cap: int, ttl_epoch: int) -> int:
        n = self.counts.get((day, model), 0)
        if n >= cap:
            raise BudgetCapReached(model)
        self.counts[(day, model)] = n + 1
        return n + 1


def chat_turn(quota: AccountQuota, monkeypatch: Any, *, sub: str = "user-a", routed: bool = True):
    llm = make_llm([route_response(intent="balance_lookup")] if routed else [])
    tools = FakeTools()
    monkeypatch.setattr("yofina_agent.turn.write_stream", FakeWriter("Tổng 7.730.000 ₫."))
    deps = TurnDeps(
        settings=agent_settings(),
        llm=lambda: llm[0],
        store=UnconfiguredTurnBlockStore(),
        tools_factory=lambda identity: tools,  # type: ignore[arg-type,return-value]
        quota=quota,
    )
    turn = Turn(
        deps,
        run_input("Hũ ăn uống còn bao nhiêu?"),
        Identity(sub, make_jwt(sub)),
        trace_id="8f3a21c94b7e4d0aa1c25e6f7b8c9d01",
        conversation_id="session-1",
    )
    return run(collect(turn)), tools, llm[1]


def notices_of(events: list[Any]) -> list[dict[str, Any]]:
    return [b for b in blocks_of(events) if b["type"] == "notice"]


def test_tran_2_thi_luot_thu_ba_nhan_thong_bao_va_khong_goi_model_hay_tool(monkeypatch):
    quota = AccountQuota("chat", store=CountingUsage(), cap=2, now=lambda: NOW)
    for _ in range(2):
        events, tools, _ = chat_turn(quota, monkeypatch)
        assert notices_of(events) == [] and tools.calls

    events, tools, bedrock = chat_turn(quota, monkeypatch, routed=False)
    [notice] = notices_of(events)
    data = notice["data"]
    assert data["code"] == "DAILY_QUOTA_EXCEEDED"
    assert "2 lượt" in data["message"] and "vẫn xem" in data["message"]
    assert tools.calls == [] and bedrock.calls == []
    assert events[-1].type.value == "RUN_FINISHED"
