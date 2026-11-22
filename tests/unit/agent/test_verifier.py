"""Verifier (L4): NumericGrounding nhiều dạng số tiếng Việt, phán quyết, bản ghi lượt, hỏi lại."""

from __future__ import annotations

import pytest
from yofina_agent.clarify import missing_slot, resolve_clarify
from yofina_agent.schemas import IntentParams, IntentResult, OptionSuitability
from yofina_agent.trace import build_record, confidence, data_used, merge_rules, step_timings
from yofina_agent.tools import ToolKind, ToolOutcome
from yofina_agent.verifier import Allowed, NumericGrounding, assemble_verdict, suitability_status

from yofina_core.suitability import SuitabilityVerdict

PAYLOAD = {
    "status": "OK",
    "data": {
        "total_due_vnd": 2_200_000,
        "item_cost_vnd": 1_200_000,
        "shortfall_vnd": 1_150_000,
        "balance_vnd": 1_050_000,
        "p_shortfall_after": 0.97,
        "ratio": 0.5778,
        "headline": "Đến hạn 05/12 bạn cần 2.200.000 ₫; hũ Nghĩa vụ hụt 1.150.000 ₫.",
        "days": 14,
    },
}


def check(text: str, *, user: str = "") -> tuple[bool, list[str]]:
    allowed = Allowed.from_payloads([PAYLOAD], [user])
    res = NumericGrounding.check({"narrative": text}, allowed)
    return res.ok, [g.text for g in res.ungrounded]


@pytest.mark.parametrize(
    "text",
    [
        "Bạn cần 2.200.000 ₫ vào ngày 05/12.",  # định dạng đầy đủ
        "Bạn cần 2,2 triệu vào ngày đến hạn.",  # làm tròn kiểu "2,2 triệu"
        "Bạn cần 2.2 triệu.",
        "Bạn cần 2tr2 vào ngày đến hạn.",  # viết liền
        "Hụt khoảng 1,15 triệu đồng.",
        "Hụt khoảng 1.150k.",
        "Hụt 1150 nghìn.",
        "Món này 1,2 triệu.",
        "Món này 1.200.000đ.",
        "Món này 1200000 VND.",
        "Khả năng hụt khoảng 97%.",  # phần trăm từ số thực 0,97
        "Nghĩa vụ chiếm khoảng 58% thu nhập.",  # 0,5778 làm tròn
        "Còn 1,05 triệu trong hũ.",
        "Chỉ còn 14 ngày nữa.",  # số đếm nhỏ không phải số tiền
        "Chừng 1 triệu rưỡi",  # không có số tiền nào khớp ở đây xem test riêng bên dưới
    ][:-1],
)
def test_so_co_can_cu_trong_tool_thi_qua(text):
    ok, bad = check(text)
    assert ok, bad


@pytest.mark.parametrize(
    ("text", "bad_value"),
    [
        ("Bạn cần 2.350.000 ₫ vào ngày 05/12.", "2.350.000 ₫"),
        ("Hụt khoảng 1,3 triệu.", "1.300.000 ₫"),
        ("Hụt 1tr3.", "1.300.000 ₫"),
        ("Tổng 3.400.000 ₫ gồm hai khoản.", "3.400.000 ₫"),  # tổng tự cộng: không có trong tool
        ("Hụt tới 500k.", "500.000 ₫"),
        ("Khả năng hụt 45%.", "45%"),
        ("Nghĩa vụ chiếm 70% thu nhập.", "70%"),
    ],
)
def test_so_khong_co_can_cu_thi_bi_bat(text, bad_value):
    ok, bad = check(text)
    assert not ok and bad_value in bad


def test_so_nguoi_dung_tu_noi_la_hop_le():
    assert check("Bạn nói mua 1,2 triệu.", user="nếu mua tai nghe 1,2 triệu")[0]
    assert check("Mua 3 triệu.", user="nếu mua tai nghe 1,2 triệu")[0] is False


def test_ngay_thang_va_so_nho_khong_phai_so_tien():
    assert check("Hạn 05/12/2026, còn 3 hũ, sau 14 ngày.")[0]


def test_so_trong_tham_so_hanh_dong_cung_duoc_kiem():
    allowed = Allowed.from_payloads([PAYLOAD])
    ok = NumericGrounding.check({}, allowed, extra_amounts={"phương án a": 1_150_000})
    bad = NumericGrounding.check({}, allowed, extra_amounts={"phương án b": 777_000})
    assert ok.ok and not bad.ok and bad.ungrounded[0].value_vnd == 777_000


