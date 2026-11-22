# Backtest phase 2: dự báo theo hũ, Monte Carlo và hiệu chỉnh (luồng ML)

Viết ngày 2026-11-22 bởi subagent làm luồng ML của phase 2 (Claude Sonnet 5.5). Mã: [ml/yofina_ml/](../../ml/README.md); chạy lại: `uv run scripts/ml_backtest.py --all`. Kết quả thô: `ml/backtest-results/phase-2.json`, `phase-2.md` (bảng) và `phase-2-statsforecast.*`. **Mọi số trong file này do script đó in ra** (lần chạy cuối ngày 2026-11-22, Python 3.13.9, numpy 2.5.5, desktop Intel i5-14600KF); mục "Suy luận" ghi rõ khi là kết luận của người viết.

> **Giới hạn lớn nhất:** toàn bộ dữ liệu là TỔNG HỢP do hai bộ sinh do dự án tự viết. Họ (i) cùng họ với mô hình hurdle nên mô hình được lợi thế nội tại; họ (ii) khác hẳn nhưng vẫn là mô phỏng. Con số ở đây chứng minh cơ chế và chuẩn đo hoạt động, KHÔNG phải độ chính xác trên dữ liệu thật. Mọi tham số hiệu chỉnh phải được đo lại khi có dữ liệu thật (batch tuần, mục "Việc còn lại").

## 0. Kết luận

| Tiêu chí (phase 2, tiêu chí 4 và mục tiêu của luồng B) | Kết quả | Đạt? |
|---|---|---|
| Hurdle có pinball thấp hơn seasonal naive trên CẢ HAI họ bộ sinh | Pinball P10/P50/P90 của chi tiêu ngày so với seasonal naive: họ (i) 0,61 (hũ dày 0,72, hũ thưa 0,56); họ (ii) 0,60 (hũ dày 0,74, hũ thưa 0,57). Sản phẩm (có ACI): 0,62 và 0,60 | Đạt |
| Độ phủ khoảng 80% của số dư (tổng chi) 30 ngày trong [0,75; 0,85] | Sau hiệu chỉnh, seed giữ ra ngoài: hũ dày 0,80 (họ (i) 0,79, họ (ii) 0,82); hũ thưa 0,80 (0,78 và 0,81). Trước hiệu chỉnh hũ dày chỉ 0,69 (0,64 và 0,76) | Đạt (xem lưu ý: sau điểm gãy hũ dày 0,75, sát cận dưới) |
| `probability_enabled` | **BẬT** (khuyến nghị): `probability_ok` đúng cho `dense` và `sparse`; sai cho `cold_start` (ước lượng ban đầu không bao giờ phát xác suất) | Quyết định ở mục 3 |
| Khởi đầu lạnh | Luật + trung bình nhóm ngang hurdle ở 21 ngày (cùng 0,66) và nhỉnh hơn dưới 21 ngày; hurdle tốt hơn từ 30 ngày. Ngưỡng `cold_start_min_days = 21` có cơ sở đo | Đạt |
| Thời gian chạy một người dùng 7 hũ x 30 ngày, lịch sử 250 ngày | `forecast_user` 61 ms (2.000 đường), 145 ms (5.000), 266 ms (10.000), trung vị 15 lần, desktop; `update_forecast` 2 hũ: 10 / 33 / 63 ms. Chưa đo trên Lambda arm64 | Đạt trên desktop, chưa đo Lambda |

**Điều cần biết trước khi tin các con số.** (1) Độ phủ đo trên các origin chồng lấn (mỗi 7 ngày, horizon 30) nên sai số lấy mẫu của một tỷ lệ độ phủ lớn hơn nhiều so với `sqrt(p(1-p)/n)` với n là số dòng; ước lượng thô (người viết, chưa tính bằng bootstrap) sai số chuẩn cỡ 0,02 cho hũ dày. (2) Độ phủ của hũ thưa theo ngày (0,91 đến 0,94) và ở 7/14 ngày (0,85 đến 0,88) cao hơn 0,80 vì phân phối rời rạc (nhiều ngày chi bằng 0 nằm đúng tại P10 và P50); không phải khoảng rộng quá. (3) Xác suất hụt của hũ dày lệch thấp so với tần suất thật 2 đến 8 điểm % (trung bình 5; mục 2.5). (4) Hiệu chỉnh trên một họ rồi đo trên họ kia vẫn nằm trong [0,75; 0,85] nhưng hũ dày ở chiều (ii) sang (i) chỉ 0,76.

## 1. Phương pháp

**Hàm được đo.** Toàn bộ số dưới đây đo chính `yofina_ml.api.forecast_user` (hurdle theo lịch + ACI + Monte Carlo + hiệu chỉnh + cổng chất lượng), dựng `ForecastInputs` từ persona tổng hợp đúng như pipeline sẽ dựng từ DB (lịch sử tới `app_date - 1`, lương chia theo tỷ lệ, nghĩa vụ mở rộng chu kỳ có khoảng số tiền). Không gọi AWS, không đọc DB. Lệnh chạy lại: `uv run scripts/ml_backtest.py --all` (kết quả thô `ml/backtest-results/phase-2.json`, bảng `ml/backtest-results/phase-2.md`).

