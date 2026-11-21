# infra-cdk/

Hạ tầng dạng code bằng AWS CDK (TypeScript). Region `ap-southeast-1`, đặt tường minh ở `env`. Không Docker. Không NAT Gateway, không VPC endpoint.

- Proposal: §8 (kiến trúc), §14 (hạ tầng dạng code). Tự viết CDK theo tài liệu chính thức; `infra-cdk/` của FAST chỉ để tham khảo, không kéo về.
- Danh sách tài nguyên đã tạo: [../docs/aws-resources.md](../docs/aws-resources.md). Kế hoạch: [../docs/plan/phases/phase-1-nen-va-lat-doc.md](../docs/plan/phases/phase-1-nen-va-lat-doc.md).
- Đã dựng thử bằng CLI/boto3: Runtime zip + V2, Gateway + interceptor + Cedar, Aurora Data API (xem `docs/research/spike-*.md`); bước ghép thật: [spike-vertical-slice.md](../docs/research/spike-vertical-slice.md).

## Các stack (phase 1)

| Stack | Nội dung | Ghi chú |
|---|---|---|
| `YofinaFoundation` | Bucket S3 artifact, SNS `yofina-alerts`, AWS Budgets `yofina-monthly`, DynamoDB `yofina-confirm-jti` và `yofina-usage`, secret HMAC `yofina-confirm-hmac` | termination protection |
| `YofinaData` | VPC chỉ subnet isolated, Aurora PostgreSQL 17.x Serverless v2 (Data API, 0,5 đến 2 ACU), secret master `yofina-db-master`, secret role `yofina-db-app`, Lambda `yofina-migrator` | termination protection + deletion protection cluster |
| `YofinaIdentity` | Cognito `yofina-users` (tắt tự đăng ký, đăng nhập email), app client `yofina-web` (SRP, không secret), nhóm `ops` | termination protection |
| `YofinaFrontend` | Amplify Hosting `yofina-web`, branch `main`, deploy thủ công bằng zip, rewrite SPA | |
| `YofinaTools` | Lambda `yofina-ledger` (một mã, hai đường vào: Gateway và HTTP API) và HTTP API `yofina-api` (JWT authorizer Cognito, CORS cho Amplify và localhost, 6 route: `/jars`, `/confirmations`, `/actions`, `/demo/reset`, `/conversations`, `/conversations/{conversation_id}`) | cần zip ở `build/lambda/ledger-arm64.zip` (xem dưới); đọc giá trị của stack khác từ SSM lúc deploy |
| `YofinaAgent` | Gateway MCP `yofina-gateway` (JWT authorizer, interceptor `yofina-gw-interceptor`, policy engine Cedar một policy mỗi tool, target `ledger` với schema từ `contracts/tools/ledger.json`) và AgentCore Runtime `yofina_agent` (CodeZip ARM64, V2, AG-UI) cùng vai IAM của Gateway và Runtime | L1 (`Cfn*` của `aws-cdk-lib/aws-bedrockagentcore`; chưa dùng L2). Cần khóa zip ở SSM `/yofina/agent/zip-key` (`scripts/agent_deploy.py` ghi); đọc `YofinaTools`, `YofinaIdentity`, `YofinaFoundation` qua SSM |

Stack của các phase sau thêm vào `bin/yofina.ts`. Mỗi stack ghi giá trị luồng khác cần vào SSM `/yofina/...` (xem bên dưới), nên stack sau đọc SSM hoặc nhận prop, không dùng `Fn::ImportValue` cứng.

## Cấu hình

Mặc định ở [config/config.ts](config/config.ts); đổi bằng context (`-c khóa=giá trị`) hoặc `cdk.context.json` (không commit):

