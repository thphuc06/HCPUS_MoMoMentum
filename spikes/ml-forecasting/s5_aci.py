"""Mục 5: Adaptive Conformal Inference (Gibbs & Candes) tự viết, áp lên khoảng P10-P90 theo ngày của backtest.
Điểm sai số CQR s = max(q10 - y, y - q90); một alpha_t cho mỗi (hũ, nhóm horizon 1-7 / 8-14 / 15-30).
Phản hồi trễ: y của ngày t chỉ biết khi t <= origin; cập nhật alpha theo thứ tự ngày khi đã quan sát."""
import pickle
import numpy as np, pandas as pd
from common import *

d = pickle.load(open(HERE / "results" / "backtest_forecasts.pkl", "rb"))
tabs, Y, origins = d["tabs"], d["ytrue"], np.array(d["origins"])
ALPHA = 0.2
BINS = np.array([0] * 7 + [1] * 7 + [2] * 16)
MIN_POOL = 20


def aci_run(tab, y, origins, gamma, alpha=ALPHA, window=None):
    """tab: (n_orig, H, 13); y: (n_orig, H). Trả (lo, hi) đã hiệu chỉnh (n_orig, H) và alpha_t cuối cùng theo bin."""
    n = len(origins)
    lo = np.zeros((n, H)); hi = np.zeros((n, H))
    a_t = np.full(3, alpha); pool = [[], [], []]
    last_o = origins[0]
    for oi in range(n):
        o = origins[oi]
        if oi > 0:                                   # nạp các quan sát mới trong (origin_trước, origin_này]
            new = [(origins[j] + 1 + h, j, h) for j in range(oi) for h in range(H) if origins[oi - 1] < origins[j] + 1 + h <= o]
            for _, j, h in sorted(new):
                b = BINS[h]
                err = float(not (lo[j, h] <= y[j, h] <= hi[j, h]))
                a_t[b] += gamma * (alpha - err)
                pool[b].append(max(tab[j, h, 2] - y[j, h], y[j, h] - tab[j, h, 10]))
        for h in range(H):
            b = BINS[h]
            sc = np.array(pool[b][-window:] if window else pool[b])
            Q = cqr_conformal_q(sc, a_t[b]) if len(sc) >= MIN_POOL else 0.0
            lo[oi, h] = max(tab[oi, h, 2] - Q, 0.0); hi[oi, h] = tab[oi, h, 10] + Q
    return lo, hi, a_t


def evaluate(model, jars, gammas=(0.0, 0.005, 0.01, 0.02, 0.05), start=8):
    rows = []
    post = origins >= 251
    for j in jars:
        k = JARS.index(j)
        tab, y = tabs[model][:, k], Y[:, k]
        raw_lo, raw_hi = tab[:, :, 2], tab[:, :, 10]
        def cw(lo, hi, mask):
            m = mask[:, None]
            return (((y >= lo) & (y <= hi)) * m).sum() / (m.sum() * H), ((hi - lo) * m).sum() / (m.sum() * H)
        idx = np.arange(len(origins)) >= start
        r = {"jar": j, "raw_cov": cw(raw_lo, raw_hi, idx)[0], "raw_cov_post": cw(raw_lo, raw_hi, idx & post)[0], "raw_width": cw(raw_lo, raw_hi, idx)[1]}
        for g in gammas:
            lo, hi, a = aci_run(tab, y, origins, g)
            r[f"g{g}_cov"] = cw(lo, hi, idx)[0]; r[f"g{g}_cov_post"] = cw(lo, hi, idx & post)[0]; r[f"g{g}_width"] = cw(lo, hi, idx)[1]
            r[f"g{g}_alpha_end"] = tuple(np.round(a, 3))
        rows.append(r)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    out = []
    for model in ["ETS_native", "ETS_conf", "Chronos2", "Hurdle"]:
        df = evaluate(model, ["an_uong", "di_chuyen", "giai_tri", "mua_sam", "du_lich"])
        cov_cols = [c for c in df.columns if c.endswith("_cov")]
        post_cols = [c for c in df.columns if c.endswith("_cov_post")]
        w_cols = [c for c in df.columns if c.endswith("_width")]
        print(f"\n=== {model}: độ phủ daily P10-P90 (origin từ chỉ số 8, tức sau ~8 tuần nạp điểm) ===")
        print(df[["jar"] + cov_cols].round(3).to_markdown(index=False))
        print(f"mean over 5 jars:\n", df[cov_cols].mean().round(3).to_dict())
        print("post-break origins:", df[post_cols].mean().round(3).to_dict())
        print("mean width:", df[w_cols].mean().round(1).to_dict())
        print("alpha_t cuối (g=0.02):", df[["jar", "g0.02_alpha_end"]].values.tolist())
        out.append((model, df))
    pickle.dump(out, open(HERE / "results" / "s5_aci.pkl", "wb"))
