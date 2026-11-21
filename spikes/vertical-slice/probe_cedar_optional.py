"""Phép thử: Cedar `context.input.user_id == principal.id` khi `user_id` là tham số TÙY CHỌN trong schema tool,
**không có interceptor** (để chỉ Cedar quyết định). Dựng tạm một Gateway + policy engine + role riêng (tiền tố
`yofina-probe`), gọi bốn ca, rồi xóa sạch (kể cả khi lỗi).

    uv run spikes/vertical-slice/probe_cedar_optional.py

Tài nguyên tạm (ghi vào docs/aws-resources.md trong lúc tồn tại): role `yofina-probe-gateway`, engine
`yofina_probe_engine`, gateway `yofina-probe-gw`, một target, một policy. Không chạm tài nguyên thật.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests" / "integration"))

from _demo_auth import login_access_token  # noqa: E402
from _yofina import REGION, session, ssm_param  # noqa: E402
from agentcore_helpers import GatewayClient, McpFailure  # noqa: E402

TAG = {"project": "yofina", "purpose": "probe-temporary"}
ROLE = "yofina-probe-gateway"
ENGINE = "yofina_probe_engine"
GW = "yofina-probe-gw"


def wait(fn, ok, bad=("FAILED",), tries=90, sleep=4):
    for _ in range(tries):
        res = fn()
        status = res.get("status", "")
        if status in ok:
            return res
        if any(b in status for b in bad):
            raise RuntimeError(res)
        time.sleep(sleep)
    raise TimeoutError


def main() -> None:
    sess = session()
    ac = sess.client("bedrock-agentcore-control")
    iam = sess.client("iam")
    account = sess.client("sts").get_caller_identity()["Account"]
    real_gid = ssm_param("gateway/id", sess=sess)
    real = ac.get_gateway(gatewayIdentifier=real_gid)
    tools = json.loads((REPO / "contracts" / "tools" / "ledger.json").read_text(encoding="utf-8"))
    ledger_arn = ssm_param("ledger/function-arn", sess=sess)
    cedar_src = (REPO / "gateway" / "policies" / "get_jar_balances.cedar").read_text(
        encoding="utf-8"
    )
    cedar_src = "\n".join(l for l in cedar_src.splitlines() if not l.lstrip().startswith("//"))

    created: dict[str, str] = {}
    results: list[dict] = []
    try:
        trust = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                    "Condition": {
                        "StringEquals": {"aws:SourceAccount": account},
                        "ArnLike": {
                            "aws:SourceArn": f"arn:aws:bedrock-agentcore:{REGION}:{account}:gateway/*"
                        },
                    },
                }
            ],
        }
        iam.create_role(
            RoleName=ROLE,
            AssumeRolePolicyDocument=json.dumps(trust),
            Tags=[{"Key": k, "Value": v} for k, v in TAG.items()],
        )
        created["role"] = ROLE
        iam.put_role_policy(
            RoleName=ROLE,
            PolicyName="inline",
            PolicyDocument=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": "lambda:InvokeFunction",
                            "Resource": ledger_arn,
                        },
                        {
                            "Effect": "Allow",
                            "Action": [
                                "bedrock-agentcore:GetPolicyEngine",
                                "bedrock-agentcore:AuthorizeAction",
                                "bedrock-agentcore:PartiallyAuthorizeActions",
                            ],
                            "Resource": [
                                f"arn:aws:bedrock-agentcore:{REGION}:{account}:policy-engine/*",
                                f"arn:aws:bedrock-agentcore:{REGION}:{account}:gateway/*",
                            ],
                        },
                    ],
                }
            ),
        )
        time.sleep(12)  # IAM lan truyền

        eng = ac.create_policy_engine(name=ENGINE, tags=TAG)
        created["engine"] = eng["policyEngineId"]
        wait(lambda: ac.get_policy_engine(policyEngineId=created["engine"]), ("ACTIVE",))

        gw = ac.create_gateway(
            name=GW,
            roleArn=f"arn:aws:iam::{account}:role/{ROLE}",
            protocolType="MCP",
            authorizerType="CUSTOM_JWT",
            authorizerConfiguration=real["authorizerConfiguration"],
            policyEngineConfiguration={"arn": eng["policyEngineArn"], "mode": "ENFORCE"},
            exceptionLevel="DEBUG",
            tags=TAG,
        )
        created["gateway"] = gw["gatewayId"]
        gw = wait(lambda: ac.get_gateway(gatewayIdentifier=created["gateway"]), ("READY",))
        tgt = ac.create_gateway_target(
            gatewayIdentifier=created["gateway"],
            name="ledger",
            targetConfiguration={
                "mcp": {"lambda": {"lambdaArn": ledger_arn, "toolSchema": {"inlinePayload": tools}}}
            },
            credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}],
        )
        created["target"] = tgt["targetId"]
        wait(
            lambda: ac.get_gateway_target(
                gatewayIdentifier=created["gateway"], targetId=created["target"]
            ),
            ("READY",),
        )
        statement = cedar_src.replace("${GATEWAY_ARN}", gw["gatewayArn"])
        pol = ac.create_policy(
            policyEngineId=created["engine"],
            name="probe_get_jar_balances",
            definition={"cedar": {"statement": statement}},
            validationMode="FAIL_ON_ANY_FINDINGS",
        )
        created["policy"] = pol["policyId"]
        got = wait(
            lambda: ac.get_policy(policyEngineId=created["engine"], policyId=created["policy"]),
            ("ACTIVE",),
            bad=("FAILED",),
        )
        results.append(
            {
                "case": "policy tạo được với user_id TÙY CHỌN + `has` (FAIL_ON_ANY_FINDINGS)",
                "status": got["status"],
            }
        )
        time.sleep(10)

        minh, lan = login_access_token("minh", sess=sess), login_access_token("lan", sess=sess)
        import base64

        def sub(tok: str) -> str:
            return json.loads(base64.urlsafe_b64decode(tok.split(".")[1] + "=="))["sub"]

        client = GatewayClient(gw["gatewayUrl"], minh)
        cases = [
            ("user_id = sub của chính mình", {"user_id": sub(minh)}),
            ("user_id = sub của người khác", {"user_id": sub(lan)}),
            ("bỏ user_id (tùy chọn, vắng)", {}),
            ("user_id rỗng", {"user_id": ""}),
        ]
        for label, args in cases:
            try:
                reply = client.call("ledger___get_jar_balances", args)
                results.append({"case": label, "outcome": "ALLOWED", "status": reply.status})
            except McpFailure as exc:
                results.append(
                    {
                        "case": label,
                        "outcome": "DENIED",
                        "code": exc.code,
                        "message": exc.message[:300],
                    }
                )
    finally:
        for step, fn in (
            (
                "policy",
                lambda: ac.delete_policy(
                    policyEngineId=created["engine"], policyId=created["policy"]
                ),
            ),
            (
                "target",
                lambda: ac.delete_gateway_target(
                    gatewayIdentifier=created["gateway"], targetId=created["target"]
                ),
            ),
        ):
            if step in created:
                try:
                    fn()
                    time.sleep(6)
                except Exception as exc:  # noqa: BLE001
                    print("dọn", step, "lỗi", repr(exc)[:200], file=sys.stderr)
        for _ in range(30):
            try:
                if "gateway" in created:
                    ac.delete_gateway(gatewayIdentifier=created["gateway"])
                break
            except Exception as exc:  # noqa: BLE001 - target/policy đang xóa
                time.sleep(5)
                last = exc
        else:
            print("không xóa được gateway", repr(last)[:200], file=sys.stderr)
        for _ in range(20):
            try:
                if "engine" in created:
                    ac.delete_policy_engine(policyEngineId=created["engine"])
                break
            except Exception:  # noqa: BLE001
                time.sleep(5)
        if "role" in created:
            try:
                iam.delete_role_policy(RoleName=ROLE, PolicyName="inline")
                iam.delete_role(RoleName=ROLE)
            except Exception as exc:  # noqa: BLE001
                print("dọn role lỗi", repr(exc)[:200], file=sys.stderr)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    (REPO / "spikes" / "vertical-slice" / "out").mkdir(exist_ok=True)
    (REPO / "spikes" / "vertical-slice" / "out" / "probe_cedar_optional.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
