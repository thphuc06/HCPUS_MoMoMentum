"""Ngữ cảnh người dùng cho một lần trích (hũ, bảng loại giao dịch, luật phân loại, ngữ cảnh che PII) và luật gán hũ.

Thứ tự gán hũ cho dòng chi (`resolve_jar`): luật của người dùng (`category_rules`, scope always) > bảng `tx_type_map` > đề xuất của
model. `jar_source` ghi đúng nguồn (`rule`, `type_map`, `model`). Khi bảng loại giao dịch và model bất đồng, giữ hũ của bảng nhưng
hạ độ tin cậy dưới ngưỡng tự chọn, để dòng đó đi vào hàng chờ duyệt thay vì được chọn sẵn.

Chế độ eval (không DB): `eval_context` dựng hũ và bảng loại giao dịch từ chính các file seed của sản phẩm (`db/seed/*.sql`) nếu tìm
thấy; không thấy thì chỉ còn đề xuất của model.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from yofina_core.ingest import IngestSettings
from yofina_core.params import TxTypeInfo, fold_text
from yofina_core.pii import PiiPolicy

#: độ tin cậy của hũ lấy từ luật người dùng và từ bảng loại giao dịch (model chỉ đo độ chắc của đề xuất của chính nó)
RULE_CONFIDENCE = 0.99
TYPE_MAP_CONFIDENCE = 0.95
#: khi bảng loại giao dịch và model chọn hai hũ khác nhau
DISAGREE_CONFIDENCE = 0.6
#: model đề xuất hũ mà không nêu độ chắc
DEFAULT_MODEL_JAR_CONFIDENCE = 0.6


@dataclass(frozen=True)
class Rule:
    """Luật `category_rules` đang áp dụng (scope always): khóa đã chuẩn hóa (`fold_text`) và hũ."""

    key: str
    jar_code: str


@dataclass
class ExtractContext:
    jars: list[
        dict[str, Any]
    ]  # hũ người dùng (không có hũ hệ thống): code, name, color_key, icon_key
    type_map: dict[str, TxTypeInfo]
    rules: list[Rule]
    policy: PiiPolicy
    today: date
    settings: IngestSettings = field(default_factory=IngestSettings)

    @property
    def jar_codes(self) -> set[str]:
        return {j["code"] for j in self.jars}


@dataclass(frozen=True)
class JarChoice:
    code: str
    confidence: float
    source: str  # rule | type_map | model


def match_rule(
    rules: Iterable[Rule], counterparty: str | None, description: str | None
) -> Rule | None:
    """Luật khớp đối tác: bằng nhau, hoặc khóa (từ 4 ký tự) là cụm nguyên từ trong đối tác hay nội dung. Khóa dài nhất thắng."""
    cp, desc = fold_text(counterparty or ""), fold_text(description or "")
    best: Rule | None = None
    for r in rules:
        if not r.key:
            continue
        hit = r.key == cp
        if not hit and len(r.key) >= 4:
            pat = re.compile(rf"(?<!\w){re.escape(r.key)}(?!\w)")
            hit = bool(pat.search(cp) or pat.search(desc))
        if hit and (best is None or len(r.key) > len(best.key)):
            best = r
    return best


def resolve_jar(
    *,
    kind: str,
    counterparty: str | None,
    description: str | None,
    tx_type: str | None,
    model_jar: str | None,
    model_jar_confidence: float | None,
    ctx: ExtractContext,
) -> JarChoice | None:
    """Hũ đề xuất cho dòng chi (dòng thu không có hũ). None nếu không có gì đáng tin."""
    if kind != "expense":
        return None
    valid = ctx.jar_codes
    rule = match_rule(ctx.rules, counterparty, description)
    if rule is not None and rule.jar_code in valid:
        return JarChoice(rule.jar_code, RULE_CONFIDENCE, "rule")
    model_ok = model_jar if model_jar in valid else None
    model_conf = (
        DEFAULT_MODEL_JAR_CONFIDENCE
        if model_jar_confidence is None
        else float(model_jar_confidence)
    )
    info = ctx.type_map.get(tx_type or "")
    if info is not None and info.direction == "out" and info.default_jar_code in valid:
        conf = (
            TYPE_MAP_CONFIDENCE
            if model_jar_confidence is None
            else min(TYPE_MAP_CONFIDENCE, model_conf)
        )
        if model_ok is not None and model_ok != info.default_jar_code:
            conf = min(conf, DISAGREE_CONFIDENCE)
        return JarChoice(str(info.default_jar_code), conf, "type_map")
    if model_ok is not None:
        return JarChoice(model_ok, model_conf, "model")
    return None


# --- ngữ cảnh eval từ file seed -----------------------------------------------------------------------------------------------------
_VALUE = re.compile(r"'((?:[^']|'')*)'|([^,\s][^,]*)")


def _values(row: str) -> list[str | None]:
    out: list[str | None] = []
    for m in _VALUE.finditer(row):
        if m.group(1) is not None:
            out.append(m.group(1).replace("''", "'"))
        else:
            v = m.group(2).strip()
            out.append(None if v.upper() == "NULL" else v)
    return out


def _seed_rows(path: Path) -> list[list[str | None]]:
    """Các dòng `(...)` của câu INSERT ... VALUES trong file seed (mỗi dòng giá trị một hàng, như db/seed/*.sql)."""
    sql = path.read_text(encoding="utf-8")
    body = sql.split("VALUES", 1)[1].split("ON CONFLICT", 1)[0]
    rows = []
    for line in body.splitlines():
        t = line.strip().rstrip(",;")
        if t.startswith("(") and t.endswith(")"):
            rows.append(_values(t[1:-1]))
    return rows


def find_seed_dir() -> Path | None:
    """Thư mục có `tx_type_map.sql` và `jar_templates.sql`: biến `YOFINA_INGEST_SEED_DIR`, thư mục `seed` cạnh gói (Lambda), hoặc `db/seed` của repo."""
    here = Path(__file__).resolve()
    candidates = [
        os.environ.get("YOFINA_INGEST_SEED_DIR"),
        here.parents[1] / "seed",
        here.parents[2] / "seed",
        *(p / "db" / "seed" for p in here.parents),
    ]
    for c in candidates:
        if (
            c
            and (Path(c) / "tx_type_map.sql").is_file()
            and (Path(c) / "jar_templates.sql").is_file()
        ):
            return Path(c)
    return None


def load_seed_jars(seed_dir: Path) -> list[dict[str, Any]]:
    rows = _seed_rows(seed_dir / "jar_templates.sql")
    # code, name, color_key, icon_key, kind, default_split_percent, is_default, sort_order
    jars = [
        {
            "code": r[0],
            "name": r[1],
            "color_key": r[2],
            "icon_key": r[3],
            "kind": r[4],
            "sort": int(r[7] or 0),
        }
        for r in rows
        if len(r) >= 8 and r[0] and r[4] != "system"
    ]
    return sorted(jars, key=lambda j: j["sort"])


def load_seed_type_map(seed_dir: Path) -> dict[str, TxTypeInfo]:
    out: dict[str, TxTypeInfo] = {}
    # tx_type, label, direction, default_jar_code, system_role, is_selectable, sort_order, is_person_transfer
    for r in _seed_rows(seed_dir / "tx_type_map.sql"):
        if len(r) < 8 or not r[0]:
            continue
        out[str(r[0])] = TxTypeInfo(
            tx_type=str(r[0]),
            direction=str(r[2]),
            default_jar_code=r[3],
            system_role=r[4],
            label=str(r[1] or ""),
            is_selectable=str(r[5]).lower() == "true",
            is_person_transfer=str(r[7]).lower() == "true",
        )
    return out


def eval_context(today: date, *, settings: IngestSettings | None = None) -> ExtractContext:
    """Ngữ cảnh cho `extract(mode="eval")`: hũ mặc định và bảng loại giao dịch từ seed của sản phẩm, không luật người dùng."""
    seed = find_seed_dir()
    return ExtractContext(
        jars=load_seed_jars(seed) if seed else [],
        type_map=load_seed_type_map(seed) if seed else {},
        rules=[],
        policy=PiiPolicy.build(),
        today=today,
        settings=settings or IngestSettings(),
    )


def jars_from_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Hũ người dùng từ `app_list_jars` (bỏ hũ hệ thống), đúng thứ tự hiển thị."""
    return [
        {
            "code": r["code"],
            "name": r["name"],
            "color_key": r["color_key"],
            "icon_key": r["icon_key"],
            "kind": r.get("kind"),
        }
        for r in rows
        if r.get("kind") != "system"
    ]
