"""Kiểm tĩnh db/migrations/0050_ingest.sql: bộ tách thật của migrator, RLS FORCE cho ba bảng mới, quyền tối thiểu, hàm SECURITY
INVOKER tự đặt app.user_id và có LIMIT, ràng buộc funding mới, hàm thay thế giữ chữ ký, không sửa file migration cũ.
Chạy thật trên PostgreSQL cục bộ ở tests/local_pg/test_external_funding.py."""

from __future__ import annotations

import hashlib
import importlib.util
import re
import subprocess

from conftest import REPO

from yofina_core import ingest, wallet

SQL_PATH = REPO / "db" / "migrations" / "0050_ingest.sql"
_spec = importlib.util.spec_from_file_location(
    "migrator_sqlsplit", REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

SQL = SQL_PATH.read_text(encoding="utf-8")
STATEMENTS = _mod.split_migration(SQL)
FUNCS = [s for s in STATEMENTS if s.startswith("CREATE OR REPLACE FUNCTION")]
NEW_TABLES = ("ingest_jobs", "ingest_rows", "consents")

SIGNATURES = {
    "app_fold_text": "text",
    "app_get_daily_spend": "text, date, date",
    "app_coverage_facts": "text, date",
    "app_get_forecast_context": "text, timestamptz, text, integer",
    "app_get_data_coverage": "text, timestamptz, text, integer",
    "app_get_cashflow_summary": "text, date, date",
    "app_get_overview": "text, timestamptz, text",
    "app_get_overview_extras": "text, date",
    "app_create_ingest_job": "text, uuid, text, text, text, bigint",
    "app_find_ingest_job_by_content": "text, text",
    "app_update_ingest_job": "text, uuid, text, integer, jsonb",
    "app_insert_ingest_rows": "text, uuid, jsonb",
    "app_get_ingest_job": "text, uuid, integer",
    "app_list_ingest_jobs": "text, integer",
    "app_set_ingest_row_jar": "text, uuid, text",
    "app_grant_consent": "text, text, text",
    "app_get_consents": "text",
    "app_find_ingest_matches": "text, jsonb, integer",
}


def func(name: str) -> str:
    return next(f for f in FUNCS if f"FUNCTION {name}(" in f)


def test_tach_duoc_khong_tham_so_ten_khong_hai_cham_dinh_chu():
    assert STATEMENTS and all(s.strip() for s in STATEMENTS)
    assert "-- @@" in SQL
    for f in FUNCS:
        assert f.count("$$") == 2 and f.rstrip().endswith("$$"), f[:60]
    assert all(not _mod.named_params(s) for s in STATEMENTS)
    assert not re.search(r"(?<![:\w]):[A-Za-z_]", SQL)
    assert not re.search(r"ALTER\s+ROLE|PASSWORD\s+'", SQL, re.I)


def test_dau_file_ghi_ro_thay_ham_cua_0005_va_0009():
    head = SQL.split("-- @@")[0]
    assert "Thay hàm app_get_daily_spend của 0005" in head
    assert "Thay hàm app_get_forecast_context của 0009" in head


def test_khong_sua_migration_cu():
    """File 0001..0009 không đổi so với commit gốc của nhánh (migrator kiểm checksum)."""
    names = sorted(p.name for p in (REPO / "db" / "migrations").glob("000*.sql"))
    assert names[-1] == "0009_forecast_pipeline.sql" and len(names) == 9
    out = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", "db/migrations"],
        cwd=REPO, capture_output=True, text=True, check=False,
    )  # fmt: skip
    if out.returncode == 0:  # có git: không file cũ nào bị sửa
        changed = [line for line in out.stdout.splitlines() if line.strip()]
        assert all(not re.search(r"/000[1-9]_", c) for c in changed), changed
    else:  # không có git (bản sao): ít nhất 0050 là file mới duy nhất sau 0009
        assert (REPO / "db" / "migrations" / "0050_ingest.sql").exists()


def test_rls_force_va_policy_cho_ba_bang_moi():
    for t in NEW_TABLES:
        assert f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY" in STATEMENTS
        assert f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY" in STATEMENTS
        assert f"DROP POLICY IF EXISTS user_isolation ON {t}" in STATEMENTS
        pol = next(s for s in STATEMENTS if s.startswith(f"CREATE POLICY user_isolation ON {t}"))
        assert "USING (user_id = current_setting('app.user_id', true))" in pol
        assert "WITH CHECK (user_id = current_setting('app.user_id', true))" in pol


