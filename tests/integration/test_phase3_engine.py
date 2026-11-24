"""Engine phase 3 trên môi trường THẬT (luồng A): kịch bản what-if, kiểm tra trước khi quẹt, suitability, biểu phí, trace, phản hồi, lời nhắc.

Tiêu chí phase 3 phần backend: 1 (số engine của `minh`: tổng hạn 05/12 là 2.200.000 ₫), 3 (chuyển 250.000 ₫: thẻ theo hũ và tổng Trả sau
1.250.000 ₫), 4 (`GET /traces/{id}` chỉ của chính người dùng), 8 phần engine tất định (không gọi model), 9 (`POST /affordability` p95),
10 (sáu loại kịch bản FR5 chạy được). Hai tiêu chí 1 và 3 chấm theo số engine như mục "Người điều phối chốt" của file phase 3.

Tool gọi qua Gateway khi Gateway đã có tool đó (bước ghép deploy YofinaAgent); chưa có thì gọi thẳng Lambda theo ĐÚNG dạng sự kiện của
Gateway (tên tool ở client context, `user_id` do interceptor ghi đè). Kết quả cùng một Lambda, cùng một mã; chỉ thiếu lớp JWT/Cedar, lớp đó
đã có test riêng ở test_gateway_identity.py và test_gateway_config.py. Bảng `audit_events` đọc/ghi bằng secret master CHỈ để dựng một bản
ghi lượt giả lập vai trò của agent (sản phẩm không bao giờ dùng master).
"""

from __future__ import annotations

import base64
import json
import statistics
import time
import uuid
from datetime import date, timedelta

import pytest
from conftest import REPO, flow, master_data_api

pytestmark = pytest.mark.usefixtures("fresh")

TOOLS = "https://contracts.yofina.invalid/tools"
BLOCKS = "https://contracts.yofina.invalid/blocks"
REPORT_DIR = REPO / "build" / "reports"
MEASURES: dict[str, object] = {}


def code(body) -> str:
    return body["error"]["code"]


@pytest.fixture(scope="module", autouse=True)
def write_measures():
    yield
    if MEASURES:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        (REPORT_DIR / "r2-stream-a-measures.json").write_text(
            json.dumps(MEASURES, ensure_ascii=False, indent=2), encoding="utf-8"
        )


@pytest.fixture(scope="module")
def forecast_fn(sess) -> str:
    from _yofina import ssm_param

    return ssm_param("forecast/function-name", sess=sess)


@pytest.fixture(scope="module")
def gateway_tools(gw) -> set[str]:
    try:
        return set(gw("minh").tool_names())
    except Exception:  # Gateway không với tới được: dùng đường gọi thẳng Lambda
        return set()


@pytest.fixture(scope="module")
def tool(gw, subs, lambda_client, ledger_fn, forecast_fn, gateway_tools):
    """tool('minh', 'forecast___run_scenario', {...}) -> dict kết quả (status, data hoặc code). Ghi lại đường đã đi ở `tool.via`."""

    def call(who: str, name: str, args: dict | None = None) -> dict:
        args = args or {}
        if name in gateway_tools:
            call.via.add("gateway")
            reply = gw(who).call(name, args)
            assert reply.data is not None, reply.text
            return reply.data
        call.via.add("lambda")
        fn = forecast_fn if name.startswith("forecast___") else ledger_fn
        ctx = base64.b64encode(
            json.dumps({"custom": {"bedrockAgentCoreToolName": name}}).encode()
        ).decode()
        r = lambda_client.invoke(
            FunctionName=fn,
            ClientContext=ctx,
            Payload=json.dumps({**args, "user_id": subs[who]}).encode(),
        )
        assert "FunctionError" not in r, r["Payload"].read()
        return json.loads(r["Payload"].read())

    call.via = set()
    return call


@pytest.fixture(scope="module")
def master(sess):
    return master_data_api(sess)


def ok(reply: dict) -> dict:
    assert reply["status"] == "OK", reply
    return reply["data"]


