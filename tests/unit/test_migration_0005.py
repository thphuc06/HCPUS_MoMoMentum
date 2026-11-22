"""Kiểm tĩnh db/migrations/0005_wallet.sql và các file db/seed/*.sql: tách được bằng bộ tách THẬT của migrator, RLS FORCE trên
mọi bảng có user_id, quyền tối thiểu, hàm đọc theo quy ước, khớp hằng số của yofina_core.wallet, và không sửa migration cũ.

File cũng đã được chạy thử trên PostgreSQL cục bộ (pgserver, ngoài dependency của dự án): 0001 tới 0006 rồi seed, chạy lại
lần hai (idempotent), các ca RLS, ràng buộc và hàm đọc (xem docs/ai-log/2026-11.md)."""

from __future__ import annotations

import hashlib
import importlib.util
import re

import pytest
from conftest import REPO

from yofina_core import wallet

MIGRATIONS = REPO / "db" / "migrations"
SEEDS = REPO / "db" / "seed"
SQL_PATH = MIGRATIONS / "0005_wallet.sql"
SPLITTER_PATH = REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py"

_spec = importlib.util.spec_from_file_location("migrator_sqlsplit", SPLITTER_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
split_migration = _mod.split_migration
named_params = _mod.named_params

SQL = SQL_PATH.read_text(encoding="utf-8")
STATEMENTS = split_migration(SQL)
ALL = "\n".join(STATEMENTS)

USER_TABLES = ["payees", "obligations", "credit_lines", "category_rules", "salary_events"]
GLOBAL_TABLES = ["tx_type_map", "fee_schedules", "jar_templates"]

# sha256 của nội dung (đã đổi CRLF thành LF) của các migration ĐÃ CHẠY trên Aurora: không được sửa (migrator kiểm checksum).
APPLIED = {
    "0001_core": "209b525c71d3ac9ded7ce4a7b957c88d7265347a26ad5a9f899d1686559164f5",
    "0002_jar_view": "5a1d33fd89af2a0444e9dcf414091301ac38b65fdc48455406e23142f498b9f3",
    "0003_conversation_turns": "88b4f4ba3adcb60fe4549711ab7cf2624ec2b5526797dabfbf3e34111f950587",
    "0004_confirm_resolutions": "f7058db98a984a1c514a4a76c728f3d751a09a59c407943abbc00d190e23c902",
}


def code_only(sql: str) -> str:
    """Bỏ các dòng chú thích: kiểm từ khóa nguy hiểm chỉ trên mã, không trên lời giải thích."""
    return chr(10).join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))


def strip_leading_comments(stmt: str) -> str:
    lines = stmt.strip().splitlines()
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith("--")):
        lines.pop(0)
    return chr(10).join(lines).strip()


def check_values(_all: str, constraint: str) -> set[str]:
    # ADD CONSTRAINT hoặc khai trong CREATE TABLE: lấy đúng dòng của ràng buộc đó
    line = next(
        ln for s in STATEMENTS for ln in s.splitlines() if f"CONSTRAINT {constraint} " in ln
    )
    return set(re.findall(r"'([a-z_]+)'", line))


@pytest.mark.parametrize("name", sorted(APPLIED))
def test_khong_sua_migration_da_chay(name):
    text = (MIGRATIONS / f"{name}.sql").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == APPLIED[name]


def test_tach_bang_dong_phan_cach_va_khong_cau_lenh_rong():
    assert re.search(r"^-- @@$", SQL, re.M)
    assert len(STATEMENTS) > 100 and all(s.strip() for s in STATEMENTS)
    assert not any("-- @@" in s for s in STATEMENTS)
    funcs = [s for s in STATEMENTS if s.startswith("CREATE OR REPLACE FUNCTION")]
    assert len(funcs) == 11
    for f in funcs:
        assert f.count("$$") == 2 and f.rstrip().endswith("$$")  # thân plpgsql không bị cắt


def test_khong_tham_so_co_ten_va_khong_dau_hai_cham_dinh_lien_chu():
    assert all(not named_params(s) for s in STATEMENTS)
    assert not re.search(r"(?<![:\w]):[A-Za-z_]", SQL)  # kể cả trong chú thích


def test_khong_bi_mat_khong_mat_khau_khong_account_id_va_khong_alter_role():
    assert not re.search(r"PASSWORD\s+'", SQL, re.I) and not re.search(r"\b\d{12}\b", SQL)
    assert not re.search(
        r"ALTER\s+ROLE|CREATE\s+ROLE|SUPERUSER", code_only(SQL), re.I
    )  # bài học phase 1: master Aurora không ALTER ROLE
    assert not re.search(r"\b(float|double|real|money)\b", ALL, re.I)  # tiền là numeric(14,0)


