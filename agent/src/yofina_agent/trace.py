"""Bản ghi lượt (`agent_turn`) cho bảng "Vì sao": dữ liệu đã dùng, luật đã kiểm, độ tin cậy (do mã viết, không do LLM), khối đã phát, token, thời gian.

Hình dạng khớp cột của migration `0010_what_if_audit.sql` (`audit_events` với `event_type = 'agent_turn'`) và `contracts/tools/audit.results.schema.json`
(`TraceDetail`, `explain`). Hàm ở đây thuần (không I/O) để test được; việc ghi nằm ở `store.TurnRecordStore`.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from yofina_agent.tools import ToolKind, ToolOutcome
from yofina_core import blocks as B
from yofina_core.errors import ErrorCode
from yofina_core.suitability import SuitabilityVerdict

_BAND_ORDER = {"high": 2, "medium": 1, "low": 0}
_OUTCOME_RANK = {"fail": 3, "warn": 2, "pass": 1, "skipped": 0}

#: `TraceStep` của contracts/tools/audit.results.schema.json (và `Step` của yofina_audit.record)
MAX_STEPS = 30
TOOL_SEP = "___"
_STEP_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,39}$")
_TOOL_STATUSES = frozenset({"ok", "error", "denied"})

# nhãn hiển thị của nguồn dữ liệu theo tên tool (chuỗi giao diện của bảng "Vì sao")
TOOL_LABELS: dict[str, str] = {
    "get_jar_balances": "Số dư các hũ",
    "query_transactions": "Giao dịch gần đây",
    "get_cashflow_summary": "Dòng tiền",
    "get_obligations": "Nghĩa vụ sắp đến hạn",
    "get_forecast": "Dự báo hũ",
    "run_scenario": "Mô phỏng kịch bản",
    "list_scenarios": "Các khoản đang cân nhắc trong cuộc trò chuyện",
    "affordability_check": "Kiểm tra trước khi chi",
    "get_fee_schedule": "Biểu phí",
    "check_suitability": "Kiểm tra luật phù hợp",
}


def short_name(tool: str) -> str:
    return tool.split("___", 1)[-1]


def describe_tool(outcome: ToolOutcome) -> tuple[str, str | None]:
    """(nhãn, giá trị ngắn) của một nguồn dữ liệu. Giá trị chỉ là nhãn mô tả, không phải số liệu tài chính."""
    name = short_name(outcome.name)
    label = TOOL_LABELS.get(name, name)
    d = (outcome.payload or {}).get("data") or {}
    value: str | None = None
    if name == "get_jar_balances":
        value = f"{len(d.get('jars', []))} hũ"
    elif name == "get_obligations":
        value = f"{len(d.get('obligations', []))} khoản"
    elif name == "get_forecast":
        value = (d.get("jar") or {}).get("name")
    elif name == "run_scenario":
        bundle = d.get("bundle") or []
        if len(bundle) > 1:
            value = " + ".join(str(b.get("label") or b.get("kind")) for b in bundle if isinstance(b, dict))
        else:
            value = (d.get("spec") or {}).get("label") or (d.get("spec") or {}).get("kind")
    elif name == "list_scenarios":
        value = f"{len(d.get('scenarios', []))} kịch bản"
    elif name == "get_fee_schedule":
        value = d.get("product_label")
    elif name == "affordability_check":
        value = d.get("label")
    elif name == "query_transactions":
        value = f"{len(d.get('transactions', []))} giao dịch"
    return label, (str(value)[:120] if value else None)


def data_used(outcomes: Iterable[ToolOutcome]) -> list[dict[str, Any]]:
    """Mỗi tool ĐỌC thành công đóng góp một dòng (khử trùng theo (nhãn, giá trị)); tool kiểm luật và tool ghi không tính là dữ liệu."""
    rows: dict[tuple[str, str | None], dict[str, Any]] = {}
    for o in outcomes:
        if o.kind is not ToolKind.OK or short_name(o.name) == "check_suitability":
            continue
        label, value = describe_tool(o)
        item = B.DataUsed(label=label, value=value, tool=o.name, as_of=(o.payload or {}).get("as_of")).model_dump(exclude_none=True)
        rows.setdefault((label, value), item)
    if not rows:  # lượt không đụng dữ liệu tài khoản (từ chối ngoài phạm vi, xã giao, hỏi lại): bảng "Vì sao" vẫn nói thật
        return [B.DataUsed(label="Chỉ câu hỏi của bạn (không dùng dữ liệu tài khoản)", tool="agent").model_dump(exclude_none=True)]
    return list(rows.values())[:20]


def merge_rules(
    verdicts: Sequence[SuitabilityVerdict], extra: Sequence[B.RuleCheck] = ()
) -> list[dict[str, Any]]:
    """Gộp các `RuleCheck` của mọi phương án: mỗi luật một dòng, giữ kết quả nặng nhất (fail > warn > pass > skipped)."""
    best: dict[str, B.RuleCheck] = {}
    for rc in [*extra, *(c for v in verdicts for c in v.checked)]:
        cur = best.get(rc.rule_id)
        if cur is None or _OUTCOME_RANK[rc.outcome] > _OUTCOME_RANK[cur.outcome]:
            best[rc.rule_id] = rc
    return [r.model_dump(exclude_none=True) for r in list(best.values())[:20]]


def confidence(bases: Sequence[Mapping[str, Any]], *, verified: bool | None = None) -> dict[str, Any]:
    """Nhóm tin cậy Cao/Vừa/Thấp kèm lý do, viết bằng mã từ cơ sở của dự báo (`ForecastBasis`)."""
    if not bases:
        reasons = ["Số liệu lấy trực tiếp từ sổ cái của bạn, không qua ước lượng."]
        return B.ExplainConfidence(band="high", reasons=reasons).model_dump()
    band = min((b["confidence_band"] for b in bases), key=lambda x: _BAND_ORDER[x])
    days = min(int(b["history_days"]) for b in bases)
    cover = min(float(b["coverage"]) for b in bases)
    reasons = [f"Dự báo dựa trên {days} ngày dữ liệu.", f"Khoảng dự báo phủ {round(cover * 100)}% khi thử lại trên dữ liệu thật."]
    if any(b["is_initial_estimate"] for b in bases):
        reasons.append("Có ước lượng ban đầu, chưa đủ lịch sử riêng của bạn.")
    if any(b["stale"] for b in bases):
        reasons.append("Dự báo đã cũ, chưa được tính lại với dữ liệu mới nhất.")
    if verified is False:
        reasons.append("Phần lời giải thích chưa qua kiểm chứng nên không được hiển thị.")
    return B.ExplainConfidence(band=band, reasons=reasons[:4]).model_dump()


@dataclass
class TurnStep:
    """Một bước đã đo của lượt, theo thứ tự BẮT ĐẦU (lượt tạo bước khi vào, điền `ms` khi ra).

    Bước gọi tool có `step` là `<target>___<tool>`, `status` (`ok`, `error`, `denied`, đúng enum `TraceStep`) và `code` khi lỗi.
    Không bao giờ chứa tham số hay kết quả của tool (PII, số tiền).
    """

    step: str
    ms: int = 0
    status: str | None = None
    code: str | None = None


def tool_step_name(target: str, short: str) -> str:
    """Tên bước của một lần gọi tool: luôn `<target>___<tool>` theo target của Gateway (không theo tiền tố cấu hình)."""
    return f"{target}{TOOL_SEP}{short}"


def tool_status(outcome: ToolOutcome) -> tuple[str, str | None]:
    """(`status`, `code`) của một lần gọi tool theo `ToolKind`. `TraceStep` chỉ có ok/error/denied: UNAVAILABLE (hết giờ, không kết nối,
    vượt trần tool call) và BAD_RESULT là `error`, phân biệt bằng `code` (DATABASE_UNAVAILABLE, RATE_LIMITED, INTERNAL_ERROR...)."""
    if outcome.ok:
        return "ok", None
    status = "denied" if outcome.kind is ToolKind.DENIED else "error"
    code = outcome.code if isinstance(outcome.code, str) and _CODE_RE.fullmatch(outcome.code) else None
    return status, code or ErrorCode.INTERNAL_ERROR.value


def _as_step(s: TurnStep | tuple[str, int]) -> TurnStep:
    return s if isinstance(s, TurnStep) else TurnStep(s[0], s[1])


def _is_tool(row: Mapping[str, Any]) -> bool:
    return TOOL_SEP in row["step"]


def _fit(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Giữ trong `MAX_STEPS` (maxItems của `TraceStep[]`; ghi quá thì `record_turn` từ chối CẢ bản ghi). Bỏ lần gọi tool `ok` lặp nhiều
    nhất trước (lần sau cùng của tool đó), nên mọi bước không phải tool, mọi lần lỗi và ít nhất một lần của mỗi tool còn lại; thứ tự giữ nguyên."""
    keep = list(range(len(rows)))
    while len(keep) > MAX_STEPS:
        counts = Counter(rows[i]["step"] for i in keep if _is_tool(rows[i]) and rows[i].get("status") == "ok")
        if not counts:
            break
        name = max(counts, key=lambda n: counts[n])
        keep.remove(max(i for i in keep if rows[i]["step"] == name and rows[i].get("status") == "ok"))
    return [rows[i] for i in keep][:MAX_STEPS]


