"""Client `rds-data` giả dựa trên PostgreSQL cục bộ (pgserver), để chạy NGUYÊN mã `yofina_core.db.DataApi` và `LedgerRepo`
trên một Postgres thật mà không cần Aurora.

Trả đúng DẠNG phản hồi của RDS Data API (`columnMetadata`, `records` với `stringValue`/`longValue`/`isNull`...), nên cả
`to_parameters` lẫn `parse_records` của mã sản phẩm đều chạy thật. Chuyển `:ten` thành tham số psycopg, giữ nguyên `::` và
`CAST(... AS ...)`. Kết nối bằng role `yofina_app` (không phải owner, NOBYPASSRLS) nên RLS và quyền bảng được kiểm thật.

Chỉ dùng trong test (không import từ mã sản phẩm). Chạy bằng Python 3.12 vì pgserver chưa có wheel cho 3.13 (xem README).
"""

from __future__ import annotations

import itertools
import json
import re
import threading
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import psycopg

_PARAM = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")


def _convert_sql(sql: str) -> str:
    return _PARAM.sub(lambda m: f"%({m.group(1)})s", sql.replace("%", "%%"))


#: pgserver cục bộ không kèm cơ sở dữ liệu múi giờ IANA (Aurora thì có): đổi tên múi giờ của ứng dụng sang chuỗi POSIX tương
#: đương (Việt Nam là UTC+7, không có giờ mùa hè) chỉ trong bản giả này.
_POSIX_TZ = {"Asia/Ho_Chi_Minh": "UTC-7"}


def _from_param(p: dict[str, Any]) -> Any:
    v = p["value"]
    if v.get("isNull"):
        return None
    if "booleanValue" in v:
        return v["booleanValue"]
    if "longValue" in v:
        return v["longValue"]
    if "stringValue" in v:
        if p.get("typeHint") == "DECIMAL":
            return Decimal(v["stringValue"])
        return _POSIX_TZ.get(v["stringValue"], v["stringValue"])
    raise TypeError(f"Tham số Data API không hỗ trợ: {v}")


def _field(value: Any) -> dict[str, Any]:
    if value is None:
        return {"isNull": True}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"longValue": value}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, Decimal):
        return {"stringValue": format(value, "f")}
    if isinstance(value, datetime):
        return {"stringValue": value.astimezone(UTC).replace(tzinfo=None).isoformat(sep=" ")}
    if isinstance(value, date):
        return {"stringValue": value.isoformat()}
    if isinstance(value, (dict, list)) and not isinstance(value, str):
        if isinstance(value, list) and all(isinstance(x, str) for x in value):
            return {"arrayValue": {"stringValues": value}}
        return {"stringValue": json.dumps(value, ensure_ascii=False)}
    if isinstance(value, uuid.UUID):
        return {"stringValue": str(value)}
    return {"stringValue": str(value)}


class LocalRdsData:
    """Cùng giao diện với boto3 `rds-data` (phần `DataApi` dùng)."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._tx: dict[str, psycopg.Connection] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self.calls: list[str] = []  # tên thao tác theo thứ tự, để test đếm số lần gọi

    def _connect(self, autocommit: bool) -> psycopg.Connection:
        return psycopg.connect(self._dsn, autocommit=autocommit)

    def _run(self, conn: psycopg.Connection, sql: str, params: dict[str, Any]) -> dict[str, Any]:
        with conn.cursor() as cur:
            cur.execute(_convert_sql(sql), params)
            if cur.description is None:
                return {"numberOfRecordsUpdated": cur.rowcount}
            meta = []
            for col in cur.description:
                t = conn.adapters.types.get(col.type_code)
                meta.append(
                    {"label": col.name, "name": col.name, "typeName": t.name if t else "text"}
                )
            rows = cur.fetchall()
        return {
            "columnMetadata": meta,
            "records": [[_field(v) for v in row] for row in rows],
        }

    def execute_statement(self, **kw: Any) -> dict[str, Any]:
        self.calls.append("execute")
        params = {p["name"]: _from_param(p) for p in kw.get("parameters", [])}
        tx = kw.get("transactionId")
        if tx:
            return self._run(self._tx[tx], kw["sql"], params)
        with self._connect(True) as conn:
            return self._run(conn, kw["sql"], params)

    def batch_execute_statement(self, **kw: Any) -> dict[str, Any]:
        self.calls.append("batch")
        conn = self._tx[kw["transactionId"]]
        for ps in kw["parameterSets"]:
            self._run(conn, kw["sql"], {p["name"]: _from_param(p) for p in ps})
        return {"updateResults": []}

    def begin_transaction(self, **kw: Any) -> dict[str, Any]:
        self.calls.append("begin")
        with self._lock:
            tid = f"tx-{next(self._ids)}"
        self._tx[tid] = self._connect(False)
        return {"transactionId": tid}

    def commit_transaction(self, **kw: Any) -> dict[str, Any]:
        self.calls.append("commit")
        conn = self._tx.pop(kw["transactionId"])
        try:
            conn.commit()
        finally:
            conn.close()
        return {"transactionStatus": "Transaction Committed"}

    def rollback_transaction(self, **kw: Any) -> dict[str, Any]:
        self.calls.append("rollback")
        conn = self._tx.pop(kw["transactionId"], None)
        if conn is not None:
            try:
                conn.rollback()
            finally:
                conn.close()
        return {"transactionStatus": "Rollback Complete"}
