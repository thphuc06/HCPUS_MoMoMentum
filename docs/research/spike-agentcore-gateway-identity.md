# Spike thực nghiệm: AgentCore Gateway + Lambda target + Policy (Cedar) + danh tính người dùng

Ngày chạy: **2026-11-21**, Region `ap-southeast-1`, trên tài khoản AWS thật (đã dọn sạch, xem mục 6). Mã và script: `spikes/agentcore-gateway-identity/`. Mọi con số và đoạn trích dưới đây là **quan sát thật** trừ chỗ ghi rõ "suy ra" hoặc "theo tài liệu". Dữ liệu nhạy cảm đã che (`<sub-A>`, `<sub-B>`, địa chỉ IP).

Phạm vi: mọi tool là Lambda sau Gateway MCP, người dùng đăng nhập Cognito; yêu cầu: tool chỉ đụng dữ liệu của chủ JWT, tool ghi chỉ chạy khi người dùng thật sự xác nhận.

## 0. Kết luận ngắn

1. **Lambda target không nhận bất kỳ claim nào của người gọi.** `event` chỉ gồm đúng các tham số tool; `context.client_context.custom` chỉ có siêu dữ liệu của Gateway (id gateway, target, tên tool, message id), không có `sub`, `username`, `client_id`. Đã xác nhận bằng cách in toàn bộ event và context.
2. **Cách đưa danh tính xuống tool chạy được: request interceptor Lambda** (`passRequestHeaders: true`) đọc `Authorization`, lấy `sub`, **ghi đè `arguments.user_id`** và/hoặc **đặt header `x-user-id`** (target phải allowlist header; Lambda đọc ở `context.client_context.custom["bedrockAgentCorePropagatedHeaders"]`). User A gửi `user_id` của B bị ghi đè thành A; header `x-user-id` do client tự gửi cũng bị ghi đè bởi giá trị của interceptor. Gateway kiểm chữ ký JWT trước khi gọi interceptor.
3. **Cedar `context.input.user_id == principal.id` chạy đúng** và chặn A đọc/ghi dữ liệu của B khi không có interceptor. `principal.id` là `sub`; mọi claim khác (cả `sub`, `username`, `client_id`) là **tag**, dùng `principal.hasTag("x") && principal.getTag("x") == "..."`.
4. **Thứ tự: JWT authorizer, rồi request interceptor, rồi Cedar (thấy tham số đã bị interceptor sửa), rồi Lambda.** Hai lớp độc lập nhau: gỡ interceptor thì Cedar vẫn chặn, gỡ Cedar thì interceptor vẫn ghi đè.
5. **Header allowlist một mình không phải danh tính**: header client gửi đi qua nguyên văn nếu target allowlist nó (A gửi `x-user-id: <sub-B>` thì Lambda thấy `<sub-B>`). Chỉ header do interceptor đặt mới tin được.
6. **Token xác nhận HMAC do server cấp chạy được** (13 ca, mục 5): LLM tự điền `user_confirmed=true`, bịa token, ký sai khóa, đổi tham số, replay, dùng token của người khác đều bị Lambda từ chối; chỉ luồng "UI bấm nút, endpoint riêng cấp token, gọi lại tool với token" mới ghi. **Cedar không kiểm được chữ ký**, chỉ ép được hạn mức, khớp `user_id`, và có/không có `confirm_token` dạng `*.*`.
7. **Phản hồi từ chối của Cedar là lỗi giao thức JSON-RPC** (`error.code = -32002`, HTTP 200), không phải tool result `isError`. Phía MCP client Python nó nổi lên thành ngoại lệ (`ExceptionGroup`), không phải nội dung LLM đọc được. Agent (Strands) phải xử lý đường này.
8. Độ trễ warm qua Gateway khoảng **90-145 ms trơn, 160-195 ms khi có cả interceptor lẫn policy** (đo từ Việt Nam qua internet, nhiễu ±40 ms); lần gọi lạnh 0,55-1,8 s. Rất xa ngưỡng 2 giây.

## 1. Dựng tối thiểu và tên tool thực tế (Q1)

**Cách thử.** `setup_base.py` + `step1_plain.py`: Cognito User Pool (`yofina-spike-gw-pool`) + app client không secret (`USER_PASSWORD_AUTH`) + 2 user (`user-a`, `user-b`, mật khẩu sinh ngẫu nhiên); Lambda Python 3.13 `ledger` với 2 tool; Gateway `CUSTOM_JWT` (`discoveryUrl` của Cognito + `allowedClients`), target `ledger` kiểu `lambda` với `toolSchema.inlinePayload`, outbound `GATEWAY_IAM_ROLE`. Client: gói `mcp` 1.30 (`streamablehttp_client` + `ClientSession`) và `httpx` thô.

**Kết quả quan sát.**

