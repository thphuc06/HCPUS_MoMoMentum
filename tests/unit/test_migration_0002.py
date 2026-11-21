"""Kiểm tĩnh db/migrations/0002_jar_view.sql: tách được bằng bộ tách thật của migrator, hàm đọc theo
đúng quy ước của 0001 (SECURITY INVOKER, tự set_config, có LIMIT, chỉ yofina_app được EXECUTE)."""

from __future__ import annotations

import importlib.util
import re

from conftest import REPO

SQL_PATH = REPO / "db" / "migrations" / "0002_jar_view.sql"
SPLITTER_PATH = REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py"


def _statements() -> list[str]:
    spec = importlib.util.spec_from_file_location("migrator_sqlsplit", SPLITTER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = []
    for stmt in mod.split_statements(SQL_PATH.read_text(encoding="utf-8")):
        lines = stmt.strip().splitlines()
        while lines and (not lines[0].strip() or lines[0].lstrip().startswith("--")):
            lines.pop(0)
        out.append("\n".join(lines).strip())
    return out


def test_ba_cau_lenh_va_ham_khong_bi_cat():
    stmts = _statements()
    assert len(stmts) == 3
    fn = stmts[0]
    assert fn.startswith("CREATE OR REPLACE FUNCTION app_get_jar_view(p_user_id text)")
    assert fn.count("$$") == 2 and fn.rstrip().endswith("$$")


def test_ham_theo_quy_uoc_rls_va_quyen():
    fn, revoke, grant = _statements()
    assert "SECURITY INVOKER" in fn and "SECURITY DEFINER" not in fn
    assert "PERFORM set_config('app.user_id', p_user_id, true);" in fn
    assert "LEFT JOIN jars" in fn and re.search(r"LIMIT\s+20", fn)
    assert revoke == "REVOKE ALL ON FUNCTION app_get_jar_view(text) FROM PUBLIC"
    assert grant == "GRANT EXECUTE ON FUNCTION app_get_jar_view(text) TO yofina_app"


def test_khong_dau_hai_cham_dinh_lien_chu():
    # quy ước db/README.md: Data API có thể hiểu nhầm là tham số có tên (kể cả trong chú thích)
    text = SQL_PATH.read_text(encoding="utf-8")
    assert not re.search(r"(?<!:):[A-Za-z_]", text.replace("::", "  "))
