"""`forecast___affordability_check` và `POST /affordability`: kiểm tra TRƯỚC KHI quẹt, tất định, không model, không ghi gì.

Cùng một engine cho chat và màn chuyển tiền (T3a, T3b, T3c) nên hai nơi cùng số (khối `affordability_card`).

Cách tính (không chạy Monte Carlo lúc yêu cầu): phân vị số dư theo ngày của dự báo đã lưu (P10, P50, P90) là phân vị của MỘT phân
phối; trừ một khoản tất định `a` khỏi mọi đường từ ngày chi trở đi thì mọi phân vị cùng dịch đúng `a`. Vì vậy số dư SAU khi chi
đọc được chính xác từ bảng `forecasts` (cùng dãy số ngẫu nhiên với dự báo của hũ), không cần mô phỏng lại:

- **hụt**: số dư P50 sau khi chi xuống dưới ngưỡng `affordability_short_p50_floor_vnd` ở một ngày nào trước kỳ lương (hoặc số
  dư hôm nay không đủ chi); `shortfall_vnd` là số đồng thiếu (M đồng trước kỳ lương);
- **sát**: không hụt nhưng số dư P10 (kịch bản xấu) xuống dưới `affordability_tight_p10_floor_vnd` trước kỳ lương; `days_earlier` là
  số ngày hũ cạn sớm hơn so với dự báo hiện tại khi có ngày cạn;
- **đủ**: còn lại.

Nguồn Trả sau (mô phỏng): chi phí của món (gốc + phí PHÁT SINH THÊM) tách khỏi tổng phải trả ngày đến hạn (`credit.py`); hũ trả nghĩa
vụ có đủ tiền khi đến hạn không; tỷ lệ nghĩa vụ trên thu nhập so với ngưỡng của luật (`obligation_to_income`), vượt thì đỏ kèm
"không khuyến khích". Phương án (đổi hũ, Trả sau, hoãn, chia nhỏ) sinh bằng luật tất định; mỗi phương án đã đi qua bộ luật
suitability (`yofina_planner`), phương án bị chặn (block) không được đưa ra.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any

from yofina_core.blocks import (
    AffordabilityCardData,
    ForecastBasis,
    format_instant,
)
from yofina_core.clock import app_today
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.money import format_vnd, to_vnd
from yofina_core.schedule import bnpl_due_date
from yofina_core.suitability import Proposal
from yofina_core.wallet import BNPL_PRODUCT_CODE
from yofina_forecast.common import (
    STATUS_RANK,
    STATUS_WORD,
    best,
    clip,
    dm,
    int_of,
    min_band,
    to_date,
    worst,
)
from yofina_forecast.credit import (
    compute_credit_cost,
    jar_at_due,
    obligation_impact,
)
from yofina_forecast.runner import Pipeline
from yofina_forecast.settings import ForecastSettings
from yofina_ml.params import MLParams
from yofina_planner.engine import evaluate, obligation_ratio_figures, passed_rule_ids
from yofina_planner.facts import SuitabilityFacts, facts_from_rows
from yofina_planner.rules import cached_rules

log = logging.getLogger("yofina.forecast.afford")

MAX_OPTIONS = 4
JAR_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
MAX_VND = 99_999_999_999_999
SeriesPoint = tuple[date, int, int, int]  # ngày, P10, P50, P90 số dư cuối ngày


# =====================================================================================
# Hàm thuần: kiểm một hũ
# =====================================================================================
def shifted(series: Sequence[SeriesPoint], amount_vnd: int, start: date) -> list[SeriesPoint]:
    """Chuỗi sau khi trừ `amount_vnd` khỏi mọi đường từ ngày `start` trở đi (mọi phân vị dịch đúng `amount_vnd`)."""
    return [
        (d, p10 - amount_vnd, p50 - amount_vnd, p90 - amount_vnd)
        if d >= start
        else (d, p10, p50, p90)
        for d, p10, p50, p90 in series
    ]


def jar_check(
    *,
    jar: Mapping[str, str],
    balance_now_vnd: int,
    series: Sequence[SeriesPoint],
    origin: date,
    payday: date,
    runout_before: date | None,
    amount_vnd: int,
    pay_date: date,
    short_floor_vnd: int,
    tight_floor_vnd: int,
    runout_threshold_vnd: int,
) -> dict[str, Any]:
    """`JarCheck` của một hũ nếu chi `amount_vnd` ngày `pay_date` bằng tiền hũ này (xem docstring module cho luật trạng thái).

    Chi vào ngày tương lai: số dư lúc chi là số dư P50 cuối ngày hôm trước. Riêng chi ĐÚNG hoặc SAU ngày lương kế (phương án "Hoãn
    tới kỳ lương"): lương đã về hũ trong ngày đó nên số dư lúc chi là số dư P50 cuối chính ngày chi (đã gồm lương và các khoản đến hạn
    cùng ngày, cách tính thận trọng), và cửa sổ xét hụt/sát là từ ngày chi tới hết khoảng dự báo, vì các ngày trước kỳ lương không
    bị khoản chi này đụng tới."""
    first = origin + timedelta(days=1)
    start = max(pay_date, first)
    after_payday = pay_date >= payday
    if pay_date <= origin:
        before = balance_now_vnd
    else:
        on = pay_date if after_payday else pay_date - timedelta(days=1)
        prior = next((p50 for d, _a, p50, _b in series if d == on), None)
        before = prior if prior is not None else balance_now_vnd
    after_balance = before - amount_vnd
    after = shifted(series, amount_vnd, start)
    if after_payday:
        window = [x for x in after if x[0] >= start]
    else:
        window = [x for x in after if first <= x[0] < payday]
    min_p50 = min((x[2] for x in window), default=None)
    min_p10 = min((x[1] for x in window), default=None)
    lows = [v for v in (min_p50, after_balance) if v is not None]
    if after_balance < short_floor_vnd or (min_p50 is not None and min_p50 < short_floor_vnd):
        status = "short"
    elif min_p10 is not None and min_p10 < tight_floor_vnd:
        status = "tight"
    else:
        status = "ok"
    runout_after = next(
        (d for d, _a, p50, _b in after if d >= start and p50 <= runout_threshold_vnd), None
    )
    out: dict[str, Any] = {
        "jar": dict(jar),
        "status": status,
        "balance_before_vnd": before,
        "balance_after_vnd": after_balance,
    }
    if runout_before:
        out["runout_date_before"] = runout_before.isoformat()
    if runout_after:
        out["runout_date_after"] = runout_after.isoformat()
    if status != "ok" and runout_after:
        out["days_earlier"] = max(0, ((runout_before or payday) - runout_after).days)
    if status == "short":
        out["shortfall_vnd"] = max(0, short_floor_vnd - min(lows))
    return out


def _defer_summary(check: Mapping[str, Any], jar_name: str, payday: date) -> str:
    """Câu của phương án "Hoãn tới kỳ lương", dựng từ số của `jar_check` (chi ngày lương, sau khi lương về). Còn sát hoặc hụt thì nói
    rõ vì sao: số dư dự kiến lúc chi (đã gồm lương) và ngày hũ cạn hoặc phần thiếu sau khi chi."""
    st = check["status"]
    head = f"{STATUS_WORD[st]}: chi ngày lương {dm(payday)}, khi tiền lương đã về hũ {jar_name}"
    if st == "ok":
        return f"{head}; còn {format_vnd(check['balance_after_vnd'])} sau khi chi."
    have = f"lúc đó hũ dự kiến có {format_vnd(check['balance_before_vnd'])}"
    if st == "tight":
        return f"{head}, nhưng {have} nên dễ thiếu nếu chi nhiều hơn dự kiến."
    where = (
        f"hũ vẫn cạn ngày {dm(check['runout_date_after'])}"
        if check.get("runout_date_after")
        else "hũ vẫn âm"
    )
    return f"{head}, nhưng {have}; {where}, thiếu khoảng {format_vnd(check.get('shortfall_vnd', 0))}."


def jar_headline(check: Mapping[str, Any], payday: date, amount_vnd: int) -> str:
    name = check["jar"]["name"]
    st = check["status"]
    if st == "ok":
        return (
            f"Đủ: hũ {name} vẫn đủ tới kỳ lương {dm(payday)} sau khi chi {format_vnd(amount_vnd)}."
        )
    if st == "tight":
        extra = (
            f", cạn sớm {check['days_earlier']} ngày"
            if check.get("days_earlier")
            else ", còn rất ít tiền"
        )
        return f"Sát: hũ {name} dự kiến{extra} trước kỳ lương {dm(payday)}."
    return (
        f"Hụt: hũ {name} dự kiến hụt khoảng {format_vnd(check.get('shortfall_vnd', 0))} "
        f"trước kỳ lương {dm(payday)}."
    )


# =====================================================================================
# Engine
# =====================================================================================
class AffordabilityEngine:
    def __init__(
        self,
        pipeline: Pipeline,
        ledger_repo: Any,
        ref: Any,
        settings: ForecastSettings,
        *,
        rules: Any = None,
    ) -> None:
        self.pipeline = pipeline
        self.repo = ledger_repo
        self.ref = ref
        self.s = settings
        self._rules = rules

    @property
    def rules(self):  # type: ignore[no-untyped-def]
        return self._rules or cached_rules()

    # ----------------------------------------------------------------------------------------------
    @staticmethod
    def _args(
        amount_vnd: Any, funding_source: Any, jar: Any, label: Any, pay_date: Any
    ) -> tuple[int, str | None, str | None, str | None, date | None]:
        if isinstance(amount_vnd, bool):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "amount_vnd phải là số nguyên dương.")
        try:
            amount = to_vnd(amount_vnd)
        except (TypeError, ValueError):
            raise YofinaError(
                ErrorCode.PARAMS_INVALID, "amount_vnd phải là số nguyên dương."
            ) from None
        if not 1 <= amount <= MAX_VND:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "amount_vnd phải là số nguyên dương.")
        funding = None if funding_source in (None, "") else funding_source
        if funding not in (None, "jar", "credit"):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "funding_source phải là jar hoặc credit.")
        jar_code = None if jar in (None, "") else jar
        if jar_code is not None and not (
            isinstance(jar_code, str) and JAR_CODE_RE.fullmatch(jar_code)
        ):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "jar không phải mã hũ hợp lệ.")
        text = None
        if label not in (None, ""):
            if not isinstance(label, str) or not 1 <= len(label.strip()) <= 60:
                raise YofinaError(ErrorCode.PARAMS_INVALID, "label dài tối đa 60 ký tự.")
            text = label.strip()
        when = None
        if pay_date not in (None, ""):
            try:
                when = date.fromisoformat(str(pay_date))
            except ValueError:
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID, "date phải có dạng YYYY-MM-DD."
                ) from None
        return amount, funding, jar_code, text, when

    # ----------------------------------------------------------------------------------------------
    def check(
        self,
        user_id: str,
        *,
        amount_vnd: Any,
        funding_source: Any = None,
        jar: Any = None,
        label: Any = None,
        pay_date: Any = None,
    ) -> dict[str, Any]:
        amount, funding, jar_code, text, when = self._args(
            amount_vnd, funding_source, jar, label, pay_date
        )
        now = self.pipeline.now()
        with ThreadPoolExecutor(max_workers=5) as pool:
            f_view = pool.submit(self.repo.jar_view, user_id)
            f_user = pool.submit(self.repo.user_row, user_id)
            f_sum = pool.submit(self.repo.forecast_summaries, user_id)
            f_obl = pool.submit(self.repo.list_obligations, user_id, status="active", limit=100)
            f_line = pool.submit(self.repo.credit_line, user_id)
            view, user, summaries = f_view.result(), f_user.result(), f_sum.result()
            obligations, line = f_obl.result(), f_line.result()
        if (
            view.clock_offset_days is None
            or not user
            or user["monthly_salary_vnd"] is None
            or user["payday_day"] is None
        ):
            raise YofinaError(
                ErrorCode.PROFILE_INCOMPLETE, "Bạn chưa khai lương và ngày nhận lương."
            )
        today = app_today(view.clock_offset_days, now, self.s.tz)
        pay_on = when or today
        if pay_on < today:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "date không được trước hôm nay mô phỏng.")

        user_jars = [j for j in view.jars if j.get("kind") != "system"]
        chosen = None
        if jar_code is not None:
            chosen = view.jar(jar_code)
            if chosen is None:
                raise YofinaError(ErrorCode.JAR_NOT_FOUND, "Không tìm thấy hũ bạn chọn.")
            if chosen.get("kind") == "system":
                raise YofinaError(
                    ErrorCode.FORECAST_NOT_APPLICABLE, "Hũ hệ thống không có dự báo."
                )
        # Nguồn hũ: kiểm MỌI hũ chi tiêu (để thẻ có sẵn phương án đổi hũ), hũ người dùng chọn đứng đầu.
        candidates: list[Mapping[str, Any]] = []
        if funding != "credit":
            candidates = [j for j in user_jars if j["kind"] == "spending"]
            if chosen is not None:
                candidates = [chosen] + [j for j in candidates if j["code"] != chosen["code"]]
        candidates = candidates[:8]

        # hũ trả nghĩa vụ Trả sau (khi xét tín dụng)
        want_credit = funding in (None, "credit")
        facts = facts_from_rows(
            today=today,
            user=user,
            jars=view.jars,
            obligations=obligations,
            window_days=self.s.horizon_days,
        )
        credit_ctx = self._credit_context(
            want_credit,
            funding,
            amount,
            pay_on,
            today,
            line,
            obligations,
            facts,
            user_jars,
            jar_code,
        )
        needed = [j["code"] for j in candidates]
        if credit_ctx is not None and credit_ctx["pay_jar"] not in needed:
            needed.append(credit_ctx["pay_jar"])
        summaries = self._ensure_forecasts(user_id, needed, summaries, today, now)
        by_summary = {r["jar_code"]: r for r in summaries}
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {c: pool.submit(self.repo.forecast_series, user_id, c) for c in needed}
            series = {c: self._series(f.result()) for c, f in futures.items()}
        stale = any(self._is_stale(by_summary[c], today, now) for c in needed if c in by_summary)

        short_floor = self.s.affordability_short_p50_floor_vnd
        tight_floor = self.s.affordability_tight_p10_floor_vnd
        runout_thr = MLParams().runout_balance_threshold_vnd
        checks: list[dict[str, Any]] = []
        for j in candidates:
            code = j["code"]
            summ = by_summary[code]
            if not series.get(code):
                raise YofinaError(
                    ErrorCode.FORECAST_UNAVAILABLE,
                    "Chưa có dự báo cho hũ này, thử lại sau ít phút.",
                )
            checks.append(
                jar_check(
                    jar=self._ref(j),
                    balance_now_vnd=int_of(j["balance_vnd"]),
                    series=series[code],
                    origin=to_date(summ["run_app_date"]),  # type: ignore[arg-type]
                    payday=to_date(summ["payday_date"]),  # type: ignore[arg-type]
                    runout_before=to_date(summ.get("runout_date")),
                    amount_vnd=amount,
                    pay_date=pay_on,
                    short_floor_vnd=short_floor,
                    tight_floor_vnd=tight_floor,
                    runout_threshold_vnd=runout_thr,
                )
            )

        basis = self._basis(needed, by_summary, today, now, stale)
        credit_data = (
            self._credit_data(
                credit_ctx,
                series,
                by_summary,
                user_jars,
                short_floor,
                tight_floor,
                basis,
                facts,
                amount,
            )
            if credit_ctx is not None
            else None
        )
        if funding == "credit" and credit_data is None:
            raise YofinaError(
                ErrorCode.CREDIT_LIMIT_EXCEEDED, "Không dùng được Trả sau cho khoản này."
            )

        # --- kết luận ------------------------------------------------------------------------------
        payday = to_date(by_summary[needed[0]]["payday_date"]) if needed else None
        selected = jar_code if funding != "credit" else None
        if funding == "credit":
            verdict = credit_data["status"]  # type: ignore[index]
            headline = credit_data["headline"]  # type: ignore[index]
            funding_out = "credit"
        else:
            funding_out = "jar"
            if selected:
                main = next(c for c in checks if c["jar"]["code"] == selected)
                verdict = main["status"]
                headline = jar_headline(main, payday, amount) if payday else STATUS_WORD[verdict]
            elif checks:
                ranked = sorted(
                    checks,
                    key=lambda c: (STATUS_RANK[c["status"]], -(c["balance_after_vnd"])),
                )
                main = ranked[0]
                verdict = main["status"]
                headline = (
                    jar_headline(main, payday, amount)
                    if verdict == "ok" and payday
                    else self._multi_headline(checks, main, payday)
                )
            else:
                verdict = credit_data["status"] if credit_data else "short"
                headline = (
                    credit_data["headline"]
                    if credit_data
                    else "Hụt: chưa có hũ chi tiêu nào để chi khoản này."
                )

        options = self._options(
            checks=checks,
            selected=selected,
            funding=funding,
            amount=amount,
            pay_on=pay_on,
            payday=payday,
            credit_data=credit_data,
            series=series,
            by_summary=by_summary,
            user_jars=user_jars,
            facts=facts,
            verdict=verdict,
            thresholds=(short_floor, tight_floor, runout_thr),
            origin=today,
        )

        card: dict[str, Any] = {
            "verdict": verdict,
            "headline": clip(headline, 160),
            "amount_vnd": amount,
            "funding_source": funding_out,
            "jar_checks": checks,
            "options": options,
            "basis": basis,
        }
        if text:
            card["label"] = text
        if when:
            card["pay_date"] = when.isoformat()
        if selected:
            card["selected_jar_code"] = selected
        if credit_data is not None:
            card["credit"] = credit_data
            if credit_data.get("cautions") and funding == "credit":
                card["cautions"] = credit_data["cautions"]
        data = AffordabilityCardData.model_validate(card).model_dump(mode="json", exclude_none=True)
        return {
            "status": "OK",
            "as_of": format_instant(now),
            "app_date": today.isoformat(),
            "data": data,
        }

    # ----------------------------------------------------------------------------------------------
    @staticmethod
    def _ref(j: Mapping[str, Any]) -> dict[str, str]:
        return {
            "code": j["code"],
            "name": j["name"],
            "color_key": j["color_key"],
            "icon_key": j["icon_key"],
        }

    @staticmethod
    def _series(rows: Sequence[Mapping[str, Any]]) -> list[SeriesPoint]:
        return sorted(
            (
                (
                    to_date(r["day"]),  # type: ignore[misc]
                    int_of(r["balance_p10_vnd"]),
                    int_of(r["balance_p50_vnd"]),
                    int_of(r["balance_p90_vnd"]),
                )
                for r in rows
            ),
            key=lambda x: x[0],
        )

    def _is_stale(self, summary: Mapping[str, Any], today: date, now: datetime) -> bool:
        if to_date(summary["run_app_date"]) != today:
            return True
        return (now - summary["computed_at"]).total_seconds() > self.s.freshness_seconds

    def _ensure_forecasts(
        self,
        user_id: str,
        codes: Sequence[str],
        summaries: list[Any],
        today: date,
        now: datetime,
    ) -> list[Any]:
        """Hũ chưa có dự báo hoặc dự báo cũ thì tính lại MỘT lần (như `get_forecast`); không tính được mà còn bản cũ thì dùng bản
        cũ và đánh dấu `stale`; không có gì thì FORECAST_UNAVAILABLE."""
        by = {r["jar_code"]: r for r in summaries}
        if all(c in by and not self._is_stale(by[c], today, now) for c in codes):
            return summaries
        try:
            self.pipeline.run_user(user_id, trigger="read")
            summaries = self.repo.forecast_summaries(user_id)
        except Exception as exc:  # không tính được: giữ bản cũ nếu có
            log.warning("recompute_failed %s", type(exc).__name__)
        by = {r["jar_code"]: r for r in summaries}
        missing = [c for c in codes if c not in by]
        if missing:
            raise YofinaError(
                ErrorCode.FORECAST_UNAVAILABLE,
                "Chưa có dự báo cho hũ này và chưa tính được ngay, thử lại sau ít phút.",
            )
        return summaries

    def _basis(
        self,
        codes: Sequence[str],
        by_summary: Mapping[str, Mapping[str, Any]],
        today: date,
        now: datetime,
        stale: bool,
    ) -> dict[str, Any]:
        rows = [by_summary[c] for c in codes if c in by_summary]
        if not rows:  # chỉ xét Trả sau mà không có hũ nào để dự báo: không xảy ra vì hũ trả luôn có trong `codes`
            raise YofinaError(ErrorCode.FORECAST_UNAVAILABLE, "Chưa có dự báo.")
        newest = max(rows, key=lambda r: r["computed_at"])
        basis: dict[str, Any] = {
            "computed_at": format_instant(newest["computed_at"]),
            "stale": bool(stale),
            "confidence_band": min_band([r["confidence_band"] for r in rows]),
            "is_initial_estimate": any(bool(r["is_initial_estimate"]) for r in rows),
            "history_days": max(int(r["history_days"]) for r in rows),
        }
        cov = [float(r["data_coverage"]) for r in rows if r.get("data_coverage") is not None]
        if cov:
            basis["coverage"] = round(min(cov), 3)
        return ForecastBasis.model_validate(basis).model_dump(mode="json", exclude_none=True)

    # --- Trả sau ----------------------------------------------------------------------------------
    def _credit_context(
        self,
        want_credit: bool,
        funding: str | None,
        amount: int,
        pay_on: date,
        today: date,
        line: Mapping[str, Any] | None,
        obligations: Sequence[Mapping[str, Any]],
        facts: SuitabilityFacts,
        user_jars: Sequence[Mapping[str, Any]],
        jar_code: str | None,
    ) -> dict[str, Any] | None:
        """Chi phí của món và hũ trả nghĩa vụ; None khi không xét Trả sau hoặc không dùng được (không có hạn mức, vượt hạn mức).
        Chỉ xét riêng Trả sau (`funding = credit`) mà không dùng được thì báo lỗi."""
        if not want_credit:
            return None
        product = (line or {}).get("product_code") or BNPL_PRODUCT_CODE
        label = self.ref.product_label(product, today)
        due = bnpl_due_date(int(line["due_day"]), pay_on) if line else None
        existing = (
            next(
                (
                    o
                    for o in obligations
                    if o["kind"] == "bnpl"
                    and to_date(o["due_date"]) == due
                    and o["status"] == "active"
                ),
                None,
            )
            if due
            else None
        )
        fees = self.ref.active_fees(product, today)
        late = next((f for f in fees if f.condition_code == "overdue" and f.amount_vnd), None)
        try:
            if due is None:
                raise YofinaError(ErrorCode.CREDIT_LIMIT_EXCEEDED, f"Bạn chưa có hạn mức {label}.")
            cost = compute_credit_cost(
                principal_vnd=amount,
                due_date=due,
                existing_due_vnd=int_of(existing["amount_vnd"]) if existing else None,
                product_label=label,
                line=line,
                fee=self.ref.bnpl_monthly_fee(today),
                late_fee=late,
            )
        except YofinaError as exc:
            if funding == "credit" or exc.code != ErrorCode.CREDIT_LIMIT_EXCEEDED:
                raise
            return None
        default_pay = next((j["code"] for j in user_jars if j["kind"] == "obligation"), None)
        pay = (existing.get("pay_jar_code") if existing else None) or default_pay
        if pay is None or all(j["code"] != pay for j in user_jars):
            pay = jar_code or next((j["code"] for j in user_jars if j["kind"] == "spending"), None)
        if pay is None:
            return None
        dues = [
            ob.amount_vnd
            for ob, d in facts.dues_between(due, due)  # type: ignore[arg-type]
            if facts.pay_jar_of(ob) == pay
        ]
        return {"cost": cost, "pay_jar": pay, "existing_on_jar": sum(dues), "due": due}

    def _credit_data(
        self,
        cc: Mapping[str, Any],
        series: Mapping[str, list[SeriesPoint]],
        by_summary: Mapping[str, Mapping[str, Any]],
        user_jars: Sequence[Mapping[str, Any]],
        short_floor: int,
        tight_floor: int,
        basis: Mapping[str, Any],
        facts: SuitabilityFacts,
        amount: int,
    ) -> dict[str, Any]:
        cost = cc["cost"]
        pay = cc["pay_jar"]
        due: date = cc["due"]
        charge = cost["principal_vnd"] + cost["fee_added_vnd"]
        after = shifted(series[pay], charge, due)
        jar = next(j for j in user_jars if j["code"] == pay)
        entry = jar_at_due(
            jar=self._ref(jar),
            days=after,
            due_date=due,
            due_vnd=cc["existing_on_jar"] + charge,
            short_floor_vnd=short_floor,
            tight_floor_vnd=tight_floor,
        )
        ratio = obligation_ratio_figures(facts, cost["item_cost_vnd"], self.rules)
        verdict = evaluate(
            Proposal(
                kind="use_credit", amount_vnd=amount, funding_source="credit", origin="user_request"
            ),
            facts,
            self.rules,
            added_obligation_vnd=cost["item_cost_vnd"],
        )
        cautions = [{"rule_id": v.rule_id, "text": v.message[:140]} for v in verdict.violations][:3]
        return obligation_impact(
            cost=cost, at_due=[entry], ratio=ratio, cautions=cautions, basis=basis
        )

    # --- phương án --------------------------------------------------------------------------------
    @staticmethod
    def _multi_headline(
        checks: Sequence[Mapping[str, Any]], main: Mapping[str, Any], payday: date | None
    ) -> str:
        st = main["status"]
        if st == "tight":
            return f"Sát: hũ {main['jar']['name']} là hũ khá nhất, vẫn dự kiến còn rất ít tiền trước kỳ lương."
        return (
            f"Hụt: không hũ chi tiêu nào đủ; hũ {main['jar']['name']} gần đủ nhất, "
            f"hụt khoảng {format_vnd(main.get('shortfall_vnd', 0))} trước kỳ lương."
        )

    def _proposal_ok(
        self,
        facts: SuitabilityFacts,
        proposal: Proposal,
        added: int | None = None,
    ) -> tuple[bool, list[str]]:
        verdict = evaluate(proposal, facts, self.rules, added_obligation_vnd=added)
        return verdict.ok, passed_rule_ids(verdict)

    def _options(
        self,
        *,
        checks: Sequence[Mapping[str, Any]],
        selected: str | None,
        funding: str | None,
        amount: int,
        pay_on: date,
        payday: date | None,
        credit_data: Mapping[str, Any] | None,
        series: Mapping[str, list[SeriesPoint]],
        by_summary: Mapping[str, Mapping[str, Any]],
        user_jars: Sequence[Mapping[str, Any]],
        facts: SuitabilityFacts,
        verdict: str,
        thresholds: tuple[int, int, int],
        origin: date,
    ) -> list[dict[str, Any]]:
        """Phương án tất định. Chỉ khi chưa "đủ" mới đưa phương án; mỗi phương án đã qua bộ luật, bị block thì loại."""
        if verdict == "ok":
            return []
        short_floor, tight_floor, runout_thr = thresholds
        out: list[dict[str, Any]] = []
        base_jar = selected or (
            max(checks, key=lambda c: c["balance_after_vnd"])["jar"]["code"] if checks else None
        )

        # 1. đổi sang hũ khá nhất khác
        others = [c for c in checks if c["jar"]["code"] != selected]
        if others:
            alt = min(others, key=lambda c: (STATUS_RANK[c["status"]], -c["balance_after_vnd"]))
            if STATUS_RANK[alt["status"]] < STATUS_RANK[verdict]:
                prop = Proposal(
                    kind="switch_jar",
                    amount_vnd=amount,
                    funding_source="jar",
                    jar_code=alt["jar"]["code"],
                    is_essential=False,
                    origin="recommendation",
                )
                ok, passed = self._proposal_ok(facts, prop)
                if ok:
                    name = alt["jar"]["name"]
                    out.append(
                        {
                            "option_id": f"switch_{alt['jar']['code']}"[:32],
                            "kind": "switch_jar",
                            "label": clip(f"Dùng tiền hũ {name}", 60),
                            "summary": clip(
                                f"{STATUS_WORD[alt['status']]}: hũ {name} còn {format_vnd(alt['balance_after_vnd'])} sau khi chi.",
                                200,
                            ),
                            "status": alt["status"],
                            "metrics": [
                                {
                                    "label": f"Hũ {name}",
                                    "before": format_vnd(alt["balance_before_vnd"]),
                                    "after": format_vnd(alt["balance_after_vnd"]),
                                }
                            ],
                            "checked_rules": passed[:8],
                        }
                    )

        # 2. Trả sau (mô phỏng)
        if credit_data is not None and funding != "credit":
            cost = credit_data["cost"]
            ok, passed = self._proposal_ok(
                facts,
                Proposal(
                    kind="use_credit",
                    amount_vnd=amount,
                    funding_source="credit",
                    origin="recommendation",
                ),
                cost["item_cost_vnd"],
            )
            if ok:
                out.append(
                    {
                        "option_id": "use_credit",
                        "kind": "use_credit",
                        "label": clip(f"Trả bằng {cost['product_label']}", 60),
                        "summary": clip(
                            f"Món này tốn {format_vnd(cost['item_cost_vnd'])}; ngày {dm(cost['due_date'])} phải trả tổng "
                            f"{format_vnd(cost['total_due_vnd'])}.",
                            200,
                        ),
                        "status": credit_data["status"],
                        "metrics": [
                            {"label": "Món này tốn", "after": format_vnd(cost["item_cost_vnd"])},
                            {
                                "label": f"Phải trả ngày {dm(cost['due_date'])}",
                                "before": format_vnd(cost["existing_due_vnd"])
                                if cost["existing_due_vnd"]
                                else "chưa có",
                                "after": format_vnd(cost["total_due_vnd"]),
                            },
                        ],
                        "checked_rules": passed[:8],
                    }
                )

        # 3. hoãn tới kỳ lương và 4. chia làm hai lần (tính trên hũ đang xét)
        if base_jar and payday and base_jar in series and base_jar in by_summary:
            summ = by_summary[base_jar]
            jar = next(j for j in user_jars if j["code"] == base_jar)
            common = dict(
                jar=self._ref(jar),
                balance_now_vnd=int_of(jar["balance_vnd"]),
                series=series[base_jar],
                origin=to_date(summ["run_app_date"]),
                payday=payday,
                runout_before=to_date(summ.get("runout_date")),
                short_floor_vnd=short_floor,
                tight_floor_vnd=tight_floor,
                runout_threshold_vnd=runout_thr,
            )
            deferred = jar_check(amount_vnd=amount, pay_date=payday, **common)  # type: ignore[arg-type]
            out.append(
                {
                    "option_id": "defer_payday",
                    "kind": "defer",
                    "label": "Hoãn tới kỳ lương",
                    "summary": clip(_defer_summary(deferred, jar["name"], payday), 200),
                    "status": deferred["status"],
                    "metrics": [
                        {"label": "Ngày chi", "after": dm(payday)},
                        {
                            "label": f"Hũ {jar['name']} lúc chi",
                            "before": format_vnd(deferred["balance_before_vnd"]),
                            "after": format_vnd(deferred["balance_after_vnd"]),
                        },
                    ],
                    "checked_rules": [],
                }
            )
            half = amount // 2
            if half >= 1 and amount - half >= 1:
                first_half = jar_check(amount_vnd=half, pay_date=pay_on, **common)  # type: ignore[arg-type]
                out.append(
                    {
                        "option_id": "split_two",
                        "kind": "split",
                        "label": "Chia làm hai lần",
                        "summary": clip(
                            f"{STATUS_WORD[first_half['status']]}: chi {format_vnd(half)} bây giờ, "
                            f"{format_vnd(amount - half)} sau kỳ lương {dm(payday)}.",
                            200,
                        ),
                        "status": first_half["status"],
                        "metrics": [
                            {"label": "Lần 1 (bây giờ)", "after": format_vnd(half)},
                            {"label": f"Lần 2 ({dm(payday)})", "after": format_vnd(amount - half)},
                        ],
                        "checked_rules": [],
                    }
                )
        best_status = best([o["status"] for o in out])
        for o in out:
            if o["status"] == best_status == "ok":
                o["recommended"] = True
                break
        return out[:MAX_OPTIONS]


__all__ = ["AffordabilityEngine", "jar_check", "shifted", "worst"]
