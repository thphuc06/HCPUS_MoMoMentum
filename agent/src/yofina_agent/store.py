"""Lưu lượt hội thoại (câu hỏi, câu trả lời, khối UI) để frontend vẽ lại khi tải lại trang.

`ACTIVITY_SNAPSHOT` không nằm trong `MESSAGES_SNAPSHOT` (spike Strands §2.5), nên khối phải được lưu phía
server theo (`conversation_id` = session id của Runtime, `trace_id`, `seq`). Bảng `turn_blocks` nằm ở Aurora
sau RLS; **agent không giữ secret DB** và không có đường ghi DB trực tiếp. Giao diện ở đây là một cổng
(`TurnBlockStore`) để bước ghép nối vào đường do luồng B cung cấp.

Cài sẵn một đường chạy được mà không cần secret nào: gọi một tool qua chính Gateway bằng token của người
dùng (interceptor ghi `user_id`, Lambda ghi qua role `yofina_app` + RLS). Tên tool lấy từ cấu hình
`turn_blocks_tool` (mặc định rỗng = chưa nối, chỉ ghi log; Runtime đặt `ledger___save_turn`). Tool là
`save_turn` trong `contracts/tools/ledger.json`:

    save_turn(conversation_id, trace_id, user_text, assistant_text, blocks: array<{seq, block}>)
    # ghi conversation_turns + turn_blocks trong một transaction (user_id do interceptor ghi đè).

Lưu là *cố gắng hết sức*: lỗi không làm hỏng lượt hội thoại (chỉ ghi log).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any, Protocol

from yofina_agent.tools import GatewayTools

log = logging.getLogger("yofina.agent.store")


class TurnBlockStore(Protocol):
    async def save(
        self,
        *,
        tools: GatewayTools,
        conversation_id: str,
        trace_id: str,
        blocks: Sequence[dict[str, Any]],
        user_text: str = "",
        assistant_text: str = "",
    ) -> bool:
        """Lưu lượt: các khối (đã ở dạng dây JSON) và văn bản hai phía. Trả True nếu đã lưu."""
        ...


class UnconfiguredTurnBlockStore:
    """Chưa nối đường lưu: ghi log rõ ràng rồi bỏ qua (không lưu gì)."""

    async def save(
        self,
        *,
        tools: GatewayTools,
        conversation_id: str,
        trace_id: str,
        blocks: Sequence[dict[str, Any]],
        user_text: str = "",
        assistant_text: str = "",
    ) -> bool:
        log.info(
            json.dumps(
                {
                    "event": "turn_blocks_not_persisted",
                    "reason": "turn_blocks_tool chưa cấu hình",
                    "trace_id": trace_id,
                    "blocks": len(blocks),
                }
            )
        )
        return False


class GatewayToolTurnBlockStore:
    """Lưu bằng một tool của Gateway (xem docstring module)."""

    def __init__(self, tool_name: str) -> None:
        self._tool = tool_name

    async def save(
        self,
        *,
        tools: GatewayTools,
        conversation_id: str,
        trace_id: str,
        blocks: Sequence[dict[str, Any]],
        user_text: str = "",
        assistant_text: str = "",
    ) -> bool:
        if not (blocks or user_text or assistant_text):
            return True
        outcome = await tools.call(
            self._tool,
            {
                "conversation_id": conversation_id,
                "trace_id": trace_id,
                "user_text": user_text,
                "assistant_text": assistant_text,
                "blocks": [{"seq": i, "block": b} for i, b in enumerate(blocks)],
            },
        )
        if not outcome.ok:
            log.warning(
                json.dumps(
                    {
                        "event": "turn_blocks_save_failed",
                        "kind": outcome.kind.value,
                        "detail": outcome.detail,
                    },
                    ensure_ascii=False,
                )
            )
        return outcome.ok


def make_store(tool_name: str) -> TurnBlockStore:
    return GatewayToolTurnBlockStore(tool_name) if tool_name else UnconfiguredTurnBlockStore()


# --- bản ghi lượt (audit_events, event_type agent_turn) ---------------------------------------
class TurnRecordStore(Protocol):
    async def save(self, *, tools: GatewayTools, record: dict[str, Any]) -> bool:
        """Ghi MỘT bản ghi lượt (`trace.build_record`). Trả True nếu đã ghi."""
        ...


class UnconfiguredTurnRecordStore:
    """Chưa nối đường ghi: ghi log rõ ràng rồi bỏ qua. Cần một tool backend (xem agent/README.md, mục "Bản ghi lượt")."""

    async def save(self, *, tools: GatewayTools, record: dict[str, Any]) -> bool:
        log.info(
            json.dumps(
                {
                    "event": "turn_record_not_persisted",
                    "reason": "turn_record_tool chưa cấu hình",
                    "trace_id": record.get("trace_id"),
                    "intent": record.get("intent"),
                }
            )
        )
        return False


class GatewayToolTurnRecordStore:
    """Ghi bằng một tool của Gateway: tham số là đúng `record` (user_id do interceptor ghi đè từ JWT); phía tool `INSERT ... ON CONFLICT DO NOTHING`."""

    def __init__(self, tool_name: str) -> None:
        self._tool = tool_name

    async def save(self, *, tools: GatewayTools, record: dict[str, Any]) -> bool:
        outcome = await tools.call(self._tool, dict(record))
        if not outcome.ok:
            log.warning(
                json.dumps(
                    {"event": "turn_record_save_failed", "kind": outcome.kind.value, "detail": outcome.detail},
                    ensure_ascii=False,
                )
            )
        return outcome.ok


def make_record_store(tool_name: str) -> TurnRecordStore:
    return GatewayToolTurnRecordStore(tool_name) if tool_name else UnconfiguredTurnRecordStore()
