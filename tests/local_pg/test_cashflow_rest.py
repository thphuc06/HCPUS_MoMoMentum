"""`GET /cashflow` trên PostgreSQL thật cục bộ: câu SQL `generate_series` gọi `app_get_cashflow_summary` theo từng ngày, phân trang
`app_list_transactions` cho phần tách nghĩa vụ và Trả sau, RLS theo `sub`. Kiểm bằng ĐÚNG mã của Lambda (repo, service, REST) với persona
`minh` vừa đặt lại (ngày mô phỏng 21/11/2026, ngày 17 của kỳ lương 05/11).

Số kỳ vọng lấy từ chính tool `get_cashflow_summary` (cùng hàm SQL) chạy với cùng khoảng ngày, không gắn cứng.

Chạy cùng bộ local_pg (lệnh ở docstring của conftest.py): `pytest tests/local_pg/test_cashflow_rest.py`.
"""

from __future__ import annotations

import json
from datetime import date

from conftest import REPO
from jsonschema import Draft202012Validator
from ledger_fakes import http_event
from referencing import Registry, Resource

from yofina_ledger.rest_api import handle_http

MINH, LAN = "sub-minh", "sub-lan"
TODAY = date(2026, 11, 21)
OPENAPI = "https://contracts.yofina.invalid/rest/openapi.yaml"


def _registry() -> Registry:
    """Như `build_registry` của tests/unit/conftest.py (không import được vì trùng tên conftest)."""
    import yaml
    from referencing.jsonschema import DRAFT202012

    reg = Registry()
    contracts = REPO / "contracts"
    for p in sorted(contracts.glob("*/*.schema.json")):
        body = json.loads(p.read_text(encoding="utf-8"))
        reg = reg.with_resource(body["$id"], Resource.from_contents(body))
    spec = yaml.safe_load((contracts / "rest" / "openapi.yaml").read_text(encoding="utf-8"))
    return reg.with_resource(
        OPENAPI, Resource.from_contents(spec, default_specification=DRAFT202012)
    )


def _get(env, sub: str) -> tuple[int, dict]:
    res = handle_http(http_event("GET", "/cashflow", sub=sub), env.svc)
    return res["statusCode"], json.loads(res["body"])


def _tool(env, sub: str, start: date, end: date) -> dict:
    return env.svc.cashflow_result(sub, from_date=start.isoformat(), to_date=end.isoformat())[
        "data"
    ]


