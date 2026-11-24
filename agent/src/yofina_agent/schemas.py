"""Kiểu dữ liệu của harness phase 3 (chỉ KIỂU, chưa nối vào luồng agent): ý định, kế hoạch, phân tích, phán quyết.

Luồng (xem docs/plan/phases/phase-3-what-if-va-kiem-tra.md, luồng B):

    L1 Router  -> `IntentResult`            (model nhỏ, ép tool)
    L2 Orchestrator -> `Plan`               (dựng ScenarioSpec, chọn tool đọc; giới hạn do cấu hình)
    L3 Analyst -> `Analysis`                (diễn giải, 2 đến 3 phương án; chỉ thấy bản gọn kết quả tool)
    L4 Verifier -> `Verdict`                (NumericGrounding + check_suitability từng phương án; mã Python)

Nguyên tắc: không giá trị mặc định cho thứ thuộc cấu hình (số vòng, số token, số lần thử): chúng là trường bắt buộc, do
cấu hình điền. Khác `router.RouterOutput` của phase 1 (bốn ý định cũ), `IntentResult` là hợp đồng của phase 3; luồng B
chuyển router sang kiểu này.
"""

from __future__ import annotations

import ast
import json
import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from yofina_core.blocks import ActionToolName, BehaviorInsightKind, ClarifySlot, JarCode, OptionKind, RuleId
from yofina_core.scenario import SCENARIO_ADAPTER, ScenarioSpec
from yofina_core.suitability import Proposal, SuitabilityVerdict
from yofina_core.wallet import INTENTS

# Phase 3 có bảy ý định; phase 4 thêm `resilience`, `stress`, `roadmap`; phase 5 thêm `behavior`, `knowledge`, `ingest`, `memory`
# (khớp `wallet.INTENTS`, cùng thứ tự với CHECK của migration 0053).
Intent = Literal[
    "lookup", "what_if", "affordability", "profile_update", "move", "out_of_scope", "chitchat",
    "resilience", "stress", "roadmap",
    "behavior", "knowledge", "ingest", "memory",
]  # fmt: skip