# --- tiêu chí 3 (phần backend): chuyển 250.000 ₫ cho người nhận demo -------------------------------------------------
def test_chuyen_250k_cho_nguoi_nhan_demo_the_theo_hu_va_tong_tra_sau_1_250_000(
    api, schema_validator
):
    status, card = api(
        "minh",
        "POST",
        "/affordability",
        {"amount_vnd": 250_000, "label": "Người nhận demo"},
        timeout=60,
    )
    assert status == 200, card
    schema_validator(f"{BLOCKS}/affordability_card.schema.json", card)
    assert (
        card["type"] == "affordability_card"
        and card["source"]["tool"] == "rest:POST /affordability"
    )
    d = card["data"]
    jars = {c["jar"]["code"]: c for c in d["jar_checks"]}
    assert jars["di_lai"]["status"] == "ok" and jars["giai_tri"]["status"] == "ok"
    assert jars["an_uong"]["status"] == "short" and jars["an_uong"]["balance_after_vnd"] == 130_000
    # Lệch so với câu chữ tiêu chí 3 (Hóa đơn vàng): số engine ra Hóa đơn hụt vì tiền điện 26/11 (không còn đủ sau khi trừ 250.000 ₫).
    assert (
        jars["hoa_don"]["status"] in ("tight", "short")
        and jars["hoa_don"]["balance_after_vnd"] == 200_000
    )
    cost = d["credit"]["cost"]
    assert (cost["principal_vnd"], cost["fee_added_vnd"], cost["item_cost_vnd"]) == (
        250_000,
        0,
        250_000,
    )
    assert (cost["existing_due_vnd"], cost["total_due_vnd"]) == (1_000_000, 1_250_000)
    assert cost["due_date"] == "2026-12-05"
    assert cost["total_due_vnd"] == cost["existing_due_vnd"] + cost["item_cost_vnd"]
    assert (
        d["credit"]["cautions"] and d["credit"]["cautions"][0]["rule_id"] == "obligation_to_income"
    )  # vượt ngưỡng: kèm luật


def test_the_do_du_sat_hut_theo_so_tien_va_hu_da_chon(api):
    def ask(jar: str, amount: int) -> dict:
        status, card = api(
            "minh",
            "POST",
            "/affordability",
            {"amount_vnd": amount, "funding_source": "jar", "jar": jar},
            timeout=60,
        )
        assert status == 200, card
        return card["data"]

    enough = ask("giai_tri", 300_000)
    assert enough["verdict"] == "ok" and enough["options"] == []  # đủ: không đưa phương án
    tight = ask("giai_tri", 750_000)
    assert tight["verdict"] == "tight" and {o["option_id"] for o in tight["options"]} >= {
        "defer_payday",
        "split_two",
    }
    short = ask("giai_tri", 900_000)
    chk = short["jar_checks"][0]
    assert short["verdict"] == "short" and chk["shortfall_vnd"] > 0 and chk["days_earlier"] > 0
    assert short["options"] and all(
        o["status"] in ("ok", "tight", "short") for o in short["options"]
    )
    # hũ khác còn đủ thì được đề xuất đổi hũ
    di_lai = ask("di_lai", 600_000)
    assert di_lai["verdict"] == "short"
    assert any(o["kind"] == "switch_jar" and o["status"] == "ok" for o in di_lai["options"])


def test_affordability_loi_dau_vao_va_danh_tinh(api):
    assert api("minh", "POST", "/affordability", {"amount_vnd": 0})[0] in (400, 422)
    status, body = api("minh", "POST", "/affordability", {"amount_vnd": 1000, "user_id": "x"})
    assert (
        status in (400, 422) and code(body) == "PARAMS_INVALID"
    )  # thân yêu cầu không được mang user_id
    status, body = api(
        "minh", "POST", "/affordability", {"amount_vnd": 1000, "jar": "khong_co"}, timeout=60
    )
    assert (status, code(body)) == (404, "JAR_NOT_FOUND")
    status, body = api(
        "minh", "POST", "/affordability", {"amount_vnd": 1000, "jar": "tien_vao_khac"}, timeout=60
    )
    assert (status, code(body)) == (404, "FORECAST_NOT_APPLICABLE")
    assert api(None, "POST", "/affordability", {"amount_vnd": 1000})[0] == 401


