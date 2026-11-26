"""Gộp kịch bản trong một cuộc trò chuyện: khoản mới cùng hũ với khoản đã hỏi trước thì hỏi giữ hay bỏ, giữ thì gộp.

Model và tool giả chỉ ở `agent_helpers`; dữ liệu `list_scenarios` là dữ liệu đầu vào của test, không nằm trong mã sản phẩm.
"""

from __future__ import annotations

from typing import Any

from agent_helpers import (
    FakeTools,
    blocks_of,
    check_agui_order,
    fixture,
    make_llm,
    mcp_ok,
    route_response,
    run_turn,
    tool_response,
)
from test_whatif import analysis
from yofina_agent.compact import compact_scenario
from yofina_agent.tools import classify_result
from yofina_agent.whatif import item_label, previous_same_jar

Q = "Nếu mua dép 300 nghìn từ hũ Giải trí thì sao"
DEP = {"kind": "one_time_purchase", "amount_vnd": 300_000, "funding_source": "jar", "jar_code": "giai_tri", "label": "dép"}
GIAY = {"kind": "one_time_purchase", "amount_vnd": 800_000, "funding_source": "jar", "jar_code": "giai_tri", "label": "giày"}
NON = {"kind": "one_time_purchase", "amount_vnd": 200_000, "funding_source": "jar", "jar_code": "an_uong", "label": "nón"}


def item(spec: dict[str, Any], label: str) -> dict[str, Any]:
    return {"kind": spec["kind"], "label": label, "amount_vnd": spec["amount_vnd"], "jar_code": spec["jar_code"], "spec": spec}


def row(*items: dict[str, Any]) -> dict[str, Any]:
    main = items[-1]
    return {
        "scenario_id": "00000000-0000-4000-8000-000000000001",
        "created_at": "2026-11-21T02:00:00Z",
        "kind": main["kind"],
        "label": " + ".join(i["label"] for i in items),
        "spec": main["spec"],
        "bundle": list(items),
    }


def listing(*rows: dict[str, Any]):
    payload = {"status": "OK", "as_of": "2026-11-21T02:00:00Z", "app_date": "2026-11-21", "data": {"scenarios": list(rows)}}
    return lambda args: classify_result("x", mcp_ok(payload))


def route(**extra: Any) -> dict[str, Any]:
    return route_response(
        intent="what_if", amount_vnd=300_000, funding="jar", scenario_kind="one_time_purchase", jar_text="Giải trí", label="dép", **extra
    )


def llm_for(*after: Any, **route_extra: Any):
    return make_llm([route(**route_extra), tool_response("plan_scenario", {"scenario": {**DEP, "date": None}}), *after])


def run_calls(tools: FakeTools) -> list[dict[str, Any]]:
    return [a for n, a in tools.calls if n == "run_scenario"]


# --- chọn khoản trước ---------------------------------------------------------------------------
def test_lay_lan_chay_gan_nhat_co_dung_hu_bo_khoan_trung_va_hu_khac():
    rows = [
        row(item(NON, "mua nón 200k")),  # mới nhất nhưng hũ khác: bỏ qua
        row(item(GIAY, "mua giày 800k"), item(DEP, "mua dép 300k")),
        row(item(GIAY, "mua giày 800k")),
    ]
    prev = previous_same_jar(rows, DEP)
    assert [p["spec"]["label"] for p in prev] == ["giày"]  # dép trùng khoản đang hỏi
    assert previous_same_jar(rows, NON) == []  # chính nó (trùng) thì không còn khoản nào
    assert previous_same_jar(rows, {"kind": "income_change", "new_monthly_salary_vnd": 9_000_000}) == []


def test_nguoi_dung_da_bo_khoan_truoc_thi_lan_sau_khong_hoi_lai():
    # lần chạy gần nhất cùng hũ chỉ còn dép (người dùng đã chọn "chỉ tính khoản mới")
    rows = [row(item(DEP, "mua dép 300k")), row(item(GIAY, "mua giày 800k"))]
    ao = {**DEP, "amount_vnd": 400_000, "label": "áo"}
    assert [p["spec"]["label"] for p in previous_same_jar(rows, ao)] == ["dép"]


def test_chi_mot_khoan_tra_sau_trong_ca_bo():
    bnpl_old = {"kind": "bnpl_purchase", "amount_vnd": 1_000_000, "funding_source": "credit", "jar_code": "giai_tri", "label": "loa"}
    bnpl_new = {**bnpl_old, "amount_vnd": 500_000, "label": "tai nghe"}
    rows = [row(item(bnpl_old, "mua loa 1tr"), item(GIAY, "mua giày 800k"))]
    assert [p["spec"]["label"] for p in previous_same_jar(rows, bnpl_new)] == ["giày"]
    assert [p["spec"]["label"] for p in previous_same_jar(rows, DEP)] == ["loa", "giày"]


