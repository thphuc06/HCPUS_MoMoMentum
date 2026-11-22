# HANDOFF — ảnh chụp trạng thái hiện tại

> **Quy ước**: cập nhật (ghi đè phần trạng thái bên dưới) vào **cuối mỗi phiên làm việc**. HANDOFF là ảnh chụp hiện tại; lịch sử thay đổi nằm ở [docs/ai-log/](docs/ai-log/README.md). Đầu phiên mới: đọc file này trước.

Cập nhật lần cuối: 2026-11-22 (đêm). Phase 3 dừng giữa chừng: bước 0 xong trên `main`, ba luồng A/B/C dở dang ở nhánh `wip/phase3-streams`.

## Đang ở đâu trong kế hoạch

Kế hoạch: [docs/plan/master-plan.md](docs/plan/master-plan.md), sáu phase trong [docs/plan/phases/](docs/plan/phases/). Hạn nộp giả định trước 11/12/2026.

| Phase | Trạng thái |
|---|---|
| [1. Nền và lát dọc](docs/plan/phases/phase-1-nen-va-lat-doc.md) | **Xong 22/11**, trừ hai việc chờ chủ dự án (mục C). Kết quả ở cuối file phase |
| [2. Ví mô phỏng và dự báo](docs/plan/phases/phase-2-vi-va-du-bao.md) | **Xong 22/11**: 8 tiêu chí đạt, tiêu chí 5 lệch câu chữ (độ phủ luôn 100% trên ví khép kín), tiêu chí 6 đạt có điều kiện. Kết quả, bằng chứng và việc chuyển sang phase sau ở cuối file phase |
| [3. What-if, kiểm tra trước khi quẹt, harness](docs/plan/phases/phase-3-what-if-va-kiem-tra.md) | **Đang làm, dừng giữa chừng**: bước 0 (hợp đồng) xong, commit `e28b9e3` trên `main`, migration `0010` đã chạy trên Aurora. Ba luồng A, B, C viết dở ở nhánh `wip/phase3-streams` (`5f8177c`): chưa xong, chưa deploy, chưa kiểm trên AWS. Xem "Việc kế tiếp" mục A |
| [4. Chống chịu, lộ trình, phân hũ tự động](docs/plan/phases/phase-4-chong-chiu-lo-trinh.md) | Chưa bắt đầu |
| [5. Nạp dữ liệu, hồ sơ hành vi, bộ nhớ, trace](docs/plan/phases/phase-5-nap-du-lieu-ho-so-trace.md) | Chưa bắt đầu |
| [6. Đánh giá, cứng hóa, đóng gói](docs/plan/phases/phase-6-danh-gia-dong-goi.md) | Chưa bắt đầu |

## Đang chạy trên AWS (`ap-southeast-1`)

Sáu stack (phase 2 thêm vào `YofinaTools` và `YofinaAgent`: Lambda `yofina-forecast-batch`, `yofina-on-transaction`, `yofina-forecast`, SQS `yofina-forecast-events`, Step Functions `yofina-nightly` chạy 02:00, target Gateway `forecast`; migration tới 0009): `YofinaFoundation`, `YofinaData`, `YofinaIdentity`, `YofinaTools`, `YofinaAgent`, `YofinaFrontend`. Danh sách đầy đủ: [docs/aws-resources.md](docs/aws-resources.md). App: `https://main.dcrwn4u7vqklo.amplifyapp.com`. Sáu tài khoản demo (`minh`, `lan`, `khoa`, `giamkhao1`–`3`), mật khẩu trong secret `yofina-demo-accounts`. Aurora `yofina-db` từ 22/11 để min 0 ACU, tự ngủ sau 10 phút rảnh (gần như không tốn tiền compute lúc ngủ; lần gọi đầu sau khi ngủ chậm khoảng 15–20 giây). **Trước buổi demo/chấm điểm** đưa về 0,5 ACU: `uv run scripts/cdk.py deploy YofinaData --require-approval never -c dbMinAcu=0.5`.

Lệnh hay dùng (chi tiết ở `scripts/README.md`, `infra-cdk/README.md`, `agent/README.md`): `uv run pytest`; `uv run pytest tests/integration -m integration` (126 test, gọi môi trường thật, khoảng 10 phút); `uv run scripts/cdk.py deploy <Stack> --require-approval never`; `uv run scripts/agent_deploy.py`; `uv run scripts/migrate.py`; `uv run scripts/seed_demo.py`; `uv run scripts/print_env.py frontend --write` rồi `npm run build` trong `frontend/` và `uv run scripts/deploy_frontend.py frontend/dist`.

## Cách làm việc

