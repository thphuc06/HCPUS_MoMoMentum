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

## Hiệu chỉnh CQR và PAV (#25)

Ngày đo: 2026-11-25. Issue #25 (ML-04, ML-07, ML-08, ML-09 trong [kiểm toán ML](2026-11-25-audit-ml-forecasting.md) §2.1 đến §2.3, §3.2).
Dữ liệu tổng hợp, chạy offline trên CPU, chỉ numpy và scipy, không gọi AWS.

### Kết luận ngắn

- **Dải số dư hũ dày** ở 120 ngày lịch sử (như `minh`), ngày 30: thật dưới P10 **0,143 → 0,098**, thật trên P90 **0,047 → 0,104**, độ
  phủ 0,810 → 0,798 (theo họ 0,796 / 0,800), dải rộng thêm 1%. Đạt mục tiêu của issue: độ phủ trong [0,75; 0,85] và mỗi đuôi gần 10%.
- **`p_shortfall` qua PAV chỉ còn ở hũ thưa.** Hũ thưa ở 120 ngày: Brier 0,1711 → 0,1701, sai lệch lớn nhất của bảng độ tin cậy
  0,049 → 0,025. Hũ dày thì PAV làm tệ hơn: sai lệch ở 120 ngày 0,070 → 0,100 (ô 0,3 đến 0,5: p 0,40 so với tần suất thật 0,46 trước
  PAV, 0,37 so với 0,47 sau), ở lịch sử đủ 0,090 → 0,092, Brier gần như không đổi (0,1609 → 0,1607). Cổng PAV xét từng loại hũ nên bảng
  của hũ dày bị bỏ: `p_shortfall` hũ dày là p thô của Monte Carlo (mục "Cổng PAV theo loại hũ").
- **Ngày cạn của hũ thưa** sai TB 6,45 ngày, chỉ 28% số ca trong ±3 ngày (hũ dày 3,48 ngày, 59%). Khi bật công tắc, hũ thưa không nêu
  ngày cụ thể: `run.params["show_runout_date"]` của kết quả dự báo ghi `false` cho hũ đó, `runout_date` vẫn giữ để tương thích ngược.
- Công tắc `recalibrate` **bật** trong `ml/yofina_ml/calibration/default.py`, vì tập kiểm qua cả bốn điều kiện của cổng dải (mục "Cổng").

### Phương pháp

- **Vì sao không đo trên `minh`**: persona demo được dựng ngược từ ngày neo nên không có số dư "tương lai" để so (kiểm toán §3.1). Đo
  trên hai họ bộ sinh tổng hợp như các mục trên, với lịch sử cắt còn đúng **120 ngày** như `minh` sau issue #8, kèm 47 ngày (như `lan`,
  `vy`) và lịch sử đủ để biết cách sửa có làm hỏng độ dài khác không.
- **Tách tập**: học bảng trên 24 persona seed 101–104, đo trên 36 persona seed 201–206 (hai họ, mọi cấu hình). Không persona nào nằm ở
  cả hai tập. Origin từ ngày 120 bước 7, chân trời 30 ngày, 2.000 đường, hạt Monte Carlo `seed × 1000 + origin`, cổng % theo lịch sử tắt khi
  đo (như mục trên). Tập học có 3.122 bản ghi dải hũ dày và 40.380 bản ghi số dư kịch bản; tập kiểm có 4.700 và 59.385.
- **CQR bất đối xứng** (Romano, Patterson, Candès 2019, Định lý 2): ở mỗi ngày h từ 1 đến 30, điểm dưới (P10 − thật) / (chi TB 28 ngày × h)
  và điểm trên (thật − P90) / (chi TB 28 ngày × h); độ lệch mỗi phía là lượng tử hiệu chỉnh bậc ⌈(n + 1) × 0,9⌉ của điểm phía đó. P10 hạ
  xuống và P90 nâng lên (hay thu vào, nếu độ lệch âm) đúng lượng đó; P50 và ngày cạn không đổi. Chỉ hũ dày: với hũ thưa chi TB nhỏ và nhiễu,
  dải nở 2,4 đến 3,2 lần (kiểm toán §2.3).
