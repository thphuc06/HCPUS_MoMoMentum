"""Mục 2 mở rộng: thăm dò từng model có quota > 0: (1) tiếng Việt stream x3 (TTFT, tổng), (2) tool use ép tool, (3) structured output gốc.
Dùng: python 08_probe.py <region> <nhóm: ap|us> [k1,k2,...]"""
import sys, time, json, os
from common import *

region, group = sys.argv[1], sys.argv[2]
only = sys.argv[3].split(",") if len(sys.argv) > 3 else None

CANDS = {
 "ap": {  # ap-southeast-1
  "novapro": "apac.amazon.nova-pro-v1:0", "novalite": "apac.amazon.nova-lite-v1:0", "nova2lite": "global.amazon.nova-2-lite-v1:0",
  "gpt6luna": "global.openai.gpt-6-luna", "gpt6sol": "global.openai.gpt-6-sol", "gpt61terra": "global.openai.gpt-6.1-terra",
  "gpt61sol": "global.openai.gpt-6.1-sol", "gpt62astra": "global.openai.gpt-6.2-astra", "gpt62sol": "global.openai.gpt-6.2-sol",
  "gpt55": "global.openai.gpt-5.5", "gpt54": "global.openai.gpt-5.4",
  "kimik3": "global.moonshotai.kimi-k3", "kimik31": "global.moonshotai.kimi-k3.1",
  "haiku45": "global.anthropic.claude-haiku-4-5-20251001-v1:0", "sonnet46": "global.anthropic.claude-sonnet-4-6",
 },
 "us": {  # us-east-1
  "gptoss120": "openai.gpt-oss-120b-1:0", "gptoss20": "openai.gpt-oss-20b-1:0", "deepseekv32": "deepseek.v3.2",
  "qwen3next80": "qwen.qwen3-next-80b-a3b", "qwen3_32": "qwen.qwen3-32b-v1:0", "qwen3vl235": "qwen.qwen3-vl-235b-a22b",
  "mistrallarge3": "mistral.mistral-large-3-675b-instruct", "ministral14": "mistral.ministral-3-14b-instruct",
  "kimik25": "moonshotai.kimi-k2.5", "gemma27": "google.gemma-3-27b-it", "gemma12": "google.gemma-3-12b-it",
  "glm47": "zai.glm-4.7", "glm47flash": "zai.glm-4.7-flash", "minimaxm25": "minimax.minimax-m2.5",
  "llama4mav": "us.meta.llama4-maverick-17b-instruct-v1:0", "llama4scout": "us.meta.llama4-scout-17b-instruct-v1:0",
  "llama33_70": "us.meta.llama3-3-70b-instruct-v1:0", "nemotronsuper": "nvidia.nemotron-super-3-120b",
  "novapro": "us.amazon.nova-pro-v1:0", "novalite": "us.amazon.nova-lite-v1:0", "novamicro": "us.amazon.nova-micro-v1:0",
  "nova2lite": "global.amazon.nova-2-lite-v1:0",
  "gpt6luna": "global.openai.gpt-6-luna", "gpt61terra": "global.openai.gpt-6.1-terra", "gpt6sol": "global.openai.gpt-6-sol",
  "kimik3": "global.moonshotai.kimi-k3",
  "haiku45": "global.anthropic.claude-haiku-4-5-20251001-v1:0", "sonnet46": "global.anthropic.claude-sonnet-4-6",
 }}[group]
if only:
    CANDS = {k: v for k, v in CANDS.items() if k in only}

PROMPT = "Giải thích ngắn gọn trong đúng 2 câu: 'hũ ăn uống' trong quản lý chi tiêu cá nhân là gì?"
INTENTS = ["what_if_purchase", "jar_balance", "spending_summary", "forecast_depletion", "investment_advice", "other"]
SCHEMA = {"type": "object", "properties": {
    "intent": {"type": "string", "enum": INTENTS},
    "params": {"type": "object", "properties": {"amount_vnd": {"type": ["integer", "null"]}, "item": {"type": ["string", "null"]},
        "payment_method": {"type": ["string", "null"]}, "jar": {"type": ["string", "null"]}},
        "required": ["amount_vnd", "item", "payment_method", "jar"], "additionalProperties": False},
    "confidence": {"type": "number"}, "needs_clarification": {"type": "boolean"}, "clarification_question": {"type": ["string", "null"]}},
    "required": ["intent", "params", "confidence", "needs_clarification", "clarification_question"], "additionalProperties": False}
