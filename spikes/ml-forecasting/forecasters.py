"""Hàm dự báo dùng chung (StatsForecast -> bảng phân vị, hurdle tự viết, Chronos-2 -> bảng phân vị)."""
import numpy as np, pandas as pd
from common import *


def to_long(df, end_idx):
    d = df[JARS].iloc[: end_idx + 1].reset_index().melt(id_vars="date", var_name="unique_id", value_name="y").rename(columns={"date": "ds"})
    return d.sort_values(["unique_id", "ds"]).reset_index(drop=True)


def sf_tables(fc, alias):
    """fc: DataFrame forecast với level=LEVELS_PCT -> (7, H, 13) theo thứ tự JARS."""
    out = np.zeros((len(JARS), H, len(QLEVELS)))
    for k, j in enumerate(JARS):
        s = fc[fc["unique_id"] == j].sort_values("ds")
        pt = s[alias].values
        lo = {l: s[f"{alias}-lo-{l}"].values for l in LEVELS_PCT}
        hi = {l: s[f"{alias}-hi-{l}"].values for l in LEVELS_PCT}
        out[k] = make_qtable_from_levels(pt, lo, hi)
    return out


def hurdle_forecast(y_hist, cov_hist, cov_fut, rng, window=180, nsim=4000):
    y = y_hist[-window:]
    wk = cov_hist["is_weekend"].values[-window:]; d = cov_hist["days_since_payday"].values[-window:]
    early = (d <= 7).astype(int)
    pos = y[y > 0]
    out = np.zeros((H, len(QLEVELS)))
    wkf = cov_fut["is_weekend"].values; df_ = cov_fut["days_since_payday"].values
    for h in range(H):
        cell = (wk == wkf[h]) & (early == int(df_[h] <= 7))
        n = cell.sum(); k = (y[cell] > 0).sum()
        if n < 8:     # ô quá ít dữ liệu -> dùng toàn cửa sổ
            n = len(y); k = (y > 0).sum()
        p = (k + 1) / (n + 3)
        if len(pos) == 0:
            out[h] = 0
            continue
        has = rng.random(nsim) < p
        sizes = rng.choice(pos, size=nsim, replace=True)
        out[h] = np.quantile(np.where(has, sizes, 0.0), QLEVELS)
    return out


def chronos_tables(pipe, df, cov_all, end_idx, ctx_len=None, use_cov=True):
    dates = df.index
    ctx_dates = dates[: end_idx + 1] if ctx_len is None else dates[max(0, end_idx + 1 - ctx_len): end_idx + 1]
    fut_dates = pd.date_range(dates[end_idx] + pd.Timedelta(days=1), periods=H, freq="D")
    rows, frows = [], []
    for j in JARS:
        c = pd.DataFrame({"id": j, "timestamp": ctx_dates, "target": df[j].loc[ctx_dates].values})
        if use_cov:
            c = pd.concat([c, cov_all.loc[ctx_dates].reset_index(drop=True)], axis=1)
        rows.append(c)
        f = pd.DataFrame({"id": j, "timestamp": fut_dates})
        if use_cov:
            f = pd.concat([f, cov_all.loc[fut_dates].reset_index(drop=True)], axis=1)
        frows.append(f)
    ctxdf = pd.concat(rows, ignore_index=True); futdf = pd.concat(frows, ignore_index=True) if use_cov else None
    out = pipe.predict_df(ctxdf, future_df=futdf, prediction_length=H, quantile_levels=[float(q) for q in QLEVELS],
                          id_column="id", timestamp_column="timestamp", target="target")
    tab = np.zeros((len(JARS), H, len(QLEVELS)))
    qcols = {float(c): c for c in out.columns if c not in ("id", "timestamp", "predictions", "target_name")}
    for k, j in enumerate(JARS):
        s = out[out["id"] == j].sort_values("timestamp")
        tab[k] = np.stack([s[qcols[float(q)]].values for q in QLEVELS], axis=1)
    return np.maximum.accumulate(np.maximum(tab, 0.0), axis=2)