- **Hai bảng CQR theo độ dài lịch sử** (kiểu Mondrian conformal): bảng học ở 47 ngày dùng cho hũ dưới 120 ngày lịch sử, bảng học ở 120
  ngày và lịch sử đủ dùng từ 120 ngày. Chọn cách này TRƯỚC khi đo tập kiểm, bằng cách chia đôi tập học (học trên seed 101–102, đo trên
  103–104, rồi đổi chiều): một bảng gộp làm hẹp đuôi trên theo lịch sử dài nên độ phủ ở 47 ngày còn 0,745 ở một chiều chia, hai bảng cho
  0,79 đến 0,81. Chuẩn hóa điểm theo độ rộng dải (thay cho chi TB × h) cho kết quả tương đương nhưng dải rộng hơn, nên giữ cách của kiểm toán.
- **PAV cho `p_shortfall`** (Kuleshov và cộng sự 2018; Dimitriadis, Gneiting, Jordan 2021): số dư kịch bản b = α × chi TB 28 ngày × w
  (w là số ngày tới lương, cần w ≥ 3; α thuộc 0,6 / 0,8 / 1,0 / 1,25 / 1,6, lưới của `evaluate_shortfall` phase 2), p thô tính trên đúng
  các đường Monte Carlo mà `forecast_user` dùng cho hũ đó, kết cục là chi thật trong w ngày vượt b. Không dùng số dư thật vì nó hiếm khi
  âm trước kỳ lương (mục trên). Học một bảng cho hũ dày, một cho hũ thưa, chỉ trên các ca mà sản phẩm có hiện % (hũ dày từ 47, hũ thưa từ
  120 ngày lịch sử), không gồm hũ nghĩa vụ. Bảng nào được ghi vào hiệu chỉnh do cổng PAV theo loại hũ quyết định.
- **Ngày cạn**: trên cùng số dư kịch bản, ngày dự báo là ngày đầu số dư P50 ≤ 0 trong 30 ngày (như `runout_date`), ngày thật là ngày đầu
  số dư thật ≤ 0. "Trong ±3 ngày" tính trên mọi ca có ngày dự báo (thật không cạn trong 30 ngày là trượt); "sai TB" tính trên ca có cả hai
  ngày. Số hơi khác kiểm toán §3.2 (hũ thưa 5,63 ngày) vì kiểm toán chỉ chấm ca có p ≥ 0,2 và origin từ ngày 90.

### Cổng bật `recalibrate`

Đọc trên tập kiểm, hũ dày, ngày 30. Cổng viết trước khi chạy tập kiểm (docstring của `ml/yofina_ml/backtest/recalibrate.py`):

| Điều kiện | Số đo | Đạt |
|---|---|---|
| 120 ngày: độ phủ gộp và từng họ trong [0,75; 0,85] | 0,798; 0,796 / 0,800 | có |
| 120 ngày: thật dưới P10 trong [0,075; 0,125] | 0,098 | có |
| 120 ngày: thật trên P90 trong [0,075; 0,125] | 0,104 | có |
| 47 ngày và lịch sử đủ: độ phủ gộp vẫn trong [0,75; 0,85] | 0,812; 0,788 | có |

Bản đầu của #25 có thêm điều kiện thứ năm: Brier sau PAV không cao hơn trước, ở 120 ngày, cả hũ dày và hũ thưa. Điều kiện đó qua, nhưng
PAV hũ dày vẫn làm bảng độ tin cậy tệ hơn (mục dưới), nên nó được thay bằng cổng PAV theo loại hũ. Công tắc nay chỉ xét dải.

### Cổng PAV theo loại hũ

Luật (`pav_gate` trong `recalibrate.py`), viết và commit trước khi chạy lại tập kiểm: bảng PAV của một loại hũ chỉ vào hiệu chỉnh khi, ở
MỌI độ dài lịch sử của tập kiểm có ca hiện % của loại đó, PAV không làm tăng sai lệch lớn nhất của bảng độ tin cậy (ô từ 30 ca) VÀ không
làm tăng Brier. So ở độ chính xác của bảng: sai lệch 3 chữ số, Brier 6 chữ số. Thiếu số để so thì không giữ. Loại không qua thì không có
`p_isotonic`; công tắc, CQR và việc ẩn ngày cạn hũ thưa không đổi. Lưu ý: số của lần chạy đầu đã biết khi viết luật. Đọc riêng ở 120
ngày hay ở mọi độ dài đều cho cùng kết luận, và luật chọn cách chặt hơn.

