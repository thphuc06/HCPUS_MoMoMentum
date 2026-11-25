"""Gọi thẳng Lambda `yofina-ledger` theo dạng sự kiện của AgentCore Gateway (boto3 invoke, tên tool ở
client context, `user_id` ở sự kiện như interceptor sẽ ghi đè), cho cả 3 tool."""

from __future__ import annotations

import pytest
from conftest import demo_jars

from yofina_core.confirm import params_hash

TOOL = "move_between_jars"
MOVE = {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100_000}

pytestmark = pytest.mark.usefixtures("fresh")


def balances(api, who):
    _, body = api(who, "GET", "/jars")
    return {j["code"]: j["balance_vnd"] for j in body["jars"]}


def rest_token(api, who, params=MOVE):
    status, conf = api(who, "POST", "/confirmations", {"tool": TOOL, "params": params})
    assert status == 200, conf
    return conf["confirm_token"]


def test_get_jar_balances(invoke, subs, schema_validator, api):
    res = invoke("get_jar_balances", {"user_id": subs["minh"], "tham_so_la": "bi bo qua"})
    schema_validator.results("GetJarBalancesResult", res)
    assert res["status"] == "OK"
    assert {j["code"]: j["balance_vnd"] for j in res["data"]["jars"]} == balances(api, "minh")
    assert res["data"]["jars_total_vnd"] == 7_730_000


def test_query_transactions_loc_va_phan_trang(invoke, subs, schema_validator):
    res = invoke("query_transactions", {"user_id": subs["minh"], "limit": 5})
    schema_validator.results("QueryTransactionsResult", res)
    txs = res["data"]["transactions"]
    assert len(txs) == 5 and res["data"]["has_more"] is True
    times = [t["occurred_at"] for t in txs]
    assert times == sorted(times, reverse=True)  # mới nhất trước
    res = invoke("query_transactions", {"user_id": subs["minh"], "jar": "du_phong", "limit": 50})
    schema_validator.results("QueryTransactionsResult", res)
    assert {t["jar"] for t in res["data"]["transactions"]} == {"du_phong"}
    res = invoke(
        "query_transactions",
        {"user_id": subs["minh"], "from_date": "2099-01-01", "limit": 10},
    )
    assert res["data"] == {"transactions": [], "has_more": False}
    res = invoke("query_transactions", {"user_id": subs["minh"], "jar": "Ăn uống"})
    schema_validator.results("ToolError", res)
    assert res["code"] == "PARAMS_INVALID"


def test_move_khong_token_khong_ghi_tra_needs_confirmation(invoke, subs, api, schema_validator):
    before = balances(api, "minh")
    res = invoke(TOOL, {"user_id": subs["minh"], **MOVE, "user_confirmed": True})
    schema_validator.results("MoveBetweenJarsResult", res)
    assert res["status"] == "NEEDS_CONFIRMATION"
    assert res["data"]["params_hash"] == params_hash(TOOL, MOVE)
    assert res["data"]["preview"]["from"]["after_vnd"] == before["giai_tri"] - 100_000
    assert balances(api, "minh") == before


def test_move_co_token_hop_le_ghi_va_tra_receipt(invoke, subs, api, schema_validator):
    before = balances(api, "minh")
    tok = rest_token(api, "minh")
    res = invoke(TOOL, {"user_id": subs["minh"], **MOVE, "confirm_token": tok})
    schema_validator.results("MoveBetweenJarsResult", res)
    assert res["status"] == "OK"
    assert res["data"]["to_jar"]["balance_after_vnd"] == before["an_uong"] + 100_000
    after = balances(api, "minh")
    assert after["giai_tri"] == before["giai_tri"] - 100_000
    # dùng lại token qua đường Gateway: bị từ chối, vẫn một lần ghi
    again = invoke(TOOL, {"user_id": subs["minh"], **MOVE, "confirm_token": tok})
    schema_validator.results("ToolError", again)
    assert again["code"] == "TOKEN_REUSED"
    assert balances(api, "minh") == after


def test_token_cua_lan_khong_ghi_duoc_cho_minh_qua_gateway(invoke, subs, api, schema_validator):
    before = balances(api, "minh")
    tok_lan = rest_token(api, "lan")
    res = invoke(TOOL, {"user_id": subs["minh"], **MOVE, "confirm_token": tok_lan})
    schema_validator.results("ToolError", res)
    assert res["code"] == "TOKEN_INVALID"
    assert balances(api, "minh") == before


def test_user_id_quyet_dinh_du_lieu_nen_interceptor_phai_ghi_de(invoke, subs):
    """Lambda tin `user_id` trong sự kiện (interceptor ghi đè từ JWT). Với user_id của lan, kết quả là
    dữ liệu của lan: không có cách nào đọc dữ liệu minh nếu interceptor đặt đúng user_id."""
    res = invoke("get_jar_balances", {"user_id": subs["lan"]})
    assert len(res["data"]["jars"]) == len(demo_jars("lan"))  # ví demo của lan sau đặt lại (issue #39)


def test_thieu_user_id_hoac_tool_la(invoke, subs, schema_validator):
    res = invoke("get_jar_balances", {})
    schema_validator.results("ToolError", res)
    assert res["code"] == "UNAUTHENTICATED"
    res = invoke("xoa_het", {"user_id": subs["minh"]})
    schema_validator.results("ToolError", res)
    assert res["code"] == "PARAMS_INVALID"
