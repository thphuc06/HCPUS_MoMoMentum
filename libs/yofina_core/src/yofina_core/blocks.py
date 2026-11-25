"""Khối UI: model Pydantic khớp `contracts/blocks/*.schema.json` và hàm dựng khối.

Nguồn sự thật là JSON Schema trong `contracts/blocks/`. Các model ở đây viết tay và được test
đối chiếu với schema (hình dạng và fixture dùng chung, xem `tests/unit/test_contracts_blocks.py`).
Frontend dùng Zod sinh từ cùng schema (`scripts/gen_contracts.mjs`).

Nguyên tắc: **số trong khối do code dựng từ kết quả tool/sổ cái**, không do LLM viết. Các hàm
`build_*` nhận số thật (int, Decimal hoặc chuỗi numeric của Data API) và tự dựng `fallback_text`.

Quy tắc `id` (ổn định trong một lượt, cùng id thì khối sau thay khối trước):
- jar_summary: `jar_summary:{trace_id}`
- confirm:     `confirm:{trace_id}:{params_hash[:12]}`
- receipt:     `receipt:{transaction_id}`
- notice:      `notice:{trace_id}:{code hoặc kind}`
- confirm_action: `confirm:{trace_id}:{params_hash[:12]}` (cùng tiền tố `confirm:` với khối confirm)
- receipt_action: `receipt:{tool}:{reference_id}` hoặc `receipt:{tool}:{trace_id}`
- forecast_timeline: `forecast_timeline:{trace_id}:{jar_code}`
- proactive_card: `proactive_card:{trace_id}:{kind}`
- forecast_timeline trước-sau (có `compare`): `forecast_timeline:{trace_id}:{jar_code}:what_if`
- affordability_card: `affordability_card:{trace_id}`
- obligation_impact: `obligation_impact:{trace_id}:{due_date}`
- options: `options:{trace_id}`
- explain: `explain:{subject_trace_id}`
- clarify: `clarify:{trace_id}`
- suggestions: `suggestions:{trace_id}:{context}`
- ingest_review: `ingest_review:{job_id}`; coverage_change: `coverage_change:{job_id}` (dựng bằng
  `yofina_core.ingest.build_ingest_review` và `build_coverage_change`)
- resilience_score: `resilience_score:{trace_id}`; stress_result: `stress_result:{trace_id}:{shock_id}`
- roadmap: `roadmap:{trace_id}:v{version}`; roadmap_diff: `roadmap_diff:{trace_id}:v{from}-v{to}`
- review_list: `review_list:{trace_id}:{mode}`
- behavior_insight: `behavior_insight:{trace_id}:{insight_id}`; citation: `citation:{trace_id}` (phase 5)
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from yofina_core.confirm import (
    MOVE_BETWEEN_JARS,
    hash_normalized_params,
    normalize_params,
    params_hash,
)
from yofina_core.money import format_vnd, to_vnd
from yofina_core.schedule import obligation_window
from yofina_core.wallet import DEFAULT_OBLIGATION_JAR, GENERIC_ACTION_TOOLS, JarPurpose

SCHEMA_VERSION = 1
MAX_VND = 99_999_999_999_999

# --- kiểu cơ bản (khớp envelope.schema.json#/$defs) ---------------------------------------
Vnd = Annotated[int, Field(ge=0, le=MAX_VND)]
VndPositive = Annotated[int, Field(ge=1, le=MAX_VND)]
JarCode = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
BlockId = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")]
TraceId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
FallbackText = Annotated[str, Field(min_length=1, max_length=280)]
IsoDate = Annotated[str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")]
IsoDateTime = Annotated[
    str,
    Field(
        pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})$"
    ),
]
JarName = Annotated[str, Field(min_length=1, max_length=40)]
KeyName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")]
SlugKey = Annotated[
    str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
]  # id trong khối phase 3 (không có dấu gạch ngang)
Summary = Annotated[str, Field(min_length=1, max_length=120)]
ToolName = Literal["move_between_jars"]
UserJarKind = Literal["spending", "saving", "obligation"]  # khớp wallet.USER_JAR_KINDS (test kiểm)


class _Strict(BaseModel):
    """`extra=forbid` giống `additionalProperties: false`: phía sinh dữ liệu phải chặt."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Source(_Strict):
    tool: Annotated[str, Field(min_length=1, max_length=80)]
    as_of: IsoDateTime
    app_date: IsoDate


class _BlockBase(_Strict):
    v: Literal[1]
    id: BlockId
    trace_id: TraceId
    fallback_text: FallbackText
    source: Source


# --- jar_summary --------------------------------------------------------------------------
class SinkingItem(_Strict):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    amount_vnd: VndPositive
    needed_date: IsoDate


class JarBalance(_Strict):
    code: JarCode
    name: JarName
    color_key: KeyName
    icon_key: KeyName
    balance_vnd: Vnd
    split_percent: Annotated[float, Field(ge=0, le=100)]
    # Phase 4 (tùy chọn, tương thích ngược): loại hũ và mục tiêu GỐC đọc từ bảng `jars`, để lộ trình dựng được `save_jars`.
    kind: UserJarKind | None = None
    purpose: JarPurpose | None = None
    goal_vnd: VndPositive | None = None
    goal_date: IsoDate | None = None
    sinking_items: Annotated[list[SinkingItem], Field(max_length=40)] | None = None

    @model_validator(mode="after")
    def _goal_pair(self) -> JarBalance:
        if self.purpose is not None and self.kind != "saving":
            raise ValueError("purpose chỉ dành cho hũ để dành")
        if self.goal_date is not None and self.goal_vnd is None and self.purpose not in ("sinking", "long_term"):
            raise ValueError("goal_date cần goal_vnd")
        return self


class JarSummaryData(_Strict):
    jars: Annotated[list[JarBalance], Field(max_length=20)]
    jars_total_vnd: Vnd


class JarSummaryBlock(_BlockBase):
    type: Literal["jar_summary"]
    data: JarSummaryData


# --- confirm ------------------------------------------------------------------------------
class MoveParams(_Strict):
    from_jar: JarCode
    to_jar: JarCode
    amount_vnd: VndPositive


class JarChange(_Strict):
    code: JarCode
    name: JarName
    before_vnd: Vnd
    after_vnd: Vnd


class ConfirmPreview(_Strict):
    # `from` là từ khóa Python: dùng alias.
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, populate_by_name=True)
    from_: JarChange = Field(alias="from")
    to: JarChange


class ConfirmData(_Strict):
    tool: ToolName
    params: MoveParams
    params_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    summary: Summary
    preview: ConfirmPreview
    expires_at: IsoDateTime


class ConfirmBlock(_BlockBase):
    type: Literal["confirm"]
    data: ConfirmData


# --- receipt ------------------------------------------------------------------------------
class JarAfter(_Strict):
    code: JarCode
    name: JarName
    balance_after_vnd: Vnd


class ReceiptData(_Strict):
    tool: ToolName
    transaction_id: Annotated[
        str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    ]
    occurred_at: IsoDateTime
    app_date: IsoDate
    amount_vnd: VndPositive
    summary: Summary
    from_jar: JarAfter
    to_jar: JarAfter


class ReceiptBlock(_BlockBase):
    type: Literal["receipt"]
    data: ReceiptData


# --- notice -------------------------------------------------------------------------------
# `info` (phase 4, tương thích ngược): chỉ mang thông tin hoặc trạng thái trống, không phải lỗi.
NoticeKind = Literal["out_of_scope", "degraded", "low_data", "error", "info"]


DegradedReason = Literal[
    "model_budget", "model_error", "tool_error", "tool_timeout", "verifier_failed",
    "low_coverage", "short_history",
]  # fmt: skip


class SuggestionItem(_Strict):
    id: SlugKey
    label: Annotated[str, Field(min_length=1, max_length=40)]
    prompt: Annotated[str, Field(min_length=1, max_length=200)]


class NoticeData(_Strict):
    kind: NoticeKind
    title: Annotated[str, Field(min_length=1, max_length=80)]
    message: Annotated[str, Field(min_length=1, max_length=280)]
    code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]*$")] | None = None
    # Phase 3 (tùy chọn, tương thích ngược)
    retryable: bool | None = None
    degraded_reason: DegradedReason | None = None
    missing: (
        Annotated[list[Annotated[str, Field(min_length=1, max_length=80)]], Field(max_length=5)]
        | None
    ) = None
    suggestions: Annotated[list[SuggestionItem], Field(max_length=4)] | None = None


class NoticeBlock(_BlockBase):
    type: Literal["notice"]
    data: NoticeData


# --- forecast_timeline ---------------------------------------------------------------------
VndSigned = Annotated[int, Field(ge=-MAX_VND, le=MAX_VND)]
Ratio = Annotated[float, Field(ge=0, le=1)]
Uuid = Annotated[
    str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
]
JarStatus = Literal["ok", "tight", "short"]
ConfidenceBand = Literal["high", "medium", "low"]


class ForecastJar(_Strict):
    code: JarCode
    name: JarName
    color_key: KeyName
    icon_key: KeyName
    purpose: JarPurpose | None = None


class ForecastPayday(_Strict):
    date: IsoDate
    days_until: Annotated[int, Field(ge=0, le=400)]


class ForecastDay(_Strict):
    date: IsoDate
    p10_vnd: VndSigned
    p50_vnd: VndSigned
    p90_vnd: VndSigned


class ForecastEvent(_Strict):
    date: IsoDate
    kind: Literal["obligation", "salary"]
    label: Annotated[str, Field(min_length=1, max_length=60)]
    amount_vnd: VndPositive
    amount_max_vnd: VndPositive | None = None


class ForecastDueShortfall(_Strict):
    date: IsoDate
    label: Annotated[str, Field(min_length=1, max_length=60)]
    shortfall_vnd: VndPositive


class ForecastObligationWindow(_Strict):
    items: list[ForecastEvent]
    first_shortfall: ForecastDueShortfall | None = None


ScenarioKindName = Literal[
    "one_time_purchase", "bnpl_purchase", "income_change", "recurring_expense", "jar_transfer",
    "goal_delay",
]  # fmt: skip


class ForecastBasis(_Strict):
    computed_at: IsoDateTime
    stale: bool
    confidence_band: ConfidenceBand
    is_initial_estimate: bool
    history_days: Annotated[int, Field(ge=0)]
    coverage: Ratio | None = None


class ForecastScenarioPath(_Strict):
    status: JarStatus
    runout_date: IsoDate | None = None
    p_shortfall: Ratio | None = None
    p_shortfall_se: Ratio | None = None
    min_balance_p50_vnd: VndSigned | None = None
    days: Annotated[list[ForecastDay], Field(min_length=1, max_length=90)]
    events: Annotated[list[ForecastEvent], Field(max_length=60)] | None = None
    obligations_before_payday: ForecastObligationWindow | None = None


class ForecastCompareDelta(_Strict):
    min_balance_delta_vnd: VndSigned
    runout_shift_days: Annotated[int, Field(ge=-400, le=400)] | None = None
    p_shortfall_delta: Annotated[float, Field(ge=-1, le=1)] | None = None


class ForecastCompare(_Strict):
    label: Annotated[str, Field(min_length=1, max_length=80)]
    kind: ScenarioKindName
    scenario_id: Uuid | None = None
    after: ForecastScenarioPath
    delta: ForecastCompareDelta
    n_paths: Annotated[int, Field(ge=1)]
    common_random_numbers: bool


class ForecastTimelineData(_Strict):
    jar: ForecastJar
    status: JarStatus
    origin_date: IsoDate
    start_balance_vnd: VndSigned
    horizon_days: Annotated[int, Field(ge=1, le=90)]
    payday: ForecastPayday
    runout_date: IsoDate | None = None
    p_shortfall: Ratio | None = None
    p_shortfall_se: Ratio | None = None
    confidence_band: ConfidenceBand
    coverage: Ratio | None = None
    history_days: Annotated[int, Field(ge=0)]
    is_initial_estimate: bool
    model: Annotated[str, Field(min_length=1, max_length=40)]
    computed_at: IsoDateTime
    stale: bool
    days: Annotated[list[ForecastDay], Field(min_length=1, max_length=90)]
    events: Annotated[list[ForecastEvent], Field(max_length=60)]
    obligations_before_payday: ForecastObligationWindow | None = None
    compare: ForecastCompare | None = None


class ForecastTimelineBlock(_BlockBase):
    type: Literal["forecast_timeline"]
    data: ForecastTimelineData


