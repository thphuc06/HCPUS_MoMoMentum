# Kịch bản demo (video 3 phút)

Nguồn: proposal §15. Kể câu chuyện của persona **Minh** (22 tuổi, thu nhập 9 triệu/tháng, lương ngày 5, sáu hũ sau khi đặt lại dữ liệu, một hạn mức Trả Sau) qua 6 cảnh. Giám khảo làm lại được từng cảnh bằng tài khoản demo có sẵn dữ liệu (§13: có nút đặt lại, phương án dự phòng tất định, video quay sẵn). Số trong cảnh là minh họa trong proposal, sẽ chỉnh theo persona thật.

| Cảnh | Thời lượng | Trên màn hình | Tính năng |
|---|---|---|---|
| 1 | 0:00–0:30 | Mở dự báo hũ Chi hằng ngày. Số dư đầu 1.080.000 ₫ dự kiến cạn khoảng 02–03/12, trước kỳ lương 05/12. Hai nguyên nhân: nhịp chi hằng ngày và 700.000 ₫ đã để riêng sang hũ Nghĩa vụ. | F1 |
| 2 | 0:30–1:15 | Gõ "nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao". Hũ Nghĩa vụ liệt kê các khoản đến hạn trước lương: cơm văn phòng, tiền điện, Trả Sau. Khoản thiếu đầu tiên là Trả Sau ngày 03/12, thiếu khoảng 761.000 ₫. Tổng đến hạn 2.200.000 ₫ đã gồm phí 33.000 ₫ của kỳ hiện tại. Ngày 03/12 là điều khoản mô phỏng của dữ liệu demo (spec Minh và BR-22 dùng ngày 5). | F2, F3 |
| 3 | 1:15–1:45 | Bấm "mất việc 2 tháng". Điểm chống chịu tụt từ 26 xuống 13, trụ được 31 ngày | F4 |
| 4 | 1:45–2:20 | Lộ trình sinh lại. Mở bảng "Vì sao". Hỏi "nên mua cổ phiếu nào" và thấy trợ lý từ chối đúng phạm vi | F5, suitability |
| 5 | 2:20–2:50 | Chụp ảnh một thông báo chuyển khoản nạp vào. Độ phủ dữ liệu tăng, dự báo cập nhật | F6 |
| 6 | 2:50–3:00 | Màn hình trace cho đội sản phẩm: mọi quyết định của agent xem lại được | Góc "Future Workspace" |

## Yêu cầu dữ liệu cho demo (suy ra, cần xác nhận)

- Trước cảnh 1 và 2, dùng Đặt lại dữ liệu ở tài khoản demo Minh để nhận bộ bốn hũ demo (Chi hằng ngày, Nghĩa vụ, Dự phòng, Mục tiêu). Dữ liệu mẫu chuyển 700.000 ₫ từ Chi hằng ngày sang Nghĩa vụ và đặt kỳ Trả Sau ngày 03/12. Ngày lương vẫn là 05/12. Số dự báo do engine cục bộ tính từ ngày mô phỏng 21/11/2026 (chạy lại 25/11 sau khi đổi sang bộ bốn hũ). Ngày cạn của cảnh 1 rơi vào 02/12 hoặc 03/12 tùy hạt Monte Carlo, vốn sinh từ mã người dùng (`user_seed`); nên chạy thử trên đúng tài khoản demo trước khi quay.
- Dữ liệu tổng hợp nên hiệu chỉnh theo số công khai (§13 rủi ro "dữ liệu tổng hợp trông không thật"); cho giám khảo tự tạo giao dịch và nạp ảnh.
- Câu hỏi mở liên quan: demo dùng tên/biểu phí Ví Trả Sau thật hay sản phẩm mô phỏng.
