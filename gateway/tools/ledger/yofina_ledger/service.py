"""Nghiệp vụ của ledger: không biết gì về Lambda, HTTP hay Gateway (hai đường vào gọi cùng lớp này).

Ba nguyên tắc (ADR-0002, ADR-0003, master-plan):

- `user_id` luôn là đối số tường minh, do đường vào tin cậy cung cấp (claim `sub` của JWT ở REST,
  `user_id` do interceptor ghi đè ở Gateway); không bao giờ lấy từ thân yêu cầu.
- Tool ghi không có `confirm_token` thì KHÔNG ghi: chỉ trả khối xem trước. Có token thì kiểm chữ ký,
  hạn, người, tool, hash tham số rồi mới tiêu `jti` (dùng một lần) và ghi.
- "Hôm nay" luôn là `app_today(clock_offset_days, now, tz)`; không gọi `date.today()`.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

from yofina_core.blocks import (
    ConfirmBlock,
    JarSummaryBlock,
    ReceiptBlock,
    block_to_wire,
    build_confirm,
    build_jar_summary,
    build_receipt,
    format_instant,
)
from yofina_core.clock import app_today
from yofina_core.confirm import (
    JAR_CODE_RE,
    MOVE_BETWEEN_JARS,
    ConfirmService,
    IssuedToken,
    ParamsError,
    normalize_params,
)
from yofina_core.confirm import params_hash as compute_params_hash
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.money import to_vnd
from yofina_ledger.repo import ConfirmClaim, LedgerRepo, MoveResult
from yofina_ledger.settings import LedgerSettings

log = logging.getLogger("yofina.ledger")

TOOL_PREFIX = "ledger___"
# Id khối `confirm` do code dựng: `confirm:{trace_id}:{params_hash[:12]}` (contracts/README.md).
CONFIRM_BLOCK_ID_RE = re.compile(r"^confirm:[A-Za-z0-9_-]{1,64}:[0-9a-f]{12}$")
CONFIRM_BLOCK_ID_MAX = 128
ALREADY_APPLIED_MESSAGE = "Đề nghị này đã được thực hiện rồi. Chưa ghi thêm gì."
_TOKEN_REJECTIONS = {
    ErrorCode.TOKEN_INVALID,
    ErrorCode.TOKEN_EXPIRED,
    ErrorCode.TOKEN_REUSED,
    ErrorCode.PARAMS_MISMATCH,
}


# --- lưu / đọc lại lượt hội thoại ---------------------------------------------------------------
USER_TEXT_MAX = 4000
ASSISTANT_TEXT_MAX = 8000
MAX_BLOCKS_PER_TURN = 20
MAX_BLOCK_BYTES = 64 * 1024
CONVERSATION_ID_MAX = 256
TRACE_ID_MAX = 64
PREVIEW_MAX = 120
LIST_DEFAULT_LIMIT = 20
LIST_MAX_LIMIT = 50
# Khóa không bao giờ được nằm trong khối lưu lại (chống vô tình lưu token vào DB).
_SECRET_KEYS = frozenset(
    {
        "confirm_token",
        "token",
        "access_token",
        "id_token",
        "refresh_token",
        "authorization",
        "password",
    }
)
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*")
_CONFIRM_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b")
REDACTED = "[đã ẩn token]"


def scrub_text(value: Any, limit: int) -> str:
    """Văn bản lượt: ép về chuỗi, che chuỗi giống JWT/token xác nhận, cắt theo giới hạn."""
    text = value if isinstance(value, str) else ""
    text = _JWT_RE.sub(REDACTED, text)
    text = _CONFIRM_TOKEN_RE.sub(REDACTED, text)
    return text[:limit]


def _has_secret_key(node: Any) -> bool:
    if isinstance(node, dict):
        return any(str(k).lower() in _SECRET_KEYS or _has_secret_key(v) for k, v in node.items())
    if isinstance(node, list):
        return any(_has_secret_key(v) for v in node)
    return False


def parse_confirm_ref(
    conversation_id: Any, confirm_block_id: Any, norm: Mapping[str, Any]
) -> tuple[str, str] | None:
    """(conversation_id, confirm_block_id) của đề nghị đang thực hiện, hoặc None nếu client không gửi cả hai.

    Chỉ một trong hai, sai kiểu/độ dài/định dạng -> PARAMS_INVALID. Phần cuối của id khối phải là 12 ký tự
    đầu của hash tham số đang thực hiện, nếu không -> PARAMS_MISMATCH (id của đề nghị khác không gắn được vào
    thao tác này).
    """
    if conversation_id is None and confirm_block_id is None:
        return None
    if conversation_id is None or confirm_block_id is None:
        raise YofinaError(
            ErrorCode.PARAMS_INVALID, "conversation_id và confirm_block_id phải đi cùng nhau."
        )
    if (
        not isinstance(conversation_id, str)
        or not 1 <= len(conversation_id) <= CONVERSATION_ID_MAX
        or conversation_id != conversation_id.strip()
    ):
        raise YofinaError(
            ErrorCode.PARAMS_INVALID,
            f"conversation_id phải dài từ 1 đến {CONVERSATION_ID_MAX} ký tự.",
        )
    if (
        not isinstance(confirm_block_id, str)
        or len(confirm_block_id) > CONFIRM_BLOCK_ID_MAX
        or not CONFIRM_BLOCK_ID_RE.fullmatch(confirm_block_id)
    ):
        raise YofinaError(ErrorCode.PARAMS_INVALID, "confirm_block_id không đúng định dạng.")
    if confirm_block_id.rsplit(":", 1)[1] != compute_params_hash(MOVE_BETWEEN_JARS, norm)[:12]:
        raise YofinaError(
            ErrorCode.PARAMS_MISMATCH, "Khối xác nhận không khớp với thao tác này; hãy hỏi lại."
        )
    return conversation_id, confirm_block_id


def utc_now() -> datetime:
    return datetime.now(UTC)


class LedgerService:
    def __init__(
        self,
        repo: LedgerRepo,
        confirm: ConfirmService,
        settings: LedgerSettings,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.repo = repo
        self.confirm = confirm
        self.settings = settings
        self._clock = clock

    # --- tiện ích -------------------------------------------------------------------
    def now(self) -> datetime:
        return self._clock()

    def _app_date(self, offset: int | None, now: datetime) -> date:
        return app_today(offset or 0, now, self.settings.tz)

    @staticmethod
    def _normalize_move(params: Mapping[str, Any]) -> dict[str, Any]:
        try:
            return normalize_params(MOVE_BETWEEN_JARS, params)
        except ParamsError as exc:
            raise YofinaError(ErrorCode.PARAMS_INVALID, str(exc)) from exc

    def _check_limit(self, norm: Mapping[str, Any]) -> None:
        if norm["amount_vnd"] > self.settings.move_max_amount_vnd:
            raise YofinaError(
                ErrorCode.AMOUNT_LIMIT_EXCEEDED,
                "Số tiền vượt hạn mức cho một lần chuyển giữa các hũ.",
            )

    # --- đọc: số dư ------------------------------------------------------------------
    def jar_summary(self, user_id: str, *, trace_id: str, source_tool: str) -> JarSummaryBlock:
        now = self.now()
        view = self.repo.jar_view(user_id)
        return build_jar_summary(
            jars=view.jars,
            trace_id=trace_id,
            source_tool=source_tool,
            as_of=now,
            app_date=self._app_date(view.clock_offset_days, now),
        )

    def get_jar_balances_result(self, user_id: str, *, trace_id: str) -> dict[str, Any]:
        block = self.jar_summary(
            user_id, trace_id=trace_id, source_tool=f"{TOOL_PREFIX}get_jar_balances"
        )
        return {
            "status": "OK",
            "as_of": block.source.as_of,
            "app_date": block.source.app_date,
            "data": block.data.model_dump(mode="json"),
        }

    def jars_response(self, user_id: str, *, trace_id: str) -> dict[str, Any]:
        block = self.jar_summary(user_id, trace_id=trace_id, source_tool="rest:GET /jars")
        data = block.data.model_dump(mode="json")
        return {
            "app_date": block.source.app_date,
            "as_of": block.source.as_of,
            "jars": data["jars"],
            "jars_total_vnd": data["jars_total_vnd"],
        }

    # --- đọc: giao dịch ----------------------------------------------------------------
    def query_transactions_result(
        self,
        user_id: str,
        *,
        jar: Any = None,
        from_date: Any = None,
        to_date: Any = None,
        limit: Any = None,
    ) -> dict[str, Any]:
        s = self.settings
        jar_code = None
        if jar not in (None, ""):
            jar_code = str(jar).strip().lower()
            if not JAR_CODE_RE.fullmatch(jar_code):
                raise YofinaError(ErrorCode.PARAMS_INVALID, "Mã hũ không hợp lệ.")
        dates = []
        for name, raw in (("from_date", from_date), ("to_date", to_date)):
            if raw in (None, ""):
                dates.append(None)
                continue
            try:
                dates.append(date.fromisoformat(str(raw)))
            except ValueError:
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID, f"{name} phải có dạng YYYY-MM-DD."
                ) from None
        if limit in (None, ""):
            n = s.transactions_default_limit
        else:
            try:
                n = int(limit)
            except (TypeError, ValueError):
                raise YofinaError(ErrorCode.PARAMS_INVALID, "limit phải là số nguyên.") from None
            n = max(1, min(n, s.transactions_max_limit))
        now = self.now()
        rows = self.repo.query_transactions(
            user_id, jar=jar_code, from_date=dates[0], to_date=dates[1], limit=n + 1
        )
        offset = self.repo.clock_offset(user_id)
        has_more = len(rows) > n
        return {
            "status": "OK",
            "as_of": format_instant(now),
            "app_date": self._app_date(offset, now).isoformat(),
            "data": {"transactions": [_tx_json(r) for r in rows[:n]], "has_more": has_more},
        }

    # --- chuyển hũ: đề nghị (không ghi) ---------------------------------------------------
    def prepare_move(
        self, user_id: str, params: Mapping[str, Any], *, trace_id: str, source_tool: str
    ) -> ConfirmBlock:
        """Kiểm nghiệp vụ và dựng khối `confirm` (tham số đã chuẩn hóa + hash + xem trước). Không ghi."""
        norm = self._normalize_move(params)
        self._check_limit(norm)
        now = self.now()
        view = self.repo.jar_view(user_id)
        src, dst = view.jar(norm["from_jar"]), view.jar(norm["to_jar"])
        if src is None or dst is None:
            raise YofinaError(ErrorCode.JAR_NOT_FOUND, "Không tìm thấy hũ bạn chọn.")
        if to_vnd(src["balance_vnd"]) < norm["amount_vnd"]:
            raise YofinaError(ErrorCode.INSUFFICIENT_FUNDS, f"Hũ {src['name']} không đủ số dư.")
        return build_confirm(
            tool=MOVE_BETWEEN_JARS,
            params=norm,
            from_jar=src,
            to_jar=dst,
            trace_id=trace_id,
            source_tool=source_tool,
            as_of=now,
            app_date=self._app_date(view.clock_offset_days, now),
            expires_at=now + timedelta(seconds=self.settings.offer_ttl_seconds),
        )

    def needs_confirmation_result(
        self, user_id: str, params: Mapping[str, Any], *, trace_id: str
    ) -> dict[str, Any]:
        block = self.prepare_move(
            user_id, params, trace_id=trace_id, source_tool=f"{TOOL_PREFIX}{MOVE_BETWEEN_JARS}"
        )
        return {
            "status": "NEEDS_CONFIRMATION",
            "as_of": block.source.as_of,
            "app_date": block.source.app_date,
            "data": block.data.model_dump(mode="json", by_alias=True),
        }

    # --- chuyển hũ: cấp token (REST) ------------------------------------------------------
    def issue_confirmation(
        self,
        user_id: str,
        *,
        tool: Any,
        params: Mapping[str, Any],
        client_params_hash: str | None,
        trace_id: str,
        conversation_id: Any = None,
        confirm_block_id: Any = None,
    ) -> IssuedToken:
        """Người dùng bấm xác nhận: kiểm nghiệp vụ lần nữa rồi ký token cho (user_id, tool, tham số).

        Có `confirm_block_id` mà đề nghị đã thực hiện rồi thì từ chối ngay (ALREADY_APPLIED), trước cả kiểm
        số dư (số dư đã đổi vì chính lần thực hiện đó) và không cấp token.
        """
        if tool != MOVE_BETWEEN_JARS:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Tool không hỗ trợ xác nhận.")
        norm = self._normalize_move(params)
        ref = parse_confirm_ref(conversation_id, confirm_block_id, norm)
        if ref is not None and self.repo.resolution(user_id, ref[1]) is not None:
            raise YofinaError(ErrorCode.ALREADY_APPLIED, ALREADY_APPLIED_MESSAGE)
        block = self.prepare_move(
            user_id, params, trace_id=trace_id, source_tool="rest:POST /confirmations"
        )
        if client_params_hash and client_params_hash != block.data.params_hash:
            raise YofinaError(
                ErrorCode.PARAMS_MISMATCH,
                "Tham số khác với khối xác nhận bạn đang xem; hãy hỏi lại.",
            )
        return self.confirm.issue(user_id, MOVE_BETWEEN_JARS, block.data.params.model_dump())

    # --- chuyển hũ: ghi (cần token) -----------------------------------------------------
    def apply_move(
        self,
        user_id: str,
        params: Mapping[str, Any],
        confirm_token: str | None,
        *,
        trace_id: str,
        channel: str,
        source_tool: str,
        conversation_id: Any = None,
        confirm_block_id: Any = None,
    ) -> ReceiptBlock:
        """Kiểm token rồi ghi hai dòng sổ cái + số dư + audit trong một transaction.

        Không token -> `NEEDS_CONFIRMATION`, không ghi. Token sai (chữ ký, hạn, người, tool, hash) hoặc
        đã dùng -> từ chối và ghi một dòng audit `rejected`. Token chỉ bị tiêu khi mọi kiểm tra khác đã qua.

        Có `conversation_id` + `confirm_block_id`: đề nghị chỉ được thực hiện MỘT lần. Đã thực hiện rồi thì
        `ALREADY_APPLIED` (kể cả với token mới hợp lệ), trước khi tiêu token. Chính transaction ghi sổ cái
        cũng lưu biên nhận gắn với đề nghị; khóa unique ở đó là đường chắc chắn khi hai yêu cầu chạy song
        song (yêu cầu sau rollback). Không gửi hai trường này (gọi REST trực tiếp, đường Gateway của agent)
        thì hành vi như cũ.
        """
        norm = self._normalize_move(params)
        self._check_limit(norm)
        ref = parse_confirm_ref(conversation_id, confirm_block_id, norm)
        if ref is not None and self.repo.resolution(user_id, ref[1]) is not None:
            exc = YofinaError(ErrorCode.ALREADY_APPLIED, ALREADY_APPLIED_MESSAGE)
            self._audit_rejection(user_id, exc, norm, trace_id, channel)
            raise exc
        try:
            payload = self.confirm.verify_and_consume(
                confirm_token, sub=user_id, tool=MOVE_BETWEEN_JARS, params=norm
            )
        except YofinaError as exc:
            if exc.code in _TOKEN_REJECTIONS:
                self._audit_rejection(user_id, exc, norm, trace_id, channel)
            raise
        now = self.now()

        def receipt_of(res: MoveResult) -> ReceiptBlock:
            return build_receipt(
                tool=MOVE_BETWEEN_JARS,
                transaction_id=res.transfer_id,
                occurred_at=res.occurred_at,
                app_date=res.app_date,
                amount_vnd=res.amount_vnd,
                from_jar=res.from_jar,
                to_jar=res.to_jar,
                trace_id=trace_id,
                source_tool=source_tool,
            )

        claim = (
            ConfirmClaim(ref[0], ref[1], lambda res: block_to_wire(receipt_of(res)))
            if ref is not None
            else None
        )
        try:
            result = self.repo.apply_move(
                user_id,
                from_jar=norm["from_jar"],
                to_jar=norm["to_jar"],
                amount_vnd=norm["amount_vnd"],
                now=now,
                tz=self.settings.tz,
                trace_id=trace_id,
                channel=channel,
                jti=payload.jti,
                claim=claim,
            )
        except YofinaError as exc:
            if exc.code == ErrorCode.ALREADY_APPLIED:  # thua cuộc đua với yêu cầu song song
                self._audit_rejection(user_id, exc, norm, trace_id, channel)
            raise
        return receipt_of(result)

    def _audit_rejection(
        self,
        user_id: str,
        exc: YofinaError,
        norm: Mapping[str, Any],
        trace_id: str,
        channel: str,
    ) -> None:
        try:
            self.repo.audit(
                user_id,
                trace_id=trace_id,
                event_type="move_between_jars",
                tool=MOVE_BETWEEN_JARS,
                outcome="rejected",
                code=str(exc.code),
                params=dict(norm),
                details={"channel": channel},
            )
        except Exception:  # audit lỗi không được che mã lỗi gốc của token
            log.warning("không ghi được audit từ chối", exc_info=True)

    # --- lượt hội thoại: lưu và đọc lại ---------------------------------------------------
    @staticmethod
    def _id(name: str, raw: Any, limit: int) -> str:
        if not isinstance(raw, str) or not 1 <= len(raw) <= limit or raw != raw.strip():
            raise YofinaError(ErrorCode.PARAMS_INVALID, f"{name} phải dài từ 1 đến {limit} ký tự.")
        return raw

    def save_turn_result(
        self,
        user_id: str,
        *,
        conversation_id: Any,
        trace_id: Any,
        user_text: Any = None,
        assistant_text: Any = None,
        blocks: Any = None,
    ) -> dict[str, Any]:
        """Ghi một lượt (câu hỏi, câu trả lời, khối UI). Ghi đè nếu cùng (conversation_id, trace_id)."""
        conv = self._id("conversation_id", conversation_id, CONVERSATION_ID_MAX)
        trace = self._id("trace_id", trace_id, TRACE_ID_MAX)
        items: list[tuple[int, dict[str, Any]]] = []
        if blocks not in (None, ""):
            if not isinstance(blocks, list) or len(blocks) > MAX_BLOCKS_PER_TURN:
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID,
                    f"blocks phải là mảng tối đa {MAX_BLOCKS_PER_TURN} phần tử.",
                )
            seen: set[int] = set()
            for entry in blocks:
                seq = entry.get("seq") if isinstance(entry, dict) else None
                block = entry.get("block") if isinstance(entry, dict) else None
                if (
                    isinstance(seq, bool)
                    or not isinstance(seq, int)
                    or seq < 0
                    or seq in seen
                    or not isinstance(block, dict)
                    or not isinstance(block.get("type"), str)
                    or not isinstance(block.get("id"), str)
                ):
                    raise YofinaError(
                        ErrorCode.PARAMS_INVALID,
                        "Mỗi phần tử của blocks cần seq (số nguyên không âm, không trùng) và block hợp lệ.",
                    )
                dumped = json.dumps(block, ensure_ascii=False)
                if _has_secret_key(block) or _JWT_RE.search(dumped):
                    raise YofinaError(
                        ErrorCode.PARAMS_INVALID, "Khối chứa dữ liệu nhạy cảm, không lưu."
                    )
                if len(dumped.encode()) > MAX_BLOCK_BYTES:
                    raise YofinaError(ErrorCode.PARAMS_INVALID, "Khối quá lớn để lưu.")
                seen.add(seq)
                items.append((seq, block))
        saved = self.repo.save_turn(
            user_id,
            conversation_id=conv,
            trace_id=trace,
            user_text=scrub_text(user_text, USER_TEXT_MAX),
            assistant_text=scrub_text(assistant_text, ASSISTANT_TEXT_MAX),
            blocks=sorted(items, key=lambda it: it[0]),
        )
        return {
            "status": "OK",
            "as_of": format_instant(self.now()),
            "data": {"blocks_saved": saved},
        }

    def conversation_response(self, user_id: str, conversation_id: Any) -> dict[str, Any]:
        """Các lượt đã lưu kèm khối theo thứ tự phát.

        Hội thoại không tồn tại hoặc không thuộc người gọi đều cho `turns` rỗng (không lộ sự tồn tại).
        """
        conv = self._id("conversation_id", conversation_id, CONVERSATION_ID_MAX)
        turns, blocks = self.repo.conversation(user_id, conv)
        resolved = (
            {r["confirm_block_id"]: r for r in self.repo.resolutions(user_id, conv)}
            if turns
            else {}
        )
        now = self.now()
        by_trace: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        for row in blocks:
            by_trace.setdefault(row["trace_id"], []).append((int(row["seq"]), row["block"]))
        out_turns = []
        for t in turns:
            turn_blocks = [
                b for _, b in sorted(by_trace.get(t["trace_id"], []), key=lambda x: x[0])
            ]
            out_turns.append(
                {
                    "trace_id": t["trace_id"],
                    "created_at": format_instant(t["created_at"]),
                    "user_text": t["user_text"],
                    "assistant_text": t["assistant_text"],
                    "blocks": turn_blocks,
                    "resolutions": [
                        _resolution(b, resolved.get(b["id"]), now)
                        for b in turn_blocks
                        if b.get("type") == "confirm" and isinstance(b.get("id"), str)
                    ],
                }
            )
        return {"conversation_id": conv, "turns": out_turns}

    def conversations_response(self, user_id: str, *, limit: Any = None) -> dict[str, Any]:
        if limit in (None, ""):
            n = LIST_DEFAULT_LIMIT
        else:
            try:
                n = int(limit)
            except (TypeError, ValueError):
                raise YofinaError(ErrorCode.PARAMS_INVALID, "limit phải là số nguyên.") from None
            if not 1 <= n <= LIST_MAX_LIMIT:
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID, f"limit phải trong khoảng 1 đến {LIST_MAX_LIMIT}."
                )
        rows = self.repo.list_conversations(user_id, limit=n)
        return {
            "conversations": [
                {
                    "conversation_id": r["conversation_id"],
                    "turns": int(r["turns"]),
                    "last_activity_at": format_instant(r["last_activity_at"]),
                    "preview": (r["preview"] or "")[:PREVIEW_MAX],
                }
                for r in rows
            ]
        }

    # --- đặt lại dữ liệu demo -----------------------------------------------------------
    def reset_demo(self, user_id: str, persona: str, *, trace_id: str) -> dict[str, Any]:
        """Xóa dữ liệu của CHÍNH người gọi, sinh lại persona tất định, đặt đồng hồ về ngày neo."""
        import personas  # dữ liệu seed (data/personas), đóng gói cùng Lambda

        s = self.settings
        now = self.now()
        try:
            data = personas.generate(persona, anchor=s.demo_anchor_date)
        except personas.PersonaError as exc:
            raise YofinaError(ErrorCode.PARAMS_INVALID, f"Persona không hợp lệ: {exc}") from exc
        mat = personas.materialize(data, anchor=s.demo_anchor_date, now=now, tz=s.tz)
        counts = self.repo.reset_user(
            user_id,
            profile={
                "display_name": data.display_name,
                "salary": data.monthly_salary_vnd,
                "payday": data.payday_day,
                "risk": data.risk_tolerance,
                "clock_offset_days": mat.clock_offset_days,
            },
            jars=[
                {
                    "code": j.code,
                    "name": j.name,
                    "color_key": j.color_key,
                    "icon_key": j.icon_key,
                    "balance": j.balance_vnd,
                    "split": j.split_percent,
                    "sort_order": j.sort_order,
                }
                for j in data.jars
            ],
            transactions=[
                {
                    "occurred_at": t.occurred_at,
                    "app_date": t.app_date,
                    "kind": t.kind,
                    "jar_code": t.jar_code,
                    "amount": t.amount_vnd,
                    "merchant": t.merchant,
                    "note": t.note,
                    "source": t.source,
                }
                for t in mat.transactions
            ],
            trace_id=trace_id,
            details={"persona": persona, "clock_offset_days": mat.clock_offset_days},
        )
        return {
            "reset_at": format_instant(now),
            "app_date": mat.app_date.isoformat(),
            "clock_offset_days": mat.clock_offset_days,
            "jars_count": counts.jars,
            "transactions_count": counts.transactions,
        }


def _resolution(
    block: Mapping[str, Any], row: Mapping[str, Any] | None, now: datetime
) -> dict[str, Any]:
    """Trạng thái một khối `confirm`: `done` (kèm `receipt`) nếu server đã ghi nhận thực hiện; không thì
    `expired` khi quá `expires_at` của đề nghị, còn lại `pending`. Đã thực hiện luôn thắng hết hạn."""
    block_id = block["id"]
    if row is not None:
        return {
            "block_id": block_id,
            "status": "done",
            "resolved_at": format_instant(row["resolved_at"]),
            "receipt": row["receipt"],
        }
    expires = (block.get("data") or {}).get("expires_at")
    try:
        expired = isinstance(expires, str) and datetime.fromisoformat(expires) <= now
    except ValueError:
        expired = False
    return {"block_id": block_id, "status": "expired" if expired else "pending"}


def _tx_json(row: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": row["id"],
        "occurred_at": format_instant(row["occurred_at"]),
        "app_date": row["app_date"].isoformat(),
        "kind": row["kind"],
        "amount_vnd": to_vnd(row["amount_vnd"]),
    }
    if row.get("jar_code"):
        out["jar"] = row["jar_code"]
    for key in ("merchant", "note"):
        if row.get(key):
            out[key] = row[key]
    if row.get("transfer_id"):
        out["transfer_id"] = row["transfer_id"]
    return out
