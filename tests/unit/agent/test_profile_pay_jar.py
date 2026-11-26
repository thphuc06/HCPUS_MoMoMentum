"""Ví không có hũ loại nghĩa vụ (không có hũ trả mặc định): khai nghĩa vụ, kiểm tra trước khi chi bằng Trả sau và what-if Trả sau
qua chat hỏi hũ trả (khối `clarify`, chip hũ thật) rồi gọi lại với `pay_jar`.

Agent chỉ hỏi khi lỗi của tool nói ĐÚNG là thiếu hũ trả: trường có cấu trúc `field: "pay_jar"` của phong bì lỗi (`ToolError`),
không so câu chữ và không đoán từ danh sách hũ. Quy tắc hũ trả mặc định là của server (`yofina_core.wallet.resolve_obligation_pay_jar`);
tool giả ở đây chỉ trả lỗi như ledger/forecast với ví không có hũ nghĩa vụ, không tự tính gì.
"""

from __future__ import annotations

import copy
from typing import Any

from agent_helpers import (
    FakeTools,
    agent_settings,
    blocks_of,
    check_agui_order,
    fixture,
    make_llm,
    mcp_ok,
    route_response,
    run_turn,
    tool_response,
)
from test_whatif import ROUTE_WHAT_IF, analysis
from yofina_agent import notices
from yofina_agent.tools import ToolOutcome, classify_result
from yofina_core.errors import ErrorCode
from yofina_core.wallet import DEFAULT_OBLIGATION_JAR

OBLIGATION = {"obligation_name": "Tiền trọ", "obligation_kind": "rent", "amount_vnd": 2_500_000, "due_day": 1}
CODE_FIRST = agent_settings(whatif_spec_source="code_first")
ROUTE_AFFORD = {"intent": "affordability", "amount_vnd": 1_200_000, "funding": "credit", "label": "tai nghe"}


def _jars(*, with_obligation_jar: bool) -> dict[str, Any]:
    """`get_jar_balances` của fixture, có `kind` cho mỗi hũ; bỏ hũ Nghĩa vụ khi ví không có hũ loại nghĩa vụ."""
    payload = copy.deepcopy(fixture("get_jar_balances.ok.json"))
    jars = []
    for j in payload["data"]["jars"]:
        if j["code"] == DEFAULT_OBLIGATION_JAR:
            if not with_obligation_jar:
                continue
            j["kind"] = "obligation"
        else:
            j["kind"] = "spending"
        jars.append(j)
    payload["data"]["jars"] = jars
    payload["data"]["jars_total_vnd"] = sum(j["balance_vnd"] for j in jars)
    return payload


def _error(message: str, field: str | None = None, code: ErrorCode = ErrorCode.PARAMS_INVALID) -> ToolOutcome:
    body = {"status": "ERROR", "code": code.value, "message": message, **({"field": field} if field else {})}
    return classify_result("x", mcp_ok(body))


def _update_profile_needs_pay_jar(args: dict[str, Any]) -> ToolOutcome:
    """Như ledger với ví không có hũ nghĩa vụ: thiếu pay_jar thì PARAMS_INVALID kèm `field: pay_jar`, có thì trả bản xem trước."""
    if "pay_jar" not in args.get("obligation", {}):
        return classify_result("x", mcp_ok(fixture("update_profile.error_pay_jar_required.json")))
    return classify_result("x", mcp_ok(fixture("update_profile.needs_confirmation.json")))


def _afford_needs_pay_jar(args: dict[str, Any]) -> ToolOutcome:
    """Như forecast `affordability_check` với Trả sau trên ví không có hũ nghĩa vụ."""
    if "pay_jar" not in args:
        return classify_result("x", mcp_ok(fixture("affordability_check.error_pay_jar_required.json")))
    return classify_result("x", mcp_ok(fixture("affordability_check.ok.json")))


def _scenario_needs_pay_jar(args: dict[str, Any]) -> ToolOutcome:
    """Như forecast `run_scenario` với kịch bản Trả sau trên ví không có hũ nghĩa vụ."""
    if "pay_jar" not in args["scenario"]:
        return classify_result("x", mcp_ok(fixture("run_scenario.error_pay_jar_required.json")))
    return classify_result("x", mcp_ok(fixture("run_scenario.ok_bnpl.json")))


def _tools(*, with_obligation_jar: bool = False, **results: Any) -> FakeTools:
    jars = _jars(with_obligation_jar=with_obligation_jar)
    base = {"get_jar_balances": lambda a: classify_result("x", mcp_ok(jars)), "update_profile": _update_profile_needs_pay_jar}
    return FakeTools({**base, **results})


def _calls(tools: FakeTools, name: str) -> list[dict[str, Any]]:
    return [args for n, args in tools.calls if n == name]


