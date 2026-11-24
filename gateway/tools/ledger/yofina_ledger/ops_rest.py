"""Route `/ops/*` của HTTP API (bảng vận hành, FR15): `GET /ops/traces`, `GET /ops/traces/{trace_id}`, `GET /ops/summary`.

CHỈ tài khoản thuộc nhóm Cognito `ops` (`x-required-group: ops` của OpenAPI): đọc claim `cognito:groups` của access token mà JWT
authorizer của HTTP API đã xác thực (HTTP API chuyển claim mảng thành chuỗi dạng `[a b]`, `personas.parse_groups_claim` đọc cả hai
dạng). Không thuộc nhóm thì 403 `FORBIDDEN` TRƯỚC mọi truy cập dữ liệu. Danh tính người xem chỉ ghi vào log dưới dạng mã giả danh.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from typing import Any

from yofina_core.errors import ErrorCode, YofinaError
from yofina_ledger.ops import OpsService, build_ops

log = logging.getLogger("yofina.ledger.ops")

OPS_GROUP = "ops"
_CACHE: dict[int, OpsService] = {}


def ops_for(service: Any) -> OpsService:
    """Một `OpsService` cho mỗi `LedgerService` (mỗi môi trường thực thi Lambda), dựng lần đầu cần tới."""
    key = id(service)
    if key not in _CACHE:
        _CACHE[key] = build_ops(service)
    return _CACHE[key]


def _claims(event: Mapping[str, Any]) -> Mapping[str, Any]:
    return (
        event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {}) or {}
    )


def in_ops_group(event: Mapping[str, Any]) -> bool:
    from personas import parse_groups_claim

    return OPS_GROUP in parse_groups_claim(_claims(event).get("cognito:groups"))


def _viewer_ref(sub: str) -> str:
    return hashlib.sha256(sub.encode("utf-8")).hexdigest()[:12]


def dispatch(
    route: str, event: Mapping[str, Any], sub: str, trace_id: str, service: Any
) -> tuple[int, dict[str, Any]]:
    if not in_ops_group(event):
        raise YofinaError(
            ErrorCode.FORBIDDEN, "Chỉ tài khoản thuộc nhóm vận hành xem được trang này."
        )
    log.info(
        json.dumps(
            {
                "msg": "ops_access",
                "route": route,
                "viewer_ref": _viewer_ref(sub),
                "trace_id": trace_id,
            }
        )
    )
    ops = ops_for(service)
    q = event.get("queryStringParameters") or {}
    if route == "GET /ops/traces":
        return 200, ops.list_traces(q)
    if route.startswith("GET /ops/traces/"):
        value = (event.get("pathParameters") or {}).get("trace_id") or route[
            len("GET /ops/traces/") :
        ]
        return 200, ops.get_trace(value)
    if route == "GET /ops/summary":
        return 200, ops.summary(q)
    raise YofinaError(ErrorCode.PARAMS_INVALID, "Đường dẫn không tồn tại.")