def test_khoa_chua_khai_luong_khong_co_the_affordability_gia(api):
    # `khoa` có hồ sơ nhưng chỉ ước lượng ban đầu: thẻ vẫn tính được và gắn cờ ước lượng ban đầu, không bịa độ tin cậy cao
    status, card = api("khoa", "POST", "/affordability", {"amount_vnd": 100_000}, timeout=60)
    assert status == 200, card
    assert card["data"]["basis"]["is_initial_estimate"] is True


# --- tiêu chí 9: POST /affordability p95 ------------------------------------------------------------------------------
def test_affordability_p95_duoi_2_giay_phien_am(api):
    api(
        "minh", "POST", "/affordability", {"amount_vnd": 250_000}, timeout=60
    )  # làm nóng (Aurora tự ngủ, Lambda lạnh)
    ms = []
    for i in range(10):
        t = time.perf_counter()
        status, _ = api(
            "minh", "POST", "/affordability", {"amount_vnd": 100_000 + i * 10_000}, timeout=60
        )
        ms.append((time.perf_counter() - t) * 1000)
        assert status == 200
    ms.sort()
    p95 = ms[min(len(ms) - 1, int(0.95 * len(ms)))]  # 10 mẫu: p95 = mẫu lớn nhất
    MEASURES["affordability_p95_ms"] = round(p95)
    MEASURES["affordability_median_ms"] = round(statistics.median(ms))
    assert p95 < 2000, ms


# --- tiêu chí 10 và 1: sáu loại kịch bản FR5 --------------------------------------------------------------------------
def scenario_specs(payday: str) -> dict[str, dict]:
    return {
        "one_time_purchase": {
            "kind": "one_time_purchase",
            "amount_vnd": 500_000,
            "funding_source": "jar",
            "jar_code": "giai_tri",
            "label": "giày",
        },
        "bnpl_purchase": {
            "kind": "bnpl_purchase",
            "amount_vnd": 1_200_000,
            "funding_source": "credit",
            "label": "tai nghe",
        },
        "income_change": {
            "kind": "income_change",
            "new_monthly_salary_vnd": 7_000_000,
            "date": payday,
        },
        "recurring_expense": {
            "kind": "recurring_expense",
            "amount_vnd": 200_000,
            "jar_code": "giai_tri",
            "cycle": "monthly",
            "date": payday,
            "label": "phòng gym",
        },
        "jar_transfer": {
            "kind": "jar_transfer",
            "amount_vnd": 300_000,
            "from_jar": "giai_tri",
            "to_jar": "an_uong",
        },
        "goal_delay": {"kind": "goal_delay", "jar_code": "du_lich", "delay_months": 2},
    }


@pytest.mark.parametrize(
    "kind",
    [
        "one_time_purchase",
        "bnpl_purchase",
        "income_change",
        "recurring_expense",
        "jar_transfer",
        "goal_delay",
    ],
)
def test_sau_loai_kich_ban_chay_duoc_5000_duong_cung_day_so_ngau_nhien(
    tool, schema_validator, kind
):
    spec = scenario_specs("2026-12-05")[kind]
    reply = tool("minh", "forecast___run_scenario", {"scenario": spec})
    schema_validator(f"{TOOLS}/forecast.results.schema.json#/$defs/RunScenarioResult", reply)
    d = ok(reply)
    assert d["spec"]["kind"] == kind
    assert d["n_paths"] == 5000 and d["common_random_numbers"] is True
    assert d["effects"] and d["timelines"]
    assert uuid.UUID(d["scenario_id"])
    for tl in d["timelines"]:
        assert tl["compare"]["common_random_numbers"] is True and tl["compare"]["n_paths"] == 5000
        assert len(tl["days"]) == tl["horizon_days"] == len(tl["compare"]["after"]["days"])


def test_mua_tai_nghe_1_2_trieu_bang_tra_sau_tong_den_han_05_12_la_2_200_000(
    tool, schema_validator
):
    d = ok(
        tool(
            "minh",
            "forecast___run_scenario",
            {"scenario": scenario_specs("2026-12-05")["bnpl_purchase"]},
        )
    )
    impact = d["obligation_impact"]
    assert impact is not None
    cost = impact["cost"] if "cost" in impact else impact["data"]["cost"]
    assert (cost["principal_vnd"], cost["fee_added_vnd"], cost["item_cost_vnd"]) == (
        1_200_000,
        0,
        1_200_000,
    )
    assert (cost["existing_due_vnd"], cost["total_due_vnd"]) == (1_000_000, 2_200_000)
    assert cost["due_date"] == "2026-12-05"
    assert (
        cost["available_before_vnd"] - cost["available_after_vnd"] == 1_200_000
    )  # hạn mức giảm đúng giá món
    assert any(
        e["jar"]["code"] == "nghia_vu" for e in d["effects"]
    )  # hũ Nghĩa vụ bị tác động khi đến hạn


