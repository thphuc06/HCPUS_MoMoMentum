"""Lập lộ trình từ output có cấu trúc và fixture Gateway của Phase 4."""

from __future__ import annotations

import asyncio
import json

import pytest
from agent_helpers import (
    FakeRecords,
    FakeTools,
    agent_settings,
    blocks_of,
    check_agui_order,
    fixture,
    make_llm,
    mcp_ok,
    route_response,
    run,
    run_turn,
    tool_response,
    types,
)
from yofina_agent import notices
from yofina_agent.roadmap_agent import build_roadmap
from yofina_agent.tools import ToolKind, ToolOutcome, classify_result

from yofina_core.errors import ErrorCode
from yofina_core.llm import TurnScope
from yofina_core.params import normalize_params


def step(step_id="bu_du_phong", **changes):
    return {
        "step_id": step_id,
        "title": "Bù hũ dự phòng",
        "kind": "set_aside",
        "reason": "Tăng khoản dự phòng từ phần có thể chuyển",
        "jar_code": "giai_tri",
        "to_jar_code": "du_phong",
        "amount_ref": {"jar_code": "du_phong", "field": "proposed_increase"},
        "action": "move_between_jars",
        **changes,
    }


def review(**changes):
    return {
        "step_id": "giu_muc_tieu",
        "kind": "review_goal",
        "title": "Xem lại mục tiêu",
        "reason": "Theo dõi khả năng giữ mục tiêu",
        "jar_code": "du_lich",
        **changes,
    }


def outline(*steps):
    return {"phases": [{"phase_id": "on_dinh", "title": "Ổn định ngân sách", "steps": list(steps)}]}


def scripted_tools(
    *, allocation="ok", checks=("ok",), saves=("ok",), latest=("error_not_found",), **other
):
    def respond(name, values):
        remaining = iter(values)

        def result(_args):
            value = next(remaining)
            payload = fixture(f"{name}.{value}.json") if isinstance(value, str) else value
            return classify_result(name, mcp_ok(payload))

        return result

    return FakeTools(
        {
            "get_resilience_score": respond("get_resilience_score", ("ok",)),
            "get_roadmap": respond("get_roadmap", latest),
            "optimize_allocation": respond("optimize_allocation", (allocation,)),
            "check_suitability": respond("check_suitability", checks),
            "save_roadmap": respond("save_roadmap", saves),
            **other,
        }
    )


def build(tools, *outputs, settings=None, scope=None, stages=None, **kwargs):
    script = [
        output if isinstance(output, Exception) else tool_response("draft_roadmap", output)
        for output in outputs
    ]
    llm, client, _ = make_llm(script)
    settings = settings or agent_settings()
    scope = scope or TurnScope(settings.max_model_calls_per_turn)

    async def call(name, args, target):
        return await tools.call(settings.tool(name, target=target), args)

    result = run(
        build_roadmap(
            call,
            llm,
            settings,
            scope,
            reason_code=kwargs.pop("reason_code", "initial"),
            on_stage=(lambda stage, progress: stages.append((stage, progress)))
            if stages is not None
            else None,
            **kwargs,
        )
    )
    return result, client, scope


def args_for(tools, tool_name):
    return [args for name, args in tools.calls if name == tool_name]


def prompt(client, index=0):
    return json.loads(client.calls[index]["messages"][0]["content"][0]["text"])


