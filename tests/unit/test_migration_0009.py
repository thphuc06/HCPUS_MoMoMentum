"""Kiểm tĩnh db/migrations/0009_forecast_pipeline.sql: bộ tách thật của migrator, hàm đọc SECURITY INVOKER tự đặt app.user_id,
hàm liệt kê người dùng là SECURITY DEFINER duy nhất và chỉ trả id, quyền chỉ cho yofina_app. Chạy thật ở tests/local_pg/."""

from __future__ import annotations

import importlib.util
import re

from conftest import REPO

SQL_PATH = REPO / "db" / "migrations" / "0009_forecast_pipeline.sql"
_spec = importlib.util.spec_from_file_location(
    "migrator_sqlsplit", REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

SQL = SQL_PATH.read_text(encoding="utf-8")
STATEMENTS = _mod.split_migration(SQL)
FUNCS = [s for s in STATEMENTS if s.startswith("CREATE OR REPLACE FUNCTION")]
NAMES = [
    "app_get_forecast_context",
    "app_get_forecast_run",
    "app_list_forecast_users",
    "app_prune_forecast_runs",
]


def test_tach_duoc_va_ham_khong_bi_cat():
    assert all(s.strip() for s in STATEMENTS)
    assert len(FUNCS) == 4
    for f in FUNCS:
        assert f.count("$$") == 2 and f.rstrip().endswith("$$")
    assert all(not _mod.named_params(s) for s in STATEMENTS)
    assert not re.search(r"(?<![:\w]):[A-Za-z_]", SQL)


def test_chi_mot_ham_security_definer_va_no_chi_tra_id():
    definers = [f for f in FUNCS if "SECURITY DEFINER" in f]
    assert len(definers) == 1 and "app_list_forecast_users" in definers[0]
    d = definers[0]
    assert "RETURNS TABLE (user_id text)" in d and "SET search_path = public, pg_temp" in d
    assert re.search(r"SELECT u\.id\s+FROM users u", d)  # không trả cột nào khác
    assert "LIMIT LEAST(GREATEST(coalesce(p_limit, 200), 1), 500)" in d


def test_ham_doc_tu_dat_user_id_va_co_gioi_han():
    for f in FUNCS:
        if "SECURITY INVOKER" not in f:
            continue
        assert "PERFORM set_config('app.user_id', p_user_id, true);" in f
    ctx = next(f for f in FUNCS if "app_get_forecast_context" in f)
    assert "LIMIT 40" in ctx and "app_get_daily_spend" in ctx and "app_list_obligations" in ctx
    run = next(f for f in FUNCS if "app_get_forecast_run" in f)
    assert "LIMIT 1" in run and "jar_state" in run  # lọc jar_state để dưới 64 KB mỗi dòng


def test_quyen_chi_cho_yofina_app_va_thu_hoi_public():
    sigs = {
        "app_get_forecast_context": "text, timestamptz, text, integer",
        "app_get_forecast_run": "text, uuid, text",
        "app_list_forecast_users": "integer",
        "app_prune_forecast_runs": "text, integer",
    }
    for name, sig in sigs.items():
        assert f"REVOKE ALL ON FUNCTION {name}({sig}) FROM PUBLIC" in STATEMENTS
        assert f"GRANT EXECUTE ON FUNCTION {name}({sig}) TO yofina_app" in STATEMENTS
    assert not re.search(r"ALTER\s+ROLE|PASSWORD\s+'", SQL, re.I)


def test_don_lan_chay_cu_giu_lan_moi_nhat_cua_moi_hu():
    prune = next(f for f in FUNCS if "app_prune_forecast_runs" in f)
    assert "DISTINCT ON (s.jar_code)" in prune and "NOT IN" in prune
    assert "OFFSET GREATEST(coalesce(p_keep, 5), 1)" in prune


def test_ten_ham_khop_danh_sach():
    for n in NAMES:
        assert any(f"FUNCTION {n}(" in f for f in FUNCS)
