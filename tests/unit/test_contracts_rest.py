"""Hợp đồng REST (OpenAPI 3.1)."""

from __future__ import annotations

import pytest
import yaml
from conftest import CONTRACTS, OPENAPI_URI, load_json
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate

from yofina_core import wallet
from yofina_core.errors import HTTP_STATUS, ErrorCode

SPEC_PATH = CONTRACTS / "rest" / "openapi.yaml"
SPEC = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
HASH = "52a35d69448e3621190f43bbc8fa12356d2cfdd9895fac320e0557dfa779a962"
PARAMS = {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100000}
TOKEN = "eyJzdWIiOiJ4In0.c2ln"


def test_openapi_31_hop_le_ke_ca_tham_chieu_ngoai():
    assert SPEC["openapi"].startswith("3.1")
    validate(SPEC, base_uri=SPEC_PATH.as_uri())


def operations():
    return {(m.upper(), p) for p, item in SPEC["paths"].items() for m in item if m != "parameters"}


def test_cac_endpoint_cua_phase_1_va_phase_2_va_bearer_jwt():
    assert operations() == {
        # phase 1
        ("GET", "/jars"),
        ("POST", "/confirmations"),
        ("POST", "/confirmations/cancel"),
        ("POST", "/actions"),
        ("POST", "/demo/reset"),
        ("GET", "/conversations"),
        ("GET", "/conversations/{conversation_id}"),
        # phase 2: màn hình không cần LLM (chỉ đọc) + dự báo
        ("GET", "/overview"),
        ("GET", "/profile"),
        ("GET", "/jars/{jar_code}"),
        ("GET", "/transactions"),
        ("GET", "/tx-types"),
        ("GET", "/payees"),
        ("GET", "/obligations"),
        ("GET", "/credit-line"),
        ("GET", "/salary-events"),
        ("GET", "/jar-templates"),
        ("GET", "/forecasts/{jar_code}"),
        # phase 3: kiểm tra trước khi quẹt (không LLM), bảng "Vì sao", phản hồi phương án
        ("POST", "/affordability"),
        ("GET", "/traces/{trace_id}"),
        ("POST", "/feedback"),
        # phase 5 (F6): nạp dữ liệu
        ("POST", "/ingest/uploads"),
        ("GET", "/ingest/jobs"),
        ("GET", "/ingest/jobs/{job_id}"),
        ("POST", "/ingest/rows/{row_id}/jar"),
        ("POST", "/ingest/confirmations"),
        ("POST", "/ingest/actions"),
        # phase 4: điểm chống chịu, cú sốc (không LLM), lộ trình, "Xem lại" và hỏi gộp
        ("GET", "/resilience"),
        ("GET", "/resilience/shocks"),
        ("POST", "/resilience/stress"),
        ("GET", "/roadmap"),
        ("GET", "/roadmap/versions"),
        ("GET", "/roadmap/diff"),
        ("POST", "/roadmap/steps/{step_id}/decision"),
        ("POST", "/roadmap/steps/{step_id}/edit"),
        ("POST", "/roadmap/versions/{version}/decision"),
        ("POST", "/roadmap/regenerate"),
        ("GET", "/roadmap/jobs/{job_id}"),
        ("GET", "/review"),
        ("POST", "/review/daily-ask/skip"),
        # phase 5: hồ sơ hành vi, bản tin, bộ nhớ, xóa dữ liệu, bảng vận hành (nhóm ops)
        ("GET", "/profile/behavior"),
        ("GET", "/nudges/today"),
        ("POST", "/nudges/{nudge_id}/feedback"),
        ("GET", "/memory"),
        ("DELETE", "/memory"),
        ("DELETE", "/memory/{record_id}"),
        ("POST", "/me/delete-data/confirmations"),
        ("POST", "/me/delete-data"),
        ("GET", "/ops/traces"),
        ("GET", "/ops/traces/{trace_id}"),
        ("GET", "/ops/summary"),
        # đợt giao diện (biểu đồ chi tiêu B1, B5, B7): bản REST của tool get_cashflow_summary
        ("GET", "/cashflow"),
    }
    assert SPEC["security"] == [{"bearerAuth": []}]
    scheme = SPEC["components"]["securitySchemes"]["bearerAuth"]
    assert (scheme["type"], scheme["scheme"], scheme["bearerFormat"]) == ("http", "bearer", "JWT")


