"""Các handler đọc phase 4 qua Gateway giả và fixture hợp đồng."""

from __future__ import annotations

import json
from typing import get_args

import pytest
from agent_helpers import (
    JARS_READ,
    REPO,
    FakeRecords,
    FakeTools,
    FakeWriter,
    agent_settings,
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
from yofina_agent import notices
from yofina_agent.clarify import GOAL_DATE_QUESTION
from yofina_agent.schemas import Intent
from yofina_agent.textutil import strip_accents
from yofina_agent.tools import classify_result
from yofina_agent.turn import (
    _GOAL_ADD_GOAL_JAR,
    _GOAL_NOT_SAVING,
    _GOAL_UNKNOWN_JAR,
    _GOAL_USE_GOAL_JAR,
    Turn,
)
from yofina_agent.writer import WRITER_SYSTEM, build_writer_prompt

from yofina_core.errors import ErrorCode
from yofina_core.resilience import load_shock_set


def gateway(tool_name, payload):
    return FakeTools({tool_name: classify_result(tool_name, mcp_ok(payload))})


@pytest.mark.parametrize(
    "intent, tool, target, block_fixture",
    [
        ("resilience", "get_resilience_score", "forecast", "resilience_score.minh"),
        ("stress", "stress_test", "forecast", "stress_result.mat_viec"),
        ("roadmap", "get_roadmap", "planner", "roadmap.active_edited"),
    ],
)
@pytest.mark.parametrize("llm_down", [False, True])
def test_phase4_success(monkeypatch, intent, tool, target, block_fixture, llm_down):
    payload = fixture(f"{tool}.ok.json")
    data = payload["data"]
    args = {}
    params = {}
    if intent == "stress":
        args = params = {"shock_id": data["shock"]["shock_id"]}
    elif intent == "roadmap":
        args = {"which": "active"}  # lượt xem luôn đọc bản đang dùng (#39)
        params = {"roadmap_action": "view"}

    if llm_down:
        classify = Turn.classify_guarded

        async def classify_then_lose_llm(self, question, history):
            routed = await classify(self, question, history)
            self.llm_down = True
            return routed

        monkeypatch.setattr(Turn, "classify_guarded", classify_then_lose_llm)

    events, tools, writer = run_turn(
        "Cho mình xem kết quả",
        llm=make_llm([route_response(intent=intent, **params)]),
        tools=gateway(tool, payload),
        monkeypatch=monkeypatch,
    )
    check_agui_order(events)
    expected = json.loads(
        (REPO / "contracts" / "fixtures" / "blocks" / "valid" / f"{block_fixture}.json").read_text(encoding="utf-8")
    )
    assert blocks_of(events)[0] == expected
    assert tools.calls == [JARS_READ, (tool, args)]
    # lần đọc ví trước router chỉ để dựng danh sách hũ cho router: im lặng, không thẻ tool trên UI (lượt này không dùng tới ví)
    t = types(events)
    # khối đứng trước TOOL_CALL_RESULT của tool sinh ra nó
    assert t.index("ACTIVITY_SNAPSHOT") < max(i for i, x in enumerate(t) if x == "TOOL_CALL_RESULT")

    compact = json.loads([e.content for e in events if e.type.value == "TOOL_CALL_RESULT"][-1])
    if intent == "resilience":
        weakest = next(c for c in data["components"] if c["key"] == data["weakest"])
        assert compact == {
            "score": data["score"],
            "band": data["band"],
            "weakest": {"label": weakest["label"], "explanation": weakest["explanation"]},
        }
        assert any(b["data"].get("degraded_reason") == "low_coverage" for b in blocks_of(events)[1:])
    elif intent == "stress":
        assert compact["shock_label"] == data["shock"]["label"]
        for key in ("score_before", "score_after", "runway_days_total", "runway_days_emergency", "shortfall_vnd"):
            assert compact[key] == data[key]
        assert compact["shortfall_text"] == "8.890.000 ₫"
    else:
        goals = [
            {
                "jar": g["jar"]["name"], "target_text": "6.000.000 ₫", "target_date_text": "31/03/2027", "on_track": g["on_track"],
                "projected_date_text": "24/03/2027",
            }
            for g in data["goals"]
        ]  # fmt: skip
        assert compact == {
            "version": data["version"],
            "status": data["status"],
            "reason": data["reason"]["text"],
            # mã lý do (26/11 tối, #39): writer biết bản lập lại vì hũ đổi mức chi
            "reason_code": data["reason"]["code"],
            "feasibility": data["feasibility"],
            # mục tiêu có cấu trúc cho writer (V5 của báo cáo rà soát #39)
            "goals": goals,
            "counts": data["counts"],
            "phase_count": len(data["phases"]),
            "step_titles": [step["title"] for step in data["phases"][0]["steps"]],
        }

    if llm_down:
        assert not writer.calls
        if intent == "roadmap":
            # lượt xem lộ trình không có lời của writer vẫn có lời kết dựng bằng mã từ khối (#39), không cần lượt gọi model
            texts = [e.delta for e in events if e.type.value == "TEXT_MESSAGE_CONTENT"]
            steps = sum(len(phase["steps"]) for phase in data["phases"])
            head = notices.ROADMAP_CLOSING_ACTIVE.format(version=data["version"], phases=len(data["phases"]), steps=steps)
            assert len(texts) == 1 and texts[0].startswith(head)
        else:
            assert "TEXT_MESSAGE_START" not in types(events)
    else:
        assert [(call["task"], call["compact"]) for call in writer.calls] == [(intent, compact)]
        assert types(events).index("TOOL_CALL_RESULT") < types(events).index("TEXT_MESSAGE_START")
        prompt = build_writer_prompt(intent, writer.calls[0]["question"], compact)
        # "không khuyên đầu tư hay vay" nói một lần ở lời nhắc hệ thống của writer, áp cho mọi việc
        assert "đầu tư hay vay tiền" in WRITER_SYSTEM
        if intent != "roadmap":
            assert "không phải điểm tín dụng" in prompt


@pytest.mark.parametrize("shock_id", [None, "unknown_shock"])
def test_stress_clarify_uses_config(monkeypatch, shock_id):
    clarify = {"slot": "other", "question": "Router muốn hỏi gì?", "chips": []} if shock_id else None
    routed = route_response(intent="stress", shock_id=shock_id, clarify=clarify)
    events, tools, writer = run_turn("Thử cú sốc", llm=make_llm([routed]), monkeypatch=monkeypatch)
    check_agui_order(events)
    (block,) = blocks_of(events)
    assert block["type"] == "clarify"
    assert block["data"]["slot"] == "other"
    assert block["data"]["question"] == notices.STRESS_QUESTION
    assert block["data"]["question"].count("?") == 1
    assert [(chip["label"], chip["value"]) for chip in block["data"]["chips"]] == [
        (shock.label, f"Thử cú sốc {shock.label}") for shock in load_shock_set().shocks
    ]
    assert tools.calls == [JARS_READ] and not writer.calls  # chỉ lần đọc ví đầu lượt


@pytest.mark.parametrize("click_chip", [True, False])
def test_stress_routes_chip_or_full_label_without_model(monkeypatch, click_chip):
    payload = fixture("stress_test.ok.json")
    shock_id = payload["data"]["shock"]["shock_id"]
    label = payload["data"]["shock"]["label"]
    if click_chip:
        events, _, _ = run_turn(
            "Thử cú sốc", llm=make_llm([route_response(intent="stress")]), monkeypatch=monkeypatch
        )
        (clarify,) = blocks_of(events)
        question = next(chip["value"] for chip in clarify["data"]["chips"] if chip["label"] == label)
    else:
        question = f"Nếu {strip_accents(label)} thì sao?"

    llm = make_llm([route_response(intent="lookup", lookup_kind="balance")])
    events, tools, _ = run_turn(
        question, llm=llm, tools=gateway("stress_test", payload), monkeypatch=monkeypatch
    )
    check_agui_order(events)
    assert tools.calls == [("stress_test", {"shock_id": shock_id})]
    assert [block["type"] for block in blocks_of(events)] == ["stress_result"]
    assert not llm[1].calls


@pytest.mark.parametrize(
    "intent, tool, error_fixture, kind",
    [
        # chưa khai lương là trạng thái trống, không phải lỗi: notice `info` (màu trung tính)
        ("resilience", "get_resilience_score", "get_resilience_score.error_profile_incomplete.json", "info"),
        # mã cú sốc không có là lỗi thật
        ("stress", "stress_test", "stress_test.error_shock_not_found.json", "error"),
    ],
)
def test_phase4_tool_error(monkeypatch, intent, tool, error_fixture, kind):
    params = {"shock_id": load_shock_set().shocks[0].shock_id} if intent == "stress" else {}
    payload = fixture(error_fixture)
    events, tools, writer = run_turn(
        "Cho mình xem kết quả",
        llm=make_llm([route_response(intent=intent, **params)]),
        tools=gateway(tool, payload),
        monkeypatch=monkeypatch,
    )
    check_agui_order(events)
    (notice,) = blocks_of(events)
    assert notice["type"] == "notice" and notice["data"]["kind"] == kind
    assert notice["data"]["code"] == payload["code"]
    assert notice["data"]["message"] == payload["message"]
    assert tools.calls == [JARS_READ, (tool, params)] and not writer.calls


def test_stress_chua_co_nen_du_bao_la_info(monkeypatch):
    payload = {"status": "ERROR", "code": ErrorCode.FORECAST_UNAVAILABLE.value, "message": "Chưa có nền dự báo để chạy cú sốc, thử lại sau ít phút."}
    shock_id = load_shock_set().shocks[0].shock_id
    events, _, _ = run_turn(
        "Thử cú sốc",
        llm=make_llm([route_response(intent="stress", shock_id=shock_id)]),
        tools=FakeTools({"stress_test": classify_result("stress_test", mcp_ok(payload))}),
        monkeypatch=monkeypatch,
    )
    (notice,) = blocks_of(events)
    assert notice["data"]["kind"] == "info" and notice["data"]["code"] == ErrorCode.FORECAST_UNAVAILABLE.value


def test_resilience_basis_without_coverage_is_accepted(monkeypatch):
    payload = fixture("get_resilience_score.ok.json")
    basis = payload["data"]["basis"]
    del basis["coverage"]
    records = FakeRecords()
    events, _, writer = run_turn(
        "Điểm chống chịu của mình",
        llm=make_llm([route_response(intent="resilience")]),
        tools=gateway("get_resilience_score", payload),
        monkeypatch=monkeypatch,
        records=records,
    )
    assert [b["type"] for b in blocks_of(events)] == ["resilience_score"]
    assert len(writer.calls) == 1
    assert records.saved[0]["confidence"]["band"] == basis["confidence_band"]


def test_resilience_malformed_basis_fails_block_contract(monkeypatch):
    payload = fixture("get_resilience_score.ok.json")
    payload["data"]["basis"] = {"coverage": "không hợp lệ"}
    events, _, writer = run_turn(
        "Điểm chống chịu của mình",
        llm=make_llm([route_response(intent="resilience")]),
        tools=gateway("get_resilience_score", payload),
        monkeypatch=monkeypatch,
    )
    (notice,) = blocks_of(events)
    assert notice["type"] == "notice" and notice["data"]["kind"] == "error"
    assert notice["data"]["code"] == ErrorCode.INTERNAL_ERROR
    assert not writer.calls


@pytest.mark.parametrize("text, grounded", [("Điểm chống chịu 58.", True), ("Điểm chống chịu 99.", False)])
def test_phase4_writer_verifies_numbers_before_emitting(monkeypatch, text, grounded):
    events, _, _ = run_turn(
        "Điểm chống chịu của mình",
        llm=make_llm([route_response(intent="resilience")]),
        tools=gateway("get_resilience_score", fixture("get_resilience_score.ok.json")),
        writer=FakeWriter(text),
        monkeypatch=monkeypatch,
    )
    assert blocks_of(events)[0]["type"] == "resilience_score"
    assert ("TEXT_MESSAGE_CONTENT" in types(events)) == grounded


def test_handlers_cover_every_intent():
    assert set(Turn._intent_handlers(object.__new__(Turn))) == set(get_args(Intent))


# --- lộ trình nhận mục tiêu người dùng nói trong câu ------------------------------------------------
GOAL_QUESTION = "Lập giúp mình lộ trình gom đủ 1 tỷ đồng trong hũ Du lịch trước cuối tháng này"


def roadmap_tools(*, allocation="ok", latest="error_not_found"):
    """Gateway giả cho đường lập lộ trình; `save_roadmap` lưu đúng feasibility, goals, alternatives được gửi (như ledger)."""

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
            "get_jar_balances": ok("get_jar_balances", "get_jar_balances.ok_goals.json"),
            "get_resilience_score": ok("get_resilience_score", "get_resilience_score.ok.json"),
            "get_roadmap": ok("get_roadmap", f"get_roadmap.{latest}.json"),
            "optimize_allocation": ok("optimize_allocation", f"optimize_allocation.{allocation}.json"),
            "save_roadmap": save,
        }
    )


