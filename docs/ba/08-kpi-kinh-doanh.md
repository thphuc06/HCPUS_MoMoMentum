# KPI kinh doanh mục tiêu: benchmark và căn cứ

> Bản nháp để chủ dự án duyệt, viết ngày 24/11/2026. Bổ sung cho [06-mo-hinh-kinh-doanh.md](06-mo-hinh-kinh-doanh.md): file 06 định nghĩa **cách đo**, file này đặt **con số mục tiêu**. Mỗi con số có benchmark có nguồn và lý do vì sao Yofina có thể đạt được.
> Bối cảnh: hướng B2B2C, tức Yofina là tính năng nằm trong ví (đề xuất D-01). Nếu đổi hướng thì phần lớn mục tiêu ở nhóm A và E phải đặt lại.

## 1. Cách đặt mục tiêu

Mỗi KPI đi theo cùng một khuôn:

| Thành phần | Nghĩa |
|---|---|
| **Benchmark** | Con số đã đo được ở sản phẩm hoặc nghiên cứu tương tự, có nguồn |
| **Mục tiêu** | Con số Yofina cam kết |
| **Căn cứ** | Cơ chế trong sản phẩm làm con số đó khả thi, cộng lý do chọn mức cao hơn hay thấp hơn benchmark |
| **Độ chắc chắn** | **Cao**: đo được ngay trong cuộc thi. **Vừa**: có benchmark gần. **Thấp**: chưa có benchmark công khai, là giả thuyết của đội |

Ba nguyên tắc:
1. **Đặt mục tiêu quanh mức trung vị khá của ngành, không lấy mức của nhóm dẫn đầu.** Yofina là sản phẩm mới, nên chỉ vượt trung vị ở chỗ có cơ chế rõ ràng.
2. **Mỗi KPI chính đi kèm một KPI "rào chắn"** để không đạt số bằng cách gây hại cho người dùng. Ví dụ: giảm trễ hạn nhưng tổng phí không được tăng.
3. **Chia theo ba mốc thời gian**, vì mỗi mốc đo được những thứ khác nhau:

| Mốc | Thời điểm | Dữ liệu | Đo được gì |
|---|---|---|---|
| **M0: Cuộc thi** | 12/2026 | Mô phỏng, backtest | Chất lượng dự báo, tốc độ, chi phí mỗi lượt, độ an toàn |
| **M1: Pilot** | 8 tuần với một đối tác | Người dùng thật, có nhóm đối chứng | Giữ chân, trễ hạn, mức chấp nhận gợi ý |
| **M2: Năm đầu** | 12 tháng sau khi tích hợp | Toàn bộ người dùng trả sau của đối tác | Độ phủ, doanh thu, ROI |

## 2. Bảng KPI tổng hợp

