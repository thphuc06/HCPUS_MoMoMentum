# Spike ML, thống kê, tối ưu: kết quả chạy thử (2026-11-21)

> Chạy local trên CPU, không đụng AWS, không gọi LLM. Mã và số thô: [spikes/ml-forecasting/](../../spikes/ml-forecasting/) (có `README.md` cách chạy lại). Ghi chú gốc được kiểm chứng: [ml-forecasting.md](ml-forecasting.md).
> **Số đo** = in ra từ script trong thư mục spike. **Suy luận** = người viết kết luận từ số đo, có ghi rõ.
> **Giới hạn lớn nhất:** toàn bộ dữ liệu là **tổng hợp** do `gen_data.py` sinh (hurdle-lognormal + hiệu ứng ngày lương + tâm trạng AR(1) chung). Câu "model A thắng B" chỉ đúng với bộ sinh này. Đặc biệt mô hình hurdle tự viết cùng họ với bộ sinh nên được lợi; đừng đọc đó là bằng chứng trên dữ liệu thật.

## 0. Môi trường và phiên bản thực cài

| | |
|---|---|
| Máy | Windows 11 Pro, Intel i5-14600KF (20 luồng; torch dùng 14 luồng mặc định), RAM 32 GB, ổ C còn 15,8 GB trước khi bắt đầu |
| Python | 3.13.9 (interpreter có sẵn, uv 0.11.14 tạo venv). Mọi thư viện cài được trên 3.13, không cần hạ xuống 3.12 |
| StatsForecast | **2.1.1** (đúng bản ghi chú đề xuất). Kéo theo `statsmodels 0.15.0`, `scipy 1.18.1`, `pandas 2.3.3`, `numpy 2.5.5`, `coreforecast 0.0.20`, `fugue 0.9.9`, `utilsforecast 0.17.2`, `pyarrow 26.0.1`, ... |
| torch | **2.15.0+cpu** (index `https://download.pytorch.org/whl/cpu`) |
| Chronos | `chronos-forecasting` **2.3.2**, `transformers 5.23.0`, `accelerate 1.16.0`, `huggingface-hub 2.4.0` |
| Phát hiện/ngoại lai | `ruptures 1.1.10`, `river 0.27.0`, `pyod 3.6.8` (kéo `numba 0.68.1`, `llvmlite 0.50.0`, `scikit-learn 1.9.1`), `scipy 1.18.1` (linprog/HiGHS) |
| PuLP | `pulp 4.3.1` (thử riêng, xem §8) |

Danh sách đầy đủ: `spikes/ml-forecasting/requirements-main.txt` và `requirements-statsforecast-only.txt`.

**Dung lượng đĩa (ổ C).** Còn trống 15,83 GB trước khi bắt đầu, 12,15 GB lúc cao điểm (sau cài torch CPU + tải 2 model + chạy; ngưỡng dừng phần Chronos là 6 GB nên không bị chạm), 12,79 GB sau dọn. Mức giảm ròng ~3,0 GB là số trên cả ổ nên có lẫn ghi của các spike khác chạy song song. Torch dùng bản CPU-only (518 MB, không kéo CUDA).
Đã xóa: `.uv-cache` (1,26 GB, phần lớn là hardlink vào venv nên giải phóng thực ít hơn), `.hf-cache` (563 MB: 2 model Chronos-2, tải lại bằng bước 3 trong README), `.venv-pulp` (venv dùng một lần), `__pycache__`. Không đụng cache HF/uv/pip toàn cục sẵn có của máy (`~/.cache/huggingface` không do spike tạo).
Còn để lại: `spikes/ml-forecasting/.venv` (môi trường chính, `site-packages` ~1,0 đến 1,3 GB) và `.venv-sf` (StatsForecast tối thiểu, ~370 MB), cộng mã, `data/` (1 MB), `results/` (8 MB). Có thể xóa hai venv nếu cần chỗ; `README.md` có lệnh dựng lại.

## 1. Bộ sinh dữ liệu tổng hợp

**Cách làm.** `gen_data.py`, seed cố định `20261121`, đơn vị nghìn đồng. Minh: lương 9.000k ngày 5 hằng tháng, 7 hũ (`an_uong`, `di_chuyen`, `giai_tri`, `mua_sam`, `du_lich`, `nghia_vu`, `du_phong`), 365 ngày từ 2025-11-01.
- Hũ chi tiêu: `P(chi>0)` = sigmoid(hệ số cơ sở + cuối tuần + exp(−d/8) ngày lương + tải "tâm trạng"), số tiền lognormal; "tâm trạng" là AR(1) (ρ=0,55) dùng chung các hũ nên các ngày liền kề có tương quan thật.
- Hũ thưa: `du_lich` (95% ngày bằng 0), `mua_sam` (84%), `giai_tri` (67%), `du_phong` (99%, chỉ có cú sốc Poisson ~4 lần/năm).
- `nghia_vu`: tiền trọ ngày 1 (2.500k, 2.800k từ 1/8), trả sau ngày 5 (450k ±150k), net ngày 8, điện ngày 12 (320k ±80k), nước ngày 14, điện thoại ngày 20; ngày trả lệch ±1 với xác suất 20% (trừ tiền trọ).
- **Điểm gãy cài sẵn** ở tháng thứ 9: **2026-07-10** (chỉ số ngày 251): ăn uống ×1,35, di chuyển ×1,6, giải trí ×1,3, trọ +300k từ tháng sau. Tổng chi 3 hũ chi đều tăng từ 99,2 lên 148,3k/ngày (+49%).
- Khoản lớn một lần (có nhãn trong `data/truth.json`): sửa laptop 1.800k (2026-01-17), tiệc 950k (2026-04-30), điện thoại 2.200k (2026-09-02), cộng 3 cú sốc `du_phong`; hai chuyến du lịch (không gán nhãn bất thường).

| Số đo | |
|---|---|
| Tổng chi/tháng (k) | 6.900 đến 12.300 (tháng có khoản lớn), lương 9.000 |
| Tỉ lệ ngày bằng 0 | an_uong 1%, di_chuyen 18%, giai_tri 67%, mua_sam 84%, du_lich 95%, nghia_vu 80%, du_phong 99% |

**Kết luận.** Đủ dùng cho spike. Hạn chế: một persona, một điểm gãy, bộ sinh cùng họ với mô hình hurdle (xem giới hạn ở đầu file). §3.2 có lặp trên 4 seed khác để kiểm độ ổn định theo ngẫu nhiên.

