"""Đổi dòng DB (Data API hoặc jsonb) sang JSON theo hợp đồng (`contracts/tools/ledger.results.schema.json`, OpenAPI).

Dòng từ `DataApi.query` mang kiểu Python (`Decimal`, `date`, `datetime`); dòng nằm trong `jsonb` do hàm `app_get_overview` và
`app_get_jar_detail` dựng mang kiểu JSON (số, chuỗi ISO). Mọi hàm ở đây nhận cả hai để REST và tool dùng chung một dạng.
Tiền luôn ra số nguyên VND; trường vắng (None) thì bỏ khỏi JSON (hợp đồng dùng `additionalProperties: false`).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from yofina_core.blocks import format_instant
from yofina_core.money import to_vnd


def vnd(value: Any) -> int:
    """Số tiền từ Decimal, chuỗi, số nguyên hoặc số thực JSON (jsonb numeric có thể ra `30.0`)."""
    if isinstance(value, bool):
        raise TypeError("bool không phải số tiền")
    if isinstance(value, float):
        value = Decimal(str(value))
    return to_vnd(value)


def percent(value: Any) -> int | float:
    """Tỷ lệ phần trăm: số nguyên nếu tròn, ngược lại số thực (khớp `blocks._percent`)."""
    p = Decimal(str(value))
    return int(p) if p == p.to_integral_value() else float(p)


def to_date(value: Any) -> date | None:
    if value is None or (isinstance(value, date) and not isinstance(value, datetime)):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def to_instant(value: Any) -> datetime | None:
    """Thời điểm có múi giờ: nhận `datetime` hoặc chuỗi ISO (jsonb ra `2026-11-22T03:00:00.123456+00:00`)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip().replace(" ", "T", 1)
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def instant_text(value: Any) -> str | None:
    dt = to_instant(value)
    return format_instant(dt) if dt else None


