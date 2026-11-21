# Spike: Strands Agents + AG-UI chạy local (kết quả chạy thật)

Ngày chạy: 2026-11-21. Chạy local trên Windows 11, Python 3.12.13 (uv). Code và luồng SSE nguyên bản nằm ở `c:\moMo\spikes\strands-agui-local\` (xem `README.md` ở đó để chạy lại). Không tạo, sửa, xóa tài nguyên AWS nào; chỉ gọi model Bedrock (khoảng 50 request Haiku, chi phí vài cent).

Quy ước: **[Chạy]** = đã chạy và thấy kết quả; **[Đọc mã]** = đọc mã nguồn trong thư viện đã cài, chưa chạy; **[Suy luận]** = suy ra, chưa thử.

## 1. Môi trường thực cài được

| Gói | Phiên bản cài | Ghi chú |
|---|---|---|
| `strands-agents` | **1.65.0** | khớp `strands-agui.md` |
| `ag-ui-strands` | **1.0.4** | khớp |
| `ag-ui-protocol` | **1.0.0** | khớp; `protocolVersion` trên dây là `"1.0"` |
| `mcp` | **2.3.0** | kéo theo `mcp-types 2.3.0`, `httpx2`. **API khác 1.x** (mục 9) |
| `fastapi` / `starlette` / `uvicorn` | 0.165.0 / 1.10.0 / 0.54.0 | |
| `pydantic` / `boto3` / `httpx` | 2.14.4 / 1.44.9 / 0.28.1 | |
| Thêm bắt buộc trên máy này | `botocore[crt]` (`awscrt 0.38.0`) | credential qua `aws login` cần gói này, thiếu thì `MissingDependencyException` |

Danh sách ghim đầy đủ: `spikes/strands-agui-local/requirements.lock.txt` (55 gói).

Model: `global.anthropic.claude-haiku-4-5-20251001-v1:0` ở `ap-southeast-1` chạy được ngay (inference profile `global.*` có ở cả `ap-southeast-1` và `us-east-1`; `us.*` chỉ thấy ở `us-east-1`). `global.anthropic.claude-sonnet-4-6` có trong danh sách profile `ACTIVE` nhưng **không gọi thử** (chỉ dùng Haiku). Không gặp throttling; `boto_client_config` đặt `retries={"max_attempts": 8, "mode": "adaptive"}`. Một lần chạy `ui_stream` mất 9,8 giây thay vì khoảng 2 giây (có thể là một lần retry của throttling, không xác nhận).

## 2. Từng câu hỏi

### 2.1 Agent cơ bản + tool + `limits` [Chạy] (`s1_basic_tool.py`)

- `@tool get_jar_balances()` trả dict hũ giả; agent tiếng Việt trả: "Hũ ăn uống của bạn còn **1.250.000 VND**..." Hai vòng (tool, trả lời), `stop_reason == "end_turn"`, 1.672 token.
- Chữ ký `Agent.__call__` có đúng `limits: Limits | None`, `structured_output_model`, `cancel_signal`, `invocation_state`.
- Hành vi chạm giới hạn: **không ném lỗi**, trả `AgentResult` với `stop_reason`:

| Thử | Kết quả |
|---|---|
| `limits={"turns": 1}` | `stop_reason == "limit_turns"`; tool đã chạy một lần; `str(result) == ""`; tin nhắn cuối là `toolResult` (role `user`), tức **không có văn bản trả lời** |
| `limits={"total_tokens": 50}` | `limit_total_tokens`, tool đã chạy, `str(result) == ""` (sau vòng đầu đã 744 token) |
| `limits={"output_tokens": 5}` | `limit_output_tokens`, như trên |
| `limits={"max_turns": 1}` (khóa sai) | `TypeError: limits keys ['max_turns'] are not recognized limits, expected one of 'turns', 'output_tokens', 'total_tokens', 'structured_output_attempts'` |

Kết luận: tên khóa đúng như tài liệu; việc kiểm tra xảy ra **sau** vòng đầu, nên dùng `stop_reason` để rẽ sang thẻ số tất định, và đừng đọc `str(result)` khi stop reason là `limit_*` (rỗng).

### 2.2 Structured output [Chạy] (`s2_structured.py`, `s2b_structured_errors.py`, `s2c_unbounded.py`)

- API đúng tên: `agent(msg, structured_output_model=Model)` (hoặc `await agent.invoke_async(...)`), đọc `result.structured_output` (instance Pydantic). Chạy với `IntentResult` (`Literal`, `ge=0`, `Field(ge=0, le=1)` cho `float`, trường optional) và `ScenarioSpec` (model con lồng nhau `PaymentPlan`, `Literal`, `ge=0`, `list[str]`): ra object hợp lệ ngay lần đầu, ví dụ `{"amount_vnd":18000000,"jar":"giai_tri","payment":{"method":"installment","installments":6},"start_date":"2026-12-01","constraints":["không được làm hụt hũ ăn uống"]}`.
- **Trường có ràng buộc (`ge=0`, `le=36`, `Literal`/enum, `$defs` lồng nhau) không gây lỗi 400** từ Bedrock với Haiku 4.5: JSON schema có `minimum`, `maximum`, `enum`, `$ref` đều được nhận. (Chỉ thử Haiku 4.5; chưa thử Sonnet 4.6.)
- **`stop_reason` khi thành công là `"tool_use"`, không phải `"end_turn"`** (vì lượt kết thúc bằng lệnh gọi tool của schema). Đừng kiểm `stop_reason == "end_turn"` để biết thành công; kiểm `result.structured_output is not None`.
- `str(result)` là chuỗi JSON của object.
- **Lỗi validate không ném**: validator Pydantic buộc ngày sau 2026-11-21, người dùng nói 2026-01-05. Model gọi tool lần đầu, Strands trả `toolResult` với `status: "error"` và nội dung `Validation failed for FutureSpec. Please fix the following errors:\n- Field 'start_date': Value error, start_date phải SAU 2026-11-21; hãy chọn ngày sau đó`. Model lúc đó **trả lời bằng văn bản** (xin lỗi, hỏi lại người dùng) thay vì sửa; Strands thêm tin user `You must format the previous response as structured output.` và ép lần nữa; lần này model tự sửa thành `2026-11-22` và thành công. Tức là model **tự đổi ngày người dùng nói** để qua validator: validator chỉ là chặn cú pháp, không thay thế kiểm tra nghiệp vụ.
- **Giới hạn số lần**: validator không thể thỏa (`Impossible`) với `limits={"structured_output_attempts": 2}`: không ném, `stop_reason == "limit_structured_output_attempts"`, `structured_output is None`. **Không đặt `limits`** thì **không kết thúc**: quan sát 6 lần gọi model liên tiếp rồi phải ngắt bằng `cancel_signal` (`stop_reason == "cancelled"`); chạy riêng với `timeout 100` không ra kết quả trong 100 giây. Kết luận: **luôn đặt `structured_output_attempts`** (tài liệu chỉ nói "ném `StructuredOutputException`", thực tế là vòng lặp không đáy; chưa thấy `StructuredOutputException` ném ra trong các lần thử).
- **`agent.structured_output(Model, prompt)` cũ vẫn còn và vẫn chạy** (`intent='move_money' ... amount_vnd=300000`), nhưng phát `DeprecationWarning` ("You should pass in `structured_output_model` directly into the agent invocation"); cả `structured_output_async` cũng vậy.
- Đo thêm: `cancel_signal=threading.Event()` hoạt động, trả `stop_reason == "cancelled"`; `agent.add_hook(fn, AfterModelCallEvent)` đăng ký được bằng hàm rời.

### 2.3 Streaming `stream_async` [Chạy] (`s3_streaming.py`, `out/out_s3.txt`)

Một lượt có tool (không tham số). Mỗi event là dict; khóa thực nhận theo thứ tự:

```
init_event_loop                                   (bool)
start                                             (bool)       <- khóa MỚI, tài liệu không nhắc
start_event_loop
event x3                                          (event thô: messageStart, contentBlockStart, contentBlockDelta ...)
current_tool_use + delta + type="tool_use_stream" (name="get_jar_balances", input="")
event x3                                          (contentBlockStop, messageStop, metadata)
message   (assistant, toolUse)
message   (user, toolResult)                      <- tin toolResult cũng đi qua `message`
start, start_event_loop                           (vòng 2)
event, data+delta+messages+model+system_prompt+tool_config   x N   (mỗi mẩu text)
event x3 (metadata)
message   (assistant, text)
result    (AgentResult, stop_reason="end_turn")
```

Điểm cần biết:
- Mỗi event `data` mang theo cả **`messages`, `model`, `system_prompt`, `tool_config`**: nếu serialize nguyên event ra trình duyệt thì **lộ system prompt và cấu hình tool** (đúng như cảnh báo "dùng allowlist" của tài liệu streaming). Adapter AG-UI không làm vậy (chỉ phát event AG-UI).
- `current_tool_use` chỉ đến **một lần** với `input` rỗng khi tool không có tham số; không có `tool_stream_event` cho tool thường (chỉ có với tool async-generator).
- `result` là khóa cuối, giá trị là `AgentResult`.

### 2.4 Server AG-UI local bằng `ag-ui-strands` [Chạy] (`server_simple.py`, `server.py`, `agui_call.py`)

- Dựng bằng **`create_strands_app(StrandsAgent(agent=..., name=..., description=...), "/invocations", "/ping", origins=[...], allow_headers=[...])`**: chạy được (cổng 8102). Server nhiều route dùng `add_strands_fastapi_endpoint(app, strands_agent, "/route")` + `add_ping`. Chạy `uvicorn` ở `127.0.0.1`.
- Gọi bằng `curl -N -X POST http://127.0.0.1:8102/invocations -H "Content-Type: application/json" -H "Accept: text/event-stream" -d @request.json` với `RunAgentInput` camelCase `{"threadId","runId","state":{},"messages":[{"id","role":"user","content"}],"tools":[],"context":[],"forwardedProps":{}}`: HTTP 200, `content-type: text/event-stream; charset=utf-8`, `cache-control: no-cache`, 34 event. Lưu ở `out/sse_curl_8102.txt` (nguyên văn) và `out/sse_base.txt`.
- Dạng dây: `data: {json}\n\n`, **không có dòng `event:` hay `id:`, không có comment `: ping`** (nên không có `Last-Event-ID` phát lại).
- `GET /ping` trả `{"status":"healthy"}` (**chữ thường**). Tài liệu hợp đồng AgentCore ghi `{"status":"Healthy"}`; chưa kiểm AgentCore có phân biệt hoa thường không. [Suy luận: rủi ro nhỏ, nên tự viết route `/ping` trả đúng `Healthy` khi đóng gói.]

