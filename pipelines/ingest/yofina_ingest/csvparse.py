"""Bộ đọc CSV sao kê ngân hàng, tất định (không gọi model): đoán bảng mã và dấu phân cách, tìm dòng tiêu đề, ánh xạ cột theo
bảng tên cột đã biết (tiếng Việt có dấu, không dấu, tiếng Anh), đọc số tiền có dấu hoặc hai cột ghi nợ/ghi có.

Cột lạ (không ánh xạ được ngày hoặc số tiền) thì trả `needs_column_map = True` kèm tiêu đề; người gọi hỏi một model nhỏ CHỈ để ánh
xạ tên cột (xem `extract.py`) rồi gọi lại `parse_rows` với ánh xạ đó. Mọi giá trị ô được xem là DỮ LIỆU: ô văn bản bắt đầu bằng
`=`, `+`, `-`, `@` bị trung hòa; ô số tiền là công thức thì dòng đó bị loại (`CsvRow.problem`), không đoán.
"""

from __future__ import annotations

import csv
import io
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from yofina_core.params import fold_text
from yofina_ingest.normalize import (
    clean_text,
    is_formula_cell,
    neutralize,
    parse_amount,
    parse_date,
)

DELIMITERS = (",", ";", "\t", "|")
HEADER_SCAN_ROWS = 15
SAMPLE_ROWS = 40

#: vai của cột -> các tên cột đã biết (đã bỏ dấu, chữ thường). Khớp đúng tên trước, rồi tên dài nhất nằm trong tiêu đề.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "date": (
        "ngay giao dich",
        "ngay gd",
        "ngay hach toan",
        "ngay hieu luc",
        "ngay",
        "thoi gian giao dich",
        "thoi gian",
        "transaction date",
        "trans. date",
        "trans date",
        "txn. date",
        "txn date",
        "posting date",
        "value date",
        "date",
    ),
    "description": (
        "noi dung chi tiet",
        "noi dung giao dich",
        "noi dung",
        "dien giai giao dich",
        "dien giai",
        "mo ta giao dich",
        "mo ta",
        "txn. description",
        "txn description",
        "transaction description",
        "narrative",
        "details",
        "description",
        "remarks",
    ),
    "debit": (
        "so tien ghi no",
        "phat sinh no",
        "tien ra",
        "so tien chi",
        "so tien rut",
        "ghi no",
        "rut ra",
        "chi ra",
        "debit amount",
        "debit",
        "withdrawal",
        "withdrawals",
        "money out",
        "paid out",
    ),
    "credit": (
        "so tien ghi co",
        "phat sinh co",
        "tien vao",
        "so tien thu",
        "so tien nop",
        "ghi co",
        "nop vao",
        "thu vao",
        "credit amount",
        "credit",
        "deposit",
        "deposits",
        "money in",
        "paid in",
    ),
    "amount": (
        "so tien giao dich",
        "so tien",
        "gia tri giao dich",
        "gia tri",
        "amount",
        "txn. amount",
        "transaction amount",
    ),
    "balance": ("so du sau giao dich", "so du", "balance", "running balance", "closing balance"),
    "counterparty": (
        "ten doi tac",
        "doi tac",
        "nguoi nhan",
        "ten nguoi nhan",
        "ben thu huong",
        "ten tai khoan doi ung",
        "tai khoan doi ung",
        "beneficiary",
        "counterparty",
        "payee",
    ),
    "reference": ("so tham chieu", "ma giao dich", "ma tham chieu", "reference", "ref no", "ref."),
}
REQUIRED_ROLES = ("date",)


