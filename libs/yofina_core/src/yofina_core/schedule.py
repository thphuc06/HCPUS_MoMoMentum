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
from yofina_core.wallet import pay_jar_or_default, split_amount


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


def bnpl_pay_jar(
    jars: Sequence[Mapping[str, Any]],
    *,
    existing_pay_jar: str | None = None,
    chosen_jar: str | None = None,
) -> str | None:
    """Hũ trả khoản Trả sau, một quy tắc cho lúc mua (ledger), dự báo, what-if và kiểm tra trước khi chi.

    `jars` là các hũ người dùng (có `code`, `kind`) theo `sort_order`. Thứ tự: hũ trả của khoản Trả sau cùng ngày đến hạn
    đã có, rồi hũ `obligation` đầu tiên; không có hũ đó (tài khoản như `lan`, `khoa`) thì hũ người dùng chọn cho món mua,
    rồi hũ `spending` đầu tiên. None khi không có hũ nào hợp lệ.
    """
    codes = {j["code"] for j in jars}
    pay = existing_pay_jar or next((j["code"] for j in jars if j.get("kind") == "obligation"), None)
    if pay in codes:
        return pay
    if chosen_jar in codes:
        return chosen_jar
    return next((j["code"] for j in jars if j.get("kind") == "spending"), None)


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
    original_due_date: date | None = None


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
    codes = {code for code, _ in split_shares}
    for ob in obligations:
        source = pay_jar_or_default(codes, ob.get("pay_jar_code"), default_pay_jar)
        if ob.get("status", "active") != "active" or source != jar_code:
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
                    original_due_date=due if d == first and due < first else None,
                )
            )
    if salary_vnd and payday_day and split_shares:
        part = split_amount(int(salary_vnd), list(split_shares)).get(jar_code, 0)
        if part > 0:
            for d in payday_dates(payday_day, origin, through):
                if d >= first:
                    events.append(TimelineEvent(d, "salary", salary_label[:60], part))
    events.sort(key=lambda e: (e.date, 0 if e.kind == "obligation" else 1, e.label))
    return events


def salary_part_on(
    day: date,
    *,
    jar_code: str,
    origin: date,
    salary_vnd: int | None,
    payday_day: int | None,
    split_shares: Sequence[tuple[str, Any]],
) -> int:
    """Phần lương về hũ `jar_code` đúng ngày `day` theo lịch lương của dự báo gốc `origin`: ngày lương sau `origin`, phần chia bằng
    `split_amount` (cùng quy tắc mốc lương của `build_timeline_events` và đầu vào Monte Carlo của pipeline). 0 khi `day` không phải
    ngày lương, chưa khai lương, hoặc tỷ lệ chia không đủ 100% (khi đó dự báo không mô phỏng lương)."""
    if not salary_vnd or not payday_day or day <= origin:
        return 0
    if day != payday_in_month(int(payday_day), day.year, day.month):
        return 0
    try:
        return split_amount(int(salary_vnd), list(split_shares)).get(jar_code, 0)
    except ValueError:
        return 0


def due_before_payday(due: date | str, payday: date | str) -> bool:
    """Cửa sổ "đến hạn trước lương" của kỳ lương `payday`: khoản đến hạn TRƯỚC HOẶC ĐÚNG ngày lương (chốt 26/11, BR-22, #39).

    Một quy tắc cho danh sách khoản đến hạn của hũ trả nghĩa vụ (`obligation_window`: khối dự báo, what-if), bộ chấm eval và ngữ cảnh lộ
    trình. Khoản đến hạn đúng ngày lương được trả bằng số dư TRƯỚC khi lương ngày đó về (thận trọng: khoản trừ có thể chạy trước khi
    lương về), xem `obligation_window`. Nhận `date` hoặc ngày ISO `YYYY-MM-DD`.
    """
    return _as_date(due) <= _as_date(payday)


def _as_date(day: date | str) -> date:
    return day if isinstance(day, date) else date.fromisoformat(str(day))


def obligation_window(
    events: Iterable[Mapping[str, Any]],
    payday: str,
    end_balances: Mapping[str, int],
    *,
    opening_balance_vnd: int = 0,
) -> dict[str, Any]:
    """Các khoản đến hạn trước lương (`due_before_payday`: gồm ngày lương) của MỘT hũ, theo ngày rồi tên, và khoản thiếu đầu tiên
    theo số dư P50.

    `events` là mốc của hũ (`kind` `obligation` hoặc `salary`, ngày ISO); `original_due_date` (khoản quá hạn mà dự báo trừ vào ngày
    dự báo đầu tiên) thay cho ngày hiển thị. `end_balances` là số dư P50 CUỐI ngày theo ngày ISO (đã trừ khoản đến hạn và cộng lương của
    ngày đó). Tiền có để trả các khoản của ngày d là số dư cuối ngày d cộng lại các khoản đó và TRỪ lương về ngày d: khoản đến hạn đúng
    ngày lương không được tính bằng lương của chính ngày đó. Khoản trước ngày dự báo đầu tiên trả từ `opening_balance_vnd`.
    """
    dues = []
    salary_by_day: dict[str, int] = {}
    for event in events:
        if event["kind"] == "salary":
            salary_by_day[event["date"]] = salary_by_day.get(event["date"], 0) + event["amount_vnd"]
            continue
        if event["kind"] != "obligation":
            continue
        due = dict(event)
        due["date"] = due.pop("original_due_date", None) or due["date"]
        if due_before_payday(due["date"], payday):
            dues.append(due)
    dues.sort(key=lambda e: (e["date"], e["label"], e["amount_vnd"]))
    daily_totals: dict[str, int] = {}
    for due in dues:
        day = due["date"]
        daily_totals[day] = daily_totals.get(day, 0) + due["amount_vnd"]
    available_by_day = {
        day: end_balances[day] + amount - salary_by_day.get(day, 0)
        for day, amount in daily_totals.items()
        if day in end_balances
    }
    result: dict[str, Any] = {"items": dues}
    first_forecast_day = min(end_balances, default=payday)
    current_balance = opening_balance_vnd
    for due in dues:
        day = due["date"]
        if day < first_forecast_day:
            available = max(current_balance, 0)
        elif day in available_by_day:
            available = max(available_by_day[day], 0)
        else:
            continue
        amount = due["amount_vnd"]
        if available < amount:
            result["first_shortfall"] = {
                "date": day, "label": due["label"], "shortfall_vnd": amount - available
            }
            break
        if day < first_forecast_day:
            current_balance -= amount
        else:
            available_by_day[day] -= amount
    return result
