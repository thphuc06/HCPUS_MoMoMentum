"""Hỏi lại đúng MỘT câu (khối `clarify`): kiểm bằng mã xem còn thiếu gì, không tin hoàn toàn vào router.

Router (model) có thể tự hỏi lại kèm chip; mã luôn kiểm lại các ô bắt buộc theo ý định. Nếu router quên hỏi mà vẫn thiếu thông tin,
hoặc model không dùng được (suy giảm), mã dựng câu hỏi từ chuỗi sản phẩm trong `notices.CLARIFY` (không phải câu trả lời soạn sẵn cho một
câu demo: chỉ là nhãn của ô còn thiếu). Chỉ hỏi một ô mỗi lượt; lượt sau người dùng trả lời thì router ghép với câu trước và chạy tiếp.

Mô phỏng mua hàng dùng nguồn trả người dùng chọn trong yêu cầu hoặc câu trả lời đang chờ. Kiểm tra trước khi chi
(`affordability`) có thể suy hũ từ loại chi. Khi cần hỏi, cả hai dùng `PAY_QUESTION` và chip của ví.

Câu hỏi mã đặt được nhận ra lại từ chữ của nó trong lịch sử (`recognize_prompt`): lượt sau biết câu trả lời điền ô nào và câu nào là bấm
chip (V3, #39).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Any

from yofina_agent import notices
from yofina_agent.fallback import _CREDIT, _has, _jar_phrase
from yofina_agent.jars import resolve_jar
from yofina_agent.schemas import ClarifyChipIn, ClarifyRequest, IntentParams, IntentResult
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


def is_known_item_update(p: IntentParams) -> bool:
    """Các ô riêng của khoản biết trước trong profile_update, sau khi ưu tiên hồ sơ cũ."""
    return (
        p.salary_vnd is None
        and p.payday_day is None
        and p.obligation_name is None
        and (p.known_item_name is not None or p.date_spec is not None or p.date_text is not None)
    )


def purchase_funding(
    r: IntentResult, question: str, rows: Sequence[Mapping[str, Any]], pending: Mapping[str, Any] | None
) -> IntentResult:
    """Chỉ dùng nguồn trả người dùng chọn cho khoản mua đang xét."""
    p = r.params
    if r.intent != "what_if" or p.scenario_kind not in _PURCHASE_KINDS:
        return r
    norm = normalize(question)
    prompt = (pending or {}).get("_prompt")
    names = [str(row["name"]) for row in rows]
    chip = prompt.chip(question, names) if prompt else None
    answering = pending is not None and (chip is not None or p.answers_pending is True)
    jar = (chip or {}).get("jar_text")
    credit = _has(norm, _CREDIT) and not re.search(r"\bkhong (?:\w+ ){0,3}(?:tra sau|bnpl)\b", norm)
    if not jar:
        # So tên đầy đủ trước để giữ tên dài và tên có chữ dừng của bộ tách cụm.
        by_name = {normalize(name): name for name in names}
        choices = "|".join(re.escape(n) for n in sorted(by_name, key=len, reverse=True) if n)
        if answering and norm.removeprefix("hu ") in by_name:
            jar = by_name[norm.removeprefix("hu ")]
        elif choices:
            pattern = rf"\b(?:bang|tu|lay o|trich|trong|dung|lay|chon) (?:tien )?(?:hu )?({choices})\b"
            matches = {m[1] for m in re.finditer(pattern, norm) if not norm[:m.start()].rstrip().endswith("khong")}
            if len(matches) == 1:
                jar = by_name[matches.pop()]
    if not jar and p.jar_text and (norm.startswith("hu ") or re.search(r"\b(?:bang|tu|trong|dung|lay) hu\b", norm)):
        # Tên lạ vẫn đi qua unknown_jar_clarify khi chính người dùng đã gõ tên đó.
        phrase = _jar_phrase(norm)
        if phrase and phrase not in by_name and normalize(p.jar_text).removeprefix("hu ") == phrase:
            jar = phrase
    if answering and not jar and not credit and pending:
        jar = pending.get("jar_text")
        credit = pending.get("funding") == "credit"
    # Trả lời ô hũ trả nợ của một giao dịch Trả sau giữ cách trả đã chọn.
    if answering and pending and pending.get("funding") == "credit" and prompt and "funding" not in (prompt.keys or ()):
        credit = True
    kind = p.scenario_kind
    if credit:
        kind = "bnpl_purchase"
    elif kind == "bnpl_purchase":
        kind = "one_time_purchase"
    params = p.model_copy(update={
        "jar_text": jar, "funding": "credit" if credit else ("jar" if jar else None),
        "scenario_kind": kind, "spend_jar_code": None, "spend_jar_named": None,
    })
    return r.model_copy(update={"params": params})


def missing_slot(r: IntentResult) -> str | None:
    """Ô bắt buộc còn thiếu theo ý định, hoặc None nếu đủ."""
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
        if is_known_item_update(p):
            if not p.known_item_name or not p.known_item_name.strip():
                return "other"
            if p.amount_vnd is None:
                return "amount"
            return "date" if p.date_spec is None else None
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
    if r.intent == "profile_update" and is_known_item_update(r.params):
        return ClarifyRequest(slot=slot, question=notices.KNOWN_ITEM_QUESTIONS[slot]) if slot else None
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
    quy tắc hũ trả riêng, không dùng hũ suy ra). Tên hũ trùng hũ khác thì chưa rõ, hai hũ trùng làm ứng viên. Router nói người dùng tự
    nêu hũ của `spend_jar_code` (`spend_jar_named` true) thì hũ đó không phải hũ suy: điền tên như người dùng đã nói, `inferred` None."""
    p = r.params
    if (p.spend_jar_code is None and p.tx_type is None) or not lacks_pay_jar(r):
        return JarInference(r)
    rows = [j for j in jar_rows if j.get("code") and j.get("name") and not is_system_jar(str(j["code"]), j.get("kind"))]
    if p.spend_jar_code is not None and any(j["code"] == p.spend_jar_code for j in rows):
        found = _with_jar(r, p.spend_jar_code, rows, None)
        if p.spend_jar_named is True and found.inferred is not None:
            # người dùng tự nêu hũ này (câu mới, hoặc câu trả lời câu hỏi hũ; #39, i2 sau Runtime v33): router chỉ trả mã, không chép tên
            # vào jar_text. Hũ là hũ người dùng chọn, không phải hũ mã suy, nên không có dòng "Tính theo hũ X" nói người dùng chưa nêu hũ.
            return JarInference(found.result)
        return found
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
#: Hạn của mục tiêu lộ trình chưa xác định được (V1): router không trả đặc tả hạn và mã không đọc trọn được cụm chỉ hạn, hoặc đặc tả
#: không tính được (sai dạng, ngày đã qua, năm Tết ngoài bảng; câu hỏi khi đó có lời của phép tính đứng trước). Có ngày ứng viên thì mỗi
#: ngày một chip ({date}: dd/mm/yyyy).
GOAL_DATE_QUESTION = "Bạn muốn gom đủ mục tiêu này trước ngày nào?"
GOAL_DATE_CHIP_LABEL = "Trước {date}"
GOAL_DATE_CHIP_VALUE = "Hạn {date}"
_GOAL_DATE_CHIP_RE = re.compile(r"^han (\d{2}) (\d{2}) (\d{4})$")
#: Câu hỏi hũ của mục tiêu lộ trình khi mã đã hiểu số tiền và/hoặc hạn ({goal}: `goal_phrase`, ví dụ "5.000.000 ₫ hạn 21/01/2027").
#: Câu nói lại điều mã đã hiểu, và lượt trả lời đọc lại đúng số tiền và ngày từ câu hỏi (không phụ thuộc router nhắc lại).
GOAL_JAR_QUESTION = "Mục tiêu {goal} thuộc hũ nào để mình lập lộ trình?"
#: hạn mã đã tính ({date}: dd/mm/yyyy, hạn là chính ngày đó); lượt trả lời đọc lại đúng ngày đó (`exact_date_spec`)
GOAL_JAR_DATE = "hạn {date}"
#: hạn là ngày liền trước một mốc (`before` của đặc tả hạn; {date}: ngày của mốc): nói "trước {mốc}", không nói "trước" ngày liền trước
#: mốc (đọc ra sớm thêm một ngày); lượt trả lời đọc lại đúng đặc tả đó (`before_date_spec`)
GOAL_JAR_BEFORE = "trước {date}"
#: chữ chỉ hạn người dùng nói mà mã chưa đổi ra ngày ({text}: đúng chữ họ gõ)
GOAL_TEXT_DATE = "hạn “{text}”"
#: chữ chỉ hạn người dùng nói kèm ngày mã đã tính từ đặc tả hạn ({date}: dd/mm/yyyy); hạn là ngày liền trước mốc thì {date} là mốc
GOAL_TEXT_DATE_ON = "hạn “{text}” ({date})"
GOAL_TEXT_BEFORE_ON = "hạn “{text}” (trước {date})"
_DMY_TEXT_RE = re.compile(r"(?<!\d)(\d{2})/(\d{2})/(\d{4})(?!\d)")
_BEFORE_WORD = GOAL_JAR_BEFORE.split("{", 1)[0]
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
            return {"date_spec": exact_date_spec(day), "date_text": day.strftime("%d/%m/%Y")}
        return None