def test_viet_lai_duoc_idempotent():
    for s in STATEMENTS:
        if s.startswith("CREATE TABLE"):
            assert "IF NOT EXISTS" in s.split("(")[0]
        if s.startswith("CREATE INDEX") or s.startswith("CREATE UNIQUE INDEX"):
            assert "IF NOT EXISTS" in s.split(" ON ")[0]
        if "ADD COLUMN" in s:
            assert "ADD COLUMN IF NOT EXISTS" in s
        if s.startswith("CREATE POLICY"):
            assert any(
                p == f"DROP POLICY IF EXISTS user_isolation ON {s.split(' ON ')[1].split()[0]}"
                for p in STATEMENTS
            )
    adds = re.findall(r"ALTER TABLE (\w+) ADD CONSTRAINT (\w+)", ALL)
    assert adds
    for (
        table,
        name,
    ) in adds:  # mỗi ràng buộc thêm vào bảng cũ có DROP CONSTRAINT IF EXISTS đứng trước
        assert f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}" in STATEMENTS, name


@pytest.mark.parametrize("table", USER_TABLES)
def test_bang_nguoi_dung_moi_co_rls_force_policy_va_khoa_ngoai_users(table):
    expected = "user_id = current_setting('app.user_id', true)"
    assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in STATEMENTS
    assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in STATEMENTS
    assert f"DROP POLICY IF EXISTS user_isolation ON {table}" in STATEMENTS
    policy = next(s for s in STATEMENTS if s.startswith(f"CREATE POLICY user_isolation ON {table}"))
    assert f"USING ({expected})" in policy and f"WITH CHECK ({expected})" in policy
    create = next(s for s in STATEMENTS if s.startswith(f"CREATE TABLE IF NOT EXISTS {table} "))
    assert "REFERENCES users (id) ON DELETE CASCADE" in create


def test_moi_bang_moi_co_user_id_deu_nam_trong_danh_sach_rls():
    created = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", ALL)
    assert set(created) == set(USER_TABLES) | set(GLOBAL_TABLES)
    for t in created:
        body = next(s for s in STATEMENTS if s.startswith(f"CREATE TABLE IF NOT EXISTS {t} "))
        has_user = re.search(r"\buser_id\b", body) is not None
        assert has_user == (t in USER_TABLES), t


def grants():
    out: dict[str, set[str]] = {}
    for s in STATEMENTS:
        m = re.fullmatch(r"GRANT ([A-Z, ]+) ON (\w+) TO yofina_app", s)
        if m:
            out[m.group(2)] = {p.strip() for p in m.group(1).split(",")}
    return out


def test_quyen_toi_thieu_bang_tra_chi_doc_bang_nguoi_dung_day_du_va_so_cai_chi_sua_cot_phan_loai():
    g = grants()
    for t in GLOBAL_TABLES:
        assert g[t] == {"SELECT"}, t  # bảng tra do seed (master) ghi, ứng dụng chỉ đọc
    for t in USER_TABLES:
        assert g[t] == {"SELECT", "INSERT", "UPDATE", "DELETE"}, t
    assert "TO PUBLIC" not in ALL and not re.search(r"GRANT\s+ALL", ALL, re.I)
    for s in STATEMENTS:
        assert not re.search(r"\b(TRUNCATE|REFERENCES|TRIGGER)\b.*TO yofina_app", s)
    col = next(s for s in STATEMENTS if s.startswith("GRANT UPDATE ("))
    cols = {c.strip() for c in re.search(r"\((.*?)\)", col).group(1).split(",")}
    assert cols == {
        "jar_code", "needs_review", "classified_by", "classification_confidence", "suggested_jars",
        "obligation_id", "payee_id",
    }  # fmt: skip
    assert not cols & {
        "amount_vnd",
        "kind",
        "occurred_at",
        "app_date",
        "user_id",
        "funding_source",
        "transfer_id",
    }
    assert col.endswith("ON transactions TO yofina_app")


def test_ham_doc_theo_quy_uoc_invoker_set_config_limit_va_phan_quyen():
    funcs = [s for s in STATEMENTS if s.startswith("CREATE OR REPLACE FUNCTION")]
    names = []
    for f in funcs:
        names.append(re.match(r"CREATE OR REPLACE FUNCTION (\w+)\(", f).group(1))
        assert "SECURITY INVOKER" in f and "SECURITY DEFINER" not in f
        assert "PERFORM set_config('app.user_id', p_user_id, true);" in f
        assert "SET search_path = public, pg_temp" in f
        if "RETURNS TABLE" in f:
            assert "LIMIT" in f, f[:80]  # mọi truy vấn nhiều dòng có LIMIT
    assert names == [
        "app_ensure_system_jars", "app_list_jars", "app_list_obligations", "app_list_payees",
        "app_get_credit_line", "app_list_transactions", "app_get_unclassified", "app_get_daily_spend",
        "app_get_cashflow_summary", "app_list_salary_events", "app_get_overview_extras",
    ]  # fmt: skip
    for n in names:
        assert re.search(rf"REVOKE ALL ON FUNCTION {n}\(.*\) FROM PUBLIC", ALL)
        assert re.search(rf"GRANT EXECUTE ON FUNCTION {n}\(.*\) TO yofina_app", ALL)