def test_cashflow_minh_khop_tool_ky_truoc_cung_so_ngay_va_rls(env):
    env.reset(MINH)
    env.reset(LAN)
    status, body = _get(env, MINH)
    assert status == 200, body

    v = Draft202012Validator(
        {"$ref": f"{OPENAPI}#/components/schemas/CashflowResponse"}, registry=_registry()
    )
    errs = [f"{list(e.path)}: {e.message}" for e in v.iter_errors(body)]
    assert errs == []

    period = body["period"]
    assert period["kind"] == "pay_period" and period["from_date"] == "2026-11-05"
    assert period["to_date"] == TODAY.isoformat() and period["day_index"] == 17
    assert period["end_date"] == "2026-12-04" and period["days_total"] == 30

    # kỳ này: đúng số của tool mặc định (không tham số) và tool với khoảng tường minh
    default = env.svc.cashflow_result(MINH)["data"]
    cur = body["current"]
    for k in ("from_date", "to_date", "salary_income_vnd", "other_income_vnd", "spent_vnd"):
        assert cur[k] == default[k], k
    assert cur["net_vnd"] == default["salary_income_vnd"] - default["spent_vnd"]
    assert body["unclassified_pending_vnd"] == default["unclassified_pending_vnd"]
    tool_jars = {j["jar"]: j for j in default["by_jar"]}
    for j in body["by_jar"]:
        if j["jar"] in tool_jars:
            assert (j["spent_vnd"], j["tx_count"]) == (
                tool_jars[j["jar"]]["spent_vnd"],
                tool_jars[j["jar"]]["tx_count"],
            )
    spent = [j["spent_vnd"] for j in body["by_jar"]]
    assert spent == sorted(spent, reverse=True)

    # kỳ trước: 05/10 tới 21/10 (ngày thứ 17), số của tool với đúng khoảng đó
    prev = body["previous"]
    assert (prev["from_date"], prev["to_date"], prev["end_date"]) == (
        "2026-10-05",
        "2026-10-21",
        "2026-11-04",
    )
    tool_prev = _tool(env, MINH, date(2026, 10, 5), date(2026, 10, 21))
    assert prev["spent_vnd"] == tool_prev["spent_vnd"]
    assert prev["salary_income_vnd"] == tool_prev["salary_income_vnd"]
    assert body["change"]["spent_vnd"] == cur["spent_vnd"] - prev["spent_vnd"]
    prev_jars = {j["jar"]: j["spent_vnd"] for j in tool_prev["by_jar"]}
    for j in body["by_jar"]:
        assert j["previous_spent_vnd"] == prev_jars.get(j["jar"], 0)

    # daily: cùng hàm theo từng ngày, cộng dồn ra đúng tổng của kỳ
    daily = body["daily"]
    assert [d["day_index"] for d in daily] == list(range(1, 18))
    assert daily[-1]["cumulative_vnd"] == cur["spent_vnd"]
    one_day = _tool(env, MINH, date(2026, 11, 9), date(2026, 11, 9))
    assert daily[4]["date"] == "2026-11-09" and daily[4]["spent_vnd"] == one_day["spent_vnd"]
    pd = body["previous_daily"]
    assert len(pd) == 31 and pd[16]["cumulative_vnd"] == prev["spent_vnd"]
    assert (
        pd[-1]["cumulative_vnd"]
        == _tool(env, MINH, date(2026, 10, 5), date(2026, 11, 4))["spent_vnd"]
    )

    # tách nghĩa vụ và Trả sau: đọc hết, khớp tool
    assert body["split_complete"] is True
    assert cur["regular_spent_vnd"] == cur["spent_vnd"] - cur["obligation_vnd"]
    assert daily[-1]["regular_cumulative_vnd"] == cur["regular_spent_vnd"]
    assert pd[16]["regular_cumulative_vnd"] == prev["regular_spent_vnd"]
    assert cur["obligation_vnd"] > 0 and cur["credit_vnd"] > 0
    for j in body["by_jar"]:
        assert j["obligation_vnd"] + j["credit_vnd"] <= j["spent_vnd"]
    assert body["change"]["regular_vnd"] == cur["regular_spent_vnd"] - prev["regular_spent_vnd"]

    # RLS: lan thấy số của lan, không phải của minh
    status, lan = _get(env, LAN)
    assert status == 200
    assert lan["current"]["spent_vnd"] == env.svc.cashflow_result(LAN)["data"]["spent_vnd"]
    assert lan["daily"][-1]["cumulative_vnd"] == lan["current"]["spent_vnd"]


def test_cashflow_khoa_ky_truoc_chua_tron_du_lieu_thi_khong_so(env):
    """khoa có 18 ngày dữ liệu (từ cuối kỳ 05/10): kỳ trước chưa trọn nên không có `previous`, kỳ này vẫn đủ số của tool."""
    env.reset("sub-khoa", "khoa")
    status, body = _get(env, "sub-khoa")
    assert status == 200, body
    assert "previous" not in body and "previous_daily" not in body and "change" not in body
    assert all("previous_spent_vnd" not in j and "change_vnd" not in j for j in body["by_jar"])
    assert (
        body["current"]["spent_vnd"] == env.svc.cashflow_result("sub-khoa")["data"]["spent_vnd"] > 0
    )


def test_cashflow_tai_khoan_trang_khong_co_ky_truoc(env):
    status, body = _get(env, "sub-trang-cashflow")
    assert status == 200, body
    assert body["period"]["kind"] == "calendar_month"
    assert body["current"]["spent_vnd"] == 0 and body["by_jar"] == []
    assert "previous" not in body and "previous_daily" not in body and "change" not in body
    assert body["daily"][-1]["cumulative_vnd"] == 0
    assert len(body["daily"]) == body["period"]["day_index"]
