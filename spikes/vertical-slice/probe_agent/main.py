"""Agent THỬ (không vào đường sản phẩm) cho hai phép thử "Chưa thử" của lát dọc:

1. Interrupt/resume AG-UI qua Runtime thật với session manager bền (S3).  forwardedProps.mode:
     "interrupt"      Strands + `S3SessionManager` (bền: resume được sau khi microVM bị dừng)
     "interrupt_ram"  Strands không session manager (chỉ RAM của microVM)
   Tool `move_plain` giả (chỉ ghi log, không ghi DB) gắn `ToolBehavior(interrupt_on_call=True)`.
2. Token hết hạn giữa luồng SSE.  forwardedProps = {"mode": "slow", "seconds": 420, "interval": 30, "gateway_url": ...}:
   phát một mẩu chữ mỗi `interval` giây trong `seconds` giây (kèm số giây còn lại của JWT), rồi gọi Gateway
   (`tools/list`) bằng đúng token đã nhận để xem token hết hạn bị từ chối ra sao.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import uuid

import httpx
import uvicorn
from ag_ui.core import (
    EventType,
    RunAgentInput,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from ag_ui.encoder import EventEncoder
from ag_ui_strands import StrandsAgent, StrandsAgentConfig, ToolBehavior
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from strands import Agent, tool
from strands.models import BedrockModel
from strands.session.s3_session_manager import S3SessionManager

REGION = os.environ.get("AWS_REGION") or "ap-southeast-1"
MODEL_ID = os.environ.get("PROBE_MODEL", "global.amazon.nova-2-lite-v1:0")
BUCKET = os.environ["PROBE_BUCKET"]
PREFIX = os.environ.get("PROBE_PREFIX", "tmp/probe-interrupt/")
PID = os.getpid()
BOOT = time.time()
SYSTEM = (
    "Bạn là trợ lý thử nghiệm. Khi người dùng yêu cầu chuyển tiền giữa hai hũ, "
    "gọi tool move_plain đúng một lần với tham số của họ. Trả lời ngắn bằng tiếng Việt."
)


def log(event: str, **kw) -> None:
    print(json.dumps({"event": event, "pid": PID, **kw}, ensure_ascii=False), flush=True)


@tool
def move_plain(from_jar: str, to_jar: str, amount_vnd: int) -> dict:
    """Chuyển tiền giữa hai hũ (GIẢ, chỉ ghi log).

    Args:
        from_jar: mã hũ nguồn
        to_jar: mã hũ đích
        amount_vnd: số tiền VND
    """
    log("move_plain_ran", from_jar=from_jar, to_jar=to_jar, amount_vnd=amount_vnd)
    return {"status": "done", "from_jar": from_jar, "to_jar": to_jar, "amount_vnd": amount_vnd}


def make_agent() -> Agent:
    return Agent(
        model=BedrockModel(model_id=MODEL_ID, region_name=REGION, temperature=0.0, max_tokens=400),
        system_prompt=SYSTEM,
        tools=[move_plain],
        callback_handler=None,
        agent_id="probe",
    )


def s3_provider(run_input):
    return S3SessionManager(
        session_id=run_input.thread_id, bucket=BUCKET, prefix=PREFIX, region_name=REGION
    )


BEHAVIORS = {"move_plain": ToolBehavior(interrupt_on_call=True)}
DURABLE = StrandsAgent(
    agent=make_agent(),
    name="probe",
    description="probe",
    config=StrandsAgentConfig(tool_behaviors=BEHAVIORS, session_manager_provider=s3_provider),
)
RAM_ONLY = StrandsAgent(
    agent=make_agent(),
    name="probe_ram",
    description="probe",
    config=StrandsAgentConfig(tool_behaviors=BEHAVIORS),
)

app = FastAPI()


@app.get("/ping")
async def ping():
    return {"status": "Healthy", "time_of_last_update": int(time.time())}


def jwt_exp(auth: str | None) -> int | None:
    try:
        seg = auth.split(" ", 1)[1].split(".")[1]
        return int(json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))["exp"])
    except Exception:
        return None


async def slow(run_input: RunAgentInput, auth: str | None, props: dict):
    seconds, interval = int(props.get("seconds", 420)), int(props.get("interval", 30))
    mid = f"msg-{uuid.uuid4().hex[:6]}"
    yield RunStartedEvent(type=EventType.RUN_STARTED, thread_id=run_input.thread_id, run_id=run_input.run_id)
    yield TextMessageStartEvent(type=EventType.TEXT_MESSAGE_START, message_id=mid, role="assistant")
    exp, t0 = jwt_exp(auth), time.time()
    elapsed = 0
    while elapsed < seconds:
        await asyncio.sleep(interval)
        elapsed = int(time.time() - t0)
        left = None if exp is None else int(exp - time.time())
        yield TextMessageContentEvent(
            type=EventType.TEXT_MESSAGE_CONTENT,
            message_id=mid,
            delta=f"[t+{elapsed}s, token còn {left}s] ",
        )
    gw_status = None
    gw_url = props.get("gateway_url")
    if gw_url and auth:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                gw_url,
                headers={
                    "Authorization": auth,
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            )
            gw_status = {"status": r.status_code, "body": r.text[:200]}
    yield TextMessageContentEvent(
        type=EventType.TEXT_MESSAGE_CONTENT,
        message_id=mid,
        delta=f"GATEWAY_AFTER_EXPIRY={json.dumps(gw_status, ensure_ascii=False)}",
    )
    yield TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id=mid)
    yield RunFinishedEvent(
        type=EventType.RUN_FINISHED,
        thread_id=run_input.thread_id,
        run_id=run_input.run_id,
        result={"gateway_after_expiry": gw_status, "token_left_at_end": None if exp is None else int(exp - time.time())},
    )


@app.post("/invocations")
async def invocations(request: Request):
    try:
        run_input = RunAgentInput.model_validate(await request.json())
    except Exception as exc:
        return JSONResponse({"error": str(exc)[:200]}, status_code=422)
    props = run_input.forwarded_props if isinstance(run_input.forwarded_props, dict) else {}
    mode = props.get("mode", "interrupt")
    encoder = EventEncoder(accept=request.headers.get("accept"))
    log("invocation", mode=mode, thread=run_input.thread_id, resume=bool(getattr(run_input, "resume", None)))
    if mode == "slow":
        gen = slow(run_input, request.headers.get("authorization"), props)
    elif mode == "interrupt_ram":
        gen = RAM_ONLY.run(run_input)
    else:
        gen = DURABLE.run(run_input)

    async def sse():
        async for event in gen:
            yield encoder.encode(event)

    return StreamingResponse(sse(), media_type=encoder.get_content_type())


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")