def test_save_grounded_roadmap_and_report_stages():
    tools, stages = scripted_tools(checks=("ok", "ok")), []
    draft = outline(step())
    draft["phases"].extend(
        [
            {
                "phase_id": "theo_doi",
                "title": "Theo dõi",
                "steps": [review(action="schedule_nudge")],
            },
            {"phase_id": "du_thua", "title": "Theo dõi thêm", "steps": [review(step_id="du_thua")]},
        ]
    )
    draft["horizon_months"] = 6
    draft["goals"] = [{"jar": "du_lich", "weight": 2}, {"jar": "khong_co", "weight": 3}]
    result, client, scope = build(tools, draft, stages=stages)
    assert result.outcome.payload == fixture("save_roadmap.ok.json")
    assert len(result.suitability) == 2
    assert scope.calls == 1
    assert [stage for stage, _ in stages] == ["context", "draft", "allocate", "suitability", "save"]
    assert [progress for _, progress in stages] == sorted({progress for _, progress in stages})
    assert args_for(tools, "optimize_allocation") == [
        {"horizon_months": 6, "goals": [{"jar": "du_lich", "weight": 2}]}
    ]
    assert args_for(tools, "get_roadmap") == [{"which": "latest"}]
    (stored,) = args_for(tools, "save_roadmap")
    assert stored["reason_code"] == "initial" and "based_on_version" not in stored
    assert stored["feasibility"] == "on_track"
    data = fixture("optimize_allocation.ok.json")["data"]
    assert stored["goals"] == data["goals"]
    assert stored["alternatives"] == data["alternatives"]
    first, second = stored["phases"]
    assert first["start_date"] == data["period_start"]
    assert first["end_date"] == second["start_date"]
    assert second["end_date"] == "2027-03-21"  # horizon trả về là bốn tháng
    move, nudge = first["steps"][0], second["steps"][0]
    line = next(line for line in data["lines"] if line["jar"]["code"] == "du_phong")
    expected = line["proposed_monthly_vnd"] - line["current_monthly_vnd"]
    assert move["amount_vnd"] == expected
    assert move["ai_generated"]
    assert move["action"] == {
        "tool": "move_between_jars",
        "params": {"from_jar": "giai_tri", "to_jar": "du_phong", "amount_vnd": expected},
    }
    assert nudge["action"]["params"]["fire_on"] == nudge["due_date"] == second["end_date"]
    for item in (move, nudge):
        action = item["action"]
        assert action["params"] == normalize_params(action["tool"], action["params"])
        assert {"user_id", "confirm_token"}.isdisjoint(action["params"])
    proposals = [args["proposal"] for args in args_for(tools, "check_suitability")]
    assert [proposal["kind"] for proposal in proposals] == ["move_between_jars", "remind_later"]
    assert [proposal.get("amount_vnd") for proposal in proposals] == [expected, None]
    assert all(proposal["origin"] == "recommendation" for proposal in proposals)
    assert "weakest" in prompt(client)["context"]


@pytest.mark.parametrize(
    ("fixture_name", "feasibility", "alternatives"),
    [
        ("ok_relaxed", "relaxed", 0),
        ("ok_infeasible", "infeasible", 2),
    ],
)
def test_save_relaxed_and_infeasible(fixture_name, feasibility, alternatives):
    tools = scripted_tools(allocation=fixture_name)
    result, _, _ = build(tools, outline(review()))
    assert result.outcome.ok
    (stored,) = args_for(tools, "save_roadmap")
    data = fixture(f"optimize_allocation.{fixture_name}.json")["data"]
    assert stored["feasibility"] == feasibility
    assert stored["goals"] == data["goals"]
    assert stored["alternatives"] == data["alternatives"]
    assert len(stored["alternatives"]) == alternatives


def test_suitability_feedback_repairs_amount_reference():
    tools = scripted_tools(checks=("violation", "ok"))
    fixed = step(amount_ref={"jar_code": "giai_tri", "field": "proposed_decrease"})
    result, client, scope = build(tools, outline(step()), outline(fixed))
    assert result.outcome.ok
    assert scope.calls == 2
    (feedback,) = prompt(client, 1)["feedback"]
    violation = fixture("check_suitability.violation.json")["data"]["violations"][0]
    assert feedback == {
        "step_id": "bu_du_phong",
        "rule_id": violation["rule_id"],
        "message": violation["message"],
    }
    assert args_for(tools, "save_roadmap")[0]["phases"][0]["steps"][0]["checked_rules"]
    assert len(args_for(tools, "optimize_allocation")) == 1


@pytest.mark.parametrize("keep_step", [True, False])
def test_drop_blocked_steps_after_both_repairs(keep_step):
    draft = outline(step())
    if keep_step:
        draft["phases"].append({"phase_id": "theo_doi", "title": "Theo dõi", "steps": [review()]})
    tools = scripted_tools(checks=("violation",) * 3)
    result, _, scope = build(tools, draft, draft, draft)
    assert scope.calls == 3
    saves = args_for(tools, "save_roadmap")
    if keep_step:
        assert result.outcome.ok
        assert [phase["phase_id"] for phase in saves[0]["phases"]] == ["theo_doi"]
        assert [item["step_id"] for item in saves[0]["phases"][0]["steps"]] == ["giu_muc_tieu"]
    else:
        assert not saves and result.outcome is None


