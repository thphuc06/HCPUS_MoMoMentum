"""Câu xin LẬP lộ trình có mục tiêu (số tiền hoặc hạn) mà router chưa trích được hũ (issue #39).

Tái lập ca đã thấy trên app 25/11: "lập giúp mình lộ trình xây quỹ dự phòng 3 triệu trong 3 tháng". Router (model) trả số tiền và hạn
nhưng không có `jar_text` và `roadmap_action` trống, hoặc có `jar_text` trỏ hũ Dự phòng (`buffer`, lập theo đích số dư của hũ). Router giả trả đúng các dạng đầu ra đó;
không có model thật. Ba ví: ví demo (Dự phòng `buffer`, Du lịch là hũ mục tiêu), ví ba hũ mới, ví bảy hũ cũ (`purpose` NULL).
"""

from __future__ import annotations

import pytest
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
    types,
)
from yofina_agent.router import merge_pending, pending_params
from yofina_agent.schemas import IntentParams, IntentResult
from yofina_agent.textutil import normalize
from yofina_agent.tools import classify_result
from yofina_agent.turn import _GOAL_NO_AMOUNT, _GOAL_NO_JAR

QUESTION = "lập giúp mình lộ trình xây quỹ dự phòng 3 triệu trong 3 tháng"
TARGET = 3_000_000
#: ngày mô phỏng của fixture là 2026-11-21: "trong 3 tháng" là 21/02/2027
DUE = "2027-02-21"

_BASE = {"color_key": "teal", "icon_key": "wallet", "balance_vnd": 0, "split_percent": 0}
DEMO_JARS = [
    {"code": "nghia_vu", "name": "Nghĩa vụ", "kind": "obligation", "split_percent": 33, "balance_vnd": 1_000_000},
    {"code": "du_phong", "name": "Dự phòng", "kind": "saving", "purpose": "buffer", "split_percent": 10,
     "balance_vnd": 2_700_000},
    {"code": "an_uong", "name": "Ăn uống", "kind": "spending", "split_percent": 30, "balance_vnd": 380_000},
    {"code": "di_lai", "name": "Đi lại", "kind": "spending", "split_percent": 7, "balance_vnd": 640_000},
    {"code": "giai_tri", "name": "Giải trí", "kind": "spending", "split_percent": 7, "balance_vnd": 760_000},
    {"code": "muc_tieu", "name": "Du lịch", "kind": "saving", "purpose": "goal", "goal_vnd": 6_000_000,
     "goal_date": "2027-03-31", "split_percent": 13, "balance_vnd": 1_800_000},
    {"code": "dau_tu", "name": "Đầu tư", "kind": "saving", "purpose": "long_term", "split_percent": 0},
]  # fmt: skip
THREE_JARS = [
    {"code": "chi_hang_ngay", "name": "Chi hằng ngày", "kind": "spending", "split_percent": 42, "balance_vnd": 900_000},
    {"code": "nghia_vu", "name": "Nghĩa vụ", "kind": "obligation", "split_percent": 33, "balance_vnd": 1_000_000},
    {"code": "du_phong", "name": "Dự phòng", "kind": "saving", "purpose": "buffer", "split_percent": 25,
     "balance_vnd": 500_000},
]  # fmt: skip
#: ví bảy hũ cũ: `purpose` NULL ở mọi hũ; Dự phòng không có mục tiêu đã khai nên là hũ đệm theo quy tắc tương thích
LEGACY_JARS = [
    {"code": "an_uong", "name": "Ăn uống", "kind": "spending", "split_percent": 30, "balance_vnd": 380_000},
    {"code": "di_lai", "name": "Đi lại", "kind": "spending", "split_percent": 7, "balance_vnd": 640_000},
    {"code": "hoa_don", "name": "Hóa đơn", "kind": "spending", "split_percent": 31, "balance_vnd": 450_000},
    {"code": "giai_tri", "name": "Giải trí", "kind": "spending", "split_percent": 7, "balance_vnd": 760_000},
    {"code": "du_lich", "name": "Du lịch", "kind": "saving", "goal_vnd": 6_000_000, "goal_date": "2027-03-31",
     "split_percent": 10, "balance_vnd": 1_800_000},
    {"code": "du_phong", "name": "Dự phòng", "kind": "saving", "split_percent": 10, "balance_vnd": 2_700_000},
    {"code": "nghia_vu", "name": "Nghĩa vụ", "kind": "obligation", "split_percent": 5, "balance_vnd": 1_000_000},
]  # fmt: skip
WALLETS = {"demo": DEMO_JARS, "three": THREE_JARS, "legacy": LEGACY_JARS}


