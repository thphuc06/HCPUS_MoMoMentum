"""Bộ sinh persona tất định theo seed (phase 1: bản tối thiểu).

Đầu vào là **dữ liệu seed** (`specs/<persona>.json`: lương, ngày lương, tỷ lệ chia, số dư hũ cần đạt,
cửa hàng...), đầu ra là hồ sơ + hũ + sổ cái giao dịch để nạp vào Aurora. Dữ liệu persona hợp lệ vì
dự án không có API giao dịch thật (master-plan: "Không hardcode, không giả lập"); nhưng **số dư hũ
không được gắn cứng trong mã sản phẩm**: nó là `target_vnd` trong spec, và bộ sinh dựng sổ cái sao
cho số dư cuối đúng bằng đó (mở đầu + lương chia hũ - chi tiêu = số dư).

Cách dựng sổ cái của một hũ:

1. Mốc đầu: `opening_vnd` (nếu > 0) ở ngày đầu lịch sử, rồi mỗi ngày lương trong lịch sử (từ ngày đầu
   tới trước ngày neo) một dòng `income` = lương x tỷ lệ chia.
2. Tổng chi `T = opening + tổng lương chia - target` phải >= 0. `recent_share` của `T` rơi vào khoảng
   sau ngày lương gần nhất (thói quen chi tiêu dồn về cuối kỳ), phần còn lại chia theo số ngày cho
   các khoảng trước. `recent_share = 1` nghĩa là toàn bộ chi tiêu nằm sau ngày lương gần nhất.
3. Mỗi khoảng sinh vài khoản chi (`expense_count` chia theo tỷ lệ), ngày, giờ, cửa hàng, số tiền lấy
   từ `random.Random` theo seed; số tiền làm tròn 1.000 đ, khoản lớn nhất nhận phần dư để tổng khớp.
4. Số dư chạy của hũ không bao giờ âm (kiểm bằng mô phỏng; spec sai thì `PersonaError`).

Kết quả chỉ dùng "số ngày trước ngày neo" và giờ địa phương; việc ghép với đồng hồ mô phỏng (ngày
neo, offset, UTC) làm ở `materialize`, theo ADR-0003.
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from yofina_core.clock import clock_offset_for

PACKAGE_DIR = Path(__file__).resolve().parent
SPECS_DIR = PACKAGE_DIR / "specs"
ACCOUNTS_FILE = PACKAGE_DIR / "accounts.json"

_ROUND = 1000
_SALARY_TIME = time(6, 0)


class PersonaError(ValueError):
    """Spec persona không hợp lệ hoặc không dựng được sổ cái nhất quán."""


@dataclass(frozen=True)
class JarSeed:
    code: str
    name: str
    color_key: str
    icon_key: str
    split_percent: Decimal
    balance_vnd: int
    sort_order: int


@dataclass(frozen=True)
class TxSeed:
    """Một dòng sổ cái, chưa gắn đồng hồ: `days_ago` ngày trước ngày neo, `local_time` giờ địa phương."""

    days_ago: int
    local_time: time
    kind: str  # income | expense
    jar_code: str
    amount_vnd: int  # có dấu: âm là chi
    merchant: str | None
    note: str | None
    source: str = "seed"


@dataclass(frozen=True)
class PersonaData:
    persona: str
    display_name: str
    monthly_salary_vnd: int
    payday_day: int
    risk_tolerance: str
    history_days: int
    jars: tuple[JarSeed, ...]
    transactions: tuple[TxSeed, ...]


# --- đọc spec và bảng tài khoản ---------------------------------------------------------------
def available_personas(specs_dir: Path = SPECS_DIR) -> list[str]:
    return sorted(p.stem for p in specs_dir.glob("*.json"))


def load_spec(persona: str, specs_dir: Path = SPECS_DIR) -> dict[str, Any]:
    if not persona.isidentifier():
        raise PersonaError(f"Tên persona không hợp lệ: {persona!r}")
    path = specs_dir / f"{persona}.json"
    if not path.is_file():
        raise PersonaError(f"Không có persona {persona!r} (có: {available_personas(specs_dir)})")
    return json.loads(path.read_text(encoding="utf-8"))


def load_accounts(path: Path = ACCOUNTS_FILE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def persona_from_groups(
    groups: Iterable[str], accounts: Mapping[str, Any] | None = None
) -> str | None:
    """Persona của người dùng từ danh sách nhóm Cognito (`persona-<tên>`); không có thì None."""
    accounts = accounts or load_accounts()
    prefix = accounts["group_prefix"]
    known = set(available_personas())
    for g in groups:
        if g.startswith(prefix) and g[len(prefix) :] in known:
            return g[len(prefix) :]
    return None


def parse_groups_claim(value: Any) -> list[str]:
    """Claim `cognito:groups` ở HTTP API là chuỗi dạng `[a b]` (hoặc danh sách thật)."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return [p for p in text.replace(",", " ").split() if p]


