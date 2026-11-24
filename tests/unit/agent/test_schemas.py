"""Hình dạng các kiểu của harness phase 3 (`yofina_agent.schemas`): IntentResult, Plan, Analysis, Verdict. Chỉ kiểm kiểu và bất
biến; chưa có luồng agent nào dùng chúng (luồng B nối vào sau)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from yofina_agent import schemas as s

from yofina_core import wallet

LIMITS = {"max_rounds": 2, "max_tokens": 4000, "max_model_calls": 4}
SCENARIO = {
    "kind": "bnpl_purchase",
    "amount_vnd": 1200000,
    "funding_source": "credit",
    "label": "tai nghe",
}
OK_VERDICT = {
    "ok": True,
    "violations": [],
    "checked": [{"rule_id": "obligations_first", "label": "Nghĩa vụ trước", "outcome": "pass"}],
    "rules_version": "1",
}
BAD_VERDICT = {
    "ok": False,
    "violations": [
        {"rule_id": "no_borrow_to_spend", "severity": "block", "message": "Không nên vay."}
    ],
    "checked": [
        {"rule_id": "no_borrow_to_spend", "label": "Không khuyên vay để tiêu", "outcome": "fail"}
    ],
    "rules_version": "1",
}


def intent(**over):
    base = {
        "intent": "what_if",
        "params": {"amount_vnd": 1200000, "funding": "credit", "scenario_kind": "bnpl_purchase"},
        "confidence": 0.92,
        "needs_clarification": False,
    }
    return {**base, **over}


# --- IntentResult ------------------------------------------------------------------------------
def test_muoi_y_dinh_khop_hang_so_hop_dong():
    args = tuple(s.Intent.__args__)
    assert args[: len(wallet.INTENTS)] == wallet.INTENTS
    assert len(wallet.INTENTS) == 11
    assert wallet.INTENTS[:7] == wallet.INTENTS_PHASE3  # bảy ý định của phase 3 giữ nguyên thứ tự
    assert wallet.INTENTS[7:10] == (
        "resilience",
        "stress",
        "roadmap",
    )  # phase 4 (luồng C cài router)
    assert wallet.INTENTS[10:] == ("memory",)  # phase 5, luồng p5-memory
    # phase 5: ý định đã có bộ xử lý ở agent nhưng còn nằm trong `wallet.PHASE5_INTENTS` (cột audit_events.intent của 0053 nhận được)
    assert args[len(wallet.INTENTS) :] == ("knowledge", "ingest")
    assert set(args) <= set(wallet.AUDIT_INTENTS)


@pytest.mark.parametrize("name", wallet.INTENTS)
def test_moi_y_dinh_tao_duoc_intent_result(name):
    r = s.IntentResult.model_validate(intent(intent=name, params={}))
    assert r.intent == name and r.clarify is None and not r.needs_clarification


def test_router_doc_duoc_ma_cu_soc_la_de_handler_kiem():
    r = s.IntentResult.model_validate(
        intent(intent="stress", params='{"shock_id":"ma_khong_co_trong_cau_hinh"}')
    )
    assert r.params.shock_id == "ma_khong_co_trong_cau_hinh"


def test_thieu_so_tien_thi_hoi_lai_dung_mot_cau_kem_chip():
    r = s.IntentResult.model_validate(
        intent(
            params={"scenario_kind": "one_time_purchase", "label": "điện thoại"},
            needs_clarification=True,
            clarify={
                "slot": "amount",
                "question": "Bạn định mua cái điện thoại với giá khoảng bao nhiêu?",
                "chips": [{"label": "Khoảng 10 triệu", "value": "10 triệu"}],
            },
        )
    )
    assert r.clarify.slot == "amount" and r.params.amount_vnd is None


def test_doi_luong_model_dat_so_vao_salary_vnd_thi_chuyen_sang_amount_vnd():
    r = s.IntentResult.model_validate(
        intent(
            intent="what_if", params={"scenario_kind": "income_change", "salary_vnd": 12_000_000}
        )
    )
    assert r.params.amount_vnd == 12_000_000 and r.params.salary_vnd is None
    # có sẵn amount_vnd thì giữ nguyên; khai báo hồ sơ thì salary_vnd không bị đụng tới
    r2 = s.IntentResult.model_validate(
        intent(
            intent="what_if",
            params={
                "scenario_kind": "income_change",
                "amount_vnd": 9_000_000,
                "salary_vnd": 12_000_000,
            },
        )
    )
    assert r2.params.amount_vnd == 9_000_000
    r3 = s.IntentResult.model_validate(
        intent(intent="profile_update", params={"salary_vnd": 12_000_000})
    )
    assert r3.params.salary_vnd == 12_000_000 and r3.params.amount_vnd is None


def test_hu_tra_tien_dat_nham_from_jar_text_thi_doi_sang_jar_text():
    # Router thật 23/11: "Chuyển 250 nghìn từ hũ Hóa đơn cho người nhận demo có ổn không" ra from/to thay vì jar_text.
    r = s.IntentResult.model_validate(
        intent(
            intent="affordability",
            params={
                "from_jar_text": "Hóa đơn",
                "to_jar_text": "người nhận demo",
                "amount_vnd": 250_000,
            },
        )
    )
    p = r.params
    assert (p.jar_text, p.label, p.from_jar_text, p.to_jar_text) == (
        "Hóa đơn",
        "người nhận demo",
        None,
        None,
    )
    r2 = s.IntentResult.model_validate(
        intent(
            intent="what_if",
            params={
                "scenario_kind": "one_time_purchase",
                "from_jar_text": "hũ giải trí",
                "amount_vnd": 600_000,
                "label": "bàn phím",
            },
        )
    )
    assert (r2.params.jar_text, r2.params.label, r2.params.from_jar_text) == (
        "hũ giải trí",
        "bàn phím",
        None,
    )


@pytest.mark.parametrize(
    "name,params",
    [
        ("move", {"from_jar_text": "Ăn uống", "to_jar_text": "Tiết kiệm", "amount_vnd": 100_000}),
        (
            "what_if",
            {
                "scenario_kind": "jar_transfer",
                "from_jar_text": "Ăn uống",
                "to_jar_text": "Tiết kiệm",
                "amount_vnd": 100_000,
            },
        ),
        (
            "what_if",
            {"from_jar_text": "Ăn uống", "to_jar_text": "Tiết kiệm", "amount_vnd": 100_000},
        ),
    ],
)
def test_chuyen_giua_hai_hu_giu_nguyen_from_to(name, params):
    r = s.IntentResult.model_validate(intent(intent=name, params=params))
    assert (r.params.from_jar_text, r.params.to_jar_text, r.params.jar_text) == (
        "Ăn uống",
        "Tiết kiệm",
        None,
    )


def test_needs_clarification_phai_di_voi_clarify_va_nguoc_lai():
    with pytest.raises(ValidationError):
        s.IntentResult.model_validate(intent(needs_clarification=True))
    with pytest.raises(ValidationError):
        s.IntentResult.model_validate(
            intent(clarify={"slot": "amount", "question": "Bao nhiêu?", "chips": []})
        )


def test_chi_hoi_mot_cau_va_ngoai_pham_vi_khong_hoi_lai():
    with pytest.raises(ValidationError):
        s.ClarifyRequest.model_validate({"slot": "amount", "question": "Bao nhiêu? Bằng gì?"})
    with pytest.raises(ValidationError):
        s.IntentResult.model_validate(
            intent(
                intent="out_of_scope",
                needs_clarification=True,
                clarify={"slot": "other", "question": "Bạn muốn gì?"},
            )
        )


@pytest.mark.parametrize(
    "bad", [{"confidence": 1.2}, {"confidence": -0.1}, {"intent": "buy_stock"}]
)
def test_intent_result_sai_bi_tu_choi(bad):
    with pytest.raises(ValidationError):
        s.IntentResult.model_validate(intent(**bad))


def test_intent_result_tu_choi_truong_la_va_so_tien_khong_duong():
    with pytest.raises(ValidationError):
        s.IntentResult.model_validate({**intent(), "user_id": "someone"})
    with pytest.raises(ValidationError):
        s.IntentResult.model_validate(intent(params={"amount_vnd": 0}))


# --- Plan --------------------------------------------------------------------------------------
def plan(**over):
    base = {
        "intent": "what_if",
        "scenario": SCENARIO,
        "steps": [
            {"tool": "forecast___get_forecast", "args": {"jar": "giai_tri"}, "parallel_group": 0},
            {"tool": "ledger___get_obligations", "args": {}, "parallel_group": 0},
            {"tool": "knowledge___get_fee_schedule", "args": {}, "parallel_group": 0},
            {
                "tool": "forecast___run_scenario",
                "args": {"scenario": SCENARIO},
                "parallel_group": 1,
            },
        ],
        "limits": LIMITS,
    }
    return {**base, **over}


def test_plan_what_if_dung_scenario_spec_hop_le():
    p = s.Plan.model_validate(plan())
    assert p.scenario_spec().kind == "bnpl_purchase"
    assert [x.parallel_group for x in p.steps] == [0, 0, 0, 1]


def test_plan_scenario_sai_bi_tu_choi_boi_model_cua_yofina_core():
    with pytest.raises(ValidationError):
        s.Plan.model_validate(plan(scenario={**SCENARIO, "funding_source": "jar"}))
    with pytest.raises(ValidationError):
        s.Plan.model_validate(plan(scenario=None))  # what_if bắt buộc có scenario
    with pytest.raises(ValidationError):
        s.Plan.model_validate(plan(intent="lookup"))  # lookup không có scenario


def test_plan_chi_chua_tool_doc_khong_co_tool_ghi_va_khong_mang_user_id():
    assert not {
        "ledger___update_profile",
        "ledger___record_transaction",
        "planner___schedule_nudge",
    } & set(s.PLAN_TOOLS)
    assert set(s.PLAN_TOOLS) == set(s.PlanToolName.__args__)
    with pytest.raises(ValidationError):
        s.PlanStep.model_validate(
            {"tool": "ledger___record_transaction", "args": {}, "parallel_group": 0}
        )
    for bad_arg in ("user_id", "confirm_token"):
        with pytest.raises(ValidationError):
            s.PlanStep.model_validate(
                {"tool": "forecast___get_forecast", "args": {bad_arg: "x"}, "parallel_group": 0}
            )


def test_plan_limits_khong_co_mac_dinh_vi_thuoc_ve_cau_hinh():
    with pytest.raises(ValidationError):
        s.PlanLimits.model_validate({})
    with pytest.raises(ValidationError):
        s.PlanLimits.model_validate({**LIMITS, "max_rounds": 0})
    assert all(f.is_required() for f in s.PlanLimits.model_fields.values())


def test_plan_toi_da_tam_buoc_va_it_nhat_mot():
    with pytest.raises(ValidationError):
        s.Plan.model_validate(plan(steps=[]))
    step = {"tool": "ledger___get_jar_balances", "args": {}, "parallel_group": 0}
    with pytest.raises(ValidationError):
        s.Plan.model_validate(plan(steps=[step] * 9))


# --- Analysis ----------------------------------------------------------------------------------
def option(option_id="defer_payday", **over):
    base = {
        "option_id": option_id,
        "kind": "defer",
        "label": "Hoãn tới sau kỳ lương",
        "summary": "Mua sau ngày lương về.",
        "proposal": {
            "kind": "defer",
            "funding_source": "jar",
            "is_essential": False,
            "origin": "recommendation",
        },
    }
    return {**base, **over}


def test_analysis_hai_den_ba_phuong_an_id_duy_nhat():
    a = s.Analysis.model_validate(
        {
            "narrative": "Mua ngay làm hũ hụt.",
            "options": [option(), option("switch_jar", kind="switch_jar")],
        }
    )
    assert len(a.options) == 2 and a.follow_ups == []
    with pytest.raises(ValidationError):
        s.Analysis.model_validate({"narrative": "x", "options": [option()]})
    with pytest.raises(ValidationError):
        s.Analysis.model_validate(
            {"narrative": "x", "options": [option(f"o{i}") for i in range(4)]}
        )
    with pytest.raises(ValidationError):
        s.Analysis.model_validate({"narrative": "x", "options": [option(), option()]})


def test_phuong_an_co_hanh_dong_ghi_chi_la_mo_ta_khong_co_token():
    o = s.AnalysisOption.model_validate(
        option(
            action={
                "tool": "schedule_nudge",
                "params": {"kind": "purchase_review", "fire_on": "2026-11-26"},
            }
        )
    )
    assert o.action.tool == "schedule_nudge"
    with pytest.raises(ValidationError):
        s.AnalysisOption.model_validate(option(action={"tool": "drop_table", "params": {}}))


def test_de_xuat_cua_phuong_an_dung_kieu_proposal_cua_suitability():
    o = s.AnalysisOption.model_validate(
        option(proposal={"kind": "use_credit", "funding_source": "credit"})
    )
    assert o.proposal.funding_source == "credit"
    with pytest.raises(ValidationError):
        s.AnalysisOption.model_validate(option(proposal={"kind": "x", "risk_level": "extreme"}))


# --- Verdict -----------------------------------------------------------------------------------
GROUND_OK = {"ok": True, "checked_count": 5, "ungrounded": []}
GROUND_BAD = {
    "ok": False,
    "checked_count": 5,
    "ungrounded": [{"text": "1,3 triệu", "value_vnd": 1300000}],
}


def test_verdict_dat_khi_grounding_va_suitability_deu_ok():
    v = s.Verdict.model_validate(
        {
            "ok": True,
            "grounding": GROUND_OK,
            "suitability": [{"option_id": "defer_payday", "verdict": OK_VERDICT}],
            "attempt": 1,
            "action": "pass",
        }
    )
    assert v.ok and v.feedback == [] and v.action == "pass"


def test_verdict_khong_dat_phai_co_feedback_co_cau_truc_cho_analyst():
    payload = {
        "ok": False,
        "grounding": GROUND_BAD,
        "suitability": [{"option_id": "use_credit", "verdict": BAD_VERDICT}],
        "feedback": [
            "Số 1,3 triệu không có trong kết quả tool.",
            "Phương án use_credit vi phạm no_borrow_to_spend.",
        ],
        "failed_rules": ["no_borrow_to_spend"],
        "attempt": 1,
        "action": "retry",
    }
    v = s.Verdict.model_validate(payload)
    assert not v.ok and v.action == "retry" and v.failed_rules == ["no_borrow_to_spend"]
    with pytest.raises(ValidationError):
        s.Verdict.model_validate({**payload, "feedback": []})
    # hết vòng thì chỉ phát khối tất định: fallback vẫn là không ok
    assert (
        s.Verdict.model_validate({**payload, "action": "fallback", "attempt": 3}).action
        == "fallback"
    )


def test_verdict_bat_bien_ok_action_va_grounding():
    base = {
        "grounding": GROUND_OK,
        "suitability": [{"option_id": "a", "verdict": OK_VERDICT}],
        "attempt": 1,
    }
    with pytest.raises(ValidationError):
        s.Verdict.model_validate({**base, "ok": True, "action": "retry"})  # ok mà không pass
    with pytest.raises(ValidationError):
        s.Verdict.model_validate(
            {**base, "ok": False, "action": "retry", "feedback": ["x"]}
        )  # ok sai
    with pytest.raises(ValidationError):
        s.GroundingResult.model_validate(
            {"ok": True, "checked_count": 1, "ungrounded": GROUND_BAD["ungrounded"]}
        )
    with pytest.raises(ValidationError):
        s.GroundingResult.model_validate({"ok": False, "checked_count": 1, "ungrounded": []})


def test_so_vong_thu_lai_khong_nam_trong_kieu():
    """Số vòng tối đa là cấu hình (nhóm harness), nên `Verdict` chỉ mang `attempt`, không có hằng số trần."""
    assert "max_attempts" not in s.Verdict.model_fields
    assert s.Verdict.model_fields["attempt"].is_required()
