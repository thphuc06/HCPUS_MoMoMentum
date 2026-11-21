"""Kiểm tĩnh db/migrations/0004_confirm_resolutions.sql: tách được bằng bộ tách thật của migrator, bảng có
RLS FORCE theo user_id và khóa unique (user_id, confirm_block_id), hàm đọc theo quy ước của 0001."""

from __future__ import annotations

import importlib.util
import re

from conftest import REPO

SQL_PATH = REPO / "db" / "migrations" / "0004_confirm_resolutions.sql"
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
    fns = [s for s in _statements() if s.startswith("CREATE OR REPLACE FUNCTION")]
    assert len(fns) == 2
    for fn in fns:
        assert fn.count("$$") == 2 and fn.rstrip().endswith("$$")


def test_bang_co_rls_force_unique_va_quyen_toi_thieu():
    text = "\n".join(_statements())
    assert "ALTER TABLE confirm_resolutions ENABLE ROW LEVEL SECURITY" in text
    assert "ALTER TABLE confirm_resolutions FORCE ROW LEVEL SECURITY" in text
    assert "USING (user_id = current_setting('app.user_id', true))" in text
    assert "UNIQUE (user_id, confirm_block_id)" in text  # một đề nghị của một người chỉ một lần
    assert "REFERENCES users (id) ON DELETE CASCADE" in text
    # chỉ thêm và xóa (đặt lại demo): không sửa một đề nghị đã thực hiện
    assert "GRANT SELECT, INSERT, DELETE ON confirm_resolutions TO yofina_app" in text
    assert "UPDATE ON confirm_resolutions" not in text


def test_ham_doc_theo_quy_uoc():
    fns = [s for s in _statements() if s.startswith("CREATE OR REPLACE FUNCTION")]
    for fn in fns:
        assert "SECURITY INVOKER" in fn and "SECURITY DEFINER" not in fn
        assert "PERFORM set_config('app.user_id', p_user_id, true);" in fn
        assert re.search(r"LIMIT\s+(LEAST|1\b)", fn)
    text = "\n".join(_statements())
    for sig in (
        "app_get_confirm_resolutions(text, text, integer)",
        "app_get_confirm_resolution(text, text)",
    ):
        assert f"REVOKE ALL ON FUNCTION {sig} FROM PUBLIC" in text
        assert f"GRANT EXECUTE ON FUNCTION {sig} TO yofina_app" in text


def test_khong_dau_hai_cham_dinh_lien_chu():
    text = SQL_PATH.read_text(encoding="utf-8")
    assert not re.search(r"(?<!:):[A-Za-z_]", text.replace("::", "  "))
