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
    return {n: login_access_token(n, sess=sess, accounts=accounts) for n in ("minh", "lan")}


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


@pytest.fixture(scope="module")
def fresh(api):
    """Đặt lại `minh` và `lan` về dữ liệu ban đầu trước và sau mỗi module."""
    reset_account(api, "minh")
    reset_account(api, "lan")
    yield
    reset_account(api, "minh")
    reset_account(api, "lan")


__all__ = ["REGION"]
