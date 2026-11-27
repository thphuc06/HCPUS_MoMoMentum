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
from typing import TYPE_CHECKING, Any

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
    MOVE_BETWEEN_JARS,
    ConfirmService,
    IssuedToken,
    ParamsError,
    TokenPayload,
    check_binding,
    decode_token,
    hash_normalized_params,
    issue_token,
    normalize_params,
)
from yofina_core.confirm import params_hash as compute_params_hash
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.money import format_vnd, to_vnd
from yofina_core.wallet import ACTION_TOOLS, BNPL_PRODUCT_CODE, PLANNER_WRITE_TOOLS, SAVE_JARS
from yofina_ledger import events, split_proposal
from yofina_ledger.events import EventPublisher
from yofina_ledger.forecast_client import ForecastClient
from yofina_ledger.phase3 import Phase3Reads
from yofina_ledger.refdata import ReferenceData
from yofina_ledger.repo import ConfirmClaim, LedgerRepo, MoveResult
from yofina_ledger.settings import LedgerSettings
from yofina_ledger.wallet_reads import WalletReads
from yofina_ledger.wallet_writes import WalletWrites

if TYPE_CHECKING:
    from yofina_ledger.proactive import NudgePreferenceSource

log = logging.getLogger("yofina.ledger")

TOOL_PREFIX = "ledger___"
#: tiền tố tên tool đầy đủ theo target Gateway (phase 3: `planner` chạy chung Lambda ledger)
PLANNER_PREFIX = "planner___"
# Id khối `confirm` do code dựng: `confirm:{trace_id}:{params_hash[:12]}` (contracts/README.md).
CONFIRM_BLOCK_ID_RE = re.compile(r"^confirm:[A-Za-z0-9_-]{1,64}:[0-9a-f]{12}$")
CONFIRM_BLOCK_ID_MAX = 128
ALREADY_APPLIED_MESSAGE = "Đề nghị này đã được thực hiện rồi. Chưa ghi thêm gì."
CANCELLED_MESSAGE = "Đề nghị này đã bị hủy. Hãy hỏi lại nếu bạn vẫn muốn thực hiện."
OFFER_EXPIRED_MESSAGE = "Đề nghị này đã hết hạn, hãy hỏi lại."
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
    conversation_id: Any,
    confirm_block_id: Any,
    norm: Mapping[str, Any],
    tool: str = MOVE_BETWEEN_JARS,
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
    digest = (
        compute_params_hash(tool, norm)
        if tool == MOVE_BETWEEN_JARS
        else hash_normalized_params(tool, norm)
    )
    if confirm_block_id.rsplit(":", 1)[1] != digest[:12]:
        raise YofinaError(
            ErrorCode.PARAMS_MISMATCH, "Khối xác nhận không khớp với thao tác này; hãy hỏi lại."
        )
    return conversation_id, confirm_block_id


def parse_confirm_ref_loose(conversation_id: Any, confirm_block_id: Any) -> tuple[str, str]:
    """Như `parse_confirm_ref` nhưng không có tham số để đối chiếu hash (dùng khi hủy đề nghị): chỉ kiểm hai trường."""
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
    return conversation_id, confirm_block_id


def utc_now() -> datetime:
    return datetime.now(UTC)


