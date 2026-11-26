"""Lập lộ trình từ output có cấu trúc và fixture Gateway của Phase 4."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from agent_helpers import (
    FakeRecords,
    FakeTools,
    FakeUsage,
    FakeWriter,
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

from yofina_core import blocks as B
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
    # Bước không có số tiền phải là nhắc/xem lại CÓ NGÀY (action schedule_nudge), không thì bị đưa vào vòng sửa như bước mơ hồ.
    return {
        "step_id": "giu_muc_tieu",
        "kind": "review_goal",
        "title": "Xem lại mục tiêu",
        "reason": "Theo dõi khả năng giữ mục tiêu",
        "jar_code": "du_lich",
        "action": "schedule_nudge",
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
            "optimize_allocation": respond(
                "optimize_allocation", allocation if isinstance(allocation, tuple) else (allocation,)
            ),
            "check_suitability": checks if callable(checks) else respond("check_suitability", checks),
            "save_roadmap": respond("save_roadmap", saves),
            **other,
        }
    )


def obligations_result(*, due_from_nghia_vu: int | None = None, **pay_jars: str):
    """`get_obligations` giả từ fixture: `pay_jars` đổi hũ trả theo tên khoản; `due_from_nghia_vu` thêm một khoản tiền trọ trả từ hũ
    Nghĩa vụ đến hạn trước kỳ lương (ngày 28/11, kỳ lương 05/12 của phương án fixture)."""
    payload = fixture("get_obligations.ok.json")
    for item in payload["data"]["obligations"]:
        if item["name"] in pay_jars:
            item["pay_jar"] = pay_jars[item["name"]]
    if due_from_nghia_vu is not None:
        payload["data"]["obligations"].append(
            {
                "id": "5d1f0b9e-8c2a-4e3b-9f6d-7a8b9c0d1e2f", "kind": "rent", "name": "Tiền trọ",
                "amount_vnd": due_from_nghia_vu, "fee_vnd": 0, "due_date": "2026-11-28", "cycle": "monthly",
                "due_day": 28, "status": "active", "pay_jar": "nghia_vu", "is_essential": True, "source": "declared",
            }
        )  # fmt: skip
    return lambda _args: classify_result("get_obligations", mcp_ok(payload))


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


def texts_of(events):
    return [e.delta for e in events if e.type.value == "TEXT_MESSAGE_CONTENT"]


def test_save_grounded_roadmap_and_report_stages():
    tools = scripted_tools(
        allocation=("ok", "ok"),
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
    # hai bước xem lại ở hai giai đoạn có cùng đề xuất: kiểm một lần, dùng chung phán quyết
    assert len(result.suitability) == 2
    assert scope.calls == 1
    assert [stage for stage, _ in stages] == ["context", "draft", "allocate", "suitability", "save"]
    assert [progress for _, progress in stages] == sorted({progress for _, progress in stages})
    # phương án mặc định chạy trước bản phác thảo (không trọng số); bản phác thảo xin horizon và trọng số khác nên tối ưu lần hai,
    # chỉ hũ tiết kiệm đã có mục tiêu được gửi trọng số
    assert args_for(tools, "optimize_allocation") == [
        {},
        {"horizon_months": 6, "goals": [{"jar": "du_lich", "weight": 2}]},
    ]
    assert args_for(tools, "get_roadmap") == [{"which": "latest"}]
    (stored,) = args_for(tools, "save_roadmap")
    assert stored["reason_code"] == "initial" and "based_on_version" not in stored
    assert stored["feasibility"] == "on_track"
    data = fixture("optimize_allocation.ok.json")["data"]
    assert stored["goals"] == data["goals"]
    assert stored["alternatives"] == data["alternatives"]
    first, second, third = stored["phases"]
    # giai đoạn đầu là từ hôm nay tới ngày lương kế (việc làm ngay, trước kỳ lương, #19); kỳ phân bổ bắt đầu ở ngày lương kế: giai
    # đoạn kế là tháng đầu của kỳ, giai đoạn cuối là phần còn lại; nối liền và theo thứ tự thời gian
    assert first["start_date"] == "2026-11-21" == fixture("get_jar_balances.ok_goals.json")["app_date"]
    assert first["end_date"] == data["period_start"] == "2026-12-05" == second["start_date"]
    assert second["end_date"] == "2027-01-05" == third["start_date"]
    assert third["end_date"] == "2027-04-05"  # horizon trả về là bốn tháng
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
    assert proposal_for_step(third["steps"][0], third["start_date"]).model_dump(exclude_none=True) == proposals[1]
    assert third["steps"][0]["checked_rules"] == nudge["checked_rules"]
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
    # bản sửa đổi số tiền tham chiếu (đề xuất khác) nên được kiểm lại; đề xuất y hệt thì dùng lại phán quyết cũ
    fixed = step(to_jar_code="du_lich", amount_ref={"jar_code": "du_lich", "field": "proposed_increase"})
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
    # phương án mặc định đã chạy trước bản phác thảo; không có bản phác thảo thì không tối ưu lần hai, không lưu
    assert len(args_for(tools, "optimize_allocation")) == 1 and not args_for(tools, "save_roadmap")


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


def test_nghia_vu_trong_ngu_canh_mang_nhan_tieng_viet_khong_mang_ma_loai():
    # #19: bản lộ trình sinh lại ở cảnh 4 ghi "Subscription 300.000 ₫ đến hạn 23/11" vì nghĩa vụ trong ngữ cảnh chỉ có mã loại (tên bị
    # bỏ vì là chữ không tin cậy): model chép chữ có trong ngữ cảnh. Nay mỗi nghĩa vụ mang nhãn của bảng chung, không còn mã.
    from yofina_core.wallet import OBLIGATION_KIND_LABELS

    tools = scripted_tools()
    _, client, _ = build(tools, outline(review()))
    seen = prompt(client)["context"]["obligations"]
    kinds = [o["kind"] for o in fixture("get_obligations.ok.json")["data"]["obligations"]]
    assert [o["kind_label"] for o in seen] == [OBLIGATION_KIND_LABELS[k] for k in kinds]
    assert all("kind" not in o and "name" not in o for o in seen)
    assert not set(kinds) & set(json.dumps(seen, ensure_ascii=False).replace('"', " ").split())


def test_giai_doan_dau_la_tu_hom_nay_toi_ngay_luong_ke():
    # Kỳ phân bổ bắt đầu ở ngày lương kế (05/12, hôm nay 21/11): giai đoạn "việc làm ngay, trước kỳ lương kế" phải nằm TRƯỚC ngày đó,
    # không phải tháng đầu của kỳ (bản cảnh 4 trên app ghi 05/12–05/01 cho giai đoạn "Tuần này"). Bước chuyển tiền của nó lấy từ số
    # dư hiện có nên đề xuất kiểm có start_date là hôm nay (luật source_jar_covers so với số dư).
    tools = scripted_tools(checks=("ok", "ok", "ok"))
    draft = outline(step())
    draft["phases"] += [
        {"phase_id": "sau_luong", "title": "Sau kỳ lương", "steps": [review(step_id="xem_sau_luong")]},
        {"phase_id": "ve_dich", "title": "Về đích", "steps": [review(step_id="xem_ve_dich", jar_code="du_phong")]},
    ]
    result, _, _ = build(tools, draft)
    assert result.outcome.ok
    first, second, third = args_for(tools, "save_roadmap")[0]["phases"]
    payday = fixture("optimize_allocation.ok.json")["data"]["period_start"]
    assert (first["start_date"], first["end_date"]) == ("2026-11-21", payday)
    assert second["start_date"] == payday and third["end_date"] > third["start_date"] == second["end_date"]
    for phase in (first, second, third):
        for item in phase["steps"]:
            if "due_date" in item:
                assert phase["start_date"] <= item["due_date"] <= phase["end_date"]
    move = args_for(tools, "check_suitability")[0]["proposal"]
    assert move["funding_source"] == "jar" and move["start_date"] == "2026-11-21"
    assert first["steps"][0]["metrics"][0]["before"] == "760.000 ₫"  # số dư hiện có của hũ nguồn


def test_model_cannot_send_money_as_a_structured_field():
    tools = scripted_tools()
    result, _, _ = build(tools, outline(step(amount_vnd=123456)))
    assert result.outcome is None and result.model_error is not None
    assert len(args_for(tools, "optimize_allocation")) == 1 and not args_for(tools, "save_roadmap")


def test_split_advice_does_not_overwrite_existing_jar_configuration():
    # get_jar_balances.ok.json là dữ liệu cũ (không có `kind`): không dựng được save_jars, bước giữ dạng hướng dẫn
    tools = scripted_tools()
    split = review(
        kind="adjust_split", action=None, amount_ref={"jar_code": "du_lich", "field": "proposed_increase"}
    )
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
    assert args_for(tools, "save_roadmap")[0]["phases"][0]["steps"][0]["action"]["tool"] == "schedule_nudge"


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


def six_distinct_steps():
    """Bảy bước có đề xuất suitability khác nhau trong ba giai đoạn (bước thứ bảy vượt `roadmap_max_steps`)."""
    return {
        "phases": [
            {
                "phase_id": "thang_nay",
                "title": "Ngay trong tháng này",
                "steps": [
                    step("chuyen_du_phong"),
                    step(
                        "chuyen_du_lich",
                        to_jar_code="du_lich",
                        amount_ref={"jar_code": "du_lich", "field": "proposed_increase"},
                    ),
                    step(
                        "giam_giai_tri",
                        kind="cut_spending",
                        to_jar_code=None,
                        action=None,
                        amount_ref={"jar_code": "giai_tri", "field": "proposed_decrease"},
                    ),
                ],
            },
            {
                "phase_id": "sau_ky_luong",
                "title": "Sau kỳ lương",
                "steps": [
                    step(
                        "tang_chia_du_phong",
                        kind="adjust_split",
                        jar_code="du_phong",
                        to_jar_code=None,
                        action=None,
                    ),
                    review(step_id="xem_lai_du_lich"),
                ],
            },
            {
                "phase_id": "ve_dich",
                "title": "Về đích",
                "steps": [
                    review(step_id="nhac_du_phong", kind="remind", jar_code="du_phong"),
                    review(step_id="thua", kind="remind", jar_code="an_uong"),
                ],
            },
        ]
    }


def test_tool_budget_includes_every_round_save_and_conflict_attempt():
    from yofina_agent.roadmap_agent import _tool_budget

    settings = agent_settings()
    # trần riêng của lượt lập lộ trình (cũ: trần chung 16 chỉ đủ hai bước)
    assert settings.roadmap_max_steps == 6
    assert settings.roadmap_max_tool_calls_per_turn == 40 > settings.max_tool_calls_per_turn == 18
    # 3 ngữ cảnh + 2 tối ưu (mặc định, và lần hai nếu bản phác thảo xin phương án khác) + 3 lưu + 2 xung đột = 10 cố định
    assert _tool_budget(settings, 15, 2, True) == 1
    # chat đã đọc get_roadmap (latest, có thể thêm active): 10 cố định + 6 bước × 3 vòng = 28
    assert _tool_budget(settings, 40 - 2, 2, True) == 6

    draft = six_distinct_steps()
    tools = scripted_tools(
        checks=("ok",) * 6,
        saves=("error_invalid", "error_invalid", "error_version_conflict", "ok"),
        latest=("ok", "ok"),
    )
    result, client, scope = build(
        tools, draft, draft, draft, settings=settings, reason_code="user_request"
    )
    assert result.outcome.ok and scope.calls == 3
    assert prompt(client)["max_steps"] == settings.roadmap_max_steps == 6
    # bước đã kiểm và giữ nguyên ở vòng sửa không bị kiểm lại: 6 lượt check cho cả ba vòng
    assert len(args_for(tools, "check_suitability")) == 6
    assert len(tools.calls) == 4 + 1 + 6 + 4 + 1 <= settings.roadmap_max_tool_calls_per_turn
    for payload in args_for(tools, "save_roadmap"):
        assert [len(phase["steps"]) for phase in payload["phases"]] == [3, 2, 1]
        assert "thua" not in json.dumps(payload)


def test_check_suitability_cua_moi_giai_doan_chay_song_song():
    """Mọi bước của một vòng được kiểm cùng lúc: lượt check thứ sáu mới mở chốt, nên chạy tuần tự (theo bước hay theo giai
    đoạn) sẽ hết giờ."""
    tools = scripted_tools(checks=("ok",) * 6)
    llm, _client, _ = make_llm([tool_response("draft_roadmap", six_distinct_steps())])
    settings = agent_settings()

    async def exercise():
        ready = asyncio.Event()
        in_flight = 0
        peak = 0

        async def call(name, args, target):
            nonlocal in_flight, peak
            if name == "check_suitability":
                in_flight += 1
                peak = max(peak, in_flight)
                if in_flight == 6:
                    ready.set()
                await asyncio.wait_for(ready.wait(), timeout=1)
                in_flight -= 1
            return await tools.call(settings.tool(name, target=target), args)

        result = await build_roadmap(call, llm, settings, TurnScope(1), reason_code="initial")
        return result, peak

    result, peak = run(exercise())
    assert result.outcome.ok and peak == 6
    (stored,) = args_for(tools, "save_roadmap")
    assert sum(len(phase["steps"]) for phase in stored["phases"]) == 6
    assert [phase["start_date"] for phase in stored["phases"]] == sorted(
        phase["start_date"] for phase in stored["phases"]
    )


@pytest.mark.parametrize(
    ("vague", "fragment"),
    [
        # "Giữ tiền hũ Nghĩa vụ cho các khoản sắp đến hạn": không nói lấy tiền từ hũ nào
        (
            step(kind="pay_obligation", jar_code="nghia_vu", to_jar_code=None, action=None,
                 amount_ref={"jar_code": "nghia_vu", "field": "floor_vnd"}),
            "hũ nguồn",
        ),
        (step(to_jar_code="giai_tri", action=None,
              amount_ref={"jar_code": "giai_tri", "field": "proposed_decrease"}), "hũ nguồn"),
        (step(amount_ref=None, action=None), "amount_ref"),
        # "Giảm chi tiêu Giải trí để bù nghĩa vụ": không có số tiền giảm
        (step(kind="cut_spending", to_jar_code=None, action=None, amount_ref=None), "proposed_decrease"),
        (review(kind="adjust_split", action=None), "save_jars"),
        (review(action=None), "schedule_nudge"),
        (review(kind="remind", action=None), "schedule_nudge"),
    ],
)  # fmt: skip
def test_buoc_mo_ho_vao_vong_sua_khong_ton_luot_kiem(vague, fragment, caplog):
    caplog.set_level("WARNING", logger="yofina.agent.roadmap")
    tools = scripted_tools(checks=("ok",))
    vague = {**vague, "step_id": "mo_ho"}
    result, client, scope = build(tools, outline(vague), outline(step()))
    assert result.outcome.ok and scope.calls == 2
    (feedback,) = prompt(client, 1)["feedback"]
    assert feedback["step_id"] == "mo_ho" and feedback["rule_id"] == "vague_step"
    assert fragment in feedback["message"]
    # chỉ bước đã sửa được kiểm suitability và lưu
    (checked,) = args_for(tools, "check_suitability")
    assert checked["proposal"]["kind"] == "roadmap_set_aside"
    (stored,) = args_for(tools, "save_roadmap")
    assert [s["step_id"] for p in stored["phases"] for s in p["steps"]] == ["bu_du_phong"]
    (rejected,) = roadmap_events(caplog, "roadmap_step_rejected")
    assert rejected["reason"] == "vague" and rejected["rule_id"] == "vague_step"


def test_tham_chieu_khong_duong_duoc_goi_y_tham_chieu_vua_so_du():
    # floor_gap_vnd của hũ Dự phòng là 0: phản hồi liệt kê các tham chiếu dương không vượt số dư hũ Giải trí (760.000 ₫)
    tools = scripted_tools()
    bad = step(amount_ref={"jar_code": "du_phong", "field": "floor_gap_vnd"})
    result, client, _ = build(tools, outline(bad), outline(step()))
    assert result.outcome.ok
    (feedback,) = prompt(client, 1)["feedback"]
    assert feedback["rule_id"] == "step_invalid"
    assert "giai_tri.proposed_decrease (600.000 ₫)" in feedback["message"]
    assert "du_phong.proposed_increase (600.000 ₫)" in feedback["message"]
    assert "current_monthly_vnd" not in feedback["message"]  # 1.200.000 ₫ vượt số dư hũ nguồn


def test_prompt_neu_khuon_hanh_dong_cu_the_khong_chep_seed():
    from yofina_agent.roadmap_agent import ROADMAP_SYSTEM

    for rule in ("hai hoặc ba giai đoạn", "từ bốn bước", "MỘT hành động cụ thể", "schedule_nudge", "hũ nguồn"):
        assert rule in ROADMAP_SYSTEM
    seed = json.loads((Path(__file__).parents[3] / "data/personas/roadmaps/minh.json").read_text(encoding="utf-8"))
    titles = [s["title"] for v in seed["versions"] for p in v.get("phases", []) for s in p["steps"]]
    assert titles and not any(title in ROADMAP_SYSTEM for title in titles)
    assert not any(ch.isdigit() for ch in ROADMAP_SYSTEM)


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
    # lời kết dựng bằng mã từ khối (không tốn lượt gọi model), phát sau khối
    assert not writer.calls
    (text,) = texts_of(events)
    data = block["data"]
    steps = sum(len(phase["steps"]) for phase in data["phases"])
    assert text.startswith(
        f"Đây là bản đề xuất phiên bản {data['version']} ({len(data['phases'])} giai đoạn, {steps} bước)"
    )
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


def roadmap_payload(name, **data_changes):
    payload = fixture(name)
    payload["data"].update(data_changes)
    return payload


def test_turn_lap_lai_khi_co_ban_de_xuat_dang_cho_noi_ro_ban_bi_thay(monkeypatch):
    # minh sau khi đặt lại: v2 đang dùng, v3 "hành vi thay đổi" đang chờ. Lập lại trong chat tạo v4 và bỏ v3 (migration 0052).
    pending = roadmap_payload("save_roadmap.ok.json")  # v3 proposed, behavior_changed, dựa trên v2
    active = fixture("get_roadmap.ok.json")  # v2 active
    saved = roadmap_payload("save_roadmap.ok.json", version=4, based_on_version=2)
    tools = scripted_tools(latest=(pending, active), saves=(saved,), checks=("ok",) * 6)
    llm = make_llm(
        [
            route_response(intent="roadmap", roadmap_action="create"),
            tool_response("draft_roadmap", six_distinct_steps()),
        ]
    )
    settings = agent_settings()
    events, _, writer = run_turn(
        "Lập lại lộ trình giúp mình", llm=llm, tools=tools, settings=settings, monkeypatch=monkeypatch
    )
    check_agui_order(events)
    # đọc bản mới nhất rồi bản đang dùng TRƯỚC khi lưu; bản mới dựa trên bản đang dùng
    assert args_for(tools, "get_roadmap") == [{"which": "latest"}, {"which": "active"}]
    (stored,) = args_for(tools, "save_roadmap")
    assert stored["based_on_version"] == 2 and stored["reason_code"] == "user_request"
    assert sum(len(phase["steps"]) for phase in stored["phases"]) == 6
    # trần tool call riêng của lượt lập lộ trình: với trần chung 16 sau hai lần đọc get_roadmap chỉ còn chỗ cho một bước
    assert prompt(llm[1], 1)["max_steps"] == settings.roadmap_max_steps == 6
    assert len(tools.calls) <= settings.roadmap_max_tool_calls_per_turn
    roadmap, notice = blocks_of(events)
    assert roadmap["type"] == "roadmap" and roadmap["data"]["version"] == 4
    assert notice["type"] == "notice" and notice["data"]["kind"] == "info"
    assert notice["data"]["code"] == "ROADMAP_PROPOSAL_REPLACED"
    assert notice["data"]["message"].startswith(
        "Bản này thay bản đề xuất phiên bản 3 (lý do: hành vi thay đổi) đang chờ bạn chọn."
    )
    assert "Bản đang dùng vẫn là phiên bản 2" in notice["data"]["message"]
    assert "Dùng bản mới" in notice["data"]["message"] and "Giữ bản cũ" in notice["data"]["message"]
    # lời kết dựng bằng mã: bản đề xuất nào, bản đang dùng, bước tiếp theo; không gọi writer
    assert not writer.calls
    (text,) = texts_of(events)
    data = roadmap["data"]
    steps = sum(len(phase["steps"]) for phase in data["phases"])
    assert text.startswith(
        f"Đây là bản đề xuất phiên bản 4 ({len(data['phases'])} giai đoạn, {steps} bước), chưa thay lộ trình bạn đang dùng."
    )
    assert "Bản đang dùng vẫn là phiên bản 2." in text
    assert text.endswith("bấm So với bản đang dùng trên thẻ, rồi chọn Dùng bản mới hoặc Giữ bản cũ.")


def test_turn_lap_lai_khi_ban_moi_nhat_da_bo_dua_tren_ban_dang_dung(monkeypatch):
    # Người dùng đã "Giữ bản cũ" (v3 discarded): lưu dựa trên bản đã bỏ thì ledger trả ROADMAP_VERSION_CONFLICT.
    dropped = roadmap_payload("save_roadmap.ok.json", status="discarded")
    tools = scripted_tools(latest=(dropped, fixture("get_roadmap.ok.json")))
    llm = make_llm(
        [route_response(intent="roadmap", roadmap_action="create"), tool_response("draft_roadmap", outline(step()))]
    )
    events, _, writer = run_turn("Lập lại lộ trình", llm=llm, tools=tools, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert args_for(tools, "get_roadmap") == [{"which": "latest"}, {"which": "active"}]
    assert args_for(tools, "save_roadmap")[0]["based_on_version"] == 2
    assert [block["type"] for block in blocks_of(events)] == ["roadmap"]  # không có bản đề xuất nào bị thay
    assert not writer.calls
    (text,) = texts_of(events)
    assert "Bản đang dùng vẫn là phiên bản 2." in text


def test_turn_lap_lai_tu_ban_dang_dung_khong_doc_them(monkeypatch):
    tools = scripted_tools(latest=("ok",))
    llm = make_llm(
        [route_response(intent="roadmap", roadmap_action="create"), tool_response("draft_roadmap", outline(step()))]
    )
    events, _, writer = run_turn("Lập lại lộ trình", llm=llm, tools=tools, monkeypatch=monkeypatch)
    assert args_for(tools, "get_roadmap") == [{"which": "latest"}]
    assert [block["type"] for block in blocks_of(events)] == ["roadmap"]
    (text,) = texts_of(events)
    assert "Bản đang dùng vẫn là phiên bản 2." in text and not writer.calls


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
    # Runtime v20: router + phác thảo + hai vòng sửa dùng hết trần 4 nên writer bị bỏ qua và lượt không có lời kết.
    # Lời kết nay dựng bằng mã nên vẫn có dù không còn lượt gọi model.
    assert not writer.calls
    (text,) = texts_of(events)
    assert text.startswith("Đây là bản đề xuất phiên bản ") and "Bước tiếp theo" in text
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
    assert len(args_for(tools, "optimize_allocation")) == 1 and not args_for(tools, "save_roadmap")


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
    # Cùng bước đó ở giai đoạn đầu (bắt đầu hôm nay, trước kỳ lương kế): tiền lấy một lần từ số dư hiện có nên vẫn bị chặn và sửa.
    # Từ #19 kỳ lộ trình bắt đầu ngày lương kế tiếp; kỳ chỉ còn bắt đầu hôm nay khi hồ sơ chưa có ngày lương (allocation giữ hôm nay).
    # Từ C3 (#39) mã chặn bước ngay khi dựng (trần chuyển ngay: số dư trừ khoản hũ nguồn phải trả trước kỳ lương), trước lượt
    # check_suitability; luật source_jar_covers vẫn chặn cùng bước đó lúc lưu.
    caplog.set_level("WARNING", logger="yofina.agent.roadmap")
    balances, facts = low_entertainment_balances(200_000)
    ok = fixture("optimize_allocation.ok.json")
    today_start = {**ok, "data": {**ok["data"], "period_start": facts.today.isoformat()}}
    tools = scripted_tools(
        allocation=today_start, get_jar_balances=balances, checks=suitability_from_engine(facts)
    )
    fixed = outline(step(kind="adjust_split", jar_code="du_phong", to_jar_code=None, action=None))
    result, client, scope = build(tools, outline(step()), fixed)
    assert result.outcome.ok and scope.calls == 2

    assert all(a["proposal"]["kind"] != "roadmap_set_aside" for a in args_for(tools, "check_suitability"))
    (feedback,) = prompt(client, 1)["feedback"]
    assert feedback["step_id"] == "bu_du_phong" and feedback["rule_id"] == "step_invalid"
    assert "200.000 ₫" in feedback["message"]
    # không tham chiếu nào của hai hũ vừa số dư 200.000 ₫ của hũ nguồn: phản hồi nói cách sửa khác
    assert "Không có tham chiếu nào" in feedback["message"]
    assert "dời bước sang giai đoạn sau kỳ lương" in feedback["message"]

    # ledger chặn cùng bước đó lúc lưu (giai đoạn bắt đầu hôm nay)
    original = {
        "step_id": "bu_du_phong", "kind": "set_aside", "title": "t", "reason": "r",
        "jar_code": "giai_tri", "to_jar_code": "du_phong", "amount_vnd": monthly_reserve(),
    }  # fmt: skip
    phase = {"phase_id": "on_dinh", "start_date": facts.today.isoformat(), "steps": [original]}
    violations, _ = check_steps([phase], facts, cached_rules())
    assert [rule for _, rule, _ in violations] == ["source_jar_covers"]
    (rejected,) = roadmap_events(caplog, "roadmap_step_rejected")
    assert rejected["phase_id"] == "on_dinh" and rejected["detail"] == "amount_over_available"


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
        # pay_obligation một hũ ("giữ tiền hũ Nghĩa vụ") nay là bước mơ hồ: xem test_buoc_mo_ho_vao_vong_sua_khong_ton_luot_kiem
        step(kind="pay_obligation", jar_code="an_uong", to_jar_code="nghia_vu", action=None,
             amount_ref={"jar_code": "nghia_vu", "field": "proposed_increase"}),
        step(kind="cut_spending", jar_code="giai_tri", to_jar_code="du_phong",
             amount_ref={"jar_code": "giai_tri", "field": "proposed_decrease"}),
        review(),
        review(action="schedule_nudge"),
    ],
)  # fmt: skip
def test_agent_proposal_matches_ledger_save_check(draft_step):
    # Trước đây bước pay_obligation một hũ bị agent gắn funding_source jar (ledger thì không) nên bị source_jar_covers chặn
    # oan; bước set_aside không action thì agent không gắn nguồn (ledger có) nên lỗi chỉ lộ ra lúc lưu.
    extra = {}
    if draft_step["kind"] == "pay_obligation":
        # bước nạp hũ Nghĩa vụ ở giai đoạn đầu chỉ hợp lệ khi hũ đó thiếu cho khoản nó trả trước kỳ lương (#39)
        extra["get_obligations"] = obligations_result(due_from_nghia_vu=1_200_000)
    tools = scripted_tools(**extra)
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
    tools = scripted_tools(allocation=("ok", "ok"), get_jar_balances=goal_balances())
    draft = outline(review())
    draft["goals"] = [{"jar": "du_lich", "weight": 2}, {"jar": "du_phong", "weight": 3}]
    result, client, _ = build(tools, draft, user_goal=USER_GOAL)
    assert result.outcome.ok
    user_entry = {"jar": "du_lich", "target_vnd": 1_000_000_000, "target_date": "2026-11-30"}
    # phương án mặc định đã theo mục tiêu người dùng nói, và bản phác thảo thấy nó; trọng số thêm cho hũ khác thì tối ưu lần hai
    assert args_for(tools, "optimize_allocation") == [
        {"goals": [user_entry]},
        {"goals": [user_entry, {"jar": "du_phong", "weight": 3}]},
    ]
    assert prompt(client)["context"]["user_goal"]["target_vnd"] == 1_000_000_000
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


# --- p5-roadmap-speed: phân bổ trước bản phác thảo, số được nhắc trong lý do, metric của bước, lời kết, sửa bước -----------
def later_phase(*steps):
    """Hai giai đoạn: giai đoạn đầu chỉ có bước xem lại, các bước truyền vào nằm ở giai đoạn sau kỳ lương."""
    draft = outline(review())
    draft["phases"].append({"phase_id": "tich_luy", "title": "Tích lũy dự phòng", "steps": list(steps)})
    return draft


def test_phan_bo_chay_truoc_ban_phac_thao_va_chi_dua_tham_chieu_duong():
    tools = scripted_tools()
    draft = outline(step())
    draft["horizon_months"] = fixture("optimize_allocation.ok.json")["data"]["horizon_months"]  # trùng phương án đã có
    result, client, scope = build(tools, draft)
    assert result.outcome.ok and scope.calls == 1
    # một lần tối ưu (mặc định, không trọng số của model); bản phác thảo đã thấy phương án và bảng tham chiếu
    assert args_for(tools, "optimize_allocation") == [{}]
    context = prompt(client)["context"]
    assert context["allocation"]["lines"]["du_phong"]["proposed_monthly_vnd"] == "1.800.000 ₫"
    refs = context["amount_refs"]
    assert refs["du_phong"]["proposed_increase"] == "600.000 ₫"
    assert refs["giai_tri"]["proposed_decrease"] == "600.000 ₫"
    # chỉ khoản dương: phần thiếu sàn bằng 0, Dự phòng không giảm, Hóa đơn giữ nguyên mức chia
    assert "floor_gap_vnd" not in refs["du_phong"] and "proposed_decrease" not in refs["du_phong"]
    assert "proposed_increase" not in refs["hoa_don"] and "proposed_decrease" not in refs["hoa_don"]
    data = fixture("optimize_allocation.ok.json")["data"]
    for code, fields in refs.items():
        line = next(item for item in data["lines"] if item["jar"]["code"] == code)
        for name in fields:
            if name == "proposed_increase":
                assert line["proposed_monthly_vnd"] > line["current_monthly_vnd"]
            elif name == "proposed_decrease":
                assert line["proposed_monthly_vnd"] < line["current_monthly_vnd"]
            else:
                assert line[name] > 0


def test_ban_phac_thao_xin_phuong_an_khac_toi_uu_lan_hai_hong_thi_giu_phuong_an_mac_dinh(caplog):
    caplog.set_level("WARNING", logger="yofina.agent.roadmap")
    tools = scripted_tools(allocation=("ok", "error_profile_incomplete"))
    draft = outline(step())
    draft["horizon_months"] = 9
    result, _, _ = build(tools, draft)
    assert result.outcome.ok
    assert args_for(tools, "optimize_allocation") == [{}, {"horizon_months": 9}]
    (stored,) = args_for(tools, "save_roadmap")
    assert stored["goals"] == fixture("optimize_allocation.ok.json")["data"]["goals"]
    (failed,) = roadmap_events(caplog, "roadmap_reoptimize_failed")
    assert failed["code"] == ErrorCode.PROFILE_INCOMPLETE


def test_ly_do_chep_so_trong_reason_numbers_khong_can_vong_sua():
    tools = scripted_tools()
    llm, client, _ = make_llm([tool_response("draft_roadmap", outline(review()))])
    settings = agent_settings()
    scope = TurnScope(settings.max_model_calls_per_turn)

    async def call(name, args, target):
        return await tools.call(settings.tool(name, target=target), args)

    run(build_roadmap(call, llm, settings, scope, reason_code="initial"))
    numbers = prompt(client)["reason_numbers"]
    obligation = fixture("get_obligations.ok.json")["data"]["obligations"][0]
    assert "760.000 ₫" in numbers  # số dư hũ Giải trí
    assert "600.000 ₫" in numbers  # tham chiếu của bảng amount_refs
    assert any(text.count("/") == 1 for text in numbers)  # ngày đến hạn dạng dd/mm
    assert not any("%" in text for text in numbers)
    assert obligation["id"] not in json.dumps(numbers)
    # lý do chép nguyên văn một chuỗi trong danh sách thì qua grounding ngay ở bản phác thảo
    reason = f"Hũ Giải trí còn {numbers[numbers.index('760.000 ₫')]}, đủ để chuyển trước kỳ lương"
    tools = scripted_tools()
    result, _, scope = build(tools, outline(step(reason=reason)))
    assert result.outcome.ok and scope.calls == 1
    assert args_for(tools, "save_roadmap")[0]["phases"][0]["steps"][0]["reason"] == reason


def test_metric_chuyen_ngay_la_so_du_hai_hu_khop_so_tien_buoc():
    tools = scripted_tools()
    result, _, _ = build(tools, outline(step()))
    assert result.outcome.ok
    (move,) = args_for(tools, "save_roadmap")[0]["phases"][0]["steps"]
    assert move["amount_vnd"] == 600_000
    # bước làm ngay lấy từ số dư hiện có: Giải trí 760.000 ₫ giảm, Dự phòng 2.700.000 ₫ tăng đúng 600.000 ₫
    assert move["metrics"] == [
        {"label": "Hũ Giải trí", "before": "760.000 ₫", "after": "160.000 ₫"},
        {"label": "Hũ Dự phòng", "before": "2.700.000 ₫", "after": "3.300.000 ₫"},
    ]


# --- bước chuyển làm ngay từ số dư (C3 của báo cáo rà soát #39): trần là số dư trừ khoản hũ nguồn phải trả trước kỳ lương, và phần hũ
# nhận còn thiếu tới đích; không so với phần tăng MỖI THÁNG của phương án tối ưu (luật đó chỉ cho bước theo kỳ lương) ---------------
def test_buoc_chuyen_ngay_lon_hon_phan_tang_moi_thang_ma_vua_so_du_kha_dung_thi_dat():
    # Du lịch chỉ cần thêm 120.000 ₫ mỗi tháng theo phương án, nhưng chuyển ngay 600.000 ₫ từ Giải trí (760.000 ₫, không có khoản phải
    # trả trước kỳ lương) vẫn nằm trong số dư và dưới phần Du lịch còn thiếu tới đích (6.000.000 - 1.800.000 ₫)
    tools = scripted_tools()
    move = step(to_jar_code="du_lich", amount_ref={"jar_code": "giai_tri", "field": "proposed_decrease"})
    result, _, scope = build(tools, outline(move))
    assert result.outcome.ok and scope.calls == 1
    (saved,) = args_for(tools, "save_roadmap")[0]["phases"][0]["steps"]
    assert (saved["to_jar_code"], saved["amount_vnd"]) == ("du_lich", 600_000)
    # cùng bước đó sau kỳ lương là khoản hằng tháng: vẫn so với phần Du lịch cần thêm mỗi tháng
    tools = scripted_tools(checks=("ok", "ok"))
    result, client, _ = build(tools, later_phase(move), later_phase(review()))
    assert result.outcome.ok and "cần thêm" in prompt(client, 1)["feedback"][0]["message"]


def test_buoc_chuyen_ngay_tru_khoan_hu_nguon_phai_tra_truoc_ky_luong(caplog):
    # Hóa đơn có 450.000 ₫ nhưng Tiền điện 375.000 ₫ trả từ hũ này đến hạn 26/11, trước kỳ lương 05/12: chuyển ngay tối đa 75.000 ₫
    caplog.set_level("WARNING", logger="yofina.agent.roadmap")
    tools = scripted_tools()
    move = step(jar_code="hoa_don", to_jar_code="du_lich", amount_ref={"jar_code": "du_lich", "field": "proposed_increase"})
    result, client, scope = build(tools, outline(move, review()), outline(review()))
    assert result.outcome.ok and scope.calls == 2
    source = prompt(client)["context"]["first_phase_sources"]["hoa_don"]
    assert (source["max_text"], source["due_before_payday_text"]) == ("75.000 ₫", "375.000 ₫")
    assert source["refs"] == []  # không tham chiếu nào vừa 75.000 ₫
    (feedback,) = prompt(client, 1)["feedback"]
    assert feedback["rule_id"] == "step_invalid"
    assert all(text in feedback["message"] for text in ("450.000 ₫", "375.000 ₫", "75.000 ₫"))
    (rejected,) = roadmap_events(caplog, "roadmap_step_rejected")
    assert rejected["detail"] == "amount_over_available"


def test_buoc_chuyen_ngay_khong_vuot_phan_hu_nhan_con_thieu_toi_dich(caplog):
    # mục tiêu Du lịch 2.000.000 ₫, hũ đang có 1.800.000 ₫: chuyển ngay 600.000 ₫ vượt đích; 120.000 ₫ thì vừa
    caplog.set_level("WARNING", logger="yofina.agent.roadmap")
    allocation = fixture("optimize_allocation.ok.json")
    allocation["data"]["goals"][0]["target_vnd"] = 2_000_000
    tools = scripted_tools(allocation=allocation, checks=("ok", "ok"))
    over = step(to_jar_code="du_lich", amount_ref={"jar_code": "giai_tri", "field": "proposed_decrease"})
    fits = step(to_jar_code="du_lich", amount_ref={"jar_code": "du_lich", "field": "proposed_increase"})
    result, client, _ = build(tools, outline(over), outline(fits))
    assert result.outcome.ok
    (feedback,) = prompt(client, 1)["feedback"]
    assert "200.000 ₫" in feedback["message"] and "2.000.000 ₫" in feedback["message"]
    (rejected,) = roadmap_events(caplog, "roadmap_step_rejected")
    assert rejected["detail"] == "amount_over_goal_gap"
    assert args_for(tools, "save_roadmap")[0]["phases"][0]["steps"][0]["amount_vnd"] == 120_000


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        # phần tăng: phân bổ hằng tháng của chính hũ được tham chiếu, chênh lệch đúng bằng số tiền bước
        (
            {"jar_code": "du_phong", "field": "proposed_increase"},
            [{"label": "Phân bổ hằng tháng hũ Dự phòng", "before": "1.200.000 ₫", "after": "1.800.000 ₫"}],
        ),
        (
            {"jar_code": "giai_tri", "field": "proposed_decrease"},
            [{"label": "Phân bổ hằng tháng hũ Giải trí", "before": "1.200.000 ₫", "after": "600.000 ₫"}],
        ),
    ],
)  # fmt: skip
def test_metric_buoc_sau_ky_luong_noi_dung_hu_va_dung_so(ref, expected):
    tools = scripted_tools(checks=("ok", "ok"))
    result, _, _ = build(tools, later_phase(step(amount_ref=ref)))
    assert result.outcome.ok
    later = args_for(tools, "save_roadmap")[0]["phases"][1]["steps"][0]
    assert later.get("metrics") == expected
    if expected:
        before, after = (int(expected[0][k].replace(".", "").split()[0]) for k in ("before", "after"))
        assert abs(after - before) == later["amount_vnd"]


def test_metric_adjust_split_phan_tang_la_so_tien_buoc():
    # số tiền của bước đổi tỷ lệ chia là phần THAY ĐỔI của hũ (120.000 ₫), mức chia mới (1.320.000 ₫) là "sau" của metric
    tools = scripted_tools(checks=("ok", "ok"))
    split = review(
        step_id="tang_chia", kind="adjust_split", jar_code="du_lich", action=None,
        amount_ref={"jar_code": "du_lich", "field": "proposed_increase"},
    )  # fmt: skip
    result, _, _ = build(tools, later_phase(split))
    assert result.outcome.ok
    later = args_for(tools, "save_roadmap")[0]["phases"][1]["steps"][0]
    assert later["amount_vnd"] == 120_000
    assert later["metrics"] == [
        {"label": "Phân bổ hằng tháng hũ Du lịch", "before": "1.200.000 ₫", "after": "1.320.000 ₫"}
    ]


@pytest.mark.parametrize(
    ("bad", "fixed", "amount"),
    [
        # bước đổi tỷ lệ chia lấy MỨC chia mới làm số tiền (cảnh 4 trên app: 5.358.067 ₫ "dồn" vào Ăn uống, #19): vượt phần hũ cần thêm
        (
            review(step_id="tang_chia", kind="adjust_split", jar_code="du_lich", action=None,
                   amount_ref={"jar_code": "du_lich", "field": "proposed_monthly_vnd"}),
            review(step_id="tang_chia", kind="adjust_split", jar_code="du_lich", action=None,
                   amount_ref={"jar_code": "du_lich", "field": "proposed_increase"}),
            120_000,
        ),
        # bước chuyển tiền sau kỳ lương theo mức chia mới hay mức hiện tại của hũ nhận: không phải khoản hũ nhận cần thêm
        (step(amount_ref={"jar_code": "du_phong", "field": "proposed_monthly_vnd"}), step(), 600_000),
        (step(amount_ref={"jar_code": "du_phong", "field": "current_monthly_vnd"}), step(), 600_000),
        # phần GIẢM của hũ nhận dùng làm khoản chuyển vào nó (Đi lại được đề xuất giảm, không cần thêm)
        (
            step(to_jar_code="di_lai", amount_ref={"jar_code": "di_lai", "field": "proposed_decrease"}),
            step(),
            600_000,
        ),
    ],
)  # fmt: skip
def test_so_tien_buoc_vuot_phan_hu_nhan_can_them_vao_vong_sua(bad, fixed, amount, caplog):
    caplog.set_level("WARNING", logger="yofina.agent.roadmap")
    tools = scripted_tools(checks=("ok", "ok", "ok"))
    result, client, scope = build(tools, later_phase(bad), later_phase(fixed))
    assert result.outcome.ok and scope.calls == 2
    (feedback,) = prompt(client, 1)["feedback"]
    assert feedback["rule_id"] == "step_invalid" and "cần thêm" in feedback["message"]
    (rejected,) = roadmap_events(caplog, "roadmap_step_rejected")
    assert rejected["detail"] == "amount_over_need"
    later = args_for(tools, "save_roadmap")[0]["phases"][1]["steps"][0]
    assert later["amount_vnd"] == amount


def test_buoc_chuyen_sau_ky_luong_khong_vuot_khoan_hu_nguon_nhan_moi_thang(caplog):
    # sau kỳ lương khoản hằng tháng lấy từ phần lương chảy vào hũ nguồn: hũ nguồn Đi lại chỉ nhận 300.000 ₫ mỗi tháng, ít hơn khoản
    # 600.000 ₫ Dự phòng cần thêm, nên bước bị đưa vào vòng sửa (luật source_jar_covers chỉ so với cả thu nhập tháng)
    caplog.set_level("WARNING", logger="yofina.agent.roadmap")
    allocation = fixture("optimize_allocation.ok.json")
    for line in allocation["data"]["lines"]:
        if line["jar"]["code"] == "di_lai":
            line["current_monthly_vnd"] = 300_000  # nhận ít hơn phần Dự phòng cần thêm (600.000 ₫)
    tools = scripted_tools(allocation=allocation, checks=("ok", "ok", "ok"))
    bad = step(jar_code="di_lai", action=None)
    result, client, _ = build(tools, later_phase(bad), later_phase(step()))
    assert result.outcome.ok
    (feedback,) = prompt(client, 1)["feedback"]
    assert "nhận mỗi tháng" in feedback["message"]
    (rejected,) = roadmap_events(caplog, "roadmap_step_rejected")
    assert rejected["detail"] == "amount_over_source"


# --- sàn của hũ có khoản định kỳ trả từ chính nó (#39, 26/11): bước không đưa phần chia mỗi tháng của hũ xuống dưới sàn ----------
def allocation_with(changes):
    """optimize_allocation.ok.json với vài trường của dòng phân bổ đổi theo hũ (mã hũ -> trường -> giá trị)."""
    allocation = fixture("optimize_allocation.ok.json")
    for line in allocation["data"]["lines"]:
        line.update(changes.get(line["jar"]["code"], {}))
    return allocation


def cut(field, **changes):
    return review(
        step_id="giam_giai_tri", kind="cut_spending", jar_code="giai_tri", action=None,
        amount_ref={"jar_code": "giai_tri", "field": field}, **changes,
    )  # fmt: skip


def split_of(code, field):
    return review(
        step_id="doi_ti_le", kind="adjust_split", jar_code=code, action=None,
        amount_ref={"jar_code": code, "field": field},
    )  # fmt: skip


@pytest.mark.parametrize(
    ("lines", "bad", "fixed", "amount"),
    [
        # Giải trí trả Netflix (sàn 180.000 ₫, hũ vẫn không thiết yếu): giảm chi CẢ khoản đang nhận (1.200.000 ₫) làm Giải trí còn 0
        ({"giai_tri": {"floor_vnd": 180_000}}, cut("current_monthly_vnd"), cut("proposed_decrease"), 600_000),
        # sau kỳ lương chuyển 600.000 ₫ mỗi tháng từ Giải trí (sàn 700.000 ₫) sang Dự phòng: Giải trí còn 600.000 ₫, dưới sàn
        (
            {"giai_tri": {"floor_vnd": 700_000}},
            step(),
            step(to_jar_code="du_lich", amount_ref={"jar_code": "du_lich", "field": "proposed_increase"}),
            120_000,
        ),
        # giảm phần chia của Giải trí theo phần giảm của bộ tối ưu (600.000 ₫), mà mức đề xuất đã dưới sàn 700.000 ₫ của hũ
        (
            {"giai_tri": {"floor_vnd": 700_000}},
            split_of("giai_tri", "proposed_decrease"),
            split_of("du_lich", "proposed_increase"),
            120_000,
        ),
    ],
)  # fmt: skip
def test_buoc_dua_phan_chia_cua_hu_xuong_duoi_san_vao_vong_sua(lines, bad, fixed, amount, caplog):
    caplog.set_level("WARNING", logger="yofina.agent.roadmap")
    tools = scripted_tools(allocation=allocation_with(lines), checks=("ok", "ok", "ok"))
    result, client, scope = build(tools, later_phase(bad), later_phase(fixed))
    assert result.outcome.ok and scope.calls == 2
    (feedback,) = prompt(client, 1)["feedback"]
    assert feedback["rule_id"] == "step_invalid" and "dưới sàn" in feedback["message"]
    # sàn của dòng là sàn CỨNG (khoản định kỳ trả từ hũ, chi thiết yếu); sàn chi theo mức chi thật gần đây không còn chặn bước (C3, #39)
    assert "Giải trí" in feedback["message"] and "chi thiết yếu" in feedback["message"]
    assert "mức chi thật gần đây" not in feedback["message"]
    (rejected,) = roadmap_events(caplog, "roadmap_step_rejected")
    assert rejected["detail"] == "amount_below_floor"
    later = args_for(tools, "save_roadmap")[0]["phases"][1]["steps"][0]
    assert later["amount_vnd"] == amount


def test_buoc_giam_toi_dung_san_van_dat():
    # Giải trí còn đúng bằng sàn sau bước (1.200.000 - 600.000 = 600.000 ₫): không vào vòng sửa
    tools = scripted_tools(allocation=allocation_with({"giai_tri": {"floor_vnd": 600_000}}), checks=("ok", "ok"))
    result, _, scope = build(tools, later_phase(cut("proposed_decrease")))
    assert result.outcome.ok and scope.calls == 1
    assert args_for(tools, "save_roadmap")[0]["phases"][1]["steps"][0]["amount_vnd"] == 600_000


#: mức chi thật gần đây của hũ Giải trí trong phương án (dữ kiện `recent_spend` của dòng phân bổ, #39)
RECENT_GIAI_TRI = {
    "giai_tri": {
        "floor_vnd": 180_000,
        "recent_spend": {
            "recent_monthly_vnd": 1_400_000, "keep_floor_vnd": 700_000, "baseline_monthly_vnd": 600_000, "unusually_high": True,
        },
    }
}  # fmt: skip


def test_san_chi_goi_y_la_du_kien_trong_ngu_canh_khong_chan_buoc():
    """Sàn chi theo mức chi thật gần đây là sàn MỀM (C3 của báo cáo rà soát #39): bước giảm chi đưa Giải trí còn 600.000 ₫ mỗi tháng, dưới
    mức nên giữ 700.000 ₫ nhưng trên sàn cứng (Netflix 180.000 ₫), vẫn được lưu mà không vào vòng sửa. Model thấy mức chi thật, mức nên
    giữ, mức nền dài hơn và cờ chi gần đây cao bất thường (C5) để nói trong lý do hoặc hỏi lại; các số đó dùng được trong lý do."""
    tools = scripted_tools(allocation=allocation_with(RECENT_GIAI_TRI), checks=("ok", "ok"))
    result, client, scope = build(tools, later_phase(cut("proposed_decrease")))
    assert result.outcome.ok and scope.calls == 1
    assert args_for(tools, "save_roadmap")[0]["phases"][1]["steps"][0]["amount_vnd"] == 600_000
    line = prompt(client)["context"]["allocation"]["lines"]["giai_tri"]
    assert line["floor_vnd"] == "180.000 ₫"
    assert (line["recent_spend_text"], line["keep_floor_text"], line["baseline_spend_text"]) == (
        "1.400.000 ₫", "700.000 ₫", "600.000 ₫",
    )  # fmt: skip
    assert line["recent_spend_unusually_high"] is True
    assert {"1.400.000 ₫", "700.000 ₫"} <= set(prompt(client)["reason_numbers"])
    # hũ không có dữ kiện chi gần đây (hũ để dành) không có các khóa đó
    assert "recent_spend_text" not in prompt(client)["context"]["allocation"]["lines"]["du_phong"]


def test_save_jars_dua_hu_xuong_duoi_san_vao_vong_sua():
    # tỷ lệ đề xuất cắt Giải trí từ 1.200.000 xuống 600.000 ₫ mỗi tháng mà sàn của hũ là 700.000 ₫: không áp tỷ lệ đó
    lines = {"giai_tri": {"floor_vnd": 700_000}}
    tools = scripted_tools(allocation=allocation_with(lines), get_jar_balances=goal_balances(), checks=("ok", "ok"))
    split = review(kind="adjust_split", action="save_jars")
    fixed = split_of("du_lich", "proposed_increase")
    result, client, _ = build(tools, outline(split), outline(fixed))
    assert result.outcome.ok
    (feedback,) = prompt(client, 1)["feedback"]
    assert "save_jars" in feedback["message"] and "dưới sàn" in feedback["message"] and "Giải trí" in feedback["message"]
    assert "action" not in args_for(tools, "save_roadmap")[0]["phases"][0]["steps"][0]


def test_log_thoi_luong_tung_chang(caplog):
    caplog.set_level("INFO", logger="yofina.agent.roadmap")
    tools = scripted_tools(checks=("violation", "ok"))
    fixed = step(to_jar_code="du_lich", amount_ref={"jar_code": "du_lich", "field": "proposed_increase"})
    result, _, _ = build(tools, outline(step()), outline(fixed))
    assert result.outcome.ok
    stages = roadmap_events(caplog, "roadmap_stage")
    assert [item["stage"] for item in stages] == [
        "context", "draft", "allocate", "suitability", "repair", "suitability", "save", "total",
    ]  # fmt: skip
    assert all(isinstance(item["ms"], int) and item["ms"] >= 0 for item in stages)
    assert stages[1]["attempts"] == 1 and stages[2]["reoptimized"] is False
    assert [item.get("round") for item in stages if item["stage"] in ("suitability", "repair")] == [0, 1, 1]
    assert stages[-1]["planner_calls"] == 2 and stages[-1]["rounds"] == 1 and stages[-1]["saved"] is True
    logged = "\n".join(json.dumps(item, ensure_ascii=False) for item in stages)
    assert "₫" not in logged and "Bù hũ" not in logged


def edit_turn(monkeypatch, question, *, active="ok", amount_vnd=None, writer=None, usage=None):
    """Lượt "sửa một bước": router trả roadmap_action="edit_step" (ý định phụ có cấu trúc, không đoán bằng regex trên chữ)."""
    tools = scripted_tools(latest=(active,))
    routed = route_response(intent="roadmap", roadmap_action="edit_step", amount_vnd=amount_vnd)
    llm = make_llm([routed], usage) if usage is not None else make_llm([routed])
    events, _, writer = run_turn(question, llm=llm, tools=tools, monkeypatch=monkeypatch, writer=writer)
    check_agui_order(events)
    assert args_for(tools, "get_roadmap") == [{"which": "active"}]
    assert not args_for(tools, "save_roadmap") and not args_for(tools, "optimize_allocation")
    return events, writer


def test_sua_mot_buoc_writer_chi_ra_buoc_tu_ban_gon_va_cho_sua(monkeypatch):
    said = "Bước “Bù 100.000 ₫ mỗi tuần cho Ăn uống” chưa đổi; bạn mở trang Lộ trình và bấm Sửa để đặt 80.000 ₫."
    events, writer = edit_turn(
        monkeypatch, "Đổi khoản bù cho Ăn uống còn 80 nghìn thôi", amount_vnd=80_000, writer=FakeWriter(said)
    )
    (block,) = blocks_of(events)
    assert block["type"] == "roadmap" and block["data"]["status"] == "active"
    (call,) = writer.calls
    facts = call["compact"]
    assert call["task"] == "roadmap_step_edit" and facts["sua_trong_chat"] is False
    assert facts["cach_sua"] == notices.ROADMAP_EDIT_HOW and facts["so_tien_moi_text"] == "80.000 ₫"
    assert facts["version"] == 2 and len(facts["steps"]) == sum(len(ph["steps"]) for ph in block["data"]["phases"])
    first = facts["steps"][0]
    step0 = block["data"]["phases"][0]["steps"][0]
    assert first["title"] == step0["title"] and first["phase"] == block["data"]["phases"][0]["title"]
    assert "amount_vnd" not in first and first.get("amount_text", "").endswith("₫")
    assert {first.get("from_jar"), first.get("to_jar")} & {"Ăn uống", "Giải trí", "Nghĩa vụ", "Dự phòng", "Du lịch"}
    assert texts_of(events) == [said]


def test_sua_buoc_writer_viet_so_khong_can_cu_thi_chi_noi_cho_sua(monkeypatch):
    events, _ = edit_turn(monkeypatch, "Bỏ bớt khoản giữ cho hũ Giải trí", writer=FakeWriter("Mình đã giảm còn 15.000 ₫ rồi."))
    assert texts_of(events) == [notices.ROADMAP_EDIT_HOW]
    assert "đã sửa" not in notices.ROADMAP_EDIT_HOW and "chưa đổi gì" in notices.ROADMAP_EDIT_HOW


def test_sua_buoc_khi_het_luot_model_van_noi_cho_sua(monkeypatch):
    usage = FakeUsage(caps_hit={"m-small-a", "m-small-b"})
    tools = scripted_tools(latest=("ok",))
    # model hết lượt: luật dự phòng không có ý định phụ, nên không vào đường sửa bước; lượt xem lộ trình vẫn có thẻ
    events, _, writer = run_turn(
        "Sửa bước 3 của lộ trình giúp mình", llm=make_llm([], usage), tools=tools, monkeypatch=monkeypatch
    )
    assert not writer.calls and "roadmap" in [b["type"] for b in blocks_of(events)]


def test_sua_buoc_khi_chua_co_lo_trinh_khong_lap_moi(monkeypatch):
    events, writer = edit_turn(monkeypatch, "Sửa bước để dành cho hũ Dự phòng", active="error_not_found")
    assert texts_of(events) == [notices.ROADMAP_EDIT_NO_ROADMAP]
    assert not blocks_of(events) and not writer.calls


def test_router_xem_lo_trinh_thi_khong_vao_duong_sua_du_cau_co_chu_buoc(monkeypatch):
    # trước đây regex trên chữ ("bước" + động từ sửa) ép vào đường sửa bước; nay chỉ tham số router quyết định
    tools = scripted_tools(latest=("ok",))
    llm = make_llm([route_response(intent="roadmap", roadmap_action="view")])
    _, _, writer = run_turn("Sửa bước 3 giúp mình", llm=llm, tools=tools, monkeypatch=monkeypatch)
    assert [c["task"] for c in writer.calls] == ["roadmap"]


def test_buoc_bi_loai_ma_phan_con_lai_du_khuon_thi_luu_khong_them_vong_sua(caplog):
    caplog.set_level("INFO", logger="yofina.agent.roadmap")
    draft = six_distinct_steps()
    draft["phases"][0]["steps"][0]["reason"] = "Dành 917.123 ₫ cho quỹ"  # số không căn cứ: bước này bị loại
    tools = scripted_tools(checks=("ok",) * 6)
    result, client, scope = build(tools, draft)
    assert result.outcome.ok and scope.calls == len(client.calls) == 1
    (stored,) = args_for(tools, "save_roadmap")
    kept = [s["step_id"] for p in stored["phases"] for s in p["steps"]]
    assert "chuyen_du_phong" not in kept and len(kept) == 5 and len(stored["phases"]) == 3
    (skipped,) = roadmap_events(caplog, "roadmap_repair_skipped")
    assert skipped["kept_steps"] == 5 and skipped["kept_phases"] == 3 and skipped["dropped"] == 1
    # ngưỡng 0: luôn sửa như trước
    tools = scripted_tools(checks=("ok",) * 6)
    settings = agent_settings(roadmap_accept_min_phases=0)
    fixed = six_distinct_steps()
    result, client, scope = build(tools, draft, fixed, settings=settings)
    assert result.outcome.ok and scope.calls == 2
    assert prompt(client, 1)["feedback"][0]["rule_id"] == "numeric_grounding"


def test_con_it_buoc_hon_khuon_thi_van_sua():
    # chỉ còn một giai đoạn, ba bước sau khi loại: chưa đủ khuôn nên vẫn vào vòng sửa
    draft = six_distinct_steps()
    draft["phases"] = draft["phases"][:2]
    draft["phases"][1]["title"] = "Sau 17 ngày"  # tiêu đề có số không căn cứ: cả giai đoạn bị loại
    tools = scripted_tools(checks=("ok",) * 6)
    result, client, scope = build(tools, draft, six_distinct_steps())
    assert result.outcome.ok and scope.calls == 2
    assert prompt(client, 1)["feedback"][0]["rule_id"] == "numeric_grounding"


def test_trong_so_mac_dinh_khong_toi_uu_lai():
    tools = scripted_tools(get_jar_balances=goal_balances())
    draft = outline(review())
    draft["goals"] = [{"jar": "du_lich", "weight": 1}, {"jar": "du_phong", "weight": 1.0}]
    result, _, _ = build(tools, draft)
    assert result.outcome.ok
    assert args_for(tools, "optimize_allocation") == [{}]


def test_nguon_giai_doan_dau_va_han_muc_tieu_dang_nguoi_doc():
    tools = scripted_tools(get_jar_balances=goal_balances())
    result, client, _ = build(tools, outline(review()))
    assert result.outcome.ok
    context = prompt(client)["context"]
    sources = context["first_phase_sources"]
    # Giải trí còn 760.000 ₫: chỉ các tham chiếu không vượt số dư đó
    assert sources["giai_tri"]["max_text"] == "760.000 ₫"
    assert {"giai_tri.proposed_decrease", "du_phong.proposed_increase"} <= set(sources["giai_tri"]["refs"])
    assert "du_phong.proposed_monthly_vnd" not in sources["giai_tri"]["refs"]  # 1.800.000 ₫
    lines = {line["jar"]["code"]: line for line in fixture("optimize_allocation.ok.json")["data"]["lines"]}
    balances = {jar["code"]: jar["balance_vnd"] for jar in context["jars"]}
    for code, entry in sources.items():
        for ref in entry["refs"]:
            jar, field = ref.split(".")
            line = lines[jar]
            value = {
                "proposed_increase": line["proposed_monthly_vnd"] - line["current_monthly_vnd"],
                "proposed_decrease": line["current_monthly_vnd"] - line["proposed_monthly_vnd"],
            }.get(field, line.get(field))
            assert 0 < value <= balances[code]
    du_lich = next(jar for jar in context["jars"] if jar["code"] == "du_lich")
    assert du_lich["goal_date_text"] == "31/03/2027"
    assert "31/03/2027" in prompt(client)["reason_numbers"]


def test_muc_tieu_trong_phuong_an_va_co_chua_co_han_trong_ngu_canh():
    """Mục tiêu của phương án vào ngữ cảnh lập lộ trình: đích, hạn, kịp hay không, mức cần mỗi tháng (V2 của báo cáo rà soát #39). Mục tiêu
    không có hạn mang cờ có cấu trúc `no_deadline` (bộ tối ưu không đặt mức cần) để model không nói kịp hay trễ hạn và có thể nhắc
    người dùng chọn hạn."""
    tools = scripted_tools()
    result, client, _ = build(tools, outline(review()))
    assert result.outcome.ok
    assert prompt(client)["context"]["allocation"]["goals"] == [
        {
            "jar_code": "du_lich", "target_text": "6.000.000 ₫", "target_date_text": "31/03/2027", "on_track": True,
            "monthly_needed_text": "1.150.000 ₫", "projected_date_text": "24/03/2027",
        }
    ]  # fmt: skip
    allocation = fixture("optimize_allocation.ok.json")
    goal = allocation["data"]["goals"][0]
    del goal["target_date"]
    goal["monthly_needed_vnd"] = 0
    tools = scripted_tools(allocation=allocation)
    result, client, _ = build(tools, outline(review()))
    assert result.outcome.ok
    assert prompt(client)["context"]["allocation"]["goals"] == [
        {"jar_code": "du_lich", "target_text": "6.000.000 ₫", "no_deadline": True, "on_track": True, "projected_date_text": "24/03/2027"}
    ]


def test_metric_buoc_chuyen_sau_ky_luong_theo_phan_tang_cua_hu_nhan():
    tools = scripted_tools(checks=("ok", "ok"))
    result, _, _ = build(tools, later_phase(step()))
    assert result.outcome.ok
    later = args_for(tools, "save_roadmap")[0]["phases"][1]["steps"][0]
    assert later["amount_vnd"] == 600_000
    assert later["metrics"] == [
        {"label": "Phân bổ hằng tháng hũ Dự phòng", "before": "1.200.000 ₫", "after": "1.800.000 ₫"}
    ]


@pytest.mark.parametrize(
    ("status", "feasibility", "active", "expected"),
    [
        (
            "active", "relaxed", None,
            "Đây là lộ trình bạn đang dùng, phiên bản 3 (1 giai đoạn, 1 bước). Mục tiêu chỉ kịp sau khi nới hạn hoặc mức,"
            " chi tiết ở thẻ. Bước tiếp theo: mở trang Lộ trình để chấp nhận, sửa hoặc từ chối từng bước.",
        ),
        (
            "proposed", "on_track", 2,
            "Đây là bản đề xuất phiên bản 3 (1 giai đoạn, 1 bước), chưa thay lộ trình bạn đang dùng. Bản đang dùng vẫn là"
            " phiên bản 2. Theo phương án phân bổ đề xuất, mục tiêu kịp hạn. Bước tiếp theo: bấm So với bản đang dùng trên"
            " thẻ, rồi chọn Dùng bản mới hoặc Giữ bản cũ.",
        ),
    ],
)  # fmt: skip
def test_loi_ket_dung_bang_ma(status, feasibility, active, expected):
    from yofina_agent.turn import _roadmap_closing

    data = fixture("save_roadmap.ok.json")["data"]
    data.update(status=status, feasibility=feasibility, alternatives=[])
    data["phases"] = data["phases"][:1]
    data["phases"][0]["steps"] = data["phases"][0]["steps"][:1]
    first = data["phases"][0]["steps"][0]["status"]
    data["counts"] = {"pending": 0, "accepted": 0, "rejected": 0, first: 1}
    assert _roadmap_closing(B.RoadmapData.model_validate(data), active, None) == expected