def test_cung_day_so_ngau_nhien_baseline_va_kich_ban_khong_nhieu(tool):
    spec = scenario_specs("2026-12-05")["jar_transfer"]
    a = ok(tool("minh", "forecast___run_scenario", {"scenario": spec}))
    b = ok(tool("minh", "forecast___run_scenario", {"scenario": spec}))
    assert a["scenario_id"] != b["scenario_id"]

    def strip(d):
        return [
            (
                e["jar"]["code"],
                e["status_after"],
                e["min_balance_delta_vnd"],
                e["p_shortfall_after"],
            )
            for e in d["effects"]
        ]

    assert strip(a) == strip(b), "cùng đầu vào phải ra cùng kết quả (dãy số ngẫu nhiên cố định)"


def test_doi_luong_bang_chinh_muc_dang_co_bi_tu_choi_va_mua_1_dong_chi_lech_dung_1_dong(api, tool):
    status, prof = api("minh", "GET", "/profile")
    assert status == 200, prof
    same = {
        "kind": "income_change",
        "new_monthly_salary_vnd": prof["profile"]["monthly_salary_vnd"],
        "date": "2026-12-05",
    }
    noop = tool("minh", "forecast___run_scenario", {"scenario": same})
    assert (
        noop["status"] == "ERROR" and noop["code"] == "SCENARIO_INVALID"
    )  # không đổi gì thì không có gì để so
    # cùng dãy số ngẫu nhiên: mua 1 đồng chỉ lệch đúng 1 đồng ở đáy số dư, không dính nhiễu Monte Carlo
    spec = {
        "kind": "one_time_purchase",
        "amount_vnd": 1,
        "funding_source": "jar",
        "jar_code": "giai_tri",
    }
    d = ok(tool("minh", "forecast___run_scenario", {"scenario": spec}))
    effect = next(e for e in d["effects"] if e["jar"]["code"] == "giai_tri")
    assert effect["min_balance_delta_vnd"] == -1
    assert effect["status_before"] == effect["status_after"]
    assert effect.get("p_shortfall_after") == effect.get("p_shortfall_before")


def test_kich_ban_sai_bi_tu_choi_dung_ma(tool):
    bad = tool(
        "minh",
        "forecast___run_scenario",
        {"scenario": {"kind": "khong_co_loai_nay", "amount_vnd": 1}},
    )
    assert bad["status"] == "ERROR" and bad["code"] in ("SCENARIO_INVALID", "PARAMS_INVALID")
    no_amount = tool(
        "minh",
        "forecast___run_scenario",
        {"scenario": {"kind": "bnpl_purchase", "funding_source": "credit"}},
    )
    assert no_amount["status"] == "ERROR" and no_amount["code"] in (
        "SCENARIO_INVALID",
        "PARAMS_INVALID",
    )
    system = tool(
        "minh",
        "forecast___run_scenario",
        {
            "scenario": {
                "kind": "one_time_purchase",
                "amount_vnd": 100_000,
                "funding_source": "jar",
                "jar_code": "tien_vao_khac",
            }
        },
    )
    assert system["status"] == "ERROR" and system["code"] == "FORECAST_NOT_APPLICABLE"
    ghost = tool(
        "minh",
        "forecast___run_scenario",
        {
            "scenario": {
                "kind": "one_time_purchase",
                "amount_vnd": 100_000,
                "funding_source": "jar",
                "jar_code": "khong_co",
            }
        },
    )
    assert ghost["status"] == "ERROR" and ghost["code"] == "JAR_NOT_FOUND"
    past = (date.today() - timedelta(days=1)).isoformat()
    assert (
        tool(
            "minh",
            "forecast___run_scenario",
            {
                "scenario": {
                    "kind": "recurring_expense",
                    "amount_vnd": 1,
                    "jar_code": "giai_tri",
                    "cycle": "monthly",
                    "date": "2026-13-45",
                    "end_date": past,
                }
            },
        )["status"]
        == "ERROR"
    )


