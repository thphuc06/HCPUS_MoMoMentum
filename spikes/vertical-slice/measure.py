"""Số đo lát dọc: Runtime thật (lượt đầu phiên lạnh vs lượt hai), trọn lượt, thời gian lưu lượt, và độ trễ Gateway ấm
(có interceptor + Cedar) so với gọi thẳng Lambda.

    uv run spikes/vertical-slice/measure.py runtime --sessions 5     # tốn ~2 lượt gọi model mỗi lượt, 2 lượt mỗi phiên
    uv run spikes/vertical-slice/measure.py gateway --calls 15
Kết quả JSON ghi ở spikes/vertical-slice/out/ (không chứa token, ARN hay account ID).
"""

from __future__ import annotations

import argparse
import base64
import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests" / "integration"))

from _demo_auth import login_access_token  # noqa: E402
from _yofina import session, ssm_param  # noqa: E402
from agentcore_helpers import GatewayClient, invoke_agent, new_session_id, runtime_url  # noqa: E402

OUT = HERE / "out"
OUT.mkdir(exist_ok=True)


def summarize(values: list[float]) -> dict:
    if not values:
        return {}
    v = sorted(values)
    return {
        "n": len(v),
        "min": round(v[0], 3),
        "median": round(statistics.median(v), 3),
        "max": round(v[-1], 3),
        "values": [round(x, 3) for x in values],
    }


def measure_runtime(sessions: int, pace: float) -> dict:
    sess = session()
    token = login_access_token("minh", sess=sess)
    url = runtime_url(ssm_param("agent/runtime-arn", sess=sess))
    first_event_t1, first_event_t2, total_t1, total_t2, persist_t1, persist_t2 = (
        [] for _ in range(6)
    )
    rows = []
    for i in range(sessions):
        sid = new_session_id()
        r1 = invoke_agent(url, token, "số dư các hũ của mình", session_id=sid)
        assert r1.status == 200 and r1.finished, (r1.status, r1.raw)
        time.sleep(pace)
        history = [
            {"id": "m1", "role": "user", "content": "số dư các hũ của mình"},
            {"id": "a1", "role": "assistant", "content": r1.text or "ok"},
            {"id": "m2", "role": "user", "content": "cho mình xem 5 giao dịch gần nhất"},
        ]
        r2 = invoke_agent(url, token, None, session_id=sid, messages=history)
        assert r2.status == 200 and r2.finished, (r2.status, r2.raw)

        def persist_gap(run) -> float:
            content = [e["_t"] for e in run.events if e["type"] != "RUN_FINISHED"]
            return round(run.finished["_t"] - max(content), 3)

        first_event_t1.append(r1.t_first_event)
        first_event_t2.append(r2.t_first_event)
        total_t1.append(r1.total)
        total_t2.append(r2.total)
        persist_t1.append(persist_gap(r1))
        persist_t2.append(persist_gap(r2))
        rows.append(
            {
                "session": i + 1,
                "turn1": {
                    "first_event_s": r1.t_first_event,
                    "total_s": r1.total,
                    "intent": r1.finished["result"]["intent"],
                    "degraded": r1.finished["result"]["degraded"],
                },
                "turn2": {
                    "first_event_s": r2.t_first_event,
                    "total_s": r2.total,
                    "intent": r2.finished["result"]["intent"],
                    "degraded": r2.finished["result"]["degraded"],
                },
            }
        )
        print(rows[-1], file=sys.stderr)
        time.sleep(pace)
    return {
        "first_event_turn1_cold_s": summarize(first_event_t1),
        "first_event_turn2_s": summarize(first_event_t2),
        "total_turn1_s": summarize(total_t1),
        "total_turn2_s": summarize(total_t2),
        "gap_last_content_to_run_finished_turn1_s": summarize(persist_t1),
        "gap_last_content_to_run_finished_turn2_s": summarize(persist_t2),
        "sessions": rows,
    }


def measure_gateway(calls: int) -> dict:
    sess = session()
    token = login_access_token("minh", sess=sess)
    gw = GatewayClient(ssm_param("gateway_url", sess=sess), token)
    import asyncio

    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async def run():
        timings = {"initialize": 0.0, "get_jar_balances": [], "move_no_token": [], "list_tools": []}
        async with httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {token}"}, timeout=60.0
        ) as client:
            t0 = time.perf_counter()
            async with streamable_http_client(gw.url, http_client=client) as streams:
                async with ClientSession(streams[0], streams[1]) as s:
                    await s.initialize()
                    timings["initialize"] = (time.perf_counter() - t0) * 1000
                    for _ in range(calls):
                        t = time.perf_counter()
                        await s.call_tool("ledger___get_jar_balances", {})
                        timings["get_jar_balances"].append((time.perf_counter() - t) * 1000)
                    for _ in range(max(3, calls // 3)):
                        t = time.perf_counter()
                        await s.call_tool(
                            "ledger___move_between_jars",
                            {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 1000},
                        )
                        timings["move_no_token"].append((time.perf_counter() - t) * 1000)
                    for _ in range(3):
                        t = time.perf_counter()
                        await s.list_tools()
                        timings["list_tools"].append((time.perf_counter() - t) * 1000)
        return timings

    gw_ms = asyncio.run(run())

    # đối chứng: gọi thẳng Lambda (boto3 invoke, cùng sự kiện Gateway)
    lam = sess.client("lambda")
    fn = ssm_param("ledger/function-name", sess=sess)
    sub = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))["sub"]
    ctx = base64.b64encode(
        json.dumps({"custom": {"bedrockAgentCoreToolName": "ledger___get_jar_balances"}}).encode()
    ).decode()
    direct = []
    for _ in range(calls):
        t = time.perf_counter()
        lam.invoke(
            FunctionName=fn, ClientContext=ctx, Payload=json.dumps({"user_id": sub}).encode()
        )
        direct.append((time.perf_counter() - t) * 1000)
    return {
        "note": "ms, đo từ máy dev (Việt Nam) qua internet; chênh lệch Gateway so với Lambda trực tiếp gồm mạng tới Gateway, JWT, interceptor, Cedar (ENFORCE)",
        "mcp_initialize_ms": round(gw_ms["initialize"], 1),
        "gateway_get_jar_balances_warm_ms": summarize(gw_ms["get_jar_balances"]),
        "gateway_move_no_token_warm_ms": summarize(gw_ms["move_no_token"]),
        "gateway_tools_list_ms": summarize(gw_ms["list_tools"]),
        "lambda_direct_invoke_ms": summarize(direct),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="what", required=True)
    r = sub.add_parser("runtime")
    r.add_argument("--sessions", type=int, default=5)
    r.add_argument("--pace", type=float, default=6.0)
    g = sub.add_parser("gateway")
    g.add_argument("--calls", type=int, default=15)
    args = ap.parse_args()
    result = (
        measure_runtime(args.sessions, args.pace)
        if args.what == "runtime"
        else measure_gateway(args.calls)
    )
    path = OUT / f"measure_{args.what}_{time.strftime('%Y%m%dT%H%M%S')}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "sessions"}, ensure_ascii=False, indent=2
        )
    )
    print("ghi", path, file=sys.stderr)


if __name__ == "__main__":
    main()
