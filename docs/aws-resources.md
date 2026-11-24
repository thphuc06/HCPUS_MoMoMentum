# Tài nguyên AWS của dự án

Danh sách mọi tài nguyên dự án tạo trên AWS, Region `ap-southeast-1`. Quy ước: tên có tiền tố `yofina-`, tag `project=yofina` (CDK gắn ở mức app). **Không ghi account ID, ARN đầy đủ, secret hay email vào file này** (repo public). Cập nhật mỗi khi tạo, đổi hoặc xóa tài nguyên; đối chiếu với tài khoản khi đóng mỗi phase.

Không thuộc dự án, không được đụng: cluster Aurora và Cognito user pool có tên bắt đầu bằng `jars-dev`, các stack `Jars*`, stack `CDKToolkit`.

"Tính tiền khi nhàn rỗi": Có = có phí dù không dùng; Không = chỉ trả khi dùng (hoặc miễn phí ở mức dự án này).

## Do CDK tạo (app `infra-cdk/`)

### Stack `YofinaFoundation` (phase 1, termination protection)

| Tên | Loại | Phase | Tính tiền khi nhàn rỗi | Ghi chú |
|---|---|---|---|---|
| `yofina-artifacts-<account-id>-ap-southeast-1` | S3 bucket | 1 | Không (vài xu theo dung lượng) | Chặn public, `enforceSSL`, SSE-S3, lifecycle: xóa `tmp/` sau 30 ngày, `builds/` sau 90 ngày; RETAIN |
| `yofina-alerts` | SNS topic | 1 | Không | Cho Budgets publish; có một subscription email (chờ người nhận bấm link xác nhận) |
| `yofina-monthly` | AWS Budgets | 1 | Không | 100 USD/tháng, ngưỡng thực tế 50/80/100% gửi SNS; phạm vi cả tài khoản (`budgetScope=account`) |
| `yofina-confirm-jti` | DynamoDB | 1 | Không (on-demand) | Khóa `jti` (S), TTL `ttl`; token xác nhận dùng một lần |
| `yofina-usage` | DynamoDB | 1 | Không (on-demand) | Khóa `day` (S) + `model` (S), thuộc tính `count`, TTL `ttl`; đếm lượt gọi model theo ngày; RETAIN |
| `yofina-confirm-hmac` | Secrets Manager | 1 | Có (0,40 USD/tháng) | Khóa HMAC ký token xác nhận, sinh ngẫu nhiên |
| `/yofina/s3/…`, `sns/…`, `dynamodb/…`, `secrets/…` | SSM Parameter (String, standard) | 1 | Không | Giá trị cho luồng khác; xem [infra-cdk/README.md](../infra-cdk/README.md) |

### Stack `YofinaData` (phase 1, termination protection)

| Tên | Loại | Phase | Tính tiền khi nhàn rỗi | Ghi chú |
|---|---|---|---|---|
| `yofina-db` | Aurora PostgreSQL 17.11 cluster | 1 | Có (cùng với instance, xem dưới) | Serverless v2, Data API, mã hóa lưu trữ, deletion protection, backup 1 ngày, không public; DB `yofina` |
| `yofina-db` writer instance | Aurora serverless v2 instance | 1 | Có khi thức (0,5–2 ACU); 0 khi ngủ | Từ 22/11: min 0, max 2 ACU, tự ngủ sau 600 giây rảnh (`dbAutoPauseSeconds`). Lúc chạy liên tục 0,5 ACU khoảng 73 USD/tháng. Trước demo deploy lại với `-c dbMinAcu=0.5` |
| `yofina-vpc` | VPC + 2 subnet isolated, route table, security group, DB subnet group | 1 | Không | 0 NAT Gateway, 0 VPC endpoint, không Internet Gateway |
| `yofina-db-master` | Secrets Manager | 1 | Có (0,40 USD/tháng) | Do RDS/CDK sinh, chỉ migrator đọc; user `yofina_admin` |
| `yofina-db-app` | Secrets Manager | 1 | Có (0,40 USD/tháng) | Role `yofina_app` (non-owner, NOBYPASSRLS); mọi tool dùng secret này |
| `yofina-migrator` | Lambda (Python 3.13, arm64, ngoài VPC) + IAM role + log group (14 ngày) | 1 | Không | Tạo/đổi mật khẩu `yofina_app`, chạy `db/migrations/*.sql` qua Data API |
| `/yofina/db/…` | SSM Parameter | 1 | Không | cluster ARN, tên DB, ARN secret app, tên hàm migrator |

### Stack `YofinaIdentity` (phase 1, termination protection)

| Tên | Loại | Phase | Tính tiền khi nhàn rỗi | Ghi chú |
|---|---|---|---|---|
| `yofina-users` | Cognito user pool | 1 | Không (10.000 MAU đầu miễn phí) | Tắt tự đăng ký, đăng nhập bằng email, deletion protection, RETAIN |
| `yofina-web` | Cognito app client | 1 | Không | Công khai, không secret, SRP, access token 60 phút |
| `ops` | Cognito group | 1 | Không | |
| `/yofina/auth/…` | SSM Parameter | 1 | Không | user pool id, client id, discovery URL |

### Stack `YofinaFrontend` (phase 1)

