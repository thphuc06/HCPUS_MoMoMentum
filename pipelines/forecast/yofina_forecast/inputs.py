"""Dựng `ForecastInputs` (hợp đồng ML) từ dữ liệu một người dùng đã đọc từ Aurora. HÀM THUẦN: không I/O, không đồng hồ.

Nguồn là các dòng của hàm DB `app_get_forecast_context` (db/migrations/0009), gồm ngày mô phỏng, hồ sơ, hũ kèm chuỗi chi tiêu
theo ngày đã lấp ngày 0, nghĩa vụ đang hoạt động và dữ kiện độ phủ. Quy tắc theo `ml/README.md` ("Pipeline dựng `ForecastInputs`
thế nào cho đúng") và `contracts/README.md` ("Mốc trên biểu đồ"):

- Lịch sử chi tiêu: chỉ khoản chi trừ tiền hũ, không gắn nghĩa vụ (hàm DB lo); `history_start` là ngày có dữ liệu sớm nhất của
  người dùng, không lùi quá cửa sổ cấu hình.
- Lương: `split_amount(lương đã khai, tỷ lệ các hũ)` vào đúng ngày lương trong horizon (cùng quy tắc `confirm_salary`).
- Nghĩa vụ: mở rộng chu kỳ trong horizon bằng `yofina_core.schedule.expand_due_dates`; quá hạn tính vào ngày đầu; nghĩa vụ chưa có hũ
  trả gán cho hũ `obligation` đầu tiên (theo `sort_order`), không có hũ đó thì bỏ và ghi `unassigned_obligations`.
- Hạt ngẫu nhiên tất định theo người dùng (băm `user_id`), nên cùng dữ liệu cho cùng dự báo qua nhiều lần chạy.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from yofina_core.clock import next_payday as next_payday_of
from yofina_core.clock import payday_dates
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.schedule import expand_due_dates
from yofina_core.wallet import split_amount
from yofina_forecast.settings import ForecastSettings
from yofina_ml.calibration import calibrated_config
from yofina_ml.contract import check_inputs
from yofina_ml.types import (
    CoverageInputs,
    ForecastConfig,
    ForecastInputs,
    JarInput,
    ScheduledFlow,
)

FORECAST_JAR_KINDS = ("spending", "saving", "obligation")  # hũ hệ thống không được dự báo
SALARY_LABEL = "Lương"
#: hàm DB `app_get_daily_spend` chặn ở số dòng (hũ, ngày) này
SPEND_ROWS_CAP = 5000


@dataclass(frozen=True)
class Context:
    """Kết quả đọc `app_get_forecast_context` đã gom theo phần."""

    meta: Mapping[str, Any]
    jars: tuple[Mapping[str, Any], ...]
    obligations: tuple[Mapping[str, Any], ...]

    @classmethod
    def from_rows(cls, rows: Iterable[Mapping[str, Any]]) -> Context | None:
        """None khi không có hồ sơ người dùng (hàm DB không trả dòng nào)."""
        meta: Mapping[str, Any] | None = None
        jars: list[Mapping[str, Any]] = []
        obligations: list[Mapping[str, Any]] = []
        for r in rows:
            section, payload = r["section"], r["payload"]
            if section == "meta":
                meta = payload
            elif section == "jar":
                jars.append(payload)
            elif section == "obligation":
                obligations.append(payload)
        if meta is None:
            return None
        return cls(meta=meta, jars=tuple(jars), obligations=tuple(obligations))

    @property
    def app_date(self) -> date:
        return date.fromisoformat(str(self.meta["app_date"]))


@dataclass(frozen=True)
class Built:
    inputs: ForecastInputs
    #: mã các hũ được dự báo (đúng thứ tự `inputs.jars`)
    jar_codes: tuple[str, ...]
    #: chẩn đoán của pipeline, ghi vào `forecast_runs.params["pipeline"]`
    notes: dict[str, Any] = field(default_factory=dict)


def user_seed(user_id: str) -> int:
    """Hạt gốc cố định theo người dùng (31 bit để vừa mọi kiểu số nguyên): hạt từng hũ do ML suy ra từ (seed, ngày gốc, mã hũ)."""
    return int.from_bytes(hashlib.sha256(user_id.encode("utf-8")).digest()[:4], "big") & 0x7FFFFFFF


def _int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return int(Decimal(str(value)).to_integral_value())


def _dense_history(values: Sequence[Any], days: int) -> tuple[int, ...]:
    """Đúng `days` giá trị cũ -> mới; thiếu thì đệm 0 ở đầu, thừa thì bỏ phần cũ."""
    series = [max(_int(v), 0) for v in values]
    if len(series) < days:
        series = [0] * (days - len(series)) + series
    return tuple(series[len(series) - days :]) if days else ()


def make_config(settings: ForecastSettings, user_id: str, *, n_paths: int) -> ForecastConfig:
    """`ForecastConfig` từ cấu hình: gốc là `calibrated_config()` (cờ xác suất theo kết quả backtest); công tắc cấu hình tắt được.
    Ngưỡng lịch sử của cổng xác suất (BR-31) mặc định theo hiệu chỉnh; có cấu hình thì ghi đè qua `extra["calibration"]`."""
    base = calibrated_config()
    gate = {
        kind: {"probability_min_history_days": days}
        for kind, days in (
            ("dense", settings.probability_min_history_days_dense),
            ("sparse", settings.probability_min_history_days_sparse),
        )
        if days is not None
    }
    return replace(
        base,
        n_paths=n_paths,
        seed=user_seed(user_id),
        cold_start_min_days=settings.cold_start_min_days,
        aci_gamma=settings.aci_gamma,
        coverage_target=settings.coverage_target,
        short_threshold=settings.short_threshold,
        tight_threshold=settings.tight_threshold,
        band_high_min_days=settings.band_high_min_days,
        band_high_min_coverage=settings.band_high_min_coverage,
        band_medium_min_days=settings.band_medium_min_days,
        probability_enabled=bool(settings.probability_enabled and base.probability_enabled),
        extra={**base.extra, "calibration": gate} if gate else base.extra,
    )


def expand_obligations(
    obligations: Sequence[Mapping[str, Any]],
    forecast_jar_codes: Sequence[str],
    default_pay_jar: str | None,
    app_date: date,
    horizon_days: int,
) -> tuple[dict[str, list[ScheduledFlow]], list[str]]:
    """Nghĩa vụ đang hoạt động -> các khoản tiền ra theo từng hũ trong horizon; trả thêm tên các khoản không gán được hũ."""
    first = app_date + timedelta(days=1)
    through = app_date + timedelta(days=horizon_days)
    known = set(forecast_jar_codes)
    flows: dict[str, list[ScheduledFlow]] = {}
    unassigned: list[str] = []
    for ob in obligations:
        if ob.get("status", "active") != "active":
            continue
        jar = ob.get("pay_jar_code") or default_pay_jar
        if jar not in known:
            unassigned.append(str(ob.get("name", ""))[:60])
            continue
        due = date.fromisoformat(str(ob["due_date"]))
        amount = _int(ob["amount_vnd"])
        lo, hi = ob.get("amount_min_vnd"), ob.get("amount_max_vnd")
        rng = (_int(lo), _int(hi)) if lo is not None and hi is not None else (None, None)
        for d in expand_due_dates(
            due, str(ob["cycle"]), ob.get("due_day"), first=first, through=through
        ):
            flows.setdefault(jar, []).append(
                ScheduledFlow(
                    date=d,
                    kind="obligation",
                    label=str(ob["name"])[:60],
                    amount_vnd=amount,
                    amount_min_vnd=rng[0],
                    amount_max_vnd=rng[1],
                    ref_id=str(ob["id"]),
                )
            )
    for lst in flows.values():
        lst.sort(key=lambda f: (f.date, f.label))
    return flows, unassigned


def build_inputs(ctx: Context, settings: ForecastSettings, user_id: str, *, n_paths: int) -> Built:
    """`ForecastInputs` đúng hợp đồng. Hồ sơ chưa khai lương hoặc ngày nhận -> `PROFILE_INCOMPLETE`."""
    profile = ctx.meta.get("profile") or {}
    salary = profile.get("monthly_salary_vnd")
    payday_day = profile.get("payday_day")
    if salary is None or payday_day is None:
        raise YofinaError(ErrorCode.PROFILE_INCOMPLETE, "Chưa khai lương và ngày nhận lương.")
    salary_vnd, payday = _int(salary), int(payday_day)
    app_date = ctx.app_date
    horizon = settings.horizon_days
    history_start = date.fromisoformat(str(ctx.meta["history_start"]))
    history_days = max((app_date - history_start).days, 0)
    notes: dict[str, Any] = {}

    user_jars = [j for j in ctx.jars if j["kind"] != "system"]
    forecast_jars = sorted(
        (j for j in user_jars if j["kind"] in FORECAST_JAR_KINDS),
        key=lambda j: (j["sort_order"], j["code"]),
    )
    codes = [j["code"] for j in forecast_jars]
    if not codes:
        raise YofinaError(ErrorCode.FORECAST_UNAVAILABLE, "Chưa có hũ nào để dự báo.")
    default_pay = next((j["code"] for j in forecast_jars if j["kind"] == "obligation"), None)

    through = app_date + timedelta(days=horizon)
    pay_dates = tuple(payday_dates(payday, app_date, through))
    try:
        parts = split_amount(salary_vnd, [(j["code"], j["split_percent"]) for j in user_jars])
    except ValueError:
        parts = {}
        notes["salary_split_invalid"] = True  # tỷ lệ chia không đủ 100: không mô phỏng lương

    outflows, unassigned = expand_obligations(
        ctx.obligations, codes, default_pay, app_date, horizon
    )
    if unassigned:
        notes["unassigned_obligations"] = unassigned
    if int(ctx.meta.get("spend_rows") or 0) >= SPEND_ROWS_CAP:
        notes["spend_truncated"] = (
            True  # hàm DB chặn số dòng (hũ, ngày): lịch sử có thể thiếu phần cũ
        )

    jars: list[JarInput] = []
    for j in forecast_jars:
        part = parts.get(j["code"], 0)
        inflows = tuple(
            ScheduledFlow(date=d, kind="salary", label=SALARY_LABEL, amount_vnd=part)
            for d in pay_dates
            if part > 0
        )
        jars.append(
            JarInput(
                code=j["code"],
                kind=j["kind"],
                balance_vnd=_int(j["balance_vnd"]),
                split_percent=float(Decimal(str(j["split_percent"]))),
                history_start=history_start,
                daily_spend_vnd=_dense_history(j.get("spend") or [], history_days),
                inflows=inflows,
                outflows=tuple(outflows.get(j["code"], ())),
            )
        )

    cov = ctx.meta.get("coverage")
    coverage = (
        CoverageInputs(
            income_vnd=_int(cov["income_vnd"]),
            spend_vnd=_int(cov["spend_vnd"]),
            balance_start_vnd=_int(cov["balance_start_vnd"]),
            balance_end_vnd=_int(cov["balance_end_vnd"]),
        )
        if cov
        else None
    )
    inputs = ForecastInputs(
        app_date=app_date,
        horizon_days=horizon,
        next_payday=next_payday_of(payday, app_date),
        payday_dates=pay_dates,
        jars=tuple(jars),
        coverage=coverage,
        config=make_config(settings, user_id, n_paths=n_paths),
        payday_day=payday,
    )
    errors = check_inputs(inputs)
    if errors:
        raise YofinaError(
            ErrorCode.INTERNAL_ERROR, "Đầu vào dự báo sai hợp đồng: " + "; ".join(errors[:3])
        )
    return Built(inputs=inputs, jar_codes=tuple(codes), notes=notes)
