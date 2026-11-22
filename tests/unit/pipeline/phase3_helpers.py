"""Đồ giả CHỈ dành cho unit test của engine phase 3 (`run_scenario`, `affordability_check`): kho đọc kiểu `LedgerRepo` dựng trên
`MemoryRepo` của test pipeline. Không được import từ mã sản phẩm."""

from __future__ import annotations

import copy
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from memory_repo import MemoryRepo
from pipeline_helpers import APP_DATE, NOW, context_rows, make_settings
from yofina_forecast.runner import Pipeline
from yofina_ledger.refdata import ReferenceData
from yofina_ledger.repo import JarView

USER = "u1"

JARS = [
    # code, name, color, icon, kind, balance, split, order, goal_vnd, goal_date
    ("an_uong", "Ăn uống", "violet", "utensils", "spending", 380_000, 60, 1, None, None),
    ("giai_tri", "Giải trí", "orchid", "gamepad", "spending", 760_000, 20, 2, None, None),
    ("nghia_vu", "Nghĩa vụ", "slate", "wallet", "obligation", 1_000_000, 20, 3, None, None),
]


def jar_rows(goal: bool = False) -> list[dict[str, Any]]:
    rows = []
    for code, name, color, icon, kind, bal, split, order, gv, gd in JARS:
        row = {
            "clock_offset_days": -19,
            "code": code,
            "name": name,
            "color_key": color,
            "icon_key": icon,
            "balance_vnd": Decimal(bal),
            "split_percent": Decimal(split),
            "sort_order": order,
            "kind": kind,
            "system_role": None,
            "goal_vnd": Decimal(gv) if gv else None,
            "goal_date": gd,
        }
        if goal and code == "giai_tri":
            row["goal_vnd"] = Decimal(3_000_000)
            row["goal_date"] = date(2027, 3, 1)
        rows.append(row)
    rows.append(
        {
            "clock_offset_days": -19,
            "code": "tien_vao_khac",
            "name": "Tiền vào khác",
            "color_key": "gray",
            "icon_key": "inbox",
            "balance_vnd": Decimal(350_000),
            "split_percent": Decimal(0),
            "sort_order": 98,
            "kind": "system",
            "system_role": "other_income",
            "goal_vnd": None,
            "goal_date": None,
        }
    )
    return rows


OBLIGATION_ROWS = [
    {
        "id": "00000000-0000-0000-0000-000000000001",
        "kind": "bill",
        "name": "Tiền điện",
        "amount_vnd": Decimal(375_000),
        "amount_min_vnd": Decimal(300_000),
        "amount_max_vnd": Decimal(450_000),
        "due_date": date(2026, 11, 26),
        "cycle": "monthly",
        "due_day": 26,
        "status": "active",
        "pay_jar_code": "nghia_vu",
        "is_essential": True,
    },
    {
        "id": "00000000-0000-0000-0000-000000000002",
        "kind": "bnpl",
        "name": "Trả sau (mô phỏng)",
        "amount_vnd": Decimal(1_000_000),
        "amount_min_vnd": None,
        "amount_max_vnd": None,
        "due_date": date(2026, 12, 5),
        "cycle": "once",
        "due_day": None,
        "status": "active",
        "pay_jar_code": None,
        "is_essential": False,
    },
]

FEE_ROWS = [
    {
        "id": "f1",
        "product_code": "bnpl_sim",
        "product_label": "Trả sau (mô phỏng)",
        "fee_type": "monthly_service_fee",
        "amount_vnd": Decimal(33_000),
        "rate_percent": None,
        "period": "per_month",
        "condition_code": "month_has_transaction",
        "condition_note": None,
        "source_name": "Biểu phí công khai (ví dụ)",
        "source_url": "https://example.com/fees",
        "effective_from": date(2026, 3, 31),
        "effective_to": None,
    }
]


class FakeLedgerRepo:
    """Giao diện đọc của `LedgerRepo` mà `ScenarioEngine`, `AffordabilityEngine` và `yofina_planner.facts` dùng."""

    def __init__(
        self,
        mem: MemoryRepo,
        *,
        obligations=None,
        credit_line=None,
        goal: bool = False,
        user=None,
    ) -> None:
        self.mem = mem
        self._obligations = copy.deepcopy(OBLIGATION_ROWS if obligations is None else obligations)
        self._line = (
            {
                "product_code": "bnpl_sim",
                "limit_vnd": Decimal(5_000_000),
                "outstanding_vnd": Decimal(967_000),
                "due_day": 5,
                "status": "active",
            }
            if credit_line is None
            else (credit_line or None)
        )
        self.goal = goal
        self._user = user or {
            "id": USER,
            "monthly_salary_vnd": Decimal(9_000_000),
            "payday_day": 5,
            "risk_tolerance": "medium",
            "clock_offset_days": -19,
        }
        self.calls: list[str] = []

    def jar_view(self, user_id: str) -> JarView:
        self.calls.append("jar_view")
        return JarView(-19, tuple(jar_rows(self.goal)))

    def user_row(self, user_id: str):
        return self._user

    def list_obligations(self, user_id: str, *, status="active", due_before=None, limit=50):
        return [o for o in self._obligations if status == "all" or o["status"] == status]

    def credit_line(self, user_id: str):
        return self._line

    def forecast_summaries(self, user_id: str, jar: str | None = None):
        return self.mem.summaries(user_id, jar)

    def forecast_series(self, user_id: str, jar: str):
        run = next((r for r in reversed(self.mem.runs) if any(j.summary.jar_code == jar for j in r["result"].jars)), None)
        if run is None:
            return []
        jf = next(j for j in run["result"].jars if j.summary.jar_code == jar)
        return [
            {
                "day": d.date,
                "balance_p10_vnd": Decimal(d.balance_p10_vnd),
                "balance_p50_vnd": Decimal(d.balance_p50_vnd),
                "balance_p90_vnd": Decimal(d.balance_p90_vnd),
            }
            for d in jf.days
        ]

    def reference_fees(self):
        return FEE_ROWS

    def reference_tx_types(self):
        return []

    def reference_templates(self):
        return []


def build(**kw: Any):
    """(pipeline, mem, repo, ref, settings) với một lần chạy đầy đủ đã lưu (nền cho what-if)."""
    settings = make_settings(
        scenario_n_paths=600, scenario_keep=50, reference_cache_seconds=300, **kw.pop("settings", {})
    )
    mem = MemoryRepo(context_rows(**kw.pop("context", {})))
    pipeline = Pipeline(mem, settings, None, clock=lambda: NOW)  # type: ignore[arg-type]
    repo = FakeLedgerRepo(mem, **kw)
    ref = ReferenceData(repo, 300)  # type: ignore[arg-type]
    pipeline.run_user(USER, trigger="manual")
    return pipeline, mem, repo, ref, settings


def fresh_now() -> datetime:
    return NOW


__all__ = ["APP_DATE", "NOW", "USER", "FakeLedgerRepo", "build"]
