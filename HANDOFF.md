# HANDOFF — ảnh chụp trạng thái hiện tại

> **Quy ước**: cập nhật (ghi đè phần trạng thái bên dưới) vào **cuối mỗi phiên làm việc**. HANDOFF là ảnh chụp hiện tại; lịch sử thay đổi nằm ở [docs/ai-log/](docs/ai-log/README.md). Đầu phiên mới: đọc file này trước.

Cập nhật lần cuối: 2026-11-22 (chiều), dừng giữa chừng ở bước đóng phase 2 để bàn giao.

## Đang ở đâu trong kế hoạch

Kế hoạch: [docs/plan/master-plan.md](docs/plan/master-plan.md), sáu phase trong [docs/plan/phases/](docs/plan/phases/). Hạn nộp giả định trước 11/12/2026.

| Phase | Trạng thái |
|---|---|
| [1. Nền và lát dọc](docs/plan/phases/phase-1-nen-va-lat-doc.md) | **Xong 22/11**, trừ hai việc chờ chủ dự án (xem dưới). Kết quả ở cuối file phase |
| [2. Ví mô phỏng và dự báo](docs/plan/phases/phase-2-vi-va-du-bao.md) | **Code xong, đã deploy, CHƯA đóng**: còn người điều phối tự đi cảnh 1 trên trình duyệt, soát 10 tiêu chí, viết tài liệu đóng phase (xem "Việc kế tiếp") |
| [3. What-if, kiểm tra trước khi quẹt, harness](docs/plan/phases/phase-3-what-if-va-kiem-tra.md) | Chưa bắt đầu |
| [4. Chống chịu, lộ trình, phân hũ tự động](docs/plan/phases/phase-4-chong-chiu-lo-trinh.md) | Chưa bắt đầu |
| [5. Nạp dữ liệu, hồ sơ hành vi, bộ nhớ, trace](docs/plan/phases/phase-5-nap-du-lieu-ho-so-trace.md) | Chưa bắt đầu |
| [6. Đánh giá, cứng hóa, đóng gói](docs/plan/phases/phase-6-danh-gia-dong-goi.md) | Chưa bắt đầu |

## Đang chạy trên AWS (`ap-southeast-1`)

Sáu stack (phase 2 thêm vào `YofinaTools` và `YofinaAgent`: Lambda `yofina-forecast-batch`, `yofina-on-transaction`, `yofina-forecast`, SQS `yofina-forecast-events`, Step Functions `yofina-nightly` chạy 02:00, target Gateway `forecast`; migration tới 0009): `YofinaFoundation`, `YofinaData`, `YofinaIdentity`, `YofinaTools`, `YofinaAgent`, `YofinaFrontend`. Danh sách đầy đủ: [docs/aws-resources.md](docs/aws-resources.md). App: `https://main.dcrwn4u7vqklo.amplifyapp.com`. Sáu tài khoản demo (`minh`, `lan`, `khoa`, `giamkhao1`–`3`), mật khẩu trong secret `yofina-demo-accounts`. Aurora 0,5 ACU chạy liên tục (khoảng 2,4 USD/ngày).

Lệnh hay dùng (chi tiết ở `scripts/README.md`, `infra-cdk/README.md`, `agent/README.md`): `uv run pytest`; `uv run pytest tests/integration -m integration` (126 test, gọi môi trường thật, khoảng 10 phút); `uv run scripts/cdk.py deploy <Stack> --require-approval never`; `uv run scripts/agent_deploy.py`; `uv run scripts/migrate.py`; `uv run scripts/seed_demo.py`; `uv run scripts/print_env.py frontend --write` rồi `npm run build` trong `frontend/` và `uv run scripts/deploy_frontend.py frontend/dist`.

## Cách làm việc

