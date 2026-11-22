"""Kiểm tĩnh db/migrations/0006_forecast.sql (bảng dự báo): tách bằng bộ tách thật của migrator, RLS FORCE, quyền chỉ thêm và xóa,
ràng buộc phân vị, hàm đọc "mới nhất mỗi hũ". Đã chạy thử trên PostgreSQL cục bộ cùng 0005 (xem test_migration_0005.py)."""

from __future__ import annotations

import importlib.util
import re

import pytest
from conftest import REPO

from yofina_core import wallet

SQL_PATH = REPO / "db" / "migrations" / "0006_forecast.sql"
_spec = importlib.util.spec_from_file_location(
    "migrator_sqlsplit", REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

SQL = SQL_PATH.read_text(encoding="utf-8")
STATEMENTS = _mod.split_migration(SQL)
ALL = "\n".join(STATEMENTS)
TABLES = ["forecast_runs", "forecast_jar_summaries", "forecasts"]


def test_tach_duoc_va_ham_khong_bi_cat():
    assert len(STATEMENTS) > 20 and all(s.strip() for s in STATEMENTS)
    funcs = [s for s in STATEMENTS if s.startswith("CREATE OR REPLACE FUNCTION")]
    assert len(funcs) == 3
    for f in funcs:
        assert f.count("$$") == 2 and f.rstrip().endswith("$$")
        assert "SECURITY INVOKER" in f and "SECURITY DEFINER" not in f
        assert "PERFORM set_config('app.user_id', p_user_id, true);" in f
    assert all(not _mod.named_params(s) for s in STATEMENTS)
    assert not re.search(r"(?<![:\w]):[A-Za-z_]", SQL)


def test_viet_lai_duoc():
    for s in STATEMENTS:
        if s.startswith("CREATE TABLE"):
            assert "IF NOT EXISTS" in s.split("(")[0]
        if s.startswith("CREATE INDEX"):
            assert "IF NOT EXISTS" in s.split(" ON ")[0]
        assert not re.search(r"ALTER\s+ROLE|PASSWORD\s+'", s, re.I)


@pytest.mark.parametrize("table", TABLES)
def test_rls_force_policy_va_quyen_chi_them_va_xoa(table):
    expected = "user_id = current_setting('app.user_id', true)"
    assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in STATEMENTS
    assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in STATEMENTS
    policy = next(s for s in STATEMENTS if s.startswith(f"CREATE POLICY user_isolation ON {table}"))
    assert f"USING ({expected})" in policy and f"WITH CHECK ({expected})" in policy
    assert (
        f"GRANT SELECT, INSERT, DELETE ON {table} TO yofina_app" in STATEMENTS
    )  # không UPDATE: lần chạy đã ghi không sửa
    create = next(s for s in STATEMENTS if s.startswith(f"CREATE TABLE IF NOT EXISTS {table} "))
    assert re.search(r"\buser_id\b", create)


def test_bang_con_xoa_theo_lan_chay_va_theo_hu():
    for t in ("forecast_jar_summaries", "forecasts"):
        create = next(s for s in STATEMENTS if s.startswith(f"CREATE TABLE IF NOT EXISTS {t} "))
        assert (
            "FOREIGN KEY (user_id, run_id) REFERENCES forecast_runs (user_id, id) ON DELETE CASCADE"
            in create
        )
        assert (
            "FOREIGN KEY (user_id, jar_code) REFERENCES jars (user_id, code) ON DELETE CASCADE"
            in create
        )


def test_rang_buoc_phan_vi_va_so_du_co_the_am():
    fc = next(s for s in STATEMENTS if s.startswith("CREATE TABLE IF NOT EXISTS forecasts "))
    assert "spend_p10_vnd <= spend_p50_vnd AND spend_p50_vnd <= spend_p90_vnd" in fc
    assert "balance_p10_vnd <= balance_p50_vnd AND balance_p50_vnd <= balance_p90_vnd" in fc
    assert "spend_p10_vnd     numeric(14,0) NOT NULL CHECK (spend_p10_vnd >= 0)" in fc
    for col in ("balance_p10_vnd", "balance_p50_vnd", "balance_p90_vnd"):
        line = next(ln for ln in fc.splitlines() if ln.strip().startswith(col + " "))
        assert "CHECK" not in line  # số dư mô phỏng được phép âm (hụt)
    assert "PRIMARY KEY (run_id, jar_code, day)" in fc


def test_xac_suat_chi_co_khi_show_probability_va_tap_gia_tri_khop_wallet():
    s = next(
        x for x in STATEMENTS if x.startswith("CREATE TABLE IF NOT EXISTS forecast_jar_summaries")
    )
    assert "CHECK (show_probability = (p_shortfall IS NOT NULL))" in s
    assert (
        "p_shortfall            numeric(5,4) CHECK (p_shortfall IS NULL OR p_shortfall BETWEEN 0 AND 1)"
        in s
    )
    assert set(
        re.search(r"status\s+text NOT NULL CHECK \(status IN \((.*?)\)\)", s)
        .group(1)
        .replace("'", "")
        .replace(" ", "")
        .split(",")
    ) == set(wallet.JAR_STATUSES)
    assert set(
        re.findall(
            r"'(\w+)'", re.search(r"confidence_band\s+text NOT NULL CHECK \((.*?)\)\)", s).group(1)
        )
    ) == set(wallet.CONFIDENCE_BANDS)
    assert set(
        re.findall(r"'(\w+)'", re.search(r"series_kind\s+text CHECK \((.*?)\)\)", s).group(1))
    ) == set(wallet.FORECAST_SERIES_KINDS)
    run = next(x for x in STATEMENTS if x.startswith("CREATE TABLE IF NOT EXISTS forecast_runs"))
    assert set(
        re.findall(
            r"'(\w+)'", re.search(r"trigger\s+text NOT NULL CHECK \((.*?)\)\)", run).group(1)
        )
    ) == set(wallet.FORECAST_TRIGGERS)
    assert "horizon_days         smallint NOT NULL CHECK (horizon_days BETWEEN 1 AND 90)" in run


def test_ham_doc_moi_nhat_moi_hu_va_chuoi_90_ngay_va_don_dep():
    names = re.findall(r"CREATE OR REPLACE FUNCTION (\w+)\(", ALL)
    assert names == [
        "app_get_forecast_summaries",
        "app_get_forecast_series",
        "app_prune_forecast_runs",
    ]
    summaries = next(s for s in STATEMENTS if "FUNCTION app_get_forecast_summaries" in s)
    assert (
        "DISTINCT ON (s.jar_code)" in summaries
        and "ORDER BY s.jar_code, r.computed_at DESC, r.id DESC" in summaries
    )
    assert "LIMIT 40" in summaries
    series = next(s for s in STATEMENTS if "FUNCTION app_get_forecast_series" in s)
    assert "LIMIT 90" in series and "ORDER BY f.day" in series
    for n, sig in {
        "app_get_forecast_summaries": "text, text",
        "app_get_forecast_series": "text, text",
        "app_prune_forecast_runs": "text, integer",
    }.items():
        assert f"REVOKE ALL ON FUNCTION {n}({sig}) FROM PUBLIC" in STATEMENTS
        assert f"GRANT EXECUTE ON FUNCTION {n}({sig}) TO yofina_app" in STATEMENTS


def test_khong_luu_moc_nghia_vu_va_luong_trong_bang_du_bao():
    assert "KHÔNG lưu ở đây" in SQL  # ghép lúc đọc từ obligations và lịch lương
    assert not re.search(r"\bobligation_id\b|\bevents\b", ALL)


def test_nguoi_dung_luon_la_ngay_mo_phong_khong_dung_dong_ho_postgres():
    assert not re.search(r"\b(current_date|current_timestamp|localtimestamp)\b", ALL, re.I)
    assert re.findall(r"\bnow\(\)", ALL) == [
        "now()"
    ]  # chỉ DEFAULT now() của computed_at (thời điểm thật), không phải ngày nghiệp vụ
