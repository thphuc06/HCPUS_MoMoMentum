"""Truy cập Aurora của ledger: toàn bộ SQL nằm ở đây, qua `yofina_core.db.DataApi`.

- **Đọc**: hàm plpgsql `app_*` (một lệnh gọi, RLS theo `set_config` bên trong hàm).
- **Ghi**: `DataApi.transaction(user_id)` (Begin -> set_config -> câu lệnh -> Commit, rollback trong
  `finally`). Mọi câu lệnh ghi vẫn có `user_id = :uid` do code ép; RLS là lớp phụ.
- Tiền là `Decimal` từ DB, đổi sang `int` VND bằng `to_vnd` ở lớp trên.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from yofina_core.clock import app_today
from yofina_core.db import DataApi, Row
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.money import to_vnd

JARS_PER_USER = 20  # khớp LIMIT của app_get_jar_view và maxItems của hợp đồng


@dataclass(frozen=True)
class JarView:
    """Số dư các hũ cùng độ lệch đồng hồ của người dùng. `clock_offset_days` None = chưa có người dùng."""

    clock_offset_days: int | None
    jars: tuple[Row, ...]

    def jar(self, code: str) -> Row | None:
        return next((j for j in self.jars if j["code"] == code), None)


@dataclass(frozen=True)
class MoveResult:
    transfer_id: str
    occurred_at: datetime
    app_date: date
    amount_vnd: int
    from_jar: dict[str, Any]  # code, name, balance_vnd (sau khi chuyển)
    to_jar: dict[str, Any]


@dataclass(frozen=True)
class ConfirmClaim:
    """Đề nghị (khối `confirm`) mà thao tác chuyển hũ này thực hiện (migration 0004).

    `receipt_for` dựng khối `receipt` (dạng JSON gửi ra ngoài) từ kết quả ghi; repo lưu nó cùng transaction
    với sổ cái để phát lại sau khi tải trang.
    """

    conversation_id: str
    confirm_block_id: str
    receipt_for: Callable[[MoveResult], Mapping[str, Any]]


@dataclass(frozen=True)
class ResetCounts:
    jars: int
    transactions: int


SQL_JAR_VIEW = "SELECT * FROM app_get_jar_view(:uid)"

SQL_QUERY_TRANSACTIONS = (
    "SELECT * FROM app_query_transactions("
    "CAST(:uid AS text), CAST(:jar AS text), CAST(:from_date AS date), CAST(:to_date AS date), "
    "CAST(:lim AS integer))"
)

SQL_GET_USER = "SELECT * FROM app_get_user(:uid)"

# Khóa hai hũ theo thứ tự mã (tránh deadlock khi hai lệnh chuyển ngược chiều), kèm độ lệch đồng hồ.
SQL_LOCK_JARS = (
    "SELECT u.clock_offset_days, j.code, j.name, j.balance_vnd "
    "FROM users u JOIN jars j ON j.user_id = u.id "
    "WHERE u.id = :uid AND j.code IN (:from_jar, :to_jar) "
    "ORDER BY j.code FOR UPDATE OF j"
)

# Một câu lệnh ghi duy nhất (CTE biến đổi dữ liệu): cập nhật hai hũ, hai dòng sổ cái cùng transfer_id,
# một dòng audit. Cả câu lệnh nằm trong transaction đã mở; kiểm số dư đã làm ở bước khóa phía trên,
# và ràng buộc CHECK (balance_vnd >= 0) là lưới cuối.
SQL_WRITE_MOVE = """
WITH moved AS (
  UPDATE jars
  SET balance_vnd = balance_vnd + CASE WHEN code = :from_jar
        THEN -CAST(:amount AS numeric) ELSE CAST(:amount AS numeric) END,
      updated_at = now()
  WHERE user_id = :uid AND code IN (:from_jar, :to_jar)
  RETURNING code, name, balance_vnd
), led AS (
  INSERT INTO transactions
    (user_id, occurred_at, app_date, kind, jar_code, amount_vnd, note, transfer_id, source)
  VALUES
    (:uid, CAST(:occurred_at AS timestamptz), CAST(:app_date AS date), 'transfer', :from_jar,
     -CAST(:amount AS numeric), :note_out, CAST(:transfer_id AS uuid), 'move'),
    (:uid, CAST(:occurred_at AS timestamptz), CAST(:app_date AS date), 'transfer', :to_jar,
     CAST(:amount AS numeric), :note_in, CAST(:transfer_id AS uuid), 'move')
  RETURNING id
), aud AS (
  INSERT INTO audit_events (user_id, trace_id, event_type, tool, outcome, params, details)
  VALUES (:uid, :trace_id, 'move_between_jars', 'move_between_jars', 'ok',
          CAST(:params AS jsonb), CAST(:details AS jsonb))
  RETURNING id
)
SELECT code, name, balance_vnd FROM moved
"""

# Đánh dấu đề nghị đã thực hiện (migration 0004). Trùng (user_id, confirm_block_id) thì không chèn và không
# trả dòng nào: người gọi coi là ALREADY_APPLIED và rollback cả transaction.
SQL_CLAIM_CONFIRM = (
    "INSERT INTO confirm_resolutions (user_id, confirm_block_id, conversation_id, transfer_id, receipt) "
    "VALUES (:uid, :cbid, :conv, CAST(:transfer_id AS uuid), CAST(:receipt AS jsonb)) "
    "ON CONFLICT (user_id, confirm_block_id) DO NOTHING RETURNING id"
)
SQL_GET_RESOLUTION = "SELECT * FROM app_get_confirm_resolution(:uid, :cbid)"
SQL_GET_RESOLUTIONS = (
    "SELECT * FROM app_get_confirm_resolutions(:uid, :conv, CAST(:lim AS integer))"
)

SQL_AUDIT = (
    "INSERT INTO audit_events (user_id, trace_id, event_type, tool, outcome, code, params, details) "
    "VALUES (:uid, :trace_id, :event_type, :tool, :outcome, :code, "
    "CAST(:params AS jsonb), CAST(:details AS jsonb))"
)

# --- lưu / đọc lại lượt hội thoại (migration 0003) ---------------------------------------------------
SQL_SAVE_TURN = (
    "INSERT INTO conversation_turns (user_id, conversation_id, trace_id, user_text, assistant_text) "
    "VALUES (:uid, :conv, :trace, :user_text, :assistant_text) "
    "ON CONFLICT (user_id, conversation_id, trace_id) DO UPDATE SET "
    "user_text = EXCLUDED.user_text, assistant_text = EXCLUDED.assistant_text"
)
SQL_DELETE_TURN_BLOCKS = (
    "DELETE FROM turn_blocks WHERE user_id = :uid AND conversation_id = :conv AND trace_id = :trace"
)
SQL_INSERT_TURN_BLOCK = (
    "INSERT INTO turn_blocks (user_id, conversation_id, trace_id, seq, block) "
    "VALUES (:uid, :conv, :trace, :seq, CAST(:block AS jsonb))"
)
SQL_GET_TURNS = "SELECT * FROM app_get_conversation_turns(:uid, :conv, CAST(:lim AS integer))"
SQL_GET_BLOCKS = "SELECT * FROM app_get_conversation_blocks(:uid, :conv, CAST(:lim AS integer))"
SQL_LIST_CONVERSATIONS = "SELECT * FROM app_list_conversations(:uid, CAST(:lim AS integer))"

TURNS_PER_CONVERSATION = 50
BLOCKS_PER_CONVERSATION = 300  # trần của app_get_conversation_blocks
RESOLUTIONS_PER_CONVERSATION = 300  # trần của app_get_confirm_resolutions

SQL_RESET_TRANSACTIONS = "DELETE FROM transactions WHERE user_id = :uid"
SQL_RESET_BLOCKS = "DELETE FROM turn_blocks WHERE user_id = :uid"
SQL_RESET_RESOLUTIONS = "DELETE FROM confirm_resolutions WHERE user_id = :uid"
SQL_RESET_TURNS = "DELETE FROM conversation_turns WHERE user_id = :uid"
SQL_RESET_JARS = "DELETE FROM jars WHERE user_id = :uid"
SQL_UPSERT_USER = """
INSERT INTO users (id, display_name, monthly_salary_vnd, payday_day, risk_tolerance, clock_offset_days)
VALUES (:uid, :display_name, :salary, :payday, :risk, :clock_offset_days)
ON CONFLICT (id) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  monthly_salary_vnd = EXCLUDED.monthly_salary_vnd,
  payday_day = EXCLUDED.payday_day,
  risk_tolerance = EXCLUDED.risk_tolerance,
  clock_offset_days = EXCLUDED.clock_offset_days,
  updated_at = now()
