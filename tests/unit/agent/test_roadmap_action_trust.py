"""Lộ trình tin `roadmap_action` của router (C2, #39): bỏ luật "câu lộ trình có số tiền hoặc hạn thì LUÔN lập bản mới".

Router "view" thì chỉ xem, không bao giờ lưu bản mới hay bỏ bản đang chờ, kể cả khi câu nêu số tiền hoặc hạn. Router để trống mà câu
nêu mục tiêu: đã có bản đang dùng thì hỏi đúng một câu với hai chip (lập bản mới, xem bản đang dùng); chưa có bản nào thì lập. Router
giả, không gọi model. Câu số 9 của báo cáo rà soát RR.
"""

from __future__ import annotations

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
from yofina_agent.clarify import ROADMAP_CHOICE_CHIPS, ROADMAP_CHOICE_QUESTION
from yofina_agent.notices import ROADMAP_GOAL_JAR_QUESTION

RR9 = "lo trinh hien tai co kip gom 20 trieu truoc Tet khong"  # câu số 9 của báo cáo RR
GOAL = {"amount_vnd": 20_000_000, "date_text": "trước Tết"}
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
        {"id": "m2", "role": "assistant", "content": ROADMAP_CHOICE_QUESTION},
        {"id": "m3", "role": "user", "content": chip_value},
    ]


def test_router_noi_xem_thi_chi_xem_du_cau_co_so_tien_va_han(monkeypatch):
    events, tools, writer = _turn(monkeypatch, route_response(intent="roadmap", roadmap_action="view", **GOAL))
    assert [tool for tool, _ in tools.calls] == ["get_jar_balances", "get_roadmap"]
    assert calls_of(tools, "get_roadmap") == [{"which": "latest"}]
    assert [b["type"] for b in blocks_of(events)] == ["roadmap"]
    # không lưu bản mới, nên cũng không bỏ bản đề xuất đang chờ (lưu bản mới là việc bỏ bản đang chờ)
    assert not {tool for tool, _ in tools.calls} & WRITES
    (call,) = writer.calls
    # mục tiêu người dùng nêu là dữ kiện cho writer (số đã định dạng để kiểm căn cứ), không thành bản mới
    assert call["task"] == "roadmap"
    assert call["compact"]["muc_tieu_nguoi_dung_hoi"] == {"so_tien_text": "20.000.000 ₫", "han_nguoi_dung_noi": "trước Tết"}


def test_router_de_trong_ma_da_co_ban_dang_dung_thi_hoi_mot_cau_hai_chip(monkeypatch):
    events, tools, writer = _turn(monkeypatch, route_response(intent="roadmap", **GOAL))
    (block,) = blocks_of(events)
    assert block["type"] == "clarify"
    data = block["data"]
    assert data["question"] == ROADMAP_CHOICE_QUESTION and data["question"].count("?") == 1
    assert [(c["label"], c["value"]) for c in data["chips"]] == [(label, value) for label, value, _ in ROADMAP_CHOICE_CHIPS]
    assert calls_of(tools, "get_roadmap") == [{"which": "active"}]
    assert not {tool for tool, _ in tools.calls} & WRITES and not writer.calls


def test_router_de_trong_chua_co_lo_trinh_thi_lap_hoi_hu_cua_muc_tieu(monkeypatch):
    events, tools, _ = _turn(monkeypatch, route_response(intent="roadmap", **GOAL), latest="error_not_found")
    (block,) = blocks_of(events)
    assert block["type"] == "clarify" and block["data"]["question"] == ROADMAP_GOAL_JAR_QUESTION
    assert not {tool for tool, _ in tools.calls} & WRITES


@pytest.mark.parametrize(
    "routed",
    [
        route_response(intent="roadmap"),  # router không nói gì thêm: chip quyết
        route_response(intent="roadmap", roadmap_action="create", answers_pending=True),
    ],
)
def test_bam_chip_lap_ban_moi_thi_lap_theo_muc_tieu_cua_cau_truoc(monkeypatch, routed):
    value = next(v for _, v, action in ROADMAP_CHOICE_CHIPS if action == "create")
    events, tools, _ = _turn(monkeypatch, routed, messages=_choice_messages(value))
    # đi đường lập với số tiền của câu trước; mục tiêu chưa có hũ nên hỏi hũ (không hỏi lại lập hay xem)
    (block,) = blocks_of(events)
    assert block["type"] == "clarify" and block["data"]["question"] == ROADMAP_GOAL_JAR_QUESTION
    assert not calls_of(tools, "get_roadmap")


@pytest.mark.parametrize(
    "routed",
    [route_response(intent="roadmap"), route_response(intent="roadmap", roadmap_action="view", answers_pending=True)],
)
def test_bam_chip_xem_ban_dang_dung_thi_chi_xem(monkeypatch, routed):
    value = next(v for _, v, action in ROADMAP_CHOICE_CHIPS if action == "view")
    events, tools, writer = _turn(monkeypatch, routed, messages=_choice_messages(value))
    assert [b["type"] for b in blocks_of(events)] == ["roadmap"]
    assert calls_of(tools, "get_roadmap") == [{"which": "latest"}]
    assert not {tool for tool, _ in tools.calls} & WRITES
    assert writer.calls[0]["compact"]["muc_tieu_nguoi_dung_hoi"]["so_tien_text"] == "20.000.000 ₫"


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