def _drop_none(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def tx_json(row: Mapping[str, Any]) -> dict[str, Any]:
    """Một dòng sổ cái theo `Transaction` (có thể là dòng của `app_*` hoặc phần tử jsonb)."""
    jar = row.get("jar_code")
    out: dict[str, Any] = {
        "id": str(row["id"]),
        "occurred_at": instant_text(row["occurred_at"]),
        "app_date": to_date(row["app_date"]).isoformat(),  # type: ignore[union-attr]
        "kind": row["kind"],
        "amount_vnd": vnd(row["amount_vnd"]),
    }
    out.update(
        _drop_none(
            {
                "jar": jar or None,
                "merchant": row.get("merchant") or None,
                "note": row.get("note") or None,
                "transfer_id": str(row["transfer_id"]) if row.get("transfer_id") else None,
                "tx_type": row.get("tx_type") or None,
                "funding_source": row.get("funding_source") or None,
                "payee_id": str(row["payee_id"]) if row.get("payee_id") else None,
                "payee_name": row.get("payee_name") or None,
                "obligation_id": str(row["obligation_id"]) if row.get("obligation_id") else None,
            }
        )
    )
    if row.get("needs_review") is not None:
        out["needs_review"] = bool(row["needs_review"])
    return out


def obligation_json(row: Mapping[str, Any]) -> dict[str, Any]:
    """Một nghĩa vụ theo `Obligation` (`pay_jar_code` của DB thành `pay_jar`)."""
    out: dict[str, Any] = {
        "id": str(row["id"]),
        "kind": row["kind"],
        "name": row["name"],
        "amount_vnd": vnd(row["amount_vnd"]),
        "fee_vnd": vnd(row["fee_vnd"]),
        "due_date": to_date(row["due_date"]).isoformat(),  # type: ignore[union-attr]
        "cycle": row["cycle"],
        "status": row["status"],
        "is_essential": bool(row["is_essential"]),
        "source": row["source"],
    }
    for src, dst in (
        ("amount_min_vnd", "amount_min_vnd"),
        ("amount_max_vnd", "amount_max_vnd"),
        ("principal_vnd", "principal_vnd"),
    ):
        if row.get(src) is not None:
            out[dst] = vnd(row[src])
    if row.get("due_day") is not None:
        out["due_day"] = int(row["due_day"])
    if row.get("pay_jar_code"):
        out["pay_jar"] = row["pay_jar_code"]
    if row.get("paid_at") is not None:
        out["paid_at"] = instant_text(row["paid_at"])
    return out


def credit_line_json(row: Mapping[str, Any], label: str) -> dict[str, Any]:
    limit, outstanding = vnd(row["limit_vnd"]), vnd(row["outstanding_vnd"])
    return {
        "product_code": row["product_code"],
        "product_label": label,
        "limit_vnd": limit,
        "outstanding_vnd": outstanding,
        "available_vnd": max(limit - outstanding, 0),
        "due_day": int(row["due_day"]),
        "status": row["status"],
    }


def payee_json(row: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": str(row["id"]),
        "name": row["name"],
        "is_favorite": bool(row["is_favorite"]),
    }
    if row.get("account_hint"):
        out["account_hint"] = row["account_hint"]
    if row.get("last_used_at") is not None:
        out["last_used_at"] = instant_text(row["last_used_at"])
    return out


def salary_event_json(row: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": str(row["id"]),
        "period_date": to_date(row["period_date"]).isoformat(),  # type: ignore[union-attr]
        "received_on": to_date(row["received_on"]).isoformat(),  # type: ignore[union-attr]
        "amount_vnd": vnd(row["amount_vnd"]),
        "deviation_percent": float(Decimal(str(row["deviation_percent"]))),
        "ask_update_salary": bool(row["ask_update_salary"]),
        "status": row["status"],
    }
    if row.get("expected_vnd") is not None:
        out["expected_vnd"] = vnd(row["expected_vnd"])
    if row.get("confirmed_at") is not None:
        out["confirmed_at"] = instant_text(row["confirmed_at"])
    return out


def jar_full_json(
    row: Mapping[str, Any], forecast: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Một hũ theo `JarFull`; `forecast` là dòng tóm tắt dự báo MỚI NHẤT của hũ (nếu có)."""
    out: dict[str, Any] = {
        "code": row["code"],
        "name": row["name"],
        "color_key": row["color_key"],
        "icon_key": row["icon_key"],
        "kind": row["kind"],
        "balance_vnd": vnd(row["balance_vnd"]),
        "split_percent": percent(row["split_percent"]),
    }
    if row.get("system_role"):
        out["system_role"] = row["system_role"]
    if row.get("goal_vnd") is not None:
        out["goal_vnd"] = vnd(row["goal_vnd"])
    if row.get("purpose") is not None:
        out["purpose"] = row["purpose"]
    if row.get("sinking_items"):
        out["sinking_items"] = row["sinking_items"]
    if row.get("goal_date") is not None:
        out["goal_date"] = to_date(row["goal_date"]).isoformat()  # type: ignore[union-attr]
    if forecast is not None:
        out["status"] = forecast["status"]
        out["confidence_band"] = forecast["confidence_band"]
        if forecast.get("runout_date_shown") is False:
            # hũ thưa (#25, cột của migration 0055): không nêu ngày cạn, giao diện nói "có thể cạn trước ngày lương"
            out["runout_date_shown"] = False
        elif forecast.get("runout_date"):
            out["runout_date"] = to_date(forecast["runout_date"]).isoformat()  # type: ignore[union-attr]
        if forecast.get("forecast_floor_vnd") is not None:
            out["forecast_floor_vnd"] = vnd(forecast["forecast_floor_vnd"])
        if forecast.get("show_probability") and forecast.get("p_shortfall") is not None:
            out["p_shortfall"] = float(Decimal(str(forecast["p_shortfall"])))
    return out
