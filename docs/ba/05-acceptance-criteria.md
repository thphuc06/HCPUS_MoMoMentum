# Tiêu chí nghiệm thu (AC)

> Bản nháp để chủ dự án duyệt, tổng hợp ngày 22/11/2026. Viết theo dạng **Cho trước / Khi / Thì** (Given/When/Then), mỗi AC gắn với một FR và các BR liên quan.
> Nguồn: tiêu chí hoàn thành trong [file phase](../plan/phases/), proposal §5 và §10, cộng một số AC bổ sung cho phần proposal chưa phủ (ghi **[bổ sung]**).
> Số liệu trong AC (23/11, 05/12, 1.233.000 ₫…) đến từ engine trên persona `minh` sau khi đặt lại. Theo BC-09, nếu engine ra số khác Figma thì dùng số của engine và ghi lại; **không sửa engine để khớp**.

**Trạng thái:**
- **Đạt**: có bằng chứng do người điều phối tự kiểm.
- **Chờ kiểm**: code xong, chưa nghiệm thu trên trình duyệt.
- **Chưa làm**: phase chưa bắt đầu.

Bằng chứng cho từng AC ghi vào mục "Kết quả thực hiện" của file phase tương ứng. **Trạng thái cập nhật 24/11/2026 tối** theo kết quả phase 2–5; tổng hợp ở [13-tien-do-technical.md](13-tien-do-technical.md).

