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


def test_period_checks_khoan_dung_ngay_luong_thuoc_ky_truoc_tra_bang_so_du_truoc_luong():
    """Cửa sổ chung `due_before_payday` (BR-22, #39): khoản đến hạn ĐÚNG ngày lương 05/12 thuộc kỳ hiện tại và trả bằng số dư trước khi lương
    05/12 về; khoản 06/12 thuộc kỳ kế; khoản đúng ngày lương 05/01 thuộc kỳ kế (trước lương 05/01). Không khoản nào tính hai lần."""
    dues = [
        (date(2026, 12, 5), "Trả sau", 1_200_000),
        (date(2026, 12, 6), "Tiền trọ", 2_000_000),
        (date(2027, 1, 5), "Trả sau", 300_000),
        (date(2027, 1, 6), "Tiền trọ", 2_000_000),
    ]
    shares = [("chi_hang_ngay", Decimal(40)), ("nghia_vu", Decimal(35)), ("du_phong", Decimal(25))]
    first, second = sp.period_checks(
        today=TODAY, payday_day=PAYDAY, salary_vnd=SALARY, shares=shares, jar_code="nghia_vu",
        jar_name="Nghĩa vụ", balance_vnd=1_000_000, dues=dues,
    )  # fmt: skip
    assert [i["date"] for i in first["items"]] == ["2026-12-05"]
    assert (first["due_vnd"], first["available_vnd"]) == (1_200_000, 1_000_000)
    assert first["shortfall"] == {"label": "Trả sau", "date": "2026-12-05", "shortfall_vnd": 200_000}
    assert [i["date"] for i in second["items"]] == ["2026-12-06", "2027-01-05"]
    assert (second["due_vnd"], second["available_vnd"]) == (2_300_000, 3_150_000)
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


# --- sàn của hũ có khoản định kỳ trả từ chính nó (#39, 26/11): mọi hũ, không theo mã ----------------------------------------------
def minh_obligations():
    """Nghĩa vụ đã khai của `minh` (spec persona, không chép tay), hũ trả theo bộ hũ demo (`LEGACY_JAR_ALIASES`, như đặt lại): tiền nhà
    và hóa đơn từ Nghĩa vụ, Netflix từ Giải trí, Tiền cơm văn phòng từ Ăn uống."""
    import json
    from pathlib import Path

    from yofina_core.wallet import LEGACY_JAR_ALIASES

    spec = Path(__file__).resolve().parents[2] / "data" / "personas" / "specs" / "minh.json"
    rows = json.loads(spec.read_text(encoding="utf-8"))["obligations"]
    return [
        ob(o["name"], o["amount_vnd"], kind=o["kind"], due_day=o["due_day"], essential=o["is_essential"],
           pay=LEGACY_JAR_ALIASES.get(o["pay_jar"], o["pay_jar"]))
        for o in rows
    ]  # fmt: skip


def test_minh_demo_obligations_are_paid_from_their_own_jars():
    by_jar = {}
    for o in minh_obligations():
        by_jar.setdefault(o["pay_jar_code"], []).append((o["name"], int(o["amount_vnd"])))
    assert by_jar["giai_tri"] == [("Netflix", 180_000)]  # 2% lương 9.000.000
    assert by_jar["an_uong"] == [("Tiền cơm văn phòng", 300_000)]  # 3,33% -> sàn 4%


@pytest.mark.parametrize(
    ("loan", "expected"),
    [
        # nhu cầu 29,94% -> 30: thừa 3 điểm về Chi hằng ngày, không hũ nào bị lấy nên sàn không đổi gì
        (None, {"chi_hang_ngay": 6, "giai_tri": 7, "an_uong": 30, "di_lai": 7, "muc_tieu": 10, "du_phong": 10,
                "nghia_vu": 30}),
        # 49,94% -> 50, +17 điểm: Giải trí giữ 2% cho Netflix (trước: về 0), phần còn lại lấy từ hũ mục tiêu
        (1_800_000, {"chi_hang_ngay": 0, "giai_tri": 2, "an_uong": 30, "di_lai": 7, "muc_tieu": 1, "du_phong": 10,
                     "nghia_vu": 50}),
        # 79,94% -> 80, +47 điểm: Ăn uống giữ 4% cho Tiền cơm văn phòng (trước: còn 3%), phần thiếu lấy tiếp từ Đi lại
        (4_500_000, {"chi_hang_ngay": 0, "giai_tri": 2, "an_uong": 4, "di_lai": 4, "muc_tieu": 0, "du_phong": 10,
                     "nghia_vu": 80}),
    ],
)  # fmt: skip
def test_minh_demo_wallet_keeps_each_jar_above_obligations_it_pays(loan, expected):
    jars = demo_daily_jars()
    obs = minh_obligations() + ([ob("Khoản vay", loan, kind="loan")] if loan else [])
    result = propose(jars=jars, obligations=obs, essential_jars=essential(jars))
    assert result["status"] == "proposed"
    shares = after(result)
    assert {k: shares[k] for k in expected} == expected
    assert shares["dau_tu"] == 0 and sum(shares.values()) == 100
    assert params_split(result) == shares