UNKNOWN_PROMPT = AskedPrompt()


def exact_date_spec(day: date) -> dict[str, Any]:
    """Đặc tả của đúng một ngày dương lịch (mốc `date` đủ ngày, tháng, năm): ngày mã đã biết (chip ngày, ngày nói lại trong câu hỏi) đi
    qua cùng ô và cùng phép tính với hạn router trả, `dates.resolve_date` ra lại đúng ngày đó."""
    return {"anchor": "date", "day": day.day, "month": day.month, "year": day.year}


def before_date_spec(anchor: date) -> dict[str, Any]:
    """Đặc tả "trước mốc `anchor`" (ngày liền trước mốc, `before`): hạn mã nói lại trong câu hỏi dạng "trước {mốc}" đọc lại thành đúng
    đặc tả đó, nên `dates.resolve_date` ra lại cùng ngày và cùng mốc đã dùng."""
    return {**exact_date_spec(anchor), "before": True}


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
        AskedPrompt(keys=("date_text", "date_spec"), date_chips=True, intent="roadmap", implies=_ROADMAP_CREATE),
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
    if known := _known_item_prompt(text):
        return known
    for pattern, prompt in _GOAL_PROMPTS:
        if m := pattern.search(text):
            return replace(prompt, given=_goal_given(m["goal"]))
    for pattern, prompt in _PROMPTS:
        if pattern.search(text) if isinstance(pattern, re.Pattern) else pattern in text:
            return prompt
    return None


