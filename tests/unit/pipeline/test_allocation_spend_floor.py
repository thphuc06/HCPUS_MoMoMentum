"""Sàn chi theo mức chi thật gần đây (issue #39, quyết định 26/11): lộ trình và đề xuất không cắt một hũ chi dưới `spending_keep_ratio` x
mức chi điển hình mỗi tháng của chính hũ đó (cùng số LP đã dùng: chi trung bình `resilience_window_days` ngày gần nhất quy về tháng).

Thứ tự ưu tiên khi không đủ chỗ, từ cứng tới mềm: sàn nghĩa vụ và sàn thiết yếu > giữ hũ đệm chưa tới đích > sàn chi (mới) > mức cần
của mục tiêu > phần còn lại. Mục tiêu không lấy được tiền dưới sàn chi (mục tiêu lùi hạn hoặc chưa khả thi), còn nghĩa vụ và chi thiết
yếu thì lấy được (sàn chi nhường, ví đang trả đủ nghĩa vụ không thành vô nghiệm). Dùng solver THẬT."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import numpy as np
import pytest
from pipeline_helpers import APP_DATE, NOW, context_rows, jar_row
from test_allocation import RESULT, STEP, prop, total
from test_resilience import USER, World, _ledger_obligation, errors_of, pipe, world

from yofina_core.config import Config
from yofina_core.roadmap import AllocationPlanData
from yofina_core.spend_baseline import BaselineSettings, typical_monthly
from yofina_forecast.allocation import AllocationEngine
from yofina_forecast.resilience import variable_monthly_spend
from yofina_forecast.settings import DEFAULT_ALLOCATION_PARAMS as P
from yofina_forecast.settings import ForecastSettings
from yofina_ml.allocation import AllocationProblem, GoalSpec, JarSpec, Relaxation, optimize

INCOME = 9_000_000
#: mức nền bền (#39, chốt 26/11 tối): sàn chi và sàn thiết yếu tính từ đây, cùng hàm và tham số với LP
BASE = BaselineSettings(P.spend_baseline_weeks, P.spend_baseline_min_weeks, P.month_days, 30)


# =====================================================================================
# Bộ giải: từng bậc của thứ tự ưu tiên
# =====================================================================================
def tiers(*, oblig_floor=3_000_000, trip=None, hold=False, spend=True, allow=True):
    """Ví 9 triệu: Chi hằng ngày 600.000 ₫ (sàn chi 300.000 ₫), Giải trí 400.000 ₫ (Netflix 180.000 ₫, sàn chi 250.000 ₫), Du lịch,
    Dự phòng 1.000.000 ₫ mỗi tháng; Ăn uống, Nghĩa vụ đang đúng bằng sàn. `spend=False`: cùng ví nhưng chưa có sàn chi (hành vi trước
    26/11 chiều)."""
    floors = {"chi_hang_ngay": 300_000, "giai_tri": 250_000} if spend else {}
    return AllocationProblem(
        INCOME,
        (
            JarSpec("nghia_vu", "obligation", 3_000_000, oblig_floor, "obligation"),
            JarSpec("an_uong", "essential", 3_000_000, 3_000_000),
            JarSpec("chi_hang_ngay", "discretionary", 600_000, spend_floor_vnd=floors.get("chi_hang_ngay", 0)),
            JarSpec("giai_tri", "discretionary", 400_000, 180_000, spend_floor_vnd=floors.get("giai_tri", 0)),
            JarSpec("du_lich", "goal", 1_000_000, goal=trip),
            JarSpec("du_phong", "emergency", 1_000_000, hold_current=hold),
        ),
        P,
        allow_relaxation=allow,
    )


def trip(remaining: int, days: int = 90) -> GoalSpec:
    return GoalSpec("du_lich", remaining, days, 6_000_000, None)


def kinds(sol) -> set[tuple[str, str]]:
    return {(r.kind, r.jar_code) for r in sol.relaxations}


@pytest.mark.parametrize(
    "allow,sinking_vnd,spend_vnd", [(False, 300_000, 200_000), (True, 500_000, 0)]
)
def test_nghia_vu_va_thiet_yeu_duoc_cat_phan_chia_quy_don(allow, sinking_vnd, spend_vnd):
    problem = AllocationProblem(
        5_000_000,
        (
            JarSpec("nghia_vu", "obligation", 2_000_000, 2_500_000, "obligation"),
            JarSpec("an_uong", "essential", 1_600_000, 2_000_000),
            JarSpec("quy_don", "saving", 1_000_000, hold_current=True),
            JarSpec("giai_tri", "discretionary", 400_000, spend_floor_vnd=300_000),
        ),
        P,
        allow_relaxation=allow,
    )
    sol = optimize(problem)
    assert (sol.status, sol.relaxation_rounds) == (("relaxed", 1) if allow else ("optimal", 0))
    assert total(sol) == problem.income_vnd and all(o.floor_gap_vnd == 0 for o in sol.jars)
    assert prop(sol, "quy_don") == sinking_vnd and prop(sol, "giai_tri") == spend_vnd


@pytest.mark.parametrize(
    "allow,sinking_vnd,spend_vnd", [(False, 600_000, 200_000), (True, 800_000, 0)]
)
def test_du_phong_chua_toi_dich_giu_truoc_quy_don(allow, sinking_vnd, spend_vnd):
    problem = AllocationProblem(
        1_800_000,
        (
            JarSpec("du_phong", "emergency", 1_000_000, hold_current=True),
            JarSpec("quy_don", "saving", 1_000_000, hold_current=True),
            JarSpec("giai_tri", "discretionary", 400_000),
        ),
        P,
        allow_relaxation=allow,
    )
    sol = optimize(problem)
    assert (sol.status, sol.relaxation_rounds) == (("relaxed", 1) if allow else ("optimal", 0))
    assert prop(sol, "du_phong") == 1_000_000
    assert prop(sol, "quy_don") == sinking_vnd and prop(sol, "giai_tri") == spend_vnd


@pytest.mark.parametrize("allow", [False, True], ids=["strict", "relaxed"])
def test_quy_don_co_khoan_sap_can_giu_truoc_san_chi(allow):
    problem = AllocationProblem(
        1_200_000,
        (
            JarSpec("quy_don", "saving", 1_000_000, hold_current=True),
            JarSpec("giai_tri", "discretionary", 400_000, spend_floor_vnd=300_000),
        ),
        P,
        allow_relaxation=allow,
    )
    sol = optimize(problem)
    assert prop(sol, "quy_don") == 1_000_000 and prop(sol, "giai_tri") == 200_000
    assert (sol.status, sol.relaxation_rounds) == (("relaxed", 1) if allow else ("optimal", 0))
    assert kinds(sol) == ({("discretionary_reduced", "giai_tri")} if allow else set())


@pytest.mark.parametrize("remaining,status", [(3_000_000, "relaxed"), (9_000_000, "infeasible")])
def test_quy_don_co_khoan_sap_can_giu_truoc_muc_tieu_du_lich(remaining, status):
    travel = replace(
        trip(remaining), target_vnd=remaining, target_date=APP_DATE + timedelta(days=90)
    )
    problem = AllocationProblem(
        1_500_000,
        (
            JarSpec("quy_don", "saving", 1_000_000, hold_current=True),
            JarSpec("du_lich", "goal", 500_000, goal=travel),
        ),
        P,
    )
    strict = optimize(replace(problem, allow_relaxation=False))
    relaxed = optimize(problem)
    assert strict.status == "infeasible" and not strict.relaxations
    assert (relaxed.status, relaxed.relaxation_rounds) == (status, 1)
    assert kinds(relaxed) == {("goal_delayed", "du_lich")}
    for sol in (strict, relaxed):
        assert prop(sol, "quy_don") == 1_000_000 and prop(sol, "du_lich") == 500_000
        assert not sol.outcome("du_lich").goal_on_track


def test_muc_tieu_co_han_xep_truoc_tich_luy_dai_han():
    travel = replace(trip(3_000_000), target_date=APP_DATE + timedelta(days=90))
    problem = AllocationProblem(
        1_500_000,
        (
            JarSpec("dau_tu", "saving", 1_000_000),
            JarSpec("du_lich", "goal", 500_000, goal=travel),
        ),
        P,
    )
    sol = optimize(problem)
    assert (sol.status, sol.relaxation_rounds) == ("optimal", 0)
    assert prop(sol, "du_lich") == 1_000_000 and sol.outcome("du_lich").goal_on_track
    assert prop(sol, "dau_tu") == 500_000


@pytest.mark.parametrize(
    "remaining,days,budget,status,rounds,shares,unallocated,goal_values",
    [
        # Ca thứ 21 của bài toán ngẫu nhiên bên dưới (seed 39).
        pytest.param(
            563_405,
            217,
            (12_243_185, 3_562_852, 312_799, 473_456),
            "optimal",
            0,
            (3_562_852, 3_000_000, 600_000, 473_456, 1_000_000, 1_000_000),
            2_606_877,
            (77_891, True, 0, 17),
            id="optimal",
        ),
        pytest.param(
            4_800_000,
            90,
            (9_000_000, 3_000_000, 300_000, 250_000),
            "relaxed",
            1,
            (3_000_000, 3_000_000, 300_000, 250_000, 1_450_000, 1_000_000),
            0,
            (1_600_000, False, 450_000, 100),
            id="relaxed",
        ),
        pytest.param(
            12_000_000,
            30,
            (9_000_000, 3_000_000, 300_000, 250_000),
            "infeasible",
            1,
            (3_000_000, 3_000_000, 300_000, 250_000, 1_450_000, 1_000_000),
            0,
            (12_000_000, False, 10_550_000, 249),
            id="infeasible",
        ),
    ],
)
def test_phan_bo_khong_co_quy_don_giu_nguyen_so_tien(
    remaining, days, budget, status, rounds, shares, unallocated, goal_values
):
    # Ghi từ solver gốc 907252e với cùng ví: có sàn chi, giữ Dự phòng, Du lịch có hạn.
    income, oblig_floor, daily_floor, leisure_floor = budget
    base = tiers(oblig_floor=oblig_floor, trip=trip(remaining, days), hold=True)
    floors = {"chi_hang_ngay": daily_floor, "giai_tri": leisure_floor}
    jars = tuple(replace(j, spend_floor_vnd=floors.get(j.code, 0)) for j in base.jars)
    sol = optimize(replace(base, income_vnd=income, jars=jars))
    assert (sol.status, sol.relaxation_rounds) == (status, rounds)
    assert tuple(o.proposed_vnd for o in sol.jars) == shares
    assert sol.unallocated_vnd == unallocated and sol.floor_gap_total_vnd == 0
    for out in sol.jars:
        assert out.floor_gap_vnd == 0
        expected = goal_values if out.code == "du_lich" else (0, True, 0, None)
        assert (
            out.needed_vnd,
            out.goal_on_track,
            out.goal_shortfall_vnd,
            out.days_to_goal,
        ) == expected
    assert sol.relaxations == (
        ()
        if status == "optimal"
        else (Relaxation("goal_delayed", "du_lich", goal_values[0], 1_450_000, delay_months=6),)
    )


def test_muc_tieu_khong_lay_tien_duoi_san_chi_ma_lui_han():
    # Du lịch cần 1.600.000 ₫/tháng (đang 1.000.000 ₫), Dự phòng đang giữ. Chưa có sàn chi: vòng nới cắt Chi hằng ngày dưới mức đó để kịp
    # hạn (hiện tượng Chi hằng ngày 3% -> 0,47% của `minh`)
    plain = optimize(tiers(trip=trip(4_800_000), hold=True, spend=False))
    assert plain.status == "relaxed" and plain.outcome("du_lich").goal_on_track
    assert prop(plain, "chi_hang_ngay") < 300_000
    # có sàn chi: Chi hằng ngày và Giải trí chỉ xuống tới sàn chi, Du lịch không kịp hạn gốc mà lùi hạn
    sol = optimize(tiers(trip=trip(4_800_000), hold=True))
    assert sol.status == "relaxed" and total(sol) == INCOME
    assert prop(sol, "chi_hang_ngay") == 300_000 and prop(sol, "giai_tri") == 250_000
    assert not sol.outcome("du_lich").goal_on_track
    assert kinds(sol) == {("goal_delayed", "du_lich")}
    assert prop(sol, "du_phong") == 1_000_000 and all(o.floor_gap_vnd == 0 for o in sol.jars)


def test_muc_tieu_lui_han_van_khong_du_thi_chua_kha_thi_khong_cat_san_chi():
    # Du lịch cần 12.000.000 ₫ trong 30 ngày: lùi 6 tháng vẫn cần 1.714.286 ₫/tháng, chỉ đủ nếu cắt dưới sàn chi
    plain = optimize(tiers(trip=trip(12_000_000, 30), hold=True, spend=False))
    assert plain.status == "relaxed"
    sol = optimize(tiers(trip=trip(12_000_000, 30), hold=True))
    assert sol.status == "infeasible" and sol.floor_gap_total_vnd == 0
    assert prop(sol, "chi_hang_ngay") >= 300_000 and prop(sol, "giai_tri") >= 250_000
    assert not sol.outcome("du_lich").goal_on_track and total(sol) == INCOME


def test_nghia_vu_lay_duoc_tien_duoi_san_chi_va_khong_thanh_vo_nghiem():
    # khoản vay mới đẩy sàn Nghĩa vụ lên 5.700.000 ₫ (+2.700.000 ₫): hết phần trên sàn chi, Du lịch, Dự phòng (không giữ) mới tới sàn chi
    sol = optimize(tiers(oblig_floor=5_700_000))
    assert sol.status == "relaxed" and all(o.floor_gap_vnd == 0 for o in sol.jars) and total(sol) == INCOME
    assert prop(sol, "chi_hang_ngay") + prop(sol, "giai_tri") == 300_000 + 250_000 - 250_000
    assert prop(sol, "giai_tri") >= 180_000  # sàn khoản định kỳ (Netflix) vẫn đứng trên sàn chi
    assert {c for k, c in kinds(sol) if k == "discretionary_reduced"} <= {"chi_hang_ngay", "giai_tri"}
    assert ("discretionary_reduced", "chi_hang_ngay") in kinds(sol)
    assert prop(sol, "du_lich") == 0 and prop(sol, "du_phong") == 0


def test_sau_san_chi_nhuong_thi_tra_dung_trang_thai_nhu_truoc():
    # sàn nghĩa vụ vượt cả thu nhập: vẫn vô nghiệm như khi chưa có sàn chi, phần thiếu rơi vào cùng chỗ
    sol, plain = optimize(tiers(oblig_floor=9_500_000)), optimize(tiers(oblig_floor=9_500_000, spend=False))
    assert sol.status == plain.status == "infeasible"
    assert {o.code: o.floor_gap_vnd for o in sol.jars} == {o.code: o.floor_gap_vnd for o in plain.jars}


def test_san_thiet_yeu_lay_duoc_tien_duoi_san_chi():
    problem = tiers()
    eat = replace(problem.jars[1], floor_vnd=5_500_000)  # sàn thiết yếu +2.500.000 ₫
    sol = optimize(replace(problem, jars=(problem.jars[0], eat, *problem.jars[2:])))
    assert sol.status == "relaxed" and all(o.floor_gap_vnd == 0 for o in sol.jars)
    assert prop(sol, "chi_hang_ngay") + prop(sol, "giai_tri") == 300_000 + 250_000 - 50_000


def test_giu_hu_dem_dung_tren_san_chi():
    # nghĩa vụ cần thêm 1.700.000 ₫: Du lịch nhường 1.000.000 ₫, phần trên sàn chi 450.000 ₫, còn 250.000 ₫ lấy từ sàn chi chứ không từ
    # Dự phòng đang giữ (chưa tới đích); Dự phòng không giữ thì nhường trước sàn chi như trước
    held = optimize(tiers(oblig_floor=4_700_000, hold=True))
    assert held.status == "relaxed" and prop(held, "du_phong") == 1_000_000
    assert prop(held, "chi_hang_ngay") + prop(held, "giai_tri") == 300_000 + 250_000 - 250_000
    plain = optimize(tiers(oblig_floor=4_700_000))
    assert plain.status == "optimal" and prop(plain, "du_phong") == 750_000
    assert prop(plain, "chi_hang_ngay") >= 300_000 and prop(plain, "giai_tri") >= 250_000


def test_giu_hu_dem_dung_tren_muc_can_cua_muc_tieu_ca_khi_muc_tieu_chua_kha_thi():
    # Du lịch cần 12.000.000 ₫ trong 30 ngày, Dự phòng chưa tới đích: mục tiêu chưa khả thi, không lấy phần chia của Dự phòng (trước
    # 26/11 chiều: giữ mà vô nghiệm thì bỏ giữ, Du lịch lấy tiền của Dự phòng)
    sol = optimize(tiers(trip=trip(12_000_000, 30), hold=True))
    assert sol.status == "infeasible" and prop(sol, "du_phong") == 1_000_000
    assert prop(sol, "chi_hang_ngay") >= 300_000 and prop(sol, "giai_tri") >= 250_000


def test_vo_nghiem_du_da_nhuong_het_thi_san_chi_khong_nhuong_cho_san_thiet_yeu():
    """Như cảnh 4: sàn thiết yếu của Ăn uống (80% mức chi vừa tăng vọt) lớn tới mức nhường hết mọi thứ ví vẫn vô nghiệm. Nhường sàn chi khi
    đó không cứu được ví mà chỉ đưa hũ chi về 0 (bước "Giảm Chi hằng ngày 270.000 → 0 ₫"), nên sàn chi giữ; tiền để dành (Du lịch, Dự
    phòng) vẫn nhường cho chi thiết yếu. Nghĩa vụ cứng vượt thu nhập thì sàn chi vẫn nhường cho nghĩa vụ."""
    problem = tiers(hold=True)
    eat = replace(problem.jars[1], floor_vnd=9_000_000)
    sol = optimize(replace(problem, jars=(problem.jars[0], eat, *problem.jars[2:])))
    assert sol.status == "infeasible" and sol.outcome("an_uong").floor_gap_vnd > 0
    assert sol.outcome("nghia_vu").floor_gap_vnd == 0 and total(sol) == INCOME
    assert prop(sol, "chi_hang_ngay") == 300_000 and prop(sol, "giai_tri") == 250_000
    assert prop(sol, "du_phong") == 0 and prop(sol, "du_lich") == 0
    debt = optimize(tiers(oblig_floor=9_500_000, hold=True))
    assert debt.status == "infeasible" and prop(debt, "chi_hang_ngay") == prop(debt, "giai_tri") == 0
    assert prop(debt, "nghia_vu") == INCOME


def test_san_chi_khong_bi_lam_tron_mat():
    problem = tiers(trip=trip(4_800_000))
    odd = tuple(replace(j, spend_floor_vnd=300_333) if j.code == "chi_hang_ngay" else j for j in problem.jars)
    sol = optimize(replace(problem, jars=odd))
    assert prop(sol, "chi_hang_ngay") >= 300_333 and total(sol) == INCOME


def test_khong_cho_noi_thi_san_chi_nhuong_cho_nghia_vu_ma_khong_vo_nghiem():
    # +2.480.000 ₫ cho Nghĩa vụ: vòng chặt chỉ đủ nếu Giải trí xuống dưới sàn chi (Chi hằng ngày đã ở mức cắt tối đa của vòng chặt)
    assert optimize(tiers(oblig_floor=5_480_000, spend=False, allow=False)).status == "optimal"
    sol = optimize(tiers(oblig_floor=5_480_000, allow=False))
    assert sol.status == "optimal" and all(o.floor_gap_vnd == 0 for o in sol.jars)
    assert prop(sol, "giai_tri") < 250_000


def test_bai_toan_ngau_nhien_luon_co_nghiem_hoac_dung_trang_thai():
    """300 bài toán: tiền bảo toàn; sàn chi không bao giờ tạo phần thiếu sàn nghĩa vụ hay thiết yếu (ca không có sàn chi đạt mọi sàn thì
    ca có sàn chi cũng đạt); `optimal` giữ đủ sàn chi; hũ bị cắt dưới sàn chi được ghi là điều đã nới; vô nghiệm chỉ thêm khi mục tiêu
    không kịp."""
    rng = np.random.default_rng(39)
    seen = {"optimal": 0, "relaxed": 0, "infeasible": 0}
    for _ in range(300):
        income = int(rng.integers(0, 14_000_000))
        remaining, days = int(rng.integers(0, 12_000_000)), int(rng.integers(5, 400))
        oblig = int(rng.integers(0, 8_000_000))
        hold, allow = bool(rng.integers(0, 2)), bool(rng.integers(0, 3))
        base = tiers(oblig_floor=oblig, trip=trip(remaining, days), hold=hold, allow=allow)
        floors = {"chi_hang_ngay": int(rng.integers(0, 700_000)), "giai_tri": int(rng.integers(0, 500_000))}
        jars = tuple(replace(j, spend_floor_vnd=floors.get(j.code, 0)) for j in base.jars)
        problem = replace(base, income_vnd=income, jars=jars)
        sol = optimize(problem)
        plain = optimize(replace(problem, jars=tuple(replace(j, spend_floor_vnd=0) for j in jars)))
        seen[sol.status] += 1
        tag = (income, remaining, days, oblig, hold, allow, floors)
        assert total(sol) == income and all(j.proposed_vnd >= 0 for j in sol.jars), tag
        assert sol.relaxation_rounds == (0 if sol.status == "optimal" else 1), tag
        gaps, plain_gaps = (sum(o.floor_gap_vnd for o in s.jars) for s in (sol, plain))
        oblig_gap, plain_oblig_gap = (s.outcome("nghia_vu").floor_gap_vnd for s in (sol, plain))
        # sàn chi không làm thiếu sàn ở ví mà khi chưa có sàn chi đạt mọi sàn, và không bao giờ lấy tiền của nghĩa vụ cứng
        if plain_gaps == 0:
            assert gaps == 0, tag
        assert oblig_gap <= plain_oblig_gap + STEP, tag
        if plain.status == "infeasible" and plain_gaps > 0:
            assert sol.status == "infeasible", tag
        if sol.status in ("optimal", "relaxed"):
            assert gaps == 0, tag
        if sol.status == "optimal" and problem.allow_relaxation:
            assert not sol.relaxations and all(prop(sol, c) >= f for c, f in floors.items()), tag
        current = {j.code: j.current_vnd for j in jars}
        cut = {c for c, f in floors.items() if prop(sol, c) < min(f, current[c])}
        if sol.status == "relaxed":
            assert cut <= {r.jar_code for r in sol.relaxations if r.kind == "discretionary_reduced"}, tag
        if sol.status == "infeasible" and plain.status != "infeasible" and problem.allow_relaxation:
            assert gaps == 0 and not sol.outcome("du_lich").goal_on_track, tag
        if hold and gaps == 0:
            assert prop(sol, "du_phong") >= prop(plain, "du_phong") - STEP, tag
    assert all(seen.values()), seen


# =====================================================================================
# Dựng bài toán từ dữ liệu người dùng (Lambda forecast)
# =====================================================================================
def built(w, **kw):
    engine = AllocationEngine(pipe(w, **kw))
    gathered = engine.resilience.gather(USER, NOW)
    problem = engine.build(gathered, horizon_months=3, goal_args=[], shock_id=None, allow_relaxation=True).problem
    return gathered, {j.code: j for j in problem.jars}


def test_san_chi_la_ti_le_giu_nhan_muc_chi_dien_hinh_cua_chinh_hu():
    gathered, by = built(world())
    spend = {j["code"]: j["spend"] for j in gathered.ctx.jars}
    # mức gốc của sàn chi là mức nền bền (trung vị chi theo tuần, 26/11 tối): Giải trí chi 60.000 ₫ mỗi sáu ngày nên tuần điển hình là
    # 60.000 ₫, tức 257.143 ₫ mỗi tháng (trước: chi trung bình 30 ngày 300.000 ₫)
    level = typical_monthly(spend["giai_tri"], BASE)
    assert variable_monthly_spend(spend["giai_tri"], 30, P.month_days) == 300_000
    assert level.robust and level.monthly_vnd == 257_143 and P.spending_keep_ratio == 0.5
    # Giải trí (không thiết yếu): nửa mức nền, không theo mã hũ hay persona
    assert by["giai_tri"].spend_floor_vnd == round(P.spending_keep_ratio * level.monthly_vnd)
    # hũ chi thiết yếu cũng có sàn chi theo cùng quy tắc nhưng sàn thiết yếu (80%) đã cao hơn; hũ để dành, hũ nghĩa vụ không có
    for code in ("an_uong", "di_lai"):
        assert by[code].spend_floor_vnd == round(P.spending_keep_ratio * typical_monthly(spend[code], BASE).monthly_vnd)
        assert by[code].floor_vnd >= by[code].spend_floor_vnd
    assert by["du_lich"].spend_floor_vnd == by["du_phong"].spend_floor_vnd == by["nghia_vu"].spend_floor_vnd == 0


def test_san_chi_khong_vuot_phan_chia_hien_tai():
    # hũ đang được chia ít hơn nửa mức chi thật: sàn chi chỉ giữ không cắt thêm, không nâng hũ lên
    w = world()
    w.jars = [(c, k, b, 1 if c == "giai_tri" else s, o, gv, gd) for c, k, b, s, o, gv, gd in w.jars]
    w.jars = [(c, k, b, s + 9 if c == "du_phong" else s, o, gv, gd) for c, k, b, s, o, gv, gd in w.jars]
    _, by = built(w)
    assert by["giai_tri"].current_vnd == 90_000 and by["giai_tri"].spend_floor_vnd == 90_000


def test_chua_du_lich_su_thi_khong_ap_san_chi():
    # cùng cổng "ước lượng ban đầu" của dự báo (`cold_start_min_days`): 20 ngày lịch sử thì chưa có mức chi điển hình
    _, short = built(world(days=20))
    assert all(j.spend_floor_vnd == 0 for j in short.values())
    _, enough = built(world(days=21))
    assert enough["giai_tri"].spend_floor_vnd > 0
    _, gate = built(world(days=21), cold_start_min_days=30)
    assert all(j.spend_floor_vnd == 0 for j in gate.values())


def three_jar(daily_essential: int, *, days: int = 47, spend: list[int] | None = None):
    """Ví ba hũ: Chi hằng ngày nhận cả loại thiết yếu (`essential_spend`) và loại khác (tổng `spend`, mặc định 100.000 ₫ mỗi ngày)."""
    from test_allocation import NETFLIX

    rent = {**NETFLIX, "id": "00000000-0000-0000-0000-0000000000a5", "kind": "rent", "name": "Tiền trọ", "amount_vnd": 2_000_000,
            "due_date": "2026-12-06", "due_day": 6, "pay_jar_code": "nghia_vu"}  # fmt: skip
    jars = [
        ("chi_hang_ngay", "spending", 900_000, 42, 1, None, None),
        ("nghia_vu", "obligation", 1_000_000, 33, 2, None, None),
        ("du_phong", "saving", 500_000, 25, 3, None, None),
    ]
    ctx_jars = [jar_row(c, k, b, s, o, [0] * days) for c, k, b, s, o, _g, _d in jars]
    ctx_jars[0] = {**ctx_jars[0], "spend": spend or [100_000] * days, "essential_spend": [daily_essential] * days}
    w = World(context_rows(days=days, jars=ctx_jars, obligations=[dict(rent)]), jars, [_ledger_obligation(dict(rent))])
    rows = w.jar_state
    w.jar_state = lambda user_id: [{**r, "purpose": "buffer"} if r["code"] == "du_phong" else r for r in rows(user_id)]
    return w


@pytest.mark.parametrize("daily_essential", [0, 40_000, 80_000])
def test_vi_ba_hu_san_chi_hang_ngay_la_so_lon_hon_cua_san_thiet_yeu_va_san_chi(daily_essential):
    _, by = built(three_jar(daily_essential))
    daily = by["chi_hang_ngay"]
    essential = round(daily_essential * P.month_days * P.essential_floor_percent / 100)
    whole = round(P.spending_keep_ratio * 100_000 * P.month_days)
    assert (daily.floor_vnd, daily.spend_floor_vnd) == (essential, whole)
    res = AllocationEngine(pipe(three_jar(daily_essential))).optimize(USER, {})
    assert not errors_of(RESULT, res), errors_of(RESULT, res)
    line = next(x for x in res["data"]["lines"] if x["jar"]["code"] == "chi_hang_ngay")
    # sàn CỨNG ở `floor_vnd`; sàn chi là sàn mềm, đi riêng cùng mức chi thật gần đây (C3 của báo cáo rà soát #39). Sáu tuần lịch sử đã đủ
    # cho mức nền bền (26/11 tối; trước đó mức nền cần cả một cửa sổ 30 ngày trước cửa sổ gần nhất nên vắng)
    assert line["floor_vnd"] == essential
    assert line["recent_spend"] == {
        "recent_monthly_vnd": 100_000 * P.month_days, "keep_floor_vnd": whole, "baseline_monthly_vnd": 100_000 * P.month_days,
        "unusually_high": False, "change_confirmed": False,
    }  # fmt: skip


def test_muc_nen_ben_va_dot_chi_tang():
    """Mức nền là mức nền bền (trung vị chi theo tuần trên 12 tuần, #39 chốt 26/11 tối). Tháng gần nhất chi gấp ba mức nền thì có dữ kiện
    đợt tăng (cờ, từ ngày nào) để agent nói ra hoặc hỏi lại; chi đều thì không; dưới sáu tuần lịch sử thì không có mức nền. Sàn chi là tỷ
    lệ giữ x mức nền (trước 26/11 tối: x mức chi 30 ngày gần nhất, ca tăng gấp ba là 2.250.000 ₫)."""

    def recent(**kw):
        res = AllocationEngine(pipe(three_jar(0, **kw))).optimize(USER, {})
        assert not errors_of(RESULT, res), errors_of(RESULT, res)
        return next(x for x in res["data"]["lines"] if x["jar"]["code"] == "chi_hang_ngay")["recent_spend"]

    steady = recent(days=90)
    assert steady["baseline_monthly_vnd"] == steady["recent_monthly_vnd"] == 3_000_000 and not steady["unusually_high"]
    assert "high_since" not in steady
    spike = recent(days=90, spend=[50_000] * 60 + [150_000] * 30)
    assert (spike["recent_monthly_vnd"], spike["baseline_monthly_vnd"]) == (4_500_000, 1_500_000) and spike["unusually_high"]
    assert spike["keep_floor_vnd"] == min(round(P.spending_keep_ratio * 1_500_000), 3_780_000)
    # bốn tuần đủ của cửa sổ 30 ngày đều chi 1.050.000 ₫ (từ 525.000 ₫ là vượt ngưỡng): từ đầu tuần sớm nhất
    assert spike["high_since"] == (APP_DATE - timedelta(days=28)).isoformat() and not spike["change_confirmed"]
    assert P.spend_spike_ratio == 1.5
    short = recent(days=35)
    assert "baseline_monthly_vnd" not in short and not short["unusually_high"]


def test_vi_bay_hu_cu_giai_tri_giu_san_chi_khi_muc_tieu_can_tien():
    # ví bảy hũ cũ (`purpose` NULL), mục tiêu Du lịch gấp: trước đây vòng nới đưa Giải trí về 0; nay Giải trí giữ sàn chi, Du lịch lùi hạn
    args = {"goals": [{"jar": "du_lich", "target_vnd": 9_000_000, "target_date": "2027-02-01"}]}
    _, by = built(world())
    out = AllocationEngine(pipe(world())).optimize(USER, args)
    assert not errors_of(RESULT, out), errors_of(RESULT, out)
    d = AllocationPlanData.model_validate(out["data"])
    lines = {line.jar.code: line for line in d.lines}
    assert lines["giai_tri"].proposed_monthly_vnd >= by["giai_tri"].spend_floor_vnd > 0
    assert lines["giai_tri"].floor_vnd == by["giai_tri"].floor_vnd and not lines["giai_tri"].is_essential
    assert lines["giai_tri"].recent_spend is not None
    assert lines["giai_tri"].recent_spend.keep_floor_vnd == by["giai_tri"].spend_floor_vnd
    assert d.status in ("relaxed", "infeasible")
    assert any(r.kind == "goal_delayed" for r in d.relaxations) or d.status == "infeasible"


def test_san_chi_da_nhuong_cho_nghia_vu_thi_dong_phan_bo_van_bao_san_chi_goi_y():
    """Ví ba hũ khai thêm khoản vay 4.000.000 ₫: Nghĩa vụ cần thêm 3.030.000 ₫, Chi hằng ngày (3.780.000 ₫, sàn chi 1.500.000 ₫) nhường cả
    phần dưới sàn chi, Dự phòng chưa tới đích được giữ (giữ hũ đệm đứng trên sàn chi). `floor_vnd` chỉ là sàn cứng (ở đây 0), sàn chi gợi
    ý vẫn báo ở `recent_spend` để người lập lộ trình thấy hũ nhận ít hơn mức chi thật gần đây; `floor_gap_vnd` (sàn cứng) vẫn 0."""
    from test_allocation import NETFLIX

    w = three_jar(0)
    loan = {**NETFLIX, "id": "00000000-0000-0000-0000-0000000000a6", "kind": "loan", "name": "Khoản vay", "amount_vnd": 4_000_000,
            "pay_jar_code": "nghia_vu"}  # fmt: skip
    w.obl.append(_ledger_obligation(dict(loan)))
    _, by = built(w)
    assert by["du_phong"].hold_current and by["chi_hang_ngay"].spend_floor_vnd == 1_500_000
    out = AllocationEngine(pipe(w)).optimize(USER, {})
    assert not errors_of(RESULT, out), errors_of(RESULT, out)
    d = AllocationPlanData.model_validate(out["data"])
    lines = {x.jar.code: x for x in d.lines}
    daily = lines["chi_hang_ngay"]
    assert d.status == "relaxed" and all(x.floor_gap_vnd == 0 for x in d.lines)
    assert lines["du_phong"].proposed_monthly_vnd == lines["du_phong"].current_monthly_vnd
    assert daily.floor_vnd == by["chi_hang_ngay"].floor_vnd == 0
    assert daily.recent_spend is not None and daily.proposed_monthly_vnd < daily.recent_spend.keep_floor_vnd == 1_500_000
    assert {(r.kind, r.jar_code) for r in d.relaxations} == {("discretionary_reduced", "chi_hang_ngay")}


def test_ti_le_giu_doc_tu_cau_hinh():
    env = {
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
    assert ForecastSettings.from_config(Config(env=env)).allocation.spending_keep_ratio == 0.5
    over = ForecastSettings.from_config(Config(env={**env, "YOFINA_ALLOCATION_SPENDING_KEEP_RATIO": "0.7"}))
    assert over.allocation.spending_keep_ratio == 0.7
    w = world()
    _, by = built(w, allocation=over.allocation)
    assert by["giai_tri"].spend_floor_vnd == round(0.7 * 257_143)  # tỷ lệ giữ x mức nền bền của Giải trí (xem ca đầu)