def test_khong_co_duong_ghi_tat_chi_post_confirmations_actions_va_reset():
    """Mọi thao tác ghi SỔ CÁI đi qua token xác nhận: ngoài hai endpoint đó chỉ có huỷ đề nghị (không ghi sổ cái), demo/reset,
    `POST /affordability` (POST chỉ để có thân yêu cầu, không ghi gì), `POST /feedback` (một dòng phản hồi, không đụng
    tiền) và hai endpoint nạp dữ liệu (phase 5, không ghi sổ cái): xin URL tải lên (tạo job, ghi đồng ý) và đổi hũ ĐỀ XUẤT
    của một dòng; cộng hai endpoint ghi của Lambda ingest (`/ingest/confirmations`, `/ingest/actions`) cho `confirm_rows`,
    cùng luồng token (không có đường ghi tắt). Không có PATCH (CORS của HTTP API chung chỉ cho GET, POST, OPTIONS). Lời nhắc (`schedule_nudge`) KHÔNG có endpoint riêng: đi qua /confirmations và /actions."""
    writes = {op for op in operations() if op[0] != "GET"}
    assert writes == {
        ("POST", "/confirmations"),
        ("POST", "/confirmations/cancel"),
        ("POST", "/actions"),
        ("POST", "/demo/reset"),
        ("POST", "/affordability"),
        ("POST", "/feedback"),
        ("POST", "/ingest/uploads"),
        ("POST", "/ingest/rows/{row_id}/jar"),
        ("POST", "/ingest/confirmations"),
        ("POST", "/ingest/actions"),
        # phase 4: không đổi số dư, không qua token (xem test_contracts_phase4)
        ("POST", "/resilience/stress"),
        ("POST", "/roadmap/steps/{step_id}/decision"),
        ("POST", "/roadmap/steps/{step_id}/edit"),
        ("POST", "/roadmap/versions/{version}/decision"),
        ("POST", "/roadmap/regenerate"),
        ("POST", "/review/daily-ask/skip"),
        # phase 5: phản hồi bản tin và xóa bộ nhớ không đụng tiền, không qua token; xóa dữ liệu đi qua token riêng (xem
        # test_contracts_phase5)
        ("POST", "/nudges/{nudge_id}/feedback"),
        ("DELETE", "/memory"),
        ("DELETE", "/memory/{record_id}"),
        ("POST", "/me/delete-data/confirmations"),
        ("POST", "/me/delete-data"),
    }
    # lên lịch nhắc vẫn KHÔNG có endpoint riêng (đi qua /confirmations và /actions); /nudges/* chỉ đọc bản tin và ghi phản hồi
    assert {path for _, path in operations() if "nudge" in path} == {"/nudges/today", "/nudges/{nudge_id}/feedback"}
    for path, method in (("/ingest/uploads", "post"), ("/ingest/rows/{row_id}/jar", "post")):
        text = SPEC["paths"][path][method]["description"]
        assert "không ghi sổ cái" in text or "presigned" in text, path


def test_moi_operation_co_id_duy_nhat_va_x_lambda_hop_le():
    ids = []
    for path, item in SPEC["paths"].items():
        for method, op in item.items():
            ids.append(op["operationId"])
            assert op.get("x-lambda", "ledger") in {"ledger", "forecast", "audit", "ingest"}, (method, path)
            assert op["tags"], (method, path)
    assert len(ids) == len(set(ids))
    assert SPEC["paths"]["/forecasts/{jar_code}"]["get"]["x-lambda"] == "forecast"

    def served_by(lam):
        return {
            p
            for p, item in SPEC["paths"].items()
            for op in item.values()
            if op.get("x-lambda", "ledger") == lam
        }

    assert served_by("forecast") == {
        "/forecasts/{jar_code}", "/affordability", "/resilience", "/resilience/shocks", "/resilience/stress",
        "/profile/behavior",
    }  # fmt: skip
    assert served_by("audit") == set()  # phase 3: audit chạy chung Lambda ledger
    assert {"/traces/{trace_id}", "/feedback"} <= served_by("ledger")
    ingest = {
        p for p, item in SPEC["paths"].items() for op in item.values() if op.get("x-lambda") == "ingest"
    }
    assert ingest == {p for p in SPEC["paths"] if p.startswith("/ingest/")}


