"""Dựng event AG-UI (ag-ui-protocol 1.0.0) và đọc đầu vào `RunAgentInput`.

Thứ tự hợp lệ mà `@ag-ui/client` 1.0.5 đọc được: `RUN_STARTED` ... `RUN_FINISHED` (hoặc `RUN_ERROR`, và sau đó
không có event nào nữa); một tin nhắn chữ mở bằng `TEXT_MESSAGE_START`, đóng bằng `TEXT_MESSAGE_END` trước khi
mở tin khác hoặc một tool call; mỗi tool call là `TOOL_CALL_START` -> `TOOL_CALL_ARGS` -> `TOOL_CALL_END`, rồi
`TOOL_CALL_RESULT` (khối UI đi bằng `ACTIVITY_SNAPSHOT` **trước** `TOOL_CALL_RESULT`).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from ag_ui.core import (
    ActivitySnapshotEvent,
    BaseEvent,
    EventType,
    RunAgentInput,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)

BLOCK_ACTIVITY_TYPE = "yofina.block"


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:16]}"


def run_started(run_input: RunAgentInput) -> BaseEvent:
    return RunStartedEvent(
        type=EventType.RUN_STARTED, thread_id=run_input.thread_id, run_id=run_input.run_id
    )


def run_finished(
    run_input: RunAgentInput, *, result: Mapping[str, Any], usage: Sequence[Mapping[str, Any]]
) -> BaseEvent:
    return RunFinishedEvent(
        type=EventType.RUN_FINISHED,
        thread_id=run_input.thread_id,
        run_id=run_input.run_id,
        result=dict(result),
        usage=[dict(u) for u in usage] or None,  # type: ignore[arg-type]
    )


def run_error(message: str, code: str) -> BaseEvent:
    return RunErrorEvent(type=EventType.RUN_ERROR, message=message, code=code)


def text_start(message_id: str) -> BaseEvent:
    return TextMessageStartEvent(
        type=EventType.TEXT_MESSAGE_START, message_id=message_id, role="assistant"
    )


def text_content(message_id: str, delta: str) -> BaseEvent:
    return TextMessageContentEvent(
        type=EventType.TEXT_MESSAGE_CONTENT, message_id=message_id, delta=delta
    )


def text_end(message_id: str) -> BaseEvent:
    return TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id=message_id)


def tool_call_start(tool_call_id: str, name: str) -> BaseEvent:
    return ToolCallStartEvent(
        type=EventType.TOOL_CALL_START, tool_call_id=tool_call_id, tool_call_name=name
    )


def tool_call_args(tool_call_id: str, args: Mapping[str, Any]) -> BaseEvent:
    return ToolCallArgsEvent(
        type=EventType.TOOL_CALL_ARGS,
        tool_call_id=tool_call_id,
        delta=json.dumps(dict(args), ensure_ascii=False),
    )


def tool_call_end(tool_call_id: str) -> BaseEvent:
    return ToolCallEndEvent(type=EventType.TOOL_CALL_END, tool_call_id=tool_call_id)


def tool_call_result(tool_call_id: str, content: Mapping[str, Any]) -> BaseEvent:
    return ToolCallResultEvent(
        type=EventType.TOOL_CALL_RESULT,
        message_id=new_id("res-"),
        tool_call_id=tool_call_id,
        content=json.dumps(dict(content), ensure_ascii=False),
        role="tool",
    )


def block_snapshot(block_wire: Mapping[str, Any]) -> BaseEvent:
    """Khối UI: `messageId` = `block.id`, `replace: true` (cùng id thì khối sau thay khối trước)."""
    return ActivitySnapshotEvent(
        type=EventType.ACTIVITY_SNAPSHOT,
        message_id=block_wire["id"],
        activity_type=BLOCK_ACTIVITY_TYPE,
        content=dict(block_wire),
        replace=True,
    )


# --- đọc đầu vào ------------------------------------------------------------------------------
def message_text(message: Any) -> str:
    """Chữ của một tin nhắn AG-UI (chuỗi, hoặc ghép các phần `text` của nội dung nhiều phần)."""
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            getattr(p, "text", None) or (p.get("text") if isinstance(p, dict) else None)
            for p in content
        ]
        return "\n".join(t for t in parts if t).strip()
    return ""


def last_user_text(run_input: RunAgentInput) -> tuple[str, int] | None:
    """(chữ của tin nhắn người dùng cuối cùng, chỉ số của nó) hoặc None nếu không có."""
    for i in range(len(run_input.messages) - 1, -1, -1):
        m = run_input.messages[i]
        if m.role == "user" and (text := message_text(m)):
            return text, i
    return None


_ROLE_LABEL = {
    "user": "Người dùng",
    "assistant": "Yofina",
    "system": "Ứng dụng",
    "developer": "Ứng dụng",
}


def format_history(
    run_input: RunAgentInput, *, before_index: int, max_messages: int, max_chars: int
) -> str:
    """Bản ghi gọn các tin trước câu hỏi hiện tại (để router hiểu "chuyển luôn đi", "hũ đó"...)."""
    lines = []
    for m in run_input.messages[:before_index]:
        label = _ROLE_LABEL.get(m.role)
        text = message_text(m) if label else ""
        if text:
            lines.append(f"{label}: {text[:max_chars]}")
    return "\n".join(lines[-max_messages:]) if max_messages > 0 else ""
