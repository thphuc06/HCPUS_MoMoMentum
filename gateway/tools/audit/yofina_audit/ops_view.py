"""Dựng dữ liệu của bảng vận hành (`GET /ops/traces`, `GET /ops/traces/{trace_id}`, `GET /ops/summary`) từ dòng mà các hàm
`app_ops_*` của migration 0053 trả. Hàm thuần (không I/O); hình dạng đầu ra là `OpsTraceSummary`, `OpsTraceDetail`,
`OpsSummaryResponse` của contracts/rest/openapi.yaml.

Cùng tinh thần `trace.py`: chỉ ĐỌC lại bản ghi lượt, không tính lại gì của lượt đó; phần tử hỏng thì bỏ (một dòng hỏng không làm mất
cả màn trace). Che PII ở mọi chữ tự do (nhãn và giá trị dữ liệu đã dùng, nhãn và chi tiết luật, lý do độ tin cậy) TRƯỚC khi trả:
`mask_text` (số điện thoại, email, số tài khoản, CCCD, thẻ) rồi `mask_names` (tên người Việt). Hàm SQL không trả `user_id`,
`conversation_id`, câu hỏi hay câu trả lời; người dùng chỉ hiện bằng `user_ref` mà DB đã tính.

Chi phí ước tính (`est_cost_vnd`): `token_usage` của bản ghi lượt không tách theo model, nên dùng MỘT bảng giá (USD mỗi triệu token
vào, ra, đọc cache) và tỷ giá trong cấu hình (`yofina_ledger/ops_defaults.json`), làm tròn lên số nguyên VND.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from yofina_audit.record import BlockRef, Step, Usage
from yofina_core.blocks import DataUsed, ExplainConfidence, RuleCheck, format_instant
from yofina_core.errors import ErrorCode
from yofina_core.pii import mask_names, mask_text

#: target của Gateway mà `OpsToolCall.target` nhận (enum của hợp đồng)
TOOL_TARGETS = frozenset({"ledger", "forecast", "knowledge", "planner", "audit", "ingest"})
TOOL_SEP = "___"
TOOL_ERROR_STATUSES = frozenset({"error", "denied"})
INTENT_RE = re.compile(r"^[a-z][a-z_]{0,31}$")
TOOL_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
BLOCK_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
OUTCOMES = ("ok", "rejected", "error")
_ERROR_CODES = frozenset(c.value for c in ErrorCode)


@dataclass(frozen=True)
class Pricing:
    """Bảng giá ước tính chi phí model (USD mỗi triệu token) và tỷ giá VND mỗi USD."""

    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal
    cache_read_usd_per_mtok: Decimal
    vnd_per_usd: Decimal

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> Pricing:
        try:
            p = cls(
                input_usd_per_mtok=Decimal(str(raw["input_usd_per_mtok"])),
                output_usd_per_mtok=Decimal(str(raw["output_usd_per_mtok"])),
                cache_read_usd_per_mtok=Decimal(str(raw["cache_read_usd_per_mtok"])),
                vnd_per_usd=Decimal(str(raw["vnd_per_usd"])),
            )
        except (KeyError, ArithmeticError, TypeError, ValueError) as exc:
            raise ValueError(f"Bảng giá ops sai định dạng: {exc!r}") from exc
        if (
            min(
                p.input_usd_per_mtok,
                p.output_usd_per_mtok,
                p.cache_read_usd_per_mtok,
                p.vnd_per_usd,
            )
            < 0
        ):
            raise ValueError("Bảng giá ops không được âm.")
        return p

    def cost_vnd(self, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0) -> int:
        """Chi phí ước tính, số nguyên VND, làm tròn lên (thiên về không báo thấp chi phí)."""
        usd = (
            Decimal(max(input_tokens, 0)) * self.input_usd_per_mtok
            + Decimal(max(output_tokens, 0)) * self.output_usd_per_mtok
            + Decimal(max(cache_read_tokens, 0)) * self.cache_read_usd_per_mtok
        ) / Decimal(1_000_000)
        return math.ceil(usd * self.vnd_per_usd)


# --- che PII -------------------------------------------------------------------------------------------------------
def mask(text: str) -> str:
    """Che PII trong chữ tự do của bản ghi lượt (số, email, tên người)."""
    return mask_names(mask_text(text))


def _fit(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _valid(model: type[Any], items: Iterable[Any]) -> list[Any]:
    out = []
    for it in items:
        try:
            out.append(model.model_validate(it))
        except ValidationError:
            continue
    return out


def masked_data_used(value: Any) -> list[dict[str, Any]]:
    out = []
    for d in _valid(DataUsed, _list(value))[:20]:
        item = d.model_dump(exclude_none=True)
        item["label"] = _fit(mask(d.label), 80)
        if d.value is not None:
            item["value"] = _fit(mask(d.value), 120)
        out.append(item)
    return out


def masked_rules(value: Any) -> list[dict[str, Any]]:
    out = []
    for r in _valid(RuleCheck, _list(value))[:20]:
        item = r.model_dump(exclude_none=True)
        item["label"] = _fit(mask(r.label), 80)
        if r.detail is not None:
            item["detail"] = _fit(mask(r.detail), 200)
        out.append(item)
    return out


def masked_confidence(value: Any) -> dict[str, Any] | None:
    try:
        conf = ExplainConfidence.model_validate(value)
    except ValidationError:
        return None
    return {"band": conf.band, "reasons": [_fit(mask(r), 140) for r in conf.reasons]}


# --- bước và lần gọi tool -----------------------------------------------------------------------------------------
def steps_of(value: Any) -> list[dict[str, Any]]:
    """`step_timings` đúng `TraceStep`, nguyên thứ tự, tối đa 30."""
    return [s.model_dump(exclude_none=True) for s in _valid(Step, _list(value))][:30]


def _error_code(code: Any) -> str | None:
    return code if isinstance(code, str) and code in _ERROR_CODES else None


def tool_calls_of(steps: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Lần gọi tool là bước có `step` dạng `<target>___<tool>` với target của Gateway. Bước ghi trước phase 5 không có `status`:
    coi là `ok`, cùng cách `app_ops_summary` đếm lỗi (chỉ `error`, `denied` là lỗi)."""
    out = []
    for s in steps:
        name = str(s.get("step", ""))
        target, sep, tool = name.partition(TOOL_SEP)
        if not sep or target not in TOOL_TARGETS or not TOOL_RE.fullmatch(tool):
            continue
        status = s.get("status") if s.get("status") in ("ok", "error", "denied") else "ok"
        call: dict[str, Any] = {
            "target": target,
            "tool": tool,
            "ms": int(s["ms"]),
            "status": status,
        }
        code = _error_code(s.get("code"))
        if code and status != "ok":
            call["code"] = code
        out.append(call)
    return out


