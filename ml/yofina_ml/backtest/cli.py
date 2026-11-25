"""Dòng lệnh của backtest (gọi từ `scripts/ml_backtest.py`)."""

from __future__ import annotations

import argparse
import importlib
import json
import platform
import statistics
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from yofina_ml.backtest import calibrate as cal_mod
from yofina_ml.backtest import evaluate as ev
from yofina_ml.backtest import report, studies
from yofina_ml.backtest.common import CAL_SEEDS, EVAL_SEEDS, HORIZON, personas
from yofina_ml.calibration import default as calibration_default
from yofina_ml.calibration import default_calibration
from yofina_ml.forecast import forecast_user, update_forecast
from yofina_ml.synth import FAMILIES
from yofina_ml.synth.base import build_inputs
from yofina_ml.types import ForecastConfig

PROB_BAND = (0.75, 0.85)  # độ phủ tổng 30 ngày phải nằm trong khoảng này mới được phát xác suất
CALIBRATION_PATH = Path(__file__).resolve().parents[1] / "calibration" / "default.py"


def _cal_dict(result: dict[str, Any]) -> dict[str, Any]:
    """Tham số mới của hiệu chỉnh; ngưỡng lịch sử BR-31 giữ nguyên từ bản hiện hành (do `scripts/ml_history_gate.py` chọn)."""
    kinds = result["kinds"]
    current = default_calibration()
    out: dict[str, Any] = {}
    for k in ("dense", "sparse", "cold_start"):
        src = kinds.get(k) or kinds["dense"]
        out[k] = {
            "rho": src["rho"],
            "level_sigma": src["level_sigma"],
            "probability_ok": False,
            "probability_min_history_days": current.for_kind(k).probability_min_history_days,
        }
    return out


def run_calibration(args: argparse.Namespace, families=None) -> dict[str, Any]:
    seeds = CAL_SEEDS[:1] if args.quick else CAL_SEEDS
    ps = personas(families or FAMILIES, seeds)
    origin_list = cal_mod.default_origin_list()
    if args.quick:
        origin_list = origin_list[::2]
    units = cal_mod.collect_units(ps, origin_list)
    units += cal_mod.collect_units(ps, cal_mod.cold_start_origins())
    print(f"[hiệu chỉnh] {len(units)} đơn vị (origin x hũ) từ {len(ps)} persona", flush=True)
    return cal_mod.calibrate(units, n_paths=args.cal_paths)


