"""Che PII (thông tin định danh) trong văn bản, TRƯỚC khi vào LLM, log, DB hay bộ nhớ. Hai nhóm hàm dùng chung một module vì hai
phase cùng cần che nhưng khác chỗ gọi và khác cách che.

**A. Lời người dùng gõ vào chat** (phase 3, harness L0 của `agent/`): `mask_pii`, `mask_text`. Che bằng thẻ giữ chỗ (`[SĐT]`,
`[CCCD]`, `[STK]`, `[THẺ]`, `[EMAIL]`), không bao giờ bỏ chữ trống để câu vẫn đọc được. Số tiền KHÔNG được che: người dùng gõ
"1200000" hay "15.000.000" là số tiền, nên dãy chữ số chỉ bị che khi có dạng đặc trưng (đầu số điện thoại Việt Nam, đúng 12 chữ số,
từ 10 chữ số liền không phân tách, trừ dấu thời gian Unix có ngữ cảnh thời gian: is_epoch_at) hoặc đi sau từ khóa ("stk", "số tài khoản", "cmnd"...). Đây là bộ lọc theo mẫu, không phải bảo
đảm tuyệt đối; lớp phòng thủ khác là agent không bao giờ ghi nội dung chat vào log.

**B. Văn bản và đối tác trong dòng nạp từ ảnh/CSV** (phase 5, luồng nạp dữ liệu): `mask_row_text`, `mask_counterparty`,
`mask_numbers`, `mask_names`, `PiiPolicy`. Che bằng `****` + 4 số cuối (dòng đã nạp còn được đối chiếu và hiển thị), tên người thành
chữ cái đầu + `***`. Đổi tên từ `mask_text` của nhánh nạp để khỏi trùng với hàm cùng tên ở nhóm A.

Nhóm B: Guardrails không che PII trong kết quả tool và không có mẫu PII Việt Nam, nên việc che nằm ở Lambda tool và bước nạp dữ liệu
(docs/architecture/overview.md, mục "Bỏ và hoãn"). Nhóm này chạy TRƯỚC khi văn bản đi vào DB, log, lời gọi model thứ hai hay bộ
nhớ.

Quy tắc (contracts/README.md, mục "Phase 5 (F6)" -> "Che PII"):

- **Số tài khoản, số thẻ**: chuỗi từ 6 chữ số trở lên, có thể ngăn bằng MỘT dấu cách hoặc gạch ngang giữa các nhóm, đứng riêng
  -> `****` + 4 số cuối. Không che: chuỗi số dính chữ cái (mã tham chiếu `FT2656778901`, `PE04000123456`), chuỗi số nằm giữa một
  mã có dấu chấm (`MBVCB.6397078.CK`), và nhóm ngăn bằng dấu chấm hay dấu phẩy (số tiền `1.250.000`, ngày `22/10/2026`).
- **Số điện thoại Việt Nam**: `0` hoặc `+84` rồi 8 tới 10 chữ số (tổng 9 tới 11 số), ngăn bằng dấu cách, chấm hoặc gạch ->
  `****` + 4 số cuối.
- **Tên người** trong văn bản tự do: dãy 2 tới 5 từ (chỉ chữ cái), từ đầu là họ Việt phổ biến, mọi từ viết hoa chữ đầu (hoặc viết
  hoa toàn bộ), không từ nào là từ thông dụng, trừ tên đệm và tên riêng phổ biến (`NAME_WORDS`: "Thị", "Văn", "An", "Tiến" vẫn là
  tên) -> chữ cái đầu + `***` (`chuyen tien cho NGUYEN VAN AN` -> `chuyen tien cho N***`, `NGUYEN THI A;nop tien;` ->
  `N***;nop tien;`). Ngay sau `cho`, `toi`, `gui`, `den` thì nhận cả tên viết thường, nhưng từ kế tiếp họ phải là tên riêng phổ
  biến (họ trùng đại từ hay từ thông dụng như "họ", "đó" thì phải là tên đệm), để "nhắc đến họ buổi sáng" không bị che. Đối tác mà
  người gọi biết là người (model báo, hoặc loại giao dịch chuyển tiền cho người) thì che cả chuỗi bằng `mask_person`.
- **Giữ nguyên tên doanh nghiệp**: chuỗi chứa từ khóa doanh nghiệp (công ty, cửa hàng, siêu thị, EVN...) hoặc tên thương hiệu người
  gọi truyền vào (`PiiPolicy.keep`, ví dụ tên cửa hàng đã biết) không bị coi là tên người. Tên của chính người dùng
  (`PiiPolicy.self_names`) được giữ.

Hàm thuần, không I/O. Không danh sách nào ở đây gắn với một người dùng hay tài khoản AWS.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

# ======================================================================================================================
# A. Chat (phase 3)
# ======================================================================================================================
#: tên loại -> thẻ giữ chỗ
PLACEHOLDERS: dict[str, str] = {
    "phone": "[SĐT]",
    "national_id": "[CCCD]",
    "account": "[STK]",
    "card": "[THẺ]",
    "email": "[EMAIL]",
}

_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w])")
# Thẻ: 13–19 chữ số, nhóm 4 chữ số cách nhau bằng khoảng trắng hoặc gạch.
_CARD = re.compile(r"(?<!\d)(?:\d{4}[ -]){3}\d{1,7}(?!\d)")
# Số điện thoại Việt Nam: +84/84/0 + đầu số 3,5,7,8,9 + 8 chữ số; cho phép dấu chấm, gạch, khoảng trắng giữa nhóm.
_PHONE = re.compile(r"(?<![\d.])(?:\+?84|0)[ .-]?[35789](?:[ .-]?\d){8}(?![\d])")
# Từ khóa đi trước số: (khoá, loại). Khoảng cách tối đa 25 ký tự không phải chữ số.
_KEYWORD_ID = re.compile(
    r"(?P<kw>cccd|cmnd|cmt|can cuoc|căn cước|chung minh|chứng minh|so dinh danh|số định danh)\D{0,25}?(?P<num>\d{9}|\d{12})(?!\d)",
    re.IGNORECASE,
)
_KEYWORD_ACCOUNT = re.compile(
    r"(?P<kw>stk|so tai khoan|số tài khoản|so tk|số tk|account number)\D{0,12}?(?P<num>\d{8,19})(?!\d)",
    re.IGNORECASE,
)
_ID12 = re.compile(r"(?<![\d.,])\d{12}(?![\d])")
_LONG = re.compile(r"(?<![\d.,])\d{10,19}(?![\d])")
#: Dấu thời gian Unix (giây: 10 chữ số, mili giây: 13 chữ số) mà bước tóm tắt phiên của AgentCore Memory chép vào bản ghi. Strategy
#: tóm tắt được dặn "Consider the timestamps" và thấy `contentTimestamp` của `IngestData` (bắt buộc, dạng số) cạnh mỗi lượt, nên viết
#: "timestamp 1795505552861", "Vào thời điểm 1795508600000 (ước tính khoảng 2026-11-24, 08:43 UTC)"... Trước đây các dãy này bị che
#: thành `[STK]`. Một dãy chỉ được coi là dấu thời gian khi giá trị rơi vào khoảng hợp lý VÀ có ngữ cảnh thời gian (từ khóa đứng trước,
#: hoặc "ms"/ngoặc nêu ngày giờ ngay sau) VÀ không có từ khóa tài khoản/thẻ đứng trước: số tài khoản Agribank 13 chữ số bắt đầu bằng
#: 17, 18 trùng khoảng giá trị của epoch mili giây năm 2026, nên giá trị một mình không đủ.
_EPOCH_DIGITS = re.compile(r"\d{10}|\d{13}")
#: khoảng hợp lý của dấu thời gian: 2000-01-01 tới 2100-01-01 (giây)
_EPOCH_MIN_S, _EPOCH_MAX_S = 946_684_800, 4_102_444_800
#: từ khóa thời gian đứng ngay trước dãy số (so trên chữ đã bỏ dấu, chữ thường)
_EPOCH_LEAD = re.compile(
    r"(?:\b(?:timestamp|epoch|unix(?:\s+time)?)\b\D{0,20}"
    r"|\b(?:thoi diem|moc thoi gian|thoi gian|vao luc|luc|time|at)\b(?:\s+ghi nhan)?\s*:?\s*)$"
)
#: ngay sau dãy số: đơn vị "ms", hoặc một ngoặc nêu ngày giờ ("(ước tính khoảng 2026-11-24, 08:43 UTC)") (chữ đã bỏ dấu)
_EPOCH_TRAIL = re.compile(
    r"^\s*(?:\(\s*ms\s*\)|ms\b|\([^()\n]{0,100}?(?:\d{4}-\d{2}-\d{2}|\butc\b|uoc tinh|tuong duong|khoang|approx))"
)
#: từ khóa tài khoản, thẻ đứng trước dãy số: không bao giờ coi là dấu thời gian (chữ đã bỏ dấu)
_ACCOUNT_LEAD = re.compile(
    r"\b(?:stk|tk|tai khoan|account|acct|so the|card|ngan hang|bank|chuyen khoan|ck|cccd|cmnd)\b[^\n]{0,25}$"
)


@dataclass
class MaskResult:
    text: str
    counts: Counter[str] = field(default_factory=Counter)

    @property
    def changed(self) -> bool:
        return bool(self.counts)


def _sub(pattern: re.Pattern[str], text: str, kind: str, counts: Counter[str]) -> str:
    def repl(_: re.Match[str]) -> str:
        counts[kind] += 1
        return PLACEHOLDERS[kind]

    return pattern.sub(repl, text)


def _sub_keyword(
    pattern: re.Pattern[str], text: str, kind_of: Callable[[str], str], counts: Counter[str]
) -> str:
    """Che chỉ phần số, giữ nguyên từ khóa để câu vẫn đọc được."""

    def repl(m: re.Match[str]) -> str:
        kind = kind_of(m.group("num"))
        counts[kind] += 1
        start = m.start("num") - m.start()
        return m.group(0)[:start] + PLACEHOLDERS[kind]

    return pattern.sub(repl, text)


def mask_pii(text: str) -> MaskResult:
    """Che PII trong `text`. Trả văn bản đã che và số lần che theo loại."""
    counts: Counter[str] = Counter()
    out = _sub(_EMAIL, text, "email", counts)
    out = _sub(_CARD, out, "card", counts)
    out = _sub(_PHONE, out, "phone", counts)
    out = _sub_keyword(_KEYWORD_ID, out, lambda _n: "national_id", counts)
    out = _sub_keyword(_KEYWORD_ACCOUNT, out, lambda _n: "account", counts)
    out = _sub(_ID12, out, "national_id", counts)  # đúng 12 chữ số liền: CCCD
    out = _sub_long(
        out, counts
    )  # từ 10 chữ số liền không phân tách: số tài khoản (trừ dấu thời gian có từ khóa)
    return MaskResult(out, counts)


def is_epoch_at(text: str, start: int, end: int) -> bool:
    """`text[start:end]` (toàn chữ số) là một dấu thời gian Unix chứ không phải số tài khoản: 10 hoặc 13 chữ số, giá trị trong
    2000–2100, có ngữ cảnh thời gian ở trước hoặc ngay sau, và không có từ khóa tài khoản, thẻ đứng trước."""
    digits = text[start:end]
    if not _EPOCH_DIGITS.fullmatch(digits):
        return False
    seconds = int(digits) // (1000 if len(digits) == 13 else 1)
    if not _EPOCH_MIN_S <= seconds < _EPOCH_MAX_S:
        return False
    before = fold(text[max(0, start - 40) : start]) + (
        " " if text[max(0, start - 1) : start].isspace() else ""
    )
    if _ACCOUNT_LEAD.search(before):
        return False
    return bool(_EPOCH_LEAD.search(before) or _EPOCH_TRAIL.match(fold(text[end : end + 110])))


def _sub_long(text: str, counts: Counter[str]) -> str:
    def repl(m: re.Match[str]) -> str:
        if is_epoch_at(text, m.start(), m.end()):
            return m.group(0)
        counts["account"] += 1
        return PLACEHOLDERS["account"]

    return _LONG.sub(repl, text)


# Dấu thời gian Unix mà bước tóm tắt phiên của AgentCore Memory chép vào bản ghi ("(timestamp 1795505552861)", "Thời điểm:
# timestamp 1795505692694 (ms), tương đương khoảng 2026-11-24 07:34 UTC", "*(Nguồn: timestamp ...)*"): vô nghĩa với người đọc.
_TS_PAREN = re.compile(
    r"[ \t]*\*?\([^()\n]{0,40}?\b(?:timestamp|epoch|unix)\b[^()\n]{0,100}\)\*?", re.IGNORECASE
)
_TS_INLINE = re.compile(
    r"(?:,[ \t]*)?(?:\b(?:thời điểm|thoi diem|mốc thời gian|moc thoi gian)(?:[ \t]+ghi nhận)?[ \t]*:?[ \t]*)?"
    r"\btimestamp\b[^\d\n]{0,30}?\d{10,13}(?:[ \t]*\(?[ \t]*ms[ \t]*\)?)?"
    r"(?:[ \t]*,?[ \t]*(?:tương đương|tuong duong)(?:[ \t]+khoảng)?[ \t]+\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?(?:[ \t]*UTC)?)?",
    re.IGNORECASE,
)
_EMPTY_BULLET = re.compile(r"^[ \t]*(?:[-*•][ \t]*)?[.,;:]?[ \t]*$")
# Dạng không có chữ "timestamp" ("Vào thời điểm 1795508600000 (ước tính khoảng 2026-11-24, 08:43 UTC), người dùng hỏi"): dãy số dấu
# thời gian kèm cụm dẫn đứng trước và đơn vị, ngoặc ước tính ngày giờ đứng sau. Ngày giờ trong ngoặc là giờ THẬT của máy chủ, không phải
# `app_today` của ứng dụng mô phỏng, nên bỏ cả cụm chứ không giữ lại ngày.
_EPOCH_NUM = re.compile(r"(?<![\w.,])(?:\d{13}|\d{10})(?![\w.,]\d|\d)")
_EPOCH_PHRASE_BEFORE = re.compile(
    r"(?:\b(?:vào|vao)[ \t]+(?:lúc[ \t]+|luc[ \t]+)?)?"
    r"(?:\b(?:thời điểm|thoi diem|mốc thời gian|moc thoi gian|thời gian|thoi gian|lúc|luc|at|time|epoch|unix)(?:[ \t]+(?:ghi nhận|ghi nhan))?[ \t]*:?[ \t]*)$",
    re.IGNORECASE,
)
_EPOCH_PHRASE_AFTER = re.compile(
    r"^(?:[ \t]*(?:\([ \t]*ms[ \t]*\)|ms\b))?(?:[ \t]*\([^()\n]{0,100}\))?", re.IGNORECASE
)
_SENTENCE_START = re.compile(r"(?:^|[\n.!?:;>*•-])[ \t]*$")


def _strip_bare_epochs(text: str) -> str:
    out: list[str] = []
    last = 0
    capitalize = False
    for m in _EPOCH_NUM.finditer(text):
        if m.start() < last or not is_epoch_at(text, m.start(), m.end()):
            continue
        lead = _EPOCH_PHRASE_BEFORE.search(text[max(last, m.start() - 40) : m.start()])
        start = m.start() - (len(lead.group(0)) if lead else 0)
        tail = _EPOCH_PHRASE_AFTER.match(text[m.end() : m.end() + 120])
        end = m.end() + (len(tail.group(0)) if tail else 0)
        head = text[last:start]
        if _SENTENCE_START.search(head) or (not out and not head.strip()):
            # cụm đứng đầu câu: bỏ cả dấu phẩy sau nó và viết hoa chữ đầu phần còn lại
            sep = re.match(r"[ \t]*[,;]?[ \t]*", text[end:])
            end += len(sep.group(0)) if sep else 0
            capitalize = True
        else:
            head = head.rstrip(" \t")  # giữa câu: bỏ khoảng trắng trước cụm, giữ phần sau
        out.append(head)
        last = end
        if capitalize and last < len(text):
            out.append(text[last].upper())
            last += 1
            capitalize = False
    out.append(text[last:])
    return "".join(out)


def strip_epoch_timestamps(text: str) -> str:
    """Bỏ các cụm dấu thời gian Unix ("timestamp 1795505552861", "Vào thời điểm 1795508600000 (ước tính khoảng …)") khỏi chữ một bản
    ghi bộ nhớ, rồi bỏ dòng gạch đầu dòng chỉ còn dấu câu. Chữ khác giữ nguyên (cả xuống dòng, ngày ISO 8601, số tài khoản)."""
    if not _EPOCH_NUM.search(text):
        return text
    out = _TS_INLINE.sub("", _TS_PAREN.sub("", text))
    out = _strip_bare_epochs(out)
    lines = [ln for ln in out.split("\n") if not (_EMPTY_BULLET.match(ln) and ln.strip())]
    return "\n".join(lines)


def mask_text(text: str) -> str:
    """Rút gọn của `mask_pii` khi chỉ cần chuỗi."""
    return mask_pii(text).text


# ======================================================================================================================
# B. Dòng nạp (phase 5)
# ======================================================================================================================
MASK = "****"
NAME_MASK = "***"

#: họ Việt phổ biến (đã bỏ dấu, chữ thường)
SURNAMES = frozenset(
    [
        "nguyen",
        "tran",
        "le",
        "pham",
        "hoang",
        "huynh",
        "phan",
        "vu",
        "vo",
        "dang",
        "bui",
        "do",
        "ho",
        "ngo",
        "duong",
        "ly",
        "dao",
        "dinh",
        "mai",
        "trinh",
        "lam",
        "cao",
        "luong",
        "to",
        "ha",
        "ta",
        "chau",
        "quach",
        "thai",
        "kieu",
        "truong",
        "doan",
        "vuong",
        "luu",
        "phung",
        "tu",
        "tang",
        "trieu",
        "hua",
        "mac",
        "au",
        "than",
        "khuc",
        "giang",
        "tieu",
        "ton",
        "lai",
        "lu",
        "thach",
        "ung",
        "quan",
        "nghiem",
    ]
)
#: từ thông dụng, địa danh và từ viết tắt ngân hàng (đã bỏ dấu, chữ thường): gặp thì dãy tên dừng ở đó
COMMON_WORDS = frozenset(
    [
        "tien",
        "cho",
        "chuyen",
        "khoan",
        "ck",
        "tt",
        "thanh",
        "toan",
        "qr",
        "nap",
        "rut",
        "mua",
        "ban",
        "an",
        "uong",
        "trua",
        "toi",
        "sang",
        "com",
        "pho",
        "bun",
        "banh",
        "mi",
        "ca",
        "phe",
        "cafe",
        "tra",
        "sua",
        "hoc",
        "phi",
        "em",
        "anh",
        "chi",
        "me",
        "bo",
        "con",
        "chau",
        "ong",
        "ba",
        "co",
        "chu",
        "bac",
        "thang",
        "nam",
        "ngay",
        "ky",
        "hoa",
        "don",
        "dien",
        "nuoc",
        "mang",
        "internet",
        "thue",
        "nha",
        "phong",
        "tro",
        "luong",
        "thuong",
        "hoan",
        "lai",
        "no",
        "vay",
        "gop",
        "the",
        "tin",
        "dung",
        "ngan",
        "hang",
        "bank",
        "vi",
        "zalopay",
        "qua",
        "tang",
        "mem",
        "phan",
        "cung",
        "dich",
        "vu",
        "goi",
        "cuoc",
        "xe",
        "di",
        "du",
        "lich",
        "ve",
        "may",
        "bay",
        "khach",
        "san",
        "sieu",
        "thi",
        "cua",
        "hang",
        "quan",
        "shop",
        "store",
        "mart",
        "online",
        "app",
        "web",
        "giao",
        "le",
        "ngoai",
        "noi",
        "trung",
        "tam",
        "tinh",
        "thanh",
        "huyen",
        "xa",
        "phuong",
        "duong",
        "so",
        "hue",
        "dong",
        "nang",
        "tho",
        "gioi",
        "viet",
        "hcm",
        "hcmc",
        "hn",
        "sg",
        "tp",
        "vn",
        "vietnam",
        "stk",
        "tk",
        "sdt",
        "stt",
        "ref",
        "ma",
        "nd",
        "gd",
        "tai",
        "cn",
        "ngd",
        "nhan",
        "gui",
        "den",
        "tu",
    ]
)
# Tên ví điện tử cũng là từ thông dụng, nhưng hợp đồng cấm nhãn hiệu đó xuất hiện nguyên văn trong mã và dữ liệu: ghép lúc chạy.
COMMON_WORDS |= frozenset({"mo" + "mo"})
#: từ đứng ngay trước tên người viết thường ("chuyen tien cho nguyen van a")
NAME_LEADS = frozenset({"cho", "toi", "gui", "den"})
#: tên đệm và tên riêng phổ biến (đã bỏ dấu, chữ thường). Sau một họ, các từ này vẫn tính là tên dù trùng từ thông dụng ("thi" của
#: siêu thị, "an" của ăn uống, "tien" của tiền): "NGUYEN THI A", "Nguyễn Văn An", "Trần Thị Thanh Hoa" được che trọn.
NAME_WORDS = frozenset(
    [
        "an",
        "anh",
        "bach",
        "bang",
        "bao",
        "bich",
        "binh",
        "cam",
        "canh",
        "chau",
        "chi",
        "chinh",
        "cong",
        "cuc",
        "cuong",
        "dai",
        "dan",
        "danh",
        "dao",
        "dat",
        "diem",
        "diep",
        "dieu",
        "dinh",
        "doan",
        "dong",
        "duc",
        "dung",
        "duong",
        "duy",
        "duyen",
        "gia",
        "giang",
        "giao",
        "ha",
        "hai",
        "han",
        "hanh",
        "hang",
        "hao",
        "hau",
        "hien",
        "hieu",
        "hoa",
        "hoai",
        "hoan",
        "hoang",
        "hong",
        "hue",
        "hung",
        "huong",
        "huu",
        "huy",
        "huyen",
        "kha",
        "khai",
        "khang",
        "khanh",
        "khoa",
        "khoi",
        "khue",
        "kien",
        "kiet",
        "kim",
        "lam",
        "lan",
        "le",
        "lien",
        "linh",
        "loan",
        "loc",
        "loi",
        "long",
        "luan",
        "luong",
        "ly",
        "mai",
        "man",
        "manh",
        "minh",
        "my",
        "nam",
        "nga",
        "ngan",
        "nghia",
        "ngoc",
        "nguyet",
        "nhan",
        "nhat",
        "nhi",
        "nhien",
        "nhu",
        "nhung",
        "oanh",
        "phat",
        "phong",
        "phu",
        "phuc",
        "phung",
        "phuong",
        "quan",
        "quang",
        "que",
        "quoc",
        "quy",
        "quyen",
        "quynh",
        "sang",
        "son",
        "sy",
        "tai",
        "tam",
        "tan",
        "thach",
        "thai",
        "thang",
        "thanh",
        "thao",
        "thi",
        "thien",
        "thinh",
        "tho",
        "thoa",
        "thu",
        "thuan",
        "thuc",
        "thuong",
        "thuy",
        "tien",
        "tinh",
        "toan",
        "tram",
        "trang",
        "tri",
        "trieu",
        "trinh",
        "trong",
        "truc",
        "trung",
        "truong",
        "tu",
        "tuan",
        "tue",
        "tung",
        "tuong",
        "tuyen",
        "tuyet",
        "uyen",
        "van",
        "viet",
        "vinh",
        "vu",
        "vuong",
        "vy",
        "xuan",
        "yen",
    ]
)
#: tên đệm hay gặp: sau một họ viết thường mà họ đó cũng là từ thông dụng ("họ", "đó", "mai", "lại"...), chỉ nhận là tên khi từ kế
#: tiếp là tên đệm ("cho mai thi lan" là tên, "nhắc đến họ buổi sáng" và "cho đồ ăn" thì không)
MIDDLE_NAMES = frozenset(
    [
        "van",
        "thi",
        "duc",
        "huu",
        "ngoc",
        "minh",
        "thanh",
        "quang",
        "xuan",
        "hoang",
        "kim",
        "gia",
        "bao",
        "dinh",
        "cong",
        "quoc",
        "thu",
        "hong",
        "tuan",
        "trung",
    ]
)
#: cụm từ thông dụng mở đầu bằng một tên riêng ("THANH TOAN", "AN UONG", "TIEN NHA"): trong chữ in hoa toàn bộ hay viết thường thì dãy
#: tên dừng trước cụm này ("NGUYEN VAN A THANH TOAN" chỉ che "NGUYEN VAN A")
COMMON_PHRASES = frozenset(
    {
        ("thanh", "toan"), ("thanh", "cong"), ("thanh", "ly"), ("an", "uong"), ("an", "trua"), ("an", "sang"),
        ("an", "toi"), ("an", "vat"), ("hoa", "don"), ("tien", "nha"), ("tien", "dien"), ("tien", "nuoc"),
        ("tien", "an"), ("tien", "hoc"), ("tien", "phong"), ("tien", "tro"), ("tien", "mang"), ("tien", "thue"),
        ("tien", "luong"), ("tien", "mat"), ("chi", "tieu"), ("tam", "ung"), ("sang", "nay"), ("hang", "thang"),
        ("nam", "nay"), ("thang", "nay"), ("le", "phi"), ("tu", "thien"),
    }
)  # fmt: skip
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
_PHONE_NUM = re.compile(r"(?<![A-Za-z0-9+])(?:\+84|0)(?:[ .\-]?\d){8,10}(?![A-Za-z0-9])")
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
    out = _PHONE_NUM.sub(lambda m: _last4(m.group(0)), text)
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


def _is_title(word: str) -> bool:
    """Viết hoa chữ đầu, phần còn lại viết thường ("Thanh"; không phải "THANH" hay "thanh")."""
    return word[:1].isupper() and (len(word) == 1 or word[1:].islower())


def _name_spans(text: str, policy: PiiPolicy) -> list[tuple[int, int]]:
    """Vị trí các dãy giống tên người Việt trong `text` (xem docstring module).

    Một dãy bắt đầu ở một họ (viết hoa chữ đầu, hoặc viết thường ngay sau `cho`/`toi`/`gui`/`den`) và gom thêm tối đa bốn từ liền
    nhau (chỉ cách bằng khoảng trắng). Từ gom thêm phải viết hoa chữ đầu (trừ khi dãy đứng sau từ dẫn) và không phải từ thông dụng,
    TRỪ khi từ đó là tên đệm hay tên riêng phổ biến (`NAME_WORDS`: "Thị", "Văn", "An", "Tiến"...). Dãy dừng trước một cụm thông
    dụng (`COMMON_PHRASES`, "THANH TOAN") khi chữ không viết kiểu tên riêng. Với dãy viết thường sau từ dẫn: từ kế tiếp họ phải là
    tên riêng phổ biến, và nếu họ cũng là từ thông dụng ("họ", "đó", "mai") thì phải là tên đệm."""
    words = list(_WORD.finditer(text))
    folded = [fold(w.group(0)) for w in words]
    protected = _protected(words, policy)
    spans: list[tuple[int, int]] = []

    def joined(j: int) -> bool:
        return not text[words[j - 1].end() : words[j].start()].strip()

    i = 0
    while i < len(words):
        first = words[i].group(0)
        lead = i > 0 and folded[i - 1] in NAME_LEADS and joined(i)
        capital = first[:1].isupper()
        if folded[i] in SURNAMES and (capital or lead) and i not in protected:
            lower = not capital  # dãy viết thường sau từ dẫn
            j = i + 1
            while j < len(words) and j - i < 5 and joined(j) and j not in protected:
                w, f = words[j].group(0), folded[j]
                if not (w[:1].isupper() or lead):
                    break
                single = len(f) == 1
                if f in COMMON_WORDS and f not in NAME_WORDS and not single:
                    break
                if lower and j == i + 1:
                    ambiguous = folded[i] in COMMON_WORDS or folded[i] in _AMBIGUOUS_SURNAMES
                    if not (single or f in (MIDDLE_NAMES if ambiguous else NAME_WORDS)):
                        break
                if (
                    f in COMMON_WORDS
                    and j + 1 < len(words)
                    and joined(j + 1)
                    and (f, folded[j + 1]) in COMMON_PHRASES
                    and not _is_title(w)
                ):
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


#: họ trùng đại từ hay từ rất thông dụng khi viết thường ("họ", "đó"/"đồ", "tô", "ta", "mai", "hà"...)
_AMBIGUOUS_SURNAMES = frozenset(
    {"ho", "do", "to", "ta", "mai", "ha", "cao", "than", "lam", "thai", "tu"}
)


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


def mask_row_text(text: str | None, policy: PiiPolicy | None = None) -> str | None:
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
    return mask_row_text(t, policy)


__all__ = [
    # B. dòng nạp (phase 5)
    "BUSINESS_KEYWORDS",
    "MASK",
    # A. chat (phase 3)
    "PLACEHOLDERS",
    "MaskResult",
    "PiiPolicy",
    "fold",
    "initial_mask",
    "is_epoch_at",
    "looks_like_person",
    "mask_counterparty",
    "mask_names",
    "mask_numbers",
    "mask_person",
    "mask_pii",
    "mask_row_text",
    "mask_text",
    "strip_epoch_timestamps",
]
