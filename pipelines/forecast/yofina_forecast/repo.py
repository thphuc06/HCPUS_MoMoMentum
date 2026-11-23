"""Truy cập Aurora của pipeline dự báo, qua `yofina_core.db.DataApi` bằng role `yofina_app` (RLS, không bao giờ secret master).

- Đọc: hàm `app_*` (một lệnh gọi, RLS theo `set_config` trong hàm).
- Ghi: MỘT transaction cho cả lần chạy (`forecast_runs`, `forecast_jar_summaries`, `forecasts`) rồi dọn lần chạy cũ; lỗi thì rollback
  nên không bao giờ có lần chạy ghi dở.
- Mọi câu lệnh ghi đặt `user_id = :uid` do code ép; RLS là lớp phụ.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from yofina_core.db import DataApi, Row
from yofina_ml.types import ForecastResult

SQL_CONTEXT = (
    "SELECT section, jar_code, payload "
    "FROM app_get_forecast_context(CAST(:uid AS text), CAST(:now AS timestamptz), CAST(:tz AS text), CAST(:win AS integer))"
)
SQL_SUMMARIES = "SELECT * FROM app_get_forecast_summaries(CAST(:uid AS text), CAST(:jar AS text))"
SQL_RUN = "SELECT * FROM app_get_forecast_run(CAST(:uid AS text), CAST(:run AS uuid), CAST(:jars AS text))"
SQL_USERS = "SELECT user_id FROM app_list_forecast_users(CAST(:lim AS integer))"
SQL_PRUNE = "SELECT app_prune_forecast_runs(CAST(:uid AS text), CAST(:keep AS integer)) AS removed"

SQL_INSERT_RUN = (
    "INSERT INTO forecast_runs (id, user_id, model, model_version, computed_at, app_date, horizon_days, history_days, "
    "data_coverage, confidence_label, is_initial_estimate, trigger, n_paths, seed, parent_run_id, source_event_id, params) "
    "VALUES (CAST(:id AS uuid), :uid, :model, :model_version, CAST(:computed_at AS timestamptz), CAST(:app_date AS date), "
    ":horizon, :history_days, CAST(:coverage AS numeric), :label, :initial, :trigger, :n_paths, :seed, CAST(:parent AS uuid), "
    ":source_event, CAST(:params AS jsonb))"
)
SQL_INSERT_SUMMARY = (
    "INSERT INTO forecast_jar_summaries (run_id, user_id, jar_code, start_balance_vnd, payday_date, days_to_payday, "
    "runout_date, p_shortfall, p_shortfall_se, status, confidence_band, show_probability, series_kind) "
    "VALUES (CAST(:run AS uuid), :uid, :jar, CAST(:start AS numeric), CAST(:payday AS date), :days_to_payday, "
    "CAST(:runout AS date), CAST(:p AS numeric), CAST(:se AS numeric), :status, :band, :show, :kind)"
)
SQL_INSERT_DAY = (
    "INSERT INTO forecasts (run_id, user_id, jar_code, day, spend_p10_vnd, spend_p50_vnd, spend_p90_vnd, "
    "balance_p10_vnd, balance_p50_vnd, balance_p90_vnd) "
    "VALUES (CAST(:run AS uuid), :uid, :jar, CAST(:day AS date), CAST(:s10 AS numeric), CAST(:s50 AS numeric), "
    "CAST(:s90 AS numeric), CAST(:b10 AS numeric), CAST(:b50 AS numeric), CAST(:b90 AS numeric))"
)
SQL_INSERT_SCENARIO = (
    "INSERT INTO scenarios (id, user_id, trace_id, kind, spec, spec_hash, app_date, baseline_run_id, n_paths, seed, result, "
    "conversation_id, bundle) "
    "VALUES (CAST(:id AS uuid), :uid, :trace_id, :kind, CAST(:spec AS jsonb), :spec_hash, CAST(:app_date AS date), "
    "CAST(:run AS uuid), :n_paths, :seed, CAST(:result AS jsonb), CAST(:conversation_id AS text), CAST(:bundle AS jsonb))"
)
SQL_LIST_CONVERSATION_SCENARIOS = "SELECT * FROM app_list_conversation_scenarios(CAST(:uid AS text), CAST(:cid AS text), CAST(:lim AS integer))"
SQL_PRUNE_SCENARIOS = (
    "SELECT app_prune_scenarios(CAST(:uid AS text), CAST(:keep AS integer)) AS removed"
)
BATCH_CHUNK = 400  # Data API cho tối đa 1.000 bộ tham số mỗi lần; chừa dư


def _dec(value: float | None, digits: int) -> Decimal | None:
    return None if value is None else Decimal(str(round(float(value), digits)))


class ForecastRepo:
    def __init__(self, db: DataApi) -> None:
        self.db = db

    # --- đọc ------------------------------------------------------------------------------------
    def context(self, user_id: str, now: datetime, tz: str, window_days: int) -> list[Row]:
        return self.db.query(
            SQL_CONTEXT,
            {"uid": user_id, "now": now, "tz": tz, "win": window_days},
            max_rows=200,
        )

    def summaries(self, user_id: str, jar: str | None = None) -> list[Row]:
        """Tóm tắt dự báo MỚI NHẤT của mỗi hũ (hàm `app_get_forecast_summaries`)."""
        return self.db.query(SQL_SUMMARIES, {"uid": user_id, "jar": jar}, max_rows=40)

    def run(self, user_id: str, run_id: str, jar_codes: Sequence[str] | None = None) -> Row | None:
        """Một lần chạy kèm `params`; `jar_codes` lọc `params.jar_state` (giữ dưới giới hạn 64 KB mỗi dòng của Data API)."""
        rows = self.db.query(
            SQL_RUN,
            {"uid": user_id, "run": run_id, "jars": ",".join(jar_codes) if jar_codes else None},
            max_rows=1,
        )
        return rows[0] if rows else None

    def users(self, limit: int) -> list[str]:
        return [r["user_id"] for r in self.db.query(SQL_USERS, {"lim": limit}, max_rows=500)]

    # --- ghi ------------------------------------------------------------------------------------
    def save(
        self,
        user_id: str,
        result: ForecastResult,
        *,
        trigger: str,
        params: Mapping[str, Any],
        computed_at: datetime,
        parent_run_id: str | None = None,
        source_event_id: str | None = None,
        keep_runs: int = 6,
    ) -> str:
        """Ghi một lần chạy (run + tóm tắt + dòng ngày) trong MỘT transaction rồi dọn lần chạy cũ. Trả `run_id`.

        `computed_at` là đồng hồ của người gọi (cùng đồng hồ với các phép so độ tươi), không phải `now()` của DB: tránh lệch
        giữa hai đồng hồ làm sai kiểm tra độ tươi và thứ tự "mới nhất"."""
        run_id = str(uuid.uuid4())
        run = result.run
        summaries = [
            {
                "run": run_id,
                "uid": user_id,
                "jar": jf.summary.jar_code,
                "start": jf.summary.start_balance_vnd,
                "payday": jf.summary.payday_date,
                "days_to_payday": jf.summary.days_to_payday,
                "runout": jf.summary.runout_date,
                "p": _dec(jf.summary.p_shortfall, 4),
                "se": _dec(jf.summary.p_shortfall_se, 5),
                "status": jf.summary.status,
                "band": jf.summary.confidence_band,
                "show": jf.summary.show_probability,
                "kind": jf.summary.series_kind,
            }
            for jf in result.jars
        ]
        days = [
            {
                "run": run_id,
                "uid": user_id,
                "jar": jf.summary.jar_code,
                "day": d.date,
                "s10": d.spend_p10_vnd,
                "s50": d.spend_p50_vnd,
                "s90": d.spend_p90_vnd,
                "b10": d.balance_p10_vnd,
                "b50": d.balance_p50_vnd,
                "b90": d.balance_p90_vnd,
            }
            for jf in result.jars
            for d in jf.days
        ]
        with self.db.transaction(user_id) as tx:
            tx.execute(
                SQL_INSERT_RUN,
                {
                    "id": run_id,
                    "uid": user_id,
                    "model": run.model,
                    "model_version": run.model_version,
                    "computed_at": computed_at,
                    "app_date": run.app_date,
                    "horizon": run.horizon_days,
                    "history_days": run.history_days,
                    "coverage": _dec(run.data_coverage, 3),
                    "label": run.confidence_label,
                    "initial": run.is_initial_estimate,
                    "trigger": trigger,
                    "n_paths": run.n_paths,
                    "seed": run.seed,
                    "parent": parent_run_id,
                    "source_event": source_event_id,
                    "params": json.dumps(params, ensure_ascii=False, separators=(",", ":")),
                },
            )
            tx.batch(SQL_INSERT_SUMMARY, summaries)
            for i in range(0, len(days), BATCH_CHUNK):
                tx.batch(SQL_INSERT_DAY, days[i : i + BATCH_CHUNK])
            tx.execute(SQL_PRUNE, {"uid": user_id, "keep": keep_runs})
        return run_id


def save_scenario(
    repo: ForecastRepo,
    user_id: str,
    *,
    scenario_id: str,
    trace_id: str,
    kind: str,
    spec: Mapping[str, Any],
    spec_hash: str,
    app_date: date,
    baseline_run_id: str | None,
    n_paths: int,
    seed: int | None,
    result: Mapping[str, Any],
    keep: int,
    conversation_id: str | None = None,
    bundle: Sequence[Mapping[str, Any]] | None = None,
) -> None:
    """Ghi một kịch bản đã chạy (dữ liệu DẪN XUẤT, không phải sổ cái; bảng `scenarios`) rồi dọn bớt bản cũ, trong một transaction.

    `conversation_id` (id phiên chat) và `bundle` (các spec đã gộp, theo thứ tự áp, phần tử cuối là `spec`) là của migration 0051;
    vắng thì lưu NULL."""
    with repo.db.transaction(user_id) as tx:
        tx.execute(
            SQL_INSERT_SCENARIO,
            {
                "id": scenario_id,
                "uid": user_id,
                "trace_id": trace_id,
                "kind": kind,
                "spec": json.dumps(spec, ensure_ascii=False, separators=(",", ":")),
                "spec_hash": spec_hash,
                "app_date": app_date,
                "run": baseline_run_id,
                "n_paths": n_paths,
                "seed": seed,
                "result": json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                "conversation_id": conversation_id,
                "bundle": None
                if bundle is None
                else json.dumps(list(bundle), ensure_ascii=False, separators=(",", ":")),
            },
        )
        tx.execute(SQL_PRUNE_SCENARIOS, {"uid": user_id, "keep": keep})


def list_conversation_scenarios(
    repo: ForecastRepo, user_id: str, conversation_id: str, limit: int
) -> list[Row]:
    """Các kịch bản của CHÍNH người dùng trong một cuộc chat, mới nhất trước (hàm `app_list_conversation_scenarios`, tối đa 10)."""
    return repo.db.query(
        SQL_LIST_CONVERSATION_SCENARIOS,
        {"uid": user_id, "cid": conversation_id, "lim": limit},
        max_rows=10,
    )


def to_date(value: Any) -> date | None:
    """`date` hoặc chuỗi ISO -> `date` (hàm DB trả `date` đã đổi sẵn; giữ để chịu được cả chuỗi)."""
    if value is None or isinstance(value, date):
        return value  # type: ignore[return-value]
    return date.fromisoformat(str(value)[:10])
