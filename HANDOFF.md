# HANDOFF — ảnh chụp trạng thái hiện tại

> **Quy ước**: cập nhật (ghi đè phần trạng thái bên dưới) vào **cuối mỗi phiên làm việc**. HANDOFF là ảnh chụp hiện tại; lịch sử thay đổi nằm ở [docs/ai-log/](docs/ai-log/README.md). Đầu phiên mới: đọc file này trước.

Cập nhật lần cuối: **2026-11-24 trưa** (Claude Code điều phối các worker `kiro-cli`). Phase 4 đã đóng. Phase 5 đã code xong, đã deploy, **chưa đóng**: còn evals phase 5 và đi cảnh trên app.

## Đang ở đâu trong kế hoạch

Kế hoạch: [docs/plan/master-plan.md](docs/plan/master-plan.md), sáu phase trong [docs/plan/phases/](docs/plan/phases/). Hạn nộp giả định trước 11/12/2026.

| Phase | Trạng thái |
|---|---|
| 1. Nền và lát dọc | Xong 22/11 |
| 2. Ví mô phỏng và dự báo | Xong 22/11 |
| [3. What-if, kiểm tra trước khi chi](docs/plan/phases/phase-3-what-if-va-kiem-tra.md) | Đóng 23/11. Đi cảnh 2 trên Amplify ngày 23/11 tối: đạt (Học kiểm mục 8 trên điện thoại) |
| [4. Chống chịu, lộ trình, phân hũ tự động](docs/plan/phases/phase-4-chong-chiu-lo-trinh.md) | **Đóng 24/11**: bảng 9 tiêu chí ở mục "Đóng phase ngày 2026-11-24". Tiêu chí 6 đúng 92% nhưng tỷ lệ phải hỏi 17,4% (mục tiêu < 10%) |
| [5. Nạp dữ liệu, hồ sơ hành vi, bộ nhớ, trace](docs/plan/phases/phase-5-nap-du-lieu-ho-so-trace.md) | **Code xong, đã deploy 24/11, chưa đóng**. RAG (luồng C) đã cắt theo quyết định của chủ dự án. Còn: evals phase 5, đi 6 cảnh, kiểm tay tiêu chí 1, 2, 5, 8, 9 |
| [6. Đánh giá, cứng hóa, đóng gói](docs/plan/phases/phase-6-danh-gia-dong-goi.md) | Chưa bắt đầu |

## Đang chạy trên AWS (`ap-southeast-1`)

- Bảy stack `YofinaFoundation`, `YofinaData`, `YofinaIdentity`, `YofinaTools`, `YofinaAgent`, `YofinaFrontend`, `YofinaIngest`, đều `*_COMPLETE`. Danh sách tài nguyên đầy đủ: [docs/aws-resources.md](docs/aws-resources.md).
- **Runtime `yofina_agent` v21**, **Amplify job 13**, migration tới **0053**. App: `https://main.dcrwn4u7vqklo.amplifyapp.com`.
- Mới của phase 5: AgentCore Memory `yofina_memory` (ba strategy: sở thích, sự thật, tóm tắt phiên; tính phí theo lượt dùng); target Gateway `ingest` (3 tool) và tool `forecast___get_behavior_profile`; 11 route REST mới (`/profile/behavior`, `/nudges/*`, `/memory*`, `/me/delete-data*`, `/ops/*`); dashboard CloudWatch `yofina-ops` và 8 alarm (khoảng 0,90 USD/tháng); tài khoản `minh` thuộc nhóm Cognito `ops` (để mở màn trace).
- Sáu tài khoản demo (`minh`, `lan`, `khoa`, `giamkhao1`–`3`), mật khẩu trong secret `yofina-demo-accounts`. **Mật khẩu đã lộ trong lịch sử chat 23/11: đổi trước buổi chấm.**
- Aurora `yofina-db` để min 0 ACU, tự ngủ sau 10 phút (lần gọi đầu chậm 15–20 giây). **Trước buổi demo** đưa lên 0,5 ACU: `uv run scripts/cdk.py deploy YofinaData --require-approval never -c dbMinAcu=0.5`, demo xong trả về `-c dbMinAcu=0`.