## 2. StatsForecast 2.1.1 trên Python 3.13 / Windows

**Cách thử.** Venv riêng chỉ có StatsForecast (`.venv-sf`), đo kích thước, thời gian import, thời gian fit + dự báo 30 ngày cho 7 chuỗi (335 ngày lịch sử), thử `level=[80]` mặc định và `prediction_intervals=ConformalIntervals(h=30, n_windows=2)`.

| Số đo | Kết quả |
|---|---|
| Cài được trên 3.13/Windows | **Có**, wheel dựng sẵn, 27 gói, cài 8 giây |
| Kéo numba? | **Không** (không có `numba`, `llvmlite` trong venv; `sys.modules` không có numba sau khi import). Numba trong venv chính đến từ **PyOD**, không từ StatsForecast |
| `site-packages` ngay sau khi cài | **332 MB** (scipy 87, pyarrow 87, statsmodels 42, pandas 40, numpy 22 + numpy.libs 21, scipy.libs 20, statsforecast 2). Sau khi chạy, thêm ~38 MB `__pycache__` |
| Bỏ `__pycache__` và thư mục `tests` | ~271 MB; vẫn lớn hơn giới hạn 250 MB giải nén của Lambda zip. `pyarrow` do `triad`/`fugue` bắt buộc: gỡ pyarrow thì `import statsforecast` lỗi |
| Import | `import statsforecast` 0,65 s + `statsforecast.models` 1,2 s (nóng); lần đầu ngay sau khi cài 2,2 s + 4,0 s |
| Fit + dự báo 30 ngày × 7 chuỗi, chỉ điểm, nóng | SeasonalNaive 2 ms, AutoETS(season 7) **0,25 s**, Croston/TSB/ADIDA 2 ms, IMAPA 4 ms; cả 6 model một lượt 0,24 s |
| Với conformal (n_windows=2) | SeasonalNaive 3 ms, AutoETS 0,70 s, Croston/TSB/ADIDA 3 ms, IMAPA 8 ms |

Khoảng dự báo (cột `lo-80`/`hi-80`):

| Model | `level=[80]` native | Conformal |
|---|---|---|
| SeasonalNaive | Có (rộng: 785k trung bình, 94% biên dưới âm) | Có |
| AutoETS | Có (362k, 86% biên dưới âm: cần cắt ở 0) | Có |
| CrostonClassic, TSB, ADIDA, IMAPA | **Không**: lỗi `You have to instantiate the class with prediction_intervals to calculate them` | **Có** (truyền `prediction_intervals=ConformalIntervals(...)` khi gọi `forecast`) |

Lưu ý nhỏ: đối tượng model nhớ trạng thái `prediction_intervals` sau lần gọi conformal (dùng lại instance đó với `level` sẽ không báo lỗi nữa), nên tạo instance mới cho mỗi cấu hình.

**Kết luận.**
- *Số đo:* StatsForecast 2.1.1 cài được, không numba, nhanh (AutoETS 0,25 s cho 7 chuỗi). Ghi chú gốc đúng ở điểm này.
- *Số đo:* ghi chú gốc chưa rõ "không kiểm chứng được khoảng native cho Croston/TSB/ADIDA/IMAPA"; nay đã rõ: **không có**, chỉ conformal.
- *Số đo:* 332 MB trên Windows, đã vượt 250 MB zip. *Suy luận:* wheel Linux có kích thước cùng bậc (không đo); đúng với khuyến nghị dùng Lambda **container image**. Muốn zip thì phải cắt pyarrow/tests, và pyarrow không gỡ được.

## 3. Backtest rolling-origin

**Cách thử.** `s3_backtest.py`: 31 origin (chỉ số 120, 127, ..., 330 cho đến 335; mỗi 7 ngày), horizon 30, mở rộng lịch sử (expanding), fit lại từng origin. Mọi model quy về bảng 13 phân vị (0,01 đến 0,99) theo ngày. Model: `SN_native`, `SN_conf` (SeasonalNaive, khoảng native hoặc conformal n_windows=2), `ETS_native`, `ETS_conf`, `Croston_conf`, `TSB_conf`, `ADIDA_conf`, `IMAPA_conf` (chỉ có conformal), `Hurdle` (tự viết: `P(chi>0)` theo ô cuối tuần × nửa đầu kỳ lương, làm trơn Beta(1,2), số tiền bootstrap từ các ngày có chi trong 180 ngày, 4.000 mẫu/ngày), `Chronos2` (có covariate), `Chronos2_nocov`, `Chronos2_small`.
Chỉ số: pinball trung bình qua τ = 0,1/0,5/0,9; độ phủ khoảng P10 đến P90 theo ngày; **tổng 30 ngày** lấy mẫu từ bảng phân vị bằng Gaussian copula AR(1) (ρ lấy từ tự tương quan lag 1 của PIT, hoặc ρ=0 để so). Baseline "seasonal naive" = `SN_conf` (bản native tệ hơn 17%, xem bảng).

### 3.1 Kết quả chính (31 origin, seed 20261121)

Pinball tương đối so với `SN_conf` (1,00 = bằng, nhỏ hơn là tốt hơn), trung bình số học qua hũ:

| Model | 2 hũ dày (ăn uống, di chuyển) | 4 hũ thưa (giải trí, mua sắm, du lịch, dự phòng) | 6 hũ chi tiêu | trước điểm gãy | sau điểm gãy | `nghia_vu` |
|---|---:|---:|---:|---:|---:|---:|
| SN_native | 0,90 | 1,31 | 1,17 | 1,05 | 1,00 | 1,07 |
| ETS_native | 0,73 | 0,93 | 0,86 | 0,81 | 0,71 | 0,73 |
| ETS_conf | 0,81 | 0,85 | 0,84 | 0,85 | 0,70 | 0,63 |
| Croston_conf | 0,76 | 0,73 | 0,74 | 0,71 | 0,77 | 0,65 |
| TSB_conf | 0,79 | 0,79 | 0,79 | 0,79 | 0,80 | 0,68 |
| ADIDA_conf | 0,76 | 0,75 | 0,75 | 0,73 | 0,76 | 0,65 |
| IMAPA_conf | 0,76 | 0,81 | 0,79 | 0,78 | 0,77 | 0,68 |
| **Hurdle (tự viết)** | **0,65** | **0,50** | **0,55** | 0,54 | 0,58 | 0,53 |
| **Chronos2 (120M, covariate)** | **0,63** | **0,50** | **0,55** | 0,55 | 0,57 | **0,29** |
| Chronos2_nocov | 0,64 | 0,52 | 0,56 | 0,55 | 0,57 | 0,39 |
| Chronos2_small (28M) | 0,63 | 0,50 | 0,55 | 0,54 | 0,58 | 0,37 |

