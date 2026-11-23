"""Chuẩn hóa chuỗi giao dịch cho bước embedding và che thông tin định danh trước khi vào model.

Chuỗi đưa vào embedding và vào bộ nhãn k-NN (`text_norm`): bỏ dấu, chữ thường, bỏ dấu câu, mở rộng viết tắt (từ điển `abbreviations.json`),
bỏ số (số tiền, số tham chiếu không mang nghĩa) trừ cụm "tháng N". Spike Bedrock §6: bước này đưa độ chính xác 1-NN từ 81 và 84 phần trăm lên
93 phần trăm, và là chỗ "khớp chuỗi chính xác" có nghĩa (khác với ngưỡng cosine 0,97 của proposal, đã bị bác).

Che PII (`yofina_core.pii`): số tài khoản và số điện thoại thành `****` + 4 số cuối; đối tác là NGƯỜI (người nhận đã lưu, loại chuyển cho người
khác, hoặc chuỗi giống tên người) thì tên bị che hoàn toàn và KHÔNG đi vào chuỗi nhúng (một chữ cái đầu không mang nghĩa nào, lại trùng giữa
nhiều người); danh tính của người nhận nằm ở `payee_id` (luật, lịch sử), không ở embedding. Đối tác là doanh nghiệp thì giữ tên.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from yofina_core.pii import PiiPolicy, fold, mask_counterparty, mask_row_text

#: DB: tx_embeddings.text_norm dài 1..300
TEXT_NORM_MAX = 300
_MONTH_SHORT = re.compile(r"t(\d{1,2})")
_NON_WORD = re.compile(r"[^a-z0-9\s]")


@lru_cache(maxsize=1)
def abbreviations() -> dict[str, str]:
    raw = (
        resources.files("yofina_classify")
        .joinpath("abbreviations.json")
        .read_text(encoding="utf-8")
    )
    return {k: v for k, v in json.loads(raw)["words"].items()}


def normalize_text(*parts: str | None) -> str:
    """Ghép các phần, bỏ dấu, chữ thường, mở rộng viết tắt, bỏ số và chữ cái đơn lẻ. Rỗng nếu không còn chữ nào."""
    joined = " ".join(p for p in parts if p)
    folded = _NON_WORD.sub(" ", fold(joined))
    abbr = abbreviations()
    out: list[str] = []
    prev = ""
    for tok in folded.split():
        m = _MONTH_SHORT.fullmatch(tok)
        if m:  # t11 -> thang 11
            out.extend(["thang", m.group(1)])
            prev = m.group(1)
            continue
        if tok in abbr:
            out.extend(abbr[tok].split())
            prev = tok
            continue
        if tok.isdigit():
            if prev == "thang":  # chỉ giữ số đứng ngay sau "thang"
                out.append(tok)
            prev = tok
            continue
        if (
            re.fullmatch(r"\d+k", tok) or len(tok) == 1
        ):  # 40k, chữ cái đơn lẻ (dấu vết của tên đã che)
            prev = tok
            continue
        out.append(tok)
        prev = tok
    return " ".join(out)[:TEXT_NORM_MAX].strip()


@dataclass(frozen=True)
class MaskedTx:
    """Phần chữ của một giao dịch sau khi che: dùng cho model (`counterparty`, `note`) và cho embedding (`text_norm`)."""

    counterparty: str | None
    note: str | None
    text_norm: (
        str  # rỗng nếu không có chữ nào mang nghĩa (ví dụ chuyển khoản tên riêng không lời nhắn)
    )

    @property
    def has_text(self) -> bool:
        return bool(self.text_norm)


def mask_tx(
    counterparty: str | None,
    note: str | None,
    *,
    is_person: bool | None,
    policy: PiiPolicy | None = None,
) -> MaskedTx:
    """Che đối tác và lời nhắn. `is_person` đúng thì cả tên đối tác bị che và bị loại khỏi chuỗi nhúng."""
    policy = policy or PiiPolicy()
    cp = mask_counterparty(counterparty, is_person=is_person, policy=policy)
    nt = mask_row_text(note, policy)
    person = bool(is_person) or (
        counterparty is not None and cp is not None and cp.endswith("***") and "*" in cp
    )
    text = normalize_text(None if person else cp, nt)
    return MaskedTx(cp, nt, text)