def _is_tool_step(s: Mapping[str, Any]) -> bool:
    return TOOL_SEP in str(s.get("step", ""))


def _usage(value: Any) -> dict[str, Any]:
    try:
        return Usage.model_validate(value).model_dump(exclude_none=True)
    except ValidationError:
        return {"input_tokens": 0, "output_tokens": 0, "model_calls": 0}


def _cost(usage: Mapping[str, Any], pricing: Pricing) -> int:
    return pricing.cost_vnd(
        int(usage.get("input_tokens", 0)),
        int(usage.get("output_tokens", 0)),
        int(usage.get("cache_read_tokens", 0)),
    )


def _head(row: Mapping[str, Any]) -> dict[str, Any]:
    """Các trường chung của tóm tắt và chi tiết: trace_id, created_at, user_ref, intent, outcome, code, duration_ms."""
    created = row["created_at"]
    head: dict[str, Any] = {
        "trace_id": str(row["trace_id"]),
        "created_at": format_instant(created) if isinstance(created, datetime) else str(created),
        "user_ref": str(row["user_ref"]),
    }
    intent = row.get("intent")
    if isinstance(intent, str) and INTENT_RE.fullmatch(intent):
        head["intent"] = intent
    head["outcome"] = row.get("outcome") if row.get("outcome") in OUTCOMES else "ok"
    code = _error_code(row.get("code"))
    if code:
        head["code"] = code
    head["duration_ms"] = max(int(row.get("duration_ms") or 0), 0)
    return head


