"""Trạng thái hiển thị không tự mâu thuẫn với danh sách khoản đến hạn trước lương (#39, việc nối 3; KK "điểm còn nghi").

Xác suất hụt của engine chỉ xét các ngày trước ngày lương. Khoản đến hạn ĐÚNG ngày lương lớn hơn số dư trước lương thì danh sách khoản
đến hạn có khoản thiếu (`obligation_window`) mà trạng thái của engine vẫn "đủ". `yofina_forecast.due_status.with_due_status` (chạy trước
khi ghi lần dự báo thường, cùng định nghĩa với thẻ what-if) ghi trạng thái hụt và không phát xác suất; chuỗi số dư và mọi số khác của
engine giữ nguyên. Dữ liệu dựng tay, không chạy Monte Carlo.
"""

from __future__ import annotations

from datetime import date, timedelta

from yofina_forecast.due_status import due_window, shown_p, shown_status, with_due_status
from yofina_ml.types import (
    DayQuantiles,
    ForecastInputs,
    ForecastResult,
    JarForecast,
    JarInput,
    JarSummary,
    RunMeta,
    ScheduledFlow,
)

TODAY = date(2026, 11, 21)
PAYDAY = date(2026, 12, 5)
SALARY_PART = 2_970_000


def _jar(code: str, balance: int, *, due: int | None) -> JarInput:
    outflows = (ScheduledFlow(PAYDAY, "obligation", "Trả sau", due),) if due else ()
    return JarInput(
        code=code, kind="obligation", balance_vnd=balance, split_percent=33.0, history_start=TODAY - timedelta(days=60),
        daily_spend_vnd=(0,) * 60, inflows=(ScheduledFlow(PAYDAY, "salary", "Lương", SALARY_PART),), outflows=outflows,
    )  # fmt: skip


def _forecast(jar: JarInput, *, status: str = "ok", p: float | None = 0.0) -> JarForecast:
    """P50 bằng số dư tới trước ngày lương; ngày lương trừ khoản đến hạn rồi cộng lương (số dư CUỐI ngày)."""
    due = sum(f.amount_vnd for f in jar.outflows)
    days = []
    for i in range(1, 31):
        day = TODAY + timedelta(days=i)
        balance = jar.balance_vnd if day < PAYDAY else jar.balance_vnd - due + SALARY_PART
        days.append(DayQuantiles(day, 0, 0, 0, balance, balance, balance))
    summary = JarSummary(
        jar_code=jar.code, start_balance_vnd=jar.balance_vnd, payday_date=PAYDAY, days_to_payday=(PAYDAY - TODAY).days,
        runout_date=None, p_shortfall=p, p_shortfall_se=0.001 if p is not None else None, status=status,  # type: ignore[arg-type]
        confidence_band="high", show_probability=p is not None, series_kind="dense",
    )  # fmt: skip
    return JarForecast(summary, tuple(days))


def _run(*jars: JarInput, forecasts: tuple[JarForecast, ...] | None = None) -> tuple[ForecastInputs, ForecastResult]:
    inputs = ForecastInputs(app_date=TODAY, horizon_days=30, next_payday=PAYDAY, payday_dates=(PAYDAY,), jars=jars)
    meta = RunMeta(
        model="test", model_version="0", app_date=TODAY, horizon_days=30, history_days=60, data_coverage=1.0,
        confidence_label="high", is_initial_estimate=False, n_paths=1, seed=1, params={},
    )  # fmt: skip
    return inputs, ForecastResult(meta, forecasts or tuple(_forecast(j) for j in jars))


def test_khoan_dung_ngay_luong_lon_hon_so_du_truoc_luong_thi_trang_thai_la_hut_khong_phat_xac_suat():
    short = _jar("nghia_vu", 900_000, due=1_000_000)  # cuối ngày 05/12 còn dương (đã cộng lương) mà khoản Trả sau thiếu 100.000 ₫
    inputs, result = _run(short)
    (jf,) = result.jars
    window = due_window(inputs, jf)
    assert window["first_shortfall"] == {"date": "2026-12-05", "label": "Trả sau", "shortfall_vnd": 100_000}
    assert jf.summary.status == "ok" and min(d.balance_p50_vnd for d in jf.days) > 0
    assert shown_status(jf, window) == "short" and shown_p(jf, window) is None
    (saved,) = with_due_status(inputs, result).jars
    assert saved.summary.status == "short"
    assert not saved.summary.show_probability and saved.summary.p_shortfall is None and saved.summary.p_shortfall_se is None
    # số của engine giữ nguyên: chuỗi số dư, ngày cạn, số dư đầu
    assert saved.days == jf.days and saved.summary.runout_date is None
    assert saved.summary.start_balance_vnd == jf.summary.start_balance_vnd


def test_du_tien_cho_khoan_dung_ngay_luong_hoac_khong_co_khoan_thi_giu_trang_thai_cua_engine():
    enough = _jar("nghia_vu", 1_031_608, due=1_000_000)
    plain = _jar("du_phong", 2_700_000, due=None)
    inputs, result = _run(enough, plain)
    assert with_due_status(inputs, result) == result


def test_engine_da_bao_hut_thi_giu_xac_suat_cua_engine():
    short = _jar("nghia_vu", 900_000, due=1_000_000)
    inputs, result = _run(short, forecasts=(_forecast(short, status="short", p=0.62),))
    (saved,) = with_due_status(inputs, result).jars
    assert saved.summary.status == "short" and saved.summary.p_shortfall == 0.62 and saved.summary.show_probability