| Tên | Loại | Phase | Tính tiền khi nhàn rỗi | Ghi chú |
|---|---|---|---|---|
| `yofina-web` | Amplify Hosting app + branch `main` | 1 | Không (theo băng thông/dung lượng) | Deploy thủ công bằng zip; rewrite SPA; header bảo mật cơ bản. URL: `https://main.dcrwn4u7vqklo.amplifyapp.com` (đang là trang thử hạ tầng) |
| `/yofina/frontend/…` | SSM Parameter | 1 | Không | app id, branch, URL |

### Stack `YofinaTools` (phase 1, luồng B)

| Tên | Loại | Phase | Tính tiền khi nhàn rỗi | Ghi chú |
|---|---|---|---|---|
| `yofina-ledger` | Lambda (Python 3.13, arm64, ngoài VPC, 512 MB, timeout 30 s) + IAM role + log group `/aws/lambda/yofina-ledger` (14 ngày) | 1 | Không | Một mã, hai đường vào: HTTP API và AgentCore Gateway (luồng C sẽ gắn target). Zip đóng bằng `scripts/build_lambda.py` (kèm `yofina_core` và `data/personas`). IAM tối thiểu: Data API trên cluster, `GetSecretValue` chỉ trên secret `yofina-db-app` và `yofina-confirm-hmac` (không đọc secret master), `dynamodb:PutItem` trên `yofina-confirm-jti` |
| `yofina-api` | API Gateway HTTP API (`$default` stage, tự deploy) + JWT authorizer `yofina-cognito` + 4 route (`GET /jars`, `POST /confirmations`, `POST /actions`, `POST /demo/reset`) + permission Lambda | 1 | Không (theo số request) | Authorizer: issuer là user pool `yofina-users`, audience là app client `yofina-web` (HTTP API so với `aud` hoặc `client_id`, nên nhận access token Cognito). CORS cho origin Amplify (SSM) và `http://localhost:5173`. Giới hạn mặc định 20 req/s, burst 40 |
| `/yofina/api/url`, `/yofina/ledger/function-name`, `/yofina/ledger/function-arn` | SSM Parameter | 1 | Không | URL API (không có dấu `/` cuối) cho frontend (`print_env.py` ghi thành `VITE_API_BASE_URL`); tên và ARN Lambda cho luồng C |

**Phase 2, luồng A (2026-11-22)** thêm vào stack `YofinaTools`:

| Tên | Loại | Tính tiền khi nhàn rỗi | Ghi chú |
|---|---|---|---|
| `yofina-bus` | EventBridge event bus (tùy biến) | Không (theo số sự kiện) | Nhận sự kiện của ledger sau mỗi lần ghi: `transaction.recorded`, `salary.confirmed`, `obligation.changed`, `profile.updated` (source `yofina.ledger`). Chưa có consumer (đợt sau: Lambda `yofina-on-transaction` qua SQS có DLQ). SSM: `/yofina/events/bus-name`, `/yofina/events/bus-arn` |
| `yofina-ledger-event-publish-failed` | CloudWatch alarm (1 metric) | Không đáng kể (khoảng 0,10 USD/tháng) | Metric `EventPublishFailed` của namespace `Yofina/Ledger` do Lambda ghi bằng log EMF; có sự cố phát sự kiện thì gửi SNS `yofina-alerts` |

Thay đổi trên tài nguyên có sẵn: `yofina-ledger` thêm quyền `events:PutEvents` (chỉ trên `yofina-bus`) và 8 biến môi trường nghiệp vụ mới; `yofina-api` có 18 route (thêm 12: `/jars/{jar_code}`, `/overview`, `/profile`, `/transactions`, `/tx-types`, `/payees`, `/obligations`, `/credit-line`, `/salary-events`, `/jar-templates`, `/forecasts/{jar_code}`, `/confirmations/cancel`); Aurora chạy migration `0007_wallet_ops`. Test tích hợp tạo rồi **xóa** các thứ tạm: một user Cognito (và mọi dòng DB của nó), một rule EventBridge và một hàng đợi SQS trên `yofina-bus` (tiền tố `yofina-test-`); không để lại tài nguyên nào.

Bước ghép backend (2026-11-22) thêm vào `yofina-api` hai route `GET /conversations` và `GET /conversations/{conversation_id}` (đọc lại các lượt hội thoại đã lưu) và vào `yofina-ledger` tool `save_turn`; bảng Aurora mới `conversation_turns` (migration `0003_conversation_turns`).

**Phase 2, luồng C (2026-11-22)** thêm vào stack `YofinaTools` (pipeline dự báo; không có thứ nào tính tiền khi nhàn rỗi):

