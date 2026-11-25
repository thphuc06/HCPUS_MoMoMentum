"""Đề xuất tỷ lệ chia lương theo số đã khai (bước 3 của onboarding, màn "Chi phí cố định").

Nguồn quy tắc: docs/plan/default-six-jars-rollout.md mục "Bước 3" và "Bước 4"; BR-12, BR-21, BR-45, BR-47, BR-48 ở
docs/ba/02-business-rules.md. Các hàm ở đây THUẦN: nhận lương đã khai, hũ, nghĩa vụ, khoản biết trước và ngày mô phỏng,
không đọc DB, đồng hồ hay cấu hình. Mọi con số mà thẻ đề xuất và bản xem trước `save_jars` hiện đều tính ở đây; giao diện
chỉ vẽ lại.

Quy tắc:

- **Nghĩa vụ**: tỷ lệ cần = tổng nghĩa vụ đang hoạt động do người dùng khai và trả từ hũ Nghĩa vụ, quy về tháng, chia lương
  đã khai, làm tròn LÊN điểm nguyên. Quy về tháng: hằng tháng giữ nguyên, hằng tuần nhân 52/12, hằng năm chia 12. Khoản một
  lần không lặp nên không vào tỷ lệ; nó vẫn vào phần kiểm tra theo ngày.
- **Quỹ dồn**: tỷ lệ cần = tổng (phần còn thiếu của từng khoản / số kỳ lương còn lại trước ngày cần) / lương, làm tròn lên.
  Số dư Quỹ dồn đang có được trừ vào khoản cần sớm nhất trước.
- Chỉ đề xuất khi tỷ lệ cần lệch tỷ lệ đang đặt từ 1 điểm (hoặc có khoản biết trước mới). Phần chênh lấy từ hũ chi không
  thiết yếu theo LOẠI giao dịch (Chi hằng ngày, hũ trộn, trước; rồi hũ như Giải trí), rồi Dự phòng nhưng không xuống dưới sàn
  `buffer_min_split_percent`, rồi hũ để dành khác (mục tiêu, dài hạn xếp sau nghĩa vụ theo BR-65), hũ chi thiết yếu (chỉ nhận
  loại ăn uống, đi lại, hóa đơn) sau cùng (BR-21, BR-54). Phần thừa trả về hũ chi đầu tiên (Chi hằng ngày trước).
- Nghĩa vụ + Quỹ dồn + sàn Dự phòng vượt 100%: không đề xuất tỷ lệ, không gợi ý cắt khoản thiết yếu (BR-21); trả danh sách
  nghĩa vụ theo thứ tự ưu tiên (nhà ở, điện nước, rồi nợ) để giao diện mở lộ trình.
- Mẫu số chỉ là lương đã khai. Lần lương nhận gần nhất lệch số khai quá ngưỡng BR-12 thì hỏi cập nhật lương trước.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from functools import lru_cache
from typing import Any

from yofina_core.clock import next_payday, payday_dates, payday_in_month
from yofina_core.config import Config
from yofina_core.money import format_vnd
from yofina_core.params import ParamsError, TxTypeInfo, normalize_sinking_items, unique_jar_code
from yofina_core.schedule import expand_due_dates
from yofina_core.wallet import (
    DEFAULT_ESSENTIAL_CATEGORIES,
    DEFAULT_SPENDING_JAR,
    SYSTEM_JAR_CODES,
    is_buffer_jar,
    resolve_obligation_pay_jar,
    split_amount,
    transaction_jar,
)
from yofina_ledger import convert

#: Giả định của lộ trình ("Bước 3", chưa có nguồn): Dự phòng không xuống dưới 10% lương khi bù cho nghĩa vụ. Cấu hình
#: `buffer_min_split_percent` (biến `YOFINA_BUFFER_MIN_SPLIT_PERCENT` hoặc SSM) ghi đè.
ASSUMED_BUFFER_MIN_SPLIT_PERCENT = 10
#: "Khoản biết trước trong 12 tháng tới"
KNOWN_ITEM_HORIZON_MONTHS = 12
#: Thứ tự ưu tiên khi nghĩa vụ vượt số chia được: nhà ở, điện nước, rồi nợ, cuối cùng thuê bao (CFPB "prioritizing bills").
OBLIGATION_PRIORITY = {"rent": 0, "bill": 1, "loan": 2, "bnpl": 2, "subscription": 3}
PRIORITY_LIST_MAX = 20
CHECK_ITEMS_MAX = 20
PROPOSAL_STATUSES = (
    "no_salary",
    "salary_mismatch",
    "no_obligation_jar",
    "no_declarations",
    "aligned",
    "proposed",
    "infeasible",
)
ZERO = Decimal(0)
HUNDRED = Decimal(100)


@lru_cache(maxsize=1)
def buffer_min_split_percent() -> int:
    """Sàn tỷ lệ của Dự phòng khi bù cho nghĩa vụ (đọc cấu hình một lần mỗi tiến trình)."""
    value = int(
        Config().get_int("buffer_min_split_percent", default=ASSUMED_BUFFER_MIN_SPLIT_PERCENT)
    )
    if not 0 <= value <= 100:
        raise ValueError("buffer_min_split_percent phải trong khoảng 0..100")
    return value


@lru_cache(maxsize=1)
def essential_categories() -> tuple[str, ...]:
    """Nhóm loại giao dịch thiết yếu (cấu hình `essential_jar_codes`, cùng khóa và mặc định với dự báo), đọc một lần mỗi tiến trình."""
    raw = str(Config().get("essential_jar_codes", default=",".join(DEFAULT_ESSENTIAL_CATEGORIES)))
    return tuple(c.strip() for c in raw.split(",") if c.strip())


def essential_spending_jars(
    jars: Iterable[Mapping[str, Any]],
    tx_types: Mapping[str, TxTypeInfo],
    categories: Iterable[str],
) -> frozenset[str]:
    """Hũ chi tiêu THIẾT YẾU của ví này, theo LOẠI giao dịch (không theo mã hũ): hũ chi mà mọi loại chi được xếp vào nó (bảng tra
    `tx_type_map` qua `transaction_jar`, cùng đường với ghi giao dịch và phân loại) đều thuộc nhóm thiết yếu. Hũ trộn (Chi hằng ngày
    nhận cả giải trí) và hũ chỉ nhận loại không thiết yếu (Giải trí) không thiết yếu: phần chênh lấy từ đó trước (BR-21, BR-54)."""
    rows = list(jars)
    codes = {str(j["code"]) for j in rows}
    spending = {str(j["code"]) for j in rows if j["kind"] == "spending"}
    wanted = set(categories)
    routed: dict[str, set[bool]] = {}
    for tx_type, info in tx_types.items():
        if info.direction != "out" or info.default_jar_code is None:
            continue
        dest = transaction_jar(info.default_jar_code, codes, tx_type=tx_type)
        if dest in spending:
            routed.setdefault(dest, set()).add(info.default_jar_code in wanted)
    return frozenset(code for code, flags in routed.items() if flags == {True})


@dataclass(frozen=True)
class KnownItem:
    """Một khoản biết trước (Tết, học phí, bảo hiểm năm...): tên, số tiền, ngày cần."""

    name: str
    amount_vnd: int
    needed_date: date

    def wire(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "amount_vnd": self.amount_vnd,
            "needed_date": self.needed_date.isoformat(),
        }


# --- tiện ích số ----------------------------------------------------------------------------------------
def months_later(day: date, months: int) -> date:
    """Cùng ngày sau `months` tháng (kẹp ngày cuối tháng)."""
    index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(index, 12)
    return payday_in_month(day.day, year, month + 1)


def monthly_equivalent(amount_vnd: int, cycle: str) -> Fraction:
    """Số tiền quy về một tháng; khoản một lần (`once`) không lặp nên bằng 0."""
    if cycle == "monthly":
        return Fraction(amount_vnd)
    if cycle == "weekly":
        return Fraction(amount_vnd * 52, 12)
    if cycle == "yearly":
        return Fraction(amount_vnd, 12)
    return Fraction(0)


def ceil_percent(part_vnd: Fraction, salary_vnd: int) -> int:
    """Phần trăm của lương, làm tròn LÊN điểm nguyên."""
    return math.ceil(Fraction(part_vnd) * 100 / salary_vnd)


def percent_text(part_vnd: Fraction, salary_vnd: int) -> str:
    """Phần trăm của lương, một chữ số thập phân, dấu phẩy ("35,6"; số tròn thì "35")."""
    ratio = Fraction(part_vnd) * 100 / salary_vnd
    value = (Decimal(ratio.numerator) / Decimal(ratio.denominator)).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )
    text = format(value, "f")
    return text[:-2] if text.endswith(".0") else text.replace(".", ",")


def _num(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def _pct(value: Decimal) -> str:
    return str(_num(value)).replace(".", ",")


def _signed_vnd(delta: int) -> str:
    return ("+" if delta > 0 else "−" if delta < 0 else "±") + format_vnd(abs(delta))


def jar_amounts(salary_vnd: int | None, shares: Sequence[tuple[str, Any]]) -> dict[str, int] | None:
    """Phần lương mỗi kỳ của từng hũ theo `split_amount` (cùng quy tắc `confirm_salary`); None nếu chưa chia được."""
    if not salary_vnd or not shares:
        return None
    try:
        return split_amount(int(salary_vnd), [(code, Decimal(str(p))) for code, p in shares])
    except ValueError:
        return None


def share_line(
    before_pct: Decimal | None,
    after_pct: Decimal,
    before_vnd: int | None,
    after_vnd: int | None,
) -> tuple[str | None, str]:
    """Hai vế "trước" và "sau" của một dòng xem trước: tỷ lệ, tiền mỗi kỳ lương và phần chênh."""
    if after_vnd is None:
        return (f"{_pct(before_pct)}%" if before_pct is not None else None), f"{_pct(after_pct)}%"
    after = f"{_pct(after_pct)}% · {format_vnd(after_vnd)}/kỳ"
    if before_pct is None:
        return None, after
    before = f"{_pct(before_pct)}% · {format_vnd(before_vnd or 0)}/kỳ"
    delta = after_vnd - (before_vnd or 0)
    return before, f"{after} ({_signed_vnd(delta)})" if delta else after


# --- khoản biết trước -----------------------------------------------------------------------------------
def parse_known_items(raw: Any, today: date) -> list[KnownItem]:
    """Khoản biết trước người dùng vừa khai: tên, số tiền, ngày cần SAU hôm nay và trong 12 tháng tới."""
    if raw is None:
        return []
    horizon = months_later(today, KNOWN_ITEM_HORIZON_MONTHS)
    items = []
    for entry in normalize_sinking_items(raw):
        needed = date.fromisoformat(entry["needed_date"])
        if not today < needed <= horizon:
            raise ParamsError("Ngày cần của khoản biết trước phải trong 12 tháng tới.")
        items.append(KnownItem(entry["name"], entry["amount_vnd"], needed))
    return items


def stored_items(jar: Mapping[str, Any] | None) -> list[KnownItem]:
    return [
        KnownItem(str(i["name"]), convert.vnd(i["amount_vnd"]), convert.to_date(i["needed_date"]))  # type: ignore[arg-type]
        for i in ((jar or {}).get("sinking_items") or [])
    ]


def merge_items(existing: Sequence[KnownItem], new: Sequence[KnownItem]) -> list[KnownItem]:
    """Khoản đã lưu giữ nguyên ngày đã cam kết; khoản mới cùng tên chỉ được đổi số tiền."""
    by_name = {i.name.casefold(): i for i in existing}
    out = list(existing)
    for item in new:
        old = by_name.get(item.name.casefold())
        if old is None:
            out.append(item)
            by_name[item.name.casefold()] = item
            continue
        if old.needed_date != item.needed_date:
            raise ParamsError("Ngày đã cam kết của Quỹ dồn được giữ nguyên")
        out[out.index(old)] = KnownItem(old.name, item.amount_vnd, old.needed_date)
    return out


def sinking_plan(
    items: Sequence[KnownItem], *, today: date, payday_day: int, saved_vnd: int
) -> list[dict[str, Any]]:
    """Mỗi khoản: phần còn thiếu (số dư Quỹ dồn trừ vào khoản cần sớm nhất trước), số kỳ lương còn lại trước ngày cần (ngày
    lương sau hôm nay và trước ngày cần) và số cần trích mỗi kỳ (làm tròn lên VND)."""
    left = max(int(saved_vnd), 0)
    plan = []
    for item in sorted(items, key=lambda i: (i.needed_date, i.name.casefold())):
        used = min(left, item.amount_vnd)
        left -= used
        remaining = item.amount_vnd - used
        paydays = len(payday_dates(payday_day, today, item.needed_date - timedelta(days=1)))
        row: dict[str, Any] = {
            **item.wire(),
            "remaining_vnd": remaining,
            "paydays": paydays,
        }
        if paydays and remaining:
            row["per_payday_vnd"] = -(-remaining // paydays)
        plan.append(row)
    return plan


def sinking_need(plan: Iterable[Mapping[str, Any]]) -> Fraction:
    """Số cần trích mỗi kỳ lương cho cả Quỹ dồn (chưa làm tròn); khoản không còn kỳ lương nào thì không tính được."""
    return sum(
        (Fraction(r["remaining_vnd"], r["paydays"]) for r in plan if r["paydays"] and r["remaining_vnd"]),
        Fraction(0),
    )


# --- nghĩa vụ -------------------------------------------------------------------------------------------
def _pairs(jars: Iterable[Mapping[str, Any]]) -> list[tuple[str, str]]:
    return [(str(j["code"]), str(j["kind"])) for j in jars]


def _active(ob: Mapping[str, Any]) -> bool:
    return ob.get("status", "active") == "active"


def paid_from(
    obligations: Iterable[Mapping[str, Any]], jars: Sequence[Mapping[str, Any]], jar_code: str
) -> list[Mapping[str, Any]]:
    """Nghĩa vụ đang hoạt động trả từ `jar_code` (nguồn đã lưu nếu còn hợp lệ, không thì hũ Nghĩa vụ chung)."""
    pairs = _pairs(jars)
    return [
        o
        for o in obligations
        if _active(o) and resolve_obligation_pay_jar(pairs, saved=o.get("pay_jar_code")) == jar_code
    ]


def declared_need(
    obligations: Iterable[Mapping[str, Any]], jars: Sequence[Mapping[str, Any]], jar_code: str
) -> tuple[list[Mapping[str, Any]], Fraction]:
    """Nghĩa vụ người dùng khai (không gồm Trả sau tự sinh) trả từ `jar_code`, và tổng quy về tháng."""
    declared = [
        o for o in paid_from(obligations, jars, jar_code) if o.get("source", "declared") == "declared"
    ]
    total = sum(
        (monthly_equivalent(convert.vnd(o["amount_vnd"]), str(o["cycle"])) for o in declared),
        Fraction(0),
    )
    return declared, total


def obligation_reason(monthly_vnd: Fraction, salary_vnd: int) -> str:
    return (
        f"Nghĩa vụ đã khai {format_vnd(math.ceil(monthly_vnd))}/tháng = "
        f"{percent_text(monthly_vnd, salary_vnd)}% lương {format_vnd(salary_vnd)}"
    )


def sinking_reason(plan: Sequence[Mapping[str, Any]], salary_vnd: int) -> str:
    per = sum(int(r.get("per_payday_vnd", 0)) for r in plan)
    return (
        f"Khoản biết trước cần {format_vnd(per)}/kỳ lương = "
        f"{percent_text(sinking_need(plan), salary_vnd)}% lương"
    )


def priority_obligations(obligations: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Nghĩa vụ đang hoạt động theo thứ tự ưu tiên: nhà ở, điện nước, rồi nợ; thiết yếu trước, hạn sớm trước."""
    rows = sorted(
        (o for o in obligations if _active(o)),
        key=lambda o: (
            OBLIGATION_PRIORITY.get(str(o["kind"]), len(OBLIGATION_PRIORITY)),
            not bool(o.get("is_essential")),
            convert.to_date(o["due_date"]),
            str(o["name"]),
        ),
    )
    out = []
    for o in rows[:PRIORITY_LIST_MAX]:
        amount = convert.vnd(o["amount_vnd"])
        monthly = monthly_equivalent(amount, str(o["cycle"]))
        out.append(
            {
                "id": str(o["id"]),
                "name": str(o["name"])[:80],
                "kind": str(o["kind"]),
                "cycle": str(o["cycle"]),
                "amount_vnd": amount,
                "monthly_vnd": math.ceil(monthly) if monthly else amount,
                "is_essential": bool(o.get("is_essential")),
            }
        )
    return out


