# Kiểm toán ML: dự báo, độ bất định và phân bổ (25/11/2026)

Ngày 25/11/2026. Người viết: sub-agent kiểm toán (Kiro), một trong chín luồng kiểm toán song song. Đọc mã và tài liệu trên đĩa (`main` lúc
865fba9). Có chạy backtest cục bộ, offline, chỉ đọc mã sản phẩm. Không gọi AWS, không deploy, không chạy eval, không sửa file nào khác ngoài ghi chú này.

Ký hiệu: [đã đọc tài liệu] là đọc file trong repo hoặc nguồn ngoài, [đã chạy thử] là số do phép thử cục bộ ở mục 9 in ra, [suy luận] là
suy ra từ hai loại trên, chưa đo.

Không lặp lại [ml-forecasting.md](ml-forecasting.md), [spike-ml-forecasting.md](spike-ml-forecasting.md) và
[backtest-phase-2.md](backtest-phase-2.md); ghi chú này chỉ thêm phần các file đó chưa có. Mức ảnh hưởng tới giám khảo dựa theo giả định
của BA: [ba/08 mục 5](../ba/08-kpi-kinh-doanh.md) (giám khảo nhìn K2, K5 và NFR độ trễ, độ đúng của số, an toàn; K5 ở mức ưu tiên Cao và
nên đưa lên slide) và [ba/10 mục 7](../ba/10-tac-dong-stakeholder.md) (mốc M0: "dự báo đúng và sớm (backtest)").

## Câu hỏi

1. Hiện đang cài những gì (hurdle, baseline, khoảng, phát hiện đổi hành vi, chuỗi gián đoạn, Monte Carlo "hũ cạn ngày X", LP)? Kỹ thuật
   nào của proposal (Chronos-2, conformal, PELT/CUSUM/ADWIN, ECOD, Croston/TSB, Monte Carlo, LP) bị bỏ hoặc làm yếu đi, và việc đó có
   được ghi lại không?
2. Khoảng bất định có thật sự được hiệu chỉnh không (khoảng 80% có phủ khoảng 80% trên backtest)? Nếu chưa, cách đúng rẻ nhất cho chuỗi
   ngắn của từng người dùng là gì?
3. Trong vài ngày, chạy CPU trong Lambda, không SageMaker, cải tiến nào nâng được độ chính xác hoặc độ hiệu chỉnh một cách đo được?
4. Trình bày cho giám khảo thế nào, bằng chứng nào còn thiếu?
5. Rủi ro đúng đắn: rò dữ liệu trong backtest, dùng sai đồng hồ mô phỏng `app_today`, làm tròn VND, bỏ qua mùa vụ theo ngày lương.

## Kết luận ngắn

Bộ kỹ thuật hiện tại đúng hướng cho một bản demo 16 ngày: hurdle tự viết thắng seasonal naive khoảng 36–40% pinball, Monte Carlo có tương
quan, xác suất hụt có kỹ năng (Brier thấp hơn tần suất chung khoảng 30% ở hũ dày), LP bằng HiGHS. Không nên thêm mô hình mới. Thiếu ba thứ,
và cả ba đều hiện ra khi giám khảo hỏi "dự báo đúng tới đâu":

1. **K5 chưa đo, và cách đo đã lên kế hoạch không đo được.** Persona demo được dựng ngược từ ngày neo nên không có "tương lai thật". Câu
   "minh cạn 23/11, trước kỳ lương 12 ngày" là khoảng cách tới kỳ lương; thực ra cảnh báo chỉ đến trước khi hũ cạn 2 ngày. Đo trên số dư kịch
   bản của bộ sinh tổng hợp (mục 3): hũ dày báo đúng ±3 ngày **0,57** (mục tiêu K5 ≥ 0,70), sai TB 3,0 ngày, trung vị báo trước 12 ngày. Hũ
   thưa báo đúng 0,28, sai TB 5,6 ngày. Seasonal naive 0,46 và burn-rate 0,47 ở hũ dày.
2. **Dải P10–P90 phủ 0,80 nhưng lệch một phía**: ở hũ dày, 30 ngày, số dư thật rơi dưới P10 16% số lần và trên P90 chỉ 4% (danh định 10/10).
   Ngày cạn lấy theo P50 nên trễ TB 1,6 ngày, và xác suất hụt hũ dày thấp hơn tần suất thật 7–9 điểm %.
3. **Ở độ dài lịch sử của demo (47 ngày), hũ thưa chỉ phủ 0,69**, dưới cổng 0,75 của chính dự án, nhưng vẫn phát %, vì `probability_ok`
   không xét độ dài lịch sử (hiệu chỉnh chỉ đo ở origin từ ngày 90).

ACI ("adaptive conformal" của proposal) có trong mã nhưng chỉ chỉnh phân vị chi tiêu theo ngày. Các phân vị đó không hiện ở đâu trên giao diện.
Dải người dùng thấy được hiệu chỉnh offline bằng lưới (rho, level_sigma) trên dữ liệu tổng hợp. Không nên nói với giám khảo là "khoảng do conformal".

## 1. Hiện trạng: proposal so với mã