def test_hu_he_thong_ton_tai_voi_ma_co_dinh_va_tien_vao_khac_khong_am():
    ensure = next(s for s in STATEMENTS if "FUNCTION app_ensure_system_jars" in s)
    assert (
        f"'{wallet.OTHER_INCOME_JAR_CODE}'" in ensure
        and f"'{wallet.UNCLASSIFIED_JAR_CODE}'" in ensure
    )
    assert "ON CONFLICT DO NOTHING" in ensure  # gọi lại an toàn
    balance = next(
        s for s in STATEMENTS if s.startswith("ALTER TABLE jars ADD CONSTRAINT jars_balance_check")
    )
    # coalesce: system_role NULL không được làm biểu thức ra NULL và vô tình cho số dư âm
    assert "coalesce(system_role, '') = 'unclassified'" in balance


def test_tap_gia_tri_khop_yofina_core_wallet():
    assert check_values(ALL, "jars_kind_check") == set(wallet.JAR_KINDS)
    assert check_values(ALL, "obligations_kind_check") == set(wallet.OBLIGATION_KINDS)
    assert check_values(ALL, "obligations_cycle_check") == set(wallet.OBLIGATION_CYCLES)
    assert check_values(ALL, "obligations_status_check") == set(wallet.OBLIGATION_STATUSES)
    assert check_values(ALL, "obligations_source_check") == set(wallet.OBLIGATION_SOURCES)
    assert re.search(r"funding_source IN \('jar', 'credit'\)", ALL) and set(
        wallet.FUNDING_SOURCES
    ) == {"jar", "credit"}
    classified = re.search(r"classified_by IN \((.*?)\)", ALL).group(1)
    assert set(re.findall(r"'(\w+)'", classified)) == set(wallet.CLASSIFIED_BY)
    salary = re.search(r"status IN \('pending', 'confirmed', 'kept_other'\)", ALL)
    assert salary and set(wallet.SALARY_EVENT_STATUSES) == {"pending", "confirmed", "kept_other"}
    assert "scope IN ('once', 'always')" in ALL and set(wallet.RULE_SCOPES) == {"once", "always"}
    assert wallet.BNPL_PRODUCT_CODE == "bnpl_sim" and "DEFAULT 'bnpl_sim'" in ALL


def test_nghia_vu_tra_sau_chi_tu_sinh_va_moi_ngay_den_han_mot_dong_hoat_dong():
    create = next(s for s in STATEMENTS if s.startswith("CREATE TABLE IF NOT EXISTS obligations"))
    assert "(kind = 'bnpl') = (source = 'bnpl_auto')" in create
    assert "amount_vnd = principal_vnd + fee_vnd" in create
    uidx = next(s for s in STATEMENTS if "obligations_bnpl_cycle_uidx" in s)
    assert "(user_id, due_date)" in uidx and "kind = 'bnpl' AND status = 'active'" in uidx


def test_khu_trung_unique_theo_nguoi_dung_va_chi_khi_co_khoa():
    idx = next(s for s in STATEMENTS if "transactions_dedupe_uidx" in s)
    assert (
        "UNIQUE INDEX" in idx
        and "(user_id, dedupe_key)" in idx
        and "WHERE dedupe_key IS NOT NULL" in idx
    )
    assert "dedupe_key ~ '^[0-9a-f]{64}$'" in ALL  # sha256 hex


def test_giao_dich_tra_sau_khong_doi_so_du_duoc_ghi_ro_va_funding_credit_chi_cho_chi_tieu():
    assert "funding_source = 'jar' OR kind = 'expense'" in ALL
    assert "KHÔNG đổi số dư hũ" in SQL


def test_confirm_resolutions_chap_nhan_bien_nhan_khong_co_transfer_id():
    assert "ALTER TABLE confirm_resolutions ALTER COLUMN transfer_id DROP NOT NULL" in STATEMENTS


# --- seed -------------------------------------------------------------------------------------
SEED_FILES = sorted(SEEDS.glob("*.sql"))


def test_co_ba_file_seed_cho_ba_bang_tra():
    assert [p.stem for p in SEED_FILES] == ["fee_schedules", "jar_templates", "tx_type_map"]


