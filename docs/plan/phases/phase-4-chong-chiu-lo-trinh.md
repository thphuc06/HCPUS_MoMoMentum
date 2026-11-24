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

**Đã làm ngày 2026-11-23** (chỉ hợp đồng: chưa cài logic, chưa chạy migration, chưa deploy). Quyết định, chỗ lệch so với danh sách dưới đây và việc của từng luồng: [Quyết định hợp đồng phase 4](#quyết-định-hợp-đồng-phase-4) và [Cho các luồng sau](#cho-các-luồng-sau).

- Migration `0052` (số `0004` ở bản đầu file này là cũ): `resilience_scores` (điểm, bốn thành phần, đầu vào đã dùng, theo ngày), `roadmaps` (JSON, phiên bản, lý do sinh lại, trạng thái từng bước), `behavior_flags` (nghi đổi hành vi, điểm gãy đã xác nhận), cột embedding (pgvector) và độ tin cậy phân loại trên `transactions`, bảng `tx_embeddings_labeled`.
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

## Kế hoạch thực hiện phần của Phúc (luồng A, B; chốt 23/11)

Người điều phối (Claude Code trên máy Phúc) giao bốn gói cho bốn subagent Claude Sonnet 5.5 (effort high), chạy song song trên CÙNG cây làm việc `main`. Mỗi gói chỉ sửa đúng các file liệt kê; file dùng chung do người điều phối nối ở bước ghép. Học làm luồng C và D trên nhánh `feat/phase4-agent-ui`, không đụng các file dưới đây.

**Hợp đồng nội bộ giữa các gói (chốt trước khi giao)**

- **N1. Ledger gọi forecast để tối ưu phân bổ.** `planner___optimize_allocation` ở ledger là proxy mỏng: gọi `Invoke` đồng bộ Lambda `yofina-forecast-batch` với sự kiện `{"op": "optimize_allocation", "user_id": <sub>, "args": <tham số tool đã bỏ user_id>}` và trả nguyên văn kết quả: phong bì tool như Gateway (`{"status": "OK", "as_of", "app_date", "data": OptimizeAllocationData}` hoặc phong bì lỗi `{"status": "ERROR", "code", "message"}`). Lambda forecast tự đọc dữ liệu người dùng và dựng bài toán (nó đã nhúng `yofina_ledger` để đọc). Lỗi gọi (hết giờ, Lambda lỗi) thì ledger trả `FORECAST_UNAVAILABLE` (lỗi tạm thời), không đoán số.
- **N2. Batch đêm.** Mỗi gói xuất một hàm cho từng người dùng, KHÔNG tự nối vào `run_user`: gói 1 `yofina_forecast.resilience.compute_and_store(pipeline, user_id, now)`; gói 3 `yofina_forecast.change.detect_and_store(pipeline, user_id, now)`. Người điều phối nối cả hai vào sau bước dự báo của `run_user` (thứ tự: dự báo → điểm chống chịu → phát hiện đổi hành vi), lỗi của một bước không làm hỏng bước khác.
- **N3. REST ledger.** `rest_api._dispatch` là chuỗi `if`. Gói 2 thêm đúng MỘT khối chuyển tiếp `if route.startswith(("GET /roadmap", "POST /roadmap")): return roadmap_rest.dispatch(...)`; gói 4 thêm đúng MỘT khối cho `/review`. Đọc lại file ngay trước khi sửa (hai gói sửa cùng file, khác dòng). REST `/resilience*` thuộc Lambda forecast (gói 1).
- **N4. Dữ liệu persona.** Gói 3 sở hữu chuỗi giao dịch của persona (điểm gãy của `minh`); gói 2 sở hữu file mới `data/personas/roadmaps/` (lộ trình v1 đến v3 và dấu hiệu đổi hành vi đã xác nhận cài sẵn cho `minh`); gói 4 sở hữu nhãn k-NN seed (file mới dưới `data/personas/`). Không ai sửa file của gói khác.
- **N5. `RESET_DELETES`** (ledger `repo.py`): gói 2 thêm TẤT CẢ bảng mới của 0052 (cả bảng của gói 1, 3, 4) đúng thứ tự khóa ngoại.

| Gói | Nội dung | Được sửa | Kiểm tối thiểu |
|---|---|---|---|
| **1. Điểm chống chịu, cú sốc, tối ưu phân bổ** (phía forecast) | Công thức điểm (đọc `resilience_defaults.json`), `stress_test` Monte Carlo cùng dãy số ngẫu nhiên (đọc `shocks.json`), LP `linprog` (HiGHS) có biến elastic, nới một vòng, đúng hai lựa chọn khi vô nghiệm; tool `get_resilience_score`, `stress_test`; REST `GET /resilience`, `GET /resilience/shocks`, `POST /resilience/stress`; op `optimize_allocation` (N1); hàm batch N2 | `ml/yofina_ml/{resilience,stress,allocation}.py` (mới), `pipelines/forecast/yofina_forecast/{resilience,stress,allocation}.py` (mới), `tool.py`, `batch.py`, `handler_tool.py`, `repo.py` (forecast), `settings.py` (forecast), test mới | unit + local_pg; số `minh` ghi lại so với Figma (58 → 34, 27 ngày); `solver.elapsed_ms` |
| **2. Lộ trình phía ledger** | `save_roadmap` (chạy lại `check_suitability` từng bước, `ROADMAP_INVALID`), `get_roadmap`, proxy `optimize_allocation` (N1); 8 REST `/roadmap*` gồm job sinh lại (ghi `roadmap_jobs`, phát `roadmap.regeneration_requested` sau commit), quyết định bước, sửa bước (bản mới `active`, không gọi model), chọn phiên bản, so phiên bản; audit + `feedback`; seed persona (N4); `RESET_DELETES` (N5) | `gateway/tools/ledger/yofina_ledger/roadmap_*.py` (mới), `forecast_client.py`, `gateway_api.py`, một khối trong `rest_api.py` (N3), `repo.py` (chỉ `RESET_DELETES` và nạp seed lộ trình), `events.py` (sự kiện mới), `data/personas/roadmaps/` (mới), test mới | unit + local_pg; đặt lại `minh` ra v1 superseded, v2 active, v3 proposed lý do `behavior_changed` |
| **3. Phát hiện đổi hành vi** | z bền MAD cho khoản lớn một lần; CUSUM hoặc PageHinkley theo tuần trong đường sự kiện ("nghi", không phát sự kiện); PELT theo tuần trong batch (N2) xác nhận khi mức mới giữ khoảng 2 tuần, ghi `behavior_flags`, phát `behavior.changed`; hiệu chỉnh trên 3 persona và bộ sinh khác họ, ghi tỷ lệ báo nhầm vào `detail`; điểm gãy cài sẵn cho `minh`; script thêm hai tuần giao dịch lệch mức (tiêu chí 3) | `ml/yofina_ml/change.py` (mới), `pipelines/forecast/yofina_forecast/change.py` (mới), `consumer.py` (đường sự kiện), `events.py` (forecast), chuỗi giao dịch persona trong `data/personas/` (N4), `scripts/inject_behavior_shift.py` (mới), `ml/pyproject.toml` nếu thêm phụ thuộc, test mới | unit; báo cáo hiệu chỉnh; một khoản lớn đơn lẻ KHÔNG xác nhận đổi hành vi |
| **4. Phân hũ tự động** | Lambda `yofina-classify` (SQS + DLQ, idempotent, bỏ qua khi người dùng tự chọn hũ): bảng tra → `category_rules` → embedding Cohere (chuẩn hóa bỏ dấu, khớp chính xác trước, rồi k-NN) → model nhỏ; ba mức tin cậy; hỏi gộp mỗi ngày (`review_asks`); `assign_jar` gán cùng hũ để xác nhận, ghi nhãn k-NN, `correction_count` và `auto_min_confidence`; mở rộng kết quả `get_unclassified`; REST `GET /review`, `POST /review/daily-ask/skip`; che PII trước model; bộ kiểm ≥ 300 dòng và báo cáo | `pipelines/classify/` (mới), `gateway/tools/ledger/yofina_ledger/{review_*,classify_*}.py` (mới), phần `assign_jar` trong `wallet_writes.py`, phần `get_unclassified` trong `wallet_reads.py`, một khối trong `rest_api.py` (N3), `libs/yofina_core/src/yofina_core/llm.py` (thêm gọi embedding), `evals/classification/` (mới), nhãn seed (N4), `infra-cdk/lib/classify.ts` (construct mới, CHƯA nối vào stack), test mới | unit + local_pg; độ đúng ≥ 90%, tỷ lệ phải hỏi < 10% trên bộ kiểm (chưa đạt thì ghi số thật) |

**Người điều phối làm (sau khi bốn gói xong)**: nối N2 vào `run_user`; xóa tên đã cài khỏi `wallet.PHASE4_TOOLS`; 13 route trong `infra-cdk/lib/tools-stack.ts` (forecast cho `/resilience*`) và nối construct phân loại (EventBridge → SQS → Lambda, IAM Bedrock embedding, DB); lệnh build zip mới; chạy cả bộ test cục bộ; deploy theo thứ tự migration → `YofinaTools` → `YofinaAgent` → Runtime; test tích hợp mới cho luồng A và B trên AWS; ghi "Kết quả thực hiện" phần A, B. Migration `0052` chạy trên Aurora trước khi giao.

**Ràng buộc chung cho mọi gói**: không hardcode, không mock trong mã sản phẩm (fixture chỉ trong test); mọi số đọc từ dữ liệu hoặc file cấu hình có nguồn; không deploy, không đổi tài nguyên AWS (gọi Bedrock để hiệu chỉnh thì được); không commit; tra tài liệu chính thức trước khi dùng thư viện hay dịch vụ; ghi một entry ai-log mỗi gói.

## Kết quả thực hiện

### Đóng phase ngày 2026-11-24 (Runtime `yofina_agent` version 18)

Chủ dự án quyết định đóng phase 4 ngày 24/11. Cách làm của đợt đóng: Claude Code điều phối, các worker `kiro-cli` (Claude Opus 5.5) viết code, deploy và chạy kiểm; Claude Code review, merge và tự đi cảnh 3, 4.

| # | Tiêu chí | Kết quả | Dẫn chứng |
|---|---|---|---|
| 1 | Điểm chống chịu `minh`, ba cú sốc | Đạt | Đi trên Amplify 24/11: điểm 33/100 "Yếu", bốn thành phần có giải thích (Tiết kiệm 15, Chi tiêu 43, Vay nợ 10, Kế hoạch 94); "Mất việc 2 tháng" 33 → 13, trụ 31 ngày, hũ Dự phòng 13 ngày, thiếu 8.508.779 ₫ từ 23/12. Figma ghi 58 → 34, 27 ngày; dùng số engine (đã ghi ở quyết định 12). Hai cú sốc còn lại: integration test 03 |
| 2 | Sau đặt lại có lộ trình "hành vi thay đổi", so bản cũ, chấp nhận bước | Đạt | Đi trên Amplify: v2 đang dùng + dải "Có phiên bản mới" → So với bản cũ (thêm 1, bỏ 1, đổi 1, lý do "Chi Ăn uống mỗi tuần tăng từ 520.000 ₫ lên 810.000 ₫…") → Dùng bản mới → Vì sao → Chấp nhận. Đổi số dư qua confirm và token: integration test 09, 12 |
| 3 | Script lệch mức + batch đêm → điểm gãy, lộ trình mới; một khoản lớn không sinh lại | Đạt (trên `lan`, `--factor 4`) | Mục "Tiêu chí 3 (24/11)" bên dưới |
| 4 | Mục tiêu không khả thi: nói thẳng, hai lựa chọn | Đạt | Golden `roadmap-infeasible-goal`: `feasibility` infeasible, đúng 2 `alternatives` (Runtime v18) |
| 5 | Đối kháng: 0 lộ trình vi phạm suitability | Đạt | Adversarial phase 4 12/12, 0 bước vi phạm |
| 6 | Phân loại ≥ 90% đúng, < 10% phải hỏi | Đúng đạt, tỷ lệ hỏi chưa đạt | 92% đúng trên phần tự gán; tỷ lệ hỏi 17,4% (ghi ở entry ai-log gói 4, 23/11) |
| 7 | Đối tác mới trong 1 phút; "luôn luôn cho người này" | Đạt | Integration test 19–21 (45/45 trên v18) |
| 8 | LP: ca vô nghiệm, nới, ưu tiên; thời gian | Đạt | Unit test LP; giải 3 ms, cả lượt 0,89 s (23/11) |
| 9 | Cảnh 3, 4 trên Amplify | Đạt | Đi 24/11 ở khổ 390x844, tài khoản `minh` (chủ dự án tự đăng nhập). Hỏi "Nên mua cổ phiếu nào?" → "Ngoài phạm vi hiện tại", không mã chứng khoán |

Số cuối cùng trên Runtime v18: golden phase 4 14/14, adversarial phase 4 12/12, golden phase 3 31/31 (gồm `whatif-bnpl2`), integration phase 3+4 45/45, unit 2902.

Sửa trong đợt đóng (23–24/11): schema gửi model mất field `title`; goals sai hũ; Lambda sinh lại bỏ qua `profile.updated` có `onboarding`; phác thảo lộ trình thử lại khi sai schema, bỏ nhãn thứ tự khỏi grounding, đề xuất suitability khớp ledger, log bước bị loại; mục tiêu người dùng nói trong câu (`target_vnd`, `target_date`); luật `source_jar_covers` v2 (bước từ kỳ lương kế so với thu nhập tháng); Verifier what-if gửi proposal đúng hũ nguồn và giữ phương án khi rơi vào dự phòng.

Lệch và việc để sau:
- Đi cảnh 4 thấy: bước lộ trình hiện mã hũ thô ("giai_tri → an_uong"); chip gợi ý sau lời từ chối chưa có lối về chống chịu/lộ trình (đang giao sửa). "Vì sao" mở tại chỗ thay vì bảng riêng như Figma; trang lộ trình mở bản đang dùng (v2) kèm dải "Có phiên bản mới" thay vì mở thẳng v3.
- `period_end` của lộ trình tính theo ngày hôm nay, chưa theo ngày lương (agent chưa có ngày lương từ tool).
- Model đôi khi đề bước có phân bổ 0 ₫ (bị loại, lộ trình vẫn lưu các bước còn lại).
- Golden `roadmap-edit-one-step` ra `infeasible`: có thể router đọc câu sửa bước thành mục tiêu mới; xem lại.
- Seed `minh` có sẵn dấu hiệu `confirmed` nên tiêu chí 3 phải kiểm trên `lan`; docstring script ghi `--factor 2` nhưng cần khoảng 3–4.
- local_pg `test_dat_lai_xoa_sach_du_lieu_moi_cua_0052_dung_nguoi` đỏ sẵn (đếm `tx_embeddings_labeled`).
- Tỷ lệ hỏi của phân loại 17,4%: hai hướng giảm (bỏ token mẫu QR khỏi chuỗi embedding; giảm trọng số lịch sử khi ghi chú rõ).

### Tiêu chí 3 (24/11)

Kiểm trên AWS thật (`ap-southeast-1`) ngày 24/11, 06:46 đến 06:56 (+07), worker Kiro (Claude Opus 5.5) do Claude Code điều phối, Phúc đồng ý ghi dữ liệu thử. Không deploy, không migration, không sửa code. Ghi dữ liệu chỉ qua `scripts/inject_behavior_shift.py` (luồng nạp CSV F6) và `POST /demo/reset` (`scripts/seed_demo.py`). Đọc qua REST (`/roadmap/versions`, `/roadmap?which=latest`, `/roadmap/jobs/{id}`), CloudWatch Logs và Data API bằng secret `yofina-db-app` có đặt `app.user_id` (chỉ SELECT).

**Kết luận: đạt có điều kiện.** Ca đổi hành vi đạt trên `lan` (không chạy được trên `minh`) với `--factor 4` (không dùng mặc định 2). Ca khoản lớn đơn lẻ đạt.

**Vì sao không dùng `minh`.** Sau khi đặt lại, `minh` có sẵn dấu hiệu `confirmed` (nguồn `persona_seed`) cho `an_uong`, mức 520.000 → 810.000 ₫, điểm gãy 2026-11-04. Mỗi (người dùng, hũ) chỉ có tối đa MỘT dấu hiệu mở, và `detect_and_store` bỏ qua hũ đã có dấu hiệu `confirmed` nên không thể có dòng mới, đúng như thiết kế. Script chạy thử cũng báo "Hai tuần cuối của hũ đã đạt 2.0 lần mức cũ (435,000 VND mỗi tuần)". Các hũ khác không dùng được: `giai_tri` bị bỏ qua vì `insufficient_history` (mức cũ 31.000 ₫, dưới `min_abs_change_vnd` 50.000 ₫), `di_lai` bị bỏ qua vì `sparse`. `giamkhao1` và `giamkhao2` cũng là persona `minh`. `giamkhao3` (persona `vy`) đã có dấu hiệu `applied` với điểm gãy 2026-10-31, nên điểm gãy mới trong hai tuần cuối trùng trong `dedupe_days` 14 ngày. Chọn `lan`: có hũ `an_uong` đủ điều kiện, không có dấu hiệu và không có lộ trình.

**Ca đổi hành vi (`lan`, hũ `an_uong`)**

Chuỗi chi theo tuần mà `detect_and_store` đọc (từ `app_get_forecast_context`, cũ tới mới, tuần cuối kết thúc 2026-11-20, ngày mô phỏng 2026-11-21) được dựng lại cục bộ bằng chính `yofina_forecast.change.spending_series` và `yofina_ml.change`, chỉ đọc:

| Lần | Thêm (script) | Ghi được | 6 tuần (nghìn ₫) | PELT |
|---|---|---|---|---|
| Trước khi thêm (sau đặt lại) | | | 459, 471, 181, 336, 698, 694 | không xác nhận (batch 06:46 xác nhận lại) |
| `--factor 2` (mặc định) | không thêm gì | | | script báo hai tuần cuối đã đạt 2 lần mức cũ 336.000 ₫ |
| `--factor 3` | 18 dòng, 624.000 ₫ | 12 dòng, 431.000 ₫ (6 dòng bị khử trùng) | 459, 471, 181, 336, 973, 850 | không xác nhận (batch 06:47) |
| Đặt lại rồi `--factor 4` | 18 dòng, 1.296.000 ₫ | 15 dòng, 1.071.000 ₫ (3 dòng bị khử trùng) | 459, 471, 181, 336, 1.119, 1.344 | **xác nhận** |

Với `--factor 3`, hai tuần lệch tăng khoảng 550.000 ₫ so với mức cũ, nhưng với sigma khoảng 150.000 ₫ thì penalty `6 · sigma² · ln 52` cần khoảng 630.000 ₫. Với 6 tuần lịch sử và một tuần nền thấp (181.000 ₫), bộ phát hiện chỉ xác nhận khi mức mới gấp khoảng 3 lần mức cũ.

Kết quả của lần `--factor 4`:

- `behavior_flags`: một dòng mới `2dead1bf…`, `an_uong`, `pelt`, `up`, `old_weekly_vnd` 361.750, `new_weekly_vnd` 1.219.868, `change_point_date` 2026-11-07, `weeks_held` 2, `sigma_vnd` 149.915, `params_version` 2026-11-phase4-goi3-2. Dòng được tạo lúc 06:50:00, chuyển `applied` lúc 06:50:10, sau khi lộ trình được lưu.
- Bước phát hiện chạy trong `run_user`, do API nạp dữ liệu gọi ngay sau `confirm_rows` (`trigger` `manual`, có trong `POST_STEP_TRIGGERS`). Log `yofina-forecast-batch` lúc 06:49:59–06:50:00 có `"confirmed": ["an_uong"]`, `"published": ["2dead1bf-…"]` và metric `BehaviorChangeConfirmed` 1, nghĩa là `behavior.changed` đã phát. Lần gọi `run_user` với `trigger` `nightly` theo lệnh script in ra (06:50:20) không tạo gì mới (dấu hiệu đã có, nằm trong `dedupe_days`), tức bước này chạy lại an toàn.
- `yofina-roadmap-regen` chạy một lần lúc 06:50:00, 10,1 s. Job `fd116720…`: `trigger` `behavior_changed`, `behavior_flag_id` và `dedupe_key` bằng `2dead1bf…`, `requested_at` 06:50:00, `finished_at` 06:50:10 (9,6 s), `status` `done`, `stage` `save`, `progress` 100. `GET /roadmap/jobs/{id}` trả cùng số liệu.
- `GET /roadmap/versions`: phiên bản 1 (`4f750c5c…`), `active`, `reason_code` `behavior_changed`, lý do "Chi Ăn uống mỗi tuần tăng từ 361.750 ₫ lên 1.219.868 ₫ và giữ mức đó 2 tuần.", `feasibility` `on_track`, 2 bước. Lộ trình mới là v1 vì `lan` chưa có lộ trình nào, nên được dùng ngay (`active`), không phải `proposed`. `GET /roadmap?which=latest` trả khối `roadmap` có `reason.detail` "Chi Ăn uống mỗi tuần" từ 361.750 ₫ lên 1.219.868 ₫, kèm `behavior_flag_id`.

**Ca khoản lớn đơn lẻ (`lan` sau khi đặt lại, hũ `an_uong`)**

- `--mode one-off --apply --consent`: một dòng 3.360.000 ₫ ngày 2026-11-17 (10 lần mức cũ 336.000 ₫), ghi được 1/1.
- Chuỗi tuần thô là 459, 471, 181, 336, 698, 4.054 (nghìn ₫). Bước z bền MAD đánh dấu đúng ngày 2026-11-17 (`one_off_days`), tuần cuối sau khi làm sạch còn 939.716 ₫, PELT không xác nhận.
- Lần chạy `run_user` sau nạp (06:52:17) và lần `nightly` (06:52:31) đều log `checked: ["an_uong"]`, không có `confirmed`. `behavior_flags` có 0 dòng (không có cả `suspected`). `roadmap_jobs` có 0 dòng, `GET /roadmap/versions` trả `[]`, log `yofina-roadmap-regen` trống từ 06:52 tới lúc kiểm (khoảng 06:54).

**Hàng đợi, Aurora, đặt lại**

- DLQ `yofina-roadmap-events-dlq` và `yofina-forecast-events-dlq`: 0 tin (`ApproximateNumberOfMessages` và `NotVisible` đều 0).
- Aurora `yofina-db`: `MinCapacity` 0, `MaxCapacity` 2, tự ngủ sau 600 s.
- Cuối buổi chạy `uv run scripts/seed_demo.py minh lan`. `lan` có 0 dấu hiệu và 0 lộ trình. `minh` trở lại seed: dấu hiệu `confirmed` cài sẵn cùng v1 `superseded`, v2 `active`, v3 `proposed` `behavior_changed`. `giamkhao1` đến `giamkhao3` chỉ được chạy thử (không ghi).

**Phát hiện (chưa sửa)**

1. Theo thiết kế, tiêu chí 3 không làm được trên `minh` sau khi đặt lại, vì seed đã có điểm gãy và dấu hiệu `confirmed` mở cho `an_uong`. Muốn kiểm trên `minh` thì cần một tài khoản persona `minh` không có dấu hiệu seed, hoặc chỉ ra hũ khác có đủ lịch sử.
2. `--factor` mặc định 2 không đủ trên `lan`, và cả 3 cũng không đủ. Docstring của script ghi "đủ lớn để PELT xác nhận sau hai tuần giữ mức". Điều đó chỉ đúng với chuỗi ít nhiễu, còn với 6 tuần lịch sử của `lan` thì cần khoảng 3 lần mức cũ.
3. Script lập kế hoạch rồi nạp, nhưng bước khử trùng của luồng nạp loại một phần dòng trùng (ngày, số tiền) với giao dịch có sẵn: lần `--factor 3` bỏ 6/18 dòng, lần `--factor 4` bỏ 3/18 dòng. Vì vậy tổng ghi được thấp hơn mức mục tiêu mà script in ra. Script có báo `rows_duplicate` nhưng không bù.
4. `yofina-roadmap-regen` không ghi dòng log ứng dụng nào (chỉ có START, END, REPORT). Bằng chứng job phải đọc từ `roadmap_jobs` hoặc REST.

### Quyết định hợp đồng phase 4

Viết ngày 2026-11-23 bởi subagent làm "Bước 0 — Hợp đồng" của phase 4 (Claude Sonnet 5.5). Bốn luồng sau đọc mục này cùng [contracts/README.md](../../../contracts/README.md#phase-4-chống-chịu-lộ-trình-phân-hũ-tự-động) và [db/README.md](../../../db/README.md#schema-phase-4-0052). Mọi mục dưới đây là lựa chọn tự quyết khi file phase chưa nói rõ hoặc cần chỉnh; **lệch so với file phase** được đánh dấu. Migration `0052`, tool và route mới **chưa chạy, chưa deploy**.

**Dữ liệu**

1. **Migration là `0052`, không phải `0004`** (LỆCH file phase: số cũ). Mới nhất trước đó là `0051_scenario_conversation.sql`. Một file, một transaction, tách bằng `-- @@`, viết lại được, RLS `ENABLE` + `FORCE`, hàm đọc `app_*` SECURITY INVOKER, không sửa migration cũ. `CREATE EXTENSION IF NOT EXISTS vector` nằm ở đầu (chạy bằng secret MASTER qua Lambda migrator; Aurora 17.11, pgvector 0.8.2; Postgres cục bộ của test có 0.6.2, nên chỉ dùng thứ có ở cả hai: `vector(1024)`, HNSW, toán tử `<=>`; không `halfvec`, không `hnsw.iterative_scan` trong SQL).
2. **Embedding nằm ở bảng riêng, không phải cột của `transactions`** (LỆCH file phase: "cột embedding trên `transactions`"). Lý do: Data API trả `vector` dạng chuỗi (khoảng 10 KB mỗi dòng), cột này làm phình mọi `SELECT`, `RETURNING` và hàm `app_*` của sổ cái. Độ tin cậy phân loại (`classification_confidence`), `classified_by`, `needs_review`, `suggested_jars` đã có ở `transactions` từ `0005`, nên không thêm gì vào `transactions`. Hai bảng: `tx_embeddings` (một dòng mỗi giao dịch, không chỉ mục vector, `ON DELETE CASCADE` theo giao dịch) và `tx_embeddings_labeled` (bộ nhãn k-NN của TỪNG người dùng, RLS, chỉ mục **HNSW cosine** `m=16, ef_construction=64`, khóa duy nhất `(user_id, text_norm, jar_code)` phục vụ bước "khớp chuỗi chính xác trước"). Nhãn có nguồn `user` (người dùng sửa) hoặc `seed` (persona); không có nguồn `auto` để tránh tự học từ lỗi của chính mình. Hàm `app_knn_labeled(user, vector-dạng-chuỗi, k)` và `app_find_labeled_exact(user, text_norm)`. **Chưa có ngưỡng cosine trong hợp đồng**: spike Bedrock §6 đã bác 0,97 của proposal; ngưỡng là cấu hình hiệu chỉnh trên `evals/classification/` (luồng B). Cảnh báo cho luồng B: HNSW lọc theo `user_id` SAU khi quét chỉ mục nên bộ nhãn lớn có thể trả ít hơn `k` dòng; bộ nhãn mỗi người nhỏ nên planner thường quét tuần tự; quyết định khi đo (Aurora 0.8.2 có `hnsw.iterative_scan`). Người dùng mới hoàn toàn chưa có nhãn: k-NN không có gì để so, phân loại rơi sang bước LLM.
3. **`roadmaps`: nội dung bất biến, phiên bản nguyên tử.** Mỗi lần lưu là MỘT dòng mới `(user_id, version)`; `version` tăng dần theo người dùng. Cột `plan` (jsonb: `headline`, `horizon`, `goals`, `phases` với bước ở trạng thái `pending`, `alternatives`, `basis`) **không sửa được**: `yofina_app` chỉ có `UPDATE (status, step_states, updated_at)`. Trạng thái từng bước nằm ở `step_states` (đối tượng `step_id -> {status, decided_at, edited?}`; bước vắng là `pending`), người đọc phủ lên `plan`. `status` của phiên bản: `active` (đang dùng, tối đa một, chỉ mục duy nhất một phần), `proposed` (bản mới chờ chọn, tối đa một), `superseded`, `discarded`. Ba hàm ghi (`app_save_roadmap`, `app_decide_roadmap_version`, `app_set_roadmap_step_state`) khóa dòng `users` của người gọi để hai yêu cầu song song không sinh trùng số; lỗi nghiệp vụ là `RAISE EXCEPTION` có tiền tố mã `ErrorCode` (`ROADMAP_VERSION_CONFLICT: ...`). Đã chạy thật trên PostgreSQL cục bộ (`tests/local_pg/test_phase4_schema.py`, 16 test).
4. **Lộ trình sinh lại là `proposed`, trừ hai trường hợp** (BỔ SUNG: file phase chưa nói bản mới có dùng ngay không; frame L3 có "Dùng bản mới / Giữ bản cũ" nên phải có trạng thái chờ). Bản đầu tiên (`initial`) và bản do người dùng tự sửa một bước (`step_edited`) là `active` ngay; mọi lần sinh lại khác (`behavior_changed`, `goal_changed`, `income_changed`, `forecast_drift`, `user_request`) là `proposed`. Hàm `yofina_core.roadmap.status_for_new_version`. Lưu bản `active` mới thì bản active cũ thành `superseded` và bản `proposed` (nếu có) bị bỏ; lưu bản `proposed` mới thì chỉ bản `proposed` cũ bị bỏ. Bản gốc (`based_on_version`) phải còn sống (active hoặc proposed), nếu không `ROADMAP_VERSION_CONFLICT`. Persona `minh` sau khi đặt lại: v1 và v2 `superseded` và `active`, v3 `proposed` với lý do `behavior_changed` (luồng A seed; khớp frame L1).
5. **`roadmap_jobs` (BỔ SUNG)**: một lần sinh lại chạy nền, để REST hỏi tiến độ bằng polling (`status` queued, running, done, failed; `stage` context, draft, allocate, suitability, save; `progress` 0..100; kết quả `version` và `roadmap_id`; lỗi `error_code`, `error_message`). Mỗi người dùng tối đa MỘT job đang chạy (chỉ mục duy nhất một phần): `POST /roadmap/regenerate` khi đang có job thì trả chính job đó. `dedupe_key` duy nhất theo người dùng để `behavior.changed` giao ít nhất một lần không sinh trùng.
6. **`behavior_flags`**: theo hũ, `status` suspected (CUSUM hoặc PageHinkley, đường sự kiện), confirmed (PELT, batch đêm, mức mới giữ khoảng 2 tuần), dismissed (báo nhầm), applied (đã dùng sinh lại); mức cũ và mới tính VND mỗi tuần; một dấu hiệu mở (nghi hoặc đã xác nhận) mỗi (người dùng, hũ). Ràng buộc kiểm hướng khớp mức (`up` đúng khi mức mới cao hơn). `detail` ghi tham số bộ phát hiện và tỷ lệ báo nhầm đã hiệu chỉnh.
7. **`resilience_scores`**: một dòng mỗi (người dùng, ngày mô phỏng), ghi đè khi tính lại. Bốn thành phần nằm trong cột jsonb `components` (đúng 4 phần tử, CHECK) thay vì bốn cột điểm, để điểm, trọng số, câu giải thích và đầu vào của từng thành phần đi cùng nhau và không lệch hai nơi. `inputs` là ảnh chụp dữ kiện đã dùng (mã lần chạy dự báo, cửa sổ ngày), `basis` là ảnh chụp độ tươi. Điểm lần trước lấy lúc đọc (`previous_score`), không lưu.
8. **`review_asks` (BỔ SUNG)**: câu hỏi gộp của một ngày mô phỏng, một dòng mỗi (người dùng, ngày) nên "hỏi MỘT lần mỗi ngày" được DB bảo đảm; `status` open, answered, skipped. **`payees` thêm `correction_count` và `auto_min_confidence`** (ngưỡng tự gán riêng, NULL là dùng ngưỡng chung): sửa nhiều lần thì luồng B nâng ngưỡng này. Với đối tác không có người nhận đã lưu (luật theo `merchant_key`) luồng B tự chọn cách đếm (đề xuất: số luật `once` cùng `merchant_key`); hợp đồng chưa thêm cột cho trường hợp đó.
9. **`audit_events.intent` nới từ bảy lên mười giá trị** (thêm `resilience`, `stress`, `roadmap`): nếu không, `audit___record_turn` của lượt có ý định mới sẽ vi phạm CHECK của `0010`. `wallet.INTENTS_PHASE3` giữ bảy cũ (test của `0010` khóa bằng nó), `wallet.INTENTS` là mười.

**Điểm chống chịu, cú sốc**

10. **Trọng số, ngưỡng, nhãn, mẫu câu giải thích và ba cú sốc là dữ liệu đóng gói trong `yofina_core`**, không phải trong `ml/` (LỆCH nhẹ: file phase nói "trong cấu hình" mà không nói đặt ở đâu): `resilience_defaults.json` và `shocks.json` cạnh `llm_defaults.json`, để Lambda forecast, Lambda ledger (REST `/resilience/shocks`) và `ml/` cùng đọc một file đã có trong zip. Mỗi số có `value`, `unit`, `note`, `source`; số mô phỏng nói rõ là mô phỏng (test kiểm). Định dạng khóa bằng JSON Schema (`contracts/ml/resilience_config.schema.json`, `shock_set.schema.json`) và Pydantic (`yofina_core.resilience`). Câu giải thích của thành phần do code điền vào mẫu (`explanation_template`, chỗ điền hợp lệ ở `EXPLANATION_PLACEHOLDERS`); mô tả cú sốc không chứa số (số nằm ở `params`). `yofina_core.resilience.band_for_score` là hàm duy nhất đổi điểm thành nhóm yếu, vừa, tốt. **Hợp đồng không có công thức tính điểm** (luồng A viết, đọc ngưỡng từ file; mốc nội suy tuyến tính giữa `zero_score_*` và `full_score_*`).
11. **Điểm có bốn thành phần luôn đủ đúng thứ tự save, spend, borrow, plan; thành phần không áp dụng được thì bị bỏ khỏi điểm.** Chưa có mục tiêu thì Plan có `applicable` sai, không có `score` và `band`, `weight` 0; trọng số các thành phần còn lại chuẩn hóa để cộng bằng 1. Pydantic kiểm: điểm tổng bằng trung bình có trọng số (lệch tối đa 1 do làm tròn), `weakest` là thành phần áp dụng thấp nhất. Nhóm điểm và trạng thái đủ/sát/hụt của cú sốc luôn có chữ (`headline`, `band`, `status`), không chỉ màu.
12. **`stress_result`**: điểm trước và sau, `score_delta` (không dương), số ngày trụ được của toàn bộ tiền (`runway_days_total`, vắng nghĩa là trụ hết khoảng dự báo) và của riêng hũ Dự phòng (`runway_days_emergency` kèm `emergency_jar`; vắng khi người dùng không có hũ Dự phòng), `shortfall_vnd` kèm `shortfall_from`, điểm trước và sau từng thành phần, `method` `monte_carlo`, `common_random_numbers` luôn đúng. Fixture dùng số của bảng Figma (58 → 34, 27 ngày, hũ Dự phòng 9 ngày) để luồng D vẽ đúng frame R2; số thật do engine tính, lệch thì dùng số engine (đã ghi ở tiêu chí 1).
13. **`stress_test` chỉ nhận `shock_id`** trong ba mã của `shocks.json` (không cho LLM bịa số của cú sốc; đổi số là việc của what-if). Mô tả tool liệt kê ba mã và test kiểm khớp file dữ liệu. REST thêm `GET /resilience/shocks` để giao diện vẽ ba thẻ R1 từ dữ liệu, không gắn cứng nhãn.

**Lộ trình, bộ tối ưu**

14. **Khối `roadmap` mang cả lý do sinh lại và lựa chọn khi chưa khả thi.** `reason` (`code`, `text` do code dựng từ sự kiện, `detail` là các con số của sự kiện, `behavior_flag_id`), `feasibility` (`on_track`, `relaxed`, `infeasible`), `goals` (từng mục tiêu: kịp hay không, thiếu bao nhiêu, mỗi tháng cần bao nhiêu), `alternatives` (đúng hai lựa chọn khi `infeasible`, rỗng ở các trường hợp khác: tiêu chí 4 "nói thẳng và đưa hai lựa chọn"), `counts` (số bước theo trạng thái), `rules_version`, `basis`. Bước (`RoadmapStep`): `reason` ("Vì sao", `ai_generated` nếu do model viết), `metrics` (số trước và sau do bộ tối ưu tính), `checked_rules`, `status` chờ / đã chấp nhận / đã từ chối kèm `decided_at`, `edited`, và `action` tùy chọn.
15. **Chấp nhận một bước KHÔNG tự thực hiện hành động và không đổi số dư.** `action = {tool, params}` với `tool` thuộc `move_between_jars`, `save_jars`, `schedule_nudge`: người dùng thực hiện bằng luồng xác nhận sẵn có (`POST /confirmations` rồi `POST /actions`, ADR-0002); hợp đồng không thêm đường ghi tiền thứ hai. `params` không được có `user_id` hay `confirm_token` (Pydantic và test kiểm). Lý do không dùng `options.action` (tham chiếu khối `confirm` đã phát): lộ trình sống nhiều ngày, không có khối `confirm` nào đang chờ, và số dư lúc bấm có thể đã khác; server chuẩn hóa lại và tính bản xem trước lúc người dùng bấm.
16. **Lưu và đổi trạng thái lộ trình KHÔNG qua token** (đúng câu của file phase: "lưu lộ trình là thao tác ghi không đổi số dư"), như `POST /feedback` và `audit___record_turn`. `planner___save_roadmap` vì thế KHÔNG thuộc `PLANNER_WRITE_TOOLS` hay `ACTION_TOOLS`, Cedar chỉ ép `user_id` (không `confirm_token`). Bù lại, **Lambda chạy lại `check_suitability` cho từng bước khi lưu** (vi phạm mức block thì `ROADMAP_INVALID`, không lưu; thông điệp nêu mã luật), nên prompt injection không lưu được bước vi phạm (tiêu chí 5: 0 lộ trình chứa hành động vi phạm). Mọi thao tác đổi trạng thái ghi `audit_events` và một dòng `feedback` (`block_id` là id khối `roadmap`, `option_id` là `step_id`; sửa một bước ghi `accepted` với lý do `edited`).
17. **`save_roadmap` nhận bản nháp** (`RoadmapDraft`): nội dung do Roadmap agent soạn, KHÔNG có phiên bản, trạng thái bước, `reason.text`, `headline`, `counts`, `basis`, `rules_version` (Lambda điền). `goals` và `alternatives` lấy nguyên từ kết quả `optimize_allocation` (mã gọi tool chuyển tiếp, không để LLM chép số). Sửa một bước (`POST /roadmap/steps/{step_id}/edit`) chỉ đổi số tiền hoặc ngày, lưu bản mới `active` (lý do `step_edited`, bước đã sửa `accepted` và `edited`), không gọi model, không sinh lại toàn bộ.
18. **`optimize_allocation` trả tiền bảo toàn**: tổng `proposed_monthly_vnd` cộng `unallocated_vnd` bằng `income_monthly_vnd` (Pydantic và test kiểm). `status` `optimal` (không nới gì, mọi sàn đạt), `relaxed` (đã nới đúng một vòng và ghi lại điều đã nới: lùi hạn mục tiêu hoặc giảm hũ không thiết yếu), `infeasible` (đã nới một vòng vẫn vô nghiệm, kèm đúng hai lựa chọn). **Vô nghiệm không phải lỗi của tool** (`status` OK, `data.status` là `infeasible`): tiêu chí 4 đòi nói thẳng và đưa lựa chọn. `AllocationLine.floor_gap_vnd` là biến elastic dương (phần sàn chưa đạt). `solver.elapsed_ms` để ghi độ trễ (tiêu chí 8).
19. **Sinh lại chạy nền đi qua bảng và sự kiện, trả HTTP 200 (không 202)**: `POST /roadmap/regenerate` ghi dòng `roadmap_jobs`, phát `roadmap.regeneration_requested` (SAU commit, `event_id` = `job_id`, `note` tự do của người dùng ở lại job để sự kiện không có PII) và trả job ngay. Dùng 200 vì test hợp đồng REST yêu cầu mọi mã khác 200 phải thuộc bảng mã lỗi (`HTTP_STATUS`); 202 không phải lỗi. Sự kiện mới thứ hai `behavior.changed` (nguồn `yofina.forecast`, chỉ phát khi PELT XÁC NHẬN; dấu hiệu "nghi" không phát; `event_id` = `flag_id`). `profile.updated` đã có phục vụ "đổi mục tiêu hoặc thu nhập": nếu luồng C cần biết trường nào đổi, hợp đồng đã có `fields` (`salary`, `jars`).

**REST, khối, tool**

20. **Mười ba endpoint mới** (đều Bearer JWT; điểm chống chịu và cú sốc `x-lambda: forecast`, còn lại `ledger`): `GET /resilience`, `GET /resilience/shocks`, `POST /resilience/stress`; `GET /roadmap`, `GET /roadmap/versions`, `GET /roadmap/diff`, `POST /roadmap/steps/{step_id}/decision`, `POST /roadmap/steps/{step_id}/edit`, `POST /roadmap/versions/{version}/decision`, `POST /roadmap/regenerate`, `GET /roadmap/jobs/{job_id}`; `GET /review`, `POST /review/daily-ask/skip`. `POST /resilience/stress` là POST chỉ để có thân yêu cầu, không ghi. Không PATCH. Test "không có đường ghi tắt" liệt kê tường minh các POST không đổi số dư.
21. **Gán hũ kèm phạm vi luật dùng lại `assign_jar`, không có đường ghi thứ hai** (đúng yêu cầu điều phối): `remember` `once` hoặc `always` đã có từ phase 2. "Đúng rồi" với một mục "Xem lại" là `assign_jar` với CHÍNH hũ hiện tại (xóa cờ cần xem lại, ghi `classified_by` user và nhãn k-NN, không chuyển tiền): luồng B cài hành vi này (hiện `assign_jar` cùng hũ có thể bị từ chối). Tool `ledger___get_unclassified` giữ nguyên đầu vào, chỉ mở rộng KẾT QUẢ tương thích ngược (`tier`, `classified_by`, `confidence` ở mục; `confidence`, `reason` ở gợi ý). Hai chế độ của "Xem lại" và hỏi gộp là khối `review_list` (`mode` review hoặc daily_ask), lấy từ `GET /review`; `count` và `pending_total_vnd` là của cả tập để Tổng quan và màn dự báo hiện "chưa phân loại". Khối này không có `basis` (số của sổ cái, không phải ước lượng).
22. **Mã lỗi mới (thêm cuối)**: `ROADMAP_NOT_FOUND` (404; chưa có lộ trình, hoặc không có phiên bản, bước, job; của người khác cũng như không có), `ROADMAP_INVALID` (422), `ROADMAP_VERSION_CONFLICT` (409; bản gốc đã bị thay hoặc bản không còn chờ chọn), `SHOCK_NOT_FOUND` (404). Frontend `errors.ts` đã thêm bốn mã và thông báo (test `openapi.test.ts` so khớp).
23. **Cedar và Gateway**: mỗi tool mới một file `gateway/policies/<tool>.cedar` (CDK bắt buộc; `FAIL_ON_ANY_FINDINGS`). **`agent-stack.ts` tự đăng ký mọi tool trong `forecast.json` và `planner.json` ở lần deploy `YofinaAgent` kế tiếp; Lambda chưa cài sẽ trả "Tool không tồn tại" (`PARAMS_INVALID`)**. Chấp nhận được cho tới khi luồng A cài. `wallet.PHASE4_TOOLS` liệt kê năm tool chưa cài; test `test_ledger_wallet` dùng nó để khỏi đòi `_ARG_KEYS`: luồng A xóa từng tên khi cài xong. Schema Gateway của `optimize_allocation` có tham số kiểu `number` (`weight`): Gateway sinh kiểu Cedar `Decimal`, không ảnh hưởng policy (chỉ ép `user_id`). Độ sâu lồng của `save_roadmap` là bảy cấp (`phases[].steps[].action.params`); tài liệu AgentCore không nêu giới hạn độ sâu, nhưng nếu `cdk deploy` từ chối thì làm phẳng `action` (đề xuất: `action_tool` và `action_params`).
24. **Agent: chỉ khai báo ba ý định `resilience`, `stress`, `roadmap`** (`wallet.INTENTS`, `agent/.../schemas.py` `Intent`). `IntentResult` là mô hình đầu ra của router, nên JSON schema của router NAY liệt kê ba giá trị mới (test `test_schema_router_phang_va_day_du` đã cập nhật). **Một dòng sửa ngoài hợp đồng thuần**: `turn.py` đổi `handler = {...}[routed.intent]` thành `.get(routed.intent, self.on_out_of_scope)`, vì nếu không router trả `resilience` (rất khớp "điểm chống chịu bao nhiêu") sẽ làm `KeyError` cả lượt. Luồng C thay bằng bộ xử lý thật. `ROUTER_SYSTEM` chưa nhắc ba ý định này; `IntentParams` chưa có chỗ cho `shock_id` (luồng C thêm khi cài router).
25. **Frontend chỉ chạm tối thiểu** (như phase 3 làm): `errors.ts` thêm bốn mã; `frontend/src/contracts/blocks.ts` sinh lại (năm khối có Zod, `ALL_BLOCK_TYPES` 21, `BLOCK_TYPES` vẫn 16 vì `REGISTERED_BY_FRONTEND` chưa thêm); `registry.test.tsx` lọc fixture hợp lệ theo khối đã đăng ký; `walletBlocks.test.tsx` đổi số đếm. Luồng D bỏ hai chỗ này khi đăng ký view.

### Cho các luồng sau

Phân việc theo người: **luồng A (ML) và B (phân hũ tự động) do Phúc** (máy mạnh, chạy nặng, deploy); **luồng C (agent) và D (frontend) do Học** (máy yếu, chỉ chạy unit test agent và frontend, code theo fixture trong `contracts/fixtures/`, KHÔNG deploy). `contracts/` chỉ đổi khi hai bên báo nhau (đổi hợp đồng là sửa ở `contracts/` trước, sinh lại, chạy `uv run pytest`). Chỉ một luồng deploy tại một thời điểm; **không deploy phase 4 trước khi F1 và F3 lên môi trường thật** (đã xong 23/11). Thứ tự deploy: migration `0052` (migrator) → `YofinaTools` → `YofinaAgent` → Runtime → Amplify.

**Luồng A — ML, điểm chống chịu, cú sốc, LP, điểm gãy (Phúc)**

- Sửa được: `ml/yofina_ml/` (điểm chống chịu, stress, LP, bộ phát hiện đổi hành vi), `gateway/tools/forecast/` (cài `get_resilience_score`, `stress_test`; REST `GET /resilience`, `GET /resilience/shocks`, `POST /resilience/stress`), `gateway/tools/planner/` (cài `optimize_allocation`, `save_roadmap`, `get_roadmap`), `pipelines/nightly/` (bước tính điểm, PELT, phát `behavior.changed`), file mới `gateway/tools/ledger/yofina_ledger/roadmap_*.py` (REST `/roadmap*` và job: ledger Lambda phục vụ chúng; một mô-đun riêng để không đụng luồng B), `data/personas/` (điểm gãy cài sẵn cho `minh`, v1 đến v3), `scripts/` (script thêm hai tuần giao dịch lệch mức cũ, tiêu chí 3).
- Phải làm: đọc ngưỡng từ `resilience_defaults.json` và cú sốc từ `shocks.json` (không đặt số trong mã); khi cài mỗi tool mới xóa tên khỏi `wallet.PHASE4_TOOLS` và thêm vào `_ARG_KEYS` của `gateway_api.py`; thêm các bảng mới (`resilience_scores`, `roadmaps`, `roadmap_jobs`, `behavior_flags`) vào `RESET_DELETES` của ledger (`repo.py`; luồng B thêm `tx_embeddings_labeled`, `review_asks`; một người sửa, người kia báo, vì cùng một danh sách); đăng ký route mới trong `infra-cdk/lib/tools-stack.ts` (route đang liệt kê tay, không đọc OpenAPI; `x-lambda: forecast` thì tích hợp Lambda forecast như `/affordability`); hiệu chỉnh penalty PELT trên ba persona và bộ sinh khác họ, ghi tỷ lệ báo nhầm vào `detail`; đo thời gian LP (`solver.elapsed_ms`).
- **Đã chốt 23/11 (chủ dự án giao người điều phối chọn): nơi chạy scipy cho `optimize_allocation`.** Target `planner` GIỮ NGUYÊN trên Lambda `yofina-ledger`; `optimize_allocation` ở ledger dựng bài toán rồi gọi `Invoke` đồng bộ sang Lambda forecast (có sẵn numpy và scipy) để giải `linprog`, theo đúng mẫu `yofina_ledger/forecast_client.py` đang dùng để tính dự báo (thêm một thao tác giải LP vào hàm đó, IAM `grantInvoke` đã có ở `tools-stack.ts`). Lý do:
  - Không thêm scipy vào zip ledger: zip ledger 3,9 MB, zip forecast 44 MB nén (khoảng 160 MB giải nén); ledger phục vụ MỌI route REST nên phình zip làm chậm khởi động nguội của cả API chỉ vì một tool ít gọi (đây cũng là lý do `forecast_client.py` tồn tại).
  - Không trỏ cả target `planner` sang forecast: target đó còn `schedule_nudge` (tool ghi, cần secret ký token xác nhận) và `save_roadmap` (ghi DB); chuyển đi thì có hai Lambda cầm đường ghi và secret, đi ngược "một đường ghi" (ADR-0002) và phải thêm IAM, secret cho forecast.
  - Hợp đồng không đổi (tên `planner___optimize_allocation`, schema vào/ra giữ nguyên); chỉ tốn thêm một lần gọi Lambda khi lập lộ trình (việc vốn đã mất vài giây vì gọi model). Ghi `solver.elapsed_ms` là thời gian giải ở forecast; nếu cần, thêm thời gian gọi vào `detail`.
  - Phương án (a) thêm scipy vào ledger và (b) đổi `arn` target `planner` sang forecast: không chọn.
- Hợp đồng giao: `forecast___get_resilience_score`, `forecast___stress_test`, `planner___optimize_allocation`, `planner___save_roadmap`, `planner___get_roadmap` (schema vào ở `contracts/tools/{forecast,planner}.json`, kết quả ở `*.results.schema.json`, fixture `contracts/fixtures/tools/<tool>.*.json`), bảng `resilience_scores`, `roadmaps`, `roadmap_jobs`, `behavior_flags` và hàm `app_*` ở `0052`, sự kiện `behavior.changed`.

**Luồng B — Pipeline sự kiện, phân hũ tự động (Phúc)**

- Sửa được: `pipelines/event/` (Lambda `yofina-classify`, SQS có DLQ), `gateway/tools/ledger/` phần phân loại (file mới `review_*.py`, `classify_*.py`; `assign_jar`, `get_unclassified`), `evals/classification/`, `ml/yofina_ml/` chỉ phần phân loại (thư mục con riêng), `infra-cdk/lib/` construct phân loại (file mới), `data/personas/` nhãn seed cho `tx_embeddings_labeled`.
- Phải làm: bước 0 bảng tra loại → bước 1 `category_rules` → bước 2 embedding (chuẩn hóa chuỗi bỏ dấu và chữ thường, khớp chuỗi chính xác `app_find_labeled_exact` trước rồi `app_knn_labeled`; ghi `tx_embeddings`; ngưỡng cosine là cấu hình) → bước 3 model nhỏ; ba mức tin cậy (`wallet.CLASSIFICATION_TIERS`, ngưỡng trong cấu hình, hiệu chỉnh trên dữ liệu); hỏi gộp một lần mỗi ngày (`review_asks`); `assign_jar` ghi nhãn k-NN và luật `once` hoặc `always`, nâng `payees.auto_min_confidence` khi sửa nhiều lần, chấp nhận gán cùng hũ hiện tại để xác nhận "đúng rồi"; mở rộng KẾT QUẢ `get_unclassified` (không đổi đầu vào); REST `GET /review`, `POST /review/daily-ask/skip` (qua hàm `app_get_review_list`, `app_get_review_ask`); che tên người nhận và số tài khoản trước khi vào model; bộ kiểm thử ít nhất 300 dòng có chuyển khoản tên riêng không lời nhắn.
- Hợp đồng giao: khối `review_list`, `contracts/tools/ledger.results.schema.json` (phần mở rộng), bảng `tx_embeddings`, `tx_embeddings_labeled`, `review_asks`, cột `payees` mới.

**Luồng C — Agent (Học; không deploy, chạy unit test agent)**

- Sửa được: `agent/` (và `tests/unit/agent/`); nếu cần Lambda `yofina-roadmap-regen`: thư mục mới `pipelines/roadmap/` (luồng C viết mã và test, Phúc deploy). KHÔNG sửa `gateway/`, `contracts/`, `libs/yofina_core` (báo Phúc).
- Phải làm: bộ xử lý thật cho ba ý định (`on_resilience`, `on_stress`, `on_roadmap`) thay dòng `.get(..., on_out_of_scope)` ở `turn.py`; cập nhật `ROUTER_SYSTEM` và `IntentParams` (thêm tham số cho `shock_id`) CHỈ sau khi bộ xử lý chạy được; chat trả khối `resilience_score`, `stress_result`, `roadmap` bằng `build_*` của `yofina_core.blocks` (bọc `data` của tool, LLM không viết số); Roadmap agent (Sonnet 4.6): gom ngữ cảnh → phác giai đoạn → `optimize_allocation` → `check_suitability` → sửa tối đa 2 vòng, hết vòng thì bỏ bước vi phạm → `save_roadmap` với `RoadmapDraft` (`goals` và `alternatives` chuyển nguyên từ kết quả tối ưu); dùng `status_for_new_version`; Lambda sinh lại nghe `behavior.changed`, `roadmap.regeneration_requested`, `profile.updated`, đọc job theo `job_id`, cập nhật `stage` và `progress`, gọi Runtime bằng danh tính dịch vụ kèm `user_id` (tra tài liệu AgentCore trước khi chọn; phương án dự phòng: chạy cùng mã agent trong Lambda); cổng nhắc tối thiểu (thẻ chủ động chọn một việc; `proactive_card` đang do `GET /overview` chọn ở `yofina_ledger/proactive.py`, sửa chỗ đó là việc của Phúc, luồng C chỉ đề xuất thứ tự ưu tiên); evals `golden/phase4.jsonl` (≥ 12 câu) và `adversarial/phase4.jsonl` (≥ 10 câu).
- Code theo fixture: `contracts/fixtures/tools/{get_resilience_score,stress_test,optimize_allocation,save_roadmap,get_roadmap}.*.json`, `contracts/fixtures/blocks/valid/{resilience_score,stress_result,roadmap,roadmap_diff,review_list}.*.json`.

**Luồng D — Frontend (Học; không deploy, chạy test frontend)**

- Sửa được: `frontend/` và đúng MỘT dòng `REGISTERED_BY_FRONTEND` trong `scripts/gen_contracts.mjs` (thêm năm khối khi đăng ký view, rồi `node scripts/gen_contracts.mjs`; không sửa tay `frontend/src/contracts/blocks.ts`). Khi đó bỏ dòng lọc trong `registry.test.tsx` và đổi `walletBlocks.test.tsx` về 21 khối.
- Phải làm: tab "Nhìn trước" R1 (gauge SVG, ba thẻ cú sốc đọc từ `GET /resilience/shocks`), R2 (điểm tụt có animation số, `runway_days_total`, `runway_days_emergency`, `shortfall_vnd`, nút "Xem lộ trình thích ứng"), R3 (bốn thành phần có giải thích, dòng `disclaimer`); lộ trình L1 đến L3 (phiên bản và `reason`, `counts`, bước Chấp nhận / Sửa / Từ chối qua `POST /roadmap/steps/{step_id}/decision` và `/edit`, "Vì sao" là `reason` của bước, so với bản cũ bằng `GET /roadmap/diff`, "Dùng bản mới" / "Giữ bản cũ" qua `POST /roadmap/versions/{version}/decision`, tiến độ sinh lại bằng polling `GET /roadmap/jobs/{job_id}`, `alternatives` khi `infeasible`); thực hiện `action` của bước bằng luồng xác nhận sẵn có (`createConfirmation` rồi `applyAction`, không tự gọi tool ghi); A1 và A2 từ `GET /review` (sửa bằng một chạm qua `assign_jar` với `remember` once hoặc always); số chưa phân loại (`pending_total_vnd`) ở Tổng quan và màn dự báo; Zod cho các kiểu REST mới ở `frontend/src/api/` (kiểu khối đã có sẵn ở `contracts/blocks.ts`).
- Code theo fixture: `contracts/fixtures/blocks/valid/*` (năm khối), `contracts/fixtures/rest/` (`ResilienceScoreResponse.*`, `StressResultResponse.*`, `ShocksResponse.*`, `RoadmapResponse.*`, `RoadmapDiffResponse.*`, `RoadmapVersionsResponse.*`, `RoadmapJob.*`, `ReviewListResponse.*`, `Roadmap*Request.*`, `RegenerateRoadmapRequest.*`). Ba trạng thái (chờ, đã chấp nhận, đã từ chối) và nhóm điểm luôn kèm chữ.

**Cố ý để cho luồng sau (hợp đồng không làm)**: công thức điểm và mô phỏng cú sốc; bộ tối ưu LP và ngưỡng của từng ràng buộc; bộ phát hiện đổi hành vi; ngưỡng cosine và ngưỡng ba mức tin cậy; Lambda phân loại, Lambda sinh lại, Roadmap agent, router, giao diện; seed persona `minh` (v1 đến v3) và nhãn k-NN; `RESET_DELETES`; thêm route vào `tools-stack.ts`; chọn nơi chạy scipy; đo p95 (tiêu chí 8 và 9). Hợp đồng KHÔNG chạy migration `0052` trên Aurora, không deploy gì.
