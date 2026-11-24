"""Bảng vận hành (FR15, phase 5): đọc bản ghi lượt của MỌI người dùng cho màn trace X1 và trang tổng hợp.

Ba thao tác (`GET /ops/traces`, `GET /ops/traces/{trace_id}`, `GET /ops/summary`, contracts/rest/openapi.yaml). Quyền nhóm Cognito
`ops` do `ops_rest` kiểm TRƯỚC khi tới đây (DB không biết JWT). Dữ liệu đọc qua bốn hàm SECURITY DEFINER `app_ops_*` của migration
0053, chỉ trả cột đã chọn (không `user_id`, `conversation_id`, câu hỏi hay câu trả lời); dựng và che PII ở `yofina_audit.ops_view`.

Lượt gọi model theo ngày so với trần: đọc bộ đếm DynamoDB `yofina-usage` (khóa `day` + `model`, thuộc tính `count`) mà
`yofina_core.llm` tăng trước MỖI lời gọi Bedrock của mọi thành phần (agent, nạp dữ liệu, phân loại, sinh lại lộ trình). Ngày là
ngày của múi giờ trần (`budget_timezone` của `llm_defaults.json`), đúng cửa sổ mà trần được tính. Trần tính theo TỪNG model, nên mỗi
ngày có `by_model` (model id, lượt gọi, trần ngày của model đó); `cap` của ngày chỉ là tổng trần các model đang cấu hình. Bảng có TTL
(`usage_ttl_days`) nên ngày cũ hơn không còn số. Không đọc được bảng thì dùng số lượt gọi model ghi
trong bản ghi lượt của agent (`app_ops_model_calls_by_day`, ngày UTC; chỉ tính agent, nên thấp hơn số thật; không có `by_model`) và ghi
log cảnh báo.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from importlib import resources
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from yofina_audit.ops_view import Pricing, summary, trace_detail, trace_summary
from yofina_core.config import Config
from yofina_core.errors import ErrorCode, YofinaError

log = logging.getLogger("yofina.ledger.ops")

DEFAULTS_FILE = "ops_defaults.json"
TRACE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
INTENT_RE = re.compile(r"^[a-z][a-z_]{0,31}$")
ISO_INSTANT_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})$"
)
UINT_RE = re.compile(r"^[0-9]{1,9}$")
OUTCOMES = frozenset({"ok", "rejected", "error"})
LIST_LIMIT_DEFAULT, LIST_LIMIT_MAX = 50, 100
CURSOR_MAX = 200
MAX_DAYS_IN_SUMMARY = 31  # maxItems của `model_calls_by_day`
MAX_MODELS_PER_DAY = 20  # maxItems của `OpsDayModelCalls.by_model`

SQL_LIST_TRACES = (
    "SELECT * FROM app_ops_list_traces(CAST(:p_from AS timestamptz), CAST(:p_to AS timestamptz), CAST(:p_intent AS text), "
    "CAST(:p_outcome AS text), CAST(:p_min_duration AS integer), CAST(:p_before_created AS timestamptz), "
    "CAST(:p_before_trace AS text), CAST(:p_limit AS integer))"
)
SQL_GET_TRACE = "SELECT * FROM app_ops_get_trace(CAST(:p_trace_id AS text))"
SQL_SUMMARY = (
    "SELECT * FROM app_ops_summary(CAST(:p_from AS timestamptz), CAST(:p_to AS timestamptz))"
)
SQL_MODEL_CALLS_BY_DAY = "SELECT * FROM app_ops_model_calls_by_day(CAST(:p_from AS timestamptz), CAST(:p_to AS timestamptz))"


class Db(Protocol):
    def query(
        self, sql: str, params: Mapping[str, Any] | None = None, *, max_rows: int | None = None
    ) -> list[dict[str, Any]]: ...


# --- cấu hình --------------------------------------------------------------------------------------------------------
def load_defaults() -> dict[str, Any]:
    text = resources.files("yofina_ledger").joinpath(DEFAULTS_FILE).read_text(encoding="utf-8")
    return json.loads(text)


@dataclass(frozen=True)
class OpsSettings:
    pricing: Pricing
    #: khoảng mặc định khi không truyền `from` (ngày)
    default_range_days: int
    #: khoảng tối đa của `/ops/summary` (ngày; hàm SQL cũng chặn 31)
    max_summary_days: int
    #: múi giờ của trần gọi model (khóa `day` của `yofina-usage`)
    budget_timezone: str
    #: trần ngày của từng model id đang cấu hình (lấy lớn nhất nếu một model ở nhiều vai)
    model_caps: Mapping[str, int] = field(default_factory=dict)

    @property
    def daily_cap_total(self) -> int:
        return max(sum(self.model_caps.values()), 1)

    @classmethod
    def from_config(cls, cfg: Config | None = None, *, llm_settings: Any = None) -> OpsSettings:
        """Mặc định đóng gói (`ops_defaults.json`), ghi đè bằng `YOFINA_OPS_PRICING` (JSON) và `YOFINA_OPS_DEFAULT_RANGE_DAYS`.
        Trần và múi giờ trần đọc bằng `yofina_core.llm.load_settings` (cùng nguồn với cổng gọi model)."""
        cfg = cfg or Config()
        d = load_defaults()
        raw_pricing = cfg.get("ops_pricing", default=None)
        pricing_src = d["pricing"]
        if raw_pricing:
            try:
                pricing_src = {**pricing_src, **json.loads(raw_pricing)}
            except ValueError as exc:
                raise ValueError(f"YOFINA_OPS_PRICING không phải JSON: {exc}") from exc
        days = cfg.get_int("ops_default_range_days", default=int(d["default_range_days"]))
        max_days = min(int(d["max_summary_days"]), MAX_DAYS_IN_SUMMARY)
        if not 1 <= days <= max_days:
            raise ValueError(f"ops_default_range_days phải trong 1..{max_days}")
        if llm_settings is None:
            from yofina_core.llm import load_settings

            llm_settings = load_settings()
        caps: dict[str, int] = {}
        for specs in llm_settings.roles.values():
            for spec in specs:
                caps[spec.id] = max(caps.get(spec.id, 0), int(spec.daily_cap))
        return cls(
            pricing=Pricing.from_mapping(pricing_src),
            default_range_days=days,
            max_summary_days=max_days,
            budget_timezone=llm_settings.budget_timezone,
            model_caps=caps,
        )


# --- đọc DB -----------------------------------------------------------------------------------------------------------
class OpsRepo:
    """SQL của bảng vận hành: chỉ gọi bốn hàm `app_ops_*` (SECURITY DEFINER, chỉ trả cột đã chọn)."""

    def __init__(self, db: Db) -> None:
        self.db = db

    def list_traces(
        self,
        *,
        start: datetime,
        end: datetime,
        intent: str | None,
        outcome: str | None,
        min_duration_ms: int | None,
        before: tuple[datetime, str] | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        return self.db.query(
            SQL_LIST_TRACES,
            {
                "p_from": start,
                "p_to": end,
                "p_intent": intent,
                "p_outcome": outcome,
                "p_min_duration": min_duration_ms,
                "p_before_created": before[0] if before else None,
                "p_before_trace": before[1] if before else None,
                "p_limit": limit,
            },
            max_rows=LIST_LIMIT_MAX,
        )

    def get_trace(self, trace_id: str) -> dict[str, Any] | None:
        rows = self.db.query(SQL_GET_TRACE, {"p_trace_id": trace_id}, max_rows=1)
        return rows[0] if rows else None

    def summary(self, start: datetime, end: datetime) -> dict[str, Any] | None:
        rows = self.db.query(SQL_SUMMARY, {"p_from": start, "p_to": end}, max_rows=1)
        return rows[0] if rows else None

    def model_calls_by_day(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        return self.db.query(
            SQL_MODEL_CALLS_BY_DAY, {"p_from": start, "p_to": end}, max_rows=MAX_DAYS_IN_SUMMARY + 1
        )


# --- bộ đếm lượt gọi model (DynamoDB `yofina-usage`) -----------------------------------------------------------------
class UsageReader:
    """Đọc bộ đếm của `yofina_core.llm.DynamoUsageStore`: `Query` theo khóa `day`, lấy `count` của từng model. Chỉ đọc."""

    def __init__(self, table_name: str, client: Any = None, *, region: str | None = None) -> None:
        self._table, self._client, self._region = table_name, client, region

    @classmethod
    def from_config(cls, cfg: Config | None = None) -> UsageReader | None:
        cfg = cfg or Config()
        table = cfg.get("usage_table", default="")
        return cls(table, region=cfg.region()) if table else None

    def _ddb(self) -> Any:
        if self._client is None:
            import boto3
            from botocore.config import Config as BotoConfig

            self._client = boto3.client(
                "dynamodb",
                region_name=self._region,
                config=BotoConfig(connect_timeout=3, read_timeout=5, retries={"max_attempts": 2}),
            )
        return self._client

    def calls_by_model_on(self, day: date) -> dict[str, int]:
        """Lượt gọi theo model id trong một ngày (khóa `day` + `model`), mọi trang của `Query`."""
        out: dict[str, int] = {}
        kw: dict[str, Any] = {
            "TableName": self._table,
            # `day`, `model` và `count` đi qua tên giả (`day`, `count` là từ khóa dành riêng của DynamoDB)
            "KeyConditionExpression": "#d = :d",
            "ProjectionExpression": "#m, #c",
            "ExpressionAttributeNames": {"#d": "day", "#m": "model", "#c": "count"},
            "ExpressionAttributeValues": {":d": {"S": day.isoformat()}},
        }
        while True:
            page = self._ddb().query(**kw)
            for item in page.get("Items", []):
                raw = item.get("count", {}).get("N")
                if raw is not None:
                    model = str(item.get("model", {}).get("S") or "")
                    out[model] = out.get(model, 0) + int(raw)
            if not page.get("LastEvaluatedKey"):
                return out
            kw["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def calls_on(self, day: date) -> int:
        return sum(self.calls_by_model_on(day).values())


# --- tham số ------------------------------------------------------------------------------------------------------
def _instant(value: Any, name: str) -> datetime | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not ISO_INSTANT_RE.fullmatch(value):
        raise YofinaError(
            ErrorCode.PARAMS_INVALID, f"{name} phải là thời điểm RFC 3339 có múi giờ."
        )
    try:
        return datetime.fromisoformat(value).astimezone(UTC)
    except ValueError:
        raise YofinaError(
            ErrorCode.PARAMS_INVALID, f"{name} không phải thời điểm hợp lệ."
        ) from None


def _uint(value: Any, name: str, *, lo: int, hi: int) -> int | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not UINT_RE.fullmatch(value) or not lo <= int(value) <= hi:
        raise YofinaError(ErrorCode.PARAMS_INVALID, f"{name} phải là số nguyên trong {lo}..{hi}.")
    return int(value)


def encode_cursor(created_at: datetime, trace_id: str) -> str:
    raw = f"{created_at.astimezone(UTC).isoformat()}|{trace_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: Any) -> tuple[datetime, str]:
    bad = YofinaError(ErrorCode.PARAMS_INVALID, "cursor không hợp lệ.")
    if not isinstance(cursor, str) or not 1 <= len(cursor) <= CURSOR_MAX:
        raise bad
    try:
        text = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        created_text, trace_id = text.split("|", 1)
        created = datetime.fromisoformat(created_text)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise bad from None
    if created.tzinfo is None or not TRACE_ID_RE.fullmatch(trace_id):
        raise bad
    return created.astimezone(UTC), trace_id


# --- dịch vụ ------------------------------------------------------------------------------------------------------
class OpsService:
    def __init__(
        self,
        repo: OpsRepo,
        settings: OpsSettings,
        *,
        usage: UsageReader | None,
        now: Callable[[], datetime],
    ) -> None:
        self.repo, self.settings, self.usage, self.now = repo, settings, usage, now

    def _range(self, q: Mapping[str, Any], *, max_days: int | None) -> tuple[datetime, datetime]:
        end = _instant(q.get("to"), "to") or self.now().astimezone(UTC)
        start = _instant(q.get("from"), "from") or end - timedelta(
            days=self.settings.default_range_days
        )
        if end < start:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "to phải sau from.")
        if max_days is not None and end - start > timedelta(days=max_days):
            raise YofinaError(ErrorCode.PARAMS_INVALID, f"Khoảng thời gian tối đa {max_days} ngày.")
        return start, end

    def list_traces(self, q: Mapping[str, Any]) -> dict[str, Any]:
        """`GET /ops/traces`: `OpsTraceListResponse`, mới nhất trước, phân trang theo (created_at, trace_id)."""
        start, end = self._range(q, max_days=None)
        intent = q.get("intent") or None
        if intent is not None and (not isinstance(intent, str) or not INTENT_RE.fullmatch(intent)):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "intent không hợp lệ.")
        outcome = q.get("outcome") or None
        if outcome is not None and outcome not in OUTCOMES:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "outcome phải là ok, rejected hoặc error.")
        min_ms = _uint(q.get("min_duration_ms"), "min_duration_ms", lo=0, hi=2_147_483_647)
        limit = _uint(q.get("limit"), "limit", lo=1, hi=LIST_LIMIT_MAX) or LIST_LIMIT_DEFAULT
        before = decode_cursor(q["cursor"]) if q.get("cursor") else None
        rows = self.repo.list_traces(
            start=start,
            end=end,
            intent=intent,
            outcome=outcome,
            min_duration_ms=min_ms,
            before=before,
            limit=limit,
        )[:limit]
        out: dict[str, Any] = {"traces": [trace_summary(r, self.settings.pricing) for r in rows]}
        if len(rows) == limit and isinstance(rows[-1].get("created_at"), datetime):
            out["next_cursor"] = encode_cursor(rows[-1]["created_at"], str(rows[-1]["trace_id"]))
        return out

    def get_trace(self, trace_id: Any) -> dict[str, Any]:
        """`GET /ops/traces/{trace_id}`: `OpsTraceDetail`; sai dạng hay không có đều 404 (hợp đồng không có 400)."""
        if not isinstance(trace_id, str) or not TRACE_ID_RE.fullmatch(trace_id):
            raise YofinaError(ErrorCode.TRACE_NOT_FOUND, "Không tìm thấy trace.")
        row = self.repo.get_trace(trace_id)
        if row is None:
            raise YofinaError(ErrorCode.TRACE_NOT_FOUND, "Không tìm thấy trace.")
        return trace_detail(row, self.settings.pricing)

    def summary(self, q: Mapping[str, Any]) -> dict[str, Any]:
        """`GET /ops/summary`: `OpsSummaryResponse`."""
        start, end = self._range(q, max_days=self.settings.max_summary_days)
        row = self.repo.summary(start, end)
        return summary(
            row,
            start=start,
            end=end,
            model_calls_by_day=self.model_calls_by_day(start, end),
            pricing=self.settings.pricing,
        )

    def model_calls_by_day(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        cap = self.settings.daily_cap_total
        if self.usage is not None:
            try:
                return self._usage_by_day(start, end, cap)
            except Exception as exc:  # bảng không đọc được: dùng bản ghi lượt, không làm hỏng trang
                log.warning(
                    json.dumps({"msg": "ops_usage_unreadable", "error": type(exc).__name__})
                )
        rows = self.repo.model_calls_by_day(start, end)
        return [
            {"day": _day(r["day"]), "model_calls": int(r["model_calls"]), "cap": cap}
            for r in rows
            if int(r.get("model_calls") or 0) > 0
        ][-MAX_DAYS_IN_SUMMARY:]

    def _usage_by_day(self, start: datetime, end: datetime, cap: int) -> list[dict[str, Any]]:
        assert self.usage is not None
        tz = ZoneInfo(self.settings.budget_timezone)
        days = _days(start.astimezone(tz).date(), end.astimezone(tz).date())[-MAX_DAYS_IN_SUMMARY:]
        caps = self.settings.model_caps
        out = []
        for d in days:
            by_model = {m: n for m, n in self.usage.calls_by_model_on(d).items() if n > 0}
            calls = sum(by_model.values())
            if calls > 0:
                rows = []
                for model in sorted(by_model)[:MAX_MODELS_PER_DAY]:
                    row: dict[str, Any] = {"model": model[:200] or "unknown", "model_calls": by_model[model]}
                    if model in caps:
                        row["cap"] = int(caps[model])
                    rows.append(row)
                out.append({"day": d.isoformat(), "model_calls": calls, "cap": cap, "by_model": rows})
        return out


def _days(first: date, last: date) -> list[date]:
    n = (last - first).days
    return [first + timedelta(days=i) for i in range(n + 1)]


def _day(value: Any) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


def build_ops(service: Any) -> OpsService:
    """Dịch vụ vận hành của Lambda thật: dùng chung DataApi và đồng hồ với `LedgerService`."""
    return OpsService(
        OpsRepo(service.repo.db),
        OpsSettings.from_config(),
        usage=UsageReader.from_config(),
        now=service.now,
    )


__all__: Sequence[str] = (
    "OpsRepo",
    "OpsService",
    "OpsSettings",
    "UsageReader",
    "build_ops",
    "decode_cursor",
    "encode_cursor",
)