- `tools/list` trả đúng hai tool tên **`ledger___get_jar_balances`** và **`ledger___move_between_jars`** (ba gạch dưới, đúng như ghi chú cũ). `inputSchema` trả nguyên.
- Giới hạn tên (thử tạo target thật): target **100 ký tự chữ-số = chấp nhận, 101 = bị từ chối** (`ValidationException`, pattern `([0-9a-zA-Z][-]?){1,100}`); chuỗi `a-a-a-...-a` dài 199 ký tự cũng khớp pattern và được chấp nhận. **Gạch dưới và dấu chấm trong tên target bị từ chối.** Tên **gateway** theo pattern `([0-9a-zA-Z][-]?){1,48}`.
- Tên **tool trong schema không bị kiểm khi tạo target**: 128 và cả 129 ký tự, `get_x`, `get.x`, `get-x`, `a___b` đều tạo được (READY). Tức giới hạn 128 trong ghi chú cũ **không được Gateway cưỡng chế**. Giới hạn thực tế đến từ phía model: tên tool Bedrock Converse tối đa 64 ký tự và chỉ `[a-zA-Z0-9_-]` [suy ra từ kiến thức về Converse, chưa kiểm trong spike này]; giữ `<target>___<tool>` ngắn (hiện 25 ký tự).
- Chỉ **access token** vào được. ID token (có `aud`, không có `client_id`) bị `403 insufficient_scope`. Token bị sửa `sub` (giữ chữ ký cũ) hoặc chữ ký hỏng cũng ra **403** (không phải 401), thông điệp `insufficient_scope - The request requires higher privileges...` gây hiểu nhầm. Claim thực của access token Cognito: `sub, iss, client_id, token_use=access, scope="aws.cognito.signin.user.admin", username, auth_time, exp, iat, jti, origin_jti, event_id, acr, amr`; **không có `aud`** (xác nhận điều ghi chú cũ phỏng đoán).
- Gateway **có kiểm `inputSchema`**: thiếu trường `required` hoặc sai kiểu (số thay chuỗi, chuỗi thay số, `1.5` thay integer, `"true"` thay boolean) trả `result.isError=true` với text `ValidationException - Parameter validation failed: ... Missing required field(s)...` hoặc `... has invalid type: integer found, string expected`. **Tham số thừa không bị từ chối** (`evil: "x"` vẫn tới Lambda), nên Lambda phải bỏ qua tham số lạ.

## 2. Lambda nhận được gì (Q2)

Event và context Lambda `ledger` in ra khi user A gọi `ledger___get_jar_balances` qua gateway trơn (đã che):

```json
{
  "event": { "user_id": "<sub-A>" },
  "client_context": {
    "custom": {
      "bedrockAgentCoreTargetId": "MQ9KHKBSSK",
      "bedrockAgentCoreGatewayId": "yofina-spike-gw-plain-<id>",
      "bedrockAgentCoreMessageVersion": "1.0",
      "bedrockAgentCoreMcpMessageId": "1",
      "bedrockAgentCoreAwsRequestId": "6f522e7c-...",
      "bedrockAgentCoreToolName": "ledger___get_jar_balances"
    },
    "env": null, "client": null
  },
  "context": {
    "function_name": "yofina-spike-gw-ledger",
    "identity": { "cognito_identity_id": null, "cognito_identity_pool_id": null },
    "attrs": ["aws_request_id","client_context","function_name","function_version","get_remaining_time_in_millis",
              "identity","invoked_function_arn","log","log_group_name","log_stream_name","memory_limit_in_mb","tenant_id","w3c"]
  }
}
```

**Kết luận:** không có `sub`, `username`, `client_id`, `iss`, scope hay bất kỳ phần nào của JWT. `context.identity` (Cognito identity) rỗng. Trường `user_id` ở trên **do client gửi**, nên giả mạo được. Khi target allowlist header và có header được gửi, thêm khóa `bedrockAgentCorePropagatedHeaders` (object lồng nhau mặc định) vào `client_context.custom`; khi không có header thì khóa này vắng.

## 3. Đưa danh tính xuống tool: thử từng cách (Q3)

### 3a. Request interceptor: CHẠY

Gateway `main` có `interceptorConfigurations=[{interceptor:{lambda:{arn}}, interceptionPoints:["REQUEST"], inputConfiguration:{passRequestHeaders:true}}]`; role gateway cần `lambda:InvokeFunction` trên Lambda interceptor. Input mà interceptor nhận (header `Authorization` còn nguyên, Gateway **không giải mã claim giúp**, interceptor tự decode phần payload; không cần kiểm chữ ký vì Gateway đã kiểm):

```json
{"interceptorInputVersion":"1.0","mcp":{"gatewayRequest":{"path":"/mcp","httpMethod":"POST",
 "headers":{"Authorization":"Bearer <jwt>","Host":"<gw>.gateway.bedrock-agentcore.ap-southeast-1.amazonaws.com",
            "X-Forwarded-For":"<ip>","X-Amzn-Trace-Id":"Root=1-...","Content-Type":"application/json", "...":"..."},
 "body":{"id":5,"jsonrpc":"2.0","method":"tools/call","params":{"name":"ledger___get_jar_balances","arguments":{"user_id":"<sub-B>"}}},
 "context":null},"gatewayResponse":null,"rawGatewayRequest":{"body":"{...}"}}}
```

Output chạy được (trích từ `lambdas/interceptor/handler.py`): `{"interceptorOutputVersion":"1.0","mcp":{"transformedGatewayRequest":{"body":<body đã sửa>,"headers":{"x-user-id":"<sub>"}}}}`.

Kết quả, user A (JWT thật) gọi `get_jar_balances` với `user_id = <sub-B>`:

| Chế độ interceptor | Lambda `ledger` nhận | Ghi chú |
|---|---|---|
| `passthrough` | `event.user_id = <sub-B>` | A đọc được dữ liệu của B (xác nhận lỗ hổng gốc) |
| `overwrite` | `event.user_id = <sub-A>`, `bedrockAgentCorePropagatedHeaders = {"x-user-id":"<sub-A>"}` | bị ghi đè |
| `deny` (trả `transformedGatewayResponse`) | Lambda không được gọi; client nhận `result.isError=true`, text "user_id không khớp JWT" | ngắt sớm, bỏ qua policy và target |

