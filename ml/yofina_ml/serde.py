"""Chuyển qua lại giữa kiểu dữ liệu của `yofina_ml.types` và dạng JSON của `contracts/ml/forecast_io.schema.json`.

Chỉ là phép chuyển đổi (ngày <-> chuỗi YYYY-MM-DD, tuple <-> mảng), không có logic dự báo. Dùng ở test, lưu vết đầu vào
của một lần chạy và khi gọi qua ranh giới tiến trình. Phía đọc nghiêm: thiếu trường bắt buộc thì `KeyError`.
"""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import date
from typing import Any

from yofina_ml.types import (
    CoverageInputs,
    DayQuantiles,
    ForecastConfig,
    ForecastInputs,
    ForecastResult,
    JarForecast,
    JarInput,
    JarSummary,
    RunMeta,
    ScheduledFlow,
)


def _d(value: str) -> date:
    return date.fromisoformat(value)


def _flow_from(o: dict[str, Any]) -> ScheduledFlow:
    return ScheduledFlow(
        date=_d(o["date"]), kind=o["kind"], label=o["label"], amount_vnd=o["amount_vnd"],
        amount_min_vnd=o.get("amount_min_vnd"), amount_max_vnd=o.get("amount_max_vnd"),
        ref_id=o.get("ref_id"),
        original_due_date=_d(o["original_due_date"]) if o.get("original_due_date") else None,
    )  # fmt: skip


def _flow_to(f: ScheduledFlow) -> dict[str, Any]:
    out: dict[str, Any] = {
        "date": f.date.isoformat(),
        "kind": f.kind,
        "label": f.label,
        "amount_vnd": f.amount_vnd,
    }
    for key in ("amount_min_vnd", "amount_max_vnd", "ref_id"):
        if getattr(f, key) is not None:
            out[key] = getattr(f, key)
    if f.original_due_date is not None:
        out["original_due_date"] = f.original_due_date.isoformat()
    return out


def _jar_from(o: dict[str, Any]) -> JarInput:
    return JarInput(
        code=o["code"], kind=o["kind"], balance_vnd=o["balance_vnd"], split_percent=o["split_percent"],
        history_start=_d(o["history_start"]), daily_spend_vnd=tuple(o["daily_spend_vnd"]),
        inflows=tuple(_flow_from(x) for x in o.get("inflows", [])),
        outflows=tuple(_flow_from(x) for x in o.get("outflows", [])), purpose=o.get("purpose"),
    )  # fmt: skip


def _jar_to(j: JarInput) -> dict[str, Any]:
    return {
        "code": j.code, "kind": j.kind, "balance_vnd": j.balance_vnd, "split_percent": j.split_percent,
        "history_start": j.history_start.isoformat(), "daily_spend_vnd": list(j.daily_spend_vnd),
        **({"purpose": j.purpose} if j.purpose is not None else {}),
        "inflows": [_flow_to(f) for f in j.inflows], "outflows": [_flow_to(f) for f in j.outflows],
    }  # fmt: skip


def forecast_config_from_dict(o: dict[str, Any]) -> ForecastConfig:
    known = {f.name for f in fields(ForecastConfig)}
    unknown = set(o) - known
    if unknown:
        raise KeyError(f"ForecastConfig không có trường {sorted(unknown)}")
    return ForecastConfig(**o)


def forecast_inputs_from_dict(o: dict[str, Any]) -> ForecastInputs:
    return ForecastInputs(
        app_date=_d(o["app_date"]), horizon_days=o["horizon_days"], next_payday=_d(o["next_payday"]),
        payday_dates=tuple(_d(x) for x in o["payday_dates"]),
        jars=tuple(_jar_from(x) for x in o["jars"]),
        coverage=CoverageInputs(**o["coverage"]) if o.get("coverage") else None,
        config=forecast_config_from_dict(o["config"]) if "config" in o else ForecastConfig(),
        payday_day=o.get("payday_day"),
    )  # fmt: skip