| Context | Mặc định | Ý nghĩa |
|---|---|---|
| `budgetUsd` | 100 | Ngân sách tháng (USD) |
| `budgetThresholds` | `50,80,100` | Ngưỡng cảnh báo thực tế (%) |
| `budgetScope` | `account` | `account`: cả tài khoản; `tag`: chỉ chi phí gắn tag `project=yofina` (cần bật cost allocation tag `project` ở Billing, có hiệu lực sau khoảng 24 giờ) |
| `alertEmail` | (không) | Email nhận cảnh báo. **Không ghi vào repo**: lưu ở SSM `/yofina/alert-email` (SecureString), `scripts/cdk.py` tự đọc và truyền vào |
| `dbEngineVersion` | `17.11` | Aurora PostgreSQL (dòng 17.x, cần 17.4 trở lên cho Data API) |
| `dbMinAcu` / `dbMaxAcu` | `0.5` / `2` | Giữ min 0,5 ACU: Data API không chờ resume từ 0 ACU (xem spike-aurora-data-api) |
| `accessTokenMinutes` | 60 | Hạn access token Cognito |
| `region` | `ap-southeast-1` | |

Cấu hình riêng của `YofinaTools` (`loadToolsConfig` trong `lib/tools-stack.ts`, đổi bằng `-c`):

| Context | Mặc định | Ý nghĩa |
|---|---|---|
| `ledgerZip` | `../build/lambda/ledger-arm64.zip` | Zip Lambda ledger (tính từ `infra-cdk/`) |
| `ledgerMemoryMb` / `ledgerTimeoutSeconds` | 512 / 30 | |
| `confirmTokenTtlSeconds` | 120 | Hạn token xác nhận, tối đa 120 ([ADR-0002](../docs/decisions/0002-xac-nhan-truoc-khi-ghi.md)) |
| `confirmOfferTtlSeconds` | 600 | Hạn của đề nghị trong khối `confirm` |
| `moveMaxAmountVnd` | 50000000 | Hạn mức một lần chuyển hũ (cùng giá trị với luật Cedar) |
| `transactionsDefaultLimit` / `transactionsMaxLimit` | 20 / 50 | `query_transactions` |
| `appTimezone` / `demoAnchorDate` | `Asia/Ho_Chi_Minh` / `2026-11-21` | Đồng hồ mô phỏng ([ADR-0003](../docs/decisions/0003-dong-ho-mo-phong.md)) |
| `dbResumeMaxWaitSeconds` | 18 | Chờ Aurora dậy trong Lambda (nhỏ hơn timeout) |
| `apiThrottleRate` / `apiThrottleBurst` | 20 / 40 | Giới hạn mặc định của API |
| `extraCorsOrigins` | `http://localhost:5173` | Origin CORS ngoài Amplify (phân cách bằng dấu phẩy) |

Cấu hình riêng của `YofinaAgent` (`loadAgentConfig` trong `lib/agent-stack.ts`, đổi bằng `-c`):

| Context | Mặc định | Ý nghĩa |
|---|---|---|
| `policyMode` | `ENFORCE` | Chế độ policy engine của Gateway: `LOG_ONLY` (chỉ ghi quyết định lên metric `AWS/Bedrock-AgentCore`) hoặc `ENFORCE` |
| `gatewayExceptionLevel` | (rỗng) | `DEBUG`: thông điệp lỗi chi tiết hơn (nêu tên policy khi một `forbid` quyết định); rỗng: mức mặc định của Gateway. Với luật `permit` của Yofina hai mức cho cùng thông điệp từ chối |
| `agentRuntimeName` | `yofina_agent` | Tên Runtime (`[a-zA-Z][a-zA-Z0-9_]*`; đổi tên là thay thế Runtime) |
| `agentZipKeyParam` | `/yofina/agent/zip-key` | Tham số SSM giữ khóa S3 của zip agent hiện hành |
| `agentPlatformVersion` | `V2` | Platform của Runtime |
| `interceptorTimeoutSeconds` | `5` | Timeout Lambda interceptor |

Hạn mức chuyển hũ trong luật Cedar lấy từ `moveMaxAmountVnd` của `YofinaTools` (một giá trị cho cả Lambda và Cedar).

Account lấy từ credential hiện tại (`CDK_DEFAULT_ACCOUNT`, `scripts/cdk.py` đặt sẵn).

## Synth, diff, deploy

Dùng wrapper để account/region đúng và email cảnh báo được đọc từ SSM:

