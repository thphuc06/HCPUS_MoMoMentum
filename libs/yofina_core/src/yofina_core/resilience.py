"""Hợp đồng của Điểm chống chịu và cú sốc (phase 4, F4): kiểu dùng chung, cấu hình trọng số và ngưỡng, định nghĩa cú sốc.

- Kiểu dùng chung một nguồn cho bảng `resilience_scores`, tool `forecast___get_resilience_score` và `forecast___stress_test`,
  REST `GET /resilience` và `POST /resilience/stress`, và khối `resilience_score`, `stress_result`: `ResilienceScore` và
  `StressResult` là chính `ResilienceScoreData` và `StressResultData` của `yofina_core.blocks` (đặt tên đúng như file phase).
- `ResilienceConfig`: định dạng `resilience_defaults.json` (trọng số, ngưỡng nhóm điểm, ngưỡng từng thành phần, tham số stress).
  Mọi số có đơn vị, ghi chú và nguồn; engine (luồng A) đọc từ đây, không đặt số trong mã.
- `ShockSet`: định dạng `shocks.json`, ba cú sốc mẫu (mất việc 2 tháng, tiền trọ tăng, ốm một tuần) dạng dữ liệu.

Chỉ có KIỂU, nạp file và kiểm hình dạng; **không có công thức tính điểm hay mô phỏng** (luồng A cài ở `ml/yofina_ml/`).
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yofina_core.blocks import (
    RESILIENCE_ORDER,
    ResilienceScoreData,
    ShockSummary,
    SlugKey,
    StressResultData,
    Vnd,
)

#: Tên theo file phase: cùng một kiểu với `data` của khối (một nguồn cho bảng, tool, REST, khối).
ResilienceScore = ResilienceScoreData
StressResult = StressResultData

DEFAULTS_FILE = "resilience_defaults.json"
SHOCKS_FILE = "shocks.json"

ConfigUnit = Literal["ratio", "days", "vnd", "score", "count"]
ComponentKey = Literal["save", "spend", "borrow", "plan"]
ObligationKind = Literal["bnpl", "loan", "rent", "bill", "subscription"]

#: Tên ngưỡng bắt buộc của từng thành phần (khóa của `components.<key>.thresholds`).
REQUIRED_THRESHOLDS: dict[str, tuple[str, ...]] = {
    "save": ("zero_score_days", "full_score_days"),
    "spend": ("full_score_spend_ratio", "zero_score_spend_ratio", "on_time_share_weight"),
    "borrow": ("full_score_obligation_ratio", "zero_score_obligation_ratio"),
    "plan": ("full_score_progress_ratio", "zero_score_progress_ratio"),
}
#: Chỗ `{tên}` hợp lệ trong `explanation_template` của từng thành phần (engine điền).
EXPLANATION_PLACEHOLDERS: dict[str, tuple[str, ...]] = {
    "save": ("runway_days", "full_score_days"),
    "spend": ("spend_ratio_percent", "on_time_percent"),
    "borrow": ("obligation_ratio_percent", "full_score_percent"),
    "plan": ("progress_percent",),
}
STRESS_KEYS = ("horizon_days", "n_paths", "short_shortfall_ratio")
BAND_KEYS = ("weak_max_score", "fair_max_score")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ConfigValue(_Model):
    """Một giá trị cấu hình có đơn vị, ghi chú và nguồn."""

    value: float
    unit: ConfigUnit
    note: Annotated[str, Field(min_length=1, max_length=400)]
    source: Annotated[str, Field(min_length=1, max_length=300)]


class ComponentConfig(_Model):
    label: Annotated[str, Field(min_length=1, max_length=40)]
    explanation_template: Annotated[str, Field(min_length=1, max_length=200)]
    thresholds: dict[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")], ConfigValue]


class ComponentWeights(_Model):
    save: ConfigValue
    spend: ConfigValue
    borrow: ConfigValue
    plan: ConfigValue


class BandConfig(_Model):
    weak_max_score: ConfigValue
    fair_max_score: ConfigValue


class ComponentsConfig(_Model):
    save: ComponentConfig
    spend: ComponentConfig
    borrow: ComponentConfig
    plan: ComponentConfig


class StressConfig(_Model):
    horizon_days: ConfigValue
    n_paths: ConfigValue
    short_shortfall_ratio: ConfigValue


class ResilienceConfig(_Model):
    version: Annotated[str, Field(min_length=1, max_length=40)]
    note: Annotated[str, Field(min_length=1, max_length=600)]
    disclaimer: Annotated[str, Field(min_length=1, max_length=160)]
    weights: ComponentWeights
    bands: BandConfig
    components: ComponentsConfig
    stress: StressConfig

    @model_validator(mode="after")
    def _invariants(self) -> ResilienceConfig:
        """Trọng số là tỷ lệ cộng bằng 1; ngưỡng nhóm tăng dần trong 0..100; mọi thành phần đủ ngưỡng bắt buộc; mẫu câu chỉ dùng
        chỗ điền hợp lệ; các mốc 'đủ điểm' và 'không điểm' không trùng nhau."""
        weights = {k: getattr(self.weights, k) for k in RESILIENCE_ORDER}
        if any(w.unit != "ratio" or not 0 <= w.value <= 1 for w in weights.values()):
            raise ValueError("trọng số phải là tỷ lệ trong 0..1")
        if abs(sum(w.value for w in weights.values()) - 1) > 1e-9:
            raise ValueError("trọng số của bốn thành phần phải cộng bằng 1")
        weak, fair = self.bands.weak_max_score.value, self.bands.fair_max_score.value
        if not 0 <= weak < fair < 100:
            raise ValueError("ngưỡng nhóm điểm phải tăng dần trong khoảng 0..100")
        for key in RESILIENCE_ORDER:
            comp: ComponentConfig = getattr(self.components, key)
            missing = set(REQUIRED_THRESHOLDS[key]) - set(comp.thresholds)
            if missing:
                raise ValueError(f"thành phần {key} thiếu ngưỡng {sorted(missing)}")
            names = set(re.findall(r"\{([a-z_]+)\}", comp.explanation_template))
            if not names <= set(EXPLANATION_PLACEHOLDERS[key]):
                raise ValueError(
                    f"mẫu câu của {key} dùng chỗ điền lạ: {sorted(names - set(EXPLANATION_PLACEHOLDERS[key]))}"
                )
        t = self.components.save.thresholds
        if not t["zero_score_days"].value < t["full_score_days"].value:
            raise ValueError("save: mốc 0 điểm phải nhỏ hơn mốc 100 điểm")
        t = self.components.borrow.thresholds
        if not t["full_score_obligation_ratio"].value < t["zero_score_obligation_ratio"].value:
            raise ValueError("borrow: mốc 100 điểm phải nhỏ hơn mốc 0 điểm")
        t = self.components.spend.thresholds
        if not t["full_score_spend_ratio"].value < t["zero_score_spend_ratio"].value:
            raise ValueError("spend: mốc 100 điểm phải nhỏ hơn mốc 0 điểm")
        if not 0 <= t["on_time_share_weight"].value <= 1:
            raise ValueError("spend: on_time_share_weight phải trong 0..1")
        t = self.components.plan.thresholds
        if not t["zero_score_progress_ratio"].value < t["full_score_progress_ratio"].value:
            raise ValueError("plan: mốc 0 điểm phải nhỏ hơn mốc 100 điểm")
        if not (self.stress.n_paths.value >= 1 and self.stress.horizon_days.value >= 1):
            raise ValueError("stress: n_paths và horizon_days phải dương")
        if not 0 < self.stress.short_shortfall_ratio.value <= 1:
            raise ValueError("stress: short_shortfall_ratio phải trong (0, 1]")
        return self

    def label_of(self, key: str) -> str:
        return getattr(self.components, key).label


# --- cú sốc dạng dữ liệu -----------------------------------------------------------------------
#: Tham số bắt buộc (và duy nhất được nhận) của từng loại cú sốc.
SHOCK_PARAMS_BY_KIND: dict[str, tuple[str, ...]] = {
    "income_loss": ("duration_days", "income_loss_percent"),
    "expense_increase": ("target_obligation_kind", "expense_increase_percent", "duration_days"),
    "health_event": ("duration_days", "income_loss_percent", "extra_cost_vnd"),
}


class ShockParams(_Model):
    duration_days: Annotated[int, Field(ge=1, le=365)] | None = None
    income_loss_percent: Annotated[float, Field(ge=0, le=100)] | None = None
    extra_cost_vnd: Vnd | None = None
    expense_increase_percent: Annotated[float, Field(ge=0, le=1000)] | None = None
    target_obligation_kind: ObligationKind | None = None


class ShockDefinition(_Model):
    shock_id: SlugKey
    kind: Literal["income_loss", "expense_increase", "health_event"]
    label: Annotated[str, Field(min_length=1, max_length=60)]
    description: Annotated[str, Field(min_length=1, max_length=160)]
    params: ShockParams
    source: Annotated[str, Field(min_length=1, max_length=300)]

    @model_validator(mode="after")
    def _params_match_kind(self) -> ShockDefinition:
        """Mỗi loại đòi đúng các tham số của nó, không thừa không thiếu (JSON Schema không diễn đạt được)."""
        given = {k for k, v in self.params.model_dump().items() if v is not None}
        if given != set(SHOCK_PARAMS_BY_KIND[self.kind]):
            raise ValueError(
                f"cú sốc {self.kind} cần đúng các tham số {SHOCK_PARAMS_BY_KIND[self.kind]}, đang có {sorted(given)}"
            )
        return self

    def summary(self) -> ShockSummary:
        """Bản gọn đi vào khối `stress_result` và `GET /resilience/shocks`."""
        return ShockSummary(
            shock_id=self.shock_id,
            kind=self.kind,
            label=self.label,
            description=self.description,
            duration_days=self.params.duration_days,
        )


class ShockSet(_Model):
    version: Annotated[str, Field(min_length=1, max_length=40)]
    note: Annotated[str, Field(min_length=1, max_length=600)]
    shocks: Annotated[list[ShockDefinition], Field(min_length=1, max_length=12)]

    @model_validator(mode="after")
    def _unique_ids(self) -> ShockSet:
        ids = [s.shock_id for s in self.shocks]
        if len(set(ids)) != len(ids):
            raise ValueError("shock_id phải duy nhất")
        return self

    def get(self, shock_id: str) -> ShockDefinition | None:
        return next((s for s in self.shocks if s.shock_id == shock_id), None)


def _read(name: str) -> dict[str, Any]:
    return json.loads(Path(__file__).with_name(name).read_text(encoding="utf-8"))


def parse_config(obj: dict[str, Any]) -> ResilienceConfig:
    """Kiểm một cấu hình đã nạp từ JSON (ném `pydantic.ValidationError` nếu sai)."""
    return ResilienceConfig.model_validate(obj, strict=False)


def parse_shock_set(obj: dict[str, Any]) -> ShockSet:
    """Kiểm một bộ cú sốc đã nạp từ JSON (ném `pydantic.ValidationError` nếu sai)."""
    return ShockSet.model_validate(obj, strict=False)


@cache
def load_resilience_config() -> ResilienceConfig:
    """Cấu hình đóng gói cùng module (`resilience_defaults.json`)."""
    return parse_config(_read(DEFAULTS_FILE))


@cache
def load_shock_set() -> ShockSet:
    """Ba cú sốc mẫu đóng gói cùng module (`shocks.json`)."""
    return parse_shock_set(_read(SHOCKS_FILE))


def band_for_score(score: int, config: ResilienceConfig | None = None) -> str:
    """Nhóm điểm theo ngưỡng của cấu hình (không có số gắn cứng): weak, fair hoặc strong."""
    cfg = config or load_resilience_config()
    if score <= cfg.bands.weak_max_score.value:
        return "weak"
    if score <= cfg.bands.fair_max_score.value:
        return "fair"
    return "strong"
