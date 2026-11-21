"""Lambda tool `ledger` (spike). In ra TOÀN BỘ event + context nhận được và trả lại trong kết quả
để quan sát. move_between_jars là ghi giả (chỉ log) và có thể đòi token xác nhận HMAC."""
import base64, hashlib, hmac, json, os, time
import boto3

SECRET = os.environ.get("CONFIRM_SECRET", "").encode()
TABLE = os.environ.get("JTI_TABLE", "")
REQUIRE_TOKEN = os.environ.get("REQUIRE_TOKEN", "1") == "1"
_ddb = None


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def params_hash(args):
    core = {k: args.get(k) for k in ("user_id", "from_jar", "to_jar", "amount_vnd")}
    return hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify_token(token, args):
    """Trả (ok, lý do). Kiểm: chữ ký, hạn dùng, tool, user, hash tham số, dùng một lần."""
    global _ddb
    try:
        p_b64, sig_b64 = token.split(".")
        got = _b64d(sig_b64)
    except Exception:
        return False, "token sai định dạng"
    expect = hmac.new(SECRET, p_b64.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(expect, got):
        return False, "chữ ký không hợp lệ"
    p = json.loads(_b64d(p_b64))
    if p["exp"] < time.time():
        return False, "token hết hạn"
    if p["tool"] != "move_between_jars":
        return False, "token cho tool khác"
    if p["sub"] != args.get("user_id"):
        return False, "token cấp cho người dùng khác"
    if p["h"] != params_hash(args):
        return False, "tham số khác với tham số đã được xác nhận"
    if TABLE:
        _ddb = _ddb or boto3.client("dynamodb")
        try:
            _ddb.put_item(TableName=TABLE, Item={"jti": {"S": p["jti"]}, "ttl": {"N": str(int(p["exp"]) + 3600)}},
                          ConditionExpression="attribute_not_exists(jti)")
        except _ddb.exceptions.ConditionalCheckFailedException:
            return False, "token đã được dùng (replay)"
    return True, "ok"


def lambda_handler(event, context):
    cc = context.client_context
    custom = dict(getattr(cc, "custom", None) or {})
    ident = getattr(context, "identity", None)
    dump = {
        "event": event,
        "client_context": {"custom": custom, "env": getattr(cc, "env", None), "client": getattr(cc, "client", None)} if cc else None,
        "context": {
            "function_name": context.function_name,
            "aws_request_id": context.aws_request_id,
            "identity": {"cognito_identity_id": getattr(ident, "cognito_identity_id", None),
                         "cognito_identity_pool_id": getattr(ident, "cognito_identity_pool_id", None)} if ident else None,
            "attrs": sorted(a for a in dir(context) if not a.startswith("_")),
        },
    }
    print("LEDGER_DUMP " + json.dumps(dump, default=str))
    tool = custom.get("bedrockAgentCoreToolName", "").split("___")[-1] or event.get("_tool", "")
    out = {"tool": tool, "dump": dump}
    if tool == "get_jar_balances":
        out["result"] = {"owner": event.get("user_id"), "jars": {"thiet_yeu": 5000000, "tiet_kiem": 2000000, "vui_choi": 800000}}
    elif tool == "move_between_jars":
        if REQUIRE_TOKEN:
            tok = event.get("confirm_token")
            if not tok:
                out["result"] = {"status": "NEEDS_CONFIRMATION", "reason": "thiếu confirm_token"}
                return out
            ok, why = verify_token(tok, event)
            if not ok:
                print("LEDGER_REJECT " + why)
                out["result"] = {"status": "REJECTED", "reason": why}
                return out
        print("LEDGER_WRITE (giả) " + json.dumps({k: event.get(k) for k in ("user_id", "from_jar", "to_jar", "amount_vnd")}))
        out["result"] = {"status": "MOVED", "owner": event.get("user_id"), "from": event.get("from_jar"),
                         "to": event.get("to_jar"), "amount_vnd": event.get("amount_vnd")}
    else:
        out["result"] = {"error": "tool lạ", "tool": tool}
    return out
