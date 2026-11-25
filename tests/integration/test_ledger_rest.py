"""REST thật: HTTP API + JWT Cognito + Lambda ledger + Aurora + DynamoDB (phase 1, tiêu chí 2-5)."""

from __future__ import annotations

import threading
import time
import urllib.request

import pytest
from _yofina import ssm_param
from conftest import demo_balances, demo_jars, token_payload

from yofina_core.blocks import parse_block
from yofina_core.confirm import issue_token, params_hash

TOOL = "move_between_jars"
MOVE = {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100_000}

# Ví demo của minh sau đặt lại (bộ hũ demo, issue #39), suy từ bộ sinh persona qua cùng ánh xạ mã hũ: Hóa đơn gộp vào Nghĩa vụ,
# Du lịch là hũ goal `muc_tieu`, thêm Đầu tư 0 ₫; tổng vẫn 7.730.000 ₫ của bảng số Figma §5
MINH_BALANCES = demo_balances("minh")

pytestmark = pytest.mark.usefixtures("fresh")


def balances(api, who):
    status, body = api(who, "GET", "/jars")
    assert status == 200, body
    return {j["code"]: j["balance_vnd"] for j in body["jars"]}, body


def confirm(api, who, params=MOVE, **extra):
    return api(who, "POST", "/confirmations", {"tool": TOOL, "params": params, **extra})


def act(api, who, token, params=MOVE, **kw):
    body = {"tool": TOOL, "params": params}
    if token is not None:
        body["confirm_token"] = token
    return api(who, "POST", "/actions", body, **kw)


def error_code(body) -> str:
    return body["error"]["code"]


# --- xác thực -------------------------------------------------------------------------------
@pytest.mark.parametrize("tok", [None, "", "abc.def.ghi", "khong-phai-jwt"])
def test_khong_token_hoac_token_gia_bi_authorizer_chan_401(api, tok):
    status, _ = api(None, "GET", "/jars", token=tok)
    assert status == 401