Độ phủ khoảng 80% (P10 đến P90) **theo ngày** (mục tiêu 0,80):

| Model | ăn uống | di chuyển | giải trí | mua sắm | du lịch | dự phòng |
|---|---:|---:|---:|---:|---:|---:|
| SN_native | 0,92 | 0,86 | 0,87 | 0,97 | 0,95 | 0,99 |
| SN_conf | 0,60 | 0,57 | 0,64 | 0,77 | 0,90 | 0,99 |
| ETS_native | 0,86 | 0,74 | 0,84 | 0,96 | 0,92 | 1,00 |
| ETS_conf | 0,58 | 0,59 | 0,55 | 0,66 | 0,75 | 0,82 |
| Croston_conf / TSB_conf | 0,59 / 0,58 | 0,58 / 0,56 | 0,55 / 0,54 | 0,68 / 0,57 | 0,72 / 0,65 | 0,67 / 0,94 |
| Hurdle | 0,82 | 0,77 | 0,84 | 0,88 | 0,95 | 1,00 |
| Chronos2 | 0,78 | 0,74 | 0,76 | 0,79 | 0,85 | 1,00 |
| Chronos2_small | 0,77 | 0,71 | **0,53** | **0,34** | 0,92 | 0,95 |

Độ phủ theo ngày của hũ thưa (đặc biệt du lịch, dự phòng) gần như vô nghĩa vì P10 = P50 = 0; đọc kèm cột tổng 30 ngày.

**Tổng 30 ngày** (độ phủ P10 đến P90; hai số = ρ ước lượng từ PIT / độc lập ρ=0), trung bình 2 hũ dày và 4 hũ thưa:

| Model | 2 hũ dày | 4 hũ thưa |
|---|---|---|
| SN_native | 0,55 / 0,45 | 0,15 / 0,15 |
| ETS_native | 0,47 / 0,26 | 0,12 / 0,12 |
| ETS_conf | 0,26 / 0,21 | 0,23 / 0,21 |
| Croston_conf | 0,37 / 0,35 | 0,15 / 0,13 |
| Hurdle | 0,48 / 0,42 | **0,72 / 0,71** |
| Chronos2 | 0,52 / 0,45 | 0,51 / 0,48 |
| Chronos2_nocov | 0,61 / 0,50 | 0,51 / 0,49 |

Pinball tổng 30 ngày so với `SN_conf` (2 hũ dày / 4 hũ thưa / nghĩa vụ): Hurdle 0,81 / 0,66 / 0,17; Chronos2 0,62 / 0,54 / 0,11; ETS_native 0,85 / 1,52 / 0,83; Croston_conf 0,83 / 0,64 / 0,21.

### 3.2 Kiểm độ bền và các phát hiện phụ

- **Lặp trên 4 seed khác** của cùng bộ sinh (101 đến 104, `s10_seeds.py`): pinball tương đối so với SN_conf (6 hũ): Hurdle 0,572 ±0,013, Chronos2 0,570 ±0,008, Chronos2_nocov 0,572 ±0,013, ETS_native 0,812 ±0,050. Trên 2 hũ dày: Chronos2 0,65, Hurdle 0,66, ETS_native 0,68. Phủ theo ngày ăn uống: ETS_native 0,93, Hurdle 0,81, Chronos2 0,78, SN_conf 0,59.
- **Chronos-2 so với Hurdle:** tỉ lệ pinball 6 hũ 1,007 (SE thô 0,016; origin chồng lấn nên SE bị đánh thấp), thắng 52% số origin: **hòa**. **Chronos-2 so với ETS_native:** 0,67, thắng 31/31 origin.
- **Covariate (ngày lương, cuối tuần) cho Chronos-2:** trên seed chính giảm pinball 6 hũ ~7% (thắng 94% origin so với `nocov`), nhưng trên 4 seed khác chênh lệch ~0 (0,570 so với 0,572). Lợi ích rõ chỉ ở `nghia_vu` (30,4 so với 41,1 k/ngày; Hurdle 55,2). *Suy luận:* covariate chưa chứng minh được giá trị trên chi tiêu tùy ý; có giá trị với chuỗi có lịch cứng, mà chuỗi đó nên dùng lịch tất định thay vì dự báo.
- **Base so với small:** base (120M) tốt hơn small (28M) ~7% pinball và small có độ phủ rất kém ở vài hũ thưa (mua sắm 0,34 theo ngày, tổng 30 ngày không cải thiện). Số này từ một bộ sinh, một lần chạy.
- **Khoảng conformal mặc định của StatsForecast (n_windows=2) phủ thiếu nghiêm trọng:** 0,54 đến 0,60 cho 80% danh định ở hũ dày (SN_conf, ETS_conf, Croston/TSB/ADIDA/IMAPA). Khoảng native của ETS phủ tốt hơn (0,86/0,74 ở hũ dày, hơi thừa). Dùng conformal mặc định mà không hiệu chỉnh lại sẽ vi phạm NFR "phủ 75 đến 85%".
- **Tổng 30 ngày phủ thiếu cho mọi model**, kể cả tốt nhất (0,48 đến 0,61 ở hũ dày với ρ theo PIT). Quét ρ (3 hũ dày, `s3c_extra.py`): độ phủ tổng 30 ngày với ρ = 0 / 0,2 / 0,4 / 0,6 / 0,8 là ETS_native 0,27 / 0,35 / 0,48 / 0,66 / 0,83; Hurdle 0,45 / 0,54 / 0,59 / 0,66 / 0,80; Chronos2 0,51 / 0,58 / 0,67 / 0,74 / 0,87. Nghĩa là cần ρ cỡ **0,7 đến 0,8** để tổng 30 ngày phủ đúng, lớn hơn nhiều ρ lag-1 đo từ PIT (ăn uống 0,39 với Hurdle/Chronos2, di chuyển 0,05, giải trí 0,07 đến 0,13). *Suy luận:* sai số dự báo có thành phần "mức" kéo dài cả 30 ngày (sai lệch mức + tâm trạng), không phải AR(1) bậc 1; chọn ρ bằng độ phủ tổng 30 ngày trên backtest, không bằng tự tương quan lag 1. Tương tự hiệu ứng nằm ở cả trước và sau điểm gãy.
- **Độ dài lịch sử tối thiểu** (`s9_short_history.py`, 14 cửa sổ, cắt còn L ngày cuối, pinball so với SN_native cùng L, 6 hũ chi tiêu):