| Kỹ thuật proposal (§11) | Trong mã | Trạng thái | Có ghi lại? |
|---|---|---|---|
| Chronos-2 zero-shot | Không có | Bỏ: cần torch, container khoảng 1 GB; trong spike hòa với hurdle | Có: [open-questions](../requirements/open-questions.md) đã tick, spike §4. [overview.md](../architecture/overview.md) dòng 26, 170 vẫn ghi "chưa chốt" |
| Croston/TSB cho hũ thưa | `HurdleCalendarModel` ([models.py](../../ml/yofina_ml/models.py)); hũ thưa mô phỏng hurdle trực tiếp ([montecarlo.py](../../ml/yofina_ml/montecarlo.py) `draw_paths`) | Thay thế, có số đo (spike: hurdle tốt hơn Croston/TSB 30–37% pinball) | Có (ml-forecasting §2 mục 3) [đã đọc tài liệu] |
| Baseline | `SeasonalNaiveModel` numpy; StatsForecast chỉ để so trên máy dev | Đủ | Có (backtest §2.8) |
| Adaptive conformal (Zaffran 2022) | [aci.py](../../ml/yofina_ml/aci.py): ACI theo mức phân vị, γ = 0,01, ba nhóm horizon, backtest nội bộ trên lịch sử của hũ | **Làm yếu**: `alpha` của ACI chỉ vào `_spend_quantiles` → cột `spend_p*` ([forecast.py](../../ml/yofina_ml/forecast.py) `_jar_result`). Dải số dư, `p_shortfall`, `runout_date` lấy từ Monte Carlo, không dùng `alpha`. Khối `forecast_timeline` chỉ đọc `balance_p*` (`yofina_core/blocks.py` dòng 1963–1998) | Một phần: backtest §2.1 ghi "ACI gần như trung tính". [ba/04](../ba/04-non-functional-requirements.md) NFR-11 ghi độ phủ đạt "sau ACI", sai nguồn; [requirements.md](../requirements/requirements.md) dòng 37–38 còn số spike 21/11 [đã đọc tài liệu] |
| Monte Carlo số dư | Copula Gaussian AR(1) (rho đã chọn = 0) cộng hệ số mức chung `level_sigma` = 0,25 cho hũ dày; hurdle trực tiếp cho hũ thưa; common random numbers | Đủ, đã hiệu chỉnh trên dữ liệu tổng hợp | Có |
| CUSUM online | `change.detect_suspect`, CUSUM hai phía tự viết trên z theo tuần (k = 1, h = 4) | Có. Recall 0,37 với 1,36 báo nhầm mỗi hũ-năm (tổng hợp) | Có (`change_defaults.json` mục `calibration`) |
| ADWIN | Không có | Bỏ (spike: không bắt được điểm gãy +49%) | Có |
| PELT offline | `change.detect_confirmed`, `ruptures` `l2` theo tuần, c = 6, đoạn tối thiểu 2 tuần | Có. Recall trong 8 tuần 0,24, báo nhầm 0,25 mỗi hũ-năm, trễ trung vị 21 ngày (tổng hợp). **Không đưa vào dự báo**: batch đêm chạy `change.detect_and_store` riêng ([batch.py](../../pipelines/forecast/yofina_forecast/batch.py) dòng 85), mô hình dự báo không cắt cửa sổ sau điểm gãy | Số đo có; việc không đưa vào dự báo chưa ghi rõ [đã đọc tài liệu] |
| ECOD cho khoản lớn | z bền MAD > 10 (`flag_one_offs`) | Thay thế | Có (ml/README, `change_defaults.json`) |
| LP phân bổ | [allocation.py](../../ml/yofina_ml/allocation.py): `scipy.optimize.linprog` (HiGHS), biến elastic theo ưu tiên, nới đúng một vòng | Đủ | Có |
| "Hiệu chỉnh conformal lại mỗi tuần" (§10.4) | Không có | Cắt (phase 6 Q11, bỏ batch tuần) | Có |
| Monte Carlo phía thu, thu nhập không đều | Lương tất định theo số đã khai gần nhất | Ngoài MVP | Có ([requirements.md](../requirements/requirements.md) dòng 51) |

Tham số sản phẩm đang deploy ([forecast-pipeline.ts](../../infra-cdk/lib/forecast-pipeline.ts) dòng 106–124): 10.000 đường cho batch
đêm, 5.000 cho sự kiện và what-if, `cold_start_min_days` 21, γ 0,01, ngưỡng hụt 0,5 và sát 0,2, `probabilityEnabled` true [đã đọc tài liệu].

## 2. Khoảng có được hiệu chỉnh không

### 2.1 Số đã công bố tái hiện được, nhưng chỉ ở lịch sử dài

Chạy lại `forecast_user` (mục 9, phép A) trên 36 persona giữ ra ngoài (seed 201–206, hai họ bộ sinh), origin mỗi 7 ngày từ ngày 90, 2.000
đường [đã chạy thử]:

