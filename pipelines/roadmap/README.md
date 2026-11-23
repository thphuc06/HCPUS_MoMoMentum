# Lambda sinh lại lộ trình

`yofina-roadmap-regen` chạy lõi Roadmap agent và cập nhật `roadmap_jobs` cho frontend polling. Điểm vào là `handler.lambda_handler`. Handler nhận phong bì EventBridge trực tiếp hoặc nhận JSON của cùng phong bì trong `Records[].body` của SQS.

| `detail-type` | `source` | Cách xử lý |
| --- | --- | --- |
| `roadmap.regeneration_requested` | `yofina.ledger` | `event_id = job_id`. Ledger phát sau khi commit. Lambda đọc job theo `job_id` và người dùng của sự kiện, lấy trigger, `alternative_id`, `note` và phiên bản gốc nếu đã ghi trong job. |
| `behavior.changed` | `yofina.forecast` | Chỉ nhận xác nhận từ PELT. `event_id = flag_id`. Tạo job `behavior_changed` với `behavior_flag_id` và `dedupe_key = event_id`. |
| `profile.updated` | `yofina.ledger` | Có `onboarding` (khai hồ sơ lần đầu, đặt lại tài khoản demo) thì bỏ qua để không loại lộ trình seed. Còn lại: `salary` tạo job `income_changed`, `jars` tạo job `goal_changed`. Khi cả hai thay đổi, ưu tiên `income_changed`. Bỏ qua các trường còn lại. `dedupe_key = event_id`. |

Lambda dùng secret của role `yofina_app` và transaction của `DataApi` để đặt `app.user_id` cho RLS. Khi job chưa chỉ định phiên bản gốc, agent dùng bản `active` nếu có. Ghi chú được che PII trước khi vào ngữ cảnh model. Tool `save_roadmap` quyết định trạng thái phiên bản theo `status_for_new_version` và trả ID, phiên bản đã lưu để chốt job `done`.

Chỉ mục duy nhất trong migration `0052` giới hạn một job `queued` hoặc `running` cho mỗi người dùng. Một lần giao chỉ chạy khi nhận chuyển được job từ `queued` sang `running`. Giao lại job đã kết thúc được xác nhận ngay. Sự kiện gặp job còn sống hoặc Data API lỗi trong lúc nhận hay chốt job được trả về trong `batchItemFailures` để SQS giao lại. Tin sai định dạng đi DLQ theo chính sách redrive. Lỗi nghiệp vụ, model hoặc tool được ghi vào job `failed` với `finished_at`, rồi xác nhận tin đã xử lý.

Khi Lambda bị dừng cứng hoặc không ghi được trạng thái cuối, lần giao tiếp theo sau khi hết lease chốt job cũ thành `failed`. `save_roadmap` và ghi trạng thái job là hai thao tác riêng. Một lần Invoke mất phản hồi vẫn có thể đã lưu bản mới, nên pipeline tránh gọi lưu lại cho cùng job. Đường EventBridge trực tiếp chuyển ngoại lệ cho cơ chế retry của đích. Cấu hình production dùng SQS để bảo đảm lần giao phục hồi sau lease.

## Gọi tool và quyền IAM

AgentCore Runtime chọn một cơ chế inbound auth. Runtime `yofina_agent` và Gateway hiện cấu hình JWT Cognito, còn Lambda chạy nền có danh tính dịch vụ IAM. Lambda chạy cùng mã Roadmap agent và gọi đồng bộ hai Lambda tool đích bằng `lambda:InvokeFunction`. `ledger` và `planner` trỏ đến `yofina-ledger`. `forecast` trỏ đến `yofina-forecast` phục vụ tool.

Payload gồm tham số tool và `user_id` của sự kiện hệ thống. `ClientContext` là base64 của JSON `{"custom":{"bedrockAgentCoreToolName":"planner___save_roadmap"}}`. Đường này bỏ qua Cedar của Gateway. Chỉ cấp quyền phát sự kiện, gửi vào SQS và gọi handler cho các thành phần hệ thống được phép. Danh sách tool trong `settings.py` chỉ gồm các lượt đọc, `check_suitability`, `optimize_allocation` và `save_roadmap`. Mọi tham số `confirm_token` bị từ chối.

