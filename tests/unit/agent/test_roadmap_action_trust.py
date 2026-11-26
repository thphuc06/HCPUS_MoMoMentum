"""Lộ trình tin `roadmap_action` của router (C2, #39): bỏ luật "câu lộ trình có số tiền hoặc hạn thì LUÔN lập bản mới".

Router "view" thì chỉ xem, không bao giờ lưu bản mới hay bỏ bản đang chờ, kể cả khi câu nêu số tiền hoặc hạn. Router để trống mà câu
nêu mục tiêu: đã có bản đang dùng thì hỏi đúng một câu với hai chip (lập bản mới, xem bản đang dùng); chưa có bản nào thì lập. Router
giả, không gọi model. Câu số 9 của báo cáo rà soát RR.
"""

from __future__ import annotations

from datetime import date

import pytest
from agent_helpers import (
    FakeWriter,
    blocks_of,
    check_agui_order,
    make_llm,
    route_response,
    run_turn,
)
from test_roadmap_create_turn import DEMO_JARS, calls_of, roadmap_tools
from yofina_agent.clarify import (
    GOAL_DATE_QUESTION,
    ROADMAP_CHOICE_CHIPS,
    goal_jar_question,
    recognize_prompt,
    roadmap_choice_question,
)
from yofina_agent.notices import ROADMAP_GOAL_JAR_QUESTION

RR9 = "lo trinh hien tai co kip gom 20 trieu truoc Tet khong"  # câu số 9 của báo cáo RR
GOAL = {"amount_vnd": 20_000_000, "date_text": "trước Tết", "date_spec": {"anchor": "lunar_new_year", "before": True}}  # đặc tả hạn (V1)
TET_EVE = date(2027, 2, 5)  # ngày liền trước Tết Đinh Mùi (06/02/2027)
TET = date(2027, 2, 6)  # mốc đã dùng của hạn "trước Tết": câu hỏi nói "trước {mốc}", không nói "trước" ngày liền trước mốc
CHOICE_Q = roadmap_choice_question(20_000_000, "trước Tết", TET_EVE, before=TET)
#: hạn đã tính từ đặc tả, làm dữ kiện cho writer (mốc đã dùng, năm Tết): nói được "trước Tết" kèm ngày
TET_FACTS = {
    "date_text": "05/02/2027", "day_month_text": "05/02", "weekday_text": "thứ Sáu", "days_from_today": 76,
    "anchor": "lunar_new_year", "anchor_date_text": "06/02/2027", "before_anchor": True,
    "lunar_new_year": {"name": "Đinh Mùi", "date_text": "06/02/2027", "year": 2027}, "next_occurrence": True,
}  # fmt: skip
WRITES = {"save_roadmap", "optimize_allocation", "move_between_jars"}


def _turn(monkeypatch, routed, *, latest="ok", question=RR9, messages=None):
    llm = make_llm([routed])
    writer = FakeWriter("Bản đang dùng chưa có bước nào cho mục tiêu này.")
    events, tools, writer = run_turn(
        question if messages is None else None,
        llm=llm, tools=roadmap_tools(DEMO_JARS, latest=latest), monkeypatch=monkeypatch, writer=writer, messages=messages,
    )  # fmt: skip
    check_agui_order(events)
    return events, tools, writer


def _choice_messages(chip_value: str) -> list[dict[str, str]]:
    return [
        {"id": "m1", "role": "user", "content": RR9},
        {"id": "m2", "role": "assistant", "content": CHOICE_Q},
        {"id": "m3", "role": "user", "content": chip_value},
    ]


def _chip(action: str) -> str:
    return next(value for _, value, a in ROADMAP_CHOICE_CHIPS if a == action)


def test_router_noi_xem_thi_chi_xem_du_cau_co_so_tien_va_han(monkeypatch):
    events, tools, writer = _turn(monkeypatch, route_response(intent="roadmap", roadmap_action="view", **GOAL))
    assert [tool for tool, _ in tools.calls] == ["get_jar_balances", "get_roadmap"]
    assert calls_of(tools, "get_roadmap") == [{"which": "active"}]  # xem là xem bản đang dùng (#39)
    assert [b["type"] for b in blocks_of(events)] == ["roadmap"]
    # không lưu bản mới, nên cũng không bỏ bản đề xuất đang chờ (lưu bản mới là việc bỏ bản đang chờ)
    assert not {tool for tool, _ in tools.calls} & WRITES
    (call,) = writer.calls
    # mục tiêu người dùng nêu là dữ kiện cho writer (số đã định dạng để kiểm căn cứ, hạn đã tính kèm mốc), không thành bản mới
    assert call["task"] == "roadmap"
    assert call["compact"]["muc_tieu_nguoi_dung_hoi"] == {
        "so_tien_text": "20.000.000 ₫", "so_tien_short_text": "20 triệu", "han_nguoi_dung_noi": "trước Tết", "han": TET_FACTS,
    }  # fmt: skip


