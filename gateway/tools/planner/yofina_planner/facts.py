"""Dữ kiện của người dùng cho các luật suitability: số dư hũ, nghĩa vụ đang hoạt động, thu nhập đã khai, khẩu vị rủi ro.

`load_facts` đọc từ `repo` (cùng giao diện `LedgerRepo`: `user_row`, `jar_view`, `list_obligations`) trong ba lệnh gọi; hàm
đánh giá (`engine.py`) chỉ nhận `SuitabilityFacts` đã dựng nên thuần và test được không cần DB.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from yofina_core.clock import next_payday as next_payday_of
from yofina_core.money import to_vnd
from yofina_core.schedule import expand_due_dates

MONTH_DAYS = Decimal(30)


@dataclass(frozen=True)
class JarFact:
    code: str
    name: str
    kind: str
    balance_vnd: int
    goal_vnd: int | None = None


@dataclass(frozen=True)
class ObligationFact:
    kind: str
    name: str
    amount_vnd: int
    due_date: date
    cycle: str
    due_day: int | None
    pay_jar_code: str | None
    is_essential: bool


@dataclass(frozen=True)
class SuitabilityFacts:
    today: date
    next_payday: date | None
    monthly_income_vnd: int | None
    risk_tolerance: str | None
    jars: tuple[JarFact, ...]
    obligations: tuple[ObligationFact, ...]
    #: số ngày của kỳ tính tổng nghĩa vụ (cấu hình: `suitability_window_days` hoặc horizon dự báo)
    window_days: int

    def jar(self, code: str | None) -> JarFact | None:
        return next((j for j in self.jars if j.code == code), None)

    @property
    def default_pay_jar(self) -> str | None:
        """Hũ trả nghĩa vụ mặc định: hũ `obligation` đầu tiên (cùng quy tắc của dự báo)."""
        return next((j.code for j in self.jars if j.kind == "obligation"), None)

    def pay_jar_of(self, ob: ObligationFact) -> str | None:
        return ob.pay_jar_code or self.default_pay_jar

    def dues_between(self, first: date, through: date) -> list[tuple[ObligationFact, date]]:
        """Mọi lần đến hạn của nghĩa vụ đang hoạt động trong [first, through]; nghĩa vụ quá hạn tính vào `first`."""
        out: list[tuple[ObligationFact, date]] = []
        for ob in self.obligations:
            for d in expand_due_dates(
                ob.due_date, ob.cycle, ob.due_day, first=first, through=through
            ):
                out.append((ob, d))
        return out

    def window_obligations_vnd(self) -> int:
        """Tổng nghĩa vụ đến hạn trong kỳ tính (từ ngày mai tới hết `window_days`)."""
        first = self.today + timedelta(days=1)
        through = self.today + timedelta(days=self.window_days)
        return sum(ob.amount_vnd for ob, _ in self.dues_between(first, through))

    def essential_monthly_vnd(self) -> Decimal:
        """Chi tiêu thiết yếu mỗi tháng: nghĩa vụ đánh dấu thiết yếu, quy về tháng 30 ngày (tuần x 30/7, năm / 12)."""
        total = Decimal(0)
        for ob in self.obligations:
            if not ob.is_essential:
                continue
            if ob.cycle == "monthly":
                total += ob.amount_vnd
            elif ob.cycle == "weekly":
                total += Decimal(ob.amount_vnd) * MONTH_DAYS / 7
            elif ob.cycle == "yearly":
                total += Decimal(ob.amount_vnd) / 12
        return total

    def is_emergency_jar(self, jar: JarFact) -> bool:
        """Hũ thuộc quỹ dự phòng: hũ tiết kiệm không gắn mục tiêu cụ thể (hũ có mục tiêu là để dành cho việc khác). Cùng định nghĩa
        với `yofina_forecast.resilience.emergency_jar`."""
        return jar.kind == "saving" and jar.goal_vnd is None

    def emergency_fund_vnd(self) -> int:
        """Quỹ dự phòng: tổng số dư các hũ thuộc quỹ dự phòng (`is_emergency_jar`)."""
        return sum(j.balance_vnd for j in self.jars if self.is_emergency_jar(j))


def facts_from_rows(
    *,
    today: date,
    user: Mapping[str, Any] | None,
    jars: Sequence[Mapping[str, Any]],
    obligations: Sequence[Mapping[str, Any]],
    window_days: int,
) -> SuitabilityFacts:
    """Dựng dữ kiện từ các hàng DB (hàm thuần, test được)."""
    income = user.get("monthly_salary_vnd") if user else None
    payday = user.get("payday_day") if user else None
    return SuitabilityFacts(
        today=today,
        next_payday=next_payday_of(int(payday), today) if payday is not None else None,
        monthly_income_vnd=to_vnd(income) if income is not None else None,
        risk_tolerance=(user or {}).get("risk_tolerance"),
        jars=tuple(
            JarFact(
                code=j["code"],
                name=j["name"],
                kind=j["kind"],
                balance_vnd=to_vnd(j["balance_vnd"]),
                goal_vnd=to_vnd(j["goal_vnd"]) if j.get("goal_vnd") is not None else None,
            )
            for j in jars
            if j.get("kind") != "system"
        ),
        obligations=tuple(
            ObligationFact(
                kind=o["kind"],
                name=str(o["name"]),
                amount_vnd=to_vnd(o["amount_vnd"]),
                due_date=o["due_date"]
                if isinstance(o["due_date"], date)
                else date.fromisoformat(str(o["due_date"])[:10]),
                cycle=o["cycle"],
                due_day=int(o["due_day"]) if o.get("due_day") is not None else None,
                pay_jar_code=o.get("pay_jar_code"),
                is_essential=bool(o.get("is_essential")),
            )
            for o in obligations
            if o.get("status", "active") == "active"
        ),
        window_days=window_days,
    )


def load_facts(repo: Any, user_id: str, *, today: date, window_days: int) -> SuitabilityFacts:
    """Đọc ba lệnh (hồ sơ, hũ, nghĩa vụ đang hoạt động) rồi dựng dữ kiện."""
    view = repo.jar_view(user_id)
    return facts_from_rows(
        today=today,
        user=repo.user_row(user_id),
        jars=view.jars,
        obligations=repo.list_obligations(user_id, status="active", limit=100),
        window_days=window_days,
    )
