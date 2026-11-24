"""Bảng vận hành (FR15, phase 5): `/ops/*` chỉ cho nhóm Cognito `ops`, dữ liệu đúng OpenAPI và đã che PII, tổng hợp p50/p95, lỗi
tool, luật chặn, lượt gọi model theo ngày so với trần (bộ đếm `yofina-usage`). Cùng bản ghi lượt nhận ý định phase 5 và bước gọi
tool có `status`. DB và DynamoDB là đồ giả trong test; SQL thật là các hàm `app_ops_*` của migration 0053."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from conftest import OPENAPI_URI
from jsonschema import Draft202012Validator
from ledger_fakes import NOW, http_event, make_service

from yofina_audit.ops_view import Pricing, mask, tool_calls_of, trace_detail
from yofina_audit.record import parse_turn_record
from yofina_audit.trace import build_trace_data
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.llm import load_settings
from yofina_core.wallet import PHASE5_INTENTS
from yofina_ledger import ops_rest
from yofina_ledger.ops import (
    SQL_GET_TRACE,
    SQL_LIST_TRACES,
    SQL_MODEL_CALLS_BY_DAY,
    SQL_SUMMARY,
    OpsRepo,
    OpsService,
    OpsSettings,
    UsageReader,
    decode_cursor,
    encode_cursor,
)
from yofina_ledger.rest_api import handle_http

AUDIT_RESULTS_URI = "https://contracts.yofina.invalid/tools/audit.results.schema.json"
PRICING = Pricing(Decimal(3), Decimal(15), Decimal("0.3"), Decimal(26000))
CAPS = {"model-a": 400, "model-b": 2000}
SETTINGS = OpsSettings(
    pricing=PRICING,
    default_range_days=7,
    max_summary_days=31,
    budget_timezone="Asia/Ho_Chi_Minh",
    model_caps=CAPS,
)
CREATED = datetime(2026, 12, 10, 3, 0, 2, 123456, tzinfo=UTC)

STEPS = [
    {"step": "router", "ms": 480},
    {"step": "ledger___get_jar_balances", "ms": 140, "status": "ok"},
    {
        "step": "forecast___run_scenario",
        "ms": 1450,
        "status": "error",
        "code": "FORECAST_UNAVAILABLE",
    },
    {"step": "planner___check_suitability", "ms": 60, "status": "denied", "code": "KHONG_PHAI_MA"},
    {"step": "verifier", "ms": 35},
]
RULES = [
    {"rule_id": "numeric_grounding", "label": "Số liệu có căn cứ", "outcome": "pass"},
    {
        "rule_id": "obligation_to_income",
        "label": "Nghĩa vụ trên thu nhập",
        "outcome": "fail",
        "detail": "Khoản trả cho Nguyễn Minh Khoa, SĐT 0912345678, vượt ngưỡng.",
    },
]
DATA_USED = [
    {"label": "Số dư hũ Giải trí", "value": "760.000 ₫", "tool": "ledger___get_jar_balances"},
    {
        "label": "Chuyển cho Trần Quốc Bảo",
        "value": "STK 0123456789012",
        "tool": "ledger___query_transactions",
    },
]


def row(**kw):
    base = {
        "trace_id": "8f3a21c94b7e4d0aa1c25e6f7b8c9d01",
        "created_at": CREATED,
        "user_ref": "3f9a0c1d2e4b",
        "intent": "what_if",
        "outcome": "ok",
        "code": None,
        "duration_ms": 5400,
        "token_usage": {
            "input_tokens": 5200,
            "output_tokens": 640,
            "model_calls": 3,
            "cache_read_tokens": 1024,
        },
        "step_timings": STEPS,
        "rules_checked": RULES,
        "data_used": DATA_USED,
        "confidence": {"band": "medium", "reasons": ["Có 47 ngày dữ liệu."]},
        "blocks_emitted": [{"id": "options:8f3a21c94b7e4d0aa1c25e6f7b8c9d01", "type": "options"}],
    }
    base.update(kw)
    return base


class FakeDb:
    """Trả dòng theo câu SQL; ghi lại mọi lời gọi để kiểm tham số."""

    def __init__(self, results=None):
        self.results = results or {}
        self.calls: list[tuple[str, dict]] = []

    def query(self, sql, params=None, *, max_rows=None):
        self.calls.append((sql, dict(params or {})))
        rows = self.results.get(sql, [])
        rows = rows(params) if callable(rows) else rows
        assert max_rows is None or len(rows) <= max_rows
        return rows


class FakeDdb:
    def __init__(self, items_by_day=None, fail=False):
        self.items_by_day = items_by_day or {}
        self.fail = fail
        self.calls: list[dict] = []

    def query(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise RuntimeError("AccessDeniedException")
        day = kw["ExpressionAttributeValues"][":d"]["S"]
        items = [{"count": {"N": str(n)}} for n in self.items_by_day.get(day, [])]
        if "ExclusiveStartKey" in kw:  # trang thứ hai: phần còn lại
            return {"Items": items[1:]}
        page = {"Items": items[:1]}  # trang thứ nhất: một mục, còn nữa thì có LastEvaluatedKey
        if len(items) > 1:
            page["LastEvaluatedKey"] = {"day": {"S": day}, "model": {"S": "x"}}
        return page


def make_ops(db=None, ddb=None):
    usage = UsageReader("yofina-usage", ddb) if ddb is not None else None
    return OpsService(OpsRepo(db or FakeDb()), SETTINGS, usage=usage, now=lambda: NOW)


@pytest.fixture
def schema_ok(registry):
    def run(name: str, instance):
        v = Draft202012Validator(
            {"$ref": f"{OPENAPI_URI}#/components/schemas/{name}"}, registry=registry
        )
        errors = [f"{list(e.path)}: {e.message}" for e in v.iter_errors(instance)]
        assert not errors, errors

    return run


def req(svc, path, *, groups="[ops]", sub="sub-ops", query=None, path_params=None):
    res = handle_http(
        http_event("GET", path, sub=sub, groups=groups, query=query, path_params=path_params), svc
    )
    return res["statusCode"], json.loads(res["body"])


@pytest.fixture
def wired(monkeypatch):
    """Lambda ledger với `OpsService` dùng DB và DynamoDB giả."""
    db = FakeDb(
        {
            SQL_LIST_TRACES: [row()],
            SQL_GET_TRACE: lambda p: [row()] if p["p_trace_id"] == row()["trace_id"] else [],
            SQL_SUMMARY: [
                {
                    "turns": 42,
                    "turns_rejected": 3,
                    "turns_error": 1,
                    "p50_ms": 4200,
                    "p95_ms": 9800,
                    "tool_calls": 96,
                    "tool_errors": 2,
                    "rule_fails": 3,
                    "input_tokens": 200_000,
                    "output_tokens": 30_000,
                    "model_calls": 114,
                }
            ],
        }
    )
    ddb = FakeDdb({"2026-12-08": [40, 21], "2026-12-10": [9]})
    ops = make_ops(db, ddb)
    built = []
    monkeypatch.setattr(ops_rest, "ops_for", lambda svc: built.append(svc) or ops)
    svc, _, _ = make_service()
    return SimpleNamespace(svc=svc, db=db, ddb=ddb, built=built)


# --- quyền nhóm ops -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/ops/traces", "/ops/traces/abc", "/ops/summary"])
@pytest.mark.parametrize("groups", [None, "[persona-minh]", "[operators ops-team]"])
def test_khong_thuoc_nhom_ops_bi_403_truoc_khi_doc_du_lieu(wired, schema_ok, path, groups):
    status, body = req(wired.svc, path, groups=groups)
    assert status == 403
    schema_ok("ErrorResponse", body)
    assert body["error"]["code"] == "FORBIDDEN"
    assert wired.built == [] and wired.db.calls == [] and wired.ddb.calls == []


def test_nhom_ops_doc_tu_claim_dang_chuoi_hoac_mang(wired):
    assert req(wired.svc, "/ops/summary", groups="[persona-minh ops]")[0] == 200
    ev = http_event("GET", "/ops/summary", sub="sub-ops")
    ev["requestContext"]["authorizer"]["jwt"]["claims"]["cognito:groups"] = ["ops"]
    assert handle_http(ev, wired.svc)["statusCode"] == 200


def test_nhom_ops_van_can_sub(wired):
    status, _ = req(wired.svc, "/ops/summary", sub=None)
    assert status == 401 and wired.db.calls == []


# --- danh sách ------------------------------------------------------------------------------------------------------------
def test_danh_sach_dung_hop_dong_va_mac_dinh_7_ngay(wired, schema_ok):
    status, body = req(wired.svc, "/ops/traces")
    assert status == 200, body
    schema_ok("OpsTraceListResponse", body)
    t = body["traces"][0]
    assert t["user_ref"] == "3f9a0c1d2e4b" and "user_id" not in t and "conversation_id" not in t
    assert (t["tool_calls"], t["tool_errors"], t["rules_failed"]) == (3, 2, 1)
    assert t["est_cost_vnd"] == PRICING.cost_vnd(5200, 640, 1024)
    sql, params = wired.db.calls[0]
    assert sql == SQL_LIST_TRACES
    assert params["p_to"] == NOW and params["p_from"] == NOW - timedelta(days=7)
    assert params["p_limit"] == 50 and params["p_before_created"] is None
    assert "next_cursor" not in body  # ít hơn limit


def test_danh_sach_loc_theo_ngay_y_dinh_loi_va_phan_trang(wired, schema_ok):
    q = {
        "from": "2026-12-01T00:00:00Z",
        "to": "2026-12-10T00:00:00+07:00",
        "intent": "behavior",
        "outcome": "error",
        "min_duration_ms": "3000",
        "limit": "1",
    }
    status, body = req(wired.svc, "/ops/traces", query=q)
    assert status == 200, body
    schema_ok("OpsTraceListResponse", body)
    params = wired.db.calls[-1][1]
    assert params["p_from"] == datetime(2026, 12, 1, tzinfo=UTC)
    assert params["p_to"] == datetime(2026, 12, 9, 17, tzinfo=UTC)
    assert (
        params["p_intent"],
        params["p_outcome"],
        params["p_min_duration"],
        params["p_limit"],
    ) == (
        "behavior",
        "error",
        3000,
        1,
    )
    cursor = body["next_cursor"]
    assert decode_cursor(cursor) == (
        CREATED,
        row()["trace_id"],
    )  # giữ micro giây: không bỏ sót dòng cùng giây
    req(wired.svc, "/ops/traces", query={**q, "cursor": cursor})
    assert wired.db.calls[-1][1]["p_before_created"] == CREATED
    assert wired.db.calls[-1][1]["p_before_trace"] == row()["trace_id"]


@pytest.mark.parametrize(
    "q",
    [
        {"from": "2026-12-01"},
        {"from": "2026-12-01T00:00:00"},
        {"from": "2026-12-10T00:00:00Z", "to": "2026-12-01T00:00:00Z"},
        {"intent": "What-If"},
        {"outcome": "denied"},
        {"min_duration_ms": "-1"},
        {"limit": "0"},
        {"limit": "101"},
        {"cursor": "khong-phai-cursor"},
        {"cursor": encode_cursor(CREATED, "x")[:-2] + "!!"},
    ],
)
def test_tham_so_sai_tra_400(wired, schema_ok, q):
    status, body = req(wired.svc, "/ops/traces", query=q)
    assert status == 400, body
    schema_ok("ErrorResponse", body)
    assert body["error"]["code"] == "PARAMS_INVALID"


# --- chi tiết ------------------------------------------------------------------------------------------------------------
def test_chi_tiet_du_buoc_dung_hop_dong_va_da_che_pii(wired, schema_ok):
    tid = row()["trace_id"]
    status, body = req(wired.svc, f"/ops/traces/{tid}", path_params={"trace_id": tid})
    assert status == 200, body
    schema_ok("OpsTraceDetail", body)
    assert body["pii_masked"] is True
    assert [s["step"] for s in body["steps"]] == [s["step"] for s in STEPS]
    assert body["tool_calls"] == [
        {"target": "ledger", "tool": "get_jar_balances", "ms": 140, "status": "ok"},
        {
            "target": "forecast",
            "tool": "run_scenario",
            "ms": 1450,
            "status": "error",
            "code": "FORECAST_UNAVAILABLE",
        },
        {
            "target": "planner",
            "tool": "check_suitability",
            "ms": 60,
            "status": "denied",
        },  # mã lạ bị bỏ
    ]
    text = json.dumps(body, ensure_ascii=False)
    for secret in ("0912345678", "0123456789012", "Nguyễn Minh Khoa", "Trần Quốc Bảo"):
        assert secret not in text
    assert body["data_used"][0]["value"] == "760.000 ₫"  # số tiền không bị che
    assert body["token_usage"]["cache_read_tokens"] == 1024
    assert body["est_cost_vnd"] == PRICING.cost_vnd(5200, 640, 1024)
    assert wired.db.calls[-1] == (SQL_GET_TRACE, {"p_trace_id": tid})


def test_chi_tiet_khong_co_hoac_sai_dang_tra_404(wired, schema_ok):
    for tid in ("khong-co", "co dau cach"):
        status, body = req(wired.svc, f"/ops/traces/{tid}", path_params={"trace_id": tid})
        assert status == 404
        schema_ok("ErrorResponse", body)
        assert body["error"]["code"] == "TRACE_NOT_FOUND"


def test_chi_tiet_ban_ghi_cu_hoac_hong_van_dung_hop_dong(schema_ok):
    old = row(
        intent=None,
        code="degraded_custom",
        step_timings=[
            {"step": "router", "ms": 10},
            {"step": "tools", "ms": 900},
            {"step": "Hong", "ms": -1},
        ],
        rules_checked=[{"rule_id": "x"}],
        data_used="khong-phai-mang",
        confidence=None,
        blocks_emitted=[{"id": "a b", "type": "options"}],
        token_usage=None,
    )
    d = trace_detail(old, PRICING)
    schema_ok("OpsTraceDetail", d)
    assert "intent" not in d and "code" not in d and "confidence" not in d
    assert d["tool_calls"] == [] and d["data_used"] == [] and d["est_cost_vnd"] == 0
    assert [s["step"] for s in d["steps"]] == ["router", "tools"]


def test_buoc_tool_ghi_truoc_phase5_khong_status_coi_la_ok():
    assert tool_calls_of([{"step": "ledger___get_jar_balances", "ms": 5}]) == [
        {"target": "ledger", "tool": "get_jar_balances", "ms": 5, "status": "ok"}
    ]
    assert tool_calls_of([{"step": "lạ___x", "ms": 5}, {"step": "memory___get", "ms": 5}]) == []


def test_che_pii_giu_nhan_thuong():
    assert mask("Số dư hũ Ăn uống") == "Số dư hũ Ăn uống"
    assert "0912345678" not in mask("Gọi 0912345678")
    assert mask("Chuyển cho Nguyễn Minh Khoa") == "Chuyển cho N***"


# --- tổng hợp ------------------------------------------------------------------------------------------------------------
def test_tong_hop_dung_hop_dong_va_doc_bang_usage(wired, schema_ok):
    status, body = req(wired.svc, "/ops/summary")
    assert status == 200, body
    schema_ok("OpsSummaryResponse", body)
    assert body["latency_ms"] == {"p50": 4200, "p95": 9800}
    assert (body["turns"], body["turns_rejected"], body["turns_error"]) == (42, 3, 1)
    assert body["tool_error_rate"] == round(2 / 96, 4) and body["rule_fails"] == 3
    assert body["est_cost_vnd"] == PRICING.cost_vnd(200_000, 30_000)
    # ngày theo múi giờ của trần (Asia/Ho_Chi_Minh), chỉ ngày có lượt gọi; trần = tổng trần các model đang cấu hình
    assert body["model_calls_by_day"] == [
        {"day": "2026-12-08", "model_calls": 61, "cap": 2400},
        {"day": "2026-12-10", "model_calls": 9, "cap": 2400},
    ]
    days = [
        c["ExpressionAttributeValues"][":d"]["S"]
        for c in wired.ddb.calls
        if "ExclusiveStartKey" not in c
    ]
    assert days == [(date(2026, 12, 3) + timedelta(days=i)).isoformat() for i in range(8)]
    call = wired.ddb.calls[0]
    assert call["TableName"] == "yofina-usage" and call["KeyConditionExpression"] == "#d = :d"
    assert call["ExpressionAttributeNames"] == {"#d": "day", "#c": "count"}
    assert [c for c in wired.db.calls if c[0] == SQL_MODEL_CALLS_BY_DAY] == []


def test_tong_hop_khong_co_luot_khong_co_latency(schema_ok):
    db = FakeDb(
        {
            SQL_SUMMARY: [
                {
                    "turns": 0,
                    "turns_rejected": 0,
                    "turns_error": 0,
                    "p50_ms": None,
                    "p95_ms": None,
                    "tool_calls": 0,
                    "tool_errors": 0,
                    "rule_fails": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "model_calls": 0,
                }
            ]
        }
    )
    body = make_ops(db, FakeDdb()).summary({})
    schema_ok("OpsSummaryResponse", body)
    assert (
        "latency_ms" not in body
        and body["tool_error_rate"] == 0
        and body["model_calls_by_day"] == []
    )


def test_tong_hop_bang_usage_hong_thi_dung_ban_ghi_luot(schema_ok):
    db = FakeDb(
        {
            SQL_SUMMARY: [],
            SQL_MODEL_CALLS_BY_DAY: [
                {"day": date(2026, 12, 9), "turns": 4, "model_calls": 11},
                {"day": date(2026, 12, 10), "turns": 1, "model_calls": 0},
            ],
        }
    )
    body = make_ops(db, FakeDdb(fail=True)).summary({})
    schema_ok("OpsSummaryResponse", body)
    assert body["model_calls_by_day"] == [{"day": "2026-12-09", "model_calls": 11, "cap": 2400}]
    assert make_ops(db, None).summary({})["model_calls_by_day"] == body["model_calls_by_day"]


def test_tong_hop_qua_31_ngay_tra_400(wired):
    status, body = req(
        wired.svc,
        "/ops/summary",
        query={"from": "2026-11-01T00:00:00Z", "to": "2026-12-10T00:00:00Z"},
    )
    assert status == 400 and body["error"]["code"] == "PARAMS_INVALID"
    assert [c for c in wired.db.calls if c[0] == SQL_SUMMARY] == []


def test_usage_reader_phan_trang_cong_moi_model():
    ddb = FakeDdb({"2026-12-08": [40, 21, 3]})
    assert UsageReader("yofina-usage", ddb).calls_on(date(2026, 12, 8)) == 64
    assert len(ddb.calls) == 2


# --- cấu hình -----------------------------------------------------------------------------------------------------------
def test_cau_hinh_tran_lay_tu_llm_defaults_va_gia_ghi_de_duoc():
    llm = load_settings(env={})
    s = OpsSettings.from_config(
        cfg=_Cfg({"YOFINA_OPS_PRICING": json.dumps({"vnd_per_usd": 25000})}), llm_settings=llm
    )
    expected: dict[str, int] = {}
    for specs in llm.roles.values():
        for m in specs:
            expected[m.id] = max(expected.get(m.id, 0), m.daily_cap)
    assert s.model_caps == expected and s.daily_cap_total == sum(expected.values())
    assert s.pricing.vnd_per_usd == 25000 and s.pricing.input_usd_per_mtok == 3
    assert s.budget_timezone == llm.budget_timezone and s.default_range_days == 7


def test_gia_lam_tron_len_so_nguyen_vnd():
    assert PRICING.cost_vnd(0, 0) == 0
    assert PRICING.cost_vnd(1, 0) == 1  # 0,078 ₫ làm tròn lên
    assert PRICING.cost_vnd(1_000_000, 0) == 78_000
    with pytest.raises(ValueError):
        Pricing.from_mapping({"input_usd_per_mtok": 1})


def _Cfg(env):
    from yofina_core.config import Config

    return Config(env=env)


# --- bản ghi lượt (record_turn, get_trace) ----------------------------------------------------------------------------------
RECORD = {
    "trace_id": "t1",
    "outcome": "ok",
    "data_used": [{"label": "Số dư", "tool": "ledger___get_jar_balances"}],
    "rules_checked": [],
    "confidence": {"band": "high", "reasons": ["Số liệu lấy trực tiếp từ sổ cái."]},
    "blocks_emitted": [],
    "token_usage": {"input_tokens": 1, "output_tokens": 1, "model_calls": 1},
    "step_timings": [
        {"step": "router", "ms": 3},
        {
            "step": "ledger___get_jar_balances",
            "ms": 4,
            "status": "error",
            "code": "DATABASE_UNAVAILABLE",
        },
    ],
    "duration_ms": 10,
}


@pytest.mark.parametrize("intent", PHASE5_INTENTS)
def test_record_turn_nhan_y_dinh_phase5(intent):
    assert parse_turn_record({**RECORD, "intent": intent})["intent"] == intent


def test_record_turn_giu_status_va_code_cua_buoc_goi_tool():
    rec = parse_turn_record(RECORD)
    assert rec["step_timings"][1] == {
        "step": "ledger___get_jar_balances",
        "ms": 4,
        "status": "error",
        "code": "DATABASE_UNAVAILABLE",
    }
    for bad in ({"status": "failed"}, {"code": "thuong"}):
        with pytest.raises(YofinaError) as e:
            parse_turn_record({**RECORD, "step_timings": [{"step": "x___y", "ms": 1, **bad}]})
        assert e.value.code == ErrorCode.PARAMS_INVALID
    with pytest.raises(YofinaError):
        parse_turn_record({**RECORD, "intent": "khong_co"})


def test_get_trace_tra_lai_status_cua_buoc_tool(registry):
    data = build_trace_data(
        {**parse_turn_record(RECORD), "created_at": CREATED},
        request_trace_id="t2",
        source_tool="audit___get_trace",
        now=NOW,
        app_date=date(2026, 11, 21),
    )
    assert data["detail"]["step_timings"][1]["status"] == "error"
    v = Draft202012Validator({"$ref": f"{AUDIT_RESULTS_URI}#/$defs/TraceData"}, registry=registry)
    assert not list(v.iter_errors(data))
