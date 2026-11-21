# Phase 1 — Nền và lát dọc

Ngày dự kiến: 21–24/11/2026. Kế hoạch tổng và quy tắc chung: [master-plan.md](../master-plan.md) (đọc mục 2, 3, 4 trước).

## Mục tiêu

Một đường chạy thật từ đầu tới cuối trên AWS: người dùng đăng nhập Cognito trên app đã host → mở chat → agent Strands trên AgentCore Runtime → tool `ledger` qua Gateway (interceptor + Cedar) → Aurora → khối UI hiện trên màn hình; và một thao tác ghi (chuyển tiền giữa hai hũ) đi qua khối `confirm` và token dùng một lần. Lát dọc này cũng trả lời các điểm ở mục "Chưa thử" của [open-questions.md](../../requirements/open-questions.md), vì hai nửa backend và frontend mới được thử riêng.

## Phạm vi

Trong phase:

- Danh tính deploy thay root, bootstrap CDK, cảnh báo ngân sách, file danh sách tài nguyên.
- Sáu stack CDK ở mức tối thiểu (xem master-plan mục 2).
- Schema lõi, role `yofina_app`, RLS, migrator; dữ liệu Minh tối thiểu (7 hũ với số dư theo bảng số Figma, vài chục giao dịch); đặt lại dữ liệu.
- Tool `ledger___get_jar_balances`, `ledger___query_transactions`, `ledger___move_between_jars`; REST `GET /jars`, `POST /confirmations`, `POST /actions`, `POST /demo/reset`.
- Agent tối thiểu: router, đường nhanh một tool, phát khối UI, trần lượt gọi model.
- Frontend: khung app, đăng nhập, Tổng quan bản đầu, sheet chat với registry khối, host trên Amplify.
- Các phép thử "Chưa thử".

Ngoài phase: dự báo, màn hình chuyển tiền, onboarding, specialist, verifier, Guardrails, Memory dài hạn, pipeline.

## Đọc trước

| Luồng | Đọc |
|---|---|
| Mọi luồng | [overview.md](../../architecture/overview.md) trọn file; [open-questions.md](../../requirements/open-questions.md) mục "Chưa thử" |
| A | [aws-data-events-infra.md](../../research/aws-data-events-infra.md) §3.6, §3.6.5, §3.8; skill `aws-core:aws-cdk`, `aws-core:aws-iam`, `aws-core:aws-billing-and-cost-management` |
| B | [spike-aurora-data-api.md](../../research/spike-aurora-data-api.md) §4, §5, §6, §7; mã `spikes/aurora-data-api/setup_schema.py`, `setup_rls_fn.py`, `lambda_function.py` |
| C | [spike-agentcore-gateway-identity.md](../../research/spike-agentcore-gateway-identity.md) §1–§5, §8; mã `spikes/agentcore-gateway-identity/` (`setup_base.py`, `step2_interceptor.py`, `step3_policy.py`, `step5_confirm.py`, `lambdas/`); [agentcore.md](../../research/agentcore.md) §3.3, §3.4 |
| D | [spike-agentcore-runtime-cors.md](../../research/spike-agentcore-runtime-cors.md) §1, §2, §5, §7; [spike-strands-agui-local.md](../../research/spike-strands-agui-local.md) §2.1–§2.7, §2.9, §3; mã `spikes/agentcore-runtime-cors/agent/`, `make_zip.py`, `spikes/strands-agui-local/server.py`; [spike-bedrock-models.md](../../research/spike-bedrock-models.md) §2, §3, §8 |
| E | [ADR-0001](../../decisions/0001-frontend-stack.md); [spike-frontend-stack.md](../../research/spike-frontend-stack.md) §0, §1, §4, §5, §6; mã `spikes/frontend-stack/src/`; [figma-ui-design.md](../../research/figma-ui-design.md) §2, §3, §4; Figma node: Đăng nhập `31:2715`, Tổng quan `17:2`, H1 `21:1283`, H6a `21:1932`, H6b `21:2025`, component TabBar `5:218`, BalanceCard `14:143`, JarCard `7:130`, ConfirmBlock `11:244`, ReceiptBlock `11:269`, Notice `10:196`, ToolProgress `10:75` |

