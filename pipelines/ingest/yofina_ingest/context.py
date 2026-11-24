"""Ngữ cảnh người dùng cho một lần trích: hũ, bảng loại giao dịch, luật phân loại, ngữ cảnh che PII, và các cổng của bộ phân loại.

Gán hũ cho dòng chi KHÔNG nằm ở đây mà ở `yofina_ingest.classify` (bộ phân loại phase 4: luật, bảng loại giao dịch, embedding k-NN, model
nhỏ, ba mức tin cậy). `store` là kho nhãn và lịch sử của người dùng (Aurora ở worker); vắng thì bỏ bước k-NN và tín hiệu lặp lại.

Chế độ eval (không DB): `eval_context` dựng hũ và bảng loại giao dịch từ chính các file seed của sản phẩm (`db/seed/*.sql`) nếu tìm
thấy; không thấy thì chỉ còn đề xuất của model.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from yofina_core.ingest import IngestSettings
from yofina_core.params import TxTypeInfo
from yofina_core.pii import PiiPolicy
from yofina_ingest.classify import ClassifyInputs, LabelStore, Rule, match_rule

__all__ = ["ExtractContext", "Rule", "eval_context", "jars_from_rows", "match_rule"]


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
    #: người dùng của lần nạp (nhãn k-NN và lịch sử là của chính họ); vắng ở chế độ eval
    user_id: str | None = None
    #: kho nhãn và lịch sử cho bộ phân loại; vắng thì bỏ bước k-NN và tín hiệu lặp lại
    store: LabelStore | None = None
    tz: ZoneInfo | None = None

    @property
    def jar_codes(self) -> set[str]:
        return {j["code"] for j in self.jars}

    def classify_inputs(self, gateway: Any = None) -> ClassifyInputs:
        return ClassifyInputs(
            user_id=self.user_id or "eval",
            jars=self.jars,
            type_map=self.type_map,
            rules=self.rules,
            policy=self.policy,
            store=self.store if self.user_id else None,
            gateway=gateway,
            tz=self.tz,
        )


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
