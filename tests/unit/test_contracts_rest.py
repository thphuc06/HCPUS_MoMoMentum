"""Hợp đồng REST (OpenAPI 3.1)."""

from __future__ import annotations

import pytest
import yaml
from conftest import CONTRACTS, OPENAPI_URI, load_json
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate

from yofina_core.errors import HTTP_STATUS, ErrorCode

SPEC_PATH = CONTRACTS / "rest" / "openapi.yaml"
SPEC = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
HASH = "52a35d69448e3621190f43bbc8fa12356d2cfdd9895fac320e0557dfa779a962"
PARAMS = {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100000}
TOKEN = "eyJzdWIiOiJ4In0.c2ln"


def test_openapi_31_hop_le_ke_ca_tham_chieu_ngoai():
    assert SPEC["openapi"].startswith("3.1")
    validate(SPEC, base_uri=SPEC_PATH.as_uri())


def test_cac_endpoint_cua_phase_1_va_bearer_jwt():
    ops = {(m.upper(), p) for p, item in SPEC["paths"].items() for m in item if m != "parameters"}
    assert ops == {
        ("GET", "/jars"),
        ("POST", "/confirmations"),
        ("POST", "/actions"),
        ("POST", "/demo/reset"),
        ("GET", "/conversations"),
        ("GET", "/conversations/{conversation_id}"),
    }
    assert SPEC["security"] == [{"bearerAuth": []}]
    scheme = SPEC["components"]["securitySchemes"]["bearerAuth"]
    assert (scheme["type"], scheme["scheme"], scheme["bearerFormat"]) == ("http", "bearer", "JWT")


def test_ma_loi_khop_yofina_core_errors():
    schema = SPEC["components"]["schemas"]["ErrorCode"]
    assert schema["enum"] == [c.value for c in ErrorCode]
    assert schema["x-http-status"] == {c.value: s for c, s in HTTP_STATUS.items()}
    assert set(schema["x-meaning"]) == set(schema["enum"])
    required = {
        "NEEDS_CONFIRMATION",
        "TOKEN_INVALID",
        "TOKEN_EXPIRED",
        "TOKEN_REUSED",
        "PARAMS_MISMATCH",
    }
    assert required <= set(schema["enum"])


def test_moi_ma_http_loi_trong_operation_co_trong_bang_anh_xa():
    statuses = set(HTTP_STATUS.values())
    for path, item in SPEC["paths"].items():
        for method, op in item.items():
            for code in op["responses"]:
                if code != "200":
                    assert int(code) in statuses, (method, path, code)


def test_actions_tra_receipt_va_khong_nhan_user_id():
    op = SPEC["paths"]["/actions"]["post"]
    ok = op["responses"]["200"]["content"]["application/json"]["schema"]
    assert ok == {"$ref": "../blocks/receipt.schema.json"}
    assert "428" in op["responses"]  # thiếu token -> NEEDS_CONFIRMATION
    body = SPEC["components"]["schemas"]["ActionRequest"]
    assert "user_id" not in body["properties"]
    assert body["required"] == ["tool", "params"]  # token tùy chọn: vắng thì 428
    assert SPEC["components"]["schemas"]["ConfirmationRequest"]["required"] == ["tool", "params"]


def schema_validator(registry, name):
    ref = f"{OPENAPI_URI}#/components/schemas/{name}"
    return Draft202012Validator({"$ref": ref}, registry=registry)


JAR = {
    "code": "an_uong", "name": "Ăn uống", "color_key": "violet", "icon_key": "utensils",
    "balance_vnd": 380000, "split_percent": 30,
}  # fmt: skip

