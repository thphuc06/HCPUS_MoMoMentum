"""Danh tính người dùng, lấy từ header `Authorization` mà AgentCore Runtime đã xác minh.

Runtime (JWT authorizer, `allowedClients`) kiểm chữ ký, hạn và client **trước** khi gọi agent, rồi
chuyển nguyên header `Authorization` nếu nó nằm trong `requestHeaderAllowlist`. Vì vậy ở đây chỉ
**giải mã** payload để lấy `sub`, không xác minh lại chữ ký. Agent **không bao giờ** nhận `user_id` từ
payload của request. Token được giữ nguyên để chuyển cho Gateway (interceptor ở đó mới ghi đè
`user_id` từ chính JWT này).
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field

_SUB_RE = re.compile(r"^[\w.:@\-]{1,128}$")


class Unauthenticated(Exception):
    """Thiếu hoặc sai header Authorization."""


@dataclass(frozen=True)
class Identity:
    sub: str
    token: str = field(repr=False)  # không bao giờ ghi log

    @property
    def authorization(self) -> str:
        return f"Bearer {self.token}"


def decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3 or not all(parts[:2]):
        raise Unauthenticated("Token không phải JWT")
    segment = parts[1]
    try:
        raw = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise Unauthenticated("Không giải mã được payload của JWT") from exc
    if not isinstance(payload, dict):
        raise Unauthenticated("Payload của JWT không phải object")
    return payload


def identity_from_authorization(header: str | None) -> Identity:
    """`Authorization: Bearer <jwt>` -> `Identity(sub, token)`."""
    if not header:
        raise Unauthenticated("Thiếu header Authorization")
    scheme, _, token = header.strip().partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise Unauthenticated("Authorization phải có dạng 'Bearer <token>'")
    sub = decode_jwt_payload(token).get("sub")
    if not isinstance(sub, str) or not _SUB_RE.fullmatch(sub):
        raise Unauthenticated("JWT không có claim 'sub' hợp lệ")
    return Identity(sub=sub, token=token)
