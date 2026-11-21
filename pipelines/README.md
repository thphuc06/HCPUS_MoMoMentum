# pipelines/

Ba nhịp chạy nền của hệ thống (proposal §8):

| Thư mục | Nhịp | Nội dung | Proposal |
|---|---|---|---|
| `event/` | Event, dưới 1 phút | Phân hũ tự động (bước 0, luật, embedding, LLM), cập nhật số dư và dự báo nhanh, phát hiện lệch, cổng nhắc; EventBridge → SQS → Lambda idempotent, DLQ | §10.3 |
| `nightly/` | Batch 02:00 (xong trước 06:00) | Dự báo lại (F1), điểm chống chịu (F4), hồ sơ hành vi (F7), PELT, bản tin; EventBridge Scheduler → Step Functions | §10.4 |
| `weekly/` | Chủ nhật | Backtest, hiệu chỉnh khoảng tin cậy, đánh giá agent trên bộ câu chuẩn, đồng bộ kho tri thức | §8 (bảng "Cái gì chạy lúc nào") |

Mô hình nằm ở [../ml/](../ml/README.md); schema ở [../db/](../db/README.md).

Batch dự báo/Monte Carlo chạy trong Lambda container (StatsForecast 332 MB, vượt giới hạn zip), PELT theo tuần, Data API với `LIMIT` và retry `DatabaseResumingException`: [spike-ml-forecasting.md](../docs/research/spike-ml-forecasting.md), [spike-aurora-data-api.md](../docs/research/spike-aurora-data-api.md).