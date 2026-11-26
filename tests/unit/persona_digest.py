"""Băm toàn bộ đầu ra của bộ sinh persona (generate + materialize), để khóa "ba persona cũ không đổi một byte".

Dùng chung cho test và cho lần tính mốc (chạy trực tiếp: `uv run python tests/unit/persona_digest.py`). Trường mới của F6 (thu nhập
ngoài ví, chi ngoài ví) chỉ được bỏ khỏi bản băm khi chúng đang ở giá trị vắng mặc định: persona không khai thì bản băm phải
y như trước khi có tính năng.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

ANCHOR = date(2026, 11, 21)
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = datetime(2026, 12, 10, 3, 0, tzinfo=UTC)
#: trường thêm ở F6, mặc định vắng (None): bỏ khỏi bản băm khi vắng
NEW_OPTIONAL_FIELDS = ("external_income_monthly_vnd",)
#: trường chỉ ví demo dùng (issue #39: hũ Chi hằng ngày của khối `demo_jars`): `materialize` của ví persona không đọc nó, nên bản băm của
#: ví persona không tính nó; ví demo có test riêng (`tests/unit/test_personas.py`)
DEMO_ONLY_FIELDS = ("demo_jars",)
MATERIALIZED_FIELDS = (
    "clock_offset_days", "app_date", "profile", "jars", "payees", "obligations", "credit_line",
    "transaction_rows", "salary_events",
)  # fmt: skip


def persona_digest(name: str) -> str:
    from personas import generate, materialize

    d = generate(name, anchor=ANCHOR)
    m = materialize(
        d, anchor=ANCHOR, now=NOW, tz=TZ, user_id="u1", bnpl_fee={"amount_vnd": 33_000, "id": None}
    )
    gen = dataclasses.asdict(d)
    for key in NEW_OPTIONAL_FIELDS:
        if key in gen and gen[key] is None:
            del gen[key]
    for key in DEMO_ONLY_FIELDS:
        gen.pop(key, None)
    payload = {
        "generate": gen,
        "materialize": {k: getattr(m, k) for k in MATERIALIZED_FIELDS},
        "materialized_tx": [dataclasses.asdict(t) for t in m.transactions],
    }
    text = json.dumps(payload, default=str, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    for n in ("minh", "lan", "khoa"):
        print(n, persona_digest(n))
