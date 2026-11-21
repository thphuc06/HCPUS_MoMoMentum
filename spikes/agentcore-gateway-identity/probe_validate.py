"""Gateway có kiểm inputSchema không; header client gửi có tới Lambda không (plain, không interceptor)."""
import json
from gw import *
from mcpcall import *
G = load_state()["gateways"]["plain"]
tk = tokens(); A, B = tk["user-a"], tk["user-b"]
def call(nm, a, extra=None, token=None):
    s, body, ms = raw_post(G["url"], token or A["access"], {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":nm,"arguments":a}}, extra)
    j = json.loads(body)
    if "error" in j: return {"HTTP": s, "error": j["error"]}
    r = j["result"]
    if r.get("isError"): return {"isError": r["content"][0]["text"][:300]}
    inner = json.loads(r["content"][0]["text"])
    return {"event": inner["dump"]["event"], "propagated": inner["dump"]["client_context"]["custom"].get("bedrockAgentCorePropagatedHeaders"), "result": inner["result"]}
print("thiếu user_id (required)   ->", call("ledger___get_jar_balances", {}))
print("user_id kiểu số            ->", call("ledger___get_jar_balances", {"user_id": 123}))
print("tham số thừa 'evil'        ->", call("ledger___get_jar_balances", {"user_id": A["sub"], "evil": "x"}))
print("amount_vnd là chuỗi        ->", call("ledger___move_between_jars", {"user_id": A["sub"], "from_jar":"a","to_jar":"b","amount_vnd":"100","user_confirmed":True}))
print("amount_vnd là số thực 1.5  ->", call("ledger___move_between_jars", {"user_id": A["sub"], "from_jar":"a","to_jar":"b","amount_vnd":1.5,"user_confirmed":True}))
print("user_confirmed là chuỗi 'true' ->", call("ledger___move_between_jars", {"user_id": A["sub"], "from_jar":"a","to_jar":"b","amount_vnd":1,"user_confirmed":"true"}))
print("client gửi header x-user-id=B (target cho phép allowlist) ->", call("ledger___get_jar_balances", {"user_id": A["sub"]}, {"x-user-id": B["sub"]}))
print("client gửi header x-other (không allowlist)  ->", call("ledger___get_jar_balances", {"user_id": A["sub"]}, {"x-other": "zzz"}))
