"""Bộ luật suitability: nạp YAML (dữ liệu), năm bộ đánh giá, ngưỡng đọc từ file (đổi file đổi kết quả, không đổi mã)."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest
from yofina_core.suitability import Proposal
from yofina_planner.engine import (
    applies,
    effective_essential,
    evaluate,
    obligation_ratio_figures,
    passed_rule_ids,
)
from yofina_planner.facts import JarFact, ObligationFact, SuitabilityFacts, facts_from_rows
from yofina_planner.rules import default_rules_dir, load_rules, rules_version

TODAY = date(2026, 11, 21)
RULE_IDS = [
    "obligations_first",
    "emergency_before_investing",
    "risk_within_tolerance",
    "no_borrow_to_spend",
    "obligation_to_income",
    "source_jar_covers",
]


def ob(name, amount, due, *, essential=True, pay="hoa_don", cycle="monthly", kind="bill"):
    return ObligationFact(kind, name, amount, due, cycle, due.day if cycle == "monthly" else None, pay, essential)


def facts(**kw):
    base = dict(
        today=TODAY,
        next_payday=date(2026, 12, 5),
        monthly_income_vnd=9_000_000,
        risk_tolerance="medium",
        jars=(
            JarFact("hoa_don", "Hóa đơn", "spending", 450_000),
            JarFact("du_phong", "Dự phòng", "saving", 2_700_000),
            JarFact("du_lich", "Du lịch", "saving", 1_800_000, goal_vnd=6_000_000),
            JarFact("nghia_vu", "Nghĩa vụ", "obligation", 1_000_000),
        ),
        obligations=(
            ob("Tiền điện", 375_000, date(2026, 11, 26)),
            ob("Thuê phòng", 2_000_000, date(2026, 12, 6), pay="nghia_vu"),
            ob("Trả sau", 1_000_000, date(2026, 12, 5), essential=False, pay="nghia_vu", cycle="once", kind="bnpl"),
        ),
        window_days=30,
    )
    base.update(kw)
    return SuitabilityFacts(**base)


RULES = load_rules()


def check(proposal, f=None, **kw):
    return evaluate(Proposal.model_validate(proposal, strict=False), f or facts(), RULES, **kw)


def by(verdict):
    return {c.rule_id: c for c in verdict.checked}


# --- nạp luật -------------------------------------------------------------------------------------------
def test_sau_luat_nap_tu_yaml_theo_thu_tu_va_phien_ban():
    assert [r.id for r in RULES] == RULE_IDS
    assert rules_version(RULES) == "v1.1.1.1.1.1"
    assert all(p.stem in RULE_IDS for p in default_rules_dir().glob("*.yaml"))


def test_luat_sai_dinh_dang_hoac_sai_ten_file_thi_bao_loi_khong_bo_qua(tmp_path: Path):
    shutil.copytree(default_rules_dir(), tmp_path / "r")
    (tmp_path / "r" / "obligations_first.yaml").rename(tmp_path / "r" / "doi_ten.yaml")
    with pytest.raises(ValueError, match="không trùng tên file"):
        load_rules(tmp_path / "r")
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="không có luật nào"):
        load_rules(empty)


def test_nguong_la_du_lieu_doi_file_doi_ket_qua_khong_doi_ma(tmp_path: Path):
    prop = {"kind": "proceed", "category": "investment", "risk_level": "low", "origin": "recommendation"}
    assert by(check(prop))["emergency_before_investing"].outcome == "fail"  # 2,7 triệu / chi thiết yếu hằng tháng: chưa đủ 3 tháng
    shutil.copytree(default_rules_dir(), tmp_path / "r")
    path = tmp_path / "r" / "emergency_before_investing.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("value: 3", "value: 0.5"), encoding="utf-8")
    relaxed = load_rules(tmp_path / "r")
    v = evaluate(Proposal.model_validate(prop, strict=False), facts(), relaxed)
    assert by(v)["emergency_before_investing"].outcome == "pass"


# --- luật 1: nghĩa vụ trước -----------------------------------------------------------------------------
def test_nghia_vu_truoc_chi_tuy_y_tu_hu_tra_nghia_vu_bi_chan():
    # hũ Hóa đơn 450.000 phải trả tiền điện 375.000 trước kỳ lương: chi 200.000 từ hũ này làm thiếu
    v = check({"kind": "one_time_purchase", "amount_vnd": 200_000, "funding_source": "jar", "jar_code": "hoa_don", "origin": "recommendation"})
    c = by(v)["obligations_first"]
    assert c.outcome == "fail" and not v.ok and "Hóa đơn" in c.detail
    # chi từ hũ không gánh nghĩa vụ thì qua
    ok = check({"kind": "one_time_purchase", "amount_vnd": 200_000, "funding_source": "jar", "jar_code": "du_lich"})
    assert by(ok)["obligations_first"].outcome == "pass" and ok.ok


def test_nghia_vu_truoc_khoan_thiet_yeu_khong_ap_dung():
    v = check({"kind": "one_time_purchase", "amount_vnd": 200_000, "funding_source": "jar", "jar_code": "hoa_don", "is_essential": True})
    assert by(v)["obligations_first"].outcome == "skipped" and v.ok


# --- luật 2 và 3: đầu tư -------------------------------------------------------------------------------
def test_dau_tu_can_quy_du_phong_va_khau_vi_rui_ro():
    prop = {"kind": "proceed", "category": "investment", "amount_vnd": 500_000, "risk_level": "high", "origin": "recommendation"}
    v = check(prop)
    assert [x.rule_id for x in v.violations] == ["emergency_before_investing", "risk_within_tolerance"]
    assert all(x.severity == "block" for x in v.violations) and not v.ok
    rich = facts(jars=(JarFact("du_phong", "Dự phòng", "saving", 50_000_000),))
    ok = check({**prop, "risk_level": "medium"}, rich)
    assert ok.ok and by(ok)["emergency_before_investing"].outcome == "pass" and by(ok)["risk_within_tolerance"].outcome == "pass"
    unknown = facts(risk_tolerance=None, jars=rich.jars)
    assert by(check({**prop, "risk_level": "medium"}, unknown))["risk_within_tolerance"].outcome == "fail"  # chưa khai: coi là thấp
    assert by(check({**prop, "risk_level": None}, rich))["risk_within_tolerance"].outcome == "fail"  # chưa rõ rủi ro: coi là cao


def test_khong_phai_dau_tu_thi_luat_dau_tu_bi_bo_qua_va_van_du_moi_luat():
    v = check({"kind": "defer"})
    assert len(v.checked) == len(RULE_IDS) and by(v)["emergency_before_investing"].outcome == "skipped"
    assert {c.outcome for c in v.checked} <= {"pass", "skipped"}


# --- luật 4: không khuyên vay để tiêu -------------------------------------------------------------------
@pytest.mark.parametrize(
    ("origin", "essential", "severity"),
    [("user_request", False, "warn"), ("recommendation", False, "block"), ("recommendation", True, None), ("user_request", None, None)],
)
def test_vay_de_tieu_theo_nguon_de_xuat(origin, essential, severity):
    prop = {"kind": "use_credit", "amount_vnd": 100_000, "funding_source": "credit", "origin": origin, "is_essential": essential}
    v = check(prop)
    got = next((x.severity for x in v.violations if x.rule_id == "no_borrow_to_spend"), None)
    assert got == severity


# --- luật 5: nghĩa vụ trên thu nhập ---------------------------------------------------------------------
def test_ty_le_nghia_vu_tren_thu_nhap_theo_ky_30_ngay():
    f = facts()
    # tiền điện 375.000 + Trả sau 1.000.000 + thuê phòng 2.000.000 (06/12) = 3.375.000 trong 30 ngày
    assert f.window_obligations_vnd() == 3_375_000
    fig = obligation_ratio_figures(f, 1_200_000, RULES)
    assert fig == {"obligations_vnd": 4_575_000, "income_vnd": 9_000_000, "ratio": 0.5083, "threshold": 0.36, "exceeds": True}
    v = check({"kind": "use_credit", "amount_vnd": 1_200_000, "funding_source": "credit", "origin": "user_request"}, added_obligation_vnd=1_200_000)
    c = by(v)["obligation_to_income"]
    assert c.outcome == "warn" and "51%" in c.detail  # warn với lời người dùng, block với phương án hệ thống
    sys_v = check({"kind": "use_credit", "amount_vnd": 1_200_000, "funding_source": "credit", "origin": "recommendation"})
    assert any(x.rule_id == "obligation_to_income" and x.severity == "block" for x in sys_v.violations)


def test_ty_le_bo_qua_khi_khong_them_nghia_vu_hoac_chua_khai_thu_nhap():
    assert by(check({"kind": "defer"}))["obligation_to_income"].outcome == "skipped"
    assert obligation_ratio_figures(facts(monthly_income_vnd=None), 1, RULES) is None
    v = check({"kind": "use_credit", "amount_vnd": 1}, facts(monthly_income_vnd=None))
    assert by(v)["obligation_to_income"].outcome == "skipped"


# --- tiện ích ---------------------------------------------------------------------------------------------
def test_essential_mac_dinh_va_applies_va_passed_rule_ids():
    assert effective_essential(Proposal(kind="one_time_purchase")) is False
    assert effective_essential(Proposal(kind="switch_jar")) is None
    assert effective_essential(Proposal(kind="bnpl_purchase", is_essential=True)) is True
    assert applies(None, Proposal(kind="x")) is True
    v = check({"kind": "defer"})
    assert passed_rule_ids(v) == [c.rule_id for c in v.checked if c.outcome == "pass"]


def test_facts_from_rows_bo_hu_he_thong_va_nghia_vu_khong_hoat_dong():
    f = facts_from_rows(
        today=TODAY,
        user={"monthly_salary_vnd": 9_000_000, "payday_day": 5, "risk_tolerance": "low"},
        jars=[
            {"code": "a", "name": "A", "kind": "spending", "balance_vnd": 10, "goal_vnd": None},
            {"code": "tien_vao_khac", "name": "TVK", "kind": "system", "balance_vnd": 99, "goal_vnd": None},
        ],
        obligations=[
            {"kind": "bill", "name": "x", "amount_vnd": 5, "due_date": "2026-11-25", "cycle": "once", "status": "paid", "is_essential": True},
            {"kind": "bill", "name": "y", "amount_vnd": 7, "due_date": date(2026, 11, 25), "cycle": "once", "status": "active", "is_essential": True},
        ],
        window_days=30,
    )
    assert [j.code for j in f.jars] == ["a"] and [o.name for o in f.obligations] == ["y"]
    assert f.next_payday == date(2026, 12, 5) and f.risk_tolerance == "low"


# --- luật 6: hũ nguồn đủ tiền --------------------------------------------------------------------------
def test_hu_nguon_khong_du_tien_he_thong_de_xuat_thi_chan_nguoi_dung_hoi_thi_canh_bao():
    # hũ Dự phòng 2.700.000 ₫, khoản 15.000.000 ₫ (lỗi đi cảnh 2: phương án "Dùng hũ Dự phòng" hiện "Đủ")
    prop = {"kind": "switch_jar", "amount_vnd": 15_000_000, "funding_source": "jar", "jar_code": "du_phong", "origin": "recommendation"}
    v = check(prop)
    c = by(v)["source_jar_covers"]
    assert c.outcome == "fail" and not v.ok and "Dự phòng" in c.detail and "12.300.000" in c.detail
    assert [x.severity for x in v.violations if x.rule_id == "source_jar_covers"] == ["block"]
    user = check({**prop, "origin": "user_request"})
    assert by(user)["source_jar_covers"].outcome == "warn" and user.ok
    # vừa đúng số dư thì qua (ngưỡng còn lại 0 ₫ trong file luật)
    assert by(check({**prop, "amount_vnd": 2_700_000}))["source_jar_covers"].outcome == "pass"


def test_hu_nguon_bo_qua_khi_khong_lay_tien_tu_hu():
    assert by(check({"kind": "defer", "funding_source": "jar"}))["source_jar_covers"].outcome == "skipped"
    credit = {"kind": "use_credit", "amount_vnd": 15_000_000, "funding_source": "credit", "jar_code": "du_phong"}
    assert by(check(credit))["source_jar_covers"].outcome == "skipped"  # nguồn tín dụng: không áp luật


def test_nguong_hu_nguon_la_du_lieu(tmp_path: Path):
    shutil.copytree(default_rules_dir(), tmp_path / "r")
    path = tmp_path / "r" / "source_jar_covers.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("value: 0", "value: 500000"), encoding="utf-8")
    prop = {"kind": "switch_jar", "amount_vnd": 2_500_000, "funding_source": "jar", "jar_code": "du_phong", "origin": "recommendation"}
    assert by(check(prop))["source_jar_covers"].outcome == "pass"
    v = evaluate(Proposal.model_validate(prop, strict=False), facts(), load_rules(tmp_path / "r"))
    assert by(v)["source_jar_covers"].outcome == "fail"  # phải giữ lại 500.000 ₫
