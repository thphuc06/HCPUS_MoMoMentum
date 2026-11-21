"""Q3b/Q4/Q5 bổ sung: claim là tag (hasTag/getTag), có `sub` làm tag không; Cedar kiểm sự hiện diện confirm_token;
enforcementMode theo từng policy."""
import json, time
from gw import *
from mcpcall import *
from step2_interceptor import G, set_mode
from step5_confirm import issue, call, set_env

gid = G["id"]; eid = load_state()["engine"]["id"]
arn = ac.get_gateway(gatewayIdentifier=gid)["gatewayArn"]
set_mode("overwrite"); set_env("ledger", REQUIRE_TOKEN="1")
tk = tokens(); A, B = tk["user-a"], tk["user-b"]
READ = "ledger___get_jar_balances"; MOVE = "ledger___move_between_jars"


def drop(name):
    for p in ac.list_policies(policyEngineId=eid)["policies"]:
        if p["name"] == name:
            ac.delete_policy(policyEngineId=eid, policyId=p["policyId"])
            for _ in range(30):
                if not any(x["name"] == name for x in ac.list_policies(policyEngineId=eid)["policies"]): break
                time.sleep(2)


def pol(name):
    return next(p for p in ac.list_policies(policyEngineId=eid)["policies"] if p["name"] == name)


print("=== 1. claim làm tag")
create = create_policy(eid, "forbid_username_user_b", f'''forbid(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"{READ}",
  resource == AgentCore::Gateway::"{arn}"
) when {{
  principal.hasTag("username") && principal.getTag("username") == "user-b"
}};''')
print("policy tag username:", create["status"], create.get("statusReasons")); time.sleep(8)
print("  A đọc (username=user-a):", call(A["access"], READ, {"user_id": A["sub"]}))
print("  B đọc (username=user-b):", call(B["access"], READ, {"user_id": B["sub"]}))
drop("forbid_username_user_b"); time.sleep(8)
c2 = create_policy(eid, "forbid_if_has_sub_tag", f'''forbid(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"{READ}",
  resource == AgentCore::Gateway::"{arn}"
) when {{
  principal.hasTag("sub")
}};''')
print("policy hasTag('sub'):", c2["status"], c2.get("statusReasons")); time.sleep(8)
print("  A đọc khi forbid-if-has-sub-tag:", call(A["access"], READ, {"user_id": A["sub"]}), "(nếu bị chặn => sub là tag)")
drop("forbid_if_has_sub_tag"); time.sleep(8)

print("=== 2. Cedar kiểm sự hiện diện/định dạng confirm_token")
p = pol("write_confirmed_within_limit")
new = f'''permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"{MOVE}",
  resource == AgentCore::Gateway::"{arn}"
) when {{
  context.input.user_id == principal.id &&
  context.input.user_confirmed &&
  context.input.amount_vnd <= 5000000 &&
  context.input has confirm_token &&
  context.input.confirm_token like "*.*"
}};'''
ac.update_policy(policyEngineId=eid, policyId=p["policyId"], definition={"cedar": {"statement": new}}, validationMode="FAIL_ON_ANY_FINDINGS")
for _ in range(30):
    g = ac.get_policy(policyEngineId=eid, policyId=p["policyId"])
    if g["status"] in ("ACTIVE", "UPDATE_FAILED"): break
    time.sleep(2)
print("update policy:", g["status"], g.get("statusReasons")); time.sleep(8)
base = {"user_id": A["sub"], "from_jar": "tiet_kiem", "to_jar": "thiet_yeu", "amount_vnd": 300000, "user_confirmed": True}
print("  không có confirm_token       ->", call(A["access"], MOVE, base))
print("  token 'abc' (không có dấu .) ->", call(A["access"], MOVE, dict(base, confirm_token="abc")))
print("  token bịa 'abc.def'          ->", call(A["access"], MOVE, dict(base, confirm_token="abc.def")))
tok = issue(A["access"], {k: base[k] for k in ("from_jar", "to_jar", "amount_vnd")})["confirm_token"]
print("  token thật                   ->", call(A["access"], MOVE, dict(base, confirm_token=tok)))

print("=== 3. enforcementMode LOG_ONLY theo từng policy (engine vẫn ENFORCE)")
ac.update_policy(policyEngineId=eid, policyId=p["policyId"], enforcementMode="LOG_ONLY")
time.sleep(10)
print("  policy mode:", ac.get_policy(policyEngineId=eid, policyId=p["policyId"]).get("enforcementMode"))
print("  ghi không token (Cedar không chặn nữa vì không có policy ACTIVE nào permit...) ->", call(A["access"], MOVE, base))
ac.update_policy(policyEngineId=eid, policyId=p["policyId"], enforcementMode="ACTIVE"); time.sleep(10)
print("  trả về ACTIVE ->", call(A["access"], MOVE, base))