def test_affordability_check_tool_cung_so_voi_rest(api, tool, gw, gateway_tools, schema_validator):
    reply = tool(
        "minh",
        "forecast___affordability_check",
        {"amount_vnd": 250_000, "label": "Người nhận demo"},
    )
    schema_validator(f"{TOOLS}/forecast.results.schema.json#/$defs/AffordabilityCheckResult", reply)
    d = ok(reply)
    status, card = api(
        "minh",
        "POST",
        "/affordability",
        {"amount_vnd": 250_000, "label": "Người nhận demo"},
        timeout=60,
    )
    assert status == 200
    assert (
        d["jar_checks"] == card["data"]["jar_checks"]
        and d["credit"]["cost"] == card["data"]["credit"]["cost"]
    )
    if "forecast___affordability_check" in gateway_tools:  # Gateway kiểm schema trước Lambda: thiếu amount_vnd bị từ chối ở cổng
        reply = gw("minh").call("forecast___affordability_check", {})
        assert reply.is_error and "amount_vnd" in reply.text
    else:
        missing = tool("minh", "forecast___affordability_check", {})
        assert missing["status"] == "ERROR" and missing["code"] == "PARAMS_INVALID"


# --- get_fee_schedule và check_suitability --------------------------------------------------------------------------
def test_get_fee_schedule_doc_bang_co_cau_truc_kem_nguon_va_ngay_hieu_luc(tool, schema_validator):
    reply = tool("minh", "knowledge___get_fee_schedule", {})
    schema_validator(f"{TOOLS}/knowledge.results.schema.json#/$defs/GetFeeScheduleResult", reply)
    d = ok(reply)
    assert d["product_code"] == "bnpl_sim" and d["fees"]
    assert all(f["source_url"].startswith("https://") and f["effective_from"] for f in d["fees"])
    monthly = ok(tool("minh", "knowledge___get_fee_schedule", {"fee_type": "monthly_service_fee"}))[
        "fees"
    ]
    assert len(monthly) == 1 and monthly[0]["amount_vnd"] == 33_000
    miss = tool("minh", "knowledge___get_fee_schedule", {"fee_type": "khong_co_phi_nay"})
    assert miss["status"] == "ERROR" and miss["code"] == "FEE_SCHEDULE_NOT_FOUND"


def test_check_suitability_liet_ke_du_nam_luat_va_chan_vay_de_tieu(tool, schema_validator):
    five = {
        "obligations_first",
        "emergency_before_investing",
        "risk_within_tolerance",
        "no_borrow_to_spend",
        "obligation_to_income",
        "source_jar_covers",  # luật thứ sáu (23/11): hũ nguồn đủ tiền
        "emergency_not_for_discretionary",  # luật thứ bảy (25/11): giữ quỹ dự phòng cho việc gấp
    }
    rec = tool(
        "minh",
        "planner___check_suitability",
        {
            "proposal": {
                "kind": "use_credit",
                "amount_vnd": 1_200_000,
                "funding_source": "credit",
                "category": "spending",
                "is_essential": False,
                "origin": "recommendation",
            }
        },
    )
    schema_validator(f"{TOOLS}/planner.results.schema.json#/$defs/CheckSuitabilityResult", rec)
    d = ok(rec)
    assert {c["rule_id"] for c in d["checked"]} == five
    assert d["ok"] is False and any(
        v["rule_id"] == "no_borrow_to_spend" and v["severity"] == "block" for v in d["violations"]
    )
    own = ok(
        tool(
            "minh",
            "planner___check_suitability",
            {
                "proposal": {
                    "kind": "bnpl_purchase",
                    "amount_vnd": 1_200_000,
                    "funding_source": "credit",
                    "is_essential": False,
                    "origin": "user_request",
                }
            },
        )
    )
    assert {c["rule_id"] for c in own["checked"]} == five
    assert all(
        v["severity"] == "warn" for v in own["violations"] if v["rule_id"] == "no_borrow_to_spend"
    )  # lời người dùng tự hỏi: cảnh báo, không chặn
    clean = ok(
        tool(
            "minh",
            "planner___check_suitability",
            {"proposal": {"kind": "jar_transfer", "amount_vnd": 100_000, "category": "saving"}},
        )
    )
    assert clean["ok"] is True and not [v for v in clean["violations"] if v["severity"] == "block"]


