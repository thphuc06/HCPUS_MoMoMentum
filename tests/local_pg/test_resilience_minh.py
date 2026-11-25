"""Điểm chống chịu, cú sốc và tối ưu phân bổ trên PostgreSQL thật cục bộ: SQL thật (migration 0009, 0052), RLS thật, engine ML thật, persona `minh`.

Kiểm cả chuỗi: đặt lại persona -> điểm chống chịu (ghi `resilience_scores`) -> ba cú sốc -> tối ưu phân bổ -> REST (`handle_http` của Lambda
forecast) -> op batch `optimize_allocation` (N1). Kết quả tool và REST đều được kiểm bằng JSON Schema của `contracts/`.
Số thật của `minh` in ra khi chạy với `-s` (ghi vào "Kết quả" của file phase)."""

from __future__ import annotations

import importlib.util
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import ANCHOR
from jsonschema import Draft202012Validator
from pipeline_helpers import make_settings

from personas import generate
from yofina_core.blocks import ResilienceScoreData, StressResultData
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.resilience import load_resilience_config, load_shock_set
from yofina_core.roadmap import AllocationPlanData
from yofina_forecast import tool as tool_mod
from yofina_forecast.allocation import AllocationEngine
from yofina_forecast.batch import handle_batch
from yofina_forecast.repo import ForecastRepo
from yofina_forecast.resilience import ResilienceEngine, compute_and_store
from yofina_forecast.runner import Pipeline
from yofina_forecast.stress import StressEngine

MINH, LAN, KHOA = "sub-minh", "sub-lan", "sub-khoa"
_spec = importlib.util.spec_from_file_location(
    "unit_conftest", Path(__file__).resolve().parents[1] / "unit" / "conftest.py"
)
_uc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_uc)
BASE = _uc.BASE
REG = _uc.build_registry()
CFG = load_resilience_config()


def validator(ref: str) -> Draft202012Validator:
    return Draft202012Validator({"$ref": f"{BASE}/{ref}"}, registry=REG)


SCORE_TOOL = validator("tools/forecast.results.schema.json#/$defs/GetResilienceScoreResult")
STRESS_TOOL = validator("tools/forecast.results.schema.json#/$defs/StressTestResult")
ALLOC_TOOL = validator("tools/planner.results.schema.json#/$defs/OptimizeAllocationResult")
SCORE_REST = validator("rest/openapi.yaml#/components/schemas/ResilienceScoreResponse")
STRESS_REST = validator("rest/openapi.yaml#/components/schemas/StressResultResponse")
SHOCKS_REST = validator("rest/openapi.yaml#/components/schemas/ShocksResponse")


def errs(v: Draft202012Validator, doc: Any) -> list[str]:
    return [f"{list(e.path)}: {e.message}" for e in v.iter_errors(doc)]


def pipeline(env) -> Pipeline:
    return Pipeline(
        ForecastRepo(env.db),
        make_settings(n_paths_full=10000, n_paths_fast=5000),
        None,
        clock=env.clock,
    )


def http_event(method: str, path: str, sub: str, body: dict | None = None) -> dict[str, Any]:
    ev: dict[str, Any] = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method, "path": path},
            "authorizer": {"jwt": {"claims": {"sub": sub}}},
        },
        "headers": {},
    }
    if body is not None:
        ev["body"] = json.dumps(body)
    return ev


def stored(env, user):
    return ForecastRepo(env.db).resilience(user)


def count(env, sql: str, *params) -> int:
    with env.master() as m:
        return m.execute(sql, params).fetchone()[0]


# --- điểm chống chịu -------------------------------------------------------------------------------
def test_minh_diem_chong_chiu_bon_thanh_phan_ghi_vao_bang_va_doc_lai(env):
    env.reset(MINH)
    p = pipeline(env)
    eng = ResilienceEngine(p)
    res = eng.get(MINH)
    assert not errs(SCORE_TOOL, res), errs(SCORE_TOOL, res)
    d = ResilienceScoreData.model_validate(res["data"])
    assert [c.key for c in d.components] == ["save", "spend", "borrow", "plan"]
    assert all(c.applicable for c in d.components)  # minh có mục tiêu Du lịch
    assert d.disclaimer == CFG.disclaimer and d.config_version == CFG.version
    # lịch sử của căn cứ là lịch sử bộ sinh persona tạo cho minh (120 ngày từ issue #8), không chép số
    assert d.basis.history_days == generate("minh", anchor=ANCHOR).history_days
    assert d.basis.is_initial_estimate is False
    row = stored(env, MINH)
    assert row["score"] == d.score and row["band"] == d.band and row["source"] == "read"
    assert row["app_date"].isoformat() == "2026-11-21" and len(row["components"]) == 4
    assert row["inputs"]["goal_count"] == 1 and row["previous_score"] is None
    # lần đọc sau trả lại bản đã lưu, không ghi thêm
    again = eng.get(MINH)
    assert again["data"]["components"] == res["data"]["components"]
    assert count(env, "SELECT count(*) FROM resilience_scores WHERE user_id = %s", MINH) == 1
    print("\n[MINH] điểm", d.score, d.band, d.headline)
    for c in d.components:
        print("[MINH]  ", c.key, c.score, c.weight, c.explanation)


