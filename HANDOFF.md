# HANDOFF — ảnh chụp trạng thái hiện tại

> **Quy ước**: cập nhật (ghi đè phần trạng thái bên dưới) vào **cuối mỗi phiên làm việc**. HANDOFF là ảnh chụp hiện tại; lịch sử thay đổi nằm ở [docs/ai-log/](docs/ai-log/README.md). Đầu phiên mới: đọc file này trước.

Cập nhật lần cuối: 2026-11-22 (chiều), sau khi đóng phase 2.

## Đang ở đâu trong kế hoạch

Kế hoạch: [docs/plan/master-plan.md](docs/plan/master-plan.md), sáu phase trong [docs/plan/phases/](docs/plan/phases/). Hạn nộp giả định trước 11/12/2026.

| Phase | Trạng thái |
|---|---|
| [1. Nền và lát dọc](docs/plan/phases/phase-1-nen-va-lat-doc.md) | **Xong 22/11**, trừ hai việc chờ chủ dự án (mục C). Kết quả ở cuối file phase |
| [2. Ví mô phỏng và dự báo](docs/plan/phases/phase-2-vi-va-du-bao.md) | **Xong 22/11**: 8 tiêu chí đạt, tiêu chí 5 lệch câu chữ (độ phủ luôn 100% trên ví khép kín), tiêu chí 6 đạt có điều kiện. Kết quả, bằng chứng và việc chuyển sang phase sau ở cuối file phase |
| [3. What-if, kiểm tra trước khi quẹt, harness](docs/plan/phases/phase-3-what-if-va-kiem-tra.md) | **Việc kế tiếp**, chưa bắt đầu |
| [4. Chống chịu, lộ trình, phân hũ tự động](docs/plan/phases/phase-4-chong-chiu-lo-trinh.md) | Chưa bắt đầu |
| [5. Nạp dữ liệu, hồ sơ hành vi, bộ nhớ, trace](docs/plan/phases/phase-5-nap-du-lieu-ho-so-trace.md) | Chưa bắt đầu |
| [6. Đánh giá, cứng hóa, đóng gói](docs/plan/phases/phase-6-danh-gia-dong-goi.md) | Chưa bắt đầu |

## Đang chạy trên AWS (`ap-southeast-1`)

Sáu stack (phase 2 thêm vào `YofinaTools` và `YofinaAgent`: Lambda `yofina-forecast-batch`, `yofina-on-transaction`, `yofina-forecast`, SQS `yofina-forecast-events`, Step Functions `yofina-nightly` chạy 02:00, target Gateway `forecast`; migration tới 0009): `YofinaFoundation`, `YofinaData`, `YofinaIdentity`, `YofinaTools`, `YofinaAgent`, `YofinaFrontend`. Danh sách đầy đủ: [docs/aws-resources.md](docs/aws-resources.md). App: `https://main.dcrwn4u7vqklo.amplifyapp.com`. Sáu tài khoản demo (`minh`, `lan`, `khoa`, `giamkhao1`–`3`), mật khẩu trong secret `yofina-demo-accounts`. Aurora 0,5 ACU chạy liên tục (khoảng 2,4 USD/ngày).

Lệnh hay dùng (chi tiết ở `scripts/README.md`, `infra-cdk/README.md`, `agent/README.md`): `uv run pytest`; `uv run pytest tests/integration -m integration` (126 test, gọi môi trường thật, khoảng 10 phút); `uv run scripts/cdk.py deploy <Stack> --require-approval never`; `uv run scripts/agent_deploy.py`; `uv run scripts/migrate.py`; `uv run scripts/seed_demo.py`; `uv run scripts/print_env.py frontend --write` rồi `npm run build` trong `frontend/` và `uv run scripts/deploy_frontend.py frontend/dist`.

## Cách làm việc