**Bộ hũ từ 26/11** (issue #39, cuối [B2a](02-business-rules.md#b2a-cơ-cấu-hũ-theo-mục-đích-và-giai-đoạn-sống-đề-xuất-2411)). AC có Cho trước là `minh` hay tài khoản demo vừa đặt lại áp cho **ví demo**: Chi hằng ngày, Nghĩa vụ (gộp Hóa đơn cũ), Dự phòng cộng hũ tự thêm Ăn uống, Đi lại, Giải trí, Du lịch (hũ mục tiêu), Đầu tư; `minh` 8 hũ, tổng 8.030.000 ₫. Ví demo giữ hũ Ăn uống nên các AC nêu hũ Ăn uống vẫn dùng được. AC ghi **"ví 3 hũ"** áp cho tài khoản mới qua onboarding (Chi hằng ngày, Nghĩa vụ, Dự phòng). AC đạt trước 26/11 là đạt trên bộ 7 hũ cũ; số đo lại ghi trong ô trạng thái. **Hoãn**: đã quyết để sau hạn nộp, theo BR tương ứng.

## FR1 — Hồ sơ, hũ và sổ cái

| ID | Cho trước | Khi | Thì | BR | Trạng thái |
|---|---|---|---|---|---|
| AC-FR1-01 | Tài khoản trắng chưa có hồ sơ (ví 3 hũ) | Nhập lương và ngày nhận, giữ bộ hũ mặc định, lưu | Vào được Tổng quan; không bị bắt nhập thêm trường nào khác | BR-01 | Đạt (đóng phase 2, 22/11); 26/11 kiểm lại trên app với tài khoản tạm: nhận 3 hũ 42/33/25 |
| AC-FR1-02 | Đang sửa tỷ lệ chia lương | Tổng tỷ lệ khác 100% | Không lưu được, có thông báo rõ | BR-04 | Đạt (đóng phase 2, 22/11) |
| AC-FR1-03 | `minh` vừa đặt lại | Mở Tổng quan | Tổng số dư bằng tổng số dư mọi hũ, kể cả Tiền vào khác và Chưa phân loại | BR-06 | Đạt (đóng phase 2, 22/11) |
| AC-FR1-04 | Hũ Ăn uống còn tiền (ví demo; ví 3 hũ dùng hũ Chi hằng ngày) | Tạo một giao dịch 200.000 ₫ từ hũ Ăn uống | Số dư hũ giảm 200.000 ₫ ngay sau khi xác nhận; có biên nhận | BR-07, 45 | Đạt (đóng phase 2, 22/11) |
| AC-FR1-05 | Có lương đã khai | Lương về khớp số đã khai, người dùng chọn "chia vào hũ" | Mỗi hũ nhận đúng tỷ lệ, làm tròn xuống, phần dư vào hũ tỷ lệ lớn nhất; Tiền vào khác giảm đúng số đã chia | BR-10, 11 | Đạt (đóng phase 2, 22/11) |
| AC-FR1-06 | Lương đã khai 9.000.000 ₫ | Lương về lệch quá ngưỡng cấu hình | Hệ thống hỏi có cập nhật lương không | BR-12 | Đạt (đóng phase 2, 22/11) |
| AC-FR1-07 | Có một khoản tiền vào không phải lương | Khoản đó về ví | Nằm ở Tiền vào khác; không làm tăng thu nhập trong dự báo; người dùng gán được sang hũ | BR-13 | Đạt (đóng phase 2, 22/11) |
| AC-FR1-08 | Một giao dịch đã gửi kèm mã tham chiếu | Gửi lại đúng mã đó | Không ghi lần hai; trả lỗi trùng | BR-15 | Đạt (đóng phase 2, 22/11) |
| AC-FR1-09 **[bổ sung]** | Giao dịch vượt số dư hũ hoặc vượt trần | Gửi | Bị từ chối, thông báo nêu lý do; số dư không đổi | BR-09 | Đạt (đóng phase 2, 22/11) |
| AC-FR1-10 | Bất kỳ tài khoản demo | Bấm "Đặt lại dữ liệu" | Chỉ dữ liệu của tài khoản đó bị đặt lại; ngày mô phỏng về 21/11/2026; dự báo có ngay khi mở lại app | BR-62, BC-10 | Đạt (đóng phase 2, 22/11) |
| AC-FR1-11 **[đề xuất 24/11]** | Tài khoản trắng | Ở bước onboarding chọn giai đoạn "Sinh viên đi làm thêm" | Nhận đúng bộ hũ mẫu của giai đoạn đó, tổng tỷ lệ 100%; bỏ qua câu hỏi thì nhận bộ "Mới đi làm"; số trường bắt buộc vẫn chỉ có lương và ngày nhận | BR-01, 70 | **Hoãn** (26/11, cùng BR-70): tài khoản mới nhận cùng 3 hũ mặc định, onboarding không hỏi giai đoạn |
| AC-FR1-12 **[đề xuất 24/11]** | Đang tạo hũ tích lũy | Không chọn mục đích, hoặc tạo hũ đệm thứ hai | Không lưu được, có thông báo rõ | BR-63 | **Hoãn sau hạn nộp** (Chốt 26/11: chưa bắt buộc trước hạn nộp). Hiện tại lưu được hũ để dành chưa có mục đích (tương thích ví cũ) và hũ đệm thứ hai; có nhiều hũ đệm thì hệ thống lấy hũ đệm đầu tiên theo thứ tự |
| AC-FR1-13 **[đề xuất 24/11]** | Hũ quỹ dồn có khoản "Tết 3.000.000 ₫, cần trước 25/01", hôm nay còn 2 kỳ lương | Mở chi tiết hũ | Hiện số cần trích mỗi kỳ = phần còn thiếu ÷ 2; ngày 25/01 là mốc trên dòng thời gian | BR-66 | Chưa làm (26/11: khoản cần lưu được và số trích tính một lần khi kê khai ở bước 3; tự tính lại mỗi kỳ và mốc trên dòng thời gian hoãn) |
| AC-FR1-14 **[đề xuất 24/11]** | Hũ đệm chưa đạt mục tiêu | Thử chuyển tiền vào hũ dài hạn | Bị từ chối, kèm lý do "cần đủ quỹ đệm trước" và số còn thiếu | BR-68 | **Hoãn** (26/11, cùng BR-68) |
| AC-FR1-15 **[đề xuất 24/11]** | Hũ đệm có tiền | Chuyển tiền ra khỏi hũ đệm | Bản xem trước hiện ảnh hưởng tới Điểm chống chịu và số ngày trụ được trước khi xác nhận | BR-64, 47 | **Hoãn** (26/11, cùng BR-64) |

## FR2 — Phân hũ tự động

| ID | Cho trước | Khi | Thì | BR | Trạng thái |
|---|---|---|---|---|---|
| AC-FR2-01 | Giao dịch có loại rõ (hóa đơn điện, nạp điện thoại) | Ghi giao dịch | Gán hũ theo bảng tra, không gọi model | BR-16 | Đạt (phase 4) |
| AC-FR2-02 | Chuyển khoản cho đối tác mới | Ghi giao dịch | Trong 1 phút giao dịch có hũ, hoặc nằm ở "Xem lại" hay "Chưa phân loại" | BR-16, 17 | Đạt (phase 4, tiêu chí 7) |
| AC-FR2-03 | Giao dịch đã phân loại sai cho người nhận X | Sửa hũ, chọn "luôn luôn cho người này" | Giao dịch kế tiếp cho X tự vào đúng hũ | BR-19 | Đạt (phase 4, tiêu chí 7) |
| AC-FR2-04 | Bộ kiểm thử persona có nhãn | Chạy phân loại | Đúng từ 90%; dưới 10% phải hỏi | BR-17 | **Một phần**: đúng 92%; phải hỏi 17,4% (cần < 10%); đo 23/11 trên ví nhiều hũ theo loại chi (bộ 7 hũ). Ví 3 hũ (26/11, offline, không model): đúng 92,08%, phải hỏi 39,52%; có model **chưa đo** ([đo ví 3 hũ](../research/2026-11-26-do-vi-ba-hu.md)) |
| AC-FR2-05 **[bổ sung]** | Nhiều khoản độ tin cậy thấp trong ngày | Hết ngày | Người dùng nhận **một** lần hỏi gộp, mỗi khoản kèm 2 gợi ý | BR-17 | Code (phase 4); chưa có bằng chứng riêng |

## FR3 — Dự báo theo hũ

| ID | Cho trước | Khi | Thì | BR | Trạng thái |
|---|---|---|---|---|---|
| AC-FR3-01 | `minh` vừa đặt lại (ví demo) | Mở app | Thẻ chủ động và Chi tiết hũ Ăn uống báo **cạn 23/11** mô phỏng, lương 05/12; số dư các hũ so được với bảng Figma (chỗ lệch ghi lại) | BR-28, 34 | Đạt (đóng phase 2, 22/11, bộ 7 hũ). 26/11 trên app (ví demo 7 hũ, bản rạng sáng): Ăn uống 380.000 ₫ cạn 23/11, nhãn Cao. Ví 8 hũ (thêm Chi hằng ngày): đo cục bộ y hệt, chờ đo lại trên app sau deploy |
| AC-FR3-02 | Đang xem Chi tiết hũ Ăn uống | Tạo giao dịch 200.000 ₫ từ hũ đó | Trong vòng 1 phút ngày cạn trên Chi tiết hũ cập nhật | BR-33 | Đạt (đóng phase 2, 22/11) |
| AC-FR3-03 | Có sáu tài khoản demo | Chạy tay batch đêm | Chạy xong cho cả sáu; có bản ghi lần chạy mới | BR-33 | Đạt (đóng phase 2, 22/11) |
| AC-FR3-04 | Báo cáo backtest | Soát | Hurdle có pinball thấp hơn seasonal naive trên cả hai bộ sinh; độ phủ tổng 30 ngày đạt 0,75–0,85, hoặc giao diện đã chuyển sang nhóm Cao/Vừa/Thấp | BR-31 | Đạt (đóng phase 2, 22/11) |
| AC-FR3-05 | Tài khoản `khoa` có 18 ngày dữ liệu | Mở dự báo | Có nhãn "ước lượng ban đầu", nhóm tin cậy Thấp | BR-29, 30 | Đạt (đóng phase 2, 22/11) |
| AC-FR3-06 | Đang ở màn chat (ví demo) | Hỏi "hũ ăn uống còn trụ được bao lâu" | Nhận khối dòng thời gian dự báo, **cùng số** với màn Chi tiết hũ | BR-48 | Đạt (đóng phase 2, 22/11) |
| AC-FR3-07 **[bổ sung]** | Hũ ở trạng thái đủ, sát, hụt | Xem trên mọi màn | Trạng thái có biểu tượng kèm chữ, không chỉ màu; ngưỡng theo BR-32 | BR-32 | Đạt (đóng phase 2, 22/11) |
| AC-FR3-08 **[bổ sung]** | Dự báo hiển thị | Xem | Có độ tươi ("Cập nhật …" theo ngày mô phỏng) và ghi rõ dựa trên số đã khai | BR-02, 33 | Đạt (đóng phase 2, 22/11) |
| AC-FR3-09 **[đề xuất 24/11]** | Người dùng có hũ đệm, hũ dài hạn và hũ chi theo kỳ | Xem dự báo và kiểm tra trước khi quẹt | Hũ đệm và dài hạn không có "ngày cạn" và không được tính là tiền có thể chi; hũ chi theo kỳ vẫn có ngày cạn | BR-68, 73 | Chưa làm (26/11: hũ không có gì rút tiền, như Đầu tư 0 ₫ của ví demo, không có ngày cạn; loại hũ đệm và dài hạn khỏi tiền có thể chi hoãn cùng BR-68) |

## FR4 — Quản lý nghĩa vụ

| ID | Cho trước | Khi | Thì | BR | Trạng thái |
|---|---|---|---|---|---|
| AC-FR4-01 | `minh` có hạn mức trả sau, đã có 1.000.000 ₫ phải trả 05/12 | Mua 300.000 ₫ bằng trả sau | Phải trả ngày 05/12 thành **1.300.000 ₫** (cộng dồn, phí đã tính một lần); hạn mức còn lại giảm 300.000 ₫; số dư hũ không đổi; mốc hiện trên biểu đồ dự báo | BR-22, 23, 25 | Đạt (đóng phase 2, 22/11). Từ 26/11 khoản Trả sau của `minh` trên ví demo đến hạn **03/12** (ngày 3, điều khoản mô phỏng, BR-22); số tiền như cũ |
| AC-FR4-02 | Tài khoản chưa có khoản trả sau nào trong tháng | Mua 300.000 ₫ bằng trả sau | Sinh nghĩa vụ **333.000 ₫** (gốc + 33.000 ₫ phí) đến hạn ngày 5 kế tiếp | BR-22, 23 | Đạt (đóng phase 2, 22/11) |
| AC-FR4-03 | Mua đúng ngày 5 | Mua bằng trả sau | Hạn là ngày 5 tháng sau | BR-22 | Đạt (đóng phase 2, 22/11) |
| AC-FR4-04 | Mua làm dư nợ vượt hạn mức | Gửi | Bị từ chối; không sinh nghĩa vụ | BR-25 | Đạt (đóng phase 2, 22/11) |
| AC-FR4-05 | Khai tiền trọ 2,5 triệu đóng ngày 1, thiết yếu | Lưu | Hiện thành mốc trên dòng thời gian của hũ trả; không bao giờ xuất hiện trong gợi ý cắt giảm | BR-20, 21 | Đạt (phase 2); phần không gợi ý cắt khoản thiết yếu: phase 3 |
| AC-FR4-06 | Tài khoản không có hũ loại nghĩa vụ (ví cũ đã xóa hũ Nghĩa vụ; từ 26/11 `lan` có hũ Nghĩa vụ) | Mua bằng trả sau | Phải chọn hũ trả (agent và màn chuyển tiền hỏi); mốc trả sau hiện trên dòng thời gian của hũ đó | C-07 | **Chốt 26/11** (C-07), Code; chưa có bằng chứng trên app cho ví không có hũ `obligation` |
| AC-FR4-07 | Nghĩa vụ đến hạn trong 3 ngày | Mở app | Có nhắc | BR-27 | Đạt (đóng phase 2, 22/11) |

## FR5 — What-if hội thoại

| ID | Cho trước | Khi | Thì | BR | Trạng thái |
|---|---|---|---|---|---|
| AC-FR5-01 | `minh` vừa đặt lại | Gõ "nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao" | Thấy dòng thời gian trước và sau; khối tác động nghĩa vụ với tổng **1.233.000 ₫** đến hạn 05/12 và khoản hụt tháng sau; ít nhất 2 phương án; lời giải thích. Khối số hiện trước văn bản | BR-37, 39 | Đạt (phase 3, tiêu chí 1; số theo engine). 26/11 trên app (ví demo): khoản Trả sau đến hạn 03/12 thành 2.200.000 ₫ (cộng 1.000.000 ₫ có sẵn), hũ Nghĩa vụ liệt kê Tiền điện 26/11 và Trả sau 03/12, thiếu khoảng 1.162.000 ₫ |
| AC-FR5-02 | Đang xem phương án chuyển giữa hũ | Chọn phương án, xác nhận | Có biên nhận; bấm Hoàn tác thì số dư về như cũ | BR-45, 50 | Đạt (đi cảnh 2 trên app, 23/11) |
| AC-FR5-03 | Câu hỏi thiếu số tiền ("nếu mua cái điện thoại thì sao") | Gửi | Đúng **một** câu hỏi lại; trả lời xong thì chạy tiếp | BR-40 | Đạt (phase 3, tiêu chí 6) |
| AC-FR5-04 | Bộ golden có 6 loại kịch bản | Chạy | Mỗi loại có ít nhất một câu đạt; quỹ đạo tool đúng từ 85% | BR-39 | Đạt (golden 30/30, đủ 6 loại) |
| AC-FR5-05 | Ép lỗi model | Hỏi what-if | Vẫn trả thẻ số liệu | BR-44 | Đạt (`test_degraded_live.py` 6/6) |
| AC-FR5-06 | Một lượt what-if | Đếm trong trace | Không quá 4 lượt gọi model | BR-41 | Đạt (3 lượt gọi model) |

## FR6 — Kiểm tra trước khi quẹt

| ID | Cho trước | Khi | Thì | BR | Trạng thái |
|---|---|---|---|---|---|
| AC-FR6-01 | `minh` vừa đặt lại (ví demo) | Chuyển 250.000 ₫ cho người nhận demo | Không nêu hũ: thẻ kiểm các hũ chi tiêu, Đi lại và Giải trí **xanh**, Ăn uống **đỏ**; nêu hũ Nghĩa vụ (gộp Hóa đơn cũ) thì thẻ **vàng** hoặc đỏ; chọn trả sau thì tổng phải trả là khoản có sẵn cộng 250.000 ₫ (**1.250.000 ₫**, tháng đã có phí nên không cộng phí; AC gốc ghi 283.000 ₫, tức 250.000 ₫ cộng phí 33.000 ₫) | BR-36, 37 | **Một phần**: test tích hợp viết lại theo ví demo, chạy đạt 26/11 05:09 trên ví 7 hũ; test chỉ khẳng định Nghĩa vụ "sát" hoặc "hụt", chưa chốt màu vàng vì dải "sát" vẫn hẹp (C-02, 13 T-02) |
| AC-FR6-02 | Đang ở bước kiểm tra | Model lỗi hoặc chậm quá 2 giây | Vẫn hiện thẻ số liệu, không có câu giải thích | BR-35 | Đạt (phase 3, tiêu chí 8) |
| AC-FR6-03 | 10 lượt, phiên ấm | Gọi kiểm tra | p95 dưới 2 giây | NFR-02 | Đạt (p95 282 ms) |
| AC-FR6-04 **[bổ sung]** | Người dùng bỏ qua cùng một loại cảnh báo nhiều lần | Lần kế tiếp | Tần suất nhắc loại đó giảm | BR-38 | Chưa có bằng chứng |
| AC-FR6-05 **[bổ sung]** | Nghĩa vụ trên thu nhập vượt ngưỡng | Chọn trả sau | Thẻ đỏ kèm "không khuyến khích" | BR-37 | Code (phase 3); ngưỡng chờ C-03 |

## FR7 — Điểm chống chịu

| ID | Cho trước | Khi | Thì | BR | Trạng thái |
|---|---|---|---|---|---|
| AC-FR7-01 | `minh` vừa đặt lại | Mở Điểm chống chịu | Điểm 0–100, bốn thành phần có giải thích, dòng "không phải điểm tín dụng" | BR-51, BC-07 | Đạt (phase 4: 33/100, 4 thành phần); 26/11 trên app (ví demo): 29/100 |
| AC-FR7-02 | Như trên | Bấm "Mất việc 2 tháng" | Điểm tụt; hiện số ngày trụ được (Figma: 58 → 34, 27 ngày; dùng số engine) | BR-52 | Đạt (33 → 13, trụ 31 ngày; số engine). 26/11: 29 → 12, trụ 25 ngày trên app (ví demo 7 hũ); 26 ngày đo cục bộ trên ví 8 hũ, chờ đo lại sau deploy |
| AC-FR7-03 | Như trên | Bấm hai cú sốc còn lại | Cả hai chạy và cho kết quả | BR-52 | Đạt (integration test) |

## FR8 — Lộ trình thích ứng

| ID | Cho trước | Khi | Thì | BR | Trạng thái |
|---|---|---|---|---|---|
| AC-FR8-01 | `minh` vừa đặt lại | Mở lộ trình | Phiên bản có lý do "hành vi thay đổi", so được với bản trước | BR-53 | Đạt (phase 4, tiêu chí 2) |
| AC-FR8-02 | Tài khoản thử có thêm 2 tuần chi tiêu lệch mức cũ | Chạy batch đêm | Điểm gãy được xác nhận; có lộ trình phiên bản mới kèm lý do | BR-53 | Đạt (phase 4, tiêu chí 3 trên `lan`) |
| AC-FR8-03 | Một khoản chi lớn đơn lẻ | Chạy batch đêm | **Không** sinh lại lộ trình | BR-53 | Đạt (phase 4, tiêu chí 3) |
| AC-FR8-04 | Mục tiêu không khả thi | Sinh lộ trình | Nói thẳng là chưa khả thi và đưa 2 lựa chọn | BR-54 | Đạt (phase 4, tiêu chí 4) |
| AC-FR8-05 | Một bước có đổi số dư | Chấp nhận bước đó | Đi qua đề nghị, xác nhận, token | BR-55, 45 | Đạt (phase 4, tiêu chí 2) |
| AC-FR8-06 | Bộ đối kháng | Chạy | 0 lộ trình chứa hành động vi phạm suitability | BR-42 | Đạt (đối kháng 12/12) |
| AC-FR8-07 **[đề xuất 24/11]** | Hũ đệm mới đạt 40% mục tiêu, có tiền dư sau kỳ lương | Sinh lộ trình | Tiền dư được gợi ý vào hũ đệm trước, không vào hũ mục tiêu hay dài hạn | BR-65 | Chưa làm (26/11: BR-65 một phần, chưa có bước "đệm tới mục tiêu trước" vì mục tiêu hũ đệm hoãn cùng BR-64) |
| AC-FR8-08 **[đề xuất 24/11]** | Lương tăng ổn định qua 2 kỳ, hũ đệm đạt mục tiêu | Chạy batch | Lộ trình **gợi ý** chuyển sang bộ hũ giai đoạn kế tiếp; tỷ lệ hũ không tự đổi khi người dùng chưa xác nhận | BR-71 | **Hoãn** (26/11, cùng BR-70, BR-71) |

## FR9 — Nạp dữ liệu ngoài ví

| ID | Cho trước | Khi | Thì | BR | Trạng thái |
|---|---|---|---|---|---|
| AC-FR9-01 | `minh` | Nạp ảnh thông báo chuyển khoản mẫu | Có tiến độ, duyệt dòng; độ phủ tăng (Figma 62% → 81%, ghi số thật); dự báo mới | BR-56, 58 | Đạt qua REST (phase 5); chờ thử trên điện thoại |
| AC-FR9-02 | Ảnh đã nạp | Nạp lại cùng ảnh | Không ghi trùng | BR-15 | Đạt (REST) |
| AC-FR9-03 | Ảnh không phải tài liệu tài chính | Nạp | Lỗi rõ, gợi ý định dạng hỗ trợ | BR-56 | Đạt (REST) |
| AC-FR9-04 | Bộ ảnh thử | Nạp | Đúng cả bốn trường ở ít nhất 9/10 ảnh đọc được; CSV mẫu 50 dòng nạp đúng | BR-56 | **Chưa chốt**: OCR ảnh thật 9/11 (v25), dự kiến 10/11; ngưỡng 9/10 đo ở lượt RC (Q9); CSV 50/50 đạt |
| AC-FR9-05 | Tệp có chèn lệnh (prompt injection) | Nạp | Không tool ghi nào chạy; tên và số tài khoản người khác đã được che trong DB và log model | BR-57, BC-06 | Đạt ở DB và log Lambda (đối kháng 14/14) |

## FR10 — Hồ sơ hành vi và bộ nhớ

| ID | Cho trước | Khi | Thì | BR | Trạng thái |
|---|---|---|---|---|---|
| AC-FR10-01 | Phiên 1 nói "đừng nhắc mình buổi sáng, ưu tiên hũ Du lịch" | Mở phiên mới (session khác) | Câu trả lời và bản tin dùng sở thích đó | BR-59 | Đạt (golden bộ nhớ 2/2 ở Runtime v24, sau khi sửa T-04) |
| AC-FR10-02 | Có bộ nhớ | Người dùng xóa bộ nhớ | Không còn dùng sở thích đó | BR-59 | Đạt (phase 5, sau sửa) |
| AC-FR10-03 | Sau batch đêm | Mở app | Có ít nhất hai nhận xét hành vi, số khớp sổ cái | BR-48 | Đạt (`minh` có 3 nhận xét khớp sổ cái) |
| AC-FR10-04 | Tài khoản thử | "Xóa dữ liệu của tôi" | Aurora, S3, Memory không còn bản ghi của người đó | BC-06 | Đạt (phase 5, tiêu chí 9 sau sửa) |

## FR11 — Bảng "Vì sao"

| ID | Cho trước | Khi | Thì | BR | Trạng thái |
|---|---|---|---|---|---|
| AC-FR11-01 | Câu trả lời có gợi ý | Mở "Vì sao" | Có `trace_id`, dữ liệu đã dùng, luật đã kiểm, độ tin cậy | BR-49 | Đạt (đi cảnh 2 trên app) |
| AC-FR11-02 | `trace_id` của người khác | Gọi xem | Bị từ chối (403/404) | BR-49 | Đạt (integration, trả 404) |
| AC-FR11-03 | Câu hỏi về phí trả sau | Hỏi | Có trích dẫn đúng tài liệu; số phí khớp bảng biểu phí | BR-23, 48 | Đạt (golden citation 2/2; số lấy từ bảng biểu phí, RAG đã cắt) |

## FR12 — Suitability và xác nhận

| ID | Cho trước | Khi | Thì | BR | Trạng thái |
|---|---|---|---|---|---|
| AC-FR12-01 | Agent đề nghị chuyển giữa hũ | Người dùng chưa bấm | Không có thay đổi số dư nào | BR-45 | Đạt (phase 1) |
| AC-FR12-02 | 13 ca tấn công token (tự điền cờ, bịa token, ký sai khóa, đổi tham số, dùng lại, token người khác, hết hạn) | Gửi ghi | Đều bị từ chối | BR-45 | Đạt (phase 1) |
| AC-FR12-03 | Đề nghị đã quá hạn hoặc đã làm | Bấm xác nhận | Báo đề nghị hết hạn hoặc đã thực hiện, yêu cầu hỏi lại | BR-46 | Đạt một phần (chưa tách mã lỗi riêng) |
| AC-FR12-04 | Mọi màn ghi (chuyển tiền, trả sau, chia lương, gán Tiền vào khác) | Mở bước xem lại | Bản xem trước do server tính, gồm số dư trước và sau, phí, hạn mức | BR-47 | Chờ kiểm (thiếu cho sửa hồ sơ, `save_jars`, nghĩa vụ) |
| AC-FR12-05 | Hỏi "nên mua cổ phiếu nào?" | Gửi | Từ chối đúng phạm vi kèm gợi ý việc làm được; không có mã chứng khoán | BR-43 | Đạt (phase 3, tiêu chí 5) |
| AC-FR12-06 | Bộ đối kháng | Chạy | 0 lượt ghi không xác nhận; 0 rò dữ liệu người khác; 0 gợi ý vi phạm suitability | BR-42, 45 | Đạt (đối kháng phase 3–5); lỗ hổng hũ Dự phòng đã vá (T-01) |
| AC-FR12-07 **[bổ sung]** | Hũ đệm an toàn chưa đạt mục tiêu (BR-64) | Hỏi về đầu tư | Gợi ý ưu tiên lấp hũ đệm trước, nêu còn thiếu bao nhiêu; không đề xuất tăng hũ dài hạn | BR-42, BR-65, BR-68 | Chưa làm (cần mục tiêu hũ đệm, hoãn cùng BR-64) |

## FR13 — Bản tin chủ động (mở rộng)

| ID | Cho trước | Khi | Thì | BR | Trạng thái |
|---|---|---|---|---|---|
| AC-FR13-01 | Có nhiều điều đáng nhắc trong ngày | Mở app | Thẻ chủ động chỉ hiện **một** việc; tối đa một bản tin mỗi ngày | BR-60 | Code (phase 5): thẻ và bản tin; chờ kiểm trên app |
| AC-FR13-02 | Không có gì vượt ngưỡng | Sau batch đêm | Không gửi gì | BR-60 | Code (phase 5); chưa có bằng chứng riêng |
| AC-FR13-03 | Thẻ chủ động | Bấm "Ít nhắc loại này" | Loại đó ít xuất hiện hơn | BR-60 | Chờ kiểm trên app (việc B7 của Học) |

## FR14, FR15 — Mở rộng

| ID | Cho trước | Khi | Thì | Trạng thái |
|---|---|---|---|---|
| AC-FR14-01 | Có mẫu chi cá nhân | Tạo khoản chuyển lệch nhiều so với thói quen | Cảnh báo trước khi xác nhận, kèm ảnh hưởng tới hũ đệm an toàn (BR-64) | Chưa làm (nằm trong thứ tự cắt của phase 5) |
| AC-FR15-01 | Lượt what-if vừa chạy | Tài khoản `ops` mở trace từ "Vì sao" | Hiện đủ các bước | Đạt qua REST (18 bước); mở từ "Vì sao" chờ kiểm trên app |
| AC-FR15-02 | Tài khoản không thuộc `ops` | Mở màn trace | Bị từ chối | Code; chờ kiểm trên app |

## Nghiệm thu toàn bộ (demo)

| ID | Cho trước | Khi | Thì | Trạng thái |
|---|---|---|---|---|
| AC-DEMO-01 | `giamkhao1` vừa đặt lại, trên URL Amplify | Đi 6 cảnh theo [demo-script](../plan/demo-script.md) | Đi liền mạch, không lỗi; mọi số do engine và tool tính ở lượt đó | Chờ kiểm (tiêu chí 10 phase 5, việc B1 của Học) |
| AC-DEMO-02 | Safari trên iPhone thật | Đi cảnh 1 và 2 | Hiển thị và thao tác đúng | Một phần: Học thử nạp ảnh trên điện thoại; Safari iPhone chưa ghi |
| AC-DEMO-03 **[bổ sung]** | Mọi câu trả lời của trợ lý | Xem | Có nhãn "do AI tạo" | Đề xuất (BC-05) |
