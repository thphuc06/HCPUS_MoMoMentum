"""Kiểm tra độ bền: lặp backtest (SN_conf, ETS_native, Hurdle, Chronos2, Chronos2_nocov) trên 4 hạt giống khác của bộ sinh dữ liệu.
Nhắc lại: cùng bộ sinh, chỉ đổi seed => chỉ kiểm độ ổn định theo ngẫu nhiên, KHÔNG kiểm khái quát sang dữ liệu thật."""
import os, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
from statsforecast import StatsForecast
from statsforecast.models import SeasonalNaive, AutoETS
from statsforecast.utils import ConformalIntervals
from common import *
from gen_data import build_history, covariates_for
from forecasters import sf_tables, hurdle_forecast, chronos_tables, to_long
from chronos import Chronos2Pipeline

pipe = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map="cpu")
SPEND = [j for j in JARS if j != "nghia_vu"]
TAU = {0.1: 2, 0.5: 6, 0.9: 10}
cov_all = covariates_for(pd.date_range("2025-11-01", periods=365 + 60, freq="D"))
sf = StatsForecast(models=[SeasonalNaive(season_length=7, alias="SN_conf"), AutoETS(season_length=7, alias="ETS_native")], freq="D", n_jobs=1)
sfn = StatsForecast(models=[AutoETS(season_length=7, alias="ETS_native")], freq="D", n_jobs=1)
rows = []
for seed in (101, 102, 103, 104):
    d, _, _ = build_history(seed)
    d.index.name = "date"
    Y = d[JARS].values
    res = {m: {j: [] for j in SPEND} for m in ("SN_conf", "ETS_native", "Hurdle", "Chronos2", "Chronos2_nocov")}
    cov = {m: {j: [] for j in SPEND} for m in res}
    for o in ORIGINS:
        tr = to_long(d, o); y = Y[o + 1: o + 1 + H].T
        f1 = sfn.forecast(df=tr, h=H, level=LEVELS_PCT)
        f2 = StatsForecast(models=[SeasonalNaive(season_length=7, alias="SN_conf")], freq="D").forecast(df=tr, h=H, level=LEVELS_PCT, prediction_intervals=ConformalIntervals(h=H, n_windows=2))
        tabs = {"ETS_native": sf_tables(f1, "ETS_native"), "SN_conf": sf_tables(f2, "SN_conf")}
        rng = np.random.default_rng(o)
        tabs["Hurdle"] = np.stack([hurdle_forecast(Y[: o + 1, k], cov_all.iloc[: o + 1], cov_all.iloc[o + 1: o + 1 + H], rng) for k in range(len(JARS))])
        tabs["Chronos2"] = chronos_tables(pipe, d, cov_all, o)
        tabs["Chronos2_nocov"] = chronos_tables(pipe, d, cov_all, o, use_cov=False)
        for m, t in tabs.items():
            for j in SPEND:
                k = JARS.index(j)
                res[m][j].append(np.mean([pinball(y[k], t[k, :, i], tau).mean() for tau, i in TAU.items()]))
                cov[m][j].append(((y[k] >= t[k, :, 2]) & (y[k] <= t[k, :, 10])).mean())
    base = {j: np.mean(res["SN_conf"][j]) for j in SPEND}
    for m in res:
        rel = np.mean([np.mean(res[m][j]) / base[j] for j in SPEND if base[j] > 1e-9])
        rel_dense = np.mean([np.mean(res[m][j]) / base[j] for j in ("an_uong", "di_chuyen")])
        rows.append({"seed": seed, "model": m, "rel_SN_conf (6 hũ)": round(rel, 2), "rel (2 hũ dày)": round(rel_dense, 2),
                     "phủ daily an_uong": round(np.mean(cov[m]["an_uong"]), 2), "phủ daily di_chuyen": round(np.mean(cov[m]["di_chuyen"]), 2)})
    print("seed", seed, "xong", flush=True)
t = pd.DataFrame(rows)
print(t.to_markdown(index=False))
print("\ntrung bình theo model:\n", t.groupby("model")[["rel_SN_conf (6 hũ)", "rel (2 hũ dày)", "phủ daily an_uong", "phủ daily di_chuyen"]].agg(["mean", "std"]).round(3).to_markdown())
t.to_csv(HERE / "results" / "s10_seeds.csv", index=False)
