"""Lịch của nghĩa vụ và lương: hàm thuần dùng chung ledger (ghi, đọc) và pipeline dự báo (luồng C).

Mọi hàm nhận ngày mô phỏng tường minh (không đọc đồng hồ hệ thống, ADR-0003). Quy tắc mở rộng chu kỳ khớp
contracts/README.md ("Mở rộng chu kỳ"): `weekly` cộng 7 ngày, `monthly` theo `due_day` (kẹp ngày cuối tháng),
`yearly` cộng một năm (29/2 kẹp 28/2), `once` chỉ `due_date`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from yofina_core.clock import next_payday, payday_dates, payday_in_month
from yofina_core.wallet import split_amount


def _add_months(day: date, months: int, due_day: int | None = None) -> date:
    """Cộng `months` tháng; ngày trong tháng là `due_day` (nếu có) hoặc `day.day`, kẹp ngày cuối tháng."""
    index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(index, 12)
    return payday_in_month(due_day or day.day, year, month + 1)


def first_due_from_day(due_day: int, today: date) -> date:
    """Ngày `due_day` sớm nhất KHÔNG trước `today` (hôm nay đúng ngày đó thì lấy hôm nay)."""
    this_month = payday_in_month(due_day, today.year, today.month)
    return this_month if this_month >= today else _add_months(today, 1, due_day)


def bnpl_due_date(due_day: int, today: date) -> date:
    """Ngày đến hạn của nghĩa vụ trả sau: `due_day` KẾ TIẾP sau ngày mua (mua đúng ngày đó thì sang tháng sau)."""
    return next_payday(due_day, today)


def advance_due(due: date, cycle: str, due_day: int | None) -> date | None:
    """Ngày đến hạn kế tiếp sau khi trả kỳ `due`; `once` thì None (nghĩa vụ xong)."""
    if cycle == "weekly":
        return due + timedelta(days=7)
    if cycle == "monthly":
        return _add_months(due, 1, due_day or due.day)
    if cycle == "yearly":
        return _add_months(due, 12, due.day)
    return None


def expand_due_dates(
    due: date, cycle: str, due_day: int | None, *, first: date, through: date
) -> list[date]:
    """Mọi ngày đến hạn trong [`first`, `through`] của một nghĩa vụ có hạn kế tiếp là `due`.

    Hạn đã quá `first` (nghĩa vụ quá hạn) thì tính vào đúng ngày `first`, rồi các kỳ sau theo chu kỳ.
    """
    if due > through and due >= first:
        return []
    out: list[date] = []
    cursor: date | None = due
    if due < first:
        out.append(first)  # quá hạn: tính vào ngày đầu của chuỗi
        cursor = advance_due(due, cycle, due_day)
        while cursor is not None and cursor <= first:  # kỳ trùng ngày đầu đã gộp vào khoản quá hạn
            cursor = advance_due(cursor, cycle, due_day)
    while cursor is not None and cursor <= through:
        if cursor >= first:
            out.append(cursor)
        cursor = advance_due(cursor, cycle, due_day)
        if len(out) > 400:  # lưới an toàn với chu kỳ weekly kéo dài
            break
    return out


def midpoint(low: int, high: int) -> int:
    """Trung điểm làm tròn xuống (số tiền kỳ vọng của khoản có khoảng)."""
    return (low + high) // 2


@dataclass(frozen=True)
class TimelineEvent:
    date: date
    kind: str  # obligation | salary
    label: str
    amount_vnd: int
    amount_max_vnd: int | None = None


def _jar_of(ob: Mapping[str, Any], default_pay_jar: str | None) -> str | None:
    return ob.get("pay_jar_code") or default_pay_jar


def build_timeline_events(
    *,
    jar_code: str,
    obligations: Iterable[Mapping[str, Any]],
    origin: date,
    horizon_days: int,
    default_pay_jar: str | None,
    salary_vnd: int | None,
    payday_day: int | None,
    split_shares: Sequence[tuple[str, Any]],
    salary_label: str,
) -> list[TimelineEvent]:
    """Mốc trên biểu đồ của MỘT hũ: nghĩa vụ đang hoạt động trả bằng hũ này và phần lương của hũ.

    Ngày dự báo bắt đầu sau origin. Nghĩa vụ cũ thiếu hũ trả dùng default_pay_jar nếu có. Phần lương dùng `split_amount` (cùng quy tắc
    `confirm_salary`) nên số trên biểu đồ khớp số được chia thật. Sắp theo ngày, nghĩa vụ trước lương cùng ngày.
    """
    first = origin + timedelta(days=1)
    through = origin + timedelta(days=horizon_days)
    events: list[TimelineEvent] = []
    for ob in obligations:
        if ob.get("status", "active") != "active" or _jar_of(ob, default_pay_jar) != jar_code:
            continue
        due: date = ob["due_date"]
        amount = int(ob["amount_vnd"])
        high = ob.get("amount_max_vnd")
        for d in expand_due_dates(
            due, str(ob["cycle"]), ob.get("due_day"), first=first, through=through
        ):
            events.append(
                TimelineEvent(
                    d,
                    "obligation",
                    str(ob["name"])[:60],
                    amount,
                    int(high) if high is not None and int(high) > amount else None,
                )
            )
    if salary_vnd and payday_day and split_shares:
        part = split_amount(int(salary_vnd), list(split_shares)).get(jar_code, 0)
        if part > 0:
            for d in payday_dates(payday_day, origin, through):
                if d >= first:
                    events.append(TimelineEvent(d, "salary", salary_label[:60], part))
    events.sort(key=lambda e: (e.date, 0 if e.kind == "obligation" else 1, e.label))
    return events[:60]