# --- tiêu chí 4: trace chỉ của chính người dùng ------------------------------------------------------------------------
def insert_turn(master, sub: str, trace_id: str) -> None:
    with master.transaction(sub) as tx:
        tx.execute(
            """INSERT INTO audit_events (user_id, trace_id, event_type, outcome, intent, data_used, rules_checked, confidence,
                   blocks_emitted, token_usage, step_timings, duration_ms)
               VALUES (:u, :t, 'agent_turn', 'ok', 'what_if', CAST(:du AS jsonb), CAST(:rc AS jsonb), CAST(:cf AS jsonb),
                   CAST(:be AS jsonb), CAST(:tu AS jsonb), CAST(:st AS jsonb), 1200)""",
            {
                "u": sub,
                "t": trace_id,
                "du": json.dumps(
                    [
                        {
                            "label": "Số dư hũ Giải trí",
                            "value": "760.000 ₫",
                            "tool": "ledger___get_jar_balances",
                        }
                    ]
                ),
                "rc": json.dumps(
                    [{"rule_id": "obligations_first", "label": "Nghĩa vụ trước", "outcome": "pass"}]
                ),
                "cf": json.dumps({"band": "medium", "reasons": ["Có 47 ngày dữ liệu."]}),
                "be": json.dumps([{"id": f"options:{trace_id}", "type": "options"}]),
                "tu": json.dumps({"input_tokens": 100, "output_tokens": 20, "model_calls": 1}),
                "st": json.dumps([{"step": "tools", "ms": 800}]),
            },
        )


def test_trace_chi_cua_chinh_nguoi_dung_nguoi_khac_va_khong_ton_tai_cung_404(
    api, tool, master, subs, schema_validator
):
    trace = uuid.uuid4().hex
    insert_turn(master, subs["minh"], trace)
    status, body = api("minh", "GET", f"/traces/{trace}")
    assert status == 200, body
    assert body["trace_id"] == trace and body["explain"]["type"] == "explain"
    assert body["explain"]["data"]["subject_trace_id"] == trace
    assert body["explain"]["data"]["data_used"][0]["tool"] == "ledger___get_jar_balances"
    assert body["explain"]["data"]["rules_checked"][0]["rule_id"] == "obligations_first"
    assert body["explain"]["data"]["confidence"]["band"] == "medium"
    schema_validator(f"{BLOCKS}/explain.schema.json", body["explain"])
    # người khác và trace không tồn tại: cùng một câu trả lời, không lộ sự tồn tại
    status, other = api("lan", "GET", f"/traces/{trace}")
    assert (status, code(other)) == (404, "TRACE_NOT_FOUND")
    status, none = api("minh", "GET", f"/traces/{uuid.uuid4().hex}")
    assert (status, code(none)) == (404, "TRACE_NOT_FOUND")
    assert api(None, "GET", f"/traces/{trace}")[0] == 401
    # cùng dữ liệu qua tool audit___get_trace
    via_tool = ok(tool("minh", "audit___get_trace", {"trace_id": trace}))
    assert via_tool["explain"]["data"] == body["explain"]["data"]
    denied = tool("lan", "audit___get_trace", {"trace_id": trace})
    assert denied["status"] == "ERROR" and denied["code"] == "TRACE_NOT_FOUND"


