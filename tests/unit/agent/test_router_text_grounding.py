"""Chữ router tự viết (lời đáp `reply`, câu hỏi lại `clarify.question`) được phát nguyên văn, nên số tiền và phần trăm trong đó phải có
căn cứ như mọi lời model viết (#39, câu e của lượt kiểm sau Runtime v33): căn cứ là câu mới, lời người dùng và dòng "Ứng dụng:" của
lịch sử. Dòng "Yofina:" không phải căn cứ: đó là lời model của lượt trước, có thể chưa qua bộ kiểm số (ở app, lời tra cứu có số
3.600.000 ₫ bị gắn "Hãy đối chiếu số liệu", rồi lần hỏi lại router tự viết lại đúng số đó trong lời xã giao). Không có căn cứ thì lời
đó không phát: xã giao lùi về writer có dữ kiện, câu hỏi lại lùi về câu của mã. Router giả, không gọi model.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_helpers import blocks_of, make_llm, route_response, run_turn
from yofina_agent import notices
from yofina_agent.router import checked_route
from yofina_agent.schemas import ClarifyChipIn, ClarifyRequest, IntentParams, IntentResult

#: câu của test, không trùng câu eval hay câu người dùng trên app
ASKED = "ke hoach dang dung co du gom 30 trieu truoc he khong"
#: lời của Yofina ở lượt trước: số 4.100.000 ₫ do model tự cộng, chưa có căn cứ
EARLIER = "Hũ Dự phòng đang có 2.700.000 ₫, cuối kỳ dự kiến 4.100.000 ₫ nên chưa đủ."


def _text(events: list[Any]) -> str:
    return "".join(e.delta for e in events if e.type.value == "TEXT_MESSAGE_CONTENT")


def _ir(intent: str, reply: str | None = None, clarify: ClarifyRequest | None = None, **params: Any) -> IntentResult:
    return IntentResult(
        intent=intent,  # type: ignore[arg-type]
        params=IntentParams(**params),
        confidence=0.9,
        needs_clarification=clarify is not None,
        clarify=clarify,
        reply=reply,
    )


def test_loi_xa_giao_chep_so_tu_dong_yofina_truoc_thi_khong_phat(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    msgs = [
        {"id": "m1", "role": "user", "content": ASKED},
        {"id": "m2", "role": "assistant", "content": EARLIER},
        {"id": "m3", "role": "user", "content": ASKED},
    ]
    llm = make_llm([route_response(intent="chitchat", reply="Bạn vừa hỏi rồi: cuối kỳ hũ Dự phòng dự kiến có 4.100.000 ₫.")])
    events, _, writer = run_turn(None, llm=llm, monkeypatch=monkeypatch, messages=msgs)
    assert "4.100.000" not in _text(events)
    assert [c["task"] for c in writer.calls] == ["chitchat"]  # lùi về writer có dữ kiện của việc xã giao
    assert '"event": "router_text_ungrounded"' in caplog.text and '"field": "reply"' in caplog.text


def test_loi_xa_giao_nhac_lai_so_nguoi_dung_tu_noi_van_phat(monkeypatch):
    msgs = [
        {"id": "m1", "role": "user", "content": "thang nay minh duoc thuong 2 trieu"},
        {"id": "m2", "role": "assistant", "content": "Tuyệt quá."},
        {"id": "m3", "role": "user", "content": "cam on nhe"},
    ]
    llm = make_llm([route_response(intent="chitchat", reply="Không có gì, chúc mừng khoản thưởng 2 triệu của bạn!")])
    events, _, writer = run_turn(None, llm=llm, monkeypatch=monkeypatch, messages=msgs)
    assert "2 triệu" in _text(events) and writer.calls == []


def test_cau_hoi_lai_cua_router_co_so_khong_can_cu_thi_dung_cau_cua_ma(monkeypatch):
    msgs = [
        {"id": "m1", "role": "user", "content": "du phong con bao nhieu"},
        {"id": "m2", "role": "assistant", "content": EARLIER},
        {"id": "m3", "role": "user", "content": "chuyen tu du phong sang an uong giup minh"},
    ]
    clarify = {"slot": "amount", "question": "Bạn muốn chuyển bao nhiêu trong 4.100.000 ₫ đó?", "chips": [{"label": "1 triệu"}]}
    llm = make_llm(
        [route_response(intent="move", from_jar_text="du phong", to_jar_text="an uong", clarify=clarify)]
    )
    events, tools, _ = run_turn(None, llm=llm, monkeypatch=monkeypatch, messages=msgs)
    asked = [b for b in blocks_of(events) if b["type"] == "clarify"]
    assert len(asked) == 1 and asked[0]["data"]["question"] == notices.CLARIFY["amount"]["question"]
    assert "4.100.000" not in str(asked)
    assert "move_between_jars" not in [name for name, _ in tools.calls]


def test_checked_route_chi_nhan_so_cua_cau_moi_loi_nguoi_dung_va_dong_ung_dung(caplog):
    caplog.set_level(logging.INFO)
    said = ["thang nay minh duoc thuong 2 trieu", "Hệ thống ghi nhận: đã chuyển 100.000 ₫ từ Giải trí sang Ăn uống."]
    ok = _ir("chitchat", reply="Đã chuyển 100.000 ₫, còn khoản thưởng 2 triệu thì tùy bạn.")
    assert checked_route(ok, "cam on", "", None, said=said).reply == ok.reply
    for bad in ("Hũ Ăn uống giờ có 480.000 ₫.", "Bạn đã dùng 35% hũ Giải trí."):
        assert checked_route(_ir("chitchat", reply=bad), "cam on", "", None, said=said).reply is None
    # không đưa căn cứ của lịch sử: chỉ câu mới là căn cứ (lượt gọi thẳng `route`, như eval)
    assert checked_route(ok, "cam on", "", None).reply is None
    asked = ClarifyRequest(slot="amount", question="Chuyển bao nhiêu trong 700.000 ₫ của hũ?", chips=[ClarifyChipIn(label="1 triệu")])
    out = checked_route(_ir("move", clarify=asked, from_jar_text="a", to_jar_text="b"), "chuyen tu a sang b", "", None, said=said)
    assert out.clarify is None and out.needs_clarification is False
    kept = ClarifyRequest(slot="amount", question="Bạn muốn chuyển bao nhiêu?", chips=[ClarifyChipIn(label="1 triệu")])
    assert checked_route(_ir("move", clarify=kept), "chuyen tu a sang b", "", None, said=said).clarify == kept
    assert caplog.text.count('"event": "router_text_ungrounded"') == 4
