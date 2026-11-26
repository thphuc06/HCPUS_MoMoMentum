"""Bản lộ trình nói sai nguồn trả (issue #39, cảnh 4 và câu quỹ dự phòng sau deploy đợt 3): bước "Chuyển từ Dự phòng sang Nghĩa vụ trước
hạn" có lý do "Thuê bao đến hạn 23/11 …", trong khi khoản 23/11 (Tiền cơm văn phòng) trả từ hũ Ăn uống và hũ Nghĩa vụ đã đủ cho các khoản
của nó (1.450.000 ₫ cho 1.375.000 ₫ đến hạn trước kỳ lương).

Nguyên nhân: ngữ cảnh đưa cho model lập lộ trình chỉ có loại, số tiền, ngày của từng khoản nghĩa vụ, không có HŨ TRẢ, nên model gán mọi
khoản cho hũ Nghĩa vụ. Nay mỗi khoản kèm hũ trả (`pay_jar_code`, `pay_jar_name`), có thêm tình trạng đủ/thiếu của từng hũ trả trước kỳ
lương (`obligation_pay_jars`), và mã kiểm khi nhận bước: bước `pay_obligation` nạp một hũ không trả khoản nào, hoặc ở giai đoạn đầu nạp một
hũ trả đã đủ, thì vào vòng sửa sẵn có. Không gọi model (model giả theo kịch bản).
"""

from __future__ import annotations

from datetime import date

from agent_helpers import fixture, mcp_ok
from test_roadmap_agent import (
    args_for,
    build,
    outline,
    prompt,
    review,
    roadmap_events,
    scripted_tools,
    step,
)
from yofina_agent.compact import compact_obligations
from yofina_agent.roadmap_agent import StepOutline, _obligation_pay_jars, _obligation_step_issue
from yofina_agent.tools import classify_result

PAYDAY = date(2026, 12, 5)  # period_start của phương án fixture (optimize_allocation.ok)
JARS = [
    {"code": "an_uong", "name": "Ăn uống", "kind": "spending", "balance_vnd": 380_000},
    {"code": "nghia_vu", "name": "Nghĩa vụ", "kind": "obligation", "balance_vnd": 1_450_000},
    {"code": "du_phong", "name": "Dự phòng", "kind": "saving", "balance_vnd": 2_700_000},
    {"code": "giai_tri", "name": "Giải trí", "kind": "spending", "balance_vnd": 760_000},
]


def _ob(name, kind, amount, due, pay_jar=None, status="active"):
    row = {
        "id": "00000000-0000-4000-8000-000000000000", "kind": kind, "name": name, "amount_vnd": amount, "fee_vnd": 0,
        "due_date": due, "cycle": "monthly", "status": status, "is_essential": kind != "subscription", "source": "declared",
    }  # fmt: skip
    if pay_jar:
        row["pay_jar"] = pay_jar
    return row


#: nghĩa vụ của minh trên ví demo (Tổng quan 26/11): khoản 23/11 trả từ Ăn uống, các khoản còn lại từ Nghĩa vụ
MINH_OBLIGATIONS = [
    _ob("Tiền cơm văn phòng", "subscription", 300_000, "2026-11-23", "an_uong"),
    _ob("Tiền điện", "bill", 375_000, "2026-11-26", "nghia_vu"),
    _ob("Trả sau (mô phỏng)", "bnpl", 1_000_000, "2026-12-03", "nghia_vu"),
    _ob("Tiền thuê phòng", "rent", 2_000_000, "2026-12-06", "nghia_vu"),
]


def _payload(obligations):
    return {
        "status": "OK", "as_of": "2026-11-21T02:00:00Z", "app_date": "2026-11-21",
        "data": {"obligations": obligations, "total_due_vnd": sum(o["amount_vnd"] for o in obligations)},
    }  # fmt: skip


