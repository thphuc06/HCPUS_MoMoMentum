# ml/

**Trạng thái (2026-11-22):** dự báo theo hũ, ACI, Monte Carlo, hiệu chỉnh và khung backtest đã cài (phase 2, luồng B; mục "Cài đặt" dưới đây, số đo ở [docs/research/backtest-phase-2.md](../docs/research/backtest-phase-2.md)); điểm chống chịu, phát hiện đổi hành vi, LP phân bổ, phân cụm, embedding để phase sau.

Mô hình và kỹ thuật ML/thống kê (phần số, không phải LLM): dự báo chi theo hũ (hurdle tự viết bằng numpy làm mặc định; StatsForecast chỉ làm baseline; Chronos-2 đề xuất để ngoài MVP, chưa chốt), adaptive conformal inference tự viết, mô phỏng Monte Carlo có tương quan, điểm chống chịu (Spend/Save/Borrow/Plan), phát hiện thay đổi hành vi (PELT/ruptures theo tuần; CUSUM/PageHinkley tự viết để "nghi"; bỏ ADWIN), z bền MAD cho khoản lớn (bỏ PyOD), quy hoạch tuyến tính phân bổ hũ bằng `scipy.optimize.linprog` (bỏ PuLP), phân cụm hồ sơ hành vi, embedding cho phân loại (chuẩn hóa chuỗi trước khi nhúng).

- Proposal: §11 (bảng ML và thống kê), §10.4 (batch đêm), §14 (StatsForecast/Darts, ruptures, scikit-learn; Chronos-2 trên SageMaker và PyOD không còn trong bộ tối thiểu).
- Tính năng: F1, F2, F4, F5, F7. Chạy trong pipeline [../pipelines/](../pipelines/README.md) và qua tool `forecast___*`, `planner___*`.
- Cần tra paper/tài liệu trước khi cài: [../docs/references/links.md](../docs/references/links.md).
- Số đo, bộ tối thiểu và code thử (dữ liệu tổng hợp; StatsForecast cần container 332 MB; khoảng tổng 30 ngày phủ thiếu): [spike-ml-forecasting.md](../docs/research/spike-ml-forecasting.md).
## Giao diện

Hợp đồng giữa gói `yofina_ml` (luồng ML) và pipeline (luồng C: `pipelines/nightly`, `pipelines/event`, `gateway/tools/forecast`). Hai luồng code song song nên chữ ký, kiểu và bất biến dưới đây là cố định; đổi gì thì sửa ở đây, ở `contracts/ml/forecast_io.schema.json` và ở `ml/yofina_ml/` TRƯỚC. Kiểu dữ liệu thật: [`yofina_ml/types.py`](yofina_ml/types.py) (dataclass bất biến, chỉ thư viện chuẩn); chữ ký hàm: [`yofina_ml/api.py`](yofina_ml/api.py) (thân hàm cài ở [`forecast.py`](yofina_ml/forecast.py) từ phase 2 luồng B, chữ ký không đổi); chuyển JSON: [`yofina_ml/serde.py`](yofina_ml/serde.py); bộ kiểm bất biến: [`yofina_ml/contract.py`](yofina_ml/contract.py). Fixture: `contracts/fixtures/ml/`.

```python
from yofina_ml.api import forecast_user, update_forecast
from yofina_ml.types import ForecastInputs, ForecastResult

def forecast_user(inputs: ForecastInputs) -> ForecastResult: ...
def update_forecast(inputs: ForecastInputs, previous: ForecastResult, jar_codes: Sequence[str]) -> ForecastResult: ...
```

### Quy ước

- Thuần hàm: cùng `inputs` (có `config.seed`) cho cùng kết quả; không I/O, không đọc đồng hồ hệ thống (mọi "hôm nay" là `inputs.app_date`, ADR-0003), không đọc cấu hình. Chỉ `numpy` và `scipy` (không torch, không StatsForecast: Lambda đóng zip, không Docker). `config.seed` là hạt gốc: hạt của từng hũ suy ra từ (seed, ngày gốc, mã hũ). `seed = None` vẫn tất định (coi như 0) và `run.seed` ghi None; pipeline nên đặt seed theo người dùng.
- Tiền là `int` VND. Ngày là `datetime.date` mô phỏng. Ngày dự báo đầu tiên là `app_date + 1`; `horizon_days` từ 1 đến 90 (sản phẩm dùng 30).
- Mọi ngưỡng đi vào qua `ForecastConfig` (pipeline đọc từ cấu hình); ML không gắn cứng ngưỡng. Giá trị mặc định trong dataclass chỉ để dev và test.

