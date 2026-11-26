"""Hỏi lại đúng MỘT câu (khối `clarify`): kiểm bằng mã xem còn thiếu gì, không tin hoàn toàn vào router.

Router (model) có thể tự hỏi lại kèm chip; mã luôn kiểm lại các ô bắt buộc theo ý định. Nếu router quên hỏi mà vẫn thiếu thông tin,
hoặc model không dùng được (suy giảm), mã dựng câu hỏi từ chuỗi sản phẩm trong `notices.CLARIFY` (không phải câu trả lời soạn sẵn cho một
câu demo: chỉ là nhãn của ô còn thiếu). Chỉ hỏi một ô mỗi lượt; lượt sau người dùng trả lời thì router ghép với câu trước và chạy tiếp.

Lượt chỉ đọc (what-if mua hàng, kiểm tra trước khi chi) thiếu hũ trả thì mã dùng hũ router chọn theo ý định trong danh sách hũ của ví,
không có thì hũ suy từ loại chi bằng quy tắc phân loại của ví (`infer_pay_jar`), trước khi quyết định hỏi; chỉ hỏi khi chưa rõ.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from yofina_agent import notices
from yofina_agent.jars import resolve_jar
from yofina_agent.schemas import ClarifyChipIn, ClarifyRequest, IntentResult
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