**Hai họ bộ sinh dữ liệu** (`ml/yofina_ml/synth/`, chỉ để backtest, không phải persona demo), mỗi họ ba cấu hình persona, 330 ngày, một điểm gãy lối sống cài sẵn, 7 hũ (6 hũ chi tiêu và hũ nghĩa vụ có lịch khai kèm khoảng số tiền, ngày trả thực lệch ±1 ngày với xác suất 20%):

| Họ | Cơ chế | Cấu hình | Vì sao dùng |
|---|---|---|---|
| (i) `hurdle_lognormal` | Mỗi ngày có chi với xác suất sigmoid(cơ sở + cuối tuần + hiệu ứng ngày lương mũ + "tâm trạng" AR(1) chung), số tiền lognormal. Lấy lại từ spike | `office` (lương 9 triệu, ngày 5), `student` (4,5 triệu, ngày 1, đổi nhà trọ), `freelancer` (12 triệu, ngày 25, sau điểm gãy chi GIẢM) | Cùng họ với mô hình hurdle nên mô hình có lợi thế nội tại: dùng để kiểm cơ chế, không phải để khen |
| (ii) `shopping_sessions` | Phiên mua đến theo quá trình tái tạo (khoảng cách Gamma, dịch tới thứ ưa thích, có thể là giữa tuần), giá trị phiên là giỏ hàng (Poisson món, lognormal, món đắt đuôi nặng), ngân sách tự điều chỉnh khi gần hết tiền (tạo tương quan ÂM giữa các ngày), hiệu ứng ngày lương dạng bậc tuyến tính, du lịch nhiều ngày liên tiếp; điểm gãy: giá tăng, phiên thưa, lương tăng | `grocer_office` (ngày 5), `student_allowance` (ngày 1), `night_shift` (ngày 25, thứ ưa thích là thứ ba và thứ tư) | KHÁC HẲN họ (i): không có xác suất theo ngày, không có hiệu ứng cuối tuần cố định, phụ thuộc theo ngân sách là ÂM. Mô hình hurdle theo lịch bị sai đặc tả ở đây |

**Rolling-origin.** Mỗi persona: origin từ ngày 90, mỗi 7 ngày, horizon 30 (30 origin), fit lại từ đầu ở mỗi origin. Seed hiệu chỉnh 101 đến 104; seed ĐO 201 đến 206 (khác hẳn, giữ ra ngoài). Mỗi họ: 3 cấu hình x 6 seed = 18 persona.

**Đại lượng đo.**
- *Pinball* trung bình qua tau = 0,1 / 0,5 / 0,9 của chi tiêu NGÀY, tương đối so với seasonal naive: với mỗi (persona, hũ) lấy tổng pinball của mô hình chia tổng pinball của seasonal naive, rồi trung bình qua (persona, hũ). 1,00 bằng baseline, nhỏ hơn là tốt hơn. Baseline là `SeasonalNaiveModel` (numpy: giá trị cùng thứ của tuần trước, khoảng từ phân vị của y_t - y_{t-7}); mạnh hơn bản "native" của StatsForecast mà spike dùng nên con số tương đối không so thẳng với spike (xem mục StatsForecast).
- *Độ phủ khoảng P10-P90 theo ngày* của chi tiêu ngày.
- *Độ phủ khoảng P10-P90 của SỐ DƯ hũ* tại ngày 7, 14, 30 so với số dư thật trong sổ cái (số dư thật = số dư đầu + lương thật - nghĩa vụ thật - chi thật; vì lịch lương và nghĩa vụ tất định nên với hũ chi tiêu đây chính là độ phủ của tổng chi cộng dồn). Kèm độ rộng khoảng ngày 30 chia cho chi tiêu trung bình 28 ngày gần nhất x 30 (để thấy khoảng không "phủ đúng" bằng cách nở vô hạn).
- *Độ tin cậy của xác suất hụt trước kỳ lương* (Brier và bảng độ tin cậy): với mỗi (origin, hũ chi tiêu) và số dư kịch bản b = alpha x (chi tiêu trung bình 28 ngày x số ngày trước kỳ lương), alpha trong 0,6 / 0,8 / 1,0 / 1,25 / 1,6; kết cục thật là tổng chi thật trước kỳ lương vượt b.
- Tách theo hũ dày (tỷ lệ ngày không chi tối đa 50%) và hũ thưa, trước và sau điểm gãy (trước: cả cửa sổ 30 ngày nằm trước điểm gãy; sau: origin sau điểm gãy; cửa sổ vắt qua điểm gãy bị loại khỏi hai cột này).

