"""Xóa SẠCH mọi thứ tiền tố yofina-spike-gw- (theo tên, không phụ thuộc state.json), rồi liệt kê lại.
Chạy: uv run python teardown.py"""
import time
from botocore.exceptions import ClientError
from common import *

ac, iam, lam, ddb, cog, logs = (client("bedrock-agentcore-control"), client("iam"), client("lambda"),
                                client("dynamodb"), client("cognito-idp"), client("logs"))


def safe(fn, *a, **k):
    try:
        return fn(*a, **k)
    except ClientError as e:
        print("  !", fn.__name__, e.response["Error"]["Code"], str(e)[:160])


def gateways():
    return [g for g in ac.list_gateways()["items"] if g["name"].startswith(PREFIX)]


def engines():
    return [e for e in ac.list_policy_engines()["policyEngines"] if e["name"].replace("_", "-").startswith(PREFIX)]


def wait_gone(fn, what, tries=40):
    for _ in range(tries):
        if not fn():
            return True
        time.sleep(4)
    print("  ! còn sót:", what)
    return False


def main():
    # 1. gateway: gỡ policy engine trước, xóa target, xóa gateway
    for g in gateways():
        gid = g["gatewayId"]
        print("gateway", g["name"])
        for t in ac.list_gateway_targets(gatewayIdentifier=gid)["items"]:
            safe(ac.delete_gateway_target, gatewayIdentifier=gid, targetId=t["targetId"])
        wait_gone(lambda: ac.list_gateway_targets(gatewayIdentifier=gid)["items"], "targets of " + gid)
        safe(ac.delete_gateway, gatewayIdentifier=gid)
    wait_gone(gateways, "gateways")
    # 2. policy engine: xóa policy rồi engine
    for e in engines():
        eid = e["policyEngineId"]
        print("engine", e["name"])
        for p in ac.list_policies(policyEngineId=eid)["policies"]:
            safe(ac.delete_policy, policyEngineId=eid, policyId=p["policyId"])
        wait_gone(lambda: ac.list_policies(policyEngineId=eid)["policies"], "policies of " + eid)
        safe(ac.delete_policy_engine, policyEngineId=eid)
    wait_gone(engines, "policy engines")
    # 3. Lambda
    for f in lam.list_functions()["Functions"]:
        if f["FunctionName"].startswith(PREFIX):
            print("lambda", f["FunctionName"]); safe(lam.delete_function, FunctionName=f["FunctionName"])
    # 4. log group
    for lg in logs.describe_log_groups(logGroupNamePrefix="/aws/lambda/" + PREFIX)["logGroups"]:
        print("log", lg["logGroupName"]); safe(logs.delete_log_group, logGroupName=lg["logGroupName"])
    for lg in logs.describe_log_groups(logGroupNamePrefix="/aws/vendedlogs/" + PREFIX)["logGroups"]:
        print("log", lg["logGroupName"]); safe(logs.delete_log_group, logGroupName=lg["logGroupName"])
    # 5. DynamoDB
    for t in ddb.list_tables()["TableNames"]:
        if t.startswith(PREFIX):
            print("table", t); safe(ddb.delete_table, TableName=t)
    # 6. Cognito
    for p in cog.list_user_pools(MaxResults=60)["UserPools"]:
        if p["Name"].startswith(PREFIX):
            print("pool", p["Id"]); safe(cog.delete_user_pool, UserPoolId=p["Id"])
    # 7. IAM
    for r in iam.list_roles()["Roles"]:
        if r["RoleName"].startswith(PREFIX):
            n = r["RoleName"]; print("role", n)
            for pn in iam.list_role_policies(RoleName=n)["PolicyNames"]:
                safe(iam.delete_role_policy, RoleName=n, PolicyName=pn)
            for ap in iam.list_attached_role_policies(RoleName=n)["AttachedPolicies"]:
                safe(iam.detach_role_policy, RoleName=n, PolicyArn=ap["PolicyArn"])
            safe(iam.delete_role, RoleName=n)


def verify():
    left = {
        "gateways": [g["name"] for g in gateways()],
        "policy_engines": [e["name"] for e in engines()],
        "lambdas": [f["FunctionName"] for f in lam.list_functions()["Functions"] if f["FunctionName"].startswith(PREFIX)],
        "log_groups": [l["logGroupName"] for l in logs.describe_log_groups(logGroupNamePrefix="/aws/lambda/" + PREFIX)["logGroups"]],
        "tables": [t for t in ddb.list_tables()["TableNames"] if t.startswith(PREFIX)],
        "pools": [p["Name"] for p in cog.list_user_pools(MaxResults=60)["UserPools"] if p["Name"].startswith(PREFIX)],
        "roles": [r["RoleName"] for r in iam.list_roles()["Roles"] if r["RoleName"].startswith(PREFIX)],
    }
    print("CÒN LẠI:", left)
    return not any(left.values())


if __name__ == "__main__":
    main()
    ok = verify()
    with MANIFEST.open("a", encoding="utf-8") as f:
        f.write(f"\n## Kết quả dọn ({time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC)\n\n"
                + ("Đã xóa sạch, liệt kê lại không còn tài nguyên tiền tố `yofina-spike-gw-`.\n" if ok else "CÒN SÓT, xem log teardown.\n"))
    if STATE.exists() and ok:
        STATE.unlink()
