"""Mục 3+4: tính pinball, độ phủ 80% theo ngày và theo tổng 30 ngày, ước lượng rho (PIT AR1) từ backtest_forecasts.pkl."""
import pickle, json
import numpy as np, pandas as pd
from scipy.stats import norm
from common import *

d = pickle.load(open(HERE / "results" / "backtest_forecasts.pkl", "rb"))
tabs, Y, origins = d["tabs"], d["ytrue"], np.array(d["origins"])
MODELS = list(tabs)
TAU_IDX = {0.1: 2, 0.5: 6, 0.9: 10}
BASE = "SN_conf"
BREAK_IDX = 251
seg = {"all": np.ones(len(origins), bool), "pre_break": origins + H < BREAK_IDX, "post_break": origins >= BREAK_IDX}
dense = ["an_uong", "di_chuyen"]; sparse = ["giai_tri", "mua_sam", "du_lich", "du_phong"]


def daily_metrics(m, mask):
    t = tabs[m][mask]; y = Y[mask]
    res = {}
    for k, j in enumerate(JARS):
        pl = np.mean([pinball(y[:, k], t[:, k, :, i], tau).mean() for tau, i in TAU_IDX.items()])
        cov = ((y[:, k] >= t[:, k, :, 2]) & (y[:, k] <= t[:, k, :, 10])).mean()
        res[j] = (pl, cov)
    return res


def pit_rho(m):
    """rho AR(1) của phần dư PIT chuẩn hóa, gộp các origin, theo hũ. PIT ngẫu nhiên hóa ở khối lượng tại 0 / trùng."""
    rng = np.random.default_rng(7)
    out = {}
    tau_e = np.concatenate([[0.0], QLEVELS, [1.0]])
    for k, j in enumerate(JARS):
        zs = np.full(Y.shape[0:1] + (H,), np.nan)
        for oi in range(Y.shape[0]):
            for h in range(H):
                q = tabs[m][oi, k, h]; y = Y[oi, k, h]
                klo = int((q < y).sum()); khi = int((q <= y).sum())
                if khi > klo:
                    u = rng.uniform(tau_e[klo], tau_e[khi])
                elif klo == 0:
                    u = QLEVELS[0] * (y / q[0]) if q[0] > 0 else 0.5 * QLEVELS[0]
                elif klo == len(q):
                    u = 0.995
                else:
                    u = QLEVELS[klo - 1] + (QLEVELS[klo] - QLEVELS[klo - 1]) * (y - q[klo - 1]) / (q[klo] - q[klo - 1])
                zs[oi, h] = norm.ppf(np.clip(u, 1e-3, 1 - 1e-3))
        a, b = zs[:, :-1].ravel(), zs[:, 1:].ravel()
        out[j] = float(np.corrcoef(a, b)[0, 1])
    return out


def total_metrics(m, rho_by_jar, mask, N=2000, seed=11):
    rng = np.random.default_rng(seed)
    t = tabs[m]; y = Y
    res = {}
    for k, j in enumerate(JARS):
        rho = float(np.clip(rho_by_jar[j], 0, 0.9)) if rho_by_jar is not None else 0.0
        cov, pls = [], []
        for oi in np.where(mask)[0]:
            z = ar1_normals(rng, N, H, rho); u = ndtr(z)
            s = sample_from_qtable(u, t[oi, k]).sum(axis=1)
            q10, q50, q90 = np.quantile(s, [0.1, 0.5, 0.9]); act = y[oi, k].sum()
            cov.append(q10 <= act <= q90)
            pls.append(np.mean([pinball(act, q, tau) for q, tau in ((q10, 0.1), (q50, 0.5), (q90, 0.9))]))
        res[j] = (float(np.mean(pls)), float(np.mean(cov)))
    return res


out = {"daily": {}, "rho": {}, "total_rho_fit": {}, "total_indep": {}, "seg": {}}
for m in MODELS:
    out["daily"][m] = daily_metrics(m, seg["all"])
    out["rho"][m] = pit_rho(m)
    out["total_rho_fit"][m] = total_metrics(m, out["rho"][m], seg["all"])
    out["total_indep"][m] = total_metrics(m, None, seg["all"])
    for s in ("pre_break", "post_break"):
        out["seg"][(m, s)] = daily_metrics(m, seg[s])

