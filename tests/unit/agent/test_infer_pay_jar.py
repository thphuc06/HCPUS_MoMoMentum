"""Lượt chỉ đọc (what-if, kiểm tra trước khi chi) tự suy hũ trả từ loại chi khi người dùng không nêu hũ (issue #39, 26/11).

Router (giả ở đây, không gọi model) trích loại chi `tx_type` theo danh mục loại giao dịch của sản phẩm; mã đưa loại đó qua CÙNG quy tắc
với phân loại giao dịch (`yofina_core.wallet.spending_tx_type_jar`, tức `transaction_jar`): ví có hũ riêng khớp loại thì hũ riêng, không có
thì hũ chung. Ra đúng một hũ người dùng thì không hỏi, tính luôn và nói rõ bằng khối `notice` thông tin; không có loại, loại không có hũ
nhận hoặc hai hũ ngang nhau thì hỏi như cũ (chip hũ ứng viên trước). Tên hũ người dùng nêu luôn thắng. Mua bằng Trả sau giữ quy tắc hũ
trả riêng: hũ suy theo loại chi không bao giờ thành hũ trả.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from agent_helpers import (
    FakeTools,
    agent_settings,
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
from yofina_agent import notices
from yofina_agent.clarify import infer_pay_jar
from yofina_agent.router import build_router_system
from yofina_agent.schemas import ROUTER_TX_TYPES, IntentParams, IntentResult
from yofina_agent.tools import ToolOutcome, classify_result

from yofina_core.llm import bedrock_json_schema
from yofina_core.wallet import SPENDING_TX_TYPES, TX_TYPE_BNPL_PURCHASE

CODE_FIRST = agent_settings(whatif_spec_source="code_first")
TRAVEL_Q = "đi chơi xa cuối tuần khoảng 2 triệu thì ổn không"  # câu của test, không trùng câu eval hay câu trên app


def _jar(code: str, name: str, kind: str, balance: int, **extra: Any) -> dict[str, Any]:
    return {
        "code": code, "name": name, "color_key": "violet", "icon_key": "wallet", "balance_vnd": balance,
        "split_percent": 10, "kind": kind, **extra,
    }  # fmt: skip


#: ví demo từ 26/11: ba hũ mặc định rồi các hũ tự thêm; hũ goal `muc_tieu` mang tên "Du lịch" và có ít tiền hơn khoản chi của test
DEMO_8 = [
    _jar("chi_hang_ngay", "Chi hằng ngày", "spending", 300_000),
    _jar("nghia_vu", "Nghĩa vụ", "obligation", 1_000_000),
    _jar("du_phong", "Dự phòng", "saving", 2_700_000, purpose="buffer"),
    _jar("an_uong", "Ăn uống", "spending", 380_000),
    _jar("di_lai", "Đi lại", "spending", 640_000),
    _jar("giai_tri", "Giải trí", "spending", 760_000),
    _jar("muc_tieu", "Du lịch", "saving", 1_800_000, purpose="goal", goal_vnd=6_000_000, goal_date="2027-03-31"),
    _jar("dau_tu", "Đầu tư", "saving", 0, purpose="long_term"),
]
THREE = DEMO_8[:3]
THREE_WITH_FOOD = [*THREE, _jar("an_uong", "Ăn uống", "spending", 380_000)]
#: ví không có hũ loại nghĩa vụ (không có hũ trả mặc định cho Trả sau) nhưng có hũ goal nhận du lịch
NO_OBLIGATION = [DEMO_8[0], DEMO_8[2], DEMO_8[6]]


def _balances(jars: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "OK", "as_of": "2026-11-21T02:00:00Z", "app_date": "2026-11-21",
        "data": {"jars": jars, "jars_total_vnd": sum(j["balance_vnd"] for j in jars)},
    }  # fmt: skip


def _tools(jars: list[dict[str, Any]], **results: Any) -> FakeTools:
    payload = _balances(jars)
    return FakeTools({"get_jar_balances": lambda a: classify_result("x", mcp_ok(payload)), **results})


def _calls(tools: FakeTools, name: str) -> list[dict[str, Any]]:
    return [args for n, args in tools.calls if n == name]


def _types(events: list[Any]) -> list[str]:
    return [b["type"] for b in blocks_of(events)]


def _inferred_notice(events: list[Any]) -> dict[str, Any] | None:
    found = [b["data"] for b in blocks_of(events) if b["type"] == "notice" and b["data"].get("code") == "PAY_JAR_INFERRED"]
    assert len(found) <= 1
    return found[0] if found else None


def _assert_notice_names(events: list[Any], jar_name: str) -> None:
    notice = _inferred_notice(events)
    assert notice is not None and notice["kind"] == "info"
    assert jar_name in notice["title"] and jar_name in notice["message"]
    assert not any(ch.isdigit() for ch in notice["message"])  # notice không chứa số liệu tài chính


# --- router: trường loại chi có cấu trúc theo danh mục của sản phẩm -------------------------------------------
def test_loai_chi_cua_router_la_danh_muc_loai_giao_dich_tru_cach_tra():
    expected = {code: label for code, label, _ in SPENDING_TX_TYPES if code != TX_TYPE_BNPL_PURCHASE}
    assert expected == ROUTER_TX_TYPES
    schema = bedrock_json_schema(IntentResult)["properties"]["params"]["properties"]["tx_type"]
    assert schema["enum"] == [*ROUTER_TX_TYPES, None]


@pytest.mark.parametrize("value", ["shopping", "salary", TX_TYPE_BNPL_PURCHASE, "", 3])
def test_ma_loai_ngoai_danh_muc_thi_coi_nhu_khong_trich_duoc_khong_bat_thu_lai(value):
    assert IntentParams(tx_type=value).tx_type is None  # type: ignore[arg-type]
    assert IntentParams(tx_type="travel").tx_type == "travel"


def test_prompt_router_dua_danh_muc_loai_chi_tu_du_lieu_truoc_danh_sach_cu_soc():
    system = build_router_system()
    catalog = "\n".join(f"- {code}: {label}" for code, label in ROUTER_TX_TYPES.items())
    assert catalog in system
    assert system.index(catalog) < system.index("Cú sốc mẫu")
    assert "tx_type" in system.split("Loại chi")[0]  # trường được mô tả trong quy tắc trích tham số


# --- quy tắc "đã rõ" / "chưa rõ" (mã thuần) --------------------------------------------------------------------
def _routed(intent: str = "affordability", **params: Any) -> IntentResult:
    return IntentResult(intent=intent, params=IntentParams(**params), confidence=0.9, needs_clarification=False)  # type: ignore[arg-type]


def test_suy_hu_dat_ten_hu_nhu_nguoi_dung_noi_va_giu_nguyen_tham_so_khac():
    found = infer_pay_jar(_routed(amount_vnd=2_000_000, label="chuyến đi", tx_type="travel"), DEMO_8)
    assert found.inferred is not None and (found.inferred.code, found.inferred.name) == ("muc_tieu", "Du lịch")
    assert found.result.params.jar_text == "Du lịch" and found.result.params.amount_vnd == 2_000_000
    assert found.candidates == ()


@pytest.mark.parametrize(
    ("params", "jars"),
    [
        pytest.param({"amount_vnd": 2_000_000}, DEMO_8, id="khong-trich-duoc-loai"),
        pytest.param({"amount_vnd": 250_000, "tx_type": "transfer_person"}, DEMO_8, id="loai-khong-co-hu-nhan"),
        pytest.param({"amount_vnd": 250_000, "tx_type": "other_expense"}, DEMO_8, id="chi-tieu-khac"),
        pytest.param({"amount_vnd": 2_000_000, "tx_type": "travel"}, [DEMO_8[2], DEMO_8[7]], id="vi-khong-co-hu-nhan"),
        pytest.param({"tx_type": "travel"}, DEMO_8, id="thieu-so-tien-thi-hoi-so-tien-truoc"),
        pytest.param({"amount_vnd": 2_000_000, "tx_type": "travel", "jar_text": "Ăn uống"}, DEMO_8, id="ten-hu-nguoi-dung-thang"),
        pytest.param({"amount_vnd": 2_000_000, "tx_type": "travel", "funding": "credit"}, DEMO_8, id="tra-sau-khong-suy-hu-tra"),
    ],
)
def test_khong_suy_hu_khi_chua_ro_hoac_khong_can(params, jars):
    routed = _routed(**params)
    found = infer_pay_jar(routed, jars)
    assert found.inferred is None and found.result == routed


def test_hai_hu_ngang_nhau_thi_chua_ro_va_tra_ung_vien():
    twins = [*DEMO_8, _jar("du_lich_he", "Du lịch", "saving", 100_000, purpose="goal")]
    found = infer_pay_jar(_routed(amount_vnd=2_000_000, tx_type="travel"), twins)
    assert found.inferred is None and found.result.params.jar_text is None
    assert found.candidates[:2] == ("muc_tieu", "du_lich_he")


def test_y_dinh_ghi_khong_suy_hu():
    routed = _routed("profile_update", obligation_name="Tiền trọ", obligation_kind="rent", amount_vnd=2_500_000, tx_type="rent")
    assert infer_pay_jar(routed, THREE).result == routed


# --- kiểm tra trước khi chi (affordability) --------------------------------------------------------------------
def test_kiem_tra_du_lich_khong_noi_hu_tinh_luon_theo_hu_goal_va_noi_ro(monkeypatch):
    # router còn tự hỏi hũ (như lỗi thấy trên app): mã đã suy được hũ nên bỏ câu hỏi đó
    ask = {"slot": "jar", "question": notices.CLARIFY["pay_jar"]["question"], "chips": []}
    llm = make_llm([route_response(intent="affordability", amount_vnd=2_000_000, label="chuyến đi", tx_type="travel", clarify=ask)])
    events, tools, writer = run_turn(TRAVEL_Q, llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch)
    check_agui_order(events)
    assert "clarify" not in _types(events)
    assert [n for n, _ in tools.calls] == ["get_jar_balances", "affordability_check"]
    (args,) = _calls(tools, "affordability_check")
    # hũ goal ít tiền hơn khoản chi: không chặn, vẫn kiểm (thẻ nói đủ, sát hay hụt)
    assert args == {"amount_vnd": 2_000_000, "label": "chuyến đi", "jar": "muc_tieu"}
    assert _types(events) == ["notice", "affordability_card"]
    _assert_notice_names(events, "Du lịch")
    # một lượt: router + lời của model nhỏ; trước đây là lượt hỏi hũ (router) rồi lượt trả lời (router + lời)
    assert len(llm[1].calls) == 1 and [c["task"] for c in writer.calls] == ["affordability"]


@pytest.mark.parametrize(
    ("jars", "expected"),
    [
        pytest.param(DEMO_8, "an_uong", id="vi-demo-8-hu"),
        pytest.param(THREE, "chi_hang_ngay", id="vi-3-hu"),
        pytest.param(THREE_WITH_FOOD, "an_uong", id="vi-3-hu-them-an-uong"),
    ],
)
def test_kiem_tra_an_uong_theo_hu_rieng_hoac_hu_chung(monkeypatch, jars, expected):
    llm = make_llm([route_response(intent="affordability", amount_vnd=150_000, tx_type="food_drink")])
    events, tools, _ = run_turn("bữa tối nay 150k có sao không", llm=llm, tools=_tools(jars), monkeypatch=monkeypatch)
    (args,) = _calls(tools, "affordability_check")
    assert args["jar"] == expected
    _assert_notice_names(events, next(j["name"] for j in jars if j["code"] == expected))


def test_hoa_don_tren_vi_ba_hu_vao_nghia_vu(monkeypatch):
    llm = make_llm([route_response(intent="affordability", amount_vnd=400_000, tx_type="bill_electricity")])
    _, tools, _ = run_turn("trả tiền điện 400k lúc này được không", llm=llm, tools=_tools(THREE), monkeypatch=monkeypatch)
    assert _calls(tools, "affordability_check")[0]["jar"] == "nghia_vu"


def test_nguoi_dung_noi_ten_hu_thi_ten_hu_thang_va_khong_co_notice_suy_hu(monkeypatch):
    """Lượt sau "tính theo hũ khác": router ghép câu trước với tên hũ mới; tên hũ thắng loại chi."""
    msgs = [
        {"id": "m1", "role": "user", "content": TRAVEL_Q},
        {"id": "m2", "role": "assistant", "content": "Bạn chưa nói hũ nào nên mình tính theo hũ Du lịch."},
        {"id": "m3", "role": "user", "content": "tính theo hũ Ăn uống"},
    ]
    llm = make_llm([route_response(intent="affordability", amount_vnd=2_000_000, tx_type="travel", jar_text="Ăn uống")])
    events, tools, _ = run_turn(None, llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch, messages=msgs)
    assert _calls(tools, "affordability_check")[0]["jar"] == "an_uong"
    assert _inferred_notice(events) is None and "clarify" not in _types(events)


@pytest.mark.parametrize(
    "tx_type",
    [pytest.param(None, id="khong-co-loai"), pytest.param("transfer_person", id="loai-khong-co-hu-nhan")],
)
def test_chua_ro_hu_thi_hoi_nhu_cu_chip_hu_that(monkeypatch, tx_type):
    llm = make_llm([route_response(intent="affordability", amount_vnd=250_000, label="người nhận", tx_type=tx_type)])
    events, tools, _ = run_turn("gửi 250k cho bạn có ổn không", llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch)
    check_agui_order(events)
    assert _types(events) == ["clarify"] and not _calls(tools, "affordability_check")
    data = blocks_of(events)[0]["data"]
    assert data["slot"] == "jar" and data["question"] == notices.CLARIFY["pay_jar"]["question"]
    assert [c["label"] for c in data["chips"]] == [j["name"] for j in DEMO_8][:6]  # thứ tự trong ví như trước


def test_hai_hu_ngang_nhau_thi_hoi_chip_ung_vien_dung_dau(monkeypatch):
    twins = [*DEMO_8, _jar("du_lich_he", "Du lịch", "saving", 100_000, purpose="goal")]
    llm = make_llm([route_response(intent="affordability", amount_vnd=2_000_000, tx_type="travel")])
    events, tools, _ = run_turn(TRAVEL_Q, llm=llm, tools=_tools(twins), monkeypatch=monkeypatch)
    assert _types(events) == ["clarify"] and not _calls(tools, "affordability_check")
    chips = blocks_of(events)[0]["data"]["chips"]
    assert [c["label"] for c in chips][:3] == ["Du lịch", "Du lịch", "Chi hằng ngày"]


def test_thieu_so_tien_van_hoi_so_tien_khong_doc_hu(monkeypatch):
    llm = make_llm([route_response(intent="affordability", tx_type="travel")])
    events, tools, _ = run_turn("đi chơi xa cuối tuần có ổn không", llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch)
    assert tools.calls == [] and _types(events) == ["clarify"]
    assert blocks_of(events)[0]["data"]["slot"] == "amount"


def test_kiem_tra_tra_sau_khong_dung_hu_suy_theo_loai_lam_hu_tra(monkeypatch):
    def afford(args: dict[str, Any]) -> ToolOutcome:
        name = "affordability_check.ok.json" if "pay_jar" in args else "affordability_check.error_pay_jar_required.json"
        return classify_result("x", mcp_ok(fixture(name)))

    llm = make_llm([route_response(intent="affordability", amount_vnd=2_000_000, funding="credit", tx_type="travel")])
    events, tools, _ = run_turn(TRAVEL_Q, llm=llm, tools=_tools(NO_OBLIGATION, affordability_check=afford), monkeypatch=monkeypatch)
    (args,) = _calls(tools, "affordability_check")
    assert "jar" not in args and "pay_jar" not in args
    assert _types(events) == ["clarify"] and _inferred_notice(events) is None  # hỏi hũ trả theo quy tắc hũ trả như cũ


# --- what-if ---------------------------------------------------------------------------------------------------
ROUTE_TRIP = {"intent": "what_if", "amount_vnd": 2_000_000, "scenario_kind": "one_time_purchase", "label": "chuyến đi", "tx_type": "travel"}


def test_what_if_du_lich_khong_noi_cach_tra_hay_hu_thi_tinh_luon(monkeypatch):
    """Trước đây hỏi "trả bằng tiền trong hũ hay Trả sau" rồi hỏi hũ; nay hũ đã rõ nên tính luôn từ hũ đó."""
    llm = make_llm([route_response(**ROUTE_TRIP), tool_response("analyze", analysis())])
    events, tools, _ = run_turn(TRAVEL_Q, llm=llm, tools=_tools(DEMO_8), settings=CODE_FIRST, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert "clarify" not in _types(events)
    (args,) = _calls(tools, "run_scenario")
    assert args["scenario"] == {
        "kind": "one_time_purchase", "amount_vnd": 2_000_000, "funding_source": "jar", "jar_code": "muc_tieu", "label": "chuyến đi",
    }  # fmt: skip
    kinds = _types(events)
    assert kinds.index("notice") < kinds.index("forecast_timeline")
    _assert_notice_names(events, "Du lịch")
    assert len(llm[1].calls) == 2  # router, Analyst (spec dựng bằng mã)


def test_what_if_orchestrator_nhan_ten_hu_da_suy_trong_tham_so_router(monkeypatch):
    spec = {"kind": "one_time_purchase", "amount_vnd": 2_000_000, "funding_source": "jar", "jar_code": "muc_tieu", "label": "chuyến đi",
            "date": "2026-12-05"}  # fmt: skip
    llm = make_llm(
        [
            route_response(**ROUTE_TRIP, date_text="tháng sau"),
            tool_response("plan_scenario", {"scenario": spec}),
            tool_response("analyze", analysis()),
        ]
    )
    events, tools, _ = run_turn(TRAVEL_Q, llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch)
    prompt = llm[1].calls[1]["messages"][0]["content"][0]["text"]
    router_params = json.loads(prompt.split("<tham_so_router>\n", 1)[1].split("\n</tham_so_router>", 1)[0])
    assert router_params["jar_text"] == "Du lịch" and router_params["tx_type"] == "travel"
    assert _calls(tools, "run_scenario")[0]["scenario"]["jar_code"] == "muc_tieu"
    _assert_notice_names(events, "Du lịch")
    assert len(llm[1].calls) == 3  # router, Orchestrator, Analyst: không thêm lời gọi nào


def test_what_if_chua_ro_hu_van_hoi_cach_tra_nhu_cu(monkeypatch):
    route = {k: v for k, v in ROUTE_TRIP.items() if k != "tx_type"}
    llm = make_llm([route_response(**route)])
    events, tools, _ = run_turn(TRAVEL_Q, llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch)
    assert _types(events) == ["clarify"] and blocks_of(events)[0]["data"]["slot"] == "funding_source"
    assert tools.calls == []  # không loại chi thì không cần đọc hũ (như trước)


def test_what_if_tra_sau_giu_quy_tac_hu_tra(monkeypatch):
    def scenario(args: dict[str, Any]) -> ToolOutcome:
        name = "run_scenario.ok_bnpl.json" if "pay_jar" in args["scenario"] else "run_scenario.error_pay_jar_required.json"
        return classify_result("x", mcp_ok(fixture(name)))

    route = {**ROUTE_TRIP, "scenario_kind": "bnpl_purchase", "funding": "credit"}
    llm = make_llm([route_response(**route)])
    events, tools, _ = run_turn(
        TRAVEL_Q, llm=llm, tools=_tools(NO_OBLIGATION, run_scenario=scenario), settings=CODE_FIRST, monkeypatch=monkeypatch
    )
    (args,) = _calls(tools, "run_scenario")
    assert "pay_jar" not in args["scenario"] and "jar_code" not in args["scenario"]
    assert _types(events) == ["clarify"] and _inferred_notice(events) is None
    assert blocks_of(events)[0]["data"]["question"] == notices.CLARIFY["pay_jar"]["question"]


# --- lượt ghi giữ luồng cũ -------------------------------------------------------------------------------------
def test_khai_nghia_vu_khong_dung_hu_suy_theo_loai(monkeypatch):
    llm = make_llm(
        [route_response(intent="profile_update", obligation_name="Tiền trọ", obligation_kind="rent", amount_vnd=2_500_000, tx_type="rent")]
    )
    events, tools, _ = run_turn("tiền trọ 2,5 triệu mỗi tháng", llm=llm, tools=_tools(THREE), monkeypatch=monkeypatch)
    assert "pay_jar" not in _calls(tools, "update_profile")[0]["obligation"]
    assert _types(events) == ["confirm_action"] and _inferred_notice(events) is None
