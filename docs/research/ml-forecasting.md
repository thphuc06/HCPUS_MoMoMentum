# ML, thống kê và tối ưu cho Yofina Foresight

> Ghi chú nghiên cứu cho các phiên code sau. Bản gốc chỉ đọc tài liệu, không cài và không chạy thử gì. Ngày truy cập mọi nguồn: **2026-11-21**.
> **[Đã chạy thử 2026-11-21]**: một spike local trên CPU đã chạy thử phần lớn mục dự báo/thống kê/tối ưu trên dữ liệu tổng hợp; đoạn nào mang nhãn này thì số đo thay cho ước đoán, xem [spike-ml-forecasting.md](spike-ml-forecasting.md) (mã ở `spikes/ml-forecasting/`). Số đo chỉ đúng với bộ sinh dữ liệu của spike, đừng khái quát.
> Nhãn nguồn dùng trong file:
> - **[ĐÃ ĐỌC]** — đọc trực tiếp trong tài liệu chính thức, model card, PyPI/GitHub hoặc paper.
> - **[BLOG/REPO]** — blog, repo mẫu, trang bên thứ ba.
> - **[ĐỀ XUẤT]** — suy luận hoặc đề xuất của người viết, chưa có nguồn xác nhận, **chưa chạy thử**.
> - **[NỀN]** — kiến thức nền của người viết, chưa đối chiếu nguồn trong phiên này.
> Mọi đoạn code trong file là **chưa chạy thử**; đoạn nào lấy nguyên từ tài liệu thì có ghi nguồn.

## 1. Câu hỏi cần trả lời

1. Chronos-2: kích thước, đầu vào/đầu ra, covariate, phân vị, context tối thiểu, tốc độ CPU, cách cài, giấy phép, cách chạy trên AWS; có đáng vào MVP không.
2. Baseline thống kê: StatsForecast hay Darts; seasonal naive, AutoETS, Croston/TSB/ADIDA/IMAPA; khoảng dự báo; backtest; pinball loss và độ phủ 80%; chạy trong Lambda.
3. Conformal prediction cho chuỗi thời gian (ACI, AgACI): thuật toán, thư viện, hiệu chỉnh hằng tuần.
4. Monte Carlo số dư hũ: lấy mẫu đường đi có tương quan, số đường, vector hóa, dưới 0,5 giây.
5. Phát hiện đổi hành vi: PELT, CUSUM, ADWIN, nối với quy tắc "giữ 2 tuần"; ECOD cho khoản lớn.
6. Phân bổ thu nhập vào hũ bằng LP: OR-Tools, PuLP hay scipy; ràng buộc cứng/mềm; vô nghiệm.
7. Điểm chống chịu 4 thành phần theo FinHealth Score.
8. Phân loại giao dịch 3 bước: embedding tiếng Việt, pgvector, ngưỡng tin cậy, đặc trưng hành vi.
9. Hồ sơ hành vi: đặc trưng và phân cụm với dữ liệu ít.
10. Sinh dữ liệu tổng hợp cho 3 persona Việt Nam.

## 2. Kết luận ngắn

**Bộ tối thiểu cho MVP (làm trước, theo thứ tự):**

1. **Khung backtest tự viết trước mọi mô hình**: rolling-origin (mỗi 7 ngày, horizon 30 ngày), chấm bằng pinball loss ở τ = 0,1/0,5/0,9 và độ phủ khoảng 80%, chuẩn hóa so với seasonal naive. Không có khung này thì NFR "tốt hơn seasonal naive" không kiểm được.
2. **StatsForecast 2.1.1** làm thư viện thống kê chính (không dùng Darts): `SeasonalNaive(season_length=7)`, `AutoETS`, `TSB` cho hũ thưa. StatsForecast 2.1.1 không khai báo numba trong `requires_dist` [ĐÃ ĐỌC] nên bớt rủi ro cold start; vẫn nên đóng gói Lambda dạng **container image** (giới hạn 10 GB, so với 250 MB bản zip) vì kích thước thực của package chưa đo. **[Đã chạy thử 2026-11-21]** 2.1.1 cài được trên Python 3.13/Windows, không kéo numba (numba trong môi trường đầy đủ đến từ PyOD); `site-packages` đo được **332 MB** (pyarrow 87 MB bắt buộc qua `fugue`/`triad`, gỡ thì import lỗi), vượt 250 MB zip. AutoETS cho 7 chuỗi 0,25 s. Xem [spike §2](spike-ml-forecasting.md).
3. **Hũ thưa (Du lịch, Mua sắm) dùng mô phỏng "hurdle" tự viết** (xác suất có chi × phân phối lognormal/empirical của số tiền) thay vì lấy P50 từ Croston/TSB. Croston/TSB ước lượng **trung bình mỗi kỳ** chứ không phải trung vị, nên P50 và các phân vị suy ra từ chúng sai bản chất với chuỗi toàn số 0 [ĐỀ XUẤT, dựa trên mô tả TSB ở nguồn]. **[Đã chạy thử 2026-11-21, xác nhận trên dữ liệu tổng hợp]** hurdle tự viết có pinball thấp hơn Croston/TSB/ADIDA/IMAPA ~30 đến 37% trên 4 hũ thưa (tương đối so với seasonal naive: hurdle 0,50, Croston 0,73, TSB 0,79); Croston/TSB/ADIDA/IMAPA **không có khoảng native** (báo lỗi, chỉ conformal). Hurdle cùng họ với bộ sinh nên được lợi; xem [spike §3](spike-ml-forecasting.md).
4. **Conformal tự viết ~20 dòng**: ACI (Gibbs & Candès) với điểm CQR `max(q10 − y, y − q90)`, γ ≈ 0,01–0,05, gộp điểm sai số theo từng bước horizon, tính lại tập điểm hằng tuần. Không cần MAPIE (MAPIE 1.6.0 là wrapper cho estimator kiểu scikit-learn, không vừa chuỗi dự báo đã có sẵn) [ĐÃ ĐỌC + ĐỀ XUẤT]. **[Đã chạy thử 2026-11-21]** ACI tự viết chạy được: sửa ETS+conformal phủ thiếu từ 0,61 lên 0,81; γ = 0,005 đến 0,01 tốt nhất, **γ = 0,05 làm khoảng nở gấp ~5 lần** (nên γ=0,01 đến 0,05 ở trên nghiêng về cận dưới). Conformal mặc định của StatsForecast (`n_windows=2`) **phủ thiếu** (0,54 đến 0,60 cho 80% danh định). [Spike §3, §5](spike-ml-forecasting.md).
5. **Monte Carlo vector hóa bằng numpy** với **Gaussian copula AR(1)** để lấy mẫu đường đi từ phân vị theo ngày (Chronos-2 chỉ trả phân vị, không trả sample path), cộng lịch tất định, 2.000–5.000 đường. Sai số chuẩn của xác suất hụt khoảng 0,7–1,1 điểm phần trăm (tính ở §3.4). **[Đã chạy thử 2026-11-21]** vector hóa numpy 6 hũ × 30 ngày: 1.000 đường 14 ms, 5.000 đường 76 ms, 10.000 đường 160 ms (desktop i5-14600KF, dưới 0,5 s); SE đo thật khớp công thức. Độc lập đánh giá thấp xác suất hụt ở mức rủi ro 10% (5,8% so với 10% thật ở hũ ăn uống); copula chỉ đúng cho hũ dày, **sai hướng với hũ thưa**; ρ lag-1 từ PIT (0,05 đến 0,4) quá thấp để tổng 30 ngày phủ đúng (cần ρ≈0,7 đến 0,8). [Spike §6](spike-ml-forecasting.md).
6. **LP bằng `scipy.optimize.linprog` (HiGHS)** với biến slack cho ràng buộc mềm và biến "elastic" cho ràng buộc cứng để luôn có nghiệm báo được mức thiếu. **PuLP 4.3.1 yêu cầu Python ≥ 3.12 và không còn kèm CBC** [ĐÃ ĐỌC], nên không chọn PuLP. **[Đã chạy thử 2026-11-21]** cài `pulp 4.3.1` thử: `listSolvers(onlyAvailable=True)` = `[]` (không kèm solver), chỉ có `HiGHS` sau `pulp[highs]`; API đã đổi (lõi Rust, `PULP_CBC_CMD` không còn). `linprog` giải 7 hũ trong ~1 ms; elastic với một M chung phân bổ phần thiếu **tùy tiện**, cần M theo ưu tiên (spike §8).
7. **Phát hiện đổi hành vi**: PELT `ruptures` với `min_size=14` chạy đêm trên chuỗi đã chuẩn hóa tuần + CUSUM/Page-Hinkley tự viết hoặc `river.drift.PageHinkley` chạy online. **`river` không có lớp CUSUM riêng**, chỉ có `PageHinkley` mô tả là CUSUM [ĐÃ ĐỌC]. **[Đã chạy thử 2026-11-21]** xác nhận không có CUSUM trong river 0.27.0. PELT tuần (`l2`, `min_size=2`, penalty 2 đến 3×σ²·ln n) bắt đúng điểm gãy +49% nhưng cửa sổ penalty hẹp; chuỗi ngày cuộn 7 ngày với `min_size=14` cho 11 đến 18 điểm giả; **ADWIN không bắt được điểm gãy** ở mọi `clock`/delta thử (chuỗi ngày và tuần); PageHinkley báo giả nhiều. [Spike §7](spike-ml-forecasting.md).
8. **Điểm chống chịu**: dùng 4 trụ Spend/Save/Borrow/Plan nhưng **tự định nghĩa chỉ số hành vi và đặt tên riêng**. Toolkit gốc là bảng hỏi 8 câu; **dùng FinHealth Score trong phần mềm thương mại cần license từ Financial Health Network** [ĐÃ ĐỌC] — cần hỏi lại trước khi ghi tên "FinHealth Score" trong sản phẩm.
9. **Phân loại**: chuẩn hóa văn bản về không dấu + từ điển viết tắt, embedding qua Bedrock (Titan Text Embeddings V2 có Vietnamese trong danh sách ngôn ngữ nhưng "tối ưu cho tiếng Anh" [ĐÃ ĐỌC]) hoặc Cohere Embed v3 đa ngôn ngữ, kNN trong pgvector theo từng user, **hiệu chỉnh độ tin cậy bằng Platt/sigmoid** (isotonic cần > ~1000 mẫu theo scikit-learn [ĐÃ ĐỌC]). Ngưỡng 0,97 trong proposal là cosine thô của một model cụ thể, cần đặt lại bằng dữ liệu.
10. **Dữ liệu tổng hợp**: bộ sinh tự viết bằng `numpy.random.Generator` (hurdle theo hũ, hiệu ứng ngày lương và cuối tuần, cú sốc Poisson, điểm gãy cài sẵn có nhãn) + Faker `vi_VN` cho tên người. Phải lưu **nhãn sự thật** (ngày gãy, ngày sốc, nhãn hũ) để chấm PELT, ECOD, phân loại.

**Thêm nếu kịp:**

11. **Chronos-2** (`chronos-forecasting` 2.3.2, Apache-2.0, 120M tham số; có bản `chronos-2-small` 28M) với covariate ngày lương/cuối tuần/hóa đơn; chạy trong Lambda container CPU hoặc SageMaker. Bằng chứng trong paper là trên benchmark chung; **không có bằng chứng cho chuỗi chi tiêu theo ngày toàn số 0**, nên chỉ đưa vào sản phẩm nếu thắng ETS/seasonal naive trên backtest persona. **[Đã chạy thử 2026-11-21]** trên dữ liệu tổng hợp: Chronos-2 120M thắng ETS (pinball −33%, thắng 31/31 origin) và các mô hình gián đoạn, **hòa với hurdle tự viết** (tỉ lệ 1,007); CPU: 0,2 s cho 7 chuỗi, ~29 chuỗi/s theo lô, RAM đỉnh 1,2 GB, model 478 MB. Không bắt buộc cho MVP. [Spike §3, §4](spike-ml-forecasting.md).
12. AgACI (gộp nhiều γ) thay cho một γ cố định.
13. ECOD cho khoản lớn (đặc trưng đa chiều), ADWIN trên chuỗi tổng tuần.
14. Bộ phân loại nhỏ (logistic/GBM) cho chuyển khoản tên riêng trên đặc trưng hành vi.

**Điều cần chỉnh trong proposal** (chi tiết ở §4): đo chất lượng trên sản phẩm cuối (Brier của xác suất hụt, sai số ngày cạn) chứ không chỉ phân vị theo ngày; chỉ rõ FinHealth chỉ là cảm hứng/cần license; tách rõ "Chronos-2 chạy được trên CPU" (có nguồn) với "đủ nhanh cho lịch của mình" (chưa có số đo); ngưỡng 30/90 ngày chỉ là giả thuyết cần backtest.

