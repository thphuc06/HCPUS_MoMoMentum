"""Hiệu chỉnh bộ phát hiện đổi hành vi (`yofina_ml.change`) trên bộ sinh tổng hợp KHÁC HỌ và trên ba persona demo.

CÔNG CỤ ĐO TRÊN MÁY, không phải mã sản phẩm (không được import từ `yofina_ml.change` hay pipeline).

    uv run python -m yofina_ml.backtest.change_calibration                    # in bảng, không ghi gì
    uv run python -m yofina_ml.backtest.change_calibration --grid             # quét c của PELT và (k, h) của CUSUM
    uv run python -m yofina_ml.backtest.change_calibration --write            # ghi mục `calibration` vào change_defaults.json

Cách đo (mô phỏng đúng cách sản phẩm chạy): với MỖI hũ chi tiêu của mỗi (họ, cấu hình, seed) trong `yofina_ml.synth`, chạy bộ phát
hiện ở MỌI ngày làm "hôm nay" (origin) từ khi đủ `min_weeks_total` tuần tới hết chuỗi (đúng như batch đêm chạy mỗi đêm), chỉ nhìn
dữ liệu tới hôm qua. Một dấu hiệu là sự kiện đầu tiên của (hũ, điểm gãy) vì sản phẩm lưu dấu hiệu và không tạo lại trong
`dedupe_days` ngày. Sự thật:

- Điểm gãy thật là ngày `break_index` của bộ sinh. Hũ có "dịch mức thật" khi tỷ lệ trung bình tuần đã cắt khoản lớn của 8 tuần
  sau so với 8 tuần trước điểm gãy ra ngoài (1 / (1 + m), 1 + m) với m = `TRUTH_SHIFT` (30%, cố định). Hũ ở giữa dải (dịch nhỏ) là mơ hồ.
- ĐÚNG (TP): dấu hiệu của hũ có dịch mức thật, định vị điểm gãy trong +-`tol_days` ngày quanh điểm gãy thật, phát SAU điểm gãy.
- BÁO NHẦM (FA): mọi dấu hiệu khác của hũ KHÔNG mơ hồ (hũ không dịch, hoặc hũ có dịch nhưng điểm gãy sai chỗ hay phát trước điểm gãy).
  Dấu hiệu của hũ mơ hồ gần điểm gãy thật được đếm riêng (`ambiguous`), không tính đúng hay sai.
- Độ trễ: số ngày từ điểm gãy thật tới đêm đầu tiên có dấu hiệu ĐÚNG.
- Tỷ lệ báo nhầm: số dấu hiệu sai trên mỗi hũ-năm quan sát, và tỷ lệ hũ-chuỗi có ít nhất một dấu hiệu sai.
Hũ không đủ điều kiện (thưa, thiếu tuần) không được phân tích nên không có dấu hiệu; số hũ-chuỗi đủ điều kiện được báo riêng.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from yofina_ml import change as ch
from yofina_ml.synth import FAMILIES, config_names
from yofina_ml.synth import generate as synth_generate

SYNTH_START = date(2026, 1, 1)  # ngày đầu của mọi chuỗi tổng hợp (mặc định của bộ sinh)
#: một hũ có "dịch mức thật" khi tỷ lệ trung bình tuần 8 tuần sau/trước điểm gãy ngoài (1/(1+m), 1+m). CỐ ĐỊNH, không phụ thuộc
#: `min_relative_change` đang thử (nếu không, đổi ngưỡng chặn làm đổi luôn đáp án và các cấu hình không so với nhau được).
TRUTH_SHIFT = 0.3
SPENDING_KIND = (
    "spending"  # pipeline chỉ phân tích hũ chi tiêu; hũ tiết kiệm (dự phòng) có cú sốc ngẫu nhiên
)

#: dấu hiệu mà bộ phát hiện đưa ra ở một đêm: (ngày điểm gãy ước lượng, loại)
Event = tuple[date, str]


@dataclass(frozen=True)
class JarCase:
    family: str
    config: str
    seed: int
    jar: str
    daily: np.ndarray
    break_index: int
    shift_ratio: float  # trung bình tuần (đã cắt) 8 tuần sau / 8 tuần trước điểm gãy thật

    @property
    def key(self) -> str:
        return f"{self.family}/{self.config}/{self.seed}/{self.jar}"


def build_cases(seeds: Sequence[int], params: ch.ChangeParams, n_days: int = 330) -> list[JarCase]:
    cases: list[JarCase] = []
    for family in FAMILIES:
        for config in config_names(family):
            for seed in seeds:
                p = synth_generate(family, config, seed, n_days)
                if p.break_index is None:
                    continue
                for jar in p.jars:
                    if jar.kind != SPENDING_KIND:
                        continue
                    clean = ch.winsorize_daily(jar.spend.astype(float), params)
                    b = p.break_index
                    pre = clean[max(0, b - 56) : b].sum() / 8.0
                    post = clean[b : b + 56].sum() / 8.0
                    ratio = post / pre if pre > 0 else float("inf")
                    cases.append(
                        JarCase(family, config, seed, jar.code, jar.spend.astype(float), b, ratio)
                    )
    return cases


def _is_true_shift(ratio: float, m: float) -> bool:
    return ratio >= 1 + m or ratio <= 1 / (1 + m)


def _is_flat(ratio: float, m: float) -> bool:
    return 1 / (1 + m / 2) <= ratio <= 1 + m / 2


def simulate_case(
    case: JarCase, params: ch.ChangeParams, mode: str
) -> tuple[list[tuple[int, date, str]], int, bool]:
    """Chạy bộ phát hiện (`mode` là `confirm` hoặc `suspect`) ở mọi origin. Trả (các sự kiện (origin, ngày điểm gãy, loại),
    số origin đã quan sát có đủ điều kiện, hũ có đủ điều kiện ở origin cuối không). Sự kiện trùng dấu hiệu cũ của hũ (lệch
    <= dedupe_days ngày) bị bỏ như sản phẩm."""
    events: list[tuple[int, date, str]] = []
    seen: list[date] = []
    observed = 0
    eligible_last = False
    start = (params.min_weeks_total + 0) * ch.WEEK
    for t in range(start, len(case.daily) + 1):
        series = ch.prepare_weekly(case.daily[:t], params)
        eligible_last = series.skipped is None
        if series.skipped is not None:
            continue
        observed += 1
        last_day = SYNTH_START + timedelta(days=t - 1)
        if mode == "confirm":
            hit = ch.detect_confirmed(series, params)
            idx = hit.change_index if hit else None
            kind = hit.direction if hit else ""
        else:
            sus = ch.detect_suspect(series, params)
            idx = sus.start_index if sus else None
            kind = sus.direction if sus else ""
        if idx is None:
            continue
        when = ch.week_start_date(last_day, series.n_weeks, idx)
        if any(abs((when - s).days) <= params.dedupe_days for s in seen):
            continue
        seen.append(when)
        events.append((t, when, kind))
    return events, observed, eligible_last


def _simulate_job(
    job: tuple[JarCase, ch.ChangeParams, str],
) -> tuple[list[tuple[int, date, str]], int, bool]:
    return simulate_case(*job)


def simulate_case_grid(
    case: JarCase, base: ch.ChangeParams, combos: Sequence[dict[str, Any]]
) -> list[tuple[list[tuple[int, date, str]], int]]:
    """Như `simulate_case` (chế độ confirm) cho NHIỀU bộ tham số cùng lúc: các bộ chung (c, sàn sigma, n_ref) dùng chung MỘT lần PELT mỗi
    origin (PELT là phần đắt), các tham số chặn (`min_relative_change`, `hold_midpoint_fraction`...) chỉ lọc lại."""
    params = [replace(base, **c) for c in combos]
    groups: dict[tuple[Any, ...], list[int]] = {}
    for i, p in enumerate(params):
        key = (p.pelt_penalty_c, p.sigma_floor_ratio, p.pelt_penalty_n_ref, p.pelt_min_size_weeks)
        groups.setdefault(key, []).append(i)
    events: list[list[tuple[int, date, str]]] = [[] for _ in params]
    seen: list[list[date]] = [[] for _ in params]
    observed = 0
    for t in range(base.min_weeks_total * ch.WEEK, len(case.daily) + 1):
        series = ch.prepare_weekly(case.daily[:t], base)
        if series.skipped is not None:
            continue
        observed += 1
        last_day = SYNTH_START + timedelta(days=t - 1)
        for idxs in groups.values():
            breaks = ch.pelt_breakpoints(series.clean, params[idxs[0]])
            for i in idxs:
                hit = ch.detect_confirmed(series, params[i], breaks=breaks)
                if hit is None:
                    continue
                when = ch.week_start_date(last_day, series.n_weeks, hit.change_index)
                if any(abs((when - sd).days) <= params[i].dedupe_days for sd in seen[i]):
                    continue
                seen[i].append(when)
                events[i].append((t, when, hit.direction))
    return [(events[i], observed) for i in range(len(params))]


def _grid_job(job: tuple[JarCase, ch.ChangeParams, Sequence[dict[str, Any]]]):
    return simulate_case_grid(*job)


def _pool_map(fn, jobs, workers: int | None):
    n_workers = workers if workers is not None else min(os.cpu_count() or 1, 12)
    if n_workers > 1:
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            return list(pool.map(fn, jobs, chunksize=2))
    return [fn(j) for j in jobs]


def score(
    cases: Sequence[JarCase],
    params: ch.ChangeParams,
    mode: str,
    *,
    tol_days: int = 21,
    workers: int | None = None,
) -> dict[str, Any]:
    sims = _pool_map(_simulate_job, [(case, params, mode) for case in cases], workers)
    return evaluate(cases, [(ev, obs) for ev, obs, _ in sims], params, mode, tol_days=tol_days)


def evaluate(
    cases: Sequence[JarCase],
    sims: Sequence[tuple[list[tuple[int, date, str]], int]],
    params: ch.ChangeParams,
    mode: str,
    *,
    tol_days: int = 21,
    big_shift: float = 1.5,
) -> dict[str, Any]:
    m = TRUTH_SHIFT
    tp = fa = amb = 0
    fa_series = 0
    n_eligible = n_series_shift = hit_series = hit8 = 0
    n_big = hit_big = 0
    delays: list[int] = []
    obs_days = 0
    by_family: dict[str, dict[str, int]] = {}
    for case, (events, observed) in zip(cases, sims, strict=True):
        obs_days += observed
        fam = by_family.setdefault(case.family, {"tp": 0, "fa": 0, "series": 0, "obs_days": 0})
        fam["obs_days"] += observed
        if observed:
            n_eligible += 1
            fam["series"] += 1
        brk_day = SYNTH_START + timedelta(days=case.break_index)
        true_shift = _is_true_shift(case.shift_ratio, m)
        flat = _is_flat(case.shift_ratio, m)
        big = case.shift_ratio >= big_shift or case.shift_ratio <= 1 / big_shift
        first_tp: int | None = None
        series_fa = 0
        for origin, when, _kind in events:
            origin_day = SYNTH_START + timedelta(days=origin - 1)
            near = abs((when - brk_day).days) <= tol_days and origin_day >= brk_day
            if true_shift and near:
                tp += 1
                fam["tp"] += 1
                if first_tp is None:
                    first_tp = (origin_day - brk_day).days
            elif not true_shift and not flat and near:
                amb += 1
            else:
                fa += 1
                fam["fa"] += 1
                series_fa += 1
        fa_series += 1 if series_fa else 0
        if observed and big:
            n_big += 1
            hit_big += 1 if first_tp is not None else 0
        if true_shift and observed:
            n_series_shift += 1
            if first_tp is not None:
                hit_series += 1
                delays.append(first_tp)
                if first_tp <= 56:
                    hit8 += 1
    years = obs_days / 365.0
    return {
        "mode": mode,
        "series_eligible": n_eligible,
        "series_total": len(cases),
        "series_with_true_shift": n_series_shift,
        "series_with_big_shift": n_big,
        "tp": tp,
        "fa": fa,
        "ambiguous": amb,
        "obs_jar_years": round(years, 2),
        "fa_per_jar_year": round(fa / years, 4) if years else None,
        "fa_series_share": round(fa_series / n_eligible, 4) if n_eligible else None,
        "recall_any": round(hit_series / n_series_shift, 4) if n_series_shift else None,
        "recall_8w": round(hit8 / n_series_shift, 4) if n_series_shift else None,
        "recall_big_shift": round(hit_big / n_big, 4) if n_big else None,
        "delay_days_median": float(np.median(delays)) if delays else None,
        "delay_days_p90": float(np.percentile(delays, 90)) if delays else None,
        "by_family": by_family,
    }


def grid_confirm(
    cases: Sequence[JarCase], base: ch.ChangeParams, combos: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Quét nhiều bộ tham số PELT một lượt: trả metric theo thứ tự `combos`."""
    per_case = _pool_map(_grid_job, [(case, base, combos) for case in cases], None)
    out = []
    for i, combo in enumerate(combos):
        p = replace(base, **combo)
        out.append(evaluate(cases, [pc[i] for pc in per_case], p, "confirm"))
    return out


