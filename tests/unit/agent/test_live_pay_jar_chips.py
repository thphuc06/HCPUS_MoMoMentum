"""Lỗi thấy trên app sau deploy đợt 3 (issue #39, `giamkhao1`, ví demo 8 hũ): câu chi cho chuyến đi không nêu hũ vẫn bị hỏi "trả bằng tiền
của hũ nào" và khối hỏi lại chỉ có 6 chip đầu (thiếu Du lịch, Đầu tư).

Log Runtime của hai lượt đó (09:42 và 09:45 giờ VN) có `ledger___get_jar_balances` rồi khối `clarify`, KHÔNG có sự kiện
`pay_jar_inferred` hay `pay_jar_unclear`: `Turn.infer_pay_jar` trả sớm, tức `tx_type` của ý định là None sau khi qua `IntentParams` (router để
trống, hoặc trả mã ngoài danh mục mà bộ kiểm bỏ đi). Runtime không ghi đầu ra router nên không phân biệt được hai trường hợp: nay có sự
kiện `routed` (mã và tên trường có giá trị, không chữ người dùng) và `router_tx_type_dropped`.

Router giả ở đây trả đúng dạng đã suy ra từ log (affordability, có số tiền, có cụm ngày, không có loại chi). Không gọi model.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from agent_helpers import blocks_of, check_agui_order, make_llm, route_response, run_turn
from test_infer_pay_jar import DEMO_8, _calls, _jar, _tools, _types
from yofina_agent import notices
from yofina_agent.router import routed_summary
from yofina_agent.schemas import IntentParams, IntentResult

from yofina_core.blocks import CLARIFY_MAX_CHIPS, parse_block

TRIP_Q = "tháng tới mình định đi chơi biển chừng 2 triệu có được không"  # câu của test, không trùng câu eval hay câu trên app
#: đầu ra router suy từ log của lượt trên app: không có `tx_type`
ROUTE_NO_TYPE = {"intent": "affordability", "amount_vnd": 2_000_000, "label": "đi chơi biển", "date_text": "tháng tới"}


def _events_of(caplog: pytest.LogCaptureFixture, name: str) -> list[dict[str, Any]]:
    out = []
    for rec in caplog.records:
        try:
            payload = json.loads(rec.getMessage())
        except ValueError:
            continue
        if isinstance(payload, dict) and payload.get("event") == name:
            out.append(payload)
    return out


def test_tai_lap_cau_chuyen_di_khong_co_loai_chi_thi_hoi_hu_voi_du_moi_hu_cua_vi(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    llm = make_llm([route_response(**ROUTE_NO_TYPE)])
    events, tools, _ = run_turn(TRIP_Q, llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch)
    check_agui_order(events)
    # đúng như log trên app: đọc hũ một lần, hỏi hũ, không kiểm, không có sự kiện suy hũ
    assert [n for n, _ in tools.calls] == ["get_jar_balances"] and not _calls(tools, "affordability_check")
    assert _types(events) == ["clarify"]
    assert not _events_of(caplog, "pay_jar_inferred") and not _events_of(caplog, "pay_jar_unclear")
    block = blocks_of(events)[0]
    data = block["data"]
    assert data["slot"] == "jar" and data["question"] == notices.CLARIFY["pay_jar"]["question"]
    # đủ 8 hũ của ví (trước đây cắt còn 6: không chọn được Du lịch, Đầu tư), theo thứ tự trong ví
    assert [c["label"] for c in data["chips"]] == [j["name"] for j in DEMO_8]
    assert parse_block(block).type == "clarify"  # khối 8 chip đúng hợp đồng
    # đầu ra router có trong log: ý định, tên các trường có giá trị, và KHÔNG có loại chi
    (routed,) = _events_of(caplog, "routed")
    assert routed["intent"] == "affordability" and "tx_type" not in routed
    assert routed["filled"] == ["amount_vnd", "date_text", "label"]


def test_router_tra_ma_loai_ngoai_danh_muc_thi_log_ghi_gia_tri_bi_bo(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    llm = make_llm([route_response(**ROUTE_NO_TYPE, tx_type="du_lich")])  # mã hũ chứ không phải mã loại
    events, _, _ = run_turn(TRIP_Q, llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch)
    assert _types(events) == ["clarify"]
    assert [e["value"] for e in _events_of(caplog, "router_tx_type_dropped")] == ["du_lich"]
    assert "tx_type" not in _events_of(caplog, "routed")[0]


def test_router_tra_loai_du_lich_thi_tinh_theo_hu_du_lich_khong_hoi(monkeypatch, caplog):
    """Cùng câu, router trích được `travel`: mã suy ra hũ goal "Du lịch" (hũ để dành không bị loại khỏi hũ chi được)."""
    caplog.set_level(logging.INFO)
    llm = make_llm([route_response(**ROUTE_NO_TYPE, tx_type="travel")])
    events, tools, _ = run_turn(TRIP_Q, llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch)
    assert _types(events) == ["notice", "affordability_card"]
    assert _calls(tools, "affordability_check")[0]["jar"] == "muc_tieu"
    assert _events_of(caplog, "routed")[0]["tx_type"] == "travel"
    assert _events_of(caplog, "pay_jar_inferred")[0]["jar"] == "muc_tieu"


def test_chip_ung_vien_dung_dau_roi_du_cac_hu_con_lai(monkeypatch):
    twins = [*DEMO_8, _jar("du_lich_he", "Du lịch", "saving", 100_000, purpose="goal")]
    llm = make_llm([route_response(**ROUTE_NO_TYPE, tx_type="travel")])
    events, _, _ = run_turn(TRIP_Q, llm=llm, tools=_tools(twins), monkeypatch=monkeypatch)
    labels = [c["label"] for c in blocks_of(events)[0]["data"]["chips"]]
    assert labels[:2] == ["Du lịch", "Du lịch"] and len(labels) == len(twins)
    assert labels[2:] == [j["name"] for j in DEMO_8 if j["code"] != "muc_tieu"]


def test_ten_hu_la_thi_hoi_lai_voi_du_moi_hu(monkeypatch):
    llm = make_llm([route_response(intent="affordability", amount_vnd=200_000, jar_text="Hũ Sở thích")])
    events, tools, _ = run_turn("lấy hũ Sở thích trả 200k được không", llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch)
    assert _types(events) == ["clarify"] and not _calls(tools, "affordability_check")
    assert [c["label"] for c in blocks_of(events)[0]["data"]["chips"]] == [j["name"] for j in DEMO_8]


def test_vi_toi_da_so_hu_thi_chip_khong_vuot_hop_dong(monkeypatch):
    many = [_jar(f"hu_{i}", f"Hũ số {i}", "spending", 10_000) for i in range(CLARIFY_MAX_CHIPS + 3)]
    llm = make_llm([route_response(intent="affordability", amount_vnd=50_000)])
    events, _, _ = run_turn("chi 50k có sao không", llm=llm, tools=_tools(many), monkeypatch=monkeypatch)
    block = blocks_of(events)[0]
    assert len(block["data"]["chips"]) == CLARIFY_MAX_CHIPS
    assert parse_block(block).type == "clarify"


def test_tom_tat_dau_ra_router_khong_mang_chu_nguoi_dung_hay_so_tien():
    r = IntentResult(
        intent="affordability",
        params=IntentParams(amount_vnd=1_234_567, jar_text="Hũ Bí mật", label="quà cho Lan", date_text="mai", tx_type="travel"),
        confidence=0.8,
        needs_clarification=False,
    )
    summary = routed_summary(r)
    text = json.dumps(summary, ensure_ascii=False)
    for secret in ("1234567", "Bí mật", "Lan", "mai"):
        assert secret not in text
    assert summary["tx_type"] == "travel" and summary["filled"] == ["amount_vnd", "date_text", "jar_text", "label"]
