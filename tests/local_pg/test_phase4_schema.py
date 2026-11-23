"""Migration 0052 (phase 4) trên PostgreSQL thật cục bộ, role `yofina_app` (không phải owner, NOBYPASSRLS): pgvector (tạo extension, ghi và đọc
vector, k-NN theo khoảng cách cosine, chỉ mục HNSW), RLS FORCE của tám bảng (người khác không đọc, không ghi được), phiên bản lộ trình
(nguyên tử, bất biến nội dung), job sinh lại, dấu hiệu đổi hành vi, điểm chống chịu, danh sách "Xem lại" và hỏi gộp, và CHECK ý định
của audit_events đã nới.

Chạy cùng bộ local_pg (lệnh ở docstring của conftest.py). Phiên bản pgvector cục bộ là 0.6.2 (Aurora 0.8.2): chỉ dùng thứ có ở cả hai.
"""

from __future__ import annotations

import json
import uuid

import psycopg
import psycopg.rows
import pytest
from psycopg import errors as pgerr

from yofina_core import wallet

MINH, LAN = "sub-minh", "sub-lan"
APP_DATE = "2026-11-21"
NEW_TABLES = (
    "resilience_scores",
    "roadmaps",
    "roadmap_jobs",
    "behavior_flags",
    "tx_embeddings",
    "tx_embeddings_labeled",
    "review_asks",
)


def vec(*hot: tuple[int, float], dims: int = wallet.EMBEDDING_DIMENSIONS) -> str:
    """Vector dạng chuỗi như Data API nhận và trả: gần như toàn 0, vài chiều có giá trị."""
    values = [0.0] * dims
    for i, v in hot:
        values[i] = v
    return "[" + ",".join(str(v) for v in values) + "]"


def plan(*step_ids: str, phases: int = 1) -> str:
    steps = [{"step_id": s, "kind": "set_aside", "title": s, "reason": "r", "status": "pending"} for s in step_ids]
    return json.dumps(
        {
            "headline": "Lộ trình thử",
            "horizon": {"start_date": APP_DATE, "end_date": "2027-02-21"},
            "goals": [],
            "phases": [{"phase_id": f"p{i + 1}", "title": "G", "steps": steps if i == 0 else []} for i in range(phases)],
            "alternatives": [],
            "basis": {},
        }
    )


@pytest.fixture
def db(env):
    """Hai người dùng sạch (minh, lan) với bảng phase 4 trống; trả đối tượng gọi hàm và truy cập bằng role ứng dụng."""
    env.reset(MINH)
    env.reset(LAN)
    with env.master() as m:
        for t in NEW_TABLES:
            m.execute(f"DELETE FROM {t} WHERE user_id IN (%s, %s)", (MINH, LAN))
    return Db(env)


class Db:
    def __init__(self, env) -> None:
        self.env = env

    def app(self) -> psycopg.Connection:
        return psycopg.connect(self.env.pg["dsn"], autocommit=True)

    def master(self) -> psycopg.Connection:
        return self.env.master()

    def call(self, sql: str, params: tuple = ()) -> list[dict]:
        """Chạy một câu SELECT bằng role ứng dụng (hàm app_* tự đặt app.user_id)."""
        with self.app() as c, c.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def as_user(self, user: str, sql: str, params: tuple = ()) -> list[dict]:
        """Chạy câu lệnh bất kỳ bằng role ứng dụng với app.user_id đặt tay (kiểm RLS và quyền bảng trực tiếp)."""
        with self.app() as c, c.transaction(), c.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute("SELECT set_config('app.user_id', %s, true)", (user,))
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else []

    def save_roadmap(self, user=MINH, *, reason="initial", based_on=None, status="active", steps=("s1", "s2"), flag=None):
        rows = self.call(
            "SELECT * FROM app_save_roadmap(%s, %s, %s, NULL::jsonb, %s::uuid, %s::integer, 'on_track', %s::date, %s::jsonb, 'r1', %s, 'trace1')",
            (user, reason, f"Lý do {reason}", flag, based_on, APP_DATE, plan(*steps), status),
        )
        return rows[0]

    def roadmap(self, user=MINH, version=None, which="active"):
        rows = self.call("SELECT * FROM app_get_roadmap(%s, %s::integer, %s)", (user, version, which))
        return rows[0] if rows else None

    def statuses(self, user=MINH) -> dict[int, str]:
        return {r["version"]: r["status"] for r in self.call("SELECT * FROM app_list_roadmap_versions(%s)", (user,))}


