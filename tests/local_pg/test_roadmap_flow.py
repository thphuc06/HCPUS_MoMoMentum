"""Lộ trình phía ledger (phase 4, gói 2) trên PostgreSQL thật cục bộ: SQL thật (migration 0052), RLS thật, `LedgerService` và `LedgerRepo`
thật, tám REST `/roadmap*` qua `handle_http`, ba tool `planner___*` qua `handle_gateway`, seed persona khi đặt lại demo, `RESET_DELETES`.

Chạy cùng bộ local_pg (lệnh ở docstring của conftest.py), ví dụ: `pytest tests/local_pg/test_roadmap_flow.py`.
"""

from __future__ import annotations

import json
import uuid
from datetime import date

import pytest
from conftest import REPO
from jsonschema import Draft202012Validator
from ledger_fakes import gateway_context, http_event
from referencing import Registry, Resource

from yofina_core.blocks import MAX_VND  # noqa: F401  (cùng trần với hợp đồng)
from yofina_ledger import roadmap_logic as rl
from yofina_ledger.gateway_api import handle_gateway
from yofina_ledger.repo import RESET_DELETES
from yofina_ledger.rest_api import handle_http
from yofina_ledger.roadmap_service import roadmap_ops
from yofina_planner.rules import cached_rules

MINH, LAN = "sub-minh", "sub-lan"
TODAY = date(2026, 11, 21)
CONTRACTS = REPO / "contracts"
OPENAPI = "https://contracts.yofina.invalid/rest/openapi.yaml"


