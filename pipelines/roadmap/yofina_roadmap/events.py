"""Đọc các trường định tuyến từ phong bì EventBridge."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from yofina_core.roadmap import JobTrigger

_SOURCES = {
    "roadmap.regeneration_requested": "yofina.ledger",
    "behavior.changed": "yofina.forecast",
    "profile.updated": "yofina.ledger",
}


class BadEvent(ValueError):
    """Sự kiện không thể xử lý, giữ lại để SQS chuyển DLQ."""


@dataclass(frozen=True)
class RoadmapEvent:
    user_id: str
    event_id: str
    trigger: JobTrigger | None = None
    job_id: str | None = None
    behavior_flag_id: str | None = None


def _uuid(value: Any) -> str:
    try:
        if isinstance(value, str) and str(UUID(value)) == value:
            return value
    except ValueError:
        pass
    raise BadEvent("Thiếu UUID hợp lệ")


def parse_event(body: Any) -> RoadmapEvent:
    try:
        envelope = json.loads(body) if isinstance(body, str) else body
    except ValueError as exc:
        raise BadEvent("Thân tin nhắn không phải JSON") from exc
    if not isinstance(envelope, dict):
        raise BadEvent("Phong bì không phải đối tượng")
    kind = envelope.get("detail-type")
    if (
        not isinstance(kind, str)
        or kind not in _SOURCES
        or envelope.get("source") != _SOURCES[kind]
    ):
        raise BadEvent("Nguồn hoặc loại sự kiện không hợp lệ")
    detail = envelope.get("detail")
    if not isinstance(detail, dict) or type(detail.get("v")) is not int or detail["v"] != 1:
        raise BadEvent("Thiếu detail hoặc phiên bản sự kiện không được hỗ trợ")

    user_id = detail.get("user_id")
    if not isinstance(user_id, str) or not user_id.strip() or len(user_id) > 128:
        raise BadEvent("Thiếu user_id hợp lệ")
    event_id = _uuid(detail.get("event_id"))
    if kind == "roadmap.regeneration_requested":
        if _uuid(detail.get("job_id")) != event_id:
            raise BadEvent("event_id phải bằng job_id")
        # Trigger và các tùy chọn của job lấy từ DB sau khi áp dụng RLS.
        return RoadmapEvent(user_id, event_id, job_id=event_id)
    if kind == "behavior.changed":
        if detail.get("method") != "pelt":
            raise BadEvent("behavior.changed cần xác nhận từ PELT")
        if _uuid(detail.get("flag_id")) != event_id:
            raise BadEvent("event_id phải bằng flag_id")
        return RoadmapEvent(user_id, event_id, "behavior_changed", behavior_flag_id=event_id)

    fields = detail.get("fields")
    if not isinstance(fields, list) or not fields or not all(isinstance(f, str) for f in fields):
        raise BadEvent("Thiếu danh sách fields")
    trigger: JobTrigger | None = None
    if "salary" in fields:
        trigger = "income_changed"
    elif "jars" in fields:
        trigger = "goal_changed"
    return RoadmapEvent(user_id, event_id, trigger)