Lệnh hay dùng (chi tiết ở `scripts/README.md`, `infra-cdk/README.md`): `uv run pytest tests/unit libs/yofina_core/tests -q`; `uv run pytest tests/integration -m integration`; `uv run scripts/cdk.py diff|deploy <Stack> --require-approval never`; `uv run scripts/agent_deploy.py` (có thể trả exit 1 dù đã READY, kiểm bằng `aws bedrock-agentcore-control get-agent-runtime`); `uv run scripts/migrate.py`; `uv run scripts/seed_demo.py <persona>`; frontend: `uv run scripts/print_env.py frontend --write`, `npm.cmd run build` trong `frontend/`, `uv run scripts/deploy_frontend.py frontend/dist`. Lệnh build zip từng Lambda: các hằng `*_BUILD_COMMAND` trong `infra-cdk/lib/` (ledger nay kèm `--keep-boto`, boto3 1.44.9).

## Số đo mới nhất

- Unit 3449 passed; local_pg 223; CDK 66/66; vitest 816.
- Integration sau deploy phase 5 (24/11): `test_wallet_rest`, `test_phase4_live`, `test_phase3_engine`, `test_ingest_live`: 82/83. Ca đỏ là test cũ coi bảng `nudges` rỗng sau đặt lại; đã sửa test (chỉ đếm `source <> 'system'`) và chạy lại xanh trên AWS.
- Phase 4 trên Runtime v18: golden 14/14, adversarial 12/12, golden phase 3 31/31. Evals phase 5 **chưa chạy**.
- Lộ trình lập trong chat: sau bản sửa tốc độ (phân bổ trước khi phác thảo) đo cục bộ với Bedrock thật 1 lượt planner, 10–11 giây; **chưa đo trên Runtime v21** (lần đo trên v20: 35–54 giây).
- `minh` sau batch: 3 nhận xét hành vi (Trả sau 2 lần 967.000 ₫ bằng 14% chi tiêu; cuối tuần 37% tổng chi trên 26% số ngày; 7 ngày đầu sau lương 40% tổng chi); bản tin hôm nay "Hũ Ăn uống dự kiến cạn ngày 23/11".

## Việc kế tiếp

### A. Phúc / Claude Code (người điều phối)

1. Chạy evals phase 5 MỘT lần: `uv run scripts/seed_demo.py minh`, `uv run python evals/run.py golden --phase 5 --min-interval 25`, rồi `adversarial --phase 5` (đặt lại `minh` trước mỗi bộ). Đo lại 4 ca lộ trình trên Runtime v21 (`golden --phase 4 --only roadmap-create-emergency-fund,roadmap-regenerate-after-spending-change,roadmap-infeasible-goal,roadmap-edit-one-step --redo`).
2. Đóng phase 5: điền "Kết quả thực hiện" (bảng 10 tiêu chí) trong file phase 5 sau khi có kết quả của Học (mục B).
3. Quyết định: bật CloudWatch Transaction Search không (có phí mức tài khoản; hiện không bật, màn trace đọc từ `audit_events`).
4. Phase 6 (đánh giá, cứng hóa, đóng gói).

### B. Học (cần người thật đăng nhập app hoặc dùng điện thoại)

Đăng nhập trên `https://main.dcrwn4u7vqklo.amplifyapp.com` (mật khẩu trong secret `yofina-demo-accounts`). Mỗi việc ghi kết quả (đạt / lỗi kèm ảnh chụp, giờ) vào mục "Kiểm sau" của file phase tương ứng hoặc gửi Phúc. Bấm "Đặt lại dữ liệu demo" (Hồ sơ) trước mỗi việc dùng `minh`.

