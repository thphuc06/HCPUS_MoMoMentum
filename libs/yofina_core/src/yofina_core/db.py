"""Client RDS Data API cho Aurora (spike: docs/research/spike-aurora-data-api.md §4-§7).

Quy tắc đã chứng minh trong spike và được cài ở đây:

- **Đường đọc**: gọi hàm plpgsql `app_*` (db/migrations), một lệnh gọi Data API; hàm tự
  `set_config('app.user_id', ..., true)` nên RLS áp theo người dùng. Dùng `DataApi.query`.
- **Đường ghi**: `with api.transaction(user_id) as tx:` = `BeginTransaction` -> `set_config('app.user_id',
  :uid, true)` -> các câu lệnh -> `Commit`. Rời khỏi khối `with` bằng ngoại lệ (hoặc thoát mà chưa
  commit) thì **luôn rollback trong `finally`**: một transaction bỏ dở giữ khóa tới ~3 phút.
- Dùng secret của role `yofina_app` (không bao giờ secret master: master vượt RLS).
- `DatabaseResumingException` (Aurora đang dậy sau auto-pause) được retry trong ngân sách thời gian
  cấu hình; hết ngân sách thì `YofinaError(DATABASE_UNAVAILABLE)`. boto3 không tự retry loại lỗi này.
- Mọi truy vấn nhiều dòng phải có `LIMIT` (phản hồi tối đa 1 MiB, vượt là lỗi cả lệnh): trách nhiệm của
  câu SQL; `query(..., max_rows=...)` thêm một lưới an toàn phía client.
- `numeric` về dạng chuỗi -> `Decimal`; `timestamptz` về dạng chuỗi UTC không hậu tố -> `datetime` có
  múi giờ UTC; `date` -> `date`; `jsonb` -> đối tượng Python. Tiền là `Decimal`/`int`, **không float**.
- Tham số: `None`, `bool`, `int`, `str`, `Decimal` (kèm typeHint DECIMAL), `date`/`datetime` (gửi dạng
  chuỗi ISO; câu SQL phải `CAST(:p AS date)` hoặc `CAST(:p AS timestamptz)`: Data API không tự ép
  kiểu chuỗi), `dict`/`list` (gửi dạng JSON, câu SQL phải `CAST(:p AS jsonb)`).
- Cấu hình (ARN cluster, ARN secret, tên DB, ngân sách retry) lấy từ `yofina_core.config` (biến môi
  trường `YOFINA_DB_CLUSTER_ARN`... do CDK đặt, hoặc SSM), không gắn cứng.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Protocol

from yofina_core.config import Config
from yofina_core.errors import HTTP_STATUS, ErrorCode, YofinaError

log = logging.getLogger(__name__)

Params = Mapping[str, Any]
Row = dict[str, Any]
#: một tiền tố mã kiểu `ErrorCode` ("ROADMAP_VERSION_CONFLICT: ") trong thông điệp lỗi của Postgres; mã có thuộc `ErrorCode` không
#: thì `_sql_business_code` kiểm
_SQL_CODE_RE = re.compile(r"\b([A-Z][A-Z0-9_]+): ")


class RdsDataClient(Protocol):
    """Phần của boto3 `rds-data` mà module dùng (để thay bằng đối tượng giả trong test)."""

    def execute_statement(self, **kwargs: Any) -> dict[str, Any]: ...
    def batch_execute_statement(self, **kwargs: Any) -> dict[str, Any]: ...
    def begin_transaction(self, **kwargs: Any) -> dict[str, Any]: ...
    def commit_transaction(self, **kwargs: Any) -> dict[str, Any]: ...
    def rollback_transaction(self, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True)
class DataApiSettings:
    cluster_arn: str
    secret_arn: str
    database: str
    #: tổng thời gian tối đa chờ Aurora dậy (giây), cộng dồn các lần retry
    resume_max_wait_seconds: float = 20.0
    #: nghỉ giữa hai lần retry (giây); spike: lần thành công đầu tiên sau ~16 giây
    resume_sleep_seconds: float = 1.5

    @classmethod
    def from_config(cls, cfg: Config | None = None) -> DataApiSettings:
        cfg = cfg or Config()
        return cls(
            cluster_arn=cfg.get("db_cluster_arn"),
            secret_arn=cfg.get("db_app_secret_arn"),
            database=cfg.get("db_name"),
            resume_max_wait_seconds=float(cfg.get("db_resume_max_wait_seconds", default="20")),
            resume_sleep_seconds=float(cfg.get("db_resume_sleep_seconds", default="1.5")),
        )


def _ts_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime gửi vào DB phải có múi giờ")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def to_parameter(name: str, value: Any) -> dict[str, Any]:
    """Một giá trị Python -> tham số Data API."""
    if value is None:
        return {"name": name, "value": {"isNull": True}}
    if isinstance(value, bool):
        return {"name": name, "value": {"booleanValue": value}}
    if isinstance(value, int):
        return {"name": name, "value": {"longValue": value}}
    if isinstance(value, float):
        raise TypeError(f"Tham số {name}: không gửi float vào DB (dùng int, Decimal hoặc str)")
    if isinstance(value, Decimal):
        return {"name": name, "value": {"stringValue": format(value, "f")}, "typeHint": "DECIMAL"}
    if isinstance(value, datetime):
        return {"name": name, "value": {"stringValue": _ts_text(value)}}
    if isinstance(value, date):
        return {"name": name, "value": {"stringValue": value.isoformat()}}
    if isinstance(value, (dict, list)):
        return {"name": name, "value": {"stringValue": json.dumps(value, ensure_ascii=False)}}
    if isinstance(value, str):
        return {"name": name, "value": {"stringValue": value}}
    raise TypeError(f"Tham số {name}: kiểu {type(value).__name__} không được hỗ trợ")


def to_parameters(params: Params | None) -> list[dict[str, Any]]:
    return [to_parameter(k, v) for k, v in (params or {}).items()]


def _parse_timestamp(text: str) -> datetime:
    # '2026-11-21 02:13:37.658608' (UTC, không hậu tố); chấp nhận cả dạng có hậu tố.
    dt = datetime.fromisoformat(text.strip().replace(" ", "T", 1))
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _convert(field_value: Mapping[str, Any], type_name: str) -> Any:
    if field_value.get("isNull"):
        return None
    if "stringValue" in field_value:
        s = field_value["stringValue"]
        t = type_name.lower()
        if t in {"numeric", "decimal"}:
            return Decimal(s)
        if t in {"timestamptz", "timestamp"}:
            return _parse_timestamp(s)
        if t == "date":
            return date.fromisoformat(s)
        if t in {"jsonb", "json"}:
            return json.loads(s)
        return s
    for key in ("longValue", "doubleValue", "booleanValue", "blobValue"):
        if key in field_value:
            return field_value[key]
    if "arrayValue" in field_value:
        arr = field_value["arrayValue"]
        for key in ("longValues", "doubleValues", "booleanValues", "stringValues"):
            if key in arr:
                return list(arr[key])
        return []
    return None


def parse_records(response: Mapping[str, Any]) -> list[Row]:
    """`execute_statement(includeResultMetadata=True)` -> danh sách dict theo tên cột."""
    meta = response.get("columnMetadata") or []
    names = [m.get("label") or m.get("name") for m in meta]
    types = [m.get("typeName", "") for m in meta]
    rows: list[Row] = []
    for rec in response.get("records") or []:
        rows.append({n: _convert(f, t) for n, t, f in zip(names, types, rec, strict=False)})
    return rows


def _error_code(exc: Exception) -> str:
    resp = getattr(exc, "response", None)
    if isinstance(resp, Mapping):
        return str(resp.get("Error", {}).get("Code", ""))
    return type(exc).__name__


def _is_resuming(exc: Exception) -> bool:
    return _error_code(exc) == "DatabaseResumingException" or (
        type(exc).__name__ == "DatabaseResumingException"
    )


class DataApi:
    """Client Data API cho một cặp (cluster, secret của role `yofina_app`, database)."""

    def __init__(
        self,
        settings: DataApiSettings,
        client: RdsDataClient | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        region: str | None = None,
    ) -> None:
        self.settings = settings
        self._client = client
        self._region = region
        self._sleep = sleep
        self._monotonic = monotonic

    @classmethod
    def from_config(cls, cfg: Config | None = None) -> DataApi:
        cfg = cfg or Config()
        return cls(DataApiSettings.from_config(cfg), region=cfg.region())

    @property
    def client(self) -> RdsDataClient:
        if self._client is None:
            import boto3
            from botocore.config import Config as BotoConfig

            self._client = boto3.client(
                "rds-data",
                region_name=self._region,
                config=BotoConfig(
                    connect_timeout=5,
                    read_timeout=40,
                    retries={"max_attempts": 2, "mode": "standard"},
                ),
            )
        return self._client

    # --- retry --------------------------------------------------------------------------
    def _call(self, op: str, **kwargs: Any) -> dict[str, Any]:
        """Gọi một thao tác Data API, retry `DatabaseResumingException` trong ngân sách thời gian."""
        fn = getattr(self.client, op)
        deadline = self._monotonic() + self.settings.resume_max_wait_seconds
        while True:
            try:
                return fn(**kwargs)
            except Exception as exc:
                if _is_resuming(exc):
                    if self._monotonic() + self.settings.resume_sleep_seconds > deadline:
                        raise YofinaError(
                            ErrorCode.DATABASE_UNAVAILABLE,
                            "Cơ sở dữ liệu đang khởi động, thử lại sau vài giây.",
                        ) from exc
                    log.info("db_resuming op=%s: chờ rồi thử lại", op)
                    self._sleep(self.settings.resume_sleep_seconds)
                    continue
                raise _translate(exc) from exc

    def _base(self) -> dict[str, Any]:
        s = self.settings
        return {"resourceArn": s.cluster_arn, "secretArn": s.secret_arn, "database": s.database}

    # --- đọc ----------------------------------------------------------------------------
    def execute(
        self, sql: str, params: Params | None = None, *, transaction_id: str | None = None
    ) -> list[Row]:
        kwargs = self._base()
        kwargs.update(sql=sql, includeResultMetadata=True)
        if params:
            kwargs["parameters"] = to_parameters(params)
        if transaction_id:
            kwargs["transactionId"] = transaction_id
        return parse_records(self._call("execute_statement", **kwargs))

    def query(
        self, sql: str, params: Params | None = None, *, max_rows: int | None = None
    ) -> list[Row]:
        """Truy vấn đọc ngoài transaction (thường là `SELECT * FROM app_*(:uid, ...)`).

        `max_rows` là lưới an toàn: nếu DB trả nhiều hơn thì báo lỗi (câu SQL thiếu LIMIT).
        """
        rows = self.execute(sql, params)
        if max_rows is not None and len(rows) > max_rows:
            raise YofinaError(ErrorCode.INTERNAL_ERROR, "Truy vấn trả quá nhiều dòng.")
        return rows

    # --- ghi ----------------------------------------------------------------------------
    @contextmanager
    def transaction(self, user_id: str) -> Iterator[Transaction]:
        """Transaction của một người dùng: set_config('app.user_id') rồi các câu lệnh rồi Commit.

        Thoát bình thường thì commit; ngoại lệ thì rollback. `finally` luôn rollback nếu chưa commit.
        """
        if not user_id:
            raise ValueError("transaction cần user_id")
        base = self._base()
        tx_id = self._call("begin_transaction", **base)["transactionId"]
        tx = Transaction(self, tx_id)
        committed = False
        try:
            self.execute(
                "SELECT set_config('app.user_id', :uid, true)",
                {"uid": user_id},
                transaction_id=tx_id,
            )
            yield tx
            self._call(
                "commit_transaction",
                resourceArn=base["resourceArn"],
                secretArn=base["secretArn"],
                transactionId=tx_id,
            )
            committed = True
        finally:
            if not committed:
                try:
                    self.client.rollback_transaction(
                        resourceArn=base["resourceArn"],
                        secretArn=base["secretArn"],
                        transactionId=tx_id,
                    )
                except Exception:
                    log.warning("rollback_transaction thất bại (transaction có thể đã hết hạn)")

    def batch(
        self,
        sql: str,
        param_sets: Sequence[Params],
        *,
        transaction_id: str,
    ) -> None:
        """`BatchExecuteStatement` trong một transaction (chèn nhiều dòng một lệnh gọi)."""
        if not param_sets:
            return
        kwargs = self._base()
        kwargs.update(
            sql=sql,
            parameterSets=[to_parameters(p) for p in param_sets],
            transactionId=transaction_id,
        )
        self._call("batch_execute_statement", **kwargs)


@dataclass
class Transaction:
    api: DataApi
    id: str
    statements: int = field(default=0)

    def execute(self, sql: str, params: Params | None = None) -> list[Row]:
        self.statements += 1
        return self.api.execute(sql, params, transaction_id=self.id)

    def batch(self, sql: str, param_sets: Sequence[Params]) -> None:
        self.statements += 1
        self.api.batch(sql, param_sets, transaction_id=self.id)


def _sql_business_code(exc: Exception) -> ErrorCode | None:
    """Mã nghiệp vụ nhóm 4xx nếu `exc` là lỗi do hàm SQL `app_*` ném theo quy ước `RAISE EXCEPTION 'MÃ: ...'` (db/README.md), với MÃ
    là một `ErrorCode` (Data API giữ dạng `ERROR: ROADMAP_VERSION_CONFLICT: ...`). Mã 5xx (`INTERNAL_ERROR`) hay chữ lạ thì None."""
    for m in _SQL_CODE_RE.finditer(str(exc)):
        code = ErrorCode.__members__.get(m.group(1))
        if code is not None:
            return code if HTTP_STATUS[code] < 500 else None
    return None


def _translate(exc: Exception) -> Exception:
    """Lỗi boto3 khác -> `YofinaError` không rò chi tiết SQL; log giữ nguyên chi tiết.

    Lỗi nghiệp vụ dự kiến của hàm SQL (mã 4xx, ví dụ `ROADMAP_VERSION_CONFLICT`) là việc của người dùng hoặc dữ liệu, không phải sự cố:
    ghi WARNING, không ghi ERROR. Không hạ xuống INFO vì tầng này không biết bên gọi trả mã nào: lộ trình đổi về đúng mã 4xx
    (`roadmap_logic.db_business_error`), còn các đường khác vẫn trả `INTERNAL_ERROR` khi hàm SQL chặn một tham số mà REST lẽ ra đã chặn
    trước. Lỗi còn lại là lỗi hệ thống, ghi ERROR. Chữ có dấu trong thông điệp của Postgres có thể đã bị Data API thay bằng U+FFFD trước
    khi tới đây (xem `roadmap_logic.DB_ERROR_FALLBACK`); log ghi nguyên văn những gì nhận."""
    code = _error_code(exc)
    business = _sql_business_code(exc)
    if business is not None:
        log.warning(
            json.dumps(
                {"msg": "data_api_business_error", "code": str(business), "aws_code": code, "detail": str(exc)[:500]},
                ensure_ascii=False,
            )
        )
    else:
        log.error("data_api_error code=%s detail=%s", code, str(exc)[:500])
    if code in {"ServiceUnavailableError", "StatementTimeoutException"}:
        return YofinaError(ErrorCode.DATABASE_UNAVAILABLE, "Cơ sở dữ liệu tạm thời không phản hồi.")
    if isinstance(exc, YofinaError):
        return exc
    return YofinaError(ErrorCode.INTERNAL_ERROR, "Lỗi hệ thống khi truy cập dữ liệu.")