### Đầu vào (`ForecastInputs`): pipeline dựng, ML chỉ đọc

| Trường | Ý nghĩa và nguồn |
|---|---|
| `app_date`, `horizon_days` | Ngày mô phỏng hôm nay (`yofina_core.clock.app_today`) và số ngày dự báo |
| `next_payday`, `payday_dates` | `yofina_core.clock.next_payday` và `payday_dates(payday_day, app_date, app_date + horizon)` |
| `payday_day` | TÙY CHỌN (thêm ở phase 2 luồng B, tương thích ngược): ngày lương hằng tháng 1..31 (`yofina_core.clock`). ML dùng để biết mỗi ngày lịch sử nằm ở nửa đầu hay nửa sau kỳ lương. Vắng thì suy ra từ `next_payday.day` (sai chỉ khi ngày lương kế tiếp bị kẹp cuối tháng ngắn). Pipeline nên luôn truyền |
| `jars[]` | Chỉ hũ `spending`, `saving`, `obligation` (hũ hệ thống không được dự báo); một `JarInput` mỗi hũ |
| `JarInput.balance_vnd` | Số dư hũ hiện tại (`app_list_jars`) |
| `JarInput.daily_spend_vnd`, `history_start` | Chi tiêu mỗi ngày từ `history_start` tới `app_date - 1`, cũ tới mới, KHÔNG thủng ngày (ngày không chi là 0). Nguồn: hàm DB `app_get_daily_spend(user, from, to)` (chỉ chi trừ tiền hũ, không gắn nghĩa vụ: khoản trả theo lịch đã nằm ở `outflows`, tính hai lần là sai). `history_start` là ngày có dữ liệu sớm nhất của người dùng, không lùi xa hơn một cửa sổ cấu hình |
| `JarInput.inflows` | Phần lương của hũ tại mỗi ngày lương trong horizon: `yofina_core.wallet.split_amount(lương đã khai, tỷ lệ các hũ người dùng)` (`kind` `salary`) |
| `JarInput.outflows` | Nghĩa vụ đang hoạt động trả bằng hũ này, đã mở rộng chu kỳ trong horizon (`kind` `obligation`, có `amount_min_vnd`/`amount_max_vnd` nếu khai theo khoảng, `ref_id` là `obligation_id`). Nghĩa vụ quá hạn tính vào `app_date + 1`. Nghĩa vụ chưa có hũ trả gán cho hũ `obligation` đầu tiên theo `sort_order`; không có hũ đó thì bỏ và ghi `unassigned_obligations` vào tham số của lần chạy. Luật mở rộng chu kỳ (`weekly` +7 ngày, `monthly` theo `due_day` kẹp cuối tháng, `yearly` +1 năm, `once`) cài ở pipeline, ML không biết chu kỳ |
| `coverage` | `CoverageInputs` (lương đã nhận, chi tiêu đã ghi, tổng số dư đầu cửa sổ và hiện tại, mọi hũ kể cả hệ thống) để ML tính độ phủ dữ liệu. Vắng thì `data_coverage` là None |
| `config` | `ForecastConfig`: `n_paths`, `seed`, `cold_start_min_days`, ngưỡng `short_threshold`/`tight_threshold`, `probability_enabled`, ngưỡng nhóm tin cậy, `rho`, `aci_gamma`, `extra` |

### Đầu ra (`ForecastResult`) và ánh xạ sang bảng

| Kiểu | Bảng (migration 0006) | Ghi chú |
|---|---|---|
| `RunMeta` | `forecast_runs` | Pipeline thêm `id`, `user_id`, `computed_at`, `trigger`, `parent_run_id`, `source_event_id`. Test `tests/unit/test_contracts_ml.py` khóa tên cột khớp tên trường |
| `JarSummary` | `forecast_jar_summaries` (+ `run_id`, `user_id`) | `p_shortfall` None khi và chỉ khi `show_probability` sai (CHECK của DB) |
| `DayQuantiles` | `forecasts` (+ `run_id`, `user_id`, `jar_code`; `date` là cột `day`) | Phân vị chi tiêu NGÀY (>= 0) và phân vị SỐ DƯ cuối ngày (đã tính nghĩa vụ và lương, có thể âm), mỗi nhóm P10 <= P50 <= P90 |