| Tên | Loại | Tính tiền khi nhàn rỗi | Ghi chú |
|---|---|---|---|
| `yofina-forecast-batch` | Lambda (Python 3.13, arm64, ngoài VPC, 1.769 MB, timeout 120 s) + IAM role + log group `/aws/lambda/yofina-forecast-batch` (14 ngày) | Không | Batch đêm, đặt lại demo (ledger gọi đồng bộ), tính lại khi đọc cũ (ledger gọi nền). Zip numpy + scipy 46 MB nén, 156 MB giải nén, dùng chung cho ba Lambda (đóng bằng `scripts/build_lambda.py pipelines/forecast ... --slim`). IAM tối thiểu: Data API trên cluster, `GetSecretValue` CHỈ trên secret `yofina-db-app`, `events:PutEvents` trên `yofina-bus` |
| `yofina-on-transaction` | Lambda (cùng cấu hình, timeout 90 s) + IAM role + log group | Không | Consumer SQS của sự kiện ledger (chỉnh nhanh hoặc chạy đầy đủ), idempotent theo `event_id`. IAM như trên, cộng `PutItem/GetItem/UpdateItem/DeleteItem` trên `yofina-idempotency` |
| `yofina-forecast` | Lambda (cùng cấu hình, timeout 60 s) + IAM role + log group | Không | Target `forecast` của Gateway (tool `forecast___get_forecast`) |
| `yofina-idempotency` | DynamoDB (on-demand) | Không | Khóa `event_id` (S), TTL `ttl` (3 ngày). Đặt ở `YofinaTools` thay vì `YofinaFoundation` (stack có termination protection, tránh đụng vào Budgets); `DESTROY` khi gỡ stack |
| `yofina-forecast-events` | SQS standard (visibility 540 s, giữ 4 ngày, `enforceSSL`) | Không | Nhận 4 loại sự kiện của ledger từ rule `yofina-forecast-ledger-events` trên `yofina-bus`; event source mapping vào `yofina-on-transaction` (lô 10, không chờ gom, đồng thời tối đa 5, partial batch response) |
| `yofina-forecast-events-dlq` | SQS (giữ 14 ngày) | Không | Sau 3 lần giao không thành |
| `yofina-forecast-ledger-events` | EventBridge rule trên `yofina-bus` | Không | `source yofina.ledger`, `detail-type` ∈ `transaction.recorded`, `salary.confirmed`, `obligation.changed`, `profile.updated`; đích là hàng đợi trên |
| `yofina-nightly` | Step Functions Standard (+ log group `/aws/vendedlogs/states/yofina-nightly`, mức ERROR) + IAM role | Không (theo số chuyển trạng thái) | ListUsers -> Map (song song 3) -> RunUser (retry `DatabaseUnavailable`, catch từng người) -> Summarize (có lỗi thì execution thất bại) |
| `yofina-nightly-0200` | EventBridge Scheduler schedule + role `yofina-nightly-scheduler` | Không | `cron(0 2 * * ? *)`, múi giờ `Asia/Ho_Chi_Minh`, bắt đầu `yofina-nightly` (retry 2 lần) |
| `yofina-nightly-failed`, `yofina-nightly-timed-out`, `yofina-forecast-events-dlq-not-empty` | CloudWatch alarm (3 metric) | Không đáng kể (khoảng 0,10 USD/tháng mỗi alarm) | Gửi SNS `yofina-alerts` |
| `/yofina/forecast/function-name`, `function-arn`, `batch-function-name`, `nightly-arn`, `events-queue-url`, `idempotency-table` | SSM Parameter | Không | Giá trị cho `YofinaAgent`, script và test |

Thay đổi trên tài nguyên có sẵn (phase 2, luồng C): `yofina-ledger` thêm 2 biến môi trường (`YOFINA_FORECAST_FUNCTION_NAME`, `YOFINA_FORECAST_SYNC_TIMEOUT_SECONDS`) và quyền `lambda:InvokeFunction` CHỈ trên `yofina-forecast-batch`; Aurora chạy migration `0009_forecast_pipeline`; `YofinaAgent` thêm target `forecast` (Lambda `yofina-forecast`, schema từ `contracts/tools/forecast.json`) và policy Cedar `forecast_get_forecast_own_user`, vai `yofina-gateway` được `lambda:InvokeFunction` thêm trên `yofina-forecast`, Runtime `yofina_agent` lên version mới (ý định `forecast_lookup`). Test tích hợp tạo rồi xóa: tài khoản Cognito tạm, rule và hàng đợi SQS tạm tiền tố `yofina-test-`, thực thi Step Functions tên `test-*`; không để lại tài nguyên nào.

**Đóng phase 2 (2026-11-22)**: không tạo tài nguyên mới. Deploy lại `YofinaTools` (chỉ đổi code 4 Lambda: `yofina-ledger`, `yofina-forecast-batch`, `yofina-on-transaction`, `yofina-forecast`) và một lần deploy Amplify. Tạo rồi xóa một user Cognito tạm trong `yofina-users` để thử onboarding (kèm mọi dòng DB của nó).

**Phase 3, luồng A (2026-11-22)**: deploy lại `YofinaTools`. Tài nguyên mới (đều không tính tiền theo giờ, không có thẻ nào chạy khi nhàn rỗi):

| Tài nguyên | Loại | Ghi chú |
|---|---|---|
| route `POST /affordability` | HTTP API `yofina-api`, JWT authorizer Cognito | Tích hợp Lambda `yofina-forecast` (khối `affordability_card`, không qua LLM) |
| route `GET /traces/{trace_id}` | HTTP API `yofina-api` | Tích hợp Lambda `yofina-ledger` (bảng "Vì sao", chỉ của chính người dùng) |
| route `POST /feedback` | HTTP API `yofina-api` | Tích hợp Lambda `yofina-ledger` (không qua token xác nhận, không đụng tiền) |
| 3 quyền `lambda:InvokeFunction` cho API Gateway | Lambda permission | Một quyền mỗi route mới |

