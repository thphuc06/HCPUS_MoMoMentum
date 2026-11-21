"""Request interceptor của Gateway: ghi đè user_id từ sub của JWT, đóng cửa khi thiếu danh tính."""

from __future__ import annotations

import base64
import importlib.util
import json

import pytest
from conftest import REPO

_spec = importlib.util.spec_from_file_location(
    "gw_interceptor", REPO / "gateway" / "interceptor" / "handler.py"
)
interceptor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(interceptor)


def jwt(sub: str | None = "sub-A", **extra) -> str:
    def b64(obj) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    payload = {**({"sub": sub} if sub is not None else {}), **extra}
    return f"{b64({'alg': 'RS256'})}.{b64(payload)}.c2ln"


def event(body, auth: str | None = None, header_name: str = "Authorization"):
    headers = {"Content-Type": "application/json"}
    if auth is not None:
        headers[header_name] = auth
    return {
        "interceptorInputVersion": "1.0",
        "mcp": {
            "gatewayRequest": {
                "path": "/mcp",
                "httpMethod": "POST",
                "headers": headers,
                "body": body,
            }
        },
    }


def call_msg(name="ledger___get_jar_balances", arguments=None, mid=7):
    params = {"name": name}
    if arguments is not None:
        params["arguments"] = arguments
    return {"jsonrpc": "2.0", "id": mid, "method": "tools/call", "params": params}


def out_body(res):
    return res["mcp"]["transformedGatewayRequest"]["body"]


@pytest.mark.parametrize(
    "arguments",
    [None, {}, {"user_id": "sub-B"}, {"user_id": ""}, {"user_id": None, "limit": 3}, "chuoi la"],
)
def test_ghi_de_user_id_bang_sub(arguments):
    res = interceptor.handle(event(call_msg(arguments=arguments), f"Bearer {jwt('sub-A')}"))
    args = out_body(res)["params"]["arguments"]
    assert args["user_id"] == "sub-A"
    if isinstance(arguments, dict) and "limit" in arguments:
        assert args["limit"] == 3  # tham số khác giữ nguyên


def test_khong_sua_ban_goc_va_header_khong_phan_biet_hoa_thuong():
    msg = call_msg(arguments={"user_id": "sub-B"})
    res = interceptor.handle(event(msg, f"bearer {jwt('sub-A')}", header_name="authorization"))
    assert msg["params"]["arguments"]["user_id"] == "sub-B"
    assert out_body(res)["params"]["arguments"]["user_id"] == "sub-A"


@pytest.mark.parametrize(
    "method", ["initialize", "tools/list", "notifications/initialized", "ping"]
)
def test_phuong_thuc_khac_di_qua_nguyen_ven(method):
    body = {"jsonrpc": "2.0", "id": 1, "method": method}
    # kể cả không có Authorization: Gateway đã xác thực, interceptor không can thiệp
    assert out_body(interceptor.handle(event(body))) == body


@pytest.mark.parametrize(
    "auth",
    [
        None,
        "",
        "Basic abc",
        "Bearer",
        "Bearer a.b",
        "Bearer a.%%%.c",
        f"Bearer {jwt(None)}",
        f"Bearer {jwt('x y')}",
    ],
)
def test_tools_call_thieu_danh_tinh_bi_tu_choi_va_khong_toi_lambda(auth):
    res = interceptor.handle(event(call_msg(arguments={"user_id": "sub-B"}, mid=42), auth))
    assert "transformedGatewayRequest" not in res["mcp"]
    body = res["mcp"]["transformedGatewayResponse"]["body"]
    assert body["id"] == 42 and body["result"]["isError"] is True


def test_goi_theo_lo_moi_tools_call_deu_bi_ghi_de():
    batch = [
        call_msg(arguments={"user_id": "B"}, mid=1),
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        call_msg(mid=3),
    ]
    out = out_body(interceptor.handle(event(batch, f"Bearer {jwt('sub-A')}")))
    assert out[0]["params"]["arguments"]["user_id"] == "sub-A"
    assert "params" not in out[1]
    assert out[2]["params"]["arguments"]["user_id"] == "sub-A"


def test_khong_ghi_token_ra_log(caplog):
    token = jwt("sub-A")
    with caplog.at_level("INFO", logger="yofina.gateway.interceptor"):
        interceptor.handle(event(call_msg(arguments={"user_id": "sub-B"}), f"Bearer {token}"))
        interceptor.handle(event(call_msg(), "Bearer rac.rac.rac"))
    text = caplog.text
    assert token not in text and "Bearer" not in text
    assert "client_sent_other_user_id" in text and "true" in text


def test_lambda_handler_bao_boc():
    res = interceptor.lambda_handler(event(call_msg(), f"Bearer {jwt('sub-Z')}"), None)
    assert res["interceptorOutputVersion"] == "1.0"
    assert out_body(res)["params"]["arguments"]["user_id"] == "sub-Z"
