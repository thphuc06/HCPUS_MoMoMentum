"""Bộ sinh persona: tất định, số dư khớp bảng số Figma §5, sổ cái nhất quán, đồng hồ mô phỏng."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from conftest import REPO

from personas import (
    PersonaError,
    available_personas,
    generate,
    load_accounts,
    materialize,
    parse_groups_claim,
    persona_from_groups,
)

ANCHOR = date(2026, 11, 21)
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = datetime(2026, 12, 10, 3, 0, tzinfo=UTC)  # ngày thật 10/12 -> offset -19

# Bảng số Figma §5 (ngày 21/11/2026). Số này là KỲ VỌNG của test, không nằm trong mã sản phẩm.
FIGMA_BALANCES = {
    "an_uong": 380_000,
    "di_lai": 640_000,
    "hoa_don": 450_000,
    "giai_tri": 760_000,
    "du_lich": 1_800_000,
    "du_phong": 2_700_000,
    "nghia_vu": 1_000_000,
}
FIGMA_SPLIT = {
    "hoa_don": 31,
    "an_uong": 30,
    "di_lai": 7,
    "giai_tri": 7,
    "du_lich": 10,
    "du_phong": 10,
    "nghia_vu": 5,
}


def test_co_ba_persona():
    assert available_personas() == ["khoa", "lan", "minh"]


def test_minh_khop_bang_so_figma():
    d = generate("minh", anchor=ANCHOR)
    assert d.monthly_salary_vnd == 9_000_000 and d.payday_day == 5
    assert {j.code: j.balance_vnd for j in d.jars} == FIGMA_BALANCES
    assert sum(j.balance_vnd for j in d.jars) == 7_730_000
    assert {j.code: int(j.split_percent) for j in d.jars} == FIGMA_SPLIT
    assert [j.code for j in d.jars] == [
        "an_uong",
        "di_lai",
        "hoa_don",
        "giai_tri",
        "du_lich",
        "du_phong",
        "nghia_vu",
    ]
    assert 100 <= len(d.transactions) <= 200  # lịch sử đủ dày cho dự báo


@pytest.mark.parametrize("name", ["minh", "lan", "khoa"])
def test_tat_dinh_cung_seed_cung_ket_qua(name):
    assert generate(name, anchor=ANCHOR) == generate(name, anchor=ANCHOR)


def test_seed_khac_cho_ket_qua_khac_nhung_van_khop_so_du():
    a = generate("minh", anchor=ANCHOR)
    b = generate("minh", anchor=ANCHOR, seed=1)
    assert a.transactions != b.transactions
    assert {j.code: j.balance_vnd for j in b.jars} == FIGMA_BALANCES


@pytest.mark.parametrize("name", ["minh", "lan", "khoa"])
def test_so_cai_nhat_quan_so_du_bang_tong_dong_tra_bang_hu_va_khong_bao_gio_am(name):
    d = generate(name, anchor=ANCHOR)
    by_jar: dict[str, list] = defaultdict(list)
    for t in d.transactions:
        if t.funding_source == "jar":
            by_jar[t.jar_code].append(t)
    for jar in d.jars:
        bal = 0
        for t in sorted(by_jar[jar.code], key=lambda t: (-t.days_ago, t.local_time)):
            bal += t.amount_vnd
            assert bal >= 0, (jar.code, t)
        assert bal == jar.balance_vnd
    for code, expected in d.system_balances.items():
        assert sum(t.amount_vnd for t in by_jar[code]) == expected
    keys = [t.key for t in d.transactions]
    assert len(keys) == len(set(keys))
    for t in d.transactions:
        assert t.amount_vnd != 0 and 1 <= t.days_ago <= d.history_days
        assert t.kind in {"income", "expense", "transfer"}
        assert t.kind != "expense" or t.amount_vnd < 0
        assert t.kind != "income" or t.amount_vnd > 0
        assert t.merchant is None or len(t.merchant) <= 120
        assert t.tx_type
    # mỗi nhóm chuyển có tổng bằng 0, trừ số dư đầu kỳ (một phía)
    groups: dict[str, int] = defaultdict(int)
    sizes: dict[str, int] = defaultdict(int)
    for t in d.transactions:
        if t.transfer_key:
            groups[t.transfer_key] += t.amount_vnd
            sizes[t.transfer_key] += 1
    assert all(total == 0 or sizes[k] == 1 for k, total in groups.items())


def test_minh_hai_hu_he_thong_va_khoan_tra_sau_khop_hop_dong():
    d = generate("minh", anchor=ANCHOR)
    assert d.system_balances == {"tien_vao_khac": 350_000, "chua_phan_loai": -180_000}
    assert sum(j.balance_vnd for j in d.jars) == 7_730_000  # tổng bảy hũ thường giữ nguyên
    # chi chưa xếp hũ là KHOẢN CHI (số âm), cần xem lại
    uncl = [t for t in d.transactions if t.jar_code == "chua_phan_loai"]
    assert sum(t.amount_vnd for t in uncl) == -180_000
    assert all(t.kind == "expense" and t.needs_review for t in uncl)
    assert d.bnpl_principal_vnd == 967_000 and d.credit_limit_vnd == 5_000_000
    assert d.credit_due_day == 5
    credit = [t for t in d.transactions if t.funding_source == "credit"]
    assert sum(-t.amount_vnd for t in credit) == 967_000
    assert {j.code: j.kind for j in d.jars}["nghia_vu"] == "obligation"
    du_lich = next(j for j in d.jars if j.code == "du_lich")
    assert du_lich.goal_vnd == 6_000_000 and du_lich.goal_date == date(2027, 4, 1)
    assert [p.name for p in d.payees if p.is_favorite][:1] == ["Trần Quang Huy"]
    assert {o.name for o in d.obligations} >= {"Tiền thuê phòng", "Tiền điện", "Internet FPT"}


def test_khoan_tra_nghia_vu_trong_lich_su_gan_obligation_va_dung_han_tung_thang():
    d = generate("minh", anchor=ANCHOR)
    rent = next(o for o in d.obligations if o.kind == "rent")
    paid = [t for t in d.transactions if t.obligation_key == rent.key]
    days = [(ANCHOR - timedelta(days=t.days_ago)).isoformat() for t in paid]
    assert sorted(days) == ["2026-10-06", "2026-11-06"]
    assert all(t.amount_vnd == -rent.amount_vnd and t.tx_type == "rent" for t in paid)
    electric = next(o for o in d.obligations if o.name == "Tiền điện")
    (one,) = [t for t in d.transactions if t.obligation_key == electric.key]
    assert electric.amount_min_vnd <= -one.amount_vnd <= electric.amount_max_vnd


def test_lich_su_co_nhip_cuoi_tuan_va_dau_ky_luong():
    d = generate("minh", anchor=ANCHOR)
    spend = [
        t
        for t in d.transactions
        if t.jar_code == "an_uong" and t.kind == "expense" and t.funding_source == "jar"
    ]
    per_day: dict[int, int] = defaultdict(int)
    for t in spend:
        per_day[t.days_ago] += -t.amount_vnd
    weekend = [per_day[a] for a in range(1, 48) if (ANCHOR - timedelta(days=a)).weekday() >= 5]
    weekday = [per_day[a] for a in range(1, 48) if (ANCHOR - timedelta(days=a)).weekday() < 5]
    assert sum(weekend) / len(weekend) > 1.15 * sum(weekday) / len(weekday)
    assert sum(1 for v in per_day.values() if v) >= 28  # đủ ngày có chi cho mô hình theo lịch


def test_tham_so_nhip_la_cau_hinh_trong_spec_khong_phai_ma():
    def flatten(s):
        s["rhythm_defaults"].update(weekend_multiplier=1.0, early_period_multiplier=1.0)

    flat = generate("x", anchor=ANCHOR, spec=_spec(flatten))
    base = generate("minh", anchor=ANCHOR)
    assert flat.transactions != base.transactions
    assert {j.code: j.balance_vnd for j in flat.jars} == FIGMA_BALANCES  # đổi nhịp không đổi số dư


def test_minh_co_47_ngay_lich_su_va_hai_ky_luong():
    d = generate("minh", anchor=ANCHOR)
    assert d.history_days == 47
    salary = [t for t in d.transactions if t.tx_type == "salary"]
    assert {t.days_ago for t in salary} == {47, 16}  # 5/10 và 5/11
    assert all(t.amount_vnd == 9_000_000 and t.jar_code == "tien_vao_khac" for t in salary)
    assert sorted(e.days_ago for e in d.salary_events) == [16, 47]
    # mặc định KHÔNG nạp sự kiện lương đã xác nhận: kỳ lương hiện tại ở trạng thái `expected` như bảng số Figma
    assert d.seed_salary_events is False
    assert materialize(d, anchor=ANCHOR, now=NOW, tz=TZ).salary_events == []
    spec = _spec(lambda s: s.update(seed_salary_events=True))
    d2 = generate("x", anchor=ANCHOR, spec=spec)
    assert len(materialize(d2, anchor=ANCHOR, now=NOW, tz=TZ).salary_events) == 2
    split = [t for t in d.transactions if t.tx_type == "salary_split" and t.days_ago == 16]
    assert sum(t.amount_vnd for t in split) == 0 and len(split) == 8  # trừ Tiền vào khác, cộng 7 hũ


def test_khoa_la_tai_khoan_moi_chi_18_ngay():
    d = generate("khoa", anchor=ANCHOR)
    assert d.history_days == 18 and max(t.days_ago for t in d.transactions) == 18
    assert sum(1 for t in d.transactions if t.tx_type == "salary") == 1  # một kỳ lương
    assert len(d.salary_events) == 1


def test_an_uong_cua_minh_chi_tieu_don_ve_cuoi_ky():
    d = generate("minh", anchor=ANCHOR)
    spent = [t for t in d.transactions if t.jar_code == "an_uong" and t.kind == "expense"]
    recent = sum(-t.amount_vnd for t in spent if t.days_ago <= 16)
    old = sum(-t.amount_vnd for t in spent if t.days_ago > 16)
    assert recent > 0 and old > 0 and recent >= old * 0.9


# --- đồng hồ mô phỏng -------------------------------------------------------------------------
def test_materialize_dat_ngay_mo_phong_ve_ngay_neo():
    d = generate("minh", anchor=ANCHOR)
    m = materialize(d, anchor=ANCHOR, now=NOW, tz=TZ)
    assert m.clock_offset_days == -19 and m.app_date == ANCHOR
    last = max(m.transactions, key=lambda t: t.occurred_at)
    assert last.app_date < ANCHOR
    for t in m.transactions:
        # ngày thật = hôm nay thật - days_ago, nhất quán với offset
        real_day = t.occurred_at.astimezone(TZ).date()
        assert (t.app_date - real_day).days == -19
        assert t.occurred_at.tzinfo is not None and t.occurred_at < NOW


def test_materialize_thuan_ham_theo_now():
    d = generate("minh", anchor=ANCHOR)
    a = materialize(d, anchor=ANCHOR, now=NOW, tz=TZ)
    b = materialize(d, anchor=ANCHOR, now=NOW + timedelta(days=2), tz=TZ)
    assert (a.clock_offset_days, b.clock_offset_days) == (-19, -21)
    assert [t.app_date for t in a.transactions] == [t.app_date for t in b.transactions]


def test_materialize_dung_id_tat_dinh_khac_nhau_giua_nguoi_dung_va_khop_khoa_ngoai():
    d = generate("minh", anchor=ANCHOR)
    fee = {"amount_vnd": 33_000, "id": None}
    a = materialize(d, anchor=ANCHOR, now=NOW, tz=TZ, user_id="u1", bnpl_fee=fee)
    b = materialize(d, anchor=ANCHOR, now=NOW, tz=TZ, user_id="u2")
    a2 = materialize(d, anchor=ANCHOR, now=NOW, tz=TZ, user_id="u1", bnpl_fee=fee)
    assert [t["id"] for t in a.transaction_rows] == [t["id"] for t in a2.transaction_rows]
    a_ids = {t["id"] for t in a.transaction_rows}
    assert not a_ids & {t["id"] for t in b.transaction_rows}  # khóa chính toàn cục
    ob_ids = {o["id"] for o in a.obligations}
    assert {t["obligation_id"] for t in a.transaction_rows if t["obligation_id"]} <= ob_ids
    assert a.salary_events == []  # mặc định không nạp sự kiện lương lịch sử
    payee_ids = {p["id"] for p in a.payees}
    assert {t["payee_id"] for t in a.transaction_rows if t["payee_id"]} <= payee_ids
    bnpl = next(o for o in a.obligations if o["kind"] == "bnpl")
    assert bnpl["amount"] == 1_000_000 == bnpl["principal"] + bnpl["fee"]
    assert bnpl["due_date"] == date(2026, 12, 5)
    assert a.credit_line == {
        "product": "bnpl_sim",
        "lim": 5_000_000,
        "outstanding": 967_000,
        "due_day": 5,
    }
    # không có biểu phí thì nghĩa vụ trả sau không có phí (phí chỉ đến từ bảng, không gắn cứng trong mã)
    assert next(o for o in b.obligations if o["kind"] == "bnpl")["fee"] == 0


# --- spec sai ------------------------------------------------------------------------------------
def _spec(mutate):
    spec = json.loads((REPO / "data" / "personas" / "specs" / "minh.json").read_text("utf-8"))
    mutate(spec)
    return spec


def test_spec_tien_vao_nho_hon_so_du_can_dat_thi_bao_loi():
    spec = _spec(lambda s: s["jars"][0].update(target_vnd=99_000_000))
    with pytest.raises(PersonaError, match="opening_vnd"):
        generate("x", anchor=ANCHOR, spec=spec)


def test_spec_ty_le_chia_khong_du_100():
    spec = _spec(lambda s: s["jars"][0].update(split_percent=10))
    with pytest.raises(PersonaError, match="100"):
        generate("x", anchor=ANCHOR, spec=spec)


def test_spec_chi_tieu_vuot_so_du_chay_thi_bao_loi():
    # dồn toàn bộ chi tiêu vào kỳ đầu, lớn hơn lương kỳ đó
    spec = _spec(lambda s: s["jars"][0].update(recent_share=0.0))
    with pytest.raises(PersonaError, match="âm"):
        generate("x", anchor=ANCHOR, spec=spec)


def test_ten_persona_la_bi_tu_choi():
    for bad in ("../minh", "khong_co", "minh.json"):
        with pytest.raises(PersonaError):
            generate(bad, anchor=ANCHOR)


# --- ánh xạ tài khoản -> persona --------------------------------------------------------------
def test_anh_xa_tai_khoan_demo_dung_bang_cau_hinh():
    acc = load_accounts()
    assert acc["demo_accounts"] == {
        "minh": "minh",
        "lan": "lan",
        "khoa": "khoa",
        "giamkhao1": "minh",
        "giamkhao2": "minh",
        "giamkhao3": "minh",
    }
    assert set(acc["demo_accounts"].values()) <= set(available_personas())


def test_persona_tu_nhom_cognito():
    assert persona_from_groups(["ops", "persona-lan"]) == "lan"
    assert persona_from_groups(["ops"]) is None
    assert persona_from_groups(["persona-khong-co"]) is None
    assert persona_from_groups([]) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("[persona-minh ops]", ["persona-minh", "ops"]),
        ("persona-minh", ["persona-minh"]),
        (["a", "b"], ["a", "b"]),
        (None, []),
        ("[]", []),
    ],
)
def test_parse_claim_nhom(raw, expected):
    assert parse_groups_claim(raw) == expected