## 3. Chi tiết theo từng mục

### 3.1 Chronos-2

**Thông tin cơ bản [ĐÃ ĐỌC]** — model card `autogluon/chronos-2` và README `amazon-science/chronos-forecasting`:
- 120M tham số, F32, Apache-2.0 (badge trong README ghi "MIT" mâu thuẫn với phần thân ghi Apache-2.0; PyPI cũng ghi Apache-2.0). Biến thể: `autogluon/chronos-2-small` 28M, `autogluon/chronos-2-synth` 120M (huấn luyện chỉ bằng dữ liệu tổng hợp).
- Encoder-only kiểu T5, xen kẽ time attention và group attention; 21 phân vị {0,01; 0,05; 0,1; …; 0,9; 0,95; 0,99}. Context tối đa 8192 (huấn luyện trước 2048, mở rộng lên 8192 ở giai đoạn sau), horizon tối đa một lần gọi 1024 (dài hơn thì unroll tự hồi quy).
- Zero-shot cho đơn biến, đa biến và có covariate. Covariate số và categorical; past-only và known-future. Categorical được mã hóa target encoding (mục tiêu đơn biến). Dự báo của covariate bị bỏ.
- Group attention: "cross-learning" cho phép chia sẻ thông tin giữa các chuỗi trong một nhóm, mặc định tắt trong `predict_df` (`cross_learning=False`); kết quả phụ thuộc `batch_size`; AutoGluon bật mặc định.
- Paper (arXiv 2510.15821): fev-bench win rate 90,7%, skill score 47,3% (SQL); GIFT-Eval WQL win rate 81,9%; Chronos Benchmark II 79,8%. Nhóm 42 tác vụ có covariate "vượt baseline với biên lớn" (số cụ thể chỉ có trong hình). **Paper không nêu context tối thiểu, không bàn dữ liệu gián đoạn, không có thời gian CPU.** Paper nói ICL giúp khi lịch sử ngắn và phần lớn tác vụ Benchmark II có dưới 300 bước trung bình.
- Tốc độ [ĐÃ ĐỌC]: ~300 chuỗi/giây trên một A10G (batch 1.024, context 2048, horizon 64); bản small nhanh "gần 2×". Model card nói hỗ trợ cả GPU và CPU nhưng **không có số CPU**. **[Đã chạy thử 2026-11-21]** số CPU đo được (i5-14600KF, torch 2.15 CPU, 14 luồng): 120M ~29 chuỗi/s theo lô (context 180, horizon 30, có covariate), small ~115 đến 124 chuỗi/s; spike §4. Median runtime trên fev-bench là 3,6 giây (Bảng 3 của paper; không rõ phần cứng).

**Cài đặt và API [ĐÃ ĐỌC]** (PyPI `chronos-forecasting` 2.3.2, phát hành 2026-09-08, Python ≥ 3.10):
- Phụ thuộc bắt buộc: `torch>=2.2,<3`, `transformers>=4.41,<6`, `accelerate>=1.1.0,<2`, `einops`, `numpy`, `pandas>=2.0`. Wheel chỉ 79 KB nhưng kéo theo PyTorch nên **không nhét vừa zip Lambda 250 MB** — dùng container image.
- Ba hàm chính trong `Chronos2Pipeline` (đọc từ `src/chronos/chronos2/pipeline.py`):
  - `predict(inputs, prediction_length, batch_size=256, context_length=None, cross_learning=False)` trả danh sách tensor `(n_variates, n_quantiles, prediction_length)`.
  - `predict_quantiles(inputs, prediction_length, quantile_levels=[0.1..0.9])` trả `(quantiles, mean)`; "mean" thực ra là median.
  - `predict_df(df, future_df=None, id_column, timestamp_column, target, prediction_length, quantile_levels, ...)` trả DataFrame dài, cột `predictions` (median) + một cột mỗi phân vị.
- Đầu vào dạng danh sách dict: `{"target": ..., "past_covariates": {...}, "future_covariates": {...}}`; mọi khóa của `future_covariates` phải có trong `past_covariates`; covariate categorical phải là NumPy array; `future_covariates` ngắn hơn horizon bị đệm NaN và **không có cảnh báo**.
- **Chỉ có phân vị, không có sample.** Code không lộ cách lấy mẫu thô. Darts `Chronos2Model` có `num_samples`, nhưng tài liệu **không nói** lấy mẫu từ phân vị thế nào và có tương quan theo thời gian không [ĐÃ ĐỌC].

Mẫu từ model card (nguyên văn rút gọn), dùng `future_df` cho covariate đã biết:

```python
from chronos import Chronos2Pipeline
pipeline = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map="cuda")  # CPU: device_map="cpu" (chưa kiểm)
pred_df = pipeline.predict_df(
    context_df,                 # cột: id, timestamp, target + covariate quá khứ
    future_df=future_df,        # cột: id, timestamp + covariate tương lai (bỏ cột target)
    prediction_length=30,
    quantile_levels=[0.1, 0.5, 0.9],
    id_column="id", timestamp_column="timestamp", target="target",
)
```
Nguồn: https://huggingface.co/autogluon/chronos-2 và https://github.com/amazon-science/chronos-forecasting. Ví dụ gốc dùng `device_map="cuda"`; dùng `"cpu"` là suy luận [ĐỀ XUẤT]. **[Đã chạy thử 2026-11-21]** `device_map="cpu"` chạy đúng; `predict_df` với `future_df` chạy được; cột đầu ra có thêm `target_name`, cột phân vị đặt tên theo chuỗi số (`"0.1"`, `"0.5"`, ...).

**Covariate cho Yofina [ĐỀ XUẤT]:** `days_since_payday` (số), `is_payday`, `is_weekend` (0/1), `dow` (categorical), `bill_due_today` (0/1 hoặc số tiền hóa đơn đến hạn trong ngày), `is_holiday_vn` (Tết, 30/4, 2/9). Tất cả đều tính được trước 30 ngày từ lịch đã khai, nên đưa vào `future_df` được. Thận trọng: nếu `future_df` thiếu hàng hoặc lệch tần suất, `predict_df` với `validate_inputs=True` sẽ kiểm; đừng đặt `validate_inputs=False`.