| L (ngày) | ETS | Hurdle | Chronos2 (covariate) | Chronos2_nocov |
|---:|---:|---:|---:|---:|
| 14 | **6,54** (ăn uống bùng nổ: pinball 784 so với 23) | 0,88 | 1,25 | 0,94 |
| 21 | **2,25** | 0,76 | 0,66 | 0,66 |
| 30 | 1,16 | 0,74 | 0,63 | 0,65 |
| 60 | 1,02 | 0,61 | 0,61 | 0,62 |
| 90 | 0,92 | 0,60 | 0,59 | 0,60 |

*Số đo:* **AutoETS với mùa 7 không dùng được dưới ~60 ngày** (tệ hơn seasonal naive; chỉ thắng ở 90 ngày); Hurdle và Chronos-2 thắng seasonal naive từ 21 đến 30 ngày; ở 14 ngày Chronos-2 có covariate (1,25) tệ hơn cả không covariate (0,94).

**Kết luận mục 3 (cho bộ sinh này).** Hurdle tự viết và Chronos-2 ngang nhau và cùng tốt hơn hẳn ETS và các mô hình gián đoạn; mô hình gián đoạn (Croston/TSB/ADIDA/IMAPA, chỉ có P50 = trung bình) tốt hơn seasonal naive ~25% nhưng thua Hurdle rõ, đúng như ghi chú dự đoán. Hurdle được lợi vì cùng họ với bộ sinh.

## 4. Chronos-2 trên CPU

**Cách thử.** `s4_chronos_probe.py` (mỗi model một tiến trình riêng để RAM đỉnh đúng), `chronos-forecasting 2.3.2`, `Chronos2Pipeline.from_pretrained(..., device_map="cpu")` (chạy được, ghi chú gốc ghi "chưa kiểm"), `predict_df` có `future_df` với covariate `is_payday`, `is_weekend`, `days_since_payday`, `cross_learning=False`, 30 ngày, 3 phân vị, torch 14 luồng.

| Số đo | `amazon/chronos-2` | `autogluon/chronos-2-small` |
|---|---:|---:|
| Tham số (đếm thật) | 119,5M, float32 | 27,9M, float32 |
| Kích thước trên đĩa (`model.safetensors`) | 478 MB | 112 MB |
| Tải model (cache hệ điều hành nóng) | 0,41 s (lần 2: 0,34 s) | 0,15 s (0,13 s) |
| Tải xuống lần đầu từ Hugging Face | 16,6 s | 6,0 s |
| RAM tiến trình sau khi tải (RSS; torch + chronos đã nạp ~404 MB) | 892 MB | 524 MB |
| RAM đỉnh sau mọi lượt suy luận (gồm lô 1.050 chuỗi) | **1.193 MB** | 768 MB |
| Suy luận 7 chuỗi, context 90 / 180 / 335 ngày, có covariate | 0,135 / 0,20 / 0,30 s | 0,045 / 0,066 / 0,081 s |
| 7 chuỗi, context 180, không covariate | 0,087 s | 0,029 s |
| Lô 350 chuỗi (context 180, batch_size 256) | 12,2 s (28,6 chuỗi/s) | 3,0 s (115 chuỗi/s) |
| Lô 1.050 chuỗi | 36,3 s (28,9 chuỗi/s) | 8,5 s (124 chuỗi/s) |
| `import torch` / `import chronos` (nóng) | 1,2 s / 2,5 s (lần đầu sau cài: 3,8 s / 8,8 s) | như trái |

Kích thước môi trường: `torch` CPU-only 518 MB, `transformers` 63 MB; cả `.venv` (kèm statsforecast, pyod, numba, scikit-learn, matplotlib...) có `site-packages` 1.311 MB.

Độ chính xác: xem §3 (cùng bảng backtest). Ngoại suy lên vài trăm chuỗi: ~29 chuỗi/s (120M) và ~115 đến 124 chuỗi/s (small), tuyến tính theo số chuỗi.

**Kết luận.**
- *Số đo:* chạy được trên CPU, nhanh hơn nhiều so với ngoại suy thô trong ghi chú gốc (ghi chú dự đoán vài chục chuỗi/s cho c6i.2xlarge; ở đây 29 chuỗi/s trên 14 luồng desktop, 0,2 s cho một persona 7 hũ). Với 7 chuỗi, độ trễ suy luận không phải vấn đề; vấn đề là đóng gói (torch 518 MB + model 478 MB) và RAM ≥ 1,2 GB. Chưa đo trên vCPU của Lambda (chậm hơn desktop) và chưa đo cold start container.
- **Có thắng mô hình thống kê trên dữ liệu này không?** Thắng ETS và các mô hình gián đoạn rõ (pinball thấp hơn 33% so với ETS_native, thắng cả 31 origin; ổn định qua 4 seed). **Không thắng mô hình hurdle tự viết** (hòa: 1,007). Tuy nhiên hurdle cùng họ với bộ sinh nên có thể được lợi.
- **Có đáng đưa vào MVP không?** *Suy luận từ số đo:* **không bắt buộc**. Hurdle tự viết đạt cùng chất lượng bằng numpy (0,65 s cho cả 31 origin × 7 chuỗi), không cần torch/container/model 478 MB. Chronos-2 là ứng viên để thay hoặc làm thử nghiệm A/B khi có dữ liệu thật, hoặc nếu muốn một chuỗi tuyên bố "foundation model có đo". Nếu đưa vào, dùng bản 120M (small kém ~7% và phủ thiếu ở hũ thưa), `cross_learning=False`.

## 5. Adaptive Conformal Inference (ACI)

**Cách thử.** `s5_aci.py` (~25 dòng thuật toán). Điểm CQR `s = max(q10 − y, y − q90)`, một `α_t` cho mỗi (hũ, nhóm horizon 1 đến 7 / 8 đến 14 / 15 đến 30), cập nhật `α_{t+1} = α_t + γ(0,2 − err_t)` theo thứ tự ngày khi đã quan sát (phản hồi trễ vì horizon 30 ngày, các cửa sổ chồng lấn), phân vị bảo thủ (n+1) trên mọi điểm đã thấy, bỏ qua hiệu chỉnh khi < 20 điểm. Đánh giá từ origin thứ 8 (≈ 8 tuần sau) để mọi cột cùng tập origin; 5 hũ chi tiêu; mục tiêu 0,80. γ = 0 là split conformal.