Thay đổi trên tài nguyên có sẵn: code Lambda `yofina-ledger` (thêm `yofina_planner`, `yofina_knowledge`, `yofina_audit`, thư mục `rules/` YAML cho tool `planner`, `knowledge`, `audit`; chạy chung Lambda theo quyết định của người điều phối, không có Lambda riêng) và `yofina-forecast`, `yofina-forecast-batch`, `yofina-on-transaction` (cùng một zip, thêm `run_scenario`, `affordability_check`, engine kịch bản 5.000 đường). Biến môi trường mới: `YOFINA_FORECAST_SCENARIO_N_PATHS`, `YOFINA_FORECAST_SCENARIO_KEEP`, `YOFINA_AFFORDABILITY_TIGHT_P10_FLOOR_VND`, `YOFINA_AFFORDABILITY_SHORT_P50_FLOOR_VND`, `YOFINA_REFERENCE_CACHE_SECONDS` (Lambda forecast) và `YOFINA_SUITABILITY_WINDOW_DAYS` (Lambda ledger); mọi ngưỡng nằm trong cấu hình, không gắn cứng trong mã. Cổng của Gateway (bốn target `forecast`, `planner`, `knowledge`, `audit` và các policy Cedar) thuộc stack `YofinaAgent`, **chưa deploy** ở bước này. Không thêm Lambda, bảng, hàng đợi hay endpoint tính tiền theo giờ.

### Stack `YofinaAgent` (phase 1, bước ghép, luồng C và D)

| Tên | Loại | Phase | Tính tiền khi nhàn rỗi | Ghi chú |
|---|---|---|---|---|
| `yofina-gateway` | AgentCore Gateway (MCP) | 1 | Không (theo lời gọi) | JWT authorizer Cognito (discovery URL của `yofina-users`, `allowedClients` = app client `yofina-web`), 1 interceptor `REQUEST` (`passRequestHeaders`), policy engine ở `ENFORCE`, `exceptionLevel` mặc định (không DEBUG); target `ledger` (Lambda `yofina-ledger`, schema từ `contracts/tools/ledger.json`, 10 tool từ phase 2) |
| `yofina-gw-interceptor` | Lambda (Python 3.13, arm64, ngoài VPC, 128 MB, timeout 5 s) + log group (14 ngày) | 1 | Không | Ghi đè `user_id` bằng `sub` của JWT (mã ở `gateway/interceptor/`, chỉ thư viện chuẩn) |
| `yofina_policy_engine` + 10 policy `ledger_<tool>_own_user` (phase 2: thêm 6) | AgentCore Policy engine và policy Cedar | 1 | Không (theo lượt đánh giá) | Mã Cedar ở `gateway/policies/`, `FAIL_ON_ANY_FINDINGS` |
| `yofina-gateway` (role) | IAM role | 1 | Không | Tin `bedrock-agentcore.amazonaws.com` (điều kiện `aws:SourceAccount`, `aws:SourceArn` `gateway/*`); `lambda:InvokeFunction` chỉ trên `yofina-ledger` và `yofina-gw-interceptor`, `GetPolicyEngine`/`AuthorizeAction`/`PartiallyAuthorizeActions` |
| `yofina_agent` | AgentCore Runtime (CodeZip ARM64, `PYTHON_3_13`, AGUI, platform V2) + endpoint `DEFAULT` + workload identity tự sinh | 1 | Không khi nhàn rỗi (tính theo mức dùng) | `customJWTAuthorizer` (`allowedClients` = `yofina-web`), `requestHeaderAllowlist ["Authorization"]`, mã từ S3 `builds/agent-<hash>.zip`; log group `/aws/bedrock-agentcore/runtimes/yofina_agent-*` tự tạo |
| `yofina-agent-runtime` | IAM role | 1 | Không | Quyền tối thiểu: `bedrock:InvokeModel*` cho các model/inference profile trong `llm_defaults.json` (Sonnet 4.6, Kimi K3, Nova 2 Lite, Haiku 4.5, Cohere Embed), `dynamodb:UpdateItem` trên `yofina-usage`, `ssm:GetParameter(sByPath)` trên `/yofina/gateway_url`, `/yofina/dynamodb/usage-table`, `/yofina/llm/*`, `s3:GetObject` trên `builds/*`, log, X-Ray, `PutMetricData`, workload identity |
| `/yofina/gateway_url`, `/yofina/gateway/id`, `/yofina/gateway/arn`, `/yofina/agent/runtime-arn`, `/yofina/agent/runtime-id`, `/yofina/agent/runtime-url` | SSM Parameter | 1 | Không | URL MCP của Gateway; ARN, id và URL invoke của Runtime (chứa account ID: chỉ đi qua SSM và `frontend/.env.local`) |
| `yofina-guardrail` (+ version cố định, đổi cấu hình thì ra version mới) | Bedrock Guardrail (bậc STANDARD, hồ sơ liên vùng `apac.guardrail.v1:0`), tag `project=yofina` | 3 | Không (theo lượt `ApplyGuardrail`) | Chủ đề cấm `specific-investment-advice`; lọc nội dung HIGH (riêng MISCONDUCT LOW từ 23/11, vì chặn nhầm câu chuyển tiền) + PROMPT_ATTACK ở đầu vào. Deploy 2026-11-22; đã kiểm `ApplyGuardrail` chặn câu hỏi "nên mua cổ phiếu" (`GUARDRAIL_INTERVENED`). **Tới 23/11 sáng Runtime gọi Guardrail luôn AccessDenied** (IAM chỉ cho hồ sơ ở ap-southeast-1); nay statement `ApplyGuardrail` gồm hồ sơ ở 6 vùng đích APAC |
| `/yofina/guardrail/id`, `/yofina/guardrail/version` | SSM Parameter | 3 | Không | Agent đọc id và version lúc khởi động |
| Phase 3 (YofinaAgent, 2026-11-22) | Target Gateway `forecast`, `planner`, `knowledge`, `audit` + policy Cedar mỗi tool; statement IAM `ApplyGuardrail` (guardrail và guardrail-profile) và hai tham số SSM guardrail thêm vào `yofina-agent-runtime` | 3 | Không | Runtime `yofina_agent` lên version 4 (mã agent phase 3, `scripts/agent_deploy.py`); frontend đã deploy lại lên Amplify (job 6) |

