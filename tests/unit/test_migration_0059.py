"""Kiểm tĩnh db/migrations/0059_activate_onboarding_jar_layout.sql (CHƯA chạy trên AWS; trên nhánh feat/default-six-jars là 0057):
bộ tách thật của migrator, không tham số tên; chỉ đổi DỮ LIỆU danh mục `jar_templates` (không đổi schema); bật đúng bộ ba của
onboarding (Chi hằng ngày 42, Nghĩa vụ 33, Dự phòng 25, tổng 100), tắt mọi hũ khác kể cả bảy hũ của seed; và PHẢI là migration cuối
(lộ trình Bước 7: bước bật bộ ba tách được khỏi phần schema 0057, 0058)."""

from __future__ import annotations

import importlib.util
import re

from conftest import REPO

from yofina_core.wallet import DEFAULT_OBLIGATION_JAR, DEFAULT_SPENDING_JAR, JAR_PURPOSES

MIGRATIONS = REPO / "db" / "migrations"
SQL_0059 = (MIGRATIONS / "0059_activate_onboarding_jar_layout.sql").read_text(encoding="utf-8")
SEED = (REPO / "db" / "seed" / "jar_templates.sql").read_text(encoding="utf-8")
_spec = importlib.util.spec_from_file_location(
    "migrator_sqlsplit", REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
STATEMENTS = _mod.split_migration(SQL_0059)
ONBOARDING = {DEFAULT_SPENDING_JAR: 42, DEFAULT_OBLIGATION_JAR: 33, "du_phong": 25}


def _rows(sql: str) -> dict[str, list[str]]:
    """Các bộ giá trị của câu INSERT theo mã hũ (một dòng một bộ), mỗi giá trị đã bỏ nháy."""
    values = sql.split("VALUES", 1)[1].split("ON CONFLICT", 1)[0]
    out = {}
    for ln in values.splitlines():
        if re.match(r"\s*\('", ln):
            parts = [p.strip("'") for p in re.findall(r"'[^']*'|[A-Za-z0-9_]+", ln)]
            out[parts[0]] = parts
    return out


ROWS = _rows(
    STATEMENTS[1]
)  # code, name, color_key, icon_key, kind, default_split_percent, is_default, sort_order, purpose


def test_tach_duoc_khong_tham_so_chi_doi_du_lieu_danh_muc():
    assert "-- @@" in SQL_0059 and len(STATEMENTS) == 2
    assert all(not _mod.named_params(s) for s in STATEMENTS)
    assert not re.search(r"(?<![:\w]):[A-Za-z_]", SQL_0059)
    code = "\n".join(STATEMENTS)
    assert not re.search(r"\b(?:ALTER|CREATE|DROP|TRUNCATE|DELETE|GRANT|REVOKE)\b", code, re.I)
    assert not re.search(r"\bjars\b", code)  # không đụng hũ của ví đã tạo


def test_thu_tu_tat_bo_cu_roi_ghi_danh_muc_moi():
    off, upsert = STATEMENTS
    assert off.startswith(
        "UPDATE jar_templates SET is_default = false WHERE is_default AND code NOT IN"
    )
    assert set(re.findall(r"'(\w+)'", off)) == set(ONBOARDING)
    assert upsert.startswith(
        "INSERT INTO jar_templates (code, name, color_key, icon_key, kind, default_split_percent, "
        "is_default, sort_order, purpose) VALUES"
    )
    # viết lại được: chạy lại (hoặc danh mục đã có hàng của seed) thì ghi đè đủ cột, kể cả is_default và purpose
    tail = " ".join(upsert.split("ON CONFLICT", 1)[1].split())
    assert tail.startswith("(code) DO UPDATE SET")
    for col in (
        "name",
        "color_key",
        "icon_key",
        "kind",
        "default_split_percent",
        "is_default",
        "sort_order",
        "purpose",
    ):
        assert f"{col} = EXCLUDED.{col}" in tail, col


def test_bat_dung_bo_ba_tong_100():
    defaults = {c: int(r[5]) for c, r in ROWS.items() if r[6] == "true"}
    assert defaults == ONBOARDING and sum(defaults.values()) == 100
    assert {c: ROWS[c][4] for c in ONBOARDING} == {
        DEFAULT_SPENDING_JAR: "spending", DEFAULT_OBLIGATION_JAR: "obligation", "du_phong": "saving",
    }  # fmt: skip
    assert [c for c, _ in sorted(defaults.items(), key=lambda kv: int(ROWS[kv[0]][7]))] == [
        DEFAULT_SPENDING_JAR, DEFAULT_OBLIGATION_JAR, "du_phong",
    ]  # fmt: skip


def test_purpose_chi_o_hu_saving_va_dung_bo_muc_dich():
    legacy = set(_rows(SEED)) - set(ONBOARDING)
    for code, r in ROWS.items():
        kind, purpose = r[4], r[8]
        if kind != "saving" or code in legacy:
            assert purpose == "NULL", (
                code
            )  # hũ không phải saving, và hũ cũ của seed (Du lịch), giữ purpose trống
        else:
            assert purpose in JAR_PURPOSES, code
    # mỗi mục đích có đúng một hũ mẫu, Dự phòng là buffer
    assert sorted(r[8] for r in ROWS.values() if r[8] != "NULL") == sorted(JAR_PURPOSES)
    assert ROWS["du_phong"][8] == "buffer"


def test_tat_moi_hu_cua_seed_ngoai_bo_ba():
    seed = _rows(SEED)
    assert set(seed) <= set(ROWS)  # mọi hũ của seed có hàng ghi đè
    for code in set(seed) - set(ONBOARDING):
        assert ROWS[code][6] == "false", code
    assert "ON CONFLICT (code) DO NOTHING" in SEED  # seed chạy lại không bật lại bộ bảy


def test_la_migration_cuoi():
    names = sorted(p.name for p in MIGRATIONS.glob("*.sql"))
    assert names[-1] == "0059_activate_onboarding_jar_layout.sql"
    assert names[-3:-1] == ["0057_default_six_jars.sql", "0058_sinking_commitments.sql"]
