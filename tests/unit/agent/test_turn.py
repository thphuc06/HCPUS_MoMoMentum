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
    make_jwt,
    make_llm,
    mcp_ok,
    route_response,
    run,
    run_input,
    run_turn,
    types,
)
from yofina_agent.identity import Identity
from yofina_agent.tools import ToolKind, ToolOutcome, classify_result
from yofina_agent.turn import Turn, TurnDeps, drain_background, stream_turn

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
def test_so_du_dung_lan_doc_vi_dau_luot_khoi_truoc_cau_tra_loi(monkeypatch):
    """Tra số dư dùng lại lần đọc ví ở đầu lượt (danh sách hũ cho router, #39): một tool call; thẻ số dư dựng từ kết quả đó nên đi sau
    TOOL_CALL_RESULT của lần đọc, và trước chữ."""
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
        "TOOL_CALL_RESULT",
        "ACTIVITY_SNAPSHOT",
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
        "lookup",
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
            )
        ]
    )
    events, tools, _ = run_turn("chuyển từ giải trí sang ăn uống", llm=llm, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert tools.calls == [("get_jar_balances", {})]  # chỉ lần đọc ví đầu lượt; đúng một câu hỏi lại (khối clarify)
    (clarify,) = blocks_of(events)
    assert clarify["type"] == "clarify" and clarify["data"]["slot"] == "amount"
    assert clarify["data"]["question"].count("?") == 1 and clarify["data"]["pending_intent"] == "move"
    assert [e for e in events if e.type.value == "TEXT_MESSAGE_CONTENT"] == []


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


def _clarify_of(events):
    (clarify,) = [b for b in blocks_of(events) if b["type"] == "clarify"]
    return clarify["data"]


def test_chuyen_tien_khong_noi_hu_nguon_thi_hoi_dung_mot_cau_kem_chip_hu_that(monkeypatch):
    """F3: trước đây ra thẻ "Đủ" và options rỗng; giờ hỏi lại, không gọi affordability_check."""
    llm = make_llm([route_response(intent="affordability", amount_vnd=250000)])
    events, tools, writer = run_turn("chuyển 250k cho người nhận demo", llm=llm, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert "affordability_check" not in [c[0] for c in tools.calls]
    data = _clarify_of(events)
    assert data["slot"] == "jar" and data["question"].count("?") == 1
    real = {"Ăn uống", "Giải trí"}  # hũ của persona minh trong fixture get_jar_balances
    names = [c["label"] for c in data["chips"]]
    # mọi hũ của ví làm chip, đúng thứ tự trong ví (#39: không cắt còn 6), rồi chip Trả sau (V4: một chính sách cho mọi khoản chi)
    assert names == [*(j["name"] for j in fixture("get_jar_balances.ok.json")["data"]["jars"]), "Trả sau (mô phỏng)"]
    assert real <= set(names)
    assert all(c["value"].startswith("Hũ ") for c in data["chips"][:-1])
    assert data["chips"][-1]["value"] == "Trả bằng Trả sau (mô phỏng)"
    assert [e for e in events if e.type.value == "TEXT_MESSAGE_CONTENT"] == []


def test_ten_hu_la_khi_kiem_tra_chi_tieu_thi_hoi_lai_kem_chip_hu_that(monkeypatch):
    llm = make_llm([route_response(intent="affordability", amount_vnd=250000, jar_text="quỹ nhà")])
    events, tools, _ = run_turn("chi 250k từ quỹ nhà", llm=llm, monkeypatch=monkeypatch)
    assert "affordability_check" not in [c[0] for c in tools.calls]
    data = _clarify_of(events)
    assert data["slot"] == "jar" and "quỹ nhà" in data["question"] and data["question"].count("?") == 1
    assert "Ăn uống" in [c["label"] for c in data["chips"]]


def test_what_if_chuyen_hu_thieu_hu_nguon_thi_hoi_lai_khong_chay_kich_ban(monkeypatch):
    llm = make_llm(
        [route_response(intent="what_if", scenario_kind="jar_transfer", amount_vnd=300000, to_jar_text="ăn uống")]
    )
    events, tools, _ = run_turn("nếu chuyển 300k sang ăn uống thì sao", llm=llm, monkeypatch=monkeypatch)
    assert "run_scenario" not in [c[0] for c in tools.calls]
    data = _clarify_of(events)
    assert data["slot"] == "jar" and data["chips"] and data["question"].count("?") == 1


def test_hu_nguon_hop_le_thi_van_chay_kiem_tra_binh_thuong(monkeypatch):
    llm = make_llm([route_response(intent="affordability", amount_vnd=250000, jar_text="ăn uống")])
    events, tools, _ = run_turn("chi 250k từ ăn uống", llm=llm, monkeypatch=monkeypatch)
    assert "affordability_check" in [c[0] for c in tools.calls]
    assert [b for b in blocks_of(events) if b["type"] == "clarify"] == []


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
    assert tools.calls == [("get_jar_balances", {})]  # chỉ lần đọc ví đầu lượt
    assert block_types(events) == ["notice", "suggestions"]
    n, sug = blocks_of(events)
    assert n["data"]["kind"] == "out_of_scope" and sug["data"]["context"] == "out_of_scope"
    assert sug["data"]["can_do"] and sug["data"]["cannot_do"] and sug["data"]["items"]
    # lời từ chối là chuỗi sản phẩm, không phải lời model (nên không thể lọt mã chứng khoán)
    assert [e for e in events if e.type.value == "TEXT_MESSAGE_CONTENT"] == []


def test_xa_giao_dung_cau_tra_loi_cua_router(monkeypatch):
    llm = make_llm([route_response(intent="chitchat", reply="Chào bạn!")])
    events, tools, writer = run_turn("chào", llm=llm, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert tools.calls == [("get_jar_balances", {})] and writer.calls == []  # chỉ lần đọc ví đầu lượt
    assert [e.delta for e in events if e.type.value == "TEXT_MESSAGE_CONTENT"] == ["Chào bạn!"]


def test_xa_giao_khong_co_reply_thi_nho_writer(monkeypatch):
    from yofina_agent import notices

    llm = make_llm([route_response(intent="chitchat")])
    _, _, writer = run_turn("chào", llm=llm, monkeypatch=monkeypatch)
    assert writer.calls[0]["task"] == "chitchat"
    # danh sách việc làm được đi vào dữ liệu (một nguồn: notices.CAN_DO), không chép trong lời nhắc của việc
    assert writer.calls[0]["compact"] == {"viec_lam_duoc": list(notices.CAN_DO)}


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
    assert r["degraded"] is True and r["model_calls"] == 0 and r["intent"] == "lookup"


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
    # đọc ví đầu lượt đã chạy trước khi lời gọi router chạm trần; ngoài lần đó không tool nào
    assert tools.calls == [("get_jar_balances", {})] and block_types(events) == ["notice"]
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


def _turn_with(store, records, *, settings=None):
    llm = make_llm([route_response(intent="balance_lookup")])
    tools = FakeTools()
    deps = TurnDeps(
        settings=settings or agent_settings(),
        llm=lambda: llm[0],
        store=store,
        tools_factory=lambda identity: tools,
        guardrail=None,
        records=records,
    )
    turn = Turn(
        deps,
        run_input("số dư"),
        Identity("user-a", make_jwt("user-a")),
        trace_id="8f3a21c94b7e4d0aa1c25e6f7b8c9d01",
        conversation_id="session-1",
    )
    return turn, tools


def test_run_finished_phat_truoc_khi_ghi_luot_va_ghi_luot_van_xong(monkeypatch):
    """#11: save_turn và record_turn chạy nền SAU `RUN_FINISHED` (khung chat mở ngay), và vẫn ghi xong."""
    monkeypatch.setattr("yofina_agent.turn.write_stream", FakeWriter())
    gate = asyncio.Event()
    order: list[str] = []

    class SlowStore:
        async def save(self, **kw):
            await gate.wait()
            order.append("save_done")
            return True

    class SlowRecords:
        async def save(self, *, tools, record):
            await gate.wait()
            order.append(f"record_done:{record['intent']}")
            return True

    turn, tools = _turn_with(
        SlowStore(),
        SlowRecords(),
        settings=agent_settings(turn_blocks_timeout_seconds=1.0, turn_record_timeout_seconds=1.0),
    )

    async def main():
        events = [e async for e in stream_turn(turn)]
        order.append(f"stream_end:{events[-1].type.value}")
        gate.set()
        await drain_background()
        return events

    run(asyncio.wait_for(main(), 10))
    assert order[0] == "stream_end:RUN_FINISHED"
    assert sorted(order[1:]) == ["record_done:lookup", "save_done"]
    assert tools.closed  # phiên MCP đóng sau khi ghi xong, không đóng trước


def test_ghi_luot_loi_hoac_qua_gio_lan_dau_thi_thu_lai_mot_lan(monkeypatch):
    attempts = {"save": 0, "record": 0}

    class FlakyStore:
        async def save(self, **kw):
            attempts["save"] += 1
            if attempts["save"] == 1:
                raise RuntimeError("Gateway lỗi tạm thời")
            return True

    class SlowOnceRecords:
        def __init__(self):
            self.saved = []

        async def save(self, *, tools, record):
            attempts["record"] += 1
            if attempts["record"] == 1:
                await asyncio.sleep(5)  # quá turn_record_timeout_seconds
            self.saved.append(record["trace_id"])
            return True

    records = SlowOnceRecords()
    llm = make_llm([route_response(intent="balance_lookup")])
    events, _, _ = run_turn(
        "số dư",
        llm=llm,
        monkeypatch=monkeypatch,
        store=FlakyStore(),
        records=records,
        settings=agent_settings(turn_blocks_timeout_seconds=0.2, turn_record_timeout_seconds=0.2),
    )
    check_agui_order(events)
    assert attempts == {"save": 2, "record": 2}
    assert records.saved == ["8f3a21c94b7e4d0aa1c25e6f7b8c9d01"]  # đúng một bản ghi lượt


def test_hang_so_ma_loi_khop_errorcode():
    assert ErrorCode.MODEL_BUDGET_EXCEEDED.value == "MODEL_BUDGET_EXCEEDED"


# --- dự báo một hũ (phase 2, luồng C) --------------------------------------------------------------------
FORECAST_TOOL = "forecast___get_forecast"


def forecast_calls(tools):
    return [(n, a) for n, a in tools.calls if n == "get_forecast"]


def test_hoi_du_bao_mot_hu_goi_tool_forecast_phat_khoi_timeline_va_nho_writer(monkeypatch):
    from yofina_agent.compact import allowed_amounts

    llm = make_llm([route_response(intent="forecast_lookup", jar_text="ăn uống")])
    events, tools, writer = run_turn(
        "hũ ăn uống còn trụ được bao lâu", llm=llm, monkeypatch=monkeypatch
    )
    check_agui_order(events)
    assert [c[0] for c in tools.calls] == ["get_jar_balances", "get_forecast"]
    assert forecast_calls(tools) == [
        ("get_forecast", {"jar": "an_uong"})
    ]  # mã hũ ánh xạ từ dữ liệu tool
    assert tool_names(events) == [JAR_TOOL, FORECAST_TOOL]  # tool dự báo thuộc target `forecast`
    # độ phủ của fixture (0,62) thấp hơn ngưỡng cấu hình nên có thêm notice độ tin cậy thấp
    assert block_types(events) == ["forecast_timeline", "notice"]
    assert blocks_of(events)[1]["data"]["degraded_reason"] == "low_coverage"
    block = blocks_of(events)[0]
    want = fixture("get_forecast.ok.json")["data"]
    assert block["data"] == want  # số trong khối là số của tool, nguyên vẹn
    assert block["id"].startswith("forecast_timeline:") and block["id"].endswith(":an_uong")
    assert block["source"]["tool"] == FORECAST_TOOL
    call = writer.calls[0]
    assert call["task"] == "forecast"
    c = call["compact"]
    assert c["jar"] == "Ăn uống" and c["status"] == "hụt"
    assert c["runout"] == {"date_text": "29/11", "days_from_today": 8, "days_before_payday": 6}
    assert (
        c["payday"] == {"date_text": "05/12", "days_until": 14} and c["p_shortfall_percent"] == 71
    )
    assert (
        c["upcoming"][0]["label"] == "Tiền điện" and c["upcoming"][0]["amount_text"] == "375.000 ₫"
    )
    # mọi số tiền model được phép nhắc đều có trong kết quả tool
    assert allowed_amounts(c) >= {380_000, 375_000, 2_700_000}
    assert result_of(events)["intent"] == "lookup" and result_of(events)["tool_calls"] == 2


def test_du_bao_khong_noi_hu_nao_thi_doc_moi_hu_khong_hoi_lai(monkeypatch):
    # router lỡ hỏi lại "hũ nào": tra cứu không có ô bắt buộc nên mã bỏ câu hỏi đó và đọc dự báo của mọi hũ
    llm = make_llm(
        [
            route_response(
                intent="forecast_lookup",
                clarify={"slot": "jar", "question": "Bạn muốn xem dự báo hũ nào?", "chips": []},
            )
        ]
    )
    events, tools, _ = run_turn("dự báo giúp mình", llm=llm, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert len(forecast_calls(tools)) > 1
    assert "clarify" not in block_types(events)


def test_du_bao_hu_khong_co_thi_hien_so_du_that_va_hoi_lai(monkeypatch):
    llm = make_llm([route_response(intent="forecast_lookup", jar_text="quỹ nhà")])
    events, tools, writer = run_turn(
        "quỹ nhà còn trụ được bao lâu", llm=llm, monkeypatch=monkeypatch
    )
    assert forecast_calls(tools) == []
    assert block_types(events) == ["jar_summary"] and writer.calls[0]["task"] == "clarify"


def test_du_bao_loi_tool_hien_notice_dung_ma(monkeypatch):
    unavailable = fixture("get_forecast.error_unavailable.json")
    tools = FakeTools({"get_forecast": lambda a: classify_result("x", mcp_ok(unavailable))})
    llm = make_llm([route_response(intent="forecast_lookup", jar_text="ăn uống")])
    events, _, writer = run_turn(
        "ăn uống khi nào cạn", llm=llm, tools=tools, monkeypatch=monkeypatch
    )
    check_agui_order(events)
    n = next(b for b in blocks_of(events) if b["type"] == "notice")["data"]
    assert (n["kind"], n["code"]) == ("error", "FORECAST_UNAVAILABLE") and n[
        "title"
    ] == "Chưa có dự báo"
    assert writer.calls == []


def test_du_bao_khi_model_loi_van_tra_khoi_timeline_bang_bo_phan_loai_du_phong(monkeypatch):
    usage = FakeUsage(caps_hit={"m-small-a", "m-small-b"})
    llm = make_llm([], usage)
    events, tools, writer = run_turn(
        "hũ ăn uống còn trụ được bao lâu", llm=llm, monkeypatch=monkeypatch
    )
    check_agui_order(events)
    assert block_types(events) == [
        "forecast_timeline",
        "notice",
        "notice",
    ]  # số thật từ tool + notice độ tin cậy thấp (độ phủ của fixture) + thông báo suy giảm
    assert forecast_calls(tools) == [("get_forecast", {"jar": "an_uong"})]
    assert writer.calls == [] and llm[1].calls == []
    assert (
        result_of(events)["intent"] == "lookup" and result_of(events)["degraded"] is True
    )


def test_ket_qua_du_bao_sai_hop_dong_thi_khong_phat_khoi(monkeypatch):
    bad = fixture("get_forecast.ok.json")
    bad["data"]["status"] = "khong-hop-le"
    tools = FakeTools({"get_forecast": lambda a: classify_result("x", mcp_ok(bad))})
    llm = make_llm([route_response(intent="forecast_lookup", jar_text="ăn uống")])
    events, _, _ = run_turn("ăn uống khi nào cạn", llm=llm, tools=tools, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert "forecast_timeline" not in block_types(events)
    assert next(b for b in blocks_of(events) if b["type"] == "notice")["data"]["kind"] == "error"
