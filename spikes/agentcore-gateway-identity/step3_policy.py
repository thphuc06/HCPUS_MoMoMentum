"""Q3b/Q4: policy engine + luật Cedar; thử LOG_ONLY rồi ENFORCE; thứ tự interceptor so với policy."""
import json, sys, time
from gw import *
from mcpcall import *
from step2_interceptor import set_mode, show, G, lam

st = load_state()
gid = G["id"]
gw_arn = ac.get_gateway(gatewayIdentifier=gid)["gatewayArn"]

READ = f'''permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"ledger___get_jar_balances",
  resource == AgentCore::Gateway::"{gw_arn}"
) when {{
  context.input.user_id == principal.id
}};'''

WRITE = f'''permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"ledger___move_between_jars",
  resource == AgentCore::Gateway::"{gw_arn}"
) when {{
  context.input.user_id == principal.id &&
  context.input.user_confirmed &&
  context.input.amount_vnd <= 5000000
}};'''


def setup():
    if "engine" not in load_state():
        e = create_engine("pe")
        save_state(engine={"id": e["policyEngineId"], "arn": e["policyEngineArn"]})
    eid = load_state()["engine"]["id"]
    out = {}
    for name, cedar in (("read_own_balances", READ), ("write_confirmed_within_limit", WRITE)):
        p = create_policy(eid, name, cedar)
        out[name] = (p["status"], p.get("statusReasons"))
        print(name, p["status"], p.get("statusReasons"))
    return out


def attach(mode):
    eng = load_state()["engine"]
    update_gateway(gid, policyEngineConfiguration={"arn": eng["arn"], "mode": mode})
    time.sleep(8)           # nhất quán cuối cùng


def calls(label, A, B):
    gw = Gw(G["url"], A["access"])
    cases = [
        ("A đọc của A", "ledger___get_jar_balances", {"user_id": A["sub"]}),
        ("A đọc của B", "ledger___get_jar_balances", {"user_id": B["sub"]}),
        ("A ghi của A, confirmed, 100k", "ledger___move_between_jars", {"user_id": A["sub"], "from_jar": "x", "to_jar": "y", "amount_vnd": 100000, "user_confirmed": True}),
        ("A ghi của A, chưa confirm", "ledger___move_between_jars", {"user_id": A["sub"], "from_jar": "x", "to_jar": "y", "amount_vnd": 100000, "user_confirmed": False}),
        ("A ghi của A, confirmed, 9tr (vượt hạn mức)", "ledger___move_between_jars", {"user_id": A["sub"], "from_jar": "x", "to_jar": "y", "amount_vnd": 9000000, "user_confirmed": True}),
        ("A ghi của B, confirmed", "ledger___move_between_jars", {"user_id": B["sub"], "from_jar": "x", "to_jar": "y", "amount_vnd": 100000, "user_confirmed": True}),
    ]
    print(f"\n######## {label}")
    for name, tool, args in cases:
        try:
            r = gw.call(tool, args)
            s = show(r)
            print(f"- {name}: isError={s.get('isError')} ", s.get("text") or (s.get("result")))
        except Exception as ex:
            print(f"- {name}: EXC {type(ex).__name__}: {str(ex)[:400]}")


if __name__ == "__main__":
    step = sys.argv[1]
    if step == "setup":
        setup()
    else:
        tk = tokens(); A, B = tk["user-a"], tk["user-b"]
        if step == "logonly":
            set_mode("passthrough"); attach("LOG_ONLY"); calls("LOG_ONLY, interceptor passthrough", A, B)
        elif step == "enforce":
            set_mode("passthrough"); attach("ENFORCE"); calls("ENFORCE, interceptor passthrough", A, B)
        elif step == "order":
            set_mode("overwrite"); attach("ENFORCE"); calls("ENFORCE, interceptor overwrite (thứ tự)", A, B)
