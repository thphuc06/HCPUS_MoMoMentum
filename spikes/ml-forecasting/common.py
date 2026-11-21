"""Hàm dùng chung: đọc dữ liệu, bảng phân vị, pinball, ACI, Monte Carlo."""
from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd
from scipy.special import ndtr

HERE = Path(__file__).parent
JARS = ["an_uong", "di_chuyen", "giai_tri", "mua_sam", "du_lich", "nghia_vu", "du_phong"]
H = 30
# 13 mức phân vị dùng chung cho mọi model (từ các level 98/90/80/60/40/20 + trung vị)
QLEVELS = np.array([0.01, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99])
LEVELS_PCT = [98, 90, 80, 60, 40, 20]
# origin: chỉ số ngày cuối của tập huấn luyện; 120..335 bước 7 => 31 cửa sổ
ORIGINS = list(range(120, 336, 7))


def load():
    df = pd.read_csv(HERE / "data" / "minh_daily.csv", parse_dates=["date"]).set_index("date")
    return df


def pinball(y, q, tau):
    d = y - q
    return np.maximum(tau * d, (tau - 1) * d)


def make_qtable_from_levels(point, lo, hi):
    """point: (H,), lo/hi: dict level_pct -> (H,). Trả (H, 13) đơn điệu, cắt >= 0."""
    cols = []
    for tau in QLEVELS:
        if abs(tau - 0.5) < 1e-9:
            cols.append(point)
        elif tau < 0.5:
            cols.append(lo[int(round((1 - 2 * tau) * 100))])
        else:
            cols.append(hi[int(round((2 * tau - 1) * 100))])
    q = np.stack(cols, axis=1)
    q = np.maximum.accumulate(np.maximum(q, 0.0), axis=1)
    return q


def ar1_normals(rng, N, Hh, rho):
    e = rng.standard_normal((N, Hh))
    if rho == 0:
        return e
    z = np.empty_like(e)
    z[:, 0] = e[:, 0]
    s = np.sqrt(1 - rho ** 2)
    for h in range(1, Hh):
        z[:, h] = rho * z[:, h - 1] + s * e[:, h]
    return z


def sample_from_qtable(u, q, tau=QLEVELS):
    """u: (N, H) trong (0,1); q: (H, K) phân vị theo ngày. Nội suy tuyến tính, vector hóa hoàn toàn.
    Đuôi: dưới tau[0] nội suy về q(0)=0 tại u=0; trên tau[-1] ngoại suy tuyến tính theo độ dốc đoạn cuối."""
    tau_e = np.concatenate([[0.0], tau, [1.0]])
    Hh = q.shape[0]
    q0 = np.zeros((Hh, 1))
    slope = (q[:, -1] - q[:, -2]) / (tau[-1] - tau[-2])
    q1 = (q[:, -1] + slope * (1.0 - tau[-1]))[:, None]
    qe = np.concatenate([q0, q, q1], axis=1)          # (H, K+2)
    i = np.clip(np.searchsorted(tau_e, u, side="right"), 1, len(tau_e) - 1)   # (N, H)
    cols = np.arange(Hh)[None, :]
    t_lo, t_hi = tau_e[i - 1], tau_e[i]
    w = (u - t_lo) / (t_hi - t_lo)
    return qe[cols, i - 1] * (1 - w) + qe[cols, i] * w


def cqr_conformal_q(scores, alpha_t):
    n = len(scores)
    if n == 0:
        return 0.0
    if alpha_t <= 0:
        return float(np.max(scores)) * 2 + 1e-9
    if alpha_t >= 1:
        return float(np.min(scores))
    k = min(n, int(np.ceil((n + 1) * (1 - alpha_t))))
    return float(np.sort(scores)[k - 1])
