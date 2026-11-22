# HANDOFF — ảnh chụp trạng thái hiện tại

> **Quy ước**: cập nhật (ghi đè phần trạng thái bên dưới) vào **cuối mỗi phiên làm việc**. HANDOFF là ảnh chụp hiện tại; lịch sử thay đổi nằm ở [docs/ai-log/](docs/ai-log/README.md). Đầu phiên mới: đọc file này trước.

Cập nhật lần cuối: 2026-11-22 (tối), phase 3 xong bước 0 (hợp đồng).

## Đang ở đâu trong kế hoạch

Kế hoạch: [docs/plan/master-plan.md](docs/plan/master-plan.md), sáu phase trong [docs/plan/phases/](docs/plan/phases/). Hạn nộp giả định trước 11/12/2026.

| Phase | Trạng thái |
|---|---|
| [1. Nền và lát dọc](docs/plan/phases/phase-1-nen-va-lat-doc.md) | **Xong 22/11**, trừ hai việc chờ chủ dự án (mục C). Kết quả ở cuối file phase |
| [2. Ví mô phỏng và dự báo](docs/plan/phases/phase-2-vi-va-du-bao.md) | **Xong 22/11**: 8 tiêu chí đạt, tiêu chí 5 lệch câu chữ (độ phủ luôn 100% trên ví khép kín), tiêu chí 6 đạt có điều kiện. Kết quả, bằng chứng và việc chuyển sang phase sau ở cuối file phase |
| [3. What-if, kiểm tra trước khi quẹt, harness](docs/plan/phases/phase-3-what-if-va-kiem-tra.md) | **Đang làm**: bước 0 xong và đã commit, migration `0010` đã chạy trên Aurora. Ngày 22/11 (chiều): mã ba luồng đã viết trong working tree, **chưa commit**, chưa deploy. A (engine): `scenario.py`, `afford.py`, `credit.py`, `planner` (rules/engine/facts), `knowledge/fees.py`, `audit/trace.py`, `repo_phase3.py`. B (harness): `clarify`, `guardrail`, `verifier`, `whatif`, `trace` trong `agent/`, `infra-cdk/lib/guardrail.ts`. C (frontend): `phase3Views`, `UndoBar`, `features/affordability`, `features/explain`, `TransferCheckPage`, `SuggestionChips`. Test Python đơn vị liên quan: 353 xanh. Chưa kiểm: test frontend, `evals/`, tích hợp AWS, tiêu chí hoàn thành |
| [4. Chống chịu, lộ trình, phân hũ tự động](docs/plan/phases/phase-4-chong-chiu-lo-trinh.md) | Chưa bắt đầu |
| [5. Nạp dữ liệu, hồ sơ hành vi, bộ nhớ, trace](docs/plan/phases/phase-5-nap-du-lieu-ho-so-trace.md) | Chưa bắt đầu |
| [6. Đánh giá, cứng hóa, đóng gói](docs/plan/phases/phase-6-danh-gia-dong-goi.md) | Chưa bắt đầu |

## Đang chạy trên AWS (`ap-southeast-1`)

Sáu stack (phase 2 thêm vào `YofinaTools` và `YofinaAgent`: Lambda `yofina-forecast-batch`, `yofina-on-transaction`, `yofina-forecast`, SQS `yofina-forecast-events`, Step Functions `yofina-nightly` chạy 02:00, target Gateway `forecast`; migration tới 0009): `YofinaFoundation`, `YofinaData`, `YofinaIdentity`, `YofinaTools`, `YofinaAgent`, `YofinaFrontend`. Danh sách đầy đủ: [docs/aws-resources.md](docs/aws-resources.md). App: `https://main.dcrwn4u7vqklo.amplifyapp.com`. Sáu tài khoản demo (`minh`, `lan`, `khoa`, `giamkhao1`–`3`), mật khẩu trong secret `yofina-demo-accounts`. Aurora `yofina-db` từ 22/11 để min 0 ACU, tự ngủ sau 10 phút rảnh (gần như không tốn tiền compute lúc ngủ; lần gọi đầu sau khi ngủ chậm khoảng 15–20 giây). **Trước buổi demo/chấm điểm** đưa về 0,5 ACU: `uv run scripts/cdk.py deploy YofinaData --require-approval never -c dbMinAcu=0.5`.

