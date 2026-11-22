"""Họ bộ sinh (ii): theo PHIÊN MUA và GIỎ HÀNG, KHÁC HẲN họ hurdle-lognormal.

Khác ở cơ chế, để mô hình hurdle theo lịch (ô cuối tuần x nửa đầu kỳ lương) không tự khen mình:
- Không có xác suất có chi theo ngày. Phiên mua đến theo quá trình TÁI TẠO: khoảng cách giữa hai phiên ~ Gamma(k, .) (k lớn:
  đều đặn như đi chợ hằng tuần; k nhỏ: thất thường), rồi dịch tới thứ ưa thích (có thể là thứ ba, thứ tư chứ không phải
  cuối tuần).
- Giá trị phiên là GIỎ HÀNG: số món 1 + Poisson, mỗi món lognormal, thỉnh thoảng một món đắt (đuôi nặng).
- Ngân sách TỰ ĐIỀU CHỈNH khi gần hết tiền: hệ số phi = (phần ngân sách kỳ còn lại) / (phần thời gian kỳ còn lại) làm giảm cỡ giỏ
  và bỏ bớt phiên khi phi < 1. Vòng phản hồi này tạo TƯƠNG QUAN ÂM giữa các ngày trong kỳ (mô hình hurdle giả định ngày độc lập
  hoặc tương quan dương), nên là phép thử khó cho phần hiệu chỉnh tổng nhiều ngày.
- Hiệu ứng ngày lương là bậc tuyến tính giảm trong 10 ngày (không phải mũ), du lịch là chuỗi nhiều ngày liên tiếp.
- ĐIỂM GÃY lối sống: giá và cỡ giỏ tăng, phiên thưa đi, lương tăng.
Mọi tham số là đầu vào; ba cấu hình khác nhau về ngày lương, thứ ưa thích và cấu trúc hũ.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from yofina_ml.daycal import latest_payday
from yofina_ml.synth.base import (
    OBLIGATION_JAR,
    ObligationSpec,
    SynthJar,
    SynthPersona,
    build_ledger,
    payday_list,
    schedule_obligation_payments,
)


@dataclass(frozen=True)
class SessionParams:
    gap_mean: float  # khoảng cách trung bình giữa hai phiên (ngày)
    gap_shape: float  # hình dạng Gamma của khoảng cách (lớn: đều đặn)
    items_lambda: float  # số món thêm ~ Poisson
    price_med: float  # trung vị giá một món (VND)
    price_sigma: float
    pref_days: tuple[int, ...] = ()  # thứ ưa thích (0 = thứ hai); rỗng: không ưa thứ nào
    pref_strength: float = 0.0  # xác suất dịch phiên tới thứ ưa thích
    tail_prob: float = 0.0  # xác suất một món là món đắt
    tail_mult: float = 1.0
    payday_boost: float = 0.0  # tăng số món sau ngày lương, giảm tuyến tính trong 10 ngày
    adjust: float = 0.0  # độ mạnh tự điều chỉnh ngân sách (0: không)
    duration_mean: float = 1.0  # số ngày liên tiếp của một phiên (du lịch)
    brk_price: float = 1.0  # nhân giá sau điểm gãy
    brk_gap: float = 1.0  # nhân khoảng cách phiên sau điểm gãy


@dataclass(frozen=True)
class Config:
    payday_day: int
    salary_vnd: int
    splits: dict[str, float]
    jars: dict[str, SessionParams]
    break_at: int = 205
    raise_mult: float = 1.15  # lương tăng sau điểm gãy
    rent_vnd: int = 2_500_000
    rent_step_vnd: int = 0
    budget_fraction: float = 0.92  # người dùng định tiêu tối đa phần này của phần chia
    extra: dict[str, float] = field(default_factory=dict)


def _office() -> Config:
    return Config(
        payday_day=5, salary_vnd=10_000_000,
        splits={"an_uong": 26, "di_chuyen": 8, "giai_tri": 9, "mua_sam": 9, "du_lich": 7, "du_phong": 4, "nghia_vu": 37},
        jars={
            "an_uong": SessionParams(1.4, 3.0, 2.2, 26_000, 0.5, (5, 6), 0.25, 0.08, 4.0, 0.6, 0.8, brk_price=1.2, brk_gap=1.1),
            "di_chuyen": SessionParams(1.1, 10.0, 0.0, 16_000, 0.15, (0, 1, 2, 3, 4), 0.95, 0.04, 6.0, 0.1, 0.3, brk_price=1.5),
            "giai_tri": SessionParams(8.0, 3.0, 1.2, 70_000, 0.6, (4, 5), 0.6, 0.10, 3.0, 0.8, 0.9, brk_price=1.2),
            "mua_sam": SessionParams(17.0, 1.5, 1.5, 120_000, 0.8, (), 0.0, 0.15, 4.0, 1.0, 0.9, brk_price=1.25),
            "du_lich": SessionParams(60.0, 1.3, 0.0, 450_000, 0.5, (), 0.0, 0.0, 1.0, 0.0, 0.0, duration_mean=2.5),
            "du_phong": SessionParams(85.0, 1.0, 0.0, 900_000, 0.7, (), 0.0, 0.3, 2.0, 0.0, 0.0),
        },
        rent_vnd=2_600_000, rent_step_vnd=300_000,
    )  # fmt: skip


def _student() -> Config:
    return Config(
        payday_day=1, salary_vnd=4_500_000,
        splits={"an_uong": 36, "di_chuyen": 10, "giai_tri": 8, "mua_sam": 6, "du_lich": 4, "du_phong": 4, "nghia_vu": 32},
        jars={
            "an_uong": SessionParams(1.15, 4.0, 1.5, 17_000, 0.45, (2, 4), 0.3, 0.05, 3.0, 0.7, 0.9, brk_price=1.15),
            "di_chuyen": SessionParams(1.3, 6.0, 0.0, 9_000, 0.2, (0, 1, 2, 3, 4), 0.9, 0.05, 8.0, 0.0, 0.2, brk_price=1.6, brk_gap=0.9),
            "giai_tri": SessionParams(10.0, 2.0, 1.0, 45_000, 0.6, (5, 6), 0.7, 0.10, 3.0, 0.9, 0.9),
            "mua_sam": SessionParams(22.0, 1.4, 1.2, 80_000, 0.85, (), 0.0, 0.15, 3.5, 1.1, 0.9, brk_price=1.1),
            "du_lich": SessionParams(75.0, 1.2, 0.0, 250_000, 0.5, (), 0.0, 0.0, 1.0, 0.0, 0.0, duration_mean=2.0),
            "du_phong": SessionParams(95.0, 1.0, 0.0, 450_000, 0.7, (), 0.0, 0.3, 2.0, 0.0, 0.0),
        },
        break_at=195, raise_mult=1.25, rent_vnd=1_500_000, rent_step_vnd=0, budget_fraction=0.97,
    )  # fmt: skip


def _night_shift() -> Config:
    # ca đêm: thứ ưa thích là giữa tuần (thứ ba, thứ tư), không phải cuối tuần
    return Config(
        payday_day=25, salary_vnd=8_000_000,
        splits={"an_uong": 30, "di_chuyen": 9, "giai_tri": 9, "mua_sam": 8, "du_lich": 6, "du_phong": 5, "nghia_vu": 33},
        jars={
            "an_uong": SessionParams(1.3, 3.0, 2.0, 24_000, 0.5, (1, 2), 0.5, 0.06, 3.5, 0.4, 0.7, brk_price=1.2),
            "di_chuyen": SessionParams(1.2, 8.0, 0.0, 14_000, 0.2, (1, 2, 3, 4, 5), 0.9, 0.05, 6.0, 0.0, 0.3, brk_price=1.4),
            "giai_tri": SessionParams(9.0, 2.5, 1.3, 60_000, 0.7, (1, 2), 0.6, 0.12, 3.0, 0.6, 0.9),
            "mua_sam": SessionParams(15.0, 1.6, 1.4, 100_000, 0.8, (2,), 0.5, 0.12, 4.0, 0.9, 0.9, brk_gap=1.2),
            "du_lich": SessionParams(70.0, 1.2, 0.0, 380_000, 0.6, (), 0.0, 0.0, 1.0, 0.0, 0.0, duration_mean=3.0),
            "du_phong": SessionParams(80.0, 1.0, 0.0, 700_000, 0.7, (), 0.0, 0.35, 2.0, 0.0, 0.0),
        },
        break_at=220, raise_mult=1.05, rent_vnd=2_000_000, rent_step_vnd=500_000, budget_fraction=0.9,
    )  # fmt: skip


CONFIGS = {"grocer_office": _office, "student_allowance": _student, "night_shift": _night_shift}
CONFIG_NAMES = tuple(CONFIGS)
SPENDING_ORDER = ("an_uong", "di_chuyen", "giai_tri", "mua_sam", "du_lich", "du_phong")
KIND = {"du_phong": "saving"}


def _simulate_jar(
    rng: np.random.Generator,
    sp: SessionParams,
    budget: np.ndarray,  # (n,) ngân sách kỳ hiện tại của hũ
    weekday: np.ndarray,
    since: np.ndarray,
    period_start: np.ndarray,
    period_len: np.ndarray,
    break_at: int,
) -> np.ndarray:
    n = len(weekday)
    out = np.zeros(n)
    spent_in_period = 0.0
    cur_period = -1
    next_session = float(rng.integers(0, max(2, int(sp.gap_mean))))
    pending: list[float] = []  # số tiền các ngày kế của phiên nhiều ngày
    for t in range(n):
        if period_start[t] != cur_period:
            cur_period = int(period_start[t])
            spent_in_period = 0.0
        after = t >= break_at
        left = period_len[t] - (t - period_start[t])
        r = max(budget[t] - spent_in_period, 0.0) / max(budget[t], 1.0)
        tl = max(left / max(period_len[t], 1), 0.05)
        phi = float(np.clip(r / tl, 0.2, 1.3)) if sp.adjust > 0 else 1.0
        phi = phi**sp.adjust if sp.adjust > 0 else 1.0
        amt = 0.0
        if pending:
            amt += pending.pop(0)
        elif t >= next_session:
            skip = float(np.clip(1.0 - phi, 0.0, 0.8)) if sp.adjust > 0 else 0.0
            if rng.random() >= skip:
                boost = 1.0 + sp.payday_boost * max(0.0, 1.0 - since[t] / 10.0)
                k = (
                    1 + rng.poisson(sp.items_lambda * min(phi, 1.2) * boost)
                    if sp.items_lambda > 0
                    else 1
                )
                med = sp.price_med * (sp.brk_price if after else 1.0)
                prices = med * np.exp(sp.price_sigma * rng.standard_normal(k))
                if sp.tail_prob > 0:
                    prices = np.where(rng.random(k) < sp.tail_prob, prices * sp.tail_mult, prices)
                total = float(prices.sum() * (phi if sp.adjust > 0 and phi < 1 else 1.0))
                amt += total
                if sp.duration_mean > 1.0:
                    for _ in range(int(rng.poisson(sp.duration_mean - 1.0))):
                        pending.append(total * float(rng.uniform(0.6, 1.2)))
            gap = rng.gamma(
                sp.gap_shape, sp.gap_mean * (sp.brk_gap if after else 1.0) / sp.gap_shape
            )
            nxt = t + max(1, round(gap))
            if sp.pref_days and rng.random() < sp.pref_strength:
                for dd in range(7):
                    if (weekday[0] + nxt + dd) % 7 in sp.pref_days:
                        nxt += dd
                        break
            next_session = float(nxt)
        amt = max(1000.0, round(amt, -3)) if amt > 0 else 0.0
        out[t] = amt
        spent_in_period += amt
    return out


def generate(
    config: str, seed: int, n_days: int = 330, start: date = date(2026, 1, 1)
) -> SynthPersona:
    cfg = CONFIGS[config]()
    rng = np.random.default_rng([seed, 22, sum(map(ord, config))])
    dates = [start + timedelta(days=i) for i in range(n_days)]
    weekday = np.array([d.weekday() for d in dates])
    since = np.array([(d - latest_payday(cfg.payday_day, d)).days for d in dates], dtype=float)
    paydays = payday_list(
        cfg.payday_day, start - timedelta(days=62), dates[-1] + timedelta(days=45)
    )
    pd_idx = [(d - start).days for d in paydays]
    period_start = np.zeros(n_days, dtype=np.int64)
    period_len = np.zeros(n_days, dtype=np.int64)
    for t in range(n_days):
        ps = max(i for i in pd_idx if i <= t)
        pe = min(i for i in pd_idx if i > t)
        period_start[t], period_len[t] = ps, pe - ps
    break_day = dates[min(cfg.break_at, n_days - 1)]
    salary_by_payday = {
        d: int(round(cfg.salary_vnd * (cfg.raise_mult if d > break_day else 1.0), -3))
        for d in paydays
        if d <= dates[-1]
    }
    salary_at = np.array(
        [
            next(
                (
                    salary_by_payday[d]
                    for d in reversed(paydays)
                    if d <= dates[t] and d in salary_by_payday
                ),
                cfg.salary_vnd,
            )
            for t in range(n_days)
        ],
        dtype=float,
    )
    spend: dict[str, np.ndarray] = {}
    for code in SPENDING_ORDER:
        budget = salary_at * cfg.splits[code] / 100.0 * cfg.budget_fraction
        spend[code] = _simulate_jar(
            rng, cfg.jars[code], budget, weekday, since, period_start, period_len, cfg.break_at
        )
    rent_step = cfg.rent_vnd + cfg.rent_step_vnd if cfg.rent_step_vnd else None
    obligations = (
        ObligationSpec("Tiền trọ", 1, cfg.rent_vnd, jitter=False, step_date=break_day.replace(day=1) + timedelta(days=32) if rent_step else None, step_vnd=rent_step),
        ObligationSpec("Trả sau", 5, 380_000, 250_000, 500_000),
        ObligationSpec("Internet", 8, 200_000),
        ObligationSpec("Tiền điện", 12, 300_000, 220_000, 380_000),
        ObligationSpec("Tiền nước", 14, 85_000, 75_000, 95_000),
        ObligationSpec("Điện thoại", 20, 120_000),
    )  # fmt: skip
    paid = schedule_obligation_payments(rng, obligations, start, n_days)
    jars = tuple(
        SynthJar(
            code,
            KIND.get(code, "spending"),
            cfg.splits[code],
            np.rint(spend[code]).astype(np.int64),
        )
        for code in SPENDING_ORDER
    )
    jars = (
        *jars,
        SynthJar(
            OBLIGATION_JAR,
            "obligation",
            cfg.splits[OBLIGATION_JAR],
            np.zeros(n_days, dtype=np.int64),
        ),
    )
    salary, balances = build_ledger(start, n_days, cfg.payday_day, salary_by_payday, jars, paid)
    return SynthPersona(
        family="shopping_sessions", config=config, seed=seed, start=start, n_days=n_days,
        payday_day=cfg.payday_day, salary_vnd=salary, jars=jars, obligations=obligations,
        obligation_paid=paid, balances=balances, break_index=cfg.break_at,
    )  # fmt: skip
