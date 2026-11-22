"""Kiểm tĩnh db/migrations/0010_what_if_audit.sql (phase 3): bộ tách thật của migrator, RLS FORCE và quyền của ba bảng mới, cột
có kiểu của bản ghi lượt trong audit_events, hàm đọc SECURITY INVOKER, tập giá trị khớp hằng số trong `yofina_core.wallet`.
Chạy thật trên PostgreSQL cục bộ: chạy `uv run scripts/db_local_check.py` (chạy 0001 tới 0010) hoặc kịch bản kiểm riêng của 0010."""

from __future__ import annotations

import importlib.util
import re

import pytest
from conftest import REPO

from yofina_core import wallet

SQL_PATH = REPO / "db" / "migrations" / "0010_what_if_audit.sql"
_spec = importlib.util.spec_from_file_location(
    "migrator_sqlsplit", REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

SQL = SQL_PATH.read_text(encoding="utf-8")
STATEMENTS = _mod.split_migration(SQL)
FUNCS = [s for s in STATEMENTS if s.startswith("CREATE OR REPLACE FUNCTION")]
TABLES = ["scenarios", "nudges", "feedback"]


def sql_set(statement: str, column: str) -> tuple[str, ...]:
    """Tập giá trị trong `column IN ('a', 'b', ...)` của một câu lệnh."""
    m = re.search(rf"{column}\s+IN\s*\(([^)]*)\)", statement)
    assert m, f"không thấy CHECK IN của {column}"
    return tuple(re.findall(r"'([^']*)'", m.group(1)))


def create_table(name: str) -> str:
    return next(s for s in STATEMENTS if s.startswith(f"CREATE TABLE IF NOT EXISTS {name} "))


def test_tach_duoc_va_ham_khong_bi_cat():
    assert len(STATEMENTS) > 30 and all(s.strip() for s in STATEMENTS)
    assert len(FUNCS) == 4
    for f in FUNCS:
        assert f.count("$$") == 2 and f.rstrip().endswith("$$")
        assert "SECURITY INVOKER" in f and "SECURITY DEFINER" not in f
        assert "PERFORM set_config('app.user_id', p_user_id, true);" in f
        assert "SET search_path = public, pg_temp" in f
    assert all(not _mod.named_params(s) for s in STATEMENTS)
    assert not re.search(r"(?<![:\w]):[A-Za-z_]", SQL)


def test_viet_lai_duoc_va_khong_dong_den_role_hay_migration_cu():
    for s in STATEMENTS:
        if s.startswith("CREATE TABLE"):
            assert "IF NOT EXISTS" in s.split("(")[0]
        if s.startswith("CREATE INDEX") or s.startswith("CREATE UNIQUE INDEX"):
            assert "IF NOT EXISTS" in s.split(" ON ")[0]
        if s.startswith("ALTER TABLE audit_events ADD COLUMN"):
            assert "IF NOT EXISTS" in s
        assert not re.search(r"ALTER\s+ROLE|PASSWORD\s+'|DROP\s+TABLE|TRUNCATE", s, re.I)


@pytest.mark.parametrize("table", TABLES)
def test_rls_force_policy_va_khoa_ngoai_cascade(table):
    expected = "user_id = current_setting('app.user_id', true)"
    assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in STATEMENTS
    assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in STATEMENTS
    policy = next(s for s in STATEMENTS if s.startswith(f"CREATE POLICY user_isolation ON {table}"))
    assert f"USING ({expected})" in policy and f"WITH CHECK ({expected})" in policy
    assert f"DROP POLICY IF EXISTS user_isolation ON {table}" in STATEMENTS
    create = create_table(table)
    assert re.search(r"user_id\s+text NOT NULL REFERENCES users \(id\) ON DELETE CASCADE", create)


def test_quyen_cua_yofina_app():
    assert (
        "GRANT SELECT, INSERT, DELETE ON scenarios TO yofina_app" in STATEMENTS
    )  # dữ liệu dẫn xuất
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON nudges TO yofina_app" in STATEMENTS
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON feedback TO yofina_app" in STATEMENTS
    # audit_events: KHÔNG cấp thêm quyền nào (vẫn chỉ thêm)
    assert not any("audit_events" in s and s.startswith("GRANT") for s in STATEMENTS)
    assert not any("audit_events" in s and s.startswith("CREATE POLICY") for s in STATEMENTS)


def test_tap_gia_tri_khop_hang_so():
    assert sql_set(create_table("scenarios"), "kind") == wallet.SCENARIO_KINDS
    nudges = create_table("nudges")
    assert sql_set(nudges, "kind") == wallet.NUDGE_KINDS
    assert sql_set(nudges, "status") == wallet.NUDGE_STATUSES
    assert sql_set(create_table("feedback"), "decision") == wallet.FEEDBACK_DECISIONS
    intent = next(s for s in STATEMENTS if "ADD COLUMN IF NOT EXISTS intent" in s)
    assert sql_set(intent, "intent") == wallet.INTENTS


def test_nudges_co_rang_buoc_trang_thai_va_ngay():
    n = create_table("nudges")
    assert "CHECK (fire_on > created_app_date)" in n  # ngày nhắc phải sau ngày tạo (ngày mô phỏng)
    assert "CHECK ((status = 'cancelled') = (cancelled_at IS NOT NULL))" in n
    assert "CHECK ((status = 'sent') = (sent_at IS NOT NULL))" in n
    dedupe = next(s for s in STATEMENTS if "nudges_user_dedupe_idx" in s)
    assert dedupe.startswith("CREATE UNIQUE INDEX") and "WHERE dedupe_key IS NOT NULL" in dedupe


def test_feedback_mot_dong_moi_phuong_an_va_khong_dinh_null():
    f = create_table("feedback")
    assert "UNIQUE (user_id, trace_id, block_id, option_id)" in f
    assert re.search(r"block_id\s+text NOT NULL DEFAULT ''", f)  # khóa duy nhất không có NULL


def test_scenarios_giu_result_duoi_gioi_han_data_api():
    s = create_table("scenarios")
    assert "octet_length(result::text) <= 60000" in s
    assert "spec_hash ~ '^[0-9a-f]{64}$'" in re.sub(r"\s+", " ", s)
    assert (
        "REFERENCES forecast_runs" not in s
    )  # baseline_run_id không có khóa ngoại (lần chạy cũ bị dọn)


def test_audit_events_them_cot_co_kieu_cho_ban_ghi_luot():
    cols = {}
    for s in STATEMENTS:
        m = re.match(r"ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS (\w+) (\w+)", s)
        if m:
            cols[m.group(1)] = (m.group(2), s)
    assert set(cols) == {
        "conversation_id", "intent", "data_used", "rules_checked", "confidence", "blocks_emitted",
        "token_usage", "step_timings", "duration_ms",
    }  # fmt: skip
    arrays = {"data_used", "rules_checked", "blocks_emitted", "step_timings"}
    objects = {"confidence", "token_usage"}
    for name in arrays | objects:
        typ, stmt = cols[name]
        assert typ == "jsonb"
        kind = "array" if name in arrays else "object"
        assert f"jsonb_typeof({name}) = '{kind}'" in stmt
    assert cols["duration_ms"][0] == "integer" and "duration_ms >= 0" in cols["duration_ms"][1]
    # mỗi lượt đúng một bản ghi lượt
    once = next(s for s in STATEMENTS if "audit_events_turn_once_idx" in s)
    assert once.startswith("CREATE UNIQUE INDEX")
    assert "event_type = 'agent_turn'" in once and "(user_id, trace_id)" in once


def test_ham_doc_theo_nguoi_dung_va_gioi_han():
    trace = next(f for f in FUNCS if "app_get_trace(" in f)
    assert "a.user_id = p_user_id" in trace and "a.event_type = 'agent_turn'" in trace
    assert re.search(r"LIMIT 1;\s*END", trace)
    nudges = next(f for f in FUNCS if "app_list_nudges(" in f)
    assert "LIMIT LEAST(GREATEST(coalesce(p_limit, 50), 1), 200)" in nudges
    scen = next(f for f in FUNCS if "app_get_scenario(" in f)
    assert "s.user_id = p_user_id" in scen and "LIMIT 1" in scen
    prune = next(f for f in FUNCS if "app_prune_scenarios(" in f)
    assert "OFFSET GREATEST(coalesce(p_keep, 50), 1)" in prune


def test_quyen_ham_chi_cho_yofina_app():
    sigs = {
        "app_get_trace": "text, text",
        "app_get_scenario": "text, uuid",
        "app_list_nudges": "text, text, integer",
        "app_prune_scenarios": "text, integer",
    }
    for name, sig in sigs.items():
        assert f"REVOKE ALL ON FUNCTION {name}({sig}) FROM PUBLIC" in STATEMENTS
        assert f"GRANT EXECUTE ON FUNCTION {name}({sig}) TO yofina_app" in STATEMENTS
