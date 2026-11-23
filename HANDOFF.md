# HANDOFF — ảnh chụp trạng thái hiện tại

> **Quy ước**: cập nhật (ghi đè phần trạng thái bên dưới) vào **cuối mỗi phiên làm việc**. HANDOFF là ảnh chụp hiện tại; lịch sử thay đổi nằm ở [docs/ai-log/](docs/ai-log/README.md). Đầu phiên mới: đọc file này trước.

Cập nhật lần cuối: 2026-11-23 (chiều). Phase 3 đã đóng (golden 30/30, integration 169/169). `main` đã push. Phase 3 đóng có điều kiện, F1 và F3 đã deploy; sáng 23/11 sửa router (ghép nhầm câu mới với lịch sử chat, sai ô số lương và ô hũ) và Guardrail (thiếu quyền liên vùng nên chưa từng chạy; chặn nhầm câu chuyển tiền), Runtime v9: golden 27/29 (93,1%), đối kháng 16/16. Phase 5 luồng A (F6 nạp dữ liệu từ ảnh và CSV) xong và đã deploy. Trưa 23/11: agent nhớ lượt trước (lịch sử gửi kèm tóm tắt khối), gộp kịch bản cùng hũ trong một cuộc chat (hỏi giữ hay bỏ khoản trước), hỏi xác nhận thay vì từ chối khi router xếp nhầm ngoài phạm vi; migration 0051, tool `forecast___list_scenarios`, Runtime v12, Amplify job 8; integration 163/163.

## Đang ở đâu trong kế hoạch

Kế hoạch: [docs/plan/master-plan.md](docs/plan/master-plan.md), sáu phase trong [docs/plan/phases/](docs/plan/phases/). Hạn nộp giả định trước 11/12/2026.

| Phase | Trạng thái |
|---|---|
| [1. Nền và lát dọc](docs/plan/phases/phase-1-nen-va-lat-doc.md) | **Xong 22/11**, trừ hai việc chờ chủ dự án (mục C). Kết quả ở cuối file phase |
| [2. Ví mô phỏng và dự báo](docs/plan/phases/phase-2-vi-va-du-bao.md) | **Xong 22/11**: 8 tiêu chí đạt, tiêu chí 5 lệch câu chữ (độ phủ luôn 100% trên ví khép kín), tiêu chí 6 đạt có điều kiện. Kết quả, bằng chứng và việc chuyển sang phase sau ở cuối file phase |
| [3. What-if, kiểm tra trước khi quẹt, harness](docs/plan/phases/phase-3-what-if-va-kiem-tra.md) | **Đóng 23/11** (Runtime v13): golden **30/30**, đối kháng 16/16, integration 169/169, ép lỗi model 6/6, đã đo p95. **Kiểm sau**: đi cảnh 2 trên trình duyệt, Figma, Hoàn tác thật trên UI; Guardrail 446 ms vượt ngưỡng 400 ms. Xem mục A |
| [4. Chống chịu, lộ trình, phân hũ tự động](docs/plan/phases/phase-4-chong-chiu-lo-trinh.md) | **Bước 0 (hợp đồng) xong 23/11** trên `main`: migration 0052 (chưa chạy trên Aurora), 5 khối, 5 tool, 13 REST, kiểu dùng chung, cú sốc và trọng số dạng dữ liệu. Chia việc: Phúc luồng A (ML) và B (phân hũ tự động), deploy; Học luồng C (agent) và D (frontend) trên nhánh `feat/phase4-agent-ui`. Xem mục B |
| [5. Nạp dữ liệu, hồ sơ hành vi, bộ nhớ, trace](docs/plan/phases/phase-5-nap-du-lieu-ho-so-trace.md) | **Luồng A (F6) xong và deploy 23/11** (stack `YofinaIngest`, migration 0050, persona `vy` cho `giamkhao3`, test tích hợp 11/11, eval 58 mục). Luồng B–E chưa làm. Kết quả ở cuối file phase |
| [6. Đánh giá, cứng hóa, đóng gói](docs/plan/phases/phase-6-danh-gia-dong-goi.md) | Chưa bắt đầu |

