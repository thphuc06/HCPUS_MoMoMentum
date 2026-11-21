"""Mã lỗi máy đọc được, dùng chung cho REST (`contracts/rest/openapi.yaml`), kết quả tool
(`contracts/tools/ledger.results.schema.json`) và `notice.data.code` của khối UI.

Danh sách và ánh xạ HTTP status phải khớp `components.schemas.ErrorCode` trong OpenAPI
(test `tests/unit/test_contracts_rest.py` kiểm).
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    PARAMS_INVALID = "PARAMS_INVALID"
    JAR_NOT_FOUND = "JAR_NOT_FOUND"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    AMOUNT_LIMIT_EXCEEDED = "AMOUNT_LIMIT_EXCEEDED"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    TOKEN_INVALID = "TOKEN_INVALID"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_REUSED = "TOKEN_REUSED"
    PARAMS_MISMATCH = "PARAMS_MISMATCH"
    RATE_LIMITED = "RATE_LIMITED"
    MODEL_BUDGET_EXCEEDED = "MODEL_BUDGET_EXCEEDED"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.PARAMS_INVALID: 400,
    ErrorCode.JAR_NOT_FOUND: 404,
    ErrorCode.INSUFFICIENT_FUNDS: 422,
    ErrorCode.AMOUNT_LIMIT_EXCEEDED: 422,
    ErrorCode.NEEDS_CONFIRMATION: 428,
    ErrorCode.TOKEN_INVALID: 403,
    ErrorCode.TOKEN_EXPIRED: 403,
    ErrorCode.TOKEN_REUSED: 409,
    ErrorCode.PARAMS_MISMATCH: 409,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.MODEL_BUDGET_EXCEEDED: 503,
    ErrorCode.DATABASE_UNAVAILABLE: 503,
    ErrorCode.INTERNAL_ERROR: 500,
}


class ToolStatus(StrEnum):
    """Trường `status` trong kết quả tool ledger (Lambda trả về Gateway hoặc REST nội bộ)."""

    OK = "OK"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    ERROR = "ERROR"


class YofinaError(Exception):
    """Lỗi nghiệp vụ có mã máy đọc được (`ErrorCode`) và câu tiếng Việt hiển thị được.

    Dùng xuyên suốt tầng ledger: tool trả `{"status": "ERROR", code, message}`, REST ánh xạ
    `HTTP_STATUS[code]`. `message` không chứa dữ liệu nhạy cảm (không token, không số dư của người khác).
    """

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message

    @property
    def http_status(self) -> int:
        return HTTP_STATUS[self.code]
