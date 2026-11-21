"""Test lượt hội thoại: thứ tự event AG-UI, khối UI, ánh xạ hũ, xác nhận, đường suy giảm."""

from __future__ import annotations

import asyncio
import json

from agent_helpers import (
    FakeTools,
    FakeUsage,
    FakeWriter,
    agent_settings,
    blocks_of,
    check_agui_order,
    fixture,
    make_llm,
    mcp_ok,
    route_response,
    run_turn,
    types,
)
from yofina_agent.tools import ToolKind, ToolOutcome, classify_result

from yofina_core.errors import ErrorCode
from yofina_core.llm import ModelBudgetExceeded

JAR_TOOL = "ledger___get_jar_balances"


def result_of(events):
    return events[-1].result


def block_types(events):
    return [b["type"] for b in blocks_of(events)]


def tool_names(events):
    return [e.tool_call_name for e in events if e.type.value == "TOOL_CALL_START"]


# --- đường nhanh số dư -----------------------------------------------------------------------
def test_so_du_thu_tu_event_va_khoi_truoc_tool_call_result(monkeypatch):
    llm = make_llm([route_response(intent="balance_lookup")])
    events, tools, writer = run_turn(
        "hỏi gì cũng được",
        llm=llm,
        monkeypatch=monkeypatch,
        writer=FakeWriter(["Tổng ", "7.730.000 ₫."]),
    )
    check_agui_order(events)
    t = types(events)
    assert t == [
        "RUN_STARTED",
        "TOOL_CALL_START",
        "TOOL_CALL_END",  # tool không tham số: không có TOOL_CALL_ARGS
        "ACTIVITY_SNAPSHOT",
        "TOOL_CALL_RESULT",
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "RUN_FINISHED",
    ]
    snap = next(e for e in events if e.type.value == "ACTIVITY_SNAPSHOT")
    assert snap.activity_type == "yofina.block" and snap.replace is True
    assert snap.message_id == snap.content["id"] == f"jar_summary:{events[-1].result['trace_id']}"
    assert snap.content["type"] == "jar_summary" and len(snap.content["data"]["jars"]) == 7
    # model chỉ thấy bản gọn: TOOL_CALL_RESULT không có màu/biểu tượng; writer nhận cùng bản gọn
    res = json.loads(next(e for e in events if e.type.value == "TOOL_CALL_RESULT").content)
    assert "color_key" not in json.dumps(res) and res["jars_total_text"] == "7.730.000 ₫"
    assert writer.calls[0]["task"] == "balance" and writer.calls[0]["compact"] == res
    assert tools.calls == [("get_jar_balances", {})]
    assert tool_names(events) == [JAR_TOOL]
    r = result_of(events)
    assert (r["intent"], r["degraded"], r["model_calls"], r["tool_calls"]) == (
        "balance_lookup",
        False,
        1,
        1,
    )
    assert events[-1].usage[0].model == "m-small-a"
    assert tools.closed


def test_agent_khong_bao_gio_gui_user_id(monkeypatch):
    llm = make_llm([route_response(intent="balance_lookup")])
    _, tools, _ = run_turn("số dư", llm=llm, monkeypatch=monkeypatch)
    assert all("user_id" not in args for _, args in tools.calls)


def test_lich_su_hoi_thoai_duoc_dua_cho_router(monkeypatch):
    llm = make_llm([route_response(intent="balance_lookup")])
    msgs = [
        {"id": "1", "role": "user", "content": "chào"},
        {"id": "2", "role": "assistant", "content": "Chào bạn"},
        {"id": "3", "role": "system", "content": "Đã chuyển 100.000 ₫ từ A sang B"},
        {"id": "4", "role": "user", "content": "còn bao nhiêu"},
    ]
    run_turn(None, llm=llm, monkeypatch=monkeypatch, messages=msgs)
    prompt = llm[1].calls[0]["messages"][0]["content"][0]["text"]
    assert (
        "Người dùng: chào" in prompt
        and "Yofina: Chào bạn" in prompt
        and "Ứng dụng: Đã chuyển" in prompt
    )
    assert prompt.rstrip().endswith("còn bao nhiêu\n</cau_moi>")


