"""Dữ kiện của writer ở lượt tra dự báo một hũ (#39, câu e sau Runtime v33): lời tra cứu có hai số bị bộ kiểm bắt (`numeric_ungrounded`
[3600000, 20000000]) vì cả hai không có trong dữ kiện: số người dùng tự nói trong câu ("20 triệu") và số dư cuối kỳ dự báo (model tự
cộng số dư hôm nay với khoản lương về). Sửa ở dữ kiện, không nới bộ kiểm: bản gọn của dự báo có số dư giữa ngày cuối kỳ dự báo (số của
engine), và lượt tra cứu có các số tiền người dùng nói (mã đọc lại từ câu, đúng dạng họ gõ và dạng đầy đủ). Router và writer giả.
"""

from __future__ import annotations

from typing import Any

from agent_helpers import FakeWriter, blocks_of, fixture, make_llm, route_response, run_turn
from yofina_agent.compact import compact_forecast
from yofina_agent.writer import build_writer_prompt, check_grounding

#: câu của test, không trùng câu eval hay câu người dùng trên app
ASKED = "hu an uong toi cuoi ky co con du 3 trieu khong"


def _result(events: list[Any]) -> dict[str, Any]:
    return events[-1].result


def test_ban_gon_du_bao_co_so_du_giua_ngay_cuoi_ky():
    c = compact_forecast(fixture("get_forecast.ok.json"))
    assert c["end_of_forecast"] == {"date_text": "21/12", "balance_vnd": 1_460_000, "balance_text": "1.460.000 ₫"}


def test_tra_du_bao_co_so_nguoi_dung_noi_va_so_cuoi_ky_thi_loi_co_can_cu(monkeypatch):
    llm = make_llm([route_response(intent="lookup", lookup_kind="forecast", jar_text="ăn uống")])
    said = "Cuối kỳ dự báo (21/12) hũ Ăn uống dự kiến còn 1.460.000 ₫, chưa tới 3 triệu bạn hỏi."
    events, _, writer = run_turn(ASKED, llm=llm, monkeypatch=monkeypatch, writer=FakeWriter(said))
    compact = writer.calls[0]["compact"]
    assert compact["so_tien_nguoi_dung_noi"] == [{"amount_text": "3.000.000 ₫", "short_text": "3 triệu"}]
    assert check_grounding(said, compact) == []
    assert _result(events)["degraded"] is False
    assert not [b for b in blocks_of(events) if (b.get("data") or {}).get("code") == "NUMERIC_UNVERIFIED"]
    # nghĩa của trường nói cho writer biết đây là số người dùng nói, không phải số liệu của ví
    prompt = build_writer_prompt("forecast", ASKED, compact)
    assert "so_tien_nguoi_dung_noi" in prompt.split("</du_lieu>", 1)[1]


def test_cau_khong_co_so_tien_thi_khong_them_truong(monkeypatch):
    llm = make_llm([route_response(intent="lookup", lookup_kind="forecast", jar_text="ăn uống")])
    _, _, writer = run_turn("hu an uong con tru duoc bao lau", llm=llm, monkeypatch=monkeypatch)
    assert "so_tien_nguoi_dung_noi" not in writer.calls[0]["compact"]
