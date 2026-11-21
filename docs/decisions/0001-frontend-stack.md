# ADR-0001: Stack frontend và hướng giao diện

- **Trạng thái**: Đã chốt
- **Ngày**: 2026-11-21
- **Người/agent quyết định**: chủ dự án (sau khi xem ảnh chụp màn hình của spike)
- **Liên quan**: proposal §12, §14; [open-questions](../requirements/open-questions.md); [frontend-fintech-ui.md](../research/frontend-fintech-ui.md); [spike-frontend-stack.md](../research/spike-frontend-stack.md); ai-log 2026-11-21

## Bối cảnh

Chủ dự án muốn UI là app kiểu ngân hàng trên điện thoại (chuyển tiền, biểu đồ tài chính, hũ chi tiêu, chatbot AI có đầu ra render từ JSON) và tiêu chí chọn stack là "cái nào cho giao diện đẹp nhất". Proposal §14 ghi Next.js + React, Tailwind, Recharts hoặc visx. Không dùng frontend của FAST.

## Các lựa chọn đã cân nhắc

1. **Next.js (App Router)** theo proposal — tài liệu Amplify Hosting ghi không hỗ trợ Next.js streaming; app đăng nhập rồi mới dùng nên SSR không đem lại gì; thêm khái niệm server/client component.
2. **React + Vite SPA, shadcn/ui + Tailwind 4, Recharts + SVG tự vẽ** — đã dựng thử và build được trong spike; chủ dự án xem ảnh chụp và thấy ổn.

## Quyết định

Chọn lựa chọn 2:

- React + Vite + TypeScript, dạng SPA, host tĩnh.
- shadcn/ui (Base UI) + Tailwind 4.
- Recharts cho biểu đồ dự báo (dải P10–P90, mốc ngày, what-if); SVG tự vẽ cho hũ có mực nước và gauge điểm chống chịu.
- Motion và NumberFlow cho animation; font Plus Jakarta Sans tự host.
- `@ag-ui/client` làm client mỏng; khối UI render qua registry `type → component` có Zod schema, dùng chung cho màn hình chính và chat.
- Hướng giao diện như màn hình mẫu của spike: nền kem, màu chủ đạo chàm, thẻ số dư + hành động nhanh, thẻ hũ, thanh tab dưới 5 mục, chat dạng bottom sheet mở từ nút giữa.

Phiên bản đã chạy được và các lệnh đúng: xem [spike-frontend-stack.md](../research/spike-frontend-stack.md).

## Hệ quả

- Lệch proposal §14 ở framework (Vite thay Next.js).
- Màn hình mẫu mới chứng minh stack làm được; spike tự đánh giá giao diện còn giống shadcn mặc định (icon, thẻ, hũ đơn giản). Cần thêm công thiết kế để có nét riêng.
- Các lỗi đã biết phải mang sang app thật: vá bottom sheet khi dùng snap points, nút preset quá nhỏ cho cảm ứng, parse từng khối riêng thay vì cả mảng.
- Chưa thử: điện thoại thật, Amplify Hosting, backend AgentCore thật (CORS, JWT, interrupt/resume), React Router.
- Code thật viết trong `frontend/`; `spikes/frontend-stack/` chỉ là bản thử để tham khảo.

## Nguồn đã tra

- Liệt kê trong [frontend-fintech-ui.md](../research/frontend-fintech-ui.md) và [spike-frontend-stack.md](../research/spike-frontend-stack.md).
