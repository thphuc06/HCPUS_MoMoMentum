"""Đường HTTP API (payload v2) của ledger: danh tính chỉ từ claim `sub`, mã lỗi và HTTP status
đúng OpenAPI, luồng confirmations -> actions, đặt lại demo. Dùng kho dữ liệu giả."""

from __future__ import annotations

import json

import pytest
from conftest import OPENAPI_URI
from handler import is_http_event
from jsonschema import Draft202012Validator
from ledger_fakes import http_event, make_service

from yofina_core.blocks import parse_block
from yofina_core.errors import HTTP_STATUS, ErrorCode
from yofina_ledger.rest_api import handle_http

MINH, LAN = "sub-minh", "sub-lan"
MOVE = {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100_000}


@pytest.fixture
def schema_ok(registry):
    def run(name: str, instance):
        v = Draft202012Validator(
            {"$ref": f"{OPENAPI_URI}#/components/schemas/{name}"}, registry=registry
        )
        errors = [f"{list(e.path)}: {e.message}" for e in v.iter_errors(instance)]
        assert not errors, errors

    return run


def req(svc, method, path, **kw):
    res = handle_http(http_event(method, path, **kw), svc)
    return res["statusCode"], json.loads(res["body"]), res


def confirm_then_act(svc, sub=MINH, params=MOVE):
    status, body, _ = req(
        svc, "POST", "/confirmations", sub=sub, body={"tool": "move_between_jars", "params": params}
    )
    assert status == 200, body
    return body


def test_nhan_dien_su_kien_http():
    assert is_http_event(http_event("GET", "/jars", sub="x"))
    assert not is_http_event({"user_id": "x"})


# --- GET /jars ------------------------------------------------------------------------------
def test_get_jars_dung_hop_dong(schema_ok):
    svc, _, _ = make_service()
    status, body, res = req(svc, "GET", "/jars", sub=MINH)
    assert status == 200
    schema_ok("JarsResponse", body)
    assert body["app_date"] == "2026-11-21" and body["jars_total_vnd"] == 1_780_000
    assert res["headers"]["content-type"].startswith("application/json")


def test_thieu_claim_sub(schema_ok):
    svc, _, _ = make_service()
    status, body, _ = req(svc, "GET", "/jars", sub=None)
    assert status == 401
    schema_ok("ErrorResponse", body)
    assert body["error"]["code"] == "UNAUTHENTICATED"


def test_sub_chi_tu_claim_khong_tu_than_yeu_cau_hay_query():
    svc, repo, _ = make_service()
    repo.users[LAN]["jars"]["an_uong"]["balance_vnd"] = 5
    ev = http_event("GET", "/jars", sub=LAN)
    ev["queryStringParameters"] = {"user_id": MINH}
    ev["body"] = json.dumps({"user_id": MINH, "sub": MINH})
    res = handle_http(ev, svc)
    jars = json.loads(res["body"])["jars"]
    assert jars[0]["balance_vnd"] == 5  # dữ liệu của lan, không phải của minh


def test_duong_dan_la_va_traceparent(schema_ok):
    svc, _, _ = make_service()
    tp = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    status, body, _ = req(svc, "GET", "/khong-co", sub=MINH, headers={"traceparent": tp})
    assert status == 400
    assert body["error"]["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    schema_ok("ErrorResponse", body)


# --- POST /confirmations và POST /actions -----------------------------------------------------
def test_luong_day_du_confirmations_roi_actions(schema_ok):
    svc, repo, _ = make_service()
    conf = confirm_then_act(svc)
    schema_ok("ConfirmationResponse", conf)
    assert conf["ttl_seconds"] == 120 and conf["params"] == MOVE
    status, receipt, _ = req(
        svc,
        "POST",
        "/actions",
        sub=MINH,
        body={"tool": "move_between_jars", "params": MOVE, "confirm_token": conf["confirm_token"]},
    )
    assert status == 200
    block = parse_block(receipt)
    assert block.type == "receipt" and receipt["source"]["tool"] == "rest:POST /actions"
    assert receipt["data"]["from_jar"]["balance_after_vnd"] == 660_000
    assert repo.users[MINH]["jars"]["an_uong"]["balance_vnd"] == 480_000


def test_actions_khong_token_428_va_khong_ghi(schema_ok):
    svc, repo, _ = make_service()
    status, body, _ = req(
        svc, "POST", "/actions", sub=MINH, body={"tool": "move_between_jars", "params": MOVE}
    )
    assert status == 428 and body["error"]["code"] == "NEEDS_CONFIRMATION"
    schema_ok("ErrorResponse", body)
    assert not repo.moves


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        ("replay", "TOKEN_REUSED"),
        ("amount", "PARAMS_MISMATCH"),
        ("other_user", "TOKEN_INVALID"),
        ("garbage", "TOKEN_INVALID"),
        ("expired", "TOKEN_EXPIRED"),
    ],
)
def test_token_xau_bi_tu_choi_dung_ma_va_dung_http_status(schema_ok, mutate, code):
    svc, repo, clock = make_service()
    conf = confirm_then_act(svc)
    token, params, sub = conf["confirm_token"], dict(MOVE), MINH
    if mutate == "replay":
        req(
            svc,
            "POST",
            "/actions",
            sub=MINH,
            body={"tool": "move_between_jars", "params": MOVE, "confirm_token": token},
        )
    elif mutate == "amount":
        params["amount_vnd"] = 700_000
    elif mutate == "other_user":
        sub = LAN
    elif mutate == "garbage":
        token = "abc.def"
    elif mutate == "expired":
        clock.advance(500)
    n_before = len(repo.moves)
    status, body, _ = req(
        svc,
        "POST",
        "/actions",
        sub=sub,
        body={"tool": "move_between_jars", "params": params, "confirm_token": token},
    )
    assert body["error"]["code"] == code
    assert status == HTTP_STATUS[ErrorCode(code)]
    schema_ok("ErrorResponse", body)
    assert len(repo.moves) == n_before