#: Tool ĐỌC mà Orchestrator được đặt vào kế hoạch (tên đầy đủ qua Gateway). Tool ghi KHÔNG ở đây: ghi luôn đi qua khối
#: xác nhận và token (ADR-0002), không nằm trong kế hoạch do model dựng.
PLAN_TOOLS = (
    "ledger___get_jar_balances",
    "ledger___query_transactions",
    "ledger___get_cashflow_summary",
    "ledger___get_obligations",
    "forecast___get_forecast",
    "forecast___run_scenario",
    "forecast___affordability_check",
    "knowledge___get_fee_schedule",
    "planner___check_suitability",
)
PlanToolName = Literal[
    "ledger___get_jar_balances",
    "ledger___query_transactions",
    "ledger___get_cashflow_summary",
    "ledger___get_obligations",
    "forecast___get_forecast",
    "forecast___run_scenario",
    "forecast___affordability_check",
    "knowledge___get_fee_schedule",
    "planner___check_suitability",
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- L1: IntentResult ------------------------------------------------------------------------
class ClarifyChipIn(_Model):
    label: Annotated[str, Field(min_length=1, max_length=40)]
    value: Annotated[str, Field(min_length=1, max_length=80)] | None = None


class ClarifyRequest(_Model):
    """Một câu hỏi lại. Router chỉ được hỏi MỘT câu (một dấu hỏi)."""

    slot: ClarifySlot
    question: Annotated[str, Field(min_length=1, max_length=200)]
    chips: Annotated[list[ClarifyChipIn], Field(max_length=6)] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_question(self) -> ClarifyRequest:
        if self.question.count("?") > 1:
            raise ValueError("chỉ hỏi đúng một câu")
        return self


LookupKind = Literal["balance", "transactions", "forecast", "obligations"]
ObligationKind = Literal["rent", "bill", "subscription", "loan"]


class IntentParams(_Model):
    """Tham số người dùng nói (router không đoán). Tên hũ giữ nguyên chữ họ gõ."""

    lookup_kind: LookupKind | None = (
        None  # chỉ với intent `lookup`: tra số dư, giao dịch, dự báo một hũ hay nghĩa vụ
    )
    jar_text: str | None = None
    from_jar_text: str | None = None
    to_jar_text: str | None = None
    amount_vnd: Annotated[int, Field(ge=1)] | None = None
    funding: Literal["jar", "credit"] | None = None
    scenario_kind: Literal[
        "one_time_purchase", "bnpl_purchase", "income_change", "recurring_expense",
        "jar_transfer", "goal_delay",
    ] | None = None  # fmt: skip
    date_text: str | None = None
    label: Annotated[str, Field(max_length=80)] | None = None
    days_back: Annotated[int, Field(ge=1)] | None = None
    limit: Annotated[int, Field(ge=1)] | None = None
    # khai báo hồ sơ bằng chat (profile_update): lương, ngày nhận lương, hoặc MỘT khoản nghĩa vụ
    salary_vnd: Annotated[int, Field(ge=1)] | None = None
    payday_day: Annotated[int, Field(ge=1, le=31)] | None = None
    obligation_name: Annotated[str, Field(max_length=80)] | None = None
    obligation_kind: ObligationKind | None = None
    due_day: Annotated[int, Field(ge=1, le=31)] | None = None
    # what_if: người dùng vừa trả lời câu "vẫn giữ khoản trước để tính gộp không": true giữ, false bỏ, null khi không có câu hỏi đó
    keep_previous: bool | None = None
    shock_id: str | None = None  # stress: handler kiểm mã cú sốc theo cấu hình cú sốc
    # roadmap: xem, lập/lập lại, hoặc sửa một bước của bản đang dùng. Mục tiêu người dùng nói dùng lại amount_vnd (số tiền mục tiêu),
    # jar_text (hũ, giữ chữ họ gõ) và date_text (cụm chỉ hạn họ nói, ví dụ "cuối tháng này"); handler đổi hũ và ngày bằng mã.
    # Sửa bước: amount_vnd là số tiền mới người dùng muốn (nếu nói).
    roadmap_action: Literal["view", "create", "edit_step"] | None = None
    # Ý định phụ do router trích (thay cho đoán bằng từ khóa trên chữ): loại nhận xét hành vi, loại phí được hỏi, hỏi cách nạp hay lần nạp.
    insight_kind: BehaviorInsightKind | None = None  # behavior; null khi hỏi chung về thói quen
    fee_topic: Literal["monthly", "per_transaction", "once", "late", "other"] | None = None  # knowledge; null khi hỏi chung biểu phí
    ingest_action: Literal["how_to", "status"] | None = None  # ingest; null thì xem lần nạp gần nhất
    # Số tiền người dùng nói bằng NGOẠI TỆ: router không quy đổi (amount_vnd để null); `fx_chat.convert_foreign_amount` gọi
    # `knowledge___get_exchange_rate` và điền amount_vnd từ kết quả tool. currency là mã ISO 4217, amount_original là số theo ngoại tệ.
    currency: str | None = None
    amount_original: Annotated[float, Field(gt=0)] | None = None

    @field_validator("currency", mode="before")
    @classmethod
    def _currency_code(cls, value: Any) -> Any:
        """Mã ngoại tệ ba chữ in hoa; VND hay giá trị không phải mã thì coi như không có (số tiền khi đó là VND như mọi câu khác)."""
        code = value.strip().upper() if isinstance(value, str) else None
        return code if code and re.fullmatch(r"[A-Z]{3}", code) and code != "VND" else None


class IntentResult(_Model):
    intent: Intent
    params: IntentParams
    confidence: Annotated[float, Field(ge=0, le=1)]
    needs_clarification: bool
    clarify: ClarifyRequest | None = None
    reply: Annotated[str, Field(max_length=400)] | None = None

    @field_validator("params", mode="before")
    @classmethod
    def _params_lenient(cls, value: Any) -> Any:
        """Model nhỏ đôi khi trả `params` thành CHUỖI (JSON hoặc dạng Python có `None`) hoặc null: đọc lại thay vì bắt thử lại."""
        if value is None:
            return {}
        if isinstance(value, str):
            text = re.sub(
                r"\bnull\b",
                "None",
                re.sub(r"\btrue\b", "True", re.sub(r"\bfalse\b", "False", value)),
            )
            try:
                parsed = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                try:
                    parsed = json.loads(value)
                except ValueError:
                    return value
            return parsed if isinstance(parsed, dict) else value
        return value

    def _pays_from_one_jar(self) -> bool:
        """Ý định mà tiền đi ra từ MỘT hũ (không phải chuyển giữa hai hũ): kiểm tra chi tiêu và what-if mua hàng hay khoản lặp lại.
        what-if chưa rõ loại thì chỉ tính khi không có hũ đích (có thể là chuyển hũ)."""
        p = self.params
        if self.intent == "affordability":
            return True
        if self.intent != "what_if":
            return False
        if p.scenario_kind in ("one_time_purchase", "bnpl_purchase", "recurring_expense"):
            return True
        return p.scenario_kind is None and p.to_jar_text is None

    @model_validator(mode="after")
    def _consistent(self) -> IntentResult:
        p = self.params
        if (
            self.intent == "what_if"
            and p.scenario_kind == "income_change"
            and p.amount_vnd is None
            and p.salary_vnd is not None
        ):
            # Model nhỏ hay đặt "lương mới" vào salary_vnd (ô của profile_update). Cùng một con số người dùng đã nói,
            # chỉ sai ô: chuyển sang amount_vnd thay vì hỏi lại số tiền họ vừa nói.
            p.amount_vnd, p.salary_vnd = p.salary_vnd, None
        if self._pays_from_one_jar() and (p.from_jar_text or p.to_jar_text):
            # Khoản mua hoặc khoản chi trả từ MỘT hũ (mã đọc jar_text). Model nhỏ hay đặt "từ hũ X" vào from_jar_text và người nhận
            # vào to_jar_text, khiến mã hỏi lại hũ dù người dùng đã nói, hoặc coi tên người nhận là hũ lạ. Dời đúng chữ họ gõ sang ô đúng.
            if p.jar_text is None and p.from_jar_text:
                p.jar_text = p.from_jar_text
            if p.label is None and p.to_jar_text:
                p.label = p.to_jar_text[:80]
            p.from_jar_text = p.to_jar_text = None
        if self.intent == "roadmap" and (p.from_jar_text or p.to_jar_text):
            # "gom đủ 1 tỷ trong hũ Du lịch": model nhỏ hay coi hũ mục tiêu là hũ đích. Lộ trình chỉ có MỘT hũ mục tiêu (jar_text).
            if p.jar_text is None:
                p.jar_text = p.to_jar_text or p.from_jar_text
            p.from_jar_text = p.to_jar_text = None
        if self.needs_clarification != (self.clarify is not None):
            raise ValueError("needs_clarification đúng khi và chỉ khi có `clarify`")
        return self


# --- L2: Plan --------------------------------------------------------------------------------
class PlanLimits(_Model):
    """Giới hạn của lượt; KHÔNG có mặc định: giá trị đến từ cấu hình (nhóm `harness`)."""

    max_rounds: Annotated[int, Field(ge=1)]
    max_tokens: Annotated[int, Field(ge=1)]
    max_model_calls: Annotated[int, Field(ge=1)]


class PlanStep(_Model):
    tool: PlanToolName
    args: dict[str, Any]
    parallel_group: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _no_user_id(self) -> PlanStep:
        """`user_id` do interceptor ghi đè từ JWT; kế hoạch không được mang nó (kể cả user_id của người khác)."""
        if "user_id" in self.args or "confirm_token" in self.args:
            raise ValueError("args không được có user_id hoặc confirm_token")
        return self


class Plan(_Model):
    intent: Literal["what_if", "affordability", "lookup"]
    scenario: dict[str, Any] | None = None
    steps: Annotated[list[PlanStep], Field(min_length=1, max_length=8)]
    limits: PlanLimits

    @model_validator(mode="after")
    def _scenario_is_valid(self) -> Plan:
        """what_if cần một ScenarioSpec hợp lệ (kiểm bằng model của `yofina_core.scenario`); intent khác thì không có."""
        if self.intent == "what_if":
            if self.scenario is None:
                raise ValueError("what_if cần scenario")
            SCENARIO_ADAPTER.validate_python(self.scenario)
        elif self.scenario is not None:
            raise ValueError("chỉ what_if mới có scenario")
        return self

    def scenario_spec(self) -> ScenarioSpec | None:
        """ScenarioSpec đã kiểm (None nếu không phải what_if)."""
        return None if self.scenario is None else SCENARIO_ADAPTER.validate_python(self.scenario)


# --- L3: Analysis ----------------------------------------------------------------------------
class OptionActionSpec(_Model):
    """Việc ghi mà phương án muốn dẫn tới. Agent gọi tool KHÔNG token để lấy khối xác nhận; Analyst không tạo token."""

    tool: ActionToolName
    params: dict[str, Any]


class AnalysisOption(_Model):
    option_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
    kind: OptionKind
    label: Annotated[str, Field(min_length=1, max_length=60)]
    summary: Annotated[str, Field(min_length=1, max_length=200)]
    proposal: Proposal
    action: OptionActionSpec | None = None
    jar_code: JarCode | None = None
    recommended: bool | None = None


#: Mã căn cứ của một bước lập luận: `tool:<tên ngắn>` hoặc `rule:<rule_id>`, chọn trong danh sách `<can_cu>` của prompt.
BasisKey = Annotated[str, Field(pattern=r"^(tool|rule):[a-z][a-z0-9_]{0,63}$")]
AdvicePersonal = Literal["memory", "behavior"]


class ReasoningStepIn(_Model):
    """Một bước lập luận model trả về NHƯ DỮ LIỆU (luồng K của phase 6), không phải suy nghĩ thô. Mã kiểm số từng câu và căn cứ
    rồi mới phát (`advisor.py`); bước có số không căn cứ hoặc không có căn cứ hợp lệ bị bỏ."""

    seen: Annotated[str, Field(min_length=1, max_length=160)]
    why: Annotated[str, Field(min_length=1, max_length=160)]
    effect: Annotated[str, Field(min_length=1, max_length=160)]
    basis: Annotated[list[BasisKey], Field(min_length=1, max_length=3)]


class OptionConclusionIn(_Model):
    """Câu kết luận của what-if: nên làm gì và vì sao, theo phương án được gợi ý (`option_id`)."""

    text: Annotated[str, Field(min_length=1, max_length=240)]
    option_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
    personal: Annotated[list[AdvicePersonal], Field(max_length=2)] = Field(default_factory=list)


class Analysis(_Model):
    reasoning: Annotated[list[ReasoningStepIn], Field(max_length=5)] = Field(default_factory=list)
    narrative: Annotated[str, Field(min_length=1, max_length=800)]
    options: Annotated[list[AnalysisOption], Field(min_length=2, max_length=3)]
    conclusion: OptionConclusionIn | None = None
    follow_ups: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=200)]], Field(max_length=3)
    ] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> Analysis:
        ids = [o.option_id for o in self.options]
        if len(set(ids)) != len(ids):
            raise ValueError("option_id phải duy nhất")
        return self