| Loại hũ | Lịch sử | Sai lệch lớn nhất trước → sau | Brier trước → sau | Đạt |
|---|---|---|---|---|
| hũ dày | 47 | 0,070 → 0,053 | 0,1643 → 0,1638 | có |
| hũ dày | 120 | 0,070 → **0,100** | 0,1609 → 0,1607 | **không** |
| hũ dày | đủ | 0,090 → **0,092** | 0,1653 → 0,1651 | **không** |
| hũ thưa | 120 | 0,049 → 0,025 | 0,1711 → 0,1701 | có |
| hũ thưa | đủ | 0,044 → 0,022 | 0,1666 → 0,1660 | có |

Kết luận: **giữ PAV cho hũ thưa, bỏ PAV hũ dày**. Hũ thưa ở 47 ngày không hiện % (ngưỡng 120 ngày) nên không có ô để xét. Lý do bỏ ở
hũ dày: bảng học trên seed 101–104 không chuyển được sang seed 201–206. Trên tập học, ô 0,3 đến 0,5 dự báo cao hơn tần suất thật (0,40 so
với 0,37); trên tập kiểm thì thấp hơn (0,40 so với 0,46). PAV học theo tập học nên kéo p xuống, trong khi tập kiểm cần kéo lên. Bảng cũ còn một đoạn
phẳng rộng: p thô từ 0,311 tới 0,405 đều thành 0,306, nên what-if làm p thô đổi trong đoạn đó báo % không đổi. Bỏ bảng thì hai p thô khác
nhau cho hai % khác nhau (test `test_hieu_chinh_mac_dinh_hai_p_tho_khac_nhau_cua_hu_day_ra_hai_phan_tram_khac_nhau`). Bảng PAV hũ thưa
cũng có đoạn phẳng, rộng nhất 0,078 (p thô 0,8725 đến 0,951 đều thành 0,903).

### Số đo trên tập kiểm (seed 201–206)

Dải P10–P90 số dư hũ dày. Độ rộng tương đối là (P90 − P10) / (chi TB 28 ngày × 30) ở ngày 30.

| Lịch sử | n | Phủ 30 ngày trước → sau | Phủ 30 ngày theo họ (sau) | Phủ 7 / 14 ngày (sau) | Dưới P10 trước → sau | Trên P90 trước → sau | Độ rộng tương đối trước → sau |
|---|---|---|---|---|---|---|---|
| 47 | 1563 | 0,782 → 0,812 | 0,828 / 0,787 | 0,788 / 0,804 | 0,154 → 0,073 | 0,065 → 0,115 | 0,79 → 0,93 (+18%) |
| **120** | 1574 | 0,810 → **0,798** | 0,796 / 0,800 | 0,789 / 0,801 | 0,143 → **0,098** | 0,047 → **0,104** | 0,85 → 0,85 (+1%) |
| đủ | 1563 | 0,804 → 0,788 | 0,776 / 0,807 | 0,776 / 0,801 | 0,147 → 0,106 | 0,049 → 0,106 | 0,87 → 0,88 (+1%) |

Độ lệch đã học (đơn vị chi TB 28 ngày × h; dương là nới, âm là thu):

| Bảng | Dưới, ngày 7 / 14 / 30 | Trên, ngày 7 / 14 / 30 |
|---|---|---|
| Lịch sử dưới 120 ngày (học ở 47 ngày) | 0,097 / 0,172 / 0,203 | −0,053 / −0,061 / −0,063 |
| Lịch sử từ 120 ngày (học ở 120 ngày và lịch sử đủ) | 0,046 / 0,118 / 0,083 | −0,059 / −0,066 / −0,074 |

Ở lịch sử dài, dải chỉ dời xuống: hạ P10 và hạ P90 gần bằng nhau nên độ rộng gần như không đổi. Ở 47 ngày, P10 hạ nhiều hơn nên dải rộng thêm 18%.

