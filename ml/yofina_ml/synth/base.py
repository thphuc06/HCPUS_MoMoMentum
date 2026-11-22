"""Cấu trúc chung của bộ sinh dữ liệu tổng hợp CHỈ DÙNG ĐỂ BACKTEST (không phải persona demo, không phải mã sản phẩm).

Một `SynthPersona` có chi tiêu từng ngày của các hũ, lịch nghĩa vụ đã khai và thực tế, lương, sổ cái (số dư cuối ngày) và (nếu
có) điểm gãy lối sống. `build_inputs` dựng `ForecastInputs` tại một origin giống hệt cách pipeline sẽ dựng từ DB (lịch sử
tới `app_date - 1`, lương chia theo tỷ lệ, nghĩa vụ mở rộng chu kỳ), để backtest chạy đúng hàm sản phẩm `forecast_user`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from yofina_ml.daycal import payday_in_month
from yofina_ml.types import (
    CoverageInputs,
    ForecastConfig,
    ForecastInputs,
    JarInput,
    ScheduledFlow,
)

OBLIGATION_JAR = "nghia_vu"


@dataclass(frozen=True)
class SynthJar:
    code: str
    kind: str  # spending | saving | obligation
    split_percent: float
    spend: (
        np.ndarray
    )  # (n_days,) chi tiêu ngẫu nhiên từng ngày, VND nguyên (không gồm nghĩa vụ theo lịch)


@dataclass(frozen=True)
class ObligationSpec:
    """Nghĩa vụ hằng tháng người dùng đã khai."""

    label: str
    day: int  # ngày trong tháng
    expected_vnd: int
    min_vnd: int | None = None
    max_vnd: int | None = None
    jitter: bool = True  # thực tế đôi khi lệch +-1 ngày
    step_date: date | None = None  # từ ngày này số tiền kỳ vọng đổi (ví dụ tăng tiền trọ)
    step_vnd: int | None = None

    def expected_on(self, d: date) -> int:
        if self.step_date is not None and self.step_vnd is not None and d >= self.step_date:
            return self.step_vnd
        return self.expected_vnd


@dataclass(frozen=True)
class SynthPersona:
    family: str
    config: str
    seed: int
    start: date
    n_days: int
    payday_day: int
    salary_vnd: np.ndarray  # (n_days,) lương nhận trong ngày (0 nếu không phải ngày lương)
    jars: tuple[SynthJar, ...]
    obligations: tuple[ObligationSpec, ...]
    obligation_paid: np.ndarray  # (n_days,) tiền nghĩa vụ thực rút từ hũ nghĩa vụ mỗi ngày
    balances: dict[str, np.ndarray]  # số dư cuối ngày của từng hũ (kể cả hũ nghĩa vụ)
    break_index: int | None

    def day(self, i: int) -> date:
        return self.start + timedelta(days=i)

    def jar(self, code: str) -> SynthJar:
        return next(j for j in self.jars if j.code == code)

    @property
    def spending_codes(self) -> list[str]:
        return [j.code for j in self.jars if j.kind != "obligation"]


def month_iter(first: date, last: date):
    y, m = first.year, first.month
    while date(y, m, 1) <= last:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def payday_list(payday_day: int, after: date, through: date) -> list[date]:
    out = [
        payday_in_month(payday_day, y, m)
        for y, m in month_iter(after - timedelta(days=31), through)
    ]
    return sorted(d for d in out if after < d <= through)


def build_ledger(
    start: date,
    n_days: int,
    payday_day: int,
    salary_by_payday: dict[date, int],
    jars: tuple[SynthJar, ...],
    obligation_paid: np.ndarray,
    initial_cycles: float = 1.0,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Lương mỗi ngày và số dư cuối ngày của từng hũ. Số dư đầu kỳ là `initial_cycles` lần phần chia của một kỳ lương."""
    salary = np.zeros(n_days, dtype=np.int64)
    first_salary = next(iter(sorted(salary_by_payday.values())), 0)
    for i in range(n_days):
        d = start + timedelta(days=i)
        if d in salary_by_payday:
            salary[i] = salary_by_payday[d]
    balances: dict[str, np.ndarray] = {}
    for j in jars:
        inflow = np.rint(salary * (j.split_percent / 100.0)).astype(np.int64)
        out = obligation_paid if j.code == OBLIGATION_JAR else j.spend
        bal0 = round(first_salary * j.split_percent / 100.0 * initial_cycles)
        balances[j.code] = bal0 + np.cumsum(inflow - out)
    return salary, balances