| Lịch sử | Nhóm | n | Phủ số dư 7 / 14 / 30 ngày | Thật dưới P10 (30 ngày) | Thật trên P90 (30 ngày) | Thật dưới P50 (30 ngày) |
|---|---|---|---|---|---|---|
| Đủ (≥ 90 ngày) | hũ dày | 1816 | 0,81 / 0,81 / 0,80 | **0,160** | **0,039** | 0,600 |
| Đủ | hũ thưa | 4664 | 0,88 / 0,85 / 0,80 | 0,131 | 0,072 | 0,437 |
| Đủ | hũ nghĩa vụ | 1080 | 0,82 / 0,77 / 0,76 | 0,094 | 0,150 | 0,442 |
| Cắt còn 47 ngày (như `minh`, `lan`, `vy`) | hũ dày | 1805 | 0,80 / 0,80 / 0,79 | 0,167 | 0,043 | 0,590 |
| 47 ngày | hũ thưa | 4675 | 0,86 / 0,80 / **0,69** | 0,208 | 0,099 | 0,407 |
| Cắt còn 30 ngày | hũ dày | 1846 | 0,79 / 0,78 / 0,77 | 0,179 | 0,050 | 0,594 |
| 30 ngày | hũ thưa | 4634 | 0,83 / 0,77 / **0,62** | 0,258 | 0,123 | 0,430 |

Đọc bảng:

- Hàng "Đủ" khớp [backtest-phase-2.md §2.2](backtest-phase-2.md) (hũ dày 0,80; hũ thưa 0,80; hũ nghĩa vụ 0,76), nên khung đo tái hiện được
  dù dùng numpy 2.3.5 thay cho 2.5.5 [đã chạy thử].
- **Độ phủ hai phía đạt nhưng hai đuôi lệch**: hũ dày trượt xuống dưới P10 nhiều gấp 4 lần trượt lên trên P90. Với sản phẩm báo "hũ sắp cạn",
  đuôi dưới mới là đuôi đắt: dải đang lạc quan [đã chạy thử]. Backtest phase 2 chỉ báo độ phủ hai phía nên không thấy chỗ này.
- **Lịch sử ngắn làm hỏng hũ thưa**: ở 47 ngày, độ phủ 30 ngày còn 0,69, dưới cổng [0,75; 0,85] mà `probability_gate` (`backtest/cli.py`) dùng
  để bật xác suất. Gate chỉ chạy ở origin từ ngày 90 ([common.py](../../ml/yofina_ml/backtest/common.py) `FIRST_ORIGIN = 90`), và
  `probability_ok` không phụ thuộc độ dài lịch sử ([forecast.py](../../ml/yofina_ml/forecast.py) biến `show`). Vì vậy `minh` (47 ngày, hũ Đi lại là hũ
  thưa theo `change_defaults.json`) vẫn được phát % cho hũ thưa. Quy tắc BR-30/31 ("chỉ hiện % khi backtest đạt", [ba/10](../ba/10-tac-dong-stakeholder.md)
  dòng 54) bị vi phạm đúng ở điều kiện của demo [đã chạy thử, suy luận về hũ cụ thể].
- Khảo sát "độ dài lịch sử" của phase 2 (§2.6) chỉ đo pinball và độ phủ THEO NGÀY, không đo độ phủ số dư hay xác suất, nên không bắt được việc này
  [đã đọc tài liệu].

### 2.2 Xác suất hụt

Đo theo cách của phase 2 (số dư kịch bản b = α × chi TB 28 ngày × số ngày tới lương, kết cục là chi thật vượt b), lưới α 0,5 / 0,7 / 0,85 /
1,0 / 1,2 (mục 9, phép B) [đã chạy thử]:

| Lịch sử | Nhóm | n | Brier / tần suất chung | Bảng độ tin cậy (p dự báo TB → tần suất thật) |
|---|---|---|---|---|
| Đủ | hũ dày | 6855 | 0,162 / 0,231 | 0,06→0,15; 0,21→0,28; 0,40→0,49; 0,60→0,68; 0,80→0,87; 0,96→0,97 |
| Đủ | hũ thưa | 12370 | 0,178 / 0,240 | 0,06→0,05; 0,21→0,14; 0,40→0,34; 0,59→0,60; 0,79→0,77; 0,95→0,93 |
| 47 ngày | hũ dày | 6840 | 0,162 / 0,233 | 0,08→0,21; 0,20→0,26; 0,40→0,44; 0,60→0,66; 0,80→0,85; 0,96→0,99 |
| 47 ngày | hũ thưa | 12385 | 0,214 / 0,241 | 0,07→0,07; 0,23→0,20; 0,40→0,30; 0,59→0,47; 0,79→0,70; 0,94→0,89 |

Hũ dày dự báo thấp 7–9 điểm % ở các khoảng giữa (phase 2 đo 2–8 điểm với lưới α khác). Ở 47 ngày, hũ thưa đổi chiều sang dự báo cao 9–12 điểm
và kỹ năng gần hết (Brier 0,214 so với 0,241). Seasonal naive tệ hơn tần suất chung ở hũ thưa (Brier 0,354 so với 0,240) [đã chạy thử].

### 2.3 Cách đúng rẻ nhất cho chuỗi ngắn