```bash
npm ci --prefix infra-cdk                          # lần đầu (ghim phiên bản trong package.json)
uv run scripts/cdk.py synth --strict
uv run scripts/cdk.py diff
uv run scripts/cdk.py deploy YofinaFoundation --require-approval never
uv run scripts/cdk.py deploy YofinaData YofinaIdentity YofinaFrontend --concurrency 3 --require-approval never
uv run scripts/cdk.py deploy YofinaTools --require-approval never   # sau khi đóng zip Lambda ledger (mục "Đóng gói")
uv run scripts/agent_deploy.py                                       # build agent + upload + deploy YofinaAgent (Gateway, Cedar, Runtime) + chờ READY
uv run scripts/cdk.py deploy YofinaAgent --require-approval never   # chỉ Gateway/Cedar/interceptor khi mã agent không đổi (nhanh, không đụng Runtime)
npm run typecheck --prefix infra-cdk              # kiểm kiểu
```

- CDK đã bootstrap sẵn ở `ap-southeast-1` (stack `CDKToolkit`, qualifier mặc định, version 32); **không chạy `cdk bootstrap`**. Credential hiện tại là root nên CDK dùng thẳng credential (không assume được role bootstrap, thông báo "Proceeding anyway" là bình thường).
- Không đổi ID construct của stack có dữ liệu (`Cluster`, `Users`, `Usage`...): đổi ID là thay thế tài nguyên. Luôn `diff` trước khi deploy.
- Nâng `aws-cdk-lib`: kiểm `BootstrapVersion` tối thiểu trong template (`cdk.out/*.template.json`) không vượt 32.
- Muốn đặt email cảnh báo lần đầu: `aws ssm put-parameter --name /yofina/alert-email --type SecureString --value <email> --region ap-southeast-1`, rồi deploy lại `YofinaFoundation`; subscription SNS ở trạng thái chờ cho tới khi người nhận bấm link xác nhận trong thư.

## Migrator: chạy migration

`db/migrations/*.sql` (tên file bỏ `.sql` là version, chạy theo thứ tự chữ). Lambda `yofina-migrator` chạy bằng secret master qua Data API; nó:

1. tạo role `yofina_app` nếu chưa có (`NOSUPERUSER NOBYPASSRLS`, LOGIN) và đặt mật khẩu từ secret `yofina-db-app`, **trước** khi chạy migration (nên migration có thể `GRANT ... TO yofina_app`). Role đã có thì chỉ đổi mật khẩu rồi kiểm lại thuộc tính;
2. chạy từng file chưa có trong bảng `schema_migrations`, mỗi file một transaction; lỗi thì rollback sạch; file đã chạy mà nội dung đổi thì từ chối (hãy thêm migration mới). Checksum là sha256 của nội dung (CRLF chuẩn hóa thành LF);
3. tách câu lệnh vì Data API không nhận nhiều câu lệnh một lần: theo dòng `-- @@` nếu file có (quy ước của `db/migrations/`, xem `libs/yofina_core/src/yofina_core/migrations.py`), nếu không thì theo dấu `;` (tôn trọng chuỗi, chú thích, `$$...$$`). Tham số có tên `:app_password`, `:app_username` lấy từ secret của role và chỉ gửi cho câu lệnh dùng nó.

Giới hạn của Aurora cần biết khi viết migration: master (`rds_superuser`) **không** chạy được `ALTER ROLE ... NOSUPERUSER` (kể cả để gỡ quyền; `NOBYPASSRLS`, `LOGIN`, `NOCREATEDB`, `SET search_path` thì được). Đặt thuộc tính SUPERUSER chỉ ở `CREATE ROLE`.

```bash
uv run scripts/migrate.py --dry-run     # liệt kê việc chờ chạy
uv run scripts/migrate.py               # chạy thật
uv run scripts/db_check.py              # SELECT 1 bằng secret của yofina_app (không phải master)
uv run scripts/db_check.py "SELECT count(*) FROM jars"
```

Lambda không cần build (chỉ dùng boto3 có sẵn trong runtime); sửa `lambdas/migrator/` rồi deploy lại `YofinaData`. Test bộ tách câu lệnh: `cd infra-cdk/lambdas/migrator && python -m unittest`. Migration thử để kiểm migrator: `infra-cdk/test/migrations*/` (không chạy cùng migration thật).