def test_khoan_da_giu_bo_ngay_da_qua_giu_ngay_tuong_lai():
    from yofina_agent.whatif import carry_spec

    old = {**GIAY, "date": "2026-11-20"}
    assert "date" not in carry_spec(old, "2026-11-21")
    assert carry_spec({**GIAY, "date": "2026-11-25"}, "2026-11-21")["date"] == "2026-11-25"
    assert carry_spec(old, None)["date"] == "2026-11-20"


def test_nhan_khoan_moi_dung_kieu_nhan_cua_engine():
    assert item_label(DEP) == "mua dép 300 nghìn"
    assert item_label({"kind": "recurring_expense", "amount_vnd": 150_000, "jar_code": "giai_tri"}).startswith("khoản chi định kỳ")


# --- luồng ---------------------------------------------------------------------------------------
def test_co_khoan_truoc_cung_hu_thi_hoi_giu_hay_bo_dung_mot_cau_va_chua_chay_mo_phong(monkeypatch):
    tools = FakeTools({"list_scenarios": listing(row(item(GIAY, "mua giày 800k")))})
    events, tools, _ = run_turn(Q, llm=llm_for(), monkeypatch=monkeypatch, tools=tools)
    check_agui_order(events)
    blocks = blocks_of(events)
    assert [b["type"] for b in blocks] == ["clarify"]
    data = blocks[0]["data"]
    assert data["question"].count("?") == 1
    assert "mua giày 800k" in data["question"] and "Giải trí" in data["question"] and "mua dép 300 nghìn" in data["question"]
    assert [c["label"] for c in data["chips"]] == ["Vẫn giữ, tính gộp", "Chỉ tính khoản mới"]
    assert data["pending_intent"] == "what_if"
    names = [n for n, _ in tools.calls]
    assert "list_scenarios" in names and "run_scenario" not in names
    assert dict(tools.calls)["list_scenarios"] == {"conversation_id": "session-1"}


def test_router_tu_dat_giu_khoan_truoc_khi_chua_duoc_hoi_thi_van_hoi_khong_gop_ngam(monkeypatch):
    """Router đặt keep_previous ở câu hỏi đầu (Yofina chưa hỏi giữ hay bỏ, #39): mã bỏ cờ (`router.checked_route`), lượt hỏi đúng một
    câu như khi router để trống, không gộp ngầm khoản cũ. Đường giữ/bỏ thật đi qua câu trả lời cho câu hỏi đó (các test ở dưới)."""
    for keep in (True, False):
        tools = FakeTools({"list_scenarios": listing(row(item(GIAY, "mua giày 800k")))})
        events, tools, _ = run_turn(Q, llm=llm_for(keep_previous=keep), monkeypatch=monkeypatch, tools=tools)
        assert [b["type"] for b in blocks_of(events)] == ["clarify"]
        assert "run_scenario" not in [n for n, _ in tools.calls]


def test_giu_khoan_truoc_thi_gui_with_scenarios_va_conversation_id(monkeypatch):
    tools = FakeTools({"list_scenarios": listing(row(item(GIAY, "mua giày 800k")))})
    events, tools, _ = run_turn(
        None, llm=keep_llm(route_response(intent="what_if", keep_previous=True)), monkeypatch=monkeypatch, tools=tools,
        messages=conversation("ừ vẫn mua giày"),
    )  # fmt: skip
    (args,) = run_calls(tools)
    assert args["conversation_id"] == "session-1"
    assert args["with_scenarios"] == [GIAY]
    assert args["scenario"]["label"] == "dép"
    assert "clarify" not in [b["type"] for b in blocks_of(events)]


def test_bo_khoan_truoc_thi_chay_khoan_moi_mot_minh(monkeypatch):
    tools = FakeTools({"list_scenarios": listing(row(item(GIAY, "mua giày 800k")))})
    _, tools, _ = run_turn(
        None, llm=keep_llm(route_response(intent="what_if", keep_previous=False)), monkeypatch=monkeypatch, tools=tools,
        messages=conversation("thôi chỉ tính đôi dép"),
    )  # fmt: skip
    (args,) = run_calls(tools)
    assert "with_scenarios" not in args and args["conversation_id"] == "session-1"


def test_khong_co_khoan_truoc_thi_khong_hoi_va_van_luu_theo_cuoc_tro_chuyen(monkeypatch):
    llm = llm_for(tool_response("analyze", analysis()))
    _, tools, _ = run_turn(Q, llm=llm, monkeypatch=monkeypatch)
    (args,) = run_calls(tools)
    assert "with_scenarios" not in args and args["conversation_id"] == "session-1"


def test_doc_danh_sach_loi_thi_chay_khoan_moi_khong_doan(monkeypatch):
    err = {"status": "ERROR", "code": "INTERNAL_ERROR", "message": "lỗi"}
    tools = FakeTools({"list_scenarios": lambda args: classify_result("x", mcp_ok(err))})
    llm = llm_for(tool_response("analyze", analysis()))
    _, tools, _ = run_turn(Q, llm=llm, monkeypatch=monkeypatch, tools=tools)
    (args,) = run_calls(tools)
    assert "with_scenarios" not in args


