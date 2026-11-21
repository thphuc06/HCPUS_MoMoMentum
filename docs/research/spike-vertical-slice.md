# Lát dọc phase 1: kết quả chạy thật phía backend (Gateway, Cedar, Runtime, lưu lượt)

Ngày chạy: **2026-11-21 và 2026-11-22**, Region `ap-southeast-1`, tài khoản AWS thật (phiên root của CLI), Bedrock thật (Nova 2 Lite làm router và model viết câu), Aurora thật. Mã thử: `spikes/vertical-slice/` (số đo, thử Strands `MCPClient`, thử Cedar, thử Runtime tạm), `tests/integration/test_gateway_*.py` và `test_agent_runtime.py`. Mọi giá trị phụ thuộc tài khoản đã che (`<account>`). Quy ước: **[Chạy]** là điều đã chạy và quan sát; **[Suy luận]** là suy ra, chưa kiểm trực tiếp.

Phạm vi: nửa backend của bảng "Phép thử Chưa thử" ở [phase 1](../plan/phases/phase-1-nen-va-lat-doc.md). Frontend thật nối Runtime thật, CORS từ trình duyệt thật và Safari iPhone thuộc bước sau (không thử ở đây).

## 0. Kết luận ngắn

1. **Đường chạy thật hoạt động đầu-cuối ở backend**: access token Cognito → Runtime (JWT) → agent Strands → Gateway (JWT + interceptor + Cedar `ENFORCE`) → Lambda `ledger` → Aurora, và khối UI ra qua SSE AG-UI. 19 test Gateway và 6 test Runtime (cùng 39 test ledger có sẵn) đều xanh ([mục 8](#8-test-tích-hợp)).
2. **Interceptor ghi đè `user_id`, Cedar là lớp phụ chạy được với `user_id` tùy chọn** (đề xuất §8.4 của spike Gateway): policy có `context.input has user_id && context.input.user_id == principal.id` qua kiểm kiểu; khi không có interceptor, `user_id` của người khác, vắng hoặc rỗng đều bị `-32002`.
3. **Strands `MCPClient` với Gateway thật**: tên tool `ledger___…` đúng, header `Authorization` đi nguyên vẹn, Cedar từ chối ra `MCPError -32002` (bọc trong `ExceptionGroup`) và `MCPClient.call_tool_async` nuốt thành chuỗi nên lớp `_GatewayMCPClient` giữ ngoại lệ gốc để phân loại (đã chạy với Gateway thật); người dùng thấy khối `notice` "Không có quyền thực hiện".
4. **Interrupt/resume AG-UI qua Runtime thật chạy được** với session manager bền (`S3SessionManager`), kể cả khi microVM bị dừng giữa chừng; không có session manager thì resume sau khi microVM đổi bị `UNKNOWN_INTERRUPT_ID`. Luồng xác nhận của Yofina (ADR-0002) **không dùng** nó và không phụ thuộc vào nó.
5. **Token hết hạn giữa luồng SSE**: luồng đang mở **không bị cắt** (token chỉ kiểm lúc mở request); nhưng lời gọi Gateway bằng token đã hết hạn ra `403 -32002 insufficient_scope` (gây hiểu nhầm là Cedar từ chối), và Runtime từ chối request mới nếu token đã hết hạn hoặc sắp hết hạn trong vòng một phút ("Ineffectual token, will expire within the next minute"). Frontend phải làm mới token sớm hơn 1 phút.
6. **Số đo** (từ máy ở Việt Nam): event đầu của lượt đầu phiên lạnh trung vị **2,04 s** (1,72 đến 3,18; 5 phiên), lượt hai cùng phiên **0,34 s**; trọn lượt 5,2 đến 6,4 s (lượt đầu) và khoảng 3,0 s (lượt hai); Gateway ấm có interceptor + Cedar trung vị **174 ms** so với **140 ms** gọi thẳng Lambda (thêm khoảng 35 ms).
7. Bẫy mới (mục 9): Cedar không nhận `!(has) || truy cập` (dùng `if has then … else true`), CloudFormation tạo Runtime song song khiến rollback lỗi, `StopRuntimeSession` bằng SigV4 bị từ chối khi Runtime dùng JWT (dùng Bearer thì được), `exceptionLevel` không DEBUG (xem mục 4).

## 1. Cách dựng (CDK, không có gì ngoài CDK ngoài một tham số SSM)

Stack `YofinaAgent` ([infra-cdk/lib/agent-stack.ts](../../infra-cdk/lib/agent-stack.ts)), L1 của `aws-cdk-lib` 2.278 (`CfnGateway`, `CfnGatewayTarget`, `CfnPolicyEngine`, `CfnPolicy`, `CfnRuntime`; đã có L2 trong `aws-cdk-lib/aws-bedrockagentcore` nhưng L1 cho đủ thuộc tính: interceptor, `policyEngineConfiguration`, `requestHeaderConfiguration`, `platformVersion`). Gateway, target `ledger` (schema đọc từ `contracts/tools/ledger.json`), 4 policy (đọc từ `gateway/policies/*.cedar`, synth báo lỗi nếu một tool thiếu file), Lambda interceptor (`gateway/interceptor/`), Runtime V2 CodeZip và hai vai IAM đều nằm trong CDK. Ngoài CDK duy nhất: tham số SSM `/yofina/agent/zip-key` do `scripts/agent_deploy.py` ghi (đầu vào của CDK: khóa S3 của zip mới để CloudFormation thấy `prefix` đổi và tạo version Runtime mới).

**Thời gian**: tạo `YofinaAgent` lần đầu ~5 phút (Runtime V2 ~5 phút, phần còn lại ~1 phút); đổi chỉ Gateway/Cedar ~40 giây; cập nhật Runtime ~5 phút.

**Đưa lên `LOG_ONLY` rồi `ENFORCE`** [Chạy]. Deploy với `-c policyMode=LOG_ONLY`; gọi `get_jar_balances` (hợp lệ), `move_between_jars` 60 triệu (vượt hạn mức) và `move_between_jars` với `confirm_token` không có dấu chấm. Client thấy cả ba chạy tới Lambda (vượt hạn mức nhận `AMOUNT_LIMIT_EXCEEDED` từ **Lambda**, token rác nhận `TOKEN_INVALID` từ Lambda: lớp Lambda vẫn chặn). Metric `AWS/Bedrock-AgentCore` (dimension `Mode=LOG_ONLY`, `OperationName=AuthorizeAction`) trong 30 phút: `AllowDecisions` = 2 (hai lần `get_jar_balances`), `DenyDecisions` = 2 (đúng hai ca Cedar lẽ ra từ chối). Rồi deploy lại không có context (mặc định `ENFORCE`): cả 19 test Gateway xanh, gồm hai ca `-32002`.

## 2. Cedar `context.input.user_id` khi `user_id` là tham số tùy chọn

**Cách thử** [Chạy] (`probe_cedar_optional.py`): dựng tạm Gateway **không interceptor** + policy engine + role riêng (đã xóa), cùng target và schema thật (`user_id` tùy chọn, không `required`), policy `get_jar_balances.cedar` thật ở `ENFORCE`, token của `minh`.

| Ca | Kết quả |
|---|---|
| Policy với `has user_id && user_id == principal.id`, `validationMode FAIL_ON_ANY_FINDINGS` | `ACTIVE` (qua kiểm kiểu) |
| `user_id` = `sub` của chính mình | cho phép, `status OK` |
| `user_id` = `sub` của người khác | **từ chối** `-32002` |
| bỏ `user_id` | **từ chối** `-32002` (`has` ra false) |
| `user_id` rỗng | **từ chối** `-32002` |

Kết luận: đề xuất của spike Gateway §8.4 chạy đúng; không cần đổi `user_id` thành `required`. Hệ quả: nếu interceptor bị gỡ thì đường chạy bình thường (LLM không điền `user_id`) bị từ chối thay vì rò dữ liệu. Thông điệp từ chối của các ca trên đều là `[No policy applies to the request (denied by default).]` (permit không khớp nên không có policy nào "quyết định").

## 3. Strands `MCPClient` với Gateway thật

**Cách thử** [Chạy] (`probe_strands_mcp.py`): `yofina_agent.tools.GatewayTools` (bọc `strands.tools.mcp.MCPClient`, header `Authorization: Bearer <access token>` của `minh`), Gateway `ENFORCE` thật, không gọi model. Kết quả:

| Ca | `ToolKind` | Mã | Người dùng thấy |
|---|---|---|---|
| `list_tools_sync` | | | `ledger___get_jar_balances`, `ledger___move_between_jars`, `ledger___query_transactions`, `ledger___save_turn` (đúng tên, đủ 4) |
| `get_jar_balances` không `user_id` | `ok` | | khối số dư |
| `move_between_jars` không token | `needs_confirmation` | | khối `confirm` |
| vượt hạn mức 60 triệu (Cedar) | `denied` | `FORBIDDEN` | "Bạn không có quyền thực hiện thao tác này." (log: `MCP -32002 … denied by default`) |
| `confirm_token` không có dấu chấm (Cedar) | `denied` | `FORBIDDEN` | như trên |
| hũ không tồn tại (tool trả `ERROR`) | `tool_error` | `JAR_NOT_FOUND` | "Không tìm thấy hũ bạn chọn." |
| `amount_vnd` sai kiểu (chuỗi) | `denied` | `FORBIDDEN` | như trên; **Cedar chạy trước kiểm schema** nên lỗi là `-32002 … policy evaluation errors: Value does not match expected type`, không phải `ValidationException` |
| tool không tồn tại | `tool_error` | `INTERNAL_ERROR` | thông điệp chung (`MCP -32602 Unknown tool`) |
| token rác lúc mở phiên MCP | (trước) `unavailable` `DATABASE_UNAVAILABLE`; (sau sửa) `tool_error` `UNAUTHENTICATED` | | lúc đầu hiện "Dịch vụ dữ liệu tạm thời không phản hồi" (sai nhãn); đã sửa thành "Phiên đăng nhập đã hết hạn" |

Quan sát: (1) `MCPClient` không ném ra ngoài mà trả kết quả lỗi chỉ có chuỗi, nên `_handle_tool_execution_error` được ghi đè để giữ ngoại lệ gốc và đọc `MCPError.code` (mã mới: `-32002` Cedar, `-32001` "Invalid Bearer token" lúc mở phiên, `-32602` tool lạ). (2) Token sai lúc **mở phiên** (initialize) nổi lên là `MCPClientInitializationError` với nguyên nhân `MCPError -32001` nằm sâu trong `ExceptionGroup`; phải duyệt chuỗi `__cause__`/`exceptions` (đã có `_flatten`). (3) Token **hết hạn** (không phải sai) ra `-32002 insufficient_scope` (mục 6): đã thêm nhánh nhận diện theo chuỗi `insufficient_scope` để không nhầm với Cedar. Có test đơn vị cho từng nhánh (`tests/unit/agent/test_tools.py`).

## 4. Thông điệp từ chối khi Gateway không bật `DEBUG`

**Cách thử** [Chạy]: deploy `YofinaAgent` với `exceptionLevel` mặc định (bỏ `DEBUG`; `get_gateway` trả `exceptionLevel: null`), chạy lại `probe_strands_mcp.py` với Gateway `ENFORCE`.

**Kết quả**: thông điệp từ chối **giống hệt** bản `DEBUG` ở mọi ca của mục 3: `Tool Execution Denied: Tool call not allowed due to policy enforcement [No policy applies to the request (denied by default).]` (vượt hạn mức, `confirm_token` rác), `[... policy evaluation errors: Value does not match expected type]` (sai kiểu), `-32602 Unknown tool`. Lý do: toàn bộ luật của Yofina là `permit`, nên không policy nào "quyết định" từ chối và không có tên policy nào để lộ; mức `DEBUG` chỉ thêm tên policy khi một `forbid` quyết định (spike Gateway §4). Kết luận: **dùng mức mặc định (không DEBUG)** cho bản deploy, không mất thông tin nào mà agent dùng (agent chỉ phân loại theo mã `-32002` và chuỗi `insufficient_scope`, không hiển thị thông điệp Gateway). Chưa thử xem `DEBUG` thêm gì cho lỗi Lambda target.

## 5. Interrupt/resume AG-UI qua Runtime với session manager bền

**Cách thử** [Chạy] (`probe_runtime.py up/interrupt/down`, một nhánh thử tách khỏi đường sản phẩm, tổng thời gian khoảng 40 phút): dựng tạm Runtime `yofina_probe` (platform V1 để tạo nhanh, cùng authorizer JWT, `allowedClients` có thêm client thử), agent Strands + `ag-ui-strands` 1.0.4 với tool `move_plain` giả gắn `ToolBehavior(interrupt_on_call=True)` (cơ chế (B) của spike Strands §2.7), model Nova 2 Lite; hai biến thể: `S3SessionManager` (bucket artifact, tiền tố `tmp/probe-interrupt/`) và không session manager. Lượt 1 "chuyển 50 nghìn từ giai_tri sang an_uong" → `RUN_FINISHED` với `outcome.type = "interrupt"`; lượt 2 `resume: [{interruptId, status: "resolved", payload: {approved: true}}]`, cùng `threadId` và session id. Với ca "microVM bị dừng", gọi `StopRuntimeSession` bằng **Bearer** (SigV4 bị `AccessDeniedException: Authorization method mismatch` vì Runtime dùng JWT) rồi resume cùng session id (microVM mới). Dọn: đã xóa Runtime, role, app client, đối tượng S3, log group.

| Ca | Resume |
|---|---|
| A. S3 session manager, cùng microVM | **chạy**: `TOOL_CALL_RESULT {"status":"done",…}` rồi câu trả lời, `RUN_FINISHED` thành công |
| B. S3 session manager, microVM bị dừng (`StopRuntimeSession` HTTP 200) rồi resume | **chạy** (trạng thái interrupt đọc lại từ S3) |
| C. không session manager, cùng microVM | **chạy** (trạng thái ở RAM của tiến trình) |
| D. không session manager, microVM bị dừng rồi resume | **lỗi**: `RUN_ERROR UNKNOWN_INTERRUPT_ID` "No pending interrupts for this thread." |

Lượt 1 mất 4,8 đến 6,7 s (model chọn tool); `interrupt` có `message`, `toolCallId`, `responseSchema` và `metadata.tool_input` đủ để dựng khối xác nhận.

**Kết luận**: interrupt/resume qua Runtime **dùng được** nếu có session manager bền (S3; `AgentCoreMemorySessionManager` chưa thử). Yofina **không dùng** vì ADR-0002: xác nhận bằng token một lần đi qua REST, LLM không nằm trên đường ghi, không phụ thuộc resume, không tốn lượt model và quota 10 request/phút. Phương án này chỉ còn là đường lùi nếu sau này cần "agent hỏi lại người dùng giữa chừng một tool nhiều bước" (phase 3 trở đi).

## 6. Token hết hạn giữa luồng SSE

**Cách thử** [Chạy] (`probe_runtime.py expiry`): tạo tạm app client `yofina-probe` (access token **300 giây**, tối thiểu của Cognito; đã xóa), thêm tạm vào `allowedClients` của Runtime thử và của Gateway thật (đã khôi phục: `allowedClients` có đúng một client, đã kiểm lại), đăng nhập `minh` bằng `USER_PASSWORD_AUTH`, mở một luồng SSE 330 giây (mẩu chữ mỗi 30 giây, kèm số giây còn lại của JWT), cuối luồng agent thử gọi Gateway bằng đúng token đã nhận, rồi gửi một request mới cùng token.

| Quan sát | Kết quả |
|---|---|
| Luồng đã mở khi token còn hợp lệ | **không bị cắt**: HTTP 200, đủ 11 mẩu, `RUN_FINISHED` ở 334 giây, kể cả sau khi token hết hạn (còn -35 s ở cuối) |
| Cuối luồng, agent gọi Gateway bằng token đã hết hạn | **HTTP 403**, JSON-RPC `-32002`, `insufficient_scope - The request requires higher privileges than provided by the access token.` (không phải 401, và dễ nhầm với Cedar từ chối) |
| Request MỚI tới Runtime với token đã hết hạn | HTTP 401, `RUN_ERROR UNAUTHORIZED`: "Ineffectual token, will expire within the next minute" |

Hệ quả: (1) Runtime từ chối token "sẽ hết hạn trong vòng một phút" (thông điệp quan sát được với token đã hết hạn; ngưỡng đúng 60 giây **[Suy luận]** từ chữ của thông điệp, chưa đo với token còn 30 giây), nên frontend phải làm mới access token khi còn dưới ~2 phút, trước khi gửi lượt mới; đã có thông điệp rõ ràng ở `RUN_ERROR`. (2) Một lượt dài hơn thời gian sống còn lại của token vẫn chạy tiếp ở Runtime, nhưng tool call tới Gateway sau lúc hết hạn thất bại: agent nhận diện `insufficient_scope` và `-32001` thành khối `notice` "Cần đăng nhập lại" (không phải "không có quyền"). Lượt tối đa 60 giây (`run_timeout_seconds`) nên chỉ gặp nếu token còn 1 đến 2 phút lúc bắt đầu. (3) Với app client thật `yofina-web` (60 phút) không đổi cấu hình; phép thử dùng client riêng nên không đụng.

## 7. Số đo

Đo từ một máy ở Việt Nam qua internet tới Singapore; mẫu nhỏ (5 phiên), dùng làm bậc độ lớn. JSON thô do script ghi ở `spikes/vertical-slice/out/` (bị `.gitignore`; chạy lại script để có).

**Runtime thật** (platform V2, 5 phiên, mỗi phiên hai lượt; lượt 1 "số dư các hũ của mình" = router + `get_jar_balances` + viết câu + lưu; lượt 2 "cho mình xem 5 giao dịch gần nhất" = router + `get_jar_balances` + `query_transactions` + viết câu + lưu):

| Chỉ số | Lượt 1 (phiên lạnh) | Lượt 2 (cùng phiên) |
|---|---|---|
| Thời gian tới event đầu (`RUN_STARTED`), giây | trung vị **2,04** (1,72; 1,92; 2,04; 2,05; 3,18) | trung vị **0,34** (0,27 đến 0,37) |
| Trọn lượt, giây | trung vị **5,75** (5,23 đến 6,44) | trung vị **3,00** (2,95 đến 3,16) |
| Từ mẩu nội dung cuối tới `RUN_FINISHED` (chủ yếu là lưu lượt), giây | trung vị 0,33 (0,32 đến 0,35) | trung vị 0,32 (0,30 đến 0,38) |

Phiên lạnh không đạt mục tiêu "ký tự đầu dưới 1,5 giây" (như spike Runtime §4); lượt hai đạt. Lưu lượt qua Gateway thêm khoảng 0,3 giây trước `RUN_FINISHED`. Router + viết câu dùng 2 lượt Nova mỗi lượt.

**Gateway ấm** (một phiên MCP, `get_jar_balances`, 15 lần; Gateway có interceptor + Cedar `ENFORCE`):

| Đường | Trung vị (ms) | Khoảng (ms) |
|---|---|---|
| Gateway: `tools/call get_jar_balances` | **174** | 153 đến 526 (một mẫu 526) |
| Gateway: `tools/call move_between_jars` không token | 172 | 162 đến 185 |
| Gateway: `tools/list` | 138 | 137 đến 138 |
| `initialize` phiên MCP | 214 | |
| Đối chứng: `lambda:Invoke` trực tiếp cùng sự kiện | 140 | 126 đến 190 |

Gateway (JWT + interceptor + Cedar) thêm khoảng **35 ms** ở trạng thái ấm, thấp hơn 50 đến 80 ms của spike Gateway (khác máy/mạng, nhiễu ±40 ms).

## 8. Test tích hợp

`uv run pytest tests/integration -m integration` (token thật; Runtime và Gateway thật):

Kết quả lần chạy cuối (22/11, sau khi deploy bản agent cuối): **64 passed trong 125 giây** (39 test ledger REST/Lambda/RLS của luồng B, 19 test Gateway (7 cấu hình + 12 danh tính), 6 test Runtime).

| File | Ca đã chạy thật | Kết quả |
|---|---|---|
| `test_gateway_config.py` (7) | Gateway `READY`; JWT authorizer chỉ nhận client `yofina-web`; đúng 1 interceptor `REQUEST` với `passRequestHeaders` trỏ Lambda `yofina-gw-interceptor`; policy engine `ENFORCE` và `ACTIVE`; mỗi tool một policy `ACTIVE` chứa `user_id == principal.id`; target `ledger` `READY` với schema khớp `contracts/tools/ledger.json`; cấu hình Runtime (AGUI, V2, `PYTHON_3_13`, `allowedClients`, header allowlist, env) | xanh |
| `test_gateway_identity.py` (12) | `tools/list` đúng 4 tên `ledger___*`; `minh` đọc 7 hũ khớp `GET /jars`; `lan` gửi `user_id` của `minh` vẫn chỉ thấy dữ liệu `lan` (số dư và giao dịch); bỏ `user_id` hoặc để rỗng vẫn chạy; ID token bị 401/403; không token 401; token đúng payload sai chữ ký bị từ chối; `move_between_jars` không token trả `NEEDS_CONFIRMATION` và DB không đổi (kể cả khi `lan` gửi `user_id` của `minh`); token bịa `TOKEN_INVALID` và DB không đổi; token không có dấu chấm và vượt hạn mức 60 triệu bị Cedar `-32002`, DB không đổi; token thật từ REST đi qua Gateway ghi đúng một lần, dùng lại `TOKEN_REUSED`; `save_turn` qua Gateway với `user_id` của người khác chỉ lưu cho người gọi, REST đọc lại đúng khối, `minh` không thấy, khối chứa `confirm_token` bị từ chối | xanh |
| `test_agent_runtime.py` (6) | "số dư các hũ của mình": `ACTIVITY_SNAPSHOT` `jar_summary` 7 hũ khớp `GET /jars`, có văn bản do agent sinh, `RUN_FINISHED` không `RUN_ERROR`, khối khớp JSON Schema, và `GET /conversations/{sid}` trả đúng một lượt với `user_text`, `assistant_text` và khối **trùng từng byte** với thứ đã phát; "chuyển 100 nghìn từ Giải trí sang Ăn uống": khối `confirm` đúng `from_jar/to_jar/amount_vnd`, DB không đổi, rồi `POST /confirmations` + `POST /actions` với đúng `tool` và `params` của khối ra `receipt` hợp lệ và số dư hai hũ đổi đúng 100.000; "nên mua cổ phiếu nào": `notice` `out_of_scope`, lượt được lưu; `lan` không đọc được hội thoại của `minh` qua REST (200, `turns` rỗng; danh sách rỗng) và bị 403 khi dùng session id của `minh` ở Runtime; không token 401, token rác 401/403; trần model về 0 qua SSM (`/yofina/llm/daily_cap_small` và `daily_cap_planner`, rồi **khôi phục**: nhánh `/yofina/llm` rỗng trở lại) vẫn ra khối `jar_summary` (số khớp DB) + `notice` `degraded` mã `MODEL_BUDGET_EXCEEDED`, `model_calls = 0`, lượt suy giảm cũng được lưu | xanh |

Số lượt gọi model của bước ghép: khoảng 80 (mỗi lượt chat thật 2 lượt Nova: router và viết câu; gồm các lần chạy lại, 10 lượt đo và 8 lượt thử interrupt). Không chạm quota; router và model viết câu dùng Nova nên quota 10 request/phút của Claude 4.x không bị đụng.

## 9. Bẫy và phát hiện khác

1. **Cedar**: `(!(context.input has confirm_token) || context.input.confirm_token like "*.*")` bị bộ kiểm kiểu từ chối (`unable to guarantee safety of access to optional attribute`) và làm `CREATE_FAILED`; dùng `(if context.input has confirm_token then context.input.confirm_token like "*.*" else true)`.
2. **CloudFormation**: khi một policy lỗi trong lúc `AWS::BedrockAgentCore::Runtime` đang `CREATING`, rollback không xóa được Runtime (409 "being modified by another operation") và stack vào `ROLLBACK_FAILED`; chờ Runtime `READY` rồi `aws cloudformation delete-stack` lại. Sửa Cedar bằng `cdk deploy -c policyMode=LOG_ONLY` trước khi tạo cả stack sẽ tránh được (có thể thử policy trước trên stack nhỏ).
3. **`StopRuntimeSession`** bằng SigV4 bị từ chối khi Runtime dùng JWT; gọi `POST /runtimes/<ARN>/stopruntimesession?qualifier=DEFAULT` với `Authorization: Bearer` và header session id thì HTTP 200.
4. **Lỗi giao thức khác**: token hết hạn ra `403 -32002 insufficient_scope`; token sai/rác lúc mở phiên MCP ra `-32001 Invalid Bearer token`; tool lạ `-32602`; Cedar `-32002 Tool Execution Denied`. Chỉ phân biệt được bằng nội dung thông điệp.
5. **`mcp` 2.x**: `CallToolResult.is_error` (không còn `isError`); `streamable_http_client(url, http_client=httpx2.AsyncClient(headers=…))` thay `streamablehttp_client(url, headers=…)`.
6. **Gateway tên tool**: bốn tool tạo target được; `tools/list` không có `x_amz_bedrock_agentcore_search` (không bật semantic search).
7. **Rò thông tin**: hội thoại không thuộc người gọi và hội thoại không tồn tại đều trả 200 với `turns` rỗng (RLS); Runtime V2 ghim session theo `sub`: `lan` dùng session id của `minh` bị 403.

## 10. CORS từ domain Amplify (curl)

**Cách thử** [Chạy] (`curl`, không phải trình duyệt): `Origin` = URL Amplify thật (đọc từ SSM `/yofina/frontend/amplify-url`), URL Runtime thật.

- Preflight `OPTIONS` với `Access-Control-Request-Method: POST` và `Access-Control-Request-Headers: authorization,content-type,accept,traceparent,x-amzn-bedrock-agentcore-runtime-session-id` (các header frontend gửi): **HTTP 200**, `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Headers` phản chiếu đúng danh sách đã hỏi, `Access-Control-Allow-Methods: POST`, `Access-Control-Max-Age: 172800`, `Access-Control-Expose-Headers: smithy-protocol,baggage,WWW-Authenticate,Date,Mcp-Session-Id,X-Amzn-Trace-Id,X-Amzn-Bedrock-AgentCore-Runtime-Session-Id,Mcp-Protocol-Version,tracestate,x-amzn-ErrorMessage,traceparent,x-amzn-RequestId,x-amzn-ErrorType`. Không cần `Authorization`.
- `POST` không token với cùng `Origin`: **401** vẫn mang `Access-Control-Allow-Origin: *` và `Access-Control-Expose-Headers` (nên JS đọc được lỗi), thân `RUN_ERROR UNAUTHORIZED "Missing Authentication Token"`, header `WWW-Authenticate`, `x-amzn-ErrorType: MissingAuthenticationTokenException`.
- Origin `http://localhost:5173`: preflight cũng 200 với `*`.

Giống hệt kết quả với `localhost` ở spike Runtime §3: CORS do dịch vụ AgentCore xử lý, không phụ thuộc Origin. **Chưa thử từ trình duyệt thật trên domain Amplify** (bước frontend); `credentials: 'include'` vẫn bị chặn vì `*`, frontend không dùng. Tiêu chí "CORS từ domain Amplify" chỉ đóng khi bản đã host gọi chat thành công; phương án lùi (Lambda Function URL làm proxy) chưa cần.

## 11. Chưa thử / chưa chắc

- Frontend thật nối Runtime thật, CORS từ **trình duyệt** thật (curl chỉ cho thấy header), Safari iPhone: bước sau.
- `AgentCoreMemorySessionManager` cho interrupt/resume; interrupt/resume với `ag-ui-strands` qua đường sản phẩm (agent thật dùng "Cách B", không dùng `StrandsAgent`).
- Span/quyết định chi tiết của Cedar ở `aws/spans` (cần CloudWatch Transaction Search, chưa bật); số đo từ trong Region; tải đồng thời; chi phí thực.
- Phiên Runtime hết hạn nhàn rỗi và `idleRuntimeSessionTimeout`; hành vi khi hai lượt song song cùng session (V2 trả 409 `SESSION_BUSY`, đã biết từ spike Runtime, chưa thử lại trên agent thật).
- Receipt (`POST /actions`) không được lưu vào hội thoại; khối `confirm` phát lại không biết đã bấm hay chưa.
