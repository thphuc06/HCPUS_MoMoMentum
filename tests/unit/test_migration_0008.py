"""Kiểm tĩnh db/migrations/0008_wallet_hints.sql (cờ chuyển tiền cho người, mực dự báo). Chạy thật ở tests/local_pg và trên Aurora."""

from __future__ import annotations

import importlib.util
import re

from conftest import REPO

_spec = importlib.util.spec_from_file_location(
    "migrator_sqlsplit", REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
SQL = (REPO / "db" / "migrations" / "0008_wallet_hints.sql").read_text(encoding="utf-8")
STATEMENTS = _mod.split_migration(SQL)


def test_tach_duoc_viet_lai_duoc_va_khong_dau_hai_cham_dinh_chu():
    assert len(STATEMENTS) == 5 and all(not _mod.named_params(s) for s in STATEMENTS)
    assert not re.search(r"(?<![:\w]):[A-Za-z_]", SQL)
    assert (
        "ADD COLUMN IF NOT EXISTS is_person_transfer boolean NOT NULL DEFAULT false"
        in STATEMENTS[0]
    )
    assert STATEMENTS[1].startswith(
        "DROP FUNCTION IF EXISTS app_get_forecast_summaries(text, text)"
    )
    fn = STATEMENTS[2]
    assert "SECURITY INVOKER" in fn and "PERFORM set_config('app.user_id', p_user_id, true);" in fn
    assert (
        "forecast_floor_vnd numeric" in fn
        and "f.day < s.payday_date" in fn
        and "min(f.balance_p50_vnd)" in fn
    )
    assert any(
        s.startswith("REVOKE ALL ON FUNCTION app_get_forecast_summaries") for s in STATEMENTS
    )
    assert any(s.endswith("TO yofina_app") for s in STATEMENTS)