# --- kiểm tra theo ngày ---------------------------------------------------------------------------------
def obligation_dues(
    obligations: Iterable[Mapping[str, Any]],
    jars: Sequence[Mapping[str, Any]],
    jar_code: str,
    *,
    first: date,
    through: date,
) -> list[tuple[date, str, int]]:
    """Các lần đến hạn trong [first, through] của nghĩa vụ trả từ `jar_code` (quá hạn tính vào `first`)."""
    out = []
    for o in paid_from(obligations, jars, jar_code):
        due = convert.to_date(o["due_date"])
        assert due is not None
        due_day = int(o["due_day"]) if o.get("due_day") is not None else None
        amount = convert.vnd(o["amount_vnd"])
        for d in expand_due_dates(due, str(o["cycle"]), due_day, first=first, through=through):
            out.append((d, str(o["name"])[:60], amount))
    return out


def period_checks(
    *,
    today: date,
    payday_day: int,
    salary_vnd: int,
    shares: Sequence[tuple[str, Decimal]],
    jar_code: str,
    jar_name: str,
    balance_vnd: int,
    dues: Sequence[tuple[date, str, int]],
    pending_salary_vnd: int | None = None,
) -> list[dict[str, Any]]:
    """Kỳ lương hiện tại và kỳ kế tiếp: cộng các khoản đến hạn TRƯỚC ngày lương rồi so với số dư cộng phần chia.

    Kỳ hiện tại: số dư hôm nay, cộng phần của lương đang chờ chia (nếu có, theo tỷ lệ `shares`). Kỳ kế tiếp: phần còn lại
    sau kỳ hiện tại (không âm) cộng phần lương của ngày lương kế tiếp. Thiếu thì nêu khoản đầu tiên bị thiếu và số thiếu.
    """
    p1 = next_payday(payday_day, today)
    p2 = next_payday(payday_day, p1)
    part = (jar_amounts(salary_vnd, shares) or {}).get(jar_code, 0)
    pending = (jar_amounts(pending_salary_vnd, shares) or {}).get(jar_code, 0)
    carry = int(balance_vnd) + pending
    out = []
    for start, end, income in ((today, p1, 0), (p1, p2, part)):
        available = carry + income
        window = sorted((d for d in dues if start <= d[0] < end), key=lambda d: (d[0], d[1]))
        total = sum(a for _, _, a in window)
        row: dict[str, Any] = {
            "jar_code": jar_code,
            "jar_name": jar_name,
            "payday": end.isoformat(),
            "due_vnd": total,
            "available_vnd": available,
            "items": [
                {"label": label, "date": d.isoformat(), "amount_vnd": amount}
                for d, label, amount in window[:CHECK_ITEMS_MAX]
            ],
        }
        running = 0
        for d, label, amount in window:
            running += amount
            if running > available:
                row["shortfall"] = {
                    "label": label,
                    "date": d.isoformat(),
                    "shortfall_vnd": min(amount, running - max(available, 0)),
                }
                break
        out.append(row)
        carry = max(available - total, 0)
    return out


