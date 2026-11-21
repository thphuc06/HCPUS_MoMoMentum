"""Q1: giới hạn tên target/tool; gateway có kiểm schema đầu vào không; header do client gửi."""
import json, time
from botocore.exceptions import ClientError
from gw import *
from mcpcall import *
G = load_state()["gateways"]["plain"]; gid = G["id"]
tk = tokens(); A, B = tk["user-a"], tk["user-b"]
def tool(name): return {"name": name, "description": "t", "inputSchema": {"type": "object", "properties": {"user_id": {"type": "string"}}}}
def try_target(label, tname, toolname):
    try:
        t = create_target(gid, name=tname, tools=[tool(toolname)], headers=None)
        status = t["status"]; why = t.get("statusReasons")
        ok = status == "READY"
        names = []
        if ok:
            names = [x["name"] for x in Gw(G["url"], A["access"]).list_tools().tools if x["name"].startswith(tname) if False] if False else []
        print(f"{label}: target={status} {why or ''}")
        ac.delete_gateway_target(gatewayIdentifier=gid, targetId=t["targetId"])
        for _ in range(40):
            if not [x for x in ac.list_gateway_targets(gatewayIdentifier=gid)["items"] if x["targetId"] == t["targetId"]]: break
            time.sleep(2)
    except ClientError as e:
        print(f"{label}: REJECT {e.response['Error']['Code']}: {e.response['Error']['Message'][:200]}")
    except Exception as e:
        print(f"{label}: EXC {type(e).__name__} {str(e)[:200]}")
try_target("target 100 ký tự chữ", "a"*100, "t")
try_target("target 101 ký tự chữ", "a"*101, "t")
try_target("target 'a-a-...' 199 ký tự (khớp pattern)", "-".join("a"*100), "t")
try_target("target có gạch dưới 'my_t'", "my_t", "t")
try_target("target có dấu chấm 'my.t'", "my.t", "t")
try_target("tool name 128 ký tự", "tt", "a"*128)
try_target("tool name 129 ký tự", "tt", "a"*129)
try_target("tool name gạch dưới 'get_x'", "tt", "get_x")
try_target("tool name dấu chấm 'get.x'", "tt", "get.x")
try_target("tool name gạch nối 'get-x'", "tt", "get-x")
try_target("tool name có '___' bên trong 'a___b'", "tt", "a___b")
