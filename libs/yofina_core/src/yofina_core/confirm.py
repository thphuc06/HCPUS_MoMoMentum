"""Xác nhận trước khi ghi (ADR-0002).

Phần đã cài ở bước 0 là phần thuộc **hợp đồng**: chuẩn hóa tham số và băm tham số. Khối `confirm`
(contracts/blocks/confirm.schema.json) chứa đúng `tool`, `params` đã chuẩn hóa và `params_hash`
này; token HMAC ký lên cùng hash, nên thứ người dùng thấy là thứ được ký.

Luồng B sẽ thêm vào module này (chưa có, KHÔNG cài giả ở đây):
- cấp token (HMAC-SHA256 trên `{sub, tool, h, exp, jti}`, secret ở Secrets Manager, hạn lấy từ
  cấu hình `confirm_token_ttl_seconds`);
- kiểm token: chữ ký, hạn, tool, sub, hash tham số, `jti` dùng một lần (`PutItem` có điều kiện
  vào bảng DynamoDB `yofina-confirm-jti`), trả đúng mã lỗi của `yofina_core.errors.ErrorCode`
  (`TOKEN_INVALID`, `TOKEN_EXPIRED`, `TOKEN_REUSED`, `PARAMS_MISMATCH`);
- 13 ca thử của spike (docs/research/spike-agentcore-gateway-identity.md §5) thành unit test.

Quy ước băm (để mọi bên tính ra cùng một giá trị):
    params_hash = sha256( canonical_json({"tool": tool, "params": normalized_params}) ).hexdigest()
    canonical_json = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                     mã hóa UTF-8.
`user_id` KHÔNG nằm trong hash: ràng buộc người dùng nằm ở `sub` trong payload của token.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from yofina_core.money import to_vnd

MOVE_BETWEEN_JARS = "move_between_jars"
JAR_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
MAX_VND = 99_999_999_999_999  # numeric(14,0)

_MOVE_KEYS = ("from_jar", "to_jar", "amount_vnd")


class ParamsError(ValueError):
    """Tham số tool không hợp lệ (ứng với `ErrorCode.PARAMS_INVALID`)."""


def _jar_code(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ParamsError(f"{name} phải là chuỗi mã hũ")
    code = value.strip().lower()
    if not JAR_CODE_RE.fullmatch(code):
        raise ParamsError(f"{name} không phải mã hũ hợp lệ: {value!r}")
    return code


def normalize_move_params(params: Mapping[str, Any]) -> dict[str, Any]:
    """Chuẩn hóa tham số của `move_between_jars`.

    Chỉ giữ `from_jar`, `to_jar`, `amount_vnd` (bỏ `user_id`, `confirm_token` và tham số lạ);
    mã hũ cắt khoảng trắng và hạ chữ thường; số tiền là số nguyên VND trong [1, MAX_VND].
    Idempotent: chuẩn hóa hai lần cho cùng kết quả.
    """
    missing = [k for k in _MOVE_KEYS if k not in params]
    if missing:
        raise ParamsError(f"Thiếu tham số: {', '.join(missing)}")
    from_jar = _jar_code("from_jar", params["from_jar"])
    to_jar = _jar_code("to_jar", params["to_jar"])
    if from_jar == to_jar:
        raise ParamsError("Hũ nguồn và hũ đích phải khác nhau")
    try:
        amount = to_vnd(params["amount_vnd"])
    except (TypeError, ValueError) as exc:
        raise ParamsError(f"amount_vnd không hợp lệ: {exc}") from exc
    if not 1 <= amount <= MAX_VND:
        raise ParamsError(f"amount_vnd phải trong khoảng 1..{MAX_VND}")
    return {"from_jar": from_jar, "to_jar": to_jar, "amount_vnd": amount}


def normalize_params(tool: str, params: Mapping[str, Any]) -> dict[str, Any]:
    if tool == MOVE_BETWEEN_JARS:
        return normalize_move_params(params)
    raise ParamsError(f"Tool không hỗ trợ xác nhận: {tool!r}")


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def params_hash(tool: str, params: Mapping[str, Any]) -> str:
    """sha256 (hex thường, 64 ký tự) của `{"tool", "params"}` đã chuẩn hóa."""
    normalized = normalize_params(tool, params)
    payload = canonical_json({"tool": tool, "params": normalized})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
