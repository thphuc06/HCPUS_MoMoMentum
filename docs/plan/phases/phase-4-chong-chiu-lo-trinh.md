# Phase 4 — Chống chịu, lộ trình, phân hũ tự động (F4, F5)

Ngày dự kiến: 3–5/12/2026. Kế hoạch tổng: [master-plan.md](../master-plan.md). Điều kiện vào: phase 3 đạt; đọc "Kết quả thực hiện" của các phase trước.

## Mục tiêu

Người dùng thấy Điểm chống chịu 0–100 với bốn thành phần và bấm được ba cú sốc; có lộ trình theo giai đoạn, mỗi bước có lý do, lưu phiên bản và sinh lại khi hành vi đổi; giao dịch được phân hũ tự động sau khi ghi, với danh sách "Xem lại" và hỏi gộp. **Cảnh 3 và cảnh 4 của demo chạy được.**

## Phạm vi

FR7, FR8, FR2 đầy đủ (bước 0 → luật → embedding → LLM, ba mức tin cậy), phát hiện đổi hành vi, cổng nhắc ở mức tối thiểu (bản tin đầy đủ ở phase 5).

## Đọc trước

| Luồng | Đọc |
|---|---|
| Mọi luồng | [proposal-summary.md](../../proposal/proposal-summary.md) §10.3, §10.4, §10.5, §11 (đoạn Điểm chống chịu); [overview.md](../../architecture/overview.md) mục ML |
| A | [spike-ml-forecasting.md](../../research/spike-ml-forecasting.md) §6, §7, §8, §9; mã `spikes/ml-forecasting/s7_change.py`, `s8_lp.py`; [ml-forecasting.md](../../research/ml-forecasting.md) phần điểm chống chịu, điểm gãy, LP |
| B | [spike-bedrock-models.md](../../research/spike-bedrock-models.md) §6; [spike-aurora-data-api.md](../../research/spike-aurora-data-api.md) §3; [aws-data-events-infra.md](../../research/aws-data-events-infra.md) §3.3; skill `aws-core:aws-messaging-and-streaming` |
| C | proposal-summary §10.5; [strands-agui.md](../../research/strands-agui.md) phần agents-as-tools; mã `agent/` của phase 3 |
| D | [figma-ui-design.md](../../research/figma-ui-design.md) §4, §5, §8.2 cảnh 3 và 4. Figma node: R1 `23:1786`, R2 `23:1881`, R3 `23:1993`, L1 `23:2088`, L2 `23:2190`, L3 `23:2279`, A1 `24:2406`, A2 `24:2505`; component ResilienceGauge `14:319`, ScoreRow `14:332`, RoadmapStep `14:385` |

## Bước 0 — Hợp đồng

- Migration `0004`: `resilience_scores` (điểm, bốn thành phần, đầu vào đã dùng, theo ngày), `roadmaps` (JSON, phiên bản, lý do sinh lại, trạng thái từng bước), `behavior_flags` (nghi đổi hành vi, điểm gãy đã xác nhận), cột embedding (pgvector) và độ tin cậy phân loại trên `transactions`, bảng `tx_embeddings_labeled`.
- Tool: `forecast___get_resilience_score`, `forecast___stress_test`, `planner___optimize_allocation`, `planner___save_roadmap`, `planner___get_roadmap`, `ledger___get_unclassified`, `ledger___assign_jar` (hai tool cuối đã có khung từ phase 2, nay hoàn chỉnh).
- Khối: `resilience_score`, `stress_result` (điểm trước–sau, số ngày trụ được, khoản thiếu), `roadmap` (giai đoạn, bước, lý do, trạng thái chờ / đã chấp nhận / đã từ chối), `roadmap_diff`, `review_list`.
- REST: điểm chống chịu, chạy cú sốc, lộ trình (đọc, chấp nhận / sửa / từ chối từng bước, so phiên bản, yêu cầu sinh lại), danh sách "Xem lại", hỏi gộp, gán hũ kèm phạm vi luật.
- `Roadmap` (Pydantic) và định nghĩa ba cú sốc mẫu (mất việc 2 tháng, tiền trọ tăng, ốm một tuần) dạng dữ liệu.

## Luồng A — ML: điểm chống chịu, cú sốc, LP, điểm gãy

Sở hữu: `ml/yofina_ml/`, `gateway/tools/forecast/` (phần mới), `gateway/tools/planner/` (phần mới), bước mới trong `pipelines/nightly/`.

