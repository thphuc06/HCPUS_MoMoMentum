"""Hạn mục tiêu lộ trình (V1, #39): router đổi hạn ra ngày ISO theo <ngay_hom_nay>, như Orchestrator what-if tính ngày.

Mã chỉ kiểm ngày có thật và sau hôm nay. Cách đọc cụm chỉ hạn bằng mã (`textutil.parse_goal_date`) chỉ là đường lùi khi router không
trả ngày, và chỉ khi đọc được TRỌN cụm; hai bên lệch rõ, hoặc không bên nào ra ngày, thì hỏi đúng một câu. Bỏ câu cố định "dùng hạn đã
khai, nếu có". Router giả, không gọi model. Câu số 10, 11 của báo cáo rà soát RR. Ngày mô phỏng của fixture là 21/11/2026.
"""

from __future__ import annotations

import logging
from datetime import date

import pytest
from agent_helpers import (
    blocks_of,
    check_agui_order,
    make_llm,
    route_response,
    run_turn,
    tool_response,
)
from test_live_pay_jar_chips import _events_of
from test_roadmap_create_turn import DEMO_JARS, answer_turn, calls_of, outline, roadmap_tools
from yofina_agent.clarify import GOAL_DATE_QUESTION, goal_jar_question
from yofina_agent.router import ROUTER_SYSTEM, build_router_prompt
from yofina_agent.schemas import IntentParams
from yofina_agent.textutil import parse_goal_date

TODAY = date(2026, 11, 21)
RR10 = "Lập kế hoạch để dành 12 triệu đi Nhật, hạn đầu năm sau, đừng cắt hũ Giải trí"  # câu số 10 của báo cáo RR
RR11 = "muon de danh 5 trieu trong hai thang nua"  # câu số 11 của báo cáo RR


def _goal_turn(monkeypatch, question, *, draft_jar="muc_tieu", **router):
    llm = make_llm([route_response(intent="roadmap", **router), tool_response("draft_roadmap", outline(draft_jar))])
    events, tools, _ = run_turn(question, llm=llm, tools=roadmap_tools(DEMO_JARS), monkeypatch=monkeypatch)
    check_agui_order(events)
    return events, tools, llm


def _goals(tools):
    return calls_of(tools, "optimize_allocation")


# --- trường có cấu trúc và prompt --------------------------------------------------------------------------
def test_router_tra_target_date_iso_hoac_null():
    assert IntentParams(target_date="2027-01-31").target_date == "2027-01-31"
    for bad in ("31/01/2027", "2027-02-30", "đầu năm sau", 20270131, ""):
        assert IntentParams(target_date=bad).target_date is None  # type: ignore[arg-type]


def test_prompt_router_co_ngay_hom_nay_dau_tin_va_quy_tac_target_date():
    text = build_router_prompt("q", "Người dùng: a", None, TODAY)
    assert text.startswith("<ngay_hom_nay>2026-11-21</ngay_hom_nay>\n")
    assert "<ngay_hom_nay>" not in build_router_prompt("q", "")  # không biết ngày thì không có thẻ
    assert "target_date" in ROUTER_SYSTEM and "<ngay_hom_nay>" in ROUTER_SYSTEM


def test_router_nhan_ngay_mo_phong_cua_lan_doc_vi(monkeypatch):
    _, _, llm = _goal_turn(monkeypatch, RR11, roadmap_action="create", amount_vnd=5_000_000)
    prompt = llm[1].calls[0]["messages"][0]["content"][0]["text"]
    assert prompt.startswith("<ngay_hom_nay>2026-11-21</ngay_hom_nay>")


# --- đường lùi bằng mã: chỉ khi đọc được trọn cụm -----------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "whole"),
    [
        ("trong 3 tháng", date(2027, 2, 21)),
        ("trong 5 tháng tới", None),  # luật đọc "5 tháng tới", còn chữ "trong": ngày của router quyết
        ("cuối tháng sau", date(2026, 12, 31)),
        ("31/12", date(2026, 12, 31)),
        ("đầu năm sau", None),  # luật chỉ hiểu "năm sau" (31/12 năm sau): không đọc trọn cụm thì không dùng
        ("ngày 15 tháng sau", None),
        ("hai tháng nữa", None),
        ("trước Tết", None),
    ],
)
def test_doc_han_bang_ma_chi_nhan_khi_doc_tron_cum(text, whole):
    assert parse_goal_date(text, TODAY, whole=True) == whole
    if text == "đầu năm sau":
        assert parse_goal_date(text, TODAY) == date(2027, 12, 31)  # cách đọc cũ (sai) vẫn còn cho người gọi khác


