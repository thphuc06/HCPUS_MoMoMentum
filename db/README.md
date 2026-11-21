# db/

Aurora PostgreSQL Serverless v2 (+ pgvector): nguồn sự thật duy nhất cho mọi con số.

- `schema/`: định nghĩa bảng `users`, `jars`, `transactions`, `category_rules`, `obligations`, `forecasts`, `resilience_scores`, `roadmaps`, `scenarios`, `nudges`, `feedback`, `audit_events`.
- `migrations/`: migration theo thứ tự.
- Truy cập bằng RDS Data API (không psycopg/VPC); tool dùng role riêng `yofina_app` (master vượt RLS), RLS qua hàm plpgsql `SECURITY INVOKER` có `set_config(..., true)`; giữ min 0,5 ACU khi demo; pgvector 0.8.2 chạy được. Số đo và mẫu SQL: [spike-aurora-data-api.md](../docs/research/spike-aurora-data-api.md).
- Proposal: §7 (mô hình dữ liệu, cổng chất lượng), §14. Mô tả bảng: [../docs/architecture/overview.md](../docs/architecture/overview.md#mô-hình-dữ-liệu).