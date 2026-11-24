"""Bộ nhớ dài hạn (phase 5, luồng B, AgentCore Memory): namespace theo người dùng, loại bản ghi và kiểu REST `/memory*`.

Một nơi định nghĩa namespace để agent (đọc, ghi sự kiện), batch đêm (ghi bản ghi tự tạo) và Lambda ledger (xem, xóa) không lệch
nhau. Theo tài liệu AgentCore Memory (đã tra 24/11/2026):

- Namespace là chuỗi phân cấp có `/` đầu và cuối (tránh trùng tiền tố giữa người dùng: `/actors/alice/` chứ không `/actors/alice`);
  chiến lược (strategy) nhận mẫu có biến `{actorId}`, `{sessionId}`, `{memoryStrategyId}` và tự thay khi trích xuất.
- Mỗi bản ghi có đúng MỘT namespace (`MemoryRecordSummary.namespaces`, tối đa 1 phần tử); id dạng `mem-...` dài 40 đến 50 ký tự.
- KHÔNG có API xóa theo người dùng. Xóa hết của một người: `ListMemoryRecords` với `namespacePath` = gốc của người đó (liệt kê
  phân cấp, tối đa 100 mỗi trang, có `nextToken`) rồi `BatchDeleteMemoryRecords` (tối đa 100 mỗi lần) hoặc `DeleteMemoryRecord`
  (cần `namespace` cho điều kiện IAM); sự kiện ngắn hạn: `ListSessions` theo `actorId`, `ListEvents`, `DeleteEvent` từng sự kiện.
- `actorId` là `sub` của Cognito (UUID, khớp mẫu `[a-zA-Z0-9][a-zA-Z0-9-_/]*` của AgentCore); `sessionId` là session id của
  Runtime (id hội thoại).

Bản ghi KHÔNG chứa số dư, giao dịch thô hay PII (che bằng `yofina_core.pii` trước khi ghi sự kiện và bản ghi tự tạo); số luôn đọc
tươi từ tool.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from yofina_core.blocks import IsoDateTime

#: Loại bản ghi: sở thích (chiến lược user preference), sự thật về người dùng (semantic), tóm tắt phiên (summarization), hồ sơ
#: hành vi do batch đêm ghi, "bài học của agent" tóm tắt từ bảng `feedback` (hai loại sau là bản ghi tự tạo bằng
#: `BatchCreateMemoryRecords`).
MEMORY_KINDS = ("preference", "fact", "session_summary", "behavior", "lesson")
#: Nguồn: trích tự động từ hội thoại (chiến lược có sẵn) hoặc do hệ thống tự tạo.
MEMORY_SOURCES = ("conversation", "system")
MEMORY_SOURCE_OF_KIND = {
    "preference": "conversation",
    "fact": "conversation",
    "session_summary": "conversation",
    "behavior": "system",
    "lesson": "system",
}
#: Gốc namespace của một người dùng; mọi bản ghi của người đó nằm dưới đây (dùng làm `namespacePath` khi liệt kê và xóa).
MEMORY_ROOT_TEMPLATE = "/yofina/users/{actorId}/"
#: Mẫu namespace theo loại (đúng chuỗi đưa vào cấu hình chiến lược của CDK; `{actorId}` và `{sessionId}` do AgentCore thay).
MEMORY_NAMESPACE_TEMPLATES = {
    "preference": "/yofina/users/{actorId}/preferences/",
    "fact": "/yofina/users/{actorId}/facts/",
    "session_summary": "/yofina/users/{actorId}/sessions/{sessionId}/",
    "behavior": "/yofina/users/{actorId}/behavior/",
    "lesson": "/yofina/users/{actorId}/lessons/",
}
#: Mẫu id của AgentCore (actorId tối đa 255; ở đây chỉ nhận dạng không có `/` hay `:` để namespace không bị chèn cấp).
ACTOR_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")
RECORD_ID_RE = re.compile(r"^mem-[A-Za-z0-9_-]{36,46}$")
#: Độ dài tối đa của nội dung một bản ghi khi trả về REST (bản ghi dài hơn bị cắt ở ranh giới câu).
MEMORY_TEXT_MAX_CHARS = 1000
MEMORY_LIST_LIMIT_DEFAULT = 50
MEMORY_LIST_LIMIT_MAX = 100

MemoryKind = Literal["preference", "fact", "session_summary", "behavior", "lesson"]
MemorySource = Literal["conversation", "system"]
RecordId = Annotated[str, Field(pattern=r"^mem-[A-Za-z0-9_-]{36,46}$")]


def _actor(actor_id: str) -> str:
    if not ACTOR_ID_RE.fullmatch(actor_id or ""):
        raise ValueError("actor_id không hợp lệ cho namespace")
    return actor_id


def user_root(actor_id: str) -> str:
    """Gốc namespace của người dùng `actor_id` (sub của Cognito), có `/` đầu và cuối."""
    return MEMORY_ROOT_TEMPLATE.replace("{actorId}", _actor(actor_id))


def namespace_for(kind: str, actor_id: str, session_id: str | None = None) -> str:
    """Namespace cụ thể của một loại bản ghi. `session_summary` cần `session_id`; loại khác không nhận nó."""
    if kind not in MEMORY_NAMESPACE_TEMPLATES:
        raise ValueError(f"loại bộ nhớ lạ: {kind!r}")
    ns = MEMORY_NAMESPACE_TEMPLATES[kind].replace("{actorId}", _actor(actor_id))
    if "{sessionId}" in ns:
        if not session_id or not SESSION_ID_RE.fullmatch(session_id):
            raise ValueError("session_summary cần session_id hợp lệ")
        return ns.replace("{sessionId}", session_id)
    if session_id is not None:
        raise ValueError(f"{kind} không gắn với phiên")
    return ns


def kind_of_namespace(namespace: str, actor_id: str) -> str | None:
    """Loại bản ghi của `namespace` NẾU nó thuộc người dùng `actor_id`; namespace của người khác hoặc lạ thì None (Lambda bỏ
    bản ghi đó, không trả và không xóa: chặn rò bộ nhớ giữa người dùng ngay cả khi lọc phía dịch vụ sai)."""
    root = user_root(actor_id)
    if not namespace.startswith(root):
        return None
    rest = namespace[len(root) :]
    for kind, template in MEMORY_NAMESPACE_TEMPLATES.items():
        tail = template.split("{actorId}/", 1)[1]
        if "{sessionId}" in tail:
            prefix = tail.split("{sessionId}", 1)[0]
            sid = rest[len(prefix) :].removesuffix("/")
            if rest.startswith(prefix) and rest.endswith("/") and SESSION_ID_RE.fullmatch(sid):
                return kind
        elif rest == tail:
            return kind
    return None


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MemoryRecord(_Strict):
    """Một bản ghi bộ nhớ như REST trả (`GET /memory`): không mang namespace (có `sub`) hay strategy id."""

    record_id: RecordId
    kind: MemoryKind
    source: MemorySource
    text: Annotated[str, Field(min_length=1, max_length=MEMORY_TEXT_MAX_CHARS)]
    created_at: IsoDateTime


class MemoryListResponse(_Strict):
    records: Annotated[list[MemoryRecord], Field(max_length=MEMORY_LIST_LIMIT_MAX)]
    next_cursor: Annotated[str, Field(min_length=1, max_length=2048)] | None = None


class MemoryRecordDeleteResponse(_Strict):
    record_id: RecordId
    deleted: Literal[True]


class MemoryClearResponse(_Strict):
    deleted_records: Annotated[int, Field(ge=0)]
    deleted_events: Annotated[int, Field(ge=0)]
    failed: Annotated[int, Field(ge=0)]