def raises(excs, match: str | None = None):
    return pytest.raises(excs, match=match)


# =====================================================================================
# pgvector
# =====================================================================================
def test_extension_vector_da_tao_va_chi_muc_hnsw_cosine(db):
    with db.master() as m:
        ext = m.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()
        idx = m.execute("SELECT indexdef FROM pg_indexes WHERE indexname = 'tx_embeddings_labeled_hnsw_idx'").fetchone()
    assert ext is not None
    assert idx is not None and "USING hnsw (embedding vector_cosine_ops)" in idx[0]


def test_ghi_va_doc_vector_1024_chieu_dung_so_chieu(db):
    label = (
        "INSERT INTO tx_embeddings_labeled (user_id, text_norm, jar_code, source, model, embedding) "
        "VALUES (%s, %s, %s, 'user', 'cohere.embed-multilingual-v3', %s::vector) RETURNING id"
    )
    rows = db.as_user(MINH, label, (MINH, "highlands coffee", "an_uong", vec((0, 1.0))))
    assert len(rows) == 1
    got = db.as_user(MINH, "SELECT embedding::text AS e, vector_dims(embedding) AS d FROM tx_embeddings_labeled")
    assert got[0]["d"] == 1024 and got[0]["e"].startswith("[1,0,0")  # Data API trả vector dạng chuỗi
    with raises(pgerr.DataException, match="1024"):  # sai số chiều bị từ chối
        db.as_user(MINH, label, (MINH, "sai chieu", "an_uong", "[1,2,3]"))


def test_knn_theo_cosine_gan_nhat_truoc_va_khop_chuoi_chinh_xac(db):
    ins = (
        "INSERT INTO tx_embeddings_labeled (user_id, text_norm, jar_code, source, model, embedding) "
        "VALUES (%s, %s, %s, %s, 'm', %s::vector)"
    )
    db.as_user(MINH, ins, (MINH, "highlands coffee", "an_uong", "user", vec((0, 1.0))))
    db.as_user(MINH, ins, (MINH, "grab bike", "di_lai", "seed", vec((1, 1.0))))
    db.as_user(MINH, ins, (MINH, "cgv cinema", "giai_tri", "user", vec((2, 1.0))))
    near = db.call("SELECT * FROM app_knn_labeled(%s, %s, 2)", (MINH, vec((0, 1.0), (1, 0.2))))
    assert [r["jar_code"] for r in near] == ["an_uong", "di_lai"]  # gần nhất trước, đúng k
    assert near[0]["distance"] < near[1]["distance"] < 1.0 and near[0]["distance"] < 0.05
    assert near[0]["distance"] >= 0  # khoảng cách cosine, độ giống = 1 - distance
    exact = db.call("SELECT * FROM app_find_labeled_exact(%s, 'grab bike')", (MINH,))
    assert [(r["jar_code"], r["source"]) for r in exact] == [("di_lai", "seed")]
    assert db.call("SELECT * FROM app_find_labeled_exact(%s, 'khong co')", (MINH,)) == []
    # nhãn trùng (người dùng, chuỗi, hũ) bị chặn: chọn lại thì cập nhật, không thêm dòng
    with raises(pgerr.UniqueViolation):
        db.as_user(MINH, ins, (MINH, "grab bike", "di_lai", "user", vec((1, 1.0))))


def test_knn_va_nhan_chi_cua_chinh_nguoi_dung_rls(db):
    ins = (
        "INSERT INTO tx_embeddings_labeled (user_id, text_norm, jar_code, source, model, embedding) "
        "VALUES (%s, %s, %s, 'user', 'm', %s::vector)"
    )
    db.as_user(LAN, ins, (LAN, "highlands coffee", "an_uong", vec((0, 1.0))))
    assert db.call("SELECT * FROM app_knn_labeled(%s, %s, 5)", (MINH, vec((0, 1.0)))) == []  # minh không thấy nhãn của lan
    assert len(db.call("SELECT * FROM app_knn_labeled(%s, %s, 5)", (LAN, vec((0, 1.0))))) == 1
    assert db.as_user(MINH, "SELECT 1 FROM tx_embeddings_labeled") == []
    with raises(pgerr.InsufficientPrivilege):  # WITH CHECK: không ghi hộ người khác
        db.as_user(MINH, ins, (LAN, "x", "an_uong", vec((3, 1.0))))
    with db.app() as c:  # chưa đặt app.user_id thì không thấy dòng nào
        assert c.execute("SELECT count(*) FROM tx_embeddings_labeled").fetchone()[0] == 0