- **Conformal theo từng người dùng không dùng được ở độ dài này.** Cận của ACI (Gibbs và Candès 2021, Mệnh đề 4.1): |TB err − α| ≤ (max{α₁, 1 − α₁} + γ) / (Tγ).
  Với α₁ = 0,2, γ = 0,01, T = 47 ngày, vế phải bằng 1,7, tức không bảo đảm gì; ở T = 150 ngày vẫn là 0,54 [đã đọc tài liệu]. Người dùng 47 ngày
  cũng chưa có một cửa sổ 30 ngày trọn vẹn nào để chấm. Quantile tracking hay Conformal PID (Angelopoulos và cộng sự 2023) cũng là dạng tích
  lũy sai số trực tuyến nên gặp cùng giới hạn [đã đọc tài liệu, suy luận].
- **Cách khả thi: split conformal GỘP qua nhiều người dùng**, chia ô theo (loại chuỗi × mốc horizon × nhóm độ dài lịch sử), hiệu chỉnh trên seed
  riêng và đo trên seed giữ ra ngoài. Lưới (rho, level_sigma) hiện tại đã đi theo hướng này nhưng mới nhắm độ phủ hai phía. Phiên bản đúng cho dải
  lệch là CQR bất đối xứng (Romano, Patterson, Candès 2019, Định lý 2): mỗi đuôi một hiệu chỉnh riêng ở mức 1 − α/2. Bài báo đo được khoảng
  rộng hơn bản đối xứng (1,40 lên 1,58 trên mạng nơ-ron) và vẫn giữ độ phủ [đã đọc tài liệu].
- **Xác suất hụt**: hiệu chỉnh lại bằng isotonic (PAV) trên seed hiệu chỉnh (Kuleshov và cộng sự 2018 cho hồi quy; Dimitriadis, Gneiting,
  Jordan 2021 cho sơ đồ độ tin cậy CORP dùng chính PAV). PAV chỉ khoảng 20 dòng numpy, không cần scikit-learn [đã đọc tài liệu, suy luận về số dòng].
- Phép thử CQR bất đối xứng trên dải số dư (mục 9, phép D: hiệu chỉnh trên seed 101–104 gồm lịch sử đủ, 47 và 30 ngày; điểm chuẩn hóa theo chi
  TB 28 ngày × h; đo trên seed 201–206) [đã chạy thử]:

| Lịch sử | Nhóm, mốc | Phủ trước → sau | Dưới P10 trước → sau | Trên P90 trước → sau | Độ rộng tương đối trước → sau |
|---|---|---|---|---|---|
| Đủ | hũ dày, 30 ngày | 0,806 → 0,838 | 0,155 → 0,088 | 0,039 → 0,074 | 0,81 → 0,89 (+11%) |
| Đủ | hũ dày, 7 ngày | 0,800 → 0,802 | 0,137 → 0,098 | 0,064 → 0,100 | 1,16 → 1,28 |
| 47 ngày | hũ dày, 30 ngày | 0,795 → 0,802 | 0,166 → 0,104 | 0,039 → 0,094 | 0,74 → 0,82 (+12%) |
| 30 ngày | hũ dày, 30 ngày | 0,774 → 0,788 | 0,174 → 0,108 | 0,052 → 0,104 | 0,73 → 0,82 |
| 47 ngày | hũ thưa, 30 ngày | 0,696 → 0,795 | 0,204 → 0,106 | 0,099 → 0,099 | 1,49 → 4,71 (gấp 3,2) |

Với hũ dày, CQR đưa hai đuôi về gần 10/10 và chỉ nới dải khoảng 11%. Với hũ thưa, điểm chuẩn hóa theo chi TB có đuôi rất nặng (chi TB nhỏ
và nhiễu) nên dải nở gấp 2,4 đến 3,2 lần, không dùng được. Hũ thưa cần cách khác: chạy lại lưới `level_sigma` có thêm đơn vị lịch sử ngắn, hoặc
không phát % cho hũ thưa dưới khoảng 60 ngày lịch sử [đã chạy thử, suy luận về cách sửa].

Lưu ý khi cài: nếu chỉ dời P10/P90 sau Monte Carlo thì dải và `p_shortfall` (tính từ các đường) không còn khớp nhau. Nên đọc P10/P90 ở mức
phân vị đã hiệu chỉnh ngay trên ma trận đường (`summarize_paths`), cho `p_shortfall` đi qua PAV, và lưu tham số vào `calibration/default.py`
qua `--write-calibration` như hiện nay [suy luận].

## 3. K5: báo trước khi hũ cạn

### 3.1 Vì sao kế hoạch H2 không đo được như đã viết

- Phase 6 H2 và [ba/08 §3.5](../ba/08-kpi-kinh-doanh.md) định đo K5 "trên 3 persona". [generator.py](../../data/personas/generator.py) dựng sổ
  cái NGƯỢC từ ngày neo (`start = anchor - history_days`, chia tổng theo nhóm hũ, `_simulate_non_negative`) để số dư khớp bảng Figma. Persona không
  có dữ liệu sau ngày neo, nên không có gì để so [đã đọc tài liệu].
