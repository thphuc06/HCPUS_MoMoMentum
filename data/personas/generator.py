"""Bộ sinh persona tất định theo seed (phase 2: ví đầy đủ).

Đầu vào là **dữ liệu seed** (`specs/<persona>.json`: lương, ngày lương, tỷ lệ chia, số dư hũ cần đạt, nhịp chi tiêu, người
nhận, nghĩa vụ, hạn mức Trả sau, hai hũ hệ thống), đầu ra là hồ sơ, hũ, người nhận, nghĩa vụ và sổ cái giao dịch để nạp vào
Aurora. Dữ liệu persona hợp lệ vì dự án không có API giao dịch thật (master-plan: "Không hardcode, không giả lập"); nhưng
**số dư hũ không được gắn cứng trong mã sản phẩm**: nó là `target_vnd` trong spec, và bộ sinh dựng sổ cái sao cho số dư cuối
đúng bằng đó (mở đầu + lương chia - chi tiêu = số dư). Mọi tham số sinh (mức chi, nhịp cuối tuần và đầu kỳ lương, độ phân tán
số tiền) là cấu hình trong spec: chỉnh số ở đó, không sửa mã.

Cách dựng sổ cái (đúng cách ví thật ghi, nên các hàm dự báo đọc được cùng dữ liệu như người dùng thật):

1. Mỗi ngày lương trong lịch sử: một dòng `income` (`tx_type salary`) vào hũ Tiền vào khác, rồi dòng chuyển (`salary_split`,
   cùng `transfer_id`) trừ Tiền vào khác và cộng các hũ theo `split_amount` (cùng quy tắc `confirm_salary`); một sự kiện lương
   `confirmed` ghi lại phép chia.
2. Số dư đầu kỳ (`opening_vnd`) là một dòng chuyển một phía vào hũ ở ngày đầu lịch sử.
3. Khoản trả nghĩa vụ định kỳ trong lịch sử (`paid_in_history`) là dòng chi gắn `obligation_id`, ngày đúng hạn của từng tháng;
   khoản chưa tới hạn nằm trong bảng `obligations`. Dự báo không đếm hai lần: lịch sử chi tiêu theo ngày bỏ qua dòng gắn nghĩa vụ.
4. Chi tiêu còn lại của hũ `T = đầu kỳ + lương chia - số dư cần đạt - tổng khoản trả nghĩa vụ` rơi vào khoảng sau ngày lương
   gần nhất theo `recent_share` (thói quen chi tiêu dồn về cuối kỳ), phần còn lại chia theo số ngày cho các khoảng trước.
5. Trong mỗi khoảng, ngày chi được chọn theo trọng số nhịp (`weekend_multiplier` cho thứ bảy và chủ nhật, `early_period_multiplier`
   cho `early_period_days` ngày đầu kỳ lương), số tiền theo phân phối lognormal (`amount_sigma`), tối đa `max_per_day` khoản mỗi ngày;
   tổng làm tròn 1.000 đ, khoản lớn nhất nhận phần dư. Mọi giá trị ngẫu nhiên lấy từ `random.Random` theo seed.
6. Hũ hệ thống: "Tiền vào khác" nhận các dòng `income` khác lương; "Chưa phân loại" nhận khoản CHI chưa xếp hũ (số dư âm). Mua bằng
   Trả sau là dòng chi `funding_source credit` (không đổi số dư hũ) cộng một nghĩa vụ `bnpl` tự sinh.
7. Số dư chạy của mọi hũ trừ "Chưa phân loại" không bao giờ âm (kiểm bằng mô phỏng; spec sai thì `PersonaError`).

8. Thu nhập ngoài ví (tùy chọn, F6): spec khai `external_income_monthly_vnd` thì mỗi tháng trong lịch sử có một dòng `income`
   `funding_source external` (không hũ, không đổi số dư hũ nào) vào ngày `external_income.day`: tiền về tài khoản ngân hàng khác
   của người dùng. Nó chỉ vào mẫu số của độ phủ dữ liệu (xem README "Độ phủ dữ liệu"); spec không khai thì bộ sinh cho đúng
   kết quả như trước (ba persona cũ không đổi một byte, `tests/unit/persona_digest.py` khóa điều này).

9. Chuyển hũ trong lịch sử (tùy chọn): spec khai `jar_transfers` (`days_ago`, `from`, `to`, `amount_vnd`, `note`) thì mỗi khoản là
   hai dòng `transfer` (`tx_type jar_transfer`, cùng `transfer_id`) lúc 06:30, sau dòng chia lương và trước mọi khoản chi trong
   ngày: âm ở hũ nguồn, dương ở hũ đích, đúng như người dùng bấm "Chuyển hũ". Tiền chuyển vào được tính vào tiền vào của hũ đích
   ở bước 4 (nên hũ đích chi được nhiều hơn phần lương chia mà vẫn về đúng số dư cần đạt), tiền chuyển đi trừ khỏi hũ nguồn.
   Spec không khai thì không có dòng nào.

10. Hũ chỉ ví demo có (tùy chọn, issue #39): spec khai `demo_jars` (mỗi hũ: `code`, `split_from` là mã hũ demo -> số điểm % lấy
   sang, cộng các khóa của một hũ thường: `opening_vnd`, `target_vnd`, `expense_count`, `recent_share`, `rhythm`, `merchants`) thì bộ
   sinh dựng dòng của riêng hũ đó (số dư đầu kỳ, khoản chi) vào `PersonaData.demo_jars` bằng `random.Random` riêng. Ví persona
   (`jars`, `transactions`, `materialize`) không đổi một byte; `personas.six_jars.apply_demo_layout` mới gộp hũ này vào ví demo.

Kết quả chỉ dùng "số ngày trước ngày neo" và giờ địa phương; việc ghép với đồng hồ mô phỏng (ngày neo, offset, UTC) và dựng id
làm ở `materialize`, theo ADR-0003.
"""

from __future__ import annotations

