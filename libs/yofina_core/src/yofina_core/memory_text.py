"""Chữ của bản ghi bộ nhớ dài hạn (AgentCore Memory): một nơi cho agent (đọc vào prompt) và Lambda ledger (`GET /memory`).

Hai bên phải hiển thị và khử trùng giống nhau, nếu không thì câu kể "bạn nhớ gì về mình" và màn Bộ nhớ của tôi lệch nhau (kiểm lại
Runtime v23, 24/11: agent đã khử trùng, REST chưa). Ở đây chỉ có hàm thuần, không gọi dịch vụ:

- `record_text`: chữ chính của một bản ghi. Strategy sở thích trả JSON `{context, preference, categories}` (tài liệu "System prompt for
  user preference memory strategy"), strategy sự thật trả `{fact}`; lấy trường nội dung, không lấy `context`.
- `same_meaning`, `dedupe_by_meaning`: bỏ bản ghi lặp ý giữa sở thích và sự thật (hai strategy cùng trích một câu thành hai bản ghi).
  So gần đúng theo tập từ, không gọi model.
- `drop_empty_labels`: bỏ mẩu nhãn rỗng ("Thời điểm: ,", "Thời điểm: (mili giây).") còn lại sau khi bỏ dấu thời gian Unix mà bước tóm
  tắt chép vào, và dấu câu thừa đi kèm.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

#: Trường nội dung của bản ghi JSON, theo thứ tự ưu tiên (`context` là lý do trích, chỉ dùng khi không có gì khác).
CONTENT_KEYS = ("preference", "fact", "text", "context")
#: Thứ tự ưu tiên khi khử trùng: gặp hai bản cùng ý thì giữ bản của loại đứng trước.
DEDUP_KIND_ORDER = ("preference", "fact")


def record_text(content: Any) -> str:
    """Chữ chính của một bản ghi (`content.text`); bản ghi JSON thì lấy trường nội dung đầu tiên khác rỗng trong `CONTENT_KEYS`."""
    raw = content.get("text") if isinstance(content, Mapping) else None
    if not isinstance(raw, str):
        return ""
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            obj = json.loads(raw)
        except ValueError:
            return raw
        if isinstance(obj, Mapping):
            for key in CONTENT_KEYS:
                value = obj.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return raw


# --- khử trùng ------------------------------------------------------------------------------------
#: Từ đệm bỏ qua khi so hai bản ghi có cùng ý không (chữ thường, CÒN dấu: bỏ dấu thì "tối" trùng "tôi", "buổi tối" thành trùng
#: "buổi sáng").
DEDUP_STOPWORDS = frozenset(
    {
        "người",
        "dùng",
        "muốn",
        "mong",
        "mình",
        "tôi",
        "em",
        "bạn",
        "là",
        "thì",
        "cho",
        "vào",
        "của",
        "nhé",
        "hãy",
        "được",
        "rằng",
        "luôn",
        "và",
        "các",
        "những",
        "sẽ",
        "đã",
        "đang",
        "the",
        "user",
        "wants",
        "to",
        "a",
    }
)
_WORD_RE = re.compile(r"[^\W_]+")
#: Hai bản ghi cùng ý khi hệ số Dice của tập từ (đã bỏ từ đệm) đạt ngưỡng này: "Ưu tiên để dành cho hũ Du lịch" và "Người dùng muốn
#: ưu tiên để dành tiền vào hũ Du lịch." là 0,93; "Không nhắc buổi sáng" và "Không nhắc buổi tối" là 0,75 (giữ cả hai).
DEDUP_MIN_DICE = 0.8


def _words(text: str) -> frozenset[str]:
    t = unicodedata.normalize("NFC", text).lower()
    return frozenset(w for w in _WORD_RE.findall(t) if w not in DEDUP_STOPWORDS)


def same_meaning(a: str, b: str) -> bool:
    """Hai chữ bản ghi nói cùng một ý: giống hệt sau khi chuẩn hóa, hoặc tập từ nội dung trùng tới `DEDUP_MIN_DICE`."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return " ".join(a.lower().split()) == " ".join(b.lower().split())
    return wa == wb or 2 * len(wa & wb) / (len(wa) + len(wb)) >= DEDUP_MIN_DICE


