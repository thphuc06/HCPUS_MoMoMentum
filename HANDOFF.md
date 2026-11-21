# HANDOFF — ảnh chụp trạng thái hiện tại

> **Quy ước**: cập nhật (ghi đè phần trạng thái bên dưới) vào **cuối mỗi phiên làm việc**. HANDOFF là ảnh chụp hiện tại; lịch sử thay đổi nằm ở [docs/ai-log/](docs/ai-log/README.md). Đầu phiên mới: đọc file này trước.

Cập nhật lần cuối: 2026-11-21, sau khi chạy bảy spike và đồng bộ tài liệu.

## Đang ở đâu trong kế hoạch

Tuần 1 (21–27/11/2026), ngày đầu. Mục tiêu tuần 1 theo proposal §15: "nền chạy được từ đầu đến cuối". Hạn nộp giả định trước chung kết 11/12/2026 (chưa xác nhận). Xem [docs/plan/README.md](docs/plan/README.md).

## Vừa làm xong

- Dựng cấu trúc thư mục + README từng thư mục code (chưa có code, chưa có package.json/pyproject/CDK app, chưa cài gì).
- Chuyển PDF proposal vào `docs/proposal/`; viết [proposal-summary.md](docs/proposal/proposal-summary.md).
- Viết tài liệu: architecture (project-structure, overview), requirements (FR/NFR, open-questions), decisions (README + template, chưa có ADR), references (links.md, aws-tooling.md), research (README), plan, ai-log.
- Chủ dự án chốt: **không kéo FAST về, không dùng frontend của FAST**; FAST chỉ để tham khảo, code tự viết theo tài liệu chính thức. Thư mục agent đổi từ `patterns/yofina-agent/` thành `agent/`. Ghi chú layout FAST ở [docs/architecture/project-structure.md](docs/architecture/project-structure.md).
- Bảy ghi chú nghiên cứu trong [docs/research/](docs/research/README.md) (AgentCore, Strands/AG-UI, Bedrock, hạ tầng, ML, generative UI, frontend fintech). Chỉ đọc tài liệu, chưa chạy thử gì. Các điểm lệch proposal và quyết định còn chờ: [open-questions.md](docs/requirements/open-questions.md#rút-ra-từ-nghiên-cứu-2026-11-21).
- **Bảy spike đã chạy thật** (bảng ở [docs/research/README.md](docs/research/README.md), code ở `spikes/`): model Bedrock, Strands + AG-UI local, Runtime + CORS, Gateway + Cedar + danh tính, Aurora Data API, ML, stack frontend. Kết quả chính: trình duyệt gọi thẳng Runtime qua SSE được; deploy bằng zip không cần Docker; danh tính xuống tool bằng interceptor + Cedar; token xác nhận do server cấp chạy đúng; Data API đủ nhanh; Sonnet 4.6 / Haiku 4.5 / Nova / Kimi K3 gọi được ngay (Claude 5.x bị chặn); Chronos-2 đề xuất để ngoài MVP (chưa chốt). Tài nguyên AWS của spike đã xóa và đã kiểm lại trên tài khoản.
- Stack frontend đã chốt ([ADR-0001](docs/decisions/0001-frontend-stack.md)).
- Chủ dự án muốn UI là app kiểu ngân hàng trên điện thoại: chuyển tiền, biểu đồ, hũ, chatbot có đầu ra JSON để render (ghi ở [frontend/README.md](frontend/README.md)).
- Chưa là git repo (chưa chạy `git init`).

## Việc kế tiếp (tuần 1, theo proposal §15)

0. **Chờ chủ dự án**: xin tăng quota Bedrock cho Sonnet 5.5 và Haiku 5.5 (đang bằng 0); cơ chế xác nhận trước khi ghi. (Chủ dự án không xin tăng quota được: đang tìm model thay thế. Stack frontend đã chốt, [ADR-0001](docs/decisions/0001-frontend-stack.md).)
1. Chốt **Region triển khai** và đổi danh tính deploy khỏi root (xem "Quyết định còn treo"); kiểm tính năng AgentCore/Bedrock theo Region (ghi vào `docs/research/`).
2. Dựng nền hạ tầng bằng CDK trong `infra-cdk/` (Cognito, AgentCore Runtime, Gateway, Memory, Aurora): đọc tài liệu chính thức trước, xem FAST như một ví dụ khi cần. Triển khai thử nền.
3. Schema Aurora PostgreSQL (`db/schema/`) theo mô hình dữ liệu ở [overview.md](docs/architecture/overview.md#mô-hình-dữ-liệu).
4. Bộ sinh dữ liệu 3 persona (`data/personas/`), kèm persona Minh cho demo.
5. Tool `ledger.*` (`gateway/tools/ledger/`), router và đường nhanh trong agent (`agent/`).
6. Màn hình khai báo và màn hình hũ (`frontend/`).

## Quyết định còn treo

Danh sách đầy đủ và tick khi chốt: [docs/requirements/open-questions.md](docs/requirements/open-questions.md). Nổi bật:

- Hạn nộp chính xác và trọng số chấm; đội 2 hay 3 người (quyết định cắt F6 hay không).
- Chronos-2 có vào MVP không (hay thống kê trước); tool Python toàn bộ hay tách sổ cái sang Java Spring.
- Demo dùng Ví Trả Sau thật hay sản phẩm mô phỏng; persona chính; giữ tên Yofina.

## Môi trường (kiểm ngày 2026-11-21, có thể đã đổi — tự kiểm lại mỗi phiên)

- Windows 11, thư mục `c:\moMo`, chưa phải git repo. Shell chính PowerShell, có Git Bash.
- **AWS CLI** đã đăng nhập (`aws login`); `aws sts get-caller-identity` chạy được. Danh tính là **root user** của tài khoản; region mặc định `~/.aws/config` là `us-east-1`. Không ghi account ID vào tài liệu.
- **AWS MCP (connector claude.ai)** đã đăng nhập lại và dùng được (STS GetCallerIdentity thành công, 2026-11-21), trỏ cùng tài khoản với CLI (cũng root). Khi gọi AWS API ưu tiên connector này (`run_script`) hơn AWS CLI qua Bash. Đăng nhập CLI và connector là hai việc riêng; connector có thể hết phiên lại.
- **aws-docs MCP** và **agentcore MCP**: có trong phiên, dùng được để tra tài liệu.
- Server `aws-serverless`, `terraform`, và `aws-mcp` của plugin aws-core: có cấu hình nhưng không kết nối được trong phiên kiểm tra.
- Skill `aws-core:*` có sẵn (xem [docs/references/aws-tooling.md](docs/references/aws-tooling.md)).
- Chưa có project sản phẩm nào được cài (không CDK). Trong `spikes/` còn venv và `node_modules` của bản thử (khoảng 1,5 GB ở `spikes/ml-forecasting/`); ổ C còn khoảng 12 GB trống — xóa các venv đó khi cần chỗ.
- Docker Desktop không chạy trên máy; deploy Runtime bằng zip không cần Docker.
- Tài khoản AWS có sẵn tài nguyên không thuộc phiên này ở `ap-southeast-1`: một cluster Aurora và một Cognito pool có từ trước (đang chạy, không đụng tới; chủ dự án cần xác nhận còn dùng không).

## Lưu ý

- **Đang dùng root user**: nên tạo IAM user/role riêng (quyền tối thiểu cho CDK) cho việc deploy; tránh tạo/sửa tài nguyên bằng root.
- **Region**: mặc định CLI là `us-east-1`, proposal nhắc Singapore (`ap-southeast-1`). Chốt Region trước khi deploy, đặt Region tường minh khi gọi.
- Tạo/sửa/xóa tài nguyên AWS thật: hỏi chủ dự án trước.
- Link PDF trong [links.md](docs/references/links.md) được trích từ link nhúng trong PDF; ánh xạ link ↔ dòng bảng số liệu §2 suy theo thứ tự, nên đối chiếu nếu cần trích chính xác.
- Proposal ghi rõ Program-of-Thoughts, Croston/TSB không có link nguồn; cần tìm khi dùng.