# --- sinh ---------------------------------------------------------------------------------------
def _payday(year: int, month: int, day: int) -> date:
    first_next = date(year + (month == 12), month % 12 + 1, 1)
    last = (first_next - timedelta(days=1)).day
    return date(year, month, min(day, last))


def _paydays(start: date, anchor: date, day: int) -> list[date]:
    """Các ngày lương trong [start, anchor) (ngày neo là "hôm nay", chưa tính)."""
    out: list[date] = []
    y, m = start.year, start.month
    while date(y, m, 1) < anchor:
        d = _payday(y, m, day)
        if start <= d < anchor:
            out.append(d)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _round_amount(value: Decimal) -> int:
    return int((value / _ROUND).quantize(Decimal(1), rounding=ROUND_HALF_UP)) * _ROUND


def _split_total(rng: random.Random, total: int, n: int) -> list[int]:
    """Chia `total` (bội của 1.000) thành `n` khoản dương làm tròn 1.000, khoản lớn nhất nhận phần dư."""
    if n <= 0 or total <= 0:
        return []
    n = min(n, total // _ROUND)
    weights = [Decimal(str(rng.uniform(0.4, 1.6))) for _ in range(n)]
    wsum = sum(weights)
    parts = [max(_ROUND, int(total * w / wsum) // _ROUND * _ROUND) for w in weights]
    diff = total - sum(parts)
    parts[parts.index(max(parts))] += diff
    if min(parts) <= 0:
        raise PersonaError("Không chia được tổng chi thành các khoản dương")
    return parts


def _segments(income_days: list[int], start_ago: int, end_ago: int) -> list[tuple[int, int]]:
    """Các khoảng (days_ago_lớn, days_ago_nhỏ) giữa các ngày có tiền vào, theo thứ tự thời gian.

    `days_ago` giảm dần theo thời gian: khoảng đầu là (start_ago .. ngày lương đầu + 1)... Ở đây
    mỗi khoảng bắt đầu đúng ngày có tiền vào (hoặc ngày đầu) và kết thúc trước ngày có tiền vào kế
    tiếp, hoặc tới ngày hôm qua (days_ago = 1)."""
    marks = sorted({start_ago, *income_days}, reverse=True)
    segs: list[tuple[int, int]] = []
    for i, first in enumerate(marks):
        last = marks[i + 1] + 1 if i + 1 < len(marks) else end_ago
        if first >= last:
            segs.append((first, last))
    return segs


def _simulate_non_negative(jar: str, txs: list[TxSeed]) -> None:
    bal = 0
    # thứ tự thời gian: days_ago giảm dần, trong ngày theo giờ
    for t in sorted(txs, key=lambda t: (-t.days_ago, t.local_time)):
        bal += t.amount_vnd
        if bal < 0:
            raise PersonaError(f"Hũ {jar}: số dư chạy âm ({bal}) ở {t.days_ago} ngày trước")


def generate(
    persona: str,
    *,
    anchor: date,
    seed: int | None = None,
    specs_dir: Path = SPECS_DIR,
    spec: Mapping[str, Any] | None = None,
) -> PersonaData:
    """Sinh hồ sơ, hũ và sổ cái của `persona`. Tất định: cùng (persona, seed, anchor) -> cùng kết quả.

    `spec` (tùy chọn) thay cho file spec, dùng để thử spec sai trong test."""
    spec = spec if spec is not None else load_spec(persona, specs_dir)
    seed = spec["seed"] if seed is None else seed
    salary = int(spec["monthly_salary_vnd"])
    payday_day = int(spec["payday_day"])
    history_days = int(spec["history_days"])
    start = anchor - timedelta(days=history_days)
    paydays = _paydays(start, anchor, payday_day)
    income_days = [(anchor - d).days for d in paydays]  # days_ago của mỗi ngày lương
    end_ago = 1  # hôm qua là ngày cuối cùng có giao dịch lịch sử

    split_total = sum(Decimal(str(j["split_percent"])) for j in spec["jars"])
    if split_total != 100:
        raise PersonaError(f"Tỷ lệ chia của {persona} cộng lại {split_total}, phải là 100")

    jars: list[JarSeed] = []
    txs: list[TxSeed] = []
    for order, j in enumerate(spec["jars"]):
        code = j["code"]
        rng = random.Random(f"{seed}:{persona}:{code}")
        pct = Decimal(str(j["split_percent"]))
        share = (Decimal(salary) * pct / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        opening = int(j.get("opening_vnd", 0))
        target = int(j["target_vnd"])
        jar_txs: list[TxSeed] = []
        if opening > 0:
            jar_txs.append(
                TxSeed(history_days, time(5, 0), "income", code, opening, "Số dư đầu kỳ", None)
            )
        for pd, ago in zip(paydays, income_days, strict=True):
            jar_txs.append(
                TxSeed(
                    ago,
                    _SALARY_TIME,
                    "income",
                    code,
                    int(share),
                    "Lương",
                    f"Lương tháng {pd.month}/{pd.year} chia vào hũ {j['name']}",
                )
            )
        total_in = sum(t.amount_vnd for t in jar_txs)
        spend = total_in - target
        if spend < 0:
            raise PersonaError(
                f"Hũ {code}: tiền vào {total_in} nhỏ hơn số dư cần đạt {target}; thêm opening_vnd"
            )
        if spend % _ROUND:
            raise PersonaError(f"Hũ {code}: tổng chi {spend} phải là bội của {_ROUND}")
        if spend and not j.get("merchants"):
            raise PersonaError(f"Hũ {code}: có chi tiêu nhưng không khai merchants")

        if spend:
            segs = _segments(income_days, history_days, end_ago)
            recent_share = Decimal(str(j.get("recent_share", 0.5)))
            last_seg, earlier = segs[-1], segs[:-1]
            recent_total = _round_amount(Decimal(spend) * recent_share) if earlier else spend
            allocations: list[tuple[tuple[int, int], int]] = [(last_seg, recent_total)]
            rest = spend - recent_total
            if earlier and rest:
                days = [s[0] - s[1] + 1 for s in earlier]
                acc = 0
                for i, seg in enumerate(earlier):
                    part = (
                        rest - acc
                        if i == len(earlier) - 1
                        else _round_amount(Decimal(rest) * days[i] / sum(days))
                    )
                    acc += part
                    allocations.append((seg, part))
            n_total = int(j.get("expense_count", 0)) or max(1, spend // 100_000)
            for (first, last), amount in allocations:
                if amount <= 0:
                    continue
                n = max(1, round(n_total * amount / spend))
                for money in _split_total(rng, amount, n):
                    ago = rng.randint(last, first)
                    t = time(rng.randint(7, 21), rng.randint(0, 59))
                    jar_txs.append(
                        TxSeed(
                            ago,
                            t,
                            "expense",
                            code,
                            -money,
                            rng.choice(j["merchants"]),
                            None,
                        )
                    )

        _simulate_non_negative(code, jar_txs)
        final = sum(t.amount_vnd for t in jar_txs)
        if final != target:  # bất biến của bộ sinh
            raise PersonaError(f"Hũ {code}: số dư cuối {final} khác mục tiêu {target}")
        jars.append(
            JarSeed(
                code=code,
                name=j["name"],
                color_key=j["color_key"],
                icon_key=j["icon_key"],
                split_percent=pct,
                balance_vnd=target,
                sort_order=order,
            )
        )
        txs.extend(jar_txs)

    txs.sort(key=lambda t: (-t.days_ago, t.local_time, t.jar_code))
    return PersonaData(
        persona=persona,
        display_name=spec["display_name"],
        monthly_salary_vnd=salary,
        payday_day=payday_day,
        risk_tolerance=spec["risk_tolerance"],
        history_days=history_days,
        jars=tuple(jars),
        transactions=tuple(txs),
    )


# --- ghép với đồng hồ mô phỏng (ADR-0003) -----------------------------------------------------
@dataclass(frozen=True)
class MaterializedTx:
    occurred_at: datetime
    app_date: date
    kind: str
    jar_code: str
    amount_vnd: int
    merchant: str | None
    note: str | None
    source: str


@dataclass(frozen=True)
class Materialized:
    clock_offset_days: int
    app_date: date
    data: PersonaData
    transactions: tuple[MaterializedTx, ...]


def materialize(data: PersonaData, *, anchor: date, now: datetime, tz: tzinfo) -> Materialized:
    """Gắn đồng hồ: offset sao cho ngày mô phỏng = `anchor`; mỗi dòng có `app_date` mô phỏng và
    `occurred_at` thật (UTC) nhất quán với offset (ngày thật = hôm nay thật - days_ago)."""
    offset = clock_offset_for(anchor, now, tz)
    real_today = now.astimezone(tz).date()
    rows: list[MaterializedTx] = []
    for t in data.transactions:
        local = datetime.combine(real_today - timedelta(days=t.days_ago), t.local_time, tzinfo=tz)
        rows.append(
            MaterializedTx(
                occurred_at=local.astimezone(UTC),
                app_date=anchor - timedelta(days=t.days_ago),
                kind=t.kind,
                jar_code=t.jar_code,
                amount_vnd=t.amount_vnd,
                merchant=t.merchant,
                note=t.note,
                source=t.source,
            )
        )
    return Materialized(
        clock_offset_days=offset, app_date=anchor, data=data, transactions=tuple(rows)
    )