@pytest.mark.parametrize(
    "text", ["Dành 917.123 ₫", "Dành tiền trong 17 ngày", "Xem lại vào 18/01/2099"]
)
def test_ungrounded_text_triggers_repair(text):
    tools = scripted_tools()
    result, client, _ = build(tools, outline(step(reason=text)), outline(step()))
    assert result.outcome.ok
    assert prompt(client, 1)["feedback"][0]["rule_id"] == "numeric_grounding"
    assert len(args_for(tools, "check_suitability")) == 1


def test_accepts_formatted_amount_from_allocation():
    tools = scripted_tools()
    result, _, scope = build(tools, outline(step(reason="Mức đề xuất là 1.800.000 ₫ mỗi tháng")))
    assert result.outcome.ok
    assert scope.calls == 1


@pytest.mark.parametrize("exhausted", [True, False])
def test_draft_model_failure_or_no_budget_does_not_save(exhausted):
    tools = scripted_tools()
    scope = TurnScope(0 if exhausted else 1)
    result, _, _ = build(tools, RuntimeError("planner unavailable"), scope=scope)
    assert result.outcome is None and result.model_budget_exhausted == exhausted
    assert (result.model_error is not None) == (not exhausted)
    assert not args_for(tools, "optimize_allocation") and not args_for(tools, "save_roadmap")


def test_model_budget_limits_repairs_and_preserves_valid_steps():
    tools = scripted_tools(checks=("violation",))
    result, _, scope = build(tools, outline(step(), review()), scope=TurnScope(1))
    assert result.outcome.ok and scope.calls == 1
    (stored,) = args_for(tools, "save_roadmap")
    assert [item["step_id"] for item in stored["phases"][0]["steps"]] == ["giu_muc_tieu"]


def test_optional_context_can_fail_and_balances_are_required():
    unavailable = ToolOutcome("optional", ToolKind.UNAVAILABLE)
    tools = scripted_tools(
        latest=({"status": "ERROR", "code": "INTERNAL_ERROR"},), get_resilience_score=unavailable
    )
    result, client, _ = build(tools, outline(review()))
    assert result.outcome.ok
    assert {"weakest", "previous_feedback"}.isdisjoint(prompt(client)["context"])
    tools = scripted_tools(get_jar_balances=unavailable)
    result, client, _ = build(tools)
    assert result.outcome is unavailable
    assert not client.calls


def test_parallel_context_and_pii_filtered_before_model():
    jars = fixture("get_jar_balances.ok.json")
    jars["data"]["jars"][0]["name"] = "Nguyễn Văn An"
    obligations = fixture("get_obligations.ok.json")
    obligations["data"]["obligations"][0]["name"] = "Liên hệ người nhận"
    tools = scripted_tools(
        get_jar_balances=classify_result("get_jar_balances", mcp_ok(jars)),
        get_obligations=classify_result("get_obligations", mcp_ok(obligations)),
    )
    llm, client, _ = make_llm([tool_response("draft_roadmap", outline(review()))])
    settings = agent_settings()
    context_calls = {
        ("get_jar_balances", "ledger"),
        ("get_obligations", "ledger"),
        ("get_resilience_score", "forecast"),
        ("get_roadmap", "planner"),
    }

    async def exercise():
        ready = asyncio.Event()
        seen = set()

        async def call(name, args, target):
            if (name, target) in context_calls:
                seen.add((name, target))
                if seen == context_calls:
                    ready.set()
                await asyncio.wait_for(ready.wait(), timeout=1)
            return await tools.call(settings.tool(name, target=target), args)

        return await build_roadmap(call, llm, settings, TurnScope(1), reason_code="initial")

    assert run(exercise()).outcome.ok
    data = json.dumps(prompt(client), ensure_ascii=False)
    assert "Nguyễn Văn An" not in data
    assert "Liên hệ người nhận" not in data
    assert obligations["data"]["obligations"][0]["id"] not in data


