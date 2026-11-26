"""Router xếp "ngoài phạm vi" nhưng câu có dấu hiệu chi tiêu: hỏi xác nhận (khối clarify) thay vì từ chối cứng.

Câu ngoài phạm vi thật (router không trích tham số chi tiêu) và câu Guardrail chặn vẫn bị từ chối như cũ.
"""

from __future__ import annotations

import pytest
from agent_helpers import (
    FakeGuardrailClient,
    blocks_of,
    check_agui_order,
    make_guardrail,
    make_llm,
    route_response,
    run_turn,
)
from yofina_agent import notices
from yofina_agent.fallback import classify_by_rules


def types_of(events):
    return [b["type"] for b in blocks_of(events)]


def test_ngoai_pham_vi_nhung_co_dau_hieu_chi_tieu_thi_hoi_xac_nhan(monkeypatch):
    llm = make_llm([route_response(intent="out_of_scope", amount_vnd=5_000_000, label="đi du lịch")])
    events, tools, _ = run_turn("10 ngày nữa đi du lịch 5 triệu", llm=llm, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert types_of(events) == ["clarify"]
    (c,) = blocks_of(events)
    q = c["data"]["question"]
    assert q.count("?") == 1 and "đi du lịch" in q and "5.000.000 ₫" in q
    assert [x["label"] for x in c["data"]["chips"]] == ["Thử nếu chi khoản này", "Kiểm tra có đủ tiền không", "Không cần"]
    assert [n for n, _ in tools.calls] == ["get_jar_balances"]  # chỉ lần đọc ví đầu lượt: chỉ hỏi lại


def test_chi_co_loai_mua_hang_khong_so_tien_van_hoi_cau_khong_ten(monkeypatch):
    llm = make_llm([route_response(intent="out_of_scope", scenario_kind="one_time_purchase", funding="credit")])
    events, _, _ = run_turn("cái đó thì sao", llm=llm, monkeypatch=monkeypatch)
    (c,) = blocks_of(events)
    assert c["type"] == "clarify" and c["data"]["question"].startswith("Mình chưa chắc ý bạn")


def test_ngoai_pham_vi_that_khong_co_tham_so_thi_van_tu_choi(monkeypatch):
    llm = make_llm([route_response(intent="out_of_scope")])
    events, _, _ = run_turn("thời tiết Đà Lạt tuần sau thế nào", llm=llm, monkeypatch=monkeypatch)
    assert types_of(events) == ["notice", "suggestions"]


def test_guardrail_chan_thi_tu_choi_du_router_trich_duoc_so_tien(monkeypatch):
    g = make_guardrail(FakeGuardrailClient(block_words=("cổ phiếu",)))
    llm = make_llm([route_response(intent="what_if", amount_vnd=10_000_000, label="cổ phiếu FPT")])
    events, tools, _ = run_turn("Có 10 triệu nên mua cổ phiếu FPT không", llm=llm, monkeypatch=monkeypatch, guardrail=g)
    assert types_of(events) == ["notice", "suggestions"]
    # chỉ lần đọc ví đầu lượt (trước router, song song Guardrail); không tool nào của ý định router chọn
    assert [n for n, _ in tools.calls] == ["get_jar_balances"]


def test_tu_choi_ngoai_pham_vi_co_chip_quay_ve_chong_chiu_va_lo_trinh(monkeypatch):
    # Cảnh 4 của kịch bản demo (figma-ui-design.md §8.2): sau lời từ chối "Nên mua cổ phiếu nào?" có chip về điểm chống chịu và lộ trình.
    llm = make_llm([route_response(intent="out_of_scope")])
    events, _, _ = run_turn("Nên mua cổ phiếu nào?", llm=llm, monkeypatch=monkeypatch)
    assert types_of(events) == ["notice", "suggestions"]
    items = blocks_of(events)[1]["data"]["items"]
    assert len(items) <= 6
    by_id = {x["id"]: x for x in items}
    assert by_id["resilience"]["label"] == "Điểm chống chịu của mình"
    assert by_id["roadmap"]["label"] == "Xem lộ trình"
    # chip cũ vẫn còn
    assert {"balances", "forecast", "what_if", "check"} <= set(by_id)


@pytest.mark.parametrize(
    ("chip_id", "intent", "roadmap_action"),
    [("resilience", "resilience", None), ("roadmap", "roadmap", "view")],
)
def test_cau_cua_chip_moi_vao_dung_intent_ca_khi_router_model_nghi(chip_id, intent, roadmap_action):
    # Câu chip gửi phải được bộ luật dự phòng (dùng khi model router hỏng) hiểu đúng intent, không thành ngoài phạm vi.
    (item,) = [x for x in notices.SUGGESTION_ITEMS if x["id"] == chip_id]
    r = classify_by_rules(item["prompt"])
    assert r is not None and r.intent == intent
    assert r.params.roadmap_action == roadmap_action