`p_shortfall` trên số dư kịch bản, các ca có hiện %. Bảng độ tin cậy: p dự báo TB → tần suất thật trong các ô 0–0,1 / 0,1–0,3 / 0,3–0,5 /
0,5–0,7 / 0,7–0,9 / 0,9–1. Sai lệch lớn nhất tính trên ô có từ 30 ca. Cột "sau" của hũ dày là số NẾU áp PAV; sản phẩm dùng cột "trước"
vì PAV hũ dày không qua cổng.

| Lịch sử | Nhóm | n | Brier trước → sau | Brier tần suất chung | Sai lệch lớn nhất trước → sau | Độ tin cậy trước | Độ tin cậy sau |
|---|---|---|---|---|---|---|---|
| 47 | hũ dày | 7020 | 0,1643 → 0,1638 | 0,2491 | 0,070 → 0,053 | 0,05→0,12; 0,19→0,23; 0,40→0,42; 0,60→0,63; 0,80→0,84; 0,94→0,97 | 0,07→0,09; 0,17→0,20; 0,37→0,42; 0,57→0,59; 0,77→0,78; 0,94→0,94 |
| **120** | **hũ dày** | 7080 | 0,1609 → 0,1607 | 0,2496 | 0,070 → **0,100** | 0,05→0,10; 0,19→0,23; 0,40→0,46; 0,60→0,67; 0,80→0,86; 0,95→0,95 | 0,06→0,05; 0,17→0,20; 0,37→0,47; 0,57→0,63; 0,77→0,81; 0,94→0,94 |
| **120** | **hũ thưa** | 12715 | 0,1711 → 0,1701 | 0,2209 | 0,049 → **0,025** | 0,05→0,05; 0,20→0,17; 0,39→0,34; 0,59→0,57; 0,78→0,75; 0,94→0,90 | 0,07→0,06; 0,19→0,20; 0,41→0,40; 0,61→0,62; 0,78→0,76; 0,91→0,89 |
| đủ | hũ dày | 7030 | 0,1653 → 0,1651 | 0,2496 | 0,090 → 0,092 | 0,04→0,10; 0,19→0,24; 0,40→0,45; 0,60→0,69; 0,80→0,85; 0,95→0,95 | 0,06→0,05; 0,18→0,21; 0,37→0,45; 0,57→0,66; 0,77→0,80; 0,94→0,93 |
| đủ | hũ thưa | 12765 | 0,1666 → 0,1660 | 0,2212 | 0,044 → 0,022 | 0,05→0,04; 0,20→0,16; 0,39→0,36; 0,59→0,59; 0,79→0,75; 0,94→0,93 | 0,07→0,05; 0,19→0,20; 0,42→0,42; 0,61→0,63; 0,78→0,77; 0,91→0,89 |

Ngày cạn trên số dư kịch bản (trước khi đổi; sau khi bật, hũ thưa không nêu ngày, ngày của hũ dày không đổi vì P50 không đổi):

| Lịch sử | Nhóm | Ca có ngày dự báo | Trong ±3 ngày | Sai TB (ngày) |
|---|---|---|---|---|
| 47 | hũ dày | 5884 | 0,575 | 3,55 |
| 47 | hũ thưa | 10524 | 0,253 | 6,54 |
| **120** | hũ dày | 5891 | 0,585 | 3,48 |
| **120** | **hũ thưa** | 8992 | **0,280** | **6,45** |
| đủ | hũ dày | 5813 | 0,579 | 3,55 |
| đủ | hũ thưa | 8968 | 0,290 | 6,39 |

### Công tắc, tham số và đầu ra

- `CALIBRATION["recalibrate"]` bật cả ba việc. Bảng nằm ở `dense.cqr` (danh sách hai bảng, mỗi bảng có `min_history_days`) và
  `sparse.p_isotonic`; hũ dày không có `p_isotonic` vì không qua cổng PAV. Số đo của cổng ở `meta.recalibration` (`gate.pav` cho từng loại
  hũ, `pav_kinds` là các loại giữ PAV). Mọi số do lệnh dưới đây sinh, không gõ tay. Tệp hiệu chỉnh cũ không có các khóa này thì hành vi như
  trước #25; ghi đè từng phần được qua `ForecastConfig.extra["calibration"]` (ví dụ `{"recalibrate": false}`, hoặc
  `{"sparse": {"p_isotonic": null}}` để bỏ PAV hũ thưa).
