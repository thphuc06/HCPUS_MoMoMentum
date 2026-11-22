"""SQL của phase 3: bản ghi lượt (`audit_events`), phản hồi phương án (`feedback`), lời nhắc (`nudges`), kịch bản đã chạy.

Cùng quy ước `repo_wallet.py`: đọc qua hàm `app_*` (RLS theo `set_config` trong hàm), ghi trong `DataApi.transaction(user_id)`
(RLS cộng điều kiện `user_id = :uid` do code ép). Repo không biết hợp đồng khối UI.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from yofina_core.db import DataApi, Row
from yofina_core.errors import ErrorCode, YofinaError
from yofina_ledger.repo_wallet import ClaimSpec, WriteResult

SQL_GET_TRACE = "SELECT * FROM app_get_trace(CAST(:uid AS text), CAST(:trace_id AS text))"
SQL_GET_SCENARIO = "SELECT * FROM app_get_scenario(CAST(:uid AS text), CAST(:id AS uuid))"
SQL_LIST_NUDGES = "SELECT * FROM app_list_nudges(CAST(:uid AS text), CAST(:status AS text), CAST(:lim AS integer))"
# Trace "thuộc người gọi": có sự kiện audit, lượt hội thoại hoặc kịch bản mang trace đó (RLS lọc theo người dùng).
SQL_TRACE_KNOWN = (
    "SELECT 1 AS found FROM audit_events WHERE user_id = :uid AND trace_id = :trace_id "
    "UNION ALL SELECT 1 FROM conversation_turns WHERE user_id = :uid AND trace_id = :trace_id "
    "UNION ALL SELECT 1 FROM scenarios WHERE user_id = :uid AND trace_id = :trace_id LIMIT 1"
)
SQL_SCENARIO_KNOWN = (
    "SELECT 1 AS found FROM scenarios WHERE user_id = :uid AND id = CAST(:id AS uuid) LIMIT 1"
)
SQL_UPSERT_FEEDBACK = (
    "INSERT INTO feedback (user_id, trace_id, block_id, option_id, decision, reason, scenario_id) "
    "VALUES (:uid, :trace_id, :block_id, :option_id, :decision, :reason, CAST(:scenario_id AS uuid)) "
    "ON CONFLICT (user_id, trace_id, block_id, option_id) DO UPDATE SET decision = EXCLUDED.decision, "
    "reason = EXCLUDED.reason, scenario_id = COALESCE(EXCLUDED.scenario_id, feedback.scenario_id), "
    "updated_at = now() RETURNING id, decision, updated_at"
)
SQL_INSERT_NUDGE = (
    "INSERT INTO nudges (id, user_id, kind, fire_on, created_app_date, jar_code, note, status, source, scenario_id, trace_id) "
    "VALUES (CAST(:id AS uuid), :uid, :kind, CAST(:fire_on AS date), CAST(:created AS date), :jar_code, :note, "
    "'scheduled', 'user_option', CAST(:scenario_id AS uuid), :trace_id) RETURNING id"
)
SQL_CANCEL_NUDGE = (
    "UPDATE nudges SET status = 'cancelled', cancelled_at = now(), updated_at = now() "
    "WHERE user_id = :uid AND id = CAST(:id AS uuid) AND status = 'scheduled' "
    "RETURNING id, kind, fire_on, jar_code, note"
)
# Bản ghi lượt: đúng một dòng mỗi (user_id, trace_id) nhờ chỉ mục duy nhất một phần của migration 0010; ghi lại thì không làm gì.
SQL_RECORD_TURN = (
    "INSERT INTO audit_events (user_id, trace_id, event_type, tool, outcome, code, conversation_id, intent, data_used, "
    "rules_checked, confidence, blocks_emitted, token_usage, step_timings, duration_ms) "
    "VALUES (:uid, :trace_id, 'agent_turn', 'record_turn', :outcome, :code, :conversation_id, :intent, "
    "CAST(:data_used AS jsonb), CAST(:rules_checked AS jsonb), CAST(:confidence AS jsonb), CAST(:blocks_emitted AS jsonb), "
    "CAST(:token_usage AS jsonb), CAST(:step_timings AS jsonb), :duration_ms) "
    "ON CONFLICT (user_id, trace_id) WHERE event_type = 'agent_turn' AND trace_id IS NOT NULL DO NOTHING RETURNING id"
)
SQL_AUDIT_WRITE = (
    "INSERT INTO audit_events (user_id, trace_id, event_type, tool, outcome, code, params, details) "
    "VALUES (:uid, :trace_id, :event_type, :tool, 'ok', NULL, CAST(:params AS jsonb), CAST(:details AS jsonb))"
)


class Phase3Repo:
    """Mixin của `LedgerRepo`: dùng `self.db` (DataApi) và `self._claim` của `WalletRepo`."""

    db: DataApi

    # --- đọc -----------------------------------------------------------------------------------------------
    def get_trace(self, user_id: str, trace_id: str) -> Row | None:
        """Bản ghi lượt của CHÍNH người gọi, hoặc None (của người khác và không tồn tại giống nhau)."""
        rows = self.db.query(SQL_GET_TRACE, {"uid": user_id, "trace_id": trace_id}, max_rows=1)
        return rows[0] if rows else None

    def get_scenario(self, user_id: str, scenario_id: str) -> Row | None:
        rows = self.db.query(SQL_GET_SCENARIO, {"uid": user_id, "id": scenario_id}, max_rows=1)
        return rows[0] if rows else None

    def get_nudge(self, user_id: str, nudge_id: str) -> Row | None:
        """Lời nhắc đang `scheduled` của người gọi theo id, hoặc None."""
        rows = self.db.query(
            SQL_LIST_NUDGES, {"uid": user_id, "status": "scheduled", "lim": 200}, max_rows=200
        )
        return next((r for r in rows if str(r["id"]) == nudge_id), None)

    # --- ghi: bản ghi lượt ---------------------------------------------------------------------------------
    def record_turn(self, user_id: str, rec: Mapping[str, Any]) -> bool:
        """Ghi bản ghi lượt của CHÍNH người gọi (user_id từ JWT, RLS cộng điều kiện). True nếu ghi mới, False nếu đã có."""
        with self.db.transaction(user_id) as tx:
            rows = tx.execute(
                SQL_RECORD_TURN,
                {
                    "uid": user_id,
                    "trace_id": rec["trace_id"],
                    "outcome": rec["outcome"],
                    "code": rec.get("code"),
                    "conversation_id": rec.get("conversation_id"),
                    "intent": rec.get("intent"),
                    "data_used": rec["data_used"],
                    "rules_checked": rec["rules_checked"],
                    "confidence": rec["confidence"],
                    "blocks_emitted": rec["blocks_emitted"],
                    "token_usage": rec["token_usage"],
                    "step_timings": rec["step_timings"],
                    "duration_ms": rec["duration_ms"],
                },
            )
        return bool(rows)

    # --- ghi: phản hồi -------------------------------------------------------------------------------------
    def upsert_feedback(
        self,
        user_id: str,
        *,
        trace_id: str,
        block_id: str,
        option_id: str,
        decision: str,
        reason: str | None,
        scenario_id: str | None,
    ) -> Row:
        """Ghi hoặc cập nhật phản hồi (khóa duy nhất: trace, khối, phương án). `trace_id` hoặc `scenario_id` không thuộc người
        gọi thì TRACE_NOT_FOUND (RLS làm dòng của người khác vô hình, nên không lộ sự tồn tại)."""
        with self.db.transaction(user_id) as tx:
            if not tx.execute(SQL_TRACE_KNOWN, {"uid": user_id, "trace_id": trace_id}):
                raise YofinaError(ErrorCode.TRACE_NOT_FOUND, "Không tìm thấy lượt trả lời này.")
            if scenario_id is not None and not tx.execute(
                SQL_SCENARIO_KNOWN, {"uid": user_id, "id": scenario_id}
            ):
                raise YofinaError(ErrorCode.TRACE_NOT_FOUND, "Không tìm thấy kịch bản này.")
            rows = tx.execute(
                SQL_UPSERT_FEEDBACK,
                {
                    "uid": user_id,
                    "trace_id": trace_id,
                    "block_id": block_id,
                    "option_id": option_id,
                    "decision": decision,
                    "reason": reason,
                    "scenario_id": scenario_id,
                },
            )
        return rows[0]

    # --- ghi: lời nhắc (đi qua token như mọi thao tác ghi) --------------------------------------------------
    def write_nudge(
        self,
        user_id: str,
        *,
        norm: Mapping[str, Any],
        now: datetime,
        app_date: date,
        trace_id: str,
        audit: Mapping[str, Any],
        claim: ClaimSpec | None,
        tool: str,
    ) -> WriteResult:
        """`op create`: thêm một dòng `nudges`; `op cancel`: đổi `scheduled` thành `cancelled`. Cùng transaction với audit
        và biên nhận của đề nghị. Phase 3 chỉ LƯU và hủy lời nhắc (việc gửi theo ngày là phase 4 và 5)."""
        with self.db.transaction(user_id) as t:
            if norm["op"] == "cancel":
                rows = t.execute(SQL_CANCEL_NUDGE, {"uid": user_id, "id": norm["nudge_id"]})
                if not rows:
                    raise YofinaError(ErrorCode.NUDGE_NOT_FOUND, "Không còn lời nhắc nào để hủy.")
                facts: dict[str, Any] = {
                    "op": "cancel",
                    "kind": rows[0]["kind"],
                    "fire_on": rows[0]["fire_on"],
                    "jar_code": rows[0]["jar_code"],
                    "note": rows[0]["note"],
                }
                ref = norm["nudge_id"]
            else:
                ref = str(uuid.uuid4())
                t.execute(
                    SQL_INSERT_NUDGE,
                    {
                        "id": ref,
                        "uid": user_id,
                        "kind": norm["kind"],
                        "fire_on": norm["fire_on"],
                        "created": app_date,
                        "jar_code": norm.get("jar_code"),
                        "note": norm.get("note"),
                        "scenario_id": norm.get("scenario_id"),
                        "trace_id": trace_id,
                    },
                )
                facts = {
                    "op": "create",
                    "kind": norm["kind"],
                    "fire_on": date.fromisoformat(norm["fire_on"]),
                    "jar_code": norm.get("jar_code"),
                    "note": norm.get("note"),
                }
            t.execute(
                SQL_AUDIT_WRITE,
                {
                    "uid": user_id,
                    "trace_id": audit["trace_id"],
                    "event_type": audit["event_type"],
                    "tool": tool,
                    "params": audit["params"],
                    "details": audit["details"],
                },
            )
            result = WriteResult(
                tool=tool, reference_id=ref, occurred_at=now, app_date=app_date, facts=facts
            )
            self._claim(t, user_id, claim, result)  # type: ignore[attr-defined]
        return result
