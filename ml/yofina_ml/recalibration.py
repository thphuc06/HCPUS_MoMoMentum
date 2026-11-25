"""Hiệu chỉnh lại SAU Monte Carlo (#25), tham số fit offline trên backtest và lưu trong hiệu chỉnh (`calibration/default.py`).
Không fit gì lúc chạy: hàm ở đây chỉ áp bảng đã lưu (và hàm fit dùng trong backtest).

- `Isotonic`: ánh xạ đơn điệu không giảm của `p_shortfall` thô sang xác suất đã hiệu chỉnh, fit bằng PAV (pool adjacent
  violators; Kuleshov và cs. 2018, Dimitriadis, Gneiting, Jordan 2021). Lưu các nút (x, y); giữa hai nút nội suy tuyến tính,
  ngoài khoảng giữ giá trị đầu mút.
- `CQRBand`: CQR bất đối xứng (conformalized quantile regression; Romano, Patterson, Candès 2019, Định lý 2) cho dải số dư
  P10-P90: hai đuôi có độ lệch RIÊNG, mỗi đuôi hiệu chỉnh ở mức 1 - `tail`, nên dải lệch một phía (thật dưới P10 nhiều hơn
  trên P90) được sửa đúng phía. Điểm sai lệch chuẩn hóa theo chi tiêu TB ngày của hũ nhân số ngày tới mốc, để một bảng dùng
  chung cho mọi hũ dày bất kể mức chi. Chỉ dùng cho hũ dày: với hũ thưa chi TB nhỏ và nhiễu nên dải nở 2,4 đến 3,2 lần
  (kiểm toán ML §2.3).

Phương pháp và số đo: docs/research/backtest-final.md mục "Hiệu chỉnh CQR và PAV".
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Isotonic:
    x: tuple[float, ...]
    y: tuple[float, ...]

    def __call__(self, p: float) -> float:
        return float(np.clip(np.interp(float(p), self.x, self.y), 0.0, 1.0))

    def to_dict(self) -> dict[str, Any]:
        return {"x": list(self.x), "y": list(self.y)}

    @staticmethod
    def from_dict(o: dict[str, Any]) -> Isotonic:
        x = tuple(float(v) for v in o["x"])
        y = tuple(float(v) for v in o["y"])
        if not x or len(x) != len(y):
            raise ValueError("bảng isotonic cần x và y cùng độ dài, không rỗng")
        if any(b < a for a, b in itertools.pairwise(x)) or any(
            b < a for a, b in itertools.pairwise(y)
        ):
            raise ValueError("bảng isotonic phải không giảm")
        return Isotonic(x, y)


def fit_isotonic(
    p: Sequence[float], outcome: Sequence[float], weight: Sequence[float] | None = None
) -> Isotonic:
    """PAV: hồi quy đơn điệu không giảm của kết cục (0/1) theo xác suất dự báo. Điểm cùng x gộp trước; mỗi khối cuối cùng cho
    hai nút ở x nhỏ nhất và lớn nhất của khối, cùng giá trị khối (như `IsotonicRegression` của scikit-learn), nên tại điểm
    đã fit trả đúng giá trị PAV, giữa hai khối nội suy tuyến tính."""
    x = np.asarray(p, dtype=float)
    y = np.asarray(outcome, dtype=float)
    w = np.ones_like(x) if weight is None else np.asarray(weight, dtype=float)
    if x.size == 0:
        raise ValueError("cần ít nhất một điểm")
    ux, inv = np.unique(x, return_inverse=True)
    sw = np.bincount(inv, weights=w)
    sy = np.bincount(inv, weights=w * y)
    blocks: list[list[float]] = []  # [tổng w, tổng w*y, x nhỏ nhất, x lớn nhất]
    for xi, wi, yi in zip(ux, sw, sy, strict=True):
        blocks.append([wi, yi, xi, xi])
        while len(blocks) > 1 and blocks[-2][1] / blocks[-2][0] >= blocks[-1][1] / blocks[-1][0]:
            w2, y2, _lo, hi = blocks.pop()
            blocks[-1] = [blocks[-1][0] + w2, blocks[-1][1] + y2, blocks[-1][2], hi]
    xs: list[float] = []
    ys: list[float] = []
    for bw, by, lo, hi in blocks:
        v = round(by / bw, 6)
        for xv in dict.fromkeys((round(lo, 6), round(hi, 6))):
            xs.append(xv)
            ys.append(v)
    return Isotonic(tuple(xs), tuple(ys))


@dataclass(frozen=True)
class CQRBand:
    """Độ lệch CQR của dải số dư theo số ngày tới mốc `h` (tăng dần). Đơn vị của `lo`, `hi` là chi TB ngày của hũ (TB
    `scale_days` ngày lịch sử cuối) nhân h. `lo` dương hạ P10 xuống, `hi` dương nâng P90 lên; âm thì thu dải lại. Giữa hai
    nút nội suy tuyến tính theo h; trước nút đầu và sau nút cuối giữ hệ số của nút đầu mút (độ lệch vẫn tăng theo h).

    `min_history_days`: bảng dùng cho hũ có từ ngần này ngày lịch sử (CQR theo nhóm, kiểu Mondrian conformal: mỗi nhóm độ
    dài lịch sử một bảng, vì hũ ít lịch sử lệch đuôi dưới nhiều hơn). Chọn bảng bằng `select_cqr`."""

    h: tuple[int, ...]
    lo: tuple[float, ...]
    hi: tuple[float, ...]
    scale_days: int = 28
    min_history_days: int = 0

    def offsets(self, horizon: int) -> tuple[np.ndarray, np.ndarray]:
        """Hệ số (chưa nhân đơn vị) của ngày 1..horizon."""
        hs = np.arange(1, horizon + 1, dtype=float)
        return np.interp(hs, self.h, self.lo), np.interp(hs, self.h, self.hi)

    def to_dict(self) -> dict[str, Any]:
        return {
            "h": list(self.h),
            "lo": list(self.lo),
            "hi": list(self.hi),
            "scale_days": self.scale_days,
            "min_history_days": self.min_history_days,
        }

    @staticmethod
    def from_dict(o: dict[str, Any]) -> CQRBand:
        h = tuple(int(v) for v in o["h"])
        lo = tuple(float(v) for v in o["lo"])
        hi = tuple(float(v) for v in o["hi"])
        scale_days = int(o.get("scale_days", 28))
        min_days = int(o.get("min_history_days", 0))
        if not h or not len(h) == len(lo) == len(hi):
            raise ValueError("bảng CQR cần h, lo, hi cùng độ dài, không rỗng")
        if h[0] < 1 or any(b <= a for a, b in itertools.pairwise(h)) or scale_days < 1:
            raise ValueError("bảng CQR cần h tăng ngặt từ 1 và scale_days >= 1")
        if min_days < 0:
            raise ValueError("min_history_days của bảng CQR phải >= 0")
        return CQRBand(h, lo, hi, scale_days, min_days)


def parse_cqr(o: dict[str, Any] | list[dict[str, Any]]) -> tuple[CQRBand, ...]:
    """Các bảng CQR theo nhóm độ dài lịch sử, sắp theo `min_history_days`. Nhận một bảng (dict) hoặc danh sách bảng."""
    items = [o] if isinstance(o, dict) else list(o)
    bands = tuple(sorted((CQRBand.from_dict(x) for x in items), key=lambda b: b.min_history_days))
    if not bands:
        raise ValueError("cần ít nhất một bảng CQR")
    if len({b.min_history_days for b in bands}) != len(bands):
        raise ValueError("hai bảng CQR trùng min_history_days")
    return bands


def select_cqr(bands: Sequence[CQRBand] | None, history_days: int) -> CQRBand | None:
    """Bảng của nhóm có `min_history_days` lớn nhất mà không vượt `history_days`; không nhóm nào khớp thì None."""
    chosen = None
    for b in bands or ():
        if b.min_history_days <= history_days:
            chosen = b
    return chosen


def _conformal_quantile(scores: np.ndarray, tail: float) -> float:
    """Bậc thứ ceil((n + 1)(1 - tail)) của n điểm (lượng tử hiệu chỉnh mẫu hữu hạn của split conformal)."""
    n = len(scores)
    k = math.ceil((n + 1) * (1.0 - tail) - 1e-9)
    if k > n:
        raise ValueError(f"mỗi mốc cần ít nhất {k} điểm hiệu chỉnh với đuôi {tail}, có {n}")
    return float(np.sort(scores)[k - 1])


def fit_cqr(
    h: Sequence[int],
    lower: Sequence[float],
    upper: Sequence[float],
    truth: Sequence[float],
    scale: Sequence[float],
    tail: float = 0.1,
    scale_days: int = 28,
    min_history_days: int = 0,
) -> CQRBand:
    """Fit CQR bất đối xứng trên tập hiệu chỉnh: mỗi phần tử là một (hũ, origin, mốc h) với P10, P90 dự báo, số dư thật và
    chi TB ngày `scale` của hũ tại origin. Ở từng mốc h: điểm dưới (P10 - thật) / (scale x h), điểm trên
    (thật - P90) / (scale x h); độ lệch mỗi phía là lượng tử hiệu chỉnh của điểm phía đó ở mức 1 - `tail` (Romano và cs.
    2019, Định lý 2: mỗi đuôi tối đa `tail`, độ phủ ít nhất 1 - 2 `tail`). Phần tử có scale <= 0 bị bỏ. Fit theo nhóm độ dài
    lịch sử thì gọi một lần cho mỗi nhóm với các phần tử của nhóm đó và `min_history_days` của nhóm."""
    hh = np.asarray(h, dtype=int)
    lo = np.asarray(lower, dtype=float)
    up = np.asarray(upper, dtype=float)
    y = np.asarray(truth, dtype=float)
    unit = np.asarray(scale, dtype=float) * hh
    keep = unit > 0
    knots: list[int] = []
    off_lo: list[float] = []
    off_hi: list[float] = []
    for hv in np.unique(hh[keep]):
        m = keep & (hh == hv)
        knots.append(int(hv))
        off_lo.append(round(_conformal_quantile((lo[m] - y[m]) / unit[m], tail), 6))
        off_hi.append(round(_conformal_quantile((y[m] - up[m]) / unit[m], tail), 6))
    if not knots:
        raise ValueError("không có điểm hiệu chỉnh nào có chi TB dương")
    return CQRBand(tuple(knots), tuple(off_lo), tuple(off_hi), scale_days, min_history_days)


def apply_cqr(
    band: CQRBand,
    p10: Sequence[float],
    p50: Sequence[float],
    p90: Sequence[float],
    scale: float,
) -> tuple[np.ndarray, np.ndarray]:
    """P10, P90 số dư mới (VND nguyên) của ngày 1..H: P10 - lo x đơn vị, P90 + hi x đơn vị, đơn vị = scale x h. Kẹp để
    P10 <= P50 <= P90 vẫn đúng (P50, tức đường ngày cạn, không đổi)."""
    q10 = np.asarray(p10, dtype=float)
    q50 = np.asarray(p50, dtype=float)
    q90 = np.asarray(p90, dtype=float)
    off_lo, off_hi = band.offsets(len(q10))
    unit = max(float(scale), 0.0) * np.arange(1, len(q10) + 1, dtype=float)
    new10 = np.minimum(np.rint(q10 - off_lo * unit), q50)
    new90 = np.maximum(np.rint(q90 + off_hi * unit), q50)
    return new10.astype(np.int64), new90.astype(np.int64)