- Tắt công tắc thì `forecast_user` cho kết quả từng hũ giống hệt bản trước #25 (test hồi quy
  `tests/unit/ml/test_ml_recalibration.py::test_tat_cong_tac_thi_dau_ra_giong_het_tep_hieu_chinh_cu`).
- Bật thì `run.params["show_runout_date"]` là {mã hũ: có nêu ngày cạn không}: `false` cho hũ thưa, trừ hũ nghĩa vụ (ngày cạn của nó đi theo
  lịch nghĩa vụ đã biết). Bên dùng đọc bằng `yofina_ml.api.runout_date_shown(result, jar_code)`; kết quả cũ không có khóa thì luôn là có nêu.
  `JarSummary` không đổi (cột của bảng `forecast_jar_summaries` giữ nguyên), nên bên dùng chưa đọc cờ thì vẫn hiện ngày như cũ.
- PAV không áp khi p là tất định (số dư đã âm, hay không còn ngày nào trước kỳ lương) và không áp cho hũ nghĩa vụ. `p_shortfall_se` vẫn là
  sai số chuẩn Monte Carlo của p thô.
- `params.calibration` của mỗi lần chạy mang theo các bảng, dưới giới hạn 64 KB mỗi dòng của Data API. Bỏ bảng PAV hũ dày làm `params`
  nhỏ đi khoảng 1,9 KB: 14,3 KB → 12,4 KB (`json.dumps` của `run.params`, một lần chạy bảy hũ của persona tổng hợp).

### Chạy lại

```powershell
uv run scripts/ml_backtest.py --write-recalibration --out recalibration.json --tables recalibration.md
```

Lệnh học bảng, đo trước/sau, in ba bảng trên và kết quả hai cổng, rồi ghi bảng (PAV chỉ của loại qua cổng) và công tắc vào
`ml/yofina_ml/calibration/default.py` (giữ nguyên mọi khóa khác). Sau đó chạy `uv run ruff format ml/yofina_ml/calibration/default.py`.
`--recalibrate` thay cho `--write-recalibration` để chỉ đo; `--quick` để kiểm khói (1 seed học, 2 seed kiểm, origin bước 28, khoảng 2 phút).
Bản đầy đủ mất khoảng 21 phút trên máy dev (1.264 giây ở lần sinh lại theo cổng PAV mới; lần đầu 1.429 giây). Kết quả tất định: lần sinh lại
cho đúng các số của lần đầu, chỉ khác phần cổng. Chạy lại
`--write-calibration` của phase 2 (đổi `rho`/`level_sigma`) thì bảng hiệu chỉnh lại không còn đúng: lệnh đó bỏ bảng và tắt công tắc, cần chạy
lại `--write-recalibration` sau.

### Điều chưa xử lý

