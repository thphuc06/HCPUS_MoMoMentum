"""Số tiền ngoại tệ trong câu hỏi: quy đổi sang VND bằng `knowledge___get_exchange_rate` trước khi vào ý định.

Luồng (mã điều khiển, không có lượt model nào):

    router trích `currency` (ISO 4217) và `amount_original` (số theo ngoại tệ), KHÔNG tự quy đổi
      -> `Turn.flow` gọi `convert_foreign_amount` ngay sau khi ghép câu cụt, trước khi hỏi lại ô còn thiếu:
         `knowledge___get_exchange_rate` (Lambda ledger, cùng hàm `yofina_core.fx` và cùng nguồn với pipeline nạp chứng từ)
      -> OK: `params.amount_vnd` = `amount_vnd` của kết quả (thay số router đặt), rồi ý định chạy tiếp như một câu hỏi bằng VND
         (what-if, kiểm tra trước khi chi...). Kết quả tool nằm trong `Turn.tool_log` nên NumericGrounding của Analyst nhận các số đó
         như mọi tool khác; bản gọn `exchange_rate` đi kèm dữ liệu của Analyst và của người viết.
      -> lỗi: khối `notice` với thông điệp của tool, kết thúc lượt (không đoán số VND).
    ý định `knowledge` có `currency` (hỏi tỷ giá hay quy đổi): câu trả lời dựng bằng mã từ kết quả tool, qua NumericGrounding trước khi
    phát (`on_exchange_rate`).

Vì sao gắn ở `Turn.flow` mà không ở từng handler: số tiền ngoại tệ là một THAM SỐ của câu hỏi, không phải một ý định riêng. Đổi nó
thành VND ở một chỗ trước khi chia ý định thì mọi đường dùng `amount_vnd` (Orchestrator, `affordability_check`, hỏi lại số tiền) chạy
nguyên như cũ, không thêm đường xử lý riêng nào.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from yofina_agent.verifier import Allowed, NumericGrounding
from yofina_core import blocks as B
from yofina_core.money import format_vnd

if TYPE_CHECKING:
    from yofina_agent.schemas import IntentResult
    from yofina_agent.turn import Turn

TOOL = "get_exchange_rate"
TARGET = "knowledge"
_SOURCE_LABEL = {"vietcombank": "Vietcombank"}


def decimal_vi(text: str) -> str:
    """Chuỗi thập phân của hợp đồng ("25790.00", "111.11") theo cách viết Việt Nam: nhóm nghìn bằng ".", phần lẻ bằng "," (bỏ số 0
    thừa ở cuối)."""
    d = Decimal(text)
    whole, _, frac = f"{d:f}".partition(".")
    frac = frac.rstrip("0")
    grouped = f"{int(whole):,}".replace(",", ".")
    return f"{grouped},{frac}" if frac else grouped


def _date_vi(iso: str) -> str:
    return "/".join(reversed(iso.split("-")))


def compact_exchange_rate(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Bản gọn cho model và cho `TOOL_CALL_RESULT`: số đã định dạng (`*_text`) để chép nguyên văn, ngày dạng dd/mm/yyyy."""
    d = payload["data"]
    cur = d["currency"]
    out: dict[str, Any] = {
        "status": "OK",
        "currency": cur,
        "rate_type": d["rate_type"],
        "rate_text": f"{decimal_vi(d['rate'])} ₫",
        "source": _SOURCE_LABEL.get(d["rate_source"], d["rate_source"]),
        "rate_date_text": _date_vi(d["rate_date"]),
        "requested_date_text": _date_vi(d["requested_date"]),
    }
    if "amount_vnd" in d:
        out["amount_original_text"] = f"{decimal_vi(d['amount_original'])} {cur}"
        out["amount_vnd"] = d["amount_vnd"]
        out["amount_vnd_text"] = format_vnd(d["amount_vnd"])
    return out


async def convert_foreign_amount(turn: Turn, r: IntentResult) -> IntentResult | None:
    """Đổi số tiền ngoại tệ của câu hỏi sang VND bằng tool tỷ giá. None nếu tool lỗi (đã phát `notice`, lượt kết thúc).

    Số theo ngoại tệ là `amount_original`; router để nó trống mà lại đặt số vào `amount_vnd` thì đó vẫn là số người dùng nói kèm
    ngoại tệ (quy tắc của router: số ngoại tệ không bao giờ là VND), nên dùng số đó làm số gốc thay vì hỏi lại."""
    p = r.params
    original = p.amount_original if p.amount_original is not None else p.amount_vnd
    args: dict[str, Any] = {"currency": p.currency}
    if original is not None:
        args["amount"] = original
    res = await turn.call_tool_retry(
        TOOL, args, target=TARGET, compact=lambda o: compact_exchange_rate(o.payload or {})
    )
    if not res.outcome.ok:
        turn.tool_failure(res.outcome)
        return None
    vnd = ((res.outcome.payload or {}).get("data") or {}).get("amount_vnd")
    params = p.model_copy(update={"amount_vnd": vnd, "amount_original": original})
    return r.model_copy(update={"params": params})


def answer_text(c: Mapping[str, Any]) -> str:
    """Câu trả lời cho câu hỏi tỷ giá hay quy đổi, chỉ từ bản gọn của kết quả tool."""
    cur, rate = c["currency"], c["rate_text"]
    head = f"tỷ giá bán {cur} của {c['source']} ngày {c['rate_date_text']} ({rate} cho 1 {cur})"
    if "amount_vnd_text" in c:
        text = (
            f"{c['amount_original_text']} quy đổi được khoảng {c['amount_vnd_text']} theo {head}. Đây là số ước tính: thanh toán "
            "bằng thẻ thường cộng thêm phí chuyển đổi ngoại tệ của ngân hàng phát hành."
        )
    else:
        text = f"{head[0].upper()}{head[1:]}."
    if c["rate_date_text"] != c["requested_date_text"]:
        text += f" Ngày {c['requested_date_text']} chưa có bảng tỷ giá nên mình dùng bảng gần nhất trước đó."
    return text


async def on_exchange_rate(turn: Turn, r: IntentResult, question: str) -> None:
    """Ý định `knowledge` hỏi tỷ giá hay quy đổi: `convert_foreign_amount` đã gọi tool; câu trả lời dựng bằng mã và chỉ phát khi mọi
    con số có căn cứ trong kết quả tool (NumericGrounding, như lời của model)."""
    c = turn.compact_of(TOOL)
    if c is None:  # không có kết quả tool thì không có số nào để nói (lỗi đã thành `notice`)
        return
    text = answer_text(c)
    allowed = Allowed.from_payloads([*turn.grounding_payloads(), c], [question])
    grounding = NumericGrounding.check({"exchange_rate": text}, allowed)
    turn.extra_rules["numeric_grounding"] = B.RuleCheck(
        rule_id="numeric_grounding",
        label="Số liệu có căn cứ",
        outcome="pass" if grounding.ok else "fail",
        detail=f"Đã kiểm {grounding.checked_count} con số trong câu trả lời.",
    )
    turn.verified = grounding.ok
    if not grounding.ok:
        turn.degrade_code = turn.degrade_code or "NUMERIC_UNVERIFIED"
        return
    await turn.emit_fixed_text(text)