def jars_payload(rows):
    payload = fixture("get_jar_balances.ok_goals.json")
    payload["data"]["jars"] = [{**_BASE, **r} for r in rows]
    payload["data"]["jars_total_vnd"] = sum(r.get("balance_vnd", 0) for r in rows)
    return payload


def roadmap_tools(rows, *, latest="error_not_found"):
    """Gateway giả của đường lộ trình; `save_roadmap` lưu đúng feasibility, goals, alternatives được gửi (như ledger)."""

    def ok(name, file):
        return lambda _args: classify_result(name, mcp_ok(fixture(file)))

    def save(args):
        payload = fixture("save_roadmap.ok.json")
        payload["data"].update(
            feasibility=args["feasibility"], goals=args["goals"], alternatives=args["alternatives"]
        )
        return classify_result("save_roadmap", mcp_ok(payload))

    return FakeTools(
        {
            "get_jar_balances": lambda _a: classify_result("get_jar_balances", mcp_ok(jars_payload(rows))),
            "get_resilience_score": ok("get_resilience_score", "get_resilience_score.ok.json"),
            "get_roadmap": ok("get_roadmap", f"get_roadmap.{latest}.json"),
            "optimize_allocation": ok("optimize_allocation", "optimize_allocation.ok.json"),
            "save_roadmap": save,
        }
    )


def outline(jar_code):
    step = {
        "step_id": "xem_lai_muc_tieu",
        "kind": "review_goal",
        "title": "Xem lại mục tiêu",
        "reason": "Theo dõi khả năng giữ mục tiêu",
        "jar_code": jar_code,
        "action": "schedule_nudge",  # bước không có số tiền phải là nhắc/xem lại có ngày
    }
    return {"phases": [{"phase_id": "on_dinh", "title": "Ổn định ngân sách", "steps": [step]}]}


def calls_of(tools, name):
    return [args for tool, args in tools.calls if tool == name]


def texts_of(events):
    return [e.delta for e in events if e.type.value == "TEXT_MESSAGE_CONTENT"]


def ask_turn(monkeypatch, rows, **router):
    """Lượt đầu: router trả `router` (dạng đã thấy), không có lời phác thảo nào trong kịch bản model."""
    llm = make_llm([route_response(intent="roadmap", **router)])
    events, tools, writer = run_turn(QUESTION, llm=llm, tools=roadmap_tools(rows), monkeypatch=monkeypatch)
    return events, tools, writer, llm


def answer_messages(question):
    return [
        {"id": "m1", "role": "user", "content": QUESTION},
        {"id": "m2", "role": "assistant", "content": question},
        {"id": "m3", "role": "user", "content": None},
    ]


def answer_turn(monkeypatch, rows, clarify_block, chip_label, routed, *, latest="error_not_found", draft_jar):
    """Lượt trả lời: người dùng bấm chip `chip_label` của khối hỏi lại; router giả trả `routed` cho câu cụt đó."""
    chip = next(c for c in clarify_block["data"]["chips"] if c["label"] == chip_label)
    messages = answer_messages(clarify_block["fallback_text"])
    messages[-1]["content"] = chip["value"]
    tools = roadmap_tools(rows, latest=latest)
    llm = make_llm([routed, tool_response("draft_roadmap", outline(draft_jar))])
    events, tools, writer = run_turn(None, llm=llm, tools=tools, monkeypatch=monkeypatch, messages=messages)
    return events, tools, writer, llm


