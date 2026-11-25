"""Kiểm tĩnh db/migrations/0051_scenario_conversation.sql: bộ tách thật của migrator, hai cột mới của `scenarios` (viết lại được, có
CHECK), chỉ mục riêng cho cuộc chat, hàm đọc SECURITY INVOKER tự đặt app.user_id và có LIMIT, quyền chỉ cho yofina_app, không sửa
migration cũ. Chạy thật trên PostgreSQL cục bộ ở tests/local_pg/test_scenario_conversation.py."""

from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path

from conftest import REPO

SQL_PATH = REPO / "db" / "migrations" / "0051_scenario_conversation.sql"
_spec = importlib.util.spec_from_file_location(
    "migrator_sqlsplit", REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

SQL = SQL_PATH.read_text(encoding="utf-8")
STATEMENTS = _mod.split_migration(SQL)
FUNC = next(s for s in STATEMENTS if s.startswith("CREATE OR REPLACE FUNCTION"))
SIG = "app_list_conversation_scenarios(text, text, integer)"


def test_tach_duoc_khong_tham_so_ten_khong_hai_cham_dinh_chu():
    assert len(STATEMENTS) == 6 and all(s.strip() for s in STATEMENTS)
    assert FUNC.count("$$") == 2 and FUNC.rstrip().endswith("$$")
    assert all(not _mod.named_params(s) for s in STATEMENTS)
    assert not re.search(r"(?<![:\w]):[A-Za-z_]", SQL)
    assert not re.search(r"ALTER\s+ROLE|PASSWORD\s+'|DROP\s+TABLE|TRUNCATE", SQL, re.I)


def test_hai_cot_moi_viet_lai_duoc_va_co_check():
    cols = {}
    for s in STATEMENTS:
        m = re.match(r"ALTER TABLE scenarios ADD COLUMN IF NOT EXISTS (\w+) (\w+)", s)
        if m:
            cols[m.group(1)] = (m.group(2), s)
    assert set(cols) == {"conversation_id", "bundle"}
    assert cols["conversation_id"][0] == "text"
    assert "conversation_id IS NULL OR length(conversation_id) BETWEEN 1 AND 256" in cols["conversation_id"][1]
    assert cols["bundle"][0] == "jsonb"
    assert "bundle IS NULL OR jsonb_typeof(bundle) = 'array'" in cols["bundle"][1]
    assert not any("NOT NULL" in s for _, s in cols.values())  # dòng cũ phải còn hợp lệ (NULL)


def test_chi_muc_theo_nguoi_dung_cuoc_chat_va_thoi_gian():
    idx = next(s for s in STATEMENTS if s.startswith("CREATE INDEX"))
    assert "IF NOT EXISTS" in idx.split(" ON ")[0]
    assert "ON scenarios (user_id, conversation_id, created_at DESC)" in idx
    assert "WHERE conversation_id IS NOT NULL" in idx


def test_ham_doc_security_invoker_dat_user_va_co_gioi_han():
    assert "SECURITY INVOKER" in FUNC and "SECURITY DEFINER" not in FUNC
    assert "PERFORM set_config('app.user_id', p_user_id, true);" in FUNC
    assert "SET search_path = public, pg_temp" in FUNC
    assert "p_limit integer DEFAULT 5" in FUNC
    assert "LIMIT LEAST(GREATEST(coalesce(p_limit, 5), 1), 10)" in FUNC
    assert "s.user_id = p_user_id AND s.conversation_id = p_conversation_id" in FUNC
    assert "ORDER BY s.created_at DESC" in FUNC  # mới nhất trước
    for col in ("id uuid", "kind text", "spec jsonb", "bundle jsonb", "result_label text", "result_bundle jsonb", "created_at timestamptz"):
        assert col in FUNC


def test_quyen_ham_chi_cho_yofina_app_va_khong_dong_quyen_bang():
    assert f"REVOKE ALL ON FUNCTION {SIG} FROM PUBLIC" in STATEMENTS
    assert f"GRANT EXECUTE ON FUNCTION {SIG} TO yofina_app" in STATEMENTS
    assert not any(s.startswith(("GRANT SELECT", "CREATE POLICY", "ALTER TABLE scenarios ENABLE")) for s in STATEMENTS)


def test_khong_sua_migration_cu():
    out = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", "db/migrations"],
        cwd=REPO, capture_output=True, text=True, check=False,
    )  # fmt: skip
    if out.returncode == 0:
        changed = [line for line in out.stdout.splitlines() if line.strip()]
        assert all(Path(c).name >= SQL_PATH.name for c in changed), changed
