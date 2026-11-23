"""Router trích mục tiêu người dùng nói khi lập lộ trình (amount_vnd, jar_text, date_text) qua schema `IntentResult`."""

from __future__ import annotations

import pytest
from agent_helpers import make_llm, route_response, run
from yofina_agent.router import ROUTER_SYSTEM, route
from yofina_agent.schemas import IntentResult


def test_prompt_router_day_trich_muc_tieu_lo_trinh_va_khong_tu_doi_ngay():
    assert "roadmap có mục tiêu người dùng nói" in ROUTER_SYSTEM
    rule = ROUTER_SYSTEM.split("roadmap có mục tiêu người dùng nói", 1)[1].split("\n- ", 1)[0]
    for key in ("amount_vnd", "jar_text", "date_text", '"create"'):
        assert key in rule
    assert "không tự đổi thành ngày" in rule
    # roadmap vẫn không bao giờ hỏi lại
    assert "stress và roadmap không bao giờ hỏi lại" in ROUTER_SYSTEM


def test_route_tra_tham_so_muc_tieu_lo_trinh():
    llm, _, _ = make_llm(
        [
            route_response(
                intent="roadmap",
                roadmap_action="create",
                amount_vnd=1_000_000_000,
                jar_text="hũ Du lịch",
                date_text="cuối tháng này",
            )
        ]
    )
    res = run(route(llm, "Lập lộ trình gom đủ 1 tỷ trong hũ Du lịch trước cuối tháng này", "", max_attempts=1, max_tokens=400))
    p = res.value.params
    assert res.value.intent == "roadmap" and not res.value.needs_clarification
    assert (p.amount_vnd, p.jar_text, p.date_text, p.roadmap_action) == (
        1_000_000_000,
        "hũ Du lịch",
        "cuối tháng này",
        "create",
    )


@pytest.mark.parametrize("field", ["to_jar_text", "from_jar_text"])
def test_schema_lo_trinh_doi_hu_dich_sang_jar_text(field):
    r = IntentResult.model_validate(
        {
            "intent": "roadmap",
            "params": {"amount_vnd": 1_000_000_000, field: "hũ Du lịch", "date_text": "cuối tháng này"},
            "confidence": 0.9,
            "needs_clarification": False,
        }
    )
    assert r.params.jar_text == "hũ Du lịch"
    assert r.params.to_jar_text is None and r.params.from_jar_text is None
    assert (r.params.amount_vnd, r.params.date_text) == (1_000_000_000, "cuối tháng này")


def test_schema_lo_trinh_giu_jar_text_da_co():
    r = IntentResult.model_validate(
        {
            "intent": "roadmap",
            "params": {"jar_text": "Du lịch", "to_jar_text": "Dự phòng"},
            "confidence": 0.9,
            "needs_clarification": False,
        }
    )
    assert (r.params.jar_text, r.params.to_jar_text) == ("Du lịch", None)
