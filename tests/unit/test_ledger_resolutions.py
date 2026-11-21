"""Đề nghị (khối `confirm`) chỉ được thực hiện một lần và server giữ trạng thái: `POST /confirmations` và
`POST /actions` nhận `conversation_id` + `confirm_block_id`; `GET /conversations/{id}` trả `resolutions`
(pending | done kèm receipt | expired). Dùng kho dữ liệu giả tách theo người dùng (migration 0004)."""

from __future__ import annotations

import json

import pytest
from conftest import OPENAPI_URI
from jsonschema import Draft202012Validator
from ledger_fakes import http_event, make_service

from yofina_core.blocks import block_to_wire
from yofina_ledger.rest_api import handle_http

MINH, LAN = "sub-minh", "sub-lan"
MOVE = {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100_000}
TOOL = "move_between_jars"
CONV = "c" * 40
TRACE = "8f3a21c94b7e4d0aa1c25e6f7b8c9d01"


def req(svc, method, path, **kw):
    res = handle_http(http_event(method, path, **kw), svc)
    return res["statusCode"], json.loads(res["body"])


def offer(svc, uid=MINH, params=MOVE, trace=TRACE, conv=CONV):
    """Agent phát khối confirm rồi lưu lượt (save_turn); trả (khối dạng JSON, tham số gửi kèm)."""
    block = block_to_wire(
        svc.prepare_move(uid, params, trace_id=trace, source_tool="ledger___move_between_jars")
    )
    svc.save_turn_result(
        uid,
        conversation_id=conv,
        trace_id=trace,
        user_text="chuyển 100 nghìn",
        assistant_text="Bạn xác nhận nhé.",
        blocks=[{"seq": 0, "block": block}],
    )
    return block


def ref_of(block, conv=CONV):
    return {"conversation_id": conv, "confirm_block_id": block["id"]}


def confirmation(svc, sub=MINH, params=MOVE, **extra):
    return req(
        svc,
        "POST",
        "/confirmations",
        sub=sub,
        body={"tool": TOOL, "params": params, **extra},
    )


def action(svc, token, sub=MINH, params=MOVE, **extra):
    body = {"tool": TOOL, "params": params, **extra}
    if token is not None:
        body["confirm_token"] = token
    return req(svc, "POST", "/actions", sub=sub, body=body)


def conversation(svc, sub=MINH, conv=CONV):
    status, body = req(
        svc, "GET", f"/conversations/{conv}", sub=sub, path_params={"conversation_id": conv}
    )
    assert status == 200, body
    return body


def balance(repo, uid, code):
    return int(repo.users[uid]["jars"][code]["balance_vnd"])


@pytest.fixture
def validate(registry):
    def run(name, instance):
        v = Draft202012Validator(
            {"$ref": f"{OPENAPI_URI}#/components/schemas/{name}"}, registry=registry
        )
        errors = [f"{list(e.path)}: {e.message}" for e in v.iter_errors(instance)]
        assert not errors, errors

    return run


# --- trạng thái do server giữ -------------------------------------------------------------------
def test_chua_bam_thi_pending_roi_bam_xong_la_done_kem_receipt(validate):
    svc, repo, _ = make_service()
    block = offer(svc)
    body = conversation(svc)
    validate("ConversationResponse", body)
    assert body["turns"][0]["resolutions"] == [{"block_id": block["id"], "status": "pending"}]

    status, conf = confirmation(svc, **ref_of(block))
    assert status == 200, conf
    status, receipt = action(svc, conf["confirm_token"], **ref_of(block))
    assert status == 200, receipt
    assert balance(repo, MINH, "giai_tri") == 660_000

    body = conversation(svc)
    validate("ConversationResponse", body)
    (res,) = body["turns"][0]["resolutions"]
    assert res["block_id"] == block["id"] and res["status"] == "done"
    assert res["receipt"] == receipt  # đúng khối POST /actions đã trả
    assert res["resolved_at"].endswith("Z")
    assert body["turns"][0]["blocks"] == [block]  # khối confirm vẫn nguyên văn


def test_het_han_thi_expired_con_done_thi_van_la_done():
    svc, _, clock = make_service()
    block = offer(svc)
    clock.advance(svc.settings.offer_ttl_seconds - 1)
    assert conversation(svc)["turns"][0]["resolutions"][0]["status"] == "pending"
    clock.advance(2)
    assert conversation(svc)["turns"][0]["resolutions"][0] == {
        "block_id": block["id"],
        "status": "expired",
    }
    # hết hạn đề nghị nhưng người dùng đã thực hiện trước đó: done thắng
    svc2, _, clock2 = make_service()
    block2 = offer(svc2)
    _, conf = confirmation(svc2, **ref_of(block2))
    assert action(svc2, conf["confirm_token"], **ref_of(block2))[0] == 200
    clock2.advance(svc2.settings.offer_ttl_seconds * 3)
    assert conversation(svc2)["turns"][0]["resolutions"][0]["status"] == "done"