**Hiệu chỉnh khoảng tổng nhiều ngày.** Spike đo độ phủ tổng 30 ngày chỉ 0,48 đến 0,61 so với 0,80 danh định ở hũ dày và quét ρ cho thấy cần ρ cỡ 0,7 đến 0,8, lớn hơn nhiều ρ lag-1 của sai số (0,05 đến 0,39). Cách xử lý ở đây:
1. Phân phối biên theo ngày giữ nguyên (đã có độ phủ theo ngày gần danh định nhờ hurdle giải tích và ACI); chỉ sửa phần PHỤ THUỘC giữa các ngày, trong Monte Carlo.
2. Hai tham số cho mỗi loại chuỗi: `rho` của copula Gaussian AR(1) (bắt tương quan ngắn hạn) và `level_sigma` của hệ số mức chung M = exp(sigma xi - sigma^2/2) nhân chi tiêu cả horizon (bắt sai lệch mức kéo dài: sai ước lượng mức, tâm trạng, điểm gãy; trung bình của M bằng 1 nên không làm lệch kỳ vọng).
3. Chọn (rho, sigma) trong lưới 9 x 11 bằng ĐỘ PHỦ của tổng chi cộng dồn tại 7/14/30 ngày (trọng số 0,2/0,3/0,5, mục tiêu 0,80) trên các seed hiệu chỉnh, không bằng tự tương quan lag-1. Mỗi ô lưới mô phỏng 1.500 đường cho từng đơn vị (origin x hũ); hòa thì chọn sigma nhỏ rồi rho nhỏ.
4. Kiểm trên seed giữ ra ngoài; bật `probability_ok` cho từng loại chuỗi chỉ khi độ phủ số dư 30 ngày nằm trong [0,75; 0,85] ở TỪNG họ bộ sinh và gộp, và xác suất hụt có Brier thấp hơn chỉ dùng tần suất chung.
5. Kiểm khả năng chuyển: hiệu chỉnh trên một họ, đo trên họ kia.

**Cổng khởi đầu lạnh.** Đo mô hình nào thắng theo độ dài lịch sử L (cắt lịch sử còn L ngày cuối, 24 cửa sổ mỗi persona, 36 persona của hai họ): hurdle theo lịch, seasonal naive, luật khởi đầu lạnh.

## 2. Kết quả

Các bảng 2.1 đến 2.5: seed giữ ra ngoài 201 đến 206, 18 persona mỗi họ, 30 origin mỗi persona, `n_paths = 2.000` (Monte Carlo).

### 2.1 Chi tiêu ngày: pinball và độ phủ theo ngày

Pinball tương đối so với seasonal naive numpy (1,00 = bằng, nhỏ hơn là tốt hơn). "hurdle thô" là bảng phân vị hurdle trước ACI, "sản phẩm" là bảng ghi ra `forecasts` (sau ACI, gamma 0,01). "Trước gãy" và "sau gãy" tính cho sản phẩm.

| Họ | Nhóm | n | pinball hurdle thô / SN | pinball sản phẩm (ACI) / SN | trước gãy | sau gãy | phủ ngày SN | phủ ngày hurdle thô | phủ ngày sản phẩm |
|---|---|---|---|---|---|---|---|---|---|
| (i) hurdle-lognormal | hũ dày | 1093 | 0,72 | 0,73 | 0,68 | 0,76 | 0,76 | 0,81 | 0,80 |
| (i) hurdle-lognormal | hũ thưa | 2147 | 0,56 | 0,57 | 0,62 | 0,55 | 0,86 | 0,93 | 0,91 |
| (i) hurdle-lognormal | mọi hũ chi tiêu | 3240 | 0,61 | 0,62 | 0,64 | 0,62 | 0,83 | 0,89 | 0,87 |
| (ii) phiên mua + giỏ hàng | hũ dày | 723 | 0,74 | 0,75 | 0,71 | 0,78 | 0,77 | 0,84 | 0,79 |
| (ii) phiên mua + giỏ hàng | hũ thưa | 2517 | 0,57 | 0,57 | 0,57 | 0,59 | 0,90 | 0,95 | 0,94 |
| (ii) phiên mua + giỏ hàng | mọi hũ chi tiêu | 3240 | 0,60 | 0,60 | 0,59 | 0,63 | 0,87 | 0,93 | 0,91 |
| gộp hai họ | hũ dày | 1816 | 0,72 | 0,74 | 0,69 | 0,77 | 0,76 | 0,82 | 0,80 |
| gộp hai họ | hũ thưa | 4664 | 0,56 | 0,57 | 0,59 | 0,57 | 0,88 | 0,94 | 0,93 |
| gộp hai họ | mọi hũ chi tiêu | 6480 | 0,61 | 0,61 | 0,62 | 0,63 | 0,85 | 0,91 | 0,89 |

Đọc:
- Hurdle thắng seasonal naive 22 đến 45% pinball ở mọi nhóm, mọi họ, cả trước lẫn sau điểm gãy. Hũ thưa được lợi nhiều hơn (0,56 so với 0,72 ở hũ dày) vì seasonal naive không biểu diễn được "phần lớn ngày bằng 0".
- Sau điểm gãy lối sống pinball xấu đi (hũ dày 0,68 lên 0,76 ở họ (i), 0,71 lên 0,78 ở họ (ii)): mô hình trễ sau điểm gãy dù đã giảm trọng số theo tuổi. Vẫn thắng baseline.
- ACI (gamma 0,01) gần như trung tính: pinball tăng 0,01 ở hũ dày; độ phủ ngày của hũ dày đi từ 0,81 và 0,84 (thô) về 0,80 và 0,79 (đích 0,80). *Suy luận:* hurdle giải tích đã gần đủ phủ theo ngày nên ACI không có nhiều việc; giá trị của ACI sẽ rõ khi có điểm gãy mạnh hoặc mô hình khác (spike §5 cũng không tách được phần "thích ứng").

