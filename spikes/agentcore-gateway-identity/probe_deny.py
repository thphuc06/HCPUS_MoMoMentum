import json
from gw import *
from mcpcall import *
from step2_interceptor import G
tk = tokens(); A, B = tk["user-a"], tk["user-b"]
def call(args, name="ledger___get_jar_balances"):
    return raw_post(G["url"], A["access"], {"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":name,"arguments":args}})
for label, nm, a in [("A đọc của B","ledger___get_jar_balances",{"user_id":B["sub"]}),
                  ("ghi vượt hạn mức","ledger___move_between_jars",{"user_id":A["sub"],"from_jar":"x","to_jar":"y","amount_vnd":9000000,"user_confirmed":True}),
                  ("tool không tồn tại","ledger___nope",{}),
                  ("A đọc của A","ledger___get_jar_balances",{"user_id":A["sub"]})]:
    s, body, ms = call(a, nm)
    print(label, s, f"{ms:.0f}ms", body[:600])
# tools/list khi enforce
s, body, ms = raw_post(G["url"], A["access"], {"jsonrpc":"2.0","id":1,"method":"tools/list"})
print("tools/list", s, [t["name"] for t in json.loads(body)["result"]["tools"]])