# --- proactive_card ------------------------------------------------------------------------
ProactiveKind = Literal[
    "runout_warning", "obligation_due", "salary_pending", "review_needed", "low_data",
    "roadmap_proposed", "resilience_drop", "behavior_insight",
]  # fmt: skip
ProactiveActionKind = Literal[
    "open_forecast", "confirm_salary", "review_unclassified", "open_obligations",
    "ask_why", "snooze", "mute_kind", "open_roadmap", "open_resilience", "open_profile",
]  # fmt: skip


class ProactiveAction(_Strict):
    kind: ProactiveActionKind
    label: Annotated[str, Field(min_length=1, max_length=40)]
    jar_code: JarCode | None = None
    prompt: Annotated[str, Field(min_length=1, max_length=200)] | None = None


class ProactiveCardData(_Strict):
    kind: ProactiveKind
    status: JarStatus
    title: Annotated[str, Field(min_length=1, max_length=80)]
    reason: Annotated[str, Field(min_length=1, max_length=200)]
    jar_code: JarCode | None = None
    nudge_id: Uuid | None = None  # phase 5: bản tin của cổng giá trị (dòng `nudges`), để "Để sau" và "Ít nhắc loại này" gửi phản hồi
    actions: Annotated[list[ProactiveAction], Field(min_length=1, max_length=4)]


class ProactiveCardBlock(_BlockBase):
    type: Literal["proactive_card"]
    data: ProactiveCardData


# --- coverage_change (phase 5, F6) ---------------------------------------------------------
class CoverageJar(_Strict):
    code: JarCode
    name: JarName


class CoverageChangeData(_Strict):
    job_id: Uuid
    before: Ratio | None = None
    after: Ratio | None = None
    rows_added: Annotated[int, Field(ge=0)]
    external_spend_added_vnd: Vnd
    external_income_added_vnd: Vnd | None = None
    jars_affected: Annotated[list[CoverageJar], Field(max_length=20)]
    forecast_refresh: Literal["queued", "done", "skipped"]


class CoverageChangeBlock(_BlockBase):
    type: Literal["coverage_change"]
    data: CoverageChangeData


# --- ingest_review (phase 5, F6) -----------------------------------------------------------
IngestJobStatus = Literal[
    "awaiting_upload", "queued", "processing", "review", "done", "failed", "rejected"
]
IngestRowStatus = Literal["auto_added", "pending", "approved", "rejected", "duplicate"]


class IngestJar(_Strict):
    code: JarCode
    name: JarName
    color_key: KeyName
    icon_key: KeyName


#: số thập phân không âm dạng chuỗi (số tiền theo ngoại tệ, tỷ giá VND cho một đơn vị): chính xác, không qua float
FxDecimal = Annotated[str, Field(pattern=r"^[0-9]{1,12}(\.[0-9]{1,4})?$", max_length=17)]
CurrencyCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class IngestFx(_Strict):
    """Dòng ghi bằng ngoại tệ (F6): số và tiền tệ đúng như chứng từ, và tỷ giá đã dùng để ước tính `amount_vnd`.

    `converted`: có tỷ giá bán của nguồn (`rate_source`) ngày `rate_date`, `amount_vnd` = làm tròn tới đồng của
    `amount_original * rate`. `rate_unavailable`: tra tỷ giá lỗi, không có `rate_*` và dòng chưa có `amount_vnd` cho tới khi
    người dùng nhập số VND lúc chốt."""

    currency: CurrencyCode
    amount_original: FxDecimal
    status: Literal["converted", "rate_unavailable"]
    #: số VND cho một đơn vị ngoại tệ (không phải số tiền nên không có hậu tố `_vnd`)
    rate: FxDecimal | None = None
    rate_type: Literal["sell"] | None = None
    rate_source: Literal["vietcombank"] | None = None
    rate_date: IsoDate | None = None

    @model_validator(mode="after")
    def _rate_matches_status(self) -> IngestFx:
        fields = (self.rate, self.rate_type, self.rate_source, self.rate_date)
        if self.currency == "VND":
            raise ValueError("fx chỉ dành cho dòng không phải VND")
        if self.status == "converted" and any(f is None for f in fields):
            raise ValueError("fx converted cần đủ rate, rate_type, rate_source, rate_date")
        if self.status == "rate_unavailable" and any(f is not None for f in fields):
            raise ValueError("fx rate_unavailable không có rate_*")
        return self


class IngestRow(_Strict):
    row_id: Uuid
    seq: Annotated[int, Field(ge=1, le=10000)]
    kind: Literal["expense", "income"]
    app_date: IsoDate
    #: vắng CHỈ khi dòng ngoại tệ chưa có tỷ giá (`fx.status = rate_unavailable`): người dùng nhập số VND lúc chốt
    amount_vnd: VndPositive | None = None
    counterparty: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    description: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    extract_confidence: Ratio
    suggested_jar: IngestJar | None = None
    jar_confidence: Ratio | None = None
    jar_source: Literal["type_map", "rule", "model", "user"] | None = None
    review_status: IngestRowStatus
    duplicate_of: Uuid | None = None
    fx: IngestFx | None = None

    @model_validator(mode="after")
    def _amount_or_pending_rate(self) -> IngestRow:
        if self.amount_vnd is None and (self.fx is None or self.fx.status != "rate_unavailable"):
            raise ValueError("amount_vnd chỉ được vắng ở dòng ngoại tệ chưa có tỷ giá")
        return self


class IngestCounts(_Strict):
    auto_added: Annotated[int, Field(ge=0)]
    pending: Annotated[int, Field(ge=0)]
    approved: Annotated[int, Field(ge=0)]
    rejected: Annotated[int, Field(ge=0)]
    duplicate: Annotated[int, Field(ge=0)]


class IngestReviewData(_Strict):
    job_id: Uuid
    status: IngestJobStatus
    source_kind: Literal["image", "csv"]
    rows: Annotated[list[IngestRow], Field(max_length=200)]
    rows_total: Annotated[int, Field(ge=0)]
    counts: IngestCounts
    jars: Annotated[list[IngestJar], Field(max_length=20)]


class IngestReviewBlock(_BlockBase):
    type: Literal["ingest_review"]
    data: IngestReviewData


# --- confirm_action ------------------------------------------------------------------------
ConfirmActionTool = Literal[
    "record_transaction", "assign_jar", "update_profile", "save_jars", "confirm_salary",
    "schedule_nudge",
    "confirm_rows",
]  # fmt: skip


class ActionChange(_Strict):
    label: Annotated[str, Field(min_length=1, max_length=60)]
    before: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    after: Annotated[str, Field(min_length=1, max_length=120)]


class ConfirmActionData(_Strict):
    tool: ConfirmActionTool
    params: dict[str, Any]
    params_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    summary: Summary
    changes: Annotated[list[ActionChange], Field(min_length=1, max_length=20)]
    warnings: (
        Annotated[list[Annotated[str, Field(min_length=1, max_length=140)]], Field(max_length=5)]
        | None
    ) = None
    expires_at: IsoDateTime


class ConfirmActionBlock(_BlockBase):
    type: Literal["confirm_action"]
    data: ConfirmActionData


# --- receipt_action ------------------------------------------------------------------------
class ReceiptDetail(_Strict):
    label: Annotated[str, Field(min_length=1, max_length=60)]
    value: Annotated[str, Field(min_length=1, max_length=120)]


class ReceiptFollowUp(_Strict):
    kind: Literal["confirm_salary", "review_unclassified"]
    label: Annotated[str, Field(min_length=1, max_length=80)]
    salary_event_id: Uuid | None = None
    expected_vnd: VndPositive | None = None
    received_vnd: VndPositive | None = None
    deviation_percent: Annotated[float, Field(ge=-100000, le=100000)] | None = None
    ask_update_salary: bool | None = None


class JarBalanceAfter(_Strict):
    code: JarCode
    name: JarName
    balance_after_vnd: VndSigned


class ReceiptActionData(_Strict):
    tool: ConfirmActionTool
    reference_id: Uuid | None = None
    occurred_at: IsoDateTime
    app_date: IsoDate
    amount_vnd: VndPositive | None = None
    summary: Summary
    jars_after: Annotated[list[JarBalanceAfter], Field(max_length=20)]
    details: Annotated[list[ReceiptDetail], Field(max_length=20)]
    follow_up: ReceiptFollowUp | None = None
    #: chỉ có với confirm_rows (phase 5): khối coverage_change của lần chốt
    coverage_change: CoverageChangeBlock | None = None


class ReceiptActionBlock(_BlockBase):
    type: Literal["receipt_action"]
    data: ReceiptActionData


# --- phase 3: tác động nghĩa vụ, phương án, kiểm tra trước khi quẹt, giải thích, hỏi lại, gợi ý ------
RuleId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64)]
OptionKind = Literal[
    "defer", "switch_jar", "split", "pay_now", "use_credit", "proceed", "reduce_amount",
    "move_between_jars", "remind_later", "skip",
]  # fmt: skip
ActionToolName = Literal[
    "move_between_jars", "record_transaction", "assign_jar", "update_profile", "save_jars",
    "confirm_salary", "schedule_nudge",
]  # fmt: skip


class FeeApplied(_Strict):
    fee_type: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
    amount_vnd: Vnd
    source_name: Annotated[str, Field(min_length=1, max_length=200)]
    effective_from: IsoDate


class Caution(_Strict):
    rule_id: RuleId
    text: Annotated[str, Field(min_length=1, max_length=140)]


class CreditCost(_Strict):
    product_label: Annotated[str, Field(min_length=1, max_length=60)]
    principal_vnd: VndPositive
    fee_added_vnd: Vnd
    item_cost_vnd: VndPositive
    due_date: IsoDate
    existing_due_vnd: Vnd
    total_due_vnd: VndPositive
    fee: FeeApplied | None = None
    late_penalty_vnd: Vnd | None = None
    limit_vnd: Vnd | None = None
    available_before_vnd: Vnd | None = None
    available_after_vnd: Vnd | None = None

    @model_validator(mode="after")
    def _invariants(self) -> CreditCost:
        """Bất biến của hợp đồng: tách chi phí của món này khỏi tổng phải trả ngày đến hạn."""
        if self.item_cost_vnd != self.principal_vnd + self.fee_added_vnd:
            raise ValueError("item_cost_vnd phải bằng principal_vnd + fee_added_vnd")
        if self.total_due_vnd != self.existing_due_vnd + self.item_cost_vnd:
            raise ValueError("total_due_vnd phải bằng existing_due_vnd + item_cost_vnd")
        return self


class ObligationRatio(_Strict):
    obligations_vnd: Vnd
    income_vnd: Vnd
    ratio: Annotated[float, Field(ge=0)]
    threshold: Ratio
    exceeds: bool


class JarAtDue(_Strict):
    jar: ForecastJar
    status: JarStatus
    balance_before_due_vnd: VndSigned
    due_vnd: Vnd
    shortfall_vnd: Vnd


class ObligationImpactData(_Strict):
    status: JarStatus
    headline: Annotated[str, Field(min_length=1, max_length=160)]
    cost: CreditCost
    at_due: Annotated[list[JarAtDue], Field(min_length=1, max_length=8)]
    shortfall_vnd: Vnd
    ratio: ObligationRatio | None = None
    cautions: Annotated[list[Caution], Field(max_length=3)] | None = None
    basis: ForecastBasis


class ObligationImpactBlock(_BlockBase):
    type: Literal["obligation_impact"]
    data: ObligationImpactData


class OptionAction(_Strict):
    kind: Literal["confirm", "confirm_action"]
    tool: ActionToolName
    block_id: Annotated[
        str, Field(pattern=r"^confirm:[A-Za-z0-9_-]+:[0-9a-f]{12}$", max_length=128)
    ]

    @model_validator(mode="after")
    def _kind_matches_tool(self) -> OptionAction:
        """`confirm` chỉ cho chuyển hũ; mọi tool ghi khác dùng `confirm_action` (như hai cặp khối phase 2)."""
        if (self.kind == "confirm") != (self.tool == MOVE_BETWEEN_JARS):
            raise ValueError("kind confirm đi với move_between_jars; confirm_action với tool khác")
        return self


class OptionItem(_Strict):
    option_id: SlugKey
    kind: OptionKind
    label: Annotated[str, Field(min_length=1, max_length=60)]
    summary: Annotated[str, Field(min_length=1, max_length=200)]
    status: JarStatus
    recommended: bool | None = None
    metrics: Annotated[list[ActionChange], Field(max_length=4)] | None = None
    checked_rules: Annotated[list[RuleId], Field(max_length=8)] | None = None
    action: OptionAction | None = None


