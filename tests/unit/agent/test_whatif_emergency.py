"""Luật "giữ quỹ dự phòng cho việc gấp" (`emergency_not_for_discretionary`, mức warn) trong luồng what-if.

Ca gốc (Runtime v23, what-if "mua tai nghe 1,2 triệu bằng Trả sau"): phương án "Mua bằng hũ Dự phòng" được đánh "Gợi ý" vì không luật
nào nói tới việc tiêu quỹ dự phòng cho khoản không thiết yếu. `check_suitability` giả ở đây chấm bằng bộ luật THẬT của repo
(`yofina_planner.engine.evaluate`) trên số dư hũ của fixture `get_jar_balances.ok.json`.
"""

from __future__ import annotations

import copy
from datetime import date
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
from test_whatif import text_of
from test_whatif_switch_jar import BASE, NARRATIVE, ROUTE, SCENARIO, Q
from yofina_agent.schemas import AnalysisOption
from yofina_agent.tools import classify_result
from yofina_agent.whatif import (
    EMERGENCY_RULE_ID,
    inherit_purchase_class,
    mark_emergency_spend,
)

from yofina_core.suitability import Proposal, SuitabilityVerdict
from yofina_planner.engine import evaluate
from yofina_planner.facts import JarFact, SuitabilityFacts
from yofina_planner.rules import load_rules

RULES = load_rules()
#: loại hũ và mục tiêu như hồ sơ `minh` (fixture số dư không mang loại hũ): Dự phòng là hũ tiết kiệm không mục tiêu, Du lịch có mục tiêu
KINDS = {"du_lich": "saving", "du_phong": "saving", "nghia_vu": "obligation"}
GOALS = {"du_lich": 6_000_000}


def facts() -> SuitabilityFacts:
    jars = fixture("get_jar_balances.ok.json")["data"]["jars"]
    return SuitabilityFacts(
        today=date(2026, 11, 21),
        next_payday=date(2026, 12, 5),
        monthly_income_vnd=9_000_000,
        risk_tolerance="medium",
        jars=tuple(
            JarFact(j["code"], j["name"], KINDS.get(j["code"], "spending"), j["balance_vnd"], GOALS.get(j["code"]))
            for j in jars
        ),
        obligations=(),
        window_days=30,
    )


def verdict_of(proposal: dict[str, Any]) -> SuitabilityVerdict:
    return evaluate(Proposal.model_validate(proposal, strict=False), facts(), RULES)


def real_suitability(args: dict[str, Any]) -> Any:
    v = verdict_of(args["proposal"])
    payload = {"status": "OK", "as_of": "2026-11-21T02:00:00Z", "app_date": "2026-11-21", "data": v.model_dump(mode="json", exclude_none=True)}
    return classify_result("x", mcp_ok(payload))


def analysis(jar: str, *, proposal: dict[str, Any] | None = None) -> dict[str, Any]:
    switch = proposal if proposal is not None else {"kind": "switch_jar", "funding_source": "jar", "jar_code": jar, **BASE}
    return {
        "narrative": NARRATIVE,
        "options": [
            {
                "option_id": "defer",
                "kind": "defer",
                "label": "Hoãn mua sau kỳ lương",
                "summary": "Hoãn tới sau 05/12 rồi xem lại.",
                "proposal": {"kind": "defer", "funding_source": "jar", **BASE},
            },
            {
                "option_id": "switch",
                "kind": "switch_jar",
                "label": "Mua bằng hũ khác",
                "summary": "Dùng tiền hũ khác thay vì Trả sau.",
                "proposal": switch,
                "jar_code": jar,
                "recommended": True,
            },
        ],
        "follow_ups": [],
    }


def run(monkeypatch: Any, a: dict[str, Any]) -> tuple[list[Any], FakeTools]:
    tools = FakeTools({"check_suitability": real_suitability})
    llm = make_llm([route_response(**ROUTE), tool_response("plan_scenario", SCENARIO), tool_response("analyze", a)])
    events, tools, _ = run_turn(Q, llm=llm, tools=tools, monkeypatch=monkeypatch)
    check_agui_order(events)
    return events, tools


def options_of(events: list[Any]) -> dict[str, dict[str, Any]]:
    block = next(b for b in blocks_of(events) if b["type"] == "options")
    return {o["option_id"]: o for o in block["data"]["options"]}


def switch_calls(tools: FakeTools) -> list[dict[str, Any]]:
    return [a["proposal"] for n, a in tools.calls if n == "check_suitability" and a["proposal"]["kind"] == "switch_jar"]


