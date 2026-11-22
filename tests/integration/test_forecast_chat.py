"""Chat dự báo qua AgentCore Runtime THẬT (router -> tool `forecast___get_forecast` qua Gateway -> khối `forecast_timeline`).

Tiêu chí 8 của phase 2: "hũ ăn uống còn trụ được bao lâu" trả khối `forecast_timeline` CÙNG SỐ với màn Chi tiết hũ
(`GET /forecasts/an_uong`). Mỗi lượt tốn 2 lượt gọi model (router và viết câu); giãn nhịp giữa các lượt.
"""

from __future__ import annotations

import re
import time

import pytest
from agentcore_helpers import invoke_agent, new_session_id

pytestmark = pytest.mark.usefixtures("fresh")

PACE_SECONDS = 4


@pytest.fixture(autouse=True)
def pace():
    yield
    time.sleep(PACE_SECONDS)


def ask(agent_url, tokens, who, text, **kw):
    run = invoke_agent(agent_url, tokens[who], text, **kw)
    assert run.status == 200, (run.status, run.raw)
    assert "RUN_STARTED" in run.types and run.finished is not None, run.types
    assert "RUN_ERROR" not in run.types, [e for e in run.events if e["type"] == "RUN_ERROR"]
    return run


def test_chat_hu_an_uong_con_tru_duoc_bao_lau_tra_khoi_timeline_cung_so_voi_rest(
    agent_url, tokens, api, schema_validator
):
    sid = new_session_id()
    run = ask(agent_url, tokens, "minh", "hũ ăn uống còn trụ được bao lâu", session_id=sid)
    assert run.finished["result"]["intent"] == "lookup"
    assert run.finished["result"]["degraded"] is False
    [block] = run.blocks_of("forecast_timeline")
    schema_validator("https://contracts.yofina.invalid/blocks/forecast_timeline.schema.json", block)
    status, rest = api("minh", "GET", "/forecasts/an_uong")
    assert status == 200, rest
    assert block["data"] == rest["data"], "chat và màn Chi tiết hũ phải cùng số"
    assert block["data"]["runout_date"] == "2026-11-23" and block["data"]["status"] == "short"
    assert block["fallback_text"] == rest["fallback_text"]
    # câu trả lời do model viết ở lượt này, và mọi số nó nhắc phải có trong kết quả tool
    assert run.text.strip(), "phải có câu trả lời bằng chữ do agent sinh"
    assert "23/11" in run.text or "23" in run.text
    tools = [e["toolCallName"] for e in run.events if e["type"] == "TOOL_CALL_START"]
    assert tools == ["ledger___get_jar_balances", "forecast___get_forecast"]
    amounts = {
        block["data"]["start_balance_vnd"],
        *[e["amount_vnd"] for e in block["data"]["events"]],
    }
    for m in re.findall(r"\d{1,3}(?:\.\d{3})+", run.text):
        assert int(m.replace(".", "")) in amounts | {
            abs(d["p50_vnd"]) for d in block["data"]["days"]
        }, m
    # khối được lưu cùng lượt và phát lại khi tải lại trang
    status, conv = api("minh", "GET", f"/conversations/{sid}")
    assert status == 200 and conv["turns"][0]["blocks"] == run.blocks


def test_chat_hu_khong_co_thi_hoi_lai_khong_goi_tool_forecast(agent_url, tokens):
    run = ask(agent_url, tokens, "minh", "quỹ nhà còn trụ được bao lâu")
    tools = [e["toolCallName"] for e in run.events if e["type"] == "TOOL_CALL_START"]
    assert "forecast___get_forecast" not in tools
    assert run.text.strip()


def test_chat_tai_khoan_khoa_ra_uoc_luong_ban_dau(agent_url, tokens, api):
    run = ask(agent_url, tokens, "khoa", "khi nào hũ ăn uống cạn")
    [block] = run.blocks_of("forecast_timeline")
    d = block["data"]
    assert (
        d["is_initial_estimate"] is True
        and d["confidence_band"] == "low"
        and "p_shortfall" not in d
    )
    assert api("khoa", "GET", "/forecasts/an_uong")[1]["data"] == d
