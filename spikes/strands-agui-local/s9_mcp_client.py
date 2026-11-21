"""Mục 9: Strands MCPClient + streamable_http_client (mcp 2.x) tới MCP server local.
Chạy server trước: python mcp_server.py 8201"""
import sys
from mcp.client.streamable_http import streamable_http_client
from strands import Agent
from strands.tools.mcp import MCPClient
from common import model

URL = "http://127.0.0.1:8201/mcp"

# Cách 1: url= (SDK tự dựng transport)
c1 = MCPClient(url=URL, prefix="gateway")
with c1:
    tools = c1.list_tools_sync()
    print("tool names (url=, prefix='gateway'):", [t.tool_name for t in tools])
    r = c1.call_tool_sync("t1", "get_jar_balances", {})
    print("call_tool_sync status:", r["status"], "|", str(r["content"])[:120])

# Cách 2: lambda factory (mẫu FAST) với tên import của mcp 2.x
c2 = MCPClient(lambda: streamable_http_client(URL), prefix="gateway")
if len(sys.argv) > 1 and sys.argv[1] == "agent":
    a = Agent(model=model(512), tools=[c2], callback_handler=None,
              system_prompt="Trả lời ngắn tiếng Việt, dùng tool để lấy số.")
    res = a("Hũ ăn uống còn bao nhiêu?")
    used = [c["toolUse"]["name"] for m in a.messages for c in m["content"] if "toolUse" in c]
    print("agent used tools:", used, "| answer:", str(res).strip()[:150])
else:
    with c2:
        print("lambda factory tools:", [t.tool_name for t in c2.list_tools_sync()])
