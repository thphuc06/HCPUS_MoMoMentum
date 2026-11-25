"""Hiệu chỉnh lại sau Monte Carlo (#25): học CQR bất đối xứng cho dải số dư hũ dày và PAV cho `p_shortfall` trên tập hiệu chỉnh,
đo trước/sau trên tập kiểm, quyết định công tắc `recalibrate` và ghi bảng vào `calibration/default.py`.

Tách tập: học trên persona seed `CAL_SEEDS` (101-104), đo trên persona seed `EVAL_SEEDS` (201-206); cả hai họ bộ sinh, mọi cấu
hình. Không persona nào nằm ở cả hai tập, nên số trên tập kiểm không đo trên dữ liệu đã học.

Lịch sử: mỗi (persona, origin) được dự báo lại với lịch sử cắt còn L ngày (`studies._truncate`, như người dùng mới vào app L ngày
trước), L thuộc `LENGTHS` (47 ngày như `lan`, `vy`; 120 ngày như `minh`; lịch sử đủ). Cổng đọc ở `GATE_LENGTH` = 120 ngày, hai độ
dài kia chỉ phải không trượt khỏi dải [0,75; 0,85]. Origin chung từ ngày 120 bước 7, chân trời 30 ngày, hạt Monte Carlo
`seed * 1000 + origin` (như `history_gate`), 2.000 đường.

- **Dải số dư (CQR)**: bản ghi (hũ dày, origin) gồm P10/P50/P90 số dư dự báo 30 ngày của `forecast_user` (công tắc tắt), số dư thật
  từ sổ cái của bộ sinh và chi TB 28 ngày lịch sử cuối. `recalibration.fit_cqr` học độ lệch từng phía ở mỗi ngày 1..30 (mỗi đuôi
  0,1), riêng cho từng nhóm độ dài lịch sử của `CQR_GROUPS` (Mondrian): bảng học ở 47 ngày cho hũ dưới 120 ngày lịch sử, bảng học
  ở 120 ngày và lịch sử đủ cho hũ từ 120 ngày. Một bảng gộp làm hẹp đuôi trên theo lịch sử dài và đẩy độ phủ ở 47 ngày xuống dưới
  0,75 (đã thấy khi chia đôi chính tập hiệu chỉnh, seed 101-102 so với 103-104, trước khi đo tập kiểm). "Sau" là `forecast_user`
  chạy lại với công tắc bật và bảng vừa học (đúng đường mã sản phẩm).
- **p_shortfall (PAV)**: số dư kịch bản b = alpha x chi TB 28 ngày x w (w = số ngày tới lương, cần w >= 3), như
  `evaluate.evaluate_shortfall`: số dư thật của bộ sinh hiếm khi âm trước kỳ lương nên Brier theo số dư thật suy biến
  (backtest-final.md). p thô là `summarize_paths` trên cùng đường Monte Carlo mà `forecast_user` dùng cho hũ đó (common random
  numbers), kết cục là chi thật trong w ngày vượt b. PAV học riêng hũ dày và hũ thưa, chỉ trên các ca mà sản phẩm có hiện %
  (lịch sử từ `probability_min_history_days` của loại chuỗi); không gồm hũ nghĩa vụ.
- **Ngày cạn**: trên cùng số dư kịch bản, ngày dự báo là ngày đầu số dư P50 <= 0 trong chân trời (như `JarSummary.runout_date`),
  ngày thật là ngày đầu số dư thật <= 0. Đo để biết vì sao hũ thưa không nêu ngày: sau khi bật, hũ thưa không có ngày để chấm.

Cổng bật `recalibrate` (`gate`), đọc trên tập kiểm, hũ dày, ngày 30: ở 120 ngày độ phủ P10-P90 trong [0,75; 0,85] ở số gộp và từng
họ, thật dưới P10 và thật trên P90 mỗi phía trong [0,075; 0,125] (10% +- 2,5 điểm, tức nửa dải của độ phủ); ở 47 ngày và lịch sử
đủ độ phủ gộp vẫn trong [0,75; 0,85]; Brier của p sau PAV không cao hơn trước ở cả hũ dày và hũ thưa (120 ngày).
"""

from __future__ import annotations