# =====================================================================================================
# Hạ tầng
# =====================================================================================================
def _registry() -> Registry:
    import yaml

    reg = Registry()
    for path in sorted(CONTRACTS.glob("*/*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        reg = reg.with_resource(schema["$id"], Resource.from_contents(schema))
    spec = yaml.safe_load((CONTRACTS / "rest" / "openapi.yaml").read_text(encoding="utf-8"))
    from referencing.jsonschema import DRAFT202012

    return reg.with_resource(
        OPENAPI, Resource.from_contents(spec, default_specification=DRAFT202012)
    )


REGISTRY = _registry()


def valid_rest(name: str, instance) -> None:
    v = Draft202012Validator({"$ref": f"{OPENAPI}#/components/schemas/{name}"}, registry=REGISTRY)
    errors = sorted(v.iter_errors(instance), key=lambda e: list(e.path))
    assert not errors, [f"{list(e.path)}: {e.message}" for e in errors[:3]]


def valid_tool(name: str, instance) -> None:
    uri = "https://contracts.yofina.invalid/tools/planner.results.schema.json"
    v = Draft202012Validator({"$ref": f"{uri}#/$defs/{name}"}, registry=REGISTRY)
    errors = sorted(v.iter_errors(instance), key=lambda e: list(e.path))
    assert not errors, [f"{list(e.path)}: {e.message}" for e in errors[:3]]


def rest(env, method: str, path: str, sub: str = MINH, body=None, query=None):
    out = handle_http(
        http_event(method, path, sub=sub, body=body, query=query, headers={}), env.svc
    )
    return out["statusCode"], json.loads(out["body"])


def tool(env, name: str, user: str = MINH, **args):
    return handle_gateway({"user_id": user, **args}, gateway_context(f"planner___{name}"), env.svc)


def add_forecast(env, user: str = MINH) -> None:
    """Một lần chạy dự báo tối thiểu (để `basis` của lộ trình có nguồn). Ghi bằng role master vì đây là dữ liệu của pipeline."""
    run = str(uuid.uuid4())
    with env.master() as m:
        m.execute(
            "INSERT INTO forecast_runs (id, user_id, model, model_version, computed_at, app_date, horizon_days, "
            "history_days, data_coverage, confidence_label, is_initial_estimate, trigger, n_paths) "
            "VALUES (%s, %s, 'hurdle', 't', %s, '2026-11-21', 90, 47, 0.62, 'medium', false, 'reset', 1000)",
            (run, user, env.clock.now),
        )
        m.execute(
            "INSERT INTO forecast_jar_summaries (run_id, user_id, jar_code, start_balance_vnd, payday_date, "
            "days_to_payday, status, confidence_band, show_probability, series_kind) "
            "VALUES (%s, %s, 'an_uong', 380000, '2026-12-05', 14, 'ok', 'medium', false, 'dense')",
            (run, user),
        )


def count(env, table: str, user: str, where: str = "true") -> int:
    with env.master() as m:
        return m.execute(
            f"SELECT count(*) FROM {table} WHERE user_id = %s AND {where}", (user,)
        ).fetchone()[0]


def statuses(env, user: str = MINH) -> dict[int, str]:
    status, body = rest(env, "GET", "/roadmap/versions", user)
    assert status == 200, body
    return {v["version"]: v["status"] for v in body["versions"]}


def step_status(block: dict, step_id: str) -> str:
    steps = {s["step_id"]: s for p in block["data"]["phases"] for s in p["steps"]}
    return steps[step_id]["status"]


@pytest.fixture
def minh(env):
    env.reset(MINH)
    env.reset(LAN)
    add_forecast(env, MINH)
    return env


def draft(env, **over) -> dict:
    """Bản nháp hợp lệ cho `minh`: một giai đoạn một bước chuyển 100.000 ₫ từ Giải trí sang Ăn uống, mục tiêu lấy từ bản đang dùng."""
    _, block = rest(env, "GET", "/roadmap")
    goals = block["data"]["goals"]
    d = {
        "reason_code": "user_request",
        "based_on_version": 2,
        "feasibility": "on_track",
        "goals": goals,
        "alternatives": [],
        "phases": [
            {
                "phase_id": "giai_doan_moi",
                "title": "Giai đoạn mới",
                "start_date": "2026-11-21",
                "end_date": "2026-12-05",
                "steps": [
                    {
                        "step_id": "bu_them_an_uong",
                        "kind": "set_aside",
                        "title": "Bù 100.000 ₫ cho Ăn uống",
                        "reason": "Hũ Ăn uống sắp cạn trước kỳ lương.",
                        "amount_vnd": 100000,
                        "jar_code": "giai_tri",
                        "to_jar_code": "an_uong",
                        "action": {
                            "tool": "move_between_jars",
                            "params": {
                                "from_jar": "giai_tri",
                                "to_jar": "an_uong",
                                "amount_vnd": 100000,
                            },
                        },
                    }
                ],
            }
        ],
    }
    d.update(over)
    return d


# =====================================================================================================
# Seed persona (N4) và RESET_DELETES (N5)
# =====================================================================================================
def test_dat_lai_minh_ra_v1_superseded_v2_active_v3_proposed(minh):
    env = minh
    assert statuses(env) == {1: "superseded", 2: "active", 3: "proposed"}
    status, versions = rest(env, "GET", "/roadmap/versions")
    valid_rest("RoadmapVersionsResponse", versions)
    assert versions["active_version"] == 2 and versions["proposed_version"] == 3
    assert "current_job" not in versions

    status, v3 = rest(env, "GET", "/roadmap", query={"which": "proposed"})
    assert status == 200
    valid_rest("RoadmapResponse", v3)
    d = v3["data"]
    assert d["version"] == 3 and d["status"] == "proposed" and d["based_on_version"] == 2
    assert d["reason"]["code"] == "behavior_changed"
    assert (
        d["reason"]["text"]
        == "Chi Ăn uống mỗi tuần tăng từ 520.000 ₫ lên 810.000 ₫ và giữ mức đó 2 tuần."
    )
    assert d["reason"]["detail"] == [
        {"label": "Chi Ăn uống mỗi tuần", "before": "520.000 ₫", "after": "810.000 ₫"}
    ]
    # behavior_flag_id trỏ một dòng behavior_flags ĐÃ XÁC NHẬN của chính minh
    with env.master() as m:
        flag = m.execute(
            "SELECT status, jar_code, method, user_id, detail->>'source' FROM behavior_flags WHERE id = %s",
            (d["reason"]["behavior_flag_id"],),
        ).fetchone()
    assert flag == ("confirmed", "an_uong", "pelt", MINH, "persona_seed")
    assert d["counts"] == {"pending": 5, "accepted": 0, "rejected": 0}
    assert d["feasibility"] == "relaxed" and d["alternatives"] == []

    status, v2 = rest(env, "GET", "/roadmap")  # mặc định: bản đang dùng
    d2 = v2["data"]
    assert d2["version"] == 2 and d2["status"] == "active" and d2["based_on_version"] == 1
    assert d2["reason"]["code"] == "step_edited" and d2["feasibility"] == "on_track"
    assert d2["counts"] == {"pending": 2, "accepted": 2, "rejected": 1}
    edited = next(s for p in d2["phases"] for s in p["steps"] if s["step_id"] == "bu_an_uong")
    assert (
        edited["status"] == "accepted"
        and edited["edited"] is True
        and edited["amount_vnd"] == 100000
    )
    assert edited["title"] == "Bù 100.000 ₫ mỗi tuần cho Ăn uống"
    assert edited["action"]["params"]["amount_vnd"] == 100000
    assert step_status(v2, "cat_giai_tri") == "rejected"
    assert step_status(v2, "giu_san_com_van_phong") == "accepted"


def test_muc_tieu_trong_seed_lay_tu_du_lieu_persona(minh):
    from personas import generate

    spec = next(j for j in generate("minh", anchor=TODAY).jars if j.code == "du_lich")
    _, v3 = rest(minh, "GET", "/roadmap", query={"which": "proposed"})
    (goal,) = v3["data"]["goals"]
    assert goal["jar"] == {
        "code": "du_lich",
        "name": spec.name,
        "color_key": spec.color_key,
        "icon_key": spec.icon_key,
    }
    assert goal["target_vnd"] == spec.goal_vnd and goal["target_date"] == spec.goal_date.isoformat()
    assert goal["on_track"] is True and goal["shortfall_vnd"] == 0
    assert goal["projected_date"] <= goal["target_date"]
    # tiền cơm văn phòng của persona đến hạn đúng ngày bước giữ sẵn nó
    ob = minh.repo.list_obligations(MINH, status="active", limit=100)
    com = next(o for o in ob if o["name"] == "Tiền cơm văn phòng")
    step = next(
        s
        for p in v3["data"]["phases"]
        for s in p["steps"]
        if s["step_id"] == "giu_san_com_van_phong"
    )
    assert step["due_date"] == com["due_date"].isoformat()
    assert step["amount_vnd"] == int(com["amount_vnd"])


def test_lo_trinh_seed_hop_le_theo_luat_suitability_tung_buoc(minh):
    ops = roadmap_ops(minh.svc)
    ctx = ops._context(MINH, with_facts=True)
    rules = cached_rules()
    checked_any = False
    for version in (1, 2, 3):
        row = minh.svc.repo and ops.repo.get_roadmap(MINH, version)
        violations, checked = rl.check_steps(row["plan"]["phases"], ctx.facts, rules)
        assert violations == [], (version, violations)
        for _p, st in rl.iter_steps(row["plan"]["phases"]):
            assert st.get("checked_rules", []) == checked[st["step_id"]]
        checked_any |= any(checked.values())
    assert (
        checked_any
    )  # có bước thật sự bị kiểm bởi một luật (obligations_first), không phải toàn bỏ qua


def test_dat_lai_lap_lai_khong_nhan_doi_phien_ban_va_khong_dung_nguoi_khac(minh):
    env = minh
    rest(env, "POST", "/roadmap/versions/3/decision", body={"decision": "adopt"})
    assert statuses(env)[3] == "active"
    env.reset(MINH)  # đặt lại: seed nạp lại từ đầu
    assert statuses(env) == {1: "superseded", 2: "active", 3: "proposed"}
    assert count(env, "roadmaps", MINH) == 3 and count(env, "behavior_flags", MINH) == 1
    assert count(env, "roadmaps", LAN) == 0  # lan không có file seed


def test_dat_lai_chi_xoa_dung_nguoi(minh):
    env = minh
    before = count(env, "roadmaps", MINH)
    env.reset(LAN)
    assert count(env, "roadmaps", MINH) == before


def test_reset_deletes_co_du_bang_moi_cua_0052_dung_thu_tu(minh):
    names = [s.split()[2] for s in RESET_DELETES]
    new = {
        "resilience_scores", "roadmaps", "roadmap_jobs", "behavior_flags", "tx_embeddings",
        "tx_embeddings_labeled", "review_asks",
    }  # fmt: skip
    assert new <= set(names)
    assert names.index("tx_embeddings") < names.index("transactions")
    assert names.index("tx_embeddings_labeled") < names.index("jars")
    assert names.index("behavior_flags") < names.index("jars")


def test_dat_lai_xoa_sach_du_lieu_moi_cua_0052_dung_nguoi(minh):
    env = minh
    vec = "[" + ",".join(["0.5"] * 1024) + "]"
    with env.master() as m:
        for user in (MINH, LAN):
            tx_id = m.execute(
                "SELECT id FROM transactions WHERE user_id = %s LIMIT 1", (user,)
            ).fetchone()[0]
            m.execute(
                "INSERT INTO tx_embeddings (transaction_id, user_id, text_norm, model, embedding) "
                "VALUES (%s, %s, 'abc', 'm', %s::vector) ON CONFLICT DO NOTHING",
                (tx_id, user, vec),
            )
            # nhãn do người dùng xác nhận (`user`): đặt lại xóa mọi nhãn rồi chỉ nạp lại bộ seed của persona (`classify_seed`)
            m.execute(
                "INSERT INTO tx_embeddings_labeled (user_id, text_norm, jar_code, source, model, embedding) "
                "VALUES (%s, 'abc', 'an_uong', 'user', 'm', %s::vector)",
                (user, vec),
            )
            m.execute(
                "INSERT INTO review_asks (user_id, ask_date, item_count) VALUES (%s, '2026-11-21', 1)",
                (user,),
            )
            m.execute(
                "INSERT INTO resilience_scores (user_id, app_date, score, band, weakest, headline, components, "
                "basis, config_version, source) VALUES (%s, '2026-11-21', 50, 'fair', 'save', 'h', "
                "'[{},{},{},{}]'::jsonb, '{}'::jsonb, 'v1', 'reset')",
                (user,),
            )
            m.execute(
                "INSERT INTO roadmap_jobs (user_id, trigger) VALUES (%s, 'user_request') "
                "ON CONFLICT DO NOTHING",
                (user,),
            )
    tables = (
        "tx_embeddings", "tx_embeddings_labeled", "review_asks", "resilience_scores", "roadmap_jobs",
    )  # fmt: skip
    # bảng nhãn còn có nhãn k-NN seed của persona (nạp lại khi đặt lại): chỉ đếm dòng test vừa thêm
    marker = {"tx_embeddings_labeled": "text_norm = 'abc'"}
    for t in tables:
        w = marker.get(t, "true")
        assert count(env, t, MINH, w) == 1 and count(env, t, LAN, w) == 1, t
    env.reset(MINH)
    for t in tables:
        w = marker.get(t, "true")
        assert count(env, t, MINH, w) == 0, t
        assert count(env, t, LAN, w) == 1, t  # người khác nguyên vẹn
    assert count(env, "tx_embeddings_labeled", MINH, "source <> 'seed'") == 0
    assert count(env, "behavior_flags", MINH) == 1  # đúng một dấu hiệu seed, không nhân đôi


# =====================================================================================================
# GET /roadmap, /roadmap/versions, /roadmap/diff, /roadmap/jobs
# =====================================================================================================
def test_get_roadmap_loi_va_rls(minh):
    env = minh
    status, body = rest(env, "GET", "/roadmap", LAN)
    assert status == 404 and body["error"]["code"] == "ROADMAP_NOT_FOUND"
    status, body = rest(
        env, "GET", "/roadmap", LAN, query={"version": "2"}
    )  # phiên bản của người khác
    assert status == 404 and body["error"]["code"] == "ROADMAP_NOT_FOUND"
    status, body = rest(env, "GET", "/roadmap", query={"version": "99"})
    assert status == 404 and body["error"]["code"] == "ROADMAP_NOT_FOUND"
    for bad in ({"version": "0"}, {"version": "x"}, {"which": "oldest"}):
        status, body = rest(env, "GET", "/roadmap", query=bad)
        assert status == 400 and body["error"]["code"] == "PARAMS_INVALID", bad
    status, body = rest(env, "GET", "/roadmap/versions", LAN)
    assert status == 200 and body == {"versions": []}
    valid_rest("RoadmapVersionsResponse", body)
    status, body = rest(env, "GET", "/roadmap/khong_co", MINH)
    assert status == 400 and body["error"]["code"] == "PARAMS_INVALID"


def test_diff_v2_v3_mac_dinh_la_ban_cho_so_voi_ban_goc(minh):
    status, block = rest(minh, "GET", "/roadmap/diff")
    assert status == 200
    valid_rest("RoadmapDiffResponse", block)
    d = block["data"]
    assert (d["from_version"], d["to_version"], d["to_status"], d["can_adopt"]) == (
        2,
        3,
        "proposed",
        True,
    )
    kinds = {c["step_id"]: c for c in d["changes"]}
    assert kinds["bu_an_uong"]["kind"] == "changed"
    assert kinds["bu_an_uong"]["fields"] == [
        {"label": "Số tiền", "before": "100.000 ₫", "after": "150.000 ₫"}
    ]
    assert kinds["danh_cho_du_phong"]["kind"] == "added"
    assert kinds["cat_giai_tri"]["kind"] == "removed"
    assert d["counts"] == {"added": 1, "removed": 1, "changed": 1, "unchanged": 3}
    assert d["headline"] == "Phiên bản 3 khác phiên bản 2 ở 3 bước: thêm 1, bỏ 1, đổi 1."
    assert d["reason"]["code"] == "behavior_changed"
    # chọn tường minh; so ngược chiều (bản cũ là "to") thì không thể dùng
    status, rev = rest(minh, "GET", "/roadmap/diff", query={"from_version": "3", "to_version": "2"})
    assert status == 200 and rev["data"]["can_adopt"] is False
    status, body = rest(
        minh, "GET", "/roadmap/diff", query={"from_version": "2", "to_version": "2"}
    )
    assert status == 400
    status, body = rest(
        minh, "GET", "/roadmap/diff", query={"from_version": "9", "to_version": "2"}
    )
    assert status == 404 and body["error"]["code"] == "ROADMAP_NOT_FOUND"
    # v1 không có bản gốc: không nêu from_version thì 400
    status, body = rest(minh, "GET", "/roadmap/diff", query={"to_version": "1"})
    assert status == 400


# =====================================================================================================
# POST /roadmap/steps/{step_id}/decision
# =====================================================================================================
def test_quyet_dinh_buoc_ghi_trang_thai_feedback_va_audit_va_idempotent(minh):
    env = minh
    body = {"version": 3, "decision": "accepted"}
    audit0 = count(env, "audit_events", MINH, "event_type = 'roadmap_step_decided'")
    status, block = rest(env, "POST", "/roadmap/steps/bu_an_uong/decision", body=body)
    assert status == 200, block
    valid_rest("RoadmapResponse", block)
    assert step_status(block, "bu_an_uong") == "accepted"
    assert block["data"]["counts"] == {"pending": 4, "accepted": 1, "rejected": 0}
    step = next(
        s for p in block["data"]["phases"] for s in p["steps"] if s["step_id"] == "bu_an_uong"
    )
    assert step["decided_at"].endswith("Z")
    fb = count(env, "feedback", MINH, "option_id = 'bu_an_uong' AND decision = 'accepted'")
    audit = count(env, "audit_events", MINH, "event_type = 'roadmap_step_decided'")
    assert fb == 1 and audit == audit0 + 1
    # gửi lại cùng quyết định: không ghi thêm gì
    status, again = rest(env, "POST", "/roadmap/steps/bu_an_uong/decision", body=body)
    assert status == 200 and again["data"] == block["data"]
    assert count(env, "audit_events", MINH, "event_type = 'roadmap_step_decided'") == audit0 + 1
    # từ chối kèm lý do
    status, block = rest(
        env,
        "POST",
        "/roadmap/steps/danh_cho_du_phong/decision",
        body={"version": 3, "decision": "rejected", "reason": "Tháng này tôi cần tiền"},
    )
    assert status == 200 and step_status(block, "danh_cho_du_phong") == "rejected"
    with env.master() as m:
        row = m.execute(
            "SELECT decision, reason, block_id, trace_id FROM feedback WHERE user_id = %s AND option_id = 'danh_cho_du_phong'",
            (MINH,),
        ).fetchone()
    assert row[0] == "rejected" and row[1] == "Tháng này tôi cần tiền"
    assert row[2] == f"roadmap:{row[3]}:v3"
    # hoàn tác về chờ: xóa trạng thái, không có feedback pending
    status, block = rest(
        env,
        "POST",
        "/roadmap/steps/danh_cho_du_phong/decision",
        body={"version": 3, "decision": "pending"},
    )
    assert step_status(block, "danh_cho_du_phong") == "pending"
    # không đổi số dư và không có đường ghi tiền: sổ cái không thêm dòng nào
    assert count(env, "transactions", MINH, "source = 'roadmap'") == 0


def test_quyet_dinh_buoc_loi(minh):
    env = minh
    ok = {"version": 3, "decision": "accepted"}
    status, body = rest(env, "POST", "/roadmap/steps/khong_co/decision", body=ok)
    assert status == 404 and body["error"]["code"] == "ROADMAP_NOT_FOUND"
    status, body = rest(
        env, "POST", "/roadmap/steps/bu_an_uong/decision", body={**ok, "version": 1}
    )
    assert status == 409 and body["error"]["code"] == "ROADMAP_VERSION_CONFLICT"  # v1 đã bị thay
    status, body = rest(
        env, "POST", "/roadmap/steps/bu_an_uong/decision", body={**ok, "version": 99}
    )
    assert status == 404
    status, body = rest(env, "POST", "/roadmap/steps/bu_an_uong/decision", LAN, body=ok)
    assert (
        status == 404 and body["error"]["code"] == "ROADMAP_NOT_FOUND"
    )  # của người khác = không có
    for bad in (
        {"version": 3, "decision": "maybe"},
        {"version": 3},
        {"decision": "accepted"},
        {**ok, "user_id": "sub-lan"},  # danh tính chỉ từ JWT: trường lạ bị từ chối
        {**ok, "reason": ""},
    ):
        status, body = rest(env, "POST", "/roadmap/steps/bu_an_uong/decision", body=bad)
        assert status == 400 and body["error"]["code"] == "PARAMS_INVALID", bad
    status, body = rest(env, "POST", "/roadmap/steps/Bad-Id/decision", body=ok)
    assert status == 400


# =====================================================================================================
# POST /roadmap/steps/{step_id}/edit
# =====================================================================================================
def test_sua_buoc_luu_ban_moi_active_khong_goi_model_giu_trang_thai_buoc_khac(minh):
    env = minh
    audit0 = count(env, "audit_events", MINH, "event_type = 'roadmap_step_edited'")
    status, block = rest(
        env, "POST", "/roadmap/steps/bu_an_uong/edit", body={"version": 2, "amount_vnd": 120000}
    )
    assert status == 200, block
    valid_rest("RoadmapResponse", block)
    d = block["data"]
    assert d["version"] == 4 and d["status"] == "active" and d["based_on_version"] == 2
    assert d["reason"]["code"] == "step_edited"
    assert d["reason"]["text"] == (
        "Bạn đã sửa bước 'Bù 120.000 ₫ mỗi tuần cho Ăn uống' (số tiền 120.000 ₫) và lưu thành phiên bản mới."
    )
    assert d["reason"]["detail"] == [
        {"label": "Số tiền", "before": "100.000 ₫", "after": "120.000 ₫"}
    ]
    step = next(s for p in d["phases"] for s in p["steps"] if s["step_id"] == "bu_an_uong")
    assert step["amount_vnd"] == 120000 and step["title"] == "Bù 120.000 ₫ mỗi tuần cho Ăn uống"
    assert step["status"] == "accepted" and step["edited"] is True
    assert step["action"]["params"]["amount_vnd"] == 120000
    assert step_status(block, "giu_san_com_van_phong") == "accepted"  # bước khác giữ trạng thái
    assert step_status(block, "cat_giai_tri") == "rejected"
    assert d["counts"] == {"pending": 2, "accepted": 2, "rejected": 1}
    # v2 thành superseded, bản chờ v3 bị bỏ
    assert statuses(env) == {1: "superseded", 2: "superseded", 3: "discarded", 4: "active"}
    # feedback accepted lý do edited, audit; số dư không đổi
    with env.master() as m:
        fb = m.execute(
            "SELECT decision, reason FROM feedback WHERE user_id = %s AND option_id = 'bu_an_uong'",
            (MINH,),
        ).fetchone()
    assert fb == ("accepted", "edited")
    assert count(env, "audit_events", MINH, "event_type = 'roadmap_step_edited'") == audit0 + 1
    # bản gốc đã bị thay: sửa tiếp trên v2 thì 409
    status, body = rest(
        env, "POST", "/roadmap/steps/bu_an_uong/edit", body={"version": 2, "amount_vnd": 130000}
    )
    assert status == 409 and body["error"]["code"] == "ROADMAP_VERSION_CONFLICT"


def test_sua_ngay_cua_buoc_va_loi_dau_vao(minh):
    env = minh
    status, block = rest(
        env,
        "POST",
        "/roadmap/steps/nhac_du_lich/edit",
        body={"version": 2, "due_date": "2027-01-10"},
    )
    assert status == 200, block
    step = next(
        s for p in block["data"]["phases"] for s in p["steps"] if s["step_id"] == "nhac_du_lich"
    )
    assert step["due_date"] == "2027-01-10" and step["action"]["params"]["fire_on"] == "2027-01-10"
    for body, code in (
        ({"version": 4}, 400),  # thiếu amount_vnd và due_date
        ({"version": 4, "amount_vnd": 0}, 400),
        ({"version": 4, "amount_vnd": 1.5}, 400),
        ({"version": 4, "due_date": "2026-13-45"}, 400),
        ({"version": 4, "due_date": "2026-11-01"}, 400),  # trước hôm nay
        ({"version": 4, "amount_vnd": 5000}, 400),  # nhac_du_lich không có số tiền
        ({"version": 4, "due_date": "2027-01-10"}, 400),  # trùng giá trị hiện tại
        ({"version": 4, "amount_vnd": 1000, "user_id": "x"}, 400),
    ):
        status, out = rest(env, "POST", "/roadmap/steps/nhac_du_lich/edit", body=body)
        assert status == code and out["error"]["code"] == "PARAMS_INVALID", body
    status, out = rest(
        env, "POST", "/roadmap/steps/khong_co/edit", body={"version": 4, "amount_vnd": 1000}
    )
    assert status == 404
    assert statuses(env)[4] == "active" and 5 not in statuses(env)  # không bản nào bị lưu thêm


def test_sua_buoc_vi_pham_luat_thi_422_va_khong_luu(minh):
    env = minh
    # Hũ Hóa đơn 450.000 ₫ gánh nghĩa vụ thiết yếu trước kỳ lương (tiền điện 375.000 ₫): rút 50.000 ₫ vẫn đủ, rút 200.000 ₫ thì hụt.
    ok = draft(env, based_on_version=2)
    step = ok["phases"][0]["steps"][0]
    step.update(
        jar_code="hoa_don",
        title="Dành 50.000 ₫ cho Ăn uống",
        amount_vnd=50000,
        action={
            "tool": "move_between_jars",
            "params": {"from_jar": "hoa_don", "to_jar": "an_uong", "amount_vnd": 50000},
        },
    )
    saved = tool(env, "save_roadmap", **ok)
    assert saved["status"] == "OK", saved
    version = saved["data"]["version"]
    before = statuses(env)
    status, out = rest(
        env,
        "POST",
        "/roadmap/steps/bu_them_an_uong/edit",
        body={"version": version, "amount_vnd": 200000},
    )
    assert status == 422 and out["error"]["code"] == "ROADMAP_INVALID", out
    assert (
        "obligations_first" in out["error"]["message"]
        and "bu_them_an_uong" in out["error"]["message"]
    )
    assert statuses(env) == before  # không lưu gì


# =====================================================================================================
# POST /roadmap/versions/{version}/decision
# =====================================================================================================
def test_dung_ban_moi_va_giu_ban_cu(minh):
    env = minh
    audit0 = count(env, "audit_events", MINH, "event_type = 'roadmap_version_decided'")
    status, block = rest(env, "POST", "/roadmap/versions/3/decision", body={"decision": "adopt"})
    assert status == 200 and block["data"]["version"] == 3 and block["data"]["status"] == "active"
    valid_rest("RoadmapResponse", block)
    assert statuses(env) == {1: "superseded", 2: "superseded", 3: "active"}
    assert count(env, "audit_events", MINH, "event_type = 'roadmap_version_decided'") == audit0 + 1
    assert (
        count(env, "feedback", MINH, "option_id = 'version_adopt' AND decision = 'accepted'") == 1
    )
    # idempotent
    status, again = rest(env, "POST", "/roadmap/versions/3/decision", body={"decision": "adopt"})
    assert status == 200 and again["data"] == block["data"]
    assert count(env, "audit_events", MINH, "event_type = 'roadmap_version_decided'") == audit0 + 1
    # bản đang dùng không còn "chờ chọn": giữ bản cũ với nó là 409
    status, body = rest(
        env, "POST", "/roadmap/versions/3/decision", body={"decision": "keep_previous"}
    )
    assert status == 409 and body["error"]["code"] == "ROADMAP_VERSION_CONFLICT"

    env.reset(MINH)
    status, block = rest(
        env, "POST", "/roadmap/versions/3/decision", body={"decision": "keep_previous"}
    )
    assert status == 200 and block["data"]["status"] == "discarded"
    assert statuses(env) == {1: "superseded", 2: "active", 3: "discarded"}
    assert (
        count(
            env, "feedback", MINH, "option_id = 'version_keep_previous' AND decision = 'rejected'"
        )
        == 1
    )
    status, again = rest(
        env, "POST", "/roadmap/versions/3/decision", body={"decision": "keep_previous"}
    )
    assert status == 200
    status, body = rest(env, "POST", "/roadmap/versions/3/decision", body={"decision": "adopt"})
    assert status == 409  # bản đã bỏ không thể dùng
    status, body = rest(env, "POST", "/roadmap/versions/99/decision", body={"decision": "adopt"})
    assert status == 404 and body["error"]["code"] == "ROADMAP_NOT_FOUND"
    status, body = rest(
        env, "POST", "/roadmap/versions/3/decision", LAN, body={"decision": "adopt"}
    )
    assert status == 404
    for bad in ({"decision": "x"}, {}, {"decision": "adopt", "user_id": "u"}):
        status, body = rest(env, "POST", "/roadmap/versions/2/decision", body=bad)
        assert status == 400, bad


# =====================================================================================================
# POST /roadmap/regenerate và GET /roadmap/jobs/{job_id}
# =====================================================================================================
def regen_events(env):
    return [e for e in env.events.sent if e.detail_type == "roadmap.regeneration_requested"]


def test_sinh_lai_ghi_job_phat_su_kien_sau_commit_va_tra_lai_job_dang_chay(minh):
    env = minh
    env.events.sent.clear()
    status, job = rest(
        env,
        "POST",
        "/roadmap/regenerate",
        body={"note": "mình muốn đi sau Tết", "based_on_version": 2},
    )
    assert status == 200, job
    valid_rest("RoadmapJob", job)
    assert job["status"] == "queued" and job["trigger"] == "user_request" and job["progress"] == 0
    (ev,) = regen_events(env)
    d = ev.detail
    assert d["event_id"] == d["job_id"] == job["job_id"] and d["user_id"] == MINH
    assert (
        d["trigger"] == "user_request"
        and d["based_on_version"] == 2
        and d["app_date"] == "2026-11-21"
    )
    assert "note" not in d and "mình" not in json.dumps(
        d, ensure_ascii=False
    )  # ghi chú không đi vào sự kiện
    with env.master() as m:
        row = m.execute(
            "SELECT note, based_on_version, status FROM roadmap_jobs WHERE id = %s",
            (job["job_id"],),
        ).fetchone()
    assert row == ("mình muốn đi sau Tết", 2, "queued")  # ghi chú ở lại job
    # lần nữa khi đang có job: trả CHÍNH job đó, không ghi, không phát
    status, again = rest(env, "POST", "/roadmap/regenerate", body={})
    assert status == 200 and again["job_id"] == job["job_id"]
    assert len(regen_events(env)) == 1
    assert count(env, "roadmap_jobs", MINH) == 1
    # GET job, và current_job trong danh sách phiên bản
    status, got = rest(env, "GET", f"/roadmap/jobs/{job['job_id']}")
    assert status == 200 and got == job
    status, versions = rest(env, "GET", "/roadmap/versions")
    assert versions["current_job"]["job_id"] == job["job_id"]
    valid_rest("RoadmapVersionsResponse", versions)
    # người khác và id lạ đều 404 như nhau
    for sub, jid in ((LAN, job["job_id"]), (MINH, str(uuid.uuid4())), (MINH, "khong-phai-uuid")):
        status, body = rest(env, "GET", f"/roadmap/jobs/{jid}", sub)
        assert status == 404 and body["error"]["code"] == "ROADMAP_NOT_FOUND"
    # job xong thì lần sau tạo job mới
    with env.master() as m:
        m.execute(
            "UPDATE roadmap_jobs SET status = 'done', progress = 100, finished_at = now(), "
            "roadmap_id = %s, version = 3 WHERE id = %s",
            (str(uuid.uuid4()), job["job_id"]),
        )
    status, done = rest(env, "GET", f"/roadmap/jobs/{job['job_id']}")
    valid_rest("RoadmapJob", done)
    assert done["status"] == "done" and done["version"] == 3
    status, versions = rest(env, "GET", "/roadmap/versions")
    assert "current_job" not in versions
    status, job2 = rest(env, "POST", "/roadmap/regenerate")
    assert job2["job_id"] != job["job_id"] and len(regen_events(env)) == 2


def test_sinh_lai_kiem_dau_vao_va_ban_goc(minh):
    env = minh
    for bad in (
        {"note": ""},
        {"note": "x" * 201},
        {"alternative_id": "Lui-Han"},
        {"based_on_version": 0},
        {"user_id": "u"},
    ):
        status, body = rest(env, "POST", "/roadmap/regenerate", body=bad)
        assert status == 400 and body["error"]["code"] == "PARAMS_INVALID", bad
    status, body = rest(env, "POST", "/roadmap/regenerate", body={"based_on_version": 1})
    assert status == 409 and body["error"]["code"] == "ROADMAP_VERSION_CONFLICT"  # v1 đã bị thay
    status, body = rest(env, "POST", "/roadmap/regenerate", body={"based_on_version": 99})
    assert status == 404
    # alternative_id phải là một lựa chọn của bản gốc (bản seed on_track không có lựa chọn nào)
    status, body = rest(env, "POST", "/roadmap/regenerate", body={"alternative_id": "lui_han"})
    assert status == 400 and body["error"]["code"] == "PARAMS_INVALID"
    assert count(env, "roadmap_jobs", MINH) == 0 and regen_events(env) == []


def test_sinh_lai_khi_chua_co_lo_trinh_thi_job_khong_co_ban_goc(minh):
    env = minh
    status, job = rest(env, "POST", "/roadmap/regenerate", LAN)
    assert status == 200 and job["status"] == "queued"
    with env.master() as m:
        assert m.execute(
            "SELECT based_on_version FROM roadmap_jobs WHERE id = %s", (job["job_id"],)
        ).fetchone() == (None,)
    # job của lan không chạm minh
    assert count(env, "roadmap_jobs", MINH) == 0


def test_sinh_lai_su_kien_khop_hop_dong_va_phat_loi_khong_lam_hong_job(minh):
    env = minh
    env.events.fail = True  # bus hỏng: job vẫn ghi, có dòng audit EVENT_PUBLISH_FAILED
    failed0 = count(env, "audit_events", MINH, "code = 'EVENT_PUBLISH_FAILED'")
    status, job = rest(env, "POST", "/roadmap/regenerate")
    assert status == 200 and job["status"] == "queued"
    assert count(env, "audit_events", MINH, "code = 'EVENT_PUBLISH_FAILED'") == failed0 + 1
    with env.master() as m:
        # audit chỉ thêm và sống qua đặt lại; test khác đếm tuyệt đối dòng này của minh nên dọn dòng do test này tạo
        m.execute(
            "DELETE FROM audit_events WHERE user_id = %s AND code = 'EVENT_PUBLISH_FAILED' "
            "AND trace_id IN (SELECT trace_id FROM audit_events WHERE user_id = %s "
            "AND event_type = 'roadmap_regenerate_requested' ORDER BY created_at DESC LIMIT 1)",
            (MINH, MINH),
        )
    env.events.fail = False
    with env.master() as m:
        m.execute(
            "UPDATE roadmap_jobs SET status='failed', finished_at=now(), error_code='X', error_message='m' WHERE id=%s",
            (job["job_id"],),
        )
    env.events.sent.clear()
    status, job = rest(env, "POST", "/roadmap/regenerate")
    (ev,) = regen_events(env)
    schema = json.loads(
        (CONTRACTS / "events" / "roadmap.regeneration_requested.schema.json").read_text(
            encoding="utf-8"
        )
    )
    errors = list(Draft202012Validator(schema, registry=REGISTRY).iter_errors(ev.detail))
    assert not errors, [e.message for e in errors[:3]]


# =====================================================================================================
# Tool planner___save_roadmap, planner___get_roadmap, planner___optimize_allocation
# =====================================================================================================
def test_save_roadmap_ban_cho_chon_phien_ban_tang_dan_va_chay_lai_suitability(minh):
    env = minh
    audit0 = count(env, "audit_events", MINH, "event_type = 'roadmap_saved'")
    out = tool(env, "save_roadmap", **draft(env))
    assert out["status"] == "OK", out
    valid_tool("SaveRoadmapResult", out)
    d = out["data"]
    assert d["version"] == 4 and d["status"] == "proposed" and d["based_on_version"] == 2
    assert d["reason"] == {"code": "user_request", "text": "Bạn yêu cầu lập lại lộ trình."}
    assert d["headline"] == "Lộ trình phiên bản 4: 1 giai đoạn, 1 bước, kịp hạn."
    assert d["counts"] == {"pending": 1, "accepted": 0, "rejected": 0}
    assert d["rules_version"].startswith("v") and d["basis"]["confidence_band"] == "medium"
    assert d["basis"]["coverage"] == 0.62 and d["basis"]["stale"] is False
    step = d["phases"][0]["steps"][0]
    assert step["status"] == "pending" and step["checked_rules"] == ["obligations_first", "source_jar_covers"]
    # bản chờ cũ (v3) bị bỏ, bản đang dùng v2 giữ nguyên
    assert statuses(env) == {1: "superseded", 2: "active", 3: "discarded", 4: "proposed"}
    assert count(env, "audit_events", MINH, "event_type = 'roadmap_saved'") == audit0 + 1
    with env.master() as m:
        assert m.execute(
            "SELECT trace_id IS NOT NULL FROM roadmaps WHERE user_id = %s AND version = 4", (MINH,)
        ).fetchone() == (True,)
    # đọc lại bằng tool get_roadmap (cùng dữ liệu) và REST (cùng khối)
    got = tool(env, "get_roadmap", version=4)
    valid_tool("GetRoadmapResult", got)
    assert got["data"] == d
    got_active = tool(env, "get_roadmap")
    assert got_active["data"]["version"] == 2
    assert tool(env, "get_roadmap", which="proposed")["data"]["version"] == 4


def test_save_roadmap_bo_trang_thai_do_agent_tu_khai(minh):
    """Agent không tự đặt phiên bản, trạng thái bước hay luật đã kiểm: Lambda điền (hợp đồng RoadmapDraft có extra=forbid)."""
    env = minh
    d = draft(env)
    d["phases"][0]["steps"][0]["checked_rules"] = ["emergency_before_investing", "khong_co_that"]
    out = tool(env, "save_roadmap", **d)
    assert out["status"] == "OK"
    assert out["data"]["phases"][0]["steps"][0]["checked_rules"] == ["obligations_first", "source_jar_covers"]
    out = tool(env, "save_roadmap", **draft(env, based_on_version=2, version=9, status="active"))
    assert out["status"] == "OK"  # tham số lạ bị bỏ qua (Gateway không từ chối chúng)
    assert out["data"]["version"] == 5 and out["data"]["status"] == "proposed"


def test_save_roadmap_buoc_vi_pham_muc_block_thi_roadmap_invalid_va_khong_luu(minh):
    env = minh
    d = draft(env)
    step = d["phases"][0]["steps"][0]
    # rút 200.000 ₫ khỏi hũ Hóa đơn (450.000 ₫, còn 375.000 ₫ tiền điện đến hạn trước kỳ lương) làm hụt nghĩa vụ thiết yếu
    step.update(
        jar_code="hoa_don",
        amount_vnd=200000,
        action={
            "tool": "move_between_jars",
            "params": {"from_jar": "hoa_don", "to_jar": "an_uong", "amount_vnd": 200000},
        },
    )
    before = statuses(env)
    audit0 = count(env, "audit_events", MINH, "event_type = 'roadmap_saved'")
    out = tool(env, "save_roadmap", **d)
    assert out["status"] == "ERROR" and out["code"] == "ROADMAP_INVALID"
    assert "obligations_first" in out["message"] and "bu_them_an_uong" in out["message"]
    assert statuses(env) == before
    assert count(env, "audit_events", MINH, "event_type = 'roadmap_saved'") == audit0


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda d: d.update(reason_code="step_edited"),
            "ROADMAP_INVALID",
        ),  # chỉ người dùng sửa bước mới có lý do này
        (lambda d: d["phases"][0]["steps"][0].update(jar_code="khong_co"), "ROADMAP_INVALID"),
        (
            lambda d: d["phases"][0]["steps"][0].update(jar_code="chua_phan_loai"),
            "ROADMAP_INVALID",
        ),  # hũ hệ thống
        (lambda d: d["goals"][0]["jar"].update(code="khong_co"), "ROADMAP_INVALID"),
        (
            lambda d: d["phases"][0]["steps"][0]["action"]["params"].update(amount_vnd=900000),
            "ROADMAP_INVALID",  # hành động không khớp bước: luật kiểm một số, hành động chạy số khác
        ),
        (
            lambda d: d.update(feasibility="infeasible"),
            "ROADMAP_INVALID",
        ),  # infeasible cần đúng hai lựa chọn
        (
            lambda d: d.update(behavior_flag_id=str(uuid.uuid4())),
            "ROADMAP_INVALID",
        ),  # cờ chỉ đi với behavior_changed
        (
            lambda d: d.update(reason_code="behavior_changed", behavior_flag_id=str(uuid.uuid4())),
            "ROADMAP_INVALID",
        ),
        (
            lambda d: d.update(reason_code="initial", based_on_version=None),
            "ROADMAP_VERSION_CONFLICT",
        ),
        (lambda d: d.update(based_on_version=1), "ROADMAP_VERSION_CONFLICT"),  # bản gốc đã bị thay
        (lambda d: d.update(phases=[]), "PARAMS_INVALID"),
        (lambda d: d.update(reason_code="bat_ky"), "PARAMS_INVALID"),
    ],
)
def test_save_roadmap_tu_choi(minh, mutate, code):
    d = draft(minh)
    mutate(d)
    before = statuses(minh)
    out = tool(minh, "save_roadmap", **d)
    assert out["status"] == "ERROR" and out["code"] == code, out
    assert statuses(minh) == before