**Deploy 23/11 (đêm 22 sang 23/11, sau khi merge `feat/ingest`)**: F1 (tool `audit___record_turn`, Cedar `audit_record_turn_own_user`, env `YOFINA_TURN_RECORD_TOOL`) và F3 đã lên: `YofinaTools`, `YofinaAgent`, Runtime `yofina_agent` version 6 (`scripts/agent_deploy.py`), frontend Amplify job 7. Migration tới `0050_ingest`. Zip `yofina-ledger` nay kèm persona `vy` (`data/personas`).

**Deploy 23/11 sáng** (`scripts/agent_deploy.py`, ba lần, chỉ `YofinaAgent`): IAM `ApplyGuardrail` cho hồ sơ guardrail ở 6 vùng đích; cấu hình guardrail mới (MISCONDUCT LOW, version mới); mã router và schema sửa. Runtime `yofina_agent` version 9. Không thêm tài nguyên tính tiền theo giờ.

**Deploy 23/11 chiều (đóng phase 3)**: `YofinaData` min ACU tạm lên 0,5 để đo rồi trả về 0 (auto-pause 600 s, đã kiểm `describe-db-clusters`); Runtime `yofina_agent` version 13 (sửa ca Trả sau, luật dự phòng khi model hỏng); Amplify job 9 (thu nhỏ ảnh trước khi tải). SSM `/yofina/llm/*` đã được test ép lỗi khôi phục. Không thêm tài nguyên tính tiền theo giờ.

**Deploy 23/11 trưa**: migration `0051_scenario_conversation` (cột `scenarios.conversation_id`, `scenarios.bundle`, hàm `app_list_conversation_scenarios`); zip `yofina-forecast` + `YofinaTools`; `YofinaAgent` (tool `forecast___list_scenarios` trên target `forecast` + Cedar `forecast_list_scenarios_own_user`; `run_scenario` thêm `conversation_id`, `with_scenarios`); Runtime `yofina_agent` version 12; Amplify job 8. Không thêm tài nguyên tính tiền theo giờ.

### Stack `YofinaIngest` (phase 5, F6 nạp dữ liệu từ ảnh và CSV) — đã deploy 23/11

Code ở `infra-cdk/lib/ingest-stack.ts`. Không có thứ tính tiền theo giờ. Nhóm Cognito mới `persona-vy` (tạo bằng `scripts/seed_demo.py giamkhao3`, gán `giamkhao3`).

