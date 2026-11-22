"""Hợp đồng của lớp suitability (phase 3): đề xuất, kết luận và định dạng file luật.

- `Proposal`: thứ `planner___check_suitability` nhận (khớp `contracts/tools/planner.json`).
- `SuitabilityVerdict`, `Violation`: thứ nó trả (khớp `contracts/tools/planner.results.schema.json`); agent (Verifier L4) dùng lại.
- `SuitabilityRule`: định dạng một file luật `gateway/tools/planner/rules/*.yaml` (khớp `rules/rule.schema.json`).

Chỉ có KIỂU và kiểm hình dạng, **không có rule engine**: luồng engine (A) viết bộ đánh giá cho từng `evaluator` và đọc ngưỡng
từ `thresholds` của file luật. Ngưỡng là dữ liệu, mỗi ngưỡng có đơn vị, ghi chú và nguồn; không gắn cứng trong mã.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yofina_core.blocks import JarCode, RuleCheck, RuleId, VndPositive

EvaluatorName = Literal[
    "essential_obligations_covered",
    "emergency_fund_before_investing",
    "risk_within_tolerance",
    "no_credit_for_discretionary",
    "obligation_income_ratio",
]
EVALUATORS: tuple[str, ...] = (
    "essential_obligations_covered",
    "emergency_fund_before_investing",
    "risk_within_tolerance",
    "no_credit_for_discretionary",
    "obligation_income_ratio",
)
Severity = Literal["block", "warn"]
Category = Literal["spending", "saving", "investment", "debt_payment"]
Origin = Literal["recommendation", "user_request"]
RiskLevel = Literal["low", "medium", "high"]
FundingSource = Literal["jar", "credit"]
ThresholdUnit = Literal["ratio", "months", "days", "vnd", "level", "flag"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Proposal(_Model):
    """Đề xuất cần kiểm (đầu vào của `check_suitability`)."""

    kind: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
    amount_vnd: VndPositive | None = None
    funding_source: FundingSource | None = None
    jar_code: JarCode | None = None
    is_essential: bool | None = None
    category: Category | None = None
    risk_level: RiskLevel | None = None
    origin: Origin | None = None


class Violation(_Model):
    rule_id: RuleId
    severity: Severity
    message: Annotated[str, Field(min_length=1, max_length=200)]


class SuitabilityVerdict(_Model):
    ok: bool
    violations: Annotated[list[Violation], Field(max_length=10)]
    checked: Annotated[list[RuleCheck], Field(max_length=20)]
    rules_version: Annotated[str, Field(min_length=1, max_length=40)]

    @model_validator(mode="after")
    def _consistent(self) -> SuitabilityVerdict:
        has_block = any(v.severity == "block" for v in self.violations)
        if self.ok == has_block:
            raise ValueError("ok phải đúng khi và chỉ khi không có vi phạm mức block")
        outcome = {c.rule_id: c.outcome for c in self.checked}
        for v in self.violations:
            if outcome.get(v.rule_id) not in ("warn", "fail"):
                raise ValueError(
                    f"vi phạm {v.rule_id} phải có trong checked với outcome warn hoặc fail"
                )
        return self


# --- định dạng file luật ---------------------------------------------------------------------
class Threshold(_Model):
    """Một ngưỡng của luật. `value` là số, chuỗi hoặc cờ; `unit` nói nó đo gì."""

    value: float | int | str | bool
    unit: ThresholdUnit
    note: Annotated[str, Field(min_length=1, max_length=400)]
    source: Annotated[str, Field(min_length=1, max_length=300)] | None = None


class AppliesWhen(_Model):
    """Bộ lọc áp luật. Trường vắng là không lọc theo trường đó; mọi trường có mặt phải cùng khớp."""

    categories: list[Category] | None = None
    origins: list[Origin] | None = None
    funding_sources: list[FundingSource] | None = None
    essential: bool | None = None


class SuitabilityRule(_Model):
    id: RuleId
    version: Annotated[int, Field(ge=1)]
    title: Annotated[str, Field(min_length=1, max_length=80)]
    description: Annotated[str, Field(min_length=1, max_length=500)]
    evaluator: EvaluatorName
    severity: Severity
    recommendation_severity: Severity | None = None
    applies_when: AppliesWhen | None = None
    thresholds: dict[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")], Threshold]
    message: Annotated[str, Field(min_length=1, max_length=200)]

    def severity_for(self, origin: str | None) -> str:
        """Mức nghiêm trọng theo nguồn: phương án hệ thống đề xuất có thể nghiêm hơn lời người dùng tự đưa ra."""
        if origin == "recommendation" and self.recommendation_severity:
            return self.recommendation_severity
        return self.severity


def parse_rule(obj: dict[str, Any]) -> SuitabilityRule:
    """Kiểm một file luật đã nạp từ YAML (ném `pydantic.ValidationError` nếu sai)."""
    return SuitabilityRule.model_validate(obj, strict=False)
