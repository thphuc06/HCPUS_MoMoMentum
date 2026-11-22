"""Agent thật trên AgentCore Runtime (HTTP + SSE AG-UI, access token Cognito thật, Gateway thật, Bedrock thật).

Giãn nhịp giữa các lượt để không chạm quota model (router và model viết câu dùng Nova 2 Lite, nhưng vẫn
chừa khoảng nghỉ). Tổng số lượt gọi model của file này khoảng 15 (mỗi lượt 2 lượt gọi: router và viết câu).
Chạy: `uv run pytest tests/integration/test_agent_runtime.py -m integration`.
"""

from __future__ import annotations

import time

import pytest
from _yofina import session as make_session
from agentcore_helpers import invoke_agent, new_session_id

PACE_SECONDS = 4
MOVE = {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100_000}

pytestmark = pytest.mark.usefixtures("fresh")


@pytest.fixture(autouse=True)
def pace():
    yield
    time.sleep(PACE_SECONDS)


def balances(api, who):
    _, body = api(who, "GET", "/jars")
    return {j["code"]: j["balance_vnd"] for j in body["jars"]}


def ask(agent_url, tokens, who, text, **kw):
    run = invoke_agent(agent_url, tokens[who], text, **kw)
    assert run.status == 200, (run.status, run.raw)
    assert "RUN_STARTED" in run.types and run.finished is not None, run.types
    assert "RUN_ERROR" not in run.types, [e for e in run.events if e["type"] == "RUN_ERROR"]
    return run


def conversation(api, who, sid):
    status, body = api(who, "GET", f"/conversations/{sid}")
    assert status == 200, body
    return body


def test_so_du_cac_hu_khop_rest_va_duoc_luu(agent_url, tokens, api, schema_validator):
    sid = new_session_id()
    run = ask(agent_url, tokens, "minh", "số dư các hũ của mình", session_id=sid)
    [jar_block] = run.blocks_of("jar_summary")
    jars = jar_block["data"]["jars"]
    assert len(jars) == 7
    assert {j["code"]: j["balance_vnd"] for j in jars} == balances(api, "minh")
    assert run.text.strip(), "phải có câu trả lời bằng chữ do agent sinh"
    assert run.finished["result"]["intent"] == "lookup"
    assert run.finished["result"]["degraded"] is False
    # khối khớp hợp đồng JSON Schema
    schema_validator("https://contracts.yofina.invalid/blocks/jar_summary.schema.json", jar_block)

    saved = conversation(api, "minh", sid)
    assert len(saved["turns"]) == 1
    turn = saved["turns"][0]
    assert turn["trace_id"] == run.trace_id
    assert turn["user_text"] == "số dư các hũ của mình"
    assert turn["assistant_text"] == run.text
    assert turn["blocks"] == run.blocks  # đúng khối đã phát, đúng thứ tự
    listing = api("minh", "GET", "/conversations")[1]["conversations"]
    assert sid in [c["conversation_id"] for c in listing]


def test_chuyen_hu_hien_confirm_roi_xac_nhan_bang_rest(agent_url, tokens, api, schema_validator):
    before = balances(api, "minh")
    sid = new_session_id()
    run = ask(
        agent_url, tokens, "minh", "chuyển 100 nghìn từ Giải trí sang Ăn uống", session_id=sid
    )
    [confirm] = run.blocks_of("confirm")
    assert confirm["data"]["tool"] == "move_between_jars"
    assert confirm["data"]["params"] == MOVE
    assert balances(api, "minh") == before, "chưa bấm xác nhận thì không được ghi"
    saved = conversation(api, "minh", sid)["turns"][0]
    assert [b["type"] for b in saved["blocks"]] == [b["type"] for b in run.blocks]

    # người dùng bấm nút: đúng tool và params của khối
    status, conf = api(
        "minh",
        "POST",
        "/confirmations",
        {
            "tool": confirm["data"]["tool"],
            "params": confirm["data"]["params"],
            "params_hash": confirm["data"]["params_hash"],
        },
    )
    assert status == 200, conf
    status, receipt = api(
        "minh",
        "POST",
        "/actions",
        {
            "tool": confirm["data"]["tool"],
            "params": confirm["data"]["params"],
            "confirm_token": conf["confirm_token"],
        },
    )
    assert status == 200, receipt
    assert receipt["type"] == "receipt"
    schema_validator("https://contracts.yofina.invalid/blocks/receipt.schema.json", receipt)
    after = balances(api, "minh")
    assert after["giai_tri"] == before["giai_tri"] - 100_000
    assert after["an_uong"] == before["an_uong"] + 100_000


