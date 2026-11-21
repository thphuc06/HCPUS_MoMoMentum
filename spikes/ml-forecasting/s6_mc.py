"""Mục 6: Monte Carlo số dư hũ (vector hóa numpy). So lấy mẫu độc lập theo ngày vs Gaussian copula AR(1); đo thời gian.
Origin: 2026-10-20 (chỉ số 354); lương kế tiếp 2026-11-05 => 'trước kỳ lương' = 15 ngày đầu của horizon.
'Sự thật' = mô phỏng thẳng từ bộ sinh dữ liệu (100.000 đường, cùng tham số sau điểm gãy)."""
import time, json, warnings, os
import numpy as np, pandas as pd
from scipy.signal import lfilter
warnings.filterwarnings("ignore")
from common import *
from gen_data import sim_stochastic, covariates_for, obligations_schedule, BREAK_DATE, STOCH_JARS
from forecasters import hurdle_forecast, chronos_tables, to_long, sf_tables

df = load(); dates = df.index
O = int(np.where(dates == pd.Timestamp("2026-10-20"))[0][0])
fut = pd.date_range(dates[O] + pd.Timedelta(days=1), periods=H, freq="D")
HP = int((pd.Timestamp("2026-11-05") - dates[O]).days) - 1           # số ngày trước ngày lương = 15
cov_all = covariates_for(pd.date_range(dates[0], periods=len(df) + 60, freq="D"))
MC_JARS = ["an_uong", "di_chuyen", "giai_tri", "mua_sam", "du_lich", "du_phong"]
JI = [JARS.index(j) for j in MC_JARS]

# --- số dư đầu kỳ: phân bổ = BUDGET_FACTOR x trung vị chi 3 kỳ lương gần nhất (Jul5-Oct4); trừ phần đã chi từ 5/10 đến 20/10 -------------
BUDGET_FACTOR = float(os.environ.get("BUDGET_FACTOR", "1.3"))
periods = [df.loc[a:b, MC_JARS].sum() for a, b in [("2026-07-05", "2026-08-04"), ("2026-08-05", "2026-09-04"), ("2026-09-05", "2026-10-04")]]
per = pd.concat(periods, axis=1).median(axis=1) * BUDGET_FACTOR      # phân bổ = 1,3 x trung vị chi 3 kỳ gần nhất
spent_now = df.loc["2026-10-05":"2026-10-20", MC_JARS].sum()
alloc = per.copy(); alloc["du_phong"] = 1200.0 + spent_now["du_phong"]          # quỹ dự phòng 1.200k đầu kỳ
bal0 = (alloc - spent_now).values
print("phân bổ/kỳ (k):", alloc.round(0).to_dict()); print("đã chi 5-20/10:", spent_now.round(0).to_dict()); print("số dư đầu horizon:", dict(zip(MC_JARS, bal0.round(0))))
# lịch tất định: hóa đơn rơi vào hũ Nghĩa vụ -> không nằm trong 6 hũ ngẫu nhiên; ví dụ cộng lịch tất định vào hũ Giải trí: gói thuê bao 70k ngày 8/11 (minh họa cơ chế)
outflow_det = np.zeros((len(MC_JARS), H)); outflow_det[MC_JARS.index("giai_tri"), int((pd.Timestamp("2026-11-08") - fut[0]).days)] = 70.0