# --- lượt đầu: có số tiền hoặc hạn, không có hũ -> hỏi lại đúng một câu chọn hũ ----------------------------------------
@pytest.mark.parametrize(
    "router",
    [
        {"amount_vnd": TARGET, "date_text": "trong 3 tháng"},  # dạng đã thấy: không jar_text, không roadmap_action
        {"amount_vnd": TARGET, "date_text": "3 tháng"},
        {"amount_vnd": TARGET},
        {"date_text": "trong 3 tháng"},
        {"amount_vnd": TARGET, "date_text": "trong 3 tháng", "roadmap_action": "create"},
    ],
)
@pytest.mark.parametrize(
    ("wallet", "chips"),
    [("demo", ["Dự phòng", "Du lịch"]), ("three", ["Dự phòng"]), ("legacy", ["Du lịch", "Dự phòng"])],
)
def test_muc_tieu_chua_co_hu_hoi_lai_mot_cau_chon_hu_khong_hien_ban_cu(monkeypatch, router, wallet, chips):
    events, tools, writer, llm = ask_turn(monkeypatch, WALLETS[wallet], **router)
    check_agui_order(events)
    (block,) = blocks_of(events)
    assert block["type"] == "clarify"
    data = block["data"]
    assert data["slot"] == "jar" and data["question"].count("?") == 1
    assert block["fallback_text"] == data["question"]
    # chip là hũ đặt được đích của lộ trình (hũ mục tiêu, hũ Dự phòng), theo thứ tự trong ví; giá trị gửi lại là tên hũ thật
    assert [c["label"] for c in data["chips"]] == chips
    assert all(c["value"] == f"Hũ {c['label']}" for c in data["chips"])
    # không đọc hay hiện lộ trình cũ, không lập, không câu "chưa nói mục tiêu này thuộc hũ nào"
    assert {tool for tool, _ in tools.calls} == {"get_jar_balances"}
    assert "TEXT_MESSAGE_CONTENT" not in types(events)
    assert not writer.calls
    assert len(llm[1].calls) == 1  # chỉ router: hỏi lại không tốn lời gọi model


def test_ten_hu_khop_nhieu_hu_hoi_lai_chon_trong_cac_hu_do(monkeypatch):
    """Chữ người dùng gõ khớp nhiều hũ: cũng là chưa xác định được hũ, hỏi lại với chip là đúng các hũ khớp."""
    rows = [
        *THREE_JARS,
        {"code": "du_lich_da_lat", "name": "Du lịch Đà Lạt", "kind": "saving", "purpose": "goal", "goal_vnd": 4_000_000},
        {"code": "du_lich_nhat", "name": "Du lịch Nhật", "kind": "saving", "purpose": "goal", "goal_vnd": 30_000_000},
    ]
    events, tools, _, _ = ask_turn(monkeypatch, rows, amount_vnd=TARGET, date_text="trong 3 tháng", jar_text="hũ du lịch")
    check_agui_order(events)
    (block,) = blocks_of(events)
    assert block["type"] == "clarify"
    assert [c["label"] for c in block["data"]["chips"]] == ["Du lịch Đà Lạt", "Du lịch Nhật"]
    assert {tool for tool, _ in tools.calls} == {"get_jar_balances"}


def test_lap_lai_khong_neu_muc_tieu_van_lap_khong_hoi_lai(monkeypatch):
    """"Lập lại lộ trình giúp mình" (không số tiền, không hạn, không hũ): lập ngay như trước, không hỏi hũ."""
    llm = make_llm(
        [route_response(intent="roadmap", roadmap_action="create"), tool_response("draft_roadmap", outline("muc_tieu"))]
    )
    events, tools, _ = run_turn(
        "Lập lại lộ trình giúp mình", llm=llm, tools=roadmap_tools(DEMO_JARS), monkeypatch=monkeypatch
    )
    check_agui_order(events)
    assert calls_of(tools, "optimize_allocation") == [{}]
    assert len(calls_of(tools, "save_roadmap")) == 1
    assert [b["type"] for b in blocks_of(events)] == ["roadmap"]