Phiên bản đã chạy được trong spike: `strands-agents` 1.65.0, `ag-ui-strands` 1.0.4, `ag-ui-protocol` 1.0.0, `@ag-ui/client` 1.0.5, `mcp` 2.x. Ghim đúng các bản này trừ khi tài liệu hiện hành buộc đổi.

## Bước 0 — Hợp đồng (tuần tự, làm trước)

Một subagent tạo:

- Workspace uv ở gốc repo, gói `libs/yofina_core` (khung rỗng có test chạy được), `contracts/`.
- `contracts/blocks/`: phong bì chung (`v`, `id`, `type`, `trace_id`, `fallback_text`, `source`, `data`) và schema cho `jar_summary`, `confirm`, `receipt`, `notice`. Script sinh Zod cho frontend và Pydantic cho Python.
- `contracts/tools/ledger.json`: ba tool của phase, `user_id` là tham số tùy chọn có mô tả "hệ thống tự điền".
- `contracts/rest/openapi.yaml`: bốn endpoint của phase.
- `db/migrations/0001_core.sql`: `users` (có `clock_offset_days`), `jars`, `transactions`, `audit_events`, `turn_blocks`; role `yofina_app` (`NOBYPASSRLS`, không phải owner), RLS `FORCE` trên mọi bảng có `user_id`, hàm đọc plpgsql `SECURITY INVOKER`.
- ADR-0002 (cơ chế xác nhận) và ADR-0003 (đồng hồ mô phỏng) theo master-plan mục 2.

## Luồng A — Danh tính deploy và nền CDK

Sở hữu: `infra-cdk/`, `scripts/bootstrap/`, `docs/aws-resources.md`.

> **Đổi ngày 2026-11-21 (chủ dự án)**: dùng luôn phiên root của CLI để deploy, không chuyển sang IAM user. Các bước 3–5 dưới đây không thực hiện; user `yofina-deployer` đã tạo ở bước 2 được giữ lại (không mật khẩu, không access key) để chuyển sang sau nếu muốn. Hệ quả: policy Deny lên `jars-dev*` không có tác dụng với root, nên việc không đụng `jars-dev*`, các stack `Jars*` và `CDKToolkit` chỉ còn dựa vào kỷ luật của agent; mọi lệnh vẫn đặt `--region ap-southeast-1` tường minh. Tiêu chí hoàn thành 8 bỏ vế "`sts get-caller-identity` là `yofina-deployer`".

Danh tính deploy (kế hoạch ban đầu):

1. Chủ dự án đăng nhập lại (`aws login`, connector AWS MCP). Phiên này còn là root.
2. Agent, bằng phiên root, chỉ tạo: IAM user `yofina-deployer` (không access key), gắn `AdministratorAccess` (CDK bootstrap cần quyền gần quản trị) và một policy `yofina-deny-jars-dev` Deny mọi hành động `rds:*` lên cluster và instance tên `jars-dev*`, và `cognito-idp:*` lên user pool có sẵn (tra id lúc chạy, không ghi vào repo). Tag `project=yofina`.
3. Chủ dự án tự làm trong console: đặt mật khẩu console và MFA cho `yofina-deployer`; bật MFA cho root nếu chưa; không tạo access key cho root.
4. Chủ dự án chạy `aws login --profile yofina-deploy` (chọn user mới), đặt `region = ap-southeast-1` cho profile, rồi kết nối lại connector AWS MCP bằng user mới.
5. Agent kiểm `sts get-caller-identity` không còn là root rồi mới làm tiếp. Từ đây mọi lệnh dùng `--profile yofina-deploy --region ap-southeast-1`.

