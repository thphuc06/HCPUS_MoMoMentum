"""Q7: gateway bật searchType SEMANTIC: tools/list khác gì, tool x_amz_bedrock_agentcore_search."""
import json, time
from gw import *
from mcpcall import *

st = load_state()
if "sem" not in st.get("gateways", {}):
    g = create_gateway("sem", semantic=True)
    t = create_target(g["gatewayId"])
    print("target ledger:", t["status"], t.get("statusReasons"))
    extra = [{"name": n, "description": d, "inputSchema": {"type": "object", "properties": {"user_id": {"type": "string"}}}}
             for n, d in (("get_forecast", "Dự báo dòng tiền 30 ngày tới của người dùng"),
                          ("list_goals", "Danh sách mục tiêu tiết kiệm và tiến độ"),
                          ("explain_spending", "Giải thích vì sao chi tiêu tháng này tăng so với tháng trước"))]
    t2 = create_target(g["gatewayId"], name="planner", tools=extra, headers=None)
    print("target planner:", t2["status"], t2.get("statusReasons"))
    time.sleep(10)
G = load_state()["gateways"]["sem"]
tk = tokens(); A = tk["user-a"]
s, body, ms = raw_post(G["url"], A["access"], {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
j = json.loads(body)
print("tools/list:", [t["name"] for t in j["result"]["tools"]], "| nextCursor:", j["result"].get("nextCursor"))
print(json.dumps([t for t in j["result"]["tools"] if t["name"].startswith("x_amz")], ensure_ascii=False, indent=1)[:1500])
for q in ("chuyển tiền giữa các hũ", "xem số dư", "tại sao tôi tiêu nhiều hơn", "mục tiêu tiết kiệm"):
    t0 = time.perf_counter()
    s, body, ms = raw_post(G["url"], A["access"], {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                                    "params": {"name": "x_amz_bedrock_agentcore_search", "arguments": {"query": q}}})
    j = json.loads(body)
    try:
        res = j["result"]
        txt = res.get("structuredContent") or json.loads(res["content"][0]["text"])
        names = [t["name"] for t in (txt.get("tools") if isinstance(txt, dict) else txt)]
    except Exception:
        names = body[:300]
    print(f"search '{q}' ({ms:.0f}ms) ->", names)
# gọi tool bình thường qua gateway semantic vẫn chạy?
s, body, ms = raw_post(G["url"], A["access"], {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                                "params": {"name": "ledger___get_jar_balances", "arguments": {"user_id": A["sub"]}}})
print("call ledger___get_jar_balances qua gateway semantic:", s, "isError" in body and json.loads(body)["result"]["isError"])