def _assert_asks_pay_jar(events: list[Any], pending_intent: str) -> None:
    check_agui_order(events)
    blocks = blocks_of(events)
    assert [b["type"] for b in blocks if b["type"] in ("clarify", "notice")] == ["clarify"]  # không có notice lỗi cụt đường
    data = next(b for b in blocks if b["type"] == "clarify")["data"]
    assert data["slot"] == "jar" and data["question"] == notices.CLARIFY["pay_jar"]["question"]
    assert data["pending_intent"] == pending_intent
    user_jars = _jars(with_obligation_jar=False)["data"]["jars"]
    assert data["chips"]
    assert [c["label"] for c in data["chips"]] == [j["name"] for j in user_jars][: len(data["chips"])]


# --- update_profile -------------------------------------------------------------------------------------
def test_vi_khong_co_hu_nghia_vu_thi_hoi_hu_tra_kem_chip_hu_that(monkeypatch):
    tools = _tools()
    llm = make_llm([route_response(intent="profile_update", **OBLIGATION)])
    events, tools, _ = run_turn("tiền trọ 2,5 triệu, đóng ngày 1", llm=llm, tools=tools, monkeypatch=monkeypatch)
    _assert_asks_pay_jar(events, "profile_update")
    assert [("pay_jar" in c["obligation"]) for c in _calls(tools, "update_profile")] == [False]


def test_tra_loi_ten_hu_thi_goi_lai_update_profile_voi_pay_jar(monkeypatch):
    tools = _tools()
    chosen = _jars(with_obligation_jar=False)["data"]["jars"][-1]
    llm = make_llm([route_response(intent="profile_update", jar_text=f"Hũ {chosen['name']}", **OBLIGATION)])
    events, tools, writer = run_turn(f"Hũ {chosen['name']}", llm=llm, tools=tools, monkeypatch=monkeypatch)
    check_agui_order(events)
    first, retry = _calls(tools, "update_profile")
    assert "pay_jar" not in first["obligation"]
    assert retry["obligation"] == {**first["obligation"], "pay_jar": chosen["code"]}
    assert "confirm_token" not in retry
    assert [b["type"] for b in blocks_of(events)] == ["confirm_action"]
    assert writer.calls[0]["task"] == "confirm_action"


def test_vi_co_hu_nghia_vu_khong_hoi_va_gui_dung_tham_so_cu(monkeypatch):
    tools = FakeTools()
    llm = make_llm([route_response(intent="profile_update", **OBLIGATION)])
    events, tools, _ = run_turn("tiền trọ 2,5 triệu, đóng ngày 1", llm=llm, tools=tools, monkeypatch=monkeypatch)
    assert [name for name, _ in tools.calls] == ["get_jar_balances", "get_obligations", "update_profile"]  # đọc ví đầu lượt
    assert "pay_jar" not in _calls(tools, "update_profile")[0]["obligation"]
    assert [b["type"] for b in blocks_of(events)] == ["confirm_action"]


def test_loi_params_khac_o_vi_co_hu_nghia_vu_van_bao_loi_khong_hoi_hu(monkeypatch):
    tools = _tools(with_obligation_jar=True, update_profile=lambda a: _error(notices.GENERIC_ERROR_MESSAGE))
    llm = make_llm([route_response(intent="profile_update", **OBLIGATION)])
    events, tools, _ = run_turn("tiền trọ 2,5 triệu, đóng ngày 1", llm=llm, tools=tools, monkeypatch=monkeypatch)
    blocks = blocks_of(events)
    assert blocks[0]["type"] == "notice" and blocks[0]["data"]["code"] == ErrorCode.PARAMS_INVALID.value
    assert "clarify" not in [b["type"] for b in blocks]
    assert len(_calls(tools, "update_profile")) == 1


def test_vi_khong_co_hu_nghia_vu_loi_params_vi_ly_do_khac_thi_bao_loi_khong_hoi_hu(monkeypatch):
    """PARAMS_INVALID không phải vì thiếu hũ trả (ví dụ ngày sai: không có `field: pay_jar`) thì không hỏi hũ, dù ví không có hũ
    trả mặc định."""
    bad_day = _error("due_day phải từ 1 đến 31.", field="due_day")
    tools = _tools(update_profile=lambda a: bad_day)
    llm = make_llm([route_response(intent="profile_update", **OBLIGATION)])
    events, tools, _ = run_turn("tiền trọ 2,5 triệu, đóng ngày 1", llm=llm, tools=tools, monkeypatch=monkeypatch)
    blocks = blocks_of(events)
    assert blocks[0]["type"] == "notice" and blocks[0]["data"]["code"] == ErrorCode.PARAMS_INVALID.value
    assert "clarify" not in [b["type"] for b in blocks]
    assert len(_calls(tools, "update_profile")) == 1


