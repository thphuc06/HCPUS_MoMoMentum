"""REST của bản tin chủ động (FR13, phase 5 luồng B): `GET /nudges/today` và `POST /nudges/{nudge_id}/feedback`.

Nối vào `rest_api._dispatch` bằng MỘT khối chuyển tiếp cho tiền tố `/nudges`. Danh tính chỉ lấy từ claim `sub` do `rest_api` truyền.

- `GET /nudges/today`: bản tin mà cổng giá trị của batch đêm đã ghi cho hôm nay mô phỏng (`app_get_today_nudge`), dựng thành khối
  `proactive_card` có `nudge_id` (`proactive.gate_card`). `suppressed` là danh sách loại cổng đã bỏ (lưu trong `gate_reason`). Giờ hiện
  tại (múi giờ ứng dụng) rơi vào giờ im lặng trong sở thích của người dùng (`service.nudge_preferences`, điểm móc
  `proactive.NudgePreferenceSource`) thì KHÔNG trả thẻ và thêm `{kind, reason: quiet_hours}`. Không ghi gì, không gọi model.
- `POST /nudges/{nudge_id}/feedback {outcome, reason?}`: `app_set_nudge_outcome` (idempotent) cộng một dòng `feedback` (`block_id` là
  id thẻ, `option_id` là loại bản tin; `acted` là accepted, còn lại rejected). Không đổi số dư nên không qua token. Không phải bản tin
  của cổng của chính người gọi thì 404 `NUDGE_NOT_FOUND`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from yofina_core.blocks import block_to_wire, format_instant
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.wallet import NUDGE_OUTCOMES
from yofina_ledger import convert, proactive

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
FEEDBACK_FIELDS = frozenset({"outcome", "reason"})
SQL_SET_OUTCOME = "SELECT * FROM app_set_nudge_outcome(CAST(:uid AS text), CAST(:id AS uuid), CAST(:outcome AS text))"
SQL_NUDGE_FOR_FEEDBACK = (
    "SELECT kind, trace_id FROM nudges WHERE user_id = :uid AND id = CAST(:id AS uuid) AND source = 'system' LIMIT 1"
)
SQL_UPSERT_FEEDBACK = (
    "INSERT INTO feedback (user_id, trace_id, block_id, option_id, decision, reason) "
    "VALUES (:uid, :trace_id, :block_id, :option_id, :decision, :reason) "
    "ON CONFLICT (user_id, trace_id, block_id, option_id) DO UPDATE SET decision = EXCLUDED.decision, "
    "reason = EXCLUDED.reason, updated_at = now()"
)


def dispatch(
    route: str, event: Mapping[str, Any], sub: str, trace_id: str, service: Any
) -> tuple[int, dict[str, Any]]:
    if route == "GET /nudges/today":
        return 200, today_response(service, sub)
    if route.startswith("POST /nudges/") and route.endswith("/feedback"):
        from yofina_ledger import rest_api  # nhập muộn: rest_api nhập module này

        nudge_id = rest_api._path_param(event, "nudge_id", "/nudges/").removesuffix("/feedback").strip("/")
        return 200, feedback_response(service, sub, nudge_id, rest_api._body(event), trace_id=trace_id)
    raise YofinaError(ErrorCode.PARAMS_INVALID, "Đường dẫn không tồn tại.")


def _today(service: Any, user_id: str) -> Any:
    return service._app_date(service.repo.clock_offset(user_id), service.now())


def nudge_wire(row: Mapping[str, Any], app_date: str) -> dict[str, Any]:
    """`Nudge` của hợp đồng từ một dòng `app_get_today_nudge` (`gate` chỉ giữ năm khóa của `NudgeGate`)."""
    reason = row.get("gate_reason") or {}
    gate = {k: reason[k] for k in proactive.GATE_REASON_KEYS if k in reason}
    out: dict[str, Any] = {
        "nudge_id": str(row["id"]),
        "kind": row["kind"],
        "app_date": app_date,
        "title": row["title"],
        "reason": row["body"],
        "gate": gate,
    }
    if row.get("jar_code"):
        out["jar_code"] = row["jar_code"]
    if row.get("value_vnd") is not None:
        out["value_vnd"] = convert.vnd(row["value_vnd"])
    if row.get("outcome"):
        out["outcome"] = row["outcome"]
    return out


def today_response(service: Any, user_id: str) -> dict[str, Any]:
    now = service.now()
    today = _today(service, user_id)
    rows = service.repo.db.query(proactive.SQL_TODAY_NUDGE, {"uid": user_id, "d": today}, max_rows=1)
    body: dict[str, Any] = {"app_date": today.isoformat(), "suppressed": []}
    if not rows:
        return body
    row = rows[0]
    suppressed = [
        {"kind": s["kind"], "reason": s["reason"]}
        for s in ((row.get("gate_reason") or {}).get("suppressed") or [])
        if isinstance(s, Mapping) and s.get("kind") and s.get("reason")
    ]
    prefs = proactive.read_preferences(getattr(service, "nudge_preferences", None), user_id)
    hour = now.astimezone(service.settings.tz).hour
    dismissed = row.get("status") == "dismissed" or row.get("outcome") in ("dismissed", "snoozed", "less_like_this")
    if prefs.is_quiet(hour):
        body["suppressed"] = [{"kind": row["kind"], "reason": "quiet_hours"}, *suppressed][:10]
        return body
    body["suppressed"] = suppressed[:10]
    if dismissed:
        return body  # người dùng đã bỏ qua, để sau hoặc ít nhắc: hôm nay không hiện lại
    body["nudge"] = nudge_wire(row, today.isoformat())
    body["card"] = block_to_wire(proactive.gate_card(row, as_of=now, app_date=today))
    return body


def feedback_response(
    service: Any, user_id: str, nudge_id: str, body: Mapping[str, Any], *, trace_id: str
) -> dict[str, Any]:
    if not _UUID_RE.match(nudge_id or ""):
        raise YofinaError(ErrorCode.NUDGE_NOT_FOUND, "Không tìm thấy bản tin này.")
    extra = sorted(set(body) - FEEDBACK_FIELDS)
    if extra:
        raise YofinaError(ErrorCode.PARAMS_INVALID, "Trường không hợp lệ: " + ", ".join(extra)[:80])
    outcome = body.get("outcome")
    if outcome not in NUDGE_OUTCOMES:
        raise YofinaError(ErrorCode.PARAMS_INVALID, "outcome phải là acted, dismissed, snoozed hoặc less_like_this.")
    reason = body.get("reason")
    if reason is not None and (not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 200):
        raise YofinaError(ErrorCode.PARAMS_INVALID, "reason phải là chuỗi 1 đến 200 ký tự.")
    if isinstance(reason, str):
        from yofina_core.pii import mask_pii

        reason = mask_pii(reason.strip()).text[:200]  # lý do không chứa PII (hợp đồng)
    with service.repo.db.transaction(user_id) as tx:
        found = tx.execute(SQL_NUDGE_FOR_FEEDBACK, {"uid": user_id, "id": nudge_id})
        rows = tx.execute(SQL_SET_OUTCOME, {"uid": user_id, "id": nudge_id, "outcome": outcome}) if found else []
        if not rows:
            raise YofinaError(ErrorCode.NUDGE_NOT_FOUND, "Không tìm thấy bản tin này.")
        kind, card_trace = found[0]["kind"], found[0]["trace_id"] or trace_id
        tx.execute(
            SQL_UPSERT_FEEDBACK,
            {
                "uid": user_id,
                "trace_id": card_trace,
                "block_id": f"proactive_card:{card_trace}:{kind}",
                "option_id": kind,
                "decision": "accepted" if outcome == "acted" else "rejected",
                "reason": reason or outcome,
            },
        )
    row = rows[0]
    return {"nudge_id": str(row["id"]), "outcome": row["outcome"], "recorded_at": format_instant(row["outcome_at"])}
