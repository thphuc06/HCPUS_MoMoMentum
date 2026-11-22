"""Họ bộ sinh (i): hurdle-lognormal. Cùng họ với mô hình hurdle theo lịch nên mô hình được LỢI THẾ NỘI TẠI.

Mỗi hũ mỗi ngày: có chi với xác suất sigmoid(hệ số cơ sở + cuối tuần + hiệu ứng ngày lương exp(-d/tau) + tải "tâm trạng"), số
tiền lognormal có trung vị phụ thuộc cuối tuần và ngày lương. "Tâm trạng" là AR(1) chung của các hũ (làm các ngày liền kề có
tương quan dương thật). Có điểm gãy lối sống (nhân tử riêng của từng hũ), khoản lớn một lần và các chuyến du lịch.
Lấy lại từ `spikes/ml-forecasting/gen_data.py` (đơn vị VND thay vì nghìn đồng, ba cấu hình persona, mọi tham số là đầu vào).
"""

from __future__ import annotations

from dataclasses import dataclass
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
class JarParams:
    p0: float  # xác suất có chi cơ sở trong ngày
    bw: float  # hiệu ứng cuối tuần (logit)
    bph: float  # hiệu ứng ngày lương (logit)
    med: float  # trung vị số tiền (VND)
    sig: float  # sigma lognormal
    wk: float  # nhân số tiền cuối tuần
    ph: float  # biên độ ngày lương của số tiền
    load: float  # hệ số tải tâm trạng
    brk: float  # nhân sau điểm gãy


@dataclass(frozen=True)
class Config:
    payday_day: int
    salary_vnd: int
    splits: dict[str, float]
    jars: dict[str, JarParams]
    mood_rho: float = 0.55
    mood_sd: float = 0.30
    phase_tau: float = 8.0
    break_at: int = 200
    rent_vnd: int = 2_500_000
    rent_step_vnd: int = 300_000


def _office() -> Config:  # persona kiểu Minh của spike
    return Config(
        payday_day=5,
        salary_vnd=9_000_000,
        splits={"an_uong": 28, "di_chuyen": 8, "giai_tri": 8, "mua_sam": 8, "du_lich": 8, "du_phong": 4, "nghia_vu": 36},
        jars={
            "an_uong": JarParams(0.97, 0.3, 0.5, 38_000, 0.45, 1.3, 0.45, 1.0, 1.35),
            "di_chuyen": JarParams(0.85, -0.8, 0.2, 18_000, 0.40, 1.1, 0.10, 0.5, 1.60),
            "giai_tri": JarParams(0.22, 1.1, 0.8, 55_000, 0.60, 1.2, 0.50, 1.2, 1.30),
            "mua_sam": JarParams(0.09, 0.4, 1.2, 95_000, 0.80, 1.0, 0.60, 1.2, 1.00),
            "du_lich": JarParams(0.03, 0.7, 0.0, 210_000, 0.70, 1.0, 0.0, 0.5, 1.00),
            "du_phong": JarParams(4 / 365, 0.0, 0.0, 650_000, 0.60, 1.0, 0.0, 0.0, 1.00),
        },
    )  # fmt: skip


def _student() -> (
    Config
):  # sinh viên làm thêm: lương thấp, chi nhỏ, ngày nhận 1, đổi nhà trọ ở điểm gãy
    return Config(
        payday_day=1,
        salary_vnd=4_500_000,
        splits={"an_uong": 36, "di_chuyen": 10, "giai_tri": 8, "mua_sam": 6, "du_lich": 4, "du_phong": 4, "nghia_vu": 32},
        jars={
            "an_uong": JarParams(0.95, 0.5, 0.6, 22_000, 0.40, 1.4, 0.50, 1.0, 1.15),
            "di_chuyen": JarParams(0.80, -1.0, 0.1, 12_000, 0.35, 1.1, 0.05, 0.5, 1.80),
            "giai_tri": JarParams(0.18, 1.4, 0.9, 40_000, 0.60, 1.3, 0.50, 1.2, 1.10),
            "mua_sam": JarParams(0.07, 0.3, 1.3, 70_000, 0.85, 1.0, 0.70, 1.2, 1.00),
            "du_lich": JarParams(0.02, 0.8, 0.0, 150_000, 0.70, 1.0, 0.0, 0.5, 1.00),
            "du_phong": JarParams(3 / 365, 0.0, 0.0, 400_000, 0.60, 1.0, 0.0, 0.0, 1.00),
        },
        mood_rho=0.45,
        mood_sd=0.35,
        phase_tau=6.0,
        break_at=190,
        rent_vnd=1_500_000,
        rent_step_vnd=400_000,
    )  # fmt: skip