def test_minh_demo_wallet_is_infeasible_when_only_cutting_committed_jars_would_fit():
    # 89,94% -> 90 + sàn Dự phòng 10 + Netflix 2 + Tiền cơm văn phòng 4 = 106: trước đây "vừa" 100% bằng cách đưa Giải trí, Ăn uống
    # về 0 (khoản định kỳ của hai hũ đó không còn tiền trả); nay không đề xuất và liệt kê nghĩa vụ theo thứ tự ưu tiên
    jars = demo_daily_jars()
    obs = [*minh_obligations(), ob("Khoản vay", 5_400_000, kind="loan")]
    result = propose(jars=jars, obligations=obs, essential_jars=essential(jars))
    assert result["status"] == "infeasible"
    assert result["required_percent"] == 106
    assert "params" not in result
    assert [o["name"] for o in result["priority_obligations"]][-2:] == ["Netflix", "Tiền cơm văn phòng"]


def test_three_jar_wallet_keeps_daily_jar_above_obligation_it_pays():
    # khoản định kỳ người dùng chọn trả từ Chi hằng ngày: 300.000 = 3,33% -> sàn 4; nhu cầu 83,33% -> 84, +51 điểm
    jars = three()
    obs = [ob("Tiền trọ", 7_500_000), ob("Gửi xe tháng", 300_000, kind="bill", pay="chi_hang_ngay")]
    result = propose(jars=jars, obligations=obs, essential_jars=essential(jars))
    assert after(result) == {"chi_hang_ngay": 4, "nghia_vu": 84, "du_phong": 12}  # trước: 0 / 84 / 16
    # cùng tiền trọ mà không có khoản nào trả từ Chi hằng ngày: như trước
    plain = propose(jars=jars, obligations=[ob("Tiền trọ", 7_500_000)], essential_jars=essential(jars))
    assert after(plain) == {"chi_hang_ngay": 0, "nghia_vu": 84, "du_phong": 16}


def test_three_jar_wallet_below_committed_floor_is_infeasible_not_cut():
    jars = three()
    obs = [ob("Tiền trọ", 7_800_000), ob("Gửi xe tháng", 300_000, kind="bill", pay="chi_hang_ngay")]
    result = propose(jars=jars, obligations=obs, essential_jars=essential(jars))
    assert result["status"] == "infeasible" and result["required_percent"] == 101  # 87 + sàn Dự phòng 10 + 4


def test_legacy_wallet_keeps_entertainment_above_its_subscription():
    jars = legacy_jars()
    obs = [
        ob("Tiền trọ", 2_500_000, pay="hoa_don"),
        ob("Khoản vay", 900_000, kind="loan"),
        ob("Netflix", 600_000, kind="subscription", essential=False, pay="giai_tri"),  # 6,67% -> sàn 7
    ]
    result = propose(jars=jars, obligations=obs, essential_jars=essential(jars))
    shares = after(result)
    # trước: Giải trí 10 -> 5; nay giữ 7, 2 điểm còn lại lấy từ Dự phòng (ví cũ, `purpose` NULL) xuống không dưới sàn 10
    assert (shares["nghia_vu"], shares["giai_tri"], shares["du_phong"], shares["an_uong"]) == (10, 7, 13, 25)
    assert shares["hoa_don"] == 30 and shares["du_lich"] == 5


def test_committed_floor_keeps_a_jar_already_below_it_and_never_raises_it():
    jars = [jar("chi_hang_ngay", "spending", 1), jar("nghia_vu", "obligation", 33), jar("du_phong", "saving", 65, "buffer"),
            jar("giai_tri", "spending", 1)]  # fmt: skip
    obs = [ob("Tiền trọ", 3_240_000), ob("Netflix", 180_000, kind="subscription", essential=False, pay="giai_tri")]
    shares = after(propose(jars=jars, obligations=obs, essential_jars=essential(jars)))
    # +3 điểm: Giải trí đang 1% (dưới sàn 2%) không bị lấy thêm và cũng không được nâng; trước: Giải trí về 0, Dự phòng 64
    assert shares == {"chi_hang_ngay": 0, "nghia_vu": 36, "du_phong": 63, "giai_tri": 1}


