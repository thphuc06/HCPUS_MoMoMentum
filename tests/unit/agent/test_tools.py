import copy
import json

import pytest
from agent_helpers import fixture, mcp_ok
from mcp.shared.exceptions import MCPError
from yofina_agent.compact import (
    allowed_amounts,
    compact_confirm,
    compact_jars,
    compact_transactions,
)
from yofina_agent.tools import (
    ContractMismatch,
    ToolKind,
    classify_exception,
    classify_result,
    confirm_block,
    jar_summary_block,
)

from yofina_core import blocks as B

TRACE = "8f3a21c94b7e4d0aa1c25e6f7b8c9d01"


def test_ket_qua_ok_va_needs_confirmation():
    ok = classify_result("t", mcp_ok(fixture("get_jar_balances.ok.json")))
    assert ok.kind is ToolKind.OK and ok.ok
    nc = classify_result("t", mcp_ok(fixture("move_between_jars.needs_confirmation.json")))
    assert nc.kind is ToolKind.NEEDS_CONFIRMATION and nc.ok


def test_ket_qua_status_error_giu_ma_va_thong_diep_cua_tool():
    o = classify_result("t", mcp_ok(fixture("move_between_jars.error_token_reused.json")))
    assert (o.kind, o.code) == (ToolKind.TOOL_ERROR, "TOKEN_REUSED")
    assert o.message == "Token xác nhận đã được dùng."
    unknown = classify_result("t", mcp_ok({"status": "ERROR", "code": "MA_LA", "message": "m"}))
    assert unknown.code == "INTERNAL_ERROR"


def test_structured_content_duoc_uu_tien_va_text_json_van_doc_duoc():
    payload = fixture("get_jar_balances.ok.json")
    via_struct = classify_result(
        "t", {"status": "success", "content": [{"text": "bỏ qua"}], "structuredContent": payload}
    )
    assert via_struct.kind is ToolKind.OK
    via_text = classify_result("t", mcp_ok(payload))
    assert via_text.payload == payload


def test_loi_gateway_validation_va_loi_khac():
    v = classify_result(
        "t",
        {
            "status": "error",
            "content": [{"text": "ValidationException - Missing required field(s)"}],
        },
    )
    assert (v.kind, v.code) == (ToolKind.TOOL_ERROR, "PARAMS_INVALID")
    other = classify_result(
        "t", {"status": "error", "isError": True, "content": [{"text": "boom"}]}
    )
    assert (other.kind, other.code) == (ToolKind.TOOL_ERROR, "INTERNAL_ERROR")


def test_ket_qua_khong_doc_duoc_hoac_status_la():
    assert (
        classify_result("t", {"status": "success", "content": [{"text": "không phải json"}]}).kind
        is ToolKind.BAD_RESULT
    )
    assert classify_result("t", mcp_ok({"status": "???"})).kind is ToolKind.BAD_RESULT
    assert classify_result("t", None).kind is ToolKind.BAD_RESULT


def test_cedar_tu_choi_la_loi_giao_thuc_va_bi_boc_trong_exception_group():
    denied = MCPError(
        -32002, "Tool Execution Denied: Tool call not allowed due to policy enforcement"
    )
    direct = classify_exception("t", denied)
    grouped = classify_exception("t", ExceptionGroup("unhandled errors in a TaskGroup", [denied]))
    nested = classify_exception("t", ExceptionGroup("outer", [ExceptionGroup("inner", [denied])]))
    for o in (direct, grouped, nested):
        assert (o.kind, o.code) == (ToolKind.DENIED, "FORBIDDEN")
        assert "-32002" in (o.detail or "")
        assert "policy" not in (o.message or "")  # không lộ chi tiết chính sách cho người dùng


def test_mcp_error_khac_va_loi_ket_noi():
    o = classify_exception("t", MCPError(-32602, "Unknown tool"))
    assert (o.kind, o.code) == (ToolKind.TOOL_ERROR, "INTERNAL_ERROR")
    t = classify_exception("t", TimeoutError("hết giờ"))
    assert (t.kind, t.code) == (ToolKind.UNAVAILABLE, "DATABASE_UNAVAILABLE")


def test_khoi_jar_summary_dung_tu_ket_qua_tool():
    o = classify_result("ledger___get_jar_balances", mcp_ok(fixture("get_jar_balances.ok.json")))
    block = jar_summary_block(o, TRACE)
    wire = B.block_to_wire(block)
    assert wire["type"] == "jar_summary" and wire["id"] == f"jar_summary:{TRACE}"
    assert [j["code"] for j in wire["data"]["jars"]][:2] == ["an_uong", "di_lai"]
    assert wire["data"]["jars_total_vnd"] == 7_730_000
    assert wire["source"]["tool"] == "ledger___get_jar_balances"
    B.parse_block(wire)  # hợp lệ theo hợp đồng


def test_khoi_confirm_chua_dung_du_lieu_tool_tra_va_hash_khop():
    o = classify_result(
        "ledger___move_between_jars", mcp_ok(fixture("move_between_jars.needs_confirmation.json"))
    )
    block = confirm_block(o, TRACE)
    wire = B.block_to_wire(block)
    tool_data = o.payload["data"]
    assert wire["data"]["params"] == tool_data["params"]
    assert wire["data"]["params_hash"] == tool_data["params_hash"]
    assert wire["data"]["preview"] == tool_data["preview"]
    assert wire["data"]["summary"] == "Chuyển 100.000 ₫ từ Giải trí sang Ăn uống"
    assert wire["id"] == f"confirm:{TRACE}:{tool_data['params_hash'][:12]}"
    # agent không điền token hay cờ xác nhận nào vào khối
    assert "token" not in json.dumps(wire).lower() and "confirmed" not in json.dumps(wire).lower()
    B.parse_block(wire)


