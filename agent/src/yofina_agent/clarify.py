"""Hỏi lại đúng MỘT câu (khối `clarify`): kiểm bằng mã xem còn thiếu gì, không tin hoàn toàn vào router.

Router (model) có thể tự hỏi lại kèm chip; mã luôn kiểm lại các ô bắt buộc theo ý định. Nếu router quên hỏi mà vẫn thiếu thông tin,
hoặc model không dùng được (suy giảm), mã dựng câu hỏi từ chuỗi sản phẩm trong `notices.CLARIFY` (không phải câu trả lời soạn sẵn cho một
câu demo: chỉ là nhãn của ô còn thiếu). Chỉ hỏi một ô mỗi lượt; lượt sau người dùng trả lời thì router ghép với câu trước và chạy tiếp.
"""

from __future__ import annotations

from yofina_agent import notices
from yofina_agent.schemas import ClarifyChipIn, ClarifyRequest, IntentResult

#: scenario_kind nào KHÔNG cần số tiền
_NO_AMOUNT_KINDS = {"goal_delay"}
#: scenario_kind nào là mua hàng và cần biết trả bằng hũ hay Trả sau
_PURCHASE_KINDS = {None, "one_time_purchase", "bnpl_purchase"}
#: Ý định duy nhất có ô bắt buộc nên được hỏi lại qua khối `clarify` (cùng tập với `pending_intent` của hợp đồng khối). Ý định khác
#: tự xử lý phần còn thiếu trong handler (dự báo không nói hũ thì đọc mọi hũ, cú sốc chưa chọn thì hỏi bằng danh sách cấu hình,
#: lộ trình có mục tiêu mà chưa rõ hũ thì handler lộ trình hỏi hũ của mục tiêu...), nên câu hỏi lại router đặt cho chúng bị bỏ ở đây,
#: không dặn lại trong lời nhắc của từng ý định.
CLARIFY_INTENTS = frozenset({"what_if", "affordability", "move", "profile_update"})


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
