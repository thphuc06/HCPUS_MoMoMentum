"""Ý định `behavior` (phase 5 luồng B): câu hỏi về thói quen chi tiêu -> `forecast___get_behavior_profile` -> khối `behavior_insight`."""

from __future__ import annotations

import copy
import json

import pytest
from agent_helpers import (
    REPO,
    FakeTools,
    blocks_of,
    check_agui_order,
    fixture,
    make_llm,
    mcp_ok,
    route_response,
    run_turn,
    types,
)
from yofina_agent import behavior_chat
from yofina_agent.router import ROUTER_SYSTEM
from yofina_agent.tools import classify_result

from yofina_core import blocks as B
from yofina_core.errors import ErrorCode

PROFILE = fixture("get_behavior_profile.ok.json")


def gateway(payload):
    return FakeTools({"get_behavior_profile": classify_result("get_behavior_profile", mcp_ok(payload))})


def texts_of(events):
    return ["".join(e.delta for e in events if e.type.value == "TEXT_MESSAGE_CONTENT")]


def test_hoi_chung_ra_khoi_nhan_xet_quan_trong_nhat(monkeypatch):
    events, tools, writer = run_turn(
        "Thói quen chi tiêu của mình thế nào?",
        llm=make_llm([route_response(intent="behavior")]),
        tools=gateway(PROFILE),
        monkeypatch=monkeypatch,
    )
    check_agui_order(events)
    assert tools.calls == [("get_behavior_profile", {})]
    assert [e.tool_call_name for e in events if e.type.value == "TOOL_CALL_START"] == ["forecast___get_behavior_profile"]
    (block,) = blocks_of(events)
    expected = json.loads(
        (REPO / "contracts/fixtures/blocks/valid/behavior_insight.chi_don_sau_luong.json").read_text(encoding="utf-8")
    )
    assert block == expected  # cùng khối với màn Hồ sơ dựng từ hồ sơ này
    assert types(events).index("ACTIVITY_SNAPSHOT") < types(events).index("TOOL_CALL_RESULT")
    # câu trả lời do mã dựng từ chính hồ sơ, không qua Writer
    assert not writer.calls
    (text,) = texts_of(events)
    insight, step = PROFILE["data"]["insights"][0], PROFILE["data"]["next_step"]
    assert text.startswith(insight["headline"]) and step["label"] in text


@pytest.mark.parametrize(
    ("question", "insight_id"),
    [
        ("Mình dùng Trả sau nhiều không?", "tra_sau_5_lan"),
        ("Cuối tuần mình tiêu nhiều không?", "thu_bay_an_uong"),
        ("Mình có chi dồn sau ngày lương không?", "chi_don_sau_luong"),
    ],
)
def test_hoi_dung_chu_de_thi_lay_dung_nhan_xet(monkeypatch, question, insight_id):
    events, _, _ = run_turn(
        question, llm=make_llm([route_response(intent="behavior")]), tools=gateway(PROFILE), monkeypatch=monkeypatch
    )
    (block,) = blocks_of(events)
    B.BehaviorInsightBlock.model_validate(block)
    assert block["data"]["insight"]["insight_id"] == insight_id
    assert block["id"].endswith(f":{insight_id}")


def test_hoi_chu_de_ho_so_khong_co_thi_noi_ro_va_lay_nhan_xet_noi_bat(monkeypatch):
    events, _, _ = run_turn(
        "Mình hay tiêu vào buổi tối không?",
        llm=make_llm([route_response(intent="behavior")]),
        tools=gateway(PROFILE),
        monkeypatch=monkeypatch,
    )
    (block,) = blocks_of(events)
    assert block["data"]["insight"]["insight_id"] == PROFILE["data"]["insights"][0]["insight_id"]
    (text,) = texts_of(events)
    assert text.startswith("Mình chưa thấy thói quen nào rõ về giờ chi tiêu trong ngày")


def test_ho_so_chua_san_sang_la_notice_khong_bia_nhan_xet(monkeypatch):
    payload = fixture("get_behavior_profile.ok_chua_san_sang.json")
    events, _, writer = run_turn(
        "Thói quen chi tiêu của mình?",
        llm=make_llm([route_response(intent="behavior")]),
        tools=gateway(payload),
        monkeypatch=monkeypatch,
    )
    check_agui_order(events)
    (notice,) = blocks_of(events)
    assert notice["type"] == "notice" and notice["data"]["kind"] == "low_data"
    assert notice["data"]["message"] == payload["data"]["headline"]
    assert "TEXT_MESSAGE_START" not in types(events) and not writer.calls


@pytest.mark.parametrize(("code", "kind"), [(ErrorCode.PROFILE_INCOMPLETE.value, "info"), (ErrorCode.INTERNAL_ERROR.value, "error")])
def test_tool_loi(monkeypatch, code, kind):
    payload = {"status": "ERROR", "code": code, "message": "Chưa khai lương và ngày nhận lương."}
    events, _, _ = run_turn(
        "Thói quen chi tiêu của mình?",
        llm=make_llm([route_response(intent="behavior")]),
        tools=gateway(payload),
        monkeypatch=monkeypatch,
    )
    notices = [b for b in blocks_of(events) if b["type"] == "notice"]
    assert notices and notices[0]["data"]["kind"] == kind and notices[0]["data"]["code"] == code


def test_ho_so_sai_hop_dong_thi_bao_loi_khong_phat_khoi(monkeypatch):
    payload = copy.deepcopy(PROFILE)
    payload["data"]["insights"][0]["evidence"] = []
    events, _, _ = run_turn(
        "Thói quen chi tiêu của mình?",
        llm=make_llm([route_response(intent="behavior")]),
        tools=gateway(payload),
        monkeypatch=monkeypatch,
    )
    (notice,) = blocks_of(events)
    assert notice["type"] == "notice" and notice["data"]["code"] == ErrorCode.INTERNAL_ERROR.value


def test_router_co_luat_cho_y_dinh_behavior():
    assert "- behavior:" in ROUTER_SYSTEM and "Các ý định (intent)" in ROUTER_SYSTEM
    assert behavior_chat.asked_kind("Mình có hay xài trả sau không") == "bnpl_usage"
    assert behavior_chat.asked_kind("số lượng giao dịch của mình") is None  # "lượng" không phải "lương"
