"""Adapt the historical demo ledgers to the configured demo layout (issue #39).

The demo wallet keeps the onboarding defaults Nghĩa vụ and Dự phòng and the jars the user added: Ăn uống, Đi lại, Giải trí
(Chi hằng ngày split by category, so behaviour signals stay per jar), Mục tiêu and Đầu tư. Each persona jar folds into one
demo jar (`JAR_ALIASES`, identity for a code the layout keeps): balances, split shares, history, salary splits, obligation
sources and the roadmap seed all follow the same mapping, so the wallet total and every line of the kept jars are unchanged.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING

from personas.generator import JarSeed, PersonaData, PersonaError, TxSeed
from yofina_core.wallet import LEGACY_JAR_ALIASES, TX_TYPE_JAR_TRANSFER, TX_TYPE_SALARY_SPLIT

if TYPE_CHECKING:
    from yofina_ledger.jar_layout import DemoJar

#: persona jar -> demo jar, for codes the demo layout does not keep. The same mapping routes a new transaction whose type
#: defaults to a legacy jar (`yofina_core.wallet.transaction_jar`): travel goes to the goal jar built from Du lịch.
JAR_ALIASES = LEGACY_JAR_ALIASES

#: simulated BNPL due day per persona on the demo wallet. Minh's spec uses the payday (5); the demo moves the December
#: installment two days earlier so it falls inside the "due before payday" window of the Nghĩa vụ forecast (scene 2).
DEMO_CREDIT_DUE_DAY = {"minh": 3}


def demo_jar_code(code: str) -> str:
    return JAR_ALIASES.get(code, code)


def apply_demo_layout(data: PersonaData, layout: Sequence[DemoJar]) -> PersonaData:
    """Fold the persona wallet into the demo layout while preserving the wallet total."""
    layout_codes = [j.code for j in layout]
    if len(set(layout_codes)) != len(layout_codes):
        raise PersonaError("Cấu hình hũ demo phải có mã duy nhất.")
    stray = sorted({j.code for j in data.jars} - {c for c in JAR_ALIASES} - set(layout_codes))
    if stray or any(target not in layout_codes for target in JAR_ALIASES.values()):
        raise PersonaError(f"Hũ của persona không có trong cấu hình hũ demo: {', '.join(stray) or 'ánh xạ'}.")

    sources: dict[str, list[JarSeed]] = defaultdict(list)
    for old in data.jars:
        sources[demo_jar_code(old.code)].append(old)
    jars: list[JarSeed] = []
    for j in layout:
        own = sources.get(j.code, [])
        goal = next((s for s in own if s.goal_vnd is not None), None)
        if j.purpose == "goal" and goal is None:
            if own:
                raise PersonaError(f"Hũ {j.name} của bộ hũ demo cần mục tiêu từ hũ của persona.")
            continue  # a goal jar needs an amount and a date; the persona has none to bring
        jars.append(
            JarSeed(
                code=j.code,
                # a goal jar is one the user added for a specific goal: it shows the name of the persona jar it comes from
                # (Du lịch), the name the roadmap seed and the persona story use; the layout name is for a goal without source
                name=goal.name if j.purpose == "goal" and goal is not None else j.name,
                color_key=j.color_key,
                icon_key=j.icon_key,
                kind=j.kind,
                split_percent=sum((Decimal(s.split_percent) for s in own), Decimal(0)),
                balance_vnd=sum(s.balance_vnd for s in own),
                sort_order=j.sort_order,
                goal_vnd=goal.goal_vnd if goal else None,
                goal_date=goal.goal_date if goal else None,
            )
        )
    if sum(j.split_percent for j in jars) != 100:
        raise PersonaError("Tỷ lệ chia của bộ hũ demo phải có tổng 100%.")

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
        else:
            transactions.append(t)
    transactions.extend(salary_lines.values())
    transactions.sort(key=lambda t: (-t.days_ago, t.local_time, t.key))

    events = []
    for event in data.salary_events:
        amounts: Counter[str] = Counter()
        for code, value in event.split:
            amounts[demo_jar_code(code)] += value
        events.append(replace(event, split=tuple(amounts.items())))

    return replace(
        data,
        jars=tuple(jars),
        transactions=tuple(transactions),
        obligations=tuple(
            replace(ob, pay_jar=demo_jar_code(ob.pay_jar) if ob.pay_jar else None)
            for ob in data.obligations
        ),
        salary_events=tuple(events),
        credit_due_day=DEMO_CREDIT_DUE_DAY.get(data.persona, data.credit_due_day),
    )
