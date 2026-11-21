"""Mục 7: phát hiện thay đổi (ruptures PELT, river PageHinkley/ADWIN) và PyOD ECOD cho khoản lớn một lần."""
import json, time, warnings, importlib, pkgutil
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import ruptures as rpt, river
from river import drift
from common import *

df = load()
truth = json.load(open(HERE / "data" / "truth.json", encoding="utf-8"))
BK = truth["break_index"]            # 251 = 2026-07-10
SPEND = ["an_uong", "di_chuyen", "giai_tri"]          # 3 hũ chi đều (có điểm gãy cài sẵn)
daily = df[SPEND].sum(axis=1)
cov = df[["is_weekend", "days_since_payday"]]
print("điểm gãy thật: index", BK, df.index[BK].date(), "| trung bình chi/ngày trước:", round(daily[:BK].mean(), 1), "sau:", round(daily[BK:].mean(), 1), "(+%.0f%%)" % (100 * (daily[BK:].mean() / daily[:BK].mean() - 1)))

# --- chuỗi tuần không chồng lấn (52 tuần, tuần 0 bắt đầu 2025-11-01); tuần chứa điểm gãy = BK//7 ---------------------------
def weekly(x):
    n = len(x) // 7
    return x[: n * 7].reshape(n, 7).sum(1)
W_BREAK = BK // 7                     # 35 (tuần 35 gồm 7/7 .. 13/7... chỉ số 245..251 trước gãy; gãy xảy ra cuối tuần 35)
print("tuần chứa điểm gãy:", W_BREAK, "(ngày 245-251); mức mới bắt đầu tuần", W_BREAK + 1)
raw_w = weekly(daily.values)
# (B) cắt khoản lớn: giới hạn mỗi ngày ở trung vị + 4*MAD*1.4826 của riêng hũ (trên chuỗi ngày), như bước winsorize trước PELT
def winsor(s):
    s = s.copy()
    for c in s.columns:
        x = s[c]; med = x[x > 0].median(); mad = (x[x > 0] - med).abs().median() * 1.4826
        s[c] = x.clip(upper=med + 5 * mad)
    return s
win_w = weekly(winsor(df[SPEND]).sum(axis=1).values)
# (C) khử nhịp ngày lương: chia cho hồ sơ trung bình theo 'số ngày từ lương' ước lượng trên giai đoạn trước điểm gãy
pre = df.iloc[:BK]
prof = pre.groupby(pre["days_since_payday"].clip(upper=30))[SPEND].mean().sum(axis=1)
prof = prof / prof.mean()
adj = winsor(df[SPEND]).sum(axis=1).values / prof.reindex(df["days_since_payday"].clip(upper=30)).values
adj_w = weekly(adj)

def pelt_report(sig, name, bk_week=W_BREAK, min_size=2):
    sig = (sig - np.median(sig)) / (np.std(sig))
    s_hat = 1.4826 * np.median(np.abs(np.diff(sig) - np.median(np.diff(sig)))) / np.sqrt(2)   # sigma bền từ sai phân
    n = len(sig); base = s_hat ** 2 * np.log(n)
    rows = []
    for c in (0.5, 1, 2, 3, 5, 8):
        pen = c * base
        bk = rpt.Pelt(model="l2", min_size=min_size, jump=1).fit(sig.reshape(-1, 1)).predict(pen=pen)[:-1]
        hit = [b for b in bk if abs(b - (bk_week + 1)) <= 2]
        rows.append({"chuỗi": name, "c": c, "pen": round(pen, 2), "điểm gãy (tuần)": bk, "bắt đúng (±2 tuần)": bool(hit), "báo động giả": len(bk) - len(hit)})
    return rows

rows = []
for sig, name in [(raw_w, "A. tuần thô (có khoản lớn)"), (win_w, "B. tuần, cắt khoản lớn"), (adj_w, "C. tuần, cắt + khử nhịp ngày lương")]:
    rows += pelt_report(sig, name)
t = pd.DataFrame(rows)
print("\nPELT l2, min_size=2 tuần, penalty = c * sigma^2 * ln(n) (sigma bền từ sai phân); điểm gãy thật = tuần", W_BREAK + 1, "\n", t.to_markdown(index=False))
# PELT trên chuỗi NGÀY: trung bình cuộn 7 ngày, min_size=14, cho chuỗi C
roll = pd.Series(adj).rolling(7).mean().dropna().values
off = 6
s = (roll - np.median(roll)) / roll.std()
s_hat = 1.4826 * np.median(np.abs(np.diff(s) - np.median(np.diff(s)))) / np.sqrt(2)
base = s_hat ** 2 * np.log(len(s))
print("\nPELT trên chuỗi ngày (cuộn 7 ngày, cắt + khử nhịp), min_size=14, jump=1; điểm gãy thật = ngày", BK)
for c in (1, 3, 10, 30, 100):
    t0 = time.perf_counter()
    bk = rpt.Pelt(model="l2", min_size=14, jump=1).fit(s.reshape(-1, 1)).predict(pen=c * base)[:-1]
    el = time.perf_counter() - t0
    bkd = [b + off for b in bk]
    print(f"  c={c:>3}: điểm gãy (ngày) {bkd}  | thời gian {el*1000:.0f} ms | gần điểm gãy thật (±14 ngày): {[b for b in bkd if abs(b - BK) <= 14]}")
