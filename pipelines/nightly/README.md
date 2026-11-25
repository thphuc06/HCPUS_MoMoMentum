# pipelines/nightly/

Nhịp **batch đêm** (proposal §10.4): dự báo lại mọi người dùng mỗi đêm. Mã nằm ở [../forecast/](../forecast/README.md) (`yofina_forecast/batch.py`, `handler_batch.py`); thư mục này mô tả cách nhịp chạy. Hạ tầng ở `infra-cdk/lib/forecast-pipeline.ts` (stack `YofinaTools`).

```
EventBridge Scheduler `yofina-nightly-0200`   cron(0 2 * * ? *), múi giờ Asia/Ho_Chi_Minh (không đổi sang UTC)
  -> Step Functions `yofina-nightly` (Standard)
       ListUsers   Lambda yofina-forecast-batch {op: list_users}          (hàm DB app_list_forecast_users: chỉ trả id)
                   Retry: DatabaseUnavailable (Aurora đang ngủ lúc 02:00) 3 lần, lùi 10 s x2 (#14)
       ForEachUser Map, song song tối đa 3 (cấu hình forecastNightlyConcurrency)
         RunUser   Lambda yofina-forecast-batch {op: run_user, trigger: nightly}
                   Retry: DatabaseUnavailable (Aurora vừa dậy) 3 lần, lùi 10 s x2
                   Catch: mọi lỗi khác -> ghi nhận {status: failed} cho người đó, không làm hỏng người khác
       Summarize   Lambda {op: summarize}: đếm ok/skipped/failed; có failed thì NÉM lỗi -> execution THẤT BẠI
  -> alarm `yofina-nightly-failed` và `yofina-nightly-timed-out` -> SNS `yofina-alerts`
```

- **Danh tính dịch vụ kèm `user_id`**: Lambda dùng secret của role `yofina_app` (không master), mỗi lần đọc/ghi một người dùng đặt `app.user_id` (RLS). Hàm `app_list_forecast_users` là hàm `SECURITY DEFINER` DUY NHẤT của dự án (migration 0009), chỉ trả cột `id` của người dùng đã khai lương và ngày nhận (đã kiểm trên Aurora: gọi trực tiếp `SELECT FROM users` bằng role đó ra 0 dòng, gọi hàm ra đủ 6).
- **Mỗi người dùng một lần chạy đầy đủ** (`forecast_user`, 10.000 đường); `forecast_runs.trigger = nightly`. Dọn lần chạy cũ (`forecast_keep_runs`, nhưng không bao giờ xóa lần chạy mới nhất của một hũ).
- **Chạy tay**: `aws stepfunctions start-execution --state-machine-arn <arn từ SSM /yofina/forecast/nightly-arn> --region ap-southeast-1`; kết quả ở output của execution (`{total, ok, skipped, failed}`). Đã chạy thật: 6 tài khoản, 6 ok, khoảng 4 giây (Lambda ấm).
- **Người dùng chưa khai lương** thì `skipped` (không phải lỗi). Lỗi một người không làm hỏng người khác nhưng làm execution thất bại ở bước cuối để alarm kêu.
- Tần suất, số song song, giờ chạy, số đường, ngưỡng: context CDK (`infra-cdk/README.md`), không số nào gắn cứng trong mã.
