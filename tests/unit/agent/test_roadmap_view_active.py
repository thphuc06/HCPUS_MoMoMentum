"""Lượt XEM lộ trình (router `roadmap_action="view"`) sau khi người dùng "Giữ bản cũ" một bản đề xuất (#39, lỗi 1 của báo cáo NN).

Ca thật (Runtime v32, 26/11): `minh` có v2 đang dùng, v3 vừa bị bỏ (`discarded`). Câu "lộ trình hiện tại có kịp gom 20 triệu đầu năm
sau không" hiện thẻ v3 "Đã bỏ" (lượt xem đọc `which: latest`) và không có câu trả lời: lời của writer bị bộ kiểm số bỏ
(`numeric_ungrounded`) vì người dùng nói "20 triệu" mà dữ kiện chỉ có dạng "20.000.000 ₫". Router giả, writer giả, không gọi model.
"""

from __future__ import annotations

import copy

from agent_helpers import (
    FakeTools,
    FakeWriter,
    blocks_of,
    check_agui_order,
    fixture,
    make_llm,
    mcp_ok,
    route_response,
    run_turn,
)
from test_roadmap_action_trust import GOAL, RR9, TET, TET_EVE
from test_roadmap_create_turn import DEMO_JARS, calls_of, jars_payload, texts_of
from yofina_agent import notices
from yofina_agent.clarify import ROADMAP_CHOICE_CHIPS, roadmap_choice_question
from yofina_agent.tools import classify_result

WRITES = {"save_roadmap", "optimize_allocation", "move_between_jars"}
ACTIVE = fixture("get_roadmap.ok.json")  # v2 đang dùng
STEPS = sum(len(p["steps"]) for p in ACTIVE["data"]["phases"])
ACTIVE_CLOSING = notices.ROADMAP_CLOSING_ACTIVE.format(version=2, phases=len(ACTIVE["data"]["phases"]), steps=STEPS)


def _discarded_v3() -> dict:
    payload = copy.deepcopy(ACTIVE)
    payload["data"].update(version=3, status="discarded", based_on_version=2)
    return payload


def _tools() -> FakeTools:
    """`get_roadmap`: bản đang dùng là v2, bản mới nhất là v3 đã bỏ (như sau khi bấm "Giữ bản cũ")."""

    def get_roadmap(args):
        payload = _discarded_v3() if args.get("which") == "latest" else ACTIVE
        return classify_result("get_roadmap", mcp_ok(payload))

    return FakeTools(
        {
            "get_jar_balances": lambda _a: classify_result("get_jar_balances", mcp_ok(jars_payload(DEMO_JARS))),
            "get_roadmap": get_roadmap,
        }
    )


def _view(monkeypatch, writer_text: str, *, goal: bool = True, question: str = RR9):
    routed = route_response(intent="roadmap", roadmap_action="view", **(GOAL if goal else {}))
    events, tools, writer = run_turn(
        question, llm=make_llm([routed]), tools=_tools(), monkeypatch=monkeypatch, writer=FakeWriter(writer_text)
    )
    check_agui_order(events)
    return events, tools, writer


def test_xem_lo_trinh_doc_ban_dang_dung_khong_doc_ban_moi_nhat_da_bo(monkeypatch):
    events, tools, _ = _view(monkeypatch, "Bản đang dùng chưa có bước nào cho mục tiêu này.")
    assert calls_of(tools, "get_roadmap") == [{"which": "active"}]
    (block,) = [b for b in blocks_of(events) if b["type"] == "roadmap"]
    assert block["data"]["version"] == 2 and block["data"]["status"] == "active"
    assert not {tool for tool, _ in tools.calls} & WRITES


def test_so_tien_nguoi_dung_noi_theo_cach_ngan_co_trong_du_kien_cho_writer(monkeypatch):
    # writer nói lại số tiền theo đúng cách người dùng nói ("20 triệu"): dạng đó phải có trong dữ kiện để bộ kiểm số không bỏ lời
    text = "Lộ trình phiên bản 2 chưa có mục tiêu gom 20 triệu trước Tết; mục tiêu hiện có là hũ Du lịch."
    events, _, writer = _view(monkeypatch, text)
    asked = writer.calls[0]["compact"]["muc_tieu_nguoi_dung_hoi"]
    assert asked["so_tien_text"] == "20.000.000 ₫" and asked["so_tien_short_text"] == "20 triệu"
    assert texts_of(events) == [text]


def test_dang_ngan_chi_co_khi_dung_so_tien_nguoi_dung_noi(monkeypatch):
    # 20.550.000 ₫ làm tròn ra "20,6 triệu" (khác số người dùng nói): không đưa dạng ngắn, chỉ dạng đầy đủ
    goal = {**GOAL, "amount_vnd": 20_550_000}
    routed = route_response(intent="roadmap", roadmap_action="view", **goal)
    _, _, writer = run_turn(RR9, llm=make_llm([routed]), tools=_tools(), monkeypatch=monkeypatch, writer=FakeWriter("Được."))
    asked = writer.calls[0]["compact"]["muc_tieu_nguoi_dung_hoi"]
    assert asked["so_tien_text"] == "20.550.000 ₫" and "so_tien_short_text" not in asked


def test_loi_bi_bo_kiem_so_bo_thi_van_co_cau_tra_loi_an_toan_va_hoi_lai(monkeypatch):
    # số lạ (35 triệu) không có trong dữ kiện: lời bị bỏ; người dùng vẫn nhận câu dựng bằng mã từ bản đang dùng và câu hỏi lập bản mới
    # theo mục tiêu họ hỏi (không nói kịp hay không: chưa có phép tính nào cho mục tiêu đó)
    events, tools, _ = _view(monkeypatch, "Bạn cần thêm 35 triệu nữa.")
    assert texts_of(events) == [ACTIVE_CLOSING]
    clarify = [b for b in blocks_of(events) if b["type"] == "clarify"]
    assert len(clarify) == 1
    assert clarify[0]["data"]["question"] == roadmap_choice_question(20_000_000, "trước Tết", TET_EVE, before=TET)
    assert [(c["label"], c["value"]) for c in clarify[0]["data"]["chips"]] == [
        (label, value) for label, value, _ in ROADMAP_CHOICE_CHIPS
    ]
    assert not {tool for tool, _ in tools.calls} & WRITES


def test_cau_xem_khong_neu_muc_tieu_loi_bi_bo_thi_noi_lai_ban_dang_dung(monkeypatch):
    events, _, _ = _view(monkeypatch, "Còn 99 ngày nữa.", goal=False, question="Cho mình xem lộ trình đang dùng")
    (text,) = texts_of(events)
    assert text.startswith(ACTIVE_CLOSING) and notices.ROADMAP_CLOSING_NEXT_REVIEW in text
    assert not [b for b in blocks_of(events) if b["type"] == "clarify"]


def test_loi_hop_le_thi_khong_them_cau_du_phong(monkeypatch):
    events, _, _ = _view(monkeypatch, "Đây là lộ trình phiên bản 2 bạn đang dùng.", goal=False, question="Xem lộ trình")
    assert texts_of(events) == ["Đây là lộ trình phiên bản 2 bạn đang dùng."]
