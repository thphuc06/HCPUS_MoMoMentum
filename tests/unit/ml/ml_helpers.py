"""Dựng đầu vào nhỏ cho test của gói ML (không dùng bộ sinh backtest để test không phụ thuộc vào nó)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import numpy as np

from yofina_ml.types import (
    CoverageInputs,
    ForecastConfig,
    ForecastInputs,
    JarInput,
    ScheduledFlow,
)

APP_DATE = date(2026, 11, 21)  # thứ bảy


def history(
    n: int, seed: int = 0, p: float = 0.9, med: float = 40_000, weekend: float = 1.5
) -> tuple[int, ...]:
    """Chi tiêu ngày giả lập (có hiệu ứng cuối tuần), n ngày kết thúc ở APP_DATE - 1."""
    rng = np.random.default_rng(seed)
    start = APP_DATE - timedelta(days=n)
    out = []
    for i in range(n):
        d = start + timedelta(days=i)
        has = rng.random() < p
        amt = med * (weekend if d.weekday() >= 5 else 1.0) * np.exp(0.4 * rng.standard_normal())
        out.append(int(round(amt, -3)) if has else 0)
    return tuple(out)


def jar(
    code: str = "an_uong",
    *,
    n: int = 60,
    seed: int = 0,
    balance: int = 1_000_000,
    kind: str = "spending",
    p: float = 0.9,
    med: float = 40_000,
    inflows: tuple[ScheduledFlow, ...] = (),
    outflows: tuple[ScheduledFlow, ...] = (),
    spend: tuple[int, ...] | None = None,
) -> JarInput:
    sp = history(n, seed, p, med) if spend is None else spend
    return JarInput(
        code=code,
        kind=kind,  # type: ignore[arg-type]
        balance_vnd=balance,
        split_percent=20.0,
        history_start=APP_DATE - timedelta(days=len(sp)),
        daily_spend_vnd=sp,
        inflows=inflows,
        outflows=outflows,
    )


def salary(day_offset: int, amount: int = 3_000_000) -> ScheduledFlow:
    return ScheduledFlow(APP_DATE + timedelta(days=day_offset), "salary", "Lương", amount)


def obligation(
    day_offset: int,
    amount: int,
    lo: int | None = None,
    hi: int | None = None,
    label: str = "Tiền trọ",
) -> ScheduledFlow:
    return ScheduledFlow(
        APP_DATE + timedelta(days=day_offset), "obligation", label, amount, lo, hi, label
    )


def inputs(
    jars: tuple[JarInput, ...] | None = None,
    *,
    horizon: int = 30,
    payday_offset: int = 14,
    config: ForecastConfig | None = None,
    coverage: CoverageInputs | None = None,
) -> ForecastInputs:
    next_payday = APP_DATE + timedelta(days=payday_offset)
    paydays = tuple(
        d
        for d in (next_payday, next_payday + timedelta(days=30), next_payday + timedelta(days=60))
        if d <= APP_DATE + timedelta(days=horizon)
    )
    if jars is None:
        jars = (
            jar("an_uong", n=60, seed=1, balance=900_000, inflows=(salary(payday_offset),)),
            jar("giai_tri", n=60, seed=2, p=0.2, med=90_000, balance=700_000),
            jar("nghia_vu", n=60, seed=3, kind="obligation", p=0.0, balance=2_000_000,
                outflows=(obligation(5, 1_200_000), obligation(20, 300_000, 250_000, 350_000, "Tiền điện"))),
        )  # fmt: skip
    return ForecastInputs(
        app_date=APP_DATE,
        horizon_days=horizon,
        next_payday=next_payday,
        payday_dates=paydays,
        jars=jars,
        coverage=coverage,
        config=config or ForecastConfig(n_paths=1000, seed=5),
        payday_day=next_payday.day,
    )


def with_config(inp: ForecastInputs, **kw) -> ForecastInputs:
    return replace(inp, config=replace(inp.config, **kw))
