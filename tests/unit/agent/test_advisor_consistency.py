"""Luồng K (#7): lập luận phải nhất quán với kết quả ĐÃ LƯU của lượt, kiểm bằng mã sau các kiểm số và căn cứ đã có.

Hũ nhận bằng tên/mã hũ thật của lượt (`jar_rows`), luật bằng mã căn cứ bước đã khai và phán quyết `check_suitability` của lượt; không có
danh sách từ khóa nào. Model, tool và bộ nhớ là đồ giả.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_helpers import (
    FakeTools,
    blocks_of,
    fixture,
    make_llm,
    mcp_ok,
    route_response,
    run_turn,
    tool_response,
)
from test_advisor import ROADMAP_STEP_BEHAVIOR, ROADMAP_STEP_OBLIGATION, STEP_BEHAVIOR
from test_roadmap_agent import build, outline, review, scripted_tools, step
from test_whatif import NARRATIVE, ROUTE_WHAT_IF, SCENARIO, WHAT_IF_Q
from yofina_agent import advisor
from yofina_agent.schemas import ReasoningStepIn
from yofina_agent.tools import classify_result

from yofina_core.suitability import SuitabilityVerdict

#: hũ thật của lượt (như `get_jar_balances.ok`): mã -> tên
JAR_NAMES = {j["code"]: j["name"] for j in fixture("get_jar_balances.ok.json")["data"]["jars"]}


def verdict(**outcomes: str) -> SuitabilityVerdict:
    """Phán quyết như `check_suitability.ok` với vài luật đổi kết quả (`fail` là luật chặn: kèm vi phạm mức block)."""
    data = fixture("check_suitability.ok.json")["data"]
    checked = [{**c, "outcome": outcomes.get(c["rule_id"], c["outcome"])} for c in data["checked"]]
    violations = [
        {"rule_id": rule, "severity": "block", "message": "Hũ nguồn không đủ tiền cho khoản này."}
        for rule, outcome in outcomes.items()
        if outcome == "fail"
    ]
    return SuitabilityVerdict.model_validate(
        {**data, "ok": not violations, "violations": violations, "checked": checked}
    )


def reasoning_step(seen: str, why: str, effect: str, *basis: str) -> ReasoningStepIn:
    return ReasoningStepIn.model_validate(
        {"seen": seen, "why": why, "effect": effect, "basis": list(basis)}
    )


def check(
    steps: list[ReasoningStepIn], saved: advisor.SavedResult, verdicts: list[SuitabilityVerdict]
):
    return advisor.verify_steps(
        steps,
        grounded=lambda _text: True,  # số đã qua kiểm riêng; ở đây chỉ xét nhất quán
        tools=["get_jar_balances", "run_scenario", "get_obligations"],
        rules=advisor.checked_rules(verdicts),
        saved=saved,
    )


# --- cảnh 2: what-if "Nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao" -------------------------------------------------
#: luật "Hũ nguồn đủ tiền" đã loại đề xuất trả bằng hũ Giải trí (760.000 ₫ < 1.200.000 ₫); phương án Du lịch qua
CANH2_JUDGED: list[tuple[str | None, SuitabilityVerdict]] = [
    ("giai_tri", verdict(source_jar_covers="fail")),
    ("du_lich", verdict(source_jar_covers="pass")),
]
CANH2_STEP = reasoning_step(
    "Hũ Giải trí còn 760.000 ₫, hũ Du lịch còn 1.800.000 ₫, đều có thể dùng để mua tai nghe 1.200.000 ₫.",
    "Tai nghe là đồ tùy ý, hợp lấy từ hũ hơn là vay.",
    "Mở ra phương án dùng tiền hũ thay vì Trả sau.",
    "tool:get_jar_balances",
    "rule:source_jar_covers",
)
CANH2_SHORTFALL = reasoning_step(
    "Mua bằng Trả sau thì ngày 05/12 hũ Nghĩa vụ phải trả 2.200.000 ₫.",
    "Thiếu tiền đúng hạn thì dễ bị trễ thanh toán.",
    "Nghiêng về không dùng Trả sau cho khoản này.",
    "tool:run_scenario",
    "tool:get_obligations",
)


def test_canh2_buoc_trich_luat_da_loai_hu_no_nhac_bi_bo():
    # hũ Giải trí vẫn có mặt trong kết quả (ví dụ một phương án chuyển bù nhận tiền vào hũ đó): chỉ luật đã loại nó làm bỏ bước
    saved = advisor.SavedResult(
        jar_names=JAR_NAMES,
        step_jars=frozenset({"nghia_vu", "du_lich", "giai_tri"}),
        conclusion_jars=frozenset({"nghia_vu", "du_lich"}),
        rejected=advisor.rule_rejections(CANH2_JUDGED),
    )
    kept, dropped = check([CANH2_SHORTFALL, CANH2_STEP], saved, [v for _, v in CANH2_JUDGED])
    assert [s.seen for s in kept] == [CANH2_SHORTFALL.seen]
    assert dropped["rule_conflict"] == 1 and dropped["jar_mismatch"] == 0


# --- lộ trình: lập luận nói chuyển từ hũ Giải trí, bản đã lưu chuyển từ hũ Đi lại ------------------------------------------
ROADMAP_SAVED = advisor.SavedResult(
    jar_names=JAR_NAMES,
    step_jars=frozenset({"di_lai", "an_uong"}),  # bước đã lưu: chuyển từ Đi lại sang Ăn uống
    conclusion_jars=frozenset({"di_lai", "an_uong"}),
)
ROADMAP_SEEN = "Hũ Ăn uống chỉ còn 380.000 ₫ trong khi mức thiết yếu tháng là 2.956.000 ₫."
ROADMAP_WHY = "Hũ thiết yếu sắp cạn, cần bổ sung từ hũ có dư trước kỳ lương."


def test_lo_trinh_buoc_noi_hu_nguon_khac_ban_da_luu_bi_bo():
    wrong = reasoning_step(
        ROADMAP_SEEN,
        ROADMAP_WHY,
        "Thêm bước chuyển từ hũ Giải trí sang Ăn uống trong giai đoạn đầu.",
        "tool:get_jar_balances",
        "rule:source_jar_covers",
    )
    kept, dropped = check([wrong], ROADMAP_SAVED, [verdict()])
    assert kept == [] and dropped["jar_mismatch"] == 1 and dropped["rule_conflict"] == 0


def test_lap_luan_nhat_quan_giu_nguyen():
    right = reasoning_step(
        ROADMAP_SEEN,
        ROADMAP_WHY,
        "Thêm bước chuyển từ hũ Đi lại sang Ăn uống trong giai đoạn đầu.",
        "tool:get_jar_balances",
        "rule:source_jar_covers",
    )
    # chữ thường là danh từ chung, không phải tên hũ: "khoản nghĩa vụ", "quỹ dự phòng"
    generic = reasoning_step(
        "Khoản nghĩa vụ tháng này đã có tiền.",
        "Bạn không phải lấy quỹ dự phòng.",
        "Giai đoạn đầu chỉ cần bù hũ Ăn uống.",
        "tool:get_obligations",
    )
    kept, dropped = check([right, generic], ROADMAP_SAVED, [verdict(source_jar_covers="pass")])
    assert [(s.step_id, s.seen, s.effect) for s in kept] == [
        ("s1", right.seen, right.effect),
        ("s2", generic.seen, generic.effect),
    ]
    assert [b.ref for b in kept[0].basis] == ["get_jar_balances", "source_jar_covers"]
    assert dropped == {"grounding": 0, "basis": 0, "rule_conflict": 0, "jar_mismatch": 0}
    # cảnh 2: phương án được khuyên là hũ Du lịch, bước nói về hũ Nghĩa vụ của kịch bản và hũ Du lịch
    saved = advisor.SavedResult(
        jar_names=JAR_NAMES,
        step_jars=frozenset({"nghia_vu", "du_lich"}),
        conclusion_jars=frozenset({"nghia_vu", "du_lich"}),
        rejected=advisor.rule_rejections(CANH2_JUDGED),
    )
    du_lich = reasoning_step(
        "Hũ Du lịch còn 1.800.000 ₫, đủ trả tai nghe 1.200.000 ₫.",
        "Trả bằng tiền sẵn có thì không thêm nợ.",
        "Nghiêng về dùng hũ Du lịch.",
        "tool:get_jar_balances",
        "rule:source_jar_covers",
    )
    kept, _ = check([CANH2_SHORTFALL, du_lich], saved, [v for _, v in CANH2_JUDGED])
    assert [s.seen for s in kept] == [CANH2_SHORTFALL.seen, du_lich.seen]


def conclude(text: str, saved: advisor.SavedResult):
    return advisor.verify_conclusion(
        text,
        (),
        grounded=lambda _text: True,
        target_ok=True,
        has_memory=False,
        has_behavior=False,
        step_id="chuyen_di_lai",
        saved=saved,
    )


def test_ket_luan_mau_thuan_thi_bo_ca_khoi():
    conclusion, why = conclude(
        "Bạn nên chuyển tiền từ hũ Giải trí sang Ăn uống ngay hôm nay.", ROADMAP_SAVED
    )
    assert conclusion is None and why == "jar_mismatch"
    steps, dropped = check(
        [
            reasoning_step(
                ROADMAP_SEEN, ROADMAP_WHY, "Giai đoạn đầu bù hũ Ăn uống.", "tool:get_jar_balances"
            ),
            reasoning_step(
                "Hũ Đi lại còn 640.000 ₫.",
                "Đi lại có thể giảm bớt.",
                "Lấy bớt từ Đi lại.",
                "tool:get_jar_balances",
            ),
        ],
        ROADMAP_SAVED,
        [verdict()],
    )
    advice, block = advisor.settle("roadmap", steps, conclusion, dropped, why, min_steps=2)
    assert len(steps) == 2 and advice.empty and block == "conclusion_conflict"


def test_bo_buoc_mau_thuan_con_it_hon_so_buoc_toi_thieu_thi_bo_ca_khoi():
    conclusion, why = conclude(
        "Bạn nên bắt đầu bằng bước chuyển từ hũ Đi lại sang Ăn uống.", ROADMAP_SAVED
    )
    assert conclusion is not None and why == "kept"
    wrong = reasoning_step(
        ROADMAP_SEEN, ROADMAP_WHY, "Chuyển từ hũ Giải trí sang Ăn uống.", "tool:get_jar_balances"
    )
    right = reasoning_step(
        ROADMAP_SEEN, ROADMAP_WHY, "Chuyển từ hũ Đi lại sang Ăn uống.", "tool:get_jar_balances"
    )
    steps, dropped = check([wrong, right], ROADMAP_SAVED, [verdict()])
    advice, block = advisor.settle("roadmap", steps, conclusion, dropped, why, min_steps=2)
    assert len(steps) == 1 and advice.empty and block == "too_few_steps"
    # đủ số bước tối thiểu thì giữ khối, chỉ thiếu bước mâu thuẫn
    advice, block = advisor.settle("roadmap", steps, conclusion, dropped, why, min_steps=1)
    assert (
        block == "kept"
        and [s.effect for s in advice.steps] == [right.effect]
        and advice.conclusion == conclusion
    )
    # không có bước nào bị bỏ vì mâu thuẫn thì số bước tối thiểu không áp (như trước #7)
    steps, dropped = check([right], ROADMAP_SAVED, [verdict()])
    advice, block = advisor.settle("roadmap", steps, conclusion, dropped, why, min_steps=2)
    assert block == "kept" and len(advice.steps) == 1


# --- lượt what-if, Analyst giả trả lập luận mâu thuẫn với phương án đã phát (cảnh 2) -----------------------------------------
PROPOSAL_BASE = {
    "is_essential": False,
    "category": "spending",
    "risk_level": "low",
    "origin": "recommendation",
}
SHORTFALL = {
    "seen": "Mua bằng Trả sau thì ngày 05/12 hũ Nghĩa vụ phải trả 2.200.000 ₫.",
    "why": "Thiếu tiền đúng hạn thì dễ bị trễ thanh toán.",
    "effect": "Nghiêng về không dùng Trả sau cho khoản này.",
    "basis": ["tool:run_scenario", "tool:get_obligations"],
}
CONTRADICTS = CANH2_STEP.model_dump()


def switch_analysis(jar: str, **advice: Any) -> dict[str, Any]:
    return {
        "narrative": NARRATIVE,
        "options": [
            {
                "option_id": "defer",
                "kind": "defer",
                "label": "Hoãn mua sau kỳ lương",
                "summary": "Hoãn tới sau 05/12 rồi xem lại.",
                "proposal": {"kind": "defer", "funding_source": "jar", **PROPOSAL_BASE},
            },
            {
                "option_id": "switch",
                "kind": "switch_jar",
                "label": "Mua bằng hũ khác",
                "summary": "Trả bằng tiền hũ.",
                "proposal": {
                    "kind": "switch_jar",
                    "funding_source": "jar",
                    "jar_code": jar,
                    **PROPOSAL_BASE,
                },
                "jar_code": jar,
                "recommended": True,
            },
        ],
        "follow_ups": [],
        **advice,
    }


def source_jar_check(args: dict[str, Any]) -> Any:
    """check_suitability giả: luật "Hũ nguồn đủ tiền" chặn đề xuất trả bằng hũ Giải trí (như engine thật với 760.000 ₫)."""
    payload = fixture("check_suitability.ok.json")
    p = args["proposal"]
    if p.get("funding_source") == "jar" and p.get("jar_code") == "giai_tri":
        payload = {
            **payload,
            "data": verdict(source_jar_covers="fail").model_dump(mode="json", exclude_none=True),
        }
    return classify_result("check_suitability", mcp_ok(payload))


def advisor_logs(caplog: Any) -> list[dict[str, Any]]:
    out = []
    for r in caplog.records:
        if r.name == "yofina.agent.advisor" and r.getMessage().startswith("{"):
            out.append(json.loads(r.getMessage()))
    return [e for e in out if e.get("event") == "advisor_reasoning"]


def reasoning_of(events: list[Any]) -> list[dict[str, Any]]:
    return [b for b in blocks_of(events) if b["type"] == "reasoning"]


def test_whatif_analyst_lap_luan_mau_thuan_thi_khoi_khong_con_buoc_vi_pham(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="yofina.agent.advisor")
    conclusion = {
        "text": "Bạn nên dùng tiền hũ Du lịch thay vì Trả sau để hũ Nghĩa vụ không hụt ngày 05/12.",
        "option_id": "switch",
        "personal": [],
    }
    llm = make_llm(
        [
            route_response(**ROUTE_WHAT_IF),
            tool_response("plan_scenario", SCENARIO),
            # vòng 1: đề xuất trả bằng hũ Giải trí, luật "Hũ nguồn đủ tiền" loại; vòng 2: hũ Du lịch, lập luận vẫn nói Giải trí đủ
            tool_response("analyze", switch_analysis("giai_tri")),
            tool_response(
                "analyze",
                switch_analysis(
                    "du_lich",
                    reasoning=[SHORTFALL, CONTRADICTS, STEP_BEHAVIOR],
                    conclusion=conclusion,
                ),
            ),
        ]
    )
    events, _, _ = run_turn(
        WHAT_IF_Q,
        llm=llm,
        tools=FakeTools({"check_suitability": source_jar_check}),
        monkeypatch=monkeypatch,
    )
    snaps = reasoning_of(events)
    assert snaps, "còn đủ bước nhất quán thì vẫn có khối"
    final = snaps[-1]["data"]
    assert [s["seen"] for s in final["steps"]] == [SHORTFALL["seen"], STEP_BEHAVIOR["seen"]]
    assert final["conclusion"]["option_id"] == "switch_du_lich"
    assert "Giải trí" not in json.dumps(snaps, ensure_ascii=False)
    (logged,) = advisor_logs(caplog)
    assert logged["dropped_rule_conflict"] == 1 and logged["block"] == "kept"
    assert "Giải trí" not in json.dumps(logged, ensure_ascii=False) and "760" not in json.dumps(
        logged
    )


def two_jar_analysis(conclusion_text: str) -> dict[str, Any]:
    """Analyst đưa hai phương án trả bằng tiền hũ (Du lịch được gợi ý, Giải trí), lập luận nhất quán và một câu kết luận."""
    out = switch_analysis(
        "du_lich",
        reasoning=[SHORTFALL, STEP_BEHAVIOR],
        conclusion={"text": conclusion_text, "option_id": "switch", "personal": []},
    )
    out["options"][0] = {
        "option_id": "giai_tri",
        "kind": "switch_jar",
        "label": "Mua bằng hũ Giải trí",
        "summary": "Trả bằng tiền hũ.",
        "proposal": {
            "kind": "switch_jar",
            "funding_source": "jar",
            "jar_code": "giai_tri",
            **PROPOSAL_BASE,
        },
        "jar_code": "giai_tri",
    }
    return out


def whatif_turn(analysis_payload: dict[str, Any], monkeypatch: Any) -> list[Any]:
    llm = make_llm(
        [
            route_response(**ROUTE_WHAT_IF),
            tool_response("plan_scenario", SCENARIO),
            tool_response("analyze", analysis_payload),
        ]
    )
    events, _, _ = run_turn(WHAT_IF_Q, llm=llm, tools=FakeTools(), monkeypatch=monkeypatch)
    return events


def test_whatif_ket_luan_so_hai_phuong_an_deu_da_phat_thi_giu_khoi(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="yofina.agent.advisor")
    text = "Bạn nên trả bằng hũ Du lịch thay vì hũ Giải trí để hũ Nghĩa vụ không hụt ngày 05/12."
    events = whatif_turn(two_jar_analysis(text), monkeypatch)
    options = [b for b in blocks_of(events) if b["type"] == "options"]
    assert {o["option_id"] for o in options[-1]["data"]["options"]} == {
        "switch_giai_tri",
        "switch_du_lich",
    }
    final = reasoning_of(events)[-1]["data"]
    assert [s["seen"] for s in final["steps"]] == [SHORTFALL["seen"], STEP_BEHAVIOR["seen"]]
    assert final["conclusion"]["text"] == text
    assert final["conclusion"]["option_id"] == "switch_du_lich"
    (logged,) = advisor_logs(caplog)
    assert logged["conclusion"] == "kept" and logged["block"] == "kept"


def test_whatif_ket_luan_nhac_hu_ngoai_moi_phuong_an_van_bo_ca_khoi(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="yofina.agent.advisor")
    # hũ Đi lại không thuộc phương án nào đã phát, cũng không thuộc kịch bản
    text = "Bạn nên trả bằng hũ Du lịch thay vì hũ Đi lại để hũ Nghĩa vụ không hụt ngày 05/12."
    events = whatif_turn(two_jar_analysis(text), monkeypatch)
    assert reasoning_of(events) == []
    (logged,) = advisor_logs(caplog)
    assert logged["conclusion"] == "jar_mismatch" and logged["block"] == "conclusion_conflict"


# --- lộ trình trong chat, planner giả trả lập luận nói hũ nguồn khác bản đã lưu ----------------------------------------------
def saved_from(old: str, new: str) -> dict[str, Any]:
    """`save_roadmap.ok` với hũ nguồn `old` của mọi bước đổi thành `new` (bản đã lưu chuyển tiền từ hũ khác)."""
    payload = fixture("save_roadmap.ok.json")
    for phase in payload["data"]["phases"]:
        for s in phase["steps"]:
            if s.get("jar_code") == old:
                s["jar_code"] = new
            params = (s.get("action") or {}).get("params") or {}
            if params.get("from_jar") == old:
                params["from_jar"] = new
    return payload


ROADMAP_WRONG = {
    "seen": "Hũ Ăn uống sắp cạn trước kỳ lương.",
    "why": "Thiếu tiền ăn thì khó giữ lộ trình.",
    "effect": "Thêm bước chuyển từ hũ Giải trí sang Ăn uống trong giai đoạn đầu.",
    "basis": ["tool:get_jar_balances"],
}


def test_lo_trinh_planner_noi_hu_nguon_khac_ban_da_luu_thi_bo_buoc(caplog):
    caplog.set_level(logging.INFO, logger="yofina.agent.advisor")
    draft = outline(step(jar_code="di_lai"), review())
    draft["reasoning"] = [ROADMAP_WRONG, ROADMAP_STEP_OBLIGATION, ROADMAP_STEP_BEHAVIOR]
    draft["conclusion"] = {
        "text": "Bạn nên bắt đầu bằng việc giữ sẵn tiền cho khoản đến hạn 05/12.",
        "step_id": "giu_san_tra_sau",
        "personal": [],
    }
    # bản đã lưu chuyển tiền từ hũ Đi lại (không bước nào lấy từ hũ Giải trí)
    tools = scripted_tools(checks=("ok", "ok", "ok"), saves=(saved_from("giai_tri", "di_lai"),))
    result, _, _ = build(tools, draft, advise=True)
    assert result.outcome.ok and result.advice is not None
    assert [s.seen for s in result.advice.steps] == [
        ROADMAP_STEP_OBLIGATION["seen"],
        ROADMAP_STEP_BEHAVIOR["seen"],
    ]
    assert "Giải trí" not in " ".join(result.advice.texts())
    assert result.advice.conclusion is not None
    (logged,) = advisor_logs(caplog)
    assert logged["context"] == "roadmap" and logged["dropped_jar_mismatch"] == 1
    assert logged["block"] == "kept"


def saved_without_action(step_id: str) -> dict[str, Any]:
    """`save_roadmap.ok` với bước `step_id` không gắn hành động: hũ nhận chỉ còn ở `to_jar_code` của bước."""
    payload = fixture("save_roadmap.ok.json")
    for phase in payload["data"]["phases"]:
        for s in phase["steps"]:
            if s["step_id"] == step_id:
                s.pop("action", None)
    return payload


def test_lo_trinh_hu_nhan_chi_o_to_jar_code_van_tinh_la_hu_cua_ban_da_luu(caplog):
    caplog.set_level(logging.INFO, logger="yofina.agent.advisor")
    bu_an_uong = {
        "seen": "Hũ Ăn uống sắp cạn trước kỳ lương.",
        "why": "Thiếu tiền ăn thì khó giữ lộ trình.",
        "effect": "Giai đoạn đầu bù hũ Ăn uống.",
        "basis": ["tool:get_jar_balances"],
    }
    draft = outline(step(jar_code="di_lai"), review())
    draft["reasoning"] = [bu_an_uong, ROADMAP_STEP_OBLIGATION]
    draft["conclusion"] = {
        "text": "Bạn nên bắt đầu bằng bước bù hũ Ăn uống trước kỳ lương.",
        "step_id": "bu_an_uong",
        "personal": [],
    }
    # bước bu_an_uong của bản đã lưu (set_aside, giai_tri -> an_uong) không có hành động move_between_jars
    tools = scripted_tools(checks=("ok", "ok", "ok"), saves=(saved_without_action("bu_an_uong"),))
    result, _, _ = build(tools, draft, advise=True)
    assert result.outcome.ok and result.advice is not None
    assert [s.seen for s in result.advice.steps] == [
        bu_an_uong["seen"],
        ROADMAP_STEP_OBLIGATION["seen"],
    ]
    assert result.advice.conclusion is not None
    assert result.advice.conclusion.step_id == "bu_an_uong"
    (logged,) = advisor_logs(caplog)
    assert logged["dropped_jar_mismatch"] == 0 and logged["block"] == "kept"
