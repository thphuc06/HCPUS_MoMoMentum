"""Lưu và đọc lại lượt hội thoại (tool save_turn, REST /conversations), kho giả tách theo người dùng."""

from __future__ import annotations

import json

import pytest
from conftest import BASE, OPENAPI_URI
from jsonschema import Draft202012Validator
from ledger_fakes import gateway_context, http_event, make_service

from yofina_core.blocks import build_notice
from yofina_ledger.gateway_api import handle_gateway
from yofina_ledger.rest_api import handle_http

MINH, LAN = "sub-minh", "sub-lan"
CONV = "c" * 40
TRACE = "8f3a21c94b7e4d0aa1c25e6f7b8c9d01"


def notice_block(trace=TRACE):
    from datetime import UTC, date, datetime

    b = build_notice(
        kind="degraded",
        title="Chậm",
        message="Thử lại sau.",
        trace_id=trace,
        source_tool="agent",
        as_of=datetime(2026, 12, 10, 3, 0, tzinfo=UTC),
        app_date=date(2026, 11, 21),
        code="RATE_LIMITED",
    )
    from yofina_core.blocks import block_to_wire

    return block_to_wire(b)


def save(svc, uid=MINH, **kw):
    args = {
        "user_id": uid,
        "conversation_id": CONV,
        "trace_id": TRACE,
        "user_text": "số dư các hũ",
        "assistant_text": "Bạn có 7 hũ.",
        "blocks": [{"seq": 0, "block": notice_block()}],
        **kw,
    }
    return handle_gateway(args, gateway_context("ledger___save_turn"), svc)


def rest(svc, path, sub=MINH, **kw):
    res = handle_http(http_event("GET", path, sub=sub, **kw), svc)
    return res["statusCode"], json.loads(res["body"])


def validate(registry, name, instance):
    v = Draft202012Validator(
        {"$ref": f"{OPENAPI_URI}#/components/schemas/{name}"}, registry=registry
    )
    errs = [f"{list(e.path)}: {e.message}" for e in v.iter_errors(instance)]
    assert not errs, errs


def test_save_turn_ket_qua_dung_hop_dong(registry):
    svc, _, _ = make_service()
    res = save(svc)
    v = Draft202012Validator(
        {"$ref": f"{BASE}/tools/ledger.results.schema.json#/$defs/SaveTurnResult"},
        registry=registry,
    )
    assert v.is_valid(res), res
    assert res["status"] == "OK" and res["data"]["blocks_saved"] == 1


def test_luu_roi_doc_lai_dung_thu_tu_va_noi_dung(registry):
    svc, _, clock = make_service()
    save(svc)
    clock.advance(30)
    t2 = "1" * 32
    save(
        svc,
        trace_id=t2,
        user_text="chuyển 100 nghìn",
        assistant_text="",
        blocks=[{"seq": 1, "block": notice_block(t2)}, {"seq": 0, "block": notice_block(t2)}],
    )
    status, body = rest(svc, f"/conversations/{CONV}", path_params={"conversation_id": CONV})
    assert status == 200
    validate(registry, "ConversationResponse", body)
    assert [t["trace_id"] for t in body["turns"]] == [TRACE, t2]
    assert body["turns"][0]["user_text"] == "số dư các hũ"
    assert body["turns"][0]["assistant_text"] == "Bạn có 7 hũ."
    assert len(body["turns"][1]["blocks"]) == 2 and body["turns"][1]["assistant_text"] == ""


def test_luu_lai_cung_luot_ghi_de_khong_nhan_doi():
    svc, repo, _ = make_service()
    save(svc)
    save(svc, assistant_text="Bản mới.", blocks=[])
    turns, blocks = repo.conversation(MINH, CONV)
    assert len(turns) == 1 and turns[0]["assistant_text"] == "Bản mới." and blocks == []


def test_lan_khong_doc_duoc_hoi_thoai_cua_minh(registry):
    svc, _, _ = make_service()
    save(svc, MINH)
    status, body = rest(
        svc, f"/conversations/{CONV}", sub=LAN, path_params={"conversation_id": CONV}
    )
    assert status == 200 and body == {"conversation_id": CONV, "turns": []}
    status, body = rest(svc, "/conversations", sub=LAN)
    assert body == {"conversations": []}