Lệnh hay dùng (chi tiết ở `scripts/README.md`, `infra-cdk/README.md`, `agent/README.md`): `uv run pytest`; `uv run pytest tests/integration -m integration` (126 test, gọi môi trường thật, khoảng 10 phút); `uv run scripts/cdk.py deploy <Stack> --require-approval never`; `uv run scripts/agent_deploy.py`; `uv run scripts/migrate.py`; `uv run scripts/seed_demo.py`; `uv run scripts/print_env.py frontend --write` rồi `npm run build` trong `frontend/` và `uv run scripts/deploy_frontend.py frontend/dist`.

## Cách làm việc

Người điều phối giao subagent (Sonnet 5.5, effort high) code từng phase, tự kiểm trên môi trường thật rồi mới sang phase sau. **Không hardcode, không giả lập** ([master-plan mục 2](docs/plan/master-plan.md#2-quyết-định-áp-dụng-cho-mọi-phase)). Chỉ một luồng deploy tại một thời điểm. Đóng phase: điền "Kết quả thực hiện", ai-log, ghi đè file này, tick open-questions, cập nhật aws-resources, commit (không Co-Authored-By) và push.

## Việc kế tiếp

### A. Phase 3, các luồng A, B, C: ĐANG DỞ (ba luồng bị dừng giữa chừng 22/11 tối)

Bước 0 xong và đã commit (`e28b9e3`); migration `0010_what_if_audit` đã chạy trên Aurora. Hợp đồng ở `contracts/` (mục "Phase 3" của [contracts/README.md](contracts/README.md)); quyết định, "Cho ba luồng sau" và "Người điều phối chốt" ở cuối [file phase 3](docs/plan/phases/phase-3-what-if-va-kiem-tra.md).

**Trạng thái cây làm việc**: ba subagent (A backend, B agent, C frontend) đã viết khoảng 120 file **chưa commit, chưa kiểm** (frontend/src ~50, agent/src ~17, tests/unit ~15, gateway/tools ~13, pipelines/forecast ~10, gateway/policies ~6, infra-cdk/lib ~4 gồm `guardrail.ts` mới, `evals/`). Cả ba bị dừng khi đang làm, chưa có báo cáo cuối. **Chưa deploy gì**: `YofinaTools` và `YofinaAgent` vẫn là bản phase 2 (kiểm 22/11: `UPDATE_COMPLETE`). Không deploy `YofinaAgent` trước khi Lambda `forecast` cài xong `run_scenario` và `affordability_check` (`contracts/tools/forecast.json` đã liệt kê hai tool này).

**Việc tiếp**: (1) `git status`, chạy `uv run pytest`, `npm run typecheck`/`lint`/test từng file trong `frontend/` để xem phần dở đang ở đâu; (2) hoặc giao lại ba luồng (mỗi luồng đọc phần đã có rồi làm nốt), một luồng deploy tại một thời điểm; (3) sau đó bước ghép: nối `guardrail.ts` vào stack, deploy `YofinaTools` rồi `YofinaAgent`, `scripts/agent_deploy.py`, deploy Amplify, chạy `evals/run.py`, đi cảnh 2 trên trình duyệt; (4) đóng phase.

Việc phase 2 chuyển sang (đã nằm trong hợp đồng phase 3: `OFFER_EXPIRED`, 404 `FORECAST_NOT_APPLICABLE`) cùng lỗi nhỏ còn lại: preview cho sửa hồ sơ, `save_jars`, nghĩa vụ; câu riêng cho hũ 0 ₫; "gần như chắc chắn" thay "100%"; nhãn bước công cụ của lời gọi dự báo; nhãn mốc biểu đồ chồng nhau; tên cho trình đọc màn hình.

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