# --- chuyển tiền giữa hũ ------------------------------------------------------------------------
def test_chuyen_hu_goi_tool_khong_token_va_phat_khoi_confirm(monkeypatch):
    llm = make_llm(
        [
            route_response(
                intent="move_between_jars",
                from_jar_text="Giải trí",
                to_jar_text="ăn uống",
                amount_vnd=100000,
            )
        ]
    )
    events, tools, writer = run_turn(
        "chuyển 100 nghìn từ Giải trí sang Ăn uống", llm=llm, monkeypatch=monkeypatch
    )
    check_agui_order(events)
    # tên hũ gõ ra được ánh xạ sang mã bằng dữ liệu hũ của người dùng (get_jar_balances trước)
    assert [c[0] for c in tools.calls] == ["get_jar_balances", "move_between_jars"]
    move_args = tools.calls[1][1]
    assert move_args == {
        "from_jar": "giai_tri",
        "to_jar": "an_uong",
        "amount_vnd": 100000,
    }  # không token, không cờ, không user_id
    assert block_types(events) == ["confirm"]
    confirm = blocks_of(events)[0]
    tool_data = fixture("move_between_jars.needs_confirmation.json")["data"]
    assert (
        confirm["data"]["params"] == tool_data["params"]
        and confirm["data"]["params_hash"] == tool_data["params_hash"]
    )
    assert writer.calls[0]["task"] == "confirm_move"
    assert "params_hash" not in json.dumps(writer.calls[0]["compact"])
    # khối confirm phát trước TOOL_CALL_RESULT của chính tool đó
    t = types(events)
    last_snapshot = max(i for i, x in enumerate(t) if x == "ACTIVITY_SNAPSHOT")
    last_result = max(i for i, x in enumerate(t) if x == "TOOL_CALL_RESULT")
    assert last_snapshot < last_result


