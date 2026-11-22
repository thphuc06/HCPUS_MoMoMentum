"""Mười tool của target `ledger` qua AgentCore Gateway THẬT (MCP, access token Cognito): schema, danh tính, Cedar mỗi tool,
tool ghi không token chỉ xem trước (không ghi), và `save_jars` / `confirm_salary` không lộ cho agent."""

from __future__ import annotations

import pytest
from agentcore_helpers import McpFailure

pytestmark = pytest.mark.usefixtures("fresh")


def balances(api, who):
    status, body = api(who, "GET", "/jars")
    assert status == 200, body
    return {j["code"]: j["balance_vnd"] for j in body["jars"]}


def test_schema_tool_tren_gateway_khop_hop_dong_va_khong_lo_save_jars_confirm_salary(gw):
    tools = {t.name: t for t in gw("minh").tools()}
    assert "ledger___save_jars" not in tools and "ledger___confirm_salary" not in tools
    assert set(tools) >= {
        "ledger___record_transaction",
        "ledger___update_profile",
        "ledger___assign_jar",
        "ledger___get_cashflow_summary",
        "ledger___get_obligations",
        "ledger___get_unclassified",
    }
    props = (
        getattr(tools["ledger___record_transaction"], "inputSchema", None)
        or tools["ledger___record_transaction"].input_schema
    )["properties"]
    assert {"kind", "amount_vnd", "funding", "client_ref", "confirm_token"} <= set(props)


def test_record_transaction_khong_token_chi_xem_truoc_khong_ghi(gw, api):
    before = balances(api, "minh")
    reply = gw("minh").call(
        "ledger___record_transaction",
        {"kind": "expense", "amount_vnd": 90_000, "jar": "an_uong", "tx_type": "food_drink"},
    )
    assert reply.status == "NEEDS_CONFIRMATION", reply.text
    data = reply.data["data"]
    assert data["tool"] == "record_transaction" and data["params"]["jar"] == "an_uong"
    assert (
        data["changes"][0]["before"] == "380.000 ₫" and data["changes"][0]["after"] == "290.000 ₫"
    )
    assert balances(api, "minh") == before


def test_update_profile_va_assign_jar_khong_token_chi_xem_truoc(gw, api):
    r = gw("minh").call("ledger___update_profile", {"monthly_salary_vnd": 9_500_000})
    assert (
        r.status == "NEEDS_CONFIRMATION" and r.data["data"]["changes"][0]["before"] == "9.000.000 ₫"
    )
    items = gw("minh").call("ledger___get_unclassified").data["data"]["items"]
    tx = items[0]["transaction"]["id"]
    r = gw("minh").call("ledger___assign_jar", {"transaction_id": tx, "jar": "di_lai"})
    assert r.status == "NEEDS_CONFIRMATION"
    assert api("minh", "GET", "/profile")[1]["profile"]["monthly_salary_vnd"] == 9_000_000


def test_token_that_di_qua_gateway_ghi_mot_lan_va_phat_receipt_action(gw, api):
    params = {"kind": "expense", "amount_vnd": 25_000, "jar": "di_lai", "tx_type": "ride_hailing"}
    status, conf = api(
        "minh", "POST", "/confirmations", {"tool": "record_transaction", "params": params}
    )
    assert status == 200, conf
    before = balances(api, "minh")["di_lai"]
    reply = gw("minh").call(
        "ledger___record_transaction", {**params, "confirm_token": conf["confirm_token"]}
    )
    assert reply.status == "OK", reply.text
    assert reply.data["data"]["jars_after"] == [
        {"code": "di_lai", "name": "Đi lại", "balance_after_vnd": before - 25_000}
    ]
    again = gw("minh").call(
        "ledger___record_transaction", {**params, "confirm_token": conf["confirm_token"]}
    )
    assert again.status == "ERROR" and again.data["code"] == "TOKEN_REUSED"
    assert balances(api, "minh")["di_lai"] == before - 25_000


def test_vuot_han_muc_giao_dich_va_token_rac_bi_cedar_chan(gw, api):
    before = balances(api, "minh")
    with pytest.raises(McpFailure) as exc:
        gw("minh").call(
            "ledger___record_transaction",
            {"kind": "expense", "amount_vnd": 60_000_000, "jar": "du_phong"},
        )
    assert exc.value.code == -32002
    with pytest.raises(McpFailure) as exc:
        gw("minh").call(
            "ledger___record_transaction",
            {
                "kind": "expense",
                "amount_vnd": 1_000,
                "jar": "di_lai",
                "confirm_token": "khongcodauchamnao",
            },
        )
    assert exc.value.code == -32002
    with pytest.raises(McpFailure) as exc:
        gw("minh").call(
            "ledger___update_profile", {"monthly_salary_vnd": 1, "confirm_token": "rac"}
        )
    assert exc.value.code == -32002
    assert balances(api, "minh") == before


def test_lan_gui_user_id_cua_minh_van_chi_thay_du_lieu_cua_lan(gw, subs):
    sneaky = gw("lan").call("ledger___get_obligations", {"user_id": subs["minh"]})
    names = {o["name"] for o in sneaky.data["data"]["obligations"]}
    assert (
        "Tiền trọ" in names and "Tiền thuê phòng" not in names
    )  # nghĩa vụ của Lan, không phải của Minh
    cf = gw("lan").call("ledger___get_cashflow_summary", {"user_id": subs["minh"]})
    assert (
        cf.data["data"]["unclassified_pending_vnd"] == 0
    )  # Minh có 180.000 chưa phân loại, Lan không
    un = gw("lan").call("ledger___get_unclassified", {"user_id": subs["minh"]})
    assert un.data["data"]["count"] == 0


def test_get_obligations_kem_han_muc_tra_sau_va_dong_tien_tach_luong_khoi_tien_vao_khac(gw):
    ob = gw("minh").call("ledger___get_obligations", {"within_days": 30}).data["data"]
    assert ob["credit_line"]["product_label"] == "Trả sau (mô phỏng)" and ob["total_due_vnd"] > 0
    assert all(o["status"] == "active" for o in ob["obligations"])
    cf = gw("minh").call("ledger___get_cashflow_summary").data["data"]
    assert cf["salary_income_vnd"] == 9_000_000 and cf["other_income_vnd"] == 350_000
    assert cf["unclassified_pending_vnd"] == 180_000