def test_danh_sach_hoi_thoai_gan_day(registry):
    svc, _, clock = make_service()
    save(svc)
    clock.advance(60)
    save(svc, conversation_id="d" * 40, trace_id="2" * 32, user_text="hũ nào sắp cạn?")
    status, body = rest(svc, "/conversations")
    assert status == 200
    validate(registry, "ConversationListResponse", body)
    assert [c["conversation_id"] for c in body["conversations"]] == ["d" * 40, CONV]
    assert body["conversations"][1]["preview"] == "số dư các hũ"
    status, body = rest(svc, "/conversations", query={"limit": "1"})
    assert len(body["conversations"]) == 1
    status, body = rest(svc, "/conversations", query={"limit": "0"})
    assert status == 400 and body["error"]["code"] == "PARAMS_INVALID"


@pytest.mark.parametrize(
    "kw",
    [
        {"conversation_id": ""},
        {"conversation_id": "x" * 257},
        {"trace_id": " "},
        {"blocks": "không phải mảng"},
        {"blocks": [{"seq": 0}]},
        {"blocks": [{"seq": -1, "block": {"id": "a", "type": "notice"}}]},
        {"blocks": [{"seq": True, "block": {"id": "a", "type": "notice"}}]},
        {"blocks": [{"seq": 0, "block": {"type": "notice"}}]},
        {
            "blocks": [
                {"seq": 0, "block": {"id": "a", "type": "notice"}},
                {"seq": 0, "block": {"id": "b", "type": "notice"}},
            ]
        },
        {"blocks": [{"seq": i, "block": {"id": str(i), "type": "notice"}} for i in range(21)]},
    ],
)
def test_save_turn_tu_choi_tham_so_sai(kw):
    svc, repo, _ = make_service()
    res = save(svc, **kw)
    assert res["status"] == "ERROR" and res["code"] == "PARAMS_INVALID"
    assert repo.turns.get(MINH, {}) == {}


def test_khong_luu_token():
    svc, repo, _ = make_service()
    jwt = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4eHh4eCJ9.c2lnbmF0dXJl"
    ctok = "A" * 30 + "." + "B" * 30
    res = save(svc, user_text=f"token của tôi {jwt} và {ctok}", assistant_text=f"đây {jwt}")
    assert res["status"] == "OK"
    turn = repo.turns[MINH][(CONV, TRACE)]
    assert jwt not in turn["user_text"] and ctok not in turn["user_text"]
    assert "[đã ẩn token]" in turn["user_text"] and jwt not in turn["assistant_text"]
    bad = save(
        svc,
        trace_id="3" * 32,
        blocks=[
            {"seq": 0, "block": {"id": "a", "type": "notice", "data": {"confirm_token": "x.y"}}}
        ],
    )
    assert bad["status"] == "ERROR" and bad["code"] == "PARAMS_INVALID"
    bad = save(
        svc,
        trace_id="4" * 32,
        blocks=[{"seq": 0, "block": {"id": "a", "type": "notice", "fallback_text": jwt}}],
    )
    assert bad["status"] == "ERROR"


def test_cat_van_ban_dai():
    svc, repo, _ = make_service()
    save(svc, user_text="a" * 5000, assistant_text="b" * 9000)
    turn = repo.turns[MINH][(CONV, TRACE)]
    assert len(turn["user_text"]) == 4000 and len(turn["assistant_text"]) == 8000


def test_user_id_chi_tu_su_kien_khong_tu_than_tham_so():
    svc, repo, _ = make_service()
    # tham số lạ (kể cả user_id lồng) bị bỏ qua; người sở hữu là user_id của sự kiện
    save(svc, MINH, extra="bo qua")
    assert (CONV, TRACE) in repo.turns[MINH] and LAN not in repo.turns


def test_reset_demo_xoa_luot_da_luu():
    svc, repo, _ = make_service()
    save(svc)
    repo.reset_user(
        MINH,
        profile={"clock_offset_days": 0},
        jars=[],
        transactions=[],
        trace_id=TRACE,
        details={},
    )
    assert repo.turns[MINH] == {}
