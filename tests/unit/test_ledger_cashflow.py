"""`GET /cashflow` (bản REST của tool `get_cashflow_summary`, B1, B5, B7): cùng số với tool, kỳ trước tính tới cùng số ngày, chuỗi
theo ngày, phần tách nghĩa vụ và Trả sau chỉ khi khớp tool, danh tính chỉ từ `sub`. Kho dữ liệu giả trong bộ nhớ làm theo đúng bộ lọc
của `app_get_cashflow_summary` (migration 0050); SQL thật (kể cả câu `generate_series`) được kiểm ở tests/local_pg/test_cashflow_rest.py."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from itertools import count

import pytest
from conftest import OPENAPI_URI
from jsonschema import Draft202012Validator
from ledger_fakes import FakeRepo, http_event, make_service

from yofina_ledger import cashflow_rest
from yofina_ledger.cashflow_rest import SQL_DAILY, periods
from yofina_ledger.gateway_api import handle_gateway
from yofina_ledger.rest_api import handle_http

MINH, LAN = "sub-minh", "sub-lan"
TODAY = date(2026, 11, 21)  # ngày mô phỏng của đồng hồ giả (offset -19)
_seq = count()


class CashflowRepo(FakeRepo):
    """FakeRepo + các hàm đọc mà `cashflow_result` và `cashflow_rest` dùng. Bộ lọc giống SQL: chi là `kind = expense` và
    `funding_source <> external`; thu là `kind = income` và `funding_source <> external`; không tính `transfer`."""

    def __init__(self, clock) -> None:
        super().__init__(clock)
        self.payday: dict[str, int | None] = {}
        self.cashflow_calls: list[tuple[str, date, date]] = []
        self.db = self  # `cashflow_rest` đọc chuỗi ngày qua `repo.db.query`

    def user_row(self, uid):
        if uid not in self.users:
            return None
        return {
            "clock_offset_days": self.users[uid]["offset"],
            "payday_day": self.payday.get(uid, 5),
        }

    def review_stats(self, uid):
        return {"pending_total": Decimal(0)}

    def cashflow(self, uid, from_date, to_date):
        self.cashflow_calls.append((uid, from_date, to_date))
        rows = [
            t
            for t in self.transactions.get(uid, [])
            if from_date <= t["app_date"] <= to_date and t["funding_source"] != "external"
        ]
        by_jar: dict[str, list] = {}
        income: dict[str, list] = {}
        for t in rows:
            if t["kind"] == "expense":
                s = by_jar.setdefault(t["jar_code"], [Decimal(0), 0])
                s[0] += -t["amount_vnd"]
                s[1] += 1
            elif t["kind"] == "income":
                s = income.setdefault(t["tx_type"], [Decimal(0), 0])
                s[0] += t["amount_vnd"]
                s[1] += 1
        return {
            "by_jar": [
                {"jar_code": k, "spent_vnd": v[0], "tx_count": v[1]}
                for k, v in sorted(by_jar.items())
            ],
            "income_by_type": [
                {"tx_type": k, "amount_vnd": v[0], "tx_count": v[1]}
                for k, v in sorted(income.items())
            ],
        }

    def query(self, sql, params, max_rows=None):
        assert sql == SQL_DAILY, sql
        start, days = params["from_date"], params["days"]
        out = []
        for i in range(days):
            d = start + timedelta(days=i)
            out.append({"day": d, "data": self.cashflow(params["uid"], d, d)})
        assert max_rows is None or len(out) <= max_rows
        return out

    def list_transactions(self, uid, *, jar=None, from_date=None, to_date=None, kind=None, tx_type=None,
                          needs_review=None, cursor=None, limit=20):  # fmt: skip
        rows = [
            t
            for t in self.transactions.get(uid, [])
            if (kind is None or t["kind"] == kind)
            and (from_date is None or t["app_date"] >= from_date)
            and (to_date is None or t["app_date"] <= to_date)
        ]
        rows.sort(key=lambda t: (t["occurred_at"], t["id"]), reverse=True)
        if cursor:
            rows = [t for t in rows if (t["occurred_at"], t["id"]) < (cursor[0], cursor[1])]
        return rows[: min(limit, 51)]


def tx(
    repo, uid, day, jar, amount, *, kind="expense", funding="jar", obligation=False, tx_type="spend"
):
    n = next(_seq)
    sign = -1 if kind == "expense" else 1
    repo.transactions[uid].append(
        {
            "id": str(uuid.UUID(int=n + 1)),
            "occurred_at": datetime(day.year, day.month, day.day, 3, 0, tzinfo=UTC)
            + timedelta(seconds=n),
            "app_date": day,
            "kind": kind,
            "jar_code": jar,
            "amount_vnd": Decimal(sign * amount),
            "funding_source": funding,
            "obligation_id": str(uuid.uuid4()) if obligation else None,
            "tx_type": tx_type,
        }
    )


def service_with_data():
    svc, base, clock = make_service()
    repo = CashflowRepo(clock)
    repo.users, repo.transactions = base.users, base.transactions
    svc.repo = repo
    d = date
    # kỳ trước (05/10 đến 04/11); ngày thứ 17 là 21/10
    tx(repo, MINH, d(2026, 10, 5), "an_uong", 9_000_000, kind="income", tx_type="salary")
    tx(repo, MINH, d(2026, 10, 6), "an_uong", 50_000)
    tx(repo, MINH, d(2026, 10, 6), "giai_tri", 1_000_000, obligation=True)
    tx(repo, MINH, d(2026, 10, 10), "giai_tri", 300_000, funding="credit")
    tx(repo, MINH, d(2026, 10, 21), "di_lai", 40_000)
    tx(repo, MINH, d(2026, 10, 22), "an_uong", 70_000)  # sau ngày thứ 17: chỉ ở previous_daily
    # kỳ này (05/11 tới hôm nay 21/11)
    tx(repo, MINH, d(2026, 11, 5), "an_uong", 9_000_000, kind="income", tx_type="salary")
    tx(repo, MINH, d(2026, 11, 6), "an_uong", 60_000)
    tx(repo, MINH, d(2026, 11, 6), "giai_tri", 1_000_000, obligation=True)
    tx(repo, MINH, d(2026, 11, 7), "an_uong", 80_000)
    tx(
        repo, MINH, d(2026, 11, 8), "an_uong", 999_000, funding="external"
    )  # chi ngoài ví: tool không tính
    tx(repo, MINH, d(2026, 11, 9), "giai_tri", 450_000, funding="credit")
    tx(repo, MINH, d(2026, 11, 10), "an_uong", 200_000, kind="transfer", tx_type="move")
    tx(repo, MINH, d(2026, 11, 12), "an_uong", 100_000, kind="income", tx_type="gift")
    tx(repo, MINH, d(2026, 11, 21), "di_lai", 20_000)
    # lan: chỉ có kỳ này
    tx(repo, LAN, d(2026, 11, 7), "an_uong", 33_000)
    return svc, repo


@pytest.fixture
def schema_ok(registry):
    def run(name, instance):
        v = Draft202012Validator(
            {"$ref": f"{OPENAPI_URI}#/components/schemas/{name}"}, registry=registry
        )
        errors = [f"{list(e.path)}: {e.message}" for e in v.iter_errors(instance)]
        assert not errors, errors

    return run


def get(svc, sub=MINH, **kw):
    res = handle_http(http_event("GET", "/cashflow", sub=sub, **kw), svc)
    return res["statusCode"], json.loads(res["body"])


# --- kỳ (thuần) ----------------------------------------------------------------------------------------------
def test_ky_luong_hien_tai_va_ky_truoc_cung_so_ngay():
    p = periods(5, TODAY)
    assert (p["kind"], p["start"], p["end"], p["day_index"], p["days_total"]) == (
        "pay_period", date(2026, 11, 5), date(2026, 12, 4), 17, 30,
    )  # fmt: skip
    assert (p["prev_start"], p["prev_to"], p["prev_end"]) == (
        date(2026, 10, 5),
        date(2026, 10, 21),
        date(2026, 11, 4),
    )


def test_ngay_luong_la_hom_nay_thi_ngay_thu_nhat():
    p = periods(5, date(2026, 12, 5))
    assert p["start"] == date(2026, 12, 5) and p["day_index"] == 1
    assert p["prev_start"] == p["prev_to"] == date(2026, 11, 5)


def test_ky_truoc_ngan_hon_thi_khong_qua_cuoi_ky_truoc():
    # lương ngày 31: kỳ trước 31/01 đến 27/02 (28 ngày), kỳ này 28/02 đến 30/03; hôm nay 30/03 là ngày thứ 31
    p = periods(31, date(2027, 3, 30))
    assert p["start"] == date(2027, 2, 28) and p["day_index"] == 31
    assert p["prev_start"] == date(2027, 1, 31) and p["prev_end"] == date(2027, 2, 27)
    assert p["prev_to"] == p["prev_end"]


def test_chua_khai_ngay_luong_thi_thang_duong_lich_nhu_tool():
    p = periods(None, TODAY)
    assert (p["kind"], p["start"], p["end"], p["prev_start"], p["prev_to"]) == (
        "calendar_month", date(2026, 11, 1), date(2026, 11, 30), date(2026, 10, 1), date(2026, 10, 21),
    )  # fmt: skip


# --- REST ------------------------------------------------------------------------------------------------------
def test_cung_so_voi_tool_qua_gateway(schema_ok):
    svc, _ = service_with_data()
    status, body = get(svc)
    assert status == 200, body
    schema_ok("CashflowResponse", body)
    tool = handle_gateway({"user_id": MINH}, _ctx(), svc)
    assert tool["status"] == "OK"
    data = tool["data"]
    cur = body["current"]
    for k in ("from_date", "to_date", "salary_income_vnd", "other_income_vnd", "spent_vnd"):
        assert cur[k] == data[k], k
    assert body["unclassified_pending_vnd"] == data["unclassified_pending_vnd"]
    assert {j["jar"]: (j["spent_vnd"], j["tx_count"]) for j in body["by_jar"] if j["tx_count"]} == {
        j["jar"]: (j["spent_vnd"], j["tx_count"]) for j in data["by_jar"]
    }
    # số của dữ liệu giả: chi ngoài ví, chuyển hũ, tiền vào không phải chi
    assert cur["spent_vnd"] == 60_000 + 1_000_000 + 80_000 + 450_000 + 20_000
    assert (cur["salary_income_vnd"], cur["other_income_vnd"]) == (9_000_000, 100_000)
    assert cur["net_vnd"] == 9_000_000 - cur["spent_vnd"]


def test_ky_truoc_tinh_toi_cung_so_ngay_bang_cung_ham(schema_ok):
    svc, repo = service_with_data()
    _, body = get(svc)
    prev = body["previous"]
    assert (prev["from_date"], prev["to_date"], prev["end_date"]) == (
        "2026-10-05",
        "2026-10-21",
        "2026-11-04",
    )
    assert prev["spent_vnd"] == 50_000 + 1_000_000 + 300_000 + 40_000  # không gồm 70.000 ngày 22/10
    assert (MINH, date(2026, 10, 5), date(2026, 10, 21)) in repo.cashflow_calls
    assert (MINH, date(2026, 11, 5), TODAY) in repo.cashflow_calls
    assert body["change"]["spent_vnd"] == body["current"]["spent_vnd"] - prev["spent_vnd"]
    jars = {j["jar"]: j for j in body["by_jar"]}
    assert jars["an_uong"]["previous_spent_vnd"] == 50_000
    assert jars["an_uong"]["change_vnd"] == 140_000 - 50_000
    assert jars["di_lai"]["previous_spent_vnd"] == 40_000 and jars["di_lai"]["spent_vnd"] == 20_000
    spent = [j["spent_vnd"] for j in body["by_jar"]]
    assert spent == sorted(spent, reverse=True)


def test_chuoi_theo_ngay_lu_ke_bang_tong_cua_tool():
    svc, _ = service_with_data()
    _, body = get(svc)
    daily = body["daily"]
    assert [d["day_index"] for d in daily] == list(range(1, 18))
    assert daily[0]["date"] == "2026-11-05" and daily[-1]["date"] == "2026-11-21"
    assert daily[-1]["cumulative_vnd"] == body["current"]["spent_vnd"]
    assert daily[1]["spent_vnd"] == 1_060_000 and daily[1]["obligation_vnd"] == 1_000_000
    assert daily[3]["spent_vnd"] == 0  # 08/11 chỉ có chi ngoài ví
    pd = body["previous_daily"]
    assert len(pd) == 31 and pd[-1]["date"] == "2026-11-04"
    assert pd[16]["cumulative_vnd"] == body["previous"]["spent_vnd"]
    assert (
        pd[17]["spent_vnd"] == 70_000
        and pd[-1]["cumulative_vnd"] == body["previous"]["spent_vnd"] + 70_000
    )


def test_tach_nghia_vu_va_tra_sau():
    svc, _ = service_with_data()
    _, body = get(svc)
    assert body["split_complete"] is True
    cur, prev = body["current"], body["previous"]
    assert (cur["obligation_vnd"], cur["credit_vnd"]) == (1_000_000, 450_000)
    assert cur["regular_spent_vnd"] == cur["spent_vnd"] - 1_000_000
    assert (prev["obligation_vnd"], prev["credit_vnd"]) == (1_000_000, 300_000)
    assert body["change"]["regular_vnd"] == cur["regular_spent_vnd"] - prev["regular_spent_vnd"]
    g = next(j for j in body["by_jar"] if j["jar"] == "giai_tri")
    assert (g["obligation_vnd"], g["credit_vnd"], g["spent_vnd"]) == (1_000_000, 450_000, 1_450_000)
    assert body["daily"][-1]["regular_cumulative_vnd"] == cur["regular_spent_vnd"]
    assert body["previous_daily"][16]["regular_cumulative_vnd"] == prev["regular_spent_vnd"]


def test_qua_nhieu_trang_thi_bo_phan_tach_khong_tra_so_lech(monkeypatch, schema_ok):
    svc, repo = service_with_data()
    for i in range(60):  # hơn một trang 51 dòng
        tx(repo, MINH, date(2026, 11, 13), "an_uong", 1_000 + i)
    monkeypatch.setattr(cashflow_rest, "SPLIT_MAX_PAGES", 1)
    _, body = get(svc)
    schema_ok("CashflowResponse", body)
    assert body["split_complete"] is False
    assert "obligation_vnd" not in body["current"] and "regular_spent_vnd" not in body["previous"]
    assert "regular_vnd" not in body["change"]
    assert all("obligation_vnd" not in j and "credit_vnd" not in j for j in body["by_jar"])
    assert all("regular_cumulative_vnd" not in d for d in body["daily"] + body["previous_daily"])
    # tổng vẫn đúng của tool
    assert body["current"]["spent_vnd"] == svc.cashflow_result(MINH)["data"]["spent_vnd"]
    monkeypatch.setattr(cashflow_rest, "SPLIT_MAX_PAGES", 20)
    _, again = get(svc)
    assert again["split_complete"] is True  # nhiều trang vẫn đọc hết qua con trỏ
    assert again["current"]["regular_spent_vnd"] == again["current"]["spent_vnd"] - 1_000_000


def test_phan_tach_lech_so_dong_cua_tool_thi_bo(monkeypatch):
    svc, repo = service_with_data()
    real = repo.list_transactions

    def drop_one(uid, **kw):  # một dòng chi biến mất giữa hai lần đọc (ghi chen giữa)
        rows = real(uid, **kw)
        return (
            [r for r in rows if r["jar_code"] != "di_lai"] if kw.get("kind") == "expense" else rows
        )

    monkeypatch.setattr(repo, "list_transactions", drop_one)
    _, body = get(svc)
    assert body["split_complete"] is False and "obligation_vnd" not in body["current"]


def test_chua_co_du_lieu_tu_dau_ky_truoc_thi_khong_so(schema_ok):
    svc, _ = service_with_data()
    status, body = get(svc, sub=LAN)
    assert status == 200
    schema_ok("CashflowResponse", body)
    assert "previous" not in body and "change" not in body and "previous_daily" not in body
    assert body["by_jar"] == [
        {
            "jar": "an_uong",
            "name": "Ăn uống",
            "spent_vnd": 33_000,
            "tx_count": 1,
            "obligation_vnd": 0,
            "credit_vnd": 0,
        }
    ]


def test_ky_nay_chua_chi_gi_va_ky_truoc_co_chi(schema_ok):
    svc, repo = service_with_data()
    repo.transactions[MINH] = [
        t for t in repo.transactions[MINH] if t["app_date"] < date(2026, 11, 5)
    ]
    _, body = get(svc)
    schema_ok("CashflowResponse", body)
    assert body["current"]["spent_vnd"] == 0 and body["daily"][-1]["cumulative_vnd"] == 0
    # hũ chỉ có chi ở kỳ trước vẫn hiện, chi 0, chênh âm
    jars = {j["jar"]: j for j in body["by_jar"]}
    assert jars["giai_tri"]["spent_vnd"] == 0 and jars["giai_tri"]["change_vnd"] == -1_300_000
    assert body["change"]["spent_vnd"] == -body["previous"]["spent_vnd"]


def test_tai_khoan_trang(schema_ok):
    svc, _ = service_with_data()
    status, body = get(svc, sub="sub-chua-co")
    assert status == 200
    schema_ok("CashflowResponse", body)
    assert body["period"]["kind"] == "calendar_month" and body["by_jar"] == []
    assert body["current"]["spent_vnd"] == 0 and "previous" not in body
    assert len(body["daily"]) == body["period"]["day_index"]


def test_danh_tinh_chi_tu_sub_khong_tu_query_hay_than(schema_ok):
    svc, _ = service_with_data()
    ev = http_event(
        "GET", "/cashflow", sub=LAN, query={"user_id": MINH}, body={"user_id": MINH, "sub": MINH}
    )
    body = json.loads(handle_http(ev, svc)["body"])
    assert body["current"]["spent_vnd"] == 33_000  # của lan
    status, err = get(svc, sub=None)
    assert status == 401 and err["error"]["code"] == "UNAUTHENTICATED"
    schema_ok("ErrorResponse", err)


def _ctx():
    from ledger_fakes import gateway_context

    return gateway_context("ledger___get_cashflow_summary")


# --- fixture hợp đồng (sinh từ server thật trên PostgreSQL cục bộ, persona minh và khoa) ----------------------------
@pytest.mark.parametrize(
    "name", ["CashflowResponse.minh", "CashflowResponse.khoa_chua_co_ky_truoc"]
)
def test_fixture_nhat_quan_tong_theo_hu_theo_ngay(name):
    from conftest import CONTRACTS, load_json

    b = load_json(CONTRACTS / "fixtures" / "rest" / f"{name}.json")
    cur, n = b["current"], b["period"]["day_index"]
    assert sum(j["spent_vnd"] for j in b["by_jar"]) == cur["spent_vnd"]
    assert len(b["daily"]) == n and b["daily"][-1]["cumulative_vnd"] == cur["spent_vnd"]
    assert cur["net_vnd"] == cur["salary_income_vnd"] - cur["spent_vnd"]
    if b["split_complete"]:
        assert cur["regular_spent_vnd"] == cur["spent_vnd"] - cur["obligation_vnd"]
        assert b["daily"][-1]["regular_cumulative_vnd"] == cur["regular_spent_vnd"]
    assert ("previous" in b) == ("change" in b) == ("previous_daily" in b)
    if "previous" in b:
        prev = b["previous"]
        assert b["previous_daily"][n - 1]["cumulative_vnd"] == prev["spent_vnd"]
        assert b["change"]["spent_vnd"] == cur["spent_vnd"] - prev["spent_vnd"]
        assert all(j["change_vnd"] == j["spent_vnd"] - j["previous_spent_vnd"] for j in b["by_jar"])
    else:
        assert all("previous_spent_vnd" not in j for j in b["by_jar"])
