"""Gateway `yofina-gateway` thật (client MCP, access token Cognito thật): danh tính do interceptor ghi đè,
Cedar làm lớp phụ, tool ghi không token không ghi, token bịa bị từ chối, lưu và đọc lại lượt hội thoại.

Chạy: `uv run pytest tests/integration/test_gateway_identity.py -m integration`.
"""

from __future__ import annotations

import pytest
from agentcore_helpers import McpFailure, raw_gateway_post

EXPECTED_TOOLS = {
    "ledger___get_jar_balances",
    "ledger___query_transactions",
    "ledger___move_between_jars",
    "ledger___save_turn",
}
MOVE = {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100_000}

pytestmark = pytest.mark.usefixtures("fresh")


def rest_balances(api, who):
    status, body = api(who, "GET", "/jars")
    assert status == 200
    return {j["code"]: j["balance_vnd"] for j in body["jars"]}


def gw_balances(reply):
    assert reply.status == "OK", reply.text
    return {j["code"]: j["balance_vnd"] for j in reply.data["data"]["jars"]}


def test_tools_list_dung_ten_co_tien_to_target(gw):
    assert set(gw("minh").tool_names()) == EXPECTED_TOOLS


def test_minh_doc_hu_qua_gateway_khop_rest(gw, api):
    reply = gw("minh").call("ledger___get_jar_balances")
    assert not reply.is_error
    assert len(reply.data["data"]["jars"]) == 7
    assert gw_balances(reply) == rest_balances(api, "minh")


def test_lan_gui_user_id_cua_minh_van_chi_thay_du_lieu_cua_lan(gw, api, subs):
    assert subs["minh"] != subs["lan"]
    sneaky = gw("lan").call("ledger___get_jar_balances", {"user_id": subs["minh"]})
    assert gw_balances(sneaky) == rest_balances(api, "lan")
    assert gw_balances(sneaky) != rest_balances(api, "minh")
    tx = gw("lan").call("ledger___query_transactions", {"user_id": subs["minh"], "limit": 50})
    mine = gw("lan").call("ledger___query_transactions", {"limit": 50})
    assert tx.status == "OK" and tx.data["data"] == mine.data["data"]


def test_bo_user_id_van_chay_va_user_id_rong_cung_vay(gw, api):
    for args in ({}, {"user_id": ""}):
        assert gw_balances(gw("minh").call("ledger___get_jar_balances", args)) == rest_balances(
            api, "minh"
        )


def test_id_token_bi_tu_choi(sess, gateway_url, accounts):
    from _demo_auth import REGION, ssm_param
    from pycognito.aws_srp import AWSSRP

    acct = accounts["minh"]
    result = AWSSRP(
        username=acct["email"],
        password=acct["password"],
        pool_id=ssm_param("auth/user-pool-id", sess=sess),
        client_id=ssm_param("auth/client-id", sess=sess),
        pool_region=REGION,
    ).authenticate_user()["AuthenticationResult"]
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    assert raw_gateway_post(gateway_url, result["IdToken"], body).status_code in (401, 403)
    assert raw_gateway_post(gateway_url, result["AccessToken"], body).status_code == 200


def test_khong_token_va_token_rac_bi_tu_choi(gateway_url, tokens):
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    assert raw_gateway_post(gateway_url, None, body).status_code == 401
    assert raw_gateway_post(gateway_url, "abc.def.ghi", body).status_code in (401, 403)
    forged = tokens["minh"].rsplit(".", 1)[0] + ".AAAA"  # đúng payload, chữ ký sai
    assert raw_gateway_post(gateway_url, forged, body).status_code in (401, 403)


def test_move_khong_token_tra_needs_confirmation_va_khong_ghi(gw, api):
    before = rest_balances(api, "minh")
    reply = gw("minh").call("ledger___move_between_jars", MOVE)
    assert reply.status == "NEEDS_CONFIRMATION", reply.text
    assert reply.data["data"]["params"] == MOVE
    assert rest_balances(api, "minh") == before


def test_move_voi_user_id_nguoi_khac_khong_ghi_vao_nguoi_khac(gw, api, subs):
    before_minh, before_lan = rest_balances(api, "minh"), rest_balances(api, "lan")
    reply = gw("lan").call("ledger___move_between_jars", {**MOVE, "user_id": subs["minh"]})
    assert reply.status == "NEEDS_CONFIRMATION"
    assert rest_balances(api, "minh") == before_minh and rest_balances(api, "lan") == before_lan


