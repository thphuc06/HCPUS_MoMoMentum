"""`ScenarioSpec`: kịch bản what-if (FR5), model Pydantic khớp `contracts/scenario/scenario_spec.schema.json`.

Sáu loại, phân biệt theo `kind`. JSON Schema là nguồn chung; ở đây viết tay (như `blocks.py`) và được test đối
chiếu (hình dạng từng loại và fixture dùng chung, xem `tests/unit/test_contracts_phase3.py`).

Hai luật liên trường mà JSON Schema (tập con của repo) không diễn đạt được, nên **Pydantic quyết định**:
- `jar_transfer`: `from_jar` khác `to_jar`;
- `recurring_expense`: `end_date` không trước `date`;
- mọi ngày phải là ngày lịch thật (schema chỉ kiểm dạng `YYYY-MM-DD`).

Dùng ở: agent (Simulation specialist dịch câu hỏi sang spec), Lambda `forecast` (`run_scenario`), bảng `scenarios`.
Số tiền là số nguyên VND dương. Không đọc đồng hồ hệ thống: `date` vắng nghĩa là hôm nay mô phỏng, engine điền.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import Field, TypeAdapter, model_validator

from yofina_core.blocks import IsoDate, JarCode, VndPositive, _Strict
from yofina_core.confirm import canonical_json

Label = Annotated[str, Field(min_length=1, max_length=80)]


def _check_date(name: str, value: str | None) -> None:
    if value is None:
        return
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} không phải ngày lịch hợp lệ: {value!r}") from exc


class _ScenarioBase(_Strict):
    @model_validator(mode="after")
    def _dates_are_real(self) -> _ScenarioBase:
        for name in ("date", "end_date"):
            _check_date(name, getattr(self, name, None))
        return self


class OneTimePurchase(_ScenarioBase):
    kind: Literal["one_time_purchase"]
    amount_vnd: VndPositive
    funding_source: Literal["jar"]
    jar_code: JarCode
    date: IsoDate | None = None
    label: Label | None = None


class BnplPurchase(_ScenarioBase):
    kind: Literal["bnpl_purchase"]
    amount_vnd: VndPositive
    funding_source: Literal["credit"]
    jar_code: JarCode | None = None
    date: IsoDate | None = None
    label: Label | None = None


class IncomeChange(_ScenarioBase):
    kind: Literal["income_change"]
    new_monthly_salary_vnd: VndPositive
    date: IsoDate | None = None
    label: Label | None = None


class RecurringExpense(_ScenarioBase):
    kind: Literal["recurring_expense"]
    amount_vnd: VndPositive
    cycle: Literal["weekly", "monthly", "yearly"]
    date: IsoDate
    end_date: IsoDate | None = None
    jar_code: JarCode
    label: Label | None = None

    @model_validator(mode="after")
    def _end_not_before_start(self) -> RecurringExpense:
        if self.end_date is not None and self.end_date < self.date:
            raise ValueError("end_date không được trước date")
        return self


class JarTransfer(_ScenarioBase):
    kind: Literal["jar_transfer"]
    amount_vnd: VndPositive
    from_jar: JarCode
    to_jar: JarCode
    date: IsoDate | None = None
    label: Label | None = None

    @model_validator(mode="after")
    def _different_jars(self) -> JarTransfer:
        if self.from_jar == self.to_jar:
            raise ValueError("from_jar và to_jar phải khác nhau")
        return self


class GoalDelay(_ScenarioBase):
    kind: Literal["goal_delay"]
    jar_code: JarCode
    delay_months: Annotated[int, Field(ge=1, le=60)]
    label: Label | None = None


ScenarioSpec = Annotated[
    OneTimePurchase | BnplPurchase | IncomeChange | RecurringExpense | JarTransfer | GoalDelay,
    Field(discriminator="kind"),
]
SCENARIO_ADAPTER: TypeAdapter[Any] = TypeAdapter(ScenarioSpec)

#: kind -> model, cùng thứ tự với `oneOf` của scenario_spec.schema.json.
SCENARIO_MODELS: dict[str, type[_ScenarioBase]] = {
    "one_time_purchase": OneTimePurchase,
    "bnpl_purchase": BnplPurchase,
    "income_change": IncomeChange,
    "recurring_expense": RecurringExpense,
    "jar_transfer": JarTransfer,
    "goal_delay": GoalDelay,
}


def parse_scenario(obj: Mapping[str, Any]) -> _ScenarioBase:
    """Kiểm một spec (ném `pydantic.ValidationError` nếu sai)."""
    return SCENARIO_ADAPTER.validate_python(obj)


def scenario_to_wire(spec: _ScenarioBase) -> dict[str, Any]:
    """Dạng JSON chuẩn: bỏ trường tùy chọn vắng. Dùng cho `scenarios.spec` và băm."""
    return spec.model_dump(mode="json", exclude_none=True)


def scenario_hash(spec: _ScenarioBase | Mapping[str, Any]) -> str:
    """sha256 hex của dạng JSON chuẩn của spec (cùng công thức canonical_json như `params_hash`).

    Hai spec cùng nghĩa (khác thứ tự khóa, hoặc có `null` ở trường tùy chọn) ra cùng hash."""
    model = spec if isinstance(spec, _ScenarioBase) else parse_scenario(spec)
    return hashlib.sha256(canonical_json(scenario_to_wire(model)).encode("utf-8")).hexdigest()
