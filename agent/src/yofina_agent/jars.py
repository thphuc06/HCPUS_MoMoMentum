"""Ánh xạ tên hũ người dùng gõ ("giải trí", "ăn uống") sang mã hũ.

Bảng ánh xạ **không nằm trong code**: nó được dựng lúc chạy từ danh sách hũ của chính người dùng
mà tool `get_jar_balances` trả về (mã + tên), nên hũ nào người dùng có thì khớp được hũ đó.
So khớp theo thứ tự: mã, tên đầy đủ, tên nằm trong/chứa câu gõ, rồi gần đúng (lỗi gõ).
"""

from __future__ import annotations

import difflib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from yofina_agent.textutil import normalize

_FILLER = {"hu", "ve", "vi", "jar", "muc", "khoan", "tien"}
_FUZZY_CUTOFF = 0.8

Status = Literal["ok", "empty", "none", "ambiguous"]


@dataclass(frozen=True)
class JarMatch:
    status: Status
    code: str | None = None
    candidates: tuple[str, ...] = field(default_factory=tuple)  # mã hũ gần nhất khi mơ hồ


def _strip_filler(norm: str) -> str:
    words = norm.split()
    while words and words[0] in _FILLER:
        words.pop(0)
    return " ".join(words)


def resolve_jar(text: str | None, jars: Sequence[Mapping[str, object]]) -> JarMatch:
    """Tìm hũ trong `jars` (mỗi hũ có `code` và `name`) ứng với chuỗi người dùng gõ."""
    if text is None or not (query := _strip_filler(normalize(text))):
        return JarMatch("empty")
    names = {str(j["code"]): normalize(str(j["name"])) for j in jars}
    codes = {code: normalize(code) for code in names}  # `an_uong` -> "an uong"

    exact = [c for c in names if query in {codes[c], names[c]}]
    if len(exact) == 1:
        return JarMatch("ok", exact[0])

    contained = [
        c
        for c in names
        if len(names[c]) >= 3 and (names[c] in query or (len(query) >= 3 and query in names[c]))
    ]
    if len(contained) == 1:
        return JarMatch("ok", contained[0])
    if len(contained) > 1:
        return JarMatch("ambiguous", None, tuple(contained))

    pool = {**{n: c for c, n in names.items()}, **{n: c for c, n in codes.items()}}
    close = difflib.get_close_matches(query, list(pool), n=2, cutoff=_FUZZY_CUTOFF)
    owners = list(dict.fromkeys(pool[n] for n in close))
    if len(owners) == 1:
        return JarMatch("ok", owners[0])
    if len(owners) > 1:
        return JarMatch("ambiguous", None, tuple(owners))
    return JarMatch("none")
