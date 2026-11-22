"""Monte Carlo số dư hũ (numpy vector hóa).

Mỗi đường là một kịch bản chi tiêu `H` ngày của MỘT hũ, cộng lịch tất định (lương vào hũ theo ngày nhận, nghĩa vụ rút từ hũ
theo ngày đến hạn; nghĩa vụ khai theo khoảng thì lấy mẫu đều trong khoảng):

    số_dư[d] = số_dư_đầu + tổng_{t <= d} (lương[t] - nghĩa_vụ[t] - chi[t])

Cách sinh `chi[t]`:
- **hũ dày** (và khởi đầu lạnh): copula Gaussian AR(1). z_t = rho z_{t-1} + sqrt(1 - rho^2) e_t, u_t = Phi(z_t), chi_t =
  ppf_t(u_t) (phân phối biên đúng của mô hình, không nội suy bảng 13 mức). Tương quan dương giữa các ngày làm xác suất hụt
  không bị đánh giá thấp như khi lấy mẫu độc lập (spike ML §6).
- **hũ thưa**: mô phỏng hurdle trực tiếp: mỗi đường rút xác suất có chi của từng ô lịch từ Beta posterior (bất định về mức,
  chung cho cả horizon), mỗi ngày Bernoulli độc lập rồi lấy số tiền từ phân phối số tiền (spike: copula Gaussian qua phân vị
  có khối lượng ở 0 cho kết quả sai hướng ở hũ thưa).
- **hệ số mức chung** M = exp(sigma xi - sigma^2 / 2) (trung bình 1, xi chuẩn) nhân chi tiêu của cả horizon: bắt "sai lệch mức
  kéo dài" mà tương quan lag-1 không bắt được. `rho` và `sigma` là THAM SỐ HIỆU CHỈNH do backtest chọn (xem
  `yofina_ml.calibration`), không phải hằng số gắn cứng.

Tất định và "common random numbers": mọi số ngẫu nhiên của một hũ lấy từ các dòng riêng sinh bởi
`SeedSequence([seed, ngày_gốc, crc32(mã_hũ)])`; mỗi dòng (copula, độc lập, Beta, hệ số mức, nghĩa vụ theo khoảng) có bộ sinh
riêng nên đổi số dư, lịch lương hay nghĩa vụ KHÔNG làm đổi các số ngẫu nhiên còn lại: kịch bản gốc và kịch bản what-if dùng
cùng dãy ngẫu nhiên, chênh lệch trước-sau không bị nhiễu mẫu. Đổi `n_paths` chỉ cắt hoặc nối thêm hàng.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from datetime import date

import numpy as np
from scipy.signal import lfilter
from scipy.special import betaincinv, ndtr

from yofina_ml.calibration import SeriesCalibration
from yofina_ml.daycal import DayFeatures
from yofina_ml.marginals import HurdleMarginal, Marginal

_MASK = (1 << 63) - 1


@dataclass(frozen=True)
class SimSpec:
    """Mọi thứ cần để mô phỏng một hũ (không có số ngẫu nhiên)."""

    balance_vnd: float
    marginal: Marginal
    feats: DayFeatures  # đặc trưng của H ngày dự báo
    sparse: bool  # hũ thưa và biên là hurdle: mô phỏng hurdle trực tiếp
    inflow: np.ndarray  # (H,) tiền vào tất định mỗi ngày
    outflow: np.ndarray  # (H,) nghĩa vụ tất định mỗi ngày
    ranged: tuple[
        tuple[int, float, float], ...
    ] = ()  # (chỉ số ngày, min, max) nghĩa vụ theo khoảng
    window: int = 0  # số ngày đầu tính "trước kỳ lương"


@dataclass(frozen=True)
class SimSummary:
    balance_p10: np.ndarray  # (H,) int
    balance_p50: np.ndarray
    balance_p90: np.ndarray
    p_shortfall: float
    p_shortfall_se: float
    runout_index: int | None  # chỉ số ngày (0 là app_date + 1) đầu tiên số dư P50 <= ngưỡng


def jar_seed_sequence(seed: int | None, app_date: date, jar_code: str) -> np.random.SeedSequence:
    """Hạt giống tất định theo (seed của cấu hình, ngày gốc, mã hũ). `seed` None được coi như 0 (vẫn tất định)."""
    base = 0 if seed is None else int(seed) & _MASK
    return np.random.SeedSequence(
        [base, app_date.toordinal(), zlib.crc32(jar_code.encode("utf-8"))]
    )


class _Streams:
    """Năm dòng ngẫu nhiên độc lập của một hũ (xem docstring module)."""

    def __init__(self, ss: np.random.SeedSequence) -> None:
        # con của SeedSequence dựng KHÔNG đổi trạng thái `ss` (khác `ss.spawn`), nên gọi lại với cùng `ss` cho cùng dãy
        kids = [np.random.SeedSequence(ss.entropy, spawn_key=(*ss.spawn_key, i)) for i in range(5)]
        gens = [np.random.Generator(np.random.PCG64(k)) for k in kids]
        self.copula, self.indep, self.beta, self.level, self.oblig = gens


@dataclass(frozen=True)
class PathDraws:
    """Phần ngẫu nhiên của một hũ chưa nhân hệ số mức: chi tiêu cơ sở (N, H), nghĩa vụ theo khoảng (N, R) và xi (N,) của hệ số
    mức. Tách riêng để backtest dò nhiều `level_sigma` mà không phải sinh lại chi tiêu."""

    spend: np.ndarray
    xi: np.ndarray
    ranged_amounts: np.ndarray  # (N, R)


def draw_paths(spec: SimSpec, rho: float, n_paths: int, ss: np.random.SeedSequence) -> PathDraws:
    """Sinh chi tiêu cơ sở theo copula AR(1) với `rho` (hũ dày) hoặc hurdle trực tiếp (hũ thưa)."""
    h = len(spec.feats)
    st = _Streams(ss)
    if spec.sparse and isinstance(spec.marginal, HurdleMarginal):
        marg = spec.marginal
        u = st.indep.random((n_paths, h))
        p_cell = betaincinv(marg.a[None, :], marg.b[None, :], st.beta.random((n_paths, 4)))
        spend = marg.ppf(u, spec.feats, p=p_cell[:, spec.feats.cell])
    else:
        e = st.copula.standard_normal((n_paths, h))
        if rho > 0.0:
            s = np.sqrt(1.0 - rho * rho)
            x = e.copy()
            x[:, 0] = e[:, 0] / s
            z = lfilter([s], [1.0, -rho], x, axis=1)
        else:
            z = e
        spend = spec.marginal.ppf(ndtr(z), spec.feats)
    xi = st.level.standard_normal(n_paths)
    uo = st.oblig.random((n_paths, len(spec.ranged)))
    amounts = np.empty((n_paths, len(spec.ranged)))
    for k, (_idx, lo, hi) in enumerate(spec.ranged):
        amounts[:, k] = lo + (hi - lo) * uo[:, k]
    return PathDraws(spend=np.asarray(spend, dtype=float), xi=xi, ranged_amounts=amounts)


def balance_from_draws(spec: SimSpec, draws: PathDraws, level_sigma: float) -> np.ndarray:
    """Số dư cuối mỗi ngày (N, H): áp hệ số mức exp(sigma xi - sigma^2 / 2) lên chi tiêu rồi cộng lịch tất định."""
    spend = draws.spend
    if level_sigma > 0.0:
        spend = spend * np.exp(level_sigma * draws.xi - 0.5 * level_sigma * level_sigma)[:, None]
    flow = (spec.inflow - spec.outflow)[None, :] - spend
    for k, (idx, _lo, _hi) in enumerate(spec.ranged):
        flow[:, idx] -= draws.ranged_amounts[:, k]
    return spec.balance_vnd + np.cumsum(flow, axis=1)


def simulate_balance_paths(
    spec: SimSpec, cal: SeriesCalibration, n_paths: int, ss: np.random.SeedSequence
) -> np.ndarray:
    """Số dư cuối mỗi ngày của n_paths đường, hình (n_paths, H), float64."""
    return balance_from_draws(
        spec, draw_paths(spec, float(cal.rho), n_paths, ss), float(cal.level_sigma)
    )


def summarize_paths(bal: np.ndarray, spec: SimSpec, runout_threshold: float) -> SimSummary:
    n = bal.shape[0]
    q = np.rint(np.quantile(bal, [0.1, 0.5, 0.9], axis=0))
    q = np.maximum.accumulate(q, axis=0)
    if spec.balance_vnd < 0:
        p, se = 1.0, 0.0
    elif spec.window >= 1:
        p = float(np.mean(bal[:, : spec.window].min(axis=1) < 0.0))
        se = float(np.sqrt(max(p * (1.0 - p), 0.0) / n))
    else:
        p, se = 0.0, 0.0
    hit = np.nonzero(q[1] <= runout_threshold)[0]
    return SimSummary(
        balance_p10=q[0].astype(np.int64),
        balance_p50=q[1].astype(np.int64),
        balance_p90=q[2].astype(np.int64),
        p_shortfall=p,
        p_shortfall_se=se,
        runout_index=int(hit[0]) if len(hit) else None,
    )


def simulate_jar(
    spec: SimSpec,
    cal: SeriesCalibration,
    n_paths: int,
    ss: np.random.SeedSequence,
    runout_threshold: float = 0.0,
) -> SimSummary:
    return summarize_paths(simulate_balance_paths(spec, cal, n_paths, ss), spec, runout_threshold)