Các điều khác quan sát được:

- **Bỏ trống `user_id`** (tool khai `required`): ở chế độ `overwrite` vẫn qua, Lambda nhận `user_id=<sub-A>`. Tức interceptor chạy **trước** bước kiểm schema.
- **Header do client gửi đè**: A gửi `x-user-id: <sub-B>` tới gateway có interceptor `overwrite`, Lambda thấy `<sub-A>` (header của interceptor thắng, đúng như tài liệu "Header precedence").
- **`user_id` không có trong schema** (target `ledgerx`, tool `get_jar_balances` với `properties: {}`): LLM không thấy tham số; interceptor tiêm `user_id` vào `arguments` thì Lambda **vẫn nhận được**; kể cả khi "LLM" tự nhét `user_id=<sub-B>` vào, vẫn bị ghi đè. Gateway không cắt tham số lạ.
- **Interceptor chỉ chạy sau khi JWT hợp lệ**: gửi JWT bị sửa `sub` hoặc hỏng chữ ký, nhận 403 và Lambda interceptor **không được gọi** (đếm log: 0 lần).
- **Cấu hình**: `passRequestHeaders` bắt buộc `true` để thấy `Authorization`. Interceptor "đọc claim" nghĩa là tự `base64url`-decode phân đoạn giữa của JWT.

### 3b. Cedar ép `user_id == principal.id`: CHẠY

Policy engine `yofina_spike_gw_pe` (tên engine dùng gạch dưới). Hai luật đã **qua validation và ACTIVE** (resource phải là ARN gateway; tạo target trước, tạo policy sau, rồi mới gắn engine vào gateway bằng `UpdateGateway`):

