"""Nguồn spec của what-if (#23): khóa `whatif_spec_source`.

- `model` (mặc định): như cũ, Orchestrator luôn gọi model vai `planner` (Sonnet), dựng bằng mã chỉ khi model không dùng được.
- `code_first`: router đủ tham số thì spec dựng bằng mã (`deterministic_spec`), không gọi model và tool đọc chạy ngay; không đủ thì
  gọi vai `small`, vai đó lỗi hay trả spec sai thì gọi `planner`; cả hai đều không được thì về đường dựng bằng mã như cũ.

Model và tool giả chỉ nằm ở đây và ở `agent_helpers`.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from agent_helpers import (
    FakeRecords,
    FakeTools,
    agent_settings,
    blocks_of,
    check_agui_order,
    make_llm,
    route_response,
    run_turn,
    tool_response,
)
from botocore.exceptions import ClientError
from test_whatif import ROUTE_WHAT_IF, SCENARIO, WHAT_IF_Q, analysis
from yofina_agent.schemas import IntentParams, IntentResult
from yofina_agent.settings import AgentSettings
from yofina_agent.tools import ToolOutcome
from yofina_agent.whatif import code_spec

from yofina_core.config import ConfigError

GATEWAY = {"YOFINA_GATEWAY_URL": "http://gateway.invalid/mcp"}
SONNET = "m-plan"  # model của vai planner trong `make_llm`; vai small là m-small-a, m-small-b
CODE_FIRST = agent_settings(whatif_spec_source="code_first")
BNPL_SPEC = {
    "kind": "bnpl_purchase",
    "amount_vnd": 1_200_000,
    "funding_source": "credit",
    "label": "tai nghe",
}
ROUTE_DEP = {
    "intent": "what_if",
    "amount_vnd": 300_000,
    "funding": "jar",
    "scenario_kind": "one_time_purchase",
    "jar_text": "Giải trí",
    "label": "dép",
}


class ReadTools(FakeTools):
    """Ghi số lời gọi model đã gửi lúc mỗi tool bắt đầu; tool trong `together` chỉ trả kết quả khi cả nhóm đã bắt đầu (gọi nối
    tiếp thì chờ quá giờ và bị ghi vào `waited_alone`)."""

    def __init__(self, client: Any, together: set[str]) -> None:
        super().__init__()
        self.client, self.together = client, together
        self.model_calls_at: dict[str, int] = {}
        self.started: set[str] = set()
        self.waited_alone: list[str] = []
        self.all_started = asyncio.Event()

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        short = name.split("___", 1)[-1]
        self.model_calls_at.setdefault(short, len(self.client.calls))
        if short in self.together:
            self.started.add(short)
            if self.started >= self.together:
                self.all_started.set()
            try:
                await asyncio.wait_for(self.all_started.wait(), 1.0)
            except TimeoutError:
                self.waited_alone.append(short)
        return await super().call(name, arguments)


def model_ids(llm: Any) -> list[str]:
    return [c["modelId"] for c in llm[1].calls]


def scenario_sent(tools: FakeTools) -> dict[str, Any]:
    return next(a for n, a in tools.calls if n == "run_scenario")["scenario"]


# --- khóa cấu hình ------------------------------------------------------------------------------
def test_mac_dinh_la_model_env_ghi_de_duoc_gia_tri_la_bi_tu_choi():
    assert AgentSettings.load(GATEWAY).whatif_spec_source == "model"
    s = AgentSettings.load({**GATEWAY, "YOFINA_WHATIF_SPEC_SOURCE": "code_first"})
    assert s.whatif_spec_source == "code_first"
    with pytest.raises(ConfigError, match="whatif_spec_source"):
        AgentSettings.load({**GATEWAY, "YOFINA_WHATIF_SPEC_SOURCE": "sonnet"})
    assert agent_settings().whatif_spec_source == "model"


# --- code_first: router đủ tham số -------------------------------------------------------------
def test_du_tham_so_thi_khong_goi_orchestrator_va_tool_doc_chay_ngay(monkeypatch):
    """Trả sau đủ số tiền: spec dựng bằng mã; nghĩa vụ và biểu phí bắt đầu cùng lúc ngay sau router; chỉ một lời gọi Sonnet (Analyst)."""
    llm = make_llm([route_response(**ROUTE_WHAT_IF), tool_response("analyze", analysis())])
    tools = ReadTools(llm[1], {"get_obligations", "get_fee_schedule"})
    events, _, _ = run_turn(
        WHAT_IF_Q, llm=llm, tools=tools, settings=CODE_FIRST, monkeypatch=monkeypatch
    )
    check_agui_order(events)
    assert model_ids(llm) == ["m-small-a", SONNET]  # router, Analyst; không có Orchestrator
    assert tools.waited_alone == []
    assert (
        tools.model_calls_at["get_obligations"] == 1
    )  # chỉ router đã gửi trước khi tool đọc đầu tiên bắt đầu
    assert scenario_sent(tools) == BNPL_SPEC
    r = events[-1].result
    assert r["model_calls"] == 2 and r["degraded"] is False
    assert "options" in [b["type"] for b in blocks_of(events)]


def test_du_tham_so_mua_bang_hu_doc_ca_du_bao_hu_va_kich_ban_truoc_cung_luc(monkeypatch):
    llm = make_llm([route_response(**ROUTE_DEP), tool_response("analyze", analysis())])
    tools = ReadTools(llm[1], {"get_obligations", "get_forecast", "list_scenarios"})
    events, _, _ = run_turn(
        "Nếu mua dép 300k từ hũ Giải trí thì sao",
        llm=llm,
        tools=tools,
        settings=CODE_FIRST,
        monkeypatch=monkeypatch,
    )
    check_agui_order(events)
    assert model_ids(llm).count(SONNET) == 1 and len(model_ids(llm)) == 2
    assert tools.waited_alone == []
    names = [n for n, _ in tools.calls]
    assert all(
        names.count(t) == 1 for t in ("get_obligations", "get_forecast", "list_scenarios")
    )  # kế hoạch dùng lại kết quả
    assert next(a for n, a in tools.calls if n == "get_forecast") == {"jar": "giai_tri"}
    assert scenario_sent(tools) == {
        "kind": "one_time_purchase", "amount_vnd": 300_000, "funding_source": "jar", "jar_code": "giai_tri", "label": "dép"
    }  # fmt: skip


# --- code_first: router chưa đủ tham số ---------------------------------------------------------
ROUTE_GYM = {
    "intent": "what_if",
    "amount_vnd": 300_000,
    "scenario_kind": "recurring_expense",
    "jar_text": "Giải trí",
    "label": "gym",
}
GYM_Q = "Nếu mình đăng ký gym 300 nghìn mỗi tháng từ ngày 1 tháng sau bằng hũ giải trí thì sao"
GYM = {
    "kind": "recurring_expense", "amount_vnd": 300_000, "funding_source": None, "jar_code": "giai_tri", "date": "2026-12-01",
    "label": "gym", "new_monthly_salary_vnd": None, "cycle": "monthly", "end_date": None, "from_jar": None, "to_jar": None,
    "delay_months": None,
}  # fmt: skip
GYM_SPEC = {
    "kind": "recurring_expense",
    "amount_vnd": 300_000,
    "jar_code": "giai_tri",
    "date": "2026-12-01",
    "label": "gym",
    "cycle": "monthly",
}


def test_thieu_tham_so_thi_orchestrator_goi_vai_small_khong_goi_sonnet(monkeypatch):
    """Chi lặp lại: mã không dựng được (cần chu kỳ, ngày) nên Orchestrator gọi vai small; Sonnet chỉ còn lời gọi của Analyst."""
    llm = make_llm(
        [
            route_response(**ROUTE_GYM),
            tool_response("plan_scenario", {"scenario": GYM}),
            tool_response("analyze", analysis()),
        ]
    )
    events, tools, _ = run_turn(GYM_Q, llm=llm, settings=CODE_FIRST, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert model_ids(llm) == ["m-small-a", "m-small-a", SONNET]
    orchestrator = llm[1].calls[1]
    assert orchestrator["toolConfig"]["toolChoice"] == {"tool": {"name": "plan_scenario"}}
    assert scenario_sent(tools) == GYM_SPEC
    assert events[-1].result["degraded"] is False


def test_vai_small_loi_thi_sonnet_du_phong_va_luot_khong_suy_giam(monkeypatch):
    """Nova và Haiku đều bị throttle (AllModelsFailed của vai small): Sonnet dựng spec; lượt không bị coi là mất model nên
    Analyst vẫn chạy và không có notice suy giảm."""
    throttle = ClientError({"Error": {"Code": "ThrottlingException", "Message": "x"}}, "Converse")
    llm = make_llm(
        [
            route_response(**ROUTE_GYM),
            throttle,
            throttle,
            tool_response("plan_scenario", {"scenario": GYM}),
            tool_response("analyze", analysis()),
        ]
    )
    events, tools, _ = run_turn(GYM_Q, llm=llm, settings=CODE_FIRST, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert model_ids(llm) == ["m-small-a", "m-small-a", "m-small-b", SONNET, SONNET]
    assert scenario_sent(tools) == GYM_SPEC
    r = events[-1].result
    assert r["degraded"] is False and "notice" not in [b["type"] for b in blocks_of(events)]


def test_vai_small_tra_spec_sai_thi_sonnet_du_phong(monkeypatch):
    bad = {"scenario": {**GYM, "jar_code": "hu_khong_ton_tai"}}
    llm = make_llm(
        [
            route_response(**ROUTE_GYM),
            tool_response("plan_scenario", bad),
            tool_response("plan_scenario", {"scenario": GYM}),
            tool_response("analyze", analysis()),
        ]
    )
    _, tools, _ = run_turn(GYM_Q, llm=llm, settings=CODE_FIRST, monkeypatch=monkeypatch)
    assert model_ids(llm) == ["m-small-a", "m-small-a", SONNET, SONNET]
    assert scenario_sent(tools) == GYM_SPEC


def test_ca_hai_vai_tra_spec_sai_thi_ve_duong_dung_bang_ma_nhu_cu(monkeypatch):
    """Router có cụm ngày nên mã không tự dựng (code_spec trả None); cả small lẫn Sonnet trả mã hũ lạ: về đường dự phòng cũ
    (`deterministic_spec` + `validate_spec`), giống hệt khi Orchestrator Sonnet trả spec sai ở chế độ `model`."""
    bad = {"scenario": {**SCENARIO["scenario"], "jar_code": "hu_khong_ton_tai"}}
    route = route_response(**ROUTE_WHAT_IF, date_text="thứ sáu tuần sau")
    llm = make_llm(
        [
            route,
            tool_response("plan_scenario", bad),
            tool_response("plan_scenario", bad),
            tool_response("analyze", analysis()),
        ]
    )
    events, tools, _ = run_turn(WHAT_IF_Q, llm=llm, settings=CODE_FIRST, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert model_ids(llm) == ["m-small-a", "m-small-a", SONNET, SONNET]
    assert scenario_sent(tools) == BNPL_SPEC
    assert "options" in [b["type"] for b in blocks_of(events)]


def test_cum_ngay_cua_router_thi_khong_dung_spec_bang_ma():
    jars = [{"code": "giai_tri", "name": "Giải trí"}]
    with_date = IntentResult(
        intent="what_if",
        params=IntentParams(
            amount_vnd=1_200_000,
            funding="credit",
            scenario_kind="bnpl_purchase",
            label="tai nghe",
            date_text="thứ sáu tuần sau",
        ),
        confidence=0.9,
        needs_clarification=False,
    )
    assert code_spec(with_date, jars) is None
    plain = with_date.model_copy(
        update={"params": with_date.params.model_copy(update={"date_text": None})}
    )
    assert code_spec(plain, jars) == BNPL_SPEC


def test_router_khong_trich_loai_kich_ban_thi_khong_dung_spec_bang_ma():
    """Router để `scenario_kind` trống: mã không tự đoán loại từ nguồn tiền (Trả sau, hũ) dù đủ số tiền và hũ."""
    jars = [{"code": "giai_tri", "name": "Giải trí"}]
    for params in (
        IntentParams(amount_vnd=1_200_000, funding="credit", label="tai nghe"),
        IntentParams(amount_vnd=300_000, funding="jar", jar_text="Giải trí", label="gym"),
    ):
        r = IntentResult(intent="what_if", params=params, confidence=0.9, needs_clarification=False)
        assert code_spec(r, jars) is None


def test_code_first_router_khong_trich_loai_thi_goi_vai_small_va_mot_buoc_orchestrator(monkeypatch):
    """Câu chi lặp lại mà router bỏ sót loại: không chạy như mua một lần bằng mã; Orchestrator gọi vai small dựng spec chi lặp lại,
    và bản ghi lượt chỉ có MỘT bước `orchestrator`."""
    route = {k: v for k, v in ROUTE_GYM.items() if k != "scenario_kind"}
    route["funding"] = "jar"
    llm = make_llm(
        [
            route_response(**route),
            tool_response("plan_scenario", {"scenario": GYM}),
            tool_response("analyze", analysis()),
        ]
    )
    records = FakeRecords()
    events, tools, _ = run_turn(
        GYM_Q, llm=llm, settings=CODE_FIRST, monkeypatch=monkeypatch, records=records
    )
    check_agui_order(events)
    assert model_ids(llm) == ["m-small-a", "m-small-a", SONNET]
    assert scenario_sent(tools) == GYM_SPEC
    (rec,) = records.saved
    assert [s["step"] for s in rec["step_timings"]].count("orchestrator") == 1