Các loại event thực nhận (toàn bộ thí nghiệm): `RUN_STARTED`, `STATE_SNAPSHOT`, `MESSAGES_SNAPSHOT`, `TOOL_CALL_START`, `TOOL_CALL_ARGS`, `TOOL_CALL_END`, `TOOL_CALL_RESULT`, `TEXT_MESSAGE_START`, `TEXT_MESSAGE_CONTENT`, `TEXT_MESSAGE_END`, `RAW`, `CUSTOM`, `ACTIVITY_SNAPSHOT`, `STATE_DELTA`, `RUN_FINISHED`, `RUN_ERROR`. **Không thấy** `STEP_*`, `REASONING_*`, `SUBAGENT_*` (không tạo điều kiện).

Thứ tự một lượt có tool (tool không tham số, route `/base`):

```
RUN_STARTED > STATE_SNAPSHOT > MESSAGES_SNAPSHOT > TOOL_CALL_START > TOOL_CALL_END > MESSAGES_SNAPSHOT
> RAW > TOOL_CALL_RESULT > MESSAGES_SNAPSHOT > TEXT_MESSAGE_START > TEXT_MESSAGE_CONTENT x17 > RAW
> TEXT_MESSAGE_END > MESSAGES_SNAPSHOT > STATE_SNAPSHOT > RUN_FINISHED
```

