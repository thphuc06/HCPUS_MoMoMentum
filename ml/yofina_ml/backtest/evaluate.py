"""Đo `forecast_user` bằng rolling-origin trên dữ liệu tổng hợp.

Mỗi bản ghi là (persona, origin, hũ). Đo:
- theo NGÀY: pinball P10/P50/P90 và độ phủ khoảng P10-P90 của (a) sản phẩm (hurdle + ACI), (b) hurdle thô (không ACI),
  (c) seasonal naive (baseline numpy, xem `models.SeasonalNaiveModel`);
- theo TỔNG CỘNG DỒN 7/14/30 ngày: độ phủ khoảng P10-P90 của SỐ DƯ hũ từ `forecast_user` (đã gồm Monte Carlo, hiệu chỉnh,
  lịch lương và nghĩa vụ) so với số dư thật trong sổ cái, cùng độ rộng tương đối;
- độ tin cậy của xác suất hụt trước kỳ lương (Brier, bảng độ tin cậy).
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from dataclasses import replace
from datetime import timedelta
from typing import Any

import numpy as np

from yofina_ml.backtest.common import (
    CUM_HORIZONS,
    HORIZON,
    TAUS,
    mean_pinball,
    origins,
    pinball,
    segment,
)
from yofina_ml.calibration import calibration_from_dict, default_calibration
from yofina_ml.forecast import fit_jar, forecast_user, make_context
from yofina_ml.models import HurdleCalendarModel, SeasonalNaiveModel
from yofina_ml.montecarlo import (
    SimSpec,
    balance_from_draws,
    draw_paths,
    jar_seed_sequence,
)
from yofina_ml.params import MLParams
from yofina_ml.synth.base import OBLIGATION_JAR, SynthPersona, build_inputs
from yofina_ml.types import ForecastConfig, ForecastInputs

SHORTFALL_ALPHAS = (
    0.6,
    0.8,
    1.0,
    1.25,
    1.6,
)  # số dư kịch bản = alpha x chi tiêu kỳ vọng tới ngày lương


def _jar_truth(p: SynthPersona, code: str, origin: int, horizon: int):
    j = p.jar(code)
    spend = p.obligation_paid if code == OBLIGATION_JAR else j.spend
    y = spend[origin + 1 : origin + 1 + horizon].astype(float)
    bal = p.balances[code][origin + 1 : origin + 1 + horizon].astype(float)
    return y, bal


def _raw_tables(inputs: ForecastInputs, jar_idx: int, prm: MLParams) -> dict[str, np.ndarray]:
    jar = inputs.jars[jar_idx]
    fut = tuple(inputs.app_date + timedelta(days=i + 1) for i in range(inputs.horizon_days))
    pday = inputs.payday_day
    out = {}
    for name, cls in (("hurdle_raw", HurdleCalendarModel), ("seasonal_naive", SeasonalNaiveModel)):
        m = cls(prm, pday)
        tab = m.predict(jar.daily_spend_vnd, jar.history_start, fut, inputs.payday_dates, TAUS)
        out[name] = np.array(tab, dtype=float).T  # (3, H)
    return out


def evaluate(
    personas_: list[SynthPersona],
    *,
    n_paths: int = 2000,
    horizon: int = HORIZON,
    config_extra: dict[str, Any] | None = None,
    first_origin: int = 90,
    step: int = 7,
    progress: bool = False,
) -> list[dict[str, Any]]:
    """Danh sách bản ghi (persona, origin, hũ). `config_extra` ghi đè `ForecastConfig.extra` (ví dụ calibration)."""
    prm = MLParams.from_extra(config_extra)
    rows: list[dict[str, Any]] = []
    for pi, p in enumerate(personas_):
        for o in origins(p.n_days, horizon, first_origin, step):
            cfg = ForecastConfig(
                n_paths=n_paths, seed=p.seed * 1000 + o, extra=dict(config_extra or {})
            )
            inputs = build_inputs(p, o, horizon, cfg)
            result = forecast_user(inputs)
            seg = segment(o, horizon, p.break_index)
            for ji, jf in enumerate(result.jars):
                code = jf.summary.jar_code
                y, bal_true = _jar_truth(p, code, o, horizon)
                hist = np.asarray(inputs.jars[ji].daily_spend_vnd, dtype=float)
                scale = float(hist[-28:].mean()) if len(hist) else 0.0
                rec: dict[str, Any] = {
                    "family": p.family,
                    "config": p.config,
                    "seed": p.seed,
                    "origin": o,
                    "jar": code,
                    "bucket": "obligation" if code == OBLIGATION_JAR else jf.summary.series_kind,
                    "segment": seg,
                    "scale": scale,
                }
                if code != OBLIGATION_JAR:
                    prod = np.array(
                        [
                            [d.spend_p10_vnd for d in jf.days],
                            [d.spend_p50_vnd for d in jf.days],
                            [d.spend_p90_vnd for d in jf.days],
                        ],
                        dtype=float,
                    )
                    tabs = {"product": prod, **_raw_tables(inputs, ji, prm)}
                    for name, q in tabs.items():
                        rec[f"pl_{name}"] = mean_pinball(y, q)
                        rec[f"cov_{name}"] = float(np.mean((y >= q[0]) & (y <= q[2])))
                for h in CUM_HORIZONS:
                    d = jf.days[h - 1]
                    t = bal_true[h - 1]
                    rec[f"cum{h}_in"] = float(d.balance_p10_vnd <= t <= d.balance_p90_vnd)
                    rec[f"cum{h}_width"] = (d.balance_p90_vnd - d.balance_p10_vnd) / max(
                        scale * h, 1.0
                    )
                    rec[f"cum{h}_pl"] = float(
                        np.mean(
                            [
                                pinball(np.array(t), np.array(q), tau)
                                for q, tau in (
                                    (d.balance_p10_vnd, 0.1),
                                    (d.balance_p50_vnd, 0.5),
                                    (d.balance_p90_vnd, 0.9),
                                )
                            ]
                        )
                    )
                rows.append(rec)
        if progress:
            print(f"  [{pi + 1}/{len(personas_)}] {p.family}/{p.config}/{p.seed}", flush=True)
    return rows


# --------------------------------------------------------------------------------------
# Tổng hợp
# --------------------------------------------------------------------------------------
def _sel(rows, **kw):
    return [r for r in rows if all(r.get(k) == v for k, v in kw.items())]


def relative_pinball(
    rows: list[dict[str, Any]], model: str, base: str = "seasonal_naive"
) -> float | None:
    """Pinball tương đối: với mỗi (persona, hũ) lấy tổng pinball của model chia tổng của baseline, rồi trung bình qua
    (persona, hũ). 1,00 = bằng baseline, nhỏ hơn là tốt hơn."""
    acc: dict[tuple, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for r in rows:
        if f"pl_{model}" not in r:
            continue
        k = (r["family"], r["config"], r["seed"], r["jar"])
        acc[k][0] += r[f"pl_{model}"]
        acc[k][1] += r[f"pl_{base}"]
    ratios = [a / b for a, b in acc.values() if b > 1e-9]
    return float(np.mean(ratios)) if ratios else None


def mean_of(rows: list[dict[str, Any]], key: str) -> float | None:
    v = [r[key] for r in rows if key in r]
    return float(np.mean(v)) if v else None


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Bảng tổng hợp theo (họ, nhóm hũ, đoạn)."""
    out: dict[str, Any] = {"by_family": {}}
    families = sorted({r["family"] for r in rows})
    for fam in [*families, "all"]:
        fr = rows if fam == "all" else _sel(rows, family=fam)
        block: dict[str, Any] = {}
        for bucket in ("dense", "sparse", "obligation", "spending"):
            br = (
                [r for r in fr if r["bucket"] in ("dense", "sparse")]
                if bucket == "spending"
                else _sel(fr, bucket=bucket)
            )
            if not br:
                continue
            cell: dict[str, Any] = {"n": len(br)}
            for seg in ("all", "pre_break", "post_break"):
                sr = br if seg == "all" else _sel(br, segment=seg)
                if not sr:
                    continue
                cell[seg] = {
                    "rel_pl_hurdle_raw": relative_pinball(sr, "hurdle_raw"),
                    "rel_pl_product": relative_pinball(sr, "product"),
                    "cov_daily_product": mean_of(sr, "cov_product"),
                    "cov_daily_raw": mean_of(sr, "cov_hurdle_raw"),
                    "cov_daily_sn": mean_of(sr, "cov_seasonal_naive"),
                    **{f"cov_cum{h}": mean_of(sr, f"cum{h}_in") for h in CUM_HORIZONS},
                    **{f"width_cum{h}": mean_of(sr, f"cum{h}_width") for h in CUM_HORIZONS},
                }
            block[bucket] = cell
        out["by_family"][fam] = block
    return out


