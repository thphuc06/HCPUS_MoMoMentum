"""Q5: token xác nhận HMAC do server cấp. Gateway 'main' (ENFORCE + interceptor overwrite), ledger REQUIRE_TOKEN=1."""
import base64, hashlib, hmac, json, time, uuid
from gw import *
from mcpcall import *
from step2_interceptor import G, set_mode

lam = client("lambda")


def set_env(fn, **kv):
    cur = lam.get_function_configuration(FunctionName=PREFIX + fn)["Environment"]["Variables"]
    cur.update(kv)
    lam.update_function_configuration(FunctionName=PREFIX + fn, Environment={"Variables": cur})
    lam.get_waiter("function_updated_v2").wait(FunctionName=PREFIX + fn)
    time.sleep(1)


def issue(access, params):
    """Giả lập 'nút bấm Xác nhận' của UI: gọi Lambda cấp token bằng access token của người dùng."""
    r = lam.invoke(FunctionName=PREFIX + "confirm", Payload=json.dumps({"access_token": access, "params": params}).encode())
    body = json.loads(r["Payload"].read())
    return body


def call(tok_access, name, args):
    s, body, ms = raw_post(G["url"], tok_access, {"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": name, "arguments": args}})
    j = json.loads(body)
    if "error" in j:
        return {"MCP_ERROR": j["error"]["message"][:140]}
    if j["result"].get("isError"):
        return {"isError": j["result"]["content"][0]["text"]}
    inner = json.loads(j["result"]["content"][0]["text"])
    return inner["result"]


def b64e(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


if __name__ == "__main__":
    set_env("ledger", REQUIRE_TOKEN="1")
    set_mode("overwrite")
    tk = tokens(); A, B = tk["user-a"], tk["user-b"]
    P = {"from_jar": "tiet_kiem", "to_jar": "thiet_yeu", "amount_vnd": 300000}
    MOVE = "ledger___move_between_jars"

    def args(user, tok=None, **over):
        a = {"user_id": user["sub"], **P, "user_confirmed": True, **over}
        if tok:
            a["confirm_token"] = tok
        return a

    print("1. LLM tự điền user_confirmed=true, không token  ->", call(A["access"], MOVE, args(A)))
    print("2. LLM bịa token 'abc.def'                       ->", call(A["access"], MOVE, args(A, "abc.def")))
    forged_payload = b64e(json.dumps({"sub": A["sub"], "tool": "move_between_jars", "exp": int(time.time()) + 600, "jti": uuid.uuid4().hex,
                                      "h": "0" * 64}, separators=(",", ":")).encode())
    forged = forged_payload + "." + b64e(hmac.new(b"khong-phai-secret", forged_payload.encode(), hashlib.sha256).digest())
    print("3. Token giả đúng định dạng, ký sai khóa         ->", call(A["access"], MOVE, args(A, forged)))

    t = issue(A["access"], dict(P, user_id=B["sub"]))     # client cố đòi cấp cho B bằng token của A
    print("4. Cấp token: client gửi user_id=B, server ghim  ->", {"bound_user_is_A": t["bound_params"]["user_id"] == A["sub"], "ttl": t["expires_in"]})
    tokA = t["confirm_token"]
    print("5. Tham số khác (amount 300000->3000000)         ->", call(A["access"], MOVE, args(A, tokA, amount_vnd=3000000)))
    print("6. Tham số khác (to_jar khác)                    ->", call(A["access"], MOVE, args(A, tokA, to_jar="vui_choi")))
    print("7. Đúng tham số + token (nút bấm đã bấm)         ->", call(A["access"], MOVE, args(A, tokA)))
    print("8. Replay cùng token                             ->", call(A["access"], MOVE, args(A, tokA)))

    tB = issue(B["access"], P)["confirm_token"]
    print("9. A dùng token của B (user_id bị ghi đè = A)    ->", call(A["access"], MOVE, args(A, tB)))
    tB2 = issue(B["access"], P)["confirm_token"]
    set_mode("passthrough")
    print("10. Như 9 nhưng KHÔNG có interceptor, A gửi user_id=B + token của B (token bị lộ/đánh cắp) ->",
          call(A["access"], MOVE, args(B, tB2)))
    set_mode("overwrite")

    try:
        bad = issue("khong.phai.jwt", P)
        print("11. Cấp token với access token giả               ->", bad.get("errorType"), str(bad.get("errorMessage"))[:90])
    except Exception as e:
        print("11. exc", e)

    set_env("confirm", TOKEN_TTL="1")
    t1 = issue(A["access"], P)["confirm_token"]
    time.sleep(3)
    print("12. Token hết hạn (TTL 1s)                        ->", call(A["access"], MOVE, args(A, t1)))
    set_env("confirm", TOKEN_TTL="120")
    print("13. Hợp lệ sau khi đặt lại TTL                    ->", call(A["access"], MOVE, args(A, issue(A["access"], P)["confirm_token"])))
