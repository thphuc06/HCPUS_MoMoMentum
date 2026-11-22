"""Phần thuần của ví phase 2 trong ledger: thẻ chủ động, chuyển đổi dòng DB, sự kiện (đúng JSON Schema), publisher, bảng tra,
cấu hình, luật Cedar khớp hợp đồng tool, và `cancelled` trong hợp đồng. SQL thật được kiểm ở tests/local_pg và tests/integration."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from conftest import BASE, CONTRACTS, REPO, load_json
from jsonschema import Draft202012Validator

from yofina_core.blocks import parse_block
from yofina_core.config import Config
from yofina_core.errors import YofinaError
from yofina_ledger import convert, events
from yofina_ledger.gateway_api import _ARG_KEYS
from yofina_ledger.proactive import choose_proactive_card
from yofina_ledger.refdata import ReferenceData
from yofina_ledger.settings import LedgerSettings
from yofina_ledger.wallet_reads import decode_cursor, encode_cursor

NOW = datetime(2026, 12, 10, 3, 0, tzinfo=UTC)
TODAY = date(2026, 11, 21)
UUID1 = "6f1e2d3c-4b5a-4968-8777-665544332211"
UUID2 = "7e1f3a90-2c4b-4d6e-8f01-a3b5c7d9e0f2"


# --- thẻ chủ động ----------------------------------------------------------------------------------------
def card(**kw):
    base = dict(
        today=TODAY, jars=[], forecasts={}, salary_event=None, obligations_due=[], review_count=0,
        obligation_days=3, trace_id="t" * 8, as_of=NOW, source_tool="rest:GET /overview",
    )  # fmt: skip
    base.update(kw)
    return choose_proactive_card(**base)


def jar(code, name, balance):
    return {"code": code, "name": name, "balance_vnd": balance}


def fc(status, runout=None, p=None, show=False, initial=False, days_to=14, history=47):
    return {
        "status": status, "runout_date": runout, "p_shortfall": p, "show_probability": show, "payday_date": date(2026, 12, 5),
        "days_to_payday": days_to, "is_initial_estimate": initial, "history_days": history,
    }  # fmt: skip


def test_the_chu_dong_khong_co_viec_thi_none():
    assert card(jars=[jar("a", "A", 1)], forecasts={"a": fc("ok")}) is None


def test_luong_cho_xac_nhan_thang_moi_thu():
    ev = {
        "status": "pending",
        "received_on": date(2026, 12, 5),
        "amount_vnd": 9_000_000,
        "deviation_percent": Decimal("0.00"),
    }
    c = card(
        salary_event=ev, jars=[jar("a", "A", 1)], forecasts={"a": fc("short", date(2026, 11, 23))},
        review_count=3, obligations_due=[{"name": "x", "amount_vnd": 1, "due_date": TODAY, "id": "1"}],
    )  # fmt: skip
    assert c.data.kind == "salary_pending" and c.data.actions[0].kind == "confirm_salary"
    assert "9.000.000" in c.data.reason and "đúng số đã khai" in c.data.reason
    parse_block(json.loads(c.model_dump_json()))


def test_hu_hut_co_ngay_can_som_nhat_va_xac_suat_chi_hien_khi_duoc_phep():
    jars = [jar("an_uong", "Ăn uống", 380_000), jar("giai_tri", "Giải trí", 760_000)]
    f = {
        "an_uong": fc("short", date(2026, 11, 23), 0.71, True),
        "giai_tri": fc("short", date(2026, 11, 29), 0.5, True),
    }
    c = card(jars=jars, forecasts=f)
    assert (
        c.data.kind == "runout_warning"
        and c.data.status == "short"
        and c.data.jar_code == "an_uong"
    )
    assert c.data.title == "Hũ Ăn uống dự kiến cạn ngày 23/11"
    assert (
        c.data.reason
        == "Còn 380.000 ₫, cạn xong còn 12 ngày nữa mới tới kỳ lương 05/12. Xác suất hụt khoảng 71%."
    )
    assert [a.kind for a in c.data.actions] == ["open_forecast", "ask_why", "snooze", "mute_kind"]
    assert c.data.actions[1].prompt == "Vì sao hũ Ăn uống sắp cạn?"
    f["an_uong"] = fc(
        "short", date(2026, 11, 23), 0.71, False
    )  # chưa đủ tin cậy: không phát phần trăm
    assert "Xác suất" not in card(jars=jars, forecasts=f).data.reason


def test_hu_sat_va_nghia_vu_den_han_va_xem_lai_va_du_lieu_it_theo_thu_tu():
    jars = [jar("hoa_don", "Hóa đơn", 450_000), jar("nghia_vu", "Nghĩa vụ", 1_000_000)]
    ob = {
        "id": "x",
        "name": "Tiền điện",
        "amount_vnd": 375_000,
        "due_date": date(2026, 11, 23),
        "status": "active",
        "pay_jar_code": "hoa_don",
    }
    tight = card(
        jars=jars, forecasts={"hoa_don": fc("tight")}, obligations_due=[ob], review_count=2
    )
    assert (
        tight.data.kind == "runout_warning"
        and tight.data.status == "tight"
        and "sát" in tight.data.title
    )
    due = card(jars=jars, forecasts={"hoa_don": fc("ok")}, obligations_due=[ob], review_count=2)
    assert due.data.kind == "obligation_due" and due.data.jar_code == "hoa_don"
    assert (
        due.data.title == "Tiền điện đến hạn ngày 23/11"
        and due.data.reason == "Cần 375.000 ₫, trả từ hũ Hóa đơn."
    )
    far = {**ob, "due_date": date(2026, 12, 20)}
    rev = card(jars=jars, forecasts={"hoa_don": fc("ok")}, obligations_due=[far], review_count=2)
    assert rev.data.kind == "review_needed" and rev.data.title == "2 giao dịch cần bạn xem lại"
    low = card(jars=jars, forecasts={"hoa_don": fc("ok", initial=True, history=18)})
    assert low.data.kind == "low_data" and "18 ngày" in low.data.reason


# --- chuyển đổi dòng DB sang JSON hợp đồng ---------------------------------------------------------------
@pytest.fixture(scope="module")
def results_validator(registry):
    def check(name, instance):
        v = Draft202012Validator(
            {"$ref": f"{BASE}/tools/ledger.results.schema.json#/$defs/{name}"}, registry=registry
        )
        errors = [f"{list(e.path)}: {e.message}" for e in v.iter_errors(instance)]
        assert not errors, errors

    return check


def test_chuyen_doi_nhan_ca_kieu_python_va_kieu_jsonb(results_validator):
    py = {
        "id": UUID1, "occurred_at": NOW, "app_date": TODAY, "kind": "expense", "jar_code": "an_uong", "amount_vnd": Decimal("-45000"),
        "merchant": "Quán", "note": None, "transfer_id": None, "tx_type": "food_drink", "funding_source": "jar", "payee_id": None,
        "payee_name": None, "obligation_id": None, "needs_review": False,
    }  # fmt: skip
    js = {
        **py,
        "occurred_at": "2026-12-10T03:00:00.123456+00:00",
        "app_date": "2026-11-21",
        "amount_vnd": -45000,
    }
    a, b = convert.tx_json(py), convert.tx_json(js)
    assert a == b and "note" not in a and "payee_id" not in a and a["jar"] == "an_uong"
    assert a["occurred_at"] == "2026-12-10T03:00:00Z" and a["needs_review"] is False
    results_validator("Transaction", a)
    results_validator(
        "Transaction",
        convert.tx_json({**py, "jar_code": None, "payee_id": UUID2, "payee_name": "Huy"}),
    )


def test_chuyen_doi_nghia_vu_va_han_muc(results_validator):
    row = {
        "id": UUID1, "kind": "bill", "name": "Tiền điện", "amount_vnd": Decimal("375000"), "amount_min_vnd": Decimal("300000"),
        "amount_max_vnd": Decimal("450000"), "fee_vnd": Decimal(0), "principal_vnd": None, "due_date": date(2026, 11, 26),
        "cycle": "monthly", "due_day": 26, "status": "active", "pay_jar_code": "hoa_don", "is_essential": True, "source": "declared",
        "paid_at": None,
    }  # fmt: skip
    o = convert.obligation_json(row)
    assert (
        o["pay_jar"] == "hoa_don"
        and "principal_vnd" not in o
        and "paid_at" not in o
        and o["due_day"] == 26
    )
    results_validator("Obligation", o)
    line = convert.credit_line_json(
        {
            "product_code": "bnpl_sim",
            "limit_vnd": Decimal(5_000_000),
            "outstanding_vnd": Decimal(967_000),
            "due_day": 5,
            "status": "active",
        },
        "Trả sau (mô phỏng)",
    )
    assert line["available_vnd"] == 4_033_000
    results_validator("CreditLine", line)
    ev = convert.salary_event_json(
        {"id": UUID1, "period_date": date(2026, 12, 5), "received_on": date(2026, 12, 5), "expected_vnd": Decimal(9_000_000),
         "amount_vnd": Decimal(10_500_000), "deviation_percent": Decimal("16.67"), "ask_update_salary": True, "status": "pending", "confirmed_at": None}
    )  # fmt: skip
    results_validator("SalaryEvent", ev)
    assert (
        convert.percent(Decimal("30.00")) == 30
        and convert.percent(33.33) == 33.33
        and convert.vnd(30.0) == 30
    )


def test_con_tro_trang_ma_hoa_khu_hoi_va_tu_choi_rac():
    cur = encode_cursor(NOW, UUID1)
    assert decode_cursor(cur) == (NOW, UUID1) and "=" not in cur
    for bad in ("", "%%%", "e30", "x" * 300, encode_cursor(NOW, "khong-phai-uuid")):
        with pytest.raises(YofinaError):
            decode_cursor(bad)


# --- sự kiện: đúng JSON Schema, không PII ----------------------------------------------------------------
@pytest.fixture(scope="module")
def event_validator(registry):
    def check(ev: events.Event):
        v = Draft202012Validator(
            {"$ref": f"{BASE}/events/{ev.detail_type}.schema.json"}, registry=registry
        )
        errors = [f"{list(e.path)}: {e.message}" for e in v.iter_errors(ev.detail)]
        assert not errors, errors
        text = json.dumps(ev.detail, ensure_ascii=False)
        assert "confirm_token" not in text and "@" not in text

    return check


def test_su_kien_ledger_hop_le(event_validator):
    common = dict(user_id="sub-1", trace_id="a" * 32, occurred_at=NOW, app_date=TODAY)
    tr = events.transaction_recorded(
        transaction_id=UUID1, kind="expense", tx_type="food_drink", funding_source="jar", amount_vnd=200_000,
        jar_codes=["an_uong"], deltas={"an_uong": -200_000}, balances={"an_uong": 180_000}, payee_id=UUID2,
        needs_classification=False, **common,
    )  # fmt: skip
    event_validator(tr)
    assert (
        tr.detail["event_id"] == tr.detail["transaction_id"] == UUID1
        and "needs_classification" not in tr.detail
    )
    credit = events.transaction_recorded(
        transaction_id=UUID1, kind="expense", tx_type="other_expense", funding_source="credit", amount_vnd=300_000,
        jar_codes=["giai_tri"], deltas={}, balances={}, **common,
    )  # fmt: skip
    event_validator(credit)
    assert credit.detail["effects"] == []
    event_validator(
        events.salary_confirmed(
            salary_event_id=UUID1,
            period_date=date(2026, 12, 5),
            decision="split",
            amount_vnd=9_000_000,
            salary_updated=False,
            deltas={"tien_vao_khac": -9_000_000, "an_uong": 2_700_000},
            balances={"tien_vao_khac": 350_000, "an_uong": 3_080_000},
            **common,
        )
    )
    keep = events.salary_confirmed(
        salary_event_id=UUID1, period_date=date(2026, 12, 5), decision="keep_as_other", amount_vnd=9_000_000, salary_updated=False,
        deltas={}, balances={}, **common,
    )  # fmt: skip
    event_validator(keep)
    assert keep.detail["jar_codes"] == []
    ob = events.obligation_changed(
        obligation_id=UUID1,
        change="created",
        kind="bnpl",
        pay_jar="nghia_vu",
        due_date=date(2026, 12, 5),
        **common,
    )
    event_validator(ob)
    assert (
        ob.detail["event_id"]
        != events.obligation_changed(
            obligation_id=UUID1, change="created", kind="bnpl", **common
        ).detail["event_id"]
    )
    event_validator(events.profile_updated(fields=["onboarding", "salary", "salary"], **common))
    assert events.profile_updated(fields=["salary", "salary"], **common).detail["fields"] == [
        "salary"
    ]


class FakeBus:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def put_events(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return self.response or {
            "FailedEntryCount": 0,
            "Entries": [{"EventId": "e"} for _ in kw["Entries"]],
        }


def sample_event():
    return events.profile_updated(
        user_id="u", trace_id=None, occurred_at=NOW, app_date=TODAY, fields=["salary"]
    )


def test_publisher_phat_dung_source_detail_type_va_bus(caplog):
    bus = FakeBus()
    pub = events.EventPublisher("yofina-bus", bus)
    assert pub.publish([sample_event()], trace_id="t") is True
    (entry,) = bus.calls[0]["Entries"]
    assert (
        entry["EventBusName"] == "yofina-bus"
        and entry["Source"] == "yofina.ledger"
        and entry["DetailType"] == "profile.updated"
    )
    assert json.loads(entry["Detail"])["fields"] == ["salary"]


def test_publisher_loi_khong_nem_ra_ngoai_va_ghi_metric_emf(caplog):
    caplog.set_level("INFO")
    assert (
        events.EventPublisher("b", FakeBus(error=RuntimeError("mạng đứt"))).publish(
            [sample_event()]
        )
        is False
    )
    partial = FakeBus({"FailedEntryCount": 1, "Entries": [{"ErrorCode": "ThrottlingException"}]})
    assert events.EventPublisher("b", partial).publish([sample_event()]) is False
    lines = [json.loads(r.getMessage()) for r in caplog.records if r.name == "yofina.ledger.events"]
    failed = [x for x in lines if x.get("EventPublishFailed") == 1]
    assert len(failed) == 2 and failed[0]["DetailType"] == "profile.updated"
    metric = failed[0]["_aws"]["CloudWatchMetrics"][0]
    assert (
        metric["Namespace"] == "Yofina/Ledger"
        and metric["Metrics"][0]["Name"] == "EventPublishFailed"
    )
    assert (
        events.EventPublisher("", FakeBus()).publish([sample_event()]) is False
    )  # chưa có bus: chỉ log
    assert events.EventPublisher("b", FakeBus()).publish([]) is True


# --- bảng tra ---------------------------------------------------------------------------------------------
class FakeRef:
    def __init__(self):
        self.loads = 0
        self.fees = [
            {"id": UUID1, "product_code": "bnpl_sim", "product_label": "Trả sau (mô phỏng)", "fee_type": "monthly_service_fee", "amount_vnd": Decimal(33_000),
             "rate_percent": None, "period": "per_month", "condition_code": "month_has_transaction", "condition_note": None, "source_name": "n",
             "source_url": "https://x", "effective_from": date(2026, 3, 31), "effective_to": None},
            {"id": UUID2, "product_code": "bnpl_sim", "product_label": "Trả sau (mô phỏng)", "fee_type": "monthly_service_fee", "amount_vnd": Decimal(40_000),
             "rate_percent": None, "period": "per_month", "condition_code": "month_has_transaction", "condition_note": None, "source_name": "n",
             "source_url": "https://x", "effective_from": date(2027, 1, 1), "effective_to": None},
        ]  # fmt: skip

    def reference_tx_types(self):
        self.loads += 1
        return [
            {
                "tx_type": "food_drink",
                "label": "Ăn uống",
                "direction": "out",
                "default_jar_code": "an_uong",
                "system_role": None,
                "is_selectable": True,
                "sort_order": 10,
            }
        ]

    def reference_fees(self):
        self.loads += 1
        return self.fees

    def reference_templates(self):
        return []


def test_bang_tra_cache_theo_thoi_gian_va_phi_theo_ngay_hieu_luc():
    src, t = FakeRef(), [0.0]
    ref = ReferenceData(src, 300, monotonic=lambda: t[0])
    assert ref.tx_types()["food_drink"].default_jar_code == "an_uong"
    ref.tx_types()
    assert src.loads == 1
    t[0] = 301
    ref.tx_types()
    assert src.loads == 2
    # phí lấy từ bảng, theo ngày hiệu lực; không có số tiền nào gắn cứng trong mã
    assert ref.bnpl_monthly_fee(date(2026, 11, 21)).amount_vnd == 33_000
    assert ref.bnpl_monthly_fee(date(2027, 2, 1)).amount_vnd == 40_000
    assert ref.bnpl_monthly_fee(date(2026, 1, 1)) is None
    assert ref.product_label("bnpl_sim", date(2026, 11, 21)) == "Trả sau (mô phỏng)"
    assert ref.product_label("khac", date(2026, 11, 21)) == "khac"


# --- cấu hình ---------------------------------------------------------------------------------------------
ENV = {
    "YOFINA_CONFIRM_OFFER_TTL_SECONDS": "600", "YOFINA_MOVE_MAX_AMOUNT_VND": "50000000", "YOFINA_TRANSACTIONS_DEFAULT_LIMIT": "20",
    "YOFINA_TRANSACTIONS_MAX_LIMIT": "50", "YOFINA_APP_TIMEZONE": "Asia/Ho_Chi_Minh", "YOFINA_DEMO_ANCHOR_DATE": "2026-11-21",
    "YOFINA_TRANSACTION_MAX_AMOUNT_VND": "50000000", "YOFINA_SALARY_DEVIATION_ASK_PERCENT": "10.5",
    "YOFINA_DEFAULT_CREDIT_LIMIT_VND": "3000000", "YOFINA_DEFAULT_DISPLAY_NAME": "Bạn", "YOFINA_FORECAST_FRESHNESS_SECONDS": "3600",
    "YOFINA_PROACTIVE_OBLIGATION_DAYS": "3", "YOFINA_REFERENCE_CACHE_SECONDS": "300", "YOFINA_EVENT_BUS_NAME": "yofina-bus",
    "YOFINA_SUITABILITY_WINDOW_DAYS": "30",
}  # fmt: skip


def test_cau_hinh_doc_tu_bien_moi_truong_va_thieu_thi_bao_loi():
    s = LedgerSettings.from_config(Config(env=ENV))
    assert s.salary_deviation_ask_percent == Decimal("10.5") and s.event_bus_name == "yofina-bus"
    assert s.default_display_name == "Bạn" and s.forecast_freshness_seconds == 3600
    for key in (
        "YOFINA_SALARY_DEVIATION_ASK_PERCENT",
        "YOFINA_DEFAULT_CREDIT_LIMIT_VND",
        "YOFINA_FORECAST_FRESHNESS_SECONDS",
    ):
        with pytest.raises(Exception, match="Thiếu cấu hình"):
            LedgerSettings.from_config(Config(env={k: v for k, v in ENV.items() if k != key}))
    s2 = LedgerSettings.from_config(
        Config(env={k: v for k, v in ENV.items() if k != "YOFINA_EVENT_BUS_NAME"})
    )
    assert s2.event_bus_name == ""  # chưa có bus thì chỉ log, không lỗi


# --- tool Gateway, Cedar và hợp đồng -----------------------------------------------------------------------
TOOLS = load_json(CONTRACTS / "tools" / "ledger.json")


PHASE3_LEDGER_TOOLS = {"check_suitability", "schedule_nudge", "get_fee_schedule", "get_trace"}


def test_moi_tool_trong_hop_dong_co_dung_tham_so_o_gateway_api():
    # phase 3: Lambda ledger CŨNG phục vụ ba target planner, knowledge, audit (cùng Lambda, người điều phối chốt)
    assert {t["name"] for t in TOOLS} == set(_ARG_KEYS) - PHASE3_LEDGER_TOOLS
    contracts = list(TOOLS)
    for name in ("planner", "knowledge", "audit"):
        contracts += load_json(CONTRACTS / "tools" / f"{name}.json")
    assert {t["name"] for t in contracts} == set(_ARG_KEYS)
    for t in contracts:
        props = set(t["inputSchema"]["properties"]) - {"user_id"}
        assert props == set(_ARG_KEYS[t["name"]]), t["name"]


def test_moi_tool_co_luat_cedar_dung_dang():
    policies = REPO / "gateway" / "policies"
    for t in TOOLS:
        text = (policies / f"{t['name']}.cedar").read_text(encoding="utf-8")
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))
        assert f'action == AgentCore::Action::"ledger___{t["name"]}"' in code
        assert "context.input has user_id && context.input.user_id == principal.id" in code
        props = t["inputSchema"]["properties"]
        has_token = "confirm_token" in props
        assert ("confirm_token like" in code) == has_token, t["name"]
        # tool ghi có số tiền thì có hạn mức lấy từ cấu hình (placeholder do CDK thay), không số gắn cứng
        if "amount_vnd" in props and has_token:
            assert re.search(r"context\.input\.amount_vnd <= \$\{[A-Z_]+_MAX_AMOUNT_VND\}", code), (
                t["name"]
            )
        assert not re.search(r"\b[0-9]{6,}\b", code), "hạn mức phải đi qua placeholder"
    # save_jars và confirm_salary chỉ có ở REST, không lộ cho agent
    names = {t["name"] for t in TOOLS}
    assert not names & {"save_jars", "confirm_salary"}


def test_cancelled_trong_hop_dong_rest(registry):
    ref = f"{BASE}/rest/openapi.yaml#/components/schemas"

    def valid(name, inst):
        v = Draft202012Validator({"$ref": f"{ref}/{name}"}, registry=registry)
        return not list(v.iter_errors(inst))

    bid = "confirm:" + "a" * 32 + ":" + "0" * 12
    assert valid(
        "ConfirmResolution",
        {"block_id": bid, "status": "cancelled", "resolved_at": "2026-12-10T03:00:00Z"},
    )
    assert not valid(
        "ConfirmResolution", {"block_id": bid, "status": "cancelled"}
    )  # cần resolved_at
    assert valid("ConfirmResolution", {"block_id": bid, "status": "expired"})
    assert valid("CancelConfirmationRequest", {"conversation_id": "c1", "confirm_block_id": bid})
    assert not valid("CancelConfirmationRequest", {"conversation_id": "c1"})
    assert valid(
        "CancelConfirmationResponse",
        {"block_id": bid, "status": "cancelled", "resolved_at": "2026-12-10T03:00:00Z"},
    )


def test_seed_hu_mac_dinh_cong_lai_dung_100_va_co_chuyen_tien_cho_nguoi_duoc_danh_dau():
    seed = (REPO / "db" / "seed" / "jar_templates.sql").read_text(encoding="utf-8")
    rows = re.findall(
        r"^\s+\('([a-z_]+)',\s*'[^']+',\s*'[^']+',\s*'[^']+',\s*'[^']+',\s*([0-9.]+),\s*(true|false)",
        seed,
        re.M,
    )
    assert len(rows) == 7
    assert sum(Decimal(p) for _, p, d in rows if d == "true") == 100
    tx = (REPO / "db" / "seed" / "tx_type_map.sql").read_text(encoding="utf-8")
    flagged = re.findall(r"^\s+\('([a-z_]+)'.*, true\),?$", tx, re.M)
    person = [t for t in flagged if t == "transfer_person"]
    assert person == ["transfer_person"] and "is_person_transfer" in tx