def test_moi_endpoint_doc_co_loi_401_va_503():
    for path, item in SPEC["paths"].items():
        for method, op in item.items():
            if method == "get":
                assert "401" in op["responses"], path
                assert "503" in op["responses"], path


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
        "ALREADY_APPLIED",
    }
    assert required <= set(schema["enum"])


def test_moi_ma_http_loi_trong_operation_co_trong_bang_anh_xa():
    statuses = set(HTTP_STATUS.values())
    for path, item in SPEC["paths"].items():
        for method, op in item.items():
            for code in op["responses"]:
                if code != "200":
                    assert int(code) in statuses, (method, path, code)


def test_actions_tra_receipt_hoac_receipt_action_va_khong_nhan_user_id():
    op = SPEC["paths"]["/actions"]["post"]
    ok = op["responses"]["200"]["content"]["application/json"]["schema"]
    assert ok == {"$ref": "#/components/schemas/ActionResponse"}
    assert SPEC["components"]["schemas"]["ActionResponse"]["oneOf"] == [
        {"$ref": "../blocks/receipt.schema.json"},
        {"$ref": "../blocks/receipt_action.schema.json"},
    ]
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
    "ConfirmationResponse.co_xem_truoc": {
        "confirm_token": TOKEN, "expires_at": "2026-12-10T03:02:00Z", "ttl_seconds": 120,
        "tool": "move_between_jars", "params": PARAMS, "params_hash": HASH,
        "preview": {
            "summary": "Chuyển 100.000 ₫ từ Giải trí sang Ăn uống",
            "changes": [
                {"label": "Hũ Giải trí", "before": "760.000 ₫", "after": "660.000 ₫"},
                {"label": "Phải trả ngày 05/12", "before": "chưa có", "after": "333.000 ₫"},
            ],
            "warnings": ["Phí dịch vụ 33.000 ₫ tính một lần cho tháng có giao dịch."],
        },
    },
    "ActionRequest": {"tool": "move_between_jars", "params": PARAMS, "confirm_token": TOKEN},
    "ActionRequest.voi_de_nghi": {
        "tool": "move_between_jars", "params": PARAMS, "confirm_token": TOKEN,
        "conversation_id": "0b1f9c3e-5a7d-4e21-9f3a-6c1d2e8b4a70",
        "confirm_block_id": f"confirm:8f3a21c94b7e4d0aa1c25e6f7b8c9d01:{HASH[:12]}",
    },
    "ConfirmationRequest.voi_de_nghi": {
        "tool": "move_between_jars", "params": PARAMS,
        "conversation_id": "0b1f9c3e-5a7d-4e21-9f3a-6c1d2e8b4a70",
        "confirm_block_id": f"confirm:8f3a21c94b7e4d0aa1c25e6f7b8c9d01:{HASH[:12]}",
    },
    "ConfirmResolution.pending": {"block_id": "confirm:t:" + HASH[:12], "status": "pending"},
    "ConfirmResolution.expired": {"block_id": "confirm:t:" + HASH[:12], "status": "expired"},
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
                "resolutions": [],
            }
        ],
    },
}  # fmt: skip


@pytest.mark.parametrize("name", VALID)
def test_vi_du_hop_le_qua_schema_cua_openapi(registry, name):
    schema = name.split(".")[0]
    assert list(schema_validator(registry, schema).iter_errors(VALID[name])) == []


def test_confirm_resolution_done_mang_receipt_that(registry):
    receipt = load_json(CONTRACTS / "fixtures/blocks/valid/receipt.move.json")
    done = {
        "block_id": "confirm:t:" + HASH[:12],
        "status": "done",
        "resolved_at": "2026-12-10T03:00:00Z",
        "receipt": receipt,
    }
    v = schema_validator(registry, "ConfirmResolution")
    assert v.is_valid(done)
    assert not v.is_valid({k: x for k, x in done.items() if k != "receipt"})  # done phải có receipt
    assert not v.is_valid({**done, "receipt": {"type": "receipt"}})
    assert not v.is_valid({**done, "status": "pending"})  # pending không mang receipt
    assert not v.is_valid({"block_id": "x", "status": "cancelled"})


def test_turn_phai_co_resolutions(registry):
    turn = {**VALID["ConversationResponse"]["turns"][0]}
    body = {"conversation_id": "s" * 40, "turns": [turn]}
    assert schema_validator(registry, "ConversationResponse").is_valid(body)
    del turn["resolutions"]
    assert not schema_validator(registry, "ConversationResponse").is_valid(body)


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
        (
            "ActionRequest",
            {"tool": "move_between_jars", "params": PARAMS, "confirm_block_id": "confirm:x:abc"},
        ),
        (
            "ConfirmationRequest",
            {"tool": "move_between_jars", "params": PARAMS, "conversation_id": ""},
        ),
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