- [ba/08 §3.5](../ba/08-kpi-kinh-doanh.md) lấy "minh được báo cạn ngày 23/11, trước kỳ lương 12 ngày" làm căn cứ cho K5. Ngày mô phỏng là 21/11,
  nên cảnh báo chỉ đến **trước khi hũ cạn 2 ngày**. "12 ngày" là khoảng từ ngày cạn tới kỳ lương, không phải lead time [đã đọc tài liệu]. Đưa câu này
  lên slide cạnh "≥ 7 ngày" sẽ tự mâu thuẫn.
- Sổ cái của bộ sinh tổng hợp cho số dư âm mãi (họ (i) không ràng buộc ngân sách). Đếm "cạn" trên số dư thật của sổ thì phần lớn sự kiện là hũ
  đã âm từ trước origin: trung vị lead time ra 1 ngày, vô nghĩa [đã chạy thử, phép A]. Vì vậy mục 3.2 dùng số dư kịch bản.

### 3.2 Đo bằng số dư kịch bản

Cách làm (mục 9, phép B; mở rộng `evaluate_shortfall` của phase 2 sang ngày cạn): ở mỗi (persona, origin, hũ chi tiêu) còn ít nhất 8 ngày tới lương,
đặt số dư b = α × chi TB 28 ngày × w, w là số ngày tới lương. Ngày cạn thật là ngày đầu chi thật cộng dồn ≥ b. Sản phẩm "cảnh báo" khi `p_shortfall` ≥ 0,2
và có ngày cạn (P50 chạm 0 trong w ngày). "Đúng" khi ngày thật cách ngày báo không quá ±3 ngày (E-02). Hai baseline: seasonal naive (cùng Monte Carlo,
`extra.model`) và burn-rate (chi TB 28 ngày × t, kiểu app nhắc hạn đơn giản) [đã chạy thử]:

| Lịch sử | Nhóm | Phương pháp | Báo đúng ±3 ngày | Báo mà không cạn trước lương | Bắt được, cạn từ ngày 7 trở đi | Sai TB (ngày) | Lead trung vị của báo đúng | Brier |
|---|---|---|---|---|---|---|---|---|
| Đủ | hũ dày (n 6855) | **sản phẩm** | **0,565** | 0,159 | 0,525 | 3,03 | 12 | 0,162 |
| Đủ | hũ dày | seasonal naive | 0,458 | 0,275 | 0,540 | 3,36 | 11 | 0,208 |
| Đủ | hũ dày | burn-rate | 0,469 | 0,274 | 0,595 | 3,25 | 12 | — |
| Đủ | hũ thưa (n 12370) | **sản phẩm** | **0,276** | 0,312 | 0,325 | 5,63 | 11 | 0,178 |
| Đủ | hũ thưa | seasonal naive | 0,201 | 0,512 | 0,340 | 5,37 | 8 | 0,354 |
| Đủ | hũ thưa | burn-rate | 0,171 | 0,569 | 0,430 | 6,31 | 11 | — |
| 47 ngày | hũ dày (n 6840) | sản phẩm | 0,546 | 0,172 | 0,526 | 3,10 | 12 | 0,162 |
| 47 ngày | hũ thưa (n 12385) | sản phẩm | 0,222 | 0,434 | 0,338 | 5,91 | 12 | 0,214 |

Đọc bảng:

- Sản phẩm hơn cả hai baseline ở độ đúng của cảnh báo (hũ dày 0,57 so với 0,46–0,47) và ở số lần báo mà hũ không cạn (16% so với 27%). Nó bắt
  được ít sự kiện hơn burn-rate (0,53 so với 0,60) vì chỉ báo khi P50 chạm 0. Giá trị của engine nằm ở xác suất có hiệu chỉnh và ít báo nhầm,
  không ở độ chính xác của ngày [đã chạy thử].
- Lead time đạt (trung vị 12 ngày ≥ 7). Độ đúng ±3 ngày chưa đạt mục tiêu 0,70, kể cả ở hũ dày. Ở hũ thưa, ngày cạn sai TB 5–6 ngày: một
  ngày cụ thể ở hũ thưa là thông tin giả chính xác [đã chạy thử, suy luận].
- Con số tuyệt đối phụ thuộc lưới α (cách chọn số dư kịch bản); phép so với baseline thì công bằng vì cùng kịch bản [suy luận].

### 3.3 Đổi quy tắc ngày cạn có giúp không

Phép C (mục 9) [đã chạy thử]: với hũ dày, dự báo TRUNG BÌNH của tổng chi w ngày gần như không lệch (thật / dự báo TB = 0,998), nhưng trung vị
thấp hơn thật 8,8% vì phân phối lệch phải (hệ số mức lognormal, số tiền lognormal). Ngày cạn theo P50 vì thế trễ TB 1,6 ngày. Lấy ngày theo đường
trung bình: báo đúng 0,565 → 0,544, bắt được 0,525 → 0,567, sai TB 3,03 → 2,95, trễ TB còn 0,7 ngày. Hệ số sửa mức gộp ước trên seed hiệu chỉnh
(0,977) không giúp. Kết luận: không đáng đổi trước cuộc thi; giữ P50 vì khớp đường người dùng thấy trên biểu đồ (lý do đã ghi ở ml/README).

## 4. Cải tiến làm được trong vài ngày (CPU, không SageMaker), xếp hạng