def test_tx_embeddings_mot_dong_moi_giao_dich_va_xoa_theo_giao_dich(db):
    with db.master() as m:
        tx = m.execute("SELECT id FROM transactions WHERE user_id = %s AND kind = 'expense' LIMIT 1", (MINH,)).fetchone()[0]
    ins = "INSERT INTO tx_embeddings (transaction_id, user_id, text_norm, model, embedding) VALUES (%s, %s, 'abc', 'm', %s::vector)"
    db.as_user(MINH, ins, (tx, MINH, vec((5, 1.0))))
    with raises(pgerr.UniqueViolation):
        db.as_user(MINH, ins, (tx, MINH, vec((5, 1.0))))
    assert db.as_user(LAN, "SELECT 1 FROM tx_embeddings") == []
    with db.master() as m:
        m.execute("DELETE FROM transactions WHERE id = %s", (tx,))
        assert m.execute("SELECT count(*) FROM tx_embeddings WHERE transaction_id = %s", (tx,)).fetchone()[0] == 0  # CASCADE


# =====================================================================================
# Lộ trình: phiên bản nguyên tử
# =====================================================================================
def test_phien_ban_tang_dan_active_proposed_va_chuyen_trang_thai(db):
    v1 = db.save_roadmap()
    assert (v1["version"], v1["status"]) == (1, "active")
    with raises(psycopg.errors.Error, match="ROADMAP_VERSION_CONFLICT"):  # bản đầu tiên chỉ có một lần
        db.save_roadmap(reason="initial")
    v2 = db.save_roadmap(reason="behavior_changed", based_on=1, status="proposed", flag=str(uuid.uuid4()))
    assert (v2["version"], v2["status"]) == (2, "proposed")
    assert db.statuses() == {1: "active", 2: "proposed"}
    assert db.roadmap()["version"] == 1  # mặc định đọc bản đang dùng
    assert db.roadmap(which="proposed")["version"] == 2
    assert db.roadmap(which="latest")["version"] == 2
    assert db.roadmap(version=2)["status"] == "proposed"
    assert db.roadmap(version=9) is None
    # bản chờ mới thay bản chờ cũ (bỏ bản cũ), bản đang dùng không đổi
    v3 = db.save_roadmap(reason="goal_changed", based_on=1, status="proposed")
    assert v3["version"] == 3
    assert db.statuses() == {1: "active", 2: "discarded", 3: "proposed"}
    with raises(psycopg.errors.Error, match="ROADMAP_VERSION_CONFLICT"):  # bản gốc đã bị bỏ
        db.save_roadmap(reason="goal_changed", based_on=2, status="proposed")
    # "Dùng bản mới": bản chờ thành active, bản active cũ thành superseded; gọi lại không đổi gì
    done = db.call("SELECT * FROM app_decide_roadmap_version(%s, 3, 'adopt')", (MINH,))[0]
    assert done["status"] == "active"
    assert db.call("SELECT * FROM app_decide_roadmap_version(%s, 3, 'adopt')", (MINH,))[0]["status"] == "active"
    assert db.statuses() == {1: "superseded", 2: "discarded", 3: "active"}
    with raises(psycopg.errors.Error, match="ROADMAP_VERSION_CONFLICT"):  # bản đang dùng không "giữ bản cũ" được
        db.call("SELECT * FROM app_decide_roadmap_version(%s, 3, 'keep_previous')", (MINH,))
    with raises(psycopg.errors.Error, match="ROADMAP_NOT_FOUND"):
        db.call("SELECT * FROM app_decide_roadmap_version(%s, 99, 'adopt')", (MINH,))
    with raises(psycopg.errors.Error, match="ROADMAP_INVALID"):
        db.call("SELECT * FROM app_decide_roadmap_version(%s, 3, 'bua')", (MINH,))
    # người dùng sửa một bước: bản mới active ngay, thay bản active cũ và bỏ bản chờ (nếu có)
    db.save_roadmap(reason="behavior_changed", based_on=3, status="proposed")
    v5 = db.save_roadmap(reason="step_edited", based_on=3, status="active")
    assert v5["version"] == 5 and db.statuses() == {1: "superseded", 2: "discarded", 3: "superseded", 4: "discarded", 5: "active"}
    # "Giữ bản cũ" với bản chờ: bản chờ bị bỏ, bản đang dùng giữ nguyên
    p = db.save_roadmap(reason="user_request", based_on=5, status="proposed")
    kept = db.call("SELECT * FROM app_decide_roadmap_version(%s, %s, 'keep_previous')", (MINH, p["version"]))[0]
    assert kept["status"] == "discarded" and db.statuses()[5] == "active"


