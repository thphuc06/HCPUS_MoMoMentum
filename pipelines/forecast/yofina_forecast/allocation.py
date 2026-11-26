"""`optimize_allocation` phía Lambda forecast (phase 4, F5): dựng bài toán phân bổ lương từ dữ liệu người dùng, giải bằng
`yofina_ml.allocation` (scipy `linprog`, HiGHS) và trả `AllocationPlanData`.

Chạy ở đây (không phải ở ledger) vì Lambda này có numpy và scipy (ADR của phase 4, mục luồng A). Ledger gọi `Invoke` đồng bộ với sự kiện
`{"op": "optimize_allocation", "user_id", "args"}` (op ở `batch.py`) và trả NGUYÊN phong bì tool; Gateway không gọi thẳng Lambda này cho tool
này. Không ghi gì vào DB.

Dựng bài toán (mọi số lấy từ dữ liệu người dùng hoặc cấu hình `ForecastSettings.allocation`):
- **Thu nhập hằng tháng** = lương đã khai. Có `shock_id` thì thu nhập co theo cú sốc (cùng công thức hệ số thu nhập của `stress_test`),
  nghĩa vụ loại bị tăng giá tăng theo, khoản chi một lần trừ vào thu nhập: dựng lộ trình thích ứng sau `stress_test`.
- **Mức hiện tại** của hũ = thu nhập x tỷ lệ chia đã khai.
- **Sàn cứng** = nghĩa vụ cứng phải trả bằng hũ đó (nghĩa vụ thiết yếu và nợ Trả sau, vay; quy về tháng) cộng, với hũ chi tiêu thiết
  yếu, `essential_floor_percent` của mức chi trung bình hằng tháng. Chi hằng ngày và hũ obligation chỉ tính phần chi có LOẠI giao dịch
  thiết yếu không gắn nghĩa vụ (`essential_spend`; hũ obligation: hóa đơn trả lẻ như nạp điện thoại). Nghĩa vụ ưu tiên hơn chi tiêu
  thiết yếu (mức phạt elastic khác nhau). Sàn của MỌI hũ (không theo mã) không dưới tổng mọi nghĩa vụ đang hoạt động trả từ hũ đó, kể cả
  khoản không thiết yếu (Netflix trả từ Giải trí giữ Giải trí không dưới mức Netflix); hũ chỉ có khoản không thiết yếu vẫn là hũ không
  thiết yếu, sàn bậc thiết yếu.
- **Mục tiêu** = hũ có `goal_vnd`; mức cần mỗi tháng = phần còn thiếu x ngày của tháng / số ngày còn lại tới hạn (không có hạn thì hết
  `horizon_months`). `goals` của tham số ghi đè trọng số, số tiền hoặc hạn của từng hũ (hũ không phải hũ tiết kiệm thì từ chối).
- Hũ chi tiêu thiết yếu theo cấu hình (`essential_jar_codes`), hũ tiết kiệm không mục tiêu là hũ Dự phòng (giữ mức hiện tại, cắt thì
  phạt nặng nhất), còn lại không thiết yếu.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from yofina_core.blocks import (
    ActionChange,
    ForecastJar,
    GoalProjection,
    RoadmapAlternative,
    format_instant,
)
from yofina_core.clock import next_payday
from yofina_core.errors import ErrorCode, ToolStatus, YofinaError
from yofina_core.money import format_vnd
from yofina_core.roadmap import (
    AllocationLine,
    AllocationPlanData,
    AllocationRelaxation,
    AllocationSolver,
)
from yofina_core.wallet import (
    DEFAULT_SPENDING_JAR,
    is_buffer_jar,
    is_goal_jar,
    pay_jar_or_default,
    resolve_obligation_pay_jar,
)
from yofina_forecast.common import clip, int_of, to_date
from yofina_forecast.resilience import (
    Gathered,
    ResilienceEngine,
    monthly_equivalent,
    variable_monthly_spend,
)
from yofina_forecast.runner import Pipeline
from yofina_forecast.stress import find_shock
from yofina_ml.allocation import (
    AllocationProblem,
    AllocationSolution,
    GoalSpec,
    JarSpec,
    optimize,
    project_date,
)
from yofina_ml.stress import income_factor

log = logging.getLogger("yofina.forecast.allocation")

ARG_KEYS = frozenset({"horizon_months", "goals", "shock_id", "allow_relaxation", "user_id"})
GOAL_KEYS = frozenset({"jar", "weight", "target_vnd", "target_date"})
MAX_HORIZON_MONTHS = 24
MAX_GOALS = 8
#: khoản nợ không bỏ qua được dù người dùng không đánh dấu thiết yếu (trả sau, vay)
DEBT_KINDS = ("bnpl", "loan")
JAR_KIND_TO_LINE = {"spending": "spending", "saving": "saving", "obligation": "obligation"}


def _date_vn(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


@dataclass(frozen=True)
class _Goal:
    jar_code: str
    target_vnd: int
    target_date: date | None
    balance_vnd: int
    weight: float


@dataclass(frozen=True)
class Built:
    problem: AllocationProblem
    horizon_months: int
    income_vnd: int
    obligations_monthly_vnd: int
    #: nghĩa vụ không thiết yếu cắt được (quy về tháng), cho lựa chọn khi chỉ sàn vượt thu nhập
    cuttable_obligations_vnd: int
    goals: dict[str, _Goal]
    jars: dict[str, Mapping[str, Any]]
    split_percent: dict[str, float]


class AllocationEngine:
    def __init__(self, pipeline: Pipeline, resilience: ResilienceEngine | None = None) -> None:
        self.pipeline = pipeline
        self.resilience = resilience or ResilienceEngine(pipeline)

    # --- tham số ----------------------------------------------------------------------------------
    def _args(self, args: Mapping[str, Any]) -> tuple[int, list[dict[str, Any]], str | None, bool]:
        extra = sorted(set(args) - ARG_KEYS)
        if extra:
            raise YofinaError(
                ErrorCode.PARAMS_INVALID, "Tham số không hợp lệ: " + ", ".join(extra)[:80]
            )
        horizon = args.get("horizon_months")
        if horizon is None:
            horizon = self.pipeline.settings.allocation_horizon_months
        if (
            isinstance(horizon, bool)
            or not isinstance(horizon, int)
            or not 1 <= horizon <= MAX_HORIZON_MONTHS
        ):
            raise YofinaError(
                ErrorCode.PARAMS_INVALID, "horizon_months phải là số nguyên từ 1 đến 24."
            )
        goals = args.get("goals") or []
        if (
            not isinstance(goals, Sequence)
            or isinstance(goals, str | bytes | Mapping)
            or len(goals) > MAX_GOALS
        ):
            raise YofinaError(
                ErrorCode.PARAMS_INVALID, f"goals phải là danh sách tối đa {MAX_GOALS} mục."
            )
        clean: list[dict[str, Any]] = []
        for i, g in enumerate(goals):
            if not isinstance(g, Mapping) or not isinstance(g.get("jar"), str) or not g["jar"]:
                raise YofinaError(ErrorCode.PARAMS_INVALID, f"goals[{i}] cần mã hũ `jar`.")
            if set(g) - GOAL_KEYS:
                raise YofinaError(ErrorCode.PARAMS_INVALID, f"goals[{i}] có trường không hợp lệ.")
            w = g.get("weight")
            if w is not None and (isinstance(w, bool) or not isinstance(w, int | float) or w <= 0):
                raise YofinaError(ErrorCode.PARAMS_INVALID, f"goals[{i}].weight phải lớn hơn 0.")
            t = g.get("target_vnd")
            if t is not None and (isinstance(t, bool) or not isinstance(t, int) or t < 1):
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID, f"goals[{i}].target_vnd phải là số nguyên dương."
                )
            d = g.get("target_date")
            if d is not None:
                try:
                    date.fromisoformat(str(d))
                except ValueError:
                    raise YofinaError(
                        ErrorCode.PARAMS_INVALID, f"goals[{i}].target_date phải có dạng YYYY-MM-DD."
                    ) from None
            clean.append(dict(g))
        shock = args.get("shock_id")
        if shock is not None and not isinstance(shock, str):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "shock_id phải là chuỗi.")
        relax = args.get("allow_relaxation")
        if relax is not None and not isinstance(relax, bool):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "allow_relaxation phải là true hoặc false.")
        return horizon, clean, shock, True if relax is None else relax

    # --- dựng bài toán ---------------------------------------------------------------------------
    def build(
        self,
        g: Gathered,
        *,
        horizon_months: int,
        goal_args: Sequence[Mapping[str, Any]],
        shock_id: str | None,
        allow_relaxation: bool,
    ) -> Built:
        s = self.pipeline.settings
        prm = s.allocation
        month_days = prm.month_days
        today = g.app_date
        salary = int_of((g.ctx.meta.get("profile") or {})["monthly_salary_vnd"])
        shock = find_shock(shock_id) if shock_id else None
        jars = {j["code"]: j for j in g.jar_rows}
        codes = [j["code"] for j in g.jar_rows]
        spend = {j["code"]: j.get("spend") or [] for j in g.ctx.jars}
        # chi thiết yếu theo LOẠI giao dịch (không gắn nghĩa vụ) của Chi hằng ngày và hũ obligation (`essential_spend`, repo.SQL_CONTEXT)
        essential_of = {
            j["code"]: j.get("essential_spend") or [] for j in g.ctx.jars if "essential_spend" in j
        }
        daily_spend = essential_of.get(DEFAULT_SPENDING_JAR, [])
        default_pay = resolve_obligation_pay_jar((j["code"], j["kind"]) for j in g.jar_rows)

        # nghĩa vụ quy về tháng (có cú sốc tăng giá thì loại bị tăng nặng hơn). Sàn của hũ gồm nghĩa vụ cứng (thiết yếu, nợ) trả từ hũ
        # đó; ngoài ra MỌI hũ (không theo mã) không nhận dưới tổng mọi nghĩa vụ đang hoạt động trả từ nó, kể cả khoản không thiết yếu
        # (Netflix ở Giải trí): cắt dưới mức đó thì khoản đã cam kết không trả được (#39, 26/11). Khoản không thiết yếu vẫn là phần
        # cắt được của lựa chọn khi sàn vượt thu nhập.
        oblig_floor = dict.fromkeys(codes, 0)
        owed = dict.fromkeys(codes, 0)
        obligations_total = 0
        cuttable = 0
        for ob in g.obligations:
            monthly = monthly_equivalent(ob, month_days, once_months=horizon_months, today=today)
            if shock is not None and shock.params.target_obligation_kind == ob["kind"]:
                pct = shock.params.expense_increase_percent or 0.0
                share = min(shock.params.duration_days or month_days, month_days) / month_days
                monthly = round(monthly * (1.0 + pct / 100.0 * share))
            obligations_total += monthly
            hard = bool(ob.get("is_essential")) or ob["kind"] in DEBT_KINDS
            pay = pay_jar_or_default(jars, ob.get("pay_jar_code"), default_pay)
            if pay in owed:
                owed[pay] += monthly
            if hard and pay in oblig_floor:
                oblig_floor[pay] += monthly
            elif not hard:
                cuttable += monthly

        # mục tiêu: khai ở hũ, rồi ghi đè theo tham số
        goals: dict[str, _Goal] = {}
        explicit_buffer = any(j.get("purpose") == "buffer" for j in jars.values())
        for code, j in jars.items():
            if j.get("goal_vnd") is not None and (
                is_goal_jar(j["kind"], j.get("purpose"))
                or (j["kind"] == "spending" and j.get("purpose") is None)
            ):
                goals[code] = _Goal(
                    code,
                    int_of(j["goal_vnd"]),
                    to_date(j.get("goal_date")),
                    int_of(j["balance_vnd"]),
                    1.0,
                )
        for ga in goal_args:
            code = ga["jar"]
            j = jars.get(code)
            if j is None:
                raise YofinaError(ErrorCode.JAR_NOT_FOUND, f"Không tìm thấy hũ {code}.")
            if not is_goal_jar(j["kind"], j.get("purpose")):
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID,
                    f"Hũ {j['name']} không dùng cho mục tiêu trong lộ trình.",
                )
            old = goals.get(code)
            target = ga.get("target_vnd") or (old.target_vnd if old else None)
            if target is None:
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID, f"Hũ {j['name']} chưa có mục tiêu: cần target_vnd."
                )
            when = (
                date.fromisoformat(str(ga["target_date"]))
                if ga.get("target_date")
                else (old.target_date if old else None)
            )
            goals[code] = _Goal(
                code,
                int(target),
                when,
                int_of(j["balance_vnd"]),
                float(ga.get("weight") or (old.weight if old else 1.0)),
            )

        # thu nhập
        income = salary
        if shock is not None:
            income = round(salary * income_factor(shock, month_days))
            income = max(income - (shock.params.extra_cost_vnd or 0), 0)

        specs: list[JarSpec] = []
        split: dict[str, float] = {}
        for code in codes:
            j = jars[code]
            kind = j["kind"]
            pct = float(j["split_percent"])
            split[code] = pct
            goal = goals.get(code)
            if code == DEFAULT_SPENDING_JAR:
                essential_spend = daily_spend
            elif kind == "obligation":
                essential_spend = essential_of.get(code, [])
            else:
                essential_spend = spend.get(code, [])
            monthly_spend = variable_monthly_spend(
                essential_spend, s.resilience_window_days, month_days
            )
            if kind == "obligation":
                role = "obligation"
            elif goal is not None or j.get("purpose") == "goal":
                role = "goal"
            elif is_buffer_jar(kind, j.get("purpose"), j.get("goal_vnd")) and (
                j.get("purpose") == "buffer" or not explicit_buffer
            ):
                role = "emergency"
            elif kind == "saving":
                role = "saving"
            elif (
                monthly_spend > 0 if code == DEFAULT_SPENDING_JAR else code in s.essential_jar_codes
            ):
                role = "essential"
            else:
                role = "discretionary"
            floor = oblig_floor[code]
            tier = "obligation" if floor > 0 else "essential"
            # hũ chi tiêu thiết yếu, và hũ obligation với hóa đơn trả lẻ (không gắn nghĩa vụ đã khai): sàn gồm phần chi thiết yếu
            if role == "essential" or role == "obligation":
                floor += round(monthly_spend * prm.essential_floor_percent / 100.0)
            # không dưới tổng nghĩa vụ trả từ hũ (gồm khoản không thiết yếu); hũ không có khoản nào giữ sàn như trước
            floor = max(floor, owed[code])
            goal_spec = None
            if goal is not None:
                when = goal.target_date
                days_left = (when - today).days if when else horizon_months * month_days
                goal_spec = GoalSpec(
                    jar_code=code,
                    remaining_vnd=max(goal.target_vnd - goal.balance_vnd, 0),
                    days_left=days_left,
                    target_vnd=goal.target_vnd,
                    target_date=when,
                    weight=goal.weight,
                )
            specs.append(
                JarSpec(
                    code=code,
                    role=role,  # type: ignore[arg-type]
                    current_vnd=round(salary * pct / 100.0),
                    floor_vnd=floor,
                    floor_tier=tier,  # type: ignore[arg-type]
                    goal=goal_spec,
                    weight=goal.weight if goal else 1.0,
                )
            )
        problem = AllocationProblem(
            income_vnd=income, jars=tuple(specs), params=prm, allow_relaxation=allow_relaxation
        )
        return Built(
            problem=problem,
            horizon_months=horizon_months,
            income_vnd=income,
            obligations_monthly_vnd=obligations_total,
            cuttable_obligations_vnd=cuttable,
            goals=goals,
            jars=jars,
            split_percent=split,
        )

    # --- kết quả ----------------------------------------------------------------------------------
    @staticmethod
    def _ref(j: Mapping[str, Any]) -> dict[str, str]:
        return {
            **({"purpose": j["purpose"]} if j.get("purpose") is not None else {}),
            "code": j["code"],
            "name": j["name"],
            "color_key": j["color_key"],
            "icon_key": j["icon_key"],
        }

    def _data(self, g: Gathered, b: Built, sol: AllocationSolution) -> AllocationPlanData:
        today = g.app_date
        specs = {j.code: j for j in b.problem.jars}
        income = b.income_vnd
        lines: list[dict[str, Any]] = []
        for out in sol.jars:
            sp = specs[out.code]
            j = b.jars[out.code]
            lines.append(
                AllocationLine(
                    jar=ForecastJar.model_validate(self._ref(j)),
                    kind=JAR_KIND_TO_LINE[j["kind"]],  # type: ignore[arg-type]
                    # hũ thiết yếu theo vai, hoặc có sàn của khoản cứng; sàn chỉ vì khoản không thiết yếu (Netflix ở Giải trí) không biến
                    # hũ thành thiết yếu với model (bước giảm chi vẫn chọn được, tới sàn)
                    is_essential=sp.role in ("obligation", "essential", "emergency")
                    or (sp.floor_vnd > 0 and sp.floor_tier == "obligation"),
                    floor_vnd=sp.floor_vnd,
                    current_monthly_vnd=sp.current_vnd,
                    proposed_monthly_vnd=out.proposed_vnd,
                    split_percent_current=round(min(b.split_percent[out.code], 100.0), 2),
                    split_percent_proposed=round(min(100.0 * out.proposed_vnd / income, 100.0), 2)
                    if income
                    else 0.0,
                    floor_gap_vnd=out.floor_gap_vnd,
                ).model_dump()
            )
        goals: list[dict[str, Any]] = []
        for out in sol.jars:
            goal = b.goals.get(out.code)
            if goal is None:
                continue
            projected = project_date(today, out.days_to_goal)
            gp: dict[str, Any] = {
                "jar": self._ref(b.jars[out.code]),
                "target_vnd": goal.target_vnd,
                "on_track": out.goal_on_track,
                "shortfall_vnd": out.goal_shortfall_vnd,
                "monthly_needed_vnd": out.needed_vnd,
            }
            if goal.target_date is not None:
                gp["target_date"] = goal.target_date.isoformat()
            if projected is not None:
                gp["projected_date"] = projected.isoformat()
            goals.append(
                GoalProjection.model_validate(gp).model_dump(mode="json", exclude_none=True)
            )
        relaxations = [self._relaxation(b, r, specs) for r in sol.relaxations]
        alternatives: list[dict[str, Any]] = []
        if sol.status == "infeasible":
            alternatives = self._alternatives(b, sol, today)
        data = AllocationPlanData(
            status=sol.status,
            headline=self._headline(b, sol),
            horizon_months=b.horizon_months,
            period_start=self._period_start(g).isoformat(),
            income_monthly_vnd=income,
            obligations_monthly_vnd=b.obligations_monthly_vnd,
            lines=[AllocationLine.model_validate(x) for x in lines],
            unallocated_vnd=sol.unallocated_vnd,
            goals=[GoalProjection.model_validate(x) for x in goals],
            relaxations=relaxations,
            alternatives=[RoadmapAlternative.model_validate(a) for a in alternatives],
            solver=AllocationSolver(
                name="scipy.optimize.linprog",
                method=sol.method,
                status=sol.solver_status,
                elapsed_ms=sol.elapsed_ms,
                relaxation_rounds=sol.relaxation_rounds,
            ),
            basis=g.basis,
        )
        return data

    @staticmethod
    def _relaxation(b: Built, r: Any, specs: Mapping[str, JarSpec]) -> AllocationRelaxation:
        j = b.jars[r.jar_code]
        name = j["name"]
        if r.kind == "discretionary_reduced":
            return AllocationRelaxation(
                kind="discretionary_reduced",
                jar_code=r.jar_code,
                label=clip(f"Giảm hũ {name}", 60),
                before=f"{format_vnd(r.before_vnd)} mỗi tháng",
                after=f"{format_vnd(r.after_vnd)} mỗi tháng",
            )
        goal = b.goals[r.jar_code]
        when = goal.target_date
        before = _date_vn(when) if when else "hạn gốc"
        after = (
            _date_vn(when + timedelta(days=r.delay_months * b.problem.params.month_days))
            if when
            else f"lùi {r.delay_months} tháng"
        )
        return AllocationRelaxation(
            kind="goal_delayed",
            jar_code=r.jar_code,
            label=clip(f"Lùi hạn mục tiêu {name} thêm {r.delay_months} tháng", 60),
            before=before,
            after=after,
        )

    @staticmethod
    def _headline(b: Built, sol: AllocationSolution) -> str:
        names = {c: j["name"] for c, j in b.jars.items()}
        goal_names = ", ".join(names[c] for c in b.goals)
        if sol.status == "optimal":
            tail = f", mục tiêu {goal_names} kịp hạn." if b.goals else "."
            return clip(f"Phân bổ khả thi: đủ sàn mọi hũ{tail}", 160)
        if sol.status == "relaxed":
            parts = []
            for r in sol.relaxations:
                parts.append(
                    f"giảm hũ {names[r.jar_code]}"
                    if r.kind == "discretionary_reduced"
                    else f"lùi hạn mục tiêu {names[r.jar_code]}"
                )
            return clip("Phân bổ khả thi sau khi nới một lần: " + ", ".join(parts) + ".", 160)
        reasons = []
        if sol.floor_gap_total_vnd > 0:
            reasons.append(
                f"sàn bắt buộc vượt thu nhập {format_vnd(sol.floor_gap_total_vnd)} mỗi tháng"
            )
        late = [names[o.code] for o in sol.jars if o.code in b.goals and not o.goal_on_track]
        if late:
            reasons.append(f"mục tiêu {', '.join(late)} không kịp")
        return clip("Chưa khả thi: " + ", ".join(reasons or ["không đủ thu nhập"]) + ".", 160)

    @staticmethod
    def _period_start(g: Gathered) -> date:
        """Kỳ lộ trình bắt đầu từ ngày lương KẾ TIẾP theo `payday_day` của hồ sơ (lỗi P4-02, E5): tỷ lệ chia mới áp từ lần lương sau,
        và agent dựng các mốc tháng theo ngày-trong-tháng của `period_start`. Hồ sơ chưa có ngày lương thì giữ hôm nay."""
        payday_day = (g.ctx.meta.get("profile") or {}).get("payday_day")
        if payday_day is None:
            return g.app_date
        return next_payday(int(payday_day), g.app_date)

    def _alternatives(self, b: Built, sol: AllocationSolution, today: date) -> list[dict[str, Any]]:
        """Đúng hai lựa chọn nói thẳng khi vẫn vô nghiệm sau một vòng nới."""
        prm = b.problem.params
        late = [o for o in sol.jars if o.code in b.goals and not o.goal_on_track]
        if late:
            worst = max(late, key=lambda o: o.goal_shortfall_vnd)
            goal = b.goals[worst.code]
            name = b.jars[worst.code]["name"]
            when = goal.target_date
            days_left = (when - today).days if when else b.horizon_months * prm.month_days
            reachable = goal.balance_vnd + int(
                worst.proposed_vnd * max(days_left, 1) / prm.month_days
            )
            reachable = max(
                reachable // prm.rounding_step_vnd * prm.rounding_step_vnd, goal.balance_vnd
            )
            delay_metrics = (
                [
                    ActionChange(
                        label="Hạn mục tiêu",
                        before=_date_vn(when),
                        after=_date_vn(
                            when + timedelta(days=prm.relax_delay_months * prm.month_days)
                        ),
                    )
                ]
                if when
                else None
            )
            return [
                RoadmapAlternative(
                    option_id="lui_han",
                    kind="delay_goal",
                    label=clip(f"Lùi hạn {name} thêm {prm.relax_delay_months} tháng", 60),
                    summary=clip(
                        f"Giữ mục tiêu {format_vnd(goal.target_vnd)} và dời hạn để kịp sau khi các khoản bắt buộc giảm.",
                        200,
                    ),
                    jar_code=worst.code,
                    metrics=delay_metrics,
                ).model_dump(mode="json", exclude_none=True),
                RoadmapAlternative(
                    option_id="giam_muc_tieu",
                    kind="reduce_goal",
                    label=clip(f"Giảm mục tiêu {name} còn {format_vnd(reachable)}", 60),
                    summary=clip(
                        (
                            f"Giữ hạn {_date_vn(when)} và giảm số tiền cần dành."
                            if when
                            else "Giảm số tiền cần dành."
                        ),
                        200,
                    ),
                    jar_code=worst.code,
                    metrics=[
                        ActionChange(
                            label=clip(f"Mục tiêu {name}", 60),
                            before=format_vnd(goal.target_vnd),
                            after=format_vnd(reachable),
                        )
                    ],
                ).model_dump(mode="json", exclude_none=True),
            ]
        gap = sol.floor_gap_total_vnd
        biggest = max(b.problem.jars, key=lambda j: j.floor_vnd)
        return [
            RoadmapAlternative(
                option_id="cat_khoan_dinh_ky",
                kind="cut_discretionary",
                label="Cắt khoản định kỳ không thiết yếu",
                summary=clip(
                    f"Bỏ các khoản định kỳ không thiết yếu giúp giảm khoảng {format_vnd(b.cuttable_obligations_vnd)} mỗi tháng.",
                    200,
                ),
                metrics=[
                    ActionChange(
                        label="Nghĩa vụ hằng tháng",
                        before=format_vnd(b.obligations_monthly_vnd),
                        after=format_vnd(
                            max(b.obligations_monthly_vnd - b.cuttable_obligations_vnd, 0)
                        ),
                    )
                ],
            ).model_dump(mode="json", exclude_none=True),
            RoadmapAlternative(
                option_id="giam_chi_thiet_yeu",
                kind="cut_discretionary",
                label="Giảm chi tiêu thiết yếu hoặc tăng thu nhập",
                summary=clip(
                    f"Cần giảm thêm hoặc bù khoảng {format_vnd(gap)} mỗi tháng ở các khoản bắt buộc.",
                    200,
                ),
                jar_code=biggest.code,
            ).model_dump(mode="json", exclude_none=True),
        ]

    # --- điểm vào ------------------------------------------------------------------------------
    def optimize(self, user_id: str, args: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Kết quả tool `planner___optimize_allocation`: `{status, as_of, app_date, data}`."""
        horizon, goal_args, shock_id, allow = self._args(args or {})
        if shock_id:
            find_shock(shock_id)  # mã lạ thì SHOCK_NOT_FOUND trước khi đọc dữ liệu
        now = self.pipeline.now()
        g = self.resilience.gather(user_id, now)
        built = self.build(
            g,
            horizon_months=horizon,
            goal_args=goal_args,
            shock_id=shock_id,
            allow_relaxation=allow,
        )
        solution = optimize(built.problem)
        data = self._data(g, built, solution)
        log.info(
            "optimize_allocation status=%s ms=%s",
            solution.status,
            solution.elapsed_ms,
        )
        return {
            "status": str(ToolStatus.OK),
            "as_of": format_instant(now),
            "app_date": g.app_date.isoformat(),
            "data": data.model_dump(mode="json", exclude_none=True),
        }


__all__ = ["AllocationEngine"]
