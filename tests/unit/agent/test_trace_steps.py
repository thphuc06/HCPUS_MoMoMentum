"""Bản ghi lượt ghi MỖI lần gọi tool thành một bước `<target>___<tool>` (màn trace `/ops/traces/{id}` và tỷ lệ lỗi tool của `/ops/summary`).

Lượt what-if giả lập (model, tool giả của `agent_helpers`); bản ghi được kiểm bằng chính `record_turn` (`yofina_audit.record`) và
`TraceDetail` của hợp đồng, nên thứ agent ghi chắc chắn được Lambda nhận và màn trace đọc lại được.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from agent_helpers import FakeRecords, FakeTools, make_llm, route_response, run_turn, tool_response
from conftest import BASE
from jsonschema import Draft202012Validator
from test_whatif import WHAT_IF_Q, analysis, call_names, what_if_llm
from yofina_agent import trace
from yofina_agent.tools import ToolKind, ToolOutcome

from yofina_audit.ops_view import tool_calls_of
from yofina_audit.record import parse_turn_record

TARGET = {
    "get_jar_balances": "ledger",
    "get_obligations": "ledger",
    "move_between_jars": "ledger",
    "list_scenarios": "forecast",
    "run_scenario": "forecast",
    "get_forecast": "forecast",
    "get_fee_schedule": "knowledge",
    "check_suitability": "planner",
}


def tool_steps(rec: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for s in rec["step_timings"] if "___" in s["step"]]


def expected_names(tools: FakeTools) -> list[str]:
    return [f"{TARGET[n]}___{n}" for n in call_names(tools)]


@pytest.fixture
def trace_detail_ok(registry):
    v = Draft202012Validator({"$ref": f"{BASE}/tools/audit.results.schema.json#/$defs/TraceDetail"}, registry=registry)

    def check(rec: dict[str, Any]) -> None:
        detail = {k: rec[k] for k in ("intent", "outcome", "blocks_emitted", "token_usage", "step_timings", "duration_ms") if k in rec}
        errors = [f"{list(e.path)}: {e.message}" for e in v.iter_errors(detail)]
        assert not errors, errors
        parse_turn_record(rec)  # Lambda audit nhận nguyên bản ghi (bước sai làm hỏng CẢ bản ghi)

    return check


class SlowTools(FakeTools):
    """Tool giả có độ trễ theo lần gọi: lần gọi bắt đầu trước có thể xong sau (kiểm lượt gọi song song)."""

    def __init__(self, delays: dict[str, list[float]], results: dict[str, Any] | None = None) -> None:
        super().__init__(results)
        self.delays = {k: list(v) for k, v in delays.items()}

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        short = name.split("___", 1)[-1]
        queue = self.delays.get(short)
        delay = queue.pop(0) if queue else 0.0
        self.calls.append((short, dict(arguments)))
        await asyncio.sleep(delay)
        res = self.results[short]
        outcome = res(arguments) if callable(res) else res
        outcome.name, outcome.args = name, dict(arguments)
        return outcome

    async def aclose(self) -> None:
        self.closed = True


# --- lượt what-if ------------------------------------------------------------------------------------------------------
def test_what_if_moi_lan_goi_tool_la_mot_buoc_theo_thu_tu(monkeypatch, trace_detail_ok):
    records = FakeRecords()
    events, tools, _ = run_turn(
        WHAT_IF_Q, llm=what_if_llm(tool_response("analyze", analysis())), monkeypatch=monkeypatch, records=records
    )
    (rec,) = records.saved
    trace_detail_ok(rec)
    steps = tool_steps(rec)
    # đúng một bước cho mỗi lần gọi, đúng thứ tự gọi, tên đầy đủ theo target của Gateway
    assert [s["step"] for s in steps] == expected_names(tools)
    assert [s["step"] for s in steps].count("planner___check_suitability") == 2  # hai lần cùng tool: hai bước, không cộng dồn
    assert all(s["status"] == "ok" and "code" not in s and s["ms"] >= 0 for s in steps)
    assert events[-1].result["tool_calls"] == len(steps)
    # bước lớn vẫn còn (bảng "Vì sao"), và giữ chỗ lúc bắt đầu: lần gọi tool của kế hoạch đứng sau bước `tools`
    names = [s["step"] for s in rec["step_timings"]]
    assert {"router", "orchestrator", "tools", "analyst", "verifier", "composer"} <= set(names)
    assert names.index("tools") < names.index("forecast___run_scenario") < names.index("analyst")
    assert [s for s in rec["step_timings"] if "___" not in s["step"] and "status" in s] == []
    # màn trace đọc ra cùng danh sách
    calls = tool_calls_of(rec["step_timings"])
    assert [f"{c['target']}___{c['tool']}" for c in calls] == expected_names(tools)


def test_tool_loi_ghi_status_va_code(monkeypatch, trace_detail_ok):
    denied = lambda a: ToolOutcome("x", ToolKind.DENIED, code="FORBIDDEN", message="Không có quyền.")  # noqa: E731
    down = lambda a: ToolOutcome("x", ToolKind.UNAVAILABLE, code="DATABASE_UNAVAILABLE", message="tạm thời")  # noqa: E731
    records = FakeRecords()
    _, tools, _ = run_turn(
        WHAT_IF_Q,
        llm=what_if_llm(tool_response("analyze", analysis())),
        tools=FakeTools({"get_fee_schedule": denied, "get_obligations": down}),
        monkeypatch=monkeypatch,
        records=records,
    )
    (rec,) = records.saved
    trace_detail_ok(rec)
    steps = tool_steps(rec)
    assert [s["step"] for s in steps] == expected_names(tools)
    by = {}
    for s in steps:
        by.setdefault(s["step"], []).append(s)
    # Cedar từ chối: denied, không thử lại
    assert [(s["status"], s["code"]) for s in by["knowledge___get_fee_schedule"]] == [("denied", "FORBIDDEN")]
    # không kết nối được: `error` (TraceStep không có `unavailable`), thử lại một lần nên hai bước
    assert [(s["status"], s["code"]) for s in by["ledger___get_obligations"]] == [("error", "DATABASE_UNAVAILABLE")] * 2
    assert all(s["status"] == "ok" and "code" not in s for s in by["forecast___run_scenario"])
    calls = tool_calls_of(rec["step_timings"])
    assert sum(c["status"] != "ok" for c in calls) == 3
    assert {c.get("code") for c in calls if c["status"] != "ok"} == {"FORBIDDEN", "DATABASE_UNAVAILABLE"}


def test_luot_goi_song_song_ghi_du_tung_buoc_theo_thu_tu_bat_dau(monkeypatch, trace_detail_ok):
    # lần check_suitability đầu chậm hơn lần sau: xong sau nhưng vẫn đứng trước; get_obligations (song song với biểu phí) cũng chậm
    records = FakeRecords()
    _, tools, _ = run_turn(
        WHAT_IF_Q,
        llm=what_if_llm(tool_response("analyze", analysis())),
        tools=SlowTools({"check_suitability": [0.12, 0.0], "get_obligations": [0.08]}),
        monkeypatch=monkeypatch,
        records=records,
    )
    (rec,) = records.saved
    trace_detail_ok(rec)
    steps = tool_steps(rec)
    assert [s["step"] for s in steps] == expected_names(tools)
    suit = [s for s in steps if s["step"] == "planner___check_suitability"]
    assert len(suit) == 2 and suit[0]["ms"] >= 100 > suit[1]["ms"]
    oblig = next(s for s in steps if s["step"] == "ledger___get_obligations")
    fee = next(s for s in steps if s["step"] == "knowledge___get_fee_schedule")
    assert oblig["ms"] >= 70 > fee["ms"]


def test_buoc_khong_lo_tham_so_hay_ket_qua(monkeypatch):
    records = FakeRecords()
    _, tools, _ = run_turn(
        WHAT_IF_Q, llm=what_if_llm(tool_response("analyze", analysis())), monkeypatch=monkeypatch, records=records
    )
    (rec,) = records.saved
    assert all(set(s) <= {"step", "ms", "status", "code"} for s in rec["step_timings"])
    text = json.dumps(rec["step_timings"], ensure_ascii=False)
    assert tools.calls and any(args for _, args in tools.calls)  # các lần gọi có tham số thật
    for secret in ("1200000", "1.200.000", "1150000", "tai nghe", "giai_tri", "nghia_vu", "session-1", "user-a", "proposal"):
        assert secret not in text


def test_tool_nem_loi_giua_chung_van_co_buoc_error(monkeypatch, trace_detail_ok):
    def boom(args):
        raise RuntimeError("socket closed")

    records = FakeRecords()
    run_turn(
        "Hũ của mình còn bao nhiêu",
        llm=make_llm([route_response(intent="balance_lookup")]),
        tools=FakeTools({"get_jar_balances": boom}),
        monkeypatch=monkeypatch,
        records=records,
    )
    (rec,) = records.saved
    trace_detail_ok(rec)
    assert tool_steps(rec) == [{"step": "ledger___get_jar_balances", "ms": tool_steps(rec)[0]["ms"], "status": "error", "code": "INTERNAL_ERROR"}]


# --- hàm thuần --------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("kind", "code", "expected"),
    [
        (ToolKind.OK, None, ("ok", None)),
        (ToolKind.NEEDS_CONFIRMATION, None, ("ok", None)),
        (ToolKind.TOOL_ERROR, "INSUFFICIENT_FUNDS", ("error", "INSUFFICIENT_FUNDS")),
        (ToolKind.DENIED, "FORBIDDEN", ("denied", "FORBIDDEN")),
        (ToolKind.UNAVAILABLE, "RATE_LIMITED", ("error", "RATE_LIMITED")),
        (ToolKind.BAD_RESULT, None, ("error", "INTERNAL_ERROR")),
        (ToolKind.TOOL_ERROR, "sai dạng", ("error", "INTERNAL_ERROR")),
    ],
)
def test_trang_thai_theo_tool_kind(kind, code, expected):
    assert trace.tool_status(ToolOutcome("ledger___x", kind, code=code)) == expected


def test_buoc_khong_phai_tool_van_cong_don_buoc_tool_thi_khong():
    steps = [
        trace.TurnStep("router", 5),
        trace.TurnStep("ledger___get_jar_balances", 7, "ok"),
        trace.TurnStep("guardrail_out", 3),
        trace.TurnStep("ledger___get_jar_balances", 9, "error", "DATABASE_UNAVAILABLE"),
        trace.TurnStep("guardrail_out", 4),
        ("router", 1),  # dạng cũ (tên, ms) vẫn nhận
        trace.TurnStep("Sai-Ten", 1),  # sai mẫu tên: bỏ, không làm hỏng cả bản ghi
    ]
    assert trace.step_timings(steps) == [
        {"step": "router", "ms": 6},
        {"step": "ledger___get_jar_balances", "ms": 7, "status": "ok"},
        {"step": "guardrail_out", "ms": 7},
        {"step": "ledger___get_jar_balances", "ms": 9, "status": "error", "code": "DATABASE_UNAVAILABLE"},
    ]


def test_lo_trinh_nhieu_tool_van_trong_gioi_han_hop_dong(trace_detail_ok):
    # lộ trình: 5 chặng, ~40 lần gọi (check_suitability lặp nhiều nhất), có lỗi ở giữa
    steps: list[trace.TurnStep] = [trace.TurnStep("guardrail_in", 300), trace.TurnStep("router", 900)]
    steps += [trace.TurnStep("roadmap_context", 1), trace.TurnStep("ledger___get_jar_balances", 50, "ok"),
              trace.TurnStep("planner___get_roadmap", 40, "ok"), trace.TurnStep("roadmap_draft", 9000),
              trace.TurnStep("roadmap_allocate", 1), trace.TurnStep("forecast___optimize_allocation", 300, "ok"),
              trace.TurnStep("roadmap_suitability", 1)]  # fmt: skip
    for i in range(34):
        failed = i == 30
        steps.append(trace.TurnStep("planner___check_suitability", 20 + i, "error" if failed else "ok", "RATE_LIMITED" if failed else None))
    steps += [trace.TurnStep("roadmap_save", 1), trace.TurnStep("planner___save_roadmap", 80, "ok"), trace.TurnStep("guardrail_out", 200)]
    out = trace.step_timings(steps)
    assert len(out) == trace.MAX_STEPS
    names = [s["step"] for s in out]
    # mọi bước lớn, mọi tool khác và lần lỗi còn; chỉ bỏ lần check_suitability `ok` lặp lại (lần sau cùng trước)
    assert [n for n in names if "___" not in n] == [s.step for s in steps if "___" not in s.step]
    assert {"ledger___get_jar_balances", "planner___get_roadmap", "forecast___optimize_allocation", "planner___save_roadmap"} <= set(names)
    assert any(s.get("code") == "RATE_LIMITED" for s in out)
    kept_ms = [s["ms"] for s in out if s["step"] == "planner___check_suitability"]
    assert kept_ms == sorted(kept_ms) and kept_ms[0] == 20  # thứ tự giữ nguyên, lần đầu còn
    rec = trace.build_record(
        trace_id="t-roadmap", conversation_id="c", intent="roadmap", outcome="ok", code=None, outcomes=[], suitability=[],
        extra_rules=[], bases=[], blocks=[], usage_by_model=[], model_calls=2, steps=steps, duration_ms=12000,
    )  # fmt: skip
    trace_detail_ok(rec)