Người điều phối giao subagent (Sonnet 5.5, effort high) code từng phase, tự kiểm trên môi trường thật rồi mới sang phase sau. **Không hardcode, không giả lập** ([master-plan mục 2](docs/plan/master-plan.md#2-quyết-định-áp-dụng-cho-mọi-phase)). Chỉ một luồng deploy tại một thời điểm. Đóng phase: điền "Kết quả thực hiện", ai-log, ghi đè file này, tick open-questions, cập nhật aws-resources, commit (không Co-Authored-By) và push.

## Việc kế tiếp

### A. Phase 3, bước 0 — Hợp đồng (việc của người nhận bàn giao)

Đọc [file phase 3](docs/plan/phases/phase-3-what-if-va-kiem-tra.md) (mục "Bước 0 — Hợp đồng") và mục "Kết quả thực hiện" của [phase 1](docs/plan/phases/phase-1-nen-va-lat-doc.md) và [phase 2](docs/plan/phases/phase-2-vi-va-du-bao.md) (đặc biệt "Chuyển sang phase sau"). Bước 0 do một subagent làm trước, rồi mới chia các luồng song song (A engine, B harness, C frontend), một luồng deploy tại một thời điểm.

Việc phase 2 chuyển sang, cân nhắc gộp vào bước 0 hoặc luồng tương ứng: tách `OFFER_EXPIRED` khỏi `TOKEN_EXPIRED`; `GET /forecasts/{hũ hệ thống}` trả 503 thay vì 404 (đổi thì sửa hợp đồng và test cùng lúc); preview cho sửa hồ sơ, `save_jars`, nghĩa vụ; câu riêng cho hũ 0 ₫ ở tài khoản mới (đang hiện "dự kiến cạn"); "Xác suất hụt khoảng 100%" nên ghi "gần như chắc chắn"; nhãn bước công cụ "Đã đọc số dư các hũ" cho lời gọi dự báo; nhãn mốc biểu đồ chồng nhau; nút chat và ô chọn nguồn tiền thiếu tên cho trình đọc màn hình.

### B. Lưu ý khi kiểm

- Chạy cả bộ test frontend song song trên máy này có lúc đỏ vì chờ quá giờ (mã HEAD cũng vậy, đã nâng `testTimeout` lên 15 giây). Nếu đỏ: chạy lại từng file (`npx vitest run <file>`); 21 file đều xanh ngày 22/11.
- Công cụ preview của app gọi `npm` qua nvm thì bị chặn (NVM4306); dùng cấu hình `yofina-frontend-preview-node` trong `.claude/launch.json`, hoặc chạy `node frontend/node_modules/vite/bin/vite.js preview frontend --port 5173 --strictPort`. CORS của API chỉ cho `http://localhost:5173`.
- Ảnh chụp của khung trình duyệt trong app trễ một bước; đọc DOM (`get_page_text`, `javascript_tool`) để lấy bằng chứng.
- `uv run scripts/ml_backtest.py --all` ghi đè `ml/yofina_ml/calibration/default.py` bằng định dạng khác (cùng giá trị): `git restore` file đó nếu không đổi tham số.
- `infra-cdk/` cần `npm ci` và hai zip trong `build/lambda/` (`build_lambda.py`, xem `infra-cdk/README.md`) trước khi `cdk deploy YofinaTools`.

### C. Chờ chủ dự án

Thử chat trên URL Amplify bằng Chrome máy tính và Safari iPhone (chưa ai kiểm từ trình duyệt thật; người điều phối chỉ kiểm bản build ở localhost); bấm link xác nhận trong mail SNS; xem Cost Explorer.

## Quyết định đã chốt (2026-11-21, chủ dự án)

Region `ap-southeast-1`; không kéo FAST; frontend theo [ADR-0001](docs/decisions/0001-frontend-stack.md) và Figma; Cognito tắt tự đăng ký, tài khoản demo có nút đặt lại; bộ model (Sonnet 4.6, Nova hoặc Haiku 4.5, Kimi K3, Cohere), không tăng quota được; xác nhận bằng token dùng một lần do server cấp, Cedar là lớp phụ; Chronos-2 và SageMaker để ngoài; bỏ Bedrock Data Automation và Automated Reasoning; tool Python toàn bộ; sản phẩm trả sau mô phỏng; "Điểm chống chịu". Đã tick trong [open-questions.md](docs/requirements/open-questions.md).

Quyền với AWS: được tạo và sửa tài nguyên `yofina-*` (tag `project=yofina`, ghi vào aws-resources.md) ở `ap-southeast-1` không cần hỏi từng lần; hỏi trước với thứ tính tiền theo giờ đáng kể ngoài Aurora 0,5 ACU và trước khi xóa thứ không do dự án tạo; không đụng `jars-dev*`.

## Quyết định còn treo

- Hạn nộp chính xác và trọng số chấm; đội 2 hay 3 người; persona chính; giữ tên Yofina; kiểm lại app MoMo ([open-questions.md](docs/requirements/open-questions.md)).
- Có bật CloudWatch Transaction Search không (hỏi ở phase 5).

## Môi trường (kiểm ngày 2026-11-22, có thể đã đổi — tự kiểm lại mỗi phiên)

- Windows 11, thư mục `D:\Projects\HCPUS_MoMoMentum`, git repo nhánh `main`, remote `origin` trên GitHub (public). PowerShell và Git Bash. Python 3.13, uv, Node 24.
- **AWS CLI**: ngày 22/11 `aws sts get-caller-identity` ra một **IAM user** (không phải root) của tài khoản có sáu stack `Yofina*`; profile chọn qua biến môi trường `AWS_PROFILE`, region mặc định của profile là `ap-southeast-1`. Vẫn truyền `--region ap-southeast-1` tường minh. Không ghi account ID vào tài liệu.
- **MCP trong phiên 22/11**: `aws-mcp` (`mcp__aws-mcp__aws___run_script` dùng được), `aws-docs`, `agentcore`. Chi tiết cài đặt: [docs/references/aws-tooling.md](docs/references/aws-tooling.md) (chưa cập nhật theo phiên này).
- Docker Desktop không chạy: kế hoạch không dùng Docker ở đâu cả.
- Tài khoản AWS có sẵn tài nguyên `jars-dev*` và stack `Jars*` ở `ap-southeast-1`: không đụng.

## Lưu ý

- Repo public: không commit account ID, ARN có account ID, secret, token, mật khẩu demo, email.
- Mọi lời gọi model đi qua một module có giới hạn tốc độ và trần mỗi ngày (làm ở phase 1); Claude 4.x chỉ 10 request/phút mỗi model.
- Link PDF trong [links.md](docs/references/links.md) trích từ link nhúng trong PDF; đối chiếu nếu cần trích chính xác.