# --- cân lại tỷ lệ --------------------------------------------------------------------------------------
def rebalance(
    shares: Mapping[str, Decimal],
    targets: Mapping[str, Decimal],
    sources: Sequence[tuple[str, Decimal]],
    refund_to: str | None = None,
) -> dict[str, Decimal] | None:
    """Đặt `targets`, lấy phần thiếu từ `sources` theo thứ tự (mỗi nguồn không xuống dưới sàn của nó) hoặc trả phần thừa về
    `refund_to` (vắng thì nguồn đầu tiên). None nếu các nguồn không đủ."""
    out = dict(shares)
    need = ZERO
    for code, target in targets.items():
        need += target - out.get(code, ZERO)
        out[code] = target
    if need < 0:
        if refund_to is None and not sources:
            return None
        out[refund_to or sources[0][0]] += -need
        return out
    for code, floor in sources:
        if need <= 0:
            break
        take = min(need, max(out[code] - floor, ZERO))
        out[code] -= take
        need -= take
    return out if need <= 0 else None


def editable_jar(jar: Mapping[str, Any], split: Decimal) -> dict[str, Any]:
    """Một hũ theo dạng tham số `save_jars`, giữ mục đích, mục tiêu và khoản Quỹ dồn đã có."""
    out: dict[str, Any] = {
        "code": jar["code"],
        "name": jar["name"],
        "color_key": jar["color_key"],
        "icon_key": jar["icon_key"],
        "kind": jar["kind"],
        "split_percent": _num(split),
    }
    if jar.get("purpose"):
        out["purpose"] = jar["purpose"]
    if jar.get("goal_vnd") is not None:
        out["goal_vnd"] = convert.vnd(jar["goal_vnd"])
    if jar.get("goal_date") is not None:
        out["goal_date"] = convert.to_date(jar["goal_date"]).isoformat()  # type: ignore[union-attr]
    if jar.get("sinking_items"):
        out["sinking_items"] = [i.wire() for i in stored_items(jar)]
    return out