# --- sàn chi theo mức chi thật gần đây (#39, quyết định 26/11 chiều): hũ chi không thiết yếu không bị lấy dưới tỷ lệ giữ x mức chi
# điển hình của chính nó, trừ khi nghĩa vụ không còn chỗ nào khác; cùng nguồn số và tham số với LP phân bổ ---------------------------
#: mức chi đo trên ví demo `minh` sau "Đặt lại" (tests/local_pg/test_demo_scenes.py -s): mức nền bền (trung vị chi theo tuần trên 12 tuần),
#: mức gốc của sàn chi từ 26/11 tối. Chi 30 ngày gần nhất là 210.000 ₫ và 409.000 ₫ (mức gốc trước đó); điểm lương làm tròn lên không đổi
MINH_TYPICAL = {"chi_hang_ngay": 190_714, "giai_tri": 390_000}


def spend_floors(typical, ratio=0.5):
    return {code: round(ratio * value) for code, value in typical.items()}


def context(spend_by_jar, *, days=30, kinds=None):
    """Dòng như `app_get_forecast_context` (phần meta và hũ) với `days` ngày lịch sử."""
    from datetime import timedelta

    rows = [{"section": "meta", "jar_code": None,
             "payload": {"app_date": TODAY.isoformat(), "history_start": (TODAY - timedelta(days=days)).isoformat()}}]
    for code, series in spend_by_jar.items():
        kind = (kinds or {}).get(code, "spending")
        rows.append({"section": "jar", "jar_code": code, "payload": {"code": code, "kind": kind, "spend": series}})
    return rows  # fmt: skip


SPEND = sp.SpendFloorSettings(keep_ratio=0.5, window_days=30, month_days=30, min_history_days=21)


def test_san_chi_tinh_tu_muc_nen_ben_cung_ham_voi_lp():
    """Sàn chi của đề xuất tỷ lệ = tỷ lệ giữ x mức nền bền của hũ (#39, chốt 26/11 tối): CÙNG hàm `yofina_core.spend_baseline.typical_monthly`
    và cùng tham số mặc định với LP phân bổ, không chép công thức. Đợt chi tăng hai tuần không kéo sàn lên; chưa đủ sáu tuần thì như
    trước (chi trung bình 30 ngày gần nhất)."""
    from yofina_core.spend_baseline import typical_monthly
    from yofina_forecast.resilience import variable_monthly_spend

    spike = [120_000] * 70 + [378_571] * 14  # mười hai tuần, hai tuần cuối gấp khoảng 3,15 lần
    floors = sp.spending_floors_vnd(context({"giai_tri": spike, "an_uong": [90_000] * 84}, days=84), SPEND)
    assert floors["giai_tri"] == round(0.5 * typical_monthly(spike, SPEND.baseline).monthly_vnd) == round(0.5 * 3_600_000)
    assert round(0.5 * variable_monthly_spend(spike, 30, 30)) > 2 * floors["giai_tri"]  # cách cũ: theo đợt tăng
    assert floors["an_uong"] == round(0.5 * 90_000 * 30)
    short = [120_000] * 21 + [378_571] * 14  # năm tuần
    assert sp.spending_floors_vnd(context({"giai_tri": short}, days=35), SPEND) == {
        "giai_tri": round(0.5 * variable_monthly_spend(short, 30, 30))
    }
    # đọc đủ cửa sổ mức nền (12 tuần), không chỉ 30 ngày như trước
    assert SPEND.context_window_days == 84


def test_san_chi_chi_cho_hu_chi_va_khi_du_lich_su():
    rows = context({"giai_tri": [10_000] * 30, "du_phong": [5_000] * 30, "nghia_vu": [7_000] * 30},
                   kinds={"du_phong": "saving", "nghia_vu": "obligation"})  # fmt: skip
    assert sp.spending_floors_vnd(rows, SPEND) == {"giai_tri": 150_000}
    # cùng cổng "ước lượng ban đầu" của dự báo: dưới `min_history_days` ngày lịch sử thì chưa có mức chi điển hình
    assert sp.spending_floors_vnd(context({"giai_tri": [10_000] * 20}, days=20), SPEND) == {}
    assert sp.spending_floors_vnd(context({"giai_tri": [10_000] * 21}, days=21), SPEND) == {"giai_tri": 150_000}
    assert sp.spending_floors_vnd([], SPEND) == {}