Độ phủ daily trung bình 5 hũ, mục tiêu 0,80 (cột "sau gãy" là các origin sau 2026-07-10):

| Model gốc | không ACI | γ=0 | γ=0,005 | γ=0,01 | γ=0,02 | γ=0,05 |
|---|---:|---:|---:|---:|---:|---:|
| ETS_conf (phủ thiếu: 0,61) | 0,609 | 0,797 | 0,814 | 0,813 | 0,807 | 0,807 |
| ETS_conf, sau gãy | 0,587 | 0,791 | 0,807 | 0,792 | 0,779 | 0,805 |
| Chronos2 | 0,791 | 0,815 | 0,816 | 0,817 | 0,816 | 0,811 |
| Chronos2, sau gãy | 0,780 | 0,794 | 0,797 | 0,804 | 0,818 | 0,851 |
| ETS_native (phủ thừa: 0,87) | 0,868 | 0,864 | 0,867 | 0,869 | 0,838 | 0,803 |
| Hurdle | 0,856 | 0,859 | 0,856 | 0,859 | 0,859 | 0,838 |

Độ rộng khoảng trung bình (k VND/ngày): ETS_conf 80,5 (gốc) → 102 (γ=0) → 111 → 168 → 224 → 396 (γ=0,05); Chronos2 62,4 → 63,9 → 64,3 → 65,0 → 69,9 → 317; ETS_native 162 → 161 → 163 → 176 → 210 → 437.

**Kết luận.**
- *Số đo:* ACI **sửa được** model phủ thiếu (ETS_conf 0,61 → 0,81, kể cả sau điểm gãy) và gần như không đổi khi model gốc đã phủ gần đúng (Chronos2). Với ETS_native phủ thừa (0,87), γ nhỏ không đổi gì; chỉ γ=0,05 kéo về 0,80 (đổi lại khoảng nở).
- *Số đo:* **γ lớn làm khoảng nở rất rộng** (γ=0,05: gấp 5 lần ở Chronos2, ETS_conf gấp gần 5), (suy luận: `α_t` trôi ra ngoài (0,1), nhất là ở hũ thưa, nên phân vị bị kẹp về cực trị; `α_t` cuối của hurdle ở du lịch đạt 1,49 với γ=0,02); γ trong 0,005 đến 0,01 là điểm tốt trên dữ liệu này. Ghi chú gốc khuyên γ 0,01 đến 0,05; số đo thiên về cận dưới.
- *Số đo:* γ=0 (split conformal, không thích ứng) đã đủ trên dữ liệu gần dừng này; lợi ích riêng của phần "thích ứng" **không tách ra được** trong spike (điểm gãy chỉ có một và model gốc thích ứng được nhờ fit lại). Cần dữ liệu có drift mạnh hơn để kiểm.

## 6. Monte Carlo số dư hũ

**Cách thử.** `s6_mc.py`. Origin 2026-10-20, lương kế tiếp 5/11, "trước kỳ lương" = 15 ngày đầu. Bảng phân vị lấy từ (a) **oracle**: phân phối biên thật của bộ sinh (100.000 đường mô phỏng thẳng từ bộ sinh), (b) Chronos-2, (c) Hurdle. Lấy mẫu qua nghịch đảo hàm phân vị (nội suy tuyến tính trên 13 mức, neo `q(0)=0`, đuôi trên ngoại suy theo độ dốc đoạn cuối), vector hóa hoàn toàn bằng numpy (`searchsorted` + fancy indexing, không vòng lặp theo cột), copula Gaussian AR(1) với ρ khác nhau. **Sự thật** = xác suất hụt tính trực tiếp từ 100.000 đường của bộ sinh (dòng chi ≥ 0 nên "hụt trước lương" ⇔ tổng chi 15 ngày đầu vượt số dư). Để so công bằng, số dư đầu kỳ chọn sao cho xác suất hụt thật = 10%, 30% hoặc 50%.

Xác suất hụt ước lượng (N=20.000 đường), bảng phân vị **oracle** (cô lập riêng tác động của sự phụ thuộc):

| P thật | ρ | ăn uống | di chuyển | giải trí | mua sắm | du lịch |
|---:|---:|---:|---:|---:|---:|---:|
| 0,10 | 0 (độc lập) | 0,058 | 0,091 | 0,089 | 0,091 | 0,086 |
| 0,10 | 0,2 | 0,092 | 0,131 | 0,115 | 0,105 | 0,095 |
| 0,10 | 0,4 | 0,129 | 0,177 | 0,146 | 0,121 | 0,109 |
| 0,10 | 0,8 | 0,220 | 0,285 | 0,202 | 0,147 | 0,119 |
| 0,30 | 0 | 0,277 | 0,316 | 0,326 | 0,371 | 0,384 |
| 0,30 | 0,4 | 0,323 | 0,365 | 0,337 | 0,339 | 0,343 |
| 0,30 | 0,8 | 0,353 | 0,410 | 0,312 | 0,251 | 0,223 |
| 0,50 | 0 | 0,529 | 0,530 | 0,552 | 0,556 | 0,624 |
| 0,50 | 0,4 | 0,502 | 0,513 | 0,499 | 0,496 | 0,554 |
| 0,50 | 0,8 | 0,454 | 0,496 | 0,401 | 0,339 | 0,361 |

(Đầy đủ ρ = 0, 0,2, 0,4, 0,6, 0,8 và cả bảng Chronos-2/Hurdle: `results/s6_mc.txt`.)