- Điểm chống chịu: Save (số ngày sống được bằng số dư khả dụng), Spend (tỷ lệ chi trên thu, trả đúng hạn), Borrow (nghĩa vụ trên thu nhập), Plan (tiến độ mục tiêu). Trọng số và ngưỡng trong cấu hình, mỗi thành phần trả kèm câu giải thích dựng bằng code. Tính trong batch đêm và khi đặt lại dữ liệu.
- `stress_test`: áp cú sốc lên dự báo bằng Monte Carlo, trả điểm sau cú sốc, số ngày trụ được (toàn bộ và riêng hũ Dự phòng), khoản thiếu.
- `optimize_allocation`: `scipy.optimize.linprog`, sàn cứng qua biến elastic với mức phạt riêng theo ưu tiên, trọng số mục tiêu khác nhau; vô nghiệm thì nới ràng buộc mềm một lần (lùi hạn mục tiêu, giảm hũ không thiết yếu), vẫn không được thì trả hai lựa chọn.
- Đổi hành vi: z bền MAD cho khoản lớn một lần (chỉ chỉnh dự báo kỳ này); CUSUM / PageHinkley tự viết trên z theo tuần để "nghi" (chạy trong đường sự kiện); PELT theo tuần (`ruptures`, `l2`, chuỗi đã cắt khoản lớn) trong batch đêm để xác nhận, mức mới phải giữ khoảng 2 tuần. Hiệu chỉnh penalty trên cả ba persona và bộ sinh khác họ; ghi tỷ lệ báo nhầm.
- Điểm gãy được xác nhận → phát sự kiện `behavior.changed` → kích hoạt sinh lại lộ trình.
- Persona `minh` có điểm gãy cài sẵn để sau khi đặt lại, lộ trình ở phiên bản 3 với lý do "hành vi thay đổi" (khớp frame L1).

## Luồng B — Pipeline sự kiện: phân hũ tự động

Sở hữu: `pipelines/event/`, `gateway/tools/ledger/` (phần phân loại).

- Lambda `yofina-classify` nghe `transaction.recorded` (SQS, idempotent). Người dùng đã tự chọn hũ nguồn thì bỏ qua. Thứ tự: bước 0 bảng tra loại giao dịch → bước 1 `category_rules` của người dùng (SQL) → bước 2 embedding (Cohere, chuỗi đã chuẩn hóa: bỏ dấu, chữ thường, mở rộng viết tắt; khớp chuỗi chính xác trước, rồi k-NN pgvector; ngưỡng hiệu chỉnh trên bộ kiểm thử, không dùng 0,97) → bước 3 model nhỏ (lời nhắn, số tiền, thời điểm, tín hiệu hành vi: lặp lại cùng người nhận, số tiền tròn, giờ ăn).
- Ba mức tin cậy (ngưỡng trong cấu hình, hiệu chỉnh trên dữ liệu): tự gán; tự gán và vào "Xem lại"; vào hũ tạm "Chưa phân loại" và hỏi gộp một lần mỗi ngày kèm 2 gợi ý. Khoản nhỏ một lần không rõ thì vào hũ "Khác", không hỏi.
- `assign_jar`: sửa hũ, lưu luật theo phạm vi "chỉ lần này" hoặc "luôn luôn cho người này"; sửa nhiều lần thì nâng ngưỡng tự gán của người nhận đó.
- Sau phân loại: cập nhật số dư hũ, chỉnh nhanh dự báo (đã có từ phase 2), chạy bộ "nghi".
- Bộ kiểm thử phân loại `evals/classification/`: giao dịch có nhãn của ba persona (ít nhất 300 dòng, có chuyển khoản tên riêng không lời nhắn). Báo cáo độ đúng và tỷ lệ phải hỏi.
- Tên người nhận và số tài khoản che trước khi vào model.

## Luồng C — Agent: Roadmap agent và cú sốc trong chat

Sở hữu: `agent/`.

- Roadmap agent (Sonnet 4.6): gom ngữ cảnh (mục tiêu, dự báo, nghĩa vụ, điểm yếu chống chịu, phản hồi trước đây) → phác giai đoạn và hành động → `optimize_allocation` tính số → `check_suitability` → vi phạm thì sửa tối đa 2 vòng, hết vòng thì bỏ hành động vi phạm và giữ phần hợp lệ → `Roadmap` kèm lý do từng bước → `save_roadmap` phiên bản mới (lưu lộ trình là thao tác ghi không đổi số dư; hành động đổi số dư trong từng bước vẫn qua `confirm`).
- Sinh lại chạy nền: Lambda `yofina-roadmap-regen` nghe `behavior.changed`, đổi mục tiêu, đổi thu nhập, hoặc yêu cầu của người dùng; gọi Runtime bằng danh tính dịch vụ kèm `user_id` đã xác thực (hoặc chạy cùng mã agent trong Lambda nếu gọi Runtime từ dịch vụ không khả thi: tra tài liệu trước khi chọn). Frontend hỏi tiến độ bằng polling.
- Dự báo đổi nhẹ chưa tới ngưỡng: cập nhật số trong lộ trình cũ, giữ cấu trúc. Người dùng sửa một bước: lưu phiên bản mới, ghi `feedback`, không sinh lại toàn bộ. Từ chối toàn bộ: hỏi một câu lý do, ghi lại.
- Router thêm ý định `resilience`, `stress`, `roadmap`; chat trả khối `resilience_score`, `stress_result`, `roadmap`.
- Cổng nhắc tối thiểu: thẻ chủ động ở Tổng quan chọn một việc có giá trị cao nhất (hũ sắp cạn, nghĩa vụ sắp đến hạn, lộ trình mới), tối đa một việc; "Ít nhắc loại này" giảm tần suất loại đó.