def test_model_cannot_send_money_as_a_structured_field():
    tools = scripted_tools()
    result, _, _ = build(tools, outline(step(amount_vnd=123456)))
    assert result.outcome is None and result.model_error is not None
    assert not args_for(tools, "optimize_allocation") and not args_for(tools, "save_roadmap")


def test_split_advice_does_not_overwrite_existing_jar_configuration():
    tools = scripted_tools()
    split = review(kind="adjust_split")
    result, client, _ = build(tools, outline({**split, "action": "save_jars"}), outline(split))
    assert result.outcome.ok
    assert "save_jars" in prompt(client, 1)["feedback"][0]["message"]
    assert "action" not in args_for(tools, "save_roadmap")[0]["phases"][0]["steps"][0]


def test_optimization_error_stops_before_save():
    tools = scripted_tools(allocation="error_profile_incomplete")
    result, _, _ = build(tools, outline(review()))
    assert result.outcome.code == ErrorCode.PROFILE_INCOMPLETE
    assert not args_for(tools, "save_roadmap")


def test_save_invalid_uses_same_repair_budget():
    tools = scripted_tools(saves=("error_invalid", "ok"))
    result, client, scope = build(
        tools, outline(review()), outline(review(title="Rà soát mục tiêu"))
    )
    assert result.outcome.ok and scope.calls == 2
    (feedback,) = prompt(client, 1)["feedback"]
    assert feedback["rule_id"] == "roadmap_invalid"
    assert feedback["message"] == fixture("save_roadmap.error_invalid.json")["message"]
    assert len(args_for(tools, "save_roadmap")) == 2


def test_save_invalid_with_no_model_budget_returns_tool_error():
    tools = scripted_tools(saves=("error_invalid",))
    result, _, _ = build(tools, outline(review()), scope=TurnScope(1))
    assert result.outcome.code == ErrorCode.ROADMAP_INVALID
    assert len(args_for(tools, "save_roadmap")) == 1


@pytest.mark.parametrize("race_result", ["ok", "error_version_conflict"])
def test_conflict_refreshes_latest_and_saves_once(race_result):
    newer = fixture("save_roadmap.ok.json")
    tools = scripted_tools(latest=("ok", newer), saves=("error_version_conflict", race_result))
    flag_id = newer["data"]["reason"]["behavior_flag_id"]
    result, client, scope = build(
        tools, outline(review()), reason_code="behavior_changed", behavior_flag_id=flag_id
    )
    assert result.outcome.ok == (race_result == "ok")
    assert args_for(tools, "get_roadmap") == [{"which": "latest"}] * 2
    original, updated = args_for(tools, "save_roadmap")
    assert original["based_on_version"] == fixture("get_roadmap.ok.json")["data"]["version"]
    assert updated == {**original, "based_on_version": newer["data"]["version"]}
    assert updated["behavior_flag_id"] == flag_id and scope.calls == 1
    feedback = prompt(client)["context"]["previous_feedback"]
    assert feedback["version"] == original["based_on_version"]
    assert [item["step_id"] for item in feedback["rejected_steps"]] == ["cat_giai_tri"]
    assert flag_id not in json.dumps(prompt(client))


def test_initial_conflict_returns_other_turns_saved_version():
    tools = scripted_tools(
        latest=("error_not_found", "ok"),
        saves=("error_version_conflict",),
    )
    result, _, _ = build(tools, outline(review()))
    assert result.outcome.payload == fixture("get_roadmap.ok.json")
    assert len(args_for(tools, "get_roadmap")) == 2
    assert len(args_for(tools, "save_roadmap")) == 1


def test_tool_budget_includes_every_round_save_and_conflict_attempt():
    settings = agent_settings()
    draft = outline(step(), step("giu_tien"), step("khong_du_ngan_sach"))
    tools = scripted_tools(
        checks=("ok",) * 6,
        saves=("error_invalid", "error_invalid", "error_version_conflict", "ok"),
        latest=("ok", "ok"),
    )
    result, client, scope = build(
        tools, draft, draft, draft, settings=settings, reason_code="user_request"
    )
    assert result.outcome.ok and scope.calls == 3
    assert prompt(client)["max_steps"] == settings.roadmap_max_steps
    assert len(tools.calls) == settings.max_tool_calls_per_turn == 16
    assert len(args_for(tools, "check_suitability")) == 6
    assert all(
        len(payload["phases"][0]["steps"]) == 2 for payload in args_for(tools, "save_roadmap")
    )


