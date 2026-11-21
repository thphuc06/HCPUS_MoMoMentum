import json, sys
from gw import *
from mcpcall import *
from step2_interceptor import G, set_mode
set_mode(sys.argv[1])
tk = tokens(); A, B = tk["user-a"], tk["user-b"]
def call(nm, a):
    s, body, ms = raw_post(G["url"], A["access"], {"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":nm,"arguments":a}})
    try:
        j = json.loads(body)
        if "error" in j: return s, j["error"]
        inner = json.loads(j["result"]["content"][0]["text"]) if not j["result"].get("isError") else j["result"]
        return s, {"ledger_event": inner["dump"]["event"], "result": inner["result"]} if "dump" in inner else inner
    except Exception: return s, body[:300]
print("mode", sys.argv[1])
print("A đọc user_id=B   ->", call("ledger___get_jar_balances", {"user_id": B["sub"]}))
print("A đọc không user_id ->", call("ledger___get_jar_balances", {}))
print("A ghi user_id=B, confirmed, 100k ->", call("ledger___move_between_jars", {"user_id": B["sub"],"from_jar":"x","to_jar":"y","amount_vnd":100000,"user_confirmed":True}))
print("A ghi user_id=A, user_confirmed=False ->", call("ledger___move_between_jars", {"user_id": A["sub"],"from_jar":"x","to_jar":"y","amount_vnd":100000,"user_confirmed":False}))
print("A ghi thiếu user_confirmed (field required) ->", call("ledger___move_between_jars", {"user_id": A["sub"],"from_jar":"x","to_jar":"y","amount_vnd":100000}))
print("A đọc user_id kiểu số (sai kiểu) ->", call("ledger___get_jar_balances", {"user_id": 123}))
