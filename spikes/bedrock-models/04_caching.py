"""Mục 4: prompt caching (cachePoint sau system prompt dài). Gọi 2 lần mỗi cỡ prompt, đọc usage.cache*."""
import sys, time, json, uuid
from common import *
region = sys.argv[1] if len(sys.argv) > 1 else "ap-southeast-1"
plan = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {"haiku45": [3000, 4500], "sonnet46": [700, 1300]}
c = client(region)

PARAS = [
 "Quy tắc {i}: khi người dùng hỏi về hũ chi tiêu số {i}, luôn dùng số liệu từ công cụ ledger, không tự bịa; làm tròn số tiền đến nghìn đồng và viết dạng 1.200.000 đ.",
 "Ví dụ {i}: người dùng nói 'mua tai nghe {i}00 nghìn bằng ví trả sau thì sao' thì phân loại thành what_if_purchase, amount_vnd={i}00000, payment_method='ví trả sau'.",
]
def build_system(target_tokens, nonce):
    """Tạo system prompt tiếng Việt đủ dài; kiểm số token bằng count_tokens (nếu có) hoặc ước lượng sau lần gọi đầu."""
    head = f"[phiên {nonce}] Bạn là trợ lý tài chính cá nhân Yofina (dữ liệu hư cấu). Trả lời ngắn gọn bằng tiếng Việt.\n"
    n = max(1, target_tokens // 55)
    while True:
        txt = head + "\n".join(PARAS[i % 2].format(i=i) for i in range(n))
        try:
            tk = c.count_tokens(modelId=MODELS_FOR_COUNT, input={"converse": {"messages": [{"role": "user", "content": [{"text": "Xin chào"}]}], "system": [{"text": txt}]}})["inputTokens"]
        except Exception:
            return txt, None
        if tk >= target_tokens or n > 400: return txt, tk
        n = int(n * max(1.05, target_tokens / max(tk, 1)))

results = {}
for k, sizes in plan.items():
    mid = MODELS.get(k, k); MODELS_FOR_COUNT = mid
    for sz in sizes:
        sysmsg, tk = build_system(sz, uuid.uuid4().hex[:8])
        rows = []
        for call in (1, 2):
            logs = []
            kw = dict(modelId=mid, system=[{"text": sysmsg}, {"cachePoint": {"type": "default"}}],
                      messages=[{"role": "user", "content": [{"text": "Xin chào, trả lời đúng một từ."}]}], inferenceConfig={"maxTokens": 10, "temperature": 0})
            try:
                pace(k)
                r, _ = with_retry(lambda: c.converse(**kw), log=logs)
                u = r["usage"]; rows.append(dict(call=call, usage=u, retry=logs))
            except Exception as e:
                rows.append(dict(call=call, error=err_str(e), retry=logs))
        results[f"{k}@~{sz}"] = dict(counted_tokens=tk, rows=rows)
        print(f"[{region}] {k} mục tiêu {sz} (count_tokens={tk}):", flush=True)
        for r in rows:
            u = r.get("usage"); print("   ", r["call"], u or r.get("error"), ("total_in=%d" % (u["inputTokens"] + u.get("cacheReadInputTokens", 0) + u.get("cacheWriteInputTokens", 0))) if u else "", flush=True)
json.dump(results, open(f"results_04_caching_{region}.json", "w"), ensure_ascii=False, indent=1)
