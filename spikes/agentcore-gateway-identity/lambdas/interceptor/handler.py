"""Request interceptor (spike). Đọc JWT (Gateway đã xác minh), lấy sub, rồi:
 - MODE=overwrite: ghi đè arguments.user_id = sub và thêm header x-user-id = sub
 - MODE=deny: nếu user_id client gửi != sub thì trả transformedGatewayResponse (từ chối ngay)
 - MODE=passthrough: chỉ log
In ra input (đã che token) để quan sát."""
import base64, copy, json, os

MODE = os.environ.get("MODE", "overwrite")


def _claims(tok):
    tok = tok.split(" ", 1)[-1]
    p = tok.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))


def lambda_handler(event, context):
    safe = copy.deepcopy(event)
    h = safe.get("mcp", {}).get("gatewayRequest", {}).get("headers") or {}
    for k in list(h):
        if k.lower() == "authorization":
            h[k] = "<redacted>"
    print("INTERCEPTOR_INPUT " + json.dumps(safe, default=str))
    req = event["mcp"]["gatewayRequest"]
    body = copy.deepcopy(req["body"])
    headers_in = {k.lower(): v for k, v in (req.get("headers") or {}).items()}
    out_req = {"body": body}
    if body.get("method") == "tools/call" and headers_in.get("authorization"):
        sub = _claims(headers_in["authorization"])["sub"]
        args = body.setdefault("params", {}).setdefault("arguments", {})
        sent = args.get("user_id")
        if MODE == "overwrite":
            args["user_id"] = sub
            out_req["headers"] = {"x-user-id": sub}
            print(f"INTERCEPTOR overwrite user_id {sent!r} -> {sub!r}")
        elif MODE == "deny" and sent is not None and sent != sub:
            print("INTERCEPTOR deny")
            return {"interceptorOutputVersion": "1.0", "mcp": {"transformedGatewayResponse": {
                "statusCode": 200, "body": {"jsonrpc": "2.0", "id": body.get("id"), "result": {
                    "isError": True, "content": [{"type": "text", "text": "user_id không khớp JWT"}]}}}}}
    return {"interceptorOutputVersion": "1.0", "mcp": {"transformedGatewayRequest": out_req}}
