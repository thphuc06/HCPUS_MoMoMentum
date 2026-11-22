"""Lõi pipeline dự báo: `Pipeline.run_user` cho MỘT người dùng, dùng chung cho batch đêm, đường sự kiện, đặt lại demo và tool.

Hai đường tính:

- **Đầy đủ** (`forecast_user`): fit lại mô hình và ACI cho mọi hũ, Monte Carlo `n_paths_full` đường. Dùng cho batch đêm, đặt lại, đọc
  khi dự báo cũ, và mọi lúc đường nhanh không dùng được.
- **Nhanh** (`update_forecast`, chỉ cho `trigger = event` kèm danh sách hũ): chạy lại Monte Carlo `n_paths_fast` đường cho vài hũ
  trên phân phối chi tiêu ngày ĐÃ fit của lần chạy trước (đọc lại từ `forecast_runs.params.jar_state`) với số dư mới. Điều kiện
  dùng đường nhanh (`_fast_previous`): mọi hũ đều đã có dự báo, cùng ngày mô phỏng, đủ trẻ (`fast_max_age_seconds`), cùng trạng
  thái ước lượng ban đầu (đã vượt ngưỡng khởi đầu lạnh thì phải fit lại: `ml/README.md`), và `params` còn phân phối của hũ.

Kết quả luôn qua `contract.check_result` TRƯỚC khi ghi; ghi ba bảng trong một transaction; phát `forecast.updated` sau commit.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from yofina_core.errors import ErrorCode, YofinaError
from yofina_forecast.events import ForecastEventPublisher, emf
from yofina_forecast.inputs import Built, Context, build_inputs
from yofina_forecast.repo import ForecastRepo, to_date
from yofina_forecast.settings import ForecastSettings
from yofina_ml.api import forecast_user, update_forecast
from yofina_ml.contract import check_result
from yofina_ml.types import ForecastInputs, ForecastResult, JarForecast, JarSummary, RunMeta

log = logging.getLogger("yofina.forecast.runner")

TRIGGERS = ("nightly", "event", "manual", "reset", "read")


@dataclass
class RunOutcome:
    """Kết quả một lần gọi `run_user` (gửi ra ngoài dạng JSON qua `to_dict`)."""

    user_id: str
    trigger: str
    status: str  # ok | skipped
    mode: str | None = None  # full | fast
    run_id: str | None = None
    jar_codes: list[str] = field(default_factory=list)
    app_date: str | None = None
    computed_at: str | None = None
    reason: str | None = None
    fast_fallback: str | None = None  # lý do đường nhanh không dùng được (khi đã rơi về đầy đủ)
    is_initial_estimate: bool | None = None
    history_days: int | None = None
    timings_ms: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in (None, [], {})}


class Pipeline:
    """`forecast_fn`/`update_fn` thay được bằng bản giả trong unit test; mã sản phẩm dùng `yofina_ml.api`."""

    def __init__(
        self,
        repo: ForecastRepo,
        settings: ForecastSettings,
        publisher: ForecastEventPublisher | None = None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        forecast_fn: Callable[[ForecastInputs], ForecastResult] = forecast_user,
        update_fn: Callable[
            [ForecastInputs, ForecastResult, Sequence[str]], ForecastResult
        ] = update_forecast,
    ) -> None:
        self.repo = repo
        self.settings = settings
        self.publisher = publisher
        self._clock = clock
        self._forecast = forecast_fn
        self._update = update_fn

    # --- tiện ích -------------------------------------------------------------------------------
    def now(self) -> datetime:
        return self._clock()

    def load_context(self, user_id: str, now: datetime) -> Context:
        rows = self.repo.context(
            user_id, now, self.settings.app_timezone, self.settings.history_window_days
        )
        ctx = Context.from_rows(rows)
        if ctx is None:
            raise YofinaError(ErrorCode.PROFILE_INCOMPLETE, "Người dùng chưa có hồ sơ.")
        return ctx

    # --- điểm vào -------------------------------------------------------------------------------
    def run_user(
        self,
        user_id: str,
        *,
        trigger: str,
        jar_codes: Sequence[str] | None = None,
        source_event_id: str | None = None,
        force_full: bool = False,
        trace_id: str | None = None,
    ) -> RunOutcome:
        """Tính và ghi dự báo của một người dùng.

        `jar_codes` chỉ có nghĩa với `trigger = event` (đường nhanh). `trigger = read` bị bỏ qua nếu vừa có lần chạy trẻ hơn
        `recompute_guard_seconds` cùng ngày mô phỏng (nhiều lượt đọc cùng lúc không gây bão tính lại).
        """
        if trigger not in TRIGGERS:
            raise ValueError(f"trigger không hợp lệ: {trigger}")
        started = time.perf_counter()
        t: dict[str, float] = {}
        now = self.now()

        if trigger == "read":
            fresh = self._fresh_run(user_id, now)
            if fresh is not None:
                return RunOutcome(user_id, trigger, "skipped", reason="fresh", **fresh)

        ctx = self.load_context(user_id, now)
        t["context"] = _ms(started)

        mode, fallback, previous = "full", None, None
        built: Built
        if trigger == "event" and jar_codes and not force_full:
            built = build_inputs(ctx, self.settings, user_id, n_paths=self.settings.n_paths_fast)
            targets = [c for c in dict.fromkeys(jar_codes) if c in built.jar_codes]
            if not targets:
                return RunOutcome(
                    user_id,
                    trigger,
                    "skipped",
                    reason="no_forecastable_jar",
                    app_date=ctx.app_date.isoformat(),
                )
            previous, fallback = self._fast_previous(user_id, built.inputs, targets, now)
            if previous is not None:
                mode = "fast"
        if mode == "full":
            built = build_inputs(ctx, self.settings, user_id, n_paths=self.settings.n_paths_full)
            targets = list(built.jar_codes)
        t["inputs"] = _ms(started)

        parent_run_id: str | None = None
        if mode == "fast":
            assert previous is not None
            prev_result, parent_run_id = previous
            result = self._update(built.inputs, prev_result, targets)
            errors = check_result(built.inputs, result, subset=True)
        else:
            result = self._forecast(built.inputs)
            errors = check_result(built.inputs, result)
        if errors:
            raise YofinaError(
                ErrorCode.INTERNAL_ERROR,
                "Kết quả dự báo sai hợp đồng: " + "; ".join(errors[:3]),
            )
        t["compute"] = _ms(started)

        params = dict(result.run.params)
        params["pipeline"] = {
            **built.notes,
            "mode": mode,
            "trigger": trigger,
            "jar_codes": [jf.summary.jar_code for jf in result.jars],
            "n_paths": result.run.n_paths,
            **({"fast_fallback": fallback} if fallback else {}),
        }
        computed_at = self.now()
        run_id = self.repo.save(
            user_id,
            result,
            trigger=trigger,
            params=params,
            computed_at=computed_at,
            parent_run_id=parent_run_id,
            source_event_id=source_event_id,
            keep_runs=self.settings.keep_runs,
        )
        t["save"] = _ms(started)
        codes = [jf.summary.jar_code for jf in result.jars]
        if self.publisher is not None:
            self.publisher.forecast_updated(
                user_id=user_id,
                run_id=run_id,
                computed_at=computed_at,
                app_date=result.run.app_date,
                trigger=trigger,
                jar_codes=codes,
                is_initial_estimate=result.run.is_initial_estimate,
                confidence_label=result.run.confidence_label,
                parent_event_id=source_event_id,
                trace_id=trace_id,
            )
        t["publish"] = _ms(started)
        total = _ms(started)
        log.info(
            json.dumps(
                {
                    "msg": "forecast_run",
                    "trigger": trigger,
                    "mode": mode,
                    "jars": len(codes),
                    "run_id": run_id,
                    "ms": total,
                    "stages": t,
                    **({"fast_fallback": fallback} if fallback else {}),
                }
            )
        )
        log.info(emf("ForecastRunMs", total, "Milliseconds", Mode=mode, Trigger=trigger))
        return RunOutcome(
            user_id,
            trigger,
            "ok",
            mode=mode,
            run_id=run_id,
            jar_codes=codes,
            app_date=result.run.app_date.isoformat(),
            computed_at=computed_at.isoformat(),
            fast_fallback=fallback,
            is_initial_estimate=result.run.is_initial_estimate,
            history_days=result.run.history_days,
            timings_ms=t,
        )

    # --- chống bão tính lại ---------------------------------------------------------------------
    def _fresh_run(self, user_id: str, now: datetime) -> dict[str, Any] | None:
        """Có lần chạy trẻ hơn `recompute_guard_seconds` thì trả thông tin của nó, không thì None.

        Chỉ so tuổi (không đọc ngày mô phỏng): ngày mô phỏng đổi chậm (một ngày mỗi ngày thật), nên trong vài giây của khoảng
        bảo vệ, lần chạy vừa xong vẫn cùng ngày."""
        rows = self.repo.summaries(user_id)
        if not rows:
            return None
        latest = max(rows, key=lambda r: (r["computed_at"], str(r["run_id"])))
        if (now - latest["computed_at"]).total_seconds() < self.settings.recompute_guard_seconds:
            return {
                "run_id": str(latest["run_id"]),
                "app_date": to_date(latest["run_app_date"]).isoformat(),  # type: ignore[union-attr]
                "computed_at": latest["computed_at"].isoformat(),
            }
        return None

    # --- đường nhanh ----------------------------------------------------------------------------
    def _fast_previous(
        self, user_id: str, inputs: ForecastInputs, targets: Sequence[str], now: datetime
    ) -> tuple[tuple[ForecastResult, str] | None, str | None]:
        """Dựng `previous` cho `update_forecast` từ lần chạy mới nhất của từng hũ. Trả ((previous, parent_run_id) | None, lý do rơi về)."""
        rows = {r["jar_code"]: r for r in self.repo.summaries(user_id)}
        missing = [c for c in targets if c not in rows]
        if missing:
            return None, "no_previous"
        s = self.settings
        history = max((j.history_days for j in inputs.jars), default=0)
        is_initial = history < inputs.config.cold_start_min_days
        for code in targets:
            r = rows[code]
            if to_date(r["run_app_date"]) != inputs.app_date:
                return None, "app_date_changed"
            if (now - r["computed_at"]).total_seconds() > s.fast_max_age_seconds:
                return None, "previous_too_old"
            if bool(r["is_initial_estimate"]) and not is_initial:
                return None, "left_cold_start"
        # mỗi lần chạy khác nhau đọc một lần (kèm chỉ jar_state của các hũ cần, để dưới 64 KB mỗi dòng)
        by_run: dict[str, list[str]] = {}
        for code in targets:
            by_run.setdefault(str(rows[code]["run_id"]), []).append(code)
        runs: dict[str, Mapping[str, Any]] = {}
        merged_state: dict[str, Any] = {}
        for run_id, codes in by_run.items():
            run = self.repo.run(user_id, run_id, codes)
            if run is None or not isinstance(run.get("params"), dict):
                return None, "no_params"
            state = (run["params"].get("jar_state") or {}) if run["params"] else {}
            for c in codes:
                if not state.get(c) or not state[c].get("marginal"):
                    return None, "no_jar_state"
                merged_state[c] = state[c]
            runs[run_id] = run
        newest_id = max(runs, key=lambda i: (runs[i]["computed_at"], i))
        newest = runs[newest_id]
        params = dict(newest["params"])
        params["jar_state"] = merged_state
        meta = RunMeta(
            model=newest["model"],
            model_version=newest.get("model_version"),
            app_date=to_date(newest["run_app_date"]),  # type: ignore[arg-type]
            horizon_days=int(newest["horizon_days"]),
            history_days=int(newest["history_days"]),
            data_coverage=float(newest["data_coverage"])
            if newest.get("data_coverage") is not None
            else None,
            confidence_label=newest["confidence_label"],
            is_initial_estimate=bool(newest["is_initial_estimate"]),
            n_paths=newest.get("n_paths"),
            seed=newest.get("seed"),
            params=params,
        )
        jars = tuple(
            JarForecast(summary=_summary_of(rows[c]), days=()) for c in targets
        )  # `days` rỗng: chỉ dùng khi thiếu jar_state, mà ở đây đã kiểm đủ
        return (ForecastResult(run=meta, jars=jars), newest_id), None


def _summary_of(r: Mapping[str, Any]) -> JarSummary:
    def f(v: Any) -> float | None:
        return None if v is None else float(v)

    return JarSummary(
        jar_code=r["jar_code"],
        start_balance_vnd=int(r["start_balance_vnd"]),
        payday_date=to_date(r["payday_date"]),  # type: ignore[arg-type]
        days_to_payday=int(r["days_to_payday"]),
        runout_date=to_date(r.get("runout_date")),
        p_shortfall=f(r.get("p_shortfall")),
        p_shortfall_se=f(r.get("p_shortfall_se")),
        status=r["status"],
        confidence_band=r["confidence_band"],
        show_probability=bool(r["show_probability"]),
        series_kind=r["series_kind"],
    )


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