@pytest.mark.parametrize("path", SEED_FILES, ids=lambda p: p.name)
def test_seed_mot_cau_lenh_viet_lai_duoc_khong_tham_so_khong_bi_mat(path):
    sql = path.read_text(encoding="utf-8")
    stmts = [strip_leading_comments(x) for x in split_migration(sql)]
    assert len(stmts) == 1 and stmts[0].startswith("INSERT INTO")
    assert "ON CONFLICT" in stmts[0] and "DO UPDATE SET" in stmts[0]  # chạy lại nhiều lần được
    assert not named_params(stmts[0]) and not re.search(r"(?<![:\w]):[A-Za-z_]", sql)
    assert not re.search(r"PASSWORD|SECRET|\b\d{12}\b", code_only(sql), re.I)


def seed_rows(path):
    """Mỗi dòng giá trị của câu INSERT (một dòng một bộ, bắt đầu bằng dấu mở ngoặc và dấu nháy)."""
    sql = path.read_text(encoding="utf-8")
    return [ln.strip().rstrip(",") for ln in sql.splitlines() if re.match(r"\s*\('", ln)]


def test_tx_type_map_ma_hu_chuan_deu_co_trong_jar_templates_va_loai_noi_bo_khong_chon_duoc():
    jar_codes = {
        r.lstrip("(").split(",")[0].strip().strip("'")
        for r in seed_rows(SEEDS / "jar_templates.sql")
    }
    rows = []
    for r in seed_rows(SEEDS / "tx_type_map.sql"):
        parts = [p.strip() for p in re.findall(r"'[^']*'|[A-Za-z0-9_]+", r)]
        rows.append(parts)
    assert len(rows) >= 28
    for tx_type, _label, direction, jar, role, selectable, _order in rows:
        tx_type, direction = tx_type.strip("'"), direction.strip("'")
        assert re.fullmatch(r"[a-z][a-z0-9_]{0,39}", tx_type)
        assert (jar == "NULL") or jar.strip("'") in jar_codes, (tx_type, jar)
        assert jar == "NULL" or role == "NULL"  # không vừa mã hũ vừa vai trò hệ thống
        if direction == "internal":
            assert jar == "NULL" and role == "NULL" and selectable == "false"
        else:
            assert jar != "NULL" or role != "NULL"  # mọi loại chọn được phải suy ra được hũ
    assert {r[0].strip("'") for r in rows} >= {
        wallet.TX_TYPE_SALARY, wallet.TX_TYPE_SALARY_SPLIT, wallet.TX_TYPE_JAR_TRANSFER,
        wallet.TX_TYPE_OBLIGATION_PAYMENT, wallet.TX_TYPE_BNPL_PURCHASE, "transfer_person", "other_expense",
        "income_other",
    }  # fmt: skip


def test_jar_templates_tong_ty_le_mac_dinh_bang_100_va_khong_co_hu_he_thong():
    total = 0
    for r in seed_rows(SEEDS / "jar_templates.sql"):
        parts = [p.strip().strip("'") for p in re.findall(r"'[^']*'|[A-Za-z0-9_]+", r)]
        code, _name, _color, _icon, kind, split, is_default, _order = parts
        assert kind in wallet.USER_JAR_KINDS and code not in wallet.SYSTEM_JAR_CODES.values()
        total += int(split) if is_default == "true" else 0
    assert total == 100


def test_bieu_phi_co_nguon_ngay_hieu_luc_va_khong_bia_them_khoan_phi():
    sql = (SEEDS / "fee_schedules.sql").read_text(encoding="utf-8")
    assert "'bnpl_sim'" in sql and "'monthly_service_fee'" in sql and "33000" in sql
    assert "month_has_transaction" in sql and "DATE '2026-03-31'" in sql
    assert re.search(r"'https://[^']+'", sql)  # nguồn có đường dẫn
    assert sql.count("INSERT INTO") == 1 and sql.count("33000") == 1  # chỉ khoản phí có nguồn
    assert "late" not in sql.lower().replace("ví dụ phí trả chậm", "")  # không bịa phí trả chậm


def test_go_moi_check_cu_nhac_toi_balance_vnd_truoc_khi_them_check_moi():
    block = next(s for s in STATEMENTS if s.startswith("DO $$") and "pg_get_constraintdef" in s)
    assert "conrelid = 'jars'::regclass" in block and "contype = 'c'" in block
    assert "c.conname <> 'jars_balance_check'" in block and "LIKE '%balance_vnd%'" in block
    assert STATEMENTS.index(block) < STATEMENTS.index(
        next(
            s
            for s in STATEMENTS
            if s.startswith("ALTER TABLE jars ADD CONSTRAINT jars_balance_check")
        )
    )  # gỡ trước, thêm sau
