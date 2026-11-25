# Backtest cuối: độ phủ theo độ dài lịch sử và cổng hiện % (BR-31)

Ngày đo: 2026-11-25. Issue #9 (AU-09, ML-03 trong [kiểm toán ML](2026-11-25-audit-ml-forecasting.md) §2.1). Dữ liệu tổng hợp, chạy offline trên
CPU, không gọi AWS.

## Kết luận ngắn

- Dải P10–P90 số dư 30 ngày của **hũ dày** đạt cổng [0,75; 0,85] từ **47 ngày** lịch sử (0,782). Ở 30 ngày một họ bộ sinh tụt còn 0,744.
- Dải của **hũ thưa** chỉ đạt từ **120 ngày** (0,767). Ở 47 ngày nó phủ 0,677, tức người dùng mới như `minh`, `lan`, `vy` đang thấy % không
  đáng tin cho mọi hũ thưa.
- Ngưỡng chọn: `probability_min_history_days` = **47** (hũ dày) và **120** (hũ thưa), ghi trong `ml/yofina_ml/calibration/default.py`. Dưới
  ngưỡng thì ẩn %, chỉ còn nhãn Cao/Vừa/Thấp và trạng thái hũ.

## Độ phủ theo độ dài lịch sử

### Phương pháp

- Persona: 36 persona giữ ra ngoài (seed 201–206, hai họ bộ sinh `hurdle_lognormal` và `shopping_sessions`, mọi cấu hình), giống phép A của
  kiểm toán.
- Origin: từ ngày 120 tới 293, bước 7 (25 origin mỗi persona), chân trời 30 ngày. Mọi độ dài dùng **cùng một tập origin**, nên chênh lệch
  giữa các hàng chỉ do độ dài lịch sử. Kiểm toán đo từ ngày 90, nên số ở đây lệch vài phần nghìn so với bảng §2.1 (47 ngày, hũ thưa: 0,677
  ở đây so với 0,69 ở kiểm toán).
- Độ dài L: 30, 47, 60, 75, 90, 105, 120 ngày, cộng "đủ" (không cắt, 120 đến 293 ngày). Lịch sử cắt bằng `backtest.studies._truncate`: chỉ giữ
  L ngày gần nhất của mọi hũ, đúng như người dùng mới vào app L ngày trước.
- Dự báo: `forecast_user` với `calibrated_config()` (hiệu chỉnh `rho`/`level_sigma` hiện hành), 2.000 đường. Cổng lịch sử bị tắt trong lúc
  đo (ngưỡng 0) để mọi hũ đều có `p_shortfall`.
- Chấm: số dư thật ngày h có nằm trong [P10; P90] số dư dự báo ngày h không (h = 7, 14, 30), tách theo nhóm `series_kind` của chính lần
  chạy đó (`dense`, `sparse`; hũ nghĩa vụ để riêng như backtest phase 2).
- Tất định: hạt Monte Carlo của mỗi lần là `seed × 1000 + origin`, như `backtest/evaluate.py`.

### Số đo

Độ phủ khoảng P10–P90 của số dư (mục tiêu 0,80, cổng [0,75; 0,85]). "Theo họ" là `hurdle_lognormal` / `shopping_sessions`. In đậm là ô
trượt cổng.

