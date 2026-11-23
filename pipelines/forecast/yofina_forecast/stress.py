"""`forecast___stress_test` và `POST /resilience/stress` (phase 4, F4): áp MỘT cú sốc mẫu lên dự báo của người dùng.

Chỉ nhận `shock_id` (ba mã trong `yofina_core/shocks.json`); không số nào của cú sốc đến từ model hay từ người gọi. Cách làm (chi tiết
và công thức ở `yofina_ml.stress`):

1. Đọc dữ liệu như `resilience.py` (một lượt) rồi chấm điểm TRƯỚC bằng đúng công thức của màn "Nhìn trước".
2. Dựng `ForecastInputs` cho khoảng `stress.horizon_days` của cấu hình, rồi áp cú sốc vào lịch lương, lịch nghĩa vụ và khoản chi
   một lần (hũ Dự phòng trả khoản chi một lần).
3. Monte Carlo số dư TỔNG của nền và của kịch bản sốc trên CÙNG dãy số ngẫu nhiên (phân phối chi tiêu đã fit của lần dự báo gần
   nhất; chưa có hoặc đã cũ thì chạy dự báo đầy đủ một lần, như `run_scenario`).
4. Chấm điểm SAU trên đầu vào đã áp cú sốc; số ngày trụ được, khoản thiếu và trạng thái từ mô phỏng.

Không ghi gì vào DB. Kết quả `{status, as_of, app_date, data}` với `data` là `StressResultData`.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import timedelta
from typing import Any

from yofina_core.blocks import RESILIENCE_ORDER, ForecastJar, StressResultData, format_instant
from yofina_core.errors import ErrorCode, ToolStatus, YofinaError
from yofina_core.money import format_vnd
from yofina_core.resilience import (
    ShockDefinition,
    load_resilience_config,
    load_shock_set,
)
from yofina_forecast.inputs import build_inputs
from yofina_forecast.resilience import Gathered, ResilienceEngine, score_of
from yofina_forecast.runner import Pipeline
from yofina_ml.params import MLParams
from yofina_ml.resilience import BAND_WORD
from yofina_ml.stress import (
    shock_forecast_inputs,
    shock_score_inputs,
    simulate_stress,
    summarize_stress,
)

log = logging.getLogger("yofina.forecast.stress")

#: nhãn của khoản chi một lần mà cú sốc thêm vào lịch (hiện trong sự kiện mô phỏng, không phải số liệu)
EXTRA_COST_LABEL = "Chi phí phát sinh do cú sốc"
MAX_HORIZON_DAYS = 90  # giới hạn của hợp đồng ML (`check_inputs`)


def find_shock(shock_id: Any) -> ShockDefinition:
    shocks = load_shock_set()
    if not isinstance(shock_id, str) or not shock_id:
        raise YofinaError(ErrorCode.PARAMS_INVALID, "Thiếu shock_id.")
    shock = shocks.get(shock_id)
    if shock is None:
        names = ", ".join(f"{s.shock_id} ({s.label.lower()})" for s in shocks.shocks)
        raise YofinaError(
            ErrorCode.SHOCK_NOT_FOUND, f"Không có cú sốc này. Chọn một trong: {names}."
        )
    return shock


def list_shocks() -> dict[str, Any]:
    """Dữ liệu của `GET /resilience/shocks` (`ListShocksData`): ba cú sốc đọc từ `shocks.json`, không cần dữ liệu người dùng."""
    return {
        "shocks": [
            s.summary().model_dump(mode="json", exclude_none=True) for s in load_shock_set().shocks
        ]
    }


class StressEngine:
    def __init__(self, pipeline: Pipeline, resilience: ResilienceEngine | None = None) -> None:
        self.pipeline = pipeline
        self.resilience = resilience or ResilienceEngine(pipeline)
        self.config = load_resilience_config()

    # ----------------------------------------------------------------------------------------------
    def _previous(self, user_id: str, inputs: Any, jar_codes: Any):  # type: ignore[no-untyped-def]
        now = self.pipeline.now()
        prev, _reason, _rows = self.pipeline.previous_state(user_id, inputs, jar_codes, now)
        if prev is None:  # chưa có nền hoặc quá cũ: tính đầy đủ một lần rồi thử lại
            self.pipeline.run_user(user_id, trigger="manual")
            prev, _reason, _rows = self.pipeline.previous_state(
                user_id, inputs, jar_codes, self.pipeline.now()
            )
        if prev is None:
            raise YofinaError(
                ErrorCode.FORECAST_UNAVAILABLE,
                "Chưa có nền dự báo để chạy cú sốc, thử lại sau ít phút.",
            )
        return prev[0]

    def run(self, user_id: str, shock_id: Any) -> dict[str, Any]:
        shock = find_shock(shock_id)
        now = self.pipeline.now()
        g = self.resilience.gather(user_id, now)
        data = self.compute(user_id, g, shock)
        return {
            "status": str(ToolStatus.OK),
            "as_of": format_instant(now),
            "app_date": g.app_date.isoformat(),
            "data": data.model_dump(mode="json", exclude_none=True),
        }

    def compute(self, user_id: str, g: Gathered, shock: ShockDefinition) -> StressResultData:
        cfg = self.config
        s = self.pipeline.settings
        horizon = int(cfg.stress.horizon_days.value)
        n_paths = int(cfg.stress.n_paths.value)
        if not 1 <= horizon <= MAX_HORIZON_DAYS:
            raise YofinaError(
                ErrorCode.INTERNAL_ERROR, "Cấu hình stress.horizon_days ngoài khoảng 1..90."
            )
        duration = shock.params.duration_days or horizon
        if duration > horizon:
            raise YofinaError(
                ErrorCode.INTERNAL_ERROR, "Cú sốc dài hơn khoảng dự báo của cấu hình stress."
            )
        built = build_inputs(g.ctx, replace(s, horizon_days=horizon), user_id, n_paths=n_paths)
        kinds = {str(o["id"]): str(o["kind"]) for o in g.obligations}
        em_code = g.emergency_jar_code if g.emergency_jar_code in built.jar_codes else None
        cost_code = em_code or (
            max(built.inputs.jars, key=lambda j: j.balance_vnd).code if built.inputs.jars else None
        )
        shocked = shock_forecast_inputs(
            built.inputs,
            shock,
            obligation_kinds=kinds,
            cost_jar=cost_code,
            extra_cost_label=EXTRA_COST_LABEL,
            month_days=s.allocation.month_days,
        )
        previous = self._previous(user_id, built.inputs, built.jar_codes)
        sim = simulate_stress(built.inputs, shocked, previous, n_paths=n_paths)

        before = score_of(g.inputs, cfg)
        after = score_of(shock_score_inputs(g.inputs, shock), cfg)
        em_balance = None
        em_ref = None
        if em_code is not None:
            row = next(j for j in g.jar_rows if j["code"] == em_code)
            em_balance = int(row["balance_vnd"])
            em_ref = ForecastJar.model_validate(
                {
                    "code": row["code"],
                    "name": row["name"],
                    "color_key": row["color_key"],
                    "icon_key": row["icon_key"],
                }
            )
        threshold = float(
            MLParams.from_extra(built.inputs.config.extra).runout_balance_threshold_vnd
        )
        outcome = summarize_stress(
            sim,
            duration_days=duration,
            emergency_balance_vnd=em_balance,
            runout_threshold_vnd=threshold,
            short_shortfall_ratio=cfg.stress.short_shortfall_ratio.value,
        )
        score_after = min(after.score, before.score)
        shortfall_from = (
            g.app_date + timedelta(days=outcome.shortfall_index + 1)
            if outcome.shortfall_index is not None
            else None
        )
        payload: dict[str, Any] = {
            "shock": shock.summary().model_dump(mode="json", exclude_none=True),
            "status": outcome.status,
            "headline": self._headline(
                shock, before.score, score_after, after.band, outcome, horizon
            ),
            "score_before": before.score,
            "score_after": score_after,
            "score_delta": score_after - before.score,
            "band_before": before.band,
            "band_after": after.band if score_after == after.score else before.band,
            "runway_days_total": outcome.runway_days_total,
            "runway_days_emergency": outcome.runway_days_emergency,
            "emergency_jar": em_ref.model_dump(mode="json") if em_ref else None,
            "horizon_days": horizon,
            "shortfall_vnd": outcome.shortfall_vnd,
            "shortfall_from": shortfall_from.isoformat() if shortfall_from else None,
            "components": [
                {
                    "key": k,
                    "score_before": before.component(k).score,
                    "score_after": after.component(k).score,
                }
                for k in RESILIENCE_ORDER
            ],
            "method": "monte_carlo",
            "n_paths": sim.n_paths,
            "common_random_numbers": True,
            "basis": g.basis.model_dump(mode="json", exclude_none=True),
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        return StressResultData.model_validate(payload)

    @staticmethod
    def _headline(shock, before: int, after: int, band_after: str, outcome, horizon: int) -> str:  # type: ignore[no-untyped-def]
        if after < before:
            lead = f"{shock.label}: điểm tụt từ {before} xuống {after} ({BAND_WORD[band_after]})"
        else:
            lead = f"{shock.label}: điểm giữ nguyên ở {before} ({BAND_WORD[band_after]})"
        if outcome.runway_days_total is None:
            runway = f"vẫn trụ hết {horizon} ngày"
        else:
            runway = f"trụ được {outcome.runway_days_total} ngày"
        if outcome.shortfall_vnd > 0:
            return f"{lead}, {runway}, thiếu {format_vnd(outcome.shortfall_vnd)}."[:160]
        return f"{lead}, {runway}, không thiếu tiền."[:160]


__all__ = ["StressEngine", "find_shock", "list_shocks"]
