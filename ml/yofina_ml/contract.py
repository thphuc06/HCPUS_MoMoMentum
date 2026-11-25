"""Bộ kiểm hợp đồng ML <-> pipeline: trả danh sách vi phạm (rỗng là đạt). Không dự báo gì, chỉ kiểm bất biến mà JSON Schema
không diễn đạt được. Dùng ở test của luồng ML (kiểm đầu ra của `forecast_user`), test của luồng pipeline (kiểm đầu vào do
pipeline dựng và đầu ra giả) và là nguồn sự thật của các bất biến ghi ở `ml/README.md` mục "Giao diện".
"""

from __future__ import annotations

import re
from datetime import timedelta

from yofina_ml.types import ForecastInputs, ForecastResult

_MODEL_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_STATUSES = ("ok", "tight", "short")
_BANDS = ("high", "medium", "low")


def check_inputs(inputs: ForecastInputs) -> list[str]:
    """Bất biến của đầu vào do pipeline dựng."""
    errs: list[str] = []
    end = inputs.app_date + timedelta(days=inputs.horizon_days)
    if not 1 <= inputs.horizon_days <= 90:
        errs.append("horizon_days phải trong 1..90")
    if inputs.next_payday <= inputs.app_date:
        errs.append("next_payday phải sau app_date")
    if list(inputs.payday_dates) != sorted(set(inputs.payday_dates)):
        errs.append("payday_dates phải tăng dần và không trùng")
    if any(not inputs.app_date < d <= end for d in inputs.payday_dates):
        errs.append("payday_dates phải nằm trong (app_date, app_date + horizon_days]")
    if inputs.payday_day is not None and not 1 <= inputs.payday_day <= 31:
        errs.append("payday_day phải trong 1..31")
    codes = [j.code for j in inputs.jars]
    if len(set(codes)) != len(codes):
        errs.append("mã hũ trùng nhau")
    if not inputs.jars:
        errs.append("cần ít nhất một hũ")
    for j in inputs.jars:
        tag = f"hũ {j.code}"
        if any((not isinstance(v, int)) or isinstance(v, bool) or v < 0 for v in j.daily_spend_vnd):
            errs.append(f"{tag}: daily_spend_vnd phải là số nguyên không âm")
        if j.history_start + timedelta(days=j.history_days) != inputs.app_date:
            errs.append(
                f"{tag}: lịch sử phải kết thúc ở app_date - 1 (history_start + số ngày = app_date)"
            )
        for flow, kind in [(f, "salary") for f in j.inflows] + [
            (f, "obligation") for f in j.outflows
        ]:
            if flow.kind != kind:
                errs.append(
                    f"{tag}: {flow.kind} nằm sai danh sách (inflows là salary, outflows là obligation)"
                )
            if not inputs.app_date < flow.date <= end:
                errs.append(f"{tag}: mốc {flow.date} ngoài horizon")
            if flow.amount_vnd <= 0:
                errs.append(f"{tag}: amount_vnd phải dương")
            lo, hi = flow.amount_min_vnd, flow.amount_max_vnd
            if (lo is None) != (hi is None) or (lo is not None and not lo <= flow.amount_vnd <= hi):
                errs.append(f"{tag}: khoảng số tiền không chứa amount_vnd")
    return errs