Người điều phối giao subagent (Sonnet 5.5, effort high) code từng phase, tự kiểm trên môi trường thật rồi mới sang phase sau. **Không hardcode, không giả lập** ([master-plan mục 2](docs/plan/master-plan.md#2-quyết-định-áp-dụng-cho-mọi-phase)). Chỉ một luồng deploy tại một thời điểm. Đóng phase: điền "Kết quả thực hiện", ai-log, ghi đè file này, tick open-questions, cập nhật aws-resources, commit (không Co-Authored-By) và push.

## Việc kế tiếp

### A. Đóng phase 2 (việc của người nhận bàn giao)

Trạng thái lúc dừng (22/11): toàn bộ code phase 2 đã commit và push; backend chạy thật; frontend bản mới đã deploy Amplify. Người điều phối đã tự kiểm: 1156 unit test, 126 integration test, 364 test frontend, `check:bundle` sạch; sau `POST /demo/reset`, `minh` có hũ Ăn uống cạn 23/11 (lương 05/12), `khoa` ra "ước lượng ban đầu" (đọc qua API thật). **Chưa** tự kiểm bằng trình duyệt sau khi ghép frontend: mới có báo cáo của subagent ghép (entry đầu [ai-log](docs/ai-log/2026-11.md)), không coi là bằng chứng.

1. Chạy bản build với backend thật trên localhost (`uv run scripts/print_env.py frontend --write`; `npm run build`; `npm --prefix frontend run preview -- --port 5173 --strictPort`), khung di động 390x844, đi cảnh 1 của [demo-script.md](docs/plan/demo-script.md) bằng `minh`, rồi xem `khoa`, `lan`. Chỉ gõ mật khẩu trên localhost.
2. Soát 10 tiêu chí ở [file phase 2](docs/plan/phases/phase-2-vi-va-du-bao.md), ghi bằng chứng từng tiêu chí. Điểm cần để ý:
   - Tiêu chí 7 (onboarding tài khoản trống) chưa ai thử trên API thật vì sáu tài khoản đều có dữ liệu; cần một tài khoản trống (tạo user Cognito `yofina-*` tạm rồi xóa, hoặc cách khác) hoặc ghi rõ là chưa đạt.
   - Tiêu chí 6: mốc nghĩa vụ Trả sau hiện trên `minh` (cộng dồn 1.000.000 → 1.300.000 ₫ hạn 05/12), không hiện trên `lan` vì `lan` không có hũ loại `obligation`. Quyết định: chấp nhận hay sửa.
   - Tiêu chí 5: `khoa` có nhãn "ước lượng ban đầu", nhóm Thấp, nhưng độ phủ dữ liệu luôn 100% (ví khép kín) nên không có "độ phủ thấp". Sửa câu chữ tiêu chí hoặc ghi lệch.
   - Tiêu chí 4 (backtest) xem [backtest-phase-2.md](docs/research/backtest-phase-2.md).
3. Lỗi nhỏ đã biết, chưa sửa: thẻ chủ động của `minh` ghi "còn 14 ngày tới kỳ lương" (tính từ hôm nay) trong khi kịch bản demo và chat ghi 12 ngày (từ ngày cạn tới lương), sửa ở phía server; `OFFER_EXPIRED` chưa tách khỏi `TOKEN_EXPIRED`; preview trả "+1.11%" dấu chấm; `GET /forecasts/{hũ hệ thống}` trả 503 thay vì 404; chưa có preview cho sửa hồ sơ, `save_jars`, nghĩa vụ; tổng ví `minh` 7.900.000 ₫ khác Figma 8.260.000 ₫ (quyết định hợp đồng, giữ).
4. Đóng phase: điền "Kết quả thực hiện" vào file phase 2 (theo mẫu của [phase 1](docs/plan/phases/phase-1-nen-va-lat-doc.md)), thêm entry ai-log, ghi đè file này, tick [open-questions.md](docs/requirements/open-questions.md), soát [aws-resources.md](docs/aws-resources.md), commit (không Co-Authored-By) và push.

### B. Sau đó

[Phase 3](docs/plan/phases/phase-3-what-if-va-kiem-tra.md): bước 0 hợp đồng, rồi các luồng song song.

### C. Chờ chủ dự án

Thử chat trên URL Amplify bằng Chrome máy tính và Safari iPhone (chưa ai kiểm từ trình duyệt thật); bấm link xác nhận trong mail SNS; Cost Explorer ngày 22/11 vẫn chưa hiện chi phí (trễ), xem lại sau.

## Quyết định đã chốt (2026-11-21, chủ dự án)

Region `ap-southeast-1`; không kéo FAST; frontend theo [ADR-0001](docs/decisions/0001-frontend-stack.md) và Figma; Cognito tắt tự đăng ký, tài khoản demo có nút đặt lại; bộ model (Sonnet 4.6, Nova hoặc Haiku 4.5, Kimi K3, Cohere), không tăng quota được; xác nhận bằng token dùng một lần do server cấp, Cedar là lớp phụ; Chronos-2 và SageMaker để ngoài; bỏ Bedrock Data Automation và Automated Reasoning; tool Python toàn bộ; sản phẩm trả sau mô phỏng; "Điểm chống chịu". Đã tick trong [open-questions.md](docs/requirements/open-questions.md).

Quyền với AWS: được tạo và sửa tài nguyên `yofina-*` (tag `project=yofina`, ghi vào aws-resources.md) ở `ap-southeast-1` không cần hỏi từng lần; hỏi trước với thứ tính tiền theo giờ đáng kể ngoài Aurora 0,5 ACU và trước khi xóa thứ không do dự án tạo; không đụng `jars-dev*`.

## Quyết định còn treo

- Hạn nộp chính xác và trọng số chấm; đội 2 hay 3 người; persona chính; giữ tên Yofina; kiểm lại app MoMo ([open-questions.md](docs/requirements/open-questions.md)).
- Có bật CloudWatch Transaction Search không (hỏi ở phase 5).

## Môi trường (kiểm ngày 2026-11-21, có thể đã đổi — tự kiểm lại mỗi phiên)

- Windows 11, thư mục `c:\moMo`, git repo nhánh `main`, remote `origin` trên GitHub (public). PowerShell và Git Bash. Python 3.13, uv, Node 24.
- **AWS CLI**: đăng nhập bằng `aws login`, danh tính **root** (chủ dự án chốt dùng root; `yofina-deployer` có sẵn nhưng chưa dùng); region mặc định `us-east-1`, luôn truyền `--region ap-southeast-1`. Không ghi account ID vào tài liệu.
- **AWS MCP**: `mcp__plugin_aws-core_aws-mcp__aws___run_script` dùng được (22/11); connector claude.ai thì không. AWS CLI/boto3 vẫn là đường chính.
- **aws-docs MCP** và **agentcore MCP**: có trong phiên. `aws-serverless`, `terraform`, `aws-mcp` của plugin aws-core: không kết nối được.
- Figma MCP có trong phiên (file thiết kế `l9vWyORNRjDqiEOXqpbzYm`).
- Docker Desktop không chạy: kế hoạch không dùng Docker ở đâu cả.
- Ổ C: chủ dự án đã dọn, không còn hạn chế cài đặt.
- Tài khoản AWS có sẵn cluster Aurora và Cognito pool `jars-dev*` ở `ap-southeast-1`: không đụng.

## Lưu ý

- Repo public: không commit account ID, ARN có account ID, secret, token, mật khẩu demo, email.
- Mọi lời gọi model đi qua một module có giới hạn tốc độ và trần mỗi ngày (làm ở phase 1); Claude 4.x chỉ 10 request/phút mỗi model.
- Link PDF trong [links.md](docs/references/links.md) trích từ link nhúng trong PDF; đối chiếu nếu cần trích chính xác.