def test_save_roadmap_dau_hieu_hanh_vi_phai_la_cua_chinh_minh_va_da_xac_nhan(minh):
    env = minh
    _, v3 = rest(env, "GET", "/roadmap", query={"which": "proposed"})
    flag_id = v3["data"]["reason"]["behavior_flag_id"]
    d = draft(env, reason_code="behavior_changed", behavior_flag_id=flag_id, based_on_version=2)
    # người khác dùng cờ của minh: không thấy (RLS)
    other = tool(env, "save_roadmap", LAN, **{**d, "goals": [], "based_on_version": None})
    assert other["status"] == "ERROR" and other["code"] == "ROADMAP_INVALID"
    assert "Không tìm thấy dấu hiệu" in other["message"]
    out = tool(env, "save_roadmap", **d)
    assert out["status"] == "OK", out
    assert out["data"]["reason"]["behavior_flag_id"] == flag_id
    assert out["data"]["reason"]["text"].startswith("Chi Ăn uống mỗi tuần tăng từ 520.000 ₫")
    with env.master() as m:  # cờ đã được một phiên bản dùng
        assert m.execute(
            "SELECT status FROM behavior_flags WHERE id = %s", (flag_id,)
        ).fetchone() == ("applied",)
    # cờ 'nghi' (chưa xác nhận) hoặc báo nhầm không đủ để sinh lại
    with env.master() as m:
        m.execute(
            "UPDATE behavior_flags SET status = 'dismissed', confirmed_app_date = NULL, applied_at = NULL WHERE id = %s",
            (flag_id,),
        )
    out = tool(
        env,
        "save_roadmap",
        **draft(env, reason_code="behavior_changed", behavior_flag_id=flag_id, based_on_version=2),
    )
    assert (
        out["status"] == "ERROR"
        and out["code"] == "ROADMAP_INVALID"
        and "chưa được xác nhận" in out["message"]
    )