def step_timings(steps: Iterable[TurnStep | tuple[str, int]]) -> list[dict[str, Any]]:
    """`step_timings` của bản ghi lượt, theo thứ tự bắt đầu.

    Mỗi lần gọi tool là MỘT bước (hai lần gọi cùng tool là hai bước), kèm `status` và `code` khi lỗi. Bước khác (router, guardrail_out,
    verifier...) cùng tên thì cộng dồn ở vị trí đầu tiên, như bảng "Vì sao" vẫn hiển thị. Bước sai mẫu tên bị bỏ (một bước sai làm
    `record_turn` từ chối cả bản ghi). Tối đa `MAX_STEPS`.
    """
    rows: list[dict[str, Any]] = []
    merged: dict[str, dict[str, Any]] = {}
    for raw in steps:
        s = _as_step(raw)
        if not _STEP_RE.fullmatch(s.step):
            continue
        ms = max(int(s.ms), 0)
        if TOOL_SEP in s.step:
            row: dict[str, Any] = {"step": s.step, "ms": ms}
            if s.status in _TOOL_STATUSES:
                row["status"] = s.status
                if s.status != "ok" and s.code and _CODE_RE.fullmatch(s.code):
                    row["code"] = s.code
            rows.append(row)
        elif (prev := merged.get(s.step)) is not None:
            prev["ms"] += ms
        else:
            merged[s.step] = {"step": s.step, "ms": ms}
            rows.append(merged[s.step])
    return _fit(rows)


