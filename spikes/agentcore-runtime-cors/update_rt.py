"""Cập nhật runtime (tạo version mới) từ create.json với vài ghi đè. Dùng: update_rt.py <runtime_id> <create.json> key=value ...
Ghi đè hỗ trợ: zip=<prefix>, cors=on|off, audience=<id>|none (đặt allowedAudience thay allowedClients), both=1 (cả hai), entry=otel|plain, env.K=V"""
import json, sys, boto3, time
rid, cj, *kv = sys.argv[1:]
d = json.load(open(cj)); d.pop("agentRuntimeName"); d.pop("tags", None); d.pop("platformVersion", None); d["agentRuntimeId"] = rid
a = d["authorizerConfiguration"]["customJWTAuthorizer"]; clients = a["allowedClients"]
for x in kv:
    k, v = x.split("=", 1)
    if k == "zip": d["agentRuntimeArtifact"]["codeConfiguration"]["code"]["s3"]["prefix"] = v
    elif k == "cors": d["environmentVariables"]["SPIKE_CORS"] = v
    elif k == "audience": a.pop("allowedClients"); a["allowedAudience"] = clients
    elif k == "both": a["allowedAudience"] = clients
    elif k == "entry": d["agentRuntimeArtifact"]["codeConfiguration"]["entryPoint"] = ["opentelemetry-instrument", "main.py"] if v == "otel" else ["main.py"]
    elif k.startswith("env."): d["environmentVariables"][k[4:]] = v
c = boto3.client("bedrock-agentcore-control", region_name="ap-southeast-1")
r = c.update_agent_runtime(**d); print("version", r["agentRuntimeVersion"], r["status"])
t0 = time.time()
while True:
    g = c.get_agent_runtime(agentRuntimeId=rid)
    if g["status"] not in ("UPDATING", "CREATING"): break
    time.sleep(5)
print(g["status"], "after", round(time.time() - t0), "s", g.get("failureReason", ""), "authorizer:", json.dumps(g["authorizerConfiguration"]["customJWTAuthorizer"]).replace(d["authorizerConfiguration"]["customJWTAuthorizer"]["discoveryUrl"], "<disc>"), g["environmentVariables"])
