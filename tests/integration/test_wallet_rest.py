"""Ví mô phỏng phase 2 trên môi trường THẬT: REST (JWT Cognito) -> Lambda ledger -> Aurora, kèm sự kiện thật lên EventBridge.

Tiêu chí phase 2 do luồng sổ cái chịu trách nhiệm: 2 (giao dịch 200.000 ₫ đổi số dư ngay), 6 (Trả sau 300.000 ₫ sinh nghĩa vụ
333.000 ₫ hạn ngày 5), 7 (onboarding tài khoản trắng), 9 (phần sự kiện), cộng chuẩn hóa tham số, khử trùng, cô lập người dùng,
đề nghị hết hạn hoặc đã hủy. Số phí lấy từ `GET /credit-line` (đọc bảng `fee_schedules`), không gắn cứng trong test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from conftest import demo_balances, demo_jars, demo_wallet, flow

from yofina_core.blocks import block_to_wire, build_confirm_action, parse_block

pytestmark = pytest.mark.usefixtures("fresh")

# ví demo của minh sau đặt lại (bộ hũ demo, issue #39: Chi hằng ngày cạnh các hũ tự thêm, Hóa đơn gộp vào Nghĩa vụ, Du lịch là hũ goal
# `muc_tieu`, thêm Đầu tư 0 ₫), suy từ bộ sinh persona qua cùng ánh xạ mã hũ của đặt lại; tổng là 7.730.000 ₫ của ví persona cộng số dư
# hũ Chi hằng ngày trong khối `demo_jars` của spec, đọc từ bộ sinh, không chép số
MINH_BALANCES = demo_balances("minh")
MINH_JARS_TOTAL = sum(MINH_BALANCES.values())
MINH_TOTAL = MINH_JARS_TOTAL + sum(demo_wallet("minh").system_balances.values())  # cộng Tiền vào khác, Chưa phân loại


def jars(api, who):
    status, body = api(who, "GET", "/jars")
    assert status == 200, body
    return {j["code"]: j["balance_vnd"] for j in body["jars"]}


def get(api, who, path, **kw):
    status, body = api(who, "GET", path, **kw)
    assert status == 200, (path, body)
    return body


def code(body) -> str:
    return body["error"]["code"]


# --- đọc: mọi endpoint đúng hợp đồng ---------------------------------------------------------------------------
def test_moi_endpoint_doc_dung_schema_cua_openapi(api, schema_validator):
    for path, schema in (
        ("/overview", "OverviewResponse"),
        ("/profile", "ProfileResponse"),
        ("/jars/an_uong", "JarDetailResponse"),
        ("/jars/chua_phan_loai", "JarDetailResponse"),
        ("/transactions?limit=5", "TransactionsResponse"),
        ("/tx-types", "TxTypesResponse"),
        ("/payees", "PayeesResponse"),
        ("/obligations", "ObligationsResponse"),
        ("/credit-line", "CreditLineResponse"),
        ("/salary-events", "SalaryEventsResponse"),
        ("/jar-templates", "JarTemplatesResponse"),
        ("/jars", "JarsResponse"),
    ):
        schema_validator.openapi(schema, get(api, "minh", path))


def test_tong_quan_minh_dung_so_va_thu_chua_co_du_bao(api):
    ov = get(api, "minh", "/overview")
    assert ov["balance"] == {
        "total_vnd": MINH_TOTAL,
        "jars_total_vnd": MINH_JARS_TOTAL,
        "other_income_vnd": 350_000,
        "unclassified_vnd": -180_000,
    }
    assert {j["code"]: j["balance_vnd"] for j in ov["jars"]} == MINH_BALANCES
    assert [j["code"] for j in ov["system_jars"]] == ["tien_vao_khac", "chua_phan_loai"]
    assert ov["profile"] == {
        "display_name": "Minh",
        "onboarded": True,
        "monthly_salary_vnd": 9_000_000,
        "payday_day": 5,
        "risk_tolerance": "medium",
    }
    assert ov["next_payday"]["date"] == "2026-12-05" and ov["next_payday"]["state"] == "expected"
    assert (
        ov["credit_line"]["product_label"] == "Trả sau (mô phỏng)"
        and ov["credit_line"]["outstanding_vnd"] == 967_000
    )
    assert ov["needs_review_count"] == 2
    # dự báo là việc của đợt sau: chưa có lần chạy thì null đúng hợp đồng, jar không có trường dự báo
    if ov["forecast"] is None:
        assert all("status" not in j for j in ov["jars"])
    # GET /jars giữ hình dạng phase 1: các hũ của ví demo, không có hũ hệ thống
    status, body = api("minh", "GET", "/jars")
    assert status == 200 and len(body["jars"]) == len(MINH_BALANCES) and body["jars_total_vnd"] == MINH_JARS_TOTAL


def test_du_bao_chua_co_thi_tra_503_forecast_unavailable_dung_hinh_dang(api):
    status, body = api("minh", "GET", "/forecasts/an_uong")
    if status == 200:  # đợt sau có pipeline thì đã có khối
        assert body["type"] == "forecast_timeline"
        return
    assert (status, code(body)) == (503, "FORECAST_UNAVAILABLE")
    status, body = api("minh", "GET", "/forecasts/khong_co")
    assert (status, code(body)) == (404, "JAR_NOT_FOUND")
    # hũ hệ thống không bao giờ có dự báo: 404 FORECAST_NOT_APPLICABLE, không phải 503 (503 chỉ là lỗi tạm thời)
    for system_jar in ("tien_vao_khac", "chua_phan_loai"):
        status, body = api("minh", "GET", f"/forecasts/{system_jar}")
        assert (status, code(body)) == (404, "FORECAST_NOT_APPLICABLE")


def test_giao_dich_loc_va_phan_trang_con_tro_khong_trung_dong(api):
    p1 = get(api, "minh", "/transactions?limit=7")
    assert len(p1["transactions"]) == 7 and p1["next_cursor"]
    p2 = get(api, "minh", f"/transactions?limit=7&cursor={p1['next_cursor']}")
    assert not {t["id"] for t in p1["transactions"]} & {t["id"] for t in p2["transactions"]}
    assert max(t["occurred_at"] for t in p2["transactions"]) <= min(
        t["occurred_at"] for t in p1["transactions"]
    )
    inc = get(api, "minh", "/transactions?kind=income&limit=50")
    assert inc["transactions"] and all(t["kind"] == "income" for t in inc["transactions"])
    jar = get(api, "minh", "/transactions?jar=muc_tieu&limit=50")  # hũ goal dựng từ Du lịch (chia lương các kỳ trước)
    assert jar["transactions"] and all(t["jar"] == "muc_tieu" for t in jar["transactions"])
    assert api("minh", "GET", "/transactions?cursor=rac")[0] == 400
    assert api("minh", "GET", "/transactions?from=21-11-2026")[0] == 400
    assert api("minh", "GET", "/transactions?kind=xyz")[0] == 400
    assert api("minh", "GET", "/obligations?status=xyz")[0] == 400


def test_lan_va_khoa_co_du_lieu_rieng(api):
    lan, khoa = get(api, "lan", "/overview"), get(api, "khoa", "/overview")
    assert lan["profile"]["monthly_salary_vnd"] == 4_500_000 and len(lan["jars"]) == len(demo_jars("lan"))
    assert khoa["profile"]["monthly_salary_vnd"] == 7_000_000 and len(khoa["jars"]) == len(demo_jars("khoa"))
    assert lan["credit_line"]["outstanding_vnd"] == 0 and lan["balance"]["unclassified_vnd"] == 0
    assert not [o for o in get(api, "lan", "/obligations")["obligations"] if o["kind"] == "bnpl"]


# --- tiêu chí 2: chi 200.000 đồng đổi số dư ngay -----------------------------------------------------------------
def test_chi_200k_tu_an_uong_doi_so_du_ngay(api, schema_validator):
    status, receipt = flow(
        api, "minh", "record_transaction",
        {"kind": "expense", "amount_vnd": 200_000, "jar": "an_uong", "tx_type": "food_drink", "counterparty": "Cơm tấm Cô Ba"},
    )  # fmt: skip
    assert status == 200, receipt
    assert parse_block(receipt).type == "receipt_action"
    assert receipt["data"]["jars_after"] == [
        {"code": "an_uong", "name": "Ăn uống", "balance_after_vnd": 180_000}
    ]
    assert jars(api, "minh")["an_uong"] == 180_000
    ov = get(api, "minh", "/overview")
    assert (
        ov["recent_transactions"][0]["amount_vnd"] == -200_000
        and ov["recent_transactions"][0]["merchant"] == "Cơm tấm Cô Ba"
    )
    assert ov["balance"]["total_vnd"] == MINH_TOTAL - 200_000
    schema_validator.openapi("OverviewResponse", ov)


def test_chi_vuot_so_du_va_vuot_han_muc_bi_tu_choi(api):
    status, body = flow(
        api,
        "minh",
        "record_transaction",
        {"kind": "expense", "amount_vnd": 999_000, "jar": "an_uong"},
    )
    assert (status, code(body)) == (422, "INSUFFICIENT_FUNDS")
    before = jars(api, "minh")
    status, body = flow(
        api,
        "minh",
        "record_transaction",
        {"kind": "expense", "amount_vnd": 60_000_000, "jar": "du_phong"},
    )
    assert (status, code(body)) == (422, "AMOUNT_LIMIT_EXCEEDED")
    assert jars(api, "minh") == before


def test_khong_token_la_428_khong_ghi_gi(api):
    before = jars(api, "minh")
    status, body = api(
        "minh",
        "POST",
        "/actions",
        {
            "tool": "record_transaction",
            "params": {"kind": "expense", "amount_vnd": 5_000, "jar": "an_uong"},
        },
    )
    assert (status, code(body)) == (428, "NEEDS_CONFIRMATION")
    assert jars(api, "minh") == before


def test_token_cap_cho_ban_chuan_hoa_va_doi_tham_so_bi_tu_choi(api):
    params = {
        "kind": "expense",
        "amount_vnd": 50_000,
        "tx_type": "ride_hailing",
    }  # thiếu jar: server suy ra
    before = jars(api, "minh")["di_lai"]
    status, conf = api(
        "minh", "POST", "/confirmations", {"tool": "record_transaction", "params": params}
    )
    assert status == 200, conf
    assert conf["params"]["jar"] == "di_lai" and conf["params"]["funding"] == "jar"
    status, body = api(
        "minh",
        "POST",
        "/actions",
        {
            "tool": "record_transaction",
            "params": {**params, "amount_vnd": 90_000},
            "confirm_token": conf["confirm_token"],
        },
    )
    assert (status, code(body)) == (409, "PARAMS_MISMATCH")
    status, body = api(
        "minh",
        "POST",
        "/actions",
        {"tool": "record_transaction", "params": params, "confirm_token": conf["confirm_token"]},
    )
    assert status == 200, body  # token chưa mất vì lần trước đổi tham số
    status, body = api(
        "minh",
        "POST",
        "/actions",
        {"tool": "record_transaction", "params": params, "confirm_token": conf["confirm_token"]},
    )
    assert (status, code(body)) == (409, "TOKEN_REUSED")
    assert jars(api, "minh")["di_lai"] == before - 50_000


def test_gui_trung_client_ref_khong_ghi_hai_lan(api):
    p = {
        "kind": "expense",
        "amount_vnd": 20_000,
        "jar": "di_lai",
        "tx_type": "public_transport",
        "counterparty": "Xe buýt",
        "client_ref": f"it-{uuid.uuid4().hex[:8]}",
    }
    before = jars(api, "minh")["di_lai"]
    assert flow(api, "minh", "record_transaction", p)[0] == 200
    status, body = flow(api, "minh", "record_transaction", p)
    assert (status, code(body)) == (409, "DUPLICATE_TRANSACTION")
    assert jars(api, "minh")["di_lai"] == before - 20_000  # chỉ trừ một lần


# --- tiêu chí 6: Trả sau (mô phỏng) -------------------------------------------------------------------------------
def test_mua_300k_bang_tra_sau_sinh_nghia_vu_gom_phi_tu_bang_va_han_ngay_5(api, schema_validator):
    credit = get(api, "lan", "/credit-line")
    fee = next(f for f in credit["fees"] if f["fee_type"] == "monthly_service_fee")[
        "amount_vnd"
    ]  # đọc từ bảng fee_schedules
    before = jars(api, "lan")
    status, receipt = flow(
        api, "lan", "record_transaction",
        {"kind": "expense", "amount_vnd": 300_000, "jar": "giai_tri", "tx_type": "entertainment", "funding": "credit", "counterparty": "Tiki"},
    )  # fmt: skip
    assert status == 200, receipt
    assert receipt["data"]["jars_after"] == []
    assert jars(api, "lan") == before  # mua bằng hạn mức không đổi số dư hũ
    (ob,) = [o for o in get(api, "lan", "/obligations")["obligations"] if o["kind"] == "bnpl"]
    schema_validator.results("Obligation", ob)
    assert (
        ob["amount_vnd"] == 300_000 + fee == 333_000
        and ob["principal_vnd"] == 300_000
        and ob["fee_vnd"] == fee
    )
    assert (
        ob["due_date"].endswith("-05") and ob["status"] == "active" and ob["source"] == "bnpl_auto"
    )
    assert datetime.fromisoformat(ob["due_date"]).day == 5
    ov = get(api, "lan", "/overview")
    assert ov["credit_line"]["outstanding_vnd"] == 300_000
    assert any(o["id"] == ob["id"] for o in ov["obligations_due"])
    # vượt hạn mức còn lại
    status, body = flow(
        api,
        "lan",
        "record_transaction",
        {"kind": "expense", "amount_vnd": 1_800_000, "jar": "giai_tri", "funding": "credit"},
    )
    assert (status, code(body)) == (422, "CREDIT_LIMIT_EXCEEDED")


# --- lương ------------------------------------------------------------------------------------------------------
def test_luong_ve_xac_nhan_chia_dung_luat_va_khong_xac_nhan_hai_lan(api):
    before = jars(api, "minh")
    status, receipt = flow(
        api,
        "minh",
        "record_transaction",
        {"kind": "income", "amount_vnd": 9_000_000, "tx_type": "salary"},
    )
    assert status == 200, receipt
    fu = receipt["data"]["follow_up"]
    assert fu["kind"] == "confirm_salary" and fu["ask_update_salary"] is False
    pending = get(api, "minh", "/salary-events")["salary_events"]
    assert [e["id"] for e in pending] == [fu["salary_event_id"]]
    assert get(api, "minh", "/overview")["balance"]["other_income_vnd"] == 9_350_000
    status, done = flow(
        api,
        "minh",
        "confirm_salary",
        {"salary_event_id": fu["salary_event_id"], "decision": "split"},
    )
    assert status == 200, done
    after = jars(api, "minh")
    # tỷ lệ chia của ví demo (tổng tỷ lệ của hũ nguồn trong spec, issue #39): 9.000.000 ₫ chia chẵn theo từng tỷ lệ, không có phần dư
    shares = {c: 9_000_000 * int(j.split_percent) // 100 for c, j in demo_jars("minh").items()}
    assert sum(shares.values()) == 9_000_000
    assert {c: after[c] - before[c] for c in shares} == shares
    assert get(api, "minh", "/overview")["balance"]["other_income_vnd"] == 350_000
    assert get(api, "minh", "/salary-events")["salary_events"] == []
    status, body = flow(
        api,
        "minh",
        "confirm_salary",
        {"salary_event_id": fu["salary_event_id"], "decision": "split"},
    )
    assert (status, code(body)) == (409, "ALREADY_APPLIED")


def test_luong_lech_nhieu_hoi_cap_nhat_luong(api):
    status, receipt = flow(
        api,
        "lan",
        "record_transaction",
        {"kind": "income", "amount_vnd": 6_000_000, "tx_type": "salary"},
    )
    assert status == 200, receipt
    fu = receipt["data"]["follow_up"]
    assert fu["ask_update_salary"] is True and fu["deviation_percent"] == pytest.approx(33.33)
    status, _ = flow(
        api,
        "lan",
        "confirm_salary",
        {
            "salary_event_id": fu["salary_event_id"],
            "decision": "split",
            "update_declared_salary": True,
        },
    )
    assert status == 200
    assert get(api, "lan", "/profile")["profile"]["monthly_salary_vnd"] == 6_000_000


# --- gán hũ, nghĩa vụ, hũ, người nhận ---------------------------------------------------------------------------
def test_gan_khoan_chua_phan_loai_vao_hu_va_nho_luat(api):
    mine = get(api, "minh", "/transactions?jar=chua_phan_loai&limit=10")["transactions"]
    qr = next(t for t in mine if t["tx_type"] == "qr_other")
    before = jars(api, "minh")["di_lai"]
    status, receipt = flow(
        api,
        "minh",
        "assign_jar",
        {"transaction_id": qr["id"], "jar": "di_lai", "remember": "always"},
    )
    assert status == 200, receipt
    ov = get(api, "minh", "/overview")
    assert (
        ov["balance"]["unclassified_vnd"] == -180_000 - qr["amount_vnd"]
        and ov["needs_review_count"] == 1
    )
    assert jars(api, "minh")["di_lai"] == before + qr["amount_vnd"]


def test_khai_sua_xoa_nghia_vu_va_chuyen_tien_cho_nguoi_nhan(api):
    status, receipt = flow(
        api,
        "khoa",
        "update_profile",
        {
            "obligation": {
                "op": "upsert",
                "kind": "subscription",
                "name": "Spotify",
                "amount_vnd": 59_000,
                "due_day": 25,
                "pay_jar": "giai_tri",
            }
        },
    )
    assert status == 200, receipt
    obs = get(api, "khoa", "/obligations")
    (ob,) = [o for o in obs["obligations"] if o["name"] == "Spotify"]
    assert (
        ob["cycle"] == "monthly" and ob["pay_jar"] == "giai_tri" and obs["total_due_vnd"] >= 59_000
    )
    assert (
        flow(
            api,
            "khoa",
            "update_profile",
            {"obligation": {"op": "delete", "obligation_id": ob["id"]}},
        )[0]
        == 200
    )
    assert all(o["id"] != ob["id"] for o in get(api, "khoa", "/obligations")["obligations"])
    nam = next(p for p in get(api, "khoa", "/payees")["payees"] if p["name"] == "Đỗ Hoàng Nam")
    assert "account_hint" in nam and len(nam["account_hint"]) <= 40
    status, receipt = flow(
        api,
        "khoa",
        "record_transaction",
        {
            "kind": "expense",
            "amount_vnd": 100_000,
            "jar": "giai_tri",
            "tx_type": "transfer_person",
            "payee_id": nam["id"],
            "note": "Chia tiền",
        },
    )
    assert status == 200, receipt
    t = get(api, "khoa", "/transactions?limit=1")["transactions"][0]
    assert t["payee_name"] == "Đỗ Hoàng Nam" and t["note"] == "Chia tiền"


def test_save_jars_sua_ty_le_va_bao_ve_hu_con_tien(api):
    cur = get(api, "khoa", "/overview")["jars"]
    body = [
        {
            "code": j["code"],
            "name": j["name"],
            "color_key": j["color_key"],
            "icon_key": j["icon_key"],
            "kind": j["kind"],
            "split_percent": j["split_percent"],
        }
        for j in cur
    ]
    # hũ Ăn uống (không phải hũ đầu tiên: ví demo từ 26/11 mở đầu bằng Chi hằng ngày 3%)
    food = next(j for j in body if j["code"] == "an_uong")
    food_before = food["split_percent"]
    food["split_percent"] = food_before - 5
    body.append(
        {
            "name": "Học tiếng Anh",
            "color_key": "teal",
            "icon_key": "plane",
            "kind": "saving",
            "split_percent": 5,
            "goal_vnd": 3_000_000,
            "goal_date": "2027-06-01",
        }
    )
    assert flow(api, "khoa", "save_jars", {"jars": body})[0] == 200
    after = {j["code"]: j for j in get(api, "khoa", "/overview")["jars"]}
    assert (
        after["hoc_tieng_anh"]["goal_vnd"] == 3_000_000
        and after["an_uong"]["split_percent"] == food_before - 5
    )
    _status, err = flow(
        api,
        "khoa",
        "save_jars",
        {
            "jars": [
                *[j for j in body if j.get("code") not in ("du_phong", "an_uong")][:-1],
                {**food, "split_percent": food_before},
            ]
        },
    )
    assert code(err) in ("JAR_PROTECTED", "PARAMS_INVALID"), err
    food["split_percent"] = 90
    assert code(flow(api, "khoa", "save_jars", {"jars": body})[1]) == "PARAMS_INVALID"


# --- cô lập người dùng trên mọi endpoint mới -------------------------------------------------------------------
def test_a_khong_doc_khong_ghi_duoc_du_lieu_cua_b_tren_endpoint_moi(api):
    minh_tx = get(api, "minh", "/transactions?limit=1")["transactions"][0]["id"]
    minh_ob = get(api, "minh", "/obligations")["obligations"][0]["id"]
    minh_payee = get(api, "minh", "/payees")["payees"][0]["id"]
    assert minh_payee not in {p["id"] for p in get(api, "lan", "/payees")["payees"]}
    assert minh_ob not in {
        o["id"] for o in get(api, "lan", "/obligations?status=all")["obligations"]
    }
    assert minh_tx not in {
        t["id"] for t in get(api, "lan", "/transactions?limit=50")["transactions"]
    }
    assert api("lan", "GET", "/jars/muc_tieu")[0] == 404  # hũ goal Du lịch chỉ ví demo của Minh có
    before_minh = get(api, "minh", "/overview")["balance"]
    for tool, params, expected in (
        ("assign_jar", {"transaction_id": minh_tx, "jar": "an_uong"}, "TRANSACTION_NOT_FOUND"),
        (
            "record_transaction",
            {"kind": "expense", "amount_vnd": 1_000, "jar": "an_uong", "obligation_id": minh_ob},
            "OBLIGATION_NOT_FOUND",
        ),
        (
            "record_transaction",
            {"kind": "expense", "amount_vnd": 1_000, "jar": "an_uong", "payee_id": minh_payee},
            "PAYEE_NOT_FOUND",
        ),
        (
            "update_profile",
            {"obligation": {"op": "delete", "obligation_id": minh_ob}},
            "OBLIGATION_NOT_FOUND",
        ),
        (
            "confirm_salary",
            {"salary_event_id": str(uuid.uuid4()), "decision": "split"},
            "SALARY_EVENT_NOT_FOUND",
        ),
    ):
        _status, body = flow(api, "lan", tool, params)
        assert code(body) == expected, (tool, body)
    assert get(api, "minh", "/overview")["balance"] == before_minh


def test_token_cua_nguoi_khac_khong_dung_duoc_cho_tool_moi(api):
    p = {"kind": "expense", "amount_vnd": 5_000, "jar": "an_uong"}
    _, conf = api("lan", "POST", "/confirmations", {"tool": "record_transaction", "params": p})
    status, body = api(
        "minh",
        "POST",
        "/actions",
        {"tool": "record_transaction", "params": p, "confirm_token": conf["confirm_token"]},
    )
    assert (status, code(body)) == (403, "TOKEN_INVALID")
    # token của tool này không dùng được cho tool khác
    _, conf2 = api("minh", "POST", "/confirmations", {"tool": "record_transaction", "params": p})
    status, body = api(
        "minh",
        "POST",
        "/actions",
        {
            "tool": "assign_jar",
            "params": {"transaction_id": str(uuid.uuid4()), "jar": "an_uong"},
            "confirm_token": conf2["confirm_token"],
        },
    )
    assert code(body) in ("TOKEN_INVALID", "PARAMS_MISMATCH")


# --- đề nghị: hết hạn, hủy, đã thực hiện ------------------------------------------------------------------------
def _store_block(invoke, subs, who, conv, block):
    res = invoke(
        "save_turn",
        {
            "user_id": subs[who],
            "conversation_id": conv,
            "trace_id": uuid.uuid4().hex,
            "user_text": "x",
            "assistant_text": "y",
            "blocks": [{"seq": 0, "block": block}],
        },
    )
    assert res["status"] == "OK", res


def _offer(params, *, ttl_seconds):
    trace = uuid.uuid4().hex
    now = datetime.now(UTC)
    block = build_confirm_action(
        tool="record_transaction", params=params, summary="Chi 10.000 ₫", changes=[{"label": "Hũ", "after": "x"}], trace_id=trace,
        source_tool="ledger___record_transaction", as_of=now, app_date=now.date(), expires_at=now + timedelta(seconds=ttl_seconds),
    )  # fmt: skip
    return block_to_wire(block)


def _norm(api, who, params):
    status, conf = api(
        who, "POST", "/confirmations", {"tool": "record_transaction", "params": params}
    )
    assert status == 200, conf
    return conf["params"]


def test_de_nghi_het_han_bi_server_tu_choi_o_confirmations_va_actions(api, invoke, subs):
    params = _norm(api, "minh", {"kind": "expense", "amount_vnd": 10_000, "jar": "di_lai"})
    conv = f"it-conv-{uuid.uuid4().hex[:8]}"
    block = _offer(params, ttl_seconds=-30)  # đã quá hạn từ lúc dựng
    _store_block(invoke, subs, "minh", conv, block)
    ref = {"conversation_id": conv, "confirm_block_id": block["id"]}
    status, body = api(
        "minh", "POST", "/confirmations", {"tool": "record_transaction", "params": params, **ref}
    )
    assert (status, code(body)) == (410, "OFFER_EXPIRED") and "hết hạn" in body["error"]["message"]
    _, conf = api(
        "minh", "POST", "/confirmations", {"tool": "record_transaction", "params": params}
    )
    status, body = api(
        "minh",
        "POST",
        "/actions",
        {
            "tool": "record_transaction",
            "params": params,
            "confirm_token": conf["confirm_token"],
            **ref,
        },
    )
    assert (status, code(body)) == (410, "OFFER_EXPIRED")
    turn = get(api, "minh", f"/conversations/{conv}")["turns"][0]
    assert turn["resolutions"] == [{"block_id": block["id"], "status": "expired"}]


def test_bam_khong_luu_o_server_va_de_nghi_da_huy_khong_thuc_hien_duoc(
    api, invoke, subs, schema_validator
):
    params = _norm(api, "minh", {"kind": "expense", "amount_vnd": 10_000, "jar": "di_lai"})
    conv = f"it-conv-{uuid.uuid4().hex[:8]}"
    block = _offer(params, ttl_seconds=600)
    _store_block(invoke, subs, "minh", conv, block)
    ref = {"conversation_id": conv, "confirm_block_id": block["id"]}
    turn = get(api, "minh", f"/conversations/{conv}")["turns"][0]
    assert turn["resolutions"] == [{"block_id": block["id"], "status": "pending"}]
    status, out = api("minh", "POST", "/confirmations/cancel", ref)
    assert status == 200, out
    schema_validator.openapi("CancelConfirmationResponse", out)
    assert out["status"] == "cancelled"
    assert (
        api("minh", "POST", "/confirmations/cancel", ref)[1]["resolved_at"] == out["resolved_at"]
    )  # idempotent
    turn = get(api, "minh", f"/conversations/{conv}")["turns"][0]
    assert turn["resolutions"] == [
        {"block_id": block["id"], "status": "cancelled", "resolved_at": out["resolved_at"]}
    ]
    schema_validator.openapi("ConversationResponse", get(api, "minh", f"/conversations/{conv}"))
    before = jars(api, "minh")
    status, body = api(
        "minh", "POST", "/confirmations", {"tool": "record_transaction", "params": params, **ref}
    )
    assert (status, code(body)) == (409, "ALREADY_APPLIED") and "hủy" in body["error"]["message"]
    status, _ = flow(api, "minh", "record_transaction", params, **ref)
    assert status == 409
    assert jars(api, "minh") == before
    # người khác không hủy và không đọc được đề nghị của mình
    assert api("lan", "POST", "/confirmations/cancel", ref)[0] == 400
    assert get(api, "lan", f"/conversations/{conv}")["turns"] == []


def test_de_nghi_da_thuc_hien_phat_lai_receipt_va_khong_thuc_hien_lai(api, invoke, subs):
    params = _norm(api, "minh", {"kind": "expense", "amount_vnd": 10_000, "jar": "di_lai"})
    conv = f"it-conv-{uuid.uuid4().hex[:8]}"
    block = _offer(params, ttl_seconds=600)
    _store_block(invoke, subs, "minh", conv, block)
    ref = {"conversation_id": conv, "confirm_block_id": block["id"]}
    status, receipt = flow(api, "minh", "record_transaction", params, **ref)
    assert status == 200, receipt
    res = get(api, "minh", f"/conversations/{conv}")["turns"][0]["resolutions"][0]
    assert res["status"] == "done" and res["receipt"] == receipt
    before = jars(api, "minh")
    assert flow(api, "minh", "record_transaction", params, **ref)[0] == 409
    assert (
        api("minh", "POST", "/confirmations/cancel", ref)[0] == 409
    )  # đã thực hiện thì không hủy được
    assert jars(api, "minh") == before


# --- tiêu chí 7: onboarding tài khoản trắng ----------------------------------------------------------------------
def test_onboarding_tai_khoan_trang_chi_voi_luong_va_ngay_nhan(
    base, blank_account, schema_validator
):
    from _demo_auth import call_api

    token, _sub = blank_account
    call = lambda m, p, b=None: call_api(base, m, p, token, b)[:2]  # noqa: E731
    status, ov = call("GET", "/overview")
    assert status == 200, ov
    schema_validator.openapi("OverviewResponse", ov)
    assert (
        ov["profile"]["onboarded"] is False
        and ov["jars"] == []
        and ov["next_payday"] is None
        and ov["proactive_card"] is None
    )
    assert "@" not in ov["profile"]["display_name"]  # không bao giờ dùng email làm tên
    # thiếu ngày nhận thì chưa đủ
    status, err = call(
        "POST",
        "/confirmations",
        {"tool": "update_profile", "params": {"monthly_salary_vnd": 12_000_000}},
    )
    assert (status, code(err)) == (422, "PROFILE_INCOMPLETE")
    params = {"monthly_salary_vnd": 12_000_000, "payday_day": 15}
    status, conf = call("POST", "/confirmations", {"tool": "update_profile", "params": params})
    assert status == 200, conf
    status, receipt = call(
        "POST",
        "/actions",
        {
            "tool": "update_profile",
            "params": conf["params"],
            "confirm_token": conf["confirm_token"],
        },
    )
    assert status == 200 and receipt["data"]["summary"].startswith("Đã tạo hồ sơ"), receipt
    status, ov = call("GET", "/overview")
    schema_validator.openapi("OverviewResponse", ov)
    assert ov["profile"]["onboarded"] and ov["profile"]["monthly_salary_vnd"] == 12_000_000
    # tài khoản mới nhận bộ hũ onboarding (rollout Q1: ba hũ mặc định của danh mục), không phải bảy hũ cũ
    templates = call("GET", "/jar-templates")[1]["templates"]
    defaults = {t["code"] for t in templates if t["is_default"]}
    assert len(ov["jars"]) == len(defaults) and round(sum(j["split_percent"] for j in ov["jars"]), 2) == 100
    assert [j["code"] for j in ov["system_jars"]] == ["tien_vao_khac", "chua_phan_loai"]
    assert ov["next_payday"]["date"].endswith("-15") and ov["balance"]["total_vnd"] == 0
    assert ov["credit_line"]["status"] == "active"
    assert {j["code"] for j in ov["jars"]} == defaults
    # đã onboard thì ghi được tiền vào ngay
    status, rec = call(
        "POST",
        "/confirmations",
        {
            "tool": "record_transaction",
            "params": {"kind": "income", "amount_vnd": 100_000, "tx_type": "friend_repay"},
        },
    )
    assert status == 200, rec


# --- sự kiện thật lên bus ---------------------------------------------------------------------------------------
def test_su_kien_that_su_len_yofina_bus(api, event_sink, schema_validator):
    import json

    status, receipt = flow(
        api, "lan", "record_transaction",
        {"kind": "expense", "amount_vnd": 15_000, "jar": "di_lai", "tx_type": "public_transport", "counterparty": "Xe buýt"},
    )  # fmt: skip
    assert status == 200, receipt
    status, rec2 = flow(
        api,
        "lan",
        "record_transaction",
        {
            "kind": "expense",
            "amount_vnd": 100_000,
            "jar": "giai_tri",
            "funding": "credit",
            "tx_type": "entertainment",
        },
    )
    assert status == 200, rec2
    got = event_sink(3)
    assert len(got) == 3, [(e["detail-type"], e["detail"].get("event_id")) for e in got]
    by_type = {}
    for e in got:
        by_type.setdefault(e["detail-type"], []).append(e)
        assert e["source"] == "yofina.ledger"
    assert (
        sorted(by_type) == ["obligation.changed", "transaction.recorded"]
        and len(by_type["transaction.recorded"]) == 2
    )
    for e in got:
        schema_validator(
            f"https://contracts.yofina.invalid/events/{e['detail-type']}.schema.json", e["detail"]
        )
        assert "@" not in json.dumps(e["detail"])
    debit = next(
        e["detail"]
        for e in by_type["transaction.recorded"]
        if e["detail"]["funding_source"] == "jar"
    )
    assert debit["event_id"] == debit["transaction_id"] == receipt["data"]["reference_id"]
    assert debit["effects"][0]["delta_vnd"] == -15_000 and debit["jar_codes"] == ["di_lai"]
    credit = next(
        e["detail"]
        for e in by_type["transaction.recorded"]
        if e["detail"]["funding_source"] == "credit"
    )
    assert credit["effects"] == [] and credit["jar_codes"] == ["giai_tri"]
    assert by_type["obligation.changed"][0]["detail"]["kind"] == "bnpl"


def test_gui_trung_mot_su_kien_cung_event_id_khi_gui_lai_cung_mot_lan_ghi():
    """event_id của transaction.recorded bằng id dòng sổ cái: gửi lại cùng một lần ghi cho cùng event_id (consumer dedupe)."""
    from yofina_ledger import events

    now = datetime.now(UTC)
    a = events.transaction_recorded(
        user_id="u",
        trace_id=None,
        transaction_id=str(uuid.uuid4()),
        occurred_at=now,
        app_date=now.date(),
        kind="expense",
        tx_type="x",
        funding_source="jar",
        amount_vnd=1,
        jar_codes=["a"],
        deltas={"a": -1},
        balances={"a": 0},
    )
    b = events.transaction_recorded(
        user_id="u",
        trace_id=None,
        transaction_id=a.detail["transaction_id"],
        occurred_at=now,
        app_date=now.date(),
        kind="expense",
        tx_type="x",
        funding_source="jar",
        amount_vnd=1,
        jar_codes=["a"],
        deltas={"a": -1},
        balances={"a": 0},
    )
    assert a.detail["event_id"] == b.detail["event_id"]


def test_lich_su_chi_tieu_theo_ngay_cua_minh_du_day_cho_du_bao(api):
    """Lịch sử chi của hũ Ăn uống trải trên nhiều ngày (đọc hết các trang): đủ dày để mô hình dự báo dùng được."""
    days: set[str] = set()
    path = "/transactions?kind=expense&jar=an_uong&limit=50"
    for _ in range(6):
        page = get(api, "minh", path)
        days |= {t["app_date"] for t in page["transactions"]}
        if "next_cursor" not in page:
            break
        path = f"/transactions?kind=expense&jar=an_uong&limit=50&cursor={page['next_cursor']}"
    assert len(days) >= 28


# --- gợi ý do server tính cho giao diện ---------------------------------------------------------------------------
def test_confirmations_tra_them_xem_truoc_do_server_tinh_gom_phi_tra_sau(api, schema_validator):
    fee = next(
        f
        for f in get(api, "khoa", "/credit-line")["fees"]
        if f["fee_type"] == "monthly_service_fee"
    )["amount_vnd"]
    before = jars(api, "khoa")
    status, conf = api(
        "khoa",
        "POST",
        "/confirmations",
        {
            "tool": "record_transaction",
            "params": {
                "kind": "expense",
                "amount_vnd": 250_000,
                "jar": "giai_tri",
                "funding": "credit",
            },
        },
    )
    assert status == 200, conf
    schema_validator.openapi("ConfirmationResponse", conf)
    pv = conf["preview"]
    labels = {c["label"]: c for c in pv["changes"]}
    due = next(k for k in labels if k.startswith("Phải trả ngày"))
    assert due.endswith("/12") or due.endswith("/01") or due.endswith("/11") or due.endswith("/02")
    assert (
        labels[due]["before"] == "chưa có"
        and labels[due]["after"] == f"{250_000 + fee:,}".replace(",", ".") + " ₫"
    )
    assert "Hạn mức còn lại" in labels and pv["summary"].startswith(
        "Mua 250.000 ₫ bằng Trả sau (mô phỏng)"
    )
    assert jars(api, "khoa") == before  # xem trước không ghi gì
    status, conf = api(
        "khoa",
        "POST",
        "/confirmations",
        {
            "tool": "move_between_jars",
            "params": {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 10_000},
        },
    )
    assert status == 200 and [c["label"] for c in conf["preview"]["changes"]] == [
        "Hũ Giải trí",
        "Hũ Ăn uống",
    ]


def test_tx_types_co_co_person_transfer_va_mat_du_bao_vang_khi_chua_co_du_bao(
    api, schema_validator
):
    types = get(api, "minh", "/tx-types")["tx_types"]
    assert [t["tx_type"] for t in types if t["is_person_transfer"]] == ["transfer_person"]
    ov = get(api, "minh", "/overview")
    for j in ov["jars"]:
        assert "forecast_floor_vnd" not in j or isinstance(j["forecast_floor_vnd"], int)
    schema_validator.openapi("OverviewResponse", ov)
