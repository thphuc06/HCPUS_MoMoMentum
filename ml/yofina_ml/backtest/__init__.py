"""Khung backtest rolling-origin của gói ML (chỉ để đo và hiệu chỉnh, không phải mã sản phẩm: có thể dùng pandas hoặc
StatsForecast nếu cài, KHÔNG được import từ mã sản phẩm). Chạy bằng `uv run scripts/ml_backtest.py`.

- `evaluate`: đo `forecast_user` rolling-origin trên hai họ bộ sinh (pinball so với seasonal naive, độ phủ theo ngày và theo
  tổng cộng dồn 7/14/30 ngày, tách hũ dày/thưa và trước/sau điểm gãy, độ tin cậy của xác suất hụt).
- `calibrate`: chọn rho và level_sigma theo độ phủ tổng cộng dồn và ghi `calibration/default.py`.
- `short_history`: mô hình nào thắng ở từng độ dài lịch sử (cơ sở của ngưỡng khởi đầu lạnh).
"""
