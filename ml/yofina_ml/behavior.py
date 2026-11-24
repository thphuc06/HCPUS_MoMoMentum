"""Hồ sơ hành vi chi tiêu (F7, phase 5 luồng B): đặc trưng, phân cụm đơn giản, nhận xét kèm bằng chứng số. Hàm THUẦN: không DB,
không model ngôn ngữ, không đồng hồ hệ thống (người gọi truyền `today` là ngày mô phỏng của `yofina_core.clock.app_today`).

Đầu vào là các dòng CHI của sổ cái (`SpendFact`, không có tên đối tác hay lời nhắn nên không mang PII) trong cửa sổ `window_days`
ngày trước `today`. Chỉ tính ngày đã trọn (trước hôm nay). Khoản trả nghĩa vụ theo lịch (dòng gắn `obligation_id`) không phải thói quen
nên bị bỏ; dòng Trả sau (`funding = credit`) và dòng nạp ngoài ví (`external`) vẫn là chi tiêu.

Đặc trưng (khớp `BehaviorFeatures` của contracts/blocks/behavior_insight.schema.json):
- nhịp lương: phần chi trong `first_week_days` ngày đầu mỗi kỳ lương, so với phần số ngày của các tuần đầu đó trong cửa sổ;
- ngày trong tuần: phần chi vào thứ Bảy, Chủ nhật so với phần số ngày cuối tuần; thứ có mức chi trung bình mỗi ngày cao nhất;
- giờ: phần chi trong ví (không tính dòng ngoài ví vì không có giờ thật) vào buổi tối `[evening_start_hour, evening_end_hour]`;
- Trả sau: số lần, tổng tiền và phần chi bằng hạn mức Trả sau.

Phân cụm đơn giản (hai mức, tất định):
- ngày: k-means một chiều, hai cụm, trên tổng chi mỗi ngày có chi (khởi tạo bằng min và max) -> nhóm "ngày chi đậm";
- người dùng: gán vào tâm cụm gần nhất trong bốn nhóm cố định (`SEGMENTS`) trên ba trục đã chuẩn hóa (độ dồn sau lương, độ dồn cuối
  tuần, phần Trả sau). Một người dùng mỗi lần nên không fit k-means giữa người dùng; tâm cụm cố định là cách gán ổn định và giải thích
  được.

Mỗi nhận xét có câu mẫu do mã dựng (`headline`, `detail`) chỉ dùng số trong `evidence`, và `ground_text` kiểm điều đó (cùng hợp đồng với
`NumericGrounding` của agent: số trong câu phải có trong bằng chứng). Model nhỏ viết lại câu ở phía pipeline; câu của model cũng phải qua
`ground_text`.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Any

from yofina_ml.daycal import latest_payday, payday_in_month


def next_payday(payday_day: int, today: date) -> date:
    """Ngày lương sớm nhất SAU `today` (cùng quy tắc với `yofina_core.clock.next_payday`; ML không phụ thuộc yofina_core)."""
    this_month = payday_in_month(payday_day, today.year, today.month)
    if this_month > today:
        return this_month
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return payday_in_month(payday_day, year, month)


def format_vnd(value: int) -> str:
    """`1.200.000 ₫` (cùng định dạng với `yofina_core.money.format_vnd`)."""
    n = int(value)
    return ("-" if n < 0 else "") + f"{abs(n):,}".replace(",", ".") + " ₫"

#: Phiên bản bộ tính (cột `behavior_profiles.config_version`). Đổi công thức hay ngưỡng thì tăng.
CONFIG_VERSION = "behavior-2026-11-v1"

WEEKDAY_NAMES = {
    1: "thứ Hai",
    2: "thứ Ba",
    3: "thứ Tư",
    4: "thứ Năm",
    5: "thứ Sáu",
    6: "thứ Bảy",
    7: "Chủ nhật",
}
_UNIT_SUFFIX = {"percent": "%", "days": " ngày", "count": " lần", "hour": " giờ"}


@dataclass(frozen=True)
class BehaviorConfig:
    """Ngưỡng và cửa sổ của bộ tính. Giá trị do dự án chọn trên dữ liệu mô phỏng (chưa hiệu chỉnh trên người dùng thật)."""

    window_days: int = 90
    #: dưới số ngày lịch sử này thì hồ sơ chưa sẵn sàng (`ready` sai, `min_history_days` của hợp đồng)
    min_history_days: int = 21
    #: cần ít nhất từng này dòng chi để nhận xét
    min_spend_count: int = 10
    first_week_days: int = 7
    #: nhận xét "dồn" khi phần chi lớn hơn phần số ngày ít nhất từng này lần và từng này điểm tỷ lệ
    min_lift: float = 1.25
    min_share_gap: float = 0.05
    evening_start_hour: int = 18
    evening_end_hour: int = 23
    evening_min_share: float = 0.45
    evening_min_count: int = 5
    bnpl_min_count: int = 1
    #: ngày chi đậm: cụm cao ít nhất từng này ngày, tâm cụm cao gấp từng này lần tâm cụm thấp, và không quá từng này phần số ngày có chi
    heavy_min_days: int = 3
    heavy_min_ratio: float = 2.5
    heavy_max_share_of_days: float = 0.4
    kmeans_iterations: int = 25
    #: nhóm tin cậy theo số ngày lịch sử
    high_confidence_days: int = 60
    medium_confidence_days: int = 28
    max_insights: int = 6


DEFAULT_CONFIG = BehaviorConfig()


@dataclass(frozen=True)
class SpendFact:
    """Một dòng chi của sổ cái (giá trị dương). `local_hour` là giờ theo múi giờ ứng dụng; None với dòng không có giờ thật."""

    app_date: date
    amount_vnd: int
    jar_code: str | None = None
    funding: str = "jar"  # jar | credit | external
    local_hour: int | None = None
    is_obligation: bool = False


@dataclass(frozen=True)
class Evidence:
    key: str
    label: str
    value: int | float
    unit: str
    period_from: date | None = None
    period_to: date | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"key": self.key, "label": self.label, "value": self.value, "unit": self.unit}
        if self.period_from is not None:
            d["period_from"] = self.period_from.isoformat()
        if self.period_to is not None:
            d["period_to"] = self.period_to.isoformat()
        return d

    @property
    def display(self) -> str:
        """Chuỗi hiển thị chuẩn của con số (model được dặn chép nguyên văn chuỗi này)."""
        return display_value(self.value, self.unit)


@dataclass(frozen=True)
class InsightDraft:
    insight_id: str
    kind: str
    headline: str
    evidence: tuple[Evidence, ...]
    confidence: str
    strength: float
    detail: str | None = None
    jar_code: str | None = None
    ai_generated: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "insight_id": self.insight_id,
            "kind": self.kind,
            "headline": self.headline,
            "evidence": [e.to_dict() for e in self.evidence],
            "confidence": self.confidence,
            "ai_generated": self.ai_generated,
        }
        if self.detail:
            d["detail"] = self.detail
        if self.jar_code:
            d["jar_code"] = self.jar_code
        return d


@dataclass(frozen=True)
class ProfileDraft:
    """Kết quả của `compute_profile`, cùng hình dạng (qua `to_data`) với `BehaviorProfileData` trừ `computed_at` (người gọi thêm)."""

    ready: bool
    app_date: date
    history_days: int
    headline: str
    features: dict[str, Any]
    insights: tuple[InsightDraft, ...] = ()
    segment: dict[str, str] | None = None
    next_step: dict[str, Any] | None = None
    min_history_days: int | None = None
    config_version: str = CONFIG_VERSION
    #: số liệu nội bộ để truy vết (không vào hợp đồng)
    notes: dict[str, Any] = field(default_factory=dict)

    def with_insights(self, insights: Sequence[InsightDraft], headline: str | None = None) -> ProfileDraft:
        return replace(self, insights=tuple(insights), headline=headline or self.headline)

    def to_data(self, computed_at: str | None) -> dict[str, Any]:
        d: dict[str, Any] = {
            "ready": self.ready,
            "app_date": self.app_date.isoformat(),
            "config_version": self.config_version,
            "headline": self.headline,
            "history_days": self.history_days,
            "features": dict(self.features),
            "insights": [i.to_dict() for i in self.insights],
        }
        if computed_at is not None:
            d["computed_at"] = computed_at
        if self.min_history_days is not None:
            d["min_history_days"] = self.min_history_days
        if self.segment is not None:
            d["segment"] = dict(self.segment)
        if self.next_step is not None:
            d["next_step"] = dict(self.next_step)
        return d


# --- hiển thị và kiểm căn cứ của số ---------------------------------------------------------------
def _num_text(value: float) -> str:
    if float(value) == int(value):
        return str(int(value))
    return f"{value:g}".replace(".", ",")


def display_value(value: float, unit: str) -> str:
    if unit == "vnd":
        return format_vnd(int(value))
    if unit == "weekday":
        return WEEKDAY_NAMES[int(value)]
    if unit == "ratio":
        return f"{round(float(value) * 100)}%"
    return _num_text(value) + _UNIT_SUFFIX.get(unit, "")


def _dm(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}"


_DATE_RE = re.compile(r"(?<![\d.,])(\d{1,2})/(\d{1,2})(?:/(\d{4}))?(?![\d/])")
_NUM_RE = re.compile(r"\d[\d.,]*\d|\d")


def _allowed_tokens(evidence: Iterable[Evidence]) -> tuple[set[str], set[tuple[int, int]]]:
    tokens: set[str] = set()
    dates: set[tuple[int, int]] = set()
    for e in evidence:
        v = e.value
        if e.unit == "vnd":
            n = int(v)
            tokens |= {str(n), f"{n:,}".replace(",", ".")}
        elif e.unit == "ratio":
            tokens |= {str(round(float(v) * 100)), _num_text(v)}
        elif e.unit == "weekday":
            tokens.add(str(int(v)))
            if int(v) <= 6:  # "thứ 7" là thứ Bảy (ISO 6): số thứ tiếng Việt = ISO + 1
                tokens.add(str(int(v) + 1))
        else:
            tokens |= {_num_text(v), str(v)}
        for d in (e.period_from, e.period_to):
            if d is not None:
                dates.add((d.day, d.month))
    return tokens, dates


def ground_text(text: str, evidence: Iterable[Evidence]) -> list[str]:
    """Các con số trong `text` KHÔNG có trong `evidence` (rỗng là đạt). Số tiền theo dạng `1.200.000` hoặc `1200000`, phần trăm,
    số ngày, số lần, giờ, thứ (kể cả "thứ 7" của tiếng Việt), ngày `dd/mm` của cửa sổ bằng chứng. Không có dạng làm tròn ("1,2
    triệu"): câu phải chép đúng chuỗi hiển thị của bằng chứng."""
    tokens, dates = _allowed_tokens(evidence)
    bad: list[str] = []

    def take_date(m: re.Match[str]) -> str:
        day, month = int(m.group(1)), int(m.group(2))
        if (day, month) not in dates:
            bad.append(m.group(0))
        return " "

    rest = _DATE_RE.sub(take_date, text)
    for raw in _NUM_RE.findall(rest):
        tok = raw.rstrip(".,")
        if tok not in tokens:
            bad.append(tok)
    return bad


def insight_grounded(i: InsightDraft) -> bool:
    return not ground_text(i.headline, i.evidence) and not (i.detail and ground_text(i.detail, i.evidence))


# --- tính đặc trưng -------------------------------------------------------------------------------
def _ratio(part: float, whole: float) -> float:
    return part / whole if whole > 0 else 0.0


def _pct(x: float) -> int:
    return round(x * 100)


def _confidence(history_days: int, cfg: BehaviorConfig) -> str:
    if history_days >= cfg.high_confidence_days:
        return "high"
    if history_days >= cfg.medium_confidence_days:
        return "medium"
    return "low"


def kmeans_1d(values: Sequence[float], iterations: int = 25) -> tuple[float, float, list[int]]:
    """k-means hai cụm trên một chiều, khởi tạo bằng min và max (tất định). Trả (tâm thấp, tâm cao, nhãn 0/1 theo thứ tự `values`)."""
    if not values:
        return 0.0, 0.0, []
    lo, hi = float(min(values)), float(max(values))
    labels = [0] * len(values)
    for _ in range(iterations):
        labels = [1 if abs(v - hi) < abs(v - lo) else 0 for v in values]
        low = [v for v, lab in zip(values, labels, strict=True) if lab == 0]
        high = [v for v, lab in zip(values, labels, strict=True) if lab == 1]
        new_lo = sum(low) / len(low) if low else lo
        new_hi = sum(high) / len(high) if high else hi
        if math.isclose(new_lo, lo) and math.isclose(new_hi, hi):
            break
        lo, hi = new_lo, new_hi
    return lo, hi, labels


#: Bốn nhóm hành vi: (mã, nhãn, tâm cụm trên ba trục: độ dồn sau lương, độ dồn cuối tuần, phần Trả sau đã chuẩn hóa)
SEGMENTS: tuple[tuple[str, str, tuple[float, float, float]], ...] = (
    ("chi_deu_tay", "Chi đều tay", (0.0, 0.0, 0.0)),
    ("chi_don_sau_luong", "Chi dồn sau kỳ lương", (0.6, 0.0, 0.0)),
    ("chi_manh_cuoi_tuan", "Chi mạnh cuối tuần", (0.0, 0.6, 0.0)),
    ("hay_dung_tra_sau", "Hay dùng Trả sau", (0.0, 0.0, 0.6)),
)


def assign_segment(payday_lift: float, weekend_lift: float, bnpl_share: float) -> dict[str, str]:
    """Nhóm gần nhất (khoảng cách Euclid) trên ba trục đã cắt về [0, 1,5]."""

    def clip(x: float) -> float:
        return max(0.0, min(1.5, x))

    point = (clip(payday_lift - 1), clip(weekend_lift - 1), clip(bnpl_share * 4))
    seg_id, label, _ = min(SEGMENTS, key=lambda s: math.dist(point, s[2]))
    return {"segment_id": seg_id, "label": label}


def _top_jar(amounts: Mapping[str | None, int], names: Mapping[str, str]) -> str | None:
    named = {k: v for k, v in amounts.items() if k and k in names and v > 0}
    return max(named, key=lambda k: (named[k], k)) if named else None


def compute_profile(
    facts: Iterable[SpendFact],
    *,
    today: date,
    payday_day: int,
    jar_names: Mapping[str, str],
    config: BehaviorConfig = DEFAULT_CONFIG,
) -> ProfileDraft:
    """Hồ sơ hành vi ở ngày mô phỏng `today`. `jar_names`: mã hũ người dùng -> tên hiển thị (không gồm hũ hệ thống)."""
    cfg = config
    window_start = today - timedelta(days=cfg.window_days)
    rows = [f for f in facts if not f.is_obligation and f.amount_vnd > 0 and window_start <= f.app_date < today]
    first = min((f.app_date for f in rows), default=today)
    history_days = (today - first).days
    days = [first + timedelta(days=i) for i in range(history_days)]
    total = sum(f.amount_vnd for f in rows)
    features: dict[str, Any] = {"history_days": history_days}

    def not_ready(headline: str) -> ProfileDraft:
        return ProfileDraft(
            ready=False,
            app_date=today,
            history_days=history_days,
            headline=headline,
            features=features,
            min_history_days=cfg.min_history_days,
        )

    if history_days < cfg.min_history_days:
        need = cfg.min_history_days - history_days
        return not_ready(f"Cần thêm khoảng {need} ngày giao dịch để mình nhận ra thói quen chi tiêu của bạn.")
    if len(rows) < cfg.min_spend_count or total <= 0:
        return not_ready("Chưa đủ giao dịch chi để nhận ra thói quen chi tiêu của bạn.")

    conf = _confidence(history_days, cfg)
    period = (first, today - timedelta(days=1))
    features["avg_daily_spend_vnd"] = round(total / history_days)

    # --- nhịp lương ---
    def cycle_day(d: date) -> int:
        return (d - latest_payday(payday_day, d)).days

    fw_days = [d for d in days if cycle_day(d) < cfg.first_week_days]
    fw_spend: dict[str | None, int] = {}
    for f in rows:
        if cycle_day(f.app_date) < cfg.first_week_days:
            fw_spend[f.jar_code] = fw_spend.get(f.jar_code, 0) + f.amount_vnd
    fw_total = sum(fw_spend.values())
    fw_share = _ratio(fw_total, total)
    fw_exposure = _ratio(len(fw_days), history_days)
    payday_lift = _ratio(fw_share, fw_exposure)
    features["first_week_after_payday_share"] = round(fw_share, 3)

    # --- ngày trong tuần ---
    wk_days = [d for d in days if d.isoweekday() >= 6]
    wk_spend: dict[str | None, int] = {}
    by_weekday: dict[int, int] = {}
    for f in rows:
        wd = f.app_date.isoweekday()
        by_weekday[wd] = by_weekday.get(wd, 0) + f.amount_vnd
        if wd >= 6:
            wk_spend[f.jar_code] = wk_spend.get(f.jar_code, 0) + f.amount_vnd
    wk_total = sum(wk_spend.values())
    wk_share = _ratio(wk_total, total)
    wk_exposure = _ratio(len(wk_days), history_days)
    weekend_lift = _ratio(wk_share, wk_exposure)
    day_count = {wd: sum(1 for d in days if d.isoweekday() == wd) for wd in range(1, 8)}
    avg_by_weekday = {wd: by_weekday.get(wd, 0) / n for wd, n in day_count.items() if n > 0}
    top_weekday = max(avg_by_weekday, key=lambda wd: (avg_by_weekday[wd], -wd))
    features["weekend_share"] = round(wk_share, 3)
    features["top_weekday"] = top_weekday

    # --- giờ trong ngày (chỉ giao dịch trong ví có giờ) ---
    timed = [f for f in rows if f.local_hour is not None and f.funding != "external"]
    evening = [f for f in timed if cfg.evening_start_hour <= int(f.local_hour or 0) <= cfg.evening_end_hour]
    timed_total = sum(f.amount_vnd for f in timed)
    evening_share = _ratio(sum(f.amount_vnd for f in evening), timed_total)
    if timed:
        features["evening_share"] = round(evening_share, 3)

    # --- Trả sau ---
    bnpl = [f for f in rows if f.funding == "credit"]
    bnpl_total = sum(f.amount_vnd for f in bnpl)
    bnpl_share = _ratio(bnpl_total, total)
    features["bnpl_purchases_per_month"] = min(round(len(bnpl) * 30 / history_days, 2), 1000.0)
    features["bnpl_share"] = round(bnpl_share, 3)

    # --- phân cụm ngày ---
    daily: dict[date, int] = {}
    for f in rows:
        daily[f.app_date] = daily.get(f.app_date, 0) + f.amount_vnd
    spend_days = sorted(daily)
    lo, hi, labels = kmeans_1d([float(daily[d]) for d in spend_days], cfg.kmeans_iterations)
    heavy = [d for d, lab in zip(spend_days, labels, strict=True) if lab == 1]

    insights: list[InsightDraft] = []
    if (
        len(fw_days) >= cfg.first_week_days
        and payday_lift >= cfg.min_lift
        and fw_share - fw_exposure >= cfg.min_share_gap
    ):
        last_pay = latest_payday(payday_day, today - timedelta(days=1))
        if last_pay < first:
            last_pay = first
        last_to = min(last_pay + timedelta(days=cfg.first_week_days - 1), today - timedelta(days=1))
        last_spend = sum(f.amount_vnd for f in rows if last_pay <= f.app_date <= last_to)
        ev = (
            Evidence("first_week_share", "Phần chi trong tuần đầu sau ngày lương", _pct(fw_share), "percent", *period),
            Evidence("first_week_days", "Số ngày tính là tuần đầu", cfg.first_week_days, "days"),
            Evidence("first_week_day_share", "Phần số ngày thuộc tuần đầu sau lương", _pct(fw_exposure), "percent", *period),
            Evidence("last_first_week_vnd", f"Chi tuần đầu kỳ lương {_dm(last_pay)}", last_spend, "vnd", last_pay, last_to),
        )
        n = cfg.first_week_days
        insights.append(
            InsightDraft(
                insight_id="chi_don_sau_luong",
                kind="payday_cycle",
                headline=(
                    f"{n} ngày đầu sau ngày lương bạn chi {_pct(fw_share)}% tổng chi, "
                    f"dù chỉ chiếm {_pct(fw_exposure)}% số ngày."
                ),
                detail=f"Tuần đầu kỳ lương {_dm(last_pay)} bạn đã chi {format_vnd(last_spend)}.",
                evidence=ev,
                confidence=conf,
                strength=payday_lift - 1,
                jar_code=_top_jar(fw_spend, jar_names),
            )
        )
    if wk_days and weekend_lift >= cfg.min_lift and wk_share - wk_exposure >= cfg.min_share_gap:
        # ngày cuối tuần chi nhiều hơn (thứ Bảy hoặc Chủ nhật), không phải thứ cao nhất cả tuần: câu nói về cuối tuần
        top_wk = max((6, 7), key=lambda wd: (avg_by_weekday.get(wd, 0.0), -wd))
        avg_top = round(avg_by_weekday.get(top_wk, 0.0))
        day_name = WEEKDAY_NAMES[top_wk]
        ev = (
            Evidence("weekend_share", "Phần chi vào thứ Bảy, Chủ nhật", _pct(wk_share), "percent", *period),
            Evidence("weekend_day_share", "Phần số ngày là cuối tuần", _pct(wk_exposure), "percent", *period),
            Evidence("top_weekend_day", "Ngày cuối tuần chi nhiều hơn", top_wk, "weekday"),
            Evidence("avg_top_weekend_vnd", f"Chi trung bình mỗi {day_name}", avg_top, "vnd", *period),
        )
        insights.append(
            InsightDraft(
                insight_id="chi_manh_cuoi_tuan",
                kind="weekday_pattern",
                headline=(
                    f"Cuối tuần bạn chi {_pct(wk_share)}% tổng chi, dù cuối tuần chỉ chiếm {_pct(wk_exposure)}% số ngày."
                ),
                detail=f"Riêng {day_name}, bạn chi trung bình {format_vnd(avg_top)} mỗi ngày.",
                evidence=ev,
                confidence=conf,
                strength=weekend_lift - 1,
                jar_code=_top_jar(wk_spend, jar_names),
            )
        )
    if len(bnpl) >= cfg.bnpl_min_count:
        ev = (
            Evidence("window_days", "Số ngày đã xét", history_days, "days", *period),
            Evidence("bnpl_count", "Số lần dùng Trả sau", len(bnpl), "count", *period),
            Evidence("bnpl_total_vnd", "Tổng mua bằng Trả sau", bnpl_total, "vnd", *period),
            Evidence("bnpl_share", "Phần chi bằng Trả sau", _pct(bnpl_share), "percent", *period),
        )
        by_jar: dict[str | None, int] = {}
        for f in bnpl:
            by_jar[f.jar_code] = by_jar.get(f.jar_code, 0) + f.amount_vnd
        insights.append(
            InsightDraft(
                insight_id="dung_tra_sau",
                kind="bnpl_usage",
                headline=(
                    f"{history_days} ngày qua bạn dùng Trả sau {len(bnpl)} lần, tổng {format_vnd(bnpl_total)}, "
                    f"chiếm {_pct(bnpl_share)}% chi tiêu."
                ),
                evidence=ev,
                confidence="high",  # đếm thẳng từ sổ cái, không ước lượng
                strength=bnpl_share * 4 + 0.1 * len(bnpl),
                jar_code=_top_jar(by_jar, jar_names),
            )
        )
    if len(evening) >= cfg.evening_min_count and evening_share >= cfg.evening_min_share:
        ev = (
            Evidence("evening_share", "Phần chi trong ví vào buổi tối", _pct(evening_share), "percent", *period),
            Evidence("evening_start_hour", "Giờ bắt đầu buổi tối", cfg.evening_start_hour, "hour"),
            Evidence("evening_end_hour", "Giờ kết thúc buổi tối", cfg.evening_end_hour, "hour"),
            Evidence("evening_count", "Số lần chi buổi tối", len(evening), "count", *period),
        )
        insights.append(
            InsightDraft(
                insight_id="chi_buoi_toi",
                kind="time_of_day",
                headline=(
                    f"Bạn chi {_pct(evening_share)}% số tiền trong ví vào buổi tối, "
                    f"từ {cfg.evening_start_hour} giờ đến {cfg.evening_end_hour} giờ."
                ),
                evidence=ev,
                confidence=conf,
                strength=evening_share - 0.3,
            )
        )
    if (
        len(heavy) >= cfg.heavy_min_days
        and lo > 0
        and hi >= cfg.heavy_min_ratio * lo
        and len(heavy) <= cfg.heavy_max_share_of_days * len(spend_days)
    ):
        ev = (
            Evidence("heavy_days", "Số ngày chi đậm", len(heavy), "count", *period),
            Evidence("heavy_avg_vnd", "Chi trung bình một ngày chi đậm", round(hi), "vnd", *period),
            Evidence("light_avg_vnd", "Chi trung bình một ngày thường", round(lo), "vnd", *period),
        )
        insights.append(
            InsightDraft(
                insight_id="ngay_chi_dam",
                kind="spending_cluster",
                headline=(
                    f"Có {len(heavy)} ngày bạn chi đậm, trung bình {format_vnd(round(hi))} mỗi ngày; "
                    f"ngày thường trung bình {format_vnd(round(lo))}."
                ),
                evidence=ev,
                confidence=conf,
                strength=0.2,
            )
        )
    insights.sort(key=lambda i: -i.strength)
    insights = insights[: cfg.max_insights]
    segment = assign_segment(payday_lift, weekend_lift, bnpl_share)
    notes = {
        "payday_lift": round(payday_lift, 3),
        "weekend_lift": round(weekend_lift, 3),
        "heavy_center_vnd": round(hi),
        "light_center_vnd": round(lo),
        "spend_rows": len(rows),
    }
    if not insights:
        draft = not_ready(f"Chưa thấy thói quen chi tiêu nào nổi bật trong {history_days} ngày qua.")
        return replace(draft, segment=segment, notes=notes)
    return ProfileDraft(
        ready=True,
        app_date=today,
        history_days=history_days,
        headline=insights[0].headline,
        features=features,
        insights=tuple(insights),
        segment=segment,
        next_step=next_step_for(insights[0], today=today, payday_day=payday_day, jar_names=jar_names),
        notes=notes,
    )


# --- MỘT việc cần làm ------------------------------------------------------------------------------
def _next_weekday(today: date, iso_weekday: int) -> date:
    """Ngày gần nhất SAU hôm nay có thứ `iso_weekday`."""
    delta = (iso_weekday - today.isoweekday()) % 7 or 7
    return today + timedelta(days=delta)


def next_step_for(
    top: InsightDraft, *, today: date, payday_day: int, jar_names: Mapping[str, str]
) -> dict[str, Any]:
    """Việc cần làm theo nhận xét quan trọng nhất. Không có số trong câu (khỏi phải kiểm căn cứ); nếu có hành động thì là
    `schedule_nudge` (người dùng bấm thì đi luồng xác nhận, không tự ghi gì) với ngày SAU hôm nay."""
    jar = top.jar_code if top.jar_code in jar_names else None
    jar_name = jar_names.get(jar or "", "")
    if top.kind == "payday_cycle":
        fire = next_payday(payday_day, today)
        label = f"Đặt lời nhắc giữ nhịp chi hũ {jar_name} sau kỳ lương" if jar else "Đặt lời nhắc giữ nhịp chi sau kỳ lương"
        params: dict[str, Any] = {"op": "create", "kind": "runout_warning", "fire_on": fire.isoformat()}
        if jar:
            params["jar_code"] = jar
        params["note"] = "Giữ nhịp chi trong tuần đầu kỳ lương"
        return {
            "label": label[:80],
            "reason": "Chi dồn vào tuần đầu dễ làm hũ hụt trước kỳ lương sau.",
            "action": {"tool": "schedule_nudge", "params": params},
        }
    if top.kind == "weekday_pattern":
        wd = int(next(e.value for e in top.evidence if e.unit == "weekday"))
        fire = _next_weekday(today, wd - 1 if wd > 1 else 7)  # ngày liền trước ngày chi nhiều, sau hôm nay
        params = {"op": "create", "kind": "runout_warning", "fire_on": fire.isoformat()}
        if jar:
            params["jar_code"] = jar
        params["note"] = f"Xem lại hũ trước {WEEKDAY_NAMES[wd]}"
        return {
            "label": f"Nhắc mình xem lại hũ trước {WEEKDAY_NAMES[wd]}"[:80],
            "reason": "Đặt hạn mức cho ngày chi nhiều nhất giúp hũ không hụt giữa kỳ.",
            "action": {"tool": "schedule_nudge", "params": params},
        }
    if top.kind == "bnpl_usage":
        return {
            "label": "Xem lại các khoản Trả sau trước ngày đến hạn",
            "reason": "Trả sau không trừ hũ ngay nhưng sẽ phải trả bằng tiền của hũ khi đến hạn.",
        }
    if top.kind == "time_of_day":
        return {
            "label": "Đặt giới hạn cho các khoản chi buổi tối",
            "reason": "Phần lớn tiền trong ví được chi vào buổi tối.",
        }
    return {
        "label": "Xem lại những ngày chi đậm",
        "reason": "Vài ngày chi đậm chiếm phần lớn chi tiêu của cả kỳ.",
    }


__all__ = [
    "CONFIG_VERSION",
    "DEFAULT_CONFIG",
    "SEGMENTS",
    "WEEKDAY_NAMES",
    "BehaviorConfig",
    "Evidence",
    "InsightDraft",
    "ProfileDraft",
    "SpendFact",
    "assign_segment",
    "compute_profile",
    "display_value",
    "ground_text",
    "insight_grounded",
    "kmeans_1d",
    "next_step_for",
]
