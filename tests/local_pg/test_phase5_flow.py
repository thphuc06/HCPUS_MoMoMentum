"""SQL mới của phase 5 (migration 0053) trên PostgreSQL thật cục bộ: chưa từng chạy trên Aurora, nên đây là lần đầu câu lệnh chạy thật.

Kiểm bằng ĐÚNG mã của Lambda (repo, service, REST), role `yofina_app`, RLS FORCE:

- hồ sơ hành vi: batch `after_forecast` (bước `behavior`, `nudge_gate`) ghi `behavior_profiles` bằng `ON CONFLICT (user_id, app_date)`
  (tính lại cùng ngày là ghi đè, không thêm dòng), đọc lại qua `app_get_behavior_profile`, CHECK nhất quán `ready`, RLS;
- bản tin của cổng: `ON CONFLICT` trên chỉ mục duy nhất MỘT PHẦN `nudges_system_one_per_day_idx` (tối đa một bản tin của cổng mỗi
  ngày, bản đã hủy không tính), `GET /nudges/today`, `POST /nudges/{id}/feedback` (`app_set_nudge_outcome`, idempotent, người khác 404);
- "Xóa dữ liệu của tôi": `POST /me/delete-data*` -> `app_delete_user_data` (xóa đúng người, mọi bảng có `user_id`, chạy lại vẫn xong,
  ghi `data_deletions`; gọi thẳng hàm cho người khác bị từ chối);
- bảng vận hành: bốn hàm `app_ops_*` qua `OpsService` và `GET /ops/*` (không trả `user_id`, `conversation_id`);
- đặt lại demo xóa `behavior_profiles` (`RESET_DELETES`);
- luồng nạp (F6) gán hũ bằng bộ phân loại phase 4 trên nhãn k-NN thật (`app_find_labeled_exact`, `app_knn_labeled`, pgvector).

Chạy cùng bộ local_pg (lệnh ở docstring của conftest.py): `pytest tests/local_pg/test_phase5_flow.py`.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any

import psycopg
import pytest
from conftest import REPO
from jsonschema import Draft202012Validator
from ledger_fakes import http_event
from pipeline_helpers import make_settings
from referencing import Registry, Resource

for _p in ("pipelines/ingest", "gateway/tools/ingest", "pipelines/classify"):
    if str(REPO / _p) not in sys.path:
        sys.path.insert(0, str(REPO / _p))

from yofina_core.blocks import BehaviorProfileData, ProactiveCardBlock  # noqa: E402
from yofina_core.config import Config  # noqa: E402
from yofina_core.errors import YofinaError  # noqa: E402
from yofina_core.llm import load_settings  # noqa: E402
from yofina_core.memory import MemoryClearResponse  # noqa: E402
from yofina_core.wallet import EMBEDDING_DIMENSIONS  # noqa: E402
from yofina_forecast import batch as batch_mod  # noqa: E402
from yofina_forecast.behavior import BehaviorEngine, BehaviorRepo, run_nudge_gate  # noqa: E402
from yofina_forecast.repo import ForecastRepo  # noqa: E402
from yofina_forecast.runner import Pipeline  # noqa: E402
from yofina_ledger import ops_rest, privacy_rest, proactive  # noqa: E402
from yofina_ledger.ops import OpsRepo, OpsService, OpsSettings  # noqa: E402
from yofina_ledger.privacy_rest import DeletionRepo, PrivacyService, S3Deleter  # noqa: E402
from yofina_ledger.repo import RESET_DELETES  # noqa: E402
from yofina_ledger.rest_api import handle_http  # noqa: E402

MINH, LAN = "sub-minh", "sub-lan"
TODAY = date(2026, 11, 21)  # ngày mô phỏng của đồng hồ cố định (offset -19)
CONTRACTS = REPO / "contracts"
OPENAPI = "https://contracts.yofina.invalid/rest/openapi.yaml"


# =====================================================================================================
# Hạ tầng
# =====================================================================================================
def _registry() -> Registry:
    import yaml
    from referencing.jsonschema import DRAFT202012

    reg = Registry()
    for path in sorted(CONTRACTS.glob("*/*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        reg = reg.with_resource(schema["$id"], Resource.from_contents(schema))
    spec = yaml.safe_load((CONTRACTS / "rest" / "openapi.yaml").read_text(encoding="utf-8"))
    return reg.with_resource(
        OPENAPI, Resource.from_contents(spec, default_specification=DRAFT202012)
    )


REGISTRY = _registry()


def valid_rest(name: str, instance) -> None:
    v = Draft202012Validator({"$ref": f"{OPENAPI}#/components/schemas/{name}"}, registry=REGISTRY)
    errors = sorted(v.iter_errors(instance), key=lambda e: list(e.path))
    assert not errors, [f"{list(e.path)}: {e.message}" for e in errors[:3]]


def valid_tool(ref: str, instance) -> None:
    uri = "https://contracts.yofina.invalid/tools/forecast.results.schema.json"
    v = Draft202012Validator({"$ref": f"{uri}#/$defs/{ref}"}, registry=REGISTRY)
    errors = sorted(v.iter_errors(instance), key=lambda e: list(e.path))
    assert not errors, [f"{list(e.path)}: {e.message}" for e in errors[:3]]


def rest(env, method: str, path: str, sub: str = MINH, body=None, query=None, groups=None):
    out = handle_http(
        http_event(method, path, sub=sub, body=body, query=query, groups=groups, headers={}),
        env.svc,
    )
    return out["statusCode"], json.loads(out["body"])


def pipeline(env) -> Pipeline:
    return Pipeline(
        ForecastRepo(env.db),
        make_settings(n_paths_full=2000, n_paths_fast=1000),
        None,
        clock=env.clock,
    )


def q(env, sql: str, *args) -> list[tuple]:
    with env.master() as m:
        return m.execute(sql, args).fetchall()


@contextmanager
def db_error(caplog, detail: str):
    """Lỗi SQL đi qua `yofina_core.db` thành `YofinaError` không lộ chi tiết; chi tiết thật nằm trong log `data_api_error`."""
    caplog.clear()
    with pytest.raises(YofinaError):
        yield
    assert any(detail in r.getMessage() for r in caplog.records), [
        r.getMessage() for r in caplog.records
    ]


def count(env, table: str, user: str, where: str = "true") -> int:
    return q(env, f"SELECT count(*) FROM {table} WHERE user_id = %s AND {where}", user)[0][0]


def user_tables(env) -> list[str]:
    """Mọi bảng public có cột user_id (cùng cách duyệt của app_delete_user_data), trừ nhật ký xóa."""
    rows = q(
        env,
        "SELECT c.table_name FROM information_schema.columns c JOIN information_schema.tables s "
        "ON s.table_schema = c.table_schema AND s.table_name = c.table_name "
        "WHERE c.table_schema = 'public' AND c.column_name = 'user_id' AND s.table_type = 'BASE TABLE' "
        "AND c.table_name <> 'data_deletions' ORDER BY 1",
    )
    return [r[0] for r in rows]


def snapshot(env, user: str) -> dict[str, int]:
    out = {t: count(env, t, user) for t in user_tables(env)}
    out["users"] = q(env, "SELECT count(*) FROM users WHERE id = %s", user)[0][0]
    return out


@pytest.fixture()
def two(env):
    env.reset(MINH)
    env.reset(LAN)
    return env


def run_phase5_batch(env, user: str = MINH, trigger: str = "reset") -> dict[str, Any]:
    """Batch đêm của một người dùng như Lambda forecast-batch: dự báo rồi `after_forecast` (điểm, đổi hành vi, hồ sơ, cổng)."""
    p = pipeline(env)
    p.run_user(user, trigger=trigger)
    return batch_mod.after_forecast(p, user, trigger)


# =====================================================================================================
# Migration 0053 chạy lại được (quy ước của db/README.md)
# =====================================================================================================
def test_migration_0053_chay_lai_tren_db_da_co_du_lieu_khong_loi_va_khong_nhan_doi(two):
    from conftest import _load

    env = two
    proactive.insert_gate_nudge(
        env.db,
        MINH,
        nudge_id=str(uuid.uuid4()),
        app_date=TODAY,
        decision=_decision(),
        trace_id="9" * 32,
    )
    sqlsplit = _load("sqlsplit", REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py")
    stmts = sqlsplit.split_migration(
        (REPO / "db/migrations/0053_phase5.sql").read_text(encoding="utf-8")
    )
    with env.master() as m:
        with m.transaction():
            for s in stmts:
                m.execute(s)
        names = [
            r[0]
            for r in m.execute(
                "SELECT conname FROM pg_constraint WHERE conrelid = 'public.nudges'::regclass AND contype = 'c' "
                "AND pg_get_constraintdef(oid) LIKE '%fire_on%created_app_date%' ORDER BY 1"
            ).fetchall()
        ]
        idx = m.execute(
            "SELECT count(*) FROM pg_indexes WHERE tablename = 'nudges' AND indexname = 'nudges_system_one_per_day_idx'"
        ).fetchone()[0]
    assert names == ["nudges_fire_on_check"]  # CHECK không tên của 0010 đã bỏ, không sinh bản trùng
    assert idx == 1
    assert count(env, "nudges", MINH, "source = 'system'") == 1


# =====================================================================================================
# Hồ sơ hành vi
# =====================================================================================================
def test_batch_ghi_ho_so_hanh_vi_tinh_lai_cung_ngay_la_ghi_de_va_doc_lai_dung_hop_dong(two):
    env = two
    steps = run_phase5_batch(env)
    assert steps["behavior"]["status"] == "ok", steps
    assert steps["nudge_gate"]["status"] == "ok", steps
    rows = q(
        env,
        "SELECT app_date, ready, source, model, jsonb_array_length(insights), next_step IS NOT NULL, computed_at "
        "FROM behavior_profiles WHERE user_id = %s",
        MINH,
    )
    assert len(rows) == 1
    app_date, ready, source, model, n_insights, has_next, first_at = rows[0]
    assert (
        app_date == TODAY and source == "reset" and model is None
    )  # đặt lại: câu mẫu của mã, không gọi model
    assert ready is True and n_insights >= 1 and has_next, rows  # minh có đủ lịch sử (47 ngày)

    # tính lại CÙNG ngày (chạy tay): ON CONFLICT (user_id, app_date) DO UPDATE, không thêm dòng
    env.clock.now = env.clock.now + timedelta(minutes=5)
    eng = BehaviorEngine(pipeline(env))
    data = eng.compute_and_store(MINH, env.clock.now, trigger="reset")
    BehaviorProfileData.model_validate(data)
    rows2 = q(env, "SELECT source, computed_at FROM behavior_profiles WHERE user_id = %s", MINH)
    assert len(rows2) == 1 and rows2[0][1] > first_at

    # đọc lại qua app_get_behavior_profile (SECURITY INVOKER, đặt app.user_id) và tool: đúng hợp đồng
    res = eng.get(MINH)
    valid_tool("GetBehaviorProfileResult", res)
    assert res["data"]["ready"] is True and res["data"]["app_date"] == TODAY.isoformat()
    assert res["data"]["insights"] == data["insights"]

    # người khác chưa có hồ sơ: ready sai, không thấy hồ sơ của minh (RLS)
    other = eng.get(LAN)
    valid_tool("GetBehaviorProfileResult", other)
    assert other["data"]["ready"] is False and other["data"]["insights"] == []
    assert BehaviorRepo(env.db).profile(LAN, TODAY) is None


def test_loc_ho_so_khong_con_nhan_xet_thi_ready_sai_kem_ly_do(two):
    env = two
    run_phase5_batch(env)
    eng = BehaviorEngine(pipeline(env))
    full = eng.get(MINH)["data"]
    kinds = {i["kind"] for i in full["insights"]}
    one = sorted(kinds)[0]
    kept = eng.get(MINH, insight_kind=one)
    valid_tool("GetBehaviorProfileResult", kept)
    assert kept["data"]["ready"] is True and {i["kind"] for i in kept["data"]["insights"]} == {one}
    missing = next(
        k
        for k in (
            "payday_cycle",
            "weekday_pattern",
            "time_of_day",
            "bnpl_usage",
            "category_trend",
            "spending_cluster",
        )
        if k not in kinds
    )
    none = eng.get(MINH, insight_kind=missing)
    valid_tool("GetBehaviorProfileResult", none)
    assert none["data"]["ready"] is False and none["data"]["insights"] == []
    assert "chưa có nhận xét nào khớp" in none["data"]["headline"]
    assert none["data"]["history_days"] == full["history_days"]
    by_jar = eng.get(MINH, jar="khong_co_hu_nay")
    assert by_jar["data"]["ready"] is False  # hũ không có nhận xét: cùng cách, không phải lỗi


def test_check_behavior_profiles_ready_phai_nhat_quan_va_rls_chan_ghi_ho_nguoi_khac(two, caplog):
    env = two
    base = (
        "INSERT INTO behavior_profiles (user_id, app_date, ready, config_version, history_days, headline, insights, "
        "next_step, source) VALUES (%s, %s, %s, 'v1', 30, 'h', %s::jsonb, %s::jsonb, 'nightly')"
    )
    bad = [
        (True, "[]", None),  # sẵn sàng mà không có nhận xét
        (True, '[{"insight_id": "a"}]', None),  # sẵn sàng mà không có việc cần làm
        (False, '[{"insight_id": "a"}]', None),  # chưa sẵn sàng mà có nhận xét
        (False, "[]", '{"kind": "x"}'),  # chưa sẵn sàng mà có việc cần làm
    ]
    for ready, insights, nxt in bad:
        with pytest.raises(psycopg.errors.CheckViolation), env.master() as m:
            m.execute(base, (MINH, "2026-11-01", ready, insights, nxt))
    with env.master() as m:
        m.execute(base, (MINH, "2026-11-01", False, "[]", None))
        with pytest.raises(psycopg.errors.UniqueViolation):
            m.execute(base, (MINH, "2026-11-01", False, "[]", None))
    # role ứng dụng ghi hộ người khác trong transaction của minh: RLS (WITH CHECK) chặn
    with db_error(caplog, "row-level security"), env.db.transaction(MINH) as tx:
        tx.execute(
            "INSERT INTO behavior_profiles (user_id, app_date, ready, config_version, history_days, headline, source) "
            "VALUES (:u, CAST('2026-11-02' AS date), false, 'v1', 0, 'h', 'nightly')",
            {"u": LAN},
        )


def test_dat_lai_demo_xoa_ho_so_hanh_vi_dung_nguoi(two):
    env = two
    assert "DELETE FROM behavior_profiles WHERE user_id = :uid" in RESET_DELETES
    run_phase5_batch(env, MINH)
    run_phase5_batch(env, LAN)
    assert count(env, "behavior_profiles", MINH) == 1 and count(env, "behavior_profiles", LAN) == 1
    env.reset(MINH)
    assert count(env, "behavior_profiles", MINH) == 0
    assert count(env, "behavior_profiles", LAN) == 1  # người khác nguyên vẹn


# =====================================================================================================
# Bản tin của cổng giá trị
# =====================================================================================================
def _decision(
    kind: str = "review_needed", title: str = "2 giao dịch chờ bạn chọn hũ"
) -> proactive.GateDecision:
    cand = proactive.GateCandidate(
        kind=kind,
        score=1.2,
        title=title,
        body="Tổng 180.000 ₫; trả lời một lần là xong cho hôm nay.",
        value_vnd=180_000,
    )
    return proactive.select_nudge([cand])


def test_toi_da_mot_ban_tin_cua_cong_moi_ngay_on_conflict_tren_chi_muc_mot_phan(two):
    env = two
    d = _decision()
    assert d.chosen is not None
    first = str(uuid.uuid4())
    assert proactive.insert_gate_nudge(
        env.db, MINH, nudge_id=first, app_date=TODAY, decision=d, trace_id="a" * 32
    )
    # lần ghi thứ hai cùng ngày: ON CONFLICT ... DO NOTHING, không lỗi, không thêm dòng
    second = _decision("behavior_insight", "Nhận xét mới về thói quen chi tiêu")
    assert not proactive.insert_gate_nudge(
        env.db, MINH, nudge_id=str(uuid.uuid4()), app_date=TODAY, decision=second, trace_id="b" * 32
    )
    assert count(env, "nudges", MINH, "source = 'system'") == 1
    # người khác cùng ngày, và minh ngày khác: được ghi
    assert proactive.insert_gate_nudge(
        env.db, LAN, nudge_id=str(uuid.uuid4()), app_date=TODAY, decision=d, trace_id="c" * 32
    )
    assert proactive.insert_gate_nudge(
        env.db,
        MINH,
        nudge_id=str(uuid.uuid4()),
        app_date=TODAY + timedelta(days=1),
        decision=d,
        trace_id="d" * 32,
    )
    # bản đã hủy không tính: hủy bản hôm nay thì ghi được bản mới
    with env.master() as m:
        m.execute(
            "UPDATE nudges SET status = 'cancelled', cancelled_at = now() WHERE id = %s", (first,)
        )
    third = str(uuid.uuid4())
    assert proactive.insert_gate_nudge(
        env.db, MINH, nudge_id=third, app_date=TODAY, decision=second, trace_id="e" * 32
    )
    row = BehaviorRepo(env.db).today_nudge(MINH, TODAY)
    assert str(row["id"]) == third and row["kind"] == "behavior_insight"
    # bản tin của cổng phải có tiêu đề, lý do và lý do cổng; fire_on bằng ngày tạo chỉ cho phép với source system
    with pytest.raises(psycopg.errors.CheckViolation), env.master() as m:
        m.execute(
            "INSERT INTO nudges (user_id, kind, fire_on, created_app_date, source) VALUES (%s, 'low_data', %s, %s, 'system')",
            (MINH, "2026-11-25", "2026-11-25"),
        )
    with pytest.raises(psycopg.errors.CheckViolation), env.master() as m:
        m.execute(
            "INSERT INTO nudges (user_id, kind, fire_on, created_app_date, source) VALUES (%s, 'low_data', %s, %s, 'agent')",
            (MINH, "2026-11-25", "2026-11-25"),
        )


def test_cong_cua_batch_khong_chon_lai_trong_ngay(two):
    env = two
    steps = run_phase5_batch(env)
    gate = steps["nudge_gate"]
    assert gate["status"] == "ok", steps
    n = count(env, "nudges", MINH, "source = 'system'")
    assert n == (1 if gate.get("chosen") else 0)
    if not gate.get(
        "chosen"
    ):  # không có ứng viên vượt ngưỡng: ghi một bản tin để kiểm lần chạy lại
        proactive.insert_gate_nudge(
            env.db,
            MINH,
            nudge_id=str(uuid.uuid4()),
            app_date=TODAY,
            decision=_decision(),
            trace_id="f" * 32,
        )
    again = run_nudge_gate(pipeline(env), MINH, env.clock.now)
    assert again == {"status": "ok", "chosen": None, "reason": "already_chosen"}
    assert count(env, "nudges", MINH, "source = 'system'") == 1


def test_rest_ban_tin_hom_nay_va_phan_hoi_idempotent_nguoi_khac_404(two, caplog):
    env = two
    nid = str(uuid.uuid4())
    proactive.insert_gate_nudge(
        env.db, MINH, nudge_id=nid, app_date=TODAY, decision=_decision(), trace_id="a" * 32
    )
    status, body = rest(env, "GET", "/nudges/today")
    assert status == 200, body
    valid_rest("NudgeTodayResponse", body)
    assert body["nudge"]["nudge_id"] == nid and body["nudge"]["value_vnd"] == 180_000
    card = ProactiveCardBlock.model_validate(body["card"])
    assert card.data.nudge_id == nid and card.data.kind == "review_needed"
    assert body["nudge"]["gate"]["rank"] >= 1 and "status" not in body["nudge"]["gate"]
    # người khác không thấy và không phản hồi được bản tin của minh
    status, other = rest(env, "GET", "/nudges/today", LAN)
    assert status == 200 and "nudge" not in other
    status, err = rest(env, "POST", f"/nudges/{nid}/feedback", LAN, body={"outcome": "acted"})
    assert status == 404 and err["error"]["code"] == "NUDGE_NOT_FOUND"
    status, err = rest(env, "POST", f"/nudges/{uuid.uuid4()}/feedback", body={"outcome": "acted"})
    assert status == 404 and err["error"]["code"] == "NUDGE_NOT_FOUND"
    # snoozed hai lần: cùng outcome_at (idempotent), một dòng feedback
    s1 = rest(env, "POST", f"/nudges/{nid}/feedback", body={"outcome": "snoozed"})
    s2 = rest(env, "POST", f"/nudges/{nid}/feedback", body={"outcome": "snoozed"})
    assert s1[0] == 200 and s1 == s2, (s1, s2)
    valid_rest("NudgeFeedbackResponse", s1[1])
    assert (
        count(env, "feedback", MINH, f"block_id = 'proactive_card:{'a' * 32}:review_needed'") == 1
    )
    # đã để sau thì hôm nay không hiện lại thẻ
    assert "nudge" not in rest(env, "GET", "/nudges/today")[1]
    # đổi sang less_like_this: outcome_at mới, vẫn một dòng feedback (cập nhật), thống kê của cổng đếm đúng
    s3 = rest(
        env,
        "POST",
        f"/nudges/{nid}/feedback",
        body={"outcome": "less_like_this", "reason": "Nhắc nhiều quá"},
    )
    assert (
        s3[0] == 200
        and s3[1]["outcome"] == "less_like_this"
        and s3[1]["recorded_at"] >= s1[1]["recorded_at"]
    )
    assert q(env, "SELECT decision, reason FROM feedback WHERE user_id = %s", MINH) == [
        ("rejected", "Nhắc nhiều quá")
    ]
    stats = BehaviorRepo(env.db).nudge_stats(MINH, TODAY - timedelta(days=30))
    assert [(s["kind"], s["shown"], s["less_like_this"], s["snoozed"]) for s in stats] == [
        ("review_needed", 1, 1, 0)
    ]
    # dismissed đổi cả trạng thái dòng
    rest(env, "POST", f"/nudges/{nid}/feedback", body={"outcome": "dismissed"})
    assert q(env, "SELECT status, outcome FROM nudges WHERE id = %s", nid) == [
        ("dismissed", "dismissed")
    ]
    # hàm DB từ chối outcome lạ (REST đã chặn trước, đây là lớp DB)
    with db_error(caplog, "PARAMS_INVALID: outcome"), env.db.transaction(MINH) as tx:
        tx.execute(
            "SELECT * FROM app_set_nudge_outcome(CAST(:u AS text), CAST(:i AS uuid), CAST(:o AS text))",
            {"u": MINH, "i": nid, "o": "liked"},
        )
    # bản tin không phải của cổng (lời nhắc người dùng đặt) không nhận phản hồi
    other_id = str(uuid.uuid4())
    with env.master() as m:
        m.execute(
            "INSERT INTO nudges (id, user_id, kind, fire_on, created_app_date, source) VALUES (%s, %s, 'low_data', %s, %s, 'agent')",
            (other_id, MINH, "2026-11-25", "2026-11-21"),
        )
    status, err = rest(env, "POST", f"/nudges/{other_id}/feedback", body={"outcome": "acted"})
    assert status == 404 and err["error"]["code"] == "NUDGE_NOT_FOUND"


# =====================================================================================================
# Xóa dữ liệu của tôi
# =====================================================================================================
class FakeMemory:
    """Bộ nhớ AgentCore giả (chỉ test): ghi lại người được xóa."""

    def __init__(self) -> None:
        self.cleared: list[str] = []

    def memory_id(self) -> str:
        return "mem-test"

    def clear(self, sub: str) -> MemoryClearResponse:
        self.cleared.append(sub)
        return MemoryClearResponse(deleted_records=2, deleted_events=0, failed=0)


class FakeS3:
    def __init__(self, keys: list[str]) -> None:
        self.keys = list(keys)

    def list_objects_v2(self, **kw):
        return {
            "Contents": [{"Key": k} for k in self.keys if k.startswith(kw["Prefix"])],
            "IsTruncated": False,
        }

    def delete_objects(self, **kw):
        gone = {o["Key"] for o in kw["Delete"]["Objects"]}
        self.keys = [k for k in self.keys if k not in gone]
        return {}


@pytest.fixture()
def privacy(two, monkeypatch):
    env = two
    s3 = FakeS3([f"u/{MINH}/a.png", f"u/{MINH}/b.csv", f"u/{LAN}/c.png"])
    mem = FakeMemory()
    svc = PrivacyService(
        repo=DeletionRepo(env.db),
        confirm=env.svc.confirm,
        memory=mem,  # type: ignore[arg-type]
        s3=S3Deleter("yofina-ingest-test", "u/", client=s3),
        lease_seconds=120,
        now=env.clock,
    )
    monkeypatch.setattr(privacy_rest, "_SERVICE", svc)
    return env, svc, s3, mem


def delete_my_data(env, sub: str = MINH):
    req = {"tool": "delete_my_data", "params": {"scope": "all"}}
    status, issued = rest(env, "POST", "/me/delete-data/confirmations", sub, body=req)
    assert status == 200, issued
    return rest(
        env, "POST", "/me/delete-data", sub, body={**req, "confirm_token": issued["confirm_token"]}
    )


def _fill_minh_and_lan(env) -> None:
    """Dữ liệu ở thêm các bảng phase 4 và 5 cho cả hai người (dự báo, điểm, hồ sơ hành vi, bản tin, bản ghi lượt)."""
    for user in (MINH, LAN):
        run_phase5_batch(env, user)
        proactive.insert_gate_nudge(
            env.db,
            user,
            nudge_id=str(uuid.uuid4()),
            app_date=TODAY + timedelta(days=2),
            decision=_decision(),
            trace_id="a" * 32,
        )
    with env.master() as m:
        for user in (MINH, LAN):
            m.execute(
                "INSERT INTO audit_events (user_id, trace_id, event_type, outcome, intent, conversation_id) "
                "VALUES (%s, %s, 'agent_turn', 'ok', 'lookup', 'conv-1')",
                (user, uuid.uuid4().hex),
            )


def test_xoa_du_lieu_cua_toi_xoa_dung_nguoi_moi_bang_va_ghi_nhat_ky(privacy):
    env, _svc, s3, mem = privacy
    _fill_minh_and_lan(env)
    before_minh, before_lan = snapshot(env, MINH), snapshot(env, LAN)
    for t in (
        "behavior_profiles",
        "nudges",
        "forecast_runs",
        "forecasts",
        "audit_events",
        "transactions",
        "roadmaps",
    ):
        assert before_minh[t] > 0, t
    for t in ("behavior_profiles", "nudges", "forecasts", "audit_events", "transactions"):
        assert before_lan[t] > 0, t

    status, body = delete_my_data(env)
    assert status == 200, body
    valid_rest("DataDeletion", body)
    assert body["status"] == "done"
    assert body["steps"]["s3"] == {"status": "done", "deleted": 2}
    assert body["steps"]["memory"] == {"status": "done", "deleted": 2} and mem.cleared == [MINH]
    # số dòng Aurora đã xóa = tổng các bảng của minh trước khi xóa (users tính 1)
    assert body["steps"]["aurora"] == {"status": "done", "deleted": sum(before_minh.values())}
    after_minh = snapshot(env, MINH)
    assert all(v == 0 for v in after_minh.values()), {k: v for k, v in after_minh.items() if v}
    assert snapshot(env, LAN) == before_lan  # người khác nguyên vẹn
    assert s3.keys == [f"u/{LAN}/c.png"]
    log = q(
        env,
        "SELECT id::text, status, steps, finished_at IS NOT NULL FROM data_deletions WHERE user_id = %s",
        MINH,
    )
    assert len(log) == 1 and log[0][0] == body["deletion_id"] and log[0][1] == "done" and log[0][3]
    assert log[0][2]["aurora"]["deleted"] == sum(before_minh.values())

    # chạy lại (token mới): không còn gì để xóa, vẫn done, thêm một dòng nhật ký
    status, again = delete_my_data(env)
    assert status == 200 and again["status"] == "done", again
    assert (
        again["steps"]["aurora"] == {"status": "done", "deleted": 0}
        and again["steps"]["s3"]["deleted"] == 0
    )
    assert count(env, "data_deletions", MINH) == 2
    assert snapshot(env, LAN) == before_lan
    # đăng nhập lại là tài khoản trắng: đặt lại demo dựng lại được
    env.reset(MINH)
    assert snapshot(env, MINH)["users"] == 1


def test_app_delete_user_data_chi_chay_voi_lan_xoa_dang_chay_cua_chinh_nguoi_do(privacy, caplog):
    env, *_ = privacy
    before_lan = snapshot(env, LAN)
    did = str(uuid.uuid4())
    with env.master() as m:
        m.execute(
            "INSERT INTO data_deletions (id, user_id, steps) VALUES (%s, %s, '{}'::jsonb)",
            (did, MINH),
        )
    sql = "SELECT relname, deleted FROM app_delete_user_data(:u, CAST(:d AS uuid))"
    # lần xóa của minh nhưng gọi cho lan: bị từ chối, không xóa gì
    with db_error(caplog, "không có lần xóa đang chạy"), env.db.transaction(LAN) as tx:
        tx.execute(sql, {"u": LAN, "d": did})
    with (
        db_error(caplog, "không có lần xóa đang chạy"),
        env.db.transaction(MINH) as tx,
    ):  # id không tồn tại
        tx.execute(sql, {"u": MINH, "d": str(uuid.uuid4())})
    assert snapshot(env, LAN) == before_lan and snapshot(env, MINH)["users"] == 1
    # role ứng dụng không xóa được nhật ký
    with db_error(caplog, "permission denied"), env.db.transaction(MINH) as tx:
        tx.execute("DELETE FROM data_deletions WHERE user_id = :u", {"u": MINH})
    # đúng người, đúng lần xóa đang chạy: trả số dòng theo bảng, tổng khớp
    with env.db.transaction(MINH) as tx:
        rows = tx.execute(sql, {"u": MINH, "d": did})
    by_table = {r["relname"]: int(r["deleted"]) for r in rows}
    assert by_table["users"] == 1 and by_table["transactions"] > 0 and by_table["jars"] > 0
    assert "data_deletions" not in by_table
    assert snapshot(env, LAN) == before_lan


# =====================================================================================================
# Bảng vận hành
# =====================================================================================================
T0 = datetime(2026, 12, 9, 10, 0, tzinfo=UTC)


def _turn(
    user: str,
    trace: str,
    at: datetime,
    *,
    intent: str,
    outcome: str,
    ms: int,
    steps: list,
    tokens: dict,
) -> tuple:
    return (
        user, trace, at, intent, outcome, ms,
        json.dumps(steps), json.dumps(tokens),
        json.dumps([{"rule_id": "grounding", "outcome": "pass"}, {"rule_id": "suitability", "outcome": "fail"}]),
        json.dumps([{"source": "ledger", "as_of": "2026-12-09T10:00:00Z"}]),
        json.dumps({"band": "high"}), json.dumps([{"id": "b1", "type": "jar_summary"}]),
    )  # fmt: skip


@pytest.fixture()
def ops(two, monkeypatch):
    env = two
    turns = [
        _turn(MINH, "t1" * 16, T0, intent="what_if", outcome="ok", ms=4000,
              steps=[{"step": "forecast___run_scenario", "ms": 900, "status": "ok"},
                     {"step": "ledger___get_jar_balances", "ms": 50, "status": "error", "code": "DATABASE_UNAVAILABLE"},
                     {"step": "router", "ms": 300}],
              tokens={"input_tokens": 1000, "output_tokens": 200, "model_calls": 3}),
        _turn(MINH, "t2" * 16, T0 + timedelta(hours=1), intent="lookup", outcome="rejected", ms=1000,
              steps=[{"step": "ledger___get_overview", "ms": 100, "status": "denied"}],
              tokens={"input_tokens": 500, "output_tokens": 100, "model_calls": 1}),
        _turn(LAN, "t3" * 16, T0 + timedelta(days=1, hours=2), intent="lookup", outcome="ok", ms=2000,
              steps=[], tokens={"input_tokens": 10, "output_tokens": 5, "model_calls": 1}),
    ]  # fmt: skip
    with env.master() as m:
        # bảng chỉ thêm dùng chung cả phiên test: dọn lượt của lần chạy fixture trước trong cửa sổ này
        m.execute(
            "DELETE FROM audit_events WHERE created_at >= %s AND created_at < %s",
            (T0 - timedelta(days=1), T0 + timedelta(days=3)),
        )
        for t in turns:
            m.execute(
                "INSERT INTO audit_events (user_id, trace_id, event_type, outcome, created_at, intent, duration_ms, step_timings, "
                "token_usage, rules_checked, data_used, confidence, blocks_emitted, conversation_id) VALUES (%s, %s, 'agent_turn', "
                "%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, 'conv-bi-mat')",
                (t[0], t[1], t[4], t[2], t[3], t[5], *t[6:]),
            )
        # sự kiện khác loại không phải bản ghi lượt
        m.execute(
            "INSERT INTO audit_events (user_id, trace_id, event_type, outcome, created_at) VALUES (%s, %s, 'demo_reset', 'ok', %s)",
            (MINH, "t4" * 16, T0),
        )
    settings = OpsSettings.from_config(Config({}), llm_settings=load_settings(Config({}), env={}))
    service = OpsService(OpsRepo(env.db), settings, usage=None, now=env.clock)
    monkeypatch.setitem(ops_rest._CACHE, id(env.svc), service)
    return env, service


RANGE = {"from": "2026-12-09T00:00:00Z", "to": "2026-12-11T00:00:00Z"}


def ref(user: str) -> str:
    return hashlib.sha256(user.encode("utf-8")).hexdigest()[:12]


def test_ops_traces_moi_nguoi_dung_khong_tra_user_id_phan_trang_va_loc(ops):
    env, _ = ops
    status, body = rest(env, "GET", "/ops/traces", query=RANGE, groups="[ops]")
    assert status == 200, body
    valid_rest("OpsTraceListResponse", body)
    assert [t["trace_id"] for t in body["traces"]] == [
        "t3" * 16,
        "t2" * 16,
        "t1" * 16,
    ]  # mới nhất trước, không có demo_reset
    assert [t["user_ref"] for t in body["traces"]] == [ref(LAN), ref(MINH), ref(MINH)]
    text = json.dumps(body, ensure_ascii=False)
    assert (
        MINH not in text and LAN not in text and "conv-bi-mat" not in text and "user_id" not in text
    )
    # trang 1 phần tử rồi trang sau theo cursor
    status, p1 = rest(env, "GET", "/ops/traces", query={**RANGE, "limit": "1"}, groups="[ops]")
    assert status == 200 and len(p1["traces"]) == 1 and p1.get("next_cursor")
    status, p2 = rest(
        env,
        "GET",
        "/ops/traces",
        query={**RANGE, "limit": "1", "cursor": p1["next_cursor"]},
        groups="[ops]",
    )
    assert status == 200 and p2["traces"][0]["trace_id"] == "t2" * 16
    # lọc theo ý định, kết quả, thời lượng tối thiểu
    _, f = rest(
        env,
        "GET",
        "/ops/traces",
        query={**RANGE, "intent": "lookup", "outcome": "ok"},
        groups="[ops]",
    )
    assert [t["trace_id"] for t in f["traces"]] == ["t3" * 16]
    _, f = rest(
        env, "GET", "/ops/traces", query={**RANGE, "min_duration_ms": "3000"}, groups="[ops]"
    )
    assert [t["trace_id"] for t in f["traces"]] == ["t1" * 16]
    # không thuộc nhóm ops: 403 trước khi đọc gì
    status, err = rest(env, "GET", "/ops/traces", query=RANGE)
    assert status == 403 and err["error"]["code"] == "FORBIDDEN"


def test_ops_trace_chi_tiet_va_tong_hop(ops, caplog):
    env, _ = ops
    status, body = rest(env, "GET", f"/ops/traces/{'t1' * 16}", groups="[ops]")
    assert status == 200, body
    valid_rest("OpsTraceDetail", body)
    assert body["user_ref"] == ref(MINH) and body["intent"] == "what_if"
    assert "user_id" not in json.dumps(body) and "conv-bi-mat" not in json.dumps(body)
    assert (
        rest(env, "GET", f"/ops/traces/{'t4' * 16}", groups="[ops]")[0] == 404
    )  # demo_reset không phải bản ghi lượt
    assert rest(env, "GET", "/ops/traces/khong_co", groups="[ops]")[0] == 404

    status, s = rest(env, "GET", "/ops/summary", query=RANGE, groups="[ops]")
    assert status == 200, s
    valid_rest("OpsSummaryResponse", s)
    # cùng số với hàm SQL, đếm tay từ ba lượt đã ghi
    row = OpsRepo(env.db).summary(
        datetime(2026, 12, 9, tzinfo=UTC), datetime(2026, 12, 11, tzinfo=UTC)
    )
    assert (row["turns"], row["turns_rejected"], row["turns_error"]) == (3, 1, 0)
    assert (row["tool_calls"], row["tool_errors"], row["rule_fails"]) == (3, 2, 3)
    assert (row["input_tokens"], row["output_tokens"], row["model_calls"]) == (1510, 305, 5)
    assert row["p50_ms"] == 2000
    by_day = OpsRepo(env.db).model_calls_by_day(
        datetime(2026, 12, 9, tzinfo=UTC), datetime(2026, 12, 11, tzinfo=UTC)
    )
    assert [(r["day"], r["turns"], r["model_calls"]) for r in by_day] == [
        (date(2026, 12, 9), 2, 4),
        (date(2026, 12, 10), 1, 1),
    ]
    # khoảng quá 31 ngày: hàm SQL từ chối (REST đã chặn trước)
    with db_error(caplog, "không quá 31 ngày"):
        OpsRepo(env.db).summary(
            datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 12, 11, tzinfo=UTC)
        )
    # role ứng dụng KHÔNG đọc thẳng được bản ghi lượt của người khác (chỉ qua hàm đã chọn cột)
    with env.db.transaction(MINH) as tx:
        seen = tx.execute(
            "SELECT DISTINCT user_id FROM audit_events WHERE event_type = 'agent_turn'"
        )
    assert [r["user_id"] for r in seen] == [MINH]


# =====================================================================================================
# Luồng nạp (F6) gán hũ bằng nhãn k-NN thật
# =====================================================================================================
def _axis(i: int) -> list[float]:
    vec = [0.0] * EMBEDDING_DIMENSIONS
    vec[i] = 1.0
    return vec


class FakeBedrockWithEmbed:
    """Bedrock giả (chỉ test): `converse` trả kết quả đọc tệp, `invoke_model` trả vector theo từ điển (chuỗi lạ: một trục riêng)."""

    def __init__(self, doc: dict[str, Any], vectors: dict[str, list[float]]) -> None:
        self.doc, self.vectors, self.embedded = doc, vectors, []

    def converse(self, **req: Any) -> dict[str, Any]:
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"toolUse": {"toolUseId": "t", "name": "report", "input": self.doc}}
                    ],
                }
            },
            "usage": {"inputTokens": 1, "outputTokens": 1},
        }

    def invoke_model(self, **req: Any) -> dict[str, Any]:
        texts = json.loads(req["body"])["texts"]
        self.embedded.extend(texts)
        vecs = [self.vectors.get(t, _axis(900 + len(self.embedded) % 100)) for t in texts]
        return {
            "body": io.BytesIO(json.dumps({"embeddings": vecs}).encode()),
            "ResponseMetadata": {"HTTPHeaders": {}},
        }


def test_nap_anh_gan_hu_bang_khop_chinh_xac_va_knn_tren_nhan_cua_chinh_nguoi_dung(two):
    from test_ingest_flow import PNG, Ctx, doc, ids_by_amount, tx_row
    from yofina_ingest.extract import MemoryUsageStore
    from yofina_ingest.worker import Worker, handle_sqs

    from yofina_core.llm import LlmGateway

    env = two
    # nhãn của minh: một chuỗi khớp chính xác (người dùng đã xác nhận) và một chuỗi chỉ gần theo vector; nhãn của lan cùng vector
    with env.master() as m:
        m.execute(
            "DELETE FROM tx_embeddings_labeled WHERE user_id IN (%s, %s)", (MINH, LAN)
        )  # cô lập khỏi nhãn seed
        for user, text, jar, vec in (
            (MINH, "tiem banh mi co ba", "giai_tri", _axis(1)),
            (MINH, "nha sach phuong nam", "giai_tri", _axis(2)),
            (LAN, "cua hang xa la", "di_lai", _axis(3)),
        ):
            m.execute(
                "INSERT INTO tx_embeddings_labeled (user_id, text_norm, jar_code, source, model, embedding) "
                "VALUES (%s, %s, %s, 'user', 'cohere.embed-multilingual-v3', %s::vector)",
                (user, text, jar, "[" + ",".join(str(x) for x in vec) + "]"),
            )
    model_doc = doc(
        tx_row(amount_vnd=31_000, counterparty="Tiệm Bánh Mì Cô Ba", description=None, tx_type="other_expense", jar_code=None),
        tx_row(amount_vnd=32_000, counterparty="Nhà Sách PN Quận 1", description=None, tx_type="other_expense", jar_code=None),
        tx_row(amount_vnd=33_000, counterparty="Cửa Hàng Lạ", description=None, tx_type="other_expense", jar_code=None),
    )  # fmt: skip
    ing = Ctx(env)
    up = ing.upload()
    ing.storage.objects[up["key"]] = PNG
    # chuỗi thứ hai trùng vector của nhãn "nha sach phuong nam" (k-NN), chuỗi thứ ba trùng vector nhãn của LAN (RLS: không được thấy)
    client = FakeBedrockWithEmbed(
        model_doc, {"nha sach pn quan": _axis(2), "cua hang la": _axis(3)}
    )
    gw = LlmGateway(
        load_settings(Config({}), env={}),
        client=client,
        usage=MemoryUsageStore(),
        sleep=lambda _s: None,
    )
    worker = Worker(ing.repo, ing.storage, ing.rt, gateway=gw, clock=env.clock)
    s3_body = {
        "Records": [
            {
                "eventName": "ObjectCreated:Post",
                "s3": {"bucket": {"name": "yofina-ingest-test"}, "object": {"key": up["key"]}},
            }
        ]
    }
    ev = {
        "Records": [
            {
                "messageId": "m",
                "body": json.dumps(s3_body),
                "attributes": {"ApproximateReceiveCount": "1"},
            }
        ]
    }
    assert handle_sqs(ev, worker, max_receive_count=3) == {"batchItemFailures": []}

    job = ing.job(up["job_id"])
    assert job["status"] == "review", job
    rows = ids_by_amount(job)
    # khớp chính xác: không cần nhúng chuỗi đó
    assert "tiem banh mi co ba" not in client.embedded
    assert (
        rows[31_000]["suggested_jar"]["code"] == "giai_tri"
        and rows[31_000]["jar_source"] == "model"
    )
    # k-NN trên nhãn của chính minh (pgvector, app_knn_labeled)
    assert "nha sach pn quan" in client.embedded  # chuỗi đã che PII (bỏ chữ số) trước khi nhúng
    assert (
        rows[32_000]["suggested_jar"]["code"] == "giai_tri"
        and rows[32_000]["jar_source"] == "model"
    )
    # nhãn của lan không lọt sang minh: hàng gần nhất của minh không phải di_lai
    assert rows[33_000].get("suggested_jar", {}).get("code") != "di_lai"
    # dòng nạp chưa vào sổ cái, không ghi embedding giao dịch
    assert count(env, "transactions", MINH, "funding_source = 'external'") == 0
    assert count(env, "tx_embeddings", MINH) == 0
