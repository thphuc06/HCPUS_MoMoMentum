"""Orchestrator what-if gọi tool `knowledge___resolve_date` khi cần một ngày từ cách nói thời gian (#39, brief LL).

Model không tự tính ngày: người dùng nêu đủ ngày, tháng, năm thì model điền `date`; cách nói khác thì điền đặc tả `date_spec` (cùng
định nghĩa với đầu vào tool) và mã gọi tool qua Gateway (bước của kế hoạch, `PLAN_TOOLS`) trước khi chạy kịch bản. Không thêm lời gọi
model; tool call chỉ có khi model điền đặc tả. Kết quả tool (ngày và trường giải thích) là dữ kiện cho Analyst. Model và tool giả.
"""

from __future__ import annotations

import json
from typing import Any

from agent_helpers import (
    FakeTools,
    blocks_of,
    check_agui_order,
    fixture,
    make_llm,
    mcp_ok,
    route_response,
    run_turn,
    tool_response,
)
from test_tool_labels import contract_tools
from test_whatif import analysis
from yofina_agent import notices, trace
from yofina_agent.schemas import PLAN_TOOLS, PlanStep
from yofina_agent.tools import ToolKind, ToolOutcome, classify_result
from yofina_agent.whatif import ORCHESTRATOR_SYSTEM, OrchestratorOutput

from yofina_core import dates as D
from yofina_core.llm import bedrock_json_schema

QUESTION = "Nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau trước Tết thì sao"
ROUTED = {
    "intent": "what_if", "amount_vnd": 1_200_000, "funding": "credit", "scenario_kind": "bnpl_purchase", "label": "tai nghe",
    "date_text": "trước Tết",
}  # fmt: skip
TET_EVE_SPEC = {
    "anchor": "lunar_new_year", "period": None, "period_offset": None, "lunar_year": None, "day": None, "month": None,
    "year": None, "offset": None, "before": True,
}  # fmt: skip


def _scenario(**extra: Any) -> dict[str, Any]:
    base = {"kind": "bnpl_purchase", "amount_vnd": 1_200_000, "funding_source": "credit", "jar_code": None, "date": None, "label": "tai nghe"}
    return {"scenario": {**base, **extra}}


def _tools(resolve: dict[str, Any] | None = None) -> FakeTools:
    payload = resolve or fixture("resolve_date.ok.json")
    return FakeTools({"resolve_date": lambda _a: classify_result("resolve_date", mcp_ok(payload))})


def _turn(monkeypatch, scenario: dict[str, Any], tools: FakeTools, *extra: Any):
    llm = make_llm([route_response(**ROUTED), tool_response("plan_scenario", scenario), *extra])
    events, tools, _ = run_turn(QUESTION, llm=llm, tools=tools, monkeypatch=monkeypatch)
    check_agui_order(events)
    return events, tools, llm


def _calls(tools: FakeTools, name: str) -> list[dict[str, Any]]:
    return [args for tool, args in tools.calls if tool == name]


# --- hợp đồng: tool được phép, schema dùng chung, mô tả theo nguyên tắc ------------------------------------------------
def test_tool_nam_trong_danh_sach_tool_cua_ke_hoach():
    assert "knowledge___resolve_date" in PLAN_TOOLS
    assert PlanStep(tool="knowledge___resolve_date", args={"anchor": "today"}, parallel_group=0).tool == "knowledge___resolve_date"
    assert "resolve_date" in contract_tools() and trace.TOOL_LABELS["resolve_date"]


def test_schema_dac_ta_cua_orchestrator_cung_dinh_nghia_voi_dau_vao_tool():
    props = bedrock_json_schema(OrchestratorOutput)["properties"]["scenario"]["properties"]
    for key in ("date_spec", "end_date_spec"):
        assert list(props[key]["properties"]) == list(D.SPEC_FIELDS)
        assert "knowledge___resolve_date" in props[key]["description"]
    assert "đủ ngày, tháng, năm" in props["date"]["description"]


def test_prompt_orchestrator_goi_tool_thay_vi_tu_tinh_ngay():
    assert "knowledge___resolve_date" in ORCHESTRATOR_SYSTEM and "date_spec" in ORCHESTRATOR_SYSTEM
    assert "tính ra ngày cụ thể" not in ORCHESTRATOR_SYSTEM  # bản cũ: model tự tính ngày
    assert "thứ hai tuần sau" not in ORCHESTRATOR_SYSTEM.lower()  # không câu mẫu cách nói thời gian