### 2.2 Tổng cộng dồn: độ phủ của số dư hũ

Độ phủ khoảng P10-P90 của SỐ DƯ hũ tại ngày 7, 14, 30 (đích 0,80). Cột cuối: độ rộng khoảng ngày 30 chia cho (chi tiêu trung bình 28 ngày gần nhất x 30), chỉ có nghĩa với hũ dày (hũ thưa có chi trung bình gần 0 ở nhiều origin nên tỷ số vô nghĩa).

**Sau hiệu chỉnh (cấu hình hiện hành):**

| Họ | Nhóm | n | phủ số dư 7 ngày | phủ số dư 14 ngày | phủ số dư 30 ngày | rộng 30 ngày / chi TB |
|---|---|---|---|---|---|---|
| (i) hurdle-lognormal | hũ dày | 1093 | 0,81 | 0,81 | 0,79 | 0,87 |
| (i) hurdle-lognormal | hũ thưa | 2147 | 0,86 | 0,84 | 0,78 | 244876,98 |
| (i) hurdle-lognormal | hũ nghĩa vụ | 540 | 0,83 | 0,80 | 0,81 | - |
| (ii) phiên mua + giỏ hàng | hũ dày | 723 | 0,81 | 0,81 | 0,82 | 0,86 |
| (ii) phiên mua + giỏ hàng | hũ thưa | 2517 | 0,88 | 0,86 | 0,81 | 376086,92 |
| (ii) phiên mua + giỏ hàng | hũ nghĩa vụ | 540 | 0,80 | 0,75 | 0,70 | - |
| gộp hai họ | hũ dày | 1816 | 0,81 | 0,81 | 0,80 | 0,87 |
| gộp hai họ | hũ thưa | 4664 | 0,88 | 0,85 | 0,80 | 315686,46 |
| gộp hai họ | hũ nghĩa vụ | 1080 | 0,82 | 0,77 | 0,76 | - |

**Trước hiệu chỉnh** (copula AR(1) với rho = 0,3 cỡ tự tương quan lag-1, không hệ số mức; hũ thưa rho = 0 và không hệ số mức):

| Họ | Nhóm | n | phủ số dư 7 ngày | phủ số dư 14 ngày | phủ số dư 30 ngày | rộng 30 ngày / chi TB |
|---|---|---|---|---|---|---|
| (i) hurdle-lognormal | hũ dày | 1093 | 0,80 | 0,75 | 0,64 | 0,67 |
| (i) hurdle-lognormal | hũ thưa | 2147 | 0,86 | 0,84 | 0,78 | 244876,98 |
| (i) hurdle-lognormal | hũ nghĩa vụ | 540 | 0,83 | 0,80 | 0,81 | - |
| (ii) phiên mua + giỏ hàng | hũ dày | 723 | 0,83 | 0,80 | 0,76 | 0,73 |
| (ii) phiên mua + giỏ hàng | hũ thưa | 2517 | 0,88 | 0,86 | 0,81 | 376086,92 |
| (ii) phiên mua + giỏ hàng | hũ nghĩa vụ | 540 | 0,80 | 0,75 | 0,70 | - |
| gộp hai họ | hũ dày | 1816 | 0,81 | 0,77 | 0,69 | 0,70 |
| gộp hai họ | hũ thưa | 4664 | 0,88 | 0,85 | 0,80 | 315686,46 |
| gộp hai họ | hũ nghĩa vụ | 1080 | 0,82 | 0,77 | 0,76 | - |

Trước và sau điểm gãy, độ phủ 30 ngày (sau hiệu chỉnh, gộp hai họ): hũ dày 0,85 trước gãy và 0,75 sau gãy (trước hiệu chỉnh 0,72 và 0,65); hũ thưa 0,82 và 0,80. Khoảng hũ dày rộng thêm khoảng 24% (0,70 lên 0,87 lần chi tiêu trung bình tháng): độ phủ không đạt bằng cách nở vô hạn.

Hũ nghĩa vụ (lịch khai, khoảng số tiền, ngày trả thực lệch ±1 ngày với xác suất 20%) không thuộc cổng xác suất: độ phủ 30 ngày 0,76 gộp (0,81 ở họ (i), 0,70 ở họ (ii)). Hai nguyên nhân đã biết nhưng chưa tách riêng định lượng: mô hình coi ngày đến hạn là chính xác (không biết lệch ±1 ngày làm số dư tại các mốc 7/14/30 ngày đổi), và ở họ (ii) lương tăng sau điểm gãy (trong một lần chạy chẩn đoán riêng trên 3 seed, các cửa sổ 30 ngày vắt qua điểm gãy ở họ (ii) chỉ phủ 0,53; lần chạy chẩn đoán không nằm trong bảng chính) trong khi lịch lương dùng số lương đã nhận gần nhất.

### 2.3 Cấu hình hiệu chỉnh đã chọn

