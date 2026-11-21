# Amazon Bedrock AgentCore: ghi chú cách dùng cho Yofina Foresight

Ngày tra cứu: **2026-11-21**. Người ghi: agent nghiên cứu (chỉ đọc, không tạo tài nguyên AWS nào). Dịch vụ đổi nhanh: tin trang tài liệu hơn file này khi hai bên lệch nhau, và chạy thử trước khi dựa vào chỗ đánh dấu [SĐ].

Quy ước nhãn nguồn trong file:

- **[TL]** đã đọc trong tài liệu chính thức AWS (docs.aws.amazon.com), URL ở mục 6.
- **[BL]** đọc từ blog AWS, repo mẫu hoặc README gói thư viện.
- **[SĐ]** suy đoán hoặc suy luận của người viết từ các điều đã đọc, chưa kiểm chứng.
- **[Đã chạy thử 2026-11-21]** đã chạy thật ở `ap-southeast-1` trong spike, có link tới file spike. Khi nhãn này mâu thuẫn với [TL]/[BL]/[SĐ] cùng chỗ thì tin spike. Phần về Gateway, Policy, danh tính xuống tool áp từ mục "Cần sửa trong agentcore.md" của [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) (đã áp hết 14 điểm ngày 2026-11-21); phần về Runtime từ [spike-agentcore-runtime-cors.md](spike-agentcore-runtime-cors.md).

## 1. Câu hỏi cần trả lời

1. **Runtime**: đóng gói và deploy agent Strands (Python) thế nào (entrypoint, zip hay container, ARM64, CLI nào, CDK thế nào); streaming SSE; giao thức HTTP/MCP/A2A/AG-UI và cách bật AG-UI; session, microVM, timeout, job nền dài và báo tiến độ; quota.
2. **Xác thực**: JWT authorizer của Runtime với Cognito; truyền danh tính người dùng xuống tool để tool chỉ đọc dữ liệu của chủ JWT.
3. **Gateway**: biến Lambda thành tool MCP, schema, đặt tên `ledger.*`, auth vào và ra, tìm tool theo ngữ nghĩa, gọi từ Strands.
4. **Policy (Cedar)**: gắn vào Gateway, mặc định từ chối, luật theo claim và tham số, chế độ chỉ ghi log, luật mẫu.
5. **Memory**: ngắn hạn, dài hạn, chiến lược, namespace theo người dùng, tích hợp Strands, độ trễ trích xuất, xóa theo yêu cầu.
6. **Observability + Evaluations**: bật trace, xem ở đâu, trả `trace_id`, evaluator có sẵn và tự viết, online và on-demand.
7. **Region**: từng thành phần có ở `ap-southeast-1` chưa.
8. **Chi phí**: mô hình tính tiền đủ để ước lượng demo.

## 2. Kết luận ngắn: làm thế này