@pytest.mark.parametrize("action", [None, "view"])
@pytest.mark.parametrize(
    "question",
    ["Cho mình xem lộ trình đang dùng", "Vì sao lộ trình của mình lại xếp như vậy?", "Dùng bản mới", "Giữ bản cũ"],
)
def test_xem_lo_trinh_khong_muc_tieu_van_la_xem(monkeypatch, action, question):
    """Câu xem lộ trình (không số tiền, không hạn) giữ hành vi cũ: đọc bản theo cấu hình, writer viết, không lập, không hỏi."""
    llm = make_llm([route_response(intent="roadmap", roadmap_action=action)])
    events, tools, writer = run_turn(
        question, llm=llm, tools=roadmap_tools(DEMO_JARS, latest="ok"), monkeypatch=monkeypatch
    )
    check_agui_order(events)
    assert [tool for tool, _ in tools.calls] == ["get_jar_balances", "get_roadmap"]  # đọc ví đầu lượt
    assert [b["type"] for b in blocks_of(events)] == ["roadmap"]
    assert [call["task"] for call in writer.calls] == ["roadmap"]


def test_cau_cut_khong_neu_hu_sau_cau_hoi_hu_khong_hoi_lai_lan_nua(monkeypatch):
    """Đã hỏi hũ của mục tiêu mà người dùng nhắn câu cụt không nêu hũ ("Giữ bản cũ"): không phải câu trả lời, không ghép mục tiêu
    của câu trước, chạy đúng như router xếp (xem lộ trình)."""
    events, _, _, _ = ask_turn(monkeypatch, DEMO_JARS, amount_vnd=TARGET, date_text="trong 3 tháng")
    (clarify,) = blocks_of(events)
    messages = answer_messages(clarify["fallback_text"])
    messages[-1]["content"] = "Giữ bản cũ"
    llm = make_llm([route_response(intent="roadmap", roadmap_action="view")])
    events, tools, _ = run_turn(
        None, llm=llm, tools=roadmap_tools(DEMO_JARS, latest="ok"), monkeypatch=monkeypatch, messages=messages
    )
    check_agui_order(events)
    assert [tool for tool, _ in tools.calls] == ["get_jar_balances", "get_roadmap"]  # đọc ví đầu lượt
    assert [b["type"] for b in blocks_of(events)] == ["roadmap"]


def test_vi_khong_co_hu_dat_dich_lap_theo_muc_tieu_da_khai(monkeypatch):
    """Ví không có hũ nào đặt được đích (không hũ tiết kiệm): không có gì để chọn nên không hỏi; lập bản mới và nói rõ như trước."""
    rows = [r for r in THREE_JARS if r["kind"] != "saving"]
    llm = make_llm(
        [route_response(intent="roadmap", amount_vnd=TARGET, date_text="trong 3 tháng"),
         tool_response("draft_roadmap", outline("nghia_vu"))]
    )  # fmt: skip
    events, tools, _ = run_turn(QUESTION, llm=llm, tools=roadmap_tools(rows), monkeypatch=monkeypatch)
    check_agui_order(events)
    assert texts_of(events)[0] == _GOAL_NO_JAR
    assert calls_of(tools, "optimize_allocation") == [{}]
    assert "clarify" not in [b["type"] for b in blocks_of(events)]


# --- lượt trả lời: người dùng chọn hũ -> lập bản mới theo mục tiêu đã nêu ---------------------------------------------
@pytest.mark.parametrize(
    "routed_for_answer",
    [
        # router xếp câu cụt "Hũ Du lịch" thành tra số dư, hoặc thành lộ trình chỉ có hũ: mã ghép số tiền và hạn của câu trước
        lambda name: route_response(intent="lookup", lookup_kind="balance", jar_text=name),
        lambda name: route_response(intent="roadmap", jar_text=name),
        lambda name: route_response(intent="roadmap", roadmap_action="view", jar_text=name),
    ],
)
@pytest.mark.parametrize("latest", ["error_not_found", "ok"])
def test_tra_loi_hu_muc_tieu_lap_ban_moi_theo_muc_tieu(monkeypatch, routed_for_answer, latest):
    events, _, _, _ = ask_turn(monkeypatch, DEMO_JARS, amount_vnd=TARGET, date_text="trong 3 tháng")
    (clarify,) = blocks_of(events)
    events, tools, writer, llm = answer_turn(
        monkeypatch, DEMO_JARS, clarify, "Du lịch", routed_for_answer("Hũ Du lịch"), latest=latest, draft_jar="muc_tieu"
    )
    check_agui_order(events)
    # mục tiêu chỉ gửi cho bộ tối ưu của lượt này, không ghi vào hũ
    assert calls_of(tools, "optimize_allocation") == [
        {"goals": [{"jar": "muc_tieu", "target_vnd": TARGET, "target_date": DUE}]}
    ]
    assert {tool for tool, _ in tools.calls} <= {
        "get_jar_balances", "get_obligations", "get_resilience_score", "get_roadmap",
        "optimize_allocation", "check_suitability", "save_roadmap", "get_behavior_profile",
    }  # fmt: skip
    (stored,) = calls_of(tools, "save_roadmap")
    assert stored["reason_code"] == ("initial" if latest == "error_not_found" else "user_request")
    assert [b["type"] for b in blocks_of(events)] == ["roadmap"]
    # lời kết dựng bằng mã nói bản vừa lập và mục tiêu người dùng nêu; không viết lại bản cũ bằng writer
    assert not writer.calls
    (text,) = texts_of(events)
    assert "3.000.000 ₫ cho hũ Du lịch trước 21/02/2027" in text
    assert len(llm[1].calls) <= 4