# --- dữ kiện có cấu trúc trong ngữ cảnh -----------------------------------------------------------------------------------------
def test_moi_khoan_nghia_vu_kem_hu_tra_theo_quy_tac_cua_du_bao():
    view = compact_obligations(_payload([*MINH_OBLIGATIONS, _ob("Internet", "bill", 220_000, "2026-12-12")]), jars=JARS)
    got = [(o["kind_label"], o.get("pay_jar_code"), o.get("pay_jar_name")) for o in view["obligations"]]
    assert got == [
        ("Thuê bao", "an_uong", "Ăn uống"),
        ("Hóa đơn", "nghia_vu", "Nghĩa vụ"),
        ("Trả sau", "nghia_vu", "Nghĩa vụ"),
        ("Tiền trọ", "nghia_vu", "Nghĩa vụ"),
        ("Hóa đơn", "nghia_vu", "Nghĩa vụ"),  # khoản chưa lưu hũ trả: hũ trả mặc định của ví
    ]
    # bản gọn của chat (không truyền hũ) giữ nguyên như trước: không có mã hũ để lọt ra câu trả lời
    assert all("pay_jar_code" not in o for o in compact_obligations(_payload(MINH_OBLIGATIONS))["obligations"])


def test_ban_gon_nghia_vu_cat_con_tam_khoan_thi_bao_con_bao_nhieu_khoan_bi_an():
    """Người có hơn 8 khoản (thuê bao, điện nước, khoản vay): bản gọn chỉ giữ 8 khoản đầu, nên model phải biết còn khoản chưa hiện (tổng
    phải trả vẫn tính đủ mọi khoản), không coi danh sách là đủ (T2 của báo cáo rà soát #39)."""
    many = [_ob(f"Khoản {i}", "bill", 100_000 + i, f"2026-12-{i + 1:02d}", "nghia_vu") for i in range(10)]
    view = compact_obligations(_payload(many), jars=JARS)
    assert len(view["obligations"]) == 8
    assert view["has_more"] is True and view["hidden_count"] == 2
    assert view["total_due_vnd"] == sum(o["amount_vnd"] for o in many)
    few = compact_obligations(_payload(MINH_OBLIGATIONS), jars=JARS)
    assert few["has_more"] is False and "hidden_count" not in few


def test_hu_tra_du_hay_thieu_truoc_ky_luong_theo_so_du_hien_co():
    rows = _obligation_pay_jars(_payload(MINH_OBLIGATIONS), JARS, PAYDAY)
    assert rows == [
        {"jar_code": "an_uong", "jar_name": "Ăn uống", "due_before_payday_text": "300.000 ₫", "status": "đủ"},
        # 375.000 + 1.000.000 = 1.375.000 trước ngày 05/12; tiền thuê 06/12 sau kỳ lương không tính
        {"jar_code": "nghia_vu", "jar_name": "Nghĩa vụ", "due_before_payday_text": "1.375.000 ₫", "status": "đủ"},
    ]
    short = [{**j, "balance_vnd": 1_000_000} if j["code"] == "nghia_vu" else j for j in JARS]
    paid = [*MINH_OBLIGATIONS, _ob("Đã trả", "bill", 9_000_000, "2026-11-25", "nghia_vu", status="paid")]
    (_, nghia_vu) = _obligation_pay_jars(_payload(paid), short, PAYDAY)
    assert nghia_vu["status"] == "thiếu" and nghia_vu["shortfall_text"] == "375.000 ₫"


# --- kiểm bước khi nhận ----------------------------------------------------------------------------------------------------------
def _context(jars=JARS, obligations=MINH_OBLIGATIONS):
    return {
        "jars": jars,
        **compact_obligations(_payload(obligations), jars=jars),
        "obligation_pay_jars": _obligation_pay_jars(_payload(obligations), jars, PAYDAY),
    }


def _pay(to_jar, source="du_phong"):
    return StepOutline.model_validate(
        step(kind="pay_obligation", jar_code=source, to_jar_code=to_jar, amount_ref={"jar_code": to_jar, "field": "proposed_increase"})
    )