# --- phản hồi phương án -------------------------------------------------------------------------------------------------
def test_feedback_upsert_theo_phuong_an_va_tu_choi_dau_vao_sai(api, tool, master, subs):
    trace = uuid.uuid4().hex
    spec = {
        "kind": "jar_transfer",
        "amount_vnd": 100_000,
        "from_jar": "giai_tri",
        "to_jar": "an_uong",
    }
    scenario_id = ok(tool("minh", "forecast___run_scenario", {"scenario": spec}))["scenario_id"]
    status, nope = api(
        "minh",
        "POST",
        "/feedback",
        {"trace_id": trace, "block_id": "options:x", "option_id": "a", "decision": "accepted"},
    )
    assert (status, code(nope)) == (
        404,
        "TRACE_NOT_FOUND",
    )  # không ghi phản hồi cho lượt không có thật
    insert_turn(master, subs["minh"], trace)
    body = {
        "trace_id": trace,
        "block_id": f"options:{trace}",
        "option_id": "defer_payday",
        "decision": "accepted",
        "scenario_id": scenario_id,
    }
    status, first = api("minh", "POST", "/feedback", body)
    assert status == 200, first
    assert first["decision"] == "accepted" and uuid.UUID(first["feedback_id"])
    status, second = api(
        "minh", "POST", "/feedback", {**body, "decision": "rejected"}
    )  # đổi ý: cập nhật, không thêm dòng
    assert (
        status == 200
        and second["decision"] == "rejected"
        and second["feedback_id"] == first["feedback_id"]
    )
    rows = master.query(
        "SELECT decision FROM feedback WHERE user_id = :u AND trace_id = :t",
        {"u": subs["minh"], "t": trace},
    )
    assert [r["decision"] for r in rows] == ["rejected"]
    assert api("minh", "POST", "/feedback", {**body, "decision": "maybe"})[0] in (400, 422)
    assert api("minh", "POST", "/feedback", {**body, "user_id": subs["lan"]})[0] in (400, 422)
    assert api(None, "POST", "/feedback", body)[0] == 401
    other = master.query(
        "SELECT 1 FROM feedback WHERE user_id = :u AND trace_id = :t",
        {"u": subs["lan"], "t": trace},
    )
    assert other == []


# --- lời nhắc: chỉ qua đường ghi có token, không có POST /nudges -------------------------------------------------------
def test_schedule_nudge_qua_token_tao_va_huy_va_khong_co_post_nudges(api, tool, master, subs):
    # từ phase 5, batch sau khi đặt lại ghi một bản tin của cổng giá trị (`source = 'system'`): chỉ đếm lời nhắc người dùng đặt
    own = "SELECT status, fire_on::text AS fire_on FROM nudges WHERE user_id = :u AND source <> 'system'"
    params = {
        "op": "create",
        "kind": "purchase_review",
        "fire_on": "2026-11-26",
        "jar_code": "giai_tri",
        "note": "xem lại tai nghe",
    }
    dry = tool("minh", "planner___schedule_nudge", params)  # không token: chỉ xem trước, không ghi
    assert dry["status"] == "NEEDS_CONFIRMATION" and dry["data"]["tool"] == "schedule_nudge"
    assert master.query(own, {"u": subs["minh"]}) == []
    status, receipt = flow(api, "minh", "schedule_nudge", params)
    assert status == 200, receipt
    nudge_id = receipt["data"]["reference_id"] if "data" in receipt else receipt["reference_id"]
    rows = master.query(own, {"u": subs["minh"]})
    assert [(r["status"], r["fire_on"]) for r in rows] == [("scheduled", "2026-11-26")]
    status, cancelled = flow(api, "minh", "schedule_nudge", {"op": "cancel", "nudge_id": nudge_id})
    assert status == 200, cancelled
    rows = master.query(own, {"u": subs["minh"]})
    assert [r["status"] for r in rows] == ["cancelled"]
    # ngày không sau hôm nay mô phỏng (21/11) bị từ chối ngay ở bước xem trước
    status, bad = api(
        "minh",
        "POST",
        "/confirmations",
        {"tool": "schedule_nudge", "params": {**params, "fire_on": "2026-11-21"}},
    )
    assert status in (400, 422), bad
    assert api("minh", "POST", "/nudges", params)[0] in (403, 404)  # không có đường ghi tắt


# --- ledger: OFFER_EXPIRED đã có ở test_wallet_rest.py; ở đây kiểm Hoàn tác lời nhắc của người khác không chạm được ----
def test_huy_loi_nhac_cua_nguoi_khac_bi_tu_choi(api, master, subs):
    status, receipt = flow(
        api,
        "minh",
        "schedule_nudge",
        {"op": "create", "kind": "purchase_review", "fire_on": "2026-11-27"},
    )
    assert status == 200, receipt
    nudge_id = receipt["data"]["reference_id"] if "data" in receipt else receipt["reference_id"]
    status, body = flow(api, "lan", "schedule_nudge", {"op": "cancel", "nudge_id": nudge_id})
    assert status in (404, 403) and code(body) in ("NUDGE_NOT_FOUND", "FORBIDDEN"), body
    rows = master.query("SELECT status FROM nudges WHERE id = CAST(:i AS uuid)", {"i": nudge_id})
    assert [r["status"] for r in rows] == ["scheduled"]


