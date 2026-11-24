"""Phase 3 trong Lambda ledger: `planner___check_suitability`, `planner___schedule_nudge` (tool GHI qua token), `knowledge___get_fee_schedule`,
`audit___get_trace`, `GET /traces/{id}`, `POST /feedback`, mã lỗi `OFFER_EXPIRED`, và hai target Gateway mới chạy chung Lambda.
Kho dữ liệu là đồ giả trong bộ nhớ (như `ledger_fakes`); SQL thật được kiểm ở tests/integration."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from conftest import BASE, CONTRACTS, load_json
from jsonschema import Draft202012Validator
from ledger_fakes import (
    SETTINGS,
    FakeRepo,
    gateway_context,
    http_event,
    make_service,
)
from yofina_core.blocks import block_to_wire
from yofina_core.confirm import hash_normalized_params
from yofina_core.errors import ErrorCode, YofinaError
from yofina_ledger.gateway_api import handle_gateway
from yofina_ledger.refdata import ReferenceData
from yofina_ledger.repo_wallet import WriteResult
from yofina_ledger.rest_api import handle_http

U = "sub-minh"
V = "sub-lan"
TODAY = date(2026, 11, 21)

FEES = [
    {
        "id": "f1", "product_code": "bnpl_sim", "product_label": "Trả sau (mô phỏng)", "fee_type": "monthly_service_fee",
        "amount_vnd": Decimal(33_000), "rate_percent": None, "period": "per_month", "condition_code": "month_has_transaction",
        "condition_note": None, "source_name": "Biểu phí công khai", "source_url": "https://example.com/fees",
        "effective_from": date(2026, 3, 31), "effective_to": None,
    }
]  # fmt: skip


class Fake3(FakeRepo):
    """`FakeRepo` cộng các hàm phase 3. Dữ liệu tách theo người dùng như RLS."""

    def __init__(self, clock) -> None:
        super().__init__(clock)
        self.obligations: dict[str, list[dict[str, Any]]] = {}
        self.risk: dict[str, str | None] = {}
        self.traces: dict[str, dict[str, dict[str, Any]]] = {}
        self.scenarios: dict[str, dict[str, dict[str, Any]]] = {}
        self.feedback: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        self.nudges: dict[str, dict[str, dict[str, Any]]] = {}

    def add_user(self, uid, offset=-19, jars=None):
        from ledger_fakes import JARS

        super().add_user(uid, offset, jars or JARS)
        for j in self.users[uid]["jars"].values():
            j["kind"] = "spending"
            j["system_role"] = None
            j["goal_vnd"] = None
        self.users[uid]["jars"]["di_lai"]["kind"] = "obligation"
        self.obligations[uid] = []
        self.risk[uid] = "medium"

    def user_row(self, uid):
        if uid not in self.users:
            return None
        return {
            "id": uid, "monthly_salary_vnd": Decimal(9_000_000), "payday_day": 5,
            "risk_tolerance": self.risk[uid], "clock_offset_days": self.users[uid]["offset"],
        }  # fmt: skip

    def list_obligations(self, uid, *, status="active", due_before=None, limit=50):
        return [o for o in self.obligations.get(uid, []) if status == "all" or o["status"] == status]

    def reference_fees(self):
        return FEES

    # --- audit, kịch bản, phản hồi, lời nhắc ---
    def get_trace(self, uid, trace_id):
        return self.traces.get(uid, {}).get(trace_id)

    def record_turn(self, uid, rec):
        """Như SQL thật: mỗi (user, trace) một dòng, ghi lại thì không làm gì."""
        store = self.traces.setdefault(uid, {})
        if rec["trace_id"] in store:
            return False
        store[rec["trace_id"]] = {"created_at": self.clock(), "code": None, **rec}
        return True

    def get_scenario(self, uid, sid):
        return self.scenarios.get(uid, {}).get(sid)

    def upsert_feedback(self, uid, *, trace_id, block_id, option_id, decision, reason, scenario_id):
        known = trace_id in self.traces.get(uid, {})
        if not known:
            raise YofinaError(ErrorCode.TRACE_NOT_FOUND, "Không tìm thấy lượt trả lời này.")
        key = (uid, trace_id, block_id, option_id)
        row = self.feedback.get(key) or {"id": str(uuid.uuid4())}
        row.update(decision=decision, reason=reason, updated_at=self.clock())
        self.feedback[key] = row
        return row

    def get_nudge(self, uid, nudge_id):
        n = self.nudges.get(uid, {}).get(nudge_id)
        return n if n and n["status"] == "scheduled" else None

    def write_nudge(self, uid, *, norm, now, app_date, trace_id, audit, claim, tool):
        store = self.nudges.setdefault(uid, {})
        if norm["op"] == "cancel":
            n = store.get(norm["nudge_id"])
            if not n or n["status"] != "scheduled":
                raise YofinaError(ErrorCode.NUDGE_NOT_FOUND, "Không còn lời nhắc nào để hủy.")
            n["status"] = "cancelled"
            facts = {"op": "cancel", "kind": n["kind"], "fire_on": n["fire_on"], "jar_code": n.get("jar_code"), "note": n.get("note")}
            ref = norm["nudge_id"]
        else:
            ref = str(uuid.uuid4())
            fire = date.fromisoformat(norm["fire_on"])
            store[ref] = {"id": ref, "kind": norm["kind"], "fire_on": fire, "jar_code": norm.get("jar_code"), "note": norm.get("note"), "status": "scheduled"}
            facts = {"op": "create", "kind": norm["kind"], "fire_on": fire, "jar_code": norm.get("jar_code"), "note": norm.get("note")}
        res = WriteResult(tool=tool, reference_id=ref, occurred_at=now, app_date=app_date, facts=facts)
        return res


@pytest.fixture
def svc():
    service, repo, clock = make_service(())
    repo3 = Fake3(clock)
    for u in (U, V):
        repo3.add_user(u)
    service.repo = repo3
    service.ref = ReferenceData(repo3, 300)  # type: ignore[arg-type]
    service.settings = SETTINGS
    return service, repo3, clock


def validate(registry, file, name, obj):
    v = Draft202012Validator({"$ref": f"{BASE}/tools/{file}.results.schema.json#/$defs/{name}"}, registry=registry)
    errs = [f"{list(e.path)}: {e.message}" for e in v.iter_errors(obj)]
    assert not errs, errs


# --- knowledge ---------------------------------------------------------------------------------------
def test_get_fee_schedule_doc_bang_co_cau_truc_kem_nguon_va_ngay_hieu_luc(svc, registry):
    service, _, _ = svc
    res = service.fee_schedule_result(U)
    validate(registry, "knowledge", "GetFeeScheduleResult", res)
    fee = res["data"]["fees"][0]
    assert (fee["fee_type"], fee["amount_vnd"], fee["effective_from"]) == ("monthly_service_fee", 33_000, "2026-03-31")
    assert fee["source_name"] and fee["source_url"].startswith("https://")
    assert res["data"]["product_label"] == "Trả sau (mô phỏng)"


def test_get_fee_schedule_loi(svc):
    service, _, _ = svc
    for kw, code in (
        ({"fee_type": "khong_co"}, ErrorCode.FEE_SCHEDULE_NOT_FOUND),
        ({"product": "san_pham_la"}, ErrorCode.FEE_SCHEDULE_NOT_FOUND),
        ({"fee_type": "Sai Dạng"}, ErrorCode.PARAMS_INVALID),
    ):
        with pytest.raises(YofinaError) as e:
            service.fee_schedule_result(U, **kw)
        assert e.value.code == code


# --- planner: check_suitability ---------------------------------------------------------------------
def test_check_suitability_dau_tu_khi_chua_du_quy_du_phong_bi_chan(svc, registry):
    service, repo, _ = svc
    repo.obligations[U] = [
        {"kind": "rent", "name": "Thuê phòng", "amount_vnd": Decimal(2_000_000), "due_date": date(2026, 12, 6), "cycle": "monthly",
         "due_day": 6, "status": "active", "pay_jar_code": "di_lai", "is_essential": True}
    ]  # fmt: skip
    res = service.check_suitability_result(
        U, proposal={"kind": "proceed", "category": "investment", "amount_vnd": 1_000_000, "risk_level": "high", "origin": "recommendation"}
    )
    validate(registry, "planner", "CheckSuitabilityResult", res)
    v = res["data"]
    assert v["ok"] is False and len(v["checked"]) == 7  # đủ bảy luật
    by = {c["rule_id"]: c["outcome"] for c in v["checked"]}
    assert by["emergency_before_investing"] == "fail" and by["risk_within_tolerance"] == "fail"
    assert by["obligations_first"] == "skipped" and by["no_borrow_to_spend"] == "skipped"
    assert {x["rule_id"] for x in v["violations"]} == {"emergency_before_investing", "risk_within_tolerance"}
    assert all(x["severity"] == "block" for x in v["violations"]) and v["rules_version"].startswith("v")


def test_check_suitability_vay_de_tieu_user_hoi_thi_canh_bao_he_thong_de_xuat_thi_chan(svc):
    service, _, _ = svc
    base = {"kind": "bnpl_purchase", "amount_vnd": 1_200_000, "funding_source": "credit", "is_essential": False}
    user = service.check_suitability_result(U, proposal={**base, "origin": "user_request"})["data"]
    assert user["ok"] is True  # người dùng tự hỏi: cảnh báo (warn), vẫn tính what-if
    assert [(x["rule_id"], x["severity"]) for x in user["violations"]] == [("no_borrow_to_spend", "warn")]
    system = service.check_suitability_result(U, proposal={**base, "origin": "recommendation"})["data"]
    assert system["ok"] is False and system["violations"][0]["severity"] == "block"
    # khoản thiết yếu được phép dùng tín dụng
    ess = service.check_suitability_result(U, proposal={**base, "is_essential": True, "origin": "recommendation"})["data"]
    assert ess["ok"] is True and not ess["violations"]


def test_check_suitability_mac_dinh_mua_sam_la_tuy_y_khi_khong_noi_ro(svc):
    service, _, _ = svc
    out = service.check_suitability_result(U, proposal={"kind": "bnpl_purchase", "amount_vnd": 500_000, "funding_source": "credit", "origin": "recommendation"})["data"]
    assert out["ok"] is False  # chưa nói thiết yếu: mua sắm mặc định là tùy ý


def test_check_suitability_loi_dau_vao(svc):
    service, _, _ = svc
    for proposal, code in (
        ("không phải object", ErrorCode.PARAMS_INVALID),
        ({"amount_vnd": 5}, ErrorCode.PARAMS_INVALID),  # thiếu kind
        ({"kind": "proceed", "trang_la": 1}, ErrorCode.PARAMS_INVALID),
        ({"kind": "proceed", "jar_code": "khong_co"}, ErrorCode.JAR_NOT_FOUND),
    ):
        with pytest.raises(YofinaError) as e:
            service.check_suitability_result(U, proposal=proposal)
        assert e.value.code == code
    with pytest.raises(YofinaError) as e:
        service.check_suitability_result("sub-la", proposal={"kind": "proceed"})
    assert e.value.code == ErrorCode.PROFILE_INCOMPLETE


def test_check_suitability_dung_nghia_vu_da_tinh_cua_kich_ban(svc):
    service, repo, _ = svc
    sid = str(uuid.uuid4())
    repo.scenarios[U] = {sid: {"result": {"obligation_impact": {"cost": {"item_cost_vnd": 6_000_000}}}}}
    data = service.check_suitability_result(
        U, proposal={"kind": "bnpl_purchase", "amount_vnd": 1_000, "funding_source": "credit", "is_essential": True}, scenario_id=sid
    )["data"]
    ratio = next(c for c in data["checked"] if c["rule_id"] == "obligation_to_income")
    assert ratio["outcome"] == "warn"  # 6.000.000 trên lương 9.000.000 vượt 0,36 (số lấy từ kịch bản, không phải 1.000)
    with pytest.raises(YofinaError):
        service.check_suitability_result(U, proposal={"kind": "proceed"}, scenario_id=str(uuid.uuid4()))


@pytest.mark.parametrize(
    ("proposal", "adds"),
    [
        ({"kind": "defer", "funding_source": "jar"}, False),
        ({"kind": "skip"}, False),
        ({"kind": "remind_later"}, False),
        ({"kind": "move_between_jars", "funding_source": "jar", "jar_code": "an_uong", "amount_vnd": 1_000}, False),
        ({"kind": "defer", "funding_source": "credit"}, True),  # nhãn hoãn nhưng vẫn vay: không né được kiểm nghĩa vụ
        ({"kind": "use_credit", "funding_source": "credit"}, True),
        ({"kind": "proceed"}, True),
    ],
)
def test_check_suitability_chi_cong_nghia_vu_kich_ban_khi_de_xuat_them_nghia_vu(svc, proposal, adds):
    """Gốc lỗi verifier_failed của ca Trả sau: có `scenario_id` thì trước đây MỌI đề xuất bị cộng nghĩa vụ của kịch bản. Khớp
    `yofina_agent.whatif.adds_scenario_obligation`."""
    service, repo, _ = svc
    sid = str(uuid.uuid4())
    repo.scenarios[U] = {sid: {"result": {"obligation_impact": {"cost": {"item_cost_vnd": 6_000_000}}}}}
    prop = {**proposal, "is_essential": True, "origin": "user_request"}
    data = service.check_suitability_result(U, proposal=prop, scenario_id=sid)["data"]
    ratio = next(c for c in data["checked"] if c["rule_id"] == "obligation_to_income")
    if adds:
        assert ratio["outcome"] == "warn"  # 6.000.000 của kịch bản trên lương 9.000.000
    else:
        assert ratio["outcome"] == "skipped" and data["ok"] is True


# --- audit: get_trace ---------------------------------------------------------------------------------
def turn_row(**kw):
    row = {
        "trace_id": "trace-abc", "created_at": datetime(2026, 12, 10, 3, 0, tzinfo=__import__("datetime").UTC), "conversation_id": "c1",
        "intent": "what_if", "outcome": "ok", "code": None,
        "data_used": [{"label": "Dự báo hũ Ăn uống", "tool": "forecast___get_forecast", "value": "cạn 23/11"}],
        "rules_checked": [{"rule_id": "obligations_first", "label": "Nghĩa vụ trước", "outcome": "pass"}],
        "confidence": {"band": "medium", "reasons": ["47 ngày lịch sử"]},
        "blocks_emitted": [{"id": "forecast_timeline:t:an_uong", "type": "forecast_timeline"}],
        "token_usage": {"input_tokens": 100, "output_tokens": 20, "model_calls": 3},
        "step_timings": [{"step": "router", "ms": 300}], "duration_ms": 4200,
    }  # fmt: skip
    row.update(kw)
    return row


def test_trace_chi_cua_chinh_nguoi_dung_nguoi_khac_va_khong_co_deu_404(svc, registry):
    service, repo, _ = svc
    repo.traces[U] = {"trace-abc": turn_row()}
    res = service.trace_result(U, "trace-abc")
    validate(registry, "audit", "GetTraceResult", res)
    data = res["data"]
    assert data["explain"]["type"] == "explain" and data["explain"]["data"]["subject_trace_id"] == "trace-abc"
    assert data["explain"]["data"]["confidence"]["band"] == "medium"
    assert data["detail"]["intent"] == "what_if" and data["detail"]["duration_ms"] == 4200
    for who, tid in ((V, "trace-abc"), (U, "khong-co"), (U, "sai dạng!"), (U, "x" * 80)):
        with pytest.raises(YofinaError) as e:
            service.trace_data(who, tid, source_tool="t")
        assert e.value.code == ErrorCode.TRACE_NOT_FOUND  # cùng một mã, không lộ sự tồn tại


def turn_args(**kw):
    """Tham số `audit___record_turn` đúng như agent gửi (không có created_at, không có user_id)."""
    args = {k: v for k, v in turn_row().items() if k not in ("created_at", "code")}
    args.update(kw)
    return args


def test_record_turn_ghi_roi_get_trace_va_feedback_chap_nhan_chi_cua_chinh_chu(svc, registry):
    service, repo, _ = svc
    res = handle_gateway({"user_id": U, **turn_args()}, gateway_context("audit___record_turn"), service)
    validate(registry, "audit", "RecordTurnResult", res)
    assert res["status"] == "OK" and res["data"] == {"trace_id": "trace-abc", "recorded": True}
    # vòng đầy đủ: đọc lại bằng tool và REST, rồi phản hồi
    got = handle_gateway({"user_id": U, "trace_id": "trace-abc"}, gateway_context("audit___get_trace"), service)
    validate(registry, "audit", "GetTraceResult", got)
    assert got["status"] == "OK" and got["data"]["detail"]["intent"] == "what_if"
    rest = handle_http(http_event("GET", "/traces/trace-abc", sub=U, path_params={"trace_id": "trace-abc"}), service)
    assert rest["statusCode"] == 200
    body = {"trace_id": "trace-abc", "option_id": "defer_payday", "decision": "accepted"}
    assert handle_http(http_event("POST", "/feedback", sub=U, body=body), service)["statusCode"] == 200
    # người khác: 404 cho cả đọc lẫn phản hồi
    other = handle_http(http_event("GET", "/traces/trace-abc", sub=V, path_params={"trace_id": "trace-abc"}), service)
    assert other["statusCode"] == 404
    assert handle_http(http_event("POST", "/feedback", sub=V, body=body), service)["statusCode"] == 404
    assert "trace-abc" not in repo.traces.get(V, {})


def test_record_turn_ghi_lai_cung_trace_khong_ghi_them(svc):
    service, repo, _ = svc
    assert service.record_turn_result(U, **turn_args())["data"]["recorded"] is True
    again = service.record_turn_result(U, **turn_args(duration_ms=1))
    assert again["status"] == "OK" and again["data"]["recorded"] is False
    assert repo.traces[U]["trace-abc"]["duration_ms"] == 4200  # bản đầu giữ nguyên (chỉ thêm)


def test_record_turn_danh_tinh_chi_tu_user_id_cua_interceptor_khong_tu_than(svc):
    service, repo, _ = svc
    # thân mang user_id khác không có đường nào tới DB: tham số lạ bị bỏ, người ghi là user_id của sự kiện (đã bị interceptor ghi đè)
    ev = {"user_id": U, **turn_args(), "conversation_id": "c9"}
    handle_gateway({**ev, "owner": V}, gateway_context("audit___record_turn"), service)
    assert "trace-abc" in repo.traces[U] and "trace-abc" not in repo.traces.get(V, {})
    no_user = handle_gateway(turn_args(), gateway_context("audit___record_turn"), service)
    assert no_user["status"] == "ERROR" and no_user["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize(
    "patch",
    [
        {"trace_id": "sai dạng!"},
        {"trace_id": "x" * 65},
        {"outcome": "weird"},
        {"intent": "hack"},
        {"data_used": []},
        {"data_used": [{"label": "a"}]},
        {"confidence": {"band": "super", "reasons": ["x"]}},
        {"rules_checked": [{"rule_id": "r", "label": "l", "outcome": "maybe"}]},
        {"token_usage": {"input_tokens": -1, "output_tokens": 0, "model_calls": 0}},
        {"duration_ms": -5},
        {"blocks_emitted": [{"id": "b", "type": "Sai Loai"}]},
    ],
)
def test_record_turn_tham_so_sai_la_params_invalid_va_khong_ghi(svc, patch):
    service, repo, _ = svc
    res = handle_gateway({"user_id": U, **turn_args(**patch)}, gateway_context("audit___record_turn"), service)
    assert res["status"] == "ERROR" and res["code"] == "PARAMS_INVALID"
    assert not repo.traces.get(U)


def test_record_turn_nhan_dung_ban_ghi_ma_agent_dung(svc):
    """Hợp đồng agent -> backend: bản ghi do `trace.build_record` của agent dựng được ghi và đọc lại được."""
    from yofina_agent import trace as agent_trace

    from yofina_core import blocks as B

    service, _, _ = svc
    rec = agent_trace.build_record(
        trace_id="trace-agent-1", conversation_id="conv-1", intent="move", outcome="ok", code=None,
        outcomes=[], suitability=[], extra_rules=[B.RuleCheck(rule_id="obligations_first", label="Nghĩa vụ trước", outcome="pass")],
        bases=[], blocks=[{"id": "clarify:t", "type": "clarify"}], usage_by_model=[{"inputTokens": 5, "outputTokens": 2}],
        model_calls=1, steps=[("router", 120), ("router", 30)], duration_ms=900,
    )  # fmt: skip
    assert service.record_turn_result(U, **rec)["data"]["recorded"] is True
    assert service.trace_data(U, "trace-agent-1", source_tool="t")["detail"]["duration_ms"] == 900


def test_trace_thieu_phan_nao_thi_dung_gia_tri_trung_tinh_khong_bia(svc, registry):
    service, repo, _ = svc
    repo.traces[U] = {"t1": turn_row(trace_id="t1", data_used=None, confidence=None, rules_checked=None, token_usage=None, step_timings=None, duration_ms=None, intent=None, outcome="rejected")}
    res = service.trace_result(U, "t1")
    validate(registry, "audit", "GetTraceResult", res)
    d = res["data"]
    assert d["explain"]["data"]["data_used"][0]["tool"] == "none"
    assert d["explain"]["data"]["confidence"]["band"] == "low"
    assert d["detail"]["outcome"] == "rejected" and "intent" not in d["detail"]


def test_rest_get_traces_va_404(svc):
    service, repo, _ = svc
    repo.traces[U] = {"trace-abc": turn_row()}
    ok = handle_http(http_event("GET", "/traces/trace-abc", sub=U, path_params={"trace_id": "trace-abc"}), service)
    assert ok["statusCode"] == 200 and json.loads(ok["body"])["trace_id"] == "trace-abc"
    other = handle_http(http_event("GET", "/traces/trace-abc", sub=V, path_params={"trace_id": "trace-abc"}), service)
    assert other["statusCode"] == 404 and json.loads(other["body"])["error"]["code"] == "TRACE_NOT_FOUND"
    anon = handle_http(http_event("GET", "/traces/trace-abc", sub=None), service)
    assert anon["statusCode"] == 401


# --- audit: feedback ----------------------------------------------------------------------------------
def test_feedback_idempotent_theo_trace_khoi_phuong_an_va_doi_y(svc):
    service, repo, _ = svc
    repo.traces[U] = {"trace-abc": turn_row()}
    body = {"trace_id": "trace-abc", "block_id": "options:trace-abc", "option_id": "defer_payday", "decision": "accepted"}
    first = service.feedback_response(U, body)
    again = service.feedback_response(U, {**body, "decision": "rejected", "reason": "để sau"})
    assert first["feedback_id"] == again["feedback_id"] and again["decision"] == "rejected"
    assert len(repo.feedback) == 1 and first["recorded_at"].endswith("Z")


@pytest.mark.parametrize(
    "patch",
    [
        {"decision": "maybe"}, {"option_id": "Sai Dạng"}, {"trace_id": "sai dạng"}, {"block_id": "!!"},
        {"scenario_id": "khong-phai-uuid"}, {"reason": ""}, {"reason": "x" * 201}, {"option_id": None},
    ],
)  # fmt: skip
def test_feedback_tham_so_sai(svc, patch):
    service, repo, _ = svc
    repo.traces[U] = {"trace-abc": turn_row()}
    body = {"trace_id": "trace-abc", "option_id": "defer_payday", "decision": "accepted", **patch}
    with pytest.raises(YofinaError) as e:
        service.feedback_response(U, body)
    assert e.value.code == ErrorCode.PARAMS_INVALID


def test_feedback_cho_trace_cua_nguoi_khac_la_404_va_rest_khong_can_token(svc):
    service, repo, _ = svc
    repo.traces[U] = {"trace-abc": turn_row()}
    body = {"trace_id": "trace-abc", "option_id": "defer_payday", "decision": "accepted"}
    res = handle_http(http_event("POST", "/feedback", sub=V, body=body), service)
    assert res["statusCode"] == 404 and json.loads(res["body"])["error"]["code"] == "TRACE_NOT_FOUND"
    ok = handle_http(http_event("POST", "/feedback", sub=U, body=body), service)
    assert ok["statusCode"] == 200 and set(json.loads(ok["body"])) == {"feedback_id", "decision", "recorded_at"}


# --- planner: schedule_nudge (tool ghi qua token) -------------------------------------------------------
NUDGE = {"op": "create", "kind": "purchase_review", "fire_on": "2026-11-28", "note": "xem lại tai nghe"}


def test_schedule_nudge_khong_token_thi_chi_xem_truoc_khong_ghi(svc, registry):
    service, repo, _ = svc
    res = handle_gateway({"user_id": U, **NUDGE}, gateway_context("planner___schedule_nudge"), service)
    validate(registry, "planner", "ScheduleNudgeResult", res)
    assert res["status"] == "NEEDS_CONFIRMATION" and res["data"]["tool"] == "schedule_nudge"
    assert res["data"]["params"] == NUDGE and any(c["label"] == "Ngày nhắc" and c["after"] == "28/11" for c in res["data"]["changes"])
    assert not repo.nudges.get(U)


def test_schedule_nudge_co_token_ghi_roi_hoan_tac_bang_cancel_qua_cung_luong_token(svc, registry):
    service, repo, _ = svc
    issued = service.issue_confirmation(U, tool="schedule_nudge", params=NUDGE, client_params_hash=None, trace_id="t1")
    res = handle_gateway({"user_id": U, **NUDGE, "confirm_token": issued.token}, gateway_context("planner___schedule_nudge"), service)
    validate(registry, "planner", "ScheduleNudgeResult", res)
    assert res["status"] == "OK" and res["data"]["tool"] == "schedule_nudge"
    nudge_id = res["data"]["reference_id"]
    assert repo.nudges[U][nudge_id]["status"] == "scheduled" and res["data"]["summary"] == "Đã đặt nhắc ngày 28/11"
    # token dùng một lần
    again = handle_gateway({"user_id": U, **NUDGE, "confirm_token": issued.token}, gateway_context("planner___schedule_nudge"), service)
    assert again["status"] == "ERROR" and again["code"] == "TOKEN_REUSED"
    # Hoàn tác = cancel với nudge_id = reference_id, cũng qua token
    cancel = {"op": "cancel", "nudge_id": nudge_id}
    prev = handle_gateway({"user_id": U, **cancel}, gateway_context("planner___schedule_nudge"), service)
    assert prev["status"] == "NEEDS_CONFIRMATION" and prev["data"]["params"] == cancel
    tok = service.issue_confirmation(U, tool="schedule_nudge", params=cancel, client_params_hash=None, trace_id="t2")
    done = handle_gateway({"user_id": U, **cancel, "confirm_token": tok.token}, gateway_context("planner___schedule_nudge"), service)
    assert done["status"] == "OK" and done["data"]["summary"] == "Đã hủy lời nhắc"
    assert repo.nudges[U][nudge_id]["status"] == "cancelled"
    gone = handle_gateway({"user_id": U, **cancel}, gateway_context("planner___schedule_nudge"), service)
    assert gone["status"] == "ERROR" and gone["code"] == "NUDGE_NOT_FOUND"


def test_schedule_nudge_token_cua_tool_khac_hay_tham_so_khac_bi_tu_choi(svc):
    service, _, _ = svc
    tok = service.issue_confirmation(U, tool="schedule_nudge", params=NUDGE, client_params_hash=None, trace_id="t")
    changed = {**NUDGE, "fire_on": "2026-11-29"}
    res = handle_gateway({"user_id": U, **changed, "confirm_token": tok.token}, gateway_context("planner___schedule_nudge"), service)
    assert res["status"] == "ERROR" and res["code"] == "PARAMS_MISMATCH"
    other = service.confirm.issue(U, "move_between_jars", {"from_jar": "an_uong", "to_jar": "giai_tri", "amount_vnd": 1000})
    res = handle_gateway({"user_id": U, **NUDGE, "confirm_token": other.token}, gateway_context("planner___schedule_nudge"), service)
    assert res["status"] == "ERROR" and res["code"] in ("TOKEN_INVALID", "PARAMS_MISMATCH")


@pytest.mark.parametrize(
    ("patch", "code"),
    [
        ({"fire_on": "2026-11-21"}, "PARAMS_INVALID"),  # không sau hôm nay mô phỏng
        ({"fire_on": "2026-11-01"}, "PARAMS_INVALID"),
        ({"kind": "tu_nghi"}, "PARAMS_INVALID"),
        ({"jar_code": "khong_co"}, "JAR_NOT_FOUND"),
        ({"note": "x" * 121}, "PARAMS_INVALID"),
    ],
)
def test_schedule_nudge_tham_so_sai(svc, patch, code):
    service, _, _ = svc
    res = handle_gateway({"user_id": U, **NUDGE, **patch}, gateway_context("planner___schedule_nudge"), service)
    assert res["status"] == "ERROR" and res["code"] == code


def test_schedule_nudge_qua_rest_confirmations_va_actions(svc):
    service, repo, _ = svc
    conf = handle_http(http_event("POST", "/confirmations", sub=U, body={"tool": "schedule_nudge", "params": NUDGE}), service)
    assert conf["statusCode"] == 200
    body = json.loads(conf["body"])
    assert body["preview"]["summary"].startswith("Nhắc bạn ngày 28/11")
    act = handle_http(http_event("POST", "/actions", sub=U, body={"tool": "schedule_nudge", "params": body["params"], "confirm_token": body["confirm_token"]}), service)
    assert act["statusCode"] == 200 and json.loads(act["body"])["type"] == "receipt_action"
    assert len(repo.nudges[U]) == 1
    # lời nhắc của người này không hủy được bằng tài khoản khác
    nid = next(iter(repo.nudges[U]))
    cancel = {"op": "cancel", "nudge_id": nid}
    other = handle_http(http_event("POST", "/confirmations", sub=V, body={"tool": "schedule_nudge", "params": cancel}), service)
    assert other["statusCode"] == 404 and json.loads(other["body"])["error"]["code"] == "NUDGE_NOT_FOUND"


# --- OFFER_EXPIRED tách khỏi TOKEN_EXPIRED -------------------------------------------------------------------
def test_de_nghi_qua_han_la_offer_expired_410_khac_token_expired(svc):
    service, repo, clock = svc
    block = service.prepare_move(U, {"from_jar": "an_uong", "to_jar": "giai_tri", "amount_vnd": 50_000}, trace_id="t1", source_tool="ledger___move_between_jars")
    repo.save_turn(U, conversation_id="c1", trace_id="t1", user_text="x", assistant_text="y", blocks=[(0, block_to_wire(block))])
    clock.advance(SETTINGS.offer_ttl_seconds + 5)
    res = handle_http(
        http_event(
            "POST", "/confirmations", sub=U,
            body={"tool": "move_between_jars", "params": {"from_jar": "an_uong", "to_jar": "giai_tri", "amount_vnd": 50_000}, "conversation_id": "c1", "confirm_block_id": block.id},
        ),
        service,
    )
    assert res["statusCode"] == 410 and json.loads(res["body"])["error"]["code"] == "OFFER_EXPIRED"
    assert ErrorCode.OFFER_EXPIRED != ErrorCode.TOKEN_EXPIRED


# --- cùng Lambda, nhiều target -------------------------------------------------------------------------------------
def test_ba_target_moi_dung_dung_ten_tool_theo_hop_dong(svc):
    service, repo, _ = svc
    repo.traces[U] = {"trace-abc": turn_row()}
    cases = {
        "knowledge___get_fee_schedule": {},
        "planner___check_suitability": {"proposal": {"kind": "proceed"}},
        "audit___get_trace": {"trace_id": "trace-abc"},
    }
    for name, args in cases.items():
        res = handle_gateway({"user_id": U, **args}, gateway_context(name), service)
        assert res["status"] == "OK", (name, res)
    res = handle_gateway({"user_id": U}, gateway_context("audit___get_trace"), service)
    assert res["status"] == "ERROR" and res["code"] == "PARAMS_INVALID"


def test_tool_doc_moi_bo_qua_tham_so_la_va_user_id_cua_nguoi_khac_khong_doi_chu(svc):
    service, repo, _ = svc
    repo.traces[V] = {"trace-abc": turn_row()}
    # interceptor đã ghi đè user_id bằng sub của JWT; kể cả khi client gửi trace của người khác thì đọc theo user_id đã ghi đè
    res = handle_gateway({"user_id": U, "trace_id": "trace-abc", "bay": 1}, gateway_context("audit___get_trace"), service)
    assert res["status"] == "ERROR" and res["code"] == "TRACE_NOT_FOUND"


def test_hash_tham_so_nudge_khong_phu_thuoc_thu_tu_khoa(svc):
    shuffled = dict(reversed(list(NUDGE.items())))
    from yofina_core.params import normalize_params

    assert hash_normalized_params("schedule_nudge", normalize_params("schedule_nudge", NUDGE)) == hash_normalized_params(
        "schedule_nudge", normalize_params("schedule_nudge", shuffled)
    )
    assert CONTRACTS.exists() and load_json(CONTRACTS / "tools" / "planner.json")
    assert TODAY + timedelta(days=7) == date(2026, 11, 28)