Payload mẫu rút gọn:

```json
{"type":"RUN_STARTED","threadId":"t-base1","runId":"r-da3a17","protocolVersion":"1.0"}
{"type":"STATE_SNAPSHOT","snapshot":{}}
{"type":"TOOL_CALL_START","toolCallId":"tooluse_ti6d...","toolCallName":"get_jar_balances","parentMessageId":"6423f090-..."}
{"type":"TOOL_CALL_END","toolCallId":"tooluse_ti6d..."}
{"type":"RAW","event":{"event":{"metadata":{"usage":{"inputTokens":711,"outputTokens":40,"totalTokens":751},"metrics":{"latencyMs":503}}}},"source":"strands"}
{"type":"TOOL_CALL_RESULT","messageId":"cbfaa096-...","toolCallId":"tooluse_ti6d...","content":"{\"as_of\":\"2026-11-21\",\"jars\":[{\"code\":\"an_uong\",\"name\":\"Ăn uống\",\"balance_vnd\":1250000,...}]}"}
{"type":"TEXT_MESSAGE_START","messageId":"2b100f3e-...","role":"assistant"}
{"type":"TEXT_MESSAGE_CONTENT","messageId":"2b100f3e-...","delta":"Hũ ăn uống"}
{"type":"RUN_FINISHED","threadId":"t-base1","runId":"r-da3a17","outcome":{"type":"success"},"usage":[{"provider":"bedrock","model":"global.anthropic.claude-haiku-4-5-20251001-v1:0","inputTokens":1613,"outputTokens":94,"totalTokens":1707}]}
```

Chi tiết khác với tài liệu hoặc đáng ghi:
- Tool **không có tham số thì không phát `TOOL_CALL_ARGS`**. Tool có tham số phát nhiều `TOOL_CALL_ARGS` (mẩu JSON dở, ví dụ `"{\"from_"`, `"jar\": \""`).
- `TOOL_CALL_RESULT.content` là **chuỗi JSON** của kết quả tool (frontend phải `JSON.parse`).
- `RAW` mang metadata token/độ trễ của Bedrock (`source: "strands"`): frontend nên bỏ qua.
- `RUN_FINISHED` có thêm `usage` (token theo model) và `outcome`; đây là cách có sẵn để ghi chi phí.
- `MESSAGES_SNAPSHOT` phát nhiều lần trong một lượt (sau mỗi bước tool/text): tốn băng thông, có thể tắt bằng `StrandsAgentConfig(emit_messages_snapshot=False)` [Đọc mã, chưa thử].
- `STATE_SNAPSHOT` đầu và cuối lượt luôn có (cuối lượt phản ánh `current_state` của adapter, xem 2.5).
- Mỗi đoạn văn bản của model là một cặp `TEXT_MESSAGE_START ... END` riêng: một lượt có thể có **nhiều tin nhắn văn bản** (ở `/structured` model viết văn bản trước cả hai lần gọi tool: 19 và 23 event `CONTENT`).
- Lỗi do adapter phát thành `RUN_ERROR` với `code` riêng, kèm `RUN_STARTED` trước nó, vẫn HTTP 200: `PENDING_INTERRUPTS`, `INTERRUPT_RESUME_ERROR`, `UNKNOWN_INTERRUPT_ID` (mục 2.7).

### 2.5 Khối UI dạng JSON: bốn cách [Chạy] (`server.py`, các route `ui_*`)

