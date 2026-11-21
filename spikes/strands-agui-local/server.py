"""Server AG-UI local: nhiều route để thử cách phát khối UI, structured output, interrupt.

Chạy:  python server.py --port 8101 [--session-dir sessions] [--origins http://localhost:5173]
Route: /base /ui_custom /ui_activity /ui_state /ui_delta /ui_all /structured
       /interrupt /interrupt_nosm /interrupt_hook
"""
import argparse, json, os, time
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from strands import Agent, tool
from strands.session.file_session_manager import FileSessionManager
from ag_ui.core import CustomEvent, ActivitySnapshotEvent, StateDeltaEvent, EventType
from ag_ui_strands import (StrandsAgent, StrandsAgentConfig, ToolBehavior,
                           add_strands_fastapi_endpoint, add_ping)

from common import model, JARS
from schemas import IntentResult

HERE = Path(__file__).parent
LOG = HERE / "logs"
LOG.mkdir(exist_ok=True)
SYS = "Bạn là trợ lý tài chính Yofina. Trả lời ngắn gọn bằng tiếng Việt. Luôn dùng tool để lấy số, không bịa."


def log(name, obj):
    with open(LOG / f"{name}.log", "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, default=repr) + "\n")


# ---------- tool tất định ----------
@tool
def get_jar_balances() -> dict:
    """Lấy số dư hiện tại của các hũ chi tiêu của người dùng (VND)."""
    return {"as_of": "2026-11-21", "jars": [
        {"code": k, "name": v["name"], "balance_vnd": v["balance_vnd"], "budget_vnd": v["budget_vnd"]}
        for k, v in JARS.items()]}


# ---------- block builder: chạy bằng code, KHÔNG qua LLM ----------
def build_jar_summary(result: dict) -> dict:
    return {
        "type": "jar_summary", "v": 1, "id": "js:" + result["as_of"],
        "source": {"tool": "get_jar_balances", "as_of": result["as_of"]},
        "fallback_text": "; ".join(
            f'{j["name"]}: {j["balance_vnd"]:,} đ'.replace(",", ".") for j in result["jars"]),
        "data": {"jars": [dict(j, pct_left=round(100 * j["balance_vnd"] / j["budget_vnd"]))
                          for j in result["jars"]]},
    }


def _as_dict(result_data):
    """Handler nhận result_data dạng nào? ghi log để biết, rồi chuẩn hóa."""
    log("result_data_types", {"type": type(result_data).__name__, "repr": repr(result_data)[:300]})
    if isinstance(result_data, dict):
        return result_data
    if isinstance(result_data, str):
        return json.loads(result_data)
    if isinstance(result_data, list):  # content blocks [{"text": "..."}]
        return json.loads(result_data[0]["text"])
    raise TypeError(type(result_data))


async def custom_handler(ctx):
    block = build_jar_summary(_as_dict(ctx.result_data))
    yield CustomEvent(type=EventType.CUSTOM, name="yofina.block", value=block)


async def activity_handler(ctx):
    block = build_jar_summary(_as_dict(ctx.result_data))
    yield ActivitySnapshotEvent(type=EventType.ACTIVITY_SNAPSHOT, message_id=block["id"],
                                activity_type="yofina.block", content=block, replace=True)


def state_from_result(ctx):
    return {"composer": {"blocks": [build_jar_summary(_as_dict(ctx.result_data))]}}


async def delta_handler(ctx):
    block = build_jar_summary(_as_dict(ctx.result_data))
    yield StateDeltaEvent(type=EventType.STATE_DELTA,
                          delta=[{"op": "add", "path": "/blocks", "value": [block]}])


async def all_handler(ctx):
    async for e in custom_handler(ctx):
        yield e
    async for e in activity_handler(ctx):
        yield e
    async for e in delta_handler(ctx):
        yield e


@tool
async def show_jar_summary():
    """Hiển thị khối số dư các hũ cho người dùng và trả số dư về cho bạn."""
    raw = {"as_of": "2026-11-21", "jars": [
        {"code": k, "name": v["name"], "balance_vnd": v["balance_vnd"], "budget_vnd": v["budget_vnd"]}
        for k, v in JARS.items()]}
    yield {"state": {"composer": {"blocks": [build_jar_summary(raw)]}}}   # -> STATE_SNAPSHOT (cơ chế async-generator tool)
    yield {"as_of": raw["as_of"], "an_uong_balance_vnd": JARS["an_uong"]["balance_vnd"]}  # kết quả tool (LLM chỉ thấy bản gọn này)


@tool
async def show_jar_summary_v2():
    """Hiển thị khối số dư các hũ cho người dùng và trả số dư về cho bạn."""
    raw = {"as_of": "2026-11-21", "jars": [
        {"code": k, "name": v["name"], "balance_vnd": v["balance_vnd"], "budget_vnd": v["budget_vnd"]}
        for k, v in JARS.items()]}
    yield {"yofina_block": build_jar_summary(raw)}       # đi ra tool_stream_event_handler, LLM không thấy
    yield {"as_of": raw["as_of"], "an_uong_balance_vnd": JARS["an_uong"]["balance_vnd"]}


async def stream_event_handler(ctx):
    """ToolStreamEventContext: tool_use_id, tool_name, stream_data."""
    log("stream_ctx", {"tool": ctx.tool_name, "keys": list(ctx.stream_data)[:3] if isinstance(ctx.stream_data, dict) else repr(ctx.stream_data)[:80]})
    if isinstance(ctx.stream_data, dict) and "yofina_block" in ctx.stream_data:
        block = ctx.stream_data["yofina_block"]
        yield ActivitySnapshotEvent(type=EventType.ACTIVITY_SNAPSHOT, message_id=block["id"],
                                    activity_type="yofina.block", content=block, replace=True)


# ---------- tool ghi giả + interrupt ----------
LEDGER = HERE / "logs" / "ledger.json"


@tool(context=True)
def move_between_jars(from_jar: str, to_jar: str, amount_vnd: int, tool_context) -> dict:
    """Chuyển tiền giữa hai hũ (GHI dữ liệu, cần người dùng xác nhận).

    Args:
        from_jar: mã hũ nguồn, ví dụ giai_tri
        to_jar: mã hũ đích, ví dụ an_uong
        amount_vnd: số tiền VND, số nguyên dương
    """
    # BẪY: dòng dưới chạy lại mỗi lần resume
    log("pre_interrupt", {"pid": os.getpid(), "ts": time.time(), "args": [from_jar, to_jar, amount_vnd]})
    approval = tool_context.interrupt(
        "yofina-confirm-move",
        reason={"message": f"Chuyển {amount_vnd:,} đ từ {from_jar} sang {to_jar}?".replace(",", "."),
                "from_jar": from_jar, "to_jar": to_jar, "amount_vnd": amount_vnd})
    log("post_interrupt", {"pid": os.getpid(), "approval": approval})
    resp = approval.get("response") if isinstance(approval, dict) else approval
    if not isinstance(approval, dict) or approval.get("cancelled") or not (resp or {}).get("approved"):
        return {"status": "cancelled"}
    LEDGER.write_text(json.dumps({"moved": [from_jar, to_jar, amount_vnd]}), encoding="utf-8")
    return {"status": "done", "from_jar": from_jar, "to_jar": to_jar, "amount_vnd": amount_vnd}


@tool
def move_plain(from_jar: str, to_jar: str, amount_vnd: int) -> dict:
    """Chuyển tiền giữa hai hũ (GHI dữ liệu); dùng cùng ToolBehavior(interrupt_on_call=True).

    Args:
        from_jar: mã hũ nguồn
        to_jar: mã hũ đích
        amount_vnd: số tiền VND
    """
    log("move_plain_ran", {"pid": os.getpid(), "args": [from_jar, to_jar, amount_vnd]})
    return {"status": "done", "from_jar": from_jar, "to_jar": to_jar, "amount_vnd": amount_vnd}


async def structured_surface(ctx):
    """Đưa structured output ra frontend: tool 'IntentResult' do Strands tạo từ schema; lấy tool_input khi validate xong."""
    log("structured_ctx", {"tool": ctx.tool_name, "input": ctx.tool_input, "result": repr(ctx.result_data)[:120]})
    if str(ctx.result_data).startswith("Successfully validated"):
        yield CustomEvent(type=EventType.CUSTOM, name="yofina.structured_output",
                          value={"schema": ctx.tool_name, "object": ctx.tool_input})


def make_agent(tools, **kw):
    return Agent(model=model(512), system_prompt=SYS, tools=tools, callback_handler=None,
                 agent_id="yofina", **kw)


def build_app(session_dir: Path, origins) -> FastAPI:
    app = FastAPI(title="strands-agui-local spike")
    if origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=origins, allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["authorization", "content-type", "x-amzn-bedrock-agentcore-runtime-session-id"],
            expose_headers=["x-amzn-bedrock-agentcore-runtime-session-id"])

    def reg(path, tools, config=None, **kw):
        a = StrandsAgent(agent=make_agent(tools, **kw), name=path.strip("/"), description="spike", config=config)
        add_strands_fastapi_endpoint(app, a, path)

    reg("/base", [get_jar_balances])
    reg("/ui_custom", [get_jar_balances], StrandsAgentConfig(tool_behaviors={
        "get_jar_balances": ToolBehavior(custom_result_handler=custom_handler)}))
    reg("/ui_activity", [get_jar_balances], StrandsAgentConfig(tool_behaviors={
        "get_jar_balances": ToolBehavior(custom_result_handler=activity_handler)}))
    reg("/ui_state", [get_jar_balances], StrandsAgentConfig(tool_behaviors={
        "get_jar_balances": ToolBehavior(state_from_result=state_from_result)}))
    reg("/ui_delta", [get_jar_balances], StrandsAgentConfig(tool_behaviors={
        "get_jar_balances": ToolBehavior(custom_result_handler=delta_handler)}))
    reg("/ui_all", [get_jar_balances], StrandsAgentConfig(tool_behaviors={
        "get_jar_balances": ToolBehavior(state_from_result=state_from_result,
                                         custom_result_handler=all_handler)}))
    reg("/ui_gen", [show_jar_summary])
    reg("/ui_stream", [show_jar_summary_v2], StrandsAgentConfig(tool_behaviors={
        "show_jar_summary_v2": ToolBehavior(tool_stream_event_handler=stream_event_handler)}))
    reg("/structured", [get_jar_balances], structured_output_model=IntentResult)
    reg("/structured2", [get_jar_balances], StrandsAgentConfig(tool_behaviors={
        "IntentResult": ToolBehavior(custom_result_handler=structured_surface)}),
        structured_output_model=IntentResult)

    def sm_provider(run_input):
        return FileSessionManager(session_id=run_input.thread_id, storage_dir=str(session_dir))

    reg("/interrupt", [move_between_jars], StrandsAgentConfig(session_manager_provider=sm_provider))
    reg("/interrupt_nosm", [move_between_jars])
    reg("/interrupt_hook", [move_plain], StrandsAgentConfig(
        tool_behaviors={"move_plain": ToolBehavior(interrupt_on_call=True)},
        session_manager_provider=sm_provider))
    from strands.vended_interventions import HumanInTheLoop
    reg("/interrupt_hitl", [get_jar_balances, move_plain], StrandsAgentConfig(session_manager_provider=sm_provider),
        interventions=[HumanInTheLoop(allowed_tools=["get_jar_balances"])])
    add_ping(app, "/ping")
    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8101)
    ap.add_argument("--session-dir", default=str(HERE / "sessions"))
    ap.add_argument("--origins", nargs="*", default=None)
    args = ap.parse_args()
    Path(args.session_dir).mkdir(parents=True, exist_ok=True)
    uvicorn.run(build_app(Path(args.session_dir), args.origins), host="127.0.0.1",
                port=args.port, log_level="warning")
