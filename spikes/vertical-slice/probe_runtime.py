"""Phép thử Runtime thật cho hai điểm "Chưa thử": interrupt/resume AG-UI với session manager bền, và token hết hạn
giữa luồng SSE. Dựng một Runtime THỬ riêng (`yofina_probe`, platform V1 để tạo nhanh), KHÔNG đụng agent thật.

    uv run spikes/vertical-slice/probe_runtime.py up          # build zip, role, app client yofina-probe, Runtime
    uv run spikes/vertical-slice/probe_runtime.py interrupt   # thử interrupt/resume (tốn vài lượt gọi Nova)
    uv run spikes/vertical-slice/probe_runtime.py expiry      # luồng 330 giây với access token sống 5 phút
    uv run spikes/vertical-slice/probe_runtime.py down        # XÓA toàn bộ tài nguyên thử, khôi phục Gateway

Tài nguyên tạm (tiền tố `yofina-probe`/`yofina_probe`, tag project=yofina purpose=probe-temporary): IAM role
`yofina-probe-runtime`, Cognito app client `yofina-probe` (access token 5 phút), AgentCore Runtime `yofina_probe`,
object `tmp/probe-agent.zip` và `tmp/probe-interrupt/*` trong bucket artifact; trong phép thử `expiry` Gateway thật
được thêm tạm client `yofina-probe` vào `allowedClients` (khôi phục ở `down` hoặc ngay sau phép thử).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests" / "integration"))

from _demo_auth import demo_accounts, login_access_token  # noqa: E402
from _yofina import REGION, session, ssm_param  # noqa: E402
from agentcore_helpers import invoke_agent  # noqa: E402
from build_lambda import PLATFORMS, write_zip  # noqa: E402

OUT = HERE / "out"
OUT.mkdir(exist_ok=True)
STATE_FILE = OUT / "probe_state.json"
BUILD = REPO / "build" / "probe"
ROLE = "yofina-probe-runtime"
CLIENT_NAME = "yofina-probe"
RUNTIME = "yofina_probe"
TAGS = {"project": "yofina", "purpose": "probe-temporary"}
ZIP_KEY = "tmp/probe-agent.zip"
S3_PREFIX = "tmp/probe-interrupt/"
DEPS = [
    "ag-ui-protocol==1.0.0",
    "ag-ui-strands==1.0.4",
    "strands-agents==1.65.0",
    "fastapi",
    "uvicorn",
    "boto3",
    "httpx",
]


def state() -> dict:
    return json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}


def save(**kw) -> None:
    s = state()
    s.update(kw)
    STATE_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")


def runtime_arn(sess, runtime_id: str) -> str:
    account = sess.client("sts").get_caller_identity()["Account"]
    return f"arn:aws:bedrock-agentcore:{REGION}:{account}:runtime/{runtime_id}"


def url_for(sess, runtime_id: str) -> str:
    arn = runtime_arn(sess, runtime_id)
    return (
        f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/"
        f"{urllib.parse.quote(arn, safe='')}/invocations?qualifier=DEFAULT"
    )


def build_zip() -> Path:
    pkg = BUILD / "pkg"
    if pkg.exists():
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True)
    subprocess.run(
        [
            "uv", "pip", "install", "--python-platform", PLATFORMS["arm64"], "--python-version", "3.13",
            "--only-binary=:all:", "--target", str(pkg), *DEPS,
        ],
        check=True,
    )  # fmt: skip
    for junk in ("bin", "Scripts"):
        shutil.rmtree(pkg / junk, ignore_errors=True)
    shutil.copy2(HERE / "probe_agent" / "main.py", pkg / "main.py")
    for cache in pkg.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    out = BUILD / "probe-agent.zip"
    write_zip(pkg, out)
    return out


def up() -> None:
    sess = session()
    account = sess.client("sts").get_caller_identity()["Account"]
    bucket = ssm_param("s3/artifact-bucket", sess=sess)
    pool = ssm_param("auth/user-pool-id", sess=sess)
    web_client = ssm_param("auth/client-id", sess=sess)
    discovery = ssm_param("auth/discovery-url", sess=sess)
    zip_path = build_zip()
    sess.client("s3").upload_file(str(zip_path), bucket, ZIP_KEY)

    iam = sess.client("iam")
    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": account},
                    "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock-agentcore:{REGION}:{account}:runtime/*"},
                },
            }
        ],
    }
    iam.create_role(
        RoleName=ROLE,
        AssumeRolePolicyDocument=json.dumps(trust),
        Tags=[{"Key": k, "Value": v} for k, v in TAGS.items()],
    )
    save(role=ROLE)
    iam.put_role_policy(
        RoleName=ROLE,
        PolicyName="inline",
        PolicyDocument=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                        "Resource": [
                            f"arn:aws:bedrock:{REGION}:{account}:inference-profile/global.amazon.nova-2-lite-v1:0",
                            "arn:aws:bedrock:*::foundation-model/amazon.nova-2-lite-v1:0",
                        ],
                    },
                    {
                        "Effect": "Allow",
                        "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                        "Resource": f"arn:aws:s3:::{bucket}/{S3_PREFIX}*",
                    },
                    {"Effect": "Allow", "Action": "s3:ListBucket", "Resource": f"arn:aws:s3:::{bucket}"},
                    {
                        "Effect": "Allow",
                        "Action": ["s3:GetObject"],
                        "Resource": f"arn:aws:s3:::{bucket}/{ZIP_KEY}",
                    },
                    {
                        "Effect": "Allow",
                        "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
                        "Resource": f"arn:aws:logs:{REGION}:{account}:log-group:/aws/bedrock-agentcore/runtimes/*",
                    },
                ],
            }
        ),
    )
    cog = sess.client("cognito-idp")
    created = cog.create_user_pool_client(
        UserPoolId=pool,
        ClientName=CLIENT_NAME,
        GenerateSecret=False,
        ExplicitAuthFlows=["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
        AccessTokenValidity=5,
        IdTokenValidity=5,
        RefreshTokenValidity=1,
        TokenValidityUnits={"AccessToken": "minutes", "IdToken": "minutes", "RefreshToken": "days"},
    )["UserPoolClient"]["ClientId"]
    save(probe_client_id=created)
    time.sleep(12)  # IAM lan truyền

    control = sess.client("bedrock-agentcore-control")
    rt = control.create_agent_runtime(
        agentRuntimeName=RUNTIME,
        agentRuntimeArtifact={
            "codeConfiguration": {
                "code": {"s3": {"bucket": bucket, "prefix": ZIP_KEY}},
                "runtime": "PYTHON_3_13",
                "entryPoint": ["main.py"],
            }
        },
        roleArn=f"arn:aws:iam::{account}:role/{ROLE}",
        networkConfiguration={"networkMode": "PUBLIC"},
        protocolConfiguration={"serverProtocol": "AGUI"},
        authorizerConfiguration={
            "customJWTAuthorizer": {"discoveryUrl": discovery, "allowedClients": [web_client, created]}
        },
        requestHeaderConfiguration={"requestHeaderAllowlist": ["Authorization"]},
        environmentVariables={"PROBE_BUCKET": bucket, "PROBE_PREFIX": S3_PREFIX},
        tags=TAGS,
    )
    save(runtime_id=rt["agentRuntimeId"])
    while True:
        got = control.get_agent_runtime(agentRuntimeId=rt["agentRuntimeId"])
        if got["status"] not in ("CREATING", "UPDATING"):
            break
        time.sleep(5)
    print("runtime", got["status"], got.get("failureReason", ""))


def events_summary(run) -> dict:
    fin = run.finished or {}
    errs = [e for e in run.events if e.get("type") == "RUN_ERROR"]
    return {
        "http": run.status,
        "types": sorted(set(run.types)),
        "outcome": fin.get("outcome"),
        "result": fin.get("result"),
        "text": run.text[:200],
        "errors": [{k: e.get(k) for k in ("code", "message")} for e in errs],
        "tool_results": [e.get("content", "")[:120] for e in run.events if e.get("type") == "TOOL_CALL_RESULT"],
        "total_s": run.total,
    }


def interrupt() -> dict:
    sess = session()
    st = state()
    url = url_for(sess, st["runtime_id"])
    arn = runtime_arn(sess, st["runtime_id"])
    token = login_access_token("minh", sess=sess)
    out: dict[str, dict] = {}

    def first(mode: str, sid: str):
        run = invoke_agent(
            url,
            token,
            "chuyển 50 nghìn từ giai_tri sang an_uong",
            session_id=sid,
            thread_id=sid,
            forwarded_props={"mode": mode},
        )
        return run

    def resume(mode: str, sid: str, interrupt_id: str, approved: bool = True):
        import httpx

        from agentcore_helpers import SESSION_HEADER, AgentRun  # noqa: F401

        body = {
            "threadId": sid,
            "runId": "r-resume",
            "state": {},
            "messages": [],
            "tools": [],
            "context": [],
            "forwardedProps": {"mode": mode},
            "resume": [{"interruptId": interrupt_id, "status": "resolved", "payload": {"approved": approved}}],
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            SESSION_HEADER: sid,
        }
        run = AgentRun(status=0)
        with httpx.Client(timeout=120) as c, c.stream("POST", url, headers=headers, json=body) as r:
            run.status = r.status_code
            buf = "".join(r.iter_text())
        for frame in buf.split("\n\n"):
            for line in frame.split("\n"):
                if line.startswith("data:"):
                    run.events.append(json.loads(line[5:]))
        return run

    def interrupt_id_of(run) -> str | None:
        outcome = (run.finished or {}).get("outcome") or {}
        items = outcome.get("interrupts") or []
        return items[0]["id"] if items else None

    cases = [
        ("A. bền (S3), resume cùng microVM", "interrupt", False),
        ("B. bền (S3), microVM bị dừng rồi resume (microVM mới)", "interrupt", True),
        ("C. không session manager, resume cùng microVM", "interrupt_ram", False),
        ("D. không session manager, microVM bị dừng rồi resume", "interrupt_ram", True),
    ]
    for label, mode, stop in cases:
        import uuid

        sid = str(uuid.uuid4())
        r1 = first(mode, sid)
        iid = interrupt_id_of(r1)
        entry = {"turn1": events_summary(r1), "interrupt_id_seen": bool(iid)}
        if iid:
            if stop:
                # Runtime dùng JWT nên StopRuntimeSession (SigV4) bị từ chối; gọi bằng Bearer thì được (200)
                import httpx

                stop_url = (
                    f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/"
                    f"{urllib.parse.quote(arn, safe='')}/stopruntimesession?qualifier=DEFAULT"
                )
                r = httpx.post(
                    stop_url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": sid,
                        "Content-Type": "application/json",
                    },
                    json={},
                    timeout=30,
                )
                entry["stop_session_http"] = r.status_code
                time.sleep(3)
            entry["resume"] = events_summary(resume(mode, sid, iid))
        out[label] = entry
        print(label, json.dumps(entry, ensure_ascii=False)[:600], file=sys.stderr)
        time.sleep(5)
    (OUT / "probe_interrupt.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def gateway_allowed_clients(sess, add: str | None = None, remove: str | None = None) -> list[str]:
    control = sess.client("bedrock-agentcore-control")
    gid = ssm_param("gateway/id", sess=sess)
    g = control.get_gateway(gatewayIdentifier=gid)
    jwt = dict(g["authorizerConfiguration"]["customJWTAuthorizer"])
    clients = [c for c in jwt["allowedClients"] if c != remove]
    if add and add not in clients:
        clients.append(add)
    jwt["allowedClients"] = clients
    kw = {
        "gatewayIdentifier": gid,
        "name": g["name"],
        "roleArn": g["roleArn"],
        "protocolType": g["protocolType"],
        "authorizerType": g["authorizerType"],
        "authorizerConfiguration": {"customJWTAuthorizer": jwt},
    }
    for k in ("protocolConfiguration", "interceptorConfigurations", "policyEngineConfiguration", "exceptionLevel", "description"):
        if k in g:
            kw[k] = g[k]
    control.update_gateway(**kw)
    for _ in range(60):
        if control.get_gateway(gatewayIdentifier=gid)["status"] == "READY":
            break
        time.sleep(3)
    return clients


def expiry(seconds: int = 330) -> dict:
    sess = session()
    st = state()
    url = url_for(sess, st["runtime_id"])
    probe_client = st["probe_client_id"]
    cog = sess.client("cognito-idp")
    acct = demo_accounts(sess)["minh"]
    gateway_allowed_clients(sess, add=probe_client)
    time.sleep(10)
    try:
        auth = cog.initiate_auth(
            ClientId=probe_client,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": acct["email"], "PASSWORD": acct["password"]},
        )["AuthenticationResult"]
        token = auth["AccessToken"]
        print("access token sống", auth["ExpiresIn"], "giây; mở luồng", seconds, "giây", file=sys.stderr)
        run = invoke_agent(
            url,
            token,
            "thử",
            forwarded_props={
                "mode": "slow",
                "seconds": seconds,
                "interval": 30,
                "gateway_url": ssm_param("gateway_url", sess=sess),
            },
            timeout=seconds + 120,
        )
        summary = events_summary(run)
        # sau khi token đã hết hạn: một request MỚI với cùng token
        after = invoke_agent(url, token, "thử", forwarded_props={"mode": "slow", "seconds": 1, "interval": 1})
        summary["new_request_with_expired_token"] = {"http": after.status, "raw": (after.raw or "")[:200], "events": after.events[:2]}
        summary["expires_in_seconds"] = auth["ExpiresIn"]
        (OUT / "probe_expiry.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return summary
    finally:
        gateway_allowed_clients(sess, remove=probe_client)


def down() -> None:
    sess = session()
    st = state()
    control = sess.client("bedrock-agentcore-control")
    try:
        gateway_allowed_clients(sess, remove=st.get("probe_client_id", "none"))
    except Exception as exc:  # noqa: BLE001
        print("khôi phục Gateway:", repr(exc)[:200])
    if st.get("runtime_id"):
        try:
            control.delete_agent_runtime(agentRuntimeId=st["runtime_id"])
            for _ in range(60):
                time.sleep(5)
                try:
                    control.get_agent_runtime(agentRuntimeId=st["runtime_id"])
                except Exception:  # noqa: BLE001
                    break
        except Exception as exc:  # noqa: BLE001
            print("xóa runtime:", repr(exc)[:200])
    if st.get("probe_client_id"):
        try:
            sess.client("cognito-idp").delete_user_pool_client(
                UserPoolId=ssm_param("auth/user-pool-id", sess=sess), ClientId=st["probe_client_id"]
            )
        except Exception as exc:  # noqa: BLE001
            print("xóa app client:", repr(exc)[:200])
    iam = sess.client("iam")
    if st.get("role"):
        try:
            iam.delete_role_policy(RoleName=ROLE, PolicyName="inline")
            iam.delete_role(RoleName=ROLE)
        except Exception as exc:  # noqa: BLE001
            print("xóa role:", repr(exc)[:200])
    bucket = ssm_param("s3/artifact-bucket", sess=sess)
    s3 = sess.client("s3")
    keys = [ZIP_KEY] + [
        o["Key"] for o in s3.list_objects_v2(Bucket=bucket, Prefix=S3_PREFIX).get("Contents", [])
    ]
    for k in keys:
        s3.delete_object(Bucket=bucket, Key=k)
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    print("đã dọn:", {"runtime": st.get("runtime_id"), "client": bool(st.get("probe_client_id")), "role": st.get("role"), "s3_objects": len(keys)})


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"up": up, "interrupt": interrupt, "expiry": expiry, "down": down}[cmd]()