1. **Đi trọn 6 cảnh** theo [figma-ui-design.md §8.2](docs/research/figma-ui-design.md) với `giamkhao1` vừa đặt lại (tiêu chí 10 của phase 5), bấm giờ từng cảnh so với [demo-script.md](docs/plan/demo-script.md), đối chiếu frame Figma (R1–R3, L1–L3, A1–A2, S1 Hồ sơ, X1 trace).
2. **Cảnh 4, lộ trình lập trong chat**: hỏi "Lập lại lộ trình giúp mình". Ghi: mất bao nhiêu giây (mục tiêu khoảng 30), mấy giai đoạn và bước, bước có cụ thể (số tiền, hũ nguồn → hũ đích) không, có lời kết không, có báo "thay bản đề xuất phiên bản 3" không, nút sang trang Lộ trình có chạy không. Kiểm thẻ "Lộ trình thích ứng" mới trên tab Nhìn trước.
3. **Cảnh 5, nạp dữ liệu trên điện thoại thật**: chụp/chọn ảnh thông báo chuyển khoản → tiến độ → duyệt dòng → độ phủ tăng → Chi tiết hũ có dự báo mới (tiêu chí 1). Nạp lại cùng ảnh: không ghi trùng. Nạp ảnh không phải tài liệu tài chính: báo lỗi rõ (tiêu chí 2). Hỏi trong chat "mình vừa nạp ảnh": ra trạng thái và bảng duyệt.
4. **Bộ nhớ (tiêu chí 5)**: phiên 1 gõ "Đừng nhắc mình buổi sáng, mình ưu tiên hũ Du lịch". Đợi vài phút (trích xuất chạy nền), đăng xuất rồi đăng nhập lại (phiên mới), hỏi một câu what-if lấy tiền: câu trả lời có tránh hũ Du lịch hoặc nói rõ không. Mở Hồ sơ → Bộ nhớ của tôi: thấy sở thích; xóa thì hết.
5. **Màn trace (tiêu chí 8, cảnh 6)**: đăng nhập `minh` (thuộc nhóm `ops`), chạy một what-if, mở "Vì sao" → hàng "Mã trace" → màn trace hiện đủ bước (router, từng tool kèm thời gian, verifier, luật). Đăng nhập `lan`: không thấy lối vào, gõ thẳng `#/ops/summary` bị từ chối.
6. **Xóa dữ liệu của tôi (tiêu chí 9)**: CHỈ trên `khoa` hoặc `giamkhao2`. Hồ sơ → Xóa dữ liệu của tôi → xác nhận. Sau đó app không còn dữ liệu; báo Phúc để kiểm Aurora/S3/Memory, rồi bấm Đặt lại dữ liệu demo.
7. **Hồ sơ hành vi và bản tin**: `minh` → Hồ sơ thấy 3 nhận xét; Tổng quan thấy thẻ bản tin; bấm "Ít nhắc loại này". Hỏi chat "Mình hay tiêu vào lúc nào?" ra khối nhận xét. Hỏi "Phí dịch vụ Trả sau mỗi tháng bao nhiêu?" ra số kèm khối trích dẫn nguồn.

Việc code nhỏ Học nhận được (mỗi việc một nhánh, chỉ unit test, gửi Phúc merge):
8. Màn So với bản cũ (L3) ghi "Loại bước" và "Giai đoạn" bằng mã thô (`set_aside`, `phase_id`): sửa ở `gateway/tools/ledger/yofina_ledger/roadmap_logic.py` (hàm dựng diff) cho ra chữ tiếng Việt.
9. Lambda sinh lại lộ trình (`pipelines/roadmap/`) lưu bản mới thì âm thầm bỏ bản đề xuất đang chờ (chat đã báo, Lambda thì chưa): ghi lý do vào bản mới hoặc phát notice.
10. Router và tiện ích ngày chưa đọc "trong 6 tháng" (chỉ đọc "6 tháng nữa/tới/sau"); luật dự phòng không đọc được hũ có tên chứa "mua" ("Mua xe").

### C. Việc để sau (đã ghi trong file phase 4, 5)