def test_save_roadmap_khong_co_du_bao_thi_forecast_unavailable_va_ho_so_thieu(minh):
    env = minh
    with env.master() as m:
        m.execute("DELETE FROM forecast_runs WHERE user_id = %s", (MINH,))
    out = tool(env, "save_roadmap", **draft(env))
    assert out["status"] == "ERROR" and out["code"] == "FORECAST_UNAVAILABLE"
    assert statuses(env) == {1: "superseded", 2: "active", 3: "proposed"}
    # người dùng chưa khai lương: PROFILE_INCOMPLETE
    with env.master() as m:
        m.execute("UPDATE users SET monthly_salary_vnd = NULL WHERE id = %s", (MINH,))
    out = tool(env, "save_roadmap", **draft(env))
    assert out["status"] == "ERROR" and out["code"] == "PROFILE_INCOMPLETE"


def test_save_roadmap_ban_dau_tien_la_active_va_ban_sau_la_cho_chon(minh):
    env = minh
    add_forecast(env, LAN)
    _, v2 = rest(env, "GET", "/roadmap")
    jar = "an_uong"
    base = {
        "reason_code": "initial",
        "feasibility": "on_track",
        "goals": [],
        "alternatives": [],
        "phases": [
            {
                "phase_id": "p1",
                "title": "Giữ nhịp",
                "start_date": "2026-11-21",
                "end_date": "2026-12-05",
                "steps": [
                    {
                        "step_id": "nhac_xem_lai",
                        "kind": "remind",
                        "title": "Nhắc xem lại hũ Ăn uống",
                        "reason": "Hũ sắp cạn.",
                        "jar_code": jar,
                    }
                ],
            }
        ],
    }
    out = tool(env, "save_roadmap", LAN, **base)
    assert out["status"] == "OK", out
    assert out["data"]["version"] == 1 and out["data"]["status"] == "active"
    assert out["data"]["headline"] == "Lộ trình phiên bản 1: 1 giai đoạn, 1 bước."
    assert out["data"]["phases"][0]["steps"][0].get("checked_rules") is None
    # bản đầu tiên chỉ có một lần
    again = tool(env, "save_roadmap", LAN, **base)
    assert again["status"] == "ERROR" and again["code"] == "ROADMAP_VERSION_CONFLICT"
    nxt = tool(
        env, "save_roadmap", LAN, **{**base, "reason_code": "goal_changed", "based_on_version": 1}
    )
    assert nxt["status"] == "OK" and nxt["data"]["status"] == "proposed"
    assert v2["data"]["version"] == 2  # bản của minh không bị chạm