def dedupe_by_meaning[T](
    items: Iterable[T],
    *,
    text: Callable[[T], str],
    kind: Callable[[T], str],
    kinds: Sequence[str] = DEDUP_KIND_ORDER,
) -> list[T]:
    """Bỏ mục lặp ý trong các loại `kinds`, GIỮ thứ tự gốc của các mục còn lại.

    Gặp hai mục cùng ý thì giữ mục của loại đứng trước trong `kinds` (sở thích trước sự thật), cùng loại thì giữ mục đứng trước. Mục
    thuộc loại khác (tóm tắt phiên...) không bị so và luôn giữ."""
    seq = list(items)
    rank = {k: i for i, k in enumerate(kinds)}
    order = sorted(
        (i for i, it in enumerate(seq) if kind(it) in rank), key=lambda i: (rank[kind(seq[i])], i)
    )
    kept: list[int] = []
    for i in order:
        if any(same_meaning(text(seq[i]), text(seq[j])) for j in kept):
            continue
        kept.append(i)
    keep = set(kept)
    return [it for i, it in enumerate(seq) if kind(it) not in rank or i in keep]


# --- mẩu nhãn rỗng ----------------------------------------------------------------------------------
_SENTENCE_END = r"(?:[.!?](?=\s|$)|\n|$)"
#: Nhãn ngắn (1 đến 5 từ, không số) ở đầu câu hoặc đầu dòng, theo sau là dấu hai chấm mà KHÔNG có giá trị: ngay sau là dấu câu, hoặc
#: chỉ một cụm đơn vị trong ngoặc ("(mili giây)"). Nhãn đứng cuối dòng ("Tóm tắt:") là tiêu đề, giữ nguyên. Cả câu có nhãn rỗng bị bỏ:
#: phần còn lại của nó chỉ là phần ước tính của dấu thời gian đã bị bỏ (giờ thật của máy chủ, không phải ngày mô phỏng của ứng dụng).
_EMPTY_LABEL_RE = re.compile(
    r"(?:^|(?<=[\n.!?;]))[ \t]*(?:[-*•][ \t]+)?"
    r"[^\W\d_][^\W\d_]*(?:[ \t]+[^\W\d_][^\W\d_]*){0,4}[ \t]*:[ \t]*"
    r"(?:\([^()\d]{0,20}\)[ \t]*(?=[,;.!?]|\n|$)|(?=[,;.!?]))"
    rf"[^\n]*?{_SENTENCE_END}",
    re.MULTILINE,
)
_SPACE_BEFORE_PUNCT_RE = re.compile(r"[ \t]+([,.;:!?])")
_REPEATED_PUNCT_RE = re.compile(r"([.;,:!?])(?:[ \t]*[.;,])+")
_LEADING_PUNCT_RE = re.compile(r"^[ \t]*[.,;:!?]+[ \t]*", re.MULTILINE)


def _clean_line(line: str) -> str:
    out = _EMPTY_LABEL_RE.sub("", line)
    out = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", out)
    out = _REPEATED_PUNCT_RE.sub(r"\1", out)
    out = _LEADING_PUNCT_RE.sub("", out).strip()
    return out[:1].upper() + out[1:]


def drop_empty_labels(text: str) -> str:
    """Bỏ câu có nhãn mà không còn giá trị ("Thời điểm: , ước tính khoảng ... (UTC).", "Thời điểm: (mili giây).") và dấu câu thừa
    (". .", " ,", dấu câu đứng đầu dòng) rồi viết hoa lại chữ đầu, CHỈ trên dòng có mẩu như vậy; dòng khác giữ nguyên từng ký tự.
    Dòng chỉ còn rỗng thì bỏ."""
    if not text:
        return ""
    lines = []
    for line in text.split("\n"):
        probe = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", line)
        dirty = bool(
            _EMPTY_LABEL_RE.search(line)
            or _REPEATED_PUNCT_RE.search(probe)
            or _LEADING_PUNCT_RE.match(line)
        )
        if not dirty:
            lines.append(line)
            continue
        cleaned = _clean_line(line)
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines).strip()


__all__ = [
    "CONTENT_KEYS",
    "DEDUP_KIND_ORDER",
    "DEDUP_MIN_DICE",
    "DEDUP_STOPWORDS",
    "dedupe_by_meaning",
    "drop_empty_labels",
    "record_text",
    "same_meaning",
]