Block builder (code backend, không qua LLM) biến kết quả tool thành `{"type":"jar_summary","v":1,"id":"js:2026-11-21","source":{...},"fallback_text":"Ăn uống: 1.250.000 đ; ...","data":{"jars":[{... ,"pct_left":42}]}}`. Kết quả tool thật là dict `{"as_of","jars":[...]}`. Với **mọi** cách dưới đây tool chạy đúng một lần, khối đến **ngay sau `TOOL_CALL_RESULT` và trước `TEXT_MESSAGE_START`** (cách (e) đến trước `TOOL_CALL_RESULT`).

| | Cách | Chạy được? | Event thực nhận | Ghi chú rút ra |
|---|---|---|---|---|
| (a) | Đọc thẳng `TOOL_CALL_RESULT` | **Có**, không cần code adapter | `TOOL_CALL_RESULT.content` = chuỗi JSON của dict tool trả | Đơn giản nhất. Khối là **chính thứ LLM thấy**; không dựng thêm được khối khác với số liệu tool |
| (b) | `ToolBehavior(custom_result_handler=...)` yield `CustomEvent` | **Có** | `{"type":"CUSTOM","name":"yofina.block","value":{<khối>}}` | `ctx.result_data` là **dict** đã parse (không phải chuỗi). Handler chạy **thêm** vào `TOOL_CALL_RESULT` mặc định, không thay thế |
| (c) | Cùng handler, yield `ActivitySnapshotEvent` | **Có**: SDK `ag-ui-protocol` 1.0.0 có `ActivitySnapshotEvent` và `ActivityDeltaEvent` | `{"type":"ACTIVITY_SNAPSHOT","messageId":"js:2026-11-21","activityType":"yofina.block","content":{<khối>},"replace":true}` | `messageId` do mình đặt (dùng `block.id`) nên cập nhật/thay thế khối đúng chỗ được. **Không đưa vào `MESSAGES_SNAPSHOT`** (xem bên dưới) |
| (d1) | `ToolBehavior(state_from_result=fn)` trả dict | **Có** | `{"type":"STATE_SNAPSHOT","snapshot":{"composer":{"blocks":[{<khối>}]}}}` ngay sau `TOOL_CALL_RESULT` | `current_state` của adapter được cập nhật, nên **`STATE_SNAPSHOT` cuối lượt vẫn giữ** `composer` |
| (d2) | handler yield `StateDeltaEvent` (JSON Patch) | **Có** phát ra | `{"type":"STATE_DELTA","delta":[{"op":"add","path":"/blocks","value":[{<khối>}]}]}` | **Bẫy**: adapter không biết về delta, nên `STATE_SNAPSHOT` cuối lượt là `{}` và **xóa mất** thứ delta vừa thêm nếu client thay state theo mỗi snapshot |
| (e) | Tool **async generator** + `ToolBehavior(tool_stream_event_handler=...)` (cách nên dùng, xem 3.1) | **Có** | `ACTIVITY_SNAPSHOT` trước `TOOL_CALL_RESULT`; `TOOL_CALL_RESULT.content` chỉ là bản gọn `{"as_of":"2026-11-21","an_uong_balance_vnd":1250000}` | LLM chỉ thấy bản gọn, khối đầy đủ đi riêng ra UI. Handler nhận mọi `yield` của tool (kể cả giá trị cuối) nên phải lọc theo khóa |
| (f) | Tool async generator `yield {"state": {...}}` (không cấu hình gì) | Có (đúng như `strands-agui.md` 3.8c) | `STATE_SNAPSHOT` với `composer.blocks` trước `TOOL_CALL_RESULT` | **Cùng bẫy với (d2)**: `STATE_SNAPSHOT` cuối lượt là `{}` |

Điểm quan trọng khác:
- **`ACTIVITY_SNAPSHOT` và `CUSTOM` không nằm trong `MESSAGES_SNAPSHOT`** (4 tin cuối chỉ có `user`, `assistant`, `tool`, `assistant`). Hệ quả: khối chỉ tồn tại trong luồng của lượt đó; nếu frontend tải lại trang và dựng từ `MESSAGES_SNAPSHOT` hoặc từ replay, khối mất. Phải lưu khối phía server/DB theo `trace_id` (đúng khuyến nghị trong `agentic-ui-generative-ui.md` 6.2).
- Với (a), (b), (c), (d1), (d2) LLM nhìn thấy nguyên kết quả tool (hết cả `budget_vnd`...), và còn viết lại thành bảng markdown trong `TEXT_MESSAGE_CONTENT`. Chỉ (e) và (f) giữ được khối ra khỏi ngữ cảnh LLM.
- `custom_result_handler`/`state_from_result` đều nhận `ToolResultContext` (`tool_name`, `tool_use_id`, `tool_input`, `result_data`, `message_id`, `input_data`). `tool_stream_event_handler` nhận `ToolStreamEventContext` (`tool_use_id`, `tool_name`, `stream_data`).
- Lỗi trong handler không làm hỏng run: được bọc và phát `CUSTOM` tên `hook_error` [Đọc mã `agent.py` quanh dòng 6980, chưa chạy].
- Chưa thử `ToolBehavior` với tool MCP (tên tool có tiền tố, ví dụ `gateway_get_jar_balances`): khóa `tool_behaviors` phải khớp tên đó [Suy luận].