def test_router_de_trong_ma_da_co_ban_dang_dung_thi_hoi_mot_cau_hai_chip(monkeypatch):
    events, tools, writer = _turn(monkeypatch, route_response(intent="roadmap", **GOAL))
    (block,) = blocks_of(events)
    assert block["type"] == "clarify"
    data = block["data"]
    # câu hỏi nói lại mục tiêu (số tiền, đúng chữ chỉ hạn người dùng nói kèm mốc đã dùng: hạn là ngày liền trước mốc đó)
    assert data["question"] == CHOICE_Q and data["question"].count("?") == 1
    assert "20.000.000 ₫" in CHOICE_Q and "“trước Tết” (trước 06/02/2027)" in CHOICE_Q and "05/02/2027" not in CHOICE_Q
    assert [(c["label"], c["value"]) for c in data["chips"]] == [(label, value) for label, value, _ in ROADMAP_CHOICE_CHIPS]
    assert calls_of(tools, "get_roadmap") == [{"which": "active"}]
    assert not {tool for tool, _ in tools.calls} & WRITES and not writer.calls
    # lượt trả lời đọc lại đúng đặc tả "trước mốc": cùng hạn 05/02/2027 và cùng mốc đã dùng
    given = recognize_prompt(CHOICE_Q)
    assert given is not None and dict(given.given) == {
        "amount_vnd": 20_000_000, "date_text": "trước Tết",
        "date_spec": {"anchor": "date", "day": 6, "month": 2, "year": 2027, "before": True},
    }  # fmt: skip


def test_router_de_trong_chua_co_lo_trinh_thi_lap_hoi_hu_cua_muc_tieu(monkeypatch):
    events, tools, _ = _turn(monkeypatch, route_response(intent="roadmap", **GOAL), latest="error_not_found")
    (block,) = blocks_of(events)
    # câu hỏi hũ nói lại số tiền và hạn mã đã hiểu (hạn trước mốc: nói "trước {mốc}")
    assert block["type"] == "clarify" and block["data"]["question"] == goal_jar_question(20_000_000, TET_EVE, before=TET)
    assert "20.000.000 ₫ trước 06/02/2027" in block["data"]["question"] and "05/02/2027" not in block["data"]["question"]
    assert not {tool for tool, _ in tools.calls} & WRITES


@pytest.mark.parametrize(
    "routed",
    [
        # router không nói gì thêm (chip quyết lập): hạn đọc lại từ câu hỏi (chữ của người dùng kèm ngày đã tính), không hỏi hạn
        route_response(intent="roadmap"),
        route_response(intent="roadmap", roadmap_action="create", answers_pending=True),
        # router ghép lại cả hạn: lập theo hạn đó
        route_response(intent="roadmap", roadmap_action="create", answers_pending=True, **GOAL),
    ],
)
def test_bam_chip_lap_ban_moi_thi_lap_theo_muc_tieu_cua_cau_truoc(monkeypatch, routed):
    events, tools, _ = _turn(monkeypatch, routed, messages=_choice_messages(_chip("create")))
    # đi đường lập với mục tiêu của câu trước, không hỏi lại lập hay xem, không hỏi lại hạn; mục tiêu chưa có hũ nên hỏi hũ
    (block,) = blocks_of(events)
    assert block["type"] == "clarify" and block["data"]["question"] == goal_jar_question(20_000_000, TET_EVE, before=TET)
    assert GOAL_DATE_QUESTION not in block["data"]["question"]
    assert not calls_of(tools, "get_roadmap") and not {tool for tool, _ in tools.calls} & WRITES


@pytest.mark.parametrize(
    "routed",
    [route_response(intent="roadmap"), route_response(intent="roadmap", roadmap_action="view", answers_pending=True)],
)
def test_bam_chip_xem_ban_dang_dung_thi_chi_xem(monkeypatch, routed):
    events, tools, writer = _turn(monkeypatch, routed, messages=_choice_messages(_chip("view")))
    assert [b["type"] for b in blocks_of(events)] == ["roadmap"]
    assert calls_of(tools, "get_roadmap") == [{"which": "active"}]  # xem là xem bản đang dùng (#39)
    assert not {tool for tool, _ in tools.calls} & WRITES
    assert writer.calls[0]["compact"]["muc_tieu_nguoi_dung_hoi"] == {
        "so_tien_text": "20.000.000 ₫", "so_tien_short_text": "20 triệu", "han_nguoi_dung_noi": "trước Tết",
        # hạn đọc lại từ câu hỏi là đặc tả trước mốc đã dùng (mốc date): cùng hạn, cùng mốc; chữ của người dùng ở han_nguoi_dung_noi
        "han": {
            "date_text": "05/02/2027", "day_month_text": "05/02", "weekday_text": "thứ Sáu", "days_from_today": 76,
            "anchor": "date", "anchor_date_text": "06/02/2027", "before_anchor": True,
        },
    }  # fmt: skip


def test_router_noi_xem_o_cau_tra_loi_hu_cua_muc_tieu_thi_van_chi_xem(monkeypatch):
    """Đã hỏi hũ của mục tiêu (đường lập) mà router xếp câu trả lời là xem: tin router, không lưu bản mới."""
    messages = [
        {"id": "m1", "role": "user", "content": "lập lộ trình gom 3 triệu trong 3 tháng"},
        {"id": "m2", "role": "assistant", "content": ROADMAP_GOAL_JAR_QUESTION},
        {"id": "m3", "role": "user", "content": "Hũ Du lịch"},
    ]
    events, tools, _ = _turn(
        monkeypatch, route_response(intent="roadmap", roadmap_action="view", jar_text="Hũ Du lịch"), messages=messages
    )
    assert [b["type"] for b in blocks_of(events)] == ["roadmap"]
    assert not {tool for tool, _ in tools.calls} & WRITES