| Lịch sử | Nhóm | n | Phủ 7 / 14 / 30 ngày | Phủ 30 ngày theo họ | Dưới P10 / trên P90 (30 ngày) |
|---|---|---|---|---|---|
| 30 | hũ dày | 1609 | 0,784 / 0,773 / 0,756 | **0,744** / 0,774 | 0,172 / 0,073 |
| 30 | hũ thưa | 4007 | 0,837 / 0,763 / **0,603** | **0,575** / **0,627** | 0,259 / 0,139 |
| **47** | **hũ dày** | 1563 | 0,796 / 0,784 / **0,782** | 0,774 / 0,793 | 0,154 / 0,065 |
| **47** | **hũ thưa** | 4053 | 0,857 / 0,798 / **0,677** | **0,648** / **0,701** | 0,216 / 0,107 |
| 60 | hũ dày | 1580 | 0,804 / 0,794 / 0,796 | 0,785 / 0,814 | 0,144 / 0,060 |
| 60 | hũ thưa | 4036 | 0,867 / 0,813 / **0,711** | **0,691** / **0,728** | 0,191 / 0,099 |
| 75 | hũ dày | 1570 | 0,807 / 0,796 / 0,807 | 0,797 / 0,822 | 0,136 / 0,057 |
| 75 | hũ thưa | 4046 | 0,870 / 0,822 / **0,732** | **0,712** / **0,749** | 0,173 / 0,095 |
| 90 | hũ dày | 1584 | 0,802 / 0,794 / 0,814 | 0,808 / 0,823 | 0,132 / 0,054 |
| 90 | hũ thưa | 4032 | 0,874 / 0,832 / **0,747** | **0,727** / 0,763 | 0,166 / 0,088 |
| 105 | hũ dày | 1571 | 0,807 / 0,807 / 0,813 | 0,806 / 0,823 | 0,139 / 0,048 |
| 105 | hũ thưa | 4045 | 0,872 / 0,837 / 0,757 | **0,736** / 0,776 | 0,157 / 0,085 |
| **120** | **hũ dày** | 1574 | 0,809 / 0,809 / **0,810** | 0,796 / 0,830 | 0,143 / 0,047 |
| **120** | **hũ thưa** | 4042 | 0,875 / 0,842 / **0,767** | 0,750 / 0,782 | 0,151 / 0,082 |
| đủ | hũ dày | 1563 | 0,795 / 0,800 / 0,804 | 0,786 / 0,832 | 0,147 / 0,049 |
| đủ | hũ thưa | 4053 | 0,874 / 0,849 / 0,787 | 0,769 / 0,802 | 0,135 / 0,078 |
| mọi độ dài | hũ nghĩa vụ | 936 | 0,837 / 0,787 / **0,728** | 0,788 / **0,667** | 0,095 / 0,177 |

Đọc bảng:

- Hũ dày gần như không đổi theo độ dài (0,78 đến 0,81 từ 47 ngày trở lên). Hũ thưa tăng đều từ 0,60 (30 ngày) lên 0,79 (lịch sử đủ): mô
  hình hũ thưa cần nhiều ngày để ước tần suất ngày có chi và cỡ khoản chi.
- Ở hũ thưa, phần trượt nằm chủ yếu ở đuôi dưới (số dư thật dưới P10: 0,216 ở 47 ngày so với 0,107 trên P90). Dải đang lạc quan, đúng chiều
  đắt cho sản phẩm báo "hũ sắp cạn".
- Hũ nghĩa vụ không đổi theo độ dài vì dự báo của nó chủ yếu đi theo lịch nghĩa vụ, không theo lịch sử chi. Họ `shopping_sessions` chỉ phủ
  0,667, dưới cổng ở mọi độ dài (xem "Điều chưa xử lý").
- Brier của `p_shortfall` theo số dư thật có trong JSON nhưng không dùng: số dư thật của bộ sinh hiếm khi âm trước kỳ lương (Brier
  của tần suất chung ở hũ dày chỉ 0,005 đến 0,023), nên phép so kỹ năng suy biến. Kỹ năng xác suất theo độ dài đã đo bằng số dư kịch bản ở kiểm toán §2.2: ở
  47 ngày vẫn hơn tần suất chung (hũ dày Brier 0,162 so với 0,233; hũ thưa 0,214 so với 0,241).

### Ngưỡng đã chọn và lý do

Luật (`ml/yofina_ml/backtest/history_gate.py`, `choose_thresholds`): với mỗi loại chuỗi, ngưỡng là độ dài nhỏ nhất của lưới mà từ đó trở
lên (mọi độ dài lớn hơn trong lưới và cả lịch sử đủ) độ phủ 30 ngày nằm trong [0,75; 0,85] ở **cả hai họ** và ở số gộp. Đây là luật
`probability_gate` của phase 2 (`backtest/cli.py`) thêm chiều độ dài.