- *Số đo:* với biên đúng, lấy mẫu **độc lập đánh giá thấp** xác suất hụt khi rủi ro thấp: tại P thật 10%, hũ dày cho 5,8% (ăn uống) và 9,1% (di chuyển), thiếu 4 điểm % và tương đối −42% ở ăn uống; copula AR(1) ρ ≈ 0,2 đến 0,3 khớp (ăn uống 9,2% ở ρ=0,2). Chênh lệch giữa độc lập và copula ρ=0,4 là **+7 điểm % (ăn uống), +8,6 (di chuyển) tại P=10%; +4,6 và +4,9 tại P=30%**; tại P=50% đổi chiều nhẹ (−2,7 và −1,7 điểm %).
- *Số đo:* với **hũ thưa** (mua sắm, du lịch) copula Gaussian lấy mẫu qua phân vị có khối lượng ở 0 cho hướng sai khi ρ lớn (ρ=0,8 tại P=50%: 0,34 và 0,36 so với 0,50 thật); độc lập gần đúng hơn. *Suy luận:* hũ thưa nên mô phỏng hurdle trực tiếp (như ghi chú gốc đề xuất), không qua nội suy phân vị.
- *Số đo:* sai số do bảng phân vị của model lớn hơn tác động của sự phụ thuộc. Cùng số dư (P thật 10%), Chronos-2 độc lập cho ăn uống 21,8%, Hurdle 29,7%; chênh với thật còn lớn hơn chênh độc lập/copula. Đây là một origin duy nhất và "sự thật" ở đây không điều kiện hóa theo mức chi gần đây, nên **không khái quát**; chỉ cho thấy chất lượng phân vị biên quan trọng không kém sự phụ thuộc.
- Ngày cạn (hũ ăn uống, số dư thực của Minh): trung vị trong các đường có cạn là ngày 14 (độc lập), 12 (ρ=0,8), 13 (thật). Chênh 1 ngày, nhỏ hơn chênh xác suất.

**Thời gian chạy** (`mc_run`, 6 hũ × 30 ngày, trung vị 15 lần, máy này; gồm sinh số ngẫu nhiên, copula, nội suy, cumsum, xác suất và ngày cạn):

| N đường | độc lập | copula (vòng for AR(1)) | copula (`scipy.signal.lfilter`) |
|---:|---:|---:|---:|
| 1.000 | 13,6 ms | 13,5 ms | 14,6 ms |
| 5.000 | 76 ms | 77 ms | 77 ms |
| 10.000 | 153 ms | 163 ms | 161 ms |

Một hũ, N=5.000: 11,7 ms. Mục tiêu "dưới 0,5 giây" đạt với dư địa ~3× ở 10.000 đường trên desktop; vòng for AR(1) 30 bước không phải nút thắt (lfilter không nhanh hơn). *Chưa đo:* vCPU Lambda chậm hơn (không đo), cold start import scipy (0,56 s nóng cho `scipy.optimize`).
Sai số chuẩn thực của xác suất qua 40 seed ở p≈0,5 (ăn uống): N=1.000 1,73 điểm %, N=5.000 0,61, N=10.000 0,40, khớp công thức `√(p(1−p)/N)` trong ghi chú (1,6 / 0,7 / 0,5).

**Kết luận.** Vector hóa numpy dễ đạt <0,5 s. Độc lập không an toàn khi báo rủi ro thấp (đánh giá thấp 4 đến 8 điểm % ở mức 10%): dùng copula cho hũ dày, hurdle trực tiếp cho hũ thưa. ρ cho tổng 30 ngày phải hiệu chỉnh (xem §3.2: ρ≈0,7 đến 0,8 để phủ đúng tổng 30 ngày, nhưng ρ≈0,2 đến 0,3 khớp xác suất hụt 15 ngày ở bộ sinh này); không có một ρ đúng cho mọi đại lượng.

## 7. Phát hiện thay đổi và ngoại lai

**Cách thử.** `s7_change.py`. Chuỗi = tổng 3 hũ chi đều (ăn uống + di chuyển + giải trí); điểm gãy thật ngày 251 (tuần 36, vì tuần 35 là ngày 245 đến 251). Ba biến thể chuỗi tuần không chồng lấn (52 tuần): A thô (có khoản lớn), B cắt khoản lớn (kẹp ở median + 5×MAD của từng hũ), C = B + chia cho hồ sơ trung bình theo "số ngày từ lương".

**PELT (`ruptures` 1.1.10, cost `l2`, `jump=1`, penalty = c × σ² × ln n với σ bền từ sai phân):**

| Chuỗi tuần | c=0,5 | c=1 | c=2 | c=3 | c=5, 8 |
|---|---|---|---|---|---|
| A thô | bắt đúng, 7 báo giả | bắt đúng, 3 giả | **bắt đúng, 0 giả** | không bắt được | không bắt được |
| B cắt khoản lớn | bắt đúng, 7 giả | bắt đúng, 3 giả | **bắt đúng, 0 giả** | **bắt đúng, 0 giả** | không bắt được |
| C cắt + khử nhịp | bắt đúng, 7 giả | bắt đúng, 3 giả | **bắt đúng, 0 giả** | **bắt đúng, 0 giả** | không bắt được |

Ở c = 2 đến 3 điểm gãy bắt được đúng tuần 36; ở c ≤ 1 điểm khớp nằm trong ±2 tuần nhưng kèm báo giả. Cửa sổ penalty tốt rất hẹp (c ∈ [2; 3]); c ≤ 1 báo 3 đến 7 điểm giả, c ≥ 5 bỏ sót cả điểm gãy +49%. Chuỗi ngày (cuộn 7 ngày, `min_size=14`) **không dùng được**: c từ 1 đến 30 cho 11 đến 18 điểm gãy (giả nhiều vì cửa sổ cuộn tạo tự tương quan), c=100 còn `[256, 285, 339]` (điểm gãy thật 251; chỉ 256 đúng), thời gian 10 đến 280 ms. `l1` không báo gì; `normal` (đổi cả phương sai) báo `[12, 39]` (không đúng tuần 36). Khoản lớn một lần: chuỗi thô (A) chỉ giữ được điểm đúng ở c=2, chuỗi đã cắt (B, C) rộng hơn.

