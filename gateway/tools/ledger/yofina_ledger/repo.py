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
from yofina_ledger.repo_wallet import WalletRepo

JARS_PER_USER = 40  # khớp LIMIT của app_get_jar_state (20 hũ người dùng + hũ hệ thống)


@dataclass(frozen=True)
class JarView:
    """Số dư MỌI hũ (kể cả hũ hệ thống) cùng độ lệch đồng hồ của người dùng. `clock_offset_days` None = chưa có
    người dùng. Mỗi hũ có `kind` và `system_role`; `GET /jars` và tool `get_jar_balances` lọc bỏ hũ hệ thống."""

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


SQL_JAR_VIEW = "SELECT * FROM app_get_jar_state(:uid)"

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
    (user_id, occurred_at, app_date, kind, jar_code, amount_vnd, note, transfer_id, source, tx_type)
  VALUES
    (:uid, CAST(:occurred_at AS timestamptz), CAST(:app_date AS date), 'transfer', :from_jar,
     -CAST(:amount AS numeric), :note_out, CAST(:transfer_id AS uuid), 'move', 'jar_transfer'),
    (:uid, CAST(:occurred_at AS timestamptz), CAST(:app_date AS date), 'transfer', :to_jar,
     CAST(:amount AS numeric), :note_in, CAST(:transfer_id AS uuid), 'move', 'jar_transfer')
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

# --- đặt lại dữ liệu demo: xóa đúng thứ tự khóa ngoại rồi nạp lại -----------------------------------------------
# forecast_runs kéo theo forecast_jar_summaries và forecasts (ON DELETE CASCADE); salary_events và category_rules trước
# transactions; transactions trước obligations và payees (khóa ngoại); jars cuối cùng.
# Phase 5 (migration 0050): ingest_rows rồi ingest_jobs TRƯỚC transactions (dòng nạp trỏ tới giao dịch đã ghi, không khóa
# ngoại cứng), nên đặt lại xóa sạch cả dòng external lẫn lịch sử nạp. consents cũng xóa: đặt lại đưa tài khoản demo về
# trạng thái chưa từng nạp, nên lần nạp kế tiếp hỏi đồng ý lại (bằng chứng đã đồng ý vẫn nằm ở audit_events, bảng chỉ thêm).
RESET_DELETES = (
    "DELETE FROM forecast_runs WHERE user_id = :uid",
    "DELETE FROM salary_events WHERE user_id = :uid",
    "DELETE FROM category_rules WHERE user_id = :uid",
    "DELETE FROM ingest_rows WHERE user_id = :uid",
    "DELETE FROM ingest_jobs WHERE user_id = :uid",
    "DELETE FROM consents WHERE user_id = :uid",
    "DELETE FROM transactions WHERE user_id = :uid",
    "DELETE FROM obligations WHERE user_id = :uid",
    "DELETE FROM payees WHERE user_id = :uid",
    "DELETE FROM credit_lines WHERE user_id = :uid",
    "DELETE FROM turn_blocks WHERE user_id = :uid",
    "DELETE FROM conversation_turns WHERE user_id = :uid",
    "DELETE FROM confirm_resolutions WHERE user_id = :uid",
    "DELETE FROM jars WHERE user_id = :uid",
)
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
    "INSERT INTO jars (user_id, code, name, color_key, icon_key, balance_vnd, split_percent, sort_order, kind, "
    "goal_vnd, goal_date) "
    "VALUES (:uid, :code, :name, :color_key, :icon_key, 0, CAST(:split AS numeric), :sort_order, :kind, "
    "CAST(:goal_vnd AS numeric), CAST(:goal_date AS date))"
)
SQL_ENSURE_SYSTEM = "SELECT app_ensure_system_jars(:uid) AS created"
SQL_INSERT_PAYEE = (
    "INSERT INTO payees (id, user_id, name, account_hint, is_favorite, last_used_at) "
    "VALUES (CAST(:id AS uuid), :uid, :name, :account_hint, :is_favorite, CAST(:last_used_at AS timestamptz))"
)
SQL_INSERT_OBLIGATION_SEED = (
    "INSERT INTO obligations (id, user_id, kind, name, amount_vnd, amount_min_vnd, amount_max_vnd, fee_vnd, "
    "principal_vnd, due_date, cycle, due_day, status, pay_jar_code, is_essential, source, fee_schedule_id) "
    "VALUES (CAST(:id AS uuid), :uid, :kind, :name, CAST(:amount AS numeric), CAST(:amount_min AS numeric), "
    "CAST(:amount_max AS numeric), CAST(:fee AS numeric), CAST(:principal AS numeric), CAST(:due_date AS date), "
    ":cycle, CAST(:due_day AS smallint), 'active', :pay_jar, :is_essential, :source, CAST(:fee_id AS uuid))"
)
SQL_INSERT_CREDIT_LINE = (
    "INSERT INTO credit_lines (user_id, product_code, limit_vnd, outstanding_vnd, due_day) "
    "VALUES (:uid, :product, CAST(:lim AS numeric), CAST(:outstanding AS numeric), CAST(:due_day AS smallint))"
)
SQL_INSERT_TX = (
    "INSERT INTO transactions "
    "(id, user_id, occurred_at, app_date, kind, jar_code, amount_vnd, merchant, note, transfer_id, source, "
    "tx_type, funding_source, payee_id, obligation_id, needs_review, classified_by) "
    "VALUES (CAST(:id AS uuid), :uid, CAST(:occurred_at AS timestamptz), CAST(:app_date AS date), :kind, :jar_code, "
    "CAST(:amount AS numeric), :merchant, :note, CAST(:transfer_id AS uuid), :source, :tx_type, :funding_source, "
    "CAST(:payee_id AS uuid), CAST(:obligation_id AS uuid), :needs_review, :classified_by)"
)
SQL_INSERT_SALARY_EVENT = (
    "INSERT INTO salary_events (id, user_id, period_date, transaction_id, received_on, expected_vnd, amount_vnd, "
    "deviation_percent, ask_update_salary, status, split, confirmed_at) "
    "VALUES (CAST(:id AS uuid), :uid, CAST(:period_date AS date), CAST(:transaction_id AS uuid), "
    "CAST(:received_on AS date), CAST(:expected AS numeric), CAST(:amount AS numeric), CAST(:deviation AS numeric), "
    "false, :status, CAST(:split AS jsonb), CAST(:confirmed_at AS timestamptz))"
)
# Số dư mỗi hũ = tổng các dòng trả bằng hũ (bất biến của sổ cái): dựng từ chính sổ cái vừa nạp.
SQL_RECOMPUTE_BALANCES = (
    "UPDATE jars SET balance_vnd = coalesce((SELECT sum(t.amount_vnd) FROM transactions t "
    "WHERE t.user_id = jars.user_id AND t.jar_code = jars.code AND t.funding_source = 'jar'), 0) "
    "WHERE user_id = :uid"
)