## Tài khoản demo và mật khẩu

```bash
uv run scripts/create_demo_users.py            # tạo minh, lan, khoa, giamkhao1..3 (email <tên>@demo.yofina.example)
uv run scripts/create_demo_users.py --rotate   # đặt mật khẩu mới
uv run scripts/get_token.py minh --check       # đăng nhập SRP thử, không in token
TOKEN=$(uv run scripts/get_token.py lan)       # access token (60 phút) cho test tích hợp
```

Mật khẩu sinh ngẫu nhiên, nằm trong một secret Secrets Manager `yofina-demo-accounts` (JSON `{"minh": {"email": ..., "password": ...}, ...}`); script không in và không ghi file. Đọc khi cần (đừng dán vào repo, log hay chat):

```bash
aws secretsmanager get-secret-value --secret-id yofina-demo-accounts --region ap-southeast-1 --query SecretString --output text
```

## Frontend và biến môi trường

```bash
uv run scripts/print_env.py frontend --write   # frontend/.env.local (VITE_*, không commit)
uv run scripts/print_env.py python --write     # .env.local ở gốc repo (YOFINA_*, không commit)
uv run scripts/deploy_frontend.py frontend/dist   # zip thư mục build, create-deployment, upload, start-deployment, chờ SUCCEED
```

URL Amplify: `/yofina/frontend/amplify-url`. Trang đang host lúc này là trang thử hạ tầng; luồng E thay bằng app thật.

## Đóng gói Lambda / Runtime không Docker

```bash
uv run scripts/build_lambda.py gateway/tools/ledger --arch arm64 --extra data/personas:personas   # build/lambda/ledger-arm64/ và .zip
uv run scripts/build_lambda.py agent --arch arm64 --no-core
```

Dùng `uv pip install --python-platform aarch64-manylinux2014 --only-binary=:all:` để cài wheel Linux ngay trên Windows, kèm `libs/yofina_core` nếu có. Trong CDK dùng `lambda.Code.fromAsset('<đường dẫn>.zip')`. Chi tiết và giới hạn ở docstring của script.

## Giá trị trong SSM `/yofina/...`

| Khóa | Giá trị |
|---|---|
| `s3/artifact-bucket` | Tên bucket artifact |
| `sns/alert-topic-arn` | SNS cảnh báo |
| `dynamodb/confirm-jti-table` | Khóa `jti` (S), TTL `ttl` |
| `dynamodb/usage-table` | Khóa `day` (S) + `model` (S), thuộc tính `count`, TTL `ttl` |
| `secrets/confirm-hmac-arn` | Secret khóa HMAC (chuỗi thuần) |
| `db/cluster-arn`, `db/name`, `db/app-secret-arn`, `db/migrator-function` | Aurora (Data API) và migrator |
| `auth/user-pool-id`, `auth/client-id`, `auth/discovery-url` | Cognito |
| `frontend/amplify-app-id`, `frontend/amplify-branch`, `frontend/amplify-url` | Amplify |
| `api/url` | URL HTTP API `yofina-api` (không có `/` cuối); `print_env.py` ghi thành `VITE_API_BASE_URL` / `YOFINA_API_URL` |
| `ledger/function-name`, `ledger/function-arn` | Lambda `yofina-ledger` (cho target Gateway của luồng C) |
| `gateway_url`, `gateway/id`, `gateway/arn` | Gateway `yofina-gateway` (URL MCP; `print_env.py python` ghi thành `YOFINA_GATEWAY_URL`) |
| `agent/runtime-arn`, `agent/runtime-id`, `agent/runtime-url` | Runtime `yofina_agent`; URL invoke đầy đủ (`.../invocations?qualifier=DEFAULT`) ghi thành `VITE_AGENT_RUNTIME_URL`; ARN chứa account ID nên `print_env.py frontend` không ghi nó (Vite nhúng mọi `VITE_*` vào bundle) |
| `agent/zip-key` | Khóa S3 của zip agent hiện hành (`builds/agent-<hash>.zip`); `scripts/agent_deploy.py` ghi (ngoài CDK) |
| `alert-email` | Email cảnh báo (SecureString, chỉ `scripts/cdk.py` đọc) |
