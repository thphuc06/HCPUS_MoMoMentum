"""Kiểm áp lực: chuỗi chi KHÔNG có đổi hành vi, chỉ có nhịp kỳ lương (đầu kỳ tiêu nhiều, cuối kỳ nhịn). Mọi lần xác nhận là báo nhầm.

CÔNG CỤ ĐO TRÊN MÁY, không phải mã sản phẩm. Ba mức nhịp (7 ngày đầu kỳ × hệ số, 10 ngày cuối kỳ × hệ số): nhẹ 1,2/0,85, mạnh 1,6/0,6,
rất mạnh 2,0/0,45; hũ dày (85% ngày có chi), cuối tuần ×1,6; 48 chuỗi 330 ngày mỗi mức. Ngoài đời nhịp lương là nguồn báo nhầm phổ biến.

    uv run python -m yofina_ml.backtest.change_payday_stress '[{}, {"pelt_penalty_c": 5.0}]'
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import date, timedelta

import numpy as np

from yofina_ml import change as ch

START = date(2026, 1, 1)
N_DAYS = 330
# (tên, hệ số 7 ngày đầu kỳ, hệ số 10 ngày cuối kỳ)
STRENGTHS = [("nhe", 1.2, 0.85), ("manh", 1.6, 0.6), ("rat_manh", 2.0, 0.45)]
PAYDAYS = [1, 5, 10, 25]


def make_series(seed: int, early: float, late: float, payday: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = np.zeros(N_DAYS)
    for t in range(N_DAYS):
        d = START + timedelta(days=t)
        since = (d.day - payday) % 30  # xấp xỉ số ngày từ kỳ lương gần nhất
        mult = early if since < 7 else (late if since >= 20 else 1.0)
        if d.weekday() >= 5:
            mult *= 1.6
        if rng.random() < 0.85:  # hũ dày (ăn uống): hầu hết ngày có chi
            n = 1 + rng.poisson(1.2)
            out[t] = float(np.sum(rng.lognormal(np.log(60_000), 0.45, n))) * mult
    return np.round(out, -3)


def fa_count(args: tuple[np.ndarray, ch.ChangeParams]) -> tuple[int, int]:
    daily, params = args
    seen: list[date] = []
    fa = observed = 0
    for t in range(params.min_weeks_total * ch.WEEK, N_DAYS + 1):
        series = ch.prepare_weekly(daily[:t], params)
        if series.skipped is not None:
            continue
        observed += 1
        hit = ch.detect_confirmed(series, params)
        if hit is None:
            continue
        when = ch.week_start_date(START + timedelta(days=t - 1), series.n_weeks, hit.change_index)
        if any(abs((when - s).days) <= params.dedupe_days for s in seen):
            continue
        seen.append(when)
        fa += 1
    return fa, observed


def main() -> None:
    combos = json.loads(sys.argv[1]) if len(sys.argv) > 1 else [{}]
    base = ch.load_params()
    for combo in combos:
        params = replace(base, **combo)
        row = {"params": combo}
        for name, early, late in STRENGTHS:
            jobs = [(make_series(1000 + s, early, late, PAYDAYS[s % 4]), params) for s in range(48)]
            with ProcessPoolExecutor(max_workers=8) as pool:
                res = list(pool.map(fa_count, jobs, chunksize=2))
            fa = sum(r[0] for r in res)
            years = sum(r[1] for r in res) / 365.0
            row[name] = round(fa / years, 3) if years else None
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