def review_outline():
    step = {
        "step_id": "giu_muc_tieu",
        "kind": "review_goal",
        "title": "Xem lại mục tiêu",
        "reason": "Theo dõi khả năng giữ mục tiêu",
        "jar_code": "du_lich",
        "action": "schedule_nudge",  # bước không có số tiền phải là nhắc/xem lại có ngày
    }
    return {"phases": [{"phase_id": "on_dinh", "title": "Ổn định ngân sách", "steps": [step]}]}


def goal_turn(monkeypatch, *, tools, writer=None, question=GOAL_QUESTION, **params):
    llm = make_llm(
        [route_response(intent="roadmap", **params), tool_response("draft_roadmap", review_outline())]
    )
    return run_turn(question, llm=llm, tools=tools, writer=writer, monkeypatch=monkeypatch)


def calls_of(tools, name):
    return [args for tool, args in tools.calls if tool == name]


def texts_of(events):
    return [e.delta for e in events if e.type.value == "TEXT_MESSAGE_CONTENT"]


@pytest.mark.parametrize(
    "action, latest, reason",
    [("create", "error_not_found", "initial"), ("create", "ok", "user_request")],
)
def test_lo_trinh_nhan_muc_tieu_trong_cau_va_khoi_infeasible(monkeypatch, action, latest, reason):
    tools = roadmap_tools(allocation="ok_infeasible", latest=latest)
    writer = FakeWriter("Mục tiêu 1 tỷ cho hũ Du lịch trước 30/11/2026 chưa khả thi.")
    events, _, writer = goal_turn(
        monkeypatch,
        tools=tools,
        writer=writer,
        roadmap_action=action,
        amount_vnd=1_000_000_000,
        jar_text="hũ Du lịch",
        date_text="cuối tháng này",
    )
    check_agui_order(events)
    # đổi hũ và ngày bằng mã; mục tiêu chỉ gửi optimize_allocation, không lưu vào hũ
    assert calls_of(tools, "optimize_allocation") == [
        {"goals": [{"jar": "du_lich", "target_vnd": 1_000_000_000, "target_date": "2026-11-30"}]}
    ]
    assert len(calls_of(tools, "get_jar_balances")) == 1  # build_roadmap dùng lại lần đọc hũ của handler
    assert {tool for tool, _ in tools.calls} <= {
        "get_jar_balances", "get_obligations", "get_resilience_score", "get_roadmap",
        "optimize_allocation", "check_suitability", "save_roadmap", "get_behavior_profile",
    }  # fmt: skip  # check_suitability: agent kiểm mọi bước như ledger lúc lưu (fix/roadmap-robust); get_behavior_profile: người tư vấn (luồng K)
    (stored,) = calls_of(tools, "save_roadmap")
    assert stored["reason_code"] == reason
    assert stored["feasibility"] == "infeasible" and len(stored["alternatives"]) == 2
    (block,) = blocks_of(events)
    assert block["type"] == "roadmap"
    assert block["data"]["feasibility"] == "infeasible"
    assert [a["kind"] for a in block["data"]["alternatives"]] == ["delay_goal", "reduce_goal"]
    # không hỏi lại; lời kết dựng bằng mã (không gọi writer) nhắc mục tiêu người dùng nói, nói rõ chưa khả thi và chưa lưu vào hũ
    assert not writer.calls
    (text,) = texts_of(events)
    assert "mục tiêu 1.000.000.000 ₫ cho hũ Du lịch trước 30/11/2026 chưa khả thi" in text
    assert "Thẻ có 2 lựa chọn thay thế" in text and "chưa lưu vào hũ" in text
    assert text.startswith("Đây là bản đề xuất phiên bản ")
    if reason == "user_request":  # lập lại: bản đang dùng (v2) đọc trước khi lưu
        assert "Bản đang dùng vẫn là phiên bản 2." in text and "So với bản đang dùng" in text
    else:
        assert "Bản đang dùng" not in text and "mở trang Lộ trình" in text