def expand_obligations(
    specs: tuple[ObligationSpec, ...], after: date, through: date
) -> list[tuple[date, ObligationSpec]]:
    out: list[tuple[date, ObligationSpec]] = []
    for y, m in month_iter(after - timedelta(days=31), through):
        for sp in specs:
            d = payday_in_month(sp.day, y, m)
            if after < d <= through:
                out.append((d, sp))
    out.sort(key=lambda t: (t[0], t[1].label))
    return out


def declared_salary(persona: SynthPersona, i: int) -> int:
    """Lương người dùng đã khai tại thời điểm i: lần nhận lương gần nhất."""
    idx = np.nonzero(persona.salary_vnd[: i + 1] > 0)[0]
    return int(persona.salary_vnd[idx[-1]]) if len(idx) else int(persona.salary_vnd.max())


def build_inputs(
    persona: SynthPersona, origin: int, horizon: int, config: ForecastConfig
) -> ForecastInputs:
    """Đầu vào `forecast_user` tại origin: `origin` ngày lịch sử, `app_date` là ngày chỉ số `origin`."""
    app_date = persona.day(origin)
    end = app_date + timedelta(days=horizon)
    paydays = payday_list(persona.payday_day, app_date, end)
    next_payday = (
        paydays[0]
        if paydays
        else payday_list(persona.payday_day, app_date, end + timedelta(days=62))[0]
    )
    salary = declared_salary(persona, origin)
    jars = []
    for j in persona.jars:
        inflows = tuple(
            ScheduledFlow(d, "salary", "Lương", round(salary * j.split_percent / 100.0))
            for d in paydays
            if round(salary * j.split_percent / 100.0) > 0
        )
        outflows: tuple[ScheduledFlow, ...] = ()
        if j.code == OBLIGATION_JAR:
            outflows = tuple(
                ScheduledFlow(
                    d, "obligation", sp.label, sp.expected_on(d), sp.min_vnd, sp.max_vnd, sp.label
                )
                for d, sp in expand_obligations(persona.obligations, app_date, end)
            )
        jars.append(
            JarInput(
                code=j.code,
                kind=j.kind,  # type: ignore[arg-type]
                balance_vnd=int(persona.balances[j.code][origin]),
                split_percent=j.split_percent,
                history_start=persona.start,
                daily_spend_vnd=tuple(int(v) for v in j.spend[:origin]),
                inflows=inflows,
                outflows=outflows,
            )
        )
    income = int(persona.salary_vnd[:origin].sum())
    spend = int(
        sum(j.spend[:origin].sum() for j in persona.jars) + persona.obligation_paid[:origin].sum()
    )
    tot = np.sum([b for b in persona.balances.values()], axis=0)
    cov = CoverageInputs(income, spend, int(tot[0]), int(tot[origin])) if origin > 0 else None
    return ForecastInputs(
        app_date=app_date,
        horizon_days=horizon,
        next_payday=next_payday,
        payday_dates=tuple(paydays),
        jars=tuple(jars),
        coverage=cov,
        config=config,
        payday_day=persona.payday_day,
    )


def schedule_obligation_payments(
    rng: np.random.Generator,
    specs: tuple[ObligationSpec, ...],
    start: date,
    n_days: int,
) -> np.ndarray:
    """Tiền nghĩa vụ thực rút mỗi ngày: số tiền ngẫu nhiên đều trong khoảng đã khai, ngày lệch +-1 với xác suất 20%."""
    paid = np.zeros(n_days, dtype=np.int64)
    last = start + timedelta(days=n_days - 1)
    for d, sp in expand_obligations(specs, start - timedelta(days=1), last):
        amt = sp.expected_on(d)
        if sp.min_vnd is not None and sp.max_vnd is not None and sp.max_vnd > sp.min_vnd:
            amt = int(round(rng.uniform(sp.min_vnd, sp.max_vnd), -3))
        idx = (d - start).days
        if sp.jitter and rng.random() < 0.2:
            idx += int(rng.choice([-1, 1]))
        paid[min(max(idx, 0), n_days - 1)] += amt
    return paid