import copy
import time
from dataclasses import replace
from typing import Any

import numpy as np

from yofina_ml.backtest.common import CAL_SEEDS, EVAL_SEEDS, HORIZON, origins, personas
from yofina_ml.backtest.evaluate import SHORTFALL_ALPHAS, reliability
from yofina_ml.backtest.studies import _truncate
from yofina_ml.calibration import calibrated_config, default_calibration
from yofina_ml.forecast import forecast_user, make_context
from yofina_ml.marginals import marginal_from_state
from yofina_ml.montecarlo import (
    SimSpec,
    balance_from_draws,
    draw_paths,
    jar_seed_sequence,
    summarize_paths,
)
from yofina_ml.recalibration import Isotonic, fit_cqr, fit_isotonic
from yofina_ml.synth import FAMILIES
from yofina_ml.synth.base import OBLIGATION_JAR, SynthPersona, build_inputs

PROB_BAND = (0.75, 0.85)  # độ phủ P10-P90 (như cổng BR-31)
TAIL_BAND = (0.075, 0.125)  # mỗi đuôi: 10% +- 2,5 điểm
TAIL = 0.1  # mức của mỗi đuôi khi fit CQR (dải P10-P90)
#: chi TB của ngần này ngày lịch sử cuối là đơn vị của điểm CQR và của số dư kịch bản
SCALE_DAYS = 28
FULL = "full"
LENGTHS: tuple[int | str, ...] = (47, 120, FULL)
GATE_LENGTH = 120
#: nhóm CQR theo độ dài lịch sử: (min_history_days của bảng, các độ dài L dùng để học bảng đó)
CQR_GROUPS: tuple[tuple[int, tuple[int | str, ...]], ...] = ((0, (47,)), (120, (120, FULL)))
FIRST_ORIGIN = 120
STEP = 7
MARKS = (7, 14, 30)
SHORT_KINDS = ("dense", "sparse")
_UNGATED = {k: {"probability_min_history_days": 0} for k in SHORT_KINDS}


# --------------------------------------------------------------------------------------
# Thu bản ghi
# --------------------------------------------------------------------------------------
def _calibration_override(tables: dict[str, Any] | None, recalibrate: bool) -> dict[str, Any]:
    over: dict[str, Any] = {"recalibrate": recalibrate}
    for k in SHORT_KINDS:
        over[k] = {**_UNGATED[k], **((tables or {}).get(k) or {})}
    return over


def _scale(spend: tuple[int, ...]) -> float:
    recent = spend[-SCALE_DAYS:]
    return float(np.mean(recent)) if recent else 0.0


def _scenarios(
    p: SynthPersona, o: int, inputs, res, length: int | str, horizon: int
) -> list[dict[str, Any]]:
    """Bản ghi số dư kịch bản cho mọi hũ chi tiêu và tiết kiệm của một lần chạy (xem docstring module)."""
    ctx = make_context(inputs)
    w = ctx.window
    if w < 3:
        return []
    default = default_calibration()
    thr = float(ctx.prm.runout_balance_threshold_vnd)
    rows: list[dict[str, Any]] = []
    states = res.run.params["jar_state"]
    for jar in inputs.jars:
        st = states[jar.code]
        kind = st["series_kind"]
        if jar.kind == "obligation" or kind not in SHORT_KINDS:
            continue
        mu = _scale(jar.daily_spend_vnd) * w
        if mu <= 0:
            continue
        ck = ctx.cal.for_kind(kind)
        spec = SimSpec(
            0.0,
            marginal_from_state(st["marginal"]),
            ctx.f_fut,
            kind == "sparse",
            np.zeros(horizon),
            np.zeros(horizon),
            (),
            w,
        )
        draws = draw_paths(
            spec, ck.rho, inputs.config.n_paths,
            jar_seed_sequence(inputs.config.seed, inputs.app_date, jar.code),
        )  # fmt: skip
        true_cum = np.cumsum(p.jar(jar.code).spend[o + 1 : o + 1 + horizon].astype(float))
        shown = default.for_kind(kind).probability_ok_at(jar.history_days)
        for a in SHORTFALL_ALPHAS:
            b = a * mu
            spec_b = replace(spec, balance_vnd=b)
            sim = summarize_paths(balance_from_draws(spec_b, draws, ck.level_sigma), spec_b, thr)
            true_bal = b - true_cum
            hit = np.nonzero(true_bal <= thr)[0]
            rows.append(
                {
                    "length": length,
                    "family": p.family,
                    "seed": p.seed,
                    "bucket": kind,
                    "shown": shown,
                    "p": float(sim.p_shortfall),
                    "event": float(true_bal[:w].min() < 0.0),
                    "pred_day": sim.runout_index,
                    "true_day": int(hit[0]) if len(hit) else None,
                }
            )
    return rows


