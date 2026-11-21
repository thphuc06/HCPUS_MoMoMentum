"""MCP server local nhỏ (mcp 2.x: MCPServer, không còn FastMCP). Chạy: python mcp_server.py [port]  -> http://127.0.0.1:PORT/mcp"""
import sys
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("yofina-ledger")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8201


@mcp.tool()
def get_jar_balances() -> dict:
    """Số dư các hũ (dữ liệu giả)."""
    return {"an_uong": 1_250_000, "di_lai": 640_000, "giai_tri": 420_000}


if __name__ == "__main__":
    mcp.run("streamable-http", host="127.0.0.1", port=PORT)