# --- kiểm tra trước khi chi bằng Trả sau ---------------------------------------------------------------------
def test_kiem_tra_tra_sau_tren_vi_khong_co_hu_nghia_vu_hoi_hu_tra(monkeypatch):
    tools = _tools(affordability_check=_afford_needs_pay_jar)
    llm = make_llm([route_response(**ROUTE_AFFORD)])
    events, tools, _ = run_turn("mua tai nghe 1,2 triệu bằng Trả sau có ổn không", llm=llm, tools=tools, monkeypatch=monkeypatch)
    _assert_asks_pay_jar(events, "affordability")
    assert ["pay_jar" in a for a in _calls(tools, "affordability_check")] == [False]
    assert len(llm[1].calls) == 1  # chỉ router: hỏi lại không tốn lời gọi model


def test_kiem_tra_tra_sau_tra_loi_ten_hu_thi_goi_lai_voi_pay_jar(monkeypatch):
    tools = _tools(affordability_check=_afford_needs_pay_jar)
    chosen = _jars(with_obligation_jar=False)["data"]["jars"][-1]
    llm = make_llm([route_response(**ROUTE_AFFORD, jar_text=f"Hũ {chosen['name']}")])
    events, tools, writer = run_turn(f"Hũ {chosen['name']}", llm=llm, tools=tools, monkeypatch=monkeypatch)
    check_agui_order(events)
    first, retry = _calls(tools, "affordability_check")
    assert "pay_jar" not in first
    assert retry == {**first, "pay_jar": chosen["code"]}
    types = [b["type"] for b in blocks_of(events)]
    assert "affordability_card" in types and "clarify" not in types and "notice" not in types
    assert writer.calls[0]["task"] == "affordability"


def test_kiem_tra_loi_params_khac_khong_hoi_hu_tra(monkeypatch):
    tools = _tools(affordability_check=lambda a: _error("date không được trước hôm nay mô phỏng.", field="date"))
    llm = make_llm([route_response(**ROUTE_AFFORD)])
    events, tools, _ = run_turn("mua tai nghe 1,2 triệu bằng Trả sau có ổn không", llm=llm, tools=tools, monkeypatch=monkeypatch)
    blocks = blocks_of(events)
    assert "clarify" not in [b["type"] for b in blocks]
    assert [b["data"]["code"] for b in blocks if b["type"] == "notice"] == [ErrorCode.PARAMS_INVALID.value]
    assert len(_calls(tools, "affordability_check")) == 1


# --- what-if Trả sau -------------------------------------------------------------------------------------
def test_what_if_tra_sau_tren_vi_khong_co_hu_nghia_vu_hoi_hu_tra(monkeypatch):
    tools = _tools(run_scenario=_scenario_needs_pay_jar)
    llm = make_llm([route_response(**ROUTE_WHAT_IF)])
    events, tools, _ = run_turn(
        "Nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao", llm=llm, tools=tools, settings=CODE_FIRST, monkeypatch=monkeypatch
    )
    _assert_asks_pay_jar(events, "what_if")
    assert ["pay_jar" in a["scenario"] for a in _calls(tools, "run_scenario")] == [False]
    assert len(llm[1].calls) == 1  # router; không gọi Analyst khi chưa có kết quả kịch bản


def test_what_if_tra_sau_tra_loi_ten_hu_thi_chay_lai_kich_ban_voi_pay_jar(monkeypatch):
    tools = _tools(run_scenario=_scenario_needs_pay_jar)
    chosen = _jars(with_obligation_jar=False)["data"]["jars"][-1]
    llm = make_llm([route_response(**ROUTE_WHAT_IF, jar_text=f"Hũ {chosen['name']}"), tool_response("analyze", analysis())])
    events, tools, _ = run_turn(f"Hũ {chosen['name']}", llm=llm, tools=tools, settings=CODE_FIRST, monkeypatch=monkeypatch)
    check_agui_order(events)
    first, retry = _calls(tools, "run_scenario")
    assert "pay_jar" not in first["scenario"]
    assert retry["scenario"] == {**first["scenario"], "pay_jar": chosen["code"]}
    assert {k: v for k, v in retry.items() if k != "scenario"} == {k: v for k, v in first.items() if k != "scenario"}
    types = [b["type"] for b in blocks_of(events)]
    assert "clarify" not in types and "notice" not in types
    assert len(llm[1].calls) == 2  # router, Analyst: gọi lại tool không tốn lời gọi model


def test_what_if_loi_kich_ban_khac_khong_hoi_hu_tra(monkeypatch):
    tools = _tools(run_scenario=lambda a: classify_result("x", mcp_ok(fixture("run_scenario.error_invalid.json"))))
    llm = make_llm([route_response(**ROUTE_WHAT_IF)])
    events, tools, _ = run_turn(
        "Nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao", llm=llm, tools=tools, settings=CODE_FIRST, monkeypatch=monkeypatch
    )
    blocks = blocks_of(events)
    assert "clarify" not in [b["type"] for b in blocks]
    assert [b["type"] for b in blocks if b["type"] == "notice"]
    assert len(_calls(tools, "run_scenario")) == 1