- `lambda:InvokeFunction` giới hạn đúng hai Lambda tool trên.
- `bedrock:InvokeModel` cho các model và inference profile trong chuỗi `planner` của `llm_defaults.json` hoặc cấu hình ghi đè. Cấp `dynamodb:UpdateItem` trên bảng usage mà `LlmGateway` dùng để giữ trần gọi model.
- `rds-data:ExecuteStatement`, `rds-data:BeginTransaction`, `rds-data:CommitTransaction` và `rds-data:RollbackTransaction` trên cluster Aurora. Cấp `secretsmanager:GetSecretValue` trên secret DB app.
- Nếu dùng SSM, cấp `ssm:GetParameter` trên các khóa cấu hình cần đọc và quyền giải mã tương ứng khi dùng khóa KMS do dự án quản lý. Cấp quyền đọc, xóa tin và lấy thuộc tính của hàng đợi nguồn cho event source mapping, cùng quyền ghi CloudWatch Logs.

## Cấu hình và đóng gói

| Biến môi trường | Giá trị |
| --- | --- |
| `YOFINA_ROADMAP_LEDGER_FUNCTION_NAME` | Tên Lambda tool của target `ledger` và `planner`. |
| `YOFINA_ROADMAP_FORECAST_FUNCTION_NAME` | Tên Lambda tool của target `forecast`. |
| `YOFINA_EVENT_BUS_NAME` | Tên bus dùng cho các rule, hiện là `yofina-bus`. |
| `YOFINA_ROADMAP_INVOKE_CONNECT_TIMEOUT_SECONDS`, `YOFINA_ROADMAP_INVOKE_READ_TIMEOUT_SECONDS` | Timeout kết nối và đọc kết quả Invoke, tính bằng giây. |
| `YOFINA_ROADMAP_RUNNING_LEASE_SECONDS` | Số giây tối đa job ở trạng thái `running`. Đặt lớn hơn timeout thực thi Lambda và nhỏ hơn SQS visibility timeout để lần giao lại có thể dọn job bị dừng. |
| `YOFINA_ROADMAP_STAGE_PROGRESS` | Năm số nguyên phần trăm phân tách bằng dấu phẩy, tăng dần và nhỏ hơn 100. Thứ tự là `context,draft,allocate,suitability,save`. |
| `YOFINA_DB_CLUSTER_ARN`, `YOFINA_DB_APP_SECRET_ARN`, `YOFINA_DB_NAME` | Cấu hình Data API theo `yofina_core.db`. |
| `YOFINA_USAGE_TABLE` | Bảng đếm lượt gọi model, hoặc dùng SSM `dynamodb/usage-table`. |
| `YOFINA_REGION` hoặc `AWS_REGION` | Region của client AWS. |
| `YOFINA_SSM_PREFIX` | Tùy chọn. Cho phép `Config` tìm khóa SSM chữ thường khi thiếu biến môi trường. |

Giới hạn model, tool và số vòng sửa lấy từ `yofina_agent/defaults.json` và có thể ghi đè bằng env như trong agent. Đóng gói `handler.py`, cả gói `yofina_roadmap`, cả gói `yofina_core` kèm các tệp dữ liệu JSON/YAML theo gói, và cài `requirements.txt` theo runtime/kiến trúc Lambda. Chép các module `yofina_agent` gồm `__init__.py`, `roadmap_agent.py`, `settings.py`, `compact.py`, `textutil.py`, `tools.py`, `identity.py`, `notices.py`, `verifier.py`, `schemas.py`, `writer.py`, `metered_model.py` và `defaults.json`. `writer.py` nạp `metered_model.py` nên cần Strands. boto3 và botocore có sẵn trong Lambda runtime.

## Hạ tầng (CDK) và giá trị đã chọn

Construct `RoadmapRegen` ở `infra-cdk/lib/roadmap-regen.ts`, nối vào `YofinaTools` (`infra-cdk/lib/tools-stack.ts`), test `infra-cdk/test/roadmap-regen.test.ts`. **Chưa deploy.** Tài nguyên: [docs/aws-resources.md](../../docs/aws-resources.md).

Đóng zip (chạy ở gốc repo; ra `build/lambda/roadmap-arm64.zip`, khoảng 13 MB nén, `handler.py` ở gốc, `strands-agents` 1.65.0 và gói native cài theo `aarch64`):