class OptionsData(_Strict):
    title: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    scenario_id: Uuid | None = None
    options: Annotated[list[OptionItem], Field(min_length=2, max_length=3)]

    @model_validator(mode="after")
    def _ids_unique_one_recommended(self) -> OptionsData:
        ids = [o.option_id for o in self.options]
        if len(set(ids)) != len(ids):
            raise ValueError("option_id phải duy nhất trong khối")
        if sum(1 for o in self.options if o.recommended) > 1:
            raise ValueError("tối đa một phương án recommended")
        return self


class OptionsBlock(_BlockBase):
    type: Literal["options"]
    data: OptionsData


class JarCheck(_Strict):
    jar: ForecastJar
    status: JarStatus
    balance_before_vnd: VndSigned
    balance_after_vnd: VndSigned
    runout_date_before: IsoDate | None = None
    runout_date_after: IsoDate | None = None
    days_earlier: Annotated[int, Field(ge=0, le=400)] | None = None
    shortfall_vnd: Vnd | None = None
    p_shortfall_after: Ratio | None = None


class AffordabilityCardData(_Strict):
    verdict: JarStatus
    headline: Annotated[str, Field(min_length=1, max_length=160)]
    amount_vnd: VndPositive
    label: Annotated[str, Field(min_length=1, max_length=60)] | None = None
    pay_date: IsoDate | None = None
    funding_source: Literal["jar", "credit"]
    selected_jar_code: JarCode | None = None
    jar_checks: Annotated[list[JarCheck], Field(max_length=8)]
    credit: ObligationImpactData | None = None
    cautions: Annotated[list[Caution], Field(max_length=3)] | None = None
    options: Annotated[list[OptionItem], Field(max_length=4)]
    basis: ForecastBasis


class AffordabilityCardBlock(_BlockBase):
    type: Literal["affordability_card"]
    data: AffordabilityCardData


class DataUsed(_Strict):
    label: Annotated[str, Field(min_length=1, max_length=80)]
    value: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    tool: Annotated[str, Field(min_length=1, max_length=80)]
    as_of: IsoDateTime | None = None


RuleOutcomeName = Literal["pass", "warn", "fail", "skipped"]


class RuleCheck(_Strict):
    rule_id: RuleId
    label: Annotated[str, Field(min_length=1, max_length=80)]
    outcome: RuleOutcomeName
    detail: Annotated[str, Field(min_length=1, max_length=200)] | None = None


class ExplainConfidence(_Strict):
    band: ConfidenceBand
    reasons: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=140)]],
        Field(min_length=1, max_length=4),
    ]


class ExplainData(_Strict):
    subject_trace_id: TraceId
    headline: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    data_used: Annotated[list[DataUsed], Field(min_length=1, max_length=20)]
    rules_checked: Annotated[list[RuleCheck], Field(max_length=20)]
    confidence: ExplainConfidence
    ai_generated: bool | None = None


class ExplainBlock(_BlockBase):
    type: Literal["explain"]
    data: ExplainData


ClarifySlot = Literal["amount", "funding_source", "jar", "date", "scenario_kind", "other"]


class ClarifyChip(_Strict):
    id: SlugKey
    label: Annotated[str, Field(min_length=1, max_length=40)]
    value: Annotated[str, Field(min_length=1, max_length=80)] | None = None


class ClarifyData(_Strict):
    question: Annotated[str, Field(min_length=1, max_length=200)]
    slot: ClarifySlot
    chips: Annotated[list[ClarifyChip], Field(max_length=6)]
    pending_intent: Literal["what_if", "affordability", "move", "profile_update"] | None = None
    allow_free_text: bool | None = None

    @model_validator(mode="after")
    def _exactly_one_question(self) -> ClarifyData:
        """Đúng một câu hỏi: không quá một dấu hỏi (hợp đồng của khối `clarify`)."""
        if self.question.count("?") > 1:
            raise ValueError("khối clarify chỉ hỏi đúng một câu")
        return self


class ClarifyBlock(_BlockBase):
    type: Literal["clarify"]
    data: ClarifyData


SuggestionContext = Literal["welcome", "after_answer", "out_of_scope", "degraded"]


class SuggestionsData(_Strict):
    context: SuggestionContext
    title: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    can_do: (
        Annotated[list[Annotated[str, Field(min_length=1, max_length=80)]], Field(max_length=6)]
        | None
    ) = None
    cannot_do: (
        Annotated[list[Annotated[str, Field(min_length=1, max_length=80)]], Field(max_length=6)]
        | None
    ) = None
    items: Annotated[list[SuggestionItem], Field(min_length=1, max_length=6)]


class SuggestionsBlock(_BlockBase):
    type: Literal["suggestions"]
    data: SuggestionsData


# --- phase 4: điểm chống chịu, cú sốc, lộ trình, danh sách "Xem lại" -------------------------------------
Number = Annotated[float, Field(ge=-MAX_VND, le=MAX_VND)]
Score = Annotated[int, Field(ge=0, le=100)]
Weight = Annotated[float, Field(ge=0, le=1)]
RoadmapVersion = Annotated[int, Field(ge=1, le=10000)]
ResilienceComponentKey = Literal["save", "spend", "borrow", "plan"]
ResilienceBand = Literal["weak", "fair", "strong"]
MetricUnit = Literal["vnd", "days", "ratio", "count"]
ShockKind = Literal["income_loss", "expense_increase", "health_event"]
RoadmapReasonCode = Literal[
    "initial", "behavior_changed", "goal_changed", "income_changed", "forecast_drift",
    "user_request", "step_edited",
]  # fmt: skip
RoadmapVersionStatus = Literal["active", "proposed", "superseded", "discarded"]
RoadmapStepStatus = Literal["pending", "accepted", "rejected"]
RoadmapStepKind = Literal[
    "set_aside", "adjust_split", "pay_obligation", "cut_spending", "review_goal", "remind"
]  # fmt: skip
RoadmapStepActionTool = Literal["move_between_jars", "save_jars", "schedule_nudge"]
RoadmapFeasibility = Literal["on_track", "relaxed", "infeasible"]
AlternativeKind = Literal["delay_goal", "reduce_goal", "cut_discretionary"]
ClassificationTier = Literal["auto", "review", "ask"]
ClassifiedByName = Literal["user", "type_map", "rule", "embedding", "llm", "seed"]
ReviewMode = Literal["review", "daily_ask"]
ReviewAskStatus = Literal["open", "answered", "skipped"]
#: Thứ tự cố định của bốn thành phần (hiển thị và lưu).
RESILIENCE_ORDER: tuple[str, ...] = ("save", "spend", "borrow", "plan")


class ResilienceInput(_Strict):
    """Một đầu vào đã dùng để tính một thành phần (ví dụ số dư khả dụng, chi tiêu mỗi ngày)."""

    key: SlugKey
    label: Annotated[str, Field(min_length=1, max_length=60)]
    value: Number
    unit: MetricUnit

    @model_validator(mode="after")
    def _unit_matches_value(self) -> ResilienceInput:
        """Tiền và số đếm là số nguyên (hợp đồng "tiền là số nguyên VND"); JSON Schema chỉ biết `number`."""
        if self.unit in ("vnd", "count") and self.value != int(self.value):
            raise ValueError("đầu vào đơn vị vnd hoặc count phải là số nguyên")
        if self.unit in ("days", "ratio", "count") and self.value < 0:
            raise ValueError("đầu vào days, ratio, count không âm")
        return self


class ResilienceComponent(_Strict):
    key: ResilienceComponentKey
    label: Annotated[str, Field(min_length=1, max_length=40)]
    score: Score | None = None
    weight: Weight
    applicable: bool
    band: ResilienceBand | None = None
    explanation: Annotated[str, Field(min_length=1, max_length=200)]
    inputs: Annotated[list[ResilienceInput], Field(max_length=6)]

    @model_validator(mode="after")
    def _applicable_consistent(self) -> ResilienceComponent:
        if self.applicable != (self.score is not None) or self.applicable != (
            self.band is not None
        ):
            raise ValueError("applicable đúng khi và chỉ khi có score và band")
        if not self.applicable and self.weight != 0:
            raise ValueError("thành phần không áp dụng có weight bằng 0")
        return self


class ResilienceScoreData(_Strict):
    score: Score
    band: ResilienceBand
    headline: Annotated[str, Field(min_length=1, max_length=160)]
    app_date: IsoDate
    computed_at: IsoDateTime
    components: Annotated[list[ResilienceComponent], Field(min_length=4, max_length=4)]
    weakest: ResilienceComponentKey
    previous_score: Score | None = None
    config_version: Annotated[str, Field(min_length=1, max_length=40)]
    disclaimer: Annotated[str, Field(min_length=1, max_length=160)]
    basis: ForecastBasis

    @model_validator(mode="after")
    def _invariants(self) -> ResilienceScoreData:
        """Bất biến của hợp đồng: đủ bốn thành phần đúng thứ tự, trọng số của các thành phần áp dụng cộng lại bằng 1,
        điểm tổng bằng trung bình có trọng số (sai lệch tối đa 1 do làm tròn), `weakest` là thành phần áp dụng thấp nhất."""
        if tuple(c.key for c in self.components) != RESILIENCE_ORDER:
            raise ValueError("components phải đủ save, spend, borrow, plan đúng thứ tự")
        live = [c for c in self.components if c.applicable]
        if not live:
            raise ValueError("cần ít nhất một thành phần áp dụng")
        if abs(sum(c.weight for c in live) - 1) > 0.005:
            raise ValueError("trọng số của các thành phần áp dụng phải cộng lại bằng 1")
        weighted = sum(c.weight * (c.score or 0) for c in live)
        if abs(self.score - weighted) > 1:
            raise ValueError("score phải bằng trung bình có trọng số của các thành phần")
        lowest = min(live, key=lambda c: (c.score or 0, RESILIENCE_ORDER.index(c.key)))
        if self.weakest != lowest.key:
            raise ValueError("weakest phải là thành phần áp dụng có điểm thấp nhất")
        return self


class ResilienceScoreBlock(_BlockBase):
    type: Literal["resilience_score"]
    data: ResilienceScoreData


class ShockSummary(_Strict):
    """Cú sốc đã áp (bản gọn của một mục trong `shocks.json`); nhãn và mô tả lấy từ file dữ liệu, không viết trong mã."""

    shock_id: SlugKey
    kind: ShockKind
    label: Annotated[str, Field(min_length=1, max_length=60)]
    description: Annotated[str, Field(min_length=1, max_length=160)]
    duration_days: Annotated[int, Field(ge=1, le=365)] | None = None


class StressComponentDelta(_Strict):
    key: ResilienceComponentKey
    score_before: Score | None = None
    score_after: Score | None = None


class StressResultData(_Strict):
    shock: ShockSummary
    status: JarStatus
    headline: Annotated[str, Field(min_length=1, max_length=160)]
    score_before: Score
    score_after: Score
    score_delta: Annotated[int, Field(ge=-100, le=0)]
    band_before: ResilienceBand
    band_after: ResilienceBand
    runway_days_total: Annotated[int, Field(ge=0, le=400)] | None = None
    runway_days_emergency: Annotated[int, Field(ge=0, le=400)] | None = None
    emergency_jar: ForecastJar | None = None
    horizon_days: Annotated[int, Field(ge=1, le=400)]
    shortfall_vnd: Vnd
    shortfall_from: IsoDate | None = None
    components: Annotated[list[StressComponentDelta], Field(min_length=4, max_length=4)]
    method: Literal["monte_carlo"]
    n_paths: Annotated[int, Field(ge=1)]
    common_random_numbers: Literal[True]
    basis: ForecastBasis

    @model_validator(mode="after")
    def _invariants(self) -> StressResultData:
        """Cú sốc không làm điểm tăng; `score_delta` đúng bằng sau trừ trước; có khoản thiếu thì không thể là "đủ"; số ngày
        của hũ Dự phòng chỉ có khi có hũ đó."""
        if self.score_after > self.score_before:
            raise ValueError("score_after không được cao hơn score_before")
        if self.score_delta != self.score_after - self.score_before:
            raise ValueError("score_delta phải bằng score_after - score_before")
        if tuple(c.key for c in self.components) != RESILIENCE_ORDER:
            raise ValueError("components phải đủ save, spend, borrow, plan đúng thứ tự")
        if self.shortfall_vnd > 0 and self.status == "ok":
            raise ValueError("có khoản thiếu thì status không thể là ok")
        if (self.shortfall_from is None) != (self.shortfall_vnd == 0):
            raise ValueError("shortfall_from có đúng khi shortfall_vnd lớn hơn 0")
        if self.runway_days_emergency is not None and self.emergency_jar is None:
            raise ValueError("runway_days_emergency cần emergency_jar")
        return self


