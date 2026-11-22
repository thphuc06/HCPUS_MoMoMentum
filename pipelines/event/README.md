# pipelines/event/

Nhịp **sự kiện, dưới 1 phút** (proposal §10.3): ledger ghi một thứ gì đó -> dự báo của hũ liên quan được cập nhật. Phase 2 làm phần **cập nhật dự báo**; phân loại giao dịch tự động (bước 0, luật, embedding, LLM), phát hiện lệch và cổng nhắc là phase 4, 5. Mã nằm ở [../forecast/](../forecast/README.md) (`yofina_forecast/consumer.py`, `idempotency.py`, `handler_event.py`); hạ tầng ở `infra-cdk/lib/forecast-pipeline.ts`.

```
Lambda ledger  --PutEvents-->  EventBridge bus `yofina-bus`  (SAU khi transaction DB commit; lỗi phát không làm hỏng việc ghi)
   rule `yofina-forecast-ledger-events`: source yofina.ledger, detail-type ∈ {transaction.recorded, salary.confirmed, obligation.changed, profile.updated}
     -> SQS `yofina-forecast-events` (visibility 540 s, DLQ `yofina-forecast-events-dlq` sau 3 lần giao, alarm khi DLQ có tin)
        -> Lambda `yofina-on-transaction` (batch 10, không chờ gom, đồng thời tối đa 5, partial batch response)
```

| Sự kiện | Việc |
|---|---|
| `transaction.recorded` | chỉnh **nhanh** các hũ trong `jar_codes` (`update_forecast`, 5.000 đường, trên phân phối đã fit của lần chạy trước đọc lại từ `forecast_runs.params.jar_state`). Mua bằng hạn mức (`funding_source` credit) không đổi số dư hũ nên bỏ qua; dòng gắn nghĩa vụ (`obligation_id`) chạy đầy đủ |
| `salary.confirmed`, `obligation.changed`, `profile.updated` | chạy **đầy đủ** mọi hũ (`forecast_user`, 10.000 đường) |

- **Đường nhanh rơi về đầy đủ** (ghi `params.pipeline.fast_fallback`): hũ chưa có dự báo (`no_previous`), lần chạy trước khác ngày mô phỏng (`app_date_changed`), quá cũ (`previous_too_old`, mặc định 24 giờ), đã vượt ngưỡng khởi đầu lạnh (`left_cold_start`, theo `ml/README.md`), hoặc `params` thiếu phân phối của hũ (`no_jar_state`).
- **Gộp theo người dùng**: nhiều sự kiện của cùng một người trong một lô chỉ gây MỘT lần chạy (hợp các hũ; một sự kiện đòi chạy đầy đủ thì cả nhóm chạy đầy đủ).
- **Idempotency theo `event_id`** (bảng DynamoDB `yofina-idempotency`, khóa `event_id`, TTL 3 ngày): `PutItem` có điều kiện giành khóa thuê (120 giây); xong thì `done` (lần giao trùng bị bỏ qua, "không tính hai lần"); lỗi thì nhả khóa và báo lỗi từng mục để SQS giao lại; tiến trình chết giữa chừng thì khóa thuê hết hạn và lần giao lại giành được. Bảng nằm cùng stack `YofinaTools` (không đụng `YofinaFoundation` có termination protection), `DESTROY` khi gỡ stack.
- **Độ trễ đo thật** (giao dịch 200.000 ₫ từ hũ Ăn uống -> `GET /forecasts/an_uong` có lần tính mới): vài giây (3-4 giây đo được, mục tiêu dưới 60 giây). Log `EventLagMs` (EMF, namespace `Yofina/Forecast`) ghi độ trễ từ `occurred_at` của sự kiện tới lúc consumer bắt đầu.
- **Đặt lại demo** (`POST /demo/reset`) tính dự báo ĐỒNG BỘ trước khi trả (ledger gọi `yofina-forecast-batch`, `forecast_ready: true`), rồi vẫn phát `profile.updated` (hợp đồng): consumer chạy thêm một lần đầy đủ vài giây sau, cùng dữ liệu và cùng hạt nên cùng số, chỉ `computed_at` đổi.