Hiệu chỉnh trên seed 101 đến 104 (hai họ gộp), lưới rho x level_sigma 9 x 11, 1.500 đường mỗi ô lưới. Ba cột cuối là độ phủ P10-P90 của tổng chi cộng dồn tại 7/14/30 ngày.

| Loại chuỗi | đơn vị (origin x hũ) | rho | level_sigma | phủ 7/14/30 ngày: rho=0, sigma=0 | rho=0,3, sigma=0 | đã chọn |
|---|---|---|---|---|---|---|
| dense | 1201 | 0,00 | 0,25 | 0,74 / 0,70 / 0,62 | 0,82 / 0,77 / 0,71 | 0,82 / 0,81 / 0,80 |
| sparse | 3119 | 0,00 | 0,00 | 0,89 / 0,87 / 0,82 | 0,89 / 0,87 / 0,82 | 0,89 / 0,87 / 0,82 |
| cold_start | 720 | 0,80 | 0,80 | 0,51 / 0,42 / 0,37 | 0,63 / 0,53 / 0,47 | 0,91 / 0,81 / 0,75 |

- **Hũ dày:** rho = 0 và level_sigma = 0,25. Tương quan ngắn hạn (rho) không giúp thêm khi đã có hệ số mức; toàn bộ phần phủ thiếu của tổng 30 ngày nằm ở sai lệch MỨC kéo dài cả horizon, đúng với suy luận của spike §3.2 (lúc đó diễn đạt bằng rho = 0,7 đến 0,8 của copula AR(1)). Hệ số mức là mô hình đúng hơn của hiện tượng này vì nó giữ chi tiêu từng ngày không âm và giữ trung bình.
- **Hũ thưa:** level_sigma = 0 đã đủ ở độ phủ 30 ngày (0,82 trên seed hiệu chỉnh, 0,80 trên seed giữ ra ngoài): bất định về xác suất có chi (Beta posterior chung cả horizon) đã cho độ phân tán cần thiết. rho không dùng (mô phỏng hurdle trực tiếp, các ngày độc lập có điều kiện).
- **Khởi đầu lạnh:** rho = 0,8 và level_sigma = 0,8 (cận của lưới): prior nhóm kém, khoảng phải rất rộng để phủ 0,75 ở 30 ngày. Không phát xác suất cho loại này nên không ảnh hưởng gate; chỉ làm đường P10-P90 rộng và nhãn luôn Thấp.

### 2.4 Chuyển hiệu chỉnh giữa hai họ

Hiệu chỉnh trên MỘT họ rồi đo độ phủ số dư 30 ngày trên họ kia (seed giữ ra ngoài 201 đến 204):

| Hiệu chỉnh trên | Đo trên | (rho, sigma) hũ dày | độ phủ hũ dày | (rho, sigma) hũ thưa | độ phủ hũ thưa |
|---|---|---|---|---|---|
| (i) hurdle-lognormal | (ii) phiên mua | (0,1; 0,25) | 0,83 | (0; 0,25) | 0,83 |
| (ii) phiên mua | (i) hurdle-lognormal | (0; 0,2) | 0,76 | (0; 0) | 0,79 |

Cả bốn ô nằm trong [0,75; 0,85] nên hiệu chỉnh chuyển được giữa hai cơ chế sinh dữ liệu khác hẳn nhau, nhưng ô hũ dày từ (ii) sang (i) sát cận dưới (0,76): hiệu chỉnh trên họ có ít tương quan dương hơn thì kém an toàn hơn. *Suy luận:* khi có dữ liệu thật phải hiệu chỉnh lại từ dữ liệu thật; bộ sinh nào cũng chỉ cho cận trên của độ tin cậy vào cấu hình này.

### 2.5 Xác suất hụt trước kỳ lương: độ tin cậy

Số dư kịch bản b = alpha x (chi tiêu trung bình 28 ngày x số ngày trước kỳ lương), alpha trong 0,6 / 0,8 / 1,0 / 1,25 / 1,6; kết cục thật = tổng chi thật trước kỳ lương vượt b. Brier thấp hơn "chỉ dùng tần suất chung" nghĩa là xác suất có kỹ năng.

Xác suất hụt, hũ dày: n = 4035, Brier = 0,161 (chỉ dùng tần suất chung: 0,250), xác suất dự báo TB = 0,428, tần suất thật = 0,480

| khoảng p dự báo | n | p dự báo TB | tần suất thật |
|---|---|---|---|
| 0.0-0.1 | 699 | 0,045 | 0,096 |
| 0.1-0.3 | 1006 | 0,193 | 0,239 |
| 0.3-0.5 | 711 | 0,399 | 0,447 |
| 0.5-0.7 | 638 | 0,598 | 0,674 |
| 0.7-0.9 | 633 | 0,801 | 0,861 |
| 0.9-1.0 | 348 | 0,947 | 0,963 |

Xác suất hụt, hũ thưa: n = 7235, Brier = 0,162 (chỉ dùng tần suất chung: 0,220), xác suất dự báo TB = 0,358, tần suất thật = 0,326