| Tên | Loại | Phase | Tính tiền khi nhàn rỗi | Ghi chú |
|---|---|---|---|---|
| `yofina-ingest-<account-id>-ap-southeast-1` | S3 bucket | 5 | Không (vài xu theo dung lượng) | Chặn public, `enforceSSL`, SSE-S3, không versioning, `BucketOwnerEnforced`, xóa object sau 30 ngày, hủy multipart dở sau 1 ngày, CORS `POST` (Amplify + localhost) cho presigned POST; ObjectCreated `u/` -> SQS; RETAIN |
| `yofina-ingest-jobs`, `yofina-ingest-jobs-dlq` | SQS (SSE-SQS, bắt TLS) | 5 | Không | Visibility 720 s (6 × 120 s), `maxReceiveCount` 3, DLQ giữ 14 ngày; queue policy cho `s3.amazonaws.com` có `aws:SourceArn` + `aws:SourceAccount` |
| `yofina-ingest-jobs-dlq-not-empty` | CloudWatch alarm | 5 | Không (trong 10 alarm miễn phí; vượt thì 0,10 USD/tháng) | -> SNS `yofina-alerts` |
| `yofina-ingest-api` | Lambda (Python 3.13, arm64, 512 MB, 30 s, `handler_api.handler`) + IAM role + log group `/aws/lambda/yofina-ingest-api` (14 ngày) | 5 | Không | REST `/ingest/*`: presigned POST (`s3:PutObject` chỉ khi `s3:authType = POST`), tiến độ job, đổi hũ đề xuất, tự cấp/kiểm token `confirm_rows` bằng `yofina_core.confirm` (cùng secret HMAC, cùng bảng jti với ledger), chốt dòng vào sổ cái (`funding_source = external`) trong một transaction, rồi gọi `yofina-forecast-batch` bất đồng bộ (`lambda:InvokeFunction` chỉ trên Lambda đó). Tự dọn job mồ côi sau khi `/demo/reset` của ledger cũ. Không gọi Bedrock, không phát sự kiện. |
| `yofina-ingest` | Lambda (Python 3.13, arm64, 1024 MB, 120 s, `handler_worker.handler`) + IAM role + log group `/aws/lambda/yofina-ingest` (14 ngày) + event source SQS (batch 1, `ReportBatchItemFailures`, max concurrency 2, không reserved concurrency) | 5 | Không | Worker đọc ảnh bằng Bedrock Converse (vai `ingest`: Sonnet 4.6, dự phòng Kimi K3), ánh xạ cột và gắn nhãn CSV bằng model nhỏ (vai `ingest_columns`: Nova 2 Lite, dự phòng Haiku 4.5), global cross-Region inference; đếm lượt gọi ở `yofina-usage` (trần ngày `ingest` 300, `ingest_columns` 600); đọc/xóa `u/*`; xử lý bản tin SQS từng cái, lần giao cuối đánh dấu job `failed` trước khi vào DLQ; có op `eval_extract` (gọi trực tiếp, không DB, không S3) cho `scripts/eval_ingest.py --via-lambda`. |
| `yofina-cognito-ingest` | JWT authorizer trên HTTP API `yofina-api` (có sẵn) | 5 | Không | Cùng issuer/audience với `yofina-cognito`; thuộc stack `YofinaIngest`, không sửa `YofinaTools` |
| 6 route `/ingest/*` + 1 integration | Route và integration trên `yofina-api` | 5 | Không (theo request) | `POST /ingest/uploads`, `GET /ingest/jobs`, `GET /ingest/jobs/{job_id}`, `POST /ingest/rows/{row_id}/jar`, `POST /ingest/confirmations`, `POST /ingest/actions`; chỉ GET/POST (CORS của `yofina-api` chỉ cho GET, POST, OPTIONS); JWT; `AWS_PROXY` 2.0 |
| `/yofina/ingest/bucket-name`, `/yofina/ingest/api-function-name`, `/yofina/ingest/worker-function-name`, `/yofina/ingest/queue-url` | SSM Parameter | 5 | Không | |
| Lambda tạm của CDK cho `Custom::S3BucketNotifications` + role | Lambda | 5 | Không | CDK tự sinh để gắn notification vào bucket |

### Phase 4 (chống chịu, lộ trình, phân hũ tự động) — đã deploy 23/11 chiều

Thuộc stack `YofinaTools` (construct `ClassifyPipeline`, `infra-cdk/lib/classify.ts`) và `YofinaAgent`. Migration `0052_resilience_roadmap_classify` đã chạy trên Aurora (pgvector, bảy bảng, hàm `app_*`). Không thêm tài nguyên tính tiền theo giờ (không NAT, không endpoint SageMaker, không OpenSearch); Aurora giữ min 0 ACU.

| Tên | Loại | Phase | Tính tiền khi nhàn rỗi | Ghi chú |
|---|---|---|---|---|
| `yofina-classify` | Lambda (Python 3.13, arm64, 512 MB, timeout 90 s) + IAM role + log group `/aws/lambda/yofina-classify` | 4 | Không | Phân hũ tự động: luật người dùng, bảng tra loại, embedding Cohere, k-NN pgvector, model nhỏ. Zip `classify-arm64` (4,0 MB, nhúng `yofina_ledger` kèm `classify_defaults.json`). IAM: Data API và secret `yofina-db-app`, Bedrock cho model của vai `small`, `embedding` (có `cohere.embed-multilingual-v3`), `yofina-usage`, bảng idempotency riêng |
| `yofina-classify-events` | SQS (visibility 540 s) | 4 | Không | Nhận `transaction.recorded` có `needs_classification`; event source cho `yofina-classify` (batch 5, `ReportBatchItemFailures`, `maxConcurrency` 3) |
| `yofina-classify-events-dlq` | SQS | 4 | Không | Sau 3 lần giao không thành |
| `yofina-classify-needs-classification` | EventBridge rule trên `yofina-bus` | 4 | Không | `source yofina.ledger`, `detail-type transaction.recorded`, `needs_classification` = true -> `yofina-classify-events` |
| `yofina-classify-idempotency` | DynamoDB (on-demand) | 4 | Không | Khóa `event_id`, TTL 3 ngày |
| `yofina-classify-events-dlq-not-empty` | CloudWatch alarm | 4 | Không đáng kể (khoảng 0,10 USD/tháng nếu vượt 10 alarm miễn phí) | -> SNS `yofina-alerts` |
| 10 route ledger: `GET /roadmap`, `GET /roadmap/versions`, `GET /roadmap/diff`, `POST /roadmap/steps/{step_id}/decision`, `POST /roadmap/steps/{step_id}/edit`, `POST /roadmap/versions/{version}/decision`, `POST /roadmap/regenerate`, `GET /roadmap/jobs/{job_id}`, `GET /review`, `POST /review/daily-ask/skip` | Route trên HTTP API `yofina-api` | 4 | Không | Tích hợp Lambda `yofina-ledger` |
| 3 route forecast: `GET /resilience`, `GET /resilience/shocks`, `POST /resilience/stress` | Route trên `yofina-api` | 4 | Không | Tích hợp Lambda `yofina-forecast` |
| 5 tool Gateway: `forecast___get_resilience_score`, `forecast___stress_test`, `planner___optimize_allocation`, `planner___save_roadmap`, `planner___get_roadmap` + 5 policy Cedar `<target>_<tool>_own_user` | Tool trên target `forecast` và `planner` | 4 | Không | Gateway nhận schema `save_roadmap` lồng bảy cấp, không phải làm phẳng `action`. `optimize_allocation` ở ledger gọi `Invoke` sang `yofina-forecast-batch` để giải LP (scipy) |

