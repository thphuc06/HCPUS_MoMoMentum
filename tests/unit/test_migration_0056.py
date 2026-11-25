"""Kiểm tĩnh db/migrations/0056_ingest_pii_kinds.sql (CHƯA chạy trên AWS): bộ tách thật của migrator, viết lại được, không tham số
tên; cột `ingest_rows.pii_masked` chỉ nhận các LOẠI PII mà `yofina_core.pii` che (issue #16, cảnh 5), hai hàm thay thế giữ đúng chữ ký
và kiểu trả về của 0054 và chỉ THÊM khóa `pii_masked`."""

from __future__ import annotations

import importlib.util
import json
import re

from conftest import REPO

from yofina_core.pii import ROW_PII_KINDS

SQL_0056 = (REPO / "db" / "migrations" / "0056_ingest_pii_kinds.sql").read_text(encoding="utf-8")
SQL_0054 = (REPO / "db" / "migrations" / "0054_ingest_fx.sql").read_text(encoding="utf-8")
_spec = importlib.util.spec_from_file_location(
    "migrator_sqlsplit", REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
STATEMENTS = _mod.split_migration(SQL_0056)
FUNCS = {
    re.search(r"FUNCTION (\w+)\(", s).group(1): s
    for s in STATEMENTS
    if s.startswith("CREATE OR REPLACE FUNCTION")
}


def _old(name: str) -> str:
    return next(
        s
        for s in _mod.split_migration(SQL_0054)
        if s.startswith("CREATE OR REPLACE FUNCTION") and f"FUNCTION {name}(" in s
    )


def _head(fn: str) -> str:
    """Chữ ký và kiểu trả về (phần trước `AS $$`)."""
    return " ".join(fn.split("AS $$")[0].split())


def _body(fn: str) -> str:
    return " ".join(fn.split("AS $$")[1].split())


def test_tach_duoc_viet_lai_duoc_khong_tham_so():
    assert STATEMENTS and "-- @@" in SQL_0056
    assert all(not _mod.named_params(s) for s in STATEMENTS)
    assert not re.search(r"(?<![:\w]):[A-Za-z_]", SQL_0056)
    assert not re.search(
        r"ALTER\s+ROLE|PASSWORD\s+'|DROP\s+TABLE|TRUNCATE|DROP\s+FUNCTION", SQL_0056, re.I
    )
    for s in STATEMENTS:
        if "ADD COLUMN" in s:
            assert "ADD COLUMN IF NOT EXISTS" in s
        if " ADD CONSTRAINT " in s:
            name = re.search(r"ADD CONSTRAINT (\w+)", s).group(1)
            assert any(x.endswith(f"DROP CONSTRAINT IF EXISTS {name}") for x in STATEMENTS), name


def test_cot_chi_nhan_loai_cua_bo_che_pii():
    assert "ALTER TABLE ingest_rows ADD COLUMN IF NOT EXISTS pii_masked text[]" in STATEMENTS
    check = next(s for s in STATEMENTS if "ADD CONSTRAINT ingest_rows_pii_masked_check" in s)
    assert set(re.findall(r"'(\w+)'", check)) == set(ROW_PII_KINDS)
    assert "pii_masked IS NULL OR" in check and "pii_masked <@ ARRAY[" in check
    # cùng tập loại với hợp đồng khối (contracts/blocks/ingest_review.schema.json)
    schema = json.loads(
        (REPO / "contracts" / "blocks" / "ingest_review.schema.json").read_text(encoding="utf-8")
    )
    prop = schema["$defs"]["IngestRow"]["properties"]["pii_masked"]
    assert prop["items"]["enum"] == list(ROW_PII_KINDS)


def test_hai_ham_thay_the_giu_chu_ky_va_chi_them_khoa():
    assert set(FUNCS) == {"app_insert_ingest_rows", "app_get_ingest_job"}
    for name, fn in FUNCS.items():
        assert _head(fn) == _head(_old(name)), name
        assert (
            fn.count("$$") == 2
            and "SECURITY INVOKER" in fn
            and "SET search_path = public, pg_temp" in fn
        )
        assert "set_config('app.user_id', p_user_id, true)" in fn
    ins = FUNCS["app_insert_ingest_rows"]
    assert "dedupe_key, fx, pii_masked" in ins
    # mảng chuỗi thì thành text[] (phần tử lạ bị CHECK chặn); giá trị khác mảng thì NULL
    assert (
        "CASE WHEN jsonb_typeof(e -> 'pii_masked') = 'array' "
        "THEN ARRAY(SELECT jsonb_array_elements_text(e -> 'pii_masked')) END"
        in " ".join(ins.split())
    )
    # phần còn lại của thân hàm như 0054
    old_ins = _body(_old("app_insert_ingest_rows"))
    for part in (
        "ON CONFLICT (user_id, dedupe_key) DO NOTHING",
        "jsonb_array_length(p_rows) > 500",
    ):
        assert part in old_ins and part in _body(ins), part
    get = FUNCS["app_get_ingest_job"]
    assert "'fx', r.fx, 'pii_masked', r.pii_masked" in " ".join(get.split())
    assert "LIMIT LEAST(GREATEST(coalesce(p_row_limit, 200), 1), 500)" in get
    for key in re.findall(r"'(\w+)', [jr]\.", _old("app_get_ingest_job")):
        assert f"'{key}'," in get, key


def test_la_migration_sau_0055_khong_sua_file_cu():
    names = sorted(p.name for p in (REPO / "db" / "migrations").glob("*.sql"))
    i = names.index("0056_ingest_pii_kinds.sql")
    assert names[i - 1] == "0055_runout_date_shown.sql"