| khoảng p dự báo | n | p dự báo TB | tần suất thật |
|---|---|---|---|
| 0.0-0.1 | 895 | 0,049 | 0,049 |
| 0.1-0.3 | 2467 | 0,202 | 0,141 |
| 0.3-0.5 | 1999 | 0,393 | 0,356 |
| 0.5-0.7 | 1171 | 0,589 | 0,588 |
| 0.7-0.9 | 580 | 0,785 | 0,786 |
| 0.9-1.0 | 123 | 0,942 | 0,919 |

- Cả hai loại có kỹ năng rõ (Brier 0,161 so với 0,250 ở hũ dày; 0,162 so với 0,220 ở hũ thưa).
- **Hũ dày: xác suất dự báo thấp hơn tần suất thật ở mọi khoảng**, 2 đến 8 điểm % (trung bình dự báo 0,43 so với thật 0,48) (ví dụ dự báo 0,60, thật 0,67; dự báo 0,05, thật 0,10). *Suy luận:* nguồn chính là sai lệch mức sau điểm gãy lối sống và các khoản lớn không báo trước (khoảng 80% đã phủ đúng nhưng đuôi trên bị xem nhẹ). Không dùng cho quyết định cần độ chính xác cao hơn "một vài điểm %"; giao diện nên làm tròn (ví dụ bước 5%) và luôn kèm nhóm tin cậy. Hũ thưa gần đúng (lệch tối đa 6 điểm %, dự báo hơi cao ở khoảng 0,1 đến 0,3 và 0,3 đến 0,5).

### 2.6 Cổng khởi đầu lạnh: mô hình nào thắng theo độ dài lịch sử

Mỗi ô: pinball tương đối so với seasonal naive cùng độ dài / độ phủ ngày P10-P90. Cắt lịch sử còn L ngày cuối; 24 cửa sổ mỗi persona x 36 persona (hai họ, seed giữ ra ngoài) x 6 hũ chi tiêu.

| L (ngày lịch sử) | hurdle theo lịch | seasonal naive | luật khởi đầu lạnh |
|---|---|---|---|
| 7 | 0,70 / 0,91 | 1,00 / 0,77 | 0,67 / 0,94 |
| 14 | 0,69 / 0,92 | 1,00 / 0,79 | 0,64 / 0,94 |
| 21 | 0,66 / 0,92 | 1,00 / 0,82 | 0,66 / 0,94 |
| 30 | 0,64 / 0,91 | 1,00 / 0,83 | 0,67 / 0,94 |
| 45 | 0,63 / 0,91 | 1,00 / 0,84 | 0,67 / 0,94 |
| 60 | 0,62 / 0,91 | 1,00 / 0,85 | 0,68 / 0,94 |
| 90 | 0,61 / 0,91 | 1,00 / 0,85 | 0,67 / 0,94 |

Ở L = 7 đến 14 luật khởi đầu lạnh nhỉnh hơn (0,64 đến 0,67 so với 0,69 đến 0,70); ở L = 21 hòa (0,66); từ L = 30 hurdle tốt hơn và hơn dần (0,64 xuống 0,61). Ngưỡng `cold_start_min_days = 21` (mặc định) nằm đúng điểm hòa; seasonal naive không bao giờ thắng ở cả hai họ. Khớp spike §3.2 (hurdle thắng seasonal naive từ 21 đến 30 ngày; AutoETS không dùng được dưới 60 ngày). Độ phủ ngày của luật khởi đầu lạnh 0,94 (khoảng rộng, cố ý).

### 2.7 Ablation của hurdle

Pinball tương đối so với seasonal naive, 36 persona giữ ra ngoài, origin mỗi 14 ngày (mức bảng phân vị ngày thô, không Monte Carlo).

| Biến thể hurdle | (i) hurdle-lognormal | (ii) phiên mua + giỏ hàng | gộp hai họ |
|---|---|---|---|
| mặc định (nửa đời 180 ngày, co ô về xác suất chung kappa=20, số tiền = hệ số ô x phần dư chung) | 0,64 | 0,63 | 0,63 |
| như spike: Beta(1,2) riêng từng ô, số tiền chung, không giảm trọng số | 0,65 | 0,64 | 0,64 |
| số tiền theo lưới riêng từng ô khi đủ 15 mẫu (cách cũ) | 0,64 | 0,63 | 0,64 |
| không co ô (Beta(1,2) riêng từng ô) | 0,65 | 0,65 | 0,65 |
| nửa đời 45 ngày | 0,64 | 0,63 | 0,64 |
| nửa đời 90 ngày | 0,64 | 0,63 | 0,63 |
| không giảm trọng số theo tuổi | 0,64 | 0,63 | 0,63 |
| cửa sổ 90 ngày | 0,64 | 0,63 | 0,64 |
| không dùng lịch (xác suất và số tiền chung mọi ô) | 0,64 | 0,65 | 0,64 |

