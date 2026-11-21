"""Phép thử: Strands `MCPClient` (qua `yofina_agent.tools.GatewayTools`) với Gateway thật.

Ghi lại: tên tool thấy được, header Authorization đi nguyên vẹn, kết quả khi Cedar từ chối (-32002) và khi token
xấu; agent trả gì cho người dùng (ToolKind + thông điệp tiếng Việt). Không gọi model.

    uv run spikes/vertical-slice/probe_strands_mcp.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from _demo_auth import login_access_token  # noqa: E402
from _yofina import session, ssm_param  # noqa: E402
from yofina_agent.identity import Identity, identity_from_authorization  # noqa: E402
from yofina_agent.tools import GatewayTools, _make_mcp_client  # noqa: E402


def show(label: str, outcome) -> dict:
    row = {
        "case": label,
        "kind": outcome.kind.value,
        "code": outcome.code,
        "user_message": outcome.message,
        "detail": (outcome.detail or "")[:300],
        "payload_status": (outcome.payload or {}).get("status"),
    }
    print(json.dumps(row, ensure_ascii=False))
    return row


async def main() -> None:
    sess = session()
    url = ssm_param("gateway_url", sess=sess)
    token = login_access_token("minh", sess=sess)
    identity = identity_from_authorization(f"Bearer {token}")
    rows = []

    tools = GatewayTools(url, identity, call_timeout=20, startup_timeout=15)
    try:
        # tên tool thật do MCPClient của Strands thấy
        client = await tools._ensure()
        listed = await asyncio.to_thread(client.list_tools_sync)
        names = sorted(t.tool_name for t in listed)
        print(json.dumps({"case": "list_tools", "names": names}, ensure_ascii=False))
        rows.append({"case": "list_tools", "names": names})
        rows.append(
            show(
                "get_jar_balances (không user_id)",
                await tools.call("ledger___get_jar_balances", {}),
            )
        )
        rows.append(
            show(
                "move không token (hợp lệ)",
                await tools.call(
                    "ledger___move_between_jars",
                    {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100000},
                ),
            )
        )
        rows.append(
            show(
                "Cedar từ chối: vượt hạn mức",
                await tools.call(
                    "ledger___move_between_jars",
                    {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 60000000},
                ),
            )
        )
        rows.append(
            show(
                "Cedar từ chối: confirm_token không có dấu chấm",
                await tools.call(
                    "ledger___move_between_jars",
                    {
                        "from_jar": "giai_tri",
                        "to_jar": "an_uong",
                        "amount_vnd": 1000,
                        "confirm_token": "khongcodau",
                    },
                ),
            )
        )
        rows.append(
            show(
                "lỗi nghiệp vụ: hũ không tồn tại (tool trả ERROR)",
                await tools.call(
                    "ledger___move_between_jars",
                    {"from_jar": "khong_co", "to_jar": "an_uong", "amount_vnd": 1000},
                ),
            )
        )
        rows.append(
            show(
                "Gateway kiểm schema: amount_vnd sai kiểu",
                await tools.call(
                    "ledger___move_between_jars",
                    {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": "mot trieu"},
                ),
            )
        )
        rows.append(show("tool không tồn tại", await tools.call("ledger___khong_co_tool", {})))
    finally:
        await tools.aclose()

    # token xấu: Gateway từ chối ngay lúc mở phiên MCP (HTTP 401/403)
    bad = GatewayTools(
        url, Identity(sub="x", token="abc.def.ghi"), call_timeout=20, startup_timeout=15
    )
    rows.append(show("token rác", await bad.call("ledger___get_jar_balances", {})))
    await bad.aclose()
    _ = _make_mcp_client

    out = REPO / "spikes" / "vertical-slice" / "out" / "probe_strands_mcp.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
