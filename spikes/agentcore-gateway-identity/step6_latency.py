"""Q6: độ trễ tools/call qua Gateway: lạnh (Lambda cold start ép bằng đổi env) và ấm (5 lần), 4 cấu hình."""
import json, statistics, time
import httpx
from gw import *
from mcpcall import *
from step2_interceptor import G as MAIN, set_mode

lam = client("lambda")
PLAIN = load_state()["gateways"]["plain"]
eng = load_state()["engine"]


def bump():
    """Ép cold start: đổi env của cả ledger lẫn interceptor -> sandbox mới."""
    for fn, base in (("ledger", {"JTI_TABLE": PREFIX + "jti", "REQUIRE_TOKEN": "0"}), ("interceptor", {"MODE": "overwrite"})):
        cur = lam.get_function_configuration(FunctionName=PREFIX + fn)["Environment"]["Variables"]
        cur["BUMP"] = str(time.time())
        lam.update_function_configuration(FunctionName=PREFIX + fn, Environment={"Variables": cur})
    for fn in ("ledger", "interceptor"):
        lam.get_waiter("function_updated_v2").wait(FunctionName=PREFIX + fn)


def one(c, url, tok, sub):
    t0 = time.perf_counter()
    r = c.post(url, headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
               json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "ledger___get_jar_balances", "arguments": {"user_id": sub}}})
    ms = (time.perf_counter() - t0) * 1000
    j = r.json()
    ok = "result" in j and not j["result"].get("isError") and "owner" in j["result"]["content"][0]["text"]
    return ms, ok


def measure(label, url, tok, sub):
    cold = []
    for _ in range(3):
        bump()
        with httpx.Client(timeout=60) as c:
            cold.append(one(c, url, tok, sub))
    warm = []
    with httpx.Client(timeout=60) as c:
        one(c, url, tok, sub)           # làm nóng TLS (không tính)
        for _ in range(5):
            warm.append(one(c, url, tok, sub))
    assert all(ok for _, ok in cold + warm), (label, cold, warm)
    cs = [round(m) for m, _ in cold]; ws = [round(m) for m, _ in warm]
    print(f"{label}: lạnh(3 lần, gồm TLS+Lambda cold) = {cs} | ấm(5) = {ws} | ấm trung vị {statistics.median(ws)} ms")
    return {"cold": cs, "warm": ws}


if __name__ == "__main__":
    tk = tokens(); A = tk["user-a"]
    out = {}
    # baseline: Lambda invoke trực tiếp (ấm)
    ts = []
    for _ in range(6):
        t0 = time.perf_counter(); lam.invoke(FunctionName=PREFIX + "ledger", Payload=json.dumps({"user_id": A["sub"], "_tool": "get_jar_balances"}).encode())
        ts.append(round((time.perf_counter() - t0) * 1000))
    print("Lambda invoke trực tiếp (ấm, bỏ lần đầu):", ts[1:]); out["lambda_direct"] = ts[1:]
    out["C0 plain"] = measure("C0 gateway trơn (không interceptor, không policy)", PLAIN["url"], A["access"], A["sub"])
    # C1: chỉ interceptor
    update_gateway(MAIN["id"], policyEngineConfiguration=None); time.sleep(8)
    g = ac.get_gateway(gatewayIdentifier=MAIN["id"]); print("  engine còn gắn?", "policyEngineConfiguration" in g, "| interceptors:", len(g.get("interceptorConfigurations", [])))
    out["C1 interceptor"] = measure("C1 chỉ interceptor (overwrite)", MAIN["url"], A["access"], A["sub"])
    # C3: cả hai
    update_gateway(MAIN["id"], policyEngineConfiguration={"arn": eng["arn"], "mode": "ENFORCE"}); time.sleep(8)
    out["C3 interceptor+policy"] = measure("C3 interceptor + policy ENFORCE", MAIN["url"], A["access"], A["sub"])
    # C2: chỉ policy
    update_gateway(MAIN["id"], interceptorConfigurations=None); time.sleep(8)
    g = ac.get_gateway(gatewayIdentifier=MAIN["id"]); print("  interceptors còn?", len(g.get("interceptorConfigurations", [])), "| engine:", g.get("policyEngineConfiguration", {}).get("mode"))
    out["C2 policy"] = measure("C2 chỉ policy ENFORCE", MAIN["url"], A["access"], A["sub"])
    # trả lại cấu hình đầy đủ
    update_gateway(MAIN["id"], interceptorConfigurations=interceptor_cfg(True)); time.sleep(8)
    (HERE / "latency_result.json").write_text(json.dumps(out, indent=1))
