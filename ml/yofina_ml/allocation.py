"""Tối ưu phân bổ lương vào hũ (phase 4, F5) bằng `scipy.optimize.linprog` (HiGHS). HÀM THUẦN: không I/O, không đồng hồ.

Bài toán theo tháng (đơn vị nội bộ là `rounding_step_vnd` VND để HiGHS không phải xử lý số quá lớn):

    biến   x_j   tiền vào hũ j                      u   phần chưa phân bổ
           e_j   phần SÀN chưa đạt (elastic)        g_j phần mức cần của mục tiêu chưa đạt (cứng)
           h_j   phần mức cần ưa thích chưa đạt     d_j phần cắt xuống dưới mức hiện tại
           f_j   phần SÀN CHI chưa đạt (elastic)
    ràng buộc  sum_j x_j + u = thu nhập
               x_j + e_j >= sàn_j                   (sàn cứng của nghĩa vụ và khoản thiết yếu, qua biến elastic)
               x_j + f_j >= sàn chi_j               (sàn chi theo mức chi thật gần đây của hũ, #39 26/11)
               x_j + g_j >= mức cần_j               (mục tiêu có hạn: cần đóng góp đủ mỗi tháng để kịp hạn)
               x_j + d_j >= mức hiện tại_j          (chia theo tỷ lệ đã khai; cắt xuống thì chịu phạt `d_j`)
    mục tiêu   min sum M_j e_j + M_spend sum f_j + M_goal sum g_j + sum w_j h_j + sum k_j d_j + eps sum x_j

- Sàn cứng KHÔNG đặt qua `bounds` mà qua `e_j` với mức phạt `M_j` theo ưu tiên (nghĩa vụ > thiết yếu), nên bài toán luôn có nghiệm và
  nếu thu nhập không đủ thì phần thiếu rơi vào hũ ưu tiên thấp trước (spike `s8_lp.py` ca 2b và 2c).
- Cắt xuống dưới mức hiện tại tốn `k_j` theo loại hũ (không thiết yếu < mục tiêu < thiết yếu < dự phòng), nên tiền để trả sàn và mục
  tiêu lấy từ hũ không thiết yếu trước.
- **Thứ tự ưu tiên khi không đủ chỗ** (#39, #44), từ cứng tới mềm, theo mức phạt: sàn nghĩa vụ (`penalty_obligation_floor`) và
  sàn thiết yếu (`penalty_essential_floor`) > giữ hũ đệm chưa tới đích (`penalty_spending_floor x weight_emergency / weight_goal`) >
  giữ Quỹ dồn có khoản sắp cần chưa đủ tiền (trung bình mức phạt giữ hũ đệm và sàn chi) > sàn chi (`penalty_spending_floor`) >
  mức cần của mục tiêu có hạn (`penalty_goal_need`, hũ đệm nhân `weight_emergency / weight_goal`) > phần còn lại gồm tích lũy dài hạn
  (trọng số cắt `k_j`). Cấu hình phải giữ đúng thứ tự này.
- **Sàn chi** (`JarSpec.spend_floor_vnd`, người gọi tính: tỷ lệ giữ x mức nền bền của hũ, không vượt mức hiện tại): mục tiêu lùi hạn hoặc
  chưa khả thi nếu phải lấy tiền dưới sàn chi. Sàn chi nhường cho sàn nghĩa vụ, sàn thiết yếu và mức giữ của hũ đệm, Quỹ dồn. Phần hụt
  sàn chi được ghi là điều đã nới (`discretionary_reduced`). Khi ví vẫn thiếu sàn cứng dù sàn chi đã nhường hết, giải lại với sàn chi là
  cận dưới cứng, miễn nghĩa vụ cứng vẫn nhận đủ như khi nhường (`_keep_spend_floors`).
- Hũ đệm (`emergency`) có thể mang mục tiêu (đích số dư của lượt lập lộ trình): phần thiếu của mức cần trên hũ đó phạt nặng hơn mục tiêu
  khác theo tỷ lệ `weight_emergency / weight_goal`, nên khi không đủ cho mọi mục tiêu thì hũ đệm được trước (BR-65).
- Mục tiêu **chưa có hạn** (`GoalSpec.days_left` None, V2 của báo cáo rà soát #39): không có mức cần cứng hay ưa thích, nên không ép hũ
  nào; hũ giữ phần chia theo thứ tự cắt (nhận phần còn lại sau các bậc trên), không bao giờ bị coi là trễ hạn hay phải lùi hạn.
- Hũ đệm **chưa tới đích** (`hold_current`, người gọi quyết từ số dư và đích của hũ) giữ mức hiện tại ở CẢ HAI vòng: cắt xuống dưới mức
  hiện tại chịu mức phạt giữ hũ đệm ở trên, nên mục tiêu khác (kể cả khi vì thế mà chưa khả thi) và sàn chi không lấy được tiền từ hũ
  đệm (BR-65: hũ đệm chưa đủ thì không tăng hũ mục tiêu trước), còn sàn nghĩa vụ và sàn thiết yếu (phạt nặng hơn) vẫn lấy được.
- Quỹ dồn (`role="saving"`, `hold_current=True`) giữ mức hiện tại ở cả hai vòng khi thiếu tiền cho khoản có ngày cần trong kỳ
  (`today < needed_date <= end`, kỳ do người gọi tính). Số dư đủ cho tổng các khoản trong kỳ thì dùng trọng số cắt thông thường.
- **Vòng 0** (chặt): hũ không thiết yếu chỉ được cắt tới `(1 - cắt tối đa) x mức hiện tại`; mục tiêu cần đủ mức cần để kịp hạn.
  Đạt (mọi `e_j`, `g_j`, `f_j` bằng 0 và giữ mức hiện tại của các hũ có `hold_current`) thì trạng thái `optimal`.
- **Nới ĐÚNG MỘT vòng** nếu vòng 0 không đạt: hũ không thiết yếu được cắt tới 0 (sàn chi vẫn giữ trước mục tiêu), mục tiêu chỉ
  cần đủ mức cần của hạn đã lùi `relax_delay_months` tháng (cứng) và mức cần của hạn gốc (mềm, phạt `h_j`). Đạt (mọi `e_j`, `g_j`
  bằng 0) thì `relaxed` kèm điều đã nới (hũ không thiết yếu bị cắt sâu hơn vòng 0, hũ bị cắt dưới sàn chi, mục tiêu phải lùi hạn).
  Nếu đạt mà không có điều đã nới để ghi (ví dụ chỉ cắt Quỹ dồn để đủ sàn cứng), kết quả là `optimal`. Vẫn không đạt thì `infeasible`
  (không nới thêm): người gọi nêu đúng hai lựa chọn.
- Không cho nới (`allow_relaxation=False`): nghiệm vòng 0; phần hụt sàn chi hoặc mức giữ hũ đệm và Quỹ dồn được chấp nhận nếu đạt sàn
  cứng và mức cần cứng.
- Tiền bảo toàn: tổng `x_j` đã làm tròn cộng `unallocated` đúng bằng thu nhập (phần dư làm tròn dồn vào hũ lớn nhất; phần thiếu lấy từ
  hũ còn dư nhiều nhất trên mức phải giữ: sàn, sàn chi, mức cần đã đạt, mức hiện tại của hũ LP không cắt).

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
    #: đích tự tính của hũ đệm khi lượt gọi không nêu đích: từng này tháng chi thiết yếu (BR-64, C-13). Người gọi dùng để quyết
    #: `JarSpec.hold_current`; bộ giải không đọc.
    buffer_target_months: float
    #: tỷ lệ giữ: sàn chi của hũ chi = tỷ lệ này x mức nền bền mỗi tháng của hũ (#39, 26/11). Người gọi tính `JarSpec.spend_floor_vnd`;
    #: bộ giải không đọc.
    spending_keep_ratio: float
    #: mức phạt mỗi đồng sàn chi chưa đạt: trên mức cần của mục tiêu (kể cả hũ đệm), dưới sàn thiết yếu; giữ hũ đệm nhân thêm
    #: `weight_emergency / weight_goal` (xem docstring module)
    penalty_spending_floor: float
    #: mức chi gần đây của một hũ chi được coi là cao bất thường khi từ từng này lần mức nền bền trở lên (#39, C5), trừ khi bộ phát hiện
    #: đổi hành vi PELT đã xác nhận dấu hiệu cho hũ đó (khi ấy dùng chính dấu hiệu đó). Chỉ là dữ kiện người gọi trả cho agent
    #: (`AllocationSpend.unusually_high`); bộ giải không đọc và không đổi cách tính sàn.
    spend_spike_ratio: float
    #: cửa sổ mức nền bền (tuần): sàn thiết yếu, sàn chi và đích tự tính của hũ đệm tính từ trung vị chi theo tuần của từng này tuần gần
    #: nhất (`yofina_core.spend_baseline`, #39 chốt 26/11). Người gọi tính; bộ giải không đọc.
    spend_baseline_weeks: int
    #: số tuần tối thiểu của cửa sổ mức nền; ít hơn (hoặc hũ thưa có trung vị 0) thì người gọi lùi về chi trung bình của cửa sổ gần nhất
    spend_baseline_min_weeks: int


@dataclass(frozen=True)
class GoalSpec:
    """Mục tiêu của một hũ. `days_left` None: mục tiêu CHƯA CÓ HẠN (V2 của báo cáo rà soát #39): không có mức cần cứng, hũ chỉ giữ phần
    chia theo thứ tự cắt và nhận phần còn lại, không bao giờ bị coi là trễ hạn (người gọi báo "chưa có hạn" để agent hỏi lại)."""

    jar_code: str
    remaining_vnd: int
    days_left: int | None
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
    #: giữ mức hiện tại ở cả hai vòng cho hũ đệm chưa tới đích (`emergency`) hoặc Quỹ dồn có khoản sắp cần (`saving`)
    hold_current: bool = False
    #: sàn chi (VND/tháng): mục tiêu không lấy tiền dưới mức này, nghĩa vụ và thiết yếu thì lấy được (xem docstring module)
    spend_floor_vnd: int = 0


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
    """Mức cần mỗi tháng để kịp hạn (hạn lùi thêm `extra_months` tháng nếu có). Mục tiêu chưa có hạn không có mức cần (0)."""
    if g.days_left is None:
        return 0
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
    #: mức cần ưa thích (hạn gốc) của vòng nới, VND; vòng chặt toàn 0
    need_pref: np.ndarray
    #: phần sàn chi chưa đạt, VND
    f: np.ndarray
    #: phần cắt dưới mức hiện tại, VND
    d: np.ndarray


def _rank(p: AllocationParams, role: Role) -> float:
    """Hũ đệm xếp trên hũ khác cùng bậc theo tỷ lệ trọng số cắt của vai đệm so với vai mục tiêu (BR-65); hũ khác 1."""
    return p.weight_emergency / p.weight_goal if role == "emergency" and p.weight_goal > 0 else 1.0


def _solve(
    p: AllocationProblem, relaxed: bool, keep_vnd: np.ndarray | None = None
) -> tuple[_Raw, np.ndarray]:
    """Giải một vòng. Trả (nghiệm quy về VND, mức cần cứng của từng hũ trong vòng này, VND). `keep_vnd` (VND): cận dưới cứng của từng hũ
    (giữ sàn chi khi ví vô nghiệm dù đã nhường, xem `_keep_spend_floors`)."""
    prm = p.params
    jars = p.jars
    n = len(jars)
    s = float(prm.rounding_step_vnd)
    income = p.income_vnd / s
    cur = np.array([j.current_vnd for j in jars], dtype=float) / s
    floor = np.array([j.floor_vnd for j in jars], dtype=float) / s
    spend_floor = np.array([j.spend_floor_vnd for j in jars], dtype=float) / s
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
    if keep_vnd is not None:
        lower = np.maximum(lower, keep_vnd / s)
        if lower.sum() > income:  # người gọi bảo đảm riêng `keep_vnd` vừa thu nhập
            lower = keep_vnd / s

    # biến: x(n) e(n) g(n) h(n) d(n) f(n) u(1)
    nv = 6 * n + 1
    iu = 6 * n
    c = np.zeros(nv)
    for k, j in enumerate(jars):
        c[n + k] = (
            prm.penalty_obligation_floor
            if j.floor_tier == "obligation"
            else prm.penalty_essential_floor
        )
        # mức cần của mục tiêu trên hũ đệm (đích số dư của Dự phòng) xếp trước mục tiêu khác (BR-65): phần thiếu chịu phạt nhân tỷ lệ
        # trọng số cắt của vai đệm so với vai mục tiêu. Hũ không có mục tiêu thì g_j, h_j không có ràng buộc nào nên không đổi gì.
        rank = _rank(prm, j.role)
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
        if j.hold_current:
            cut = prm.penalty_spending_floor * rank
            # BR-65: mức giữ Quỹ dồn nằm giữa mức giữ hũ đệm và sàn chi ở cả hai vòng.
            if j.role == "saving":
                cut = prm.penalty_spending_floor * (1.0 + _rank(prm, "emergency")) / 2.0
        c[4 * n + k] = cut
        c[5 * n + k] = prm.penalty_spending_floor
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
        if spend_floor[k] > 0:
            r = np.zeros(nv)
            r[k] = -1.0
            r[5 * n + k] = -1.0
            rows.append(r)
            rhs.append(-spend_floor[k])
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
    bounds = [(lower[k], None) for k in range(n)] + [(0, None)] * (5 * n + 1)
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
        need_pref=need_pref * s,
        f=v[5 * n : 6 * n],
        d=v[4 * n : 5 * n],
    )
    return raw, need_hard * s


def _round_step(v: float, step: int) -> int:
    return round(v / step) * step


def _integerize(p: AllocationProblem, raw: _Raw, need_hard: np.ndarray) -> tuple[list[int], int]:
    """Số nguyên VND bội của bước làm tròn, bảo toàn tiền; không để mức làm tròn làm một sàn hay mức cần đã đạt thành hụt, hay cắt một
    hũ mà LP giữ nguyên mức hiện tại."""
    step = p.params.rounding_step_vnd
    tol = GAP_TOLERANCE_VND
    n = len(p.jars)
    lows: list[int] = []
    xs: list[int] = []
    for k, j in enumerate(p.jars):
        low = 0
        if j.floor_vnd > 0 and raw.e[k] < tol:
            low = max(low, j.floor_vnd)
        if j.spend_floor_vnd > 0 and raw.f[k] < tol:
            low = max(low, j.spend_floor_vnd)
        if need_hard[k] > 0 and raw.g[k] < tol:
            low = max(low, int(np.ceil(need_hard[k] - 1e-6)))
        if raw.need_pref[k] > 0 and raw.h[k] < tol:
            # vòng nới đã đủ mức cần theo hạn gốc: làm tròn không biến nó thành "lùi hạn"
            low = max(low, int(np.ceil(raw.need_pref[k] - 1e-6)))
        if raw.x[k] >= j.current_vnd - tol:
            # LP không cắt hũ này (hũ đệm đang giữ, hũ không phải nhường): làm tròn không lấy bớt của nó
            low = max(low, j.current_vnd)
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
            # chưa có hạn: không có mức cần nên không bao giờ "trễ hạn"; chỉ có ngày dự kiến theo mức đề xuất
            on_track = j.goal.days_left is None or xs[k] >= needed
            if not on_track:
                assert j.goal.days_left is not None
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
        deeper = j.role == "discretionary" and xs2[k] < keep * j.current_vnd - GAP_TOLERANCE_VND
        # sàn chi đã nhường cho nghĩa vụ hay chi thiết yếu: phần không thiết yếu của hũ bị giảm (cả hũ trộn như Chi hằng ngày của ví ba hũ)
        below_spend = xs2[k] < min(j.spend_floor_vnd, j.current_vnd) - GAP_TOLERANCE_VND
        if deeper or below_spend:
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


def _ok(raw: _Raw, p: AllocationProblem | None = None) -> bool:
    """Đạt sàn cứng và mức cần cứng. Vòng chặt khi được nới (`p`): còn phải giữ đủ sàn chi và mức hiện tại của hũ đệm, Quỹ dồn có
    `hold_current`."""
    hard = bool(
        raw.e.max(initial=0.0) < GAP_TOLERANCE_VND and raw.g.max(initial=0.0) < GAP_TOLERANCE_VND
    )
    if p is None or not hard:
        return hard
    held = [k for k, j in enumerate(p.jars) if j.hold_current]
    return bool(
        raw.f.max(initial=0.0) < GAP_TOLERANCE_VND
        and all(raw.d[k] < GAP_TOLERANCE_VND for k in held)
    )


def optimize(problem: AllocationProblem) -> AllocationSolution:
    """Giải bài toán; xem docstring module. Thu nhập 0 (cú sốc mất việc) cho nghiệm không có đồng nào để phân bổ, mọi sàn thiếu, `infeasible`. Ném `ValueError` nếu thu nhập âm."""
    if problem.income_vnd < 0:
        raise ValueError("thu nhập không được âm")
    if not problem.jars:
        raise ValueError("cần ít nhất một hũ")
    return _optimize(problem, time.perf_counter())


def _obligation_gap(p: AllocationProblem, raw: _Raw) -> float:
    return float(sum(raw.e[k] for k, j in enumerate(p.jars) if j.floor_tier == "obligation"))


def _keep_spend_floors(
    p: AllocationProblem, raw: _Raw, relaxed: bool
) -> tuple[_Raw, np.ndarray] | None:
    """Ví vẫn thiếu sàn cứng dù sàn chi đã nhường hết (vô nghiệm dù sao, như cảnh 4 khi sàn thiết yếu của Ăn uống theo mức chi vừa tăng
    vọt vượt chỗ): nhường sàn chi không làm ví đủ sàn mà chỉ đưa hũ chi về 0, nên giải lại vòng đó với sàn chi là cận dưới cứng. Chỉ giữ
    khi nghĩa vụ cứng nhận đủ như khi nhường (nghĩa vụ trước, BR-42); không thì None (giữ nghiệm đã nhường)."""
    if raw.e.max(initial=0.0) < GAP_TOLERANCE_VND:
        return None  # vô nghiệm vì mục tiêu không kịp: sàn chi đã đứng trên mục tiêu
    keep = np.array([min(j.spend_floor_vnd, j.current_vnd) for j in p.jars], dtype=float)
    if not keep.any() or keep.sum() > p.income_vnd:
        return None
    again, need = _solve(p, relaxed, keep_vnd=keep)
    if _obligation_gap(p, again) > _obligation_gap(p, raw) + GAP_TOLERANCE_VND:
        return None
    return again, need


def _optimize(problem: AllocationProblem, started: float) -> AllocationSolution:
    first, need0 = _solve(problem, relaxed=False)
    if _ok(first, problem if problem.allow_relaxation else None):
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
        last, last_need, relaxed_round = first, need0, False
        note = ("không nới theo yêu cầu: nghiệm là của vòng chặt",)
    else:
        last, last_need, relaxed_round = second, need1, True
        note = ()
    kept = _keep_spend_floors(problem, last, relaxed_round)
    if kept is not None:
        last, last_need = kept
    if kept is not None or not problem.allow_relaxation:
        xs, unalloc = _integerize(problem, last, last_need)
        relax = _relaxations(problem, first, last, xs) if problem.allow_relaxation else ()
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
