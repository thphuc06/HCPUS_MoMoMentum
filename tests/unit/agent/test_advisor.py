"""Luồng K của phase 6 (agent như người tư vấn), phía what-if: Analyst trả lập luận có cấu trúc và một câu kết luận trong CHÍNH lời
gọi đã có; mã kiểm số, căn cứ và đích của kết luận rồi phát dần khối `reasoning` trước khối `options`. Model, tool và bộ nhớ là đồ giả.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from agent_helpers import (
    FakeGuardrailClient,
    FakeTools,
    blocks_of,
    check_agui_order,
    fixture,
    make_guardrail,
    make_llm,
    mcp_ok,
    route_response,
    run_turn,
    tool_response,
    types,
)
from test_memory_wiring import raw_prompt, run_with_memory, travel_client
from test_roadmap_agent import build, outline, review, scripted_tools, step
from test_whatif import (
    ROUTE_WHAT_IF,
    SCENARIO,
    WHAT_IF_Q,
    analysis,
    block_types,
    result_of,
    text_of,
    what_if_llm,
)
from test_whatif_switch_jar import _analysis, _options, _run
from yofina_agent import advisor
from yofina_agent.schemas import Analysis
from yofina_agent.tools import ToolKind, ToolOutcome, classify_result
from yofina_agent.whatif import ANALYST_SYSTEM

from yofina_core import blocks as B
from yofina_core.suitability import SuitabilityVerdict

REPO = Path(__file__).resolve().parents[3]

#: bước có số đúng của lượt (run_scenario: 2.200.000 ₫ phải trả, hũ có 1.050.000 ₫)
STEP_SCENARIO = {
    "seen": "Ngày 05/12 hũ Nghĩa vụ phải trả 2.200.000 ₫ nhưng chỉ có 1.050.000 ₫.",
    "why": "Thiếu tiền đúng hạn thì khoản Trả sau dễ bị trễ.",
    "effect": "Mua ngay bằng Trả sau không an toàn.",
    "basis": ["tool:run_scenario", "tool:get_obligations"],
}
#: bước dựa vào luật đã kiểm (obligation_to_income: pass trong fixture check_suitability.ok)
STEP_RULE = {
    "seen": "Nghĩa vụ hằng tháng sẽ vượt mức nên giữ so với thu nhập.",
    "why": "Thêm khoản trả góp làm mỗi kỳ lương nặng hơn.",
    "effect": "Không nên vay thêm cho món không thiết yếu.",
    "basis": ["rule:obligation_to_income", "rule:no_borrow_to_spend"],
}
#: bước có số KHÔNG có trong kết quả tool của lượt
STEP_UNGROUNDED = {
    "seen": "Bạn sẽ thiếu 1.350.000 ₫ vào ngày đến hạn.",
    "why": "Thiếu tiền thì bị phạt.",
    "effect": "Nên hoãn.",
    "basis": ["tool:run_scenario"],
}
#: bước dựa vào thói quen của hồ sơ hành vi (46% chi trong 7 ngày đầu sau lương: số của chính hồ sơ)
STEP_BEHAVIOR = {
    "seen": "Bạn thường chi 46% của cả kỳ trong 7 ngày đầu sau ngày lương.",
    "why": "Mua đúng lúc lương về thì hũ dễ cạn sớm.",
    "effect": "Hoãn tới sau kỳ lương và để dành dần thì nhẹ hơn.",
    "basis": ["tool:get_behavior_profile"],
}
CONCLUSION = {
    "text": "Bạn nên hoãn mua tới sau 05/12 vì hũ Nghĩa vụ đang hụt 1.150.000 ₫ và tuần đầu sau lương bạn thường chi nhiều.",
    "option_id": "defer",
    "personal": ["behavior"],
}


def advised(
    steps: list[dict[str, Any]] | None = None,
    conclusion: dict[str, Any] | None = CONCLUSION,
    **kw: Any,
) -> dict[str, Any]:
    out = analysis(**kw)
    out["reasoning"] = [STEP_SCENARIO, STEP_RULE] if steps is None else steps
    if conclusion is not None:
        out["conclusion"] = conclusion
    return out


def reasoning_blocks(events: list[Any]) -> list[dict[str, Any]]:
    return [b for b in blocks_of(events) if b["type"] == "reasoning"]


def final_reasoning(events: list[Any]) -> dict[str, Any]:
    *_, last = reasoning_blocks(events)
    return last


def analyst_call(llm: Any) -> dict[str, Any]:
    return llm[1].calls[2]


# --- đường chính ---------------------------------------------------------------------------------------------------------
def test_lap_luan_phat_dan_truoc_phuong_an_va_khong_them_luot_goi_model(monkeypatch):
    llm = what_if_llm(tool_response("analyze", advised([STEP_SCENARIO, STEP_RULE, STEP_BEHAVIOR])))
    events, tools, _ = run_turn(WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch)
    check_agui_order(events)
    # khối số liệu -> lập luận (phát dần, cùng id) -> phương án -> khối xác nhận; chữ sau cùng
    assert block_types(events) == [
        "forecast_timeline", "obligation_impact", "reasoning", "reasoning", "reasoning", "options", "confirm",
    ]  # fmt: skip
    snaps = reasoning_blocks(events)
    assert len({b["id"] for b in snaps}) == 1 and snaps[0]["id"].startswith("reasoning:")
    assert [len(b["data"]["steps"]) for b in snaps] == [1, 2, 3]
    assert [b["data"]["complete"] for b in snaps] == [False, False, True]
    assert all("conclusion" not in b["data"] for b in snaps[:-1])
    final = snaps[-1]["data"]
    assert [s["step_id"] for s in final["steps"]] == ["s1", "s2", "s3"]
    assert final["steps"][0]["basis"] == [
        {"kind": "tool", "ref": "run_scenario", "label": "Kết quả mô phỏng"},
        {"kind": "tool", "ref": "get_obligations", "label": "Các khoản đến hạn"},
    ]
    # nhãn luật lấy từ kết quả check_suitability của chính lượt
    assert final["steps"][1]["basis"][0] == {
        "kind": "rule",
        "ref": "obligation_to_income",
        "label": "Nghĩa vụ trên thu nhập",
    }
    assert final["conclusion"] == {
        "text": CONCLUSION["text"],
        "option_id": "defer",
        "personal": ["behavior"],
    }
    # fallback_text do mã dựng, không chép chữ của model
    assert (
        CONCLUSION["text"] not in snaps[-1]["fallback_text"]
        and "3 điều" in snaps[-1]["fallback_text"]
    )
    assert text_of(events).startswith("Nếu mua tai nghe")
    r = result_of(events)
    assert (
        r["model_calls"] == 3 and r["degraded"] is False
    )  # router, Orchestrator, Analyst: không lượt gọi nào thêm
    # thói quen đọc bằng tool đọc có sẵn, song song với kế hoạch, trước run_scenario xong
    assert ("get_behavior_profile", {}) in tools.calls
    for b in snaps:
        B.parse_block(b)


def test_buoc_co_so_khong_can_cu_bi_loai_buoc_khac_van_giu(monkeypatch):
    llm = what_if_llm(tool_response("analyze", advised([STEP_UNGROUNDED, STEP_SCENARIO])))
    events, _, _ = run_turn(WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch)
    final = final_reasoning(events)["data"]
    assert [s["seen"] for s in final["steps"]] == [STEP_SCENARIO["seen"]]
    assert final["steps"][0]["step_id"] == "s1"  # đánh lại số sau khi bỏ
    assert "1.350.000" not in json.dumps(reasoning_blocks(events), ensure_ascii=False)
    # bước bị bỏ không làm Analyst phải sửa lại (không tốn lượt gọi model) và không làm lượt suy giảm
    r = result_of(events)
    assert r["model_calls"] == 3 and r["verifier_rounds"] == 1 and r["degraded"] is False


def test_can_cu_khong_co_that_trong_luot_thi_bo_buoc(monkeypatch):
    fake_tool = {
        **STEP_SCENARIO,
        "basis": ["tool:get_forecast"],
    }  # kịch bản Trả sau không nêu hũ: lượt không gọi get_forecast
    skipped_rule = {
        **STEP_RULE,
        "basis": ["rule:risk_within_tolerance"],
    }  # luật bị `skipped` trong mọi phán quyết
    mixed = {**STEP_RULE, "basis": ["rule:risk_within_tolerance", "rule:obligation_to_income"]}
    llm = what_if_llm(tool_response("analyze", advised([fake_tool, skipped_rule, mixed])))
    events, tools, _ = run_turn(WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch)
    assert "get_forecast" not in [n for n, _ in tools.calls]
    final = final_reasoning(events)["data"]
    assert len(final["steps"]) == 1
    assert [b["ref"] for b in final["steps"][0]["basis"]] == [
        "obligation_to_income"
    ]  # căn cứ sai bị bỏ, căn cứ đúng giữ


@pytest.mark.parametrize(
    "conclusion",
    [
        {**CONCLUSION, "option_id": "cover"},  # không phải phương án mang nhãn Gợi ý
        {**CONCLUSION, "text": "Bạn nên hoãn vì sẽ thiếu 1.350.000 ₫."},  # số không có căn cứ
        {**CONCLUSION, "personal": ["memory"]},  # lượt không có bộ nhớ
    ],
    ids=["khong_phai_goi_y", "so_khong_can_cu", "gan_bo_nho_khong_co"],
)
def test_ket_luan_sai_bi_bo_lap_luan_van_giu(monkeypatch, conclusion):
    llm = what_if_llm(tool_response("analyze", advised(conclusion=conclusion)))
    events, _, _ = run_turn(WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch)
    final = final_reasoning(events)["data"]
    assert "conclusion" not in final and final["complete"] is True and len(final["steps"]) == 2
    assert "options" in block_types(events)


def test_ket_luan_gan_thoi_quen_khi_ho_so_chua_san_sang_thi_bo(monkeypatch):
    not_ready = classify_result("x", mcp_ok(fixture("get_behavior_profile.ok_chua_san_sang.json")))
    tools = FakeTools({"get_behavior_profile": lambda a: not_ready})
    llm = what_if_llm(tool_response("analyze", advised([STEP_SCENARIO])))
    events, _, _ = run_turn(WHAT_IF_Q, llm=llm, tools=tools, monkeypatch=monkeypatch)
    assert "conclusion" not in final_reasoning(events)["data"]
    prompt = raw_prompt(analyst_call(llm))
    assert '"behavior"' not in prompt.split("<du_lieu>", 1)[1].split("</du_lieu>", 1)[0]


def test_ket_luan_theo_bo_nho_khi_luot_co_bo_nho(monkeypatch):
    conclusion = {
        **CONCLUSION,
        "text": "Bạn nên hoãn mua tới sau 05/12 để giữ nguyên hũ Du lịch như bạn đã dặn.",
        "personal": ["memory"],
    }
    script = [
        route_response(**ROUTE_WHAT_IF),
        tool_response("plan_scenario", SCENARIO),
        tool_response("analyze", advised(conclusion=conclusion)),
    ]
    events, _, _, bedrock = run_with_memory(WHAT_IF_Q, script, travel_client(), monkeypatch)
    final = final_reasoning(events)["data"]
    assert final["conclusion"]["personal"] == ["memory"]
    # chỉ dẫn ghi `memory` vào personal đi cùng khối bộ nhớ, không nằm trong system prompt
    assert (
        "memory vào personal" in raw_prompt(bedrock.calls[2])
        and "memory vào personal" not in ANALYST_SYSTEM
    )


def test_khong_co_lap_luan_thi_luot_chay_nhu_cu(monkeypatch):
    llm = what_if_llm(tool_response("analyze", analysis()))
    events, _, _ = run_turn(WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch)
    assert block_types(events) == ["forecast_timeline", "obligation_impact", "options", "confirm"]
    assert text_of(events).startswith("Nếu mua tai nghe") and result_of(events)["degraded"] is False


def test_moi_buoc_deu_bi_bo_va_khong_ket_luan_thi_khong_co_khoi(monkeypatch):
    llm = what_if_llm(tool_response("analyze", advised([STEP_UNGROUNDED], conclusion=None)))
    events, _, _ = run_turn(WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch)
    assert reasoning_blocks(events) == []
    assert block_types(events) == ["forecast_timeline", "obligation_impact", "options", "confirm"]


def test_chi_con_ket_luan_thi_khoi_chi_co_ket_luan(monkeypatch):
    llm = what_if_llm(tool_response("analyze", advised([STEP_UNGROUNDED])))
    events, _, _ = run_turn(WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch)
    (only,) = reasoning_blocks(events)
    assert (
        only["data"]["steps"] == []
        and only["data"]["complete"] is True
        and only["data"]["conclusion"]["option_id"] == "defer"
    )


def test_guardrail_loc_ca_chu_cua_lap_luan(monkeypatch):
    client = FakeGuardrailClient(block_words=("cổ phiếu",))
    bad = {**STEP_SCENARIO, "effect": "Nên bán cổ phiếu để mua."}
    llm = what_if_llm(tool_response("analyze", advised([bad])))
    events, _, _ = run_turn(
        WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch, guardrail=make_guardrail(client)
    )
    output_checks = [c for c in client.calls if c["source"] == "OUTPUT"]
    assert any("Nên bán cổ phiếu" in c["content"][0]["text"]["text"] for c in output_checks)
    assert reasoning_blocks(events) == [] and "options" not in block_types(
        events
    )  # như mọi chữ model khác bị chặn


def test_analyst_thay_can_cu_va_thoi_quen_trong_prompt(monkeypatch):
    llm = what_if_llm(tool_response("analyze", advised()))
    run_turn(WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch)
    prompt = raw_prompt(analyst_call(llm))
    can_cu = json.loads(prompt.split("<can_cu>", 1)[1].split("</can_cu>", 1)[0])
    keys = [c["ma"] for c in can_cu]
    assert {"tool:run_scenario", "tool:get_obligations", "tool:get_behavior_profile"} <= set(keys)
    assert "tool:check_suitability" not in keys and "tool:move_between_jars" not in keys
    assert {f"rule:{r}" for r in advisor.RULE_TITLES} <= set(keys)
    data = json.loads(prompt.split("<du_lieu>", 1)[1].split("</du_lieu>", 1)[0])
    assert data["behavior"]["habits"][0] == {
        "kind": "payday_cycle",
        "text": "7 ngày đầu sau ngày lương bạn chi 46% tổng chi của cả kỳ.",
    }
    # lập luận đứng trước phương án trong schema (model viết căn cứ trước khi chọn)
    props = list(Analysis.model_json_schema()["properties"])
    assert props.index("reasoning") < props.index("options") < props.index("conclusion")


def test_ket_luan_theo_id_moi_khi_ma_dat_lai_id_phuong_an(monkeypatch):
    """`enforce_switch_jar` đặt lại id theo hũ thật (`switch` thành `switch_du_phong`): kết luận trỏ phương án đó vẫn khớp."""

    payload = _analysis("du_phong")
    payload["conclusion"] = {
        "text": "Bạn nên lấy tiền hũ Dự phòng cho món này.",
        "option_id": "switch",
        "personal": [],
    }
    events, _ = _run(monkeypatch, payload)
    assert _options(events)["switch_du_phong"]["recommended"] is True
    assert final_reasoning(events)["data"]["conclusion"]["option_id"] == "switch_du_phong"


# --- hàm thuần -----------------------------------------------------------------------------------------------------------
def test_ten_luat_khop_file_luat():

    titles = {}
    for path in sorted((REPO / "gateway/tools/planner/rules").glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        titles[doc["id"]] = doc["title"]
    assert titles == advisor.RULE_TITLES


def test_luat_skipped_khong_phai_can_cu():
    v = SuitabilityVerdict.model_validate(fixture("check_suitability.ok.json")["data"])
    rules = advisor.checked_rules([v])
    assert set(rules) == {"obligations_first", "no_borrow_to_spend", "obligation_to_income"}
    assert rules["no_borrow_to_spend"] == "Không khuyên vay để tiêu"


def test_ho_so_hanh_vi_chua_san_sang_thi_khong_co_thoi_quen():
    assert advisor.behavior_view(fixture("get_behavior_profile.ok_chua_san_sang.json")) is None
    assert advisor.behavior_view(None) is None
    view = advisor.behavior_view(fixture("get_behavior_profile.ok.json"))
    assert (
        view is not None
        and len(view["habits"]) <= advisor.MAX_HABITS
        and view["segment"] == "Chi dồn sau kỳ lương"
    )


def test_tools_ok_chi_lay_tool_doc_tra_ok():

    outs = [
        ToolOutcome("forecast___run_scenario", ToolKind.OK, payload={"status": "OK"}),
        ToolOutcome("ledger___get_obligations", ToolKind.TOOL_ERROR, code="INTERNAL_ERROR"),
        ToolOutcome("planner___check_suitability", ToolKind.OK, payload={"status": "OK"}),
        ToolOutcome("forecast___run_scenario", ToolKind.OK, payload={"status": "OK"}),
    ]
    assert advisor.tools_ok(outs) == ["run_scenario"]


def test_khong_thay_suy_nghi_tho_trong_khoi():
    """Khối chỉ có các trường đã kiểm: không có chỗ cho chuỗi suy nghĩ của model (hợp đồng chặt)."""
    data = fixture_block("reasoning.what_if")["data"]
    with pytest.raises(Exception):  # noqa: B017
        B.ReasoningData.model_validate({**data, "thinking": "..."})


def fixture_block(name: str) -> dict[str, Any]:
    return json.loads(
        (REPO / "contracts/fixtures/blocks/valid" / f"{name}.json").read_text(encoding="utf-8")
    )


def test_thu_tu_su_kien_hop_le_khi_co_lap_luan(monkeypatch):
    llm = what_if_llm(tool_response("analyze", advised()))
    events, _, _ = run_turn(WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch)
    t = types(events)
    first_reasoning = next(
        i
        for i, e in enumerate(events)
        if e.type.value == "ACTIVITY_SNAPSHOT" and e.content["type"] == "reasoning"
    )
    options_at = next(
        i
        for i, e in enumerate(events)
        if e.type.value == "ACTIVITY_SNAPSHOT" and e.content["type"] == "options"
    )
    assert first_reasoning < options_at < t.index("TEXT_MESSAGE_START")


# --- lộ trình ------------------------------------------------------------------------------------------------------------
ROADMAP_STEP_OBLIGATION = {
    "seen": "Khoản Trả sau 333.000 ₫ đến hạn 05/12.",
    "why": "Trả đúng hạn thì không mất phí trễ.",
    "effect": "Giai đoạn đầu giữ sẵn tiền cho khoản này.",
    "basis": ["tool:get_obligations"],
}
ROADMAP_STEP_BEHAVIOR = {
    "seen": "Bạn hay chi dồn trong tuần đầu sau ngày lương.",
    "why": "Tiền để dành dễ bị tiêu trước khi kịp chuyển.",
    "effect": "Bước để dành đặt ngay sau kỳ lương.",
    "basis": ["tool:get_behavior_profile"],
}
ROADMAP_STEP_UNGROUNDED = {
    "seen": "Bạn cần thêm 999.999 ₫ mỗi tháng.",
    "why": "Thiếu thì chậm mục tiêu.",
    "effect": "Tăng phần để dành.",
    "basis": ["tool:optimize_allocation"],
}


def roadmap_draft(
    conclusion_step: str | None = "bu_du_phong", personal: list[str] | None = None
) -> dict[str, Any]:

    draft = outline(step(), review())
    draft["reasoning"] = [ROADMAP_STEP_UNGROUNDED, ROADMAP_STEP_OBLIGATION, ROADMAP_STEP_BEHAVIOR]
    if conclusion_step is not None:
        draft["conclusion"] = {
            "text": "Bạn nên bắt đầu bằng việc giữ sẵn tiền cho khoản đến hạn 05/12.",
            "step_id": conclusion_step,
            "personal": personal or [],
        }
    return draft


def test_lo_trinh_co_nguoi_tu_van_kiem_lap_luan_va_ket_luan_theo_ban_da_luu():

    tools = scripted_tools(checks=("ok", "ok", "ok"))
    result, client, scope = build(
        tools, roadmap_draft("giu_san_tra_sau", ["behavior"]), advise=True
    )
    assert result.outcome.ok and scope.calls == 1  # một lời gọi planner như cũ
    assert ("get_behavior_profile", {}) in tools.calls
    advice = result.advice
    assert advice is not None and advice.context == "roadmap"
    assert [s.seen for s in advice.steps] == [
        ROADMAP_STEP_OBLIGATION["seen"],
        ROADMAP_STEP_BEHAVIOR["seen"],
    ]
    assert [b.ref for b in advice.steps[1].basis] == ["get_behavior_profile"]
    # kết luận trỏ một bước CỦA BẢN ĐÃ LƯU (fixture save_roadmap.ok có bước giu_san_tra_sau)
    assert advice.conclusion is not None and advice.conclusion.step_id == "giu_san_tra_sau"
    assert advice.conclusion.personal == ["behavior"]
    call = client.calls[0]
    system = json.dumps(call["system"], ensure_ascii=False)
    assert "reasoning" in system and "conclusion" in system
    sent = json.loads(call["messages"][0]["content"][0]["text"])
    assert (
        "behavior" in sent["context"]
        and {"ma": "tool:get_behavior_profile", "ten": "Thói quen chi tiêu"} in sent["can_cu"]
    )
    schema = json.dumps(call["toolConfig"], ensure_ascii=False)
    assert '"reasoning"' in schema and '"conclusion"' in schema


def test_lo_trinh_ket_luan_tro_buoc_khong_luu_thi_bo():

    result, _, _ = build(
        scripted_tools(checks=("ok", "ok", "ok")), roadmap_draft("bu_du_phong"), advise=True
    )
    assert (
        result.advice is not None
        and result.advice.conclusion is None
        and len(result.advice.steps) == 2
    )


def test_job_sinh_lai_khong_co_nguoi_tu_van():

    tools = scripted_tools(checks=("ok", "ok", "ok"))
    result, client, _ = build(tools, outline(step(), review()))
    assert result.outcome.ok and result.advice is None
    assert "get_behavior_profile" not in [n for n, _ in tools.calls]
    call = client.calls[0]
    assert '"reasoning"' not in json.dumps(call["toolConfig"], ensure_ascii=False)
    assert "can_cu" not in json.loads(call["messages"][0]["content"][0]["text"])


def test_chat_lap_lo_trinh_phat_lap_luan_truoc_the_lo_trinh(monkeypatch):

    tools = scripted_tools(checks=("ok", "ok", "ok"))
    llm = make_llm(
        [
            route_response(intent="roadmap", roadmap_action="create"),
            tool_response("draft_roadmap", roadmap_draft("giu_san_tra_sau")),
        ]
    )
    events, _, _ = run_turn("Lập lộ trình cho mình", llm=llm, tools=tools, monkeypatch=monkeypatch)
    check_agui_order(events)
    kinds = block_types(events)
    assert "roadmap" in kinds and kinds.index("reasoning") < kinds.index("roadmap")
    final = final_reasoning(events)["data"]
    assert final["context"] == "roadmap" and final["conclusion"]["step_id"] == "giu_san_tra_sau"
    assert "999.999" not in json.dumps(reasoning_blocks(events), ensure_ascii=False)
