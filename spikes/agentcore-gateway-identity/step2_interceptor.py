"""Q3a: gateway 'main' với request interceptor. A gọi với user_id của B; xem ledger nhận gì (ghi đè? header?)."""
import json, time
from gw import *
from mcpcall import *

lam = client("lambda")
st = load_state()
if "main" not in st.get("gateways", {}):
    g = create_gateway("main", interceptors=interceptor_cfg(True))
    t = create_target(g["gatewayId"])
    print("target:", t["status"], t.get("statusReasons"))
G = load_state()["gateways"]["main"]


def set_mode(mode):
    lam.update_function_configuration(FunctionName=PREFIX + "interceptor", Environment={"Variables": {"MODE": mode}})
    lam.get_waiter("function_updated_v2").wait(FunctionName=PREFIX + "interceptor")
    time.sleep(1)


def show(r):
    t = r.content[0].text if r.content else ""
    try:
        j = json.loads(t)
        d = j["dump"]
        return {"isError": r.isError, "ledger_event": d["event"], "propagated": d["client_context"]["custom"].get("bedrockAgentCorePropagatedHeaders"),
                "result": j["result"]}
    except Exception:
        return {"isError": r.isError, "text": t}


if __name__ == "__main__":
    tk = tokens(); A, B = tk["user-a"], tk["user-b"]
    gw = Gw(G["url"], A["access"])
    for mode in ("passthrough", "overwrite", "deny"):
        set_mode(mode)
        print(f"\n=== MODE={mode}: A gọi get_jar_balances với user_id của B")
        print(json.dumps(show(gw.call("ledger___get_jar_balances", {"user_id": B["sub"]})), ensure_ascii=False, indent=1))
    set_mode("overwrite")
    print("\n=== MODE=overwrite: A gọi get_jar_balances với user_id='' / thiếu user_id")
    try:
        print(json.dumps(show(gw.call("ledger___get_jar_balances", {})), ensure_ascii=False, indent=1))
    except Exception as e:
        print("exc", e)
    print("\n=== MODE=overwrite: A gọi move_between_jars, user_id=B, user_confirmed=true")
    print(json.dumps(show(gw.call("ledger___move_between_jars", {"user_id": B["sub"], "from_jar": "a", "to_jar": "b", "amount_vnd": 100000, "user_confirmed": True})), ensure_ascii=False, indent=1))