Khối `forecast_timeline` được dựng từ chính các hàng này bằng `yofina_core.blocks.build_forecast_timeline` (không qua ML).

### Bất biến mà `check_result(inputs, result)` kiểm (đầu ra của `forecast_user` phải đạt)

- `jars` cùng tập và thứ tự với đầu vào; mỗi hũ đúng `horizon_days` dòng ngày liên tiếp từ `app_date + 1`.
- Phân vị chi tiêu `>= 0` và tăng dần; phân vị số dư tăng dần.
- `start_balance_vnd` bằng số dư đầu vào; `payday_date = next_payday`; `days_to_payday = (next_payday - app_date).days`.
- `run.history_days` = số ngày lịch sử lớn nhất của các hũ; `run.is_initial_estimate` đúng khi `history_days < config.cold_start_min_days`; khi đó `confidence_label` và mọi `confidence_band` là `low`, mọi hũ `show_probability` sai.
- `p_shortfall` là tỷ lệ 0..1; `status` suy từ `p_shortfall` bằng hai ngưỡng (`short` nếu `>= short_threshold`, `tight` nếu `>= tight_threshold`, còn lại `ok`) khi có xác suất; `show_probability` đúng chỉ khi `config.probability_enabled`, không phải ước lượng ban đầu, và hũ đủ ngưỡng lịch sử của loại chuỗi (BR-31, xem "Hiệu chỉnh tổng nhiều ngày").
- `series_kind = cold_start` đúng với hũ có ít lịch sử hơn `cold_start_min_days`.
- `runout_date` (nếu có) nằm trong horizon.

### Ngữ nghĩa các đại lượng

- `p_shortfall`: xác suất số dư hũ xuống dưới 0 ít nhất một ngày từ `app_date + 1` tới trước `next_payday` (hoặc hết horizon nếu ngày lương xa hơn). `p_shortfall_se`: sai số chuẩn Monte Carlo.
- `status` luôn được tính (kể cả khi `show_probability` sai, từ xác suất nội bộ) để màn hình vẫn có đủ/sát/hụt; chỉ con số phần trăm bị giấu.
- `runout_date`: ngày đầu tiên số dư P50 chạm 0 hoặc thấp hơn trong horizon; None nếu không cạn.
- `data_coverage` mặc định `clamp((spend + balance_end - balance_start) / income, 0, 1)` (xem `CoverageInputs`); luồng ML có thể tinh chỉnh, nhưng phải ghi công thức vào `RunMeta.params`.
- Nhóm tin cậy `confidence_band` / `confidence_label`: do ML quyết từ số ngày lịch sử, độ phủ dữ liệu và độ phủ khoảng đo trên backtest (ngưỡng ở `ForecastConfig`); `low` bắt buộc với ước lượng ban đầu.
- `RunMeta.params`: JSON thuần ghi chẩn đoán (ρ đã chọn, hệ số nới khoảng, γ của ACI, tên bộ sinh backtest...).

### `update_forecast` (đường sự kiện, dưới 1 phút)

Tính lại Monte Carlo cho các hũ trong `jar_codes` trên phân phối chi tiêu ngày đã có trong `previous` (không huấn luyện lại model, không chạy lại ACI) với số dư, nghĩa vụ và lương mới trong `inputs`. Phân phối được đọc từ `previous.run.params["jar_state"][mã_hũ]` (xem "Cài đặt"): pipeline phải lưu và đọc lại nguyên `forecast_runs.params` (jsonb) để `previous` đầy đủ; thiếu thì ML rơi về dựng biên từ ba phân vị chi tiêu ngày P10/P50/P90 (kém chính xác hơn, nhất là với hũ thưa). Cùng đầu vào thì kết quả y hệt `forecast_user`; đổi số dư thì số dư dịch đúng bằng chênh lệch (cùng dãy ngẫu nhiên). Trả `ForecastResult` chỉ gồm các hũ đó (theo thứ tự `jar_codes`); `check_result(..., subset=True)` kiểm. Hũ không có trong `previous` thì `KeyError` (pipeline rơi về `forecast_user` đầy đủ). Pipeline ghi một `forecast_runs` mới với `trigger = event`, `parent_run_id` trỏ lần chạy `previous`, chỉ có dòng cho các hũ đã tính; hàm DB `app_get_forecast_summaries` lấy "lần chạy mới nhất có chứa hũ" nên các hũ khác vẫn dùng dự báo cũ.

