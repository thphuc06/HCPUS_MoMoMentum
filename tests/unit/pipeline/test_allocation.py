"""Tối ưu phân bổ (phase 4, F5): LP `linprog` (HiGHS) với sàn cứng qua biến elastic, trọng số theo ưu tiên, nới ĐÚNG MỘT vòng, đúng hai lựa
chọn khi vô nghiệm, tiền bảo toàn; engine phía Lambda forecast và op batch `optimize_allocation` (N1). Dùng solver THẬT."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal

import numpy as np
import pytest
from conftest import BASE, build_registry
from jsonschema import Draft202012Validator
from pipeline_helpers import APP_DATE, NOW
from test_resilience import USER, errors_of, pipe, world

from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.roadmap import AllocationPlanData
from yofina_forecast.allocation import AllocationEngine
from yofina_forecast.batch import handle_batch
from yofina_forecast.settings import DEFAULT_ALLOCATION_PARAMS as P
from yofina_ml.allocation import (
    AllocationProblem,
    GoalSpec,
    JarSpec,
    goal_need_vnd,
    optimize,
)

REGISTRY = build_registry()
RESULT = Draft202012Validator(
    {"$ref": f"{BASE}/tools/planner.results.schema.json#/$defs/OptimizeAllocationResult"},
    registry=REGISTRY,
)
INCOME = 12_000_000
STEP = P.rounding_step_vnd


def goal(days: int, remaining: int = 6_000_000, **kw) -> GoalSpec:
    return GoalSpec("du_lich", remaining, days, 6_000_000, date(2027, 3, 31), **kw)


def jars(*, days: int = 200, oblig_floor: int = 2_160_000, essential_floor: int = 2_400_000, **kw):
    return (
        JarSpec("an_uong", "essential", 3_600_000, essential_floor),
        JarSpec("di_lai", "essential", 1_200_000, 720_000),
        JarSpec("hoa_don", "obligation", 1_800_000, 1_800_000, "obligation"),
        JarSpec("giai_tri", "discretionary", 1_200_000),
        JarSpec("du_lich", "goal", 1_200_000, goal=goal(days, **kw)),
        JarSpec("du_phong", "emergency", 1_200_000, 600_000),
        JarSpec("nghia_vu", "obligation", 1_800_000, oblig_floor, "obligation"),
    )


def solve(income: int = INCOME, **kw):
    allow = kw.pop("allow_relaxation", True)
    return optimize(AllocationProblem(income, jars(**kw), P, allow_relaxation=allow))


def total(sol) -> int:
    return sum(j.proposed_vnd for j in sol.jars) + sol.unallocated_vnd


def prop(sol, code: str) -> int:
    return sol.outcome(code).proposed_vnd


# =====================================================================================
# Ba trạng thái và bảo toàn tiền
# =====================================================================================
def test_khong_ap_luc_thi_giu_nguyen_ti_le_chia_hien_tai():
    sol = solve(days=3000, oblig_floor=1_800_000)  # mục tiêu rất xa, sàn nằm trong mức hiện tại
    assert sol.status == "optimal" and sol.relaxation_rounds == 0 and not sol.relaxations
    assert all(prop(sol, j.code) == j.current_vnd for j in jars(days=3000, oblig_floor=1_800_000))
    assert sol.unallocated_vnd == 0 and total(sol) == INCOME and sol.solver_status == "optimal"


def test_ca_toi_uu_muc_tieu_can_them_tien_lay_tu_hu_khong_thiet_yeu_truoc():
    sol = solve(days=100)
    need = goal_need_vnd(jars(days=100)[4].goal, P.month_days)
    assert need > 1_200_000
    assert sol.status == "optimal" and sol.relaxations == ()
    assert prop(sol, "du_lich") >= need and sol.outcome("du_lich").goal_on_track
    assert prop(sol, "giai_tri") < 1_200_000  # hũ không thiết yếu bị cắt trước
    assert (
        prop(sol, "giai_tri") >= (1 - P.discretionary_max_cut_percent / 100) * 1_200_000 - STEP
    )  # nhưng không quá mức cắt tối đa
    assert (
        prop(sol, "du_phong") == 1_200_000 and prop(sol, "hoa_don") == 1_800_000
    )  # dự phòng và nghĩa vụ không đụng tới
    assert total(sol) == INCOME and all(j.floor_gap_vnd == 0 for j in sol.jars)


def test_ca_noi_rang_buoc_mot_vong_cat_sau_hu_khong_thiet_yeu_va_lui_han_muc_tieu():
    sol = solve(days=40)
    assert sol.status == "relaxed" and sol.relaxation_rounds == 1
    assert sol.solver_status == "optimal sau khi nới"
    kinds = {(r.kind, r.jar_code) for r in sol.relaxations}
    assert ("discretionary_reduced", "giai_tri") in kinds and ("goal_delayed", "du_lich") in kinds
    assert (
        prop(sol, "giai_tri") < (1 - P.discretionary_max_cut_percent / 100) * 1_200_000
    )  # sâu hơn vòng chặt cho phép
    delayed = next(r for r in sol.relaxations if r.kind == "goal_delayed")
    assert delayed.delay_months == P.relax_delay_months
    # mục tiêu kịp hạn đã LÙI nhưng đủ mức cần của hạn lùi
    g = jars(days=40)[4].goal
    assert prop(sol, "du_lich") >= goal_need_vnd(g, P.month_days, extra_months=P.relax_delay_months)
    assert not sol.outcome("du_lich").goal_on_track  # chưa kịp hạn gốc
    assert all(o.floor_gap_vnd == 0 for o in sol.jars) and total(sol) == INCOME


def test_vo_nghiem_sau_khi_noi_thi_infeasible_va_phan_thieu_roi_vao_hu_uu_tien_thap():
    sol = solve(income=6_000_000)  # sàn: nghĩa vụ 3,96 triệu + thiết yếu 3,12 triệu > thu nhập
    assert sol.status == "infeasible" and sol.relaxation_rounds == 1
    assert sol.floor_gap_total_vnd > 0 and sol.solver_status == "infeasible sau khi nới"
    gaps = {o.code: o.floor_gap_vnd for o in sol.jars}
    # mức phạt elastic: nghĩa vụ (1e6) > thiết yếu (1e5) nên phần thiếu dồn vào thiết yếu, nghĩa vụ giữ đủ sàn
    assert gaps["hoa_don"] == gaps["nghia_vu"] == 0
    assert gaps["an_uong"] + gaps["di_lai"] > 0 and gaps["du_phong"] >= 0
    assert prop(sol, "giai_tri") == 0 and total(sol) == 6_000_000


def test_uu_tien_nghia_vu_hon_thiet_yeu_hon_dua_tien_vao_muc_tieu():
    # thu nhập chỉ đủ sàn nghĩa vụ, một phần thiết yếu: không còn đồng nào cho mục tiêu
    sol = solve(income=4_800_000, days=40)
    assert sol.outcome("nghia_vu").floor_gap_vnd == 0 and sol.outcome("hoa_don").floor_gap_vnd == 0
    assert prop(sol, "du_lich") <= 1_200_000
    assert sol.status == "infeasible"
    assert prop(sol, "nghia_vu") + prop(sol, "hoa_don") == 2_160_000 + 1_800_000


def test_thu_nhap_bang_khong_la_vo_nghiem_khong_phai_loi_va_thu_nhap_am_bi_tu_choi():
    sol = solve(income=0)
    assert (
        sol.status == "infeasible"
        and total(sol) == 0
        and all(j.proposed_vnd == 0 for j in sol.jars)
    )
    with pytest.raises(ValueError):
        solve(income=-1)
    with pytest.raises(ValueError):
        optimize(AllocationProblem(10, (), P))


def test_khong_cho_noi_thi_ket_qua_vong_chat_va_van_bao_vo_nghiem():
    sol = solve(days=40, allow_relaxation=False)
    assert sol.status == "infeasible" and sol.relaxations == () and sol.notes
    assert total(sol) == INCOME


def test_tien_bao_toan_va_sau_ve_sau_voi_1500_bai_toan_ngau_nhien():
    rng = np.random.default_rng(11)
    seen = {"optimal": 0, "relaxed": 0, "infeasible": 0}
    for _ in range(300):
        income = int(rng.integers(0, 30_000_000))
        days = int(rng.integers(5, 400))
        sol = solve(
            income=income,
            days=days,
            remaining=int(rng.integers(0, 12_000_000)),
            oblig_floor=int(rng.integers(0, 6_000_000)),
            essential_floor=int(rng.integers(0, 5_000_000)),
        )
        seen[sol.status] += 1
        assert total(sol) == income, sol
        assert all(j.proposed_vnd >= 0 for j in sol.jars) and sol.unallocated_vnd >= 0
        assert sol.relaxation_rounds == (0 if sol.status == "optimal" else 1)
        if sol.status in ("optimal", "relaxed"):
            assert all(o.floor_gap_vnd == 0 for o in sol.jars), sol
        if sol.status == "optimal":
            assert not sol.relaxations
        if sol.status == "relaxed":
            assert sol.relaxations
        # sàn nghĩa vụ được giữ trước sàn thiết yếu: có hụt sàn nghĩa vụ thì thiết yếu đã bị đẩy xuống hết mức sàn của nó
        if sol.outcome("nghia_vu").floor_gap_vnd > 0:
            assert sol.outcome("an_uong").proposed_vnd <= 1000
    assert all(seen.values()), seen  # bộ ngẫu nhiên phủ cả ba trạng thái


def test_luon_xep_so_tien_theo_buoc_lam_tron_tru_mot_hu_nhan_phan_du():
    sol = solve(days=100)
    off = [j.code for j in sol.jars if j.proposed_vnd % STEP]
    assert (
        len(off) <= 2
    )  # phần dư làm tròn dồn vào hũ lớn nhất, và sàn/mức cần không phải bội của bước


def test_do_tre_giai_ghi_lai_va_nho():
    sol = solve(days=40)
    assert isinstance(sol.elapsed_ms, int) and 0 <= sol.elapsed_ms < 2000 and sol.method == "highs"


def test_ket_qua_tat_dinh_cung_vao_cung_ra():
    a, b = solve(days=40), solve(days=40)
    assert [(j.code, j.proposed_vnd) for j in a.jars] == [(j.code, j.proposed_vnd) for j in b.jars]


def test_trong_so_muc_tieu_doi_thu_tu_cat():
    base = jars(days=100)
    heavy = tuple(replace(j, weight=10.0) if j.code == "du_lich" else j for j in base)
    a = optimize(AllocationProblem(INCOME, base, P))
    b = optimize(AllocationProblem(INCOME, heavy, P))
    assert a.status == b.status == "optimal"
    assert prop(a, "du_lich") >= goal_need_vnd(base[4].goal, P.month_days)


# =====================================================================================
# Engine phía Lambda: dựng bài toán từ dữ liệu người dùng
# =====================================================================================
def run(args=None, **wkw):
    w = world(**wkw)
    eng = AllocationEngine(pipe(w))
    return eng.optimize(USER, args or {}), w


def test_engine_tra_dung_hop_dong_va_bao_toan_tien():
    res, w = run()
    assert not errors_of(RESULT, res), errors_of(RESULT, res)
    d = AllocationPlanData.model_validate(res["data"])
    assert d.income_monthly_vnd == 9_000_000 and d.horizon_months == 3
    assert sum(line.proposed_monthly_vnd for line in d.lines) + d.unallocated_vnd == 9_000_000
    assert [line.jar.code for line in d.lines] == [
        "an_uong",
        "di_lai",
        "giai_tri",
        "du_lich",
        "du_phong",
        "nghia_vu",
    ]
    by = {line.jar.code: line for line in d.lines}
    assert (
        by["nghia_vu"].kind == "obligation"
        and by["du_phong"].is_essential
        and not by["giai_tri"].is_essential
    )
    assert (
        by["an_uong"].is_essential and by["an_uong"].current_monthly_vnd == 2_700_000
    )  # 30% lương
    # sàn của hũ nghĩa vụ: tiền thuê phòng + tiền điện (thiết yếu) + Trả sau (nợ) quy về tháng; Trả sau một lần chia đều 3 tháng
    assert by["nghia_vu"].floor_vnd == 2_000_000 + 375_000 + round(1_000_000 / 3)
    assert d.goals[0].jar.code == "du_lich" and d.goals[0].target_vnd == 6_000_000
    assert (
        d.solver.name == "scipy.optimize.linprog"
        and d.solver.method == "highs"
        and d.solver.elapsed_ms >= 0
    )
    assert d.obligations_monthly_vnd == 2_000_000 + 375_000 + round(1_000_000 / 3)
    # lỗi P4-02 (E5): kỳ lộ trình bắt đầu từ ngày lương kế tiếp theo hồ sơ (ngày 5), không phải hôm nay 21/11
    assert d.period_start == "2026-12-05"
    assert (
        res["app_date"] == APP_DATE.isoformat() and w.score_saves == 0
    )  # không ghi gì (kể cả điểm chống chịu)


def test_engine_horizon_va_ghi_de_muc_tieu():
    res, _ = run(
        {
            "horizon_months": 6,
            "goals": [
                {
                    "jar": "du_lich",
                    "weight": 5,
                    "target_vnd": 9_000_000,
                    "target_date": "2027-02-01",
                }
            ],
        }
    )
    d = AllocationPlanData.model_validate(res["data"])
    assert d.horizon_months == 6
    g = d.goals[0]
    assert g.target_vnd == 9_000_000 and g.target_date == "2027-02-01"
    assert not errors_of(RESULT, res)
    # mục tiêu mới cho hũ chưa có mục tiêu (Dự phòng): cần target_vnd
    res2, _ = run({"goals": [{"jar": "du_phong", "target_vnd": 12_000_000}]})
    assert {g["jar"]["code"] for g in res2["data"]["goals"]} == {"du_lich", "du_phong"}
    assert "target_date" not in next(
        g for g in res2["data"]["goals"] if g["jar"]["code"] == "du_phong"
    )  # không hạn: tính theo horizon


@pytest.mark.parametrize(
    "args,code",
    [
        ({"horizon_months": 0}, ErrorCode.PARAMS_INVALID),
        ({"horizon_months": 25}, ErrorCode.PARAMS_INVALID),
        ({"horizon_months": True}, ErrorCode.PARAMS_INVALID),
        ({"goals": "x"}, ErrorCode.PARAMS_INVALID),
        ({"goals": [{"weight": 1}]}, ErrorCode.PARAMS_INVALID),
        ({"goals": [{"jar": "du_lich", "weight": 0}]}, ErrorCode.PARAMS_INVALID),
        ({"goals": [{"jar": "du_lich", "target_vnd": 1.5}]}, ErrorCode.PARAMS_INVALID),
        ({"goals": [{"jar": "du_lich", "target_date": "31/03/2027"}]}, ErrorCode.PARAMS_INVALID),
        ({"goals": [{"jar": "du_lich", "x": 1}]}, ErrorCode.PARAMS_INVALID),
        ({"goals": [{"jar": "khong_co", "target_vnd": 5}]}, ErrorCode.JAR_NOT_FOUND),
        ({"goals": [{"jar": "an_uong", "target_vnd": 5}]}, ErrorCode.PARAMS_INVALID),
        ({"goals": [{"jar": "du_phong"}]}, ErrorCode.PARAMS_INVALID),
        ({"shock_id": "la"}, ErrorCode.SHOCK_NOT_FOUND),
        ({"shock_id": 5}, ErrorCode.PARAMS_INVALID),
        ({"allow_relaxation": "co"}, ErrorCode.PARAMS_INVALID),
        ({"la": 1}, ErrorCode.PARAMS_INVALID),
    ],
)
def test_engine_tu_choi_tham_so_sai(args, code):
    w = world()
    with pytest.raises(YofinaError) as e:
        AllocationEngine(pipe(w)).optimize(USER, args)
    assert e.value.code == code


def test_engine_muc_tieu_khong_kha_thi_noi_thang_va_dua_dung_hai_lua_chon():
    res, _ = run(
        {"goals": [{"jar": "du_lich", "target_vnd": 90_000_000, "target_date": "2026-12-15"}]}
    )
    d = AllocationPlanData.model_validate(res["data"])
    assert not errors_of(RESULT, res), errors_of(RESULT, res)
    assert d.status == "infeasible" and len(d.alternatives) == 2 and d.solver.relaxation_rounds == 1
    assert {a.kind for a in d.alternatives} == {"delay_goal", "reduce_goal"}
    assert all(a.jar_code == "du_lich" for a in d.alternatives)
    assert d.headline.startswith("Chưa khả thi") and "không kịp" in d.headline
    assert not d.goals[0].on_track and d.goals[0].shortfall_vnd > 0
    reduce = next(a for a in d.alternatives if a.kind == "reduce_goal")
    assert reduce.metrics and reduce.metrics[0].after != reduce.metrics[0].before


def test_engine_ca_noi_mot_lan_ghi_lai_dieu_da_noi():
    res, _ = run(
        {"goals": [{"jar": "du_lich", "target_vnd": 6_000_000, "target_date": "2027-01-10"}]}
    )
    d = AllocationPlanData.model_validate(res["data"])
    assert d.status in ("relaxed", "infeasible")
    assert d.solver.relaxation_rounds == 1 and (d.status == "infeasible" or d.relaxations)
    assert not errors_of(RESULT, res)
    for r in d.relaxations:
        assert r.before and r.after and r.label


def test_engine_cu_soc_dung_lo_trinh_thich_ung():
    base, _ = run()
    job, _ = run({"shock_id": "mat_viec_2_thang"})
    d = AllocationPlanData.model_validate(job["data"])
    assert d.income_monthly_vnd == 0 and d.status == "infeasible" and len(d.alternatives) == 2
    assert not errors_of(RESULT, job)
    rent, _ = run({"shock_id": "tien_tro_tang"})
    ob_base = base["data"]["obligations_monthly_vnd"]
    assert rent["data"]["obligations_monthly_vnd"] > ob_base  # tiền trọ tăng làm nghĩa vụ tăng
    sick, _ = run({"shock_id": "om_mot_tuan"})
    assert sick["data"]["income_monthly_vnd"] < base["data"]["income_monthly_vnd"]
    for r in (rent, sick):
        assert not errors_of(RESULT, r)


def test_engine_khong_co_muc_tieu_thi_khong_co_goals():
    res, _ = run(goal=False)
    d = AllocationPlanData.model_validate(res["data"])
    assert d.goals == [] and d.status == "optimal" and "mục tiêu" not in d.headline


def test_engine_thieu_ho_so_la_profile_incomplete():
    with pytest.raises(YofinaError) as e:
        AllocationEngine(pipe(world(salary=None))).optimize(USER, {})
    assert e.value.code == ErrorCode.PROFILE_INCOMPLETE


def test_engine_thu_nhap_chi_du_san_thi_khong_con_tien_cho_hu_khong_thiet_yeu():
    res, _ = run(salary=2_000_000)
    d = AllocationPlanData.model_validate(res["data"])
    assert d.status == "infeasible" and len(d.alternatives) == 2
    assert sum(line.proposed_monthly_vnd for line in d.lines) + d.unallocated_vnd == 2_000_000
    assert next(line for line in d.lines if line.jar.code == "giai_tri").proposed_monthly_vnd == 0
    assert "sàn bắt buộc vượt thu nhập" in d.headline


# =====================================================================================
# Op batch (N1): phong bì như Gateway
# =====================================================================================
def test_op_batch_optimize_allocation_tra_nguyen_phong_bi_tool():
    w = world()
    p = pipe(w)
    out = handle_batch(
        {"op": "optimize_allocation", "user_id": USER, "args": {"horizon_months": 2}}, p
    )
    assert out["status"] == "OK" and not errors_of(RESULT, out)
    assert out["data"]["horizon_months"] == 2
    json.dumps(out)  # trả được qua Invoke (JSON thuần)
    assert out["as_of"] == "2026-12-10T03:00:00Z" == NOW.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.mark.parametrize(
    "event,code",
    [
        ({"op": "optimize_allocation", "args": {}}, "UNAUTHENTICATED"),
        ({"op": "optimize_allocation", "user_id": USER, "args": []}, "PARAMS_INVALID"),
        (
            {"op": "optimize_allocation", "user_id": USER, "args": {"horizon_months": 99}},
            "PARAMS_INVALID",
        ),
        (
            {"op": "optimize_allocation", "user_id": USER, "args": {"shock_id": "la"}},
            "SHOCK_NOT_FOUND",
        ),
    ],
)
def test_op_batch_loi_tra_phong_bi_loi_khong_nem(event, code):
    out = handle_batch(event, pipe(world()))
    assert out["status"] == "ERROR" and out["code"] == code and out["message"]
    assert not errors_of(RESULT, out)


def test_op_batch_thieu_ho_so_va_loi_ngoai_du_kien():
    out = handle_batch(
        {"op": "optimize_allocation", "user_id": USER, "args": {}}, pipe(world(salary=None))
    )
    assert out["code"] == "PROFILE_INCOMPLETE"
    w = world()
    p = pipe(w)

    def boom(*a, **k):
        raise RuntimeError("x")

    w.jar_state = boom  # type: ignore[method-assign]
    out = handle_batch({"op": "optimize_allocation", "user_id": USER, "args": {}}, p)
    assert out["status"] == "ERROR" and out["code"] == "INTERNAL_ERROR"
    assert "RuntimeError" not in json.dumps(out)  # không rò chi tiết nội bộ
    assert not errors_of(RESULT, out)


def test_cau_hinh_mac_dinh_la_gia_tri_mo_phong_co_the_ghi_de_bang_cau_hinh():
    from yofina_core.config import Config
    from yofina_forecast.settings import ForecastSettings

    keys = {
        "YOFINA_FORECAST_HORIZON_DAYS": "30", "YOFINA_FORECAST_HISTORY_WINDOW_DAYS": "330", "YOFINA_FORECAST_N_PATHS_FULL": "600",
        "YOFINA_FORECAST_N_PATHS_FAST": "400", "YOFINA_FORECAST_COLD_START_MIN_DAYS": "21", "YOFINA_FORECAST_ACI_GAMMA": "0.01",
        "YOFINA_FORECAST_COVERAGE_TARGET": "0.8", "YOFINA_FORECAST_SHORT_THRESHOLD": "0.5", "YOFINA_FORECAST_TIGHT_THRESHOLD": "0.2",
        "YOFINA_FORECAST_BAND_HIGH_MIN_DAYS": "60", "YOFINA_FORECAST_BAND_HIGH_MIN_COVERAGE": "0.7",
        "YOFINA_FORECAST_BAND_MEDIUM_MIN_DAYS": "21", "YOFINA_FORECAST_PROBABILITY_ENABLED": "true", "YOFINA_FORECAST_KEEP_RUNS": "6",
        "YOFINA_FORECAST_FAST_MAX_AGE_SECONDS": "86400", "YOFINA_FORECAST_RECOMPUTE_GUARD_SECONDS": "20",
        "YOFINA_FORECAST_FRESHNESS_SECONDS": "3600", "YOFINA_APP_TIMEZONE": "Asia/Ho_Chi_Minh",
        "YOFINA_FORECAST_IDEMPOTENCY_TTL_SECONDS": "100", "YOFINA_FORECAST_IDEMPOTENCY_LEASE_SECONDS": "10",
        "YOFINA_FORECAST_NIGHTLY_MAX_USERS": "10", "YOFINA_FORECAST_SCENARIO_N_PATHS": "100", "YOFINA_FORECAST_SCENARIO_KEEP": "5",
        "YOFINA_AFFORDABILITY_SHORT_P50_FLOOR_VND": "0", "YOFINA_AFFORDABILITY_TIGHT_P10_FLOOR_VND": "0",
        "YOFINA_REFERENCE_CACHE_SECONDS": "300",
    }  # fmt: skip
    base = ForecastSettings.from_config(Config(env=keys))
    assert (
        base.allocation == P
        and base.resilience_window_days == 30
        and base.essential_jar_codes == ("an_uong", "di_lai", "hoa_don")
    )
    over = ForecastSettings.from_config(
        Config(
            env={
                **keys,
                "YOFINA_ALLOCATION_RELAX_DELAY_MONTHS": "3",
                "YOFINA_ALLOCATION_WEIGHT_GOAL": "4.5",
                "YOFINA_ALLOCATION_BUFFER_TARGET_MONTHS": "1.5",
                "YOFINA_ESSENTIAL_JAR_CODES": "an_uong, hoa_don",
                "YOFINA_ALLOCATION_HORIZON_MONTHS": "6",
                "YOFINA_RESILIENCE_WINDOW_DAYS": "14",
            }
        )
    )
    assert over.allocation.relax_delay_months == 3 and over.allocation.weight_goal == 4.5
    assert P.buffer_target_months == 3.0 and over.allocation.buffer_target_months == 1.5
    assert (
        over.essential_jar_codes == ("an_uong", "hoa_don") and over.allocation_horizon_months == 6
    )
    assert over.resilience_window_days == 14


def test_mixed_daily_jar_floor_uses_only_essential_transaction_history():
    w = world()
    engine = AllocationEngine(pipe(w))
    gathered = engine.resilience.gather(USER, NOW)
    jars = tuple(
        {**j, "code": "chi_hang_ngay"} if j["code"] == "an_uong" else j
        for j in gathered.jar_rows
    )
    for daily_essential in (0, 20_000):
        ctx = replace(gathered.ctx, jars=tuple(
            {**j, "code": "chi_hang_ngay", "spend": [100_000] * 30,
             "essential_spend": [daily_essential] * 30}
            if j["code"] == "an_uong" else j
            for j in gathered.ctx.jars
        ))
        built = engine.build(
            replace(gathered, ctx=ctx, jar_rows=jars),
            horizon_months=3, goal_args=[], shock_id=None, allow_relaxation=False,
        )
        daily = next(j for j in built.problem.jars if j.code == "chi_hang_ngay")
        assert daily.floor_vnd == daily_essential * P.month_days * P.essential_floor_percent / 100


def test_daily_jar_next_to_own_category_jars_is_not_counted_twice():
    """Ví demo từ 26/11 (issue #39): Chi hằng ngày cạnh Ăn uống, Đi lại. Sàn của Ăn uống, Đi lại giữ theo chuỗi chi của chính chúng như
    khi chưa có Chi hằng ngày; Chi hằng ngày chỉ tính phần chi loại thiết yếu ghi vào chính nó (`essential_spend`, không đếm lại chi của
    Ăn uống). Hũ chỉ có chi lặt vặt (không loại thiết yếu) thì không thiết yếu, sàn 0, kể cả khi tổng chi của nó lớn."""
    w = world()
    engine = AllocationEngine(pipe(w))
    gathered = engine.resilience.gather(USER, NOW)
    alone = {j.code: j for j in engine.build(
        gathered, horizon_months=3, goal_args=[], shock_id=None, allow_relaxation=False,
    ).problem.jars}  # fmt: skip
    template_row = next(j for j in gathered.jar_rows if j["code"] == "giai_tri")
    template_ctx = next(j for j in gathered.ctx.jars if j["code"] == "giai_tri")
    days = len(template_ctx["spend"])
    jars = (
        {**template_row, "code": "chi_hang_ngay", "name": "Chi hằng ngày", "split_percent": 0, "balance_vnd": 300_000},
        *gathered.jar_rows,
    )
    for daily_essential, role in ((0, "discretionary"), (15_000, "essential")):
        ctx = replace(gathered.ctx, jars=(
            {**template_ctx, "code": "chi_hang_ngay", "spend": [80_000] * days, "essential_spend": [daily_essential] * days},
            *gathered.ctx.jars,
        ))  # fmt: skip
        built = {j.code: j for j in engine.build(
            replace(gathered, ctx=ctx, jar_rows=jars),
            horizon_months=3, goal_args=[], shock_id=None, allow_relaxation=False,
        ).problem.jars}  # fmt: skip
        daily = built["chi_hang_ngay"]
        assert daily.role == role
        assert daily.floor_vnd == daily_essential * P.month_days * P.essential_floor_percent / 100
        for code in ("an_uong", "di_lai", "giai_tri"):
            assert (built[code].role, built[code].floor_vnd) == (alone[code].role, alone[code].floor_vnd), code


def test_obligation_jar_floor_adds_essential_bills_not_tied_to_an_obligation():
    """Ví demo, ví ba hũ: hóa đơn vào hũ obligation. Sàn của hũ này = nghĩa vụ cứng đã khai + `essential_floor_percent` của chi
    thiết yếu theo LOẠI giao dịch không gắn nghĩa vụ (chuỗi `essential_spend` của ngữ cảnh), như sàn hũ Hóa đơn của ví bảy hũ cũ."""
    w = world()
    engine = AllocationEngine(pipe(w))
    gathered = engine.resilience.gather(USER, NOW)
    floors = {}
    for bills in (None, 0, 6_000):
        ctx = replace(gathered.ctx, jars=tuple(
            {**j, **({} if bills is None else {"essential_spend": [bills] * 30})}
            if j["code"] == "nghia_vu" else j
            for j in gathered.ctx.jars
        ))
        built = engine.build(
            replace(gathered, ctx=ctx),
            horizon_months=3, goal_args=[], shock_id=None, allow_relaxation=False,
        )
        nv = next(j for j in built.problem.jars if j.code == "nghia_vu")
        assert nv.role == "obligation" and nv.floor_tier == "obligation"
        floors[bills] = nv.floor_vnd
    hard = 2_000_000 + 375_000 + round(1_000_000 / 3)
    assert floors[None] == floors[0] == hard  # ví cũ (không có chuỗi) và ví không có hóa đơn: như trước
    assert floors[6_000] == hard + round(6_000 * P.month_days * P.essential_floor_percent / 100)


# =====================================================================================
# Sàn của hũ có khoản định kỳ trả từ chính nó (#39, 26/11): mọi hũ, không theo mã, kể cả khoản không thiết yếu
# =====================================================================================
NETFLIX = {
    "id": "00000000-0000-0000-0000-0000000000a2", "kind": "subscription", "name": "Netflix", "amount_vnd": 180_000,
    "amount_min_vnd": None, "amount_max_vnd": None, "due_date": "2026-12-15", "cycle": "monthly", "due_day": 15,
    "pay_jar_code": "giai_tri",
}  # fmt: skip
LUNCH = {**NETFLIX, "id": "00000000-0000-0000-0000-0000000000a3", "name": "Tiền cơm văn phòng", "amount_vnd": 300_000,
         "due_date": "2026-11-23", "due_day": 23, "pay_jar_code": "an_uong"}  # fmt: skip
#: mục tiêu làm vòng nới cắt hũ không thiết yếu (trước: Giải trí về 0 dù Netflix trả từ đó)
TIGHT_GOAL = {"goals": [{"jar": "du_lich", "target_vnd": 9_000_000, "target_date": "2027-02-01"}]}


def committed(*rows):
    from test_resilience import _ledger_obligation

    w = world()
    w.obl.extend(_ledger_obligation(dict(r)) for r in rows)  # không thiết yếu: `is_essential` theo loại, thuê bao là false
    return w


def built_jars(w):
    engine = AllocationEngine(pipe(w))
    gathered = engine.resilience.gather(USER, NOW)
    problem = engine.build(gathered, horizon_months=3, goal_args=[], shock_id=None, allow_relaxation=True).problem
    return {j.code: j for j in problem.jars}


def test_floor_of_each_jar_covers_every_active_obligation_it_pays():
    bus = {**NETFLIX, "id": "00000000-0000-0000-0000-0000000000a4", "name": "Vé xe buýt tháng", "amount_vnd": 500_000,
           "pay_jar_code": "di_lai"}  # fmt: skip
    base, now = built_jars(world()), built_jars(committed(NETFLIX, LUNCH, bus))
    assert not any(o["is_essential"] for o in committed(NETFLIX, LUNCH).obl if o["kind"] == "subscription")
    # Giải trí: hũ không thiết yếu, sàn đúng bằng khoản định kỳ của nó; bậc sàn là bậc thiết yếu (khoản cứng vẫn đứng trên)
    assert (now["giai_tri"].role, now["giai_tri"].floor_vnd, now["giai_tri"].floor_tier) == ("discretionary", 180_000, "essential")
    # Ăn uống: sàn chi thiết yếu đã cao hơn khoản định kỳ trả từ nó nên giữ nguyên; Đi lại: sàn chi thiết yếu thấp hơn vé tháng nên
    # sàn lên bằng vé tháng
    assert base["an_uong"].floor_vnd > 300_000 and now["an_uong"].floor_vnd == base["an_uong"].floor_vnd
    assert base["di_lai"].floor_vnd < 500_000 and now["di_lai"].floor_vnd == 500_000
    assert {c: j for c, j in now.items() if c not in ("giai_tri", "di_lai")} == {
        c: j for c, j in base.items() if c not in ("giai_tri", "di_lai")
    }


def test_obligation_jar_floor_also_counts_its_non_essential_obligations():
    base = built_jars(world())
    now = built_jars(committed({**NETFLIX, "pay_jar_code": None}))  # không lưu hũ trả: hũ Nghĩa vụ chung
    assert now["nghia_vu"].floor_vnd == base["nghia_vu"].floor_vnd + 180_000
    assert now["nghia_vu"].floor_tier == "obligation" and now["giai_tri"].floor_vnd == 0


def test_lp_never_proposes_a_jar_below_the_obligations_it_pays():
    from yofina_core.spend_baseline import BaselineSettings, typical_monthly

    res, _ = run(TIGHT_GOAL)
    plain = {line["jar"]["code"]: line for line in res["data"]["lines"]}
    # hũ không có khoản định kỳ: trước 26/11 chiều vòng nới cắt về 0; nay chỉ tới sàn chi (#39). Sàn chi là nửa mức nền bền của hũ (26/11
    # tối: Giải trí chi 60.000 ₫ mỗi sáu ngày, tuần điển hình 60.000 ₫, mức nền 257.143 ₫/tháng; trước đó nửa chi 30 ngày 300.000 ₫),
    # làm tròn lên bước nghìn đồng ở phần đề xuất. Sàn chi là sàn mềm: báo ở `recent_spend`, sàn cứng của dòng là 0 (C3, #39)
    fun = plain["giai_tri"]
    series = [60_000 if i % 6 == 0 else 0 for i in range(47)]  # chuỗi Giải trí của `world()`
    level = typical_monthly(series, BaselineSettings(P.spend_baseline_weeks, P.spend_baseline_min_weeks, P.month_days, 30))
    keep = round(P.spending_keep_ratio * level.monthly_vnd)
    assert level.robust and fun["recent_spend"]["keep_floor_vnd"] == keep == 128_572
    assert fun["proposed_monthly_vnd"] == -(-keep // STEP) * STEP
    assert fun["floor_vnd"] == 0
    w = committed(NETFLIX, LUNCH)
    out = AllocationEngine(pipe(w)).optimize(USER, TIGHT_GOAL)
    assert not errors_of(RESULT, out), errors_of(RESULT, out)
    d = AllocationPlanData.model_validate(out["data"])
    by = {line.jar.code: line for line in d.lines}
    # từ 26/11 chiều (#39): Du lịch không lấy được tiền dưới sàn chi của Giải trí hay phần chia của Dự phòng chưa tới đích, nên "chưa khả
    # thi" kèm hai lựa chọn (trước: "relaxed", bỏ giữ Dự phòng để Du lịch lùi hạn); mọi sàn vẫn đủ
    assert d.status == "infeasible" and len(d.alternatives) == 2
    assert all(line.floor_gap_vnd == 0 for line in d.lines)
    assert by["giai_tri"].floor_vnd == 180_000 and by["giai_tri"].proposed_monthly_vnd >= 180_000
    assert by["giai_tri"].floor_gap_vnd == 0 and not by["giai_tri"].is_essential  # vẫn là hũ không thiết yếu với model
    assert by["an_uong"].proposed_monthly_vnd >= by["an_uong"].floor_vnd
    assert sum(line.proposed_monthly_vnd for line in d.lines) + d.unallocated_vnd == d.income_monthly_vnd


def test_non_essential_obligations_stay_the_cuttable_part_when_floors_exceed_income():
    from test_resilience import _ledger_obligation

    w = world(salary=2_000_000, goal=False)
    w.obl.extend(_ledger_obligation(dict(r)) for r in (NETFLIX, LUNCH))
    d = AllocationPlanData.model_validate(AllocationEngine(pipe(w)).optimize(USER, {})["data"])
    assert d.status == "infeasible" and "sàn bắt buộc vượt thu nhập" in d.headline
    cut = next(a for a in d.alternatives if a.option_id == "cat_khoan_dinh_ky")
    assert "480.000" in cut.summary  # Netflix 180.000 + cơm văn phòng 300.000 mỗi tháng


def three_jar_world(*obligations, salary=9_000_000, days=47, buffer_code="du_phong"):
    """Ví ba hũ của tài khoản mới (Chi hằng ngày 42, Nghĩa vụ 33, Dự phòng `buffer` 25) với các nghĩa vụ đã khai. `buffer_code` đổi mã
    của hũ Dự phòng (hũ đệm nhận ra theo `purpose`, không theo mã)."""
    from pipeline_helpers import context_rows, jar_row
    from test_resilience import World, _ledger_obligation

    jars = [
        ("chi_hang_ngay", "spending", 900_000, 42, 1, None, None),
        ("nghia_vu", "obligation", 1_000_000, 33, 2, None, None),
        (buffer_code, "saving", 500_000, 25, 3, None, None),
    ]
    spend = {"chi_hang_ngay": [80_000 + 20_000 * (i % 4) for i in range(days)]}
    ctx_jars = [jar_row(c, k, b, s, o, spend.get(c, [0] * days)) for c, k, b, s, o, _g, _d in jars]
    w = World(
        context_rows(days=days, salary=salary, jars=ctx_jars, obligations=[dict(o) for o in obligations]),
        jars,
        [_ledger_obligation(dict(o)) for o in obligations],
    )
    rows = w.jar_state
    w.jar_state = lambda user_id: [{**r, "purpose": "buffer"} if r["code"] == buffer_code else r for r in rows(user_id)]
    return w


def test_three_jar_wallet_lp_keeps_daily_jar_above_subscription_it_pays():
    rent = {**NETFLIX, "id": "00000000-0000-0000-0000-0000000000a5", "kind": "rent", "name": "Tiền trọ", "amount_vnd": 7_500_000,
            "due_date": "2026-12-06", "due_day": 6, "pay_jar_code": "nghia_vu"}  # fmt: skip
    spotify = {**NETFLIX, "name": "Spotify", "amount_vnd": 60_000, "pay_jar_code": "chi_hang_ngay"}
    plain = AllocationPlanData.model_validate(AllocationEngine(pipe(three_jar_world(rent))).optimize(USER, {})["data"])
    by = {line.jar.code: line for line in plain.lines}
    # tiền trọ 7.500.000 ₫ vượt phần Nghĩa vụ: Chi hằng ngày (không thiết yếu, không khoản định kỳ nào) bị cắt về 0 như trước
    assert by["chi_hang_ngay"].floor_vnd == 0 and by["chi_hang_ngay"].proposed_monthly_vnd == 0
    out = AllocationEngine(pipe(three_jar_world(rent, spotify))).optimize(USER, {})
    assert not errors_of(RESULT, out), errors_of(RESULT, out)
    by = {line.jar.code: line for line in AllocationPlanData.model_validate(out["data"]).lines}
    assert by["chi_hang_ngay"].floor_vnd == 60_000 and by["chi_hang_ngay"].proposed_monthly_vnd >= 60_000
    assert not by["chi_hang_ngay"].is_essential

# =====================================================================================
# Đích số dư của hũ Dự phòng (`buffer`, BR-64) trong lộ trình (#39, 26/11): nhận qua `goals`, giữ vai đệm, không đọc goal_vnd
# =====================================================================================
def purposed(*, purposes=None, goal_vnd=None, **kw):
    """Ví có mục đích hũ như ví demo và ví ba hũ (Dự phòng `buffer`, Du lịch `goal`). Kho thử không có cột `purpose` nên gắn vào hàng;
    `goal_vnd` (nếu có) ghi lên hũ Dự phòng để kiểm bộ tối ưu không đọc nó."""
    w = world(**kw)
    rows = w.jar_state
    purposes = {"du_phong": "buffer", "du_lich": "goal", **(purposes or {})}

    def jar_state(user_id):
        out = []
        for r in rows(user_id):
            r = {**r, "purpose": purposes.get(r["code"])}
            if r["code"] == "du_phong" and goal_vnd is not None:
                r["goal_vnd"] = Decimal(goal_vnd)
            out.append(r)
        return out

    w.jar_state = jar_state  # type: ignore[method-assign]
    return w


def buffer_goal(target=3_000_000, when=date(2027, 2, 21), **kw):
    return {"jar": "du_phong", "target_vnd": target, **({"target_date": when.isoformat()} if when else {}), **kw}


def test_hu_du_phong_nhan_dich_so_du_giu_vai_dem_va_chieu_ra_goals():
    w = purposed()
    engine = AllocationEngine(pipe(w))
    built = engine.build(
        engine.resilience.gather(USER, NOW), horizon_months=3, goal_args=[buffer_goal()], shock_id=None,
        allow_relaxation=True,
    )  # fmt: skip
    buf = next(j for j in built.problem.jars if j.code == "du_phong")
    # vai đệm (cắt sau cùng), mức cần tính từ số dư hiện có 2.000.000 ₫ tới đích 3.000.000 ₫ trước 21/02/2027
    assert buf.role == "emergency" and buf.goal is not None
    assert (buf.goal.target_vnd, buf.goal.remaining_vnd, buf.goal.days_left) == (3_000_000, 1_000_000, 92)
    res = engine.optimize(USER, {"goals": [buffer_goal()]})
    assert not errors_of(RESULT, res), errors_of(RESULT, res)
    d = AllocationPlanData.model_validate(res["data"])
    goal = next(x for x in d.goals if x.jar.code == "du_phong")
    assert goal.jar.purpose == "buffer" and goal.target_vnd == 3_000_000 and goal.target_date == "2027-02-21"
    assert goal.on_track and goal.monthly_needed_vnd == goal_need_vnd(buf.goal, P.month_days) == 326_087
    by = {line.jar.code: line for line in d.lines}
    assert by["du_phong"].is_essential and by["du_phong"].proposed_monthly_vnd >= goal.monthly_needed_vnd
    assert {x.jar.code for x in d.goals} == {"du_lich", "du_phong"}  # mục tiêu đã khai ở hũ goal vẫn có
    # số dư 2.000.000 ₫ chưa tới đích 3.000.000 ₫ nên Dự phòng giữ phần chia ở vòng chặt (BR-65, #39): Du lịch không còn lấy tiền từ Dự
    # phòng để kịp hạn (trước 26/11 trưa: "optimal", Dự phòng 1.800.000 → 1.142.000 ₫, Du lịch tăng) mà lùi hạn; Dự phòng chỉ nhường
    # phần sàn thiết yếu còn thiếu sau khi Giải trí về 0
    assert d.status == "relaxed" and w.score_saves == 0
    assert {(r.kind, r.jar_code) for r in d.relaxations} == {("discretionary_reduced", "giai_tri"), ("goal_delayed", "du_lich")}
    assert by["du_lich"].proposed_monthly_vnd <= by["du_lich"].current_monthly_vnd
    assert all(line.floor_gap_vnd == 0 for line in d.lines)


def test_dich_du_phong_khong_doc_goal_vnd_cua_hu():
    # hũ Dự phòng có goal_vnd trên hàng (dữ liệu cũ hay tự đặt): không có mục tiêu nếu lượt này không gửi, và không dùng làm đích
    w = purposed(goal_vnd=50_000_000)
    plain = AllocationPlanData.model_validate(AllocationEngine(pipe(w)).optimize(USER, {})["data"])
    assert [x.jar.code for x in plain.goals] == ["du_lich"]
    asked = AllocationPlanData.model_validate(AllocationEngine(pipe(w)).optimize(USER, {"goals": [buffer_goal()]})["data"])
    assert next(x for x in asked.goals if x.jar.code == "du_phong").target_vnd == 3_000_000
    for bad in ({"jar": "du_phong"}, {"jar": "du_phong", "target_date": "2027-02-21"}):
        with pytest.raises(YofinaError) as e:
            AllocationEngine(pipe(w)).optimize(USER, {"goals": [bad]})
        assert e.value.code == ErrorCode.PARAMS_INVALID and "target_vnd" in e.value.message


def test_dich_du_phong_khong_kha_thi_ra_chua_kha_thi_kem_hai_lua_chon():
    # 30 triệu trong một tháng với lương 9 triệu: không lỗi, "chưa khả thi" và đúng hai lựa chọn của hũ Dự phòng như hũ goal
    res = AllocationEngine(pipe(purposed())).optimize(
        USER, {"goals": [buffer_goal(30_000_000, date(2026, 12, 21))]}
    )
    assert not errors_of(RESULT, res), errors_of(RESULT, res)
    d = AllocationPlanData.model_validate(res["data"])
    assert d.status == "infeasible" and d.headline.startswith("Chưa khả thi") and "không kịp" in d.headline
    assert {a.kind for a in d.alternatives} == {"delay_goal", "reduce_goal"}
    assert all(a.jar_code == "du_phong" for a in d.alternatives)
    goal = next(x for x in d.goals if x.jar.code == "du_phong")
    assert not goal.on_track and goal.shortfall_vnd > 0
    reduce = next(a for a in d.alternatives if a.kind == "reduce_goal")
    assert reduce.metrics and reduce.metrics[0].before == "30.000.000 ₫" != reduce.metrics[0].after


@pytest.mark.parametrize("purpose", ["sinking", "long_term"])
def test_hu_tiet_kiem_khac_van_khong_nhan_muc_tieu(purpose):
    with pytest.raises(YofinaError) as e:
        AllocationEngine(pipe(purposed(purposes={"du_lich": purpose}))).optimize(
            USER, {"goals": [{"jar": "du_lich", "target_vnd": 5_000_000}]}
        )
    assert e.value.code == ErrorCode.PARAMS_INVALID


@pytest.mark.parametrize(
    "commitments,balance,hold",
    [
        pytest.param([("2026-11-21", 5_000_000)], 0, False, id="today-excluded"),
        pytest.param([("2026-11-22", 5_000_000)], 0, True, id="tomorrow-included"),
        pytest.param([("2027-02-19", 5_000_000)], 0, True, id="horizon-end-included"),
        pytest.param([("2027-02-20", 5_000_000)], 0, False, id="after-horizon-excluded"),
        pytest.param(
            [("2027-01-15", 2_000_000), ("2027-02-05", 3_000_000)],
            5_000_000,
            False,
            id="fully-funded",
        ),
        pytest.param(
            [("2027-01-15", 2_000_000), ("2027-02-05", 3_000_000)],
            4_999_999,
            True,
            id="one-dong-short",
        ),
        pytest.param(
            [("2026-11-20", 7_000_000), ("2027-02-05", 5_000_000), ("2027-02-20", 6_000_000)],
            5_000_000,
            False,
            id="outside-amounts-excluded",
        ),
        pytest.param([], 0, False, id="empty"),
        pytest.param(None, 0, False, id="null"),
    ],
)
def test_quy_don_giu_phan_chia_khi_thieu_tien_cho_khoan_sap_can(commitments, balance, hold):
    engine = AllocationEngine(pipe(purposed()))
    gathered = engine.resilience.gather(USER, NOW)
    assert gathered.app_date == APP_DATE  # ngày của ví, không phải ngày của NOW
    row = {
        "code": "quy_don",
        "kind": "saving",
        "purpose": "sinking",
        "balance_vnd": Decimal(balance),
        "split_percent": Decimal(10),
        "sinking_items": None
        if commitments is None
        else [
            {"name": f"Khoản {i}", "needed_date": day, "amount_vnd": amount}
            for i, (day, amount) in enumerate(commitments, 1)
        ],
    }
    built = engine.build(
        replace(gathered, jar_rows=(*gathered.jar_rows, row)),
        horizon_months=3,
        goal_args=[],
        shock_id=None,
        allow_relaxation=True,
    )
    sinking = built.problem.jars[-1]
    assert sinking.code == "quy_don" and sinking.role == "saving" and sinking.goal is None
    assert sinking.current_vnd == 900_000 and sinking.floor_vnd == 0
    assert sinking.hold_current is hold


def test_vi_bay_hu_cu_du_phong_nhan_muc_tieu_nhu_hu_tiet_kiem_cu():
    # `purpose` NULL: hũ Dự phòng nhận mục tiêu như mọi hũ tiết kiệm cũ, vai mục tiêu như trước
    engine = AllocationEngine(pipe(world()))
    built = engine.build(
        engine.resilience.gather(USER, NOW), horizon_months=3, goal_args=[buffer_goal()], shock_id=None,
        allow_relaxation=True,
    )  # fmt: skip
    assert next(j for j in built.problem.jars if j.code == "du_phong").role == "goal"


@pytest.mark.parametrize("buffer_first", [True, False])
def test_muc_can_cua_hu_du_phong_xep_truoc_muc_tieu_khac_br65(buffer_first):
    """BR-65: hũ đệm (tới đích) trước mục tiêu. Thu nhập đủ mức cần của Dự phòng cộng mức cần theo hạn đã lùi của Du lịch, không đủ mức
    cần của cả hai theo hạn gốc: Dự phòng nhận đủ, Du lịch lùi hạn. Trước đây hai mức cần cùng mức phạt nên phần dư rơi vào hũ nào tùy
    thứ tự hũ trong bài toán (Du lịch đứng trước thì Dự phòng chỉ giữ 500.000 ₫)."""
    buf = GoalSpec("du_phong", 3_000_000, 90, 3_000_000, None)
    trip = GoalSpec("du_lich", 6_000_000, 90, 6_000_000, None)
    need = goal_need_vnd(buf, P.month_days)
    pair = [JarSpec("du_phong", "emergency", 500_000, goal=buf), JarSpec("du_lich", "goal", 500_000, goal=trip)]
    problem = AllocationProblem(
        2_000_000 + need + 700_000,
        (JarSpec("nghia_vu", "obligation", 2_000_000, 2_000_000, "obligation"), *(pair if buffer_first else pair[::-1])),
        P,
    )
    sol = optimize(problem)
    assert sol.status == "relaxed" and total(sol) == problem.income_vnd
    assert prop(sol, "du_phong") >= need and sol.outcome("du_phong").goal_on_track
    assert not sol.outcome("du_lich").goal_on_track
    assert {(r.kind, r.jar_code) for r in sol.relaxations} == {("goal_delayed", "du_lich")}


# =====================================================================================
# Hũ đệm chưa tới đích giữ phần chia hiện tại ở vòng chặt (BR-65, #39 26/11): Dự phòng trước, mục tiêu sau. Trước đây mức cần theo hạn
# của hũ mục tiêu (phạt `penalty_goal_need`) thắng phần cắt hũ đệm (`weight_emergency`), nên LP cắt Dự phòng để tăng Du lịch.
# =====================================================================================
def held_problem(*, hold: bool, an_uong_floor: int = 3_000_000, income: int = 10_000_000, trip: bool = True, allow: bool = True):
    """Du lịch cần 1.800.000 ₫/tháng để kịp hạn mà đang nhận 1.000.000 ₫; ở vòng chặt Giải trí chỉ nhường được 500.000 ₫, Ăn uống và
    Nghĩa vụ đang đúng bằng sàn. `trip=False`: Du lịch không có mục tiêu."""
    goal = GoalSpec("du_lich", 5_400_000, 90, 6_000_000, None) if trip else None
    return AllocationProblem(
        income,
        (
            JarSpec("an_uong", "essential", 3_000_000, an_uong_floor),
            JarSpec("nghia_vu", "obligation", 3_000_000, 3_000_000, "obligation"),
            JarSpec("giai_tri", "discretionary", 1_000_000),
            JarSpec("du_lich", "goal", 1_000_000, goal=goal),
            JarSpec("du_phong", "emergency", 2_000_000, hold_current=hold),
        ),
        P,
        allow_relaxation=allow,
    )


def proposals(sol) -> dict[str, int]:
    return {j.code: j.proposed_vnd for j in sol.jars}


def goal_up_while_buffer_cut(sol, problem, buffer: str) -> list[str]:
    """Hũ mục tiêu được TĂNG trong khi hũ đệm bị CẮT (điều BR-65 cấm khi hũ đệm chưa tới đích)."""
    cur = {j.code: j.current_vnd for j in problem.jars}
    if sol.outcome(buffer).proposed_vnd >= cur[buffer]:
        return []
    return [j.code for j in problem.jars if j.role == "goal" and sol.outcome(j.code).proposed_vnd > cur[j.code]]


def test_hu_dem_duoc_giu_khong_bi_cat_de_tang_hu_muc_tieu():
    before = optimize(held_problem(hold=False))
    # hành vi cũ: Dự phòng mất 300.000 ₫ để Du lịch kịp hạn
    assert before.status == "optimal" and prop(before, "du_phong") < 2_000_000 and prop(before, "du_lich") >= 1_800_000
    problem = held_problem(hold=True)
    sol = optimize(problem)
    assert prop(sol, "du_phong") == 2_000_000 and goal_up_while_buffer_cut(sol, problem, "du_phong") == []
    # Du lịch vẫn kịp hạn nhờ cắt sâu hũ không thiết yếu (vòng nới), không lấy từ Dự phòng
    assert sol.status == "relaxed" and sol.outcome("du_lich").goal_on_track
    assert {(r.kind, r.jar_code) for r in sol.relaxations} == {("discretionary_reduced", "giai_tri")}
    assert total(sol) == problem.income_vnd and all(o.floor_gap_vnd == 0 for o in sol.jars)


@pytest.mark.parametrize("income,status", [(10_000_000, "relaxed"), (5_000_000, "infeasible")])
def test_san_nghia_vu_va_thiet_yeu_van_thang_hu_dem_duoc_giu(income, status):
    """Sàn thiết yếu cần thêm 2.000.000 ₫ mà ở vòng chặt hũ khác chỉ nhường được 1.500.000 ₫. Từ 26/11 chiều (#39, thứ tự ưu tiên chốt:
    giữ hũ đệm đứng trên phần cắt sâu của hũ không thiết yếu): vòng nới cắt Giải trí về 0 trước, Dự phòng giữ nguyên (trước đó vòng
    chặt cắt Dự phòng 500.000 ₫, "optimal"). Thu nhập không đủ sàn thì vẫn vô nghiệm như trước, Dự phòng vẫn bị lấy cho sàn thiết yếu."""
    kw = {"an_uong_floor": 5_000_000, "income": income, "trip": False}
    held, plain = optimize(held_problem(hold=True, **kw)), optimize(held_problem(hold=False, **kw))
    assert held.status == status and plain.status == ("optimal" if status == "relaxed" else status)
    assert all(o.floor_gap_vnd == 0 for o in held.jars) == (status == "relaxed")
    if status == "relaxed":
        assert prop(plain, "du_phong") < 2_000_000 and prop(held, "du_phong") == 2_000_000
        assert {(r.kind, r.jar_code) for r in held.relaxations} == {("discretionary_reduced", "giai_tri")}
    else:
        assert (proposals(held), held.relaxations) == (proposals(plain), plain.relaxations)
        assert prop(held, "du_phong") < 2_000_000


def test_khong_cho_noi_thi_giu_hu_dem_khong_lam_ca_kha_thi_thanh_vo_nghiem():
    """Không cho nới, Du lịch chỉ kịp hạn nếu lấy phần chia của Dự phòng chưa tới đích. Từ 26/11 chiều (#39: giữ hũ đệm đứng trên mức cần
    của mục tiêu, kể cả khi vì thế mà mục tiêu chưa khả thi): vô nghiệm vì mục tiêu không kịp, Dự phòng giữ nguyên, mọi sàn vẫn đủ (trước
    đó: giữ mà vô nghiệm thì trả nghiệm không giữ, Dự phòng bị cắt cho Du lịch)."""
    plain = optimize(held_problem(hold=False, allow=False))
    held = optimize(held_problem(hold=True, allow=False))
    assert plain.status == "optimal" and prop(plain, "du_phong") < 2_000_000
    assert held.status == "infeasible" and prop(held, "du_phong") == 2_000_000
    assert all(o.floor_gap_vnd == 0 for o in held.jars) and not held.outcome("du_lich").goal_on_track


def test_giu_hu_dem_khong_bao_gio_lam_bai_toan_te_hon_va_khong_cat_hu_dem_nhieu_hon():
    """Giữ hũ đệm không bao giờ làm thiếu sàn nghĩa vụ hay thiết yếu, không cắt hũ đệm nhiều hơn; vô nghiệm chỉ thêm khi mục tiêu không
    kịp (từ 26/11 chiều mục tiêu không lấy phần chia của hũ đệm chưa tới đích, #39)."""
    rng = np.random.default_rng(39)
    for _ in range(300):
        income = int(rng.integers(0, 30_000_000))
        kw = {
            "days": int(rng.integers(5, 400)),
            "remaining": int(rng.integers(0, 12_000_000)),
            "oblig_floor": int(rng.integers(0, 6_000_000)),
            "essential_floor": int(rng.integers(0, 5_000_000)),
        }
        allow = bool(rng.integers(0, 2))
        base = jars(**kw)
        held_jars = tuple(replace(j, hold_current=True) if j.code == "du_phong" else j for j in base)
        plain = optimize(AllocationProblem(income, base, P, allow_relaxation=allow))
        held = optimize(AllocationProblem(income, held_jars, P, allow_relaxation=allow))
        assert total(held) == income and all(j.proposed_vnd >= 0 for j in held.jars)
        held_gaps, plain_gaps = (sum(o.floor_gap_vnd for o in s.jars) for s in (held, plain))
        assert held_gaps <= plain_gaps + STEP, (income, kw, allow)
        if held.status == "infeasible" and plain.status != "infeasible":
            assert held_gaps == 0 and not held.outcome("du_lich").goal_on_track, (income, kw, allow)
        assert prop(held, "du_phong") >= prop(plain, "du_phong") - STEP, (income, kw, allow)


def built_for(w, goal_args=()):
    engine = AllocationEngine(pipe(w))
    gathered = engine.resilience.gather(USER, NOW)
    built = engine.build(gathered, horizon_months=3, goal_args=list(goal_args), shock_id=None, allow_relaxation=True)
    return gathered, built, {j.code: j for j in built.problem.jars}


def without_hold(problem: AllocationProblem) -> AllocationProblem:
    return replace(problem, jars=tuple(replace(j, hold_current=False) for j in problem.jars))


def with_balance(w, code: str, balance: int):
    w.jars = [(c, k, balance if c == code else b, s, o, gv, gd) for c, k, b, s, o, gv, gd in w.jars]
    return w


def test_dich_tu_tinh_cua_hu_dem_la_so_thang_chi_thiet_yeu():
    """Hũ đệm không có đích trong lượt này: đích là `buffer_target_months` tháng chi thiết yếu (BR-64, C-13) = nghĩa vụ cứng (thiết yếu,
    nợ) quy về tháng cộng mức chi thiết yếu hằng tháng, cùng các số LP dùng cho sàn (chưa nhân `essential_floor_percent`). Từ 26/11 tối
    mức chi thiết yếu là mức nền bền (trung vị chi theo tuần, #39), không chi trung bình 30 ngày gần nhất."""
    from yofina_core.spend_baseline import BaselineSettings, typical_monthly

    gathered, built, by = built_for(purposed())
    spend = {j["code"]: j["spend"] for j in gathered.ctx.jars}
    base = BaselineSettings(P.spend_baseline_weeks, P.spend_baseline_min_weeks, P.month_days, 30)
    essential = sum(typical_monthly(spend[c], base).monthly_vnd for c in ("an_uong", "di_lai"))
    hard = 2_000_000 + 375_000 + round(1_000_000 / 3)  # tiền thuê phòng, tiền điện, Trả sau một lần chia 3 tháng
    assert P.buffer_target_months > 0
    assert built.buffer_target_vnd == round(P.buffer_target_months * (hard + essential))
    assert gathered.jar_rows[4]["balance_vnd"] < built.buffer_target_vnd and by["du_phong"].hold_current
    assert [c for c, j in by.items() if j.hold_current] == ["du_phong"]


def test_vi_co_du_phong_duoi_dich_khong_cat_du_phong_de_tang_du_lich():
    _, built, _ = built_for(purposed())
    plain, held = optimize(without_hold(built.problem)), optimize(built.problem)
    assert goal_up_while_buffer_cut(plain, built.problem, "du_phong") == ["du_lich"]  # hành vi cũ
    assert goal_up_while_buffer_cut(held, built.problem, "du_phong") == []
    assert prop(held, "du_phong") > prop(plain, "du_phong")
    assert held.status != "infeasible" and all(o.floor_gap_vnd == 0 for o in held.jars)


def test_vi_co_du_phong_da_dat_dich_thi_duoc_giam_nhu_cu():
    _, first, _ = built_for(purposed())
    w = with_balance(purposed(), "du_phong", first.buffer_target_vnd)
    _, built, by = built_for(w)
    assert not by["du_phong"].hold_current
    sol = optimize(built.problem)
    assert proposals(sol) == proposals(optimize(without_hold(built.problem)))
    assert prop(sol, "du_phong") < by["du_phong"].current_vnd  # đủ đích rồi thì cắt được như trước
    out = AllocationEngine(pipe(w)).optimize(USER, {})
    assert not errors_of(RESULT, out), errors_of(RESULT, out)


def test_dich_nguoi_dung_neu_thay_dich_tu_tinh():
    # đích 3 triệu, số dư 2 triệu: chưa tới đích thì giữ; đích 1,5 triệu: đã tới đích (dù chưa đủ số tháng chi thiết yếu) thì không giữ
    _, built, by = built_for(purposed(), [buffer_goal()])
    assert built.buffer_target_vnd == 3_000_000 and by["du_phong"].hold_current
    _, built, by = built_for(purposed(), [buffer_goal(1_500_000)])
    assert built.buffer_target_vnd == 1_500_000 and not by["du_phong"].hold_current


def test_vi_bay_hu_cu_hu_du_phong_theo_quy_tac_tuong_thich_cung_duoc_giu():
    # ví cũ `purpose` NULL: hũ tiết kiệm không mục tiêu là hũ đệm (`emergency_jar`); có đích trong lượt này thì vẫn là vai mục tiêu
    _, built, by = built_for(world())
    assert by["du_phong"].role == "emergency" and by["du_phong"].hold_current and not by["du_lich"].hold_current
    held = optimize(built.problem)
    assert goal_up_while_buffer_cut(held, built.problem, "du_phong") == []
    _, built, by = built_for(world(), [buffer_goal()])
    assert by["du_phong"].role == "goal" and not by["du_phong"].hold_current


def test_nhieu_hu_dem_thi_chi_giu_hu_dem_dau_tien_theo_thu_tu():
    _, _, by = built_for(purposed(purposes={"du_lich": "buffer"}))
    assert by["du_lich"].role == by["du_phong"].role == "emergency"
    assert by["du_lich"].hold_current and not by["du_phong"].hold_current


@pytest.mark.parametrize("code", ["du_phong", "quy_khan_cap"])
def test_vi_ba_hu_giu_du_phong_theo_purpose_va_san_nghia_vu_van_thang(code):
    def rent(amount):
        return {**NETFLIX, "id": "00000000-0000-0000-0000-0000000000a5", "kind": "rent", "name": "Tiền trọ", "amount_vnd": amount,
                "due_date": "2026-12-06", "due_day": 6, "pay_jar_code": "nghia_vu"}  # fmt: skip

    # tiền trọ 2.000.000 ₫ vừa phần Nghĩa vụ: đích tự tính 3 tháng x 2.000.000 ₫, Dự phòng 500.000 ₫ chưa tới nên được giữ
    _, built, by = built_for(three_jar_world(rent(2_000_000), buffer_code=code))
    assert built.buffer_target_vnd == round(P.buffer_target_months * 2_000_000)
    assert by[code].hold_current and by[code].role == "emergency"
    sol = optimize(built.problem)
    assert sol.status == "optimal" and prop(sol, code) == by[code].current_vnd
    # tiền trọ 7.500.000 ₫ vượt phần Nghĩa vụ: Dự phòng vẫn bị cắt cho sàn nghĩa vụ. Từ 26/11 chiều (#39, thứ tự ưu tiên chốt: giữ hũ
    # đệm đứng trên sàn chi) Chi hằng ngày nhường hết, kể cả phần dưới sàn chi, trước khi Dự phòng bị cắt (trước đó: y hệt khi không giữ,
    # Dự phòng về 0 trong khi Chi hằng ngày còn)
    _, built, by = built_for(three_jar_world(rent(7_500_000), buffer_code=code))
    assert by[code].hold_current and by["chi_hang_ngay"].spend_floor_vnd > 0
    held, plain = optimize(built.problem), optimize(without_hold(built.problem))
    assert held.status == plain.status == "relaxed"
    assert prop(held, "chi_hang_ngay") == 0 and prop(plain, "chi_hang_ngay") > 0
    assert prop(plain, code) < prop(held, code) < by[code].current_vnd
    assert held.outcome("nghia_vu").floor_gap_vnd == 0


def test_lam_tron_khong_bien_hu_dem_dang_giu_hay_muc_can_da_du_thanh_hut():
    """Số như LP mặc định của `minh` trên ví demo: vòng nới đủ mức cần theo hạn gốc của Du lịch và giữ Dự phòng, nhưng làm tròn sàn
    Nghĩa vụ lên bội 1.000 ₫ làm thừa vài trăm đồng. Phần thừa không lấy từ Dự phòng đang giữ hay Đi lại (LP không cắt hai hũ này), cũng
    không làm Du lịch thành "lùi hạn": hũ LP đã cắt (Chi hằng ngày) nhận phần đó."""
    trip = GoalSpec("muc_tieu", 4_200_000, 131, 6_000_000, date(2027, 4, 1))
    problem = AllocationProblem(
        9_000_000,
        (
            JarSpec("chi_hang_ngay", "discretionary", 270_000),
            JarSpec("nghia_vu", "obligation", 2_970_000, 3_170_733, "obligation"),
            JarSpec("du_phong", "emergency", 900_000, hold_current=True),
            JarSpec("an_uong", "essential", 2_700_000, 3_114_400),
            JarSpec("di_lai", "essential", 630_000, 471_200),
            JarSpec("giai_tri", "discretionary", 630_000, 180_000),
            JarSpec("muc_tieu", "goal", 900_000, goal=trip),
            JarSpec("dau_tu", "saving", 0),
        ),
        P,
    )
    sol = optimize(problem)
    assert sol.status == "relaxed" and total(sol) == 9_000_000
    assert prop(sol, "du_phong") == 900_000 and sol.outcome("muc_tieu").goal_on_track
    assert prop(sol, "di_lai") == 630_000 and prop(sol, "chi_hang_ngay") < 270_000
    assert {r.kind for r in sol.relaxations} == {"discretionary_reduced"}
    assert goal_up_while_buffer_cut(sol, problem, "du_phong") == []


# =====================================================================================
# Mục tiêu không có hạn (V2 của báo cáo rà soát #39): không gán hạn ngầm, không có mức cần cứng
# =====================================================================================
def no_deadline_jars(goal_spec: GoalSpec) -> tuple[JarSpec, ...]:
    return (
        JarSpec("nghia_vu", "obligation", 3_000_000, 3_000_000, "obligation"),
        JarSpec("an_uong", "essential", 3_000_000, 2_400_000),
        JarSpec("giai_tri", "discretionary", 1_000_000, spend_floor_vnd=300_000),
        JarSpec("quy_cuoi", "goal", 1_000_000, goal=goal_spec),
        JarSpec("du_phong", "emergency", 1_000_000),
    )


def test_muc_tieu_khong_co_han_khong_dat_muc_can_cung_va_khong_ep_hu_khac():
    """Quỹ cưới 150 triệu chưa biết khi nào: trước đây coi như hạn 3 tháng (cần 50 triệu mỗi tháng, ép mọi hũ xuống sàn). Nay không có
    mức cần: hũ mục tiêu giữ phần chia hiện tại theo thứ tự cắt, không nới gì, mục tiêu không bị coi là trễ hạn; ngày dự kiến tới đích
    theo mức đề xuất vẫn có."""
    undated = GoalSpec("quy_cuoi", 150_000_000, None, 150_000_000, None)
    sol = optimize(AllocationProblem(9_000_000, no_deadline_jars(undated), P))
    assert sol.status == "optimal" and not sol.relaxations and total(sol) == 9_000_000
    out = sol.outcome("quy_cuoi")
    assert (out.needed_vnd, out.goal_on_track, out.goal_shortfall_vnd) == (0, True, 0)
    assert prop(sol, "quy_cuoi") == 1_000_000 and prop(sol, "giai_tri") == 1_000_000
    assert out.days_to_goal == 150_000_000 * P.month_days // 1_000_000
    assert goal_need_vnd(undated, P.month_days) == 0
    # cùng mục tiêu với hạn 3 tháng (cách tính cũ khi không có hạn): ép Giải trí xuống sàn chi, mục tiêu vẫn không kịp
    dated = optimize(AllocationProblem(9_000_000, no_deadline_jars(replace(undated, days_left=90)), P))
    assert dated.status == "infeasible" and prop(dated, "giai_tri") == 300_000


def test_engine_muc_tieu_nguoi_dung_noi_khong_co_han_thi_bao_chua_co_han():
    """Lượt lập lộ trình với mục tiêu không hạn trên hũ chưa có hạn: phương án không đặt mức cần, kết quả không có `target_date` (cờ có
    cấu trúc "chưa có hạn" cho agent hỏi lại), tiêu đề nói chưa có hạn thay vì "kịp hạn"."""
    res, _ = run({"goals": [{"jar": "du_lich", "target_vnd": 150_000_000}]}, goal=False)
    assert not errors_of(RESULT, res), errors_of(RESULT, res)
    d = AllocationPlanData.model_validate(res["data"])
    (g,) = d.goals
    assert g.jar.code == "du_lich" and g.target_date is None
    assert (g.monthly_needed_vnd, g.on_track, g.shortfall_vnd) == (0, True, 0)
    assert not any(r.kind == "goal_delayed" for r in d.relaxations) and d.status != "infeasible"
    assert "chưa có hạn" in d.headline and "kịp hạn" not in d.headline
    # mục tiêu đã khai có hạn thì vẫn theo hạn đó như trước
    dated, _ = run({"goals": [{"jar": "du_lich", "target_vnd": 9_000_000}]})
    assert dated["data"]["goals"][0]["target_date"] == "2027-04-01" and dated["data"]["goals"][0]["monthly_needed_vnd"] > 0