**Chạy trên AWS:**
- **Lambda container image, CPU** [ĐỀ XUẤT dựa trên hạn mức đã đọc]: image tối đa 10 GB, bộ nhớ tối đa 10.240 MB (1.769 MB ≈ 1 vCPU), timeout tối đa 30 phút, zip chỉ 250 MB giải nén (https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html). Trọng số F32: 120M × 4 byte ≈ 480 MB, small ≈ 112 MB (phép nhân của người viết). **[Đã chạy thử 2026-11-21]** đo thật: `model.safetensors` 478 MB và 112 MB; RSS sau khi tải 892 MB và 524 MB, đỉnh 1.193 MB và 768 MB; torch CPU thêm 518 MB vào image. Nên nướng trọng số vào image hoặc tải từ S3 lúc cold start; chưa có số cold start.
- **SageMaker qua AutoGluon-Cloud 0.5.0** [ĐÃ ĐỌC] (https://auto.gluon.ai/cloud/dev/tutorials/foundation-model-timeseries.html): `TimeSeriesFoundationModel(model_name="chronos-2")`; real-time mặc định `ml.g5.xlarge`; bảng tương đối: `ml.c6i.2xlarge` (CPU) 1× chi phí và 1× thông lượng, `ml.g4dn.xlarge` ~2× và ~5×, `ml.g5.xlarge` ~3× và ~10×. Batch dùng CPU `ml.m5.2xlarge` hoặc `ml.c6i.2xlarge`, khởi động ~4 phút. Serverless chỉ CPU, cold start ~30 giây, **không nêu giới hạn bộ nhớ**. Endpoint real-time tính tiền đến khi xóa.
- **SageMaker JumpStart** [ĐÃ ĐỌC từ model card]: `model_id="pytorch-forecasting-chronos-2"` trên `ml.g5.2xlarge`, payload JSON; `pip install -U 'sagemaker<3'`. Chưa đọc được notebook triển khai nên **chưa biết định dạng payload covariate**.
- Từ bảng tương đối của AutoGluon-Cloud có thể ngoại suy thô: nếu GPU A10G ~300 chuỗi/giây thì CPU loại c6i.2xlarge cỡ vài chục chuỗi/giây — **ngoại suy của người viết, không phải số đo** [ĐỀ XUẤT]. **[Đã chạy thử 2026-11-21]** số đo trên desktop 14 luồng thực tế ~29 chuỗi/s, tức cùng bậc với "vài chục chuỗi/s"; chưa đo trên c6i hay vCPU Lambda. Với 3 persona × 7 hũ = 21 chuỗi thì cỡ này thừa; vấn đề là cold start và đóng gói, không phải thông lượng.
- Một case study Decathlon dùng EC2 `m6i.8xlarge` (CPU) cho batch hằng tuần, không có số độ trễ [BLOG/REPO, kết quả tìm kiếm, chưa mở bài gốc].

**Có đáng vào MVP không?** Đề xuất: **không đưa vào bộ tối thiểu; làm thành thử nghiệm A/B trên backtest ở tuần 2–3.** Lý do:
- Lợi thế (zero-shot, covariate, cross-learning, ICL cho chuỗi ngắn) có thật nhưng chứng cứ là benchmark chung; chuỗi chi tiêu ngày của một hũ có nhiều số 0, nhịp lương, ít điểm — loại chuỗi mà paper không bàn.
- Chi phí kỹ thuật cao hơn hẳn: torch + container + cold start, và **chỉ có phân vị** nên vẫn phải tự lo copula cho Monte Carlo.
- Đường lui rẻ: giao diện dự báo trả về bảng phân vị (P10/P50/P90 theo ngày) nên đổi model không đụng downstream. Thiết kế `ForecastModel.predict(history, covariates) -> quantile_table` để cắm Chronos-2 sau.
- Nếu thử: dùng `chronos-2-small` (28M) trước vì nhẹ và nhanh gần gấp đôi; để `cross_learning=False` khi suy luận theo từng người để tránh trộn dữ liệu người dùng và tránh kết quả phụ thuộc batch.

### 3.2 Baseline thống kê

**StatsForecast hay Darts?** Chọn **StatsForecast**.

| Tiêu chí | StatsForecast 2.1.1 | Darts |
|---|---|---|
| Phụ thuộc [ĐÃ ĐỌC] | `numpy, pandas<3, scipy, statsmodels>=0.14.5, coreforecast, fugue, utilsforecast, cloudpickle, tqdm, threadpoolctl`; **không có numba** trong `requires_dist` của 2.1.1; Python ≥ 3.10 | Python ≥ 3.11; gói đầy đủ kèm PyTorch Lightning (trang chủ không nêu kích thước) |
| Mô hình cần | Có đủ: SeasonalNaive, AutoETS, CrostonClassic/Optimized/SBA, TSB, ADIDA, IMAPA | Có `Croston`, `AutoETS` (bọc StatsForecast), `ExponentialSmoothing`, `Chronos2Model` |
| Khoảng dự báo | Native (ETS) + conformal cho mọi model | Phân vị qua mẫu (`num_samples`) + `ConformalNaiveModel`/`ConformalQRModel` |
| Backtest | `cross_validation(h, step_size, n_windows)` | `historical_forecasts` |
| Rủi ro đóng gói | Thấp hơn | Cao hơn do PyTorch |

Nguồn: https://pypi.org/pypi/statsforecast/json , https://unit8co.github.io/darts/ . Lưu ý: nhánh `main` của repo StatsForecast ghi `requires-python >=3.11` và không liệt kê numba, khác với PyPI 2.1.1 (`>=3.10`) — **ghim đúng 2.1.1** thay vì lấy `main`. README StatsForecast không nói gì về Lambda hay Windows.

**Mô hình chuỗi gián đoạn [ĐÃ ĐỌC]:**
- Có: `ADIDA`, `CrostonClassic`, `CrostonOptimized`, `CrostonSBA`, `IMAPA`, `TSB` (README). TSB dùng `TSB(alpha_d=0.8, alpha_p=0.9)`; trang tài liệu không định nghĩa rõ hai tham số (alpha_d làm trơn kích thước, alpha_p làm trơn xác suất có cầu — suy luận [ĐỀ XUẤT]). `IMAPA()` không tham số, gộp thời gian rồi SES tối ưu và lấy trung bình.
- TSB (Teunter, Syntetos, Babai 2011, EJOR 214(3) 606–615): khác Croston ở chỗ cập nhật **xác suất có cầu mỗi kỳ** nên dự báo giảm sau chuỗi số 0, và không lệch. Nguồn: https://dx.doi.org/10.1016/j.ejor.2011.05.018 (đọc qua tóm tắt tìm kiếm).
- **Cạm bẫy:** các model này cho **một đường phẳng** (trang TSB ví dụ trả hằng số ~65,59 cho mọi giờ), nên không bắt được nhịp cuối tuần và ngày lương. Ví dụ trên tài liệu của TSB và IMAPA gọi `predict` không có `level` và kết quả không có cột khoảng, nên **không kiểm chứng được khoảng native** cho các model này; dùng conformal (§3.3). **[Đã chạy thử 2026-11-21]** đã kiểm: `forecast(level=[80])` với Croston/TSB/ADIDA/IMAPA **báo lỗi** ("instantiate the class with `prediction_intervals`"); chỉ chạy với `prediction_intervals=ConformalIntervals(...)`. SeasonalNaive và AutoETS có khoảng native.
- **Chọn model theo loại chuỗi [NỀN]:** phân loại Syntetos–Boylan theo ADI (khoảng cách trung bình giữa hai lần có cầu) và CV² của số tiền; ngưỡng thường dùng ADI ≈ 1,32, CV² ≈ 0,49 — chưa đối chiếu nguồn, kiểm lại trước khi dùng. Ở đây các hũ Ăn uống/Di chuyển gần như ngày nào cũng có chi nên dùng ETS/seasonal naive; hũ Du lịch/Mua sắm/Giải trí thưa mới cần mô hình gián đoạn.
- **Đề xuất hũ thưa (hurdle):** `P(chi>0)` ước lượng bằng tần suất làm trơn có trọng số gần đây (kiểu TSB) và **phân phối số tiền khi có chi** lấy từ lịch sử (lognormal hoặc empirical). Phân vị τ: bằng 0 nếu τ ≤ 1−p, ngược lại `F_size^{-1}((τ−(1−p))/p)`. Mô phỏng đường đi trực tiếp: mỗi ngày Bernoulli(p) × mẫu số tiền. Vừa đúng bản chất vừa dễ làm Monte Carlo [ĐỀ XUẤT].

**ETS trên chuỗi ngày toàn số dương:** `AutoETS(season_length=7)` dùng sai số Gaussian nên khoảng dưới (P10) có thể âm; cắt ở 0 sau khi tính (`np.maximum(q, 0)`). AutoETS có khoảng native khi `prediction_intervals=None` [ĐÃ ĐỌC trong mã `models.py`]. Độ dài tối thiểu để AutoETS với mùa 7 chạy ổn **chưa kiểm**; kiểm bằng backtest 30/45/60 ngày. **[Đã chạy thử 2026-11-21]** dưới ~60 ngày AutoETS(season 7) **tệ hơn seasonal naive** (pinball tương đối 6,54 / 2,25 / 1,16 / 1,02 / 0,92 ở 14 / 21 / 30 / 60 / 90 ngày; có chuỗi dự báo bùng nổ); chỉ nên dùng từ ~90 ngày. Hurdle và Chronos-2 thắng seasonal naive từ 21 đến 30 ngày. Chỉ đúng trên dữ liệu tổng hợp (spike §3.2).

**Khoảng dự báo bằng conformal có sẵn của StatsForecast** [ĐÃ ĐỌC] (https://nixtlaverse.nixtla.io/statsforecast/docs/tutorials/conformalprediction.html):

```python
from statsforecast import StatsForecast
from statsforecast.models import SeasonalNaive, AutoETS, TSB
from statsforecast.utils import ConformalIntervals

res = StatsForecast(models=[SeasonalNaive(season_length=7), AutoETS(season_length=7)], freq="D") \
    .forecast(df=train, h=30,
              prediction_intervals=ConformalIntervals(h=30, n_windows=2),
              level=[80])      # cột: <model>-lo-80, <model>-hi-80
```
- Điểm sai số là **|dự báo − thực tế|** trên các cửa sổ rolling-origin, `n_windows ≥ 2`, và **`n_windows * h` phải nhỏ hơn độ dài chuỗi** [ĐÃ ĐỌC]. **[Đã chạy thử 2026-11-21]** với `n_windows=2` khoảng 80% này **phủ chỉ 0,54 đến 0,60** trên backtest (SeasonalNaive, AutoETS, Croston/TSB/ADIDA/IMAPA), cần ACI hoặc hiệu chỉnh lại. Với h=30 và chuỗi 90 ngày chỉ được 2 cửa sổ; chuỗi 30–60 ngày không dùng được cách này → dùng h ngắn hơn khi hiệu chỉnh, hoặc gộp điểm sai số giữa các hũ cùng loại (§3.3).
- Hai biến thể: `conformal_distribution` (cộng/trừ điểm vào đường dự báo rồi lấy phân vị) và `conformal_error` (biên đối xứng bằng phân vị hữu hạn của |điểm|) [ĐÃ ĐỌC trong mã].
- `level=[80]` cho P10 và P90; P50 lấy từ cột dự báo điểm. Với ETS đó là kỳ vọng ≈ trung vị (Gaussian); với Croston/TSB đó là trung bình, không phải trung vị.

**Backtest và chỉ số:**
- `sf.cross_validation(df=df, h=30, step_size=7, n_windows=N)` trả cột `unique_id, ds, cutoff, y` + cột mỗi model [ĐÃ ĐỌC]. Trang hướng dẫn không nói gì về `refit` và `level`; xem API reference.
- Thư viện `utilsforecast.losses` [ĐÃ ĐỌC]: `mqloss(df, models, quantiles, ...)` (trung bình pinball loss qua các phân vị, xấp xỉ CRPS), `quantile_loss(df, models, q=0.5)`, `coverage(df, models, level)`, `calibration`, `scaled_crps`. `models` là dict tên model → danh sách tên cột theo từng phân vị, nên phải tự đổi tên cột `lo-80`/`hi-80` thành cột phân vị.
- **Pinball loss** (công thức của người viết [NỀN]): `L_τ(y, q) = max(τ(y − q), (τ − 1)(y − q))`; lấy trung bình τ ∈ {0,1; 0,5; 0,9}. **Skill vs seasonal naive** = `1 − PL_model / PL_snaive`; yêu cầu NFR "tốt hơn seasonal naive" ⇔ skill > 0, đo riêng từng hũ và từng độ dài lịch sử (30, 60, 90, 180, 365 ngày).
- **Độ phủ 80%** = tỉ lệ `P10 ≤ y ≤ P90` trên các điểm backtest. Cạm bẫy: ở hũ thưa mà P10 = P50 = 0 thì độ phủ theo ngày không có ý nghĩa; đo thêm trên **tổng theo tuần** và trên tổng 30 ngày [ĐỀ XUẤT].
- **Đo sản phẩm cuối** [ĐỀ XUẤT]: Brier score của xác suất "hụt trước kỳ lương", sai số ngày cạn (ngày dự báo vs ngày thực) trên backtest. Đây là thứ người dùng thấy.

**Chạy trong Lambda:**
- Hạn mức đã đọc: zip 250 MB giải nén (kể cả layers), image 10 GB, bộ nhớ ≤ 10.240 MB, timeout ≤ 30 phút (https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html).
- Kích thước thực của StatsForecast + scipy + statsmodels + pandas **chưa đo**; ước đoán của người viết là sát giới hạn zip nên dùng container image ngay từ đầu để khỏi phải tối ưu. **[Đã chạy thử 2026-11-21]** đo: 332 MB `site-packages` trên Windows (~271 MB nếu bỏ `__pycache__` và `tests`), tức **vượt** 250 MB; ước đoán đúng hướng. Kích thước wheel Linux chưa đo.
- Numba: StatsForecast 2.1.1 không khai báo [ĐÃ ĐỌC]; nhưng bản cũ (1.7.x) từng dùng numba (PyPI 1.7.x ghi "optimized with numba") và issue #753 "remove numba dependency" đã tồn tại [BLOG/REPO]. Nếu vô tình cài bản cũ sẽ dính JIT compile lúc cold start; ghim phiên bản. **[Đã chạy thử 2026-11-21]** 2.1.1 trên Python 3.13: không có numba trong môi trường và `import numba` không xảy ra; lưu ý PyOD kéo `numba` + `llvmlite` (~136 MB) vào image nếu dùng chung.

### 3.3 Conformal prediction thích ứng

**ACI gốc (Gibbs & Candès, arXiv 2106.00170) [ĐÃ ĐỌC]:**
- Cập nhật mức sai: `α_{t+1} = α_t + γ (α − err_t)`, với `err_t = 1` nếu `y_t` ra ngoài khoảng, ngược lại 0; `α` là mức sai mục tiêu (0,2 cho khoảng 80%).
- Đảm bảo không giả định về dữ liệu: `|mean(err_t) − α| ≤ (max(α_1, 1−α_1) + γ) / (γ T)`.
- Họ dùng γ = 0,005 trong thí nghiệm. Điểm CQR: `S = max{q̂(α/2) − y, y − q̂(1−α/2)}`; khoảng tại thời điểm t lấy phân vị `1 − α_t` của các điểm gần đây.
- **Hệ quả cho chuỗi ngắn** (tính từ công thức trên, của người viết): α=0,2, α_1=0,2, T=90 ngày: γ=0,01 cho biên 0,90; γ=0,05 cho biên 0,19; T=365, γ=0,05 cho 0,047. Tức đảm bảo lý thuyết **gần như vô nghĩa** với 90 ngày; phải dựa vào đo thực nghiệm trên backtest.

**Zaffran et al. 2022 (ICML, arXiv 2202.07282) [ĐÃ ĐỌC qua abstract và README repo]:**
- Phân tích ảnh hưởng của learning rate γ đến hiệu quả khoảng (độ rộng) với dữ liệu hoán đổi được và AR; mô phỏng dùng γ ∈ {0; 0,01; 0,05} (γ=0 là online split conformal).
- **AgACI**: chạy ACI với nhiều γ, rồi gộp các khoảng bằng online expert aggregation (R package OPERA: EWA, ML-Poly, BOA). Không tìm được lưới γ cụ thể; lưới nằm ở `main_acp.py` (~dòng 73) và script R trong repo https://github.com/mzaffran/AdaptiveConformalPredictionsTimeSeries . Bản AgACI Python "đang lên kế hoạch" (qua `rpy2`) — **không có sẵn Python**.
- Repo R khác: gói `AdaptiveConformal` (arXiv 2312.00448) có 5 thuật toán ACI, là gói R.

**Cài đặt có sẵn:**
| Cách | Ghi chú |
|---|---|
| StatsForecast `ConformalIntervals` | Có sẵn, offline (không phải ACI), cần `n_windows*h < len(series)` [ĐÃ ĐỌC] |
| MAPIE 1.6.0 (2026-10-19) | `TimeSeriesRegressor` (v1; v0 gọi `MapieTimeSeriesRegressor`) chỉ có hai phương pháp **EnbPI và ACI**, có `adapt_conformal_inference(X, y, gamma, ...)`, γ ∈ [0,1] [ĐÃ ĐỌC qua kết quả tìm kiếm tài liệu v1.4.1]. Là wrapper cho estimator kiểu scikit-learn, nên phải bọc StatsForecast thành estimator — mất công hơn viết tay |
| Darts `ConformalNaiveModel`/`ConformalQRModel` | Bọc model toàn cục; cần Darts [ĐÃ ĐỌC] |
| **Tự viết** | ~20 dòng numpy; khuyến nghị cho MVP |

**Đoạn mã tự viết [ĐỀ XUẤT]** — ACI cho khoảng 80% trên P10/P90, theo từng bước horizon `h`. **[Đã chạy thử 2026-11-21]** đoạn dưới được dùng gần nguyên trong `spikes/ml-forecasting/common.py` (`cqr_conformal_q`) và `s5_aci.py`; khi `α_t ≤ 0` hàm trả khoảng vô hạn nên spike kẹp bằng `2·max(scores)`, và khoảng nở rất rộng ở γ=0,05:

```python
import numpy as np

def conformal_q(scores, alpha_t):
    """Phân vị bảo thủ (n+1) của điểm sai số; kẹp khi alpha_t ra ngoài (0,1)."""
    n = len(scores)
    if n == 0 or alpha_t <= 0:
        return np.inf            # khoảng vô hạn; trong thực tế kẹp bằng max(scores)*k
    if alpha_t >= 1:
        return -np.inf           # khoảng rỗng; kẹp bằng min(scores)
    k = min(n, int(np.ceil((n + 1) * (1 - alpha_t))))
    return np.sort(scores)[k - 1]

def aci_update(alpha_t, miss, alpha=0.2, gamma=0.02):
    return alpha_t + gamma * (alpha - (1.0 if miss else 0.0))

# điểm CQR: s = max(q10 - y, y - q90) ;  khoảng: [q10 - Q, q90 + Q], rồi np.maximum(·, 0)
```
Lưu ý khi triển khai:
- Giữ **một `α_t` cho mỗi (người, hũ, bước horizon theo nhóm 1–7, 8–14, 15–30 ngày)**; cập nhật hằng ngày vào batch đêm khi biết `y` thực.
- **Gộp tập điểm sai số** giữa các hũ cùng loại hoặc giữa người dùng cùng persona, chia cho thang đo của chuỗi (ví dụ trung bình chi 28 ngày) để đủ mẫu khi người dùng mới có ít ngày [ĐỀ XUẤT]. Gibbs & Candès nhấn mạnh chuẩn hóa điểm theo dự báo điểm là quan trọng (điểm không chuẩn hóa cho độ phủ kém hơn nhiều, trong ví dụ volatility của họ) [ĐÃ ĐỌC].
- **Hiệu chỉnh lại hằng tuần** (Chủ nhật, batch tuần trong proposal): tính lại tập điểm từ backtest rolling-origin mới; giữ `α_t` làm trạng thái liên tục hoặc đặt lại về 0,2 nếu chưa đủ 4 tuần dữ liệu.
- Với số 0 nhiều, điểm sai số có nhiều giá trị trùng; vẫn dùng được nhưng độ phủ trên từng ngày dao động; đo trên tổng tuần.
- **[Đã chạy thử 2026-11-21]** trên dữ liệu tổng hợp γ = 0,005 đến 0,01 đủ và khoảng không nở quá; γ=0,05 nở gấp ~5 lần. γ=0 (split conformal, không thích ứng) đã sửa phủ thiếu 0,61 → 0,80 nên tác dụng riêng của phần "thích ứng" chưa tách được (spike §5).
- Chọn γ bằng backtest trên persona trong khoảng 0,005–0,05; nếu `α_t` lệch mạnh khỏi 0,2 là dấu hiệu model gốc hỏng, nên báo chứ đừng chỉ che bằng khoảng rộng.

### 3.4 Monte Carlo số dư hũ

**Vấn đề:** nội suy phân vị từng ngày độc lập thì tổng 30 ngày có phương sai thấp hơn thực tế khi chi tiêu các ngày có tương quan dương (ví dụ chuỗi ngày đắt liên tiếp quanh ngày lương) → xác suất hụt thấp giả tạo [ĐỀ XUẤT, suy luận toán]. Chronos-2 chỉ trả phân vị; Darts không nói rõ cách lấy mẫu [ĐÃ ĐỌC]. Với `statsmodels` ETS có `ETSResults.simulate(nsimulations, anchor, repetitions, random_errors, rng)` trả `(nsimulations, repetitions)` sample path thật từ mô hình không gian trạng thái, kể cả `random_errors="bootstrap"` [ĐÃ ĐỌC]; dùng được cho hũ thường xuyên chi nếu chịu thêm phụ thuộc statsmodels (đã có sẵn qua StatsForecast).

**Ba cách, từ rẻ đến đắt [ĐỀ XUẤT; ý tưởng copula/shuffle từ tài liệu dự báo xác suất]:**
1. **Gaussian copula AR(1) quanh phân vị theo ngày** (khuyến nghị MVP): mỗi hũ, tạo `z` chuẩn có tự tương quan `ρ` giữa các ngày, `u = Φ(z)`, rồi nghịch đảo hàm phân vị: `spend[:, h] = np.interp(u[:, h], tau_ext, q_ext[h])`. `ρ` ước lượng từ tự tương quan bậc 1 của phần dư chuẩn hóa (PIT) trên backtest (thường 0,1–0,3, cần đo). **[Đã chạy thử 2026-11-21]** ρ lag-1 từ PIT đo được 0,05 (di chuyển) đến 0,39 (ăn uống), nhưng để **tổng 30 ngày** phủ đúng 80% cần ρ≈0,7 đến 0,8 (sai số dự báo có thành phần mức kéo dài, không phải AR(1)); trong khi xác suất hụt 15 ngày khớp thật ở ρ≈0,2 đến 0,3. Không có một ρ đúng cho mọi đại lượng; chọn ρ bằng backtest cho đại lượng cần báo (spike §3.2, §6). Cần **mở rộng đuôi**: chỉ có P10/P50/P90 (ETS) hoặc 21 phân vị (Chronos-2); thêm neo `q(0)=0` (không chi âm) và đuôi trên ngoại suy kiểu mũ từ P90.
2. **Schaake shuffle**: lấy mẫu độc lập từ phân phối từng ngày rồi **sắp xếp lại thứ hạng** theo cấu trúc xếp hạng của các cửa sổ 30 ngày lịch sử của chính người dùng (Clark et al. 2004; áp dụng cho giá điện theo giờ trong Grothe, Kächele, Krüger 2022, arXiv 2204.10154 [ĐÃ ĐỌC abstract, **chưa đọc được thuật toán** vì PDF không trích text]). Giữ được cấu trúc phụ thuộc thật nhưng cần ≥ vài cửa sổ lịch sử; chuỗi < 60 ngày không đủ.
3. **Bootstrap phần dư theo khối** quanh trung vị: lấy khối phần dư 7 ngày từ lịch sử cùng loại ngày. Đơn giản, giữ được tương quan trong tuần.

Với hũ thưa dùng hurdle (§3.2) mô phỏng trực tiếp; **không** cần phân vị. **[Đã chạy thử 2026-11-21]** xác nhận hướng này: copula Gaussian qua phân vị có khối lượng ở 0 cho xác suất hụt sai hướng ở hũ thưa khi ρ lớn (mua sắm, du lịch), còn độc lập gần đúng hơn; ở hũ dày độc lập đánh giá thấp xác suất hụt 4 đến 8 điểm % tại mức 10% (spike §6).

**Cộng lịch tất định** (lương, tiền trọ, trả sau, hóa đơn): cộng trực tiếp vào mọi đường (hằng số), vì số tiền và ngày đã khai. Nếu nghĩa vụ có khoảng (hóa đơn điện 300–400k) thì lấy mẫu đều trong khoảng. Chi nhánh trả sau tự sinh từ ví mô phỏng cũng tất định.

**Ngày cạn và xác suất hụt (numpy, kích thước `(N, H)`):**

```python
rng = np.random.default_rng(seed)
e = rng.standard_normal((N, H))
z = np.empty_like(e); z[:, 0] = e[:, 0]
for h in range(1, H):                                  # H = 30, vòng ngắn
    z[:, h] = rho * z[:, h-1] + np.sqrt(1 - rho**2) * e[:, h]
u = 0.5 * (1 + scipy.special.erf(z / np.sqrt(2)))      # Φ(z)
spend = np.stack([np.interp(u[:, h], tau_ext, q_ext[h]) for h in range(H)], axis=1)
bal = bal0 + np.cumsum(inflow[None, :] - outflow_det[None, :] - spend, axis=1)   # (N, H)
broke = bal < 0
p_short_before_payday = broke[:, :H_to_payday].any(axis=1).mean()
first_zero = np.where(broke.any(1), broke.argmax(1), H)                         # ngày cạn theo đường
day_p50 = np.percentile(first_zero[broke.any(1)], 50)
```
**Số đường:** sai số chuẩn của một xác suất `p` là `sqrt(p(1−p)/N)` (tính của người viết): N=1.000 → 1,6 điểm % tại p=0,5; N=2.000 → 1,1; N=5.000 → 0,7; tại p=0,1 với N=2.000 là 0,67 điểm %. Đề xuất: **2.000 đường cho what-if tương tác; 5.000–10.000 cho batch đêm**. Dùng **seed cố định theo (user, kịch bản)** và "common random numbers" (cùng `e` cho kịch bản gốc và kịch bản what-if) để chênh lệch trước/sau không bị nhiễu mẫu — quan trọng với câu hỏi "nếu thì" và với NFR "100% số khớp tool".

**Dưới 0,5 giây:** 5.000 × 30 × 7 hũ ≈ 1 triệu phần tử số thực, các phép `interp`/`cumsum`/`erf` đều vector hóa; bậc độ lớn là vài chục mili giây trên một vCPU, nhưng **chưa đo**. **[Đã chạy thử 2026-11-21]** đo (desktop, 6 hũ × 30 ngày): N=1.000 13,6 ms; N=5.000 76 ms; N=10.000 153 đến 163 ms; một hũ N=5.000 11,7 ms. Vòng `for h` AR(1) không phải nút thắt (`lfilter` không nhanh hơn). Chưa đo trên vCPU Lambda. Cạm bẫy: vòng `for h` AR(1) và `np.interp` theo cột — nếu thành nút thắt thì dùng `scipy.signal.lfilter` cho AR(1) hoặc `np.searchsorted` theo khối. Cold start Lambda (import scipy) mới là rủi ro độ trễ, không phải phép tính. Tiền xử lý nặng (phân vị, ρ, đuôi) tính sẵn trong batch đêm; runtime chỉ nhận mảng `q_ext`, `rho` từ bảng `forecasts` và chạy phần trên.

### 3.5 Phát hiện thay đổi hành vi

**PELT trong `ruptures` 1.1.10 (2025-09-10, Python 3.9–3.13, **không hỗ trợ 3.14**) [ĐÃ ĐỌC]:**

```python
import ruptures as rpt
algo = rpt.Pelt(model="l2", min_size=14, jump=1).fit(signal)   # signal shape (n,) hoặc (n, d)
bkps = algo.predict(pen=pen)                                    # trả danh sách chỉ số kết thúc đoạn, phần tử cuối = n
```
Nguồn: https://centre-borelli.github.io/ruptures-docs/user-guide/detection/pelt/ (ví dụ gốc dùng `model="l1"`, `min_size=3`, `jump=5`, `pen=3`).
- **Cost model:** `"l2"` (dịch chuyển trung bình, nhanh hơn mô hình tuyến tính/AR đáng kể), `"l1"` (bền với ngoại lai), `"rbf"` (kernel, không tham số, chậm hơn), `"normal"` = `CostNormal` đổi cả trung bình **và hiệu phương sai** (log-định thức hiệp phương sai) [ĐÃ ĐỌC]. Với chuỗi tuần của chi tiêu: `l2` nếu chỉ quan tâm mức chi đổi; `normal` nếu quan tâm cả độ biến động đổi; `l1` nếu ngoại lai nhiều.
- **Penalty:** tài liệu `Window` ghi ví dụ `pen = np.log(n) * dim * sigma**2` và `epsilon = 3 * n * sigma**2` [ĐÃ ĐỌC] (kiểu BIC cho `l2`); trang PELT không nói cách chọn. Đề xuất: `sigma` = độ lệch chuẩn bền (MAD × 1,4826) của phần dư sau khi loại cú sốc, nhân hệ số `c ∈ [1; 3]` chỉnh bằng dữ liệu tổng hợp có nhãn điểm gãy [ĐỀ XUẤT]. **[Đã chạy thử 2026-11-21]** với σ bền ước từ sai phân bậc 1 và penalty = c·σ²·ln n trên chuỗi tuần: c=2 đến 3 bắt đúng điểm gãy (+49%) với 0 báo giả, c ≤ 1 báo 3 đến 7 điểm giả, c ≥ 5 bỏ sót; tức `c ∈ [1; 3]` đề xuất quá rộng ở cận dưới trên bộ này (spike §7).
- **Nối với quy tắc "mức mới giữ 2 tuần":** `min_size=14` trên chuỗi **ngày** nghĩa là mọi đoạn, kể cả đoạn cuối, dài ≥ 14 ngày; đoạn cuối có độ dài ≥ 14 với mức khác đoạn trước nghĩa là mức mới đã giữ ≥ 2 tuần [ĐỀ XUẤT, suy ra từ tham số đã đọc]. Trên chuỗi ngày nhiều số 0, nên chạy trên **tổng cuộn 7 ngày** (hoặc phần dư so với nhịp tuần) để khử nhịp cuối tuần; khi đó `min_size` tính theo ngày vẫn là 14 nhưng nhớ chuỗi đã tự tương quan mạnh do cửa sổ cuộn — dùng chuỗi tổng **theo tuần không chồng lấn** (`min_size=2`) cho gọn nếu có ≥ 12 tuần dữ liệu. **[Đã chạy thử 2026-11-21]** chuỗi ngày cuộn 7 ngày với `min_size=14` cho 11 đến 18 điểm gãy giả (c từ 1 đến 30), chỉ còn 3 điểm ở c=100 (1 đúng); chuỗi tuần `min_size=2` bắt đúng tháng 9. Dùng chuỗi tuần.
- Độ phức tạp trung bình ~O(CKn) [ĐÃ ĐỌC]; n ≤ 365 nên rẻ. `ruptures` là **offline**; trang `Window` không nói đến online [ĐÃ ĐỌC].

**CUSUM và ADWIN online:**
- `river.drift.ADWIN` [ĐÃ ĐỌC; docs "latest", nhiều khả năng river 0.27.x, chưa xác nhận]: `delta=0.002`, `clock=32`, `max_buckets=5`, `min_window_length=5`, `grace_period=10`; `update(x)` rồi đọc `drift_detected`, `estimation`, `width`. Với `clock=32` nó chỉ kiểm tra mỗi 32 điểm — quá thưa cho chuỗi ngày, nên đặt `clock=1` hoặc cấp dữ liệu **mỗi tuần** [ĐỀ XUẤT]. **[Đã chạy thử 2026-11-21]** ADWIN (river 0.27.0) giả định dữ liệu trong [0,1]; trên chuỗi chi tiêu dịch +49% (≈0,66σ) **không bắt được ở clock=32, 7, 1, ở delta 0,0002 đến 0,3**, cả chuỗi ngày và tuần; kiểm công cụ trên bậc thang sạch 0,2→0,5 (sd 0,1) bắt được nhưng trễ 43 điểm (clock=1) và 55 điểm (clock=32). Không dùng ADWIN cho tín hiệu này.
- `river.drift.PageHinkley` [ĐÃ ĐỌC]: `min_instances=30`, `delta=0.005`, `threshold=50.0`, `alpha=0.9999`, `mode="both"`; mô tả là "CUSUM control chart". Mô-đun `river.drift` chỉ có ADWIN, KSWIN, PageHinkley, NoDrift, DummyDriftDetector, DriftRetrainingClassifier — **không có CUSUM riêng**.
- **Khuyến nghị:** CUSUM hai phía tự viết 10 dòng trên **sai số dự báo chuẩn hóa** `z_t = (y_t − ŷ_t) / s_t` với `s_t` là thang đo bền; `S⁺_t = max(0, S⁺_{t−1} + z_t − k)`, `S⁻_t = max(0, S⁻_{t−1} − z_t − k)`, báo khi vượt `h` (k = 0,5, h ≈ 4–5 là mặc định sách giáo khoa [NỀN], chỉnh bằng ARL trên dữ liệu tổng hợp). Tự viết cho phép serialize trạng thái 2 số vào Aurora; đối tượng `river` cũng pickle được nhưng thêm phụ thuộc. **[Đã chạy thử 2026-11-21]** CUSUM tự viết trên z tuần (k=0,5/h=4): báo giả 3, trễ 1 tuần; k=1/h=4: báo giả 1, trễ 3 tuần. `PageHinkley` mặc định (threshold 50, min_instances 30) trên chuỗi ngày trễ 65 ngày; threshold 5 đến 10 báo 5 đến 7 giả; trên chuỗi tuần threshold 20 không giả, trễ 3 tuần. Ngang tự viết.
- **Sự kiện** (proposal §10.3): mỗi giao dịch mới cập nhật `z_t` của ngày đó (cộng dồn trong ngày), vào CUSUM/ADWIN; chỉ **đánh dấu "nghi"**.

**Máy trạng thái đề xuất cho "giữ 2 tuần" [ĐỀ XUẤT]:**
`BÌNH_THƯỜNG → NGHI` (CUSUM hoặc ADWIN báo, ghi `t_alarm`) → `XÁC NHẬN` khi batch đêm chạy PELT (`min_size=14`) và có điểm gãy τ trong `[t_alarm − 7, t_alarm + 7]` **và** độ lệch mức `|μ_sau − μ_trước| / σ ≥ ngưỡng` → sinh lại lộ trình (F5). Nếu sau 14 ngày PELT không xác nhận → quay về `BÌNH_THƯỜNG`. Khoản lớn một lần (ECOD hoặc z bền > ngưỡng, chỉ 1–2 ngày) **loại khỏi chuỗi** (winsorize) trước khi vào PELT/CUSUM, để một cú sốc không thành điểm gãy.

**ECOD (PyOD 3.6.8, 2026-11-12) [ĐÃ ĐỌC]:** `ECOD(contamination=0.1, n_jobs=1)`; không tham số (paper arXiv 2201.00382: dùng ECDF từng chiều và xác suất đuôi, tổng hợp thành điểm). `fit(X)` yêu cầu **mảng 2 chiều**; `decision_scores_`, `threshold_`, `labels_`; `decision_function(X_new)` hoạt động sau `fit` nhưng **ghép dữ liệu huấn luyện với dữ liệu mới rồi tính ECDF cho cả hai**, nên điểm của mẫu mới phụ thuộc tập tham chiếu và mỗi lần gọi tính lại (chậm dần theo lịch sử, nhưng dữ liệu một người nhỏ nên chấp nhận được).
- Đặc trưng đề xuất cho khoản lớn [ĐỀ XUẤT]: `log(số tiền)`, `số tiền / trung vị chi 90 ngày của hũ`, giờ trong ngày, ngày so với ngày lương, `là người nhận mới`. Dùng đa chiều có nghĩa; chỉ một chiều số tiền thì z bền (MAD) là đủ và dễ giải thích.
- `contamination` mặc định 0,1 quá cao cho "khoản bất thường"; đặt 0,01–0,02 và/hoặc lấy ngưỡng theo phân vị điểm [ĐỀ XUẤT]. **[Đã chạy thử 2026-11-21]** ECOD xếp 3 khoản lớn có nhãn ở hạng 1, 2, 3 trên 857 hũ-ngày (recall 100%), nhưng với `contamination` 0,10 / 0,02 / 0,01 gắn cờ 86 / 18 / 9 (precision 0,03 / 0,17 / 0,33); ECOD đối xứng nên cờ cả khoản rất nhỏ. z bền MAD > 10 trên số tiền theo hũ đạt 8 cờ (5 sai), ngang ECOD ở 0,01. PyOD kéo `numba`+`llvmlite`+sklearn, import 2,2 s (spike §7).

### 3.6 Phân bổ thu nhập vào hũ (LP)

**So sánh:**
| | `scipy.optimize.linprog` | OR-Tools | PuLP |
|---|---|---|---|
| Phiên bản đã đọc | SciPy docs v1.18.0 | 9.15.6755 (2026-01-14), Python ≥ 3.9, wheel 22–30 MB | 4.3.1 (2026-11-19), **Python ≥ 3.12**, **không kèm CBC**, cần `pulp[highs]` hoặc `pulp[cbc]` |
| Solver | HiGHS (`method="highs"`); `integrality` cho MILP | GLOP (LP), SCIP/CP-SAT (nguyên) | CBC/HiGHS ngoài |
| Ưu | Đã có scipy; không thêm phụ thuộc; mã trạng thái `status` rõ (0 tối ưu, 2 vô nghiệm, 3 không chặn) | API mô hình dễ đọc (`solver.Add(...)`); MILP/CP khi cần chia nguyên theo bậc 10.000đ | Cú pháp mô hình gọn |
| Nhược | Phải tự dựng ma trận | Thêm ~30 MB vào image | Ràng buộc Python 3.12 và solver ngoài, rắc rối cho Lambda |
Nguồn: https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linprog.html , https://pypi.org/project/ortools/ , https://pypi.org/project/PuLP/ , ví dụ OR-Tools https://developers.google.com/optimization/lp/lp_example (dùng `pywraplp.Solver.CreateSolver("GLOP")`, kiểm `status == pywraplp.Solver.OPTIMAL`).

**Khuyến nghị: `scipy.optimize.linprog` (HiGHS)** cho MVP — bài toán chỉ vài chục biến. Cần làm tròn đến nghìn đồng thì làm tròn sau, hoặc dùng `integrality`.

**Mẫu mô hình [ĐỀ XUẤT; mô hình đã chạy thử 2026-11-21 trong `spikes/ml-forecasting/s8_lp.py`, đoạn code bên dưới là bản gốc chưa chạy nguyên văn]:** biến `x_j` (tiền vào hũ j), `s_j` (thiếu mục tiêu mềm), `e_j` (thiếu nghĩa vụ cứng, "elastic").
- Cứng: `Σ x_j = I` (thu nhập kỳ); `x_j + e_j ≥ L_j` cho hũ nghĩa vụ/tiền trọ (L = số đã khai); `x_j ≥ floor_j` cho thiết yếu (từ P50 chi dự báo).
- Mềm: `x_j + s_j ≥ T_j` (nhu cầu đóng góp mục tiêu `T = (đích − hiện có) / số kỳ còn lại`), `s_j ≥ 0`.
- Mục tiêu: `min  M·Σ e_j + Σ w_j s_j + ε·Σ|x_j − x_prev_j|` với `M ≫ w` (nghĩa vụ trước mục tiêu), `w_j` theo ưu tiên (dự phòng > mục tiêu > giải trí) và `|·|` tuyến tính hóa bằng hai biến phụ để lộ trình ổn định giữa các phiên bản.

```python
import numpy as np
from scipy.optimize import linprog

def allocate(I, L, floor, T, w, M=1e6):
    n = len(L)                                    # biến: x(n), s(n), e(n)
    c = np.r_[np.zeros(n), w, np.full(n, M)]
    A_eq = np.r_[np.ones(n), np.zeros(n), np.zeros(n)][None, :]; b_eq = [I]
    A_ub, b_ub = [], []
    for j in range(n):
        r = np.zeros(3*n); r[j] = -1; r[2*n+j] = -1; A_ub.append(r); b_ub.append(-L[j])   # x+e >= L
        r = np.zeros(3*n); r[j] = -1; r[n+j] = -1;   A_ub.append(r); b_ub.append(-T[j])   # x+s >= T
    bounds = [(floor[j], None) for j in range(n)] + [(0, None)]*(2*n)
    res = linprog(c, A_ub=np.array(A_ub), b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    return res.status, res.x[:n], res.x[n:2*n], res.x[2*n:]
```
**Cạm bẫy:** `bounds` với `floor_j` đẩy tổng sàn vượt `I` thì `linprog` trả `status=2` (vô nghiệm) trước cả khi có `e` **[Đã chạy thử 2026-11-21: xác nhận, I=5.500 so với sàn 6.430 → status 2 không kèm mức thiếu]**; để biến `e` phát huy tác dụng phải đặt sàn cứng của nghĩa vụ **qua `x+e ≥ L`**, không qua `bounds`. Với thiết yếu không phải nghĩa vụ cũng làm tương tự (thêm biến elastic).
**Xử lý vô nghiệm như proposal §10.5:** (1) có nghiệm với `e = 0` và `s` lớn → mục tiêu chưa khả thi: nới mềm một lần bằng cách tăng kỳ hạn (`T_j` giảm) hoặc hạ sàn hũ không thiết yếu rồi giải lại; (2) vẫn `s > 0` → báo "mục tiêu chưa khả thi" kèm 2 lựa chọn và số tiền thiếu `Σ s_j`; (3) `e > 0` → thu nhập không đủ nghĩa vụ: báo mức thiếu `Σ e_j` (đây là thông tin có giá trị, không phải lỗi). Luôn kiểm `res.status` trước khi đọc `res.x` [ĐÃ ĐỌC]. **[Đã chạy thử 2026-11-21]** thêm hai điều đo được: (a) dùng cùng một `M` cho mọi biến elastic thì phần thiếu rơi **tùy tiện** (thử: rơi hết vào tiền trọ/nghĩa vụ trong khi ăn uống vẫn đủ) → đặt `M` theo ưu tiên (nghĩa vụ ≫ thiết yếu ≫ khác); (b) trọng số `w` hòa cho nghiệm không duy nhất (giải trí hay mua sắm bị cắt tùy cấu hình/solver) → dùng trọng số khác nhau. Thời gian giải ~1 ms.

### 3.7 Điểm chống chịu 4 thành phần (FinHealth)

**Khung gốc [ĐÃ ĐỌC]** — FinHealth Score Toolkit 2021 (https://finhealthnetwork.org/wp-content/uploads/2021/11/FinHealthScoreToolkit-2021.pdf, trang 3–8): **8 câu hỏi khảo sát**, mỗi câu quy ra 0–100 điểm; điểm thành phần = **trung bình của 2 câu**; điểm tổng = trung bình 8 câu. Ngưỡng: 0–39 Vulnerable, 40–79 Coping, 80–100 Healthy.

| Trụ | Câu | Đo gì (câu hỏi gốc) | Bậc điểm |
|---|---|---|---|
| Spend | 1 | Tổng chi so với tổng thu 12 tháng qua | much less 100 / a little less 75 / about equal 50 / a little more 25 / much more 0 |
| Spend | 2 | Trả hóa đơn đúng hạn 12 tháng qua | all 100 / nearly all 60 / most 40 / some 20 / very few 0 |
| Save | 3 | Sống được bao lâu chỉ bằng tiền sẵn có, không rút hưu trí và không vay | ≥ 6 tháng 100 / 3–5 tháng 75 / 1–2 tháng 50 / 1–3 tuần 25 / < 1 tuần 0 |
| Save | 4 | Tự tin mức nào là đang làm đủ cho mục tiêu dài hạn | very 100 / moderately 75 / somewhat 50 / slightly 25 / not at all 0 |
| Borrow | 5 | Nợ có quản lý được không | không nợ 100 / quản lý được 85 / hơi quá sức 40 / quá sức nhiều 0 |
| Borrow | 6 | Tự đánh giá điểm tín dụng | excellent 100 / very good 80 / good 60 / fair 40 / poor 0 / không biết 0 |
| Plan | 7 | Tự tin bảo hiểm đủ hỗ trợ khi khẩn cấp | very 100 / moderately 75 / somewhat 50 / slightly 25 / not at all 10 / không ai có bảo hiểm 0 |
| Plan | 8 | "Gia đình tôi có kế hoạch tài chính trước" | agree strongly 100 / somewhat 65 / neutral 35 / disagree somewhat 15 / strongly 0 |

Tên trụ thứ tư: toolkit ghi **Plan**, trang web ghi "Plan and Protect" (https://finhealthnetwork.org/score/). Toolkit **không cho ngưỡng số** (ví dụ "bao nhiêu % thu là nợ thì quản lý được"): đó là tự báo cáo. Ngưỡng định lượng phải tự đặt.

**Giấy phép [ĐÃ ĐỌC, một phần]:** Toolkit miễn phí cho nghiên cứu, vận động và nội bộ; **dùng Score trong phần mềm và thương mại cần license qua Attune, gia hạn hằng năm** (kết quả tìm kiếm trích trang chính thức); thỏa thuận 2026 yêu cầu ghi nhận "This [product] leverages the Financial Health Network's FinHealth Score®", cấm ghi nhãn gây hiểu lầm là được chứng thực, và Financial Health Network sở hữu câu hỏi và công thức chấm (https://finhealthnetwork.org/finhealth-score-license-agreement/ — **chưa đọc được Exhibit A và mục về chỉ số phái sinh**). → Điểm của Yofina là chỉ số **tính từ hành vi**, khác bản chất bảng hỏi; nên đặt tên là "Điểm chống chịu" với chú thích "lấy cảm hứng từ bốn trụ của khung FinHealth", không nêu là FinHealth Score, và **xác nhận lại với đội/giám khảo/pháp lý** nếu muốn dùng tên.

**Chuyển sang chỉ số hành vi [ĐỀ XUẤT]** — mỗi chỉ số quy về 0–100 theo cùng bậc điểm với câu gốc rồi nội suy tuyến tính giữa các bậc; ngưỡng là giả thuyết, chỉnh trên 3 persona:
| Trụ | Chỉ số hành vi (từ sổ cái, dự báo) | Gợi ý ánh xạ |
|---|---|---|
| Spend 1 | `chi/thu` trung bình 90 ngày (tách chi thiết yếu) | ≤ 0,7 → 100; 0,9 → 75; 1,0 → 50; 1,1 → 25; ≥ 1,25 → 0 |
| Spend 2 | Tỉ lệ nghĩa vụ trả **trước hoặc đúng hạn** (trả sau, vay, trọ, hóa đơn) 90 ngày | 100% → 100; ≥ 95% → 60; ≥ 85% → 40; ≥ 70% → 20; còn lại 0 (bậc lấy từ câu gốc) |
| Save 3 | **Runway** = (số dư các hũ thanh khoản) / (chi thiết yếu trung bình ngày) quy ra tháng | ≥ 6 tháng 100; 3–5 → 75; 1–2 → 50; 1–3 tuần → 25; < 1 tuần 0 (đúng bậc câu gốc; bản chất cũng là câu 3) |
| Save 4 | **Tiến độ mục tiêu**: phần đóng góp thực hiện / kế hoạch trong các kỳ gần nhất, và trạng thái "đúng hạn" của mục tiêu | ≥ 100% → 100; 75–99 → 75; 50–74 → 50; 25–49 → 25; < 25 → 0 |
| Borrow 5 | **Tỉ lệ nghĩa vụ nợ trên thu nhập** (gốc + phí/lãi trả sau, vay) và dư nợ trả sau trên hạn mức | không nợ 100; tỉ lệ ≤ 15% 85; 15–30% 40; > 30% 0 (ngưỡng 15/30% **tự đặt**, cần căn cứ; chưa tìm được ngưỡng chuẩn Việt Nam) |
| Borrow 6 | Thay cho điểm tín dụng (không có CIC trong demo): lịch sử trả sau đúng hạn, tỷ lệ dùng hạn mức, số lần trễ | Quy theo số lần trễ 12 tháng và mức sử dụng hạn mức |
| Plan 7 | Bảo hiểm không quan sát được → thay bằng **khả năng chịu cú sốc**: sống sót bao nhiêu ngày dưới kịch bản "mất việc 2 tháng", "ốm một tuần" qua `stress_test` (Monte Carlo), tỉ lệ cú sốc mà hũ Dự phòng đủ đỡ | 100% cú sốc đủ → 100 … 0 không cú sốc nào đủ |
| Plan 8 | **Kỷ luật kế hoạch**: có lộ trình, mức chi hũ lệch so với ngân sách đã chia, tần suất mở app/xác nhận lương | Tỉ lệ ngày/tuần hũ nằm trong ngân sách |

Điểm thành phần = trung bình 2 chỉ số, tổng = trung bình 4 thành phần (đúng cấu trúc gốc). **Giải thích được từng điểm**: mỗi chỉ số trả kèm giá trị gốc ("chi/thu 1,08") và nguồn dữ liệu cho bảng "Vì sao". Khi thiếu dữ liệu (độ phủ thấp) trả điểm kèm khoảng và nêu rõ phần chưa tính.

### 3.8 Phân loại giao dịch 3 bước

**Chuẩn hóa văn bản [ĐỀ XUẤT]:** (1) hạ chữ thường; (2) bỏ dấu tiếng Việt (`unicodedata.normalize("NFD")`, bỏ ký tự kết hợp, `đ→d`) để **một dạng duy nhất** cho cả văn bản có dấu và không dấu; (3) từ điển viết tắt (`ck → chuyen khoan`, `tt → thanh toan`, `t11 → thang 11`, `tien nuoc/dien/net`); (4) che số tài khoản, số điện thoại, tên người; (5) thay số/ngày bằng token. Không tìm được nguồn nào kiểm thử embedding trên **tiếng Việt không dấu**; mọi chọn lựa dưới đây phải thử trên tập dev tự dựng.

**Mô hình embedding (đã đọc tài liệu):**
| Lựa chọn | Thông tin | Ghi chú |
|---|---|---|
| Amazon Titan Text Embeddings V2 (`amazon.titan-embed-text-v2:0`) | 8.192 token; vector 1.024 (mặc định), 512 hoặc 256; **Vietnamese có trong danh sách ngôn ngữ nhưng model "tối ưu cho tiếng Anh"**, truy vấn chéo ngôn ngữ cho kết quả kém | https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html |
| Cohere Embed v3 trên Bedrock | `input_type`: `search_document`, `search_query`, `classification`, `clustering`; 1.024 chiều; mỗi văn bản ≤ 512 token (~2.048 ký tự); ≤ 96 văn bản/lần | https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-embed-v3.html — **chưa xác nhận ngôn ngữ Vietnamese cụ thể** (trang không liệt kê) |
| `BAAI/bge-m3` (MIT, 1.024 chiều, 8.192 token, >100 ngôn ngữ) | Tự lưu trữ, nặng hơn | https://huggingface.co/BAAI/bge-m3 |
| Họ Việt hóa: `bkai-foundation-models/vietnamese-bi-encoder` (nền PhoBERT-base-v2), `AITeamVN/Vietnamese_Embedding` (tinh chỉnh từ bge-m3) | PhoBERT cần tách từ trước khi nhúng; điểm VN-MTEB chưa đọc được | [BLOG/REPO] https://arxiv.org/pdf/2507.21500 |
Đề xuất MVP: **Bedrock Titan V2 (cùng hệ AWS, không tự lưu model) hoặc Cohere v3**, thử cả hai trên tập dev ~300 chuỗi; nếu kém với không dấu thì thêm **TF-IDF ký tự** (`TfidfVectorizer(analyzer="char_wb", ngram_range=(2,4))`) kNN song song — bền với viết tắt và thiếu dấu, không cần model, chạy cục bộ [ĐỀ XUẤT].

**pgvector [ĐÃ ĐỌC]** (https://github.com/pgvector/pgvector, README ghi phiên bản 0.8.7; Aurora PostgreSQL hỗ trợ: https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.VectorDB.html):
- Toán tử: `<=>` khoảng cách cosine, `<->` L2, `<#>` âm tích vô hướng; **độ tương đồng cosine = `1 - (a <=> b)`**.
- Mặc định tìm kiếm **chính xác** (recall 100%), không cần chỉ mục; bảng nhỏ thì quét bảng có thể nhanh hơn. Mỗi người chỉ có vài trăm đến vài nghìn giao dịch đã gán nhãn → dùng `WHERE user_id = $1 ORDER BY embedding <=> $2 LIMIT 5` với chỉ mục B-tree trên `user_id` và **không** tạo HNSW. Nếu thêm HNSW cho kho dùng chung: chỉ mục xấp xỉ lọc **sau** khi quét nên bộ lọc chặt có thể trả ít hàng hơn; bật `hnsw.iterative_scan` hoặc dùng chỉ mục từng phần/phân vùng.
- Giới hạn chiều: chỉ mục `vector` ≤ 2.000 chiều, `halfvec` ≤ 4.000.

**Ngưỡng tin cậy:**
- Proposal đặt `≥ 0,97` gán bước 2, `≥ 0,9` tự gán, `0,6–0,9` xem lại, `< 0,6` hỏi. Cosine thô của embedding **không phải xác suất** và thang phụ thuộc từng model (Titan, Cohere, bge khác nhau). Đề xuất: lấy `k=5` láng giềng, **độ tin cậy = P(đúng)** hiệu chỉnh từ các đặc trưng (cosine tối đa, tỉ lệ phiếu của nhãn thắng, biên giữa nhãn nhất và nhì, số láng giềng) bằng **hồi quy logistic/Platt (sigmoid)** — scikit-learn khuyên sigmoid khi mẫu nhỏ, isotonic chỉ khi > ~1.000 mẫu (https://scikit-learn.org/stable/modules/calibration.html [ĐÃ ĐỌC]).
- Đặt ngưỡng theo **mục tiêu độ chính xác**, không theo con số cố định: `t_auto` = ngưỡng nhỏ nhất để độ chính xác trên tập kiểm ≥ 95% (NFR: đúng ≥ 90% tổng thể, hỏi < 10%); `t_ask` để tỉ lệ hỏi ≤ 10%. Vẽ biểu đồ độ tin cậy (`calibration_curve`) để xem lệch.
- **Điều chỉnh theo từng người** (proposal): tăng `t_auto` riêng cho người nhận mà người dùng đã sửa nhiều lần — lưu `corrections` theo `(user, recipient)` và cộng vào ngưỡng.

**Đặc trưng hành vi cho chuyển khoản tên riêng, không lời nhắn [ĐỀ XUẤT]:** số lần chuyển trước đó cho người này; khoảng cách trung vị giữa các lần và độ biến thiên (CV) → "nhịp"; độ biến thiên số tiền; số tiền tròn (chia hết 10.000/50.000/100.000); số tiền so với trung vị chi người dùng; ngày trong tháng (đầu tháng → trọ); giờ trong ngày (giờ ăn trưa); thời gian từ hóa đơn nhóm/chi ăn uống gần nhất; người này có từng chuyển ngược cho người dùng (chia tiền hai chiều → ăn chung, khác một chiều → tiền trọ/cho mượn). Dùng làm (a) tín hiệu đưa vào prompt bước LLM và/hoặc (b) bộ phân loại nhẹ (logistic/GBM) huấn luyện trên dữ liệu persona có nhãn, nếu không đủ thời gian thì chỉ (a).

### 3.9 Hồ sơ hành vi

Với dữ liệu ít (người dùng mới, 3 persona), **phân cụm trên cá nhân vô nghĩa** (k lớn hơn số người) [ĐỀ XUẤT]. Làm gọn:
1. **Đặc trưng có giải thích, không cụm** (đáp ứng "nhận xét truy được về số liệu"): `share_first10` (tỉ lệ chi trong 10 ngày sau lương), hồ sơ chi theo ngày trong tuần (7 tỉ lệ, **làm trơn Dirichlet** với số đếm giả để chuỗi ngắn không nhảy), tỉ lệ chi cuối tuần, 4 khung giờ (sáng/trưa/chiều/tối-đêm), tỉ lệ ngày không chi, hệ số biến thiên, mức tập trung đối tác (HHI), dùng trả sau (tỉ lệ dùng hạn mức, số kỳ góp).
2. **Co kéo về trung bình nhóm** (empirical Bayes): `ước_lượng = (n·x̄_user + k₀·x̄_nhóm)/(n + k₀)` cho các tham số theo hũ khi `n` ngày nhỏ — chính là "nhóm tương tự" mà proposal dùng cho khởi đầu lạnh.
3. **Cụm chỉ làm trên tập người dùng tổng hợp lớn hơn** (ví dụ vài trăm hồ sơ sinh ra từ 3 persona có nhiễu) để chọn **nhóm tương tự** khi người mới đến: K-Means (inductive, gán được người mới) với k = 3–5, đặc trưng chuẩn hóa, chọn k bằng `silhouette_score` — scikit-learn 1.9.1: K-Means phù hợp "kích thước cụm gần bằng nhau, hình học phẳng, inductive"; Gaussian mixtures "không scale"; HDBSCAN và agglomerative là **transductive** (không áp cho người mới) [ĐÃ ĐỌC] (https://scikit-learn.org/stable/modules/clustering.html). Nhãn cụm đặt tên bằng quy tắc dựa trên tâm cụm, không để LLM tự diễn giải.
4. LLM chỉ **diễn giải** bảng đặc trưng + bằng chứng (số liệu) thành 1–2 câu; không tự suy.

### 3.10 Sinh dữ liệu tổng hợp 3 persona

**Hiện trạng thư viện [BLOG/REPO, kết quả tìm kiếm]:** AMLSim (IBM, Apache-2.0, đa tác tử, sinh CSV nhưng nhắm rửa tiền), IBM AMLworld/IT-AML (arXiv 2306.16424), AMLGentex, PaySim (cần dữ liệu thật để hiệu chỉnh) — đều **không** nhằm mô phỏng chi tiêu cá nhân theo persona. Không tìm được thư viện sẵn cho yêu cầu này → **tự viết bộ sinh** (~300–500 dòng), dùng `numpy.random.Generator` (hạt giống cố định) + **Faker** (40.63.0, 2026-11-20, MIT, Python ≥ 3.10; locale `vi_VN` có provider `person` [ĐÃ ĐỌC trong GitHub]) chỉ để sinh tên người nhận.

**Cấu trúc bộ sinh [ĐỀ XUẤT]:**
1. **Hồ sơ persona**: thu nhập, ngày lương, tiền trọ + ngày đóng, hóa đơn (điện nước, net, điện thoại) với chu kỳ/khoảng tiền, hạn mức và hành vi trả sau, mục tiêu, tên người nhận thường gặp (bạn ăn chung, chủ trọ), cửa hàng quen. Tạo 3 hồ sơ khai báo kèm sinh dữ liệu (proposal §7).
2. **Chi tiêu theo hũ/ngày — mô hình hurdle**: `P(chi>0 | hũ, thứ, giai đoạn lương) = sigmoid(β₀ + β_dow + β_phase)`; số tiền ~ lognormal (tham số theo hũ, persona); **hiệu ứng ngày lương**: cường độ chi suy giảm theo `exp(−d/τ)` sau ngày lương (proposal có ví dụ 46% ngân sách chi trong 10 ngày đầu); **cuối tuần** tăng chi ăn uống/giải trí; **nhịp tháng** (Tết, 30/4, 2/9) tùy persona; tách ngày thành số giao dịch (Poisson) và chia tổng ngày bằng Dirichlet, gán giờ theo hỗn hợp (sáng/trưa/tối).
3. **Nghĩa vụ tất định** với nhiễu nhỏ (ngày trả lệch ±1 ngày, hóa đơn điện dao động ±25%).
4. **Cú sốc**: quá trình Poisson (ví dụ ~2–4 lần/năm) với số tiền lognormal đuôi dày (sửa xe, ốm, đóng học phí) — lưu `shock_id`.
5. **Điểm gãy lối sống cài sẵn**: tại ngày `T_break` đổi tham số (chuyển trọ: tiền trọ và chi di chuyển đổi mức; đổi việc: ngày lương/thu nhập đổi) — **lưu nhãn `T_break`** để chấm PELT/CUSUM.
6. **Nhãn sự thật**: hũ đúng của từng giao dịch, loại tiền vào (lương/khác), `T_break`, ngày/độ lớn cú sốc, để đánh giá phân loại, PELT, ECOD, và dự báo.
7. **Tên đối tác/lời nhắn**: kho mẫu có dấu và không dấu + viết tắt + lỗi gõ ("ck tien nuoc t11", "CK TIEN TRO T12", "tra no ban A") và chuyển khoản tên riêng không lời nhắn (chủ trọ, bạn bè, gia đình).
8. **Cắt ngắn lịch sử**: sinh 12 tháng nhưng đánh giá cũng ở các điểm cắt 14, 30, 60, 90 ngày để kiểm đường khởi đầu lạnh.

**Cạm bẫy lớn:** đánh giá mô hình bằng dữ liệu do chính họ mô hình gần giống sinh ra sẽ **quá lạc quan** (vòng lặp). Giảm nhẹ: cho bộ sinh dùng **họ phân phối khác** mô hình dự báo (hurdle-lognormal + hiệu ứng ngày lương, khác ETS/Chronos), thêm nhiễu cấu trúc (ngày chi lớn bất thường, thay đổi phương sai, dữ liệu thiếu), và tách bộ sinh dùng cho phát triển/bộ dùng cho đánh giá cuối. Chưa tìm được số liệu thật về cơ cấu chi tiêu người 18–30 ở Việt Nam để hiệu chỉnh tham số; nếu cần phải xin nguồn riêng (không thuộc phạm vi ghi chú này).

## 4. Khuyến nghị cho Yofina, chỗ proposal cần chỉnh

1. **§11/F1 "Chronos-2 chạy được trên CPU, 120 triệu tham số"**: đúng về chủ trương (model card nói hỗ trợ CPU, AutoGluon-Cloud có tầng `ml.c6i.2xlarge`) nhưng **không có số đo CPU nào** trong tài liệu; paper không bàn dữ liệu gián đoạn. Đổi giọng thành "thử nghiệm so với baseline, bật nếu thắng trên backtest". **[Đã chạy thử 2026-11-21]** nay có số: chạy được trên CPU (0,2 s cho 7 chuỗi, 1,2 GB RAM đỉnh); thắng ETS nhưng hòa với hurdle tự viết trên dữ liệu tổng hợp; đề nghị giữ giọng "thử nghiệm A/B", không đặt vào bộ tối thiểu.
2. **§10.4 ngưỡng 30/90 ngày**: là giả thuyết; paper Chronos-2 nói ICL giúp khi lịch sử ngắn nên có thể bật Chronos-2 sớm hơn 90 ngày; ngược lại ETS với mùa 7 có thể cần > 30 ngày. Đưa vào backtest theo độ dài lịch sử. **[Đã chạy thử 2026-11-21]** ETS(season 7) chỉ thắng seasonal naive từ ~90 ngày (6,54× tệ hơn ở 14 ngày, 1,16× ở 30 ngày); hurdle và Chronos-2 thắng từ 21 đến 30 ngày; ở 14 ngày Chronos-2 có covariate (1,25) kém hơn seasonal naive. Ngưỡng 30/90 ngày của proposal nên sửa thành: dưới ~21 ngày dùng baseline/nhóm tương tự, 21 đến 90 ngày dùng hurdle (hoặc Chronos-2 không covariate), ≥ 90 ngày thêm ETS làm đối chứng (dữ liệu tổng hợp).
3. **Chất lượng dự báo (NFR)**: "khoảng 80% phủ 75–85%" và "tốt hơn seasonal naive trên pinball loss" cần định nghĩa: ở mức ngày hay tổng tuần/30 ngày, trung bình qua τ nào; bổ sung **Brier score của xác suất hụt** và **sai số ngày cạn**. Độ phủ theo ngày của hũ thưa không có nghĩa.
4. **Monte Carlo (§4, F1)**: bổ sung "tương quan giữa các ngày" — Chronos-2 và đa số model chỉ trả phân vị biên; cần copula/shuffle, nếu không thì xác suất hụt thấp giả tạo. **[Đã chạy thử 2026-11-21]** xác nhận cho hũ dày (độc lập: 5,8% so với 10% thật ở ăn uống); nhưng copula Gaussian **sai hướng ở hũ thưa**, nên hũ thưa cần mô phỏng hurdle trực tiếp.
5. **Croston/TSB cho hũ thưa**: ước lượng trung bình, dự báo phẳng, không cho phân vị native (chưa kiểm chứng) — hũ thưa nên dùng mô phỏng hurdle hoặc conformal trên TSB; viết lại dòng "Mô hình làm mượt thường dự báo sai loại chuỗi này" cho khớp. **[Đã chạy thử 2026-11-21]** đã kiểm: không có khoảng native (báo lỗi); conformal n_windows=2 phủ thiếu; hurdle tự viết tốt hơn ~30 đến 37% pinball trên hũ thưa (dữ liệu tổng hợp).
6. **Conformal**: "Adaptive conformal inference tự chỉnh khi hành vi đổi" đúng, nhưng đảm bảo lý thuyết yếu với T ≤ 365; phải kèm đo độ phủ trên backtest; không có AgACI Python sẵn. **[Đã chạy thử 2026-11-21]** ACI tự viết sửa phủ thiếu 0,61 → 0,81; γ ≥ 0,05 làm khoảng nở gấp ~5 lần.
7. **CUSUM trong `river`**: không có lớp CUSUM; dùng `PageHinkley` hoặc tự viết. ADWIN mặc định kiểm mỗi 32 điểm (`clock=32`) — chỉnh cho chuỗi ngày/tuần. **[Đã chạy thử 2026-11-21]** xác nhận không có CUSUM; nhưng chỉnh `clock` **không đủ**: ADWIN không bắt được điểm gãy +49% ở mọi `clock` thử (kể cả `clock=1`) trên chuỗi chi tiêu nhiễu. Bỏ ADWIN khỏi đề xuất; dùng PELT tuần + CUSUM tự viết.
8. **FinHealth Score**: proposal ghi "tính từ hành vi thay cho bảng hỏi" — hợp lý, nhưng toolkit gốc cần license khi dùng trong phần mềm thương mại; đặt tên riêng và ghi "lấy cảm hứng"; hỏi lại trước khi ghi tên chính thức. Ngưỡng định lượng (nợ/thu, chi/thu) phải tự đặt, toolkit không cung cấp.
9. **Quy hoạch tuyến tính "OR-Tools / PuLP"**: bỏ PuLP (Python ≥ 3.12, không kèm CBC); dùng `scipy.optimize.linprog` (đã có scipy) hoặc OR-Tools GLOP. Thêm biến elastic để vô nghiệm trả mức thiếu, thay vì chỉ "nới ràng buộc mềm". **[Đã chạy thử 2026-11-21]** xác nhận bỏ PuLP (cài thử: không kèm solver, API đổi); thêm: elastic cần `M` theo ưu tiên và trọng số khác nhau.
10. **Ngưỡng embedding 0,97**: cosine thô phụ thuộc model; hiệu chỉnh bằng Platt và đặt theo độ chính xác mục tiêu; Titan V2 ghi tối ưu cho tiếng Anh nên cần thử với không dấu.
11. **ML trên Lambda**: StatsForecast + scipy + statsmodels nên đóng container image; Chronos-2 buộc container (torch). Ghi vào kiến trúc: "Lambda container" chứ không "Lambda zip". **[Đã chạy thử 2026-11-21]** đo: StatsForecast + deps 332 MB (Windows), torch CPU 518 MB + model 478 MB; xác nhận container image.
12. **Tài liệu bàn giao**: thêm `ForecastModel` interface (trả bảng phân vị + metadata mô hình) để đổi ETS/TSB/Chronos-2 mà không động Monte Carlo.

## 5. Điều chưa chắc, cần chạy thử

- **[Đã chạy thử 2026-11-21: một phần]** thời gian Chronos-2 và chronos-2-small trên CPU desktop đã đo (context 90 đến 335, horizon 30: 0,14 đến 0,30 s cho 7 chuỗi với bản 120M); **còn chưa đo** trên Lambda 3–10 GB / c6i và cold start container có torch.
- (Bản gốc) Thời gian Chronos-2 và chronos-2-small trên CPU (Lambda 3–10 GB, c6i) với context 90–365 và horizon 30; thời gian cold start của container có torch.
- **[Đã chạy thử 2026-11-21: một phần]** Chronos-2 thắng seasonal naive và ETS (và hòa với hurdle tự viết) trên 1 persona tổng hợp (5 seed); covariate ngày lương chưa chứng minh được lợi ích ổn định (chỉ rõ ở hũ nghĩa vụ); chuỗi < 30 ngày: ở 14 ngày bản có covariate kém seasonal naive. **Còn chưa kiểm:** 3 persona, dữ liệu thật, `cross_learning`.
- (Bản gốc) Chronos-2 có thắng seasonal naive/ETS trên chuỗi chi tiêu ngày của 3 persona, đặc biệt hũ nhiều số 0, và với covariate ngày lương; hành vi khi chuỗi < 30 ngày; có cần `cross_learning` trong lô cho người mới (cân nhắc quyền riêng tư).
- **[Đã chạy thử 2026-11-21: đã trả lời]** kích thước StatsForecast + deps: 332 MB (Windows; wheel Linux chưa đo); AutoETS mùa 7 cần ≥ ~60 đến 90 ngày; SeasonalNaive/AutoETS có khoảng native, TSB/Croston/ADIDA/IMAPA chỉ conformal.
- (Bản gốc) Kích thước thực của image/zip StatsForecast + deps; AutoETS với mùa 7 cần bao nhiêu ngày tối thiểu; `SeasonalNaive`, TSB, IMAPA có khoảng native hay chỉ conformal (tài liệu không chứng minh).
- **[Đã chạy thử 2026-11-21: đã trả lời một phần]** ρ lag-1 từ PIT 0,05 đến 0,39 (ăn uống 0,39); xác suất hụt nhạy với ρ (độc lập thấp hơn 4 đến 8 điểm % ở mức 10%); copula kém với khối lượng tại 0 (hũ thưa sai hướng). Schaake shuffle chưa thử.
- (Bản gốc) Hệ số tương quan ρ giữa các ngày của phần dư PIT và độ nhạy của xác suất hụt vào ρ; có cần Schaake shuffle không. Độ chính xác copula với phân vị rời rạc (nhiều khối lượng tại 0).
- Thuật toán Schaake shuffle và AgACI (lưới γ, luật gộp) **chưa đọc được từ PDF**; cần đọc trực tiếp nếu muốn cài đặt bản chính thức.
- **[Đã chạy thử 2026-11-21: đã trả lời trên 1 persona]** PELT c ∈ [2; 3] (chuỗi tuần), CUSUM k=0,5/h=4 hoặc k=1/h=4, PageHinkley threshold 20 (tuần), ADWIN không bắt được; báo giả/sót đã đếm. Cần lặp trên nhiều persona/điểm gãy.
- (Bản gốc) Lưới penalty/`c` tốt cho PELT, tham số CUSUM `k,h`, `delta` ADWIN/PageHinkley trên dữ liệu tổng hợp; xác suất báo nhầm/báo sót.
- Chất lượng embedding (Titan V2, Cohere v3, bge-m3, họ Việt hóa) trên tiếng Việt không dấu, viết tắt; ngưỡng tự gán đạt precision 95%; tỉ lệ phải hỏi.
- Định dạng payload covariate của JumpStart (`pytorch-forecasting-chronos-2`); giới hạn bộ nhớ SageMaker serverless; Chronos-2 có trong region triển khai không (chưa kiểm).
- Nội dung đầy đủ của thỏa thuận license FinHealth (Exhibit A, mục 4) — có áp dụng cho chỉ số phái sinh tự tính không.
- Ngưỡng ADI/CV² Syntetos–Boylan [NỀN] cần đối chiếu nguồn; ngưỡng nợ/thu 15/30% là tự đặt.
- Faker `vi_VN` chỉ xác nhận có provider `person`; chưa kiểm chất lượng tên; chưa có số liệu thật về chi tiêu người 18–30 để hiệu chỉnh bộ sinh.
- **[Đã đọc 2026-11-21]** phần cuối `proposal-summary.md` (dòng 335 đến 462) đã đọc: không mâu thuẫn với ghi chú này; liên quan là §12 (ngân sách what-if: mô phỏng 0,5 s, đã đo 76 đến 160 ms ở 5.000 đến 10.000 đường), §14 (stack ghi "OR-Tools hoặc PuLP": nên bỏ PuLP; "StatsForecast hoặc Darts": giữ StatsForecast; "Chronos-2 trên SageMaker MVP nếu kịp": chạy được trên CPU container nhưng không bắt buộc), §13 (rủi ro "dữ liệu tổng hợp trông không thật" cũng áp cho kết luận của spike).
- (Bản gốc) Phần còn lại của `proposal-summary.md` (từ dòng 340, khoảng 120 dòng) **chưa đọc** vì giới hạn kích thước đọc; có thể chứa ràng buộc liên quan (rủi ro, kế hoạch) cần đối chiếu.

## 6. Nguồn (truy cập 2026-11-21)

**Chronos-2 và AutoGluon**
- Paper Chronos-2: https://arxiv.org/abs/2510.15821 (và bản HTML https://arxiv.org/html/2510.15821)
- Model card: https://huggingface.co/autogluon/chronos-2
- Repo/README: https://github.com/amazon-science/chronos-forecasting
- Mã pipeline: https://raw.githubusercontent.com/amazon-science/chronos-forecasting/main/src/chronos/chronos2/pipeline.py
- PyPI chronos-forecasting 2.3.2: https://pypi.org/project/chronos-forecasting/ , https://pypi.org/pypi/chronos-forecasting/json
- AutoGluon Chronos-2 (1.6.1 docs): https://auto.gluon.ai/stable/tutorials/timeseries/forecasting-chronos.html ; `autogluon.timeseries` 1.6.3: https://pypi.org/project/autogluon.timeseries/
- AutoGluon-Cloud trên SageMaker: https://auto.gluon.ai/cloud/dev/tutorials/foundation-model-timeseries.html
- Bài AWS (bị cắt nội dung, chỉ lấy tiêu đề): https://aws.amazon.com/jp/blogs/news/chronos-2-on-amazon-sagemaker-ai-with-autogluon-cloud/
- Decathlon / benchmark bên thứ ba (kết quả tìm kiếm, chưa đọc gốc): https://aihub.hkuspace.hku.hk/?p=8156 , https://dev.classmethod.jp/en/articles/dgx-spark-timeseries-fm-3-bench/
- Lambda quotas: https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html

**Thống kê và dự báo**
- StatsForecast: https://pypi.org/project/statsforecast/ , https://pypi.org/pypi/statsforecast/json , https://github.com/Nixtla/statsforecast , mã `models.py`: https://raw.githubusercontent.com/Nixtla/statsforecast/main/python/statsforecast/models.py , `pyproject`: https://raw.githubusercontent.com/Nixtla/statsforecast/main/pyproject.toml
- Conformal StatsForecast: https://nixtlaverse.nixtla.io/statsforecast/docs/tutorials/conformalprediction.html
- Cross-validation: https://nixtlaverse.nixtla.io/statsforecast/docs/tutorials/crossvalidation.html
- TSB: https://nixtlaverse.nixtla.io/statsforecast/docs/models/tsb.html ; IMAPA: https://nixtlaverse.nixtla.io/statsforecast/docs/models/imapa.html ; CrostonClassic: https://nixtlaverse.nixtla.io/statsforecast/docs/models/crostonclassic.html
- utilsforecast losses: https://nixtlaverse.nixtla.io/utilsforecast/losses.html
- Teunter, Syntetos, Babai 2011 (tóm tắt): https://dx.doi.org/10.1016/j.ejor.2011.05.018
- Kolassa 2016 (IJF, count data): https://eprints.lancs.ac.uk/id/eprint/134005
- Darts: https://unit8co.github.io/darts/ ; `Chronos2Model`: https://unit8co.github.io/darts/generated_api/darts.models.forecasting.chronos2_model.html
- statsmodels `ETSResults.simulate`: https://www.statsmodels.org/stable/generated/statsmodels.tsa.exponential_smoothing.ets.ETSResults.simulate.html
- Issue numba StatsForecast: https://www.github.com/Nixtla/statsforecast/issues/753

**Conformal**
- Gibbs & Candès (ACI): https://arxiv.org/html/2106.00170
- Zaffran et al. (AgACI): https://arxiv.org/abs/2202.07282 (PDF không trích được text), https://proceedings.mlr.press/v162/zaffran22a.html , repo https://github.com/mzaffran/AdaptiveConformalPredictionsTimeSeries
- AdaptiveConformal (R): https://arxiv.org/abs/2312.00448
- MAPIE: https://pypi.org/project/MAPIE/ , https://mapie.readthedocs.io/en/latest/ , lớp `TimeSeriesRegressor`: https://mapie.readthedocs.io/en/v1.2.1/generated/mapie.regression.TimeSeriesRegressor.html

**Monte Carlo, copula**
- Schaake shuffle cho giá điện: https://arxiv.org/abs/2204.10154 ; COBASE: https://arxiv.org/pdf/2510.25610v2 ; Ensemble copula coupling: https://arxiv.org/pdf/1302.7149

**Đổi hành vi, ngoại lai**
- ruptures: https://pypi.org/project/ruptures/ , https://centre-borelli.github.io/ruptures-docs/user-guide/detection/pelt/ , https://centre-borelli.github.io/ruptures-docs/user-guide/detection/window/ , https://centre-borelli.github.io/ruptures-docs/user-guide/costs/costnormal/ ; paper https://arxiv.org/abs/1801.00826
- river ADWIN: https://riverml.xyz/latest/api/drift/ADWIN/ ; PageHinkley: https://riverml.xyz/latest/api/drift/PageHinkley/
- PyOD: https://pypi.org/project/pyod/ ; mã ECOD: https://raw.githubusercontent.com/yzhao062/pyod/master/pyod/models/ecod.py ; paper ECOD: https://arxiv.org/abs/2201.00382

**Tối ưu**
- SciPy linprog: https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linprog.html
- OR-Tools: https://pypi.org/project/ortools/ , https://developers.google.com/optimization/lp/lp_example
- PuLP: https://pypi.org/project/PuLP/

**FinHealth**
- Trang chính: https://finhealthnetwork.org/score/ ; phương pháp: https://finhealthnetwork.org/tools/financial-health-score/finhealth-score-methodology/
- Toolkit 2021 (PDF, đã đọc trực tiếp trang 1–8): https://finhealthnetwork.org/wp-content/uploads/2021/11/FinHealthScoreToolkit-2021.pdf
- Thỏa thuận license 2026: https://finhealthnetwork.org/finhealth-score-license-agreement/

**Phân loại, embedding, hồ sơ**
- Titan Text Embeddings: https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html
- Cohere Embed v3 trên Bedrock: https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-embed-v3.html
- bge-m3: https://huggingface.co/BAAI/bge-m3 ; VN-MTEB: https://arxiv.org/pdf/2507.21500 ; Vietnamese bi-encoder: https://huggingface.co/bkai-foundation-models/vietnamese-bi-encoder ; Vietnamese_Embedding: https://huggingface.co/AITeamVN/Vietnamese_Embedding
- pgvector: https://github.com/pgvector/pgvector ; Aurora: https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.VectorDB.html
- scikit-learn hiệu chỉnh: https://scikit-learn.org/stable/modules/calibration.html ; phân cụm: https://scikit-learn.org/stable/modules/clustering.html

**Dữ liệu tổng hợp**
- AMLSim: https://github.com/IBM/AMLSim ; IBM AML dữ liệu: https://arxiv.org/pdf/2306.16424
- Faker: https://pypi.org/project/Faker/ ; provider `vi_VN`: https://github.com/joke2k/faker/tree/master/faker/providers/person/vi_VN
