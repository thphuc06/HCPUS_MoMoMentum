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
| `YofinaTools` | **Pipeline dự báo (phase 2, luồng C)**: Lambda `yofina-forecast-batch`, `yofina-on-transaction`, `yofina-forecast` (một zip), bảng DynamoDB `yofina-idempotency`, SQS `yofina-forecast-events` + DLQ, rule trên `yofina-bus`, Step Functions `yofina-nightly`, EventBridge Scheduler `yofina-nightly-0200`, ba alarm -> SNS. Cộng: Lambda `yofina-ledger` (một mã, hai đường vào: Gateway và HTTP API), HTTP API `yofina-api` (JWT authorizer Cognito, CORS cho Amplify và localhost, 47 route: 42 tới Lambda ledger (`/jars`, `/jars/{jar_code}`, `POST /jars/split-proposal`, `/overview`, `/profile`, `/transactions`, `/tx-types`, `/payees`, `/obligations`, `/credit-line`, `/salary-events`, `/jar-templates`, `/forecasts/{jar_code}`, `/confirmations`, `/confirmations/cancel`, `/actions`, `/demo/reset`, `/conversations`, `/conversations/{conversation_id}`, `/traces/{trace_id}`, `/feedback`, 8 route `/roadmap*`, 2 route `/review*`, 3 route `/ops/*`, 5 route `/memory*` và `/me/delete-data*`, 2 route `/nudges/*`, `/cashflow`) và 5 tới `yofina-forecast` (`/affordability`, `/resilience*`, `/profile/behavior`); `tests/unit/test_rest_routes_cdk.py` đỏ khi `contracts/rest/openapi.yaml` có route mà CDK hoặc `rest_api.py` không nối), EventBridge bus `yofina-bus` và alarm `yofina-ledger-event-publish-failed` | cần zip ở `build/lambda/ledger-arm64.zip` (xem dưới); đọc giá trị của stack khác từ SSM lúc deploy |
| `YofinaAgent` | Gateway MCP `yofina-gateway` (JWT authorizer, interceptor `yofina-gw-interceptor`, policy engine Cedar một policy mỗi tool, target `ledger` với schema từ `contracts/tools/ledger.json` và target `forecast` (Lambda `yofina-forecast`, schema từ `contracts/tools/forecast.json`, policy `get_forecast.cedar`)) và AgentCore Runtime `yofina_agent` (CodeZip ARM64, V2, AG-UI) cùng vai IAM của Gateway và Runtime | L1 (`Cfn*` của `aws-cdk-lib/aws-bedrockagentcore`; chưa dùng L2). Cần khóa zip ở SSM `/yofina/agent/zip-key` (`scripts/agent_deploy.py` ghi); đọc `YofinaTools`, `YofinaIdentity`, `YofinaFoundation` qua SSM |

