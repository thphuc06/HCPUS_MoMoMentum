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
from yofina_core.wallet import DEFAULT_SPENDING_JAR
from yofina_forecast.settings import DEFAULT_ESSENTIAL_JAR_CODES
from yofina_ml.types import ForecastResult

SQL_CONTEXT = """
WITH ctx AS MATERIALIZED (
  SELECT section, jar_code, payload
  FROM app_get_forecast_context(CAST(:uid AS text), CAST(:now AS timestamptz), CAST(:tz AS text), CAST(:win AS integer))
), date_window AS (
  SELECT CAST(payload->>'history_start' AS date) AS first_day,
         CAST(payload->>'app_date' AS date) - 1 AS last_day
  FROM ctx WHERE section = 'meta'
), essential AS (
  -- chi thiết yếu theo LOẠI giao dịch (nhóm của loại trong tx_type_map thuộc tham số essential, cấu hình essential_jar_codes), không gắn
  -- nghĩa vụ (khoản đã khai tính riêng ở sàn nghĩa vụ): của Chi hằng ngày và của hũ obligation (hóa đơn trả lẻ trên ví có hũ Nghĩa vụ chung)
  SELECT t.jar_code, t.app_date, sum(-t.amount_vnd) AS amount
  FROM transactions t
  JOIN tx_type_map m ON m.tx_type = t.tx_type
  JOIN jars ej ON ej.user_id = t.user_id AND ej.code = t.jar_code
  CROSS JOIN date_window w
  WHERE t.user_id = :uid
    AND (t.jar_code = :daily_jar OR ej.kind = 'obligation') AND t.kind = 'expense'
    AND t.funding_source IN ('jar', 'external') AND t.obligation_id IS NULL
    AND m.default_jar_code = ANY(string_to_array(CAST(:essential AS text), ','))
    AND t.app_date BETWEEN w.first_day AND w.last_day
  GROUP BY t.jar_code, t.app_date
)
SELECT c.section, c.jar_code,
  CASE WHEN c.section = 'jar' THEN
    c.payload || jsonb_strip_nulls(jsonb_build_object('purpose', j.purpose))
      || CASE WHEN c.jar_code = :daily_jar OR j.kind = 'obligation' THEN jsonb_build_object('essential_spend', (
        SELECT coalesce(jsonb_agg(coalesce(e.amount, 0) ORDER BY g.day), '[]'::jsonb)
        FROM date_window w CROSS JOIN LATERAL generate_series(
          CAST(w.first_day AS timestamp), CAST(w.last_day AS timestamp), interval '1 day'
        ) AS g(day)
        LEFT JOIN essential e ON e.jar_code = c.jar_code AND e.app_date = CAST(g.day AS date)
      )) ELSE '{}'::jsonb END
    ELSE c.payload END AS payload
FROM ctx c
LEFT JOIN jars j ON c.section = 'jar' AND j.user_id = :uid AND j.code = c.jar_code
"""
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
SQL_JAR_STATE = "SELECT * FROM app_get_jar_state_with_commitments(CAST(:uid AS text))"
SQL_OBLIGATIONS = "SELECT * FROM app_list_obligations(CAST(:uid AS text), CAST(:status AS text), CAST(:due AS date), CAST(:lim AS integer))"
SQL_GET_RESILIENCE = (
    "SELECT * FROM app_get_resilience_score(CAST(:uid AS text), CAST(:app_date AS date))"
)
#: số khoản nghĩa vụ ĐÃ TRẢ (dòng chi gắn `obligation_id`) từ ngày `:since`; RLS lọc theo người dùng của transaction
SQL_PAID_OBLIGATIONS = (
    "SELECT count(*) AS paid FROM transactions "
    "WHERE obligation_id IS NOT NULL AND kind = 'expense' AND app_date >= CAST(:since AS date)"
)
SQL_UPSERT_RESILIENCE = (
    "INSERT INTO resilience_scores (user_id, app_date, score, band, weakest, headline, components, inputs, basis, "
    "config_version, source, computed_at) "
    "VALUES (:uid, CAST(:app_date AS date), :score, :band, :weakest, :headline, CAST(:components AS jsonb), "
    "CAST(:inputs AS jsonb), CAST(:basis AS jsonb), :config_version, :source, CAST(:computed_at AS timestamptz)) "
    "ON CONFLICT (user_id, app_date) DO UPDATE SET score = EXCLUDED.score, band = EXCLUDED.band, weakest = EXCLUDED.weakest, "
    "headline = EXCLUDED.headline, components = EXCLUDED.components, inputs = EXCLUDED.inputs, basis = EXCLUDED.basis, "
    "config_version = EXCLUDED.config_version, source = EXCLUDED.source, computed_at = EXCLUDED.computed_at"
)
BATCH_CHUNK = 400  # Data API cho tối đa 1.000 bộ tham số mỗi lần; chừa dư


