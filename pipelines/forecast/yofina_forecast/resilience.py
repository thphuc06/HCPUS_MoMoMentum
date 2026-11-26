"""Điểm chống chịu phía Lambda forecast (phase 4, F4): đọc dữ liệu người dùng, dựng `ResilienceInputs`, gọi công thức ở
`yofina_ml.resilience`, ghi `resilience_scores`, trả kết quả theo hợp đồng.

Dùng chung cho: tool `forecast___get_resilience_score`, REST `GET /resilience`, và batch đêm (`compute_and_store`, hàm N2 do người điều
phối nối vào sau bước dự báo của `Pipeline.run_user`).

Dữ liệu đọc (một lượt, không mô hình ngôn ngữ):
- ngữ cảnh dự báo (`app_get_forecast_context`): ngày mô phỏng, lương, chi tiêu từng ngày của từng hũ;
- hũ kèm mục tiêu (`app_get_jar_state`), nghĩa vụ đang hoạt động (`app_list_obligations`);
- số khoản nghĩa vụ đã trả trong kỳ (dòng chi gắn `obligation_id`);
- tóm tắt dự báo mới nhất (độ tươi, nhóm tin cậy) cho `basis`; chưa có thì chạy dự báo trước.

Định nghĩa các đầu vào (kỳ là `resilience_window_days`, mặc định 30 ngày):
- thu nhập = lương đã khai (quy về kỳ); số dư khả dụng = tổng số dư các hũ người dùng (không gồm hũ hệ thống);
- chi thay đổi = trung bình chi mỗi ngày trong `window` ngày lịch sử gần nhất x ngày của kỳ (lịch sử chi KHÔNG gồm nghĩa vụ);
- nghĩa vụ = các lần đến hạn trong (hôm nay, hôm nay + kỳ] của mọi nghĩa vụ đang hoạt động (quá hạn tính vào ngày đầu), cùng cách
  tính với `yofina_planner` (luật `obligation_to_income`);
- trả đúng hạn = số khoản đã trả trong kỳ / (số đã trả + số đang quá hạn); không có khoản nào thì 1. Sổ cái không giữ hạn của lần trả
  đã xong nên khoản trả TRỄ rồi mới trả được tính là đúng hạn: giới hạn đã biết;
- mục tiêu: hũ có `goal_vnd` và `goal_date`; mức cần mỗi tháng = phần còn thiếu x ngày của tháng / số ngày còn lại tới hạn; đóng góp
  hiện có = lương x tỷ lệ chia của hũ. Hũ có mục tiêu mà không có hạn thì không tính vào Plan.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from yofina_core.blocks import (
    ForecastBasis,
    ResilienceScoreData,
    format_instant,
)
from yofina_core.clock import app_today
from yofina_core.errors import ErrorCode, ToolStatus, YofinaError
from yofina_core.resilience import ResilienceConfig, band_for_score, load_resilience_config
from yofina_core.schedule import expand_due_dates
from yofina_core.spend_baseline import recent_monthly
from yofina_core.wallet import is_buffer_jar, is_goal_jar
from yofina_forecast.common import int_of, min_band, to_date
from yofina_forecast.inputs import Context
from yofina_forecast.runner import Pipeline
from yofina_ml.resilience import (
    GoalFact,
    ResilienceInputs,
    ResilienceResult,
    compute_score,
    monthly_needed_vnd,
)

log = logging.getLogger("yofina.forecast.resilience")

SOURCES = ("nightly", "reset", "event", "read")
FORECAST_KINDS = ("spending", "saving", "obligation")


@dataclass(frozen=True)
class Gathered:
    """Mọi dữ liệu đã đọc cho MỘT lần chấm điểm (dùng lại cho cú sốc, không đọc lại)."""

    now: datetime
    ctx: Context
    app_date: date
    jar_rows: tuple[Mapping[str, Any], ...]
    obligations: tuple[Mapping[str, Any], ...]
    inputs: ResilienceInputs
    basis: ForecastBasis
    #: tổng số dư và mã hũ Dự phòng (hũ tiết kiệm không có mục tiêu đầu tiên); None nếu không có
    emergency_jar_code: str | None
    #: tóm tắt dự báo mới nhất của từng hũ (đã đọc cho `basis`; LP lấy ngày cạn của hũ đang chi tăng làm dữ kiện, không tính lại dự báo)
    summaries: tuple[Mapping[str, Any], ...] = ()


def emergency_jar(jar_rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """Use the explicit buffer if present, with the legacy no-goal fallback."""
    buffers = [j for j in jar_rows if is_buffer_jar(j["kind"], j.get("purpose"), j.get("goal_vnd"))]
    return next((j for j in buffers if j.get("purpose") == "buffer"), buffers[0] if buffers else None)


def monthly_equivalent(
    ob: Mapping[str, Any], month_days: int, *, once_months: int | None = None, today: date
) -> int:
    """Nghĩa vụ quy về mỗi tháng: tháng giữ nguyên, tuần x tháng/7, năm / 12; khoản một lần chia đều cho `once_months` tháng nếu đến
    hạn trong khoảng đó (không có `once_months` thì không tính)."""
    amount = int_of(ob["amount_vnd"])
    cycle = ob["cycle"]
    if cycle == "monthly":
        return amount
    if cycle == "weekly":
        return round(amount * month_days / 7)
    if cycle == "yearly":
        return round(amount / 12)
    if once_months is None:
        return 0
    due = to_date(ob["due_date"])
    assert due is not None
    return (
        round(amount / once_months)
        if due <= today + timedelta(days=once_months * month_days)
        else 0
    )


def window_obligations(
    obligations: Sequence[Mapping[str, Any]], today: date, window_days: int
) -> tuple[int, dict[str, int]]:
    """(tổng nghĩa vụ đến hạn trong (hôm nay, hôm nay + kỳ], tách theo loại), tính từng lần đến hạn (như `yofina_planner.facts`)."""
    first, through = today + timedelta(days=1), today + timedelta(days=window_days)
    total = 0
    by_kind: dict[str, int] = {}
    for ob in obligations:
        if ob.get("status", "active") != "active":
            continue
        due = to_date(ob["due_date"])
        assert due is not None
        n = len(
            expand_due_dates(
                due,
                str(ob["cycle"]),
                int(ob["due_day"]) if ob.get("due_day") is not None else None,
                first=first,
                through=through,
            )
        )
        amount = int_of(ob["amount_vnd"]) * n
        if amount:
            total += amount
            by_kind[ob["kind"]] = by_kind.get(ob["kind"], 0) + amount
    return total, by_kind


def variable_monthly_spend(spend: Sequence[Any], window_days: int, month_days: int) -> int:
    """Chi thay đổi của một hũ quy về một tháng: trung bình `window_days` ngày lịch sử gần nhất x `month_days`. Chưa có ngày lịch sử
    nào thì 0. Cùng công thức `yofina_core.spend_baseline.recent_monthly` (mức chi gần đây; cách lùi của mức nền bền)."""
    return recent_monthly(spend, window_days, month_days)


def forecast_basis(
    rows: Sequence[Mapping[str, Any]], now: datetime, freshness_seconds: int
) -> ForecastBasis:
    """`basis` từ tóm tắt dự báo mới nhất của các hũ (cùng cách `run_scenario` dựng)."""
    latest = max(rows, key=lambda r: (r["computed_at"], str(r["run_id"])))
    computed = latest["computed_at"]
    basis: dict[str, Any] = {
        "computed_at": format_instant(computed),
        "stale": (now - computed).total_seconds() > freshness_seconds,
        "confidence_band": min_band([r["confidence_band"] for r in rows]),
        "is_initial_estimate": any(bool(r["is_initial_estimate"]) for r in rows),
        "history_days": max(int(r["history_days"]) for r in rows),
    }
    if latest.get("data_coverage") is not None:
        basis["coverage"] = round(float(latest["data_coverage"]), 3)
    return ForecastBasis.model_validate(basis)


def score_of(i: ResilienceInputs, cfg: ResilienceConfig | None = None) -> ResilienceResult:
    """Chấm điểm bằng công thức của `yofina_ml.resilience` với cấu hình của `yofina_core` (nhóm điểm do `band_for_score` quyết định)."""
    config = cfg or load_resilience_config()
    return compute_score(i, config, lambda score: band_for_score(score, config))


class ResilienceEngine:
    """Điểm chống chịu cho một người dùng. Chỉ cần `Pipeline` (kho dự báo cũng đọc được hũ, nghĩa vụ, điểm đã lưu)."""

    def __init__(self, pipeline: Pipeline, config: ResilienceConfig | None = None) -> None:
        self.pipeline = pipeline
        self.config = config or load_resilience_config()

    @property
    def settings(self):  # type: ignore[no-untyped-def]
        return self.pipeline.settings

    # --- đọc dữ liệu ---------------------------------------------------------------------------
    def gather(self, user_id: str, now: datetime) -> Gathered:
        s = self.settings
        repo = self.pipeline.repo
        ctx = self.pipeline.load_context(user_id, now)
        profile = ctx.meta.get("profile") or {}
        salary, payday = profile.get("monthly_salary_vnd"), profile.get("payday_day")
        if salary is None or payday is None or int_of(salary) <= 0:
            raise YofinaError(ErrorCode.PROFILE_INCOMPLETE, "Chưa khai lương và ngày nhận lương.")
        today = ctx.app_date
        summaries = repo.summaries(user_id)
        if not summaries:  # chưa có dự báo: tính một lần (cần cho độ tươi và nhóm tin cậy)
            self.pipeline.run_user(user_id, trigger="read")
            summaries = repo.summaries(user_id)
        if not summaries:
            raise YofinaError(
                ErrorCode.FORECAST_UNAVAILABLE,
                "Chưa có dự báo và chưa tính được ngay, thử lại sau ít phút.",
            )
        jar_rows = tuple(r for r in repo.jar_state(user_id) if r["kind"] in FORECAST_KINDS)
        if not jar_rows:
            raise YofinaError(ErrorCode.FORECAST_UNAVAILABLE, "Chưa có hũ nào để chấm điểm.")
        obligations = tuple(repo.obligations(user_id, "active"))
        inputs = self.build_inputs(
            ctx=ctx,
            salary=int_of(salary),
            jar_rows=jar_rows,
            obligations=obligations,
            paid=repo.paid_obligation_count(
                user_id, today - timedelta(days=s.resilience_window_days)
            ),
        )
        em = emergency_jar(jar_rows)
        return Gathered(
            now=now,
            ctx=ctx,
            app_date=today,
            jar_rows=jar_rows,
            obligations=obligations,
            inputs=inputs,
            basis=forecast_basis(summaries, now, s.freshness_seconds),
            emergency_jar_code=em["code"] if em else None,
            summaries=tuple(summaries),
        )

    def build_inputs(
        self,
        *,
        ctx: Context,
        salary: int,
        jar_rows: Sequence[Mapping[str, Any]],
        obligations: Sequence[Mapping[str, Any]],
        paid: int,
    ) -> ResilienceInputs:
        s = self.settings
        window, month_days = s.resilience_window_days, s.allocation.month_days
        today = ctx.app_date
        spend_by_jar = {j["code"]: j.get("spend") or [] for j in ctx.jars if j["kind"] != "system"}
        variable = sum(
            variable_monthly_spend(spend_by_jar.get(j["code"], []), window, month_days)
            for j in jar_rows
        )
        total_ob, by_kind = window_obligations(obligations, today, window)
        overdue = sum(
            1
            for o in obligations
            if o.get("status", "active") == "active" and (to_date(o["due_date"]) or today) < today
        )
        on_time = paid / (paid + overdue) if paid + overdue > 0 else 1.0
        goals: list[GoalFact] = []
        for j in jar_rows:
            if (
                j.get("goal_vnd") is None or j.get("goal_date") is None
                or (j.get("purpose") is not None and not is_goal_jar(j["kind"], j.get("purpose")))
            ):
                continue
            remaining = max(int_of(j["goal_vnd"]) - int_of(j["balance_vnd"]), 0)
            days_left = (to_date(j["goal_date"]) - today).days  # type: ignore[operator]
            needed = monthly_needed_vnd(
                remaining_vnd=remaining, days_left=days_left, month_days=month_days
            )
            contribution = round(salary * float(j["split_percent"]) / 100.0)
            goals.append(GoalFact(j["code"], needed, contribution))
        return ResilienceInputs(
            liquid_balance_vnd=sum(int_of(j["balance_vnd"]) for j in jar_rows),
            income_vnd=round(salary * window / month_days),
            variable_spend_vnd=round(variable * window / month_days),
            obligations_vnd=total_ob,
            window_days=window,
            on_time_share=on_time,
            goals=tuple(goals),
            obligations_by_kind=by_kind,
        )

    # --- chấm điểm ---------------------------------------------------------------------------
    def score(self, g: Gathered) -> ResilienceResult:
        return score_of(g.inputs, self.config)

    def to_data(
        self, g: Gathered, result: ResilienceResult, previous_score: int | None
    ) -> ResilienceScoreData:
        comps = [
            {
                "key": c.key,
                "label": c.label,
                "score": c.score,
                "weight": c.weight,
                "applicable": c.applicable,
                "band": c.band,
                "explanation": c.explanation,
                "inputs": [
                    {"key": k, "label": lab, "value": val, "unit": unit}
                    for k, lab, val, unit in c.inputs
                ],
            }
            for c in result.components
        ]
        return ResilienceScoreData.model_validate(
            {
                "score": result.score,
                "band": result.band,
                "headline": result.headline,
                "app_date": g.app_date.isoformat(),
                "computed_at": format_instant(g.now),
                "components": comps,
                "weakest": result.weakest,
                "previous_score": previous_score,
                "config_version": self.config.version,
                "disclaimer": self.config.disclaimer,
                "basis": g.basis.model_dump(mode="json", exclude_none=True),
            }
        )

    def _previous_score(self, user_id: str, app_date: date) -> int | None:
        row = self.pipeline.repo.resilience(user_id, app_date - timedelta(days=1))
        return int(row["score"]) if row else None

    # --- tính và lưu -------------------------------------------------------------------------
    def compute_and_store(
        self, user_id: str, now: datetime, *, source: str = "nightly"
    ) -> ResilienceScoreData:
        if source not in SOURCES:
            raise ValueError(f"source không hợp lệ: {source}")
        g = self.gather(user_id, now)
        result = self.score(g)
        data = self.to_data(g, result, self._previous_score(user_id, g.app_date))
        wire = data.model_dump(mode="json", exclude_none=True)
        self.pipeline.repo.save_resilience(
            user_id,
            app_date=g.app_date,
            score=data.score,
            band=data.band,
            weakest=data.weakest,
            headline=data.headline,
            components=wire["components"],
            inputs=dict(result.inputs),
            basis=wire["basis"],
            config_version=self.config.version,
            source=source,
            computed_at=now,
        )
        log.info(
            json.dumps(
                {
                    "msg": "resilience_stored",
                    "source": source,
                    "score": data.score,
                    "band": data.band,
                }
            )
        )
        return data

    # --- tool và REST ------------------------------------------------------------------------
    def get(self, user_id: str, *, refresh: Any = None) -> dict[str, Any]:
        """`forecast___get_resilience_score`: đọc điểm đã lưu; tính lại khi `refresh`, chưa có, sang ngày mô phỏng khác, cấu hình đã
        đổi hoặc quá `freshness_seconds`. Kết quả `{status, as_of, app_date, data}`."""
        if refresh is not None and not isinstance(refresh, bool):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "refresh phải là true hoặc false.")
        now = self.pipeline.now()
        stored = None if refresh else self._fresh_stored(user_id, now)
        if stored is not None:
            data = self._data_from_row(stored)
        else:
            data = self.compute_and_store(user_id, now, source="read")
        return {
            "status": str(ToolStatus.OK),
            "as_of": format_instant(now),
            "app_date": data.app_date,
            "data": data.model_dump(mode="json", exclude_none=True),
        }

    def _fresh_stored(self, user_id: str, now: datetime) -> Mapping[str, Any] | None:
        jars = self.pipeline.repo.jar_state(user_id)
        if not jars:
            return None
        offset = jars[0].get("clock_offset_days")
        if offset is None:
            return None
        today = app_today(int(offset), now, self.settings.tz)
        row = self.pipeline.repo.resilience(user_id)
        if row is None or to_date(row["app_date"]) != today:
            return None
        if row["config_version"] != self.config.version:
            return None
        if (now - row["computed_at"]).total_seconds() > self.settings.freshness_seconds:
            return None
        return row

    def _data_from_row(self, row: Mapping[str, Any]) -> ResilienceScoreData:
        basis = dict(row["basis"])
        # độ tươi tính lại theo lúc đọc (cột `basis` ghi `stale` lúc tính)
        computed = datetime.fromisoformat(str(basis["computed_at"]).replace("Z", "+00:00"))
        basis["stale"] = (
            self.pipeline.now() - computed
        ).total_seconds() > self.settings.freshness_seconds
        return ResilienceScoreData.model_validate(
            {
                "score": int(row["score"]),
                "band": row["band"],
                "headline": row["headline"],
                "app_date": to_date(row["app_date"]).isoformat(),  # type: ignore[union-attr]
                "computed_at": format_instant(row["computed_at"]),
                "components": row["components"],
                "weakest": row["weakest"],
                "previous_score": int(row["previous_score"])
                if row.get("previous_score") is not None
                else None,
                "config_version": row["config_version"],
                "disclaimer": self.config.disclaimer,
                "basis": basis,
            }
        )


def compute_and_store(
    pipeline: Pipeline, user_id: str, now: datetime, *, source: str = "nightly"
) -> ResilienceScoreData:
    """HÀM N2 (phase 4): tính và ghi điểm chống chịu của MỘT người dùng. KHÔNG tự nối vào `Pipeline.run_user`; người điều phối nối nó
    sau bước dự báo (lỗi của bước này không được làm hỏng các bước khác). Ném `YofinaError` (PROFILE_INCOMPLETE, FORECAST_UNAVAILABLE...)."""
    return ResilienceEngine(pipeline).compute_and_store(user_id, now, source=source)


__all__ = [
    "Gathered",
    "ResilienceEngine",
    "compute_and_store",
    "emergency_jar",
    "forecast_basis",
    "monthly_equivalent",
    "score_of",
    "variable_monthly_spend",
    "window_obligations",
]
