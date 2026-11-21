"""Mục 1: gọi Haiku 5.5 / Sonnet 5.5 (và 4.x để đối chứng), KHÔNG retry, ghi nguyên mã lỗi."""
import sys, time, json
from common import *
region = sys.argv[1] if len(sys.argv) > 1 else "ap-southeast-1"
c = client(region)
for key in ["haiku55", "sonnet55", "haiku45", "sonnet46"]:
    mid = MODELS[key]
    t = time.time()
    try:
        r = c.converse(modelId=mid, messages=[{"role": "user", "content": [{"text": "Chào, trả lời đúng một từ: ok"}]}],
                       inferenceConfig={"maxTokens": 20})
        txt = r["output"]["message"]["content"][0].get("text", str(r["output"]["message"]["content"]))
        print(f"[{region}] {key}: GỌI ĐƯỢC {time.time()-t:.2f}s usage={r['usage']} text={txt!r} stop={r['stopReason']}")
    except Exception as e:
        print(f"[{region}] {key}: LỖI {err_str(e)} ({time.time()-t:.2f}s)")
    time.sleep(8)