**river 0.27.0:**
- **Xác nhận không có CUSUM**: `river.drift` chỉ có `ADWIN, DriftRetrainingClassifier, DummyDriftDetector, KSWIN, NoDrift, PageHinkley`; tìm "cusum" trong mọi tên module river không ra gì.
- `PageHinkley` (min_instances=30, delta=0,005, alpha=0,9999, mode="both") trên chuỗi **ngày** chuẩn hóa z theo 120 ngày đầu: threshold 5 → 11 sự kiện, 7 báo giả trước gãy, phát hiện sau gãy trễ 1 ngày; threshold 10 → 5 giả, trễ 4; threshold 20 → 3 giả, trễ 22; threshold 50 (mặc định) → 1 giả, **trễ 65 ngày**. Ở threshold 5 các sự kiện cách nhau đúng 30 ngày (suy luận: do nhịp ngày lương). Trên chuỗi **tuần** C (min_instances=10): threshold 20 → 0 giả, phát hiện trễ 3 tuần; threshold 10 → 1 giả, trễ 3 tuần.
- `ADWIN` (delta 0,002 mặc định): với `clock=32` (mặc định), `clock=7`, `clock=1`, trên chuỗi ngày và chuỗi tuần, cả khi chuẩn hóa về [0,1] và delta 0,0002/0,01/0,05/0,3: **không bắt được điểm gãy +49%** (độ dịch chuẩn hóa 0,136 so với độ lệch chuẩn ngày 0,207, tức ~0,66 σ). Kiểm công cụ trên bậc thang sạch 0,2→0,5 (sd 0,1): bắt được, nhưng **trễ 43 điểm (clock=1) hoặc 55 điểm (clock=32)**; bậc 0,2→0,3 (sd 0,15): không bắt. *Suy luận:* ADWIN hợp với bước nhảy lớn so với nhiễu; chuỗi chi tiêu hằng ngày nhiễu cao không hợp. `clock=1` bắt sớm hơn `clock=32` ~12 điểm. ADWIN giả định dữ liệu trong [0,1] nên phải chuẩn hóa.
- CUSUM hai phía tự viết (10 dòng) trên z tuần: k=0,5/h=4 báo giả 3, trễ 1 tuần; k=1/h=4 báo giả 1, trễ 3 tuần; không hơn rõ PageHinkley.

**PyOD ECOD 3.6.8** (đặc trưng `[log(số tiền/trung vị hũ), log(số tiền)]`, 857 hũ-ngày có chi, 3 khoản lớn có nhãn):
- Hạng ECOD của 3 khoản có nhãn: **1, 2, 3** trên 857 (recall 100%). Nhưng ở ngưỡng `contamination` cố định precision thấp: 0,10 → gắn cờ 86 (3 đúng); 0,05 → 43; 0,02 → 18 (3 đúng, 15 sai); 0,01 → 9 (3 đúng, 6 sai). ECOD đối xứng nên cờ cả các khoản **rất nhỏ** (5 đến 10k); lọc đuôi phải còn 5 cờ (3 đúng, 2 sai) ở 0,01. So sánh: z bền MAD > 10 gắn 8 cờ (3 đúng, 5 sai), MAD > 6 gắn 16 (13 sai): **ngang ECOD**. Fit 1 ms (lần đầu 200 đến 500 ms); import `pyod.models.ecod` 2,2 s (kéo sklearn/numba, thêm ~136 MB llvmlite + numba).
- Lưu ý: hũ `du_phong` bị loại khỏi phép chấm vì mọi khoản của nó đều là cú sốc (không bất thường so với trung vị riêng của hũ); khoản lớn vẫn nằm trong chuỗi gốc nếu không cắt.

**Kết luận.** PELT tuần với `l2`, `min_size=2`, chuỗi đã cắt khoản lớn, penalty 2 đến 3 × σ²·ln n bắt đúng tháng 9 (tuần 36) với 0 báo giả trên bộ này, nhưng rất nhạy penalty (cần hiệu chỉnh trên nhiều persona). Nhịp ngày lương không gây báo giả ở tuần (khử nhịp không cần thiết ở đây, B bằng C). Không dùng ADWIN cho chuỗi này; PageHinkley/CUSUM chỉ để "nghi" rồi PELT xác nhận (đúng máy trạng thái đã đề xuất). ECOD không hơn z bền MAD trên 1 chiều số tiền.

## 8. Phân bổ lương vào hũ bằng LP

**Cách thử.** `s8_lp.py`, `scipy 1.18.1` `linprog(method="highs")`, mô hình trong ghi chú gốc (biến `x`, thiếu mềm `s`, elastic `e`) thêm biến phụ cho phạt thay đổi so với kỳ trước. 7 hũ, 35 biến, đơn vị k VND. Cứng: nghĩa vụ 3.980, ăn uống 2.000, di chuyển 450 (tổng 6.430). Mềm: giải trí 600, mua sắm 500, du lịch 900, dự phòng 1.000 (tổng 3.000); trọng số phạt 1/1/2/3.

| Ca | Kết quả (`status`) |
|---|---|
| 1: I=9.000 | 0 (tối ưu): cứng đủ (e=0), thiếu mục tiêu mềm Σs=430 (dồn vào giải trí, ca trọng số hòa) |
| 1b: trọ +300, phạt thay đổi so với kỳ trước | 0: thay đổi `x` đúng 300 (nghĩa vụ) bù −300 ở mua sắm, hũ khác giữ nguyên |
| 1c: giãn kỳ hạn mục tiêu (T×0,5) | 0: Σs=0 (nới mềm một lần đủ) |
| 2a: I=5.500, sàn cứng đặt qua `bounds` | **2 (vô nghiệm)**, không có thông tin mức thiếu: xác nhận cảnh báo của ghi chú |
| 2b: I=5.500, sàn cứng qua `x+e ≥ L` (elastic, M=10⁶ như nhau) | 0: Σe=930 (báo mức thiếu), nhưng thiếu rơi hết vào **nghĩa vụ** (3.050 trên 3.980) trong khi ăn uống và di chuyển đủ: sai thứ tự ưu tiên vì M bằng nhau |
| 2c: như 2b, M theo ưu tiên (nghĩa vụ 10⁶ > ăn uống 10⁵ > di chuyển 10⁴) | 0: nghĩa vụ đủ 3.980, thiếu rơi vào ăn uống (−480) và di chuyển (−450) |
| 3: I=0 | 0: Σe=6.430 |
| 4: `integrality` trên `x` | 0: nhưng nghiệm tối ưu khác ca 1 (dồn thiếu sang mua sắm) vì trọng số hòa |

Thời gian giải (median / p95, 300 lần): ca 1 **0,98 / 1,03 ms**, ca 1b 1,02 / 1,17, ca vô nghiệm 0,71 / 0,82, MILP nguyên 1,00 / 1,05, `highs-ds` 1,03, `highs-ipm` 1,27. `import scipy.optimize` ~0,56 s lần đầu.

