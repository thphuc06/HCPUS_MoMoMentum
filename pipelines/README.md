# pipelines/

Ba nhịp chạy nền của hệ thống (proposal §8):

| Thư mục | Nhịp | Nội dung | Proposal | Trạng thái |
|---|---|---|---|---|
| `event/` | Event, dưới 1 phút | Cập nhật dự báo nhanh theo sự kiện ledger (phase 2); phân hũ tự động (bước 0, luật, embedding, LLM), phát hiện lệch, cổng nhắc (phase 4, 5). EventBridge -> SQS (có DLQ) -> Lambda idempotent | §10.3 | Dự báo theo sự kiện **xong** (phase 2); phân hũ tự động **xong** (phase 4, Lambda `yofina-classify`, mã ở [`classify/`](classify/README.md)); sinh lại lộ trình theo sự kiện ở [`roadmap/`](roadmap/README.md) |
| `nightly/` | Batch 02:00 giờ Việt Nam | Dự báo lại mọi người dùng (phase 2); điểm chống chịu, hồ sơ hành vi, PELT, bản tin (phase 4, 5). EventBridge Scheduler -> Step Functions | §10.4 | Dự báo đêm **xong** (phase 2) |
| `weekly/` | Chủ nhật | Backtest, hiệu chỉnh khoảng tin cậy, đánh giá agent trên bộ câu chuẩn, đồng bộ kho tri thức | §8 (bảng "Cái gì chạy lúc nào") | **Cắt** (phase 6, Q11): thư mục chỉ có `.gitkeep`. Backtest và hiệu chỉnh chạy tay trên máy, eval chạy tay bằng `evals/`; RAG đã cắt nên không có kho tri thức để đồng bộ ([ADR-0004](../docs/decisions/0004-lech-so-voi-proposal.md) dòng 5) |
| `forecast/` | (mã dùng chung) | **Lõi pipeline dự báo** và ba Lambda vỏ mỏng: batch, consumer sự kiện, tool | §10.4, §9 | Xong (phase 2) |

Mã của `event/` và `nightly/` không nằm trong hai thư mục đó mà ở [`forecast/`](forecast/README.md): batch đêm, đường sự kiện, đặt lại demo và tool `forecast___get_forecast` cần CÙNG một lõi (đọc dữ liệu một người dùng qua các hàm `app_*` có RLS, dựng `ForecastInputs`, gọi `yofina_ml`, ghi ba bảng trong một transaction, phát `forecast.updated`), nên lõi được viết một lần và đóng thành MỘT zip dùng cho ba Lambda. Hai thư mục kia ghi cách nhịp của chúng chạy ([event/README.md](event/README.md), [nightly/README.md](nightly/README.md)). Mô hình nằm ở [../ml/](../ml/README.md); schema ở [../db/](../db/README.md).

Dự báo/Monte Carlo chạy bằng Lambda zip (Python 3.13 arm64, numpy + scipy, không Docker; StatsForecast không được deploy, chỉ chạy trên máy trong báo cáo backtest: [master-plan mục 2](../docs/plan/master-plan.md#2-quyết-định-áp-dụng-cho-mọi-phase)). Data API với `LIMIT` và retry `DatabaseResumingException`: [spike-aurora-data-api.md](../docs/research/spike-aurora-data-api.md).
