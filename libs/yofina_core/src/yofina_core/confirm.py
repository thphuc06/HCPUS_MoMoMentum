"""Xác nhận trước khi ghi (ADR-0002).

Phần đã cài ở bước 0 là phần thuộc **hợp đồng**: chuẩn hóa tham số và băm tham số. Khối `confirm`
(contracts/blocks/confirm.schema.json) chứa đúng `tool`, `params` đã chuẩn hóa và `params_hash`
này; token HMAC ký lên cùng hash, nên thứ người dùng thấy là thứ được ký.

Phần token (luồng B, bên dưới): cấp và kiểm token HMAC-SHA256 trên `{sub, tool, h, exp, jti}`,
secret ở Secrets Manager, `jti` dùng một lần bằng `PutItem` có điều kiện vào DynamoDB. Mọi lỗi là
`YofinaError` với mã `TOKEN_INVALID`, `TOKEN_EXPIRED`, `TOKEN_REUSED`, `PARAMS_MISMATCH` hoặc
`NEEDS_CONFIRMATION` (khớp OpenAPI). Spike: docs/research/spike-agentcore-gateway-identity.md §5.

Quy ước băm (để mọi bên tính ra cùng một giá trị):
    params_hash = sha256( canonical_json({"tool": tool, "params": normalized_params}) ).hexdigest()
    canonical_json = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                     mã hóa UTF-8.
`user_id` KHÔNG nằm trong hash: ràng buộc người dùng nằm ở `sub` trong payload của token.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from yofina_core.config import Config
from yofina_core.errors import ErrorCode, YofinaError
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


# =====================================================================================
# Token xác nhận dùng một lần (ADR-0002)
# =====================================================================================

_B64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    if not _B64URL_RE.fullmatch(text):
        raise ValueError("không phải base64url")
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@dataclass(frozen=True)
class TokenPayload:
    """Nội dung ký của token: ai (`sub`), việc gì (`tool`), tham số nào (`h`), hạn (`exp`, epoch
    giây), mã dùng một lần (`jti`)."""

    sub: str
    tool: str
    h: str
    exp: int
    jti: str

    def to_json(self) -> str:
        return json.dumps(
            {"sub": self.sub, "tool": self.tool, "h": self.h, "exp": self.exp, "jti": self.jti},
            separators=(",", ":"),
            sort_keys=True,
        )


def _sign(key: bytes, payload_b64: str) -> bytes:
    return hmac.new(key, payload_b64.encode("ascii"), hashlib.sha256).digest()


def issue_token(
    key: bytes,
    *,
    sub: str,
    tool: str,
    params_hash: str,
    now_epoch: float,
    ttl_seconds: int,
    jti: str | None = None,
) -> tuple[str, TokenPayload]:
    """Ký một token: `base64url(payload).base64url(HMAC-SHA256(key, base64url(payload)))`.

    Hàm thuần (không I/O). Người gọi phải đã xác thực `sub` (từ JWT) và đã chuẩn hóa tham số.
    """
    if not sub:
        raise ValueError("token cần sub")
    if ttl_seconds < 1:
        raise ValueError("ttl_seconds phải >= 1")
    payload = TokenPayload(
        sub=sub,
        tool=tool,
        h=params_hash,
        exp=int(now_epoch) + int(ttl_seconds),
        jti=jti or uuid.uuid4().hex,
    )
    body = _b64e(payload.to_json().encode("utf-8"))
    return f"{body}.{_b64e(_sign(key, body))}", payload


def decode_token(
    token: str | None, *, key: bytes, now_epoch: float, max_ttl_seconds: int
) -> TokenPayload:
    """Kiểm định dạng, chữ ký và hạn; trả payload. Chưa kiểm ràng buộc `sub`/`tool`/hash/`jti`.

    Thứ tự: thiếu token -> NEEDS_CONFIRMATION; sai định dạng hoặc chữ ký -> TOKEN_INVALID;
    quá hạn -> TOKEN_EXPIRED; hạn xa hơn `max_ttl_seconds` -> TOKEN_INVALID (không do ta cấp).
    Chữ ký luôn được kiểm trước hạn: token giả không bao giờ nhận được TOKEN_EXPIRED.
    """
    if token is None or token == "":
        raise YofinaError(
            ErrorCode.NEEDS_CONFIRMATION, "Thao tác này cần bạn xác nhận trước khi thực hiện."
        )
    invalid = YofinaError(ErrorCode.TOKEN_INVALID, "Token xác nhận không hợp lệ.")
    if not isinstance(token, str) or token.count(".") != 1:
        raise invalid
    body, sig_text = token.split(".")
    try:
        sig = _b64d(sig_text)
    except (ValueError, binascii.Error):
        raise invalid from None
    if not hmac.compare_digest(_sign(key, body), sig):
        raise invalid
    try:
        raw = json.loads(_b64d(body))
        payload = TokenPayload(
            sub=str(raw["sub"]),
            tool=str(raw["tool"]),
            h=str(raw["h"]),
            exp=int(raw["exp"]),
            jti=str(raw["jti"]),
        )
    except (ValueError, KeyError, TypeError, binascii.Error):
        raise invalid from None
    if payload.exp < now_epoch:
        raise YofinaError(ErrorCode.TOKEN_EXPIRED, "Token xác nhận đã hết hạn, hãy xác nhận lại.")
    if payload.exp - now_epoch > max_ttl_seconds:
        raise invalid
    return payload


def check_binding(payload: TokenPayload, *, sub: str, tool: str, params_hash: str) -> None:
    """Token phải đúng người, đúng tool, đúng tham số."""
    if not hmac.compare_digest(payload.sub.encode(), sub.encode()):
        raise YofinaError(ErrorCode.TOKEN_INVALID, "Token xác nhận không hợp lệ.")
    if payload.tool != tool:
        raise YofinaError(ErrorCode.TOKEN_INVALID, "Token xác nhận không hợp lệ.")
    if not hmac.compare_digest(payload.h.encode(), params_hash.encode()):
        raise YofinaError(
            ErrorCode.PARAMS_MISMATCH,
            "Tham số khác với tham số bạn đã xác nhận; hãy xác nhận lại.",
        )


class JtiStore(Protocol):
    def consume(self, jti: str, exp: int) -> None:
        """Đánh dấu `jti` đã dùng; ném `YofinaError(TOKEN_REUSED)` nếu đã dùng rồi."""


class DynamoJtiStore:
    """`jti` dùng một lần bằng `PutItem` có điều kiện vào bảng DynamoDB (có TTL).

    Atomic: hai request đua cùng `jti` thì đúng một request thắng. Lỗi DynamoDB khác -> fail closed
    (không ghi, `INTERNAL_ERROR`)."""

    def __init__(
        self, table_name: str, client: Any = None, *, ttl_grace_seconds: int = 3600
    ) -> None:
        self.table_name = table_name
        self._client = client
        self.ttl_grace_seconds = ttl_grace_seconds

    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("dynamodb", region_name=Config().region())
        return self._client

    def consume(self, jti: str, exp: int) -> None:
        try:
            self.client.put_item(
                TableName=self.table_name,
                Item={"jti": {"S": jti}, "ttl": {"N": str(int(exp) + self.ttl_grace_seconds)}},
                ConditionExpression="attribute_not_exists(jti)",
            )
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
            if code == "ConditionalCheckFailedException":
                raise YofinaError(
                    ErrorCode.TOKEN_REUSED, "Token xác nhận đã được dùng; hãy xác nhận lại."
                ) from exc
            raise YofinaError(
                ErrorCode.INTERNAL_ERROR,
                "Không kiểm tra được trạng thái token, thao tác bị từ chối.",
            ) from exc


class SecretKeyProvider:
    """Khóa HMAC từ Secrets Manager (chuỗi thuần), cache trong tiến trình `cache_seconds` giây
    (đủ ngắn để xoay khóa có hiệu lực, đủ dài để không gọi mỗi request)."""

    def __init__(
        self,
        secret_id: str,
        client: Any = None,
        *,
        cache_seconds: float = 300.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.secret_id = secret_id
        self._client = client
        self.cache_seconds = cache_seconds
        self._monotonic = monotonic
        self._key: bytes | None = None
        self._fetched_at = 0.0

    def get(self) -> bytes:
        now = self._monotonic()
        if self._key is None or now - self._fetched_at > self.cache_seconds:
            if self._client is None:
                import boto3

                self._client = boto3.client("secretsmanager", region_name=Config().region())
            value = self._client.get_secret_value(SecretId=self.secret_id)["SecretString"]
            if not value:
                raise YofinaError(ErrorCode.INTERNAL_ERROR, "Khóa xác nhận chưa được cấu hình.")
            self._key = value.encode("utf-8")
            self._fetched_at = now
        return self._key


@dataclass(frozen=True)
class IssuedToken:
    token: str
    expires_at: datetime
    ttl_seconds: int
    tool: str
    params: dict[str, Any]
    params_hash: str


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ConfirmService:
    """Cấp và kiểm token xác nhận. Không có I/O riêng ngoài `key_provider` và `jti_store`."""

    def __init__(
        self,
        key_provider: Callable[[], bytes],
        jti_store: JtiStore,
        *,
        ttl_seconds: int,
        max_ttl_seconds: int | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._key = key_provider
        self._jti = jti_store
        self.ttl_seconds = ttl_seconds
        self.max_ttl_seconds = max_ttl_seconds if max_ttl_seconds is not None else ttl_seconds
        if ttl_seconds > self.max_ttl_seconds:
            raise ValueError("ttl_seconds vượt trần max_ttl_seconds")
        self._clock = clock

    @classmethod
    def from_config(cls, cfg: Config | None = None) -> ConfirmService:
        cfg = cfg or Config()
        ttl = cfg.get_int("confirm_token_ttl_seconds")
        max_ttl = cfg.get_int("confirm_token_max_ttl_seconds", default=ttl)
        keys = SecretKeyProvider(cfg.get("confirm_hmac_secret_arn"))
        store = DynamoJtiStore(cfg.get("confirm_jti_table"))
        return cls(keys.get, store, ttl_seconds=ttl, max_ttl_seconds=max_ttl)

    def issue(self, sub: str, tool: str, params: Mapping[str, Any]) -> IssuedToken:
        """Cấp token cho `sub` (đã xác thực từ JWT) và tham số đã chuẩn hóa."""
        normalized = _normalize_or_error(tool, params)
        digest = params_hash(tool, normalized)
        now = self._clock()
        token, payload = issue_token(
            self._key(),
            sub=sub,
            tool=tool,
            params_hash=digest,
            now_epoch=now.timestamp(),
            ttl_seconds=self.ttl_seconds,
        )
        return IssuedToken(
            token=token,
            expires_at=datetime.fromtimestamp(payload.exp, UTC),
            ttl_seconds=self.ttl_seconds,
            tool=tool,
            params=normalized,
            params_hash=digest,
        )

    def verify(
        self, token: str | None, *, sub: str, tool: str, params: Mapping[str, Any]
    ) -> TokenPayload:
        """Kiểm token mà CHƯA tiêu `jti` (chữ ký, hạn, người, tool, hash tham số)."""
        normalized = _normalize_or_error(tool, params)
        payload = decode_token(
            token,
            key=self._key(),
            now_epoch=self._clock().timestamp(),
            max_ttl_seconds=self.max_ttl_seconds,
        )
        check_binding(payload, sub=sub, tool=tool, params_hash=params_hash(tool, normalized))
        return payload

    def verify_and_consume(
        self, token: str | None, *, sub: str, tool: str, params: Mapping[str, Any]
    ) -> TokenPayload:
        """Kiểm rồi tiêu `jti` (dùng một lần). Tham số sai (hash lệch) KHÔNG làm mất token."""
        payload = self.verify(token, sub=sub, tool=tool, params=params)
        self._jti.consume(payload.jti, payload.exp)
        return payload


def _normalize_or_error(tool: str, params: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return normalize_params(tool, params)
    except ParamsError as exc:
        raise YofinaError(ErrorCode.PARAMS_INVALID, str(exc)) from exc