## Đang chạy trên AWS (`ap-southeast-1`)

Bảy stack (phase 2 thêm vào `YofinaTools` và `YofinaAgent`: Lambda `yofina-forecast-batch`, `yofina-on-transaction`, `yofina-forecast`, SQS `yofina-forecast-events`, Step Functions `yofina-nightly` chạy 02:00, target Gateway `forecast`; migration tới 0009): `YofinaFoundation`, `YofinaData`, `YofinaIdentity`, `YofinaTools`, `YofinaAgent`, `YofinaFrontend`, `YofinaIngest`. Danh sách đầy đủ: [docs/aws-resources.md](docs/aws-resources.md). App: `https://main.dcrwn4u7vqklo.amplifyapp.com`. Sáu tài khoản demo (`minh`, `lan`, `khoa`, `giamkhao1`–`3`), mật khẩu trong secret `yofina-demo-accounts`. Aurora `yofina-db` từ 22/11 để min 0 ACU, tự ngủ sau 10 phút rảnh (gần như không tốn tiền compute lúc ngủ; lần gọi đầu sau khi ngủ chậm khoảng 15–20 giây). Phase 3: Guardrail `yofina-guardrail`, target Gateway `planner`/`knowledge`/`audit` (trỏ `yofina-ledger`, có `audit___record_turn`), Runtime `yofina_agent` version 13, Amplify job 9. Guardrail: IAM cho hồ sơ `apac.guardrail.v1:0` ở 6 vùng đích, MISCONDUCT mức LOW (bốn bộ lọc kia và PROMPT_ATTACK mức HIGH), version mới mỗi lần đổi cấu hình. Phase 5 luồng A: stack thứ bảy `YofinaIngest` (bucket `yofina-ingest-*`, SQS `yofina-ingest-jobs` + DLQ, Lambda `yofina-ingest-api` và `yofina-ingest`, 6 route `/ingest/*` trên `yofina-api`), nhóm Cognito `persona-vy` (`giamkhao3`). Migration tới 0050. **Trước buổi demo/chấm điểm** đưa về 0,5 ACU: `uv run scripts/cdk.py deploy YofinaData --require-approval never -c dbMinAcu=0.5`.

Lệnh hay dùng (chi tiết ở `scripts/README.md`, `infra-cdk/README.md`, `agent/README.md`): `uv run pytest`; `uv run pytest tests/integration -m integration` (126 test, gọi môi trường thật, khoảng 10 phút); `uv run scripts/cdk.py deploy <Stack> --require-approval never`; `uv run scripts/agent_deploy.py`; `uv run scripts/migrate.py`; `uv run scripts/seed_demo.py`; `uv run scripts/print_env.py frontend --write` rồi `npm run build` trong `frontend/` và `uv run scripts/deploy_frontend.py frontend/dist`.

## Cách làm việc

