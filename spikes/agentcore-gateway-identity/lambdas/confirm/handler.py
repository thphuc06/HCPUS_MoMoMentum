"""Lambda cấp token xác nhận (chỉ nút bấm của UI gọi tới, KHÔNG nằm sau Gateway/LLM).
Xác minh access token Cognito bằng cognito-idp:GetUser (API không cần chữ ký AWS), lấy sub thật,
ghim user_id = sub rồi ký HMAC gắn (sub, tool, hash tham số, hạn dùng, jti)."""
import base64, hashlib, hmac, json, os, time, uuid
import boto3

SECRET = os.environ["CONFIRM_SECRET"].encode()
TTL = int(os.environ.get("TOKEN_TTL", "120"))
cog = boto3.client("cognito-idp")


def _b64e(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def params_hash(args):
    core = {k: args.get(k) for k in ("user_id", "from_jar", "to_jar", "amount_vnd")}
    return hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def lambda_handler(event, context):
    user = cog.get_user(AccessToken=event["access_token"])          # ném lỗi nếu token sai/hết hạn
    sub = next(a["Value"] for a in user["UserAttributes"] if a["Name"] == "sub")
    params = dict(event["params"])
    params["user_id"] = sub                                          # server ghim, không tin client
    payload = {"sub": sub, "tool": "move_between_jars", "h": params_hash(params),
               "exp": int(time.time()) + TTL, "jti": uuid.uuid4().hex}
    p_b64 = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64e(hmac.new(SECRET, p_b64.encode(), hashlib.sha256).digest())
    return {"confirm_token": f"{p_b64}.{sig}", "bound_params": params, "expires_in": TTL}
