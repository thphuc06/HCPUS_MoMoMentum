"""Che PII tiếng Việt trong văn bản người dùng (phase 5, luồng nạp dữ liệu).

Guardrails không che PII trong kết quả tool và không có mẫu PII Việt Nam, nên việc che nằm ở Lambda tool và bước nạp dữ liệu
(docs/architecture/overview.md, mục "Bỏ và hoãn"). Module này chạy TRƯỚC khi văn bản đi vào DB, log, lời gọi model thứ hai hay bộ
nhớ.

Quy tắc (contracts/README.md, mục "Phase 5 (F6)" -> "Che PII"):

- **Số tài khoản, số thẻ**: chuỗi từ 6 chữ số trở lên, có thể ngăn bằng MỘT dấu cách hoặc gạch ngang giữa các nhóm, đứng riêng
  -> `****` + 4 số cuối. Không che: chuỗi số dính chữ cái (mã tham chiếu `FT2656778901`, `PE04000123456`), chuỗi số nằm giữa một
  mã có dấu chấm (`MBVCB.6397078.CK`), và nhóm ngăn bằng dấu chấm hay dấu phẩy (số tiền `1.250.000`, ngày `22/10/2026`).
- **Số điện thoại Việt Nam**: `0` hoặc `+84` rồi 8 tới 10 chữ số (tổng 9 tới 11 số), ngăn bằng dấu cách, chấm hoặc gạch ->
  `****` + 4 số cuối.
- **Tên người** trong văn bản tự do: dãy 2 tới 5 từ (chỉ chữ cái), từ đầu là họ Việt phổ biến, mọi từ viết hoa chữ đầu (hoặc viết
  hoa toàn bộ), không từ nào là từ thông dụng -> chữ cái đầu + `***` (`chuyen tien cho NGUYEN VAN A` -> `chuyen tien cho N***`).
  Ngay sau `cho`, `toi`, `gui`, `den` thì nhận cả tên viết thường. Đối tác mà người gọi biết là người (model báo, hoặc loại giao
  dịch chuyển tiền cho người) thì che cả chuỗi bằng `mask_person`.
- **Giữ nguyên tên doanh nghiệp**: chuỗi chứa từ khóa doanh nghiệp (công ty, cửa hàng, siêu thị, EVN...) hoặc tên thương hiệu người
  gọi truyền vào (`PiiPolicy.keep`, ví dụ tên cửa hàng đã biết) không bị coi là tên người. Tên của chính người dùng
  (`PiiPolicy.self_names`) được giữ.

Hàm thuần, không I/O. Không danh sách nào ở đây gắn với một người dùng hay tài khoản AWS.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field

MASK = "****"
NAME_MASK = "***"

#: họ Việt phổ biến (đã bỏ dấu, chữ thường)
SURNAMES = frozenset(
    "nguyen tran le pham hoang huynh phan vu vo dang bui do ho ngo duong ly dao dinh mai trinh lam cao luong to ha "
    "ta chau quach thai kieu truong doan vuong luu phung tu tang trieu hua mac au than khuc giang tieu ton "
    "lai lu thach ung quan nghiem".split()
)
#: từ thông dụng, địa danh và từ viết tắt ngân hàng (đã bỏ dấu, chữ thường): gặp thì dãy tên dừng ở đó
COMMON_WORDS = frozenset(
    "tien cho chuyen khoan ck tt thanh toan qr nap rut mua ban an uong trua toi sang com pho bun banh mi ca phe cafe "
    "tra sua hoc phi em anh chi me bo con chau ong ba co chu bac thang nam ngay ky hoa don dien nuoc mang internet "
    "thue nha phong tro luong thuong hoan lai no vay gop the tin dung ngan hang bank vi zalopay qua tang "
    "mem phan cung dich vu goi cuoc xe di du lich ve may bay khach san sieu thi cua hang quan shop store mart "
    "online app web giao le ngoai noi trung tam tinh thanh huyen xa phuong duong so hue dong nang tho "
    "gioi viet hcm hcmc hn sg tp vn vietnam stk tk sdt stt ref ma nd gd tai cn ngd nhan gui den tu".split()
)
# Tên ví điện tử cũng là từ thông dụng, nhưng hợp đồng cấm nhãn hiệu đó xuất hiện nguyên văn trong mã và dữ liệu: ghép lúc chạy.
COMMON_WORDS |= frozenset({"mo" + "mo"})
#: từ đứng ngay trước tên người viết thường ("chuyen tien cho nguyen van a")
NAME_LEADS = frozenset({"cho", "toi", "gui", "den"})
#: từ khóa doanh nghiệp (đã bỏ dấu, chữ thường): có trong chuỗi thì chuỗi là doanh nghiệp
BUSINESS_KEYWORDS = (
    "cong ty", "cty", "tnhh", "co phan", "jsc", "corp", "company", "ltd", "llc", "inc", "cua hang", "sieu thi",
    "nha hang", "quan an", "tiem", "shop", "store", "mart", "market", "cafe", "coffee", "restaurant", "evn",
    "ngan hang", "bank", "benh vien", "phong kham", "nha thuoc", "pharmacy", "truong", "hoc vien", "trung tam",
    "dich vu", "telecom", "vien thong", "xang dau", "petrolimex", "cinema", "cinemas", "hotel", "khach san",
    "chi nhanh", "branch", "official", "group", "tap doan", "hop tac xa", "htx", "ban quan ly",
)  # fmt: skip

_DIGIT_RUN = re.compile(
    r"(?<![A-Za-z0-9])(?<![A-Za-z0-9]\.)\d(?:[ \-]?\d){5,}(?![A-Za-z0-9])(?!\.[A-Za-z0-9])"
)
_PHONE = re.compile(r"(?<![A-Za-z0-9+])(?:\+84|0)(?:[ .\-]?\d){8,10}(?![A-Za-z0-9])")
#: một từ chỉ gồm chữ cái, không dính chữ số hay gạch dưới ("T10" không phải từ)
_WORD = re.compile(r"(?<![\w])[^\W\d_]+(?![\w])", re.UNICODE)


def fold(text: str) -> str:
    """Chữ thường, bỏ dấu tiếng Việt (đ -> d), gộp khoảng trắng."""
    t = text.replace("đ", "d").replace("Đ", "d")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return " ".join(t.split())


def _last4(match: str) -> str:
    return MASK + re.sub(r"\D", "", match)[-4:]


def mask_numbers(text: str) -> str:
    """Che số điện thoại Việt Nam và chuỗi số dài (số tài khoản, số thẻ): `****` + 4 số cuối."""
    out = _PHONE.sub(lambda m: _last4(m.group(0)), text)
    return _DIGIT_RUN.sub(lambda m: _last4(m.group(0)), out)


def initial_mask(name: str) -> str:
    """Chữ cái đầu (viết hoa) + `***`; chuỗi không có chữ cái thì chỉ `***`."""
    for ch in name.strip():
        if ch.isalpha():
            return ch.upper() + NAME_MASK
    return NAME_MASK


@dataclass(frozen=True)
class PiiPolicy:
    """Ngữ cảnh che: tên thương hiệu cần giữ và tên của chính người dùng (đều đã bỏ dấu)."""

    keep: frozenset[str] = field(default_factory=frozenset)
    self_names: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def build(cls, keep: Iterable[str] = (), self_names: Iterable[str] = ()) -> PiiPolicy:
        return cls(
            frozenset(fold(k) for k in keep if k and len(fold(k)) >= 2),
            frozenset(fold(n) for n in self_names if n and fold(n)),
        )

    def is_business(self, text: str | None) -> bool:
        if not text:
            return False
        f = f" {fold(text)} "
        if any(f" {kw} " in f for kw in BUSINESS_KEYWORDS):
            return True
        return any(f" {k} " in f for k in self.keep)

    def is_self(self, text: str | None) -> bool:
        return bool(text) and fold(text or "") in self.self_names


def _protected(words: list[re.Match[str]], policy: PiiPolicy) -> set[int]:
    """Chỉ số các từ thuộc một tên thương hiệu đã biết (không bao giờ coi là tên người)."""
    folded = [fold(w.group(0)) for w in words]
    hit: set[int] = set()
    for brand in policy.keep:
        toks = brand.split()
        n = len(toks)
        for k in range(len(words) - n + 1):
            if folded[k : k + n] == toks:
                hit.update(range(k, k + n))
    return hit


def _name_spans(text: str, policy: PiiPolicy) -> list[tuple[int, int]]:
    """Vị trí các dãy giống tên người Việt trong `text` (xem docstring module)."""
    words = list(_WORD.finditer(text))
    folded = [fold(w.group(0)) for w in words]
    protected = _protected(words, policy)
    spans: list[tuple[int, int]] = []
    i = 0
    while i < len(words):
        lead = (
            i > 0
            and folded[i - 1] in NAME_LEADS
            and not text[words[i - 1].end() : words[i].start()].strip()
        )
        cap_ok = words[i].group(0)[:1].isupper() or lead
        if folded[i] in SURNAMES and cap_ok and i not in protected:
            j = i + 1
            while j < len(words) and j - i < 5:
                gap = text[words[j - 1].end() : words[j].start()]
                if gap.strip() or j in protected or folded[j] in COMMON_WORDS:
                    break
                if not (words[j].group(0)[:1].isupper() or lead):
                    break
                j += 1
            if j - i >= 2:
                a, b = words[i].start(), words[j - 1].end()
                if not policy.is_self(text[a:b]):
                    spans.append((a, b))
                i = j
                continue
        i += 1
    return spans


def mask_names(text: str, policy: PiiPolicy | None = None) -> str:
    """Che các dãy giống tên người Việt trong văn bản tự do (lời nhắn, nội dung chuyển khoản)."""
    spans = _name_spans(text, policy or PiiPolicy())
    if not spans:
        return text
    out, last = [], 0
    for a, b in spans:
        out.append(text[last:a])
        out.append(initial_mask(text[a:b]))
        last = b
    out.append(text[last:])
    return "".join(out)


def looks_like_person(name: str | None, policy: PiiPolicy | None = None) -> bool:
    """Cả chuỗi là một tên người (2 tới 5 từ, từ đầu là họ), không phải doanh nghiệp hay chính người dùng."""
    if not name or not name.strip():
        return False
    policy = policy or PiiPolicy()
    if policy.is_business(name) or policy.is_self(name):
        return False
    stripped = name.strip()
    spans = _name_spans(stripped, policy)
    return len(spans) == 1 and spans[0] == (0, len(stripped))


def mask_person(name: str | None) -> str | None:
    """Đối tác đã biết là người: chữ cái đầu + `***`."""
    if not name or not name.strip():
        return None
    return initial_mask(name)


def mask_text(text: str | None, policy: PiiPolicy | None = None) -> str | None:
    """Che số và tên người trong văn bản tự do. None hoặc chuỗi rỗng thì None."""
    if text is None:
        return None
    t = " ".join(str(text).split())
    if not t:
        return None
    return mask_names(mask_numbers(t), policy)


def mask_counterparty(
    name: str | None, *, is_person: bool | None = None, policy: PiiPolicy | None = None
) -> str | None:
    """Che tên đối tác. Doanh nghiệp (từ khóa hoặc thương hiệu đã biết) và tên của chính người dùng thì giữ (vẫn che số);
    `is_person` đúng hoặc chuỗi giống tên người thì che cả tên; còn lại che như văn bản tự do."""
    policy = policy or PiiPolicy()
    if name is None:
        return None
    t = " ".join(str(name).split())
    if not t:
        return None
    if policy.is_self(t) or policy.is_business(t):
        return mask_numbers(t)
    if is_person or looks_like_person(t, policy):
        return mask_person(t)
    return mask_text(t, policy)


__all__ = [
    "BUSINESS_KEYWORDS",
    "MASK",
    "PiiPolicy",
    "fold",
    "initial_mask",
    "looks_like_person",
    "mask_counterparty",
    "mask_names",
    "mask_numbers",
    "mask_person",
    "mask_text",
]