# --- L4: Verdict -----------------------------------------------------------------------------
class UngroundedNumber(_Model):
    """Một con số trong văn bản không có trong kết quả tool của lượt."""

    text: Annotated[str, Field(min_length=1, max_length=60)]
    value_vnd: int | None = None
    context: Annotated[str, Field(max_length=200)] | None = None


class GroundingResult(_Model):
    ok: bool
    checked_count: Annotated[int, Field(ge=0)]
    ungrounded: list[UngroundedNumber] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> GroundingResult:
        if self.ok != (len(self.ungrounded) == 0):
            raise ValueError("ok đúng khi và chỉ khi không có số nào thiếu căn cứ")
        return self


class OptionSuitability(_Model):
    option_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
    verdict: SuitabilityVerdict


class Verdict(_Model):
    """Phán quyết của Verifier. `action` do mã quyết định theo số lần thử còn lại (cấu hình):
    pass: phát; retry: trả `feedback` cho Analyst sửa; fallback: hết vòng, chỉ phát khối số liệu tất định và một notice."""

    ok: bool
    grounding: GroundingResult
    suitability: list[OptionSuitability]
    feedback: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=300)]], Field(max_length=10)
    ] = Field(default_factory=list)
    failed_rules: list[RuleId] = Field(default_factory=list)
    attempt: Annotated[int, Field(ge=1)]
    action: Literal["pass", "retry", "fallback"]

    @model_validator(mode="after")
    def _consistent(self) -> Verdict:
        expected_ok = self.grounding.ok and all(s.verdict.ok for s in self.suitability)
        if self.ok != expected_ok:
            raise ValueError("ok phải bằng grounding.ok và mọi suitability.ok")
        if (self.action == "pass") != self.ok:
            raise ValueError("action pass đúng khi và chỉ khi ok")
        if not self.ok and not self.feedback:
            raise ValueError("không ok thì phải có feedback có cấu trúc cho Analyst")
        return self


__all__ = [
    "INTENTS",
    "PLAN_TOOLS",
    "Analysis",
    "AnalysisOption",
    "BasisKey",
    "ClarifyChipIn",
    "ClarifyRequest",
    "GroundingResult",
    "Intent",
    "IntentParams",
    "LookupKind",
    "ObligationKind",
    "IntentResult",
    "OptionActionSpec",
    "OptionConclusionIn",
    "OptionSuitability",
    "Plan",
    "PlanLimits",
    "PlanStep",
    "ReasoningStepIn",
    "UngroundedNumber",
    "Verdict",
]
