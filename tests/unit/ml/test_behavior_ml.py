"""Hồ sơ hành vi (phase 5 luồng B, `yofina_ml.behavior`): đặc trưng, phân cụm, nhận xét kèm bằng chứng số khớp sổ cái, kiểm căn cứ."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from personas.generator import generate, materialize
from yofina_core import blocks as b
from yofina_core.clock import next_payday as core_next_payday
from yofina_core.money import format_vnd as core_format_vnd
from yofina_core.params import NormContext, normalize_params
from yofina_ml.behavior import (
    DEFAULT_CONFIG,
    Evidence,
    SpendFact,
    assign_segment,
    compute_profile,
    display_value,
    format_vnd,
    ground_text,
    insight_grounded,
    kmeans_1d,
    next_payday,
)

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
ANCHOR = date(2026, 11, 21)
NOW = datetime(2026, 12, 10, 3, 0, tzinfo=UTC)


def persona(name: str):
    data = generate(name, anchor=ANCHOR)
    m = materialize(data, anchor=ANCHOR, now=NOW, tz=TZ)
    rows = [r for r in m.transaction_rows if r["kind"] == "expense"]
    facts = [
        SpendFact(
            app_date=r["app_date"],
            amount_vnd=-int(r["amount"]),
            jar_code=r["jar_code"],
            funding=r["funding_source"],
            local_hour=r["occurred_at"].astimezone(TZ).hour if r["funding_source"] != "external" else None,
            is_obligation=r["obligation_id"] is not None,
        )
        for r in rows
    ]
    names = {j["code"]: j["name"] for j in m.jars}
    return data, m, rows, facts, names


@pytest.fixture(scope="module")
def minh():
    data, m, rows, facts, names = persona("minh")
    prof = compute_profile(facts, today=ANCHOR, payday_day=data.payday_day, jar_names=names)
    return data, m, rows, prof


def ev(insight, key):
    return next(e for e in insight.evidence if e.key == key).value


def test_minh_co_it_nhat_hai_nhan_xet_va_hop_dong_hop_le(minh):
    _, _, _, prof = minh
    assert prof.ready and len(prof.insights) >= 2  # tiêu chí 6 của phase 5
    data = b.BehaviorProfileData.model_validate(prof.to_data("2026-12-10T03:00:00Z"))
    assert data.next_step is not None and data.features is not None and data.segment is not None
    assert {i.kind for i in data.insights} >= {"bnpl_usage", "weekday_pattern", "payday_cycle"}
    block = b.build_behavior_insight(
        data=b.behavior_insight_data(data), trace_id="t" * 32, source_tool="forecast___get_behavior_profile",
        as_of=NOW, app_date=ANCHOR,
    )  # fmt: skip
    assert block.data.insight.insight_id == data.insights[0].insight_id


def _spend_rows(rows, *, window_from: date, window_to: date):
    """Dòng chi mà một người đếm tay sẽ tính: không phải khoản trả nghĩa vụ, trong [window_from, window_to]."""
    return [r for r in rows if r["obligation_id"] is None and window_from <= r["app_date"] <= window_to]


def test_bang_chung_khop_so_cai_khi_dem_lai_doc_lap(minh):
    """Mỗi con số làm bằng chứng được đếm lại trực tiếp từ các dòng sổ cái (không qua mã của yofina_ml)."""
    data, _, rows, prof = minh
    by_kind = {i.kind: i for i in prof.insights}
    first = min(r["app_date"] for r in rows if r["obligation_id"] is None)
    spend = _spend_rows(rows, window_from=first, window_to=ANCHOR - timedelta(days=1))
    total = sum(-int(r["amount"]) for r in spend)
    days = [first + timedelta(days=i) for i in range((ANCHOR - first).days)]

    bnpl = by_kind["bnpl_usage"]
    credit = [r for r in spend if r["funding_source"] == "credit"]
    assert ev(bnpl, "bnpl_count") == len(credit) == 2  # spec minh: hai lần mua Trả sau
    assert ev(bnpl, "bnpl_total_vnd") == sum(-int(r["amount"]) for r in credit) == 967_000
    assert ev(bnpl, "bnpl_share") == round(967_000 / total * 100)
    assert ev(bnpl, "window_days") == len(days) == prof.history_days

    week = by_kind["weekday_pattern"]
    weekend = sum(-int(r["amount"]) for r in spend if r["app_date"].isoweekday() >= 6)
    assert ev(week, "weekend_share") == round(weekend / total * 100)
    assert ev(week, "weekend_day_share") == round(sum(d.isoweekday() >= 6 for d in days) / len(days) * 100)

    pay = by_kind["payday_cycle"]
    def in_first_week(d: date) -> bool:
        p = date(d.year, d.month, data.payday_day) if d.day >= data.payday_day else (
            date(d.year, d.month - 1, data.payday_day) if d.month > 1 else date(d.year - 1, 12, data.payday_day)
        )
        return (d - p).days < 7
    fw = sum(-int(r["amount"]) for r in spend if in_first_week(r["app_date"]))
    assert ev(pay, "first_week_share") == round(fw / total * 100)
    last = next(e for e in pay.evidence if e.key == "last_first_week_vnd")
    assert last.period_from == date(2026, 11, 5) and last.period_to == date(2026, 11, 11)
    assert last.value == sum(
        -int(r["amount"]) for r in spend if date(2026, 11, 5) <= r["app_date"] <= date(2026, 11, 11)
    )


def test_khoan_tra_nghia_vu_khong_tinh_la_thoi_quen(minh):
    data, m, rows, prof = minh
    assert any(r["obligation_id"] for r in rows)
    facts = [SpendFact(r["app_date"], -int(r["amount"]), r["jar_code"], r["funding_source"], 12, False) for r in rows]
    names = {j["code"]: j["name"] for j in m.jars}
    as_habit = compute_profile(facts, today=ANCHOR, payday_day=data.payday_day, jar_names=names)
    assert as_habit.features["avg_daily_spend_vnd"] > prof.features["avg_daily_spend_vnd"]


def test_moi_cau_mau_qua_kiem_can_cu_va_qua_numeric_grounding_cua_agent(minh):
    from yofina_agent.verifier import Allowed, NumericGrounding

    _, _, _, prof = minh
    for i in prof.insights:
        assert insight_grounded(i), (i.insight_id, i.headline, i.detail)
        allowed = Allowed.from_payloads([[e.to_dict() for e in i.evidence]])
        texts = {"headline": i.headline, **({"detail": i.detail} if i.detail else {})}
        assert NumericGrounding.check(texts, allowed).ok, i.insight_id
        # cùng quy ước của test hợp đồng (test_contracts_phase5): số trong headline nằm trong evidence
        values = set()
        for e in i.evidence:
            v = e.value
            values |= {str(v), f"{int(v):,}".replace(",", ".")}
        assert all(n in values for n in re.findall(r"\d[\d.,]*\d|\d", i.headline)), i.headline


def test_nhan_xet_khong_mang_ten_doi_tac_hay_loi_nhan(minh):
    _, _, rows, prof = minh
    secrets = {str(r["merchant"]) for r in rows if r.get("merchant")} | {str(r["note"]) for r in rows if r.get("note")}
    text = " ".join(f"{i.headline} {i.detail or ''}" for i in prof.insights) + str(prof.next_step)
    assert secrets and not any(s in text for s in secrets)


def test_viec_can_lam_chuan_hoa_duoc_va_ngay_sau_hom_nay(minh):
    _, _, _, prof = minh
    step = prof.next_step
    assert step is not None and not re.search(r"\d", step["label"] + step["reason"])  # câu không có số nào
    for p in ("lan", "vy"):
        data, _, _, facts, names = persona(p)
        other = compute_profile(facts, today=ANCHOR, payday_day=data.payday_day, jar_names=names)
        action = other.next_step["action"]
        ctx = NormContext(today=ANCHOR, jar_codes=frozenset(names))
        assert normalize_params(action["tool"], action["params"], ctx) == action["params"]
        assert date.fromisoformat(action["params"]["fire_on"]) > ANCHOR


def test_lich_su_ngan_thi_chua_san_sang_va_noi_can_them_bao_nhieu_ngay():
    data, _, _, facts, names = persona("khoa")  # khoa: 18 ngày lịch sử
    prof = compute_profile(facts, today=ANCHOR, payday_day=data.payday_day, jar_names=names)
    assert not prof.ready and not prof.insights and prof.next_step is None
    assert prof.min_history_days == DEFAULT_CONFIG.min_history_days
    need = DEFAULT_CONFIG.min_history_days - prof.history_days
    assert f"{need} ngày" in prof.headline
    b.BehaviorProfileData.model_validate(prof.to_data("2026-12-10T03:00:00Z"))


def test_chi_deu_khong_co_nhan_xet_nao_thi_chua_san_sang():
    start = ANCHOR - timedelta(days=40)
    facts = [SpendFact(start + timedelta(days=i), 100_000, "an_uong", "jar", 12) for i in range(40)]
    prof = compute_profile(facts, today=ANCHOR, payday_day=5, jar_names={"an_uong": "Ăn uống"})
    assert not prof.ready and not prof.insights
    assert prof.segment == {"segment_id": "chi_deu_tay", "label": "Chi đều tay"}
    b.BehaviorProfileData.model_validate(prof.to_data("2026-12-10T03:00:00Z"))


def test_chi_buoi_toi_va_ngay_chi_dam():
    start = ANCHOR - timedelta(days=42)
    facts = []
    for i in range(42):
        d = start + timedelta(days=i)
        facts.append(SpendFact(d, 50_000, "an_uong", "jar", 20))
        if i % 7 == 2:
            facts.append(SpendFact(d, 600_000, "giai_tri", "jar", 21))
    facts.append(SpendFact(start, 80_000, "an_uong", "external", None))
    prof = compute_profile(facts, today=ANCHOR, payday_day=5, jar_names={"an_uong": "Ăn uống", "giai_tri": "Giải trí"})
    kinds = {i.kind: i for i in prof.insights}
    assert ev(kinds["time_of_day"], "evening_share") == 100  # dòng ngoài ví không có giờ nên không tính
    heavy = kinds["spending_cluster"]
    assert ev(heavy, "heavy_days") == 6 and ev(heavy, "heavy_avg_vnd") == 650_000
    assert all(insight_grounded(i) for i in prof.insights)


def test_kmeans_1d_tat_dinh_va_phan_cum_dung():
    lo, hi, labels = kmeans_1d([100, 120, 90, 900, 1000, 110])
    assert (round(lo), round(hi), labels) == (105, 950, [0, 0, 0, 1, 1, 0])
    assert kmeans_1d([]) == (0.0, 0.0, [])
    assert assign_segment(1.8, 1.0, 0.0)["segment_id"] == "chi_don_sau_luong"
    assert assign_segment(1.0, 1.9, 0.0)["segment_id"] == "chi_manh_cuoi_tuan"
    assert assign_segment(1.1, 1.1, 0.3)["segment_id"] == "hay_dung_tra_sau"


def test_kiem_can_cu_bat_so_la_ngay_la_va_nhan_thu_tieng_viet():
    e = (
        Evidence("a", "Chi", 2_069_000, "vnd", date(2026, 11, 5), date(2026, 11, 11)),
        Evidence("b", "Phần", 40, "percent"),
        Evidence("c", "Ngày", 6, "weekday"),
    )
    assert ground_text("Tuần đầu kỳ lương 05/11 bạn chi 2.069.000 ₫, chiếm 40%.", e) == []
    assert ground_text("Bạn chi 2069000 đồng vào thứ 7.", e) == []  # "thứ 7" là thứ Bảy (ISO 6)
    assert ground_text("Bạn chi 2,1 triệu.", e) == ["2,1"]
    assert ground_text("Bạn chi 41% tổng chi.", e) == ["41"]
    assert ground_text("Từ 01/10 bạn chi nhiều.", e) == ["01/10"]


def test_dinh_dang_va_ngay_luong_trung_yofina_core():
    for v in (0, 7, 1_000, 2_069_000, 123_456_789):
        assert format_vnd(v) == core_format_vnd(v) == display_value(v, "vnd")
    for d in (date(2026, 11, 4), date(2026, 11, 5), date(2026, 12, 31), date(2027, 1, 31)):
        for day in (1, 5, 31):
            assert next_payday(day, d) == core_next_payday(day, d)
    assert display_value(6, "weekday") == "thứ Bảy" and display_value(0.46, "ratio") == "46%"
