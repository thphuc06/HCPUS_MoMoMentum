"""Tối ưu phân bổ lương vào hũ (phase 4, F5) bằng `scipy.optimize.linprog` (HiGHS). HÀM THUẦN: không I/O, không đồng hồ.

Bài toán theo tháng (đơn vị nội bộ là `rounding_step_vnd` VND để HiGHS không phải xử lý số quá lớn):

    biến   x_j   tiền vào hũ j                      u   phần chưa phân bổ
           e_j   phần SÀN chưa đạt (elastic)        g_j phần mức cần của mục tiêu chưa đạt (cứng)
           h_j   phần mức cần ưa thích chưa đạt     d_j phần cắt xuống dưới mức hiện tại
    ràng buộc  sum_j x_j + u = thu nhập
               x_j + e_j >= sàn_j                   (sàn cứng của nghĩa vụ và khoản thiết yếu, qua biến elastic)
               x_j + g_j >= mức cần_j               (mục tiêu có hạn: cần đóng góp đủ mỗi tháng để kịp hạn)
               x_j + d_j >= mức hiện tại_j          (chia theo tỷ lệ đã khai; cắt xuống thì chịu phạt `d_j`)
    mục tiêu   min sum M_j e_j + M_goal sum g_j + sum w_j h_j + sum k_j d_j + eps sum x_j

- Sàn cứng KHÔNG đặt qua `bounds` mà qua `e_j` với mức phạt `M_j` theo ưu tiên (nghĩa vụ > thiết yếu), nên bài toán luôn có nghiệm và
  nếu thu nhập không đủ thì phần thiếu rơi vào hũ ưu tiên thấp trước (spike `s8_lp.py` ca 2b và 2c).
- Cắt xuống dưới mức hiện tại tốn `k_j` theo loại hũ (không thiết yếu < mục tiêu < thiết yếu < dự phòng), nên tiền để trả sàn và mục
  tiêu lấy từ hũ không thiết yếu trước.
- Hũ đệm (`emergency`) có thể mang mục tiêu (đích số dư của lượt lập lộ trình): phần thiếu của mức cần trên hũ đó phạt nặng hơn mục tiêu
  khác theo tỷ lệ `weight_emergency / weight_goal`, nên khi không đủ cho mọi mục tiêu thì hũ đệm được trước (BR-65).
- **Vòng 0** (chặt): hũ không thiết yếu chỉ được cắt tới `(1 - cắt tối đa) x mức hiện tại`; mục tiêu cần đủ mức cần để kịp hạn.
  Đạt (mọi `e_j` và `g_j` bằng 0) thì trạng thái `optimal`.
- **Nới ĐÚNG MỘT vòng** nếu vòng 0 không đạt: hũ không thiết yếu được cắt tới 0, mục tiêu chỉ cần đủ mức cần của hạn đã lùi
  `relax_delay_months` tháng (cứng) và mức cần của hạn gốc (mềm, phạt `h_j`). Đạt thì `relaxed` kèm điều đã nới (hũ không thiết yếu
  bị cắt sâu hơn vòng 0, mục tiêu phải lùi hạn). Vẫn không đạt thì `infeasible` (không nới thêm): người gọi nêu đúng hai lựa chọn.
- Tiền bảo toàn: tổng `x_j` đã làm tròn cộng `unallocated` đúng bằng thu nhập (phần dư làm tròn dồn vào hũ lớn nhất).

Mọi số (mức phạt, trọng số, mức cắt tối đa, số tháng lùi hạn, bước làm tròn) nằm ở `AllocationParams` do người gọi truyền (cấu hình).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

import numpy as np
from scipy.optimize import linprog

from yofina_ml.resilience import monthly_needed_vnd

Role = Literal["obligation", "essential", "discretionary", "goal", "emergency", "saving"]
FloorTier = Literal["obligation", "essential"]
#: sai số coi là 0 của các biến elastic, tính bằng VND
GAP_TOLERANCE_VND = 0.5


@dataclass(frozen=True)
class AllocationParams:
    """Tham số của bộ tối ưu (cấu hình, không gắn cứng trong mã; xem `yofina_forecast.settings`)."""

    month_days: int
    rounding_step_vnd: int
    relax_delay_months: int
    discretionary_max_cut_percent: float
    essential_floor_percent: float
    weight_discretionary: float
    weight_goal: float
    weight_essential: float
    weight_emergency: float
    penalty_obligation_floor: float
    penalty_essential_floor: float
    penalty_goal_need: float
    stay_epsilon: float


@dataclass(frozen=True)
class GoalSpec:
    jar_code: str
    remaining_vnd: int
    days_left: int
    target_vnd: int
    target_date: date | None
    weight: float = 1.0


@dataclass(frozen=True)
class JarSpec:
    code: str
    role: Role
    current_vnd: int
    floor_vnd: int = 0
    floor_tier: FloorTier = "essential"
    goal: GoalSpec | None = None
    weight: float = 1.0


@dataclass(frozen=True)
class AllocationProblem:
    income_vnd: int
    jars: tuple[JarSpec, ...]
    params: AllocationParams
    allow_relaxation: bool = True


@dataclass(frozen=True)
class JarOutcome:
    code: str
    proposed_vnd: int
    floor_gap_vnd: int
    #: mức cần mỗi tháng của mục tiêu theo hạn gốc (0 nếu không có mục tiêu hoặc đã đủ)
    needed_vnd: int = 0
    goal_on_track: bool = True
    goal_shortfall_vnd: int = 0
    #: số ngày để đóng đủ phần còn thiếu nếu giữ mức đề xuất; None nếu mức đề xuất bằng 0
    days_to_goal: int | None = None


@dataclass(frozen=True)
class Relaxation:
    kind: Literal["goal_delayed", "discretionary_reduced"]
    jar_code: str
    before_vnd: int
    after_vnd: int
    delay_months: int = 0


@dataclass(frozen=True)
class AllocationSolution:
    status: Literal["optimal", "relaxed", "infeasible"]
    jars: tuple[JarOutcome, ...]
    unallocated_vnd: int
    relaxations: tuple[Relaxation, ...]
    relaxation_rounds: int
    solver_status: str
    elapsed_ms: int
    method: str = "highs"
    #: tổng phần sàn còn thiếu (VND) sau nghiệm trả về
    floor_gap_total_vnd: int = 0
    notes: tuple[str, ...] = field(default_factory=tuple)

    def outcome(self, code: str) -> JarOutcome:
        return next(j for j in self.jars if j.code == code)


def goal_need_vnd(g: GoalSpec, month_days: int, *, extra_months: int = 0) -> int:
    """Mức cần mỗi tháng để kịp hạn (hạn lùi thêm `extra_months` tháng nếu có)."""
    return monthly_needed_vnd(
        remaining_vnd=g.remaining_vnd,
        days_left=g.days_left + extra_months * month_days,
        month_days=month_days,
    )


@dataclass
class _Raw:
    x: np.ndarray  # VND
    u: float
    e: np.ndarray
    g: np.ndarray
    h: np.ndarray
    status: int
    message: str
    fun: float


def _solve(p: AllocationProblem, relaxed: bool) -> tuple[_Raw, np.ndarray]:
    """Giải một vòng. Trả (nghiệm quy về VND, mức cần cứng của từng hũ trong vòng này, VND)."""
    prm = p.params
    jars = p.jars
    n = len(jars)
    s = float(prm.rounding_step_vnd)
    income = p.income_vnd / s
    cur = np.array([j.current_vnd for j in jars], dtype=float) / s
    floor = np.array([j.floor_vnd for j in jars], dtype=float) / s
    need_hard = np.zeros(n)
    need_pref = np.zeros(n)
    for k, j in enumerate(jars):
        if j.goal is None:
            continue
        full = goal_need_vnd(j.goal, prm.month_days)
        if relaxed:
            need_hard[k] = (
                goal_need_vnd(j.goal, prm.month_days, extra_months=prm.relax_delay_months) / s
            )
            need_pref[k] = full / s
        else:
            need_hard[k] = full / s
    keep = 1.0 - prm.discretionary_max_cut_percent / 100.0
    lower = np.zeros(n)
    if not relaxed:
        for k, j in enumerate(jars):
            if j.role == "discretionary":
                lower[k] = keep * cur[k]
        if (
            lower.sum() > income
        ):  # thu nhập không đủ giữ cả mức tối thiểu: bỏ ràng buộc mềm này (vòng nới sẽ ghi nhận), tránh vô nghiệm
            lower[:] = 0.0

    # biến: x(n) e(n) g(n) h(n) d(n) u(1)
    nv = 5 * n + 1
    iu = 5 * n
    c = np.zeros(nv)
    for k, j in enumerate(jars):
        c[n + k] = (
            prm.penalty_obligation_floor
            if j.floor_tier == "obligation"
            else prm.penalty_essential_floor
        )
        # mức cần của mục tiêu trên hũ đệm (đích số dư của Dự phòng) xếp trước mục tiêu khác (BR-65): phần thiếu chịu phạt nhân tỷ lệ
        # trọng số cắt của vai đệm so với vai mục tiêu. Hũ không có mục tiêu thì g_j, h_j không có ràng buộc nào nên không đổi gì.
        rank = (
            prm.weight_emergency / prm.weight_goal
            if j.role == "emergency" and prm.weight_goal > 0
            else 1.0
        )
        c[2 * n + k] = prm.penalty_goal_need * rank
        c[3 * n + k] = prm.weight_goal * j.weight * rank
        cut = {
            "discretionary": prm.weight_discretionary,
            "goal": prm.weight_goal * j.weight,
            "saving": prm.weight_goal,
            "essential": prm.weight_essential,
            "obligation": prm.weight_essential,
            "emergency": prm.weight_emergency,
        }[j.role]
        c[4 * n + k] = cut
        c[k] = prm.stay_epsilon
    a_eq = np.zeros((1, nv))
    a_eq[0, :n] = 1.0
    a_eq[0, iu] = 1.0
    rows: list[np.ndarray] = []
    rhs: list[float] = []
    for k in range(n):
        if floor[k] > 0:
            r = np.zeros(nv)
            r[k] = -1.0
            r[n + k] = -1.0
            rows.append(r)
            rhs.append(-floor[k])
        if need_hard[k] > 0:
            r = np.zeros(nv)
            r[k] = -1.0
            r[2 * n + k] = -1.0
            rows.append(r)
            rhs.append(-need_hard[k])
        if relaxed and need_pref[k] > 0:
            r = np.zeros(nv)
            r[k] = -1.0
            r[3 * n + k] = -1.0
            rows.append(r)
            rhs.append(-need_pref[k])
        if cur[k] > 0:
            r = np.zeros(nv)
            r[k] = -1.0
            r[4 * n + k] = -1.0
            rows.append(r)
            rhs.append(-cur[k])
    bounds = [(lower[k], None) for k in range(n)] + [(0, None)] * (4 * n + 1)
    res = linprog(
        c,
        A_ub=np.array(rows) if rows else None,
        b_ub=np.array(rhs) if rhs else None,
        A_eq=a_eq,
        b_eq=[income],
        bounds=bounds,
        method="highs",
    )
    if res.status != 0 or res.x is None:
        raise RuntimeError(f"HiGHS không giải được: status {res.status} ({res.message[:80]})")
    v = res.x * s
    raw = _Raw(
        x=v[:n],
        e=v[n : 2 * n],
        g=v[2 * n : 3 * n],
        h=v[3 * n : 4 * n],
        u=float(v[iu]),
        status=int(res.status),
        message=str(res.message),
        fun=float(res.fun),
    )
    return raw, need_hard * s


def _round_step(v: float, step: int) -> int:
    return round(v / step) * step


def _integerize(p: AllocationProblem, raw: _Raw, need_hard: np.ndarray) -> tuple[list[int], int]:
    """Số nguyên VND bội của bước làm tròn, bảo toàn tiền; không để mức làm tròn làm một sàn đã đạt thành hụt."""
    step = p.params.rounding_step_vnd
    tol = GAP_TOLERANCE_VND
    n = len(p.jars)
    lows: list[int] = []
    xs: list[int] = []
    for k, j in enumerate(p.jars):
        low = 0
        if j.floor_vnd > 0 and raw.e[k] < tol:
            low = max(low, j.floor_vnd)
        if need_hard[k] > 0 and raw.g[k] < tol:
            low = max(low, int(np.ceil(need_hard[k] - 1e-6)))
        lows.append(low)
        xs.append(max(_round_step(float(raw.x[k]), step), low))
    unalloc = max(round(raw.u), 0)
    diff = p.income_vnd - unalloc - sum(xs)
    order = sorted(range(n), key=lambda k: -float(raw.x[k]))
    if diff > 0 and order:
        xs[order[0]] += diff
    while diff < 0:
        k = max(range(n), key=lambda k: xs[k] - lows[k])
        take = min(-diff, max(xs[k] - lows[k], 0)) or min(-diff, xs[k])
        if take <= 0:
            break
        xs[k] -= take
        diff += take
    unalloc = p.income_vnd - sum(xs)
    return xs, max(unalloc, 0)


def _outcomes(p: AllocationProblem, xs: list[int]) -> tuple[JarOutcome, ...]:
    prm = p.params
    out: list[JarOutcome] = []
    for k, j in enumerate(p.jars):
        gap = max(j.floor_vnd - xs[k], 0)
        needed, on_track, shortfall, days = 0, True, 0, None
        if j.goal is not None and j.goal.remaining_vnd > 0:
            needed = goal_need_vnd(j.goal, prm.month_days)
            if xs[k] > 0:
                days = int(np.ceil(j.goal.remaining_vnd * prm.month_days / xs[k]))
            on_track = xs[k] >= needed
            if not on_track:
                shortfall = max(
                    j.goal.remaining_vnd - int(xs[k] * max(j.goal.days_left, 1) / prm.month_days), 0
                )
        out.append(JarOutcome(j.code, xs[k], gap, needed, on_track, shortfall, days))
    return tuple(out)


def _relaxations(
    p: AllocationProblem, first: _Raw, second: _Raw, xs2: list[int]
) -> tuple[Relaxation, ...]:
    prm = p.params
    keep = 1.0 - prm.discretionary_max_cut_percent / 100.0
    found: list[Relaxation] = []
    for k, j in enumerate(p.jars):
        if j.role == "discretionary" and xs2[k] < keep * j.current_vnd - GAP_TOLERANCE_VND:
            found.append(Relaxation("discretionary_reduced", j.code, j.current_vnd, xs2[k]))
        if j.goal is not None and j.goal.remaining_vnd > 0:
            full = goal_need_vnd(j.goal, prm.month_days)
            if xs2[k] < full - GAP_TOLERANCE_VND:
                found.append(
                    Relaxation(
                        "goal_delayed", j.code, full, xs2[k], delay_months=prm.relax_delay_months
                    )
                )
    return tuple(found)


def _ok(raw: _Raw) -> bool:
    return bool(
        raw.e.max(initial=0.0) < GAP_TOLERANCE_VND and raw.g.max(initial=0.0) < GAP_TOLERANCE_VND
    )


def optimize(problem: AllocationProblem) -> AllocationSolution:
    """Giải bài toán; xem docstring module. Thu nhập 0 (cú sốc mất việc) cho nghiệm không có đồng nào để phân bổ, mọi sàn thiếu, `infeasible`. Ném `ValueError` nếu thu nhập âm."""
    if problem.income_vnd < 0:
        raise ValueError("thu nhập không được âm")
    if not problem.jars:
        raise ValueError("cần ít nhất một hũ")
    started = time.perf_counter()
    first, need0 = _solve(problem, relaxed=False)
    if _ok(first):
        xs, unalloc = _integerize(problem, first, need0)
        return AllocationSolution(
            status="optimal",
            jars=_outcomes(problem, xs),
            unallocated_vnd=unalloc,
            relaxations=(),
            relaxation_rounds=0,
            solver_status="optimal",
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )
    second, need1 = _solve(problem, relaxed=True)
    xs, unalloc = _integerize(problem, second, need1)
    relax = _relaxations(problem, first, second, xs)
    if problem.allow_relaxation and _ok(second) and relax:
        return AllocationSolution(
            status="relaxed",
            jars=_outcomes(problem, xs),
            unallocated_vnd=unalloc,
            relaxations=relax,
            relaxation_rounds=1,
            solver_status="optimal sau khi nới",
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )
    if problem.allow_relaxation and _ok(second) and not relax:
        # vòng 0 trượt ngưỡng sai số nhưng vòng nới không phải nới gì: nghiệm vòng nới đạt, không có gì để ghi lại
        return AllocationSolution(
            status="optimal",
            jars=_outcomes(problem, xs),
            unallocated_vnd=unalloc,
            relaxations=(),
            relaxation_rounds=0,
            solver_status="optimal",
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )
    if not problem.allow_relaxation:
        xs, unalloc = _integerize(problem, first, need0)
        relax = ()
        note = ("không nới theo yêu cầu: nghiệm là của vòng chặt",)
    else:
        note = ()
    outcomes = _outcomes(problem, xs)
    return AllocationSolution(
        status="infeasible",
        jars=outcomes,
        unallocated_vnd=unalloc,
        relaxations=relax,
        relaxation_rounds=1,
        solver_status="infeasible sau khi nới" if not note else "infeasible, không nới",
        elapsed_ms=round((time.perf_counter() - started) * 1000),
        floor_gap_total_vnd=sum(o.floor_gap_vnd for o in outcomes),
        notes=note,
    )


def project_date(start: date, days_to_goal: int | None) -> date | None:
    return None if days_to_goal is None else start + timedelta(days=days_to_goal)


__all__ = [
    "AllocationParams",
    "AllocationProblem",
    "AllocationSolution",
    "GoalSpec",
    "JarOutcome",
    "JarSpec",
    "Relaxation",
    "goal_need_vnd",
    "optimize",
    "project_date",
]
