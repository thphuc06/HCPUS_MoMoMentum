"""Chi phí của một món mua bằng Trả sau (mô phỏng) và tác động lên nghĩa vụ. Dùng chung cho `run_scenario` (kịch bản
`bnpl_purchase`) và `affordability_check` (nguồn tín dụng); thuần hàm, không I/O.

Quy tắc phí (quyết định số 5 phase 2, `contracts/README.md` mục "Chi phí của món này và tổng phải trả ngày đến hạn"): phí dịch vụ tính
MỘT lần cho mỗi nghĩa vụ (mỗi nghĩa vụ ứng với một tháng có giao dịch). Hai bất biến của `CreditCost`:

    item_cost_vnd = principal_vnd + fee_added_vnd          # chi phí của món này
    total_due_vnd = existing_due_vnd + item_cost_vnd       # tổng phải trả ngày đến hạn, cộng dồn

`fee_added_vnd` là 0 khi ngày đến hạn đó đã có nghĩa vụ Trả sau (phí đã nằm trong đó). Số tiền phí lấy từ bảng `fee_schedules`
(`ReferenceData`), không có số nào gắn cứng trong mã.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.money import format_vnd
from yofina_forecast.common import STATUS_WORD, clip, dm, worst


def available_credit(line: Mapping[str, Any] | None) -> tuple[int, int] | None:
    """(hạn mức, còn lại) của hạn mức đang hoạt động; None nếu không có."""
    if not line or line.get("status") != "active":
        return None
    limit = int(line["limit_vnd"])
    return limit, limit - int(line["outstanding_vnd"])


def compute_credit_cost(
    *,
    principal_vnd: int,
    due_date: date,
    existing_due_vnd: int | None,
    product_label: str,
    line: Mapping[str, Any] | None,
    fee: Any | None,
    late_fee: Any | None = None,
) -> dict[str, Any]:
    """`CreditCost` của một món `principal_vnd` đến hạn `due_date`.

    `existing_due_vnd`: tổng nghĩa vụ Trả sau đã có ngày đó (None hoặc 0 nếu chưa có; phí 33.000 đã nằm trong số này).
    `fee`, `late_fee`: dòng `FeeRow` đang hiệu lực (phí hằng tháng, phí trả chậm nếu biểu phí có nguồn). Không có hạn mức hoạt
    động hoặc vượt hạn mức thì CREDIT_LIMIT_EXCEEDED."""
    limits = available_credit(line)
    if limits is None:
        raise YofinaError(
            ErrorCode.CREDIT_LIMIT_EXCEEDED,
            f"Bạn chưa có hạn mức {product_label} đang hoạt động.",
        )
    limit, available = limits
    if principal_vnd > available:
        raise YofinaError(
            ErrorCode.CREDIT_LIMIT_EXCEEDED,
            f"Vượt hạn mức {product_label}: còn {format_vnd(available)}.",
        )
    existing = existing_due_vnd or 0
    fee_amount = int(fee.amount_vnd) if fee is not None and fee.amount_vnd is not None else 0
    fee_added = 0 if existing > 0 else fee_amount
    item_cost = principal_vnd + fee_added
    cost: dict[str, Any] = {
        "product_label": product_label[:60],
        "principal_vnd": principal_vnd,
        "fee_added_vnd": fee_added,
        "item_cost_vnd": item_cost,
        "due_date": due_date.isoformat(),
        "existing_due_vnd": existing,
        "total_due_vnd": existing + item_cost,
        "limit_vnd": limit,
        "available_before_vnd": available,
        "available_after_vnd": available - principal_vnd,
    }
    if fee_added > 0 and fee is not None:
        cost["fee"] = {
            "fee_type": fee.fee_type,
            "amount_vnd": fee_added,
            "source_name": fee.source_name[:200],
            "effective_from": fee.effective_from.isoformat(),
        }
    if late_fee is not None and late_fee.amount_vnd is not None:
        cost["late_penalty_vnd"] = int(late_fee.amount_vnd)
    return cost


def jar_at_due(
    *,
    jar: Mapping[str, Any],
    days: Sequence[tuple[date, int, int, int]],
    due_date: date,
    due_vnd: int,
    short_floor_vnd: int,
    tight_floor_vnd: int,
) -> dict[str, Any]:
    """`JarAtDue`: hũ trả nghĩa vụ có đủ tiền khi đến hạn không, đọc từ chuỗi số dư SAU khi áp đề xuất (mỗi phần tử: ngày, P10,
    P50, P90 cuối ngày). `due_vnd` là TỔNG hũ này phải trả ngày đó (gồm khoản mới). Số dư cuối ngày đến hạn đã trừ mọi khoản
    ngày đó và đã cộng tiền vào cùng ngày (lương), nên `balance_before_due_vnd = P50 + due_vnd` và
    `shortfall = max(0, ngưỡng - P50)`. Ngày đến hạn ngoài chuỗi thì dùng ngày gần nhất trong chuỗi."""
    row = next((d for d in days if d[0] == due_date), None)
    if row is None:
        row = days[0] if due_date < days[0][0] else days[-1]
    _day, p10, p50, _p90 = row
    shortfall = max(0, short_floor_vnd - p50)
    if p50 < short_floor_vnd:
        status = "short"
    elif p10 < tight_floor_vnd:
        status = "tight"
    else:
        status = "ok"
    return {
        "jar": {
            "code": jar["code"],
            "name": jar["name"],
            "color_key": jar["color_key"],
            "icon_key": jar["icon_key"],
            **({"purpose": jar["purpose"]} if jar.get("purpose") is not None else {}),
        },
        "status": status,
        "balance_before_due_vnd": p50 + due_vnd,
        "due_vnd": due_vnd,
        "shortfall_vnd": shortfall,
    }


def obligation_impact(
    *,
    cost: Mapping[str, Any],
    at_due: Sequence[Mapping[str, Any]],
    ratio: Mapping[str, Any] | None,
    cautions: Sequence[Mapping[str, Any]] | None,
    basis: Mapping[str, Any],
) -> dict[str, Any]:
    """`ObligationImpactData`. Trạng thái là nặng nhất của các hũ khi đến hạn, và HỤT nếu tỷ lệ nghĩa vụ trên thu nhập vượt ngưỡng
    của luật (đỏ kèm "không khuyến khích"). `headline` luôn có chữ Đủ, Sát hoặc Hụt."""
    status = worst(
        [a["status"] for a in at_due] + (["short"] if ratio and ratio["exceeds"] else [])
    )
    shortfall = sum(int(a["shortfall_vnd"]) for a in at_due)
    head = (
        f"{STATUS_WORD[status]}: {cost['product_label']}, món này tốn {format_vnd(cost['item_cost_vnd'])}, "
        f"ngày {dm(cost['due_date'])} phải trả tổng {format_vnd(cost['total_due_vnd'])}"
    )
    if shortfall > 0:
        head += f"; hũ {at_due[0]['jar']['name']} hụt {format_vnd(shortfall)}"
    elif ratio and ratio["exceeds"]:
        head += "; nghĩa vụ vượt mức nên giữ so với thu nhập"
    out: dict[str, Any] = {
        "status": status,
        "headline": clip(head + ".", 160),
        "cost": dict(cost),
        "at_due": [dict(a) for a in at_due][:8],
        "shortfall_vnd": shortfall,
        "basis": dict(basis),
    }
    if ratio is not None:
        out["ratio"] = dict(ratio)
    if cautions:
        out["cautions"] = [dict(c) for c in cautions][:3]
    return out
