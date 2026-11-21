"""Request interceptor của AgentCore Gateway `yofina-gateway` (điểm chặn REQUEST, `passRequestHeaders: true`).

Việc duy nhất: mọi `tools/call` đều bị **ghi đè** `params.arguments.user_id` bằng `sub` của JWT trong header
`Authorization`. Gateway đã kiểm chữ ký, hạn và `client_id` của JWT trước khi gọi Lambda này (spike Gateway
§3a: JWT hỏng thì interceptor không được gọi), nên ở đây chỉ **giải mã** phần payload để lấy `sub`.

- Agent/LLM không cần biết `user_id`; giá trị client hoặc LLM tự gửi (kể cả `user_id` của người khác) bị
  thay bằng `sub`, kể cả khi vắng (interceptor chạy trước bước kiểm schema).
- Không lấy được `sub` ở một `tools/call` thì **từ chối** (đóng cửa), không cho đi tiếp với `user_id` do client gửi.
- Các phương thức khác (`initialize`, `tools/list`, ...) đi qua nguyên vẹn.
- Chỉ thư viện chuẩn, không phụ thuộc, không đọc cấu hình ngoài. Không bao giờ ghi token ra log.
"""

from __future__ import annotations

import base64
import copy
import json
import logging
import re
from typing import Any

log = logging.getLogger("yofina.gateway.interceptor")
log.setLevel(logging.INFO)

_SUB_RE = re.compile(r"^[\w.:@\-]{1,128}$")
DENY_TEXT = "Không xác định được người dùng từ token đăng nhập."


class NoIdentity(Exception):
    """Thiếu hoặc sai header Authorization (không lấy được `sub`)."""


def _headers(request: dict[str, Any]) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in (request.get("headers") or {}).items()}


def sub_from_authorization(value: str | None) -> str:
    if not value:
        raise NoIdentity("thiếu Authorization")
    scheme, _, token = value.strip().partition(" ")
    parts = token.strip().split(".")
    if scheme.lower() != "bearer" or len(parts) != 3 or not parts[1]:
        raise NoIdentity("Authorization không phải Bearer JWT")
    try:
        segment = parts[1]
        payload = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
    except (ValueError, UnicodeDecodeError) as exc:
        raise NoIdentity("không giải mã được JWT") from exc
    sub = payload.get("sub") if isinstance(payload, dict) else None
    if not isinstance(sub, str) or not _SUB_RE.fullmatch(sub):
        raise NoIdentity("JWT không có sub hợp lệ")
    return sub


def _override_one(message: dict[str, Any], sub: str) -> bool:
    """Ghi đè `user_id` ở một thông điệp `tools/call`; trả True nếu client đã gửi giá trị khác `sub`."""
    params = message.get("params")
    if not isinstance(params, dict):
        params = message["params"] = {}
    args = params.get("arguments")
    if not isinstance(args, dict):
        args = params["arguments"] = {}
    sent = args.get("user_id")
    args["user_id"] = sub
    return sent is not None and sent != sub


def _deny(message_id: Any) -> dict[str, Any]:
    return {
        "interceptorOutputVersion": "1.0",
        "mcp": {
            "transformedGatewayResponse": {
                "statusCode": 200,
                "body": {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": {"isError": True, "content": [{"type": "text", "text": DENY_TEXT}]},
                },
            }
        },
    }


def handle(event: dict[str, Any]) -> dict[str, Any]:
    request = event["mcp"]["gatewayRequest"]
    body = copy.deepcopy(request.get("body"))
    messages = body if isinstance(body, list) else [body]
    calls = [m for m in messages if isinstance(m, dict) and m.get("method") == "tools/call"]
    if not calls:
        return {
            "interceptorOutputVersion": "1.0",
            "mcp": {"transformedGatewayRequest": {"body": body}},
        }
    try:
        sub = sub_from_authorization(_headers(request).get("authorization"))
    except NoIdentity as exc:
        log.warning(json.dumps({"event": "interceptor_deny", "reason": str(exc)}))
        return _deny(calls[0].get("id"))
    overridden = [_override_one(m, sub) for m in calls]
    log.info(
        json.dumps(
            {
                "event": "interceptor_overwrite",
                "tools": [(m.get("params") or {}).get("name") for m in calls],
                "client_sent_other_user_id": any(overridden),
            }
        )
    )
    return {
        "interceptorOutputVersion": "1.0",
        "mcp": {"transformedGatewayRequest": {"body": body}},
    }


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return handle(event)