| `YofinaIngest` | **F6 nạp dữ liệu từ ảnh và CSV (phase 5)**: bucket `yofina-ingest-<account>-<region>`, SQS `yofina-ingest-jobs` + DLQ, alarm `yofina-ingest-jobs-dlq-not-empty`, Lambda `yofina-ingest-api` và `yofina-ingest` (worker), JWT authorizer `yofina-cognito-ingest` và 6 route `/ingest/*` gắn vào HTTP API `yofina-api` có sẵn | **chưa deploy**. Cần zip `build/lambda/ingest-arm64.zip`; đọc mọi giá trị stack khác từ SSM; không sửa `YofinaTools`. Chi tiết ở mục "Stack YofinaIngest" dưới |

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
| `dbMinAcu` / `dbMaxAcu` / `dbAutoPauseSeconds` | `0` / `2` / `600` | Mặc định cho Aurora tự ngủ để đỡ tiền lúc dev; code đã retry `DatabaseResumingException` (lần gọi đầu sau khi ngủ chậm 15–20 giây, xem spike-aurora-data-api). Buổi demo/chấm điểm: `-c dbMinAcu=0.5` |
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
| `transactionsDefaultLimit` / `transactionsMaxLimit` | 20 / 50 | `query_transactions` và `GET /transactions` |
| `transactionMaxAmountVnd` | 50000000 | Hạn mức một giao dịch `record_transaction` (cùng giá trị với luật Cedar) |
| `salaryDeviationAskPercent` | 10 | Số nhận lệch lương đã khai quá ngưỡng này (phần trăm) thì hỏi có cập nhật lương không |
| `defaultCreditLimitVnd` | 3000000 | Hạn mức Trả sau (mô phỏng) của tài khoản mới (VND) |
| `defaultDisplayName` | `Bạn` | Tên hiển thị khi tài khoản chưa có hồ sơ và JWT không có tên (không dùng email) |
| `forecastFreshnessSeconds` | 3600 | Quá hạn này thì dự báo bị đánh dấu `stale` |
| `proactiveObligationDays` | 3 | Thẻ chủ động báo nghĩa vụ đến hạn trong N ngày tới |
| `referenceCacheSeconds` | 300 | Giữ bảng tra (loại giao dịch, biểu phí, hũ mẫu) trong bộ nhớ Lambda |
| `appTimezone` / `demoAnchorDate` | `Asia/Ho_Chi_Minh` / `2026-11-21` | Đồng hồ mô phỏng ([ADR-0003](../docs/decisions/0003-dong-ho-mo-phong.md)) |
| `dbResumeMaxWaitSeconds` | 18 | Chờ Aurora dậy trong Lambda (nhỏ hơn timeout) |
| `apiThrottleRate` / `apiThrottleBurst` | 20 / 40 | Giới hạn mặc định của API |
| `extraCorsOrigins` | `http://localhost:5173` | Origin CORS ngoài Amplify (phân cách bằng dấu phẩy) |
| `onboardingJarLayout` | `catalogue` | Công tắc quay lui bộ hũ của tài khoản mới (#39), thành `YOFINA_ONBOARDING_JAR_LAYOUT` của Lambda ledger: `catalogue` là bộ hũ `is_default` của `jar_templates` (ba hũ sau 0059), `legacy` là bộ bảy hũ cũ. Quay lui: `uv run scripts/cdk.py deploy YofinaTools --require-approval never -c onboardingJarLayout=legacy`; chỉ đổi lần tạo ví sau, ví đã tạo và reset demo giữ nguyên. Lần deploy `YofinaTools` sau phải giữ `-c onboardingJarLayout=legacy` (hoặc đặt trong `cdk.context.json`), không thì về `catalogue`. Giá trị khác bị từ chối lúc synth |

Cấu hình pipeline dự báo (`loadForecastConfig` trong `lib/forecast-pipeline.ts`, đổi bằng `-c`; truyền vào Lambda dưới dạng `YOFINA_FORECAST_*`, đọc ở `pipelines/forecast/yofina_forecast/settings.py`):

| Context | Mặc định | Ý nghĩa |
|---|---|---|
| `forecastZip` | `../build/lambda/forecast-arm64.zip` | Zip dùng chung của ba Lambda (đóng bằng `build_lambda.py pipelines/forecast ... --slim`) |
| `forecastMemoryMb` | 1769 | Chọn theo số đo thật: 1.024 MB chậm hơn 50%, 3.008 MB không nhanh hơn ([pipelines/forecast/README.md](../pipelines/forecast/README.md#số-đo-lambda-arm64-aurora-thật)) |
| `forecastBatchTimeoutSeconds` / `forecastEventTimeoutSeconds` / `forecastToolTimeoutSeconds` | 120 / 90 / 60 | Timeout ba Lambda (visibility timeout SQS bằng 6 lần timeout consumer) |
| `forecastHorizonDays`, `forecastHistoryWindowDays` | 30, 330 | Số ngày dự báo; số ngày lịch sử tối đa đọc |
| `forecastNPathsFull` / `forecastNPathsFast` | 10000 / 5000 | Số đường Monte Carlo của chạy đầy đủ (đêm, đặt lại, đọc cũ) và chỉnh nhanh (sự kiện) |
| `forecastColdStartMinDays`, `forecastAciGamma`, `forecastCoverageTarget` | 21, 0.01, 0.8 | Ngưỡng ước lượng ban đầu; tốc độ ACI; độ phủ khoảng danh định |
| `forecastShortThreshold` / `forecastTightThreshold` | 0.5 / 0.2 | Ngưỡng xác suất hụt cho hụt / sát |
| `forecastBandHighMinDays`, `forecastBandHighMinCoverage`, `forecastBandMediumMinDays` | 60, 0.7, 21 | Ngưỡng nhóm tin cậy Cao / Vừa |
| `forecastProbabilityEnabled` | true | Công tắc xác suất: `false` thì chỉ hiện nhóm Cao/Vừa/Thấp bất kể kết quả hiệu chỉnh |
| `forecastKeepRuns`, `forecastFastMaxAgeSeconds`, `forecastRecomputeGuardSeconds` | 6, 86400, 20 | Số lần chạy giữ lại; tuổi tối đa của lần chạy trước để dùng đường nhanh; khoảng bảo vệ chống bão tính lại |
| `forecastIdempotencyTtlSeconds`, `forecastIdempotencyLeaseSeconds` | 259200, 120 | TTL của bản ghi `event_id`; thời hạn khóa thuê của một sự kiện đang xử lý |
| `forecastNightlyConcurrency`, `forecastNightlyHour`, `forecastNightlyMinute`, `forecastNightlyMaxUsers` | 3, 2, 0, 200 | Số người dùng chạy song song trong Map; giờ chạy (múi giờ `appTimezone`); số người dùng tối đa |
| `forecastEventMaxConcurrency`, `forecastEventBatchSize`, `forecastEventMaxReceiveCount` | 5, 10, 3 | Số consumer song song; cỡ lô SQS; số lần giao trước khi vào DLQ |

Cấu hình riêng của `YofinaAgent` (`loadAgentConfig` trong `lib/agent-stack.ts`, đổi bằng `-c`):

| Context | Mặc định | Ý nghĩa |
|---|---|---|
| `policyMode` | `ENFORCE` | Chế độ policy engine của Gateway: `LOG_ONLY` (chỉ ghi quyết định lên metric `AWS/Bedrock-AgentCore`) hoặc `ENFORCE` |
| `gatewayExceptionLevel` | (rỗng) | `DEBUG`: thông điệp lỗi chi tiết hơn (nêu tên policy khi một `forbid` quyết định); rỗng: mức mặc định của Gateway. Với luật `permit` của Yofina hai mức cho cùng thông điệp từ chối |
| `agentRuntimeName` | `yofina_agent` | Tên Runtime (`[a-zA-Z][a-zA-Z0-9_]*`; đổi tên là thay thế Runtime) |
| `agentZipKeyParam` | `/yofina/agent/zip-key` | Tham số SSM giữ khóa S3 của zip agent hiện hành |
| `agentPlatformVersion` | `V2` | Platform của Runtime |
| `interceptorTimeoutSeconds` | `5` | Timeout Lambda interceptor |

Cấu hình riêng của `YofinaIngest` (`loadIngestConfig` trong `lib/ingest-stack.ts`, đổi bằng `-c`). TTL token, offer TTL, chờ Aurora, đồng hồ mô phỏng và hạn mức KHÔNG có khóa riêng: lấy từ cấu hình của `YofinaTools` (cùng context) để ingest và ledger không lệch nhau.

| Context | Mặc định | Ý nghĩa |
|---|---|---|
| `ingestZip` | `../build/lambda/ingest-arm64.zip` | Zip chung của hai Lambda (lệnh đóng ở mục "Stack YofinaIngest"). Thiếu zip thì stack này báo lỗi lúc synth (stack khác vẫn synth được) |
| `ingestApiMemoryMb` / `ingestApiTimeoutSeconds` | 512 / 30 | `yofina-ingest-api` (timeout integration HTTP API tối đa 30 s) |
| `ingestWorkerMemoryMb` / `ingestWorkerTimeoutSeconds` | 1024 / 120 | Worker: Converse với ảnh 20–40 s, Aurora dậy 15–20 s. Visibility timeout của hàng đợi = 6 lần giá trị này |
| `ingestWorkerMaxConcurrency` | 2 | `maxConcurrency` của SQS event source (tối thiểu 2 theo AWS); chặn số worker song song để không vượt rpm của Claude |
| `ingestWorkerReservedConcurrency` | 0 (không đặt) | Tài khoản đang có quota 10 lần chạy đồng thời, Lambda bắt giữ tối thiểu 10 unreserved, nên đặt reserved concurrency bất kỳ sẽ làm deploy lỗi. Nâng quota rồi mới đặt (ví dụ 2) |
| `ingestMaxReceiveCount` | 3 | Số lần giao trước khi vào DLQ |
| `ingestObjectExpirationDays` / `ingestAbortMultipartDays` | 30 / 1 | Vòng đời bucket |
| `ingestUploadPrefix` | `u/` | Tiền tố khóa tệp người dùng; chỉ tiền tố này kích hoạt worker và nằm trong quyền S3 |
| `ingestLlmRoles` | `ingest,ingest_columns` | Vai trong `llm_defaults.json` được cấp quyền Bedrock cho WORKER (đọc lúc synth): `ingest` (đọc ảnh: Sonnet 4.6, dự phòng Kimi K3) và `ingest_columns` (ánh xạ cột và gắn nhãn CSV: Nova 2 Lite, dự phòng Haiku 4.5). Vai chưa có thì bỏ qua kèm cảnh báo `yofina:ingest:llm-role-missing:<vai>`; không vai nào có thì stack báo lỗi |
| `forecastHistoryWindowDays` | 330 | CÙNG context với pipeline dự báo (`YOFINA_FORECAST_HISTORY_WINDOW_DAYS`): cửa sổ tính độ phủ dữ liệu của ingest, để `coverage_change` khớp dải độ phủ của dự báo |
| `ingestLlmDefaults` | `../libs/yofina_core/src/yofina_core/llm_defaults.json` | File cấu hình model đọc lúc synth (test trỏ sang file giả) |

### Stack YofinaIngest

- **API id**: `/yofina/api/url` đọc bằng `valueForStringParameter` (tham số CFN kiểu `AWS::SSM::Parameter::Value<String>`, là `Ref` nên dùng được trong `Fn::Split`), rồi `Fn::Select(0, Split('.', Select(2, Split('/', url))))`.
- **Authorizer** (giữ authorizer riêng, có chủ ý): authorizer `yofina-cognito` của YofinaTools không có id ở SSM, và custom resource `GetAuthorizers` chỉ lấy được theo chỉ số mảng (không lọc theo tên), còn sửa YofinaTools để ghi id ra SSM thì nhánh này không được deploy. Stack này tạo authorizer RIÊNG `yofina-cognito-ingest` trên cùng API, cùng issuer (`https://cognito-idp.<region>.amazonaws.com/<user pool>`) và audience (app client), identity source `$request.header.Authorization`, nên token nào qua được route ledger thì qua được route ingest. Stack tự chứa: xóa stack thì authorizer và route mất theo; API và route của ledger không bị ảnh hưởng.
- **Route** (đều JWT, integration `AWS_PROXY` payload 2.0 tới `yofina-ingest-api`; nguồn là `INGEST_ROUTES` trong `lib/ingest-stack.ts`, khớp `contracts/rest/openapi.yaml` của luồng backend):

  | Route | Việc |
  |---|---|
  | `POST /ingest/uploads` | xin presigned POST, ghi consent, tạo job |
  | `GET /ingest/jobs` | job gần đây |
  | `GET /ingest/jobs/{job_id}` | tiến độ và dòng đề xuất của một job |
  | `POST /ingest/rows/{row_id}/jar` | đổi hũ đề xuất của một dòng |
  | `POST /ingest/confirmations` | cấp token xác nhận cho tool `confirm_rows` |
  | `POST /ingest/actions` | chốt dòng bằng token (`confirm_rows`) |

  Quyền gọi Lambda: `apigateway.amazonaws.com`, `sourceArn` `arn:aws:execute-api:<region>:<account>:<apiId>/*/*/ingest/*`. Stage `$default` của API có auto-deploy nên route có hiệu lực ngay.
- **Xác nhận `confirm_rows`**: Lambda `yofina-ledger` đã deploy không biết `confirm_rows`, và nhánh này không deploy YofinaTools, nên `yofina-ingest-api` tự cấp và kiểm token bằng CÙNG `yofina_core.confirm` (cùng secret HMAC `secrets/confirm-hmac-arn`, cùng bảng jti `dynamodb/confirm-jti-table`, cùng TTL lấy từ cấu hình YofinaTools): đúng cơ chế ADR-0002, chỉ khác route (`/ingest/confirmations`, `/ingest/actions` thay cho route của ledger).
- **CORS**: CORS preflight của `yofina-api` đặt ở YofinaTools là `GET, POST, OPTIONS`. Vì vậy mọi route ingest chỉ dùng GET hoặc POST (đổi hũ là `POST /ingest/rows/{row_id}/jar`, không PATCH); test chặn route có method khác. Stack này không sửa CORS của API.
- **Bucket**: chặn public, `enforceSSL`, SSE-S3, không versioning, `BucketOwnerEnforced`, xóa object sau 30 ngày, hủy multipart dở sau 1 ngày, CORS chỉ `POST` cho URL Amplify (SSM `frontend/amplify-url`, đọc lúc deploy, không gõ cứng) + `extraCorsOrigins` (mặc định `http://localhost:5173`; header `content-type`, lộ `ETag`, `Location`). RETAIN như bucket artifact (dữ liệu người dùng; vòng đời đã dọn object). ObjectCreated `u/` -> SQS; queue policy cho `s3.amazonaws.com` có `aws:SourceArn` (bucket) và `aws:SourceAccount`.
- **Upload**: backend ký presigned POST (`generate_presigned_post`) với khóa `u/{user_id}/{job_id}` (không có tên tệp gốc) và điều kiện `["content-length-range", 1, <trần>]` cùng `{"Content-Type": ...}` (hoặc `starts-with`); S3 kiểm các điều kiện này khi nhận form. Role API chỉ có `s3:PutObject` với điều kiện `s3:authType = POST`, nên quyền này không dùng được cho PUT trực tiếp hay presigned PUT.
- **Hàng đợi và worker**: SQS `yofina-ingest-jobs` (SSE-SQS, visibility = 6 × timeout worker = 720 s, `maxReceiveCount` 3) -> DLQ `yofina-ingest-jobs-dlq` (14 ngày) -> alarm `yofina-ingest-jobs-dlq-not-empty` gửi SNS `yofina-alerts`. Event source: `batchSize` 1, `reportBatchItemFailures`, `maxConcurrency` 2 (trần chạy song song của worker, vì Claude chỉ khoảng 8–10 request/phút; reserved concurrency mặc định không đặt, xem bảng context).
- **Bedrock** (chỉ worker; API không gọi model): mỗi model `global.*` của các vai trong `ingestLlmRoles` được cấp theo mẫu 3 phần của tài liệu global cross-Region inference: (1) `inference-profile/global.<model>` ở region gọi, điều kiện `aws:RequestedRegion` = region; (2) `arn:aws:bedrock:<region>::foundation-model/<model>`, điều kiện region + `bedrock:InferenceProfileArn` = profile đó; (3) `arn:aws:bedrock:::foundation-model/<model>` (không region), điều kiện `aws:RequestedRegion` = `unspecified` + `bedrock:InferenceProfileArn`. Model không có tiền tố `global.` được cấp `foundation-model` ở region gọi. Converse dùng quyền `bedrock:InvokeModel`. Với `llm_defaults.json` hiện tại: Sonnet 4.6, Kimi K3 (vai `ingest`), Nova 2 Lite, Haiku 4.5 (vai `ingest_columns`); test kiểm vai embedding và model ngoài hai vai KHÔNG được cấp.
- **IAM theo từng Lambda** (mỗi Lambda một role, không `*`): cả hai có Data API trên cluster và `GetSecretValue` CHỈ trên secret `yofina-db-app` (không master). API thêm: khóa HMAC, `dynamodb:PutItem` trên bảng jti, `s3:PutObject` trên `u/*` CHỈ khi `s3:authType = POST`, `lambda:InvokeFunction` CHỈ trên `yofina-forecast-batch` (tính lại dự báo sau khi chốt). Worker thêm: Bedrock, `dynamodb:UpdateItem` trên `yofina-usage`, `s3:GetObject` và `s3:DeleteObject` trên `u/*` (xóa tệp gốc ngay sau khi đọc). Không có `events:PutEvents`: ingest không phát sự kiện lên `yofina-bus` (sau khi chốt, API gọi thẳng tính lại dự báo đầy đủ).

Đóng zip (một zip cho cả hai Lambda; `--extra` lặp được, đường dẫn tính từ gốc repo, `NGUỒN:ĐÍCH` chép thư mục vào gốc zip; `yofina_core` tự kèm):

```bash
uv run scripts/build_lambda.py gateway/tools/ingest --arch arm64 --name ingest --extra pipelines/ingest/yofina_ingest:yofina_ingest --extra gateway/tools/ledger/yofina_ledger:yofina_ledger --extra pipelines/classify/yofina_classify:yofina_classify --extra db/seed:seed
# -> build/lambda/ingest-arm64.zip; handler: handler_api.handler (REST), handler_worker.handler (SQS). Lệnh chuẩn là INGEST_BUILD_COMMAND trong lib/ingest-stack.ts: thiếu yofina_classify thì Lambda API lỗi ImportModuleError (500) sau deploy
```

Synth riêng: `uv run scripts/cdk.py synth YofinaIngest`. Nếu app đầy đủ dừng vì thiếu luật Cedar của `YofinaAgent` (nhánh phase 3 chưa ghép), synth riêng stack này bằng một entry chỉ dựng `IngestStack` (`--app "npx tsx bin/<entry>.ts"`). App dựng mọi stack, nên synth cần cả zip ledger, forecast và các luật Cedar của YofinaAgent; thiếu chúng thì app dừng trước khi tới stack này. Stack ingest thiếu zip của chính nó thì KHÔNG ném lỗi lúc dựng mà gắn lỗi (annotation) vào `YofinaIngest`: CLI từ chối synth/deploy stack này, stack khác vẫn synth được.

Tài liệu AWS đã đối chiếu:
- Presigned POST, điều kiện `content-length-range`, `Content-Type`: [Creating a POST policy](https://docs.aws.amazon.com/AmazonS3/latest/developerguide/sigv4-HTTPPOSTConstructPolicy.html), [Browser-based uploads using POST](https://docs.aws.amazon.com/AmazonS3/latest/developerguide/sigv4-UsingHTTPPOST.html); khóa `s3:authType` (giá trị `REST-HEADER`, `REST-QUERY-STRING`, `POST`): [SigV4 authentication-specific policy keys](https://docs.aws.amazon.com/AmazonS3/latest/developerguide/bucket-policy-s3-sigv4-conditions.html).
- S3 -> SQS và queue policy: [Granting permissions to publish event notification messages to a destination](https://docs.aws.amazon.com/AmazonS3/latest/userguide/grant-destinations-permissions-to-s3.html), [Walkthrough: configuring a bucket for notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/ways-to-add-notification-config-to-bucket.html).
- Lambda SQS event source (visibility ≥ 6 × timeout, `maxConcurrency` tối thiểu 2, `ReportBatchItemFailures`): [Creating and configuring an SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html), [Handling errors for an SQS event source](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html).
- Bedrock global cross-Region inference (policy 3 phần, `aws:RequestedRegion = unspecified`): [Global cross-Region inference](https://docs.aws.amazon.com/bedrock/latest/userguide/global-cross-region-inference.html).

Biến môi trường (cả hai Lambda, cùng giá trị):

| Biến | Nguồn |
|---|---|
| `YOFINA_REGION`, `YOFINA_LOG_LEVEL`, `YOFINA_SSM_PREFIX` (`/yofina`) | cấu hình app |
| `YOFINA_DB_CLUSTER_ARN`, `YOFINA_DB_NAME` | SSM `db/cluster-arn`, `db/name` |
| `YOFINA_DB_SECRET_ARN` và `YOFINA_DB_APP_SECRET_ARN` (cùng secret `yofina_app`; `yofina_core.db` đọc tên thứ hai) | SSM `db/app-secret-arn` |
| `YOFINA_DB_RESUME_MAX_WAIT_SECONDS` | `dbResumeMaxWaitSeconds` (YofinaTools) |
| `YOFINA_INGEST_BUCKET` | bucket của stack |
| `YOFINA_CONFIRM_HMAC_SECRET_ARN`, `YOFINA_CONFIRM_JTI_TABLE` | SSM `secrets/confirm-hmac-arn`, `dynamodb/confirm-jti-table` |
| `YOFINA_CONFIRM_TOKEN_TTL_SECONDS`, `YOFINA_CONFIRM_TOKEN_MAX_TTL_SECONDS` | `confirmTokenTtlSeconds` (cả hai, như ledger) |
| `YOFINA_CONFIRM_OFFER_TTL_SECONDS` | `confirmOfferTtlSeconds` |
| `YOFINA_FORECAST_BATCH_FUNCTION` và `YOFINA_FORECAST_FUNCTION_NAME` (tên ledger đọc), `YOFINA_FORECAST_SYNC_TIMEOUT_SECONDS` (timeout - 8) | SSM `forecast/batch-function-name` |
| `YOFINA_EVENT_BUS_NAME` | SSM `events/bus-name` |
| `YOFINA_APP_TIMEZONE`, `YOFINA_DEMO_ANCHOR_DATE` | `appTimezone`, `demoAnchorDate` |
| `YOFINA_LLM_USAGE_TABLE` và `YOFINA_USAGE_TABLE` (tên `yofina_core.llm` đọc) | SSM `dynamodb/usage-table` |
| `YOFINA_MOVE_MAX_AMOUNT_VND`, `YOFINA_TRANSACTIONS_DEFAULT_LIMIT`, `YOFINA_TRANSACTIONS_MAX_LIMIT`, `YOFINA_TRANSACTION_MAX_AMOUNT_VND`, `YOFINA_SALARY_DEVIATION_ASK_PERCENT`, `YOFINA_DEFAULT_CREDIT_LIMIT_VND`, `YOFINA_DEFAULT_DISPLAY_NAME`, `YOFINA_FORECAST_FRESHNESS_SECONDS`, `YOFINA_PROACTIVE_OBLIGATION_DAYS`, `YOFINA_REFERENCE_CACHE_SECONDS` | cùng giá trị với `yofina-ledger` (khi mã ingest dùng `LedgerSettings` để chốt dòng) |

Khóa `ingest_*` của `IngestSettings` (`yofina_core.ingest`) không đặt trong env: dùng mặc định trong mã hoặc ghi đè ở SSM `/yofina/ingest_*`.

IAM (mỗi Lambda một role do CDK sinh, cộng `AWSLambdaBasicExecutionRole`):

| Quyền | `yofina-ingest-api` | `yofina-ingest` (worker) |
|---|---|---|
| `rds-data:ExecuteStatement, BatchExecuteStatement, BeginTransaction, CommitTransaction, RollbackTransaction` trên cluster ARN | có | có |
| `secretsmanager:GetSecretValue` | secret `yofina_app` + khóa HMAC | chỉ secret `yofina_app` |
| `bedrock:InvokeModel` (Converse dùng quyền này), mẫu 3 phần của global cross-Region inference cho model của `ingestLlmRoles` (xem mục Bedrock ở trên) | có | có |
| `dynamodb:UpdateItem` trên `yofina-usage` (worker: đếm lượt model; API: đếm lần nạp tệp theo tài khoản, mục "Trần theo tài khoản mỗi ngày") | có | có |
| `ssm:GetParameter, GetParametersByPath` trên `/yofina/llm`, `/yofina/llm/*`, `/yofina/ingest_*`, `/yofina/db_*`, `/yofina/confirm_*`, `/yofina/forecast_*`, `/yofina/dynamodb/usage-table` (khóa tùy chọn vắng phải trả `ParameterNotFound`, không phải `AccessDenied`) | có | có |
| `lambda:InvokeFunction` trên `yofina-forecast-batch` (ARN dựng bằng `formatArn`) | có | có |
| `events:PutEvents` trên `yofina-bus` | có | có |
| `s3:GetObject` (gồm HeadObject) trên `bucket/u/*` | | có |
| `s3:DeleteObject` trên `bucket/u/*` (xóa tệp gốc sau khi đọc, hủy job, đặt lại demo) | có | có |
| `s3:PutObject` trên `bucket/u/*`, điều kiện `s3:authType = POST` (presigned POST được S3 kiểm bằng quyền của role ký) | có | |
| `s3:ListBucket` với điều kiện `s3:prefix` `u/`, `u/*` | có | |
| `dynamodb:PutItem` trên `yofina-confirm-jti` | có | |
| SQS `ReceiveMessage/DeleteMessage/ChangeMessageVisibility/GetQueueAttributes` (event source tự cấp) | | có |

Chạy test của infra: `npm test --prefix infra-cdk` (node:test + `aws-cdk-lib/assertions`, zip rỗng và `llm_defaults.json` giả trong thư mục tạm, không gọi AWS). Test khóa: đúng 6 route, chỉ GET/POST, bucket chặn public + lifecycle 30 ngày, DLQ + alarm, IAM theo tiền tố, mẫu Bedrock 3 phần, không tài nguyên tính tiền theo giờ, tag `project`.

Hạn mức trong luật Cedar lấy từ `moveMaxAmountVnd` và `transactionMaxAmountVnd` của `YofinaTools` (một giá trị cho cả Lambda và Cedar). Target `ledger` lấy schema từ `contracts/tools/ledger.json` (10 tool) và mỗi tool cần một file `gateway/policies/<tool>.cedar` (thiếu thì synth báo lỗi). Đổi schema tool là cập nhật tại chỗ target (không thay thế).

Account lấy từ credential hiện tại (`CDK_DEFAULT_ACCOUNT`, `scripts/cdk.py` đặt sẵn).

## Synth, diff, deploy

Dùng wrapper để account/region đúng và email cảnh báo được đọc từ SSM:

```bash
npm ci --prefix infra-cdk                          # lần đầu (ghim phiên bản trong package.json)
uv run scripts/cdk.py synth --strict
uv run scripts/cdk.py diff
uv run scripts/cdk.py deploy YofinaFoundation --require-approval never
uv run scripts/cdk.py deploy YofinaData YofinaIdentity YofinaFrontend --concurrency 3 --require-approval never
uv run scripts/cdk.py deploy YofinaTools --require-approval never   # sau khi đóng zip Lambda ledger và forecast (mục "Đóng gói")
uv run scripts/cdk.py deploy YofinaIngest --require-approval never  # F6 (chưa deploy): sau khi đóng zip ingest; diff trước
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
uv run scripts/build_lambda.py gateway/tools/ledger --arch arm64 --keep-boto --extra data/personas:personas --extra gateway/tools/planner/yofina_planner:yofina_planner --extra gateway/tools/planner/rules:rules --extra gateway/tools/knowledge/yofina_knowledge:yofina_knowledge --extra gateway/tools/audit/yofina_audit:yofina_audit   # build/lambda/ledger-arm64/ và .zip
uv run scripts/build_lambda.py agent --arch arm64 --no-core
uv run scripts/build_lambda.py pipelines/forecast --arch arm64 --name forecast --slim   --extra ml/yofina_ml:yofina_ml --extra gateway/tools/ledger/yofina_ledger:yofina_ledger --extra gateway/tools/planner/yofina_planner:yofina_planner --extra gateway/tools/planner/rules:rules --extra gateway/tools/knowledge/yofina_knowledge:yofina_knowledge --extra gateway/tools/audit/yofina_audit:yofina_audit   # numpy + scipy: 46 MB nén, 156 MB giải nén
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
| `ledger/function-name`, `ledger/function-arn` | Lambda `yofina-ledger` |
| `forecast/function-name`, `forecast/function-arn` | Lambda `yofina-forecast` (target `forecast` của Gateway) |
| `forecast/batch-function-name`, `forecast/nightly-arn`, `forecast/events-queue-url`, `forecast/idempotency-table` | Lambda batch (ledger gọi để đặt lại và đọc cũ), state machine `yofina-nightly`, hàng đợi sự kiện, bảng idempotency |
| `events/bus-name`, `events/bus-arn` | EventBridge bus `yofina-bus` (sự kiện của ledger; consumer là `yofina-on-transaction` qua SQS; test tích hợp dựng rule tạm trên bus này rồi dọn) |
| `gateway_url`, `gateway/id`, `gateway/arn` | Gateway `yofina-gateway` (URL MCP; `print_env.py python` ghi thành `YOFINA_GATEWAY_URL`) |
| `agent/runtime-arn`, `agent/runtime-id`, `agent/runtime-url` | Runtime `yofina_agent`; URL invoke đầy đủ (`.../invocations?qualifier=DEFAULT`) ghi thành `VITE_AGENT_RUNTIME_URL`; ARN chứa account ID nên `print_env.py frontend` không ghi nó (Vite nhúng mọi `VITE_*` vào bundle) |
| `agent/zip-key` | Khóa S3 của zip agent hiện hành (`builds/agent-<hash>.zip`); `scripts/agent_deploy.py` ghi (ngoài CDK) |
| `ingest/bucket-name`, `ingest/api-function-name`, `ingest/worker-function-name`, `ingest/queue-url` | `YofinaIngest` (chưa deploy): bucket tệp tải lên, hai Lambda, hàng đợi job |
| `quota/chat_turns_per_day`, `quota/uploads_per_day` | Trần theo tài khoản mỗi ngày. Tạo tay, không do CDK; vắng thì dùng mặc định trong mã (mục dưới) |
| `alert-email` | Email cảnh báo (SecureString, chỉ `scripts/cdk.py` đọc) |

## Trần theo tài khoản mỗi ngày (#13)

`yofina_core.quota` giới hạn mỗi tài khoản trong một ngày, để một người không dùng hết trần chung theo model (`/yofina/llm/daily_cap_<vai>`, khác với trần này) của mọi người:

| Khóa SSM (String, số nguyên) | Mặc định trong mã | Tính một lượt khi | Ai đọc | Chạm trần thì |
|---|---|---|---|---|
| `/yofina/quota/chat_turns_per_day` | 100 | mỗi tin nhắn chat (không tính lượt làm nóng `warmup`) | Runtime `yofina_agent` | khối `notice` lỗi mã `DAILY_QUOTA_EXCEEDED`, lượt kết thúc, 0 lời gọi model và tool |
| `/yofina/quota/uploads_per_day` | 20 | mỗi lần `POST /ingest/uploads` cấp URL (yêu cầu hỏng, chưa đồng ý thì không tính) | Lambda `yofina-ingest-api` | HTTP 429 `DAILY_QUOTA_EXCEEDED`, không tạo job, không ký URL |

Các màn số liệu (REST đọc của ledger, `GET /ingest/*`) không bị ảnh hưởng.

- **Thứ tự nguồn**: biến môi trường `YOFINA_QUOTA_CHAT_TURNS_PER_DAY` / `YOFINA_QUOTA_UPLOADS_PER_DAY` (đổi phải deploy), rồi SSM, rồi mặc định. Mỗi tiến trình (phiên Runtime, môi trường Lambda) nhớ giá trị SSM 300 giây rồi đọc lại. Đọc SSM lỗi hoặc giá trị không phải số nguyên thì dùng mặc định và ghi log `quota_cap_unreadable`.
- **Đổi trần không cần deploy**: `aws ssm put-parameter --name /yofina/quota/chat_turns_per_day --type String --value 150 --overwrite --region ap-southeast-1` (tương tự `uploads_per_day`). Có hiệu lực ở mọi phiên đang chạy trong vòng 5 phút. Bỏ ghi đè: `aws ssm delete-parameter --name /yofina/quota/chat_turns_per_day --region ap-southeast-1` (về mặc định sau tối đa 5 phút). Trần `0` chặn ngay. Đọc lại: `aws ssm get-parameter --name /yofina/quota/chat_turns_per_day --region ap-southeast-1`.
- **Thử tích hợp** (cách kiểm của #13): đặt `chat_turns_per_day` = 2, chờ 5 phút, gửi 3 tin từ một tài khoản thử: tin thứ ba nhận thông báo hết lượt; xong thì xóa tham số.
- **Bộ đếm**: bảng `yofina-usage`, `day` = `quota#<YYYY-MM-DD>` (ngày thật theo `budget_timezone`, mặc định `Asia/Ho_Chi_Minh`, đổi lúc 0 giờ), `model` = `chat#<băm>` hoặc `upload#<băm>` (SHA-256 của `sub`, không lưu `sub` hay email), TTL 3 ngày. Phân vùng riêng nên `/ops/summary` (`Query` theo `day = YYYY-MM-DD`) không lẫn số. Bảng đếm lỗi (mạng, quyền) thì cho qua và ghi log `quota_store_error`: trần chung theo model vẫn chặn chi phí. Chạm trần ghi log `quota_exceeded` (loại và trần, không có `sub`); không có `YOFINA_USAGE_TABLE` thì tắt và ghi `quota_disabled`.
- **IAM**: Runtime có `/yofina/quota/*` trong `ReadConfig` và dùng chung `dynamodb:UpdateItem` của bộ đếm lượt gọi model; `yofina-ingest-api` có `ssm:GetParameter` trên `/yofina/quota/*` và `dynamodb:UpdateItem` trên `yofina-usage`. CORS của `yofina-api` không đổi: HTTP API tự gắn header CORS đã cấu hình vào mọi phản hồi của integration, kể cả 429.