### Cài đặt (phase 2, luồng B)

Báo cáo đo thật, phương pháp và giới hạn: [docs/research/backtest-phase-2.md](../docs/research/backtest-phase-2.md). Cài đặt chỉ phụ thuộc `numpy` và `scipy` (Python 3.12 và 3.13); `backtest/` và `synth/` là công cụ đo trên máy, không được import từ mã sản phẩm (có test kiểm).

| Module (`yofina_ml/`) | Việc |
|---|---|
| `forecast.py` | Thân của `forecast_user` và `update_forecast` (api.py chỉ gọi vào đây) |
| `models.py`, `marginals.py` | `ForecastModel`: `hurdle_calendar` (mặc định), `seasonal_naive` (baseline, chọn bằng `config.extra["model"]`), `cold_start_rules`; mỗi mô hình fit thành một phân phối biên theo ngày (`ppf`, `state()` JSON) |
| `aci.py` | ACI tự viết theo mức phân vị, một alpha cho mỗi nhóm horizon 1-7 / 8-14 / 15+, kẹp alpha; dựng lại dòng thời gian bằng backtest rolling-origin nội bộ trên lịch sử của hũ |
| `montecarlo.py` | (không còn nhập `scipy.signal`: bộ lọc AR(1) là vòng lặp numpy cho kết quả y hệt từng bit, giảm khởi động nguội trên Lambda khoảng 1,8 giây) Monte Carlo số dư: copula Gaussian AR(1) cho hũ dày, hurdle trực tiếp (xác suất có chi lấy từ Beta posterior) cho hũ thưa, hệ số mức chung, lịch lương và nghĩa vụ tất định; hạt giống tất định theo (seed, ngày gốc, mã hũ) và tách dòng ngẫu nhiên (common random numbers) |
| `quality.py` | Độ phủ dữ liệu, nhãn tin cậy, trạng thái đủ/sát/hụt |
| `calibration/` | Tham số hiệu chỉnh do backtest sinh (`default.py`, KHÔNG sửa tay) và cách ghi đè |
| `params.py` | Hằng số thuật toán (`MLParams`), ghi đè bằng `config.extra["ml"]` |
| `synth/`, `backtest/` | Hai họ bộ sinh dữ liệu tổng hợp và khung backtest; chạy `uv run scripts/ml_backtest.py --help` |

**Chọn mô hình theo số ngày lịch sử của TỪNG hũ**: dưới `cold_start_min_days` thì `cold_start_rules` (luật + trung bình nhóm: chi trung bình mỗi ngày = tỷ lệ chi của loại hũ x phần lương của hũ / 30, pha với dữ liệu của hũ theo sức nặng 14 ngày; kết quả `series_kind = cold_start`, nhãn Thấp); từ ngưỡng thì `hurdle_calendar`. `run.model` là mô hình của đa số hũ (`cold_start_rules` khi cả tài khoản là ước lượng ban đầu); mô hình từng hũ ở `run.params["jar_models"]`.

**Ngày cạn** (`runout_date`) là ngày đầu tiên số dư P50 <= 0. Lý do chọn: khớp đường P50 người dùng nhìn thấy trên biểu đồ, đơn điệu và không phụ thuộc cách đếm theo đường (trung vị ngày cạn trong số các đường có cạn thiên lệch vì chỉ tính các đường đã cạn, và không tồn tại khi đa số đường không cạn).