def goal_phrase(
    amount_vnd: int | None, *, deadline: date | None = None, date_text: str | None = None, before: date | None = None
) -> str:
    """Mục tiêu lộ trình mã đã hiểu, nói lại trong câu hỏi: số tiền đã định dạng, hạn dạng dd/mm/yyyy (`deadline`), đúng chữ chỉ hạn người
    dùng nói (`date_text`), hoặc cả hai (chữ của họ kèm ngày đã tính). `before`: hạn là ngày liền trước mốc này (`before` của đặc tả hạn),
    nên câu nói "trước {mốc}" thay cho ngày `deadline` (đọc ra sớm thêm một ngày). Rỗng khi không có gì."""
    parts = [format_vnd(amount_vnd)] if amount_vnd is not None else []
    cleaned = date_text.replace("“", "").replace("”", "").strip()[:40] if date_text else ""
    if before is not None:
        when = before.strftime("%d/%m/%Y")
        parts.append(GOAL_TEXT_BEFORE_ON.format(text=cleaned, date=when) if cleaned else GOAL_JAR_BEFORE.format(date=when))
    elif deadline is not None and cleaned:
        parts.append(GOAL_TEXT_DATE_ON.format(text=cleaned, date=deadline.strftime("%d/%m/%Y")))
    elif deadline is not None:
        parts.append(GOAL_JAR_DATE.format(date=deadline.strftime("%d/%m/%Y")))
    elif cleaned:
        parts.append(GOAL_TEXT_DATE.format(text=cleaned))
    return " ".join(parts)


def goal_jar_question(amount_vnd: int | None, deadline: date | None, *, before: date | None = None) -> str:
    """Câu hỏi hũ của mục tiêu lộ trình, nói lại số tiền và hạn mã đã hiểu (`GOAL_JAR_QUESTION`); không có cả hai thì câu chung."""
    goal = goal_phrase(amount_vnd, deadline=deadline, before=before)
    return GOAL_JAR_QUESTION.format(goal=goal) if goal else notices.ROADMAP_GOAL_JAR_QUESTION


def roadmap_choice_question(
    amount_vnd: int | None, date_text: str | None, deadline: date | None = None, *, before: date | None = None
) -> str:
    """Câu hỏi lập bản mới hay xem bản đang dùng (C2), nói lại mục tiêu người dùng nêu: chữ chỉ hạn của họ, kèm ngày đã tính từ đặc tả
    hạn nếu có (lượt trả lời đọc lại được cả hai, không phải hỏi hạn lần nữa); không có thì câu chung."""
    goal = goal_phrase(amount_vnd, deadline=deadline, date_text=date_text, before=before)
    return ROADMAP_CHOICE_QUESTION_FOR.format(goal=goal) if goal else ROADMAP_CHOICE_QUESTION