def test_router_hong_luat_du_phong_van_nhan_muc_tieu_lo_trinh(monkeypatch):
    """Router trả JSON sai schema: luật dự phòng trích số tiền, hũ, hạn của câu như router nên `optimize_allocation` nhận đúng mục tiêu."""
    tools = roadmap_tools(allocation="ok_infeasible")
    llm = make_llm(
        [tool_response("route", {"intent": "khong_co"}), tool_response("draft_roadmap", review_outline())]
    )
    events, _, _ = run_turn(
        GOAL_QUESTION, llm=llm, tools=tools, monkeypatch=monkeypatch,
        settings=agent_settings(router_max_attempts=1),
    )  # fmt: skip
    check_agui_order(events)
    assert calls_of(tools, "optimize_allocation") == [
        {"goals": [{"jar": "du_lich", "target_vnd": 1_000_000_000, "target_date": "2026-11-30"}]}
    ]
    assert blocks_of(events)[0]["type"] == "roadmap"


@pytest.mark.parametrize(
    "jar_text, note",
    [
        ("hũ Ăn uống", _GOAL_NOT_SAVING.format(name="Ăn uống")),
        ("hũ Nghĩa vụ", _GOAL_NOT_SAVING.format(name="Nghĩa vụ")),
        ("hũ Mua nhà", _GOAL_UNKNOWN_JAR.format(typed="hũ Mua nhà")),
    ],
)
def test_lo_trinh_bo_muc_tieu_hu_khong_phai_tiet_kiem_va_noi_ro(monkeypatch, jar_text, note):
    tools = roadmap_tools()
    events, _, _ = goal_turn(
        monkeypatch,
        tools=tools,
        roadmap_action="create",
        amount_vnd=1_000_000_000,
        jar_text=jar_text,
        date_text="cuối tháng này",
    )
    check_agui_order(events)
    assert texts_of(events)[0] == note
    assert calls_of(tools, "optimize_allocation") == [{}]  # không gửi mục tiêu
    assert [b["type"] for b in blocks_of(events)] == ["roadmap"]


