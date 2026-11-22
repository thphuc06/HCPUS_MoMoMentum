"""Phase 5 (F6) trên PostgreSQL thật cục bộ: nguồn trả `external` (migration 0050) qua MỌI đường đọc sổ cái, bất biến độ phủ của
minh, lan, khoa so với bản 0009, khử trùng với sổ cái, hàm của luồng nạp, RLS và đặt lại demo.

Chạy cùng bộ local_pg (lệnh ở docstring của conftest.py). Mỗi test ứng với một dòng của bảng rà đường đọc ở contracts/README.md
mục "Phase 5 (F6): nạp dữ liệu".
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal

import psycopg
import pytest
from conftest import REPO, _load
from pipeline_helpers import make_settings

from yofina_core import ingest
from yofina_core.errors import ErrorCode, YofinaError
from yofina_forecast.consumer import plan_event
from yofina_forecast.events import LedgerEvent
from yofina_forecast.inputs import Context, build_inputs
from yofina_ledger.repo import RESET_DELETES, SQL_RECOMPUTE_BALANCES
from yofina_ml import quality
from yofina_ml.api import forecast_user
from yofina_ml.types import CoverageInputs

MINH, LAN, KHOA = "sub-minh", "sub-lan", "sub-khoa"
#: lỗi ràng buộc hoặc RLS từ DB: psycopg.Error, hoặc YofinaError khi DataApi dịch lỗi
DB_ERRORS = (psycopg.Error, YofinaError)
TZ = "Asia/Ho_Chi_Minh"
WIN = 330
EXT_DAY = date(2026, 11, 19)  # trước ngày mô phỏng 21/11 (lịch sử chi lấy tới hôm qua)
AMOUNT = 150_000

SQL_CONTEXT = (
    "SELECT section, jar_code, payload FROM {fn}(CAST(:uid AS text), CAST(:now AS timestamptz), CAST(:tz AS text), "
    "CAST(:win AS integer))"
)
SQL_DAILY = "SELECT * FROM {fn}(CAST(:uid AS text), CAST(:f AS date), CAST(:t AS date))"


# --- hạ tầng: bản 0005/0009 của hai hàm dưới tên khác, để so với bản 0050 trên cùng dữ liệu ----------------------------
@pytest.fixture(scope="module")
def legacy(pg):
    """Tạo `app_get_daily_spend_v0005` và `app_get_forecast_context_v0009` từ đúng văn bản của 0005 và 0009 (chỉ đổi tên)."""
    sqlsplit = _load("sqlsplit", REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py")

    def stmt(file: str, name: str) -> str:
        sql = (REPO / "db" / "migrations" / file).read_text(encoding="utf-8")
        return next(s for s in sqlsplit.split_migration(sql) if f"FUNCTION {name}(" in s)

    daily = stmt("0005_wallet.sql", "app_get_daily_spend").replace(
        "FUNCTION app_get_daily_spend(", "FUNCTION app_get_daily_spend_v0005("
    )
    ctx = (
        stmt("0009_forecast_pipeline.sql", "app_get_forecast_context")
        .replace("FUNCTION app_get_forecast_context(", "FUNCTION app_get_forecast_context_v0009(")
        .replace("app_get_daily_spend(p_user_id", "app_get_daily_spend_v0005(p_user_id")
    )
    assert "app_get_daily_spend_v0005(p_user_id" in ctx and "funding_source = 'jar'" in daily
    with psycopg.connect(pg["master"], autocommit=True) as m:
        m.execute(daily)
        m.execute(ctx)
        m.execute(
            "GRANT EXECUTE ON FUNCTION app_get_daily_spend_v0005(text, date, date) TO yofina_app"
        )
        m.execute(
            "GRANT EXECUTE ON FUNCTION app_get_forecast_context_v0009(text, timestamptz, text, integer) TO yofina_app"
        )
    return {"ctx": "app_get_forecast_context_v0009", "daily": "app_get_daily_spend_v0005"}


def context(env, user, fn="app_get_forecast_context"):
    rows = env.db.query(
        SQL_CONTEXT.format(fn=fn),
        {"uid": user, "now": env.clock.now, "tz": TZ, "win": WIN},
        max_rows=200,
    )
    return [
        {"section": r["section"], "jar_code": r["jar_code"], "payload": r["payload"]} for r in rows
    ]


def meta(rows):
    return next(r["payload"] for r in rows if r["section"] == "meta")


def jar_payload(rows, code):
    return next(r["payload"] for r in rows if r["section"] == "jar" and r["jar_code"] == code)


def daily(env, user, fn="app_get_daily_spend", start=date(2026, 9, 1), end=date(2026, 11, 20)):
    rows = env.db.query(SQL_DAILY.format(fn=fn), {"uid": user, "f": start, "t": end}, max_rows=5000)
    return {(r["jar_code"], r["day"]): (int(r["spent_vnd"]), int(r["tx_count"])) for r in rows}


def balances(env, user):
    return {j["code"]: int(j["balance_vnd"]) for j in env.repo.jar_view(user).jars}


def insert_tx(env, user, *, kind="expense", jar="an_uong", amount=AMOUNT, funding="external", day=EXT_DAY,
              merchant="Cơm tấm Phúc Lộc", **extra):  # fmt: skip
    tid = str(uuid.uuid4())
    signed = -amount if kind == "expense" else amount
    cols = {
        # occurred_at là thời điểm THẬT lúc ghi (confirm_rows ghi bây giờ), app_date là ngày mô phỏng của dòng trên tệp
        "id": tid, "user_id": user, "occurred_at": env.clock.now, "app_date": day, "kind": kind,
        "jar_code": jar, "amount_vnd": signed, "merchant": merchant, "source": "ingest",
        "tx_type": "other_expense" if kind == "expense" else "income_other", "funding_source": funding,
        **extra,
    }  # fmt: skip
    names = ", ".join(cols)
    marks = ", ".join(["%s"] * len(cols))
    with env.master() as m:
        m.execute(f"INSERT INTO transactions ({names}) VALUES ({marks})", list(cols.values()))
    return tid


def first_spending_jar(env, user):
    return next(j["code"] for j in env.repo.jar_view(user).jars if j["kind"] == "spending")


# =====================================================================================================
# Ràng buộc sổ cái
# =====================================================================================================
def test_rang_buoc_funding_external(env):
    env.reset(MINH)
    insert_tx(env, MINH)  # chi ngoài ví có hũ
    insert_tx(env, MINH, kind="income", jar=None, amount=2_000_000)  # thu nhập ngoài ví
    bad = [
        dict(kind="transfer", transfer_id=str(uuid.uuid4())),  # không chuyển hũ ngoài ví
        dict(jar=None),  # chi ngoài ví phải có hũ
        dict(
            obligation_id=None,
            funding="external",
            kind="income",
            jar=None,
            transfer_id=str(uuid.uuid4()),
        ),
        dict(funding="credit", kind="income", jar=None),  # credit vẫn chỉ cho chi
        dict(funding="bank"),
    ]
    for kw in bad:
        with pytest.raises(psycopg.errors.CheckViolation):
            insert_tx(env, MINH, **kw)


# =====================================================================================================
# Đường đọc: số dư hũ, tổng ví, giao dịch gần đây, cần xem lại -> KHÔNG đổi
# =====================================================================================================
def test_so_du_hu_va_dung_lai_so_du_khong_doi(env):
    env.reset(MINH)
    before = balances(env, MINH)
    insert_tx(env, MINH)
    insert_tx(env, MINH, kind="income", jar="tien_vao_khac", amount=2_000_000)
    assert balances(env, MINH) == before  # app_get_jar_state
    with env.db.transaction(
        MINH
    ) as tx:  # SQL_RECOMPUTE_BALANCES (đặt lại demo dựng số dư từ sổ cái)
        tx.execute(SQL_RECOMPUTE_BALANCES, {"uid": MINH})
    assert balances(env, MINH) == before
    listed = {r["code"]: int(r["balance_vnd"]) for r in env.db.query(
        "SELECT * FROM app_list_jars(:uid)", {"uid": MINH}, max_rows=40)}  # fmt: skip
    assert listed == before  # app_list_jars
    res = env.svc.get_jar_balances_result(MINH, trace_id="t" * 8)  # tool get_jar_balances
    assert {j["code"]: j["balance_vnd"] for j in res["data"]["jars"]} == {
        c: b for c, b in before.items() if c not in ("tien_vao_khac", "chua_phan_loai")
    }


def test_tong_quan_tong_so_du_gan_day_va_can_xem_lai_khong_doi(env):
    env.reset(MINH)
    ov0 = env.svc.overview_response(MINH)
    stats0 = env.repo.review_stats(MINH)
    unc0 = [r["id"] for r in env.repo.unclassified(MINH, 50)]
    tid = insert_tx(env, MINH, needs_review=False)
    ov1 = env.svc.overview_response(MINH)
    assert ov1["balance"] == ov0["balance"]  # tổng ví
    assert (
        ov1["recent_transactions"] == ov0["recent_transactions"]
    )  # gần đây của VÍ: không gồm external
    assert tid not in {t["id"] for t in ov1["recent_transactions"]}
    assert ov1["needs_review_count"] == ov0["needs_review_count"]
    assert env.repo.review_stats(MINH) == stats0  # app_get_review_stats
    assert [r["id"] for r in env.repo.unclassified(MINH, 50)] == unc0  # app_get_unclassified
    extras = env.db.query(
        "SELECT app_get_overview_extras(:uid, CAST(:d AS date)) AS data", {"uid": MINH, "d": date(2026, 11, 21)},
        max_rows=1,
    )[0]["data"]  # fmt: skip
    assert tid not in {t["id"] for t in extras["recent_transactions"]}


def test_lich_su_va_chi_tiet_hu_co_dong_external_kem_nguon(env):
    env.reset(MINH)
    tid = insert_tx(env, MINH)
    page = env.svc.transactions_response(MINH, jar="an_uong", limit=50)  # app_list_transactions
    row = next(t for t in page["transactions"] if t["id"] == tid)
    assert row["funding_source"] == "external" and row["amount_vnd"] == -AMOUNT
    detail = env.svc.jar_detail_response(MINH, "an_uong")  # app_get_jar_detail
    assert any(
        t["id"] == tid and t["funding_source"] == "external" for t in detail["recent_transactions"]
    )
    assert detail["jar"]["balance_vnd"] == balances(env, MINH)["an_uong"]
    one = env.db.query("SELECT * FROM app_get_transaction(:uid, CAST(:id AS uuid))", {"uid": MINH, "id": tid},
                       max_rows=1)[0]  # fmt: skip
    assert one["funding_source"] == "external"  # app_get_transaction


def test_dong_tien_cua_vi_khong_gom_external_va_tach_rieng(env):
    env.reset(MINH)
    f, t = date(2026, 11, 1), date(2026, 11, 21)
    base = env.svc.cashflow_result(MINH, from_date=f.isoformat(), to_date=t.isoformat())["data"]
    insert_tx(env, MINH)
    insert_tx(env, MINH, kind="income", jar=None, amount=2_000_000)
    after = env.svc.cashflow_result(MINH, from_date=f.isoformat(), to_date=t.isoformat())["data"]
    assert after == base  # tool get_cashflow_summary: luồng tiền của ví không đổi
    raw = env.repo.cashflow(MINH, f, t)
    assert raw["external"] == {"spent_vnd": AMOUNT, "income_vnd": 2_000_000, "tx_count": 2}


# =====================================================================================================
# Đầu vào dự báo: chi của hũ ĐỔI đúng bằng số tiền; độ phủ đổi theo công thức mới
# =====================================================================================================
def test_daily_spend_va_spend_cua_context_doi_dung_so_tien(env):
    env.reset(MINH)
    d0, c0 = daily(env, MINH), context(env, MINH)
    insert_tx(env, MINH)
    d1, c1 = daily(env, MINH), context(env, MINH)
    key = ("an_uong", EXT_DAY)
    s0, n0 = d0.get(key, (0, 0))
    assert d1[key] == (s0 + AMOUNT, n0 + 1)
    assert {k: v for k, v in d1.items() if k != key} == {k: v for k, v in d0.items() if k != key}
    m0 = meta(c0)
    idx = (EXT_DAY - date.fromisoformat(m0["history_start"])).days
    a0, a1 = jar_payload(c0, "an_uong")["spend"], jar_payload(c1, "an_uong")["spend"]
    assert a1[idx] - a0[idx] == AMOUNT and sum(a1) - sum(a0) == AMOUNT
    assert jar_payload(c1, "an_uong")["balance_vnd"] == jar_payload(c0, "an_uong")["balance_vnd"]
    assert jar_payload(c1, "di_lai") == jar_payload(c0, "di_lai")
    cov0, cov1 = m0["coverage"], meta(c1)["coverage"]
    assert cov1["spend_vnd"] - cov0["spend_vnd"] == AMOUNT
    assert cov1["income_vnd"] == cov0["income_vnd"]
    assert (cov1["balance_start_vnd"], cov1["balance_end_vnd"]) == (
        cov0["balance_start_vnd"],
        cov0["balance_end_vnd"],
    )


def test_thu_nhap_ngoai_vi_vao_do_phu_khong_doi_so_du_tien_vao_khac(env):
    env.reset(MINH)
    before = balances(env, MINH)
    c0 = meta(context(env, MINH))["coverage"]
    insert_tx(env, MINH, kind="income", jar="tien_vao_khac", amount=2_000_000)
    assert balances(env, MINH)["tien_vao_khac"] == before["tien_vao_khac"]
    c1 = meta(context(env, MINH))["coverage"]
    assert c1["income_vnd"] - c0["income_vnd"] == 2_000_000 and c1["spend_vnd"] == c0["spend_vnd"]


def test_credit_va_dong_gan_nghia_vu_van_khong_vao_lich_su_chi(env):
    env.reset(MINH)
    d0 = daily(env, MINH)
    insert_tx(env, MINH, funding="credit")
    assert daily(env, MINH) == d0


# =====================================================================================================
# BẤT BIẾN: người dùng không có dòng external -> mọi số Y HỆT bản 0009
# =====================================================================================================
@pytest.mark.parametrize("user", [MINH, LAN, KHOA])
def test_khong_co_external_thi_context_y_het_ban_0009(env, legacy, user):
    env.reset(user)
    new, old = context(env, user), context(env, user, legacy["ctx"])
    assert new == old and new  # meta (gồm coverage), mọi dòng jar (gồm spend), mọi nghĩa vụ
    assert daily(env, user) == daily(env, user, legacy["daily"])
    cov = env.db.query(
        "SELECT * FROM app_get_data_coverage(CAST(:uid AS text), CAST(:now AS timestamptz), CAST(:tz AS text), "
        "CAST(:win AS integer))", {"uid": user, "now": env.clock.now, "tz": TZ, "win": WIN}, max_rows=1,
    )[0]  # fmt: skip
    m = meta(old)
    assert {
        k: int(cov[k]) for k in ("income_vnd", "spend_vnd", "balance_start_vnd", "balance_end_vnd")
    } == {
        k: int(m["coverage"][k])
        for k in ("income_vnd", "spend_vnd", "balance_start_vnd", "balance_end_vnd")
    }
    assert (
        cov["history_start"].isoformat() == m["history_start"]
        and int(cov["external_spend_vnd"]) == 0
    )


@pytest.mark.parametrize("user", [MINH, LAN, KHOA])
def test_khong_co_external_thi_nhan_tin_cay_va_uoc_luong_ban_dau_khong_doi(env, legacy, user):
    env.reset(user)
    settings = make_settings(n_paths_full=400, n_paths_fast=200)
    runs = []
    for fn in (legacy["ctx"], "app_get_forecast_context"):
        ctx = Context.from_rows(context(env, user, fn))
        built = build_inputs(ctx, settings, user, n_paths=400)
        res = forecast_user(built.inputs)
        runs.append((built.inputs, res.run.confidence_label, res.run.is_initial_estimate, res.run.data_coverage,
                     {j.summary.jar_code: j.summary.confidence_band for j in res.jars}))  # fmt: skip
    assert runs[0] == runs[1]
    inputs, label, initial, coverage, bands = runs[1]
    assert coverage == quality.data_coverage(inputs.coverage)
    assert initial is (user == KHOA)  # khoa 18 ngày lịch sử: ước lượng ban đầu
    if user == KHOA:
        assert label == "low" and set(bands.values()) == {"low"}


def test_do_phu_hien_tai_cung_so_voi_du_bao_sau_khi_co_external(env):
    env.reset(MINH)
    insert_tx(env, MINH)
    insert_tx(env, MINH, kind="income", jar=None, amount=2_000_000)
    m = meta(context(env, MINH))
    row = env.db.query(
        "SELECT * FROM app_get_data_coverage(CAST(:uid AS text), CAST(:now AS timestamptz), CAST(:tz AS text), "
        "CAST(:win AS integer))", {"uid": MINH, "now": env.clock.now, "tz": TZ, "win": WIN}, max_rows=1,
    )[0]  # fmt: skip
    expect = quality.data_coverage(
        CoverageInputs(**{k: int(m["coverage"][k]) for k in m["coverage"]})
    )
    assert ingest.coverage_ratio(row) == expect
    assert int(row["external_spend_vnd"]) == AMOUNT and int(row["external_income_vnd"]) == 2_000_000


# =====================================================================================================
# assign_jar với dòng external: đổi hũ nhưng KHÔNG chuyển tiền; sự kiện -> consumer chạy đầy đủ
# =====================================================================================================
def test_assign_jar_dong_external_khong_chuyen_tien_va_su_kien_chay_day_du(env):
    env.reset(MINH)
    before = balances(env, MINH)
    tid = insert_tx(env, MINH)
    env.events.sent.clear()
    receipt = env.act(MINH, "assign_jar", {"transaction_id": tid, "jar": "giai_tri"})
    assert receipt["type"] == "receipt_action"
    assert balances(env, MINH) == before  # moves_money = funding_source == 'jar' -> False
    tx = env.db.query("SELECT * FROM app_get_transaction(:uid, CAST(:id AS uuid))", {"uid": MINH, "id": tid},
                      max_rows=1)[0]  # fmt: skip
    assert tx["jar_code"] == "giai_tri" and tx["funding_source"] == "external"
    ev = next(e for e in env.events.sent if e.detail_type == "transaction.recorded")
    assert ev.detail["funding_source"] == "external" and ev.detail["effects"] == []
    plan = plan_event(LedgerEvent(ev.detail_type, ev.detail["event_id"], MINH, ev.detail))
    assert plan.full  # không chỉnh nhanh, không trừ số dư


def test_consumer_external_luon_chay_day_du():
    d = {
        "event_id": "e1",
        "user_id": "u",
        "funding_source": "external",
        "jar_codes": ["an_uong"],
        "kind": "expense",
    }
    assert plan_event(LedgerEvent("transaction.recorded", "e1", "u", d)).full


def test_record_transaction_khong_ghi_duoc_external(env):
    env.reset(MINH)
    with pytest.raises(YofinaError) as e:
        env.act(
            MINH,
            "record_transaction",
            {"kind": "expense", "amount_vnd": 1000, "jar": "an_uong", "funding": "external"},
        )
    assert e.value.code == ErrorCode.PARAMS_INVALID


# =====================================================================================================
# Khử trùng chặt: cùng số tiền tuyệt đối, cùng kind, lệch ngày trong cửa sổ, MỌI nguồn trả
# =====================================================================================================
SQL_MATCH = (
    "SELECT * FROM app_find_ingest_matches(:uid, CAST(:rows AS jsonb), CAST(:win AS integer))"
)


def matches(env, user, rows, win):
    return env.db.query(
        SQL_MATCH, {"uid": user, "rows": json.dumps(rows), "win": win}, max_rows=2000
    )


def test_khu_trung_moi_nguon_tra_cua_so_la_tham_so(env):
    env.reset(MINH)
    jar_tx = insert_tx(
        env, MINH, funding="jar", amount=123_457, day=date(2026, 11, 18), merchant="Phở Hà Nội"
    )
    ext_tx = insert_tx(env, MINH, amount=98_765, day=date(2026, 11, 10), merchant="GRAB *TRIP")
    cr_tx = insert_tx(
        env, MINH, funding="credit", amount=77_777, day=date(2026, 11, 12), merchant="Tiki"
    )
    cands = [
        {
            "idx": 1,
            "app_date": "2026-11-20",
            "amount_vnd": 123457,
            "counterparty": "pho ha noi",
            "kind": "expense",
        },
        {
            "idx": 2,
            "app_date": "2026-11-10",
            "amount_vnd": 98765,
            "counterparty": "",
            "kind": "expense",
        },
        {
            "idx": 3,
            "app_date": "2026-11-13",
            "amount_vnd": 77777,
            "counterparty": "Shopee",
            "kind": "expense",
        },
        {
            "idx": 4,
            "app_date": "2026-11-20",
            "amount_vnd": 123457,
            "counterparty": "Phở",
            "kind": "income",
        },
    ]
    got = {(r["idx"], str(r["transaction_id"])): r for r in matches(env, MINH, cands, 3)}
    assert got[(1, jar_tx)]["funding_source"] == "jar" and got[(1, jar_tx)]["day_diff"] == -2
    assert got[(1, jar_tx)]["counterparty_match"] is True
    assert (
        got[(2, ext_tx)]["funding_source"] == "external"
        and got[(2, ext_tx)]["counterparty_match"] is False
    )
    assert (
        got[(3, cr_tx)]["funding_source"] == "credit"
        and got[(3, cr_tx)]["counterparty_match"] is False
    )
    assert not any(k[0] == 4 for k in got)  # khác kind
    narrow = {(r["idx"], str(r["transaction_id"])) for r in matches(env, MINH, cands, 1)}
    assert (1, jar_tx) not in narrow and (2, ext_tx) in narrow and (3, cr_tx) in narrow
    assert matches(env, LAN, cands, 3) == [] or all(  # RLS: không thấy giao dịch của người khác
        str(r["transaction_id"]) not in {jar_tx, ext_tx, cr_tx} for r in matches(env, LAN, cands, 3)
    )


def test_dedupe_key_so_cai_chan_ghi_hai_lan(env):
    env.reset(MINH)
    key = ingest.row_dedupe_key(
        app_date=EXT_DAY, amount_vnd=AMOUNT, counterparty="Cơm tấm", content_sha256="a" * 64, seq=1
    )
    insert_tx(env, MINH, dedupe_key=key)
    with pytest.raises(psycopg.errors.UniqueViolation):
        insert_tx(env, MINH, dedupe_key=key)


# =====================================================================================================
# Hàm của luồng nạp (role yofina_app, RLS thật)
# =====================================================================================================
def call(env, sql, params, n=500):
    return env.db.query(sql, params, max_rows=n)


def new_job(env, user, kind="image"):
    jid = str(uuid.uuid4())
    row = call(env, "SELECT * FROM app_create_ingest_job(:uid, CAST(:id AS uuid), :k, :key, :mime, CAST(:sz AS bigint))",
               {"uid": user, "id": jid, "k": kind, "key": f"{user}/{jid}", "mime": "image/png", "sz": 1000})[0]  # fmt: skip
    assert row["status"] == "awaiting_upload"
    return jid


def update(env, user, jid, status, progress=None, patch=None):
    return call(env, "SELECT * FROM app_update_ingest_job(:uid, CAST(:id AS uuid), :st, CAST(:p AS integer), CAST(:patch AS jsonb))",
                {"uid": user, "id": jid, "st": status, "p": progress, "patch": json.dumps(patch or {})})  # fmt: skip


def rows_payload(sha, n=3):
    out = []
    for i in range(1, n + 1):
        out.append({
            "seq": i, "kind": "expense", "app_date": "2026-11-18", "amount_vnd": 10000 * i, "counterparty": f"Quán {i}",
            "description": "Thanh toán thẻ", "extract_confidence": 0.95, "suggested_jar_code": "an_uong",
            "jar_confidence": 0.9, "jar_source": "type_map", "review_status": "auto_added",
            "dedupe_key": ingest.row_dedupe_key(app_date="2026-11-18", amount_vnd=10000 * i, counterparty=f"Quán {i}",
                                                content_sha256=sha, seq=i),
        })  # fmt: skip
    return out


def insert_rows(env, user, jid, rows):
    return call(env, "SELECT * FROM app_insert_ingest_rows(:uid, CAST(:id AS uuid), CAST(:rows AS jsonb))",
                {"uid": user, "id": jid, "rows": json.dumps(rows)})  # fmt: skip


def get_job(env, user, jid):
    rows = call(
        env,
        "SELECT * FROM app_get_ingest_job(:uid, CAST(:id AS uuid), 200)",
        {"uid": user, "id": jid},
    )
    job = next((r["payload"] for r in rows if r["section"] == "job"), None)
    return job, [r["payload"] for r in rows if r["section"] == "row"]


def test_vong_doi_job_chuyen_trang_thai_va_tien_do(env):
    env.reset(MINH)
    jid = new_job(env, MINH)
    assert update(env, MINH, jid, "processing") == []  # chưa queued thì không nhảy sang processing
    assert (
        update(env, MINH, jid, "queued", 5, {"content_sha256": "b" * 64, "size_bytes": 999})[0][
            "status"
        ]
        == "queued"
    )
    assert update(env, MINH, jid, "processing", 40)[0]["progress"] == 40
    assert update(env, MINH, jid, "processing", 10)[0]["progress"] == 40  # tiến độ không lùi
    assert (
        update(
            env, MINH, jid, "review", 100, {"rows_total": 3, "rows_auto_added": 3, "model": "m"}
        )[0]["status"]
        == "review"
    )
    done = update(env, MINH, jid, "done", None, {"coverage_before": 0.62, "coverage_after": 0.81})[
        0
    ]
    assert done["progress"] == 100 and done["finished_at"] is not None
    assert (
        update(env, MINH, jid, "failed", None, {"error_code": "INTERNAL_ERROR"}) == []
    )  # đã kết thúc thì không đổi
    job, _ = get_job(env, MINH, jid)
    assert job["content_sha256"] == "b" * 64 and Decimal(str(job["coverage_after"])) == Decimal(
        "0.81"
    )
    with pytest.raises(DB_ERRORS):  # failed bắt buộc error_code
        update(env, MINH, new_job(env, MINH), "failed")


def test_chen_dong_khu_trung_khi_nap_lai_cung_tep_va_rls(env):
    env.reset(MINH)
    env.reset(LAN)
    sha = "c" * 64
    jid = new_job(env, MINH)
    first = insert_rows(env, MINH, jid, rows_payload(sha))
    assert [r["seq"] for r in first] == [1, 2, 3]
    jid2 = new_job(env, MINH)  # nạp lại cùng tệp: cùng khóa từng dòng -> không dòng thứ hai
    assert insert_rows(env, MINH, jid2, rows_payload(sha)) == []
    job, rows = get_job(env, MINH, jid)
    assert job["status"] == "awaiting_upload" and [r["seq"] for r in rows] == [1, 2, 3]
    assert all("raw" not in k for r in rows for k in r)
    assert get_job(env, LAN, jid) == (None, [])  # RLS: người khác không thấy
    assert call(env, "SELECT * FROM app_list_ingest_jobs(:uid, 5)", {"uid": LAN}) == []
    assert len(call(env, "SELECT * FROM app_list_ingest_jobs(:uid, 5)", {"uid": MINH})) == 2
    # lan không chèn được dòng vào job của minh (khóa ngoại theo user_id, RLS)
    with pytest.raises(DB_ERRORS):
        insert_rows(env, LAN, jid, rows_payload("d" * 64))


def test_job_loi_thi_xoa_dong_mo_de_nap_lai_duoc(env):
    env.reset(MINH)
    sha = "e" * 64
    jid = new_job(env, MINH)
    insert_rows(env, MINH, jid, rows_payload(sha, 2))
    assert (
        update(env, MINH, jid, "rejected", None, {"error_code": "INGEST_NOT_FINANCIAL"})[0][
            "status"
        ]
        == "rejected"
    )
    assert get_job(env, MINH, jid)[1] == []
    assert len(insert_rows(env, MINH, new_job(env, MINH), rows_payload(sha, 2))) == 2


def test_cung_noi_dung_tep_chi_mot_job_con_song(env):
    env.reset(MINH)
    sha = "f" * 64
    a, b = new_job(env, MINH), new_job(env, MINH)
    update(env, MINH, a, "queued", None, {"content_sha256": sha})
    found = call(
        env, "SELECT * FROM app_find_ingest_job_by_content(:uid, :sha)", {"uid": MINH, "sha": sha}
    )
    assert [str(r["id"]) for r in found] == [a]
    with pytest.raises(DB_ERRORS):
        update(env, MINH, b, "queued", None, {"content_sha256": sha})
    update(env, MINH, a, "failed", None, {"error_code": "INTERNAL_ERROR"})
    assert update(env, MINH, b, "queued", None, {"content_sha256": sha})[0]["status"] == "queued"


def test_doi_hu_mot_dong_chi_doi_de_xuat(env):
    env.reset(MINH)
    jid = new_job(env, MINH)
    rid = str(insert_rows(env, MINH, jid, rows_payload("1" * 64, 1))[0]["row_id"])
    sql = "SELECT * FROM app_set_ingest_row_jar(:uid, CAST(:id AS uuid), :jar)"
    assert call(env, sql, {"uid": MINH, "id": rid, "jar": "giai_tri"}) == []  # job chưa ở review
    for st in ("queued", "processing", "review"):
        update(env, MINH, jid, st)
    before = balances(env, MINH)
    assert call(env, sql, {"uid": MINH, "id": rid, "jar": "tien_vao_khac"}) == []  # hũ hệ thống
    assert call(env, sql, {"uid": MINH, "id": rid, "jar": "khong_co"}) == []
    got = call(env, sql, {"uid": MINH, "id": rid, "jar": "giai_tri"})[0]
    assert (got["suggested_jar_code"], got["jar_source"], got["review_status"]) == (
        "giai_tri",
        "user",
        "auto_added",
    )
    assert call(env, sql, {"uid": LAN, "id": rid, "jar": "giai_tri"}) == []  # RLS
    assert balances(env, MINH) == before


def test_dong_y_theo_nguon(env):
    env.reset(MINH)
    sql = "SELECT * FROM app_grant_consent(:uid, :src, :ver)"
    call(env, sql, {"uid": MINH, "src": "image_upload", "ver": "2026-12"})
    again = call(env, sql, {"uid": MINH, "src": "image_upload", "ver": "2027-01"})[0]
    assert again["version"] == "2027-01" and again["revoked_at"] is None
    got = call(env, "SELECT * FROM app_get_consents(:uid)", {"uid": MINH})
    assert [r["source"] for r in got] == ["image_upload"]
    assert call(env, "SELECT * FROM app_get_consents(:uid)", {"uid": LAN}) == []
    with pytest.raises(DB_ERRORS):
        call(env, sql, {"uid": MINH, "src": "email", "ver": "x"})


def test_ingest_review_dung_tu_ket_qua_ham_db(env):
    env.reset(MINH)
    jid = new_job(env, MINH)
    insert_rows(env, MINH, jid, rows_payload("2" * 64, 2))
    job, rows = get_job(env, MINH, jid)
    blk = ingest.build_ingest_review(job=job, rows=rows, jars=env.repo.jar_view(MINH).jars, trace_id="t" * 8,
                                     source_tool="x", as_of=env.clock.now, app_date=date(2026, 11, 21))  # fmt: skip
    assert blk.data.counts.auto_added == 2 and blk.data.rows[0].suggested_jar.code == "an_uong"
    assert all(j.code not in ("tien_vao_khac", "chua_phan_loai") for j in blk.data.jars)


# =====================================================================================================
# Đặt lại demo: xóa sạch external và dữ liệu nạp của ĐÚNG người đó
# =====================================================================================================
def test_dat_lai_xoa_external_va_du_lieu_nap_dung_nguoi(env):
    assert any("ingest_rows" in s for s in RESET_DELETES)
    order = [s.split()[2] for s in RESET_DELETES]
    assert order.index("ingest_rows") < order.index("ingest_jobs") < order.index("transactions")
    for user in (MINH, LAN):
        env.reset(user)
        insert_tx(env, user, jar=first_spending_jar(env, user))
        jid = new_job(env, user)
        insert_rows(env, user, jid, rows_payload(("7" if user == MINH else "8") * 64, 2))
        call(env, "SELECT * FROM app_grant_consent(:uid, 'csv_upload', 'v1')", {"uid": user})
    lan_daily = daily(env, LAN)
    env.reset(MINH)
    with env.master() as m:

        def count(table, user):
            return m.execute(
                f"SELECT count(*) FROM {table} WHERE user_id = %s", (user,)
            ).fetchone()[0]

        ext = "SELECT count(*) FROM transactions WHERE user_id = %s AND funding_source = 'external'"
        assert m.execute(ext, (MINH,)).fetchone()[0] == 0
        assert (
            count("ingest_jobs", MINH),
            count("ingest_rows", MINH),
            count("consents", MINH),
        ) == (0, 0, 0)
        assert m.execute(ext, (LAN,)).fetchone()[0] == 1
        assert (count("ingest_jobs", LAN), count("ingest_rows", LAN), count("consents", LAN)) == (
            1,
            2,
            1,
        )
    assert daily(env, LAN) == lan_daily
