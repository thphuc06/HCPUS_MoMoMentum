"""Hợp đồng của chứng từ ngoại tệ và mã INGEST_NO_TRANSACTIONS (F6, 25/11): khối `ingest_review` có `fx`, `amount_vnd` chỉ vắng khi
chưa có tỷ giá, `confirm_rows` nhận `amount_vnd` cho dòng ngoại tệ, mã lỗi mới khớp bốn nơi (yofina_core, OpenAPI, frontend, bảng của
backend và bản sao của eval), lý do con khớp giữa OpenAPI, backend và frontend."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import yaml
from ingest_helpers import REPO
from pydantic import ValidationError

from yofina_core import blocks as b
from yofina_core import ingest
from yofina_core.confirm import hash_normalized_params
from yofina_core.errors import HTTP_STATUS, ErrorCode
from yofina_core.params import ParamsError, normalize_confirm_rows

CONTRACTS = REPO / "contracts"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


SPEC = yaml.safe_load((CONTRACTS / "rest" / "openapi.yaml").read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]
FRONT = CONTRACTS.parent / "frontend" / "src"
JOB = "5c2d8e14-7a3b-4f60-9d21-0b4e6a8c1f37"
R1 = "9a1b2c3d-4e5f-4a6b-8c7d-000000000001"
R2 = "9a1b2c3d-4e5f-4a6b-8c7d-000000000002"


def _extract():
    from yofina_ingest import extract

    return extract


# --- mã lỗi ------------------------------------------------------------------------------------------------------------------
def test_ma_no_transactions_khop_cac_noi_va_them_cuoi():
    code = "INGEST_NO_TRANSACTIONS"
    schema = SCHEMAS["ErrorCode"]
    assert list(ErrorCode)[-1] == ErrorCode(code) and schema["enum"][-1] == code
    assert HTTP_STATUS[ErrorCode(code)] == 422 == schema["x-http-status"][code]
    assert "error_reason" in schema["x-meaning"][code]
    errors_ts = (FRONT / "api" / "errors.ts").read_text(encoding="utf-8")
    assert f"'{code}'," in errors_ts and f"{code}: 422," in errors_ts
    ex = _extract()
    assert ex.ERROR_CODE_OF["no_transactions"] == code
    assert (
        ex.ERROR_CODE_OF["not_financial"] == "INGEST_NOT_FINANCIAL"
    )  # hai trường hợp không còn chung một mã


def test_ly_do_con_khop_openapi_backend_va_frontend():
    reasons = SCHEMAS["IngestErrorReason"]["enum"]
    assert set(reasons) == set(_extract().NO_TX_REASONS)
    assert SCHEMAS["IngestJobResponse"]["properties"]["error_reason"] == {
        "$ref": "#/components/schemas/IngestErrorReason"
    }
    errors_ts = (FRONT / "api" / "errors.ts").read_text(encoding="utf-8")
    block = errors_ts.split("INGEST_NO_TX_REASON_MESSAGES", 1)[1].split("}", 1)[0]
    assert set(re.findall(r"^\s+(\w+):", block, re.M)) == set(reasons)
    migration = (CONTRACTS.parent / "db" / "migrations" / "0054_ingest_fx.sql").read_text(
        encoding="utf-8"
    )
    check = migration.split("ingest_jobs_error_reason_check CHECK", 1)[1].split(";", 1)[0]
    assert set(re.findall(r"'(\w+)'", check)) == set(reasons)


def test_fixture_rest_no_transactions_co_ly_do():
    j = load_json(CONTRACTS / "fixtures" / "rest" / "IngestJobResponse.no_transactions.json")
    assert (j["error_code"], j["error_reason"]) == (
        "INGEST_NO_TRANSACTIONS",
        "own_account_transfer",
    )
    assert j["error_message"] == _extract().NO_TX_REASONS["own_account_transfer"]


# --- khối ingest_review với fx ---------------------------------------------------------------------------------------------------
def _row(**kw):
    base = {
        "id": R1, "seq": 1, "kind": "expense", "app_date": date(2026, 11, 10), "amount_vnd": "2865527",
        "counterparty": "Dịch vụ AI", "description": None, "extract_confidence": "0.950", "suggested_jar_code": None,
        "jar_confidence": None, "jar_source": None, "review_status": "pending", "duplicate_of_transaction_id": None,
    }  # fmt: skip
    base.update(kw)
    return base


FX_OK = {"currency": "USD", "amount_original": "111.11", "status": "converted", "rate": "25790.00",
         "rate_type": "sell", "rate_source": "vietcombank", "rate_date": "2026-11-10"}  # fmt: skip


def build(rows):
    return ingest.build_ingest_review(
        job={"id": JOB, "status": "review", "source_kind": "image"}, rows=rows, jars=[], trace_id="a" * 32,
        source_tool="rest:GET /ingest/jobs/{job_id}", as_of=datetime(2026, 11, 24, 11, 30, tzinfo=UTC),
        app_date=date(2026, 11, 24),
    )  # fmt: skip


def test_dung_khoi_co_fx_va_dong_chua_co_ty_gia_khong_co_so_vnd():
    block = build([
        _row(fx=FX_OK),
        _row(id=R2, seq=2, amount_vnd=None, fx={"currency": "EUR", "amount_original": "48.5", "status": "rate_unavailable"}),
    ])  # fmt: skip
    wire = b.block_to_wire(block)["data"]["rows"]
    assert wire[0]["amount_vnd"] == 2_865_527 and wire[0]["fx"] == FX_OK
    assert "amount_vnd" not in wire[1] and wire[1]["fx"]["status"] == "rate_unavailable"


@pytest.mark.parametrize(
    ("row", "why"),
    [
        (_row(amount_vnd=None), "dòng VND không có số tiền"),
        (_row(amount_vnd=None, fx=FX_OK), "đã quy đổi mà không có số VND"),
        (_row(fx={**FX_OK, "rate": None}), "converted thiếu tỷ giá"),
        (
            _row(
                fx={
                    "currency": "USD",
                    "amount_original": "1",
                    "status": "rate_unavailable",
                    "rate": "1",
                }
            ),
            "rate_unavailable có tỷ giá",
        ),
        (_row(fx={**FX_OK, "currency": "VND"}), "fx cho dòng VND"),
        (_row(fx={**FX_OK, "amount_original": "1e3"}), "số gốc không phải chuỗi thập phân"),
    ],
)
def test_khoi_tu_choi_fx_sai(row, why):
    with pytest.raises(ValidationError):
        build([row])


# --- confirm_rows với amount_vnd ------------------------------------------------------------------------------------------
def test_chuan_hoa_confirm_rows_nhan_amount_vnd_va_idempotent():
    raw = {
        "job_id": JOB,
        "rows": [{"row_id": R2, "amount_vnd": "2950000"}, {"row_id": R1, "amount_vnd": ""}],
        "reject_row_ids": [],
    }
    n = normalize_confirm_rows(raw)
    assert n["rows"] == [{"row_id": R1}, {"row_id": R2, "amount_vnd": 2_950_000}]
    assert normalize_confirm_rows(n) == n
    other = normalize_confirm_rows({**raw, "rows": [{"row_id": R2, "amount_vnd": 2_950_001}]})
    assert hash_normalized_params("confirm_rows", n) != hash_normalized_params(
        "confirm_rows", other
    )  # token gắn với số


@pytest.mark.parametrize("bad", [0, -5, 1.5, True, "abc", 10**15])
def test_amount_vnd_sai_bi_tu_choi(bad):
    with pytest.raises(ParamsError):
        normalize_confirm_rows({"job_id": JOB, "rows": [{"row_id": R1, "amount_vnd": bad}]})


def test_rest_va_tool_cho_phep_amount_vnd_cua_dong():
    item = SCHEMAS["ConfirmRowsParams"]["properties"]["rows"]["items"]["properties"]
    assert item["amount_vnd"]["$ref"].endswith("#/$defs/VndPositive")
    tool = next(
        t for t in load_json(CONTRACTS / "tools" / "ingest.json") if t["name"] == "confirm_rows"
    )
    props = tool["inputSchema"]["properties"]["rows"]["items"]["properties"]
    assert (
        props["amount_vnd"]["type"] == "integer"
        and "Không tự quy đổi" in props["amount_vnd"]["description"]
    )


def test_frontend_zod_cua_khoi_co_fx():
    zod = (FRONT / "contracts" / "blocks.ts").read_text(encoding="utf-8")
    assert "export const IngestFx = z.object({" in zod
    assert "amount_vnd: VndPositive.optional()," in zod and "fx: IngestFx.optional()," in zod


def test_so_goc_va_ty_gia_giu_dung_chu_so():
    """`amount_original` và `rate` là chuỗi thập phân (không qua float); `rate` không mang hậu tố `_vnd` vì không phải số tiền."""
    ex = _extract()
    from yofina_core.fx import FxRate

    info = ex.FxInfo("USD", Decimal("111.11"), FxRate("USD", Decimal("25790"), date(2026, 11, 10)))
    assert info.to_json()["amount_original"] == "111.11" and info.to_json()["rate"] == "25790.00"
    assert b.IngestFx(**info.to_json()).rate == "25790.00"
