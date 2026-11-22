"""Chọn `rho` (copula AR(1)) và `level_sigma` (hệ số mức chung) theo ĐỘ PHỦ của tổng chi cộng dồn trên backtest rolling-origin.

Không chọn theo tự tương quan lag-1 của sai số (spike ML §3.2: ρ lag-1 đo 0,05 đến 0,39 nhưng phủ tổng 30 ngày đúng 80% cần
ρ cỡ 0,7 đến 0,8): với mỗi (rho, level_sigma) trong lưới, mô phỏng tổng chi cộng dồn 7/14/30 ngày từ chính phân phối biên mà
`forecast_user` dùng, đếm tần suất tổng thật rơi trong [P10, P90] và chọn cặp có độ phủ gần mục tiêu nhất (trọng số ưu tiên
tổng 30 ngày). Thực hiện riêng cho từng loại chuỗi (dense, sparse, cold_start).

Dùng seed hiệu chỉnh (`CAL_SEEDS`); số đo báo cáo lấy trên seed khác (`EVAL_SEEDS`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np

from yofina_ml.backtest.common import CUM_HORIZONS, HORIZON, N_DAYS
from yofina_ml.daycal import DayFeatures
from yofina_ml.forecast import fit_jar, make_context
from yofina_ml.marginals import Marginal
from yofina_ml.montecarlo import SimSpec, draw_paths, jar_seed_sequence
from yofina_ml.synth.base import SynthPersona, build_inputs
from yofina_ml.types import ForecastConfig

RHOS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8)
SIGMAS = (0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.65, 0.8)
HORIZON_WEIGHTS = {7: 0.2, 14: 0.3, 30: 0.5}
TARGET = 0.8


@dataclass(frozen=True)
class Unit:
    kind: str
    marginal: Marginal
    feats: DayFeatures
    truth_cum: np.ndarray  # (len(CUM_HORIZONS),) tổng chi thật cộng dồn tại 7/14/30 ngày
    seed: int
    app_date: date
    code: str


def collect_units(
    personas_: list[SynthPersona], origin_list: list[int], horizon: int = HORIZON
) -> list[Unit]:
    units: list[Unit] = []
    for p in personas_:
        for o in origin_list:
            if o + 1 + horizon > p.n_days:
                continue
            cfg = ForecastConfig(n_paths=1000, seed=p.seed * 1000 + o, aci_gamma=0.0)
            inputs = build_inputs(p, o, horizon, cfg)
            ctx = make_context(inputs)
            for jar in inputs.jars:
                if jar.kind == "obligation":
                    continue
                fit = fit_jar(jar, ctx)
                y = p.jar(jar.code).spend[o + 1 : o + 1 + horizon].astype(float)
                truth = np.cumsum(y)[[h - 1 for h in CUM_HORIZONS]]
                units.append(
                    Unit(
                        fit.kind,
                        fit.marginal,
                        ctx.f_fut,
                        truth,
                        cfg.seed or 0,
                        inputs.app_date,
                        jar.code,
                    )
                )
    return units


def grid_coverage(
    units: list[Unit],
    rhos: tuple[float, ...] = RHOS,
    sigmas: tuple[float, ...] = SIGMAS,
    n_paths: int = 1500,
) -> dict[str, dict[tuple[float, float], np.ndarray]]:
    """Độ phủ [P10, P90] của tổng cộng dồn tại các horizon, theo loại chuỗi và cặp (rho, sigma). Mảng (len(CUM_HORIZONS),)."""
    hits: dict[str, dict[tuple[float, float], np.ndarray]] = {}
    counts: dict[str, int] = {}
    idx = [h - 1 for h in CUM_HORIZONS]
    for u in units:
        spec = SimSpec(
            0.0,
            u.marginal,
            u.feats,
            u.kind == "sparse",
            np.zeros(len(u.feats)),
            np.zeros(len(u.feats)),
        )
        ss = jar_seed_sequence(u.seed, u.app_date, u.code)
        kind_hits = hits.setdefault(u.kind, {})
        counts[u.kind] = counts.get(u.kind, 0) + 1
        for rho in rhos if u.kind != "sparse" else (0.0,):
            draws = draw_paths(spec, rho, n_paths, ss)
            cum = np.cumsum(draws.spend, axis=1)[:, idx]
            for sg in sigmas:
                m = np.exp(sg * draws.xi - 0.5 * sg * sg)[:, None] if sg > 0 else 1.0
                q = np.quantile(cum * m, [0.1, 0.9], axis=0)
                inside = ((u.truth_cum >= q[0]) & (u.truth_cum <= q[1])).astype(float)
                kind_hits.setdefault((rho, sg), np.zeros(len(idx)))
                kind_hits[(rho, sg)] += inside
    return {k: {c: v / counts[k] for c, v in d.items()} for k, d in hits.items()}


def objective(cov: np.ndarray) -> float:
    w = np.array([HORIZON_WEIGHTS[h] for h in CUM_HORIZONS])
    return float(np.sum(w * np.abs(cov - TARGET)))


def choose(grid: dict[tuple[float, float], np.ndarray]) -> tuple[float, float]:
    """Cặp (rho, sigma) có độ phủ gần mục tiêu nhất; hòa thì ưu tiên sigma nhỏ rồi rho nhỏ (khoảng gọn hơn)."""
    best = min(grid, key=lambda c: (round(objective(grid[c]), 4), c[1], c[0]))
    return best


def calibrate(units: list[Unit], n_paths: int = 1500) -> dict[str, Any]:
    cov = grid_coverage(units, n_paths=n_paths)
    out: dict[str, Any] = {
        "units": {k: sum(1 for u in units if u.kind == k) for k in cov},
        "kinds": {},
    }
    for kind, grid in cov.items():
        rho, sg = choose(grid)
        base = grid[(0.0, 0.0)]
        ref = grid.get((0.3, 0.0), base)
        out["kinds"][kind] = {
            "rho": rho,
            "level_sigma": sg,
            "cov_before_rho0": [float(x) for x in base],
            "cov_before_rho0_3": [float(x) for x in ref],
            "cov_after": [float(x) for x in grid[(rho, sg)]],
            "grid_h30": {f"{r:.1f}/{s:.2f}": float(v[-1]) for (r, s), v in sorted(grid.items())},
        }
    out["horizons"] = list(CUM_HORIZONS)
    return out


def cold_start_origins() -> list[int]:
    return [8, 11, 14, 17, 20]


def default_origin_list() -> list[int]:
    from yofina_ml.backtest.common import FIRST_ORIGIN, ORIGIN_STEP, origins

    return origins(N_DAYS, HORIZON, FIRST_ORIGIN, ORIGIN_STEP)