| # | Việc | Lợi ích dự kiến | Công | Căn cứ |
|---|---|---|---|---|
| 1 | Đưa phép B (K5 trên số dư kịch bản, kèm seasonal naive và burn-rate) vào `scripts/ml_backtest.py --k5`, viết bảng mục 3.2 vào `backtest-final.md` (H2) | Có số K5 thật cho slide, thay cho "12 ngày trước lương" | S (nửa ngày) | Mục 3 [đã chạy thử] |
| 2 | Gate xác suất theo nhóm độ dài lịch sử: chạy `probability_gate` thêm ở lịch sử 30/47/60 ngày; hũ thưa dưới ngưỡng thì `show_probability = false` (vẫn có `status` và nhãn tin cậy) | Hết vi phạm BR-31 ở demo; không đổi mô hình | S | Mục 2.1 [đã chạy thử] |
| 3 | CQR bất đối xứng gộp cho dải số dư hũ dày, theo mốc horizon, đọc trên ma trận đường | Đuôi dưới 16% → 9–10%, đuôi trên 4% → 7–9%, dải rộng thêm khoảng 11% | M (1 ngày, gồm test và chạy lại backtest) | Romano và cộng sự 2019; mục 2.3 [đã chạy thử] |
| 4 | PAV cho `p_shortfall` (theo loại chuỗi), khớp với mục 3 | Sai lệch độ tin cậy của hũ dày 7–9 điểm → dưới 3 điểm trên seed giữ ra ngoài (dự kiến) | M (0,5–1 ngày) | Kuleshov và cộng sự 2018; Dimitriadis và cộng sự 2021 [suy luận về mức lợi] |
| 5 | Làm tròn % hụt trên giao diện theo bước 5% (`formatRatioPercent` đang làm tròn 1%) | Không hứa độ chính xác mà mô hình không có (backtest §2.5 đã khuyên) | S (frontend) | [đã đọc tài liệu] |
| 6 | Hũ thưa: hiện "có thể cạn trước lương" kèm xác suất thay cho một ngày cụ thể | Bỏ con số sai TB 5–6 ngày khỏi màn hình | S–M (frontend + khối) | Mục 3.2 [đã chạy thử] |

Không nên làm trước cuộc thi:

- Cắt cửa sổ fit khi PELT xác nhận điểm gãy: trần lợi ích nhỏ (sau điểm gãy pinball hũ dày chỉ 0,68 → 0,76), PELT recall 0,24 và trễ trung vị 21 ngày
  [đã đọc tài liệu, suy luận].
- ACI, AgACI hay Conformal PID theo từng người dùng: cận lý thuyết vô nghĩa ở T = 47 (mục 2.3).
- Chronos-2, StatsForecast trong sản phẩm, Croston/TSB/iETS: các file trước đã đo và quyết định bỏ. Bài tổng quan fable.intermittent (Damato và
  cộng sự 2026) nhắc lại Croston/SBA/TSB chỉ cho dự báo điểm, không đủ cho quyết định [đã đọc tài liệu].
- Ngày cạn theo đường trung bình: mục 3.3, lợi ích không đáng kể.

## 5. Trình bày cho giám khảo

Nên có (một trang slide và một mục trong `backtest-final.md`):

1. **Bảng chính**: sản phẩm so với seasonal naive và burn-rate, chia hũ dày và hũ thưa, seed giữ ra ngoài, cả hai họ bộ sinh. Cột gồm pinball tương
   đối, độ phủ 80% kèm tách hai đuôi, kỹ năng Brier so với tần suất chung, và K5 (báo đúng ±3 ngày, báo nhầm, lead time, sai số ngày). FPP3 dùng
   seasonal naive làm mốc mặc định cho dữ liệu có mùa vụ khi tính skill score [đã đọc tài liệu].
2. **Biểu đồ độ phủ theo horizon** (7/14/30 ngày) có đường danh định, tách phần thật dưới P10 và thật trên P90, và một cột cho lịch sử 47 ngày.
3. **Sơ đồ độ tin cậy** của `p_shortfall` theo CORP (PAV) kèm dải nhất quán, thay cho bảng 6 ô cố định (Dimitriadis và cộng sự 2021).
4. **Histogram sai số ngày cạn có dấu** (dự báo trừ thật), chia theo lead time.
5. **Một ô giới hạn**: dữ liệu tổng hợp do chính nhóm viết; có phép chuyển hiệu chỉnh giữa hai họ; chưa có dữ liệu thật.

Còn thiếu trong bằng chứng hiện có: K5 (mục 3); tách hai đuôi; độ phủ và độ tin cậy ở lịch sử ngắn; nói rõ ACI không đứng sau dải người dùng thấy.

## 6. Rủi ro đúng đắn

- **Rò dữ liệu trong backtest: không thấy.** `build_inputs` ([synth/base.py](../../ml/yofina_ml/synth/base.py)) cho lịch sử `spend[:origin]` (tới
  `app_date - 1`), số dư cuối ngày origin, sự thật từ `origin + 1`. Lương khai là lần nhận gần nhất tính tới origin. Seed hiệu chỉnh (101–104) tách với
  seed đo (201–206). ACI nội bộ chỉ dùng `y[:m]`. Rò "mềm" còn lại: bộ sinh do cùng nhóm viết sau khi đã biết mô hình. Điều này đã ghi; phép chuyển giữa
  hai họ giảm bớt [đã đọc tài liệu].