# --------------------------------------------------------------------------------------
# Xác suất hụt trước kỳ lương: độ tin cậy
# --------------------------------------------------------------------------------------
def evaluate_shortfall(
    personas_: list[SynthPersona],
    *,
    n_paths: int = 2000,
    horizon: int = HORIZON,
    config_extra: dict[str, Any] | None = None,
    first_origin: int = 90,
    step: int = 14,
) -> list[dict[str, Any]]:
    """Với mỗi (origin, hũ chi tiêu) và mỗi số dư kịch bản b = alpha x (chi tiêu TB 28 ngày x số ngày trước lương),
    so xác suất hụt của engine với kết cục thật (tổng chi trước kỳ lương > b). Dùng cùng hiệu chỉnh như `forecast_user`."""
    cal = default_calibration()
    if config_extra and config_extra.get("calibration"):
        cal = calibration_from_dict(config_extra["calibration"], base=cal)
    rows: list[dict[str, Any]] = []
    for p in personas_:
        for o in origins(p.n_days, horizon, first_origin, step):
            cfg = ForecastConfig(
                n_paths=n_paths,
                seed=p.seed * 1000 + o,
                extra=dict(config_extra or {}),
                aci_gamma=0.0,
            )
            inputs = build_inputs(p, o, horizon, cfg)
            ctx = make_context(inputs, cal)
            w = ctx.window
            if w < 3:
                continue
            for jar in inputs.jars:
                if jar.kind == "obligation":
                    continue
                fit = fit_jar(jar, ctx)
                cal_k = cal.for_kind(fit.kind)
                spec = SimSpec(
                    0.0,
                    fit.marginal,
                    ctx.f_fut,
                    fit.kind == "sparse",
                    np.zeros(horizon),
                    np.zeros(horizon),
                    (),
                    w,
                )
                draws = draw_paths(
                    spec, cal_k.rho, n_paths, jar_seed_sequence(cfg.seed, inputs.app_date, jar.code)
                )
                bal = balance_from_draws(spec, draws, cal_k.level_sigma)  # = -tổng chi cộng dồn
                total_w = -bal[:, w - 1]
                y_true, _ = _jar_truth(p, jar.code, o, horizon)
                actual = float(y_true[:w].sum())
                mu = float(np.mean(jar.daily_spend_vnd[-28:])) * w
                if mu <= 0:
                    continue
                for a in SHORTFALL_ALPHAS:
                    b = a * mu
                    rows.append(
                        {
                            "family": p.family,
                            "bucket": fit.kind,
                            "alpha": a,
                            "p": float(np.mean(total_w > b)),
                            "event": float(actual > b),
                        }
                    )
    return rows


def reliability(
    rows: list[dict[str, Any]], bins=(0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0001)
) -> dict[str, Any]:
    if not rows:
        return {}
    p = np.array([r["p"] for r in rows])
    e = np.array([r["event"] for r in rows])
    table = []
    for lo, hi in itertools.pairwise(bins):
        m = (p >= lo) & (p < hi)
        if m.any():
            table.append(
                {
                    "bin": f"{lo:.1f}-{min(hi, 1.0):.1f}",
                    "n": int(m.sum()),
                    "mean_p": float(p[m].mean()),
                    "freq": float(e[m].mean()),
                }
            )
    return {
        "n": len(rows),
        "brier": float(np.mean((p - e) ** 2)),
        "brier_climatology": float(np.mean((e.mean() - e) ** 2)),
        "mean_p": float(p.mean()),
        "event_rate": float(e.mean()),
        "table": table,
    }


def with_config(cfg: ForecastConfig, **kw: Any) -> ForecastConfig:
    return replace(cfg, **kw)