def _jars_payload(rows):
    payload = fixture("get_jar_balances.ok_goals.json")
    base = {"color_key": "teal", "icon_key": "wallet", "balance_vnd": 0, "split_percent": 0}
    payload["data"]["jars"] = [{**base, **r} for r in rows]
    payload["data"]["jars_total_vnd"] = 0
    return payload


THREE_JARS = [
    {"code": "chi_hang_ngay", "name": "Chi hằng ngày", "kind": "spending", "split_percent": 42},
    {"code": "nghia_vu", "name": "Nghĩa vụ", "kind": "obligation", "split_percent": 33},
    {"code": "du_phong", "name": "Dự phòng", "kind": "saving", "purpose": "buffer", "split_percent": 25},
]


LONG_TERM_JAR = {"code": "tich_luy", "name": "Tích lũy dài hạn", "kind": "saving", "purpose": "long_term", "split_percent": 0}
GOAL_JAR = {"code": "muc_tieu", "name": "Du lịch", "kind": "saving", "purpose": "goal", "goal_vnd": 6_000_000,
            "goal_date": "2027-04-01", "split_percent": 0}


@pytest.mark.parametrize(
    ("rows", "jar_text", "note"),
    [
        # hũ tiết kiệm dài hạn: chưa có hũ mục tiêu thì chỉ chỗ thêm, có rồi thì chỉ ra hũ đó
        ([*THREE_JARS, LONG_TERM_JAR], "hũ Tích lũy dài hạn", _GOAL_ADD_GOAL_JAR.format(name="Tích lũy dài hạn")),
        (
            [*THREE_JARS, LONG_TERM_JAR, GOAL_JAR], "hũ Tích lũy dài hạn",
            _GOAL_USE_GOAL_JAR.format(name="Tích lũy dài hạn", goal_jars="Du lịch"),
        ),
    ],
)  # fmt: skip
def test_lo_trinh_muc_tieu_o_hu_tiet_kiem_khong_phai_hu_muc_tieu_noi_dung_tinh_huong(monkeypatch, rows, jar_text, note):
    """Hũ dài hạn LÀ hũ tiết kiệm, chỉ không phải hũ mục tiêu: câu báo nói đúng tình huống, không nói "không phải hũ tiết kiệm"; mục
    tiêu không gửi cho bộ tối ưu và lộ trình vẫn lập."""
    tools = roadmap_tools()
    tools.results["get_jar_balances"] = lambda _a: classify_result("get_jar_balances", mcp_ok(_jars_payload(rows)))
    events, _, _ = goal_turn(
        monkeypatch, tools=tools, roadmap_action="create", amount_vnd=3_000_000, jar_text=jar_text, date_text="3 tháng nữa"
    )
    check_agui_order(events)
    assert texts_of(events)[0] == note
    assert "không phải hũ tiết kiệm" not in note
    assert calls_of(tools, "optimize_allocation") == [{}]