# cost 'normal' và 'l1' trên tuần C để so
for model in ("l1", "normal"):
    sig = (adj_w - np.median(adj_w)) / adj_w.std()
    try:
        ms = 3 if model == "normal" else 2
        bk = rpt.Pelt(model=model, min_size=ms, jump=1).fit(sig.reshape(-1, 1)).predict(pen=3 * np.log(len(sig)))[:-1]
        print(f"  model={model}, pen=3 ln n, min_size={ms}: {bk}")
    except Exception as e:
        print("  model", model, "lỗi", str(e)[:100])

# --- river ---------------------------------------------------------------------------------------------------------
print("\nriver", river.__version__, "| lớp trong river.drift:", sorted(n for n in dir(drift) if n[0].isupper()))
hits = []
for m in pkgutil.walk_packages(river.__path__, "river."):
    if "cusum" in m.name.lower():
        hits.append(m.name)
cus = [n for n in dir(drift) if "cusum" in n.lower()]
print("tìm 'cusum' trong tên module river:", hits, "| trong river.drift:", cus)
base_mu, base_sd = daily[:120].mean(), daily[:120].std()
z_daily = ((daily - base_mu) / base_sd).values
z_week = ((pd.Series(adj_w) - np.median(adj_w[:15])) / np.std(adj_w[:15])).values

def run_detector(det, xs):
    ev = []
    for i, x in enumerate(xs):
        det.update(float(x))
        if det.drift_detected:
            ev.append(i)
    return ev

def summarize(ev, bk, unit=1):
    pre_fa = [e for e in ev if e < bk]
    post = [e for e in ev if e >= bk]
    return {"sự kiện": ev, "báo giả trước gãy": len(pre_fa), "độ trễ phát hiện đầu tiên sau gãy": (post[0] - bk) if post else None}

print("\nChuỗi NGÀY, z theo 120 ngày đầu (tổng 3 hũ chi đều, có khoản lớn và nhịp ngày lương); điểm gãy = ngày", BK)
for thr in (5, 10, 20, 50):
    for mi in (30,):
        ev = run_detector(drift.PageHinkley(min_instances=mi, delta=0.005, threshold=thr, alpha=0.9999, mode="both"), z_daily)
        print(f"  PageHinkley threshold={thr:>3}:", summarize(ev, BK))
for clock in (32, 7, 1):
    for delta in (0.002, 0.0002):
        ev = run_detector(drift.ADWIN(delta=delta, clock=clock), z_daily)
        print(f"  ADWIN delta={delta} clock={clock:>2}:", summarize(ev, BK))
# ADWIN giả định giá trị trong [0,1] (Hoeffding): chuẩn hóa về [0,1] theo phân vị 99 của giai đoạn tham chiếu
x01_d = np.clip(daily.values / np.quantile(daily.values[:120], 0.99), 0, 1)
x01_w = np.clip(adj_w / (1.5 * np.max(adj_w[:15])), 0, 1)
print("\nADWIN trên chuỗi đã chuẩn hóa về [0,1] (ngày: chia phân vị 99 của 120 ngày đầu; tuần: chia 1,5 x max 15 tuần đầu)")
for clock in (32, 7, 1):
    for delta in (0.002, 0.01, 0.05):
        ev = run_detector(drift.ADWIN(delta=delta, clock=clock), x01_d)
        print(f"  NGÀY  ADWIN delta={delta} clock={clock:>2}:", summarize(ev, BK))
for clock in (32, 1):
    for delta in (0.002, 0.05, 0.3):
        ev = run_detector(drift.ADWIN(delta=delta, clock=clock), x01_w)
        print(f"  TUẦN  ADWIN delta={delta} clock={clock:>2}:", summarize(ev, W_BREAK + 1))
# kiểm tra công cụ: bậc thang sạch 0,2 -> 0,5 (nhiễu Gaussian sd 0,1) ở điểm 200 trong 365 điểm, và bậc +49% như dữ liệu nhưng sd nhỏ hơn
rng_chk = np.random.default_rng(0)
for lab_, lvl0, lvl1, sd in [("bậc 0,2->0,5 sd 0,1", 0.2, 0.5, 0.1), ("bậc 0,2->0,3 sd 0,15", 0.2, 0.3, 0.15)]:
    xs = np.clip(np.r_[rng_chk.normal(lvl0, sd, 200), rng_chk.normal(lvl1, sd, 165)], 0, 1)
    for clock in (32, 1):
        ev = run_detector(drift.ADWIN(delta=0.002, clock=clock), xs)
        print(f"  KIỂM TRA ADWIN {lab_} clock={clock:>2}:", summarize(ev, 200))
