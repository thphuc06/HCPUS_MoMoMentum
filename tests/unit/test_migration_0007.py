"""Kiểm tĩnh db/migrations/0007_wallet_ops.sql: tách bằng bộ tách thật của migrator, hàm đọc SECURITY INVOKER tự đặt app.user_id,
quyền chỉ cho yofina_app, viết lại được, ràng buộc trạng thái của đề nghị. Đã chạy thật trên PostgreSQL cục bộ
(tests/local_pg) và trên Aurora (scripts/migrate.py)."""

from __future__ import annotations

import importlib.util
import re

import pytest
from conftest import REPO

SQL_PATH = REPO / "db" / "migrations" / "0007_wallet_ops.sql"
_spec = importlib.util.spec_from_file_location(
    "migrator_sqlsplit", REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

SQL = SQL_PATH.read_text(encoding="utf-8")
STATEMENTS = _mod.split_migration(SQL)
FUNCTIONS = [s for s in STATEMENTS if re.match(r"CREATE (OR REPLACE )?FUNCTION", s)]
NAMES = [
    "app_get_confirm_resolutions",
    "app_get_confirm_resolution",
    "app_get_confirm_block",
    "app_get_jar_state",
    "app_get_transaction",
    "app_get_jar_usage",
    "app_get_review_stats",
    "app_get_overview",
    "app_get_jar_detail",
]


def test_tach_duoc_va_ham_khong_bi_cat():
    assert len(STATEMENTS) > 25 and all(s.strip() for s in STATEMENTS)
    assert len(FUNCTIONS) == len(NAMES)
    for f in FUNCTIONS:
        assert f.count("$$") == 2 and f.rstrip().endswith("$$")
        assert "SECURITY INVOKER" in f and "SECURITY DEFINER" not in f
        assert "PERFORM set_config('app.user_id', p_user_id, true);" in f
    assert all(not _mod.named_params(s) for s in STATEMENTS)
    assert not re.search(r"(?<![:\w]):[A-Za-z_]", SQL)


def test_viet_lai_duoc_va_khong_cham_mat_khau_role():
    for s in STATEMENTS:
        if s.startswith("ALTER TABLE") and "ADD COLUMN" in s:
            assert "IF NOT EXISTS" in s
        if s.startswith("ALTER TABLE") and "ADD CONSTRAINT" in s:
            idx = STATEMENTS.index(s)
            assert (
                STATEMENTS[idx - 1].startswith("ALTER TABLE")
                and "DROP CONSTRAINT IF EXISTS" in STATEMENTS[idx - 1]
            )
        assert not re.search(r"ALTER\s+ROLE|PASSWORD\s+'", s, re.I)
    # hàm đổi chữ ký được DROP rồi tạo lại (CREATE OR REPLACE không đổi được kiểu trả về)
    assert "DROP FUNCTION IF EXISTS app_get_confirm_resolutions(text, text, integer)" in STATEMENTS
    assert "DROP FUNCTION IF EXISTS app_get_confirm_resolution(text, text)" in STATEMENTS


@pytest.mark.parametrize("name", NAMES)
def test_moi_ham_co_revoke_public_va_grant_cho_yofina_app(name):
    sig = next(
        re.search(rf"FUNCTION {name}\(([^)]*)\)", f) for f in FUNCTIONS if f"FUNCTION {name}(" in f
    )
    types = ", ".join(
        p.strip().split()[1] if len(p.split()) > 1 else p.strip() for p in sig.group(1).split(",")
    )
    types = re.sub(r"\s+DEFAULT.*", "", types)
    assert any(
        s.startswith(f"REVOKE ALL ON FUNCTION {name}(") and s.endswith("FROM PUBLIC")
        for s in STATEMENTS
    )
    assert any(
        s.startswith(f"GRANT EXECUTE ON FUNCTION {name}(") and s.endswith("TO yofina_app")
        for s in STATEMENTS
    )
    assert types  # chữ ký đọc được


def test_trang_thai_de_nghi_done_co_receipt_cancelled_thi_khong():
    add = next(s for s in STATEMENTS if "ADD COLUMN IF NOT EXISTS status" in s)
    assert "DEFAULT 'done'" in add and "NOT NULL" in add  # dòng cũ mặc định là đã thực hiện
    assert "ALTER TABLE confirm_resolutions ALTER COLUMN receipt DROP NOT NULL" in STATEMENTS
    check = next(s for s in STATEMENTS if "confirm_resolutions_status_check CHECK" in s)
    assert (
        "status IN ('done', 'cancelled')" in check
        and "(status = 'done') = (receipt IS NOT NULL)" in check
    )
    for name in ("app_get_confirm_resolutions", "app_get_confirm_resolution"):
        body = next(f for f in FUNCTIONS if f"FUNCTION {name}(" in f)
        assert "status text" in body


def test_overview_tinh_ngay_mo_phong_trong_ham_tu_offset():
    f = next(f for f in FUNCTIONS if "FUNCTION app_get_overview(" in f)
    assert "p_now AT TIME ZONE p_tz" in f and "clock_offset_days" in f
    # ba nhóm dữ liệu Tổng quan nằm trong một lệnh gọi: hũ, tóm tắt dự báo, nghĩa vụ sắp đến hạn
    for part in (
        "'jars'",
        "'forecasts'",
        "'obligations_due'",
        "'salary_event'",
        "'recent_transactions'",
        "'review_count'",
    ):
        assert part in f
    assert "LIMIT 5" in f and "LIMIT 40" in f  # mọi truy vấn nhiều dòng có LIMIT