def mc_run(qt, bal0, outflow_det, N, rho, seed=0, use_lfilter=True, Hp=HP):
    """qt: (J,H,K) bảng phân vị theo ngày. Trả (xác suất hụt trước lương (J,), ngày cạn đầu tiên (J,N) với H nếu không cạn)."""
    J = qt.shape[0]
    rng = np.random.default_rng(seed)
    e = rng.standard_normal((J, N, H))
    if rho > 0:
        if use_lfilter:
            s = np.sqrt(1 - rho ** 2)
            x = e.copy(); x[..., 0] = e[..., 0] / s
            z = lfilter([s], [1.0, -rho], x, axis=-1)
        else:
            z = np.empty_like(e); z[..., 0] = e[..., 0]; s = np.sqrt(1 - rho ** 2)
            for h in range(1, H):
                z[..., h] = rho * z[..., h - 1] + s * e[..., h]
    else:
        z = e
    u = ndtr(z)
    tau_e = np.concatenate([[0.0], QLEVELS, [1.0]])
    slope = (qt[..., -1] - qt[..., -2]) / (QLEVELS[-1] - QLEVELS[-2])
    qe = np.concatenate([np.zeros((J, H, 1)), qt, (qt[..., -1] + slope * (1 - QLEVELS[-1]))[..., None]], axis=-1)
    i = np.clip(np.searchsorted(tau_e, u, side="right"), 1, len(tau_e) - 1)
    jj = np.arange(J)[:, None, None]; hh = np.arange(H)[None, None, :]
    w = (u - tau_e[i - 1]) / (tau_e[i] - tau_e[i - 1])
    spend = qe[jj, hh, i - 1] * (1 - w) + qe[jj, hh, i] * w
    bal = bal0[:, None, None] - np.cumsum(spend + outflow_det[:, None, :], axis=-1)
    broke = bal[..., :Hp] < 0
    p = broke.any(-1).mean(-1)
    first = np.where(broke.any(-1), broke.argmax(-1) + 1, 0)                 # ngày thứ mấy cạn (1..Hp), 0 = không
    return p, first


# --- bảng phân vị: (a) oracle từ bộ sinh, (b) Chronos-2 + (c) Hurdle tại origin --------------------------------------------
t0 = time.perf_counter()
P_TRUE = 100_000
rng = np.random.default_rng(2026)
sim = sim_stochastic(rng, fut, P=P_TRUE)                    # mood khởi tạo ngẫu nhiên từ phân phối dừng
truth_paths = np.stack([sim[j] for j in MC_JARS])           # (J, P, H)
qt_oracle = np.quantile(truth_paths, QLEVELS, axis=1).transpose(1, 2, 0)    # (J,H,K)
cum = bal0[:, None, None] - np.cumsum(truth_paths + outflow_det[:, None, :], axis=-1)
bro = cum[..., :HP] < 0
p_true = bro.any(-1).mean(-1); first_true = np.where(bro.any(-1), bro.argmax(-1) + 1, 0)
print("mô phỏng sự thật xong %.1fs" % (time.perf_counter() - t0))

os.environ.setdefault("HF_HUB_OFFLINE", "1")
from chronos import Chronos2Pipeline
pipe = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map="cpu")
qt_chr = chronos_tables(pipe, df, cov_all, O)[JI]
cov_hist = cov_all.iloc[: O + 1]; cov_fut = cov_all.iloc[O + 1: O + 1 + H]
qt_hur = np.stack([hurdle_forecast(df[j].values[: O + 1], cov_hist, cov_fut, np.random.default_rng(5)) for j in MC_JARS])

res = {"HP": HP, "bal0": dict(zip(MC_JARS, bal0.round(1))), "p_true": dict(zip(MC_JARS, p_true.round(4)))}
N = 20000
rows = []
for name, qt in [("oracle (biên thật từ bộ sinh)", qt_oracle), ("Chronos-2", qt_chr), ("Hurdle", qt_hur)]:
    for rho in [0.0, 0.2, 0.4, 0.6, 0.8]:
        p, first = mc_run(qt, bal0, outflow_det, N, rho, seed=1)
        rows.append({"bảng phân vị": name, "rho": rho, **{j: round(float(p[k]), 3) for k, j in enumerate(MC_JARS)}})
rows.append({"bảng phân vị": "SỰ THẬT (mô phỏng bộ sinh, 100k đường)", "rho": "-", **{j: round(float(p_true[k]), 3) for k, j in enumerate(MC_JARS)}})
t = pd.DataFrame(rows)
print("\nXác suất hụt trước kỳ lương (15 ngày đầu), N=20.000 đường mỗi ô\n", t.to_markdown(index=False))
res["p_table"] = rows

