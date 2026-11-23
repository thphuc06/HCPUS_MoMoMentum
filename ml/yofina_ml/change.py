"""Phát hiện đổi hành vi chi tiêu theo hũ (F5, luồng A phase 4): ba bộ phát hiện chạy trên chuỗi chi tiêu THEO TUẦN của một hũ.

Máy trạng thái đề xuất ở spike ML §7 (`docs/research/spike-ml-forecasting.md`):

1. **z bền MAD** (`flag_one_offs`, `winsorize_daily`): đánh dấu khoản lớn một lần. CHỈ đánh dấu và cắt khỏi chuỗi trước khi phát
   hiện; một khoản lớn đơn lẻ KHÔNG BAO GIỜ là đổi hành vi (nó chỉnh dự báo kỳ này, việc đó của mô hình dự báo).
2. **CUSUM hai phía tự viết** trên z theo tuần (`detect_suspect`): chạy trong đường sự kiện để "nghi" (rẻ, chỉ numpy). river không có
   CUSUM và PageHinkley của river không hơn (spike §7), nên tự viết 10 dòng.
3. **PELT** (`ruptures`, chi phí `l2`, chuỗi đã cắt khoản lớn; `detect_confirmed`): chạy trong batch đêm để "xác nhận" khi mức mới
   giữ đủ số tuần. `ruptures` chỉ được import khi chạy PELT (đường sự kiện không cần).

Thuần hàm: không I/O, không đồng hồ, không đọc cấu hình ngầm; tham số đi vào qua `ChangeParams` (mặc định đọc từ
`change_defaults.json` cạnh file này: mỗi số có ghi nguồn và lý do). Chuỗi vào là chi tiêu từng NGÀY (VND, cũ tới mới, không thủng
ngày, ngày cuối là hôm qua); tuần được cắt LÙI từ ngày cuối nên mọi tuần đều đủ 7 ngày và tuần mới nhất kết thúc hôm qua.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, fields
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

DEFAULTS_FILE = Path(__file__).with_name("change_defaults.json")
WEEK = 7
#: hệ số đổi MAD thành độ lệch chuẩn của phân phối chuẩn
MAD_SCALE = 1.4826

# lý do một hũ không được phân tích (khóa ổn định, ghi vào `detail` và log)
SKIP_INSUFFICIENT = "insufficient_history"
SKIP_SPARSE = "sparse"
SKIP_NO_SPEND = "no_spend"


@dataclass(frozen=True)
class ChangeParams:
    """Mọi hằng số của bộ phát hiện. Giá trị lấy từ `change_defaults.json` (xem `load_params`); đây không phải nơi đặt số."""

    version: str
    min_weeks_total: int
    pelt_min_size_weeks: int
    pelt_penalty_c: float
    pelt_penalty_n_ref: int
    sigma_floor_ratio: float
    min_relative_change: float
    min_abs_change_vnd: float
    hold_midpoint_fraction: float
    max_weeks_since_break: int
    min_active_day_share: float
    one_off_z: float
    one_off_max_share: float
    winsor_z: float
    cusum_k: float
    cusum_h: float
    cusum_monitor_weeks: int
    cusum_min_reference_weeks: int
    cusum_sigma_floor_ratio: float
    suspect_expire_weeks: int
    dedupe_days: int

    def to_dict(self) -> dict[str, Any]:
        """Tham số dạng JSON thuần để ghi vào `behavior_flags.detail` (truy vết bộ phát hiện đã dùng)."""
        return {f.name: getattr(self, f.name) for f in fields(self)}


def load_raw(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or DEFAULTS_FILE).read_text(encoding="utf-8"))


def load_params(path: Path | None = None, overrides: dict[str, Any] | None = None) -> ChangeParams:
    """Đọc `change_defaults.json`; `overrides` ghi đè từng khóa (dùng cho hiệu chỉnh và test). Khóa lạ hoặc thiếu thì báo lỗi."""
    raw = load_raw(path)
    values = {k: v["value"] for k, v in raw["params"].items()}
    values.update(overrides or {})
    names = {f.name for f in fields(ChangeParams)} - {"version"}
    unknown = set(values) - names
    missing = names - set(values)
    if unknown or missing:
        raise ValueError(f"tham số đổi hành vi: lạ {sorted(unknown)}, thiếu {sorted(missing)}")
    return ChangeParams(version=str(raw["version"]), **values)


def calibration_for(detector: str, path: Path | None = None) -> dict[str, Any]:
    """Số đo đã hiệu chỉnh của một bộ phát hiện (`confirm_pelt` hoặc `suspect_cusum`) để ghi vào `detail` của dấu hiệu: tỷ lệ báo
    nhầm và độ trễ phát hiện. Chưa hiệu chỉnh thì rỗng. Đo trên dữ liệu TỔNG HỢP (xem `change_defaults.json`)."""
    cal = load_raw(path).get("calibration", {})
    block = cal.get(detector)
    if not block:
        return {}
    out = {
        "detector": detector,
        "synthetic_only": True,
        "seeds": len(cal.get("seeds", ())),
        "tolerance_days": cal.get("tolerance_days"),
    }
    for key in (
        "fa_per_jar_year",
        "fa_series_share",
        "recall_8w",
        "recall_big_shift",
        "delay_days_median",
        "delay_days_p90",
    ):
        if key in block:
            out[key] = block[key]
    return out


# --- 1. z bền MAD: khoản lớn một lần ------------------------------------------------------------
def _median_and_scale(values: np.ndarray) -> tuple[float, float]:
    """Trung vị và thang bền (1,4826 * MAD) của các NGÀY CÓ CHI; (0, 0) khi không có ngày nào."""
    pos = values[values > 0]
    if pos.size == 0:
        return 0.0, 0.0
    med = float(np.median(pos))
    scale = MAD_SCALE * float(np.median(np.abs(pos - med)))
    return med, scale


def robust_z(daily: Sequence[float]) -> np.ndarray:
    """z bền của từng ngày: (số tiền - trung vị các ngày có chi) / (1,4826 * MAD). Ngày không chi có z = 0. Thang bằng 0 (mọi khoản
    bằng nhau) thì mọi z là 0: không có gì để gọi là bất thường."""
    x = np.asarray(daily, dtype=float)
    med, scale = _median_and_scale(x)
    out = np.zeros_like(x)
    if scale > 0:
        out = np.where(x > 0, (x - med) / scale, 0.0)
    return out


def _isolated(x: np.ndarray, z_cut: float, params: ChangeParams) -> np.ndarray:
    """Chỉ số các ngày vượt `z_cut` mà vẫn là KHOẢN LẺ: nếu hơn `one_off_max_share` số ngày có chi vượt ngưỡng thì đó là một MỨC mới
    (thói quen đổi: mọi khoản đều to hơn), không phải khoản lớn một lần, nên trả rỗng (không đánh dấu, không cắt)."""
    z = robust_z(x)
    idx = np.nonzero(z > z_cut)[0]
    n_pos = int(np.count_nonzero(x > 0))
    if n_pos == 0 or len(idx) / n_pos > params.one_off_max_share:
        return np.zeros(0, dtype=int)
    return idx


def flag_one_offs(daily: Sequence[float], params: ChangeParams) -> list[int]:
    """Chỉ số các ngày bị đánh dấu là khoản lớn một lần (z bền > `one_off_z`, và chỉ khi là khoản lẻ). Chỉ ĐÁNH DẤU: không phải đổi
    hành vi."""
    x = np.asarray(daily, dtype=float)
    return [int(i) for i in _isolated(x, params.one_off_z, params)]


def winsorize_daily(daily: Sequence[float], params: ChangeParams) -> np.ndarray:
    """Chuỗi ngày đã cắt khoản lớn: mỗi khoản lẻ không vượt trung vị + `winsor_z` * 1,4826 * MAD của hũ. Khi quá nhiều ngày vượt
    mức đó (một mức chi mới) thì không cắt gì, để PELT còn thấy mức mới."""
    x = np.asarray(daily, dtype=float)
    med, scale = _median_and_scale(x)
    out = x.copy()
    if scale <= 0:
        return out
    idx = _isolated(x, params.winsor_z, params)
    out[idx] = med + params.winsor_z * scale
    return out


# --- chuỗi tuần -----------------------------------------------------------------------------------
def weekly_totals(daily: Sequence[float]) -> np.ndarray:
    """Tổng theo tuần, CŨ TỚI MỚI, tuần cắt lùi từ ngày cuối: bỏ phần đầu lẻ để mọi tuần đủ 7 ngày."""
    x = np.asarray(daily, dtype=float)
    n = len(x) // WEEK
    if n == 0:
        return np.zeros(0)
    return x[len(x) - n * WEEK :].reshape(n, WEEK).sum(axis=1)


@dataclass(frozen=True)
class WeeklySeries:
    """Chuỗi tuần của một hũ sau chuẩn bị.

    `raw` và `clean` cùng độ dài (đã bỏ các tuần đầu chưa có chi), cũ tới mới; `clean` là chuỗi đã cắt khoản lớn. `n_days_used` là số
    ngày cuối của chuỗi ngày mà các tuần này phủ (tuần mới nhất kết thúc ngày cuối). `one_off_days` là chỉ số (trong chuỗi ngày
    gốc) các khoản lớn một lần. `skipped` khác None thì hũ không được phân tích (lý do là một trong `SKIP_*`)."""

    raw: np.ndarray
    clean: np.ndarray
    n_days_used: int
    one_off_days: tuple[int, ...]
    skipped: str | None = None

    @property
    def n_weeks(self) -> int:
        return len(self.clean)


def active_day_share(daily: Sequence[float]) -> float:
    """Tỷ lệ ngày có chi, tính từ ngày có chi đầu tiên (các ngày trước đó hũ chưa hoạt động)."""
    x = np.asarray(daily, dtype=float)
    first = np.nonzero(x > 0)[0]
    if first.size == 0:
        return 0.0
    return float(np.mean(x[first[0] :] > 0))


def prepare_weekly(daily: Sequence[float], params: ChangeParams) -> WeeklySeries:
    """Chuỗi ngày -> chuỗi tuần đã cắt khoản lớn, kèm kiểm đủ điều kiện (đủ tuần, không quá thưa)."""
    x = np.asarray(daily, dtype=float)
    one_offs = tuple(flag_one_offs(x, params))
    raw = weekly_totals(x)
    clean = weekly_totals(winsorize_daily(x, params))
    # bỏ các tuần đầu toàn số 0 (hũ chưa có chi hoặc người dùng chưa có dữ liệu): chúng không phải "mức cũ"
    lead = 0
    while lead < len(raw) and raw[lead] == 0:
        lead += 1
    raw, clean = raw[lead:], clean[lead:]
    used = len(raw) * WEEK
    skipped: str | None = None
    if len(raw) == 0:
        skipped = SKIP_NO_SPEND
    elif len(raw) < params.min_weeks_total:
        skipped = SKIP_INSUFFICIENT
    elif active_day_share(x) < params.min_active_day_share:
        skipped = SKIP_SPARSE
    return WeeklySeries(raw, clean, used, one_offs, skipped)


def week_start_date(last_day: date, n_weeks: int, week_index: int) -> date:
    """Ngày đầu tiên của tuần `week_index` (0 là tuần cũ nhất trong `n_weeks` tuần) khi tuần mới nhất kết thúc `last_day`."""
    return last_day - timedelta(days=WEEK * (n_weeks - week_index) - 1)


# --- 2. CUSUM: nghi ---------------------------------------------------------------------------------
def cusum(z: Sequence[float], k: float) -> tuple[np.ndarray, np.ndarray]:
    """CUSUM hai phía trên z (đã chuẩn hóa theo sigma): trả (S+, S-) từng bước. S+ = max(0, S+ + z - k), S- = max(0, S- - z - k)."""
    sp = sn = 0.0
    up, dn = [], []
    for v in z:
        sp = max(0.0, sp + float(v) - k)
        sn = max(0.0, sn - float(v) - k)
        up.append(sp)
        dn.append(sn)
    return np.asarray(up), np.asarray(dn)


@dataclass(frozen=True)
class Suspicion:
    """CUSUM đang báo: mức tuần của hũ lệch khỏi mức nền."""

    direction: str  # up | down
    start_index: int  # tuần đầu của đợt lệch (chỉ số trong chuỗi tuần, 0 là cũ nhất)
    old_weekly_vnd: int
    new_weekly_vnd: int
    statistic: float  # giá trị CUSUM lúc kết thúc
    weeks_in_alarm: int
    sigma_vnd: float

    def to_detail(self) -> dict[str, Any]:
        return {
            "detector": "cusum",
            "statistic": round(self.statistic, 3),
            "sigma_vnd": round(self.sigma_vnd),
            "weeks_in_alarm": self.weeks_in_alarm,
        }


def _level_ok(old: float, new: float, params: ChangeParams) -> bool:
    """Mức mới đủ lệch so với mức cũ (tương đối VÀ tuyệt đối)?"""
    delta = abs(new - old)
    if delta < params.min_abs_change_vnd:
        return False
    return delta >= params.min_relative_change * max(old, 1.0)


def detect_suspect(series: WeeklySeries, params: ChangeParams) -> Suspicion | None:
    """CUSUM trên z theo tuần: mức nền là trung vị và MAD của các tuần TRƯỚC `cusum_monitor_weeks` tuần cuối.

    Nghi khi lúc kết thúc CUSUM vượt `cusum_h` VÀ mức mới (trung bình các tuần từ lúc bắt đầu lệch) đủ lệch so với mức nền. Hũ không
    đủ điều kiện (`series.skipped`) thì không nghi. Không phát hiện được điểm gãy sớm hơn `min_weeks_total` tuần."""
    if series.skipped is not None:
        return None
    w = series.clean
    n = len(w)
    monitor = min(params.cusum_monitor_weeks, n - params.cusum_min_reference_weeks)
    if monitor < 1:
        return None
    ref, mon = w[: n - monitor], w[n - monitor :]
    mu = float(np.median(ref))
    sigma = max(
        MAD_SCALE * float(np.median(np.abs(ref - mu))), params.cusum_sigma_floor_ratio * mu, 1.0
    )
    z = (mon - mu) / sigma
    s_up, s_dn = cusum(z, params.cusum_k)
    for direction, s in (("up", s_up), ("down", s_dn)):
        if s[-1] <= params.cusum_h:
            continue
        zero = np.nonzero(s == 0)[0]
        begin = int(zero[-1]) + 1 if zero.size else 0  # tuần đầu của đợt lệch trong đoạn theo dõi
        new = float(np.mean(mon[begin:]))
        if (new > mu) != (direction == "up") or not _level_ok(mu, new, params):
            continue
        return Suspicion(
            direction=direction,
            start_index=n - monitor + begin,
            old_weekly_vnd=round(mu),
            new_weekly_vnd=round(new),
            statistic=float(s[-1]),
            weeks_in_alarm=monitor - begin,
            sigma_vnd=sigma,
        )
    return None


# --- 3. PELT: xác nhận ------------------------------------------------------------------------------
def noise_sigma(weekly: Sequence[float], params: ChangeParams, *, tail: int = 0) -> float:
    """Độ lệch chuẩn bền của nhiễu theo tuần: 1,4826 * MAD của sai phân bậc một / căn 2 (một bước nhảy chỉ làm hỏng MỘT sai phân
    nên MAD không bị kéo). Có sàn `sigma_floor_ratio` * trung vị để ước lượng từ ít sai phân không thấp giả tạo (và chuỗi gần hằng
    không cho penalty bằng 0). Trung vị của sàn bỏ `tail` tuần cuối (mức TRƯỚC điểm gãy có thể có: một mức mới cao không được làm
    sàn nhiễu phình ra và che chính bước nhảy đó)."""
    w = np.asarray(weekly, dtype=float)
    base = w[: len(w) - tail] if 0 < tail < len(w) else w
    floor = params.sigma_floor_ratio * float(np.median(base)) if len(base) else 0.0
    if len(w) < 3:
        return max(floor, 1.0)
    d = np.diff(w)
    s = MAD_SCALE * float(np.median(np.abs(d - np.median(d)))) / math.sqrt(2.0)
    return max(s, floor, 1.0)


def pelt_penalty(weekly: Sequence[float], params: ChangeParams) -> float:
    """penalty = c * sigma^2 * ln(n_ref) (spike ML §7; n_ref cố định, xem `pelt_penalty_n_ref`)."""
    sigma = noise_sigma(weekly, params, tail=params.pelt_min_size_weeks)
    return params.pelt_penalty_c * sigma**2 * math.log(max(params.pelt_penalty_n_ref, 2))


def pelt_breakpoints(weekly: Sequence[float], params: ChangeParams) -> list[int]:
    """Các điểm gãy của PELT (chi phí `l2`, `jump=1`): mỗi số là chỉ số tuần ĐẦU của một đoạn mới (không gồm điểm cuối chuỗi)."""
    import ruptures as rpt  # nhập muộn: đường sự kiện (CUSUM) không cần ruptures

    w = np.asarray(weekly, dtype=float)
    if len(w) < 2 * params.pelt_min_size_weeks:
        return []
    algo = rpt.Pelt(model="l2", min_size=params.pelt_min_size_weeks, jump=1).fit(w.reshape(-1, 1))
    return [int(b) for b in algo.predict(pen=pelt_penalty(w, params))[:-1]]


@dataclass(frozen=True)
class Confirmed:
    """PELT xác nhận một điểm gãy gần đây, mức mới đã giữ đủ số tuần."""

    direction: str  # up | down
    change_index: int  # tuần đầu của mức mới (chỉ số trong chuỗi tuần, 0 là cũ nhất)
    old_weekly_vnd: int
    new_weekly_vnd: int
    weeks_held: int
    penalty: float
    sigma_vnd: float
    n_breakpoints: int

    def to_detail(self) -> dict[str, Any]:
        return {
            "detector": "pelt",
            "cost": "l2",
            "penalty": round(self.penalty, 1),
            "sigma_vnd": round(self.sigma_vnd),
            "n_breakpoints": self.n_breakpoints,
        }


def detect_confirmed(
    series: WeeklySeries, params: ChangeParams, *, breaks: Sequence[int] | None = None
) -> Confirmed | None:
    """PELT trên chuỗi tuần đã cắt khoản lớn; xác nhận điểm gãy GẦN NHẤT khi:

    - mức mới giữ >= `pelt_min_size_weeks` tuần và <= `max_weeks_since_break` tuần (cũ hơn là tin cũ);
    - mức mới lệch đủ so với mức cũ (`min_relative_change` và `min_abs_change_vnd`);
    - MỖI tuần của đoạn mới nằm phía mức mới của điểm giữa (`hold_midpoint_fraction`): một tuần vọt cao đi kèm một tuần bình thường
      không phải mức mới giữ (chặn khoản lớn một lần lọt qua bước cắt).

    `breaks` (tùy chọn) là kết quả `pelt_breakpoints` đã tính sẵn (hiệu chỉnh quét nhiều tham số chặn mà dùng chung một lần PELT).
    """
    if series.skipped is not None:
        return None
    w = series.clean
    n = len(w)
    breaks = list(breaks) if breaks is not None else pelt_breakpoints(w, params)
    if not breaks:
        return None
    b = breaks[-1]
    held = n - b
    if held < params.pelt_min_size_weeks or held > params.max_weeks_since_break:
        return None
    bounds = [0, *breaks, n]
    old_seg = w[bounds[-3] : bounds[-2]]
    new_seg = w[b:]
    old, new = float(np.mean(old_seg)), float(np.mean(new_seg))
    if new == old or not _level_ok(old, new, params):
        return None
    mid = old + params.hold_midpoint_fraction * (new - old)
    held_ok = bool(np.all(new_seg > mid)) if new > old else bool(np.all(new_seg < mid))
    if not held_ok:
        return None
    return Confirmed(
        direction="up" if new > old else "down",
        change_index=b,
        old_weekly_vnd=round(old),
        new_weekly_vnd=round(new),
        weeks_held=held,
        penalty=pelt_penalty(w, params),
        sigma_vnd=noise_sigma(w, params, tail=params.pelt_min_size_weeks),
        n_breakpoints=len(breaks),
    )