**PuLP (thử cài, venv dùng một lần):** `pulp 4.3.1` cài được trên 3.13 (bản này lõi Rust, API mới: `LpVariable(name, lowBound=...)` kiểu cũ **báo lỗi** `unexpected keyword`; `PULP_CBC_CMD` **không còn**). Sau `uv pip install pulp`: `pulp.listSolvers(onlyAvailable=True)` = **`[]`** (không kèm solver nào); sau `pulp[highs]` (thêm `highspy 1.16.0`): `['HiGHS']`. Có extra `cbc` (`cbcbox`), `highs`, `scip`, `glpk`, ... **Nhận định "PuLP bản mới không kèm solver" đúng**, và API đổi so với mọi ví dụ cũ.

**Kết luận.** `linprog` đủ (≈1 ms), `status` rõ ràng (0 hoặc 2). Hai cạm bẫy đo được: (1) sàn cứng qua `bounds` cho vô nghiệm không có chi tiết, phải dùng biến elastic; (2) elastic với một M chung phân bổ thiếu **tùy tiện** (hòa ưu tiên), cần M riêng theo ưu tiên; trọng số mục tiêu hòa cũng cho nghiệm không duy nhất (ca 1 và ca 4 khác nhau), nên dùng trọng số khác nhau hoặc thêm một mục tiêu phụ.

## 9. Bộ tối thiểu đề xuất cho MVP, sau khi đã đo

Các điểm dưới đây là **suy luận từ số đo trên dữ liệu tổng hợp**, cần kiểm lại khi có dữ liệu thật hoặc bộ sinh khác họ.

1. **Khung backtest tự viết** (rolling-origin, 31 origin × 12 model chạy 45 s trên máy này), chấm pinball P10/P50/P90, phủ theo ngày **và tổng 30 ngày**, ghi theo hũ dày/thưa và trước/sau điểm gãy. Đây là nơi cần thêm persona/seed khác nhau.
2. **Dự báo mặc định cho mọi hũ chi tiêu: hurdle tự viết theo lịch (ô cuối tuần × nửa đầu kỳ lương, bootstrap số tiền)**: tốt ngang Chronos-2, không phụ thuộc torch, thắng seasonal naive từ ~21 ngày lịch sử, bảng phân vị trả sẵn cho Monte Carlo. Giữ `ForecastModel.predict(...) -> bảng phân vị` để cắm model khác.
3. **StatsForecast 2.1.1 chỉ làm baseline** (SeasonalNaive; AutoETS **chỉ cho chuỗi ≥ 90 ngày** và hũ dày), không dùng conformal mặc định `n_windows=2` mà không hiệu chỉnh (phủ 0,54 đến 0,60). Croston/TSB/ADIDA/IMAPA không cần cho MVP (thua hurdle ở cả hũ thưa). Đóng gói Lambda **container image** (332 MB Windows, pyarrow bắt buộc).
4. **Chronos-2: thử nghiệm A/B, không nằm trong bộ tối thiểu.** Nếu bật: bản 120M, `cross_learning=False`, container ~1,2 GB RAM đỉnh; chỉ bật khi thắng hurdle trên dữ liệu thật hoặc persona khác họ bộ sinh.
5. **ACI tự viết ~25 dòng, γ = 0,005 đến 0,01**, một `α_t` cho mỗi (hũ, nhóm horizon), kẹp `α_t` để khoảng không nở vô hạn; chỉ áp khi model gốc phủ lệch (sửa 0,61 → 0,81). Không cần AgACI để có kết quả.
6. **Monte Carlo numpy vector hóa**: 5.000 đường (76 ms) cho what-if, 10.000 (160 ms) cho batch; copula Gaussian AR(1) cho hũ dày, hurdle mô phỏng trực tiếp cho hũ thưa; **chọn ρ bằng độ phủ trên backtest**, không bằng tự tương quan lag 1; báo kèm khoảng sai số chuẩn.
7. **Đổi hành vi:** PELT tuần (`l2`, `min_size=2`, chuỗi đã cắt khoản lớn, penalty 2 đến 3 × σ²·ln n, hiệu chỉnh trên nhiều persona) làm bộ xác nhận; CUSUM/PageHinkley tự viết trên z tuần làm bộ "nghi" (trễ ~3 tuần ở bộ sinh này). **Bỏ ADWIN.** **Bỏ PyOD** cho MVP: z bền MAD một chiều cho khoản lớn (ngang ECOD, tránh kéo numba/sklearn, 2,2 s import).
8. **Phân bổ lương:** `scipy.optimize.linprog` (HiGHS), elastic với M **theo ưu tiên**, trọng số mục tiêu khác nhau; ~1 ms. Bỏ PuLP.

## 10. Điều vẫn chưa thử được

- **Dữ liệu thật** hoặc bộ sinh khác họ (không hurdle-lognormal): mọi bảng xếp hạng ở §3 chưa biết có giữ nguyên không; hurdle có lợi thế nội tại. Mới có một persona, một điểm gãy, năm seed của cùng bộ sinh.
- **Lambda/AWS thật:** cold start container có torch, thời gian suy luận trên vCPU Lambda (Chronos-2 và `mc_run` đều đo trên desktop 14 luồng), RAM thật theo cấu hình Lambda, kích thước image Linux (số 332 MB là wheel Windows).
- **Chronos-2:** `cross_learning` trong lô, ảnh hưởng của `batch_size`, tinh chỉnh (fine-tune), covariate phong phú (hóa đơn đến hạn, lễ), context tối thiểu dưới 14 ngày có hợp lý; payload JumpStart/SageMaker.
- **ACI:** nhóm drift mạnh, AgACI (lưới γ, luật gộp OPERA), tách tác dụng "thích ứng" khỏi "split conformal".
- **Monte Carlo:** Schaake shuffle và bootstrap theo khối chưa cài; tương quan **giữa các hũ** (bộ sinh có tâm trạng chung, MC trong spike lấy mẫu độc lập giữa hũ); cạn "ví tổng"; what-if với common random numbers.
- **PELT/CUSUM:** hiệu chỉnh penalty trên nhiều persona/điểm gãy (hũ chuyển trọ, đổi việc làm đổi ngày lương), điểm gãy nhỏ hơn +49%, nhiều điểm gãy; phát hiện online theo sự kiện từng giao dịch.
- **ECOD đa chiều** với đặc trưng giờ/người nhận (spike chỉ có số tiền theo ngày, không có giao dịch cấp từng dòng).
- Phần còn lại của ml-forecasting.md ngoài phạm vi spike này: embedding/phân loại, hồ sơ hành vi, điểm chống chịu, license FinHealth.
