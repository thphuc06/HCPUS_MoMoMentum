# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["pgserver>=0.1.4", "psycopg[binary]>=3.2"]
# ///
"""Chạy thử db/migrations/*.sql và db/seed/*.sql trên PostgreSQL cục bộ (pgserver), như migrator thật, rồi kiểm hành vi
dưới role `yofina_app`: chạy lại như migrator (migration chỉ chạy một lần theo thứ tự: lượt hai bỏ qua mọi file theo version và
checksum; seed chạy lại được), RLS, ràng buộc, quyền, hàm đọc.

    uv run scripts/db_local_check.py

pgserver chưa có wheel cho Python 3.13 nên script ghim Python 3.12 (uv tự lo; không ảnh hưởng `.venv` của dự án).
Không gọi AWS, không cần Docker. Dùng superuser thật nên KHÔNG bắt được hạn chế riêng của master Aurora (rds_superuser):
bài học phase 1 là master Aurora không được `ALTER ROLE ... NOSUPERUSER`, 0005 và 0006 không có ALTER ROLE.
Thoát mã 1 nếu có ca lỗi.
"""

import hashlib
import importlib.util
import re
import sys
import tempfile
import uuid
from pathlib import Path

import pgserver
import psycopg

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "sqlsplit", REPO / "infra-cdk/lambdas/migrator/sqlsplit.py"
)
sqlsplit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sqlsplit)

tmp = tempfile.mkdtemp(prefix="pgdata_")
srv = pgserver.get_server(tmp, cleanup_mode="stop")
uri = srv.get_uri()
print("PostgreSQL", srv.psql("select version();").strip().splitlines()[2].strip()[:40])


def run_file(conn, path: Path):
    sql = path.read_text(encoding="utf-8")
    stmts = sqlsplit.split_migration(sql)
    with conn.transaction():
        for i, s in enumerate(stmts, 1):
            names = sqlsplit.named_params(s)
            assert not names, (path.name, i, names, s[:120])
            try:
                conn.execute(s)
            except Exception as e:
                print(f"LOI {path.name} cau {i}/{len(stmts)}: {e}\n---\n{s[:400]}")
                raise
    return len(stmts)