- `period_end` của lộ trình tính theo ngày hôm nay, chưa theo ngày lương (agent chưa đọc được payday).
- Tỷ lệ phải hỏi của phân loại 17,4%: hai hướng (bỏ token mẫu QR khỏi chuỗi embedding; giảm trọng số lịch sử khi ghi chú rõ).
- Bước lập lộ trình (`roadmap_agent.py`) chưa đọc bộ nhớ; chỉ câu trả lời của lượt lộ trình có.
- "Bài học của agent" từ `feedback` vào Memory: để sau (cần bước trong batch đêm).
- Câu tổng hồ sơ hành vi do model nhỏ viết có lúc bỏ sót ý Trả sau.
- Guardrail `ApplyGuardrail` p50 446 ms > 400 ms (open-questions).

## Cách làm việc

Claude Code là người điều phối: viết plan vào file phase, giao mỗi việc cho một worker `kiro-cli chat --no-interactive --trust-workspace --trust-all-tools --model claude-opus-5.5 --effort high` trong worktree riêng `C:\moMo-wt\<việc>` (nhánh riêng từ `main`), review diff, merge, chạy unit cả bộ; cuối đợt một worker deploy + integration + evals MỘT lần (evals tốn trần lượt gọi model trong ngày). **Không hardcode, không giả lập** ([master-plan mục 2](docs/plan/master-plan.md#2-quyết-định-áp-dụng-cho-mọi-phase)). Một luồng deploy tại một thời điểm; xem `cdk diff` trước mỗi deploy. Commit không Co-Authored-By.

## Quyết định đã chốt

- Region `ap-southeast-1`; không kéo FAST; frontend theo [ADR-0001](docs/decisions/0001-frontend-stack.md) và Figma; Cognito tắt tự đăng ký, tài khoản demo có nút đặt lại; bộ model (Sonnet 4.6, Nova 2 Lite hoặc Haiku 4.5, Kimi K3, Cohere); xác nhận bằng token dùng một lần do server cấp, Cedar là lớp phụ; sản phẩm trả sau mô phỏng; "Điểm chống chịu".
- 24/11: cắt RAG (luồng C phase 5): mọi con số lấy từ bảng có cấu trúc; khối trích dẫn dựng từ nguồn của bảng phí. Cảnh 4 demo để agent lập lộ trình trực tiếp trong chat (bản seed v3 làm đường dự phòng). Bộ nhớ theo best practice AgentCore Memory: một Memory, namespace theo `sub`, ba strategy, `IngestData`, che PII, không lưu số tiền hay giao dịch ([thiết kế](docs/research/agentcore-memory-design.md)).
- Quyền với AWS: được tạo và sửa tài nguyên `yofina-*` (tag `project=yofina`, ghi vào aws-resources.md) ở `ap-southeast-1`; hỏi trước với thứ tính tiền theo giờ đáng kể và trước khi xóa thứ không do dự án tạo; không đụng `jars-dev*`, `Jars*`, `CDKToolkit`.

## Quyết định còn treo

- Bật CloudWatch Transaction Search không.
- Hạn nộp chính xác, trọng số chấm, giữ tên Yofina ([open-questions.md](docs/requirements/open-questions.md)).

## Môi trường (kiểm 24/11, tự kiểm lại mỗi phiên)

- Windows 11, repo `C:\moMo` (Phúc), nhánh `main`, remote GitHub public. Python 3.13, uv, Node 24. `npm.ps1` bị chặn trong PowerShell: dùng `npm.cmd`.
- AWS CLI đang dùng thông tin đăng nhập root qua `aws login` (phiên 12 giờ). Không ghi account ID vào tài liệu.
- `kiro-cli` 3.5.0 đã cài, đăng nhập IAM Identity Center; model `claude-opus-5.5`.
- MCP: `aws-docs`, `agentcore`, `aws-mcp` (có lúc mất kết nối; dùng AWS CLI chỉ đọc thay thế).

## Lưu ý

- Repo public: không commit account ID, ARN có account ID, secret, token, mật khẩu demo, email.
- Mọi lời gọi model đi qua `yofina_core.llm` có giới hạn tốc độ và trần mỗi ngày (bảng `yofina-usage`, theo giờ Việt Nam); Claude 4.x khoảng 8–10 lượt/phút mỗi model. Hết trần thì ghi nhận, không chạy lại.
- `evals/results/` không vào git.
