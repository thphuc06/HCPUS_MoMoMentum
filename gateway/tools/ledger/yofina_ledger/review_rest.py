"""REST của danh sách "Xem lại" và hỏi gộp (F2, phase 4 luồng B): `GET /review` và `POST /review/daily-ask/skip`.

Nối vào `rest_api._dispatch` bằng MỘT khối chuyển tiếp cho tiền tố `/review`. Hai endpoint đều thuộc Lambda ledger, danh tính chỉ lấy từ claim
`sub` do `rest_api` truyền vào.

- `GET /review?mode=review|daily_ask&limit=`: khối `review_list` (cả phong bì khối). Chỉ đọc: việc mở "câu hỏi gộp của hôm nay" do pipeline
  phân loại ghi (`classify_write.upsert_review_ask`). Chưa có dòng của hôm nay thì `ask.status` là `open` (sắp hỏi).
- `POST /review/daily-ask/skip {ask_date}`: ghi `skipped` cho câu hỏi gộp của ngày đó (các giao dịch vẫn ở Chưa phân loại, hôm nay không
  hỏi lại). Không đổi số dư, không qua token. Idempotent; đã `answered` thì trả `answered`. Ngày không có câu hỏi thì 400.

Sửa hũ KHÔNG có đường ghi riêng ở đây: dùng `assign_jar` qua `POST /confirmations` rồi `POST /actions` (ADR-0002).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from yofina_core.blocks import block_to_wire, build_review_list
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.money import format_vnd
from yofina_ledger import convert, review_reads


def _query(event: Mapping[str, Any]) -> Mapping[str, Any]:
    return event.get("queryStringParameters") or {}


def dispatch(
    route: str, event: Mapping[str, Any], sub: str, trace_id: str, service: Any
) -> tuple[int, dict[str, Any]]:
    if route == "GET /review":
        q = _query(event)
        return 200, review_response(
            service,
            sub,
            trace_id=trace_id,
            mode=review_reads.parse_mode(q.get("mode")),
            limit=review_reads.parse_limit(q.get("limit")),
        )
    if route == "POST /review/daily-ask/skip":
        from yofina_ledger import rest_api  # nhập muộn: rest_api nhập module này

        return 200, skip_response(service, sub, rest_api._body(event))
    raise YofinaError(ErrorCode.PARAMS_INVALID, "Đường dẫn không tồn tại.")


def headline(mode: str, count: int, total_vnd: int) -> str:
    """Câu mở đầu do code dựng (không do model viết)."""
    if mode == "daily_ask":
        if count == 0:
            return "Không có giao dịch nào cần hỏi."
        return f"Hôm nay mình chưa xếp được hũ cho {count} giao dịch, tổng {format_vnd(total_vnd)}."
    if count == 0:
        return "Không có giao dịch nào cần xem lại."
    return f"Mình đã tự xếp {count} giao dịch vào hũ, bạn xem lại giúp nhé (tổng {format_vnd(total_vnd)})."


def review_response(
    service: Any, user_id: str, *, trace_id: str, mode: str, limit: int
) -> dict[str, Any]:
    now = service.now()
    db = service.repo.db
    view = service.repo.jar_view(user_id)
    today = service._app_date(view.clock_offset_days or 0, now)
    jars = [
        {
            "code": j["code"],
            "name": j["name"],
            "color_key": j["color_key"],
            "icon_key": j["icon_key"],
        }
        for j in view.jars
        if j.get("code") and j.get("kind") != "system"
    ]
    names = {j["code"]: j["name"] for j in jars}
    tx_types = service.ref.tx_types()
    type_defaults = {code: info.default_jar_code for code, info in tx_types.items()}
    rows = review_reads.list_rows(db, user_id, mode, limit)
    count = int(rows[0]["total_count"]) if rows else 0
    total = convert.vnd(rows[0]["total_vnd"]) if rows else 0

    picked: list[tuple[Mapping[str, Any], list[str]]] = []
    entries: list[dict[str, Any]] = []
    for r in rows:
        suggested = [c for c in (r.get("suggested_jars") or [])[:2] if c in names]
        if not suggested and mode == "daily_ask":
            default = type_defaults.get(r.get("tx_type") or "")
            if default in names:
                suggested = [str(default)]
        picked.append((r, suggested))
        entries.extend(
            {
                "tx_id": r["transaction_id"],
                "jar_code": c,
                "payee_id": r.get("payee_id"),
                "merchant": r.get("merchant"),
            }
            for c in suggested
        )
    counts = review_reads.history_counts(db, user_id, entries)
    jar_by_code = {j["code"]: j for j in jars}
    items: list[dict[str, Any]] = []
    for r, suggested in picked:
        sugg = review_reads.suggestion_entries(
            str(r["transaction_id"]),
            suggested,
            jar_names=names,
            payee_id=r.get("payee_id"),
            merchant=r.get("merchant"),
            tx_type=r.get("tx_type"),
            note=r.get("note"),
            type_defaults=type_defaults,
            counts=counts,
            confidence=r.get("classification_confidence"),
        )
        item: dict[str, Any] = {
            "transaction_id": str(r["transaction_id"]),
            "occurred_at": convert.instant_text(r["occurred_at"]),
            "app_date": convert.to_date(r["app_date"]).isoformat(),  # type: ignore[union-attr]
            "kind": r["kind"],
            "amount_vnd": review_reads.amount_positive(r),
            "tier": "ask" if mode == "daily_ask" else "review",
            "suggestions": [
                {
                    "jar": jar_by_code[s["code"]],
                    "reason": s["reason"],
                    **({"confidence": s["confidence"]} if "confidence" in s else {}),
                }
                for s in sugg
            ],
            "can_remember": review_reads.can_remember(r),
        }
        cp = review_reads.counterparty_of(r)
        if cp:
            item["counterparty"] = cp
        if r.get("note"):
            item["note"] = str(r["note"])[:200]
        if r.get("jar_code") and r.get("jar_name"):
            item["current_jar"] = {"code": r["jar_code"], "name": str(r["jar_name"])[:40]}
        if r.get("classified_by"):
            item["classified_by"] = r["classified_by"]
        if r.get("classification_confidence") is not None:
            item["confidence"] = round(float(r["classification_confidence"]), 3)
        items.append(item)

    data: dict[str, Any] = {
        "mode": mode,
        "headline": headline(mode, count, total),
        "count": count,
        "pending_total_vnd": total,
        "items": items,
        "jars": jars[:20],
    }
    if mode == "daily_ask":
        row = review_reads.ask_row(db, user_id, today)
        data["ask"] = {"ask_date": today.isoformat(), "status": row["status"] if row else "open"}
    block = build_review_list(
        data=data,
        trace_id=trace_id,
        source_tool="rest:GET /review",
        as_of=now,
        app_date=today,
    )
    return block_to_wire(block)


def skip_response(service: Any, user_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
    raw = body.get("ask_date")
    try:
        ask_date = date.fromisoformat(str(raw))
    except (TypeError, ValueError):
        raise YofinaError(
            ErrorCode.PARAMS_INVALID, "ask_date phải là ngày dạng YYYY-MM-DD."
        ) from None
    if not isinstance(raw, str) or len(raw) != 10:
        raise YofinaError(ErrorCode.PARAMS_INVALID, "ask_date phải là ngày dạng YYYY-MM-DD.")
    db = service.repo.db
    with db.transaction(user_id) as t:
        rows = t.execute(
            "SELECT status FROM review_asks WHERE user_id = :uid AND ask_date = CAST(:d AS date)",
            {"uid": user_id, "d": ask_date},
        )
        if not rows:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Ngày này không có câu hỏi gộp.")
        status = rows[0]["status"]
        if status == "open":
            t.execute(
                "UPDATE review_asks SET status = 'skipped', resolved_at = now() "
                "WHERE user_id = :uid AND ask_date = CAST(:d AS date) AND status = 'open'",
                {"uid": user_id, "d": ask_date},
            )
            status = "skipped"
    return {"ask_date": ask_date.isoformat(), "status": status}
