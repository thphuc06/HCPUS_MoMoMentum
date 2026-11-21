"""Header precedence + user_id không có trong schema (LLM không thấy) nhưng interceptor tiêm vào."""
import json, time
from gw import *
from mcpcall import *
from step2_interceptor import G, set_mode
set_mode("overwrite")
gid = G["id"]
gw_arn = ac.get_gateway(gatewayIdentifier=gid)["gatewayArn"]
eid = load_state()["engine"]["id"]
HID = [{"name": "get_jar_balances", "description": "Số dư hũ của người dùng hiện tại (không cần tham số)",
        "inputSchema": {"type": "object", "properties": {}}}]
if "hidden_target" not in load_state():
    t = create_target(gid, name="ledgerx", tools=HID)
    print("target ledgerx:", t["status"], t.get("statusReasons"))
    save_state(hidden_target=t["targetId"])
    p = create_policy(eid, "read_hidden_any_authenticated", f'''permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"ledgerx___get_jar_balances",
  resource == AgentCore::Gateway::"{gw_arn}"
);''')
    print("policy:", p["status"], p.get("statusReasons")); time.sleep(8)
tk = tokens(); A, B = tk["user-a"], tk["user-b"]
def call(nm, a, extra=None):
    s, body, ms = raw_post(G["url"], A["access"], {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":nm,"arguments":a}}, extra)
    j = json.loads(body)
    if "error" in j: return {"HTTP": s, "error": j["error"]}
    r = j["result"]
    if r.get("isError"): return {"isError": r["content"][0]["text"][:300]}
    inner = json.loads(r["content"][0]["text"])
    return {"event": inner["dump"]["event"], "propagated": inner["dump"]["client_context"]["custom"].get("bedrockAgentCorePropagatedHeaders"), "A_is": A["sub"]==inner["dump"]["event"].get("user_id")}
print("interceptor + client gửi x-user-id=B ->", call("ledger___get_jar_balances", {"user_id": B["sub"]}, {"x-user-id": B["sub"]}))
print("ledgerx (schema không có user_id), args {} ->", call("ledgerx___get_jar_balances", {}))
print("ledgerx, LLM cố nhét user_id=B ->", call("ledgerx___get_jar_balances", {"user_id": B["sub"]}))
print("tools/list thấy gì:", [ (t["name"], list(t["inputSchema"].get("properties",{}))) for t in json.loads(raw_post(G["url"], A["access"], {"jsonrpc":"2.0","id":1,"method":"tools/list"})[1])["result"]["tools"]])