def test_lan_khong_ghi_duoc_vao_du_lieu_minh_du_gui_user_id_cua_minh():
    svc, repo, _ = make_service()
    conf = confirm_then_act(svc, sub=LAN)
    body = {
        "tool": "move_between_jars",
        "params": {**MOVE, "user_id": MINH},
        "confirm_token": conf["confirm_token"],
        "user_id": MINH,
    }
    status, _, _ = req(svc, "POST", "/actions", sub=LAN, body=body)
    assert status == 200
    assert repo.users[MINH]["jars"]["giai_tri"]["balance_vnd"] == 760_000  # của minh không đổi
    assert repo.users[LAN]["jars"]["giai_tri"]["balance_vnd"] == 660_000


def test_confirmations_hash_khach_lech_la_params_mismatch():
    svc, _, _ = make_service()
    status, body, _ = req(
        svc,
        "POST",
        "/confirmations",
        sub=MINH,
        body={"tool": "move_between_jars", "params": MOVE, "params_hash": "1" * 64},
    )
    assert status == 409 and body["error"]["code"] == "PARAMS_MISMATCH"


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"tool": "move_between_jars"},
        {"tool": "x", "params": MOVE},
        {"tool": "move_between_jars", "params": []},
    ],
)
def test_than_yeu_cau_sai_la_400(body):
    svc, _, _ = make_service()
    status, resp, _ = req(svc, "POST", "/actions", sub=MINH, body=body)
    assert status == 400 and resp["error"]["code"] == "PARAMS_INVALID"


@pytest.mark.parametrize("route", ["/confirmations", "/actions"])
def test_ledger_khong_nhan_confirm_rows(route):
    """confirm_rows (phase 5) chỉ đi qua /ingest/confirmations và /ingest/actions của Lambda ingest."""
    svc, _, _ = make_service()
    body = {"tool": "confirm_rows", "params": {"job_id": "11111111-1111-4111-8111-111111111111"}}
    status, resp, _ = req(svc, "POST", route, sub=MINH, body=body)
    assert status == 400 and resp["error"]["code"] == "PARAMS_INVALID"


def test_json_hong_la_400():
    svc, _, _ = make_service()
    ev = http_event("POST", "/actions", sub=MINH)
    ev["body"] = "{khong phai json"
    res = handle_http(ev, svc)
    assert res["statusCode"] == 400


def test_loi_nghiep_vu_ma_http_status():
    svc, _, _ = make_service()
    for params, status in (
        ({**MOVE, "amount_vnd": 5_000_000}, 422),
        ({**MOVE, "to_jar": "khong_co"}, 404),
    ):
        s, body, _ = req(
            svc,
            "POST",
            "/confirmations",
            sub=MINH,
            body={"tool": "move_between_jars", "params": params},
        )
        assert s == status, body


# --- POST /demo/reset ------------------------------------------------------------------------
def test_reset_can_nhom_persona(schema_ok):
    svc, repo, _ = make_service()
    status, body, _ = req(svc, "POST", "/demo/reset", sub=MINH)
    assert status == 403 and body["error"]["code"] == "FORBIDDEN"
    assert not repo.resets


@pytest.mark.parametrize("groups", ["[persona-minh ops]", "persona-minh", "[ops persona-minh]"])
def test_reset_sinh_lai_persona_dat_dong_ho_ve_ngay_neo(schema_ok, groups):
    svc, repo, _ = make_service(users=())
    status, body, _ = req(svc, "POST", "/demo/reset", sub="sub-moi", groups=groups)
    assert status == 200, body
    schema_ok("ResetResponse", body)
    assert body["app_date"] == "2026-11-21" and body["clock_offset_days"] == -19
    (reset,) = repo.resets
    assert reset["uid"] == "sub-moi" and reset["profile"]["salary"] == 9_000_000
    assert len(reset["jars"]) == 4 and body["jars_count"] == 4
    assert {j["code"]: j["purpose"] for j in reset["jars"]} == {
        "chi_hang_ngay": None,
        "nghia_vu": None,
        "du_phong": "buffer",
        "muc_tieu": "goal",
    }
    assert body["transactions_count"] == len(reset["transactions"]) > 100
    assert (
        body["obligations_count"] == len(reset["obligations"]) == 7
        and body["forecast_ready"] is False
    )
    # số dư dựng từ sổ cái (bản thật làm bằng SQL; bản giả cộng các dòng trả bằng hũ)
    jars = repo.users["sub-moi"]["jars"]
    assert (
        jars["chi_hang_ngay"]["balance_vnd"] == 1_080_000 and jars["du_phong"]["balance_vnd"] == 2_700_000
    )
    assert reset["credit_line"]["lim"] == 5_000_000 and len(reset["payees"]) == 4


def test_reset_chi_xoa_du_lieu_cua_chinh_nguoi_goi():
    svc, repo, _ = make_service(users=(MINH, LAN))
    lan_before = dict(repo.users[LAN]["jars"]["an_uong"])
    req(svc, "POST", "/demo/reset", sub=MINH, groups="[persona-minh]")
    assert repo.resets[0]["uid"] == MINH
    assert repo.users[LAN]["jars"]["an_uong"] == lan_before


def test_reset_nhom_la_khong_duoc():
    svc, _, _ = make_service()
    status, _, _ = req(svc, "POST", "/demo/reset", sub=MINH, groups="[persona-khong-co ops]")
    assert status == 403
