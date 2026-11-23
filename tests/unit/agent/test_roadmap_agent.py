"""Lập lộ trình từ output có cấu trúc và fixture Gateway của Phase 4."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import date

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
from yofina_core.suitability import Proposal
from yofina_ledger.roadmap_logic import check_steps, proposal_for_step
from yofina_planner.engine import evaluate
from yofina_planner.facts import facts_from_rows
from yofina_planner.rules import cached_rules


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
            "check_suitability": checks if callable(checks) else respond("check_suitability", checks),
            "save_roadmap": respond("save_roadmap", saves),
            **other,
        }
    )


def block_jar_funded(args):
    """check_suitability giả: chặn đề xuất lấy tiền từ hũ (funding_source jar), cho qua bước còn lại."""
    name = "violation" if args["proposal"].get("funding_source") == "jar" else "ok"
    return classify_result("check_suitability", mcp_ok(fixture(f"check_suitability.{name}.json")))


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
    tools = scripted_tools(
        checks=("ok", "ok"),
        get_jar_balances=lambda _args: classify_result(
            "get_jar_balances", mcp_ok(fixture("get_jar_balances.ok_goals.json"))
        ),
    )
    stages = []
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
    # chỉ hũ tiết kiệm đã có mục tiêu được gửi trọng số: bỏ hũ không có, hũ nghĩa vụ, hũ chi tiêu (tool trả PARAMS_INVALID)
    draft["goals"] = [
        {"jar": "du_lich", "weight": 2},
        {"jar": "khong_co", "weight": 3},
        {"jar": "nghia_vu", "weight": 5},
        {"jar": "an_uong", "weight": 1},
    ]
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
    # cùng đề xuất mà save_roadmap (ledger) dựng lại từ bước đã lưu, với ngày bắt đầu giai đoạn của bước
    assert proposals == [
        proposal_for_step(item, phase["start_date"]).model_dump(exclude_none=True)
        for item, phase in ((move, first), (nudge, second))
    ]
    assert proposals[0]["start_date"] == first["start_date"] and "start_date" not in proposals[1]
    assert [proposal["kind"] for proposal in proposals] == [
        "roadmap_set_aside",
        "roadmap_review_goal",
    ]
    assert proposals[0]["funding_source"] == "jar" and proposals[0]["jar_code"] == "giai_tri"
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
    tools = scripted_tools(checks=block_jar_funded)
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
    tools = scripted_tools(checks=block_jar_funded)
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
    # get_jar_balances.ok.json là dữ liệu cũ (không có `kind`): không dựng được save_jars, bước giữ dạng hướng dẫn
    tools = scripted_tools()
    split = review(kind="adjust_split")
    result, client, _ = build(tools, outline({**split, "action": "save_jars"}), outline(split))
    assert result.outcome.ok
    assert "save_jars" in prompt(client, 1)["feedback"][0]["message"]
    assert "action" not in args_for(tools, "save_roadmap")[0]["phases"][0]["steps"][0]


def goal_balances():
    return classify_result(
        "get_jar_balances", mcp_ok(fixture("get_jar_balances.ok_goals.json"))
    )


def test_adjust_split_gan_save_jars_giu_loai_va_muc_tieu_goc():
    tools = scripted_tools(get_jar_balances=goal_balances())
    split = review(kind="adjust_split", action="save_jars")
    result, _, scope = build(tools, outline(split))
    assert result.outcome.ok and scope.calls == 1
    (stored,) = args_for(tools, "save_roadmap")
    action = stored["phases"][0]["steps"][0]["action"]
    assert action["tool"] == "save_jars"
    params = action["params"]
    assert params == normalize_params("save_jars", params)
    assert {"user_id", "confirm_token"}.isdisjoint(params)
    balances = fixture("get_jar_balances.ok_goals.json")["data"]["jars"]
    lines = {
        line["jar"]["code"]: line
        for line in fixture("optimize_allocation.ok.json")["data"]["lines"]
    }
    # thứ tự, tên, màu, biểu tượng, loại và mục tiêu GỐC lấy từ get_jar_balances; tỷ lệ từ bộ tối ưu
    assert [j["code"] for j in params["jars"]] == [j["code"] for j in balances]
    for got, jar in zip(params["jars"], balances, strict=True):
        assert got["kind"] == jar["kind"]
        assert got["name"] == jar["name"] and got["color_key"] == jar["color_key"]
        assert got["split_percent"] == lines[jar["code"]]["split_percent_proposed"]
        assert got.get("goal_vnd") == jar.get("goal_vnd")
        assert got.get("goal_date") == jar.get("goal_date")
    assert sum(j["split_percent"] for j in params["jars"]) == 100
    (proposal,) = [args["proposal"] for args in args_for(tools, "check_suitability")]
    assert proposal["kind"] == "roadmap_adjust_split" and "funding_source" not in proposal


def test_save_jars_chi_gan_cho_buoc_adjust_split():
    tools = scripted_tools(get_jar_balances=goal_balances())
    wrong = review(action="save_jars")  # review_goal
    result, client, _ = build(tools, outline(wrong), outline(review()))
    assert result.outcome.ok
    assert "adjust_split" in prompt(client, 1)["feedback"][0]["message"]
    assert "action" not in args_for(tools, "save_roadmap")[0]["phases"][0]["steps"][0]


def test_optimization_error_stops_before_save():
    tools = scripted_tools(allocation="error_profile_incomplete")
    result, _, _ = build(tools, outline(review()))
    assert result.outcome.code == ErrorCode.PROFILE_INCOMPLETE
    assert not args_for(tools, "save_roadmap")


def test_save_invalid_uses_same_repair_budget():
    tools = scripted_tools(checks=("ok", "ok"), saves=("error_invalid", "ok"))
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
    tools = scripted_tools(checks=block_jar_funded)
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


# --- chạy ổn định trên Runtime (23/11): thử lại phác thảo, luật source_jar_covers, log từng bước bị loại ----------------
def roadmap_events(caplog, event):
    found = []
    for record in caplog.records:
        if record.name != "yofina.agent.roadmap":
            continue
        payload = json.loads(record.getMessage())
        if payload["event"] == event:
            found.append(payload)
    return found


def test_draft_retries_once_when_kind_is_an_action_name():
    # Runtime v17: "phases.0.steps.1.kind: Input should be 'set_aside', ..." với max_attempts=1 làm hỏng cả lượt.
    tools = scripted_tools(checks=("ok", "ok"))
    bad = outline(review(), step(kind="move_between_jars"))
    result, client, scope = build(tools, bad, outline(review(), step()))
    assert result.outcome.ok and scope.calls == 2
    tool_result = client.calls[1]["messages"][-1]["content"][0]["toolResult"]
    assert tool_result["status"] == "error"
    assert "phases.0.steps.1.kind" in tool_result["content"][0]["text"]
    system = json.dumps(client.calls[0]["system"], ensure_ascii=False)
    assert "không bao giờ" in system and "là kind" in system
    assert len(args_for(tools, "save_roadmap")) == 1


def test_draft_retry_stays_within_turn_cap():
    from yofina_core.llm import StructuredOutputError

    tools = scripted_tools()
    bad = outline(step(kind="move_between_jars"))
    result, client, scope = build(tools, bad, outline(step()), scope=TurnScope(1))
    assert isinstance(result.model_error, StructuredOutputError)
    assert scope.calls == len(client.calls) == 1
    assert not args_for(tools, "optimize_allocation")


@pytest.mark.parametrize(("used_by_router", "repairs"), [(0, 2), (1, 1)])
def test_retried_draft_leaves_repairs_inside_cap_of_four(used_by_router, repairs):
    # Job sinh lại (không router): phác thảo 2 + sửa 2 = 4. Chat (router 1): phác thảo 2 + sửa 1 = 4.
    from yofina_core.llm import CallRecord

    settings = agent_settings()
    assert settings.max_model_calls_per_turn == 4 and settings.roadmap_fix_max_rounds == 2
    scope = TurnScope(settings.max_model_calls_per_turn)
    for _ in range(used_by_router):
        scope.begin_call("small")
        scope.add(CallRecord("small", "router", 0, 0, 0, "ok"))
    draft = outline(step(), review())
    tools = scripted_tools(checks=block_jar_funded)
    bad = outline(step(kind="move_between_jars"), review())
    result, client, _ = build(tools, bad, *[draft] * 3, scope=scope)
    assert result.outcome.ok
    assert len(client.calls) == 2 + repairs
    assert scope.calls == settings.max_model_calls_per_turn


def suitability_from_engine(facts):
    """check_suitability chạy đúng bộ luật thật (gồm source_jar_covers) trên dữ kiện cho trước."""

    def result(args):
        verdict = evaluate(Proposal.model_validate(args["proposal"]), facts, cached_rules())
        payload = {
            **fixture("check_suitability.ok.json"),
            "data": verdict.model_dump(mode="json", exclude_none=True),
        }
        return classify_result("check_suitability", mcp_ok(payload))

    return result


def low_entertainment_balances(balance_vnd):
    payload = fixture("get_jar_balances.ok_goals.json")
    for jar in payload["data"]["jars"]:
        if jar["code"] == "giai_tri":
            jar["balance_vnd"] = balance_vnd
    facts = facts_from_rows(
        today=date.fromisoformat(payload["app_date"]),
        user={"monthly_salary_vnd": 12_000_000, "payday_day": 1, "risk_tolerance": "low"},
        jars=payload["data"]["jars"],
        obligations=[],
        window_days=30,
    )
    return classify_result("get_jar_balances", mcp_ok(payload)), facts


def monthly_reserve():
    data = fixture("optimize_allocation.ok.json")["data"]
    line = next(item for item in data["lines"] if item["jar"]["code"] == "du_phong")
    return line["proposed_monthly_vnd"] - line["current_monthly_vnd"]


def test_future_step_over_current_balance_but_within_monthly_income_passes_like_save():
    # Hũ Giải trí chỉ còn 200.000 ₫, ngày lương mùng 1 (kỳ lương kế 01/12). Bước của giai đoạn sau lấy khoản hằng tháng từ lương
    # các kỳ sau, nên luật so nó với thu nhập tháng chứ không với số dư hôm nay: qua ngay, không cần vòng sửa.
    balances, facts = low_entertainment_balances(200_000)
    assert facts.jar("giai_tri").balance_vnd < monthly_reserve() < facts.monthly_income_vnd
    tools = scripted_tools(get_jar_balances=balances, checks=suitability_from_engine(facts))
    draft = outline(review())
    draft["phases"].append({"phase_id": "tich_luy", "title": "Tích lũy dự phòng", "steps": [step()]})
    result, client, scope = build(tools, draft)
    assert result.outcome.ok and scope.calls == 1 and len(client.calls) == 1

    (stored,) = args_for(tools, "save_roadmap")
    later = stored["phases"][1]
    assert later["phase_id"] == "tich_luy" and later["start_date"] >= facts.next_payday.isoformat()
    (move,) = [a["proposal"] for a in args_for(tools, "check_suitability") if a["proposal"]["kind"] == "roadmap_set_aside"]
    assert move["funding_source"] == "jar" and move["jar_code"] == "giai_tri"
    assert move == proposal_for_step(later["steps"][0], later["start_date"]).model_dump(exclude_none=True)
    # save_roadmap kiểm lại đúng như vậy và không chặn
    violations, checked = check_steps(stored["phases"], facts, cached_rules())
    assert violations == [] and "source_jar_covers" in checked["bu_du_phong"]


def test_step_starting_now_over_current_balance_is_still_blocked(caplog):
    # Cùng bước đó ở giai đoạn đầu (bắt đầu hôm nay, trước kỳ lương kế): tiền lấy từ số dư hiện có nên vẫn bị chặn và sửa.
    caplog.set_level("WARNING", logger="yofina.agent.roadmap")
    balances, facts = low_entertainment_balances(200_000)
    tools = scripted_tools(get_jar_balances=balances, checks=suitability_from_engine(facts))
    fixed = outline(step(kind="adjust_split", jar_code="du_phong", to_jar_code=None, action=None))
    result, client, scope = build(tools, outline(step()), fixed)
    assert result.outcome.ok and scope.calls == 2

    move = args_for(tools, "check_suitability")[0]["proposal"]
    assert move["kind"] == "roadmap_set_aside" and move["start_date"] < facts.next_payday.isoformat()
    (feedback,) = prompt(client, 1)["feedback"]
    assert feedback["step_id"] == "bu_du_phong" and feedback["rule_id"] == "source_jar_covers"

    # ledger chặn cùng bước đó lúc lưu (giai đoạn bắt đầu hôm nay)
    original = {
        "step_id": "bu_du_phong", "kind": "set_aside", "title": "t", "reason": "r",
        "jar_code": "giai_tri", "to_jar_code": "du_phong", "amount_vnd": monthly_reserve(),
    }  # fmt: skip
    phase = {"phase_id": "on_dinh", "start_date": facts.today.isoformat(), "steps": [original]}
    violations, _ = check_steps([phase], facts, cached_rules())
    assert [rule for _, rule, _ in violations] == ["source_jar_covers"]
    (rejected,) = roadmap_events(caplog, "roadmap_step_rejected")
    assert rejected["phase_id"] == "on_dinh" and rejected["rule_id"] == "source_jar_covers"
    assert rejected["funding_source"] == "jar"


def test_future_step_over_monthly_income_is_still_blocked():
    # Khoản hằng tháng vượt cả thu nhập tháng thì giai đoạn sau cũng không gánh được.
    balances, facts = low_entertainment_balances(200_000)
    poor = replace(facts, monthly_income_vnd=monthly_reserve() - 1)
    tools = scripted_tools(get_jar_balances=balances, checks=suitability_from_engine(poor))
    draft = outline(review())
    draft["phases"].append({"phase_id": "tich_luy", "title": "Tích lũy dự phòng", "steps": [step()]})
    fixed = outline(review())
    result, client, _ = build(tools, draft, fixed)
    assert result.outcome.ok
    (feedback,) = prompt(client, 1)["feedback"]
    assert feedback["step_id"] == "bu_du_phong" and feedback["rule_id"] == "source_jar_covers"


def test_agent_proposal_matches_ledger_save_check_in_later_phase():
    # Hai bên dựng cùng một đề xuất cho bước của giai đoạn sau (có start_date của giai đoạn đó).
    tools = scripted_tools(checks=("ok", "ok"))
    draft = outline(review())
    draft["phases"].append({"phase_id": "tich_luy", "title": "Tích lũy dự phòng", "steps": [step()]})
    result, _, _ = build(tools, draft)
    assert result.outcome.ok
    (stored,) = args_for(tools, "save_roadmap")
    expected = [
        proposal_for_step(item, phase["start_date"]).model_dump(exclude_none=True)
        for phase in stored["phases"]
        for item in phase["steps"]
    ]
    assert [args["proposal"] for args in args_for(tools, "check_suitability")] == expected
    assert expected[1]["start_date"] == stored["phases"][1]["start_date"]


@pytest.mark.parametrize(
    "draft_step",
    [
        step(),
        step(action=None),
        step(kind="pay_obligation", jar_code="nghia_vu", to_jar_code=None, action=None,
             amount_ref={"jar_code": "nghia_vu", "field": "floor_vnd"}),
        step(kind="pay_obligation", jar_code="an_uong", to_jar_code="nghia_vu", action=None,
             amount_ref={"jar_code": "nghia_vu", "field": "floor_vnd"}),
        step(kind="cut_spending", jar_code="giai_tri", to_jar_code="du_phong",
             amount_ref={"jar_code": "giai_tri", "field": "proposed_decrease"}),
        review(),
        review(action="schedule_nudge"),
    ],
)  # fmt: skip
def test_agent_proposal_matches_ledger_save_check(draft_step):
    # Trước đây bước pay_obligation một hũ bị agent gắn funding_source jar (ledger thì không) nên bị source_jar_covers chặn
    # oan; bước set_aside không action thì agent không gắn nguồn (ledger có) nên lỗi chỉ lộ ra lúc lưu.
    tools = scripted_tools()
    result, _, _ = build(tools, {"phases": [{"phase_id": "p", "title": "Ổn định", "steps": [draft_step]}]})
    assert result.outcome.ok
    (stored,) = args_for(tools, "save_roadmap")
    (saved_step,) = stored["phases"][0]["steps"]
    (checked,) = [args["proposal"] for args in args_for(tools, "check_suitability")]
    assert checked == proposal_for_step(
        saved_step, stored["phases"][0]["start_date"]
    ).model_dump(exclude_none=True)


def test_ordinal_prefix_in_titles_is_not_a_grounding_failure():
    tools = scripted_tools()
    draft = {
        "phases": [
            {"phase_id": "on_dinh", "title": "Giai đoạn 1: Ổn định", "steps": [step(title="Bước 1. Bù hũ dự phòng")]}
        ]
    }
    result, _, scope = build(tools, draft)
    assert result.outcome.ok and scope.calls == 1
    (stored,) = args_for(tools, "save_roadmap")
    assert stored["phases"][0]["title"] == "Ổn định"
    assert stored["phases"][0]["steps"][0]["title"] == "Bù hũ dự phòng"


def test_grounding_feedback_names_the_numbers_and_logs_without_text(caplog):
    caplog.set_level("WARNING", logger="yofina.agent.roadmap")
    tools = scripted_tools()
    bad = outline(step(reason="Quỹ dự phòng nên đủ 3 đến 6 tháng chi tiêu"))
    result, client, _ = build(tools, bad, outline(step()))
    assert result.outcome.ok
    (feedback,) = prompt(client, 1)["feedback"]
    assert feedback["rule_id"] == "numeric_grounding" and "3, 6" in feedback["message"]
    (rejected,) = roadmap_events(caplog, "roadmap_step_rejected")
    assert rejected["reason"] == "grounding" and rejected["field"] == "reason"
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "Quỹ dự phòng" not in logged and "tháng" not in logged


def test_whole_roadmap_rejected_logs_rules_without_amounts(caplog):
    caplog.set_level("WARNING", logger="yofina.agent.roadmap")
    tools = scripted_tools(checks=("violation",) * 3)
    draft = outline(step())
    result, _, _ = build(tools, draft, draft, draft)
    assert result.outcome is None and not args_for(tools, "save_roadmap")
    rule = fixture("check_suitability.violation.json")["data"]["violations"][0]["rule_id"]
    rejected = roadmap_events(caplog, "roadmap_step_rejected")
    assert [(item["round"], item["rule_id"]) for item in rejected] == [(0, rule), (1, rule), (2, rule)]
    (invalid,) = roadmap_events(caplog, "roadmap_invalid")
    assert invalid == {
        "event": "roadmap_invalid",
        "stage": "verify",
        "reason_code": "initial",
        "rounds": 2,
        "rejected": 1,
        "rules": {rule: 1},
    }
    amount = args_for(tools, "check_suitability")[0]["proposal"]["amount_vnd"]
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert str(amount) not in logged and "Bù hũ dự phòng" not in logged
# --- mục tiêu người dùng nói trong câu (UserGoal) ----------------------------------------------------
from yofina_agent.roadmap_agent import UserGoal  # noqa: E402

USER_GOAL = UserGoal(jar="du_lich", target_vnd=1_000_000_000, target_date="2026-11-30")


def test_muc_tieu_nguoi_dung_thay_trong_so_model_cung_hu():
    tools = scripted_tools(get_jar_balances=goal_balances())
    draft = outline(review())
    draft["goals"] = [{"jar": "du_lich", "weight": 2}, {"jar": "du_phong", "weight": 3}]
    result, _, _ = build(tools, draft, user_goal=USER_GOAL)
    assert result.outcome.ok
    assert args_for(tools, "optimize_allocation") == [
        {
            "goals": [
                {"jar": "du_lich", "target_vnd": 1_000_000_000, "target_date": "2026-11-30"},
                {"jar": "du_phong", "weight": 3},
            ]
        }
    ]
    # không ghi mục tiêu vào hũ
    assert not args_for(tools, "save_jars") and "save_jars" not in tools.results


@pytest.mark.parametrize(
    "goal",
    [
        UserGoal(jar="an_uong", target_vnd=1_000_000_000),  # hũ chi tiêu
        UserGoal(jar="nghia_vu", target_vnd=1_000_000_000),  # hũ nghĩa vụ
        UserGoal(jar="khong_co", target_vnd=1_000_000_000),
    ],
)
def test_muc_tieu_hu_khong_phai_tiet_kiem_khong_gui_optimize(goal):
    tools = scripted_tools(get_jar_balances=goal_balances())
    result, _, _ = build(tools, outline(review()), user_goal=goal)
    assert result.outcome.ok
    assert args_for(tools, "optimize_allocation") == [{}]


def test_so_tien_muc_tieu_cua_nguoi_dung_co_can_cu_trong_buoc():
    tools = scripted_tools(get_jar_balances=goal_balances())
    reason = "Mục tiêu 1.000.000.000 ₫ của hũ Du lịch cần xem lại"
    result, client, scope = build(tools, outline(review(reason=reason)), user_goal=USER_GOAL)
    assert result.outcome.ok and scope.calls == 1  # không vòng sửa numeric_grounding
    (stored,) = args_for(tools, "save_roadmap")
    assert stored["phases"][0]["steps"][0]["reason"] == reason
    # thiếu mục tiêu của người dùng thì cùng câu đó là số không căn cứ
    tools = scripted_tools(get_jar_balances=goal_balances())
    result, client, _ = build(tools, outline(review(reason=reason)), outline(review()))
    assert prompt(client, 1)["feedback"][0]["rule_id"] == "numeric_grounding"


def test_muc_tieu_nguoi_dung_vo_nghiem_luu_infeasible_va_hai_lua_chon():
    tools = scripted_tools(allocation="ok_infeasible", get_jar_balances=goal_balances())
    result, _, _ = build(tools, outline(review()), user_goal=USER_GOAL)
    assert result.outcome.ok
    assert args_for(tools, "optimize_allocation")[0]["goals"][0]["target_vnd"] == 1_000_000_000
    (stored,) = args_for(tools, "save_roadmap")
    data = fixture("optimize_allocation.ok_infeasible.json")["data"]
    assert stored["feasibility"] == "infeasible"
    assert stored["alternatives"] == data["alternatives"] and len(stored["alternatives"]) == 2
