# gateway/tools/ledger/

Tool `ledger___*` (target `ledger`, ví dụ `ledger___get_jar_balances`): `get_jar_balances`, `query_transactions`, `get_cashflow_summary`, `get_obligations`, `get_unclassified` (đọc); `update_profile`, `record_transaction`, `move_between_jars`, `assign_jar` (ghi, cần xác nhận). Phía sau: SQL có tham số trên Aurora qua Data API, role `yofina_app` (không dùng master, master vượt RLS), mọi truy vấn có `LIMIT`. Proposal §9; FR1, FR2, FR4.

Danh tính lấy từ `user_id` do interceptor ghi đè, không tin header hay tham số khác; tool ghi kiểm `confirm_token` (đề xuất, chưa chốt). Mẫu Lambda đã chạy: [spike-agentcore-gateway-identity.md](../../../docs/research/spike-agentcore-gateway-identity.md) mục 5; mẫu Data API/RLS: [spike-aurora-data-api.md](../../../docs/research/spike-aurora-data-api.md) mục 4. Cùng mã này có thể phục vụ REST API (HTTP API + JWT, đề xuất).
