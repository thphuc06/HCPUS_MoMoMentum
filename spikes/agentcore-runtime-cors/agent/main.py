"""Agent AG-UI tối thiểu cho spike AgentCore Runtime (CORS / JWT / SSE).

Hai chế độ theo payload (forwardedProps.mode):
  - "fake" (mặc định): phát event AG-UI giả, không gọi LLM; có CUSTOM event "spike.info"
    (pid, thời gian boot, số lần gọi, header app nhìn thấy) để đo phiên/streaming.
  - "llm": Strands Agent + Bedrock Haiku 4.5 + 1 tool tất định qua ag-ui-strands.
Biến môi trường:
  SPIKE_CORS = on|off   bật/tắt CORSMiddleware trong app (để kiểm header CORS do ai trả).
"""
import asyncio
import json
import os
import time
import uuid

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from ag_ui.core import (EventType, RunAgentInput, RunFinishedEvent, RunStartedEvent,
                        TextMessageContentEvent, TextMessageEndEvent, TextMessageStartEvent,
                        CustomEvent)
from ag_ui.encoder import EventEncoder

BOOT_TS = time.time()
PID = os.getpid()
COUNTER = {"n": 0}
CORS_MODE = os.environ.get("SPIKE_CORS", "off")
MODEL_ID = os.environ.get("SPIKE_MODEL", "global.anthropic.claude-haiku-4-5-20251001-v1:0")
REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "ap-southeast-1"

app = FastAPI()

if CORS_MODE == "on":
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["authorization", "content-type", "accept",
                       "x-amzn-bedrock-agentcore-runtime-session-id",
                       "x-amzn-trace-id", "traceparent", "x-yofina-test",
                       "x-amzn-bedrock-agentcore-runtime-custom-foo"],
        expose_headers=["x-amzn-bedrock-agentcore-runtime-session-id", "x-spike-marker"],
        max_age=600)


def log(kind, **kw):
    print(json.dumps({"spike": kind, "pid": PID, "ts": time.time(), **kw}, default=repr), flush=True)


_llm = {}


def get_llm_agent():
    """ag-ui-strands giữ mỗi thread một Agent trong tiến trình; tạo StrandsAgent một lần."""
    if "a" not in _llm:
        from strands import Agent, tool
        from strands.models import BedrockModel
        from ag_ui_strands import StrandsAgent

        @tool
        def get_jar_balances() -> dict:
            """Lấy số dư hiện tại của các hũ chi tiêu (VND)."""
            return {"as_of": "2026-11-21", "jars": [
                {"code": "an_uong", "name": "Ăn uống", "balance_vnd": 1250000, "budget_vnd": 3000000},
                {"code": "di_lai", "name": "Đi lại", "balance_vnd": 640000, "budget_vnd": 1000000}]}

        def factory():
            return Agent(model=BedrockModel(model_id=MODEL_ID, region_name=REGION, temperature=0.0,
                                            max_tokens=400),
                         system_prompt="Bạn là trợ lý Yofina. Trả lời rất ngắn bằng tiếng Việt. "
                                       "Luôn gọi tool để lấy số, không bịa.",
                         tools=[get_jar_balances], callback_handler=None)
        _llm["a"] = StrandsAgent(agent=factory(), name="spike", description="spike")  # instance; factory chỉ dành cho Graph/Swarm
    return _llm["a"]


@app.get("/ping")
async def ping():
    return JSONResponse({"status": "Healthy"})


@app.get("/info")
async def info():
    return {"pid": PID, "boot_ts": BOOT_TS, "cors_mode": CORS_MODE}


def seen_headers(request: Request):
    out = {}
    for k, v in request.headers.items():
        lk = k.lower()
        out[lk] = "<present, %d chars>" % len(v) if (lk == "authorization" or "token" in lk) and lk != "x-amzn-trace-id" else v[:200]
    return out


@app.post("/invocations")
async def invocations(input_data: dict, request: Request):
    COUNTER["n"] += 1
    n = COUNTER["n"]
    t_in = time.time()
    hdrs = seen_headers(request)
    fp = input_data.get("forwardedProps") or {}
    mode = fp.get("mode", "fake")
    log("invocation", n=n, mode=mode, headers=sorted(hdrs.keys()), traceparent=hdrs.get("traceparent"),
        xray=hdrs.get("x-amzn-trace-id"), session=hdrs.get("x-amzn-bedrock-agentcore-runtime-session-id"))
    encoder = EventEncoder(accept=request.headers.get("accept"))
    run_input = RunAgentInput(**input_data)

    async def gen():
        if mode == "llm":
            async for ev in get_llm_agent().run(run_input):
                yield encoder.encode(ev)
            return
        chunks = int(fp.get("chunks", 6))
        delay = float(fp.get("delay", 0.5))
        mid = "msg-" + uuid.uuid4().hex[:6]
        yield encoder.encode(RunStartedEvent(type=EventType.RUN_STARTED, thread_id=run_input.thread_id,
                                             run_id=run_input.run_id))
        yield encoder.encode(CustomEvent(type=EventType.CUSTOM, name="spike.info", value={
            "pid": PID, "boot_ts": BOOT_TS, "invocation_n": n, "uptime_s": round(t_in - BOOT_TS, 3),
            "cors_mode": CORS_MODE, "headers_seen_by_app": hdrs, "server_ts": time.time()}))
        yield encoder.encode(TextMessageStartEvent(type=EventType.TEXT_MESSAGE_START, message_id=mid,
                                                   role="assistant"))
        for i in range(chunks):
            await asyncio.sleep(delay)
            yield encoder.encode(TextMessageContentEvent(
                type=EventType.TEXT_MESSAGE_CONTENT, message_id=mid, delta=f"chunk{i} "))
        yield encoder.encode(TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id=mid))
        yield encoder.encode(RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id=run_input.thread_id,
                                              run_id=run_input.run_id))

    return StreamingResponse(gen(), media_type=encoder.get_content_type(),
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                      "X-Spike-Marker": "from-app"})


if __name__ == "__main__":
    log("boot", cors_mode=CORS_MODE, model=MODEL_ID, region=REGION)
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), log_level="warning")
