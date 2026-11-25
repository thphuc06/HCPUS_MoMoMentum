"""Kiểm tĩnh db/migrations/0057_default_six_jars.sql (CHƯA chạy trên AWS; trên nhánh feat/default-six-jars là 0055): bộ tách thật
của migrator, không tham số tên, đúng thứ tự câu lệnh; cột `purpose` chỉ nhận đúng các mục đích của `yofina_core.wallet` và chỉ ở hũ
`saving`; ba hàm đọc mới bọc hàm đọc cũ, giữ nguyên cột của hàm cũ và chỉ THÊM `purpose`; không đụng danh mục hũ (việc của 0059)."""

from __future__ import annotations

import importlib.util
import re

from conftest import REPO

from yofina_core.wallet import JAR_PURPOSES

MIGRATIONS = REPO / "db" / "migrations"
SQL_0057 = (MIGRATIONS / "0057_default_six_jars.sql").read_text(encoding="utf-8")
_spec = importlib.util.spec_from_file_location(
    "migrator_sqlsplit", REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
STATEMENTS = _mod.split_migration(SQL_0057)
NEW_FUNCS = {
    "app_get_jar_state_with_purpose": "text",
    "app_get_overview_with_purpose": "text, timestamptz, text",
    "app_get_jar_detail_with_purpose": "text, text, timestamptz, text",
}


def _fn(statements: list[str], name: str) -> str:
    return next(s for s in statements if re.match(rf"CREATE (OR REPLACE )?FUNCTION {name}\(", s))


def _latest_before_0057(name: str) -> str:
    """Định nghĩa mới nhất của hàm `name` trong các migration đứng trước 0057 (bản mà Ledger cũ đang gọi)."""
    found = None
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name >= "0057":
            break
        for s in _mod.split_migration(path.read_text(encoding="utf-8")):
            if re.match(rf"CREATE (OR REPLACE )?FUNCTION {name}\(", s):
                found = s
    assert found, name
    return found


def _columns(fn: str) -> list[str]:
    body = re.search(r"RETURNS TABLE \((.*?)\)\s*LANGUAGE", fn, re.S)
    assert body, fn[:200]
    return [c.split()[0] for c in body.group(1).replace("\n", " ").split(",") if c.strip()]


def test_tach_duoc_khong_tham_so_khong_lenh_nguy_hiem():
    assert STATEMENTS and "-- @@" in SQL_0057
    assert all(not _mod.named_params(s) for s in STATEMENTS)
    assert not re.search(r"(?<![:\w]):[A-Za-z_]", SQL_0057)
    assert not re.search(
        r"ALTER\s+ROLE|PASSWORD\s+'|DROP\s+TABLE|TRUNCATE|DROP\s+FUNCTION", SQL_0057, re.I
    )
    # mỗi khối tách theo "-- @@" đúng một câu lệnh: không còn dấu chấm phẩy ngoài thân $$
    for s in STATEMENTS:
        assert _mod.split_statements(s) == [s], s[:80]


def test_thu_tu_cau_lenh():
    heads = [" ".join(s.split("(")[0].split()) for s in STATEMENTS]
    assert heads == [
        "ALTER TABLE jars ADD COLUMN purpose text CHECK",
        "ALTER TABLE jar_templates ADD COLUMN purpose text CHECK",
        "ALTER TABLE jars DROP CONSTRAINT jars_goal_check",
        "ALTER TABLE jars ADD CONSTRAINT jars_goal_check CHECK",
        "CREATE FUNCTION app_get_jar_state_with_purpose",
        "CREATE FUNCTION app_get_overview_with_purpose",
        "CREATE FUNCTION app_get_jar_detail_with_purpose",
        *(f"REVOKE ALL ON FUNCTION {n}" for n in NEW_FUNCS),
        *(f"GRANT EXECUTE ON FUNCTION {n}" for n in NEW_FUNCS),
    ]
    for name, sig in NEW_FUNCS.items():
        assert f"REVOKE ALL ON FUNCTION {name}({sig}) FROM PUBLIC" in STATEMENTS
        assert f"GRANT EXECUTE ON FUNCTION {name}({sig}) TO yofina_app" in STATEMENTS


def test_cot_purpose_chi_nhan_muc_dich_cua_wallet_va_chi_o_hu_saving():
    for table in ("jars", "jar_templates"):
        stmt = next(
            s for s in STATEMENTS if s.startswith(f"ALTER TABLE {table} ADD COLUMN purpose")
        )
        assert "purpose IS NULL OR (kind = 'saving' AND purpose IN (" in stmt
        assert tuple(re.findall(r"'(\w+)'", stmt.split("purpose IN", 1)[1])) == JAR_PURPOSES
    goal = next(s for s in STATEMENTS if "ADD CONSTRAINT jars_goal_check" in s)
    # hạn không kèm số tiền chỉ được ở hũ sinking, long_term (khớp yofina_core.params và blocks)
    assert "(goal_vnd IS NULL OR goal_vnd > 0)" in goal
    assert "coalesce(purpose IN ('sinking', 'long_term'), false)" in goal


def test_ham_doc_moi_boc_ham_cu_va_chi_them_purpose():
    state = _fn(STATEMENTS, "app_get_jar_state_with_purpose")
    old_state = _latest_before_0057("app_get_jar_state")
    assert _columns(state) == [*_columns(old_state), "purpose"]
    assert "FROM app_get_jar_state(p_user_id) s" in state
    overview = _fn(STATEMENTS, "app_get_overview_with_purpose")
    assert "app_get_overview(p_user_id, p_now, p_tz)" in overview
    assert "jsonb_build_object('purpose', j.purpose)" in overview
    assert "ORDER BY item.ordinality" in overview  # giữ thứ tự hũ của hàm cũ
    detail = _fn(STATEMENTS, "app_get_jar_detail_with_purpose")
    assert "app_get_jar_detail(p_user_id, p_jar_code, p_now, p_tz)" in detail
    assert "jsonb_set(v_data, '{jar,purpose}', to_jsonb(v_purpose))" in detail
    for fn in (state, overview, detail):
        assert fn.count("$$") == 2 and "SECURITY INVOKER" in fn
        assert "SET search_path = public, pg_temp" in fn
        assert "j.user_id = p_user_id" in fn  # chỉ đọc hũ của chính người dùng
    assert "PERFORM set_config('app.user_id', p_user_id, true);" in state


def test_khong_dung_ham_doc_cu_va_danh_muc_hu():
    code = "\n".join(STATEMENTS)
    assert not re.search(
        r"FUNCTION app_(?:list_jars|get_jar_state|get_overview|get_jar_detail|get_forecast_context)\(",
        code,
    )
    assert "INSERT INTO" not in code and "UPDATE jar_templates" not in code


def test_dung_sau_0056_cua_main():
    names = sorted(p.name for p in MIGRATIONS.glob("*.sql"))
    i = names.index("0057_default_six_jars.sql")
    assert names[i - 1] == "0056_ingest_pii_kinds.sql"
    assert len({n[:4] for n in names}) == len(names)  # không trùng số migration