# =====================================================================================
# Phase 2: fixture REST, mọi thao tác ghi theo tool, bất biến của Tổng quan
# =====================================================================================
REST_FIXTURES = sorted((CONTRACTS / "fixtures" / "rest").glob("*.json"))
REST_INVALID = sorted((CONTRACTS / "fixtures" / "rest" / "invalid").glob("*.json"))


def schema_of(path) -> str:
    return path.name.split(".")[0]


@pytest.mark.parametrize("path", REST_FIXTURES, ids=lambda p: p.name)
def test_fixture_rest_hop_le_qua_schema_cua_openapi(registry, path):
    schema = schema_of(path)
    assert schema in SPEC["components"]["schemas"], f"{schema} không có trong components.schemas"
    errs = list(schema_validator(registry, schema).iter_errors(load_json(path)))
    assert errs == []


@pytest.mark.parametrize("path", REST_INVALID, ids=lambda p: p.name)
def test_fixture_rest_sai_bi_tu_choi(registry, path):
    schema = schema_of(path)
    assert schema in SPEC["components"]["schemas"]
    assert not schema_validator(registry, schema).is_valid(load_json(path))


def test_tool_name_khop_hang_so_va_moi_tool_co_rang_buoc_params():
    assert SPEC["components"]["schemas"]["ToolName"]["enum"] == list(wallet.ACTION_TOOLS)
    by_tool = SPEC["components"]["schemas"]["ParamsByTool"]["allOf"]
    mapped = [clause["if"]["properties"]["tool"]["const"] for clause in by_tool]
    assert mapped == list(wallet.ACTION_TOOLS)  # đủ và đúng thứ tự, không thiếu tool nào


def test_moi_tool_ghi_co_it_nhat_mot_ActionRequest_va_ConfirmationRequest_mau():
    have_action = {load_json(p)["tool"] for p in REST_FIXTURES if schema_of(p) == "ActionRequest"}
    have_conf = {
        load_json(p)["tool"] for p in REST_FIXTURES if schema_of(p) == "ConfirmationRequest"
    }
    assert have_action == have_conf == set(wallet.ACTION_TOOLS)


def test_action_request_va_confirmation_request_khong_nhan_user_id_o_bat_ky_tool_nao():
    for name in ("ActionRequest", "ConfirmationRequest"):
        props = SPEC["components"]["schemas"][name]["properties"]
        assert "user_id" not in props
        assert SPEC["components"]["schemas"][name]["additionalProperties"] is False


def test_params_tool_nay_khong_hop_le_voi_tool_kia(registry):
    v = schema_validator(registry, "ActionRequest")
    move = {"from_jar": "a", "to_jar": "b", "amount_vnd": 5}
    assert v.is_valid({"tool": "move_between_jars", "params": move})
    for tool in wallet.ACTION_TOOLS:
        if tool != "move_between_jars":
            assert not v.is_valid({"tool": tool, "params": move}), tool


def test_onboarding_chi_can_luong_va_ngay_nhan(registry):
    v = schema_validator(registry, "ActionRequest")
    assert v.is_valid(
        {"tool": "update_profile", "params": {"monthly_salary_vnd": 9000000, "payday_day": 5}}
    )
    # schema chỉ đòi có ít nhất một trường; "lần đầu phải có cả hai" do server kiểm (mô tả của UpdateProfileParams)
    assert (
        "monthly_salary_vnd" in SPEC["components"]["schemas"]["UpdateProfileParams"]["description"]
    )
    assert SPEC["components"]["schemas"]["UpdateProfileParams"]["minProperties"] == 1


