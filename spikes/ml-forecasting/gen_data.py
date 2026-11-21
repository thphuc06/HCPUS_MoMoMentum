"""Bộ sinh dữ liệu tổng hợp tối thiểu cho persona Minh (spike, giữ gọn).

Đơn vị: nghìn đồng (k VND). 365 ngày: 2025-11-01 .. 2026-10-31. Seed cố định.
7 hũ: an_uong, di_chuyen, giai_tri, mua_sam, du_lich, nghia_vu, du_phong.
Cơ chế: hurdle (xác suất có chi x lognormal) + hiệu ứng ngày lương exp(-d/8)
+ cuối tuần + "tâm trạng" AR(1) chung (làm các ngày liền kề có tương quan)
+ điểm gãy lối sống 2026-07-10 + khoản lớn một lần + hóa đơn định kỳ.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

SEED = 20261121
START = pd.Timestamp("2025-11-01")
N_DAYS = 365
BREAK_DATE = pd.Timestamp("2026-07-10")        # tháng thứ 9 (Nov=1 ... Jul=9)
PAYDAY = 5
SALARY = 9000.0
JARS = ["an_uong", "di_chuyen", "giai_tri", "mua_sam", "du_lich", "nghia_vu", "du_phong"]
JAR_NAMES = {"an_uong": "Ăn uống", "di_chuyen": "Di chuyển", "giai_tri": "Giải trí", "mua_sam": "Mua sắm",
             "du_lich": "Du lịch", "nghia_vu": "Nghĩa vụ", "du_phong": "Dự phòng"}
MOOD_RHO, MOOD_SD = 0.55, 0.30

# p0: xác suất cơ sở; bw: hiệu ứng cuối tuần (logit); bph: hiệu ứng ngày lương (logit);
# med: trung vị số tiền; sig: sigma lognormal; wk: nhân số tiền cuối tuần; ph: biên độ ngày lương;
# load: hệ số tải "tâm trạng"; brk: nhân sau điểm gãy.
PARAMS = {
    "an_uong":   dict(p0=0.97, bw=0.3, bph=0.5, med=38, sig=0.45, wk=1.3, ph=0.45, load=1.0, brk=1.35),
    "di_chuyen": dict(p0=0.85, bw=-0.8, bph=0.2, med=18, sig=0.40, wk=1.1, ph=0.10, load=0.5, brk=1.60),
    "giai_tri":  dict(p0=0.22, bw=1.1, bph=0.8, med=55, sig=0.60, wk=1.2, ph=0.50, load=1.2, brk=1.30),
    "mua_sam":   dict(p0=0.09, bw=0.4, bph=1.2, med=95, sig=0.80, wk=1.0, ph=0.60, load=1.2, brk=1.00),
    "du_lich":   dict(p0=0.03, bw=0.7, bph=0.0, med=210, sig=0.70, wk=1.0, ph=0.0, load=0.5, brk=1.00),
    "du_phong":  dict(p0=4 / 365, bw=0.0, bph=0.0, med=650, sig=0.60, wk=1.0, ph=0.0, load=0.0, brk=1.00),
}
STOCH_JARS = list(PARAMS)

# khoản lớn một lần chèn vào lịch sử (có nhãn); du_phong tự có cú sốc Poisson (cũng gán nhãn 'shock')
ONE_OFFS = [("mua_sam", "2026-01-17", 1800.0, "sửa laptop"),
            ("an_uong", "2026-04-30", 950.0, "tiệc sinh nhật"),
            ("mua_sam", "2026-09-02", 2200.0, "điện thoại mới")]
TRIPS = [("du_lich", "2025-12-27", 600.0), ("du_lich", "2025-12-28", 500.0),
         ("du_lich", "2026-04-30", 700.0), ("du_lich", "2026-05-01", 800.0), ("du_lich", "2026-05-02", 900.0)]


def calendar(dates: pd.DatetimeIndex) -> dict[str, np.ndarray]:
    dow = dates.dayofweek.values
    wk = (dow >= 5).astype(float)
    # số ngày kể từ ngày lương gần nhất (ngày 5 hằng tháng)
    d = np.empty(len(dates))
    for i, t in enumerate(dates):
        last = pd.Timestamp(t.year, t.month, PAYDAY) if t.day >= PAYDAY else (pd.Timestamp(t.year, t.month, PAYDAY) - pd.DateOffset(months=1))
        d[i] = (t - last).days
    return dict(dow=dow, wk=wk, d=d, phase=np.exp(-d / 8.0), is_payday=(dates.day.values == PAYDAY).astype(float))


def _logit(p):
    return np.log(p / (1 - p))


def sim_stochastic(rng: np.random.Generator, dates: pd.DatetimeIndex, P: int = 1, post_break_from: pd.Timestamp = BREAK_DATE,
                   mood0: np.ndarray | None = None) -> dict[str, np.ndarray]:
    """Chi tiêu ngẫu nhiên các hũ hurdle: trả dict jar -> (P, T). Vector hóa theo đường P."""
    T = len(dates)
    cal = calendar(dates)
    after = np.asarray(dates >= post_break_from).astype(float)
    m = np.empty((P, T))
    prev = rng.normal(0, MOOD_SD, P) if mood0 is None else mood0
    for t in range(T):
        prev = MOOD_RHO * prev + np.sqrt(1 - MOOD_RHO ** 2) * MOOD_SD * rng.standard_normal(P)
        m[:, t] = prev
    out = {}
    for jar, a in PARAMS.items():
        logit_p = _logit(a["p0"]) + a["bw"] * cal["wk"] + a["bph"] * cal["phase"] + 0.8 * a["load"] * m
        p = 1 / (1 + np.exp(-logit_p))
        med = a["med"] * np.where(cal["wk"] > 0, a["wk"], 1.0) * (1 + a["ph"] * cal["phase"]) * np.where(after > 0, a["brk"], 1.0) * np.exp(a["load"] * m)
        amt = np.maximum(1.0, np.round(med * np.exp(a["sig"] * rng.standard_normal((P, T)))))
        out[jar] = np.where(rng.random((P, T)) < p, amt, 0.0)
    return out


def obligations_schedule(dates: pd.DatetimeIndex, rng: np.random.Generator | None = None) -> pd.DataFrame:
    """Hóa đơn định kỳ. rng=None -> số tiền kỳ vọng, đúng ngày (dùng làm lịch tất định cho Monte Carlo)."""
    rows = []
    for t in dates:
        rent = 2800.0 if t >= pd.Timestamp("2026-08-01") else 2500.0
        items = [("tien_tro", 1, rent, 0.0), ("tra_sau", 5, 450.0, 150.0), ("net", 8, 220.0, 0.0),
                 ("dien", 12, 320.0, 80.0), ("nuoc", 14, 90.0, 9.0), ("dien_thoai", 20, 100.0, 0.0)]
        for name, day, amt, spread in items:
            if t.day == day:
                a = amt if rng is None else (amt + rng.uniform(-spread, spread))
                rows.append((t, name, float(round(a))))
    return pd.DataFrame(rows, columns=["date", "item", "amount"])


def build_history(seed: int = SEED):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(START, periods=N_DAYS, freq="D")
    sim = sim_stochastic(rng, dates, P=1)
    daily = {j: sim[j][0].copy() for j in sim}
    labels = []
    ix = {t: i for i, t in enumerate(dates)}
    for jar, d, amt, note in ONE_OFFS:
        daily[jar][ix[pd.Timestamp(d)]] += amt
        labels.append(dict(jar=jar, date=d, amount=amt, kind="one_off", note=note))
    for jar, d, amt in TRIPS:
        daily[jar][ix[pd.Timestamp(d)]] += amt
    for i in np.where(daily["du_phong"] > 0)[0]:
        labels.append(dict(jar="du_phong", date=str(dates[i].date()), amount=float(daily["du_phong"][i]), kind="shock", note="cú sốc Poisson"))
    # nghĩa vụ: hóa đơn định kỳ, ngày trả lệch +-1 ngày với xác suất 20%
    sched = obligations_schedule(dates, rng)
    nv = np.zeros(N_DAYS)
    for _, r in sched.iterrows():
        i = ix[r["date"]]
        if r["item"] not in ("tien_tro",) and rng.random() < 0.2:
            i = min(N_DAYS - 1, max(0, i + int(rng.choice([-1, 1]))))
        nv[i] += r["amount"]
    daily["nghia_vu"] = nv
    df = pd.DataFrame({j: daily[j] for j in JARS}, index=dates)
    df.index.name = "date"
    cal = calendar(dates)
    cov = pd.DataFrame({"is_payday": cal["is_payday"], "is_weekend": cal["wk"], "days_since_payday": cal["d"]}, index=dates)
    truth = dict(seed=seed, break_date=str(BREAK_DATE.date()), break_index=int(ix[BREAK_DATE]), salary_k=SALARY, payday=PAYDAY,
                 one_offs=labels, trips=[list(t) for t in TRIPS], params={k: v for k, v in PARAMS.items()})
    return df, cov, truth


def covariates_for(dates: pd.DatetimeIndex) -> pd.DataFrame:
    cal = calendar(dates)
    return pd.DataFrame({"is_payday": cal["is_payday"], "is_weekend": cal["wk"], "days_since_payday": cal["d"]}, index=dates)


if __name__ == "__main__":
    out = Path(__file__).parent / "data"
    out.mkdir(exist_ok=True)
    df, cov, truth = build_history()
    df.join(cov).to_csv(out / "minh_daily.csv")
    (out / "truth.json").write_text(json.dumps(truth, ensure_ascii=False, indent=1), encoding="utf-8")
    print(df.describe().T[["mean", "std", "max"]].round(1))
    print("share zero days:", (df == 0).mean().round(2).to_dict())
    print("monthly total (k VND):", df.sum(axis=1).resample("MS").sum().round(0).tolist())
    print("labels:", len(truth["one_offs"]))