def test_ngoai_pham_vi_ra_notice(agent_url, tokens, api):
    sid = new_session_id()
    run = ask(agent_url, tokens, "minh", "nên mua cổ phiếu nào", session_id=sid)
    [notice] = run.blocks_of("notice")
    assert notice["data"]["kind"] == "out_of_scope"
    assert run.finished["result"]["intent"] == "out_of_scope"
    saved = conversation(api, "minh", sid)["turns"][0]
    assert saved["blocks"] == run.blocks and saved["assistant_text"] == run.text


def test_lan_khong_doc_duoc_hoi_thoai_cua_minh_qua_rest_va_runtime(agent_url, tokens, api):
    sid = new_session_id()
    ask(agent_url, tokens, "minh", "xin chào", session_id=sid)
    assert len(conversation(api, "minh", sid)["turns"]) == 1
    assert conversation(api, "lan", sid)["turns"] == []
    assert sid not in [
        c["conversation_id"] for c in api("lan", "GET", "/conversations")[1]["conversations"]
    ]
    # Runtime V2 ghim session theo người dùng: lan không dùng được session của minh
    run = invoke_agent(agent_url, tokens["lan"], "số dư", session_id=sid)
    assert run.status == 403, (run.status, run.raw)


def test_id_token_va_khong_token_bi_tu_choi_o_runtime(agent_url, tokens):
    assert invoke_agent(agent_url, None, "xin chào").status == 401
    assert invoke_agent(agent_url, "abc.def.ghi", "xin chào").status in (401, 403)


def test_tran_luot_goi_model_bang_0_van_co_khoi_so_lieu_va_notice(agent_url, tokens, api):
    """Đặt trần Nova và Sonnet về 0 qua SSM `/yofina/llm/daily_cap_*`, phiên mới đọc cấu hình mới,
    rồi KHÔI PHỤC. Agent phải trả khối jar_summary (tool thật) + notice degraded, không gọi model."""
    ssm = make_session().client("ssm")
    names = ["/yofina/llm/daily_cap_small", "/yofina/llm/daily_cap_planner"]
    old: dict[str, str | None] = {}
    for n in names:
        try:
            old[n] = ssm.get_parameter(Name=n)["Parameter"]["Value"]
        except ssm.exceptions.ParameterNotFound:
            old[n] = None
    try:
        for n in names:
            ssm.put_parameter(Name=n, Value="0", Type="String", Overwrite=True)
        sid = new_session_id()  # microVM mới: đọc SSM lúc dùng lần đầu
        run = ask(agent_url, tokens, "minh", "số dư các hũ của mình", session_id=sid)
        finished = run.finished["result"]
        assert finished["model_calls"] == 0 and finished["degraded"] is True
        [jar_block] = run.blocks_of("jar_summary")
        assert {j["code"]: j["balance_vnd"] for j in jar_block["data"]["jars"]} == balances(
            api, "minh"
        )
        notices = run.blocks_of("notice")
        assert notices and notices[0]["data"]["kind"] == "degraded"
        assert notices[0]["data"]["code"] == "MODEL_BUDGET_EXCEEDED"
        # lượt suy giảm cũng được lưu
        saved = conversation(api, "minh", sid)["turns"][0]
        assert [b["type"] for b in saved["blocks"]] == ["jar_summary", "notice"]
    finally:
        for n, v in old.items():
            if v is None:
                ssm.delete_parameter(Name=n)
            else:
                ssm.put_parameter(Name=n, Value=v, Type="String", Overwrite=True)
