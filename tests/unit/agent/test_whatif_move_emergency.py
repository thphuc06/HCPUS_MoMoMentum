"""Phương án what-if "chuyển bù từ quỹ dự phòng" đi qua luật giữ quỹ dự phòng cho việc gấp theo dữ kiện có cấu trúc (#39, lỗi 5).

Ca thật (Runtime v32, d2): "Chuyển bù từ hũ Dự phòng sang Giải trí" hiện kèm cảnh báo và không được gợi ý: luật
`emergency_not_for_discretionary` ở mức warn theo thiết kế (`rules/emergency_not_for_discretionary.yaml`: người dùng vẫn tự chọn được),
nên giữ. Nhưng luật chỉ áp khi đề xuất là chi tiêu không thiết yếu, và với phương án chuyển bù thì phân loại đó do model tự điền: model
bỏ trống hoặc ghi "saving" thì luật bị bỏ qua và phương án lấy quỹ dự phòng sang hũ chi không thiết yếu không có cảnh báo nào. Như bước
lộ trình (`roadmap_agent._buffer_issue`), hũ nhận là hũ chi tiêu thì tiền chuyển vào là để chi: mã đặt phân loại, không theo chữ.
Router, planner và Analyst giả; `check_suitability` chấm bằng bộ luật thật của repo.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from agent_helpers import (
    FakeTools,
    check_agui_order,
    fixture,
    make_llm,
    mcp_ok,
    route_response,
    run_turn,
    tool_response,
)
from test_whatif_emergency import options_of, real_suitability
from test_whatif_switch_jar import NARRATIVE, ROUTE, SCENARIO, Q
from yofina_agent.tools import classify_result
from yofina_agent.whatif import EMERGENCY_FUND_NOTE, inherit_purchase_class

from yofina_agent.schemas import AnalysisOption

#: loại hũ như hồ sơ `minh` (số dư từ fixture): Dự phòng là hũ tiết kiệm không mục tiêu, Giải trí là hũ chi tiêu
KINDS = {"du_lich": "saving", "du_phong": "saving", "nghia_vu": "obligation"}


def jars_with_kinds() -> dict[str, Any]:
    payload = copy.deepcopy(fixture("get_jar_balances.ok.json"))
    for row in payload["data"]["jars"]:
        row["kind"] = KINDS.get(row["code"], "spending")
        if row["code"] == "du_lich":
            row["goal_vnd"] = 6_000_000
    return payload


def move_option(proposal_extra: dict[str, Any], *, to_jar: str = "giai_tri") -> dict[str, Any]:
    return {
        "option_id": "cover",
        "kind": "move_between_jars",
        "label": "Chuyển bù từ hũ Dự phòng",
        "summary": "Chuyển bù từ hũ Dự phòng để trả ngay, không dùng Trả sau.",
        "proposal": {"kind": "move_between_jars", "funding_source": "jar", "jar_code": "du_phong", **proposal_extra},
        "action": {"tool": "move_between_jars", "params": {"from_jar": "du_phong", "to_jar": to_jar, "amount_vnd": 1_200_000}},
        "recommended": True,
    }


def analysis(option: dict[str, Any]) -> dict[str, Any]:
    return {
        "narrative": NARRATIVE,
        "options": [
            {
                "option_id": "defer",
                "kind": "defer",
                "label": "Hoãn mua sau kỳ lương",
                "summary": "Hoãn tới sau 05/12 rồi xem lại.",
                "proposal": {"kind": "defer", "funding_source": "jar", "risk_level": "low"},
            },
            option,
        ],
        "follow_ups": [],
    }


def run(monkeypatch: Any, a: dict[str, Any]) -> tuple[list[Any], FakeTools]:
    tools = FakeTools(
        {
            "check_suitability": real_suitability,
            "get_jar_balances": lambda _a: classify_result("get_jar_balances", mcp_ok(jars_with_kinds())),
        }
    )
    llm = make_llm([route_response(**ROUTE), tool_response("plan_scenario", SCENARIO), tool_response("analyze", a)])
    events, tools, _ = run_turn(Q, llm=llm, tools=tools, monkeypatch=monkeypatch)
    check_agui_order(events)
    return events, tools


def move_proposals(tools: FakeTools) -> list[dict[str, Any]]:
    return [a["proposal"] for n, a in tools.calls if n == "check_suitability" and a["proposal"]["kind"] == "move_between_jars"]


@pytest.mark.parametrize(
    "said",
    [
        {},  # model bỏ trống phân loại
        {"category": "saving", "risk_level": "low"},  # model gọi việc chuyển bù là "để dành"
    ],
)
def test_chuyen_bu_quy_du_phong_sang_hu_chi_tieu_luon_qua_luat_giu_quy_du_phong(monkeypatch, said):
    events, tools = run(monkeypatch, analysis(move_option(said)))
    (sent,) = move_proposals(tools)
    assert (sent["category"], sent["is_essential"], sent["jar_code"]) == ("spending", False, "du_phong")
    o = options_of(events)["cover"]
    assert o.get("recommended") is None and o["status"] == "tight"  # warn: vẫn đưa để người dùng tự chọn, không gợi ý
    assert o["summary"].endswith(EMERGENCY_FUND_NOTE.format(name="Dự phòng"))


def test_nguoi_dung_noi_thiet_yeu_thi_giu_nhu_model_noi(monkeypatch):
    # khoản thiết yếu (thuốc, tiền trọ) không thuộc luật này: model nói is_essential true theo lời người dùng thì giữ
    events, tools = run(monkeypatch, analysis(move_option({"is_essential": True, "category": "spending", "risk_level": "low"})))
    (sent,) = move_proposals(tools)
    assert sent["is_essential"] is True
    assert "quỹ dự phòng" not in options_of(events)["cover"]["summary"]


def _option(proposal: dict[str, Any], to_jar: str) -> AnalysisOption:
    raw = move_option({}, to_jar=to_jar)
    raw["proposal"] = {"kind": "move_between_jars", "funding_source": "jar", "jar_code": "du_phong", "amount_vnd": 1_200_000, **proposal}
    return AnalysisOption.model_validate(raw)


def test_inherit_purchase_class_cho_chuyen_bu_theo_loai_hu_nhan():
    rows = jars_with_kinds()["data"]["jars"]
    # hũ nhận là hũ chi tiêu: tiền chuyển vào là để chi (mã đặt category, kể cả khi model nói khác)
    p = inherit_purchase_class(_option({"category": "saving"}, "giai_tri"), rows).proposal
    assert (p.category, p.is_essential) == ("spending", False)
    # hũ nhận là hũ nghĩa vụ hay hũ tiết kiệm: không phải chi tiêu, giữ phân loại model nói
    for target in ("nghia_vu", "du_lich"):
        said = _option({"category": "debt_payment", "is_essential": True}, target)
        assert inherit_purchase_class(said, rows) is said
    # không biết loại hũ nhận (số dư không mang loại hũ): như phương án trả bằng tiền hũ, chỉ điền chỗ model bỏ trống
    bare = inherit_purchase_class(_option({}, "giai_tri"), [{"code": "giai_tri", "name": "Giải trí"}]).proposal
    assert (bare.category, bare.is_essential) == ("spending", False)