Người điều phối giao subagent (Sonnet 5.5, effort high) code từng phase, tự kiểm trên môi trường thật rồi mới sang phase sau. **Không hardcode, không giả lập** ([master-plan mục 2](docs/plan/master-plan.md#2-quyết-định-áp-dụng-cho-mọi-phase)). Chỉ một luồng deploy tại một thời điểm. Đóng phase: điền "Kết quả thực hiện", ai-log, ghi đè file này, tick open-questions, cập nhật aws-resources, commit (không Co-Authored-By) và push.

## Việc kế tiếp

### A. Phase 3: làm nốt ba luồng, ghép, kiểm, đóng phase (việc của người nhận bàn giao)

#### A.1 Đã xong và nằm trên `main`

- Bước 0 (hợp đồng), commit `e28b9e3`: `contracts/scenario/`, sáu khối mới, tool `knowledge`/`planner`/`audit` và hai tool mới của `forecast`, REST `POST /affordability`, `GET /traces/{trace_id}`, `POST /feedback`, `schedule_nudge` qua `/confirmations` + `/actions`, sáu mã lỗi mới, migration `0010_what_if_audit`, `agent/src/yofina_agent/schemas.py`, `gateway/tools/planner/rules/*.yaml`. Quyết định ở cuối [file phase 3](docs/plan/phases/phase-3-what-if-va-kiem-tra.md): "Quyết định hợp đồng phase 3", "Cho ba luồng sau", "Người điều phối chốt" (số tiêu chí 1 và 3 theo engine: tổng hạn 05/12 của `minh` là 2.200.000 ₫ và 1.250.000 ₫; `audit`/`planner`/`knowledge` chạy chung Lambda `yofina-ledger`; không tạo AgentCore Memory, frontend vẫn gửi lại toàn bộ `messages`).
- Migration `0010` đã chạy trên Aurora (`scenarios`, `nudges`, `feedback` đọc được bằng role `yofina_app`).

#### A.2 Dở dang ở nhánh `wip/phase3-streams` (commit `5f8177c`, đã push)

Ba subagent Sonnet bị dừng giữa chừng (giới hạn API, rồi chủ dự án dừng), không có báo cáo cuối. Nhánh chứa toàn bộ phần đã viết, **chưa ai duyệt**.

Trạng thái đo lúc dừng (22/11 đêm, trên cây có phần dở):

- `uv run pytest`: **1636 passed, 1 failed**. Ca đỏ `tests/unit/test_contracts_zod.py::test_zod_qua_cac_fixture_dung_chung`: `tests/unit/ts/blocks.fixtures.test.mjs` còn kỳ vọng danh sách khối đăng ký cũ (8 khối), trong khi luồng C đã thêm sáu khối mới vào `REGISTERED_BY_FRONTEND` (14 khối). Sửa danh sách kỳ vọng.
- Frontend: `npm run typecheck`, `npm run lint` sạch. Test cả bộ 482 passed, 4 failed vì chờ quá giờ; chạy riêng ba file đỏ (`phase3Chat.test.tsx` 12, `walletBlocks.test.tsx` 13, `ForecastBlock.test.tsx` 14) đều xanh. Chưa chạy `npm run build`, `check:bundle`.
- `infra-cdk`: `npx tsc --noEmit` sạch. **Chưa `cdk diff`, chưa deploy.**
- AWS: **chưa deploy gì của phase 3**. `YofinaTools`, `YofinaAgent` vẫn là bản phase 2 (`UPDATE_COMPLETE`); Runtime chạy mã phase 2.

| Luồng | Đã có trên nhánh | Còn thiếu hoặc chưa kiểm |
|---|---|---|
| **A — Engine** (backend) | `pipelines/forecast/yofina_forecast/{scenario,afford,credit,common}.py` (run_scenario, affordability_check), `handler_tool.py`; `gateway/tools/{planner/yofina_planner,knowledge/yofina_knowledge,audit/yofina_audit}/`; ledger `phase3.py`, `repo_phase3.py` và sửa `gateway_api`, `rest_api`, `service`, `wallet_reads`, `wallet_writes` (OFFER_EXPIRED, 404 hũ hệ thống, reset xóa bảng mới); `yofina_core/params.py` (schedule_nudge); 6 file Cedar mới; `infra-cdk` (`tools-stack.ts` route `/affordability`, `/traces`, `/feedback`; `agent-stack.ts` vòng `extraTargets` cho `planner`/`knowledge`/`audit` trỏ ledger; lệnh build zip ledger kèm `--extra` ba gói mới); unit test `tests/unit/pipeline/test_{scenario,afford}.py`, `test_ledger_phase3.py`, `test_planner_engine.py` | Lúc dừng đang sửa `agent-stack.ts` (vòng target): soát lại. **Chưa có integration test phase 3** trong `tests/integration/` (tiêu chí 3, 4 phần backend, 9 affordability p95, sáu loại kịch bản qua Gateway). Chưa sửa test tích hợp cũ đang khóa 503 cho hũ hệ thống (`test_forecast_pipeline.py`, `test_wallet_rest.py`) và `test_gateway_config.py` (forecast nay 3 tool). Chưa cập nhật `docs/aws-resources.md`. Chưa build zip, chưa deploy |
| **B — Harness** (agent) | `agent/src/yofina_agent/{guardrail,clarify,verifier,whatif,trace}.py` mới; `turn.py` nối L0 che PII, router `IntentResult` (Guardrail song song), clarify, what_if (L2, run_scenario, Analyst, Verifier, Composer), affordability (F3), ngoài phạm vi; `yofina_core/pii.py`; `infra-cdk/lib/guardrail.ts` (**chưa nối vào stack nào**); `evals/golden/phase3.jsonl` (25 dòng), `evals/adversarial/phase3.jsonl` (16 dòng), `evals/run.py`; unit test `tests/unit/agent/test_{whatif,verifier,pii,evals}.py` | Lúc dừng đang soạn bộ đánh giá: soát đủ yêu cầu (≥ 20 golden phủ 6 loại kịch bản FR5 kèm quỹ đạo tool, ≥ 15 đối kháng). Chưa chạy agent với model thật, chưa chạy evals trên Runtime. Kiểm đường ping làm nóng phiên đã có chưa. Chưa đặt cấu hình Guardrail (SSM/env) và quyền IAM `bedrock:ApplyGuardrail` cho Runtime |
| **C — Frontend** | sáu view mới (`blocks/phase3Views.tsx`), `AffordCard`, `ObligationImpactBody`, `ExplainPanel`/`ExplainBody` (GET /traces), `SuggestionChips`, `UndoBar`/`useUndo` (Hoàn tác đếm ngược), `TransferCheckPage` (T3a–c, POST /affordability), sửa chat (`ChatSheet`, `MessageList`, `session`, `actions`, `errors` có OFFER_EXPIRED), `ForecastBlock`/`ForecastChart` (`compare`), `REGISTERED_BY_FRONTEND` 14 khối; test `phase3Blocks.test.tsx`, `phase3Chat.test.tsx` | Lúc dừng sắp chạy bộ kiểm cuối: chạy `build`, `check:bundle`. Chưa nối ping làm nóng với B. Chưa chạy trên backend thật. Chưa so với Figma (Figma MCP cần đăng nhập) |

#### A.3 Thứ tự làm tiếp

1. Lấy nhánh WIP về: `git merge --no-ff wip/phase3-streams` lên `main` (hoặc làm trên nhánh rồi merge), chạy lại các kiểm ở A.2, sửa test Zod.
2. Làm nốt từng luồng bằng subagent **Sonnet** (chủ dự án yêu cầu luồng phụ chỉ dùng Sonnet). Mỗi luồng đọc phần đã có trên nhánh trước khi viết thêm, giữ ranh giới thư mục: A sở hữu backend, `infra-cdk` (trừ `guardrail.ts`), `tests/integration/`, `docs/aws-resources.md`; B sở hữu `agent/`, `evals/`, `tests/unit/agent/`, `infra-cdk/lib/guardrail.ts`, `libs/yofina_core/src/yofina_core/pii.py`; C sở hữu `frontend/`. Chỉ một luồng deploy tại một thời điểm.
3. Ghép và deploy theo thứ tự: build zip ledger (kèm `--extra` ba gói) và zip forecast; `cdk diff` rồi `deploy YofinaTools`; nối `guardrail.ts` vào stack, `cdk deploy YofinaAgent` (target, Cedar, Guardrail; lệnh này giữ nguyên mã Runtime); `scripts/agent_deploy.py` (mã agent mới); `print_env.py frontend --write`, `npm run build`, `deploy_frontend.py`. **Không deploy `YofinaAgent` trước khi Lambda forecast có `run_scenario` và `affordability_check`.** Commit sau mỗi luồng đã kiểm, cập nhật HANDOFF ngắn.
4. Kiểm trên môi trường thật: integration test cũ (126) và mới; `evals/run.py` hai bộ (chạy nền, giãn nhịp); đi cảnh 2 trên trình duyệt (bản build ở localhost:5173 nối backend thật, khung 390x844); tự gõ ba câu ngoài bộ golden và đối chiếu từng số với trace; soát 10 tiêu chí của file phase 3 kèm bằng chứng.
5. Đóng phase: "Kết quả thực hiện" trong file phase 3, ai-log, ghi đè HANDOFF (trỏ phase 4), open-questions, aws-resources, commit, push; xóa nhánh `wip/phase3-streams` khi đã merge.

Việc phase 2 chuyển sang, chưa chắc đã làm (ngoài `OFFER_EXPIRED` và 404 hũ hệ thống đã nằm trong luồng A): preview cho sửa hồ sơ, `save_jars`, nghĩa vụ; câu riêng cho hũ 0 ₫ ở tài khoản mới; "gần như chắc chắn" thay "100%"; nhãn bước công cụ của lời gọi dự báo; nhãn mốc biểu đồ chồng nhau; tên cho trình đọc màn hình. Kiểm luồng C đã làm phần nào.

### B. Lưu ý khi kiểm

- Aurora tự ngủ sau 10 phút rảnh (đồng đội đổi 22/11): lần gọi đầu chậm khoảng 17 giây hoặc trả `DATABASE_UNAVAILABLE`, gọi lại là được. Trước khi đo p95 (tiêu chí 9) hoặc demo, đưa về 0,5 ACU: `uv run scripts/cdk.py deploy YofinaData --require-approval never -c dbMinAcu=0.5`, đo xong trả về.
- Có thể có người khác (đồng đội, danh tính root, máy khác) deploy cùng lúc: xem trạng thái stack trước mỗi deploy.

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