def test_trang_thai_tung_buoc_ghi_va_xoa_va_chi_tren_ban_con_song(db):
    db.save_roadmap(steps=("s1", "s2"))
    got = db.call("SELECT * FROM app_set_roadmap_step_state(%s, 1, 's1', 'accepted', NULL)", (MINH,))[0]["step_states"]
    assert got["s1"]["status"] == "accepted" and "decided_at" in got["s1"] and "edited" not in got["s1"]
    got = db.call("SELECT * FROM app_set_roadmap_step_state(%s, 1, 's2', 'rejected', true)", (MINH,))[0]["step_states"]
    assert got["s2"]["status"] == "rejected" and got["s2"]["edited"] is True
    got = db.call("SELECT * FROM app_set_roadmap_step_state(%s, 1, 's1', 'pending', NULL)", (MINH,))[0]["step_states"]
    assert "s1" not in got and "s2" in got  # pending là xóa trạng thái
    row = db.roadmap(version=1)
    assert row["step_states"] == got and row["plan"]["phases"][0]["steps"][0]["status"] == "pending"  # plan không bị đổi
    versions = db.call("SELECT * FROM app_list_roadmap_versions(%s)", (MINH,))
    assert (versions[0]["steps_total"], versions[0]["accepted_count"], versions[0]["rejected_count"]) == (2, 0, 1)
    with raises(psycopg.errors.Error, match="ROADMAP_NOT_FOUND"):
        db.call("SELECT * FROM app_set_roadmap_step_state(%s, 1, 'khong_co', 'accepted', NULL)", (MINH,))
    with raises(psycopg.errors.Error, match="ROADMAP_INVALID"):
        db.call("SELECT * FROM app_set_roadmap_step_state(%s, 1, 's1', 'bua', NULL)", (MINH,))
    db.save_roadmap(reason="step_edited", based_on=1, status="active")
    with raises(psycopg.errors.Error, match="ROADMAP_VERSION_CONFLICT"):  # bản v1 đã bị thay
        db.call("SELECT * FROM app_set_roadmap_step_state(%s, 1, 's1', 'accepted', NULL)", (MINH,))


def test_noi_dung_phien_ban_bat_bien_va_nguoi_khac_khong_dung_duoc(db):
    db.save_roadmap()
    with raises(pgerr.InsufficientPrivilege):  # yofina_app chỉ được UPDATE status, step_states, updated_at
        db.as_user(MINH, "UPDATE roadmaps SET plan = '{}'::jsonb WHERE version = 1")
    with raises(pgerr.InsufficientPrivilege):
        db.as_user(MINH, "UPDATE roadmaps SET version = 7 WHERE version = 1")
    assert db.as_user(MINH, "UPDATE roadmaps SET updated_at = now() WHERE version = 1 RETURNING 1") != []
    assert db.roadmap(LAN) is None and db.call("SELECT * FROM app_list_roadmap_versions(%s)", (LAN,)) == []
    with raises(psycopg.errors.Error, match="ROADMAP_NOT_FOUND"):
        db.call("SELECT * FROM app_decide_roadmap_version(%s, 1, 'adopt')", (LAN,))
    with raises(psycopg.errors.Error, match="ROADMAP_NOT_FOUND"):
        db.call("SELECT * FROM app_set_roadmap_step_state(%s, 1, 's1', 'accepted', NULL)", (LAN,))
    assert db.as_user(LAN, "SELECT 1 FROM roadmaps") == []
    with raises(pgerr.InsufficientPrivilege):
        db.as_user(LAN, "INSERT INTO roadmaps (user_id, version, status, reason_code, reason_text, feasibility, app_date, plan, rules_version) "
                        "VALUES (%s, 5, 'active', 'initial', 'x', 'on_track', %s::date, '{}'::jsonb, 'r')", (MINH, APP_DATE))
    # lan có lộ trình riêng, số phiên bản của hai người độc lập
    assert db.save_roadmap(LAN)["version"] == 1