def test_dem_so_da_kiem():
    allowed = Allowed.from_payloads([PAYLOAD])
    res = NumericGrounding.check({"a": "Cần 2,2 triệu, hụt 97%.", "b": "Không có số."}, allowed)
    assert res.ok and res.checked_count == 2


def verdict(violations=(), ok=True):
    checked = [{"rule_id": "no_borrow_to_spend", "label": "Không vay để tiêu", "outcome": "fail" if violations else "pass"}]
    return SuitabilityVerdict.model_validate(
        {"ok": ok, "violations": list(violations), "checked": checked, "rules_version": "1"}
    )


BLOCK = {"rule_id": "no_borrow_to_spend", "severity": "block", "message": "Không nên vay để tiêu."}
WARN = {"rule_id": "no_borrow_to_spend", "severity": "warn", "message": "Cân nhắc."}


def test_phan_quyet_pass_retry_fallback():
    allowed = Allowed.from_payloads([PAYLOAD])
    good = NumericGrounding.check({"a": "Cần 2,2 triệu."}, allowed)
    bad = NumericGrounding.check({"a": "Cần 9 triệu."}, allowed)
    suits_ok = [OptionSuitability(option_id="a", verdict=verdict())]
    suits_bad = [OptionSuitability(option_id="a", verdict=verdict([BLOCK], ok=False))]
    assert assemble_verdict(good, suits_ok, attempt=1, max_rounds=2).action == "pass"
    v = assemble_verdict(bad, suits_ok, attempt=1, max_rounds=2)
    assert v.action == "retry" and "9.000.000" in v.feedback[0] and v.failed_rules == ["numeric_grounding"]
    v = assemble_verdict(good, suits_bad, attempt=2, max_rounds=2)
    assert v.action == "retry" and "no_borrow_to_spend" in v.feedback[0]
    assert assemble_verdict(good, suits_bad, attempt=3, max_rounds=2).action == "fallback"  # hết vòng sửa
    # số vòng là cấu hình: max_rounds=0 thì lần đầu sai đã là fallback
    assert assemble_verdict(bad, suits_ok, attempt=1, max_rounds=0).action == "fallback"


def test_trang_thai_phuong_an_theo_luat():
    assert suitability_status(verdict()) == "ok"
    assert suitability_status(verdict([WARN])) == "tight"
    assert suitability_status(verdict([BLOCK], ok=False)) == "short"


# --- hỏi lại --------------------------------------------------------------------------------
def intent(kind: str, **params) -> IntentResult:
    return IntentResult(intent=kind, params=IntentParams(**params), confidence=0.9, needs_clarification=False)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("r", "slot"),
    [
        (intent("what_if", label="điện thoại"), "amount"),
        (intent("what_if", amount_vnd=1_000_000), "funding_source"),
        (intent("what_if", amount_vnd=1_000_000, funding="jar"), "pay_jar"),
        (intent("what_if", amount_vnd=1_000_000, funding="credit"), None),
        (intent("what_if", amount_vnd=1_000_000, scenario_kind="bnpl_purchase"), None),
        (intent("what_if", amount_vnd=1_000_000, funding="jar", jar_text="giải trí"), None),
        (intent("what_if", scenario_kind="goal_delay"), None),
        (intent("what_if", scenario_kind="income_change", amount_vnd=12_000_000), None),
        (intent("affordability"), "amount"),
        (intent("affordability", amount_vnd=250_000), "pay_jar"),  # F3: không hũ nguồn thì hỏi, không đoán "Đủ"
        (intent("affordability", amount_vnd=250_000, jar_text="hóa đơn"), None),
        (intent("affordability", amount_vnd=250_000, funding="credit"), None),
        (intent("what_if", amount_vnd=250_000, scenario_kind="jar_transfer", to_jar_text="ăn uống"), "jar"),
        (intent("what_if", amount_vnd=250_000, scenario_kind="jar_transfer", from_jar_text="giải trí", to_jar_text="ăn uống"), None),
        (intent("move", from_jar_text="a", to_jar_text="b"), "amount"),
        (intent("move", amount_vnd=1), "jar"),
        (intent("profile_update"), "other"),
        (intent("profile_update", obligation_name="Tiền trọ"), "amount"),
        (intent("profile_update", salary_vnd=9_000_000), None),
        (intent("lookup", lookup_kind="balance"), None),
        (intent("chitchat"), None),
    ],
)
def test_o_bat_buoc_con_thieu(r, slot):
    assert missing_slot(r) == slot