def test_chi_khoi_confirm_co_resolution():
    svc, _, _ = make_service()
    offer(svc)
    other = "1" * 32
    svc.save_turn_result(
        MINH,
        conversation_id=CONV,
        trace_id=other,
        user_text="số dư",
        assistant_text="ok",
        blocks=[
            {
                "seq": 0,
                "block": block_to_wire(
                    svc.jar_summary(MINH, trace_id=other, source_tool="ledger___get_jar_balances")
                ),
            }
        ],
    )
    turns = conversation(svc)["turns"]
    assert len(turns[0]["resolutions"]) == 1
    assert turns[1]["resolutions"] == []


# --- chống ghi lặp ở server -----------------------------------------------------------------------
def test_ghi_lan_hai_voi_token_moi_bi_already_applied_va_khong_ghi_them():
    svc, repo, _ = make_service()
    block = offer(svc)
    _, first = confirmation(svc, **ref_of(block))
    assert action(svc, first["confirm_token"], **ref_of(block))[0] == 200
    after_first = (balance(repo, MINH, "giai_tri"), balance(repo, MINH, "an_uong"))
    moves = len(repo.moves)

    # token mới hợp lệ, lấy bằng đường không kèm đề nghị (gọi REST trực tiếp)
    status, fresh = confirmation(svc)
    assert status == 200
    status, body = action(svc, fresh["confirm_token"], **ref_of(block))
    assert (status, body["error"]["code"]) == (409, "ALREADY_APPLIED")
    assert (balance(repo, MINH, "giai_tri"), balance(repo, MINH, "an_uong")) == after_first
    assert len(repo.moves) == moves
    assert repo.audits[-1]["outcome"] == "rejected" and repo.audits[-1]["code"] == "ALREADY_APPLIED"
    # token đó chưa bị tiêu: vẫn dùng được cho thao tác không kèm đề nghị
    assert action(svc, fresh["confirm_token"])[0] == 200


def test_cap_token_cho_de_nghi_da_thuc_hien_cung_bi_tu_choi():
    svc, _, _ = make_service()
    block = offer(svc)
    _, conf = confirmation(svc, **ref_of(block))
    assert action(svc, conf["confirm_token"], **ref_of(block))[0] == 200
    status, body = confirmation(svc, **ref_of(block))
    assert (status, body["error"]["code"]) == (409, "ALREADY_APPLIED")
    assert "confirm_token" not in body


def test_already_applied_thang_ca_het_tien_khi_so_du_da_doi():
    # Hũ nguồn còn đúng bằng số tiền: sau lần thực hiện thứ nhất không còn đủ. Bấm lại phải nhận
    # ALREADY_APPLIED (đúng sự thật), không phải INSUFFICIENT_FUNDS.
    svc, repo, _ = make_service()
    params = {**MOVE, "amount_vnd": 760_000}
    block = offer(svc, params=params)
    _, conf = confirmation(svc, params=params, **ref_of(block))
    assert action(svc, conf["confirm_token"], params=params, **ref_of(block))[0] == 200
    assert balance(repo, MINH, "giai_tri") == 0
    status, body = confirmation(svc, params=params, **ref_of(block))
    assert (status, body["error"]["code"]) == (409, "ALREADY_APPLIED")


def test_hai_yeu_cau_song_song_thua_cuoc_dua_o_khoa_unique(monkeypatch):
    # Bỏ qua kiểm trước (mô phỏng hai yêu cầu cùng vượt qua nó): lưới chắc chắn là khóa unique trong
    # transaction ghi, nên yêu cầu sau vẫn bị từ chối và không ghi gì.
    svc, repo, _ = make_service()
    block = offer(svc)
    _, c1 = confirmation(svc, **ref_of(block))
    _, c2 = confirmation(svc, **ref_of(block))
    assert action(svc, c1["confirm_token"], **ref_of(block))[0] == 200
    monkeypatch.setattr(repo, "resolution", lambda uid, bid: None)
    after_first = balance(repo, MINH, "giai_tri")
    status, body = action(svc, c2["confirm_token"], **ref_of(block))
    assert (status, body["error"]["code"]) == (409, "ALREADY_APPLIED")
    assert balance(repo, MINH, "giai_tri") == after_first
    assert len(repo.moves) == 1
    assert repo.audits[-1]["code"] == "ALREADY_APPLIED"


def test_khong_gui_de_nghi_thi_hanh_vi_cu_chuyen_hai_lan_duoc():
    svc, repo, _ = make_service()
    for _ in range(2):
        _, conf = confirmation(svc)
        assert action(svc, conf["confirm_token"])[0] == 200
    assert balance(repo, MINH, "giai_tri") == 560_000
    assert repo.resolved.get(MINH, {}) == {}


