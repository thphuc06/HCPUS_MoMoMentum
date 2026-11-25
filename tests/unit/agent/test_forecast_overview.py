"""'Hũ nào sắp cạn?': agent đọc dự báo MỌI hũ và trả hũ nào cạn trước kỳ lương, không hỏi lại hũ nào (đi cảnh 24/11).

Lỗi gốc: router xếp câu này vào `lookup`/`forecast` không có hũ (hoặc tra số dư, hoặc kèm câu hỏi lại), `on_forecast` gọi `ask_which_jar`:
hiện thẻ số dư rồi model viết "Bạn muốn kiểm tra hũ nào sắp cạn?" (log Runtime: trace 341b5800…, chỉ `ledger___get_jar_balances` và
một lượt writer 49 token, không có `forecast___get_forecast`).

Kiểm toán prompt đợt 3: câu này nay chỉ đi một lớp. Router hiểu theo nghĩa của `lookup_kind=forecast` (jar_text null khi hỏi về mọi
hũ); mã không nhận câu hỏi lại của router cho `lookup` (`clarify.CLARIFY_INTENTS`), và `on_forecast` không có hũ thì đọc mọi hũ. Lớp
regex ép ý định (`route_runout_overview`) đã bỏ; khi model lỗi, luật dự phòng nhận ra bằng từ khóa chung như mọi câu dự báo.
"""

from __future__ import annotations

import copy
import json
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
from yofina_agent.fallback import classify_by_rules
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
        route_response(  # router tự hỏi lại hũ nào
            intent="forecast_lookup",
            clarify={"slot": "jar", "question": "Bạn muốn kiểm tra hũ nào sắp cạn?", "chips": []},
        ),
    ],
    ids=["du_bao_khong_hu", "router_hoi_lai"],
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
    assert _forecast_jars(tools) == list(_PLAN)  # luật dự phòng nhận ra câu dự báo; không có hũ thì đọc mọi hũ
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
    "text",
    ["Hũ nào sắp cạn?", CHIP, "Những hũ nào sẽ hết tiền trước kỳ lương?", "Các hũ có đủ tới kỳ lương không?", "Hũ nào bị hụt tháng này"],
)
def test_luat_du_phong_xep_cau_hu_nao_sap_can_vao_du_bao_khong_hu(text):
    r = classify_by_rules(text)
    assert r is not None and (r.intent, r.params.lookup_kind, r.params.jar_text) == ("lookup", "forecast", None)


def test_router_hoi_lai_cho_tra_cuu_bi_bo_qua():
    from yofina_agent.clarify import resolve_clarify
    from yofina_agent.schemas import IntentResult

    r = IntentResult.model_validate(
        {
            "intent": "lookup",
            "params": {"lookup_kind": "forecast"},
            "confidence": 0.8,
            "needs_clarification": True,
            "clarify": {"slot": "jar", "question": "Hũ nào?", "chips": []},
        }
    )
    assert resolve_clarify(r) is None


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


@pytest.mark.parametrize("with_date", [True, False], ids=["con_ngay_cu", "producer_da_bo_ngay"])
def test_hu_thua_khong_dua_ngay_can_cho_model(with_date):
    """#25: `runout_date_shown` sai (hũ thưa) thì bản gọn gửi model không có ngày cạn của hũ đó (kể cả khi tool cũ vẫn trả ngày),
    chỉ biết hũ có thể cạn trước kỳ lương; "hũ nào sắp cạn?" xếp hũ đó vào nhóm cần chú ý không nêu ngày."""
    p = _forecast_payload("giai_tri")
    p["data"]["runout_date_shown"] = False
    if not with_date:
        del p["data"]["runout_date"]
    c = compact_forecast(p)
    assert c["runout"] == {"may_run_out_before_payday": True}
    assert "29/11" not in json.dumps(c, ensure_ascii=False)
    ov = compact_forecast_overview([compact_forecast(_forecast_payload("an_uong")), c], [])
    assert [r["jar"] for r in ov["runout_before_payday"]] == ["Ăn uống"] and ov["tight"] == ["Giải trí"]
    assert "29/11" not in json.dumps(ov, ensure_ascii=False)
    # cờ đúng: như cũ
    shown = _forecast_payload("giai_tri")
    shown["data"]["runout_date_shown"] = True
    assert compact_forecast(shown)["runout"]["date_text"] == "29/11"