def test_N2_compute_and_store_ghi_de_trong_ngay_va_diem_lan_truoc_sang_ngay_sau(env):
    env.reset(MINH)
    p = pipeline(env)
    first = compute_and_store(p, MINH, env.clock.now)
    assert stored(env, MINH)["source"] == "nightly" and first.previous_score is None
    again = compute_and_store(p, MINH, env.clock.now)
    assert again.score == first.score
    assert count(env, "SELECT count(*) FROM resilience_scores WHERE user_id = %s", MINH) == 1
    # sang ngày mô phỏng kế tiếp: thêm dòng mới, điểm lần trước là điểm hôm qua
    env.clock.now += timedelta(days=1)
    nxt = compute_and_store(p, MINH, env.clock.now)
    assert nxt.app_date == "2026-11-22" and nxt.previous_score == first.score
    assert count(env, "SELECT count(*) FROM resilience_scores WHERE user_id = %s", MINH) == 2


def test_diem_cua_nguoi_dung_khac_khong_doc_duoc_rls(env):
    env.reset(MINH)
    env.reset(LAN)
    p = pipeline(env)
    compute_and_store(p, MINH, env.clock.now)
    assert stored(env, MINH) is not None and stored(env, LAN) is None
    lan = ResilienceEngine(p).get(LAN)["data"]
    assert stored(env, LAN)["score"] == lan["score"]
    q = "SELECT count(*) FROM resilience_scores WHERE user_id = %s"
    assert count(env, q, MINH) == 1 and count(env, q, LAN) == 1  # mỗi người một dòng riêng


def test_nguoi_dung_uoc_luong_ban_dau_van_co_diem_nhung_co_nhan_tin_cay_thap(env):
    env.reset(KHOA)
    res = ResilienceEngine(pipeline(env)).get(KHOA)
    d = res["data"]
    assert d["basis"]["is_initial_estimate"] is True and d["basis"]["confidence_band"] == "low"
    assert not errs(SCORE_TOOL, res), errs(SCORE_TOOL, res)


# --- ba cú sốc ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("sid", [s.shock_id for s in load_shock_set().shocks])
def test_minh_ba_cu_soc_chay_that_va_khop_hop_dong(env, sid):
    env.reset(MINH)
    p = pipeline(env)
    res_eng = ResilienceEngine(p)
    score_now = res_eng.get(MINH)["data"]["score"]
    res = StressEngine(p, res_eng).run(MINH, sid)
    assert not errs(STRESS_TOOL, res), errs(STRESS_TOOL, res)
    d = StressResultData.model_validate(res["data"])
    assert d.score_before == score_now and d.score_after <= d.score_before
    assert d.emergency_jar is not None and d.emergency_jar.code == "du_phong"
    print(
        f"\n[MINH] {sid}: {d.score_before} -> {d.score_after} ({d.band_after}), trụ {d.runway_days_total}, "
        f"Dự phòng {d.runway_days_emergency} ngày, thiếu {d.shortfall_vnd} từ {d.shortfall_from}, {d.status}"
    )
    assert (
        count(env, "SELECT count(*) FROM scenarios WHERE user_id = %s", MINH) == 0
    )  # cú sốc không ghi gì


def test_cu_soc_tat_dinh_va_nang_nhe_dung_thu_tu(env):
    env.reset(MINH)
    p = pipeline(env)
    eng = StressEngine(p, ResilienceEngine(p))
    a = eng.run(MINH, "mat_viec_2_thang")["data"]
    b = eng.run(MINH, "mat_viec_2_thang")["data"]
    assert a == b  # cùng dữ liệu, cùng hạt giống
    assert a["common_random_numbers"] is True and a["method"] == "monte_carlo"
    sick = eng.run(MINH, "om_mot_tuan")["data"]
    assert a["score_after"] <= sick["score_after"] and a["shortfall_vnd"] >= sick["shortfall_vnd"]


