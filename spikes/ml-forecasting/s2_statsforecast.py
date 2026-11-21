"""Mục 2: StatsForecast 2.1.1 - cài, import, thời gian fit+forecast 30 ngày x 7 chuỗi, khả năng tạo khoảng dự báo.
Chạy trong .venv-sf (môi trường tối thiểu, không có torch/pyod/numba)."""
import sys, time, warnings, json
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
t0 = time.perf_counter()
from statsforecast import StatsForecast
from statsforecast.models import SeasonalNaive, AutoETS, CrostonClassic, TSB, ADIDA, IMAPA
from statsforecast.utils import ConformalIntervals
t_imp = time.perf_counter() - t0
print("import_s", round(t_imp, 2), "numba_loaded", "numba" in sys.modules)

df = pd.read_csv(Path(__file__).parent / "data" / "minh_daily.csv", parse_dates=["date"]).set_index("date")
JARS = ["an_uong", "di_chuyen", "giai_tri", "mua_sam", "du_lich", "nghia_vu", "du_phong"]
long = df[JARS].iloc[:335].reset_index().melt(id_vars="date", var_name="unique_id", value_name="y").rename(columns={"date": "ds"})
long = long.sort_values(["unique_id", "ds"]).reset_index(drop=True)

models = {"SeasonalNaive": SeasonalNaive(season_length=7), "AutoETS": AutoETS(season_length=7),
          "CrostonClassic": CrostonClassic(), "TSB": TSB(alpha_d=0.2, alpha_p=0.2), "ADIDA": ADIDA(), "IMAPA": IMAPA()}
out = {}
for name, m in models.items():
    sf = StatsForecast(models=[m], freq="D", n_jobs=1)
    # (a) chỉ điểm
    t = time.perf_counter(); f0 = sf.forecast(df=long, h=30); t_pt = time.perf_counter() - t
    # lần 2 (nóng)
    t = time.perf_counter(); sf.forecast(df=long, h=30); t_pt2 = time.perf_counter() - t
    rec = dict(point_first_s=round(t_pt, 3), point_second_s=round(t_pt2, 3))
    # (b) khoảng native
    try:
        t = time.perf_counter(); f1 = sf.forecast(df=long, h=30, level=[80]); rec["native_s"] = round(time.perf_counter() - t, 3)
        cols = [c for c in f1.columns if "lo-80" in c]
        rec["native_interval"] = bool(cols)
        if cols:
            lo = f1[cols[0]].values; hi = f1[cols[0].replace("lo", "hi")].values; mu = f1[name].values
            rec["native_width_mean"] = round(float(np.mean(hi - lo)), 1); rec["native_lo_negative_share"] = round(float((lo < 0).mean()), 2)
            rec["native_flat_forecast"] = bool(np.allclose(f1.groupby("unique_id")[name].transform("std").fillna(0), 0, atol=1e-6))
    except Exception as e:
        rec["native_interval"] = f"ERROR {type(e).__name__}: {str(e)[:120]}"
    # (c) conformal
    try:
        t = time.perf_counter()
        f2 = sf.forecast(df=long, h=30, prediction_intervals=ConformalIntervals(h=30, n_windows=2), level=[80])
        rec["conformal_s"] = round(time.perf_counter() - t, 3)
        cols = [c for c in f2.columns if "lo-80" in c]
        rec["conformal_interval"] = bool(cols)
        if cols:
            lo = f2[cols[0]].values; hi = f2[cols[0].replace("lo", "hi")].values
            rec["conformal_width_mean"] = round(float(np.mean(hi - lo)), 1)
    except Exception as e:
        rec["conformal_interval"] = f"ERROR {type(e).__name__}: {str(e)[:160]}"
    out[name] = rec
    print(name, rec)

# tất cả 6 model một lượt (thời gian "cả bộ" cho 7 chuỗi), có và không conformal
sf = StatsForecast(models=list(models.values()), freq="D", n_jobs=1)
t = time.perf_counter(); sf.forecast(df=long, h=30); all_pt = time.perf_counter() - t
t = time.perf_counter(); sf.forecast(df=long, h=30, level=[80]); all_nat = time.perf_counter() - t
print("ALL6 point_s", round(all_pt, 2), "level80_s", round(all_nat, 2))
Path(__file__).parent.joinpath("results").mkdir(exist_ok=True)
Path(__file__).parent.joinpath("results", "s2_statsforecast.json").write_text(json.dumps(dict(import_s=t_imp, models=out, all6_point_s=all_pt, all6_level80_s=all_nat), indent=1, default=str))
