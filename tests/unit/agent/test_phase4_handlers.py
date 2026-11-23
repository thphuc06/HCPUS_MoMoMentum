"""Các handler đọc phase 4 qua Gateway giả và fixture hợp đồng."""

from __future__ import annotations

import json
from typing import get_args

import pytest
from agent_helpers import (
    REPO,
    FakeRecords,
    FakeTools,
    FakeWriter,
    blocks_of,
    check_agui_order,
    fixture,
    make_llm,
    mcp_ok,
    route_response,
    run_turn,
    types,
)
from yofina_agent import notices
from yofina_agent.schemas import Intent, IntentParams
from yofina_agent.tools import classify_result
from yofina_agent.turn import Turn
from yofina_agent.writer import build_writer_prompt
from yofina_core.errors import ErrorCode
from yofina_core.resilience import load_shock_set


def gateway(tool_name, payload):
    return FakeTools({tool_name: classify_result(tool_name, mcp_ok(payload))})


def with_shock_id(monkeypatch, shock_id):
    # C3 mới thêm trường này vào schema của router.
    monkeypatch.setattr(IntentParams, "shock_id", property(lambda self: shock_id), raising=False)


@pytest.mark.parametrize(
    "intent, tool, target, block_fixture",
    [
        ("resilience", "get_resilience_score", "forecast", "resilience_score.minh"),
        ("stress", "stress_test", "forecast", "stress_result.mat_viec"),
        ("roadmap", "get_roadmap", "planner", "roadmap.active_edited"),
    ],
)
@pytest.mark.parametrize("llm_down", [False, True])
def test_phase4_success(monkeypatch, intent, tool, target, block_fixture, llm_down):
    payload = fixture(f"{tool}.ok.json")
    data = payload["data"]
    args = {}
    if intent == "stress":
        args = {"shock_id": data["shock"]["shock_id"]}
        with_shock_id(monkeypatch, args["shock_id"])
    elif intent == "roadmap":
        args = {"which": "latest"}

    if llm_down:
        classify = Turn.classify_guarded

        async def classify_then_lose_llm(self, question, history):
            routed = await classify(self, question, history)
            self.llm_down = True
            return routed

        monkeypatch.setattr(Turn, "classify_guarded", classify_then_lose_llm)

    events, tools, writer = run_turn(
        "Cho mình xem kết quả",
        llm=make_llm([route_response(intent=intent)]),
        tools=gateway(tool, payload),
        monkeypatch=monkeypatch,
    )
    check_agui_order(events)
    expected = json.loads(
        (REPO / "contracts" / "fixtures" / "blocks" / "valid" / f"{block_fixture}.json").read_text(encoding="utf-8")
    )
    assert blocks_of(events)[0] == expected
    assert tools.calls == [(tool, args)]
    assert [e.tool_call_name for e in events if e.type.value == "TOOL_CALL_START"] == [f"{target}___{tool}"]
    assert types(events).index("ACTIVITY_SNAPSHOT") < types(events).index("TOOL_CALL_RESULT")

    compact = json.loads(next(e.content for e in events if e.type.value == "TOOL_CALL_RESULT"))
    if intent == "resilience":
        weakest = next(c for c in data["components"] if c["key"] == data["weakest"])
        assert compact == {
            "score": data["score"],
            "band": data["band"],
            "weakest": {"label": weakest["label"], "explanation": weakest["explanation"]},
        }
        assert any(b["data"].get("degraded_reason") == "low_coverage" for b in blocks_of(events)[1:])
    elif intent == "stress":
        assert compact["shock_label"] == data["shock"]["label"]
        for key in ("score_before", "score_after", "runway_days_total", "runway_days_emergency", "shortfall_vnd"):
            assert compact[key] == data[key]
        assert compact["shortfall_text"] == "8.890.000 ₫"
    else:
        assert compact == {
            "version": data["version"],
            "reason": data["reason"]["text"],
            "feasibility": data["feasibility"],
            "counts": data["counts"],
            "step_titles": [step["title"] for step in data["phases"][0]["steps"]],
        }

    if llm_down:
        assert not writer.calls and "TEXT_MESSAGE_START" not in types(events)
    else:
        assert [(call["task"], call["compact"]) for call in writer.calls] == [(intent, compact)]
        assert types(events).index("TOOL_CALL_RESULT") < types(events).index("TEXT_MESSAGE_START")
        prompt = build_writer_prompt(intent, writer.calls[0]["question"], compact)
        assert "Không" in prompt and "đầu tư hay vay tiền" in prompt
        if intent != "roadmap":
            assert "không phải điểm tín dụng" in prompt