Người điều phối giao subagent (Sonnet 5.5, effort high) code từng phase, tự kiểm trên môi trường thật rồi mới sang phase sau. **Không hardcode, không giả lập** ([master-plan mục 2](docs/plan/master-plan.md#2-quyết-định-áp-dụng-cho-mọi-phase)). Chỉ một luồng deploy tại một thời điểm. Đóng phase: điền "Kết quả thực hiện", ai-log, ghi đè file này, tick open-questions, cập nhật aws-resources, commit (không Co-Authored-By) và push.

## Việc kế tiếp

### A. Phase 3: đã đóng 23/11, còn việc kiểm sau

**Đóng 23/11 chiều** (chi tiết: mục "Đóng phase ngày 2026-11-23" trong [file phase 3](docs/plan/phases/phase-3-what-if-va-kiem-tra.md), ai-log 15:00). Ba subagent Sonnet: sửa ca Trả sau (suitability cộng nghĩa vụ kịch bản vào mọi phương án), luật dự phòng khi model hỏng + `tests/integration/test_degraded_live.py`, đo số `scripts/measure_phase3.py`. Runtime v13, Aurora đã trả về min 0 ACU sau khi đo. **Việc kiểm sau**:
1. Đi cảnh 2 trên trình duyệt (cần chủ dự án tự đăng nhập trong khung trình duyệt của app hoặc Chrome có tiện ích Claude): 390x844, Figma, Hoàn tác thật, "Vì sao" trên UI, ba câu ngoài golden đối chiếu trace.
2. `ApplyGuardrail` p50 446 ms > 400 ms: quyết định ở open-questions.
3. Sửa gốc lỗi suitability ở Lambda `phase3.py` (agent đã tránh).
4. Đổi mật khẩu các tài khoản demo trước buổi chấm (đã lộ trong lịch sử chat 23/11).

Phần dưới là lịch sử trước khi đóng.

Mã trên `main` (đã push). **23/11 đã deploy bản merge `82de21d`**: migration tới 0050, `YofinaTools`, `YofinaAgent` (có tool `audit___record_turn` của F1), Runtime `yofina_agent` version 6 (F1 + F3), `YofinaIngest` mới, Amplify job 7. Integration cả bộ 161/161 xanh (gồm `test_record_turn_qua_gateway_roi_get_traces_200_feedback_200_nguoi_khac_404` và `test_ingest_live.py`). Kết quả từng tiêu chí và số đo: mục "Kết quả thực hiện" ở [file phase 3](docs/plan/phases/phase-3-what-if-va-kiem-tra.md) (10 tiêu chí: 5 đạt; 6 đạt có điều kiện; 2 và 8 chưa kiểm; 1, 3, 4, 7, 9, 10 lệch).

Thứ tự làm:

1. ~~**Deploy F1 và F3**~~ (xong 23/11) (một luồng deploy tại một thời điểm; kiểm trạng thái stack trước): build zip ledger bằng lệnh `build_lambda.py` kèm `--extra` ba gói (lệnh đầy đủ ở file phase 3, mục "Thứ tự deploy còn lại"); `cdk deploy YofinaTools`; `cdk deploy YofinaAgent`; `uv run scripts/agent_deploy.py`. Không migration, không deploy lại frontend. **Không deploy `YofinaAgent` trước `YofinaTools`.**
2. **Trưa 23/11 (Runtime v12, ai-log 10:00 và 10:40)**: gộp kịch bản trong cuộc chat (giày rồi dép cùng hũ: hỏi giữ/bỏ, giữ thì `run_scenario` với `with_scenarios`, lưu theo `conversation_id`); lịch sử gửi agent có `fallback_text` của khối; ngoài phạm vi có dấu hiệu chi tiêu thì hỏi xác nhận. Test nhiều lượt thật: `tests/integration/test_whatif_bundle_live.py`. Chưa làm: gộp cho thẻ kiểm tra trước khi chi (`affordability`), gộp hai khoản Trả sau, chưa đi trên trình duyệt.
   **Sáng 23/11 (Runtime v9, chi tiết ở ai-log 07:40)**: chủ dự án thử trên điện thoại, câu "Nếu 10 ngày sau tôi đi du lịch 5 triệu thì sao" ra "Ngoài phạm vi". Nguyên nhân: router ghép nhầm câu mới với chuỗi câu trước; model đặt lương mới vào `salary_vnd`, hũ trả tiền vào `from_jar_text`; Guardrail AccessDenied ở mọi lượt (thiếu quyền hồ sơ liên vùng), sửa xong thì MISCONDUCT chặn nhầm câu "chuyển 250 nghìn cho người nhận demo". Đã sửa cả bốn. Golden thêm 2 ca nhiều lượt (`history`). **Còn đỏ 2/29**: `whatif-bnpl` (Verifier hỏng 2 vòng, thiếu `options`; chưa rõ nguyên nhân) và `whatif-bnpl2` (15 triệu vượt hạn mức Trả sau 4.033.000 ₫: lỗi bộ câu hỏi, nên đổi số tiền). Câu trả lời của Yofina lưu rỗng nên lịch sử router chỉ có chữ người dùng: chưa xử lý.
   Trước đó: ~~Chạy lại integration~~ (xong 23/11, 161/161). Bốn ca golden đỏ chạy lại 23/11 trên Runtime v6: vẫn 0/4 (grounding, schema, suitability 100%; trượt quỹ đạo: `whatif-bnpl` thiếu khối `options`; `whatif-income`, `whatif-onetime2` không gọi `run_scenario`, thiếu `forecast_timeline`; `whatif-bnpl2` thiếu `forecast_timeline`, `obligation_impact`). **Còn**:  (cả bộ, khoảng 12 phút, tuần tự) gồm `test_record_turn_qua_gateway_roi_get_traces_200_feedback_200_nguoi_khac_404` (đã viết, chưa chạy). Rồi chạy lại **bốn ca golden đỏ** (`whatif-bnpl`, `whatif-income`, `whatif-bnpl2`, `whatif-onetime2`; đổi số tiền `whatif-bnpl2` xuống dưới hạn mức 4.033.000 ₫): `uv run python evals/run.py golden --only whatif-bnpl,whatif-income,whatif-bnpl2,whatif-onetime2 --redo --min-interval 25`. Xác định vì sao Verifier hỏng ở `whatif-bnpl`. Mục tiêu: quỹ đạo golden ≥ 85%, BNPL và đổi lương có ca đạt.
3. **Đi cảnh 2 trên trình duyệt** 390x844 (URL Amplify hoặc bản build ở localhost:5173 nối backend thật), so Figma (cần đăng nhập Figma MCP), tự gõ ba câu ngoài bộ golden và đối chiếu số với trace; kiểm "Vì sao" trả 200 sau một lượt thật; thử Hoàn tác (tiêu chí 2).
4. **Đo p95** what-if và độ trễ `ApplyGuardrail` (ngưỡng 400 ms): đưa Aurora lên 0,5 ACU (`uv run scripts/cdk.py deploy YofinaData --require-approval never -c dbMinAcu=0.5`), đo 10 lượt mỗi loại ở phiên ấm, ghi vào file phase 3, rồi **trả về 0** (`-c dbMinAcu=0`). Ép lỗi model trên Runtime (tiêu chí 8).
5. Phát hiện để sau (F4 đến F10) ở file phase 3; quyết định mở F5 (guardrail fail-open) và ngưỡng sát/hụt ở [open-questions.md](docs/requirements/open-questions.md).

Việc phase 2 chuyển sang, chưa chắc đã làm: preview cho sửa hồ sơ, `save_jars`, nghĩa vụ; câu riêng cho hũ 0 ₫ ở tài khoản mới; "gần như chắc chắn" thay "100%"; nhãn bước công cụ của lời gọi dự báo; nhãn mốc biểu đồ chồng nhau; tên cho trình đọc màn hình.

**F6 nạp dữ liệu** (đã merge, đã deploy): `confirm_rows` không qua ledger mà qua `/ingest/confirmations` + `/ingest/actions` của Lambda `yofina-ingest-api`; việc còn lại (tool Gateway `ingest___*`, intent chat, phân loại phase 4, quyết định bật thu nhập ngoài ví cho `minh`) ở [docs/plan/ingest-merge-notes.md](docs/plan/ingest-merge-notes.md) mục "Chưa làm". Demo cảnh 5: đăng nhập `giamkhao3`, Tổng quan → Tiền vào → "Nạp ảnh / sao kê ngoài ví", nạp `data/personas/samples/vy_sao_ke_vcb.csv`.

**Git**: `main` đã push. Nhánh `feat/ingest` đã xóa sau khi merge. `origin/wip/phase3-streams` và `origin/r1-merge-phase3` đã nằm trọn trong `main`, xóa được khi đồng đội đồng ý. `evals/results/` không vào git (chứa dữ liệu persona; đã có trong `.gitignore`).

### B. Phase 4: bước 0 xong, chia hai nhánh

Hợp đồng: mục "Quyết định hợp đồng phase 4" (25 quyết định) và "Cho các luồng sau" trong [file phase 4](docs/plan/phases/phase-4-chong-chiu-lo-trinh.md), `contracts/README.md` mục Phase 4, `db/README.md`. Kiểm lúc chốt: pytest 2352, local_pg 132, vitest 588, infra 19/19, Zod khớp.

- **Phúc (máy mạnh, nhánh `feat/phase4-engine`)**: luồng A (điểm chống chịu, cú sốc Monte Carlo, LP `optimize_allocation`, phát hiện đổi hành vi), luồng B (Lambda phân loại, embedding Cohere `vector(1024)`, k-NN, bộ kiểm ≥ 300 giao dịch), seed persona `minh` lộ trình v1–v3, chạy migration 0052, thêm 13 route REST vào `tools-stack.ts`, mọi deploy và test tích hợp. **Đã chốt 23/11**: target `planner` giữ trên Lambda ledger; `optimize_allocation` gọi `Invoke` sang Lambda forecast để giải LP (mẫu `forecast_client.py`), không thêm scipy vào ledger, không chuyển target (lý do ở file phase 4, luồng A).
- **Học (máy yếu, nhánh `feat/phase4-agent-ui`)**: luồng C (Roadmap agent, router ý định `resilience`/`stress`/`roadmap`, khối trong chat, cổng nhắc), luồng D (R1–R3, L1–L3, A1–A2), viết `evals/golden|adversarial/phase4.jsonl`; code theo `contracts/fixtures/`; chỉ chạy unit test agent và frontend; không deploy. Thêm việc kiểm sau của phase 3 (đi cảnh 2 trên trình duyệt, Học tự đăng nhập).
- Năm tool mới đã có trong hợp đồng và Cedar nên lần deploy `YofinaAgent` kế tiếp sẽ đăng ký chúng; trước khi luồng A cài, Gateway trả "Tool không tồn tại" (`wallet.PHASE4_TOOLS` liệt kê tên chưa cài).

### C. Lưu ý khi kiểm

- Aurora tự ngủ sau 10 phút rảnh (đồng đội đổi 22/11): lần gọi đầu chậm khoảng 17 giây hoặc trả `DATABASE_UNAVAILABLE`, gọi lại là được. Trước khi đo p95 (tiêu chí 9) hoặc demo, đưa về 0,5 ACU: `uv run scripts/cdk.py deploy YofinaData --require-approval never -c dbMinAcu=0.5`, đo xong trả về.
- Có thể có người khác (đồng đội, danh tính root, máy khác) deploy cùng lúc: xem trạng thái stack trước mỗi deploy.

- Chạy cả bộ test frontend song song trên máy này có lúc đỏ vì chờ quá giờ (mã HEAD cũng vậy, đã nâng `testTimeout` lên 15 giây). Nếu đỏ: chạy lại từng file (`npx vitest run <file>`); 21 file đều xanh ngày 22/11.
- Công cụ preview của app gọi `npm` qua nvm thì bị chặn (NVM4306); dùng cấu hình `yofina-frontend-preview-node` trong `.claude/launch.json`, hoặc chạy `node frontend/node_modules/vite/bin/vite.js preview frontend --port 5173 --strictPort`. CORS của API chỉ cho `http://localhost:5173`.
- Ảnh chụp của khung trình duyệt trong app trễ một bước; đọc DOM (`get_page_text`, `javascript_tool`) để lấy bằng chứng.
- `uv run scripts/ml_backtest.py --all` ghi đè `ml/yofina_ml/calibration/default.py` bằng định dạng khác (cùng giá trị): `git restore` file đó nếu không đổi tham số.
- `infra-cdk/` cần `npm ci` và hai zip trong `build/lambda/` (`build_lambda.py`, xem `infra-cdk/README.md`) trước khi `cdk deploy YofinaTools`.

### D. Chờ chủ dự án

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