Nếu chủ dự án muốn dùng IAM Identity Center thay IAM user thì đổi bước 2–4 tương ứng; phần còn lại giữ nguyên.

Nền CDK:

- App TypeScript, ghim phiên bản `aws-cdk-lib`, `env` tường minh, tag `project=yofina` ở mức app. `npx cdk bootstrap` cho `ap-southeast-1`.
- `YofinaFoundation`: bucket S3 artifact (chặn public, `enforceSSL`), AWS Budgets theo tháng với ngưỡng 50/80/100% gửi SNS + email (số tiền và email lấy từ context lúc deploy, không commit), bảng DynamoDB `yofina-confirm-jti` (TTL) và `yofina-usage` (đếm lượt gọi model theo ngày).
- `YofinaData`: Aurora PostgreSQL Serverless v2, 0,5–2 ACU, bật Data API, không public, subnet group do CDK tạo, termination protection; secret master và secret `yofina_app` riêng. Lambda migrator (dùng secret master) chạy các file trong `db/migrations/`.
- `YofinaIdentity`: user pool tắt tự đăng ký, app client công khai (không secret), access token 60 phút; script `scripts/create_demo_users.py` tạo sáu tài khoản demo, mật khẩu sinh ngẫu nhiên lưu Secrets Manager.
- `YofinaFrontend`: Amplify Hosting, deploy thủ công bằng zip (không nối GitHub).
- Script đóng gói Lambda và Runtime bằng uv (không Docker), dùng lại `spikes/agentcore-runtime-cors/make_zip.py`.
- Trước khi cài: xóa `.venv` và `node_modules` trong `spikes/` để lấy chỗ đĩa (giữ mã nguồn).

## Luồng B — Dữ liệu và Lambda `ledger`

Sở hữu: `db/`, `data/personas/`, `gateway/tools/ledger/`, `libs/yofina_core/` (phần DB, token, khối, `app_today`).

- `yofina_core.db`: client Data API. Đường đọc gọi hàm plpgsql; đường ghi `BeginTransaction` → `set_config('app.user_id', …, true)` → câu lệnh → `Commit`, luôn rollback trong `finally`; retry `DatabaseResumingException`; mọi truy vấn nhiều dòng có `LIMIT`; tiền là `Decimal`.
- `yofina_core.confirm`: cấp và kiểm token (HMAC, secret ở Secrets Manager; kiểm chữ ký, hạn, tool, sub, hash tham số chuẩn hóa, `jti` bằng `PutItem` điều kiện). Mang 13 ca thử của spike thành unit test.
- Lambda `yofina-ledger`, một mã hai đường vào: sự kiện từ Gateway (tên tool lấy từ `context.client_context.custom["bedrockAgentCoreToolName"]`, cắt tiền tố target, bỏ qua tham số lạ, `user_id` lấy từ `event`) và sự kiện từ HTTP API (sub lấy từ claim của JWT authorizer).
- `move_between_jars` không có token: không ghi, trả `NEEDS_CONFIRMATION` kèm tham số đã chuẩn hóa. Có token hợp lệ: ghi trong một transaction, ghi `audit_events`, trả dữ liệu cho khối `receipt`.
- HTTP API (JWT authorizer Cognito, CORS cho origin Amplify và localhost): `GET /jars`, `POST /confirmations`, `POST /actions`, `POST /demo/reset`.
- `data/personas/minh.py` bản tối thiểu, tất định theo seed, khớp số dư hũ ở [figma-ui-design.md §5](../../research/figma-ui-design.md); `demo/reset` xóa dữ liệu của người gọi rồi sinh lại và đặt `clock_offset_days`.

## Luồng C — Gateway, interceptor, Cedar

Sở hữu: `gateway/policies/`, `gateway/interceptor/`, phần Gateway trong stack `YofinaAgent`, `tests/integration/test_gateway_*.py`.