def _freelancer() -> Config:  # lương cao nhưng ngày nhận 25, biến động lớn, SAU điểm gãy chi GIẢM
    return Config(
        payday_day=25,
        salary_vnd=12_000_000,
        splits={"an_uong": 24, "di_chuyen": 9, "giai_tri": 10, "mua_sam": 9, "du_lich": 8, "du_phong": 5, "nghia_vu": 35},
        jars={
            "an_uong": JarParams(0.93, 0.2, 0.7, 52_000, 0.55, 1.2, 0.60, 1.2, 0.75),
            "di_chuyen": JarParams(0.70, -0.4, 0.3, 30_000, 0.50, 1.1, 0.20, 0.8, 0.70),
            "giai_tri": JarParams(0.30, 0.9, 1.0, 85_000, 0.70, 1.2, 0.60, 1.4, 0.65),
            "mua_sam": JarParams(0.12, 0.2, 1.4, 140_000, 0.90, 1.0, 0.80, 1.4, 0.70),
            "du_lich": JarParams(0.05, 0.6, 0.0, 380_000, 0.80, 1.0, 0.0, 0.6, 1.00),
            "du_phong": JarParams(5 / 365, 0.0, 0.0, 900_000, 0.70, 1.0, 0.0, 0.0, 1.00),
        },
        mood_rho=0.65,
        mood_sd=0.40,
        phase_tau=5.0,
        break_at=215,
        rent_vnd=3_200_000,
        rent_step_vnd=0,
    )  # fmt: skip


CONFIGS = {"office": _office, "student": _student, "freelancer": _freelancer}
CONFIG_NAMES = tuple(CONFIGS)
SPENDING_ORDER = ("an_uong", "di_chuyen", "giai_tri", "mua_sam", "du_lich", "du_phong")
KIND = {"du_phong": "saving"}


def _obligations(cfg: Config, step_date: date) -> tuple[ObligationSpec, ...]:
    rent_step = cfg.rent_vnd + cfg.rent_step_vnd if cfg.rent_step_vnd else None
    return (
        ObligationSpec("Tiền trọ", 1, cfg.rent_vnd, jitter=False, step_date=step_date if rent_step else None, step_vnd=rent_step),
        ObligationSpec("Trả sau", 5, 450_000, 300_000, 600_000),
        ObligationSpec("Internet", 8, 220_000),
        ObligationSpec("Tiền điện", 12, 320_000, 240_000, 400_000),
        ObligationSpec("Tiền nước", 14, 90_000, 80_000, 100_000),
        ObligationSpec("Điện thoại", 20, 100_000),
    )  # fmt: skip


def generate(
    config: str, seed: int, n_days: int = 330, start: date = date(2026, 1, 1)
) -> SynthPersona:
    cfg = CONFIGS[config]()
    rng = np.random.default_rng([seed, 11, sum(map(ord, config))])
    dates = [start + timedelta(days=i) for i in range(n_days)]
    weekend = np.array([d.weekday() >= 5 for d in dates], dtype=float)
    since = np.array([(d - latest_payday(cfg.payday_day, d)).days for d in dates], dtype=float)
    phase = np.exp(-since / cfg.phase_tau)
    after = (np.arange(n_days) >= cfg.break_at).astype(float)
    # tâm trạng AR(1) chung
    mood = np.empty(n_days)
    prev = rng.normal(0, cfg.mood_sd)
    for t in range(n_days):
        prev = (
            cfg.mood_rho * prev + np.sqrt(1 - cfg.mood_rho**2) * cfg.mood_sd * rng.standard_normal()
        )
        mood[t] = prev
    spend: dict[str, np.ndarray] = {}
    for code in SPENDING_ORDER:
        a = cfg.jars[code]
        logit = np.log(a.p0 / (1 - a.p0)) + a.bw * weekend + a.bph * phase + 0.8 * a.load * mood
        p = 1 / (1 + np.exp(-logit))
        med = (
            a.med
            * np.where(weekend > 0, a.wk, 1.0)
            * (1 + a.ph * phase)
            * np.where(after > 0, a.brk, 1.0)
            * np.exp(a.load * mood)
        )
        amt = np.maximum(1000.0, np.round(med * np.exp(a.sig * rng.standard_normal(n_days)), -3))
        spend[code] = np.where(rng.random(n_days) < p, amt, 0.0)
    # khoản lớn một lần và chuyến du lịch (theo ngày chỉ số cố định tương đối theo tỷ lệ, không phụ thuộc seed)
    scale = cfg.salary_vnd / 9_000_000
    for code, frac, base in (
        ("mua_sam", 0.18, 1_800_000),
        ("an_uong", 0.42, 950_000),
        ("mua_sam", 0.72, 2_200_000),
    ):
        spend[code][int(frac * n_days)] += round(base * scale, -3)
    for frac, base in (
        (0.10, 600_000),
        (0.11, 500_000),
        (0.55, 700_000),
        (0.56, 800_000),
        (0.57, 900_000),
    ):
        spend["du_lich"][int(frac * n_days)] += round(base * scale, -3)
    obligations = _obligations(cfg, dates[min(cfg.break_at + 20, n_days - 1)].replace(day=1))
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
    salary_by_payday = {
        d: cfg.salary_vnd for d in payday_list(cfg.payday_day, start - timedelta(days=1), dates[-1])
    }
    salary, balances = build_ledger(start, n_days, cfg.payday_day, salary_by_payday, jars, paid)
    return SynthPersona(
        family="hurdle_lognormal", config=config, seed=seed, start=start, n_days=n_days,
        payday_day=cfg.payday_day, salary_vnd=salary, jars=jars, obligations=obligations,
        obligation_paid=paid, balances=balances, break_index=cfg.break_at,
    )  # fmt: skip