def test_tham_so_san_chi_cung_mac_dinh_voi_bo_toi_uu_va_doc_tu_cau_hinh():
    import re
    from dataclasses import fields
    from pathlib import Path

    from yofina_core.config import Config
    from yofina_forecast.settings import DEFAULT_ALLOCATION_PARAMS, ForecastSettings

    window = next(f.default for f in fields(ForecastSettings) if f.name == "resilience_window_days")
    cdk = (Path(__file__).resolve().parents[2] / "infra-cdk" / "lib" / "forecast-pipeline.ts").read_text(encoding="utf-8")
    cold = int(re.search(r"'forecastColdStartMinDays',\s*(\d+)", cdk).group(1))
    base = sp.SpendFloorSettings.from_config(Config(env={}))
    assert base == sp.SpendFloorSettings(DEFAULT_ALLOCATION_PARAMS.spending_keep_ratio, window,
                                         DEFAULT_ALLOCATION_PARAMS.month_days, cold)  # fmt: skip
    # cửa sổ mức nền bền: cùng mặc định với LP (`spend_baseline_weeks`, `spend_baseline_min_weeks`)
    assert (base.baseline_weeks, base.baseline_min_weeks) == (
        DEFAULT_ALLOCATION_PARAMS.spend_baseline_weeks, DEFAULT_ALLOCATION_PARAMS.spend_baseline_min_weeks,
    )  # fmt: skip
    over = sp.SpendFloorSettings.from_config(Config(env={
        "YOFINA_ALLOCATION_SPENDING_KEEP_RATIO": "0.7", "YOFINA_RESILIENCE_WINDOW_DAYS": "14",
        "YOFINA_ALLOCATION_MONTH_DAYS": "31", "YOFINA_FORECAST_COLD_START_MIN_DAYS": "10",
        "YOFINA_ALLOCATION_SPEND_BASELINE_WEEKS": "8", "YOFINA_ALLOCATION_SPEND_BASELINE_MIN_WEEKS": "4",
    }))  # fmt: skip
    assert over == sp.SpendFloorSettings(0.7, 14, 31, 10, baseline_weeks=8, baseline_min_weeks=4)
    assert over.context_window_days == 56
    with pytest.raises(ValueError):
        sp.SpendFloorSettings.from_config(Config(env={"YOFINA_ALLOCATION_SPEND_BASELINE_MIN_WEEKS": "13"}))


@pytest.mark.parametrize(
    ("loan", "expected"),
    [
        # +17 điểm: Chi hằng ngày xuống tới sàn chi 2% (105.000 ₫), Giải trí tới 3% (204.500 ₫, trên Netflix 2%), rồi hũ mục tiêu về 0;
        # vẫn thiếu 2 điểm nên sàn chi của Chi hằng ngày nhường (nghĩa vụ trước). Trước: Giải trí 2, Mục tiêu 1
        (1_800_000, {"chi_hang_ngay": 0, "giai_tri": 3, "an_uong": 30, "di_lai": 7, "muc_tieu": 0, "du_phong": 10,
                     "nghia_vu": 50}),
        # +7 điểm: Chi hằng ngày nhường 1 điểm tới sàn chi, Giải trí 4 điểm tới sàn chi 3%, rồi hũ mục tiêu 2 điểm (trước: Chi hằng ngày
        # về 0, Giải trí 3, hũ mục tiêu giữ 10)
        (900_000, {"chi_hang_ngay": 2, "giai_tri": 3, "an_uong": 30, "di_lai": 7, "muc_tieu": 8, "du_phong": 10,
                   "nghia_vu": 40}),
    ],
)  # fmt: skip
def test_minh_demo_wallet_keeps_spending_floor_before_goal_jar(loan, expected):
    jars = demo_daily_jars()
    obs = [*minh_obligations(), ob("Khoản vay", loan, kind="loan")]
    result = propose(jars=jars, obligations=obs, essential_jars=essential(jars), spend_floor_vnd=spend_floors(MINH_TYPICAL))
    assert result["status"] == "proposed"
    shares = after(result)
    assert {k: shares[k] for k in expected} == expected
    assert shares["dau_tu"] == 0 and sum(shares.values()) == 100 and params_split(result) == shares