def test_rang_buoc_cua_bang_roadmaps(db):
    with raises(psycopg.errors.Error, match="ROADMAP_INVALID"):  # bản mới chỉ có thể là active hoặc proposed
        db.save_roadmap(status="superseded")
    ok = db.save_roadmap()
    assert ok["version"] == 1
    with raises(pgerr.UniqueViolation):  # chèn tay hai bản active cho một người dùng
        db.as_user(MINH, "INSERT INTO roadmaps (user_id, version, status, reason_code, reason_text, feasibility, app_date, plan, rules_version) "
                         "VALUES (%s, 2, 'active', 'initial', 'x', 'on_track', %s::date, '{}'::jsonb, 'r')", (MINH, APP_DATE))
    with raises(pgerr.CheckViolation):  # based_on_version phải nhỏ hơn version
        db.as_user(MINH, "INSERT INTO roadmaps (user_id, version, status, reason_code, reason_text, feasibility, app_date, plan, rules_version, based_on_version) "
                         "VALUES (%s, 2, 'proposed', 'user_request', 'x', 'on_track', %s::date, '{}'::jsonb, 'r', 2)", (MINH, APP_DATE))


# =====================================================================================
# Job sinh lại, dấu hiệu đổi hành vi, điểm chống chịu
# =====================================================================================
JOB = "INSERT INTO roadmap_jobs (user_id, trigger, dedupe_key) VALUES (%s, %s, %s) RETURNING id"


def test_roadmap_job_mot_lan_chay_moi_nguoi_dung_khoa_dedupe_va_trang_thai_nhat_quan(db):
    first = db.as_user(MINH, JOB, (MINH, "behavior_changed", "behavior.changed:evt1"))[0]["id"]
    with raises(pgerr.UniqueViolation):  # đang có một lần chạy mở
        db.as_user(MINH, JOB, (MINH, "user_request", None))
    db.as_user(LAN, JOB, (LAN, "user_request", None))  # người khác độc lập
    row = db.call("SELECT * FROM app_get_roadmap_job(%s, %s)", (MINH, first))[0]
    assert (row["status"], row["progress"], row["trigger"]) == ("queued", 0, "behavior_changed")
    assert db.call("SELECT * FROM app_get_roadmap_job(%s, %s)", (LAN, first)) == []  # job của người khác không đọc được
    with raises(pgerr.CheckViolation):  # done phải có roadmap_id, version, finished_at và progress 100
        db.as_user(MINH, "UPDATE roadmap_jobs SET status = 'done' WHERE id = %s", (first,))
    db.as_user(MINH, "UPDATE roadmap_jobs SET status = 'running', stage = 'allocate', progress = 55, started_at = now() WHERE id = %s", (first,))
    assert db.call("SELECT * FROM app_get_roadmap_job(%s)", (MINH,))[0]["stage"] == "allocate"  # mới nhất khi không nêu job_id
    with raises(pgerr.CheckViolation):
        db.as_user(MINH, "UPDATE roadmap_jobs SET status = 'failed', finished_at = now() WHERE id = %s", (first,))  # thiếu mã lỗi
    db.as_user(
        MINH,
        "UPDATE roadmap_jobs SET status = 'done', progress = 100, roadmap_id = gen_random_uuid(), version = 3, finished_at = now() WHERE id = %s",
        (first,),
    )
    # xong rồi thì được chạy lần mới; cùng dedupe_key (sự kiện giao lại) bị chặn
    with raises(pgerr.UniqueViolation):
        db.as_user(MINH, JOB, (MINH, "behavior_changed", "behavior.changed:evt1"))
    assert db.as_user(MINH, JOB, (MINH, "user_request", None))