1. **Region `ap-southeast-1` dùng được cho toàn bộ stack AgentCore proposal cần** (Runtime microVM, platform V2, Memory, Gateway kèm semantic search, Identity, Observability, Policy kèm temporal, Evaluations). Không có thành phần nào chặn. Hai khác biệt nhỏ ở Singapore: quota phiên đang hoạt động 2.500 (us-east-1 là 5.000) và Evaluations dựng sẵn giới hạn 200 lượt/phút (nơi khác 1.200), judge chạy qua global cross-region inference (dữ liệu có thể được xử lý ngoài Singapore). [TL]
2. **CLI đang khuyến nghị là `@aws/agentcore` (npm), không phải starter toolkit pip** (đã deprecated). Trên Windows nếu từng cài `bedrock-agentcore-starter-toolkit` thì gỡ trước, nếu không lệnh `agentcore` cũ che lệnh mới. [TL]
3. **Hạ tầng của dự án nên tự viết CDK bằng `aws-cdk-lib/aws-bedrockagentcore`** (L2 `Runtime`, `Gateway`, `Memory`, `OnlineEvaluationConfig`… đã stable ở aws-cdk-lib 2.277.0). `agentcore` CLI (CDK bên trong) dùng để scaffold, chạy thử cục bộ (`agentcore dev`) và đối chiếu; `PolicyEngine` có thể vẫn ở gói alpha, kiểm khi cài. [TL][BL]
4. **Chạy agent bằng `BedrockAgentCoreApp` + `@app.entrypoint` (async generator) cho HTTP/SSE, hoặc cùng cách đó bọc `ag-ui-strands` cho AG-UI.** Cổng 8080, `/invocations` POST, `/ping` GET. Mẫu FAST làm đúng như vậy. Bật AG-UI = đặt protocol của Runtime là `AGUI` (CLI: `agentcore add runtime --protocol AGUI`). [TL][BL]
5. **Đóng gói**: Python zip (`CodeZip`, ARM64, ≤250 MB nén) hoặc container ARM64. ~~Tài liệu hợp đồng AG-UI ghi "containerized"... mặc định chọn container cho AG-UI~~ **[Đã chạy thử 2026-11-21] SAI: AG-UI chạy được với CodeZip**, không cần Docker/QEMU/CodeBuild. Từ Windows: `uv pip install --python-platform aarch64-manylinux2014 --python-version 3.13 --only-binary=:all: --target=...` (30 MB nén cho ag-ui-strands 1.0.4 + strands-agents 1.65.0), zip, `aws s3 cp`, `create-agent-runtime` với `codeConfiguration` + `protocolConfiguration.serverProtocol=AGUI`; READY sau ~15 giây (V1). Chi tiết: `docs/research/spike-agentcore-runtime-cors.md` mục 1. [TL][BL]
6. **JWT**: Runtime và Gateway đều dùng `customJWTAuthorizer` với discovery URL của Cognito (`https://cognito-idp.<region>.amazonaws.com/<poolId>/.well-known/openid-configuration`) + `allowedClients` (access token Cognito mang `client_id`, không có `aud`). Muốn agent đọc được JWT thì phải đưa `Authorization` vào `requestHeaderAllowlist` của Runtime. **[Đã chạy thử 2026-11-21]** `allowedClients` + access token: qua; **ID token bị từ chối** (`Claim 'client_id' value mismatch`); đặt `allowedAudience` thì ngược lại (ID token qua, access token bị từ chối); đặt **cả hai** thì không token Cognito nào qua. Xem `spike-agentcore-runtime-cors.md` mục 2. **[Đã chạy thử 2026-11-21, Gateway]** Gateway cũng vậy: chỉ access token vào được; **ID token ra 403 `insufficient_scope`**, token bị sửa `sub` hoặc hỏng chữ ký cũng ra **403** (không phải 401, thông điệp "requires higher privileges" gây hiểu nhầm); access token Cognito **không có `aud`** (đã xác nhận). Xem [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 1. [TL]
7. **Danh tính xuống tool**: Lambda target của Gateway **chỉ nhận tham số tool và context metadata, không nhận JWT**. Cách khả thi: (A) tool có tham số `user_id` bắt buộc và luật Cedar ép `context.input.user_id == principal.id` (principal là `sub` của JWT); (B) interceptor Lambda ở Gateway đọc JWT và ghi đè tham số hoặc thêm header. Nên dùng cả hai. [TL][SĐ] **[Đã chạy thử 2026-11-21]** cả hai chạy đúng và độc lập nhau: interceptor ghi đè `user_id` (và đặt header `x-user-id`; Lambda đọc ở `context.client_context.custom["bedrockAgentCorePropagatedHeaders"]`), Cedar `context.input.user_id == principal.id` chặn A đọc/ghi dữ liệu của B. **Header allowlist do client tự gửi đi qua nguyên văn** (A gửi `x-user-id` của B thì Lambda thấy của B): chỉ header do interceptor đặt mới đáng tin. Xem [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 3.
8. **Tên tool**: dấu chấm không dùng được. Tên target chỉ gồm chữ, số, gạch nối; tool lộ ra qua MCP là `<target>___<tool>` (ba gạch dưới). Vậy `ledger.get_jar_balances` thành target `ledger` + tool `get_jar_balances` = `ledger___get_jar_balances`; action Cedar cũng có dạng đó. Nên sáu target = sáu nhóm (`ledger`, `forecast`, `planner`, `knowledge`, `ingest`, `audit`), mỗi target một Lambda. [TL] **[Đã chạy thử 2026-11-21]** `tools/list` trả đúng `ledger___get_jar_balances` và `ledger___move_between_jars`; gạch dưới và dấu chấm trong tên **target** bị từ chối. Giới hạn tên: xem mục 3.3 "Đặt tên". [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 1.
9. **Cedar**: mặc định từ chối, `forbid` thắng `permit`. Attach policy engine vào Gateway với `mode: LOG_ONLY` trước, xem metric `LogOnlyDecisionFlips` bằng 0 rồi đổi `ENFORCE`; ngoài ra có `enforcementMode` theo từng policy. `number` trong schema là `decimal` (so sánh bằng `.lessThanOrEqual(decimal("..."))`); số tiền VND nên khai `integer` để dùng `<=` và cộng dồn. [TL]
10. **Cờ "đã xác nhận" trong tham số chỉ là lưới an toàn, không phải bằng chứng người dùng đã bấm**: LLM tự điền được tham số. Khuyến nghị: tool ghi trong Gateway chỉ tạo "đề xuất chờ xác nhận"; nút Xác nhận của UI gọi một endpoint riêng có JWT để áp dụng. Cedar vẫn giữ cờ và hạn mức làm lớp phụ. [SĐ] (chi tiết mục 4) **[Đã chạy thử 2026-11-21]** mẫu "token xác nhận HMAC do server cấp" chạy đúng trên 13 ca (LLM tự điền `user_confirmed=true`, bịa token, ký sai khóa, đổi tham số, replay, token của người khác, token hết hạn đều bị Lambda từ chối; chỉ luồng "UI bấm nút, endpoint riêng cấp token, gọi lại tool với token" mới ghi). **Cedar chỉ là lưới phụ**: ép hạn mức, khớp `user_id`, có mặt `confirm_token` dạng `*.*`; không kiểm được chữ ký, hạn, tính duy nhất. `user_confirmed` do LLM điền vô giá trị bảo mật. Mẫu tối thiểu: `jti` dùng một lần bằng `PutItem` điều kiện trên DynamoDB (có TTL), token hạn 120 s, secret HMAC ở Secrets Manager (xoay khóa bằng hai khóa hợp lệ song song [SĐ]). Đây là hướng được đề xuất theo kết quả thử, chủ dự án chưa chốt. Xem [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 5 và mục 8.
11. **Memory**: `actorId` lấy từ `sub` của JWT, không lấy từ payload; namespace có dấu `/` đầu và cuối, ví dụ `/users/{actorId}/preferences/`; Strands dùng `AgentCoreMemorySessionManager` + `RetrievalConfig`. Không có API "xóa hết theo actor": phải liệt kê rồi xóa từng record và event. Số liệu độ trễ trích xuất **không có trong tài liệu**; đây là quá trình bất đồng bộ. [TL]
12. **Trace**: Runtime tự bật ADOT; mỗi tài khoản bật CloudWatch Transaction Search một lần (`agentcore deploy` tự bật). Xem ở console AgentCore Observability hoặc CloudWatch GenAI Observability. Client gửi `traceparent` hoặc `X-Amzn-Trace-Id` để biết trước `trace_id`. [TL]
13. **Evaluations**: evaluator dựng sẵn gồm GoalSuccessRate (phiên), Correctness, Helpfulness, Faithfulness, Coherence, Conciseness, InstructionFollowing, ResponseRelevance, Refusal, Harmfulness, Stereotyping (lượt), ToolSelectionAccuracy, ToolParameterAccuracy (tool). Evaluator tự viết bằng Lambda (code-based) hợp với `NumericGrounding`, `SchemaValidity`, `SuitabilityCompliance` và rẻ hơn judge LLM. [TL]
14. **Chi phí demo**: runtime, gateway, policy, memory chỉ vài USD; **chi phí đáng kể nhất là Evaluations dựng sẵn khi lấy mẫu cao** (tính theo token). Giữ sampling thấp, ưu tiên evaluator code-based. Ước lượng ở mục 3.8, đó là số tự tính từ bảng giá. [TL][SĐ]
15. **Job nền**: job "chục giây đến vài phút" không cần cơ chế 8 giờ. Dùng `app.add_async_task`/`complete_async_task` (hoặc `/ping` trả `HealthyBusy`) và báo tiến độ qua một lần gọi ngắn khác vào cùng session hoặc đọc trạng thái trong DB; đừng giữ một luồng SSE mở quá 60 phút. [TL]

## 3. Chi tiết

### 3.1 Runtime

#### Đóng gói và triển khai

- **Hợp đồng**: HTTP: cổng `8080`, `POST /invocations`, `GET /ping` (trả `{"status":"Healthy"}` hoặc `"HealthyBusy"`), host `0.0.0.0`, **chỉ ARM64**. MCP cổng 8000 `/mcp`; A2A cổng 9000 `/`; AG-UI cổng 8080 `/invocations` (SSE) hoặc `/ws`. Phân biệt HTTP và AG-UI chỉ bằng cấu hình `protocol` của Runtime. [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-service-contract.html
- **Hai kiểu build**: `CodeZip` (Python 3.10 trở lên, zip ≤250 MB nén / 750 MB giải nén, thư viện phải là wheel ARM64: `uv pip install --python-platform aarch64-manylinux2014 --python-version 3.13 --only-binary=:all: --target=deployment_package -r pyproject.toml`) hoặc **container** (ARM64, tối đa 2 GB nén ở V1 và 10 GB ở V2). Entrypoint khai trong `entryPoint: ['opentelemetry-instrument','main.py']`. [TL]
- **Platform V2** (đặt `platformVersion: V2` khi tạo runtime, mặc định V1; có ở Singapore): khởi động từ snapshot nên cold start ổn định, ghim phiên theo người dùng (session pinning, bật mặc định, từ chối request cùng session của người khác), tính tiền theo mức dùng thực. Đổi lại create/update mất vài phút và `/ping` phải thành công kịp để chụp snapshot. **[Đã chạy thử 2026-11-21, Singapore]** V2 tạo mất ~5 phút (V1: ~15 giây); session pinning theo `sub` JWT chạy đúng trên V2 (người dùng B dùng session của A: 403 `ACCESS_DENIED`) và **không có** trên V1 (B dùng được, chung microVM); V2 trả 409 `SESSION_BUSY` khi hai request chạy song song cùng session, V1 thì chạy song song. Cold start tới event đầu: V1 trung vị 2,7 s (2,6 đến 3,7), V2 trung vị 2,5 s (1,8 đến 2,7; trong trình duyệt 1,7 đến 2,0 s so với V1 2,5 đến 3,6 s) nên **không đạt "ký tự đầu dưới 1,5 giây" khi phiên lạnh**; phiên ấm 0,3 s. Chi tiết ở `spike-agentcore-runtime-cors.md` mục 4 và 5. [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html
- **CLI** (`npm install -g @aws/agentcore`, cần Node 20.12 trở lên, `uv`, Python 3.10 trở lên): [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-get-started-cli.html

```bash
agentcore create --name Yofina --template agent-python-strands   # code-based, CodeZip, kèm Memory
agentcore dev --mode browser          # chạy cục bộ + Agent Inspector
agentcore build && agentcore deploy   # CDK bên trong; bật luôn Transaction Search
agentcore invoke --runtime agent --payload '{"prompt":"xin chào"}'
agentcore logs runtime --since 30m --level error
agentcore traces runtime list --since 30m
```

  Ghi chú: các guide của MCP agentcore ghi tên gói là `@aws/agentcore-cli`, trang hướng dẫn chính thức ghi `@aws/agentcore`; dùng cái sau. Nhiều template (`agent-python-strands-container`, AG-UI Python Strands) có trong trình hướng dẫn `agentcore create`. [TL]
- **CDK tự viết** (hướng nên theo, mục 4): aws-cdk-lib 2.277.0 có module `aws-cdk-lib/aws-bedrockagentcore` với `Runtime`, `RuntimeEndpoint`, `AgentRuntimeArtifact`, `Gateway`, `GatewayTarget`, `Interceptor`, `Memory`, `MemoryStrategy`, `Evaluator`, `OnlineEvaluationConfig`, `WorkloadIdentity`… [TL] https://constructs.dev/packages/@aws-cdk/aws-bedrock-agentcore-alpha/v/2.277.0-alpha.0 Mẫu:

```ts
// zip trên S3
const artifact = agentcore.AgentRuntimeArtifact.fromS3(
  { bucketName: codeBucket.bucketName, objectKey: 'deployment_package.zip' },
  agentcore.AgentCoreRuntime.PYTHON_3_12, ['opentelemetry-instrument', 'main.py']);
// hoặc container build từ thư mục có Dockerfile
// const artifact = agentcore.AgentRuntimeArtifact.fromAsset(path.join(__dirname, '../agent'));
new agentcore.Runtime(this, 'Agent', {
  runtimeName: 'yofina_agent',
  agentRuntimeArtifact: artifact,
  authorizerConfiguration: agentcore.RuntimeAuthorizerConfiguration.usingJWT(
    discoveryUrl, [appClientId] /*allowedClients*/),   // [BL] chữ ký theo README stable, kiểm lại khi viết code
});
```
  Nguồn mẫu: https://github.com/aws-samples/serverless-patterns/tree/main/lambda-durable-bedrock-agentcore-async (`fromAsset` + `Runtime`) và README gói CDK ở trên. Mẫu CfnRuntime với `customJwtAuthorizer` ở https://github.com/aws-samples/serverless-patterns/tree/main/eventbridge-apidestination-agentcore. [BL]
- Quyền cần có: Runtime có service-linked role `AWSServiceRoleForBedrockAgentCoreRuntimeIdentity` (tạo từ 13/10/2025; role gọi API control cần `iam:CreateServiceLinkedRole`). Execution role tin `bedrock-agentcore.amazonaws.com`, cần ECR/S3, CloudWatch Logs, X-Ray, `bedrock:InvokeModel`. [TL] Không deploy bằng root (xem aws-tooling.md).

#### Entrypoint tối thiểu (Strands, SSE)

```python
# [TL] suy từ ví dụ runtime-oauth: async generator => SSE "data: ..."
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent

app = BedrockAgentCoreApp()

@app.entrypoint
async def invoke(payload, context):
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():   # bắt buộc: chống chèn toolUse qua kiểu JSON khác
        yield {"error": "prompt phải là chuỗi"}; return
    agent = Agent()                      # tạo mới mỗi request nếu agent phụ thuộc người dùng
    async for event in agent.stream_async(prompt):
        yield event

if __name__ == "__main__":
    app.run()
```
Khuyến cáo của tài liệu: luôn kiểm `isinstance(prompt, str)` vì payload là JSON đã parse và một khối `toolUse` lọt vào có thể chạy tool thẳng, bỏ qua mô hình và guardrail. [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-invoke-agent.html

#### Streaming, giao thức, bật AG-UI

- HTTP: response `text/event-stream`, client đọc dòng `data: `. Gọi qua HTTPS với `Authorization: Bearer` (không dùng AWS SDK khi dùng OAuth) tới `https://bedrock-agentcore.<region>.amazonaws.com/runtimes/<ARN đã URL-encode>/invocations?qualifier=DEFAULT`, header `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id`. [TL]
- AG-UI: Runtime làm proxy trong suốt, không kiểm nội dung; đúng `RunAgentInput` (`threadId`, `runId`, `messages`, `tools`, `context`, `state`, `forwardedProps`) vào, luồng sự kiện ra (`RUN_STARTED`, `TEXT_MESSAGE_*`, `TOOL_CALL_*`, `STATE_SNAPSHOT`/`STATE_DELTA`, `CUSTOM`, `RUN_FINISHED`/`RUN_ERROR`). Mọi lỗi cũng đi dưới dạng sự kiện `RUN_ERROR` (401, 403, 409 `SESSION_BUSY` là lỗi thử lại được; lỗi code agent trả HTTP 200). [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-agui.html và `runtime-agui-protocol-contract.html`
- Cách bật: `agentcore add runtime --name Agui --language python --protocol AGUI --authorizer-type CUSTOM_JWT --authorizer-configuration '{"customJwtAuthorizer":{"discoveryUrl":"...","allowedClients":["<clientId>"]}}' --request-header-allowlist Authorization`. Thư viện theo tài liệu chính thức: `ag-ui-protocol>=0.1.19,<0.2`, `ag-ui-strands>=0.3,<0.4`, `strands-agents>=1.15,<2`, `bedrock-agentcore[strands-agents]>=1.18.1,<2`, `aws-opentelemetry-distro~=0.21.0`. [TL]
- **Lệch phiên bản cần xử lý**: PyPI (xem ngày 2026-11-21) có `ag-ui-strands 1.0.4` (12/11/2026), yêu cầu `strands-agents>=1.55.0` và `ag-ui-protocol>=1.0.0`, tức khác dải ghim trong tài liệu AWS. Chọn một bộ phiên bản nhất quán, ghim bằng lockfile và chạy thử cả luồng SSE lẫn interrupt. [BL]
- Mẫu AG-UI + Strands của FAST (v0.4.1+): vẫn là `BedrockAgentCoreApp` + `@app.entrypoint` async generator `yield event.model_dump(mode="json", by_alias=True, exclude_none=True)`, tạo agent mới mỗi request, gắn Memory bằng `session_manager_provider`, `deployment_type: docker`. [BL] https://aws.amazon.com/blogs/machine-learning/build-generative-ui-for-ai-agents-on-amazon-bedrock-agentcore-with-the-ag-ui-protocol/
- `ag-ui-strands` hỗ trợ trạng thái dùng chung (`state_from_args`/`state_context_builder`), công cụ phía frontend, và human-in-the-loop bằng `tool_context.interrupt(...)` (run kết thúc với outcome `interrupt`, client tiếp tục cùng `thread_id`). Phần có tác dụng phụ phải đặt **sau** `interrupt()` vì tool chạy lại từ đầu khi resume. [BL] https://pypi.org/project/ag-ui-strands/
- CORS khi trình duyệt gọi thẳng endpoint Runtime: tài liệu không nói, nhưng **[Đã chạy thử 2026-11-21] gọi thẳng được**: chính dịch vụ trả preflight `OPTIONS` (200, `Access-Control-Allow-Origin: *`, phản chiếu `Access-Control-Request-Headers`, `Allow-Methods` = đúng method được hỏi, `Max-Age: 172800`) và gắn `Access-Control-Allow-Origin: *` cả vào phản hồi `POST` (kể cả 401/403). `fetch` POST + `Authorization: Bearer` + đọc SSE từ `http://localhost:5173` chạy được trên Edge 158 và Chrome 157 thật. `CORSMiddleware` trong app **vô hiệu** (Origin không tới app, header phản hồi của app bị bỏ). Không dùng được `credentials: 'include'` (ACAO là `*`), nhưng Bearer trong header không cần. Chi tiết: `docs/research/spike-agentcore-runtime-cors.md` mục 3. Lớp trung gian (Lambda Function URL/API Gateway) **không cần** vì CORS.

#### Session, microVM, timeout, bất đồng bộ

| Mục | Giá trị | Nguồn |
|---|---|---|
| Session | một microVM riêng (CPU, bộ nhớ, đĩa), tạo ở lần gọi đầu với `runtimeSessionId` (≥33 ký tự, dùng UUID). **[Đã chạy thử]** 33 đến 256 ký tự (≤32 hoặc ≥257 trả 400 `VALIDATION_ERROR`); không gửi header thì dịch vụ sinh UUID và trả lại trong header phản hồi | [TL] |
| Idle timeout | mặc định 15 phút, chỉnh được tới 8 giờ (`lifecycleConfiguration.idleRuntimeSessionTimeout`) | [TL] |
| Tối đa một session | 8 giờ (`maxLifetime`) | [TL] |
| Timeout request đồng bộ | 15 phút, không đổi | [TL] |
| Streaming (SSE, WebSocket) | tối đa 60 phút mỗi kết nối; chunk ≤10 MB | [TL] |
| Job bất đồng bộ | tối đa 8 giờ (microVM) | [TL] |
| Payload | ≤100 MB | [TL] |
| Kết nối đồng thời mỗi session (V2) | 150 + 50 mỗi vCPU (2 vCPU → 250) | [TL] |
| Tài nguyên mỗi session (V2) | mặc định 2 vCPU/8 GB, không bùng; cấu hình `resourceConfigurations` thì có baseline và bùng tới 4 lần, tối đa 8 vCPU/32 GB | [TL] |
| Đĩa phiên | ≤1 GB, tạm thời | [TL] |
| Biến môi trường | ≤4 KB mỗi agent | [TL] |

- Phiên bị hủy là hủy hết microVM; trạng thái trong RAM mất. Bền vững thì dùng Memory hoặc DB. `StopRuntimeSession` để dừng sớm (đỡ tiền). [TL]
- **Job nền**: dùng `app.add_async_task("tên", {...})` rồi `app.complete_async_task(task_id)`; SDK tự để `/ping` trả `HealthyBusy`, giữ session sống qua 15 phút idle. Hoặc tự viết `@app.ping` trả `PingStatus.HEALTHY_BUSY`. Đừng chạy việc chặn trong handler (sẽ chặn cả `/ping`, session bị giết sau 15 phút). Không đặt `time_of_last_update` bằng giờ hiện tại ở mỗi ping (session sẽ không bao giờ hết idle). [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-long-run.html
- **Báo tiến độ**: tài liệu không có cơ chế "tiến độ" riêng. Hai cách: (1) giữ luồng SSE đang mở và phát sự kiện `STATE_DELTA`/`CUSTOM`/`ACTIVITY_*` (≤60 phút); (2) job ghi tiến độ vào DB/DynamoDB, frontend gọi lại cùng session (hoặc tool `ingest.get_job_status`) để lấy. Cách 2 bền hơn khi mạng di động rớt. [TL][SĐ]
- Giới hạn tài khoản (mặc định, Singapore và các Region khác; us-east-1/us-west-2 gấp đôi ở mục đầu): phiên hoạt động 2.500 (điều chỉnh được), runtime 1.000, endpoint 10 mỗi agent, **25 phiên mới/giây**, 1.000 TPS gọi data plane, 50 TPS mutation control plane. [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html

### 3.2 Xác thực và danh tính

#### JWT authorizer của Runtime với Cognito

- Cấu hình: `discoveryUrl` phải khớp `^[^\s?#]+/\.well-known/(openid-configuration|oauth-authorization-server)(/[^\s?#]+)?$`; `allowedClients` so với claim `client_id`; `allowedAudience` so với `aud`; `allowedScopes`; `customClaims` (`STRING` với `EQUALS`, `STRING_ARRAY` với `CONTAINS`/`CONTAINS_ANY`). Ít nhất một trường là bắt buộc; dùng nhiều thì kiểm tất cả. [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/inbound-jwt-authorizer.html
- Với Cognito: dùng **access token** và `allowedClients: [<app client id>]`. Access token Cognito có `client_id`, `iss`, `sub`, `scope`, không có `aud`, nên đặt `allowedAudience` sẽ làm token bị từ chối [SĐ, từ kiến thức về Cognito, ví dụ token mẫu trong tài liệu cũng không có `aud`]. Token mặc định sống 60 phút; token cho tool phải làm mới. [TL] **[Đã chạy thử 2026-11-21]** đúng như phỏng đoán: access token không có `aud`, `allowedAudience` làm access token bị từ chối; ở Gateway, ID token ra 403 `insufficient_scope` và token hỏng ra 403 chứ không phải 401. Xem [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 1 và [spike-agentcore-runtime-cors.md](spike-agentcore-runtime-cors.md) mục 2.
- **Mỗi Runtime chỉ dùng SigV4 hoặc JWT, không cả hai.** Muốn cả hai thì tạo hai runtime/phiên bản. [TL]
- Đưa JWT vào code agent: thêm `Authorization` vào `requestHeaderAllowlist` (CLI `--request-header-allowlist Authorization`); trong handler đọc `context.request_headers['Authorization']`, `jwt.decode(token, options={"verify_signature": False})` (Runtime đã kiểm chữ ký). Các header khác phải khai trong allowlist và đọc qua `context.request.headers`. Tối đa 20 header, mỗi giá trị ≤10 KB; header `X-Amzn-Bedrock-AgentCore-Runtime-Custom-*` luôn qua được. **[Đã chạy thử 2026-11-21] không đúng như câu này**: header prefix `...Custom-Bar` không khai trong allowlist bị bỏ; chỉ header có tên trong allowlist (và `traceparent`/`X-Amzn-Trace-Id` nếu client gửi, `Authorization` khi đã khai) tới app. [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-header-allowlist.html
- Claim tùy biến (ví dụ `department`, `tier`) nhét vào token qua Lambda pre token generation V2 của Cognito (mẫu blog); Runtime/Gateway có thể bắt buộc claim đó. [BL] https://aws.amazon.com/blogs/security/propagate-user-authorization-context-in-ai-agents-with-amazon-bedrock-agentcore/
- Header `X-Amzn-Bedrock-AgentCore-Runtime-User-Id` (cần quyền IAM `InvokeAgentRuntimeForUser`) **không** xác thực người dùng, chỉ dùng dev; production dùng JWT. [TL]
- `agent.stream_async` không biết người dùng nào: **không bao giờ** nhận `user_id` từ payload do client gửi. Lấy `sub` từ JWT đã được Runtime kiểm.

#### Truyền danh tính xuống tool

Sự thật đã đọc [TL]: Gateway tạo yêu cầu Cedar từ JWT (principal = `AgentCore::OAuthUser::"<sub>"`, các claim còn lại thành tag) và từ lời gọi tool (`context.input` = tham số). Lambda target nhận `event` = đúng các tham số của schema và `context.client_context.custom` (`bedrockAgentCoreToolName`, `...GatewayId`, `...TargetId`, `...AwsRequestId`, header được cho phép). **JWT/claim không vào Lambda.** Header `Authorization` bị cấm đưa vào allowlist của target (chỉ interceptor mới đẩy được). Outbound auth của Lambda target chỉ có IAM role của gateway. https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-headers.html

Mẫu FAST dùng một hướng khác: Runtime xin token M2M (client credentials) và Lambda pre-token đưa danh tính người dùng vào token M2M, Cedar xét claim `department`. Repo tự ghi "không phải giải pháp production". [BL] https://github.com/awslabs/fullstack-solution-template-for-agentcore

Đề xuất cho Yofina (toàn bộ [SĐ] ghép từ các sự thật trên, **cần chạy thử**):

1. **Agent chuyển nguyên JWT của người dùng** sang Gateway: tạo `MCPClient` mới mỗi request với `streamablehttp_client(gateway_url, headers={"Authorization": f"Bearer {jwt}"})` (cùng user pool và `allowedClients` với Runtime). Principal Cedar chính là người dùng thật.
2. **Lớp 1, Cedar ghim tham số**: mọi tool đọc/ghi có `user_id` (string, bắt buộc); luật `permit ... when { context.input.user_id == principal.id }`. `principal.id` có trong entity (mục "Entity Store" của trang authorization flow). Agent code (không phải LLM) điền `user_id` từ `sub`; nếu LLM điền sai thì Gateway từ chối.
3. **Lớp 2, interceptor request** (Lambda, `passRequestHeaders: true`): đọc `Authorization`, lấy `sub`, **ghi đè** `params.arguments.user_id` trong `transformedGatewayRequest.body` (hoặc thêm header `x-user-id` đã allowlist ở target để Lambda đọc từ `bedrockAgentCorePropagatedHeaders`). Interceptor là mã của đội nên cũng ghi log kiểm toán. ~~Chưa rõ thứ tự interceptor và policy (tài liệu chỉ nói interceptor có thể "short-circuit" bỏ qua policy), nên giữ lớp 1 độc lập.~~ **[Đã chạy thử 2026-11-21]** thứ tự là `JWT authorizer -> interceptor -> Cedar (thấy tham số đã bị interceptor sửa) -> kiểm schema -> Lambda`; interceptor chỉ chạy sau khi JWT hợp lệ (JWT hỏng: 403 và Lambda interceptor không được gọi). Hai lớp độc lập: gỡ interceptor thì Cedar vẫn chặn, gỡ Cedar thì interceptor vẫn ghi đè. Interceptor trả `transformedGatewayResponse` (chế độ `deny`) thì bỏ qua cả Cedar lẫn target. Interceptor chạy **trước** kiểm schema nên tiêm được cả tham số `required` (LLM bỏ trống `user_id` vẫn qua). Vị trí "Cedar trước kiểm schema" là suy ra từ lỗi quan sát được. Độ trễ thêm 50 đến 80 ms ở trạng thái ấm. Xem [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 3 đến 6.
4. **Lambda tool luôn lọc SQL theo `user_id` đã được ghim** (tham số hóa, không SQL tự do); thêm Row-Level Security Postgres nếu kịp.
5. **Job nền dài hơn tuổi thọ token** (Cognito 60 phút): dùng danh tính dịch vụ (client credentials) kèm `user_id` đã xác thực lúc khởi tạo job, ghi `user_id` vào bản ghi job; đừng giữ JWT của người dùng.

**[Đã chạy thử 2026-11-21]** các bước 1 đến 4 đã chạy (Cedar `context.input.user_id == principal.id` qua validation và chặn đúng; interceptor `overwrite` chạy; agent chuyển nguyên access token). Chi tiết bổ sung: (a) khai `user_id` ở schema là tùy chọn và để interceptor luôn tiêm, Lambda vẫn nhận `user_id` kể cả khi schema tool không khai trường này, và kể cả khi LLM tự nhét `user_id` của người khác; riêng việc Cedar tham chiếu `context.input.user_id` khi trường không có trong schema, và tổ hợp "tùy chọn + `has`", **chưa thử** [SĐ]; (b) từ trong Lambda không phân biệt được `user_id` do interceptor đặt với do client gửi, nên cần kiểm thử CI rằng gateway luôn có interceptor và policy engine ở `ENFORCE`. Xem [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 3 và mục 8.

Luồng "on-behalf-of" của AgentCore Identity (RFC 8693) dành cho dịch vụ ngoài như Salesforce; các hàm `@requires_access_token`, `GetWorkloadAccessTokenForJWT` thuộc nhánh outbound tới dịch vụ bên thứ ba. Dùng khi gọi API ngoài, **không cần** cho Lambda nội bộ. [TL][SĐ] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/on-behalf-of-token-exchange.html **[Đọc lại tài liệu 2026-11-21, chưa chạy thử]** (spike Gateway đối chiếu bảng "outbound authorization", không dựng target loại khác để thử): **Lambda target chỉ có gateway service role** (không token exchange, không passthrough); passthrough chỉ có cho target Runtime (HTTP), token exchange cho MCP server/OpenAPI. Header `Authorization` do interceptor đặt cũng vô nghĩa với Lambda target (chỉ có header allowlist qua `client_context`). Xem [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 3c.

### 3.3 Gateway

- **Gateway** = một endpoint MCP `https://<gatewayId>.gateway.bedrock-agentcore.<region>.amazonaws.com/mcp`. Loại target: `lambda` (ARN Lambda + schema tool), `mcpServer`, `apiGateway`, `openApiSchema`, `smithyModel`, và target HTTP/Runtime/inference. Mỗi gateway ≤100 target, mỗi target ≤1.000 tool; schema inline ≤1 MB. [TL]
- **Inbound auth**: `CUSTOM_JWT` (khuyên dùng; Cognito `GatewayAuthorizer.usingCognito({userPool, allowedClients})` trong L2), `AWS_IAM`, hoặc `NONE`/`AUTHENTICATE_ONLY` (chỉ chấp nhận được nếu đã chuyển quyền quyết định cho policy engine/interceptor). **Outbound auth cho Lambda target: chỉ IAM role của gateway** (`GATEWAY_IAM_ROLE`; role cần `lambda:InvokeFunction`). [TL]
- **Schema tool Lambda** (JSON Schema rút gọn; `$ref/$defs` không được; kiểu `string|number|integer|boolean|array|object`): [TL]

```json
{ "name": "get_jar_balances",
  "description": "Số dư và hạn mức từng hũ của người dùng hiện tại",
  "inputSchema": { "type": "object",
    "properties": { "user_id": {"type": "string", "description": "sub của JWT; agent tự điền"} },
    "required": ["user_id"] } }
```
- **Kiểm tham số** **[Đã chạy thử 2026-11-21]**: Gateway kiểm `required` và kiểu (thiếu trường hoặc sai kiểu trả `result.isError=true` với `ValidationException`; số thay chuỗi, chuỗi thay số, `1.5` thay `integer`, `"true"` thay `boolean` đều bị chặn) nhưng **không từ chối tham số thừa** (`evil: "x"` vẫn tới Lambda), nên Lambda phải bỏ qua tham số lạ. Interceptor chạy trước bước kiểm này nên tiêm được tham số `required`. [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 1 và 3a.
- **Đặt tên**: tên target khớp `([0-9a-zA-Z][-]?){1,100}`: **không có dấu chấm hay gạch dưới**. Tool MCP = `${target}___${tool}`. Lambda phải tự cắt tiền tố: `context.client_context.custom['bedrockAgentCoreToolName']` rồi cắt sau `___`. Một Lambda có thể phục vụ nhiều tool của cùng target. ~~Tên tool tối đa 128 ký tự trong schema.~~ [TL] **[Đã chạy thử 2026-11-21]** giới hạn 128 **không được Gateway cưỡng chế**: tool 128 và cả 129 ký tự, `get.x`, `get-x`, `a___b` đều tạo được (READY). Tên **target**: 100 chữ-số được, 101 bị `ValidationException` (chuỗi `a-a-a-...` dài 199 ký tự khớp pattern nên cũng được); gạch dưới và dấu chấm bị từ chối. Tên **gateway**: pattern `([0-9a-zA-Z][-]?){1,48}`. Giới hạn thực tế đến từ phía model: tên tool Bedrock Converse tối đa 64 ký tự và chỉ `[a-zA-Z0-9_-]` [SĐ, suy từ kiến thức về Converse, chưa kiểm]; giữ `<target>___<tool>` ngắn. [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 1. https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-tool-naming.html và `gateway-add-target-lambda.html`
- **CDK** (mẫu chính thức gần nhất, có Cedar + Cognito + Lambda target): [BL] https://github.com/aws-samples/serverless-patterns/tree/main/agentcore-gateway-cedar

```ts
const gateway = new agentcore.Gateway(this, 'Gateway', {
  role: gatewayRole,                               // tin bedrock-agentcore.amazonaws.com + SourceAccount/SourceArn
  protocolConfiguration: agentcore.GatewayProtocol.mcp({
    supportedVersions: [agentcore.MCPProtocolVersion.MCP_2025_06_18] }),
  authorizerConfiguration: agentcore.GatewayAuthorizer.usingCognito({ userPool, allowedClients: [client] }),
  policyEngineConfiguration: { policyEngine, mode: agentcore.PolicyEngineMode.LOG_ONLY },
});
const ledger = gateway.addLambdaTarget('ledger', {      // tên target = "ledger"
  gatewayTargetName: 'ledger', lambdaFunction: ledgerFn,
  toolSchema: agentcore.ToolSchema.fromInline([ /* {name, description, inputSchema} ... */ ]),
});
// policy.node.addDependency(ledger): policy kiểm tên action theo tool của gateway nên tạo target trước
```
- **Tìm tool theo ngữ nghĩa**: bật `protocolConfiguration.mcp.searchType: SEMANTIC` khi tạo gateway; gateway thêm tool `x_amz_bedrock_agentcore_search` (`arguments: {"query": "..."}`). Có ở Singapore. Quota mặc định **25 lượt tìm/phút**, tool-call 200 TPS. Giá $0,025/1.000 lượt tìm + $0,02/100 tool được lập chỉ mục mỗi tháng. Tool bị Cedar chặn không hiện trong `tools/list`. [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-using-mcp-semantic-search.html. Với ~24 tool, nên chia sẵn theo specialist hơn là phụ thuộc tìm kiếm. [SĐ] **[Đã chạy thử 2026-11-21]** bật search **không** ẩn các tool khác: `tools/list` vẫn trả đủ mọi tool cộng `x_amz_bedrock_agentcore_search` (`inputSchema: {query: string}`, `query` bắt buộc), muốn LLM chỉ thấy tập con thì lọc phía agent. Tìm kiếm tiếng Việt chạy tốt ("chuyển tiền giữa các hũ" xếp `ledger___move_between_jars` đầu; "xem số dư" xếp `ledger___get_jar_balances` đầu), 320 đến 370 ms mỗi lần; `searchType` đặt lúc tạo và **không đổi được** sau đó; gọi tool thường qua gateway semantic vẫn chạy. [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 7.
- **Gọi từ Strands**: [TL] (ví dụ trong trang semantic search)

```python
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client
mcp = MCPClient(lambda: streamablehttp_client(GATEWAY_URL, headers={"Authorization": f"Bearer {jwt}"}))
with mcp:
    tools = mcp.list_tools_sync()        # có phân trang qua pagination_token
    agent = Agent(tools=tools)
```
  Tên tool lộ ra là `ledger___get_jar_balances`; có thể lọc theo tiền tố để mỗi specialist chỉ nhận tool của mình. Chưa xác minh tùy chọn alias/đổi tên trong `MCPClient`. [SĐ] **[Đã chạy thử 2026-11-21, MCP server cục bộ, chưa thử Gateway thật]** với `mcp` 2.3.0 hàm `streamablehttp_client` ở mẫu trên **không còn** (dùng `streamable_http_client`, không còn tham số `headers=`: đặt header trên `http_client` hoặc dùng `MCPClient(url=..., headers=...)`); `MCPClient` nhận `prefix=` (thêm tiền tố bằng gạch dưới, ví dụ `gateway_get_jar_balances`), nhưng `call_tool_sync` nhận tên gốc phía server. Xem [spike-strands-agui-local.md](spike-strands-agui-local.md) mục 2.9.
- Lỗi hay gặp: target kẹt `SYNCHRONIZING` do schema có `$ref/$defs`; `AccessDenied` khi gọi target (role gateway thiếu `lambda:InvokeFunction`); `UpdateGateway` yêu cầu truyền lại **mọi** trường đã đặt; bật `exceptionLevel: DEBUG` khi debug, tắt ở production; trace/log của gateway phải bật riêng (không tự bật); sự kiện `InvokeGateway` là data event của CloudTrail, phải bật thủ công. [TL] **[Đã chạy thử 2026-11-21]** thêm: policy gắn engine phải tạo **sau** target (resource là ARN gateway, schema Cedar sinh từ tool), rồi mới gắn engine vào gateway bằng `UpdateGateway`; policy lỗi là `CREATE_FAILED` **bất đồng bộ** (đọc `statusReasons`); `UpdateGateway` bỏ trường nào là **gỡ** trường đó (engine, interceptor), nên luôn đọc `GetGateway` rồi ghi đè; thay đổi policy/engine có hiệu lực sau vài giây (nghỉ 8 s là đủ). Interceptor cần `passRequestHeaders: true` để thấy `Authorization`, và role gateway cần `lambda:InvokeFunction` trên Lambda interceptor. [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 3a, 3b và 4.

### 3.4 Policy (Cedar)

- **Mô hình**: policy engine là tập policy; gắn vào gateway bằng `policyEngineConfiguration {arn, mode}`. **Mặc định từ chối** (không có `permit` khớp thì từ chối), **`forbid` thắng `permit`**, hai `permit` cho cùng action là phương án thay thế chứ không giao nhau (muốn "cả hai điều kiện" thì dồn vào một `permit` hoặc dùng `forbid ... unless`). [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/example-policies-action-resource.html
- **Chế độ chỉ ghi log**: hai tầng. Engine: `mode: LOG_ONLY` (không policy nào chặn) hoặc `ENFORCE`. Từng policy: `enforcementMode: LOG_ONLY|ACTIVE` (mặc định ACTIVE). Quan sát qua span (bật tracing của gateway) và metric `AWS/Bedrock-AgentCore`: `LogOnlyMatches`, **`LogOnlyDecisionFlips`** (số request mà policy sẽ đổi quyết định nếu bật; bằng 0 liên tục thì yên tâm bật), `LogOnlyEvalIncomplete`. Thay đổi có hiệu lực sau vài giây (nhất quán cuối cùng). Quy trình cho Yofina: engine `LOG_ONLY` → chạy bộ test đối kháng 50 câu và demo → kiểm `LogOnlyDecisionFlips` → chuyển `ENFORCE`. [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-test-a-policy.html **[Đã chạy thử 2026-11-21]** ở `LOG_ONLY` cấp engine **mọi lời gọi đều qua** và client luôn thấy thành công (6/6 ca của bộ test được Lambda chạy, kể cả ghi vượt hạn mức 9 triệu, ghi của người khác, đọc của người khác): đừng chạy `LOG_ONLY` với tool ghi thật. Quyết định xem ở **metric** `AWS/Bedrock-AgentCore` (bật sẵn, không cần cấu hình; dimension `PolicyEngine`, `OperationName`, `Mode`, `ToolName`, `TargetResource`): đã thấy `AllowDecisions`, `DenyDecisions`, `NoDeterminingPolicies`, `DeterminingPolicies`, `MismatchErrors`, `PolicyMismatch` với `Mode=LOG_ONLY`. `LogOnlyDecisionFlips` và `LogOnlyMatches` **chỉ xuất hiện khi dùng `enforcementMode=LOG_ONLY` ở cấp từng policy** (cấp engine không sinh ra). Log ứng dụng của Gateway **không** ghi quyết định policy; chi tiết từng quyết định (`aws.agentcore.policy.authorization_decision`, `determining_policies`) nằm ở span trong `aws/spans`, cần bật tracing của Gateway và CloudWatch Transaction Search (chưa bật trong spike, nên chưa xác minh). Policy ở `LOG_ONLY` cấp policy không còn đóng góp quyết định: nếu là `permit` duy nhất thì tool vẫn bị từ chối mặc định. [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 4.
- **Cú pháp phạm vi**: [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-scope.html
  - principal: `AgentCore::OAuthUser` (id = `sub`; claim khác = tag, **mọi claim là chuỗi**, mảng thành văn bản JSON, so bằng `like`; phải `hasTag` trước `getTag`).
  - action: `AgentCore::Action::"<target>___<tool>"`, **không có wildcard** (liệt kê `action in [...]`, hoặc `action in AgentCore::Action::"<target>"` cho cả target nhưng khi đó không đặt điều kiện trên tham số).
  - resource: nếu nêu action cụ thể thì **bắt buộc** `resource == AgentCore::Gateway::"<ARN>"`; nếu action để trống thì `resource is AgentCore::Gateway`.
  - tham số tool ở `context.input.<tên>`: `string` so bằng `==`/`like`; `integer` thành `Long` (`<=` được); `number` thành `decimal` (chỉ `.lessThanOrEqual(decimal("1000.00"))` v.v., không dùng `<`); `boolean` dùng thẳng; tham số tùy chọn phải `context.input has <tên>` trước khi đọc, nếu không policy bị từ chối lúc tạo (`CREATE_FAILED` bất đồng bộ).
- **Cú pháp đã chạy thật** **[Đã chạy thử 2026-11-21]**: `principal.id` hợp lệ (chuỗi `sub`); mọi claim khác là **tag**, **kể cả `sub`** (`principal.hasTag("sub")` đúng), ví dụ `forbid(...) when { principal.hasTag("username") && principal.getTag("username") == "user-b" }` chạy đúng; `context.input has confirm_token && context.input.confirm_token like "*.*"` hợp lệ cho tham số string tùy chọn; `<=` trên `integer` và `boolean` dùng thẳng chạy đúng; tham số `required` bị thiếu khi đánh giá thì policy báo "evaluation error" (`Property user_confirmed is missing but required`) và lời gọi bị từ chối; một `permit` vô điều kiện bị từ chối lúc tạo (`CREATE_FAILED`, finding `Overly Permissive`) khi `validationMode=FAIL_ON_ANY_FINDINGS` (tạo được với `IGNORE_ALL_FINDINGS`); `UpdatePolicy(enforcementMode="LOG_ONLY"|"ACTIVE")` chạy; thông điệp từ chối nêu tên policy khi gateway tạo với `exceptionLevel=DEBUG` (bản không DEBUG có che lý do không thì **chưa thử**). `boto3` 1.44.9 nhận `definition={"cedar": {"statement": ...}}`, trong khi một số ví dụ CLI viết `{"policy":{"statement":...}}`: dùng đúng theo model SDK đang cài. [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 3b.
- **Dạng phản hồi khi Cedar từ chối** **[Đã chạy thử 2026-11-21]**: HTTP 200, lỗi giao thức JSON-RPC `{"error":{"code":-32002,"message":"Tool Execution Denied: Tool call not allowed due to policy enforcement [...]"}}` (mặc định từ chối: `[No policy applies to the request (denied by default).]`), **không phải** tool result `isError`. Tool không tồn tại: `-32602 Unknown tool`. Client `mcp` Python: `call_tool` ném `McpError` bọc trong `ExceptionGroup` (do `anyio` TaskGroup), không trả `CallToolResult`: lớp bọc MCP của agent phải bắt và đổi thành thông điệp tool lỗi cho LLM; hành vi mặc định của Strands `MCPClient` **chưa thử**. Interceptor `deny` và `ValidationException` của schema thì ra `result.isError=true`, khác đường này. Tool bị từ chối vĩnh viễn với principal (chưa có `permit` nào) **ẩn khỏi `tools/list`**; tool có `permit` có điều kiện vẫn hiện. [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 4.
- **Luật mẫu 1, tool đọc: chỉ đọc dữ liệu của chính chủ JWT** (adaptation của mẫu "principal-scoped" và "action-scoped", tool `ledger___get_jar_balances` có tham số bắt buộc `user_id`). Tạo một policy mỗi tool (vòng lặp trong CDK như mẫu BL): [TL][SĐ]

```cedar
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"ledger___get_jar_balances",
  resource == AgentCore::Gateway::"arn:aws:bedrock-agentcore:ap-southeast-1:<ACCOUNT>:gateway/<GATEWAY_ID>"
) when {
  context.input.user_id == principal.id
};
```

- **Luật mẫu 2, tool ghi: cần cờ xác nhận và nằm trong hạn mức** (tool `ledger___move_between_jars`, `amount_vnd` kiểu `integer`, `user_confirmed` kiểu `boolean`, cả hai `required`). Cú pháp theo các mẫu `Integer comparison`, `Boolean condition` và `Constrain a job title and its input together`: [TL][SĐ]

```cedar
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"ledger___move_between_jars",
  resource == AgentCore::Gateway::"arn:aws:bedrock-agentcore:ap-southeast-1:<ACCOUNT>:gateway/<GATEWAY_ID>"
) when {
  context.input.user_id == principal.id &&
  context.input.user_confirmed &&
  context.input.amount_vnd <= 5000000
};
```
  Tool ghi **không có** `permit` nào khác, nên mọi lời gọi thiếu cờ hoặc vượt hạn mức rơi vào mặc định từ chối. Muốn chặn cứng bất kể `permit` khác thì thêm `forbid ... unless { ... }` cùng điều kiện (mẫu "Forbid everyone except a set of roles" giải thích khác biệt).
- **Trần tổng theo thời gian** (tùy chọn, Dogwood "temporal" tương thích Cedar, có ở Singapore): `forbid` khi tổng `amount_vnd` trong 24 giờ vượt ngưỡng, cần gửi header `x-amzn-bedrock-agentcore-policy-session-id` ở **mọi** request và tool phải có `integer`. Tài liệu ghi rõ **không phải kiểm soát an ninh** vì client tự chọn session id (đổi session là đếm lại); chỉ để chặn agent lặp vòng. Thêm hoặc sửa policy temporal sẽ vô hiệu hóa các session đang mở (HTTP 409, phải tạo session mới). Cú pháp xem mẫu "Cap a running total" tại https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/example-policies-temporal.html [TL]
- **Quyền IAM cho role của gateway** để đánh giá policy: `bedrock-agentcore:GetPolicyEngine`, `AuthorizeAction`, `PartiallyAuthorizeActions` (L2 của CDK cấp sẵn khi dùng `policyEngineConfiguration`; nếu nối bằng L1 thì tự cấp). Temporal cần thêm `GetWorkloadAccessToken`. [TL][BL] **[Đã chạy thử 2026-11-21]** với target Lambda, role gateway chỉ cần `lambda:InvokeFunction` (Lambda tool và Lambda interceptor) cộng `bedrock-agentcore:GetPolicyEngine`, `AuthorizeAction`, `PartiallyAuthorizeActions`; **không** cần `InvokeGateway`. Trust policy với điều kiện `aws:SourceAccount` và `aws:SourceArn` trên `gateway/*` dùng được. [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 3b.
- **Sinh luật từ ngôn ngữ tự nhiên** (`StartPolicyGeneration`, ≤2.000 ký tự, tài sản sinh ra tự xóa sau 7 ngày) chỉ để phác thảo; luôn đọc lại. Findings `ALLOW_ALL`, `DENY_ALL`, `INVALID`… làm `FAIL_ON_ANY_FINDINGS` từ chối. [TL]
- Giới hạn: policy ≤10 KB, tổng ≤200 KB mỗi engine, schema Cedar ≤400 KB (tăng theo số tool và độ phức tạp tham số), ≤1.000 policy, ≤20 policy temporal. Tên policy/engine: `[A-Za-z][A-Za-z0-9_]*`, ≤48 ký tự, không đổi được. [TL]
- Vấn đề cần nói thẳng: Cedar tại Gateway **không thấy** nội dung hội thoại (chỉ tham số tool và claim); và không kiểm tra được "người dùng thật sự bấm xác nhận". Xem mục 4. **[Đã chạy thử 2026-11-21]** đúng như vậy: Cedar không có phép HMAC lẫn trạng thái "đã dùng"; kiểm token phải nằm trong Lambda tool. Xem [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 5.

### 3.5 Memory

- **Hai loại**: ngắn hạn = chuỗi **event** theo `actorId` + `sessionId` (hết hạn sau 3–365 ngày, tối thiểu 7 ở bảng quota; mỗi event ≤10 MB, ≤100 message); dài hạn = **memory record** do **strategy** trích xuất bất đồng bộ, lưu trong **namespace**. Không có strategy thì không có bộ nhớ dài hạn. Tối đa 6 strategy mỗi memory, 150 memory mỗi Region. [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-types.html
- **Strategy dựng sẵn**: `SEMANTIC` (sự thật), `USER_PREFERENCE` (sở thích), `SUMMARIZATION` (tóm tắt phiên), `EPISODIC` (có reflection). Có "built-in with overrides" (`customMemoryStrategy` với `appendToPrompt` và `modelId`, cần `memoryExecutionRoleArn`, rẻ hơn khi lưu) và **self-managed** (trigger theo số tin/token/idle, payload giao qua SNS+S3, bạn tự trích rồi nạp bằng `BatchCreateMemoryRecords`). Ánh xạ với proposal §9: sở thích → USER_PREFERENCE; sự thật → SEMANTIC; tóm tắt phiên → SUMMARIZATION; hành vi (pipeline đêm) và bài học của agent → self-managed + `BatchCreateMemoryRecords` (mỗi record cần `memoryStrategyId` và `namespaces`; ≤100 record mỗi lần). Việc "tạo một strategy self-managed chỉ để có ID" chưa chạy thử. [TL][SĐ]
- **Namespace theo người dùng**: dạng phân cấp, **có dấu `/` ở đầu và cuối** để tránh va chạm tiền tố (`/actors/alice/` chứ không phải `/actors/alice`); biến `{actorId}`, `{sessionId}`, `{memoryStrategyId}`. Ví dụ: `/users/{actorId}/preferences/`, `/users/{actorId}/facts/`, `/users/{actorId}/summaries/{sessionId}/`, `/users/{actorId}/behavior/`. (Ví dụ trong guide của MCP agentcore bỏ dấu `/`; làm theo trang namespace chính thức.) [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-organization.html
- **Tích hợp Strands**: [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/strands-sdk-memory.html

```python
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig, RetrievalConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
cfg = AgentCoreMemoryConfig(
    memory_id=MEMORY_ID, session_id=session_id, actor_id=sub_from_jwt,
    retrieval_config={"/users/{actorId}/preferences/": RetrievalConfig(top_k=5, relevance_score=0.7),
                      "/users/{actorId}/facts/": RetrievalConfig(top_k=5, relevance_score=0.7)},
    batch_size=1)               # >1 thì phải dùng "with" hoặc close(), nếu không mất tin chưa gửi
with AgentCoreMemorySessionManager(cfg, region_name="ap-southeast-1") as sm:
    agent = Agent(session_manager=sm, ...)
```
  Với `ag-ui-strands` truyền qua `StrandsAgentConfig(session_manager_provider=...)` (mẫu FAST). Mỗi request tạo session manager và agent mới theo `actor_id`. Quota đáng nhớ: `CreateEvent` 5 lượt/giây mỗi actor-session; `RetrieveMemoryRecords` 30 TPS mỗi tài khoản (điều chỉnh được). [TL][BL]
- **Độ trễ trích xuất**: tài liệu chỉ nói trích xuất là **bất đồng bộ nền**, không nêu số giây; quota 150.000 token/phút cho trích xuất. Không dựa vào bộ nhớ dài hạn trong cùng phiên; để test thì dùng `StartMemoryExtractionJob`/`ListMemoryExtractionJobs`. **Chưa tìm được số liệu**, tự đo. [TL]
- **Xóa theo yêu cầu**: không tìm thấy API xóa theo actor. Quy trình: `ListMemoryRecords(namespacePath="/users/<id>/")` rồi `BatchDeleteMemoryRecords` (≤100/lần), và `ListSessions(actorId)` → `ListEvents` → `DeleteEvent` (20 TPS toàn tài khoản, 5 mỗi actor-session). Event tự hết hạn theo `eventExpiryDuration`; record có thể đặt TTL (`recordExpirySpecification`). Muốn che dữ liệu nhạy cảm: Memory luôn mã hóa at-rest (có thể dùng KMS key riêng qua `encryptionKeyArn`); metadata của event không mã hóa bằng CMK nên đừng đưa dữ liệu nhạy cảm vào. [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/long-term-delete-memory-records.html
- **Rủi ro với proposal**: proposal §7 nói che số tài khoản, số điện thoại, tên người nhận trước khi ghi bộ nhớ. `AgentCoreMemorySessionManager` ghi tin nhắn thô; **chưa tìm được tùy chọn che dữ liệu** trong session manager. Tài liệu khuyên làm sạch đầu vào bằng Guardrails trước `CreateEvent` và cảnh báo memory poisoning/prompt injection qua trích xuất bằng LLM. Cần tự bọc (hook trước khi ghi) hoặc chỉ lưu ngữ cảnh đã che. [TL][SĐ] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/best-practices.html
- Có thể tạo memory bằng `agentcore add memory --strategies SEMANTIC,SUMMARIZATION,USER_PREFERENCE` hoặc L2 `agentcore.Memory({ memoryStrategies: [MemoryStrategy.usingBuiltInSemantic(), ...], expirationDuration })`. `agentcore dev` không có Memory cục bộ: phải deploy memory rồi chạy local nối vào đó, hoặc giả lập. [TL][BL]

### 3.6 Observability và Evaluations

#### Trace OpenTelemetry

- **Runtime tự gắn ADOT** khi deploy bằng CLI/CDK; trong `entryPoint` dùng `opentelemetry-instrument` và thêm `aws-opentelemetry-distro~=0.21.0` (≥0.18.0 mới có đích span theo agent). Một lần cho mỗi tài khoản: bật **CloudWatch Transaction Search** (`agentcore deploy` tự làm; hoặc `aws xray update-trace-segment-destination --destination CloudWatchLogs` + resource policy cho `logs:PutLogEvents`); span khả dụng sau tối đa ~10 phút kể từ lúc bật. Index 1% trace miễn phí. [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-get-started.html
- **Xem ở đâu**: console AgentCore Observability hoặc CloudWatch **GenAI Observability** (tab Overview, Sessions, Traces, Spans); log runtime `/aws/bedrock-agentcore/runtimes/<agent_id>-<endpoint>`; span ở stream `spans` cùng log group (hoặc `aws/spans`); metric namespace `bedrock-agentcore`. Với Memory và Gateway phải **tự bật** tracing và log delivery. Từ 16/11/2026 `OTEL_RESOURCE_ATTRIBUTES` được gộp với thuộc tính của AgentCore (đã có hiệu lực). [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html
- **Lấy `trace_id` trả cho client**: tài liệu nói truyền trace ID bằng header `X-Amzn-Trace-Id` (định dạng X-Ray) hoặc `traceparent` (W3C) khi gọi runtime; không có trace ID thì OTEL tự sinh. Hai cách dùng: (1) client/BFF sinh `traceparent` mỗi lượt, lưu vào bảng `audit_events` làm `trace_id` [bám tài liệu]; (2) trong agent lấy từ OTel (`trace.get_current_span().get_span_context().trace_id` định dạng hex) và phát một sự kiện AG-UI `CUSTOM` hoặc đưa vào khối `explain`/`RUN_FINISHED.result` [SĐ]. Chọn (1) cho đơn giản và chắc: trace_id có trước khi agent chạy, ghi audit được cả khi agent lỗi. Gọi runtime còn nên gửi `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` để span gắn đúng session. [TL][SĐ] **[Đã chạy thử 2026-11-21]** client gửi `traceparent` thì trace id giữ nguyên tới app (dịch vụ chỉ đổi parent-id) và đồng thời được quy đổi thành `Root=` của `X-Amzn-Trace-Id`; chỉ gửi `X-Amzn-Trace-Id` thì `Root` cũng giữ nguyên. Phản hồi **không** trả trace id về client (cũng không expose `traceparent`), nên client phải tự sinh. Log app (stdout) nằm ở `/aws/bedrock-agentcore/runtimes/<id>-DEFAULT`. Span OTel **chưa xác nhận**: tài khoản chưa bật Transaction Search (xuất span trả 400) và spike không đổi cấu hình tài khoản. Entry `opentelemetry-instrument` chạy được nhưng cold start V1 từ 2,7 s lên 5,2 s.
- Lỗi hay gặp: không thấy span vì chưa bật Transaction Search hoặc chưa đợi ~10 phút; ADOT cũ hơn 0.18.0 bỏ qua đích span riêng; đừng đưa bí mật vào `OTEL_RESOURCE_ATTRIBUTES` (nằm trong trace). [TL]

#### Evaluations

- **Evaluator dựng sẵn** (ID dạng `Builtin.<Tên>`, ví dụ `Builtin.Helpfulness`; judge LLM, cấu hình không sửa được), theo mức: **session** `GoalSuccessRate` (có biến thể ground truth); **trace** `Coherence`, `Conciseness`, `Correctness` (có ground truth), `Faithfulness`, `Harmfulness`, `Helpfulness`, `InstructionFollowing`, `Refusal`, `ResponseRelevance`, `Stereotyping`; **tool** `ToolParameterAccuracy`, `ToolSelectionAccuracy`; thêm evaluator của bên thứ ba (DeepEval, AutoEval) và evaluator về skill. Danh sách theo các mẫu prompt trong tài liệu; xác minh ID chính xác bằng `agentcore eval evaluator list` hoặc API `ListEvaluators` (trả built-in trước). [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/prompt-templates-builtin.html
- **Tự viết bằng code** (Lambda, không dùng LLM): cùng Region với tài nguyên Evaluations, timeout 1–300 giây (mặc định 60), payload ≤6 MB. Nhận `evaluationLevel` (`TRACE`|`TOOL_CALL`|`SESSION`) và `evaluationInput.sessionSpans`; trả `{"label":"PASS","value":1.0,"explanation":"..."}` hoặc `{"errorCode":..., "errorMessage":...}`. SDK có decorator `@code_based_evaluator()` (`bedrock_agentcore.evaluation.code_based_evaluators`). `NumericGrounding` = duyệt span của lượt (`gen_ai.completion` của agent, kết quả tool trong span tool) và so mọi con số; `SchemaValidity` = `json.loads` + kiểm Pydantic; `SuitabilityCompliance` = kiểm khối `confirm`/`options` với luật. Tên thuộc tính span của tool result **chưa xác minh**, mở một trace thật để xem trước khi viết. Khi online config đang bật thì evaluator bị khóa (không sửa/xóa được). Cũng có LLM-as-a-judge tự viết (chọn model và prompt) khi cần. [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/code-based-evaluators.html
- **Online**: `CreateOnlineEvaluationConfig` (`agentcore add online-eval --agent ... --evaluators ... --sampling-rate 0.1`): lấy mẫu phiên thật từ CloudWatch Logs, ≤25 evaluator mỗi config, cần execution role. **On-demand**: `Evaluate` trên span của phiên/trace chọn sẵn (1 evaluator mỗi lần gọi; ≤20.000 span), dùng cho bộ câu chuẩn và CI (`OnDemandEvaluationDatasetRunner` trong SDK: gọi agent, chờ ingest, lấy span, gọi Evaluate). Có thêm batch evaluation (rẻ hơn 25%). Proposal "đánh giá offline mỗi lần đổi prompt" khớp với on-demand/batch. [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/on-demand-evaluations.html
- Ở Singapore: **200 lượt đánh giá dựng sẵn mỗi phút** (nơi khác 1.200, không tăng được), 1.000.000 token đầu vào/phút; judge dựng sẵn dùng global cross-region inference nên prompt và kết quả có thể được xử lý ngoài Singapore (dữ liệu vẫn lưu ở Region gốc). Nếu cần tránh, tự tạo evaluator tùy biến. Dữ liệu demo là tổng hợp nên chấp nhận được; ghi vào đánh giá rủi ro dữ liệu cá nhân nếu chạy thật. [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/evaluations-cross-region-inference.html

### 3.7 Region: `ap-southeast-1` so với `us-east-1`

Kiểm ngày **2026-11-21** bằng bảng "Supported AWS Regions" của tài liệu AgentCore và công cụ `get_regional_availability` (AWS MCP; công cụ này chỉ nhận mức sản phẩm/API, không có từng tính năng con, nên lấy bảng tài liệu làm chuẩn).

| Thành phần | ap-southeast-1 (Singapore) | us-east-1 | Ghi chú |
|---|---|---|---|
| Runtime microVMs | Có | Có | cả platform V2 |
| Runtime Instances | Có | Có | không dùng |
| Memory | Có | Có | |
| Gateway | Có | Có | semantic search có ở cả hai |
| Identity | Có | Có | |
| Built-in tools (Browser, Code Interpreter) | Có | Có | không dùng |
| Observability | Có | Có | Transaction Search và OTLP có (get_regional_availability) |
| Policy in AgentCore | Có | Có | cả temporal và policy generation |
| Evaluations | Có | Có | **Singapore 200 lượt/phút dựng sẵn, judge qua global CRIS** |
| AgentCore harness (cấu hình, không viết loop) | Có | Có | không dùng, cần Strands Graph |
| Payments | Có | Có | không dùng |
| AWS Agent Registry | **Không (đang lên kế hoạch)** | Có | không cần cho MVP |
| Web Search Tool/API | **Không** | Có | không cần (tri thức đã có KB) |

Cách xác nhận bằng API: `get_regional_availability` trả `isAvailableIn` cho `Bedrock AgentCore Control+CreateAgentRuntime`, `CreateGateway`, `CreatePolicyEngine`, `CreateMemory`, `CreateEvaluator`, `CreateOnlineEvaluationConfig` ở cả hai Region. Mô hình Bedrock (Claude, Nova, embedding), Guardrails, Knowledge Bases, Data Automation ở Singapore **không thuộc phạm vi ghi chú này**, do agent khác kiểm; riêng Knowledge Bases được báo `isAvailableIn` ở Singapore trong cùng lần gọi. Phải kiểm model/inference profile cho Strands (`BedrockModel(model_id=...)`) trước khi chốt model. [TL][BL]

### 3.8 Chi phí (đủ để ước lượng demo)

Giá lấy từ https://aws.amazon.com/bedrock/agentcore/pricing/ (đọc 2026-11-21; trang không nói giá có khác theo Region không, và không nói riêng giá Singapore; **giả định giá như nhau, cần kiểm Billing**). Khách hàng mới có thể có tới $200 tín dụng Free Tier (theo trang). [TL]

| Thành phần | Đơn vị tính | Giá |
|---|---|---|
| Runtime V2, chế độ tiêu thụ | theo giây, mức dùng thực; CPU về 0 khi chờ I/O; bộ nhớ nhàn rỗi thu hồi sau 120 giây | $0,1276/vCPU-giờ; $0,0169/GB-giờ |
| Runtime V1 | như trên | $0,0895/vCPU-giờ; $0,00945/GB-giờ |
| Runtime V2 baseline cam kết | | $0,0997/vCPU-giờ; $0,0132/GB-giờ (công bố "ra mắt trước tháng 10/2026") |
| Lưu mã | ECR (container) hoặc S3 (zip); mạng theo giá EC2 | |
| Gateway | lời gọi API (List/Invoke/Ping) | $0,005 / 1.000 |
| | tìm kiếm | $0,025 / 1.000 |
| | lập chỉ mục tool | $0,02 / 100 tool / tháng |
| Identity | token/API key cho tài nguyên ngoài AWS (miễn phí khi đi qua Runtime/Gateway) | $0,010 / 1.000 |
| Memory ngắn hạn | ingest (event tối thiểu 12 KB, tối đa 64 KB) | $1,00/GB |
| | truy xuất | $0,20/GB |
| | lưu (theo giờ trong TTL) | $0,10/GB-tháng |
| Memory dài hạn | lưu, built-in | $0,75 / 1.000 record / tháng |
| | lưu, override hoặc self-managed (model tính riêng) | $0,25 / 1.000 record / tháng |
| | truy xuất | $0,50 / 1.000 lượt |
| Policy | yêu cầu ủy quyền | $0,000025 (≈$25/triệu) |
| | sinh luật bằng ngôn ngữ tự nhiên | $0,13 / 1.000 token vào |
| Observability | tính qua CloudWatch (trang AgentCore không niêm yết giá riêng; ví dụ dùng $0,35/GB span, $0,50/GB log) | |
| Evaluations dựng sẵn | token vào | $0,0024 / 1.000 |
| | token ra | $0,012 / 1.000 |
| | evaluator tự viết (code hoặc LLM; LLM tính thêm trong tài khoản) | $1,50 / 1.000 lượt |
| | batch (rẻ hơn 25%) | $0,0018 vào, $0,009 ra / 1.000 token |

Ước lượng thô cho 3 tuần dev và demo (**số tự tính [SĐ]**, giả định 2.000 phiên, mỗi phiên 8 lượt, 6 lời gọi tool mỗi lượt, 180 giây tồn tại, 0,5 vCPU và 2 GB trung bình; chưa gồm token Bedrock cho LLM, Lambda, Aurora, v.v.):

- Runtime ≈ $0,005/phiên → khoảng **$10**.
- Gateway ≈ 60 lời gọi/phiên → khoảng **$0,6**; Policy ≈ 48 lượt/phiên × $0,000025 → khoảng **$2,4** (đắt hơn Gateway cùng khối lượng).
- Memory: truy xuất 8 lượt/phiên × $0,0005 → khoảng **$8**; event ngắn hạn và lưu dài hạn dưới $3.
- Observability (CloudWatch) vài USD.
- **Evaluations dựng sẵn**: một lượt đánh giá trace ≈ 5k token vào + 0,5k token ra ≈ $0,018; 8 trace × 2 evaluator + 1 session-level ≈ $0,37 mỗi phiên được chọn. Lấy mẫu 10% (200 phiên) ≈ **$73**; lấy mẫu 100% ≈ $730. Evaluator code-based: 24 lượt/phiên × $0,0015 ≈ $0,036/phiên.

Kết luận chi phí: toàn bộ AgentCore cho demo ≈ vài chục đến ~100 USD nếu lấy mẫu online ≤10% và dùng code-based cho chỉ tiêu số; **đừng bật sampling 100% với judge LLM**. Runtime chỉ tính tiền khi có mức dùng nên không cần xóa ngoài giờ, nhưng nhớ `StopRuntimeSession` cho session treo và đặt budget alarm (skill `aws-core:aws-billing-and-cost-management`).

## 4. Khuyến nghị cho Yofina: áp vào kiến trúc proposal, chỗ cần chỉnh

**Giữ nguyên được** (đã xác minh khả thi ở Singapore): Runtime chạy Strands với AG-UI qua SSE, JWT authorizer Cognito, Gateway biến Lambda thành MCP, Cedar mặc định từ chối với chế độ chỉ ghi log, Memory theo `actorId`, Observability, Evaluations với evaluator tự viết, job nền.

**Chỉnh/cần quyết định** (xếp theo mức ảnh hưởng đến tiến độ và an toàn):

1. **Tên tool `ledger.*` trong proposal không tồn tại**: Gateway ghép `target___tool`. Đổi quy ước sang sáu target (`ledger`, `forecast`, `planner`, `knowledge`, `ingest`, `audit`) + tên tool `snake_case`; trong Cedar và code là `ledger___get_jar_balances`. Cập nhật `overview.md`/`project-structure.md` khi coordinator tổng hợp. Mỗi target một Lambda (`gateway/tools/ledger/` ...) khớp cấu trúc thư mục dự kiến. [TL] **[Đã chạy thử 2026-11-21]** `tools/list` trả đúng `ledger___get_jar_balances`; `overview.md` đã đổi toàn bộ danh mục tool sang cách đặt tên này ([../architecture/overview.md](../architecture/overview.md)). Xem [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 1.
2. **"Tool chỉ đọc dữ liệu của chủ JWT" không tự có**: Lambda target không nhận JWT. Phải thiết kế (mục 3.2): agent chuyển nguyên JWT cho Gateway, tool có `user_id`, Cedar ghim `user_id == principal.id`, interceptor ghi đè; Lambda lọc SQL theo `user_id`. Đây là việc nên làm trong **tuần 1** vì mọi tool phụ thuộc. [TL][SĐ] **[Đã chạy thử 2026-11-21]** phương án này chạy: agent chuyển nguyên access token, interceptor ghi đè `user_id` (lớp chính, độc lập với Cedar), Cedar `user_id == principal.id` là lớp thứ hai; Lambda lọc SQL theo `user_id` trong `event` (không tin header/tham số không do interceptor đặt). Xem mục 3.2 và [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 3 và 8.
3. **Cờ xác nhận trong Cedar (proposal §9) là chưa đủ**: LLM điền được tham số, nên prompt injection có thể tự đặt `user_confirmed: true`. Khuyến nghị: tool ghi trong Gateway chỉ tạo bản ghi **"đề xuất chờ xác nhận"** (không đổi số dư); khối UI `confirm` gọi một endpoint riêng (Lambda sau Cognito, không qua LLM) kèm `proposal_id` để áp dụng và ghi `audit_events`; hoặc tool ghi yêu cầu **mã xác nhận một lần** do backend ký (HMAC trên hành động + tham số + hạn dùng) mà Lambda kiểm. Giữ luật Cedar (`user_id`, hạn mức, cờ) làm lưới phụ. Cần chủ dự án duyệt vì lệch proposal. [SĐ] **[Đã chạy thử 2026-11-21]** phương án "mã xác nhận một lần do backend ký" chạy đúng trên 13 ca; Cedar chỉ là lưới phụ (hạn mức, khớp `user_id`, có mặt `confirm_token`), không kiểm được chữ ký; `user_confirmed` do LLM điền vô giá trị bảo mật. Cơ chế này vẫn là **đề xuất, chủ dự án chưa chốt**. Xem mục 2 điểm 10 và [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 5.
4. **CDK tự viết dùng L2 `aws-cdk-lib/aws-bedrockagentcore`**, không dùng `agentcore` CLI làm đường deploy chính (CLI sinh CDK riêng trong `agentcore/cdk/`, khó ghép với stack Aurora/EventBridge/Step Functions). Dùng CLI cho `agentcore dev`, `invoke`, `logs`, `traces` và để sinh mẫu đối chiếu. Policy có thể ở gói alpha tùy phiên bản (mẫu serverless-patterns dùng `agentcore.PolicyEngine` từ aws-cdk-lib; README alpha 2.277.0 vẫn ghi Policy là alpha): **kiểm khi cài**, nếu còn alpha thì nối vào gateway bằng L1 (`policyEngineConfiguration`) và cấp thêm quyền cho role gateway như README. [TL][BL]
5. **Container ARM64 từ máy Windows**: build local cần QEMU/buildx; ưu tiên build trên CodeBuild (đường `agentcore deploy` đã làm) hoặc CI ARM. ~~AG-UI gần như chắc chắn cần container (hợp đồng ghi containerized; FAST dùng docker). Thử `CodeZip` ở ngày đầu để biết.~~ [TL][BL][SĐ] **[Đã chạy thử 2026-11-21]** SAI: AG-UI chạy được với `CodeZip` (ARM64 wheel cài bằng `uv` từ Windows, không Docker/QEMU/CodeBuild). Xem mục 2 điểm 5 và [spike-agentcore-runtime-cors.md](spike-agentcore-runtime-cors.md) mục 1.
6. **Phần "job nền tới 8 giờ" của proposal quá mức cần**: mục tiêu thật là chục giây đến vài phút. Dùng `add_async_task` chỉ cho sinh lại lộ trình; nạp sao kê giữ qua SQS + Lambda (như proposal 10.6) và báo tiến độ qua `ingest.get_job_status`/polling. Token người dùng hết hạn sau 60 phút nên job không nên giữ JWT. [TL][SĐ]
7. **Bộ nhớ**: đừng mong "hồ sơ hành vi" tự có từ strategy dựng sẵn; kế hoạch "chiến lược custom" nên là self-managed + `BatchCreateMemoryRecords` do pipeline đêm ghi, namespace `/users/{actorId}/behavior/`. Phần "che PII trước khi ghi bộ nhớ" cần tự bọc quanh session manager. Xóa dữ liệu theo yêu cầu: viết một Lambda `privacy.delete_my_data` liệt kê và xóa theo namespace + event. Độ trễ trích xuất chưa biết: không dùng cho thông tin cần ngay trong phiên (số dư luôn đọc tươi qua tool, như proposal). [TL][SĐ]
8. **Evaluations**: giữ ba evaluator tự viết bằng Lambda (đúng thế mạnh, chi phí ~$1,5/1.000) và chỉ 1–2 evaluator dựng sẵn (`GoalSuccessRate`, `Correctness`) lấy mẫu thấp; dùng on-demand cho bộ câu chuẩn trước mỗi lần đổi prompt. Nhớ trần 200 lượt/phút ở Singapore khi chạy bộ chuẩn lớn. [TL]
9. **Trace**: để frontend/BFF sinh `traceparent` mỗi lượt và dùng làm `trace_id` hiển thị trong bảng "Vì sao"; `audit.get_trace` truy theo trace đó (CloudWatch Logs Insights trên log group runtime hoặc `aws/spans`). Cần bật tracing của Gateway và Memory riêng. [TL][SĐ]
10. **Tiến độ tuần 1**: tạo thủ công nhỏ (không scaffold lớn) một Runtime `HelloAgent` + Gateway + một Lambda tool + policy engine `LOG_ONLY` ở Singapore, chạy `agentcore dev` và gọi bằng JWT Cognito thật; đây là cách rẻ nhất để chốt các điểm chưa chắc ở mục 5. (Việc tạo tài nguyên thật cần chủ dự án đồng ý theo `aws-tooling.md`.)

**So với FAST**: FAST truyền danh tính bằng token M2M cộng Lambda pre-token, Cedar theo `department`, và tự ghi là proof-of-value. Hướng "chuyển nguyên JWT người dùng sang Gateway" ở mục 3.2 đơn giản hơn cho bài toán này (mỗi người dùng một dữ liệu riêng) nhưng khác FAST, nên có thể chạy thử song song hai hướng. [BL][SĐ]

## 5. Điều chưa chắc / cần chạy thử

| # | Điều chưa chắc | Cách kiểm |
|---|---|---|
| 1 | Cedar `context.input.user_id == principal.id` có qua validation và hoạt động như dự kiến không (`principal.id` là thuộc tính entity theo trang authorization flow, nhưng ví dụ trong tài liệu dùng `principal ==` hoặc tag) | ~~Tạo policy ở `LOG_ONLY`, gọi tool bằng hai JWT khác nhau, xem span quyết định~~ **[Đã chạy thử 2026-11-21] Đã đóng**: qua validation và chặn đúng (A đọc của B: từ chối; `principal.id` là `sub`), xem [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 3b. Span quyết định chưa xem được (chưa bật Transaction Search) |
| 2 | Thứ tự **interceptor request → policy engine** (tài liệu chỉ nói interceptor "short-circuit" bỏ qua policy) và việc ghi đè `arguments` có được policy nhìn thấy không | ~~Chạy thử có interceptor sửa `user_id`~~ **[Đã chạy thử 2026-11-21] Đã đóng**: `JWT authorizer -> interceptor -> Cedar (thấy tham số đã sửa) -> kiểm schema -> Lambda`, xem [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 4 |
| 3 | Interceptor thêm bao nhiêu độ trễ (mục tiêu F3 dưới 2 giây) | ~~Đo p95~~ **[Đã chạy thử 2026-11-21] Đã đóng**: cộng khoảng 50 đến 80 ms ở trạng thái ấm (tổng ấm dưới 200 ms; lần gọi lạnh 0,55 đến 1,8 s); đo một máy ở Việt Nam, nhiễu ±40 ms, chưa đo p95 thật hay cold start của chính Gateway. [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) mục 6 |
| 4 | AG-UI chạy được bằng `CodeZip` hay buộc container; tương thích `ag-ui-strands` 1.0.x với dải ghim của AWS | **[Đã chạy thử 2026-11-21] CodeZip chạy được; `ag-ui-strands` 1.0.4 + `strands-agents` 1.65.0 chạy tốt** (đã gọi Haiku 4.5 + tool qua Runtime). Chưa thử interrupt/resume qua Runtime. Xem `spike-agentcore-runtime-cors.md` |
| 5 | CORS khi trình duyệt gọi trực tiếp `bedrock-agentcore.<region>.amazonaws.com` bằng Bearer | **[Đã chạy thử 2026-11-21] Gọi thẳng được** (dịch vụ tự trả CORS `*`); chưa thử từ domain thật (chỉ `localhost`), nhưng preflight trả `*` với mọi Origin đã thử |
| 6 | Độ trễ cold start của microVM mới cho "ký tự đầu dưới 1,5 giây" (tài liệu nói V2 "nhất quán" nhưng không nêu mili giây) | **[Đã chạy thử 2026-11-21]** cold 1,8 đến 3,9 s (V1 và V2), ấm ~0,3 s: không đạt 1,5 s khi lạnh; cần làm nóng phiên hoặc hiển thị tiến độ |
| 7 | Độ trễ trích xuất Memory dài hạn (không có số) | Đo từ `CreateEvent` đến khi `RetrieveMemoryRecords` thấy record |
| 8 | Có tạo được strategy self-managed chỉ để lấy `memoryStrategyId` cho `BatchCreateMemoryRecords` không; có che PII được trong session manager không | Thử tạo; đọc mã SDK |
| 9 | Tên thuộc tính span chứa kết quả tool cho evaluator `NumericGrounding` | Mở một trace thật, xem `gen_ai.*`/thuộc tính tool |
| 10 | ID chính xác của evaluator dựng sẵn (`Builtin.GoalSuccessRate`...) | `agentcore eval evaluator list` |
| 11 | Giá ở Singapore có bằng bảng công khai không; chi phí thực của Policy/Evaluations | Cost Explorer sau tuần đầu |
| 12 | `PolicyEngine` còn alpha hay đã vào `aws-cdk-lib` ở phiên bản cài | Cài và `import`; xem mẫu serverless-patterns |
| 13 | Alias/đổi tên tool trong `MCPClient` của Strands để LLM thấy tên gọn hơn `ledger___...` | Đọc tài liệu Strands khi code. **[Đã chạy thử một phần 2026-11-21]** `MCPClient(prefix=...)` có (thử với MCP server cục bộ, chưa thử Gateway thật), xem [spike-strands-agui-local.md](spike-strands-agui-local.md) mục 2.9; **mục này vẫn mở** |
| 14 | Tiêu chuẩn `eventExpiryDuration` tối thiểu: tài liệu ghi 3 (trang tích hợp Strands, schema CLI) và 7 (bảng quota, `CreateEvent`) | Chọn ≥7 để an toàn |
| 15 | Mô hình Bedrock và inference profile có ở Singapore cho Strands (ngoài phạm vi ghi chú) | Agent nghiên cứu Bedrock |

Không kiểm chứng được trong phiên này: không gọi tool tạo/sửa/xóa nào của agentcore MCP; chưa chạy bất kỳ mã nào; giá trị Region ở bảng 3.7 lấy từ tài liệu và công cụ tra cứu, không từ việc tạo tài nguyên thử.

## 6. Nguồn (truy cập 2026-11-21)

Tài liệu chính thức AWS (`https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/`):

- `runtime-how-it-works.html` (microVM, V1/V2, session, resource configurations)
- `runtime-long-run.html` (bất đồng bộ, `/ping`)
- `runtime-service-contract.html`, `runtime-agui.html`, `runtime-agui-protocol-contract.html`
- `runtime-oauth.html` (JWT inbound, `allowedWorkloadConfiguration`, header `Authorization`)
- `runtime-header-allowlist.html`, `inbound-jwt-authorizer.html`
- `runtime-invoke-agent.html`, `runtime-get-started-code-deploy-python.html`
- `agentcore-get-started-cli.html` (CLI `@aws/agentcore`, template, lệnh)
- `bedrock-agentcore-limits.html` (quota), `agentcore-regions.html` (Region)
- `gateway-tool-naming.html`, `gateway-add-target-lambda.html`, `gateway-headers.html`, `gateway-inbound-auth.html`, `gateway-interceptors.html`, `gateway-interceptors-types.html`, `gateway-interceptors-configuration.html`, `gateway-using-mcp-semantic-search.html`
- `policy-scope.html`, `policy-authorization-flow.html`, `example-policies-principal.html`, `example-policies-action-resource.html`, `example-policies-reference.html`, `example-policies-temporal.html`, `policy-temporal.html`, `policy-test-a-policy.html`, `create-gateway-with-policy.html`
- `memory-types.html`, `memory-strategies.html`, `memory-organization.html`, `long-term-configuring-custom-strategies.html`, `memory-self-managed-strategies.html`, `long-term-retrieve-records.html`, `long-term-delete-memory-records.html`, `strands-sdk-memory.html`, `best-practices.html`
- `observability-get-started.html`, `observability-configure.html`
- `evaluators.html`, `built-in-evaluators-overview.html`, `prompt-templates-builtin.html`, `code-based-evaluators.html`, `on-demand-evaluations.html`, `evaluations-cross-region-inference.html`
- `on-behalf-of-token-exchange.html`
- Gói công cụ MCP `agentcore`: `get_runtime_guide`, `get_gateway_guide`, `get_policy_guide`, `get_memory_guide`, `get_identity_guide` (đọc cả năm; chú ý các guide ghi `@aws/agentcore-cli`, trang chính thức ghi `@aws/agentcore`)
- API: https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_CreateGatewayTarget.html ; https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_BatchCreateMemoryRecords.html
- Giá: https://aws.amazon.com/bedrock/agentcore/pricing/

Blog và repo mẫu:

- Propagate user authorization context in AI agents with Amazon Bedrock AgentCore: https://aws.amazon.com/blogs/security/propagate-user-authorization-context-in-ai-agents-with-amazon-bedrock-agentcore/ (đọc tới mục "Pattern 3"; phần OBO Salesforce chỉ đọc lướt)
- Build generative UI for AI agents on Amazon Bedrock AgentCore with the AG-UI protocol: https://aws.amazon.com/blogs/machine-learning/build-generative-ui-for-ai-agents-on-amazon-bedrock-agentcore-with-the-ag-ui-protocol/ (đọc tới phần human-in-the-loop, chưa đọc đoạn cuối)
- FAST: https://github.com/awslabs/fullstack-solution-template-for-agentcore (README: M2M + pre-token Lambda, Cedar theo `department`, "không phải production")
- aws-samples/serverless-patterns: `agentcore-gateway-cedar` (CDK L2 Gateway + PolicyEngine + Lambda target + Cognito), `lambda-durable-bedrock-agentcore-async`, `eventbridge-apidestination-agentcore`, `cloudfront-agentcore-runtime`
- README `@aws-cdk/aws-bedrock-agentcore-alpha` 2.277.0-alpha.0 và `aws-cdk-lib` 2.277.0 module `aws_bedrockagentcore`: https://constructs.dev/packages/@aws-cdk/aws-bedrock-agentcore-alpha/v/2.277.0-alpha.0
- `ag-ui-strands` 1.0.4: https://pypi.org/project/ag-ui-strands/ ; AG-UI events: https://docs.ag-ui.com/concepts/events
- Thư viện Strands integration Memory: https://github.com/aws/bedrock-agentcore-sdk-python/tree/main/src/bedrock_agentcore/memory/integrations/strands
- Công cụ AWS MCP `get_regional_availability` (ap-southeast-1 và us-east-1, 2026-11-21).