def test_ban_gon_cho_analyst_co_cac_khoan_gop_va_tong():
    payload = fixture("run_scenario.ok.json")
    payload["data"]["bundle"] = [item(GIAY, "mua giày 800k"), item(DEP, "mua dép 300k")]
    payload["data"]["bundle_total_vnd"] = 1_100_000
    c = compact_scenario(payload)
    assert [b["label"] for b in c["bundle"]] == ["mua giày 800k", "mua dép 300k"]
    assert c["bundle"][0]["amount_text"] == "800.000 ₫" and c["bundle_total_text"] == "1.100.000 ₫"
    # một khoản: không có mục gộp
    one = fixture("run_scenario.ok.json")
    assert "bundle" not in compact_scenario(one)


# --- lượt trả lời "giữ hay bỏ" ----------------------------------------------------------------------
def conversation(answer: str) -> list[dict[str, Any]]:
    ask = (
        "Trước đó bạn có hỏi mua giày 800 nghìn từ hũ Giải trí. Bạn vẫn giữ ý định đó chứ? "
        "Nếu giữ, mình tính gộp với mua dép 300 nghìn."
    )
    return [
        {"id": "u1", "role": "user", "content": "Nếu mua giày 800 nghìn từ hũ Giải trí thì sao"},
        {"id": "a1", "role": "assistant", "content": "Hũ Giải trí chuyển từ đủ sang sát."},
        {"id": "u2", "role": "user", "content": Q},
        {"id": "a2", "role": "assistant", "content": ask},
        {"id": "u3", "role": "user", "content": answer},
    ]


def keep_llm(router: dict[str, Any]):
    # router (chỉ cần đúng giữ/bỏ) -> Orchestrator dựng khoản MỚI từ câu hỏi trước -> Analyst
    return make_llm([router, tool_response("plan_scenario", {"scenario": {**DEP, "date": None}}), tool_response("analyze", analysis())])


def test_bam_chip_giu_thi_lay_lai_khoan_moi_tu_cau_hoi_truoc_va_gop(monkeypatch):
    tools = FakeTools({"list_scenarios": listing(row(item(GIAY, "mua giày 800k")))})
    # router ghép sai (cộng hai khoản) cũng không sao: khoản mới lấy lại từ câu hỏi trước, chip quyết định giữ
    bad_router = route_response(intent="what_if", amount_vnd=1_100_000, label="giày", jar_text="giải trí", keep_previous=True)
    events, tools, _ = run_turn(
        None, llm=keep_llm(bad_router), monkeypatch=monkeypatch, tools=tools, messages=conversation("Vẫn giữ khoản trước, tính gộp cả hai")
    )
    (args,) = run_calls(tools)
    assert args["scenario"]["amount_vnd"] == 300_000 and args["scenario"]["label"] == "dép"
    assert args["with_scenarios"] == [GIAY]
    assert "clarify" not in [b["type"] for b in blocks_of(events)]
    assert events[-1].result["intent"] == "what_if"


def test_bam_chip_bo_thi_chi_tinh_khoan_moi(monkeypatch):
    tools = FakeTools({"list_scenarios": listing(row(item(GIAY, "mua giày 800k")))})
    router = route_response(intent="what_if", keep_previous=False)
    _, tools, _ = run_turn(
        None, llm=keep_llm(router), monkeypatch=monkeypatch, tools=tools, messages=conversation("Bỏ khoản trước, chỉ tính khoản mới")
    )
    (args,) = run_calls(tools)
    assert args["scenario"]["label"] == "dép" and "with_scenarios" not in args


def test_go_tay_thi_theo_router_giu_hay_bo(monkeypatch):
    tools = FakeTools({"list_scenarios": listing(row(item(GIAY, "mua giày 800k")))})
    router = route_response(intent="what_if", keep_previous=True)
    _, tools, _ = run_turn(None, llm=keep_llm(router), monkeypatch=monkeypatch, tools=tools, messages=conversation("ừ vẫn mua giày"))
    (args,) = run_calls(tools)
    assert args["with_scenarios"] == [GIAY]


def test_luot_truoc_khong_phai_cau_hoi_giu_bo_thi_di_duong_thuong(monkeypatch):
    msgs = conversation("Vẫn giữ khoản trước, tính gộp cả hai")
    msgs[3]["content"] = "Hũ Giải trí vẫn đủ."  # không có câu hỏi giữ/bỏ của sản phẩm
    llm = make_llm([route_response(intent="chitchat", reply="Bạn muốn mình tính gì tiếp?")])
    events, tools, _ = run_turn(None, llm=llm, monkeypatch=monkeypatch, messages=msgs)
    assert "run_scenario" not in [n for n, _ in tools.calls]
    assert events[-1].result["intent"] == "chitchat"


def test_nhan_khong_lap_chu_mua():
    assert item_label({**DEP, "label": "Mua dép"}) == "mua dép 300 nghìn"