| # | KPI | Mốc | Benchmark | Mục tiêu | Độ chắc chắn |
|---|---|---|---|---|---|
| K1 | Tỷ lệ người dùng trả sau dùng Yofina | M2 | Tính năng tài chính cá nhân trong ví: **khoảng 10%** (MoMo, 3 triệu trên 30 triệu); trợ lý AI ngân hàng sau 7 năm: **khoảng 35%** (Erica, 20,6 triệu trên 59 triệu) | **15%** người dùng trả sau sau 12 tháng | Vừa |
| K2 | Thời gian tới dự báo đầu tiên | M0 | Hiện đo được: đặt lại + tính dự báo khoảng 6 giây | **Dưới 2 phút** kể từ lúc bắt đầu onboarding | Cao |
| K3 | Giữ chân D30 | M1 | App tài chính: **7%** (UXCam), **11,6%** (Adjust); app tài chính Nhật Bản **8%** (Adjust, quý I/2026). Đông Nam Á: D30 của app tài chính trên Android **giảm 32%** so với năm trước (AppsFlyer 2026) | **≥ 15%** | Vừa |
| K4 | Giảm phí trễ hạn trả sau (so với đối chứng) | M1 | Nhắc hạn trong RCT: **−14%** phí trễ thẻ tín dụng; tin nhắn hành vi: **−4%** khả năng trễ | **≥ 10%** | Vừa |
| K4-R | *Rào chắn:* tổng phí mỗi người (mọi loại) | M1 | Cùng RCT trên: phí thấu chi **+9%** ở nhóm hay thấu chi | **Không tăng** so với đối chứng | Vừa |
| K5 | Số ngày cảnh báo trước khi hũ cạn | M0 | Mốc so sánh là dự báo seasonal naive (NFR-10) | **≥ 7 ngày** trung vị, cảnh báo đúng **≥ 70%** | Cao |
| K6 | Biên lợi nhuận gộp | M2 | Sản phẩm AI: **45%** (2025) → **52–53%** (2026, ICONIQ). Phần mềm SaaS: trung vị **80%** | **≥ 65%** toàn bộ; **≥ 75%** gói Cơ bản | Vừa |
| K7 | Chi phí AI trên doanh thu | M2 | Inference ở giai đoạn mở rộng: **khoảng 23%** giá vốn sản phẩm (ICONIQ) | **≤ 15%** doanh thu | Vừa |
| K8 | Tỷ lệ chuyển sang gói trả phí | M2 | Freemium mọi ngành: **2,1%** sau 35 ngày; app tài chính **khoảng 4%**; dùng thử 17–32 ngày: **42,5%** chuyển sang trả phí | **3%** người dùng kích hoạt; **≥ 35%** người dùng thử | Thấp–vừa |
| K10 **[đề xuất 24/11]** | Tỷ lệ người dùng có hũ đệm đạt ít nhất 1 tháng chi thiết yếu | M1 → M2 | Gen Z có tiết kiệm đủ hơn 3 tháng chi tiêu: **47%** (UOB ACSS 2026, tự khai); chưa có benchmark cho người dùng app | **≥ 25%** người dùng hoạt động sau 6 tháng (mục 3.9) | Thấp |
| K11 **[đề xuất 24/11]** | Ticket CSKH về phí, khoản trừ, hạn trả trên 1.000 người dùng/tháng | M1 | Chưa có benchmark Việt Nam; tham khảo Gartner: tự phục vụ rẻ hơn khoảng 7 lần so với có người hỗ trợ | **Giảm ≥ 20%** so với nhóm đối chứng; mốc lấy 3 tháng trước pilot ([06 mục 4.3](06-mo-hinh-kinh-doanh.md#43-roi)) | Vừa |
| K9 | ROI của đối tác | M1 → M2 | Không có benchmark công khai; tính bằng điểm hòa vốn (mục 3.6) | **≥ 1** (hòa vốn) cuối pilot; **≥ 3** năm đầu | Thấp |

## 3. Căn cứ cho từng KPI

### 3.1 K1: 15% người dùng trả sau dùng Yofina sau 12 tháng

- **Benchmark:**
  - Tính năng Quản Lý Chi Tiêu của MoMo có hơn 3 triệu người dùng mỗi tháng trên hơn 30 triệu người dùng, tức khoảng **10%** ([01, nguồn #10](01-boi-canh-thi-truong.md#9-nguồn)).
  - Trợ lý Erica của Bank of America có 20,6 triệu người dùng năm 2025 trên khoảng 59 triệu khách hàng số, tức khoảng **35%**, sau 7 năm vận hành [K-2].
- **Vì sao cao hơn 10% của MoMo:**
  - Yofina không nhắm toàn bộ người dùng ví mà nhắm **nhóm có trả sau** (khoảng 2 triệu người ở MoMo). Đây là nhóm có pain point rõ nhất: 37,5% có từ 3 tài khoản trả sau, 29,8% từng trả chậm ([01, mục 4.2](01-boi-canh-thi-truong.md#42-mua-trước-trả-sau-và-nợ-nhỏ)).
  - Lối vào đặt **đúng lúc cần**: ngay khi chọn trả sau, hoặc ngay khi thẻ "hũ sắp cạn" hiện lên. Tính năng quản lý chi tiêu thông thường thì người dùng phải tự tìm.
  - Onboarding chỉ có 2 trường bắt buộc (BR-01). Khi tích hợp vào ví, lương có thể được gợi ý sẵn từ giao dịch.
- **Vì sao thấp hơn 35% của Erica:** Erica là trợ lý chung cho mọi việc ngân hàng và đã chạy 7 năm. Yofina mới ra mắt và chỉ làm một việc.

### 3.2 K2: thấy dự báo đầu tiên trong dưới 2 phút

- **Đã đo:** đặt lại dữ liệu kèm tính dự báo mất khoảng 6 giây. Tính lại một người dùng khi Lambda đang ấm mất khoảng 1 giây ([pipelines/forecast](../../pipelines/forecast/README.md#số-đo-lambda-arm64-aurora-thật)).
- **Căn cứ:** onboarding chỉ có 3 màn (O1–O3), và dự báo được tính đồng bộ ngay sau khi lưu (L02 trong [07](07-dac-ta-luong-hoat-dong.md)). Phần lớn của 2 phút là thời gian người dùng nhập liệu.
- KPI này quan trọng vì nó đo việc **người dùng thấy giá trị ngay trong phiên đầu**: D1 của app tài chính chỉ khoảng 28–30% [K-1], tức phần lớn người dùng không quay lại sau ngày đầu.

### 3.3 K3: giữ chân D30 từ 15%

- **Benchmark:** trung vị app tài chính ở D30 là 7% (UXCam 2026) hoặc 11,6% (Adjust 2026, qua nguồn thứ cấp) [K-1]. Nguồn thấp nhất và cao nhất chênh nhau nhiều vì mỗi nhà cung cấp đo một kiểu.
- **Vì sao vượt được trung vị:** phần lớn app quản lý chi tiêu **không có lý do để quay lại** ngoài việc tự ghi chép. Yofina có **lịch quay lại tự nhiên**, gắn với tiền thật:
  - Lương về mỗi tháng: cần bấm chia lương (L07).
  - Hạn trả sau ngày 5: nhắc trước 3 ngày (BR-27).
  - Mỗi giao dịch làm dự báo đổi trong khoảng 3 giây, nên thẻ chủ động luôn có nội dung mới (L09, L18).
  - Nằm trong ví nên đi kèm thói quen mở ví hằng ngày để thanh toán.
- **Vì sao không đặt cao hơn:** nhắc quá nhiều sẽ phản tác dụng, nên BR-60 giới hạn tối đa 1 nhắc mỗi ngày. Yofina chấp nhận giữ chân thấp hơn một chút để không làm phiền.
- **Đo thế nào:** cần bảng `product_events` (đề xuất D-05 ở file 06).

### 3.4 K4 và K4-R: giảm phí trễ hạn ít nhất 10%, tổng phí không tăng

Đây là **KPI giá trị quan trọng nhất**, vì nó vừa là lợi ích cho người dùng vừa là lý do để bên cho vay trả tiền.

- **Bằng chứng nhân quả từ thử nghiệm ngẫu nhiên (RCT):**
  - **Medina (2021)**, Review of Financial Studies: nhắc hạn thanh toán thẻ tín dụng trên một nền tảng quản lý tài chính ở Brazil làm **phí trả chậm giảm 14%** [K-4].
  - Cùng nghiên cứu đó: **phí thấu chi tăng 9%**, tập trung ở người hay thấu chi. Với nhóm này, tổng phí còn **tăng 5%**; các người dùng còn lại tiết kiệm được 15%. Nói cách khác, nhắc trả nợ này có thể làm thiếu tiền chỗ khác.
  - Ngân hàng Colombia (Review of Finance, 2026; 7.063 khách trễ hạn): tin nhắn hành vi làm khả năng trễ **giảm 4%** [K-5].
  - Fintech cho vay (2025; 17.545 người vay): tin nhắn nhắc nợ giảm trễ hạn có ý nghĩa so với nhóm không nhắc [K-6].
- **Vì sao Yofina có thể đạt 10%:**
  - Yofina không chỉ nhắc ngày. Nó **giữ tiền trước**: khoản trả sau nằm trong dự báo của hũ Nghĩa vụ từ lúc mua, nên người dùng thấy hũ sắp không đủ trước nhiều ngày (K5).
  - Kiểm tra trước khi quẹt (L14) chặn từ gốc những khoản sẽ làm hụt tháng sau.
- **Vì sao đặt 10% chứ không 14%:** ví đã có sẵn nhắc hạn (MoMo nhắc trước 5 ngày, ZaloPay, ShopeePay có tự động trả; [09 mục 4.5](09-phan-tich-doi-thu.md#45-nhắc-hạn-ai-cũng-có-nhưng-tách-khỏi-kế-hoạch-chi)), nên phần Yofina **cộng thêm** sẽ nhỏ hơn hiệu ứng của nhắc hạn so với không nhắc gì.
- **Vì sao phải có rào chắn K4-R:** nghiên cứu của Medina cho thấy chỉ đo phí trễ hạn có thể che đi việc người dùng phải trả phí khác. Yofina có lợi thế thiết kế ở đây: dự báo **xem toàn bộ các hũ cùng lúc**, nên gợi ý trả nợ sẽ không làm hụt hũ khác mà người dùng không biết. Nhưng điều này phải được **đo**, không chỉ khẳng định.

### 3.5 K5: cảnh báo trước ít nhất 7 ngày, đúng từ 70%

- **Đo được ngay** bằng backtest trên 3 persona và trên bộ sinh dữ liệu khác họ ([backtest-phase-2.md](../research/backtest-phase-2.md)).
- **Căn cứ:** tầm dự báo là 30 ngày, kèm lịch lương và lịch nghĩa vụ đã biết trước. Persona demo `minh` được báo cạn ngày 23/11, trước kỳ lương 12 ngày.
- **Định nghĩa "đúng":** hũ được dự báo trạng thái Hụt hoặc Sát thì thực tế cạn trong khoảng ±3 ngày quanh ngày dự báo, hoặc người dùng đã hành động để tránh. Định nghĩa này cần chủ dự án duyệt.

### 3.6 K6, K7: biên lợi nhuận gộp ≥ 65%, chi phí AI ≤ 15% doanh thu

- **Benchmark:**
  - Sản phẩm AI có biên lợi nhuận gộp trung bình **45%** năm 2025, dự kiến **52–53%** năm 2026. Inference chiếm khoảng **23%** giá vốn ở giai đoạn mở rộng (ICONIQ, qua nguồn thứ cấp) [K-3].
  - Phần mềm SaaS có trung vị **80%** (Benchmarkit 2026) [K-3].
- **Vì sao Yofina gần SaaS hơn là sản phẩm AI thuần:** **phần lớn giá trị không cần LLM**.
  - Dự báo chạy batch đêm bằng numpy (Monte Carlo khoảng 0,65 giây mỗi người dùng). Thẻ chủ động, nhắc hạn và kiểm tra trước khi quẹt đều do engine tất định quyết định.
  - Một lượt chat thường tốn **2 lượt model nhỏ** (router và viết câu). Chỉ hỏi "nếu thì" mới dùng model lớn, và có trần **4 lượt mỗi câu** (BR-41).
  - Có trần lượt gọi mỗi ngày (NFR-35). Hết trần thì rơi về thẻ số liệu, không phát sinh thêm chi phí.
- **Vì sao không đặt 80%:** chi phí hạ tầng cố định (Aurora chạy liên tục) chiếm tỷ trọng lớn khi còn ít người dùng, và gói Chuyên sâu (đọc ảnh, lộ trình) tốn model lớn.
- **Còn thiếu:** chi phí AI thật mỗi lượt chưa đo. Token đã được ghi log; cần tính ở phase 6 (NFR-37) rồi mới khẳng định được K7.

### 3.7 K8: 3% người dùng kích hoạt chuyển sang trả phí

- **Benchmark:** freemium mọi ngành **2,1%** (RevenueCat 2026); app tài chính khoảng **4%** (một nguồn khác, phương pháp khác). Dùng thử 17–32 ngày có **42,5%** chuyển sang trả phí [K-7].
- **Vì sao 3%:** cao hơn mức chung vì có khoảnh khắc giá trị rõ (được cảnh báo trước khi hụt), nhưng **thấp hơn 4%** vì người Việt ít trả phí cho app ([06, nguồn N7](06-mo-hinh-kinh-doanh.md#8-nguồn)).
- **Đòn bẩy:** cho dùng thử 30 ngày, để bao trọn **một kỳ lương** và người dùng thấy ít nhất một cảnh báo trước hạn. Giá đặt thấp hơn phí dịch vụ trả sau 33.000 ₫/tháng.
- **Lưu ý:** nếu đối tác chọn trả phí bản quyền cho toàn bộ người dùng (không bán gói lẻ) thì KPI này không áp dụng.

### 3.8 K9: ROI của đối tác, tính bằng điểm hòa vốn

Chưa có benchmark công khai cho ROI của tính năng quản lý tài chính trong ví. Vì vậy dùng **điểm hòa vốn**: mức giảm trễ hạn tối thiểu để đối tác không lỗ.

```
Giá trị mỗi người dùng mỗi tháng (chỉ tính phần giảm trễ hạn)
  = Δ tỷ lệ trễ hạn × Dư nợ trung bình × Chi phí mỗi đồng trễ (tổn thất + thu hồi)

Hòa vốn khi: Phí Yofina mỗi người dùng/tháng ≤ Giá trị trên
```

Ví dụ minh họa, **mọi số là giả định** cần thay bằng số của đối tác:

| Biến | Giả định |
|---|---|
| Dư nợ trung bình | 2.000.000 ₫ |
| Chi phí mỗi đồng trễ | 10% (gần chi phí tín dụng ngành tài chính tiêu dùng 11,5%, FiinGroup; [11 mục 5a](11-can-bang-chi-phi-va-loi-ich.md)) |
| Δ tỷ lệ trễ hạn | 1 điểm % |
| Giá trị mỗi người dùng/tháng | 2.000.000 × 1% × 10% = **2.000 ₫** |

Hệ quả cho việc định giá:
- **Nếu chỉ dựa vào giảm trễ hạn, phí bản quyền phải ở mức khoảng 2.000 ₫ mỗi người dùng/tháng thì mới hòa vốn.** Muốn ROI ≥ 3 với mức phí đó, cần giảm trễ hạn khoảng 3 điểm %, hoặc phải cộng thêm giá trị giữ chân và bán chéo.
- Phần tiết kiệm CSKH (K11) chỉ khoảng 160 ₫/người dùng/tháng trong ví dụ của 06 mục 4.3c: **dễ chứng minh sớm nhưng nhỏ**, dùng làm bằng chứng đầu tiên của pilot, không dùng để gánh giá.
- Vì vậy, khi chào đối tác, nên **tính cả giá trị giữ chân** (K3 nhân với doanh thu mỗi người dùng của ví), và bắt đầu với **mức phí thấp hoặc chia sẻ lợi ích đo được** trong pilot.

### 3.9 K10: hũ đệm đạt ít nhất 1 tháng chi thiết yếu (đề xuất 24/11)

- **Vì sao cần:** K1–K9 đo người dùng có dùng không và đối tác có lời không, nhưng chưa đo trực tiếp **người dùng có an toàn hơn không**. K10 đo kết quả của cơ cấu hũ mới (BR-64, BR-65), và cũng là điều kiện mở R7 (chỉ gợi ý tích lũy khi hũ đệm đủ).
- **Benchmark:** 47% Gen Z tự khai có tiết kiệm đủ chi tiêu hơn 3 tháng (UOB ACSS 2026, [01](01-boi-canh-thi-truong.md)). Số này là tự khai trên toàn bộ tiền tiết kiệm, không phải số dư một hũ trong app, nên chỉ dùng làm trần tham khảo.
- **Vì sao chọn 1 tháng sau 6 tháng, mục tiêu 25%:** mục tiêu mặc định của hũ đệm là 3 tháng (C-13). Với bộ "Mới đi làm", hũ đệm nhận 15% lương, còn chi thiết yếu (nhà ở 30%, ăn uống 30%, đi lại 7%, trả sau 3%) khoảng 70% lương (bộ đã hiệu chỉnh ở [02 mục B2a](02-business-rules.md)). Như vậy cần khoảng 5 kỳ lương để có 1 tháng chi thiết yếu nếu chia đủ mỗi kỳ. 6 tháng chừa chỗ cho các kỳ bị rút hoặc chia thiếu. 25% (khoảng một nửa của 47%) là mức thận trọng.
- **Cách đo:** số dư hũ `buffer` ÷ chi thiết yếu hằng tháng (BR-64), ở người dùng hoạt động từ 6 tháng, so với nhóm đối chứng trong pilot ([06 mục 4.4](06-mo-hinh-kinh-doanh.md#44-cách-đo-thật-pilot-có-nhóm-đối-chứng)).
- **Giới hạn:** người dùng có thể giữ tiết kiệm ở ngân hàng, ngoài ví. K10 đo hành vi trong sản phẩm, không đo toàn bộ tài sản.

## 4. Dự phóng chi phí vận hành

| Khoản | Hiện tại (đo được) | Khi mở rộng | Cách dự phóng |
|---|---|---|---|
| **Cố định**: Aurora 0,5 ACU chạy liên tục | Khoảng 2,4 USD/ngày, tức khoảng 73 USD/tháng | Tăng theo bậc ACU khi tải tăng (tự co giãn) | Theo dõi ACU trung bình trên Cost Explorer (tag `project=yofina`) |
| **Biến đổi theo người dùng**: dự báo | Khoảng 1 giây Lambda 1.769 MB mỗi người dùng mỗi lần chạy; 1 lần/đêm + 1 lần/giao dịch | Tuyến tính theo số người dùng và số giao dịch | (Số lần chạy/người/tháng) × (giây × GB) × giá Lambda |
| **Biến đổi theo lượt**: AI | Token đã ghi log, chưa tổng hợp | Tuyến tính theo số lượt chat, phụ thuộc cơ cấu ý định | (Lượt/người/tháng theo từng ý định) × (token/lượt) × giá model. **Đo ở phase 6** |
| **Biến đổi theo lượt**: API, Gateway, DynamoDB | Theo số request | Tuyến tính | Lấy từ Cost Explorer sau pilot |

**Việc cần làm để dự phóng có căn cứ:** ở phase 6, chạy bộ câu đánh giá (golden set) và tính **chi phí trung bình mỗi lượt theo từng ý định**. Sau đó lắp vào bảng trên với giả định số lượt mỗi người dùng. Chỉ khi có số này mới chốt được K6, K7 và giá gói.

## 5. Ma trận KPI theo bên hưởng lợi

| Bên | KPI họ quan tâm | Mốc |
|---|---|---|
| Người dùng | K4, K4-R, K5, K10 | M0, M1, M2 |
| Ví (MoMo) | K1, K3, K8 | M1, M2 |
| Bên cho vay trả sau | K4, K9 | M1, M2 |
| Đội Yofina | K6, K7, K8 | M2 |
| Giám khảo cuộc thi | K2, K5, cộng NFR (độ trễ, độ đúng của số, an toàn) | M0 |

**Cho slide cuộc thi:** nên trình bày **K5 và K2** (số thật, đo được), **K4 kèm bằng chứng RCT** (lý do vì sao sản phẩm có giá trị), và **K9 dạng công thức hòa vốn** (cho thấy đội hiểu kinh tế đơn vị). Các KPI còn lại để ở phụ lục.

## 6. Việc cần chủ dự án quyết

| ID | Câu hỏi | Gợi ý |
|---|---|---|
| E-01 | Duyệt bộ mục tiêu K1–K9 | Đặc biệt là K4 (10%) và K3 (15%) |
| E-02 | Định nghĩa "cảnh báo đúng" cho K5 | ±3 ngày quanh ngày dự báo, hoặc người dùng đã hành động |
| E-03 | Đưa KPI nào lên slide | K2, K5, K4 kèm RCT, K9 dạng hòa vốn |
| E-04 | Giao việc đo chi phí AI mỗi lượt vào phase 6 | Bắt buộc để chốt K6, K7 và giá gói |

## 7. Nguồn

- Bổ sung 24/11 cho K3: [Adjust, Japan finance app growth 2026](https://www.adjust.com/blog/japan-finance-app-growth-2026/) · [AppsFlyer State of Marketing in APAC 2026, qua TechNode Global](https://technode.global/2026/08/27/appsflyer-apac-app-marketing-installs-monetization-2026/).

| # | Nguồn | Ngày | Ghi chú |
|---|---|---|---|
| K-1 | [UXCam: Mobile App Retention Benchmarks 2026](https://uxcam.com/blog/mobile-app-retention-benchmarks/); [Panto: Mobile App Retention Statistics 2026](https://www.getpanto.ai/blog/mobile-app-retention-statistics) (dẫn Adjust) | 2026 | Blog nhà cung cấp công cụ; phương pháp khác nhau |
| K-2 | [Bank of America: AI and digital innovations fuel 30 billion client interactions](https://newsroom.bankofamerica.com/content/newsroom/press-releases/2026/03/bofa-ai-and-digital-innovations-fuel-30-billion-client-interacti.html) | 10/03/2026 | Thông cáo chính thức: 20,6 triệu người dùng Erica năm 2025; khoảng 59 triệu khách hàng số |
| K-3 | [SaaStr: Have AI gross margins really turned the corner](https://www.saastr.com/have-ai-gross-margins-really-turned-the-corner/); [CloudZero: AI gross margin](https://www.cloudzero.com/blog/ai-gross-margin) | 2026 | Số ICONIQ và Benchmarkit qua nguồn thứ cấp; định nghĩa biên lợi nhuận có thể khác nhau |
| K-4 | Medina, P. (2021). [Side Effects of Nudging: Evidence from a Randomized Intervention in the Credit Card Market](https://ideas.repec.org/a/oup/rfinst/v34y2021i5p2580-2607..html). *Review of Financial Studies* 34(5), 2580–2607 | 2021 | Ngoài mốc 12 tháng, nhưng là bằng chứng nhân quả (RCT) đã bình duyệt; giữ vì không có thay thế mới hơn cùng chất lượng |
| K-5 | [Behavioral messages and debt repayment](https://doi.org/10.1093/rof/rfag015), *Review of Finance* | 2026 | RCT ngân hàng Colombia, 7.063 khách trễ hạn; chưa đọc toàn văn |
| K-6 | [Gender differences in reactions to loan collection mechanisms: A large-scale natural field experiment](https://www.sciencedirect.com/science/article/abs/pii/S104295732500052X) | 2025 | 17.545 người vay fintech; chưa đọc toàn văn, chưa có số hiệu ứng cụ thể |
| K-7 | [RevenueCat: State of Subscription Apps 2026](https://www.revenuecat.com/blog/growth/subscription-app-trends-benchmarks-2026); [ProductGrowth: Freemium benchmarks](https://www.productgrowth.blog/calculators/freemium) | 2026 | Số app tài chính 4% dùng phương pháp khác với RevenueCat |