# --- persona --------------------------------------------------------------------------------------------
def persona_daily_spend(name: str, anchor: date | None = None) -> dict[str, np.ndarray]:
    """Chi tiêu từng ngày của từng hũ chi tiêu của persona (đúng nguồn như `app_get_daily_spend`: chi trừ tiền hũ, không gắn nghĩa vụ),
    cũ tới mới, ngày cuối là hôm qua (days_ago = 1). Cần `data/` trên sys.path."""
    from personas import generate

    anchor = anchor or date(2026, 11, 21)
    d = generate(name, anchor=anchor)
    kinds = {j.code: j.kind for j in d.jars}
    out: dict[str, np.ndarray] = {}
    for jar, kind in kinds.items():
        if kind != SPENDING_KIND:
            continue
        arr = np.zeros(d.history_days + 1)
        for t in d.transactions:
            if (
                t.kind == "expense"
                and t.funding_source == "jar"
                and t.obligation_key is None
                and t.jar_code == jar
            ):
                arr[t.days_ago] += -t.amount_vnd
        out[jar] = arr[1:][::-1]  # days_ago 1 là ngày cuối
    return out


def persona_report(names: Sequence[str], params: ch.ChangeParams) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in names:
        rows: dict[str, Any] = {}
        for jar, daily in persona_daily_spend(name).items():
            s = ch.prepare_weekly(daily, params)
            conf = None if s.skipped else ch.detect_confirmed(s, params)
            sus = None if s.skipped else ch.detect_suspect(s, params)
            rows[jar] = {
                "weeks": [round(float(v)) for v in s.raw],
                "skipped": s.skipped,
                "confirmed": None
                if conf is None
                else {
                    "direction": conf.direction,
                    "change_index": conf.change_index,
                    "old": conf.old_weekly_vnd,
                    "new": conf.new_weekly_vnd,
                    "weeks_held": conf.weeks_held,
                },
                "suspect": None
                if sus is None
                else {
                    "direction": sus.direction,
                    "old": sus.old_weekly_vnd,
                    "new": sus.new_weekly_vnd,
                },
            }
        out[name] = rows
    return out


