"""Sàn thiết yếu, sàn chi và đích tự tính của hũ Dự phòng tính từ MỨC NỀN BỀN của chính người dùng (issue #39, chủ dự án chốt 26/11): trung
vị chi theo tuần trên cửa sổ dài (`spend_baseline_weeks`, mặc định 12 tuần) quy về tháng, cùng hàm `yofina_core.spend_baseline` với đề xuất
tỷ lệ của ledger. Hệ số giữ nguyên (sàn thiết yếu 80%, tỷ lệ giữ 0,5), chỉ đổi mức gốc. Chưa đủ `spend_baseline_min_weeks` tuần (hoặc hũ
thưa) thì lùi về chi trung bình 30 ngày gần nhất như trước.

Một đợt tiêu tăng là DỮ KIỆN cho agent (`recent_spend` của dòng phân bổ: mức nền, mức gần đây, từ ngày nào, đã xác nhận đổi hành vi hay
chưa, ngày dự báo hũ cạn nếu giữ nhịp), không thành sàn cứng ép Dự phòng và mục tiêu. Hũ có dấu hiệu đổi hành vi PELT đã xác nhận
(`behavior_flags`) thì dùng chính dấu hiệu đó thay cho ngưỡng `spend_spike_ratio`. Dùng solver THẬT, dự báo THẬT (không giả)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from pipeline_helpers import APP_DATE, NOW, context_rows, jar_row
from test_allocation import RESULT
from test_resilience import (
    JARS,
    OBLIGATION_ROWS_CTX,
    RENT,
    USER,
    World,
    _ledger_obligation,
    errors_of,
    pipe,
)

from yofina_core.config import Config
from yofina_core.roadmap import AllocationPlanData
from yofina_core.spend_baseline import DEFAULT_BASELINE_MIN_WEEKS, DEFAULT_BASELINE_WEEKS
from yofina_forecast.allocation import AllocationEngine
from yofina_forecast.resilience import variable_monthly_spend
from yofina_forecast.settings import DEFAULT_ALLOCATION_PARAMS as P
from yofina_forecast.settings import ForecastSettings

NORMAL_DAY, SPIKE_DAY = 120_000, 378_571  # tuần 840.000 ₫ và khoảng 2.650.000 ₫ (hệ số khoảng 3,15 như tệp sao kê cảnh 4)
BASELINE = 3_600_000  # 840.000 ₫ mỗi tuần quy về tháng 30 ngày
LAST_DAY = APP_DATE - timedelta(days=1)


def wallet(spend: dict[str, list[int]], *, days: int) -> World:
    """Ví bảy hũ cũ (`purpose` NULL) của `test_resilience` với chuỗi chi tùy chọn; hũ không nêu thì không chi."""
    ctx_jars = [jar_row(code, kind, bal, split, order, spend.get(code, [0] * days)) for code, kind, bal, split, order, _g, _d in JARS]
    ctx_obl = [dict(o) for o in OBLIGATION_ROWS_CTX] + [dict(RENT)]
    return World(context_rows(days=days, jars=ctx_jars, obligations=ctx_obl), JARS, [_ledger_obligation(o) for o in ctx_obl])


def spike(days: int = 98, spike_days: int = 14) -> list[int]:
    return [NORMAL_DAY] * (days - spike_days) + [SPIKE_DAY] * spike_days


def built(w, engine: AllocationEngine | None = None):
    engine = engine or AllocationEngine(pipe(w))
    gathered = engine.resilience.gather(USER, NOW)
    b = engine.build(gathered, horizon_months=3, goal_args=[], shock_id=None, allow_relaxation=True)
    return b, {j.code: j for j in b.problem.jars}


def plan(w, engine: AllocationEngine | None = None) -> AllocationPlanData:
    out = (engine or AllocationEngine(pipe(w))).optimize(USER, {})
    assert not errors_of(RESULT, out), errors_of(RESULT, out)
    return AllocationPlanData.model_validate(out["data"])


def steady_spend(days: int) -> dict[str, list[int]]:
    return {"an_uong": spike(days, 0), "giai_tri": [20_000] * days}


# --- sàn tính từ mức nền bền --------------------------------------------------------------------------------------------------------
def test_dot_tang_hai_tuan_khong_doi_san_thiet_yeu_san_chi_va_dich_du_phong():
    w = wallet({"an_uong": spike(), "giai_tri": [20_000] * 98}, days=98)
    b, by = built(w)
    recent = variable_monthly_spend(spike(), 30, P.month_days)
    assert recent > 2 * BASELINE  # chi 30 ngày gần nhất (cách cũ) gần gấp đôi mức nền
    # sàn thiết yếu: 80% mức nền, không 80% chi 30 ngày gần nhất
    assert by["an_uong"].floor_vnd == round(BASELINE * P.essential_floor_percent / 100) == 2_880_000
    # sàn chi: tỷ lệ giữ x mức nền (không vượt phần chia hiện tại 2.700.000 ₫)
    assert by["an_uong"].spend_floor_vnd == round(P.spending_keep_ratio * BASELINE)
    # đích tự tính của Dự phòng: số tháng x (nghĩa vụ cứng + mức nền chi thiết yếu), không theo đợt tăng
    assert b.buffer_target_vnd == round(P.buffer_target_months * (by["nghia_vu"].floor_vnd + BASELINE))
    assert by["du_phong"].hold_current


def test_dot_tang_hai_tuan_du_phong_khong_ve_0_va_du_kien_dot_tang_dung_so():
    w = wallet({"an_uong": spike(), "giai_tri": [20_000] * 98}, days=98)
    d = plan(w)
    lines = {x.jar.code: x for x in d.lines}
    assert lines["du_phong"].proposed_monthly_vnd >= lines["du_phong"].current_monthly_vnd > 0
    assert lines["an_uong"].floor_vnd == 2_880_000 and lines["an_uong"].floor_gap_vnd == 0
    fact = lines["an_uong"].recent_spend
    assert fact is not None
    assert fact.recent_monthly_vnd == variable_monthly_spend(spike(), 30, P.month_days)
    assert fact.baseline_monthly_vnd == BASELINE and fact.keep_floor_vnd == round(P.spending_keep_ratio * BASELINE)
    assert fact.unusually_high and not fact.change_confirmed
    # từ tuần đầu tiên của đợt tăng trong cửa sổ gần đây (tuần cắt lùi từ hôm qua)
    assert fact.high_since == (LAST_DAY - timedelta(days=13)).isoformat()
    # ngày dự báo hũ cạn nếu giữ nhịp: chính ngày cạn của dự báo hiện có (dự báo không đổi, không tính lại)
    runout = {r["jar_code"]: r for r in w.summaries(USER)}["an_uong"]
    assert runout["runout_date"] is not None and runout["runout_date_shown"]
    assert fact.runout_date == runout["runout_date"].isoformat()
    # hũ chi đều: không có dữ kiện đợt tăng
    other = lines["giai_tri"].recent_spend
    assert other is not None and not other.unusually_high
    assert other.high_since is None and other.runout_date is None and not other.change_confirmed


def test_vi_chi_deu_san_nhu_cach_cu():
    w = wallet(steady_spend(98), days=98)
    _, by = built(w)
    for code in ("an_uong", "giai_tri"):
        old = variable_monthly_spend(steady_spend(98)[code], 30, P.month_days)
        assert by[code].spend_floor_vnd == min(round(P.spending_keep_ratio * old), by[code].current_vnd)
    assert by["an_uong"].floor_vnd == round(variable_monthly_spend(spike(98, 0), 30, P.month_days) * 0.8)
    d = plan(w)
    assert not any(x.recent_spend.unusually_high for x in d.lines if x.recent_spend is not None)


def test_chua_du_tuan_thi_lui_ve_chi_trung_binh_30_ngay():
    # 5 tuần lịch sử (dưới `spend_baseline_min_weeks` 6 tuần): như trước 26/11, kể cả khi có đợt tăng; không có mức nền nên không có cờ
    days = 35
    w = wallet({"an_uong": spike(days), "giai_tri": [20_000] * days}, days=days)
    _, by = built(w)
    old = variable_monthly_spend(spike(days), 30, P.month_days)
    assert by["an_uong"].floor_vnd == round(old * P.essential_floor_percent / 100)
    fact = next(x for x in plan(w).lines if x.jar.code == "an_uong").recent_spend
    assert fact is not None and fact.baseline_monthly_vnd is None and not fact.unusually_high
    assert (P.spend_baseline_weeks, P.spend_baseline_min_weeks) == (DEFAULT_BASELINE_WEEKS, DEFAULT_BASELINE_MIN_WEEKS)


def test_vi_ba_hu_chi_hang_ngay_san_thiet_yeu_va_san_chi_tu_muc_nen():
    from test_allocation_spend_floor import three_jar

    days = 98
    w = three_jar(0, days=days, spend=spike(days))
    ctx = w.context_rows
    for row in ctx:
        if row["section"] == "jar" and row["payload"]["code"] == "chi_hang_ngay":
            row["payload"]["essential_spend"] = [v // 2 for v in spike(days)]
    _, by = built(w)
    daily = by["chi_hang_ngay"]
    assert daily.floor_vnd == round(BASELINE / 2 * P.essential_floor_percent / 100)
    assert daily.spend_floor_vnd == round(P.spending_keep_ratio * BASELINE)
    fact = next(x for x in plan(w).lines if x.jar.code == "chi_hang_ngay").recent_spend
    assert fact is not None and fact.unusually_high and fact.baseline_monthly_vnd == BASELINE


# --- dấu hiệu đổi hành vi PELT đã xác nhận ---------------------------------------------------------------------------------------------
class Flags:
    """Kho `behavior_flags` trong bộ nhớ (cùng hình dạng dòng `app_list_behavior_flags`)."""

    def __init__(self, *rows, fail: bool = False) -> None:
        self.rows, self.fail, self.calls = list(rows), fail, 0

    def list(self, user_id):
        self.calls += 1
        if self.fail:
            raise RuntimeError("db down")
        return self.rows


def flag(jar: str, cp: date, *, status: str = "confirmed", direction: str = "up") -> dict:
    return {"id": f"f-{jar}-{cp}", "jar_code": jar, "status": status, "method": "pelt", "direction": direction,
            "old_weekly_vnd": 140_000, "new_weekly_vnd": 300_000, "change_point_date": cp, "weeks_held": 2}  # fmt: skip


def fact_of(w, store, code="giai_tri"):
    engine = AllocationEngine(pipe(w), flags=store)
    line = next(x for x in plan(w, engine).lines if x.jar.code == code)
    return line.recent_spend


def test_pelt_da_xac_nhan_thi_dung_chinh_dau_hieu_do_khong_dung_nguong_thu_hai():
    w = wallet(steady_spend(98), days=98)  # chi đều: ngưỡng không bật
    cp = APP_DATE - timedelta(days=15)
    fact = fact_of(w, Flags(flag("giai_tri", cp)))
    assert fact is not None and fact.unusually_high and fact.change_confirmed
    assert fact.high_since == cp.isoformat()
    # đã dùng để sinh lại lộ trình (`applied`) vẫn là dấu hiệu đã xác nhận
    assert fact_of(w, Flags(flag("giai_tri", cp, status="applied"))).change_confirmed


@pytest.mark.parametrize(
    "row",
    [
        flag("giai_tri", APP_DATE - timedelta(days=15), direction="down"),  # chi giảm: không phải đợt tăng
        flag("giai_tri", APP_DATE - timedelta(days=15), status="suspected"),  # mới nghi, chưa xác nhận
        flag("giai_tri", APP_DATE - timedelta(days=15), status="dismissed"),
        flag("giai_tri", APP_DATE - timedelta(days=9 * 7)),  # điểm gãy cũ hơn `max_weeks_since_break` của PELT: tin cũ
        flag("an_uong", APP_DATE - timedelta(days=15)),  # hũ khác
    ],
)
def test_dau_hieu_khong_phai_tang_da_xac_nhan_con_moi_thi_theo_nguong(row):
    w = wallet(steady_spend(98), days=98)
    fact = fact_of(w, Flags(row))
    assert fact is not None and not fact.unusually_high and not fact.change_confirmed and fact.high_since is None


def test_dau_hieu_moi_nhat_cua_hu_quyet_dinh():
    # tăng rồi đã xác nhận giảm về sau đó: dấu hiệu mới nhất là giảm, không còn đợt tăng đã xác nhận
    w = wallet(steady_spend(98), days=98)
    rows = (flag("giai_tri", APP_DATE - timedelta(days=40), status="applied"),
            flag("giai_tri", APP_DATE - timedelta(days=12), direction="down"))  # fmt: skip
    assert not fact_of(w, Flags(*rows)).change_confirmed


def test_doc_dau_hieu_hong_thi_van_toi_uu_theo_nguong():
    w = wallet({"an_uong": spike(), "giai_tri": [20_000] * 98}, days=98)
    store = Flags(fail=True)
    fact = fact_of(w, store, "an_uong")
    assert store.calls == 1 and fact is not None and fact.unusually_high and not fact.change_confirmed


# --- cấu hình ------------------------------------------------------------------------------------------------------------------------
def test_cua_so_muc_nen_doc_tu_cau_hinh():
    env = _base_env()
    base = ForecastSettings.from_config(Config(env=env)).allocation
    assert (base.spend_baseline_weeks, base.spend_baseline_min_weeks) == (12, 6)
    over = ForecastSettings.from_config(
        Config(env={**env, "YOFINA_ALLOCATION_SPEND_BASELINE_WEEKS": "4", "YOFINA_ALLOCATION_SPEND_BASELINE_MIN_WEEKS": "4"})
    ).allocation
    assert (over.spend_baseline_weeks, over.spend_baseline_min_weeks) == (4, 4)
    # cửa sổ 4 tuần: hai tuần tăng chiếm nửa cửa sổ nên mức nền lên trung bình hai tuần giữa, sàn theo đó
    w = wallet({"an_uong": spike(), "giai_tri": [20_000] * 98}, days=98)
    _, by = built(w, AllocationEngine(pipe(w, allocation=over)))
    assert by["an_uong"].floor_vnd == round((840_000 + 7 * SPIKE_DAY) / 2 * 30 / 7 * P.essential_floor_percent / 100)


def _base_env() -> dict[str, str]:
    return {
        "YOFINA_FORECAST_HORIZON_DAYS": "30", "YOFINA_FORECAST_HISTORY_WINDOW_DAYS": "330", "YOFINA_FORECAST_N_PATHS_FULL": "600",
        "YOFINA_FORECAST_N_PATHS_FAST": "400", "YOFINA_FORECAST_COLD_START_MIN_DAYS": "21", "YOFINA_FORECAST_ACI_GAMMA": "0.01",
        "YOFINA_FORECAST_COVERAGE_TARGET": "0.8", "YOFINA_FORECAST_SHORT_THRESHOLD": "0.5", "YOFINA_FORECAST_TIGHT_THRESHOLD": "0.2",
        "YOFINA_FORECAST_BAND_HIGH_MIN_DAYS": "60", "YOFINA_FORECAST_BAND_HIGH_MIN_COVERAGE": "0.7",
        "YOFINA_FORECAST_BAND_MEDIUM_MIN_DAYS": "21", "YOFINA_FORECAST_PROBABILITY_ENABLED": "true", "YOFINA_FORECAST_KEEP_RUNS": "6",
        "YOFINA_FORECAST_FAST_MAX_AGE_SECONDS": "86400", "YOFINA_FORECAST_RECOMPUTE_GUARD_SECONDS": "20",
        "YOFINA_FORECAST_FRESHNESS_SECONDS": "3600", "YOFINA_APP_TIMEZONE": "Asia/Ho_Chi_Minh",
        "YOFINA_FORECAST_IDEMPOTENCY_TTL_SECONDS": "100", "YOFINA_FORECAST_IDEMPOTENCY_LEASE_SECONDS": "10",
        "YOFINA_FORECAST_NIGHTLY_MAX_USERS": "10", "YOFINA_FORECAST_SCENARIO_N_PATHS": "100", "YOFINA_FORECAST_SCENARIO_KEEP": "5",
        "YOFINA_AFFORDABILITY_SHORT_P50_FLOOR_VND": "0", "YOFINA_AFFORDABILITY_TIGHT_P10_FLOOR_VND": "0",
        "YOFINA_REFERENCE_CACHE_SECONDS": "300",
    }  # fmt: skip
