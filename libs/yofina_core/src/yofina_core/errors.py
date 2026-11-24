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
    ALREADY_APPLIED = "ALREADY_APPLIED"
    RATE_LIMITED = "RATE_LIMITED"
    MODEL_BUDGET_EXCEEDED = "MODEL_BUDGET_EXCEEDED"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    # Phase 2 (ví mô phỏng và dự báo): thêm CUỐI danh sách để không đổi thứ tự mã cũ.
    PROFILE_INCOMPLETE = "PROFILE_INCOMPLETE"
    TRANSACTION_NOT_FOUND = "TRANSACTION_NOT_FOUND"
    OBLIGATION_NOT_FOUND = "OBLIGATION_NOT_FOUND"
    PAYEE_NOT_FOUND = "PAYEE_NOT_FOUND"
    SALARY_EVENT_NOT_FOUND = "SALARY_EVENT_NOT_FOUND"
    JAR_PROTECTED = "JAR_PROTECTED"
    CREDIT_LIMIT_EXCEEDED = "CREDIT_LIMIT_EXCEEDED"
    DUPLICATE_TRANSACTION = "DUPLICATE_TRANSACTION"
    FORECAST_UNAVAILABLE = "FORECAST_UNAVAILABLE"
    # Phase 3 (what-if, kiểm tra trước khi quẹt): thêm CUỐI danh sách.
    OFFER_EXPIRED = "OFFER_EXPIRED"
    TRACE_NOT_FOUND = "TRACE_NOT_FOUND"
    NUDGE_NOT_FOUND = "NUDGE_NOT_FOUND"
    FEE_SCHEDULE_NOT_FOUND = "FEE_SCHEDULE_NOT_FOUND"
    FORECAST_NOT_APPLICABLE = "FORECAST_NOT_APPLICABLE"
    SCENARIO_INVALID = "SCENARIO_INVALID"
    # Phase 5 (F6, nạp dữ liệu từ ảnh và CSV): thêm cuối danh sách.
    CONSENT_REQUIRED = "CONSENT_REQUIRED"
    INGEST_JOB_NOT_FOUND = "INGEST_JOB_NOT_FOUND"
    INGEST_JOB_NOT_READY = "INGEST_JOB_NOT_READY"
    INGEST_UNSUPPORTED_TYPE = "INGEST_UNSUPPORTED_TYPE"
    INGEST_TOO_LARGE = "INGEST_TOO_LARGE"
    INGEST_NOT_FINANCIAL = "INGEST_NOT_FINANCIAL"
    INGEST_DUPLICATE_FILE = "INGEST_DUPLICATE_FILE"
    # Phase 4 (chống chịu, lộ trình, phân hũ tự động): thêm cuối danh sách.
    ROADMAP_NOT_FOUND = "ROADMAP_NOT_FOUND"
    ROADMAP_INVALID = "ROADMAP_INVALID"
    ROADMAP_VERSION_CONFLICT = "ROADMAP_VERSION_CONFLICT"
    SHOCK_NOT_FOUND = "SHOCK_NOT_FOUND"
    # Phase 5 (bộ nhớ dài hạn): thêm cuối danh sách.
    MEMORY_RECORD_NOT_FOUND = "MEMORY_RECORD_NOT_FOUND"
    MEMORY_UNAVAILABLE = "MEMORY_UNAVAILABLE"

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
    ErrorCode.ALREADY_APPLIED: 409,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.MODEL_BUDGET_EXCEEDED: 503,
    ErrorCode.DATABASE_UNAVAILABLE: 503,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.PROFILE_INCOMPLETE: 422,
    ErrorCode.TRANSACTION_NOT_FOUND: 404,
    ErrorCode.OBLIGATION_NOT_FOUND: 404,
    ErrorCode.PAYEE_NOT_FOUND: 404,
    ErrorCode.SALARY_EVENT_NOT_FOUND: 404,
    ErrorCode.JAR_PROTECTED: 422,
    ErrorCode.CREDIT_LIMIT_EXCEEDED: 422,
    ErrorCode.DUPLICATE_TRANSACTION: 409,
    ErrorCode.FORECAST_UNAVAILABLE: 503,
    ErrorCode.OFFER_EXPIRED: 410,
    ErrorCode.TRACE_NOT_FOUND: 404,
    ErrorCode.NUDGE_NOT_FOUND: 404,
    ErrorCode.FEE_SCHEDULE_NOT_FOUND: 404,
    ErrorCode.FORECAST_NOT_APPLICABLE: 404,
    ErrorCode.SCENARIO_INVALID: 422,
    ErrorCode.CONSENT_REQUIRED: 403,
    ErrorCode.INGEST_JOB_NOT_FOUND: 404,
    ErrorCode.INGEST_JOB_NOT_READY: 409,
    ErrorCode.INGEST_UNSUPPORTED_TYPE: 415,
    ErrorCode.INGEST_TOO_LARGE: 413,
    ErrorCode.INGEST_NOT_FINANCIAL: 422,
    ErrorCode.INGEST_DUPLICATE_FILE: 409,
    ErrorCode.ROADMAP_NOT_FOUND: 404,
    ErrorCode.ROADMAP_INVALID: 422,
    ErrorCode.ROADMAP_VERSION_CONFLICT: 409,
    ErrorCode.SHOCK_NOT_FOUND: 404,
    ErrorCode.MEMORY_RECORD_NOT_FOUND: 404,
    ErrorCode.MEMORY_UNAVAILABLE: 503,
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
