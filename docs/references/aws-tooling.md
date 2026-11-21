# Công cụ AWS trong Claude Code

Máy của dự án đã cấu hình sẵn một số MCP server và skill để làm việc với AWS stack ([§14 proposal](../proposal/proposal-summary.md#14-stack-14)). Trang này nói dùng cái nào cho việc gì. Danh sách lấy từ cấu hình phiên làm việc ngày 2026-11-21; **trạng thái có thể đổi nên mỗi phiên tự kiểm lại** (xem mục "Trạng thái" cuối trang).

## Việc gì → dùng gì

| Việc | Dùng | Ghi chú |
|---|---|---|
| Tra tài liệu AWS chính thức (mọi dịch vụ) | **aws-docs MCP** | Cách ưu tiên để thực hiện thói quen "tra tài liệu trước khi code" với dịch vụ AWS |
| Tra hoặc thao tác Amazon Bedrock AgentCore | **agentcore MCP** | Runtime, Memory, Gateway, Policy (Cedar), Identity, Code Interpreter, Browser |
| Gọi AWS API (liệt kê, mô tả, kiểm tra tài nguyên), kiểm Region | **AWS MCP (connector claude.ai)** | Ưu tiên thay vì chạy AWS CLI qua Bash. Dùng được ở thời điểm kiểm tra, xem "Trạng thái" |
| Viết/triển khai theo một mảng cụ thể (CDK, Lambda, Bedrock…) | **Skill `aws-core:*`** | Gọi qua Skill tool trước khi làm phần đó; skill chứa mẫu đã kiểm chứng và lỗi hay gặp |

## 1. aws-docs MCP (`mcp__aws-docs__*`)

Tra tài liệu AWS chính thức. Các tool: `search_documentation` (tìm theo thuật ngữ kỹ thuật cụ thể), `read_documentation` (đọc một trang, phân trang bằng `start_index`), `read_sections` (chỉ đọc mục cần), `search_table` (tìm dòng trong bảng lớn như quota, model hỗ trợ theo Region), `recommend` (trang liên quan; xem mục "New" của một dịch vụ để biết thay đổi gần đây). Khi trích, ghi lại URL tài liệu vào entry [ai-log](../ai-log/README.md).

## 2. agentcore MCP (`mcp__agentcore__*`)

Mọi thứ thuộc Amazon Bedrock AgentCore.

- **Đọc hướng dẫn**: `search_agentcore_docs`, `fetch_agentcore_doc`, và các `get_runtime_guide`, `get_memory_guide`, `get_gateway_guide`, `get_identity_guide`, `get_policy_guide`.
- **Thao tác thật** (có thể tốn tiền hoặc khó hoàn tác): Runtime (create/update/delete runtime và endpoint, `invoke_agent_runtime`), Memory (`memory_*`), Gateway và target (`gateway_*`, `gateway_target_*`), Policy engine và Cedar policy (`policy_*`, `policy_engine_*`), Identity (`identity_*`), Code Interpreter, Browser. Cũng có `web_search`.
- Khớp với các tầng trong proposal: Runtime chạy Strands agent (§8), Gateway + Policy cho `ledger.*` … `audit.*` (§9), Memory (§9), Identity (§8).

## 3. AWS MCP — connector claude.ai (`mcp__claude_ai_AWS_MCP__aws___*`)

Tool: `run_script` (chạy lệnh gọi AWS API qua boto3 trong sandbox), `search_documentation` / `read_documentation`, `retrieve_skill`, `list_regions`, `get_regional_availability`, `get_presigned_url` (upload/download S3), `get_tasks` (theo dõi tác vụ dài). Hướng dẫn của chính server: ưu tiên dùng nó thay vì chạy AWS CLI qua Bash.

Khi cần gọi AWS API, dùng `run_script` thay vì AWS CLI qua Bash. `get_regional_availability` hữu ích cho việc tuần 1 trong proposal: kiểm tra từng tính năng con của AgentCore, Bedrock (model, Guardrails, Knowledge Bases, Data Automation)… có ở Region Singapore hay chưa ([§13](../proposal/proposal-summary.md#13-rủi-ro-13) và [§15](../proposal/proposal-summary.md#15-kịch-bản-demo-và-kế-hoạch-3-tuần-15)). Kết quả kiểm nên ghi vào [../research/](../research/README.md).

## 4. Skill `aws-core:*`

Gọi bằng Skill tool trước khi làm phần tương ứng.

| Skill | Dùng cho phần nào của stack (§14) |
|---|---|
| `aws-core:aws-cdk` | AWS CDK: `infra-cdk/`, stack, bootstrap, `cdk synth/diff/deploy` |
| `aws-core:aws-serverless` | Lambda (tool sau Gateway), Step Functions (pipeline đêm), EventBridge và Scheduler, SQS event source |
| `aws-core:amazon-bedrock` | Model (Converse API), Guardrails, Knowledge Bases, prompt caching, AgentCore |
| `aws-core:aws-messaging-and-streaming` | SQS, EventBridge (pipeline theo sự kiện, hàng đợi lỗi/DLQ, hàng đợi nạp tệp) |
| `aws-core:aws-observability` | CloudWatch (dashboard, alarm, Logs Insights), X-Ray/ADOT, CloudTrail; trace OpenTelemetry |
| `aws-core:aws-iam` | IAM role/policy, trust policy, STS |
| `aws-core:aws-sdk-python-usage` | Code Python gọi AWS bằng boto3 (agent, Lambda tool, pipeline) |
| `aws-core:aws-sdk-js-v3-usage` | Code JS/TS gọi AWS (nếu frontend/Next.js cần) |
| `aws-core:aws-amplify` | Amplify Hosting cho frontend (lưu ý: skill này nhắm Amplify Gen2; FAST dùng Amplify chủ yếu để hosting) |
| `aws-core:aws-cloudformation` | Gỡ lỗi stack CloudFormation do CDK sinh ra |
| `aws-core:aws-billing-and-cost-management` | Ngân sách, cảnh báo chi phí, Cost Explorer (NFR "Chi phí", rủi ro "chi phí vượt credit") |
| `aws-core:signing-in-to-aws` | Lấy credential cho CLI/SDK qua `aws login` khi thiếu hoặc hết hạn |

Cũng có `aws-core:aws-containers` (ECS/Fargate/ECR) nhưng stack proposal không dùng ECS; chỉ cần nếu đội đóng container Lambda hoặc chuyển hướng.

## Quy ước làm việc

- Đọc/tra cứu: cứ làm.
- **Tạo, sửa, xóa tài nguyên AWS thật** (tốn tiền, khó hoàn tác — kể cả qua `agentcore` MCP, `run_script`, `cdk deploy`): hỏi chủ dự án trước.
- CLI đang đăng nhập bằng **root user**: tránh deploy bằng root, nên tạo IAM user/role riêng cho việc deploy (xem [open-questions](../requirements/open-questions.md#hạ-tầng-và-môi-trường-phát-sinh-khi-scaffold)).
- Region mặc định của CLI là `us-east-1`, trong khi proposal nhắm Singapore (`ap-southeast-1`): chốt Region triển khai trước khi deploy, và truyền Region tường minh thay vì dựa vào mặc định.

## Trạng thái lúc kiểm tra (2026-11-21)

Trạng thái này do coordinator ghi nhận (danh sách tool của phiên và kiểm tra trên máy); việc scaffold không gọi thử các tool. Mỗi phiên nên tự kiểm lại (ví dụ `/mcp`, `aws sts get-caller-identity`) rồi cập nhật bảng dưới và [HANDOFF.md](../../HANDOFF.md). Không ghi account ID vào tài liệu.

| Thành phần | Trạng thái |
|---|---|
| AWS CLI trên máy | Đã đăng nhập qua `aws login`; `aws sts get-caller-identity` chạy được. Danh tính hiện là **root user** của tài khoản; region mặc định trong `~/.aws/config` là `us-east-1` |
| aws-docs MCP | Có trong phiên, dùng được để tra tài liệu |
| agentcore MCP | Có trong phiên, dùng được để tra tài liệu |
| AWS MCP (connector claude.ai) | Đã đăng nhập lại và **dùng được** (coordinator chạy `run_script` với STS GetCallerIdentity thành công, 2026-11-21). Trỏ cùng tài khoản với AWS CLI, cũng là root user. Đăng nhập CLI và đăng nhập connector là hai việc riêng, nên phiên sau connector có thể lại hết phiên và cần đăng nhập lại (claude.ai connector settings hoặc `/mcp`) |
| `aws-serverless`, `terraform`, `aws-mcp` của plugin aws-core | Có cấu hình nhưng không kết nối được trong phiên này |
| Skill `aws-core:*` | Có trong danh sách skill của phiên |
