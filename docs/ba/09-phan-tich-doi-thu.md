# Phân tích đối thủ từ nguồn chính thức

> Viết ngày 24/11/2026. Thay cho bảng so sánh cũ ở [01 mục 3](01-boi-canh-thi-truong.md#3-công-cụ-hiện-có-làm-được-gì-chưa-làm-gì). Bảng cũ dựng từ báo chí, blog đánh giá và một bài so sánh do MoMo tự viết.
> **Chỉ dùng nguồn chính thức của từng sản phẩm**: website của công ty, trang hỏi đáp và trợ giúp, điều khoản và biểu phí, trang App Store do chính công ty đăng. Không dùng trang so sánh của bên thứ ba hay báo chí.

## 1. Phương pháp và giới hạn

| Sản phẩm | Đã đọc | Không đọc được |
|---|---|---|
| **MoMo** | Trang Quản Lý Chi Tiêu, Trợ thủ tài chính, Phân Bổ Lương, Ví Trả Sau, Biểu phí, 2 trang hỏi đáp phí; App Store (M-SERVICE JSC, bản 5.18.0) | Các trang không ghi ngày đăng, chỉ có "©Copyright M_Service 2026". Trang Ví Trả Sau dài, phần cuối không đọc được nguyên văn |
| **ZaloPay** | Thông báo biểu phí CIMB 2026 (đăng 29/12/2025); 2 trang hướng dẫn trả sau (06–07/2025); bài tiết kiệm Tết (30/01/2026); biểu phí trung gian thanh toán; App Store (ZION JSC) | — |
| **ShopeePay** | Điều khoản SPayLater (đăng 31/10/2025); Shopee Blog về SPayLater (19/05/2026) | 3 trang trợ giúp `help.cs.shopeepay.vn` trả trang rỗng; trang App Store không tìm đúng |
| **VNPAY** (ngoài phạm vi, chỉ tham khảo) | 2 bài trên `vnpay.vn` (đăng 2021); điều khoản ví VNPAY (hiệu lực 11/05/2023) trên `vidientu-static.vnpay.vn`; biểu phí dịch vụ trên `vnpay.vn`; tin hợp tác VNPAY và Cake (12/2024) | Tên miền `vidientu.vnpay.vn` vẫn lỗi DNS (thử lại 24/11). Các trang chính thức đọc được **không có điều khoản trả sau**, vì sản phẩm trả sau trên ví VNPAY do **Cake by VPBank** cung cấp. Số phí trả sau chỉ có từ nguồn thứ cấp (VCCI) |
| **Viettel Money** | Trang Paynow, trang Ví trả sau, trang đóng tiền khoản vay, trang quản lý chi tiêu (là **bài tư vấn chung**, không mô tả tính năng); App Store (Viettel Telecom, bản 8.8.63) | Các trang không ghi ngày đăng |

**Lưu ý chung:**
- Trang chính thức là **lời của chính doanh nghiệp**. Nó cho biết họ công bố có gì, chứ không chứng minh tính năng chạy tốt.
- "Không thấy" nghĩa là **không thấy trên các trang chính thức đã đọc**. Bước kiểm cuối vẫn là mở app ([open-questions](../requirements/open-questions.md)).
- Truy cập ngày 24/11/2026. Phí và điều khoản thay đổi thường xuyên.

## 2. Hồ sơ từng sản phẩm

### 2.1 MoMo

**Định vị:** "Trợ thủ Tài chính với AI". Trên App Store, phần AI được mô tả cụ thể nhất lại là bảo mật: "Công nghệ bảo mật 5 lớp AI… phát hiện và ngăn chặn giao dịch bất thường".

**Quản lý chi tiêu** ([momo.vn/quan-ly-chi-tieu](https://www.momo.vn/quan-ly-chi-tieu)): **mạnh nhất trong nhóm**.
- **Tự phân loại:** "hệ thống sẽ tự động phân loại các khoản chi tiêu". Dựa trên lần phân loại trước của người dùng, nội dung chuyển khoản và dữ liệu AI.
- **Danh mục và báo cáo:** người dùng tự tạo danh mục được; có "Báo cáo tuần/tháng trực quan, dễ hiểu".
- **Ngân sách và cảnh báo:** đặt ngân sách tháng hoặc theo danh mục; "MoMo sẽ tự động cảnh báo khi bạn sắp vượt hoặc đã vượt ngân sách đặt ra".
- **Chatbot:** "Truy vấn các thông tin chi tiêu trên MoMo qua chat, ghi chép & thanh toán hóa đơn qua chat"; giúp đặt mục tiêu tài chính.
- **Giao dịch ngoài ví:** quản lý được "mọi giao dịch, cả trong và ngoài MoMo", qua mục "Thêm giao dịch ngoài".

**Phân Bổ Lương** ([momo.vn/tai-chinh/phan-bo-luong](https://www.momo.vn/tai-chinh/phan-bo-luong)): là **máy tính gợi ý**, không phải hũ thật.
- Trang ghi: "gợi ý ngay cách chia tiền"; "Các cách phân bổ gợi ý mang tính tham khảo"; số nhập vào thì "MoMo không lưu lại". Sau đó người dùng tự "Thực hiện phân bổ chi tiêu theo kết quả được gợi ý".
- Phần "Dự phóng" trên trang là dự phóng **tăng trưởng đầu tư** ("Dự phóng không cam kết lợi nhuận"), không phải dự báo dòng tiền.
- Có lời miễn trừ: "chỉ là gợi ý tham khảo, không mang tính tư vấn đầu tư".

**Ví Trả Sau** ([biểu phí](https://www.momo.vn/vi-tra-sau/bieu-phi), [phí chậm trả](https://www.momo.vn/hoi-dap/phi-cham-tra-vi-tra-sau), [hỏi đáp phí](https://www.momo.vn/hoi-dap/neu-dung-vi-tra-sau-thi-toi-se-bi-tinh-phi-nhu-the-nao), [trang sản phẩm](https://www.momo.vn/vi-tra-sau)):

| Mục | Nội dung chính thức |
|---|---|
| Hạn mức | "lên đến 20 triệu đồng" |
| Bên cấp tín dụng | TPBank, MBV, VCBNeo ("được phát triển và cung cấp bởi…") |
| Phí dịch vụ | "33.000đ/tháng (chỉ tính khi trong tháng có phát sinh giao dịch)"; miễn phí "5 giao dịch đầu tiên", chỉ áp dụng một lần khi mở ví |
| Phí chậm trả (từ 01/04/2026) | Trễ 1–4 ngày: 5,25%; 5–9 ngày: 10,5%; 10–14 ngày: 15,75%; từ 14–15 ngày: 21% "số tiền chậm trả". Ví dụ của MoMo: "900,000đ x 10.5% = 94,500đ" |
| Trả một phần | Phí 6,3% trên dư nợ chuyển kỳ |
| Chuyển trả góp | 3% × số tiền × số kỳ; đã chuyển thì không hủy được |
| Hạn trả | Ngày 5 (các ví dụ của MoMo đều đến hạn ngày 05) |
| Nhắc hạn | "nhắc Khách hàng thanh toán từ 5 ngày trước khi các hóa đơn đến hạn" |
| Trước khi mua | Có **công cụ mô phỏng trả góp** ("Tổng tiền trả góp", "Phí tương đương"); không thấy công cụ kiểm tra khoản mua có làm hụt ngân sách hay không |

### 2.2 ZaloPay

**Quản lý chi tiêu:** ở mức cơ bản.
- "lịch sử giao dịch rõ ràng theo thời gian và danh mục", "báo cáo chi tiết theo ngày/tuần" ([bài Tết 30/01/2026](https://zalopay.vn/tiet-kiem-tien-tieu-tet-8194)).
- Người dùng "tự đặt cột mốc" cho nhóm chi, và bật thông báo giao dịch.
- Không thấy tự phân loại, chatbot AI hay hũ có số dư riêng. Gợi ý "quy tắc phong bì" chỉ là mẹo cho người dùng, không phải tính năng.

**Tài khoản trả sau** ([biểu phí CIMB 2026](https://zalopay.vn/cap-nhat-bieu-phi-lai-cho-tai-khoan-tra-sau-tra-gop-cua-cimb-tren-zalopay-nam-2026-8107), [hướng dẫn](https://zalopay.vn/huy-tai-khoan-tra-sau-7073), [thanh toán tối thiểu](https://zalopay.vn/thanh-toan-toi-thieu-tai-khoan-tra-sau-6968)):

| Mục | Nội dung chính thức |
|---|---|
| Bên cấp tín dụng | CIMB Việt Nam (biểu phí 2026); trang cũ hơn ghi thêm LOTTE Finance |
| Hạn mức | "lên đến 30.000.000 đồng" (biểu phí 2026); trang 2025 ghi "lên đến 8.000.000 đồng" |
| Phí dịch vụ (từ kỳ sao kê 28/01/2026) | "20.000đ/kỳ sao kê", chỉ khi "có giao dịch thanh toán phát sinh trong kỳ sao kê" |
| Miễn lãi | "tối đa 37 ngày" |
| Quá hạn | **Phí sử dụng theo bậc dư nợ chưa trả**: dưới 500.000 ₫ thì 30.000 ₫; dưới 1,5 triệu thì 60.000 ₫; dưới 2,5 triệu thì 99.000 ₫; từ 2,5 triệu thì 129.000 ₫. Cộng lãi "khoảng 0,17%/ngày" |
| Trả góp | Lãi 3%/tháng trên dư nợ giảm dần |
| Hậu quả trễ | Ghi nhận ở CIC; có thể "Giảm hạn mức tín dụng", "Khóa tính năng thanh toán" |
| Theo dõi | "Xem số dư và thông báo dư nợ theo thời gian thực"; "kiểm tra chi tiết dư nợ, phí và lãi phát sinh trực tiếp trong ứng dụng" |

### 2.3 ShopeePay (SPayLater)

**Quản lý chi tiêu:** không thấy trên các trang chính thức đã đọc.

**SPayLater** ([điều khoản 31/10/2025](https://shopeepay.vn/spaylater-dieu-khoan-su-dung), [Shopee Blog 19/05/2026](https://shopee.vn/blog/spaylater-la-gi/)):

| Mục | Nội dung chính thức |
|---|---|
| Bên cấp tín dụng | "Bên cho vay" là tổ chức tín dụng được cấp phép; trang không nêu tên |
| Hạn mức | Do bên cho vay quyết định. Blog: "tối đa không vượt quá 50.000.000 VNĐ" |
| Phí kỳ đơn | "mức phí 0% được mặc định áp dụng cho mọi đơn hàng Shopee"; khoảng 45 ngày; không tính lãi |
| Trả góp | "Chỉ từ 2.95%/kỳ" |
| Phí trả chậm | "Mức cố định là 30.000 VNĐ/kỳ", cộng vào hóa đơn kỳ sau |
| Hạn trả | Hóa đơn phát hành ngày 14 hoặc 24; trả trước 15:00 ngày đến hạn |
| Nhắc và tự động trả | Có nhắc hạn; có thanh toán tự động (theo blog) |
| Hậu quả trễ | Có thể tạm ngừng dịch vụ, khóa ưu đãi; chấm điểm tín dụng qua CIC |
| Trách nhiệm tự đánh giá | "Bên vay phải cân nhắc tất cả các loại phí… dựa trên khả năng hoàn trả khoản vay của bản thân" (Điều 4.3) |

Điểm đáng chú ý: **điều khoản đặt việc tự tính khả năng trả nợ lên người dùng**. Yofina làm đúng việc này cho người dùng.

### 2.4 VNPAY (ngoài phạm vi so sánh, quyết định 24/11)

Nhóm quyết định **không xét VNPAY là đối thủ**: VNPAY mạnh ở cổng thanh toán cho doanh nghiệp, còn trả sau trên ví VNPAY là sản phẩm của Cake by VPBank. Các ghi chú dưới đây giữ lại để tham khảo, không đưa vào bảng so sánh và không cần kiểm thêm.


- Bài chính thức năm 2021 mô tả **Ví gia đình**: mở ví thành viên cho người thân, chủ ví đặt hạn mức chi tiêu cho từng ví thành viên, có nhắc lịch thanh toán hóa đơn định kỳ.
- **Trả sau trên ví VNPAY là sản phẩm của Cake by VPBank**, tích hợp theo hợp tác ký 24/12/2024 ([Báo Đầu tư](https://baodautu.vn/vnpay-hop-tac-voi-ngan-hang-so-cake-trien-khai-dich-vu-tai-chinh-so-cua-cake-tren-vi-vnpay-d235668.html), [Thị trường Tài chính Tiền tệ](https://thitruongtaichinhtiente.vn/vi-vnpay-tich-hop-dich-vu-tra-sau-va-vay-nhanh-cua-ngan-hang-so-cake-64899.html)). Thời gian miễn lãi đến 45 ngày.
- Điều khoản ví VNPAY (hiệu lực 11/05/2023) và trang biểu phí của VNPAY **không có mục trả sau**; biểu phí chỉ nêu cổng thanh toán, thu hộ, chi hộ (tối đa 2,5% giá trị giao dịch).
- Số phí trả sau **chỉ có từ nguồn thứ cấp** (VCCI, 28/10/2026): phí 33.000 ₫ mỗi kỳ có giao dịch, cộng vào dư nợ; thanh toán tối thiểu 30% dư nợ; phần còn lại chịu lãi **3,25%/tháng** từ ngày giao dịch. Không tìm được phí trễ hạn.
- Để tham khảo cùng nhà cung cấp: FPT Paylater (cũng do Cake cung cấp) công bố phí 33.000 ₫ tháng có dùng, phạt trễ 50.000 ₫ trên gốc, hạn mức 3–5 triệu ₫ ([cake.vn](https://cake.vn/tin-tuc/hoat-dong/FPT-paylater-5-trieu-tieu-di-ngai-gi-thanh-toan)). Đây là sản phẩm khác, không suy ra cho VNPAY.

### 2.5 Viettel Money

- **Quản lý chi tiêu:** trang `/quan-ly-chi-tieu/` là **bài tư vấn chung**, không mô tả tính năng trong app. Một trang khác nói app giúp "thiết lập ngân sách, đặt mục tiêu tiết kiệm và quản lý nợ", nhưng không có chi tiết. Trên App Store có chatbot, nhưng chỉ "hỗ trợ dịch vụ Gửi tiết kiệm"; có tính năng thanh toán tự động hóa đơn (bản 03/2026).
- **Ví trả sau Paynow** ([viettelmoney.vn/paynow](https://viettelmoney.vn/paynow/)):

| Mục | Nội dung chính thức |
|---|---|
| Bên cấp tín dụng | "các Tổ Chức Tín dụng chính thống"; nêu tên FE Credit cho sản phẩm 0% |
| Hạn mức | "2 triệu đồng/tài khoản" |
| Phí giao dịch | "4%/ giá trị giao dịch (đã bao gồm VAT)" |
| Lãi | "4.1%/tháng" trên dư nợ chưa trả; miễn lãi "Lên tới 45 ngày" |
| Thanh toán tối thiểu | "30% tổng chi tiêu trong kỳ (tối thiểu 100.000 VNĐ)". **Cùng trang có chỗ ghi 2%, tối thiểu 50.000 ₫; hai con số mâu thuẫn** |
| Hạn trả | Sao kê ngày 17 hoặc 22; đến hạn sau 15 ngày |
| Phí quá hạn | "3%/ số tiền quá hạn (tối thiểu 50,000đ)" |

## 3. Bảng so sánh

**Ký hiệu:**
- ✅ có, theo trang chính thức.
- ◐ có một phần.
- ✗ không thấy trên các trang chính thức đã đọc.
- ? không đọc được trang.

**Cột Yofina** (cập nhật 24/11 tối): "Đã chạy" là đã có trên bản deploy. Chi tiết và lỗi còn lại ở [13-tien-do-technical.md](13-tien-do-technical.md).

| Tiêu chí | MoMo | ZaloPay | ShopeePay | Viettel Money | **Yofina** |
|---|---|---|---|---|---|
| **A. Nhìn lại** | | | | | |
| Lịch sử theo danh mục, báo cáo | ✅ | ✅ | ✗ | ✗ | ✅ Đã chạy |
| Tự phân loại | ✅ | ✗ | ✗ | ✗ | ✅ Đã chạy đủ 4 bước (đúng 92%) |
| Ngân sách và cảnh báo vượt | ✅ | ◐ Tự đặt mốc | ✗ | ◐ Chỉ nêu tên | Không làm. Thay bằng dự báo ngày cạn |
| Chatbot AI về chi tiêu | ✅ Hỏi, ghi chép, thanh toán hóa đơn | ✗ | ✗ | ◐ Chỉ cho tiết kiệm | ✅ Đã chạy (số dư, giao dịch, dự báo) |
| Ghi giao dịch ngoài ví | ✅ Nhập tay hoặc qua chat | ✗ | ✗ | ✗ | ✅ Đã chạy: ảnh và CSV, chống trùng (OCR ảnh thật còn yếu) |
| **B. Hũ và lương** | | | | | |
| Chia lương | ◐ Máy tính gợi ý, "không lưu lại" | ✗ | ✗ | ✗ | ✅ Chia thật một chạm khi lương về |
| Hũ có số dư riêng | ✗ (có sản phẩm tiết kiệm riêng) | ✗ | ✗ | ✗ | ✅ |
| Tách tiền vào khác khỏi thu nhập | ✗ | ✗ | ✗ | ✗ | ✅ |
| **C. Nhìn trước** | | | | | |
| Dự báo ngày tiền cạn | ✗ ("Dự phóng" chỉ cho đầu tư) | ✗ | ✗ | ✗ | ✅ Đã chạy |
| Nghĩa vụ nằm trong kế hoạch chi | ✗ | ✗ | ✗ | ✗ | ✅ Đã chạy |
| Trước khi mua: tổng chi phí thật và ảnh hưởng tới các hũ | ◐ Mô phỏng trả góp (chỉ phí) | ◐ Xem dư nợ, phí sau khi phát sinh | ✗ (điều khoản giao cho người dùng tự cân nhắc) | ◐ Ví dụ phí trên trang | ✅ Đã chạy |
| Hỏi "nếu thì" | ✗ | ✗ | ✗ | ✗ | ✅ Đã chạy |
| Cú sốc, điểm chống chịu | ✗ | ✗ | ✗ | ✗ | ✅ Đã chạy |
| Lộ trình tự sửa | ◐ Chatbot giúp đặt mục tiêu | ✗ | ✗ | ◐ Chỉ nêu "đặt mục tiêu" | ✅ Đã chạy |
| **D. Trả sau** | | | | | |
| Có sản phẩm trả sau | ✅ đến 20 triệu | ✅ đến 30 triệu | ✅ đến 50 triệu | ✅ 2 triệu | ◐ Mô phỏng |
| Nhắc hạn | ✅ trước 5 ngày | ✅ thông báo dư nợ | ✅ + tự động trả | ✅ hằng tháng | ✅ trước 3 ngày, gắn với số dư hũ |
| **E. Minh bạch và an toàn của AI** | | | | | |
| Giải thích vì sao có gợi ý | ◐ Lý do của quy tắc chia | ✗ | ✗ | ✗ | ✅ Đã chạy: bảng "Vì sao" và trace |
| Bước xác nhận trước khi AI làm việc liên quan tới tiền | ✗ (trang không mô tả, dù chatbot thanh toán được hóa đơn) | — | — | — | ✅ Token dùng một lần (đã chạy) |
| Miễn trừ, nhãn AI | ◐ "không mang tính tư vấn đầu tư" | ✗ | ✗ | ✗ | Đề xuất BC-05 |
| **F. Thế mạnh mà Yofina không có** | | | | | |
| Thanh toán thật, mạng lưới đối tác | ✅ | ✅ | ✅ | ✅ | ✗ |
| Tín dụng thật qua đối tác | ✅ | ✅ | ✅ | ✅ | ✗ |
| Chống gian lận bằng AI | ✅ "bảo mật 5 lớp AI" | ? | ? | ? | ✗ |

## 4. Các khác biệt chính

### 4.1 MoMo mạnh ở "nhìn lại"; chưa ai làm "nhìn trước"

MoMo đã làm rất đầy đủ phần ghi nhận: tự phân loại, ngân sách, cảnh báo, chatbot, giao dịch ngoài ví. **Yofina không nên cạnh tranh ở phần này.** Trên mọi trang chính thức đã đọc, không sản phẩm nào công bố dự báo ngày tiền cạn hay đưa nghĩa vụ vào kế hoạch chi. "Dự phóng" duy nhất (của MoMo) là cho đầu tư.

**Hệ quả cho slide:** không viết "MoMo chỉ có báo cáo" hay "MoMo chưa có AI". Viết thế là sai theo chính trang của MoMo. Nên viết: "MoMo cho biết bạn **đã** chi vượt ngân sách; Yofina cho biết **trước** ngày nào bạn sẽ hụt, tính cả khoản trả sau đến hạn."

### 4.2 Cảnh báo ngân sách khác dự báo ngày cạn

| | Ngân sách và cảnh báo (MoMo) | Dự báo ngày cạn (Yofina) |
|---|---|---|
| Khi nào báo | Khi tổng đã chi **sắp hoặc đã vượt** hạn mức tự đặt | **Trước** khi xảy ra, theo tốc độ chi thật của từng hũ |
| Tính cả khoản sắp phải trả | Không | Có: trả sau, tiền trọ, hóa đơn, cộng lịch lương |
| Người dùng phải tự đặt | Hạn mức từng danh mục | Chỉ lương và ngày nhận |
| Trả lời câu hỏi | "Tôi đã tiêu bao nhiêu so với kế hoạch?" | "Tôi còn trụ được tới ngày nào, và có kịp tới lương không?" |

### 4.3 Hũ thật khác hũ gợi ý

- Công cụ Phân Bổ Lương của MoMo chỉ đưa tỷ lệ tham khảo và không lưu lại; ZaloPay chỉ đưa mẹo "quy tắc phong bì".
- Không ví nào tách lương thành **các số dư riêng có thể chuyển qua lại**. Sản phẩm gần nhất là tiết kiệm riêng (MoMo).

### 4.4 Phí trả sau: mỗi ví tính một kiểu, không ai cộng sẵn trước khi mua

Ví dụ minh họa: **mua 1.200.000 ₫ bằng trả sau, trả một lần** (không trả góp). Tính theo biểu phí chính thức, đã đơn giản hóa, giả định đã dùng hết ưu đãi miễn phí.

| Sản phẩm | Trả đúng hạn | Trễ khoảng 7 ngày | Cách tính |
|---|---|---|---|
| MoMo Ví Trả Sau | **1.233.000 ₫** (+2,75%) | khoảng **1.362.000 ₫** (+13,5%) | Phí 33.000 ₫ tháng có giao dịch; trễ 5–9 ngày: 10,5% số tiền chậm trả |
| ZaloPay (CIMB) | **1.220.000 ₫** (+1,7%) | khoảng **1.295.000 ₫** (+7,9%) | Phí 20.000 ₫/kỳ; phí sử dụng 60.000 ₫ (bậc dưới 1,5 triệu) + lãi khoảng 0,17%/ngày |
| SPayLater (đơn Shopee, 1 kỳ) | **1.200.000 ₫** (0%) | **1.230.000 ₫** (+2,5%) | 0% kỳ đơn; phí trễ cố định 30.000 ₫ |
| Viettel Money Paynow | **1.248.000 ₫** (+4%) | khoảng **1.310.000 ₫** (+9,2%) | Phí 4% giao dịch; quá hạn 3% (tối thiểu 50.000 ₫) + lãi 4,1%/tháng |

Bảng này cho thấy hai điều:
1. **Tổng phải trả dao động từ 0% đến khoảng 13,5%** cho cùng một món hàng, tùy sản phẩm và tùy trễ mấy ngày. Người dùng khó tự tính, và chính điều khoản của SPayLater đặt việc cân nhắc này lên người dùng.
2. **Phí trễ của MoMo tăng theo số ngày trễ, còn của ZaloPay tăng theo bậc dư nợ.** Một lời nhắc chung chung không cho người dùng thấy cái giá của việc trễ thêm vài ngày.

Đây là chỗ Yofina tạo giá trị khác biệt: **tính sẵn tổng phải trả và chỉ ra hũ nào hụt tháng sau, trước khi bấm mua** (FR6). Hiện Yofina chỉ có biểu phí của sản phẩm mô phỏng. **Đề xuất:** khi tích hợp thật, nạp biểu phí của đúng sản phẩm trả sau mà người dùng đang chọn vào bảng `fee_schedules`, kèm nguồn và ngày hiệu lực. Bảng này đã có sẵn cấu trúc.

### 4.5 Nhắc hạn: ai cũng có, nhưng tách khỏi kế hoạch chi

Mọi ví đều nhắc hạn trả sau: MoMo trước 5 ngày, ShopeePay có tự động trả, Viettel nhắc hằng tháng. Nhưng lời nhắc nằm trong sản phẩm tín dụng, không gắn với câu hỏi "**hũ nào sẽ trả khoản này, và hũ đó có đủ không**". Bằng chứng nghiên cứu (Medina 2021, [08 mục 3.4](08-kpi-kinh-doanh.md#34-k4-và-k4-r-giảm-phí-trễ-hạn-ít-nhất-10-tổng-phí-không-tăng)) cho thấy nhắc trả nợ có thể đẩy người dùng sang thiếu tiền ở chỗ khác. Đó chính là khoảng trống Yofina lấp.

### 4.6 AI có quyền làm việc liên quan tới tiền: cần bước duyệt rõ ràng

Chatbot của MoMo **ghi chép và thanh toán hóa đơn qua chat**. Trang chính thức không mô tả bước xác nhận cho các thao tác này. Có thể trong app có, cần mở app kiểm tra. Yofina có thể nói rõ và chứng minh được cơ chế của mình: AI chỉ đề xuất; người dùng bấm xác nhận; server cấp token dùng một lần; 13 ca tấn công đã bị chặn ([07 mục 6](07-dac-ta-luong-hoat-dong.md#6-cơ-chế-vận-hành-có-phải-human-in-the-loop-không)).

## 5. Hàm ý cho định vị

| Nên nói | Không nên nói |
|---|---|
| "Ví giúp bạn ghi lại và kiểm soát đã chi; Yofina cho bạn thấy trước ngày nào sẽ hụt" | "Các ví chỉ có báo cáo đơn giản" (sai với MoMo) |
| "Tổng phải trả cho cùng một món hàng trả sau dao động 0–13,5%; Yofina tính sẵn trước khi mua" | "Ví trả sau có phí ẩn" (phí đều công khai trong biểu phí) |
| "Hũ có số dư riêng; lương chia thật một chạm" | "MoMo không có tính năng chia lương" (có công cụ gợi ý) |
| "Yofina là lớp kế hoạch gắn vào ví, dùng lại phân loại và thanh toán của ví" | "Yofina thay thế ví" |

## 6. Việc nên làm tiếp

1. **Mở app** MoMo, ZaloPay, Shopee, Viettel Money và chụp màn hình các mục ở bảng mục 3. Ưu tiên kiểm:
   - Chatbot MoMo có bước xác nhận trước khi thanh toán hóa đơn không.
   - Hạn mức thực tế mỗi ví cấp cho tài khoản mới.
2. Đối chiếu biểu phí trên trang của **bên cấp tín dụng** (TPBank, MBV, CIMB, FE Credit), vì ví chỉ là kênh phân phối.
3. Sau khi kiểm xong, cập nhật bảng mục 3 và ghi ngày kiểm.

## 7. Nguồn chính thức đã đọc (truy cập 24/11/2026)

| Sản phẩm | Trang | Ngày trên trang |
|---|---|---|
| MoMo | [Quản lý chi tiêu](https://www.momo.vn/quan-ly-chi-tieu) · [Trợ thủ tài chính](https://www.momo.vn/tro-thu-tai-chinh) · [Phân Bổ Lương](https://www.momo.vn/tai-chinh/phan-bo-luong) · [Ví Trả Sau](https://www.momo.vn/vi-tra-sau) · [Biểu phí Ví Trả Sau](https://www.momo.vn/vi-tra-sau/bieu-phi) · [Phí chậm trả](https://www.momo.vn/hoi-dap/phi-cham-tra-vi-tra-sau) · [Hỏi đáp phí](https://www.momo.vn/hoi-dap/neu-dung-vi-tra-sau-thi-toi-se-bi-tinh-phi-nhu-the-nao) · [App Store](https://apps.apple.com/vn/app/momo-tr%E1%BB%A3-th%E1%BB%A7-t%C3%A0i-ch%C3%ADnh-v%E1%BB%9Bi-ai/id918751511) | Không ghi ngày; phí chậm trả hiệu lực 01/04/2026 |
| ZaloPay | [Biểu phí CIMB 2026](https://zalopay.vn/cap-nhat-bieu-phi-lai-cho-tai-khoan-tra-sau-tra-gop-cua-cimb-tren-zalopay-nam-2026-8107) · [Tài khoản trả sau](https://zalopay.vn/huy-tai-khoan-tra-sau-7073) · [Thanh toán tối thiểu](https://zalopay.vn/thanh-toan-toi-thieu-tai-khoan-tra-sau-6968) · [Tiết kiệm tiền Tết](https://zalopay.vn/tiet-kiem-tien-tieu-tet-8194) · [App Store](https://apps.apple.com/vn/app/zalopay-si%C3%AAu-qu%C3%A0-gi%C3%A1ng-sinh/id1112407590?l=vi) | 29/12/2025 (hiệu lực 28/01/2026); 02/07/2025; 17/06/2025; 30/01/2026 |
| ShopeePay | [Điều khoản SPayLater](https://shopeepay.vn/spaylater-dieu-khoan-su-dung) · [Shopee Blog: SPayLater](https://shopee.vn/blog/spaylater-la-gi/) | 31/10/2025; 19/05/2026 |
| VNPAY | [Ví thành viên](https://vnpay.vn/mo-vi-thanh-vien-cho-bo-me-con-cai-ngay-tren-vi-dien-tu-vnpay-x5cufcpbp1a) · [Thanh toán hóa đơn](https://vnpay.vn/mo-vi-vnpay-thanh-toan-trieu-hoa-don-moi-ngay-a91hk4hbd4) · [Điều khoản ví](https://vidientu-static.vnpay.vn/mobile-terms.html) · [Biểu phí dịch vụ](https://vnpay.vn/dich-vu/0f61zmr3hwgs). Thứ cấp: [VCCI](https://vcci.com.vn/tin-tuc/mua-truoc-tra-sau-va-vong-xoay-no-tu-nhung-khoan-chi-nho) | 18/06/2021; 23/04/2021; hiệu lực 11/05/2023; không ghi ngày; 28/10/2026 |
| Viettel Money | [Paynow](https://viettelmoney.vn/paynow/) · [Ví trả sau](https://viettelmoney.vn/vi-tra-sau/) · [Đóng tiền khoản vay](https://viettelmoney.vn/dong-tien-khoan-vay/) · [Quản lý chi tiêu (bài tư vấn)](https://viettelmoney.vn/quan-ly-chi-tieu/) · [App Store](https://apps.apple.com/vn/app/viettel-money/id1344204781?l=vi) | Không ghi ngày; App Store bản 8.8.63 (31/10) |
