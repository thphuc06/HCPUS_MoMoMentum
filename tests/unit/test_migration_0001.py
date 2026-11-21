"""Kiểm tĩnh db/migrations/0001_core.sql (không cần PostgreSQL): tách được bằng chính bộ tách của
migrator, RLS trên mọi bảng, quyền tối thiểu, không có bí mật. Việc chạy thật trên Aurora do
migrator và test tích hợp; file này cũng đã được chạy thử trên một PostgreSQL cục bộ (xem ai-log)."""

from __future__ import annotations

import importlib.util
import re

import pytest
from conftest import REPO

SQL_PATH = REPO / "db" / "migrations" / "0001_core.sql"
SPLITTER_PATH = REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py"


def _load_splitter():
    """Bộ tách câu lệnh THẬT của Lambda migrator (luồng A): kiểm file SQL bằng đúng thứ sẽ chạy."""
    assert SPLITTER_PATH.exists(), f"không thấy bộ tách của migrator: {SPLITTER_PATH}"
    spec = importlib.util.spec_from_file_location("migrator_sqlsplit", SPLITTER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.split_statements


def _strip_leading_comments(stmt: str) -> str:
    lines = stmt.strip().splitlines()
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith("--")):
        lines.pop(0)
    return "\n".join(lines).strip()


SQL = SQL_PATH.read_text(encoding="utf-8")
STATEMENTS = [_strip_leading_comments(s) for s in _load_splitter()(SQL)]
ALL = "\n".join(STATEMENTS)

TABLES = ["users", "jars", "transactions", "audit_events", "turn_blocks"]
USER_COL = {"users": "id"}  # các bảng còn lại dùng user_id


def test_tach_duoc_thanh_tung_cau_lenh_va_ham_khong_bi_cat():
    assert len(STATEMENTS) > 40
    assert all(STATEMENTS)
    funcs = [s for s in STATEMENTS if s.startswith("CREATE OR REPLACE FUNCTION")]
    assert len(funcs) == 4
    for f in funcs:
        assert f.count("$$") == 2 and f.rstrip().endswith("$$")
        assert "PERFORM set_config('app.user_id', p_user_id, true);" in f
        assert "SECURITY INVOKER" in f
        assert "SECURITY DEFINER" not in f
        assert "LIMIT" in f  # mọi truy vấn nhiều dòng đều có LIMIT
    # mỗi câu lệnh trong file kết thúc bằng dấu chấm phẩy (bộ tách dựa vào đó)
    code = re.sub(r"^\s*--.*$", "", SQL, flags=re.MULTILINE).rstrip()
    assert code.endswith(";")


def test_khong_co_tham_so_co_ten_va_khong_co_cu_phap_de_hieu_nham_la_tham_so():
    # Data API hiểu :ten là tham số; migrator không gửi tham số nào cho file migration
    assert not re.search(r"(?<![:\w]):[A-Za-z_]", SQL), "có chuỗi giống tham số có tên"


def test_khong_co_mat_khau_hay_bi_mat_trong_file():
    assert not re.search(r"PASSWORD\s+'", SQL, re.IGNORECASE)
    assert not re.search(r"(AKIA|aws_secret|secret_access_key)", SQL, re.IGNORECASE)
    assert not re.search(r"\b\d{12}\b", SQL)  # không có account ID


def test_role_ung_dung_khong_phai_owner_khong_bypass_rls():
    create = next(s for s in STATEMENTS if "CREATE ROLE yofina_app" in s)
    assert "NOBYPASSRLS" in create and "NOSUPERUSER" in create and "LOGIN" in create
    alter = next(s for s in STATEMENTS if s.startswith("ALTER ROLE yofina_app LOGIN"))
    assert "NOBYPASSRLS" in alter
    # master của Aurora (rds_superuser, không phải superuser thật) bị từ chối nếu ALTER nhắc tới
    # NOSUPERUSER: phát hiện khi chạy thử trên Aurora thật (ai-log, luồng A)
    assert "SUPERUSER" not in alter
    assert not re.search(r"ALTER\s+TABLE\s+\w+\s+OWNER\s+TO\s+yofina_app", SQL, re.IGNORECASE)
    assert "SUPERUSER" not in re.sub(r"NOSUPERUSER", "", ALL)


