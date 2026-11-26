"""Adapt the historical demo ledgers to the configured demo layout (issue #39).

The demo wallet has the three onboarding defaults (Chi hằng ngày, Nghĩa vụ, Dự phòng) and, next to them, the jars the user
added: Ăn uống, Đi lại, Giải trí (behaviour signals are per jar code), Mục tiêu and Đầu tư. Each persona jar folds into one demo
jar (`JAR_ALIASES`, identity for a code the layout keeps): balances, split shares, history, salary splits, obligation sources and
the roadmap seed all follow the same mapping, so every line of the kept jars is unchanged.

Chi hằng ngày has no persona jar: its history is the small everyday spending the persona spec declares in `demo_jars`, generated
with its own random stream (`personas.generator.DemoJarSeed`). Its split share comes from the source jars of `split_from`: each
salary split of a source shrinks by the new jar's part, and the source's opening balance grows by the sum of those parts, so the
source keeps the balance of the persona spec on the anchor day. The wallet total is the persona total plus the new jar's balance.

The demo wallet's BNPL due day comes from the spec too (`credit_line.demo_due_day`, Minh: 3 so the December installment falls
inside the "due before payday" window of the Nghĩa vụ forecast in scene 2); a spec without it keeps `credit_line.due_day`.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING

from personas.generator import (
    _OPENING_TIME,
    _SPLIT_TIME,
    DemoJarSeed,
    JarSeed,
    PersonaData,
    PersonaError,
    TxSeed,
    _simulate_non_negative,
)
from yofina_core.wallet import LEGACY_JAR_ALIASES, TX_TYPE_JAR_TRANSFER, TX_TYPE_SALARY_SPLIT

if TYPE_CHECKING:
    from yofina_ledger.jar_layout import DemoJar

#: persona jar -> demo jar, for codes the demo layout does not keep. The same mapping routes a new transaction whose type
#: defaults to a legacy jar (`yofina_core.wallet.transaction_jar`): travel goes to the goal jar built from Du lịch.
JAR_ALIASES = LEGACY_JAR_ALIASES


def demo_jar_code(code: str) -> str:
    return JAR_ALIASES.get(code, code)


def _is_opening(t: TxSeed) -> bool:
    return t.tx_type == TX_TYPE_JAR_TRANSFER and t.key.startswith("open:")


def apply_demo_layout(data: PersonaData, layout: Sequence[DemoJar]) -> PersonaData:
    """Fold the persona wallet into the demo layout and add the demo-only jars of the spec (`data.demo_jars`)."""
    layout_codes = [j.code for j in layout]
    if len(set(layout_codes)) != len(layout_codes):
        raise PersonaError("Cấu hình hũ demo phải có mã duy nhất.")
    stray = sorted({j.code for j in data.jars} - {c for c in JAR_ALIASES} - set(layout_codes))
    if stray or any(target not in layout_codes for target in JAR_ALIASES.values()):
        raise PersonaError(f"Hũ của persona không có trong cấu hình hũ demo: {', '.join(stray) or 'ánh xạ'}.")
    extras: dict[str, DemoJarSeed] = {d.code: d for d in data.demo_jars}
    if missing := sorted(set(extras) - set(layout_codes)):
        raise PersonaError(f"Hũ demo của spec không có trong cấu hình hũ demo: {', '.join(missing)}.")
    names_of = {j.code: j.name for j in layout}
    # phần tỷ lệ và phần lương mỗi kỳ mà mỗi hũ nguồn nhường cho hũ demo
    given_pct: dict[str, Decimal] = defaultdict(Decimal)
    given_vnd: dict[str, int] = defaultdict(int)
    for extra in extras.values():
        for src, pts, amount in extra.split_from:
            if src not in names_of or src in extras:
                raise PersonaError(f"Hũ {extra.code}: hũ nguồn {src} của split_from không phải hũ demo có sẵn.")
            given_pct[src] += pts
            given_vnd[src] += amount

    sources: dict[str, list[JarSeed]] = defaultdict(list)
    for old in data.jars:
        sources[demo_jar_code(old.code)].append(old)
    jars: list[JarSeed] = []
    for j in layout:
        own = sources.get(j.code, [])
        extra = extras.get(j.code)
        goal = next((s for s in own if s.goal_vnd is not None), None)
        if j.purpose == "goal" and goal is None:
            if own:
                raise PersonaError(f"Hũ {j.name} của bộ hũ demo cần mục tiêu từ hũ của persona.")
            continue  # a goal jar needs an amount and a date; the persona has none to bring
        split = sum((Decimal(s.split_percent) for s in own), Decimal(0)) - given_pct.get(j.code, Decimal(0))
        if extra is not None:
            split += extra.split_percent
        if split < 0:
            raise PersonaError(f"Hũ {j.name} không đủ tỷ lệ để nhường {given_pct[j.code]} điểm cho hũ demo.")
        jars.append(
            JarSeed(
                code=j.code,
                # a goal jar is one the user added for a specific goal: it shows the name of the persona jar it comes from
                # (Du lịch), the name the roadmap seed and the persona story use; the layout name is for a goal without source
                name=goal.name if j.purpose == "goal" and goal is not None else j.name,
                color_key=j.color_key,
                icon_key=j.icon_key,
                kind=j.kind,
                split_percent=split,
                balance_vnd=sum(s.balance_vnd for s in own) + (extra.target_vnd if extra else 0),
                sort_order=j.sort_order,
                goal_vnd=goal.goal_vnd if goal else None,
                goal_date=goal.goal_date if goal else None,
            )
        )
    if sum(j.split_percent for j in jars) != 100:
        raise PersonaError("Tỷ lệ chia của bộ hũ demo phải có tổng 100%.")
    kept = {j.code for j in jars}
    if lost := sorted(set(given_pct) - kept):
        raise PersonaError(f"Hũ nguồn của split_from không có trên ví demo: {', '.join(lost)}.")

    mapped = [
        replace(t, jar_code=demo_jar_code(t.jar_code)) if t.jar_code is not None else t
        for t in data.transactions
    ]
    # a transfer between two persona jars that fold into the same demo jar nets to zero: drop both legs
    transfers: dict[str, list[TxSeed]] = defaultdict(list)
    for t in mapped:
        if t.transfer_key and t.tx_type == TX_TYPE_JAR_TRANSFER:
            transfers[t.transfer_key].append(t)
    collapsed = {
        key
        for key, pair in transfers.items()
        if len(pair) == 2
        and pair[0].jar_code == pair[1].jar_code
        and pair[0].amount_vnd + pair[1].amount_vnd == 0
    }
    names = {j.code: j.name for j in jars}
    transactions: list[TxSeed] = []
    salary_lines: dict[tuple[str, str], TxSeed] = {}
    openings: dict[str, TxSeed] = {}
    for t in mapped:
        if t.transfer_key in collapsed:
            continue
        if t.tx_type == TX_TYPE_SALARY_SPLIT and t.transfer_key and t.jar_code in names:
            # one salary-split line per demo jar, like confirm_salary writes it
            key = (t.transfer_key, t.jar_code)
            prior = salary_lines.get(key)
            salary_lines[key] = replace(
                t,
                key=f"{t.transfer_key}:{t.jar_code}",
                amount_vnd=t.amount_vnd + (prior.amount_vnd if prior else 0),
                note=f"Lương chia vào hũ {names[t.jar_code]}",
            )
        elif _is_opening(t) and t.jar_code in given_vnd:
            # a source jar keeps one opening line: it also carries the salary parts the source gave to the demo jar
            prior = openings.get(t.jar_code)
            openings[t.jar_code] = t if prior is None else replace(prior, amount_vnd=prior.amount_vnd + t.amount_vnd)
        else:
            transactions.append(t)
    split_days = sorted({line.days_ago for line in salary_lines.values()}, reverse=True)
    for code, extra in extras.items():
        if code not in names:
            continue
        for ago in split_days:
            salary_lines[(f"split:{ago}", code)] = TxSeed(
                f"split:{ago}:{code}", ago, _SPLIT_TIME, "transfer", code, extra.split_line_vnd, None,
                f"Lương chia vào hũ {names[code]}", TX_TYPE_SALARY_SPLIT, transfer_key=f"split:{ago}",
            )  # fmt: skip
        transactions.extend(extra.transactions)
    for src, amount in given_vnd.items():
        for ago in split_days:
            line = salary_lines[(f"split:{ago}", src)]
            salary_lines[(f"split:{ago}", src)] = replace(line, amount_vnd=line.amount_vnd - amount)
        moved = amount * len(split_days)
        prior = openings.get(src)
        openings[src] = (
            replace(prior, amount_vnd=prior.amount_vnd + moved)
            if prior is not None
            else TxSeed(
                f"open:{src}", data.history_days, _OPENING_TIME, "transfer", src, moved, "Số dư đầu kỳ", None,
                TX_TYPE_JAR_TRANSFER, transfer_key=f"open:{src}",
            )
        )  # fmt: skip
    transactions.extend(t for t in openings.values() if t.amount_vnd)
    transactions.extend(t for t in salary_lines.values() if t.amount_vnd)
    transactions.sort(key=lambda t: (-t.days_ago, t.local_time, t.key))
    for j in jars:  # self-check of the generator: running balance never negative, final balance as declared
        lines = [t for t in transactions if t.jar_code == j.code]
        _simulate_non_negative(j.code, lines)
        if sum(t.amount_vnd for t in lines if t.funding_source == "jar") != j.balance_vnd:
            raise PersonaError(f"Hũ {j.name} của ví demo: số dư cuối khác tổng các dòng.")

    events = []
    for event in data.salary_events:
        amounts: Counter[str] = Counter()
        for code, value in event.split:
            amounts[demo_jar_code(code)] += value
        for src, amount in given_vnd.items():
            amounts[src] -= amount
        for code, extra in extras.items():
            if code in names:
                amounts[code] += extra.split_line_vnd
        events.append(
            replace(event, split=tuple((j.code, amounts[j.code]) for j in jars if amounts.get(j.code, 0) > 0))
        )

    return replace(
        data,
        jars=tuple(jars),
        transactions=tuple(transactions),
        obligations=tuple(
            replace(ob, pay_jar=demo_jar_code(ob.pay_jar) if ob.pay_jar else None)
            for ob in data.obligations
        ),
        salary_events=tuple(events),
        # the BNPL due day of the demo wallet is spec data (`credit_line.demo_due_day`, `PersonaData.demo_credit_due_day`);
        # a spec without it keeps the persona due day
        credit_due_day=data.credit_due_day if data.demo_credit_due_day is None else data.demo_credit_due_day,
        demo_credit_due_day=None,
        demo_jars=(),
    )
