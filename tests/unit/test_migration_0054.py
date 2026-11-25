"""Kiểm tĩnh db/migrations/0054_ingest_fx.sql (CHƯA chạy trên AWS): bộ tách thật của migrator, viết lại được, không tham số tên, ba
hàm thay thế giữ đúng chữ ký và kiểu trả về của 0050 và chỉ THÊM khóa (fx, error_reason), ràng buộc khớp hợp đồng `IngestFx`."""

from __future__ import annotations

import importlib.util
import re

from conftest import REPO

SQL_0054 = (REPO / "db" / "migrations" / "0054_ingest_fx.sql").read_text(encoding="utf-8")
SQL_0050 = (REPO / "db" / "migrations" / "0050_ingest.sql").read_text(encoding="utf-8")
_spec = importlib.util.spec_from_file_location(
    "migrator_sqlsplit", REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
STATEMENTS = _mod.split_migration(SQL_0054)
FUNCS = {
    re.search(r"FUNCTION (\w+)\(", s).group(1): s
    for s in STATEMENTS
    if s.startswith("CREATE OR REPLACE FUNCTION")
}


def _old(name: str) -> str:
    return next(
        s
        for s in _mod.split_migration(SQL_0050)
        if s.startswith("CREATE OR REPLACE FUNCTION") and f"FUNCTION {name}(" in s
    )


def _head(fn: str) -> str:
    """Chữ ký và kiểu trả về (phần trước `AS $$`)."""
    return " ".join(fn.split("AS $$")[0].split())


def test_tach_duoc_viet_lai_duoc_khong_tham_so():
    assert STATEMENTS and "-- @@" in SQL_0054
    assert all(not _mod.named_params(s) for s in STATEMENTS)
    assert not re.search(r"(?<![:\w]):[A-Za-z_]", SQL_0054)
    assert not re.search(
        r"ALTER\s+ROLE|PASSWORD\s+'|DROP\s+TABLE|TRUNCATE|DROP\s+FUNCTION", SQL_0054, re.I
    )
    for s in STATEMENTS:
        if "ADD COLUMN" in s:
            assert "ADD COLUMN IF NOT EXISTS" in s
        if " ADD CONSTRAINT " in s:
            name = re.search(r"ADD CONSTRAINT (\w+)", s).group(1)
            assert any(x.endswith(f"DROP CONSTRAINT IF EXISTS {name}") for x in STATEMENTS), name


def test_ba_ham_thay_the_giu_chu_ky_va_chi_them_khoa():
    assert set(FUNCS) == {"app_update_ingest_job", "app_insert_ingest_rows", "app_get_ingest_job"}
    for name, fn in FUNCS.items():
        assert _head(fn) == _head(_old(name)), name
        assert (
            fn.count("$$") == 2
            and "SECURITY INVOKER" in fn
            and "SET search_path = public, pg_temp" in fn
        )
        assert "set_config('app.user_id', p_user_id, true)" in fn
    assert (
        "error_reason    = coalesce(v_patch ->> 'error_reason', j.error_reason)"
        in FUNCS["app_update_ingest_job"]
    )
    assert (
        "CASE WHEN jsonb_typeof(e -> 'fx') = 'object' THEN e -> 'fx' END"
        in FUNCS["app_insert_ingest_rows"]
    )
    get = FUNCS["app_get_ingest_job"]
    assert "'error_reason', j.error_reason" in get and "'fx', r.fx" in get
    assert "LIMIT LEAST(GREATEST(coalesce(p_row_limit, 200), 1), 500)" in get
    # mọi khóa cũ của payload vẫn còn
    for key in re.findall(r"'(\w+)', [jr]\.", _old("app_get_ingest_job")):
        assert f"'{key}'," in get, key


def test_rang_buoc_so_tien_va_fx_khop_hop_dong():
    assert "ALTER TABLE ingest_rows ALTER COLUMN amount_vnd DROP NOT NULL" in STATEMENTS
    amount = next(s for s in STATEMENTS if "ADD CONSTRAINT ingest_rows_amount_check" in s)
    assert "amount_vnd IS NOT NULL OR (fx ->> 'status') = 'rate_unavailable'" in amount
    assert "review_status <> 'approved' OR amount_vnd IS NOT NULL" in amount
    check = next(s for s in STATEMENTS if "ADD CONSTRAINT ingest_rows_fx_check" in s)
    for part in (
        "'^[A-Z]{3}$'",
        "<> 'VND'",
        "('converted', 'rate_unavailable')",
        "'^[0-9]{1,12}([.][0-9]{1,4})?$'",
    ):
        assert part in check, part


def test_khong_sua_migration_cu():
    names = sorted(p.name for p in (REPO / "db" / "migrations").glob("*.sql"))
    i = names.index("0054_ingest_fx.sql")  # 0055 trở đi (có test riêng) đứng sau
    assert names[i - 1] == "0053_phase5.sql"
