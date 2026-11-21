"""Mục 4a: đo tải model, RAM đỉnh, thời gian suy luận CPU của Chronos-2 / chronos-2-small.
Chạy: HF_HOME=.hf-cache .venv/Scripts/python.exe s4_chronos_probe.py"""
import time, json, os, sys, warnings
import numpy as np, pandas as pd, psutil, torch
warnings.filterwarnings("ignore")
from common import *
from gen_data import covariates_for

proc = psutil.Process()
def peak_mb():
    mi = proc.memory_info()
    return round(getattr(mi, "peak_wset", mi.rss) / 1e6)
def rss_mb():
    return round(proc.memory_info().rss / 1e6)

print("torch", torch.__version__, "threads", torch.get_num_threads(), "rss_after_import_MB", rss_mb())
from chronos import Chronos2Pipeline
print("rss_after_chronos_import_MB", rss_mb(), "peak", peak_mb())
df = load()
cov_all = covariates_for(pd.date_range(df.index[0], periods=len(df) + 60, freq="D"))

def build(ctx_len, origin=335, n_rep=1, jars=JARS):
    rows, frows = [], []
    ctx_dates = df.index[origin - ctx_len + 1: origin + 1]
    fut_dates = pd.date_range(df.index[origin] + pd.Timedelta(days=1), periods=H, freq="D")
    for r in range(n_rep):
        rng = np.random.default_rng(r)
        for j in jars:
            sid = f"{j}_{r}"
            y = df[j].loc[ctx_dates].values * (1 if r == 0 else rng.uniform(0.7, 1.3))
            c = pd.DataFrame({"id": sid, "timestamp": ctx_dates, "target": y})
            c = pd.concat([c, cov_all.loc[ctx_dates].reset_index(drop=True)], axis=1)
            rows.append(c)
            f = pd.DataFrame({"id": sid, "timestamp": fut_dates})
            f = pd.concat([f, cov_all.loc[fut_dates].reset_index(drop=True)], axis=1)
            frows.append(f)
    return pd.concat(rows, ignore_index=True), pd.concat(frows, ignore_index=True)

res = {}
NAMES = [sys.argv[1]]
for name in NAMES:
    rec = {}
    t = time.perf_counter()
    pipe = Chronos2Pipeline.from_pretrained(name, device_map="cpu")
    rec["load_s_first"] = round(time.perf_counter() - t, 2)
    rec["peak_MB_after_load"] = peak_mb(); rec["rss_MB_after_load"] = rss_mb()
    rec["n_params_M"] = round(sum(p.numel() for p in pipe.model.parameters()) / 1e6, 1)
    rec["dtype"] = str(next(pipe.model.parameters()).dtype)
    # suy luận 7 chuỗi, các độ dài context
    for ctx in [90, 180, 335]:
        ctxdf, futdf = build(ctx)
        ts = []
        for k in range(3):
            t = time.perf_counter()
            out = pipe.predict_df(ctxdf, future_df=futdf, prediction_length=H, quantile_levels=[0.1, 0.5, 0.9], id_column="id", timestamp_column="timestamp", target="target")
            ts.append(time.perf_counter() - t)
        rec[f"infer7_ctx{ctx}_s"] = [round(x, 3) for x in ts]
    # không covariate
    ctxdf, futdf = build(180)
    cols0 = ["id", "timestamp", "target"]
    t = time.perf_counter(); pipe.predict_df(ctxdf[cols0], prediction_length=H, quantile_levels=[0.1, 0.5, 0.9], id_column="id", timestamp_column="timestamp", target="target"); rec["infer7_ctx180_nocov_s"] = round(time.perf_counter() - t, 3)
    # ngoại suy: 50 -> 350, 150 -> 1050 chuỗi (context 180), batch_size mặc định 256
    for n_rep in [50, 150]:
        ctxdf, futdf = build(180, n_rep=n_rep)
        t = time.perf_counter()
        out = pipe.predict_df(ctxdf, future_df=futdf, prediction_length=H, quantile_levels=[0.1, 0.5, 0.9], id_column="id", timestamp_column="timestamp", target="target")
        el = time.perf_counter() - t
        rec[f"batch_{7 * n_rep}series_ctx180_s"] = round(el, 2); rec[f"batch_{7 * n_rep}_series_per_s"] = round(7 * n_rep / el, 1)
    rec["peak_MB_final"] = peak_mb()
    res[name] = rec
    print(name, json.dumps(rec, indent=1))
    del pipe
# tải lần 2 (đã nóng trong page cache)
for name in NAMES:
    t = time.perf_counter(); p = Chronos2Pipeline.from_pretrained(name, device_map="cpu"); res[name]["load_s_second"] = round(time.perf_counter() - t, 2); del p
res["_env"] = dict(torch=torch.__version__, threads=torch.get_num_threads(), cpu_count=os.cpu_count())
(HERE / "results").mkdir(exist_ok=True)
(HERE / "results" / ("s4_chronos_probe_" + NAMES[0].split("/")[1] + ".json")).write_text(json.dumps(res, indent=1))
print("second load", {k: v.get("load_s_second") for k, v in res.items() if k != "_env"})
