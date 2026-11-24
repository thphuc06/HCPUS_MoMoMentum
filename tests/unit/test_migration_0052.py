"""Kiểm tĩnh db/migrations/0052_resilience_roadmap_classify.sql (phase 4): bộ tách thật của migrator, extension vector, RLS FORCE và quyền của
bảy bảng mới (và bảng `review_asks`), cột `vector(1024)`, chỉ mục HNSW cosine, hàm SECURITY INVOKER tự đặt app.user_id và có LIMIT, tập giá
trị khớp hằng số trong `yofina_core.wallet`, CHECK ý định của audit_events đã nới, không sửa migration cũ.
Chạy thật trên PostgreSQL cục bộ ở tests/local_pg/test_phase4_schema.py."""

from __future__ import annotations

import importlib.util
import re
import subprocess

import pytest
from conftest import REPO

from yofina_core import wallet

SQL_PATH = REPO / "db" / "migrations" / "0052_resilience_roadmap_classify.sql"
_spec = importlib.util.spec_from_file_location(
    "migrator_sqlsplit", REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

SQL = SQL_PATH.read_text(encoding="utf-8")
STATEMENTS = _mod.split_migration(SQL)
FUNCS = [s for s in STATEMENTS if s.startswith("CREATE OR REPLACE FUNCTION")]
TABLES = (
    "resilience_scores",
    "roadmaps",
    "roadmap_jobs",
    "behavior_flags",
    "tx_embeddings",
    "tx_embeddings_labeled",
    "review_asks",
)
SIGNATURES = {
    "app_get_resilience_score": "text, date",
    "app_get_roadmap": "text, integer, text",
    "app_list_roadmap_versions": "text, integer",
    "app_save_roadmap": "text, text, text, jsonb, uuid, integer, text, date, jsonb, text, text, text",
    "app_decide_roadmap_version": "text, integer, text",
    "app_set_roadmap_step_state": "text, integer, text, text, boolean",
    "app_get_roadmap_job": "text, uuid",
    "app_get_review_list": "text, text, integer",
    "app_get_review_ask": "text, date",
    "app_list_behavior_flags": "text, text, integer",
    "app_knn_labeled": "text, text, integer",
    "app_find_labeled_exact": "text, text",
}


def sql_set(statement: str, column: str) -> tuple[str, ...]:
    m = re.search(rf"{column}\s+IN\s*\(([^)]*)\)", statement)
    assert m, f"không thấy CHECK IN của {column}"
    return tuple(re.findall(r"'([^']*)'", m.group(1)))


def create_table(name: str) -> str:
    return next(s for s in STATEMENTS if s.startswith(f"CREATE TABLE IF NOT EXISTS {name} "))


def func(name: str) -> str:
    return next(f for f in FUNCS if f"FUNCTION {name}(" in f)


def test_tach_duoc_khong_tham_so_ten_khong_hai_cham_dinh_chu():
    assert len(STATEMENTS) > 80 and all(s.strip() for s in STATEMENTS)
    assert "-- @@" in SQL
    assert len(FUNCS) == len(SIGNATURES) == 12
    for f in FUNCS:
        assert f.count("$$") == 2 and f.rstrip().endswith("$$"), f[:60]
        assert "SECURITY INVOKER" in f and "SECURITY DEFINER" not in f
        assert "PERFORM set_config('app.user_id', p_user_id, true);" in f
        assert "SET search_path = public, pg_temp" in f
    assert all(not _mod.named_params(s) for s in STATEMENTS)
    assert not re.search(r"(?<![:\w]):[A-Za-z_]", SQL)
    assert not re.search(r"ALTER\s+ROLE|PASSWORD\s+'|DROP\s+TABLE|TRUNCATE", SQL, re.I)


def test_viet_lai_duoc():
    assert STATEMENTS[0] == "CREATE EXTENSION IF NOT EXISTS vector"
    for s in STATEMENTS:
        if s.startswith("CREATE TABLE"):
            assert "IF NOT EXISTS" in s.split("(")[0]
        if s.startswith(("CREATE INDEX", "CREATE UNIQUE INDEX")):
            assert "IF NOT EXISTS" in s.split(" ON ")[0]
        if s.startswith("ALTER TABLE") and "ADD COLUMN" in s:
            assert "IF NOT EXISTS" in s
        if s.startswith("ALTER TABLE audit_events DROP CONSTRAINT"):
            assert "IF EXISTS" in s


@pytest.mark.parametrize("table", TABLES)
def test_rls_force_policy_va_khoa_ngoai_cascade(table):
    expected = "user_id = current_setting('app.user_id', true)"
    assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in STATEMENTS
    assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in STATEMENTS
    policy = next(s for s in STATEMENTS if s.startswith(f"CREATE POLICY user_isolation ON {table}"))
    assert f"USING ({expected})" in policy and f"WITH CHECK ({expected})" in policy
    assert f"DROP POLICY IF EXISTS user_isolation ON {table}" in STATEMENTS
    assert re.search(r"user_id\s+text NOT NULL REFERENCES users \(id\) ON DELETE CASCADE", create_table(table))


def test_quyen_cua_yofina_app_toi_thieu_va_noi_dung_lo_trinh_bat_bien():
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON resilience_scores TO yofina_app" in STATEMENTS
    assert "GRANT SELECT, INSERT, DELETE ON roadmaps TO yofina_app" in STATEMENTS
    assert "GRANT UPDATE (status, step_states, updated_at) ON roadmaps TO yofina_app" in STATEMENTS  # plan không sửa được
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON roadmap_jobs TO yofina_app" in STATEMENTS
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON behavior_flags TO yofina_app" in STATEMENTS
    assert "GRANT SELECT, INSERT, DELETE ON tx_embeddings TO yofina_app" in STATEMENTS
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON tx_embeddings_labeled TO yofina_app" in STATEMENTS
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON review_asks TO yofina_app" in STATEMENTS
    assert not any("audit_events" in s and s.startswith("GRANT") for s in STATEMENTS)
    assert not any(re.search(r"GRANT\s+(ALL|UPDATE)\s+ON\s+roadmaps", s) for s in STATEMENTS)


def test_embedding_la_vector_1024_khop_vai_tro_embedding_va_chi_muc_hnsw_cosine():
    assert wallet.EMBEDDING_DIMENSIONS == 1024
    for t in ("tx_embeddings", "tx_embeddings_labeled"):
        assert re.search(r"embedding\s+vector\(1024\) NOT NULL", create_table(t))
    # không thêm cột embedding vào transactions: Data API trả vector dạng chuỗi, sẽ làm phình mọi SELECT của sổ cái
    assert not any(s.startswith("ALTER TABLE transactions") for s in STATEMENTS)
    idx = next(s for s in STATEMENTS if "tx_embeddings_labeled_hnsw_idx" in s and s.startswith("CREATE INDEX"))
    assert "USING hnsw (embedding vector_cosine_ops)" in idx and "m = 16" in idx
    assert "UNIQUE (user_id, text_norm, jar_code)" in create_table("tx_embeddings_labeled")
    assert not any("vector_l2_ops" in s or "vector_ip_ops" in s for s in STATEMENTS)


def test_tap_gia_tri_khop_hang_so():
    assert sql_set(create_table("resilience_scores"), "band") == wallet.RESILIENCE_BANDS
    assert sql_set(create_table("resilience_scores"), "source") == wallet.RESILIENCE_SOURCES
    weakest = re.search(r"weakest\s+text NOT NULL CHECK \(weakest IN \(([^)]*)\)", create_table("resilience_scores"))
    assert tuple(re.findall(r"'([^']*)'", weakest.group(1))) == wallet.RESILIENCE_COMPONENTS
    roadmaps = create_table("roadmaps")
    assert sql_set(roadmaps, "status") == wallet.ROADMAP_VERSION_STATUSES
    assert sql_set(roadmaps, "reason_code") == wallet.ROADMAP_REASON_CODES
    assert sql_set(roadmaps, "feasibility") == wallet.ROADMAP_FEASIBILITIES
    jobs = create_table("roadmap_jobs")
    assert sql_set(jobs, "status") == wallet.ROADMAP_JOB_STATUSES
    assert sql_set(jobs, "trigger") == wallet.ROADMAP_JOB_TRIGGERS
    assert sql_set(jobs, "stage") == wallet.ROADMAP_JOB_STAGES
    flags = create_table("behavior_flags")
    assert sql_set(flags, "status") == wallet.BEHAVIOR_FLAG_STATUSES
    assert sql_set(flags, "method") == wallet.BEHAVIOR_METHODS
    assert sql_set(flags, "direction") == wallet.BEHAVIOR_DIRECTIONS
    assert sql_set(create_table("tx_embeddings_labeled"), "source") == wallet.LABEL_SOURCES
    assert sql_set(create_table("review_asks"), "status") == wallet.REVIEW_ASK_STATUSES


def test_check_y_dinh_cua_audit_events_nho_hon_bay_thanh_muoi_va_khop_hang_so():
    drop = next(s for s in STATEMENTS if s.startswith("ALTER TABLE audit_events DROP CONSTRAINT"))
    add = next(s for s in STATEMENTS if s.startswith("ALTER TABLE audit_events ADD CONSTRAINT"))
    assert "audit_events_intent_check" in drop and "audit_events_intent_check" in add
    assert sql_set(add, "intent") == wallet.INTENTS_PHASE4 and len(wallet.INTENTS_PHASE4) == 10
    assert wallet.INTENTS_PHASE4[: len(wallet.INTENTS_PHASE3)] == wallet.INTENTS_PHASE3


def test_ma_loi_trong_ham_la_ma_error_code_cua_hop_dong():
    from yofina_core.errors import ErrorCode

    for code in set(re.findall(r"RAISE EXCEPTION '([A-Z_]+):", SQL)):
        assert code in {c.value for c in ErrorCode}, code


def test_lo_trinh_mot_active_mot_proposed_va_phien_ban_duy_nhat():
    roadmaps = re.sub(r"\s+", " ", create_table("roadmaps"))
    assert "UNIQUE (user_id, version)" in roadmaps and "based_on_version < version" in roadmaps
    one_active = next(s for s in STATEMENTS if "roadmaps_one_active_idx" in s)
    one_proposed = next(s for s in STATEMENTS if "roadmaps_one_proposed_idx" in s)
    assert one_active.startswith("CREATE UNIQUE INDEX") and "WHERE status = 'active'" in one_active
    assert one_proposed.startswith("CREATE UNIQUE INDEX") and "WHERE status = 'proposed'" in one_proposed
    live = next(s for s in STATEMENTS if "roadmap_jobs_one_live_idx" in s)
    assert "WHERE status IN ('queued', 'running')" in live
    dedupe = next(s for s in STATEMENTS if "roadmap_jobs_dedupe_idx" in s)
    assert dedupe.startswith("CREATE UNIQUE INDEX") and "WHERE dedupe_key IS NOT NULL" in dedupe
    assert "octet_length(plan::text) <= 50000" in roadmaps  # dưới giới hạn một dòng của Data API
    save = func("app_save_roadmap")
    assert "FOR UPDATE" in save and "ROADMAP_VERSION_CONFLICT" in save  # khóa theo người dùng, kiểm bản gốc
    assert "v_max + 1" in save


def test_ham_doc_theo_nguoi_dung_va_gioi_han():
    assert "LIMIT LEAST(GREATEST(coalesce(p_limit, 20), 1), 50)" in func("app_get_review_list")
    assert "LIMIT LEAST(GREATEST(coalesce(p_limit, 20), 1), 50)" in func("app_list_roadmap_versions")
    assert "LIMIT LEAST(GREATEST(coalesce(p_limit, 20), 1), 50)" in func("app_list_behavior_flags")
    assert "LIMIT LEAST(GREATEST(coalesce(p_k, 5), 1), 20)" in func("app_knn_labeled")
    assert "p_embedding::vector" in func("app_knn_labeled") and "<=>" in func("app_knn_labeled")
    for name in ("app_get_resilience_score", "app_get_roadmap", "app_get_roadmap_job", "app_get_review_ask"):
        assert re.search(r"LIMIT 1;\s*END", func(name)), name
    for name in ("app_get_resilience_score", "app_get_roadmap", "app_get_review_list", "app_knn_labeled", "app_find_labeled_exact"):
        assert "user_id = p_user_id" in func(name), name
    # review: dùng đúng hai chế độ và không gồm dòng chuyển hũ
    review = func("app_get_review_list")
    assert "t.kind <> 'transfer'" in review and "j.system_role = 'unclassified'" in review and "t.needs_review" in review


def test_quyen_ham_chi_cho_yofina_app():
    for name, sig in SIGNATURES.items():
        assert f"REVOKE ALL ON FUNCTION {name}({sig}) FROM PUBLIC" in STATEMENTS
        assert f"GRANT EXECUTE ON FUNCTION {name}({sig}) TO yofina_app" in STATEMENTS


def test_khong_sua_migration_cu():
    out = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", "db/migrations"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    assert not [f for f in out if f != "db/migrations/0052_resilience_roadmap_classify.sql"], out
    names = sorted(p.name for p in (REPO / "db" / "migrations").glob("*.sql"))
    i = names.index("0052_resilience_roadmap_classify.sql")  # phase 5 thêm 0053 sau nó
    assert names[i - 1].startswith("0051") and all(n > names[i] for n in names[i + 1 :])
