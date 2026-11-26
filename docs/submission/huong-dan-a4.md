# Yofina Foresight · Hướng dẫn dùng thử

> Bản nháp markdown của tờ hướng dẫn 1 trang A4 (PDF) trong bộ nộp, issue #36. Số đo và thời gian chờ cập nhật sau lượt eval RC 2/12/2026.

Trợ lý tài chính "Hũ nhìn trước" (chủ đề Trợ lý AI · Trợ lý tài chính): báo trước hũ chi tiêu nào sắp cạn, tính cả Ví Trả Sau, và đề xuất lộ trình mới khi chi tiêu đổi.

**App**: https://main.dcrwn4u7vqklo.amplifyapp.com (điện thoại hoặc trình duyệt máy tính)
**Tài khoản**: `giamkhao1`, `giamkhao2`, `giamkhao3` · mật khẩu gửi trong form nộp bài
**Dữ liệu**: ví mô phỏng của persona Minh (22 tuổi, lương 9 triệu ngày 5); mọi số là dữ liệu tổng hợp. Ví có 8 hũ: 3 hũ mặc định mà tài khoản mới nào cũng có (Chi hằng ngày, Nghĩa vụ, Dự phòng) và 5 hũ Minh tự thêm để theo dõi riêng (Ăn uống, Đi lại, Giải trí, Du lịch, Đầu tư).

**Trước khi bắt đầu**: Hồ sơ → **Đặt lại dữ liệu**. Ngày trong app về 21/11/2026.

**Cảnh 1 · Hũ sắp cạn** (khoảng 30 giây)
Mở tab **Nhìn trước**. Hũ Ăn uống dự kiến cạn ngày 23/11, trước kỳ lương 5/12. Chạm vào hũ để xem đường số dư 30 ngày và độ tin cậy.

**Cảnh 2 · Hỏi "nếu thì"** (khoảng 1 phút)
Bấm **Hỏi Yofina**, gõ: *Nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao?* Chờ khoảng 15–30 giây: đường số dư trước và sau, tổng chi phí gồm phí, 2–3 phương án; hũ Nghĩa vụ báo thiếu tiền cho khoản Trả sau đến hạn 05/12, đúng ngày lương (khoản này trả bằng số dư trước khi lương về). Bấm **Vì sao** để xem dữ liệu đã dùng và luật đã kiểm, rồi **Chi tiết kỹ thuật** để xem trace từng bước.

**Cảnh 3 · Cú sốc** (khoảng 30 giây)
Tab **Nhìn trước** → mục **Điểm chống chịu** → **Thử cú sốc tài chính** → **Mất việc 2 tháng**. Điểm tụt và app báo số ngày trụ được.

**Cảnh 4 · Chi tiêu đổi, lộ trình đổi**
Tải tệp https://main.dcrwn4u7vqklo.amplifyapp.com/samples/minh_sao_ke_2_tuan.csv → Tổng quan → **Tiền vào** → **Nạp ảnh / sao kê ngoài ví** → **Tải sao kê CSV** → tích đồng ý → **Đồng ý và tải lên** → **Xác nhận thêm 32 dòng**. Tab **Nhìn trước** → thẻ Lộ trình **Có phiên bản mới** → **So với bản cũ**.
**Lưu ý: Tải tệp cảnh 4 trong ngày đặt lại dữ liệu hoặc chậm nhất ngày hôm sau**, và làm cảnh 4 trước cảnh 5. Tải lại cùng tệp sẽ bị từ chối là trùng.

**Cảnh 5 · Nạp ảnh chứng từ**
Tải ảnh https://main.dcrwn4u7vqklo.amplifyapp.com/samples/minh_bien_lai_1.png → cùng màn nạp → **Chọn ảnh có sẵn**. Họ tên, số tài khoản, số điện thoại trên ảnh bị che; chọn hũ Ăn uống nếu chưa có → xác nhận.

**Nên thử thêm**: "Nên mua cổ phiếu nào?" (trợ lý từ chối đúng phạm vi) · "Kỳ này mình tiêu bao nhiêu?" · Hồ sơ → **Bộ nhớ của tôi** (xem, xóa từng mục).

**Giới hạn**: các số đo phân loại (đúng 92%, phải hỏi 17,4%), ngưỡng hiện % (47 ngày lịch sử cho hũ chi đều, 120 ngày cho hũ chi thưa) và ngưỡng phát hiện chi tăng (2,04 lần) đo trên ví nhiều hũ như ví của Minh. Tài khoản mới 3 hũ chưa đo đủ; hũ gộp như Chi hằng ngày không tách hành vi theo từng loại chi, muốn theo dõi riêng thì tách hũ. Chi tiết: README, mục "Giới hạn đã biết".

Mọi thay đổi số dư cần bạn bấm xác nhận; trợ lý không tự chuyển tiền. Mã nguồn và tài liệu: README trong tệp `.zip`.