# --- người khác, id sai --------------------------------------------------------------------------
def test_nguoi_khac_khong_dung_duoc_de_nghi_cua_minh():
    svc, repo, _ = make_service()
    block = offer(svc)
    # lan cầm confirm_block_id của minh: chỉ tạo ra dòng của chính lan (RLS), không đụng đề nghị của minh
    _, conf = confirmation(svc, sub=LAN, **ref_of(block))
    status, receipt = action(svc, conf["confirm_token"], sub=LAN, **ref_of(block))
    assert status == 200
    assert balance(repo, MINH, "giai_tri") == 760_000  # tiền của minh không động tới
    assert conversation(svc)["turns"][0]["resolutions"][0]["status"] == "pending"
    assert conversation(svc, sub=LAN)["turns"] == []  # lan không thấy hội thoại của minh
    # minh vẫn thực hiện được đề nghị của mình
    _, conf_minh = confirmation(svc, **ref_of(block))
    assert action(svc, conf_minh["confirm_token"], **ref_of(block))[0] == 200
    assert conversation(svc)["turns"][0]["resolutions"][0]["status"] == "done"
    assert receipt["data"]["from_jar"]["balance_after_vnd"] != 0


def test_token_cua_nguoi_khac_van_bi_tu_choi_du_co_de_nghi():
    svc, repo, _ = make_service()
    block = offer(svc)
    _, conf_lan = confirmation(svc, sub=LAN)
    status, body = action(svc, conf_lan["confirm_token"], sub=MINH, **ref_of(block))
    assert (status, body["error"]["code"]) == (403, "TOKEN_INVALID")
    assert balance(repo, MINH, "giai_tri") == 760_000
    assert repo.resolved.get(MINH, {}) == {}


def test_id_khoi_cua_de_nghi_khac_khong_gan_duoc_vao_thao_tac_nay():
    svc, repo, _ = make_service()
    other = {**MOVE, "amount_vnd": 5_000}
    block = offer(svc, params=other)
    _, conf = confirmation(svc)
    status, body = action(
        svc, conf["confirm_token"], **ref_of(block)
    )  # tham số 100.000, khối là 5.000
    assert (status, body["error"]["code"]) == (409, "PARAMS_MISMATCH")
    status, body = confirmation(svc, **ref_of(block))
    assert (status, body["error"]["code"]) == (409, "PARAMS_MISMATCH")
    assert balance(repo, MINH, "giai_tri") == 760_000


@pytest.mark.parametrize(
    "extra",
    [
        {"conversation_id": CONV},
        {"confirm_block_id": "confirm:abc:0123456789ab"},
        {"conversation_id": CONV, "confirm_block_id": "khong-phai-id-khoi"},
        {"conversation_id": CONV, "confirm_block_id": "confirm:abc:0123456789AB"},
        {"conversation_id": CONV, "confirm_block_id": 12345},
        {"conversation_id": "", "confirm_block_id": "confirm:abc:0123456789ab"},
        {"conversation_id": 7, "confirm_block_id": "confirm:abc:0123456789ab"},
        {"conversation_id": "c" * 300, "confirm_block_id": "confirm:abc:0123456789ab"},
        {"conversation_id": CONV, "confirm_block_id": "confirm:" + "t" * 70 + ":0123456789ab"},
    ],
)
def test_tham_chieu_de_nghi_sai_dinh_dang_bi_tu_choi_400(extra):
    svc, repo, _ = make_service()
    status, body = confirmation(svc, **extra)
    assert (status, body["error"]["code"]) == (400, "PARAMS_INVALID")
    _, conf = confirmation(svc)
    status, body = action(svc, conf["confirm_token"], **extra)
    assert (status, body["error"]["code"]) == (400, "PARAMS_INVALID")
    assert balance(repo, MINH, "giai_tri") == 760_000


def test_de_nghi_da_thuc_hien_khong_lo_ra_cho_nguoi_khac_qua_confirmations():
    svc, _, _ = make_service()
    block = offer(svc)
    _, conf = confirmation(svc, **ref_of(block))
    assert action(svc, conf["confirm_token"], **ref_of(block))[0] == 200
    # lan hỏi cùng id: không bị ALREADY_APPLIED (không lộ việc minh đã thực hiện)
    status, _ = confirmation(svc, sub=LAN, **ref_of(block))
    assert status == 200


def test_dat_lai_demo_xoa_trang_thai_da_thuc_hien():
    svc, repo, _ = make_service()
    block = offer(svc)
    _, conf = confirmation(svc, **ref_of(block))
    assert action(svc, conf["confirm_token"], **ref_of(block))[0] == 200
    assert repo.resolved[MINH]
    svc.reset_demo(MINH, "minh", trace_id=TRACE)
    assert repo.resolved[MINH] == {}