def test_mua_mon_tuy_y_bang_quy_du_phong_khong_con_goi_y_va_noi_ro_quy_du_phong(monkeypatch):
    events, tools = run(monkeypatch, analysis("du_phong"))
    o = options_of(events)["switch_du_phong"]
    assert o["label"] == "Mua bằng hũ Dự phòng"
    assert o["summary"] == (
        "Trả 1.200.000 ₫ bằng tiền hũ Dự phòng; hũ đang có 2.700.000 ₫, đủ cho khoản này."
        " Tiền lấy từ quỹ dự phòng (hũ Dự phòng), vốn nên giữ cho việc gấp."
    )
    assert o.get("recommended") is None  # model đặt recommended=true; luật cảnh báo nên mã bỏ
    assert o["status"] == "tight"  # warn: vẫn đưa cho người dùng tự chọn, không "Đủ"
    assert EMERGENCY_RULE_ID not in (o.get("checked_rules") or [])
    # warn không phải block: Verifier qua ngay vòng đầu, vẫn có lời giải thích
    assert text_of(events).startswith("Nếu mua tai nghe")
    assert [p["jar_code"] for p in switch_calls(tools)] == ["du_phong"]


def test_model_bo_trong_phan_loai_thi_mang_phan_loai_cua_khoan_mua(monkeypatch):
    # model không nói is_essential/category cho phương án dùng hũ khác: khoản mua của kịch bản là chi tùy ý theo mặc định
    bare = {"kind": "switch_jar", "funding_source": "jar", "jar_code": "du_phong", "risk_level": "low", "origin": "recommendation"}
    events, tools = run(monkeypatch, analysis("du_phong", proposal=bare))
    sent = switch_calls(tools)
    assert [(p["is_essential"], p["category"]) for p in sent] == [(False, "spending")]
    o = options_of(events)["switch_du_phong"]
    assert o.get("recommended") is None and "quỹ dự phòng" in o["summary"]


def test_hu_khac_hoac_khoan_thiet_yeu_van_duoc_goi_y(monkeypatch):
    # hũ Du lịch có mục tiêu: không phải quỹ dự phòng
    events, _ = run(monkeypatch, analysis("du_lich"))
    o = options_of(events)["switch_du_lich"]
    assert o["recommended"] is True and o["status"] == "ok" and "quỹ dự phòng" not in o["summary"]
    assert EMERGENCY_RULE_ID in o["checked_rules"]
    # model (theo lời người dùng) nói là thiết yếu: luật không áp, giữ gợi ý của model
    essential = {"kind": "switch_jar", "funding_source": "jar", "jar_code": "du_phong", **{**BASE, "is_essential": True}}
    events, _ = run(monkeypatch, analysis("du_phong", proposal=essential))
    o = options_of(events)["switch_du_phong"]
    assert o["recommended"] is True and "quỹ dự phòng" not in o["summary"]


def _option(**kw: Any) -> AnalysisOption:
    raw = copy.deepcopy(analysis("du_phong")["options"][1])
    raw["proposal"]["amount_vnd"] = 1_200_000
    raw.update(kw)
    return AnalysisOption.model_validate(raw)


def test_mark_emergency_spend_don_vi():
    jars = [{"code": "du_phong", "name": "Quỹ khẩn cấp", "balance_vnd": 2_700_000}]
    o = _option()
    v = verdict_of(o.proposal.model_dump(exclude_none=True))
    marked = mark_emergency_spend(o, v, jars)
    # tên hũ lấy từ dữ liệu thật, không phải câu cố định cho hũ "Dự phòng"
    assert marked.summary.endswith("Tiền lấy từ quỹ dự phòng (hũ Quỹ khẩn cấp), vốn nên giữ cho việc gấp.")
    assert marked.recommended is None and marked.label == o.label
    assert mark_emergency_spend(marked, v, jars).summary == marked.summary  # không thêm câu hai lần
    # tóm tắt dài: vẫn vừa 200 ký tự và giữ câu về quỹ dự phòng
    long = mark_emergency_spend(_option(summary="x" * 200), v, jars)
    assert len(long.summary) <= 200 and long.summary.endswith("vốn nên giữ cho việc gấp.")
    # không có cảnh báo của luật này thì giữ nguyên
    other = verdict_of({**o.proposal.model_dump(exclude_none=True), "jar_code": "du_lich"})
    assert mark_emergency_spend(o, other, jars) is o


def test_inherit_purchase_class_chi_dien_khi_model_bo_trong():
    bare = _option(proposal={"kind": "switch_jar", "funding_source": "jar", "jar_code": "du_phong", "amount_vnd": 1_200_000})
    filled = inherit_purchase_class(bare).proposal
    assert (filled.is_essential, filled.category) == (False, "spending")
    said = _option(proposal={"kind": "switch_jar", "funding_source": "jar", "jar_code": "du_phong", "is_essential": True, "category": "spending"})
    assert inherit_purchase_class(said) is said
    # phương án không chi tiền hũ cho khoản mua (hoãn) hoặc dùng tín dụng: không đụng
    defer = AnalysisOption.model_validate(analysis("du_phong")["options"][0])
    assert inherit_purchase_class(defer) is defer
    credit = _option(kind="pay_now", proposal={"kind": "pay_now", "funding_source": "credit"})
    assert inherit_purchase_class(credit) is credit
