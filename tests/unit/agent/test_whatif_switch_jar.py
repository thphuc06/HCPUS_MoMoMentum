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
from yofina_agent.whatif import (
    enforce_pay_now,
    enforce_switch_jar,
    jar_short_for_option,
    unique_option_ids,
)

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
    o = _options(events)["switch_du_phong"]  # id theo hũ thật, không theo chữ model đặt
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
    o = _options(events)["switch_giai_tri"]
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
    # đã biết giá món thì số model tự điền bị bỏ (trả cả khoản bằng hũ đó); hũ không đủ thì bỏ gợi ý
    short = enforce_switch_jar(
        AnalysisOption.model_validate(_analysis("giai_tri", amount=900_000)["options"][1]),
        JARS,
        1_200_000,
    )
    assert (
        short.proposal.amount_vnd == 1_200_000
        and short.recommended is None
        and jar_short_for_option(short, JARS)
    )
    # kịch bản không có giá món: dùng số của model
    no_price = enforce_switch_jar(
        AnalysisOption.model_validate(_analysis("giai_tri", amount=500_000)["options"][1]),
        JARS,
        None,
    )
    assert no_price.proposal.amount_vnd == 500_000 and not jar_short_for_option(no_price, JARS)
    # hũ không có trong danh sách: giữ nguyên, không đoán
    unknown = AnalysisOption.model_validate(
        {**raw, "proposal": {**raw["proposal"], "jar_code": "khac"}, "jar_code": None}
    )
    assert enforce_switch_jar(unknown, JARS, 1_200_000) is unknown
    # loại khác không bị đổi chữ
    defer = AnalysisOption.model_validate(_analysis("du_phong")["options"][0])
    assert enforce_switch_jar(defer, JARS, 1_200_000) is defer


def test_model_dien_so_tien_bang_so_du_hu_van_khong_gan_du(monkeypatch):
    """Ca thật (kiểm lại Runtime v22, `minh`): model gọi check_suitability với switch_jar, amount_vnd 760.000 ₫ đúng bằng số dư hũ Giải
    trí, cho tai nghe 1.200.000 ₫. Mã cũ giữ số của model nên hiện "Đủ" và "Trả 760.000 ₫ … đủ cho khoản này"."""
    analysis = _analysis("giai_tri", amount=760_000)
    analysis["options"][1]["summary"] = (
        "Trả 760.000 ₫ bằng tiền hũ Giải trí; hũ đang có 760.000 ₫, đủ cho khoản này."
    )
    events, tools = _run(monkeypatch, analysis)
    o = _options(events)["switch_giai_tri"]
    assert o["status"] == "short" and o.get("recommended") is None
    assert o["summary"] == "Hũ Giải trí chỉ còn 760.000 ₫, không đủ trả 1.200.000 ₫."
    assert "đủ cho khoản này" not in o["summary"]
    checked = [
        a["proposal"]
        for n, a in tools.calls
        if n == "check_suitability" and a["proposal"]["kind"] == "switch_jar"
    ]
    assert [p["amount_vnd"] for p in checked] == [
        1_200_000
    ]  # luật kiểm giá món, không kiểm số dư với chính nó


def _pay_now(amount: int | None, *, jar: str = "giai_tri", funding: str = "jar") -> AnalysisOption:
    proposal: dict[str, Any] = {
        "kind": "pay_now",
        "funding_source": funding,
        "jar_code": jar,
        **BASE,
    }
    if amount is not None:
        proposal["amount_vnd"] = amount
    return AnalysisOption.model_validate(
        {
            "option_id": "pay_now",
            "kind": "pay_now",
            "label": "Trả ngay bằng hũ Giải trí",
            "summary": "Trả 760.000 ₫ ngay, hũ Giải trí đủ.",
            "proposal": proposal,
            "jar_code": jar,
            "recommended": True,
        }
    )


def test_pay_now_khong_lay_it_hon_gia_mon():
    fixed = enforce_pay_now(_pay_now(760_000), JARS, 1_200_000)
    assert fixed.proposal.amount_vnd == 1_200_000 and fixed.proposal.funding_source == "jar"
    assert jar_short_for_option(fixed, JARS) and fixed.recommended is None
    assert fixed.summary == "Hũ Giải trí chỉ còn 760.000 ₫, không đủ trả 1.200.000 ₫."
    assert fixed.label == "Trả ngay bằng hũ Giải trí"  # nhãn của model giữ nguyên
    # model bỏ trống số tiền: cũng lấy giá món
    assert enforce_pay_now(_pay_now(None), JARS, 1_200_000).proposal.amount_vnd == 1_200_000
    # hũ đủ và số đã nâng: tóm tắt nêu đúng số
    ok = enforce_pay_now(_pay_now(760_000, jar="du_phong"), JARS, 1_200_000)
    assert (
        ok.summary
        == "Trả 1.200.000 ₫ bằng tiền hũ Dự phòng; hũ đang có 2.700.000 ₫, đủ cho khoản này."
    )
    assert not jar_short_for_option(ok, JARS) and ok.recommended is True


def test_pay_now_giu_nguyen_khi_khong_can_sua():
    # số của model đã lớn hơn giá món (trả trước nhiều kỳ) và hũ đủ: không đổi gì
    big = _pay_now(2_400_000, jar="du_phong")
    assert enforce_pay_now(big, JARS, 1_200_000) is big
    # không biết giá món, nguồn tín dụng, loại khác: không đụng
    o = _pay_now(760_000)
    assert enforce_pay_now(o, JARS, None) is o
    credit = _pay_now(760_000, funding="credit")
    assert enforce_pay_now(credit, JARS, 1_200_000) is credit
    defer = AnalysisOption.model_validate(_analysis("du_phong")["options"][0])
    assert enforce_pay_now(defer, JARS, 1_200_000) is defer

def test_option_id_cua_dung_hu_khac_dung_theo_hu_that_va_duy_nhat():
    """Kiểm lại Runtime v23: phương án "Mua bằng hũ Dự phòng" mang `option_id` `pay_giai_tri` (id model đặt theo hũ khác). Id nay dựng
    từ hũ thật của đề xuất; hai phương án cùng hũ vẫn có id khác nhau."""
    raw = _analysis("du_phong")["options"][1]
    raw = {**raw, "option_id": "pay_giai_tri"}
    fixed = enforce_switch_jar(AnalysisOption.model_validate(raw), JARS, 1_200_000)
    assert fixed.option_id == "switch_du_phong" and fixed.label == "Mua bằng hũ Dự phòng"
    twin = enforce_switch_jar(AnalysisOption.model_validate({**raw, "option_id": "khac"}), JARS, 1_200_000)
    defer = AnalysisOption.model_validate(_analysis("du_phong")["options"][0])
    ids = [o.option_id for o in unique_option_ids([defer, fixed, twin])]
    assert ids == ["defer", "switch_du_phong", "switch_du_phong_2"]
    assert all(len(i) <= 32 for i in ids)