def trace_summary(row: Mapping[str, Any], pricing: Pricing) -> dict[str, Any]:
    """Một dòng của `app_ops_list_traces` -> `OpsTraceSummary`."""
    usage = _usage(row.get("token_usage"))
    steps = steps_of(row.get("step_timings"))
    tools = [s for s in steps if _is_tool_step(s)]
    return {
        **_head(row),
        "model_calls": usage["model_calls"],
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "est_cost_vnd": _cost(usage, pricing),
        "tool_calls": len(tools),
        "tool_errors": sum(1 for s in tools if s.get("status") in TOOL_ERROR_STATUSES),
        "rules_failed": sum(
            1 for r in _valid(RuleCheck, _list(row.get("rules_checked"))) if r.outcome == "fail"
        ),
    }


def trace_detail(row: Mapping[str, Any], pricing: Pricing) -> dict[str, Any]:
    """Dòng của `app_ops_get_trace` -> `OpsTraceDetail` (đã che PII, `pii_masked` luôn đúng)."""
    usage = _usage(row.get("token_usage"))
    steps = steps_of(row.get("step_timings"))
    out: dict[str, Any] = {
        **_head(row),
        "steps": steps,
        "tool_calls": tool_calls_of(steps),
        "rules_checked": masked_rules(row.get("rules_checked")),
        "data_used": masked_data_used(row.get("data_used")),
    }
    conf = masked_confidence(row.get("confidence"))
    if conf is not None:
        out["confidence"] = conf
    out["blocks_emitted"] = [
        b.model_dump()
        for b in _valid(BlockRef, _list(row.get("blocks_emitted")))
        if BLOCK_ID_RE.fullmatch(b.id)
    ][:40]
    out["token_usage"] = usage
    out["est_cost_vnd"] = _cost(usage, pricing)
    out["pii_masked"] = True
    return out


def summary(
    row: Mapping[str, Any] | None,
    *,
    start: datetime,
    end: datetime,
    model_calls_by_day: Sequence[Mapping[str, Any]],
    pricing: Pricing,
) -> dict[str, Any]:
    """Dòng của `app_ops_summary` cộng lượt gọi model theo ngày -> `OpsSummaryResponse`. Không có lượt thì không có `latency_ms`."""
    r = row or {}

    def n(key: str) -> int:
        return max(int(r.get(key) or 0), 0)

    tool_calls, tool_errors = n("tool_calls"), n("tool_errors")
    out: dict[str, Any] = {
        "from": format_instant(start),
        "to": format_instant(end),
        "turns": n("turns"),
        "turns_rejected": n("turns_rejected"),
        "turns_error": n("turns_error"),
    }
    if out["turns"] > 0 and r.get("p50_ms") is not None and r.get("p95_ms") is not None:
        out["latency_ms"] = {"p50": n("p50_ms"), "p95": n("p95_ms")}
    out["tool_calls"] = tool_calls
    out["tool_errors"] = tool_errors
    out["tool_error_rate"] = round(tool_errors / tool_calls, 4) if tool_calls else 0
    out["rule_fails"] = n("rule_fails")
    out["model_calls_by_day"] = [dict(d) for d in model_calls_by_day][-31:]
    out["est_cost_vnd"] = pricing.cost_vnd(n("input_tokens"), n("output_tokens"))
    return out
