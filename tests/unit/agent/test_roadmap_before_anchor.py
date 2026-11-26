"""Hạn "trước {mốc}" của mục tiêu lộ trình (#39, việc nối 5 của đợt gộp; LL điểm 3).

Đặc tả hạn có `before` cho ra ngày LIỀN TRƯỚC mốc ("trước Tết" là 05/02/2027 vì Tết Đinh Mùi là 06/02/2027). Câu dựng bằng mã nói hạn theo
mốc đã dùng của `resolve_date` ("trước 06/02/2027"), không nói "trước 05/02/2027" (đọc ra sớm thêm một ngày): lời kết của lượt lập, câu
hỏi hũ, và lượt trả lời câu hỏi hũ đọc lại đúng đặc tả "trước mốc" từ câu hỏi nên lời kết vẫn đúng. Hạn gửi cho bộ tối ưu vẫn là ngày
tính được (05/02/2027). Planner thấy mốc ở `user_goal.target_before_text`. Router giả, model giả.
"""

from __future__ import annotations

import json

from agent_helpers import (
    blocks_of,
    check_agui_order,
    make_llm,
    route_response,
    run_turn,
    tool_response,
)
from test_roadmap_create_turn import (
    DEMO_JARS,
    answer_turn,
    ask_turn,
    calls_of,
    outline,
    roadmap_tools,
)
from yofina_agent.clarify import recognize_prompt

AMOUNT = 3_000_000  # số tiền của câu QUESTION mà ask_turn gửi: router giả trả đúng số người dùng nói
TET_SPEC = {"anchor": "lunar_new_year", "before": True}
TET_EVE = "2027-02-05"  # ngày liền trước Tết Đinh Mùi (06/02/2027), ngày mô phỏng của fixture 21/11/2026


def _texts(events):
    return [e.delta for e in events if e.type.value == "TEXT_MESSAGE_CONTENT"]


def _draft_context(llm):
    """Ngữ cảnh của lời gọi phác thảo lộ trình (lời gọi thứ hai, sau router)."""
    return json.loads(llm[1].calls[1]["messages"][0]["content"][0]["text"])


def test_router_neu_du_hu_thi_loi_ket_noi_truoc_moc(monkeypatch):
    llm = make_llm(
        [
            route_response(intent="roadmap", roadmap_action="create", amount_vnd=AMOUNT, date_text="trước Tết",
                           date_spec=TET_SPEC, jar_text="Du lịch"),
            tool_response("draft_roadmap", outline("muc_tieu")),
        ]
    )  # fmt: skip
    events, tools, _ = run_turn("để dành 3 triệu đi chơi trước Tết", llm=llm, tools=roadmap_tools(DEMO_JARS), monkeypatch=monkeypatch)
    check_agui_order(events)
    # hạn gửi cho bộ tối ưu là ngày tính được
    assert calls_of(tools, "optimize_allocation") == [
        {"goals": [{"jar": "muc_tieu", "target_vnd": AMOUNT, "target_date": TET_EVE}]}
    ]
    (text,) = _texts(events)
    assert "3.000.000 ₫ cho hũ Du lịch trước 06/02/2027" in text and "05/02/2027" not in text
    # planner thấy mốc người dùng nói "trước" để nói hạn đúng
    context = _draft_context(llm)
    assert context["user_goal"]["target_before_text"] == "06/02/2027"
    assert context["context"]["user_goal"]["target_before_text"] == "06/02/2027"


def test_hoi_hu_roi_tra_loi_van_noi_truoc_moc(monkeypatch):
    events, _, _, _ = ask_turn(monkeypatch, DEMO_JARS, amount_vnd=AMOUNT, date_text="trước Tết", date_spec=TET_SPEC)
    (clarify,) = blocks_of(events)
    question = clarify["data"]["question"]
    assert "3.000.000 ₫ trước 06/02/2027" in question and "05/02/2027" not in question
    # câu hỏi đọc lại thành đúng đặc tả "trước mốc"
    given = recognize_prompt(question)
    assert given is not None and given.given["date_spec"] == {"anchor": "date", "day": 6, "month": 2, "year": 2027, "before": True}
    events, tools, _, _ = answer_turn(
        monkeypatch, DEMO_JARS, clarify, "Du lịch", route_response(intent="roadmap", jar_text="Hũ Du lịch"), draft_jar="muc_tieu"
    )
    check_agui_order(events)
    assert calls_of(tools, "optimize_allocation") == [
        {"goals": [{"jar": "muc_tieu", "target_vnd": AMOUNT, "target_date": TET_EVE}]}
    ]
    (text,) = _texts(events)
    assert "3.000.000 ₫ cho hũ Du lịch trước 06/02/2027" in text and "05/02/2027" not in text


def test_han_khong_co_before_giu_nguyen_cach_noi(monkeypatch):
    """Hạn là chính ngày tính được (không `before`): câu hỏi hũ nói "hạn {ngày}" và đọc lại đúng ngày đó; lời kết như cũ."""
    spec = {"anchor": "today", "offset": {"months": 3}}
    events, _, _, _ = ask_turn(monkeypatch, DEMO_JARS, amount_vnd=AMOUNT, date_text="trong 3 tháng", date_spec=spec)
    (clarify,) = blocks_of(events)
    question = clarify["data"]["question"]
    assert "3.000.000 ₫ hạn 21/02/2027" in question
    given = recognize_prompt(question)
    assert given is not None and given.given["date_spec"] == {"anchor": "date", "day": 21, "month": 2, "year": 2027}
    events, _, _, _ = answer_turn(
        monkeypatch, DEMO_JARS, clarify, "Du lịch", route_response(intent="roadmap", jar_text="Hũ Du lịch"), draft_jar="muc_tieu"
    )
    (text,) = _texts(events)
    assert "3.000.000 ₫ cho hũ Du lịch trước 21/02/2027" in text
