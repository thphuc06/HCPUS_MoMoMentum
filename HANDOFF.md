# HANDOFF — ảnh chụp trạng thái hiện tại

> **Quy ước**: cập nhật (ghi đè phần trạng thái bên dưới) vào **cuối mỗi phiên làm việc**. HANDOFF là ảnh chụp hiện tại; lịch sử thay đổi nằm ở [docs/ai-log/](docs/ai-log/README.md). Đầu phiên mới: đọc file này trước.

Cập nhật lần cuối: 2026-11-21, sau khi viết kế hoạch 6 phase. **Kế hoạch đang chờ chủ dự án duyệt; chưa bắt đầu code.**

## Đang ở đâu trong kế hoạch

Giai đoạn chuẩn bị đã xong (tài liệu, bảy spike, Figma). Kế hoạch thực hiện: [docs/plan/master-plan.md](docs/plan/master-plan.md), sáu phase, mỗi phase một file trong [docs/plan/phases/](docs/plan/phases/). Chưa có dòng code sản phẩm nào, chưa có tài nguyên AWS nào của dự án ([docs/aws-resources.md](docs/aws-resources.md)). Hạn nộp giả định trước 11/12/2026.

| Phase | Trạng thái |
|---|---|
| [1. Nền và lát dọc](docs/plan/phases/phase-1-nen-va-lat-doc.md) (21–24/11) | Chưa bắt đầu; chờ duyệt kế hoạch và chờ chủ dự án đăng nhập lại AWS |
| [2. Ví mô phỏng và dự báo](docs/plan/phases/phase-2-vi-va-du-bao.md) (25–28/11) | Chưa bắt đầu |
| [3. What-if, kiểm tra trước khi quẹt, harness](docs/plan/phases/phase-3-what-if-va-kiem-tra.md) (29/11–2/12) | Chưa bắt đầu |
| [4. Chống chịu, lộ trình, phân hũ tự động](docs/plan/phases/phase-4-chong-chiu-lo-trinh.md) (3–5/12) | Chưa bắt đầu |
| [5. Nạp dữ liệu, hồ sơ hành vi, bộ nhớ, trace](docs/plan/phases/phase-5-nap-du-lieu-ho-so-trace.md) (6–8/12) | Chưa bắt đầu |
| [6. Đánh giá, cứng hóa, đóng gói](docs/plan/phases/phase-6-danh-gia-dong-goi.md) (9–10/12) | Chưa bắt đầu |

## Cách làm việc từ đây

Người điều phối (Claude Fable 5.2) giao subagent (Sonnet 5.5, effort high) code từng phase, việc độc lập chạy song song; sau mỗi phase người điều phối tự kiểm trên môi trường đã deploy rồi mới sang phase sau. Đóng phase: điền "Kết quả thực hiện" trong file phase, ai-log, ghi đè file này, tick open-questions, cập nhật aws-resources, commit (không kèm Co-Authored-By) và push. Chi tiết: [master-plan.md mục 3](docs/plan/master-plan.md#3-cách-chia-việc-trong-một-phase).

## Việc kế tiếp

1. **Chủ dự án duyệt kế hoạch** (một lần). Ba lựa chọn của người điều phối cần chủ dự án để ý khi duyệt, đều ở [master-plan.md mục 2](docs/plan/master-plan.md#2-quyết-định-áp-dụng-cho-mọi-phase): đồng hồ mô phỏng theo tài khoản (ngày mô phỏng 21/11/2026 khi đặt lại); không dùng Docker nên không deploy StatsForecast; đường ghi đi thẳng REST bằng token, LLM không nằm trên đường ghi.
2. **Chủ dự án đăng nhập lại AWS**: `aws login` và connector AWS MCP (cả hai đã hết phiên).
3. Chủ dự án cho biết số tiền ngân sách tháng và email nhận cảnh báo (mặc định đề xuất 100 USD).
4. Bắt đầu phase 1: bước 0 (hợp đồng) rồi luồng A (danh tính deploy `yofina-deployer`, có ba bước chủ dự án tự làm trong console).

## Quyết định đã chốt (2026-11-21, chủ dự án)

Region `ap-southeast-1`; không kéo FAST; frontend theo [ADR-0001](docs/decisions/0001-frontend-stack.md) và Figma; Cognito tắt tự đăng ký, tài khoản demo có nút đặt lại; bộ model (Sonnet 4.6, Nova hoặc Haiku 4.5, Kimi K3, Cohere), không tăng quota được; xác nhận bằng token dùng một lần do server cấp, Cedar là lớp phụ; Chronos-2 và SageMaker để ngoài; bỏ Bedrock Data Automation và Automated Reasoning; tool Python toàn bộ; sản phẩm trả sau mô phỏng; "Điểm chống chịu". Đã tick trong [open-questions.md](docs/requirements/open-questions.md).

Quyền với AWS: được tạo và sửa tài nguyên `yofina-*` (tag `project=yofina`, ghi vào aws-resources.md) ở `ap-southeast-1` không cần hỏi từng lần; hỏi trước với thứ tính tiền theo giờ đáng kể ngoài Aurora 0,5 ACU và trước khi xóa thứ không do dự án tạo; không đụng `jars-dev*`.

## Quyết định còn treo

- Hạn nộp chính xác và trọng số chấm; đội 2 hay 3 người; persona chính; giữ tên Yofina; kiểm lại app MoMo ([open-questions.md](docs/requirements/open-questions.md)).
- Có bật CloudWatch Transaction Search không (hỏi ở phase 5).

## Môi trường (kiểm ngày 2026-11-21, có thể đã đổi — tự kiểm lại mỗi phiên)

- Windows 11, thư mục `c:\moMo`, git repo nhánh `main`, remote `origin` trên GitHub (public). PowerShell và Git Bash. Python 3.13, uv, Node 24.
- **AWS CLI: phiên đã hết hạn** (`aws sts get-caller-identity` báo cần `aws login`). Danh tính trước đó là root; region mặc định `us-east-1`. Không ghi account ID vào tài liệu.
- **AWS MCP (connector claude.ai): kết nối đã bị vô hiệu**, cần kết nối lại trong cài đặt connector.
- **aws-docs MCP** và **agentcore MCP**: có trong phiên. `aws-serverless`, `terraform`, `aws-mcp` của plugin aws-core: không kết nối được.
- Figma MCP có trong phiên (file thiết kế `l9vWyORNRjDqiEOXqpbzYm`).
- Docker Desktop không chạy: kế hoạch không dùng Docker ở đâu cả.
- Ổ C còn khoảng 12 GB; `.venv` và `node_modules` trong `spikes/` xóa được khi cần chỗ (phase 1 sẽ xóa).
- Tài khoản AWS có sẵn cluster Aurora và Cognito pool `jars-dev*` ở `ap-southeast-1`: không đụng.

## Lưu ý

- Repo public: không commit account ID, ARN có account ID, secret, token, mật khẩu demo, email.
- Mọi lời gọi model đi qua một module có giới hạn tốc độ và trần mỗi ngày (làm ở phase 1); Claude 4.x chỉ 10 request/phút mỗi model.
- Link PDF trong [links.md](docs/references/links.md) trích từ link nhúng trong PDF; đối chiếu nếu cần trích chính xác.
