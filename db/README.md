# db/

Aurora PostgreSQL Serverless v2 (+ pgvector): nguồn sự thật duy nhất cho mọi con số.

- `migrations/`: migration theo thứ tự `NNNN_ten.sql`. Hiện có [0001_core.sql](migrations/0001_core.sql), [0002_jar_view.sql](migrations/0002_jar_view.sql) (hàm `app_get_jar_view`: số dư hũ kèm `clock_offset_days` trong một lệnh gọi) và [0003_conversation_turns.sql](migrations/0003_conversation_turns.sql) (bảng `conversation_turns` cho câu hỏi/câu trả lời của từng lượt, RLS `FORCE`, hàm `app_get_conversation_turns` và `app_list_conversations`); [0004_confirm_resolutions.sql](migrations/0004_confirm_resolutions.sql) (bảng `confirm_resolutions`: một đề nghị `confirm_block_id` của một người dùng chỉ được thực hiện một lần, kèm biên nhận để phát lại; RLS `FORCE`, hàm `app_get_confirm_resolutions` và `app_get_confirm_resolution`); cả bốn đã chạy trên Aurora. Phase 2 thêm [0005_wallet.sql](migrations/0005_wallet.sql) và [0006_forecast.sql](migrations/0006_forecast.sql) (**chưa chạy trên Aurora**, chờ người điều phối duyệt) cùng `seed/` (bảng tra); xem mục "Schema phase 2".
- `schema/`: để dành cho bản mô tả schema tổng hợp (chưa có; nguồn sự thật hiện là chuỗi migration).
- Truy cập bằng RDS Data API (không psycopg/VPC); tool dùng role riêng `yofina_app` (master vượt RLS), RLS qua hàm plpgsql `SECURITY INVOKER` có `set_config(..., true)`; giữ min 0,5 ACU khi demo; pgvector 0.8.2 chạy được. Số đo và mẫu SQL: [spike-aurora-data-api.md](../docs/research/spike-aurora-data-api.md).
- Proposal: §7 (mô hình dữ liệu, cổng chất lượng), §14. Mô tả bảng: [../docs/architecture/overview.md](../docs/architecture/overview.md#mô-hình-dữ-liệu).

## Quy ước viết migration

- **Mỗi câu lệnh kết thúc bằng dấu chấm phẩy.** Data API chỉ nhận một câu lệnh mỗi lần gọi; Lambda migrator ([infra-cdk/lambdas/migrator/sqlsplit.py](../infra-cdk/lambdas/migrator/sqlsplit.py)) tách file theo dấu chấm phẩy ngoài chuỗi, chú thích và thân dollar-quote, nên thân hàm plpgsql (`$$ ... $$`) không bị cắt.
- **Một file chạy trong một transaction** (DDL của PostgreSQL có transaction): xong hết hoặc không gì cả. Migrator ghi `schema_migrations(version, checksum)` trong cùng transaction; file đã chạy mà bị sửa thì migrator từ chối (thêm migration mới, đừng sửa file cũ).
- **Không tham số có tên** và **không dấu hai chấm dính liền chữ** (kể cả trong chú thích): Data API có thể hiểu nhầm là tham số. Ép kiểu `::` thì được.
- **Mật khẩu role không nằm trong file**: migrator tự tạo hoặc đổi mật khẩu `yofina_app` từ secret của nó rồi mới chạy các file; file chỉ bảo đảm role tồn tại với thuộc tính đúng (`LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE`; `NOSUPERUSER` chỉ ở `CREATE ROLE`, vì master Aurora không được nhắc nó trong `ALTER ROLE`) và không đụng mật khẩu.
- **Viết lại được**: `IF NOT EXISTS`, `CREATE OR REPLACE`, `DROP POLICY IF EXISTS` rồi `CREATE POLICY`.
- **Dòng phân cách `-- @@`** (từ 0005): file có dòng chỉ gồm `-- @@` thì migrator tách theo dòng đó (mỗi khối đúng một câu lệnh, dấu chấm phẩy cuối khối được bỏ) thay vì tách theo dấu chấm phẩy. Bền hơn với thân hàm plpgsql và `DO`. 0001 tới 0004 tách theo dấu chấm phẩy và không đổi.
- **Ràng buộc có thể NULL**: biểu thức CHECK mà một vế có thể NULL thì cả biểu thức ra NULL và ràng buộc **không chặn** (ví dụ `balance_vnd >= 0 OR system_role = 'x'` với `system_role` NULL). Dùng `coalesce` hoặc `IS NOT DISTINCT FROM`; đã gặp khi chạy thử 0005.
- **Trước khi giao, chạy thử trên PostgreSQL cục bộ**: `uv run scripts/db_local_check.py` (pgserver, Python 3.12 do script tự ghim; không gọi AWS, không cần Docker).
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

**Hàm đọc thêm ở 0002**: `app_get_jar_view(p_user_id)` trả mỗi hũ kèm `clock_offset_days` (LEFT JOIN từ `users`, nên người dùng chưa có hũ vẫn có một dòng cột hũ NULL; chưa có hàng `users` thì không có dòng). Dùng cho `GET /jars` và tool `get_jar_balances` (cần cả số dư lẫn ngày mô phỏng, tiết kiệm một lệnh gọi ~50 ms).

**Đường ghi** (không có hàm ghi trong 0001): `BeginTransaction` → `SELECT set_config('app.user_id', :uid, true)` → câu lệnh → `Commit`, luôn `rollback` trong `finally`. Chuyển hũ = trừ hũ nguồn bằng `UPDATE ... WHERE balance_vnd >= :amount` (ràng buộc `balance_vnd >= 0` là lưới cuối), cộng hũ đích, thêm hai dòng `transactions` cùng `transfer_id`, thêm `audit_events`.

## Schema phase 2 (0005, 0006 và 0007)

Thiết kế và lý do: mục "Quyết định hợp đồng phase 2" cuối [file phase 2](../docs/plan/phases/phase-2-vi-va-du-bao.md); quy ước dùng được trong mã: [contracts/README.md](../contracts/README.md#phase-2-ví-mô-phỏng-và-dự-báo). Hai file dùng dòng phân cách `-- @@` (mỗi câu lệnh một khối), không dùng tách theo dấu chấm phẩy.

**0005_wallet** (không sửa 0001 tới 0004):

| Thay đổi | Nội dung |
|---|---|
| `jars` (cột mới) | `kind` (`spending`, `saving`, `obligation`, `system`), `system_role` (`other_income`, `unclassified`; duy nhất mỗi người dùng), `goal_vnd`, `goal_date`. Ràng buộc `jars_balance_check` thay `jars_balance_vnd_check` của 0001: số dư không âm, **trừ hũ `unclassified`** (được âm). Hũ hệ thống có tỷ lệ chia 0 và không có mục tiêu |
| `transactions` (cột mới) | `tx_type` (mã trong `tx_type_map`, không có khóa ngoại), `funding_source` (`jar`, `credit`), `payee_id`, `obligation_id`, `dedupe_key` (duy nhất theo người dùng khi có), `classified_by`, `classification_confidence`, `needs_review`, `suggested_jars`. `merchant` là đối tác và `note` là lời nhắn (có từ 0001). Dòng `credit` không đổi số dư hũ |
| `payees` | Người nhận của ví mô phỏng (tên, phần đã che của tài khoản, yêu thích, lần dùng cuối). Seed theo persona |
| `obligations` | Mọi khoản tiền ra theo lịch: `kind` (`bnpl`, `loan`, `rent`, `bill`, `subscription`), `amount_vnd` kỳ vọng và khoảng tùy chọn, `fee_vnd`, `principal_vnd` (trả sau), `due_date` kế tiếp, `cycle`, `due_day`, `status` (`active`, `paid`, `cancelled`), `pay_jar_code`, `is_essential`, `source` (`declared`, `bnpl_auto`). Một nghĩa vụ trả sau hoạt động mỗi ngày đến hạn (chỉ mục duy nhất một phần) |
| `credit_lines` | Hạn mức Trả sau (mô phỏng): `limit_vnd`, `outstanding_vnd` (gốc), `due_day` (mặc định 5) |
| `category_rules` | Luật phân loại học từ lần sửa (`payee` hoặc `merchant`, `scope` `once` hoặc `always`); phase 4 dùng |
| `salary_events` | Lương về chờ xác nhận: `period_date`, `amount_vnd`, `expected_vnd`, `deviation_percent`, `ask_update_salary`, `status` (`pending`, `confirmed`, `kept_other`), `split` |
| `tx_type_map`, `fee_schedules`, `jar_templates` | Bảng tra dùng chung, **không có `user_id`, không RLS, `yofina_app` chỉ SELECT**. Dữ liệu ở `db/seed/*.sql` |
| `confirm_resolutions` | `transfer_id` hết bắt buộc (biên nhận `receipt_action` không có), thêm `action_tool` |
| Hàm đọc (`SECURITY INVOKER`) | `app_ensure_system_jars`, `app_list_jars`, `app_list_obligations`, `app_list_payees`, `app_get_credit_line`, `app_list_transactions` (lọc, con trỏ), `app_get_unclassified`, `app_get_daily_spend` (đầu vào dự báo), `app_get_cashflow_summary`, `app_list_salary_events`, `app_get_overview_extras` (một lệnh gọi jsonb cho Tổng quan) |

Quyền mới của `yofina_app`: bảng người dùng mới SELECT/INSERT/UPDATE/DELETE; `transactions` thêm **UPDATE theo cột** chỉ cho `jar_code`, `needs_review`, `classified_by`, `classification_confidence`, `suggested_jars`, `obligation_id`, `payee_id` (số tiền, hũ nguồn trả, thời điểm vẫn bất biến).

**0006_forecast** (`forecast_runs`, `forecast_jar_summaries`, `forecasts`, đều RLS `FORCE`, chỉ SELECT/INSERT/DELETE): một lần chạy có metadata (model, ngày gốc, số ngày lịch sử, độ phủ, nhãn tin cậy, cờ ước lượng ban đầu); tóm tắt mỗi hũ là **bảng con** chứ không phải jsonb vì Tổng quan cần "lần chạy mới nhất của mỗi hũ" trong một truy vấn có chỉ mục và có kiểu rõ (ngày cạn, xác suất, trạng thái); `forecasts` giữ phân vị chi tiêu ngày và phân vị số dư (số dư có thể âm). Hàm: `app_get_forecast_summaries` (mới nhất mỗi hũ), `app_get_forecast_series` (chuỗi của hũ), `app_prune_forecast_runs` (giữ N lần chạy mới nhất). Mốc nghĩa vụ và lương không lưu ở đây.

**0007_wallet_ops** (luồng A, đã chạy trên Aurora ngày 2026-11-22; không sửa 0001 tới 0006): `confirm_resolutions` thêm `status` (`done` mặc định cho dòng cũ, hoặc `cancelled`), `receipt` hết bắt buộc, CHECK `(status = 'done') = (receipt IS NOT NULL)`; hai hàm đọc đề nghị được **tạo lại** có thêm cột `status` (DROP rồi CREATE vì đổi kiểu trả về). Hàm đọc mới (đều `SECURITY INVOKER`, tự đặt `app.user_id`, có LIMIT): `app_get_confirm_block` (khối `confirm` đã lưu, để server ép hạn của đề nghị), `app_get_jar_state` (MỌI hũ kể cả hũ hệ thống, kèm loại, mục tiêu và độ lệch đồng hồ), `app_get_transaction`, `app_get_review_stats`, `app_get_jar_usage` (hũ nào bỏ được), **`app_get_overview(p_user_id, p_now, p_tz)`** (jsonb: hồ sơ, hũ, tóm tắt dự báo mới nhất mỗi hũ, hạn mức, nghĩa vụ sắp đến hạn, lương chờ, 5 giao dịch gần nhất, số cần xem lại; ngày mô phỏng tính ngay trong hàm; MỘT lệnh gọi Data API thay vì ba) và `app_get_jar_detail` (hũ, dự báo, 10 giao dịch, nghĩa vụ của một hũ). Hàm `app_get_jar_view` của 0002 giữ nguyên (không còn dùng).

**0008_wallet_hints** (luồng A, đã chạy trên Aurora ngày 2026-11-22): `tx_type_map.is_person_transfer` (cờ cho giao diện, seed đặt `true` ở `transfer_person`) và hàm `app_get_forecast_summaries` được tạo lại (DROP rồi CREATE) có thêm cột `forecast_floor_vnd` = số dư P50 thấp nhất của `forecasts` từ ngày dự báo đầu tới trước `payday_date` của lần chạy mới nhất mỗi hũ; `app_get_overview` và `app_get_jar_detail` lấy cột này tự động. Không thêm cột lưu nên pipeline dự báo không phải ghi thêm gì.

**Seed** (`db/seed/`): `tx_type_map.sql` (bước 0 của phân loại), `jar_templates.sql` (hũ mặc định của onboarding), `fee_schedules.sql` (biểu phí Trả sau có nguồn). Viết lại được (`INSERT ... ON CONFLICT DO UPDATE`). Nạp bằng `uv run scripts/migrate.py --seed` SAU khi migration đã chạy: mỗi file gửi cho migrator với `version = seed_<tên>_<8 ký tự sha256>`, nên sửa nội dung seed thì được nạp lại. Dữ liệu persona (hồ sơ, hũ, giao dịch, người nhận, nghĩa vụ, hạn mức) **không** nằm ở đây mà ở `data/personas/` và được nạp bởi `POST /demo/reset` và `scripts/seed_demo.py`.

Chạy migration phase 2 trên Aurora: `uv run scripts/migrate.py --dry-run`, rồi `uv run scripts/migrate.py`, rồi `uv run scripts/migrate.py --seed` (khi đổi bảng tra), rồi `uv run scripts/seed_demo.py` (đặt lại sáu tài khoản demo; cũng gọi `app_ensure_system_jars` cho họ). **0005, 0006 và seed đã chạy; 0007 chạy ngày 2026-11-22 (33 câu lệnh, 1,9 giây).**

## Đã kiểm thế nào

Test tĩnh: `tests/unit/test_migration_0001.py` (tách bằng bộ tách thật của migrator, RLS đủ năm bảng, quyền tối thiểu, không bí mật). Ngoài ra file đã được chạy thử một lần trên PostgreSQL 16 cục bộ (gói `pgserver`, không nằm trong dependency của dự án): chạy hai lần liên tiếp (idempotent), role có mật khẩu sẵn không bị đụng, và các ca RLS (A không thấy và không ghi được dữ liệu của B), ràng buộc số dư, `audit_events` chỉ thêm, hàm đọc. Bản chạy thử cục bộ dùng superuser thật nên không bắt được việc master Aurora (`rds_superuser`) bị từ chối `ALTER ROLE ... NOSUPERUSER`; luồng A phát hiện khi thử trên Aurora thật (chạy 56 câu lệnh trong một transaction rồi rollback) và câu đó đã được sửa. **Chưa có lần chạy migration 0001 thật sự (commit) trên Aurora** tại thời điểm viết; chưa thử trên PostgreSQL 17/18.

0005 và 0006: test tĩnh `tests/unit/test_migration_0005.py` (cả seed) và `test_migration_0006.py`, cộng [scripts/db_local_check.py](../scripts/db_local_check.py): chạy 0001 tới 0006 và seed bằng bộ tách thật của migrator trên PostgreSQL 16 cục bộ, chạy lại 0005, 0006 và seed lần hai (idempotent), rồi 55 ca dưới role `yofina_app` (RLS giữa hai người dùng, ràng buộc hũ hệ thống và số dư, khử trùng, trả sau một dòng hoạt động mỗi ngày đến hạn, quyền cột của `transactions`, bảng tra chỉ đọc, hàm đọc kể cả phân trang con trỏ và "mới nhất mỗi hũ", dọn lần chạy). Ca này bắt được một lỗi của bản đầu (CHECK số dư không chặn số âm vì biểu thức ra NULL khi `system_role` rỗng). 0007: test tĩnh `tests/unit/test_migration_0007.py` và toàn bộ luồng ghi, đọc, RLS, đua song song ở **`tests/local_pg/`** (39 ca chạy `LedgerRepo` thật trên PostgreSQL 16 cục bộ qua một bản giả của client `rds-data`: SQL thật, role `yofina_app` thật). Bản cục bộ không có cơ sở dữ liệu múi giờ IANA nên bản giả đổi `Asia/Ho_Chi_Minh` thành `UTC-7` (POSIX); Aurora có đủ múi giờ và hàm `app_get_overview` chạy đúng ở đó (test tích hợp).
