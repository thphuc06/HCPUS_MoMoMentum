"""Bản gọn của kết quả tool: thứ duy nhất model nhìn thấy (và `TOOL_CALL_RESULT` mang).

Khối UI đầy đủ (màu, biểu tượng, tỷ lệ chia...) đi riêng ra frontend bằng `ACTIVITY_SNAPSHOT`.
Mỗi số tiền kèm chuỗi đã định dạng (`*_text`) để model chép nguyên văn thay vì tự tính.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from yofina_agent.textutil import extract_amounts
from yofina_core.blocks import no_outflow_expected
from yofina_core.money import format_vnd, to_vnd
from yofina_core.wallet import OBLIGATION_KIND_LABELS, resolve_obligation_pay_jar

#: Trường chữ chép nguyên từ giao dịch hoặc từ tệp người dùng nạp (đối tác, nội dung chuyển khoản, ghi chú), đã che PII nhưng không bỏ
#: chỉ dẫn: dữ liệu KHÔNG tin cậy. Prompt người viết đánh dấu chúng (`writer.build_writer_prompt`) và số trong chúng không bao giờ là
#: căn cứ (`allowed_amounts`, `writer.has_ungrounded_numbers`, bộ chấm `evals/run.py`).
UNTRUSTED_TEXT_KEYS = frozenset({"merchant", "note", "description", "counterparty"})


def has_untrusted_text(node: Any) -> bool:
    """Bản gọn (hoặc payload) có chữ không tin cậy: trường `UNTRUSTED_TEXT_KEYS` của một DÒNG (phần tử của danh sách: giao dịch, dòng
    nạp, mục cần duyệt). Trường cùng tên ở cấp ngoài (ví dụ `note` cố định của thẻ xác nhận) do code viết, không tính."""
    return without_untrusted_text(node) != node


def without_untrusted_text(node: Any, *, _in_row: bool = False) -> Any:
    """Bản sao bỏ chữ không tin cậy của các dòng (xem `has_untrusted_text`): thứ còn lại mới được làm căn cứ cho số."""
    if isinstance(node, Mapping):
        return {
            k: without_untrusted_text(v)
            for k, v in node.items()
            if not (_in_row and k in UNTRUSTED_TEXT_KEYS and isinstance(v, str))
        }
    if isinstance(node, list):
        return [without_untrusted_text(x, _in_row=True) for x in node]
    return node


def _compact_jar(j: Mapping[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "code": j["code"],
        "name": j["name"],
        "balance_vnd": to_vnd(j["balance_vnd"]),
        "balance_text": format_vnd(j["balance_vnd"]),
    }
    # Phase 4 (tùy chọn): loại hũ và mục tiêu GỐC; vắng thì không thêm khóa.
    if j.get("kind") is not None:
        row["kind"] = j["kind"]
    if j.get("purpose") is not None:
        row["purpose"] = j["purpose"]
    if j.get("goal_vnd") is not None:
        row["goal_vnd"] = to_vnd(j["goal_vnd"])
        row["goal_text"] = format_vnd(j["goal_vnd"])
    if j.get("goal_date") is not None:
        row["goal_date"] = j["goal_date"]
    if j.get("sinking_items"):
        row["sinking_items"] = j["sinking_items"]
    return row


def compact_jars(payload: Mapping[str, Any]) -> dict[str, Any]:
    """`get_jar_balances` -> {app_date, total, jars[{code,name,balance_vnd,balance_text,kind?,goal_vnd?,goal_text?,goal_date?}]}."""
    data = payload["data"]
    jars = [_compact_jar(j) for j in data["jars"]]
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
#: số khoản nghĩa vụ tối đa trong bản gọn (giữ ngữ cảnh gọn); cắt bớt thì bản gọn có `has_more` và `hidden_count`
OBLIGATIONS_SHOWN = 8


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
    if d.get("runout_date") and d.get("runout_date_shown") is not False:
        runout = date.fromisoformat(d["runout_date"])
        out["runout"] = {
            "date_text": _dm(d["runout_date"]),
            "days_from_today": (runout - origin).days,
            "days_before_payday": (date.fromisoformat(payday["date"]) - runout).days,
        }
    elif d.get("runout_date_shown") is False and d["status"] == "short":
        # hũ thưa (#25): ngày cạn sai trung bình hơn 6 ngày nên không đưa ngày (kể cả số ngày suy ra) để model không tự nói ngày
        out["runout"] = {"may_run_out_before_payday": True}
    else:
        out["runout"] = None  # không cạn trong kỳ dự báo
    if d.get("p_shortfall") is not None:
        out["p_shortfall_percent"] = round(float(d["p_shortfall"]) * 100)
    if no_outflow_expected(d):
        # #39: hũ 0 ₫ "đủ" vì không có gì để chi (hũ để dành chưa có tiền): dữ kiện cho model, không phải câu mẫu
        out["no_outflow_expected"] = True
    if before_payday:
        low = to_vnd(min(before_payday))
        out["lowest_balance_before_payday_vnd"] = low
        out["lowest_balance_before_payday_text"] = format_vnd(low)
    if (window := d.get("obligations_before_payday")) is not None:
        out["obligations_before_payday"] = window
        if first := window.get("first_shortfall"):
            out["first_shortfall_text"] = format_vnd(first["shortfall_vnd"])
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


def compact_forecast_overview(
    forecasts: list[Mapping[str, Any]], unavailable: list[str] | None = None
) -> dict[str, Any]:
    """Dự báo của MỌI hũ ("hũ nào sắp cạn?") từ các bản gọn `compact_forecast` của từng hũ.

    Hũ cạn TRƯỚC kỳ lương (runout.days_before_payday > 0) xếp theo ngày cạn sớm nhất; hũ không cạn trước kỳ lương nhưng trạng thái
    sát đứng riêng, cùng nhóm với hũ hụt không nêu được ngày cạn (hũ thưa, #25: `runout.may_run_out_before_payday`); còn lại là đủ.
    `unavailable`: tên hũ không lấy được dự báo. Chỉ chép số và ngày của tool, không tính thêm.
    """
    runout: list[dict[str, Any]] = []
    tight: list[str] = []
    ok: list[str] = []
    for f in forecasts:
        r = f.get("runout")
        if r and int(r.get("days_before_payday") or 0) > 0:
            runout.append(
                {
                    "jar": f["jar"],
                    "date_text": r["date_text"],
                    "days_from_today": r["days_from_today"],
                    "days_before_payday": r["days_before_payday"],
                }
            )
        elif f.get("status") == _STATUS_VI["tight"] or f.get("status") == _STATUS_VI["short"]:
            tight.append(f["jar"])
        else:
            ok.append(f["jar"])
    runout.sort(key=lambda x: (x["days_from_today"], x["jar"]))
    first = forecasts[0] if forecasts else {}
    return {
        "app_date": first.get("app_date"),
        "payday": first.get("payday"),
        "jars_checked": len(forecasts),
        "runout_before_payday": runout,
        "tight": tight,
        "enough": ok,
        "unavailable": list(unavailable or []),
    }


def allowed_amounts(compact: Mapping[str, Any]) -> set[int]:
    """Mọi số tiền (VND) xuất hiện trong bản gọn: căn cứ để kiểm số model viết ra. Chữ không tin cậy của các dòng (ghi chú, đối tác...,
    `without_untrusted_text`) không tính: số viết trong nội dung chuyển khoản của tệp nạp không thành "có căn cứ"."""
    found: set[int] = set()
    compact = without_untrusted_text(compact)

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


# --- phase 3: what-if, kiểm tra trước khi quẹt ----------------------------------------------------
def _pct(value: float | None) -> int | None:
    return None if value is None else round(float(value) * 100)


def _basis_compact(b: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "confidence": _BAND_VI[b["confidence_band"]],
        "is_initial_estimate": bool(b["is_initial_estimate"]),
        "history_days": b["history_days"],
        "stale": bool(b["stale"]),
    }


def compact_impact(d: Mapping[str, Any]) -> dict[str, Any]:
    """`ObligationImpactData` -> bản gọn: chi phí của món TÁCH khỏi tổng phải trả ngày đến hạn, hũ nào hụt."""
    c = d["cost"]
    out: dict[str, Any] = {
        "status": _STATUS_VI[d["status"]],
        "headline": d["headline"],
        "product": c["product_label"],
        "due_date_text": _dm(c["due_date"]),
        "item_cost_vnd": to_vnd(c["item_cost_vnd"]),
        "item_cost_text": format_vnd(c["item_cost_vnd"]),
        # gốc của món: món này tốn = gốc + phí phát sinh thêm (bất biến của hợp đồng); thiếu gốc thì model nhỏ coi cả số đó là phí (#39)
        "principal_vnd": to_vnd(c["principal_vnd"]),
        "principal_text": format_vnd(c["principal_vnd"]),
        "fee_added_vnd": to_vnd(c["fee_added_vnd"]),
        "fee_added_text": format_vnd(c["fee_added_vnd"]),
        "existing_due_vnd": to_vnd(c["existing_due_vnd"]),
        "existing_due_text": format_vnd(c["existing_due_vnd"]),
        "total_due_vnd": to_vnd(c["total_due_vnd"]),
        "total_due_text": format_vnd(c["total_due_vnd"]),
        "shortfall_vnd": to_vnd(d["shortfall_vnd"]),
        "shortfall_text": format_vnd(d["shortfall_vnd"]),
        "at_due": [
            {
                "jar": x["jar"]["name"],
                "status": _STATUS_VI[x["status"]],
                "balance_before_due_text": format_vnd(x["balance_before_due_vnd"]),
                "due_text": format_vnd(x["due_vnd"]),
                "shortfall_text": format_vnd(x["shortfall_vnd"]),
            }
            for x in d["at_due"]
        ],
        "basis": _basis_compact(d["basis"]),
    }
    if c.get("available_after_vnd") is not None:
        out["credit_available_after_text"] = format_vnd(c["available_after_vnd"])
    if d.get("ratio"):
        r = d["ratio"]
        out["obligation_to_income_percent"] = _pct(r["ratio"])
        out["obligation_to_income_threshold_percent"] = _pct(r["threshold"])
        out["obligation_to_income_exceeds"] = bool(r["exceeds"])
    if d.get("cautions"):
        out["cautions"] = [x["text"] for x in d["cautions"]]
    return out


def compact_scenario(payload: Mapping[str, Any]) -> dict[str, Any]:
    """`forecast___run_scenario` -> bản gọn cho Analyst (thứ DUY NHẤT nó thấy ngoài danh sách hũ): kịch bản, hiệu ứng từng hũ, nghĩa vụ."""
    d = payload["data"]
    spec = d["spec"]
    out: dict[str, Any] = {
        "app_date": payload["app_date"],
        "scenario": {"kind": spec["kind"], **{k: v for k, v in spec.items() if k not in ("kind",) and v is not None}},
        "effects": [],
        "basis": _basis_compact(d["basis"]),
    }
    if spec.get("amount_vnd") is not None:
        out["scenario"]["amount_text"] = format_vnd(spec["amount_vnd"])
    bundle = [b for b in (d.get("bundle") or []) if isinstance(b, Mapping)]
    if len(bundle) > 1:  # mô phỏng GỘP: các khoản người dùng vẫn giữ + khoản mới (khoản cuối là `scenario`)
        out["bundle"] = [
            {
                "label": str(b.get("label") or b.get("kind")),
                **({"amount_text": format_vnd(b["amount_vnd"])} if isinstance(b.get("amount_vnd"), int) else {}),
            }
            for b in bundle
        ]
        if isinstance(d.get("bundle_total_vnd"), int):
            out["bundle_total_text"] = format_vnd(d["bundle_total_vnd"])
    for e in d["effects"]:
        row: dict[str, Any] = {
            "jar": e["jar"]["name"],
            "jar_code": e["jar"]["code"],
            "status_before": _STATUS_VI[e["status_before"]],
            "status_after": _STATUS_VI[e["status_after"]],
        }
        if e.get("runout_date_after"):
            row["runout_after_date_text"] = _dm(e["runout_date_after"])
        if e.get("runout_date_before"):
            row["runout_before_date_text"] = _dm(e["runout_date_before"])
        if e.get("p_shortfall_before") is not None:
            row["p_shortfall_before_percent"] = _pct(e["p_shortfall_before"])
        if e.get("p_shortfall_after") is not None:
            row["p_shortfall_after_percent"] = _pct(e["p_shortfall_after"])
        if e.get("min_balance_delta_vnd") is not None:
            row["min_balance_delta_vnd"] = to_vnd(e["min_balance_delta_vnd"])
            row["min_balance_delta_text"] = format_vnd(e["min_balance_delta_vnd"])
        out["effects"].append(row)
    if d.get("obligation_impact"):
        out["obligation_impact"] = compact_impact(d["obligation_impact"])
    return out


def compact_affordability(payload: Mapping[str, Any]) -> dict[str, Any]:
    """`forecast___affordability_check` -> bản gọn cho model nhỏ viết hai câu: câu kết luận của engine + từng hũ + Trả sau."""
    d = payload["data"]
    out: dict[str, Any] = {
        "app_date": payload["app_date"],
        "verdict": _STATUS_VI[d["verdict"]],
        "headline": d["headline"],
        "amount_vnd": to_vnd(d["amount_vnd"]),
        "amount_text": format_vnd(d["amount_vnd"]),
        "funding_source": "Trả sau (mô phỏng)" if d["funding_source"] == "credit" else "tiền trong hũ",
        "jar_checks": [
            {
                "jar": c["jar"]["name"],
                "status": _STATUS_VI[c["status"]],
                "balance_after_text": format_vnd(c["balance_after_vnd"]),
                **(
                    {"runout_after_date_text": _dm(c["runout_date_after"])}
                    if c.get("runout_date_after")
                    else {}
                ),
            }
            for c in d["jar_checks"]
        ],
        "basis": _basis_compact(d["basis"]),
    }
    if d.get("label"):
        out["label"] = d["label"]
    if d.get("credit"):
        out["credit"] = compact_impact(d["credit"])
    return out


def compact_obligations(
    payload: Mapping[str, Any], *, jars: Sequence[Mapping[str, Any]] | None = None
) -> dict[str, Any]:
    """`get_obligations` -> bản gọn. Có `jars` (hũ người dùng: code, name, kind) thì mỗi khoản kèm HŨ TRẢ (`pay_jar_code`,
    `pay_jar_name`): hũ đã lưu ở khoản, không có thì hũ trả mặc định của ví (`wallet.resolve_obligation_pay_jar`, cùng quy tắc với dự
    báo); ví không có hũ trả nào thì không có hai khóa đó. Lộ trình cần dữ kiện này để không chuyển tiền vào một hũ "vì" khoản mà hũ
    khác trả (#39)."""
    d = payload["data"]
    names = {str(j["code"]): str(j["name"]) for j in jars or ()}
    # hũ của get_jar_balances là hũ người dùng (không có hũ hệ thống): bản tin cũ không có kind vẫn tính là hũ người dùng
    kinds = [(str(j["code"]), str(j.get("kind") or "spending")) for j in jars or ()]

    def pay_jar(o: Mapping[str, Any]) -> dict[str, str]:
        if jars is None:
            return {}
        code = resolve_obligation_pay_jar(kinds, saved=o.get("pay_jar"))
        return {"pay_jar_code": code, "pay_jar_name": names[code]} if code in names else {}

    rows = [
        {
            "name": o["name"],
            # nhãn tiếng Việt của bảng chung thay cho mã loại: model chép chữ có trong ngữ cảnh, nên mã thô lọt ra câu trả lời (#19)
            "kind_label": OBLIGATION_KIND_LABELS.get(o["kind"], "Nghĩa vụ"),
            "amount_vnd": to_vnd(o["amount_vnd"]),
            "amount_text": format_vnd(o["amount_vnd"]),
            "due_date_text": _dm(o["due_date"]),
            **pay_jar(o),
        }
        for o in d["obligations"][:OBLIGATIONS_SHOWN]
    ]
    out: dict[str, Any] = {
        "app_date": payload["app_date"],
        "obligations": rows,
        "total_due_vnd": to_vnd(d["total_due_vnd"]),
        "total_due_text": format_vnd(d["total_due_vnd"]),
        # danh sách bị cắt thì model biết còn khoản chưa hiện (tổng vẫn tính đủ mọi khoản), không coi danh sách là đủ (#39, T2)
        "has_more": len(d["obligations"]) > len(rows),
    }
    if out["has_more"]:
        out["hidden_count"] = len(d["obligations"]) - len(rows)
    return out


def compact_confirm_action(data: Mapping[str, Any]) -> dict[str, Any]:
    """`NEEDS_CONFIRMATION` của tool ghi khác chuyển hũ -> bản gọn (không có `params_hash`, model không cần và không được đụng)."""
    out: dict[str, Any] = {
        "status": "NEEDS_CONFIRMATION",
        "summary": data["summary"],
        "changes": [
            {k: c[k] for k in ("label", "before", "after") if c.get(k)} for c in data["changes"]
        ],
        "expires_at": data["expires_at"],
        "note": "Chưa lưu gì; người dùng phải bấm Xác nhận trên thẻ.",
    }
    if data.get("warnings"):
        out["warnings"] = list(data["warnings"])
    return out


def compact_resilience(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = payload["data"]
    weakest = next(c for c in data["components"] if c["key"] == data["weakest"])
    return {
        "score": data["score"],
        "band": data["band"],
        "weakest": {"label": weakest["label"], "explanation": weakest["explanation"]},
    }


def compact_stress(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = payload["data"]
    return {
        "shock_label": data["shock"]["label"],
        "score_before": data["score_before"],
        "score_after": data["score_after"],
        "runway_days_total": data.get("runway_days_total"),
        "runway_days_emergency": data.get("runway_days_emergency"),
        "shortfall_vnd": data["shortfall_vnd"],
        "shortfall_text": format_vnd(data["shortfall_vnd"]),
    }


def compact_roadmap(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Lộ trình cho writer (lượt xem): phiên bản, lý do, khả năng kịp mục tiêu, và các mục tiêu có cấu trúc (V5 của báo cáo rà soát #39):
    đích, hạn (hoặc `no_deadline` khi chưa có hạn), kịp hay không, phần thiếu, ngày dự kiến; `goals` rỗng là bản không có mục tiêu."""
    data = payload["data"]
    return {
        "version": data["version"],
        "status": data["status"],
        "reason": data["reason"]["text"],
        "feasibility": data["feasibility"],
        "goals": [_roadmap_goal(g) for g in data.get("goals") or []],
        "counts": data["counts"],
        "phase_count": len(data["phases"]),
        "step_titles": [step["title"] for phase in data["phases"] for step in phase["steps"]][:3],
    }


def _dmy(value: str) -> str:
    d = date.fromisoformat(value)
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def _roadmap_goal(g: Mapping[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {"jar": g["jar"]["name"], "target_text": format_vnd(g["target_vnd"])}
    if g.get("target_date"):
        row["target_date_text"] = _dmy(g["target_date"])
    else:
        row["no_deadline"] = True
    row["on_track"] = bool(g["on_track"])
    if g.get("shortfall_vnd"):
        row["shortfall_text"] = format_vnd(g["shortfall_vnd"])
    if g.get("projected_date"):
        row["projected_date_text"] = _dmy(g["projected_date"])
    return row


def compact_roadmap_steps(payload: Mapping[str, Any], jar_names: Mapping[str, str]) -> dict[str, Any]:
    """Lộ trình đang dùng cho lượt "sửa một bước": mọi bước kèm giai đoạn, số tiền (chuỗi đã định dạng), hũ nguồn và hũ đích (tên
    hũ thật của người dùng), hạn `dd/mm`. Model chỉ ra bước người dùng nói tới từ bản này, không tự tính hay đổi gì."""
    data = payload["data"]
    steps: list[dict[str, Any]] = []
    for phase in data["phases"]:
        for step in phase["steps"]:
            row: dict[str, Any] = {"phase": phase["title"], "title": step["title"]}
            if step.get("amount_vnd") is not None:
                row["amount_text"] = format_vnd(step["amount_vnd"])
            if step.get("jar_code"):
                row["from_jar"] = jar_names.get(step["jar_code"], step["jar_code"])
            if step.get("to_jar_code"):
                row["to_jar"] = jar_names.get(step["to_jar_code"], step["to_jar_code"])
            if step.get("due_date"):
                row["due_date_text"] = _dm(step["due_date"])
            steps.append(row)
    return {"version": data["version"], "status": data["status"], "steps": steps}