- **`app_today`: đúng.** ML thuần hàm, "hôm nay" là `inputs.app_date`. Pipeline dự báo gọi `app_today(offset, now, tz)` ở `tool.py`, `afford.py`,
  `scenario.py`, `resilience.py`, `behavior.py`; không có `date.today()` [đã đọc tài liệu].
- **Làm tròn VND: đúng.** Phân vị chi ngày và số dư dùng `np.rint` rồi `int`; xác suất tính trên đường float. `p_shortfall` dùng `< 0` còn ngày cạn
  dùng P50 `<= 0`; chênh lệch không đáng kể [đã đọc tài liệu].
- **Mùa vụ theo ngày lương: có nhưng thô.** Ô lịch nhị phân "7 ngày đầu kỳ lương × cuối tuần"; ablation cho thấy phần lịch chỉ góp khoảng 0,01 pinball
  (backtest §2.7). Lương ngày nghỉ được trả sớm hoặc muộn chưa được mô hình hóa; khi đó cửa sổ `p_shortfall` lệch 1–2 ngày [suy luận].
- **Hũ nghĩa vụ** phủ 0,76 và lệch lên trên (15% thật trên P90), do ngày trả lệch ±1 và lương tăng. Nguyên nhân đã ghi ở backtest §2.2; hũ này không
  phát % nên rủi ro thấp [đã chạy thử].
- **Tương quan giữa các hũ** không mô hình hóa (mỗi hũ một dòng ngẫu nhiên). Không sai cho số liệu từng hũ; chỉ sai nếu cộng xác suất nhiều hũ [đã đọc tài liệu].

## 7. Khuyến nghị cho Yofina (thứ tự làm)

1. Trước 28/11: việc 1 và 2 của mục 4. Gate theo lịch sử có thể đổi chữ ở cảnh 1 (hũ thưa của `minh` mất %), nên đi lại cảnh 1 sau khi đổi.
2. Nếu chủ dự án đồng ý trước đợt deploy 1: việc 3 và 4 (CQR cho hũ dày, PAV). Chúng đổi % hiện ở cảnh 1 (hũ Hóa đơn "sát", p khoảng 0,2–0,35 có thể
   lên gần ngưỡng 0,5) nên phải chạy lại phép hiệu chỉnh cảnh 1 trong `data/personas/README.md`. Ngày cạn của hũ Ăn uống theo P50 không đổi. Không kịp thì
   ghi "đuôi dưới phủ thiếu" vào Giới hạn đã biết.
3. Sửa tài liệu (gộp vào I6, I2): ba/04 NFR-11 ghi đúng nguồn của độ phủ (hiệu chỉnh Monte Carlo, không phải ACI); requirements.md dòng 37–38 lấy số phase 2;
   overview.md bỏ chữ "chưa chốt" ở Chronos-2 và "StatsForecast" khỏi đường sản phẩm; ba/08 §3.5 bỏ câu "trước kỳ lương 12 ngày" làm căn cứ K5.
4. Slide: dùng bảng mục 3.2 và mục 5, nói thẳng K5 ±3 ngày chưa đạt 70% trên dữ liệu tổng hợp, kèm lý do và baseline.

## 8. Điều chưa chắc

- Mọi số là dữ liệu tổng hợp của hai họ bộ sinh tự viết; dữ liệu thật có thể khác nhiều, nhất là đuôi trên (khoản lớn không báo trước).
- Số K5 phụ thuộc lưới α của số dư kịch bản và định nghĩa "cảnh báo" (ở đây là p ≥ 0,2 và có ngày cạn, nên thực tế gần như chỉ các ca "hụt"). E-02 chưa chốt.
- Phép D hiệu chỉnh trên seed 101–104 và đo trên seed 201–206 của CÙNG hai họ; chưa thử chuyển giữa hai họ như phase 2 §2.4.
- Chưa cài và đo PAV (việc 4); mức lợi ghi ở mục 4 là dự kiến.
- Chạy bằng Anaconda Python 3.13.9, numpy 2.3.5, scipy 1.16.3, vì máy không có `uv`. Số ở lịch sử đủ khớp báo cáo phase 2 (numpy 2.5.5) tới 0,01.
- Chưa kiểm hũ nào của `minh`, `lan`, `vy` được xếp `sparse` trên Aurora lúc chạy thật. Ước theo `change_defaults.json` (mục `personas`): Đi lại của cả ba, Giải trí của `lan` và `vy`.

## 9. Đã chạy gì (để chạy lại)

Bốn script tạm ở `%TEMP%`, không commit, chỉ import `yofina_ml` (đặt `PYTHONPATH=ml`, `PYTHONIOENCODING=utf-8`, chạy `C:\anaconda3\python.exe`):

- **Phép A** (`yofina_audit_ml.py 2000 7 full,L47,L30`, khoảng 5 phút): `forecast_user` với `calibrated_config()` trên 36 persona giữ ra ngoài, origin 90..299
  bước 7; lịch sử cắt bằng `backtest.studies._truncate`. Ghi độ phủ P10–P90 của số dư tại 7/14/30 ngày, tách dưới P10, trên P90, dưới P50.