def test_vi_bay_hu_cu_tra_loi_hu_du_phong_lap_theo_muc_tieu(monkeypatch):
    """Ví bảy hũ cũ: hũ Dự phòng (`purpose` NULL) nhận mục tiêu của lộ trình như mọi hũ tiết kiệm cũ, không ghi gì vào hũ."""
    events, _, _, _ = ask_turn(monkeypatch, LEGACY_JARS, amount_vnd=TARGET, date_text="trong 3 tháng")
    (clarify,) = blocks_of(events)
    events, tools, _, _ = answer_turn(
        monkeypatch, LEGACY_JARS, clarify, "Dự phòng", route_response(intent="lookup", jar_text="Hũ Dự phòng"),
        draft_jar="du_phong",
    )  # fmt: skip
    check_agui_order(events)
    assert calls_of(tools, "optimize_allocation") == [
        {"goals": [{"jar": "du_phong", "target_vnd": TARGET, "target_date": DUE}]}
    ]
    assert len(calls_of(tools, "save_roadmap")) == 1
    assert [b["type"] for b in blocks_of(events)] == ["roadmap"]


# --- hũ Dự phòng (`buffer`): lập bản mới theo đích số dư của hũ Dự phòng, không biến hũ thành hũ mục tiêu ----------------
@pytest.mark.parametrize("wallet", ["demo", "three"])
@pytest.mark.parametrize("via", ["router_jar", "answer"])
def test_muc_tieu_o_hu_du_phong_lap_ban_moi_theo_dich_so_du(monkeypatch, wallet, via):
    rows = WALLETS[wallet]
    if via == "router_jar":  # router trích được "quỹ dự phòng"
        llm = make_llm(
            [route_response(intent="roadmap", amount_vnd=TARGET, date_text="trong 3 tháng", jar_text="quỹ dự phòng"),
             tool_response("draft_roadmap", outline("du_phong"))]
        )  # fmt: skip
        events, tools, writer = run_turn(QUESTION, llm=llm, tools=roadmap_tools(rows, latest="ok"), monkeypatch=monkeypatch)
    else:
        first, _, _, _ = ask_turn(monkeypatch, rows, amount_vnd=TARGET, date_text="trong 3 tháng")
        (clarify,) = blocks_of(first)
        events, tools, writer, _ = answer_turn(
            monkeypatch, rows, clarify, "Dự phòng", route_response(intent="lookup", jar_text="Hũ Dự phòng"),
            latest="ok", draft_jar="du_phong",
        )  # fmt: skip
    check_agui_order(events)
    # đích số dư của hũ Dự phòng chỉ gửi cho bộ tối ưu của lượt này (bộ tối ưu giữ vai đệm), không ghi goal_vnd lên hũ
    assert calls_of(tools, "optimize_allocation") == [
        {"goals": [{"jar": "du_phong", "target_vnd": TARGET, "target_date": DUE}]}
    ]
    assert not {tool for tool, _ in tools.calls} & {"update_jar", "save_jars", "update_jars", "create_jar"}
    (stored,) = calls_of(tools, "save_roadmap")
    assert stored["reason_code"] == "user_request"
    assert [b["type"] for b in blocks_of(events)] == ["roadmap"]
    assert not writer.calls  # không đọc lại bản cũ bằng writer
    # một lời kết dựng bằng mã nêu đích người dùng xin; không còn câu "chưa tính được mục tiêu", không đẩy sang hũ Du lịch
    (text,) = texts_of(events)
    assert "3.000.000 ₫ cho hũ Dự phòng trước 21/02/2027" in text
    assert "chưa tính được" not in text and "Du lịch" not in text


