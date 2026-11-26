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
import copy
import json
import logging
import re
from collections.abc import Mapping
from decimal import Decimal
from functools import cache
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, WithJsonSchema, field_validator, model_validator

from yofina_core import dates as D
from yofina_core.blocks import (
    ActionToolName,
    BehaviorInsightKind,
    ClarifySlot,
    JarCode,
    OptionKind,
    RuleId,
)
from yofina_core.scenario import SCENARIO_ADAPTER, ScenarioSpec
from yofina_core.suitability import Proposal, SuitabilityVerdict
from yofina_core.wallet import INTENTS, SPENDING_TX_TYPES, TX_TYPE_BNPL_PURCHASE

log = logging.getLogger("yofina.agent.schemas")

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
    "knowledge___resolve_date",
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
    "knowledge___resolve_date",
    "planner___check_suitability",
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- đặc tả ngày model điền (router, Orchestrator) ----------------------------------------------------
#: Nghĩa của đặc tả ngày cho model, theo nghĩa của từng trường (mốc, kỳ, độ lệch, trước mốc), không câu mẫu: là `description` của
#: schema mọi trường đặc tả ngày (router, Orchestrator), nên mọi vai model đọc cùng một chỗ.
DATE_SPEC_DESCRIPTION = (
    "Đặc tả một ngày để hệ thống tính bằng phép tính lịch tất định (độ dài tháng, năm nhuận, quý, Tết âm lịch); bạn không tự đổi ra "
    "ngày. anchor là mốc: today là hôm nay; next_payday là ngày nhận lương kế tiếp; start_of và end_of là ngày đầu và ngày cuối của "
    "kỳ period (week từ thứ Hai tới Chủ nhật, month, quarter là ba tháng bắt đầu từ tháng 1, 4, 7, 10, year); lunar_new_year là Mùng "
    "1 Tết âm lịch; date là một ngày trong tháng (day). period_offset đếm kỳ từ kỳ chứa hôm nay (0 kỳ này, 1 kỳ kế tiếp, -1 kỳ trước) "
    "và chỉ có nghĩa khi có period. Mỗi mốc chỉ nhận trường của nó: today và next_payday không nhận trường nào ngoài offset và before; "
    "start_of và end_of cần period; lunar_new_year nhận lunar_year (năm dương lịch chứa Mùng 1 đó, khi người dùng nêu số năm) hoặc "
    "period year cùng period_offset (khi họ nói năm theo cách tương đối), không nhận cả hai, hoặc không nhận gì (lần Tết gần nhất); "
    "date cần day, còn tháng và năm của ngày đó nêu bằng month và year (khi người dùng nêu) hoặc bằng period cùng period_offset: period "
    "month thay cho cả month và year, period year thay cho year và vẫn cần month. Mốc không nêu năm (hoặc tháng) thì hệ thống lấy lần "
    "gần nhất sau hôm nay. offset là khoảng thời gian cộng vào mốc (years, months, weeks, days; được âm, được có phần lẻ). before là "
    "true khi ngày cần là ngày liền trước ngày tính được, tức trước mốc và không gồm chính mốc. Chỉ đưa trường có nghĩa với câu: trường "
    "không dùng thì bỏ hoặc để null, không điền 0 hay false cho đủ."
)


def _number_offsets(node: Any) -> Any:
    """Phần độ lệch của `DateSpec` là `Decimal` (schema Pydantic: số hoặc chuỗi): model chỉ được điền số."""
    if isinstance(node, list):
        return [_number_offsets(x) for x in node]
    if not isinstance(node, dict):
        return node
    if "anyOf" in node:
        kinds = [o.get("type") for o in node["anyOf"]]
        if "number" in kinds and "string" in kinds:
            node = {**node, "anyOf": [o for o in node["anyOf"] if o.get("type") != "string"]}
    return {k: _number_offsets(v) for k, v in node.items()}


