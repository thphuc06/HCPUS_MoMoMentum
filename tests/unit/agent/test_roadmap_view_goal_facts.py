"""Lượt XEM lộ trình có nêu mục tiêu: dữ kiện của writer nói bản đang xem có mục tiêu đó hay không (#39, câu e ở hội thoại mới sau
Runtime v33: router có đặc tả hạn và writer đã nhận hạn đã tính, nhưng lời nói mục tiêu "chưa có hạn cụ thể"). Lý do thật là bản đang
dùng không có mục tiêu người dùng vừa hỏi, nên chưa có phép tính kịp hay không cho nó; dữ kiện cũ không nói điều này nên model tự đặt
lý do. Mã so mục tiêu hỏi (số tiền, hạn đã tính) với mục tiêu của bản (`goals`), không đọc chữ. Router và writer giả.
"""

from __future__ import annotations

from agent_helpers import route_response
from test_roadmap_action_trust import GOAL, _turn
from yofina_agent.writer import TASKS


def _asked(writer) -> dict:
    (call,) = writer.calls
    return call["compact"]["muc_tieu_nguoi_dung_hoi"]


def test_muc_tieu_hoi_khong_co_trong_ban_dang_dung(monkeypatch):
    _, _, writer = _turn(monkeypatch, route_response(intent="roadmap", roadmap_action="view", **GOAL))
    assert _asked(writer)["co_trong_ban_nay"] is False  # bản đang dùng chỉ có mục tiêu Du lịch 6.000.000 ₫ hạn 31/03/2027


def test_muc_tieu_hoi_trung_muc_tieu_cua_ban_dang_dung(monkeypatch):
    goal = {"amount_vnd": 6_000_000, "date_text": "cuối tháng 3 năm sau", "date_spec": {"anchor": "date", "day": 31, "month": 3, "year": 2027}}
    question = "ban dang dung co kip gom 6 trieu truoc cuoi thang 3 nam sau khong"
    _, _, writer = _turn(monkeypatch, route_response(intent="roadmap", roadmap_action="view", **goal), question=question)
    assert _asked(writer)["co_trong_ban_nay"] is True


def test_cung_so_tien_khac_han_la_muc_tieu_khac(monkeypatch):
    goal = {"amount_vnd": 6_000_000, "date_text": "trước Tết", "date_spec": {"anchor": "lunar_new_year", "before": True}}
    question = "ban dang dung co kip gom 6 trieu truoc Tet khong"
    _, _, writer = _turn(monkeypatch, route_response(intent="roadmap", roadmap_action="view", **goal), question=question)
    assert _asked(writer)["co_trong_ban_nay"] is False


def test_nghia_cua_truong_nam_trong_nhiem_vu_cua_writer():
    assert "co_trong_ban_nay" in TASKS["roadmap"]
