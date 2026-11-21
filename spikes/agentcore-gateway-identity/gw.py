"""Tạo/chờ Gateway, target, policy engine, policy. Dùng bởi setup và các script test."""
import time
from botocore.exceptions import ClientError
from common import *

ac = client("bedrock-agentcore-control")

TOOLS = [
    {"name": "get_jar_balances",
     "description": "Số dư từng hũ của người dùng",
     "inputSchema": {"type": "object",
                     "properties": {"user_id": {"type": "string", "description": "sub của JWT"}},
                     "required": ["user_id"]}},
    {"name": "move_between_jars",
     "description": "Chuyển tiền giữa hai hũ (ghi giả, chỉ log)",
     "inputSchema": {"type": "object",
                     "properties": {"user_id": {"type": "string"}, "from_jar": {"type": "string"}, "to_jar": {"type": "string"},
                                    "amount_vnd": {"type": "integer"}, "user_confirmed": {"type": "boolean"},
                                    "confirm_token": {"type": "string"}},
                     "required": ["user_id", "from_jar", "to_jar", "amount_vnd", "user_confirmed"]}},
]


def role_arn():
    return f"arn:aws:iam::{account()}:role/{PREFIX}gateway-role"


def lambda_arn(short):
    return f"arn:aws:lambda:{REGION}:{account()}:function:{PREFIX}{short}"


def jwt_cfg():
    st = load_state()
    return {"customJWTAuthorizer": {
        "discoveryUrl": f"https://cognito-idp.{REGION}.amazonaws.com/{st['pool_id']}/.well-known/openid-configuration",
        "allowedClients": [st["client_id"]]}}


def interceptor_cfg(headers=True):
    return [{"interceptor": {"lambda": {"arn": lambda_arn("interceptor")}}, "interceptionPoints": ["REQUEST"],
             "inputConfiguration": {"passRequestHeaders": headers}}]


def wait_gw(gid, want="READY"):
    for _ in range(60):
        g = ac.get_gateway(gatewayIdentifier=gid)
        if g["status"] == want:
            return g
        if g["status"].endswith("FAILED"):
            raise RuntimeError(g)
        time.sleep(3)
    raise TimeoutError(gid)


def create_gateway(short, semantic=False, interceptors=None, engine=None, exception_debug=True):
    kw = dict(name=PREFIX + short, roleArn=role_arn(), protocolType="MCP", authorizerType="CUSTOM_JWT",
              authorizerConfiguration=jwt_cfg(), tags=TAGS)
    if semantic:
        kw["protocolConfiguration"] = {"mcp": {"searchType": "SEMANTIC"}}
    if interceptors:
        kw["interceptorConfigurations"] = interceptors
    if engine:
        kw["policyEngineConfiguration"] = engine
    if exception_debug:
        kw["exceptionLevel"] = "DEBUG"
    g = ac.create_gateway(**kw)
    gid = g["gatewayId"]
    record("AgentCore Gateway", gid, f"aws bedrock-agentcore-control delete-gateway --gateway-identifier {gid} --region {REGION}  (xóa target trước)")
    g = wait_gw(gid)
    st = load_state()
    st.setdefault("gateways", {})[short] = {"id": gid, "url": g["gatewayUrl"]}
    save_state(**st)
    return g


def update_gateway(gid, **over):
    """UpdateGateway cần truyền lại mọi trường: lấy hiện trạng rồi ghi đè phần đổi."""
    g = ac.get_gateway(gatewayIdentifier=gid)
    kw = dict(gatewayIdentifier=gid, name=g["name"], roleArn=g["roleArn"], protocolType=g["protocolType"],
              authorizerType=g["authorizerType"], authorizerConfiguration=g["authorizerConfiguration"])
    for k in ("protocolConfiguration", "interceptorConfigurations", "policyEngineConfiguration", "exceptionLevel", "description"):
        if k in g:
            kw[k] = g[k]
    kw.update(over)
    for k in [k for k, v in kw.items() if v is None]:
        del kw[k]
    ac.update_gateway(**kw)
    time.sleep(2)
    return wait_gw(gid)


def create_target(gid, name="ledger", tools=None, headers=("x-user-id",), fn="ledger"):
    kw = dict(gatewayIdentifier=gid, name=name,
              targetConfiguration={"mcp": {"lambda": {"lambdaArn": lambda_arn(fn), "toolSchema": {"inlinePayload": tools or TOOLS}}}},
              credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}])
    if headers:
        kw["metadataConfiguration"] = {"allowedRequestHeaders": list(headers)}
    t = ac.create_gateway_target(**kw)
    tid = t["targetId"]
    record("Gateway target", f"{gid}/{tid} ({name})", "xóa cùng gateway (delete-gateway-target trước)")
    for _ in range(60):
        t = ac.get_gateway_target(gatewayIdentifier=gid, targetId=tid)
        if t["status"] in ("READY", "FAILED", "UPDATE_UNSUCCESSFUL", "CREATE_UNSUCCESSFUL"):
            return t
        time.sleep(3)
    return t


def create_engine(short):
    name = (PREFIX + short).replace("-", "_")      # tên engine: [A-Za-z][A-Za-z0-9_]*
    e = ac.create_policy_engine(name=name, tags=TAGS)
    eid = e["policyEngineId"]
    record("Policy engine", eid, f"aws bedrock-agentcore-control delete-policy-engine --policy-engine-id {eid} --region {REGION}  (xóa policy trước)")
    for _ in range(60):
        e = ac.get_policy_engine(policyEngineId=eid)
        if e["status"] == "ACTIVE":
            break
        time.sleep(3)
    return e


def create_policy(eid, name, cedar, mode=None, validation="FAIL_ON_ANY_FINDINGS"):
    kw = dict(policyEngineId=eid, name=name, definition={"cedar": {"statement": cedar}}, validationMode=validation)
    p = ac.create_policy(**kw)
    pid = p["policyId"]
    record("Policy", f"{eid}/{pid} ({name})", "xóa trước policy engine (delete-policy)")
    for _ in range(60):
        p = ac.get_policy(policyEngineId=eid, policyId=pid)
        if p["status"] in ("ACTIVE", "CREATE_FAILED"):
            return p
        time.sleep(3)
    return p
