"""Dự báo một người dùng: ghép mô hình, ACI, Monte Carlo và cổng chất lượng (cài thân hàm của `yofina_ml.api`).

Luồng cho MỖI hũ (`forecast_user`):
1. Chọn mô hình theo số ngày lịch sử của hũ (`models.select_model`): dưới `cold_start_min_days` thì khởi đầu lạnh
   (luật + trung bình nhóm), từ ngưỡng thì hurdle theo lịch.
2. Fit mô hình thành một phân phối biên theo ngày (`marginals`).
3. ACI (backtest nội bộ rolling-origin) cho alpha_t theo nhóm horizon; phân vị chi tiêu NGÀY P10/P50/P90 ghi ra là
   phân vị của biên tại các mức (alpha_t / 2, 0,5, 1 - alpha_t / 2).
4. Monte Carlo số dư (`montecarlo`) với tham số hiệu chỉnh của loại chuỗi (`calibration`): phân vị số dư P10/P50/P90 theo ngày,
   ngày cạn, xác suất hụt trước kỳ lương và sai số chuẩn.
5. Cổng chất lượng: nhãn tin cậy, trạng thái đủ/sát/hụt, có phát xác suất hay không.

`update_forecast` chạy lại riêng bước 4-5 cho vài hũ, trên biên đã ghi ở `previous.run.params["jar_state"]` (fit và ACI giữ
nguyên). Nếu `previous` không có trạng thái (ví dụ dựng lại từ bảng `forecasts` mà thiếu `params`) thì rơi về dựng biên từ
ba phân vị chi tiêu ngày P10/P50/P90 đã có (kém chính xác hơn, nhất là với hũ thưa).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np

from yofina_ml.aci import interval_levels, run_aci
from yofina_ml.calibration import (
    Calibration,
    SeriesCalibration,
    calibration_from_dict,
    resolve_calibration,
)
from yofina_ml.daycal import DayFeatures, date_range_features
from yofina_ml.marginals import (
    Marginal,
    interp_table,
    marginal_from_state,
)
from yofina_ml.models import COLD_START, HURDLE, MODEL_VERSION, select_model
from yofina_ml.montecarlo import SimSpec, jar_seed_sequence, simulate_jar
from yofina_ml.params import MLParams
from yofina_ml.quality import (
    COVERAGE_FORMULA,
    band_for,
    data_coverage,
    min_band,
    status_for,
)
from yofina_ml.types import (
    ConfidenceBand,
    DayQuantiles,
    ForecastConfig,
    ForecastInputs,
    ForecastResult,
    JarForecast,
    JarInput,
    JarSummary,
    RunMeta,
    SeriesKind,
)


# =====================================================================================
# Ngữ cảnh chạy (tính một lần cho cả người dùng)
# =====================================================================================
@dataclass(frozen=True)
class _Ctx:
    inputs: ForecastInputs
    cfg: ForecastConfig
    prm: MLParams
    cal: Calibration
    n_paths: int
    payday_day: int
    horizon: int
    window: int  # số ngày "trước kỳ lương" dùng cho p_shortfall
    history_days: int
    is_initial: bool
    coverage: float | None
    run_label: ConfidenceBand
    f_fut: DayFeatures


def _make_ctx(inputs: ForecastInputs, cal: Calibration | None = None) -> _Ctx:
    cfg = inputs.config
    prm = MLParams.from_extra(cfg.extra)
    cal = cal or resolve_calibration(cfg)
    payday_day = inputs.payday_day if inputs.payday_day is not None else inputs.next_payday.day
    horizon = inputs.horizon_days
    days_to_payday = (inputs.next_payday - inputs.app_date).days
    history_days = max((j.history_days for j in inputs.jars), default=0)
    is_initial = history_days < cfg.cold_start_min_days
    coverage = data_coverage(inputs.coverage)
    run_label: ConfidenceBand = (
        "low"
        if is_initial
        else band_for(history_days, coverage, cal.dense.probability_ok_at(history_days), cfg, prm)
    )
    return _Ctx(
        inputs=inputs,
        cfg=cfg,
        prm=prm,
        cal=cal,
        n_paths=max(int(cfg.n_paths), prm.min_paths),
        payday_day=payday_day,
        horizon=horizon,
        window=max(0, min(days_to_payday - 1, horizon)),
        history_days=history_days,
        is_initial=is_initial,
        coverage=coverage,
        run_label=run_label,
        f_fut=date_range_features(
            inputs.app_date + timedelta(days=1), horizon, payday_day, prm.early_days
        ),
    )


def _flows(jar: JarInput, app_date: date, horizon: int):
    inflow = np.zeros(horizon)
    outflow = np.zeros(horizon)
    ranged: list[tuple[int, float, float]] = []
    for fl in jar.inflows:
        idx = (fl.date - app_date).days - 1
        if 0 <= idx < horizon:
            inflow[idx] += fl.amount_vnd
    for fl in jar.outflows:
        idx = (fl.date - app_date).days - 1
        if not 0 <= idx < horizon:
            continue
        lo, hi = fl.amount_min_vnd, fl.amount_max_vnd
        if lo is not None and hi is not None and hi > lo:
            ranged.append((idx, float(lo), float(hi)))
        else:
            outflow[idx] += fl.amount_vnd
    return inflow, outflow, tuple(ranged)


def _spend_quantiles(marg: Marginal, alpha: np.ndarray, ctx: _Ctx) -> np.ndarray:
    """Phân vị chi tiêu ngày (3, H) VND nguyên: hai đầu khoảng theo alpha_t của ACI, giữa là trung vị."""
    h = ctx.horizon
    a = interval_levels(alpha, h, ctx.prm.aci_bins)
    lo = marg.ppf((a / 2.0)[None, :], ctx.f_fut)[0]
    med = marg.ppf(np.full((1, h), 0.5), ctx.f_fut)[0]
    hi = marg.ppf((1.0 - a / 2.0)[None, :], ctx.f_fut)[0]
    q = np.rint(np.maximum(np.stack([lo, med, hi]), 0.0))
    return np.maximum.accumulate(q, axis=0).astype(np.int64)


def _series_kind(y: np.ndarray, ctx: _Ctx) -> SeriesKind:
    if len(y) < ctx.cfg.cold_start_min_days:
        return "cold_start"
    w = y[-ctx.prm.fit_window_days :]
    zero_share = 1.0 - float(np.mean(w > 0)) if len(w) else 1.0
    return "sparse" if zero_share > ctx.prm.sparse_zero_share else "dense"


def _jar_result(
    jar: JarInput,
    marg: Marginal,
    alpha: np.ndarray,
    kind: SeriesKind,
    ctx: _Ctx,
) -> JarForecast:
    inputs = ctx.inputs
    inflow, outflow, ranged = _flows(jar, inputs.app_date, ctx.horizon)
    cal_kind: SeriesCalibration = ctx.cal.for_kind(kind)
    spec = SimSpec(
        balance_vnd=float(jar.balance_vnd),
        marginal=marg,
        feats=ctx.f_fut,
        sparse=kind == "sparse",
        inflow=inflow,
        outflow=outflow,
        ranged=ranged,
        window=ctx.window,
    )
    ss = jar_seed_sequence(ctx.cfg.seed, inputs.app_date, jar.code)
    sim = simulate_jar(spec, cal_kind, ctx.n_paths, ss, float(ctx.prm.runout_balance_threshold_vnd))
    sq = _spend_quantiles(marg, alpha, ctx)
    days = tuple(
        DayQuantiles(
            date=inputs.app_date + timedelta(days=i + 1),
            spend_p10_vnd=int(sq[0, i]),
            spend_p50_vnd=int(sq[1, i]),
            spend_p90_vnd=int(sq[2, i]),
            balance_p10_vnd=int(sim.balance_p10[i]),
            balance_p50_vnd=int(sim.balance_p50[i]),
            balance_p90_vnd=int(sim.balance_p90[i]),
        )
        for i in range(ctx.horizon)
    )
    p_pub = round(float(sim.p_shortfall), 4)
    # BR-31: % chỉ hiện khi khoảng của loại chuỗi này đã đạt độ phủ mục tiêu ở ĐỘ DÀI LỊCH SỬ của hũ
    calibrated = cal_kind.probability_ok_at(jar.history_days)
    show = (
        ctx.cfg.probability_enabled
        and not ctx.is_initial
        and kind != "cold_start"
        and calibrated
    )
    band: ConfidenceBand = (
        "low"
        if kind == "cold_start"
        else min_band(
            ctx.run_label,
            band_for(jar.history_days, ctx.coverage, calibrated, ctx.cfg, ctx.prm),
        )
    )
    summary = JarSummary(
        jar_code=jar.code,
        start_balance_vnd=jar.balance_vnd,
        payday_date=inputs.next_payday,
        days_to_payday=(inputs.next_payday - inputs.app_date).days,
        runout_date=(
            inputs.app_date + timedelta(days=sim.runout_index + 1)
            if sim.runout_index is not None
            else None
        ),
        p_shortfall=p_pub if show else None,
        p_shortfall_se=round(float(sim.p_shortfall_se), 5) if show else None,
        status=status_for(p_pub, ctx.cfg),
        confidence_band=band,
        show_probability=show,
        series_kind=kind,
    )
    return JarForecast(summary=summary, days=days)


def _jar_state(model: str, kind: SeriesKind, marg: Marginal, alpha: np.ndarray) -> dict[str, Any]:
    return {
        "model": model,
        "series_kind": kind,
        "aci_alpha": [round(float(a), 6) for a in alpha],
        "marginal": marg.state(),
    }


def _run_meta(ctx: _Ctx, model: str, params: dict[str, Any]) -> RunMeta:
    cfg = ctx.cfg
    return RunMeta(
        model=model,
        model_version=MODEL_VERSION,
        app_date=ctx.inputs.app_date,
        horizon_days=ctx.horizon,
        history_days=ctx.history_days,
        data_coverage=ctx.coverage,
        confidence_label="low" if ctx.is_initial else ctx.run_label,
        is_initial_estimate=ctx.is_initial,
        n_paths=ctx.n_paths,
        seed=cfg.seed,
        params=params,
    )


def _base_params(ctx: _Ctx) -> dict[str, Any]:
    cfg = ctx.cfg
    return {
        "ml_version": MODEL_VERSION,
        "calibration": ctx.cal.to_dict(),
        "aci_gamma": float(cfg.aci_gamma),
        "aci_alpha_target": round(1.0 - float(cfg.coverage_target), 6),
        "payday_day": ctx.payday_day,
        "data_coverage_formula": COVERAGE_FORMULA,
        "probability_window_days": ctx.window,
    }


# =====================================================================================
# forecast_user
# =====================================================================================
@dataclass(frozen=True)
class JarFit:
    """Kết quả bước 1-3 cho một hũ: mô hình, loại chuỗi, phân phối biên và alpha_t của ACI."""

    model: str
    kind: SeriesKind
    marginal: Marginal
    alpha: np.ndarray


def fit_jar(jar: JarInput, ctx: _Ctx) -> JarFit:
    """Chọn mô hình, fit biên, chạy ACI (không Monte Carlo). Tách riêng để backtest dùng lại."""
    cfg, prm = ctx.cfg, ctx.prm
    y = np.asarray(jar.daily_spend_vnd, dtype=float)
    kind = _series_kind(y, ctx)
    budget = next((float(f.amount_vnd) for f in jar.inflows), float(max(jar.balance_vnd, 0)))
    model = select_model(
        len(y),
        cold_start_min_days=cfg.cold_start_min_days,
        params=prm,
        payday_day=ctx.payday_day,
        kind=jar.kind,
        monthly_budget_vnd=budget,
        override=cfg.extra.get("model"),
    )
    f_hist = date_range_features(jar.history_start, len(y), ctx.payday_day, prm.early_days)
    marg = model.fit(y, f_hist)
    alpha_target = 1.0 - float(cfg.coverage_target)
    alpha = np.full(len(prm.aci_bins) + 1, alpha_target)
    if kind != "cold_start":
        alpha = run_aci(y, f_hist, model.fit, prm, float(cfg.aci_gamma), alpha_target)
    return JarFit(model.name, kind, marg, alpha)


def make_context(inputs: ForecastInputs, cal: Calibration | None = None) -> _Ctx:
    return _make_ctx(inputs, cal)


def forecast_user(inputs: ForecastInputs) -> ForecastResult:
    ctx = _make_ctx(inputs)
    out: list[JarForecast] = []
    states: dict[str, Any] = {}
    models_used: list[str] = []
    for jar in inputs.jars:
        fit = fit_jar(jar, ctx)
        out.append(_jar_result(jar, fit.marginal, fit.alpha, fit.kind, ctx))
        states[jar.code] = _jar_state(fit.model, fit.kind, fit.marginal, fit.alpha)
        models_used.append(fit.model)
    counts = Counter(m for m in models_used if m != COLD_START)
    if ctx.is_initial or not counts:
        run_model = COLD_START
    else:
        run_model = counts.most_common(1)[0][0] or HURDLE
    params = _base_params(ctx)
    params["jar_models"] = {j.code: m for j, m in zip(inputs.jars, models_used, strict=True)}
    params["jar_state"] = states
    return ForecastResult(run=_run_meta(ctx, run_model, params), jars=tuple(out))


# =====================================================================================
# update_forecast
# =====================================================================================
class _FixedTableMarginal:
    """Biên dựng từ ba phân vị chi tiêu ngày đã có (đường dự phòng khi `previous` không có trạng thái)."""

    name = "fixed_table"
    _LEVELS = np.array([0.1, 0.5, 0.9])

    def __init__(self, table: np.ndarray) -> None:
        self.table = table  # (H, 3)

    def ppf(self, u: np.ndarray, f: DayFeatures, p: np.ndarray | None = None) -> np.ndarray:
        return interp_table(u, self.table, self._LEVELS)

    def state(
        self,
    ) -> dict[str, Any]:  # không ghi lại: lần chỉnh kế tiếp sẽ đọc lại từ phân vị chi tiêu
        return {}


def _table_from_previous(prev: JarForecast, ctx: _Ctx) -> np.ndarray:
    """Ba phân vị chi tiêu ngày cho horizon mới: ngày có trong `previous` lấy nguyên; ngày chưa có lấy ngày cùng thứ
    gần nhất đã có (không có thì lấy ngày cuối)."""
    by_date = {d.date: (d.spend_p10_vnd, d.spend_p50_vnd, d.spend_p90_vnd) for d in prev.days}
    keys = sorted(by_date)
    rows = []
    for i in range(ctx.horizon):
        d = ctx.inputs.app_date + timedelta(days=i + 1)
        if d in by_date:
            rows.append(by_date[d])
            continue
        same_weekday = [k for k in keys if (k - d).days % 7 == 0]
        rows.append(by_date[max(same_weekday) if same_weekday else keys[-1]])
    return np.array(rows, dtype=float)


def update_forecast(
    inputs: ForecastInputs, previous: ForecastResult, jar_codes: Sequence[str]
) -> ForecastResult:
    prev_by = {jf.summary.jar_code: jf for jf in previous.jars}
    jars_by = {j.code: j for j in inputs.jars}
    for code in jar_codes:
        if code not in prev_by:
            raise KeyError(f"hũ {code} không có trong previous")
        if code not in jars_by:
            raise KeyError(f"hũ {code} không có trong inputs")
    prev_params = previous.run.params or {}
    cal = (
        calibration_from_dict(prev_params["calibration"]) if "calibration" in prev_params else None
    )
    ctx = _make_ctx(inputs, cal)
    prev_states = prev_params.get("jar_state", {}) or {}
    out: list[JarForecast] = []
    states: dict[str, Any] = {}
    for code in jar_codes:
        jar = jars_by[code]
        st = prev_states.get(code)
        if st and st.get("marginal"):
            marg = marginal_from_state(st["marginal"])
            alpha = np.array(st["aci_alpha"], dtype=float)
            kind: SeriesKind = st["series_kind"]
            model = st["model"]
            states[code] = _jar_state(model, kind, marg, alpha)
        else:
            marg = _FixedTableMarginal(_table_from_previous(prev_by[code], ctx))
            alpha = np.full(len(ctx.prm.aci_bins) + 1, 1.0 - float(ctx.cfg.coverage_target))
            kind = prev_by[code].summary.series_kind
        out.append(_jar_result(jar, marg, alpha, kind, ctx))
    params = _base_params(ctx)
    params["jar_state"] = states
    params["updated_from_model"] = previous.run.model
    return ForecastResult(run=_run_meta(ctx, previous.run.model, params), jars=tuple(out))