def test_khoi_confirm_tu_choi_khi_hash_hoac_preview_lech():
    base = fixture("move_between_jars.needs_confirmation.json")
    bad_hash = copy.deepcopy(base)
    bad_hash["data"]["params_hash"] = "0" * 64
    with pytest.raises(ContractMismatch):
        confirm_block(classify_result("t", mcp_ok(bad_hash)), TRACE)
    bad_preview = copy.deepcopy(base)
    bad_preview["data"]["preview"]["from"]["after_vnd"] = 1
    with pytest.raises(ContractMismatch):
        confirm_block(classify_result("t", mcp_ok(bad_preview)), TRACE)
    bad_shape = copy.deepcopy(base)
    del bad_shape["data"]["expires_at"]
    with pytest.raises(ContractMismatch):
        confirm_block(classify_result("t", mcp_ok(bad_shape)), TRACE)


def test_ban_gon_chi_co_so_can_thiet_va_so_da_dinh_dang():
    jars = compact_jars(fixture("get_jar_balances.ok.json"))
    assert set(jars["jars"][0]) == {
        "code",
        "name",
        "balance_vnd",
        "balance_text",
    }  # không màu/biểu tượng/tỷ lệ
    assert (
        jars["jars_total_text"] == "7.730.000 ₫" and jars["jars"][0]["balance_text"] == "380.000 ₫"
    )
    names = {j["code"]: j["name"] for j in jars["jars"]}
    tx = compact_transactions(fixture("query_transactions.ok.json"), names, limit=1)
    assert tx["shown"] == 1 and tx["has_more"] is True and tx["transactions"][0]["jar"] == "Ăn uống"
    cf = compact_confirm(fixture("move_between_jars.needs_confirmation.json")["data"])
    assert "params_hash" not in json.dumps(cf) and cf["amount_text"] == "100.000 ₫"
    assert cf["from_jar"]["balance_after_text"] == "660.000 ₫"


def test_can_cu_so_tien_gom_ca_so_tong_va_so_trong_chuoi():
    jars = compact_jars(fixture("get_jar_balances.ok.json"))
    allowed = allowed_amounts(jars)
    assert {380_000, 7_730_000, 2_700_000} <= allowed
    cf = allowed_amounts(
        compact_confirm(fixture("move_between_jars.needs_confirmation.json")["data"])
    )
    assert {100_000, 660_000, 480_000, 760_000, 380_000} <= cf


def test_can_cu_so_tien_gom_so_tien_am_cua_giao_dich_duoi_dang_duong():
    names = {"an_uong": "Ăn uống", "giai_tri": "Giải trí"}
    tx = compact_transactions(fixture("query_transactions.ok.json"), names, limit=5)
    allowed = allowed_amounts(tx)
    assert {45_000, 100_000} <= allowed  # sổ cái ghi -45000 và -100000
    assert ungrounded("Bạn đã chi 45.000 ₫ tại Quán cơm ngày 20/11/2026.", allowed) == []


def ungrounded(text, allowed):
    from yofina_agent.textutil import ungrounded_amounts

    return ungrounded_amounts(text, allowed)


def test_hai_loi_goi_dau_song_song_chi_mo_mot_phien_mcp():
    """#11: `_ensure` có khóa nên hai lời gọi tool đầu tiên chạy song song dùng chung MỘT phiên MCP."""
    import asyncio
    import time

    from yofina_agent.identity import Identity
    from yofina_agent.tools import GatewayTools

    made = []

    class FakeClient:
        last_exception = None

        def start(self):
            time.sleep(0.05)  # mở phiên mất thời gian: lời gọi thứ hai tới khi phiên đầu chưa xong

        async def call_tool_async(self, tool_use_id, name, arguments, read_timeout_seconds=None):
            return mcp_ok({"status": "OK", "data": {"tool": name}})

        def stop(self, *a):
            pass

    def factory(url, headers, startup_timeout):
        made.append(FakeClient())
        return made[-1]

    tools = GatewayTools(
        "https://gw.example/mcp",
        Identity("user-a", "Bearer x"),
        call_timeout=5,
        startup_timeout=5,
        client_factory=factory,
    )

    async def main():
        return await asyncio.gather(tools.call("a", {}), tools.call("b", {}))

    a, b = asyncio.run(main())
    assert a.ok and b.ok
    assert len(made) == 1


def test_token_het_han_luc_mo_phien_mcp_thanh_can_dang_nhap_lai():
    exc = ExceptionGroup(
        "init", [ExceptionGroup("inner", [MCPError(-32001, "Invalid Bearer token")])]
    )
    o = classify_exception("t", exc)
    assert o.kind is ToolKind.TOOL_ERROR and o.code == "UNAUTHENTICATED"
    assert "đăng nhập" in o.message
    # cùng mã nhưng không phải lỗi token thì không đổi thành UNAUTHENTICATED
    other = classify_exception("t", MCPError(-32001, "Request timed out"))
    assert other.code == "INTERNAL_ERROR"


def test_token_het_han_ra_insufficient_scope_khong_bi_nham_voi_cedar():
    msg = "insufficient_scope - The request requires higher privileges than provided by the access token."
    o = classify_exception("t", ExceptionGroup("g", [MCPError(-32002, msg)]))
    assert o.kind is ToolKind.TOOL_ERROR and o.code == "UNAUTHENTICATED"
    cedar = classify_exception(
        "t", MCPError(-32002, "Tool Execution Denied: ... (denied by default).")
    )
    assert cedar.kind is ToolKind.DENIED and cedar.code == "FORBIDDEN"
