"""Điểm chống chịu (phase 4, F4): công thức bốn thành phần Save, Spend, Borrow, Plan. HÀM THUẦN: không I/O, không đồng hồ.

Mọi con số của công thức (trọng số, mốc nội suy, mẫu câu giải thích) đọc từ `cfg`, là `ResilienceConfig` của `yofina_core.resilience`
(file `resilience_defaults.json`; người gọi nạp và truyền vào); nhóm điểm do hàm `band_for` của người gọi quyết định (người gọi truyền
`yofina_core.resilience.band_for_score`, nên chỉ có MỘT hàm đổi điểm thành nhóm). Gói ML chỉ phụ thuộc numpy và scipy nên module này
không import `yofina_core`: `cfg` chỉ cần có các thuộc tính mà `ResilienceConfig` có (xem các hàm `_save`, `_spend`, ...).

Công thức (mọi mốc nội suy tuyến tính giữa hai mốc của cấu hình, kẹp trong 0..100):

- **Save**: `runway_days = số dư khả dụng / chi tiêu mỗi ngày khi KHÔNG có thu nhập`; điểm tăng tuyến tính từ `zero_score_days` tới
  `full_score_days`. Chi tiêu mỗi ngày = (chi tiêu thay đổi trong kỳ + nghĩa vụ đến hạn trong kỳ) / số ngày của kỳ.
- **Spend**: `tỷ lệ chi trên thu` (cả chi thay đổi, nghĩa vụ và khoản chi một lần) chấm từ `full_score_spend_ratio` (100 điểm) xuống
  `zero_score_spend_ratio` (0 điểm); trộn với `100 x tỷ lệ trả đúng hạn` theo `on_time_share_weight`.
- **Borrow**: `nghĩa vụ trong kỳ / thu nhập` chấm từ `full_score_obligation_ratio` (100 điểm) xuống `zero_score_obligation_ratio` (0).
- **Plan**: `tiến độ = tổng đóng góp hằng tháng (không quá mức cần) / tổng mức cần hằng tháng` của các mục tiêu chưa đạt; chấm từ
  `zero_score_progress_ratio` tới `full_score_progress_ratio`. Chưa có mục tiêu thì Plan KHÔNG áp dụng: bị bỏ khỏi điểm và trọng số
  của các thành phần còn lại chuẩn hóa để cộng bằng 1 (quyết định 11 của phase 4).

Điểm tổng bằng trung bình có trọng số của các điểm thành phần ĐÃ LÀM TRÒN (nên khớp bất biến của `ResilienceScoreData`).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

#: thứ tự cố định của bốn thành phần (khớp `yofina_core.blocks.RESILIENCE_ORDER`; test kiểm)
RESILIENCE_ORDER: tuple[str, ...] = ("save", "spend", "borrow", "plan")
#: số chữ số thập phân của trọng số đã chuẩn hóa (hợp đồng chấp nhận lệch 0,005 khi cộng lại)
WEIGHT_DIGITS = 4
#: nhãn nhóm điểm bằng chữ (nhóm luôn hiện bằng chữ, không chỉ màu)
BAND_WORD = {"weak": "yếu", "fair": "vừa", "strong": "tốt"}


@dataclass(frozen=True)
class GoalFact:
    """Một mục tiêu (hũ có `goal_vnd`) quy về mức cần mỗi tháng và đóng góp mỗi tháng hiện có."""

    jar_code: str
    monthly_needed_vnd: int
    monthly_contribution_vnd: int


@dataclass(frozen=True)
class ResilienceInputs:
    """Dữ kiện của MỘT lần chấm điểm, tính trên một kỳ `window_days` ngày (kỳ ngắn hơn một tháng cũng được: mọi số tiền của kỳ).

    - `liquid_balance_vnd`: số dư khả dụng (mọi hũ người dùng, không gồm hũ hệ thống).
    - `income_vnd`: thu nhập của kỳ (lương đã khai quy về kỳ); 0 nghĩa là không có thu nhập (cú sốc mất việc).
    - `variable_spend_vnd`: chi tiêu thay đổi của kỳ (trung bình lịch sử, không gồm nghĩa vụ).
    - `obligations_vnd`: nghĩa vụ đến hạn trong kỳ; `obligations_by_kind` tách theo loại (để cú sốc tăng giá tác động đúng loại).
    - `one_off_spend_vnd`: khoản chi một lần của kỳ (cú sốc chi phí y tế): vào tỷ lệ chi trên thu, KHÔNG vào mức chi mỗi ngày.
    - `on_time_share`: tỷ lệ khoản đến hạn được trả đúng hạn, 0..1 (không có khoản nào bị quá hạn thì 1).
    """

    liquid_balance_vnd: int
    income_vnd: int
    variable_spend_vnd: int
    obligations_vnd: int
    window_days: int
    on_time_share: float
    goals: tuple[GoalFact, ...] = ()
    obligations_by_kind: Mapping[str, int] = field(default_factory=dict)
    one_off_spend_vnd: int = 0

    @property
    def daily_burn_vnd(self) -> float:
        """Chi tiêu mỗi ngày khi không có thu nhập."""
        return (self.variable_spend_vnd + self.obligations_vnd) / self.window_days


@dataclass(frozen=True)
class ComponentResult:
    key: str
    label: str
    score: int | None
    weight: float
    applicable: bool
    band: str | None
    explanation: str
    #: (key, nhãn, giá trị, đơn vị) đúng thứ tự hiển thị
    inputs: tuple[tuple[str, str, float, str], ...]


@dataclass(frozen=True)
class ResilienceResult:
    score: int
    band: str
    headline: str
    components: tuple[ComponentResult, ...]
    weakest: str
    #: dữ kiện đã dùng (ảnh chụp, đi vào cột `inputs` của bảng `resilience_scores`)
    inputs: Mapping[str, float | int]

    def component(self, key: str) -> ComponentResult:
        return next(c for c in self.components if c.key == key)

    def scores(self) -> dict[str, int | None]:
        return {c.key: c.score for c in self.components}


def interpolate(value: float, zero_at: float, full_at: float) -> float:
    """Điểm 0..100: `zero_at` ứng với 0, `full_at` ứng với 100, giữa hai mốc tuyến tính, ngoài hai mốc thì kẹp. Hai mốc có thể
    xuôi hay ngược (mốc 100 nhỏ hơn mốc 0 với tỷ lệ càng thấp càng tốt). `inf` được kẹp như số rất lớn."""
    if full_at == zero_at:
        raise ValueError("hai mốc nội suy phải khác nhau")
    t = (value - zero_at) / (full_at - zero_at)
    return 100.0 * min(max(t, 0.0), 1.0)


def monthly_needed_vnd(
    *, remaining_vnd: int, days_left: int, month_days: int, floor_days: int = 1
) -> int:
    """Mức cần đóng góp mỗi tháng để đủ `remaining_vnd` trước hạn: `remaining x month_days / days_left` làm tròn lên. Quá hạn hoặc
    sát hạn (`days_left` dưới `floor_days`) thì coi còn `floor_days` ngày (cần gần như toàn bộ ngay)."""
    if remaining_vnd <= 0:
        return 0
    return math.ceil(remaining_vnd * month_days / max(days_left, floor_days))


def _pct(x: float) -> int:
    return round(100.0 * x)


def _save(i: ResilienceInputs, cfg: Any) -> tuple[int, str, tuple, dict]:
    t = cfg.components.save.thresholds
    zero, full = t["zero_score_days"].value, t["full_score_days"].value
    burn = i.daily_burn_vnd
    runway = math.inf if burn <= 0 else max(i.liquid_balance_vnd, 0) / burn
    score = round(interpolate(runway, zero, full))
    shown = int(full) if math.isinf(runway) else math.floor(runway)
    text = cfg.components.save.explanation_template.format(
        runway_days=shown, full_score_days=int(full)
    )
    inputs = (
        ("liquid_balance_vnd", "Số dư khả dụng", int(i.liquid_balance_vnd), "vnd"),
        ("daily_spend_vnd", "Chi tiêu mỗi ngày", round(burn), "vnd"),
        ("runway_days", "Số ngày sống được", shown, "days"),
    )
    return score, text, inputs, {"runway_days": shown, "daily_burn_vnd": round(burn)}


def _ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return math.inf if numerator > 0 else 0.0
    return numerator / denominator


def _spend(i: ResilienceInputs, cfg: Any) -> tuple[int, str, tuple, dict]:
    t = cfg.components.spend.thresholds
    ratio = _ratio(i.variable_spend_vnd + i.obligations_vnd + i.one_off_spend_vnd, i.income_vnd)
    spend_score = interpolate(
        ratio, t["zero_score_spend_ratio"].value, t["full_score_spend_ratio"].value
    )
    w = t["on_time_share_weight"].value
    score = round((1.0 - w) * spend_score + w * 100.0 * i.on_time_share)
    shown_ratio = _pct(ratio) if math.isfinite(ratio) else None
    text = cfg.components.spend.explanation_template.format(
        spend_ratio_percent="hơn 100" if shown_ratio is None else shown_ratio,
        on_time_percent=_pct(i.on_time_share),
    )
    inputs = (
        ("spend_ratio", "Chi trên thu", round(min(ratio, 99.0), 4), "ratio"),
        ("on_time_ratio", "Trả đúng hạn", round(i.on_time_share, 4), "ratio"),
    )
    return score, text, inputs, {"spend_ratio": ratio}


def _borrow(i: ResilienceInputs, cfg: Any) -> tuple[int, str, tuple, dict]:
    t = cfg.components.borrow.thresholds
    ratio = _ratio(i.obligations_vnd, i.income_vnd)
    score = round(
        interpolate(
            ratio,
            t["zero_score_obligation_ratio"].value,
            t["full_score_obligation_ratio"].value,
        )
    )
    text = cfg.components.borrow.explanation_template.format(
        obligation_ratio_percent="hơn 100" if not math.isfinite(ratio) else _pct(ratio),
        full_score_percent=_pct(t["full_score_obligation_ratio"].value),
    )
    inputs = (
        ("obligation_monthly_vnd", "Nghĩa vụ hằng tháng", int(i.obligations_vnd), "vnd"),
        ("obligation_ratio", "Nghĩa vụ trên thu nhập", round(min(ratio, 99.0), 4), "ratio"),
    )
    return score, text, inputs, {"obligation_ratio": ratio}


def goal_progress(goals: tuple[GoalFact, ...]) -> float | None:
    """Tiến độ gộp của các mục tiêu: tổng đóng góp (mỗi mục tiêu không quá mức cần) trên tổng mức cần. None khi không có mục tiêu
    nào cần đóng góp (chưa có mục tiêu, hoặc mọi mục tiêu đã đủ tiền)."""
    needed = sum(g.monthly_needed_vnd for g in goals)
    if not goals:
        return None
    if needed <= 0:
        return None
    covered = sum(min(g.monthly_contribution_vnd, g.monthly_needed_vnd) for g in goals)
    return covered / needed


def _plan(i: ResilienceInputs, cfg: Any) -> tuple[int | None, str, tuple, dict]:
    progress = goal_progress(i.goals)
    if progress is None:
        return (
            None,
            "Chưa có mục tiêu nào cần đóng góp, nên phần Kế hoạch chưa tính vào điểm.",
            (),
            {},
        )
    t = cfg.components.plan.thresholds
    score = round(
        interpolate(
            progress, t["zero_score_progress_ratio"].value, t["full_score_progress_ratio"].value
        )
    )
    text = cfg.components.plan.explanation_template.format(progress_percent=_pct(progress))
    inputs = (("goal_progress_ratio", "Tiến độ mục tiêu", round(progress, 4), "ratio"),)
    return score, text, inputs, {"goal_progress_ratio": progress}


def compute_score(
    i: ResilienceInputs, cfg: Any, band_for: Callable[[int], str]
) -> ResilienceResult:
    """Chấm điểm. `cfg` quyết định mọi trọng số, mốc và câu chữ giải thích; `band_for` đổi điểm (tổng và từng thành phần) thành nhóm."""
    if i.window_days < 1:
        raise ValueError("window_days phải dương")
    raw = {
        "save": _save(i, cfg),
        "spend": _spend(i, cfg),
        "borrow": _borrow(i, cfg),
        "plan": _plan(i, cfg),
    }
    base = {k: getattr(cfg.weights, k).value for k in RESILIENCE_ORDER}
    live = [k for k in RESILIENCE_ORDER if raw[k][0] is not None]
    if not live:
        raise ValueError("cần ít nhất một thành phần áp dụng")
    total = sum(base[k] for k in live)
    if total <= 0:
        raise ValueError("tổng trọng số của các thành phần áp dụng phải dương")
    weights = {
        k: round(base[k] / total, WEIGHT_DIGITS) if k in live else 0.0 for k in RESILIENCE_ORDER
    }
    # làm bù phần dư làm tròn vào thành phần có trọng số lớn nhất để tổng đúng bằng 1
    drift = round(1.0 - sum(weights.values()), WEIGHT_DIGITS)
    if drift:
        top = max(live, key=lambda k: weights[k])
        weights[top] = round(weights[top] + drift, WEIGHT_DIGITS)

    comps: list[ComponentResult] = []
    for k in RESILIENCE_ORDER:
        score, text, inputs, _extra = raw[k]
        comps.append(
            ComponentResult(
                key=k,
                label=cfg.label_of(k),
                score=score,
                weight=weights[k],
                applicable=score is not None,
                band=band_for(score) if score is not None else None,
                explanation=text,
                inputs=inputs,
            )
        )
    score = round(sum(weights[k] * (raw[k][0] or 0) for k in live))
    score = min(max(score, 0), 100)
    weakest = min(live, key=lambda k: (raw[k][0] or 0, RESILIENCE_ORDER.index(k)))
    band = band_for(score)
    headline = _headline(score, band, comps, weakest, raw)
    snapshot: dict[str, float | int] = {
        "window_days": i.window_days,
        "liquid_balance_vnd": int(i.liquid_balance_vnd),
        "income_vnd": int(i.income_vnd),
        "variable_spend_vnd": int(i.variable_spend_vnd),
        "obligations_vnd": int(i.obligations_vnd),
        "one_off_spend_vnd": int(i.one_off_spend_vnd),
        "on_time_share": round(i.on_time_share, 4),
        "goal_count": len(i.goals),
    }
    return ResilienceResult(
        score=score,
        band=band,
        headline=headline,
        components=tuple(comps),
        weakest=weakest,
        inputs=snapshot,
    )


def _headline(score: int, band: str, comps: list[ComponentResult], weakest: str, raw) -> str:
    c = next(x for x in comps if x.key == weakest)
    extra = raw[weakest][3]
    if weakest == "save" and "runway_days" in extra:
        tail = f"chỉ đủ sống {extra['runway_days']} ngày"
    elif weakest == "spend" and math.isfinite(extra.get("spend_ratio", math.inf)):
        tail = f"chi bằng {_pct(extra['spend_ratio'])}% thu nhập"
    elif weakest == "borrow" and math.isfinite(extra.get("obligation_ratio", math.inf)):
        tail = f"nghĩa vụ bằng {_pct(extra['obligation_ratio'])}% thu nhập"
    elif weakest == "plan" and "goal_progress_ratio" in extra:
        tail = f"mục tiêu đạt {_pct(extra['goal_progress_ratio'])}% tiến độ"
    else:
        tail = "cần chú ý nhất"
    return f"Điểm chống chịu {score}/100 ({BAND_WORD[band]}). Yếu nhất: {c.label}, {tail}."


__all__ = [
    "BAND_WORD",
    "ComponentResult",
    "GoalFact",
    "ResilienceInputs",
    "ResilienceResult",
    "compute_score",
    "goal_progress",
    "interpolate",
    "monthly_needed_vnd",
]
