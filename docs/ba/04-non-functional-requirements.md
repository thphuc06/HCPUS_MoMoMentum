# Yêu cầu phi chức năng (NFR)

> Bản nháp để chủ dự án duyệt, tổng hợp ngày 22/11/2026. Mười nhóm NFR giữ theo proposal §5. File này thêm **chỉ tiêu đo được**, **cách đo** và **số đo hiện có** cho từng mục. Những mục proposal viết định tính (quyền riêng tư, chi phí, thiết bị) được đề xuất chỉ tiêu, cần chủ dự án duyệt.
> Số đo lấy từ spike và test thật, xem [requirements.md](../requirements/requirements.md#ghi-chú-từ-số-đo-2026-11-21) và [spike-vertical-slice.md](../research/spike-vertical-slice.md). Mọi số đo ML là **trên dữ liệu tổng hợp**.

**Trạng thái:**
- **Đạt**: đã đo, đạt chỉ tiêu.
- **Chưa đạt**: đã đo, chưa đạt.
- **Chưa đo**: chưa có số đo.
- **Đề xuất**: chỉ tiêu do người tổng hợp đề xuất, cần duyệt.

> Số đo cập nhật 24/11/2026 tối theo kết quả phase 3–5; tổng hợp ở [13 mục 5](13-tien-do-technical.md#5-số-đo-hiện-có-cho-slide-và-nfr). Ngoài bảng: `ApplyGuardrail` p50 446 ms (mục tiêu 400 ms).

## 1. Hiệu năng và độ trễ

| ID | Yêu cầu | Chỉ tiêu | Cách đo | Hiện trạng | Trạng thái |
|---|---|---|---|---|---|
| NFR-01 | Chữ hoặc khối đầu tiên của câu trả lời hiện nhanh | Dưới **1,5 giây** (phiên ấm) | Đo từ lúc gửi tới event đầu, 10 lượt | Phiên ấm 0,34 giây; **phiên lạnh trung vị 2,04 giây** | Ấm: Đạt. Lạnh: Chưa đạt. Đề xuất: làm nóng phiên khi mở màn chat, hiện tiến độ cho lượt đầu, nới chỉ tiêu lượt đầu còn 3 giây (cần quyết) |
| NFR-02 | Kiểm tra trước khi quẹt (FR6) | p95 dưới **2 giây** | `POST /affordability`, 10 lượt, phiên ấm | p50 191 ms, p95 282 ms (`scripts/measure_phase3.py`, 23/11) | Đạt |
| NFR-03 | What-if trọn câu (FR5) | p95 dưới **8 giây** | 10 lượt, phiên ấm | Trọn câu p50 16,7 giây, p95 28,2 giây; khối đầu p50 6,9 giây (23/11) | **Chưa đạt** |
| NFR-04 | Màn Tổng quan tải dữ liệu | p95 dưới **300 ms** đo từ Lambda | Log thời gian của `app_get_overview` | Đang gộp thành một lệnh gọi (migration 0007) | Chưa ghi số (tiêu chí 10 phase 2) |
| NFR-05 | Dự báo cập nhật sau giao dịch | Dưới **1 phút** từ lúc ghi | Integration test | Backend báo dự báo mới có sau 3–4 giây | Đạt theo báo cáo, chờ kiểm trên trình duyệt |
| NFR-06 | Batch đêm | Xong cho mọi tài khoản demo trước 06:00 | Step Functions `yofina-nightly` | Monte Carlo 7 hũ × 10.000 đường khoảng 0,65 giây mỗi người dùng. *Đề xuất 24/11:* bộ hũ mẫu có tới 9 hũ (BR-70), nhưng hũ đệm và dài hạn không chạy Monte Carlo (BR-73), nên số hũ cần mô phỏng gần như không tăng; cần đo lại khi đổi bộ hũ | Chưa ghi số trọn batch |

## 2. Độ đúng của số

| ID | Yêu cầu | Chỉ tiêu | Cách đo | Hiện trạng | Trạng thái |
|---|---|---|---|---|---|
| NFR-07 | Số trong câu trả lời khớp kết quả tool | **100%** câu trả lời đã phát | Evaluator `NumericGrounding` trên bộ golden | Golden phase 3: 100%; golden phase 5: 91,7% | Đạt ở phase 3; phase 5 chưa đạt |
| NFR-08 | LLM không tự làm phép tính | 0 phép tính trong câu chữ không có nguồn tool | Như trên | Thiết kế: mọi số qua tool | Chưa đo |
| NFR-09 | Tiền không sai số | Số nguyên VND ở mọi tầng; bất biến số dư hũ = tổng dòng sổ cái | Unit test, ràng buộc DB | Đã có test | Đạt |
| NFR-44 **[đề xuất 24/11]** | Đổi cơ cấu hũ không làm sai tiền | Áp bộ hũ mẫu, thêm/bớt hũ hoặc chuyển giai đoạn (BR-70, BR-71): tổng tỷ lệ luôn = 100%, **tổng số dư không đổi**, mọi khoản chuyển giữa hũ có dòng sổ cái và đi qua xác nhận (BR-45) | Unit test; kiểm bất biến NFR-09 trước và sau | — | Chưa làm |

## 3. Chất lượng dự báo

| ID | Yêu cầu | Chỉ tiêu | Cách đo | Hiện trạng | Trạng thái |
|---|---|---|---|---|---|
| NFR-10 | Tốt hơn baseline | Pinball loss thấp hơn seasonal naive trên **cả hai** bộ sinh dữ liệu | Backtest rolling-origin | Pinball bằng 0,64 lần seasonal naive ([backtest](../research/backtest-phase-2.md)) | Đạt |
| NFR-11 | Khoảng 80% đúng nghĩa | Độ phủ tổng 30 ngày trong **0,75–0,85**; chưa đạt thì hiện nhóm tin cậy thay cho % (BR-31) | Backtest | Độ phủ 0,79–0,82 sau ACI | Đạt |
| NFR-12 | Báo trước đủ sớm | Số ngày cảnh báo trước khi hũ cạn, tỷ lệ cảnh báo đúng (KPI proposal §6) | Backtest 3 persona | — | Chưa đo; Đề xuất: ghi vào báo cáo phase 6 |

## 4. Phân loại giao dịch

| ID | Yêu cầu | Chỉ tiêu | Cách đo | Hiện trạng | Trạng thái |
|---|---|---|---|---|---|
| NFR-13 | Phân hũ đúng | Từ **90%** trên bộ kiểm thử persona | Bộ test có nhãn | 92% trên phần tự gán (phase 4) | Đạt |
| NFR-14 | Ít làm phiền | Dưới **10%** giao dịch phải hỏi người dùng | Như trên | 17,4% (phase 4) | **Chưa đạt** |

## 5. Độ tin cậy

| ID | Yêu cầu | Chỉ tiêu | Cách đo | Hiện trạng | Trạng thái |
|---|---|---|---|---|---|
| NFR-15 | LLM lỗi vẫn có kết quả | What-if và kiểm tra trước khi quẹt vẫn trả thẻ số khi ép lỗi model (trần về 0, sai model id) | Test ép lỗi | `test_degraded_live.py` 6/6 (phase 3) | Đạt |
| NFR-16 | Sự kiện không tính hai lần | Gửi trùng sự kiện: số dư và dự báo không đổi lần hai | Integration test | Idempotent theo `event_id` (DynamoDB), DLQ có alarm | Đạt theo test, chờ soát tiêu chí 9 phase 2 |
| NFR-17 | Luồng stream đứt hoặc rỗng | UI coi là lỗi và cho thử lại | Test frontend | Đã biết Runtime trả HTTP 200 rỗng khi lỗi | Chưa kiểm hết |
| NFR-18 | Sẵn sàng trong thời gian chấm | App và API phản hồi trong khung chấm; Aurora **không được tự tắt** | Health check thủ công trước ngày chấm | Aurora 0,5 ACU chạy liên tục | Đề xuất: checklist trước chấm ở phase 6 |

## 6. Bảo mật

| ID | Yêu cầu | Chỉ tiêu | Cách đo | Hiện trạng | Trạng thái |
|---|---|---|---|---|---|
| NFR-19 | Xác thực | Mọi API và Runtime yêu cầu JWT Cognito (access token); tắt tự đăng ký | Integration test | Có | Đạt |
| NFR-20 | Tách dữ liệu theo người dùng | **0** lượt đọc hoặc ghi dữ liệu người khác trong bộ đối kháng | Interceptor ghi đè `user_id`, Cedar, RLS; bộ test tấn công | 3 lớp đã chạy ở phase 1 | Đạt ở phase 1; chạy lại bộ đối kháng ở phase 3 |
| NFR-21 | Mặc định từ chối | Tool call bị chặn trừ khi có luật cho phép | Cedar ở chế độ `ENFORCE` | Có | Đạt |
| NFR-22 | Không ghi khi chưa xác nhận | **0** lượt ghi không có token hợp lệ (13 ca: tự điền cờ, bịa token, ký sai khóa, đổi tham số, dùng lại, token người khác, hết hạn) | Unit và integration test | Có | Đạt |
| NFR-23 | Mã hóa | Mã hóa khi lưu (Aurora, S3, DynamoDB) và khi truyền (HTTPS) | Soát cấu hình CDK | Mặc định của dịch vụ | Đề xuất: soát và ghi bằng chứng ở phase 6 |
| NFR-24 | Không lộ bí mật | Repo public không chứa account ID, ARN, secret, mật khẩu, email | Quét trước mỗi commit | Quy ước có | Đề xuất: thêm bước quét tự động |
| NFR-25 | Chống prompt injection | Nội dung tệp và câu hỏi không kích hoạt được tool ghi | Bộ đối kháng (phase 3, 5) | Đối kháng phase 3 16/16; tệp tấn công phase 5 14/14 | Đạt |

## 7. Quyền riêng tư

| ID | Yêu cầu | Chỉ tiêu | Cách đo | Hiện trạng | Trạng thái |
|---|---|---|---|---|---|
| NFR-26 | Che thông tin định danh trước LLM | 0 số tài khoản, số điện thoại, tên người nhận dạng thô trong log model và bộ nhớ | Quét log trên bộ ảnh và CSV thử | PII đã che trong DB và log Lambda; chưa có log model để đối chiếu (phase 5) | Đạt một phần |
| NFR-27 | Thu thập tối thiểu | Chỉ lương và ngày nhận là bắt buộc; mỗi nguồn nạp có đồng ý riêng | Soát màn hình | Onboarding đã đúng | Một phần |
| NFR-28 | Xóa theo yêu cầu | "Xóa dữ liệu của tôi" làm sạch Aurora, S3, Memory của người đó trong **dưới 1 phút** | Test trên tài khoản thử | Xóa sạch Aurora, S3, Memory trên `khoa` (phase 5, sau sửa); thời gian chưa ghi | Đạt; thời gian là Đề xuất |
| NFR-29 | Minh bạch nơi xử lý | Công bố việc model có thể xử lý ngoài Singapore | Soát màn quyền riêng tư | — | Cần quyết (C-09) |
| NFR-30 | Gắn nhãn AI | 100% câu trả lời của trợ lý có nhãn "do AI tạo" | Soát giao diện | — | Đề xuất (BC-05, C-08) |

## 8. Giải thích và kiểm toán

| ID | Yêu cầu | Chỉ tiêu | Cách đo | Hiện trạng | Trạng thái |
|---|---|---|---|---|---|
| NFR-31 | Mọi lượt có trace | **100%** lượt hội thoại có `trace_id` giữ từ client tới app | Đếm trace / lượt | Màn trace đọc từ `audit_events`: 18 bước có thời gian (phase 5) | Một phần; Transaction Search chưa bật |
| NFR-32 | Truy được gợi ý | Mọi gợi ý truy về dữ liệu và luật trong `audit_events` | Soát mẫu | Xác nhận và ghi đã có audit | Một phần |
| NFR-33 | Không lọt vi phạm | **0** gợi ý vi phạm suitability trong bộ đối kháng 50 câu | Bộ đối kháng | 42 câu đối kháng qua phase 3–5, 0 vi phạm; lỗ hổng hũ Dự phòng đã vá (T-01); phase 6 thêm 8 ca cho đủ 50 (Q10) | Đạt một phần (chưa đủ 50 câu) |

## 9. Chi phí và tài nguyên

| ID | Yêu cầu | Chỉ tiêu | Cách đo | Hiện trạng | Trạng thái |
|---|---|---|---|---|---|
| NFR-34 | Ngân sách | Có AWS Budgets và cảnh báo 50/80/100%. Mức ngân sách tháng do chủ dự án đặt (đề xuất 100 USD) | Budgets, Cost Explorer | Budgets có; Aurora khoảng 2,4 USD/ngày | Một phần (Cost Explorer còn trễ) |
| NFR-35 | Trần lượt gọi model | Mỗi ngày: 400 lượt Sonnet, 2.000 lượt model nhỏ, 3.000 lượt embedding; chạm trần thì về thẻ số | DynamoDB `yofina-usage` | Có module `yofina_core.llm` | Đạt (cơ chế) |
| NFR-36 | Lượt gọi mỗi câu | What-if tối đa 4 lượt gọi model; đường nhanh và F3 không cần LLM để ra số | Đếm trong trace | Trần 4 đã cấu hình | Đạt (cơ chế) |
| NFR-37 | Chi phí mỗi lượt hội thoại | Ghi được chi phí trung bình mỗi lượt (KPI proposal §6) | Token trong log | Có ghi token | Đề xuất: tính và báo cáo ở phase 6 |

## 10. Ngôn ngữ, thiết bị và khả năng dùng

| ID | Yêu cầu | Chỉ tiêu | Cách đo | Hiện trạng | Trạng thái |
|---|---|---|---|---|---|
| NFR-38 | Tiếng Việt | Giao diện và câu trả lời tiếng Việt; tiền theo định dạng Việt Nam | Soát | Có | Đạt |
| NFR-39 | Ưu tiên điện thoại | Đi được 6 cảnh demo ở khung 390x844; chạy trên Chrome máy tính và **Safari iPhone** | Chủ dự án tự thử trên máy thật | Khung 390 px đạt khi đi cảnh 2 (23/11); Học thử nạp ảnh trên điện thoại | Một phần; Safari iPhone chưa ghi |
| NFR-40 | Không dựa vào màu | Đủ, sát, hụt luôn có biểu tượng kèm chữ | Soát giao diện | Thiết kế có | Chờ soát |
| NFR-41 | Độ tương phản | Chữ đạt WCAG 2.1 AA (4,5:1) ở chế độ sáng | Kiểm bằng công cụ | — | Đề xuất |
| NFR-42 | Trạng thái màn hình | Mọi màn có trạng thái tải, lỗi, rỗng | Soát | Thiết kế có | Chờ soát |
| NFR-43 | Chịu tải demo | Tối thiểu 6 tài khoản demo dùng cùng lúc mà không vượt quota model 10 request/phút | Thử 3 tài khoản song song | — | Đề xuất; quota là ràng buộc BC-11 |

## Việc cần chủ dự án quyết

1. NFR-01: có nới chỉ tiêu cho lượt đầu phiên lạnh không (đề xuất 3 giây), hay giữ 1,5 giây và chấp nhận không đạt?
2. Duyệt các chỉ tiêu đề xuất: NFR-18, 23, 24, 28 (thời gian xóa), 30, 37, 41, 43.
3. NFR-31: có bật CloudWatch Transaction Search không? Đây là thay đổi mức tài khoản và có phí ghi span.
4. NFR-34: chốt mức ngân sách tháng.