def test_cau_hoi_lai_luon_la_dung_mot_cau():
    for r in (intent("what_if"), intent("what_if", amount_vnd=1), intent("affordability"), intent("move"), intent("profile_update")):
        req = resolve_clarify(r)
        assert req is not None and req.question.count("?") == 1 and len(req.chips) <= 6


def test_router_hoi_thua_thi_tin_ma():
    from yofina_agent.schemas import ClarifyRequest

    r = IntentResult(
        intent="what_if",
        params=IntentParams(amount_vnd=1_000_000, funding="credit"),
        confidence=0.9,
        needs_clarification=True,
        clarify=ClarifyRequest(slot="amount", question="Bao nhiêu?"),
    )
    assert resolve_clarify(r) is None  # đã đủ thông tin: không hỏi thừa


# --- bản ghi lượt ---------------------------------------------------------------------------
def test_do_tin_cay_do_ma_viet_tu_co_so_du_bao():
    basis = {"confidence_band": "medium", "is_initial_estimate": True, "history_days": 20, "coverage": 0.8, "stale": True}
    c = confidence([basis, {**basis, "confidence_band": "low", "is_initial_estimate": False, "stale": False}])
    assert c["band"] == "low" and 2 <= len(c["reasons"]) <= 4 and "20 ngày" in c["reasons"][0]
    assert confidence([])["band"] == "high"


def test_gop_luat_giu_ket_qua_nang_nhat_va_cong_don_thoi_gian():
    rules = merge_rules([verdict(), verdict([WARN])])
    assert len(rules) == 1 and rules[0]["outcome"] == "fail"
    assert step_timings([("tools", 10), ("router", 5), ("tools", 7)]) == [{"step": "tools", "ms": 17}, {"step": "router", "ms": 5}]


def test_nguon_du_lieu_khu_trung_va_luon_co_it_nhat_mot_dong():
    o = ToolOutcome("ledger___get_jar_balances", ToolKind.OK, payload={"as_of": "2026-11-21T03:00:00Z", "data": {"jars": [{}, {}]}})
    rows = data_used([o, o, ToolOutcome("planner___check_suitability", ToolKind.OK, payload={"data": {}})])
    assert rows == [{"label": "Số dư các hũ", "value": "2 hũ", "tool": "ledger___get_jar_balances", "as_of": "2026-11-21T03:00:00Z"}]
    only = data_used([])
    assert len(only) == 1 and only[0]["tool"] == "agent"


def test_ban_ghi_luot_khop_cot_migration():
    rec = build_record(
        trace_id="abc",
        conversation_id="c",
        intent="what_if",
        outcome="ok",
        code=None,
        outcomes=[],
        suitability=[verdict()],
        extra_rules=[],
        bases=[],
        blocks=[{"id": "b1", "type": "options"}],
        usage_by_model=[{"inputTokens": 10, "outputTokens": 5}],
        model_calls=3,
        steps=[("router", 1)],
        duration_ms=1234,
    )
    assert set(rec) >= {"trace_id", "conversation_id", "intent", "outcome", "data_used", "rules_checked", "confidence",
                        "blocks_emitted", "token_usage", "step_timings", "duration_ms"}
    assert rec["token_usage"] == {"input_tokens": 10, "output_tokens": 5, "model_calls": 3}


def test_params_do_model_nho_tra_thanh_chuoi_van_doc_duoc():
    """Nova 2 Lite đôi khi trả `params` thành chuỗi (có cả `None` kiểu Python lẫn `null` kiểu JSON) hoặc null."""
    base = {"intent": "out_of_scope", "confidence": 1.0, "needs_clarification": False}
    r = IntentResult.model_validate({**base, "params": '{"lookup_kind": None, "jar_text": null, "amount_vnd": 5, "funding": None}'})
    assert r.params.amount_vnd == 5 and r.params.jar_text is None
    assert IntentResult.model_validate({**base, "params": None}).params == IntentParams()
    assert IntentResult.model_validate({**base, "params": '{"amount_vnd": 7}'}).params.amount_vnd == 7