@pytest.mark.parametrize("rows", [THREE_JARS, [*THREE_JARS, GOAL_JAR]])
def test_lo_trinh_muc_tieu_o_hu_du_phong_gui_dich_so_du_cho_bo_toi_uu(monkeypatch, rows):
    """Hũ Dự phòng (`buffer`, BR-64): đích số dư của lượt này đi vào bộ tối ưu như mục tiêu của hũ mục tiêu (#39 26/11), không câu báo
    trước thẻ, không đẩy sang hũ Du lịch."""
    tools = roadmap_tools()
    tools.results["get_jar_balances"] = lambda _a: classify_result("get_jar_balances", mcp_ok(_jars_payload(rows)))
    events, _, _ = goal_turn(
        monkeypatch,
        tools=tools,
        question="lập lộ trình để hũ Dự phòng có 3 triệu sau 3 tháng nữa",  # router giả trả đúng số người dùng nói (mã kiểm số tiền, #39)
        roadmap_action="create",
        amount_vnd=3_000_000,
        jar_text="hũ Dự phòng",
        date_text="3 tháng nữa",
    )
    check_agui_order(events)
    assert calls_of(tools, "optimize_allocation") == [
        {"goals": [{"jar": "du_phong", "target_vnd": 3_000_000, "target_date": "2027-02-21"}]}
    ]
    assert "TEXT_MESSAGE_CONTENT" not in types(events)[: types(events).index("ACTIVITY_SNAPSHOT")]