def _dec(value: float | None, digits: int) -> Decimal | None:
    return None if value is None else Decimal(str(round(float(value), digits)))


class ForecastRepo:
    def __init__(self, db: DataApi) -> None:
        self.db = db

    # --- đọc ------------------------------------------------------------------------------------
    def context(
        self,
        user_id: str,
        now: datetime,
        tz: str,
        window_days: int,
        essential_categories: Sequence[str] = DEFAULT_ESSENTIAL_JAR_CODES,
    ) -> list[Row]:
        """Ngữ cảnh dự báo. `essential_categories`: nhóm loại giao dịch thiết yếu (`tx_type_map.default_jar_code`, cấu hình
        `essential_jar_codes`) cho chuỗi `essential_spend` của Chi hằng ngày và hũ obligation."""
        with self.db.transaction(user_id) as tx:
            return tx.execute(
                SQL_CONTEXT,
                {
                    "uid": user_id,
                    "now": now,
                    "tz": tz,
                    "win": window_days,
                    "daily_jar": DEFAULT_SPENDING_JAR,
                    "essential": ",".join(essential_categories),
                },
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

    # --- điểm chống chịu, tối ưu phân bổ (phase 4) -------------------------------------------------
    def jar_state(self, user_id: str) -> list[Row]:
        """Mọi hũ (kể cả hũ hệ thống) kèm mục tiêu (`goal_vnd`, `goal_date`); không có hàng nào nếu chưa có hồ sơ."""
        return [r for r in self.db.query(SQL_JAR_STATE, {"uid": user_id}, max_rows=40) if r["code"]]

    def obligations(self, user_id: str, status: str = "active") -> list[Row]:
        return self.db.query(
            SQL_OBLIGATIONS,
            {"uid": user_id, "status": status, "due": None, "lim": 100},
            max_rows=100,
        )

    def paid_obligation_count(self, user_id: str, since: date) -> int:
        with self.db.transaction(user_id) as tx:
            rows = tx.execute(SQL_PAID_OBLIGATIONS, {"since": since})
        return int(rows[0]["paid"]) if rows else 0

    def resilience(self, user_id: str, app_date: date | None = None) -> Row | None:
        """Điểm chống chịu đã lưu mới nhất không sau `app_date` (None là mới nhất), kèm `previous_score`."""
        rows = self.db.query(SQL_GET_RESILIENCE, {"uid": user_id, "app_date": app_date}, max_rows=1)
        return rows[0] if rows else None

    def save_resilience(
        self,
        user_id: str,
        *,
        app_date: date,
        score: int,
        band: str,
        weakest: str,
        headline: str,
        components: Sequence[Mapping[str, Any]],
        inputs: Mapping[str, Any],
        basis: Mapping[str, Any],
        config_version: str,
        source: str,
        computed_at: datetime,
    ) -> None:
        """Ghi đè điểm của ngày mô phỏng `app_date` (một dòng mỗi người dùng và ngày)."""

        def dump(obj: Any) -> str:
            return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

        with self.db.transaction(user_id) as tx:
            tx.execute(
                SQL_UPSERT_RESILIENCE,
                {
                    "uid": user_id,
                    "app_date": app_date,
                    "score": score,
                    "band": band,
                    "weakest": weakest,
                    "headline": headline,
                    "components": dump(list(components)),
                    "inputs": dump(inputs),
                    "basis": dump(basis),
                    "config_version": config_version,
                    "source": source,
                    "computed_at": computed_at,
                },
            )

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