@pytest.mark.parametrize("table", TABLES)
def test_rls_bat_va_force_cung_policy_theo_app_user_id(table):
    col = USER_COL.get(table, "user_id")
    assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in STATEMENTS
    assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in STATEMENTS
    assert f"DROP POLICY IF EXISTS user_isolation ON {table}" in STATEMENTS
    policy = next(s for s in STATEMENTS if s.startswith(f"CREATE POLICY user_isolation ON {table}"))
    expected = f"{col} = current_setting('app.user_id', true)"
    assert f"USING ({expected})" in policy and f"WITH CHECK ({expected})" in policy


def test_moi_bang_du_lieu_nguoi_dung_co_cot_user_id_va_khong_co_bang_nao_thieu_rls():
    created = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", ALL)
    assert set(created) == set(TABLES) | {"schema_migrations"}
    for t in created:
        if t != "schema_migrations":
            assert f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY" in STATEMENTS


def grants():
    out: dict[str, set[str]] = {}
    for s in STATEMENTS:
        m = re.fullmatch(r"GRANT ([A-Z, ]+) ON (\w+) TO yofina_app", s)
        if m:
            out[m.group(2)] = {p.strip() for p in m.group(1).split(",")}
    return out


def test_quyen_toi_thieu():
    g = grants()
    assert set(g) == set(TABLES)  # không có quyền lên schema_migrations
    assert g["audit_events"] == {"SELECT", "INSERT"}  # chỉ thêm
    assert "UPDATE" not in g["transactions"] and "UPDATE" not in g["turn_blocks"]
    assert "DELETE" not in g["users"]
    for privs in g.values():
        assert not privs & {"TRUNCATE", "REFERENCES", "TRIGGER", "ALL"}
    assert not re.search(r"GRANT\s+ALL", ALL, re.IGNORECASE)
    assert "TO PUBLIC" not in ALL


def test_ham_doc_bi_thu_hoi_quyen_cua_public_va_chi_cap_cho_app():
    fns = re.findall(r"CREATE OR REPLACE FUNCTION (\w+)\(", ALL)
    assert fns == [
        "app_get_jar_balances", "app_get_user", "app_query_transactions",
        "app_get_conversation_blocks",
    ]  # fmt: skip
    for fn in fns:
        assert re.search(rf"REVOKE ALL ON FUNCTION {fn}\(.*\) FROM PUBLIC", ALL)
        assert re.search(rf"GRANT EXECUTE ON FUNCTION {fn}\(.*\) TO yofina_app", ALL)


def test_rang_buoc_so_du_khong_am_va_so_tien_nguyen():
    assert "balance_vnd   numeric(14,0) NOT NULL DEFAULT 0 CHECK (balance_vnd >= 0)" in ALL
    assert "amount_vnd  numeric(14,0) NOT NULL CHECK (amount_vnd <> 0)" in ALL
    assert "clock_offset_days  integer NOT NULL DEFAULT 0" in ALL
    assert not re.search(r"\b(float|double|real|money)\b", ALL, re.IGNORECASE)


def test_chi_muc_can_thiet_va_viet_lai_duoc():
    for needle in (
        "ON transactions (user_id, occurred_at DESC, id DESC)",
        "ON transactions (user_id, jar_code, occurred_at DESC, id DESC)",
        "ON turn_blocks (user_id, conversation_id, id)",
        "ON jars (user_id, sort_order, code)",
        "ON audit_events (user_id, created_at DESC)",
    ):
        assert needle in ALL
    for s in STATEMENTS:
        if s.startswith("CREATE TABLE"):
            assert "IF NOT EXISTS" in s.split("(")[0]
        if s.startswith("CREATE INDEX"):
            assert "IF NOT EXISTS" in s.split(" ON ")[0]
        assert not re.match(r"CREATE (UNIQUE )?INDEX (?!IF NOT EXISTS)", s)
