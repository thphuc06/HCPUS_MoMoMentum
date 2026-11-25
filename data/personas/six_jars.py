"""Adapt the historical demo ledgers to the configured demo layout."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import replace
from datetime import time
from decimal import Decimal
from typing import TYPE_CHECKING

from personas.generator import JarSeed, PersonaData, PersonaError, TxSeed
from yofina_core.wallet import (
    DEFAULT_GOAL_JAR,
    DEFAULT_OBLIGATION_JAR,
    DEFAULT_SPENDING_JAR,
    TX_TYPE_JAR_TRANSFER,
    TX_TYPE_SALARY_SPLIT,
)

if TYPE_CHECKING:
    from yofina_ledger.jar_layout import DemoJar

JAR_ALIASES = {
    "an_uong": DEFAULT_SPENDING_JAR,
    "di_lai": DEFAULT_SPENDING_JAR,
    "giai_tri": DEFAULT_SPENDING_JAR,
    "quy_don": DEFAULT_SPENDING_JAR,
    "tich_luy_dai_han": DEFAULT_SPENDING_JAR,
    "hoa_don": DEFAULT_OBLIGATION_JAR,
    "du_lich": DEFAULT_GOAL_JAR,
}


def use_default_jars(data: PersonaData, layout: Sequence[DemoJar]) -> PersonaData:
    """Fold old demo history into the configured jars while preserving the wallet total."""
    jar_names = {j.code: j.name for j in layout}
    if len(jar_names) != len(layout) or sum(j.split_percent for j in layout) != 100:
        raise PersonaError("Cấu hình hũ demo phải có mã duy nhất và tổng tỷ lệ 100%.")

    mapped = [
        replace(t, jar_code=JAR_ALIASES.get(t.jar_code, t.jar_code)) for t in data.transactions
    ]
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
    transactions: list[TxSeed] = []
    salary_lines: dict[tuple[str, str], TxSeed] = {}
    for t in mapped:
        if t.transfer_key in collapsed:
            continue
        if (
            t.tx_type == TX_TYPE_SALARY_SPLIT
            and t.transfer_key
            and t.jar_code is not None
            and t.jar_code in jar_names
        ):
            key = (t.transfer_key, t.jar_code)
            prior = salary_lines.get(key)
            salary_lines[key] = replace(
                t,
                key=f"{t.transfer_key}:{t.jar_code}",
                amount_vnd=t.amount_vnd + (prior.amount_vnd if prior else 0),
                note=f"Lương chia vào hũ {jar_names[t.jar_code]}",
            )
        else:
            transactions.append(t)
    transactions.extend(salary_lines.values())

    balances: Counter[str] = Counter()
    for old in data.jars:
        balances[JAR_ALIASES.get(old.code, old.code)] += old.balance_vnd
    credit_due_day = data.credit_due_day
    if data.persona == "minh":
        # Demo: part of the daily jar was set aside for bills yesterday. The
        # December BNPL installment falls two days before the simulated payday.
        amount = 700_000
        transfer = "six_jars_reserve_bills"
        for code, signed in ((DEFAULT_SPENDING_JAR, -amount), (DEFAULT_OBLIGATION_JAR, amount)):
            balances[code] += signed
            transactions.append(
                TxSeed(
                    key=f"{transfer}:{code}",
                    days_ago=1,
                    local_time=time(20),
                    kind="transfer",
                    jar_code=code,
                    amount_vnd=signed,
                    merchant=None,
                    note="Để riêng tiền trả nghĩa vụ",
                    tx_type=TX_TYPE_JAR_TRANSFER,
                    transfer_key=transfer,
                )
            )
        credit_due_day = 3
    jars = tuple(
        JarSeed(
            code=j.code,
            name=j.name,
            color_key=j.color_key,
            icon_key=j.icon_key,
            kind=j.kind,
            split_percent=Decimal(j.split_percent),
            balance_vnd=balances[j.code],
            sort_order=j.sort_order,
            goal_vnd=j.goal_vnd,
            goal_date=j.goal_date,
        )
        for j in layout
    )
    events = []
    for event in data.salary_events:
        amounts: Counter[str] = Counter()
        for code, value in event.split:
            amounts[JAR_ALIASES.get(code, code)] += value
        events.append(replace(event, split=tuple(amounts.items())))

    transactions.sort(key=lambda t: (-t.days_ago, t.local_time, t.key))
    return replace(
        data,
        jars=jars,
        transactions=tuple(transactions),
        obligations=tuple(replace(ob, pay_jar=DEFAULT_OBLIGATION_JAR) for ob in data.obligations),
        salary_events=tuple(events),
        credit_due_day=credit_due_day,
    )
