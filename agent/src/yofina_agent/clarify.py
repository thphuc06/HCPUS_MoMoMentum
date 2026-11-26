"""Hỏi lại đúng MỘT câu (khối `clarify`): kiểm bằng mã xem còn thiếu gì, không tin hoàn toàn vào router.

Router (model) có thể tự hỏi lại kèm chip; mã luôn kiểm lại các ô bắt buộc theo ý định. Nếu router quên hỏi mà vẫn thiếu thông tin,
hoặc model không dùng được (suy giảm), mã dựng câu hỏi từ chuỗi sản phẩm trong `notices.CLARIFY` (không phải câu trả lời soạn sẵn cho một
câu demo: chỉ là nhãn của ô còn thiếu). Chỉ hỏi một ô mỗi lượt; lượt sau người dùng trả lời thì router ghép với câu trước và chạy tiếp.

Lượt chỉ đọc (what-if mua hàng, kiểm tra trước khi chi) thiếu hũ trả mà router đã trích loại chi thì mã suy hũ bằng quy tắc phân loại
của ví (`infer_pay_jar`) trước khi quyết định hỏi; chỉ hỏi khi chưa rõ.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from yofina_agent import notices
from yofina_agent.jars import resolve_jar
from yofina_agent.schemas import ClarifyChipIn, ClarifyRequest, IntentResult
from yofina_core.wallet import spending_tx_type_jar

#: scenario_kind nào KHÔNG cần số tiền
_NO_AMOUNT_KINDS = {"goal_delay"}
#: scenario_kind nào là mua hàng và cần biết trả bằng hũ hay Trả sau
_PURCHASE_KINDS = {None, "one_time_purchase", "bnpl_purchase"}
#: Ý định duy nhất có ô bắt buộc nên được hỏi lại qua khối `clarify` (cùng tập với `pending_intent` của hợp đồng khối). Ý định khác
#: tự xử lý phần còn thiếu trong handler (dự báo không nói hũ thì đọc mọi hũ, cú sốc chưa chọn thì hỏi bằng danh sách cấu hình,
#: lộ trình có mục tiêu mà chưa rõ hũ thì handler lộ trình hỏi hũ của mục tiêu...), nên câu hỏi lại router đặt cho chúng bị bỏ ở đây,
#: không dặn lại trong lời nhắc của từng ý định.
CLARIFY_INTENTS = frozenset({"what_if", "affordability", "move", "profile_update"})
#: Lượt CHỈ ĐỌC có hũ trả của một khoản chi (what-if mua hàng, kiểm tra trước khi chi): khi người dùng không nêu hũ, mã suy hũ từ loại
#: chi router trích (`infer_pay_jar`) thay vì hỏi. Lượt ghi (khai nghĩa vụ, chuyển hũ) giữ luồng hỏi và xác nhận của chúng.
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


# --- suy hũ trả từ loại chi --------------------------------------------------------------------
@dataclass(frozen=True)
class InferredJar:
    """Hũ trả mã suy từ loại chi (`tx_type`) khi người dùng không nêu hũ: mã và tên hũ trong ví, loại chi đã dùng để suy."""

    code: str
    name: str
    tx_type: str


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


def infer_pay_jar(r: IntentResult, jar_rows: Sequence[Mapping[str, Any]]) -> JarInference:
    """Hũ trả của khoản chi theo loại chi router trích, bằng CÙNG quy tắc với phân loại giao dịch (`wallet.spending_tx_type_jar`).

    Đã rõ: quy tắc cho đúng một hũ người dùng có trong ví, và tên hũ đó đọc lại (`jars.resolve_jar`) ra đúng hũ ấy. Khi đó ý định được
    điền tên hũ ở `jar_text` như thể người dùng đã nói, nên mọi bước sau (dựng kịch bản, kiểm tra, hỏi hũ lạ) chạy như cũ. Chưa rõ:
    không cần suy (`lacks_pay_jar` sai, kể cả khi người dùng đã nêu hũ: tên hũ thắng), router không trích được loại, loại không có hũ
    nhận (giao dịch loại đó rơi về Chưa phân loại), hoặc tên hũ suy ra trùng hũ khác (hai hũ ngang nhau, trả về làm ứng viên)."""
    tx_type = r.params.tx_type
    if tx_type is None or not lacks_pay_jar(r):
        return JarInference(r)
    rows = [j for j in jar_rows if j.get("code") and j.get("name")]
    code = spending_tx_type_jar(tx_type, [str(j["code"]) for j in rows])
    if code is None:
        return JarInference(r)
    name = next(str(j["name"]) for j in rows if j["code"] == code)
    match = resolve_jar(name, rows)
    if match.status != "ok" or match.code != code:
        others = match.candidates or ((match.code,) if match.code else ())
        return JarInference(r, candidates=tuple(dict.fromkeys((code, *others))))
    params = r.params.model_copy(update={"jar_text": name})
    return JarInference(r.model_copy(update={"params": params}), InferredJar(code, name, tx_type))