```bash
uv run scripts/build_lambda.py pipelines/roadmap --arch arm64 --name roadmap --extra agent/src/yofina_agent:yofina_agent
```

Lệnh chép cả gói `yofina_agent` (nhiều hơn danh sách module tối thiểu ở trên, không sao). Thiếu zip thì `YofinaTools` báo lỗi lúc synth.

| Giá trị | Mặc định | Context | Lý do |
| --- | --- | --- | --- |
| Timeout Lambda | 300 s | `roadmapTimeoutSeconds` | Tối đa 4 lượt model `planner` (mỗi lượt đọc tối đa 60 s) cộng Invoke tool và Data API |
| `YOFINA_ROADMAP_RUNNING_LEASE_SECONDS` | 360 s | `roadmapRunningLeaseSeconds` | Lớn hơn timeout: chỉ dọn job `running` khi lần chạy trước chắc đã dừng |
| Visibility timeout SQS | 1.800 s | `roadmapVisibilityTimeoutSeconds` | 6 lần timeout (khuyến nghị của AWS), lớn hơn lease |
| Batch size / `maxConcurrency` | 1 / 2 | `roadmapBatchSize`, `roadmapMaxConcurrency` | Một job một lần gọi; 2 là tối thiểu của SQS event source, giữ dưới rpm của Claude |
| `ReportBatchItemFailures` | bật | | `JobBusy` và lỗi Data API trả về `batchItemFailures` |
| `maxReceiveCount` | 10 | `roadmapMaxReceiveCount` | AWS khuyến nghị ≥ 5; `JobBusy` cũng tốn một lượt nhận, và một người dùng có thể có vài sự kiện cùng lúc (hồ sơ, đổi hành vi, yêu cầu tay). Mỗi lần giao lại cách 30 phút nên tin chờ được khoảng 5 giờ trước khi vào DLQ |
| Giữ tin | 4 ngày | `roadmapRetentionDays` | Phải dài hơn visibility × maxReceiveCount (synth kiểm) |
| `YOFINA_ROADMAP_INVOKE_CONNECT_TIMEOUT_SECONDS` | 5 s | `roadmapInvokeConnectTimeoutSeconds` | |
| `YOFINA_ROADMAP_INVOKE_READ_TIMEOUT_SECONDS` | 65 s | `roadmapInvokeReadTimeoutSeconds` | Mặc định là timeout lớn nhất của hai Lambda tool (forecast 60 s, ledger 30 s) cộng 5 s |
| `YOFINA_ROADMAP_STAGE_PROGRESS` | `5,25,45,65,85` | `roadmapStageProgress` | |
| Bộ nhớ | 1.024 MB | `roadmapMemoryMb` | |
| Vai model được cấp Bedrock | `planner` | `roadmapLlmRoles` | Roadmap agent chỉ gọi `planner` |

`YOFINA_ROADMAP_FORECAST_FUNCTION_NAME` trỏ `yofina-forecast` (hàm tool), không phải `yofina-forecast-batch`. Biến `YOFINA_SSM_PREFIX` có đặt cho `yofina_core.llm` đọc nhánh `/yofina/llm`; `AgentSettings` tự bỏ khóa này.

## Bàn giao

1. ~~Migration `0052` và các tool Phase 4~~: đã deploy 23/11. Ledger dispatch `planner___get_roadmap`, `planner___optimize_allocation`, `planner___save_roadmap`, `planner___check_suitability` (`gateway/tools/ledger/yofina_ledger/gateway_api.py`, `tool_name` lấy phần sau `___` cuối cùng nên tiền tố `planner___` dùng được). Forecast dispatch `forecast___get_resilience_score` (`pipelines/forecast/yofina_forecast/tool.py`). Nguồn sự kiện: ledger phát `roadmap.regeneration_requested` và `profile.updated` (`yofina_ledger/events.py`), forecast phát `behavior.changed` sau PELT (`yofina_forecast/events.py`).
2. ~~Construct CDK~~: đã có (`RoadmapRegen`, mục trên), chưa deploy.
3. Khi deploy: build zip, `uv run scripts/cdk.py diff YofinaTools`, `deploy YofinaTools`. Theo dõi DLQ `yofina-roadmap-events-dlq` và số job `failed` sau lần chạy đầu.