class StressResultBlock(_BlockBase):
    type: Literal["stress_result"]
    data: StressResultData


class RoadmapReason(_Strict):
    """Vì sao có phiên bản này. `text` do code dựng từ sự kiện kích hoạt (không do LLM viết); `detail` là các con số của sự kiện."""

    code: RoadmapReasonCode
    text: Annotated[str, Field(min_length=1, max_length=160)]
    detail: Annotated[list[ActionChange], Field(max_length=3)] | None = None
    behavior_flag_id: Uuid | None = None


class RoadmapHorizon(_Strict):
    start_date: IsoDate
    end_date: IsoDate


class GoalProjection(_Strict):
    """Một mục tiêu (hũ có `goal_vnd`) so với kế hoạch: kịp hạn hay không, thiếu bao nhiêu, mỗi tháng cần bao nhiêu."""

    jar: ForecastJar
    target_vnd: VndPositive
    target_date: IsoDate | None = None
    projected_date: IsoDate | None = None
    on_track: bool
    shortfall_vnd: Vnd
    monthly_needed_vnd: Vnd

    @model_validator(mode="after")
    def _on_track_has_no_shortfall(self) -> GoalProjection:
        if self.on_track and self.shortfall_vnd != 0:
            raise ValueError("mục tiêu kịp hạn (on_track) thì shortfall_vnd bằng 0")
        return self


class RoadmapStepAction(_Strict):
    """Việc đổi tiền gắn vào bước. Người dùng thực hiện bằng luồng xác nhận của ADR-0002 (`POST /confirmations` rồi `POST /actions`
    với đúng `tool` và `params`); chấp nhận một bước KHÔNG tự thực hiện hành động và không đổi số dư."""

    tool: RoadmapStepActionTool
    params: dict[str, Any]

    @model_validator(mode="after")
    def _no_secrets(self) -> RoadmapStepAction:
        if {"user_id", "confirm_token"} & set(self.params):
            raise ValueError("params không được có user_id hoặc confirm_token")
        return self


class RoadmapStep(_Strict):
    step_id: SlugKey
    kind: RoadmapStepKind
    title: Annotated[str, Field(min_length=1, max_length=80)]
    reason: Annotated[str, Field(min_length=1, max_length=240)]
    ai_generated: bool | None = None
    amount_vnd: VndPositive | None = None
    jar_code: JarCode | None = None
    to_jar_code: JarCode | None = None
    due_date: IsoDate | None = None
    metrics: Annotated[list[ActionChange], Field(max_length=4)] | None = None
    checked_rules: Annotated[list[RuleId], Field(max_length=8)] | None = None
    action: RoadmapStepAction | None = None
    status: RoadmapStepStatus
    decided_at: IsoDateTime | None = None
    edited: bool | None = None

    @model_validator(mode="after")
    def _decided_iff_not_pending(self) -> RoadmapStep:
        if (self.status == "pending") != (self.decided_at is None):
            raise ValueError("decided_at có đúng khi status khác pending")
        return self


class RoadmapPhase(_Strict):
    phase_id: SlugKey
    title: Annotated[str, Field(min_length=1, max_length=60)]
    summary: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    start_date: IsoDate
    end_date: IsoDate
    steps: Annotated[list[RoadmapStep], Field(min_length=1, max_length=8)]

    @model_validator(mode="after")
    def _dates_ordered(self) -> RoadmapPhase:
        if self.end_date < self.start_date:
            raise ValueError("end_date không được trước start_date")
        return self


class RoadmapAlternative(_Strict):
    """Một trong hai lựa chọn nói thẳng khi mục tiêu chưa khả thi. Chọn nó thì gửi `alternative_id` ở `POST /roadmap/regenerate`."""

    option_id: SlugKey
    kind: AlternativeKind
    label: Annotated[str, Field(min_length=1, max_length=60)]
    summary: Annotated[str, Field(min_length=1, max_length=200)]
    jar_code: JarCode | None = None
    metrics: Annotated[list[ActionChange], Field(max_length=4)] | None = None


class RoadmapCounts(_Strict):
    pending: Annotated[int, Field(ge=0)]
    accepted: Annotated[int, Field(ge=0)]
    rejected: Annotated[int, Field(ge=0)]


class RoadmapData(_Strict):
    roadmap_id: Uuid
    version: RoadmapVersion
    status: RoadmapVersionStatus
    reason: RoadmapReason
    based_on_version: RoadmapVersion | None = None
    created_at: IsoDateTime
    app_date: IsoDate
    headline: Annotated[str, Field(min_length=1, max_length=160)]
    feasibility: RoadmapFeasibility
    horizon: RoadmapHorizon
    goals: Annotated[list[GoalProjection], Field(max_length=8)]
    phases: Annotated[list[RoadmapPhase], Field(min_length=1, max_length=5)]
    alternatives: Annotated[list[RoadmapAlternative], Field(max_length=2)]
    counts: RoadmapCounts
    rules_version: Annotated[str, Field(min_length=1, max_length=40)]
    basis: ForecastBasis

    @model_validator(mode="after")
    def _invariants(self) -> RoadmapData:
        """Id duy nhất, số bước đếm đúng, phiên bản gốc cũ hơn, giai đoạn xếp theo thời gian, và nói thẳng khi chưa khả thi:
        `infeasible` kèm đúng hai lựa chọn và ít nhất một mục tiêu không kịp; `on_track` thì mọi mục tiêu kịp; các trường hợp
        khác không có lựa chọn."""
        steps = [s for p in self.phases for s in p.steps]
        if len({s.step_id for s in steps}) != len(steps):
            raise ValueError("step_id phải duy nhất trong lộ trình")
        if len({p.phase_id for p in self.phases}) != len(self.phases):
            raise ValueError("phase_id phải duy nhất trong lộ trình")
        derived = RoadmapCounts(
            pending=sum(s.status == "pending" for s in steps),
            accepted=sum(s.status == "accepted" for s in steps),
            rejected=sum(s.status == "rejected" for s in steps),
        )
        if derived != self.counts:
            raise ValueError("counts phải bằng số bước theo từng trạng thái")
        if self.based_on_version is not None and self.based_on_version >= self.version:
            raise ValueError("based_on_version phải nhỏ hơn version")
        starts = [p.start_date for p in self.phases]
        if starts != sorted(starts):
            raise ValueError("giai đoạn phải xếp theo start_date")
        if (self.feasibility == "infeasible") != (len(self.alternatives) == 2):
            raise ValueError(
                "infeasible đi với đúng hai lựa chọn, trường hợp khác không có lựa chọn"
            )
        if len({a.option_id for a in self.alternatives}) != len(self.alternatives):
            raise ValueError("option_id của lựa chọn phải duy nhất")
        if self.feasibility == "on_track" and not all(g.on_track for g in self.goals):
            raise ValueError("on_track thì mọi mục tiêu phải kịp")
        if self.feasibility == "infeasible" and all(g.on_track for g in self.goals):
            raise ValueError("infeasible thì phải có ít nhất một mục tiêu không kịp")
        return self


class RoadmapBlock(_BlockBase):
    type: Literal["roadmap"]
    data: RoadmapData


class RoadmapChange(_Strict):
    kind: Literal["added", "removed", "changed"]
    step_id: SlugKey
    phase_id: SlugKey | None = None
    title: Annotated[str, Field(min_length=1, max_length=80)]
    fields: Annotated[list[ActionChange], Field(max_length=6)] | None = None
    reason_after: Annotated[str, Field(min_length=1, max_length=240)] | None = None


class RoadmapDiffCounts(_Strict):
    added: Annotated[int, Field(ge=0)]
    removed: Annotated[int, Field(ge=0)]
    changed: Annotated[int, Field(ge=0)]
    unchanged: Annotated[int, Field(ge=0)]


class RoadmapDiffData(_Strict):
    from_version: RoadmapVersion
    to_version: RoadmapVersion
    from_roadmap_id: Uuid
    to_roadmap_id: Uuid
    to_status: RoadmapVersionStatus
    reason: RoadmapReason
    headline: Annotated[str, Field(min_length=1, max_length=160)]
    changes: Annotated[list[RoadmapChange], Field(max_length=30)]
    counts: RoadmapDiffCounts
    can_adopt: bool

    @model_validator(mode="after")
    def _invariants(self) -> RoadmapDiffData:
        if self.from_version == self.to_version:
            raise ValueError("from_version và to_version phải khác nhau")
        for kind in ("added", "removed", "changed"):
            if sum(c.kind == kind for c in self.changes) != getattr(self.counts, kind):
                raise ValueError(f"counts.{kind} phải bằng số thay đổi loại {kind}")
        if len({c.step_id for c in self.changes}) != len(self.changes):
            raise ValueError("mỗi bước chỉ có một thay đổi")
        if self.can_adopt != (self.to_status == "proposed"):
            raise ValueError("can_adopt đúng khi to_status là proposed")
        return self


class RoadmapDiffBlock(_BlockBase):
    type: Literal["roadmap_diff"]
    data: RoadmapDiffData


class ReviewJarRef(_Strict):
    code: JarCode
    name: JarName


class ReviewSuggestion(_Strict):
    jar: ForecastJar
    confidence: Ratio | None = None
    reason: Annotated[str, Field(min_length=1, max_length=80)]


class ReviewItem(_Strict):
    transaction_id: Uuid
    occurred_at: IsoDateTime
    app_date: IsoDate
    kind: Literal["expense", "income"]
    amount_vnd: VndPositive
    counterparty: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    note: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    tier: ClassificationTier
    current_jar: ReviewJarRef | None = None
    classified_by: ClassifiedByName | None = None
    confidence: Ratio | None = None
    suggestions: Annotated[list[ReviewSuggestion], Field(max_length=2)]
    can_remember: bool


class ReviewAsk(_Strict):
    ask_date: IsoDate
    status: ReviewAskStatus


class ReviewListData(_Strict):
    mode: ReviewMode
    headline: Annotated[str, Field(min_length=1, max_length=160)]
    count: Annotated[int, Field(ge=0)]
    pending_total_vnd: Vnd
    items: Annotated[list[ReviewItem], Field(max_length=50)]
    jars: Annotated[list[ForecastJar], Field(max_length=20)]
    ask: ReviewAsk | None = None

    @model_validator(mode="after")
    def _invariants(self) -> ReviewListData:
        """A1 chỉ có mục mức `review`, A2 (hỏi gộp) chỉ có mức `ask` và kèm trạng thái câu hỏi hôm nay; `count` không nhỏ hơn số
        mục đang hiện (có thể nhiều hơn vì danh sách bị cắt)."""
        want = "review" if self.mode == "review" else "ask"
        if any(i.tier != want for i in self.items):
            raise ValueError(f"chế độ {self.mode} chỉ nhận mục mức {want}")
        if (self.ask is not None) != (self.mode == "daily_ask"):
            raise ValueError("ask có đúng khi mode là daily_ask")
        if self.count < len(self.items):
            raise ValueError("count không được nhỏ hơn số mục đang hiện")
        if len({i.transaction_id for i in self.items}) != len(self.items):
            raise ValueError("mỗi giao dịch chỉ xuất hiện một lần")
        return self


class ReviewListBlock(_BlockBase):
    type: Literal["review_list"]
    data: ReviewListData


# --- phase 5: nhận xét hành vi, trích dẫn ---------------------------------------------------------------
BehaviorInsightKind = Literal[
    "payday_cycle", "weekday_pattern", "time_of_day", "bnpl_usage", "category_trend", "spending_cluster",
]  # fmt: skip
EvidenceUnit = Literal["vnd", "percent", "ratio", "days", "count", "hour", "weekday"]
InsightHeadline = Annotated[str, Field(min_length=1, max_length=160)]