def _salary_check(
    events: Iterable[Mapping[str, Any]], salary_vnd: int, threshold: Decimal
) -> dict[str, Any] | None:
    """Lần lương nhận gần nhất lệch lương đã khai quá ngưỡng BR-12 (độ lệch = (nhận − khai) / khai × 100)."""
    latest = max(
        events,
        key=lambda e: (convert.to_date(e["received_on"]), convert.to_date(e["period_date"])),
        default=None,
    )
    if latest is None:
        return None
    received = convert.vnd(latest["amount_vnd"])
    deviation = ((Decimal(received) - salary_vnd) / salary_vnd * 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    if abs(deviation) <= threshold:
        return None
    return {
        "salary_event_id": str(latest["id"]),
        "received_vnd": received,
        "declared_vnd": salary_vnd,
        "deviation_percent": float(deviation),
    }


def build_proposal(
    *,
    today: date,
    salary_vnd: int | None,
    payday_day: int | None,
    jars: Sequence[Mapping[str, Any]],
    obligations: Sequence[Mapping[str, Any]],
    known_items: Sequence[KnownItem],
    salary_events: Sequence[Mapping[str, Any]],
    deviation_ask_percent: Decimal,
    buffer_min_percent: int,
    sinking_template: Mapping[str, Any] | None,
    essential_jars: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Đề xuất tỷ lệ chia lương (xem docstring của module). `jars` là hũ người dùng theo thứ tự hiển thị; `essential_jars` là hũ
    chi thiết yếu theo loại giao dịch (`essential_spending_jars`), vắng thì mọi hũ chi coi như không thiết yếu."""
    shares = {str(j["code"]): Decimal(str(j["split_percent"])) for j in jars}
    by_code = {str(j["code"]): j for j in jars}

    def rows(after: Mapping[str, Decimal], extra: Sequence[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
        before_amt = jar_amounts(salary_vnd, list(shares.items())) or {}
        after_amt = jar_amounts(salary_vnd, list(after.items())) or {}
        out = []
        for j in [*jars, *extra]:
            code = str(j["code"])
            row: dict[str, Any] = {
                "code": code,
                "name": j["name"],
                "kind": j["kind"],
                "split_before": _num(shares.get(code, ZERO)),
                "split_after": _num(after.get(code, shares.get(code, ZERO))),
            }
            if j.get("purpose"):
                row["purpose"] = j["purpose"]
            if before_amt or after_amt:
                row["amount_before_vnd"] = before_amt.get(code, 0)
                row["amount_after_vnd"] = after_amt.get(code, row["amount_before_vnd"])
                row["delta_vnd"] = row["amount_after_vnd"] - row["amount_before_vnd"]
            out.append(row)
        return out

    if not salary_vnd or not payday_day:
        return {"status": "no_salary", "jars": rows(shares)}
    base: dict[str, Any] = {"salary_vnd": int(salary_vnd)}
    mismatch = _salary_check(salary_events, int(salary_vnd), deviation_ask_percent)
    if mismatch is not None:
        return {**base, "status": "salary_mismatch", "salary_check": mismatch, "jars": rows(shares)}
    ob_jar = resolve_obligation_pay_jar(_pairs(jars))
    if ob_jar is None:
        return {**base, "status": "no_obligation_jar", "jars": rows(shares)}
    pending = [e for e in salary_events if e.get("status") == "pending"]
    pending_vnd = convert.vnd(pending[0]["amount_vnd"]) if pending else None
    if pending:
        base["pending_salary"] = {
            "salary_event_id": str(pending[0]["id"]),
            "amount_vnd": pending_vnd,
        }

    declared, monthly = declared_need(obligations, jars, ob_jar)
    base["obligation_basis"] = "declared" if declared else "template"
    if declared:
        base["obligations_monthly_vnd"] = math.ceil(monthly)
    if not declared and not known_items:
        return {**base, "status": "no_declarations", "jars": rows(shares)}

    reasons: list[dict[str, str]] = []
    targets: dict[str, Decimal] = {}
    o_need = shares[ob_jar]
    if declared:
        o_need = Decimal(ceil_percent(monthly, int(salary_vnd)))
        reasons.append({"jar_code": ob_jar, "text": obligation_reason(monthly, int(salary_vnd))})
        if abs(o_need - shares[ob_jar]) >= 1:
            targets[ob_jar] = o_need

    sinking = next((j for j in jars if j["kind"] == "saving" and j.get("purpose") == "sinking"), None)
    new_jar: dict[str, Any] | None = None
    items_changed = False
    s_need = shares[str(sinking["code"])] if sinking else ZERO
    sink_code = str(sinking["code"]) if sinking else ""
    merged: list[KnownItem] = []
    plan: list[dict[str, Any]] = []
    if known_items:
        existing = stored_items(sinking)
        merged = merge_items(existing, known_items)
        items_changed = merged != existing
        saved = convert.vnd(sinking["balance_vnd"]) if sinking else 0
        plan = sinking_plan(merged, today=today, payday_day=int(payday_day), saved_vnd=saved)
        s_need = Decimal(ceil_percent(sinking_need(plan), int(salary_vnd)))
        base["sinking_items"] = plan
        if sinking is None:
            if sinking_template is None:
                raise ParamsError("Chưa có mẫu hũ Quỹ dồn để tạo.")
            taken = set(shares) | set(SYSTEM_JAR_CODES.values())
            code = str(sinking_template["code"])
            sink_code = code if code not in taken else unique_jar_code(str(sinking_template["name"]), taken)
            new_jar = {
                "code": sink_code,
                "name": sinking_template["name"],
                "color_key": sinking_template["color_key"],
                "icon_key": sinking_template["icon_key"],
                "kind": "saving",
                "purpose": "sinking",
                "sinking_items": [i.wire() for i in merged],
            }
            targets[sink_code] = s_need
        elif items_changed or abs(s_need - shares[sink_code]) >= 1:
            targets[sink_code] = s_need
        reasons.append({"jar_code": sink_code, "text": sinking_reason(plan, int(salary_vnd))})

    buffer = next((j for j in jars if j["kind"] == "saving" and j.get("purpose") == "buffer"), None) or next(
        (j for j in jars if is_buffer_jar(str(j["kind"]), j.get("purpose"), j.get("goal_vnd"))), None
    )
    floor = min(Decimal(buffer_min_percent), shares[str(buffer["code"])]) if buffer else ZERO
    required = o_need + s_need + floor
    if required > HUNDRED:
        return {
            **base,
            "status": "infeasible",
            "required_percent": _num(required),
            "reasons": reasons,
            "priority_obligations": priority_obligations(obligations),
            "jars": rows(shares),
        }

    spending = sorted(
        (j for j in jars if j["kind"] == "spending"), key=lambda j: j["code"] != DEFAULT_SPENDING_JAR
    )
    # BR-21, BR-54: không cắt khoản thiết yếu trước. Lấy từ hũ chi không thiết yếu (theo loại giao dịch, `essential_spending_jars`;
    # Chi hằng ngày là hũ trộn nên đứng đầu như trước), rồi Dự phòng xuống tới sàn, rồi hũ để dành khác, hũ chi thiết yếu sau cùng.
    essential_codes = essential_jars or frozenset()
    flexible = [(str(j["code"]), ZERO) for j in spending if str(j["code"]) not in essential_codes]
    sources = list(flexible)
    if buffer is not None:
        sources.append((str(buffer["code"]), floor))
    sources += [
        (str(j["code"]), ZERO)
        for j in jars
        if j["kind"] == "saving" and j is not buffer and j.get("purpose") != "sinking"
    ]
    sources += [(str(j["code"]), ZERO) for j in spending if str(j["code"]) in essential_codes]
    sources = [s for s in sources if s[0] not in targets]
    # phần thừa trả về hũ chi đầu tiên (Chi hằng ngày trước) như trước
    refund_to = next((str(j["code"]) for j in spending if str(j["code"]) not in targets), None)
    current = dict(shares)
    if new_jar is not None:
        current[str(new_jar["code"])] = ZERO
    after = rebalance(current, targets, sources, refund_to) if targets else current
    if after is None:
        return {
            **base,
            "status": "infeasible",
            "required_percent": _num(required),
            "reasons": reasons,
            "priority_obligations": priority_obligations(obligations),
            "jars": rows(shares),
        }

    extra = [new_jar] if new_jar is not None else []
    order = [*jars, *extra]
    after_shares = [(str(j["code"]), after[str(j["code"])]) for j in order]
    p2 = next_payday(int(payday_day), next_payday(int(payday_day), today))
    checks = period_checks(
        today=today,
        payday_day=int(payday_day),
        salary_vnd=int(salary_vnd),
        shares=after_shares,
        jar_code=ob_jar,
        jar_name=str(by_code[ob_jar]["name"]),
        balance_vnd=convert.vnd(by_code[ob_jar]["balance_vnd"]),
        dues=obligation_dues(obligations, order, ob_jar, first=today, through=p2 - timedelta(days=1)),
        pending_salary_vnd=pending_vnd,
    )
    if plan:
        sink_name = str((sinking or new_jar or {}).get("name", ""))
        checks += period_checks(
            today=today,
            payday_day=int(payday_day),
            salary_vnd=int(salary_vnd),
            shares=after_shares,
            jar_code=sink_code,
            jar_name=sink_name,
            balance_vnd=convert.vnd(sinking["balance_vnd"]) if sinking else 0,
            dues=[(date.fromisoformat(r["needed_date"]), r["name"], r["amount_vnd"]) for r in plan],
            pending_salary_vnd=pending_vnd,
        )
    status = "proposed" if targets or items_changed else "aligned"
    out = {**base, "status": status, "reasons": reasons, "checks": checks, "jars": rows(after, extra)}
    if status == "proposed":
        params_jars = []
        for j in order:
            code = str(j["code"])
            if new_jar is not None and code == new_jar["code"]:
                params_jars.append({**new_jar, "split_percent": _num(after[code])})
                continue
            edited = editable_jar(j, after[code])
            if code == sink_code and known_items:
                edited["sinking_items"] = [i.wire() for i in merged]
            params_jars.append(edited)
        out["params"] = {"jars": params_jars}
    return out
