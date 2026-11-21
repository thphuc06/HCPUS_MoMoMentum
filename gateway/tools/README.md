# gateway/tools/

Lambda (Python) sau AgentCore Gateway, một thư mục cho mỗi nhóm tool (proposal §9). Agent thấy tất cả như một MCP server duy nhất. LLM không tự tính số: mọi con số do các tool này trả.

| Thư mục (= target) | Tool (qua Gateway: `<target>___<tool>`) | Tính năng |
|---|---|---|
| `ledger/` | `ledger___*` — sổ cái, hũ, nghĩa vụ, hồ sơ | nền, FR1, FR2, FR4 |
| `forecast/` | `forecast___*` — dự báo, what-if, stress test, kiểm tra trước khi quẹt, điểm chống chịu, hồ sơ hành vi | F1–F4, F7 |
| `planner/` | `planner___*` — tối ưu phân bổ, suitability, lộ trình, nhắc | F5 |
| `knowledge/` | `knowledge___*` — RAG, biểu phí | giải thích, F3 |
| `ingest/` | `ingest___*` — nạp tệp ngoài ví | F6 |
| `audit/` | `audit___*` — dữ liệu bảng "Vì sao" | FR11 |

Proposal viết tên có dấu chấm (`ledger.get_jar_balances`); Gateway ghép `target___tool` (ba gạch dưới), danh mục đầy đủ ở [overview.md](../../docs/architecture/overview.md#danh-mục-tool-9). Mỗi Lambda nhận `user_id` do interceptor ghi đè, bỏ qua tham số lạ, truy cập Aurora qua Data API bằng role riêng ([spike-agentcore-gateway-identity.md](../../docs/research/spike-agentcore-gateway-identity.md), [spike-aurora-data-api.md](../../docs/research/spike-aurora-data-api.md)).