class LedgerService(WalletReads, WalletWrites, Phase3Reads):
    def __init__(
        self,
        repo: LedgerRepo,
        confirm: ConfirmService,
        settings: LedgerSettings,
        *,
        clock: Callable[[], datetime] = utc_now,
        ref: ReferenceData | None = None,
        events: EventPublisher | None = None,
        forecast: ForecastClient | None = None,
        nudge_preferences: NudgePreferenceSource | None = None,
    ) -> None:
        self.repo = repo
        self.confirm = confirm
        self.settings = settings
        self._clock = clock
        self.ref = ref or ReferenceData(repo, settings.reference_cache_seconds)  # type: ignore[arg-type]
        self.events = events
        self.forecast = forecast
        #: điểm móc sở thích bản tin (`GET /nudges/today` ẩn thẻ trong giờ im lặng); None: không có sở thích nào
        self.nudge_preferences = nudge_preferences

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
            jars=[
                j for j in view.jars if j.get("kind") != "system"
            ],  # GET /jars không gồm hũ hệ thống
            trace_id=trace_id,
            source_tool=source_tool,
            as_of=now,
            app_date=self._app_date(view.clock_offset_days, now),
        )

    def get_jar_balances_result(self, user_id: str, *, trace_id: str) -> dict[str, Any]:
        block = self.jar_summary(
            user_id, trace_id=trace_id, source_tool=f"{TOOL_PREFIX}get_jar_balances"
        )
        # exclude_none: trường tùy chọn của phase 4 (kind, goal_vnd, goal_date) vắng thì không phát `null`.
        return {
            "status": "OK",
            "as_of": block.source.as_of,
            "app_date": block.source.app_date,
            "data": block.data.model_dump(mode="json", exclude_none=True),
        }

    def jars_response(self, user_id: str, *, trace_id: str) -> dict[str, Any]:
        block = self.jar_summary(user_id, trace_id=trace_id, source_tool="rest:GET /jars")
        data = block.data.model_dump(mode="json", exclude_none=True)
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
        kind: Any = None,
        tx_type: Any = None,
        from_date: Any = None,
        to_date: Any = None,
        limit: Any = None,
        cursor: Any = None,
    ) -> dict[str, Any]:
        """Tool `query_transactions`: cùng nguồn với `GET /transactions`, bọc theo hợp đồng kết quả tool."""
        page = self.transactions_response(
            user_id,
            jar=jar,
            kind=kind,
            tx_type=tx_type,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            cursor=cursor,
        )
        data: dict[str, Any] = {
            "transactions": page["transactions"],
            "has_more": "next_cursor" in page,
        }
        if "next_cursor" in page:
            data["next_cursor"] = page["next_cursor"]
        return {"status": "OK", "as_of": page["as_of"], "app_date": page["app_date"], "data": data}

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

    # --- cấp token (REST): mọi tool ghi ---------------------------------------------------------------
    def _check_offer(
        self, user_id: str, ref: tuple[str, str], *, tool: str, trace_id: str, channel: str
    ) -> None:
        """Đề nghị đã có dòng (thực hiện hoặc hủy) thì từ chối; còn lại, khối `confirm` đã lưu mà quá `expires_at`
        thì từ chối vì hết hạn (server ép hạn của đề nghị, không chỉ giao diện). Chưa lưu được khối (lưu lỗi) thì không
        có hạn để ép: token (2 phút, dùng một lần) vẫn là lớp bảo vệ."""
        row = self.repo.resolution(user_id, ref[1])
        if row is not None:
            cancelled = row.get("status") == "cancelled"
            exc = YofinaError(
                ErrorCode.ALREADY_APPLIED,
                CANCELLED_MESSAGE if cancelled else ALREADY_APPLIED_MESSAGE,
            )
            self._audit_rejection(user_id, exc, {}, trace_id, channel, tool)
            raise exc
        block = self.repo.confirm_block(user_id, ref[0], ref[1])
        expires = ((block or {}).get("data") or {}).get("expires_at")
        if isinstance(expires, str):
            try:
                gone = datetime.fromisoformat(expires.replace("Z", "+00:00")) <= self.now()
            except ValueError:
                gone = False
            if gone:
                exc = YofinaError(ErrorCode.OFFER_EXPIRED, OFFER_EXPIRED_MESSAGE)
                self._audit_rejection(user_id, exc, {}, trace_id, channel, tool)
                raise exc

    def issue_confirmation(self, user_id: str, **kwargs: Any) -> IssuedToken:
        """Như `issue_confirmation_with_preview` nhưng chỉ trả token (đường dùng trong test và nơi không cần xem trước)."""
        return self.issue_confirmation_with_preview(user_id, **kwargs)[0]

    def _issue_save_jars_versioned(
        self, user_id: str, norm: dict[str, Any], digest: str
    ) -> IssuedToken:
        """Ký bản ledger đã chuẩn hóa. Bộ chuẩn hóa chung của ConfirmService bỏ base_version."""
        token, payload = issue_token(
            self.confirm._key(),
            sub=user_id,
            tool=SAVE_JARS,
            params_hash=digest,
            now_epoch=self.confirm._clock().timestamp(),
            ttl_seconds=self.confirm.ttl_seconds,
        )
        return IssuedToken(
            token=token,
            expires_at=datetime.fromtimestamp(payload.exp, UTC),
            ttl_seconds=self.confirm.ttl_seconds,
            tool=SAVE_JARS,
            params=norm,
            params_hash=digest,
        )

    def _verify_save_jars_versioned(
        self, user_id: str, norm: Mapping[str, Any], token: str
    ) -> TokenPayload:
        payload = decode_token(
            token,
            key=self.confirm._key(),
            now_epoch=self.confirm._clock().timestamp(),
            max_ttl_seconds=self.confirm.max_ttl_seconds,
        )
        check_binding(
            payload,
            sub=user_id,
            tool=SAVE_JARS,
            params_hash=hash_normalized_params(SAVE_JARS, norm),
        )
        return payload

    def issue_confirmation_with_preview(
        self,
        user_id: str,
        *,
        tool: Any,
        params: Mapping[str, Any],
        client_params_hash: str | None,
        trace_id: str,
        conversation_id: Any = None,
        confirm_block_id: Any = None,
        name_hint: str | None = None,
    ) -> tuple[IssuedToken, dict[str, Any]]:
        """Người dùng bấm xác nhận: kiểm nghiệp vụ lần nữa rồi ký token cho (user_id, tool, tham số), kèm bản XEM TRƯỚC do
        server tính (`summary`, `changes`, `warnings` cùng hình dạng khối `confirm_action`: số dư trước và sau từng hũ, tổng
        phải trả gồm phí Trả sau lấy từ `fee_schedules`, ngày đến hạn, hạn mức còn lại). Không ghi gì.

        Có `confirm_block_id` mà đề nghị đã thực hiện, đã hủy hoặc đã hết hạn thì từ chối ngay, trước cả kiểm số dư (số
        dư đã đổi vì chính lần thực hiện đó) và không cấp token."""
        if tool not in ACTION_TOOLS:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Tool không hỗ trợ xác nhận.")
        if tool == MOVE_BETWEEN_JARS:
            norm = self._normalize_move(params)
            ref = parse_confirm_ref(conversation_id, confirm_block_id, norm)
            if ref is not None:
                self._check_offer(user_id, ref, tool=tool, trace_id=trace_id, channel="rest")
            block = self.prepare_move(
                user_id, params, trace_id=trace_id, source_tool="rest:POST /confirmations"
            )
            if client_params_hash and client_params_hash != block.data.params_hash:
                raise YofinaError(
                    ErrorCode.PARAMS_MISMATCH,
                    "Tham số khác với khối xác nhận bạn đang xem; hãy hỏi lại.",
                )
            d = block.data
            preview = {
                "summary": d.summary,
                "changes": [
                    {
                        "label": f"Hũ {j.name}",
                        "before": format_vnd(j.before_vnd),
                        "after": format_vnd(j.after_vnd),
                    }
                    for j in (d.preview.from_, d.preview.to)
                ],
            }
            return self.confirm.issue(user_id, MOVE_BETWEEN_JARS, d.params.model_dump()), preview
        norm, st = self._normalize(user_id, tool, params)
        ref = parse_confirm_ref(conversation_id, confirm_block_id, norm, tool)
        if ref is not None:
            self._check_offer(user_id, ref, tool=tool, trace_id=trace_id, channel="rest")
        if (
            tool == SAVE_JARS
            and "base_version" not in norm
            and ref is None
            and not client_params_hash
        ):
            norm["base_version"] = split_proposal.jar_list_version(st.user_jars())
        prep = self._validate(user_id, tool, norm, st, name_hint=name_hint)
        digest = hash_normalized_params(tool, prep.norm)
        if client_params_hash and client_params_hash != digest:
            raise YofinaError(
                ErrorCode.PARAMS_MISMATCH,
                "Tham số khác với khối xác nhận bạn đang xem; hãy hỏi lại.",
            )
        preview: dict[str, Any] = {"summary": prep.summary[:120], "changes": prep.changes}
        if prep.warnings:
            preview["warnings"] = prep.warnings[:5]
        issued = (
            self._issue_save_jars_versioned(user_id, prep.norm, digest)
            if tool == SAVE_JARS and "base_version" in prep.norm
            else self.confirm.issue(user_id, tool, prep.norm)
        )
        return issued, preview

    def cancel_offer(
        self, user_id: str, *, conversation_id: Any, confirm_block_id: Any, trace_id: str
    ) -> dict[str, Any]:
        """Người dùng bấm "Không": server ghi trạng thái `cancelled` của đề nghị (không ghi sổ cái). Đề nghị đã thực
        hiện thì ALREADY_APPLIED; hủy lại đề nghị đã hủy thì trả lại đúng kết quả cũ (idempotent)."""
        ref = parse_confirm_ref_loose(conversation_id, confirm_block_id)
        known = (
            self.repo.confirm_block(user_id, ref[0], ref[1]) is not None
            or self.repo.resolution(user_id, ref[1]) is not None
        )
        if not known:
            raise YofinaError(
                ErrorCode.PARAMS_INVALID, "Không tìm thấy đề nghị này trong hội thoại."
            )
        status, at = self.repo.cancel_offer(user_id, ref[0], ref[1])
        if status != "cancelled":
            raise YofinaError(ErrorCode.ALREADY_APPLIED, ALREADY_APPLIED_MESSAGE)
        return {
            "block_id": ref[1],
            "status": "cancelled",
            "resolved_at": format_instant(at or self.now()),
        }

    # --- ghi (cần token): mọi tool, kể cả chuyển hũ ------------------------------------------------------
    def apply_action(
        self,
        user_id: str,
        tool: str,
        params: Mapping[str, Any],
        confirm_token: str | None,
        *,
        trace_id: str,
        channel: str,
        source_tool: str,
        conversation_id: Any = None,
        confirm_block_id: Any = None,
        name_hint: str | None = None,
    ) -> Any:
        """Thực hiện một tool ghi bất kỳ: trả khối `receipt` (chuyển hũ) hoặc `receipt_action`.

        Không token thì NEEDS_CONFIRMATION và không đọc gì. Thứ tự: chuẩn hóa, kiểm chữ ký/hạn/người/tool/hash, kiểm đề
        nghị (đã xử lý, hết hạn), kiểm nghiệp vụ, RỒI MỚI tiêu `jti` (nghiệp vụ sai không làm mất token), ghi một
        transaction, phát sự kiện."""
        if tool not in ACTION_TOOLS:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Tool không được hỗ trợ.")
        if tool == MOVE_BETWEEN_JARS:
            return self.apply_move(
                user_id,
                params,
                confirm_token,
                trace_id=trace_id,
                channel=channel,
                source_tool=source_tool,
                conversation_id=conversation_id,
                confirm_block_id=confirm_block_id,
            )
        if confirm_token in (None, ""):
            raise YofinaError(
                ErrorCode.NEEDS_CONFIRMATION, "Thao tác này cần bạn xác nhận trước khi thực hiện."
            )
        norm, st = self._normalize(user_id, tool, params)
        ref = parse_confirm_ref(conversation_id, confirm_block_id, norm, tool)
        try:
            payload = (
                self._verify_save_jars_versioned(user_id, norm, confirm_token)
                if tool == SAVE_JARS and "base_version" in norm
                else self.confirm.verify(confirm_token, sub=user_id, tool=tool, params=norm)
            )
        except YofinaError as exc:
            if exc.code in _TOKEN_REJECTIONS:
                self._audit_rejection(user_id, exc, norm, trace_id, channel, tool)
            raise
        if ref is not None:
            self._check_offer(user_id, ref, tool=tool, trace_id=trace_id, channel=channel)
        prep = self._validate(user_id, tool, norm, st, name_hint=name_hint)
        try:
            self.confirm.consume(payload)
        except YofinaError as exc:
            if exc.code in _TOKEN_REJECTIONS:
                self._audit_rejection(user_id, exc, norm, trace_id, channel, tool)
            raise
        try:
            return self.apply_generic(
                user_id,
                prep,
                payload.jti,
                trace_id=trace_id,
                channel=channel,
                source_tool=source_tool,
                claim_ref=ref,
            )
        except YofinaError as exc:
            if exc.code == ErrorCode.ALREADY_APPLIED:  # thua cuộc đua với yêu cầu song song
                self._audit_rejection(user_id, exc, norm, trace_id, channel, tool)
            raise

    # --- tool ghi qua Gateway (agent) ---------------------------------------------------------------------
    def needs_confirmation_for(
        self, user_id: str, tool: str, params: Mapping[str, Any], *, trace_id: str
    ) -> dict[str, Any]:
        """Tool ghi KHÔNG có token: chỉ xem trước (không ghi). `data` là đúng `data` của khối `confirm_action`."""
        if tool == MOVE_BETWEEN_JARS:
            return self.needs_confirmation_result(user_id, params, trace_id=trace_id)
        prefix = PLANNER_PREFIX if tool in PLANNER_WRITE_TOOLS else TOOL_PREFIX
        _, block = self.prepare_action(
            user_id, tool, params, trace_id=trace_id, source_tool=f"{prefix}{tool}"
        )
        wire = block_to_wire(block)
        return {
            "status": "NEEDS_CONFIRMATION",
            "as_of": block.source.as_of,
            "app_date": block.source.app_date,
            "data": wire["data"],
        }

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
        if ref is not None:
            self._check_offer(
                user_id, ref, tool=MOVE_BETWEEN_JARS, trace_id=trace_id, channel=channel
            )
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
        self._publish(user_id, trace_id, self._move_events(user_id, result, trace_id))
        return receipt_of(result)

    def _move_events(self, user_id: str, res: MoveResult, trace_id: str) -> list[Any]:
        """`transaction.recorded` của một lần chuyển hũ (event_id = transfer_id, hai hũ đổi số dư)."""
        return [
            events.transaction_recorded(
                user_id=user_id,
                trace_id=trace_id,
                transaction_id=res.transfer_id,
                occurred_at=res.occurred_at,
                app_date=res.app_date,
                kind="transfer",
                tx_type="jar_transfer",
                funding_source="jar",
                amount_vnd=res.amount_vnd,
                jar_codes=[res.from_jar["code"], res.to_jar["code"]],
                deltas={res.from_jar["code"]: -res.amount_vnd, res.to_jar["code"]: res.amount_vnd},
                balances={
                    res.from_jar["code"]: res.from_jar["balance_vnd"],
                    res.to_jar["code"]: res.to_jar["balance_vnd"],
                },
            )
        ]

    def _audit_rejection(
        self,
        user_id: str,
        exc: YofinaError,
        norm: Mapping[str, Any],
        trace_id: str,
        channel: str,
        tool: str = MOVE_BETWEEN_JARS,
    ) -> None:
        try:
            self.repo.audit(
                user_id,
                trace_id=trace_id,
                event_type=tool,
                tool=tool,
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
                        if b.get("type") in ("confirm", "confirm_action")
                        and isinstance(b.get("id"), str)
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
        """Xóa dữ liệu của CHÍNH người gọi, sinh lại persona tất định, đặt đồng hồ về ngày neo.

        Nạp đủ ví: hũ cộng hai hũ hệ thống (`app_ensure_system_jars`), người nhận, nghĩa vụ (kể cả khoản Trả sau với phí lấy
        từ bảng `fee_schedules`), hạn mức, sổ cái có `tx_type`, sự kiện lương; số dư hũ được dựng lại từ sổ cái. Sau đó TÍNH
        DỰ BÁO ĐỒNG BỘ (gọi `yofina-forecast-batch`) để mở app là có số (`forecast_ready`), rồi phát `profile.updated`."""
        import personas  # dữ liệu seed (data/personas), đóng gói cùng Lambda
        from personas.six_jars import apply_demo_layout
        from yofina_core.wallet import DEFAULT_OBLIGATION_JAR
        from yofina_ledger.jar_layout import DEMO_LAYOUT, DEMO_LAYOUT_ID

        s = self.settings
        now = self.now()
        try:
            data = apply_demo_layout(personas.generate(persona, anchor=s.demo_anchor_date), DEMO_LAYOUT)
        except personas.PersonaError as exc:
            raise YofinaError(ErrorCode.PARAMS_INVALID, f"Persona không hợp lệ: {exc}") from exc
        fee = self.ref.bnpl_monthly_fee(s.demo_anchor_date)
        mat = personas.materialize(
            data,
            anchor=s.demo_anchor_date,
            now=now,
            tz=s.tz,
            user_id=user_id,
            bnpl_fee={"amount_vnd": fee.amount_vnd, "id": fee.id} if fee else None,
            bnpl_label=self.ref.product_label(BNPL_PRODUCT_CODE, s.demo_anchor_date),
            obligation_pay_jar=DEFAULT_OBLIGATION_JAR,
        )
        purposes = {jar.code: jar.purpose for jar in DEMO_LAYOUT}
        counts = self.repo.reset_user(
            user_id,
            profile=mat.profile,
            jars=[{**jar, "purpose": purposes[jar["code"]]} for jar in mat.jars],
            payees=mat.payees,
            obligations=mat.obligations,
            credit_line=mat.credit_line,
            transactions=mat.transaction_rows,
            salary_events=mat.salary_events,
            trace_id=trace_id,
            details={
                "persona": persona,
                "jar_layout": DEMO_LAYOUT_ID,
                "clock_offset_days": mat.clock_offset_days,
            },
            app_date=mat.app_date,  # ngày neo cho lộ trình seed (phase 4), không suy từ giao dịch
        )
        # Phase 4 luồng B: nhãn k-NN seed của persona (0 nếu persona chưa có file nhãn). Lỗi nạp nhãn không làm hỏng việc đặt lại:
        # thiếu nhãn thì phân loại rơi sang bước model nhỏ, vẫn đúng hợp đồng.
        try:
            from yofina_ledger.classify_seed import apply_seed_labels

            apply_seed_labels(self.repo.db, user_id, persona)
        except Exception:
            log.exception("reset_seed_labels_failed persona=%s", persona)
        forecast_ready = (
            self.forecast.compute(user_id, "reset") if self.forecast is not None else False
        )
        self._publish(
            user_id,
            trace_id,
            [
                events.profile_updated(
                    user_id=user_id,
                    trace_id=trace_id,
                    occurred_at=now,
                    app_date=mat.app_date,
                    fields=["onboarding", "salary", "payday", "jars"],
                )
            ],
        )
        return {
            "reset_at": format_instant(now),
            "app_date": mat.app_date.isoformat(),
            "clock_offset_days": mat.clock_offset_days,
            "jars_count": counts.jars,
            "transactions_count": counts.transactions,
            "obligations_count": counts.obligations,
            "forecast_ready": forecast_ready,
        }


def _resolution(
    block: Mapping[str, Any], row: Mapping[str, Any] | None, now: datetime
) -> dict[str, Any]:
    """Trạng thái một khối `confirm` hoặc `confirm_action`: `done` (kèm `receipt`) nếu server đã ghi nhận thực hiện;
    `cancelled` nếu người dùng đã bấm "Không"; không thì `expired` khi quá `expires_at` của đề nghị, còn lại `pending`.
    Đã xử lý (done, cancelled) luôn thắng hết hạn."""
    block_id = block["id"]
    if row is not None and row.get("status") == "cancelled":
        return {
            "block_id": block_id,
            "status": "cancelled",
            "resolved_at": format_instant(row["resolved_at"]),
        }
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