# --- tối ưu phân bổ ------------------------------------------------------------------------------------
def test_minh_toi_uu_phan_bo_that_bao_toan_tien_va_ghi_do_tre(env):
    env.reset(MINH)
    p = pipeline(env)
    res = AllocationEngine(p).optimize(MINH, {})
    assert not errs(ALLOC_TOOL, res), errs(ALLOC_TOOL, res)
    d = AllocationPlanData.model_validate(res["data"])
    assert d.income_monthly_vnd == 9_000_000
    assert (
        sum(line.proposed_monthly_vnd for line in d.lines) + d.unallocated_vnd
        == d.income_monthly_vnd
    )
    assert d.goals and d.goals[0].jar.code == "du_lich"
    print(
        f"\n[MINH] LP: {d.status}, {d.solver.status}, elapsed_ms={d.solver.elapsed_ms}, {d.headline}"
    )
    for line in d.lines:
        print(
            "[MINH]  ",
            line.jar.code,
            line.floor_vnd,
            line.current_monthly_vnd,
            "->",
            line.proposed_monthly_vnd,
        )
    assert (
        count(env, "SELECT count(*) FROM resilience_scores WHERE user_id = %s", MINH) == 0
    )  # không ghi gì


def test_minh_muc_tieu_khong_kha_thi_noi_thang_va_hai_lua_chon(env):
    env.reset(MINH)
    res = AllocationEngine(pipeline(env)).optimize(
        MINH, {"goals": [{"jar": "du_lich", "target_vnd": 80_000_000, "target_date": "2026-12-20"}]}
    )
    d = AllocationPlanData.model_validate(res["data"])
    assert d.status == "infeasible" and len(d.alternatives) == 2 and not errs(ALLOC_TOOL, res)
    print(
        "\n[MINH] LP không khả thi:",
        d.headline,
        [a.label for a in d.alternatives],
        d.solver.elapsed_ms,
        "ms",
    )


def test_op_batch_optimize_allocation_N1_tren_db_that(env):
    env.reset(MINH)
    p = pipeline(env)
    out = handle_batch(
        {"op": "optimize_allocation", "user_id": MINH, "args": {"horizon_months": 4}}, p
    )
    assert (
        out["status"] == "OK" and not errs(ALLOC_TOOL, out) and out["data"]["horizon_months"] == 4
    )
    err = handle_batch({"op": "optimize_allocation", "user_id": "sub-khong-co", "args": {}}, p)
    assert (
        err["status"] == "ERROR"
        and err["code"] == "PROFILE_INCOMPLETE"
        and not errs(ALLOC_TOOL, err)
    )


# --- REST ------------------------------------------------------------------------------------------------
class NoAfford:
    def check(self, *a, **k):  # pragma: no cover
        raise AssertionError


def test_rest_ba_route_resilience_tren_db_that(env):
    env.reset(MINH)
    p = pipeline(env)
    res_eng = ResilienceEngine(p)
    stress = StressEngine(p, res_eng)
    out = tool_mod.handle_http(http_event("GET", "/resilience", MINH), NoAfford(), res_eng, stress)
    assert out["statusCode"] == 200
    body = json.loads(out["body"])
    assert body["type"] == "resilience_score" and not errs(SCORE_REST, body), errs(SCORE_REST, body)
    shocks = tool_mod.handle_http(
        http_event("GET", "/resilience/shocks", MINH), NoAfford(), res_eng, stress
    )
    sb = json.loads(shocks["body"])
    assert not errs(SHOCKS_REST, sb)
    assert [s["shock_id"] for s in sb["shocks"]] == [s.shock_id for s in load_shock_set().shocks]
    post = tool_mod.handle_http(
        http_event("POST", "/resilience/stress", MINH, {"shock_id": "mat_viec_2_thang"}),
        NoAfford(),
        res_eng,
        stress,
    )
    pb = json.loads(post["body"])
    assert post["statusCode"] == 200 and pb["type"] == "stress_result"
    assert not errs(STRESS_REST, pb), errs(STRESS_REST, pb)
    assert pb["data"]["score_before"] == body["data"]["score"]
    bad = tool_mod.handle_http(
        http_event("POST", "/resilience/stress", MINH, {"shock_id": "khong_co"}),
        NoAfford(),
        res_eng,
        stress,
    )
    assert (
        bad["statusCode"] == 404 and json.loads(bad["body"])["error"]["code"] == "SHOCK_NOT_FOUND"
    )


def test_nguoi_dung_chua_co_ho_so_thi_loi_profile_incomplete(env):
    p = pipeline(env)
    with pytest.raises(YofinaError) as e:
        ResilienceEngine(p).get("sub-chua-co-ho-so")
    assert e.value.code == ErrorCode.PROFILE_INCOMPLETE
