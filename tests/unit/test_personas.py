"""Bộ sinh persona: tất định, số dư khớp bảng số Figma §5, sổ cái nhất quán, đồng hồ mô phỏng."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
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
from personas.six_jars import apply_demo_layout
from yofina_core.wallet import TX_TYPE_SALARY_SPLIT
from yofina_ledger.jar_layout import DEMO_LAYOUT

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


def test_co_bon_persona():
    assert available_personas() == ["khoa", "lan", "minh", "vy"]


#: Bộ hũ demo (issue #39, đổi 26/11 sáng): ba hũ mặc định trước (Chi hằng ngày, Nghĩa vụ, Dự phòng), rồi hũ tự thêm; hũ cũ của
#: persona gộp vào hũ nào. KỲ VỌNG của test, viết tay theo brief, không đọc từ mã.
DEMO_SOURCES = {
    "chi_hang_ngay": (),
    "nghia_vu": ("nghia_vu", "hoa_don"),
    "du_phong": ("du_phong",),
    "an_uong": ("an_uong",),
    "di_lai": ("di_lai",),
    "giai_tri": ("giai_tri",),
    "muc_tieu": ("du_lich",),
    "dau_tu": (),
}
DEMO_KINDS = {
    "chi_hang_ngay": ("spending", None),
    "nghia_vu": ("obligation", None),
    "du_phong": ("saving", "buffer"),
    "an_uong": ("spending", None),
    "di_lai": ("spending", None),
    "giai_tri": ("spending", None),
    "muc_tieu": ("saving", "goal"),
    "dau_tu": ("saving", "long_term"),
}
SPENDING = ("an_uong", "di_lai", "giai_tri")  # ràng buộc 1 của #39: ba hũ chi giữ y hệt ví persona
DAILY = "chi_hang_ngay"
PERSONAS = ["minh", "khoa", "lan", "vy"]


def _demo(persona):
    original = generate(persona, anchor=ANCHOR)
    return original, apply_demo_layout(original, DEMO_LAYOUT)


def _daily_spec(persona):
    """Khối hũ Chi hằng ngày của ví demo trong spec persona (đầu vào của bộ sinh)."""
    spec = json.loads((REPO / "data" / "personas" / "specs" / f"{persona}.json").read_text("utf-8"))
    return spec, next(j for j in spec["demo_jars"] if j["code"] == DAILY)


def _running_ok(data, code):
    bal = 0
    for t in sorted(
        (t for t in data.transactions if t.jar_code == code and t.funding_source == "jar"),
        key=lambda t: (-t.days_ago, t.local_time),
    ):
        bal += t.amount_vnd
        if bal < 0:
            return False, bal
    return True, bal


@pytest.mark.parametrize("persona", PERSONAS)
def test_bo_hu_demo_gop_theo_anh_xa_va_bao_toan_tong_vi(persona):
    original, demo = _demo(persona)
    old = {j.code: j for j in original.jars}
    spec, daily = _daily_spec(persona)
    taken = {src: Decimal(str(pts)) for src, pts in daily["split_from"].items()}
    # hũ mục tiêu chỉ có khi persona có hũ nguồn mang mục tiêu (hũ goal phải có số tiền và hạn); mọi hũ khác luôn có
    expected_codes = [c for c in DEMO_SOURCES if c != "muc_tieu" or "du_lich" in old]
    assert [j.code for j in demo.jars] == expected_codes
    assert [j.code for j in demo.jars][:3] == [DAILY, "nghia_vu", "du_phong"]  # ba hũ mặc định trước
    purposes = {j.code: j.purpose for j in DEMO_LAYOUT}
    assert {j.code: (j.kind, purposes[j.code]) for j in demo.jars} == {
        c: DEMO_KINDS[c] for c in expected_codes
    }
    for jar in demo.jars:
        sources = [old[c] for c in DEMO_SOURCES[jar.code] if c in old]
        extra = daily["target_vnd"] if jar.code == DAILY else 0
        assert jar.balance_vnd == sum(s.balance_vnd for s in sources) + extra, jar.code
        share = sum(taken.values()) if jar.code == DAILY else -taken.get(jar.code, Decimal(0))
        assert jar.split_percent == sum(s.split_percent for s in sources) + share, jar.code
    assert sum(j.split_percent for j in demo.jars) == 100
    # tổng tiền ví = ví persona cộng số dư của hũ Chi hằng ngày (tiền mới vào ví qua số dư đầu kỳ, không lấy của hũ nào)
    assert sum(j.balance_vnd for j in demo.jars) == sum(j.balance_vnd for j in original.jars) + daily[
        "target_vnd"
    ]
    assert demo.system_balances == original.system_balances
    for jar in demo.jars:  # bất biến của bộ sinh: số dư mỗi hũ = tổng dòng trả bằng hũ, số dư chạy không âm
        ok, final = _running_ok(demo, jar.code)
        assert ok and final == jar.balance_vnd, jar.code
    if "du_lich" in old:
        goal = next(j for j in demo.jars if j.code == "muc_tieu")
        assert (goal.goal_vnd, goal.goal_date) == (old["du_lich"].goal_vnd, old["du_lich"].goal_date)
        assert goal.name == old["du_lich"].name  # tên theo hũ nguồn, như lộ trình seed và lời của persona
    dau_tu = next(j for j in demo.jars if j.code == "dau_tu")
    assert (dau_tu.balance_vnd, dau_tu.split_percent) == (0, 0)
    assert not any(t.jar_code == "dau_tu" for t in demo.transactions)
    assert spec["jars"]  # spec vẫn là ví persona cũ: hũ Chi hằng ngày chỉ khai ở khối `demo_jars`
    assert DAILY not in {j["code"] for j in spec["jars"]}


def test_bo_hu_demo_cua_minh_theo_ty_le_spec():
    _, demo = _demo("minh")
    assert {j.code: (int(j.split_percent), j.balance_vnd) for j in demo.jars} == {
        "chi_hang_ngay": (3, 300_000),
        "nghia_vu": (33, 1_450_000),
        "du_phong": (10, 2_700_000),
        "an_uong": (30, 380_000),
        "di_lai": (7, 640_000),
        "giai_tri": (7, 760_000),
        "muc_tieu": (10, 1_800_000),
        "dau_tu": (0, 0),
    }
    goal = next(j for j in demo.jars if j.code == "muc_tieu")
    assert (goal.goal_vnd, goal.goal_date) == (6_000_000, date(2027, 4, 1))
    # hũ goal là hũ người dùng tự thêm cho một mục tiêu: tên lấy theo hũ nguồn của persona (lộ trình seed nói "hũ Du lịch")
    assert [j.name for j in demo.jars] == [
        "Chi hằng ngày", "Nghĩa vụ", "Dự phòng", "Ăn uống", "Đi lại", "Giải trí", "Du lịch", "Đầu tư",
    ]  # fmt: skip
    # không có khoản chuyển "Để riêng tiền trả nghĩa vụ" của bộ bốn hũ cũ
    assert not any(t.note == "Để riêng tiền trả nghĩa vụ" for t in demo.transactions)
    # Trả sau của minh đến hạn ngày 3 (trước kỳ lương ngày 5) để khoản đến hạn nằm trong cửa sổ "trước lương" của cảnh 2
    assert demo.credit_due_day == 3


def test_ngay_den_han_tra_sau_cua_vi_demo_doc_tu_spec():
    """Ngày đến hạn Trả sau trên ví demo là dữ liệu của spec (`credit_line.demo_due_day`), không phải bảng theo tên persona trong mã:
    spec nào khai thì ví demo dùng số đó, ví persona vẫn dùng `credit_line.due_day`; spec không khai thì ví demo như ví persona."""
    import personas.six_jars as six_jars

    assert not hasattr(six_jars, "DEMO_CREDIT_DUE_DAY")
    own = generate("x", anchor=ANCHOR, spec=_spec(lambda s: s["credit_line"].update(demo_due_day=4)))
    assert own.credit_due_day == 5 and apply_demo_layout(own, DEMO_LAYOUT).credit_due_day == 4
    plain = generate("x", anchor=ANCHOR, spec=_spec(lambda s: s["credit_line"].pop("demo_due_day")))
    assert apply_demo_layout(plain, DEMO_LAYOUT).credit_due_day == 5


@pytest.mark.parametrize(
    ("persona", "due_day", "bnpl_due"),
    [("minh", 3, [date(2026, 12, 3)]), ("khoa", 5, []), ("lan", 5, []), ("vy", 5, [])],
)
def test_dat_lai_demo_han_muc_va_khoan_tra_sau_nhu_truoc(persona, due_day, bnpl_due):
    """Đặt lại ví demo (`materialize` của ví sau `apply_demo_layout`, như `LedgerService.reset_demo`) cho đúng hạn mức và khoản Trả sau
    như khi ngày đến hạn còn nằm trong mã: `minh` ngày 3 (khoản 967.000 ₫ đến hạn 03/12), các persona khác ngày 5. KỲ VỌNG viết tay."""
    _, demo = _demo(persona)
    seeded = materialize(demo, anchor=ANCHOR, now=NOW, tz=TZ, user_id=persona, obligation_pay_jar="nghia_vu")
    assert seeded.credit_line["due_day"] == due_day
    assert [o["due_date"] for o in seeded.obligations if o["kind"] == "bnpl"] == bnpl_due


@pytest.mark.parametrize("persona", PERSONAS)
def test_bo_hu_demo_giu_nguyen_tung_dong_cua_hu_chi_tieu(persona):
    """Ràng buộc 1 của #39: Ăn uống, Đi lại, Giải trí giữ nguyên mã và mọi dòng (chi, chia lương, chuyển giữa hũ, khoản trả nghĩa vụ,
    mua Trả sau) cùng khóa, ngày, giờ, số tiền, đối tác như ví persona, nên chuỗi chi, PELT và hồ sơ hành vi của cảnh 1 và cảnh 4 như
    trên `main`, dù ví demo có thêm hũ Chi hằng ngày."""
    original, demo = _demo(persona)
    for code in SPENDING:

        def series(data, code=code):
            return sorted(
                (t.key, t.days_ago, t.local_time, t.kind, t.tx_type, t.amount_vnd, t.merchant, t.obligation_key,
                 t.transfer_key, t.funding_source)
                for t in data.transactions
                if t.jar_code == code
            )  # fmt: skip

        assert series(demo) == series(original)
        assert next(j for j in demo.jars if j.code == code).balance_vnd == next(
            j for j in original.jars if j.code == code
        ).balance_vnd
    obligations = {o.key: o for o in original.obligations}
    for ob in demo.obligations:  # khoản trả từ ba hũ chi (Tiền cơm văn phòng, Netflix) giữ hũ trả
        if obligations[ob.key].pay_jar in SPENDING:
            assert ob.pay_jar == obligations[ob.key].pay_jar


def _tx_type_map():
    import re

    seed = (REPO / "db" / "seed" / "tx_type_map.sql").read_text("utf-8")
    return {
        m["code"]: (m["direction"], None if m["jar"] == "NULL" else m["jar"].strip("'"))
        for m in re.finditer(r"\('(?P<code>[a-z_]+)',\s*'[^']*',\s*'(?P<direction>[a-z]+)',\s*(?P<jar>NULL|'[a-z_]+')", seed)
    }


@pytest.mark.parametrize("persona", PERSONAS)
def test_hu_chi_hang_ngay_cua_vi_demo_la_chi_lat_vat_sinh_them(persona):
    """Hũ Chi hằng ngày của ví demo chứa khoản chi lặt vặt do bộ sinh sinh thêm (tạp hóa, đồ dùng, mua sắm nhỏ), không lấy dòng nào
    của Ăn uống, Đi lại, Giải trí: loại giao dịch có thật trong `tx_type_map` mà không loại nào đưa về hũ khác của ví (bước loại giao
    dịch không kéo khoản này sang hũ riêng), đối tác riêng, có dòng chia lương mỗi kỳ trong lịch sử."""
    from yofina_core.wallet import transaction_jar

    original, demo = _demo(persona)
    _, daily = _daily_spec(persona)
    lines = [t for t in demo.transactions if t.jar_code == DAILY]
    expenses = [t for t in lines if t.kind == "expense"]
    assert expenses and all(t.funding_source == "jar" and t.obligation_key is None for t in expenses)
    types = _tx_type_map()
    codes = [j.code for j in demo.jars]
    for t in expenses:
        direction, default = types[t.tx_type]
        assert direction == "out" and t.tx_type != "grocery"
        assert transaction_jar(default, codes, tx_type=t.tx_type) in (None, DAILY), t.tx_type
        assert 1 <= t.days_ago <= original.history_days and t.classified_by == "seed"
    other_merchants = {t.merchant for t in original.transactions if t.merchant}
    scene4 = REPO / "data" / "personas" / "samples" / "minh_sao_ke_2_tuan.csv"
    scene4_parties = {line.split(",")[3] for line in scene4.read_text("utf-8").splitlines()[1:]}
    assert not {t.merchant for t in expenses} & (other_merchants | scene4_parties)
    assert {t.merchant for t in expenses} <= {m["name"] for m in daily["merchants"]}
    # một dòng chia lương mỗi kỳ, đúng phần lương của tỷ lệ lấy từ hũ nguồn; mỗi kỳ chia vẫn đủ lương
    salary_days = sorted(t.days_ago for t in original.transactions if t.tx_type == "salary")
    split = [t for t in lines if t.tx_type == TX_TYPE_SALARY_SPLIT]
    per = sum(original.monthly_salary_vnd * int(p) // 100 for p in daily["split_from"].values())
    assert sorted(t.days_ago for t in split) == salary_days and {t.amount_vnd for t in split} == {per}
    for day in salary_days:
        assert sum(t.amount_vnd for t in demo.transactions if t.tx_type == TX_TYPE_SALARY_SPLIT
                   and t.days_ago == day and t.amount_vnd > 0) == original.monthly_salary_vnd  # fmt: skip
        assert sum(t.amount_vnd for t in demo.transactions if t.transfer_key == f"split:{day}") == 0
    for event in demo.salary_events:
        assert sum(v for _, v in event.split) == event.amount_vnd and dict(event.split)[DAILY] == per
    # chi 120 ngày của hũ = số dư đầu kỳ + lương chia - số dư cần đạt (bộ sinh tự kiểm)
    opening = sum(t.amount_vnd for t in lines if t.key.startswith("open:"))
    assert opening == daily.get("opening_vnd", 0)
    assert -sum(t.amount_vnd for t in expenses) == opening + per * len(salary_days) - daily["target_vnd"]


@pytest.mark.parametrize("persona", PERSONAS)
def test_ty_le_hu_chi_hang_ngay_lay_tu_phan_du_cua_nghia_vu_va_du_phong(persona):
    """Phần tỷ lệ của hũ mới lấy từ Nghĩa vụ phần trên nhu cầu đã khai (làm tròn lên như đề xuất tỷ lệ) và từ Dự phòng phần trên sàn
    `buffer_min_split_percent`; số dư của hũ nguồn ở ngày neo giữ nguyên (phần lương chia trong lịch sử chuyển vào số dư đầu kỳ)."""
    from yofina_ledger.split_proposal import (
        ASSUMED_BUFFER_MIN_SPLIT_PERCENT,
        ceil_percent,
        monthly_equivalent,
    )

    original, demo = _demo(persona)
    _, daily = _daily_spec(persona)
    assert set(daily["split_from"]) <= {"nghia_vu", "du_phong"}
    jars = {j.code: j for j in demo.jars}
    need = sum(
        (monthly_equivalent(o.amount_vnd, o.cycle) for o in demo.obligations if o.pay_jar == "nghia_vu"),
        Fraction(0),
    )
    assert jars["nghia_vu"].split_percent >= ceil_percent(need, demo.monthly_salary_vnd)
    assert jars["du_phong"].split_percent >= ASSUMED_BUFFER_MIN_SPLIT_PERCENT
    old_balance = {c: sum(j.balance_vnd for j in original.jars if c in DEMO_SOURCES and j.code in DEMO_SOURCES[c])
                   for c in daily["split_from"]}  # fmt: skip
    assert {c: jars[c].balance_vnd for c in daily["split_from"]} == old_balance
    # dòng chia lương của hũ nguồn bớt đúng phần của hũ mới, số dư đầu kỳ tăng đúng tổng phần đó
    salary_days = [t.days_ago for t in original.transactions if t.tx_type == "salary"]
    for src, pts in daily["split_from"].items():
        cut = demo.monthly_salary_vnd * int(pts) // 100
        before: dict[int, int] = defaultdict(int)
        for t in original.transactions:
            if t.tx_type == TX_TYPE_SALARY_SPLIT and t.amount_vnd > 0 and t.jar_code in DEMO_SOURCES[src]:
                before[t.days_ago] += t.amount_vnd
        after = {t.days_ago: t.amount_vnd for t in demo.transactions
                 if t.tx_type == TX_TYPE_SALARY_SPLIT and t.amount_vnd > 0 and t.jar_code == src}  # fmt: skip
        assert after == {d: before[d] - cut for d in salary_days}
        open_before = sum(t.amount_vnd for t in original.transactions if t.key.startswith("open:")
                          and t.jar_code in DEMO_SOURCES[src])  # fmt: skip
        open_after = sum(t.amount_vnd for t in demo.transactions if t.key.startswith("open:") and t.jar_code == src)
        assert open_after == open_before + cut * len(salary_days)
        assert sum(1 for t in demo.transactions if t.key.startswith("open:") and t.jar_code == src) == 1


def test_tham_so_hu_chi_hang_ngay_dung_dong_ngau_nhien_rieng():
    """Đổi nhịp, số khoản, đối tác của hũ Chi hằng ngày trong spec không đổi một dòng nào của hũ khác: phần mới có dòng ngẫu nhiên
    riêng, ví persona bảy hũ không biết tới nó."""

    def tweak(s):
        daily = next(j for j in s["demo_jars"] if j["code"] == DAILY)
        daily["expense_count"] = daily["expense_count"] + 7
        daily["merchants"] = [*daily["merchants"], {"name": "Tạp hóa thử", "tx_type": "qr_other", "weight": 5}]
        daily.setdefault("rhythm", {})["amount_sigma"] = 0.9

    base, other = generate("x", anchor=ANCHOR, spec=_spec(lambda s: None)), generate("x", anchor=ANCHOR, spec=_spec(tweak))
    assert base.transactions == other.transactions and base.jars == other.jars  # ví persona như cũ
    a, b = apply_demo_layout(base, DEMO_LAYOUT), apply_demo_layout(other, DEMO_LAYOUT)
    assert [t for t in a.transactions if t.jar_code != DAILY] == [t for t in b.transactions if t.jar_code != DAILY]
    assert [t for t in a.transactions if t.jar_code == DAILY] != [t for t in b.transactions if t.jar_code == DAILY]
    assert a.jars == b.jars


def test_vi_persona_bay_hu_khong_co_hu_chi_hang_ngay():
    d = generate("minh", anchor=ANCHOR)
    assert DAILY not in {j.code for j in d.jars} and not any(t.jar_code == DAILY for t in d.transactions)
    assert [j.code for j in d.demo_jars] == [DAILY]
    m = materialize(d, anchor=ANCHOR, now=NOW, tz=TZ)
    assert DAILY not in {j["code"] for j in m.jars} and not any(t["jar_code"] == DAILY for t in m.transaction_rows)


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda d: d.update(split_from={"khong_co": 3}), "khong_co"),
        (lambda d: d.update(split_from={"chi_hang_ngay": 3}), "chi_hang_ngay"),
        (lambda d: d.update(split_from={"nghia_vu": 0}), "split_from"),
        (lambda d: d.update(code="hu_la"), "hu_la"),
    ],
)
def test_khoi_hu_demo_sai_thi_bao_loi(mutate, match):
    def change(s):
        mutate(next(j for j in s["demo_jars"] if j["code"] == DAILY))

    with pytest.raises(PersonaError, match=match):
        apply_demo_layout(generate("x", anchor=ANCHOR, spec=_spec(change)), DEMO_LAYOUT)


def test_hu_nguon_khong_du_ty_le_thi_bao_loi():
    d = generate("minh", anchor=ANCHOR)
    (daily,) = d.demo_jars
    greedy = replace(daily, split_from=(("nghia_vu", Decimal(40), 3_600_000),))
    with pytest.raises(PersonaError, match="Nghĩa vụ"):
        apply_demo_layout(replace(d, demo_jars=(greedy,)), DEMO_LAYOUT)


@pytest.mark.parametrize("persona", PERSONAS)
def test_bo_hu_demo_nghia_vu_tra_tu_hu_anh_xa_va_luong_chia_gop(persona):
    original, demo = _demo(persona)
    alias = {src: code for code, srcs in DEMO_SOURCES.items() for src in srcs}
    _, daily = _daily_spec(persona)
    cut = {src: demo.monthly_salary_vnd * int(p) // 100 for src, p in daily["split_from"].items()}
    assert [(o.key, o.pay_jar) for o in demo.obligations] == [
        (o.key, alias.get(o.pay_jar, o.pay_jar) if o.pay_jar else None) for o in original.obligations
    ]
    seeded = materialize(demo, anchor=ANCHOR, now=NOW, tz=TZ, user_id=persona, obligation_pay_jar="nghia_vu")
    assert all(o["pay_jar"] in {j.code for j in demo.jars} for o in seeded.obligations if o["pay_jar"])
    for old_event, event in zip(original.salary_events, demo.salary_events, strict=True):
        expected: dict[str, int] = {DAILY: sum(cut.values())}
        for code, value in old_event.split:
            expected[alias[code]] = expected.get(alias[code], 0) + value
        for src, value in cut.items():
            expected[src] -= value
        assert dict(event.split) == expected
    split_days = {t.days_ago for t in original.transactions if t.tx_type == TX_TYPE_SALARY_SPLIT}
    for day in split_days:
        def lines(data, day=day):
            out: dict[str, int] = {}
            for t in data.transactions:
                if t.tx_type == TX_TYPE_SALARY_SPLIT and t.days_ago == day and t.amount_vnd > 0:
                    out[t.jar_code] = out.get(t.jar_code, 0) + t.amount_vnd
            return out

        folded: dict[str, int] = {DAILY: sum(cut.values())}
        for code, value in lines(original).items():
            folded[alias[code]] = folded.get(alias[code], 0) + value
        for src, value in cut.items():
            folded[src] -= value
        assert lines(demo) == folded
        assert sum(1 for t in demo.transactions if t.tx_type == TX_TYPE_SALARY_SPLIT and t.days_ago == day
                   and t.amount_vnd > 0) == len(folded)  # fmt: skip


def test_bo_hu_demo_tu_choi_hu_persona_khong_co_trong_anh_xa():
    original = generate("lan", anchor=ANCHOR)
    stray = replace(original.jars[0], code="hu_la")
    with pytest.raises(PersonaError):
        apply_demo_layout(replace(original, jars=(*original.jars, stray)), DEMO_LAYOUT)


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
    # mật độ giữ như bản 47 ngày (166 dòng, 3,5 dòng mỗi ngày) khi kéo lịch sử ra 120 ngày (issue #8)
    assert 3.0 <= len(d.transactions) / d.history_days <= 4.0


@pytest.mark.parametrize("name", ["minh", "lan", "khoa", "vy"])
def test_tat_dinh_cung_seed_cung_ket_qua(name):
    assert generate(name, anchor=ANCHOR) == generate(name, anchor=ANCHOR)


def test_seed_khac_cho_ket_qua_khac_nhung_van_khop_so_du():
    a = generate("minh", anchor=ANCHOR)
    b = generate("minh", anchor=ANCHOR, seed=1)
    assert a.transactions != b.transactions
    assert {j.code: j.balance_vnd for j in b.jars} == FIGMA_BALANCES


@pytest.mark.parametrize("name", ["minh", "lan", "khoa", "vy"])
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
    assert sorted(days) == ["2026-08-06", "2026-09-06", "2026-10-06", "2026-11-06"]
    assert all(t.amount_vnd == -rent.amount_vnd and t.tx_type == "rent" for t in paid)
    electric = next(o for o in d.obligations if o.name == "Tiền điện")
    paid_electric = [t for t in d.transactions if t.obligation_key == electric.key]
    assert len(paid_electric) == 4  # 26/7, 26/8, 26/9, 26/10
    assert all(
        electric.amount_min_vnd <= -t.amount_vnd <= electric.amount_max_vnd for t in paid_electric
    )


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
    weekend = [per_day[a] for a in range(1, d.history_days + 1) if (ANCHOR - timedelta(days=a)).weekday() >= 5]
    weekday = [per_day[a] for a in range(1, d.history_days + 1) if (ANCHOR - timedelta(days=a)).weekday() < 5]
    assert sum(weekend) / len(weekend) > 1.15 * sum(weekday) / len(weekday)
    assert sum(1 for v in per_day.values() if v) >= 28  # đủ ngày có chi cho mô hình theo lịch


def test_tham_so_nhip_la_cau_hinh_trong_spec_khong_phai_ma():
    def flatten(s):
        s["rhythm_defaults"].update(weekend_multiplier=1.0, early_period_multiplier=1.0)

    flat = generate("x", anchor=ANCHOR, spec=_spec(flatten))
    base = generate("minh", anchor=ANCHOR)
    assert flat.transactions != base.transactions
    assert {j.code: j.balance_vnd for j in flat.jars} == FIGMA_BALANCES  # đổi nhịp không đổi số dư


def test_minh_co_120_ngay_lich_su_va_bon_ky_luong():
    d = generate("minh", anchor=ANCHOR)
    assert d.history_days == 120 and max(t.days_ago for t in d.transactions) == 120
    salary = [t for t in d.transactions if t.tx_type == "salary"]
    assert {t.days_ago for t in salary} == {108, 77, 47, 16}  # 5/8, 5/9, 5/10 và 5/11
    assert all(t.amount_vnd == 9_000_000 and t.jar_code == "tien_vao_khac" for t in salary)
    assert sorted(e.days_ago for e in d.salary_events) == [16, 47, 77, 108]
    # mặc định KHÔNG nạp sự kiện lương đã xác nhận: kỳ lương hiện tại ở trạng thái `expected` như bảng số Figma
    assert d.seed_salary_events is False
    assert materialize(d, anchor=ANCHOR, now=NOW, tz=TZ).salary_events == []
    spec = _spec(lambda s: s.update(seed_salary_events=True))
    d2 = generate("x", anchor=ANCHOR, spec=spec)
    assert len(materialize(d2, anchor=ANCHOR, now=NOW, tz=TZ).salary_events) == 4
    split = [t for t in d.transactions if t.tx_type == "salary_split" and t.days_ago == 16]
    assert sum(t.amount_vnd for t in split) == 0 and len(split) == 8  # trừ Tiền vào khác, cộng 7 hũ


def test_khoa_la_tai_khoan_moi_chi_18_ngay():
    d = generate("khoa", anchor=ANCHOR)
    assert d.history_days == 18 and max(t.days_ago for t in d.transactions) == 18
    assert sum(1 for t in d.transactions if t.tx_type == "salary") == 1  # một kỳ lương
    assert len(d.salary_events) == 1


def _an_uong_moi_ngay(d):
    out: dict[int, int] = defaultdict(int)
    for t in d.transactions:
        if t.jar_code == "an_uong" and t.kind == "expense" and t.obligation_key is None:
            out[t.days_ago] += -t.amount_vnd
    return out


def test_an_uong_cua_minh_chi_don_dau_ky_luong_o_moi_ky():
    d = generate("minh", anchor=ANCHOR)
    per_day = _an_uong_moi_ngay(d)
    # ba kỳ lương đủ (5/8, 5/9, 5/10): 14 ngày đầu kỳ chi mỗi ngày nhiều hơn phần còn lại của kỳ
    for first, last in ((108, 78), (77, 48), (47, 17)):
        early = [per_day[a] for a in range(first, first - 14, -1)]
        late = [per_day[a] for a in range(first - 14, last - 1, -1)]
        assert sum(early) / len(early) > 1.1 * sum(late) / len(late), (first, last)


def test_lich_su_minh_khong_co_diem_gay_hanh_vi():
    """Không cài sẵn đổi hành vi (issue #8): bộ phát hiện của sản phẩm chạy trên đúng lịch sử lúc đặt lại không xác nhận, không
    nghi ở hũ chi tiêu nào; cảnh 4 phải tự tạo thay đổi lúc chạy. Kỳ lương hiện tại chi mỗi ngày gần như các kỳ trước."""
    from yofina_ml import change as ch
    from yofina_ml.backtest.change_calibration import persona_daily_spend

    params = ch.load_params()
    for jar, daily in persona_daily_spend("minh", ANCHOR).items():
        s = ch.prepare_weekly(daily, params)
        if s.skipped:
            continue
        assert ch.detect_confirmed(s, params) is None, jar
        assert ch.detect_suspect(s, params) is None, jar
    per_day = _an_uong_moi_ngay(generate("minh", anchor=ANCHOR))
    now = sum(per_day[a] for a in range(16, 0, -1)) / 16
    before = sum(per_day[a] for a in range(108, 16, -1)) / 92
    assert 0.8 < now / before < 1.4


@pytest.mark.parametrize("persona", PERSONAS)
def test_hu_chi_hang_ngay_cua_vi_demo_khong_co_diem_gay_hanh_vi(persona):
    """Hũ Chi hằng ngày của ví demo không tạo dấu hiệu đổi hành vi nào (không chen vào cảnh 4): chuỗi chi lặt vặt mỗi ngày (chi trừ
    tiền hũ, không gắn nghĩa vụ, như `app_get_daily_spend`) qua bộ phát hiện của sản phẩm không xác nhận, không nghi."""
    import numpy as np

    from yofina_ml import change as ch

    params = ch.load_params()
    _, demo = _demo(persona)
    daily = np.zeros(demo.history_days)
    for t in demo.transactions:
        if t.jar_code == DAILY and t.kind == "expense" and t.funding_source == "jar" and t.obligation_key is None:
            daily[demo.history_days - t.days_ago] += -t.amount_vnd
    s = ch.prepare_weekly(daily, params)
    assert s.skipped or (ch.detect_confirmed(s, params) is None and ch.detect_suspect(s, params) is None)


def test_minh_chi_deu_nhu_ban_47_ngay():
    # số khoản chi mỗi ngày giữ như bản 47 ngày (Ăn uống 110, Đi lại 14 khoản trong 47 ngày)
    d = generate("minh", anchor=ANCHOR)
    count: dict[str, int] = defaultdict(int)
    for t in d.transactions:
        if t.kind == "expense" and t.funding_source == "jar" and t.obligation_key is None:
            count[t.jar_code] += 1
    assert abs(count["an_uong"] / 120 - 110 / 47) < 0.1
    assert abs(count["di_lai"] / 120 - 14 / 47) < 0.05


def test_minh_bu_hu_an_uong_tu_hu_tiet_kiem_cuoi_moi_ky_truoc():
    d = generate("minh", anchor=ANCHOR)
    moves = [t for t in d.transactions if t.transfer_key and t.transfer_key.startswith("move:")]
    into = [t for t in moves if t.amount_vnd > 0]
    assert {t.jar_code for t in into} == {"an_uong"}
    assert {t.days_ago for t in into} == {92, 61, 31}  # 21/8, 21/9, 21/10: trước hạn tiền cơm văn phòng ngày 23
    assert sum(t.amount_vnd for t in moves) == 0 and sum(t.amount_vnd for t in into) == 3_500_000
    assert all(t.days_ago > 16 for t in moves)  # kỳ lương hiện tại chưa bù


def test_lo_trinh_seed_cua_minh_khop_lich_su_va_so_du_vua_sinh():
    """`roadmaps/minh.json` là dữ liệu seed, nhưng phần nói về lịch sử và số dư phải khớp persona vừa sinh (issue #8)."""
    seed = json.loads((REPO / "data" / "personas" / "roadmaps" / "minh.json").read_text("utf-8"))
    d = generate("minh", anchor=ANCHOR)
    basis = seed["basis"]
    assert basis["history_days"] == d.history_days == 120
    assert basis["confidence_band"] == "high"  # từ 60 ngày lịch sử, độ phủ 1,0 (band_high_min_days)
    # không cài dấu hiệu đổi hành vi (issue #22): cảnh 4 tạo thay đổi bằng tệp sao kê lúc chạy
    assert "behavior_flag" not in seed
    bal = {j.code: j.balance_vnd for j in d.jars}
    text = json.dumps(seed, ensure_ascii=False)
    assert bal["an_uong"] == 380_000 and "Ăn uống chỉ còn 380.000 ₫" in text


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


# --- chuyển hũ trong lịch sử (spec `jar_transfers`) ------------------------------------------------
def _with_transfer(s, *, days_ago=20, amount=200_000, src="du_phong", dst="an_uong"):
    s.setdefault("jar_transfers", []).append(
        {"days_ago": days_ago, "from": src, "to": dst, "amount_vnd": amount}
    )
    jar = next(j for j in s["jars"] if j["code"] == src)
    jar["opening_vnd"] += amount  # hũ nguồn giữ đúng số dư cần đạt


def test_chuyen_hu_trong_lich_su_la_hai_dong_cung_nhom_va_giu_so_du_can_dat():
    d = generate("x", anchor=ANCHOR, spec=_spec(_with_transfer))
    moves = [
        t
        for t in d.transactions
        if t.transfer_key and t.transfer_key.startswith("move:") and t.days_ago == 20
    ]
    assert sorted((t.jar_code, t.amount_vnd) for t in moves) == [
        ("an_uong", 200_000),
        ("du_phong", -200_000),
    ]
    assert len({t.transfer_key for t in moves}) == 1
    assert all(t.kind == "transfer" and t.tx_type == "jar_transfer" for t in moves)
    assert all(t.days_ago == 20 for t in moves)
    assert {j.code: j.balance_vnd for j in d.jars} == FIGMA_BALANCES

    # tiền chuyển vào được tiêu: hũ đích chi thêm đúng số đó
    def spent(data):
        return -sum(
            t.amount_vnd
            for t in data.transactions
            if t.jar_code == "an_uong" and t.kind == "expense"
        )

    assert spent(d) == spent(generate("x", anchor=ANCHOR, spec=_spec(lambda s: None))) + 200_000


@pytest.mark.parametrize(
    "patch",
    [
        {"src": "khong_co"},
        {"dst": "tien_vao_khac"},
        {"src": "an_uong", "dst": "an_uong"},
        {"amount": 0},
        {"days_ago": 999},
    ],
)
def test_chuyen_hu_sai_thi_bao_loi(patch):
    def mutate(s):
        s.setdefault("jar_transfers", []).append(
            {
                "days_ago": patch.get("days_ago", 20),
                "from": patch.get("src", "du_phong"),
                "to": patch.get("dst", "an_uong"),
                "amount_vnd": patch.get("amount", 100_000),
            }
        )

    with pytest.raises(PersonaError, match="jar_transfers"):
        generate("x", anchor=ANCHOR, spec=_spec(mutate))


# --- ánh xạ tài khoản -> persona --------------------------------------------------------------
def test_anh_xa_tai_khoan_demo_dung_bang_cau_hinh():
    acc = load_accounts()
    # ba tài khoản giám khảo cùng persona minh: cảnh 1 đến 4 ra cùng số trên mọi tài khoản (issue #8)
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