**Deploy 23/11 chiều (phase 4, phần Phúc)**: migration `0052`; `YofinaTools` ba lần (lần đầu: 13 route, `yofina-classify` + SQS + DLQ + rule + bảng idempotency, code ledger và forecast mới kèm `ruptures`; lần hai: sửa thông điệp lỗi hỏng dấu của `ROADMAP_VERSION_CONFLICT`; lần ba: ngưỡng phân loại đã hiệu chỉnh và nhãn seed trong zip ledger và classify); `YofinaAgent` qua `scripts/agent_deploy.py` (5 tool và 5 policy) -> Runtime `yofina_agent` version 14. Frontend không đổi.

### Phase 4 luồng C: sinh lại lộ trình chạy nền — **đã deploy 23/11 tối** (`YofinaTools` từ `main` 15e9bc7)

**Deploy 23/11 khuya (Claude Code)**: `YofinaTools` 4 lần, chỉ đổi code `yofina-roadmap-regen` (schema giữ field `title`, lọc `goals`, bỏ qua `profile.updated` có `onboarding`, log thông điệp lỗi); Runtime `yofina_agent` lên version 17 (`scripts/agent_deploy.py`). Không thêm tài nguyên.

**Deploy 24/11 rạng sáng (Kiro, `main` fa7f8bd)**: `YofinaTools` một lần, chỉ đổi code 6 Lambda (`yofina-ledger` có luật `source_jar_covers` version 2, `yofina-forecast-batch`, `yofina-on-transaction`, `yofina-forecast`, `yofina-classify`, `yofina-roadmap-regen`); `scripts/agent_deploy.py` -> Runtime `yofina_agent` version 18, schema `check_suitability` trên target `planner` có `start_date`; frontend Amplify job 10. Không thêm, xóa hay thay thế tài nguyên; không migration; Aurora `yofina-db` vẫn min 0 / max 2 ACU.

**Deploy 24/11 sáng (Kiro, `main` 32f22f0)**: `scripts/agent_deploy.py` -> Runtime `yofina_agent` version 19 (chip gợi ý khi từ chối ngoài phạm vi); frontend Amplify job 11 (tên hũ trên bước lộ trình). Không deploy `YofinaTools`/`YofinaData`, không migration, không thêm hay xóa tài nguyên.

**Deploy 24/11 sáng muộn (Kiro, `main` d0e4856)**: `YofinaTools` một lần, chỉ đổi code `yofina-roadmap-regen` (zip `ROADMAP_BUILD_COMMAND`, dùng chung mã agent); `scripts/agent_deploy.py` -> Runtime `yofina_agent` version 20 (lộ trình trong chat đủ giai đoạn, notice bản đề xuất bị thay); frontend Amplify job 12. Không migration (0053 chưa chạy), không thêm hay xóa tài nguyên.

Thuộc stack `YofinaTools` (construct `RoadmapRegen`, `infra-cdk/lib/roadmap-regen.ts`). Mã ở `pipelines/roadmap/`. Đã tạo trên AWS ngày 23/11 tối (deploy `YofinaTools` từ `main` 15e9bc7). Không có thứ nào tính tiền theo giờ.

| Tên | Loại | Phase | Tính tiền khi nhàn rỗi | Ghi chú |
|---|---|---|---|---|
| `yofina-roadmap-regen` | Lambda (Python 3.13, arm64, ngoài VPC, 1.024 MB, timeout 300 s) + IAM role + log group `/aws/lambda/yofina-roadmap-regen` | 4 | Không | Chạy lõi Roadmap agent, cập nhật `roadmap_jobs`. Zip `roadmap-arm64` (13,1 MB nén, 41 MB giải nén; có `strands-agents`). IAM: Data API (ExecuteStatement, BeginTransaction, CommitTransaction, RollbackTransaction) và secret `yofina-db-app`, `lambda:InvokeFunction` CHỈ trên `yofina-ledger` và `yofina-forecast`, Bedrock mẫu 3 phần global cho model của vai `planner` (Sonnet 4.6, Kimi K3), `dynamodb:UpdateItem` trên `yofina-usage`, SSM đọc `/yofina/llm*`, `/yofina/db_*`. Không có `events:PutEvents` (mã không phát sự kiện) |
| `yofina-roadmap-events` | SQS (visibility 1.800 s, giữ 4 ngày, SSE-SQS, `enforceSSL`) | 4 | Không | Event source cho `yofina-roadmap-regen`: lô 1, `ReportBatchItemFailures`, `maxConcurrency` 2. Queue policy cho `events.amazonaws.com` theo ARN từng rule |
| `yofina-roadmap-events-dlq` | SQS (giữ 14 ngày) | 4 | Không | Sau 10 lần giao không thành (`JobBusy` cũng tốn lượt; mỗi lần cách 30 phút) |
| `yofina-roadmap-roadmap-regeneration-requested`, `yofina-roadmap-behavior-changed`, `yofina-roadmap-profile-updated` | 3 EventBridge rule trên `yofina-bus` | 4 | Không | Lọc `source` + `detail-type`: `yofina.ledger`/`roadmap.regeneration_requested`, `yofina.forecast`/`behavior.changed`, `yofina.ledger`/`profile.updated`; đích `yofina-roadmap-events`, gửi nguyên phong bì |
| `yofina-roadmap-events-dlq-not-empty` | CloudWatch alarm | 4 | Không đáng kể (khoảng 0,10 USD/tháng nếu vượt 10 alarm miễn phí) | -> SNS `yofina-alerts` |