# --- model điền đặc tả: một tool call, ngày của tool vào kịch bản, dữ kiện cho Analyst -----------------------------------
def test_dac_ta_cua_orchestrator_goi_tool_roi_chay_kich_ban_theo_ngay_cua_tool(monkeypatch):
    events, tools, llm = _turn(monkeypatch, _scenario(date_spec=TET_EVE_SPEC), _tools(), tool_response("analyze", analysis()))
    assert _calls(tools, "resolve_date") == [{"anchor": "lunar_new_year", "before": True}]
    (run,) = _calls(tools, "run_scenario")
    assert run["scenario"]["date"] == "2027-02-05" and "date_spec" not in run["scenario"]
    names = [e.tool_call_name for e in events if e.type.value == "TOOL_CALL_START"]
    assert names.index("knowledge___resolve_date") < names.index("forecast___run_scenario")
    assert len(llm[1].calls) == 3  # router, Orchestrator, Analyst: không thêm lời gọi model
    prompt = llm[1].calls[2]["messages"][0]["content"][0]["text"]
    data = json.loads(prompt.split("<du_lieu>\n", 1)[1].split("\n</du_lieu>", 1)[0])
    assert data["resolved_date"] == {
        "date_text": "05/02/2027", "day_month_text": "05/02", "weekday_text": "thứ Sáu", "days_from_today": 71,
        "anchor": "lunar_new_year", "anchor_date_text": "06/02/2027", "before_anchor": True,
        "lunar_new_year": {"name": "Đinh Mùi", "date_text": "06/02/2027", "year": 2027}, "next_occurrence": True,
    }  # fmt: skip


def test_nguoi_dung_neu_du_ngay_thi_khong_goi_tool(monkeypatch):
    _, tools, _ = _turn(monkeypatch, _scenario(date="2026-12-24"), _tools(), tool_response("analyze", analysis()))
    assert not _calls(tools, "resolve_date")
    assert _calls(tools, "run_scenario")[0]["scenario"]["date"] == "2026-12-24"


def test_tool_bao_ngay_da_qua_thi_noi_dung_loi_cua_tool_khong_chay_kich_ban(monkeypatch):
    error = fixture("resolve_date.error_in_past.json")
    events, tools, llm = _turn(monkeypatch, _scenario(date_spec={"anchor": "start_of", "period": "month"}), _tools(error))
    assert _calls(tools, "resolve_date") == [{"anchor": "start_of", "period": "month"}]
    assert not _calls(tools, "run_scenario")
    (block,) = blocks_of(events)
    assert block["type"] == "notice" and block["data"]["code"] == "DATE_IN_PAST"
    assert block["data"]["message"] == error["message"]
    assert block["data"]["title"] == notices.ERROR_TITLES["DATE_IN_PAST"]
    assert len(llm[1].calls) == 2  # không gọi Analyst


def test_dac_ta_sai_dang_la_loi_cua_model_khong_goi_tool(monkeypatch):
    # start_of thiếu period: như kịch bản sai, mã dựng kịch bản từ tham số router (đường dự phòng sẵn có)
    _, tools, _ = _turn(monkeypatch, _scenario(date_spec={"anchor": "start_of"}), _tools(), tool_response("analyze", analysis()))
    assert not _calls(tools, "resolve_date")
    assert _calls(tools, "run_scenario")[0]["scenario"]["kind"] == "bnpl_purchase"


# --- bảng "Vì sao" --------------------------------------------------------------------------------------------------------
def test_bang_vi_sao_co_nhan_va_ngay_da_tinh():
    payload = fixture("resolve_date.ok.json")
    outcome = ToolOutcome("knowledge___resolve_date", ToolKind.OK, payload=payload)
    assert trace.describe_tool(outcome) == ("Ngày tính theo lịch", "05/02/2027")
    (row,) = trace.data_used([outcome])
    assert (row["label"], row["value"], row["tool"]) == ("Ngày tính theo lịch", "05/02/2027", "knowledge___resolve_date")