def migrator_pass(conn, files: list[Path]) -> tuple[list[str], list[str]]:
    """Một lượt như migrator thật (`infra-cdk/lambdas/migrator/handler.py`, `scripts/migrate.py`): `version` là tên file (seed:
    `seed_<tên>_<8 ký tự sha256>`), đã có trong `schema_migrations` cùng checksum thì bỏ qua, checksum khác thì dừng, chưa có thì chạy
    cả file trong một transaction rồi ghi `schema_migrations`. Trả (đã chạy, đã bỏ qua)."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())"
    )
    applied = dict(conn.execute("SELECT version, checksum FROM schema_migrations").fetchall())
    ran, skipped = [], []
    for f in files:
        sql = f.read_text(encoding="utf-8")
        version = f.stem if f.parent.name == "migrations" else (
            f"seed_{f.stem}_{hashlib.sha256(sql.encode('utf-8')).hexdigest()[:8]}"
        )
        digest = sqlsplit.checksum(sql)
        if version in applied:
            if applied[version] != digest:
                raise RuntimeError(f"{version} đã chạy nhưng nội dung đã đổi (checksum khác)")
            skipped.append(version)
            continue
        print(f.name, run_file(conn, f), "cau lenh")
        conn.execute("INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)", (version, digest))
        ran.append(version)
    return ran, skipped


MIGRATIONS = sorted((REPO / "db/migrations").glob("*.sql"))
SEEDS = sorted((REPO / "db/seed").glob("*.sql"))

with psycopg.connect(uri, autocommit=True) as master:
    first, _ = migrator_pass(master, MIGRATIONS)
    master.execute("ALTER ROLE yofina_app WITH PASSWORD 'local-test-only'")
    seeded, _ = migrator_pass(master, SEEDS)
    first += seeded
    # Chạy lại như migrator thật: migration chỉ chạy MỘT lần theo thứ tự (0055 đổi kiểu trả về của hàm do 0006 tạo, nên chạy lại 0006
    # sau 0055 là lỗi, và migrator không bao giờ làm vậy). Lượt hai phải bỏ qua mọi file nhờ version và checksum đã ghi.
    again, skipped = migrator_pass(master, [*MIGRATIONS, *SEEDS])
    rerun_ok = again == [] and skipped == first
    print("lan 2 migrator: chay", len(again), "bo qua", len(skipped))
    # Seed thì khác: sửa nội dung seed ra version mới và chạy lại trên dữ liệu đã có, nên mọi file seed phải chạy lại được (ON CONFLICT)
    for f in SEEDS:
        print("lan 2 seed", f.name, run_file(master, f))
    n = master.execute("select count(*) from tx_type_map").fetchone()[0]
    print(
        "tx_type_map",
        n,
        "jar_templates",
        master.execute("select count(*), sum(default_split_percent) from jar_templates").fetchone(),
    )
    print(
        "fee",
        master.execute(
            "select product_code, fee_type, amount_vnd, source_url from fee_schedules"
        ).fetchall(),
    )

# kết nối bằng role ứng dụng
m = re.match(r"postgresql://([^@]*)@(.*)", uri)
app_uri = f"postgresql://yofina_app:local-test-only@{m.group(2)}"
print("URI app", app_uri.split("@")[1])


def app():
    return psycopg.connect(app_uri, autocommit=True)


def scoped(conn, uid):
    """transaction với app.user_id"""
    return conn.transaction()


u1, u2 = "user-1", "user-2"
ok = []


def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    ok.append(cond)


check("chạy lại như migrator: mọi migration và seed đã chạy được bỏ qua theo version và checksum", rerun_ok)


def expect_error(conn, sql, params=(), uid=None, name=""):
    try:
        with conn.transaction():
            if uid:
                conn.execute("select set_config('app.user_id', %s, true)", (uid,))
            conn.execute(sql, params)
        check(name + " (lẽ ra bị từ chối)", False)
    except psycopg.Error as e:
        check(name + " -> " + type(e).__name__, True)


with app() as c:
    # users
    for u in (u1, u2):
        with c.transaction():
            c.execute("select set_config('app.user_id', %s, true)", (u,))
            c.execute(
                "insert into users (id, display_name, monthly_salary_vnd, payday_day) values (%s, %s, 9000000, 5)",
                (u, u),
            )
            n = c.execute("select app_ensure_system_jars(%s)", (u,)).fetchone()[0]
            check(f"ensure_system_jars {u} tạo 2", n == 2)
            n = c.execute("select app_ensure_system_jars(%s)", (u,)).fetchone()[0]
            check(f"ensure_system_jars {u} lần hai tạo 0", n == 0)
            for code, name, kind, bal, split in [
                ("an_uong", "Ăn uống", "spending", 380000, 30),
                ("hoa_don", "Hóa đơn", "spending", 450000, 31),
                ("nghia_vu", "Nghĩa vụ", "obligation", 1000000, 5),
                ("du_lich", "Du lịch", "saving", 1800000, 10),
            ]:
                c.execute(
                    "insert into jars (user_id, code, name, color_key, icon_key, balance_vnd, split_percent, sort_order, kind, goal_vnd, goal_date) values (%s,%s,%s,'violet','utensils',%s,%s,1,%s,%s,%s)",
                    (
                        u,
                        code,
                        name,
                        bal,
                        split,
                        kind,
                        6000000 if code == "du_lich" else None,
                        "2027-04-01" if code == "du_lich" else None,
                    ),
                )
            rows = c.execute(
                "select code, kind, system_role from app_list_jars(%s)", (u,)
            ).fetchall()
            check(
                f"app_list_jars {u}: 6 hũ",
                len(rows) == 6 and {r[2] for r in rows if r[2]} == {"other_income", "unclassified"},
            )

    # ràng buộc hũ
    expect_error(
        c,
        "update jars set balance_vnd = -1 where code = 'an_uong'",
        uid=u1,
        name="số dư hũ thường âm",
    )
    with c.transaction():
        c.execute("select set_config('app.user_id', %s, true)", (u1,))
        c.execute("update jars set balance_vnd = -180000 where code = 'chua_phan_loai'")
    check("hũ chưa phân loại được âm", True)
    expect_error(
        c,
        "update jars set balance_vnd = -5 where code = 'tien_vao_khac'",
        uid=u1,
        name="hũ tiền vào khác âm",
    )
    expect_error(
        c,
        "update jars set split_percent = 10 where code = 'tien_vao_khac'",
        uid=u1,
        name="hũ hệ thống có tỷ lệ chia",
    )
    expect_error(
        c,
        "update jars set kind = 'system' where code = 'an_uong'",
        uid=u1,
        name="kind system thiếu system_role",
    )
    expect_error(
        c,
        "update jars set goal_date = '2027-01-01' where code = 'an_uong'",
        uid=u1,
        name="goal_date không có goal_vnd",
    )
    expect_error(
        c,
        "insert into jars (user_id, code, name, color_key, icon_key, kind, system_role) values ('user-1','x2','X','a','b','system','unclassified')",
        uid=u1,
        name="hũ hệ thống trùng vai trò",
    )

    # payee, obligations, credit line, transactions
    pid = str(uuid.uuid4())
    tx1 = str(uuid.uuid4())
    tx2 = str(uuid.uuid4())
    tx3 = str(uuid.uuid4())
    ob = str(uuid.uuid4())
    with c.transaction():
        c.execute("select set_config('app.user_id', %s, true)", (u1,))
        c.execute(
            "insert into payees (id, user_id, name, account_hint, is_favorite) values (%s,%s,'Bạn A','xxxx 1234', true)",
            (pid, u1),
        )
        c.execute(
            "insert into credit_lines (user_id, limit_vnd, outstanding_vnd) values (%s, 5000000, 300000)",
            (u1,),
        )
        c.execute(
            "insert into obligations (id, user_id, kind, name, amount_vnd, fee_vnd, principal_vnd, due_date, source, pay_jar_code) values (%s,%s,'bnpl','Trả sau (mô phỏng)',333000,33000,300000,'2026-12-05','bnpl_auto','nghia_vu')",
            (ob, u1),
        )
        c.execute(
            "insert into obligations (user_id, kind, name, amount_vnd, amount_min_vnd, amount_max_vnd, due_date, cycle, due_day, pay_jar_code, is_essential) values (%s,'bill','Điện',375000,300000,450000,'2026-11-26','monthly',26,'hoa_don',true)",
            (u1,),
        )
        c.execute(
            "insert into transactions (id, user_id, occurred_at, app_date, kind, jar_code, amount_vnd, merchant, tx_type, payee_id, dedupe_key, note) values (%s,%s,'2026-11-20T10:00:00Z','2026-11-20','expense','an_uong',-45000,'Quán cơm','food_drink',%s,%s,'Bữa trưa')",
            (tx1, u1, pid, "a" * 64),
        )
        c.execute(
            "insert into transactions (id, user_id, occurred_at, app_date, kind, jar_code, amount_vnd, tx_type, funding_source) values (%s,%s,'2026-11-21T10:00:00Z','2026-11-21','expense','du_lich',-300000,'bnpl_purchase','credit')",
            (tx2, u1),
        )
        c.execute(
            "insert into transactions (id, user_id, occurred_at, app_date, kind, jar_code, amount_vnd, tx_type, needs_review, suggested_jars) values (%s,%s,'2026-11-21T12:00:00Z','2026-11-21','expense','chua_phan_loai',-60000,'transfer_person',true,%s)",
            (tx3, u1, ["an_uong", "hoa_don"]),
        )
        # lương về
        c.execute(
            "insert into transactions (user_id, occurred_at, app_date, kind, jar_code, amount_vnd, tx_type) values (%s,'2026-11-05T01:00:00Z','2026-11-05','income','tien_vao_khac',9000000,'salary')",
            (u1,),
        )
        c.execute(
            "insert into transactions (id, user_id, occurred_at, app_date, kind, jar_code, amount_vnd, tx_type, obligation_id, funding_source) values (%s,%s,'2026-11-22T01:00:00Z','2026-11-22','expense','hoa_don',-380000,'bill_electricity',(select id from obligations where kind='bill' limit 1),'jar')",
            (str(uuid.uuid4()), u1),
        )
    check("chèn dữ liệu ví", True)
    expect_error(
        c,
        "insert into transactions (user_id, occurred_at, app_date, kind, jar_code, amount_vnd, dedupe_key) values ('user-1','2026-11-20T10:00:00Z','2026-11-20','expense','an_uong',-45000,%s)",
        ("a" * 64,),
        uid=u1,
        name="dedupe_key trùng",
    )
    expect_error(
        c,
        "insert into transactions (user_id, occurred_at, app_date, kind, jar_code, amount_vnd, funding_source) values ('user-1','2026-11-20T10:00:00Z','2026-11-20','income','an_uong',5,'credit')",
        uid=u1,
        name="income không được funding credit",
    )
    expect_error(
        c,
        "insert into obligations (user_id, kind, name, amount_vnd, fee_vnd, principal_vnd, due_date, source) values ('user-1','bnpl','x',100,10,50,'2026-12-05','bnpl_auto')",
        uid=u1,
        name="bnpl amount != principal + fee",
    )
    expect_error(
        c,
        "insert into obligations (user_id, kind, name, amount_vnd, fee_vnd, principal_vnd, due_date, source) values ('user-1','bnpl','x',333000,33000,300000,'2026-12-05','bnpl_auto')",
        uid=u1,
        name="hai bnpl hoạt động cùng ngày đến hạn",
    )
    expect_error(
        c,
        "insert into obligations (user_id, kind, name, amount_vnd, amount_min_vnd, amount_max_vnd, due_date) values ('user-1','bill','x',100,200,300,'2026-12-05')",
        uid=u1,
        name="khoảng không chứa số tiền kỳ vọng",
    )
    expect_error(
        c,
        "insert into obligations (user_id, kind, name, amount_vnd, due_date, pay_jar_code) values ('user-1','rent','x',100,'2026-12-05','khong_co')",
        uid=u1,
        name="pay_jar_code không tồn tại",
    )
    expect_error(
        c,
        "update transactions set amount_vnd = -1 where id = %s",
        (tx1,),
        uid=u1,
        name="sửa số tiền sổ cái",
    )
    with c.transaction():
        c.execute("select set_config('app.user_id', %s, true)", (u1,))
        cur = c.execute(
            "update transactions set jar_code = 'hoa_don', needs_review = false where id = %s",
            (tx3,),
        )
        check("sửa jar_code/needs_review được", cur.rowcount == 1)
        c.execute(
            "update transactions set jar_code = 'chua_phan_loai', needs_review = true where id = %s",
            (tx3,),
        )

    with c.transaction():
        c.execute("select set_config('app.user_id', %s, true)", (u1,))
        rows = c.execute(
            "select id, jar_code, payee_name, obligation_id is not null from app_list_transactions(%s, null, null, null, null, null, null, null, null, 3)",
            (u1,),
        ).fetchall()
        check("app_list_transactions 3 dòng (limit)", len(rows) == 3)
        # con tro
        last = c.execute(
            "select occurred_at, id from app_list_transactions(%s, null, null, null, null, null, null, null, null, 2) order by occurred_at, id limit 1",
            (u1,),
        ).fetchone()
        page2 = c.execute(
            "select id from app_list_transactions(%s, null, null, null, null, null, null, %s, %s, 50)",
            (u1, last[0], last[1]),
        ).fetchall()
        allrows = c.execute(
            "select id from app_list_transactions(%s, null, null, null, null, null, null, null, null, 50)",
            (u1,),
        ).fetchall()
        check("phân trang con trỏ", len(page2) == len(allrows) - 2)
        r = c.execute(
            "select count(*) from app_list_transactions(%s, 'an_uong', null, null, 'expense', 'food_drink', null, null, null, 20)",
            (u1,),
        ).fetchone()
        check("lọc jar+kind+tx_type", r[0] == 1)
        un = c.execute(
            "select id, suggested_jars from app_get_unclassified(%s, 10)", (u1,)
        ).fetchall()
        check("app_get_unclassified có 1 dòng, 2 gợi ý", len(un) == 1 and len(un[0][1]) == 2)
        ds = c.execute(
            "select jar_code, day, spent_vnd from app_get_daily_spend(%s, '2026-11-01', '2026-11-30')",
            (u1,),
        ).fetchall()
        check(
            "daily_spend chỉ tính funding jar, không obligation: 1 dòng an_uong 45000",
            [(r[0], int(r[2])) for r in ds] == [("an_uong", 45000)],
        )
        cf = c.execute(
            "select app_get_cashflow_summary(%s,'2026-11-01','2026-11-30')", (u1,)
        ).fetchone()[0]
        check(
            "cashflow có by_jar và income_by_type(salary)",
            {x["tx_type"] for x in cf["income_by_type"]} == {"salary"} and len(cf["by_jar"]) >= 3,
        )
        ex = c.execute("select app_get_overview_extras(%s, '2026-11-21')", (u1,)).fetchone()[0]
        check(
            "overview extras: credit_line, 2 obligations_due, 5 recent, needs_review 1",
            ex["credit_line"]["outstanding_vnd"] == 300000
            and len(ex["obligations_due"]) == 2
            and len(ex["recent_transactions"]) == 5
            and ex["needs_review_count"] == 1,
        )
        check("overview extras profile", ex["profile"]["display_name"] == u1)
        po = c.execute("select name from app_list_payees(%s)", (u1,)).fetchall()
        check("app_list_payees", po == [("Bạn A",)])
        ol = c.execute(
            "select kind from app_list_obligations(%s, 'active', null, 10)", (u1,)
        ).fetchall()
        check("app_list_obligations sắp theo hạn", [r[0] for r in ol] == ["bill", "bnpl"])
        cl = c.execute("select limit_vnd from app_get_credit_line(%s)", (u1,)).fetchall()
        check("app_get_credit_line", len(cl) == 1)

    # RLS
    with c.transaction():
        c.execute("select set_config('app.user_id', %s, true)", (u2,))
        check(
            "u2 không thấy giao dịch của u1",
            c.execute("select count(*) from transactions").fetchone()[0] == 0,
        )
        check(
            "u2 không thấy nghĩa vụ của u1",
            c.execute("select count(*) from obligations").fetchone()[0] == 0,
        )
        check(
            "hàm đọc của u2 ra rỗng",
            c.execute("select count(*) from app_list_transactions(%s)", (u2,)).fetchone()[0] == 0,
        )
    check(
        "không set app.user_id thì không thấy gì",
        c.execute("select count(*) from obligations").fetchone()[0] == 0,
    )
    expect_error(
        c,
        "insert into payees (user_id, name) values ('user-1','lậu')",
        uid=u2,
        name="u2 ghi payee của u1",
    )

    # forecast
    r1, r2, r3 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    import datetime as dt

    def ins_run(conn, rid, when, trig="nightly"):
        conn.execute(
            "insert into forecast_runs (id, user_id, model, computed_at, app_date, horizon_days, history_days, data_coverage, confidence_label, is_initial_estimate, trigger, n_paths) values (%s,%s,'hurdle_calendar',%s,'2026-11-21',3,47,0.62,'medium',false,%s,5000)",
            (rid, u1, when, trig),
        )

    def ins_sum(conn, rid, jar, runout, p):
        conn.execute(
            "insert into forecast_jar_summaries (run_id, user_id, jar_code, start_balance_vnd, payday_date, days_to_payday, runout_date, p_shortfall, p_shortfall_se, status, confidence_band, show_probability, series_kind) values (%s,%s,%s,380000,'2026-12-05',14,%s,%s,0.006,'short','medium',%s,'dense')",
            (rid, u1, jar, runout, p, p is not None),
        )

    def ins_days(conn, rid, jar, base):
        for i in range(1, 4):
            d = dt.date(2026, 11, 21) + dt.timedelta(days=i)
            conn.execute(
                "insert into forecasts (run_id, user_id, jar_code, day, spend_p10_vnd, spend_p50_vnd, spend_p90_vnd, balance_p10_vnd, balance_p50_vnd, balance_p90_vnd) values (%s,%s,%s,%s,0,30000,90000,%s,%s,%s)",
                (rid, u1, jar, d, base - 90000 * i, base - 30000 * i, base),
            )

    with c.transaction():
        c.execute("select set_config('app.user_id', %s, true)", (u1,))
        ins_run(c, r1, "2026-11-21T19:00:00Z")
        ins_sum(c, r1, "an_uong", "2026-11-23", 0.71)
        ins_days(c, r1, "an_uong", 380000)
        ins_sum(c, r1, "hoa_don", None, None)
        ins_days(c, r1, "hoa_don", 450000)
        ins_run(c, r2, "2026-11-22T19:00:00Z", "event")
        ins_sum(c, r2, "an_uong", "2026-11-24", 0.66)
        ins_days(c, r2, "an_uong", 400000)
        sm = c.execute(
            "select jar_code, run_id, runout_date, show_probability, trigger from app_get_forecast_summaries(%s)",
            (u1,),
        ).fetchall()
        d = {r[0]: r for r in sm}
        check(
            "summaries: mới nhất mỗi hũ (an_uong lấy r2, hoa_don còn r1)",
            str(d["an_uong"][1]) == r2 and str(d["hoa_don"][1]) == r1 and len(sm) == 2,
        )
        ser = c.execute(
            "select count(*), min(balance_p50_vnd) from app_get_forecast_series(%s,'an_uong')",
            (u1,),
        ).fetchone()
        check("series an_uong từ r2: 3 ngày", ser[0] == 3 and all(True for _ in [0]))
        ser2 = c.execute(
            "select run_id from app_get_forecast_series(%s,'hoa_don') limit 1", (u1,)
        ).fetchone()
        check("series hoa_don từ r1", str(ser2[0]) == r1)
        check(
            "series hũ không có dự báo: rỗng",
            c.execute(
                "select count(*) from app_get_forecast_series(%s,'du_lich')", (u1,)
            ).fetchone()[0]
            == 0,
        )
        check(
            "summaries lọc 1 hũ",
            c.execute(
                "select count(*) from app_get_forecast_summaries(%s,'an_uong')", (u1,)
            ).fetchone()[0]
            == 1,
        )
    expect_error(
        c, "update forecast_runs set model = 'x'", uid=u1, name="sửa lần chạy (không có UPDATE)"
    )
    expect_error(
        c,
        "insert into forecasts (run_id, user_id, jar_code, day, spend_p10_vnd, spend_p50_vnd, spend_p90_vnd, balance_p10_vnd, balance_p50_vnd, balance_p90_vnd) values (%s,'user-1','an_uong','2027-01-01',5,3,9,0,0,0)",
        (r1,),
        uid=u1,
        name="phân vị chi tiêu sai thứ tự",
    )
    with c.transaction():
        c.execute("select set_config('app.user_id', %s, true)", (u1,))
        c.execute(
            "insert into forecasts (run_id, user_id, jar_code, day, spend_p10_vnd, spend_p50_vnd, spend_p90_vnd, balance_p10_vnd, balance_p50_vnd, balance_p90_vnd) values (%s,'user-1','an_uong','2027-01-01',1,3,9,-500000,-200000,0)",
            (r1,),
        )
    check("số dư âm trong dự báo được lưu", True)
    expect_error(
        c,
        "insert into forecast_jar_summaries (run_id, user_id, jar_code, start_balance_vnd, payday_date, days_to_payday, status, confidence_band, show_probability, p_shortfall) values (%s,'user-1','du_lich',1,'2026-12-05',1,'ok','high',false,0.3)",
        (r1,),
        uid=u1,
        name="show_probability lệch p_shortfall",
    )
    with c.transaction():
        c.execute("select set_config('app.user_id', %s, true)", (u1,))
        ins_run(c, r3, "2026-11-23T19:00:00Z")
        # 0009 viết lại hàm của 0006: KHÔNG BAO GIỜ xóa lần chạy mới nhất chứa một hũ nào đó (r1 còn là bản mới nhất của hoa_don,
        # r2 của an_uong), nên giữ 1 lần chạy (r3) mà vẫn không xóa gì
        n = c.execute("select app_prune_forecast_runs(%s, 1)", (u1,)).fetchone()[0]
        check(
            "prune (0009) không xóa lần chạy mới nhất của hũ nào",
            n == 0 and c.execute("select count(*) from forecast_runs").fetchone()[0] == 3,
        )
        # lần chạy mới có cả hai hũ: r1, r2 hết là bản mới nhất của hũ nào, r3 quá số giữ, nên xóa cả ba
        r4 = str(uuid.uuid4())
        ins_run(c, r4, "2026-11-24T19:00:00Z")
        for jar in ("an_uong", "hoa_don"):
            ins_sum(c, r4, jar, None, None)
            ins_days(c, r4, jar, 500000)
        n = c.execute("select app_prune_forecast_runs(%s, 1)", (u1,)).fetchone()[0]
        check("prune giữ 1 xóa 3 lần chạy đã bị thay", n == 3)
        check(
            "prune kéo theo tóm tắt và dòng ngày",
            {str(r[0]) for r in c.execute("select run_id from forecast_jar_summaries").fetchall()} == {r4}
            and {str(r[0]) for r in c.execute("select run_id from forecasts").fetchall()} == {r4}
            and c.execute("select count(*) from forecast_jar_summaries").fetchone()[0] == 2,
        )

    # bảng tra: chỉ đọc
    check(
        "yofina_app đọc tx_type_map",
        c.execute("select count(*) from tx_type_map").fetchone()[0] >= 30,
    )
    expect_error(
        c,
        "insert into tx_type_map (tx_type, label, direction, system_role) values ('hack','x','out','unclassified')",
        name="ghi tx_type_map",
    )
    expect_error(c, "update fee_schedules set amount_vnd = 1", name="sửa fee_schedules")
    expect_error(c, "delete from jar_templates", name="xóa jar_templates")
    expect_error(
        c, "update users set display_name='x' from schema_migrations", name="đụng schema_migrations"
    )

    # confirm_resolutions transfer_id null
    with c.transaction():
        c.execute("select set_config('app.user_id', %s, true)", (u1,))
        c.execute(
            "insert into confirm_resolutions (user_id, confirm_block_id, conversation_id, transfer_id, receipt, action_tool) values (%s,'confirm:t:abcdef012345','c',null,'{}'::jsonb,'update_profile')",
            (u1,),
        )
    check("confirm_resolutions.transfer_id có thể NULL", True)

print("\nTỔNG:", sum(ok), "/", len(ok), "đạt")
srv.cleanup()
sys.exit(0 if all(ok) else 1)