def test_behavior_flags_rang_buoc_huong_muc_va_mot_dau_hieu_mo_moi_hu(db):
    ins = (
        "INSERT INTO behavior_flags (user_id, jar_code, status, method, direction, old_weekly_vnd, new_weekly_vnd, suspected_app_date{extra}) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s{vals}) RETURNING id"
    )
    suspect = ins.format(extra="", vals="")
    fid = db.as_user(MINH, suspect, (MINH, "an_uong", "suspected", "cusum", "up", 520_000, 810_000, APP_DATE))[0]["id"]
    with raises(pgerr.UniqueViolation):  # một dấu hiệu mở mỗi hũ
        db.as_user(MINH, suspect, (MINH, "an_uong", "suspected", "page_hinkley", "up", 520_000, 900_000, APP_DATE))
    with raises(pgerr.CheckViolation):  # hướng phải khớp mức
        db.as_user(MINH, suspect, (MINH, "di_lai", "suspected", "cusum", "down", 100_000, 200_000, APP_DATE))
    with raises(pgerr.CheckViolation):  # đã xác nhận phải có ngày xác nhận
        db.as_user(MINH, "UPDATE behavior_flags SET status = 'confirmed' WHERE id = %s", (fid,))
    db.as_user(MINH, "UPDATE behavior_flags SET status = 'confirmed', method = 'pelt', confirmed_app_date = %s, weeks_held = 2 WHERE id = %s", (APP_DATE, fid))
    rows = db.call("SELECT * FROM app_list_behavior_flags(%s, 'confirmed', 10)", (MINH,))
    assert [(r["jar_code"], r["method"], r["weeks_held"]) for r in rows] == [("an_uong", "pelt", 2)]
    assert db.call("SELECT * FROM app_list_behavior_flags(%s)", (LAN,)) == []
    with raises(pgerr.ForeignKeyViolation):  # hũ phải của chính người dùng
        db.as_user(MINH, suspect, (MINH, "khong_co_hu", "suspected", "cusum", "up", 1, 2, APP_DATE))


def test_resilience_scores_doc_ban_moi_nhat_kem_diem_lan_truoc_va_rang_buoc(db):
    comps = json.dumps([{"key": k} for k in wallet.RESILIENCE_COMPONENTS])
    ins = (
        "INSERT INTO resilience_scores (user_id, app_date, score, band, weakest, headline, components, basis, config_version, source) "
        "VALUES (%s, %s::date, %s, %s, 'save', 'Điểm', %s::jsonb, '{}'::jsonb, 'v1', %s)"
    )
    db.as_user(MINH, ins, (MINH, "2026-11-20", 58, "fair", comps, "nightly"))
    db.as_user(MINH, ins, (MINH, "2026-11-21", 61, "fair", comps, "reset"))
    latest = db.call("SELECT * FROM app_get_resilience_score(%s)", (MINH,))[0]
    assert (str(latest["app_date"]), latest["score"], latest["previous_score"]) == ("2026-11-21", 61, 58)
    assert latest["components"][0]["key"] == "save" and latest["source"] == "reset"
    older = db.call("SELECT * FROM app_get_resilience_score(%s, '2026-11-20')", (MINH,))[0]
    assert older["score"] == 58 and older["previous_score"] is None
    assert db.call("SELECT * FROM app_get_resilience_score(%s)", (LAN,)) == []
    with raises(pgerr.UniqueViolation):  # một dòng mỗi ngày mô phỏng
        db.as_user(MINH, ins, (MINH, "2026-11-21", 70, "strong", comps, "nightly"))
    with raises(pgerr.CheckViolation):  # đúng bốn thành phần
        db.as_user(MINH, ins, (MINH, "2026-11-22", 70, "strong", json.dumps([{"key": "save"}]), "nightly"))
    with raises(pgerr.CheckViolation):
        db.as_user(MINH, ins, (MINH, "2026-11-23", 101, "strong", comps, "nightly"))


