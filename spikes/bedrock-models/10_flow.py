"""Mô phỏng một lượt what-if kiểu Yofina: router (Haiku 4.5, ép tool) -> planner (Sonnet 4.6, 2 vòng, tool giả) -> diễn giải (Haiku 4.5, stream).
Chạy 3 lượt liền nhau như người dùng thật để thấy độ trễ cả lượt và có bị Throttling khi dùng ở nhịp demo không. Dữ liệu hư cấu."""
import sys, time, json
from common import *

region = sys.argv[1] if len(sys.argv) > 1 else "ap-southeast-1"
c = client(region, read_timeout=120)
HAIKU, SONNET = MODELS["haiku45"], MODELS["sonnet46"]
ROUTER_TOOL = {"toolSpec": {"name": "report_intent", "description": "Báo cáo ý định", "inputSchema": {"json": {
    "type": "object", "properties": {"intent": {"type": "string", "enum": ["what_if_purchase", "jar_balance", "other"]},
                                      "amount_vnd": {"type": ["integer", "null"]}, "needs_clarification": {"type": "boolean"}},
    "required": ["intent", "amount_vnd", "needs_clarification"], "additionalProperties": False}}}}
SIM_TOOL = {"toolSpec": {"name": "simulate_purchase", "description": "Mô phỏng ảnh hưởng của một khoản mua lên các hũ", "inputSchema": {"json": {
    "type": "object", "properties": {"amount_vnd": {"type": "integer"}, "payment_method": {"type": "string"}}, "required": ["amount_vnd", "payment_method"]}}}}
UTTS = ["nếu mua tai nghe 1,2 triệu bằng ví trả sau thì sao", "nếu mua giày 900 nghìn bằng tiền mặt thì sao", "mua loa 2 triệu trả sau thì hũ nào cạn trước"]
log = []


def timed(label, fn):
    t0 = time.perf_counter()
    r, retries = with_retry(fn, tries=4, base=12, log=log)
    return r, time.perf_counter() - t0, retries


turns = []
for utt in UTTS:
    T0 = time.perf_counter()
    row = {"utt": utt}
    r, dt, rt = timed("router", lambda: c.converse(modelId=HAIKU, messages=[{"role": "user", "content": [{"text": utt}]}],
                                                    toolConfig={"tools": [ROUTER_TOOL], "toolChoice": {"tool": {"name": "report_intent"}}}, inferenceConfig={"maxTokens": 200}))
    row["router_s"] = round(dt, 2)
    msgs = [{"role": "user", "content": [{"text": utt + " (hãy gọi simulate_purchase rồi kết luận ngắn)"}]}]
    r1, dt, rt = timed("plan1", lambda: c.converse(modelId=SONNET, messages=msgs, toolConfig={"tools": [SIM_TOOL]}, inferenceConfig={"maxTokens": 300}))
    row["plan1_s"] = round(dt, 2)
    tu = next((b["toolUse"] for b in r1["output"]["message"]["content"] if "toolUse" in b), None)
    if tu:
        msgs += [r1["output"]["message"], {"role": "user", "content": [{"toolResult": {"toolUseId": tu["toolUseId"], "content": [{"json": {
            "jar_before": {"giai_tri": 1500000, "an_uong": 2200000}, "jar_after": {"giai_tri": 300000, "an_uong": 2200000}, "debt_added": 1200000, "ngay_can": "2026-12-14"}}]}}]}]
        r2, dt, rt = timed("plan2", lambda: c.converse(modelId=SONNET, messages=msgs, toolConfig={"tools": [SIM_TOOL]}, inferenceConfig={"maxTokens": 300}))
        row["plan2_s"] = round(dt, 2)
    def explain():
        t0 = time.perf_counter(); first = None
        s = c.converse_stream(modelId=HAIKU, messages=[{"role": "user", "content": [{"text": "Viết 2 câu tiếng Việt thân thiện: mua tai nghe 1,2 triệu bằng ví trả sau làm hũ giải trí còn 300 nghìn."}]}], inferenceConfig={"maxTokens": 120})
        for ev in s["stream"]:
            if first is None and "contentBlockDelta" in ev:
                first = time.perf_counter() - t0
        return first, time.perf_counter() - t0
    (first, tot), dt, rt = timed("explain", explain)
    row["explain_ttft_s"] = round(first, 2); row["explain_total_s"] = round(tot, 2)
    row["turn_total_s"] = round(time.perf_counter() - T0, 2)
    row["calls"] = 4 if tu else 3
    turns.append(row)
    print(row, flush=True)
print("throttle/retry log:", log)
json.dump(dict(turns=turns, retry_log=log), open(f"results_10_flow_{region}.json", "w"), ensure_ascii=False, indent=1)
