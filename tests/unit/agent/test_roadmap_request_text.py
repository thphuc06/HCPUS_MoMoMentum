"""Phần nối C4 (#39): câu của người dùng (đã che PII) tới bước lập lộ trình, để planner tôn trọng ràng buộc họ nêu.

Nhánh khác thêm tham số tùy chọn nhận câu cho `roadmap_agent.build_roadmap`; ở đây `turn.py` chỉ truyền theo tên khi chữ ký hàm có tham số
đó (`turn._ROADMAP_REQUEST_PARAMS`), nên hai nhánh gộp theo thứ tự nào cũng chạy. Lượt trả lời câu hỏi lại thì kèm câu yêu cầu gốc.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from agent_helpers import make_llm, route_response, run_turn
from test_roadmap_create_turn import DEMO_JARS, roadmap_tools
from yofina_agent.clarify import goal_jar_question

ASK = "lập lộ trình giúp mình, đừng đụng hũ Giải trí nhé, có gì gọi 0912345678"


def _fake_build(captured: list[dict[str, Any]], *, accepts: str | None):
    """`build_roadmap` giả: ghi lại các tham số theo tên, không lập gì (lượt báo chưa lập được)."""

    async def fake(tools, llm, settings, scope, **kw: Any) -> Any:
        captured.append(kw)
        return SimpleNamespace(suitability=[], model_error=None, model_budget_exhausted=False, outcome=None, advice=None)

    if accepts is None:
        return fake

    async def with_request(tools, llm, settings, scope, *, user_request: str | None = None, **kw: Any) -> Any:
        return await fake(tools, llm, settings, scope, user_request=user_request, **kw)

    return with_request


@pytest.mark.parametrize("accepts", ["user_request", None], ids=["ham-nhan-cau", "ham-chua-nhan"])
def test_cau_nguoi_dung_da_che_pii_toi_buoc_lap_lo_trinh_khi_ham_nhan(monkeypatch, accepts):
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr("yofina_agent.turn.build_roadmap", _fake_build(captured, accepts=accepts))
    llm = make_llm([route_response(intent="roadmap", roadmap_action="create")])
    events, _, _ = run_turn(ASK, llm=llm, tools=roadmap_tools(DEMO_JARS), monkeypatch=monkeypatch)
    assert events[-1].type.value == "RUN_FINISHED"
    (kw,) = captured
    if accepts is None:
        assert "user_request" not in kw  # hàm chưa có tham số: gọi như cũ, không lỗi
    else:
        assert "đừng đụng hũ Giải trí" in kw["user_request"] and "0912345678" not in kw["user_request"]


def test_luot_tra_loi_cau_hoi_hu_kem_cau_yeu_cau_goc(monkeypatch):
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr("yofina_agent.turn.build_roadmap", _fake_build(captured, accepts="user_request"))
    ask = "lập lộ trình gom 3 triệu trong 3 tháng, đừng cắt hũ Giải trí"
    messages = [
        {"id": "m1", "role": "user", "content": ask},
        {"id": "m2", "role": "assistant", "content": goal_jar_question(3_000_000, None)},
        {"id": "m3", "role": "user", "content": "Hũ Du lịch"},
    ]
    llm = make_llm([route_response(intent="roadmap", jar_text="Hũ Du lịch", answers_pending=True, date_spec={"anchor": "today", "offset": {"months": 3}})])
    run_turn(None, llm=llm, tools=roadmap_tools(DEMO_JARS), monkeypatch=monkeypatch, messages=messages)
    (kw,) = captured
    assert kw["user_request"] == f"{ask}\nHũ Du lịch"
