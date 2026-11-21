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

(Điền khi đóng phase.)
