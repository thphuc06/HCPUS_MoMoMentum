"""Hiệu chỉnh lại SAU Monte Carlo (#25), tham số fit offline trên backtest và lưu trong hiệu chỉnh (`calibration/default.py`).
Không fit gì lúc chạy: hàm ở đây chỉ áp bảng đã lưu (và hàm fit dùng trong backtest).

- `Isotonic`: ánh xạ đơn điệu không giảm của `p_shortfall` thô sang xác suất đã hiệu chỉnh, fit bằng PAV (pool adjacent
  violators; Kuleshov và cs. 2018, Dimitriadis, Gneiting, Jordan 2021). Lưu các nút (x, y); giữa hai nút nội suy tuyến tính,
  ngoài khoảng giữ giá trị đầu mút.

Phương pháp và số đo: docs/research/backtest-final.md mục "Hiệu chỉnh CQR và PAV".
"""

from __future__ import annotations

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
        if any(b < a for a, b in zip(x, x[1:], strict=False)) or any(b < a for a, b in zip(y, y[1:], strict=False)):
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