import json
import math
import random
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from yofina_core.clock import clock_offset_for, latest_payday, payday_in_month
from yofina_core.schedule import bnpl_due_date, first_due_from_day
from yofina_core.wallet import (
    OTHER_INCOME_JAR_CODE,
    UNCLASSIFIED_JAR_CODE,
    default_obligation_jar,
    split_amount,
)

PACKAGE_DIR = Path(__file__).resolve().parent
SPECS_DIR = PACKAGE_DIR / "specs"
ACCOUNTS_FILE = PACKAGE_DIR / "accounts.json"

_ROUND = 1000
_SALARY_TIME = time(6, 0)
_SPLIT_TIME = time(6, 1)
_OPENING_TIME = time(5, 0)
_OBLIGATION_TIME = time(9, 0)
_MOVE_TIME = time(6, 30)
ID_NAMESPACE = uuid.UUID(
    "5d1f0b64-2f0e-4a53-9a2c-7a1d4a3c0f11"
)  # định danh dòng seed theo (người dùng, persona, khóa)

#: nhịp mặc định khi spec không khai (spec nào cũng ghi đè được ở `rhythm_defaults` hoặc `rhythm` của từng hũ)
BUILTIN_RHYTHM = {
    "weekend_multiplier": 1.0,
    "early_period_multiplier": 1.0,
    "early_period_days": 14,
    "amount_sigma": 0.5,
    "max_per_day": 3,
}


class PersonaError(ValueError):
    """Spec persona không hợp lệ hoặc không dựng được sổ cái nhất quán."""


@dataclass(frozen=True)
class JarSeed:
    code: str
    name: str
    color_key: str
    icon_key: str
    kind: str
    split_percent: Decimal
    balance_vnd: int
    sort_order: int
    goal_vnd: int | None = None
    goal_date: date | None = None


@dataclass(frozen=True)
class PayeeSeed:
    name: str
    account_hint: str | None
    is_favorite: bool
    used_days_ago: int | None


@dataclass(frozen=True)
class ObligationSeed:
    key: str
    kind: str
    name: str
    amount_vnd: int
    amount_min_vnd: int | None
    amount_max_vnd: int | None
    fee_vnd: int
    cycle: str
    due_day: int
    pay_jar: str | None
    is_essential: bool


@dataclass(frozen=True)
class TxSeed:
    """Một dòng sổ cái, chưa gắn đồng hồ: `days_ago` ngày trước ngày neo, `local_time` giờ địa phương."""

    key: str
    days_ago: int
    local_time: time
    kind: str  # income | expense | transfer
    jar_code: str | None  # None chỉ với thu nhập ngoài ví (funding_source external)
    amount_vnd: int  # có dấu: âm là ra khỏi hũ
    merchant: str | None
    note: str | None
    tx_type: str
    source: str = "seed"
    funding_source: str = "jar"
    payee: str | None = None
    obligation_key: str | None = None
    transfer_key: str | None = None
    needs_review: bool = False
    classified_by: str | None = None


@dataclass(frozen=True)
class SalaryEventSeed:
    days_ago: int
    amount_vnd: int
    transaction_key: str
    split: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class DemoJarSeed:
    """Hũ chỉ ví demo có (spec `demo_jars`, issue #39): hũ Chi hằng ngày cạnh các hũ tự thêm. Bộ sinh dựng sẵn dòng của riêng hũ này
    (số dư đầu kỳ, khoản chi) bằng dòng ngẫu nhiên riêng; `personas.six_jars.apply_demo_layout` thêm dòng chia lương mỗi kỳ
    (`split_line_vnd`) và bớt đúng phần đó ở hũ nguồn (`split_from`: mã hũ demo, số điểm %, số tiền mỗi kỳ). Ví persona (`jars`,
    `transactions`, `materialize`) không có hũ này."""

    code: str
    split_from: tuple[tuple[str, Decimal, int], ...]
    opening_vnd: int
    target_vnd: int
    transactions: tuple[TxSeed, ...]

    @property
    def split_percent(self) -> Decimal:
        return sum((pts for _, pts, _ in self.split_from), Decimal(0))

    @property
    def split_line_vnd(self) -> int:
        return sum(amount for _, _, amount in self.split_from)


@dataclass(frozen=True)
class PersonaData:
    persona: str
    display_name: str
    monthly_salary_vnd: int
    payday_day: int
    risk_tolerance: str
    history_days: int
    anchor: date
    jars: tuple[JarSeed, ...]
    transactions: tuple[TxSeed, ...]
    payees: tuple[PayeeSeed, ...] = ()
    obligations: tuple[ObligationSeed, ...] = ()
    salary_events: tuple[SalaryEventSeed, ...] = ()
    credit_limit_vnd: int | None = None
    credit_due_day: int | None = None
    bnpl_principal_vnd: int = 0
    #: số dư của hai hũ hệ thống theo mã (Tiền vào khác, Chưa phân loại): tổng các dòng của chúng
    system_balances: Mapping[str, int] = field(default_factory=dict)
    #: có nạp sự kiện lương `confirmed` của các kỳ lương trong lịch sử không (spec `seed_salary_events`, mặc định không)
    seed_salary_events: bool = False
    #: thu nhập hằng tháng về tài khoản ngân hàng khác (spec `external_income_monthly_vnd`); None là không khai (ba persona cũ)
    external_income_monthly_vnd: int | None = None
    #: hũ chỉ ví demo có (spec `demo_jars`), chưa gộp vào ví; `apply_demo_layout` gộp. Ví persona bỏ qua trường này.
    demo_jars: tuple[DemoJarSeed, ...] = ()


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
def _paydays(start: date, anchor: date, day: int) -> list[date]:
    """Các ngày lương trong [start, anchor) (ngày neo là "hôm nay", chưa tính)."""
    out: list[date] = []
    y, m = start.year, start.month
    while date(y, m, 1) < anchor:
        d = payday_in_month(day, y, m)
        if start <= d < anchor:
            out.append(d)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _round_amount(value: Decimal) -> int:
    return int((value / _ROUND).quantize(Decimal(1), rounding=ROUND_HALF_UP)) * _ROUND


