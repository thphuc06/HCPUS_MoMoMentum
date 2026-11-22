"""Test cấu hình Gateway đã deploy (chạy lại được trong CI hoặc khi đóng phase).

Khẳng định các lớp danh tính còn nguyên: Gateway có interceptor REQUEST (passRequestHeaders) trỏ đúng Lambda,
policy engine ở ENFORCE và mỗi tool của hợp đồng có một policy ACTIVE, JWT authorizer chỉ nhận client của app,
schema tool khớp `contracts/tools/ledger.json`. Gateway bị gỡ interceptor hay chuyển LOG_ONLY là lỗ hổng
(Lambda ledger tin `user_id` của sự kiện).
"""

from __future__ import annotations

import json

import pytest
from _yofina import ssm_param
from conftest import REPO

CONTRACT_TOOLS = json.loads(
    (REPO / "contracts" / "tools" / "ledger.json").read_text(encoding="utf-8")
)
FORECAST_TOOLS = json.loads(
    (REPO / "contracts" / "tools" / "forecast.json").read_text(encoding="utf-8")
)
# Phase 3: ba target mới cùng trỏ Lambda ledger (planner, knowledge, audit); forecast nay có ba tool.
PHASE3_TARGETS = ("planner", "knowledge", "audit")
PHASE3_TOOLS = {
    name: json.loads((REPO / "contracts" / "tools" / f"{name}.json").read_text(encoding="utf-8"))
    for name in PHASE3_TARGETS
}


@pytest.fixture(scope="module")
def control(sess):
    return sess.client("bedrock-agentcore-control")


@pytest.fixture(scope="module")
def gateway(control, sess):
    return control.get_gateway(gatewayIdentifier=ssm_param("gateway/id", sess=sess))


def test_gateway_san_sang_va_dung_url(gateway, gateway_url):
    assert gateway["status"] == "READY"
    assert gateway["gatewayUrl"] == gateway_url
    assert gateway["protocolType"] == "MCP" and gateway["authorizerType"] == "CUSTOM_JWT"


def test_jwt_authorizer_chi_nhan_client_cua_app(gateway, sess):
    jwt = gateway["authorizerConfiguration"]["customJWTAuthorizer"]
    assert jwt["allowedClients"] == [ssm_param("auth/client-id", sess=sess)]
    assert jwt["discoveryUrl"] == ssm_param("auth/discovery-url", sess=sess)
    assert "allowedAudience" not in jwt  # Cognito: chỉ dùng allowedClients với access token


def test_gateway_co_interceptor_request_truyen_header(gateway, sess):
    configs = gateway["interceptorConfigurations"]
    assert len(configs) == 1
    cfg = configs[0]
    assert cfg["interceptionPoints"] == ["REQUEST"]
    assert cfg["inputConfiguration"]["passRequestHeaders"] is True
    lam = sess.client("lambda").get_function(FunctionName="yofina-gw-interceptor")["Configuration"]
    assert cfg["interceptor"]["lambda"]["arn"] == lam["FunctionArn"]


def test_policy_engine_o_che_do_enforce(gateway, control):
    cfg = gateway["policyEngineConfiguration"]
    assert cfg["mode"] == "ENFORCE", "Gateway đang LOG_ONLY: Cedar không chặn gì"
    engine_id = cfg["arn"].rsplit("/", 1)[-1]
    assert control.get_policy_engine(policyEngineId=engine_id)["status"] == "ACTIVE"


def list_all(fn, key, **kw):
    """Gộp mọi trang của một lệnh liệt kê (mỗi trang tối đa 10 mục)."""
    items, token = [], None
    while True:
        resp = fn(**kw, **({"nextToken": token} if token else {}))
        items += resp[key]
        token = resp.get("nextToken")
        if not token:
            return items


def require_phase3_gateway(gateway, control):
    """Gateway chỉ có đủ bốn target sau khi stack YofinaAgent được deploy bản phase 3 (việc của bước ghép, không phải của luồng A).
    Chưa deploy thì bỏ qua có lý do thay vì báo đỏ giả; test chạy thật ngay khi Gateway được cập nhật."""
    gid = gateway["gatewayId"]
    names = {t["name"] for t in list_all(control.list_gateway_targets, "items", gatewayIdentifier=gid)}
    if not set(PHASE3_TARGETS) <= names:
        pytest.skip(f"Gateway chưa có target phase 3 (đang có {sorted(names)}): chờ deploy YofinaAgent")


def test_moi_tool_co_mot_policy_active(gateway, control):
    require_phase3_gateway(gateway, control)
    engine_id = gateway["policyEngineConfiguration"]["arn"].rsplit("/", 1)[-1]
    policies = list_all(control.list_policies, "policies", policyEngineId=engine_id)
    names = {p["name"] for p in policies}
    assert names == (
        {f"ledger_{t['name']}_own_user" for t in CONTRACT_TOOLS}
        | {f"forecast_{t['name']}_own_user" for t in FORECAST_TOOLS}
        | {f"{n}_{t['name']}_own_user" for n, tools in PHASE3_TOOLS.items() for t in tools}
    )
    for p in policies:
        got = control.get_policy(policyEngineId=engine_id, policyId=p["policyId"])
        assert got["status"] == "ACTIVE", (p["name"], got.get("statusReasons"))
        assert got.get("enforcementMode", "ACTIVE") == "ACTIVE"
        cedar = got["definition"]["cedar"]["statement"]
        assert "context.input.user_id == principal.id" in cedar


