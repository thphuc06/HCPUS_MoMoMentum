# tests/

Test tự động (`tests/unit/`, `tests/integration/`). Ưu tiên test: engine tất định (affordability_check, Monte Carlo, suitability, phân bổ LP), phân loại giao dịch (NFR: đúng ≥ 90% trên bộ kiểm thử persona), idempotency của sự kiện. Đánh giá agent nằm ở [../evals/](../evals/README.md).

`tests/unit/` hiện chứa test hợp đồng ([contracts/](../contracts/README.md): khối UI, tool, OpenAPI, migration 0001; `ts/` là phía Zod, `test_contracts_zod.py` chạy nó trong pytest). Chạy: `uv run pytest` (cả test của `libs/yofina_core/tests`).