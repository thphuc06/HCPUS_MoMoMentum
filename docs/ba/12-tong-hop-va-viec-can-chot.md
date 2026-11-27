# 12. Tổng hợp thảo luận và danh sách việc cần chốt

> Cập nhật 25/11/2026 theo **hạn nộp thật 03/12** và kiểm toán 25/11; phần bộ hũ cập nhật 26/11 (issue #39); mô hình kinh doanh chốt 26/11. File này gom các kết luận của bộ tài liệu BA (01–11) và **mọi câu hỏi đang mở** vào một chỗ, xếp theo thời điểm cần chốt. Mỗi dòng trỏ về file gốc; khi chốt, sửa ở file gốc rồi đánh dấu ở đây.

## 1. Đã thảo luận và kết luận gì

| # | Chủ đề | Kết luận chính | File |
|---|---|---|---|
| 1 | Bối cảnh thị trường, pain point | 7 pain point (P1–P7) của người 18–30. Nặng nhất: không biết trước lúc thiếu tiền, phí trả sau không thấy trước, nhiều tài khoản trả sau, quỹ đệm mỏng. Khoảng trống thị trường: các ví mạnh ở "nhìn lại", chưa ai làm "nhìn trước" | [01](01-boi-canh-thi-truong.md) |
| 2 | Phạm vi người dùng | Giữ **18–30 theo giai đoạn sống**, không đổi sang Gen Z, vì trả sau yêu cầu từ 18 tuổi và Gen Z năm 2026 có cả người 14–17 (BC-13) | [01](01-boi-canh-thi-truong.md), [02](02-business-rules.md) |
| 3 | Quy tắc nghiệp vụ, yêu cầu | BC-01 đến 13, BR-01 đến 78, FR1–FR15, NFR-01 đến 44, AC theo Cho trước / Khi / Thì | [02](02-business-rules.md)–[05](05-acceptance-criteria.md) |
| 4 | Cơ cấu hũ mới | Hũ tích lũy chia 4 mục đích: đệm, quỹ dồn, mục tiêu, dài hạn. Hũ Hóa đơn chuyển sang nghĩa vụ. 3 bộ hũ mẫu theo giai đoạn sống. Đã nối vào BR, FR, NFR, AC, luồng L19–L20, KPI K10, bảng gói. **Chốt 26/11** (chủ dự án, issue #39, đã deploy): tài khoản mới nhận 3 hũ mặc định theo mục đích (Chi hằng ngày 42%, Nghĩa vụ 33%, Dự phòng 25%), hũ khác là hũ tự thêm; Hóa đơn gộp vào hũ Nghĩa vụ chung; ví demo giữ hũ tự thêm Ăn uống, Đi lại, Giải trí, Du lịch (mục tiêu), Đầu tư. Bộ hũ theo giai đoạn sống hoãn. Muốn theo dõi riêng một khoản thì tách hũ; phân tích theo nhóm loại chi bên trong hũ gộp để sau hạn nộp | [02 mục B2a](02-business-rules.md#b2a-cơ-cấu-hũ-theo-mục-đích-và-giai-đoạn-sống-đề-xuất-2411), [07](07-dac-ta-luong-hoat-dong.md) |
| 5 | Đối thủ | Chỉ dùng nguồn chính thức. Cùng món hàng 1,2 triệu, tổng phải trả dao động 0–13,5% tùy ví và số ngày trễ. VNPAY không xét là đối thủ (24/11) | [09](09-phan-tich-doi-thu.md) |
| 6 | Mô hình kinh doanh | **B2B2C qua ví**. 3 gói theo mức dùng AI; phần an toàn có ở mọi gói. 7 nguồn thu R1–R7. Không thu hoa hồng khoản vay, không bán dữ liệu, không quảng cáo trong tư vấn | [06](06-mo-hinh-kinh-doanh.md) |
| 7 | Luồng hoạt động, human-in-the-loop | 20 luồng. Agent chỉ đọc và đề nghị; mọi thao tác ghi đi qua xem trước và token xác nhận dùng một lần. Đây là human-in-the-loop ở mức con người duyệt từng hành động | [07](07-dac-ta-luong-hoat-dong.md) |
| 8 | KPI | K1–K11 theo 3 mốc (cuộc thi, pilot, năm đầu), mỗi KPI có benchmark và lý do vì sao đạt được. **K4 (giảm phí trễ ≥ 10%)** dựa trên thử nghiệm AFM trên trả sau: SMS nhắc hạn giảm 21–24% số khách bị phí trễ, nhóm tuổi trung bình 29 | [08](08-kpi-kinh-doanh.md) |
| 9 | Stakeholder | 6 nhóm. Chỉ xác nhận bằng token và bảng "Vì sao" có lợi cho mọi bên. 5 xung đột lợi ích, lớn nhất là phí chậm trả của bên cho vay | [10](10-tac-dong-stakeholder.md) |
| 10 | Chi phí người trẻ và lợi ích đối tác | Phí cố định 33.000 ₫/tháng tương đương khoảng 40–79%/năm trên dư nợ nhỏ. 6 đòn bẩy G1–G6. Bên cho vay có lời ròng nếu từ khoảng 1,9% ca trễ bị mất gốc, hoặc ngay lập tức nếu có G3 (chuyển trả góp) | [11](11-can-bang-chi-phi-va-loi-ich.md) |
| 11 | CSKH và AI thay nhân lực | Tiết kiệm CSKH dễ chứng minh nhưng nhỏ (khoảng 10% phí nền), dùng làm bằng chứng sớm. **Không** tính cắt nhân sự vào ROI. Chuyển nhân viên sang vai trò "hỗ trợ trước hạn" | [06 mục 4.3c, 4.3d](06-mo-hinh-kinh-doanh.md#43-roi) |
| 12 | Tiến độ technical | Phase 1–4 đóng; phase 5 chưa đóng chính thức (OCR, đi 6 cảnh); phase 6 đang làm, hạn nộp 03/12 (bản đang chạy 26/11 tối: Runtime v33, gồm bộ hũ mặc định, đợt "agent thích ứng", router Claude Haiku 4.5 và 5 lỗi sửa sau lượt kiểm v32 của #39). 7 việc lệch nghiệp vụ T-01 đến T-07: T-01, T-04 đã sửa; T-03, T-05 đã xếp lịch | [13](13-tien-do-technical.md) |
| 13 | Lấp số liệu không cần khảo sát | Mượn số **hành vi, rủi ro, quản lý** trả sau từ cơ quan quản lý Indonesia (OJK 2026), Malaysia (BNM 2H 2025); **không mượn cơ cấu chi tiêu**; tỷ lệ hũ tự hiệu chỉnh (BR-78) | [01 mục 7a](01-boi-canh-thi-truong.md#7a-số-liệu-tham-chiếu-từ-các-nước-lân-cận-bổ-sung-2511) |
| 14 | Tiêu chí độ mới của nguồn | Số thị trường, giá: trong 12 tháng. Bằng chứng nhân quả (thử nghiệm ngẫu nhiên): thiết kế tốt nhất, sát sản phẩm nhất, mới nhất có thể | [08 mục 3.4](08-kpi-kinh-doanh.md#34-k4-và-k4-r-giảm-phí-trễ-hạn-ít-nhất-10-tổng-phí-không-tăng) |

**Tiến độ bên technical:** [13-tien-do-technical.md](13-tien-do-technical.md). Lịch của technical ([phase 6](../plan/phases/phase-6-danh-gia-dong-goi.md) mục 8, đổi 25/11 theo hạn nộp thật 03/12): đợt 1 và đợt 2 đã deploy khuya 25/11, bộ hũ mới deploy 26/11; **hạn tính năng mới 30/11**, freeze tối 01/12, RC và eval cuối 02/12, nộp (gồm slide) trước 18:00 ngày **03/12**.

## 2. Việc cần chốt, xếp theo thời điểm

Ký hiệu cột **Ai chốt**: Nhóm (BA, sản phẩm), Kỹ thuật, Chủ dự án, Đối tác (cần số liệu từ bên ngoài).

### 2.0 Đã chốt hoặc đã được xử lý (không cần bàn lại)

| ID | Nội dung | Kết quả | Ngày |
|---|---|---|---|
| — | VNPAY có phải đối thủ không | Không xét VNPAY | 24/11 |
| — | Có làm khảo sát người dùng không | Không. Dùng số khu vực, khảo sát lớn của bên thứ ba, đánh giá công khai trên kho ứng dụng; tỷ lệ hũ tự hiệu chỉnh (BR-78) | 25/11 |
| — | Tiêu chí độ mới của nguồn | Như dòng 14 mục 1 | 25/11 |
| C-06 | Thành phần Điểm chống chịu | Technical đã làm ở phase 4 (Tiết kiệm, Chi tiêu, Vay nợ, Kế hoạch). BA chỉ duyệt lại | 24/11 |
| F-01 | Thêm KPI hũ đệm | Đã thêm là K10; duyệt chung trong E-01 | 24/11 |
| T-01 | Gợi ý tiêu hũ Dự phòng cho khoản không thiết yếu | Technical đã thêm luật suitability thứ bảy | 24/11 |
| T-04 | Agent nhắc lời dặn không có | Technical đã sửa gốc bộ nhớ | 24/11 |
| T-03, T-05 | Tỷ lệ phải hỏi; OCR ảnh thật | Technical đã xếp lịch ở phase 6 (E7, A4) | 25/11 |
| C-12 | Đổi bộ hũ của tài khoản demo | Đã đổi: Chi hằng ngày, Nghĩa vụ (gộp Hóa đơn), Dự phòng cộng hũ tự thêm; `minh` 8 hũ, tổng 8.030.000 ₫ | 26/11 |
| C-07 | Ví không có hũ nghĩa vụ thì mốc trả sau ở đâu | Hũ trả theo một quy tắc chung; ví không có hũ `obligation` thì phải chọn hũ trả | 26/11 |
| C-11, C-13 | Tỷ lệ 3 bộ hũ theo giai đoạn sống; mục tiêu hũ đệm | C-11 hoãn cùng BR-70 (sau hạn nộp). C-13 một phần (26/11 tối): 3 tháng chi thiết yếu (theo mức nền bền) là đích tự tính của hũ đệm bên trong bộ tối ưu, chưa hiện cho người dùng | 26/11 |
| — | BR-63: bắt buộc mục đích cho hũ để dành, chặn hũ đệm thứ hai | Chưa bắt buộc trước hạn nộp: hũ để dành cũ có thể chưa có mục đích (tương thích ví cũ); có nhiều hũ đệm thì hệ thống lấy hũ đệm đầu tiên theo thứ tự. Siết sau hạn nộp | 26/11 |
| — | Hũ "Khác" cho khoản nhỏ một lần (issue #28) | Không làm: đo offline giảm tỷ lệ hỏi tối đa khoảng 1,2 điểm, dưới ngưỡng 3 điểm | 26/11 |
| — | Phân tích theo nhóm loại chi bên trong hũ gộp | Không làm trước hạn nộp; cách dùng: tách hũ riêng. Hướng sau hạn nộp: gợi ý tách hũ khi hũ gộp có dấu hiệu tăng (issue #42 đóng, không làm) | 26/11 |
| — | Sàn cho hũ chi không thiết yếu (BR-54) | Có: sàn chi = 0,5 × mức chi điển hình của chính hũ; từ 26/11 tối mức điển hình là mức nền bền (trung vị chi theo tuần, 12 tuần), đợt chi tăng là dữ kiện cho agent nói, không thành sàn cứng | 26/11 |
| — | Khoản đến hạn đúng ngày lương (BR-22) | Tính là đến hạn trước lương, trả bằng số dư trước khi lương về (phương án B); ví demo dùng ngày 5 như mọi ví | 26/11 |
| — | Hũ của khoản chi khi người dùng hỏi agent mà không nêu hũ | Agent tự suy theo ý định từ danh sách hũ thật của ví (kể cả hũ tự đặt tên), không chắc thì hỏi; hiện "Tính theo hũ X" để đổi (cuối B2a của [02](02-business-rules.md)) | 26/11 |
| — | Giao diện có chia nhóm "hũ mặc định" và "hũ bạn thêm" không | Không: hũ mặc định chỉ là bộ khởi tạo, sau đó là hũ thường | 26/11 |
| BC-12 | Hạn nộp | **03/12** (chủ dự án, theo trang cuộc thi) | 25/11 |
| — | Có thêm tính năng mới không | Được, tới hết 30/11; chưa xanh thì cắt | 25/11 |
| C-14 | Persona và tài khoản giám khảo | `minh` 120 ngày; `giamkhao1–3` dùng `minh`, không thuộc `ops` | 25/11 |
| **I-01** | Mô hình kinh doanh | **M2 (pilot) → M7 (năm đầu) → M4 (bán bản quyền cho MoMo)**; slide mở bằng đích đến M4 ([06 mục 3c](06-mo-hinh-kinh-doanh.md#3c-bảy-mô-hình-kinh-doanh-để-chọn-2511)) | 26/11 |

### 2.1 Gấp: technical đang chờ (chốt trước hạn tính năng 30/11)

| ID | Câu hỏi | Đề xuất | Ai chốt | Gỡ việc gì |
|---|---|---|---|---|
| **C-02** → [#30](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/30) | Định nghĩa mức "sát" (vàng) khi kiểm tra trước khi chi | Theo BR-36: vàng khi ngày cạn mới rơi trước kỳ lương nhưng sau ngày cạn cũ. Technical đặt ngưỡng tương ứng | Nhóm | T-02; AC-FR6-01 |
| **C-03** | Ngưỡng nghĩa vụ trên thu nhập (code đang dùng một ngưỡng 36%) | Đơn giản nhất: **giữ 36% làm mức đỏ** (có căn cứ quy tắc 28/36, nằm giữa đề xuất 30–40%), không tách hai mức trước demo | Nhóm | T-06 |
| **C-05** | Ngưỡng "khoản đủ lớn mới hỏi" khi phân hũ | Từ 2% lương tháng; ~~khoản nhỏ một lần vào hũ "Khác"~~ (hũ "Khác" không làm, 26/11) | Nhóm | T-03 (E7) |
| **C-04** (T-09, [#52](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/52)) | **Phí trả chậm trong sản phẩm mô phỏng** | **Chốt 27/11, đã mở issue [#52](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/52). Thêm trước 30/11, mức A**: thêm một dòng phí trả chậm vào bảng biểu phí; engine kiểm tra trước khi chi và what-if **đã có sẵn đoạn đọc dòng này** và hiện "nếu trễ hạn phải trả thêm X ₫". Cần thêm vài dòng mã để nhận phí theo **tỷ lệ** như MoMo (5,25–21% dư nợ quá hạn). Mức B (sổ cái tự trừ phí khi quá hạn) để sau hạn nộp. Lý do: K4, mô hình M2 (thu theo phần trễ hạn giảm được) và G1 đều nói về phí trễ, nên demo cần cho thấy con số này | Nhóm, Kỹ thuật | Demo, slide kinh doanh |
| **FR14** | Cảnh báo khoản chuyển lệch thói quen: làm bản nhỏ trước 30/11 hay để lộ trình | Chưa có quyết định bỏ hẳn; chỉ nằm trong thứ tự cắt. Bản nhỏ: khi chuyển tiền cho người nhận, so số tiền với thói quen (bộ phát hiện bất thường đã có trong mã) và hiện cảnh báo trong bản xem trước nếu lệch nhiều hoặc làm hụt hũ Dự phòng. **Đề xuất: ưu tiên C-04 trước; làm FR14 nếu chủ dự án thấy còn sức** | Chủ dự án | Không bắt buộc cho chủ đề "Trợ lý tài chính" |
| **G-01, C-12, T-07** | Phạm vi demo cho các quy tắc mới | Chỉ thêm **G1** (chi phí quy năm trên thẻ kiểm tra trước khi chi, BR-75); phải xanh trước **30/11** (hạn tính năng mới). Không đổi bộ hũ demo (C-12): **đổi 26/11**, chủ dự án chốt bộ hũ mặc định theo mục đích và bộ hũ demo có hũ tự thêm, đã deploy (issue #39, xem cuối B2a của [02](02-business-rules.md)). Còn lại ghi là lộ trình | Nhóm, Kỹ thuật | T-07 |
| C-01 | "Còn N ngày tới lương" tính từ hôm nay hay từ ngày cạn | Tách hai câu: ngày cạn, rồi số ngày trống tới lương | Nhóm | Câu chữ cảnh 1 |
| C-08 | Vị trí và câu chữ nhãn "do AI tạo" | Dòng nhỏ dưới mỗi câu trả lời và trong màn Giới thiệu. Hỏi technical đã có chưa | Nhóm | AC-DEMO-03 |
| C-14 | Persona chính | Mới đi làm (22–26), khớp persona Minh | Nhóm | Kịch bản demo |
| E-02 | Định nghĩa "cảnh báo đúng" cho K5 | ±3 ngày quanh ngày dự báo. Technical sẽ chạy backtest tay cho K5 (Q11) | Nhóm | Số K5 trên slide |
| NFR-31 | Bật CloudWatch Transaction Search (có phí) | Không bật; màn trace đọc từ `audit_events` đã đủ cho demo | Chủ dự án | Còn treo trong HANDOFF |
| NFR-34 | Mức ngân sách AWS mỗi tháng | Chốt một con số để đặt cảnh báo | Chủ dự án | — |
| NFR | Nới NFR-01 (lượt đầu phiên lạnh lên 3 giây); duyệt NFR-18, 23, 24, 28, 30, 37, 41, 43, 44 | Duyệt theo đề xuất trong file 04 | Kỹ thuật | — |

### 2.2 Trước 1/12 (số kinh doanh [#33](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/33), nháp slide [#37](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/37))

| ID | Câu hỏi | Đề xuất | Ai chốt | File |
|---|---|---|---|---|
| **I-02** | **Duyệt các quy tắc đánh dấu đề xuất**: BC-13, BR-63 đến 78, NFR-44, K10, K11, L19, L20 | Duyệt theo khối: cơ cấu hũ (BR-63 đến 73, 78), chi phí trả sau (74 đến 76), hỗ trợ trước hạn (77). **26/11:** BR-67, 69 chốt và đã làm; BR-63 (chốt chưa bắt buộc trước hạn nộp), 64, 65, 66, 73, 78 một phần; BR-68, 70, 71 hoãn; còn duyệt BR-72, 74 đến 77. BR-79 đến 84 chỉ có ở Notion, chưa vào repo | Nhóm | [02](02-business-rules.md) |
| E-01 | Duyệt mục tiêu K1–K11 | K4 10% nay có căn cứ AFM (đo được 21–24%); chú ý K3 (15%), K10 (25%), K11 (20%) | Nhóm | [08](08-kpi-kinh-doanh.md) |
| E-03 | KPI nào lên slide | K2; **K5 với hai định nghĩa cạnh baseline**; K4 kèm thử nghiệm AFM; K9 dạng hòa vốn; phân hũ báo cả hai mặt | Nhóm | [08](08-kpi-kinh-doanh.md) |
| **J-01** | Số phân loại trên slide; có đo ví 3 hũ có model trước 1/12 không | **Gắn 92%, 17,4% với ví demo nhiều hũ**; không dùng cho tài khoản mới 3 hũ. Đề xuất nhờ chủ dự án duyệt đo có model (khoảng 294 lời gọi model nhỏ). Chi tiết: [13 T-08](13-tien-do-technical.md) | Nhóm, chủ dự án | [13](13-tien-do-technical.md) |
| D-01 | Hướng thương mại chính | B2B2C qua ví | Nhóm | [06](06-mo-hinh-kinh-doanh.md) |
| D-02 | Chỉ số Bắc Đẩu | "Số người mỗi tuần tránh được hụt nhờ cảnh báo trước" | Nhóm | [06](06-mo-hinh-kinh-doanh.md) |
| D-03 | Tên và ranh giới ba gói | Như 06 mục 5.2; chốt giá sau khi technical đo chi phí AI mỗi lượt | Nhóm | [06](06-mo-hinh-kinh-doanh.md) |
| D-04 | Mức độ đưa mô hình kinh doanh lên slide | 1 slide: B2B2C, ba gói, công thức ROI, thiết kế pilot | Nhóm | [06](06-mo-hinh-kinh-doanh.md) |
| F-02 | Nói thẳng xung đột phí chậm trả trên slide | Nên; kèm điểm hòa vốn khoảng 2% so với nợ xấu khu vực 2,4–7,2% | Nhóm | [10](10-tac-dong-stakeholder.md), [11](11-can-bang-chi-phi-va-loi-ich.md) |
| G-02 | Nói G2 làm ví đối thủ mất thị phần | Không nhấn, nhưng không ghi "mọi bên đều thắng" | Nhóm | [11](11-can-bang-chi-phi-va-loi-ich.md) |
| H-02 | Tính cắt nhân sự CSKH vào ROI | Không | Nhóm | [06](06-mo-hinh-kinh-doanh.md) |
| C-11 | Tỷ lệ bộ hũ mẫu | Bộ "Mới đi làm" có căn cứ; hai bộ còn lại ghi "minh họa"; dựa vào BR-78. **Hoãn 26/11** cùng BR-70; nếu slide nói về tỷ lệ thì nói 42/33/25 là giả định thử nghiệm | Nhóm | [02](02-business-rules.md) |
| C-13 | Mục tiêu hũ đệm | 3 tháng chi thiết yếu (CFPB); sinh viên 1 tháng. **Một phần 26/11**: 3 tháng dùng trong bộ tối ưu; hiện cho người dùng và mức theo giai đoạn sống hoãn cùng BR-64 | Nhóm | [02](02-business-rules.md) |

### 2.3 Sau cuộc thi, khi đi pilot với đối tác

Phần lớn là **số liệu phải xin đối tác**. Trước khi có, dùng số công khai làm proxy (11 mục 5a).

| ID | Câu hỏi hoặc dữ liệu cần | Vì sao cần | Ai chốt | File |
|---|---|---|---|---|
| G-04 | Tỷ lệ mất gốc ở ca trễ hạn, chi phí thu hồi mỗi ca, tỷ lệ chọn trả góp | Chốt điểm hòa vốn, R4, K9 | Đối tác | [11](11-can-bang-chi-phi-va-loi-ich.md) |
| H-01 | Số ticket theo chủ đề 3 tháng trước pilot, chi phí mỗi ticket | Mốc cho K11 và phần CSKH trong ROI | Đối tác | [06](06-mo-hinh-kinh-doanh.md) |
| H-03 | Thêm vai trò "hỗ trợ trước hạn" cho CSKH | Biến chi phí nhân công thành giá trị giảm tổn thất (BR-77) | Nhóm, Đối tác | [06](06-mo-hinh-kinh-doanh.md) |
| G-03 | Đề xuất đối tác đổi ngày hạn theo ngày lương | Giảm trễ hạn kỹ thuật, chi phí gần như 0 | Đối tác | [11](11-can-bang-chi-phi-va-loi-ich.md) |
| F-03 | Thứ tự làm việc với stakeholder | Đội sản phẩm của ví → rủi ro → tín dụng → CSKH; chuẩn bị hồ sơ cho cơ quan quản lý | Nhóm | [10](10-tac-dong-stakeholder.md) |
| C-09 | Công bố việc model xử lý dữ liệu ngoài Việt Nam; đánh giá chuyển dữ liệu ra nước ngoài | **Chặn** trước khi dùng dữ liệu thật | Nhóm, pháp lý | [02](02-business-rules.md) |
| I-03 | Có làm sản phẩm cho cơ quan quản lý không (báo cáo ẩn danh về nợ nhỏ của người trẻ) | Cơ quan quản lý hiện chưa nhận được gì cụ thể | Nhóm | [10](10-tac-dong-stakeholder.md) |
| I-04 | Phân loại rủi ro của AI tư vấn tài chính theo Luật Trí tuệ nhân tạo | Cần ý kiến pháp lý trước khi thương mại hóa | Pháp lý | [01 mục 7](01-boi-canh-thi-truong.md#7-bối-cảnh-pháp-lý-đầu-vào-cho-ràng-buộc-nghiệp-vụ) |
| D-05 | Bảng `product_events` để đo giữ chân | Không có thì không đo được K3 | Kỹ thuật | [06](06-mo-hinh-kinh-doanh.md) |

### 2.4 Tham số chi tiết (sau cuộc thi)

| ID | Câu hỏi | File |
|---|---|---|
| C-07 | Tài khoản không có hũ nghĩa vụ thì mốc trả sau hiện ở đâu (**chốt 26/11**, xem mục 2.0) | [02](02-business-rules.md) |
| C-10 | Ngưỡng giá trị để gửi nhắc chủ động | [02](02-business-rules.md) |
| BR-77 | Ngưỡng hụt để đề nghị hỗ trợ trước hạn | [02](02-business-rules.md) |
| BR-78 | Ngưỡng lệch để gợi ý chỉnh tỷ lệ hũ | [02](02-business-rules.md) |

### 2.5 Kiểm thực tế trong app (không chốt bằng tài liệu được)

Từ [09 mục 6](09-phan-tich-doi-thu.md#6-việc-nên-làm-tiếp):
1. Mở app MoMo, ZaloPay, Shopee, Viettel Money; chụp màn hình các mục ở bảng 09 mục 3.
2. Kiểm: chatbot MoMo có bước xác nhận trước khi thanh toán hóa đơn không; hạn mức thật cấp cho tài khoản mới; các mục còn dấu "?".
3. Đối chiếu biểu phí trên trang của bên cấp tín dụng (TPBank, MBV, CIMB, FE Credit).

## 3. Kế hoạch BA theo lịch team (25/11 → 3/12)

| Ngày | Mốc của team | Việc của BA | Issue |
|---|---|---|---|
| T4 25/11 | Kiểm toán xong, tạo issue | Đồng bộ tài liệu BA với hạn 3/12 và kiểm toán (đã làm) | — |
| T5 26/11 | Đóng phase 5 | **Chốt C-02, C-03, C-05 và phạm vi demo (G1)**; báo technical | [#30](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/30) |
| T6 27/11 | Review, merge | Bắt đầu [#33](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/33): khung trang "Yofina trong MoMo", câu kể "AI là phần cốt lõi". **Lấy chi phí AI theo ý định từ bản đang chạy** (đợt 1, 2 đã deploy đêm 25/11) | [#33](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/33) |
| T7 28/11 | Đo, sửa lỗi | Tính chi phí AI mỗi người dùng hoạt động mỗi tháng bằng số đo; tính lại M7 | [#33](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/33) |
| CN 29/11 | Đo sau đợt 1 | Thay số lượt giả định trong bản sơ bộ (06 mục 3b) bằng số đo; chốt giá M7 (500 ₫, 1.000 ₫, bán buôn gói) | [#33](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/33) |
| T2 30/11 | **Deploy đợt 2, hạn tính năng mới** | Duyệt I-02 (quy tắc đề xuất), E-01, E-03; nháp nội dung slide | [#37](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/37) |
| T3 1/12 | **Đóng băng code** | Gửi #33 cho chủ dự án duyệt; nháp slide 10 trang; đối chiếu ADR-0004 | [#33](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/33), [#37](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/37), [#32](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/32) |
| T4 2/12 | RC, eval cuối | Điền số đo cuối (K2, K5, eval có khoảng tin cậy) vào slide; danh sách nguồn dữ liệu cho README | [#37](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/37), [#36](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/36) |
| T5 3/12 | **Nộp trước 18:00** | Rà số trên slide trỏ về repo; khóa | [#37](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/37) |

Sau 3/12 không sửa được slide. Các việc ở 2.3, 2.4 để sau cuộc thi.

## 4. Số liệu cần lấp và nơi tìm (bổ sung 24/11)

**Đã tra và điền (24/11):**
- Bộ hũ "Mới đi làm": thu nhập, nhà ở, ăn uống, hũ đệm, theo Cục Thống kê, giá phòng trọ, CFPB ([02 mục B2a](02-business-rules.md)).
- C-03 (MAS), C-13 (CFPB).
- K3: Adjust Nhật Bản, AppsFlyer Đông Nam Á.
- Biên lãi thuần ngân hàng năm 2026 (11 mục 2.1).
- Proxy cho số của đối tác: nợ xấu 7,2% và chi phí tín dụng 11,5% (FiinGroup), lương CSKH (11 mục 5a, 06 mục 4.3c).
- **25/11:** nợ xấu trả sau Indonesia (OJK 2026), nợ trả sau quá hạn Malaysia (BNM 2H 2025), thử nghiệm AFM cho K4 (01 mục 7a, 08 mục 3.4).

**Còn trống (chấp nhận, không khảo sát):** tỷ lệ của 2 bộ hũ "Sinh viên" và "Ổn định"; 5 hũ nhỏ trong bộ "Mới đi làm" (ghi "minh họa", tự hiệu chỉnh theo BR-78); D30 tuyệt đối của app tài chính Việt Nam (báo cáo AppsFlyer bản đầy đủ phải đăng ký mới tải được).

**Cách lấp khi không khảo sát (25/11):** số hành vi và rủi ro trả sau mượn từ cơ quan quản lý Indonesia, Malaysia ([01 mục 7a](01-boi-canh-thi-truong.md#7a-số-liệu-tham-chiếu-từ-các-nước-lân-cận-bổ-sung-2511)); cơ cấu chi tiêu không mượn, thay bằng thiết kế tự hiệu chỉnh (BR-78) và ghi "minh họa" cho hai bộ còn lại; góc nhìn người dùng lấy từ đánh giá công khai trên kho ứng dụng.


Ba loại: **Tra cứu** (nhóm tự tìm từ nguồn công khai), **Đo nội bộ** (lấy từ hệ thống của mình), **Xin đối tác** (không có trên nguồn công khai).

### 4.1 Tra cứu từ nguồn công khai

| Số liệu | Đang dùng | Nằm ở | Nên tìm ở đâu |
|---|---|---|---|
| Tỷ lệ 3 bộ hũ mẫu (C-11) | **Đã điền** bộ "Mới đi làm"; 2 bộ còn lại minh họa | BR-70 | Khảo sát mức sống dân cư (VHLSS) và báo cáo lao động việc làm hằng quý của Cục Thống kê (thu nhập bình quân theo nhóm tuổi, cơ cấu chi tiêu); khảo sát người trẻ của Decision Lab, Q&Me; UOB ACSS 2026; giá phòng trọ trong báo cáo thị trường cho thuê của Batdongsan.com.vn; lương mới ra trường trong báo cáo lương của TopCV, VietnamWorks/Navigos. Không khảo sát (25/11): ghi "minh họa", tự hiệu chỉnh theo BR-78 |
| Mục tiêu hũ đệm mấy tháng (C-13) | **Đã điền**: 3 tháng (CFPB) | BR-64 | Hướng dẫn quỹ khẩn cấp của CFPB (Mỹ) và MoneySense (Singapore); UOB ACSS 2026 (47% Gen Z có tiết kiệm đủ hơn 3 tháng) |
| Ngưỡng nghĩa vụ trên thu nhập cho thẻ đỏ (C-03) | **Đã điền**: giữ 36% của code (MAS 55% làm mốc trên) | BR-37 | Tỷ lệ tổng nghĩa vụ trả nợ trên thu nhập (TDSR) 55% của MAS (Singapore); ngưỡng 43% trong quy định khoản vay đủ chuẩn cũ của CFPB; hướng dẫn cho vay có trách nhiệm của Ngân hàng Thái Lan; các thông tư về cho vay tiêu dùng của NHNN trên vbpl.vn hoặc thuvienphapluat.vn |
| Hạn mức thật cho tài khoản mới, bước xác nhận của chatbot MoMo | Chưa có | 09 mục 6 | Mở app, chụp màn hình |
| Giữ chân D30 của app tài chính ở Việt Nam hoặc Đông Nam Á | **Đã bổ sung** Adjust Nhật Bản 8%, AppsFlyer Đông Nam Á; còn thiếu số tuyệt đối của Việt Nam | K3 | Báo cáo theo khu vực của AppsFlyer, Adjust; báo cáo e-Conomy SEA (Google, Temasek, Bain) |
| Biên lãi thuần của đúng ngân hàng đối tác | **Đã điền**: 2,8–3,5% (2026) | 11 mục 2.1 | Báo cáo tài chính quý của TPBank, MB, Vietcombank trên trang quan hệ nhà đầu tư, hoặc trên Vietstock, CafeF |
| Nợ xấu, chi phí rủi ro của mảng tài chính tiêu dùng | **Đã điền**: nợ xấu ngành 7,2%, chi phí tín dụng 11,5% | 11 mục 5a | Báo cáo tài chính kiểm toán của FE Credit, Home Credit, HD Saison (công bố trên HNX); thống kê nợ xấu của NHNN; báo cáo trả sau của FiinGroup |
| Lương CSKH để ước chi phí mỗi ticket | **Đã điền** lương 8–12 triệu ₫ (CareerLink); số ticket mỗi người vẫn giả định | 06 mục 4.3c | Báo cáo lương của TopCV, VietnamWorks (vị trí chăm sóc khách hàng, tổng đài viên); chỉ là số tạm, số thật phải xin đối tác |

### 4.2 Đo nội bộ (không cần đi tìm, phải đo)

| Số liệu | Nằm ở | Đo bằng |
|---|---|---|
| Chi phí AI mỗi lượt, mỗi người dùng (E-04) | K6, K7, giá gói | Token ghi trong `yofina_core.llm` nhân với giá trên trang giá Bedrock (phase 6) |
| Ngưỡng tự gán 0,9 và 0,6 khi phân loại | BR-17 | Bộ test phân loại có nhãn (phase 4) |
| Ngưỡng lệch lương | BR-12 | Đối chiếu tham số trong SSM |
| Số ngày cảnh báo trước, tỷ lệ cảnh báo đúng | K5, NFR-12 | Backtest 3 persona |
| Thời gian batch đêm với bộ hũ mới | NFR-06 | Chạy lại sau khi đổi bộ hũ |

### 4.3 Xin đối tác (chỉ có trong pilot)

| Số liệu | Nằm ở | Ghi chú |
|---|---|---|
| Tỷ lệ mất gốc ở ca trễ hạn, chi phí thu hồi mỗi ca, tỷ lệ chọn trả góp (G-04) | 11 mục 5, R4, K9 | Có thể dùng tỷ lệ nợ xấu công khai của công ty tài chính tiêu dùng làm số tạm |
| Số ticket theo chủ đề và chi phí mỗi ticket (H-01) | K11, 06 mục 4.3c | Gartner chỉ dùng để tham khảo chênh lệch giữa hai kênh |
| Dư nợ trung bình, tỷ lệ trễ hạn hiện tại | 06 mục 4.3a, K9 | — |
| Doanh thu trung bình mỗi người dùng (ARPU) của ví, mức phí ví sẵn sàng trả (R1 1.500 ₫/người dùng hoạt động) | 06 mục 3a | MoMo không công bố ARPU; chốt qua trao đổi giá |
