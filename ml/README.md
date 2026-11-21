# ml/

Mô hình và kỹ thuật ML/thống kê (phần số, không phải LLM): dự báo chi theo hũ (hurdle tự viết bằng numpy làm mặc định; StatsForecast chỉ làm baseline; Chronos-2 đề xuất để ngoài MVP, chưa chốt), adaptive conformal inference tự viết, mô phỏng Monte Carlo có tương quan, điểm chống chịu (Spend/Save/Borrow/Plan), phát hiện thay đổi hành vi (PELT/ruptures theo tuần; CUSUM/PageHinkley tự viết để "nghi"; bỏ ADWIN), z bền MAD cho khoản lớn (bỏ PyOD), quy hoạch tuyến tính phân bổ hũ bằng `scipy.optimize.linprog` (bỏ PuLP), phân cụm hồ sơ hành vi, embedding cho phân loại (chuẩn hóa chuỗi trước khi nhúng).

- Proposal: §11 (bảng ML và thống kê), §10.4 (batch đêm), §14 (StatsForecast/Darts, ruptures, scikit-learn; Chronos-2 trên SageMaker và PyOD không còn trong bộ tối thiểu).
- Tính năng: F1, F2, F4, F5, F7. Chạy trong pipeline [../pipelines/](../pipelines/README.md) và qua tool `forecast___*`, `planner___*`.
- Cần tra paper/tài liệu trước khi cài: [../docs/references/links.md](../docs/references/links.md).
- Số đo, bộ tối thiểu và code thử (dữ liệu tổng hợp; StatsForecast cần container 332 MB; khoảng tổng 30 ngày phủ thiếu): [spike-ml-forecasting.md](../docs/research/spike-ml-forecasting.md).