Chênh lệch giữa các biến thể nhỏ (không quá 0,02): hầu hết lợi thế đến từ hình dạng hurdle (hỗn hợp "0 hoặc số tiền" với phân phối số tiền thực nghiệm), còn phần lịch (ô cuối tuần x nửa đầu kỳ lương) chỉ đóng góp khoảng 0,01. Mặc định (co ô về xác suất chung, hồi quy số tiền theo hệ số ô, nửa đời 180 ngày) được chọn không chỉ bằng pinball mà vì kiểm LỆCH TRUNG BÌNH: trên quá trình dừng có hiệu ứng nhân theo ô, bản dùng lưới số tiền riêng cho từng ô khi đủ mẫu dự báo tổng 30 ngày thấp hơn thật 4% (8% nếu không co ô), bản hồi quy số tiền theo hệ số ô lệch khoảng 0,4% (test `test_hurdle_khong_lech_ve_tong_khi_co_hieu_ung_cuoi_tuan_va_dau_ky_luong` khóa trong ±5%). Lệch trung bình quyết định xác suất hụt, pinball thì không thấy nhiều.

### 2.8 So với StatsForecast 2.1.1

Chỉ ở mức bảng phân vị chi tiêu ngày (không Monte Carlo), 18 persona giữ ra ngoài, origin mỗi 14 ngày, khoảng native mức 80 của StatsForecast (điểm dự báo làm P50). Chạy bằng `uv run --with statsforecast==2.1.1 scripts/ml_backtest.py --statsforecast`; StatsForecast KHÔNG phải dependency của gói (không vào zip).

| Mô hình | pinball / seasonal naive (numpy) | phủ ngày P10-P90 |
|---|---|---|
| seasonal_naive (numpy, của dự án) | 1,00 | 0,85 |
| hurdle_calendar (của dự án) | 0,64 | 0,91 |
| StatsForecast SeasonalNaive (native) | 1,47 | 0,94 |
| StatsForecast AutoETS (native) | 1,02 | 0,91 |

AutoETS (season 7) ngang seasonal naive numpy (1,02) và kém hurdle nhiều (0,64); SeasonalNaive native kém hơn bản numpy của dự án 47% vì khoảng chuẩn (Gaussian) rất rộng ở dữ liệu lệch phải. Khớp spike §3 (ETS_native 0,86 so với Hurdle 0,55 so với SN conformal; baseline ở đây mạnh hơn nên tỷ số tuyệt đối khác).

### 2.9 Thời gian chạy

`forecast_user`, 7 hũ x 30 ngày, lịch sử 250 ngày (gồm fit, ACI nội bộ, Monte Carlo và dựng kết quả), trung vị và lớn nhất của 15 lần chạy nóng, một tiến trình, Python 3.13.9, numpy 2.5.5 (desktop Intel i5-14600KF):

| n_paths | `forecast_user` trung vị (ms) | lớn nhất (ms) | `update_forecast` 2 hũ (ms) |
|---:|---:|---:|---:|
| 2.000 | 62 | 70 | 10 |
| 5.000 | 145 | 151 | 32 |
| 10.000 | 266 | 286 | 63 |

Cùng bậc với spike §6 (Monte Carlo thuần 6 hũ: 76 ms ở 5.000 đường, 153 ms ở 10.000), cộng phần fit và ACI nội bộ. *Chưa đo:* vCPU Lambda arm64 (chậm hơn desktop, cần đo ở luồng pipeline), khởi động nguội (nhập `scipy`), kích thước zip. Thời gian không gồm đọc DB.


## 3. Quyết định `probability_enabled`

**Bật** (khuyến nghị), theo đúng tiêu chí đã ghi trong phase 2: độ phủ khoảng 80% của số dư 30 ngày nằm trong [0,75; 0,85] ở từng họ và gộp, cho cả hũ dày (0,79; 0,82; gộp 0,80) và hũ thưa (0,78; 0,81; gộp 0,80), và xác suất hụt có kỹ năng hơn tần suất chung. Cơ chế trong mã:

- `ml/yofina_ml/calibration/default.py` ghi `probability_ok` từng loại chuỗi (đúng cho `dense`, `sparse`; sai cho `cold_start`), do `scripts/ml_backtest.py --write-calibration` sinh theo gate trên.
- Engine chỉ phát `p_shortfall` khi `config.probability_enabled` VÀ `probability_ok` của loại chuỗi VÀ không phải ước lượng ban đầu; còn lại trả `p_shortfall = None` và chỉ có `confidence_band`. `yofina_ml.calibration.calibrated_config()` trả `ForecastConfig` có `probability_enabled` đặt theo kết quả backtest (đang `True`).
- Đổi ngưỡng gate hoặc chạy lại với dữ liệu mới: sửa `PROB_BAND` ở `backtest/cli.py` hoặc chạy lại; nếu gate sai thì hợp đồng khối tự rơi về nhóm Cao/Vừa/Thấp, không cần sửa mã khác.

Lưu ý khi bật (người điều phối quyết): sau điểm gãy lối sống hũ dày chỉ đạt 0,75 (cận dưới), xác suất hũ dày lệch thấp 2 đến 8 điểm % (mục 2.5), và mọi số đo là dữ liệu tổng hợp. Nếu muốn thận trọng hơn khi demo, đặt `probability_enabled = false` ở cấu hình pipeline: engine vẫn trả `status` đủ/sát/hụt và nhóm tin cậy, chỉ giấu con số phần trăm.

## 4. Giới hạn