def token_usage(usage_by_model: Sequence[Mapping[str, Any]], model_calls: int) -> dict[str, Any]:
    return {
        "input_tokens": sum(int(u.get("inputTokens", 0)) for u in usage_by_model),
        "output_tokens": sum(int(u.get("outputTokens", 0)) for u in usage_by_model),
        "model_calls": model_calls,
    }


def build_record(
    *,
    trace_id: str,
    conversation_id: str,
    intent: str | None,
    outcome: str,
    code: str | None,
    outcomes: Iterable[ToolOutcome],
    suitability: Sequence[SuitabilityVerdict],
    extra_rules: Sequence[B.RuleCheck],
    bases: Sequence[Mapping[str, Any]],
    blocks: Iterable[Mapping[str, Any]],
    usage_by_model: Sequence[Mapping[str, Any]],
    model_calls: int,
    steps: Iterable[TurnStep | tuple[str, int]],
    duration_ms: int,
    verified: bool | None = None,
) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "trace_id": trace_id,
        "conversation_id": conversation_id,
        "outcome": outcome,
        "data_used": data_used(outcomes),
        "rules_checked": merge_rules([*suitability], extra_rules),
        "confidence": confidence(list(bases), verified=verified),
        "blocks_emitted": [{"id": b["id"], "type": b["type"]} for b in list(blocks)[:40]],
        "token_usage": token_usage(usage_by_model, model_calls),
        "step_timings": step_timings(steps),
        "duration_ms": max(int(duration_ms), 0),
    }
    if intent:
        rec["intent"] = intent
    if code:
        rec["code"] = code
    return rec