def collect(
    personas_: list[SynthPersona],
    *,
    lengths: tuple[int | str, ...] = LENGTHS,
    tables: dict[str, Any] | None = None,
    recalibrate: bool = False,
    scenarios: bool = True,
    n_paths: int = 2000,
    step: int = STEP,
    first_origin: int = FIRST_ORIGIN,
    horizon: int = HORIZON,
    progress: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(bản ghi dải hũ dày, bản ghi số dư kịch bản). `tables` và `recalibrate` ghi đè hiệu chỉnh mặc định; cổng lịch sử của %
    tắt khi chạy (để luôn có p), nhưng cờ `shown` của bản ghi kịch bản theo cổng của hiệu chỉnh mặc định."""
    extra = {"calibration": _calibration_override(tables, recalibrate)}
    base = replace(calibrated_config(), probability_enabled=True, extra=extra)
    bands: list[dict[str, Any]] = []
    scen: list[dict[str, Any]] = []
    t0 = time.time()
    for pi, p in enumerate(personas_):
        for o in origins(p.n_days, horizon, first_origin, step):
            full = build_inputs(
                p, o, horizon, replace(base, n_paths=n_paths, seed=p.seed * 1000 + o)
            )
            for length in lengths:
                inputs = full if length == FULL else _truncate(full, int(length))
                res = forecast_user(inputs)
                for jar, jf in zip(inputs.jars, res.jars, strict=True):
                    if jar.code == OBLIGATION_JAR or jf.summary.series_kind != "dense":
                        continue
                    truth = p.balances[jar.code][o + 1 : o + 1 + horizon].astype(float)
                    bands.append(
                        {
                            "length": length,
                            "family": p.family,
                            "seed": p.seed,
                            "scale": _scale(jar.daily_spend_vnd),
                            "p10": np.array([d.balance_p10_vnd for d in jf.days], dtype=float),
                            "p50": np.array([d.balance_p50_vnd for d in jf.days], dtype=float),
                            "p90": np.array([d.balance_p90_vnd for d in jf.days], dtype=float),
                            "truth": truth,
                        }
                    )
                if scenarios:
                    scen += _scenarios(p, o, inputs, res, length, horizon)
        if progress:
            print(f"  [{pi + 1}/{len(personas_)}] {time.time() - t0:.0f}s", flush=True)
    return bands, scen


# --------------------------------------------------------------------------------------
# Học
# --------------------------------------------------------------------------------------
def fit_tables(bands: list[dict[str, Any]], scen: list[dict[str, Any]]) -> dict[str, Any]:
    """Bảng hiệu chỉnh lại theo dạng của `calibration/default.py`: CQR cho hũ dày (một bảng mỗi nhóm của `CQR_GROUPS`), PAV
    cho hũ dày và hũ thưa."""
    horizon = len(bands[0]["truth"])
    hs = np.arange(1, horizon + 1)
    cqr: list[dict[str, Any]] = []
    for min_days, lengths in CQR_GROUPS:
        sel = [r for r in bands if r["length"] in lengths]
        band = fit_cqr(
            h=np.tile(hs, len(sel)),
            lower=np.concatenate([r["p10"] for r in sel]),
            upper=np.concatenate([r["p90"] for r in sel]),
            truth=np.concatenate([r["truth"] for r in sel]),
            scale=np.repeat([r["scale"] for r in sel], horizon),
            tail=TAIL,
            scale_days=SCALE_DAYS,
            min_history_days=min_days,
        )
        cqr.append(band.to_dict())
    tables: dict[str, Any] = {"dense": {"cqr": cqr}, "sparse": {}}
    for kind in SHORT_KINDS:
        sel = [r for r in scen if r["bucket"] == kind and r["shown"]]
        iso = fit_isotonic([r["p"] for r in sel], [r["event"] for r in sel])
        tables[kind]["p_isotonic"] = iso.to_dict()
    return tables


# --------------------------------------------------------------------------------------
# Tổng hợp
# --------------------------------------------------------------------------------------
def _r(v: float | None, nd: int = 3) -> float | None:
    return None if v is None else round(float(v), nd)


def band_summary(bands: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{độ dài: số đo dải hũ dày}: độ phủ ngày 7/14/30, theo họ ở ngày 30, thật dưới P10 / trên P90, độ rộng tương đối."""
    out: dict[str, dict[str, Any]] = {}
    for length in dict.fromkeys(r["length"] for r in bands):
        sel = [r for r in bands if r["length"] == length]
        cell: dict[str, Any] = {"n": len(sel)}
        for h in MARKS:
            i = h - 1
            cell[f"cov{h}"] = _r(
                np.mean([r["p10"][i] <= r["truth"][i] <= r["p90"][i] for r in sel])
            )
        i = HORIZON - 1
        cell["cov30_by_family"] = {
            f: _r(np.mean([r["p10"][i] <= r["truth"][i] <= r["p90"][i] for r in sel if r["family"] == f]))
            for f in sorted({r["family"] for r in sel})
        }  # fmt: skip
        cell["below_p10_30"] = _r(np.mean([r["truth"][i] < r["p10"][i] for r in sel]))
        cell["above_p90_30"] = _r(np.mean([r["truth"][i] > r["p90"][i] for r in sel]))
        widths = [
            (r["p90"][i] - r["p10"][i]) / (r["scale"] * HORIZON) for r in sel if r["scale"] > 0
        ]
        cell["width30"] = _r(np.mean(widths))
        out[str(length)] = cell
    return out


def _calibrated(scen: list[dict[str, Any]], tables: dict[str, Any]) -> list[dict[str, Any]]:
    isos = {k: Isotonic.from_dict(tables[k]["p_isotonic"]) for k in SHORT_KINDS}
    return [{**r, "p": isos[r["bucket"]](r["p"])} for r in scen]


def _max_gap(rel: dict[str, Any]) -> float | None:
    """Sai lệch lớn nhất |p dự báo TB - tần suất thật| qua các ô của bảng độ tin cậy (ô từ 30 bản ghi)."""
    gaps = [abs(t["mean_p"] - t["freq"]) for t in rel.get("table", []) if t["n"] >= 30]
    return _r(max(gaps)) if gaps else None


def shortfall_summary(scen: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{độ dài: {nhóm: Brier, Brier tần suất chung, sai lệch độ tin cậy lớn nhất, bảng độ tin cậy}} trên các ca có hiện %."""
    out: dict[str, dict[str, Any]] = {}
    for length in dict.fromkeys(r["length"] for r in scen):
        cells: dict[str, Any] = {}
        for kind in SHORT_KINDS:
            sel = [r for r in scen if r["length"] == length and r["bucket"] == kind and r["shown"]]
            if not sel:
                continue
            rel = reliability(sel)
            cells[kind] = {
                "n": rel["n"],
                "brier": _r(rel["brier"], 6),
                "brier_climatology": _r(rel["brier_climatology"], 6),
                "max_gap": _max_gap(rel),
                "table": [
                    {"bin": t["bin"], "n": t["n"], "mean_p": _r(t["mean_p"]), "freq": _r(t["freq"])}
                    for t in rel["table"]
                ],
            }
        out[str(length)] = cells
    return out


def runout_summary(scen: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{độ dài: {nhóm: số ca có ngày dự báo, tỷ lệ trong +-3 ngày (thật không cạn trong chân trời tính là trượt), sai TB khi cả
    hai ngày cùng có}} trên số dư kịch bản, mọi ca (ngày cạn hiện bất kể có hiện % không)."""
    out: dict[str, dict[str, Any]] = {}
    for length in dict.fromkeys(r["length"] for r in scen):
        cells: dict[str, Any] = {}
        for kind in SHORT_KINDS:
            sel = [
                r for r in scen
                if r["length"] == length and r["bucket"] == kind and r["pred_day"] is not None
            ]  # fmt: skip
            both = [r for r in sel if r["true_day"] is not None]
            err = [abs(r["pred_day"] - r["true_day"]) for r in both]
            cells[kind] = {
                "n_pred": len(sel),
                "within3": _r(sum(e <= 3 for e in err) / len(sel)) if sel else None,
                "mae_days": _r(np.mean(err), 2) if err else None,
            }
        out[str(length)] = cells
    return out


def _in(v: float | None, band: tuple[float, float]) -> bool:
    return v is not None and band[0] <= v <= band[1]


def gate(
    after: dict[str, Any], sf_before: dict[str, Any], sf_after: dict[str, Any]
) -> dict[str, Any]:
    """Luật bật công tắc (docstring module). Trả từng điều kiện và kết luận `ok`."""
    g = str(GATE_LENGTH)
    a = after[g]
    checks = {
        "cov30_120_gop_va_theo_ho": _in(a["cov30"], PROB_BAND)
        and all(_in(v, PROB_BAND) for v in a["cov30_by_family"].values()),
        "duoi_p10_120": _in(a["below_p10_30"], TAIL_BAND),
        "tren_p90_120": _in(a["above_p90_30"], TAIL_BAND),
        "cov30_do_dai_khac": all(_in(c["cov30"], PROB_BAND) for k, c in after.items() if k != g),
        "brier_khong_tang_120": all(
            sf_after[g][k]["brier"] <= sf_before[g][k]["brier"] for k in SHORT_KINDS
        ),
    }
    return {"checks": checks, "ok": all(checks.values())}


def run(*, quick: bool = False, n_paths: int = 2000, progress: bool = True) -> dict[str, Any]:
    cal_seeds = CAL_SEEDS[:1] if quick else CAL_SEEDS
    eval_seeds = EVAL_SEEDS[:2] if quick else EVAL_SEEDS
    step = 28 if quick else STEP
    t0 = time.time()
    kw = {"n_paths": n_paths, "step": step, "progress": progress}
    if progress:
        print("[hiệu chỉnh lại] học trên seed", list(cal_seeds), flush=True)
    fit_bands, fit_scen = collect(personas(FAMILIES, cal_seeds), **kw)
    tables = fit_tables(fit_bands, fit_scen)
    if progress:
        print("[hiệu chỉnh lại] đo trên seed", list(eval_seeds), "(trước, rồi sau)", flush=True)
    eval_ps = personas(FAMILIES, eval_seeds)
    before, scen = collect(eval_ps, **kw)
    after, _ = collect(eval_ps, tables=tables, recalibrate=True, scenarios=False, **kw)
    bands = {"before": band_summary(before), "after": band_summary(after)}
    sf = {"before": shortfall_summary(scen), "after": shortfall_summary(_calibrated(scen, tables))}
    return {
        "method": f"lịch sử cắt {list(LENGTHS)}, origin từ ngày {FIRST_ORIGIN} bước {step}, chân trời {HORIZON}, "
        f"{n_paths} đường; CQR mỗi đuôi {TAIL}, đơn vị chi TB {SCALE_DAYS} ngày x h; PAV trên số dư kịch bản "
        f"alpha {list(SHORTFALL_ALPHAS)}",
        "calibration_seeds": list(cal_seeds),
        "heldout_seeds": list(eval_seeds),
        "families": sorted(FAMILIES),
        "fit_rows": {"bands": len(fit_bands), "scenarios": len(fit_scen)},
        "eval_rows": {"bands": len(before), "scenarios": len(scen)},
        "tables": tables,
        "bands": bands,
        "shortfall": sf,
        "runout": runout_summary(scen),
        "gate": gate(bands["after"], sf["before"], sf["after"]),
        "seconds": round(time.time() - t0, 1),
    }


def calibration_payload(current: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Bản `CALIBRATION` mới: giữ nguyên mọi thứ, thêm bảng CQR/PAV vừa học, đặt `recalibrate` theo cổng, ghi số đo vào meta."""
    payload = copy.deepcopy(current)
    payload["recalibrate"] = bool(result["gate"]["ok"])
    for kind in (*SHORT_KINDS, "cold_start"):
        payload[kind].pop("p_isotonic", None)
        payload[kind].pop("cqr", None)
        payload[kind].update(copy.deepcopy(result["tables"].get(kind, {})))
    g = str(GATE_LENGTH)
    payload.setdefault("meta", {})["recalibration"] = {
        k: result[k] for k in ("method", "calibration_seeds", "heldout_seeds")
    } | {
        "gate_length": GATE_LENGTH,
        "prob_band_h30": list(PROB_BAND),
        "tail_band_h30": list(TAIL_BAND),
        "gate": result["gate"],
        "dense_band_h30": {
            side: {
                k: result["bands"][side][g][k]
                for k in ("cov30", "below_p10_30", "above_p90_30", "width30")
            }
            for side in ("before", "after")
        },
        "brier": {
            side: {k: result["shortfall"][side][g][k]["brier"] for k in SHORT_KINDS}
            for side in ("before", "after")
        },
    }
    return payload


# --------------------------------------------------------------------------------------
# Bảng markdown
# --------------------------------------------------------------------------------------
def _f(v: float | None, nd: int = 3) -> str:
    return "-" if v is None else f"{v:.{nd}f}".replace(".", ",")


def _arrow(a: float | None, b: float | None, nd: int = 3) -> str:
    return f"{_f(a, nd)} → {_f(b, nd)}"


def render(result: dict[str, Any]) -> str:
    bb, ba = result["bands"]["before"], result["bands"]["after"]
    lines = [
        "| Lịch sử | n | Phủ 30 ngày trước → sau | Phủ 30 ngày theo họ (sau) | Phủ 7 / 14 ngày (sau) "
        "| Dưới P10 trước → sau | Trên P90 trước → sau | Độ rộng tương đối trước → sau |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for length, a in ba.items():
        b = bb[length]
        fam = " / ".join(_f(v) for v in a["cov30_by_family"].values())
        change = (a["width30"] / b["width30"] - 1.0) * 100 if b["width30"] else 0.0
        lines.append(
            f"| {length} | {a['n']} | {_arrow(b['cov30'], a['cov30'])} | {fam} | {_f(a['cov7'])} / {_f(a['cov14'])} "
            f"| {_arrow(b['below_p10_30'], a['below_p10_30'])} | {_arrow(b['above_p90_30'], a['above_p90_30'])} "
            f"| {_arrow(b['width30'], a['width30'], 2)} ({change:+.0f}%) |"
        )
    lines += [
        "",
        "| Lịch sử | Nhóm | n | Brier trước → sau | Brier tần suất chung | Sai lệch độ tin cậy lớn nhất trước → sau "
        "| Độ tin cậy trước (p TB → tần suất thật) | Độ tin cậy sau |",
        "|---|---|---|---|---|---|---|---|",
    ]
    sb, sa = result["shortfall"]["before"], result["shortfall"]["after"]

    def rel(cell: dict[str, Any]) -> str:
        return "; ".join(f"{_f(t['mean_p'], 2)}→{_f(t['freq'], 2)}" for t in cell["table"])

    for length, cells in sa.items():
        for kind, a in cells.items():
            b = sb[length][kind]
            lines.append(
                f"| {length} | {kind} | {a['n']} | {_arrow(b['brier'], a['brier'], 4)} | {_f(a['brier_climatology'], 4)} "
                f"| {_arrow(b['max_gap'], a['max_gap'])} | {rel(b)} | {rel(a)} |"
            )
    lines += [
        "",
        "| Lịch sử | Nhóm | Ca có ngày dự báo | Trong ±3 ngày | Sai TB (ngày) |",
        "|---|---|---|---|---|",
    ]
    for length, cells in result["runout"].items():
        for kind, c in cells.items():
            lines.append(
                f"| {length} | {kind} | {c['n_pred']} | {_f(c['within3'])} | {_f(c['mae_days'], 2)} |"
            )
    lines += ["", f"Cổng: {result['gate']}"]
    return "\n".join(lines)


__all__ = [
    "LENGTHS",
    "calibration_payload",
    "collect",
    "fit_tables",
    "gate",
    "render",
    "run",
]