# --- F1: bản ghi lượt ghi qua Gateway tool (đường thật của agent), không dùng secret master -----------------------------
def test_record_turn_qua_gateway_roi_get_traces_200_feedback_200_nguoi_khac_404(
    api, tool, master, subs, schema_validator
):
    """Cần Gateway đã có tool `audit___record_turn` (deploy Tools) và Lambda ledger mới. Không dùng master để dựng bản ghi."""
    trace = uuid.uuid4().hex
    record = {
        "trace_id": trace,
        "conversation_id": f"it-{trace[:12]}",
        "intent": "what_if",
        "outcome": "ok",
        "data_used": [{"label": "Số dư các hũ", "value": "6 hũ", "tool": "ledger___get_jar_balances"}],
        "rules_checked": [{"rule_id": "obligations_first", "label": "Nghĩa vụ trước", "outcome": "pass"}],
        "confidence": {"band": "high", "reasons": ["Số liệu lấy trực tiếp từ sổ cái của bạn."]},
        "blocks_emitted": [{"id": f"options:{trace}", "type": "options"}],
        "token_usage": {"input_tokens": 10, "output_tokens": 5, "model_calls": 1},
        "step_timings": [{"step": "router", "ms": 120}],
        "duration_ms": 900,
    }
    # chưa ghi: 404 cho cả đọc lẫn phản hồi
    assert api("minh", "GET", f"/traces/{trace}")[0] == 404
    first = ok(tool("minh", "audit___record_turn", record))
    assert first == {"trace_id": trace, "recorded": True}
    again = ok(tool("minh", "audit___record_turn", {**record, "duration_ms": 1}))
    assert again["recorded"] is False  # chỉ thêm: ghi lại không đổi bản đầu
    # user_id trong thân không đổi được người ghi (interceptor/Lambda lấy từ JWT)
    spoof_trace = uuid.uuid4().hex
    spoof = tool("lan", "audit___record_turn", {**record, "user_id": subs["minh"], "trace_id": spoof_trace})
    assert spoof["status"] == "OK"
    owner = master.query("SELECT user_id FROM audit_events WHERE event_type = 'agent_turn' AND trace_id = :t", {"t": spoof_trace})
    assert [r["user_id"] for r in owner] == [subs["lan"]]
    rows = master.query(
        "SELECT user_id, duration_ms FROM audit_events WHERE event_type = 'agent_turn' AND trace_id = :t",
        {"t": trace},
    )
    assert [(r["user_id"], r["duration_ms"]) for r in rows] == [(subs["minh"], 900)]
    # đọc lại: 200 cho chính chủ, đúng bản ghi đã ghi
    status, body = api("minh", "GET", f"/traces/{trace}")
    assert status == 200, body
    assert body["detail"]["duration_ms"] == 900 and body["detail"]["intent"] == "what_if"
    schema_validator(f"{BLOCKS}/explain.schema.json", body["explain"])
    # phản hồi chấp nhận trace_id thật
    fb = {"trace_id": trace, "block_id": f"options:{trace}", "option_id": "defer_payday", "decision": "accepted"}
    status, res = api("minh", "POST", "/feedback", fb)
    assert status == 200 and res["decision"] == "accepted", res
    # người khác: 404 cho đọc và phản hồi
    status, other = api("lan", "GET", f"/traces/{trace}")
    assert (status, code(other)) == (404, "TRACE_NOT_FOUND")
    status, other_fb = api("lan", "POST", "/feedback", fb)
    assert (status, code(other_fb)) == (404, "TRACE_NOT_FOUND")
    # tham số sai: bị từ chối, không ghi
    bad = tool("minh", "audit___record_turn", {**record, "trace_id": uuid.uuid4().hex, "outcome": "weird"})
    assert bad["status"] == "ERROR" and bad["code"] in ("PARAMS_INVALID", "VALIDATION_ERROR")
