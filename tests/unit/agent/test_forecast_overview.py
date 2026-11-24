"""'Hũ nào sắp cạn?': agent đọc dự báo MỌI hũ và trả hũ nào cạn trước kỳ lương, không hỏi lại hũ nào (đi cảnh 24/11).

Lỗi gốc: router xếp câu này vào `lookup`/`forecast` không có hũ (hoặc tra số dư, hoặc kèm câu hỏi lại), `on_forecast` gọi `ask_which_jar`:
hiện thẻ số dư rồi model viết "Bạn muốn kiểm tra hũ nào sắp cạn?" (log Runtime: trace 341b5800…, chỉ `ledger___get_jar_balances` và
một lượt writer 49 token, không có `forecast___get_forecast`).
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from agent_helpers import (
    FakeTools,
    FakeUsage,
    blocks_of,
    check_agui_order,
    fixture,
    make_llm,
    mcp_ok,
    route_response,
    run_turn,
)
from yofina_agent.compact import compact_forecast, compact_forecast_overview
from yofina_agent.router import asks_which_jar_runs_out, route_runout_overview
from yofina_agent.schemas import IntentParams, IntentResult
from yofina_agent.tools import classify_result
from yofina_agent.turn import forecast_overview_text

CHIP = "Hũ nào của mình sắp cạn?"  # prompt của chip "Hũ nào sắp cạn?" (notices.SUGGESTION_ITEMS)

#: (mã, tên, trạng thái, ngày cạn) của bảy hũ trong fixture get_jar_balances: hai hũ cạn trước lương 05/12, một hũ sát
_PLAN = {
    "an_uong": ("Ăn uống", "short", "2026-11-23"),
    "di_lai": ("Đi lại", "ok", None),
    "hoa_don": ("Hóa đơn", "tight", None),
    "giai_tri": ("Giải trí", "short", "2026-11-29"),
    "du_lich": ("Du lịch", "ok", None),
    "du_phong": ("Dự phòng", "ok", None),
    "nghia_vu": ("Nghĩa vụ", "ok", None),
}


def _forecast_payload(
    code: str, plan: dict[str, tuple[str, str, str | None]] = _PLAN
) -> dict[str, Any]:
    name, status, runout = plan[code]
    p = copy.deepcopy(fixture("get_forecast.ok.json"))
    d = p["data"]
    d["jar"] = {**d["jar"], "code": code, "name": name}
    d["status"] = status
    d["runout_date"] = runout
    if runout is None:
        d["p_shortfall"] = 0.05 if status == "ok" else 0.3
    return p


def _tools(
    plan: dict[str, tuple[str, str, str | None]] = _PLAN, fail: set[str] = frozenset()
) -> FakeTools:
    def forecast(args: dict[str, Any]) -> Any:
        if args["jar"] in fail:
            return classify_result("x", mcp_ok(fixture("get_forecast.error_unavailable.json")))
        return classify_result("x", mcp_ok(_forecast_payload(args["jar"], plan)))

    return FakeTools({"get_forecast": forecast})


def _forecast_jars(tools: FakeTools) -> list[str]:
    return [a["jar"] for n, a in tools.calls if n == "get_forecast"]


def _text(events: list[Any]) -> str:
    return "".join(e.delta for e in events if e.type.value == "TEXT_MESSAGE_CONTENT")


EXPECTED = (
    "Trước kỳ lương 05/12 có 2 hũ dự kiến cạn: Ăn uống ngày 23/11, Giải trí ngày 29/11. "
    "Hũ Hóa đơn đang sát số dư trước kỳ lương. Các hũ còn lại đủ tới kỳ lương. Biểu đồ bên dưới là của hũ Ăn uống."
)


@pytest.mark.parametrize(
    "routed",
    [
        route_response(intent="forecast_lookup"),  # đúng như log: dự báo, không có hũ
        route_response(intent="balance_lookup"),  # router xếp nhầm vào tra số dư
        route_response(  # router tự hỏi lại hũ nào
            intent="forecast_lookup",
            clarify={"slot": "jar", "question": "Bạn muốn kiểm tra hũ nào sắp cạn?", "chips": []},
        ),
    ],
    ids=["du_bao_khong_hu", "tra_so_du", "router_hoi_lai"],
)
def test_hu_nao_sap_can_doc_du_bao_moi_hu_va_khong_hoi_lai(monkeypatch, routed):
    tools = _tools()
    events, tools, writer = run_turn(
        CHIP, llm=make_llm([routed]), tools=tools, monkeypatch=monkeypatch
    )
    check_agui_order(events)
    assert _forecast_jars(tools) == list(_PLAN)  # mọi hũ của người dùng, theo thứ tự hiển thị
    kinds = [b["type"] for b in blocks_of(events)]
    assert "clarify" not in kinds and "jar_summary" not in kinds
    timeline = [b for b in blocks_of(events) if b["type"] == "forecast_timeline"]
    assert len(timeline) == 1 and timeline[0]["data"]["jar"]["code"] == "an_uong"  # hũ cạn sớm nhất
    assert _text(events) == EXPECTED
    assert "?" not in _text(events)
    assert writer.calls == []  # câu do mã dựng từ số của tool, không qua model viết


def test_hu_nao_sap_can_khi_model_loi_van_doc_du_bao_moi_hu(monkeypatch):
    llm = make_llm([], FakeUsage(caps_hit={"m-small-a", "m-small-b"}))
    events, tools, writer = run_turn(CHIP, llm=llm, tools=_tools(), monkeypatch=monkeypatch)
    check_agui_order(events)
    assert _forecast_jars(tools) == list(_PLAN)  # luật dự phòng không nhận ra câu này; mã vẫn nhận
    assert _text(events) == EXPECTED
    assert llm[1].calls == [] and writer.calls == []


def test_khong_hu_nao_can_va_mot_hu_loi_thi_noi_ro(monkeypatch):
    plan = {code: (name, "ok", None) for code, (name, _, _) in _PLAN.items()}
    events, tools, _ = run_turn(
        "Có hũ nào không đủ tới kỳ lương không?",
        llm=make_llm([route_response(intent="forecast_lookup")]),
        tools=_tools(plan, fail={"du_lich"}),
        monkeypatch=monkeypatch,
    )
    check_agui_order(events)
    assert len(_forecast_jars(tools)) >= len(plan)
    assert (
        _text(events)
        == "Chưa hũ nào dự kiến cạn trước kỳ lương 05/12. Chưa có dự báo cho hũ Du lịch."
    )
    assert not [b for b in blocks_of(events) if b["type"] == "forecast_timeline"]


def test_hoi_mot_hu_cu_the_van_chi_doc_mot_hu(monkeypatch):
    _, tools, writer = run_turn(
        "hũ ăn uống còn trụ được bao lâu",
        llm=make_llm([route_response(intent="forecast_lookup", jar_text="ăn uống")]),
        tools=_tools(),
        monkeypatch=monkeypatch,
    )
    assert _forecast_jars(tools) == ["an_uong"] and writer.calls[0]["task"] == "forecast"


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("Hũ nào sắp cạn?", True),
        (CHIP, True),
        ("Những hũ nào sẽ hết tiền trước kỳ lương?", True),
        ("Các hũ có đủ tới kỳ lương không?", True),
        ("Hũ nào bị hụt tháng này", True),
        ("hũ ăn uống còn trụ được bao lâu", False),
        ("Số dư các hũ của mình", False),
        ("Chuyển 100k từ hũ Du lịch sang hũ Ăn uống", False),
    ],
)
def test_nhan_ra_cau_hoi_hu_nao_sap_can(text, want):
    assert asks_which_jar_runs_out(text) is want


def test_khong_ep_y_dinh_khac_cua_router():
    what_if = IntentResult(
        intent="what_if",
        params=IntentParams(scenario_kind="bnpl_purchase", amount_vnd=1_200_000, funding="credit"),
        confidence=0.9,
        needs_clarification=False,
    )
    assert (
        route_runout_overview(
            what_if, "Nếu mua tai nghe 1,2 triệu bằng Trả sau thì hũ nào sắp cạn?"
        )
        is what_if
    )
    forced = route_runout_overview(None, CHIP)
    assert forced is not None and (
        forced.intent,
        forced.params.lookup_kind,
        forced.params.jar_text,
    ) == (
        "lookup",
        "forecast",
        None,
    )


def test_ban_gon_va_cau_tra_loi_chi_chep_so_cua_tool():
    compacts = [compact_forecast(_forecast_payload(c)) for c in _PLAN]
    ov = compact_forecast_overview(compacts, [])
    assert [r["jar"] for r in ov["runout_before_payday"]] == ["Ăn uống", "Giải trí"]
    assert ov["runout_before_payday"][0] == {
        "jar": "Ăn uống",
        "date_text": "23/11",
        "days_from_today": 2,
        "days_before_payday": 12,
    }
    assert ov["tight"] == ["Hóa đơn"] and ov["payday"]["date_text"] == "05/12"
    one = compact_forecast_overview([compacts[0], compacts[1]], [])
    assert (
        forecast_overview_text(one)
        == "Hũ Ăn uống dự kiến cạn ngày 23/11, sớm 12 ngày so với kỳ lương 05/12. Các hũ còn lại đủ tới kỳ lương."
    )
