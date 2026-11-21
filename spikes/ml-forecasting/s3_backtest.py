"""Mục 3+4: chạy dự báo rolling-origin (31 origin, mỗi 7 ngày, h=30) cho mọi model, lưu bảng phân vị 13 mức.
Chạy: HF_HOME=.hf-cache HF_HUB_OFFLINE=1 .venv/Scripts/python.exe s3_backtest.py"""
import time, pickle, warnings, os
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from statsforecast import StatsForecast
from statsforecast.models import SeasonalNaive, AutoETS, CrostonClassic, TSB, ADIDA, IMAPA
from statsforecast.utils import ConformalIntervals
from common import *
from gen_data import covariates_for

df = load()
Y = df[JARS].values                       # (365, 7)
cov_all = covariates_for(pd.date_range(df.index[0], periods=len(df) + 60, freq="D"))
dates = df.index


from forecasters import sf_tables, hurdle_forecast, chronos_tables, to_long


MODELS = ["SN_native", "SN_conf", "ETS_native", "ETS_conf", "Croston_conf", "TSB_conf", "ADIDA_conf", "IMAPA_conf", "Hurdle",
          "Chronos2", "Chronos2_nocov", "Chronos2_small"]
tabs = {m: np.zeros((len(ORIGINS), len(JARS), H, len(QLEVELS))) for m in MODELS}
ytrue = np.zeros((len(ORIGINS), len(JARS), H))
timing = {m: 0.0 for m in MODELS}

from chronos import Chronos2Pipeline
pipes = {"Chronos2": Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map="cpu"),
         "Chronos2_small": Chronos2Pipeline.from_pretrained("autogluon/chronos-2-small", device_map="cpu")}

sf_native = StatsForecast(models=[SeasonalNaive(season_length=7, alias="SN_native"), AutoETS(season_length=7, alias="ETS_native")], freq="D", n_jobs=1)
sf_conf = StatsForecast(models=[SeasonalNaive(season_length=7, alias="SN_conf"), AutoETS(season_length=7, alias="ETS_conf"),
                                CrostonClassic(alias="Croston_conf"), TSB(alpha_d=0.2, alpha_p=0.2, alias="TSB_conf"),
                                ADIDA(alias="ADIDA_conf"), IMAPA(alias="IMAPA_conf")], freq="D", n_jobs=1)
for oi, o in enumerate(ORIGINS):
    tr = to_long(df, o)
    ytrue[oi] = Y[o + 1: o + 1 + H].T
    t = time.perf_counter(); f1 = sf_native.forecast(df=tr, h=H, level=LEVELS_PCT); dt = time.perf_counter() - t
    for a in ["SN_native", "ETS_native"]:
        tabs[a][oi] = sf_tables(f1, a)
    timing["SN_native"] += dt / 2; timing["ETS_native"] += dt / 2
    t = time.perf_counter(); f2 = sf_conf.forecast(df=tr, h=H, level=LEVELS_PCT, prediction_intervals=ConformalIntervals(h=H, n_windows=2)); dt = time.perf_counter() - t
    for a in ["SN_conf", "ETS_conf", "Croston_conf", "TSB_conf", "ADIDA_conf", "IMAPA_conf"]:
        tabs[a][oi] = sf_tables(f2, a)
    for a in ["SN_conf", "ETS_conf", "Croston_conf", "TSB_conf", "ADIDA_conf", "IMAPA_conf"]:
        timing[a] += dt / 6
    t = time.perf_counter()
    rng = np.random.default_rng(1000 + oi)
    cov_hist = cov_all.iloc[: o + 1]; cov_fut = cov_all.iloc[o + 1: o + 1 + H]
    for k, j in enumerate(JARS):
        tabs["Hurdle"][oi, k] = hurdle_forecast(Y[: o + 1, k], cov_hist, cov_fut, rng)
    timing["Hurdle"] += time.perf_counter() - t
    for name, key, kw in [("Chronos2", "Chronos2", {}), ("Chronos2_nocov", "Chronos2", dict(use_cov=False)), ("Chronos2_small", "Chronos2_small", {})]:
        t = time.perf_counter()
        tabs[name][oi] = chronos_tables(pipes[key], df, cov_all, o, **kw)
        timing[name] += time.perf_counter() - t
    print("origin", o, "done", flush=True)

with open(HERE / "results" / "backtest_forecasts.pkl", "wb") as f:
    pickle.dump(dict(tabs=tabs, ytrue=ytrue, origins=ORIGINS, jars=JARS, qlevels=QLEVELS, timing=timing), f)
print({k: round(v, 2) for k, v in timing.items()})