def test_minh_demo_wallet_spending_floor_never_makes_proposal_infeasible():
    # 89,94% -> 90: như khi chưa có sàn chi, "chưa khả thi" chỉ vì sàn Dự phòng và khoản định kỳ, không vì sàn chi
    jars = demo_daily_jars()
    obs = [*minh_obligations(), ob("Khoản vay", 5_400_000, kind="loan")]
    with_floor = propose(jars=jars, obligations=obs, essential_jars=essential(jars), spend_floor_vnd=spend_floors(MINH_TYPICAL))
    assert with_floor["status"] == "infeasible" and with_floor["required_percent"] == 106
    # khoản vay 4.500.000 ₫ (80%): vẫn đề xuất được, sàn chi nhường hết cho nghĩa vụ trước khi lấy tới hũ chi thiết yếu
    obs = [*minh_obligations(), ob("Khoản vay", 4_500_000, kind="loan")]
    plain = after(propose(jars=jars, obligations=obs, essential_jars=essential(jars)))
    floored = after(propose(jars=jars, obligations=obs, essential_jars=essential(jars), spend_floor_vnd=spend_floors(MINH_TYPICAL)))
    assert floored == plain


@pytest.mark.parametrize(
    ("rent", "expected"),
    [
        # 70%, +37: Chi hằng ngày (cả hũ, chi điển hình 3.000.000 ₫ -> sàn chi 17%) nhường tới sàn chi, phần còn lại lấy từ Dự phòng
        # (trước: Chi hằng ngày 5, Dự phòng 25)
        (6_300_000, {"chi_hang_ngay": 17, "nghia_vu": 70, "du_phong": 13}),
        # 84%, +51: Dự phòng xuống sàn 10 rồi sàn chi của Chi hằng ngày mới nhường (trước: 0 / 84 / 16)
        (7_500_000, {"chi_hang_ngay": 6, "nghia_vu": 84, "du_phong": 10}),
    ],
)
def test_three_jar_wallet_daily_jar_keeps_spending_floor_until_buffer_floor(rent, expected):
    jars = three()
    result = propose(jars=jars, obligations=[ob("Tiền trọ", rent)], essential_jars=essential(jars),
                     spend_floor_vnd={"chi_hang_ngay": 1_500_000})  # fmt: skip
    assert after(result) == expected


def test_legacy_wallet_entertainment_keeps_larger_of_subscription_and_spending_floor():
    jars = legacy_jars()
    obs = [
        ob("Tiền trọ", 2_500_000, pay="hoa_don"),
        ob("Khoản vay", 900_000, kind="loan"),
        ob("Netflix", 600_000, kind="subscription", essential=False, pay="giai_tri"),  # 6,67% -> 7
    ]
    # Giải trí chi điển hình 1.500.000 ₫/tháng: sàn chi 750.000 ₫ = 8,33% -> 9 (trên Netflix 7); Dự phòng nhường 4 điểm (trước: 7 / 13)
    result = propose(jars=jars, obligations=obs, essential_jars=essential(jars), spend_floor_vnd={"giai_tri": 750_000})
    shares = after(result)
    assert (shares["nghia_vu"], shares["giai_tri"], shares["du_phong"], shares["an_uong"]) == (10, 9, 11, 25)
    assert shares["hoa_don"] == 30 and shares["du_lich"] == 5


def test_spending_floor_keeps_a_jar_already_below_it_and_never_raises_it():
    jars = [jar("chi_hang_ngay", "spending", 1), jar("nghia_vu", "obligation", 33), jar("du_phong", "saving", 65, "buffer"),
            jar("giai_tri", "spending", 1)]  # fmt: skip
    shares = after(propose(jars=jars, obligations=[ob("Tiền trọ", 3_240_000)], essential_jars=essential(jars),
                           spend_floor_vnd={"chi_hang_ngay": 450_000, "giai_tri": 450_000}))  # fmt: skip
    # +3 điểm, sàn chi 5% của hai hũ đang 1%: không bị lấy thêm cũng không được nâng; Dự phòng nhường
    assert shares == {"chi_hang_ngay": 1, "nghia_vu": 36, "du_phong": 62, "giai_tri": 1}


def test_no_spending_history_keeps_previous_behaviour():
    jars = demo_daily_jars()
    obs = [*minh_obligations(), ob("Khoản vay", 1_800_000, kind="loan")]
    base = propose(jars=jars, obligations=obs, essential_jars=essential(jars))
    assert propose(jars=jars, obligations=obs, essential_jars=essential(jars), spend_floor_vnd={}) == base
    assert (after(base)["chi_hang_ngay"], after(base)["giai_tri"], after(base)["muc_tieu"]) == (0, 2, 1)