VALID = {
    "JarsResponse": {
        "app_date": "2026-11-21", "as_of": "2026-12-10T03:00:00Z", "jars": [JAR],
        "jars_total_vnd": 380000,
    },
    "ConfirmationRequest": {"tool": "move_between_jars", "params": PARAMS, "params_hash": HASH},
    "ConfirmationResponse": {
        "confirm_token": TOKEN, "expires_at": "2026-12-10T03:02:00Z", "ttl_seconds": 120,
        "tool": "move_between_jars", "params": PARAMS, "params_hash": HASH,
    },
    "ActionRequest": {"tool": "move_between_jars", "params": PARAMS, "confirm_token": TOKEN},
    "ResetResponse": {
        "reset_at": "2026-12-10T03:00:00Z", "app_date": "2026-11-21", "clock_offset_days": -19,
        "jars_count": 7, "transactions_count": 120,
    },
    "ErrorResponse": {"error": {"code": "TOKEN_REUSED", "message": "Token đã được dùng."}},
    "ConversationListResponse": {
        "conversations": [
            {
                "conversation_id": "0b1f9c3e-5a7d-4e21-9f3a-6c1d2e8b4a70",
                "turns": 2,
                "last_activity_at": "2026-12-10T03:00:00Z",
                "preview": "số dư các hũ của mình",
            }
        ]
    },
    "ConversationResponse": {
        "conversation_id": "0b1f9c3e-5a7d-4e21-9f3a-6c1d2e8b4a70",
        "turns": [
            {
                "trace_id": "8f3a21c94b7e4d0aa1c25e6f7b8c9d01",
                "created_at": "2026-12-10T03:00:00Z",
                "user_text": "số dư các hũ của mình",
                "assistant_text": "Bạn có 7 hũ.",
                "blocks": [],
            }
        ],
    },
}  # fmt: skip


@pytest.mark.parametrize("name", VALID)
def test_vi_du_hop_le_qua_schema_cua_openapi(registry, name):
    assert list(schema_validator(registry, name).iter_errors(VALID[name])) == []


def test_action_request_khong_token_van_hop_le_de_server_tra_428(registry):
    body = {"tool": "move_between_jars", "params": PARAMS}
    assert schema_validator(registry, "ActionRequest").is_valid(body)


@pytest.mark.parametrize(
    ("name", "bad"),
    [
        (
            "ConfirmationRequest",
            {"tool": "move_between_jars", "params": {**PARAMS, "user_id": "x"}},
        ),
        (
            "ConfirmationRequest",
            {"tool": "move_between_jars", "params": {**PARAMS, "amount_vnd": 0}},
        ),
        ("ConfirmationRequest", {"tool": "drop_table", "params": PARAMS}),
        (
            "ConfirmationRequest",
            {"tool": "move_between_jars", "params": PARAMS, "params_hash": "abc"},
        ),
        ("ConfirmationResponse", {**VALID["ConfirmationResponse"], "confirm_token": "no-dot"}),
        ("ActionRequest", {"tool": "move_between_jars", "params": PARAMS, "user_id": "x"}),
        ("ErrorResponse", {"error": {"code": "NOPE", "message": "x"}}),
        ("JarsResponse", {**VALID["JarsResponse"], "jars_total_vnd": "380000"}),
    ],
)
def test_vi_du_sai_bi_tu_choi(registry, name, bad):
    assert not schema_validator(registry, name).is_valid(bad)


def test_conversation_turn_nhan_khoi_that_cua_hop_dong(registry):
    block = load_json(CONTRACTS / "fixtures/blocks/valid/receipt.move.json")
    turn = {**VALID["ConversationResponse"]["turns"][0], "blocks": [block]}
    body = {"conversation_id": "s" * 40, "turns": [turn]}
    assert schema_validator(registry, "ConversationResponse").is_valid(body)
    bad = {"conversation_id": "s" * 40, "turns": [{**turn, "blocks": [{"type": "receipt"}]}]}
    assert not schema_validator(registry, "ConversationResponse").is_valid(bad)


def test_receipt_fixture_la_thanh_cong_hop_le_cua_actions(registry):
    receipt = load_json(CONTRACTS / "fixtures/blocks/valid/receipt.move.json")
    v = Draft202012Validator(
        {"$ref": "https://contracts.yofina.invalid/blocks/receipt.schema.json"}, registry=registry
    )
    assert v.is_valid(receipt)