## Luồng D — Frontend

Sở hữu: `frontend/`.

- Tab "Nhìn trước": R1 (gauge SVG, ba thẻ cú sốc), R2 (sau cú sốc: điểm tụt có animation số, số ngày trụ được, khoản thiếu, nút "Xem lộ trình thích ứng"), R3 (bốn thành phần có giải thích, dòng "không phải điểm tín dụng").
- Lộ trình L1–L3: phiên bản và lý do sinh lại, bước có Chấp nhận / Sửa / Từ chối, "Vì sao" từng bước, so với bản cũ, "Dùng bản mới" / "Giữ bản cũ", tiến độ khi đang sinh lại.
- A1 "Xem lại" (sửa bằng một chạm, chọn phạm vi luật) và A2 hỏi gộp; số tiền chưa phân loại hiện ở Tổng quan và màn dự báo.
- Các khối mới vào registry, dùng chung giữa màn hình và chat.

## Bộ đánh giá của phase

Thêm `evals/golden/phase4.jsonl` (ít nhất 12 câu: điểm, ba cú sốc, xin lộ trình, mục tiêu không khả thi, sửa một bước) và `evals/adversarial/phase4.jsonl` (ít nhất 10 câu: ép gợi ý đầu tư khi chưa có quỹ dự phòng, ép khuyên vay để tiêu, lời nhắn giao dịch chứa prompt injection).

## Tiêu chí hoàn thành

1. Tài khoản `minh`: Điểm chống chịu hiện với bốn thành phần có giải thích; bấm "Mất việc 2 tháng" thì điểm tụt và hiện số ngày trụ được; hai cú sốc còn lại cũng chạy. Số so với bảng số Figma (58 → 34, 27 ngày) ghi vào "Kết quả thực hiện"; lệch thì dùng số engine.
2. Sau khi đặt lại, lộ trình của `minh` là phiên bản có lý do "hành vi thay đổi"; so được với bản trước; chấp nhận một bước đổi số dư đi qua `confirm` và token.
3. Dùng script thêm hai tuần giao dịch lệch mức cũ cho một tài khoản thử rồi chạy batch đêm: điểm gãy được xác nhận, lộ trình phiên bản mới xuất hiện kèm lý do. Một khoản lớn đơn lẻ không làm sinh lại lộ trình.
4. Mục tiêu không khả thi: lộ trình nói thẳng và đưa hai lựa chọn.
5. Bộ đối kháng: 0 lộ trình chứa hành động vi phạm suitability.
6. Phân loại trên bộ kiểm thử: đúng từ 90%, dưới 10% giao dịch phải hỏi; số ghi vào file phase. Chưa đạt thì ghi rõ số đạt được và nguyên nhân.
7. Tạo một chuyển khoản cho đối tác mới: trong 1 phút giao dịch có hũ hoặc nằm ở "Xem lại" / "Chưa phân loại"; sửa hũ với "luôn luôn cho người này" thì giao dịch kế tiếp cho cùng người tự đúng.
8. LP: test unit phủ ca vô nghiệm, ca nới ràng buộc, ca ưu tiên; thời gian chạy ghi lại.
9. Cảnh 3 và 4 đi được trên URL Amplify theo kịch bản bấm.

## Cách kiểm (người điều phối)

- Chạy test, chạy bộ đánh giá phase 3 và 4 (kiểm hồi quy phase 3).
- Đi cảnh 3 và 4 theo [figma-ui-design.md §8.2](../../research/figma-ui-design.md), so với frame Figma.
- Tự chạy script điểm gãy ở tiêu chí 3 và đọc `roadmaps`, `behavior_flags` trong Aurora.
- Đọc 20 giao dịch bị phân loại sai trong báo cáo để xem lỗi có hệ thống không.

## Kết quả thực hiện

(Điền khi đóng phase.)
