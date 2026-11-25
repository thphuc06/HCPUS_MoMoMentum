"""Độ phủ của dải số dư theo ĐỘ DÀI LỊCH SỬ, để chọn ngưỡng `probability_min_history_days` của BR-31 (issue #9).

Backtest phase 2 chỉ đo ở origin từ ngày 90 với toàn bộ lịch sử (`common.FIRST_ORIGIN`), nên không thấy dải hũ thưa hụt độ phủ khi
người dùng mới có vài chục ngày lịch sử. Ở đây mỗi (persona, origin) được dự báo lại với lịch sử cắt còn L ngày gần nhất
(`studies._truncate`, như người dùng mới vào app L ngày trước), cùng một tập origin cho mọi L để các độ dài so được với nhau.

Đo trên seed giữ ra ngoài (`EVAL_SEEDS`), chân trời 30 ngày, hiệu chỉnh hiện tại (`calibrated_config()`) nhưng TẮT cổng lịch sử
(ngưỡng 0) để luôn có `p_shortfall` mà chấm Brier. Tất định: hạt Monte Carlo là `seed * 1000 + origin` như `evaluate.evaluate`.

Luật chọn ngưỡng (giống `cli.probability_gate`, thêm chiều độ dài): với mỗi loại chuỗi, ngưỡng là độ dài NHỎ NHẤT trong lưới mà
từ đó trở lên (mọi độ dài lớn hơn trong lưới và lịch sử đủ) độ phủ số dư ngày 30 nằm trong [0,75; 0,85] ở từng họ bộ sinh và gộp.
Brier của p_shortfall theo số dư THẬT chỉ in để tham khảo, không vào luật: số dư thật của bộ sinh hiếm khi âm trước kỳ lương nên
tần suất chung gần 0 và phép so kỹ năng suy biến; kỹ năng xác suất theo độ dài lịch sử đo bằng số dư kịch bản ở
docs/research/2026-11-25-audit-ml-forecasting.md §2.2.
"""

from __future__ import annotations

import copy
import time
from dataclasses import replace
from typing import Any

import numpy as np

from yofina_ml.backtest.common import EVAL_SEEDS, HORIZON, origins, personas
from yofina_ml.backtest.studies import _truncate
from yofina_ml.calibration import calibrated_config
from yofina_ml.forecast import forecast_user
from yofina_ml.synth import FAMILIES
from yofina_ml.synth.base import OBLIGATION_JAR, build_inputs

PROB_BAND = (0.75, 0.85)
LENGTHS = (30, 47, 60, 75, 90, 105, 120)
FULL = "full"  # không cắt: lịch sử bằng origin (120 đến 293 ngày)
FIRST_ORIGIN = 120  # origin chung cho mọi độ dài, không nhỏ hơn độ dài lớn nhất của lưới
STEP = 7
KINDS = ("dense", "sparse")
_UNGATED = {"calibration": {k: {"probability_min_history_days": 0} for k in KINDS}}


def measure(
    personas_: list,
    *,
    lengths: tuple[int, ...] = LENGTHS,
    n_paths: int = 2000,
    step: int = STEP,
    first_origin: int = FIRST_ORIGIN,
    horizon: int = HORIZON,
    progress: bool = False,
) -> list[dict[str, Any]]:
    """Bản ghi (độ dài, persona, origin, hũ): có nằm trong P10-P90 số dư ở ngày 7/14/30 không, p_shortfall và kết cục thật."""
    base = replace(calibrated_config(), probability_enabled=True, extra=_UNGATED)
    variants: list[int | str] = [*lengths, FULL]
    rows: list[dict[str, Any]] = []
    t0 = time.time()
    for pi, p in enumerate(personas_):
        for o in origins(p.n_days, horizon, first_origin, step):
            full = build_inputs(
                p, o, horizon, replace(base, n_paths=n_paths, seed=p.seed * 1000 + o)
            )
            w = max(0, min((full.next_payday - full.app_date).days - 1, horizon))
            for length in variants:
                inputs = full if length == FULL else _truncate(full, int(length))
                for jf in forecast_user(inputs).jars:
                    s = jf.summary
                    truth = p.balances[s.jar_code][o + 1 : o + 1 + horizon].astype(float)
                    rec: dict[str, Any] = {
                        "length": length,
                        "family": p.family,
                        "bucket": "obligation" if s.jar_code == OBLIGATION_JAR else s.series_kind,
                        "p": s.p_shortfall,
                        "event": float(truth[:w].min() < 0) if w >= 1 else None,
                    }
                    for h in (7, 14, 30):
                        d = jf.days[h - 1]
                        rec[f"in{h}"] = float(
                            d.balance_p10_vnd <= truth[h - 1] <= d.balance_p90_vnd
                        )
                    rec["below30"] = float(truth[29] < jf.days[29].balance_p10_vnd)
                    rec["above30"] = float(truth[29] > jf.days[29].balance_p90_vnd)
                    rows.append(rec)
        if progress:
            print(f"  [{pi + 1}/{len(personas_)}] {time.time() - t0:.0f}s", flush=True)
    return rows


def _mean(rows: list[dict[str, Any]], key: str) -> float | None:
    return round(float(np.mean([r[key] for r in rows])), 3) if rows else None