@pytest.mark.parametrize("goal_vnd", [None, 5_000_000])
def test_hu_du_phong_chi_co_han_hoi_so_tien_khong_doc_goal_vnd(monkeypatch, goal_vnd):
    """Câu chỉ có hạn cho hũ Dự phòng: đích số dư cần số tiền người dùng nói, kể cả khi hàng hũ có goal_vnd (không đọc nó)."""
    rows = [{**r, "goal_vnd": goal_vnd} if r["code"] == "du_phong" and goal_vnd else r for r in DEMO_JARS]
    llm = make_llm(
        [route_response(intent="roadmap", date_text="trong 3 tháng", jar_text="quỹ dự phòng"),
         tool_response("draft_roadmap", outline("du_phong"))]
    )  # fmt: skip
    events, tools, _ = run_turn(QUESTION, llm=llm, tools=roadmap_tools(rows), monkeypatch=monkeypatch)
    check_agui_order(events)
    assert texts_of(events)[0] == _GOAL_NO_AMOUNT.format(name="Dự phòng")
    assert calls_of(tools, "optimize_allocation") == [{}]
    assert [b["type"] for b in blocks_of(events)] == ["roadmap"]


# --- ghép câu cụt với câu lộ trình đang chờ, bằng mã ------------------------------------------------------------------
def test_pending_params_doc_muc_tieu_lo_trinh_cua_cau_dang_cho():
    msgs = [("user", QUESTION), ("assistant", "Mục tiêu này thuộc hũ nào?")]
    pending = pending_params(msgs)
    assert pending is not None
    assert (pending["_intent"], pending["amount_vnd"], pending["date_text"]) == ("roadmap", TARGET, "trong 3 tháng")


@pytest.mark.parametrize("text", ["Cho mình xem lộ trình", "Vì sao lộ trình xếp như vậy"])
def test_cau_lo_trinh_khong_muc_tieu_khong_thanh_cau_dang_cho(text):
    pending = pending_params([("user", text), ("assistant", "Bạn muốn xem gì thêm?")])
    assert pending is None or "_intent" not in pending


def test_merge_pending_cau_cut_thanh_lo_trinh_co_muc_tieu():
    pending = {"_intent": "roadmap", "amount_vnd": TARGET, "date_text": "trong 3 tháng"}
    routed = IntentResult(
        intent="lookup", params=IntentParams(lookup_kind="balance", jar_text="Du lịch"), confidence=0.6,
        needs_clarification=False,
    )  # fmt: skip
    merged = merge_pending(routed, "Hũ Du lịch", pending)
    assert merged.intent == "roadmap"
    p = merged.params
    assert (p.amount_vnd, p.date_text, p.lookup_kind) == (TARGET, "trong 3 tháng", None)
    assert normalize(p.jar_text or "") == "du lich"


def test_merge_pending_giu_tham_so_router_cua_cau_moi():
    """Router (câu mới) thắng mã: router đã ghép hũ, số tiền, hạn thì giữ nguyên; chỉ điền ô router để trống."""
    pending = {"_intent": "roadmap", "amount_vnd": TARGET, "date_text": "trong 3 tháng"}
    routed = IntentResult(
        intent="roadmap", params=IntentParams(jar_text="Du lịch", date_text="3 tháng"), confidence=0.8,
        needs_clarification=False,
    )  # fmt: skip
    p = merge_pending(routed, "Hũ Du lịch", pending).params
    assert (p.jar_text, p.amount_vnd, p.date_text) == ("Du lịch", TARGET, "3 tháng")