1. **Dữ liệu tổng hợp.** Cả hai họ do dự án viết; chưa có dữ liệu thật. Hiệu chỉnh (`rho`, `level_sigma`, `probability_ok`) là của dữ liệu này.
2. **Sai đặc tả có chủ ý chỉ ở mức vừa phải.** Họ (ii) khác họ (i) về cơ chế nhưng cùng có tính mùa theo thứ trong tuần, lương hằng tháng và một điểm gãy lối sống; chưa thử thay đổi ngày lương, đổi nguồn thu, lương theo tuần, giao dịch từng dòng.
3. **Điểm gãy.** Mô hình trễ sau điểm gãy (pinball tăng 0,06 đến 0,08 ở hũ dày, độ phủ tổng 30 ngày hũ dày 0,75). Phát hiện điểm gãy và cắt cửa sổ lịch sử là việc của phase 4 (PELT).
4. **Không mô hình hóa:** thay đổi lương (lương tăng làm lịch lương lệch), lệch ngày đến hạn ±1 ngày của nghĩa vụ, tương quan GIỮA các hũ (mỗi hũ mô phỏng riêng, cùng seed nhưng dòng ngẫu nhiên độc lập theo hũ), khoản lớn một lần không báo trước (kéo đuôi trên của xác suất hụt hũ dày).
5. **Độ phủ của hũ thưa theo ngày và ở 7/14 ngày cao hơn 0,80** vì rời rạc; chỉ con số 30 ngày dùng để gate.
6. **Sai số lấy mẫu của chính backtest:** origin chồng lấn, nên khoảng tin cậy của các tỷ lệ độ phủ rộng cỡ ±0,02 đến ±0,04; chênh lệch dưới 0,02 giữa các biến thể (mục 2.7) không có ý nghĩa thống kê. Số đo dùng 2.000 đường mỗi lần; Monte Carlo thêm nhiễu cỡ 0,5 đến 1 điểm % vào độ phủ.
7. **ACI trung tính trên dữ liệu này** (mục 2.1): chưa chứng minh được giá trị riêng của phần thích ứng; giữ vì rẻ (vài ms) và an toàn khi hành vi đổi mạnh.
8. **Thời gian chạy đo trên desktop**, một tiến trình; Lambda arm64 và khởi động nguội chưa đo.
9. **Xác suất hụt hũ dày lệch thấp** (mục 2.5); không hiệu chỉnh riêng vì mục tiêu hiệu chỉnh là độ phủ khoảng (theo yêu cầu) và vì chỉnh thêm cho đuôi cần dữ liệu thật.

## 5. Việc còn lại (cho pipeline và phase sau)

- Pipeline đo lại độ phủ hằng tuần trên dữ liệu thật của từng người dùng (proposal §10.4: hiệu chỉnh conformal lại mỗi tuần) và đặt `probability_enabled` theo đó; ML đã có sẵn tham số hiệu chỉnh truyền được qua `ForecastConfig.extra["calibration"]`.
- Đo `forecast_user` trên Lambda arm64 (zip numpy + scipy), chọn cấu hình bộ nhớ.
- Phase 3 (what-if): giữ nguyên `config.seed` và `app_date` giữa kịch bản gốc và kịch bản để dùng chung dãy ngẫu nhiên (đã kiểm bằng test: đổi số dư dịch số dư đúng bằng chênh lệch).

## 6. Nguồn đã tra

- Gibbs, Candès (2021), *Adaptive Conformal Inference Under Distribution Shift*, arXiv:2106.00170: https://arxiv.org/abs/2106.00170 (quy tắc cập nhật alpha_t, đảm bảo độ phủ dài hạn; công thức và cận cho chuỗi ngắn đã dẫn ở [ml-forecasting.md §3.3](ml-forecasting.md)).
- Zaffran, Dieuleveut, Féron, Goude, Josse (2022), *Adaptive Conformal Predictions for Time Series*, ICML, arXiv:2202.07282: https://arxiv.org/abs/2202.07282 (ảnh hưởng của gamma; gamma nhỏ cho khoảng ổn định; trang tóm tắt không nêu kết luận số, nên gamma 0,005 đến 0,01 dựa vào số đo của spike §5 và của backtest này).
- Sun, Yu (2024), *Copula Conformal Prediction for Multi-step Time Series Forecasting*, ICLR, arXiv:2212.03281: https://arxiv.org/abs/2212.03281 (độ phủ ĐỒNG THỜI trên cả horizon bằng copula thực nghiệm; cần nhiều chuỗi để hiệu chỉnh nên KHÔNG dùng ở đây; cách làm của dự án là hiệu chỉnh tham số của copula và hệ số mức trực tiếp lên độ phủ tổng cộng dồn).
- [spike-ml-forecasting.md](spike-ml-forecasting.md) §3, §5, §6, §9 (hurdle, ACI, Monte Carlo, số đo phủ thiếu của tổng 30 ngày) và mã `spikes/ml-forecasting/`; [ml-forecasting.md](ml-forecasting.md) §3.2 đến §3.4.
- StatsForecast 2.1.1 (PyPI, bản ghim của spike): https://pypi.org/project/statsforecast/2.1.1/ (chỉ dùng để so trên máy dev).