# tín hiệu/nhiễu của dữ liệu thật: độ dịch mức / độ lệch chuẩn ngày
print("  độ dịch mức (chuẩn hóa [0,1]) = %.3f, độ lệch chuẩn ngày = %.3f" % (x01_d[BK:].mean() - x01_d[:BK].mean(), x01_d[:BK].std()))
print("\nChuỗi TUẦN (C: cắt + khử nhịp; z theo 15 tuần đầu); điểm gãy = tuần", W_BREAK + 1)
for thr in (3, 5, 10, 20):
    ev = run_detector(drift.PageHinkley(min_instances=10, delta=0.005, threshold=thr, alpha=0.9999, mode="both"), z_week)
    print(f"  PageHinkley min_instances=10 threshold={thr:>3}:", summarize(ev, W_BREAK + 1))
for clock in (32, 1):
    ev = run_detector(drift.ADWIN(delta=0.002, clock=clock), z_week)
    print(f"  ADWIN delta=0.002 clock={clock:>2}:", summarize(ev, W_BREAK + 1))

# CUSUM hai phía tự viết (10 dòng) trên z tuần
def cusum(z, k=0.5, h=4.0):
    sp = sn = 0.0; ev = []
    for i, x in enumerate(z):
        sp = max(0.0, sp + x - k); sn = max(0.0, sn - x - k)
        if sp > h or sn > h:
            ev.append(i); sp = sn = 0.0
    return ev
for k, h in ((0.5, 4), (0.5, 5), (1.0, 4)):
    print(f"  CUSUM tự viết k={k} h={h} (tuần):", summarize(cusum(z_week, k, h), W_BREAK + 1))

# --- ECOD ------------------------------------------------------------------------------------------------------------------------
from pyod.models.ecod import ECOD
import pyod
lab = pd.DataFrame(truth["one_offs"])
anom = {(r.jar, r.date) for r in lab.itertuples() if r.kind == "one_off"}
rows = []
for j in ["an_uong", "di_chuyen", "giai_tri", "mua_sam", "du_lich"]:
    x = df[j]; pos = x[x > 0]; med = pos.median()
    for d_, v in pos.items():
        rows.append({"jar": j, "date": str(d_.date()), "amt": v, "ratio": v / med, "is_weekend": df.loc[d_, "is_weekend"], "dsp": df.loc[d_, "days_since_payday"]})
R = pd.DataFrame(rows)
R["y"] = [(r.jar, r.date) in anom for r in R.itertuples()]
X = np.c_[np.log(R["ratio"].values), np.log(R["amt"].values)]
print("\npyod", pyod.__version__, "| số dòng (hũ-ngày có chi):", len(R), "| nhãn bất thường:", int(R["y"].sum()), "(3 khoản lớn một lần chèn vào; hũ dự phòng bị loại vì mọi khoản của nó đều là cú sốc)")
for cont in (0.1, 0.05, 0.02, 0.01):
    t0 = time.perf_counter(); m = ECOD(contamination=cont).fit(X); el = time.perf_counter() - t0
    pred = m.labels_.astype(bool)
    tp = int((pred & R["y"].values).sum()); fp = int((pred & ~R["y"].values).sum()); fn = int((~pred & R["y"].values).sum())
    predR = pred & (R["ratio"].values > 1); tpR = int((predR & R["y"].values).sum())
    print(f"  (chỉ đuôi phải: gắn cờ {predR.sum()}, TP={tpR}, FP={predR.sum() - tpR})")
    print(f"  ECOD contamination={cont}: gắn cờ {pred.sum()}, TP={tp}, FP={fp}, FN={fn}, precision={tp/max(1,pred.sum()):.2f}, recall={tp/max(1,R['y'].sum()):.2f}, fit {el*1000:.0f} ms")
m = ECOD(contamination=0.02).fit(X)
R["score"] = m.decision_scores_
top = R.sort_values("score", ascending=False).head(12)
print("  top-12 điểm ECOD:\n", top[["jar", "date", "amt", "score", "y"]].round(1).to_markdown(index=False))
rk = R["score"].rank(ascending=False)
print("  hạng của các khoản có nhãn:", sorted(rk[R["y"]].astype(int).tolist()))
# z bền (MAD) một chiều trên số tiền theo hũ để so
z = R.groupby("jar")["amt"].transform(lambda s: (s - s.median()) / (1.4826 * (s - s.median()).abs().median()))
for thr in (6, 10):
    pred = (z > thr).values
    tp = int((pred & R["y"].values).sum()); print(f"  z bền MAD > {thr}: gắn cờ {pred.sum()}, TP={tp}, FP={int(pred.sum()) - tp}")