def test_get_roadmap_tool_loi(minh):
    out = tool(minh, "get_roadmap", LAN)
    assert out == {
        "status": "ERROR",
        "code": "ROADMAP_NOT_FOUND",
        "message": "Bạn chưa có lộ trình nào. Hãy nhờ Yofina lập một lộ trình.",
    }
    for args in ({"version": 0}, {"version": "abc"}, {"which": "x"}):
        out = tool(minh, "get_roadmap", **args)
        assert out["status"] == "ERROR" and out["code"] == "PARAMS_INVALID", args
    assert tool(minh, "get_roadmap", version=77)["code"] == "ROADMAP_NOT_FOUND"


def test_optimize_allocation_la_proxy_sang_lambda_forecast(minh):
    from yofina_core.errors import ErrorCode, YofinaError

    env = minh
    out = tool(env, "optimize_allocation", horizon_months=3)  # chưa cấu hình Lambda forecast
    assert out["status"] == "ERROR" and out["code"] == "FORECAST_UNAVAILABLE"

    calls = []
    envelope = {
        "status": "OK",
        "as_of": "2026-12-10T03:00:00Z",
        "app_date": "2026-11-21",
        "data": {"x": 1},
    }

    class Stub:
        def optimize_allocation(self, user_id, args):
            calls.append((user_id, dict(args)))
            return envelope

    env.svc.forecast = Stub()
    out = tool(
        env, "optimize_allocation", horizon_months=3, shock_id="mat_viec_2_thang", user_id_lac="x"
    )
    assert out == envelope  # nguyên văn
    assert calls == [
        (MINH, {"horizon_months": 3, "shock_id": "mat_viec_2_thang"})
    ]  # bỏ user_id, bỏ tham số lạ

    class Down:
        def optimize_allocation(self, user_id, args):
            raise YofinaError(ErrorCode.FORECAST_UNAVAILABLE, "tạm thời")

    env.svc.forecast = Down()
    out = tool(env, "optimize_allocation")
    assert out["status"] == "ERROR" and out["code"] == "FORECAST_UNAVAILABLE"
    env.svc.forecast = None


