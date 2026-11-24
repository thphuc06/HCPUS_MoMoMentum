"""Phương án "dùng hũ khác" (switch_jar) nhất quán bằng mã (đi cảnh 24/11, what-if tai nghe 1,2 triệu Trả sau).

Lỗi gốc: nhãn và tóm tắt của phương án do Analyst viết tự do, còn trạng thái "Đủ" lấy từ `check_suitability` của `proposal`. Model ghi
nhãn "Mua bằng hũ Giải trí" và tóm tắt "Dùng 1.200.000 ₫ từ hũ Giải trí (còn 760.000 ₫ — không đủ); chuyển sang hũ Dự phòng thay thế"
cho đề xuất lấy tiền hũ khác, nên thẻ ghi "Đủ"/"Gợi ý" dưới một tiêu đề nói hũ không đủ.
"""

from __future__ import annotations

from typing import Any

from agent_helpers import (
    blocks_of,
    check_agui_order,
    make_llm,
    route_response,
    run_turn,
    tool_response,
)
from yofina_agent.schemas import AnalysisOption
from yofina_agent.whatif import enforce_switch_jar, jar_short_for_option

Q = "Nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao"
ROUTE = {
    "intent": "what_if",
    "amount_vnd": 1_200_000,
    "funding": "credit",
    "scenario_kind": "bnpl_purchase",
    "label": "tai nghe",
}
SCENARIO = {
    "scenario": {
        "kind": "bnpl_purchase",
        "amount_vnd": 1_200_000,
        "funding_source": "credit",
        "jar_code": None,
        "date": None,
        "label": "tai nghe",
    }
}
NARRATIVE = (
    "Nếu mua tai nghe bằng Trả sau, đến hạn 05/12 bạn cần 2.200.000 ₫. Dữ liệu ở mức tin cậy vừa."
)
BASE = {
    "is_essential": False,
    "category": "spending",
    "risk_level": "low",
    "origin": "recommendation",
}
MISLEADING = (
    "Dùng 1.200.000 ₫ từ hũ Giải trí (còn 760.000 ₫ — không đủ); chuyển sang hũ Dự phòng thay thế"
)
JARS = [
    {"code": "giai_tri", "name": "Giải trí", "balance_vnd": 760_000},
    {"code": "du_phong", "name": "Dự phòng", "balance_vnd": 2_700_000},
]


def _analysis(switch_jar: str, *, amount: int | None = None) -> dict[str, Any]:
    switch_proposal: dict[str, Any] = {
        "kind": "switch_jar",
        "funding_source": "jar",
        "jar_code": switch_jar,
        **BASE,
    }
    if amount is not None:
        switch_proposal["amount_vnd"] = amount
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
                "label": "Mua bằng hũ Giải trí",
                "summary": MISLEADING,
                "proposal": switch_proposal,
                "jar_code": "giai_tri",
                "recommended": True,
            },
        ],
        "follow_ups": [],
    }


def _options(events: list[Any]) -> dict[str, dict[str, Any]]:
    block = next(b for b in blocks_of(events) if b["type"] == "options")
    return {o["option_id"]: o for o in block["data"]["options"]}


def _run(monkeypatch, analysis: dict[str, Any]):
    llm = make_llm(
        [
            route_response(**ROUTE),
            tool_response("plan_scenario", SCENARIO),
            tool_response("analyze", analysis),
        ]
    )
    events, tools, _ = run_turn(Q, llm=llm, monkeypatch=monkeypatch)
    check_agui_order(events)
    return events, tools


def test_tieu_de_va_noi_dung_theo_hu_that_cua_de_xuat(monkeypatch):
    events, tools = _run(monkeypatch, _analysis("du_phong"))
    o = _options(events)["switch"]
    assert (
        o["label"] == "Mua bằng hũ Dự phòng"
    )  # không còn "Giải trí" cho đề xuất lấy tiền hũ Dự phòng
    assert (
        o["summary"]
        == "Trả 1.200.000 ₫ bằng tiền hũ Dự phòng; hũ đang có 2.700.000 ₫, đủ cho khoản này."
    )
    assert "Giải trí" not in o["label"] + o["summary"]
    assert o["status"] == "ok" and o["recommended"] is True
    # luật kiểm đúng hũ và đúng số tiền của khoản mua (model bỏ trống amount_vnd)
    checked = [
        a["proposal"]
        for n, a in tools.calls
        if n == "check_suitability" and a["proposal"]["kind"] == "switch_jar"
    ]
    assert checked == [
        {**checked[0], "jar_code": "du_phong", "amount_vnd": 1_200_000, "funding_source": "jar"}
    ]


def test_hu_khong_du_thi_khong_gan_du_va_khong_goi_y(monkeypatch):
    # check_suitability giả luôn trả đạt (như khi luật không bắt được): mã vẫn chặn "Đủ" theo số dư thật của hũ
    events, _ = _run(monkeypatch, _analysis("giai_tri"))
    o = _options(events)["switch"]
    assert o["label"] == "Mua bằng hũ Giải trí"
    assert o["summary"] == "Hũ Giải trí chỉ còn 760.000 ₫, không đủ trả 1.200.000 ₫."
    assert o["status"] == "short" and o.get("recommended") is None


def test_enforce_switch_jar_don_vi():
    raw = _analysis("du_phong")["options"][1]
    o = AnalysisOption.model_validate(raw)
    fixed = enforce_switch_jar(o, JARS, 1_200_000)
    assert (fixed.label, fixed.jar_code, fixed.proposal.jar_code, fixed.proposal.amount_vnd) == (
        "Mua bằng hũ Dự phòng",
        "du_phong",
        "du_phong",
        1_200_000,
    )
    assert not jar_short_for_option(fixed, JARS)
    # số tiền model đặt sẵn được giữ; hũ không đủ thì bỏ gợi ý
    short = enforce_switch_jar(
        AnalysisOption.model_validate(_analysis("giai_tri", amount=900_000)["options"][1]),
        JARS,
        1_200_000,
    )
    assert (
        short.proposal.amount_vnd == 900_000
        and short.recommended is None
        and jar_short_for_option(short, JARS)
    )
    # hũ không có trong danh sách: giữ nguyên, không đoán
    unknown = AnalysisOption.model_validate(
        {**raw, "proposal": {**raw["proposal"], "jar_code": "khac"}, "jar_code": None}
    )
    assert enforce_switch_jar(unknown, JARS, 1_200_000) is unknown
    # loại khác không bị đổi chữ
    defer = AnalysisOption.model_validate(_analysis("du_phong")["options"][0])
    assert enforce_switch_jar(defer, JARS, 1_200_000) is defer