# --- CLI ----------------------------------------------------------------------------------------------------
def _fmt(r: dict[str, Any]) -> str:
    return (
        f"FA/hũ-năm={r['fa_per_jar_year']}  hũ-chuỗi có FA={r['fa_series_share']}  recall={r['recall_any']} "
        f"(8 tuần {r['recall_8w']}, dịch lớn {r['recall_big_shift']})  trễ trung vị={r['delay_days_median']} ngày, p90={r['delay_days_p90']}  "
        f"TP={r['tp']} FA={r['fa']} mơ hồ={r['ambiguous']}  đủ điều kiện={r['series_eligible']}/{r['series_total']}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--seeds", type=int, default=6, help="số seed mỗi cấu hình (101, 102, ...)")
    ap.add_argument(
        "--grid",
        action="store_true",
        help="quét tham số PELT (c, sàn sigma, chặn) và (k, h, sàn sigma) của CUSUM",
    )
    ap.add_argument("--grid-cusum", action="store_true", help="chỉ quét CUSUM (nhanh)")
    ap.add_argument(
        "--write", action="store_true", help="ghi mục calibration vào change_defaults.json"
    )
    ap.add_argument("--personas", nargs="*", default=["minh", "lan", "khoa", "vy"])
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    repo = Path(__file__).resolve().parents[3]
    for extra in ("data", "libs/yofina_core/src"):
        sys.path.insert(0, str(repo / extra))

    base = ch.load_params()
    seeds = [100 + i for i in range(1, args.seeds + 1)]
    cases = build_cases(seeds, base)
    n_shift = sum(_is_true_shift(c.shift_ratio, TRUTH_SHIFT) for c in cases)
    print(f"{len(cases)} hũ-chuỗi tổng hợp ({len(seeds)} seed), {n_shift} có dịch mức thật")

    if args.grid_cusum:
        print("\nCUSUM (nghi), quét k, h, sàn sigma:")
        for fl, k, h in itertools.product((0.15, 0.3, 0.4), (0.5, 1.0), (4.0, 5.0, 6.0, 8.0)):
            p = replace(base, cusum_sigma_floor_ratio=fl, cusum_k=k, cusum_h=h)
            print(f"  floor={fl} k={k} h={h:<4}", _fmt(score(cases, p, "suspect")))
        return 0

    if args.grid:
        combos = [
            {
                "pelt_penalty_c": c,
                "sigma_floor_ratio": fl,
                "min_relative_change": mr,
                "hold_midpoint_fraction": hd,
            }
            for c, fl, mr, hd in itertools.product(
                (3.0, 4.0, 5.0, 6.0), (0.2, 0.25, 0.3, 0.35), (0.4,), (0.5, 0.65)
            )
        ]
        print("\nPELT (xác nhận), quét c, sàn sigma, min_relative_change, hold:")
        for combo, r in zip(combos, grid_confirm(cases, base, combos), strict=True):
            print(
                f"  c={combo['pelt_penalty_c']:<4} floor={combo['sigma_floor_ratio']:<4} "
                f"rel={combo['min_relative_change']:<4} hold={combo['hold_midpoint_fraction']:<4}",
                _fmt(r),
            )
        print("\nCUSUM (nghi), quét k, h:")
        for k, h in itertools.product((0.5, 1.0), (3.0, 4.0, 5.0, 6.0)):
            p = replace(base, cusum_k=k, cusum_h=h)
            print(f"  k={k} h={h:<4}", _fmt(score(cases, p, "suspect")))
        return 0

    conf = score(cases, base, "confirm")
    sus = score(cases, base, "suspect")
    print("\nPELT xác nhận:", _fmt(conf))
    print("CUSUM nghi   :", _fmt(sus))
    pers = persona_report(args.personas, base)
    for name, rows in pers.items():
        print(f"\npersona {name}:")
        for jar, r in rows.items():
            print(
                f"  {jar:<10} bỏ qua={r['skipped']}  tuần={r['weeks']}  xác nhận={r['confirmed']}  nghi={r['suspect']}"
            )
    if args.write:
        path = ch.DEFAULTS_FILE
        raw = json.loads(path.read_text(encoding="utf-8"))
        keep = ("tp", "fa", "ambiguous", "series_eligible", "series_total", "series_with_true_shift",
                "series_with_big_shift", "obs_jar_years", "fa_per_jar_year", "fa_series_share", "recall_any",
                "recall_8w", "recall_big_shift", "delay_days_median", "delay_days_p90")  # fmt: skip
        raw["calibration"] = {
            "status": "da_hieu_chinh",
            "tool": "python -m yofina_ml.backtest.change_calibration --write",
            "params_snapshot": {k: v for k, v in base.to_dict().items() if k != "version"},
            "seeds": seeds,
            "n_days": 330,
            "tolerance_days": 21,
            "truth_shift": TRUTH_SHIFT,
            "families": list(FAMILIES),
            "note": "Số đo trên bộ sinh tổng hợp khác họ, mô phỏng mỗi đêm một lần. fa_per_jar_year là số dấu hiệu sai mỗi hũ-năm; delay_days là số ngày từ điểm gãy thật tới đêm đầu tiên có dấu hiệu đúng. Đo trên dữ liệu TỔNG HỢP, chưa có dữ liệu thật.",
            "confirm_pelt": {k: conf[k] for k in keep},
            "suspect_cusum": {k: sus[k] for k in keep},
            "personas": {
                name: {
                    jar: {
                        "confirmed": bool(r["confirmed"]),
                        "suspect": bool(r["suspect"]),
                        "skipped": r["skipped"],
                    }
                    for jar, r in rows.items()
                }
                for name, rows in pers.items()
            },
        }
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("\nđã ghi", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
