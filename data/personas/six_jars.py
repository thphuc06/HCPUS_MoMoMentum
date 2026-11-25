"""Adapt the historical demo ledgers for the six-jar Reset data flow."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import time
from decimal import Decimal
from typing import Any

from personas.generator import JarSeed, PersonaData, PersonaError, TxSeed
from yofina_core.wallet import (
    DEFAULT_GOAL_JAR,
    DEFAULT_OBLIGATION_JAR,
    DEFAULT_SPENDING_JAR,
    TX_TYPE_JAR_TRANSFER,
)

JAR_ALIASES = {
    "an_uong": DEFAULT_SPENDING_JAR,
    "di_lai": DEFAULT_SPENDING_JAR,
    "giai_tri": DEFAULT_SPENDING_JAR,
    "hoa_don": DEFAULT_OBLIGATION_JAR,
    "du_lich": DEFAULT_GOAL_JAR,
}


def use_default_jars(data: PersonaData, templates: Iterable[Mapping[str, Any]]) -> PersonaData:
    """Preserve demo history, its net balances, and the original target date."""
    defaults = [t for t in templates if t["is_default"]]
    if len(defaults) != 6 or sum(t["default_split_percent"] for t in defaults) != 100:
        raise PersonaError("Danh mục hũ mặc định phải có sáu hũ với tổng tỷ lệ 100%.")

    mapped = [
        replace(t, jar_code=JAR_ALIASES.get(t.jar_code, t.jar_code)) for t in data.transactions
    ]
    transfers: dict[str, list] = defaultdict(list)
    for t in mapped:
        if t.transfer_key and t.tx_type == "jar_transfer":
            transfers[t.transfer_key].append(t)
    collapsed = {
        key
        for key, pair in transfers.items()
        if len(pair) == 2
        and pair[0].jar_code == pair[1].jar_code
        and pair[0].amount_vnd + pair[1].amount_vnd == 0
    }
    transactions = tuple(t for t in mapped if t.transfer_key not in collapsed)

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
            transactions += (
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
                ),
            )
        credit_due_day = 3
    old_goal = next((j for j in data.jars if j.code == "du_lich"), None)
    jars = tuple(
        JarSeed(
            code=t["code"],
            name=t["name"],
            color_key=t["color_key"],
            icon_key=t["icon_key"],
            kind=t["kind"],
            split_percent=Decimal(str(t["default_split_percent"])),
            balance_vnd=balances[t["code"]],
            sort_order=t["sort_order"],
            goal_vnd=old_goal.goal_vnd if old_goal and t["code"] == DEFAULT_GOAL_JAR else None,
            goal_date=old_goal.goal_date if old_goal and t["code"] == DEFAULT_GOAL_JAR else None,
        )
        for t in defaults
    )
    events = []
    for event in data.salary_events:
        amounts: Counter[str] = Counter()
        for code, value in event.split:
            amounts[JAR_ALIASES.get(code, code)] += value
        events.append(replace(event, split=tuple(amounts.items())))

    return replace(
        data,
        jars=jars,
        transactions=transactions,
        obligations=tuple(replace(ob, pay_jar=DEFAULT_OBLIGATION_JAR) for ob in data.obligations),
        salary_events=tuple(events),
        credit_due_day=credit_due_day,
    )
