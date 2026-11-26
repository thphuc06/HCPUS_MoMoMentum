"""Đề xuất tỷ lệ chia lương theo số đã khai (onboarding bước 3, `yofina_ledger.split_proposal`): làm tròn lên, nguồn bù
(Chi hằng ngày trước, Dự phòng không dưới sàn), Nghĩa vụ vượt số chia được, bỏ qua kê khai, lương lệch BR-12, Quỹ dồn từ khoản
biết trước, kiểm tra theo ngày và dòng xem trước của `save_jars`. Hàm thuần nên không cần DB; luồng có DB ở
tests/local_pg/test_onboarding_declare.py."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest

from yofina_core.params import ParamsError
from yofina_ledger import split_proposal as sp

TODAY = date(2026, 11, 21)
SALARY = 9_000_000
PAYDAY = 5
TEMPLATE = {"code": "quy_don", "name": "Quỹ dồn", "color_key": "teal", "icon_key": "calendar"}
NAMES = {
    "chi_hang_ngay": "Chi hằng ngày",
    "nghia_vu": "Nghĩa vụ",
    "du_phong": "Dự phòng",
    "quy_don": "Quỹ dồn",
}
_ids = iter(range(1, 10_000))


def jar(code, kind, split, purpose=None, balance=0, **extra):
    return {
        "code": code,
        "name": NAMES.get(code, code),
        "kind": kind,
        "purpose": purpose,
        "split_percent": Decimal(str(split)),
        "balance_vnd": Decimal(balance),
        "color_key": "teal",
        "icon_key": "wallet",
        "goal_vnd": None,
        "goal_date": None,
        "sinking_items": None,
        **extra,
    }


def three(chi=42, ob=33, buffer=25):
    return [
        jar("chi_hang_ngay", "spending", chi),
        jar("nghia_vu", "obligation", ob),
        jar("du_phong", "saving", buffer, "buffer"),
    ]


def ob(name, amount, *, kind="rent", cycle="monthly", due=date(2026, 12, 1), due_day=1, essential=True,
       source="declared", pay=None):  # fmt: skip
    return {
        "id": f"00000000-0000-4000-8000-{next(_ids):012d}",
        "kind": kind,
        "name": name,
        "amount_vnd": Decimal(amount),
        "cycle": cycle,
        "due_date": due,
        "due_day": due_day if cycle == "monthly" else None,
        "status": "active",
        "source": source,
        "is_essential": essential,
        "pay_jar_code": pay,
    }


def propose(**kw):
    args = dict(
        today=TODAY, salary_vnd=SALARY, payday_day=PAYDAY, jars=three(), obligations=[], known_items=[],
        salary_events=[], deviation_ask_percent=Decimal(10), buffer_min_percent=10, sinking_template=TEMPLATE,
    )  # fmt: skip
    args.update(kw)
    return sp.build_proposal(**args)


def after(result):
    return {j["code"]: j["split_after"] for j in result["jars"]}


def params_split(result):
    return {j["code"]: j["split_percent"] for j in result["params"]["jars"]}


# --- tỷ lệ Nghĩa vụ ----------------------------------------------------------------------------------------
def test_obligation_share_rounds_up_and_takes_difference_from_daily_first():
    obs = [
        ob("Tiền trọ", 2_500_000),
        ob("Tiền điện", 375_000, kind="bill", due=date(2026, 11, 26), due_day=26),
        ob("Internet", 220_000, kind="subscription", due=date(2026, 12, 15), due_day=15),
    ]
    result = propose(obligations=obs)
    assert result["status"] == "proposed"
    assert result["obligation_basis"] == "declared"
    assert result["obligations_monthly_vnd"] == 3_095_000  # 34,39% lương -> làm tròn lên 35
    assert after(result) == {"chi_hang_ngay": 40, "nghia_vu": 35, "du_phong": 25}
    assert params_split(result) == {"chi_hang_ngay": 40, "nghia_vu": 35, "du_phong": 25}
    rows = {j["code"]: j for j in result["jars"]}
    assert (rows["nghia_vu"]["amount_before_vnd"], rows["nghia_vu"]["amount_after_vnd"]) == (2_970_000, 3_150_000)
    assert rows["nghia_vu"]["delta_vnd"] == 180_000
    assert rows["chi_hang_ngay"]["delta_vnd"] == -180_000
    assert result["reasons"][0] == {
        "jar_code": "nghia_vu",
        "text": "Nghĩa vụ đã khai 3.095.000 ₫/tháng = 34,4% lương 9.000.000 ₫",
    }


def test_weekly_yearly_are_monthly_equivalents_once_is_not_and_excess_returns_to_daily():
    assert sp.monthly_equivalent(100_000, "weekly") == Fraction(100_000 * 52, 12)
    assert sp.monthly_equivalent(1_200_000, "yearly") == Fraction(100_000)
    assert sp.monthly_equivalent(5_000_000, "once") == 0
    assert sp.ceil_percent(Fraction(9_000_001), SALARY) == 101
    obs = [
        ob("Gửi xe", 100_000, kind="bill", cycle="weekly", due=date(2026, 11, 28)),
        ob("Bảo hiểm", 1_200_000, kind="bill", cycle="yearly", due=date(2027, 3, 1)),
        ob("Học phí", 5_000_000, kind="bill", cycle="once", due=date(2027, 1, 10)),
    ]
    result = propose(obligations=obs)
    # 433.333,33 + 100.000 = 533.333,33/tháng = 5,93% -> 6; 27 điểm thừa trả về Chi hằng ngày
    assert after(result) == {"chi_hang_ngay": 69, "nghia_vu": 6, "du_phong": 25}


def test_less_than_one_point_off_is_aligned_and_has_no_params():
    jars = three(chi="41.5", ob="33.5")
    result = propose(jars=jars, obligations=[ob("Tiền trọ", 2_900_000)])  # 32,2% -> 33, lệch 0,5 điểm
    assert result["status"] == "aligned"
    assert "params" not in result
    assert after(result) == {"chi_hang_ngay": 41.5, "nghia_vu": 33.5, "du_phong": 25}


def test_daily_then_buffer_down_to_configured_floor():
    result = propose(obligations=[ob("Tiền trọ", 8_100_000)])  # 90%
    assert result["status"] == "proposed"
    assert after(result) == {"chi_hang_ngay": 0, "nghia_vu": 90, "du_phong": 10}
    stricter = propose(obligations=[ob("Tiền trọ", 8_100_000)], buffer_min_percent=15)
    assert stricter["status"] == "infeasible"
    assert stricter["required_percent"] == 105
    assert "params" not in stricter


def test_buffer_below_floor_is_never_lowered():
    jars = three(chi=67, ob=28, buffer=5)
    result = propose(jars=jars, obligations=[ob("Tiền trọ", 8_100_000)])  # cần 90 + sàn 5 (đang 5) = 95
    assert after(result) == {"chi_hang_ngay": 5, "nghia_vu": 90, "du_phong": 5}


def test_over_hundred_percent_lists_priority_and_saves_nothing():
    obs = [
        ob("Khoản vay", 4_500_000, kind="loan", essential=False, due=date(2026, 12, 10), due_day=10),
        ob("Netflix", 100_000, kind="subscription", essential=False),
        ob("Tiền điện", 700_000, kind="bill", due=date(2026, 11, 26), due_day=26),
        ob("Tiền trọ", 4_000_000),
    ]
    result = propose(obligations=obs)
    assert result["status"] == "infeasible"
    assert result["required_percent"] == 114  # 9.300.000 = 103,3% -> 104, cộng sàn Dự phòng 10
    assert [o["name"] for o in result["priority_obligations"]] == [
        "Tiền trọ",
        "Tiền điện",
        "Khoản vay",
        "Netflix",
    ]
    assert "params" not in result
    assert after(result) == {"chi_hang_ngay": 42, "nghia_vu": 33, "du_phong": 25}


def test_skipping_declarations_keeps_template_and_marks_basis():
    bnpl = ob("Trả sau (mô phỏng)", 333_000, kind="bnpl", cycle="once", source="bnpl_auto")
    for obligations in ([], [bnpl]):
        result = propose(obligations=obligations)
        assert result["status"] == "no_declarations"
        assert result["obligation_basis"] == "template"
        assert all(j["split_after"] == j["split_before"] for j in result["jars"])
        assert "params" not in result


def test_salary_deviation_beyond_threshold_asks_to_update_salary_first():
    event = {
        "id": "7e1f3a90-2c4b-4d6e-8f01-a3b5c7d9e0f2",
        "received_on": date(2026, 11, 5),
        "period_date": date(2026, 11, 5),
        "amount_vnd": Decimal(7_000_000),
        "status": "confirmed",
    }
    result = propose(obligations=[ob("Tiền trọ", 2_500_000)], salary_events=[event])
    assert result["status"] == "salary_mismatch"
    assert result["salary_check"] == {
        "salary_event_id": event["id"],
        "received_vnd": 7_000_000,
        "declared_vnd": SALARY,
        "deviation_percent": -22.22,
    }
    assert "params" not in result
    lenient = propose(obligations=[ob("Tiền trọ", 2_500_000)], salary_events=[event], deviation_ask_percent=Decimal(25))
    assert lenient["status"] == "proposed"


def test_pending_salary_is_reported_and_counted_in_current_period():
    event = {
        "id": "7e1f3a90-2c4b-4d6e-8f01-a3b5c7d9e0f2",
        "received_on": date(2026, 11, 21),
        "period_date": date(2026, 12, 5),
        "amount_vnd": Decimal(SALARY),
        "status": "pending",
    }
    result = propose(obligations=[ob("Tiền trọ", 2_500_000)], salary_events=[event])
    assert result["pending_salary"] == {"salary_event_id": event["id"], "amount_vnd": SALARY}
    first = result["checks"][0]
    assert first["payday"] == "2026-12-05"
    assert first["available_vnd"] == 2_520_000  # 28% của lương chờ chia (số dư hũ 0)
    assert "shortfall" not in first


# --- Quỹ dồn ---------------------------------------------------------------------------------------------
def test_known_item_proposes_sinking_jar_from_remaining_paydays():
    items = sp.parse_known_items([{"name": "Tết", "amount_vnd": 3_000_000, "needed_date": "2027-02-10"}], TODAY)
    result = propose(known_items=items)
    assert result["status"] == "proposed"
    assert result["obligation_basis"] == "template"
    (plan,) = result["sinking_items"]
    assert (plan["paydays"], plan["per_payday_vnd"], plan["remaining_vnd"]) == (3, 1_000_000, 3_000_000)
    assert after(result) == {"chi_hang_ngay": 30, "nghia_vu": 33, "du_phong": 25, "quy_don": 12}
    new = next(j for j in result["params"]["jars"] if j["code"] == "quy_don")
    assert new["purpose"] == "sinking" and new["kind"] == "saving"
    assert new["sinking_items"] == [{"name": "Tết", "amount_vnd": 3_000_000, "needed_date": "2027-02-10"}]
    assert result["reasons"][-1] == {
        "jar_code": "quy_don",
        "text": "Khoản biết trước cần 1.000.000 ₫/kỳ lương = 11,1% lương",
    }


def test_no_known_items_creates_no_sinking_jar():
    result = propose(obligations=[ob("Tiền trọ", 2_500_000)])
    assert "quy_don" not in after(result)
    assert all(j["code"] != "quy_don" for j in result["params"]["jars"])


def test_existing_sinking_balance_covers_earliest_item_and_dates_stay_committed():
    stored = [{"name": "Tết", "amount_vnd": 3_000_000, "needed_date": "2027-02-10"}]
    jars = [*three(chi=37), jar("quy_don", "saving", 5, "sinking", balance=1_000_000, sinking_items=stored)]
    new = sp.parse_known_items([{"name": "Học phí", "amount_vnd": 1_200_000, "needed_date": "2027-01-20"}], TODAY)
    result = propose(jars=jars, known_items=new)
    plan = {r["name"]: r for r in result["sinking_items"]}
    assert (plan["Học phí"]["remaining_vnd"], plan["Học phí"]["paydays"]) == (200_000, 2)
    assert plan["Tết"]["remaining_vnd"] == 3_000_000
    # (100.000 + 1.000.000)/kỳ = 12,2% -> 13; 8 điểm thêm lấy từ Chi hằng ngày
    assert after(result) == {"chi_hang_ngay": 29, "nghia_vu": 33, "du_phong": 25, "quy_don": 13}
    saved = next(j for j in result["params"]["jars"] if j["code"] == "quy_don")
    assert [i["name"] for i in saved["sinking_items"]] == ["Tết", "Học phí"]
    moved = sp.parse_known_items([{"name": "tết", "amount_vnd": 3_000_000, "needed_date": "2027-03-01"}], TODAY)
    with pytest.raises(ParamsError):
        propose(jars=jars, known_items=moved)


def test_known_items_must_be_after_today_and_within_twelve_months():
    def parse(day):
        return sp.parse_known_items([{"name": "Tết", "amount_vnd": 1, "needed_date": day}], TODAY)

    assert parse("2027-11-21")[0].needed_date == date(2027, 11, 21)
    for bad in ("2026-11-21", "2027-11-22"):
        with pytest.raises(ParamsError):
            parse(bad)
    with pytest.raises(ParamsError):
        sp.parse_known_items([{"name": "Tết", "amount_vnd": 0, "needed_date": "2027-01-01"}], TODAY)


# --- kiểm tra theo ngày và dòng xem trước ----------------------------------------------------------------
def test_period_checks_name_first_short_item_and_amount():
    dues = [
        (date(2026, 11, 26), "Tiền điện", 375_000),
        (date(2026, 12, 1), "Tiền trọ", 2_500_000),
        (date(2026, 12, 15), "Internet", 220_000),
    ]
    shares = [("chi_hang_ngay", Decimal(40)), ("nghia_vu", Decimal(35)), ("du_phong", Decimal(25))]
    checks = sp.period_checks(
        today=TODAY, payday_day=PAYDAY, salary_vnd=SALARY, shares=shares, jar_code="nghia_vu",
        jar_name="Nghĩa vụ", balance_vnd=500_000, dues=dues,
    )  # fmt: skip
    first, second = checks
    assert (first["payday"], first["due_vnd"], first["available_vnd"]) == ("2026-12-05", 2_875_000, 500_000)
    assert first["shortfall"] == {"label": "Tiền trọ", "date": "2026-12-01", "shortfall_vnd": 2_375_000}
    assert (second["payday"], second["available_vnd"], second["due_vnd"]) == ("2027-01-05", 3_150_000, 220_000)
    assert "shortfall" not in second
    pending = sp.period_checks(
        today=TODAY, payday_day=PAYDAY, salary_vnd=SALARY, shares=shares, jar_code="nghia_vu",
        jar_name="Nghĩa vụ", balance_vnd=500_000, dues=dues, pending_salary_vnd=SALARY,
    )  # fmt: skip
    assert pending[0]["available_vnd"] == 3_650_000 and "shortfall" not in pending[0]


def test_proposal_checks_use_proposed_shares_and_obligation_schedule():
    obs = [
        ob("Tiền trọ", 2_500_000),
        ob("Tiền điện", 375_000, kind="bill", due=date(2026, 11, 26), due_day=26),
    ]
    result = propose(obligations=obs)
    first, second = [c for c in result["checks"] if c["jar_code"] == "nghia_vu"]
    assert [i["label"] for i in first["items"]] == ["Tiền điện", "Tiền trọ"]
    assert first["shortfall"] == {"label": "Tiền điện", "date": "2026-11-26", "shortfall_vnd": 375_000}
    # kỳ kế tiếp: phần 32% lương (2.880.000) so với Tiền điện 26/12 và Tiền trọ 01/01
    assert second["available_vnd"] == 2_880_000 and second["due_vnd"] == 2_875_000
    assert "shortfall" not in second


def test_share_line_shows_share_amount_and_difference():
    assert sp.share_line(Decimal(33), Decimal(35), 2_970_000, 3_150_000) == (
        "33% · 2.970.000 ₫/kỳ",
        "35% · 3.150.000 ₫/kỳ (+180.000 ₫)",
    )
    assert sp.share_line(Decimal(42), Decimal("40.5"), 3_780_000, 3_645_000)[1] == (
        "40,5% · 3.645.000 ₫/kỳ (−135.000 ₫)"
    )
    assert sp.share_line(None, Decimal(12), None, 1_080_000) == (None, "12% · 1.080.000 ₫/kỳ")
    assert sp.jar_amounts(SALARY, [("a", 33), ("b", 33), ("c", 33)]) is None  # tổng khác 100


def test_legacy_wallet_without_purpose_keeps_saved_source_and_takes_from_non_essential_spending():
    jars = legacy_jars()
    obs = [ob("Tiền trọ", 2_500_000, pay="hoa_don"), ob("Khoản vay", 900_000, kind="loan")]
    result = propose(jars=jars, obligations=obs, essential_jars=essential(jars))
    assert result["obligations_monthly_vnd"] == 900_000  # tiền trọ trả từ Hóa đơn (nguồn đã lưu)
    shares = after(result)
    # BR-21, BR-54: phần chênh lấy từ hũ chi không thiết yếu (Giải trí), không cắt Ăn uống
    assert (shares["nghia_vu"], shares["giai_tri"], shares["an_uong"]) == (10, 5, 25)
    assert shares["du_phong"] == 15 and shares["hoa_don"] == 30


# --- nguồn bù trên ví không có Chi hằng ngày (BR-21, BR-54): hũ chi không thiết yếu trước, thiết yếu sau cùng ----------------------
def _seed_tx_types():
    """Bảng tra loại giao dịch thật của sản phẩm (`db/seed/tx_type_map.sql`), không dựng tay."""
    import re
    from pathlib import Path

    from yofina_core.params import TxTypeInfo

    sql = (Path(__file__).resolve().parents[2] / "db" / "seed" / "tx_type_map.sql").read_text(encoding="utf-8")
    values = sql.split("VALUES", 1)[1].split("ON CONFLICT", 1)[0]
    out = {}
    for ln in values.splitlines():
        if not re.match(r"\s*\('", ln):
            continue
        tx_type, _label, direction, jar_code, role, *_ = re.findall(r"'[^']*'|[A-Za-z0-9_]+", ln)
        unq = lambda s: None if s == "NULL" else s.strip("'")  # noqa: E731
        out[unq(tx_type)] = TxTypeInfo(unq(tx_type), unq(direction), unq(jar_code), unq(role))
    return out


TX_TYPES = _seed_tx_types()
CATEGORIES = sp.DEFAULT_ESSENTIAL_CATEGORIES


def essential(jars):
    return sp.essential_spending_jars(jars, TX_TYPES, CATEGORIES)


def demo_jars():
    """Bộ hũ demo (issue #39) theo `jar_layout.DEMO_LAYOUT`, tỷ lệ của `minh`."""
    return [
        jar("an_uong", "spending", 30, sort_order=10),
        jar("di_lai", "spending", 7, sort_order=20),
        jar("nghia_vu", "obligation", 36, sort_order=30),
        jar("giai_tri", "spending", 7, sort_order=40),
        jar("muc_tieu", "saving", 10, "goal", goal_vnd=6_000_000, goal_date=date(2027, 4, 1), sort_order=50),
        jar("du_phong", "saving", 10, "buffer", sort_order=60),
        jar("dau_tu", "saving", 0, "long_term", sort_order=70),
    ]


def demo_daily_jars():
    """Bộ hũ demo từ 26/11 (issue #39) theo `jar_layout.DEMO_LAYOUT`, tỷ lệ của `minh`: ba hũ mặc định (Chi hằng ngày 3 điểm lấy từ
    Nghĩa vụ) rồi hũ tự thêm."""
    return [
        jar("chi_hang_ngay", "spending", 3, sort_order=10),
        jar("nghia_vu", "obligation", 33, sort_order=20),
        jar("du_phong", "saving", 10, "buffer", sort_order=30),
        jar("an_uong", "spending", 30, sort_order=40),
        jar("di_lai", "spending", 7, sort_order=50),
        jar("giai_tri", "spending", 7, sort_order=60),
        jar("muc_tieu", "saving", 10, "goal", goal_vnd=6_000_000, goal_date=date(2027, 4, 1), sort_order=70),
        jar("dau_tu", "saving", 0, "long_term", sort_order=80),
    ]


def test_essential_spending_jars_on_wallet_with_daily_jar_and_own_category_jars():
    """Ví có cả hũ chung lẫn hũ riêng: loại ăn uống, đi lại vào hũ riêng nên Chi hằng ngày không nhận loại thiết yếu nào (không bị
    coi là hũ thiết yếu); ví ba hũ người dùng thêm Giải trí, Mục tiêu thì Chi hằng ngày chỉ còn nhận ăn uống, đi lại nên thiết yếu."""
    assert essential(demo_daily_jars()) == {"an_uong", "di_lai"}
    with_food = [*three(), jar("an_uong", "spending", 0)]
    assert essential(with_food) == {"an_uong"}  # Chi hằng ngày còn nhận đi lại và giải trí: hũ trộn
    added = [*three(), jar("giai_tri", "spending", 0), jar("muc_tieu", "saving", 0, "goal")]
    assert essential(added) == {"chi_hang_ngay"}


@pytest.mark.parametrize(
    ("rent", "expected"),
    [
        # 39%: +6 điểm, Chi hằng ngày (không thiết yếu, hũ chung đứng đầu) về 0 trước, rồi Giải trí
        (3_000_000, {"chi_hang_ngay": 0, "giai_tri": 4, "an_uong": 30, "di_lai": 7, "muc_tieu": 10, "du_phong": 10,
                     "nghia_vu": 39}),
        # 53%: hết hũ chi không thiết yếu, Dự phòng giữ sàn 10, rồi hũ mục tiêu; Ăn uống, Đi lại giữ nguyên
        (4_400_000, {"chi_hang_ngay": 0, "giai_tri": 0, "an_uong": 30, "di_lai": 7, "muc_tieu": 0, "du_phong": 10,
                     "nghia_vu": 53}),
        # 69%: hết nguồn không thiết yếu mới tới hũ chi thiết yếu (Ăn uống trước Đi lại theo thứ tự hũ)
        (6_000_000, {"chi_hang_ngay": 0, "giai_tri": 0, "an_uong": 14, "di_lai": 7, "muc_tieu": 0, "du_phong": 10,
                     "nghia_vu": 69}),
    ],
)  # fmt: skip
def test_demo_daily_wallet_takes_from_non_essential_first_and_essential_last(rent, expected):
    jars = demo_daily_jars()
    obs = [ob("Tiền nhà", rent, pay="nghia_vu"), ob("Khoản vay", 900_000, kind="loan")]
    result = propose(jars=jars, obligations=obs, salary_vnd=10_000_000, essential_jars=essential(jars))
    assert result["status"] == "proposed"
    shares = after(result)
    assert {k: shares[k] for k in expected} == expected
    assert shares["dau_tu"] == 0 and sum(shares.values()) == 100


def test_demo_daily_wallet_excess_returns_to_daily_jar():
    jars = demo_daily_jars()
    obs = [ob("Tiền nhà", 2_000_000, pay="nghia_vu"), ob("Khoản vay", 900_000, kind="loan")]
    result = propose(jars=jars, obligations=obs, salary_vnd=10_000_000, essential_jars=essential(jars))
    shares = after(result)  # 29%: 4 điểm thừa về hũ chi đầu tiên là hũ chung Chi hằng ngày, hũ riêng giữ nguyên
    assert (shares["nghia_vu"], shares["chi_hang_ngay"], shares["an_uong"], shares["giai_tri"]) == (29, 7, 30, 7)


def legacy_jars():
    return [
        jar("an_uong", "spending", 25, sort_order=10),
        jar("di_lai", "spending", 10, sort_order=20),
        jar("hoa_don", "spending", 30, sort_order=30),
        jar("giai_tri", "spending", 10, sort_order=40),
        jar("du_lich", "saving", 5, goal_vnd=6_000_000, sort_order=50),
        jar("du_phong", "saving", 15, sort_order=60),
        jar("nghia_vu", "obligation", 5, sort_order=70),
    ]


def test_essential_spending_jars_follow_transaction_types_not_codes():
    # hũ chi chỉ nhận loại giao dịch thiết yếu (ăn uống, đi lại, hóa đơn) là thiết yếu; hũ trộn (Chi hằng ngày nhận cả giải trí)
    # và hũ giải trí thì không
    assert essential(demo_jars()) == {"an_uong", "di_lai"}
    assert essential(legacy_jars()) == {"an_uong", "di_lai", "hoa_don"}
    assert essential(three()) == set()
    renamed = [jar("an_uong", "spending", 50), jar("nghia_vu", "obligation", 50)]
    assert essential(renamed) == {"an_uong"}


@pytest.mark.parametrize(
    ("rent", "expected"),
    [
        # 3.900.000 = 39%: +3 điểm từ Giải trí
        (3_000_000, {"giai_tri": 4, "an_uong": 30, "di_lai": 7, "muc_tieu": 10, "du_phong": 10, "nghia_vu": 39}),
        # 53%: Giải trí về 0, Dự phòng giữ sàn 10, rồi hũ mục tiêu; Ăn uống, Đi lại giữ nguyên
        (4_400_000, {"giai_tri": 0, "an_uong": 30, "di_lai": 7, "muc_tieu": 0, "du_phong": 10, "nghia_vu": 53}),
        # 69%: hết nguồn không thiết yếu mới tới hũ thiết yếu (hũ chi đầu tiên trước)
        (6_000_000, {"giai_tri": 0, "an_uong": 14, "di_lai": 7, "muc_tieu": 0, "du_phong": 10, "nghia_vu": 69}),
    ],
)
def test_demo_wallet_takes_from_non_essential_spending_then_savings_then_essential(rent, expected):
    jars = demo_jars()
    obs = [ob("Tiền nhà", rent, pay="nghia_vu"), ob("Khoản vay", 900_000, kind="loan")]
    result = propose(jars=jars, obligations=obs, salary_vnd=10_000_000, essential_jars=essential(jars))
    assert result["status"] == "proposed"
    shares = after(result)
    assert {k: shares[k] for k in expected} == expected
    assert shares["dau_tu"] == 0 and sum(shares.values()) == 100


def test_demo_wallet_excess_returns_to_first_spending_jar_as_before():
    jars = demo_jars()
    obs = [ob("Tiền nhà", 2_000_000, pay="nghia_vu"), ob("Khoản vay", 900_000, kind="loan")]
    result = propose(jars=jars, obligations=obs, salary_vnd=10_000_000, essential_jars=essential(jars))
    shares = after(result)  # 29%: 7 điểm thừa về hũ chi đầu tiên (như trước), không về Giải trí
    assert (shares["nghia_vu"], shares["an_uong"], shares["giai_tri"]) == (29, 37, 7)


def test_three_jar_wallet_keeps_daily_then_buffer():
    jars = three()
    for rent, expected in (
        (2_500_000, {"chi_hang_ngay": 47, "nghia_vu": 28, "du_phong": 25}),
        (8_100_000, {"chi_hang_ngay": 0, "nghia_vu": 90, "du_phong": 10}),
    ):
        result = propose(jars=jars, obligations=[ob("Tiền trọ", rent)], essential_jars=essential(jars))
        assert after(result) == expected
        assert after(result) == after(propose(jars=jars, obligations=[ob("Tiền trọ", rent)]))