def test_overview_nhat_quan_tong_so_du_gom_hai_hu_he_thong():
    ov = load_json(CONTRACTS / "fixtures/rest/OverviewResponse.minh.json")
    bal = ov["balance"]
    assert bal["jars_total_vnd"] == sum(j["balance_vnd"] for j in ov["jars"])
    assert (
        bal["total_vnd"]
        == bal["jars_total_vnd"] + bal["other_income_vnd"] + bal["unclassified_vnd"]
    )
    assert bal["total_vnd"] == sum(j["balance_vnd"] for j in [*ov["jars"], *ov["system_jars"]])
    assert round(sum(j["split_percent"] for j in ov["jars"]), 2) == 100  # tổng tỷ lệ chia lương
    assert all(j["kind"] != "system" for j in ov["jars"])
    roles = {j["system_role"]: j for j in ov["system_jars"]}
    assert set(roles) == {"other_income", "unclassified"}
    assert roles["other_income"]["code"] == wallet.OTHER_INCOME_JAR_CODE
    assert roles["unclassified"]["code"] == wallet.UNCLASSIFIED_JAR_CODE
    assert roles["other_income"]["balance_vnd"] == bal["other_income_vnd"]
    assert ov["proactive_card"]["type"] == "proactive_card"


def test_overview_tai_khoan_trang_khong_co_gi_de_tinh():
    ov = load_json(CONTRACTS / "fixtures/rest/OverviewResponse.blank.json")
    assert ov["profile"]["onboarded"] is False
    assert ov["jars"] == [] and ov["next_payday"] is None and ov["forecast"] is None
    assert ov["proactive_card"] is None and ov["balance"]["total_vnd"] == 0


def test_get_jars_cua_phase_1_khong_doi_hinh_dang():
    # GET /jars và tool get_jar_balances không gồm hũ hệ thống. Phase 4 thêm `kind` (chỉ loại hũ người dùng),
    # `goal_vnd`, `goal_date` dạng TÙY CHỌN; sáu trường bắt buộc của phase 1 giữ nguyên.
    jb = load_json(CONTRACTS / "blocks/jar_summary.schema.json")["$defs"]["JarBalance"]
    phase1 = {"code", "name", "color_key", "icon_key", "balance_vnd", "split_percent"}
    assert set(jb["required"]) == phase1
    assert set(jb["properties"]) == phase1 | {"kind", "goal_vnd", "goal_date"}
    assert "system" not in jb["properties"]["kind"]["enum"]


def test_forecasts_tra_dung_khoi_forecast_timeline():
    op = SPEC["paths"]["/forecasts/{jar_code}"]["get"]
    assert op["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "../blocks/forecast_timeline.schema.json"
    }
    assert {"404", "422", "503"} <= set(
        op["responses"]
    )  # JAR_NOT_FOUND, PROFILE_INCOMPLETE, FORECAST_UNAVAILABLE


def test_ma_loi_phase_2_co_trong_openapi_voi_dung_http_status():
    schema = SPEC["components"]["schemas"]["ErrorCode"]
    expected = {
        "PROFILE_INCOMPLETE": 422, "TRANSACTION_NOT_FOUND": 404, "OBLIGATION_NOT_FOUND": 404,
        "PAYEE_NOT_FOUND": 404, "SALARY_EVENT_NOT_FOUND": 404, "JAR_PROTECTED": 422,
        "CREDIT_LIMIT_EXCEEDED": 422, "DUPLICATE_TRANSACTION": 409, "FORECAST_UNAVAILABLE": 503,
    }  # fmt: skip
    for code, status in expected.items():
        assert code in schema["enum"] and schema["x-http-status"][code] == status
        assert HTTP_STATUS[ErrorCode(code)] == status


def test_confirm_resolution_done_nhan_ca_receipt_lan_receipt_action(registry):
    v = schema_validator(registry, "ConfirmResolution")
    for name in ("receipt.move.json", "receipt_action.record_transaction.json"):
        receipt = load_json(CONTRACTS / "fixtures/blocks/valid" / name)
        done = {
            "block_id": "confirm:t:" + HASH[:12], "status": "done",
            "resolved_at": "2026-12-10T03:00:00Z", "receipt": receipt,
        }  # fmt: skip
        assert v.is_valid(done), name
    assert not v.is_valid(
        {**done, "receipt": load_json(CONTRACTS / "fixtures/blocks/valid/notice.degraded.json")}
    )


def test_reset_response_nhan_truong_phase_2_tuy_chon(registry):
    body = {**VALID["ResetResponse"], "obligations_count": 2, "forecast_ready": True}
    v = schema_validator(registry, "ResetResponse")
    assert v.is_valid(body) and v.is_valid(VALID["ResetResponse"])  # trường mới là tùy chọn
    assert SPEC["components"]["schemas"]["ResetResponse"]["required"] == [
        "reset_at", "app_date", "clock_offset_days", "jars_count", "transactions_count",
    ]  # fmt: skip