def test_turn_missing_roadmap_generates_emits_and_records(monkeypatch):
    tools, records = scripted_tools(), FakeRecords()
    llm = make_llm(
        [
            route_response(intent="roadmap"),
            tool_response("draft_roadmap", outline(step())),
        ]
    )
    settings = agent_settings()
    events, _, writer = run_turn(
        "Cho mình xem lộ trình",
        llm=llm,
        tools=tools,
        records=records,
        settings=settings,
        monkeypatch=monkeypatch,
    )
    check_agui_order(events)
    (block,) = blocks_of(events)
    assert block["type"] == "roadmap"
    assert block["data"] == fixture("save_roadmap.ok.json")["data"]
    assert args_for(tools, "get_roadmap") == [{"which": "latest"}]
    assert args_for(tools, "save_roadmap")[0]["reason_code"] == "initial"
    assert writer.calls[0]["task"] == "roadmap"
    assert types(events).index("ACTIVITY_SNAPSHOT") < types(events).index("TEXT_MESSAGE_START")
    (record,) = records.saved
    assert record["token_usage"]["model_calls"] == 2 <= settings.max_model_calls_per_turn
    assert any(rule["rule_id"] == "obligations_first" for rule in record["rules_checked"])
    assert [
        timing["step"] for timing in record["step_timings"] if timing["step"].startswith("roadmap_")
    ] == [
        "roadmap_context",
        "roadmap_draft",
        "roadmap_allocate",
        "roadmap_suitability",
        "roadmap_save",
    ]


@pytest.mark.parametrize("latest, reason", [("ok", "user_request"), ("error_not_found", "initial")])
def test_turn_create_roadmap_uses_latest_as_base_or_creates_initial(monkeypatch, latest, reason):
    tools = scripted_tools(latest=(latest,))
    llm = make_llm(
        [
            route_response(intent="roadmap", roadmap_action="create"),
            tool_response("draft_roadmap", outline(step())),
        ]
    )
    events, _, _ = run_turn(
        "Lập lộ trình tiết kiệm mới",
        llm=llm,
        tools=tools,
        settings=agent_settings(roadmap_default_which="active"),
        monkeypatch=monkeypatch,
    )
    check_agui_order(events)
    assert args_for(tools, "get_roadmap") == [{"which": "latest"}]
    (stored,) = args_for(tools, "save_roadmap")
    assert stored["reason_code"] == reason
    if latest == "ok":
        assert stored["based_on_version"] == fixture("get_roadmap.ok.json")["data"]["version"]
    else:
        assert "based_on_version" not in stored
    (block,) = blocks_of(events)
    assert block["data"] == fixture("save_roadmap.ok.json")["data"]


def test_turn_draft_failure_emits_degraded_notice(monkeypatch):
    events, tools, writer = run_turn(
        "Cho mình xem lộ trình",
        tools=scripted_tools(),
        llm=make_llm([route_response(intent="roadmap"), RuntimeError("planner unavailable")]),
        monkeypatch=monkeypatch,
    )
    check_agui_order(events)
    (notice,) = blocks_of(events)
    assert notice["type"] == "notice" and notice["data"]["kind"] == "degraded"
    assert (notice["data"]["title"], notice["data"]["message"]) == notices.ROADMAP_UNBUILDABLE
    assert not args_for(tools, "save_roadmap") and not writer.calls


def test_turn_caps_model_calls_after_two_repairs(monkeypatch):
    steps = outline(step(), review())
    tools = scripted_tools(checks=("violation",) * 3)
    llm = make_llm(
        [
            route_response(intent="roadmap"),
            *[tool_response("draft_roadmap", steps) for _ in range(3)],
        ]
    )
    settings = agent_settings()
    events, _, writer = run_turn(
        "Cho mình xem lộ trình", llm=llm, tools=tools, settings=settings, monkeypatch=monkeypatch
    )
    check_agui_order(events)
    assert [block["type"] for block in blocks_of(events)] == ["roadmap"]
    assert len(llm[1].calls) == settings.max_model_calls_per_turn
    assert not writer.calls
    assert len(tools.calls) <= settings.max_tool_calls_per_turn
