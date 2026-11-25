"""Kiểm tĩnh db/migrations/0058_sinking_commitments.sql (CHƯA chạy trên AWS; trên nhánh feat/default-six-jars là 0056): bộ tách thật
của migrator, không tham số tên, đúng thứ tự câu lệnh; cột `jars.sinking_items` mặc định mảng rỗng và chỉ hũ `sinking` có phần tử;
hàm đọc mới bọc `app_get_jar_state_with_purpose` của 0057 và chỉ THÊM `sinking_items`; hai hàm thay thế giữ đúng chữ ký và kiểu trả
về của 0057 và chỉ THÊM khóa `sinking_items`."""

from __future__ import annotations

import importlib.util
import re

from conftest import REPO

MIGRATIONS = REPO / "db" / "migrations"
SQL_0058 = (MIGRATIONS / "0058_sinking_commitments.sql").read_text(encoding="utf-8")
SQL_0057 = (MIGRATIONS / "0057_default_six_jars.sql").read_text(encoding="utf-8")
_spec = importlib.util.spec_from_file_location(
    "migrator_sqlsplit", REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
STATEMENTS = _mod.split_migration(SQL_0058)
OLD = _mod.split_migration(SQL_0057)
REPLACED = ("app_get_overview_with_purpose", "app_get_jar_detail_with_purpose")


def _fn(statements: list[str], name: str) -> str:
    return next(s for s in statements if re.match(rf"CREATE (OR REPLACE )?FUNCTION {name}\(", s))


def _head(fn: str) -> str:
    """Chữ ký và kiểu trả về (phần trước `AS $$`), bỏ `OR REPLACE`."""
    return " ".join(fn.split("AS $$")[0].replace("CREATE OR REPLACE", "CREATE").split())


def _columns(fn: str) -> list[str]:
    body = re.search(r"RETURNS TABLE \((.*?)\)\s*LANGUAGE", fn, re.S)
    assert body, fn[:200]
    return [c.split()[0] for c in body.group(1).replace("\n", " ").split(",") if c.strip()]


def test_tach_duoc_khong_tham_so_khong_lenh_nguy_hiem():
    assert STATEMENTS and "-- @@" in SQL_0058
    assert all(not _mod.named_params(s) for s in STATEMENTS)
    assert not re.search(r"(?<![:\w]):[A-Za-z_]", SQL_0058)
    assert not re.search(
        r"ALTER\s+ROLE|PASSWORD\s+'|DROP\s+TABLE|TRUNCATE|DROP\s+FUNCTION|DROP\s+CONSTRAINT",
        SQL_0058,
        re.I,
    )
    for s in STATEMENTS:
        assert _mod.split_statements(s) == [s], s[:80]


def test_thu_tu_cau_lenh():
    heads = [" ".join(s.split("(")[0].split()) for s in STATEMENTS]
    assert heads == [
        "ALTER TABLE jars ADD COLUMN sinking_items jsonb NOT NULL DEFAULT '[]'::jsonb CHECK",
        "CREATE FUNCTION app_get_jar_state_with_commitments",
        "CREATE OR REPLACE FUNCTION app_get_overview_with_purpose",
        "CREATE OR REPLACE FUNCTION app_get_jar_detail_with_purpose",
        "REVOKE ALL ON FUNCTION app_get_jar_state_with_commitments",
        "GRANT EXECUTE ON FUNCTION app_get_jar_state_with_commitments",
    ]
    assert STATEMENTS[-2:] == [
        "REVOKE ALL ON FUNCTION app_get_jar_state_with_commitments(text) FROM PUBLIC",
        "GRANT EXECUTE ON FUNCTION app_get_jar_state_with_commitments(text) TO yofina_app",
    ]


def test_cot_sinking_items_mac_dinh_rong_va_chi_o_hu_sinking():
    col = STATEMENTS[0]
    assert "NOT NULL DEFAULT '[]'::jsonb" in col  # ví cũ nhận mảng rỗng, không phải NULL
    assert "jsonb_typeof(sinking_items) = 'array'" in col
    # NOT DISTINCT để purpose NULL (hũ cũ) không lọt CHECK khi mảng có phần tử
    assert "(sinking_items = '[]'::jsonb OR purpose IS NOT DISTINCT FROM 'sinking')" in col


def test_ham_doc_moi_boc_ham_cua_0057_va_chi_them_sinking_items():
    new = _fn(STATEMENTS, "app_get_jar_state_with_commitments")
    base = _fn(OLD, "app_get_jar_state_with_purpose")
    assert _columns(new) == [*_columns(base), "sinking_items"]
    assert "FROM app_get_jar_state_with_purpose(p_user_id) s" in new
    assert "PERFORM set_config('app.user_id', p_user_id, true);" in new
    assert new.count("$$") == 2 and "SECURITY INVOKER" in new
    assert "SET search_path = public, pg_temp" in new


def test_hai_ham_thay_the_giu_chu_ky_va_chi_them_khoa():
    for name in REPLACED:
        fn, old = _fn(STATEMENTS, name), _fn(OLD, name)
        assert _head(fn) == _head(old), name
        assert fn.count("$$") == 2 and "SECURITY INVOKER" in fn, name
        assert (
            "'purpose', j.purpose, 'sinking_items', NULLIF(j.sinking_items, '[]'::jsonb)"
            in " ".join(fn.split())
        ), name  # mảng rỗng thì vắng khóa, như hũ không phải sinking
        assert "j.user_id = p_user_id" in fn, name
    overview = _fn(STATEMENTS, REPLACED[0])
    assert "app_get_overview(p_user_id, p_now, p_tz)" in overview
    assert "ORDER BY item.ordinality" in overview
    detail = _fn(STATEMENTS, REPLACED[1])
    assert "app_get_jar_detail(p_user_id, p_jar_code, p_now, p_tz)" in detail
    assert (
        "v_data->'jar' IS NOT NULL AND v_metadata IS NOT NULL" in detail
    )  # hũ lạ không sinh khóa jar


def test_dung_sau_0057():
    names = sorted(p.name for p in MIGRATIONS.glob("*.sql"))
    i = names.index("0058_sinking_commitments.sql")
    assert names[i - 1] == "0057_default_six_jars.sql"