@cache
def _date_spec_object_schema() -> dict[str, Any]:
    """JSON Schema của một đặc tả ngày, sinh từ `yofina_core.dates.DateSpec`: cùng định nghĩa với đầu vào tool `knowledge___resolve_date`
    (trừ `user_id`) và với hàm `dates.resolve_date` mã gọi trong tiến trình, không viết lại trường nào ở agent. `$ref` đã giải."""
    schema = D.DateSpec.model_json_schema()
    defs = schema.pop("$defs", {})

    def inline(node: Any) -> Any:
        if isinstance(node, list):
            return [inline(x) for x in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return inline(copy.deepcopy(defs[node["$ref"].rsplit("/", 1)[-1]]))
        return {k: inline(v) for k, v in node.items()}

    out = _number_offsets(inline(schema))
    out.pop("description", None)  # docstring của lớp là ghi chú cho lập trình viên; nghĩa cho model ở `DATE_SPEC_DESCRIPTION`
    return out


def date_spec_json_schema(purpose: str = "") -> dict[str, Any]:
    """Schema của một trường đặc tả ngày (đối tượng hoặc null): `purpose` (ngày nào của câu) đứng trước nghĩa chung của đặc tả."""
    obj = {**copy.deepcopy(_date_spec_object_schema()), "description": f"{purpose} {DATE_SPEC_DESCRIPTION}".strip()}
    return {"anyOf": [obj, {"type": "null"}]}


def raw_date_spec(value: Any) -> dict[str, Any] | None:
    """Đặc tả ngày model trả, giữ dạng thô (chỉ bỏ giá trị null và độ lệch rỗng): đúng hay sai do `dates.resolve_date` kiểm lúc dùng, nên
    đặc tả sai thành câu hỏi lại hoặc lỗi có mã, không bắt model thử lại. Không có trường nào (model trả đối tượng toàn null) là không
    có đặc tả. Giá trị không phải đối tượng bị bỏ và ghi log (`date_spec_dropped`, cắt ngắn)."""
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            value = json.loads(value)  # model nhỏ đôi khi trả đối tượng lồng thành chuỗi JSON
        except ValueError:
            pass
    if value is None or value == "":
        return None
    if not isinstance(value, Mapping):
        log.warning(json.dumps({"event": "date_spec_dropped", "value": str(value)[:40]}, ensure_ascii=False))
        return None
    out = {str(k): v for k, v in value.items() if v is not None}
    if isinstance(offset := out.get("offset"), Mapping):
        parts = {str(k): v for k, v in offset.items() if v is not None}
        if parts:
            out["offset"] = parts
        else:
            out.pop("offset")
    if out.get("before") is False:
        out.pop("before")
    return out or None


def date_spec_field(purpose: str) -> Any:
    """Kiểu của một trường đặc tả ngày trong đầu ra của model: dạng thô (`raw_date_spec`), schema từ `DateSpec` (`date_spec_json_schema`)."""
    return Annotated[
        dict[str, Any] | None, BeforeValidator(raw_date_spec), WithJsonSchema(date_spec_json_schema(purpose))
    ]


def _wire_number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def date_spec_args(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Tham số của tool `knowledge___resolve_date` từ một đặc tả: đã kiểm bằng `dates.parse_spec` (sai thì `DateResolveError`
    PARAMS_INVALID), chỉ trường có giá trị, độ lệch là số JSON (schema của Gateway là `number`). Không có `user_id` (interceptor điền)."""
    parsed = D.parse_spec(spec).model_dump(exclude_none=True)
    if parsed.get("before") is False:
        parsed.pop("before")
    if "offset" in parsed:
        parsed["offset"] = {k: _wire_number(v) for k, v in parsed["offset"].items()}
    return parsed


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
#: Loại chi router trích được (`IntentParams.tx_type`): danh mục loại CHI của bảng tra loại giao dịch (`wallet.SPENDING_TX_TYPES`), mã ->
#: nhãn theo thứ tự của bảng; trừ mua bằng Trả sau vì đó là cách trả (đã có `funding`), không phải việc được trả tiền.
ROUTER_TX_TYPES: dict[str, str] = {code: label for code, label, _ in SPENDING_TX_TYPES if code != TX_TYPE_BNPL_PURCHASE}
RouterTxType = Literal[tuple(ROUTER_TX_TYPES)]  # type: ignore[valid-type]
#: Đặc tả hạn mục tiêu lộ trình router trả (`IntentParams.date_spec`).
RouterDateSpec = date_spec_field(
    "Hạn của mục tiêu lộ trình (chính hạn ở date_text) viết thành đặc tả: câu lộ trình có hạn thì điền, kỳ đếm từ <ngay_hom_nay>; "
    "null khi câu không nói hạn hoặc không chắc hạn là gì."
)

# Mô tả của các trường router phải TỰ CHỌN theo nghĩa (không chép chữ người dùng), đặt ngay ở trường trong schema của tool; lời nhắc
# hệ thống chỉ chỉ tới đây. Đo ở #39 (24 câu, logs QQ): Claude Haiku 4.5 điền đúng spend_jar_code 8/8, date_spec 6/7, answers_pending
# 3/4; Nova 2 Lite vẫn gần như không điền ba trường này dù mô tả nằm ở lời nhắc hay ở trường.
_ANSWERS_PENDING_DESCRIPTION = (
    "Chỉ xét khi dòng Yofina: cuối của <lich_su> hỏi lại người dùng một điều (hoặc mời tính lại theo cách khác); khi đó luôn điền: true "
    "nếu <cau_moi> trả lời điều đó (ngắn hay dài), false nếu <cau_moi> là yêu cầu mới. Null khi không có <lich_su> hoặc dòng cuối của "
    "Yofina không hỏi gì."
)
_JAR_TEXT_DESCRIPTION = (
    "Tên hũ người dùng TỰ NÊU, chép đúng chữ họ gõ: hũ để trả khoản chi (what_if mua hàng, affordability) hoặc hũ chứa mục tiêu lộ "
    "trình. Họ không nêu tên hũ thì null; hũ bạn chọn theo mục đích khoản chi đặt ở spend_jar_code, không đặt ở đây."
)
_SPEND_JAR_DESCRIPTION = (
    "Chỉ cho khoản chi của chính người dùng ở what_if và affordability: code của MỘT hũ trong <hu_cua_vi> mà khoản tiền thuộc về theo "
    "mục đích chi. Bạn chọn, người dùng không cần nêu tên hũ: so việc hay món họ trả tiền cho với name và purpose của từng hũ theo "
    "nghĩa của tên; hũ người dùng tự đặt tên xét như mọi hũ, hũ đặt riêng cho đúng việc đó hợp hơn hũ dùng chung, kind không loại hũ "
    "nào. Người dùng nêu tên hũ sẽ trả thì là code của đúng hũ đó. Null khi câu không nói tiền dùng vào việc gì, khi không hũ nào hợp "
    "rõ hoặc có từ hai hũ hợp ngang nhau, hoặc khi không có <hu_cua_vi>. Chỉ chép code có trong <hu_cua_vi>."
)
_TX_TYPE_DESCRIPTION = (
    "Chỉ cho khoản chi của chính người dùng ở what_if và affordability: mã trong danh sách Loại chi của lời nhắc hệ thống theo MỤC "
    "ĐÍCH của khoản tiền (nhiều thứ cho cùng một việc thì lấy loại của việc đó). Không phụ thuộc hũ: hũ trả do spend_jar_code và "
    "jar_text nói, cách trả do funding nói. Null khi câu không nói tiền dùng vào việc gì hoặc không loại nào hợp."
)
_DATE_TEXT_DESCRIPTION = "Cụm chữ chỉ thời gian người dùng nói (hạn của mục tiêu, thời điểm của khoản chi), chép nguyên văn."


class IntentParams(_Model):
    """Tham số của <cau_moi>. Trường chép chữ (jar_text, from_jar_text, to_jar_text, label, date_text, obligation_name) giữ đúng chữ
    người dùng gõ và để null khi họ không nói; số tiền chỉ lấy số họ nói. Trường mã (spend_jar_code, tx_type, date_spec,
    answers_pending và các trường kind, action, topic) là lựa chọn của bạn theo nghĩa của câu, theo mô tả của từng trường."""

    # Docstring trên là `description` của `params` trong schema tool router (model đọc), không phải ghi chú cho lập trình viên.
    # Thứ tự trường là thứ tự trong schema: trường chọn theo nghĩa đứng cạnh trường chữ nó đi cùng (hũ, hạn), cờ trả lời câu hỏi lại
    # đứng đầu vì nó nói về cả câu.
    answers_pending: bool | None = Field(default=None, description=_ANSWERS_PENDING_DESCRIPTION)
    lookup_kind: LookupKind | None = (
        None  # chỉ với intent `lookup`: tra số dư, giao dịch, dự báo một hũ hay nghĩa vụ
    )
    jar_text: str | None = Field(default=None, description=_JAR_TEXT_DESCRIPTION)
    # what_if có khoản chi và affordability: MÃ của hũ trong danh sách hũ của ví (thẻ <hu_cua_vi> của prompt router) mà khoản định chi thuộc
    # về theo ý định của người dùng, hoặc null. Mã kiểm theo danh sách đã đưa ở lượt (`router.checked_spend_jar`); người dùng không nêu hũ
    # thì đây là nguồn đầu tiên của hũ trả (`clarify.infer_pay_jar`), loại chi `tx_type` là đường lùi.
    spend_jar_code: str | None = Field(default=None, description=_SPEND_JAR_DESCRIPTION)
    from_jar_text: str | None = None
    to_jar_text: str | None = None
    amount_vnd: Annotated[int, Field(ge=1)] | None = None
    funding: Literal["jar", "credit"] | None = None
    scenario_kind: Literal[
        "one_time_purchase", "bnpl_purchase", "income_change", "recurring_expense",
        "jar_transfer", "goal_delay",
    ] | None = None  # fmt: skip
    date_text: str | None = Field(default=None, description=_DATE_TEXT_DESCRIPTION)
    # roadmap có hạn: chính hạn ở date_text viết thành đặc tả ngày (V1, #39; cùng dạng với đầu vào tool `knowledge___resolve_date`). Mã
    # tính ngày bằng `yofina_core.dates.resolve_date` trong tiến trình; đặc tả sai, ngày đã qua hay năm Tết ngoài bảng thì hỏi lại một
    # câu. Cách đọc date_text bằng mã chỉ là đường lùi khi router không trả đặc tả.
    date_spec: RouterDateSpec = None
    label: Annotated[str, Field(max_length=80)] | None = None
    # what_if có khoản chi và affordability: loại chi của khoản đó theo danh mục loại giao dịch của sản phẩm (router trích, không đoán).
    # Người dùng không nêu hũ và router không chọn hũ (spend_jar_code) thì mã đưa loại này qua quy tắc phân loại của ví để biết hũ trả
    # (`clarify.infer_pay_jar`).
    tx_type: RouterTxType | None = Field(default=None, description=_TX_TYPE_DESCRIPTION)
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
    # memory: người dùng NÓI một sở thích để nhớ (state) hay HỎI trợ lý đang nhớ gì về họ (recall); null khi chưa rõ (mã lùi về
    # `memory.is_recall_question`). Như insight_kind: ý định phụ là trường có cấu trúc của router, không đoán bằng chữ.
    memory_action: Literal["state", "recall"] | None = None
    # Số tiền người dùng nói bằng NGOẠI TỆ: router không quy đổi (amount_vnd để null); `fx_chat.convert_foreign_amount` gọi
    # `knowledge___get_exchange_rate` và điền amount_vnd từ kết quả tool. currency là mã ISO 4217, amount_original là số theo ngoại tệ.
    currency: str | None = None
    amount_original: Annotated[float, Field(gt=0)] | None = None
    # answers_pending (đầu lớp): mã chỉ ghép câu trả lời với câu đang chờ khi cờ này đúng hoặc câu trùng một chip của câu hỏi mã đã đặt
    # (`router.merge_pending`), không theo độ dài câu.

    @field_validator("spend_jar_code", mode="before")
    @classmethod
    def _spend_jar_text(cls, value: Any) -> Any:
        """Giá trị không phải chuỗi (hoặc chuỗi rỗng) coi như router không chọn hũ, không bắt router thử lại; chuỗi giữ nguyên, không sửa
        chữ của model. Giá trị bị bỏ được ghi log (`router_spend_jar_dropped`, cắt ngắn) như mã loại chi lạ."""
        if isinstance(value, str) and value:
            return value
        if value not in (None, ""):
            log.warning(json.dumps({"event": "router_spend_jar_dropped", "value": str(value)[:40]}, ensure_ascii=False))
        return None

    @field_validator("tx_type", mode="before")
    @classmethod
    def _known_tx_type(cls, value: Any) -> Any:
        """Mã ngoài danh mục loại chi coi như router không trích được loại (mã hỏi lại hũ như cũ), không bắt router thử lại. Giá trị bị
        bỏ được ghi log (`router_tx_type_dropped`, cắt ngắn) để phân biệt router để trống với router trả mã lạ khi xem lượt trên app."""
        if isinstance(value, str) and value in ROUTER_TX_TYPES:
            return value
        if value not in (None, ""):
            log.warning(json.dumps({"event": "router_tx_type_dropped", "value": str(value)[:40]}, ensure_ascii=False))
        return None

    @field_validator("answers_pending", mode="before")
    @classmethod
    def _answers_pending_bool(cls, value: Any) -> Any:
        """Chỉ nhận true/false; giá trị khác coi như router không nói (mã không ghép), không bắt router thử lại."""
        return value if isinstance(value, bool) else None

    @field_validator("memory_action", mode="before")
    @classmethod
    def _known_memory_action(cls, value: Any) -> Any:
        """Giá trị ngoài hai loại coi như router để trống (mã lùi về đường đoán sẵn có), không bắt router thử lại; giá trị bị bỏ được ghi
        log (`router_memory_action_dropped`, cắt ngắn)."""
        if value in ("state", "recall"):
            return value
        if value not in (None, ""):
            log.warning(json.dumps({"event": "router_memory_action_dropped", "value": str(value)[:40]}, ensure_ascii=False))
        return None

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
    "DATE_SPEC_DESCRIPTION",
    "INTENTS",
    "PLAN_TOOLS",
    "ROUTER_TX_TYPES",
    "Analysis",
    "AnalysisOption",
    "BasisKey",
    "ClarifyChipIn",
    "ClarifyRequest",
    "GroundingResult",
    "Intent",
    "IntentParams",
    "IntentResult",
    "LookupKind",
    "ObligationKind",
    "OptionActionSpec",
    "OptionConclusionIn",
    "OptionSuitability",
    "Plan",
    "PlanLimits",
    "PlanStep",
    "ReasoningStepIn",
    "UngroundedNumber",
    "Verdict",
    "date_spec_args",
    "date_spec_field",
    "date_spec_json_schema",
    "raw_date_spec",
]