class BehaviorEvidence(_Strict):
    """Một con số làm bằng chứng cho nhận xét, đọc từ sổ cái trong cửa sổ `period_from`..`period_to`."""

    key: SlugKey
    label: Annotated[str, Field(min_length=1, max_length=80)]
    value: Number
    unit: EvidenceUnit
    period_from: IsoDate | None = None
    period_to: IsoDate | None = None

    @model_validator(mode="after")
    def _unit_matches_value(self) -> BehaviorEvidence:
        """Tiền và số đếm là số nguyên không âm (tiền có thể âm chỉ ở dòng sổ cái, không ở đây); tỷ lệ, phần trăm, giờ, thứ
        nằm trong khoảng của đơn vị; cửa sổ không ngược."""
        v = self.value
        if self.unit in ("vnd", "count", "hour", "weekday") and v != int(v):
            raise ValueError("bằng chứng đơn vị vnd, count, hour, weekday phải là số nguyên")
        if self.unit in ("vnd", "count", "days") and v < 0:
            raise ValueError("bằng chứng đơn vị vnd, count, days không âm")
        if self.unit == "ratio" and not 0 <= v <= 1:
            raise ValueError("ratio nằm trong 0..1")
        if self.unit == "percent" and not 0 <= v <= 100:
            raise ValueError("percent nằm trong 0..100")
        if self.unit == "hour" and not 0 <= v <= 23:
            raise ValueError("hour nằm trong 0..23")
        if self.unit == "weekday" and not 1 <= v <= 7:
            raise ValueError("weekday là 1 (thứ Hai) tới 7 (Chủ nhật)")
        if self.period_from and self.period_to and self.period_from > self.period_to:
            raise ValueError("period_from không được sau period_to")
        return self


class BehaviorInsight(_Strict):
    insight_id: SlugKey
    kind: BehaviorInsightKind
    headline: InsightHeadline
    detail: Annotated[str, Field(min_length=1, max_length=280)] | None = None
    jar_code: JarCode | None = None
    evidence: Annotated[list[BehaviorEvidence], Field(min_length=1, max_length=6)]
    confidence: ConfidenceBand
    ai_generated: bool

    @model_validator(mode="after")
    def _evidence_keys_unique(self) -> BehaviorInsight:
        if len({e.key for e in self.evidence}) != len(self.evidence):
            raise ValueError("key của bằng chứng phải duy nhất trong một nhận xét")
        return self


class BehaviorNextStep(_Strict):
    """MỘT việc cần làm; `action` (tùy chọn) thực hiện bằng luồng xác nhận, bấm vào không tự ghi gì."""

    label: Annotated[str, Field(min_length=1, max_length=80)]
    reason: Annotated[str, Field(min_length=1, max_length=200)]
    action: RoadmapStepAction | None = None


class BehaviorFeatures(_Strict):
    history_days: Annotated[int, Field(ge=0)]
    avg_daily_spend_vnd: Vnd | None = None
    first_week_after_payday_share: Ratio | None = None
    weekend_share: Ratio | None = None
    evening_share: Ratio | None = None
    top_weekday: Annotated[int, Field(ge=1, le=7)] | None = None
    bnpl_purchases_per_month: Annotated[float, Field(ge=0, le=1000)] | None = None
    bnpl_share: Ratio | None = None


class BehaviorSegment(_Strict):
    segment_id: SlugKey
    label: Annotated[str, Field(min_length=1, max_length=60)]


class BehaviorProfileData(_Strict):
    """Hồ sơ hành vi ở một ngày mô phỏng (bảng `behavior_profiles`). Chưa sẵn sàng (`ready` sai) không phải lỗi."""

    ready: bool
    app_date: IsoDate
    computed_at: IsoDateTime | None = None
    config_version: Annotated[str, Field(min_length=1, max_length=40)] | None = None
    headline: InsightHeadline
    history_days: Annotated[int, Field(ge=0)]
    min_history_days: Annotated[int, Field(ge=1)] | None = None
    features: BehaviorFeatures | None = None
    segment: BehaviorSegment | None = None
    insights: Annotated[list[BehaviorInsight], Field(max_length=6)]
    next_step: BehaviorNextStep | None = None

    @model_validator(mode="after")
    def _ready_consistent(self) -> BehaviorProfileData:
        """Sẵn sàng thì có thời điểm tính, phiên bản cấu hình, đặc trưng và ít nhất một nhận xét; chưa sẵn sàng thì không có
        nhận xét, không có việc cần làm và nói cần bao nhiêu ngày. Id nhận xét duy nhất; đặc trưng cùng số ngày lịch sử."""
        if self.ready:
            if not (self.computed_at and self.config_version and self.features and self.insights and self.next_step):
                raise ValueError(
                    "hồ sơ sẵn sàng phải có computed_at, config_version, features, next_step và ít nhất một nhận xét"
                )
            if self.features.history_days != self.history_days:
                raise ValueError("features.history_days phải bằng history_days")
        else:
            if self.insights or self.next_step is not None:
                raise ValueError("hồ sơ chưa sẵn sàng thì không có nhận xét hay việc cần làm")
            if self.min_history_days is None:
                raise ValueError("hồ sơ chưa sẵn sàng phải nói min_history_days")
        if len({i.insight_id for i in self.insights}) != len(self.insights):
            raise ValueError("insight_id phải duy nhất trong hồ sơ")
        return self


class BehaviorInsightData(_Strict):
    insight: BehaviorInsight
    next_step: BehaviorNextStep
    app_date: IsoDate
    computed_at: IsoDateTime
    history_days: Annotated[int, Field(ge=0)]
    config_version: Annotated[str, Field(min_length=1, max_length=40)] | None = None


class BehaviorInsightBlock(_BlockBase):
    type: Literal["behavior_insight"]
    data: BehaviorInsightData


FeeType = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
ProductCode = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")]


class FeeLine(_Strict):
    """Một dòng biểu phí có cấu trúc (bảng `fee_schedules`), khớp `FeeLine` của `contracts/tools/knowledge.results.schema.json`."""

    fee_type: FeeType
    amount_vnd: Vnd | None = None
    rate_percent: Annotated[float, Field(ge=0)] | None = None
    period: Literal["per_month", "per_transaction", "once"]
    condition_code: Literal["always", "month_has_transaction", "overdue"]
    condition_note: Annotated[str, Field(max_length=200)] | None = None
    source_name: Annotated[str, Field(max_length=200)]
    source_url: Annotated[str, Field(pattern=r"^https://")]
    effective_from: IsoDate


class FeeScheduleData(_Strict):
    """`data` của `knowledge___get_fee_schedule` (cũng là `fees` của `GET /credit-line`): đầu vào của `build_citation`."""

    product_code: ProductCode
    product_label: Annotated[str, Field(max_length=60)]
    fees: Annotated[list[FeeLine], Field(min_length=1, max_length=20)]


class GetFeeScheduleOk(_Strict):
    status: Literal["OK"]
    as_of: IsoDateTime
    app_date: IsoDate
    data: FeeScheduleData


class CitationItem(_Strict):
    """Một nguồn của biểu phí (chép từ các `FeeLine` cùng tên nguồn, đường dẫn và ngày hiệu lực) kèm các loại phí của nó."""

    fee_types: Annotated[list[FeeType], Field(min_length=1, max_length=20)]
    source_name: Annotated[str, Field(min_length=1, max_length=200)]
    source_url: Annotated[str, Field(pattern=r"^https://", max_length=500)]
    effective_from: IsoDate
    excerpt: Annotated[str, Field(min_length=1, max_length=200)] | None = None


class CitationData(_Strict):
    product_code: ProductCode
    product_label: Annotated[str, Field(min_length=1, max_length=60)]
    items: Annotated[list[CitationItem], Field(min_length=1, max_length=5)]

    @model_validator(mode="after")
    def _sources_unique(self) -> CitationData:
        keys = [(i.source_name, i.source_url, i.effective_from) for i in self.items]
        if len(set(keys)) != len(keys):
            raise ValueError("mỗi nguồn (tên, đường dẫn, ngày hiệu lực) chỉ một mục")
        fee_types = [t for i in self.items for t in i.fee_types]
        if len(set(fee_types)) != len(fee_types):
            raise ValueError("mỗi loại phí thuộc đúng một nguồn")
        return self

class CitationBlock(_BlockBase):
    type: Literal["citation"]
    data: CitationData


# --- reasoning (phase 6, luồng K: người tư vấn) --------------------------------------------
ReasoningContext = Literal["what_if", "roadmap"]
ReasoningPersonal = Literal["memory", "behavior"]
ReasoningText = Annotated[str, Field(min_length=1, max_length=160)]
#: tối đa số bước lập luận của một khối (khớp `maxItems` của schema)
REASONING_MAX_STEPS = 5


class ReasoningBasis(_Strict):
    """Căn cứ của một bước: tool đã gọi thành công trong lượt hoặc luật phù hợp đã kiểm. `label` do code dựng."""

    kind: Literal["tool", "rule"]
    ref: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
    label: Annotated[str, Field(min_length=1, max_length=60)]


class ReasoningStep(_Strict):
    step_id: Annotated[str, Field(pattern=r"^s[1-5]$")]
    seen: ReasoningText
    why: ReasoningText
    effect: ReasoningText
    basis: Annotated[list[ReasoningBasis], Field(min_length=1, max_length=4)]


class ReasoningConclusion(_Strict):
    text: Annotated[str, Field(min_length=1, max_length=240)]
    option_id: SlugKey | None = None
    step_id: SlugKey | None = None
    personal: Annotated[list[ReasoningPersonal], Field(max_length=2)] | None = None

    @model_validator(mode="after")
    def _personal_unique(self) -> ReasoningConclusion:
        if self.personal is not None and len(set(self.personal)) != len(self.personal):
            raise ValueError("personal không được lặp")
        return self


class ReasoningData(_Strict):
    context: ReasoningContext
    complete: bool
    steps: Annotated[list[ReasoningStep], Field(max_length=REASONING_MAX_STEPS)]
    conclusion: ReasoningConclusion | None = None

    @model_validator(mode="after")
    def _consistent(self) -> ReasoningData:
        if [s.step_id for s in self.steps] != [f"s{i + 1}" for i in range(len(self.steps))]:
            raise ValueError("step_id phải là s1, s2... liên tiếp")
        if not self.complete and (not self.steps or self.conclusion is not None):
            raise ValueError("bản chưa xong có ít nhất một bước và chưa có kết luận")
        if not self.steps and self.conclusion is None:
            raise ValueError("cần ít nhất một bước hoặc một kết luận")
        c = self.conclusion
        if c is not None and ((self.context == "what_if" and c.step_id) or (self.context == "roadmap" and c.option_id)):
            raise ValueError("kết luận what_if trỏ phương án (option_id), lộ trình trỏ bước (step_id)")
        return self


class ReasoningBlock(_BlockBase):
    type: Literal["reasoning"]
    data: ReasoningData


Block = Annotated[
    JarSummaryBlock
    | ConfirmBlock
    | ReceiptBlock
    | NoticeBlock
    | ForecastTimelineBlock
    | ProactiveCardBlock
    | ConfirmActionBlock
    | ReceiptActionBlock
    | AffordabilityCardBlock
    | ObligationImpactBlock
    | OptionsBlock
    | ExplainBlock
    | ClarifyBlock
    | SuggestionsBlock
    | IngestReviewBlock
    | CoverageChangeBlock
    | ResilienceScoreBlock
    | StressResultBlock
    | RoadmapBlock
    | RoadmapDiffBlock
    | ReviewListBlock
    | BehaviorInsightBlock
    | CitationBlock
    | ReasoningBlock,
    Field(discriminator="type"),
]
BLOCK_ADAPTER: TypeAdapter[Any] = TypeAdapter(Block)

#: type -> model, cùng thứ tự với `contracts/blocks/block.schema.json`.
BLOCK_MODELS: dict[str, type[_BlockBase]] = {
    "jar_summary": JarSummaryBlock,
    "confirm": ConfirmBlock,
    "receipt": ReceiptBlock,
    "notice": NoticeBlock,
    "forecast_timeline": ForecastTimelineBlock,
    "proactive_card": ProactiveCardBlock,
    "confirm_action": ConfirmActionBlock,
    "receipt_action": ReceiptActionBlock,
    "affordability_card": AffordabilityCardBlock,
    "obligation_impact": ObligationImpactBlock,
    "options": OptionsBlock,
    "explain": ExplainBlock,
    "clarify": ClarifyBlock,
    "suggestions": SuggestionsBlock,
    "ingest_review": IngestReviewBlock,
    "coverage_change": CoverageChangeBlock,
    "resilience_score": ResilienceScoreBlock,
    "stress_result": StressResultBlock,
    "roadmap": RoadmapBlock,
    "roadmap_diff": RoadmapDiffBlock,
    "review_list": ReviewListBlock,
    "behavior_insight": BehaviorInsightBlock,
    "citation": CitationBlock,
    "reasoning": ReasoningBlock,
}