def _preflight(base, origin):
    req = urllib.request.Request(
        base + "/jars",
        method="OPTIONS",
        headers={
            "origin": origin,
            "access-control-request-method": "GET",
            "access-control-request-headers": "authorization,traceparent",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return {k.lower(): v for k, v in r.getheaders()}
    except Exception:
        return {}


def test_cors_preflight_cho_origin_amplify_va_localhost_va_chan_origin_la(base, sess):
    for origin in (ssm_param("frontend/amplify-url", sess=sess), "http://localhost:5173"):
        h = _preflight(base, origin)
        assert h.get("access-control-allow-origin") == origin
        assert "authorization" in h["access-control-allow-headers"].lower()
    assert not _preflight(base, "https://ke-tan-cong.example").get("access-control-allow-origin")


# --- đọc ------------------------------------------------------------------------------------
def test_get_jars_minh_khop_bang_so_figma(api, schema_validator):
    bal, body = balances(api, "minh")
    schema_validator.openapi("JarsResponse", body)
    assert bal == MINH_BALANCES
    assert body["jars_total_vnd"] == 7_730_000
    assert [j["code"] for j in body["jars"]] == list(MINH_BALANCES)
    assert body["app_date"] >= "2026-11-21"  # ngày neo, rồi trôi theo ngày thật (ADR-0003)


def test_lan_thay_du_lieu_cua_lan(api):
    bal, body = balances(api, "lan")
    assert set(bal) == set(demo_jars("lan"))  # ví demo của lan: không có Hóa đơn (gộp vào Nghĩa vụ), có Đầu tư
    assert bal["an_uong"] == 520_000 and body["jars_total_vnd"] == sum(bal.values())


# --- luồng đủ -------------------------------------------------------------------------------
def test_chuyen_hu_du_luong_confirmations_roi_actions(api, schema_validator, sess):
    before, _ = balances(api, "minh")
    status, conf = confirm(api, "minh")
    assert status == 200, conf
    schema_validator.openapi("ConfirmationResponse", conf)
    assert conf["params"] == MOVE and conf["ttl_seconds"] <= 120
    assert conf["params_hash"] == params_hash(TOOL, MOVE)
    assert balances(api, "minh")[0] == before  # cấp token chưa làm đổi gì

    status, receipt = act(api, "minh", conf["confirm_token"])
    assert status == 200, receipt
    assert parse_block(receipt).type == "receipt"
    assert receipt["data"]["amount_vnd"] == 100_000
    assert receipt["data"]["from_jar"] == {
        "code": "giai_tri",
        "name": "Giải trí",
        "balance_after_vnd": before["giai_tri"] - 100_000,
    }
    after, _ = balances(api, "minh")
    assert after["giai_tri"] == before["giai_tri"] - 100_000
    assert after["an_uong"] == before["an_uong"] + 100_000
    assert sum(after.values()) == sum(before.values())  # bảo toàn tiền

    # jti đã nằm trong DynamoDB kèm TTL ở tương lai
    jti = token_payload(conf["confirm_token"])["jti"]
    item = sess.client("dynamodb").get_item(
        TableName=ssm_param("dynamodb/confirm-jti-table", sess=sess), Key={"jti": {"S": jti}}
    )["Item"]
    assert int(item["ttl"]["N"]) > time.time()


def test_so_cai_co_hai_dong_cung_transfer_id(api, invoke, subs):
    small = {**MOVE, "amount_vnd": 5_000}
    _, conf = confirm(api, "minh", small)
    status, receipt = act(api, "minh", conf["confirm_token"], small)
    assert status == 200
    res = invoke("query_transactions", {"user_id": subs["minh"], "limit": 2})
    txs = res["data"]["transactions"]
    assert len(txs) == 2
    assert {t["transfer_id"] for t in txs} == {receipt["data"]["transaction_id"]}
    assert sorted(t["amount_vnd"] for t in txs) == [-5_000, 5_000]
    assert {t["jar"] for t in txs} == {"giai_tri", "an_uong"}


def test_khong_bam_thi_khong_gi_doi_khi_chi_xin_xem_truoc(api):
    before, _ = balances(api, "minh")
    status, body = act(api, "minh", None)
    assert status == 428 and error_code(body) == "NEEDS_CONFIRMATION"
    assert balances(api, "minh")[0] == before


# --- tấn công token -----------------------------------------------------------------------------
def test_replay_cung_token_bi_tu_choi_409_va_chi_ghi_mot_lan(api):
    before, _ = balances(api, "minh")
    _, conf = confirm(api, "minh")
    assert act(api, "minh", conf["confirm_token"])[0] == 200
    status, body = act(api, "minh", conf["confirm_token"])
    assert (status, error_code(body)) == (409, "TOKEN_REUSED")
    assert balances(api, "minh")[0]["giai_tri"] == before["giai_tri"] - 100_000


def test_token_doi_tham_so_bi_tu_choi_va_khong_mat_token(api):
    before, _ = balances(api, "minh")
    _, conf = confirm(api, "minh")
    for tampered in ({**MOVE, "amount_vnd": 700_000}, {**MOVE, "to_jar": "di_lai"}):
        status, body = act(api, "minh", conf["confirm_token"], tampered)
        assert (status, error_code(body)) == (409, "PARAMS_MISMATCH")
    assert balances(api, "minh")[0] == before
    assert act(api, "minh", conf["confirm_token"])[0] == 200  # token vẫn dùng được đúng tham số


def test_token_cua_nguoi_khac_bi_tu_choi_403(api):
    before_minh, _ = balances(api, "minh")
    _, conf_lan = confirm(api, "lan")
    status, body = act(api, "minh", conf_lan["confirm_token"])
    assert (status, error_code(body)) == (403, "TOKEN_INVALID")
    assert balances(api, "minh")[0] == before_minh
    # và ngược lại: token của minh không dùng được cho lan
    _, conf_minh = confirm(api, "minh")
    status, body = act(api, "lan", conf_minh["confirm_token"])
    assert (status, error_code(body)) == (403, "TOKEN_INVALID")


def test_token_het_han_bi_tu_choi_403(api, subs, hmac_key):
    # token ký đúng khóa thật nhưng hạn đã qua: chỉ lệch ở thời gian
    tok, _ = issue_token(
        hmac_key,
        sub=subs["minh"],
        tool=TOOL,
        params_hash=params_hash(TOOL, MOVE),
        now_epoch=time.time() - 600,
        ttl_seconds=120,
    )
    before, _ = balances(api, "minh")
    status, body = act(api, "minh", tok)
    assert (status, error_code(body)) == (403, "TOKEN_EXPIRED")
    assert balances(api, "minh")[0] == before


def test_token_ky_sai_khoa_va_token_bia_bi_tu_choi(api, subs):
    forged, _ = issue_token(
        b"khong-phai-khoa-that",
        sub=subs["minh"],
        tool=TOOL,
        params_hash=params_hash(TOOL, MOVE),
        now_epoch=time.time(),
        ttl_seconds=100,
    )
    for tok in (forged, "abc.def", "x" * 40 + "." + "y" * 40):
        status, body = act(api, "minh", tok)
        assert (status, error_code(body)) == (403, "TOKEN_INVALID")


def test_ttl_vuot_tran_bi_tu_choi_du_ky_dung_khoa(api, subs, hmac_key):
    tok, _ = issue_token(
        hmac_key,
        sub=subs["minh"],
        tool=TOOL,
        params_hash=params_hash(TOOL, MOVE),
        now_epoch=time.time(),
        ttl_seconds=3600,
    )
    status, body = act(api, "minh", tok)
    assert (status, error_code(body)) == (403, "TOKEN_INVALID")


def test_dua_hai_request_cung_jti_chi_mot_thanh_cong(api):
    before, _ = balances(api, "minh")
    _, conf = confirm(api, "minh")
    results: list[tuple[int, dict]] = []
    barrier = threading.Barrier(2)

    def fire():
        barrier.wait()
        results.append(act(api, "minh", conf["confirm_token"]))

    threads = [threading.Thread(target=fire) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    statuses = sorted(s for s, _ in results)
    assert statuses == [200, 409], results
    loser = next(b for s, b in results if s == 409)
    assert error_code(loser) == "TOKEN_REUSED"
    assert balances(api, "minh")[0]["giai_tri"] == before["giai_tri"] - 100_000  # chỉ trừ một lần


# --- lỗi nghiệp vụ ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("params", "status", "code"),
    [
        ({**MOVE, "amount_vnd": 760_001}, 422, "INSUFFICIENT_FUNDS"),
        ({**MOVE, "to_jar": "khong_co_hu_nay"}, 404, "JAR_NOT_FOUND"),
        ({**MOVE, "to_jar": "giai_tri"}, 400, "PARAMS_INVALID"),
        ({**MOVE, "amount_vnd": 0}, 400, "PARAMS_INVALID"),
        ({**MOVE, "amount_vnd": 100_000_000}, 422, "AMOUNT_LIMIT_EXCEEDED"),
    ],
)
def test_loi_nghiep_vu_khi_xin_token(api, schema_validator, params, status, code):
    s, body = confirm(api, "minh", params)
    assert (s, error_code(body)) == (status, code)
    schema_validator.openapi("ErrorResponse", body)


# --- cô lập người dùng --------------------------------------------------------------------------
def test_lan_khong_doc_duoc_du_lieu_minh_du_gui_user_id_cua_minh(api, subs):
    status, body = api("lan", "GET", "/jars?user_id=" + subs["minh"])
    assert status == 200 and "an_uong" in {j["code"] for j in body["jars"]}
    assert len(body["jars"]) == len(demo_jars("lan")) != len(demo_jars("minh"))  # của lan, không phải của minh


def test_lan_khong_ghi_duoc_vao_du_lieu_minh_du_gui_user_id_cua_minh(api, subs):
    minh_before, _ = balances(api, "minh")
    lan_before, _ = balances(api, "lan")
    body = {"tool": TOOL, "params": {**MOVE, "user_id": subs["minh"]}, "user_id": subs["minh"]}
    status, conf = api("lan", "POST", "/confirmations", body)
    assert status == 200, conf
    assert token_payload(conf["confirm_token"])["sub"] == subs["lan"]  # server ghim sub từ JWT
    status, receipt = api(
        "lan", "POST", "/actions", {**body, "confirm_token": conf["confirm_token"]}
    )
    assert status == 200, receipt
    assert balances(api, "minh")[0] == minh_before  # dữ liệu minh nguyên vẹn
    lan_after, _ = balances(api, "lan")
    assert lan_after["giai_tri"] == lan_before["giai_tri"] - 100_000


# --- đặt lại ------------------------------------------------------------------------------------
def test_dat_lai_dua_ve_dung_so_ban_dau(api, schema_validator):
    lan_before, _ = balances(api, "lan")
    _, conf = confirm(api, "minh")
    assert act(api, "minh", conf["confirm_token"])[0] == 200
    assert balances(api, "minh")[0] != MINH_BALANCES
    status, body = api("minh", "POST", "/demo/reset", timeout=60)
    assert status == 200, body
    schema_validator.openapi("ResetResponse", body)
    assert body["jars_count"] == len(MINH_BALANCES) and body["transactions_count"] >= 100
    assert balances(api, "minh")[0] == MINH_BALANCES
    # đồng hồ mô phỏng về ngày neo: ngày mô phỏng = 2026-11-21 ngay sau khi đặt lại
    assert body["app_date"] == "2026-11-21"
    # đặt lại minh không đụng lan
    assert balances(api, "lan")[0] == lan_before


def test_dat_lai_xoa_so_cai_cu_va_sinh_lai(api, invoke, subs):
    _, conf = confirm(api, "minh", {**MOVE, "amount_vnd": 7_000})
    act(api, "minh", conf["confirm_token"], {**MOVE, "amount_vnd": 7_000})
    api("minh", "POST", "/demo/reset", timeout=60)
    res = invoke("query_transactions", {"user_id": subs["minh"], "limit": 50})
    assert all(t["kind"] != "transfer" for t in res["data"]["transactions"])