def test_target_forecast_dung_lambda_va_schema_theo_hop_dong(gateway, control, sess):
    require_phase3_gateway(gateway, control)
    gid = gateway["gatewayId"]
    targets = list_all(control.list_gateway_targets, "items", gatewayIdentifier=gid)
    fc = next(t for t in targets if t["name"] == "forecast")
    target = control.get_gateway_target(gatewayIdentifier=gid, targetId=fc["targetId"])
    assert target["status"] == "READY"
    cfg = target["targetConfiguration"]["mcp"]["lambda"]
    assert cfg["lambdaArn"] == ssm_param("forecast/function-arn", sess=sess)
    deployed = {t["name"]: t for t in cfg["toolSchema"]["inlinePayload"]}
    assert set(deployed) == {t["name"] for t in FORECAST_TOOLS} == {
        "get_forecast",
        "run_scenario",
        "affordability_check",
    }
    got = deployed["get_forecast"]["inputSchema"]
    assert set(got["properties"]) == {"user_id", "jar"} and got["required"] == ["jar"]
    assert deployed["run_scenario"]["inputSchema"]["required"] == ["scenario"]
    assert deployed["affordability_check"]["inputSchema"]["required"] == ["amount_vnd"]


def test_ba_target_phase3_cung_tro_lambda_ledger_va_schema_theo_hop_dong(gateway, control, sess):
    require_phase3_gateway(gateway, control)
    gid = gateway["gatewayId"]
    targets = {t["name"]: t for t in list_all(control.list_gateway_targets, "items", gatewayIdentifier=gid)}
    ledger_arn = ssm_param("ledger/function-arn", sess=sess)
    for name, contract in PHASE3_TOOLS.items():
        target = control.get_gateway_target(gatewayIdentifier=gid, targetId=targets[name]["targetId"])
        assert target["status"] == "READY", (name, target.get("statusReasons"))
        cfg = target["targetConfiguration"]["mcp"]["lambda"]
        assert cfg["lambdaArn"] == ledger_arn  # không có Lambda riêng (người điều phối chốt)
        deployed = {t["name"]: t for t in cfg["toolSchema"]["inlinePayload"]}
        assert set(deployed) == {t["name"] for t in contract}


def test_target_ledger_dung_lambda_va_schema_theo_hop_dong(gateway, control, sess):
    require_phase3_gateway(gateway, control)
    gid = gateway["gatewayId"]
    targets = list_all(control.list_gateway_targets, "items", gatewayIdentifier=gid)
    assert sorted(t["name"] for t in targets) == sorted(["forecast", "ledger", *PHASE3_TARGETS])
    ledger = next(t for t in targets if t["name"] == "ledger")
    target = control.get_gateway_target(gatewayIdentifier=gid, targetId=ledger["targetId"])
    assert target["status"] == "READY"
    cfg = target["targetConfiguration"]["mcp"]["lambda"]
    assert cfg["lambdaArn"] == ssm_param("ledger/function-arn", sess=sess)
    deployed = {t["name"]: t for t in cfg["toolSchema"]["inlinePayload"]}
    assert set(deployed) == {t["name"] for t in CONTRACT_TOOLS}
    for tool in CONTRACT_TOOLS:
        got = deployed[tool["name"]]["inputSchema"]
        assert set(got.get("properties", {})) == set(tool["inputSchema"]["properties"])
        assert set(got.get("required", [])) == set(tool["inputSchema"].get("required", []))
    assert (
        target["credentialProviderConfigurations"][0]["credentialProviderType"]
        == "GATEWAY_IAM_ROLE"
    )


def test_runtime_dung_cau_hinh(control, sess):
    rt = control.get_agent_runtime(agentRuntimeId=ssm_param("agent/runtime-id", sess=sess))
    assert rt["status"] == "READY"
    assert rt["protocolConfiguration"]["serverProtocol"] == "AGUI"
    assert rt.get("platformVersion") == "V2"
    art = rt["agentRuntimeArtifact"]["codeConfiguration"]
    assert art["runtime"] == "PYTHON_3_13" and art["entryPoint"] == ["main.py"]
    jwt = rt["authorizerConfiguration"]["customJWTAuthorizer"]
    assert jwt["allowedClients"] == [ssm_param("auth/client-id", sess=sess)]
    assert "Authorization" in rt["requestHeaderConfiguration"]["requestHeaderAllowlist"]
    assert rt["networkConfiguration"]["networkMode"] == "PUBLIC"
    env = rt["environmentVariables"]
    assert env["YOFINA_GATEWAY_URL"] == ssm_param("gateway_url", sess=sess)
    assert env["YOFINA_TURN_BLOCKS_TOOL"] == "ledger___save_turn"
