"""Chuẩn hóa giá trị đọc từ tệp (ngày, số tiền, văn bản) và các luật loại dòng. Hàm thuần, không I/O.

- Số tiền VND nguyên; nhận `1.250.000`, `1,250,000`, `48,000`, `-372000`, `250.000đ`, `1 250 000 VND`.
- Ngày: `dd/mm/yyyy`, `dd-mm-yyyy`, `yyyy-mm-dd`, `dd/mm/yy`, `dd/mm` (không năm: chọn năm sao cho không rơi vào tương lai).
- Ô văn bản bắt đầu bằng `=`, `+`, `-`, `@` bị trung hòa (thêm dấu nháy đơn đứng đầu) để không thành công thức khi ai đó xuất lại.
- Phát hiện văn bản giống chỉ dẫn (tấn công qua nội dung tệp) và các dòng không phải chi tiêu thật (thất bại, tự nạp tiền).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from yofina_core.params import fold_text

_CURRENCY = re.compile(r"(vnd|vnđ|₫|dong)\b\.?|(?<=\d)\s*đ\b\.?", re.I)
_FORMULA_START = ("=", "+", "-", "@")
#: một ô số tiền hợp lệ có thể bắt đầu bằng dấu: chỉ chứa chữ số, dấu phân cách, khoảng trắng và chữ tiền tệ
_NUMERIC_CELL = re.compile(r"^[+\-−]?\s*[\d.,\s]+(?:\s*(?:vnd|vnđ|đ|₫|dong))?$", re.I)


def is_formula_cell(raw: str | None) -> bool:
    """Ô có thể bị bảng tính hiểu là công thức: bắt đầu bằng `=` hoặc `@`, hoặc bằng `+`/`-` mà phần còn lại không phải số."""
    if raw is None:
        return False
    s = raw.strip()
    if not s:
        return False
    if s[0] in ("=", "@"):
        return True
    if s[0] in ("+", "-", "−"):
        return not _NUMERIC_CELL.match(s)
    return False


def neutralize(text: str | None) -> str | None:
    """Giữ nguyên nội dung nhưng thêm dấu nháy đơn trước ô có thể là công thức (`=`, `+`, `-`, `@`). Chuỗi rỗng thì None."""
    if text is None:
        return None
    s = " ".join(str(text).split())
    if not s:
        return None
    return "'" + s if s[0] in _FORMULA_START else s


def clean_text(text: str | None, limit: int) -> str | None:
    """Gộp khoảng trắng, bỏ ký tự điều khiển, cắt về `limit` ký tự. Rỗng thì None."""
    if text is None:
        return None
    s = "".join(ch for ch in str(text) if unicodedata.category(ch)[0] != "C" or ch in "\t\n ")
    s = " ".join(s.split())
    return s[:limit].rstrip() or None


def parse_amount(raw: str | int | float | None) -> int | None:
    """Số tiền VND nguyên (có thể âm) từ chuỗi; None nếu không phải số. Số thập phân bị làm tròn (VND không có phần lẻ)."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return round(raw)
    s = str(raw).strip()
    if not s:
        return None
    neg = s.startswith(("-", "−")) or (s.startswith("(") and s.endswith(")"))
    s = _CURRENCY.sub("", s)
    s = re.sub(r"[^\d.,]", "", s)
    if not s or not re.search(r"\d", s):
        return None
    if "." in s and "," in s:
        dec_sep = "," if s.rfind(",") > s.rfind(".") else "."
        thou_sep = "." if dec_sep == "," else ","
        s = s.replace(thou_sep, "")
        whole, _, frac = s.partition(dec_sep)
        value = int(whole or "0") + (int(float("0." + frac) + 0.5) if frac else 0)
    else:
        sep = "." if "." in s else ("," if "," in s else "")
        if not sep:
            value = int(s)
        else:
            parts = s.split(sep)
            if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):
                value = int("".join(parts))  # ngăn cách hàng nghìn
            elif len(parts) == 2 and len(parts[1]) in (1, 2):
                value = int(parts[0] or "0") + int(
                    float("0." + parts[1]) + 0.5
                )  # phần thập phân (làm tròn lên từ .5)
            else:
                value = int("".join(parts))
    return -value if neg else value


_DATE_ISO = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[T\s].*)?$")
_DATE_DMY = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2}|\d{4})(?:[T\s,].*)?$")
_DATE_DM = re.compile(r"^(\d{1,2})[-/.](\d{1,2})$")