def summarize(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{độ dài: {nhóm: số đo}}; nhóm là dense, sparse, obligation."""
    out: dict[str, dict[str, Any]] = {}
    for length in dict.fromkeys(r["length"] for r in rows):
        by_len = [r for r in rows if r["length"] == length]
        cells: dict[str, Any] = {}
        for b in (*KINDS, "obligation"):
            sel = [r for r in by_len if r["bucket"] == b]
            if not sel:
                continue
            fams = sorted({r["family"] for r in sel})
            cell: dict[str, Any] = {
                "n": len(sel),
                "cov7": _mean(sel, "in7"),
                "cov14": _mean(sel, "in14"),
                "cov30": _mean(sel, "in30"),
                "cov30_by_family": {
                    f: _mean([r for r in sel if r["family"] == f], "in30") for f in fams
                },
                "below_p10_30": _mean(sel, "below30"),
                "above_p90_30": _mean(sel, "above30"),
            }
            pr = [r for r in sel if r["p"] is not None and r["event"] is not None]
            if pr:
                pv = np.array([r["p"] for r in pr])
                ev = np.array([r["event"] for r in pr])
                cell["brier"] = round(float(np.mean((pv - ev) ** 2)), 4)
                cell["brier_climatology"] = round(float(np.mean((ev.mean() - ev) ** 2)), 4)
            cells[b] = cell
        out[str(length)] = cells
    return out


def _passes(cell: dict[str, Any] | None) -> bool:
    if not cell:
        return False
    covs = [cell["cov30"], *cell["cov30_by_family"].values()]
    return all(v is not None and PROB_BAND[0] <= v <= PROB_BAND[1] for v in covs)


def choose_thresholds(summary: dict[str, dict[str, Any]]) -> dict[str, int | None]:
    """Ngưỡng từng loại chuỗi theo luật ở đầu module; None khi không độ dài nào của lưới (kể cả lịch sử đủ) đạt."""
    lengths = sorted(int(k) for k in summary if k != FULL)
    out: dict[str, int | None] = {}
    for kind in KINDS:
        ok_full = _passes(summary.get(FULL, {}).get(kind))
        chosen = None
        for i, length in enumerate(lengths):
            tail = lengths[i:]
            if ok_full and all(_passes(summary[str(t)].get(kind)) for t in tail):
                chosen = length
                break
        out[kind] = chosen
    return out


def run(*, quick: bool = False, n_paths: int = 2000, progress: bool = True) -> dict[str, Any]:
    seeds = EVAL_SEEDS[:2] if quick else EVAL_SEEDS
    ps = personas(FAMILIES, seeds)
    step = 28 if quick else STEP
    t0 = time.time()
    rows = measure(ps, n_paths=n_paths, step=step, progress=progress)
    summary = summarize(rows)
    return {
        "method": "lịch sử cắt còn L ngày (studies._truncate), origin chung từ ngày "
        f"{FIRST_ORIGIN} bước {step}, chân trời {HORIZON}, {n_paths} đường, cổng lịch sử tắt khi đo",
        "heldout_seeds": list(seeds),
        "families": sorted(FAMILIES),
        "prob_band_h30": list(PROB_BAND),
        "rows": len(rows),
        "seconds": round(time.time() - t0, 1),
        "summary": summary,
        "thresholds": choose_thresholds(summary),
    }


def calibration_payload(current: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Bản `CALIBRATION` mới: giữ nguyên mọi thứ, đặt `probability_min_history_days` của hũ dày và thưa, ghi số đo vào meta.
    Loại chuỗi không độ dài nào đạt thì tắt hẳn `probability_ok`."""
    payload = copy.deepcopy(current)
    lengths = [int(k) for k in result["summary"] if k != FULL]
    for kind, days in result["thresholds"].items():
        if days is None:
            payload[kind]["probability_ok"] = False
            payload[kind]["probability_min_history_days"] = max(lengths) + 1
        else:
            payload[kind]["probability_min_history_days"] = int(days)
    payload.setdefault("meta", {})["history_gate"] = {
        k: result[k] for k in ("method", "heldout_seeds", "prob_band_h30", "thresholds")
    } | {
        "cov30": {
            length: {b: c["cov30"] for b, c in cells.items()}
            for length, cells in result["summary"].items()
        }
    }
    return payload


def render(result: dict[str, Any]) -> str:
    head = "| Lịch sử | Nhóm | n | Phủ 7 / 14 / 30 ngày | Phủ 30 ngày theo họ | Dưới P10 / trên P90 (30) | Brier / tần suất chung |"
    lines = [head, "|---|---|---|---|---|---|---|"]
    for length, cells in result["summary"].items():
        for b, c in cells.items():
            fam = " / ".join(f"{v:.3f}" for v in c["cov30_by_family"].values())
            brier = f"{c['brier']:.3f} / {c['brier_climatology']:.3f}" if "brier" in c else "-"
            lines.append(
                f"| {length} | {b} | {c['n']} | {c['cov7']:.3f} / {c['cov14']:.3f} / {c['cov30']:.3f} | {fam} "
                f"| {c['below_p10_30']:.3f} / {c['above_p90_30']:.3f} | {brier} |"
            )
    lines.append("")
    lines.append(f"Ngưỡng chọn: {result['thresholds']}")
    return "\n".join(lines)