def probability_gate(
    rows: list[dict[str, Any]], shortfall_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Quyết định `probability_ok` từng loại chuỗi: độ phủ tổng 30 ngày trong [0,75; 0,85] ở TỪNG họ và gộp, và xác suất hụt
    có kỹ năng hơn chỉ dùng tần suất chung (Brier thấp hơn)."""
    gate: dict[str, Any] = {}
    for kind in ("dense", "sparse"):
        cov = {}
        for fam in [*sorted({r["family"] for r in rows}), "all"]:
            sel = [r for r in rows if r["bucket"] == kind and (fam == "all" or r["family"] == fam)]
            cov[fam] = float(np.mean([r["cum30_in"] for r in sel])) if sel else None
        rel = ev.reliability([r for r in shortfall_rows if r["bucket"] == kind])
        ok_cov = all(v is not None and PROB_BAND[0] <= v <= PROB_BAND[1] for v in cov.values())
        ok_skill = bool(rel) and rel["brier"] < rel["brier_climatology"]
        gate[kind] = {
            "cov30": cov,
            "brier": rel.get("brier"),
            "brier_climatology": rel.get("brier_climatology"),
            "ok": ok_cov and ok_skill,
        }
    return gate


def write_calibration(args: argparse.Namespace) -> dict[str, Any]:
    res = run_calibration(args)
    cal = _cal_dict(res)
    eval_seeds = EVAL_SEEDS[:2] if args.quick else EVAL_SEEDS
    ps = personas(FAMILIES, eval_seeds)
    extra = {"calibration": cal}
    rows = ev.evaluate(
        ps, n_paths=args.paths, config_extra=extra, step=14 if args.quick else 7, progress=True
    )
    short_rows = ev.evaluate_shortfall(ps, n_paths=args.paths, config_extra=extra)
    gate = probability_gate(rows, short_rows)
    for k in ("dense", "sparse"):
        cal[k]["probability_ok"] = bool(gate[k]["ok"])
    payload = {
        "version": args.version,
        **cal,
        "meta": {
            "method": "chọn (rho, level_sigma) theo độ phủ P10-P90 của tổng chi cộng dồn 7/14/30 ngày, trọng số 0,2/0,3/0,5",
            "families": sorted(FAMILIES),
            "calibration_seeds": list(CAL_SEEDS[:1] if args.quick else CAL_SEEDS),
            "heldout_seeds": list(eval_seeds),
            "prob_band_h30": list(PROB_BAND),
            "gate": gate,
            "cov_after": {k: res["kinds"][k]["cov_after"] for k in res["kinds"]},
            "cov_before_rho0_3": {k: res["kinds"][k]["cov_before_rho0_3"] for k in res["kinds"]},
            **{
                k: v
                for k, v in calibration_default.CALIBRATION.get("meta", {}).items()
                if k == "history_gate"
            },  # số đo của ngưỡng lịch sử đi cùng ngưỡng đã giữ lại
        },
    }
    report.write_default_calibration(CALIBRATION_PATH, payload)
    importlib.reload(calibration_default)  # các bước đo sau trong cùng tiến trình dùng bản vừa ghi
    print(f"[hiệu chỉnh] đã ghi {CALIBRATION_PATH}", flush=True)
    return {"calibration": res, "gate": gate}


UNCALIBRATED = {
    "dense": {"rho": 0.3, "level_sigma": 0.0},
    "sparse": {"rho": 0.0, "level_sigma": 0.0},
    "cold_start": {"rho": 0.3, "level_sigma": 0.0},
}  # trước hiệu chỉnh: copula AR(1) với rho cỡ tự tương quan lag-1 của sai số, không hệ số mức


def run_evaluation(args: argparse.Namespace):
    seeds = EVAL_SEEDS[:2] if args.quick else EVAL_SEEDS
    ps = personas(FAMILIES, seeds)
    step = 14 if args.quick else 7
    rows = ev.evaluate(ps, n_paths=args.paths, step=step, progress=True)
    uncal = ev.evaluate(
        ps, n_paths=args.paths, step=step, config_extra={"calibration": UNCALIBRATED}
    )
    return {
        "summary": ev.summarize(rows),
        "summary_uncalibrated": ev.summarize(uncal),
        "rows": len(rows),
    }, rows


def run_transfer(args: argparse.Namespace) -> dict[str, Any]:
    """Hiệu chỉnh trên MỘT họ rồi đo độ phủ trên họ KIA (seed giữ ra ngoài): hiệu chỉnh có chuyển được giữa hai cơ chế sinh
    dữ liệu khác hẳn nhau không."""
    out: dict[str, Any] = {}
    fams = sorted(FAMILIES)
    for src, dst in ((fams[0], fams[1]), (fams[1], fams[0])):
        res = run_calibration(args, [src])
        cal = _cal_dict(res)
        rows = ev.evaluate(
            personas([dst], EVAL_SEEDS[:2] if args.quick else EVAL_SEEDS[:4]),
            n_paths=args.paths,
            step=14,
            config_extra={"calibration": cal},
        )
        summ = ev.summarize(rows)["by_family"][dst]
        out[f"{src} -> {dst}"] = {
            "calibration": {k: cal[k] for k in ("dense", "sparse")},
            "cov_cum30": {b: summ[b]["all"]["cov_cum30"] for b in ("dense", "sparse") if b in summ},
        }
    return out


def run_timing() -> dict[str, Any]:
    from yofina_ml.backtest.common import persona as get_persona

    p = get_persona("hurdle_lognormal", "office", 201)
    out: dict[str, Any] = {
        "machine": platform.processor() or platform.machine(),
        "python": platform.python_version(),
        "numpy": np.__version__,
    }
    for n_paths in (2000, 5000, 10000):
        cfg = ForecastConfig(n_paths=n_paths, seed=7)
        inputs = build_inputs(p, 250, 30, cfg)
        forecast_user(inputs)  # khởi động
        ts = []
        res = None
        for _ in range(15):
            t = time.perf_counter()
            res = forecast_user(inputs)
            ts.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        for _ in range(15):
            update_forecast(inputs, res, ["an_uong", "giai_tri"])
        upd2 = (time.perf_counter() - t) / 15 * 1000
        out[f"forecast_user_{n_paths}_ms_median"] = round(statistics.median(ts), 1)
        out[f"forecast_user_{n_paths}_ms_max"] = round(max(ts), 1)
        out[f"update_forecast_2jars_{n_paths}_ms"] = round(upd2, 1)
    out["jars"] = len(inputs.jars)
    out["history_days"] = 250
    return out


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # console Windows mặc định cp1252
    ap = argparse.ArgumentParser(
        description="Backtest rolling-origin của yofina_ml (dữ liệu tổng hợp, hai họ bộ sinh)"
    )
    ap.add_argument("--quick", action="store_true", help="ít seed và origin (kiểm khói)")
    ap.add_argument(
        "--calibrate", action="store_true", help="chọn rho, level_sigma (in, không ghi file)"
    )
    ap.add_argument(
        "--write-calibration",
        action="store_true",
        help="hiệu chỉnh, kiểm giữ-ra-ngoài, ghi calibration/default.py",
    )
    ap.add_argument(
        "--evaluate",
        action="store_true",
        help="đo forecast_user trên seed giữ ra ngoài với hiệu chỉnh hiện tại",
    )
    ap.add_argument("--shortfall", action="store_true", help="độ tin cậy của xác suất hụt")
    ap.add_argument(
        "--short-history", action="store_true", help="mô hình nào thắng theo độ dài lịch sử"
    )
    ap.add_argument("--ablation", action="store_true", help="ablation của hurdle")
    ap.add_argument("--statsforecast", action="store_true", help="so với StatsForecast (cần cài)")
    ap.add_argument(
        "--transfer", action="store_true", help="hiệu chỉnh trên một họ, đo trên họ kia"
    )
    ap.add_argument("--timing", action="store_true", help="đo thời gian chạy")
    ap.add_argument("--all", action="store_true", help="mọi khảo sát trừ StatsForecast")
    ap.add_argument("--paths", type=int, default=2000, help="số đường Monte Carlo khi đo")
    ap.add_argument("--cal-paths", type=int, default=1500)
    ap.add_argument("--version", default=f"phase2-{date.today().isoformat()}")
    ap.add_argument("--out", type=Path, default=None, help="ghi kết quả JSON")
    ap.add_argument("--tables", type=Path, default=None, help="ghi bảng markdown")
    args = ap.parse_args(argv)
    if args.all:
        args.write_calibration = args.evaluate = args.shortfall = True
        args.short_history = args.ablation = args.timing = args.transfer = True
    chosen = [
        args.calibrate, args.write_calibration, args.evaluate, args.shortfall,
        args.short_history, args.ablation, args.statsforecast, args.timing, args.transfer,
    ]  # fmt: skip
    if not any(chosen):
        ap.error("chọn ít nhất một việc (--all, --evaluate, ...)")
    results: dict[str, Any] = {}
    md: list[str] = []
    eval_ps = personas(FAMILIES, EVAL_SEEDS[:2] if args.quick else EVAL_SEEDS)
    thin = eval_ps[::3] if args.quick else eval_ps

    if args.write_calibration:
        out = write_calibration(args)
        results["calibration"] = out
        md += ["### Hiệu chỉnh", report.render_calibration(out["calibration"]), ""]
    elif args.calibrate:
        res = run_calibration(args)
        results["calibration_dry"] = res
        md += ["### Hiệu chỉnh (chạy thử, không ghi)", report.render_calibration(res), ""]
    if args.evaluate:
        data, _rows = run_evaluation(args)
        results["evaluate"] = data
        md += [
            "### Theo ngày", report.render_daily(data["summary"]), "",
            "### Theo tổng cộng dồn, SAU hiệu chỉnh", report.render_cum(data["summary"]), "",
            "### Theo tổng cộng dồn, TRƯỚC hiệu chỉnh", report.render_cum(data["summary_uncalibrated"]), "",
        ]  # fmt: skip
    if args.transfer:
        tr = run_transfer(args)
        results["transfer"] = tr
        md += [
            "### Chuyển hiệu chỉnh giữa hai họ (phủ số dư 30 ngày)",
            "```json",
            json.dumps(tr, ensure_ascii=False, indent=1),
            "```",
            "",
        ]
    if args.shortfall:
        sf_rows = ev.evaluate_shortfall(eval_ps, n_paths=args.paths)
        rel = {
            k: ev.reliability([r for r in sf_rows if r["bucket"] == k]) for k in ("dense", "sparse")
        }
        results["shortfall"] = rel
        for k, v in rel.items():
            md += [report.render_reliability(v, f"Xác suất hụt, {report.BUCKET_LABEL[k]}"), ""]
    if args.short_history:
        sh = studies.short_history(thin, windows=24)
        results["short_history"] = {str(k): v for k, v in sh.items()}
        md += ["### Độ dài lịch sử", report.render_short(sh), ""]
    if args.ablation:
        ab = studies.ablation(thin)
        results["ablation"] = ab
        md += ["### Ablation hurdle", report.render_ablation(ab), ""]
    if args.statsforecast:
        sfc = studies.statsforecast_compare(eval_ps[:: (3 if args.quick else 2)])
        results["statsforecast"] = sfc
        md += ["### StatsForecast", report.render_sf(sfc), ""]
    if args.timing:
        tm = run_timing()
        results["timing"] = tm
        md += [
            "### Thời gian chạy",
            "```json",
            json.dumps(tm, ensure_ascii=False, indent=1),
            "```",
            "",
        ]
    results["horizon"] = HORIZON
    results["default_calibration"] = default_calibration().to_dict()
    text = "\n".join(md)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(results, ensure_ascii=False, indent=1, default=float), encoding="utf-8"
        )
    if args.tables:
        args.tables.parent.mkdir(parents=True, exist_ok=True)
        args.tables.write_text(text, encoding="utf-8")
