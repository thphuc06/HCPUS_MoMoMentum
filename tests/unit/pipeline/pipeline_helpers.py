"""Dữ liệu dựng sẵn cho test pipeline dự báo: cấu hình, context giống `app_get_forecast_context`, repo và Dynamo giả."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from yofina_forecast.settings import ForecastSettings

APP_DATE = date(2026, 11, 21)
NOW = datetime(2026, 12, 10, 3, 0, tzinfo=UTC)


def make_settings(**kw: Any) -> ForecastSettings:
    base: dict[str, Any] = {
        "horizon_days": 30,
        "history_window_days": 330,
        "n_paths_full": 600,
        "n_paths_fast": 400,
        "cold_start_min_days": 21,
        "aci_gamma": 0.01,
        "coverage_target": 0.8,
        "short_threshold": 0.5,
        "tight_threshold": 0.2,
        "band_high_min_days": 60,
        "band_high_min_coverage": 0.7,
        "band_medium_min_days": 21,
        "probability_enabled": True,
        "keep_runs": 6,
        "fast_max_age_seconds": 86400,
        "recompute_guard_seconds": 20,
        "freshness_seconds": 3600,
        "app_timezone": "Asia/Ho_Chi_Minh",
        "event_bus_name": "",
        "idempotency_table": "t",
        "idempotency_ttl_seconds": 259200,
        "idempotency_lease_seconds": 120,
        "nightly_max_users": 200,
    }
    base.update(kw)
    return ForecastSettings(**base)


def jar_row(
    code: str, kind: str, balance: int, split: float, order: int, spend: list[int]
) -> dict[str, Any]:
    return {
        "code": code,
        "name": code,
        "kind": kind,
        "balance_vnd": balance,
        "split_percent": split,
        "sort_order": order,
        "spend": spend,
    }


DEFAULT_OBLIGATIONS: list[dict[str, Any]] = [
    {
        "id": "00000000-0000-0000-0000-000000000001",
        "kind": "bill",
        "name": "Tiền điện",
        "amount_vnd": 375_000,
        "amount_min_vnd": 300_000,
        "amount_max_vnd": 450_000,
        "due_date": "2026-11-26",
        "cycle": "monthly",
        "due_day": 26,
        "pay_jar_code": "nghia_vu",
    },
    {
        "id": "00000000-0000-0000-0000-000000000002",
        "kind": "bnpl",
        "name": "Trả sau (mô phỏng)",
        "amount_vnd": 1_000_000,
        "amount_min_vnd": None,
        "amount_max_vnd": None,
        "due_date": "2026-12-05",
        "cycle": "once",
        "due_day": None,
        "pay_jar_code": None,
    },
]


def context_rows(
    *,
    days: int = 47,
    salary: int | None = 9_000_000,
    payday: int | None = 5,
    obligations: list[dict[str, Any]] | None = None,
    jars: list[dict[str, Any]] | None = None,
    spend_rows: int = 120,
    app_date: date = APP_DATE,
) -> list[dict[str, Any]]:
    """Các dòng như `app_get_forecast_context` (phần `payload` đã là dict)."""
    spend = [60_000 + 20_000 * (i % 4) for i in range(days)]
    if jars is None:
        jars = [
            jar_row("an_uong", "spending", 380_000, 60, 1, spend),
            jar_row(
                "giai_tri",
                "spending",
                760_000,
                20,
                2,
                [0, 0, 120_000] * (days // 3) + [0] * (days % 3),
            ),
            jar_row("nghia_vu", "obligation", 1_000_000, 20, 3, [0] * days),
        ]
    rows: list[dict[str, Any]] = [
        {
            "section": "meta",
            "jar_code": None,
            "payload": {
                "app_date": app_date.isoformat(),
                "history_start": (app_date - timedelta(days=days)).isoformat(),
                "spend_rows": spend_rows,
                "profile": {
                    "monthly_salary_vnd": salary,
                    "payday_day": payday,
                    "clock_offset_days": -19,
                },
                "coverage": {
                    "income_vnd": 18_000_000,
                    "spend_vnd": 5_000_000,
                    "balance_start_vnd": 100_000,
                    "balance_end_vnd": 13_100_000,
                },
            },
        }
    ]
    rows += [{"section": "jar", "jar_code": j["code"], "payload": j} for j in jars]
    for ob in obligations if obligations is not None else DEFAULT_OBLIGATIONS:
        rows.append({"section": "obligation", "jar_code": ob.get("pay_jar_code"), "payload": ob})
    return rows


class FakeDynamo:
    """Client DynamoDB giả đủ cho `IdempotencyStore`: `put_item` có điều kiện, `get_item`, `update_item`, `delete_item`."""

    class Conditional(Exception):
        response = {"Error": {"Code": "ConditionalCheckFailedException"}}  # noqa: RUF012

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.puts = 0

    def put_item(self, *, TableName, Item, ConditionExpression=None, **kw):
        key = Item["event_id"]["S"]
        old = self.items.get(key)
        if old is not None and ConditionExpression:
            now = int(kw["ExpressionAttributeValues"][":now"]["N"])
            stale_lease = old["status"]["S"] == "in_progress" and int(old["lease_until"]["N"]) < now
            if not stale_lease:
                raise self.Conditional()
        self.items[key] = dict(Item)
        self.puts += 1
        return {}

    def get_item(self, *, TableName, Key, **kw):
        item = self.items.get(Key["event_id"]["S"])
        return {"Item": item} if item else {}

    def update_item(self, *, TableName, Key, ExpressionAttributeValues, **kw):
        item = self.items[Key["event_id"]["S"]]
        item["status"] = ExpressionAttributeValues[":done"]
        item.pop("lease_until", None)
        if ":run" in ExpressionAttributeValues:
            item["run_id"] = ExpressionAttributeValues[":run"]
        return {}

    def delete_item(self, *, TableName, Key, ConditionExpression=None, **kw):
        item = self.items.get(Key["event_id"]["S"])
        if item is None or (ConditionExpression and item["status"]["S"] != "in_progress"):
            raise self.Conditional()
        del self.items[Key["event_id"]["S"]]
        return {}