- **`p_shortfall` hũ dày vẫn thấp hơn tần suất thật ở giữa thang.** Sau khi bỏ PAV, ở 120 ngày ô 0,3 đến 0,5 là 0,40 so với 0,46 và ô 0,5
  đến 0,7 là 0,60 so với 0,67 (sai lệch lớn nhất 0,070). PAV học trên seed 101–104 kéo p theo chiều ngược lại (mục "Cổng PAV theo loại
  hũ"). Cách bền hơn là học trên nhiều persona hơn, hay gộp cả hai tập seed rồi kiểm trên một tập thứ ba.
- Ở 47 ngày, dải hũ dày rộng thêm 18%; thật dưới P10 0,073 và thật trên P90 0,115, cả hai nằm sát mép [0,075; 0,125].
- Hũ có 48 đến 119 ngày lịch sử dùng bảng học ở 47 ngày. Bảng này hạ P10 nhiều hơn, tức thận trọng ở đuôi tốn kém.
- Hũ nghĩa vụ không qua PAV và vẫn nêu ngày cạn. Độ phủ 0,728 của hũ này (mục trên) chưa sửa.
- Persona demo không có tương lai thật, nên chưa đo được ảnh hưởng trên chính `minh`. Bật công tắc làm đổi dải của hũ Ăn uống ở cảnh 1 và %
  của các hũ thưa có hiện % (qua PAV); % của hũ Ăn uống là p thô như trước #25 vì PAV hũ dày đã bỏ. Ngày cạn 23/11 (theo P50) không đổi. Cần
  đi lại cảnh 1 sau khi deploy Lambda dự báo.
- Dữ liệu tổng hợp hai họ bộ sinh; chưa có dữ liệu thật để kiểm.

## K5: cảnh báo hũ cạn (#26)

Ngày đo: 2026-11-25. Issue #26 (AU-10; ML-01, ML-02 trong [kiểm toán ML](2026-11-25-audit-ml-forecasting.md) §3). Dữ liệu tổng hợp, chạy
offline trên CPU, không gọi AWS. Đo SAU hiệu chỉnh hiện hành: CQR cho dải hũ dày, PAV chỉ cho hũ thưa (mục "Hiệu chỉnh CQR và PAV").
K5 của [ba/08 §3.5](../ba/08-kpi-kinh-doanh.md): cảnh báo trước ít nhất 7 ngày, đúng từ 70%.

### Kết luận ngắn

- **Hũ dày, 120 ngày lịch sử** (như `minh`): cảnh báo đúng trong ±3 ngày **0,572**, chưa đạt mục tiêu 0,70. Sai TB 3,47 ngày. Trung vị
  số ngày báo trước của cảnh báo đúng là **13 ngày**, đạt mức 7 ngày. Seasonal naive 0,441, burn-rate 0,490.
- **Định nghĩa 2**, cảnh báo đúng vì hũ cạn thật trước ngày lương: hũ dày **0,816**, seasonal naive 0,663, burn-rate 0,686.
- **Hũ thưa** (nay không hiện ngày cạn): ±3 ngày 0,287, sai TB 6,24 ngày; định nghĩa 2 là 0,654. Một ngày cụ thể ở hũ thưa chỉ đúng khoảng
  một phần tư đến ba phần mười số lần (0,244 đến 0,301 theo độ dài lịch sử), nên việc chỉ báo "có thể cạn trước ngày lương" (#25) có cơ sở.
- Sản phẩm hơn cả hai baseline ở cả hai định nghĩa, ở mọi độ dài lịch sử và cả hai loại hũ. Đổi lại nó báo ít hơn (hũ dày 120 ngày: 2.445
  cảnh báo so với 3.441 và 3.525), nên bắt được ít ca cạn trước lương hơn (0,696 so với 0,796 và 0,843).

### Phương pháp

Luật đo viết trong docstring của `ml/yofina_ml/backtest/k5.py` trước khi chạy tập kiểm. Đây là phép B của kiểm toán §3.2, đưa vào repo.

- **Vì sao không đo trên persona demo**: `minh`, `lan`, `vy` dựng ngược từ ngày neo nên không có tương lai thật; số dư thật của bộ sinh tổng
  hợp hiếm khi âm trước kỳ lương (kiểm toán §3.1). Vì vậy dùng số dư kịch bản, như phép đo PAV ở mục trên.
- **Mẫu**: 36 persona giữ ra ngoài (seed 201–206, hai họ bộ sinh, mọi cấu hình). Origin từ ngày 120 bước 7, chân trời 30 ngày, lịch sử
  cắt còn 47 ngày, 120 ngày và lịch sử đủ. Lấy mọi hũ chi tiêu và tiết kiệm có chi TB 28 ngày dương và còn ít nhất 8 ngày trước kỳ lương
  (để báo trước 7 ngày là làm được); bỏ hũ nghĩa vụ và hũ khởi đầu lạnh.
- **Số dư kịch bản**: b = α × chi TB 28 ngày × w, α thuộc 0,6 / 0,8 / 1,0 / 1,25 / 1,6, w là số ngày trước kỳ lương; không tiền vào, không
  nghĩa vụ. Ngày cạn thật là ngày đầu tiên b trừ chi thật cộng dồn ≤ 0 trong 30 ngày.
- **Ba phương pháp**, cùng kịch bản. Sản phẩm: biên của `fit_jar`, Monte Carlo với đúng hạt và `rho`/`level_sigma` của `forecast_user`,
  p qua PAV như `forecast_user`, ngày cạn dự báo là ngày đầu số dư P50 ≤ 0. Seasonal naive: như trên với `extra.model = "seasonal_naive"`,
  p thô. Burn-rate: số dư b − chi TB 28 ngày × t, ngày cạn là ngày đầu số đó ≤ 0, không có xác suất.
- **Cảnh báo**: sản phẩm và seasonal naive báo khi p ≥ 0,2 (trạng thái Sát hoặc Hụt) VÀ ngày cạn dự báo trước ngày lương; burn-rate báo
  khi ngày cạn dự báo trước ngày lương. Hũ thưa tính cùng luật để đối chiếu, dù giao diện không hiện ngày của nó.
- **Định nghĩa 1**: cảnh báo có ngày cạn thật cách ngày dự báo không quá ±3 ngày, tính trên mọi cảnh báo (thật không cạn trong 30 ngày là
  sai). Sai TB tính trên cảnh báo có ngày cạn thật. **Định nghĩa 2**: cảnh báo mà hũ cạn thật trước ngày lương.
- **Báo trước**: số ngày từ lúc báo (origin) tới ngày cạn thật; trung vị trên các cảnh báo đúng của từng định nghĩa. Mỗi origin tính riêng,
  nên đây là khoảng báo trước tại một lần báo, không phải từ lần báo đầu tiên của một chuỗi ngày.
- **Bắt được**: trong các ca hũ cạn thật trước ngày lương, tỷ lệ có cảnh báo.

### Số đo

| Lịch sử | Nhóm | Phương pháp | Kịch bản | Cảnh báo | Đ1: đúng ±3 ngày | Sai TB (ngày) | Báo trước trung vị, Đ1 (ngày) | Đ2: cạn trước lương | Báo trước trung vị, Đ2 (ngày) | Bắt được |
|---|---|---|---|---|---|---|---|---|---|---|
| 47 | hũ dày | sản phẩm | 5835 | 2475 | 0,549 | 3,65 | 13 | 0,789 | 12 | 0,700 |
| 47 | hũ dày | seasonal naive | 5835 | 3346 | 0,409 | 4,99 | 12 | 0,641 | 13 | 0,769 |
| 47 | hũ dày | burn-rate | 5835 | 3501 | 0,488 | 3,98 | 13 | 0,675 | 13 | 0,847 |
| 47 | hũ thưa | sản phẩm | 10625 | 3779 | 0,244 | 6,64 | 12 | 0,565 | 9 | 0,564 |
| 47 | hũ thưa | seasonal naive | 10625 | 5864 | 0,181 | 8,08 | 9 | 0,424 | 10 | 0,657 |
| 47 | hũ thưa | burn-rate | 10625 | 6375 | 0,202 | 7,18 | 12 | 0,431 | 9 | 0,726 |
| **120** | **hũ dày** | **sản phẩm** | 5875 | 2445 | **0,572** | 3,47 | 13 | **0,816** | 12 | 0,696 |
| 120 | hũ dày | seasonal naive | 5875 | 3441 | 0,441 | 4,67 | 12 | 0,663 | 13 | 0,796 |
| 120 | hũ dày | burn-rate | 5875 | 3525 | 0,490 | 3,99 | 13 | 0,686 | 13 | 0,843 |
| **120** | **hũ thưa** | **sản phẩm** | 10585 | 3102 | **0,287** | 6,24 | 12 | **0,654** | 9 | 0,547 |
| 120 | hũ thưa | seasonal naive | 10585 | 6286 | 0,189 | 7,89 | 9 | 0,440 | 9 | 0,746 |
| 120 | hũ thưa | burn-rate | 10585 | 6351 | 0,200 | 7,20 | 12 | 0,424 | 9 | 0,726 |
| đủ | hũ dày | sản phẩm | 5825 | 2387 | 0,570 | 3,57 | 13 | 0,819 | 12 | 0,688 |
| đủ | hũ dày | seasonal naive | 5825 | 3393 | 0,445 | 4,62 | 12 | 0,667 | 13 | 0,796 |
| đủ | hũ dày | burn-rate | 5825 | 3495 | 0,491 | 3,98 | 13 | 0,686 | 12 | 0,842 |
| đủ | hũ thưa | sản phẩm | 10635 | 3078 | 0,301 | 6,13 | 12 | 0,671 | 9 | 0,553 |
| đủ | hũ thưa | seasonal naive | 10635 | 6427 | 0,194 | 7,77 | 9 | 0,446 | 9 | 0,768 |
| đủ | hũ thưa | burn-rate | 10635 | 6381 | 0,201 | 7,18 | 12 | 0,425 | 9 | 0,727 |

"Kịch bản" là số (persona, origin, hũ, α); "Cảnh báo" là số kịch bản phương pháp đó báo. Tỷ lệ Đ1, Đ2 chia cho số cảnh báo; "Bắt được"
chia cho số kịch bản hũ cạn thật trước ngày lương.

Đọc bảng:

- Định nghĩa 2 cao hơn định nghĩa 1 vì nó không đòi đúng ngày: cảnh báo đúng khi hũ cạn bất kỳ ngày nào trước lương. Ngược lại, một cảnh
  báo đúng ngày (±3) mà hũ cạn ngay sau ngày lương thì đúng theo định nghĩa 1 nhưng sai theo định nghĩa 2.
- Hũ dày ở 47 ngày kém 120 ngày một chút (0,549 so với 0,572); từ 120 ngày trở lên gần như không đổi (0,570 ở lịch sử đủ).
- Burn-rate bắt được nhiều nhất vì với số dư kịch bản này nó luôn báo khi α ≤ 1 (chi TB × w ≥ b), nhưng 31% cảnh báo của nó là hũ
  không cạn trước lương (hũ dày, 120 ngày), so với 18% của sản phẩm.
- So với số của kiểm toán §3.2 (lịch sử đủ, origin từ ngày 90): sản phẩm hũ dày 0,565 → 0,570, seasonal naive 0,458 → 0,445, burn-rate
  0,469 → 0,491, định nghĩa 2 (một trừ "báo mà không cạn trước lương") 0,841 → 0,819. Chênh lệch do tập origin (từ ngày 120 ở đây) và mã
  đo viết lại; script tạm của kiểm toán không còn nên không so được từng dòng. Kết luận không đổi: chưa đạt 0,70 ở định nghĩa 1, hơn hai
  baseline, báo trước đủ 7 ngày.

### Chạy lại

```powershell
uv run scripts/ml_backtest.py --k5 --out k5.json --tables k5.md
```

Lệnh in bảng trên và ghi JSON (`summary` theo độ dài, loại hũ, phương pháp). Đo với hiệu chỉnh hiện hành trong `calibration/default.py`,
nên nếu sinh lại bảng thì chạy sau `--write-recalibration` (đặt cả hai cờ trong một lệnh cũng được, K5 chạy sau khi ghi). `--quick` để kiểm
khói (2 seed, origin bước 28, khoảng 25 giây). Bản đầy đủ mất khoảng 5,5 phút trên máy dev (328 giây, 148.140 dòng). Kết quả tất định theo
hạt `seed × 1000 + origin`.

### Điều chưa xử lý

- Số tuyệt đối phụ thuộc lưới α của số dư kịch bản và luật "cảnh báo" (p ≥ 0,2 và có ngày cạn trước lương). Phép so với baseline thì công
  bằng vì cùng kịch bản.
- Định nghĩa "đúng" của ba/08 §3.5 còn vế "hoặc người dùng đã hành động để tránh", không đo offline được, và định nghĩa vẫn chờ chủ dự án
  duyệt (E-02).
- Chưa đo hũ nghĩa vụ (ngày cạn đi theo lịch nghĩa vụ đã biết).
- Dữ liệu tổng hợp hai họ bộ sinh; chưa có dữ liệu thật để kiểm.
