"""Tám REST `/roadmap*` của Lambda ledger (phase 4, F5). `rest_api._dispatch` chuyển mọi route `GET /roadmap...` và `POST /roadmap...` vào
`dispatch` (một khối chuyển tiếp duy nhất); file này phân tuyến, kiểm đầu vào (trường lạ trong thân bị từ chối, đặc biệt không có
`user_id`: danh tính CHỈ lấy từ JWT) rồi gọi `roadmap_service.RoadmapOps`.

| Route | Việc |
|---|---|
| `GET /roadmap` | khối `roadmap` (`version` hoặc `which`) |
| `GET /roadmap/versions` | các phiên bản, bản đang dùng và bản chờ, job đang chạy |
| `GET /roadmap/diff` | khối `roadmap_diff` |
| `POST /roadmap/steps/{step_id}/decision` | chấp nhận, từ chối, đưa về chờ một bước |
| `POST /roadmap/steps/{step_id}/edit` | sửa số tiền hoặc ngày: phiên bản mới `active`, lý do `step_edited` |
| `POST /roadmap/versions/{version}/decision` | "Dùng bản mới" hoặc "Giữ bản cũ" |
| `POST /roadmap/regenerate` | ghi `roadmap_jobs`, phát `roadmap.regeneration_requested` sau commit, trả job (HTTP 200) |
| `GET /roadmap/jobs/{job_id}` | tiến độ một lần sinh lại |
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date
from typing import Any

from yofina_core.blocks import MAX_VND
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.wallet import ROADMAP_WHICH
from yofina_ledger.roadmap_service import NOTE_MAX, REASON_MAX, roadmap_ops

STEP_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
OPTION_ID_RE = STEP_ID_RE
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
ISO_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
VERSION_MIN, VERSION_MAX = 1, 10000
VERSIONS_DEFAULT_LIMIT, VERSIONS_MAX_LIMIT = 20, 50

_ROUTES = (
    ("GET", re.compile(r"^/roadmap$"), "roadmap"),
    ("GET", re.compile(r"^/roadmap/versions$"), "versions"),
    ("GET", re.compile(r"^/roadmap/diff$"), "diff"),
    ("GET", re.compile(r"^/roadmap/jobs/(?P<job_id>[^/]+)$"), "job"),
    ("POST", re.compile(r"^/roadmap/steps/(?P<step_id>[^/]+)/decision$"), "step_decision"),
    ("POST", re.compile(r"^/roadmap/steps/(?P<step_id>[^/]+)/edit$"), "step_edit"),
    ("POST", re.compile(r"^/roadmap/versions/(?P<version>[^/]+)/decision$"), "version_decision"),
    ("POST", re.compile(r"^/roadmap/regenerate$"), "regenerate"),
)


def _bad(message: str) -> YofinaError:
    return YofinaError(ErrorCode.PARAMS_INVALID, message)


def _version(value: Any, name: str = "version") -> int:
    """Số phiên bản 1..10000: số nguyên (thân JSON) hoặc chuỗi chữ số (query, đường dẫn)."""
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not VERSION_MIN <= value <= VERSION_MAX
    ):
        raise _bad(f"{name} phải là số nguyên từ {VERSION_MIN} đến {VERSION_MAX}.")
    return value


def _optional_version(value: Any, name: str) -> int | None:
    return None if value in (None, "") else _version(value, name)


def _strict_body(
    event: Mapping[str, Any], allowed: frozenset[str], *, required: bool = True
) -> dict[str, Any]:
    from yofina_ledger.rest_api import _body

    body = _body(event)
    extra = sorted(set(body) - allowed)
    if extra:  # không có trường lạ (đặc biệt không có user_id: danh tính chỉ đến từ JWT)
        raise _bad("Trường không hợp lệ: " + ", ".join(str(k) for k in extra)[:80])
    if required and not body:
        raise _bad("Thiếu thân yêu cầu.")
    return body


def _query(event: Mapping[str, Any]) -> Mapping[str, Any]:
    return event.get("queryStringParameters") or {}


def _text(value: Any, name: str, limit: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
        raise _bad(f"{name} phải dài từ 1 đến {limit} ký tự.")
    return value.strip()


def _slug(value: Any, name: str) -> str:
    if not isinstance(value, str) or not STEP_ID_RE.fullmatch(value):
        raise _bad(f"{name} không hợp lệ.")
    return value


def _iso_date(value: Any, name: str) -> str:
    if not isinstance(value, str) or not ISO_DATE_RE.fullmatch(value):
        raise _bad(f"{name} phải là ngày YYYY-MM-DD.")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise _bad(f"{name} không phải ngày hợp lệ.") from None
    return value


def match_route(route: str) -> tuple[str, Mapping[str, str]] | None:
    """(tên route nội bộ, tham số đường dẫn) của `"METHOD /path"`, hoặc None nếu không phải route lộ trình."""
    method, _, path = route.partition(" ")
    for m, pattern, name in _ROUTES:
        hit = pattern.match(path)
        if m == method and hit:
            return name, hit.groupdict()
    return None


def dispatch(
    route: str, event: Mapping[str, Any], sub: str, trace_id: str, service: Any
) -> tuple[int, dict[str, Any]]:
    """Phân tuyến một route `/roadmap*`. Trả (status, thân); lỗi là `YofinaError` (`rest_api.handle_http` đổi sang HTTP)."""
    matched = match_route(route)
    if matched is None:
        raise _bad("Đường dẫn không tồn tại.")
    name, path = matched
    ops = roadmap_ops(service)

    if name == "roadmap":
        q = _query(event)
        which = q.get("which")
        if which not in (None, "") and which not in ROADMAP_WHICH:
            raise _bad("which phải là active, proposed hoặc latest.")
        return 200, ops.roadmap_response(
            sub,
            version=_optional_version(q.get("version"), "version"),
            which=which or "active",
            trace_id=trace_id,
        )

    if name == "versions":
        raw = _query(event).get("limit")
        limit = VERSIONS_DEFAULT_LIMIT
        if raw not in (None, ""):
            if (
                not (isinstance(raw, str) and raw.isdigit())
                or not 1 <= int(raw) <= VERSIONS_MAX_LIMIT
            ):
                raise _bad(f"limit phải là số nguyên từ 1 đến {VERSIONS_MAX_LIMIT}.")
            limit = int(raw)
        return 200, ops.versions_response(sub, limit=limit)

    if name == "diff":
        q = _query(event)
        return 200, ops.diff_response(
            sub,
            from_version=_optional_version(q.get("from_version"), "from_version"),
            to_version=_optional_version(q.get("to_version"), "to_version"),
            trace_id=trace_id,
        )

    if name == "job":
        job_id = path["job_id"].lower()
        if not UUID_RE.fullmatch(job_id):  # sai dạng giống không tồn tại: không lộ gì
            raise YofinaError(ErrorCode.ROADMAP_NOT_FOUND, "Không tìm thấy lần sinh lại này.")
        return 200, ops.job_response(sub, job_id)

    if name == "step_decision":
        step_id = _slug(path["step_id"], "step_id")
        body = _strict_body(event, frozenset({"version", "decision", "reason"}))
        if "version" not in body or "decision" not in body:
            raise _bad("Thiếu version hoặc decision.")
        return 200, ops.decide_step_response(
            sub,
            step_id=step_id,
            version=_version(body["version"]),
            decision=str(body["decision"]) if isinstance(body["decision"], str) else "",
            reason=_text(body.get("reason"), "reason", REASON_MAX),
            trace_id=trace_id,
        )

    if name == "step_edit":
        step_id = _slug(path["step_id"], "step_id")
        body = _strict_body(event, frozenset({"version", "amount_vnd", "due_date"}))
        if "version" not in body:
            raise _bad("Thiếu version.")
        amount = body.get("amount_vnd")
        if amount is not None and (
            isinstance(amount, bool) or not isinstance(amount, int) or not 1 <= amount <= MAX_VND
        ):
            raise _bad("amount_vnd phải là số nguyên dương.")
        due = body.get("due_date")
        if amount is None and due is None:
            raise _bad("Cần amount_vnd hoặc due_date.")
        return 200, ops.edit_step_response(
            sub,
            step_id=step_id,
            version=_version(body["version"]),
            amount_vnd=amount,
            due_date=_iso_date(due, "due_date") if due is not None else None,
            trace_id=trace_id,
        )

    if name == "version_decision":
        version = _version(path["version"])
        body = _strict_body(event, frozenset({"decision"}))
        decision = body.get("decision")
        return 200, ops.decide_version_response(
            sub,
            version=version,
            decision=decision if isinstance(decision, str) else "",
            trace_id=trace_id,
        )

    assert name == "regenerate"
    body = _strict_body(
        event, frozenset({"note", "alternative_id", "based_on_version"}), required=False
    )
    alternative = body.get("alternative_id")
    if alternative is not None and (
        not isinstance(alternative, str) or not OPTION_ID_RE.fullmatch(alternative)
    ):
        raise _bad("alternative_id không hợp lệ.")
    return 200, ops.regenerate_response(
        sub,
        note=_text(body.get("note"), "note", NOTE_MAX),
        alternative_id=alternative,
        based_on_version=_optional_version(body.get("based_on_version"), "based_on_version"),
        trace_id=trace_id,
    )