| Loại chuỗi | Ngưỡng | Lý do |
|---|---|---|
| Hũ dày | 47 ngày | 30 ngày trượt ở họ `hurdle_lognormal` (0,744); từ 47 ngày mọi ô đạt. Lưới không có điểm giữa 30 và 47 nên ngưỡng là 47, phía an toàn |
| Hũ thưa | 120 ngày | 105 ngày vẫn trượt ở họ `hurdle_lognormal` (0,736); 120 ngày đạt (0,750 / 0,782), lịch sử đủ đạt (0,769 / 0,802) |

Hai ngưỡng nằm trong hiệu chỉnh (`probability_min_history_days` của `dense` và `sparse` trong `calibration/default.py`), không gắn cứng trong
mã. Engine chỉ phát `p_shortfall` khi `probability_ok` của loại chuỗi đúng VÀ `history_days` của hũ từ ngưỡng trở lên
(`SeriesCalibration.probability_ok_at`); hũ dưới ngưỡng cũng không lên nhóm Cao (BR-30 cần "khoảng đã hiệu chỉnh đạt"). Pipeline ghi đè
được bằng khóa tùy chọn `forecast_probability_min_history_days_dense` và `forecast_probability_min_history_days_sparse` (biến môi trường
`YOFINA_...` hoặc SSM); vắng thì theo backtest.

Ảnh hưởng tới persona demo (47 ngày lịch sử, ước theo tỷ lệ ngày có chi của bộ sinh, ngưỡng hũ thưa 0,5): hũ Ăn uống của `minh`, `lan`,
`vy` là hũ dày nên vẫn hiện % (cảnh 1 giữ "cạn 23/11" và % của hũ Ăn uống). Các hũ còn lại là hũ thưa nên ẩn %, vẫn giữ trạng thái (Hóa đơn
của `minh` vẫn "sát") và nhãn tin cậy. Giao diện đã xử lý trường hợp này: `ForecastBlock` bỏ dòng "Khả năng hụt" và ghi "Chưa đủ cơ sở để
nêu xác suất" dưới nhãn tin cậy khi khối không có `p_shortfall` (test `ForecastBlock.test.tsx`), nên không phải sửa frontend.

### Chạy lại

```powershell
uv run scripts/ml_history_gate.py --out ml/backtest-results/history-gate.json --write-calibration
```

Lệnh in bảng trên, ghi JSON (`ml/backtest-results/history-gate.json`) và ghi lại hai ngưỡng vào `calibration/default.py` (giữ nguyên
`rho`, `level_sigma`, `probability_ok`). Bỏ `--write-calibration` để chỉ đo; `--quick` để kiểm khói (2 seed, origin bước 28, vài phút).
Bản đầy đủ mất khoảng 38 phút trên máy dev (2.290 giây; 36 persona × 25 origin × 8 độ dài, 52.416 bản ghi). `scripts/ml_backtest.py --write-calibration` của phase 2
giữ nguyên hai ngưỡng khi sinh lại `rho`/`level_sigma`.

## Điều chưa xử lý

- **Hũ nghĩa vụ** phủ 0,728 ở mọi độ dài (họ `shopping_sessions` 0,667), dưới cổng. Hũ nghĩa vụ không có chi thường nên rơi vào nhóm hũ thưa
  và hiện % từ 120 ngày lịch sử. Cần một ô hiệu chỉnh riêng theo loại hũ `obligation` nếu muốn chặt đúng BR-31; việc này ngoài phạm vi #9.
- **Ngưỡng hũ thưa sát mép**: ở 120 ngày họ `hurdle_lognormal` phủ đúng 0,750 (làm tròn 3 chữ số). Chạy lại với seed khác có thể đẩy ngưỡng lên
  trên 120. Cách bền hơn là sửa dải hũ thưa ở lịch sử ngắn (chạy lại lưới `level_sigma` có đơn vị lịch sử ngắn, kiểm toán §2.3), rồi đo lại để
  hạ ngưỡng.
- Lưới độ dài thô (bước 13 đến 17 ngày), nên ngưỡng thật có thể thấp hơn một chút.
- Dữ liệu tổng hợp hai họ bộ sinh; chưa có dữ liệu thật để kiểm.