# =====================================================================================
# "Xem lại", hỏi gộp, người nhận, ý định
# =====================================================================================
def test_danh_sach_xem_lai_va_hoi_gop_tach_theo_hu_chua_phan_loai(db):
    base_review = db.call("SELECT * FROM app_get_review_list(%s, 'review', 50)", (MINH,))
    base_ask = db.call("SELECT * FROM app_get_review_list(%s, 'daily_ask', 50)", (MINH,))
    with db.master() as m:
        ids = [
            r[0]
            for r in m.execute(
                "SELECT id FROM transactions WHERE user_id = %s AND kind = 'expense' AND jar_code = 'an_uong' "
                "AND NOT needs_review ORDER BY occurred_at DESC, id DESC LIMIT 3",
                (MINH,),
            ).fetchall()
        ]
        m.execute("UPDATE transactions SET needs_review = true, classified_by = 'embedding', classification_confidence = 0.8 WHERE id = ANY(%s)", (ids[:2],))
        m.execute("UPDATE transactions SET jar_code = 'chua_phan_loai', suggested_jars = ARRAY['an_uong', 'di_lai'] WHERE id = %s", (ids[2],))
    review = db.call("SELECT * FROM app_get_review_list(%s, 'review', 50)", (MINH,))
    ask = db.call("SELECT * FROM app_get_review_list(%s, 'daily_ask', 50)", (MINH,))
    assert len(review) == len(base_review) + 2 and len(ask) == len(base_ask) + 1
    mine = {r["transaction_id"]: r for r in review}
    assert {ids[0], ids[1]} <= set(mine) and ids[2] not in mine
    assert mine[ids[0]]["jar_code"] == "an_uong" and mine[ids[0]]["classified_by"] == "embedding"
    assert float(mine[ids[0]]["classification_confidence"]) == 0.8 and mine[ids[0]]["amount_vnd"] > 0
    asked = next(r for r in ask if r["transaction_id"] == ids[2])
    assert asked["suggested_jars"] == ["an_uong", "di_lai"] and asked["jar_code"] == "chua_phan_loai"
    # tổng là của TOÀN BỘ tập thuộc chế độ, không phải của phần bị cắt bởi LIMIT
    cut = db.call("SELECT * FROM app_get_review_list(%s, 'review', 1)", (MINH,))
    assert len(cut) == 1 and cut[0]["total_count"] == len(review)
    assert int(cut[0]["total_vnd"]) == sum(int(r["amount_vnd"]) for r in review)
    assert not {r["transaction_id"] for r in db.call("SELECT * FROM app_get_review_list(%s, 'review', 50)", (LAN,))} & set(ids)


def test_review_asks_mot_cau_hoi_moi_ngay_va_trang_thai_nhat_quan(db):
    ins = "INSERT INTO review_asks (user_id, ask_date, item_count, pending_total_vnd) VALUES (%s, %s::date, 2, 180000) RETURNING id"
    db.as_user(MINH, ins, (MINH, APP_DATE))
    with raises(pgerr.UniqueViolation):  # hỏi gộp MỘT lần mỗi ngày
        db.as_user(MINH, ins, (MINH, APP_DATE))
    ask = db.call("SELECT * FROM app_get_review_ask(%s, %s::date)", (MINH, APP_DATE))[0]
    assert (ask["status"], ask["item_count"], int(ask["pending_total_vnd"]), ask["resolved_at"]) == ("open", 2, 180000, None)
    assert db.call("SELECT * FROM app_get_review_ask(%s, %s::date)", (LAN, APP_DATE)) == []
    with raises(pgerr.CheckViolation):  # đã để sau thì phải có thời điểm
        db.as_user(MINH, "UPDATE review_asks SET status = 'skipped' WHERE ask_date = %s::date", (APP_DATE,))
    db.as_user(MINH, "UPDATE review_asks SET status = 'skipped', resolved_at = now() WHERE ask_date = %s::date", (APP_DATE,))
    assert db.call("SELECT * FROM app_get_review_ask(%s, %s::date)", (MINH, APP_DATE))[0]["status"] == "skipped"


def test_nguoi_nhan_co_cot_nguong_tu_gan_rieng(db):
    with db.master() as m:
        payee = m.execute("SELECT id, correction_count, auto_min_confidence FROM payees WHERE user_id = %s LIMIT 1", (MINH,)).fetchone()
    assert payee is not None and payee[1] == 0 and payee[2] is None  # mặc định: chưa sửa lần nào, dùng ngưỡng chung
    db.as_user(MINH, "UPDATE payees SET correction_count = correction_count + 1, auto_min_confidence = 0.95 WHERE id = %s", (payee[0],))
    with raises(pgerr.CheckViolation):
        db.as_user(MINH, "UPDATE payees SET auto_min_confidence = 1.5 WHERE id = %s", (payee[0],))
    with raises(pgerr.CheckViolation):
        db.as_user(MINH, "UPDATE payees SET correction_count = -1 WHERE id = %s", (payee[0],))


def test_audit_events_nhan_ba_y_dinh_moi_va_van_tu_choi_y_dinh_la(db):
    ins = "INSERT INTO audit_events (user_id, event_type, outcome, intent) VALUES (%s, 'agent_turn', 'ok', %s)"
    with db.master() as m:
        for intent in wallet.INTENTS:
            m.execute(ins, (MINH, intent))
        with raises(pgerr.CheckViolation):
            m.execute(ins, (MINH, "bua"))
