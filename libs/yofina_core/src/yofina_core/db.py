"""Client RDS Data API cho Aurora (luồng B cài; chưa có mã ở bước 0, không cài giả).

Sẽ gồm, theo spike Aurora (docs/research/spike-aurora-data-api.md §4-§7):
- đường đọc: gọi hàm plpgsql `app_*` (db/migrations/0001_core.sql), 1 lệnh gọi, RLS qua
  `set_config('app.user_id', ..., true)` bên trong hàm;
- đường ghi: `BeginTransaction` -> `set_config('app.user_id', :uid, true)` -> câu lệnh ->
  `Commit`, luôn `rollback` trong `finally`;
- dùng secret của role `yofina_app` (không bao giờ dùng secret master);
- retry `DatabaseResumingException` (boto3 không tự retry), mọi truy vấn nhiều dòng có `LIMIT`;
- `numeric` là chuỗi -> `Decimal`; `timestamptz` là UTC không hậu tố; tham số vector/jsonb/
  timestamptz phải `CAST`;
- Region và ARN cluster/secret lấy từ `yofina_core.config`, không gắn cứng.
"""
