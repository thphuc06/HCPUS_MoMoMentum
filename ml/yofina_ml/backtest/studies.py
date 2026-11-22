"""Các khảo sát phụ của backtest: độ dài lịch sử tối thiểu (cổng khởi đầu lạnh), ablation của hurdle, so với StatsForecast.

Đo ở mức bảng phân vị chi tiêu NGÀY thô (không ACI, không Monte Carlo): pinball trung bình P10/P50/P90 tương đối so với
seasonal naive (`SeasonalNaiveModel`) và độ phủ P10-P90 theo ngày.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import timedelta
from typing import Any

import numpy as np

from yofina_ml.backtest.common import HORIZON, TAUS, mean_pinball, origins
from yofina_ml.models import (
    ColdStartRulesModel,
    HurdleCalendarModel,
    SeasonalNaiveModel,
)
from yofina_ml.params import MLParams
from yofina_ml.synth.base import OBLIGATION_JAR, SynthPersona, build_inputs
from yofina_ml.types import ForecastConfig, ForecastInputs, JarInput


def _truncate(inputs: ForecastInputs, length: int) -> ForecastInputs:
    start = inputs.app_date - timedelta(days=length)
    jars = tuple(
        replace(j, daily_spend_vnd=j.daily_spend_vnd[-length:], history_start=start)
        for j in inputs.jars
    )
    return replace(inputs, jars=jars)


def _models(inputs: ForecastInputs, jar: JarInput, prm: MLParams) -> dict[str, Any]:
    budget = next((float(f.amount_vnd) for f in jar.inflows), float(max(jar.balance_vnd, 0)))
    return {
        "hurdle_calendar": HurdleCalendarModel(prm, inputs.payday_day),
        "seasonal_naive": SeasonalNaiveModel(prm, inputs.payday_day),
        "cold_start_rules": ColdStartRulesModel(
            prm, inputs.payday_day, kind=jar.kind, monthly_budget_vnd=budget
        ),
    }


def _predict(model: Any, inputs: ForecastInputs, jar: JarInput) -> np.ndarray:
    fut = tuple(inputs.app_date + timedelta(days=i + 1) for i in range(inputs.horizon_days))
    tab = model.predict(jar.daily_spend_vnd, jar.history_start, fut, inputs.payday_dates, TAUS)
    return np.array(tab, dtype=float).T


def short_history(
    personas_: list[SynthPersona],
    lengths: tuple[int, ...] = (7, 14, 21, 30, 45, 60, 90),
    windows: int = 8,
    horizon: int = HORIZON,
) -> dict[int, dict[str, dict[str, float]]]:
    """Pinball tương đối so với seasonal naive (cùng độ dài lịch sử) và độ phủ ngày, theo độ dài L và mô hình."""
    prm = MLParams()
    acc: dict[int, dict[str, dict[tuple, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0, 0.0]))
    )
    for p in personas_:
        for length in lengths:
            hi = p.n_days - horizon - 2
            starts = np.linspace(0, hi - length, windows).astype(int)
            for s in starts:
                o = int(s) + length
                inputs = _truncate(build_inputs(p, o, horizon, ForecastConfig(seed=1)), length)
                for jar in inputs.jars:
                    if jar.kind == "obligation":
                        continue
                    y = p.jar(jar.code).spend[o + 1 : o + 1 + horizon].astype(float)
                    ms = _models(inputs, jar, prm)
                    q_sn = _predict(ms["seasonal_naive"], inputs, jar)
                    pl_sn = mean_pinball(y, q_sn)
                    for name, m in ms.items():
                        q = _predict(m, inputs, jar)
                        a = acc[length][name][(p.family, p.config, p.seed, jar.code)]
                        a[0] += mean_pinball(y, q)
                        a[1] += pl_sn
                        a[2] += float(np.mean((y >= q[0]) & (y <= q[2])))
                        a[3] += 1
    out: dict[int, dict[str, dict[str, float]]] = {}
    for length, by_model in acc.items():
        out[length] = {}
        for name, by_key in by_model.items():
            ratios = [a[0] / a[1] for a in by_key.values() if a[1] > 1e-9]
            covs = [a[2] / a[3] for a in by_key.values()]
            out[length][name] = {
                "rel_pl": float(np.mean(ratios)),
                "cov_daily": float(np.mean(covs)),
            }
    return out


ABLATIONS: dict[str, dict[str, Any]] = {
    "mặc định (nửa đời 180 ngày, co ô về xác suất chung kappa=20, số tiền = hệ số ô x phần dư chung)": {},
    "như spike: Beta(1,2) riêng từng ô, số tiền chung, không giảm trọng số": {
        "cell_shrink_days": None,
        "halflife_days": None,
        "amount_effect_shrink": None,
        "min_cell_positives": 10**6,
    },
    "số tiền theo lưới riêng từng ô khi đủ 15 mẫu (cách cũ)": {"amount_effect_shrink": None},
    "không co ô (Beta(1,2) riêng từng ô)": {"cell_shrink_days": None},
    "nửa đời 45 ngày": {"halflife_days": 45.0},
    "nửa đời 90 ngày": {"halflife_days": 90.0},
    "không giảm trọng số theo tuổi": {"halflife_days": None},
    "cửa sổ 90 ngày": {"fit_window_days": 90},
    "không dùng lịch (xác suất và số tiền chung mọi ô)": {
        "cell_shrink_days": 1e9,
        "amount_effect_shrink": 1e9,
    },
}


def ablation(
    personas_: list[SynthPersona], horizon: int = HORIZON, step: int = 14
) -> dict[str, dict[str, float]]:
    """Pinball của biến thể hurdle so với seasonal naive, theo họ bộ sinh."""
    acc: dict[str, dict[tuple, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    for p in personas_:
        for o in origins(p.n_days, horizon, 90, step):
            inputs = build_inputs(p, o, horizon, ForecastConfig(seed=1))
            for jar in inputs.jars:
                if jar.kind == "obligation":
                    continue
                y = p.jar(jar.code).spend[o + 1 : o + 1 + horizon].astype(float)
                sn = mean_pinball(
                    y, _predict(SeasonalNaiveModel(MLParams(), inputs.payday_day), inputs, jar)
                )
                for name, over in ABLATIONS.items():
                    prm = replace(MLParams(), **over)
                    q = _predict(HurdleCalendarModel(prm, inputs.payday_day), inputs, jar)
                    a = acc[name][(p.family, p.config, p.seed, jar.code)]
                    a[0] += mean_pinball(y, q)
                    a[1] += sn
    out: dict[str, dict[str, float]] = {}
    for name, by_key in acc.items():
        fams: dict[str, list[float]] = defaultdict(list)
        for (fam, *_), a in by_key.items():
            if a[1] > 1e-9:
                fams[fam].append(a[0] / a[1])
        out[name] = {f: float(np.mean(v)) for f, v in fams.items()}
        out[name]["all"] = float(np.mean([x for v in fams.values() for x in v]))
    return out


def statsforecast_compare(
    personas_: list[SynthPersona], horizon: int = HORIZON, step: int = 14
) -> dict[str, dict[str, float]]:
    """So với StatsForecast (SeasonalNaive và AutoETS season 7, khoảng native level 80; trung vị là điểm dự báo). Chỉ chạy
    được khi cài statsforecast (dev, tùy chọn): `uv run --with statsforecast==2.1.1 scripts/ml_backtest.py ...`."""
    try:
        import pandas as pd
        from statsforecast import StatsForecast
        from statsforecast.models import AutoETS
        from statsforecast.models import SeasonalNaive as SFSeasonalNaive
    except ImportError as e:  # pragma: no cover - phụ thuộc môi trường
        raise SystemExit(
            "Thiếu statsforecast: chạy `uv run --with statsforecast==2.1.1 scripts/ml_backtest.py ...`"
        ) from e
    prm = MLParams()
    acc: dict[str, dict[tuple, list[float]]] = defaultdict(
        lambda: defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    )
    for p in personas_:
        codes = [j.code for j in p.jars if j.kind != "obligation"]
        for o in origins(p.n_days, horizon, 90, step):
            dates = pd.date_range(p.start, periods=o, freq="D")
            df = pd.concat(
                [
                    pd.DataFrame(
                        {"unique_id": c, "ds": dates, "y": p.jar(c).spend[:o].astype(float)}
                    )
                    for c in codes
                ],
                ignore_index=True,
            )
            sf = StatsForecast(
                models=[
                    SFSeasonalNaive(season_length=7, alias="SF_SN"),
                    AutoETS(season_length=7, alias="SF_ETS"),
                ],
                freq="D",
                n_jobs=1,
            )
            fc = sf.forecast(df=df, h=horizon, level=[80])
            inputs = build_inputs(p, o, horizon, ForecastConfig(seed=1))
            for jar in inputs.jars:
                if jar.code not in codes:
                    continue
                y = p.jar(jar.code).spend[o + 1 : o + 1 + horizon].astype(float)
                s = fc[fc["unique_id"] == jar.code].sort_values("ds")
                tabs = {
                    "seasonal_naive (numpy, của dự án)": _predict(
                        SeasonalNaiveModel(prm, inputs.payday_day), inputs, jar
                    ),
                    "hurdle_calendar (của dự án)": _predict(
                        HurdleCalendarModel(prm, inputs.payday_day), inputs, jar
                    ),
                }
                for alias, label in (
                    ("SF_SN", "StatsForecast SeasonalNaive (native)"),
                    ("SF_ETS", "StatsForecast AutoETS (native)"),
                ):
                    q = np.stack(
                        [s[f"{alias}-lo-80"].values, s[alias].values, s[f"{alias}-hi-80"].values]
                    )
                    tabs[label] = np.maximum.accumulate(np.maximum(q, 0.0), axis=0)
                for name, q in tabs.items():
                    a = acc[name][(p.family, p.config, p.seed, jar.code)]
                    a[0] += mean_pinball(y, q)
                    a[1] += mean_pinball(y, tabs["seasonal_naive (numpy, của dự án)"])
                    a[2] += float(np.mean((y >= q[0]) & (y <= q[2])))
                    a[3] += 1
    out: dict[str, dict[str, float]] = {}
    for name, by_key in acc.items():
        out[name] = {
            "rel_pl": float(np.mean([a[0] / a[1] for a in by_key.values() if a[1] > 1e-9])),
            "cov_daily": float(np.mean([a[2] / a[3] for a in by_key.values()])),
        }
    return out


__all__ = ["ABLATIONS", "OBLIGATION_JAR", "ablation", "short_history", "statsforecast_compare"]
