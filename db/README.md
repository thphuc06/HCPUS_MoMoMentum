# db/

Aurora PostgreSQL Serverless v2 (+ pgvector): nguồn sự thật duy nhất cho mọi con số.

- `migrations/`: migration theo thứ tự `NNNN_ten.sql`. Hiện có [0001_core.sql](migrations/0001_core.sql).
- `schema/`: để dành cho bản mô tả schema tổng hợp (chưa có; nguồn sự thật hiện là chuỗi migration).
- Truy cập bằng RDS Data API (không psycopg/VPC); tool dùng role riêng `yofina_app` (master vượt RLS), RLS qua hàm plpgsql `SECURITY INVOKER` có `set_config(..., true)`; giữ min 0,5 ACU khi demo; pgvector 0.8.2 chạy được. Số đo và mẫu SQL: [spike-aurora-data-api.md](../docs/research/spike-aurora-data-api.md).
- Proposal: §7 (mô hình dữ liệu, cổng chất lượng), §14. Mô tả bảng: [../docs/architecture/overview.md](../docs/architecture/overview.md#mô-hình-dữ-liệu).

## Quy ước viết migration

- **Mỗi câu lệnh kết thúc bằng dấu chấm phẩy.** Data API chỉ nhận một câu lệnh mỗi lần gọi; Lambda migrator ([infra-cdk/lambdas/migrator/sqlsplit.py](../infra-cdk/lambdas/migrator/sqlsplit.py)) tách file theo dấu chấm phẩy ngoài chuỗi, chú thích và thân dollar-quote, nên thân hàm plpgsql (`$$ ... $$`) không bị cắt.
- **Một file chạy trong một transaction** (DDL của PostgreSQL có transaction): xong hết hoặc không gì cả. Migrator ghi `schema_migrations(version, checksum)` trong cùng transaction; file đã chạy mà bị sửa thì migrator từ chối (thêm migration mới, đừng sửa file cũ).
- **Không tham số có tên** và **không dấu hai chấm dính liền chữ** (kể cả trong chú thích): Data API có thể hiểu nhầm là tham số. Ép kiểu `::` thì được.
- **Mật khẩu role không nằm trong file**: migrator tự tạo hoặc đổi mật khẩu `yofina_app` từ secret của nó rồi mới chạy các file; file chỉ bảo đảm role tồn tại với thuộc tính đúng (`LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE`; `NOSUPERUSER` chỉ ở `CREATE ROLE`, vì master Aurora không được nhắc nó trong `ALTER ROLE`) và không đụng mật khẩu.
- **Viết lại được**: `IF NOT EXISTS`, `CREATE OR REPLACE`, `DROP POLICY IF EXISTS` rồi `CREATE POLICY`.
- Mọi hàm đọc nhiều dòng có `LIMIT` (phản hồi Data API tối đa 1 MiB, vượt là lỗi cả lệnh).

## Schema lõi (0001)

| Bảng | Ghi chú |
|---|---|
| `users` | `id` = `sub` của Cognito (text); `display_name`, `monthly_salary_vnd`, `payday_day`, `risk_tolerance`, `clock_offset_days` ([ADR-0003](../docs/decisions/0003-dong-ho-mo-phong.md)). Lương, ngày nhận và mức rủi ro cho phép NULL (chưa khai báo) |
| `jars` | Khóa `(user_id, code)`; `name`, `color_key`, `icon_key`, `balance_vnd` (>= 0), `split_percent`, `sort_order` |
| `transactions` | Sổ cái; mỗi dòng tác động lên **một** hũ, `amount_vnd` có dấu (âm là ra khỏi hũ). `kind` ∈ `expense` (âm), `income` (dương), `transfer` (cặp dòng cùng `transfer_id`). `jar_code` NULL = chưa gán hũ. `app_date` là ngày mô phỏng lúc ghi |
| `audit_events` | Chỉ thêm, không sửa, không xóa (kể cả khi đặt lại demo); không khóa ngoại tới `users` |
| `turn_blocks` | Khối UI đã phát để phát lại: `conversation_id`, `trace_id`, `seq` (thứ tự trong lượt), `block` jsonb; thứ tự toàn cục theo `id` |

**RLS**: `ENABLE` và `FORCE` trên cả năm bảng, policy `user_isolation` theo `current_setting('app.user_id', true)` (bảng `users` theo cột `id`, các bảng khác theo `user_id`). Master của Aurora (`rds_superuser`) vẫn vượt RLS, nên mọi tool dùng secret của `yofina_app`.

**Quyền của `yofina_app`** (tối thiểu): `users` SELECT, INSERT, UPDATE; `jars` thêm DELETE; `transactions` và `turn_blocks` SELECT, INSERT, DELETE (không sửa sổ cái); `audit_events` SELECT, INSERT; không có quyền gì lên `schema_migrations`; không phải owner nên không tắt được RLS.

**Hàm đọc** (`SECURITY INVOKER`, tự `set_config('app.user_id', ..., true)` bên trong, một lệnh gọi Data API): `app_get_jar_balances(p_user_id)`, `app_get_user(p_user_id)`, `app_query_transactions(p_user_id, p_jar, p_from, p_to, p_limit)` (tối đa 51 dòng), `app_get_conversation_blocks(p_user_id, p_conversation_id, p_limit)` (tối đa 300). Chỉ `yofina_app` được `EXECUTE`. `numeric` và `timestamptz` trả về dạng chuỗi (UTC, không hậu tố); `jsonb` trả về chuỗi JSON.

**Đường ghi** (không có hàm ghi trong 0001): `BeginTransaction` → `SELECT set_config('app.user_id', :uid, true)` → câu lệnh → `Commit`, luôn `rollback` trong `finally`. Chuyển hũ = trừ hũ nguồn bằng `UPDATE ... WHERE balance_vnd >= :amount` (ràng buộc `balance_vnd >= 0` là lưới cuối), cộng hũ đích, thêm hai dòng `transactions` cùng `transfer_id`, thêm `audit_events`.

## Đã kiểm thế nào

Test tĩnh: `tests/unit/test_migration_0001.py` (tách bằng bộ tách thật của migrator, RLS đủ năm bảng, quyền tối thiểu, không bí mật). Ngoài ra file đã được chạy thử một lần trên PostgreSQL 16 cục bộ (gói `pgserver`, không nằm trong dependency của dự án): chạy hai lần liên tiếp (idempotent), role có mật khẩu sẵn không bị đụng, và các ca RLS (A không thấy và không ghi được dữ liệu của B), ràng buộc số dư, `audit_events` chỉ thêm, hàm đọc. Bản chạy thử cục bộ dùng superuser thật nên không bắt được việc master Aurora (`rds_superuser`) bị từ chối `ALTER ROLE ... NOSUPERUSER`; luồng A phát hiện khi thử trên Aurora thật (chạy 56 câu lệnh trong một transaction rồi rollback) và câu đó đã được sửa. **Chưa có lần chạy migration 0001 thật sự (commit) trên Aurora** tại thời điểm viết; chưa thử trên PostgreSQL 17/18.