### 2.6 Structured output + adapter AG-UI [Chạy] (`/structured`, `/structured2`)

- Adapter **dùng được** với agent có `structured_output_model` đặt ở **hàm dựng `Agent(structured_output_model=...)`**: adapter đọc lại giá trị này (qua `_default_structured_output_model`) và cấp cho agent từng thread. `RunAgentInput` không có chỗ truyền model theo lượt; `agui_agent.run(...)` cũng không có tham số này [Đọc mã: `stream_kwargs` không chứa `structured_output_model`].
- Event thực nhận: model gọi `get_jar_balances` trước, sau đó **một tool call tên đúng bằng lớp Pydantic** (`toolCallName:"IntentResult"`), có `TOOL_CALL_ARGS` (mẩu JSON), `TOOL_CALL_END`, rồi `TOOL_CALL_RESULT` với `content:"\"Successfully validated IntentResult structured output\""`. **Không có event riêng mang object đã validate**; `RUN_FINISHED` cũng không mang `structuredOutput`. Frontend ngây thơ sẽ thấy một "tool call" lạ tên `IntentResult`; model còn viết văn bản (một tin nhắn) trước cả hai lần gọi tool, nên người dùng thấy lời dẫn không mong muốn.
- Cách bắt object: `ToolBehavior` đặt cho tên tool = tên lớp Pydantic: `tool_behaviors={"IntentResult": ToolBehavior(custom_result_handler=h)}` với `h` yield `CustomEvent(name="yofina.structured_output", value={"schema": ctx.tool_name, "object": ctx.tool_input})` khi `ctx.result_data` bắt đầu bằng `"Successfully validated"`. Đã chạy được: `{"type":"CUSTOM","name":"yofina.structured_output","value":{"schema":"IntentResult","object":{"intent":"move_money","amount_vnd":300000,"confidence":0.95}}}`. (Bản `ctx.tool_input` là bản đã qua model; ở lượt validate lỗi `result_data` không bắt đầu bằng `Successfully`, nên khối bị bỏ đúng.)
- Kết luận: **dùng được nhưng vụng**; adapter không xử lý riêng structured output. Với router/composer cần object đã validate **và** kiểm soát vòng lặp (limits, thứ tự), nên **gọi agent bằng code** (`await agent.invoke_async(..., structured_output_model=..., limits=...)`) rồi tự phát event, tức "Cách B" trong `strands-agui.md` 4.2. Không thử cách tự viết generator đầy đủ trong spike này.

### 2.7 Interrupt / resume (human-in-the-loop) [Chạy] (`server.py` `/interrupt*`, `s7a_native_interrupt.py`)

Ba cơ chế đã thử, tất cả qua AG-UI với `FileSessionManager` (qua `StrandsAgentConfig(session_manager_provider=...)`) trừ khi ghi khác:

**(A) `tool_context.interrupt(name, reason={...})` trong tool `@tool(context=True)`**

Lượt 1, `RUN_FINISHED` (không có `TOOL_CALL_RESULT`; có `TOOL_CALL_START/ARGS/END` của tool trước đó):

```json
{"type":"RUN_FINISHED","threadId":"t-int1","runId":"r-cb51ba",
 "outcome":{"type":"interrupt","interrupts":[{
   "id":"v1:tool_call:tooluse_rvBZ...:ed1ac617-e69a-570b-bddf-84724f2a3b8b",
   "reason":"yofina-confirm-move",
   "metadata":{"reason":{"message":"Chuyển 300.000 đ từ giai_tri sang an_uong?","from_jar":"giai_tri","to_jar":"an_uong","amount_vnd":300000}}}]},
 "usage":[...]}
```
- Tên interrupt Strands thành **`reason`** của interrupt AG-UI (không phải `reason: "confirmation"`); dict `reason=` của mình nằm ở **`metadata.reason`**; **không có** `message`, `toolCallId`, `responseSchema` (frontend phải biết tên `yofina-confirm-move`).
- Resume: một run mới, cùng `threadId`, `resume: [{"interruptId":"<id>","status":"resolved","payload":{"approved":true}}]`, `messages: []`. Tool nhận `approval == {"response": {"approved": true}}` (**bọc**; đúng như tài liệu) hoặc `{"cancelled": true}` khi `status:"cancelled"` (đã thử cả hai: cancelled cho `{"status":"cancelled"}` và model tự giải thích "giao dịch đã bị hủy"). Sau resume phát `TOOL_CALL_RESULT` (`{"status":"done",...}`) rồi văn bản rồi `RUN_FINISHED` success.
- Phiên bản ghi vào file đã kiểm: `sessions/session_<threadId>/agents/agent_yofina/agent.json` có `_internal_state.interrupt_state` (interrupt, `pending_tool_execution`) và `state.ag_ui_interrupt_bookkeeping.pending_interrupts`. `agent_id="yofina"` đặt ở `Agent(...)` được adapter chép sang agent từng thread (thư mục `agent_yofina`).
- **Bẫy "code trước interrupt chạy lại" xác nhận**: log ghi dòng trước `interrupt()` hai lần (pid 23756 lúc lượt 1, pid 26480 lúc resume) và dòng sau `interrupt()` một lần. Tác dụng phụ phải đặt **sau** `interrupt()`.
- **Resume sau khi khởi động lại tiến trình server: chạy được.** Thao tác: lượt 1 ở tiến trình pid 23756, tắt tiến trình (kill theo cổng), bật tiến trình mới (pid 26480, cùng thư mục sessions), gửi resume: tool chạy tiếp, ghi `ledger.json`, kết quả `done`.
- **Không có session manager thì không resume được sau khi restart**: route `/interrupt_nosm`, sau restart, cùng `interruptId`: `RUN_ERROR` `code: "UNKNOWN_INTERRUPT_ID"`, `message: "No pending interrupts for this thread."`.
- Các đường lỗi (đều HTTP 200, `RUN_STARTED` rồi `RUN_ERROR`): lượt mới có `messages` khi thread còn interrupt: `code: "PENDING_INTERRUPTS"`, `"Thread has pending interrupts. Include resume[] to address them."`; resume với id lạ: `INTERRUPT_RESUME_ERROR`, `"Resume references an interrupt that is not open: bogus"`; gửi lại cùng resume cho thread đã xong: `UNKNOWN_INTERRUPT_ID`, `"No pending interrupts for this thread."` (**không idempotent kiểu "trả lại kết quả cũ"**, mà báo lỗi: client phải coi lỗi này là "đã xử lý").