def check_result(
    inputs: ForecastInputs, result: ForecastResult, *, subset: bool = False
) -> list[str]:
    """Bất biến của đầu ra. `subset` đúng với kết quả của `update_forecast` (chỉ một số hũ, theo thứ tự tùy ý)."""
    errs: list[str] = []
    cfg, run = inputs.config, result.run
    by_code = {j.code: j for j in inputs.jars}
    got = [jf.summary.jar_code for jf in result.jars]
    if subset:
        if not set(got) <= set(by_code) or len(set(got)) != len(got) or not got:
            errs.append("kết quả cục bộ phải là tập con không trùng, không rỗng của các hũ đầu vào")
    elif got != [j.code for j in inputs.jars]:
        errs.append("jars phải cùng tập và cùng thứ tự với đầu vào")

    if not _MODEL_RE.match(run.model):
        errs.append("run.model không khớp ^[a-z][a-z0-9_]{0,39}$")
    if run.app_date != inputs.app_date or run.horizon_days != inputs.horizon_days:
        errs.append("run.app_date và run.horizon_days phải bằng đầu vào")
    if run.seed != cfg.seed:
        errs.append("run.seed phải bằng config.seed")
    if run.confidence_label not in _BANDS:
        errs.append("run.confidence_label không hợp lệ")
    if run.data_coverage is not None and not 0 <= run.data_coverage <= 1:
        errs.append("run.data_coverage phải trong [0, 1]")
    history = max((j.history_days for j in inputs.jars), default=0)
    if run.history_days != history:
        errs.append("run.history_days phải bằng số ngày lịch sử lớn nhất của các hũ đầu vào")
    if run.is_initial_estimate != (history < cfg.cold_start_min_days):
        errs.append("is_initial_estimate phải đúng khi history_days < config.cold_start_min_days")
    if run.is_initial_estimate and run.confidence_label != "low":
        errs.append("ước lượng ban đầu thì confidence_label phải là low")
    shown = (run.params or {}).get("show_runout_date")
    if shown is not None and (
        not isinstance(shown, dict)
        or set(shown) != set(got)
        or any(not isinstance(v, bool) for v in shown.values())
    ):
        errs.append(
            "params.show_runout_date (nếu có) phải là {mã hũ: bool} cho đúng các hũ của kết quả"
        )

    days_to_payday = (inputs.next_payday - inputs.app_date).days
    for jf in result.jars:
        s, tag = jf.summary, f"hũ {jf.summary.jar_code}"
        jar = by_code.get(s.jar_code)
        if jar is None:
            continue
        if s.start_balance_vnd != jar.balance_vnd:
            errs.append(f"{tag}: start_balance_vnd phải bằng số dư đầu vào")
        if s.payday_date != inputs.next_payday or s.days_to_payday != days_to_payday:
            errs.append(f"{tag}: payday_date và days_to_payday phải theo next_payday")
        if s.status not in _STATUSES_SET or s.confidence_band not in _BANDS:
            errs.append(f"{tag}: status hoặc confidence_band không hợp lệ")
        if (s.p_shortfall is None) == s.show_probability:
            errs.append(
                f"{tag}: p_shortfall chỉ có khi show_probability là true (ràng buộc CHECK của DB)"
            )
        if s.p_shortfall is not None:
            if not 0 <= s.p_shortfall <= 1:
                errs.append(f"{tag}: p_shortfall phải là tỷ lệ 0..1, không phải phần trăm")
            want = (
                "short" if s.p_shortfall >= cfg.short_threshold
                else "tight" if s.p_shortfall >= cfg.tight_threshold
                else "ok"
            )  # fmt: skip
            if s.status != want:
                errs.append(
                    f"{tag}: status {s.status} không khớp ngưỡng với p_shortfall {s.p_shortfall}"
                )
        if s.p_shortfall_se is not None and (s.p_shortfall is None or s.p_shortfall_se < 0):
            errs.append(f"{tag}: p_shortfall_se chỉ có cùng p_shortfall và không âm")
        if s.show_probability and (not cfg.probability_enabled or run.is_initial_estimate):
            errs.append(
                f"{tag}: không được phát xác suất khi probability_enabled sai hoặc là ước lượng ban đầu"
            )
        if run.is_initial_estimate and s.confidence_band != "low":
            errs.append(f"{tag}: ước lượng ban đầu thì confidence_band phải là low")
        if (jar.history_days < cfg.cold_start_min_days) != (s.series_kind == "cold_start"):
            errs.append(
                f"{tag}: series_kind cold_start đúng khi hũ có ít lịch sử hơn cold_start_min_days"
            )
        end = inputs.app_date + timedelta(days=inputs.horizon_days)
        if s.runout_date is not None and not inputs.app_date < s.runout_date <= end:
            errs.append(f"{tag}: runout_date phải trong horizon")
        if len(jf.days) != inputs.horizon_days:
            errs.append(f"{tag}: phải có đúng horizon_days dòng ngày")
        for i, d in enumerate(jf.days, start=1):
            if d.date != inputs.app_date + timedelta(days=i):
                errs.append(f"{tag}: ngày thứ {i} phải là app_date + {i}")
                break
        for d in jf.days:
            if not 0 <= d.spend_p10_vnd <= d.spend_p50_vnd <= d.spend_p90_vnd:
                errs.append(f"{tag} {d.date}: phân vị chi tiêu phải >= 0 và tăng dần")
            if not d.balance_p10_vnd <= d.balance_p50_vnd <= d.balance_p90_vnd:
                errs.append(f"{tag} {d.date}: phân vị số dư phải tăng dần")
    return errs


_STATUSES_SET = frozenset(_STATUSES)