def forecast_inputs_to_dict(i: ForecastInputs) -> dict[str, Any]:
    out: dict[str, Any] = {
        "app_date": i.app_date.isoformat(), "horizon_days": i.horizon_days,
        "next_payday": i.next_payday.isoformat(), "payday_dates": [d.isoformat() for d in i.payday_dates],
        "jars": [_jar_to(j) for j in i.jars],
        "config": {k: v for k, v in asdict(i.config).items() if v is not None},
    }  # fmt: skip
    if i.coverage is not None:
        out["coverage"] = asdict(i.coverage)
    if i.payday_day is not None:
        out["payday_day"] = i.payday_day
    return out


def _summary_from(o: dict[str, Any]) -> JarSummary:
    return JarSummary(
        jar_code=o["jar_code"], start_balance_vnd=o["start_balance_vnd"], payday_date=_d(o["payday_date"]),
        days_to_payday=o["days_to_payday"], runout_date=_d(o["runout_date"]) if o.get("runout_date") else None,
        p_shortfall=o.get("p_shortfall"), p_shortfall_se=o.get("p_shortfall_se"), status=o["status"],
        confidence_band=o["confidence_band"], show_probability=o["show_probability"], series_kind=o["series_kind"],
    )  # fmt: skip


def _summary_to(s: JarSummary) -> dict[str, Any]:
    out: dict[str, Any] = {
        "jar_code": s.jar_code, "start_balance_vnd": s.start_balance_vnd, "payday_date": s.payday_date.isoformat(),
        "days_to_payday": s.days_to_payday, "status": s.status, "confidence_band": s.confidence_band,
        "show_probability": s.show_probability, "series_kind": s.series_kind,
    }  # fmt: skip
    if s.runout_date is not None:
        out["runout_date"] = s.runout_date.isoformat()
    if s.p_shortfall is not None:
        out["p_shortfall"] = s.p_shortfall
    if s.p_shortfall_se is not None:
        out["p_shortfall_se"] = s.p_shortfall_se
    return out


def _day_from(o: dict[str, Any]) -> DayQuantiles:
    return DayQuantiles(date=_d(o["date"]), **{k: o[k] for k in o if k != "date"})


def _day_to(d: DayQuantiles) -> dict[str, Any]:
    out = asdict(d)
    out["date"] = d.date.isoformat()
    return out


def forecast_result_from_dict(o: dict[str, Any]) -> ForecastResult:
    r = o["run"]
    run = RunMeta(
        model=r["model"], model_version=r.get("model_version"), app_date=_d(r["app_date"]),
        horizon_days=r["horizon_days"], history_days=r["history_days"], data_coverage=r.get("data_coverage"),
        confidence_label=r["confidence_label"], is_initial_estimate=r["is_initial_estimate"],
        n_paths=r.get("n_paths"), seed=r.get("seed"), params=dict(r.get("params", {})),
    )  # fmt: skip
    jars = tuple(
        JarForecast(
            summary=_summary_from(j["summary"]), days=tuple(_day_from(d) for d in j["days"])
        )
        for j in o["jars"]
    )
    return ForecastResult(run=run, jars=jars)


def forecast_result_to_dict(res: ForecastResult) -> dict[str, Any]:
    r = res.run
    run: dict[str, Any] = {
        "model": r.model, "app_date": r.app_date.isoformat(), "horizon_days": r.horizon_days,
        "history_days": r.history_days, "confidence_label": r.confidence_label,
        "is_initial_estimate": r.is_initial_estimate, "params": dict(r.params),
    }  # fmt: skip
    for key in ("model_version", "data_coverage", "n_paths", "seed"):
        if getattr(r, key) is not None:
            run[key] = getattr(r, key)
    return {
        "run": run,
        "jars": [
            {"summary": _summary_to(j.summary), "days": [_day_to(d) for d in j.days]}
            for j in res.jars
        ],
    }
