# Phase 2 — Ví mô phỏng và dự báo (F1)

Ngày dự kiến: 25–28/11/2026. Kế hoạch tổng: [master-plan.md](../master-plan.md). Điều kiện vào: phase 1 đạt tiêu chí hoàn thành; đọc mục "Kết quả thực hiện" của [phase 1](phase-1-nen-va-lat-doc.md) để biết chỗ đã lệch.

## Mục tiêu

App dùng được như một ví: khai báo lương và hũ, xem hũ, chuyển tiền, khai nghĩa vụ, mua bằng hạn mức trả sau mô phỏng. Mỗi hũ có dự báo 30 ngày (P10/P50/P90), ngày cạn dự kiến và xác suất hụt trước kỳ lương, tính mỗi đêm và tính lại khi có giao dịch. **Cảnh 1 của demo chạy được trên app thật**: mở app thấy hũ Ăn uống cạn 23/11, còn 12 ngày tới kỳ lương.

## Phạm vi

FR1 (hồ sơ, hũ, sổ cái, chia lương, "Tiền vào khác"), FR3 (dự báo), FR4 (nghĩa vụ, trả sau tự sinh). Phân loại giao dịch ở phase này chỉ có bước 0 (theo loại giao dịch) và người dùng tự chọn hũ nguồn; phân hũ tự động đầy đủ nằm ở phase 4. Kiểm tra trước khi chuyển (thẻ đủ/sát/hụt) nằm ở phase 3: ở phase này luồng chuyển tiền đi thẳng T2 → T4.

## Đọc trước

| Luồng | Đọc |
|---|---|
| Mọi luồng | [overview.md](../../architecture/overview.md) mục Dữ liệu, ML, Mô hình dữ liệu, Ba nhịp chạy; [proposal-summary.md](../../proposal/proposal-summary.md) §4 (đầu vào khai báo), §7, §10.4 |
| A | [spike-aurora-data-api.md](../../research/spike-aurora-data-api.md) §4, §5; proposal-summary §9 bảng tool `ledger.*` |
| B | [spike-ml-forecasting.md](../../research/spike-ml-forecasting.md) §1, §3, §5, §6, §9, §10; mã `spikes/ml-forecasting/` (`gen_data.py`, `forecasters.py`, `s5_aci.py`, `s6_mc.py`, `s3_backtest.py`); [ml-forecasting.md](../../research/ml-forecasting.md) phần dự báo, conformal, Monte Carlo |
| C | [aws-data-events-infra.md](../../research/aws-data-events-infra.md) §3.2–§3.4; skill `aws-core:aws-serverless` |
| D | [figma-ui-design.md](../../research/figma-ui-design.md) §4, §5, §6, §8.2; [spike-frontend-stack.md](../../research/spike-frontend-stack.md) §2, §3, §6, §7; [frontend-fintech-ui.md](../../research/frontend-fintech-ui.md). Figma node: C1 `17:2`, `17:289`; C2 `17:489`, `17:673`, `17:801`, `17:925`; T1 `19:787`, T2 `19:872`, T4 `19:1158`, T5 `19:1217`; O1 `25:2327`, O2 `25:2391`, O3 `25:2508`; S3 Hoạt động `31:2830`; component JarIcon `7:46`, JarCard `7:130`, JarRow `14:236`, ProactiveCard `14:176`, MiniTimeline `7:146`, TxRow `14:264`, ForecastBlock `7:248`, Numpad `14:450`, AppBar `14:457` |

## Bước 0 — Hợp đồng

