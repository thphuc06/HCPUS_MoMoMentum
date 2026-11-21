"""Mục 3/4 bổ sung: (a) quét rho cho độ phủ tổng 30 ngày (trước/sau điểm gãy), (b) chênh lệch từng origin giữa các model + sai số chuẩn thô."""
import pickle
import numpy as np, pandas as pd
from common import *
d = pickle.load(open(HERE / "results" / "backtest_forecasts.pkl", "rb"))
tabs, Y, origins = d["tabs"], d["ytrue"], np.array(d["origins"])
BREAK_IDX = 251
pre = origins + H < BREAK_IDX; post = origins >= BREAK_IDX
TAU_IDX = {0.1: 2, 0.5: 6, 0.9: 10}
dense3 = ["an_uong", "di_chuyen", "giai_tri"]

def tot_cov(m, jars, rho, mask, N=2000, seed=3):
    rng = np.random.default_rng(seed); cov = []
    for j in jars:
        k = JARS.index(j)
        for oi in np.where(mask)[0]:
            s = sample_from_qtable(ndtr(ar1_normals(rng, N, H, rho)), tabs[m][oi, k]).sum(1)
            a, b = np.quantile(s, [0.1, 0.9]); cov.append(a <= Y[oi, k].sum() <= b)
    return float(np.mean(cov))

rows = []
for m in ["ETS_native", "Hurdle", "Chronos2", "Chronos2_small"]:
    for seg, mask in [("pre_break", pre), ("post_break", post), ("all", np.ones(len(origins), bool))]:
        rows.append({"model": m, "segment": seg, **{f"rho={r}": round(tot_cov(m, dense3, r, mask), 2) for r in (0.0, 0.2, 0.4, 0.6, 0.8)}})
t = pd.DataFrame(rows)
print("Độ phủ P10-P90 của TỔNG 30 NGÀY, gộp 3 hũ dày (an_uong, di_chuyen, giai_tri), theo rho copula\n", t.to_markdown(index=False))

def per_origin_pl(m, jars):
    return np.array([np.mean([np.mean([pinball(Y[oi, JARS.index(j)], tabs[m][oi, JARS.index(j), :, i], tau).mean() for tau, i in TAU_IDX.items()]) for j in jars]) for oi in range(len(origins))])
spend6 = [j for j in JARS if j != "nghia_vu"]
rel = {}
for a, b in [("Chronos2", "Hurdle"), ("Chronos2", "ETS_native"), ("Chronos2", "Chronos2_nocov"), ("Chronos2", "Chronos2_small"), ("Hurdle", "ETS_native")]:
    pa = per_origin_pl(a, spend6); pb = per_origin_pl(b, spend6)
    # tương đối theo từng hũ rồi trung bình để không bị hũ lớn chi phối
    ra = []
    for j in spend6:
        x = per_origin_pl(a, [j]); y = per_origin_pl(b, [j])
        ra.append(np.where(y > 1e-9, x / np.maximum(y, 1e-9), np.nan))
    r = np.nanmean(np.stack(ra), axis=0)
    rel[f"{a}/{b}"] = (np.mean(r), np.std(r, ddof=1) / np.sqrt(len(r)), (r < 1).mean())
print("\nTỉ lệ pinball (6 hũ chi tiêu, trung bình theo hũ rồi theo origin; <1 = model đầu tốt hơn): mean, SE thô (origin chồng lấn nên SE bị đánh thấp), tỉ lệ origin thắng")
for k, v in rel.items():
    print(f"{k:28s} {v[0]:.3f}  SE {v[1]:.3f}  win {v[2]:.2f}")
