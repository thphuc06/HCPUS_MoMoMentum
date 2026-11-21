import json

from agent_helpers import (
    FakeTools,
    FakeUsage,
    FakeWriter,
    agent_settings,
    make_jwt,
    make_llm,
    route_response,
)
from fastapi.testclient import TestClient
from yofina_agent.app import AgentRuntime, create_app
from yofina_agent.identity import Identity
from yofina_agent.store import UnconfiguredTurnBlockStore

BODY = {
    "threadId": "thread-9",
    "runId": "run-9",
    "state": {},
    "messages": [{"id": "m1", "role": "user", "content": "số dư các hũ"}],
    "tools": [],
    "context": [],
    "forwardedProps": {},
}


def sse_events(resp) -> list[dict]:
    out = []
    for block in resp.text.split("\n\n"):
        if block.startswith("data: "):
            out.append(json.loads(block[6:]))
    return out


def make_client(monkeypatch, llm=None, tools=None, store=None, writer=None):
    monkeypatch.setattr("yofina_agent.turn.write_stream", writer or FakeWriter("Xong."))
    seen: list[Identity] = []
    tools = tools or FakeTools()

    def factory(identity):
        seen.append(identity)
        return tools

    llm = llm or make_llm([route_response(intent="balance_lookup")])
    rt = AgentRuntime(
        agent_settings(),
        llm=lambda: llm[0],
        store=store or UnconfiguredTurnBlockStore(),
        tools_factory=factory,
    )
    return TestClient(create_app(rt)), seen, tools


def auth(sub="user-a"):
    return {"Authorization": f"Bearer {make_jwt(sub)}"}


def test_ping_healthy_viet_hoa(monkeypatch):
    client, _, _ = make_client(monkeypatch)
    r = client.get("/ping")
    assert r.status_code == 200 and r.json()["status"] == "Healthy"


def test_thieu_hoac_sai_authorization_thi_401_co_ma_loi(monkeypatch):
    client, seen, _ = make_client(monkeypatch)
    for headers in ({}, {"Authorization": "Bearer abc"}, {"Authorization": "Basic xxx"}):
        r = client.post("/invocations", json=BODY, headers=headers)
        assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHENTICATED"
    assert seen == []  # không tạo lượt, không gọi gì


def test_payload_hong_thi_422(monkeypatch):
    client, _, _ = make_client(monkeypatch)
    r = client.post("/invocations", json={"messages": "không phải danh sách"}, headers=auth())
    assert r.status_code == 422 and r.json()["error"]["code"] == "PARAMS_INVALID"


def test_luong_sse_hop_le_va_khong_rong(monkeypatch):
    client, _, _ = make_client(monkeypatch)
    r = client.post("/invocations", json=BODY, headers=auth())
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-cache"
    ev = sse_events(r)
    assert (
        ev[0]["type"] == "RUN_STARTED"
        and ev[0]["threadId"] == "thread-9"
        and ev[0]["runId"] == "run-9"
    )
    assert ev[-1]["type"] == "RUN_FINISHED" and ev[-1]["result"]["intent"] == "balance_lookup"
    snap = next(e for e in ev if e["type"] == "ACTIVITY_SNAPSHOT")
    assert snap["activityType"] == "yofina.block" and snap["messageId"] == snap["content"]["id"]
    assert snap["replace"] is True


def test_sub_lay_tu_jwt_va_bo_qua_user_id_trong_payload(monkeypatch):
    client, seen, tools = make_client(monkeypatch)
    body = {
        **BODY,
        "forwardedProps": {"user_id": "evil", "userId": "evil"},
        "state": {"user_id": "evil", "sub": "evil"},
    }
    client.post("/invocations", json=body, headers=auth("real-user"))
    assert [i.sub for i in seen] == ["real-user"]
    assert all("evil" not in json.dumps(args) for _, args in tools.calls)
    assert all("user_id" not in args for _, args in tools.calls)


def test_token_nguyen_ven_di_vao_identity_de_chuyen_cho_gateway(monkeypatch):
    client, seen, _ = make_client(monkeypatch)
    token = make_jwt("u-1", client_id="web", token_use="access")
    client.post("/invocations", json=BODY, headers={"Authorization": f"Bearer {token}"})
    assert seen[0].token == token and seen[0].authorization == f"Bearer {token}"


class SpyStore:
    def __init__(self):
        self.saved = {}

    async def save(self, *, tools, conversation_id, trace_id, blocks, **kw):
        self.saved.update(conversation_id=conversation_id, trace_id=trace_id)
        return True


def test_trace_id_tu_traceparent_va_conversation_id_tu_session_header(monkeypatch):
    spy = SpyStore()
    client, _, _ = make_client(monkeypatch, store=spy)
    tid = "4bf92f3577b34da6a3ce929d0e0e4736"
    headers = {
        **auth(),
        "traceparent": f"00-{tid}-00f067aa0ba902b7-01",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": "s" * 40,
    }
    ev = sse_events(client.post("/invocations", json=BODY, headers=headers))
    assert spy.saved == {"conversation_id": "s" * 40, "trace_id": tid}
    assert ev[-1]["result"]["trace_id"] == tid


def test_khong_co_traceparent_thi_server_sinh_trace_id_va_dung_thread_id(monkeypatch):
    spy = SpyStore()
    client, _, _ = make_client(monkeypatch, store=spy)
    client.post("/invocations", json=BODY, headers=auth())
    assert spy.saved["conversation_id"] == "thread-9" and len(spy.saved["trace_id"]) == 32


def test_lam_nong_khong_goi_model_va_khong_goi_tool(monkeypatch):
    llm = make_llm([])
    client, _, tools = make_client(monkeypatch, llm=llm)
    body = {**BODY, "messages": [], "forwardedProps": {"warmup": True}}
    r = client.post("/invocations", json=body, headers=auth())
    ev = sse_events(r)
    assert [e["type"] for e in ev] == ["RUN_STARTED", "RUN_FINISHED"]
    assert ev[-1]["result"]["warm"] is True
    # không Bedrock, không DynamoDB, không tool
    assert llm[1].calls == [] and llm[2].calls == [] and tools.calls == []


def test_loi_bat_ngo_truoc_khi_co_luong_van_co_run_started_va_run_error(monkeypatch):
    def boom(identity):
        raise RuntimeError("hỏng")

    rt = AgentRuntime(
        agent_settings(),
        llm=lambda: make_llm([])[0],
        tools_factory=boom,
        store=UnconfiguredTurnBlockStore(),
    )
    r = TestClient(create_app(rt)).post("/invocations", json=BODY, headers=auth())
    ev = sse_events(r)
    assert [e["type"] for e in ev] == ["RUN_STARTED", "RUN_ERROR"] and ev[-1][
        "code"
    ] == "INTERNAL_ERROR"


def test_cham_tran_qua_http_van_tra_the_so_du_va_notice(monkeypatch):
    llm = make_llm([], FakeUsage(caps_hit={"m-small-a", "m-small-b"}))
    client, _, _ = make_client(monkeypatch, llm=llm)
    ev = sse_events(client.post("/invocations", json=BODY, headers=auth()))
    kinds = [e["content"]["type"] for e in ev if e["type"] == "ACTIVITY_SNAPSHOT"]
    assert kinds == ["jar_summary", "notice"] and ev[-1]["type"] == "RUN_FINISHED"
    assert ev[-1]["result"]["degraded"] is True
