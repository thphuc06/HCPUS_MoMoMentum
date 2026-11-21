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
    assert 30 <= len(d.transactions) <= 120


@pytest.mark.parametrize("name", ["minh", "lan", "khoa"])
def test_tat_dinh_cung_seed_cung_ket_qua(name):
    assert generate(name, anchor=ANCHOR) == generate(name, anchor=ANCHOR)


def test_seed_khac_cho_ket_qua_khac_nhung_van_khop_so_du():
    a = generate("minh", anchor=ANCHOR)
    b = generate("minh", anchor=ANCHOR, seed=1)
    assert a.transactions != b.transactions
    assert {j.code: j.balance_vnd for j in b.jars} == FIGMA_BALANCES


@pytest.mark.parametrize("name", ["minh", "lan", "khoa"])
def test_so_cai_nhat_quan_so_du_bang_tong_dong_va_khong_bao_gio_am(name):
    d = generate(name, anchor=ANCHOR)
    by_jar: dict[str, list] = defaultdict(list)
    for t in d.transactions:
        by_jar[t.jar_code].append(t)
    for jar in d.jars:
        txs = sorted(by_jar[jar.code], key=lambda t: (-t.days_ago, t.local_time))
        bal = 0
        for t in txs:
            bal += t.amount_vnd
            assert bal >= 0, (jar.code, t)
        assert bal == jar.balance_vnd
    for t in d.transactions:
        assert t.amount_vnd != 0
        assert (t.kind == "expense") == (t.amount_vnd < 0)
        assert t.kind in {"income", "expense"}
        assert 1 <= t.days_ago <= d.history_days
        assert t.merchant is None or len(t.merchant) <= 120


def test_minh_co_47_ngay_lich_su_va_hai_ky_luong():
    d = generate("minh", anchor=ANCHOR)
    assert d.history_days == 47
    salary = [t for t in d.transactions if t.merchant == "Lương"]
    assert {t.days_ago for t in salary} == {47, 16}  # 5/10 và 5/11
    for ago in (47, 16):
        assert sum(t.amount_vnd for t in salary if t.days_ago == ago) == 9_000_000


def test_khoa_la_tai_khoan_moi_chi_18_ngay():
    d = generate("khoa", anchor=ANCHOR)
    assert d.history_days == 18 and max(t.days_ago for t in d.transactions) == 18
    assert sum(1 for t in d.transactions if t.merchant == "Lương") == len(d.jars)  # một kỳ lương


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
