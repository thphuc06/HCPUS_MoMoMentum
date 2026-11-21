"""Mục 2: độ trễ tới token đầu (ConverseStream) và tổng (Converse), 3 lần lấy trung vị."""
import sys, time, json
from common import *
region = sys.argv[1] if len(sys.argv) > 1 else "ap-southeast-1"
keys = sys.argv[2].split(",") if len(sys.argv) > 2 else ["haiku45", "sonnet46", "nova2lite", "novalite", "novamicro", "novapro"]
c = client(region)
PROMPT = "Giải thích ngắn gọn trong đúng 2 câu: 'hũ ăn uống' trong quản lý chi tiêu cá nhân là gì?"
msgs = [{"role": "user", "content": [{"text": PROMPT}]}]
cfg = {"maxTokens": 100, "temperature": 0.2}
out = {}
for k in keys:
    mid = MODELS.get(k, k); ttft, tot_stream, tot_conv, otoks, logs = [], [], [], [], []
    for i in range(3):
        try:
            def call_stream():
                pace(k)
                t0 = time.perf_counter(); first = None
                r = c.converse_stream(modelId=mid, messages=msgs, inferenceConfig=cfg)
                usage = None
                for ev in r["stream"]:
                    if "contentBlockDelta" in ev and first is None and ev["contentBlockDelta"]["delta"].get("text"):
                        first = time.perf_counter() - t0
                    if "metadata" in ev: usage = ev["metadata"]["usage"]
                return first, time.perf_counter() - t0, usage
            (f, tt, u), _ = with_retry(call_stream, log=logs)
            ttft.append(f); tot_stream.append(tt); otoks.append(u["outputTokens"])
            def call_conv():
                pace(k)
                t0 = time.perf_counter(); r = c.converse(modelId=mid, messages=msgs, inferenceConfig=cfg)
                return time.perf_counter() - t0, r
            (tc, r), _ = with_retry(call_conv, log=logs)
            tot_conv.append(tc)
            if i == 0: sample = r["output"]["message"]["content"][-1].get("text", "")
        except Exception as e:
            logs.append("LỖI " + err_str(e)); break
    out[k] = dict(model=mid, region=region, ttft=[round(x,3) for x in ttft], ttft_med=med(ttft), total_stream=[round(x,3) for x in tot_stream],
                  total_stream_med=med(tot_stream), total_converse=[round(x,3) for x in tot_conv], total_converse_med=med(tot_conv), out_tokens=otoks, notes=logs, sample=sample if tot_conv else None)
    print(k, json.dumps({a: b for a, b in out[k].items() if a != "sample"}, ensure_ascii=False), flush=True)
    print("   mẫu:", out[k]["sample"], flush=True)
json.dump(out, open(f"results_02_latency_{region}.json", "w"), ensure_ascii=False, indent=1)