**(B) `ToolBehavior(interrupt_on_call=True)` trên tool thường (adapter tự dựng hook `BeforeToolCall`)**

```json
"interrupts":[{"id":"v1:before_tool_call:tooluse_7pYU...:d694e120-...","reason":"tool_call","message":"Approve call to move_plain?",
  "toolCallId":"tooluse_7pYU...","responseSchema":{"type":"object","properties":{"approved":{"type":"boolean"}},"required":["approved"]},
  "metadata":{"tool_name":"move_plain","tool_input":{"from_jar":"giai_tri","to_jar":"an_uong","amount_vnd":70000},"strandsName":"ag_ui:tool_call:move_plain"}}]
```
- Đầy đủ hơn (A): có `message`, `toolCallId`, `responseSchema`, và `metadata.tool_input` để dựng khối `confirm`. Tool **không chạy** trước khi được duyệt (log `move_plain_ran` chỉ ghi **một** dòng sau resume, trong tiến trình mới) nên **không dính bẫy chạy lại**. Resume sau restart tiến trình cũng chạy được (`payload:{"approved":true}`). [Chạy]
- Lưu ý: `reason: "tool_call"` là loại lõi AG-UI; `message` là câu cố định tiếng Anh, tự dựng nội dung xác nhận từ `metadata.tool_input` ở backend.

**(C) `HumanInTheLoop(allowed_tools=[...])` của interventions mới**
- Thuần Strands (`s7a_native_interrupt.py hitl`): chạy được; `stop_reason == "interrupt"`, interrupt `strands:human-in-the-loop`, `reason` là chuỗi `Approve "move_plain"?\n  Input: {...}`; resume `response="y"` thì tool chạy.
- Qua adapter: `interventions=[HumanInTheLoop(...)]` trên Agent mẫu **được chép sang agent từng thread** và interrupt hiện ra trong `RUN_FINISHED` (`reason:"strands:human-in-the-loop"`, chuỗi hỏi nằm ở `metadata.reason`). **Nhưng resume không chạy**: adapter luôn bọc payload thành `{"response": payload}` (kể cả payload là chuỗi `"y"`), HITL không nhận ra, trả `TOOL_CALL_RESULT` `"CONFIRMATION_FAILED: Approve \"move_plain\"?..."` và tool không chạy (fail-closed). **Không dùng `HumanInTheLoop` qua `ag-ui-strands` 1.0.4**; dùng (A) hoặc (B).

Một interrupt là nơi đặt cờ do server kiểm soát: ở (B) `metadata.tool_input` do server thấy, người dùng chỉ gửi `{"approved": true}`; model không điền cờ nào. Nhưng **cả (A) và (B) đều để tool ghi chạy trong vòng LLM**; thiết kế "xác nhận ngoài vòng LLM" của `strands-agui.md` 6.3 vẫn chưa thử.

### 2.8 CORS local [Chạy]

- `create_strands_app(..., origins=["http://localhost:5173"], allow_headers=[...])` đã tự gắn `CORSMiddleware` (đọc mã: `allow_credentials` chỉ bật với origin tường minh). Không truyền `origins` thì mặc định `*` kèm `FutureWarning`.
- `server.py` dùng `CORSMiddleware` tự thêm (`allow_methods=["GET","POST","OPTIONS"]`, `allow_headers=["authorization","content-type","x-amzn-bedrock-agentcore-runtime-session-id"]`, `expose_headers=[...]`).
- Preflight `OPTIONS /invocations` (origin `http://localhost:5173`, `Access-Control-Request-Headers: authorization,content-type,x-amzn-bedrock-agentcore-runtime-session-id`): **HTTP 200**, `access-control-allow-origin: http://localhost:5173`, `access-control-allow-credentials: true`, `access-control-allow-headers: Accept, Accept-Language, Content-Language, Content-Type, authorization, content-type, x-amzn-bedrock-agentcore-runtime-session-id`, `access-control-max-age: 600`. Origin lạ (`http://evil.example`): **HTTP 400** `Disallowed CORS origin`. Header lạ (`x-foo`) cũng **400**.
- Luồng SSE `POST` có `Origin`: `access-control-allow-origin: http://localhost:5173`, `access-control-allow-credentials: true`, `vary: Origin`, `cache-control: no-cache`, `content-type: text/event-stream; charset=utf-8`, `transfer-encoding: chunked`. **Không có** `x-accel-buffering: no` (cần thêm nếu có proxy/nginx ở giữa [Suy luận]); `access-control-expose-headers` chỉ có khi tự thêm `expose_headers`.
- Đây chỉ là kiểm local; CORS trên AgentCore thật là spike khác.

