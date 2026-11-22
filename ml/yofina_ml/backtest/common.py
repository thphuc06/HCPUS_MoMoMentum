"""Hằng số và tiện ích dùng chung của backtest."""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

import numpy as np

from yofina_ml import synth
from yofina_ml.synth.base import SynthPersona

HORIZON = 30
CUM_HORIZONS = (7, 14, 30)
TAUS = (0.1, 0.5, 0.9)
CAL_SEEDS = (101, 102, 103, 104)  # hiệu chỉnh trên các seed này
EVAL_SEEDS = (201, 202, 203, 204, 205, 206)  # đo trên seed KHÁC (giữ ra ngoài)
N_DAYS = 330
FIRST_ORIGIN = 90
ORIGIN_STEP = 7


@lru_cache(maxsize=256)
def persona(family: str, config: str, seed: int) -> SynthPersona:
    return synth.generate(family, config, seed, N_DAYS)


def personas(families: Iterable[str], seeds: Iterable[int]) -> list[SynthPersona]:
    out = []
    for fam in families:
        for cfg in synth.config_names(fam):
            for sd in seeds:
                out.append(persona(fam, cfg, sd))
    return out


def origins(
    n_days: int = N_DAYS, horizon: int = HORIZON, first: int = FIRST_ORIGIN, step: int = ORIGIN_STEP
) -> list[int]:
    return list(range(first, n_days - horizon, step))


def segment(origin: int, horizon: int, break_index: int | None) -> str:
    if break_index is None:
        return "no_break"
    if origin + horizon < break_index:
        return "pre_break"
    if origin >= break_index:
        return "post_break"
    return "straddle"


def pinball(y: np.ndarray, q: np.ndarray, tau: float) -> np.ndarray:
    d = y - q
    return np.maximum(tau * d, (tau - 1.0) * d)


def mean_pinball(y: np.ndarray, q3: np.ndarray) -> float:
    """Pinball trung bình qua tau = 0,1 / 0,5 / 0,9; q3 hình (3, H)."""
    return float(np.mean([pinball(y, q3[i], t).mean() for i, t in enumerate(TAUS)]))
