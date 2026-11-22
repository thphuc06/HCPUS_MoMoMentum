"""Hợp đồng phase 5 (F6, nạp dữ liệu): khối ingest_review và coverage_change, tool target `ingest`, kết quả tool, REST /ingest/*,
chuẩn hóa tham số confirm_rows, cấu hình, khóa khử trùng và độ phủ (cùng công thức với dự báo)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import yaml
from conftest import BASE, CONTRACTS, OPENAPI_URI, load_json
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from test_contracts_blocks import contract_tree, pydantic_tree

from yofina_core import blocks as b
from yofina_core import ingest, wallet
from yofina_core.config import Config
from yofina_core.confirm import hash_normalized_params, params_hash
from yofina_core.errors import HTTP_STATUS, ErrorCode
from yofina_core.params import (
    ParamsError,
    compute_dedupe_key,
    normalize_confirm_rows,
    normalize_params,
)

TOOLS = load_json(CONTRACTS / "tools" / "ingest.json")
BY_NAME = {t["name"]: t for t in TOOLS}
SPEC = yaml.safe_load((CONTRACTS / "rest" / "openapi.yaml").read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]
FIX = CONTRACTS / "fixtures"
REVIEW = load_json(CONTRACTS / "blocks" / "ingest_review.schema.json")["$defs"]
COVERAGE = load_json(CONTRACTS / "blocks" / "coverage_change.schema.json")["$defs"]
JOB = "5c2d8e14-7a3b-4f60-9d21-0b4e6a8c1f37"
R1 = "9a1b2c3d-4e5f-4a6b-8c7d-000000000001"
R2 = "9a1b2c3d-4e5f-4a6b-8c7d-000000000002"


def v(registry, ref: str) -> Draft202012Validator:
    return Draft202012Validator({"$ref": ref}, registry=registry)


# --- khối -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("type_", ["ingest_review", "coverage_change"])
def test_pydantic_khop_hinh_dang_json_schema(registry, type_):
    assert pydantic_tree(b.BLOCK_MODELS[type_]) == contract_tree(registry, type_)


@pytest.mark.parametrize("type_", ["receipt_action", "confirm_action"])
def test_khoi_cu_van_khop_sau_khi_them_confirm_rows(registry, type_):
    assert pydantic_tree(b.BLOCK_MODELS[type_]) == contract_tree(registry, type_)


def test_moi_khoi_moi_co_fixture_hop_le_va_khong_hop_le():
    valid = {p.name.split(".")[0] for p in (FIX / "blocks/valid").glob("*.json")}
    invalid = {p.name.split(".")[0] for p in (FIX / "blocks/invalid").glob("*.json")}
    assert {"ingest_review", "coverage_change"} <= valid & invalid
    assert (FIX / "blocks/schema_only_invalid/ingest_review.extra_field.json").exists()


def test_id_khoi_theo_quy_tac_va_dem_nhat_quan():
    for name in ("ingest_review.review", "ingest_review.done"):
        obj = load_json(FIX / f"blocks/valid/{name}.json")
        d = obj["data"]
        assert obj["id"] == f"ingest_review:{d['job_id']}"
        assert sum(d["counts"].values()) == d["rows_total"] == len(d["rows"])
        assert [r["seq"] for r in d["rows"]] == sorted(r["seq"] for r in d["rows"])
        codes = {j["code"] for j in d["jars"]}
        assert (
            "tien_vao_khac" not in codes and "chua_phan_loai" not in codes
        )  # không chọn được hũ hệ thống
        for r in d["rows"]:
            if r["kind"] == "income":
                assert "suggested_jar" not in r  # thu nhập ngoài ví không có hũ
            if "suggested_jar" in r:
                assert r["suggested_jar"]["code"] in codes and "jar_source" in r
            assert ("duplicate_of" in r) == (r["review_status"] == "duplicate")
    cov = load_json(FIX / "blocks/valid/coverage_change.added.json")
    assert cov["id"] == f"coverage_change:{cov['data']['job_id']}"


def test_bien_nhan_confirm_rows_mang_khoi_coverage_change(registry):
    rec = load_json(FIX / "blocks/valid/receipt_action.confirm_rows.json")
    assert (
        rec["data"]["tool"] == "confirm_rows" and rec["data"]["jars_after"] == []
    )  # không hũ nào đổi số dư
    assert rec["data"]["coverage_change"]["type"] == "coverage_change"
    assert v(registry, f"{BASE}/blocks/coverage_change.schema.json").is_valid(
        rec["data"]["coverage_change"]
    )
    parsed = b.parse_block(rec)
    assert isinstance(parsed.data.coverage_change, b.CoverageChangeBlock)


def test_ty_le_do_phu_la_0_den_1(registry):
    obj = load_json(FIX / "blocks/valid/coverage_change.added.json")
    obj["data"]["before"] = 62
    assert not v(registry, f"{BASE}/blocks/coverage_change.schema.json").is_valid(obj)


def test_builder_ingest_review_bo_hu_he_thong_va_cat_200_dong():
    rows = [
        {"id": f"9a1b2c3d-4e5f-4a6b-8c7d-{i:012d}", "seq": i, "kind": "expense", "app_date": "2026-11-18",
         "amount_vnd": "1000", "extract_confidence": "0.5", "suggested_jar_code": "tien_vao_khac",
         "jar_confidence": "0.9", "jar_source": "model", "review_status": "pending"}
        for i in range(1, 251)
    ]  # fmt: skip
    jars = [
        {
            "code": "tien_vao_khac",
            "name": "Tiền vào khác",
            "color_key": "gray",
            "icon_key": "inbox",
            "kind": "system",
        }
    ]
    blk = ingest.build_ingest_review(
        job={"id": JOB, "status": "review", "source_kind": "csv"}, rows=rows, jars=jars, trace_id="t1",
        source_tool="x", as_of=datetime(2026, 12, 10, tzinfo=UTC), app_date=date(2026, 11, 21),
    )  # fmt: skip
    assert (
        len(blk.data.rows) == 200 and blk.data.rows_total == 250 and blk.data.counts.pending == 250
    )
    assert blk.data.jars == [] and all(
        r.suggested_jar is None and r.jar_source is None for r in blk.data.rows
    )
    assert len(blk.fallback_text) <= 280


def test_builder_coverage_change_tu_choi_trang_thai_la():
    with pytest.raises(ValueError):
        ingest.build_coverage_change(
            job_id=JOB, before=None, after=None, rows_added=0, external_spend_added_vnd=0, jars_affected=[],
            forecast_refresh="running", trace_id="t", source_tool="x", as_of=datetime(2026, 12, 10, tzinfo=UTC),
            app_date=date(2026, 11, 21),
        )  # fmt: skip


# --- tool Gateway target `ingest` -----------------------------------------------------------------------------
NODE_KEYS = {"type", "description", "properties", "required", "items"}


def walk(node, path="inputSchema"):
    assert set(node) <= NODE_KEYS, f"{path}: từ khóa Gateway không nhận: {set(node) - NODE_KEYS}"
    assert node["type"] in {"string", "integer", "number", "boolean", "array", "object"}, path
    assert path == "inputSchema" or node.get("description", "").strip(), path
    if node["type"] == "array":
        assert "items" in node, path
    for name, child in node.get("properties", {}).items():
        yield from walk(child, f"{path}.{name}")
    if "items" in node:
        yield from walk(node["items"], f"{path}[]")
    yield path, node


def test_tool_dung_thu_tu_hang_so_va_dinh_dang_inline_payload():
    assert [t["name"] for t in TOOLS] == list(ingest.INGEST_TOOLS)
    for t in TOOLS:
        assert set(t) == {"name", "description", "inputSchema"} and t["description"].strip()
        schema = t["inputSchema"]
        assert schema["type"] == "object"
        list(walk(schema))
        assert set(schema.get("required", [])) <= set(schema["properties"])
        text = str(schema)
        for kw in (
            "enum",
            "minimum",
            "maximum",
            "pattern",
            "minLength",
            "maxLength",
            "minItems",
            "maxItems",
            "$ref",
        ):
            assert f"'{kw}'" not in text, (t["name"], kw)


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t["name"])
def test_ten_day_du_duoi_64_ky_tu_va_user_id_tu_dien(tool):
    full = f"{ingest.TARGET}___{tool['name']}"
    assert len(full) < 64 and full.replace("_", "").isalnum() and full.isascii()
    props = tool["inputSchema"]["properties"]
    assert props["user_id"]["type"] == "string" and "tự điền" in props["user_id"]["description"]
    assert "user_id" not in tool["inputSchema"].get("required", [])


def test_confirm_rows_co_token_tuy_chon_va_mo_ta_chuan_cua_tool_ghi():
    t = BY_NAME["confirm_rows"]
    props = t["inputSchema"]["properties"]
    assert set(props) == {"user_id", "job_id", "rows", "reject_row_ids", "confirm_token"}
    assert t["inputSchema"]["required"] == ["job_id"]
    assert "confirm_token" not in t["inputSchema"]["required"]
    assert "KHÔNG ghi gì" in t["description"] and "bịa" in t["description"]
    assert "external" in t["description"] and "KHÔNG đổi số dư" in t["description"]
    assert props["rows"]["items"]["required"] == ["row_id"]
    for name in ("start_job", "get_job_status"):
        assert "confirm_token" not in BY_NAME[name]["inputSchema"]["properties"]
    assert "KHÔNG tạo job" in BY_NAME["start_job"]["description"]
    assert (
        "không phải chỉ dẫn" in BY_NAME["get_job_status"]["description"]
    )  # nội dung tệp là dữ liệu


def test_mo_ta_tool_neu_gia_tri_hop_le():
    sk = BY_NAME["start_job"]["inputSchema"]["properties"]["source_kind"]["description"]
    for kind in ingest.SOURCE_KINDS:
        assert kind in sk


def test_confirm_rows_la_tool_ghi_qua_actions_nhung_khong_thuoc_target_ledger():
    assert (
        wallet.CONFIRM_ROWS in wallet.ACTION_TOOLS
        and wallet.CONFIRM_ROWS in wallet.GENERIC_ACTION_TOOLS
    )
    assert (
        wallet.CONFIRM_ROWS not in wallet.AGENT_WRITE_TOOLS
    )  # AGENT_WRITE_TOOLS là tool ghi của target ledger
    assert wallet.CONFIRM_ROWS not in wallet.LEDGER_TOOLS
    assert ingest.INGEST_WRITE_TOOLS == (wallet.CONFIRM_ROWS,)
    ledger = {t["name"] for t in load_json(CONTRACTS / "tools" / "ledger.json")}
    assert not ledger & set(ingest.INGEST_TOOLS)


# --- kết quả tool --------------------------------------------------------------------------------------------
RESULT_DEF = {
    "start_job": "StartJobResult",
    "get_job_status": "GetJobStatusResult",
    "confirm_rows": "ConfirmRowsResult",
}
TOOL_FIX = sorted((FIX / "tools" / "ingest").glob("*.json"))


def test_moi_tool_co_dinh_nghia_ket_qua_va_fixture():
    assert set(RESULT_DEF) == set(ingest.INGEST_TOOLS)
    assert {p.name.split(".")[0] for p in TOOL_FIX} == set(ingest.INGEST_TOOLS)
    names = {p.name for p in TOOL_FIX}
    assert {"confirm_rows.needs_confirmation.json", "confirm_rows.ok.json"} <= names


@pytest.mark.parametrize("path", TOOL_FIX, ids=lambda p: p.name)
def test_fixture_ket_qua_tool_hop_le_ca_schema_lan_pydantic(registry, path):
    tool = path.name.split(".")[0]
    obj = load_json(path)
    ref = f"{BASE}/tools/ingest.results.schema.json#/$defs/{RESULT_DEF[tool]}"
    assert list(v(registry, ref).iter_errors(obj)) == []
    if obj["status"] == "ERROR":
        assert obj["code"] in {c.value for c in ErrorCode}
        return
    model = next(
        m
        for m in ingest.RESULT_MODELS[tool]
        if m.model_fields["status"].annotation.__args__[0] == obj["status"]
    )
    parsed = model.model_validate(obj)
    assert parsed.model_dump(mode="json", by_alias=True, exclude_none=True) == obj
    if tool == "confirm_rows":
        assert obj["data"]["tool"] == "confirm_rows"


def test_ket_qua_sai_bi_tu_choi(registry):
    ref = f"{BASE}/tools/ingest.results.schema.json#/$defs/GetJobStatusResult"
    ok = load_json(FIX / "tools/ingest/get_job_status.ok_review.json")
    assert not v(registry, ref).is_valid({**ok, "data": {**ok["data"], "progress": 101}})
    assert not v(registry, ref).is_valid({**ok, "data": {**ok["data"], "status": "uploaded"}})
    cref = f"{BASE}/tools/ingest.results.schema.json#/$defs/ConfirmRowsResult"
    need = load_json(FIX / "tools/ingest/confirm_rows.needs_confirmation.json")
    assert not v(registry, cref).is_valid(
        {**need, "status": "OK"}
    )  # confirm_action không phải biên nhận
    with pytest.raises(ValidationError):
        ingest.ConfirmRowsOk.model_validate({**need, "status": "OK"})


# --- REST --------------------------------------------------------------------------------------------------
def schema_validator(registry, name):
    return v(registry, f"{OPENAPI_URI}#/components/schemas/{name}")


def test_endpoint_ingest_dung_lambda_ingest_va_co_loi_chuan():
    for path, method in (
        ("/ingest/uploads", "post"),
        ("/ingest/jobs/{job_id}", "get"),
        ("/ingest/rows/{row_id}", "patch"),
    ):
        op = SPEC["paths"][path][method]
        assert op["x-lambda"] == "ingest" and op["tags"] == ["ingest"]
        assert {"401", "503", "500"} <= set(op["responses"])
    up = SPEC["paths"]["/ingest/uploads"]["post"]
    assert {"403", "413", "415"} <= set(up["responses"])
    assert "CONSENT_REQUIRED" in up["description"] and "ObjectCreated" in up["description"]
    assert "404" in SPEC["paths"]["/ingest/jobs/{job_id}"]["get"]["responses"]
    assert "không ghi sổ cái" in SPEC["paths"]["/ingest/rows/{row_id}"]["patch"]["description"]
    assert "confirm_rows" in SPEC["paths"]["/actions"]["post"]["description"]


def test_khong_endpoint_nao_nhan_user_id():
    for name in ("IngestUploadRequest", "IngestRowJarRequest", "ConfirmRowsParams"):
        assert (
            "user_id" not in SCHEMAS[name]["properties"]
            and SCHEMAS[name]["additionalProperties"] is False
        )


def test_confirm_rows_trong_tool_name_va_params_by_tool(registry):
    assert "confirm_rows" in SCHEMAS["ToolName"]["enum"]
    mapped = [c["if"]["properties"]["tool"]["const"] for c in SCHEMAS["ParamsByTool"]["allOf"]]
    assert mapped[-1] == "confirm_rows"
    act = schema_validator(registry, "ActionRequest")
    good = load_json(FIX / "rest/ActionRequest.confirm_rows.json")
    assert act.is_valid(good)
    assert not act.is_valid({**good, "params": {"job_id": JOB, "rows": [{"row_id": "x"}]}})


@pytest.mark.parametrize("path", sorted((FIX / "rest").glob("Ingest*.json")), ids=lambda p: p.name)
def test_fixture_rest_ingest_hop_le(registry, path):
    assert (
        list(schema_validator(registry, path.name.split(".")[0]).iter_errors(load_json(path))) == []
    )


def test_upload_response_khoa_khong_co_ten_tep_va_job_done_co_coverage():
    up = load_json(FIX / "rest/IngestUploadResponse.image.json")
    assert up["key"].endswith(up["job_id"]) and up["key"].count("/") == 1
    done = load_json(FIX / "rest/IngestJobResponse.done.json")
    assert (
        done["review"]["type"] == "ingest_review"
        and done["coverage_change"]["type"] == "coverage_change"
    )


def test_ma_loi_moi_khop_ba_noi():
    new = {
        "CONSENT_REQUIRED": 403, "INGEST_JOB_NOT_FOUND": 404, "INGEST_JOB_NOT_READY": 409,
        "INGEST_UNSUPPORTED_TYPE": 415, "INGEST_TOO_LARGE": 413, "INGEST_NOT_FINANCIAL": 422,
        "INGEST_DUPLICATE_FILE": 409,
    }  # fmt: skip
    schema = SCHEMAS["ErrorCode"]
    for code, status in new.items():
        assert HTTP_STATUS[ErrorCode(code)] == status == schema["x-http-status"][code]
        assert schema["x-meaning"][code]
    assert schema["enum"][-len(new) :] == list(new)  # thêm cuối, không đổi thứ tự mã cũ
    front = (CONTRACTS.parent / "frontend/src/api/errors.ts").read_text(encoding="utf-8")
    for code, status in new.items():
        assert f"'{code}'," in front and f"{code}: {status}," in front


def test_transaction_funding_source_co_external():
    tx = load_json(CONTRACTS / "tools/ledger.results.schema.json")["$defs"]["Transaction"][
        "properties"
    ]
    assert tx["funding_source"]["enum"] == list(wallet.FUNDING_SOURCES)
    assert "external" in tx["funding_source"]["description"]
    ev = load_json(CONTRACTS / "events/transaction.recorded.schema.json")["properties"]
    assert ev["funding_source"]["enum"] == list(wallet.FUNDING_SOURCES)
    front = (CONTRACTS.parent / "frontend/src/api/schemas.ts").read_text(encoding="utf-8")
    assert "funding_source: z.enum(['jar', 'credit', 'external'])" in front


# --- chuẩn hóa confirm_rows --------------------------------------------------------------------------------
def test_chuan_hoa_confirm_rows_sap_xep_va_idempotent():
    raw = {
        "job_id": JOB.upper(), "user_id": "sub-lan", "confirm_token": "x",
        "rows": [{"row_id": R2, "jar": " GIAI_TRI "}, {"row_id": R1.upper(), "jar": ""}],
        "reject_row_ids": None,
    }  # fmt: skip
    n = normalize_params("confirm_rows", raw)
    assert n == {
        "job_id": JOB,
        "rows": [{"row_id": R1}, {"row_id": R2, "jar": "giai_tri"}],
        "reject_row_ids": [],
    }
    assert normalize_confirm_rows(n) == n and normalize_params("confirm_rows", n, None) == n
    assert params_hash("confirm_rows", raw) == hash_normalized_params("confirm_rows", n)
    swapped = {**raw, "rows": list(reversed(raw["rows"]))}
    assert normalize_params("confirm_rows", swapped) == n  # thứ tự gửi không đổi hash


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"job_id": "x", "rows": [{"row_id": R1}]},
        {"job_id": JOB},
        {"job_id": JOB, "rows": [], "reject_row_ids": []},
        {"job_id": JOB, "rows": [{"row_id": R1}], "reject_row_ids": [R1]},
        {"job_id": JOB, "rows": [{"row_id": R1}, {"row_id": R1}]},
        {"job_id": JOB, "rows": [{"row_id": R1, "jar": "Ăn uống"}]},
        {"job_id": JOB, "rows": "r1"},
        {"job_id": JOB, "rows": [R1]},
        {"job_id": JOB, "reject_row_ids": [R1, R1]},
    ],
)
def test_chuan_hoa_confirm_rows_tu_choi(bad):
    with pytest.raises(ParamsError):
        normalize_confirm_rows(bad)


def test_record_transaction_khong_nhan_external():
    with pytest.raises(ParamsError):
        normalize_params(
            "record_transaction",
            {"kind": "expense", "amount_vnd": 1000, "jar": "an_uong", "funding": "external"},
        )


# --- khóa khử trùng và độ phủ ----------------------------------------------------------------------------------
def test_khoa_khu_trung_cung_cong_thuc_so_cai():
    key = ingest.row_dedupe_key(
        app_date="2026-11-18",
        amount_vnd=-85000,
        counterparty="Cơm Tấm  Phúc Lộc",
        content_sha256="ab" * 32,
        seq=3,
    )
    assert key == compute_dedupe_key(
        app_date=date(2026, 11, 18), amount_vnd=85000, payee_id=None, counterparty="com tam phuc loc",
        client_ref=f"ingest:{'ab' * 8}:3",
    )  # fmt: skip
    other = ingest.row_dedupe_key(
        app_date="2026-11-18",
        amount_vnd=85000,
        counterparty="Cơm Tấm Phúc Lộc",
        content_sha256="cd" * 32,
        seq=3,
    )
    assert (
        other != key
    )  # tệp khác (dù cùng dòng) thì khóa khác; cửa sổ ngày + số tiền mới bắt trùng chéo tệp


def test_do_phu_cung_cong_thuc_voi_quality_data_coverage():
    from yofina_ml import quality
    from yofina_ml.types import CoverageInputs

    cases = [
        {"income_vnd": "9500000", "spend_vnd": "6200000", "balance_start_vnd": "1000000", "balance_end_vnd": "2900000"},
        {"income_vnd": 0, "spend_vnd": 10, "balance_start_vnd": 0, "balance_end_vnd": 0},
        {"income_vnd": 100, "spend_vnd": 900, "balance_start_vnd": 0, "balance_end_vnd": 0},
        {"income_vnd": 100, "spend_vnd": 0, "balance_start_vnd": 500, "balance_end_vnd": 0},
    ]  # fmt: skip
    for c in cases:
        expect = quality.data_coverage(
            CoverageInputs(**{k: int(Decimal(str(x))) for k, x in c.items()})
        )
        assert ingest.coverage_ratio(c) == expect
    assert ingest.COVERAGE_FORMULA == quality.COVERAGE_FORMULA
    assert ingest.coverage_ratio(None) is None


# --- cấu hình ---------------------------------------------------------------------------------------------------
def test_cau_hinh_mac_dinh_va_ghi_de():
    d = ingest.IngestSettings.from_config(Config(env={}))
    assert d == ingest.IngestSettings()
    assert d.ingest_dedupe_window_days == 3 and d.ingest_image_max_bytes == 3_750_000
    assert d.mime_types["image"] == ("image/png", "image/jpeg", "image/webp")
    env = {
        "YOFINA_INGEST_DEDUPE_WINDOW_DAYS": "5", "YOFINA_INGEST_CSV_MIME_TYPES": "text/csv",
        "YOFINA_INGEST_AUTO_EXTRACT_MIN_CONFIDENCE": "0.95",
    }  # fmt: skip
    s = ingest.IngestSettings.from_config(Config(env=env))
    assert s.ingest_dedupe_window_days == 5 and s.ingest_csv_mime_types == ("text/csv",)
    assert s.ingest_auto_extract_min_confidence == Decimal("0.95")
    with pytest.raises(ValueError):
        ingest.IngestSettings.from_config(Config(env={"YOFINA_INGEST_DEDUPE_WINDOW_DAYS": "31"}))


def test_nguong_tu_chon_san():
    s = ingest.IngestSettings()
    ok = dict(
        kind="expense", extract_confidence=0.95, jar_code="an_uong", jar_confidence=0.85, settings=s
    )
    assert ingest.should_auto_add(**ok)
    assert not ingest.should_auto_add(**{**ok, "jar_code": None, "jar_confidence": None})
    assert not ingest.should_auto_add(**{**ok, "extract_confidence": 0.89})
    assert not ingest.should_auto_add(**{**ok, "jar_confidence": 0.79})
    assert ingest.should_auto_add(
        kind="income", extract_confidence=0.9, jar_code=None, jar_confidence=None, settings=s
    )


def test_readme_ghi_khoa_cau_hinh_va_bang_ra_soat():
    text = (CONTRACTS / "README.md").read_text(encoding="utf-8")
    assert "## Phase 5 (F6): nạp dữ liệu" in text
    for name in ingest.IngestSettings.__dataclass_fields__:
        assert f"`{name}`" in text, name
    for fn in ("SQL_RECOMPUTE_BALANCES", "app_get_jar_state", "app_get_overview", "app_get_cashflow_summary",
               "app_get_daily_spend", "app_get_forecast_context", "plan_event", "RESET_DELETES", "assign_jar"):  # fmt: skip
        assert fn in text, fn
