"""Luồng what-if (L2 đến L5), kiểm tra trước khi quẹt (F3), khai báo hồ sơ, Guardrail, bản ghi lượt, suy giảm.

Model, tool và Guardrail giả chỉ nằm ở đây và ở `agent_helpers`; mã sản phẩm không import chúng.
"""

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import AsyncIterator
from typing import Any

from agent_helpers import (
    FakeGuardrailClient,
    FakeRecords,
    FakeTools,
    FakeUsage,
    FakeWriter,
    agent_settings,
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
from yofina_agent import notices
from yofina_agent.tools import ToolKind, ToolOutcome, classify_result
from yofina_agent.whatif import adds_scenario_obligation

WHAT_IF_Q = "Nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao"
ROUTE_WHAT_IF = {
    "intent": "what_if",
    "amount_vnd": 1_200_000,
    "funding": "credit",
    "scenario_kind": "bnpl_purchase",
    "label": "tai nghe",
}
SCENARIO = {
    "scenario": {
        "kind": "bnpl_purchase",
        "amount_vnd": 1_200_000,
        "funding_source": "credit",
        "jar_code": None,
        "date": None,
        "label": "tai nghe",
    }
}
NARRATIVE = (
    "Nếu mua tai nghe bằng Trả sau, đến hạn 05/12 bạn cần 2.200.000 ₫ nhưng hũ Nghĩa vụ chỉ có 1.050.000 ₫ "
    "nên bị hụt 1.150.000 ₫. Dữ liệu ở mức tin cậy vừa."
)


def analysis(narrative: str = NARRATIVE, defer_summary: str | None = None, move_amount: int = 1_150_000) -> dict[str, Any]:
    proposal = {"funding_source": "credit", "is_essential": False, "category": "spending", "risk_level": "low", "origin": "recommendation"}
    return {
        "narrative": narrative,
        "options": [
            {
                "option_id": "defer",
                "kind": "defer",
                "label": "Hoãn mua sau kỳ lương",
                "summary": defer_summary or "Hoãn tới sau 05/12 để hũ Nghĩa vụ không bị hụt 1.150.000 ₫.",
                "proposal": {"kind": "defer", **proposal},
                "recommended": True,
            },
            {
                "option_id": "cover",
                "kind": "move_between_jars",
                "label": "Chuyển bù cho hũ Nghĩa vụ",
                "summary": "Chuyển bù phần hụt từ hũ khác trước hạn.",
                "proposal": {"kind": "move_between_jars", "amount_vnd": 1_200_000, **proposal},
                "action": {"tool": "move_between_jars", "params": {"from_jar": "giai_tri", "to_jar": "nghia_vu", "amount_vnd": move_amount}},
            },
        ],
        "follow_ups": [],
    }


def what_if_llm(*extra: Any, usage: FakeUsage | None = None):
    return make_llm(
        [route_response(**ROUTE_WHAT_IF), tool_response("plan_scenario", SCENARIO), *extra], usage
    )


def block_types(events: list[Any]) -> list[str]:
    return [b["type"] for b in blocks_of(events)]


def result_of(events: list[Any]) -> dict[str, Any]:
    return events[-1].result


def text_of(events: list[Any]) -> str:
    return "".join(e.delta for e in events if e.type.value == "TEXT_MESSAGE_CONTENT")


def call_names(tools: FakeTools) -> list[str]:
    return [n for n, _ in tools.calls]


# --- what-if: đường chính ----------------------------------------------------------------------
def test_what_if_thu_tu_khoi_so_lieu_roi_phuong_an_roi_van_ban(monkeypatch):
    records = FakeRecords()
    llm = what_if_llm(tool_response("analyze", analysis()))
    events, tools, _ = run_turn(WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch, records=records)
    check_agui_order(events)
    # khối số liệu của engine trước, rồi phương án, rồi khối xác nhận mà phương án tham chiếu; văn bản sau cùng
    assert block_types(events) == ["forecast_timeline", "obligation_impact", "options", "confirm"]
    first_block = types(events).index("ACTIVITY_SNAPSHOT")
    first_text = types(events).index("TEXT_MESSAGE_START")
    assert first_block < first_text
    blocks = blocks_of(events)
    assert blocks[0]["id"].endswith(":what_if") and blocks[0]["data"]["compare"]["after"]["status"]
    assert blocks[1]["data"]["cost"]["total_due_vnd"] == 2_200_000
    opts = blocks[2]["data"]["options"]
    assert len(opts) == 2 and opts[0]["recommended"] is True
    cover = next(o for o in opts if o["option_id"] == "cover")
    assert cover["action"] == {"kind": "confirm", "tool": "move_between_jars", "block_id": blocks[3]["id"]}
    assert cover["checked_rules"] and cover["status"] == "ok"
    assert text_of(events).startswith("Nếu mua tai nghe bằng Trả sau")
    # tool: nghĩa vụ + biểu phí song song, rồi run_scenario, rồi kiểm luật từng phương án, rồi tool ghi KHÔNG token
    names = call_names(tools)
    assert names[0] == "get_jar_balances" and names.index("run_scenario") > names.index("get_obligations")
    assert names.count("check_suitability") == 2 and names[-1] == "move_between_jars"
    move_args = tools.calls[-1][1]
    assert "confirm_token" not in move_args and move_args["amount_vnd"] == 1_150_000
    # origin do mã đặt, không tin model
    suit_args = [a for n, a in tools.calls if n == "check_suitability"]
    assert all(a["proposal"]["origin"] == "recommendation" for a in suit_args)
    # tiêu chí 9: số lượt gọi model của một lượt what-if không quá 4 (đây: router, Orchestrator, Analyst)
    r = result_of(events)
    assert r["intent"] == "what_if" and r["model_calls"] == 3 and r["verifier_rounds"] == 1 and r["degraded"] is False
    # bản ghi lượt: đúng một, do mã dựng
    (rec,) = records.saved
    assert rec["intent"] == "what_if" and rec["token_usage"]["model_calls"] == 3
    assert {x["rule_id"] for x in rec["rules_checked"]} >= {"numeric_grounding", "no_borrow_to_spend"}
    assert rec["confidence"]["band"] == "medium" and len(rec["confidence"]["reasons"]) >= 2
    assert [b["type"] for b in rec["blocks_emitted"]][:2] == ["forecast_timeline", "obligation_impact"]
    assert {s["step"] for s in rec["step_timings"]} >= {"router", "orchestrator", "tools", "analyst", "verifier", "composer"}
    assert any(d["tool"].endswith("run_scenario") for d in rec["data_used"])


def test_verifier_so_khong_co_can_cu_thi_tra_loi_loi_cho_analyst_sua_mot_vong(monkeypatch):
    bad = analysis(narrative="Bạn sẽ cần 1.350.000 ₫ nữa vào ngày 05/12.")
    llm = what_if_llm(tool_response("analyze", bad), tool_response("analyze", analysis()))
    events, tools, _ = run_turn(WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert block_types(events)[-2:] == ["options", "confirm"] and text_of(events).startswith("Nếu mua")
    r = result_of(events)
    assert r["model_calls"] == 4 and r["verifier_rounds"] == 2  # vẫn không quá 4
    assert r["degraded"] is False  # vòng sửa qua kiểm tra: không suy giảm
    retry_prompt = llm[1].calls[3]["messages"][0]["content"][0]["text"]
    assert "<phan_hoi_kiem_tra>" in retry_prompt and "1.350.000" in retry_prompt


def test_het_vong_sua_thi_bo_loi_giai_thich_nhung_giu_phuong_an_da_kiem(monkeypatch):
    """Lời giải thích hai vòng đều có số không căn cứ: không phát lời; hai phương án tự qua luật và có căn cứ vẫn được phát."""
    bad = analysis(narrative="Bạn sẽ cần 1.350.000 ₫ nữa.")
    llm = what_if_llm(tool_response("analyze", bad), tool_response("analyze", bad))
    records = FakeRecords()
    events, tools, _ = run_turn(WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch, records=records)
    check_agui_order(events)
    assert block_types(events) == ["forecast_timeline", "obligation_impact", "options", "confirm", "notice"]
    blocks = blocks_of(events)
    assert [o["option_id"] for o in blocks[2]["data"]["options"]] == ["defer", "cover"]
    n = blocks[-1]["data"]
    assert n["kind"] == "degraded" and n["degraded_reason"] == "verifier_failed" and "phương án" in n["message"]
    assert (n["title"], n["message"]) == notices.VERIFIER_FAILED_OPTIONS_ONLY
    assert text_of(events) == ""  # lời giải thích chưa kiểm chứng không bao giờ được phát
    assert [a["amount_vnd"] for n_, a in tools.calls if n_ == "move_between_jars"] == [1_150_000]
    assert all("confirm_token" not in a for n_, a in tools.calls if n_ == "move_between_jars")
    r = result_of(events)
    assert r["model_calls"] == 4 and r["verifier_rounds"] == 2
    # Verifier rơi vào đường dự phòng: lượt suy giảm, cùng dấu hiệu với bản ghi lượt (lời giải thích chưa kiểm chứng)
    assert r["degraded"] is True
    (rec,) = records.saved
    assert "Phần lời giải thích chưa qua kiểm chứng nên không được hiển thị." in rec["confidence"]["reasons"]


def test_het_vong_ma_phuong_an_cung_khong_co_can_cu_thi_chi_con_khoi_so_lieu_va_notice(monkeypatch):
    bad = analysis(narrative="Bạn sẽ cần 1.350.000 ₫ nữa.", defer_summary="Hoãn để đỡ hụt 1.350.000 ₫.", move_amount=777_000)
    tools = FakeTools({"check_suitability": lambda a: classify_result("x", mcp_ok(fixture("check_suitability.violation.json")))})
    llm = what_if_llm(tool_response("analyze", bad), tool_response("analyze", bad))
    events, tools, _ = run_turn(WHAT_IF_Q, llm=llm, tools=tools, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert block_types(events) == ["forecast_timeline", "obligation_impact", "notice"]
    n = blocks_of(events)[-1]["data"]
    assert n["kind"] == "degraded" and n["degraded_reason"] == "verifier_failed"
    assert text_of(events) == "" and "move_between_jars" not in call_names(tools)  # không phương án, không gọi tool ghi
    assert (n["title"], n["message"]) == notices.VERIFIER_FAILED
    assert result_of(events)["model_calls"] == 4
    assert result_of(events)["degraded"] is True


def test_phuong_an_vi_pham_luat_khong_duoc_phat(monkeypatch):
    violation = fixture("check_suitability.violation.json")
    tools = FakeTools({"check_suitability": lambda a: classify_result("x", mcp_ok(violation))})
    llm = what_if_llm(tool_response("analyze", analysis()), tool_response("analyze", analysis()))
    events, _, _ = run_turn(WHAT_IF_Q, llm=llm, tools=tools, monkeypatch=monkeypatch)
    assert "options" not in block_types(events)
    assert blocks_of(events)[-1]["data"]["degraded_reason"] == "verifier_failed"


def _option(option_id: str, kind: str, funding: str, **extra: Any) -> dict[str, Any]:
    proposal = {"kind": kind, "funding_source": funding, "is_essential": False, "category": "spending", "risk_level": "low", "origin": "recommendation"}
    return {"option_id": option_id, "kind": kind, "label": f"Phương án {option_id}", "summary": "Giữ hũ Nghĩa vụ không hụt.", "proposal": proposal, **extra}


def test_scenario_id_chi_gan_cho_phuong_an_mang_nghia_vu_cua_kich_ban(monkeypatch):
    """Nguyên nhân verifier_failed của ca Trả sau: engine cộng nghĩa vụ của kịch bản vào MỌI đề xuất có scenario_id, nên phương án
    bỏ qua, hoãn, chuyển bù hũ bị luật obligation_to_income chặn oan. Chỉ phương án dùng tín dụng mới được gắn scenario_id."""
    a = analysis()
    a["options"] = [
        _option("skip", "skip", "jar", recommended=True),
        _option("defer", "defer", "jar"),
        _option("cover", "move_between_jars", "jar"),
    ]
    llm = what_if_llm(tool_response("analyze", a))
    _, tools, _ = run_turn(WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch)
    suit_args = [a for n, a in tools.calls if n == "check_suitability"]
    assert len(suit_args) == 3 and all("scenario_id" not in x for x in suit_args)


def test_phuong_an_dung_tin_dung_van_duoc_kiem_voi_nghia_vu_that_cua_kich_ban(monkeypatch):
    a = analysis()
    a["options"] = [
        _option("skip", "skip", "jar", recommended=True),
        _option("credit", "use_credit", "credit"),
        _option("proceed", "proceed", "jar"),
    ]
    llm = what_if_llm(tool_response("analyze", a))
    _, tools, _ = run_turn(WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch)
    by_kind = {x["proposal"]["kind"]: x for n, x in tools.calls if n == "check_suitability"}
    assert "scenario_id" not in by_kind["skip"]
    assert by_kind["use_credit"]["scenario_id"] and by_kind["proceed"]["scenario_id"]
    # nhãn defer nhưng nguồn tín dụng: không né được kiểm nghĩa vụ
    assert adds_scenario_obligation(types_option("defer", "credit")) is True
    assert adds_scenario_obligation(types_option("defer", "jar")) is False


def types_option(kind: str, funding: str) -> Any:
    from yofina_agent.schemas import AnalysisOption

    return AnalysisOption.model_validate(_option("x", kind, funding))


def test_so_tien_trong_tham_so_hanh_dong_cung_phai_co_can_cu(monkeypatch):
    bad = analysis(move_amount=777_000)  # số model tự nghĩ ra, không có trong dữ liệu tool
    llm = what_if_llm(tool_response("analyze", bad), tool_response("analyze", analysis()))
    events, tools, _ = run_turn(WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch)
    assert result_of(events)["verifier_rounds"] == 2
    assert [a["amount_vnd"] for n, a in tools.calls if n == "move_between_jars"] == [1_150_000]


def test_nhac_lai_di_qua_xac_nhan_bang_confirm_action(monkeypatch):
    a = analysis()
    a["options"][1] = {
        "option_id": "remind",
        "kind": "remind_later",
        "label": "Nhắc xem lại",
        "summary": "Nhắc bạn xem lại trước kỳ lương.",
        "proposal": {"kind": "remind_later", "category": "spending", "origin": "recommendation"},
        "action": {"tool": "schedule_nudge", "params": {"op": "create", "kind": "purchase_review", "fire_on": "2026-11-26", "note": "xem lại tai nghe"}},
    }
    llm = what_if_llm(tool_response("analyze", a))
    events, tools, _ = run_turn(WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch)
    assert block_types(events)[-2:] == ["options", "confirm_action"]
    blocks = blocks_of(events)
    action = blocks[-2]["data"]["options"][1]["action"]
    assert action == {"kind": "confirm_action", "tool": "schedule_nudge", "block_id": blocks[-1]["id"]}
    assert [a for n, a in tools.calls if n == "schedule_nudge"][0].get("confirm_token") is None


def test_tool_ghi_loi_thi_phuong_an_van_con_nhung_khong_co_hanh_dong(monkeypatch):
    err = fixture("move_between_jars.error_token_reused.json")
    tools = FakeTools({"move_between_jars": lambda a: classify_result("x", mcp_ok(err))})
    llm = what_if_llm(tool_response("analyze", analysis()))
    events, _, _ = run_turn(WHAT_IF_Q, llm=llm, tools=tools, monkeypatch=monkeypatch)
    assert block_types(events)[-1] == "options"
    cover = next(o for o in blocks_of(events)[-1]["data"]["options"] if o["option_id"] == "cover")
    assert "action" not in cover


# --- suy giảm ----------------------------------------------------------------------------------
def test_model_het_tran_thi_what_if_van_tra_the_so_lieu(monkeypatch):
    """Tiêu chí 8: ép trần model về 0, what-if vẫn có khối số liệu tất định (spec dựng bằng mã từ luật dự phòng)."""
    llm = make_llm([], FakeUsage(caps_hit={"m-small-a", "m-small-b", "m-plan"}))
    events, tools, _ = run_turn(WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert block_types(events) == ["forecast_timeline", "obligation_impact", "notice"]
    n = blocks_of(events)[-1]["data"]
    assert (n["kind"], n["code"], n["degraded_reason"]) == ("degraded", "MODEL_BUDGET_EXCEEDED", "model_budget")
    assert llm[1].calls == [] and text_of(events) == ""
    assert result_of(events)["degraded"] is True and result_of(events)["intent"] == "what_if"


def test_chi_analyst_het_tran_thi_giu_khoi_so_lieu_va_notice(monkeypatch):
    usage = FakeUsage(caps_hit={"m-plan"})
    llm = make_llm([route_response(**ROUTE_WHAT_IF)], usage)
    events, _, _ = run_turn(WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch)
    assert block_types(events) == ["forecast_timeline", "obligation_impact", "notice"]


def test_orchestrator_tra_spec_sai_thi_dung_spec_bang_ma(monkeypatch):
    bad = {"scenario": {**SCENARIO["scenario"], "jar_code": "hu_khong_ton_tai"}}
    llm = make_llm([route_response(**ROUTE_WHAT_IF), tool_response("plan_scenario", bad), tool_response("analyze", analysis())])
    events, tools, _ = run_turn(WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch)
    run_args = next(a for n, a in tools.calls if n == "run_scenario")
    assert run_args["scenario"] == {"kind": "bnpl_purchase", "amount_vnd": 1_200_000, "funding_source": "credit", "label": "tai nghe"}
    assert "options" in block_types(events)


def test_run_scenario_loi_tam_thoi_thi_thu_lai_mot_lan(monkeypatch):
    attempts = {"n": 0}
    ok = fixture("run_scenario.ok_bnpl.json")

    def flaky(args):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return ToolOutcome("x", ToolKind.UNAVAILABLE, code="DATABASE_UNAVAILABLE", message="tạm thời")
        return classify_result("x", mcp_ok(ok))

    events, tools, _ = run_turn(
        WHAT_IF_Q,
        llm=what_if_llm(tool_response("analyze", analysis())),
        tools=FakeTools({"run_scenario": flaky}),
        monkeypatch=monkeypatch,
    )
    assert call_names(tools).count("run_scenario") == 2 and "options" in block_types(events)


def test_run_scenario_loi_hai_lan_thi_notice_co_nut_thu_lai_va_khong_goi_analyst(monkeypatch):
    down = ToolOutcome("x", ToolKind.UNAVAILABLE, code="DATABASE_UNAVAILABLE", message="Dịch vụ tạm thời không phản hồi.")
    llm = what_if_llm()
    events, tools, _ = run_turn(WHAT_IF_Q, llm=llm, tools=FakeTools({"run_scenario": lambda a: down}), monkeypatch=monkeypatch)
    check_agui_order(events)
    assert call_names(tools).count("run_scenario") == 2
    assert block_types(events) == ["notice"]
    n = blocks_of(events)[0]["data"]
    assert n["kind"] == "error" and n["retryable"] is True and n["degraded_reason"] == "tool_error"
    assert len(llm[1].calls) == 2  # chỉ router và Orchestrator, không có Analyst


def test_thieu_nghia_vu_thi_tra_phan_da_co_va_noi_ro_phan_thieu(monkeypatch):
    down = ToolOutcome("x", ToolKind.UNAVAILABLE, code="DATABASE_UNAVAILABLE", message="tạm thời")
    events, _, _ = run_turn(
        WHAT_IF_Q,
        llm=what_if_llm(tool_response("analyze", analysis())),
        tools=FakeTools({"get_obligations": lambda a: down}),
        monkeypatch=monkeypatch,
    )
    notice = next(b for b in blocks_of(events) if b["type"] == "notice")["data"]
    assert notice["missing"] == ["nghĩa vụ sắp đến hạn"] and notice["retryable"] is True
    assert "options" in block_types(events)


def test_du_lieu_it_thi_co_notice_do_tin_cay_thap(monkeypatch):
    low = copy.deepcopy(fixture("run_scenario.ok_bnpl.json"))
    low["data"]["basis"]["history_days"] = 12
    events, _, _ = run_turn(
        WHAT_IF_Q,
        llm=what_if_llm(tool_response("analyze", analysis())),
        tools=FakeTools({"run_scenario": lambda a: classify_result("x", mcp_ok(low))}),
        monkeypatch=monkeypatch,
        records=(rec := FakeRecords()),
    )
    n = next(b for b in blocks_of(events) if b["type"] == "notice")["data"]
    assert n["kind"] == "low_data" and n["degraded_reason"] == "short_history"
    assert rec.saved[0]["confidence"]["band"] == "medium" and "12 ngày" in rec.saved[0]["confidence"]["reasons"][0]


def test_guardrail_dau_ra_chan_loi_giai_thich_thi_chi_con_so_lieu(monkeypatch):
    g = make_guardrail(FakeGuardrailClient(block_words=("tin cậy vừa",)))
    events, tools, _ = run_turn(
        WHAT_IF_Q, llm=what_if_llm(tool_response("analyze", analysis())), monkeypatch=monkeypatch, guardrail=g
    )
    assert block_types(events) == ["forecast_timeline", "obligation_impact", "notice"] and text_of(events) == ""
    assert "move_between_jars" not in call_names(tools)


# --- hỏi lại ----------------------------------------------------------------------------------
def test_thieu_so_tien_thi_hoi_dung_mot_cau_roi_chay_tiep_o_luot_sau(monkeypatch):
    """Tiêu chí 6: "nếu mua cái điện thoại thì sao" -> đúng một câu hỏi, không tool; trả lời xong thì chạy tiếp."""
    llm = make_llm([route_response(intent="what_if", label="điện thoại")])
    events, tools, _ = run_turn("Nếu mua cái điện thoại thì sao", llm=llm, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert tools.calls == [] and block_types(events) == ["clarify"]
    c = blocks_of(events)[0]["data"]
    assert c["slot"] == "amount" and c["question"].count("?") == 1 and c["pending_intent"] == "what_if" and c["chips"]
    # lượt sau: lịch sử có câu trước; router ghép hai câu nên what-if chạy tiếp
    msgs = [
        {"id": "m1", "role": "user", "content": "Nếu mua cái điện thoại thì sao"},
        {"id": "m2", "role": "assistant", "content": c["question"]},
        {"id": "m3", "role": "user", "content": "15 triệu, trả bằng Trả sau"},
    ]
    llm2 = make_llm(
        [
            route_response(**{**ROUTE_WHAT_IF, "amount_vnd": 15_000_000, "label": "điện thoại"}),
            tool_response("plan_scenario", {"scenario": {**SCENARIO["scenario"], "amount_vnd": 15_000_000}}),
            tool_response("analyze", analysis()),
        ]
    )
    events2, tools2, _ = run_turn(None, llm=llm2, monkeypatch=monkeypatch, messages=msgs)
    prompt = llm2[1].calls[0]["messages"][0]["content"][0]["text"]
    assert "Nếu mua cái điện thoại thì sao" in prompt and "Yofina: " in prompt  # router thấy câu trước
    assert "run_scenario" in call_names(tools2) and "options" in block_types(events2)


def test_mua_bang_tien_hu_ma_chua_biet_hu_nao_thi_hoi_hu_nguon(monkeypatch):
    llm = make_llm([route_response(intent="what_if", amount_vnd=500_000, funding="jar", scenario_kind="one_time_purchase")])
    events, tools, _ = run_turn("nếu mua giày 500 nghìn bằng tiền hũ thì sao", llm=llm, monkeypatch=monkeypatch)
    data = blocks_of(events)[0]["data"]
    assert call_names(tools) == ["get_jar_balances"] and data["slot"] == "jar"  # chỉ đọc hũ để dựng chip hũ thật
    assert data["chips"] and "Ăn uống" in [c["label"] for c in data["chips"]]


def test_router_hoi_lai_dung_o_thieu_thi_dung_cau_cua_router(monkeypatch):
    clarify = {"slot": "amount", "question": "Chiếc điện thoại giá khoảng bao nhiêu?", "chips": [{"label": "10 triệu", "value": "10 triệu"}]}
    llm = make_llm([route_response(intent="what_if", clarify=clarify)])
    events, _, _ = run_turn("nếu mua điện thoại thì sao", llm=llm, monkeypatch=monkeypatch)
    c = blocks_of(events)[0]["data"]
    assert c["question"] == "Chiếc điện thoại giá khoảng bao nhiêu?" and c["chips"][0]["value"] == "10 triệu"


# --- F3: kiểm tra trước khi quẹt trong chat ---------------------------------------------------
def test_kiem_tra_truoc_khi_chi_phat_the_ngay_roi_hai_cau_cua_model_nho(monkeypatch):
    llm = make_llm([route_response(intent="affordability", amount_vnd=250_000, label="Người nhận demo", jar_text="ăn uống")])
    writer = FakeWriter("Bạn có thể chuyển 250.000 ₫ nhưng hũ Ăn uống sẽ hụt. Hãy cân nhắc.")
    events, tools, _ = run_turn("chuyển 250k từ ăn uống cho người nhận demo có ổn không", llm=llm, monkeypatch=monkeypatch, writer=writer)
    check_agui_order(events)
    assert call_names(tools) == ["get_jar_balances", "affordability_check"]
    assert tools.calls[1][1] == {"amount_vnd": 250_000, "label": "Người nhận demo", "jar": "an_uong"}
    assert block_types(events) == ["affordability_card"]
    assert types(events).index("ACTIVITY_SNAPSHOT") < types(events).index("TEXT_MESSAGE_START")
    assert text_of(events).startswith("Bạn có thể chuyển 250.000")
    assert writer.calls[0]["task"] == "affordability"


def test_kiem_tra_truoc_khi_chi_loi_viet_qua_han_thi_bo_phan_loi(monkeypatch):
    class Slow(FakeWriter):
        def __call__(self, gateway: Any, **kw: Any) -> AsyncIterator[str]:
            async def gen() -> AsyncIterator[str]:
                await asyncio.sleep(0.5)
                yield "Câu trả lời đến muộn."

            return gen()

    llm = make_llm([route_response(intent="affordability", amount_vnd=250_000, jar_text="ăn uống")])
    events, _, _ = run_turn(
        "250k này có ổn không",
        llm=llm,
        monkeypatch=monkeypatch,
        writer=Slow(),
        settings=agent_settings(affordability_text_timeout_seconds=0.05),
    )
    check_agui_order(events)
    assert block_types(events) == ["affordability_card"] and text_of(events) == ""


def test_kiem_tra_truoc_khi_chi_so_la_trong_loi_thi_bo_phan_loi(monkeypatch):
    llm = make_llm([route_response(intent="affordability", amount_vnd=250_000, jar_text="ăn uống")])
    events, _, _ = run_turn("250k có ổn không", llm=llm, monkeypatch=monkeypatch, writer=FakeWriter("Bạn sẽ còn 999.000 ₫."))
    assert block_types(events) == ["affordability_card"] and text_of(events) == ""


def test_kiem_tra_truoc_khi_chi_model_het_tran_van_co_the(monkeypatch):
    llm = make_llm([], FakeUsage(caps_hit={"m-small-a", "m-small-b"}))
    events, tools, _ = run_turn("chuyển 250k cho bạn có ổn không", llm=llm, monkeypatch=monkeypatch)
    # model hết trần: bộ phân loại dự phòng không biết hũ nào, nên hỏi lại kèm chip hũ thật (không đoán "Đủ"); không gọi affordability_check
    assert call_names(tools) == ["get_jar_balances"] and block_types(events) == ["clarify", "notice"]
    assert blocks_of(events)[0]["data"]["chips"] and result_of(events)["degraded"] is True


def test_kiem_tra_thieu_so_tien_thi_hoi_lai(monkeypatch):
    llm = make_llm([route_response(intent="affordability")])
    events, tools, _ = run_turn("kiểm tra giúp mình", llm=llm, monkeypatch=monkeypatch)
    assert tools.calls == [] and blocks_of(events)[0]["data"]["slot"] == "amount"


# --- khai báo bằng chat ----------------------------------------------------------------------
def test_khai_bao_nghia_vu_bang_chat_qua_update_profile_khong_token_roi_confirm_action(monkeypatch):
    llm = make_llm(
        [route_response(intent="profile_update", obligation_name="Tiền trọ", obligation_kind="rent", amount_vnd=2_500_000, due_day=1)]
    )
    events, tools, writer = run_turn("tiền trọ 2,5 triệu, đóng ngày 1", llm=llm, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert call_names(tools) == ["get_obligations", "update_profile"]
    args = tools.calls[1][1]
    assert args == {"obligation": {"op": "upsert", "name": "Tiền trọ", "amount_vnd": 2_500_000, "cycle": "monthly", "due_day": 1, "kind": "rent"}}
    assert "confirm_token" not in args
    assert block_types(events) == ["confirm_action"] and writer.calls[0]["task"] == "confirm_action"


def test_khai_bao_khoan_da_co_thi_sua_khong_tao_trung(monkeypatch):
    obl = fixture("get_obligations.ok.json")
    existing = copy.deepcopy(obl["data"]["obligations"][0])
    existing.update(name="Tiền trọ", id="9a4d0e11-6b2c-4f3a-8d5e-1c7b9a3f5e21", source="declared")
    obl["data"]["obligations"].insert(0, existing)
    tools = FakeTools({"get_obligations": lambda a: classify_result("x", mcp_ok(obl))})
    llm = make_llm([route_response(intent="profile_update", obligation_name="tiền trọ", amount_vnd=2_700_000)])
    _, tools, _ = run_turn("tiền trọ giờ 2,7 triệu", llm=llm, tools=tools, monkeypatch=monkeypatch)
    sent = tools.calls[1][1]["obligation"]
    assert sent["obligation_id"] == existing["id"] and "kind" not in sent


def test_khai_bao_khoan_moi_khong_ro_loai_thi_hoi_lai(monkeypatch):
    llm = make_llm([route_response(intent="profile_update", obligation_name="Khoản lạ", amount_vnd=1_000_000)])
    events, tools, _ = run_turn("khoản lạ 1 triệu", llm=llm, monkeypatch=monkeypatch)
    assert "update_profile" not in call_names(tools) and blocks_of(events)[0]["type"] == "clarify"


def test_khai_bao_luong(monkeypatch):
    llm = make_llm([route_response(intent="profile_update", salary_vnd=9_500_000, payday_day=5)])
    events, tools, _ = run_turn("lương mình 9,5 triệu về ngày 5", llm=llm, monkeypatch=monkeypatch)
    assert call_names(tools) == ["update_profile"] and tools.calls[0][1] == {"monthly_salary_vnd": 9_500_000, "payday_day": 5}
    assert block_types(events) == ["confirm_action"]


# --- L0: PII và Guardrail ----------------------------------------------------------------------
def test_pii_duoc_che_truoc_khi_vao_model_va_truoc_khi_luu(monkeypatch):
    class Store:
        saved: list[dict[str, Any]] = []

        async def save(self, **kw: Any) -> bool:
            self.saved.append(kw)
            return True

    store = Store()
    llm = make_llm([route_response(intent="chitchat", reply="Chào bạn!")])
    run_turn("chào, sđt mình 0912345678 và stk 1234567890123", llm=llm, monkeypatch=monkeypatch, store=store)
    prompt = llm[1].calls[0]["messages"][0]["content"][0]["text"]
    assert "0912345678" not in prompt and "1234567890123" not in prompt and "[SĐT]" in prompt
    assert "[SĐT]" in store.saved[0]["user_text"] and "0912345678" not in store.saved[0]["user_text"]


def test_guardrail_chan_dau_vao_thi_tu_choi_dung_pham_vi_khong_goi_tool(monkeypatch):
    """Tiêu chí 5: không có mã chứng khoán nào trong câu trả lời."""
    client = FakeGuardrailClient(block_words=("cổ phiếu",))
    g = make_guardrail(client)
    records = FakeRecords()
    llm = make_llm([route_response(intent="what_if", amount_vnd=1_000_000, funding="jar", jar_text="giải trí")])
    events, tools, _ = run_turn("Nên mua cổ phiếu VNM nào?", llm=llm, monkeypatch=monkeypatch, guardrail=g, records=records)
    check_agui_order(events)
    assert tools.calls == [] and block_types(events) == ["notice", "suggestions"]
    wire = json.dumps(blocks_of(events), ensure_ascii=False) + text_of(events)
    assert "VNM" not in wire
    assert blocks_of(events)[0]["data"]["kind"] == "out_of_scope"
    assert records.saved[0]["intent"] == "out_of_scope" and records.saved[0]["outcome"] == "rejected"
    assert {r["rule_id"]: r["outcome"] for r in records.saved[0]["rules_checked"]}["guardrail_input"] == "fail"
    assert client.calls[0]["source"] == "INPUT" and client.calls[0]["guardrailIdentifier"] == "gr-test"


def test_guardrail_tat_hoac_chua_cau_hinh_thi_khong_goi():
    from yofina_agent.guardrail import Guardrail

    client = FakeGuardrailClient(block_words=("x",))
    off = Guardrail(agent_settings(guardrail_enabled=False, guardrail_id="g", guardrail_version="1"), region="r", client=client)
    no_id = Guardrail(agent_settings(guardrail_enabled=True, guardrail_id=None, guardrail_version=None), region="r", client=client)
    assert not off.enabled and not no_id.enabled
    res = asyncio.run(off.check("x", "INPUT"))
    assert res.skipped and not res.blocked and client.calls == []


def test_guardrail_loi_dich_vu_mac_dinh_cho_chay_tiep_va_co_the_dong():
    err = RuntimeError("boom")
    open_ = make_guardrail(FakeGuardrailClient(error=err))
    closed = make_guardrail(FakeGuardrailClient(error=err), guardrail_fail_open=False)
    assert asyncio.run(open_.check("câu hỏi", "INPUT")).blocked is False
    assert asyncio.run(closed.check("câu hỏi", "INPUT")).blocked is True


def test_ngoai_pham_vi_khong_co_loi_do_model_viet(monkeypatch):
    llm = make_llm([route_response(intent="out_of_scope", reply="Bạn nên mua VNM và FPT nhé.")])
    events, tools, _ = run_turn("nên mua cổ phiếu nào", llm=llm, monkeypatch=monkeypatch)
    wire = json.dumps(blocks_of(events), ensure_ascii=False) + text_of(events)
    assert "VNM" not in wire and "FPT" not in wire and block_types(events) == ["notice", "suggestions"]
    assert tools.calls == []


def test_xa_giao_reply_co_so_khong_co_can_cu_thi_khong_phat(monkeypatch):
    llm = make_llm([route_response(intent="chitchat", reply="Bạn còn 5.000.000 ₫ trong ví.")])
    events, _, writer = run_turn("hi", llm=llm, monkeypatch=monkeypatch)
    assert "5.000.000" not in text_of(events)
    assert writer.calls[0]["task"] == "chitchat"


def test_hoi_da_chuyen_chua_thi_tra_loi_bang_dong_he_thong_khong_goi_tool_ghi(monkeypatch):
    msgs = [
        {"id": "m1", "role": "system", "content": "Hệ thống ghi nhận: đã chuyển 100.000 ₫ từ Giải trí sang Ăn uống."},
        {"id": "m2", "role": "user", "content": "đã chuyển xong chưa"},
    ]
    llm = make_llm([route_response(intent="chitchat", reply="Rồi, mình đã chuyển 100.000 ₫ từ Giải trí sang Ăn uống.")])
    events, tools, _ = run_turn(None, llm=llm, monkeypatch=monkeypatch, messages=msgs)
    assert tools.calls == [] and "100.000" in text_of(events)
