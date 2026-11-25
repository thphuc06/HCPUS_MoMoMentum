# Kiến trúc tổng quan

Chắt từ proposal §8, §9, §10, §11 (số mục để tra ngược). Chi tiết đầy đủ ở [proposal-summary.md](../proposal/proposal-summary.md); sơ đồ gốc ở PDF (Hình 1 trang 9: kiến trúc; Hình 2 trang 10: harness; Hình 3–8: pipeline). Tên dịch vụ và tham số có thể đã đổi: tra tài liệu hiện hành trước khi code ([aws-tooling.md](../references/aws-tooling.md)).

> **File này đã được cập nhật theo kết quả nghiên cứu và spike ngày 2026-11-21** (bảy ghi chú đọc tài liệu và [bảy spike chạy thật](../research/README.md#kết-quả-chạy-thử-spike-2026-11-21)). Chỗ nào khác proposal đều ghi "khác proposal §N". Mỗi khẳng định đã xem lại mang một trong ba nhãn:
>
> - **[đã chạy thử]** đã chạy thật và quan sát được, kèm link file spike (số đo tổng hợp ở mục [Số đo đã có](#số-đo-đã-có));
> - **[đọc tài liệu]** mới đọc tài liệu chính thức hoặc ghi chú nghiên cứu, chưa chạy;
> - **[đề xuất]** suy ra từ kết quả, chưa được chủ dự án chốt.
>
> Phần không có nhãn là nội dung nguyên của proposal, chưa kiểm. Toàn bộ số đo ML chạy trên dữ liệu **tổng hợp**.
>
> **Cập nhật 25/11/2026 (issue #32)**: thân file vẫn là ảnh chụp ngày 21/11, nhãn [đề xuất] chưa được đổi hết sang trạng thái đang chạy (việc I2 của phase 6). Các quyết định đã chốt từ đó: Region `ap-southeast-1`, cơ chế xác nhận ([ADR-0002](../decisions/0002-xac-nhan-truoc-khi-ghi.md)), bộ model, Chronos-2 ngoài MVP ([open-questions](../requirements/open-questions.md#rút-ra-từ-nghiên-cứu-2026-11-21)). Bảy stack CDK đã deploy ([aws-resources.md](../aws-resources.md)). Mọi lệch so với proposal, kèm việc đang chạy và lý do, gom ở [ADR-0004](../decisions/0004-lech-so-voi-proposal.md). Đã sửa theo mã: mục Kiến trúc AWS, bảng harness (L2, L3), danh mục tool, bảng mô hình dữ liệu.

Viết tắt file spike (đều ở [../research/](../research/README.md)): **Gateway** = [spike-agentcore-gateway-identity.md](../research/spike-agentcore-gateway-identity.md), **Runtime** = [spike-agentcore-runtime-cors.md](../research/spike-agentcore-runtime-cors.md), **Aurora** = [spike-aurora-data-api.md](../research/spike-aurora-data-api.md), **Bedrock** = [spike-bedrock-models.md](../research/spike-bedrock-models.md), **Strands** = [spike-strands-agui-local.md](../research/spike-strands-agui-local.md), **ML** = [spike-ml-forecasting.md](../research/spike-ml-forecasting.md), **Frontend** = [spike-frontend-stack.md](../research/spike-frontend-stack.md).

## Chỗ lệch so với proposal (tóm tắt)

Bảng đầy đủ, có cột "vì sao" và nguồn: [ADR-0004](../decisions/0004-lech-so-voi-proposal.md).

| Proposal | Hiện hành | Mục |
|---|---|---|
| Next.js + React (§14) | React + Vite SPA, chốt bằng [ADR-0001](../decisions/0001-frontend-stack.md) | [Frontend](#frontend-gọi-thẳng-runtime) |
| Chỉ có đường agent | Thêm REST API (HTTP API + JWT) cho màn hình không cần LLM | [REST API](#rest-api-đề-xuất) |
| Tool tên `ledger.get_jar_balances` (§9) | `ledger___get_jar_balances` (target + `___` + tool) | [Danh mục tool](#danh-mục-tool-9) |
| Cedar ép `user_id`; Identity truyền danh tính (§8, §9) | Interceptor ghi đè `user_id` từ JWT + Cedar; Identity không dùng cho tool Lambda | [Danh tính](#danh-tính-xuống-tool) |
| Cedar cho tool ghi chạy khi tham số có cờ xác nhận (§9) | Token xác nhận dùng một lần do server cấp; Cedar là lớp phụ, chốt ở [ADR-0002](../decisions/0002-xac-nhan-truoc-khi-ghi.md) | [Xác nhận](#xác-nhận-trước-khi-ghi-đề-xuất-chưa-chốt) |
| Composer trả một JSON duy nhất (§9) | Khối UI phát bằng `ACTIVITY_SNAPSHOT` từ tool; JSON gộp giữ làm bản ghi lượt | [Khối UI](#khối-ui) |
| Sonnet 5.5 / Haiku 5.5 | Sonnet 4.6 và Kimi K3 (vai lớn), Nova 2 Lite và Haiku 4.5 (vai nhỏ), Cohere Embed Multilingual v3; chốt 21/11, cấu hình ở `libs/yofina_core/src/yofina_core/llm_defaults.json` | [Model](#model-đề-xuất-chưa-chốt) |
| Chronos-2 "MVP nếu kịp" (§14) | Hurdle tự viết trong Lambda zip (numpy, scipy); Chronos-2 ngoài MVP (chốt 21/11); StatsForecast chỉ chạy trên máy để so backtest | [ML](#ml-kết-quả-đã-đo) |
| Bedrock Data Automation, Automated Reasoning, SageMaker | Bỏ (chốt 21/11) | [Bỏ và hoãn](#bỏ-và-hoãn) |
| Graph của Strands cho F3 (§9) | Code tuần tự có timeout | [Harness](#agentic-harness-6-tầng-9) |
| Bedrock Knowledge Bases, `knowledge.search` (§8, §9) | Cắt 24/11; biểu phí có cấu trúc kèm trích dẫn nguồn | [Danh mục tool](#danh-mục-tool-9) |
| WAF, batch tuần, AgentCore Evaluations (§8, §9) | Không làm (phase 6 mục 3, Q11) | [ADR-0004](../decisions/0004-lech-so-voi-proposal.md) |

## Nguyên tắc

1. **LLM chỉ làm ba việc**: hiểu ý định, lập kế hoạch, diễn giải. Tính toán, kiểm tra luật, ghi dữ liệu nằm ở tool tất định.
2. Cơ sở dữ liệu quan hệ là nguồn sự thật duy nhất cho mọi số; LLM không viết SQL tự do.
3. Mọi thay đổi số dư cần người dùng xác nhận. Tool ghi bị Cedar chặn mặc định (§9): mặc định từ chối là **[đã chạy thử]** ([Gateway §4](../research/spike-agentcore-gateway-identity.md)); nhưng cờ xác nhận trong tham số do LLM điền nên không phải bằng chứng, cơ chế thay thế ở mục [Xác nhận](#xác-nhận-trước-khi-ghi-đề-xuất-chưa-chốt).
4. Mọi gợi ý truy được qua `trace_id` đến dữ liệu đã dùng và luật đã kiểm (bảng "Vì sao").
5. Runtime không chạy mô hình nặng: đọc dự báo đã tính sẵn, chỉ chạy mô phỏng nhẹ.
6. Danh tính người dùng không bao giờ lấy từ LLM hay từ tham số do client gửi: `user_id` được hạ tầng ghi đè từ JWT đã xác minh. **[đã chạy thử]** ([Gateway §3](../research/spike-agentcore-gateway-identity.md))

## Kiến trúc AWS (§8)

```
Người dùng (web mobile)
  → CloudFront + WAF → Amplify Hosting (React + Vite SPA, @ag-ui/client) ── đăng nhập → Cognito (access token JWT)
  │
  ├─ (1) Chat: fetch + SSE (AG-UI), Authorization: Bearer <access token>, gọi THẲNG Runtime
  │      → Bedrock AgentCore Runtime (platform V2, deploy bằng zip; Strands + ag-ui-strands; mỗi phiên một microVM)
  │            ├─ AgentCore Memory (ngắn hạn theo phiên, dài hạn theo người dùng)
  │            ├─ AgentCore Gateway (MCP): JWT authorizer → request interceptor (ghi đè user_id) → Policy (Cedar) → Lambda
  │            ├─ AgentCore Identity (chỉ cho dịch vụ ngoài; không dùng để truyền danh tính xuống Lambda tool)
  │            └─ AgentCore Observability + Evaluations
  │      → Amazon Bedrock: LLM lớn, LLM nhỏ, embedding · Guardrails · Knowledge Bases
  │
  └─ (2) Màn hình không cần LLM + cấp token xác nhận (đề xuất, chưa chạy thử phần HTTP API):
         HTTPS + Bearer → API Gateway HTTP API (JWT authorizer Cognito) → cùng Lambda `ledger`

  Tool: Lambda (Python) sau Gateway: ledger · forecast · planner · knowledge · ingest · audit
        ├─ Aurora PostgreSQL Serverless v2 (+ pgvector) qua RDS Data API: sổ cái, dự báo, lộ trình
        ├─ Lambda container image (StatsForecast, numpy, scipy): dự báo, mô phỏng, tối ưu
        ├─ DynamoDB (jti của token xác nhận, TTL) [đề xuất]
        ├─ EventBridge (bus + Scheduler) → SQS (+ DLQ) → Lambda; Step Functions (pipeline đêm)
        └─ S3: tệp nạp, KB, artifact mô hình, audit
  Quan sát và bảo mật xuyên suốt: CloudWatch, CloudTrail, KMS, WAF
```

Hạ tầng tự viết bằng CDK; khung FAST chỉ để tham khảo — xem [project-structure.md](project-structure.md). Bảy stack CDK đã deploy ở `ap-southeast-1` (`YofinaFoundation`, `YofinaData`, `YofinaIdentity`, `YofinaFrontend`, `YofinaTools`, `YofinaAgent`, `YofinaIngest`, khai ở `infra-cdk/bin/yofina.ts`; danh sách tài nguyên ở [aws-resources.md](../aws-resources.md)). Sơ đồ trên là bản 21/11; bản đang chạy khác ở: không WAF, không Knowledge Bases, không AgentCore Evaluations, không CloudTrail hay khóa KMS riêng (dùng khóa do AWS quản), dự báo chạy trong Lambda zip numpy + scipy thay cho container StatsForecast (lý do ở [ADR-0004](../decisions/0004-lech-so-voi-proposal.md)).

Điểm cần biết thêm:

- **Region**: **[đọc tài liệu]** mọi thành phần AgentCore proposal cần (Runtime V2, Memory, Gateway, Identity, Policy, Observability, Evaluations) có ở `ap-southeast-1`; Evaluations dựng sẵn bị giới hạn 200 lượt/phút ở đây ([agentcore.md §3.7](../research/agentcore.md)). Region chưa chốt.
- **AgentCore Memory**: **[đọc tài liệu]** `actorId` lấy từ `sub` của JWT, không từ payload; không có API xóa theo người dùng; `AgentCoreMemorySessionManager` ghi tin nhắn thô nên che PII phải tự bọc ([agentcore.md §3.5](../research/agentcore.md)). Chưa thử.
- **Đường (1) đi thẳng Runtime nên không qua WAF của CloudFront**; URL phía client chứa ARN của Runtime (bảo vệ bằng JWT). Chỉ cần lớp trung gian khi muốn giấu ARN, giới hạn tần suất hoặc dùng domain riêng. **[đề xuất]** ([Runtime §3](../research/spike-agentcore-runtime-cors.md))

### Frontend gọi thẳng Runtime

- Trình duyệt `fetch` POST tới `https://bedrock-agentcore.<region>.amazonaws.com/runtimes/<ARN url-encode>/invocations?qualifier=DEFAULT` và đọc SSE AG-UI; **không cần proxy**. Chính dịch vụ trả preflight (kể cả cho header tùy biến) và gắn `Access-Control-Allow-Origin: *` vào mọi phản hồi, kể cả 401/403; `CORSMiddleware` trong app vô hiệu. Đã chạy trên Edge 158 và Chrome 157 từ `localhost`. **[đã chạy thử]** ([Runtime §3](../research/spike-agentcore-runtime-cors.md)) Chưa thử domain thật, Safari/iPhone, Amplify Hosting.
- **Token**: gửi **access token** Cognito với `allowedClients`; ID token bị từ chối (401); `Bearer` phải viết hoa; không dùng `credentials: 'include'` (không cần). **[đã chạy thử]** ([Runtime §2](../research/spike-agentcore-runtime-cors.md))
- **Runtime platform V2**: ghim phiên theo `sub` (người dùng khác dùng session id của người khác nhận 403) và trả 409 `SESSION_BUSY` khi hai request chạy song song cùng session; V1 không có hai hành vi này. Đổi lại tạo hoặc cập nhật V2 mất khoảng 5 phút (V1 khoảng 15 giây). **[đã chạy thử]** ([Runtime §5](../research/spike-agentcore-runtime-cors.md))
- **Session id** 33–256 ký tự (UUID v4 đủ), header `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id`, client giữ ổn định theo cuộc hội thoại. **[đã chạy thử]**
- **Gửi lại toàn bộ `messages` mỗi lượt** (đúng ngữ nghĩa AG-UI): nếu chỉ gửi tin mới thì model không nhớ lượt trước. **[đã chạy thử]** ([Runtime §5](../research/spike-agentcore-runtime-cors.md))
- **Deploy bằng zip** (direct code deployment, wheel ARM64 cài bằng `uv` ngay trên Windows, khoảng 31 MB nén), **không cần Docker**; AG-UI chạy được với CodeZip, tài liệu AWS ghi "container" là chưa đúng. **[đã chạy thử]** ([Runtime §1](../research/spike-agentcore-runtime-cors.md))
- Agent nhận nguyên `Authorization` khi đã khai trong `requestHeaderAllowlist` (**[đã chạy thử]**); agent lấy `sub` từ đó và không nhận `user_id` từ payload (**[đề xuất]**).
- **Lỗi**: 401/403/409 đến dưới dạng một event `RUN_ERROR`; lỗi ném giữa luồng là HTTP 200 với thân rỗng, không có `RUN_ERROR`, nên UI phải coi luồng rỗng hoặc đứt là lỗi. **[đã chạy thử]** ([Runtime §1](../research/spike-agentcore-runtime-cors.md))
- **`trace_id`**: client sinh `traceparent` mỗi lượt, trace id được giữ nguyên tới app; phản hồi không trả trace id về. **[đã chạy thử]** ([Runtime §6](../research/spike-agentcore-runtime-cors.md)) Span trong CloudWatch chưa xác nhận (chưa bật Transaction Search).
- **Cold start**: phiên lạnh tốn 1,8 đến 3,9 s trước event đầu nên **không đạt "ký tự đầu dưới 1,5 giây"**; phiên ấm khoảng 0,3 s. **[đã chạy thử]** ([Runtime §4](../research/spike-agentcore-runtime-cors.md)) Làm nóng phiên khi người dùng mở màn hình chat và hiện tiến độ cho lượt đầu. **[đề xuất]**
- Token hết hạn giữa luồng SSE đang chạy chưa thử.

### REST API (đề xuất)

**[đề xuất]**, **chưa chạy thử phần HTTP API**: API Gateway HTTP API với JWT authorizer của Cognito, trỏ vào cùng Lambda `ledger` (một mã, hai đường vào), cho các màn hình không cần LLM (khai báo, hũ, chuyển tiền trên ví mô phỏng, danh sách "Xem lại", tiến độ nạp tệp) và cho endpoint cấp token xác nhận. Lý do: proposal chỉ có đường agent; nếu không có API này mọi thao tác UI phải đi qua LLM (chậm, tốn token, ngoài ngân sách 2 giây). **[đọc tài liệu]** ([aws-data-events-infra.md](../research/aws-data-events-infra.md)). Spike Gateway chỉ gọi thẳng Lambda cấp token và xác minh bằng `cognito-idp:GetUser`, chưa qua HTTP API.

### Tool sau Gateway

- Tool lộ ra qua MCP có tên `<target>___<tool>` (ba gạch dưới), ví dụ `ledger___get_jar_balances`; sáu target = sáu nhóm tool, mỗi target một Lambda. Tên target chỉ gồm chữ, số, gạch nối (gạch dưới và dấu chấm bị từ chối khi tạo target). **[đã chạy thử]** ([Gateway §1](../research/spike-agentcore-gateway-identity.md))
- Gateway kiểm `required` và kiểu của tham số (lỗi trả `isError`), **không từ chối tham số thừa**, nên Lambda phải bỏ qua tham số lạ. **[đã chạy thử]** ([Gateway §1](../research/spike-agentcore-gateway-identity.md))
- Gateway không cưỡng chế giới hạn 128 ký tự của tên tool; giữ `<target>___<tool>` ngắn vì Bedrock Converse giới hạn 64 ký tự (mục này mới suy ra, chưa kiểm). **[đề xuất]**
- Từ chối của Cedar là lỗi giao thức JSON-RPC (`-32002`, HTTP 200), không phải tool result `isError`; client `mcp` Python ném `ExceptionGroup`. Agent phải bắt và đổi thành thông báo cho LLM; hành vi mặc định của Strands `MCPClient` chưa thử. **[đã chạy thử]** ([Gateway §4](../research/spike-agentcore-gateway-identity.md))
- `tools/list` vẫn trả đủ mọi tool khi bật tìm kiếm ngữ nghĩa (thêm tool `x_amz_bedrock_agentcore_search`); tool bị Cedar từ chối vĩnh viễn thì ẩn khỏi danh sách. Với khoảng 24 tool, chia sẵn theo specialist thay vì dựa vào tìm kiếm. **[đã chạy thử]** ([Gateway §7](../research/spike-agentcore-gateway-identity.md)) cho phần hành vi, **[đề xuất]** cho phần chia theo specialist.
- Thư viện `mcp` 2.x đổi API so với mẫu của FAST (`streamable_http_client`, không còn tham số `headers=`; `MCPServer` thay `FastMCP`); `MCPClient(prefix=...)` của Strands thêm tiền tố bằng gạch dưới, thử với MCP server cục bộ. **[đã chạy thử]** ([Strands §2.9](../research/spike-strands-agui-local.md)) Chưa thử với Gateway thật.

### Danh tính xuống tool

Thứ tự xử lý của Gateway: **JWT authorizer → request interceptor → Cedar (thấy tham số đã bị interceptor sửa) → kiểm schema → Lambda**. **[đã chạy thử]** ([Gateway §4](../research/spike-agentcore-gateway-identity.md); vị trí "kiểm schema sau Cedar" suy ra từ lỗi quan sát được.) Interceptor chỉ chạy sau khi JWT hợp lệ.

- Lambda sau Gateway **không nhận claim nào** của người gọi. Header do client gửi và được allowlist đi qua nguyên văn (A gửi `x-user-id` của B thì Lambda thấy của B), nên không phải danh tính. **[đã chạy thử]** ([Gateway §2–§3](../research/spike-agentcore-gateway-identity.md))
- **Lớp 1 (bắt buộc): request interceptor** (`passRequestHeaders: true`) đọc `Authorization`, lấy `sub`, **ghi đè `arguments.user_id`** cho mọi `tools/call` (và đặt thêm header `x-user-id`); chạy cả khi LLM bỏ trống hoặc tự điền `user_id` của người khác. **[đã chạy thử]**
- **Lớp 2: Cedar `context.input.user_id == principal.id`** (`principal.id` là `sub`; claim khác là tag), một policy mỗi tool. Chạy độc lập với interceptor: gỡ interceptor thì Cedar vẫn chặn, gỡ Cedar thì interceptor vẫn ghi đè. **[đã chạy thử]**
- Khai `user_id` là tham số **tùy chọn** ở schema tool, interceptor luôn tiêm, luật Cedar viết `context.input has user_id && context.input.user_id == principal.id`. Tổ hợp này chưa chạy; riêng việc tiêm `user_id` khi schema không khai đã chạy được. **[đề xuất]**
- Lambda lọc dữ liệu theo `user_id` trong `event`, coi mọi tham số khác là không tin cậy; vì từ trong Lambda không phân biệt được `user_id` do interceptor đặt với do client gửi, cần kiểm thử tự động (CI) rằng Gateway luôn có interceptor và policy engine ở `ENFORCE`. **[đề xuất]**
- **Lớp 3: Aurora RLS** (xem [Dữ liệu](#dữ-liệu)); vẫn giữ `WHERE user_id = :uid` do code ép, vì RLS chỉ bảo vệ khi code tin cậy là bên đặt `app.user_id`. **[đã chạy thử]** ([Aurora §4](../research/spike-aurora-data-api.md))
- Token exchange / OBO của AgentCore Identity không áp dụng cho Lambda target (outbound chỉ có gateway service role). **[đọc tài liệu]** Job nền sống lâu hơn token dùng danh tính dịch vụ kèm `user_id` đã xác thực lúc khởi tạo. **[đề xuất]**
- Độ trễ thêm: interceptor cộng Cedar khoảng 50–80 ms ở trạng thái ấm. **[đã chạy thử]** ([Gateway §6](../research/spike-agentcore-gateway-identity.md))

### Xác nhận trước khi ghi (đề xuất, chưa chốt)

> **[đề xuất]** theo kết quả thử; **chủ dự án chưa chốt chính thức**. **Khác proposal §9**, nơi Cedar cho tool ghi chạy khi tham số có cờ xác nhận.

Vấn đề: cờ `user_confirmed` do LLM điền nên giả mạo được (kể cả bởi prompt injection); Cedar chỉ so sánh chuỗi/số/boolean, không kiểm được chữ ký hay tính duy nhất. **[đã chạy thử]** ([Gateway §5](../research/spike-agentcore-gateway-identity.md))

Cơ chế đề xuất, hai nửa:

1. **Token dùng một lần do server cấp.** Tool ghi thiếu `confirm_token` thì trả `NEEDS_CONFIRMATION` (không ghi). Người dùng bấm nút trên UI, UI gọi endpoint riêng nằm ngoài Gateway và LLM (đường REST) bằng access token; endpoint xác minh người dùng, tự ghim `user_id = sub`, ký HMAC trên (sub, tool, hash tham số chuẩn hóa, hạn tối đa 2 phút, `jti`). Lambda tool kiểm chữ ký, hạn, tool, `sub`, hash tham số và `jti` chưa dùng (`PutItem` điều kiện trên DynamoDB, có TTL). **13 ca đúng kỳ vọng**: tự điền cờ, bịa token, ký sai khóa, đổi tham số, replay, dùng token người khác, token hết hạn đều bị từ chối. **[đã chạy thử]** ([Gateway §5](../research/spike-agentcore-gateway-identity.md); endpoint thật bằng HTTP API chưa dựng, spike gọi thẳng Lambda.)
2. **Interrupt của AG-UI.** Tool ghi gắn `ToolBehavior(interrupt_on_call=True)`: run kết thúc với `RUN_FINISHED` có `outcome: interrupt`, kèm `metadata.tool_input` do server thấy (UI dựng khối `confirm` từ đó, không từ lời LLM); người dùng chỉ gửi `{"approved": true}`; tool không chạy trước khi được duyệt, và resume vẫn chạy sau khi tiến trình server khởi động lại nhờ session manager bền. **[đã chạy thử local]** ([Strands §2.7](../research/spike-strands-agui-local.md); dùng `FileSessionManager`.) Không dùng `HumanInTheLoop` qua `ag-ui-strands` 1.0.4 (resume không chạy). Chưa thử interrupt/resume qua Runtime thật hay với `AgentCoreMemorySessionManager`.

**Chưa ghép hai nửa với nhau**: token xác nhận đi vào tham số tool bằng đường nào sau khi interrupt được duyệt chưa được chạy thử. Hai hướng đã nêu: để token đi qua ngữ cảnh LLM (chấp nhận được vì token gắn tham số, người dùng, hạn 2 phút và dùng một lần), hoặc UI gọi thẳng endpoint "áp dụng" để LLM không chạm vào bước ghi. **[đề xuất]**

**Cedar giữ làm lớp phụ**: `user_id == principal.id`, `amount_vnd <=` hạn mức, có mặt `confirm_token` dạng `*.*`; `user_confirmed` chỉ là gợi ý UI. **[đã chạy thử]** Secret HMAC để ở Secrets Manager, xoay khóa bằng hai khóa hợp lệ song song. **[đề xuất]** Đưa policy engine lên ở `LOG_ONLY` rồi `ENFORCE` (xem [Quan sát](#khả-năng-quan-sát-và-đánh-giá-9)); lưu ý `LOG_ONLY` cho qua mọi lời gọi kể cả ghi vượt hạn mức. **[đã chạy thử]** ([Gateway §4](../research/spike-agentcore-gateway-identity.md))

### Khối UI

- **Tool phát khối, LLM không thấy khối.** Tool là async generator, `yield` khối đầy đủ rồi `yield` kết quả gọn; `ToolBehavior(tool_stream_event_handler=...)` đổi khối thành event `ACTIVITY_SNAPSHOT` (`activityType: "yofina.block"`, `messageId` = `block.id`, `replace: true`) đến trước `TOOL_CALL_RESULT`; `TOOL_CALL_RESULT` chỉ chứa bản gọn cho LLM. **Số trong khối do code dựng từ kết quả tool.** Các cách khác (`custom_result_handler`, state) cho LLM thấy toàn bộ kết quả và nó viết lại thành bảng markdown; khối đi qua state bị xóa ở `STATE_SNAPSHOT` cuối lượt. **[đã chạy thử local]** ([Strands §2.5, §3.1](../research/spike-strands-agui-local.md))
- **Khối lưu DB để phát lại.** `ACTIVITY_SNAPSHOT` và `CUSTOM` không nằm trong `MESSAGES_SNAPSHOT`, nên khối mất khi tải lại trang nếu chỉ dựng từ lịch sử hội thoại. **[đã chạy thử]** Lưu khối phía server theo `trace_id`. **[đề xuất]**
- **Frontend dùng registry `type → { schema Zod, Component }`**, phân tích từng khối riêng (không `parse` cả mảng bằng một union): khối lạ hoặc sai schema hiển thị `fallback_text`, trang không vỡ. `ACTIVITY_SNAPSHOT` với `messageId` ổn định thay khối tại chỗ; `CUSTOM` để cho tín hiệu phụ. **[đã chạy thử]** ([Frontend §4–§5](../research/spike-frontend-stack.md); chạy với mock server SSE.)
- **JSON gộp của proposal §9 (Composer) giữ làm bản ghi lượt** (lưu để phát lại và kiểm toán), không phải thứ stream tới trình duyệt. **[đề xuất]**
- Không chuyển nguyên event stream của Strands ra trình duyệt (chứa system prompt và cấu hình tool); adapter AG-UI chỉ phát event AG-UI. **[đã chạy thử]** ([Strands §2.3](../research/spike-strands-agui-local.md))
- Hai đầu (tool phát khối bằng Strands; frontend render từ mock server) **chưa nối với nhau**, và chưa qua Runtime thật.

### Model (đề xuất, chưa chốt)

> **[đề xuất]** theo kết quả thử; **bộ model chưa được chủ dự án chốt chính thức**. Claude 5.x (Sonnet 5.5, Haiku 5.5, Sonnet 5, Opus 4.7 trở lên, Fable) không gọi được trên tài khoản này: `AccessDeniedException` (HTTP 403), không phải `ThrottlingException`, ở cả `ap-southeast-1` và `us-east-1`. **[đã chạy thử]** ([Bedrock §1](../research/spike-bedrock-models.md)) Chuỗi dự phòng trong code phải bắt cả `AccessDeniedException`.

| Vai | Dùng được ngay (đã gọi thật ở `ap-southeast-1`) | Ghi chú |
|---|---|---|
| LLM lớn (planner) | Sonnet 4.6; dự phòng Kimi K3 | Sonnet 4.6: ép tool 14/14, structured output 14/14. Kimi K3: không cache, luôn suy nghĩ, không nhận `temperature` |
| LLM nhỏ (router, diễn giải) | Haiku 4.5; hoặc Nova 2 Lite / Nova Pro | Nova không hỗ trợ `outputConfig`: ép tool để lấy JSON; Haiku 4.5 không cache được prompt ngắn (cần ít nhất 4.096 token) |
| Đọc ảnh | Sonnet 4.6, Kimi K3 | Đúng cả bốn trường trên 3 ảnh dựng sạch; Haiku 4.5 tự sửa sai nội dung không dấu |
| Embedding | Cohere Embed Multilingual v3 hoặc v4 | Titan Text Embeddings V2 chỉ gọi được ở `us-east-1` |

- **Giới hạn**: Claude 4.x chỉ **10 request/phút mỗi model** (Haiku 4.5 và Sonnet 4.6 là hai xô riêng). Đủ cho demo một người (một lượt what-if tốn 2 call Haiku và 2 call Sonnet), không đủ cho nhiều người dùng song song hoặc chạy bộ đánh giá; Nova 20–25 RPM ở Singapore. `us-east-1` có quota rộng hơn (open-weight 100 RPM) nhưng dữ liệu xử lý ở Mỹ. **[đã chạy thử]** ([Bedrock §2, §9](../research/spike-bedrock-models.md)); biện pháp (Nova cho router, chạy đánh giá ở `us-east-1`, bộ đếm lượt/phút ở app) **[đề xuất]**.
- **Dữ liệu xử lý ngoài Singapore**: các model gọi được đều đi qua profile `global.`. **[đã chạy thử]** Hệ quả cho phần quyền riêng tư (dữ liệu có thể được xử lý ngoài Singapore). **[đọc tài liệu]** ([bedrock.md](../research/bedrock.md))
- **JSON có cấu trúc**: ép tool chạy với Haiku 4.5, Sonnet 4.6, Nova, Kimi K3 và là đường mặc định; với model open-weight không dùng `outputConfig`. Luôn đặt `structured_output_attempts`, nếu không vòng lặp có thể không dừng. **[đã chạy thử]** ([Bedrock §3](../research/spike-bedrock-models.md), [Strands §2.2](../research/spike-strands-agui-local.md))
- **Giới hạn vòng lặp**: chạm `limits` không ném lỗi mà trả `stop_reason` (`limit_turns`, `limit_total_tokens`, …) và `str(result)` rỗng; rẽ sang thẻ số tất định theo `stop_reason`. **[đã chạy thử]** ([Strands §2.1](../research/spike-strands-agui-local.md))

### Dữ liệu

- **Aurora qua RDS Data API cho mọi tool Lambda**, kể cả đường nóng: từ Lambda ngoài VPC, luồng 3 truy vấn của kiểm tra trước khi quẹt p50 91 ms, p95 113 ms. Không cần psycopg trong VPC. Chỉ cần kết nối trực tiếp nếu trả hơn 1 MiB mỗi lần. **[đã chạy thử]** ([Aurora §2](../research/spike-aurora-data-api.md))
- **Role riêng cho tool, không dùng master.** Master user (`rds_superuser`) vượt RLS ngay cả khi `FORCE ROW LEVEL SECURITY`. Lambda tool dùng secret của role `yofina_app` (không phải owner, `NOBYPASSRLS`); master chỉ cho migrator, Lambda tool không được đọc secret master. **[đã chạy thử]** ([Aurora §4](../research/spike-aurora-data-api.md))
- **`set_config('app.user_id', ..., true)` phải nằm trong transaction hoặc hàm plpgsql**: Data API reset phiên giữa các lệnh gọi. Đường đọc: hàm plpgsql `SECURITY INVOKER` (1 lệnh gọi, chi phí RLS gần bằng 0); đường ghi: `BeginTransaction` → `set_config` → câu lệnh → `Commit`, luôn `rollback` trong `finally`. Không dùng mẹo CTE `set_config` một lệnh (sai với truy vấn dùng index). **[đã chạy thử]**
- **Không để Aurora tự pause khi demo/chấm điểm**: giữ tối thiểu 0,5 ACU. Lần gọi đầu sau pause mất 16,4 s và 4 lần đầu bị `DatabaseResumingException` (boto3 không tự retry); min 0 chỉ cho dev, và tool vẫn nên retry. **[đã chạy thử]** ([Aurora §6](../research/spike-aurora-data-api.md))
- **Mọi truy vấn có thể trả nhiều dòng phải có `LIMIT`**: phản hồi tối đa 1 MiB và vượt là lỗi cả lệnh. `numeric` và `timestamptz` (UTC, không hậu tố) đến dưới dạng chuỗi (dùng `Decimal` cho tiền); `interval` phải cast sang text; tham số vector/jsonb/timestamptz phải `CAST`. **[đã chạy thử]** ([Aurora §5](../research/spike-aurora-data-api.md))
- pgvector 0.8.2 chạy qua Data API (`CAST(:q AS vector)` với chuỗi `'[...]'`); độ trễ kNN ở quy mô lớn chưa đo. **[đã chạy thử]** ([Aurora §3](../research/spike-aurora-data-api.md)). Chưa có subnet group tên `default` ở Region: để CDK tự tạo.

Aurora PostgreSQL Serverless v2 (+ pgvector) là nguồn sự thật duy nhất; schema thực nằm ở `db/schema/`.

### ML (kết quả đã đo)

> Toàn bộ số đo dưới đây trên **dữ liệu tổng hợp** do bộ sinh hurdle-lognormal tạo; mô hình hurdle tự viết cùng họ với bộ sinh nên được lợi. Chưa có kết quả trên dữ liệu thật. **[đã chạy thử]** ([ML](../research/spike-ml-forecasting.md))

- **Dự báo mặc định cho hũ chi tiêu: hurdle tự viết** (theo ô cuối tuần × nửa đầu kỳ lương, bootstrap số tiền; chỉ cần numpy). Pinball tương đối khoảng 0,55 so với seasonal naive, thắng seasonal naive từ khoảng 21–30 ngày lịch sử. Giữ `ForecastModel.predict(...) -> bảng phân vị` để cắm model khác. **[đã chạy thử]** ([ML §3](../research/spike-ml-forecasting.md))
- **StatsForecast chỉ làm baseline** (SeasonalNaive; AutoETS chỉ cho chuỗi từ 90 ngày và hũ dày, vì dưới khoảng 60 ngày tệ hơn seasonal naive). **Cần Lambda container image**: 332 MB sau khi cài (wheel Windows), vượt giới hạn 250 MB của zip, `pyarrow` bắt buộc. Croston/TSB/ADIDA/IMAPA chỉ có khoảng conformal, thua hurdle ở hũ thưa. **[đã chạy thử]** ([ML §2–§3](../research/spike-ml-forecasting.md))
- **Chronos-2 ngoài MVP** (chủ dự án chốt 21/11, cùng SageMaker). Cơ sở: hòa với hurdle (tỉ lệ pinball 1,007), thắng ETS_native (0,67, thắng 31/31 origin); cần torch cộng model 478 MB, RAM đỉnh khoảng 1,2 GB, container; chưa đo trên vCPU Lambda. **[đã chạy thử]** ([ML §3–§4](../research/spike-ml-forecasting.md)) Nên chờ dữ liệu thật hoặc persona khác họ bộ sinh để so A/B.
- **Khoảng dự báo**: conformal mặc định của StatsForecast (`n_windows=2`) phủ thiếu (0,54–0,60 so với 0,80 danh định); ACI tự viết (khoảng 25 dòng, γ = 0,005–0,01) sửa được (0,61 → 0,81). **Khoảng tổng 30 ngày phủ thiếu ở mọi model** (0,48–0,61 ở hũ dày), cần xử lý trước khi hiện xác suất hụt cho người dùng. **[đã chạy thử]** ([ML §3, §5](../research/spike-ml-forecasting.md))
- **Monte Carlo có tương quan giữa các ngày** (copula Gaussian AR(1)), vector hóa bằng numpy: lấy mẫu độc lập đánh giá thấp xác suất hụt khi rủi ro thấp (5,8% thay vì 10% ở hũ ăn uống). Hũ thưa mô phỏng hurdle trực tiếp, không qua nội suy phân vị. ρ chọn theo độ phủ trên backtest; không có một ρ đúng cho mọi đại lượng. **[đã chạy thử]** ([ML §6](../research/spike-ml-forecasting.md))
- **Phát hiện đổi hành vi**: PELT theo **tuần** (`ruptures`, cost `l2`, chuỗi đã cắt khoản lớn, penalty 2–3 × σ²·ln n; rất nhạy penalty); CUSUM/PageHinkley tự viết chỉ để "nghi"; **bỏ ADWIN** (không bắt được điểm gãy +49%). River không có CUSUM. **Bỏ PyOD**: z bền MAD một chiều ngang ECOD cho khoản lớn. **[đã chạy thử]** ([ML §7](../research/spike-ml-forecasting.md))
- **Phân bổ lương bằng LP**: `scipy.optimize.linprog` (HiGHS), khoảng 1 ms; sàn cứng phải qua biến elastic với mức phạt theo ưu tiên (M riêng từng hũ); bỏ PuLP. **[đã chạy thử]** ([ML §8](../research/spike-ml-forecasting.md))
- **Phân loại giao dịch**: bỏ ngưỡng cosine 0,97 (gộp nhầm "tiền điện/nước" với "tiền trọ"); chuẩn hóa chuỗi (bỏ dấu, chữ thường, mở rộng viết tắt) trước khi nhúng, so khớp chuỗi chính xác cho khử trùng, hiệu chỉnh ngưỡng theo từng model. **[đã chạy thử]** ([Bedrock §6](../research/spike-bedrock-models.md); 43 chuỗi tự soạn.)
- **Tên "FinHealth Score"**: dùng Score trong phần mềm thương mại cần license; gọi "Điểm chống chịu", ghi "lấy cảm hứng từ". **[đọc tài liệu]** ([ml-forecasting.md](../research/ml-forecasting.md)) rồi **[đề xuất]**, chưa chốt.

### Bỏ và hoãn

- **Bedrock Data Automation: bỏ.** Không liệt kê tiếng Việt. **[đọc tài liệu]** ([bedrock.md](../research/bedrock.md)) Model đọc ảnh trực tiếp đã thử được (Sonnet 4.6, Kimi K3). **[đã chạy thử]** ([Bedrock §5](../research/spike-bedrock-models.md)) Chỉ thử 3 ảnh dựng sạch, chưa thử ảnh chụp thật.
- **Automated Reasoning checks: hoãn.** Chỉ tiếng Anh, không có ở Singapore; verifier Python là đường chính. **[đọc tài liệu]** ([bedrock.md](../research/bedrock.md))
- **SageMaker: không cần cho MVP** vì Chronos-2 ngoài MVP. **[đề xuất]**
- **Guardrails không che PII trong kết quả tool** (và không kiểm tham số tool, định nghĩa tool), không có mẫu PII Việt Nam: che PII ở Lambda tool và bước nạp dữ liệu, thêm regex SĐT/CCCD/STK. Guardrails vẫn dùng cho đầu vào và đầu ra. **[đọc tài liệu]** ([bedrock.md](../research/bedrock.md)) Chưa tạo guardrail thử.
- **F3 viết bằng code tuần tự thay vì Graph của Strands**: Graph Python không rẽ lỗi thực thi, mâu thuẫn với NFR "LLM lỗi vẫn trả thẻ số". **[đọc tài liệu]** ([strands-agui.md](../research/strands-agui.md)) Hàm tuần tự có `try/except` và timeout cho bước LLM. **[đề xuất]**
- **Docker/container cho Runtime: không cần** (zip chạy được). **[đã chạy thử]** Container vẫn cần cho Lambda StatsForecast.
- **Next.js: thay bằng Vite SPA** ([ADR-0001](../decisions/0001-frontend-stack.md)); stack đã dựng thử trong [Frontend](../research/spike-frontend-stack.md).

## Ba nhịp chạy (§8)

| Nhịp | Kích hoạt | Việc làm | Độ trễ mục tiêu |
|---|---|---|---|
| Runtime đồng bộ | Chat, bấm kiểm tra, bấm cú sốc | Định tuyến, gọi tool, mô phỏng nhẹ, kiểm tra, stream | Vài giây (một lượt what-if đo được 6,3 s chỉ tính các call Bedrock, xem [Số đo](#số-đo-đã-có)) |
| Runtime bất đồng bộ | Sinh lại lộ trình, nạp sao kê | Agent chạy nền, nhận tiến độ từng bước | Chục giây đến vài phút |
| Event | Giao dịch mới, sửa phân loại, đổi mục tiêu | Phân loại, cập nhật số dư hũ, chỉnh nhanh dự báo, kiểm lệch, cổng nhắc | Dưới 1 phút |
| Batch đêm (02:00) | EventBridge Scheduler → Step Functions | Dự báo lại, hồ sơ hành vi, điểm chống chịu, bản tin | Xong trước 06:00 |
| Batch tuần (Chủ nhật) | Lịch | Backtest, hiệu chỉnh khoảng tin cậy, đánh giá agent trên bộ câu chuẩn, đồng bộ kho tri thức | Không ràng buộc |

Thư mục tương ứng: `pipelines/event`, `pipelines/nightly`, `pipelines/weekly`. Job nền "tới 8 giờ" của proposal quá mức cần; mục tiêu thật là chục giây đến vài phút, nạp sao kê giữ qua SQS + Lambda và báo tiến độ bằng polling. **[đọc tài liệu]** ([agentcore.md §4](../research/agentcore.md))

## Agentic harness 6 tầng (§9)

| Tầng | Việc | Thành phần |
|---|---|---|
| L0 Cổng vào | Xác thực, chặn prompt injection, che định danh | JWT authorizer của Runtime (**[đã chạy thử]**), Bedrock Guardrails cho đầu vào và đầu ra (**[đọc tài liệu]**: không kiểm kết quả tool) |
| L1 Intent Router | Phân loại ý định, rút tham số, đường nhanh hay đầy đủ | LLM nhỏ, JSON có cấu trúc bằng ép tool (**[đã chạy thử]**) |
| L2 Orchestrator | Lập kế hoạch, gọi specialist/tool song song, giữ ngân sách lượt | **Khác proposal**: mã điều khiển thứ tự (`agent/src/yofina_agent/turn.py`, `whatif.py`), không dùng agents-as-tools. Trong what-if, một lượt gọi vai `planner` chỉ dựng `ScenarioSpec` (hoặc mã dựng khi router đủ tham số, khóa `whatif_spec_source`); kế hoạch đọc tool là `schemas.Plan` có `limits`; trần 4 lượt gọi model mỗi lượt |
| L3 Specialist | Phân tích, mô phỏng, lộ trình, đọc tài liệu | **Khác proposal** (không có 4 Strands Agent): Analyst là một lượt gọi vai `planner` trên bản gọn; Simulation là engine tất định `forecast___run_scenario`; lộ trình là `roadmap_agent.py` (planner dựng nháp, LP và luật kiểm); đọc ảnh nằm trong Lambda nạp (`pipelines/ingest/`, vai `ingest`) |
| L4 Verifier | Đối chiếu số với kết quả tool, luật suitability, trả lỗi có cấu trúc (tối đa 2 vòng) | Luật Python (Automated Reasoning hoãn) |
| L5 Composer | Ghép văn bản và khối UI, gắn nhãn AI và trace_id | LLM nhỏ; khối UI do tool phát bằng `ACTIVITY_SNAPSHOT` (xem [Khối UI](#khối-ui)) |

Luồng thứ tự cố định (như kiểm tra trước khi quẹt) viết bằng **code tuần tự** thay vì Graph của Strands (xem [Bỏ và hoãn](#bỏ-và-hoãn)); khối số phát ngay sau `affordability_check`, LLM nhỏ chỉ viết hai câu giải thích trong thời hạn cố định. **[đề xuất]** Tool đi qua AgentCore Gateway dưới dạng MCP; Cedar kiểm từng tool call (**[đã chạy thử]**).

## Danh mục tool (§9)

Tên tool qua Gateway là `<target>___<tool>`: thư mục `gateway/tools/<target>/`, target `ledger`, `forecast`, `planner`, `knowledge`, `ingest`, `audit`. **[đã chạy thử]** ([Gateway §1](../research/spike-agentcore-gateway-identity.md)) Proposal viết tên với dấu chấm (`ledger.get_jar_balances`); Gateway không có dấu chấm trong tên target và luôn ghép `target___tool`, nên mọi nơi trong code và Cedar dùng dạng `ledger___get_jar_balances` (action Cedar cũng vậy).

| Nhóm (target) | Tool (tên đầy đủ qua Gateway) | Thư mục |
|---|---|---|
| `ledger` | `ledger___get_jar_balances`, `ledger___query_transactions`, `ledger___get_cashflow_summary`, `ledger___get_obligations`, `ledger___get_unclassified` (đọc); `ledger___update_profile`, `ledger___record_transaction`, `ledger___move_between_jars`, `ledger___assign_jar` (ghi, cần xác nhận); `ledger___save_turn` (lưu khối UI của lượt) | `gateway/tools/ledger/` |
| `forecast` | `forecast___get_forecast`, `forecast___run_scenario`, `forecast___list_scenarios`, `forecast___stress_test`, `forecast___affordability_check`, `forecast___get_resilience_score`, `forecast___get_behavior_profile` (đều chỉ đọc/tính; `run_scenario` ghi bảng `scenarios`) | `gateway/tools/forecast/` |
| `planner` | `planner___optimize_allocation`, `planner___check_suitability` (không ghi); `planner___save_roadmap`, `planner___get_roadmap`, `planner___schedule_nudge` (ghi; nhắc ghi bảng `nudges`, không dùng EventBridge Scheduler) | `gateway/tools/planner/` |
| `knowledge` | `knowledge___get_fee_schedule` (biểu phí có cấu trúc kèm nguồn), `knowledge___get_exchange_rate` (tỷ giá bán Vietcombank theo ngày). Không có `knowledge___search`: RAG đã cắt 24/11 | `gateway/tools/knowledge/` |
| `ingest` | `ingest___start_job`, `ingest___get_job_status`, `ingest___confirm_rows` (ghi) | `gateway/tools/ingest/` |
| `audit` | `audit___get_trace`, `audit___record_turn` (ghi bản ghi lượt) | `gateway/tools/audit/` |

Danh sách trên khớp `contracts/tools/*.json` ngày 25/11; mỗi tool có một file Cedar ở `gateway/policies/`.

Mapping đầy đủ (chức năng, phía sau, ghi hay không) ở [proposal-summary.md §9](../proposal/proposal-summary.md#9-agentic-harness-9) (dùng tên có dấu chấm). Mỗi tool Lambda đọc tên tool từ `context.client_context.custom["bedrockAgentCoreToolName"]` rồi cắt tiền tố target. **[đọc tài liệu]**

## Mô hình dữ liệu

(§7) Aurora PostgreSQL Serverless v2, pgvector cho bước embedding của phân loại; truy cập qua Data API với role riêng và RLS (xem [Dữ liệu](#dữ-liệu)). Schema thực là chuỗi [migration](../../db/README.md) (0001 tới 0054 ngày 25/11). Bảng chính:

| Bảng | Nội dung | Trạng thái |
|---|---|---|
| `users`, `jars` | Người dùng, lương và ngày nhận đã khai, mức chấp nhận rủi ro. Hũ có `kind` (spending, saving, obligation, system), `split_percent`, mục tiêu và hạn. **Hai hũ hệ thống** mỗi người: "Tiền vào khác" (`system_role other_income`) và "Chưa phân loại" (`unclassified`, số dư được âm); tổng số dư là tổng mọi hũ | 0001, 0005 |
| `transactions` | Sổ cái: thời gian, số tiền, đối tác (`merchant`), lời nhắn (`note`), hũ, `tx_type`, nguồn trả (`funding_source` jar hoặc credit), người nhận, nghĩa vụ liên kết, khóa khử trùng, nhãn phân loại (`classified_by`, `classification_confidence`, `needs_review`) | 0001, 0005 |
| `payees` | Người nhận của ví mô phỏng (seed theo persona) | 0005 |
| `obligations` | Khoản tiền ra theo lịch: trả sau (tự sinh), khoản vay, tiền trọ, hóa đơn, thuê bao (người dùng khai); số tiền kỳ vọng và khoảng, phí, ngày đến hạn, chu kỳ, trạng thái, hũ trả | 0005 |
| `credit_lines` | Hạn mức Trả sau (mô phỏng) và dư nợ gốc | 0005 |
| `fee_schedules` | Biểu phí có cấu trúc theo sản phẩm tín dụng, kèm nguồn và ngày hiệu lực | 0005, seed |
| `salary_events` | Lương về chờ xác nhận một chạm rồi chia vào hũ | 0005 |
| `category_rules` | Luật phân loại học từ lần người dùng sửa, kèm phạm vi (một lần hay luôn luôn cho người nhận đó) | 0005 (phase 4 dùng) |
| `tx_type_map`, `jar_templates` | Bảng tra: loại giao dịch sang hũ (bước 0 của phân loại), hũ mặc định cho onboarding | 0005, seed |
| `forecast_runs`, `forecast_jar_summaries`, `forecasts` | Lần chạy dự báo (model, ngày gốc, độ phủ, nhãn tin cậy, cờ ước lượng ban đầu), tóm tắt mỗi hũ (ngày cạn, xác suất hụt, đủ/sát/hụt), phân vị chi tiêu ngày và số dư theo ngày | 0006 |
| `conversation_turns`, `turn_blocks`, `confirm_resolutions` | Lượt hội thoại, khối UI đã phát, trạng thái đã thực hiện của khối xác nhận | 0001, 0003, 0004 |
| `resilience_scores` | Điểm và 4 thành phần theo ngày | 0052 |
| `roadmaps` | Lộ trình JSON có phiên bản và lý do sinh lại (kèm `roadmap_jobs`, `behavior_flags` cho điểm gãy hành vi) | 0052 |
| `scenarios`, `nudges`, `feedback` | Kịch bản đã chạy, nhắc đã gửi, phản hồi | 0010 (0053 nới loại nhắc cho bản tin của batch đêm) |
| `behavior_profiles` | Hồ sơ hành vi do batch đêm ghi (nhận xét kèm bằng chứng) | 0053 |
| `audit_events` | Mỗi gợi ý: trace_id, dữ liệu đã dùng, luật đã kiểm, kết quả; có thể thêm khối UI đã phát (để phát lại) | 0001 |

Sự kiện của sổ cái (`transaction.recorded`, `salary.confirmed`, `obligation.changed`, `profile.updated`) và của dự báo (`forecast.updated`) đi qua EventBridge bus `yofina-bus`: hợp đồng ở [contracts/README.md](../../contracts/README.md#sự-kiện-eventbridge-bus-yofina-bus).

Cổng chất lượng: khởi đầu lạnh (< 30 ngày: luật + trung bình nhóm; 30–90: thống kê; > 90: mô hình nền tảng), điểm độ phủ, khử trùng bằng khóa băm, độ tươi, thiếu dữ liệu thì hỏi lại. Số đo làm các mốc này đáng xem lại: hurdle thắng seasonal naive từ khoảng 21–30 ngày, AutoETS chỉ dùng từ 60–90 ngày. **[đã chạy thử]** ([ML §3](../research/spike-ml-forecasting.md), dữ liệu tổng hợp) Mốc chỉnh **[đề xuất]**.

## Hợp đồng đầu ra (Composer)

(§9, số trong ví dụ là minh họa của proposal.) Composer trả một JSON duy nhất; frontend ánh xạ mỗi `type` sang một component. Thêm tính năng là thêm một loại khối. Sau cập nhật 2026-11-21, JSON này là **bản ghi của lượt** (lưu DB để phát lại và kiểm toán); trên đường stream, mỗi khối do tool phát riêng bằng `ACTIVITY_SNAPSHOT` (xem [Khối UI](#khối-ui)).

```json
{
  "trace_id": "tr_8f2c",
  "intent": "what_if",
  "text": "Nếu mua bằng Ví Trả Sau, hũ Giải trí tháng 12 sẽ hụt 410.000đ.",
  "blocks": [
    {"type": "forecast_timeline", "jar": "an_uong", "horizon_days": 30,
     "baseline": {"runout_date": "2026-11-23", "p_shortfall": 0.71},
     "scenario": {"runout_date": "2026-11-23", "p_shortfall": 0.71}},
    {"type": "obligation_impact", "method": "bnpl", "principal": 1200000,
     "fee": 33000, "due_date": "2026-12-05",
     "next_month_gap": {"jar": "giai_tri", "amount": 410000}},
    {"type": "options", "items": [
      {"id": "delay_2w", "label": "Hoãn 2 tuần, trả bằng hũ Giải trí"},
      {"id": "split", "label": "Góp 300.000đ mỗi tuần trong 4 tuần"}]},
    {"type": "explain", "data_used": ["forecast:run_1120", "obligations", "fee_schedule:bnpl"],
     "rules_checked": ["obligation_ratio", "emergency_buffer"],
     "confidence": "medium", "coverage": 0.82},
    {"type": "confirm", "action": "schedule_nudge", "requires_user": true}
  ]
}
```

Khối có phong bì `v`, `id`, `trace_id`, `fallback_text` và schema Zod ở frontend (theo [ADR-0001](../decisions/0001-frontend-stack.md)). Hình dạng THẬT của các khối (không phải ví dụ minh họa ở trên) nằm ở [contracts/blocks/](../../contracts/blocks/): từ phase 2 có thêm `forecast_timeline` (đường P10/P50/P90 số dư, mốc nghĩa vụ và lương, ngày cạn, `p_shortfall` hoặc `confidence_band`; chưa có biến thể `scenario` trước-sau, thêm ở phase 3 như trường tùy chọn), `proactive_card`, `confirm_action` và `receipt_action`. Số trong khối do code dựng từ kết quả tool; số trong phần `text` do LLM viết nên vẫn cần kiểm bằng `NumericGrounding`.

## Pipeline F1–F7 (§10)

| Pipeline | Tính năng | Nhịp | Thư mục dự kiến |
|---|---|---|---|
| 10.1 Hỏi "nếu thì" | F2 | Runtime, streaming | `agent/` (+ `gateway/tools/forecast/`) |
| 10.2 Kiểm tra trước khi quẹt | F3 | Runtime, mục tiêu < 2 giây | `gateway/tools/forecast/` (affordability_check) + hàm tuần tự trong agent |
| 10.3 Phân hũ tự động, cập nhật tức thời | nền, F5 | Event | `pipelines/event/` |
| 10.4 Batch đêm | F1, F4, F7 | 02:00 | `pipelines/nightly/`, `ml/` |
| 10.5 Sinh/sinh lại lộ trình | F5 | Theo sự kiện, theo yêu cầu | `gateway/tools/planner/`, agent |
| 10.6 Nạp dữ liệu ngoài ví | F6 | Bất đồng bộ | `gateway/tools/ingest/` (ảnh chụp và CSV; PDF mở rộng, đọc bằng model, không dùng Data Automation) |

## ML và kỹ thuật (§11)

Chi tiết và số đo ở mục [ML (kết quả đã đo)](#ml-kết-quả-đã-đo) phía trên. Danh sách kỹ thuật proposal §11, sau khi cập nhật: dự báo (hurdle tự viết; seasonal naive làm mốc so sánh; StatsForecast chỉ chạy trên máy để so backtest; Chronos-2 ngoài MVP, chốt 21/11), adaptive conformal inference (chỉ chỉnh phân vị chi tiêu ngày; dải số dư người dùng thấy đến từ Monte Carlo đã hiệu chỉnh, cộng CQR và PAV từ #25, xem [backtest-final.md](../research/backtest-final.md)), Monte Carlo cho ngày cạn/xác suất hụt, điểm chống chịu theo Spend/Save/Borrow/Plan, PELT (`ruptures`) theo tuần + CUSUM tự viết (bỏ ADWIN, bỏ PyOD; điểm gãy chỉ dùng để sinh lại lộ trình, không cắt cửa sổ dự báo), quy hoạch tuyến tính bằng `scipy` phân bổ hũ, phân loại giao dịch bước 0 + thác luật → embedding (pgvector) → LLM. Phía agent: routing, mã điều khiển thứ tự thay cho orchestrator-workers tự do, evaluator-optimizer (Verifier tối đa 2 vòng trong trần 4 lượt gọi), context engineering, AgentCore Memory (hai strategy override, không Mem0, không ReasoningBank), proactive agent (cổng giá trị của batch đêm), Cedar, AG-UI. Không có hybrid search + rerank (RAG đã cắt). Chi tiết lệch: [ADR-0004](../decisions/0004-lech-so-voi-proposal.md).

## Khả năng quan sát và đánh giá (§9)

Trace OpenTelemetry mỗi lượt (span cho router, planner, tool call, verifier); dashboard CloudWatch (độ trễ, token, chi phí, lỗi tool, số lần luật chặn); AgentCore Evaluations (Correctness, Helpfulness, GoalSuccessRate); evaluator tự viết `NumericGrounding`, `SchemaValidity`, `SuitabilityCompliance`; đánh giá offline bằng bộ câu chuẩn có quỹ đạo tool mong đợi (`evals/`).

- `trace_id` do client sinh qua `traceparent` (xem [Frontend gọi thẳng Runtime](#frontend-gọi-thẳng-runtime)); log của app nằm ở log group của Runtime. **[đã chạy thử]** ([Runtime §6](../research/spike-agentcore-runtime-cors.md)) Bật OTel (ADOT) làm cold start V1 tăng khoảng 2,5 s; span chưa thấy được vì chưa bật CloudWatch Transaction Search (đổi cấu hình tài khoản, chưa làm).
- Quyết định của Policy: ở `LOG_ONLY` mọi lời gọi đều qua, quyết định xem ở metric `AWS/Bedrock-AgentCore` (`AllowDecisions`, `DenyDecisions`, …); log ứng dụng của Gateway không ghi quyết định policy; chi tiết từng quyết định nằm ở span, cần Transaction Search. **[đã chạy thử]** ([Gateway §4](../research/spike-agentcore-gateway-identity.md))
- Evaluations, evaluator tự viết, chi phí: **[đọc tài liệu]** ([agentcore.md §3.6, §3.8](../research/agentcore.md)); chưa thử. Lấy mẫu online thấp, ưu tiên evaluator code-based; judge dựng sẵn ở Singapore đi qua global cross-region inference.

## Số đo đã có

Tất cả **[đã chạy thử]** ngày 2026-11-21 ở `ap-southeast-1` (trừ ML và frontend chạy local). Mẫu nhỏ, một máy ở Việt Nam, dùng làm bậc độ lớn; ML trên dữ liệu tổng hợp.

| Hạng mục | Số đo | Nguồn |
|---|---|---|
| Gateway, lời gọi ấm (đo từ Việt Nam qua internet) | khoảng 90–145 ms trơn; khoảng 160–195 ms khi có interceptor và Cedar (cộng khoảng 50–80 ms); nhiễu ±40 ms | [Gateway §6](../research/spike-agentcore-gateway-identity.md) |
| Gateway, lần gọi lạnh (Lambda lạnh) | 0,55–1,8 s | [Gateway §6](../research/spike-agentcore-gateway-identity.md) |
| Tìm tool ngữ nghĩa (tiếng Việt) | 320–370 ms mỗi lần | [Gateway §7](../research/spike-agentcore-gateway-identity.md) |
| Data API, một lệnh (Lambda ngoài VPC, ấm) | p50 12–52 ms, p95 ≤ 57 ms | [Aurora §2](../research/spike-aurora-data-api.md) |
| Data API, luồng 3 truy vấn của kiểm tra trước khi quẹt | p50 91 ms, p95 113 ms, max 179 ms (100 lần) | [Aurora §2](../research/spike-aurora-data-api.md) |
| Cùng luồng với RLS | hàm plpgsql: p50 93 ms, p95 106 ms; transaction tường minh: p50 160 ms, p95 201 ms | [Aurora §4](../research/spike-aurora-data-api.md) |
| Ghi bằng transaction 2 câu | p50 121 ms, p95 128 ms | [Aurora §2](../research/spike-aurora-data-api.md) |
| Aurora đánh thức sau auto-pause | 16,4 s tới lần thành công đầu, 4 lần `DatabaseResumingException` | [Aurora §6](../research/spike-aurora-data-api.md) |
| Dựng cluster Aurora Serverless v2 | 429 s tới khi Data API dùng được | [Aurora §1](../research/spike-aurora-data-api.md) |
| Runtime, cold start tới event đầu (chế độ không LLM) | V1 trung vị 2,68 s, V2 trung vị 2,51 s (httpx); trình duyệt V2 1,7–2,0 s; ấm khoảng 0,3 s | [Runtime §4](../research/spike-agentcore-runtime-cors.md) |
| Runtime, có LLM (Haiku 4.5 + 1 tool, V1) | lượt đầu: event đầu 5,5 s, chữ đầu 6,55 s, xong 6,8 s; lượt hai cùng phiên: event đầu 0,33 s, xong 0,97 s | [Runtime §4](../research/spike-agentcore-runtime-cors.md) |
| Runtime, thêm OTel | cold start V1 trung vị 5,18 s (tăng khoảng 2,5 s) | [Runtime §4](../research/spike-agentcore-runtime-cors.md) |
| Runtime, tạo hoặc cập nhật | V1 khoảng 15 s và 10 s; V2 khoảng 5 phút | [Runtime §5](../research/spike-agentcore-runtime-cors.md) |
| Một lượt what-if (router Haiku, planner Sonnet 2 vòng, diễn giải Haiku) | 6,29–6,38 s (3 lượt); chưa tính guardrail, KB, Gateway, Aurora, cold start | [Bedrock §2c](../research/spike-bedrock-models.md) |
| TTFT chữ đầu của model (một prompt ngắn) | Haiku 4.5 0,38–0,91 s; Sonnet 4.6 0,57–0,61 s; Nova 0,32–0,66 s | [Bedrock §2b](../research/spike-bedrock-models.md) |
| Quota Claude 4.x | 10 request/phút mỗi model | [Bedrock §2a](../research/spike-bedrock-models.md) |
| Monte Carlo (6 hũ × 30 ngày, numpy, desktop) | 5.000 đường 76 ms; 10.000 đường khoảng 153–163 ms | [ML §6](../research/spike-ml-forecasting.md) |
| Hurdle, 31 origin × 7 chuỗi | khoảng 0,65 s | [ML §4](../research/spike-ml-forecasting.md) |
| StatsForecast AutoETS (7 chuỗi × 30 ngày) | 0,25 s; cài 332 MB | [ML §2](../research/spike-ml-forecasting.md) |
| Chronos-2 (120M, CPU desktop) | 7 chuỗi context 180 ngày 0,2 s; 28,6 chuỗi/s theo lô; RAM đỉnh 1.193 MB; model 478 MB | [ML §4](../research/spike-ml-forecasting.md) |
| LP phân bổ lương (`linprog`) | khoảng 1 ms (trung vị) | [ML §8](../research/spike-ml-forecasting.md) |
| Độ phủ khoảng 80% | tổng 30 ngày 0,48–0,61 (hũ dày, mọi model); hurdle hũ thưa 0,72; conformal mặc định theo ngày 0,54–0,60 | [ML §3](../research/spike-ml-forecasting.md) |
| Phân loại bằng embedding (1-NN theo hũ, 43 chuỗi) | 81–84% thô, 93% sau chuẩn hóa chuỗi (Cohere v3 và v4) | [Bedrock §6](../research/spike-bedrock-models.md) |
| Bundle frontend (bản thử) | JS 386,9 KB gzip (một chunk), CSS 17,9 KB gzip | [Frontend §8](../research/spike-frontend-stack.md) |

## Chưa kiểm chứng

- **Nối frontend thật với Runtime thật**, gồm interrupt/resume AG-UI qua Runtime và `AgentCoreMemorySessionManager`; hai nửa của cơ chế xác nhận (token và interrupt) chưa ghép; endpoint cấp token bằng HTTP API thật, DynamoDB `jti` dưới tải đồng thời, độ trễ `cognito-idp:GetUser`.
- **CORS từ domain thật**, Safari trên iPhone, Amplify Hosting; token hết hạn giữa luồng SSE; điện thoại thật (vuốt Drawer, bàn phím ảo, PWA).
- **Strands `MCPClient` khi Cedar từ chối** (`-32002`) và với Gateway thật (tên `___`); Cedar tham chiếu `context.input.user_id` khi `user_id` không khai trong schema; thông điệp từ chối khi Gateway không bật `DEBUG`.
- **Quan sát**: span của Runtime và Gateway trong CloudWatch (chưa bật Transaction Search), độ trễ trích xuất của Memory, Evaluations.
- **LLM**: Sonnet 4.6 làm planner nhiều bước; ảnh chụp màn hình thật và PDF; Guardrails (độ trễ, PII tiếng Việt); Knowledge Bases; mọi khẳng định về Claude 5.x (bị chặn); họ GPT-6/5.x báo quota nhưng bị `AccessDenied`.
- **ML**: mô hình dự báo trên dữ liệu không do cùng bộ sinh tạo ra; tương quan giữa các hũ; hiệu chỉnh penalty PELT trên nhiều persona; cold start và suy luận trên vCPU Lambda (Chronos-2, container); xử lý khoảng tổng 30 ngày phủ thiếu.
- **Aurora**: pause dài, kNN và HNSW ở quy mô lớn, nhiều Lambda gọi đồng thời.
- **Khối UI**: nối tool phát khối với frontend; error boundary từng khối; `abortRun`, kết nối lại.
- **Chi phí thực** chưa đối chiếu hóa đơn; **Region** chưa chốt; các số liệu Region và giá của AgentCore mới đọc từ tài liệu.
