"""Gói dùng chung của Yofina Foresight (agent, Lambda tool, pipeline).

Module và luồng sở hữu (docs/plan/phases/phase-1-nen-va-lat-doc.md):
- `blocks`, `money`, `clock`, `config`, `errors`: đã cài ở bước 0 (hợp đồng).
- `confirm`: chuẩn hóa và băm tham số đã cài; cấp/kiểm token do luồng B.
- `db`: luồng B. `llm`: luồng D. `pii`: phase 5.
"""

__version__ = "0.1.0"
