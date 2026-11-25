"""Tool `forecast___get_forecast` (target `forecast` của Gateway): dự báo MỚI NHẤT của một hũ, tính lại trước khi trả nếu cũ.

Dùng đúng mã dựng khối của ledger (`WalletReads.forecast_block`) nên `GET /forecasts/{jar_code}` và tool trả CÙNG số (tiêu chí 8:
chat và màn Chi tiết hũ cùng số). Khác ledger ở chỗ Lambda này có engine: dự báo chưa có hoặc quá hạn độ tươi thì chạy
`Pipeline.run_user(trigger = read)` rồi đọc lại; không tính được mà vẫn còn bản cũ thì trả bản cũ với `stale: true`.

Kết quả theo `contracts/tools/forecast.results.schema.json`: `{status, as_of, app_date, data}`, `data` = `ForecastTimelineData`.

Phase 4 (luồng A): CŨNG phục vụ `forecast___get_resilience_score` và `forecast___stress_test` qua Gateway (`resilience.py`, `stress.py`)
và REST `GET /resilience`, `GET /resilience/shocks`, `POST /resilience/stress` của HTTP API (cùng engine, cùng số với tool).
`planner___optimize_allocation` KHÔNG đi qua đây: ledger gọi Invoke Lambda forecast-batch (op `optimize_allocation`, `batch.py`).

Phase 3: Lambda này CŨNG phục vụ `forecast___run_scenario` và `forecast___list_scenarios` (`scenario.py`) và `forecast___affordability_check` (`afford.py`) qua Gateway,
và đường REST `POST /affordability` của HTTP API (cùng engine, trả khối `affordability_card`). `GET /forecasts/{jar_code}` vẫn do
Lambda ledger phục vụ.

Phase 5 (luồng B): `forecast___get_behavior_profile` và REST `GET /profile/behavior` CHỈ ĐỌC bảng `behavior_profiles` (`behavior.py`,
batch đêm tính và ghi); không gọi model. `handler_tool.py` không truyền engine nên mỗi lần gọi dựng `BehaviorEngine` từ pipeline.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from yofina_core.blocks import (
    block_to_wire,
    build_affordability_card,
    build_resilience_score,
    build_stress_result,
    new_trace_id,
    trace_id_from_traceparent,
)
from yofina_core.errors import ErrorCode, ToolStatus, YofinaError
from yofina_forecast.afford import AffordabilityEngine
from yofina_forecast.behavior import BehaviorEngine
from yofina_forecast.resilience import ResilienceEngine
from yofina_forecast.runner import Pipeline
from yofina_forecast.scenario import ScenarioEngine
from yofina_forecast.stress import StressEngine, list_shocks
from yofina_ledger.rest_api import _body, _claims, _header, error_response, response
from yofina_ledger.wallet_reads import WalletReads

log = logging.getLogger("yofina.forecast.tool")

TOOL_PREFIX = "forecast___"
SOURCE_TOOL = "forecast___get_forecast"
AFFORDABILITY_BODY_FIELDS = frozenset({"amount_vnd", "funding_source", "jar", "pay_jar", "label", "date"})
STRESS_BODY_FIELDS = frozenset({"shock_id"})


@dataclass(frozen=True)
class ReadSettings:
    """Phần của `LedgerSettings` mà `WalletReads.forecast_block` dùng."""

    forecast_freshness_seconds: int
    app_timezone: str

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)


class ForecastReader(WalletReads):
    """`WalletReads` dùng riêng việc dựng khối dự báo (không cần xác nhận, bảng tra hay sự kiện của ledger)."""

    def __init__(
        self,
        repo: Any,
        settings: ReadSettings,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repo = repo
        self.settings = settings
        self._clock = clock

    def now(self) -> datetime:
        return self._clock()

    def _app_date(self, offset: int | None, now: datetime):  # type: ignore[no-untyped-def]
        from yofina_core.clock import app_today

        return app_today(offset or 0, now, self.settings.tz)


def error_result(code: ErrorCode, message: str) -> dict[str, Any]:
    return {"status": str(ToolStatus.ERROR), "code": str(code), "message": message}


def tool_name(context: Any) -> str:
    custom = dict(getattr(getattr(context, "client_context", None), "custom", None) or {})
    full = str(custom.get("bedrockAgentCoreToolName", ""))
    return full.split(TOOL_PREFIX, 1)[1] if full.startswith(TOOL_PREFIX) else full.split("___")[-1]


def get_forecast(
    reader: ForecastReader, pipeline: Pipeline, user_id: str, jar: Any, *, trace_id: str
) -> dict[str, Any]:
    if not isinstance(jar, str) or not jar:
        raise YofinaError(ErrorCode.PARAMS_INVALID, "Thiếu mã hũ.")
    block = reader.forecast_block_or_none(user_id, jar, trace_id=trace_id, source_tool=SOURCE_TOOL)
    if block is None or block.data.stale:
        try:
            pipeline.run_user(user_id, trigger="read", trace_id=trace_id)
            block = (
                reader.forecast_block_or_none(
                    user_id, jar, trace_id=trace_id, source_tool=SOURCE_TOOL
                )
                or block
            )
        except (
            Exception
        ) as exc:  # không tính được: giữ bản cũ (stale) nếu có, không thì báo chưa sẵn sàng
            log.warning(
                json.dumps({"msg": "recompute_failed", "error": f"{type(exc).__name__}"[:80]})
            )
    if block is None:
        raise YofinaError(
            ErrorCode.FORECAST_UNAVAILABLE,
            "Chưa có dự báo cho hũ này và chưa tính được ngay, thử lại sau ít phút.",
        )
    return {
        "status": str(ToolStatus.OK),
        "as_of": block.source.as_of,
        "app_date": block.source.app_date,
        "data": block.data.model_dump(mode="json", exclude_none=True),
    }


def handle_gateway(
    event: Mapping[str, Any],
    context: Any,
    reader: ForecastReader,
    pipeline: Pipeline,
    scenario: ScenarioEngine | None = None,
    afford: AffordabilityEngine | None = None,
    resilience: ResilienceEngine | None = None,
    stress: StressEngine | None = None,
    behavior: BehaviorEngine | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    tool = tool_name(context)
    trace_id = new_trace_id()
    outcome = "UNKNOWN"
    try:
        user_id = event.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            raise YofinaError(ErrorCode.UNAUTHENTICATED, "Thiếu thông tin người dùng.")
        if tool == "get_forecast":
            result = get_forecast(reader, pipeline, user_id, event.get("jar"), trace_id=trace_id)
        elif tool == "run_scenario" and scenario is not None:
            result = scenario.run(
                user_id,
                event.get("scenario"),
                trace_id=trace_id,
                conversation_id=event.get("conversation_id"),
                with_scenarios=event.get("with_scenarios"),
            )
        elif tool == "list_scenarios" and scenario is not None:
            result = scenario.list_scenarios(
                user_id,
                conversation_id=event.get("conversation_id"),
                limit=event.get("limit"),
            )
        elif tool == "affordability_check" and afford is not None:
            result = afford.check(
                user_id,
                amount_vnd=event.get("amount_vnd"),
                funding_source=event.get("funding_source"),
                jar=event.get("jar"),
                pay_jar=event.get("pay_jar"),
                label=event.get("label"),
                pay_date=event.get("date"),
            )
        elif tool == "get_resilience_score" and resilience is not None:
            result = resilience.get(user_id, refresh=event.get("refresh"))
        elif tool == "stress_test" and stress is not None:
            result = stress.run(user_id, event.get("shock_id"))
        elif tool == "get_behavior_profile":
            result = (behavior or BehaviorEngine(pipeline)).get(
                user_id, insight_kind=event.get("insight_kind"), jar=event.get("jar")
            )
        else:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Tool không tồn tại.")
        outcome = str(result["status"])
        return result
    except YofinaError as exc:
        outcome = str(exc.code)
        return exc.tool_result()
    except Exception:
        outcome = "INTERNAL_ERROR"
        log.exception("forecast_tool_unhandled tool=%s trace_id=%s", tool, trace_id)
        return error_result(ErrorCode.INTERNAL_ERROR, "Có lỗi hệ thống, thử lại sau.")
    finally:
        log.info(
            json.dumps(
                {
                    "msg": "gateway_call",
                    "tool": tool,
                    "trace_id": trace_id,
                    "outcome": outcome,
                    "ms": round((time.perf_counter() - started) * 1000, 1),
                }
            )
        )


# --- REST: POST /affordability, GET /resilience, GET /resilience/shocks, POST /resilience/stress (HTTP API, JWT) ----
def _as_of(result: Mapping[str, Any]) -> tuple[datetime, date]:
    return (
        datetime.fromisoformat(result["as_of"].replace("Z", "+00:00")),
        date.fromisoformat(result["app_date"]),
    )


def handle_http(
    event: Mapping[str, Any],
    afford: AffordabilityEngine,
    resilience: ResilienceEngine | None = None,
    stress: StressEngine | None = None,
    behavior: BehaviorEngine | None = None,
) -> dict[str, Any]:
    """Đường vào HTTP API (payload v2) của Lambda này (x-lambda: forecast): `POST /affordability` (khối `affordability_card`),
    `GET /resilience` (khối `resilience_score`), `GET /resilience/shocks` (danh sách cú sốc đọc từ `shocks.json`),
    `POST /resilience/stress` (khối `stress_result`) và `GET /profile/behavior` (phase 5: `BehaviorProfileData`, cùng `data` với tool
    `forecast___get_behavior_profile`). Danh tính CHỈ lấy từ claim `sub` của JWT authorizer; thân yêu cầu không có
    `user_id`. Cùng engine, cùng số với tool tương ứng."""
    started = time.perf_counter()
    http = event.get("requestContext", {}).get("http", {})
    route = f"{str(http.get('method', '')).upper()} {str(event.get('rawPath') or http.get('path') or '').rstrip('/') or '/'}"
    trace_id = trace_id_from_traceparent(_header(event, "traceparent")) or new_trace_id()
    outcome = "UNKNOWN"
    try:
        sub = _claims(event).get("sub")
        if not isinstance(sub, str) or not sub:
            raise YofinaError(ErrorCode.UNAUTHENTICATED, "Thiếu hoặc sai thông tin đăng nhập.")
        if route == "POST /affordability":
            body = _body(event)
            extra = sorted(set(body) - AFFORDABILITY_BODY_FIELDS)
            if extra:  # hợp đồng AffordabilityRequest không có trường lạ; danh tính chỉ đến từ JWT
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID, "Trường không hợp lệ: " + ", ".join(extra)[:80]
                )
            result = afford.check(
                sub,
                amount_vnd=body.get("amount_vnd"),
                funding_source=body.get("funding_source"),
                jar=body.get("jar"),
                pay_jar=body.get("pay_jar"),
                label=body.get("label"),
                pay_date=body.get("date"),
            )
            as_of, app_date = _as_of(result)
            wire = block_to_wire(
                build_affordability_card(
                    data=result["data"],
                    trace_id=trace_id,
                    source_tool="rest:POST /affordability",
                    as_of=as_of,
                    app_date=app_date,
                )
            )
        elif route == "GET /resilience" and resilience is not None:
            result = resilience.get(sub)
            as_of, app_date = _as_of(result)
            wire = block_to_wire(
                build_resilience_score(
                    data=result["data"],
                    trace_id=trace_id,
                    source_tool="rest:GET /resilience",
                    as_of=as_of,
                    app_date=app_date,
                )
            )
        elif route == "GET /resilience/shocks" and resilience is not None:
            wire = list_shocks()
        elif route == "POST /resilience/stress" and stress is not None:
            body = _body(event)
            extra = sorted(set(body) - STRESS_BODY_FIELDS)
            if extra:
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID, "Trường không hợp lệ: " + ", ".join(extra)[:80]
                )
            result = stress.run(sub, body.get("shock_id"))
            as_of, app_date = _as_of(result)
            wire = block_to_wire(
                build_stress_result(
                    data=result["data"],
                    trace_id=trace_id,
                    source_tool="rest:POST /resilience/stress",
                    as_of=as_of,
                    app_date=app_date,
                )
            )
        elif route == "GET /profile/behavior":
            engine = behavior or BehaviorEngine(afford.pipeline)
            wire = engine.get(sub)["data"]
        else:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Đường dẫn không tồn tại.")
        outcome = "200"
        return response(200, wire)
    except YofinaError as exc:
        outcome = str(exc.code)
        return error_response(exc.code, exc.message, trace_id)
    except Exception:
        outcome = "INTERNAL_ERROR"
        log.exception("forecast_rest_unhandled route=%s trace_id=%s", route, trace_id)
        return error_response(ErrorCode.INTERNAL_ERROR, "Có lỗi hệ thống, thử lại sau.", trace_id)
    finally:
        log.info(
            json.dumps(
                {
                    "msg": "rest_request",
                    "route": route,
                    "trace_id": trace_id,
                    "outcome": outcome,
                    "ms": round((time.perf_counter() - started) * 1000, 1),
                }
            )
        )