Thứ tự khi deploy: build zip (`pipelines/roadmap/README.md`), `uv run scripts/cdk.py diff YofinaTools`, rồi `deploy YofinaTools`. Không cần đổi `YofinaAgent`.

## Không do CDK tạo

| Tên | Loại | Cách tạo | Phase | Tính tiền khi nhàn rỗi | Ghi chú |
|---|---|---|---|---|---|
| `yofina-demo-accounts` | Secrets Manager | `scripts/create_demo_users.py` | 1 | Có (0,40 USD/tháng) | JSON mật khẩu của 6 tài khoản demo (`minh`, `lan`, `khoa`, `giamkhao1`–`3`); 6 user tương ứng trong `yofina-users` |
| `persona-minh`, `persona-lan`, `persona-khoa` | Cognito group (trong `yofina-users`) | `scripts/seed_demo.py` (boto3), 2026-11-21 | 1 | Không | Mỗi tài khoản demo thuộc đúng một nhóm theo `data/personas/accounts.json`; `giamkhao1`–`3` ở `persona-minh`. Claim `cognito:groups` của access token cho `POST /demo/reset` biết persona nào cần sinh lại. Không có nhóm thì đặt lại bị từ chối (403) |
| `/yofina/agent/zip-key` | SSM Parameter (String) | `scripts/agent_deploy.py` (boto3), 2026-11-22 | 1 | Không | Khóa S3 (`builds/agent-<hash>.zip`) của zip agent hiện hành; stack `YofinaAgent` đọc khi deploy nên mỗi mã mới tạo version Runtime mới. Đặt ngoài CDK vì nó là đầu vào của CDK |
| `builds/agent-<hash>.zip` | Đối tượng S3 trong bucket artifact | `scripts/agent_deploy.py`, 2026-11-22 | 1 | Không (vài xu) | Zip agent ARM64 (khoảng 31 MB); vòng đời `builds/` xóa sau 90 ngày |
| `/yofina/alert-email` | SSM Parameter (SecureString) | CLI, 2026-11-21 | 1 | Không | Email nhận cảnh báo ngân sách; chỉ `scripts/cdk.py` đọc; không ghi vào repo |
| `yofina-deployer` | IAM user (không access key) | CLI bằng phiên root, 2026-11-21 | 1 | Không | Gắn `AdministratorAccess` và inline policy `yofina-deny-jars-dev` (Deny RDS, Data API, Cognito, CloudFormation lên tài nguyên `jars-dev*` / stack `Jars*`). Chưa dùng: phase 1 deploy bằng phiên root của CLI (quyết định chủ dự án 2026-11-21) |

Có sẵn trong tài khoản, không do dự án tạo: stack `CDKToolkit` (bootstrap CDK, qualifier mặc định, version 32) ở `ap-southeast-1`. Dự án **dùng lại, không chạy lại bootstrap và không sửa**. Các stack `Jars*` thuộc dự án khác, không đụng.

## Tài nguyên thử tạm (đã tạo và đã xóa, 2026-11-22)

Các phép thử của [spike-vertical-slice.md](research/spike-vertical-slice.md) dựng tạm rồi xóa ngay sau khi thử (tag `project=yofina`, `purpose=probe-temporary`); không còn trong tài khoản.

| Tên | Loại | Dùng để | Trạng thái |
|---|---|---|---|
| `yofina-probe-gw`, `yofina_probe_engine`, 1 target, 1 policy, role `yofina-probe-gateway` | Gateway, policy engine, policy, IAM role | Thử Cedar với `user_id` tùy chọn khi không có interceptor | Đã xóa (script tự dọn) |
| `yofina_probe` (Runtime V1), role `yofina-probe-runtime`, app client `yofina-probe` (access token 5 phút) trong `yofina-users`, `tmp/probe-agent.zip` và `tmp/probe-interrupt/*` trong bucket artifact | AgentCore Runtime, IAM role, Cognito app client, S3 | Thử interrupt/resume AG-UI với session manager S3 và token hết hạn giữa luồng SSE (tạm thêm client thử vào `allowedClients` của Gateway thật rồi khôi phục) | Đã xóa bằng `spikes/vertical-slice/probe_runtime.py down` |