- Migration `0002`: `obligations`, `category_rules`, `forecasts` (phân vị theo hũ và ngày, tên model, mã lần chạy, thời điểm tính), `forecast_runs` (kèm độ phủ dữ liệu, số ngày lịch sử, nhãn tin cậy), `credit_lines` (hạn mức trả sau mô phỏng), cột mục tiêu và hạn của hũ, cột luật chia lương, ô "Tiền vào khác" và hũ tạm "Chưa phân loại".
- `contracts/tools/`: đủ 9 tool `ledger` theo [overview.md](../../architecture/overview.md#danh-mục-tool-9); `forecast___get_forecast`.
- `contracts/rest/openapi.yaml`: hồ sơ, hũ (tạo, sửa, luật chia), giao dịch (danh sách, tạo trên ví mô phỏng), chuyển tiền cho người nhận, nghĩa vụ (CRUD), xác nhận lương về, gán "Tiền vào khác" vào hũ, dự báo theo hũ, tổng quan.
- `contracts/blocks/`: `forecast_timeline` (đường P50, dải P10–P90, mốc nghĩa vụ và lương, ngày cạn, xác suất hụt hoặc nhóm tin cậy, độ phủ, độ tươi), `proactive_card`.
- Bảng tra bước 0: loại giao dịch → hũ (`db/seed/tx_type_map.sql`).

## Luồng A — Sổ cái và REST đầy đủ

Sở hữu: `gateway/tools/ledger/`, `db/`, phần HTTP API của stack `YofinaTools`.

- Cài đủ 9 tool `ledger` và các endpoint REST trên cùng mã. Mọi thao tác ghi đi qua token xác nhận như phase 1 (onboarding lần đầu cũng là thao tác của người dùng trên màn hình, gọi REST có token).
- Chia lương: lương về khớp số đã khai thì một chạm xác nhận rồi chia vào hũ theo luật; lệch nhiều thì hỏi có cập nhật lương không. Tiền vào khác lương nằm ở ô riêng, không tính thu nhập.
- Trả sau mô phỏng: mua bằng hạn mức sinh một `obligation` (gốc + phí 33.000 ₫ nếu tháng đó có giao dịch, đến hạn ngày 5). Biểu phí để trong bảng có cấu trúc `fee_schedules`, kèm nguồn và ngày hiệu lực.
- Sau mỗi giao dịch đã ghi: phát sự kiện `transaction.recorded` lên EventBridge bus `yofina-bus` (luồng C nghe).
- Khóa khử trùng (băm ngày, số tiền, đối tác) trên `transactions`.
- Cập nhật Cedar cho các tool mới (đọc: khớp người dùng; ghi: thêm hạn mức và `confirm_token`).

## Luồng B — ML: dự báo và Monte Carlo

Sở hữu: `ml/yofina_ml/`, `data/personas/`, `tests/unit/ml/`.

- `ForecastModel.predict(lịch sử, lịch biết trước, horizon) -> bảng phân vị`. Hai cài đặt: hurdle theo lịch (ô cuối tuần × nửa đầu kỳ lương, bootstrap số tiền) và seasonal naive (baseline). Cổng khởi đầu lạnh: dưới khoảng 21 ngày dùng luật và trung bình nhóm persona, ghi rõ "ước lượng ban đầu".
- ACI tự viết (γ 0,005–0,01, kẹp α) cho khoảng theo ngày.
- Monte Carlo số dư hũ: numpy vector hóa, copula Gaussian AR(1) cho hũ dày, mô phỏng hurdle trực tiếp cho hũ thưa, cộng lịch nghĩa vụ và lương tất định. Đầu ra: phân vị số dư theo ngày, ngày cạn, xác suất hụt trước kỳ lương, sai số chuẩn.
- **Xử lý khoảng tổng 30 ngày phủ thiếu** (spike đo 0,48–0,61): chọn ρ và hệ số nới theo độ phủ trên backtest rolling-origin; mục tiêu độ phủ khoảng 80% của tổng 30 ngày nằm trong 0,75–0,85 trên ba persona. Nếu không đạt, hợp đồng khối trả nhóm Cao/Vừa/Thấp thay cho phần trăm và ghi rõ trong file phase.
- Độ phủ dữ liệu (phần thu nhập giải thích được bằng chi tiêu đã ghi và số dư) và độ tươi.
- Bộ sinh ba persona, tất định theo seed, có điểm gãy lối sống cài sẵn: `minh` (hiệu chỉnh để hũ Ăn uống cạn đúng 23/11 mô phỏng, số dư và tỷ lệ chia theo bảng số Figma, 47 ngày dữ liệu), `lan` (sinh viên làm thêm, nhiều tháng lịch sử), `khoa` (18 ngày dữ liệu). **Thêm một bộ sinh khác họ** (không phải hurdle-lognormal, ví dụ theo phiên mua và giỏ hàng) để backtest không tự khen mình; báo cáo cả hai.
- Báo cáo backtest `docs/research/backtest-phase-2.md`: pinball so với seasonal naive, độ phủ theo ngày và tổng 30 ngày, theo hũ dày và thưa.

## Luồng C — Pipeline đêm và cập nhật theo sự kiện

Sở hữu: `pipelines/nightly/`, `pipelines/event/`, `gateway/tools/forecast/`, phần tương ứng của `YofinaTools`.

- Lambda `yofina-forecast-batch` (zip, numpy + scipy): với một người dùng, đọc lịch sử và lịch đã khai, chạy dự báo + ACI + Monte Carlo, ghi `forecasts` và `forecast_runs`.
- Step Functions `yofina-nightly`: liệt kê người dùng → Map → Lambda trên; EventBridge Scheduler 02:00 giờ Việt Nam. Dùng danh tính dịch vụ kèm `user_id`, đi qua cùng lớp DB có RLS.
- Đường sự kiện: `yofina-bus` → SQS (có DLQ) → Lambda `yofina-on-transaction`, idempotent theo `event_id` (DynamoDB): chỉnh nhanh dự báo của hũ liên quan (chạy lại Monte Carlo trên phân vị đã có với số dư mới). Alarm khi DLQ có tin.
- `demo/reset` gọi đồng bộ dự báo cho người dùng đó để mở app là có số.
- Tool `forecast___get_forecast` (đọc bảng; quá hạn độ tươi thì tính lại trước khi trả) và endpoint REST tương ứng; target `forecast` trên Gateway kèm Cedar.

## Luồng D — Frontend: các màn hình ví và dự báo

Sở hữu: `frontend/`.

- Tổng quan (C1 hai frame): thẻ số dư, hành động nhanh, thẻ chủ động (một việc, có "Hỏi vì sao", "Để sau", "Ít nhắc loại này"), dòng thời gian thu gọn, dải thẻ hũ, "Gần đây".
- Danh sách hũ và Chi tiết hũ (C2): hũ thủy tinh SVG có mực nước và vạch "mực dự báo"; biểu đồ 30 ngày bằng Recharts (dải P10–P90, đường P50 màu `accent/blue`, mốc nghĩa vụ và lương, điểm cạn), giao dịch gần đây. Component `ForecastBlock` dùng chung cho màn hình và chat qua registry.
- Chuyển tiền T1, T2, T4, T5 (bàn phím số, chọn hũ nguồn, xem lại, biên nhận); trả bằng hạn mức trả sau mô phỏng; Hoạt động (danh sách giao dịch).
- Onboarding O1–O3: chỉ lương và ngày nhận là bắt buộc.
- Màn nghĩa vụ (khai tiền trọ, hóa đơn, thuê bao, khoản vay); ô "Tiền vào khác" và gán vào hũ; xác nhận lương về.
- Trạng thái tải (skeleton), lỗi, rỗng cho mọi màn; ba trạng thái đủ/sát/hụt luôn kèm biểu tượng và chữ; định dạng tiền theo [figma-ui-design.md §3](../../research/figma-ui-design.md).
- Agent (sửa nhỏ, cùng luồng này phối hợp với người điều phối): đường nhanh thêm ý định "dự báo hũ X" trả khối `forecast_timeline`.

## Tiêu chí hoàn thành

1. Đặt lại tài khoản `minh` rồi mở app: thẻ chủ động và Chi tiết hũ Ăn uống báo cạn ngày 23/11 mô phỏng, lương 5/12; số dư bảy hũ khớp bảng số Figma. Số nào engine cho khác Figma thì ghi vào "Kết quả thực hiện".
2. Tạo một giao dịch 200.000 ₫ từ hũ Ăn uống: số dư đổi ngay, trong vòng 1 phút ngày cạn trên Chi tiết hũ cập nhật.
3. Chạy tay state machine `yofina-nightly`: thành công cho cả sáu tài khoản, `forecast_runs` có bản ghi mới.
4. Backtest: hurdle có pinball thấp hơn seasonal naive trên cả hai bộ sinh; độ phủ tổng 30 ngày đã báo cáo, đạt 0,75–0,85 hoặc đã chuyển sang nhóm Cao/Vừa/Thấp.
5. Tài khoản `khoa` (18 ngày): dự báo có nhãn "ước lượng ban đầu" và độ phủ thấp.
6. Mua 300.000 ₫ bằng hạn mức trả sau mô phỏng: sinh nghĩa vụ 333.000 ₫ đến hạn ngày 5, hiện thành mốc trên biểu đồ.
7. Onboarding một tài khoản trắng chỉ với lương và ngày nhận rồi vào được Tổng quan.
8. Trong chat, "hũ ăn uống còn trụ được bao lâu" trả khối `forecast_timeline` cùng số với màn Chi tiết hũ.
9. Gửi trùng một sự kiện giao dịch: số dư và dự báo không bị tính hai lần.
10. Luồng 3 truy vấn đọc cho Tổng quan: p95 dưới 300 ms đo từ Lambda (ghi số).

## Cách kiểm (người điều phối)

- Chạy test unit và tích hợp; chạy lại backtest từ dòng lệnh và đọc báo cáo.
- Đi cảnh 1 theo [figma-ui-design.md §8.2](../../research/figma-ui-design.md) trên URL Amplify ở khổ 390×844, so từng màn với ảnh chụp frame Figma.
- Thực hiện tiêu chí 2, 6, 7 bằng tay trên app; tiêu chí 3, 9 bằng lệnh gọi AWS; đối chiếu số với Aurora.

## Kết quả thực hiện

Đóng ngày 2026-11-22 (chiều). Ví mô phỏng và dự báo chạy thật: Tổng quan, hũ, chi tiết hũ có biểu đồ 30 ngày, chuyển tiền, Trả sau (mô phỏng), nghĩa vụ, tiền vào, onboarding; dự báo tính mỗi đêm (`yofina-nightly`), tính lại theo sự kiện (SQS) và khi đặt lại demo; chat trả khối `forecast_timeline` qua Gateway. Cảnh 1 của demo chạy trên app thật.

Người điều phối tự kiểm trên trình duyệt: bản build chạy ở `localhost:5173` nối backend thật, khung 390x844, tài khoản `minh`, `khoa`, `lan` và một tài khoản trắng tạm. Test cùng ngày: 1156 unit, 126 integration (11 phút), 364 test frontend (xem lưu ý về chạy song song ở dưới).

### Tiêu chí hoàn thành

| # | Tiêu chí | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | Đặt lại `minh`: thẻ chủ động và Chi tiết hũ Ăn uống báo cạn 23/11, lương 5/12; số dư bảy hũ khớp Figma | **Đạt** | Bấm "Đặt lại dữ liệu" (7 hũ, 166 giao dịch, ngày mô phỏng 21/11/2026). Thẻ chủ động: "Hũ Ăn uống dự kiến cạn ngày 23/11 · Còn 380.000 ₫, cạn xong còn 12 ngày nữa mới tới kỳ lương 05/12. Xác suất hụt khoảng 100%." Chi tiết hũ: cạn 23/11, lương 05/12, nhóm Vừa, 47 ngày. Bảy hũ 380.000 / 640.000 / 450.000 / 760.000 / 1.800.000 / 2.700.000 / 1.000.000 ₫ (tổng 7.730.000 ₫) khớp Figma. Khác Figma: tổng ví 7.900.000 ₫ thay vì 8.260.000 ₫ vì "Đã chi, chưa xếp hũ" là −180.000 ₫ (quyết định hợp đồng số 2, giữ) |
| 2 | Giao dịch 200.000 ₫ từ Ăn uống: số dư đổi ngay, trong 1 phút ngày cạn cập nhật | **Đạt** | Trên app: chuyển 200.000 ₫ cho người nhận, trả từ hũ Ăn uống, qua màn xem lại có preview của server (380.000 → 180.000 ₫) rồi xác nhận. Biên nhận và Chi tiết hũ hiện 180.000 ₫ ngay; dự báo được tính lại trong 14 giây ("Cập nhật" đổi từ 15:05 sang 15:07). Ngày cạn vẫn 23/11 vì hũ trả nghĩa vụ "Tiền cơm văn phòng" 300.000 ₫ đúng ngày đó, nên cạn sớm hơn là không thể. Integration test `test_giao_dich_200k_cap_nhat_du_bao_hu_an_uong_trong_60_giay` kiểm dự báo mới có `start_balance_vnd` 180.000 ₫ trong 60 giây, ngày cạn không muộn hơn 23/11, và chỉ hũ liên quan được tính lại |
| 3 | Chạy tay `yofina-nightly`: thành công cho cả sáu tài khoản, `forecast_runs` có bản ghi mới | **Đạt** | Execution `test-de2c809cae83` (lần chạy integration của phiên này) SUCCEEDED trong 4,5 giây, output `{"total": 6, "ok": 6, "skipped": 0, "failed": 0}`; test `test_nightly_chay_tay_thanh_cong_cho_ca_sau_tai_khoan` kiểm thêm `forecast_runs` có dòng `trigger = 'nightly'` mới cho từng người |
| 4 | Backtest: hurdle có pinball thấp hơn seasonal naive trên cả hai bộ sinh; độ phủ tổng 30 ngày đạt 0,75–0,85 hoặc chuyển sang nhóm | **Đạt** | Chạy lại `uv run scripts/ml_backtest.py --all`, số khớp [backtest-phase-2.md](../../research/backtest-phase-2.md): pinball sản phẩm / seasonal naive 0,62 (họ hurdle-lognormal) và 0,60 (họ phiên mua); độ phủ P10–P90 số dư ngày 30 trên seed giữ ra ngoài: hũ dày 0,80, hũ thưa 0,80 (gộp hai họ). Tham số hiệu chỉnh sinh lại giống hệt bản đã commit |
| 5 | `khoa` (18 ngày): nhãn "ước lượng ban đầu" và độ phủ thấp | **Lệch câu chữ, chấp nhận** | Chi tiết hũ và Tổng quan có "Ước lượng ban đầu · Mới có 18 ngày dữ liệu", nhóm tin cậy Thấp, "Chưa đủ cơ sở để nêu xác suất". **Độ phủ dữ liệu luôn 100%** vì ví mô phỏng khép kín (mọi khoản chi đều nằm trong sổ cái), nên không có "độ phủ thấp". Tín hiệu tin cậy thấp đi qua nhóm Thấp và nhãn ước lượng ban đầu. Độ phủ dưới 100% chỉ xuất hiện khi có dữ liệu ngoài ví (phase 5, nạp ảnh và tệp) |
| 6 | Mua 300.000 ₫ bằng Trả sau: nghĩa vụ 333.000 ₫ đến hạn ngày 5, hiện thành mốc trên biểu đồ | **Đạt, có điều kiện** | Trên app với `minh`: preview và biên nhận "Phải trả ngày 05/12: 1.000.000 → 1.300.000 ₫, trong đó phí dịch vụ 33.000 ₫; hạn mức 4.033.000 → 3.733.000 ₫". `minh` đã có nghĩa vụ Trả sau tháng này (phí đã tính) nên số cộng dồn vào nghĩa vụ có sẵn, đúng quyết định hợp đồng số 5. Mốc "Trả sau (mô phỏng) 05/12 −1.300.000 ₫" hiện trên biểu đồ hũ Nghĩa vụ. Ca tài khoản chưa có nghĩa vụ (sinh đúng 333.000 ₫) do integration test `test_wallet_rest` kiểm. **Chấp nhận**: tài khoản không có hũ loại `obligation` (như `lan`) thì nghĩa vụ Trả sau có trong danh sách nghĩa vụ nhưng không thành mốc trên biểu đồ hũ nào |
| 7 | Onboarding tài khoản trắng chỉ với lương và ngày nhận, vào được Tổng quan | **Đạt** | Tạo user Cognito tạm (chủ dự án cho phép), đăng nhập trên localhost: Tổng quan chuyển sang `/onboarding`; nhập lương 8.000.000 ₫ và ngày 20, bỏ qua bước chia hũ và chi phí cố định, vào Tổng quan với 7 hũ mặc định (0 ₫) và nhãn ước lượng ban đầu. Đã xóa user Cognito và mọi dòng DB của nó (DELETE `users`, cascade; còn 0 dòng). Integration test `test_onboarding_tai_khoan_trang_chi_voi_luong_va_ngay_nhan` cũng đạt |
| 8 | Chat "hũ ăn uống còn trụ được bao lâu" trả `forecast_timeline` cùng số với Chi tiết hũ | **Đạt** | Trên app: khối "Dự báo hũ Ăn uống · Cạn ngày 23/11", 12 ngày trước kỳ lương 05/12, khả năng hụt 100%, nhóm Vừa, độ phủ 100%, 47 ngày, cập nhật 15:08: trùng từng số với màn Chi tiết hũ đọc ngay sau đó. Câu trả lời của model: "cạn vào ngày 23/11, còn 12 ngày nữa đến ngày lương 05/12, xác suất hụt là 100%". Tải lại trang: hội thoại và khối phát lại đủ |
| 9 | Gửi trùng một sự kiện giao dịch: không tính hai lần | **Đạt** | Integration test (gửi lại cùng `event_id` hai lần, chờ 25 giây, số dư và `forecast_runs` không đổi; `POST /actions` trùng `client_ref` trả 409 `DUPLICATE_TRANSACTION`) |
| 10 | Luồng 3 truy vấn đọc cho Tổng quan: p95 dưới 300 ms đo từ Lambda | **Đạt** | `uv run scripts/measure_wallet.py`: `GET /overview` phía Lambda (trường `ms` của log `rest_request`) n=60, p50 17 ms, p95 18 ms, max 75 ms; phía máy gọi qua Internet p95 206 ms. Luồng ghi hai bước p95 609 ms (máy gọi), `POST /actions` phía Lambda p95 291 ms |

### Không hardcode, không giả lập

Mọi số trên màn hình đi từ Aurora qua REST hoặc tool; `npm run check:bundle` sạch (không mock, fixture, số persona hay bí mật trong bundle, 458 KB gzip). Câu chat do agent trên Runtime sinh ở lượt đó; số trong khối do tool `forecast___get_forecast` trả.

### Sửa khi đóng phase

- Thẻ chủ động ghi "còn 14 ngày tới kỳ lương" (tính từ hôm nay) trong khi kịch bản và chat ghi 12 ngày (từ ngày cạn tới lương). Sửa ở server (`proactive.py`): có ngày cạn thì ghi "cạn xong còn N ngày nữa mới tới kỳ lương". Đã deploy `YofinaTools`.
- Preview lương lệch ghi "+1.11%": đổi sang dấu phẩy thập phân (`wallet_writes.py`).
- Chi tiết hũ ở trạng thái "Sát" vẫn ghi "dự kiến đủ tới kỳ lương" (thấy trên `khoa`): câu tóm tắt của `ForecastBlock` thêm nhánh `tight`. Đã deploy Amplify.
- `cognito.live.test.ts` vỡ khi chưa có `frontend/.env.local` (Vitest vẫn chạy thân `describe` khi skip): chỉ tạo client khi bật.
- Test frontend: `testTimeout` 15 giây, chờ Recharts tải lười 15 giây.

### Lệch so với kế hoạch

- Tiêu chí 5: không có "độ phủ thấp" trên ví khép kín (xem bảng).
- Tiêu chí 6: số 333.000 ₫ chỉ đúng khi tài khoản chưa có nghĩa vụ Trả sau tháng đó; tài khoản không có hũ Nghĩa vụ thì không có mốc trên biểu đồ.
- Tổng ví `minh` 7.900.000 ₫ khác Figma 8.260.000 ₫ (quyết định hợp đồng số 2).
- Kiểm cảnh 1 trên bản build chạy ở localhost nối backend thật, không phải trên URL Amplify (người điều phối không gõ mật khẩu vào trang đã host). URL Amplify đã phục vụ đúng bundle mới (`index-BGUqVOtg.js`).
- Không dùng Docker: StatsForecast chỉ chạy trên máy trong báo cáo backtest.

### Chuyển sang phase sau

- `OFFER_EXPIRED` chưa tách khỏi `TOKEN_EXPIRED`.
- `GET /forecasts/{hũ hệ thống}` trả 503 `FORECAST_UNAVAILABLE` thay vì 404 (test tích hợp đang khóa hành vi này; đổi thì sửa hợp đồng và test cùng lúc).
- Chưa có preview cho sửa hồ sơ, `save_jars`, nghĩa vụ.
- Tài khoản mới 0 ₫ hiện thẻ "Hũ Ăn uống dự kiến cạn ngày 23/11 · Còn 0 ₫": nên có câu riêng cho hũ chưa có tiền.
- "Xác suất hụt khoảng 100%" khi nghĩa vụ lớn hơn số dư: đúng số nhưng nên ghi "gần như chắc chắn" thay vì 100%.
- Bước công cụ trong chat ghi "Đã đọc số dư các hũ" cho lời gọi dự báo; nhãn mốc trên biểu đồ chồng nhau ở mép trên; nút chat ở thanh dưới và các ô chọn nguồn tiền thiếu tên cho trình đọc màn hình.
- Chạy cả bộ test frontend song song trên máy chậm vẫn có ca chờ quá giờ (mã HEAD cũng vậy); chạy từng file đều xanh.
- Chat trên URL Amplify từ Chrome máy tính và Safari iPhone: vẫn chờ chủ dự án.

### Quyết định hợp đồng phase 2

Viết ngày 2026-11-22 bởi subagent làm "Bước 0 — Hợp đồng" (Claude Sonnet 5.5). Bốn luồng sau (A sổ cái và REST, B ML, C pipeline và tool forecast, D frontend) đọc mục này cùng [contracts/README.md](../../../contracts/README.md#phase-2-ví-mô-phỏng-và-dự-báo), [db/README.md](../../../db/README.md#schema-phase-2-0005-và-0006) và [ml/README.md](../../../ml/README.md#giao-diện). Mọi mục dưới đây là lựa chọn tự chốt (người điều phối đổi được khi duyệt); lý do ghi kèm. Migration 0005, 0006 và seed **chưa chạy trên Aurora**. (Mục "Bước 0" ở trên ghi "Migration `0002`" vì viết trước khi phase 1 dùng 0002 tới 0004; migration thật là `0005_wallet.sql` và `0006_forecast.sql`.)

**Dữ liệu**

1. **"Tiền vào khác" và "Chưa phân loại" là hai hũ hệ thống** (`jars.kind = 'system'`, `system_role`), không phải bảng riêng. Lý do: dùng lại số dư hũ, khóa ngoại của sổ cái, `move_between_jars` (gán Tiền vào khác vào hũ chính là chuyển từ hũ này), RLS và biên nhận; tổng số dư đơn giản là tổng mọi hũ. Hai hũ do `app_ensure_system_jars` tạo (không backfill trong migration để khỏi phụ thuộc việc master Aurora vượt RLS).
2. **Hũ Chưa phân loại được âm** (CHECK `jars_balance_check` có ngoại lệ). Lý do: khoản chi chưa xếp hũ đã thật sự ra khỏi ví và phải giảm tổng số dư ("vẫn bị trừ khỏi tổng số dư", proposal 10.3); không trừ hũ nào thì tổng hũ lệch tiền thật. `assign_jar` chuyển phần chi sang hũ được chọn. **Khác Figma**: bảng số Figma ghi +180.000 ₫ cho "Chưa phân loại" và tổng 8.260.000 ₫; theo hợp đồng này số dư hũ đó thường âm nên tổng của persona `minh` có thể ra số khác (ghi vào kết quả phase khi đo). Cần người điều phối chốt nếu muốn đúng Figma.
3. **`GET /jars` và tool `get_jar_balances` không gồm hũ hệ thống** (giữ hình dạng phase 1: 7 hũ, tổng 7.730.000 ₫ của persona `minh`). Hũ hệ thống ở `GET /overview` và `GET /jars/{jar_code}`.
4. **Nguồn trả `funding_source`** (`jar` hoặc `credit`) trên mỗi dòng sổ cái. Mua bằng Trả sau là chi tiêu (đếm vào hũ để thống kê) nhưng không đổi số dư hũ; tiền rời hũ khi trả nghĩa vụ. Lý do: số dư hũ là tổng dòng `jar`, nên dự báo số dư hũ không đếm hai lần.
5. **Trả sau**: một nghĩa vụ `bnpl` hoạt động mỗi ngày đến hạn (chỉ mục duy nhất một phần), ngày đến hạn là `credit_lines.due_day` (5) kế tiếp sau ngày mua; mua thêm cộng dồn gốc; phí 33.000 ₫ tính một lần mỗi nghĩa vụ (mỗi nghĩa vụ ứng với một tháng có giao dịch); `amount = principal + fee` bằng CHECK. Biểu phí ở `fee_schedules`, `effective_from` là ngày nguồn được ghi nhận (31/03/2026), không bịa thêm phí trả chậm khi chưa có nguồn. Hạn mức mặc định của tài khoản mới là cấu hình (SSM), seed persona đặt hạn mức riêng.
6. **Lương về là hai bước**: `record_transaction` (tiền vào, `tx_type = salary`) ghi vào Tiền vào khác và sinh `salary_events` `pending` (kèm `deviation_percent` và cờ hỏi cập nhật lương theo ngưỡng cấu hình `salary_deviation_ask_percent`); `confirm_salary` chia theo `split_percent` bằng `yofina_core.wallet.split_amount` (làm tròn xuống, dư vào hũ tỷ lệ lớn nhất) hoặc giữ ở Tiền vào khác. Dùng chung `split_amount` cho lịch lương của dự báo.
7. **Khử trùng** `dedupe_key` (sha256) duy nhất theo người dùng nhưng chỉ đặt khi có `client_ref` (hoặc dòng nạp tệp): hai khoản chi giống hệt không `client_ref` là hợp lệ.
8. **Không khóa ngoại `transactions.tx_type` tới `tx_type_map`**: để reset demo cũ (chưa biết `tx_type`) không vỡ khi bảng tra chưa seed; Lambda kiểm giá trị. **Quyền cột**: `transactions` thêm UPDATE chỉ cho cột phân loại và liên kết (số tiền, hũ nguồn trả, thời điểm vẫn bất biến), để `assign_jar` không cần dòng bù trừ.
9. **Dự báo**: `forecast_runs` (metadata cả lần chạy), `forecast_jar_summaries` (một dòng mỗi hũ mỗi lần chạy), `forecasts` (phân vị chi tiêu ngày và số dư theo ngày). Tóm tắt là bảng con, không phải jsonb, vì Tổng quan cần "lần chạy mới nhất của MỖI hũ" trong một truy vấn có chỉ mục và có kiểu (ngày cạn, xác suất, trạng thái); lần chạy theo sự kiện chỉ có dòng cho vài hũ. Mốc nghĩa vụ và lương không lưu (ghép lúc đọc). Ngày dự báo bắt đầu từ `origin_date + 1`; số dư dự báo được âm.

**Ghi (xác nhận)**

10. **Một đường ghi duy nhất**: `POST /confirmations` rồi `POST /actions` với sáu `tool` (`move_between_jars`, `record_transaction`, `assign_jar`, `update_profile`, `save_jars`, `confirm_salary`). Hồ sơ, nghĩa vụ CRUD và onboarding đều là `update_profile` (onboarding: lần đầu có lương và ngày nhận thì server tạo hồ sơ, hai hũ hệ thống và hũ `jar_templates.is_default`); tạo, sửa hũ và luật chia là `save_jars` (thay cả danh sách, tổng 100); "gán Tiền vào khác vào hũ" là `move_between_jars` (từ `tien_vao_khac`) hoặc `assign_jar` theo giao dịch. `save_jars` và `confirm_salary` chỉ có ở REST, không lộ cho agent.
11. **Khối `confirm_action` và `receipt_action` mới**, `confirm` và `receipt` giữ nguyên cho chuyển hũ. Lý do: nới `ConfirmData` thành hợp theo `tool` đổi kiểu TypeScript (`preview.from`, `from_jar`) mà code phase 1 dùng; không động vào frontend ở bước 0. Hậu quả: frontend có hai cặp view; `POST /actions` trả `receipt` hoặc `receipt_action`.
12. **Chuẩn hóa `params` là một phần của hợp đồng** (bảng ở contracts/README.md): bản chuẩn hóa điền mặc định phụ thuộc trạng thái (hũ suy từ `tx_type`, mã hũ mới sinh từ tên, `due_date` từ `due_day`) và phải idempotent, để thứ ký đúng thứ hiển thị. Công thức băm đã có sẵn (`hash_normalized_params`); từng bộ chuẩn hóa là việc của luồng A.

**Dự báo và ML**

13. **Xác suất hoặc nhóm tin cậy**: `confidence_band` luôn có; `p_shortfall` (tỷ lệ 0..1) chỉ khi backtest tuần gần nhất đạt độ phủ mục tiêu (`ForecastConfig.probability_enabled`) và không phải ước lượng ban đầu. Chưa đạt thì chỉ hiện nhóm Cao/Vừa/Thấp (đúng điều kiện của tiêu chí 4). `status` đủ/sát/hụt luôn có, suy từ xác suất nội bộ qua hai ngưỡng cấu hình.
14. **Giao diện ML**: pipeline dựng mọi thứ từ DB (lịch sử chi theo ngày, lịch nghĩa vụ đã mở rộng chu kỳ, lương chia theo hũ); ML chỉ nhận số và ngày (`ForecastInputs`), thuần hàm, và tự tính độ phủ dữ liệu từ `CoverageInputs`. `history_days` và cờ ước lượng ban đầu ở mức tài khoản (lớn nhất các hũ); hũ ít lịch sử riêng có `series_kind = cold_start` và nhóm Thấp. Đường sự kiện là `update_forecast` (chỉ chạy lại Monte Carlo các hũ liên quan trên phân vị cũ).
15. **Thẻ chủ động** phase 2 chọn bằng luật tất định ở `GET /overview` (không LLM); "Để sau" và "Ít nhắc loại này" chỉ lưu phía giao diện đến khi có bảng `nudges` (F7).
16. **Sự kiện**: năm loại trên `yofina-bus`. Ngoài `transaction.recorded`, `salary.confirmed`, `forecast.updated` (đề bài) thêm `obligation.changed` và `profile.updated` vì nghĩa vụ và lương đổi làm đổi dự báo dù số dư hũ không đổi. `event_id` quyết định dedupe; phát sau commit, lỗi phát không làm hỏng việc ghi (nightly bù).

**Cho bốn luồng sau (điều cần biết trước khi code)**

- **Frontend (D)**: `frontend/src/contracts/blocks.ts` đã có Zod của tám khối nhưng `BLOCK_TYPES` và `BlockType` còn bốn (để `registry.tsx` biên dịch được); thêm bốn khối mới vào `REGISTERED_BY_FRONTEND` trong `scripts/gen_contracts.mjs` rồi sinh lại, cùng lúc đăng ký view. Test `frontend/src/api/openapi.test.ts` đối chiếu `ERROR_CODES` với `ErrorCode` của OpenAPI: sẽ **đỏ** cho tới khi `api/errors.ts` thêm chín mã mới (`PROFILE_INCOMPLETE`, `TRANSACTION_NOT_FOUND`, `OBLIGATION_NOT_FOUND`, `PAYEE_NOT_FOUND`, `SALARY_EVENT_NOT_FOUND`, `JAR_PROTECTED`, `CREDIT_LIMIT_EXCEEDED`, `DUPLICATE_TRANSACTION`, `FORECAST_UNAVAILABLE`). Cần biểu tượng và màu cho `gray` + `inbox`, `gray` + `help` (hũ hệ thống). Nhãn "Trả sau (mô phỏng)" lấy từ `CreditLine.product_label`, không gõ cứng.
- **Sổ cái (A)**: cài bộ chuẩn hóa từng tool trong `yofina_core.confirm` (theo bảng), mở rộng `repo`, `service`, `gateway_api`, `rest_api`; `reset_demo` xóa thêm bảng mới theo đúng thứ tự khóa ngoại (transactions trước obligations và payees; jars cuối) và gọi `app_ensure_system_jars`; cập nhật `gateway/policies/*.cedar`; phát sự kiện sau commit; sửa test ledger hiện có nếu cần. Chạy `uv run scripts/migrate.py --seed` trước khi dùng `tx_type_map`.
- **ML (B)**: thay thân hàm trong `ml/yofina_ml/api.py`, thêm module thuật toán; kiểm bằng `contract.check_result`. Persona sinh ra cũng phải seed `obligations`, `payees`, `credit_lines` và `tx_type` cho từng dòng sổ cái.
- **Pipeline và forecast (C)**: dựng `ForecastInputs` từ `app_get_daily_spend`, `app_list_jars`, `app_list_obligations`; mở rộng chu kỳ nghĩa vụ và chia lương (`split_amount`); ghi ba bảng dự báo trong một transaction; phát `forecast.updated`; `forecast___get_forecast` trả `ForecastTimelineData` qua `build_forecast_timeline`.
