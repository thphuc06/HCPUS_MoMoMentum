"""Kiểm tĩnh db/migrations/0055_runout_date_shown.sql (CHƯA chạy trên AWS): bộ tách thật của migrator, viết lại được, không tham
số tên; `app_get_forecast_summaries` giữ chữ ký, giữ mọi cột của 0008 theo đúng thứ tự và chỉ THÊM cột `runout_date_shown` đọc từ
cờ `params.show_runout_date` của lần chạy (#25), vắng thì đúng."""

from __future__ import annotations

import importlib.util
import re

from conftest import REPO

SQL_0055 = (REPO / "db" / "migrations" / "0055_runout_date_shown.sql").read_text(encoding="utf-8")
SQL_0008 = (REPO / "db" / "migrations" / "0008_wallet_hints.sql").read_text(encoding="utf-8")
_spec = importlib.util.spec_from_file_location(
    "migrator_sqlsplit", REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
STATEMENTS = _mod.split_migration(SQL_0055)


def _create(statements: list[str]) -> str:
    return next(s for s in statements if s.startswith("CREATE FUNCTION app_get_forecast_summaries("))


def _columns(fn: str) -> list[str]:
    """Tên các cột trả về, theo thứ tự trong RETURNS TABLE (...)."""
    body = re.search(r"RETURNS TABLE \((.*?)\)\s*LANGUAGE", fn, re.S)
    assert body, fn[:200]
    return [c.split()[0] for c in body.group(1).replace("\n", " ").split(",") if c.strip()]


def test_tach_duoc_viet_lai_duoc_khong_tham_so():
    assert STATEMENTS and "-- @@" in SQL_0055
    assert all(not _mod.named_params(s) for s in STATEMENTS)
    assert not re.search(r"(?<![:\w]):[A-Za-z_]", SQL_0055)
    assert not re.search(r"ALTER\s+ROLE|PASSWORD\s+'|DROP\s+TABLE|TRUNCATE", SQL_0055, re.I)
    # đổi kiểu trả về nên DROP rồi CREATE (CREATE OR REPLACE không đổi được cột trả về), DROP có IF EXISTS để chạy lại được
    assert STATEMENTS[0] == "DROP FUNCTION IF EXISTS app_get_forecast_summaries(text, text)"
    assert STATEMENTS[1].startswith("CREATE FUNCTION app_get_forecast_summaries(")
    assert STATEMENTS[2:] == [
        "REVOKE ALL ON FUNCTION app_get_forecast_summaries(text, text) FROM PUBLIC",
        "GRANT EXECUTE ON FUNCTION app_get_forecast_summaries(text, text) TO yofina_app",
    ]


def test_ham_giu_cot_cu_va_them_cot_runout_date_shown():
    new, old = _create(STATEMENTS), _create(_mod.split_migration(SQL_0008))
    assert _columns(new) == [*_columns(old), "runout_date_shown"]
    assert "runout_date_shown boolean" in new
    assert (
        "app_get_forecast_summaries(p_user_id text, p_jar_code text DEFAULT NULL)" in new
        and "SECURITY INVOKER" in new
        and "SET search_path = public, pg_temp" in new
        and "PERFORM set_config('app.user_id', p_user_id, true);" in new
        and "LIMIT 40" in new
    )
    # cờ của lần chạy chứa tóm tắt; kết quả cũ hoặc công tắc tắt không có khóa thì vẫn nêu ngày (như trước #25)
    assert "COALESCE((r.params -> 'show_runout_date' ->> s.jar_code)::boolean, true)" in new
    # phần còn lại của thân hàm giữ nguyên 0008 (mực dự báo, lần chạy mới nhất mỗi hũ)
    for part in (
        "min(f.balance_p50_vnd)",
        "f.day < s.payday_date",
        "SELECT DISTINCT ON (s.jar_code)",
        "ORDER BY s.jar_code, r.computed_at DESC, r.id DESC",
    ):
        assert part in new, part


def test_la_migration_moi_nhat_khong_sua_file_cu():
    names = sorted(p.name for p in (REPO / "db" / "migrations").glob("*.sql"))
    i = names.index("0055_runout_date_shown.sql")
    assert names[i - 1] == "0054_ingest_fx.sql"
