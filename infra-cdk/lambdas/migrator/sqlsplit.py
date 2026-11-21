"""Tách một file migration thành các câu lệnh riêng (RDS Data API không nhận nhiều câu lệnh trong một lần gọi).

Hai chế độ (hàm `split_migration`):
1. File có dòng chỉ gồm `-- @@`: theo quy ước của db/migrations (xem libs/yofina_core/src/yofina_core/migrations.py)
   cắt đúng ở các dòng đó, bỏ chú thích đứng đầu mỗi đoạn và dấu `;` cuối câu.
2. Không có dòng `-- @@`: tách theo dấu `;` bằng bộ phân tích dưới đây (`split_statements`).

`split_statements` tôn trọng: chuỗi '...' (kể cả '' và E'...\\'), định danh "...", chú thích -- và /* */ (lồng nhau),
và dollar-quote $tag$ ... $tag$ (thân hàm plpgsql, khối DO). Dấu ; chỉ kết thúc câu lệnh ở trạng thái thường.
Câu lệnh chỉ có chú thích/khoảng trắng bị bỏ.
"""
from __future__ import annotations

import hashlib
import re

_IDENT_START = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
_IDENT_CHARS = _IDENT_START | set("0123456789")


def split_statements(sql: str) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    has_code = False
    i, n = 0, len(sql)

    def flush() -> None:
        nonlocal buf, has_code
        text = "".join(buf).strip()
        if has_code and text:
            out.append(text)
        buf, has_code = [], False

    while i < n:
        c = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if c == "-" and nxt == "-":  # chú thích dòng
            j = sql.find("\n", i)
            j = n if j == -1 else j
            buf.append(sql[i:j])
            i = j
        elif c == "/" and nxt == "*":  # chú thích khối, cho phép lồng nhau
            depth, j = 1, i + 2
            while j < n and depth:
                if sql.startswith("/*", j):
                    depth += 1
                    j += 2
                elif sql.startswith("*/", j):
                    depth -= 1
                    j += 2
                else:
                    j += 1
            buf.append(sql[i:j])
            i = j
        elif c == "'":  # chuỗi; E'...' cho phép \ thoát
            escape = i > 0 and sql[i - 1] in "eE" and (i < 2 or sql[i - 2] not in _IDENT_CHARS)
            j = i + 1
            while j < n:
                if escape and sql[j] == "\\":
                    j += 2
                    continue
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            buf.append(sql[i : j + 1])
            has_code = True
            i = j + 1
        elif c == '"':
            j = i + 1
            while j < n:
                if sql[j] == '"':
                    if j + 1 < n and sql[j + 1] == '"':
                        j += 2
                        continue
                    break
                j += 1
            buf.append(sql[i : j + 1])
            has_code = True
            i = j + 1
        elif c == "$" and (i == 0 or sql[i - 1] not in _IDENT_CHARS):
            j = i + 1
            if j < n and sql[j] in _IDENT_START:
                while j < n and sql[j] in _IDENT_CHARS:
                    j += 1
            if j < n and sql[j] == "$":  # mở dollar-quote với thẻ sql[i:j+1]
                tag = sql[i : j + 1]
                end = sql.find(tag, j + 1)
                end = n if end == -1 else end + len(tag)
                buf.append(sql[i:end])
                has_code = True
                i = end
            else:  # $1 và tương tự
                buf.append(c)
                has_code = True
                i += 1
        elif c == ";":
            flush()
            i += 1
        else:
            buf.append(c)
            if not c.isspace():
                has_code = True
            i += 1
    flush()
    return out


_SEPARATOR = re.compile(r"^-- @@[ \t]*$", re.MULTILINE)
_PARAM = re.compile(r"(?<![:\w]):([A-Za-z_][A-Za-z0-9_]*)")
_DOLLAR_TAG = re.compile(r"\$[A-Za-z_]*\$")


def split_migration(sql: str) -> list[str]:
    """Tách file migration: theo dòng `-- @@` nếu có, nếu không thì theo dấu `;`."""
    if not _SEPARATOR.search(sql):
        return split_statements(sql)
    out: list[str] = []
    for chunk in _SEPARATOR.split(sql):
        lines = chunk.strip().splitlines()
        while lines and (not lines[0].strip() or lines[0].lstrip().startswith("--")):
            lines.pop(0)
        if lines:
            out.append("\n".join(lines).rstrip().removesuffix(";").rstrip())
    return out


def _strip_literals(sql: str) -> str:
    """Bỏ chú thích --, chuỗi '...' và thân $tag$...$tag$ để chỉ còn phần mã khi tìm tham số thật."""
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j == -1 else j
        elif ch == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            i = j + 1
        elif ch == "$":
            m = _DOLLAR_TAG.match(sql, i)
            if m:
                end = sql.find(m.group(0), m.end())
                i = n if end == -1 else end + len(m.group(0))
            else:
                out.append(ch)
                i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def named_params(statement: str) -> list[str]:
    """Tên các tham số :name mà câu lệnh thật sự dùng (không tính cast `::`, chú thích, chuỗi, thân $$)."""
    seen: list[str] = []
    for name in _PARAM.findall(_strip_literals(statement)):
        if name not in seen:
            seen.append(name)
    return seen


def checksum(sql: str) -> str:
    """sha256 nội dung file (CRLF chuẩn hóa thành LF), giống libs/yofina_core/migrations.py."""
    return hashlib.sha256(sql.replace("\r\n", "\n").encode("utf-8")).hexdigest()
