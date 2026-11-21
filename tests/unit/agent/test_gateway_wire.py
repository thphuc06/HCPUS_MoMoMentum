"""MCPClient thật của Strands nói chuyện với mock MCP cục bộ (tests/support): kiểm trên dây thật
việc chuyển token, đọc kết quả, lỗi giao thức -32002 của Cedar. Không gọi Bedrock, không chạm AWS."""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest
from agent_helpers import make_jwt, run

SUPPORT = Path(__file__).resolve().parents[2] / "support"
sys.path.insert(0, str(SUPPORT))

import mock_ledger_mcp as mock  # noqa: E402
from yofina_agent.identity import Identity  # noqa: E402
from yofina_agent.tools import GatewayTools, ToolKind, confirm_block, jar_summary_block  # noqa: E402

from yofina_core import blocks as B  # noqa: E402

PREFIX = "ledger___"
TRACE = "8f3a21c94b7e4d0aa1c25e6f7b8c9d01"


@pytest.fixture(scope="module")
def server():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = mock.RunningMock(port).start()
    yield srv
    srv.stop()


@pytest.fixture(autouse=True)
def reset_seen():
    mock.SEEN["subs"].clear()
    mock.SEEN["calls"].clear()


def tools_for(server, sub="user-a", token=None):
    ident = Identity(sub, token or make_jwt(sub))
    return GatewayTools(server.url, ident, call_timeout=10, startup_timeout=10)


def call(server, name, args, **kw):
    async def go():
        t = tools_for(server, **kw)
        try:
            return await t.call(PREFIX + name, args)
        finally:
            await t.aclose()

    return run(go())


def test_doc_so_du_va_token_nguyen_ven_toi_server(server):
    o = call(server, "get_jar_balances", {}, sub="user-xyz")
    assert o.kind is ToolKind.OK
    assert B.block_to_wire(jar_summary_block(o, TRACE))["data"]["jars_total_vnd"] == 7_730_000
    assert set(mock.SEEN["subs"]) == {
        "user-xyz"
    }  # header Authorization của đúng người dùng đã tới server
    assert mock.SEEN["calls"] == [
        ("get_jar_balances", {"user_id": None})
    ]  # agent không tự điền user_id


def test_chuyen_hu_khong_token_tra_needs_confirmation_va_khoi_hop_le(server):
    args = {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100000}
    o = call(server, "move_between_jars", args)
    assert o.kind is ToolKind.NEEDS_CONFIRMATION
    wire = B.block_to_wire(confirm_block(o, TRACE))
    assert wire["data"]["summary"] == "Chuyển 100.000 ₫ từ Giải trí sang Ăn uống"
    assert (
        mock.SEEN["calls"][0][1]["confirm_token"] is None
        and mock.SEEN["calls"][0][1]["user_id"] is None
    )


def test_cedar_tu_choi_la_loi_giao_thuc_va_duoc_phan_loai(server):
    o = call(
        server,
        "move_between_jars",
        {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 90_000_000},
    )
    assert (o.kind, o.code) == (ToolKind.DENIED, "FORBIDDEN")
    assert "-32002" in (o.detail or "")


def test_loi_nghiep_vu_cua_tool_giu_ma_va_thong_diep(server):
    o = call(
        server,
        "move_between_jars",
        {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 4_000_000},
    )
    assert (o.kind, o.code) == (ToolKind.TOOL_ERROR, "INSUFFICIENT_FUNDS")
    assert "không đủ số dư" in (o.message or "")
    nf = call(
        server,
        "move_between_jars",
        {"from_jar": "khong_co", "to_jar": "an_uong", "amount_vnd": 1000},
    )
    assert nf.code == "JAR_NOT_FOUND"


def test_tool_khong_ton_tai_va_thieu_tham_so_la_loi_co_kieu(server):
    unknown = call(server, "khong_co_tool", {})
    assert unknown.kind is ToolKind.TOOL_ERROR
    missing = call(server, "move_between_jars", {"from_jar": "giai_tri"})
    assert missing.kind is ToolKind.TOOL_ERROR


def test_thieu_token_thi_server_tu_choi_va_agent_bao_khong_san_sang(server):
    async def go():
        t = GatewayTools(
            server.url, Identity("u", "khong.phai.jwt"), call_timeout=5, startup_timeout=5
        )
        try:
            return await t.call(PREFIX + "get_jar_balances", {})
        finally:
            await t.aclose()

    o = run(go())
    assert o.kind is ToolKind.UNAVAILABLE and o.code == "DATABASE_UNAVAILABLE"


def test_query_transactions_loc_theo_hu_va_gioi_han(server):
    o = call(server, "query_transactions", {"jar": "an_uong", "limit": 1})
    assert o.kind is ToolKind.OK
    rows = o.payload["data"]["transactions"]
    assert len(rows) == 1 and rows[0]["jar"] == "an_uong"