# =====================================================================================================
# Hành động trong bước vẫn qua xác nhận: lưu và quyết định không ghi sổ cái
# =====================================================================================================
def test_chap_nhan_buoc_khong_doi_so_du_hanh_dong_di_qua_confirmations(minh):
    env = minh
    before = env.repo.jar_view(MINH)
    bal = {j["code"]: int(j["balance_vnd"]) for j in before.jars}
    rest(
        env,
        "POST",
        "/roadmap/steps/bu_an_uong/decision",
        body={"version": 3, "decision": "accepted"},
    )
    rest(env, "POST", "/roadmap/steps/bu_an_uong/edit", body={"version": 3, "amount_vnd": 130000})
    after = {j["code"]: int(j["balance_vnd"]) for j in env.repo.jar_view(MINH).jars}
    assert after == bal
    assert count(env, "transactions", MINH, "kind = 'transfer' AND source = 'move'") == 0
    # thực hiện action của bước: đúng luồng /confirmations rồi /actions với đúng tool và params của bước
    _, block = rest(env, "GET", "/roadmap")
    step = next(
        s for p in block["data"]["phases"] for s in p["steps"] if s["step_id"] == "bu_an_uong"
    )
    status, conf = rest(env, "POST", "/confirmations", body=step["action"] | {})
    assert status == 200 and conf["tool"] == "move_between_jars"
    status, receipt = rest(
        env,
        "POST",
        "/actions",
        body={**step["action"], "confirm_token": conf["confirm_token"]},
    )
    assert status == 200, receipt
    after = {j["code"]: int(j["balance_vnd"]) for j in env.repo.jar_view(MINH).jars}
    assert after["an_uong"] - bal["an_uong"] == step["action"]["params"]["amount_vnd"]
