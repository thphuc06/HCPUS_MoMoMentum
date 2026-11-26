"""Hỏi lại đúng MỘT câu (khối `clarify`): kiểm bằng mã xem còn thiếu gì, không tin hoàn toàn vào router.

Router (model) có thể tự hỏi lại kèm chip; mã luôn kiểm lại các ô bắt buộc theo ý định. Nếu router quên hỏi mà vẫn thiếu thông tin,
hoặc model không dùng được (suy giảm), mã dựng câu hỏi từ chuỗi sản phẩm trong `notices.CLARIFY` (không phải câu trả lời soạn sẵn cho một
câu demo: chỉ là nhãn của ô còn thiếu). Chỉ hỏi một ô mỗi lượt; lượt sau người dùng trả lời thì router ghép với câu trước và chạy tiếp.

Lượt chỉ đọc (what-if mua hàng, kiểm tra trước khi chi) thiếu hũ trả thì mã dùng hũ router chọn theo ý định trong danh sách hũ của ví,
không có thì hũ suy từ loại chi bằng quy tắc phân loại của ví (`infer_pay_jar`), trước khi quyết định hỏi; chỉ hỏi khi chưa rõ, và hỏi
cùng một câu cho mọi khoản mua (`PAY_QUESTION`: chip là mọi hũ cộng Trả sau; V4, #39).

Câu hỏi mã đặt được nhận ra lại từ chữ của nó trong lịch sử (`recognize_prompt`): lượt sau biết câu trả lời điền ô nào và câu nào là bấm
chip (V3, #39).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from yofina_agent import notices
from yofina_agent.jars import resolve_jar
from yofina_agent.schemas import ClarifyChipIn, ClarifyRequest, IntentResult
from yofina_agent.textutil import normalize, parse_amount_vnd
from yofina_core.money import format_vnd
from yofina_core.wallet import is_system_jar, spending_tx_type_jar

#: scenario_kind nào KHÔNG cần số tiền
_NO_AMOUNT_KINDS = {"goal_delay"}
#: scenario_kind nào là mua hàng và cần biết trả bằng hũ hay Trả sau
_PURCHASE_KINDS = {None, "one_time_purchase", "bnpl_purchase"}
#: Ý định duy nhất có ô bắt buộc nên được hỏi lại qua khối `clarify` (cùng tập với `pending_intent` của hợp đồng khối). Ý định khác
#: tự xử lý phần còn thiếu trong handler (dự báo không nói hũ thì đọc mọi hũ, cú sốc chưa chọn thì hỏi bằng danh sách cấu hình,
#: lộ trình có mục tiêu mà chưa rõ hũ thì handler lộ trình hỏi hũ của mục tiêu...), nên câu hỏi lại router đặt cho chúng bị bỏ ở đây,
#: không dặn lại trong lời nhắc của từng ý định.
CLARIFY_INTENTS = frozenset({"what_if", "affordability", "move", "profile_update"})
#: Lượt CHỈ ĐỌC có hũ trả của một khoản chi (what-if mua hàng, kiểm tra trước khi chi): khi người dùng không nêu hũ, mã dùng hũ router
#: chọn hoặc hũ suy từ loại chi router trích (`infer_pay_jar`) thay vì hỏi. Lượt ghi (khai nghĩa vụ, chuyển hũ) giữ luồng hỏi và xác nhận.
_INFER_JAR_INTENTS = frozenset({"what_if", "affordability"})


def _canned(slot: str, variant: str | None = None) -> ClarifyRequest:
    c = notices.CLARIFY[variant or slot]
    return ClarifyRequest(
        slot=slot,  # type: ignore[arg-type]
        question=c["question"],
        chips=[ClarifyChipIn(label=x["label"], value=x["value"]) for x in c["chips"]],
    )


def missing_slot(r: IntentResult) -> str | None:
    """Ô bắt buộc còn thiếu theo ý định (None nếu đủ): `amount`, `funding_source`, `jar`, `pay_jar` (hũ nguồn của khoản mua hoặc khoản chi cần kiểm tra), `other`."""
    p = r.params
    if r.intent == "what_if":
        if p.scenario_kind not in _NO_AMOUNT_KINDS and p.amount_vnd is None:
            return "amount"
        if p.scenario_kind == "jar_transfer" and not (p.from_jar_text and p.to_jar_text):
            return "jar"  # chuyển hũ phải biết hũ nguồn và hũ đích (không đoán)
        if p.scenario_kind in _PURCHASE_KINDS and p.scenario_kind != "bnpl_purchase":
            if p.funding is None and not p.jar_text:
                return "funding_source"
            if p.funding != "credit" and not p.jar_text:
                return "pay_jar"  # mua bằng tiền hũ thì phải biết hũ nguồn (hợp đồng: không đoán)
        return None
    if r.intent == "affordability":
        if p.amount_vnd is None:
            return "amount"
        # Không có hũ nguồn (và không phải Trả sau) thì thẻ kiểm tra không có "hũ trả" để kết luận: hỏi lại, không đoán "Đủ".
        return "pay_jar" if p.funding != "credit" and not p.jar_text else None
    if r.intent == "move":
        if p.amount_vnd is None:
            return "amount"
        if not (p.from_jar_text and p.to_jar_text):
            return "jar"
        return None
    if r.intent == "profile_update":
        has_obligation = p.obligation_name is not None
        if p.salary_vnd is None and p.payday_day is None and not has_obligation:
            return "other"
        if has_obligation and p.amount_vnd is None:
            return "amount"
        return None
    return None


def resolve_clarify(r: IntentResult) -> ClarifyRequest | None:
    """Câu hỏi lại cho lượt này, hoặc None nếu đủ thông tin để chạy tiếp.

    Ưu tiên câu của router khi nó hỏi đúng ô còn thiếu; nếu mã thấy thiếu mà router không hỏi (hoặc hỏi ô khác thì mã vẫn đúng hơn
    về ô BẮT BUỘC) thì dùng câu của mã. Router hỏi mà mã thấy đã đủ thì tin mã (tránh hỏi thừa), trừ khi ô router hỏi là `other`.
    Ý định ngoài `CLARIFY_INTENTS` không bao giờ hỏi lại ở đây.
    """
    if r.intent not in CLARIFY_INTENTS:
        return None
    slot = missing_slot(r)
    if slot is None:
        return r.clarify if (r.clarify and r.clarify.slot == "other") else None
    if lacks_pay_jar(r):
        # Một chính sách cho mọi khoản mua ở lượt chỉ đọc (V4, #39): mã chưa suy được hũ trả (`infer_pay_jar`) thì hỏi đúng một câu,
        # chip là mọi hũ của ví cộng Trả sau (người gọi điền chip), cho cả what-if lẫn kiểm tra trước khi chi; không còn câu hỏi riêng
        # "trả bằng hũ hay Trả sau" cho what-if.
        return ClarifyRequest(slot="jar", question=PAY_QUESTION)
    wire_slot = "jar" if slot == "pay_jar" else slot
    if r.clarify and r.clarify.slot == wire_slot:
        return r.clarify
    return _canned("jar", "pay_jar") if slot == "pay_jar" else _canned(slot)


# --- suy hũ trả: hũ router chọn theo ý định, rồi loại chi -------------------------------------
@dataclass(frozen=True)
class InferredJar:
    """Hũ trả mã dùng khi người dùng không nêu hũ: mã và tên hũ trong ví, và nguồn. `tx_type` None: router chọn hũ theo ý định trong
    danh sách hũ của ví (`spend_jar_code`); có giá trị: hũ suy từ loại chi đó bằng quy tắc phân loại (đường lùi)."""

    code: str
    name: str
    tx_type: str | None = None

    @property
    def source(self) -> str:
        return "tx_type" if self.tx_type else "router"


@dataclass(frozen=True)
class JarInference:
    """Kết quả suy hũ: `result` là ý định đã điền hũ (hoặc nguyên ý định khi chưa rõ); `candidates` là hũ ứng viên ngang nhau (mã),
    để chip của câu hỏi lại đặt chúng lên đầu."""

    result: IntentResult
    inferred: InferredJar | None = None
    candidates: tuple[str, ...] = ()


def lacks_pay_jar(r: IntentResult) -> bool:
    """Lượt chỉ đọc sắp hỏi lại chỉ vì chưa biết hũ trả: what-if mua hàng hay kiểm tra trước khi chi, không trả bằng Trả sau, đã có
    số tiền (ô còn thiếu là hũ trả, hoặc cách trả khi người dùng không nói gì về cách trả lẫn hũ)."""
    return (
        r.intent in _INFER_JAR_INTENTS
        and r.params.funding != "credit"
        and missing_slot(r) in ("pay_jar", "funding_source")
    )


def _with_jar(r: IntentResult, code: str, rows: Sequence[Mapping[str, Any]], tx_type: str | None) -> JarInference:
    """Điền tên hũ `code` vào `jar_text` như thể người dùng đã nói, nếu tên đó đọc lại (`jars.resolve_jar`) ra đúng hũ ấy; tên trùng hũ
    khác thì chưa rõ, trả các hũ trùng làm ứng viên."""
    name = next(str(j["name"]) for j in rows if j["code"] == code)
    match = resolve_jar(name, rows)
    if match.status != "ok" or match.code != code:
        others = match.candidates or ((match.code,) if match.code else ())
        return JarInference(r, candidates=tuple(dict.fromkeys((code, *others))))
    params = r.params.model_copy(update={"jar_text": name})
    return JarInference(r.model_copy(update={"params": params}), InferredJar(code, name, tx_type))


def infer_pay_jar(r: IntentResult, jar_rows: Sequence[Mapping[str, Any]]) -> JarInference:
    """Hũ trả của khoản chi khi người dùng không nêu hũ, theo thứ tự: (a) hũ router chọn theo ý định trong danh sách hũ của ví
    (`spend_jar_code`, đã kiểm thuộc danh sách) nếu hũ đó còn là hũ người dùng của ví; (b) không có thì hũ của loại chi router trích, bằng
    CÙNG quy tắc với phân loại giao dịch (`wallet.spending_tx_type_jar`); (c) vẫn không có thì chưa rõ (người gọi hỏi lại với chip mọi hũ).

    Đã rõ: ra đúng một hũ người dùng có trong ví, và tên hũ đó đọc lại (`jars.resolve_jar`) ra đúng hũ ấy. Khi đó ý định được điền tên
    hũ ở `jar_text` như thể người dùng đã nói, nên mọi bước sau (dựng kịch bản, kiểm tra, hỏi hũ lạ) chạy như cũ. Không cần suy khi
    `lacks_pay_jar` sai, kể cả khi người dùng đã nêu hũ (tên hũ người dùng nêu thắng hũ router chọn) hay trả bằng Trả sau (hũ trả nợ theo
    quy tắc hũ trả riêng, không dùng hũ suy ra). Tên hũ trùng hũ khác thì chưa rõ, hai hũ trùng làm ứng viên."""
    p = r.params
    if (p.spend_jar_code is None and p.tx_type is None) or not lacks_pay_jar(r):
        return JarInference(r)
    rows = [j for j in jar_rows if j.get("code") and j.get("name") and not is_system_jar(str(j["code"]), j.get("kind"))]
    if p.spend_jar_code is not None and any(j["code"] == p.spend_jar_code for j in rows):
        return _with_jar(r, p.spend_jar_code, rows, None)
    if p.tx_type is None:
        return JarInference(r)
    code = spending_tx_type_jar(p.tx_type, [str(j["code"]) for j in rows])
    if code is None:
        return JarInference(r)
    return _with_jar(r, code, rows, p.tx_type)


# --- câu hỏi lại (và thông báo có chip) do mã đặt, nhận ra từ chữ của nó trong lịch sử -----------------------------------------
# Lịch sử frontend gửi chỉ có chữ (`fallback_text` của khối), không có ô hay chip. Câu hỏi mã đặt là chuỗi sản phẩm nên nhận ra được:
# biết câu trả lời điền ô nào và chuỗi nào là chip (V3, #39). Câu hỏi router (model) tự đặt thì không nhận ra (`UNKNOWN_PROMPT`).

#: Lượt chỉ đọc chưa rõ hũ trả của khoản chi (V4): MỘT câu cho cả what-if mua hàng và kiểm tra trước khi chi; chip là mọi hũ của ví
#: cộng Trả sau (`CREDIT_CHIP`, cùng chữ với chip Trả sau của câu hỏi cách trả).
PAY_QUESTION = "Bạn định trả khoản này bằng hũ nào, hay bằng Trả sau (mô phỏng)?"
CREDIT_CHIP = ClarifyChipIn(label="Trả sau (mô phỏng)", value="Trả bằng Trả sau (mô phỏng)")
#: Câu lộ trình nêu mục tiêu, router không nói xem hay lập, và đã có bản đang dùng (C2): một câu, hai chip (nhãn, chữ gửi đi, việc). Có
#: mục tiêu thì câu nói lại mục tiêu ({goal}, `goal_phrase`), để lượt trả lời đọc lại đúng số tiền và chữ chỉ hạn từ câu hỏi.
ROADMAP_CHOICE_QUESTION = "Bạn muốn lập lộ trình mới theo mục tiêu này hay xem lộ trình đang dùng?"
ROADMAP_CHOICE_QUESTION_FOR = "Bạn muốn lập lộ trình mới cho mục tiêu {goal} hay xem lộ trình đang dùng?"
ROADMAP_CHOICE_CHIPS: tuple[tuple[str, str, str], ...] = (
    ("Lập bản mới", "Lập lộ trình mới theo mục tiêu này", "create"),
    ("Xem bản đang dùng", "Xem lộ trình đang dùng", "view"),
)
#: Hạn của mục tiêu lộ trình chưa xác định được (V1): router không trả ngày và mã không đọc trọn được cụm chỉ hạn, hoặc ngày router trả
#: lệch rõ với cách đọc bằng mã. Có ngày ứng viên thì mỗi ngày một chip ({date}: dd/mm/yyyy).
GOAL_DATE_QUESTION = "Bạn muốn gom đủ mục tiêu này trước ngày nào?"
GOAL_DATE_CHIP_LABEL = "Trước {date}"
GOAL_DATE_CHIP_VALUE = "Hạn {date}"
_GOAL_DATE_CHIP_RE = re.compile(r"^han (\d{2}) (\d{2}) (\d{4})$")
#: Câu hỏi hũ của mục tiêu lộ trình khi mã đã hiểu số tiền và/hoặc hạn ({goal}: `goal_phrase`, ví dụ "5.000.000 ₫ trước 21/01/2027").
#: Câu nói lại điều mã đã hiểu, và lượt trả lời đọc lại đúng số tiền và ngày từ câu hỏi (không phụ thuộc router nhắc lại).
GOAL_JAR_QUESTION = "Mục tiêu {goal} thuộc hũ nào để mình lập lộ trình?"
GOAL_JAR_DATE = "trước {date}"
#: chữ chỉ hạn người dùng nói mà mã chưa đổi ra ngày ({text}: đúng chữ họ gõ)
GOAL_TEXT_DATE = "hạn “{text}”"
_DMY_TEXT_RE = re.compile(r"(?<!\d)(\d{2})/(\d{2})/(\d{4})(?!\d)")
_QUOTED_RE = re.compile(r"“([^”]+)”")
#: Chip của thông báo "Tính theo hũ X" ở lượt chỉ đọc (V4): chọn hũ khác, và tính bằng Trả sau khi ví có hạn mức. Chữ gửi đi nói rõ
#: việc (mô phỏng hay kiểm tra) để lượt sau biết ý định của câu đang chờ mà không cần đoán.
NOTICE_CHIP_LABELS: dict[str, str] = {"choose": "Chọn hũ khác", "credit": "Tính bằng Trả sau"}
NOTICE_CHIP_PROMPTS: dict[str, dict[str, str]] = {
    "what_if": {"choose": "Mô phỏng lại khoản này với hũ khác", "credit": "Mô phỏng lại khoản này bằng Trả sau"},
    "affordability": {"choose": "Kiểm tra lại khoản này với hũ khác", "credit": "Kiểm tra lại khoản này bằng Trả sau"},
}


@dataclass(frozen=True)
class AskedPrompt:
    """Một câu hỏi lại (hoặc thông báo có chip) mã đã đặt ở lượt trước.

    `keys`: các ô (tên tham số của router) câu trả lời điền; None khi không nhận ra câu hỏi (router tự đặt): khi đó câu trả lời chỉ
    điền các ô câu đang chờ còn trống. `chips`: chữ chip (đã `normalize`) -> tham số chip đặt; giá trị None là bỏ giá trị đang có
    (chip "chọn hũ khác" không dùng lại hũ đã suy); khóa `_intent` là ý định của câu đang chờ. `jar_chips`: chip "Hũ {tên}" cho từng hũ
    của ví, tên hũ vào ô `jar_key` (None: chip hũ không gắn một ô, như câu hỏi hũ nguồn và hũ đích). `date_chips`: chip "Hạn dd/mm/yyyy".
    `intent`: ý định của câu đang chờ khi câu hỏi chỉ thuộc một ý định; `implies`: tham số mà việc trả lời câu hỏi kéo theo; `given`: tham
    số chính câu hỏi nói ra (mã đã hiểu, viết lại trong câu hỏi), thắng cách đọc lại câu đang chờ bằng mã."""

    keys: tuple[str, ...] | None = None
    chips: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    jar_chips: bool = False
    jar_key: str | None = None
    date_chips: bool = False
    intent: str | None = None
    implies: Mapping[str, Any] = field(default_factory=dict)
    given: Mapping[str, Any] = field(default_factory=dict)

    def chip(self, text: str, jar_names: Iterable[str] = ()) -> dict[str, Any] | None:
        """Tham số chip đặt nếu `text` đúng là một chip của câu hỏi này (người dùng bấm chip), None nếu không phải chip."""
        norm = normalize(text)
        if not norm:
            return None
        if norm in self.chips:
            return dict(self.chips[norm])
        if self.jar_chips:
            for name in jar_names:
                if norm == normalize(f"Hũ {name}"):
                    return {self.jar_key: name} if self.jar_key else {}
        if self.date_chips and (m := _GOAL_DATE_CHIP_RE.match(norm)):
            try:
                day = date(int(m[3]), int(m[2]), int(m[1]))
            except ValueError:
                return None
            return {"target_date": day.isoformat(), "date_text": day.strftime("%d/%m/%Y")}
        return None


UNKNOWN_PROMPT = AskedPrompt()


def _chip_map(pairs: Iterable[tuple[str, Mapping[str, Any]]]) -> dict[str, Mapping[str, Any]]:
    return {normalize(value): dict(effect) for value, effect in pairs}


def _template(text: str) -> re.Pattern[str]:
    """Mẫu khớp một chuỗi sản phẩm có chỗ điền (`{name}`): phần cố định giữ nguyên, chỗ điền khớp chữ bất kỳ."""
    parts = re.split(r"\{[a-z_]+\}", text)
    return re.compile(".+?".join(re.escape(p) for p in parts), re.S)


def _notice_chips() -> dict[str, Mapping[str, Any]]:
    clear = {"jar_text": None, "spend_jar_code": None, "tx_type": None}
    pairs: list[tuple[str, Mapping[str, Any]]] = []
    for intent, prompts in NOTICE_CHIP_PROMPTS.items():
        pairs.append((prompts["choose"], {"_intent": intent, **clear}))
        pairs.append((prompts["credit"], {"_intent": intent, "funding": "credit", "jar_text": None, "spend_jar_code": None}))
    return _chip_map(pairs)


_PAY_CHIPS = _chip_map([(str(CREDIT_CHIP.value), {"funding": "credit"})])
_ROADMAP_CREATE = {"roadmap_action": "create"}
_ROADMAP_CHOICE = AskedPrompt(
    keys=("roadmap_action",),
    chips=_chip_map((value, {"roadmap_action": action}) for _, value, action in ROADMAP_CHOICE_CHIPS),
    intent="roadmap",
)
#: (chuỗi cố định hoặc mẫu, câu hỏi) theo thứ tự xét; chuỗi cố định khớp khi nằm trong tin của Yofina (tin có thể gồm chữ của nhiều khối).
_PROMPTS: tuple[tuple[str | re.Pattern[str], AskedPrompt], ...] = (
    (PAY_QUESTION, AskedPrompt(keys=("jar_text", "funding"), chips=_PAY_CHIPS, jar_chips=True, jar_key="jar_text")),
    (notices.CLARIFY["pay_jar"]["question"], AskedPrompt(keys=("jar_text",), jar_chips=True, jar_key="jar_text")),
    (
        notices.CLARIFY["funding_source"]["question"],
        AskedPrompt(
            keys=("funding", "jar_text"),
            chips=_chip_map(
                (c["value"], {"funding": "credit" if c["value"] == CREDIT_CHIP.value else "jar"})
                for c in notices.CLARIFY["funding_source"]["chips"]
            ),
        ),
    ),
    (
        notices.CLARIFY["amount"]["question"],
        AskedPrompt(keys=("amount_vnd",), chips=_chip_map((c["value"], {}) for c in notices.CLARIFY["amount"]["chips"])),
    ),
    (notices.CLARIFY["jar"]["question"], AskedPrompt(keys=("from_jar_text", "to_jar_text"), jar_chips=True)),
    (_template(notices.UNKNOWN_JAR_QUESTION), AskedPrompt(keys=("jar_text",), jar_chips=True, jar_key="jar_text")),
    (notices.UNKNOWN_JAR_QUESTION_NO_NAME, AskedPrompt(keys=("jar_text",), jar_chips=True, jar_key="jar_text")),
    (
        notices.ROADMAP_GOAL_JAR_QUESTION,
        AskedPrompt(keys=("jar_text",), jar_chips=True, jar_key="jar_text", intent="roadmap", implies=_ROADMAP_CREATE),
    ),
    (ROADMAP_CHOICE_QUESTION, _ROADMAP_CHOICE),
    (
        GOAL_DATE_QUESTION,
        AskedPrompt(keys=("date_text", "target_date"), date_chips=True, intent="roadmap", implies=_ROADMAP_CREATE),
    ),
    (_template(notices.INFERRED_JAR_MESSAGE), AskedPrompt(keys=("jar_text", "funding"), chips=_notice_chips())),
    (_template(notices.INFERRED_JAR_MESSAGE_INTENT), AskedPrompt(keys=("jar_text", "funding"), chips=_notice_chips())),
    *(
        (
            pattern,
            AskedPrompt(
                keys=(),
                chips=_chip_map(
                    (c["value"], {"_intent": intent} if intent else {})
                    for c, intent in zip(notices.CONFIRM_SPENDING_CHIPS, ("what_if", "affordability", None), strict=True)
                ),
            ),
        )
        for pattern in (_template(notices.CONFIRM_SPENDING_QUESTION), notices.CONFIRM_SPENDING_QUESTION_NO_NAME)
    ),
)


def recognize_prompt(text: str) -> AskedPrompt | None:
    """Câu hỏi lại (hoặc thông báo có chip) mã đã đặt trong một tin của Yofina, None nếu tin không có câu nào như vậy."""
    for pattern, prompt in _GOAL_PROMPTS:
        if m := pattern.search(text):
            return replace(prompt, given=_goal_given(m["goal"]))
    for pattern, prompt in _PROMPTS:
        if pattern.search(text) if isinstance(pattern, re.Pattern) else pattern in text:
            return prompt
    return None


def goal_phrase(amount_vnd: int | None, *, deadline: date | None = None, date_text: str | None = None) -> str:
    """Mục tiêu lộ trình mã đã hiểu, nói lại trong câu hỏi: số tiền đã định dạng, hạn dạng dd/mm/yyyy (`deadline`) hoặc đúng chữ chỉ hạn
    người dùng nói khi chưa đổi ra ngày (`date_text`). Rỗng khi không có gì."""
    parts = [format_vnd(amount_vnd)] if amount_vnd is not None else []
    if deadline is not None:
        parts.append(GOAL_JAR_DATE.format(date=deadline.strftime("%d/%m/%Y")))
    elif date_text and (cleaned := date_text.replace("“", "").replace("”", "").strip()[:40]):
        parts.append(GOAL_TEXT_DATE.format(text=cleaned))
    return " ".join(parts)


def goal_jar_question(amount_vnd: int | None, deadline: date | None) -> str:
    """Câu hỏi hũ của mục tiêu lộ trình, nói lại số tiền và hạn mã đã hiểu (`GOAL_JAR_QUESTION`); không có cả hai thì câu chung."""
    goal = goal_phrase(amount_vnd, deadline=deadline)
    return GOAL_JAR_QUESTION.format(goal=goal) if goal else notices.ROADMAP_GOAL_JAR_QUESTION


def roadmap_choice_question(amount_vnd: int | None, date_text: str | None, target_date: str | None = None) -> str:
    """Câu hỏi lập bản mới hay xem bản đang dùng (C2), nói lại mục tiêu người dùng nêu (chữ chỉ hạn của họ; chỉ có ngày router tính thì
    ngày đó); không có thì câu chung."""
    deadline = date.fromisoformat(target_date) if target_date and not date_text else None
    goal = goal_phrase(amount_vnd, deadline=deadline, date_text=date_text)
    return ROADMAP_CHOICE_QUESTION_FOR.format(goal=goal) if goal else ROADMAP_CHOICE_QUESTION


def _goal_given(goal: str) -> dict[str, Any]:
    """Số tiền và hạn đọc lại từ phần {goal} của câu hỏi (`goal_phrase`, chuỗi do chính mã dựng)."""
    out: dict[str, Any] = {}
    head = re.split(r"\s(?:trước|hạn)\s", f"{goal} ", maxsplit=1)[0]
    if (amount := parse_amount_vnd(head)) is not None:
        out["amount_vnd"] = amount
    if m := _DMY_TEXT_RE.search(goal):
        try:
            day = date(int(m[3]), int(m[2]), int(m[1]))
        except ValueError:
            return out
        out["target_date"], out["date_text"] = day.isoformat(), m[0]
    elif q := _QUOTED_RE.search(goal):
        out["date_text"] = q[1]
    return out


def _goal_pattern(template: str) -> re.Pattern[str]:
    return re.compile(re.escape(template).replace(re.escape("{goal}"), "(?P<goal>.+?)"))


_GOAL_PROMPTS: tuple[tuple[re.Pattern[str], AskedPrompt], ...] = (
    (
        _goal_pattern(GOAL_JAR_QUESTION),
        AskedPrompt(keys=("jar_text",), jar_chips=True, jar_key="jar_text", intent="roadmap", implies=_ROADMAP_CREATE),
    ),
    (_goal_pattern(ROADMAP_CHOICE_QUESTION_FOR), _ROADMAP_CHOICE),
)


def is_asking(text: str) -> bool:
    """Tin của Yofina đang chờ người dùng trả lời: có câu hỏi (dấu "?"), hoặc có thông báo kèm chip mã nhận ra."""
    return "?" in text or recognize_prompt(text) is not None


def goal_date_chips(days: Iterable[date]) -> list[ClarifyChipIn]:
    """Chip ngày ứng viên của câu hỏi hạn mục tiêu (`GOAL_DATE_QUESTION`), theo thứ tự đưa vào, bỏ ngày trùng."""
    out: list[ClarifyChipIn] = []
    for day in dict.fromkeys(days):
        text = day.strftime("%d/%m/%Y")
        out.append(ClarifyChipIn(label=GOAL_DATE_CHIP_LABEL.format(date=text), value=GOAL_DATE_CHIP_VALUE.format(date=text)))
    return out