@dataclass(frozen=True)
class ResetCounts:
    jars: int
    transactions: int
    obligations: int = 0
    payees: int = 0


class LedgerRepo(WalletRepo):
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
        payees: Sequence[dict[str, Any]],
        obligations: Sequence[dict[str, Any]],
        credit_line: dict[str, Any] | None,
        transactions: Sequence[dict[str, Any]],
        salary_events: Sequence[dict[str, Any]],
        trace_id: str,
        details: dict[str, Any],
    ) -> ResetCounts:
        """Xóa dữ liệu của chính người gọi rồi nạp lại (một transaction). `audit_events` chỉ thêm.

        Thứ tự nạp theo khóa ngoại: người dùng, hũ (cộng hai hũ hệ thống), người nhận, nghĩa vụ, hạn mức, sổ cái, sự kiện
        lương; cuối cùng số dư hũ được dựng lại từ sổ cái."""
        with self.db.transaction(user_id) as tx:
            for sql in RESET_DELETES:
                tx.execute(sql, {"uid": user_id})
            tx.execute(SQL_UPSERT_USER, {"uid": user_id, **profile})
            tx.batch(SQL_INSERT_JAR, [{"uid": user_id, **j} for j in jars])
            tx.execute(SQL_ENSURE_SYSTEM, {"uid": user_id})
            tx.batch(SQL_INSERT_PAYEE, [{"uid": user_id, **p} for p in payees])
            tx.batch(SQL_INSERT_OBLIGATION_SEED, [{"uid": user_id, **o} for o in obligations])
            if credit_line is not None:
                tx.execute(SQL_INSERT_CREDIT_LINE, {"uid": user_id, **credit_line})
            tx.batch(SQL_INSERT_TX, [{"uid": user_id, **t} for t in transactions])
            tx.batch(SQL_INSERT_SALARY_EVENT, [{"uid": user_id, **e} for e in salary_events])
            tx.execute(SQL_RECOMPUTE_BALANCES, {"uid": user_id})
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
        return ResetCounts(
            jars=len(jars),
            transactions=len(transactions),
            obligations=len(obligations),
            payees=len(payees),
        )