**Hiệu chỉnh tổng nhiều ngày** (`calibration/default.py`): `rho` của copula, `level_sigma` của hệ số mức chung, và `probability_ok` cho từng loại chuỗi (`dense`, `sparse`, `cold_start`). `probability_ok` chỉ đúng khi backtest giữ-ra-ngoài cho độ phủ khoảng 80% của số dư 30 ngày nằm trong [0,75; 0,85] ở từng họ bộ sinh và xác suất hụt có kỹ năng hơn tần suất chung. Engine chỉ phát `p_shortfall` khi `config.probability_enabled` VÀ `probability_ok` của loại chuỗi VÀ hũ có từ `probability_min_history_days` ngày lịch sử của loại chuỗi đó (BR-31: dải hũ thưa chỉ đạt độ phủ khi đủ lịch sử, số đo và ngưỡng ở [docs/research/backtest-final.md](../docs/research/backtest-final.md), chọn và ghi bằng `uv run scripts/ml_history_gate.py --write-calibration`) VÀ không phải ước lượng ban đầu; dưới ngưỡng thì vẫn có `status` và `confidence_band`, và hũ đó không lên nhóm Cao. `yofina_ml.calibration.calibrated_config()` trả `ForecastConfig` với `probability_enabled` đặt theo kết quả backtest (pipeline có thể dùng làm gốc rồi ghi đè `seed`, `n_paths`).

**`RunMeta.params`** (JSON thuần, lưu vào `forecast_runs.params`): `calibration` (rho, level_sigma, probability_ok đã dùng), `aci_gamma`, `aci_alpha_target`, `payday_day`, `data_coverage_formula`, `probability_window_days`, `ml_version`, `jar_models`, và `jar_state[mã_hũ]` = `{model, series_kind, aci_alpha, marginal}` (phân phối biên đã fit, vài trăm số nguyên mỗi hũ; `update_forecast` đọc lại từ đây).

**Pipeline dựng `ForecastInputs` thế nào cho đúng** (ngoài bảng "Đầu vào"):
- `daily_spend_vnd` và `history_start`: ML chỉ dùng tối đa 180 ngày gần nhất để fit và 150 ngày để chạy ACI, nên lấy tới khoảng 330 ngày là đủ; ít hơn vẫn chạy (đầu ra ghi `history_days`).
- `payday_day`: luôn truyền (số ngày lương khai báo), đừng để ML suy ra.
- `config.seed`: một số nguyên cố định theo người dùng (ví dụ lấy từ băm `user_id`); hạt của từng hũ suy ra từ (seed, `app_date`, mã hũ). Muốn so kịch bản what-if với kịch bản gốc (phase 3) thì GIỮ NGUYÊN `seed` và `app_date`, chỉ đổi số dư, lịch lương hoặc nghĩa vụ trong `inputs`: dãy ngẫu nhiên giống hệt nên chênh lệch không bị nhiễu mẫu.
- `config.n_paths`: 10.000 cho batch đêm, 5.000 cho đường sự kiện và what-if (thời gian đo ở báo cáo backtest).
- `config.probability_enabled`: lấy từ `calibrated_config()` (hoặc từ cấu hình của pipeline); ML tự gác thêm bằng `probability_ok`.
- `update_forecast`: `previous` phải dựng từ lần chạy MỚI NHẤT có chứa hũ đó, kèm NGUYÊN `forecast_runs.params`. Hai hũ có thể nằm ở hai lần chạy khác nhau (lần chạy theo sự kiện chỉ có vài hũ): gọi từng hũ với `previous` của hũ đó, hoặc gộp `params["jar_state"]` của các lần chạy vào một `previous`. Kết quả đọc `run.model` của `previous`; nếu từ lúc đó tài khoản đã vượt ngưỡng khởi đầu lạnh thì nên gọi `forecast_user` đầy đủ.

### Phân công và kiểm

- Luồng ML sở hữu `ml/yofina_ml/` (thân hàm ở `forecast.py`, `models.py`, `aci.py`, `montecarlo.py`...), `tests/unit/ml/`, `scripts/ml_backtest.py`; **không đổi** `types.py`, `contract.py`, `serde.py`, `api.py` (chữ ký) và schema mà không báo người điều phối. (Một lần đổi đã báo: thêm trường tùy chọn `ForecastInputs.payday_day`.)
- Luồng pipeline dựng `ForecastInputs` từ DB và gọi `forecast_user`/`update_forecast`; test của luồng này thay hai hàm bằng bản giả và dùng `contract.check_inputs` để kiểm đầu vào do mình dựng.
- Kiểm hợp đồng: `uv run pytest tests/unit/test_contracts_ml.py`.