# --- câu số 10: "hạn đầu năm sau" -----------------------------------------------------------------------------
def test_rr10_han_router_tinh_duoc_dung_khong_phai_31_12(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    events, tools, _ = _goal_turn(
        monkeypatch, RR10, roadmap_action="create", amount_vnd=12_000_000, jar_text="Du lịch", date_text="đầu năm sau",
        target_date="2027-01-31",
    )  # fmt: skip
    assert _goals(tools) == [{"goals": [{"jar": "muc_tieu", "target_vnd": 12_000_000, "target_date": "2027-01-31"}]}]
    assert [b["type"] for b in blocks_of(events)] == ["roadmap"]
    (decided,) = _events_of(caplog, "goal_date")
    assert decided == {"event": "goal_date", "source": "router", "date": "2027-01-31"}


def test_rr10_router_khong_tinh_duoc_ngay_thi_hoi_mot_cau_khong_lap(monkeypatch):
    events, tools, _ = _goal_turn(
        monkeypatch, RR10, roadmap_action="create", amount_vnd=12_000_000, jar_text="Du lịch", date_text="đầu năm sau"
    )
    (block,) = blocks_of(events)
    assert block["type"] == "clarify" and block["data"]["slot"] == "date"
    assert block["data"]["question"] == GOAL_DATE_QUESTION and block["data"]["chips"] == []
    assert not _goals(tools) and not calls_of(tools, "save_roadmap")
    assert "TEXT_MESSAGE_CONTENT" not in [e.type.value for e in events]  # không câu "dùng hạn đã khai, nếu có"


# --- câu số 11: "trong hai tháng nữa", rồi trả lời câu hỏi hũ ------------------------------------------------------
def test_rr11_hoi_hu_roi_lap_giu_so_tien_va_han(monkeypatch):
    first, _, _ = _goal_turn(
        monkeypatch, RR11, roadmap_action="create", amount_vnd=5_000_000, date_text="trong hai tháng nữa", target_date="2027-01-21"
    )
    (clarify,) = blocks_of(first)
    assert clarify["data"]["slot"] == "jar"
    assert clarify["data"]["question"] == goal_jar_question(5_000_000, date(2027, 1, 21))
    # lượt trả lời: router chỉ trích hũ (không nhắc lại số tiền hay hạn); mã đọc lại đúng hai giá trị từ câu hỏi
    events, tools, _, _ = answer_turn(
        monkeypatch, DEMO_JARS, clarify, "Dự phòng",
        route_response(intent="roadmap", jar_text="Hũ Dự phòng", answers_pending=True), draft_jar="du_phong",
    )  # fmt: skip
    check_agui_order(events)
    assert _goals(tools) == [{"goals": [{"jar": "du_phong", "target_vnd": 5_000_000, "target_date": "2027-01-21"}]}]
    assert len(calls_of(tools, "save_roadmap")) == 1


# --- đối chiếu ngày router với cách đọc bằng mã ---------------------------------------------------------------------
def test_router_va_ma_lech_ro_thi_hoi_chip_hai_ngay_roi_lap_theo_ngay_chon(monkeypatch):
    router = {"roadmap_action": "create", "amount_vnd": 3_000_000, "jar_text": "Du lịch", "date_text": "cuối tháng sau"}
    events, tools, _ = _goal_turn(monkeypatch, "gom 3 triệu cuối tháng sau", **router, target_date="2027-03-01")
    (block,) = blocks_of(events)
    data = block["data"]
    assert data["slot"] == "date" and data["question"] == GOAL_DATE_QUESTION
    assert [(c["label"], c["value"]) for c in data["chips"]] == [
        ("Trước 01/03/2027", "Hạn 01/03/2027"),
        ("Trước 31/12/2026", "Hạn 31/12/2026"),
    ]
    assert not _goals(tools)
    # bấm chip ngày: router không nói gì thêm; mã đọc đúng ngày của chip, mục tiêu của câu trước giữ nguyên
    messages = [
        {"id": "m1", "role": "user", "content": "gom 3 triệu vào hũ Du lịch cuối tháng sau"},
        {"id": "m2", "role": "assistant", "content": block["fallback_text"]},
        {"id": "m3", "role": "user", "content": "Hạn 31/12/2026"},
    ]
    llm = make_llm([route_response(intent="roadmap"), tool_response("draft_roadmap", outline("muc_tieu"))])
    events, tools, _ = run_turn(None, llm=llm, tools=roadmap_tools(DEMO_JARS), monkeypatch=monkeypatch, messages=messages)
    check_agui_order(events)
    assert _goals(tools) == [{"goals": [{"jar": "muc_tieu", "target_vnd": 3_000_000, "target_date": "2026-12-31"}]}]


def test_router_va_ma_lech_it_thi_dung_ngay_router(monkeypatch):
    _, tools, _ = _goal_turn(
        monkeypatch, "gom 3 triệu cuối tháng sau", roadmap_action="create", amount_vnd=3_000_000, jar_text="Du lịch",
        date_text="cuối tháng sau", target_date="2026-12-30",
    )  # fmt: skip
    assert _goals(tools) == [{"goals": [{"jar": "muc_tieu", "target_vnd": 3_000_000, "target_date": "2026-12-30"}]}]


@pytest.mark.parametrize("model_date", [None, "2026-11-01"])  # router không trả ngày, hoặc trả ngày đã qua
def test_router_khong_co_ngay_dung_thi_lui_ve_cach_doc_tron_cum(monkeypatch, model_date):
    extra = {"target_date": model_date} if model_date else {}
    _, tools, _ = _goal_turn(
        monkeypatch, "gom 3 triệu trong 3 tháng", roadmap_action="create", amount_vnd=3_000_000, jar_text="Du lịch",
        date_text="trong 3 tháng", **extra,
    )  # fmt: skip
    assert _goals(tools) == [{"goals": [{"jar": "muc_tieu", "target_vnd": 3_000_000, "target_date": "2027-02-21"}]}]
