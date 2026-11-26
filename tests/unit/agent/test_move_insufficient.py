"""Chuyển hũ khi hũ nguồn không đủ tiền (#39, lỗi 2 của báo cáo NN).

Ca thật (Runtime v32, 26/11): "Mình muốn chuyển ngay 3 triệu từ Dự phòng sang Ăn uống" (Dự phòng có 2.700.000 ₫) chỉ ra một thông báo
lỗi "Hũ Dự phòng không đủ số dư" kèm mã thô INSUFFICIENT_FUNDS. Lượt chuyển phải nói số dư thật của hũ nguồn và hỏi lại (chuyển phần
có thể), không chỉ báo lỗi. Router giả, không gọi model.
"""

from __future__ import annotations

import copy

from agent_helpers import (
    FakeTools,
    blocks_of,
    check_agui_order,
    fixture,
    make_llm,
    mcp_ok,
    route_response,
    run_turn,
)
from yofina_agent import notices
from yofina_agent.tools import classify_result

INSUFFICIENT = {"status": "ERROR", "code": "INSUFFICIENT_FUNDS", "message": "Hũ Dự phòng không đủ số dư."}


def _move(monkeypatch, amount: int, *, balances: dict | None = None, error: dict = INSUFFICIENT):
    jars = copy.deepcopy(fixture("get_jar_balances.ok.json"))
    for row in jars["data"]["jars"]:
        if balances and row["code"] in balances:
            row["balance_vnd"] = balances[row["code"]]
    tools = FakeTools(
        {
            "get_jar_balances": lambda _a: classify_result("get_jar_balances", mcp_ok(jars)),
            "move_between_jars": lambda _a: classify_result("move_between_jars", mcp_ok(error)),
        }
    )
    routed = route_response(intent="move", from_jar_text="Dự phòng", to_jar_text="Ăn uống", amount_vnd=amount)
    events, tools, writer = run_turn(
        "Mình muốn chuyển ngay 3 triệu từ Dự phòng sang Ăn uống", llm=make_llm([routed]), tools=tools, monkeypatch=monkeypatch
    )
    check_agui_order(events)
    return events, tools, writer


def test_khong_du_so_du_noi_so_du_that_va_hoi_chuyen_phan_co_the(monkeypatch):
    events, tools, writer = _move(monkeypatch, 3_000_000)
    assert [args for name, args in tools.calls if name == "move_between_jars"] == [
        {"from_jar": "du_phong", "to_jar": "an_uong", "amount_vnd": 3_000_000}
    ]
    types = [b["type"] for b in blocks_of(events)]
    # không còn khối lỗi mang mã thô; câu hỏi lại nêu số dư thật, số cần và hũ đích, chip chuyển đúng số dư hiện có
    assert "notice" not in types and types == ["jar_summary", "clarify"]
    data = blocks_of(events)[-1]["data"]
    assert data["question"] == notices.MOVE_SHORT_QUESTION.format(
        src="Dự phòng", balance="2.700.000 ₫", amount="3.000.000 ₫", dst="Ăn uống"
    )
    assert data["question"].count("?") == 1 and "INSUFFICIENT_FUNDS" not in data["question"]
    assert [(c["label"], c["value"]) for c in data["chips"]] == [
        ("Chuyển 2.700.000 ₫", "Chuyển 2.700.000 ₫ từ hũ Dự phòng sang hũ Ăn uống")
    ]
    assert data["pending_intent"] == "move" and data["allow_free_text"] is True
    assert not writer.calls


def test_hu_nguon_het_tien_thi_noi_so_du_va_hoi_hu_khac_khong_co_chip_chuyen(monkeypatch):
    events, _, _ = _move(monkeypatch, 300_000, balances={"du_phong": 0})
    data = blocks_of(events)[-1]["data"]
    assert blocks_of(events)[-1]["type"] == "clarify"
    assert data["question"] == notices.MOVE_EMPTY_QUESTION.format(
        src="Dự phòng", balance="0 ₫", amount="300.000 ₫", dst="Ăn uống"
    )
    assert data["chips"] == []


def test_so_du_doc_o_luot_nay_du_ma_tool_van_bao_thieu_thi_bao_loi_cua_tool(monkeypatch):
    # số dư vừa đổi giữa lần đọc ví và lần chuẩn bị chuyển: không có số dư nào để nói, giữ lời tiếng Việt của tool
    events, _, _ = _move(monkeypatch, 1_000_000)
    notice = [b for b in blocks_of(events) if b["type"] == "notice"]
    assert len(notice) == 1 and notice[0]["data"]["message"] == "Hũ Dự phòng không đủ số dư."
    assert not [b for b in blocks_of(events) if b["type"] == "clarify"]
