"""Một chính sách cho mọi khoản mua ở lượt chỉ đọc (V4, #39): what-if mua hàng và kiểm tra trước khi chi.

Suy được hũ (router chọn hũ, hoặc đường lùi theo loại chi) thì tính theo hũ đó, kèm notice "Tính theo hũ X" có chip chọn hũ khác và
(ví có hạn mức Trả sau) chip tính bằng Trả sau. Không suy được thì hỏi đúng một câu, chip là mọi hũ của ví cộng Trả sau. Trước đây
"vé concert 1,5tr" (có loại chi) tính luôn còn "nồi chiên 1tr8" (không có loại chi) bị hỏi "trả bằng hũ hay Trả sau": cùng dạng câu mà hai
hành vi. Router giả, không gọi model. Câu số 2 của báo cáo rà soát RR.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from agent_helpers import (
    blocks_of,
    check_agui_order,
    fixture,
    make_llm,
    mcp_ok,
    route_response,
    run_turn,
    tool_response,
)
from test_infer_pay_jar import CODE_FIRST, DEMO_8, _calls, _inferred_notice, _tools, _types
from test_whatif import analysis
from yofina_agent import notices
from yofina_agent.clarify import NOTICE_CHIP_LABELS, NOTICE_CHIP_PROMPTS, PAY_QUESTION
from yofina_agent.tools import classify_result

JARS_AND_CREDIT = [*(j["name"] for j in DEMO_8), "Trả sau (mô phỏng)"]


def _no_credit(name: str) -> Any:
    """Kết quả tool như ví KHÔNG có hạn mức Trả sau (bỏ phần Trả sau)."""
    payload = copy.deepcopy(fixture(name))
    payload["data"].pop("credit", None)
    payload["data"].pop("credit_line", None)
    return lambda _args: classify_result("x", mcp_ok(payload))


def _chips(notice: dict[str, Any]) -> list[tuple[str, str]]:
    return [(s["label"], s["prompt"]) for s in notice.get("suggestions") or []]


def _expected(intent: str, *kinds: str) -> list[tuple[str, str]]:
    return [(NOTICE_CHIP_LABELS[k], NOTICE_CHIP_PROMPTS[intent][k]) for k in kinds]


# --- suy được hũ: tính theo hũ đó, notice có chip đổi hũ và chip Trả sau -----------------------------------------
@pytest.mark.parametrize(
    ("results", "kinds"),
    [({}, ("choose", "credit")), ({"affordability_check": _no_credit("affordability_check.ok.json")}, ("choose",))],
    ids=["vi-co-han-muc", "vi-khong-han-muc"],
)
def test_kiem_tra_suy_duoc_hu_thi_tinh_va_notice_co_chip(monkeypatch, results, kinds):
    llm = make_llm([route_response(intent="affordability", amount_vnd=1_500_000, label="vé concert", tx_type="entertainment")])
    events, tools, _ = run_turn("vé concert 1,5tr có ổn không", llm=llm, tools=_tools(DEMO_8, **results), monkeypatch=monkeypatch)
    check_agui_order(events)
    assert _types(events) == ["notice", "affordability_card"]
    assert _calls(tools, "affordability_check")[0]["jar"] == "giai_tri"
    notice = _inferred_notice(events)
    assert notice is not None and _chips(notice) == _expected("affordability", *kinds)


# --- không suy được: cùng một câu hỏi cho what-if và kiểm tra, chip mọi hũ cộng Trả sau ---------------------------------
@pytest.mark.parametrize(
    ("question", "route"),
    [
        ("Nếu mua nồi chiên không dầu 1tr8 thì các hũ ra sao?", {"intent": "what_if", "scenario_kind": "one_time_purchase"}),
        ("mua nồi chiên 1tr8 lúc này có ổn không", {"intent": "affordability"}),
        ("Nếu mua nồi chiên 1tr8 thì sao", {"intent": "what_if"}),  # router chưa nói loại kịch bản
    ],
)
def test_khong_suy_duoc_hu_thi_hoi_mot_cau_chip_moi_hu_va_tra_sau(monkeypatch, question, route):
    llm = make_llm([route_response(**route, amount_vnd=1_800_000, label="nồi chiên")])
    events, tools, _ = run_turn(question, llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch)
    check_agui_order(events)
    (block,) = blocks_of(events)
    data = block["data"]
    assert block["type"] == "clarify" and data["slot"] == "jar"
    assert data["question"] == PAY_QUESTION and data["question"].count("?") == 1
    assert [c["label"] for c in data["chips"]] == JARS_AND_CREDIT
    assert not _calls(tools, "run_scenario") and not _calls(tools, "affordability_check")


def _answer(monkeypatch, question: str, asked: str, answer: str, routed: dict[str, Any], *, analyst: bool = False):
    script = [route_response(**routed)] + ([tool_response("analyze", analysis())] if analyst else [])
    messages = [
        {"id": "m1", "role": "user", "content": question},
        {"id": "m2", "role": "assistant", "content": asked},
        {"id": "m3", "role": "user", "content": answer},
    ]
    events, tools, _ = run_turn(
        None, llm=make_llm(script), tools=_tools(DEMO_8), settings=CODE_FIRST, monkeypatch=monkeypatch, messages=messages
    )
    check_agui_order(events)
    return events, tools


def test_rr2_tra_loi_hu_chi_hang_ngay_giu_nguyen_so_tien(monkeypatch):
    question = "Nếu mua nồi chiên không dầu 1tr8 thì các hũ ra sao?"
    _, tools = _answer(
        monkeypatch, question, PAY_QUESTION, "Hũ Chi hằng ngày",
        {"intent": "what_if", "scenario_kind": "one_time_purchase", "jar_text": "Chi hằng ngày"}, analyst=True,
    )  # fmt: skip
    (args,) = _calls(tools, "run_scenario")
    assert args["scenario"]["amount_vnd"] == 1_800_000 and args["scenario"]["jar_code"] == "chi_hang_ngay"


def test_chip_tra_sau_cua_cau_hoi_hu_thi_mo_phong_bang_tra_sau(monkeypatch):
    question = "Nếu mua nồi chiên 1tr8 thì sao"
    _, tools = _answer(monkeypatch, question, PAY_QUESTION, "Trả bằng Trả sau (mô phỏng)", {"intent": "what_if"}, analyst=True)
    (args,) = _calls(tools, "run_scenario")
    assert args["scenario"]["kind"] == "bnpl_purchase" and args["scenario"]["amount_vnd"] == 1_800_000


def test_purchase_requires_user_funding_then_uses_the_selected_chip(monkeypatch):
    question = "Nếu mua loa 900 nghìn thì sao?"
    guess = dict(intent="what_if", scenario_kind="one_time_purchase", amount_vnd=900_000,
                 jar_text="Giải trí", spend_jar_code="giai_tri", spend_jar_named=True)
    events, tools, _ = run_turn(question, llm=make_llm([route_response(**guess)]),
                                tools=_tools(DEMO_8), settings=CODE_FIRST, monkeypatch=monkeypatch)
    assert not _calls(tools, "run_scenario")
    (block,) = blocks_of(events)
    assert block["type"] == "clarify" and block["data"]["question"] == PAY_QUESTION
    chip = next(c for c in block["data"]["chips"] if c["label"] == "Chi hằng ngày")
    _, tools = _answer(monkeypatch, question, block["data"]["question"], chip["value"], guess, analyst=True)
    (call,) = _calls(tools, "run_scenario")
    assert call["scenario"]["jar_code"] == "chi_hang_ngay"
    assert call["scenario"]["amount_vnd"] == 900_000


# --- chip của notice "Tính theo hũ X" ------------------------------------------------------------------------------
NOTICE_TEXT = notices.INFERRED_JAR_MESSAGE.format(name="Giải trí", label="Giải trí")
CONCERT = "vé concert 1,5tr có ổn không"


def test_chip_tinh_bang_tra_sau_cua_notice_kiem_tra_lai_bang_tra_sau(monkeypatch):
    _, tools = _answer(
        monkeypatch, CONCERT, NOTICE_TEXT, NOTICE_CHIP_PROMPTS["affordability"]["credit"],
        {"intent": "affordability", "jar_text": "Giải trí", "spend_jar_code": "giai_tri"},  # router đọc lại hũ từ lịch sử
    )  # fmt: skip
    (args,) = _calls(tools, "affordability_check")
    assert args["amount_vnd"] == 1_500_000 and args["funding_source"] == "credit" and "jar" not in args


def test_chip_chon_hu_khac_cua_notice_thi_hoi_hu_voi_du_chip(monkeypatch):
    events, tools = _answer(
        monkeypatch, CONCERT, NOTICE_TEXT, NOTICE_CHIP_PROMPTS["affordability"]["choose"],
        {"intent": "chitchat", "spend_jar_code": "giai_tri", "tx_type": "entertainment"},  # router xếp nhầm và chọn lại hũ cũ
    )  # fmt: skip
    (block,) = blocks_of(events)
    assert block["type"] == "clarify" and block["data"]["question"] == PAY_QUESTION
    assert [c["label"] for c in block["data"]["chips"]] == JARS_AND_CREDIT
    assert not _calls(tools, "affordability_check")