# --- kịch bản hiệu chỉnh: chọn số dư đầu kỳ sao cho xác suất hụt THẬT (từ bộ sinh) = 10% / 30% / 50% --------------------------
# (dòng chi >= 0 nên hụt trước lương <=> tổng chi 15 ngày đầu > số dư)
S15 = truth_paths[:, :, :HP].sum(-1) + outflow_det[:, None, :HP].sum(-1)[:, :]
CAL_JARS = ["an_uong", "di_chuyen", "giai_tri", "mua_sam", "du_lich"]
cal_rows = []
for target in (0.1, 0.3, 0.5):
    b = np.array([np.quantile(S15[MC_JARS.index(j)], 1 - target) for j in MC_JARS])
    b[MC_JARS.index("du_phong")] = 1e9
    for name, qt in [("oracle", qt_oracle), ("Chronos-2", qt_chr), ("Hurdle", qt_hur)]:
        for rho in [0.0, 0.2, 0.4, 0.6, 0.8]:
            p, _ = mc_run(qt, b, outflow_det, 20000, rho, seed=1)
            cal_rows.append({"P thật": target, "bảng phân vị": name, "rho": rho, **{j: round(float(p[MC_JARS.index(j)]), 3) for j in CAL_JARS}})
tc = pd.DataFrame(cal_rows)
print("\nKỊCH BẢN HIỆU CHỈNH: xác suất hụt ước lượng khi xác suất hụt thật = 10/30/50% (N=20.000)\n", tc.to_markdown(index=False))
res["calibrated"] = cal_rows

# ngày cạn: trung vị và P(cạn trước ngày d) cho hũ an_uong dưới 3 cách (oracle)
print("\nNgày cạn (trung vị trong các đường có cạn) - oracle: ")
for rho in (0.0, 0.8):
    p, first = mc_run(qt_oracle, bal0, outflow_det, N, rho, seed=1)
    print(" rho", rho, {j: (int(np.median(first[k][first[k] > 0])) if (first[k] > 0).any() else None) for k, j in enumerate(MC_JARS)})
print(" sự thật", {j: (int(np.median(first_true[k][first_true[k] > 0])) if (first_true[k] > 0).any() else None) for k, j in enumerate(MC_JARS)})

# --- thời gian chạy ----------------------------------------------------------------------------------------------------------
print("\nThời gian chạy (ms), vector hóa, 6 hũ x 30 ngày, trung vị 15 lần; (a) AR(1) bằng vòng for, (b) bằng scipy lfilter")
tim = []
for n in (1000, 5000, 10000):
    for rho, uf, lab in [(0.0, True, "độc lập"), (0.6, False, "copula, vòng for"), (0.6, True, "copula, lfilter")]:
        mc_run(qt_chr, bal0, outflow_det, n, rho, seed=0, use_lfilter=uf)   # khởi động
        ts = []
        for r in range(15):
            a = time.perf_counter(); mc_run(qt_chr, bal0, outflow_det, n, rho, seed=r, use_lfilter=uf); ts.append((time.perf_counter() - a) * 1000)
        tim.append({"N": n, "cách": lab, "median_ms": round(float(np.median(ts)), 1), "max_ms": round(float(np.max(ts)), 1)})
tt = pd.DataFrame(tim); print(tt.to_markdown(index=False)); res["timing"] = tim
# một hũ (chỉ 1 hũ x 30 ngày) cho what-if tương tác
ts = []
for r in range(15):
    a = time.perf_counter(); mc_run(qt_chr[:1], bal0[:1], outflow_det[:1], 5000, 0.6, seed=r); ts.append((time.perf_counter() - a) * 1000)
print("1 hũ, N=5000, copula lfilter: median %.1f ms" % np.median(ts)); res["one_jar_5000_ms"] = float(np.median(ts))
# số đường vs sai số chuẩn: lặp 40 seed, N=1000/5000/10000, độ lệch chuẩn thực của p (hũ an_uong, oracle, rho=0.4)
se = {}
for n in (1000, 5000, 10000):
    ps = np.array([mc_run(qt_oracle, bal0, outflow_det, n, 0.4, seed=100 + r)[0] for r in range(40)])
    se[n] = dict(zip(MC_JARS, (ps.std(0) * 100).round(2)))
print("\nĐộ lệch chuẩn thực của p qua 40 seed (điểm %):", json.dumps(se, ensure_ascii=False)); res["se_pp"] = {str(k): {a: float(b) for a, b in v.items()} for k, v in se.items()}
json.dump(res, open(HERE / "results" / "s6_mc.json", "w"), indent=1, default=float)
