# 12. Tổng hợp thảo luận và danh sách việc cần chốt

> Cập nhật 24/11/2026. File này gom các kết luận của bộ tài liệu BA (01–11) và **mọi câu hỏi đang mở** vào một chỗ, xếp theo thời điểm cần chốt. Mỗi dòng trỏ về file gốc; khi chốt, sửa ở file gốc rồi đánh dấu ở đây.

## 1. Đã thảo luận và kết luận gì

| # | Chủ đề | Kết luận chính | File |
|---|---|---|---|
| 1 | Bối cảnh thị trường, pain point | 7 pain point (P1–P7) của người 18–30. Nặng nhất: không biết trước lúc thiếu tiền, phí trả sau không thấy trước, nhiều tài khoản trả sau, quỹ đệm mỏng. Khoảng trống thị trường: các ví mạnh ở "nhìn lại", chưa ai làm "nhìn trước" | [01](01-boi-canh-thi-truong.md) |
| 2 | Phạm vi người dùng | Giữ **18–30 theo giai đoạn sống**, không đổi sang Gen Z, vì trả sau yêu cầu từ 18 tuổi và Gen Z năm 2026 có cả người 14–17 (BC-13) | [01](01-boi-canh-thi-truong.md), [02](02-business-rules.md) |
| 3 | Quy tắc nghiệp vụ, yêu cầu | BC-01 đến 13, BR-01 đến 77, FR1–FR15, NFR-01 đến 44, AC theo Cho trước / Khi / Thì | [02](02-business-rules.md)–[05](05-acceptance-criteria.md) |
| 4 | Cơ cấu hũ mới | Hũ tích lũy chia 4 mục đích: đệm, quỹ dồn, mục tiêu, dài hạn. Hũ Hóa đơn chuyển sang nghĩa vụ. 3 bộ hũ mẫu theo giai đoạn sống. Đã nối vào BR, FR, NFR, AC, luồng L19–L20, KPI K10, bảng gói | [02 mục B2a](02-business-rules.md), [07](07-dac-ta-luong-hoat-dong.md) |
| 5 | Đối thủ | Chỉ dùng nguồn chính thức. Cùng món hàng 1,2 triệu, tổng phải trả dao động 0–13,5% tùy ví và số ngày trễ. VNPAY không xét là đối thủ (24/11) | [09](09-phan-tich-doi-thu.md) |
| 6 | Mô hình kinh doanh | **B2B2C qua ví**. 3 gói theo mức dùng AI; phần an toàn có ở mọi gói. 7 nguồn thu R1–R7. Không thu hoa hồng khoản vay, không bán dữ liệu, không quảng cáo trong tư vấn | [06](06-mo-hinh-kinh-doanh.md) |
| 7 | Luồng hoạt động, human-in-the-loop | 20 luồng. Agent chỉ đọc và đề nghị; mọi thao tác ghi đi qua xem trước và token xác nhận dùng một lần. Đây là human-in-the-loop ở mức con người duyệt từng hành động | [07](07-dac-ta-luong-hoat-dong.md) |
| 8 | KPI | K1–K11 theo 3 mốc (cuộc thi, pilot, năm đầu), mỗi KPI có benchmark và lý do vì sao đạt được | [08](08-kpi-kinh-doanh.md) |
| 9 | Stakeholder | 6 nhóm. Chỉ xác nhận bằng token và bảng "Vì sao" có lợi cho mọi bên. 5 xung đột lợi ích, lớn nhất là phí chậm trả của bên cho vay | [10](10-tac-dong-stakeholder.md) |
| 10 | Chi phí người trẻ và lợi ích đối tác | Phí cố định 33.000 ₫/tháng tương đương khoảng 40–79%/năm trên dư nợ nhỏ. 6 đòn bẩy G1–G6. Bên cho vay có lời ròng nếu từ khoảng 1,9% ca trễ bị mất gốc, hoặc ngay lập tức nếu có G3 (chuyển trả góp) | [11](11-can-bang-chi-phi-va-loi-ich.md) |
| 11 | CSKH và AI thay nhân lực | Tiết kiệm CSKH dễ chứng minh nhưng nhỏ (khoảng 10% phí nền), dùng làm bằng chứng sớm. **Không** tính cắt nhân sự vào ROI. Chuyển nhân viên sang vai trò "hỗ trợ trước hạn" | [06 mục 4.3c, 4.3d](06-mo-hinh-kinh-doanh.md#43-roi) |

**Tiến độ bên technical** (đã đối chiếu 24/11 tối): [13-tien-do-technical.md](13-tien-do-technical.md). Mục 4 của file đó có 7 việc BA cần báo lại (T-01 đến T-07). Hai việc chốt sẽ gỡ được lỗi đang chạy: **C-02** (gỡ T-02) và **C-05** (gỡ T-03).

## 2. Việc cần chốt, xếp theo thời điểm

Ký hiệu cột **Ai chốt**: Nhóm (BA, sản phẩm), Kỹ thuật, Đối tác (cần số liệu từ bên ngoài).

### 2.1 Trước khi đóng phase 3 và quay demo (hạn nộp 11/12/2026, BC-12)

Những việc này ảnh hưởng trực tiếp tới số và câu chữ hiện trên demo.

| ID | Câu hỏi | Đề xuất | Ai chốt | File |
|---|---|---|---|---|
| C-01 | "Còn N ngày tới lương" tính từ hôm nay hay từ ngày cạn | Tách hai câu: ngày cạn, rồi số ngày trống tới lương | Nhóm | [02](02-business-rules.md) |
| C-02 | Ngưỡng "sát" (vàng) khi kiểm tra trước khi chi | Vàng khi ngày cạn mới rơi trước kỳ lương nhưng sau ngày cạn cũ | Nhóm | [02](02-business-rules.md) |
| C-03 | Tỷ lệ nghĩa vụ trên thu nhập để hiện thẻ đỏ | Cấu hình được, mặc định 30–40%; cần nguồn | Nhóm | [02](02-business-rules.md) |
| C-04 | Thêm phí trả chậm vào biểu phí mô phỏng | Đã có nguồn MoMo 5,25–21%; nên thêm | Nhóm, Kỹ thuật | [02](02-business-rules.md) |
| C-08 | Vị trí và câu chữ nhãn "do AI tạo" | Dòng nhỏ dưới mỗi câu trả lời và trong màn Giới thiệu | Nhóm | [02](02-business-rules.md) |
| C-12 | Đổi bộ hũ demo sang cơ cấu mới ngay không | **Chưa**, để sau phase 3 cho khỏi phá cảnh 1 | Nhóm, Kỹ thuật | [02](02-business-rules.md) |
| C-14 | Persona chính | Mới đi làm (22–26), khớp persona Minh | Nhóm | [02](02-business-rules.md) |
| G-01 | Đưa G1 (chi phí quy năm) và G3 (chuyển trả góp) vào demo không | Nên; G1 gần có sẵn trong FR6 | Nhóm, Kỹ thuật | [11](11-can-bang-chi-phi-va-loi-ich.md) |
| E-02 | Định nghĩa "cảnh báo đúng" cho K5 | ±3 ngày quanh ngày dự báo | Nhóm | [08](08-kpi-kinh-doanh.md) |
| NFR-01 | Nới chỉ tiêu độ trễ lượt đầu phiên lạnh | Nới lên 3 giây | Kỹ thuật | [04](04-non-functional-requirements.md) |
| NFR | Duyệt chỉ tiêu NFR-18, 23, 24, 28, 30, 37, 41, 43, 44 | Duyệt theo đề xuất trong file | Kỹ thuật | [04](04-non-functional-requirements.md) |
| NFR-31 | Bật CloudWatch Transaction Search (có phí) | Hỏi chủ dự án vì đổi mức tài khoản | Chủ dự án | [04](04-non-functional-requirements.md) |
| NFR-34 | Mức ngân sách AWS mỗi tháng | Chốt một con số để đặt cảnh báo | Chủ dự án | [04](04-non-functional-requirements.md) |

### 2.2 Trước khi làm slide và thuyết trình

| ID | Câu hỏi | Đề xuất | Ai chốt | File |
|---|---|---|---|---|
| D-01 | Hướng thương mại chính | B2B2C qua ví | Nhóm | [06](06-mo-hinh-kinh-doanh.md) |
| D-02 | Chỉ số Bắc Đẩu | "Số người mỗi tuần tránh được hụt nhờ cảnh báo trước" | Nhóm | [06](06-mo-hinh-kinh-doanh.md) |
| D-03 | Tên và ranh giới ba gói | Như 06 mục 5.2; chốt giá sau khi đo chi phí AI | Nhóm | [06](06-mo-hinh-kinh-doanh.md) |
| D-04 | Mức độ đưa mô hình kinh doanh lên slide | 1 slide: B2B2C, ba gói, công thức ROI, thiết kế pilot | Nhóm | [06](06-mo-hinh-kinh-doanh.md) |
| E-01 | Duyệt mục tiêu K1–K11 | Chú ý K3 (15%), K4 (10%), K10 (25%), K11 (20%) | Nhóm | [08](08-kpi-kinh-doanh.md) |
| E-03 | KPI nào lên slide | K2, K5, K4 kèm RCT, K9 dạng hòa vốn | Nhóm | [08](08-kpi-kinh-doanh.md) |
| F-01 | Thêm KPI hũ đệm | Đã thêm dạng đề xuất là K10; chỉ cần duyệt | Nhóm | [10](10-tac-dong-stakeholder.md) |
| F-02 | Nói thẳng xung đột phí chậm trả trên slide | Nên | Nhóm | [10](10-tac-dong-stakeholder.md) |
| G-02 | Nói G2 làm ví đối thủ mất thị phần | Không nhấn, nhưng không ghi "mọi bên đều thắng" | Nhóm | [11](11-can-bang-chi-phi-va-loi-ich.md) |
| H-02 | Tính cắt nhân sự CSKH vào ROI | Không | Nhóm | [06](06-mo-hinh-kinh-doanh.md) |
| C-11 | Căn cứ cho tỷ lệ 3 bộ hũ mẫu | Tìm khảo sát cơ cấu chi tiêu người trẻ, hoặc ghi rõ "minh họa" trên slide | Nhóm | [02](02-business-rules.md) |
| C-13 | Mục tiêu hũ đệm mấy tháng chi thiết yếu | 3 tháng; sinh viên 1 tháng | Nhóm | [02](02-business-rules.md) |
| **I-01** | **Ai trả phí nền R1?** Phí nền chiếm khoảng 68% doanh thu và do ví trả, nhưng lợi ích đo được rõ nhất (giảm trễ hạn) thuộc bên cho vay | Chia R1 giữa ví và bên cho vay; hoặc giảm R1, tăng phần R4 do bên cho vay trả | Nhóm | Mới, [06 mục 3a](06-mo-hinh-kinh-doanh.md) |
| **I-02** | **Duyệt toàn bộ quy tắc đánh dấu "đề xuất 24/11"**: BC-13, BR-63 đến 77, NFR-44, K10, K11, L19, L20 | Duyệt theo khối: cơ cấu hũ (BR-63 đến 73), chi phí trả sau (74 đến 76), hỗ trợ trước hạn (77) | Nhóm | [02](02-business-rules.md) |

### 2.3 Trước khi đi pilot với đối tác

Phần lớn là **số liệu phải xin đối tác**; thiếu những số này thì không chốt được giá và ROI.

| ID | Câu hỏi hoặc dữ liệu cần | Vì sao cần | Ai chốt | File |
|---|---|---|---|---|
| G-04 | Tỷ lệ mất gốc ở ca trễ hạn, chi phí thu hồi mỗi ca, tỷ lệ chọn trả góp | Chốt điểm hòa vốn, R4, K9 | Đối tác | [11](11-can-bang-chi-phi-va-loi-ich.md) |
| H-01 | Số ticket theo chủ đề 3 tháng trước pilot, chi phí mỗi ticket | Mốc cho K11 và phần CSKH trong ROI | Đối tác | [06](06-mo-hinh-kinh-doanh.md) |
| H-03 | Thêm vai trò "hỗ trợ trước hạn" cho CSKH trong pilot | Biến chi phí nhân công thành giá trị giảm tổn thất (BR-77) | Nhóm, Đối tác | [06](06-mo-hinh-kinh-doanh.md) |
| G-03 | Đề xuất đối tác cho đổi ngày hạn theo ngày lương | Giảm trễ hạn kỹ thuật, chi phí gần như 0 | Đối tác | [11](11-can-bang-chi-phi-va-loi-ich.md) |
| F-03 | Thứ tự làm việc với stakeholder | Đội sản phẩm của ví → rủi ro → tín dụng → CSKH; chuẩn bị hồ sơ cho cơ quan quản lý | Nhóm | [10](10-tac-dong-stakeholder.md) |
| C-09 | Công bố việc model xử lý dữ liệu ngoài Việt Nam; đánh giá chuyển dữ liệu ra nước ngoài | **Chặn** trước khi dùng dữ liệu thật | Nhóm, pháp lý | [02](02-business-rules.md), [10](10-tac-dong-stakeholder.md) |
| **I-03** | Có làm sản phẩm cho cơ quan quản lý không (ví dụ báo cáo ẩn danh, tổng hợp về nợ nhỏ của người trẻ) | Hiện cơ quan quản lý chỉ nhận được việc tuân thủ, chưa có gì cụ thể | Nhóm | Mới, [10](10-tac-dong-stakeholder.md) |
| **I-04** | Phân loại rủi ro của AI tư vấn tài chính cá nhân theo Luật Trí tuệ nhân tạo | Cần ý kiến pháp lý trước khi thương mại hóa | Pháp lý | [01 mục 7](01-boi-canh-thi-truong.md#7-bối-cảnh-pháp-lý-đầu-vào-cho-ràng-buộc-nghiệp-vụ) |
| D-05 | Thêm bảng `product_events` để đo giữ chân | Không có thì không đo được K3 | Kỹ thuật | [06](06-mo-hinh-kinh-doanh.md) |
| E-04 | Đo chi phí AI mỗi lượt ở phase 6 | Chốt K6, K7 và giá gói | Kỹ thuật | [08](08-kpi-kinh-doanh.md) |

### 2.4 Phase 4–5 (tham số chi tiết, chưa gấp)

| ID | Câu hỏi | File |
|---|---|---|
| C-05 | Ngưỡng "đủ lớn để hỏi" khi phân loại chuyển khoản cá nhân | [02](02-business-rules.md) |
| C-06 | Bốn thành phần, trọng số của Điểm chống chịu và độ lớn ba cú sốc | [02](02-business-rules.md) |
| C-07 | Tài khoản không có hũ nghĩa vụ thì mốc trả sau hiện ở đâu | [02](02-business-rules.md) |
| C-10 | Ngưỡng giá trị để gửi nhắc chủ động | [02](02-business-rules.md) |
| BR-77 | Ngưỡng hụt để đề nghị hỗ trợ trước hạn | [02](02-business-rules.md) |

### 2.5 Kiểm thực tế trong app (không chốt bằng tài liệu được)

Từ [09 mục 6](09-phan-tich-doi-thu.md#6-việc-nên-làm-tiếp):
1. Mở app MoMo, ZaloPay, Shopee, Viettel Money (VNPAY ngoài phạm vi, quyết định 24/11); chụp màn hình các mục ở bảng 09 mục 3.
2. Kiểm: chatbot MoMo có bước xác nhận trước khi thanh toán hóa đơn không; hạn mức thật cấp cho tài khoản mới; các mục còn dấu "?".
3. Đối chiếu biểu phí trên trang của bên cấp tín dụng (TPBank, MBV, CIMB, Cake, FE Credit).

## 3. Thứ tự đề nghị

1. **Tuần này:** chốt khối 2.1. Đây là các câu trả lời kỹ thuật đang chờ, và chúng quyết định số hiện trên demo.
2. **Trước khi dựng slide:** chốt khối 2.2, nhất là **I-01** (ai trả tiền) và **I-02** (duyệt các quy tắc đề xuất), vì giám khảo sẽ hỏi đúng vào mô hình doanh thu.
3. **Song song:** làm mục 2.5. Việc này chỉ tốn vài giờ và làm bảng đối thủ chắc hơn.
4. **Sau cuộc thi:** khối 2.3 và 2.4, gắn với pilot.

## 4. Số liệu cần lấp và nơi tìm (bổ sung 24/11)

**Đã tra và điền (24/11):**
- Bộ hũ "Mới đi làm": thu nhập, nhà ở, ăn uống, hũ đệm, theo Cục Thống kê, giá phòng trọ, CFPB ([02 mục B2a](02-business-rules.md)).
- C-03 (MAS), C-13 (CFPB).
- K3: Adjust Nhật Bản, AppsFlyer Đông Nam Á.
- Biên lãi thuần ngân hàng năm 2026 (11 mục 2.1).
- Proxy cho số của đối tác: nợ xấu 7,2% và chi phí tín dụng 11,5% (FiinGroup), lương CSKH (11 mục 5a, 06 mục 4.3c).

**Còn trống:** tỷ lệ của 2 bộ hũ "Sinh viên" và "Ổn định"; 5 hũ nhỏ trong bộ "Mới đi làm" (cần khảo sát); D30 tuyệt đối của app tài chính Việt Nam (báo cáo AppsFlyer bản đầy đủ phải đăng ký mới tải được).


Ba loại: **Tra cứu** (nhóm tự tìm từ nguồn công khai), **Đo nội bộ** (lấy từ hệ thống của mình), **Xin đối tác** (không có trên nguồn công khai).

### 4.1 Tra cứu từ nguồn công khai

| Số liệu | Đang dùng | Nằm ở | Nên tìm ở đâu |
|---|---|---|---|
| Tỷ lệ 3 bộ hũ mẫu (C-11) | **Đã điền** bộ "Mới đi làm"; 2 bộ còn lại minh họa | BR-70 | Khảo sát mức sống dân cư (VHLSS) và báo cáo lao động việc làm hằng quý của Cục Thống kê (thu nhập bình quân theo nhóm tuổi, cơ cấu chi tiêu); khảo sát người trẻ của Decision Lab, Q&Me; UOB ACSS 2026; giá phòng trọ trong báo cáo thị trường cho thuê của Batdongsan.com.vn; lương mới ra trường trong báo cáo lương của TopCV, VietnamWorks/Navigos. **Cách chắc nhất:** tự khảo sát 50–100 người 18–30 bằng Google Form |
| Mục tiêu hũ đệm mấy tháng (C-13) | **Đã điền**: 3 tháng (CFPB) | BR-64 | Hướng dẫn quỹ khẩn cấp của CFPB (Mỹ) và MoneySense (Singapore); UOB ACSS 2026 (47% Gen Z có tiết kiệm đủ hơn 3 tháng) |
| Ngưỡng nghĩa vụ trên thu nhập cho thẻ đỏ (C-03) | **Đã điền**: vàng 30%, đỏ 40% (MAS làm mốc) | BR-37 | Tỷ lệ tổng nghĩa vụ trả nợ trên thu nhập (TDSR) 55% của MAS (Singapore); ngưỡng 43% trong quy định khoản vay đủ chuẩn cũ của CFPB; hướng dẫn cho vay có trách nhiệm của Ngân hàng Thái Lan; các thông tư về cho vay tiêu dùng của NHNN trên vbpl.vn hoặc thuvienphapluat.vn |
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