- Gateway MCP với JWT authorizer (discovery URL của user pool, `allowedClients`), target `ledger` trỏ Lambda `yofina-ledger`, schema từ `contracts/tools/ledger.json`.
- Lambda interceptor (`REQUEST`, `passRequestHeaders: true`): lấy `sub` từ `Authorization`, ghi đè `arguments.user_id` cho mọi `tools/call`.
- Policy engine và policy Cedar mỗi tool: `context.input has user_id && context.input.user_id == principal.id`; tool ghi thêm hạn mức `amount_vnd` và `has confirm_token`. Đưa lên `LOG_ONLY`, kiểm metric, rồi chuyển `ENFORCE`.
- Test tích hợp: A không đọc được dữ liệu của B dù tự điền `user_id` của B; gỡ tham số `user_id` vẫn chạy đúng; tool ghi không token bị từ chối; test cấu hình khẳng định Gateway có interceptor và engine ở `ENFORCE` (chạy được trong CI sau này).

## Luồng D — Agent trên Runtime

Sở hữu: `agent/`, `libs/yofina_core/llm.py`, phần Runtime trong stack `YofinaAgent`.

- `yofina_core.llm`: bọc Bedrock Converse; giới hạn tốc độ mỗi model, trần mỗi ngày đếm ở `yofina-usage`, chuỗi dự phòng bắt `ThrottlingException` và `AccessDeniedException`, lỗi có kiểu `ModelBudgetExceeded`. Có chế độ model giả cho test.
- Agent Strands + `ag-ui-strands`, endpoint `/invocations` và `/ping`, đóng zip ARM64, Runtime platform V2, JWT authorizer (`allowedClients`), `Authorization` trong `requestHeaderAllowlist`. Agent đọc `sub` từ header, không nhận `user_id` từ payload, chuyển nguyên access token cho Gateway.
- Router (Nova 2 Lite, ép tool để lấy JSON, có `structured_output_attempts`): `balance_lookup`, `move_between_jars`, `out_of_scope`, `chitchat`. Đường nhanh: gọi tool qua `MCPClient`, tool bọc phát khối bằng `ACTIVITY_SNAPSHOT` (mẫu ở spike Strands §3.1), LLM chỉ thấy bản gọn. Yêu cầu chuyển hũ: gọi `ledger___move_between_jars` không token, phát khối `confirm`.
- Đặt `limits`; chạm giới hạn hoặc `ModelBudgetExceeded` thì trả khối số liệu và một khối `notice`, không trả luồng rỗng.
- Ghi `turn_blocks` theo `trace_id` (lấy từ `traceparent`) để phát lại.

## Luồng E — Frontend

Sở hữu: `frontend/`.

- Dựng project theo spike (Vite, React, TypeScript, Tailwind 4, shadcn/ui, Plus Jakarta Sans tự host). Token màu, chữ, bo góc lấy từ trang Foundations của Figma (`28:2`) thành biến CSS, có sẵn cả bộ Sáng và Tối.
- Đăng nhập Cognito bằng `amazon-cognito-identity-js` hoặc gọi thẳng API `InitiateAuth` (SRP), giữ access token trong bộ nhớ, làm mới trước khi hết hạn. Cấu hình (pool id, client id, URL REST, ARN Runtime) đọc từ `.env.local`, không commit.
- Khung app: tab bar 5 mục, nút giữa "Hỏi Yofina" mở sheet chat. Tổng quan bản đầu: thẻ số dư và dải thẻ hũ, dữ liệu từ `GET /jars`.
- Client chat: `@ag-ui/client` gọi thẳng Runtime (URL, header session id, `traceparent`, gửi lại toàn bộ `messages`); coi luồng rỗng hoặc đứt là lỗi; xử lý `RUN_ERROR`, 401/403/409.
- Registry `type → { schema Zod, Component }`, parse từng khối riêng, error boundary từng khối, khối lạ hiện `fallback_text`. Component cho `jar_summary`, `confirm`, `receipt`, `notice`, và ToolProgress.
- Nút trong khối `confirm`: `POST /confirmations` → `POST /actions` → hiện `receipt` → tải lại số dư.
- Hồ sơ có nút "Đặt lại dữ liệu".