def test_lo_trinh_han_khong_doc_duoc_thi_hoi_lai_han_khong_lap(monkeypatch):
    """V1 (#39): router không đổi được hạn ra ngày và mã không đọc trọn cụm chỉ hạn: hỏi đúng một câu về hạn, không lập với hạn đã khai
    ở hũ (bỏ câu cố định "dùng hạn đã khai, nếu có")."""
    tools = roadmap_tools()
    events, _, _ = goal_turn(
        monkeypatch,
        tools=tools,
        roadmap_action="create",
        amount_vnd=20_000_000,
        jar_text="Du lịch",
        date_text="sớm nhất có thể",
    )
    check_agui_order(events)
    (block,) = blocks_of(events)
    assert block["type"] == "clarify" and block["data"]["slot"] == "date"
    assert block["data"]["question"] == GOAL_DATE_QUESTION and block["data"]["chips"] == []
    assert not calls_of(tools, "optimize_allocation") and not calls_of(tools, "save_roadmap")
    assert "TEXT_MESSAGE_CONTENT" not in types(events)


def test_lo_trinh_chi_noi_han_dung_so_tien_da_khai_o_hu(monkeypatch):
    tools = roadmap_tools()
    events, _, _ = goal_turn(
        monkeypatch, tools=tools, jar_text="hũ Dự phòng", date_text="6 tháng nữa"
    )
    check_agui_order(events)
    assert calls_of(tools, "optimize_allocation") == [
        {"goals": [{"jar": "du_phong", "target_date": "2027-05-21"}]}
    ]
    assert "TEXT_MESSAGE_CONTENT" not in types(events)[: types(events).index("ACTIVITY_SNAPSHOT")]