- **Phép B** (`yofina_audit_k5.py 2000 7 full` và `... 47`, khoảng 1,3 phút mỗi lần): `fit_jar` (γ = 0 vì ACI không vào Monte Carlo) + `draw_paths` +
  `balance_from_draws` với số dư 0 để lấy tổng chi cộng dồn (giống `evaluate_shortfall`). Số dư kịch bản b theo lưới α; sản phẩm, seasonal naive (`extra={"model": "seasonal_naive"}`),
  burn-rate; tính các chỉ số K5 và Brier.
- **Phép C** (`yofina_audit_bias.py`, khoảng 1 phút): như B, so ngày cạn theo trung vị, theo trung bình, và theo trung vị nhân hệ số gộp ước trên seed 101–104.
- **Phép D** (`yofina_audit_cqr.py`, khoảng 5,5 phút): CQR bất đối xứng gộp theo (loại chuỗi × mốc 7/14/30); điểm `(P10 − y)/s` và `(y − P90)/s`, s = chi TB 28 ngày × h;
  mức ⌈(n+1)(1 − 0,1)⌉/n; hiệu chỉnh trên seed 101–104 (đủ, 47, 30 ngày, origin bước 14), đo trên seed 201–206.

Muốn đưa vào repo thì chuyển phép B thành một cờ của `scripts/ml_backtest.py` (H2) và phép D thành một bước của `backtest/calibrate.py`.

## Nguồn (truy cập 2026-11-25)

- Gibbs, Candès (2021), *Adaptive Conformal Inference Under Distribution Shift*, Mệnh đề 4.1 (cận sai số độ phủ theo T và γ): https://arxiv.org/abs/2106.00170 (bản HTML: https://ar5iv.labs.arxiv.org/html/2106.00170)
- Romano, Patterson, Candès (2019), *Conformalized Quantile Regression*, NeurIPS; bản bất đối xứng hai đuôi (Định lý 2) và so độ dài khoảng ở mục 6.2: https://arxiv.org/abs/1905.03222 (HTML: https://arxiv.org/html/1905.03222)
- Angelopoulos, Candès, Tibshirani (2023), *Conformal PID Control for Time Series Prediction*, NeurIPS; quantile tracking, ACI là trường hợp riêng: https://arxiv.org/abs/2307.16895 (HTML: https://ar5iv.labs.arxiv.org/html/2307.16895)
- Zaffran, Féron, Goude, Josse, Dieuleveut (2022), *Adaptive Conformal Predictions for Time Series*, ICML: https://arxiv.org/abs/2202.07282
- Kuleshov, Fenner, Ermon (2018), *Accurate Uncertainties for Deep Learning Using Calibrated Regression*, ICML (hiệu chỉnh lại bằng isotonic): https://arxiv.org/abs/1807.00263
- Dimitriadis, Gneiting, Jordan (2021), *Stable reliability diagrams for probabilistic classifiers*, PNAS (CORP, PAV): https://www.pnas.org/doi/10.1073/pnas.2016191118
- Gneiting, Balabdaoui, Raftery (2007), *Probabilistic forecasts, calibration and sharpness*, JRSS-B 69(2) (PIT, "sắc nét với điều kiện đã hiệu chỉnh"): https://sites.stat.washington.edu/raftery/Research/PDF/Gneiting2007jrssb.pdf
- Hyndman, Athanasopoulos, *Forecasting: Principles and Practice* (3rd ed.), trang "Evaluating distributional forecast accuracy" (quantile score, Winkler, CRPS, skill score với mốc seasonal naive khi dữ liệu có mùa vụ, cross-validation theo origin trượt): https://otexts.com/fpp3/distaccuracy.html
- Damato, Zambon, Corani, Azzimonti (2026), *fable.intermittent: benchmarking probabilistic forecasting methods for intermittent time series* (phần mở đầu về Croston/SBA/TSB chỉ cho dự báo điểm): https://arxiv.org/html/2609.28607v1
- MAPIE `TimeSeriesRegressor` (EnbPI, ACI; cần estimator kiểu scikit-learn, nên không vừa mô hình tự viết, như ml-forecasting đã ghi): https://mapie.readthedocs.io/en/v1.0.1/generated/mapie.regression.TimeSeriesRegressor.html
- Mã trong repo (commit 865fba9): `ml/yofina_ml/{forecast,aci,montecarlo,models,quality,params,change,allocation}.py`, `ml/yofina_ml/calibration/default.py`, `ml/yofina_ml/backtest/*.py`,
  `ml/yofina_ml/synth/base.py`, `ml/yofina_ml/change_defaults.json`, `pipelines/forecast/yofina_forecast/{batch,inputs,settings}.py`, `infra-cdk/lib/forecast-pipeline.ts`,
  `libs/yofina_core/src/yofina_core/blocks.py`, `frontend/src/lib/format.ts`, `frontend/src/features/forecast/ForecastBlock.tsx`, `data/personas/{generator.py,README.md}`.