def test_chuyen_hu_thieu_so_tien_thi_hoi_lai_khong_goi_tool(monkeypatch):
    llm = make_llm(
        [
            route_response(
                intent="move_between_jars",
                from_jar_text="giải trí",
                to_jar_text="ăn uống",
                needs_clarification=True,
                reply="Bạn muốn chuyển bao nhiêu?",
            )
        ]
    )
    events, tools, _ = run_turn("chuyển từ giải trí sang ăn uống", llm=llm, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert tools.calls == []
    assert [e.delta for e in events if e.type.value == "TEXT_MESSAGE_CONTENT"] == [
        "Bạn muốn chuyển bao nhiêu?"
    ]


def test_chuyen_hu_khong_ro_ten_hu_thi_hien_so_du_that_va_hoi_lai(monkeypatch):
    llm = make_llm(
        [
            route_response(
                intent="move_between_jars",
                from_jar_text="quỹ nhà",
                to_jar_text="ăn uống",
                amount_vnd=50000,
            )
        ]
    )
    events, tools, writer = run_turn(
        "chuyển 50k từ quỹ nhà sang ăn uống", llm=llm, monkeypatch=monkeypatch
    )
    check_agui_order(events)
    assert [c[0] for c in tools.calls] == ["get_jar_balances"]  # không gọi tool ghi
    assert block_types(events) == ["jar_summary"]
    assert writer.calls[0]["task"] == "clarify"
    assert "quỹ nhà" in writer.calls[0]["compact"]["van_de"]
    assert "Ăn uống" in writer.calls[0]["compact"]["cac_hu_hien_co"]


def test_chuyen_cung_mot_hu_thi_hoi_lai(monkeypatch):
    llm = make_llm(
        [
            route_response(
                intent="move_between_jars",
                from_jar_text="ăn uống",
                to_jar_text="Ăn uống",
                amount_vnd=1000,
            )
        ]
    )
    _events, tools, writer = run_turn("chuyển", llm=llm, monkeypatch=monkeypatch)
    assert [c[0] for c in tools.calls] == ["get_jar_balances"] and writer.calls[0][
        "task"
    ] == "clarify"


def test_tool_ghi_bi_cedar_tu_choi_thi_notice_va_khong_co_khoi_confirm(monkeypatch):
    denied = ToolOutcome(
        "x", ToolKind.DENIED, code="FORBIDDEN", message="Bạn không có quyền thực hiện thao tác này."
    )
    llm = make_llm(
        [
            route_response(
                intent="move_between_jars",
                from_jar_text="giải trí",
                to_jar_text="ăn uống",
                amount_vnd=99000000,
            )
        ]
    )
    events, _tools, writer = run_turn(
        "chuyển", llm=llm, monkeypatch=monkeypatch, tools=FakeTools({"move_between_jars": denied})
    )
    check_agui_order(events)
    assert block_types(events) == ["notice"]
    n = blocks_of(events)[0]["data"]
    assert (n["kind"], n["code"]) == ("error", "FORBIDDEN") and "quyền" in n["message"]
    assert writer.calls == []
    res = json.loads([e for e in events if e.type.value == "TOOL_CALL_RESULT"][-1].content)
    assert (
        res["status"] == "ERROR" and res["code"] == "FORBIDDEN"
    )  # lỗi được báo bằng kết quả có cấu trúc


def test_khong_du_so_du_hien_the_so_du_va_notice(monkeypatch):
    err = classify_result(
        "x",
        mcp_ok(
            {
                "status": "ERROR",
                "code": "INSUFFICIENT_FUNDS",
                "message": "Hũ Giải trí không đủ số dư để chuyển.",
            }
        ),
    )
    llm = make_llm(
        [
            route_response(
                intent="move_between_jars",
                from_jar_text="giải trí",
                to_jar_text="ăn uống",
                amount_vnd=5000000,
            )
        ]
    )
    events, _, _ = run_turn(
        "chuyển", llm=llm, monkeypatch=monkeypatch, tools=FakeTools({"move_between_jars": err})
    )
    check_agui_order(events)
    assert block_types(events) == ["jar_summary", "notice"]
    assert blocks_of(events)[1]["data"]["code"] == "INSUFFICIENT_FUNDS"


def test_tool_ghi_tra_ok_khi_chua_co_token_la_loi_nghiem_trong(monkeypatch):
    ok = classify_result("x", mcp_ok(fixture("move_between_jars.ok.json")))
    llm = make_llm(
        [
            route_response(
                intent="move_between_jars",
                from_jar_text="giải trí",
                to_jar_text="ăn uống",
                amount_vnd=1000,
            )
        ]
    )
    events, _, writer = run_turn(
        "chuyển", llm=llm, monkeypatch=monkeypatch, tools=FakeTools({"move_between_jars": ok})
    )
    check_agui_order(events)
    assert (
        block_types(events) == ["notice"]
        and blocks_of(events)[0]["data"]["code"] == "INTERNAL_ERROR"
    )
    assert writer.calls == []  # không nói gì về việc "đã chuyển"


# --- tra giao dịch -----------------------------------------------------------------------------
def test_tra_giao_dich_anh_xa_hu_va_khong_co_khoi(monkeypatch):
    llm = make_llm([route_response(intent="transactions_lookup", jar_text="ăn uống", limit=5)])
    events, tools, writer = run_turn("giao dịch hũ ăn uống", llm=llm, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert [c[0] for c in tools.calls] == ["get_jar_balances", "query_transactions"]
    assert tools.calls[1][1] == {"jar": "an_uong", "limit": 5}
    assert block_types(events) == []
    assert writer.calls[0]["task"] == "transactions"
    assert writer.calls[0]["compact"]["transactions"][0]["jar"] == "Ăn uống"


def test_tra_giao_dich_theo_so_ngay_dung_ngay_mo_phong_cua_tool(monkeypatch):
    llm = make_llm([route_response(intent="transactions_lookup", days_back=7)])
    _, tools, _ = run_turn("tuần qua", llm=llm, monkeypatch=monkeypatch)
    args = tools.calls[1][1]
    assert (
        args["to_date"] == "2026-11-21" and args["from_date"] == "2026-11-14"
    )  # app_date của tool, không phải hôm nay thật


# --- ngoài phạm vi, xã giao -----------------------------------------------------------------------
def test_ngoai_pham_vi_co_khoi_notice_va_cau_noi_ro_gioi_han(monkeypatch):
    llm = make_llm(
        [
            route_response(
                intent="out_of_scope",
                reply="Mình không tư vấn chọn cổ phiếu được; mình giúp xem số dư và chuyển tiền giữa các hũ.",
            )
        ]
    )
    events, tools, _ = run_turn("câu nào đó", llm=llm, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert tools.calls == []
    n = blocks_of(events)[0]
    assert n["type"] == "notice" and n["data"]["kind"] == "out_of_scope"
    assert any("cổ phiếu" in e.delta for e in events if e.type.value == "TEXT_MESSAGE_CONTENT")


def test_xa_giao_dung_cau_tra_loi_cua_router(monkeypatch):
    llm = make_llm([route_response(intent="chitchat", reply="Chào bạn!")])
    events, tools, writer = run_turn("chào", llm=llm, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert tools.calls == [] and writer.calls == []
    assert [e.delta for e in events if e.type.value == "TEXT_MESSAGE_CONTENT"] == ["Chào bạn!"]


def test_xa_giao_khong_co_reply_thi_nho_writer(monkeypatch):
    llm = make_llm([route_response(intent="chitchat")])
    _, _, writer = run_turn("chào", llm=llm, monkeypatch=monkeypatch)
    assert writer.calls[0]["task"] == "chitchat"


# --- suy giảm có kiểm soát -------------------------------------------------------------------------
def test_cham_tran_thi_van_tra_the_so_du_va_notice_khong_goi_model(monkeypatch):
    usage = FakeUsage(caps_hit={"m-small-a", "m-small-b"})
    llm = make_llm([], usage)
    events, tools, writer = run_turn("số dư các hũ của mình", llm=llm, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert block_types(events) == ["jar_summary", "notice"]
    notice = blocks_of(events)[1]["data"]
    assert (notice["kind"], notice["code"]) == ("degraded", "MODEL_BUDGET_EXCEEDED")
    assert tools.calls == [("get_jar_balances", {})]
    assert writer.calls == []  # không thử viết chữ khi model đã chạm trần
    assert llm[1].calls == []  # không có lời gọi Bedrock nào
    r = result_of(events)
    assert r["degraded"] is True and r["model_calls"] == 0 and r["intent"] == "balance_lookup"


def test_tran_bang_0_theo_cau_hinh_cung_di_duong_suy_giam(monkeypatch):
    from yofina_core.config import Config
    from yofina_core.llm import LlmGateway, LlmSettings, ModelSpec

    settings = LlmSettings(roles={"small": (ModelSpec("m", rpm=0, daily_cap=0),)})
    gw = LlmGateway(settings, config=Config({}), client=make_llm([])[1], usage=FakeUsage())
    events, _, _ = run_turn("số dư", llm=(gw, None, None), monkeypatch=monkeypatch)
    check_agui_order(events)
    assert block_types(events) == ["jar_summary", "notice"]


def test_che_do_suy_giam_chuyen_tien_van_ra_khoi_confirm(monkeypatch):
    llm = make_llm([], FakeUsage(caps_hit={"m-small-a", "m-small-b"}))
    events, tools, _ = run_turn(
        "chuyển 100 nghìn từ Giải trí sang Ăn uống", llm=llm, monkeypatch=monkeypatch
    )
    check_agui_order(events)
    assert tools.calls[1] == (
        "move_between_jars",
        {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100000},
    )
    assert block_types(events) == ["confirm", "notice"]


def test_suy_giam_cau_khong_nhan_ra_thi_notice_khong_doan(monkeypatch):
    llm = make_llm([], FakeUsage(caps_hit={"m-small-a", "m-small-b"}))
    events, tools, _ = run_turn("nên mua cổ phiếu nào", llm=llm, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert tools.calls == [] and block_types(events) == ["notice"]
    n = blocks_of(events)[0]["data"]
    assert (
        n["kind"] == "degraded"
        and n["code"] == "MODEL_BUDGET_EXCEEDED"
        and "chưa hiểu" in n["message"]
    )
    assert result_of(events)["degraded"] is True


def test_router_tra_json_hong_het_so_lan_thi_dung_luat(monkeypatch):
    bad = route_response(intent="khong_co_y_dinh_nay")
    llm = make_llm([bad, bad])
    events, tools, _ = run_turn(
        "số dư các hũ",
        llm=llm,
        monkeypatch=monkeypatch,
        settings=agent_settings(router_max_attempts=2),
    )
    check_agui_order(events)
    assert len(llm[1].calls) == 2  # giới hạn số lần thử, không lặp mãi
    assert block_types(events) == ["jar_summary", "notice"] and tools.calls


def test_writer_loi_giua_chung_thi_dong_tin_nhan_va_them_notice(monkeypatch):
    llm = make_llm([route_response(intent="balance_lookup")])
    w = FakeWriter(["Tổng "], error=ModelBudgetExceeded("hết", role="small", reason="daily_cap"))
    events, _, _ = run_turn("số dư", llm=llm, monkeypatch=monkeypatch, writer=w)
    check_agui_order(events)  # tin nhắn chữ đã mở vẫn được đóng
    assert block_types(events) == ["jar_summary", "notice"]
    assert blocks_of(events)[1]["data"]["code"] == "MODEL_BUDGET_EXCEEDED"


def test_so_lieu_la_trong_cau_tra_loi_thi_them_canh_bao(monkeypatch):
    llm = make_llm([route_response(intent="balance_lookup")])
    events, _, _ = run_turn(
        "số dư", llm=llm, monkeypatch=monkeypatch, writer=FakeWriter("Tổng của bạn là 9.999.000 ₫.")
    )
    check_agui_order(events)
    assert block_types(events) == ["jar_summary", "notice"]
    assert blocks_of(events)[1]["data"]["code"] == "NUMERIC_UNVERIFIED"


def test_so_lieu_dung_thi_khong_co_canh_bao(monkeypatch):
    llm = make_llm([route_response(intent="balance_lookup")])
    events, _, _ = run_turn(
        "số dư",
        llm=llm,
        monkeypatch=monkeypatch,
        writer=FakeWriter("Hũ Giải trí còn 760.000 ₫, tổng 7,7 triệu."),
    )
    assert block_types(events) == ["jar_summary"] and result_of(events)["degraded"] is False


# --- lỗi tool và lỗi hệ thống ------------------------------------------------------------------------
def test_tool_khong_phan_hoi_thi_notice_loi_va_van_ket_thuc(monkeypatch):
    down = ToolOutcome(
        "x",
        ToolKind.UNAVAILABLE,
        code="DATABASE_UNAVAILABLE",
        message="Dịch vụ dữ liệu đang tạm thời không phản hồi.",
    )
    llm = make_llm([route_response(intent="balance_lookup")])
    events, _, writer = run_turn(
        "số dư", llm=llm, monkeypatch=monkeypatch, tools=FakeTools({"get_jar_balances": down})
    )
    check_agui_order(events)
    assert (
        block_types(events) == ["notice"]
        and blocks_of(events)[0]["data"]["code"] == "DATABASE_UNAVAILABLE"
    )
    assert writer.calls == []


def test_ket_qua_tool_sai_hop_dong_khong_phat_khoi_sai(monkeypatch):
    broken = fixture("get_jar_balances.ok.json")
    broken["data"]["jars"][0]["balance_vnd"] = "không phải số"
    llm = make_llm([route_response(intent="balance_lookup")])
    events, _, _ = run_turn(
        "số dư",
        llm=llm,
        monkeypatch=monkeypatch,
        tools=FakeTools({"get_jar_balances": classify_result("x", mcp_ok(broken))}),
    )
    check_agui_order(events)
    assert (
        block_types(events) == ["notice"]
        and blocks_of(events)[0]["data"]["code"] == "INTERNAL_ERROR"
    )


def test_loi_bat_ngo_trong_luot_thanh_notice_va_run_finished(monkeypatch):
    class Boom(FakeTools):
        async def call(self, name, arguments):
            raise RuntimeError("lỗi bất ngờ")

    llm = make_llm([route_response(intent="balance_lookup")])
    events, _, _ = run_turn("số dư", llm=llm, monkeypatch=monkeypatch, tools=Boom())
    check_agui_order(events)
    assert types(events)[-1] == "RUN_FINISHED"
    assert blocks_of(events)[-1]["data"]["code"] == "INTERNAL_ERROR"


def test_het_gio_cua_ca_luot_van_ket_thuc_hop_le(monkeypatch):
    class Slow(FakeTools):
        async def call(self, name, arguments):
            await asyncio.sleep(5)

    llm = make_llm([route_response(intent="balance_lookup")])
    events, _, _ = run_turn(
        "số dư",
        llm=llm,
        monkeypatch=monkeypatch,
        tools=Slow(),
        settings=agent_settings(run_timeout_seconds=0.3),
    )
    check_agui_order(events)
    assert result_of(events)["degraded"] is True and blocks_of(events)[-1]["type"] == "notice"


def test_tran_so_tool_call_moi_luot(monkeypatch):
    llm = make_llm([route_response(intent="transactions_lookup")])
    events, tools, _ = run_turn(
        "giao dịch",
        llm=llm,
        monkeypatch=monkeypatch,
        settings=agent_settings(max_tool_calls_per_turn=1),
    )
    check_agui_order(events)
    assert [c[0] for c in tools.calls] == ["get_jar_balances"]  # tool thứ hai bị chặn
    assert blocks_of(events)[-1]["type"] == "notice"


def test_khong_co_tin_nhan_nguoi_dung_thi_notice_khong_goi_gi(monkeypatch):
    events, tools, _ = run_turn(None, llm=make_llm([]), monkeypatch=monkeypatch)
    check_agui_order(events)
    assert tools.calls == [] and blocks_of(events)[0]["data"]["code"] == "PARAMS_INVALID"


def test_chay_lai_khong_giu_trang_thai_giua_cac_luot(monkeypatch):
    llm1 = make_llm([route_response(intent="balance_lookup")])
    e1, _, _ = run_turn("số dư", llm=llm1, monkeypatch=monkeypatch)
    llm2 = make_llm([route_response(intent="balance_lookup")])
    e2, _, _ = run_turn("số dư", llm=llm2, monkeypatch=monkeypatch)
    assert types(e1) == types(e2)


# --- lưu khối để phát lại ---------------------------------------------------------------------------
def test_luu_turn_blocks_dung_thu_tu_va_dinh_danh(monkeypatch):
    saved = {}

    class Spy:
        async def save(
            self, *, tools, conversation_id, trace_id, blocks, user_text="", assistant_text=""
        ):
            saved.update(
                conversation_id=conversation_id,
                trace_id=trace_id,
                blocks=list(blocks),
                user_text=user_text,
                assistant_text=assistant_text,
            )
            return True

    llm = make_llm([route_response(intent="balance_lookup")], FakeUsage())
    events, _, _ = run_turn("số dư", llm=llm, monkeypatch=monkeypatch, store=Spy())
    assert (
        saved["conversation_id"] == "session-1"
        and saved["trace_id"] == "8f3a21c94b7e4d0aa1c25e6f7b8c9d01"
    )
    assert [b["type"] for b in saved["blocks"]] == ["jar_summary"]
    assert saved["blocks"][0] == blocks_of(events)[0]
    assert saved["user_text"] == "số dư"
    said = "".join(e.delta for e in events if e.type.value == "TEXT_MESSAGE_CONTENT")
    assert said and saved["assistant_text"] == said


def test_luot_chi_co_chu_van_duoc_luu(monkeypatch):
    saved = {}

    class Spy:
        async def save(self, *, tools, blocks, user_text="", assistant_text="", **kw):
            saved.update(blocks=list(blocks), user_text=user_text, assistant_text=assistant_text)
            return True

    llm = make_llm([route_response(intent="chitchat", reply="Chào bạn!")])
    run_turn("xin chào", llm=llm, monkeypatch=monkeypatch, store=Spy())
    assert saved == {"blocks": [], "user_text": "xin chào", "assistant_text": "Chào bạn!"}


def test_loi_khi_luu_khoi_khong_lam_hong_luot(monkeypatch):
    class Broken:
        async def save(self, **kw):
            raise RuntimeError("DB sập")

    llm = make_llm([route_response(intent="balance_lookup")])
    events, _, _ = run_turn("số dư", llm=llm, monkeypatch=monkeypatch, store=Broken())
    check_agui_order(events)
    assert result_of(events)["degraded"] is False


def test_hang_so_ma_loi_khop_errorcode():
    assert ErrorCode.MODEL_BUDGET_EXCEEDED.value == "MODEL_BUDGET_EXCEEDED"