### 2.9 MCP client [Chạy] (`mcp_server.py`, `s9_mcp_client.py`)

- Với **`mcp 2.3.0`**: `from mcp.client.streamable_http import streamable_http_client` **chạy được**; **`streamablehttp_client` không còn** (`AttributeError`). Mẫu FAST (`mcp==1.30.0`) dùng `streamablehttp_client` sẽ hỏng nếu nâng `mcp` lên 2.x. Chữ ký mới: `streamable_http_client(url, *, http_client: httpx2.AsyncClient | None, terminate_on_close=True, max_sse_event_size=1048576)` (**không còn tham số `headers=`**: header đặt trên `http_client` hoặc dùng `MCPClient(url=..., headers=...)` của Strands [Đọc chữ ký; chưa thử truyền header]). Cũng còn `mcp.client.sse.sse_client`, `mcp.client.stdio.stdio_client`.
- `mcp 2.x` đổi `FastMCP` thành **`from mcp.server.mcpserver import MCPServer`**; `mcp.server.fastmcp` không còn (thông báo lỗi tự chỉ sang tài liệu migration). `host`/`port` không còn ở hàm dựng, truyền ở `mcp.run("streamable-http", host=..., port=...)`. Gói `fastmcp` độc lập không cài.
- `strands.tools.mcp.MCPClient(transport_callable=None, *, url=None, headers=None, auth=None, auth_provider=None, startup_timeout=30, tool_filters=None, prefix=None, ...)`: cả `MCPClient(url=URL, prefix="gateway")` và `MCPClient(lambda: streamable_http_client(URL), prefix="gateway")` đều chạy.
- **Tên tool hiện ra: `gateway_get_jar_balances`** (tiền tố + **dấu gạch dưới**, không phải dấu chấm). Agent thật gọi tool này và trả lời "Hũ ăn uống còn **1.250.000 đồng**". Nhưng **`call_tool_sync(tool_use_id, name, args)` nhận tên gốc phía server** (`get_jar_balances`); truyền tên có tiền tố trả `{'status':'error','content':[{'text':'Unknown tool: gateway_get_jar_balances'}]}`.
- Chưa thử với AgentCore Gateway thật (tên kiểu `<target>___<tool>` chưa kiểm).

## 3. Mẫu code tối thiểu đã chạy được

### 3.1 Tool + khối UI qua AG-UI (cách (e), đã chạy: `/ui_stream`)

```python
from strands import Agent, tool
from ag_ui.core import ActivitySnapshotEvent, EventType
from ag_ui_strands import (StrandsAgent, StrandsAgentConfig, ToolBehavior, create_strands_app)

def build_jar_summary(raw: dict) -> dict:               # block builder: code, không qua LLM
    return {"type": "jar_summary", "v": 1, "id": "js:" + raw["as_of"],
            "source": {"tool": "get_jar_balances", "as_of": raw["as_of"]},
            "fallback_text": "...", "data": {"jars": raw["jars"]}}

@tool
async def show_jar_summary():                           # tool async generator
    """Hiển thị khối số dư các hũ cho người dùng và trả số dư về cho bạn."""
    raw = read_jars_from_ledger()                       # tất định
    yield {"yofina_block": build_jar_summary(raw)}      # -> tool_stream_event_handler; LLM KHÔNG thấy
    yield {"as_of": raw["as_of"], "an_uong_balance_vnd": raw["an_uong"]}   # giá trị cuối = kết quả tool, LLM thấy bản gọn này

async def stream_event_handler(ctx):                    # ToolStreamEventContext
    if isinstance(ctx.stream_data, dict) and "yofina_block" in ctx.stream_data:
        block = ctx.stream_data["yofina_block"]
        yield ActivitySnapshotEvent(type=EventType.ACTIVITY_SNAPSHOT, message_id=block["id"],
                                    activity_type="yofina.block", content=block, replace=True)

agent = Agent(model=model, tools=[show_jar_summary], callback_handler=None, agent_id="yofina")
agui = StrandsAgent(agent=agent, name="yofina", description="...", config=StrandsAgentConfig(
    tool_behaviors={"show_jar_summary": ToolBehavior(tool_stream_event_handler=stream_event_handler)}))
app = create_strands_app(agui, "/invocations", "/ping", origins=["http://localhost:5173"])
```

