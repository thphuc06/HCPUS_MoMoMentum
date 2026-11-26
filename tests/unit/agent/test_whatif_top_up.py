"""Phương án what-if "chuyển bù vào hũ trả rồi mua" chuyển đúng phần hũ đó còn thiếu, số do mã tính và nhãn khớp số (#39, câu concert
sau Runtime v33: nhãn "chuyển phần thiếu" mà hành động chuyển cả giá món 1.500.000 ₫ khi hũ Giải trí 760.000 ₫ chỉ thiếu 740.000 ₫).

Nguồn của 1.500.000 ₫: giá món người dùng nói, Analyst chép vào `action.params.amount_vnd` vì đó là số duy nhất "có trong dữ liệu" gần
với phần thiếu (dữ liệu không có phần thiếu của hũ trả). Sửa: danh sách hũ của Analyst có phần còn thiếu của từng hũ (mã tính từ giá món
và số dư thật), số đó là căn cứ của bộ kiểm, và phương án chuyển bù vào hũ trả khoản mua mang đúng số đó (mã đặt, như phương án "dùng hũ
khác"). Router, planner và Analyst giả; `check_suitability` chấm bằng bộ luật thật của repo.
"""

from __future__ import annotations

import copy
from typing import Any

from agent_helpers import (
    FakeTools,
    check_agui_order,
    fixture,
    make_llm,
    mcp_ok,
    route_response,
    run_turn,
    tool_response,
)
from test_whatif_emergency import options_of, real_suitability
from yofina_agent.schemas import AnalysisOption
from yofina_agent.tools import classify_result
from yofina_agent.whatif import analyst_prompt, enforce_top_up

#: câu của test, không trùng câu eval hay câu người dùng trên app
Q = "neu mua ban phim co 1,5 trieu bang hu giai tri thi sao"
ROUTE = {"intent": "what_if", "amount_vnd": 1_500_000, "funding": "jar", "scenario_kind": "one_time_purchase", "jar_text": "giải trí"}
SCENARIO = {
    "scenario": {
        "kind": "one_time_purchase",
        "amount_vnd": 1_500_000,
        "funding_source": "jar",
        "jar_code": "giai_tri",
        "date": None,
        "label": "bàn phím",
    }
}
NARRATIVE = "Hũ Giải trí đang có 760.000 ₫, chưa đủ cho khoản 1.500.000 ₫."
KINDS = {"du_lich": "saving", "du_phong": "saving", "nghia_vu": "obligation"}


def _jars() -> dict[str, Any]:
    payload = copy.deepcopy(fixture("get_jar_balances.ok.json"))  # Giải trí 760.000 ₫, Du lịch 1.800.000 ₫
    for row in payload["data"]["jars"]:
        row["kind"] = KINDS.get(row["code"], "spending")
        if row["code"] == "du_lich":
            row["goal_vnd"] = 6_000_000
    return payload


def _top_up(amount: int, *, to_jar: str = "giai_tri", summary: str = "Chuyển phần thiếu từ hũ Du lịch sang Giải trí để đủ mua.") -> dict[str, Any]:
    return {
        "option_id": "top_up",
        "kind": "move_between_jars",
        "label": "Chuyển bù từ hũ Du lịch sang Giải trí rồi mua",
        "summary": summary,
        "proposal": {"kind": "move_between_jars", "funding_source": "jar", "jar_code": "du_lich", "amount_vnd": amount},
        "action": {"tool": "move_between_jars", "params": {"from_jar": "du_lich", "to_jar": to_jar, "amount_vnd": amount}},
    }


def _analysis(option: dict[str, Any]) -> dict[str, Any]:
    defer = {
        "option_id": "defer",
        "kind": "defer",
        "label": "Hoãn mua sau kỳ lương",
        "summary": "Hoãn tới sau 05/12 rồi xem lại.",
        "proposal": {"kind": "defer", "funding_source": "jar", "risk_level": "low"},
    }
    return {"narrative": NARRATIVE, "options": [defer, option], "follow_ups": []}


def _run(monkeypatch: Any, a: dict[str, Any]) -> tuple[list[Any], FakeTools]:
    tools = FakeTools(
        {
            "check_suitability": real_suitability,
            "get_jar_balances": lambda _a: classify_result("get_jar_balances", mcp_ok(_jars())),
        }
    )
    llm = make_llm([route_response(**ROUTE), tool_response("plan_scenario", SCENARIO), tool_response("analyze", a)])
    events, tools, _ = run_turn(Q, llm=llm, tools=tools, monkeypatch=monkeypatch)
    check_agui_order(events)
    return events, tools


def test_chuyen_bu_vao_hu_tra_chuyen_dung_phan_con_thieu_va_chu_khop_so(monkeypatch):
    events, tools = _run(monkeypatch, _analysis(_top_up(1_500_000)))
    moves = [a for n, a in tools.calls if n == "move_between_jars"]
    assert [m["amount_vnd"] for m in moves] == [740_000]  # 1.500.000 ₫ giá món trừ 760.000 ₫ số dư Giải trí
    sent = [a["proposal"] for n, a in tools.calls if n == "check_suitability" and a["proposal"]["kind"] == "move_between_jars"]
    assert [p["amount_vnd"] for p in sent] == [740_000]
    o = options_of(events)["top_up"]
    assert "740.000 ₫" in o["summary"] and "Du lịch" in o["summary"] and "Giải trí" in o["summary"]
    assert "740.000" not in o["label"] and o["status"] in ("ok", "tight")  # phương án qua bộ kiểm số, không bị bỏ


def test_model_da_chuyen_dung_phan_thieu_thi_giu_chu_cua_model(monkeypatch):
    said = "Chuyển 740.000 ₫ còn thiếu từ hũ Du lịch sang Giải trí rồi mua ngay."
    events, tools = _run(monkeypatch, _analysis(_top_up(740_000, summary=said)))
    assert [a["amount_vnd"] for n, a in tools.calls if n == "move_between_jars"] == [740_000]
    assert options_of(events)["top_up"]["summary"] == said


def test_danh_sach_hu_cua_analyst_co_phan_con_thieu_do_ma_tinh():
    rows = _jars()["data"]["jars"]
    prompt = analyst_prompt(Q, {}, rows, "2026-11-21", spend_amount=1_500_000)
    assert '"code": "giai_tri", "name": "Giải trí", "balance_text": "760.000 ₫", "covers_amount": false, "missing_text": "740.000 ₫"' in prompt
    assert '"code": "du_lich", "name": "Du lịch", "balance_text": "1.800.000 ₫", "covers_amount": true}' in prompt


def test_enforce_top_up_chi_ap_cho_chuyen_bu_vao_hu_tra_khoan_mua():
    rows = _jars()["data"]["jars"]
    other = AnalysisOption.model_validate(_top_up(1_500_000, to_jar="an_uong"))
    assert enforce_top_up(other, rows, 1_500_000, "giai_tri") is other  # chuyển sang hũ khác: không phải chuyển bù cho khoản mua
    move = AnalysisOption.model_validate(_top_up(1_500_000))
    assert enforce_top_up(move, rows, 1_500_000, None) is move  # kịch bản không mua bằng tiền hũ
    assert enforce_top_up(move, rows, 700_000, "giai_tri") is move  # hũ trả đã đủ tiền: không có phần thiếu
    fixed = enforce_top_up(move, rows, 1_500_000, "giai_tri")
    assert fixed.action is not None and fixed.action.params["amount_vnd"] == 740_000 and fixed.proposal.amount_vnd == 740_000
