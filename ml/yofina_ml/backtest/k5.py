"""K5 (#26): cảnh báo hũ cạn có đúng không, đo trên số dư kịch bản của persona giữ ra ngoài, SAU hiệu chỉnh hiện hành
(`calibration/default.py`, gồm CQR/PAV của #25 khi công tắc `recalibrate` bật).

Vì sao số dư kịch bản: persona demo dựng ngược từ ngày neo nên không có tương lai thật, còn số dư thật của bộ sinh hiếm khi âm trước
kỳ lương (kiểm toán ML §3.1, backtest-final.md). Cách đo là phép B của kiểm toán §3.2, đưa vào repo. Luật dưới đây viết trước khi
chạy tập kiểm.

- **Mẫu**: persona seed `EVAL_SEEDS` (201-206), hai họ bộ sinh, mọi cấu hình. Origin từ ngày 120 bước 7, chân trời 30 ngày, lịch sử
  cắt còn 47 ngày, 120 ngày và lịch sử đủ (`studies._truncate`, như `recalibrate`). Mỗi (persona, origin, độ dài, hũ chi tiêu hoặc
  tiết kiệm có chi TB 28 ngày cuối dương) còn ít nhất `MIN_WINDOW` = 8 ngày trước kỳ lương (để báo trước 7 ngày là làm được),
  không gồm hũ nghĩa vụ và hũ khởi đầu lạnh.
- **Số dư kịch bản**: b = alpha x chi TB 28 ngày x w, alpha thuộc `SHORTFALL_ALPHAS`, w là số ngày trước kỳ lương (`ctx.window`),
  không tiền vào, không nghĩa vụ. Ngày cạn THẬT là chỉ số ngày đầu tiên (0 là ngày sau origin) mà b trừ chi thật cộng dồn <= ngưỡng
  cạn (`runout_balance_threshold_vnd`) trong chân trời; "cạn trước ngày lương" là ngày đó < w.
- **Ba phương pháp**, cùng kịch bản:
  - sản phẩm: biên của `fit_jar` (mô hình mặc định), Monte Carlo của `forecast_user` (cùng hạt, `rho`/`level_sigma` của loại chuỗi),
    p qua PAV đúng như `forecast_user` (`_recalibrated_p`, chỉ khi công tắc bật và loại có bảng), làm tròn 4 chữ số. Ngày cạn dự báo
    là ngày đầu số dư P50 <= ngưỡng (như `JarSummary.runout_date`).
  - seasonal naive: như trên với `extra.model = "seasonal_naive"`; p thô (bảng PAV học trên mô hình sản phẩm nên không áp).
  - burn-rate: số dư b - chi TB 28 ngày x (i + 1), ngày cạn dự báo là i đầu tiên số dư đó <= ngưỡng; không có xác suất.
- **Cảnh báo**: sản phẩm và seasonal naive báo khi p >= `tight_threshold` của cấu hình (trạng thái Sát hoặc Hụt) VÀ ngày cạn dự báo
  < w; burn-rate báo khi ngày cạn dự báo < w. Hũ thưa nay không hiện ngày (`show_runout_date`), số của nó vẫn tính theo cùng luật để
  đối chiếu.
- **Định nghĩa 1, đúng trong +-3 ngày**: cảnh báo có ngày cạn thật và |dự báo - thật| <= 3. Tỷ lệ trên mọi cảnh báo (thật không cạn
  trong chân trời là sai). Sai TB là TB |dự báo - thật| trên cảnh báo có ngày cạn thật.
- **Định nghĩa 2, đúng vì hũ cạn trước ngày lương**: cảnh báo có ngày cạn thật < w. Tỷ lệ trên mọi cảnh báo.
- **Báo trước**: số ngày từ lúc báo (origin) tới ngày cạn thật, tức chỉ số + 1; trung vị trên các cảnh báo đúng của từng định nghĩa.
- **Bắt được**: trong các ca cạn thật trước ngày lương, tỷ lệ có cảnh báo (để so công bằng phương pháp báo ít với phương pháp báo nhiều).
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

import numpy as np

from yofina_ml.backtest.common import EVAL_SEEDS, HORIZON, origins, personas
from yofina_ml.backtest.evaluate import SHORTFALL_ALPHAS
from yofina_ml.backtest.studies import _truncate
from yofina_ml.calibration import calibrated_config, default_calibration
from yofina_ml.forecast import _recalibrated_p, fit_jar, make_context
from yofina_ml.models import SEASONAL_NAIVE
from yofina_ml.montecarlo import (
    SimSpec,
    balance_from_draws,
    draw_paths,
    jar_seed_sequence,
    summarize_paths,
)
from yofina_ml.synth import FAMILIES
from yofina_ml.synth.base import SynthPersona, build_inputs

FULL = "full"
LENGTHS: tuple[int | str, ...] = (47, 120, FULL)
FIRST_ORIGIN = 120
STEP = 7
MIN_WINDOW = 8  # ít nhất 8 ngày trước kỳ lương thì báo trước 7 ngày mới làm được
SCALE_DAYS = 28
WITHIN_DAYS = 3
PRODUCT, BURN_RATE = "product", "burn_rate"
METHODS = (PRODUCT, SEASONAL_NAIVE, BURN_RATE)
KINDS = ("dense", "sparse")


# --------------------------------------------------------------------------------------
# Một kịch bản
# --------------------------------------------------------------------------------------
def first_runout(balance: np.ndarray, threshold: float = 0.0) -> int | None:
    """Chỉ số ngày đầu tiên số dư <= ngưỡng; không có thì None."""
    hit = np.nonzero(np.asarray(balance, dtype=float) <= threshold)[0]
    return int(hit[0]) if len(hit) else None


def burn_rate_day(b: float, scale: float, horizon: int, threshold: float = 0.0) -> int | None:
    """Ngày cạn theo burn-rate: số dư b - chi TB x (i + 1) chạm ngưỡng ở chỉ số i nào (trong chân trời)."""
    return first_runout(b - scale * np.arange(1, horizon + 1, dtype=float), threshold)


def scenario_rows(
    *,
    b: float,
    window: int,
    true_spend: Sequence[float],
    scale: float,
    models: Mapping[str, tuple[float, int | None]],
    tight: float,
    threshold: float = 0.0,
    tags: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Một dòng cho mỗi phương pháp của một kịch bản: mỗi mô hình trong `models` ({tên: (p, ngày cạn dự báo)}) và burn-rate
    (tính từ `scale`). Dòng có cờ cảnh báo, ngày dự báo, ngày cạn thật, w và các nhãn `tags`."""
    spend = np.asarray(true_spend, dtype=float)
    true_day = first_runout(b - np.cumsum(spend), threshold)
    base = {**(tags or {}), "window": int(window), "true_day": true_day}
    rows = []
    for name, (p, day) in models.items():
        warn = p >= tight and day is not None and day < window
        rows.append({**base, "method": name, "warn": bool(warn), "pred_day": day})
    day = burn_rate_day(b, scale, len(spend), threshold)
    warn = day is not None and day < window
    rows.append({**base, "method": BURN_RATE, "warn": bool(warn), "pred_day": day})
    return rows