def _rhythm(spec: Mapping[str, Any], jar: Mapping[str, Any]) -> dict[str, float]:
    out = dict(BUILTIN_RHYTHM)
    out.update(spec.get("rhythm_defaults", {}))
    out.update(jar.get("rhythm", {}))
    return out


def _split_total(rng: random.Random, total: int, n: int, sigma: float) -> list[int]:
    """Chia `total` (bội của 1.000) thành `n` khoản dương làm tròn 1.000: trọng số lognormal(0, sigma), khoản lớn nhất
    nhận phần dư."""
    if n <= 0 or total <= 0:
        return []
    n = min(n, total // _ROUND)
    weights = [Decimal(str(math.exp(rng.gauss(0, sigma)))) for _ in range(n)]
    wsum = sum(weights)
    parts = [max(_ROUND, int(total * w / wsum) // _ROUND * _ROUND) for w in weights]
    diff = total - sum(parts)
    parts[parts.index(max(parts))] += diff
    if min(parts) <= 0:
        raise PersonaError("Không chia được tổng chi thành các khoản dương")
    return parts


def _segments(income_days: list[int], start_ago: int, end_ago: int) -> list[tuple[int, int]]:
    """Các khoảng (days_ago_lớn, days_ago_nhỏ) giữa các ngày có tiền vào, theo thứ tự thời gian: mỗi khoảng bắt đầu đúng
    ngày có tiền vào (hoặc ngày đầu) và kết thúc trước ngày có tiền vào kế tiếp, hoặc tới hôm qua (days_ago = 1)."""
    marks = sorted({start_ago, *income_days}, reverse=True)
    segs: list[tuple[int, int]] = []
    for i, first in enumerate(marks):
        last = marks[i + 1] + 1 if i + 1 < len(marks) else end_ago
        if first >= last:
            segs.append((first, last))
    return segs


def _day_weights(
    days_ago: list[int], anchor: date, payday_day: int, rhythm: Mapping[str, float]
) -> list[float]:
    """Trọng số chọn ngày chi: cuối tuần và đầu kỳ lương đông hơn (nhịp mà mô hình dự báo theo lịch dùng)."""
    out: list[float] = []
    for ago in days_ago:
        day = anchor - timedelta(days=ago)
        w = 1.0
        if day.weekday() >= 5:
            w *= float(rhythm["weekend_multiplier"])
        if (day - latest_payday(payday_day, day)).days < int(rhythm["early_period_days"]):
            w *= float(rhythm["early_period_multiplier"])
        out.append(max(w, 1e-6))
    return out


def _pick_days(
    rng: random.Random, days_ago: list[int], weights: list[float], n: int, cap: int
) -> list[int]:
    """Phân `n` khoản chi vào các ngày theo trọng số nhịp, mỗi ngày tối đa `cap` khoản.

    Hạn ngạch kỳ vọng của một ngày là `n * w / tổng w`; lấy phần nguyên rồi phát các khoản còn lại theo phần lẻ cộng nhiễu nhỏ
    từ `rng` (tất định theo seed). Cách này giữ nhịp cuối tuần và đầu kỳ lương RÕ (không bị nhiễu của lấy mẫu độc lập)
    nhưng vẫn không trùng lặp giữa các seed."""
    capacity = len(days_ago) * cap
    n = min(n, capacity)
    total = sum(weights)
    quota = [n * w / total for w in weights]
    counts = [min(int(q), cap) for q in quota]
    left = n - sum(counts)
    order = sorted(
        range(len(days_ago)),
        key=lambda i: -((quota[i] - int(quota[i])) + rng.uniform(0, 0.35)),
    )
    while left > 0:
        progressed = False
        for i in order:
            if left == 0:
                break
            if counts[i] < cap:
                counts[i] += 1
                left -= 1
                progressed = True
        if not progressed:
            break
    return [ago for ago, c in zip(days_ago, counts, strict=True) for _ in range(c)]


def _simulate_non_negative(jar: str, txs: list[TxSeed]) -> None:
    bal = 0
    # thứ tự thời gian: days_ago giảm dần, trong ngày theo giờ
    for t in sorted(txs, key=lambda t: (-t.days_ago, t.local_time)):
        if t.funding_source != "jar":
            continue
        bal += t.amount_vnd
        if bal < 0:
            raise PersonaError(f"Hũ {jar}: số dư chạy âm ({bal}) ở {t.days_ago} ngày trước")


def _merchants(jar: Mapping[str, Any]) -> list[tuple[str, str, float]]:
    """Danh sách (tên, tx_type, trọng số) của hũ; `merchants` có thể là chuỗi (dùng `default_tx_type` của hũ)."""
    out: list[tuple[str, str, float]] = []
    default_type = jar.get("default_tx_type")
    for m in jar.get("merchants", []):
        if isinstance(m, str):
            if not default_type:
                raise PersonaError(f"Hũ {jar['code']}: merchants kiểu chuỗi cần default_tx_type")
            out.append((m, default_type, 1.0))
        else:
            out.append((m["name"], m.get("tx_type", default_type), float(m.get("weight", 1.0))))
            if not out[-1][1]:
                raise PersonaError(f"Hũ {jar['code']}: merchant {m['name']!r} thiếu tx_type")
    return out


def _expense_lines(
    rng: random.Random,
    code: str,
    j: Mapping[str, Any],
    spend: int,
    merchants: list[tuple[str, str, float]],
    *,
    income_days: list[int],
    history_days: int,
    end_ago: int,
    anchor: date,
    payday_day: int,
    rhythm: Mapping[str, float],
) -> list[TxSeed]:
    """Khoản chi của một hũ (bước 4 và 5 ở đầu file): `spend` chia theo `recent_share` cho khoảng sau ngày lương gần nhất, phần còn
    lại theo số ngày cho các khoảng trước; trong mỗi khoảng chọn ngày theo nhịp, số tiền theo lognormal, cửa hàng theo trọng số.
    Mọi giá trị ngẫu nhiên lấy từ `rng` của riêng hũ này, theo đúng thứ tự gọi như trước khi tách hàm (băm đầu ra không đổi)."""
    out: list[TxSeed] = []
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
    names = [m[0] for m in merchants]
    types = {m[0]: m[1] for m in merchants}
    mweights = [m[2] for m in merchants]
    seq = 0
    for (first, last), amount in allocations:
        if amount <= 0:
            continue
        n = max(1, round(n_total * amount / spend))
        money = _split_total(rng, amount, n, float(rhythm["amount_sigma"]))
        span = list(range(first, last - 1, -1))
        agos = _pick_days(
            rng,
            span,
            _day_weights(span, anchor, payday_day, rhythm),
            len(money),
            int(rhythm["max_per_day"]),
        )
        rng.shuffle(money)
        for m_amount, ago in zip(money, agos, strict=False):
            name = rng.choices(names, weights=mweights, k=1)[0]
            seq += 1
            out.append(
                TxSeed(
                    f"exp:{code}:{seq}", ago, time(rng.randint(7, 21), rng.randint(0, 59)),
                    "expense", code, -m_amount, name, None, types[name], classified_by="seed",
                )
            )  # fmt: skip
        if len(agos) < len(money):  # hết chỗ trong khoảng
            raise PersonaError(f"Hũ {code}: max_per_day quá thấp cho {len(money)} khoản chi")
    return out


def generate(
    persona: str,
    *,
    anchor: date,
    seed: int | None = None,
    specs_dir: Path = SPECS_DIR,
    spec: Mapping[str, Any] | None = None,
) -> PersonaData:
    """Sinh hồ sơ, hũ, người nhận, nghĩa vụ và sổ cái của `persona`. Tất định: cùng (persona, seed, anchor) -> cùng kết quả.

    `spec` (tùy chọn) thay cho file spec, dùng để thử spec sai trong test."""
    spec = spec if spec is not None else load_spec(persona, specs_dir)
    seed = spec["seed"] if seed is None else seed
    salary = int(spec["monthly_salary_vnd"])
    payday_day = int(spec["payday_day"])
    history_days = int(spec["history_days"])
    employer = spec.get("employer")
    start = anchor - timedelta(days=history_days)
    paydays = _paydays(start, anchor, payday_day)
    income_days = [(anchor - d).days for d in paydays]  # days_ago của mỗi ngày lương
    end_ago = 1  # hôm qua là ngày cuối cùng có giao dịch lịch sử

    split_total = sum(Decimal(str(j["split_percent"])) for j in spec["jars"])
    if split_total != 100:
        raise PersonaError(f"Tỷ lệ chia của {persona} cộng lại {split_total}, phải là 100")
    jar_codes = {j["code"] for j in spec["jars"]}
    shares = split_amount(salary, [(j["code"], j["split_percent"]) for j in spec["jars"]])

    obligations = tuple(
        ObligationSeed(
            key=f"ob{i}",
            kind=o["kind"],
            name=o["name"],
            amount_vnd=int(o["amount_vnd"]),
            amount_min_vnd=int(o["amount_min_vnd"]) if o.get("amount_min_vnd") else None,
            amount_max_vnd=int(o["amount_max_vnd"]) if o.get("amount_max_vnd") else None,
            fee_vnd=int(o.get("fee_vnd", 0)),
            cycle=o.get("cycle", "monthly"),
            due_day=int(o["due_day"]),
            pay_jar=o.get("pay_jar"),
            is_essential=bool(o.get("is_essential", False)),
        )
        for i, o in enumerate(spec.get("obligations", []))
    )
    for ob in obligations:
        if ob.pay_jar is not None and ob.pay_jar not in jar_codes:
            raise PersonaError(f"Nghĩa vụ {ob.name}: hũ trả {ob.pay_jar} không có trong spec")
    payees = tuple(
        PayeeSeed(
            name=p["name"],
            account_hint=p.get("account_hint"),
            is_favorite=bool(p.get("is_favorite", False)),
            used_days_ago=p.get("used_days_ago"),
        )
        for p in spec.get("payees", [])
    )
    payee_names = {p.name for p in payees}
    moves = _jar_transfers(spec, {j["code"]: j["name"] for j in spec["jars"]}, history_days)

    jars: list[JarSeed] = []
    txs: list[TxSeed] = []
    for order, j in enumerate(spec["jars"]):
        code = j["code"]
        rng = random.Random(f"{seed}:{persona}:{code}")
        pct = Decimal(str(j["split_percent"]))
        opening = int(j.get("opening_vnd", 0))
        target = int(j["target_vnd"])
        rhythm = _rhythm(spec, j)
        jar_txs: list[TxSeed] = []
        if opening > 0:
            jar_txs.append(
                TxSeed(
                    f"open:{code}", history_days, _OPENING_TIME, "transfer", code, opening,
                    "Số dư đầu kỳ", None, "jar_transfer", transfer_key=f"open:{code}",
                )
            )  # fmt: skip
        jar_moves = moves.get(code, [])
        jar_txs.extend(jar_moves)
        total_in = opening + shares[code] * len(paydays) + sum(t.amount_vnd for t in jar_moves)

        # khoản trả nghĩa vụ định kỳ trong lịch sử của hũ này
        obligation_total = 0
        for ob in obligations:
            spec_ob = spec["obligations"][int(ob.key[2:])]
            if ob.pay_jar != code or not spec_ob.get("paid_in_history") or ob.cycle != "monthly":
                continue
            y, m = start.year, start.month
            while date(y, m, 1) < anchor:
                due = payday_in_month(ob.due_day, y, m)
                if start <= due < anchor:
                    if ob.amount_min_vnd and ob.amount_max_vnd:
                        lo, hi = ob.amount_min_vnd // _ROUND, ob.amount_max_vnd // _ROUND
                        amount = rng.randint(lo, hi) * _ROUND
                    else:
                        amount = ob.amount_vnd
                    ago = (anchor - due).days
                    jar_txs.append(
                        TxSeed(
                            f"pay:{ob.key}:{due.isoformat()}", ago, _OBLIGATION_TIME, "expense", code,
                            -amount, spec_ob.get("merchant", ob.name), None,
                            spec_ob.get("tx_type", "obligation_payment"),
                            obligation_key=ob.key, classified_by="seed",
                        )
                    )  # fmt: skip
                    obligation_total += amount
                y, m = (y + 1, 1) if m == 12 else (y, m + 1)

        spend = total_in - target - obligation_total
        if total_in - target < 0:
            raise PersonaError(
                f"Hũ {code}: tiền vào {total_in} nhỏ hơn số dư cần đạt {target}; thêm opening_vnd"
            )
        if spend < 0:
            raise PersonaError(
                f"Hũ {code}: khoản trả nghĩa vụ trong lịch sử ({obligation_total}) lớn hơn tổng chi cho phép"
            )
        if spend % _ROUND:
            raise PersonaError(f"Hũ {code}: tổng chi {spend} phải là bội của {_ROUND}")
        merchants = _merchants(j)
        if spend and not merchants:
            raise PersonaError(f"Hũ {code}: có chi tiêu nhưng không khai merchants")

        if spend:
            jar_txs.extend(
                _expense_lines(
                    rng, code, j, spend, merchants, income_days=income_days, history_days=history_days,
                    end_ago=end_ago, anchor=anchor, payday_day=payday_day, rhythm=rhythm,
                )
            )  # fmt: skip

        # dòng tiền vào của hũ để mô phỏng số dư chạy: lương chia và số dư đầu kỳ
        income_lines = [
            TxSeed(
                f"split:{ago}:{code}", ago, _SPLIT_TIME, "transfer", code, shares[code], None, None,
                "salary_split", transfer_key=f"split:{ago}",
            )
            for ago in income_days
        ]  # fmt: skip
        _simulate_non_negative(code, jar_txs + income_lines)
        final = sum(t.amount_vnd for t in jar_txs + income_lines)
        if final != target:  # bất biến của bộ sinh
            raise PersonaError(f"Hũ {code}: số dư cuối {final} khác mục tiêu {target}")
        goal_date = date.fromisoformat(j["goal_date"]) if j.get("goal_date") else None
        jars.append(
            JarSeed(
                code=code,
                name=j["name"],
                color_key=j["color_key"],
                icon_key=j["icon_key"],
                kind=j.get("kind", "spending"),
                split_percent=pct,
                balance_vnd=target,
                sort_order=order,
                goal_vnd=int(j["goal_vnd"]) if j.get("goal_vnd") else None,
                goal_date=goal_date,
            )
        )
        txs.extend(jar_txs)

    # --- lương: income vào Tiền vào khác, rồi chia vào hũ -----------------------------------------------------
    salary_events: list[SalaryEventSeed] = []
    for pd, ago in zip(paydays, income_days, strict=True):
        income_key = f"salary:{ago}"
        txs.append(
            TxSeed(
                income_key, ago, _SALARY_TIME, "income", OTHER_INCOME_JAR_CODE, salary, employer,
                f"Lương tháng {pd.month}/{pd.year}", "salary", classified_by="seed",
            )
        )  # fmt: skip
        txs.append(
            TxSeed(
                f"split:{ago}:{OTHER_INCOME_JAR_CODE}", ago, _SPLIT_TIME, "transfer",
                OTHER_INCOME_JAR_CODE, -salary, None, "Chia lương vào các hũ", "salary_split",
                transfer_key=f"split:{ago}",
            )
        )  # fmt: skip
        for j in spec["jars"]:
            txs.append(
                TxSeed(
                    f"split:{ago}:{j['code']}", ago, _SPLIT_TIME, "transfer", j["code"],
                    shares[j["code"]], None, f"Lương chia vào hũ {j['name']}", "salary_split",
                    transfer_key=f"split:{ago}",
                )
            )  # fmt: skip
        salary_events.append(
            SalaryEventSeed(
                days_ago=ago,
                amount_vnd=salary,
                transaction_key=income_key,
                split=tuple((c, v) for c, v in shares.items() if v > 0),
            )
        )

    # --- thu nhập ngoài ví (tùy chọn): về tài khoản ngân hàng khác, không đổi số dư hũ nào ------------------------------
    external_income = _external_income_lines(spec, start, anchor)
    txs.extend(external_income)

    # --- hũ hệ thống ------------------------------------------------------------------------------------------
    system = spec.get("system_jars", {})
    balances = {OTHER_INCOME_JAR_CODE: 0, UNCLASSIFIED_JAR_CODE: 0}
    for i, line in enumerate(system.get("other_income", [])):
        _check_payee(line, payee_names)
        amount = int(line["amount_vnd"])
        txs.append(
            TxSeed(
                f"other:{i}", int(line["days_ago"]), time(12, 0), "income", OTHER_INCOME_JAR_CODE,
                amount, line.get("merchant"), line.get("note"), line.get("tx_type", "income_other"),
                payee=line.get("payee"), classified_by="seed",
            )
        )  # fmt: skip
        balances[OTHER_INCOME_JAR_CODE] += amount
    for i, line in enumerate(system.get("unclassified", [])):
        _check_payee(line, payee_names)
        amount = int(line["amount_vnd"])
        txs.append(
            TxSeed(
                f"uncl:{i}", int(line["days_ago"]), time(18, 30), "expense", UNCLASSIFIED_JAR_CODE,
                -amount, line.get("merchant"), line.get("note"), line.get("tx_type", "other_expense"),
                payee=line.get("payee"), needs_review=True,
            )
        )  # fmt: skip
        balances[UNCLASSIFIED_JAR_CODE] -= amount

    # --- Trả sau (mô phỏng) -----------------------------------------------------------------------------------
    credit = spec.get("credit_line")
    bnpl_total = 0
    for i, p in enumerate(spec.get("bnpl", {}).get("purchases", [])):
        if credit is None:
            raise PersonaError("Có giao dịch Trả sau nhưng spec không khai credit_line")
        if p["jar"] not in jar_codes:
            raise PersonaError(f"Giao dịch Trả sau {i}: hũ {p['jar']} không có trong spec")
        amount = int(p["amount_vnd"])
        bnpl_total += amount
        txs.append(
            TxSeed(
                f"bnpl:{i}", int(p["days_ago"]), time(20, 15), "expense", p["jar"], -amount,
                p.get("merchant"), p.get("note"), p.get("tx_type", "other_expense"),
                funding_source="credit", classified_by="seed",
            )
        )  # fmt: skip
    if credit is not None and bnpl_total > int(credit["limit_vnd"]):
        raise PersonaError("Tổng gốc Trả sau vượt hạn mức khai trong spec")

    # --- hũ chỉ ví demo có (spec `demo_jars`): dòng ngẫu nhiên riêng, không đụng sổ cái của ví persona ---------------------
    demo_jars = tuple(
        _demo_jar(
            spec, d, persona=persona, seed=seed, salary=salary, income_days=income_days,
            history_days=history_days, end_ago=end_ago, anchor=anchor, payday_day=payday_day,
            jar_codes=jar_codes,
        )
        for d in spec.get("demo_jars", [])
    )  # fmt: skip
    if len({d.code for d in demo_jars}) != len(demo_jars):
        raise PersonaError("demo_jars: mã hũ phải duy nhất")

    txs.sort(key=lambda t: (-t.days_ago, t.local_time, t.key))
    return PersonaData(
        persona=persona,
        display_name=spec["display_name"],
        monthly_salary_vnd=salary,
        payday_day=payday_day,
        risk_tolerance=spec["risk_tolerance"],
        history_days=history_days,
        anchor=anchor,
        jars=tuple(jars),
        transactions=tuple(txs),
        payees=payees,
        obligations=obligations,
        salary_events=tuple(salary_events),
        credit_limit_vnd=int(credit["limit_vnd"]) if credit else None,
        credit_due_day=int(credit["due_day"]) if credit else None,
        bnpl_principal_vnd=bnpl_total,
        system_balances=balances,
        seed_salary_events=bool(spec.get("seed_salary_events", False)),
        external_income_monthly_vnd=(
            int(spec["external_income_monthly_vnd"])
            if spec.get("external_income_monthly_vnd")
            else None
        ),
        demo_jars=demo_jars,
    )


def _demo_jar(
    spec: Mapping[str, Any],
    d: Mapping[str, Any],
    *,
    persona: str,
    seed: int,
    salary: int,
    income_days: list[int],
    history_days: int,
    end_ago: int,
    anchor: date,
    payday_day: int,
    jar_codes: set[str],
) -> DemoJarSeed:
    """Hũ của khối `demo_jars` (README "Bộ hũ demo sau khi đặt lại"): `split_from` (mã hũ demo -> số điểm % lấy sang hũ này),
    `opening_vnd`, `target_vnd`, `expense_count`, `recent_share`, `rhythm`, `merchants` như một hũ của `jars`. Mỗi kỳ lương hũ nhận
    `floor(lương x điểm / 100)` của từng hũ nguồn (quy tắc làm tròn của `split_amount`); chi = đầu kỳ + lương chia - số dư cần đạt,
    chia theo cùng nhịp và cùng hàm với hũ của ví persona nhưng bằng `random.Random` riêng của hũ này, nên thêm, bớt hay chỉnh hũ demo
    không đổi một dòng nào của hũ khác."""
    code = str(d.get("code") or "")
    if not code.isidentifier() or code in jar_codes:
        raise PersonaError(f"demo_jars: mã hũ {code!r} không hợp lệ hoặc trùng hũ của ví persona")
    raw = d.get("split_from") or {}
    if not raw or any(Decimal(str(p)) <= 0 for p in raw.values()):
        raise PersonaError(f"demo_jars {code}: split_from phải lấy số điểm dương từ ít nhất một hũ")
    split_from = tuple(
        (
            str(src),
            Decimal(str(p)),
            int((Decimal(salary) * Decimal(str(p)) / 100).to_integral_value(rounding=ROUND_FLOOR)),
        )
        for src, p in raw.items()
    )
    line = sum(a for _, _, a in split_from)
    opening = int(d.get("opening_vnd", 0))
    target = int(d["target_vnd"])
    rng = random.Random(f"{seed}:{persona}:demo:{code}")
    rhythm = _rhythm(spec, d)
    txs: list[TxSeed] = []
    if opening > 0:
        txs.append(
            TxSeed(
                f"open:{code}", history_days, _OPENING_TIME, "transfer", code, opening, "Số dư đầu kỳ", None,
                "jar_transfer", transfer_key=f"open:{code}",
            )
        )  # fmt: skip
    spend = opening + line * len(income_days) - target
    if spend < 0:
        raise PersonaError(
            f"demo_jars {code}: tiền vào nhỏ hơn số dư cần đạt {target}; thêm opening_vnd"
        )
    if spend % _ROUND:
        raise PersonaError(f"demo_jars {code}: tổng chi {spend} phải là bội của {_ROUND}")
    merchants = _merchants({**d, "code": code})
    if spend and not merchants:
        raise PersonaError(f"demo_jars {code}: có chi tiêu nhưng không khai merchants")
    if spend:
        txs.extend(
            _expense_lines(
                rng, code, d, spend, merchants, income_days=income_days, history_days=history_days,
                end_ago=end_ago, anchor=anchor, payday_day=payday_day, rhythm=rhythm,
            )
        )  # fmt: skip
    split_lines = [
        TxSeed(
            f"split:{ago}:{code}",
            ago,
            _SPLIT_TIME,
            "transfer",
            code,
            line,
            None,
            None,
            "salary_split",
        )
        for ago in income_days
    ]
    _simulate_non_negative(code, txs + split_lines)
    if sum(t.amount_vnd for t in txs + split_lines) != target:  # bất biến của bộ sinh
        raise PersonaError(f"demo_jars {code}: số dư cuối khác mục tiêu {target}")
    return DemoJarSeed(code, split_from, opening, target, tuple(txs))


def _external_income_lines(spec: Mapping[str, Any], start: date, anchor: date) -> list[TxSeed]:
    """Dòng thu nhập ngoài ví mỗi tháng trong [start, anchor): `external_income_monthly_vnd` vào ngày `external_income.day`
    (mặc định 15; ngày lớn hơn số ngày của tháng thì lấy ngày cuối tháng). Spec không khai số tiền thì không có dòng nào."""
    amount = int(spec.get("external_income_monthly_vnd") or 0)
    if amount < 0:
        raise PersonaError("external_income_monthly_vnd phải dương")
    if not amount:
        return []
    cfg = spec.get("external_income", {})
    day = int(cfg.get("day", 15))
    if not 1 <= day <= 31:
        raise PersonaError("external_income.day phải từ 1 đến 31")
    tx_type = cfg.get("tx_type", "income_other")
    merchant = cfg.get("merchant")
    if merchant is not None and not 1 <= len(merchant) <= 120:
        raise PersonaError("external_income.merchant dài 1 đến 120 ký tự")
    out: list[TxSeed] = []
    for d in _paydays(start, anchor, day):  # cùng quy tắc ngày-trong-tháng của ngày lương
        ago = (anchor - d).days
        out.append(
            TxSeed(
                f"extin:{ago}", ago, time(int(cfg.get("hour", 10)), 30), "income", None, amount,
                merchant, cfg.get("note"), tx_type, funding_source="external", classified_by="seed",
            )
        )  # fmt: skip
    return out


def _jar_transfers(
    spec: Mapping[str, Any], jar_names: Mapping[str, str], history_days: int
) -> dict[str, list[TxSeed]]:
    """Dòng chuyển hũ trong lịch sử theo hũ (spec `jar_transfers`, tùy chọn): mỗi khoản một dòng âm ở hũ nguồn và một dòng
    dương ở hũ đích, cùng nhóm chuyển. Chỉ giữa hai hũ thường khác nhau của spec, sau ngày đầu lịch sử."""
    out: dict[str, list[TxSeed]] = {}
    for i, mv in enumerate(spec.get("jar_transfers", [])):
        src, dst = mv.get("from"), mv.get("to")
        amount = int(mv.get("amount_vnd", 0))
        ago = int(mv.get("days_ago", 0))
        if src not in jar_names or dst not in jar_names or src == dst:
            raise PersonaError(
                f"jar_transfers[{i}]: hũ nguồn và hũ đích phải là hai hũ khác nhau trong spec"
            )
        if amount <= 0 or amount % _ROUND:
            raise PersonaError(f"jar_transfers[{i}]: amount_vnd phải dương và là bội của {_ROUND}")
        if not 1 <= ago < history_days:
            raise PersonaError(f"jar_transfers[{i}]: days_ago phải từ 1 tới {history_days - 1}")
        key = f"move:{i}"
        note = mv.get("note")
        out.setdefault(src, []).append(
            TxSeed(
                f"{key}:out", ago, _MOVE_TIME, "transfer", src, -amount, None,
                note or f"Chuyển sang hũ {jar_names[dst]}", "jar_transfer", transfer_key=key,
            )
        )  # fmt: skip
        out.setdefault(dst, []).append(
            TxSeed(
                f"{key}:in", ago, _MOVE_TIME, "transfer", dst, amount, None,
                note or f"Nhận từ hũ {jar_names[src]}", "jar_transfer", transfer_key=key,
            )
        )  # fmt: skip
    return out


def _check_payee(line: Mapping[str, Any], names: set[str]) -> None:
    if line.get("payee") and line["payee"] not in names:
        raise PersonaError(f"Người nhận {line['payee']!r} không có trong payees của spec")


# --- ghép với đồng hồ mô phỏng và dựng id (ADR-0003) --------------------------------------------
@dataclass(frozen=True)
class MaterializedTx:
    occurred_at: datetime
    app_date: date
    kind: str
    jar_code: str | None
    amount_vnd: int
    merchant: str | None
    note: str | None
    source: str
    tx_type: str = "other"
    funding_source: str = "jar"


@dataclass(frozen=True)
class Materialized:
    """Dữ liệu sẵn sàng nạp vào Aurora (khóa của từng dict khớp tham số của `LedgerRepo.reset_user`)."""

    clock_offset_days: int
    app_date: date
    data: PersonaData
    transactions: tuple[MaterializedTx, ...]
    profile: dict[str, Any] = field(default_factory=dict)
    jars: list[dict[str, Any]] = field(default_factory=list)
    payees: list[dict[str, Any]] = field(default_factory=list)
    obligations: list[dict[str, Any]] = field(default_factory=list)
    credit_line: dict[str, Any] | None = None
    transaction_rows: list[dict[str, Any]] = field(default_factory=list)
    salary_events: list[dict[str, Any]] = field(default_factory=list)


def _uid(user_id: str, persona: str, key: str) -> str:
    return str(uuid.uuid5(ID_NAMESPACE, f"{user_id}|{persona}|{key}"))


def materialize(
    data: PersonaData,
    *,
    anchor: date,
    now: datetime,
    tz: tzinfo,
    user_id: str = "demo",
    bnpl_fee: Mapping[str, Any] | None = None,
    bnpl_label: str = "Trả sau (mô phỏng)",
    obligation_pay_jar: str | None = None,
) -> Materialized:
    """Gắn đồng hồ: offset sao cho ngày mô phỏng = `anchor`; mỗi dòng có `app_date` mô phỏng và `occurred_at` thật (UTC)
    nhất quán với offset (ngày thật = hôm nay thật - days_ago). `bnpl_fee` (`amount_vnd`, `id`) lấy từ bảng `fee_schedules`
    do người gọi cung cấp; không có thì nghĩa vụ trả sau không có phí. `obligation_pay_jar` là hũ trả của khoản Trả sau
    (mặc định: Nghĩa vụ chuẩn hoặc hũ nghĩa vụ cũ)."""
    offset = clock_offset_for(anchor, now, tz)
    real_today = now.astimezone(tz).date()

    def when(days_ago: int, at: time) -> datetime:
        return datetime.combine(real_today - timedelta(days=days_ago), at, tzinfo=tz).astimezone(
            UTC
        )

    payee_ids = {p.name: _uid(user_id, data.persona, f"payee:{p.name}") for p in data.payees}
    ob_ids = {o.key: _uid(user_id, data.persona, f"ob:{o.key}") for o in data.obligations}
    tx_ids = {t.key: _uid(user_id, data.persona, f"tx:{t.key}") for t in data.transactions}

    rows: list[MaterializedTx] = []
    tx_rows: list[dict[str, Any]] = []
    for t in data.transactions:
        at = when(t.days_ago, t.local_time)
        app_date = anchor - timedelta(days=t.days_ago)
        rows.append(
            MaterializedTx(
                occurred_at=at,
                app_date=app_date,
                kind=t.kind,
                jar_code=t.jar_code,
                amount_vnd=t.amount_vnd,
                merchant=t.merchant,
                note=t.note,
                source=t.source,
                tx_type=t.tx_type,
                funding_source=t.funding_source,
            )
        )
        tx_rows.append(
            {
                "id": tx_ids[t.key],
                "occurred_at": at,
                "app_date": app_date,
                "kind": t.kind,
                "jar_code": t.jar_code,
                "amount": t.amount_vnd,
                "merchant": t.merchant,
                "note": t.note,
                "transfer_id": _uid(user_id, data.persona, f"transfer:{t.transfer_key}")
                if t.transfer_key
                else None,
                "source": t.source,
                "tx_type": t.tx_type,
                "funding_source": t.funding_source,
                "payee_id": payee_ids.get(t.payee) if t.payee else None,
                "obligation_id": ob_ids.get(t.obligation_key) if t.obligation_key else None,
                "needs_review": t.needs_review,
                "classified_by": t.classified_by,
            }
        )

    jars = [
        {
            "code": j.code,
            "name": j.name,
            "color_key": j.color_key,
            "icon_key": j.icon_key,
            "split": j.split_percent,
            "sort_order": j.sort_order,
            "kind": j.kind,
            "goal_vnd": j.goal_vnd,
            "goal_date": j.goal_date,
        }
        for j in data.jars
    ]
    payees = [
        {
            "id": payee_ids[p.name],
            "name": p.name,
            "account_hint": p.account_hint,
            "is_favorite": p.is_favorite,
            "last_used_at": when(p.used_days_ago, time(10, 0)) if p.used_days_ago else None,
        }
        for p in data.payees
    ]
    obligations = [
        {
            "id": ob_ids[o.key],
            "kind": o.kind,
            "name": o.name,
            "amount": o.amount_vnd,
            "amount_min": o.amount_min_vnd,
            "amount_max": o.amount_max_vnd,
            "fee": o.fee_vnd,
            "principal": None,
            "due_date": first_due_from_day(o.due_day, anchor),
            "cycle": o.cycle,
            "due_day": o.due_day,
            "pay_jar": o.pay_jar,
            "is_essential": o.is_essential,
            "source": "declared",
            "fee_id": None,
        }
        for o in data.obligations
    ]
    credit_line = None
    if data.credit_limit_vnd is not None and data.credit_due_day is not None:
        credit_line = {
            "product": "bnpl_sim",
            "lim": data.credit_limit_vnd,
            "outstanding": data.bnpl_principal_vnd,
            "due_day": data.credit_due_day,
        }
        if data.bnpl_principal_vnd:
            fee = int(bnpl_fee["amount_vnd"]) if bnpl_fee else 0
            pay_jar = obligation_pay_jar or default_obligation_jar(
                (j.code, j.kind) for j in data.jars
            )
            obligations.append(
                {
                    "id": _uid(user_id, data.persona, "ob:bnpl"),
                    "kind": "bnpl",
                    "name": bnpl_label,
                    "amount": data.bnpl_principal_vnd + fee,
                    "amount_min": None,
                    "amount_max": None,
                    "fee": fee,
                    "principal": data.bnpl_principal_vnd,
                    "due_date": bnpl_due_date(data.credit_due_day, anchor),
                    "cycle": "once",
                    "due_day": None,
                    "pay_jar": pay_jar,
                    "is_essential": False,
                    "source": "bnpl_auto",
                    "fee_id": bnpl_fee.get("id") if bnpl_fee else None,
                }
            )
    salary_events = [
        {
            "id": _uid(user_id, data.persona, f"salary_event:{e.days_ago}"),
            "period_date": anchor - timedelta(days=e.days_ago),
            "transaction_id": tx_ids[e.transaction_key],
            "received_on": anchor - timedelta(days=e.days_ago),
            "expected": data.monthly_salary_vnd,
            "amount": e.amount_vnd,
            "deviation": 0,
            "status": "confirmed",
            "split": [{"jar": c, "amount_vnd": v} for c, v in e.split],
            "confirmed_at": when(e.days_ago, _SPLIT_TIME),
        }
        for e in data.salary_events
        if data.seed_salary_events
    ]
    return Materialized(
        clock_offset_days=offset,
        app_date=anchor,
        data=data,
        transactions=tuple(rows),
        profile={
            "display_name": data.display_name,
            "salary": data.monthly_salary_vnd,
            "payday": data.payday_day,
            "risk": data.risk_tolerance,
            "clock_offset_days": offset,
        },
        jars=jars,
        payees=payees,
        obligations=obligations,
        credit_line=credit_line,
        transaction_rows=tx_rows,
        salary_events=salary_events,
    )
