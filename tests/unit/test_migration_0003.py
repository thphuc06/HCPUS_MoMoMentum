"""Kiểm tĩnh db/migrations/0003_conversation_turns.sql: tách được bằng bộ tách thật của migrator, bảng có RLS
FORCE theo user_id, hàm đọc theo quy ước của 0001 (SECURITY INVOKER, tự set_config, có LIMIT, chỉ yofina_app EXECUTE)."""

from __future__ import annotations

import importlib.util
import re

from conftest import REPO

SQL_PATH = REPO / "db" / "migrations" / "0003_conversation_turns.sql"
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


def test_ham_plpgsql_khong_bi_cat():
    stmts = _statements()
    fns = [s for s in stmts if s.startswith("CREATE OR REPLACE FUNCTION")]
    assert len(fns) == 2
    for fn in fns:
        assert fn.count("$$") == 2 and fn.rstrip().endswith("$$")


def test_bang_co_rls_force_va_quyen_toi_thieu():
    text = "\n".join(_statements())
    assert "ALTER TABLE conversation_turns ENABLE ROW LEVEL SECURITY" in text
    assert "ALTER TABLE conversation_turns FORCE ROW LEVEL SECURITY" in text
    assert "USING (user_id = current_setting('app.user_id', true))" in text
    assert "UNIQUE (user_id, conversation_id, trace_id)" in text
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON conversation_turns TO yofina_app" in text


def test_ham_doc_theo_quy_uoc():
    fns = [s for s in _statements() if s.startswith("CREATE OR REPLACE FUNCTION")]
    for fn in fns:
        assert "SECURITY INVOKER" in fn and "SECURITY DEFINER" not in fn
        assert "PERFORM set_config('app.user_id', p_user_id, true);" in fn
        assert re.search(r"LIMIT\s+LEAST", fn)
    text = "\n".join(_statements())
    for sig in (
        "app_get_conversation_turns(text, text, integer)",
        "app_list_conversations(text, integer)",
    ):
        assert f"REVOKE ALL ON FUNCTION {sig} FROM PUBLIC" in text
        assert f"GRANT EXECUTE ON FUNCTION {sig} TO yofina_app" in text


def test_khong_dau_hai_cham_dinh_lien_chu():
    text = SQL_PATH.read_text(encoding="utf-8")
    assert not re.search(r"(?<!:):[A-Za-z_]", text.replace("::", "  "))