def _goal_given(goal: str) -> dict[str, Any]:
    """Số tiền và hạn đọc lại từ phần {goal} của câu hỏi (`goal_phrase`, chuỗi do chính mã dựng): ngày dd/mm/yyyy thành đặc tả của đúng
    ngày đó, "trước dd/mm/yyyy" thành đặc tả trước mốc đó (`before_date_spec`), chữ trong ngoặc kép là chữ chỉ hạn người dùng nói."""
    out: dict[str, Any] = {}
    head = re.split(r"\s(?:trước|hạn)\s", f"{goal} ", maxsplit=1)[0]
    if (amount := parse_amount_vnd(head)) is not None:
        out["amount_vnd"] = amount
    quoted = _QUOTED_RE.search(goal)
    if quoted:
        out["date_text"] = quoted[1]
    if m := _DMY_TEXT_RE.search(goal):
        try:
            day = date(int(m[3]), int(m[2]), int(m[1]))
        except ValueError:
            return out
        before = goal[: m.start()].endswith(_BEFORE_WORD)
        out["date_spec"] = before_date_spec(day) if before else exact_date_spec(day)
        out.setdefault("date_text", f"{_BEFORE_WORD}{m[0]}" if before else m[0])
    return out


_KNOWN_ITEM_PREFIX = "Quỹ dồn"
_KNOWN_ITEM_KEYS = {
    notices.KNOWN_ITEM_QUESTIONS["other"]: ("known_item_name",),
    notices.KNOWN_ITEM_QUESTIONS["amount"]: ("amount_vnd",),
    notices.KNOWN_ITEM_QUESTIONS["date"]: ("date_text", "date_spec"),
}
_KNOWN_ITEM_DATE_RETRY = "Hạn {date} {reason}. Bạn chọn từ {earliest} đến {latest} nhé?"
_KNOWN_ITEM_QUESTIONS_PATTERN = "|".join(re.escape(question) for question in _KNOWN_ITEM_KEYS)
_KNOWN_ITEM_PROMPT = re.compile(
    rf"{_KNOWN_ITEM_PREFIX}(?:: “(?P<name>[^?\r\n]+)”)?"
    rf"(?: · (?P<goal>[^?\r\n]+))?\. "
    rf"(?P<question>{_KNOWN_ITEM_QUESTIONS_PATTERN}|{_template(_KNOWN_ITEM_DATE_RETRY).pattern})"
)


def known_item_date_retry_question(day: date, today: date, latest: date) -> str:
    """Nói lại hạn đã tính và cửa sổ hợp lệ khi hạn bị từ chối."""
    if day < today:
        reason = "đã qua"
    elif day == today:
        reason = "là hôm nay"
    elif day > latest:
        reason = "quá 12 tháng"
    else:
        reason = "chưa được chấp nhận"
    return _KNOWN_ITEM_DATE_RETRY.format(
        date=day.strftime("%d/%m/%Y"),
        reason=reason,
        earliest=(today + timedelta(days=1)).strftime("%d/%m/%Y"),
        latest=latest.strftime("%d/%m/%Y"),
    )


def known_item_question(p: IntentParams, slot: str, deadline: date | None, *, question: str) -> str:
    """Nói lại các ô đã đủ để lượt sau giữ nguyên dữ kiện khi người dùng chỉ trả lời ô đang hỏi."""
    name = p.known_item_name
    title = f": “{name}”" if slot != "other" and name and not re.search(r"[?\r\n]", name) else ""
    goal = goal_phrase(p.amount_vnd if slot != "amount" else None, deadline=deadline)
    summary = f" · {goal}" if goal else ""
    full = f"{_KNOWN_ITEM_PREFIX}{title}{summary}. {question}"
    if len(full) <= 200:  # Giới hạn của ClarifyData.question.
        return full
    return f"{_KNOWN_ITEM_PREFIX}{title}. {question}"


def _known_item_prompt(text: str) -> AskedPrompt | None:
    """Đọc lại dữ kiện mã đã nói trong câu hỏi về Quỹ dồn."""
    match = _KNOWN_ITEM_PROMPT.fullmatch(text.strip())
    if match is None:
        return None
    keys = _KNOWN_ITEM_KEYS.get(match["question"], _KNOWN_ITEM_KEYS[notices.KNOWN_ITEM_QUESTIONS["date"]])
    given = _goal_given(match["goal"] or "")
    if match["name"]:
        given["known_item_name"] = match["name"]
    return AskedPrompt(keys=keys, intent="profile_update", given=given)


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
