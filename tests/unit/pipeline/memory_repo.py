"""Kho trong bộ nhớ thay `ForecastRepo` trong test: lưu kết quả `save`, trả lại đúng hình dạng hàng mà các hàm DB trả
(`app_get_forecast_summaries`, `app_get_forecast_run`), để chạy được cả đường nhanh (đọc lại `params`) mà không cần Aurora."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from pipeline_helpers import NOW

from yofina_ml.types import ForecastResult


class MemoryRepo:
    def __init__(self, context_rows: list[dict[str, Any]]) -> None:
        self.context_rows = context_rows
        self.runs: list[dict[str, Any]] = []
        self.saves = 0
        self.context_calls = 0
        self.tick = NOW
        self.fail_save = False

    # --- đọc ---
    def context(self, user_id, now, tz, window_days):
        self.context_calls += 1
        return self.context_rows

    def summaries(self, user_id, jar=None):
        latest: dict[str, dict[str, Any]] = {}
        for run in self.runs:  # theo thứ tự thêm = theo computed_at tăng dần
            for jf in run["result"].jars:
                s = jf.summary
                if jar and s.jar_code != jar:
                    continue
                latest[s.jar_code] = {
                    "jar_code": s.jar_code,
                    "run_id": run["id"],
                    "computed_at": run["computed_at"],
                    "run_app_date": run["result"].run.app_date,
                    "model": run["result"].run.model,
                    "is_initial_estimate": run["result"].run.is_initial_estimate,
                    "start_balance_vnd": s.start_balance_vnd,
                    "payday_date": s.payday_date,
                    "days_to_payday": s.days_to_payday,
                    "runout_date": s.runout_date,
                    "p_shortfall": s.p_shortfall,
                    "p_shortfall_se": s.p_shortfall_se,
                    "status": s.status,
                    "confidence_band": s.confidence_band,
                    "show_probability": s.show_probability,
                    "series_kind": s.series_kind,
                }
        return list(latest.values())

    def run(self, user_id, run_id, jar_codes=None):
        for r in self.runs:
            if r["id"] == run_id:
                res = r["result"]
                params = json.loads(json.dumps(r["params"]))  # như qua jsonb
                if jar_codes is not None:
                    params["jar_state"] = {
                        k: v for k, v in params.get("jar_state", {}).items() if k in jar_codes
                    }
                return {
                    "run_id": run_id,
                    "model": res.run.model,
                    "model_version": res.run.model_version,
                    "computed_at": r["computed_at"],
                    "run_app_date": res.run.app_date,
                    "horizon_days": res.run.horizon_days,
                    "history_days": res.run.history_days,
                    "data_coverage": res.run.data_coverage,
                    "confidence_label": res.run.confidence_label,
                    "is_initial_estimate": res.run.is_initial_estimate,
                    "n_paths": res.run.n_paths,
                    "seed": res.run.seed,
                    "params": params,
                }
        return None

    def users(self, limit):
        return ["u1", "u2"][:limit]

    # --- ghi ---
    def save(
        self,
        user_id: str,
        result: ForecastResult,
        *,
        trigger: str,
        params: dict[str, Any],
        computed_at: datetime,
        parent_run_id: str | None = None,
        source_event_id: str | None = None,
        keep_runs: int = 6,
    ) -> str:
        if self.fail_save:
            raise RuntimeError("ghi lỗi")
        self.saves += 1
        self.tick = computed_at
        run = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "result": result,
            "params": params,
            "trigger": trigger,
            "parent": parent_run_id,
            "source_event_id": source_event_id,
            "computed_at": computed_at,
        }
        self.runs.append(run)
        return run["id"]