@pytest.mark.parametrize("shock_id", [None, "unknown_shock"])
def test_stress_clarify_uses_config(monkeypatch, shock_id):
    routed = route_response(intent="stress")
    if shock_id is not None:
        with_shock_id(monkeypatch, shock_id)
        routed = route_response(
            intent="stress", clarify={"slot": "other", "question": "Router muốn hỏi gì?", "chips": []}
        )
    events, tools, writer = run_turn("Thử cú sốc", llm=make_llm([routed]), monkeypatch=monkeypatch)
    check_agui_order(events)
    (block,) = blocks_of(events)
    assert block["type"] == "clarify"
    assert block["data"]["slot"] == "other"
    assert block["data"]["question"] == notices.STRESS_QUESTION
    assert block["data"]["question"].count("?") == 1
    assert [(chip["label"], chip["value"]) for chip in block["data"]["chips"]] == [
        (shock.label, f"Thử cú sốc {shock.label}") for shock in load_shock_set().shocks
    ]
    assert not tools.calls and not writer.calls


@pytest.mark.parametrize(
    "intent, tool, error_fixture",
    [
        ("resilience", "get_resilience_score", "get_resilience_score.error_profile_incomplete.json"),
        ("stress", "stress_test", "stress_test.error_shock_not_found.json"),
        ("roadmap", "get_roadmap", "get_roadmap.error_not_found.json"),
    ],
)
def test_phase4_tool_error(monkeypatch, intent, tool, error_fixture):
    if intent == "stress":
        with_shock_id(monkeypatch, load_shock_set().shocks[0].shock_id)
    payload = fixture(error_fixture)
    events, tools, writer = run_turn(
        "Cho mình xem kết quả",
        llm=make_llm([route_response(intent=intent)]),
        tools=gateway(tool, payload),
        monkeypatch=monkeypatch,
    )
    check_agui_order(events)
    (notice,) = blocks_of(events)
    assert notice["type"] == "notice" and notice["data"]["kind"] == "error"
    assert notice["data"]["code"] == payload["code"]
    if intent == "roadmap":
        assert (notice["data"]["title"], notice["data"]["message"]) == notices.ROADMAP_MISSING
    else:
        assert notice["data"]["message"] == payload["message"]
    assert len(tools.calls) == 1 and not writer.calls


def test_resilience_basis_without_coverage_is_accepted(monkeypatch):
    payload = fixture("get_resilience_score.ok.json")
    basis = payload["data"]["basis"]
    del basis["coverage"]
    records = FakeRecords()
    events, _, writer = run_turn(
        "Điểm chống chịu của mình",
        llm=make_llm([route_response(intent="resilience")]),
        tools=gateway("get_resilience_score", payload),
        monkeypatch=monkeypatch,
        records=records,
    )
    assert [b["type"] for b in blocks_of(events)] == ["resilience_score"]
    assert len(writer.calls) == 1
    assert records.saved[0]["confidence"]["band"] == basis["confidence_band"]


def test_resilience_malformed_basis_fails_block_contract(monkeypatch):
    payload = fixture("get_resilience_score.ok.json")
    payload["data"]["basis"] = {"coverage": "không hợp lệ"}
    events, _, writer = run_turn(
        "Điểm chống chịu của mình",
        llm=make_llm([route_response(intent="resilience")]),
        tools=gateway("get_resilience_score", payload),
        monkeypatch=monkeypatch,
    )
    (notice,) = blocks_of(events)
    assert notice["type"] == "notice" and notice["data"]["kind"] == "error"
    assert notice["data"]["code"] == ErrorCode.INTERNAL_ERROR
    assert not writer.calls


@pytest.mark.parametrize("text, grounded", [("Điểm chống chịu 58.", True), ("Điểm chống chịu 99.", False)])
def test_phase4_writer_verifies_numbers_before_emitting(monkeypatch, text, grounded):
    events, _, _ = run_turn(
        "Điểm chống chịu của mình",
        llm=make_llm([route_response(intent="resilience")]),
        tools=gateway("get_resilience_score", fixture("get_resilience_score.ok.json")),
        writer=FakeWriter(text),
        monkeypatch=monkeypatch,
    )
    assert blocks_of(events)[0]["type"] == "resilience_score"
    assert ("TEXT_MESSAGE_CONTENT" in types(events)) == grounded


def test_handlers_cover_every_intent():
    assert set(Turn._intent_handlers(object.__new__(Turn))) == set(get_args(Intent))