def parse_block(obj: Mapping[str, Any]) -> _BlockBase:
    """Kiểm một khối đã biết (ném `pydantic.ValidationError` nếu sai)."""
    return BLOCK_ADAPTER.validate_python(obj)


def block_to_wire(block: _BlockBase) -> dict[str, Any]:
    """Dạng JSON gửi đi: bỏ trường tùy chọn vắng (không phát `null`), `from` thay `from_`."""
    return block.model_dump(mode="json", by_alias=True, exclude_none=True)


# --- trace id -----------------------------------------------------------------------------
_TRACEPARENT_RE = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$")


def trace_id_from_traceparent(header: str | None) -> str | None:
    """Lấy trace-id (32 hex) từ header W3C `traceparent`; không hợp lệ thì trả None."""
    if not header:
        return None
    m = _TRACEPARENT_RE.match(header.strip().lower())
    if not m or set(m.group(1)) == {"0"}:
        return None
    return m.group(1)


def new_trace_id() -> str:
    """trace id do server sinh khi client không gửi `traceparent` (REST)."""
    return uuid.uuid4().hex


# --- dựng khối ----------------------------------------------------------------------------
def format_instant(value: datetime) -> str:
    """RFC 3339 ở UTC, giây, hậu tố Z (ví dụ `2026-11-21T03:00:00Z`)."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Thời điểm phải có múi giờ")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _source(tool: str, as_of: datetime, app_date: date) -> Source:
    return Source(tool=tool, as_of=format_instant(as_of), app_date=app_date.isoformat())


def _percent(value: int | float | Decimal | str) -> float:
    p = Decimal(str(value))
    return int(p) if p == p.to_integral_value() else float(p)  # type: ignore[return-value]


def _jar_row(row: Mapping[str, Any]) -> JarBalance:
    goal_vnd, goal_date = row.get("goal_vnd"), row.get("goal_date")
    if isinstance(goal_date, date):
        goal_date = goal_date.isoformat()
    return JarBalance(
        code=row["code"],
        name=row["name"],
        color_key=row["color_key"],
        icon_key=row["icon_key"],
        balance_vnd=to_vnd(row["balance_vnd"]),
        split_percent=_percent(row["split_percent"]),
        kind=row.get("kind"),
        purpose=row.get("purpose"),
        sinking_items=row.get("sinking_items") or None,
        goal_vnd=to_vnd(goal_vnd) if goal_vnd is not None else None,
        goal_date=goal_date,
    )


def build_jar_summary(
    *,
    jars: Iterable[Mapping[str, Any]],
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    block_id: str | None = None,
) -> JarSummaryBlock:
    """Khối số dư các hũ. `jars` theo thứ tự hiển thị; mỗi dòng gồm code, name, color_key,
    icon_key, balance_vnd, split_percent (giá trị đọc từ DB, tiền có thể là Decimal/chuỗi) và tùy chọn
    kind, goal_vnd, goal_date (phase 4; vắng hoặc NULL thì bỏ). Không truyền hũ hệ thống vào đây."""
    rows = [_jar_row(r) for r in jars]
    total = sum(r.balance_vnd for r in rows)
    text = f"Số dư {len(rows)} hũ, tổng {format_vnd(total)}." if rows else "Bạn chưa có hũ nào."
    return JarSummaryBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"jar_summary:{trace_id}",
        type="jar_summary",
        trace_id=trace_id,
        fallback_text=text,
        source=_source(source_tool, as_of, app_date),
        data=JarSummaryData(jars=rows, jars_total_vnd=total),
    )


def build_confirm(
    *,
    tool: str,
    params: Mapping[str, Any],
    from_jar: Mapping[str, Any],
    to_jar: Mapping[str, Any],
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    expires_at: datetime,
    block_id: str | None = None,
) -> ConfirmBlock:
    """Khối xác nhận cho `move_between_jars`.

    `params` được chuẩn hóa ở đây và `params_hash` tính từ chính bản đã chuẩn hóa, nên khối luôn
    chứa đúng thứ sẽ được ký. `from_jar`/`to_jar` là dòng hũ hiện tại (code, name, balance_vnd).
    Ném `ParamsError` nếu tham số sai, `ValueError` nếu hũ không khớp tham số hoặc không đủ tiền
    (tool phải trả INSUFFICIENT_FUNDS trước khi tới đây).
    """
    if tool != MOVE_BETWEEN_JARS:
        raise ValueError(f"build_confirm chưa hỗ trợ tool {tool!r}")
    norm = normalize_params(tool, params)
    if from_jar["code"] != norm["from_jar"] or to_jar["code"] != norm["to_jar"]:
        raise ValueError("Hũ truyền vào không khớp tham số đã chuẩn hóa")
    amount = norm["amount_vnd"]
    before_from, before_to = to_vnd(from_jar["balance_vnd"]), to_vnd(to_jar["balance_vnd"])
    if before_from < amount:
        raise ValueError("Hũ nguồn không đủ số dư; không dựng khối xác nhận")
    digest = params_hash(tool, norm)
    summary = f"Chuyển {format_vnd(amount)} từ {from_jar['name']} sang {to_jar['name']}"
    return ConfirmBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"confirm:{trace_id}:{digest[:12]}",
        type="confirm",
        trace_id=trace_id,
        fallback_text=f"{summary}. Cần bạn xác nhận trên ứng dụng.",
        source=_source(source_tool, as_of, app_date),
        data=ConfirmData(
            tool=tool,
            params=MoveParams(**norm),
            params_hash=digest,
            summary=summary,
            preview=ConfirmPreview(
                from_=JarChange(
                    code=norm["from_jar"],
                    name=from_jar["name"],
                    before_vnd=before_from,
                    after_vnd=before_from - amount,
                ),
                to=JarChange(
                    code=norm["to_jar"],
                    name=to_jar["name"],
                    before_vnd=before_to,
                    after_vnd=before_to + amount,
                ),
            ),
            expires_at=format_instant(expires_at),
        ),
    )


def build_receipt(
    *,
    tool: str,
    transaction_id: str,
    occurred_at: datetime,
    app_date: date,
    amount_vnd: int | Decimal | str,
    from_jar: Mapping[str, Any],
    to_jar: Mapping[str, Any],
    trace_id: str,
    source_tool: str,
    block_id: str | None = None,
) -> ReceiptBlock:
    """Biên nhận. `from_jar`/`to_jar` là hũ sau khi commit (code, name, balance_vnd = số dư sau)."""
    if tool != MOVE_BETWEEN_JARS:
        raise ValueError(f"build_receipt chưa hỗ trợ tool {tool!r}")
    amount = to_vnd(amount_vnd)
    summary = f"Đã chuyển {format_vnd(amount)} từ {from_jar['name']} sang {to_jar['name']}"
    return ReceiptBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"receipt:{transaction_id}",
        type="receipt",
        trace_id=trace_id,
        fallback_text=f"{summary}.",
        source=_source(source_tool, occurred_at, app_date),
        data=ReceiptData(
            tool=tool,
            transaction_id=transaction_id,
            occurred_at=format_instant(occurred_at),
            app_date=app_date.isoformat(),
            amount_vnd=amount,
            summary=summary,
            from_jar=JarAfter(
                code=from_jar["code"],
                name=from_jar["name"],
                balance_after_vnd=to_vnd(from_jar["balance_vnd"]),
            ),
            to_jar=JarAfter(
                code=to_jar["code"],
                name=to_jar["name"],
                balance_after_vnd=to_vnd(to_jar["balance_vnd"]),
            ),
        ),
    )


def build_notice(
    *,
    kind: NoticeKind,
    title: str,
    message: str,
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    code: str | None = None,
    block_id: str | None = None,
    retryable: bool | None = None,
    degraded_reason: str | None = None,
    missing: Iterable[str] | None = None,
    suggestions: Iterable[Mapping[str, Any]] | None = None,
) -> NoticeBlock:
    """Thông báo trạng thái. `message` do code/cấu hình cung cấp, không chứa số liệu tài chính.

    Phase 3 (tùy chọn): `retryable` (nút "Thử lại"), `degraded_reason`, `missing` (phần còn thiếu khi trả một
    phần), `suggestions` (gợi ý việc làm được, mỗi phần tử có id, label, prompt)."""
    return NoticeBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"notice:{trace_id}:{code or kind}",
        type="notice",
        trace_id=trace_id,
        fallback_text=message,
        source=_source(source_tool, as_of, app_date),
        data=NoticeData(
            kind=kind,
            title=title,
            message=message,
            code=code,
            retryable=retryable,
            degraded_reason=degraded_reason,  # type: ignore[arg-type]
            missing=list(missing) if missing is not None else None,
            suggestions=[SuggestionItem(**x) for x in suggestions]
            if suggestions is not None
            else None,
        ),
    )


# --- dựng khối phase 2 ---------------------------------------------------------------------
def _clip(text: str, limit: int) -> str:
    """Cắt chuỗi hiển thị về `limit` ký tự (thêm dấu ba chấm nếu bị cắt)."""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _date_text(value: date | str) -> str:
    """`date` hoặc chuỗi YYYY-MM-DD thành chuỗi ngày hợp đồng."""
    return value.isoformat() if isinstance(value, date) else str(value)


def _dm(value: date | str) -> str:
    """'23/11' từ ngày YYYY-MM-DD (dùng trong câu hiển thị)."""
    d = value if isinstance(value, date) else date.fromisoformat(str(value))
    return f"{d.day:02d}/{d.month:02d}"


def _instant_text(value: datetime | str) -> str:
    """Thời điểm của hàng đọc từ Data API (datetime hoặc chuỗi `YYYY-MM-DD HH:MM:SS[.ffffff]` ở UTC,
    không hậu tố) thành RFC 3339 `...Z`."""
    if isinstance(value, datetime):
        return format_instant(value)
    text = str(value).strip().replace(" ", "T")
    if text.endswith("Z") or "+" in text[10:] or "-" in text[10:]:
        return format_instant(datetime.fromisoformat(text.replace("Z", "+00:00")))
    return format_instant(datetime.fromisoformat(text).replace(tzinfo=UTC))


def _ratio(value: Any) -> float:
    return float(Decimal(str(value)))


def build_confirm_action(
    *,
    tool: str,
    params: Mapping[str, Any],
    summary: str,
    changes: Iterable[Mapping[str, Any]],
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    expires_at: datetime,
    warnings: Iterable[str] = (),
    block_id: str | None = None,
) -> ConfirmActionBlock:
    """Khối xác nhận cho tool ghi KHÔNG phải chuyển hũ.

    `params` phải là bản ĐÃ chuẩn hóa theo hợp đồng (contracts/README.md, mục "Chuẩn hóa tham số"; việc
    chuẩn hóa từng tool nằm ở tầng ledger). `params_hash` tính từ chính bản này bằng
    `hash_normalized_params`, nên khối luôn chứa đúng thứ sẽ được ký. `changes` mỗi phần tử gồm
    `label`, `after` và tùy chọn `before` (chuỗi đã định dạng sẵn). Ném `ValueError` nếu tool không dùng khối này.
    """
    if tool not in GENERIC_ACTION_TOOLS:
        raise ValueError(f"build_confirm_action không hỗ trợ tool {tool!r}")
    digest = hash_normalized_params(tool, params)
    summary = _clip(summary, 120)
    return ConfirmActionBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"confirm:{trace_id}:{digest[:12]}",
        type="confirm_action",
        trace_id=trace_id,
        fallback_text=_clip(f"{summary}. Cần bạn xác nhận trên ứng dụng.", 280),
        source=_source(source_tool, as_of, app_date),
        data=ConfirmActionData(
            tool=tool,  # type: ignore[arg-type]
            params=dict(params),
            params_hash=digest,
            summary=summary,
            changes=[ActionChange(**c) for c in changes],
            warnings=list(warnings) or None,
            expires_at=format_instant(expires_at),
        ),
    )


def build_receipt_action(
    *,
    tool: str,
    occurred_at: datetime,
    app_date: date,
    summary: str,
    trace_id: str,
    source_tool: str,
    reference_id: str | None = None,
    amount_vnd: int | Decimal | str | None = None,
    jars_after: Iterable[Mapping[str, Any]] = (),
    details: Iterable[Mapping[str, str]] = (),
    follow_up: Mapping[str, Any] | None = None,
    block_id: str | None = None,
    coverage_change: CoverageChangeBlock | None = None,
) -> ReceiptActionBlock:
    """Biên nhận của tool ghi KHÔNG phải chuyển hũ. `jars_after`: mỗi hũ có code, name, balance_vnd (số dư sau,
    có thể âm với hũ Chưa phân loại). `details`: các dòng `{label, value}` đã định dạng. Ném `ValueError` nếu
    tool không dùng khối này."""
    if tool not in GENERIC_ACTION_TOOLS:
        raise ValueError(f"build_receipt_action không hỗ trợ tool {tool!r}")
    summary = _clip(summary, 120)
    return ReceiptActionBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"receipt:{tool}:{reference_id or trace_id}",
        type="receipt_action",
        trace_id=trace_id,
        fallback_text=_clip(f"{summary}.", 280),
        source=_source(source_tool, occurred_at, app_date),
        data=ReceiptActionData(
            tool=tool,  # type: ignore[arg-type]
            reference_id=reference_id,
            occurred_at=format_instant(occurred_at),
            app_date=app_date.isoformat(),
            amount_vnd=None if amount_vnd is None else to_vnd(amount_vnd),
            summary=summary,
            jars_after=[
                JarBalanceAfter(
                    code=j["code"], name=j["name"], balance_after_vnd=to_vnd(j["balance_vnd"])
                )
                for j in jars_after
            ],
            details=[ReceiptDetail(**d) for d in details],
            follow_up=ReceiptFollowUp(**follow_up) if follow_up else None,
            coverage_change=coverage_change,
        ),
    )


def _forecast_sentence(
    name: str,
    status: str,
    runout: date | str | None,
    payday: date | str,
    stale: bool,
    initial: bool,
) -> str:
    if status == "short" and runout:
        gap = (date.fromisoformat(_date_text(payday)) - date.fromisoformat(_date_text(runout))).days
        text = (
            f"Hũ {name} dự kiến cạn ngày {_dm(runout)}, còn {gap} ngày tới kỳ lương {_dm(payday)}."
        )
    elif status == "short":
        text = f"Hũ {name} dự kiến hụt trước kỳ lương {_dm(payday)}."
    elif status == "tight":
        text = f"Hũ {name} sát: dự kiến còn rất ít tiền trước kỳ lương {_dm(payday)}."
    else:
        text = f"Hũ {name} đủ tới kỳ lương {_dm(payday)}."
    if initial:
        text += " Đây là ước lượng ban đầu."
    if stale:
        text += " Số liệu đã cũ."
    return _clip(text, 280)


def build_forecast_timeline(
    *,
    jar: Mapping[str, Any],
    summary: Mapping[str, Any],
    days: Iterable[Mapping[str, Any]],
    events: Iterable[Mapping[str, Any]],
    stale: bool,
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    block_id: str | None = None,
) -> ForecastTimelineBlock:
    """Khối dự báo của MỘT hũ từ các hàng đọc ở DB, dùng chung cho màn hình và chat.

    - `jar`: code, name, color_key, icon_key.
    - `summary`: một hàng của `app_get_forecast_summaries` (computed_at, run_app_date, model, horizon_days,
      history_days, data_coverage, is_initial_estimate, start_balance_vnd, payday_date, days_to_payday,
      runout_date, p_shortfall, p_shortfall_se, status, confidence_band, show_probability).
    - `days`: các hàng của `app_get_forecast_series` (day, balance_p10_vnd, balance_p50_vnd, balance_p90_vnd).
    - `events`: mốc đã ghép từ nghĩa vụ và lịch lương, mỗi mốc có date, kind, label, amount_vnd, amount_max_vnd tùy chọn.
    - `p_shortfall` chỉ được phát khi `show_probability` đúng và có giá trị (quy tắc hiển thị của hợp đồng).
    Tiền Data API trả dạng chuỗi hoặc Decimal đều được; số âm giữ nguyên dấu.
    """
    show_p = bool(summary.get("show_probability")) and summary.get("p_shortfall") is not None
    runout = summary.get("runout_date")
    coverage = summary.get("data_coverage")
    payday = _date_text(summary["payday_date"])
    timeline_days = [
        ForecastDay(
            date=_date_text(d["day"]),
            p10_vnd=to_vnd(d["balance_p10_vnd"]),
            p50_vnd=to_vnd(d["balance_p50_vnd"]),
            p90_vnd=to_vnd(d["balance_p90_vnd"]),
        )
        for d in days
    ]
    event_rows = list(events)
    timeline_events = [
        {
            "date": _date_text(e["date"]),
            "kind": e["kind"],
            "label": e["label"],
            "amount_vnd": to_vnd(e["amount_vnd"]),
            **({"amount_max_vnd": to_vnd(e["amount_max_vnd"])} if e.get("amount_max_vnd") is not None else {}),
        }
        for e in event_rows
    ]
    opening_balance = to_vnd(summary["start_balance_vnd"])
    due_window = (
        ForecastObligationWindow.model_validate(obligation_window(
            (
                {**wire, "original_due_date": _date_text(raw["original_due_date"])}
                if raw.get("original_due_date") is not None else wire
                for wire, raw in zip(timeline_events, event_rows, strict=True)
            ),
            payday,
            {d.date: d.p50_vnd for d in timeline_days},
            opening_balance_vnd=opening_balance,
        ))
        if jar["code"] == DEFAULT_OBLIGATION_JAR and jar.get("kind") == "obligation" else None
    )
    data = ForecastTimelineData(
        jar=ForecastJar(
            code=jar["code"], name=jar["name"], color_key=jar["color_key"], icon_key=jar["icon_key"],
            purpose=jar.get("purpose"),
        ),
        status=summary["status"],
        origin_date=_date_text(summary["run_app_date"]),
        start_balance_vnd=opening_balance,
        horizon_days=int(summary["horizon_days"]),
        payday=ForecastPayday(date=payday, days_until=int(summary["days_to_payday"])),
        runout_date=_date_text(runout) if runout else None,
        p_shortfall=_ratio(summary["p_shortfall"]) if show_p else None,
        p_shortfall_se=(
            _ratio(summary["p_shortfall_se"])
            if show_p and summary.get("p_shortfall_se") is not None
            else None
        ),
        confidence_band=summary["confidence_band"],
        coverage=_ratio(coverage) if coverage is not None else None,
        history_days=int(summary["history_days"]),
        is_initial_estimate=bool(summary["is_initial_estimate"]),
        model=summary["model"],
        computed_at=_instant_text(summary["computed_at"]),
        stale=stale,
        days=timeline_days,
        events=[ForecastEvent.model_validate(e) for e in timeline_events[:60]],
        obligations_before_payday=due_window,
    )
    return build_forecast_timeline_from_data(
        data=data,
        trace_id=trace_id,
        source_tool=source_tool,
        as_of=as_of,
        app_date=app_date,
        block_id=block_id,
    )


def build_forecast_timeline_from_data(
    *,
    data: Mapping[str, Any] | ForecastTimelineData,
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    block_id: str | None = None,
) -> ForecastTimelineBlock:
    """Bọc `data` ĐÃ DỰNG (kết quả tool `forecast___get_forecast`, đúng `ForecastTimelineData`) thành khối `forecast_timeline`.

    Dùng ở agent: số trong khối là số của tool (không tính lại, không do LLM viết); `fallback_text` do code sinh từ chính `data`."""
    d = (
        data
        if isinstance(data, ForecastTimelineData)
        else ForecastTimelineData.model_validate(data)
    )
    if d.compare is not None:
        # Khối what-if: trường cấp trên là TRƯỚC, `compare.after` là SAU; câu thay thế nói về SAU.
        cmp = d.compare
        text = _clip(
            f"Nếu {cmp.label}: "
            + _forecast_sentence(
                d.jar.name, cmp.after.status, cmp.after.runout_date, d.payday.date, d.stale,
                d.is_initial_estimate,
            ),
            280,
        )  # fmt: skip
        window = cmp.after.obligations_before_payday
        default_id = f"forecast_timeline:{trace_id}:{d.jar.code}:what_if"
    else:
        text = _forecast_sentence(
            d.jar.name, d.status, d.runout_date, d.payday.date, d.stale, d.is_initial_estimate
        )
        window = d.obligations_before_payday
        default_id = f"forecast_timeline:{trace_id}:{d.jar.code}"
    if window is not None and (short := window.first_shortfall) is not None:
        notice = f" {short.label} ngày {_dm(short.date)} thiếu {format_vnd(short.shortfall_vnd)}."
        text = _clip(text, 280 - len(notice)) + notice
    return ForecastTimelineBlock(
        v=SCHEMA_VERSION,
        id=block_id or default_id,
        type="forecast_timeline",
        trace_id=trace_id,
        fallback_text=text,
        source=_source(source_tool, as_of, app_date),
        data=d,
    )


def build_proactive_card(
    *,
    kind: str,
    status: str,
    title: str,
    reason: str,
    actions: Iterable[Mapping[str, Any]],
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    jar_code: str | None = None,
    block_id: str | None = None,
    nudge_id: str | None = None,
) -> ProactiveCardBlock:
    """Thẻ chủ động (một việc). `title` và `reason` do code dựng từ số liệu thật, không do LLM viết;
    `actions` đứng đầu là hành động chính (mỗi phần tử: kind, label, jar_code tùy chọn, prompt tùy chọn).
    `nudge_id` (phase 5): id dòng `nudges` khi thẻ là bản tin của cổng giá trị, để "Để sau" và "Ít nhắc loại này" gửi phản hồi;
    thẻ chọn theo luật của Tổng quan (phase 2) không có."""
    return ProactiveCardBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"proactive_card:{trace_id}:{kind}",
        type="proactive_card",
        trace_id=trace_id,
        fallback_text=_clip(f"{title}. {reason}", 280),
        source=_source(source_tool, as_of, app_date),
        data=ProactiveCardData(
            kind=kind,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            title=title,
            reason=reason,
            jar_code=jar_code,
            nudge_id=nudge_id,
            actions=[ProactiveAction(**a) for a in actions],
        ),
    )


# --- dựng khối phase 3 ---------------------------------------------------------------------
_BAND_TEXT = {"high": "Cao", "medium": "Vừa", "low": "Thấp"}


def _data_model(model: type[Any], data: Any) -> Any:
    return data if isinstance(data, model) else model.model_validate(data)


def build_affordability_card(
    *,
    data: Mapping[str, Any] | AffordabilityCardData,
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    block_id: str | None = None,
) -> AffordabilityCardBlock:
    """Bọc `data` ĐÃ DỰNG (kết quả `forecast___affordability_check` hoặc `POST /affordability`, đúng
    `AffordabilityCardData`) thành khối. `fallback_text` là `headline` do engine dựng (có chữ đủ/sát/hụt)."""
    d = _data_model(AffordabilityCardData, data)
    return AffordabilityCardBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"affordability_card:{trace_id}",
        type="affordability_card",
        trace_id=trace_id,
        fallback_text=_clip(d.headline, 280),
        source=_source(source_tool, as_of, app_date),
        data=d,
    )


def build_obligation_impact(
    *,
    data: Mapping[str, Any] | ObligationImpactData,
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    block_id: str | None = None,
) -> ObligationImpactBlock:
    """Bọc `ObligationImpactData` (từ `run_scenario`) thành khối. Id theo ngày đến hạn."""
    d = _data_model(ObligationImpactData, data)
    return ObligationImpactBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"obligation_impact:{trace_id}:{d.cost.due_date}",
        type="obligation_impact",
        trace_id=trace_id,
        fallback_text=_clip(d.headline, 280),
        source=_source(source_tool, as_of, app_date),
        data=d,
    )


def build_options(
    *,
    data: Mapping[str, Any] | OptionsData,
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    block_id: str | None = None,
) -> OptionsBlock:
    """Khối phương án. `fallback_text` liệt kê nhãn các phương án (không có số do LLM viết)."""
    d = _data_model(OptionsData, data)
    labels = "; ".join(o.label for o in d.options)
    return OptionsBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"options:{trace_id}",
        type="options",
        trace_id=trace_id,
        fallback_text=_clip(f"Có {len(d.options)} phương án: {labels}.", 280),
        source=_source(source_tool, as_of, app_date),
        data=d,
    )


def build_explain(
    *,
    data: Mapping[str, Any] | ExplainData,
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    block_id: str | None = None,
) -> ExplainBlock:
    """Khối "Vì sao" dựng từ bản ghi lượt. `trace_id` là của yêu cầu hiện tại; `subject_trace_id` trong `data` là
    của câu trả lời được giải thích."""
    d = _data_model(ExplainData, data)
    used = ", ".join(x.label for x in d.data_used[:3])
    text = f"Dữ liệu đã dùng: {used}. Độ tin cậy: {_BAND_TEXT[d.confidence.band]}."
    return ExplainBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"explain:{d.subject_trace_id}",
        type="explain",
        trace_id=trace_id,
        fallback_text=_clip(text, 280),
        source=_source(source_tool, as_of, app_date),
        data=d,
    )


def build_clarify(
    *,
    question: str,
    slot: str,
    chips: Iterable[Mapping[str, Any]],
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    pending_intent: str | None = None,
    allow_free_text: bool | None = None,
    block_id: str | None = None,
) -> ClarifyBlock:
    """Khối hỏi lại: đúng một câu hỏi kèm chip trả lời."""
    return ClarifyBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"clarify:{trace_id}",
        type="clarify",
        trace_id=trace_id,
        fallback_text=_clip(question, 280),
        source=_source(source_tool, as_of, app_date),
        data=ClarifyData(
            question=question,
            slot=slot,  # type: ignore[arg-type]
            chips=[ClarifyChip(**c) for c in chips],
            pending_intent=pending_intent,  # type: ignore[arg-type]
            allow_free_text=allow_free_text,
        ),
    )


def build_suggestions(
    *,
    context: str,
    items: Iterable[Mapping[str, Any]],
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    title: str | None = None,
    can_do: Iterable[str] | None = None,
    cannot_do: Iterable[str] | None = None,
    block_id: str | None = None,
) -> SuggestionsBlock:
    """Khối gợi ý bấm được. Nội dung do cấu hình hoặc code cung cấp."""
    rows = [SuggestionItem(**i) for i in items]
    text = title or "Gợi ý: " + ", ".join(r.label for r in rows) + "."
    return SuggestionsBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"suggestions:{trace_id}:{context}",
        type="suggestions",
        trace_id=trace_id,
        fallback_text=_clip(text, 280),
        source=_source(source_tool, as_of, app_date),
        data=SuggestionsData(
            context=context,  # type: ignore[arg-type]
            title=title,
            can_do=list(can_do) if can_do is not None else None,
            cannot_do=list(cannot_do) if cannot_do is not None else None,
            items=rows,
        ),
    )


# --- dựng khối phase 4 ---------------------------------------------------------------------
def build_resilience_score(
    *,
    data: Mapping[str, Any] | ResilienceScoreData,
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    block_id: str | None = None,
) -> ResilienceScoreBlock:
    """Bọc `data` ĐÃ DỰNG (kết quả `forecast___get_resilience_score` hoặc `GET /resilience`) thành khối. `fallback_text` là
    `headline` do code dựng (có điểm, nhóm bằng chữ và thành phần yếu nhất)."""
    d = _data_model(ResilienceScoreData, data)
    return ResilienceScoreBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"resilience_score:{trace_id}",
        type="resilience_score",
        trace_id=trace_id,
        fallback_text=_clip(d.headline, 280),
        source=_source(source_tool, as_of, app_date),
        data=d,
    )


def build_stress_result(
    *,
    data: Mapping[str, Any] | StressResultData,
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    block_id: str | None = None,
) -> StressResultBlock:
    """Bọc `data` (kết quả `forecast___stress_test` hoặc `POST /resilience/stress`) thành khối. Id theo cú sốc."""
    d = _data_model(StressResultData, data)
    return StressResultBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"stress_result:{trace_id}:{d.shock.shock_id}",
        type="stress_result",
        trace_id=trace_id,
        fallback_text=_clip(d.headline, 280),
        source=_source(source_tool, as_of, app_date),
        data=d,
    )


def build_roadmap(
    *,
    data: Mapping[str, Any] | RoadmapData,
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    block_id: str | None = None,
) -> RoadmapBlock:
    """Bọc `RoadmapData` (kết quả `planner___save_roadmap`, `planner___get_roadmap` hoặc `GET /roadmap`) thành khối."""
    d = _data_model(RoadmapData, data)
    return RoadmapBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"roadmap:{trace_id}:v{d.version}",
        type="roadmap",
        trace_id=trace_id,
        fallback_text=_clip(d.headline, 280),
        source=_source(source_tool, as_of, app_date),
        data=d,
    )


def build_roadmap_diff(
    *,
    data: Mapping[str, Any] | RoadmapDiffData,
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    block_id: str | None = None,
) -> RoadmapDiffBlock:
    """Bọc `RoadmapDiffData` (`GET /roadmap/diff`) thành khối."""
    d = _data_model(RoadmapDiffData, data)
    return RoadmapDiffBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"roadmap_diff:{trace_id}:v{d.from_version}-v{d.to_version}",
        type="roadmap_diff",
        trace_id=trace_id,
        fallback_text=_clip(d.headline, 280),
        source=_source(source_tool, as_of, app_date),
        data=d,
    )


def build_review_list(
    *,
    data: Mapping[str, Any] | ReviewListData,
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    block_id: str | None = None,
) -> ReviewListBlock:
    """Bọc `ReviewListData` (`GET /review`) thành khối. Id theo chế độ để A1 và A2 không đè nhau trong một lượt."""
    d = _data_model(ReviewListData, data)
    return ReviewListBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"review_list:{trace_id}:{d.mode}",
        type="review_list",
        trace_id=trace_id,
        fallback_text=_clip(d.headline, 280),
        source=_source(source_tool, as_of, app_date),
        data=d,
    )


# --- dựng khối phase 5 ---------------------------------------------------------------------
def behavior_insight_data(
    profile: Mapping[str, Any] | BehaviorProfileData, insight_id: str | None = None
) -> BehaviorInsightData:
    """Rút `data` của khối `behavior_insight` từ hồ sơ ĐÃ SẴN SÀNG (kết quả `forecast___get_behavior_profile` hoặc
    `GET /profile/behavior`): nhận xét `insight_id` (vắng: nhận xét đầu tiên, tức quan trọng nhất) và việc cần làm của hồ sơ.
    Hồ sơ chưa sẵn sàng hoặc không có nhận xét đó thì `ValueError` (agent trả câu "chưa đủ dữ liệu" thay vì khối)."""
    p = _data_model(BehaviorProfileData, profile)
    if not p.ready or p.next_step is None or p.computed_at is None:
        raise ValueError("hồ sơ hành vi chưa sẵn sàng")
    found = next((i for i in p.insights if insight_id in (None, i.insight_id)), None)
    if found is None:
        raise ValueError(f"không có nhận xét {insight_id!r} trong hồ sơ")
    return BehaviorInsightData(
        insight=found,
        next_step=p.next_step,
        app_date=p.app_date,
        computed_at=p.computed_at,
        history_days=p.history_days,
        config_version=p.config_version,
    )


def build_behavior_insight(
    *,
    data: Mapping[str, Any] | BehaviorInsightData,
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    block_id: str | None = None,
) -> BehaviorInsightBlock:
    """Bọc `BehaviorInsightData` (thường từ `behavior_insight_data`) thành khối. `fallback_text` là câu nhận xét kèm việc cần
    làm, cả hai do code hoặc batch đêm dựng (đã qua NumericGrounding), LLM của lượt chat không viết."""
    d = _data_model(BehaviorInsightData, data)
    return BehaviorInsightBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"behavior_insight:{trace_id}:{d.insight.insight_id}",
        type="behavior_insight",
        trace_id=trace_id,
        fallback_text=_clip(f"{d.insight.headline} Việc nên làm: {d.next_step.label}.", 280),
        source=_source(source_tool, as_of, app_date),
        data=d,
    )


#: Tool mà khối `citation` lấy nguồn (khối không có đường dẫn nào khác).
CITATION_SOURCE_TOOL = "knowledge___get_fee_schedule"
CITATION_MAX_ITEMS = 5


def citation_data(fee_schedule: Mapping[str, Any] | FeeScheduleData, fee_types: Iterable[str] | None = None) -> CitationData:
    """Rút `data` của khối `citation` từ `FeeScheduleData` (`data` của `knowledge___get_fee_schedule`): gom các dòng phí theo
    (tên nguồn, đường dẫn, ngày hiệu lực) theo thứ tự xuất hiện, mỗi nhóm một mục với các loại phí của nó; tối đa 5 nguồn đầu.
    `fee_types` (vắng: mọi dòng) chỉ giữ các loại phí câu trả lời nhắc tới; loại không có trong kết quả thì `ValueError` (agent
    không trích dẫn được phí mà tool không trả). `excerpt` là `condition_note` của dòng khi nguồn chỉ có một loại phí."""
    fs = _data_model(FeeScheduleData, fee_schedule)
    lines = list(fs.fees)
    if fee_types is not None:
        wanted = list(dict.fromkeys(fee_types))
        known = {f.fee_type for f in lines}
        missing = [t for t in wanted if t not in known]
        if missing or not wanted:
            raise ValueError(f"không có loại phí {missing or wanted!r} trong kết quả get_fee_schedule")
        lines = [f for f in lines if f.fee_type in wanted]
    groups: dict[tuple[str, str, str], list[FeeLine]] = {}
    for f in lines:
        groups.setdefault((f.source_name, f.source_url, f.effective_from), []).append(f)
    items = []
    for (name, url, eff), fees in list(groups.items())[:CITATION_MAX_ITEMS]:
        note = fees[0].condition_note if len(fees) == 1 else None
        items.append(
            CitationItem(
                fee_types=[f.fee_type for f in fees],
                source_name=name,
                source_url=url,
                effective_from=eff,
                excerpt=note or None,
            )
        )
    return CitationData(product_code=fs.product_code, product_label=fs.product_label, items=items)


def build_citation(
    *,
    result: Mapping[str, Any] | GetFeeScheduleOk,
    trace_id: str,
    fee_types: Iterable[str] | None = None,
    block_id: str | None = None,
) -> CitationBlock:
    """Dựng khối `citation` từ kết quả OK của `knowledge___get_fee_schedule` (cả `status`, `as_of`, `app_date`, `data`): nguồn
    của khối là chính lần gọi tool đó, mục là `citation_data(result.data, fee_types)`. `fallback_text` nêu nguồn đầu tiên và
    ngày hiệu lực; không có số tiền (số nằm ở câu trả lời, lấy từ `amount_vnd`)."""
    r = _data_model(GetFeeScheduleOk, result)
    d = citation_data(r.data, fee_types)
    first = d.items[0]
    more = f" và {len(d.items) - 1} nguồn khác" if len(d.items) > 1 else ""
    since = "/".join(reversed(first.effective_from.split("-")))
    text = f"Nguồn biểu phí {d.product_label}: {first.source_name}, hiệu lực từ {since}{more}."
    return CitationBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"citation:{trace_id}",
        type="citation",
        trace_id=trace_id,
        fallback_text=_clip(text, 280),
        source=Source(tool=CITATION_SOURCE_TOOL, as_of=r.as_of, app_date=r.app_date),
        data=d,
    )


def build_reasoning(
    *,
    data: Mapping[str, Any] | ReasoningData,
    trace_id: str,
    source_tool: str,
    as_of: datetime,
    app_date: date,
    block_id: str | None = None,
) -> ReasoningBlock:
    """Bọc `data` ĐÃ KIỂM (bước đã qua NumericGrounding, căn cứ hợp lệ, kết luận khớp phương án hay bước) thành khối. Agent phát nhiều
    bản cùng id (`reasoning:{trace_id}`): bản chưa xong thêm từng bước, bản cuối có kết luận. `fallback_text` do code dựng, chỉ đếm
    số bước: chữ của bước và kết luận là lời model viết, không đưa vào `fallback_text`."""
    d = _data_model(ReasoningData, data)
    n = len(d.steps)
    if not d.complete:
        text = "Yofina đang cân nhắc số liệu của bạn."
    elif d.conclusion is not None and n:
        text = f"Yofina đã cân nhắc {n} điều trước khi đưa ra gợi ý."
    elif d.conclusion is not None:
        text = "Yofina có một gợi ý cho bạn."
    else:
        text = f"Yofina đã cân nhắc {n} điều từ số liệu của bạn."
    return ReasoningBlock(
        v=SCHEMA_VERSION,
        id=block_id or f"reasoning:{trace_id}",
        type="reasoning",
        trace_id=trace_id,
        fallback_text=_clip(text, 280),
        source=_source(source_tool, as_of, app_date),
        data=d,
    )
