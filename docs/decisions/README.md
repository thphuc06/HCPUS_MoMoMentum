# Architecture Decision Records (ADR)

Mỗi quyết định kỹ thuật đáng nhớ là một file `NNNN-tiêu-đề-ngắn.md` (đánh số tăng dần, bắt đầu từ `0001`). Dùng [template.md](template.md).

**Khi nào viết ADR**: chốt một câu hỏi trong [open-questions](../requirements/open-questions.md) có ảnh hưởng kiến trúc (Region, Chronos-2 hay thống kê…); chọn thư viện/dịch vụ thay thế điều proposal ghi; đổi hướng so với proposal.

**Quy ước**: trạng thái `Đề xuất` → `Đã chốt` → (nếu đổi) `Thay thế bởi ADR-NNNN`; không xóa ADR cũ. Mỗi ADR ghi nguồn tài liệu đã tra (link) và trỏ lại entry [ai-log](../ai-log/README.md) khi có.

## Danh sách

| ADR | Tiêu đề | Trạng thái |
|---|---|---|
| [0001](0001-frontend-stack.md) | Stack frontend và hướng giao diện | Đã chốt |
| [0002](0002-xac-nhan-truoc-khi-ghi.md) | Xác nhận trước khi ghi bằng token dùng một lần do server cấp | Đã chốt |
| [0003](0003-dong-ho-mo-phong.md) | Đồng hồ mô phỏng theo tài khoản | Đã chốt |
| [0004](0004-lech-so-voi-proposal.md) | Lệch so với proposal (bảng gộp: proposal nói gì, đang chạy gì, vì sao) | Đề xuất |
