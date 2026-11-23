"""Đường nhập cho test phân hũ tự động: `pipelines/classify` không nằm trong pythonpath chung của pyproject.

Không dùng `conftest.py` riêng (trùng tên module với `tests/unit/conftest.py`): mỗi file test nhập module này TRƯỚC các gói của luồng phân loại."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
for extra in ("pipelines/classify", "evals/classification", "gateway/tools/ledger", "data"):
    p = str(REPO / extra)
    if p not in sys.path:
        sys.path.append(p)  # cuối danh sách: không che module trùng tên (`handler`) của các gói khác