def test_quyen_bang_toi_thieu_va_khong_quyen_moi_tren_transactions():
    for t in NEW_TABLES:
        assert f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO yofina_app" in STATEMENTS
    grants = [s for s in STATEMENTS if s.startswith("GRANT") and " ON FUNCTION " not in s]
    assert (
        len(grants) == 3
    )  # không thêm quyền nào cho bảng cũ (sổ cái vẫn không UPDATE được số tiền hay nguồn trả)
    assert not re.search(r"GRANT[^;]*ON transactions", SQL)


def test_ham_security_invoker_tu_dat_user_id_va_co_limit():
    names = {re.search(r"FUNCTION (\w+)\(", f).group(1) for f in FUNCS}
    assert names == set(SIGNATURES)
    for f in FUNCS:
        name = re.search(r"FUNCTION (\w+)\(", f).group(1)
        assert "SECURITY DEFINER" not in f, name
        assert "SET search_path = public, pg_temp" in f, name
        if name == "app_fold_text":
            assert "IMMUTABLE" in f
            continue
        assert "SECURITY INVOKER" in f, name
        assert "PERFORM set_config('app.user_id', p_user_id, true);" in f, name
    for name in ("app_get_ingest_job", "app_list_ingest_jobs", "app_find_ingest_matches", "app_get_consents",
                 "app_get_daily_spend", "app_find_ingest_job_by_content", "app_get_data_coverage"):  # fmt: skip
        assert "LIMIT" in func(name), name
    assert "LIMIT LEAST(GREATEST(coalesce(p_row_limit, 200), 1), 500)" in func("app_get_ingest_job")
    assert "jsonb_array_length(p_rows) > 500" in func("app_insert_ingest_rows")
    assert "jsonb_array_length(p_rows) > 500" in func("app_find_ingest_matches")


def test_quyen_ham_chi_cho_yofina_app_va_thu_hoi_public():
    for name, sig in SIGNATURES.items():
        assert f"REVOKE ALL ON FUNCTION {name}({sig}) FROM PUBLIC" in STATEMENTS, name
        assert f"GRANT EXECUTE ON FUNCTION {name}({sig}) TO yofina_app" in STATEMENTS, name


def test_rang_buoc_funding_moi_drop_roi_add():
    i = STATEMENTS.index(
        "ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_funding_check"
    )
    add = STATEMENTS[i + 1]
    assert add.startswith(
        "ALTER TABLE transactions ADD CONSTRAINT transactions_funding_check CHECK"
    )
    values = set(re.findall(r"'(\w+)'", re.search(r"funding_source IN \((.*?)\)", add).group(1)))
    assert values == set(wallet.FUNDING_SOURCES) == {"jar", "credit", "external"}
    assert "funding_source = 'external' AND kind = 'income'" in add  # thu nhập ngoài ví được
    assert (
        "transfer_id IS NULL AND obligation_id IS NULL" in add
    )  # external không chuyển hũ, không trả nghĩa vụ
    assert "jar_code IS NOT NULL" in add  # chi ngoài ví phải có hũ


def check_values(sql: str, constraint: str) -> set[str]:
    m = re.search(rf"CONSTRAINT {constraint} CHECK \((.*?)\)\s*\)", sql, re.S)
    assert m, constraint
    return set(re.findall(r"'(\w+)'", m.group(1)))


def test_tap_gia_tri_khop_yofina_core_ingest():
    assert check_values(SQL, "ingest_jobs_status_check") == set(ingest.JOB_STATUSES)
    assert check_values(SQL, "ingest_rows_review_check") == set(ingest.ROW_STATUSES)
    assert "source_kind IN ('image', 'csv')" in SQL and ingest.SOURCE_KINDS == ("image", "csv")
    assert "kind IN ('expense', 'income')" in SQL and ingest.ROW_KINDS == ("expense", "income")
    assert "jar_source IN ('type_map', 'rule', 'model', 'user')" in SQL
    assert ingest.JAR_SOURCES == ("type_map", "rule", "model", "user")
    assert "source IN ('image_upload', 'csv_upload')" in SQL
    assert ingest.CONSENT_SOURCES == ("image_upload", "csv_upload")
    assert "status IN ('done', 'failed', 'rejected')" in SQL and ingest.JOB_FINAL_STATUSES == (
        "done", "failed", "rejected",
    )  # fmt: skip


