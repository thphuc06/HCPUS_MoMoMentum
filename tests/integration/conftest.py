"""Test tích hợp của ledger: gọi môi trường AWS ĐÃ DEPLOY (HTTP API, Lambda, Aurora, DynamoDB).

Chạy: `uv run pytest tests/integration -m integration` (cần credential AWS của dự án; region
ap-southeast-1). Token là access token Cognito thật của `minh` và `lan` (đăng nhập SRP, mật khẩu đọc từ
secret trong bộ nhớ). Mọi tên tài nguyên đọc từ SSM `/yofina/...`, không gắn cứng.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from _demo_auth import (  # noqa: E402
    api_url,
    call_api,
    demo_accounts,
    login_access_token,
)
from _yofina import REGION, session, ssm_param  # noqa: E402


def pytest_collection_modifyitems(items):
    here = Path(__file__).parent
    for item in items:
        if here in Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.integration)


def _unit_conftest():
    spec = importlib.util.spec_from_file_location(
        "unit_conftest", REPO / "tests" / "unit" / "conftest.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def registry():
    return _unit_conftest().build_registry()


@pytest.fixture(scope="session")
def schema_validator(registry):
    """validator(ref_uri, instance): kiểm bằng JSON Schema/OpenAPI thật của hợp đồng."""
    from jsonschema import Draft202012Validator

    uc = _unit_conftest()

    def run(ref: str, instance) -> None:
        v = Draft202012Validator({"$ref": ref}, registry=registry)
        errors = [f"{list(e.path)}: {e.message}" for e in v.iter_errors(instance)]
        assert not errors, errors

    run.openapi = lambda name, inst: run(f"{uc.OPENAPI_URI}#/components/schemas/{name}", inst)
    run.results = lambda name, inst: run(
        f"{uc.BASE}/tools/ledger.results.schema.json#/$defs/{name}", inst
    )
    return run


@pytest.fixture(scope="session")
def sess():
    return session()


@pytest.fixture(scope="session")
def base(sess) -> str:
    return api_url(sess)


@pytest.fixture(scope="session")
def accounts(sess):
    return demo_accounts(sess)


@pytest.fixture(scope="session")
def tokens(sess, accounts):
    return {n: login_access_token(n, sess=sess, accounts=accounts) for n in ("minh", "lan", "khoa")}


def jwt_sub(token: str) -> str:
    """`sub` đọc từ phần payload của JWT (không kiểm chữ ký; chỉ để dựng tình huống tấn công)."""
    part = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))["sub"]


@pytest.fixture(scope="session")
def subs(tokens):
    return {n: jwt_sub(t) for n, t in tokens.items()}


@pytest.fixture(scope="session")
def lambda_client(sess):
    return sess.client("lambda")


@pytest.fixture(scope="session")
def ledger_fn(sess) -> str:
    return ssm_param("ledger/function-name", sess=sess)


@pytest.fixture(scope="session")
def hmac_key(sess) -> bytes:
    """Khóa ký token thật: chỉ để dựng token hết hạn/giả mạo khớp chữ ký trong test tấn công."""
    arn = ssm_param("secrets/confirm-hmac-arn", sess=sess)
    return sess.client("secretsmanager").get_secret_value(SecretId=arn)["SecretString"].encode()


@pytest.fixture(scope="session")
def api(base, tokens):
    """Gọi REST bằng token của một tài khoản: api('minh', 'GET', '/jars') -> (status, body)."""

    def run(who: str | None, method: str, path: str, body=None, *, token: str | None = None, **kw):
        tok = token if token is not None else (tokens[who] if who else None)
        status, resp, _ms = call_api(base, method, path, tok, body, **kw)
        return status, resp

    return run


def token_payload(token: str) -> dict:
    """Payload (chưa kiểm chữ ký) của token xác nhận: sub, tool, h, exp, jti."""
    part = token.split(".")[0]
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


@pytest.fixture(scope="session")
def invoke(lambda_client, ledger_fn):
    """Gọi thẳng Lambda theo dạng sự kiện của AgentCore Gateway: tên tool ở client context,
    tham số (kèm user_id do interceptor ghi đè) là payload."""

    def run(tool: str, event: dict) -> dict:
        ctx = base64.b64encode(
            json.dumps({"custom": {"bedrockAgentCoreToolName": f"ledger___{tool}"}}).encode()
        ).decode()
        r = lambda_client.invoke(
            FunctionName=ledger_fn, ClientContext=ctx, Payload=json.dumps(event).encode()
        )
        assert "FunctionError" not in r, r["Payload"].read()
        return json.loads(r["Payload"].read())

    return run


@pytest.fixture(scope="session")
def gateway_url(sess) -> str:
    return ssm_param("gateway_url", sess=sess)


@pytest.fixture(scope="session")
def gw(gateway_url, tokens):
    """gw('minh') -> GatewayClient (MCP thật, access token của tài khoản đó)."""
    from agentcore_helpers import GatewayClient

    return lambda who: GatewayClient(gateway_url, tokens[who])


@pytest.fixture(scope="session")
def agent_url(sess) -> str:
    from agentcore_helpers import runtime_url

    return runtime_url(ssm_param("agent/runtime-arn", sess=sess))


def reset_account(api, who: str) -> dict:
    status, body = api(who, "POST", "/demo/reset", timeout=60)
    assert status == 200, body
    return body


#: ngày neo của ví demo (YOFINA_DEMO_ANCHOR_DATE của Lambda ledger)
DEMO_ANCHOR = "2026-11-21"


def demo_wallet(persona: str):
    """Ví demo mà `POST /demo/reset` nạp cho persona (bộ hũ demo của issue #39): `PersonaData` sau `apply_demo_layout`, suy từ bộ sinh
    qua đúng ánh xạ mã hũ mà đặt lại dùng, không chép số. Ví dụ `credit_due_day` của minh là 3 (`DEMO_CREDIT_DUE_DAY`)."""
    from datetime import date

    from personas import generate
    from personas.six_jars import apply_demo_layout
    from yofina_ledger.jar_layout import DEMO_LAYOUT

    return apply_demo_layout(generate(persona, anchor=date.fromisoformat(DEMO_ANCHOR)), DEMO_LAYOUT)


def demo_jars(persona: str) -> dict:
    """Hũ của ví demo sau đặt lại, theo mã, theo thứ tự hiển thị: ba hũ mặc định (Chi hằng ngày với chi lặt vặt của khối `demo_jars`
    trong spec, Nghĩa vụ gộp Hóa đơn, Dự phòng) rồi hũ tự thêm (Ăn uống, Đi lại, Giải trí, Du lịch là hũ goal `muc_tieu`, Đầu tư 0 ₫);
    `minh`, `vy` 8 hũ, `lan` và `khoa` 7 hũ (không có hũ goal)."""
    return {j.code: j for j in demo_wallet(persona).jars}


def demo_balances(persona: str) -> dict[str, int]:
    return {code: j.balance_vnd for code, j in demo_jars(persona).items()}


@pytest.fixture(scope="module")
def fresh(api):
    """Đặt lại `minh`, `lan` và `khoa` về dữ liệu ban đầu trước và sau mỗi module."""
    for who in ("minh", "lan", "khoa"):
        reset_account(api, who)
    yield
    for who in ("minh", "lan", "khoa"):
        reset_account(api, who)


__all__ = ["REGION"]


# --- ví mô phỏng (phase 2): thêm khoa, tài khoản trắng tạm thời, hàng đợi hứng sự kiện tạm thời ----------------
def master_data_api(sess):
    """Data API bằng secret MASTER (chỉ để DỌN tài khoản thử; sản phẩm không bao giờ dùng master)."""
    from yofina_core.db import DataApi, DataApiSettings

    secret_arn = sess.client("secretsmanager").describe_secret(SecretId="yofina-db-master")["ARN"]
    return DataApi(
        DataApiSettings(
            cluster_arn=ssm_param("db/cluster-arn", sess=sess),
            secret_arn=secret_arn,
            database=ssm_param("db/name", sess=sess),
        ),
        region=REGION,
    )


@pytest.fixture(scope="session")
def khoa_token(sess, accounts):
    return login_access_token("khoa", sess=sess, accounts=accounts)


@pytest.fixture(scope="module")
def blank_account(sess):
    """Tài khoản Cognito trắng, tạo bằng script rồi DỌN (xóa user Cognito và mọi dòng DB của nó). Trả (token, sub)."""
    import secrets
    import uuid

    idp = sess.client("cognito-idp")
    pool = ssm_param("auth/user-pool-id", sess=sess)
    email = f"yofina-test-{uuid.uuid4().hex[:12]}@example.com"  # sinh lúc chạy, không ghi vào repo
    password = "Aa1!" + secrets.token_urlsafe(18)
    idp.admin_create_user(
        UserPoolId=pool,
        Username=email,
        TemporaryPassword=password,
        MessageAction="SUPPRESS",
        UserAttributes=[
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "true"},
        ],
    )
    sub = None
    try:
        idp.admin_set_user_password(
            UserPoolId=pool, Username=email, Password=password, Permanent=True
        )
        token = login_access_token(
            "blank", sess=sess, accounts={"blank": {"email": email, "password": password}}
        )
        sub = jwt_sub(token)
        yield token, sub
    finally:
        idp.admin_delete_user(UserPoolId=pool, Username=email)
        if sub:
            db = master_data_api(sess)
            with db.transaction(sub) as tx:
                tx.execute(
                    "DELETE FROM users WHERE id = :id", {"id": sub}
                )  # kéo theo mọi dòng (ON DELETE CASCADE)


@pytest.fixture()
def event_sink(sess):
    """Hàng đợi SQS tạm hứng sự kiện của `yofina-bus` qua một rule tạm; dọn sạch khi xong (không để lại rác)."""
    import json
    import uuid

    events, sqs = sess.client("events"), sess.client("sqs")
    bus = ssm_param("events/bus-name", sess=sess)
    suffix = uuid.uuid4().hex[:10]
    queue_name, rule = f"yofina-test-events-{suffix}", f"yofina-test-rule-{suffix}"
    qurl = sqs.create_queue(QueueName=queue_name, Attributes={"MessageRetentionPeriod": "60"})[
        "QueueUrl"
    ]
    qarn = sqs.get_queue_attributes(QueueUrl=qurl, AttributeNames=["QueueArn"])["Attributes"][
        "QueueArn"
    ]
    try:
        rule_arn = events.put_rule(
            Name=rule,
            EventBusName=bus,
            EventPattern=json.dumps({"source": ["yofina.ledger"]}),
            State="ENABLED",
        )["RuleArn"]
        sqs.set_queue_attributes(
            QueueUrl=qurl,
            Attributes={
                "Policy": json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"Service": "events.amazonaws.com"},
                                "Action": "sqs:SendMessage",
                                "Resource": qarn,
                                "Condition": {"ArnEquals": {"aws:SourceArn": rule_arn}},
                            }
                        ],
                    }
                )
            },
        )
        events.put_targets(Rule=rule, EventBusName=bus, Targets=[{"Id": "q", "Arn": qarn}])

        import time

        def _receive(wait: int = 5) -> list[dict]:
            out: list[dict] = []
            resp = sqs.receive_message(QueueUrl=qurl, MaxNumberOfMessages=10, WaitTimeSeconds=wait)
            for m in resp.get("Messages", []):
                out.append(json.loads(m["Body"]))
                sqs.delete_message(QueueUrl=qurl, ReceiptHandle=m["ReceiptHandle"])
            return out

        # Nguyên nhân ca test từng không ổn định: rule EventBridge vừa tạo cần một lúc (từ vài giây tới cỡ một phút) mới có hiệu lực,
        # và có hiệu lực KHÔNG đồng loạt (các máy chủ nhận cập nhật lệch nhau): sự kiện phát trước đó bị mất vĩnh viễn, nên chờ thêm sau
        # khi phát cũng không cứu được; một sự kiện thăm dò lọt qua cũng chưa chứng tỏ các sự kiện sau đó đều lọt qua. Vì vậy gửi
        # từng đợt thăm dò (`sink.probe`, mỗi cái một lần gọi PutEvents riêng, không khớp rule thật nào) và chỉ trả quyền cho test
        # khi HAI đợt liên tiếp đều lọt đủ.
        probes_per_round, rounds_needed = 6, 2
        deadline = time.time() + 180.0
        ok_rounds = 0
        while ok_rounds < rounds_needed:
            assert time.time() < deadline, "rule tạm không có hiệu lực ổn định sau 180 giây"
            for i in range(probes_per_round):
                events.put_events(
                    Entries=[
                        {
                            "EventBusName": bus,
                            "Source": "yofina.ledger",
                            "DetailType": "sink.probe",
                            "Detail": json.dumps({"probe": suffix, "n": i}),
                        }
                    ]
                )
            seen, round_end = 0, time.time() + 10.0
            while seen < probes_per_round and time.time() < round_end:
                seen += sum(1 for e in _receive(2) if e.get("detail-type") == "sink.probe")
            ok_rounds = ok_rounds + 1 if seen == probes_per_round else 0
        _receive(1)  # dọn các thăm dò còn sót để drain() không đếm nhầm

        def drain(expected: int, timeout: float = 60.0) -> list[dict]:
            got: list[dict] = []
            end = time.time() + timeout
            while len(got) < expected and time.time() < end:
                got.extend(e for e in _receive() if e.get("detail-type") != "sink.probe")
            return got

        yield drain
    finally:
        try:
            events.remove_targets(Rule=rule, EventBusName=bus, Ids=["q"])
        finally:
            try:
                events.delete_rule(Name=rule, EventBusName=bus)
            finally:
                sqs.delete_queue(QueueUrl=qurl)


def flow(api, who, tool, params, **extra):
    """Luồng đủ qua REST: POST /confirmations rồi POST /actions. Trả (status, body) của /actions (hoặc lỗi của bước một)."""
    status, conf = api(who, "POST", "/confirmations", {"tool": tool, "params": params, **extra})
    if status != 200:
        return status, conf
    return api(
        who,
        "POST",
        "/actions",
        {"tool": tool, "params": conf["params"], "confirm_token": conf["confirm_token"], **extra},
    )