class CsvError(Exception):
    """Tệp không đọc được thành bảng (rỗng, không có dòng dữ liệu, quá nhiều dòng...). `code` ghép với mã lỗi của job."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CsvTable:
    encoding: str
    delimiter: str
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]  # dòng dữ liệu (đã bỏ dòng trống); chỉ số + 1 là `source_row`
    header_found: (
        bool  # tìm được dòng tiêu đề bằng bảng tên cột (không thì dòng đầu được coi là tiêu đề)
    )


@dataclass(frozen=True)
class Mapping_:
    """Ánh xạ vai -> chỉ số cột."""

    date: int | None = None
    description: int | None = None
    amount: int | None = None
    debit: int | None = None
    credit: int | None = None
    counterparty: int | None = None
    balance: int | None = None
    reference: int | None = None
    date_order: str = "dmy"

    @property
    def usable(self) -> bool:
        return self.date is not None and (
            self.amount is not None or self.debit is not None or self.credit is not None
        )

    def as_names(self, header: Sequence[str]) -> dict[str, str | None]:
        return {
            r: (header[i] if (i := getattr(self, r)) is not None and i < len(header) else None)
            for r in ("date", "description", "amount", "debit", "credit", "counterparty")
        }


@dataclass
class CsvRow:
    source_row: int
    date: date | None = None
    partial_year: bool = False
    amount_vnd: int | None = None  # luôn dương
    direction: str | None = None  # out | in
    description: str | None = None  # CHƯA che PII (che ở `extract`), đã trung hòa công thức
    counterparty: str | None = None
    reference: str | None = None
    confidence: float = 0.99
    problem: str | None = (
        None  # lý do dòng bị loại: formula_amount, no_date, no_amount, ambiguous_amount, bad_date
    )
    notes: list[str] = field(default_factory=list)


# --- đọc thô ----------------------------------------------------------------------------------------------------------------------
def decode_bytes(data: bytes) -> tuple[str, str]:
    """`(văn bản NFC, bảng mã)`. Thứ tự: BOM UTF-8/UTF-16, UTF-8 nghiêm ngặt, cp1258 (Windows tiếng Việt), cp1252 rồi latin-1."""
    text, enc = _decode(data)
    return unicodedata.normalize("NFC", text), enc


def _decode(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8"), "utf-8-sig"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "utf-16"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    for enc in ("cp1258", "cp1252"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1"), "latin-1"


def _parse_lines(text: str, delimiter: str) -> list[list[str]]:
    return [
        list(r)
        for r in csv.reader(
            io.StringIO(text), delimiter=delimiter, quotechar='"', skipinitialspace=False
        )
    ]


def sniff_delimiter(text: str) -> str:
    """Dấu phân cách có nhiều cột nhất mà các dòng đầu đồng nhất. Không dùng `csv.Sniffer` vì số `48,000` trong ngoặc kép làm nó lạc."""
    sample = "\n".join(text.splitlines()[:30])
    best = (0.0, ",")
    for d in DELIMITERS:
        try:
            rows = [r for r in _parse_lines(sample, d) if any(c.strip() for c in r)]
        except csv.Error:
            continue
        if len(rows) < 1:
            continue
        counts = Counter(len(r) for r in rows)
        width, freq = counts.most_common(1)[0]
        if width < 2:
            continue
        score = (freq / len(rows)) * 100 + width
        if score > best[0]:
            best = (score, d)
    return best[1]


def _role_of(folded_header: str) -> tuple[str, int] | None:
    """Vai tốt nhất của một tiêu đề (đã bỏ dấu): khớp đúng tên thì ưu tiên, sau đó tên dài nhất nằm trong tiêu đề."""
    best: tuple[int, str] | None = None
    for role, names in COLUMN_ALIASES.items():
        for n in names:
            if folded_header == n:
                score = 1000 + len(n)
            elif len(n) >= 4 and n in folded_header:
                score = len(n)
            else:
                continue
            if best is None or score > best[0]:
                best = (score, role)
    return (best[1], best[0]) if best else None


def map_header(header: Sequence[str]) -> Mapping_:
    """Ánh xạ tiêu đề -> vai bằng bảng tên cột đã biết. Mỗi vai lấy cột có điểm cao nhất."""
    chosen: dict[str, tuple[int, int]] = {}
    for i, h in enumerate(header):
        hit = _role_of(fold_text(h))
        if hit is None:
            continue
        role, score = hit
        if role not in chosen or score > chosen[role][1]:
            chosen[role] = (i, score)
    return Mapping_(**{r: chosen[r][0] for r in chosen})


def _header_score(row: Sequence[str]) -> int:
    roles = set()
    for h in row:
        hit = _role_of(fold_text(h))
        if hit:
            roles.add(hit[0])
    return len(roles)


def read_table(data: bytes, *, max_rows: int) -> CsvTable:
    """Bóc tệp thành tiêu đề và các dòng dữ liệu. Ném `CsvError` khi rỗng hoặc vượt `max_rows` dòng dữ liệu."""
    if not data.strip():
        raise CsvError("empty", "Tệp CSV trống.")
    text, enc = decode_bytes(data)
    text = text.replace("\x00", "")
    delimiter = sniff_delimiter(text)
    try:
        grid = [r for r in _parse_lines(text, delimiter) if any(c.strip() for c in r)]
    except csv.Error as exc:
        raise CsvError("malformed", "Không đọc được cấu trúc của tệp CSV.") from exc
    if len(grid) < 2:
        raise CsvError("no_rows", "Tệp CSV không có dòng dữ liệu nào.")
    head_idx, best = 0, -1
    for i, row in enumerate(grid[:HEADER_SCAN_ROWS]):
        score = _header_score(row)
        if score > best:
            head_idx, best = i, score
    found = best >= 2
    if not found:
        head_idx = 0
    header = tuple(c.strip() for c in grid[head_idx])
    body = tuple(tuple(c for c in row) for row in grid[head_idx + 1 :])
    if len(body) > max_rows:
        raise CsvError(
            "too_many_rows",
            f"Tệp có {len(body)} dòng, vượt giới hạn {max_rows} dòng mỗi lần nạp. Hãy chia nhỏ tệp.",
        )
    return CsvTable(enc, delimiter, header, body, found)


def mapping_from_names(
    header: Sequence[str], names: Mapping[str, str | None], order: str | None
) -> Mapping_:
    """Ánh xạ do model trả (tên cột nguyên văn) -> chỉ số cột. Tên không có trong tiêu đề bị bỏ (model không được bịa cột)."""
    index = {h.strip(): i for i, h in enumerate(header)}
    fields = {}
    for role in ("date", "description", "amount", "debit", "credit", "counterparty"):
        name = names.get(role)
        if name and name.strip() in index:
            fields[role] = index[name.strip()]
    return Mapping_(**fields, date_order=order if order in ("dmy", "ymd", "mdy") else "dmy")


def merge_mapping(auto: Mapping_, extra: Mapping_) -> Mapping_:
    """Ánh xạ tự động giữ nguyên; chỉ điền vai còn thiếu từ `extra`."""
    vals = {}
    for r in (
        "date",
        "description",
        "amount",
        "debit",
        "credit",
        "counterparty",
        "balance",
        "reference",
    ):
        a = getattr(auto, r)
        vals[r] = a if a is not None else getattr(extra, r)
    return Mapping_(
        **vals, date_order=extra.date_order if auto.date_order == "dmy" else auto.date_order
    )


# --- đọc dòng ---------------------------------------------------------------------------------------------------------------------
def _cell(row: Sequence[str], idx: int | None) -> str:
    return row[idx].strip() if idx is not None and idx < len(row) else ""


def _amount(raw: str) -> tuple[int | None, bool]:
    """`(giá trị có dấu, là công thức)`. Ô trống thì `(None, False)`."""
    if not raw:
        return None, False
    if is_formula_cell(raw):
        return None, True
    return parse_amount(raw), False


def parse_rows(table: CsvTable, mapping: Mapping_, *, today: date) -> list[CsvRow]:
    """Mỗi dòng dữ liệu thành một `CsvRow` (kể cả dòng bị loại, có `problem`, để người gọi đếm và báo)."""
    out: list[CsvRow] = []
    signed_col = _is_signed_column(table, mapping.amount)
    for n, raw in enumerate(table.rows, start=1):
        row = CsvRow(source_row=n)
        d_raw = _cell(raw, mapping.date)
        parsed, partial = parse_date(d_raw, today=today, order=mapping.date_order)
        row.partial_year = partial
        if is_formula_cell(d_raw):
            row.problem = "formula_date"
            out.append(row)
            continue
        if parsed is None:
            row.problem = "no_date"  # thường là dòng tổng hay số dư đầu kỳ, không phải giao dịch
            out.append(row)
            continue
        row.date = parsed
        desc_raw = _cell(raw, mapping.description)
        row.description = neutralize(clean_text(desc_raw, 400))
        row.counterparty = neutralize(clean_text(_cell(raw, mapping.counterparty), 200))
        row.reference = clean_text(_cell(raw, mapping.reference), 60)
        if mapping.debit is not None or mapping.credit is not None:
            debit, f1 = _amount(_cell(raw, mapping.debit))
            credit, f2 = _amount(_cell(raw, mapping.credit))
            if f1 or f2:
                row.problem = "formula_amount"
            elif debit and credit:
                row.problem = "ambiguous_amount"
            elif debit:
                row.amount_vnd, row.direction = abs(debit), "out"
            elif credit:
                row.amount_vnd, row.direction = abs(credit), "in"
            elif mapping.amount is not None:
                _single(row, raw, mapping, signed_col)
            else:
                row.problem = "no_amount"
        elif mapping.amount is not None:
            _single(row, raw, mapping, signed_col)
        else:
            row.problem = "no_amount"
        if row.problem is None and not row.amount_vnd:
            row.problem = "no_amount"
        out.append(row)
    return out


def _single(row: CsvRow, raw: Sequence[str], mapping: Mapping_, signed_col: bool) -> None:
    """Một cột số tiền: nếu cột có số âm thì là cột có dấu (âm là chi, dương là thu). Cột không có dấu nào thì không biết chiều:
    coi là chi nhưng giảm độ tin cậy để dòng đi vào hàng chờ duyệt."""
    cell = _cell(raw, mapping.amount)
    value, formula = _amount(cell)
    if formula:
        row.problem = "formula_amount"
        return
    if not value:
        row.problem = "no_amount"
        return
    row.amount_vnd = abs(value)
    if value < 0:
        row.direction = "out"
    elif signed_col or cell.lstrip().startswith("+"):
        row.direction = "in"
    else:
        row.direction = "out"
        row.confidence = 0.6
        row.notes += ["unsigned_amount", "direction_assumed"]


def _is_signed_column(table: CsvTable, idx: int | None) -> bool:
    if idx is None:
        return False
    for r in table.rows:
        cell = _cell(r, idx)
        if cell.startswith(("-", "−", "(")) and not is_formula_cell(cell):
            return True
    return False


def sample_for_mapping(table: CsvTable) -> list[list[str]]:
    """Vài dòng đầu để model nhỏ đoán ý nghĩa cột (người gọi PHẢI che PII từng ô trước khi gửi)."""
    return [list(r) for r in table.rows[:3]]