def test_bang_khong_co_cot_anh_hay_van_ban_tho():
    for t in ("ingest_jobs", "ingest_rows"):
        ddl = next(s for s in STATEMENTS if s.startswith(f"CREATE TABLE IF NOT EXISTS {t}"))
        cols = {
            m.group(1)
            for m in re.finditer(
                r"^\s{2}(\w+)\s+(?:uuid|text|bigint|integer|smallint|numeric|date|timestamptz)",
                ddl,
                re.M,
            )
        }
        assert not cols & {
            "raw_text",
            "ocr_text",
            "image",
            "image_bytes",
            "content",
            "body",
            "raw",
        }, (t, cols)
        assert "bytea" not in ddl
    rows = next(s for s in STATEMENTS if s.startswith("CREATE TABLE IF NOT EXISTS ingest_rows"))
    assert "amount_vnd                  numeric(14,0) NOT NULL CHECK (amount_vnd > 0)" in rows
    # transaction_id và duplicate_of KHÔNG có khóa ngoại cứng (đặt lại demo xóa transactions trước)
    assert "REFERENCES transactions" not in rows
    assert "REFERENCES ingest_jobs (user_id, id) ON DELETE CASCADE" in rows


def test_khoa_khu_trung_va_bam_noi_dung():
    assert (
        "CREATE UNIQUE INDEX IF NOT EXISTS ingest_rows_dedupe_uidx ON ingest_rows (user_id, dedupe_key)"
        in STATEMENTS
    )
    jobs = next(s for s in STATEMENTS if s.startswith("CREATE TABLE IF NOT EXISTS ingest_jobs"))
    assert "content_sha256 ~ '^[0-9a-f]{64}$'" in jobs
    assert any(
        s.startswith("CREATE UNIQUE INDEX IF NOT EXISTS ingest_jobs_content_uidx")
        for s in STATEMENTS
    )
    assert "coverage_before  numeric(4,3)" in jobs and "coverage_after   numeric(4,3)" in jobs


def test_ham_thay_the_giu_chu_ky_va_kieu_tra_ve():
    ds = func("app_get_daily_spend")
    assert "app_get_daily_spend(p_user_id text, p_from date, p_to date)" in ds
    assert "RETURNS TABLE (jar_code text, day date, spent_vnd numeric, tx_count bigint)" in ds
    assert "t.funding_source IN ('jar', 'external')" in ds and "t.obligation_id IS NULL" in ds
    assert "j.kind <> 'system'" in ds and "LIMIT 5000" in ds
    ctx = func("app_get_forecast_context")
    assert "p_user_id text, p_now timestamptz, p_tz text, p_window_days integer DEFAULT 330" in ctx
    assert "RETURNS TABLE (section text, jar_code text, payload jsonb)" in ctx
    for key in ("'income_vnd'", "'spend_vnd'", "'balance_end_vnd'", "'balance_start_vnd'", "'spend_rows'",
                "'history_start'", "'app_date'", "'profile'"):  # fmt: skip
        assert key in ctx, key
    assert "app_coverage_facts(p_user_id, v_from)" in ctx


def test_cong_thuc_do_phu_moi():
    facts = func("app_coverage_facts")
    assert "t.tx_type = 'salary' AND t.funding_source = 'jar'" in facts
    assert "t.kind = 'income' AND t.funding_source = 'external'" in facts
    assert "t.kind = 'expense' AND t.funding_source IN ('jar', 'external')" in facts
    assert (
        "sum(t.amount_vnd) FILTER (WHERE t.funding_source = 'jar')" in facts
    )  # biến động số dư chỉ của ví


def test_khu_trung_moi_nguon_tra_va_cua_so_la_tham_so():
    m = func("app_find_ingest_matches")
    assert "p_window_days integer" in m and "v_win" in m
    assert (
        "funding_source" not in m.split("JOIN transactions t")[1].split("WHERE")[0]
    )  # không lọc nguồn trả
    assert "t.kind = c.ck AND abs(t.amount_vnd) = c.ca" in m
    assert "t.kind <> 'transfer'" in m
    assert not re.search(r"BETWEEN c\.cd - [0-9]", m)  # không gõ cứng cửa sổ


def test_fold_text_sql_khop_python():
    """Bảng translate của app_fold_text gồm đúng mọi chữ có dấu tiếng Việt và cho cùng kết quả với params.fold_text."""
    from yofina_core.params import fold_text

    body = func("app_fold_text")
    src, dst = [s for s in re.findall(r"'([^']*)'", body) if len(s) > 100]
    assert len(src) == len(dst) == 134
    for a, b in zip(src, dst, strict=True):
        assert fold_text(a) == b, a
    table = str.maketrans(src, dst)
    for s in ("Cơm Tấm Phúc Lộc", "  ĐI   lại  ", "Grab *TRIP", "Nguyễn Thị Ánh"):
        assert " ".join(s.lower().translate(table).split()) == fold_text(s)


def test_checksum_on_dinh():
    assert len(hashlib.sha256(SQL.replace("\r\n", "\n").encode()).hexdigest()) == 64
    assert _mod.checksum(SQL) == _mod.checksum(SQL.replace("\n", "\r\n"))
