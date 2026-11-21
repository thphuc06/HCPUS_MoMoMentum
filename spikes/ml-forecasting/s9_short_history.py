"""Bổ sung (câu hỏi 'chưa chắc' trong ml-forecasting.md): độ dài lịch sử tối thiểu. Cắt lịch sử còn L ngày cuối, so các model theo pinball.
Các origin 150..330 bước 14 (14 cửa sổ), horizon 30, 6 hũ chi tiêu (bỏ nghĩa vụ). Baseline = SN_native cùng L."""
import os, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
from statsforecast import StatsForecast
from statsforecast.models import SeasonalNaive, AutoETS
from common import *
from gen_data import covariates_for
from forecasters import sf_tables, hurdle_forecast, chronos_tables
from chronos import Chronos2Pipeline

df = load(); Y = df[JARS].values
cov_all = covariates_for(pd.date_range(df.index[0], periods=len(df) + 60, freq="D"))
SPEND = [j for j in JARS if j != "nghia_vu"]
pipe = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map="cpu")
sfn = StatsForecast(models=[SeasonalNaive(season_length=7, alias="SN"), AutoETS(season_length=7, alias="ETS")], freq="D", n_jobs=1)
TAU = {0.1: 2, 0.5: 6, 0.9: 10}
origins = list(range(150, 336, 14))


def pl(tab, y):          # tab (7,H,13), y (7,H) -> trung bình pinball theo hũ chi tiêu
    return {j: np.mean([pinball(y[JARS.index(j)], tab[JARS.index(j), :, i], t).mean() for t, i in TAU.items()]) for j in SPEND}


rows = []
for L in (14, 21, 30, 60, 90):
    acc = {m: [] for m in ("SN", "ETS", "Hurdle", "Chronos2", "Chronos2_nocov")}
    fails = {m: 0 for m in acc}
    for o in origins:
        lo = o - L + 1
        sub = df.iloc[lo: o + 1]
        long = sub[JARS].reset_index().melt(id_vars="date", var_name="unique_id", value_name="y").rename(columns={"date": "ds"}).sort_values(["unique_id", "ds"])
        y = Y[o + 1: o + 1 + H].T
        try:
            f = sfn.forecast(df=long, h=H, level=LEVELS_PCT)
            tabs = {"SN": sf_tables(f, "SN"), "ETS": sf_tables(f, "ETS")}
            if not np.isfinite(tabs["ETS"]).all():
                raise ValueError("nan")
        except Exception as e:
            tabs = {}; fails["SN"] += 1; fails["ETS"] += 1
        rng = np.random.default_rng(o)
        cov_h = cov_all.iloc[lo: o + 1]; cov_f = cov_all.iloc[o + 1: o + 1 + H]
        tabs["Hurdle"] = np.stack([hurdle_forecast(Y[lo: o + 1, k], cov_h, cov_f, rng, window=L) for k in range(len(JARS))])
        tabs["Chronos2"] = chronos_tables(pipe, df, cov_all, o, ctx_len=L)
        tabs["Chronos2_nocov"] = chronos_tables(pipe, df, cov_all, o, ctx_len=L, use_cov=False)
        for m, t in tabs.items():
            acc[m].append(pl(t, y))
    base = {j: np.mean([a[j] for a in acc["SN"]]) for j in SPEND} if acc["SN"] else None
    for m in acc:
        if not acc[m]:
            rows.append({"L ngày": L, "model": m, "rel. SN (6 hũ)": np.nan, "lỗi": fails[m]}); continue
        mm = {j: np.mean([a[j] for a in acc[m]]) for j in SPEND}
        rel = np.mean([mm[j] / base[j] for j in SPEND if base[j] > 1e-9]) if base else np.nan
        rows.append({"L ngày": L, "model": m, "rel. SN (6 hũ)": round(rel, 2), "pinball an_uong": round(mm["an_uong"], 1), "pinball mua_sam": round(mm["mua_sam"], 1), "số cửa sổ lỗi": fails[m]})
t = pd.DataFrame(rows)
print(t.to_markdown(index=False))
t.to_csv(HERE / "results" / "s9_short_history.csv", index=False)