def test_nap_hu_nghia_vu_da_du_o_giai_doan_dau_thi_vao_vong_sua():
    issue = _obligation_step_issue(_pay("nghia_vu"), _context(), immediate=True)
    assert issue is not None and "Nghĩa vụ" in issue and "đã đủ" in issue
    assert not any(ch.isdigit() for ch in issue)  # phản hồi sửa không mang số


def test_nap_hu_khong_tra_khoan_nao_thi_vao_vong_sua_o_moi_giai_doan():
    for immediate in (True, False):
        issue = _obligation_step_issue(_pay("giai_tri"), _context(), immediate=immediate)
        assert issue is not None and "Giải trí" in issue and "không trả khoản nghĩa vụ nào" in issue


def test_buoc_hop_le_khong_bi_chan():
    short = [{**j, "balance_vnd": 1_000_000} if j["code"] == "nghia_vu" else j for j in JARS]
    assert _obligation_step_issue(_pay("nghia_vu"), _context(jars=short), immediate=True) is None  # hũ trả đang thiếu
    assert _obligation_step_issue(_pay("nghia_vu"), _context(), immediate=False) is None  # sau kỳ lương: khoản hằng tháng
    plain = StepOutline.model_validate(step())  # set_aside không nói "vì nghĩa vụ"
    assert _obligation_step_issue(plain, _context(), immediate=True) is None
    no_window = {k: v for k, v in _context().items() if k != "obligation_pay_jars"}  # kỳ phân bổ bắt đầu hôm nay
    assert _obligation_step_issue(_pay("nghia_vu"), no_window, immediate=True) is None


# --- cả lượt lập: ngữ cảnh model thấy, vòng sửa, bản lưu -------------------------------------------------------------------------
def _minh_tools():
    balances = fixture("get_jar_balances.ok.json")
    for jar in balances["data"]["jars"]:
        jar["kind"] = next((j["kind"] for j in JARS if j["code"] == jar["code"]), "spending")
        if jar["code"] == "nghia_vu":
            jar["kind"], jar["balance_vnd"] = "obligation", 1_450_000
    return scripted_tools(
        checks=("ok",),
        get_jar_balances=lambda _a: classify_result("get_jar_balances", mcp_ok(balances)),
        get_obligations=lambda _a: classify_result("get_obligations", mcp_ok(_payload(MINH_OBLIGATIONS))),
    )


def test_lap_lo_trinh_buoc_nap_nghia_vu_vi_khoan_cua_hu_khac_vao_vong_sua_roi_bi_bo(caplog):
    caplog.set_level("WARNING", logger="yofina.agent.roadmap")
    tools = _minh_tools()
    wrong = step(
        "bo_sung_nghia_vu", kind="pay_obligation", jar_code="an_uong", to_jar_code="nghia_vu", action=None,
        title="Chuyển từ Ăn uống sang Nghĩa vụ trước hạn", reason="Nghĩa vụ cần thêm tiền trước hạn",
        amount_ref={"jar_code": "nghia_vu", "field": "proposed_increase"},
    )  # fmt: skip
    result, client, scope = build(tools, outline(wrong, review()), outline(review()))
    assert result.outcome.ok and scope.calls == 2
    context = prompt(client, 0)["context"]
    assert {o["pay_jar_code"] for o in context["obligations"]} == {"an_uong", "nghia_vu"}
    assert {p["jar_code"]: p["status"] for p in context["obligation_pay_jars"]} == {"an_uong": "đủ", "nghia_vu": "đủ"}
    (feedback,) = prompt(client, 1)["feedback"]
    assert feedback["step_id"] == "bo_sung_nghia_vu" and feedback["rule_id"] == "obligation_pay_jar"
    (stored,) = args_for(tools, "save_roadmap")
    assert [s["kind"] for p in stored["phases"] for s in p["steps"]] == ["review_goal"]
    # bước sai không tốn lượt check_suitability
    assert all(a["proposal"].get("to_jar_code") != "nghia_vu" for a in args_for(tools, "check_suitability"))
    (event,) = roadmap_events(caplog, "roadmap_step_rejected")
    assert event["rule_id"] == "obligation_pay_jar"