```cedar
permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::"ledger___get_jar_balances",
  resource == AgentCore::Gateway::"arn:aws:bedrock-agentcore:ap-southeast-1:<ACCOUNT>:gateway/<GATEWAY_ID>"
) when {
  context.input.user_id == principal.id
};

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

Chế độ `ENFORCE`, **không** interceptor, user A:

| Ca | Kết quả |
|---|---|
| A đọc của A | cho phép |
| A đọc của B | **từ chối** |
| A ghi của A, confirmed, 100k | cho phép |
| A ghi của A, `user_confirmed=false` | từ chối |
| A ghi của A, 9 triệu (vượt hạn mức 5 triệu) | từ chối |
| A ghi của B, confirmed | từ chối |

Cú pháp đã kiểm thật:

- `principal.id` hợp lệ (chuỗi `sub`). `principal is AgentCore::OAuthUser`.
- **Claim khác là tag**: `forbid(...) when { principal.hasTag("username") && principal.getTag("username") == "user-b" }` chạy đúng (A qua, B bị chặn; thông điệp từ chối nêu tên policy). **`sub` cũng có mặt như tag** (`principal.hasTag("sub")` đúng).
- `context.input has confirm_token && context.input.confirm_token like "*.*"` hợp lệ cho tham số tùy chọn kiểu string. `<=` trên `integer` chạy. `boolean` dùng thẳng.
- Tham số `required` bị thiếu khi Cedar đánh giá: bị từ chối với lý do `Authorization denied due to policy evaluation errors: Property user_confirmed is missing but required`.
- Một `permit` vô điều kiện cho principal/action/resource bị **từ chối lúc tạo** (`CREATE_FAILED`, bất đồng bộ) với finding `Overly Permissive: Policy Engine will allow every request...` khi `validationMode=FAIL_ON_ANY_FINDINGS`. Tạo được với `IGNORE_ALL_FINDINGS`.
- `boto3` 1.44.9 nhận `definition={"cedar": {"statement": ...}}`; một số ví dụ CLI trong tài liệu hiện hành viết `{"policy":{"statement":...}}`: dùng đúng tên theo model SDK đang cài.
- Role gateway chỉ cần `lambda:InvokeFunction` (hai Lambda) + `bedrock-agentcore:GetPolicyEngine`, `AuthorizeAction`, `PartiallyAuthorizeActions` (không cần `InvokeGateway` cho target Lambda). Điều kiện tin `aws:SourceAccount` + `aws:SourceArn` trên `gateway/*` dùng được.

### 3c. Cách khác

- **Header allowlist do client gửi**: *không dùng được làm danh tính*. A gửi `x-user-id: <sub-B>` tới gateway trơn, Lambda thấy `bedrockAgentCorePropagatedHeaders = {"x-user-id":"<sub-B>"}`. Header không allowlist (`x-other`) bị bỏ.
- **Token exchange / OBO của AgentCore Identity và token passthrough**: **không áp dụng cho Lambda target**. Bảng "outbound authorization" của tài liệu hiện hành cho Lambda chỉ có **gateway service role** (không OAuth, không token exchange, không passthrough); passthrough có cho target "AgentCore Runtime (HTTP)", token exchange có cho MCP server/OpenAPI. Chưa thử vì không dựng target loại đó (ngoài phạm vi: tool của Yofina là Lambda). [theo tài liệu]
- **`Authorization` do interceptor đặt** tự được chuyển đến target (theo tài liệu) nhưng với Lambda target không có chỗ nhận header Authorization (chỉ header allowlist qua `client_context`), nên vô nghĩa ở đây.

Tổng hợp theo yêu cầu "A gọi với `user_id` của B thì sao":

| Cách | A gửi `user_id`=B | Ghi chú |
|---|---|---|
| Không gì cả | Lambda nhận B | lỗ hổng |
| (a) Interceptor `overwrite` | bị **ghi đè** thành A | LLM không cần biết `user_id` |
| (a') Interceptor `deny` | bị **chặn** (isError) | cần mã client hiển thị lỗi |
| (b) Cedar `== principal.id` | bị **chặn** (-32002) | không sửa được giá trị, chỉ từ chối |
| (c) Header client gửi | Lambda nhận B | không an toàn |
| (c') Header do interceptor đặt | ghi đè thành A | tương đương (a) |

## 4. Policy engine (Q4)

- **Gắn vào Gateway**: `policyEngineConfiguration={"arn":..., "mode":"LOG_ONLY"|"ENFORCE"}` ở `CreateGateway`/`UpdateGateway`; `UpdateGateway` yêu cầu truyền lại mọi trường (script đọc `GetGateway` rồi ghi đè). Bỏ trường `policyEngineConfiguration` khỏi update thì engine được gỡ (đã kiểm bằng `GetGateway`). Thay đổi policy/engine có hiệu lực sau vài giây (sleep 8 s là đủ).
- **Mặc định từ chối**: đúng. Thông điệp: `[No policy applies to the request (denied by default).]`. Tool bị từ chối vĩnh viễn với principal (chưa có permit nào, ví dụ `ledgerx___get_jar_balances` trước khi có luật) **không hiện trong `tools/list`**; tool có permit có điều kiện thì vẫn hiện (A thấy cả hai tool `ledger___*` dù luật còn điều kiện).
- **`LOG_ONLY` (cấp engine)**: mọi lời gọi **đều qua**, kể cả ca lẽ ra bị từ chối: 6/6 ca của bộ test được Lambda chạy (kể cả ghi vượt hạn mức 9 triệu, ghi của B, đọc của B). Quyết định ghi ở **metric CloudWatch** namespace `AWS/Bedrock-AgentCore` (bật mặc định, không cần cấu hình), dimension `PolicyEngine`, `OperationName` (`AuthorizeAction`/`PartiallyAuthorizeActions`), `Mode` (`LOG_ONLY`/`ENFORCE`), `ToolName`, `TargetResource`. Đã thấy `AllowDecisions`, `DenyDecisions`, `NoDeterminingPolicies`, `DeterminingPolicies`, `MismatchErrors`, `PolicyMismatch` với `Mode=LOG_ONLY` (số `DenyDecisions` ở `Mode=LOG_ONLY` > 0 trong khi client nhận toàn thành công). `LogOnlyDecisionFlips`, `LogOnlyMatches` chỉ ứng với `enforcementMode=LOG_ONLY` theo từng policy (không thấy xuất hiện vì ca đó không có policy nào khớp). Chi tiết từng quyết định (`aws.agentcore.policy.authorization_decision`, `determining_policies`, `authorization_reason`) nằm ở **span** trong log group `aws/spans`, cần bật tracing của Gateway + CloudWatch Transaction Search (cài đặt cấp tài khoản, **không bật trong spike**). Theo tài liệu, **log ứng dụng của Gateway không ghi quyết định policy** và lời gọi bị từ chối không để lại bản ghi request/response.
- **`ENFORCE`**: HTTP 200, body `{"jsonrpc":"2.0","id":7,"error":{"code":-32002,"message":"Tool Execution Denied: Tool call not allowed due to policy enforcement [No policy applies to the request (denied by default).]"}}`. Khi bị `forbid`: `[Policy evaluation denied due to forbid_username_user_b-2am3zyh9mt]` (có tên policy; gateway tạo với `exceptionLevel=DEBUG`, **chưa thử** xem bản không DEBUG có che lý do không). Tool không tồn tại: `-32602 Unknown tool`. **Phía client `mcp` Python**: `call_tool` ném `McpError` bọc trong `ExceptionGroup` (do `anyio` TaskGroup của transport), **không** trả `CallToolResult`. Cần bắt ở lớp bọc MCP của agent và chuyển thành thông điệp tool lỗi cho LLM; chưa thử hành vi mặc định của Strands `MCPClient`.
- **Thứ tự** (thử bằng interceptor `overwrite` + `ENFORCE`): A gọi `get_jar_balances` với `user_id=<sub-B>` hoặc bỏ trống `user_id` => **cho phép**, Lambda nhận `<sub-A>`; A ghi với `user_id=<sub-B>` => cho phép với `<sub-A>`. Vậy Cedar **thấy tham số đã bị interceptor sửa**: thứ tự `JWT authorizer -> request interceptor -> Cedar -> kiểm schema -> Lambda`. (Vị trí "Cedar trước kiểm schema" suy ra từ việc thiếu `user_confirmed` ra lỗi Cedar chứ không ra `ValidationException`.) Interceptor trả `transformedGatewayResponse` thì bỏ qua cả Cedar lẫn target (theo tài liệu, và ca `deny` ở 3a).
- **Luật theo từng policy**: `UpdatePolicy(enforcementMode="LOG_ONLY"|"ACTIVE")` chạy. Policy ở `LOG_ONLY` không còn đóng góp quyết định nên nếu nó là `permit` duy nhất thì tool vẫn bị từ chối mặc định.

## 5. Xác nhận không giả mạo được (Q5)

**Thiết kế đã chạy** (`lambdas/confirm`, `lambdas/ledger`, `step5_confirm.py`):

1. LLM gọi `ledger___move_between_jars` (tham số + `user_confirmed:true` tự điền). Lambda **không có `confirm_token`** => trả `status: NEEDS_CONFIRMATION` (không ghi).
2. UI hiện khối xác nhận. Người dùng bấm nút => UI gọi **một endpoint riêng không nằm sau Gateway/LLM** (trong spike là Lambda `confirm` gọi trực tiếp bằng `lambda:Invoke`; bản thật: API Gateway HTTP API + JWT authorizer Cognito hoặc Function URL) với **access token của người dùng** + tham số hiển thị. Lambda gọi `cognito-idp:GetUser(AccessToken)` (xác minh thật, API không cần chữ ký SigV4), lấy `sub`, **tự ghim `user_id=sub`** (bỏ qua `user_id` client gửi), ký HMAC-SHA256: `token = b64url(payload) + "." + b64url(hmac)`, `payload = {sub, tool, h: sha256(canonical(user_id, from_jar, to_jar, amount_vnd)), exp: now+120s, jti}`.
3. Agent gọi lại tool với `confirm_token`. Lambda `ledger` kiểm: chữ ký, `exp`, `tool`, `sub == event.user_id` (đã được interceptor ghim), `h` khớp tham số thật, `jti` chưa dùng (**`PutItem` có `attribute_not_exists(jti)` trên DynamoDB**, TTL).

Kết quả 13 ca (đầu ra thật, Gateway `main` = interceptor `overwrite` + Cedar `ENFORCE`):

| # | Ca | Kết quả |
|---|---|---|
| 1 | LLM tự điền `user_confirmed=true`, không token | `NEEDS_CONFIRMATION` (không ghi) |
| 2 | LLM bịa token `abc.def` | `REJECTED: chữ ký không hợp lệ` |
| 3 | Token giả đúng định dạng, ký bằng khóa sai | `REJECTED: chữ ký không hợp lệ` |
| 4 | Xin cấp token với `user_id=B` bằng access token của A | server ghim `user_id` = A (token cấp cho A) |
| 5 | Token hợp lệ nhưng `amount_vnd` 300000 -> 3000000 | `REJECTED: tham số khác với tham số đã được xác nhận` |
| 6 | Token hợp lệ nhưng đổi `to_jar` | `REJECTED: tham số khác...` |
| 7 | Đúng tham số + token vừa cấp | **`MOVED`** |
| 8 | Dùng lại cùng token (replay) | `REJECTED: token đã được dùng (replay)` |
| 9 | A dùng token do B xin | `REJECTED: token cấp cho người dùng khác` |
| 10 | Không interceptor; A gửi `user_id=B` + token hợp lệ của B (token bị đánh cắp) | Cedar chặn (`-32002`), vì `user_id != principal.id` |
| 11 | Xin token bằng access token giả | `NotAuthorizedException` (Cognito `GetUser`) |
| 12 | Token hết hạn (TTL 1 s, chờ 3 s) | `REJECTED: token hết hạn` |
| 13 | Quy trình hợp lệ sau khi đặt lại TTL | `MOVED` |

**Cedar có giúp được gì thêm ở đây?** Có, nhưng ở lớp phụ:

- Giúp: ép hạn mức (9 triệu bị chặn trước khi tới Lambda), ép `user_id == principal.id` độc lập với interceptor (ca 10), ép **có mặt** `confirm_token` định dạng `*.*` (`has` + `like`), ghi nhận quyết định ở metric. Ca 10 cho thấy lớp xếp chồng: token hợp lệ của B bị lộ cũng không dùng được từ JWT của A.
- Không giúp: **không kiểm được chữ ký/hạn/tính duy nhất của token** (Cedar chỉ so sánh chuỗi/số/boolean của tham số và claim; không có phép HMAC, không có trạng thái "đã dùng"). `user_confirmed` (boolean do LLM điền) vô giá trị bảo mật: giữ nếu muốn lưới phụ, đừng coi là bằng chứng.
- Hệ quả: **kiểm token phải nằm trong Lambda tool** (hoặc interceptor, chưa thử). Cedar là lưới bảo vệ thứ hai.

## 6. Độ trễ (Q6)

Đo từ máy ở Việt Nam qua internet, `httpx.Client` giữ kết nối, tool `get_jar_balances`. "Lạnh" = ép Lambda `ledger` và `interceptor` tạo sandbox mới (đổi biến môi trường) rồi gọi ngay trên kết nối TLS mới (3 mẫu); "ấm" = 5 lần liên tiếp sau một lần làm nóng.

| Cấu hình | Lạnh (ms, 3 mẫu) | Ấm (ms, 5 lần) | Trung vị ấm |
|---|---|---|---|
| Lambda `Invoke` trực tiếp (đối chứng, boto3) | - | 123 110 129 138 152 | 129 |
| C0: Gateway trơn | 1783 646 563 | 138 183 141 143 145 | 143 |
| C1: chỉ interceptor | 1020 802 710 | 154 155 150 145 149 | 150 |
| C2: chỉ policy `ENFORCE` | 622 569 668 | 139 144 140 155 147 | 144 |
| C3: interceptor + policy | 810 913 865 | 215 210 171 158 195 | 195 |
| Đo lại thêm (12 mẫu ấm) | | C0: 84-146 (trung vị 92); C3: 157-195 (trung vị 170), lần hai 109-260 (trung vị 163) | |

Nhận xét: nhiễu mạng ±40-50 ms (C0 hôm sau trung vị 92 so với 143 lúc đầu), nên chỉ kết luận thô: **interceptor + policy cộng khoảng 50-80 ms ở trạng thái ấm** và tổng ấm dưới 200 ms; lần gọi đầu sau khi Lambda lạnh 0,55-1,8 s (gồm TLS và cold start Lambda; mẫu 1783 ms là mẫu lạnh đầu tiên của C0, có thể kèm phần khởi tạo phía Gateway, không tách được). Bộ này không đo riêng cold start của chính Gateway. Ngân sách F3 (dưới 2 giây) không bị đe dọa bởi Gateway/interceptor/Cedar; nút thắt là LLM. Metric của Gateway (`Latency`, `Duration`, `TargetExecutionTime`) có sẵn để đo phía máy chủ trong môi trường thật.

## 7. Semantic tool search (Q7)

`protocolConfiguration.mcp.searchType = "SEMANTIC"` (đặt lúc tạo, không đổi được sau đó). Gateway `sem` với 5 tool (target `ledger` 2 tool + target `planner` 3 tool):

- `tools/list` **vẫn trả đầy đủ cả 5 tool** cộng thêm một tool `x_amz_bedrock_agentcore_search` (`inputSchema: {query: string}`, bắt buộc `query`). Bật search **không** ẩn các tool khác; muốn LLM chỉ thấy tập con thì phải lọc ở phía agent (ví dụ chỉ nạp tool tìm kiếm).
- `tools/call` tool `x_amz_bedrock_agentcore_search` với `{"query": "..."}` trả danh sách tool xếp hạng (có đủ 5, thứ tự theo độ liên quan). Truy vấn tiếng Việt chạy tốt: "chuyển tiền giữa các hũ" -> `ledger___move_between_jars` đầu; "xem số dư" -> `ledger___get_jar_balances` đầu; "tại sao tôi tiêu nhiều hơn" -> `planner___explain_spending` đầu; "mục tiêu tiết kiệm" -> `planner___list_goals` đầu. Mỗi lần tìm 320-370 ms.
- Gọi tool thường qua gateway semantic vẫn chạy bình thường.

## 8. Thiết kế đề xuất cho Yofina

Nhãn: **[CM]** đã chứng minh bằng thực nghiệm trong spike; **[SĐ]** suy ra, chưa chạy.

**Danh tính xuống tool**

1. Agent chuyển **nguyên access token Cognito** của người dùng cho Gateway (`allowedClients` = app client; không dùng ID token). **[CM]**
2. **Lớp 1 (bắt buộc): request interceptor** (`REQUEST`, `passRequestHeaders:true`) decode JWT, ghi đè `params.arguments.user_id = sub` cho mọi `tools/call` và đặt thêm header `x-user-id` (target allowlist `x-user-id`). Lambda đọc `event["user_id"]`. Không bao giờ tin header/tham số không do interceptor đặt. **[CM]**
3. **Lớp 2: Cedar `context.input.user_id == principal.id`** cho mọi tool có danh tính, một policy mỗi tool, tạo target trước rồi policy rồi gắn engine. Tác dụng thực: nếu có ai gỡ/lỗi interceptor thì Cedar vẫn chặn (đã thử: chạy riêng, chặn đúng). Khi interceptor chạy, điều kiện này luôn đúng nên đóng vai bảo hiểm cấu hình, không phải kiểm tra chính. **[CM]**
4. **Khai `user_id` ở schema tool thế nào**: hai phương án đều chạy. (i) `user_id` có trong schema, `required` (LLM sẽ thấy và phải điền gì đó, bị ghi đè); hoặc (ii) **không khai `user_id` trong schema** (LLM không thấy), interceptor tiêm vào, Lambda vẫn nhận **[CM]**, nhưng khi đó chưa biết Cedar có tham chiếu được `context.input.user_id` không vì schema Cedar suy ra từ schema tool **[SĐ, chưa thử]**. Đề xuất: khai `user_id` là tham số **tùy chọn** (không `required`, mô tả "hệ thống tự điền, để trống"), interceptor luôn tiêm, và luật Cedar viết `context.input has user_id && context.input.user_id == principal.id` (mẫu `has` đã chạy với `confirm_token` **[CM]**; riêng tổ hợp này **[SĐ]**).
5. Lambda: lọc dữ liệu theo `user_id` từ `event`; coi mọi tham số khác là không tin cậy (Gateway không từ chối tham số thừa). Từ trong Lambda không phân biệt được `user_id` do interceptor đặt với `user_id` do client/LLM gửi (khi interceptor bị gỡ thì cả hai đều giả mạo được), nên phải **kiểm cấu hình bằng kiểm thử tự động (CI) rằng gateway luôn có interceptor và engine ở `ENFORCE`**.
6. Đừng dùng token exchange/OBO của Identity cho tool Lambda (không áp dụng, theo tài liệu). Job nền dài hơn tuổi thọ token vẫn theo đề xuất cũ (danh tính dịch vụ + `user_id` đã xác thực lúc khởi tạo). **[SĐ]**

**Xác nhận trước khi ghi**

1. Tool ghi bắt buộc `confirm_token`; thiếu thì trả `NEEDS_CONFIRMATION` kèm đề xuất (không ghi). **[CM]**
2. Nút "Xác nhận" của UI gọi endpoint riêng (HTTP API + JWT authorizer Cognito, cùng đội Lambda `ledger`) để lấy token: xác minh người dùng, ghim `user_id=sub`, ký HMAC trên (sub, tool, hash tham số chuẩn hóa, `exp` ≤ 2 phút, `jti`). Lambda ghi kiểm đủ năm điều kiện, `jti` đánh dấu bằng `PutItem` điều kiện (DynamoDB, TTL). **[CM]** (endpoint thật bằng HTTP API chưa dựng; spike gọi trực tiếp Lambda và xác minh token bằng `cognito-idp:GetUser`).
3. Token đi qua ngữ cảnh LLM (UI đưa token vào trạng thái/tin nhắn, agent gọi lại tool): chấp nhận được vì token gắn tham số, người dùng, hạn 2 phút và dùng một lần; LLM không bịa được. Phương án chặt hơn: UI gọi thẳng endpoint "áp dụng" với token và không để LLM chạm vào bước ghi; chưa thử, **[SĐ]**. Gợi ý cho agent hiển thị: `NEEDS_CONFIRMATION` nên trả bản tóm tắt tham số để khối `confirm` hiển thị đúng thứ sẽ được ký.
4. Cedar vẫn giữ: `user_id == principal.id`, `amount_vnd <= hạn mức`, `has confirm_token && like "*.*"`. **[CM]** Bỏ `user_confirmed` hoặc coi là gợi ý UI.
5. Secret HMAC: Secrets Manager (spike để trong biến môi trường Lambda, đã xóa); xoay khóa bằng hai khóa hợp lệ song song **[SĐ]**.

**Gateway/Policy vận hành**

- Policy engine đưa lên ở `LOG_ONLY` rồi `ENFORCE`: dựa vào metric `AllowDecisions/DenyDecisions` theo `Mode` (xem được ngay không cần cấu hình); để xem lý do từng quyết định cần bật tracing + Transaction Search (chưa thử). **[CM cho metric]**
- Mã agent phải xử lý lỗi từ chối `-32002` (protocol error) và `isError` của interceptor `deny`/ValidationException khác nhau. **[CM]**

## 9. Điều chưa thử được hoặc còn mở

- Span quyết định policy (`aws.agentcore.policy.*`) và log ứng dụng của Gateway (vended logs): cần bật Transaction Search và/hoặc resource policy của CloudWatch Logs (đổi cấu hình tài khoản) nên **không bật**. Chưa xác minh `aws/spans` thực tế.
- Gateway luôn tạo với `exceptionLevel=DEBUG`; **chưa thử** thông điệp từ chối khi không DEBUG (có thể che lý do).
- Response interceptor, streaming, elicitation MCP (`elicitation/create` qua Gateway) như một cơ chế xác nhận khác; temporal policy (`x-amzn-bedrock-agentcore-policy-session-id`), guardrail trong policy.
- Hành vi mặc định của Strands `MCPClient` khi Gateway trả `-32002`; đổi tên/alias tool phía Strands; giới hạn 64 ký tự tên tool phía Bedrock Converse (chỉ suy ra).
- Endpoint cấp token bằng HTTP API + JWT authorizer thật; DynamoDB `jti` dưới tải đồng thời (chỉ thử tuần tự); độ trễ `cognito-idp:GetUser` và hạn mức của nó dưới tải.
- Cedar tham chiếu `context.input.user_id` khi `user_id` không có trong schema tool (mục 8.4); tổ hợp `user_id` tùy chọn + `has`.
- Độ trễ chỉ đo từ một máy ở Việt Nam, không đo từ trong Region; không đo cold start của chính Gateway; mẫu nhỏ.
- Chi phí thực chưa kiểm trên Billing.

## 10. Tài nguyên đã tạo và trạng thái dọn

Chi tiết từng dòng (loại, tên/ID, lệnh xóa) ở `spikes/agentcore-gateway-identity/RESOURCES.md`. Đã tạo: 2 IAM role, 1 bảng DynamoDB, 1 Cognito user pool (+1 app client, 2 user), 3 Lambda (`ledger`, `interceptor`, `confirm`) + 3 log group, 3 Gateway (`plain`, `main`, `sem`) + 5 target thật (`ledger` x3, `planner`, `ledgerx`) và 8 target tạm để đo giới hạn tên (xóa ngay), 1 policy engine + ~6 policy (gồm các policy tạm).

**Đã xóa sạch bằng `teardown.py` và kiểm lại độc lập bằng AWS CLI**: không còn gateway, policy engine, workload identity, Lambda, log group, bảng, user pool hay role nào tiền tố `yofina-spike-gw-`. Không tài nguyên nào còn sót. Không đụng tài nguyên của spike khác (runtime `yofina_spike_rt_*`, pool `yofina-spike-rt-pool`). Không tạo access key, không đổi cấu hình tài khoản. Chi phí ước tính **dưới 0,05 USD** (vài trăm lời gọi Gateway 0,005 USD/1.000, vài trăm lượt Policy 0,000025 USD/lượt, Lambda/Cognito/DynamoDB trong Free Tier hoặc vài cent; chưa kiểm Billing).

## 11. Cần sửa trong agentcore.md

Chưa sửa file đó (spike Runtime đang sửa). Liệt kê điểm cần sửa, theo vị trí:

1. **§2 mục 7, §3.2 "Truyền danh tính xuống tool", §4 mục 2**: chuyển từ [SĐ] sang đã kiểm: interceptor ghi đè `user_id` + header `x-user-id` chạy; Cedar `context.input.user_id == principal.id` chạy; header vào Lambda ở `context.client_context.custom["bedrockAgentCorePropagatedHeaders"]` (không phải khóa riêng ở event). Ghi rõ **A gửi header allowlist thì Lambda nhận nguyên văn** (chỉ header do interceptor đặt mới đáng tin).
2. **§3.2 đề xuất bước 3 ("Chưa rõ thứ tự interceptor và policy")** và **§5 mục 1, 2, 3**: đã rõ: `JWT authorizer -> interceptor -> Cedar (thấy tham số đã sửa) -> kiểm schema -> Lambda`. Interceptor chỉ chạy sau khi JWT hợp lệ. Độ trễ thêm 50-80 ms ấm (mục 6 ở trên).
3. **§3.2 "Với Cognito" / §2 mục 6**: xác nhận access token không có `aud`; **ID token vào Gateway ra 403 `insufficient_scope`**; token hỏng hoặc bị sửa cũng ra **403** (không phải 401).
4. **§3.3 "Đặt tên"**: sửa "tên tool tối đa 128 ký tự": Gateway không cưỡng chế (129 ký tự và `.` vẫn tạo được). Tên target: 1-100 nhóm `[chữ-số][-]?` (100 chữ OK, 101 lỗi; gạch dưới/dấu chấm lỗi). Tên gateway tối đa 48 nhóm. Giới hạn 64 ký tự của Converse là điều cần để ý ([SĐ]).
5. **§3.3 "Schema tool Lambda"**: bổ sung: Gateway **kiểm `required` và kiểu** (trả `isError` với `ValidationException`) nhưng **không từ chối tham số thừa**; interceptor chạy trước kiểm schema nên tiêm tham số `required` được.
6. **§3.4**: bổ sung cú pháp đã chạy: `principal.id`; claim là tag, kể cả `sub` (`principal.hasTag("sub")` đúng); `has` + `like` cho tham số string tùy chọn; permit vô điều kiện bị từ chối (`Overly Permissive`) khi `FAIL_ON_ANY_FINDINGS`; tham số `required` thiếu thì policy "evaluation error" và bị từ chối; `UpdatePolicy(enforcementMode=...)` chạy; thông điệp từ chối nêu id policy khi `exceptionLevel=DEBUG`.
7. **§3.4 "Chế độ chỉ ghi log"**: bổ sung: client luôn thấy thành công; quyết định xem ở metric `AWS/Bedrock-AgentCore` (`AllowDecisions`, `DenyDecisions`, `NoDeterminingPolicies`...) đã thấy sẵn không cần bật gì; `LogOnlyDecisionFlips` chỉ xuất hiện khi dùng `enforcementMode=LOG_ONLY` ở cấp policy; log ứng dụng Gateway **không** ghi quyết định policy; chi tiết ở span cần Transaction Search.
8. **§3.4 / §3.3**: thêm **dạng phản hồi từ chối**: HTTP 200, JSON-RPC `error.code=-32002`, `message="Tool Execution Denied: Tool call not allowed due to policy enforcement [...]"`; client `mcp` Python ném ngoại lệ (`ExceptionGroup`), không trả `CallToolResult`. Tool bị từ chối vĩnh viễn thì ẩn khỏi `tools/list`.
9. **§3.3 "Tìm tool theo ngữ nghĩa"**: bổ sung: `tools/list` **vẫn trả đủ mọi tool** cộng `x_amz_bedrock_agentcore_search`; tìm kiếm tiếng Việt chạy tốt (320-370 ms); `searchType` đặt lúc tạo, không đổi được.
10. **§2 mục 10, §4 mục 3 (cờ xác nhận)**: chuyển sang đã chứng minh mẫu HMAC (mục 5 ở trên); ghi rằng Cedar chỉ làm lưới phụ (hạn mức, khớp user, có mặt token), không kiểm được chữ ký; `user_confirmed` do LLM điền vô giá trị bảo mật. Ghi mẫu tối thiểu: `jti` dùng một lần bằng DynamoDB điều kiện, TTL 120 s, secret ở Secrets Manager.
11. **§3.2 cuối, "Luồng on-behalf-of"**: bổ sung bảng outbound auth: **Lambda target chỉ có gateway service role** (không token exchange, không passthrough); passthrough/exchange chỉ cho target Runtime HTTP/MCP server/OpenAPI.
12. **§3.4 "Quyền IAM cho role của gateway"**: xác nhận đủ: `lambda:InvokeFunction` + `GetPolicyEngine`, `AuthorizeAction`, `PartiallyAuthorizeActions`; trust policy có `aws:SourceAccount` và `aws:SourceArn` (`gateway/*`) chạy được.
13. **§3.3 "Lỗi hay gặp"**: thêm: policy gắn engine phải tạo **sau** target (resource là ARN gateway; schema Cedar sinh từ tool); policy lỗi là `CREATE_FAILED` bất đồng bộ (đọc `statusReasons`); `UpdateGateway` bỏ trường là gỡ trường (engine/interceptor).
14. **§5**: đóng các mục 1, 2, 3 (Cedar `principal.id`, thứ tự, độ trễ); mục 13 vẫn mở.
