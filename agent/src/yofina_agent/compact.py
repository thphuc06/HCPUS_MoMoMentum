"""Bản gọn của kết quả tool: thứ duy nhất model nhìn thấy (và `TOOL_CALL_RESULT` mang).

Khối UI đầy đủ (màu, biểu tượng, tỷ lệ chia...) đi riêng ra frontend bằng `ACTIVITY_SNAPSHOT`.
Mỗi số tiền kèm chuỗi đã định dạng (`*_text`) để model chép nguyên văn thay vì tự tính.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from yofina_agent.textutil import extract_amounts
from yofina_core.money import format_vnd, to_vnd


def compact_jars(payload: Mapping[str, Any]) -> dict[str, Any]:
    """`get_jar_balances` -> {app_date, total, jars[{code,name,balance_vnd,balance_text}]}."""
    data = payload["data"]
    jars = [
        {
            "code": j["code"],
            "name": j["name"],
            "balance_vnd": to_vnd(j["balance_vnd"]),
            "balance_text": format_vnd(j["balance_vnd"]),
        }
        for j in data["jars"]
    ]
    total = sum(j["balance_vnd"] for j in jars)
    return {
        "app_date": payload["app_date"],
        "jars_total_vnd": total,
        "jars_total_text": format_vnd(total),
        "jars": jars,
    }


def compact_transactions(
    payload: Mapping[str, Any], jar_names: Mapping[str, str], limit: int
) -> dict[str, Any]:
    data = payload["data"]
    rows = []
    for t in data["transactions"][:limit]:
        amount = to_vnd(t["amount_vnd"])
        rows.append(
            {
                "date": t["app_date"],
                "kind": t["kind"],
                "jar": jar_names.get(t.get("jar", ""), t.get("jar")),
                "amount_vnd": amount,
                "amount_text": format_vnd(amount),
                "merchant": t.get("merchant"),
                "note": t.get("note"),
            }
        )
    return {
        "app_date": payload["app_date"],
        "shown": len(rows),
        "has_more": bool(data["has_more"]) or len(data["transactions"]) > len(rows),
        "transactions": [{k: v for k, v in r.items() if v is not None} for r in rows],
    }


def compact_confirm(data: Mapping[str, Any]) -> dict[str, Any]:
    """`NEEDS_CONFIRMATION` -> bản gọn; không có `params_hash` (model không cần và không được đụng)."""
    p, prev = data["params"], data["preview"]
    return {
        "status": "NEEDS_CONFIRMATION",
        "summary": data["summary"],
        "amount_vnd": p["amount_vnd"],
        "amount_text": format_vnd(p["amount_vnd"]),
        "from_jar": {
            "name": prev["from"]["name"],
            "balance_before_text": format_vnd(prev["from"]["before_vnd"]),
            "balance_after_text": format_vnd(prev["from"]["after_vnd"]),
        },
        "to_jar": {
            "name": prev["to"]["name"],
            "balance_before_text": format_vnd(prev["to"]["before_vnd"]),
            "balance_after_text": format_vnd(prev["to"]["after_vnd"]),
        },
        "expires_at": data["expires_at"],
        "note": "Chưa có khoản tiền nào được chuyển; người dùng phải bấm Xác nhận trên thẻ.",
    }


_STATUS_VI = {"ok": "đủ", "tight": "sát", "short": "hụt"}
_BAND_VI = {"high": "Cao", "medium": "Vừa", "low": "Thấp"}
FORECAST_EVENTS_SHOWN = 3


def _dm(value: str) -> str:
    d = date.fromisoformat(value)
    return f"{d.day:02d}/{d.month:02d}"


def compact_forecast(payload: Mapping[str, Any]) -> dict[str, Any]:
    """`forecast___get_forecast` -> bản gọn cho model viết 1 đến 2 câu: trạng thái, ngày cạn, kỳ lương, độ tin cậy.

    Ngày dạng `dd/mm` và số tiền kèm chuỗi `*_text` để model chép nguyên văn; không có đường P10/P90 theo ngày (đã nằm trong khối UI).
    """
    d = payload["data"]
    origin = date.fromisoformat(d["origin_date"])
    payday = d["payday"]
    start = to_vnd(d["start_balance_vnd"])
    before_payday = [x["p50_vnd"] for x in d["days"] if x["date"] < payday["date"]]
    out: dict[str, Any] = {
        "app_date": payload["app_date"],
        "jar": d["jar"]["name"],
        "status": _STATUS_VI[d["status"]],
        "balance_now_vnd": start,
        "balance_now_text": format_vnd(start),
        "payday": {"date_text": _dm(payday["date"]), "days_until": payday["days_until"]},
        "confidence": _BAND_VI[d["confidence_band"]],
        "is_initial_estimate": bool(d["is_initial_estimate"]),
        "stale": bool(d["stale"]),
    }
    if d.get("runout_date"):
        runout = date.fromisoformat(d["runout_date"])
        out["runout"] = {
            "date_text": _dm(d["runout_date"]),
            "days_from_today": (runout - origin).days,
            "days_before_payday": (date.fromisoformat(payday["date"]) - runout).days,
        }
    else:
        out["runout"] = None  # không cạn trong kỳ dự báo
    if d.get("p_shortfall") is not None:
        out["p_shortfall_percent"] = round(float(d["p_shortfall"]) * 100)
    if before_payday:
        low = to_vnd(min(before_payday))
        out["lowest_balance_before_payday_vnd"] = low
        out["lowest_balance_before_payday_text"] = format_vnd(low)
    out["upcoming"] = [
        {
            "label": e["label"],
            "kind": "nghĩa vụ" if e["kind"] == "obligation" else "lương về",
            "date_text": _dm(e["date"]),
            "amount_vnd": to_vnd(e["amount_vnd"]),
            "amount_text": format_vnd(e["amount_vnd"]),
        }
        for e in d["events"][:FORECAST_EVENTS_SHOWN]
    ]
    return out


def allowed_amounts(compact: Mapping[str, Any]) -> set[int]:
    """Mọi số tiền (VND) xuất hiện trong bản gọn: căn cứ để kiểm số model viết ra."""
    found: set[int] = set()

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for k, v in node.items():
                if isinstance(v, int) and not isinstance(v, bool) and k.endswith("_vnd"):
                    found.add(abs(v))  # chi tiêu là số âm trong sổ cái nhưng được nói là số dương
                else:
                    walk(v)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    walk(compact)
    # số tiền cũng nằm trong các chuỗi *_text / summary (số dư trước và sau của thẻ xác nhận)

    def walk_text(node: Any) -> None:
        if isinstance(node, str):
            found.update(v for v, _ in extract_amounts(node))
        elif isinstance(node, Mapping):
            for v in node.values():
                walk_text(v)
        elif isinstance(node, list):
            for x in node:
                walk_text(x)

    walk_text(compact)
    return found