rows = []
def rel(m, s="all", jars=JARS):
    src = out["daily"] if s == "all" else None
    cur = out["daily"][m] if s == "all" else out["seg"][(m, s)]
    base = out["daily"][BASE] if s == "all" else out["seg"][(BASE, s)]
    v = [cur[j][0] / base[j][0] for j in jars if base[j][0] > 1e-9]
    return float(np.mean(v)) if v else float('nan')

txt = []
txt.append("## pinball trung bình (P10/P50/P90) theo hũ, toàn bộ 31 origin (đơn vị k VND/ngày)")
t1 = pd.DataFrame({m: {j: out["daily"][m][j][0] for j in JARS} for m in MODELS}).T.round(2)
txt.append(t1.to_markdown());
txt.append("\n## độ phủ 80% theo ngày (P10..P90)")
t2 = pd.DataFrame({m: {j: out["daily"][m][j][1] for j in JARS} for m in MODELS}).T.round(2)
txt.append(t2.to_markdown())
txt.append(f"\n## pinball tương đối so với {BASE} (1.00 = bằng; <1 tốt hơn), trung bình số học qua hũ")
rr = {}
for m in MODELS:
    rr[m] = {"dense(2)": rel(m, "all", dense), "sparse(4)": rel(m, "all", sparse), "nghia_vu": rel(m, "all", ["nghia_vu"]),
             "6 hũ chi tiêu": rel(m, "all", [j for j in JARS if j != "nghia_vu"]),
             "pre_break 6hũ": rel(m, "pre_break", [j for j in JARS if j != "nghia_vu"]), "post_break 6hũ": rel(m, "post_break", [j for j in JARS if j != "nghia_vu"])}
t3 = pd.DataFrame(rr).T.round(2); txt.append(t3.to_markdown())
txt.append("\n## rho AR(1) ước lượng từ PIT (lag 1, gộp origin)")
t4 = pd.DataFrame(out["rho"]).T.round(2); txt.append(t4.to_markdown())
txt.append("\n## tổng 30 ngày: độ phủ 80% (rho = ước lượng PIT) / (độc lập rho=0)")
t5 = pd.DataFrame({m: {j: f"{out['total_rho_fit'][m][j][1]:.2f} / {out['total_indep'][m][j][1]:.2f}" for j in JARS} for m in MODELS}).T
txt.append(t5.to_markdown())
txt.append("\n## tổng 30 ngày: pinball trung bình P10/50/90 (rho PIT) k VND")
t6 = pd.DataFrame({m: {j: out["total_rho_fit"][m][j][0] for j in JARS} for m in MODELS}).T.round(0); txt.append(t6.to_markdown())
txt.append("\n## tổng 30 ngày: pinball tương đối so với " + BASE)
rt = {m: {"dense(2)": np.mean([out["total_rho_fit"][m][j][0] / out["total_rho_fit"][BASE][j][0] for j in dense]),
          "sparse(4)": np.mean([out["total_rho_fit"][m][j][0] / out["total_rho_fit"][BASE][j][0] for j in sparse]),
          "nghia_vu": out["total_rho_fit"][m]["nghia_vu"][0] / out["total_rho_fit"][BASE]["nghia_vu"][0]} for m in MODELS}
txt.append(pd.DataFrame(rt).T.round(2).to_markdown())
txt.append("\n## tổng 30 ngày: độ phủ trung bình dense(2) / sparse(4) (rho PIT)")
t7 = pd.DataFrame({m: {"dense": np.mean([out['total_rho_fit'][m][j][1] for j in dense]), "sparse": np.mean([out['total_rho_fit'][m][j][1] for j in sparse]),
                        "dense_indep": np.mean([out['total_indep'][m][j][1] for j in dense]), "sparse_indep": np.mean([out['total_indep'][m][j][1] for j in sparse])} for m in MODELS}).T.round(2)
txt.append(t7.to_markdown())
(HERE / "results" / "s3_metrics.md").write_text("\n".join(txt), encoding="utf-8")
print("\n".join(txt))