Event thực nhận: `TOOL_CALL_START > TOOL_CALL_END > ACTIVITY_SNAPSHOT{activityType:"yofina.block", content:{khối}} > TOOL_CALL_RESULT{"as_of":..., "an_uong_balance_vnd":1250000} > TEXT_MESSAGE_* > STATE_SNAPSHOT{} > RUN_FINISHED`. Lưu ý: khi dùng `tool_stream_event_handler`, adapter **tắt** việc tự phát `STATE_SNAPSHOT` cho `yield {"state":...}` của tool đó (theo docstring). Cách gọn hơn nếu chấp nhận LLM thấy cả kết quả: `ToolBehavior(custom_result_handler=h)` với `h` yield `ActivitySnapshotEvent` hoặc `CustomEvent` từ `ctx.result_data` (route `/ui_activity`, `/ui_custom`).

Frontend: ánh xạ `activityType == "yofina.block"` -> registry theo `content.type`; thay thế theo `messageId`; **lưu khối vào store/DB của app** vì `MESSAGES_SNAPSHOT` không chứa nó.

### 3.2 Luồng confirm (cách (B), đã chạy: `/interrupt_hook`, qua restart tiến trình)

```python
from strands.session.file_session_manager import FileSessionManager

@tool
def move_between_jars(from_jar: str, to_jar: str, amount_vnd: int) -> dict:
    """Chuyển tiền giữa hai hũ (GHI dữ liệu).

    Args: ...
    """
    return ledger_write(from_jar, to_jar, amount_vnd)    # chỉ chạy SAU khi người dùng duyệt, và chạy đúng một lần

def sm_provider(run_input):                              # bền qua restart: S3SessionManager / SnapshotSessionManager khi lên AWS
    return FileSessionManager(session_id=run_input.thread_id, storage_dir="sessions")

config = StrandsAgentConfig(
    tool_behaviors={"move_between_jars": ToolBehavior(interrupt_on_call=True)},
    session_manager_provider=sm_provider)
agent = Agent(model=model, tools=[move_between_jars], agent_id="yofina", callback_handler=None)  # agent_id ỔN ĐỊNH
agui = StrandsAgent(agent=agent, name="yofina", description="...", config=config)
```

Dây:
1. Request 1 (user: "Chuyển 70000 từ giai_tri sang an_uong"): `... TOOL_CALL_START/ARGS/END > STATE_SNAPSHOT > RUN_FINISHED{outcome:{type:"interrupt", interrupts:[{id, reason:"tool_call", message:"Approve call to move_plain?", toolCallId, responseSchema:{approved:boolean}, metadata:{tool_name, tool_input:{from_jar,to_jar,amount_vnd}}}]}}`. Frontend dựng khối `confirm` từ `metadata.tool_input` (số tiền do người dùng thấy lấy từ `tool_input`, không từ lời LLM).
2. (Có thể tắt/bật lại tiến trình server ở đây.)
3. Request 2: cùng `threadId`, `messages: []`, `resume:[{"interruptId":"<id>","status":"resolved","payload":{"approved":true}}]` (hoặc `"status":"cancelled"`): `TOOL_CALL_RESULT{"status":"done",...} > TEXT_MESSAGE_* > RUN_FINISHED{outcome:{type:"success"}}`.

Cách (A) `tool_context.interrupt(...)` (`@tool(context=True)`) cũng chạy và cho phép đặt dict `reason` tùy ý, nhưng mã trước `interrupt()` chạy lại khi resume và các trường `message`/`responseSchema` không có.

## 4. Điều vẫn chưa thử được

- **Sonnet 4.6** và model lớn nói chung: chỉ dùng Haiku 4.5; chưa biết structured output có ổn với Sonnet; chưa đo độ trễ ký tự đầu.
- **`AgentCoreMemorySessionManager`** và `S3SessionManager` / `SnapshotSessionManager`: chỉ thử `FileSessionManager` (không tạo tài nguyên AWS). Câu hỏi "AgentCore Memory khôi phục interrupt qua microVM khác" chưa trả lời.
- Resume **đồng thời / đua** (hai request resume cùng lúc), resume khi interrupt hết hạn (`expiresAt` không được adapter phát), nhiều interrupt cùng lượt (nhiều tool ghi song song trong một phản hồi).
- Thiết kế "xác nhận ngoài vòng LLM" (backend tự gọi tool ghi sau nút bấm, token một lần gắn hash tham số): chưa dựng.
- Tự viết generator phát event (Cách B) và mô hình router -> orchestrator -> composer: chưa dựng.
- `emit_messages_snapshot=False`, `subagent_visibility`, `a2ui`, Graph/Swarm qua adapter, `invocation_state_provider`, `auth=`: chỉ đọc mã/tài liệu, không chạy.
- Hành vi CORS trên AgentCore Runtime thật, header `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` thật, `/ping` viết thường so với hợp đồng AgentCore, đóng gói ARM64.
- Tool MCP qua adapter (tên có tiền tố trong `ToolBehavior`), AgentCore Gateway thật (tên `___`), truyền `headers` với `streamable_http_client` của `mcp 2.x`.
- Prompt caching, guardrail, OpenTelemetry, song song tool: ngoài phạm vi spike này.
- Giới hạn (`limits`) có tính token của sub-agent không: không thử (không dựng multi-agent).