def _mk(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_date(
    raw: str | None,
    *,
    today: date,
    year_hint: int | None = None,
    order: str = "dmy",
) -> tuple[date | None, bool]:
    """`(ngày, thiếu_năm)`. Thiếu năm thì dùng `year_hint` nếu có, không thì năm của `today` (lùi một năm nếu rơi vào tương lai).

    `order` chỉ để quyết định `a/b/yyyy` là ngày/tháng (`dmy`, mặc định của Việt Nam) hay tháng/ngày (`mdy`)."""
    if not raw:
        return None, False
    s = " ".join(str(raw).split())
    m = _DATE_ISO.match(s)
    if m:
        return _mk(int(m.group(1)), int(m.group(2)), int(m.group(3))), False
    m = _DATE_DMY.match(s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        d, mo = (b, a) if order == "mdy" else (a, b)
        if order == "dmy" and mo > 12 >= d:  # rõ ràng là tháng/ngày
            d, mo = mo, d
        return _mk(y, mo, d), False
    m = _DATE_DM.match(s)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        if year_hint:
            return _mk(year_hint, mo, d), True
        cand = _mk(today.year, mo, d)
        if cand is None:  # 29/02 ngoài năm nhuận
            return None, True
        if cand > today:
            cand = _mk(today.year - 1, mo, d)
        return cand, True
    return None, False


# --- luật loại dòng ---------------------------------------------------------------------------------------------------------------
_FAILED = re.compile(
    r"\b(khong thanh cong|that bai|khong thuc hien duoc|da huy|bi huy|bi tu choi|tu choi|failed|declined|cancel+ed|rejected|"
    r"loi giao dich|giao dich loi|chua thanh cong|dang xu ly|cho xu ly|pending)\b"
)
_SELF_TOPUP = re.compile(
    r"\bnap tien\b.*\b(tu|vao)\b.*\b(the|tai khoan|tk|vi|ngan hang|bank)\b|"
    r"\b(chuyen|nap) (tien )?(giua|sang|vao) (cac )?(tai khoan|vi|the) (cua )?(minh|toi|ban than)\b|"
    r"\brut tien (tu )?vi\b.*\b(ve|vao)\b.*\b(tai khoan|the|ngan hang)\b|"
    r"\b(top[- ]?up|cash[- ]?in)\b.*\b(from|tu)\b"
)
_NOT_SELF_TOPUP = re.compile(
    r"\b(dien thoai|data|3g|4g|game|steam|sim|the cao|di dong|viettel|mobifone|vinaphone)\b"
)
#: rút tiền mặt (ATM, tại quầy): tiền thành tiền mặt của chính người dùng, ứng dụng không theo dõi tiền mặt nên không ghi thành khoản chi
#: (quyết định của chủ dự án 24/11). "Thẻ ATM" (thanh toán bằng thẻ ghi nợ) không khớp vì phải có "rút tiền" hay "withdrawal".
_CASH_WITHDRAWAL = re.compile(
    r"\brut tien (mat\b|(\w+ ){0,3}(atm|quay)\b)|"
    r"\b(atm|cash) withdrawal\b|\bwithdrawal\b.{0,20}\batm\b"
)
#: phí của lần rút tiền là khoản chi thật (phí ngân hàng), không loại
_CASH_FEE = re.compile(r"\b(phi|fee|charge)\b")

#: câu giống chỉ dẫn gửi cho trợ lý hay hệ thống (đã bỏ dấu, chữ thường); chỉ để GẮN CỜ, không bao giờ làm theo
_INSTRUCTION = re.compile(
    r"\b(ignore|disregard|forget|override)\b.{0,40}\b(instruction|instructions|previous|above|prior|rules?)\b|"
    r"\b(bo qua|quen)\b.{0,30}\b(huong dan|chi dan|chi thi|lenh|truoc do|tren)\b|"
    r"\b(system|assistant|developer|admin|root)\s*(prompt|message|note)?\s*:|"
    r"\b(he thong|tro ly|bot)\b.{0,25}\b(hay|phai|can|duoc yeu cau|vui long|please|must|should)\b|"
    r"\b(goi|call|invoke|use|run|chay|dung)\b.{0,20}\b(tool|cong cu|function)\b|"
    r"\b(move_between_jars|record_transaction|assign_jar|save_jars|confirm_salary|confirm_rows|update_profile|add_payee|"
    r"schedule_nudge)\b|"
    r"\b(tu dong|auto)[ -]?(duyet|approve|confirm|xac nhan|them)\b|"
    r"\b(them|add|thay doi|change)\b.{0,20}\b(nguoi nhan|payee|beneficiary)\b|"
    r"\b(chuyen|gui|transfer|send)\b.{0,15}\b(het|toan bo|all|everything|tat ca)\b.{0,10}\b(tien|money|balance|so du)\b|"
    r"\bdo not (tell|show|inform)|\bkhong (duoc )?(noi|bao|cho) (nguoi dung|user)\b"
)


def folded(text: str | None) -> str:
    return fold_text(text or "")


def looks_failed(*texts: str | None) -> bool:
    return any(_FAILED.search(folded(t)) for t in texts if t)


def looks_like_self_topup(*texts: str | None) -> bool:
    """Tiền chuyển sang chỗ khác của chính người dùng (không phải chi tiêu hay thu nhập): nạp tiền vào ví từ thẻ hay tài khoản của
    mình, chuyển giữa tài khoản của mình, rút tiền mặt (ATM, tại quầy). Nạp điện thoại và phí rút tiền không tính."""
    for t in texts:
        f = folded(t)
        if f and _SELF_TOPUP.search(f) and not _NOT_SELF_TOPUP.search(f):
            return True
        if f and _CASH_WITHDRAWAL.search(f) and not _CASH_FEE.search(f):
            return True
    return False


def looks_like_instruction(*texts: str | None) -> bool:
    return any(_INSTRUCTION.search(folded(t)) for t in texts if t)
