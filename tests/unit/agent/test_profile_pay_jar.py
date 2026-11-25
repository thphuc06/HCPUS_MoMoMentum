"""Khai nghĩa vụ bằng chat khi ví không có hũ loại nghĩa vụ: hỏi hũ trả (khối `clarify`, chip hũ thật) rồi gọi lại với `pay_jar`.

Quy tắc hũ trả mặc định là của server (`yofina_core.wallet.resolve_obligation_pay_jar`); tool giả ở đây chỉ trả lỗi
PARAMS_INVALID khi chưa có `pay_jar` (như ledger với ví không có hũ nghĩa vụ), không tự tính gì.
"""

from __future__ import annotations

import copy
from typing import Any

from agent_helpers import FakeTools, blocks_of, check_agui_order, fixture, make_llm, mcp_ok, route_response, run_turn
from yofina_agent import notices
from yofina_agent.tools import ToolOutcome, classify_result
from yofina_core.errors import ErrorCode
from yofina_core.wallet import DEFAULT_OBLIGATION_JAR

OBLIGATION = {"obligation_name": "Tiền trọ", "obligation_kind": "rent", "amount_vnd": 2_500_000, "due_day": 1}


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


def _params_invalid(message: str) -> ToolOutcome:
    return classify_result("x", mcp_ok({"status": "ERROR", "code": ErrorCode.PARAMS_INVALID.value, "message": message}))


def _update_profile_needs_pay_jar(args: dict[str, Any]) -> ToolOutcome:
    """Như ledger với ví không có hũ nghĩa vụ: thiếu pay_jar thì PARAMS_INVALID, có thì trả bản xem trước."""
    if "pay_jar" not in args.get("obligation", {}):
        return _params_invalid(notices.GENERIC_ERROR_MESSAGE)
    return classify_result("x", mcp_ok(fixture("update_profile.needs_confirmation.json")))


def _tools(*, with_obligation_jar: bool, update_profile: Any = _update_profile_needs_pay_jar) -> FakeTools:
    jars = _jars(with_obligation_jar=with_obligation_jar)
    return FakeTools({"get_jar_balances": lambda a: classify_result("x", mcp_ok(jars)), "update_profile": update_profile})


def _update_calls(tools: FakeTools) -> list[dict[str, Any]]:
    return [args for name, args in tools.calls if name == "update_profile"]


def test_vi_khong_co_hu_nghia_vu_thi_hoi_hu_tra_kem_chip_hu_that(monkeypatch):
    tools = _tools(with_obligation_jar=False)
    llm = make_llm([route_response(intent="profile_update", **OBLIGATION)])
    events, tools, _ = run_turn("tiền trọ 2,5 triệu, đóng ngày 1", llm=llm, tools=tools, monkeypatch=monkeypatch)
    check_agui_order(events)
    blocks = blocks_of(events)
    assert blocks[0]["type"] == "clarify"
    assert "notice" not in [b["type"] for b in blocks]  # không có notice lỗi cụt đường
    data = blocks[0]["data"]
    assert data["slot"] == "jar" and data["question"] == notices.CLARIFY["pay_jar"]["question"]
    assert data["pending_intent"] == "profile_update"
    user_jars = _jars(with_obligation_jar=False)["data"]["jars"]
    assert [c["label"] for c in data["chips"]] == [j["name"] for j in user_jars][: len(data["chips"])]
    assert data["chips"]
    assert [("pay_jar" in c["obligation"]) for c in _update_calls(tools)] == [False]


def test_tra_loi_ten_hu_thi_goi_lai_update_profile_voi_pay_jar(monkeypatch):
    tools = _tools(with_obligation_jar=False)
    chosen = _jars(with_obligation_jar=False)["data"]["jars"][-1]
    llm = make_llm([route_response(intent="profile_update", jar_text=f"Hũ {chosen['name']}", **OBLIGATION)])
    events, tools, writer = run_turn(f"Hũ {chosen['name']}", llm=llm, tools=tools, monkeypatch=monkeypatch)
    check_agui_order(events)
    first, retry = _update_calls(tools)
    assert "pay_jar" not in first["obligation"]
    assert retry["obligation"] == {**first["obligation"], "pay_jar": chosen["code"]}
    assert "confirm_token" not in retry
    assert [b["type"] for b in blocks_of(events)] == ["confirm_action"]
    assert writer.calls[0]["task"] == "confirm_action"


def test_vi_co_hu_nghia_vu_khong_hoi_va_gui_dung_tham_so_cu(monkeypatch):
    tools = FakeTools()
    llm = make_llm([route_response(intent="profile_update", **OBLIGATION)])
    events, tools, _ = run_turn("tiền trọ 2,5 triệu, đóng ngày 1", llm=llm, tools=tools, monkeypatch=monkeypatch)
    assert [name for name, _ in tools.calls] == ["get_obligations", "update_profile"]
    assert "pay_jar" not in _update_calls(tools)[0]["obligation"]
    assert [b["type"] for b in blocks_of(events)] == ["confirm_action"]


def test_loi_params_khac_o_vi_co_hu_nghia_vu_van_bao_loi_khong_hoi_hu(monkeypatch):
    tools = _tools(with_obligation_jar=True, update_profile=lambda a: _params_invalid(notices.GENERIC_ERROR_MESSAGE))
    llm = make_llm([route_response(intent="profile_update", **OBLIGATION)])
    events, tools, _ = run_turn("tiền trọ 2,5 triệu, đóng ngày 1", llm=llm, tools=tools, monkeypatch=monkeypatch)
    blocks = blocks_of(events)
    assert blocks[0]["type"] == "notice" and blocks[0]["data"]["code"] == ErrorCode.PARAMS_INVALID.value
    assert "clarify" not in [b["type"] for b in blocks]
    assert len(_update_calls(tools)) == 1