# --------------------------------------------------------------------------------------
# Tổng hợp
# --------------------------------------------------------------------------------------
def _median(v: list[int]) -> float | None:
    return float(np.median(v)) if v else None


def metrics(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Số đo K5 của một nhóm dòng cùng phương pháp (docstring module)."""
    warns = [r for r in rows if r["warn"]]
    with_true = [r for r in warns if r["true_day"] is not None]
    err = [abs(r["pred_day"] - r["true_day"]) for r in with_true]
    ok1 = [r for r in with_true if abs(r["pred_day"] - r["true_day"]) <= WITHIN_DAYS]
    ok2 = [r for r in with_true if r["true_day"] < r["window"]]
    events = [r for r in rows if r["true_day"] is not None and r["true_day"] < r["window"]]
    n = len(warns)
    return {
        "n": len(rows),
        "n_warn": n,
        "def1": len(ok1) / n if n else None,
        "mae_days": float(np.mean(err)) if err else None,
        "lead_median_def1": _median([r["true_day"] + 1 for r in ok1]),
        "def2": len(ok2) / n if n else None,
        "lead_median_def2": _median([r["true_day"] + 1 for r in ok2]),
        "n_events": len(events),
        "recall": sum(r["warn"] for r in events) / len(events) if events else None,
    }


def summarize(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    """{độ dài: {loại chuỗi: {phương pháp: số đo}}}, giữ thứ tự xuất hiện của độ dài, loại theo `KINDS`, phương pháp theo
    `METHODS`."""
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[(str(r["length"]), r["kind"], r["method"])].append(r)
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for length in dict.fromkeys(str(r["length"]) for r in rows):
        cells: dict[str, dict[str, Any]] = {}
        for kind in KINDS:
            by_method = {
                m: metrics(groups[(length, kind, m)])
                for m in METHODS
                if groups.get((length, kind, m))
            }
            if by_method:
                cells[kind] = by_method
        out[length] = cells
    return out


# --------------------------------------------------------------------------------------
# Thu kịch bản
# --------------------------------------------------------------------------------------
def _scale(spend: Sequence[int]) -> float:
    recent = spend[-SCALE_DAYS:]
    return float(np.mean(recent)) if len(recent) else 0.0


def _paths(fit, ctx, jar, horizon: int) -> tuple[SimSpec, np.ndarray, Any]:
    """(spec số dư 0, số dư từ 0 của mọi đường, hiệu chỉnh của loại chuỗi) với đúng hạt và tham số của `forecast_user`."""
    ck = ctx.cal.for_kind(fit.kind)
    spec = SimSpec(
        0.0,
        fit.marginal,
        ctx.f_fut,
        fit.kind == "sparse",
        np.zeros(horizon),
        np.zeros(horizon),
        (),
        ctx.window,
    )
    seq = jar_seed_sequence(ctx.cfg.seed, ctx.inputs.app_date, jar.code)
    draws = draw_paths(spec, ck.rho, ctx.n_paths, seq)
    return spec, balance_from_draws(spec, draws, ck.level_sigma), ck


def _cases(
    p: SynthPersona, o: int, inputs, length: int | str, horizon: int, min_window: int
) -> list[dict[str, Any]]:
    ctx = make_context(inputs)
    w = ctx.window
    if w < min_window:
        return []
    sn_cfg = replace(inputs.config, extra={**inputs.config.extra, "model": SEASONAL_NAIVE})
    sn_ctx = make_context(replace(inputs, config=sn_cfg))
    thr = float(ctx.prm.runout_balance_threshold_vnd)
    tight = float(inputs.config.tight_threshold)
    rows: list[dict[str, Any]] = []
    for jar in inputs.jars:
        if jar.kind == "obligation":
            continue
        scale = _scale(jar.daily_spend_vnd)
        if scale <= 0:
            continue
        fit = fit_jar(jar, ctx)
        if fit.kind not in KINDS:
            continue
        sims = {
            PRODUCT: (*_paths(fit, ctx, jar, horizon), ctx),
            SEASONAL_NAIVE: (*_paths(fit_jar(jar, sn_ctx), sn_ctx, jar, horizon), sn_ctx),
        }
        true_spend = p.jar(jar.code).spend[o + 1 : o + 1 + horizon]
        tags = {"length": length, "kind": fit.kind, "family": p.family, "seed": p.seed}
        for a in SHORTFALL_ALPHAS:
            b = a * scale * w
            models: dict[str, tuple[float, int | None]] = {}
            for name, (spec, bal0, ck, c) in sims.items():
                spec_b = replace(spec, balance_vnd=b)
                sim = summarize_paths(b + bal0, spec_b, thr)
                pv = float(sim.p_shortfall)
                if name == PRODUCT:
                    pv = _recalibrated_p(pv, spec_b, jar, ck, c)
                models[name] = (round(pv, 4), sim.runout_index)
            rows += scenario_rows(
                b=b,
                window=w,
                true_spend=true_spend,
                scale=scale,
                models=models,
                tight=tight,
                threshold=thr,
                tags={**tags, "alpha": a},
            )
    return rows


def collect(
    personas_: list[SynthPersona],
    *,
    lengths: tuple[int | str, ...] = LENGTHS,
    n_paths: int = 2000,
    step: int = STEP,
    first_origin: int = FIRST_ORIGIN,
    horizon: int = HORIZON,
    min_window: int = MIN_WINDOW,
    progress: bool = False,
) -> list[dict[str, Any]]:
    """Dòng (kịch bản, phương pháp) trên các persona đã cho, hiệu chỉnh mặc định. ACI tắt vì nó không vào Monte Carlo (biên,
    p và ngày cạn không đổi), như `evaluate.evaluate_shortfall`."""
    base = replace(calibrated_config(), n_paths=n_paths, aci_gamma=0.0)
    rows: list[dict[str, Any]] = []
    t0 = time.time()
    for pi, p in enumerate(personas_):
        for o in origins(p.n_days, horizon, first_origin, step):
            full = build_inputs(p, o, horizon, replace(base, seed=p.seed * 1000 + o))
            for length in lengths:
                inputs = full if length == FULL else _truncate(full, int(length))
                rows += _cases(p, o, inputs, length, horizon, min_window)
        if progress:
            print(f"  [{pi + 1}/{len(personas_)}] {time.time() - t0:.0f}s", flush=True)
    return rows


def run(*, quick: bool = False, n_paths: int = 2000, progress: bool = True) -> dict[str, Any]:
    seeds = EVAL_SEEDS[:2] if quick else EVAL_SEEDS
    step = 28 if quick else STEP
    t0 = time.time()
    cal = default_calibration()
    if progress:
        print(f"[K5] đo trên seed {list(seeds)}, hiệu chỉnh {cal.version}", flush=True)
    rows = collect(personas(FAMILIES, seeds), n_paths=n_paths, step=step, progress=progress)
    return {
        "method": f"số dư kịch bản alpha {list(SHORTFALL_ALPHAS)}, lịch sử cắt {list(LENGTHS)}, origin từ ngày "
        f"{FIRST_ORIGIN} bước {step}, chân trời {HORIZON}, w >= {MIN_WINDOW}, {n_paths} đường; đúng trong "
        f"+-{WITHIN_DAYS} ngày",
        "heldout_seeds": list(seeds),
        "families": sorted(FAMILIES),
        "calibration": {
            "version": cal.version,
            "recalibrate": cal.recalibrate,
            "pav_kinds": [k for k in KINDS if cal.for_kind(k).p_isotonic is not None],
        },
        "rows": len(rows),
        "summary": summarize(rows),
        "seconds": round(time.time() - t0, 1),
    }


# --------------------------------------------------------------------------------------
# Bảng markdown
# --------------------------------------------------------------------------------------
_LABEL = {PRODUCT: "sản phẩm", SEASONAL_NAIVE: "seasonal naive", BURN_RATE: "burn-rate"}
_KIND_LABEL = {"dense": "hũ dày", "sparse": "hũ thưa"}


def _f(v: float | None, nd: int = 3) -> str:
    return "-" if v is None else f"{v:.{nd}f}".replace(".", ",")


def render(result: dict[str, Any]) -> str:
    lines = [
        "| Lịch sử | Nhóm | Phương pháp | Kịch bản | Cảnh báo | Đ1: đúng ±3 ngày | Sai TB (ngày) "
        "| Báo trước trung vị, Đ1 (ngày) | Đ2: cạn trước lương | Báo trước trung vị, Đ2 (ngày) | Bắt được |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for length, cells in result["summary"].items():
        for kind, by_method in cells.items():
            for m, c in by_method.items():
                lines.append(
                    f"| {length} | {_KIND_LABEL.get(kind, kind)} | {_LABEL.get(m, m)} | {c['n']} | {c['n_warn']} "
                    f"| {_f(c['def1'])} | {_f(c['mae_days'], 2)} | {_f(c['lead_median_def1'], 0)} "
                    f"| {_f(c['def2'])} | {_f(c['lead_median_def2'], 0)} | {_f(c['recall'])} |"
                )
    cal = result["calibration"]
    lines += [
        "",
        f"Hiệu chỉnh: {cal['version']}, recalibrate = {cal['recalibrate']}, PAV cho {cal['pav_kinds']}; "
        f"{result['rows']} dòng, {result['seconds']} giây.",
    ]
    return "\n".join(lines)


__all__ = [
    "LENGTHS",
    "burn_rate_day",
    "collect",
    "first_runout",
    "metrics",
    "render",
    "run",
    "scenario_rows",
    "summarize",
]