SYSTEM = [{"text": "Bạn là bộ phân loại ý định cho trợ lý tài chính cá nhân tiếng Việt. Chỉ phân loại, không trả lời. investment_advice dùng cho câu xin khuyến nghị mã cổ phiếu/quỹ/tiền mã hóa."}]
UTT = "nếu mua tai nghe 1,2 triệu bằng ví trả sau thì sao"
c = client(region, read_timeout=180)
RES = f"results_08_probe_{group}.json"
res = json.load(open(RES, encoding="utf8")) if os.path.exists(RES) else {}
gap = lambda k: 12.0 if k in ("haiku45", "sonnet46") else 1.5


def stream_once(mid, k):
    pace(k, gap(k))
    t0 = time.perf_counter()
    first_any = first_text = None
    text = ""
    reason = ""
    usage = None
    r = c.converse_stream(modelId=mid, messages=[{"role": "user", "content": [{"text": PROMPT}]}], inferenceConfig={"maxTokens": 300})
    for ev in r["stream"]:
        if "contentBlockDelta" in ev:
            d = ev["contentBlockDelta"]["delta"]
            now = time.perf_counter() - t0
            if first_any is None:
                first_any = now
            if d.get("text"):
                if first_text is None:
                    first_text = now
                text += d["text"]
            elif d.get("reasoningContent"):
                reason += d["reasoningContent"].get("text", "") or ""
        if "metadata" in ev:
            usage = ev["metadata"]["usage"]
    return dict(first_any=first_any, first_text=first_text, total=time.perf_counter() - t0, text=text, reasoning_chars=len(reason), usage=usage)


for k, mid in CANDS.items():
    if k in res and "text" in res[k] and not only:
        continue
    out = {"model": mid, "region": region}
    logs = []
    runs = []
    try:
        for i in range(3):
            r, _ = with_retry(lambda: stream_once(mid, k), tries=6, base=10, log=logs)
            runs.append(r)
        out["text"] = dict(ttft_text_med=med([r["first_text"] for r in runs if r["first_text"]]), ttft_any_med=med([r["first_any"] for r in runs if r["first_any"]]),
                           total_med=med([r["total"] for r in runs]), out_tokens=[r["usage"]["outputTokens"] for r in runs if r["usage"]],
                           runs=[{kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in r.items()} for r in runs])
    except Exception as e:
        out["text"] = dict(error=err_str(e), partial=len(runs))
    dead = "error" in out["text"] and ("AccessDenied" in out["text"]["error"] or "not available" in out["text"]["error"])
    for mode in ("tool_forced", "tool_auto", "schema"):
        if mode == "tool_auto" and "error" not in out.get("tool_forced", {"error": 1}):
            continue
        if dead:
            out[mode] = dict(skipped="model không gọi được")
            continue
        kw = dict(modelId=mid, system=SYSTEM, messages=[{"role": "user", "content": [{"text": UTT}]}], inferenceConfig={"maxTokens": 600})
        if mode.startswith("tool"):
            kw["toolConfig"] = {"tools": [{"toolSpec": {"name": "report_intent", "description": "Báo cáo kết quả phân loại ý định", "inputSchema": {"json": SCHEMA}}}]}
            kw["toolConfig"]["toolChoice"] = {"tool": {"name": "report_intent"}} if mode == "tool_forced" else {"auto": {}}
        else:
            kw["outputConfig"] = {"textFormat": {"type": "json_schema", "structure": {"jsonSchema": {"name": "IntentResult", "schema": json.dumps(SCHEMA)}}}}
        try:
            pace(k, gap(k))
            t0 = time.perf_counter()
            r, _ = with_retry(lambda: c.converse(**kw), tries=6, base=10, log=logs)
            dt = time.perf_counter() - t0
            blocks = r["output"]["message"]["content"]
            tu = [b["toolUse"]["input"] for b in blocks if "toolUse" in b]
            tx = [b["text"] for b in blocks if "text" in b]
            parsed = None
            if tu:
                parsed = tu[0]
            else:
                try:
                    parsed = json.loads(tx[0]) if tx else None
                except Exception:
                    parsed = {"_unparsed_text": (tx[0][:200] if tx else "")}
            out[mode] = dict(secs=round(dt, 2), parsed=parsed, used_tool=bool(tu), stop=r["stopReason"], usage=r["usage"])
        except Exception as e:
            out[mode] = dict(error=err_str(e))
    out["retries"] = logs
    res[k] = out
    t = out["text"]
    print(f"[{region}] {k} ({mid})")
    print("   text:", {a: b for a, b in t.items() if a != "runs"} if "error" not in t else t)
    if "runs" in t:
        print("   mẫu:", (t["runs"][0]["text"] or "")[:260].replace("\n", " "))
    for mode in ("tool_forced", "tool_auto", "schema"):
        if mode in out:
            print(f"   {mode}:", json.dumps(out[mode], ensure_ascii=False)[:330])
    sys.stdout.flush()
    json.dump(res, open(RES, "w", encoding="utf8"), ensure_ascii=False, indent=1)