"""
SQL_INSERT_JAR = (
    "INSERT INTO jars (user_id, code, name, color_key, icon_key, balance_vnd, split_percent, sort_order) "
    "VALUES (:uid, :code, :name, :color_key, :icon_key, :balance, CAST(:split AS numeric), :sort_order)"
)
SQL_INSERT_TX = (
    "INSERT INTO transactions "
    "(user_id, occurred_at, app_date, kind, jar_code, amount_vnd, merchant, note, source) "
    "VALUES (:uid, CAST(:occurred_at AS timestamptz), CAST(:app_date AS date), :kind, :jar_code, "
    ":amount, :merchant, :note, :source)"
)


class LedgerRepo:
    def __init__(self, db: DataApi) -> None:
        self.db = db

    # --- đọc --------------------------------------------------------------------------
    def jar_view(self, user_id: str) -> JarView:
        rows = self.db.query(SQL_JAR_VIEW, {"uid": user_id}, max_rows=JARS_PER_USER)
        if not rows:
            return JarView(None, ())
        offset = int(rows[0]["clock_offset_days"])
        jars = tuple(r for r in rows if r["code"] is not None)
        return JarView(offset, jars)

    def clock_offset(self, user_id: str) -> int:
        rows = self.db.query(SQL_GET_USER, {"uid": user_id}, max_rows=1)
        return int(rows[0]["clock_offset_days"]) if rows else 0

    def query_transactions(
        self,
        user_id: str,
        *,
        jar: str | None,
        from_date: date | None,
        to_date: date | None,
        limit: int,
    ) -> list[Row]:
        """Tối đa `limit` dòng (hàm SQL tự chặn 51). Người gọi xin `limit + 1` để biết còn nữa không."""
        return self.db.query(
            SQL_QUERY_TRANSACTIONS,
            {"uid": user_id, "jar": jar, "from_date": from_date, "to_date": to_date, "lim": limit},
            max_rows=51,
        )

    # --- ghi: chuyển hũ -----------------------------------------------------------------
    def apply_move(
        self,
        user_id: str,
        *,
        from_jar: str,
        to_jar: str,
        amount_vnd: int,
        now: datetime,
        tz: Any,
        trace_id: str,
        channel: str,
        jti: str | None = None,
        claim: ConfirmClaim | None = None,
    ) -> MoveResult:
        """Chuyển tiền giữa hai hũ trong MỘT transaction. Ném `YofinaError` (JAR_NOT_FOUND,
        INSUFFICIENT_FUNDS, ALREADY_APPLIED); ngoại lệ bất kỳ thì rollback, không ghi gì.

        Có `claim`: cuối transaction đánh dấu đề nghị đã thực hiện (kèm biên nhận). Đề nghị đã thực hiện
        rồi thì ném ALREADY_APPLIED và cả sổ cái được rollback; hai yêu cầu song song cùng đề nghị thì
        yêu cầu sau chờ khóa unique rồi bị rollback."""
        with self.db.transaction(user_id) as tx:
            rows = tx.execute(
                SQL_LOCK_JARS, {"uid": user_id, "from_jar": from_jar, "to_jar": to_jar}
            )
            by_code = {r["code"]: r for r in rows}
            if from_jar not in by_code or to_jar not in by_code:
                raise YofinaError(ErrorCode.JAR_NOT_FOUND, "Không tìm thấy hũ bạn chọn.")
            src, dst = by_code[from_jar], by_code[to_jar]
            if to_vnd(src["balance_vnd"]) < amount_vnd:
                raise YofinaError(ErrorCode.INSUFFICIENT_FUNDS, f"Hũ {src['name']} không đủ số dư.")
            app_date = app_today(int(src["clock_offset_days"]), now, tz)
            transfer_id = str(uuid.uuid4())
            out = tx.execute(
                SQL_WRITE_MOVE,
                {
                    "uid": user_id,
                    "from_jar": from_jar,
                    "to_jar": to_jar,
                    "amount": amount_vnd,
                    "occurred_at": now,
                    "app_date": app_date,
                    "transfer_id": transfer_id,
                    "note_out": f"Chuyển sang hũ {dst['name']}",
                    "note_in": f"Nhận từ hũ {src['name']}",
                    "trace_id": trace_id,
                    "params": {"from_jar": from_jar, "to_jar": to_jar, "amount_vnd": amount_vnd},
                    "details": {"transfer_id": transfer_id, "channel": channel, "jti": jti},
                },
            )
            after = {r["code"]: r for r in out}
            if len(after) != 2:  # không thể xảy ra: hai hũ đã khóa ở trên
                raise YofinaError(ErrorCode.INTERNAL_ERROR, "Không ghi được giao dịch.")
            result = MoveResult(
                transfer_id=transfer_id,
                occurred_at=now,
                app_date=app_date,
                amount_vnd=amount_vnd,
                from_jar={
                    "code": from_jar,
                    "name": after[from_jar]["name"],
                    "balance_vnd": to_vnd(after[from_jar]["balance_vnd"]),
                },
                to_jar={
                    "code": to_jar,
                    "name": after[to_jar]["name"],
                    "balance_vnd": to_vnd(after[to_jar]["balance_vnd"]),
                },
            )
            if claim is not None:
                claimed = tx.execute(
                    SQL_CLAIM_CONFIRM,
                    {
                        "uid": user_id,
                        "cbid": claim.confirm_block_id,
                        "conv": claim.conversation_id,
                        "transfer_id": transfer_id,
                        "receipt": dict(claim.receipt_for(result)),
                    },
                )
                if not claimed:
                    raise YofinaError(
                        ErrorCode.ALREADY_APPLIED,
                        "Đề nghị này đã được thực hiện rồi. Chưa ghi thêm gì.",
                    )
        return result

    # --- lượt hội thoại ---------------------------------------------------------------
    def save_turn(
        self,
        user_id: str,
        *,
        conversation_id: str,
        trace_id: str,
        user_text: str,
        assistant_text: str,
        blocks: Sequence[tuple[int, dict[str, Any]]],
    ) -> int:
        """Ghi đè lượt (cùng conversation_id + trace_id) và các khối của nó trong MỘT transaction."""
        key = {"uid": user_id, "conv": conversation_id, "trace": trace_id}
        with self.db.transaction(user_id) as tx:
            tx.execute(
                SQL_SAVE_TURN, {**key, "user_text": user_text, "assistant_text": assistant_text}
            )
            tx.execute(SQL_DELETE_TURN_BLOCKS, key)
            if blocks:
                tx.batch(
                    SQL_INSERT_TURN_BLOCK,
                    [{**key, "seq": seq, "block": block} for seq, block in blocks],
                )
        return len(blocks)

    def conversation(self, user_id: str, conversation_id: str) -> tuple[list[Row], list[Row]]:
        """(lượt, khối) của một cuộc hội thoại, cũ tới mới; RLS nên hội thoại người khác ra rỗng."""
        turns = self.db.query(
            SQL_GET_TURNS,
            {"uid": user_id, "conv": conversation_id, "lim": TURNS_PER_CONVERSATION},
            max_rows=TURNS_PER_CONVERSATION,
        )
        if not turns:
            return [], []
        blocks = self.db.query(
            SQL_GET_BLOCKS,
            {"uid": user_id, "conv": conversation_id, "lim": BLOCKS_PER_CONVERSATION},
            max_rows=BLOCKS_PER_CONVERSATION,
        )
        return turns, blocks

    def resolution(self, user_id: str, confirm_block_id: str) -> Row | None:
        """Đề nghị đã thực hiện (kèm biên nhận) hoặc None. RLS nên đề nghị của người khác ra None."""
        rows = self.db.query(
            SQL_GET_RESOLUTION, {"uid": user_id, "cbid": confirm_block_id}, max_rows=1
        )
        return rows[0] if rows else None

    def resolutions(self, user_id: str, conversation_id: str) -> list[Row]:
        """Các đề nghị đã thực hiện của một cuộc hội thoại, cũ tới mới."""
        return self.db.query(
            SQL_GET_RESOLUTIONS,
            {"uid": user_id, "conv": conversation_id, "lim": RESOLUTIONS_PER_CONVERSATION},
            max_rows=RESOLUTIONS_PER_CONVERSATION,
        )

    def list_conversations(self, user_id: str, *, limit: int) -> list[Row]:
        return self.db.query(SQL_LIST_CONVERSATIONS, {"uid": user_id, "lim": limit}, max_rows=50)

    # --- audit ----------------------------------------------------------------------
    def audit(
        self,
        user_id: str,
        *,
        trace_id: str | None,
        event_type: str,
        tool: str | None,
        outcome: str,
        code: str | None = None,
        params: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self.db.transaction(user_id) as tx:
            tx.execute(
                SQL_AUDIT,
                {
                    "uid": user_id,
                    "trace_id": trace_id,
                    "event_type": event_type,
                    "tool": tool,
                    "outcome": outcome,
                    "code": code,
                    "params": params,
                    "details": details,
                },
            )

    # --- đặt lại dữ liệu demo -----------------------------------------------------------
    def reset_user(
        self,
        user_id: str,
        *,
        profile: dict[str, Any],
        jars: Sequence[dict[str, Any]],
        transactions: Sequence[dict[str, Any]],
        trace_id: str,
        details: dict[str, Any],
    ) -> ResetCounts:
        """Xóa dữ liệu của chính người gọi rồi nạp lại (một transaction). `audit_events` chỉ thêm."""
        with self.db.transaction(user_id) as tx:
            for sql in (
                SQL_RESET_TRANSACTIONS,
                SQL_RESET_BLOCKS,
                SQL_RESET_TURNS,
                SQL_RESET_RESOLUTIONS,
                SQL_RESET_JARS,
            ):
                tx.execute(sql, {"uid": user_id})
            tx.execute(SQL_UPSERT_USER, {"uid": user_id, **profile})
            tx.batch(SQL_INSERT_JAR, [{"uid": user_id, **j} for j in jars])
            tx.batch(SQL_INSERT_TX, [{"uid": user_id, **t} for t in transactions])
            tx.execute(
                SQL_AUDIT,
                {
                    "uid": user_id,
                    "trace_id": trace_id,
                    "event_type": "demo_reset",
                    "tool": None,
                    "outcome": "ok",
                    "code": None,
                    "params": None,
                    "details": details,
                },
            )
        return ResetCounts(jars=len(jars), transactions=len(transactions))
