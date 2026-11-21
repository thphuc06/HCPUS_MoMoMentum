"""Mục 1b: thử các model khác để biết cái nào gọi được (không retry)."""
import sys, time
from common import *
region = sys.argv[1] if len(sys.argv) > 1 else "ap-southeast-1"
c = client(region)
ids = {"sonnet5(global)": "global.anthropic.claude-sonnet-5", "sonnet5(in-region)": "anthropic.claude-sonnet-5",
       "opus55": "global.anthropic.claude-opus-5-5", "fable52": "global.anthropic.claude-fable-5-2",
       "opus46": "global.anthropic.claude-opus-4-6-v1", "nova2lite": MODELS["nova2lite"], "novalite": MODELS["novalite"],
       "novamicro": MODELS["novamicro"], "novapro": MODELS["novapro"]}
for k, mid in ids.items():
    t = time.time()
    try:
        r = c.converse(modelId=mid, messages=[{"role": "user", "content": [{"text": "Chào, trả lời đúng một từ: ok"}]}], inferenceConfig={"maxTokens": 20})
        print(f"[{region}] {k}: GỌI ĐƯỢC {time.time()-t:.2f}s usage_in/out={r['usage']['inputTokens']}/{r['usage']['outputTokens']}")
    except Exception as e:
        print(f"[{region}] {k}: LỖI {err_str(e)}")
    time.sleep(7)
