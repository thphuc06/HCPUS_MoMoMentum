"""Đọc cấu hình từ biến môi trường, rồi từ SSM Parameter Store.

Quy tắc dự án ("không hardcode"): model id, ngưỡng, trần lượt gọi, URL, tên tài nguyên, biểu phí
nằm trong cấu hình, không rải trong code, và **không có giá trị mặc định gắn với tài khoản AWS**.

Thứ tự tra một khóa `name`:
1. biến môi trường `YOFINA_<NAME>` (chữ hoa);
2. SSM Parameter `<prefix>/<name>` (chữ thường) nếu có `YOFINA_SSM_PREFIX` (ví dụ `/yofina`);
   `SecureString` được giải mã; kết quả được cache trong tiến trình.
Không thấy và không có `default` thì ném `ConfigError` (không đoán).

Ví dụ: `Config().get_int("confirm_token_ttl_seconds")` đọc
`YOFINA_CONFIRM_TOKEN_TTL_SECONDS` hoặc `/yofina/confirm_token_ttl_seconds`.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any, Protocol, TypeVar

T = TypeVar("T")

ENV_PREFIX = "YOFINA_"
SSM_PREFIX_ENV = "YOFINA_SSM_PREFIX"
_MISSING: Any = object()


class ConfigError(RuntimeError):
    """Thiếu hoặc sai cấu hình."""


class SsmClient(Protocol):
    def get_parameter(self, *, Name: str, WithDecryption: bool) -> Mapping[str, Any]: ...


class Config:
    """Nguồn cấu hình có thể thay thế trong test (truyền `env` và `ssm`)."""

    def __init__(self, env: Mapping[str, str] | None = None, ssm: SsmClient | None = None) -> None:
        self._env: Mapping[str, str] = os.environ if env is None else env
        self._ssm = ssm
        self._cache: dict[str, str] = {}

    def _ssm_client(self) -> SsmClient:
        if self._ssm is None:
            import boto3  # chỉ import khi thật sự cần tới SSM

            self._ssm = boto3.client("ssm", region_name=self.region())
        return self._ssm

    def _lookup(self, name: str) -> str | None:
        env_key = ENV_PREFIX + name.upper()
        if env_key in self._env:
            return self._env[env_key]
        prefix = self._env.get(SSM_PREFIX_ENV)
        if not prefix:
            return None
        path = f"{prefix.rstrip('/')}/{name.lower()}"
        if path in self._cache:
            return self._cache[path]
        client = self._ssm_client()
        try:
            resp = client.get_parameter(Name=path, WithDecryption=True)
        except Exception as exc:
            if type(exc).__name__ == "ParameterNotFound":
                return None
            raise ConfigError(f"Không đọc được SSM {path}: {exc}") from exc
        value = str(resp["Parameter"]["Value"])
        self._cache[path] = value
        return value

    def get(self, name: str, *, default: Any = _MISSING, cast: Callable[[str], Any] = str) -> Any:
        raw = self._lookup(name)
        if raw is None:
            if default is _MISSING:
                raise ConfigError(
                    f"Thiếu cấu hình '{name}' (biến {ENV_PREFIX}{name.upper()} hoặc SSM)"
                )
            return default
        try:
            return cast(raw)
        except (ValueError, ArithmeticError) as exc:
            raise ConfigError(f"Cấu hình '{name}' sai định dạng: {raw!r}") from exc

    def get_int(self, name: str, **kw: Any) -> int:
        return self.get(name, cast=int, **kw)

    def get_decimal(self, name: str, **kw: Any) -> Decimal:
        return self.get(name, cast=Decimal, **kw)

    def get_bool(self, name: str, **kw: Any) -> bool:
        return self.get(name, cast=_parse_bool, **kw)

    def region(self) -> str:
        """Region tường minh: `YOFINA_REGION` rồi `AWS_REGION`; không có mặc định."""
        for key in ("YOFINA_REGION", "AWS_REGION"):
            if self._env.get(key):
                return self._env[key]
        raise ConfigError("Thiếu YOFINA_REGION/AWS_REGION: Region phải được đặt tường minh")


def _parse_bool(raw: str) -> bool:
    v = raw.strip().lower()
    if v in {"1", "true", "yes", "on"}:
        return True
    if v in {"0", "false", "no", "off"}:
        return False
    raise ValueError(raw)


_default = Config()


def get(name: str, **kw: Any) -> Any:
    """Tra cứu bằng nguồn mặc định (môi trường tiến trình + SSM)."""
    return _default.get(name, **kw)
