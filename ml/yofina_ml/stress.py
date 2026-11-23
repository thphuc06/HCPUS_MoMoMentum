"""Cú sốc (phase 4, F4): áp MỘT cú sốc của `shocks.json` lên đầu vào dự báo và Monte Carlo cùng dãy số ngẫu nhiên với dự báo nền.

Hai phần, cùng một định nghĩa cú sốc (`ShockLike`: đúng hình dạng của `yofina_core.resilience.ShockLike`, mọi tham số đọc từ
`shocks.json`; gói ML không import `yofina_core`):

1. **Điểm trước và sau** (`shock_score_inputs`): biến `ResilienceInputs` (số tiền của một kỳ, xem `resilience.py`) thành đầu vào SAU
   cú sốc rồi chấm bằng đúng công thức đã chấm điểm hiện tại, nên điểm TRƯỚC của cú sốc chính là điểm đang hiện ở màn "Nhìn trước".
   - mất thu nhập `L%` trong `D` ngày: thu nhập của kỳ nhân `1 - L% x min(D, kỳ) / kỳ`; đóng góp mục tiêu mỗi tháng nhân cùng hệ số
     (lương ít đi thì phần chia vào hũ mục tiêu cũng ít đi);
   - tăng chi phí `p%` của loại nghĩa vụ `k`: nghĩa vụ loại `k` của kỳ tăng `p% x min(D, kỳ) / kỳ`;
   - chi phí một lần `X`: số dư khả dụng giảm `X`, tỷ lệ chi trên thu của kỳ cộng `X` (nhưng không làm tăng mức chi mỗi ngày).
2. **Số ngày trụ được, khoản thiếu** (`shock_forecast_inputs` rồi `simulate_stress`): đổi LỊCH của `ForecastInputs` (lương, nghĩa vụ, khoản
   chi một lần) rồi mô phỏng số dư TỔNG của mọi hũ bằng Monte Carlo. Mỗi hũ có một hạt giống theo (seed, ngày gốc, mã hũ) (xem
   `montecarlo.py`), nên đường chi tiêu của kịch bản gốc và kịch bản sốc là CÙNG một dãy số ngẫu nhiên (common random numbers): ta
   sinh chi tiêu một lần cho mỗi hũ rồi dùng lại cho cả hai lịch. Chênh lệch trước-sau không bị nhiễu mẫu.

   Lương bị mất theo đơn vị "một kỳ lương" (`month_days` ngày): cú sốc `L%` trong `D` ngày làm mất `L% x D / month_days` kỳ lương, trừ lần
   lượt vào các ngày lương kế tiếp. Mất việc 60 ngày mất đúng hai ngày lương liền (cùng giả định "chi tiêu và nghĩa vụ vẫn như cũ"
   của điểm Save: không còn thu nhập nào); ốm 7 ngày mất 7/30 của ngày lương kế tiếp dù ngày lương rơi ngoài cửa sổ.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Protocol

import numpy as np

from yofina_ml.calibration import calibration_from_dict
from yofina_ml.forecast import _flows, make_context
from yofina_ml.marginals import marginal_from_state
from yofina_ml.montecarlo import SimSpec, balance_from_draws, draw_paths, jar_seed_sequence
from yofina_ml.resilience import GoalFact, ResilienceInputs
from yofina_ml.types import ForecastInputs, ForecastResult, JarInput, ScheduledFlow


class ShockParamsLike(Protocol):
    duration_days: int | None
    income_loss_percent: float | None
    extra_cost_vnd: int | None
    expense_increase_percent: float | None
    target_obligation_kind: str | None


class ShockLike(Protocol):
    @property
    def params(self) -> ShockParamsLike: ...


def _share(duration_days: int, window_days: int) -> float:
    return min(duration_days, window_days) / window_days


def income_factor(shock: ShockLike, window_days: int) -> float:
    """Phần thu nhập của kỳ còn lại sau cú sốc (1 là không đổi)."""
    loss = shock.params.income_loss_percent
    if loss is None:
        return 1.0
    return 1.0 - (loss / 100.0) * _share(shock.params.duration_days or window_days, window_days)


def shock_score_inputs(i: ResilienceInputs, shock: ShockLike) -> ResilienceInputs:
    """`ResilienceInputs` SAU cú sốc (xem docstring module)."""
    p = shock.params
    factor = income_factor(shock, i.window_days)
    out = replace(
        i,
        income_vnd=round(i.income_vnd * factor),
        goals=tuple(
            GoalFact(
                g.jar_code,
                g.monthly_needed_vnd,
                round(g.monthly_contribution_vnd * factor),
            )
            for g in i.goals
        ),
    )
    if p.expense_increase_percent is not None and p.target_obligation_kind is not None:
        kind = p.target_obligation_kind
        extra = round(
            i.obligations_by_kind.get(kind, 0)
            * (p.expense_increase_percent / 100.0)
            * _share(p.duration_days or i.window_days, i.window_days)
        )
        by_kind = dict(i.obligations_by_kind)
        by_kind[kind] = by_kind.get(kind, 0) + extra
        out = replace(out, obligations_vnd=i.obligations_vnd + extra, obligations_by_kind=by_kind)
    if p.extra_cost_vnd:
        out = replace(
            out,
            liquid_balance_vnd=i.liquid_balance_vnd - p.extra_cost_vnd,
            one_off_spend_vnd=i.one_off_spend_vnd + p.extra_cost_vnd,
        )
    return out


# --- lịch của ForecastInputs ---------------------------------------------------------------------
def _salary_flows(
    flows: tuple[ScheduledFlow, ...], shock: ShockLike, month_days: int
) -> tuple[ScheduledFlow, ...]:
    """Lương bị mất theo đơn vị "một kỳ lương": cú sốc `L%` trong `D` ngày làm mất `L% x D / month_days` kỳ lương, trừ lần lượt vào các
    ngày lương kế tiếp (mỗi ngày lương mất tối đa trọn vẹn). Mất việc 60 ngày mất đúng hai ngày lương liền; ốm 7 ngày mất 7/30 của ngày
    lương kế tiếp."""
    p = shock.params
    if p.income_loss_percent is None or not p.duration_days:
        return flows
    remaining = (p.income_loss_percent / 100.0) * p.duration_days / month_days
    kept: list[ScheduledFlow] = []
    last: date | None = None
    taken = 0.0
    for f in sorted(flows, key=lambda x: x.date):
        if f.date != last:  # các hũ chia chung một ngày lương: cùng một phần bị mất
            last = f.date
            taken = min(1.0, remaining)
            remaining -= taken
        amount = round(f.amount_vnd * (1.0 - taken))
        if amount > 0:
            kept.append(replace(f, amount_vnd=amount))
    return tuple(kept)


def _scaled(f: ScheduledFlow, factor: float) -> ScheduledFlow:
    lo, hi = f.amount_min_vnd, f.amount_max_vnd
    new_lo = None if lo is None else round(lo * factor)
    new_hi = None if hi is None else round(hi * factor)
    amount = round(f.amount_vnd * factor)
    return replace(
        f,
        amount_vnd=amount,
        amount_min_vnd=None if new_lo is None else min(new_lo, amount),
        amount_max_vnd=None if new_hi is None else max(new_hi, amount),
    )


def shock_forecast_inputs(
    inputs: ForecastInputs,
    shock: ShockLike,
    *,
    obligation_kinds: Mapping[str, str],
    cost_jar: str | None,
    extra_cost_label: str,
    month_days: int,
) -> ForecastInputs:
    """`ForecastInputs` SAU cú sốc: đổi lịch lương, lịch nghĩa vụ và thêm khoản chi một lần. `obligation_kinds` ánh xạ `ref_id` của
    nghĩa vụ sang loại của nó; `cost_jar` là hũ trả khoản chi một lần (người dùng không có hũ nào thì cú sốc có chi phí một lần bị lỗi)."""
    p = shock.params
    end = inputs.app_date + timedelta(days=p.duration_days or 0)
    jars: list[JarInput] = []
    for jar in inputs.jars:
        inflows = _salary_flows(jar.inflows, shock, month_days)
        outflows = jar.outflows
        if p.expense_increase_percent is not None and p.target_obligation_kind is not None:
            factor = 1.0 + p.expense_increase_percent / 100.0
            outflows = tuple(
                _scaled(f, factor)
                if f.ref_id is not None
                and obligation_kinds.get(f.ref_id) == p.target_obligation_kind
                and f.date <= end
                else f
                for f in outflows
            )
        if p.extra_cost_vnd and jar.code == cost_jar:
            first = inputs.app_date + timedelta(days=1)
            outflows = tuple(
                sorted(
                    (
                        *outflows,
                        ScheduledFlow(
                            date=first,
                            kind="obligation",
                            label=extra_cost_label,
                            amount_vnd=p.extra_cost_vnd,
                        ),
                    ),
                    key=lambda f: (f.date, f.label),
                )
            )
        jars.append(replace(jar, inflows=inflows, outflows=outflows))
    if p.extra_cost_vnd and cost_jar is None:
        raise ValueError("cú sốc có chi phí một lần cần một hũ để trả")
    return replace(inputs, jars=tuple(jars))


# --- Monte Carlo ---------------------------------------------------------------------------------
@dataclass(frozen=True)
class StressSim:
    """Phân vị theo ngày của số dư TỔNG (mọi hũ dự báo) và chi tiêu kỳ vọng tích lũy, cho cả nền và sốc."""

    n_paths: int
    horizon_days: int
    base_total_p50: np.ndarray
    shocked_total_p50: np.ndarray
    shocked_total_p10: np.ndarray
    #: chi tiêu kỳ vọng tích lũy của mọi hũ sau mỗi ngày (chi thay đổi + nghĩa vụ + khoản một lần), lịch SAU sốc
    shocked_outflow_cum: np.ndarray
    base_outflow_cum: np.ndarray


def simulate_stress(
    base: ForecastInputs,
    shocked: ForecastInputs,
    previous: ForecastResult,
    *,
    n_paths: int,
) -> StressSim:
    """Số dư TỔNG của nền và của kịch bản sốc trên CÙNG dãy số ngẫu nhiên. `previous` là lần dự báo gần nhất (nó giữ phân phối chi
    tiêu đã fit và hiệu chỉnh trong `run.params`); `base` và `shocked` cùng ngày gốc, cùng horizon, cùng hũ."""
    if base.app_date != shocked.app_date or base.horizon_days != shocked.horizon_days:
        raise ValueError("nền và kịch bản sốc phải cùng ngày gốc và cùng horizon")
    params = previous.run.params or {}
    states = params.get("jar_state") or {}
    cal = calibration_from_dict(params["calibration"]) if "calibration" in params else None
    cfg = replace(base.config, n_paths=n_paths)
    base = replace(base, config=cfg)
    ctx = make_context(base, cal)
    horizon = base.horizon_days
    by_code = {j.code: j for j in shocked.jars}
    total_b = np.zeros((ctx.n_paths, horizon))
    total_s = np.zeros((ctx.n_paths, horizon))
    out_b = np.zeros((ctx.n_paths, horizon))
    out_s = np.zeros((ctx.n_paths, horizon))
    for jar in base.jars:
        st = states.get(jar.code)
        if not st or not st.get("marginal"):
            raise KeyError(f"hũ {jar.code} không có trạng thái phân phối chi tiêu để mô phỏng")
        sj = by_code[jar.code]
        marg = marginal_from_state(st["marginal"])
        kind = st["series_kind"]
        cal_kind = ctx.cal.for_kind(kind)
        ss = jar_seed_sequence(cfg.seed, base.app_date, jar.code)

        def spec(j: JarInput, marg=marg, kind=kind) -> SimSpec:
            inflow, outflow, ranged = _flows(j, base.app_date, horizon)
            return SimSpec(
                balance_vnd=float(j.balance_vnd),
                marginal=marg,
                feats=ctx.f_fut,
                sparse=kind == "sparse",
                inflow=inflow,
                outflow=outflow,
                ranged=ranged,
                window=0,
            )

        spec_b, spec_s = spec(jar), spec(sj)
        draws = draw_paths(spec_b, float(cal_kind.rho), ctx.n_paths, ss)
        sigma = float(cal_kind.level_sigma)
        total_b += balance_from_draws(spec_b, draws, sigma)
        total_s += balance_from_draws(spec_s, draws, sigma)
        spend = draws.spend
        if sigma > 0.0:
            spend = spend * np.exp(sigma * draws.xi - 0.5 * sigma * sigma)[:, None]
        for sp, acc in ((spec_b, out_b), (spec_s, out_s)):
            flow = sp.outflow[None, :] + spend
            for k, (idx, _lo, _hi) in enumerate(sp.ranged):
                flow[:, idx] += draws.ranged_amounts[:, k]
            acc += flow
    return StressSim(
        n_paths=ctx.n_paths,
        horizon_days=horizon,
        base_total_p50=np.quantile(total_b, 0.5, axis=0),
        shocked_total_p50=np.quantile(total_s, 0.5, axis=0),
        shocked_total_p10=np.quantile(total_s, 0.1, axis=0),
        shocked_outflow_cum=np.cumsum(out_s.mean(axis=0)),
        base_outflow_cum=np.cumsum(out_b.mean(axis=0)),
    )


@dataclass(frozen=True)
class StressOutcome:
    """Số rút ra từ mô phỏng. Chỉ số ngày (0 là ngày gốc + 1)."""

    runway_days_total: int | None
    runway_days_emergency: int | None
    shortfall_vnd: int
    shortfall_index: int | None
    need_vnd: int
    shortfall_ratio: float
    status: str
    base_runway_days_total: int | None
    base_shortfall_vnd: int


def _runway(p50: np.ndarray, threshold: float) -> tuple[int | None, int]:
    """(số ngày trụ được hoặc None nếu trụ hết khoảng dự báo, chỉ số ngày đầu tiên số dư P50 xuống DƯỚI ngưỡng hoặc -1)."""
    hit = np.nonzero(p50 < threshold)[0]
    if len(hit) == 0:
        return None, -1
    return int(hit[0]), int(hit[0])


def summarize_stress(
    sim: StressSim,
    *,
    duration_days: int,
    emergency_balance_vnd: int | None,
    runout_threshold_vnd: float,
    short_shortfall_ratio: float,
) -> StressOutcome:
    """Số ngày trụ được, khoản thiếu và trạng thái từ mô phỏng.

    - `runway_days_total`: số ngày liền từ ngày mai mà số dư TỔNG (P50) còn không dưới ngưỡng cạn; None là trụ hết khoảng dự báo.
    - `runway_days_emergency`: số ngày mà RIÊNG hũ Dự phòng đủ trả mức chi kỳ vọng của mọi hũ (chi tiêu tích lũy sau sốc), tối đa bằng
      khoảng dự báo; None khi không có hũ Dự phòng.
    - `shortfall_vnd`: số tiền thiếu lớn nhất, tức mức sâu nhất của số dư TỔNG (P50) dưới ngưỡng cạn trong khoảng dự báo.
    - `status`: nhu cầu chi trong thời gian sốc là chi tiêu kỳ vọng tích lũy tới hết `duration_days`; thiếu từ `short_shortfall_ratio`
      của nhu cầu thì short, thiếu ít hơn thì tight, không thiếu thì ok.
    """
    runway, idx = _runway(sim.shocked_total_p50, runout_threshold_vnd)
    low = float(sim.shocked_total_p50.min())
    shortfall = math.ceil(max(runout_threshold_vnd - low, 0.0))
    base_runway, _ = _runway(sim.base_total_p50, runout_threshold_vnd)
    base_low = float(sim.base_total_p50.min())
    base_short = math.ceil(max(runout_threshold_vnd - base_low, 0.0))
    emergency: int | None = None
    if emergency_balance_vnd is not None:
        beyond = np.nonzero(sim.shocked_outflow_cum > max(emergency_balance_vnd, 0))[0]
        emergency = int(beyond[0]) if len(beyond) else sim.horizon_days
    span = min(max(duration_days, 1), sim.horizon_days)
    need = round(float(sim.shocked_outflow_cum[span - 1]))
    ratio = 0.0 if shortfall == 0 else (shortfall / need if need > 0 else math.inf)
    status = "ok" if shortfall == 0 else ("short" if ratio >= short_shortfall_ratio else "tight")
    return StressOutcome(
        runway_days_total=runway,
        runway_days_emergency=emergency,
        shortfall_vnd=shortfall,
        shortfall_index=idx if shortfall > 0 and idx >= 0 else None,
        need_vnd=need,
        shortfall_ratio=ratio,
        status=status,
        base_runway_days_total=base_runway,
        base_shortfall_vnd=base_short,
    )


__all__ = [
    "StressOutcome",
    "StressSim",
    "income_factor",
    "shock_forecast_inputs",
    "shock_score_inputs",
    "simulate_stress",
    "summarize_stress",
]
