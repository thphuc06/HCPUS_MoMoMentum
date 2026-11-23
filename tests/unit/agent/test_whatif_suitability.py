"""Ca golden `whatif-bnpl2` ("Nếu mua điện thoại 3 triệu bằng Trả sau thì sao", tài khoản `minh`): Verifier hỏng 2 vòng, thiếu `options`.

Tái hiện bằng đúng các đề xuất mà Analyst gửi `check_suitability` trong lần chạy golden phase 3 trên Runtime v15 (23/11, khoảng 15:05 UTC,
`evals/results/phase3-golden.jsonl`), còn `check_suitability` giả gọi THẬT bộ luật `yofina_planner.engine.evaluate` với số dư hũ của `minh`.
Nguyên nhân: luật thứ sáu `source_jar_covers` (hũ nguồn đủ tiền) chặn
- phương án không chi tiền ngay (bỏ qua, hoãn, nhắc xem lại) mà model chép số tiền món hàng 3.000.000 ₫ vào `proposal.amount_vnd`;
- phương án chuyển bù mà model đặt `proposal.jar_code` là hũ ĐÍCH Nghĩa vụ (1.000.000 ₫) thay cho hũ nguồn của hành động.
Mỗi vòng chỉ còn phương án "bỏ qua" qua luật nên vòng nào cũng retry rồi fallback.
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
from test_whatif import ROUTE_WHAT_IF, block_types, call_names, result_of, text_of
from yofina_agent.schemas import AnalysisOption
from yofina_agent.tools import classify_result
from yofina_agent.whatif import analyst_prompt, normalize_proposal

from yofina_core.suitability import Proposal
from yofina_planner.engine import evaluate
from yofina_planner.facts import JarFact, ObligationFact, SuitabilityFacts
from yofina_planner.rules import load_rules

QUESTION = "Nếu mua điện thoại 3 triệu bằng Trả sau thì sao"
ROUTE = {**ROUTE_WHAT_IF, "amount_vnd": 3_000_000, "label": "điện thoại"}
SCENARIO = {"scenario": {"kind": "bnpl_purchase", "amount_vnd": 3_000_000, "funding_source": "credit", "label": "điện thoại"}}
RULES = load_rules()


def minh_facts() -> SuitabilityFacts:
    """Số dư hũ của `minh` như `get_jar_balances` trả trong lần chạy golden (cùng fixture `get_jar_balances.ok.json`)."""
    jars = {j["code"]: j for j in fixture("get_jar_balances.ok.json")["data"]["jars"]}
    kinds = {"du_lich": "saving", "du_phong": "saving", "nghia_vu": "obligation"}
    return SuitabilityFacts(
        today=date(2026, 11, 21),
        next_payday=date(2026, 12, 5),
        monthly_income_vnd=9_000_000,
        risk_tolerance="medium",
        jars=tuple(JarFact(c, j["name"], kinds.get(c, "spending"), j["balance_vnd"]) for c, j in jars.items()),
        obligations=(
            ObligationFact("bill", "Tiền điện", 375_000, date(2026, 11, 26), "monthly", 26, "hoa_don", True),
            ObligationFact("bnpl", "Trả sau (mô phỏng)", 1_000_000, date(2026, 12, 5), "once", None, "nghia_vu", False),
            ObligationFact("rent", "Tiền thuê phòng", 2_000_000, date(2026, 12, 6), "monthly", 6, "nghia_vu", True),
        ),
        window_days=30,
    )


def real_suitability(calls: list[dict[str, Any]]) -> Any:
    """`planner___check_suitability` giả nhưng chấm bằng bộ luật thật (YAML của repo), kể cả nghĩa vụ của kịch bản khi có `scenario_id`."""

    def handler(args: dict[str, Any]) -> Any:
        calls.append(args)
        added = 3_000_000 if args.get("scenario_id") else None
        v = evaluate(Proposal.model_validate(args["proposal"], strict=False), minh_facts(), RULES, added_obligation_vnd=added)
        payload = {"status": "OK", "as_of": "2026-11-23T15:05:48Z", "app_date": "2026-11-21", "data": v.model_dump(mode="json", exclude_none=True)}
        return classify_result("x", mcp_ok(payload))

    return handler


def scenario_3m() -> dict[str, Any]:
    """`run_scenario` của ca golden (3.000.000 ₫ Trả sau): cùng số với kết quả Runtime (tổng đến hạn 4.000.000 ₫, hụt 2.550.000 ₫)."""
    p = copy.deepcopy(fixture("run_scenario.ok_bnpl.json"))
    d = p["data"]
    d["spec"].update(amount_vnd=3_000_000, label="điện thoại")
    d["effects"][0]["min_balance_delta_vnd"] = -3_000_000
    oi = d["obligation_impact"]
    oi["headline"] = "Hụt: Trả sau (mô phỏng), món này tốn 3.000.000 ₫, ngày 05/12 phải trả tổng 4.000.000 ₫; hũ Nghĩa vụ hụt 2.550.000 ₫."
    oi["cost"].update(principal_vnd=3_000_000, item_cost_vnd=3_000_000, total_due_vnd=4_000_000, available_after_vnd=1_033_000)
    oi["at_due"][0].update(balance_before_due_vnd=1_450_000, due_vnd=4_000_000, shortfall_vnd=2_550_000)
    oi["shortfall_vnd"] = 2_550_000
    return p


NARRATIVE = (
    "Nếu mua điện thoại 3.000.000 ₫ bằng Trả sau, ngày 05/12 phải trả tổng 4.000.000 ₫ nên hũ Nghĩa vụ hụt 2.550.000 ₫. "
    "Dữ liệu ở mức tin cậy vừa."
)
BASE = {"is_essential": False, "category": "spending", "risk_level": "low", "origin": "recommendation"}


def opt(option_id: str, kind: str, label: str, summary: str, proposal: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"option_id": option_id, "kind": kind, "label": label, "summary": summary, "proposal": {"kind": kind, **proposal, **BASE}, **extra}


#: vòng 1 trong log: bỏ qua (hũ Nghĩa vụ), chuyển bù 2.550.000 ₫ (jar_code Nghĩa vụ), nhắc lại 3.000.000 ₫ (hũ Giải trí)
ROUND_1 = {
    "narrative": NARRATIVE,
    "options": [
        opt("skip", "skip", "Không mua lúc này", "Giữ hũ Nghĩa vụ không bị hụt.", {"funding_source": "jar", "jar_code": "nghia_vu"}),
        opt(
            "cover", "move_between_jars", "Chuyển bù từ hũ Dự phòng", "Chuyển 2.550.000 ₫ sang hũ Nghĩa vụ trước 05/12.",
            {"amount_vnd": 2_550_000, "funding_source": "jar", "jar_code": "nghia_vu"},
            action={"tool": "move_between_jars", "params": {"from_jar": "du_phong", "to_jar": "nghia_vu", "amount_vnd": 2_550_000}},
            recommended=True,
        ),
        opt("remind", "remind_later", "Nhắc xem lại sau kỳ lương", "Cân nhắc lại sau kỳ lương.", {"amount_vnd": 3_000_000, "funding_source": "jar", "jar_code": "giai_tri"}),
    ],
    "follow_ups": [],
}  # fmt: skip
#: vòng 2 trong log: bỏ qua, hoãn 3.000.000 ₫ (hũ Nghĩa vụ), giảm số tiền 3.000.000 ₫ (hũ Giải trí)
ROUND_2 = {
    "narrative": NARRATIVE,
    "options": [
        opt("skip", "skip", "Không mua lúc này", "Giữ hũ Nghĩa vụ không bị hụt.", {"funding_source": "jar", "jar_code": "nghia_vu"}),
        opt("defer", "defer", "Hoãn tới sau kỳ lương", "Hoãn mua để hũ Nghĩa vụ đủ trả 05/12.", {"amount_vnd": 3_000_000, "funding_source": "jar", "jar_code": "nghia_vu"}),
        opt("reduce", "reduce_amount", "Chọn máy rẻ hơn", "Giảm số tiền mua.", {"amount_vnd": 3_000_000, "funding_source": "jar", "jar_code": "giai_tri"}),
    ],
    "follow_ups": [],
}  # fmt: skip


def run_case(monkeypatch: Any, *analyses: dict[str, Any]) -> tuple[list[Any], FakeTools, list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []
    tools = FakeTools(
        {
            "check_suitability": real_suitability(calls),
            "run_scenario": lambda a: classify_result("x", mcp_ok(scenario_3m())),
        }
    )
    llm = make_llm([route_response(**ROUTE), tool_response("plan_scenario", SCENARIO), *(tool_response("analyze", a) for a in analyses)])
    events, tools, _ = run_turn(QUESTION, llm=llm, tools=tools, monkeypatch=monkeypatch)
    check_agui_order(events)
    return events, tools, calls


def test_de_xuat_trong_log_bi_luat_hu_nguon_chan_khi_gui_nguyen_van():
    """Dẫn chứng nguyên nhân: đúng các đề xuất trong log, chấm bằng luật thật, chỉ "bỏ qua" qua ở cả hai vòng."""
    for rnd in (ROUND_1, ROUND_2):
        blocked = {}
        for o in rnd["options"]:
            v = evaluate(Proposal.model_validate(o["proposal"], strict=False), minh_facts(), RULES)
            blocked[o["option_id"]] = [x.rule_id for x in v.violations if x.severity == "block"]
        assert blocked["skip"] == []
        assert all(rules == ["source_jar_covers"] for k, rules in blocked.items() if k != "skip"), blocked


def test_analyst_thay_so_du_hu_de_chon_hu_du_tien():
    rows = fixture("get_jar_balances.ok.json")["data"]["jars"]
    p = analyst_prompt(QUESTION, {}, rows, date(2026, 11, 21))
    assert '"code": "giai_tri", "name": "Giải trí", "balance_text": "760.000 ₫"' in p


def test_chuan_hoa_de_xuat_chi_sua_dieu_model_mo_ta_sai_khong_bo_kiem_khoan_chi_that():
    def norm(o: dict[str, Any]) -> dict[str, Any]:
        return normalize_proposal(AnalysisOption.model_validate(o)).model_dump(exclude_none=True)

    remind = ROUND_1["options"][2]
    assert "amount_vnd" not in norm(remind) and norm(remind)["jar_code"] == "giai_tri"
    # hoãn nhưng nguồn tín dụng vẫn là vay: giữ số tiền để luật kiểm nghĩa vụ
    credit_defer = opt("d", "defer", "Hoãn", "Hoãn.", {"amount_vnd": 3_000_000, "funding_source": "credit"})
    assert norm(credit_defer)["amount_vnd"] == 3_000_000
    # chuyển bù có hành động: hũ nguồn và số chuyển của hành động; không có hành động thì giữ như model
    cover = norm(ROUND_1["options"][1])
    assert (cover["jar_code"], cover["amount_vnd"], cover["funding_source"]) == ("du_phong", 2_550_000, "jar")
    no_action = copy.deepcopy(ROUND_1["options"][1])
    no_action.pop("action")
    assert norm(no_action)["jar_code"] == "nghia_vu"
    # chi tiền thật: giữ nguyên số và hũ
    assert norm(ROUND_2["options"][2])["amount_vnd"] == 3_000_000
    # origin luôn do mã đặt
    assert norm({**remind, "proposal": {**remind["proposal"], "origin": "user_request"}})["origin"] == "recommendation"


def test_whatif_bnpl2_vong_dau_qua_verifier_khi_de_xuat_mo_ta_dung_viec_phuong_an_lam(monkeypatch):
    events, _, calls = run_case(monkeypatch, ROUND_1, ROUND_2)
    assert block_types(events) == ["forecast_timeline", "obligation_impact", "options", "confirm"]
    r = result_of(events)
    assert r["verifier_rounds"] == 1 and r["degraded"] is False and r["model_calls"] == 3
    by_kind = {c["proposal"]["kind"]: c["proposal"] for c in calls}
    # chuyển bù: luật kiểm hũ NGUỒN của hành động với đúng số chuyển
    assert by_kind["move_between_jars"]["jar_code"] == "du_phong" and by_kind["move_between_jars"]["amount_vnd"] == 2_550_000
    # nhắc xem lại không chi tiền ngay: không gửi số tiền món hàng
    assert "amount_vnd" not in by_kind["remind_later"]
    opts = blocks_of(events)[2]["data"]["options"]
    assert {o["option_id"] for o in opts} == {"skip", "cover", "remind"} and all(o["status"] != "short" for o in opts)
    assert "source_jar_covers" in next(o for o in opts if o["option_id"] == "cover")["checked_rules"]
    assert text_of(events).startswith("Nếu mua điện thoại")


def test_phuong_an_chi_tien_tu_hu_khong_du_van_bi_chan(monkeypatch):
    """Không nới luật: giảm số tiền, trả ngay bằng hũ Giải trí 760.000 ₫ cho 3.000.000 ₫ vẫn bị `source_jar_covers` chặn; chuyển bù
    từ hũ không đủ tiền cũng bị chặn (kiểm đúng hũ nguồn)."""
    bad = {
        "narrative": NARRATIVE,
        "options": [
            opt("reduce", "reduce_amount", "Chọn máy rẻ hơn", "Giảm số tiền mua.", {"amount_vnd": 3_000_000, "funding_source": "jar", "jar_code": "giai_tri"}),
            opt("pay", "pay_now", "Trả ngay bằng hũ Giải trí", "Trả bằng tiền hũ.", {"amount_vnd": 3_000_000, "funding_source": "jar", "jar_code": "giai_tri"}),
            opt(
                "cover", "move_between_jars", "Chuyển bù từ hũ Giải trí", "Chuyển 2.550.000 ₫ sang hũ Nghĩa vụ.",
                {"amount_vnd": 2_550_000, "funding_source": "jar", "jar_code": "nghia_vu"},
                action={"tool": "move_between_jars", "params": {"from_jar": "giai_tri", "to_jar": "nghia_vu", "amount_vnd": 2_550_000}},
            ),
        ],
        "follow_ups": [],
    }  # fmt: skip
    events, tools, calls = run_case(monkeypatch, bad, bad)
    blocks = blocks_of(events)
    opts = next(b for b in blocks if b["type"] == "options")["data"]["options"]
    # đường suy giảm: không phương án nào của model qua luật nên chỉ còn phương án dựng bằng mã (bỏ qua, hoãn), đã qua luật thật
    assert [o["kind"] for o in opts] == ["skip", "defer"] and all(o["status"] != "short" for o in opts)
    assert "move_between_jars" not in call_names(tools)
    model_props = [c["proposal"] for c in calls if c["proposal"]["kind"] in ("reduce_amount", "pay_now", "move_between_jars")]
    assert {p["jar_code"] for p in model_props} == {"giai_tri"}
    assert block_types(events)[-1] == "notice" and blocks[-1]["data"]["degraded_reason"] == "verifier_failed"
    assert text_of(events) == ""


def test_verifier_van_hong_thi_luot_van_co_options_tu_phuong_an_da_kiem(monkeypatch):
    """Vòng 1 của log nhưng chuyển bù không có hành động (không biết hũ nguồn): vẫn bị chặn; vòng 2 có giảm số tiền bị chặn. Hết vòng thì
    phát `options` gồm phương án TỰ qua luật và có căn cứ của các vòng (bỏ qua, hoãn, nhắc lại), không phát lời giải thích."""
    r1 = copy.deepcopy(ROUND_1)
    r1["options"][1].pop("action")
    r1["options"][1]["summary"] = "Chuyển bù phần hụt sang hũ Nghĩa vụ."
    events, _, _ = run_case(monkeypatch, r1, ROUND_2)
    assert block_types(events) == ["forecast_timeline", "obligation_impact", "options", "notice"]
    opts = blocks_of(events)[2]["data"]["options"]
    assert [o["option_id"] for o in opts] == ["skip", "defer", "remind"]
    assert all(o["status"] != "short" for o in opts)
    n = blocks_of(events)[-1]["data"]
    assert n["kind"] == "degraded" and n["degraded_reason"] == "verifier_failed"
    assert text_of(events) == ""
    r = result_of(events)
    assert r["verifier_rounds"] == 2 and r["model_calls"] == 4