def test_token_bia_bi_tu_choi_va_db_khong_doi(gw, api):
    before = rest_balances(api, "minh")
    fake = "eyJzdWIiOiJ4In0.YWJjZGVm"
    reply = gw("minh").call("ledger___move_between_jars", {**MOVE, "confirm_token": fake})
    assert reply.status == "ERROR" and reply.data["code"] == "TOKEN_INVALID", reply.text
    # không có dấu chấm: Cedar chặn ngay ở Gateway (lỗi giao thức -32002)
    with pytest.raises(McpFailure) as exc:
        gw("minh").call(
            "ledger___move_between_jars", {**MOVE, "confirm_token": "khongcodauchamnao"}
        )
    assert exc.value.code == -32002
    assert rest_balances(api, "minh") == before


def test_vuot_han_muc_bi_cedar_tu_choi(gw, api):
    before = rest_balances(api, "minh")
    with pytest.raises(McpFailure) as exc:
        gw("minh").call("ledger___move_between_jars", {**MOVE, "amount_vnd": 60_000_000})
    assert exc.value.code == -32002 and "denied" in exc.value.message.lower()
    assert rest_balances(api, "minh") == before


def test_token_that_di_qua_gateway_ghi_mot_lan(gw, api):
    before = rest_balances(api, "minh")
    status, conf = api(
        "minh", "POST", "/confirmations", {"tool": "move_between_jars", "params": MOVE}
    )
    assert status == 200, conf
    reply = gw("minh").call(
        "ledger___move_between_jars", {**MOVE, "confirm_token": conf["confirm_token"]}
    )
    assert reply.status == "OK", reply.text
    after = rest_balances(api, "minh")
    assert after["giai_tri"] == before["giai_tri"] - 100_000
    assert after["an_uong"] == before["an_uong"] + 100_000
    again = gw("minh").call(
        "ledger___move_between_jars", {**MOVE, "confirm_token": conf["confirm_token"]}
    )
    assert again.data["code"] == "TOKEN_REUSED" and rest_balances(api, "minh") == after


def test_save_turn_qua_gateway_va_doc_lai_bang_rest(gw, api, subs):
    conv, trace = "gw-test-conversation-" + "x" * 20, "a1b2c3d4e5f60718293a4b5c6d7e8f90"
    notice = {
        "v": 1,
        "id": f"notice:{trace}:test",
        "type": "notice",
        "trace_id": trace,
        "fallback_text": "Thử.",
        "source": {"tool": "agent", "as_of": "2026-12-10T03:00:00Z", "app_date": "2026-11-21"},
        "data": {
            "kind": "degraded",
            "title": "Thử",
            "message": "Thử nghiệm.",
            "code": "RATE_LIMITED",
        },
    }
    # lan tự gửi user_id của minh: vẫn lưu cho lan, minh không thấy gì
    reply = gw("lan").call(
        "ledger___save_turn",
        {
            "user_id": subs["minh"],
            "conversation_id": conv,
            "trace_id": trace,
            "user_text": "xin chào",
            "assistant_text": "Chào bạn",
            "blocks": [{"seq": 0, "block": notice}],
        },
    )
    assert reply.status == "OK" and reply.data["data"]["blocks_saved"] == 1, reply.text
    status, body = api("lan", "GET", f"/conversations/{conv}")
    assert status == 200 and len(body["turns"]) == 1
    turn = body["turns"][0]
    assert (turn["user_text"], turn["assistant_text"]) == ("xin chào", "Chào bạn")
    assert turn["blocks"] == [notice]
    status, body = api("minh", "GET", f"/conversations/{conv}")
    assert status == 200 and body["turns"] == []
    status, listing = api("lan", "GET", "/conversations")
    assert conv in [c["conversation_id"] for c in listing["conversations"]]
    # Cedar/Gateway không cho lưu khối chứa token
    leak = gw("lan").call(
        "ledger___save_turn",
        {
            "conversation_id": conv,
            "trace_id": "ffffffffffffffffffffffffffffffff",
            "blocks": [{"seq": 0, "block": {**notice, "data": {"confirm_token": "x.y"}}}],
        },
    )
    assert leak.status == "ERROR" and leak.data["code"] == "PARAMS_INVALID"
