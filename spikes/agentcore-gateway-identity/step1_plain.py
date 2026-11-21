"""Q1/Q2: gateway trơn (JWT Cognito, không interceptor/policy) + target ledger; list/call bằng JWT user A."""
import json, sys
from gw import *
from mcpcall import *

st = load_state()
if "plain" not in st.get("gateways", {}):
    g = create_gateway("plain")
    t = create_target(g["gatewayId"])
    print("target:", t["status"], t.get("statusReasons"))
st = load_state()
G = st["gateways"]["plain"]
print("URL", G["url"])
tk = tokens()
A, B = tk["user-a"], tk["user-b"]
print("claims access token A:", {k: (v if k != "sub" else "<sub>") for k, v in claims(A["access"]).items()})
print("claims id token A:", {k: (v if k not in ("sub", "cognito:username") else "<...>") for k, v in claims(A["id"]).items()})

gw = Gw(G["url"], A["access"])
tl = gw.list_tools()
print("TOOLS/LIST:", json.dumps(tl.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=1))
r = gw.call("ledger___get_jar_balances", {"user_id": A["sub"]})
print("CALL isError:", r.isError)
print(r.content[0].text if r.content else r)
# thử với id token (không có client_id) và không token
print("id token:", raw_post(G["url"], A["id"], {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})[:2])
print("no token:", raw_post(G["url"], "", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})[:2])
