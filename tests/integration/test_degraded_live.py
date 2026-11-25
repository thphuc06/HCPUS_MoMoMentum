"""Tiêu chí 8 phase 3: model không dùng được thì what-if và kiểm tra trước khi quẹt VẪN trả thẻ số liệu tất định (agent thật trên Runtime).

Hai kiểu ép lỗi, mỗi kiểu chạy ba câu (what-if từ hũ, what-if Trả sau, kiểm tra trước khi chi), mỗi câu một phiên MỚI
(microVM mới đọc cấu hình model từ SSM lúc dùng lần đầu):

- `tran_bang_0`: SSM `/yofina/llm/daily_cap_small` và `daily_cap_planner` về 0 -> `ModelBudgetExceeded` ở lời gọi model đầu tiên (router).
- `model_id_sai`: SSM `/yofina/llm/roles` thay vai `small` và `planner` bằng MỘT model id không tồn tại -> Bedrock từ chối mọi lời gọi.

Đường đi mong đợi: router lỗi -> `fallback.classify_by_rules` (luật dự phòng) -> what-if dựng spec bằng mã (`whatif.deterministic_spec`),
chạy `run_scenario` thật, phát `forecast_timeline`; kiểm tra trước khi chi gọi `affordability_check`, phát `affordability_card`.
Không có model nào viết chữ, và có `notice` kind `degraded`. Cấu hình SSM được KHÔI PHỤC trong `finally` của fixture (mỗi kiểu một lần).

CẢNH BÁO: đổi SSM `/yofina/llm/*` là đổi toàn hệ thống trong lúc test chạy (mọi phiên Runtime mới, kể cả của người khác, đọc cấu hình
mới); đừng chạy song song với phép đo độ trễ hay gọi Bedrock khác.
Chạy: `uv run pytest tests/integration/test_degraded_live.py -m integration`.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
from _yofina import session as make_session
from agentcore_helpers import invoke_agent, new_session_id

PACE_SECONDS = 4
BAD_MODEL_ID = (
    "global.anthropic.claude-yofina-khong-ton-tai-v0"  # id không tồn tại: Bedrock từ chối
)

WHAT_IF_JAR_Q = "Nếu mua tai nghe 500 nghìn từ hũ Giải trí thì sao"
WHAT_IF_CREDIT_Q = "Nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao"
# ví demo (issue #39) không có hũ Hóa đơn: hóa đơn và tiền nhà nằm trong hũ Nghĩa vụ
AFFORD_Q = "Chuyển 250 nghìn từ hũ Nghĩa vụ cho người nhận demo có ổn không"

pytestmark = pytest.mark.usefixtures("fresh")

#: tên tham số SSM -> giá trị ép lỗi, theo kiểu
OVERRIDES: dict[str, dict[str, str]] = {
    "tran_bang_0": {
        "/yofina/llm/daily_cap_small": "0",
        "/yofina/llm/daily_cap_planner": "0",
    },
    "model_id_sai": {
        "/yofina/llm/roles": json.dumps(
            {
                role: {"daily_cap": 400, "models": [{"id": BAD_MODEL_ID, "rpm": 8}]}
                for role in ("small", "planner")
            }
        ),
    },
}
#: mã `notice` degraded chấp nhận được cho từng kiểu
DEGRADED_CODES = {
    "tran_bang_0": {"MODEL_BUDGET_EXCEEDED"},
    # Bedrock từ chối id sai bằng lỗi nào còn tùy: hết chuỗi model (RATE_LIMITED), lỗi không thuộc chuỗi dự phòng (INTERNAL_ERROR)
    "model_id_sai": {"RATE_LIMITED", "INTERNAL_ERROR", "MODEL_BUDGET_EXCEEDED"},
}


@pytest.fixture(autouse=True)
def pace():
    yield
    time.sleep(PACE_SECONDS)


@pytest.fixture(scope="module", params=list(OVERRIDES))
def degraded(request):
    """Đặt cấu hình ép lỗi cho cả nhóm test của một kiểu, rồi KHÔI PHỤC đúng giá trị và kiểu cũ (hoặc xóa nếu trước đó chưa có)."""
    mode: str = request.param
    ssm = make_session().client("ssm")
    old: dict[str, tuple[str, str] | None] = {}
    try:
        for name in OVERRIDES[mode]:
            try:
                p = ssm.get_parameter(Name=name)["Parameter"]
                old[name] = (p["Value"], p["Type"])
            except ssm.exceptions.ParameterNotFound:
                old[name] = None
        for name, value in OVERRIDES[mode].items():
            ssm.put_parameter(Name=name, Value=value, Type="String", Overwrite=True)
        yield mode
    finally:
        for name, prev in old.items():
            try:
                if prev is None:
                    ssm.delete_parameter(Name=name)
                else:
                    ssm.put_parameter(Name=name, Value=prev[0], Type=prev[1], Overwrite=True)
            except ssm.exceptions.ParameterNotFound:
                pass


def ask(agent_url: str, tokens: dict[str, str], who: str, text: str):
    run = invoke_agent(agent_url, tokens[who], text, session_id=new_session_id(), timeout=150)
    assert run.status == 200, (run.status, run.raw[:500])
    assert "RUN_STARTED" in run.types and run.finished is not None, run.types
    assert "RUN_ERROR" not in run.types, [e for e in run.events if e["type"] == "RUN_ERROR"]
    return run


def tool_args(run, short: str) -> list[dict[str, Any]]:
    """Tham số của các lời gọi tool `<đích>___<short>` đã phát trong luồng AG-UI."""
    names = {
        e["toolCallId"]: e.get("toolCallName", "")
        for e in run.events
        if e.get("type") == "TOOL_CALL_START"
    }
    out: dict[str, str] = {}
    for e in run.events:
        if e.get("type") == "TOOL_CALL_ARGS" and names.get(e["toolCallId"], "").endswith(
            f"___{short}"
        ):
            out[e["toolCallId"]] = out.get(e["toolCallId"], "") + e.get("delta", "")
    return [json.loads(v) for v in out.values()]


def assert_degraded_without_model_text(run, mode: str) -> None:
    result = run.finished["result"]
    assert result["degraded"] is True
    if mode == "tran_bang_0":
        assert result["model_calls"] == 0
    assert not run.text.strip(), f"không có câu do model viết khi model hỏng: {run.text!r}"
    notices = [b["data"] for b in run.blocks_of("notice")]
    degraded = [n for n in notices if n["kind"] == "degraded" and n.get("code")]
    assert degraded, notices
    assert {n["code"] for n in degraded} & DEGRADED_CODES[mode], [n["code"] for n in degraded]
    # số liệu đã ra thì không được kèm lỗi cứng hay câu hỏi lại
    assert not [n for n in notices if n["kind"] == "error"], notices
    assert not run.blocks_of("clarify"), run.blocks_of("clarify")


def test_what_if_tu_hu_van_co_khoi_so_lieu(agent_url, tokens, degraded, schema_validator):
    run = ask(agent_url, tokens, "minh", WHAT_IF_JAR_Q)
    assert run.finished["result"]["intent"] == "what_if"
    assert_degraded_without_model_text(run, degraded)
    timelines = run.blocks_of("forecast_timeline")
    assert timelines, run.types
    for tl in timelines:
        schema_validator(
            "https://contracts.yofina.invalid/blocks/forecast_timeline.schema.json", tl
        )
    (args,) = tool_args(run, "run_scenario")
    # spec do mã dựng từ chính câu hỏi: món mua một lần, đúng số tiền, đúng hũ, trả bằng tiền hũ
    assert args["scenario"]["kind"] == "one_time_purchase", args
    assert (args["scenario"]["amount_vnd"], args["scenario"]["jar_code"]) == (
        500_000,
        "giai_tri",
    ), args
    assert args["scenario"]["funding_source"] == "jar", args


def test_what_if_tra_sau_van_co_khoi_so_lieu(agent_url, tokens, degraded, schema_validator):
    run = ask(agent_url, tokens, "minh", WHAT_IF_CREDIT_Q)
    assert run.finished["result"]["intent"] == "what_if"
    assert_degraded_without_model_text(run, degraded)
    timelines = run.blocks_of("forecast_timeline")
    assert timelines, run.types
    for block in timelines + run.blocks_of("obligation_impact"):
        schema_validator(
            f"https://contracts.yofina.invalid/blocks/{block['type']}.schema.json", block
        )
    (args,) = tool_args(run, "run_scenario")
    assert args["scenario"]["kind"] == "bnpl_purchase", args
    assert (args["scenario"]["amount_vnd"], args["scenario"]["funding_source"]) == (
        1_200_000,
        "credit",
    ), args


def test_kiem_tra_truoc_khi_chi_van_co_the_affordability(
    agent_url, tokens, degraded, schema_validator
):
    run = ask(agent_url, tokens, "minh", AFFORD_Q)
    assert run.finished["result"]["intent"] == "affordability"
    assert_degraded_without_model_text(run, degraded)
    [card] = run.blocks_of("affordability_card")
    schema_validator("https://contracts.yofina.invalid/blocks/affordability_card.schema.json", card)
    data = card["data"]
    assert (data["amount_vnd"], data["funding_source"], data["selected_jar_code"]) == (
        250_000,
        "jar",
        "nghia_vu",
    )
    assert data["verdict"] in ("ok", "tight", "short")
    (args,) = tool_args(run, "affordability_check")
    assert (args["amount_vnd"], args["jar"]) == (250_000, "nghia_vu"), args
