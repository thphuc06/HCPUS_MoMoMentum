"""Mục 3: IntentResult qua (a) toolConfig+toolChoice ép tool, (b) outputConfig.textFormat (structured output gốc)."""
import sys, time, json
from common import *
region = sys.argv[1] if len(sys.argv) > 1 else "ap-southeast-1"
keys = sys.argv[2].split(",") if len(sys.argv) > 2 else ["haiku45"]
c = client(region)

INTENTS = ["what_if_purchase", "jar_balance", "spending_summary", "forecast_depletion", "investment_advice", "other"]
SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": INTENTS},
        "params": {"type": "object", "properties": {
            "amount_vnd": {"type": ["integer", "null"], "description": "Số tiền VND, null nếu không nói"},
            "item": {"type": ["string", "null"]},
            "payment_method": {"type": ["string", "null"], "description": "vd: ví trả sau, tiền mặt, thẻ"},
            "jar": {"type": ["string", "null"], "description": "tên hũ: ăn uống, giải trí, tiền trọ..."}},
            "required": ["amount_vnd", "item", "payment_method", "jar"], "additionalProperties": False},
        "confidence": {"type": "number", "description": "0..1"},
        "needs_clarification": {"type": "boolean"},
        "clarification_question": {"type": ["string", "null"]},
    },
    "required": ["intent", "params", "confidence", "needs_clarification", "clarification_question"],
    "additionalProperties": False,
}
SYSTEM = [{"text": "Bạn là bộ phân loại ý định cho trợ lý tài chính cá nhân tiếng Việt. Chỉ phân loại, không trả lời. "
                   "investment_advice dùng cho mọi câu xin khuyến nghị mã cổ phiếu/quỹ/tiền mã hóa. "
                   "Nếu thiếu thông tin cần thiết (vd thiếu món hàng hoặc số tiền cho what_if_purchase) thì needs_clarification=true."}]
UTTS = [
    ("nếu mua tai nghe 1,2 triệu bằng ví trả sau thì sao", dict(intent="what_if_purchase", amount_vnd=1200000, payment_method="ví trả sau", clar=False)),
    ("hũ ăn uống còn bao nhiêu", dict(intent="jar_balance", jar="ăn uống", clar=False)),
    ("nên mua cổ phiếu nào", dict(intent="investment_advice", clar=False)),
    ("cuối tháng hũ giải trí có cạn không", dict(intent="forecast_depletion", jar="giải trí", clar=False)),
    ("mua cái đó thì sao", dict(intent="what_if_purchase", clar=True)),
]

def check(res, exp):
    ok = {}
    ok["intent"] = res.get("intent") == exp["intent"]
    p = res.get("params", {}) or {}
    if "amount_vnd" in exp: ok["amount"] = p.get("amount_vnd") == exp["amount_vnd"]
    if "jar" in exp: ok["jar"] = (p.get("jar") or "").lower().replace("hũ ", "") == exp["jar"]
    if "payment_method" in exp: ok["pay"] = "trả sau" in (p.get("payment_method") or "").lower()
    ok["clar"] = bool(res.get("needs_clarification")) == exp["clar"]
    return ok

results = {}
for k in keys:
    mid = MODELS.get(k, k)
    for mode in ["tool_choice", "output_schema"]:
        rows = []
        for utt, exp in UTTS:
            kw = dict(modelId=mid, system=SYSTEM, messages=[{"role": "user", "content": [{"text": utt}]}], inferenceConfig=({"maxTokens": 700} if "kimi-k3" in mid else {"maxTokens": 500, "temperature": 0}))
            if mode == "tool_choice":
                kw["toolConfig"] = {"tools": [{"toolSpec": {"name": "report_intent", "description": "Báo cáo kết quả phân loại ý định",
                                    "inputSchema": {"json": SCHEMA}}}], "toolChoice": {"tool": {"name": "report_intent"}}}
            else:
                kw["outputConfig"] = {"textFormat": {"type": "json_schema", "structure": {"jsonSchema": {"name": "IntentResult", "schema": json.dumps(SCHEMA)}}}}
            logs = []; t0 = time.perf_counter()
            try:
                r, _ = with_retry(lambda: c.converse(**kw), log=logs)
                dt = time.perf_counter() - t0
                blocks = r["output"]["message"]["content"]
                if mode == "tool_choice":
                    res = next(b["toolUse"]["input"] for b in blocks if "toolUse" in b)
                else:
                    res = json.loads(next(b["text"] for b in blocks if "text" in b))
                rows.append(dict(utt=utt, ok=check(res, exp), result=res, secs=round(dt, 2), usage=r["usage"], stop=r["stopReason"], logs=logs))
            except Exception as e:
                rows.append(dict(utt=utt, error=err_str(e), secs=round(time.perf_counter()-t0, 2), logs=logs))
                print(f"  [{k}/{mode}] LỖI {err_str(e)}", flush=True)
                if mode == "output_schema": break   # cùng lỗi, khỏi lặp
            time.sleep(12 if "anthropic" in mid else 1)
        results[f"{k}/{mode}"] = rows
        good = [r for r in rows if "ok" in r]
        print(f"[{region}] {k}/{mode}: {len(good)}/{len(UTTS)} gọi được; trường đúng: "
              f"{sum(sum(r['ok'].values()) for r in good)}/{sum(len(r['ok']) for r in good)}; median {med([r['secs'] for r in good])}s", flush=True)
        for r in good: print("   ", r["utt"], "=>", json.dumps(r["result"], ensure_ascii=False), r["ok"], flush=True)
json.dump(results, open(f"results_03_tooluse_{region}.json", "w"), ensure_ascii=False, indent=1)