## Phép thử "Chưa thử" (người điều phối giao kèm bước ghép)

Mỗi phép thử ghi kết quả vào `docs/research/spike-vertical-slice.md` (đã chạy gì, thấy gì) và tick mục tương ứng trong open-questions.md.

| Điểm | Cách thử | Nếu không chạy |
|---|---|---|
| Frontend thật nối Runtime thật | Tiêu chí hoàn thành 1 | Không có phương án lùi: phải chạy |
| CORS từ domain Amplify | Gọi chat từ bản đã host | Thêm Lambda Function URL làm proxy streaming (hỏi chủ dự án trước) |
| Strands `MCPClient` với Gateway thật: tên `ledger___…`, truyền header, lỗi `-32002` khi Cedar từ chối | Gọi tool ghi không token với policy đang `ENFORCE` | Tự bắt `ExceptionGroup` quanh lời gọi tool, đổi thành kết quả có cấu trúc |
| Cedar `context.input.user_id` khi `user_id` là tham số tùy chọn | Luồng C | Khai `user_id` là `required` trong schema |
| Interrupt/resume AG-UI qua Runtime với session manager bền (S3 hoặc AgentCore Memory) | Thử tối đa nửa ngày bằng một tool thử | Ghi là không dùng; luồng xác nhận không phụ thuộc |
| Token hết hạn giữa luồng SSE | Đặt access token 5 phút ở một client thử | Ghi lại hành vi, frontend làm mới token trước mỗi lượt |
| Safari iPhone | Chủ dự án mở app đã host | Ghi lỗi gặp, sửa ở phase 2 |

## Tiêu chí hoàn thành

1. Trên URL Amplify, đăng nhập bằng tài khoản `minh`, gõ "số dư các hũ của mình", thấy khối `jar_summary` có 7 hũ với số khớp Aurora, kèm một câu trả lời.
2. Gõ "chuyển 100 nghìn từ Giải trí sang Ăn uống": hiện khối `confirm` đúng số tiền; bấm xác nhận thì số dư hai hũ đổi trong Aurora và hiện `receipt`; không bấm thì không gì đổi.
3. Gọi lại `POST /actions` với token đã dùng, token đổi tham số, token của tài khoản khác: đều bị từ chối.
4. Tài khoản `lan` không đọc được dữ liệu của `minh` qua Gateway lẫn REST, kể cả khi tự gửi `user_id` của `minh`.
5. "Đặt lại dữ liệu" đưa tài khoản về đúng số ban đầu.
6. Tải lại trang giữa cuộc hội thoại: khối đã hiện vẫn còn.
7. Đặt trần Sonnet và model nhỏ về 0 trong `yofina-usage`: chat vẫn trả khối số dư và một `notice`, không gọi model.
8. `sts get-caller-identity` là `yofina-deployer`; Budgets và SNS tồn tại; `docs/aws-resources.md` liệt kê đủ; `git grep` không thấy account ID hay secret.
9. Mọi dòng trong bảng phép thử có kết quả ghi lại.
10. Đo và ghi: thời gian tới event đầu của lượt đầu (phiên lạnh) và lượt hai.

## Cách kiểm (người điều phối)

- `uv run pytest` (unit) và `uv run pytest tests/integration` (gọi môi trường thật); `npm run build` và test của frontend; `npx cdk diff` sạch sau deploy.
- Mở URL Amplify bằng trình duyệt trong app, đi lại tiêu chí 1, 2, 5, 6 bằng tay; đọc Aurora qua Data API để đối chiếu số.
- Chạy lại script tấn công token và script hai tài khoản.
- Liệt kê tài nguyên có tag `project=yofina` trên tài khoản, so với `aws-resources.md`.

## Kết quả thực hiện

(Điền khi đóng phase: đã làm gì, lệch gì so với kế hoạch, số đo, việc chuyển sang phase sau.)
