# Strands Agents SDK (Python) và giao thức AG-UI phía backend

Ghi chú nghiên cứu cho Yofina Foresight. Truy cập nguồn ngày 2026-11-21. Bản gốc chỉ đọc tài liệu, **chưa chạy thử dòng code nào**: mọi đoạn code dưới đây là chép/ghép từ nguồn đã ghi, phần ghép là suy đoán của người viết và có gắn nhãn. **[Đã chạy thử 2026-11-21]** Các mục đánh dấu như vậy bên dưới đã được chạy thật (Strands 1.65.0, ag-ui-strands 1.0.4, Haiku 4.5); kết quả đầy đủ, event thực nhận và mẫu code chạy được: `spike-strands-agui-local.md` (cùng thư mục), code ở `spikes/strands-agui-local/`.

Quy ước nhãn:
- **[D]** đã đọc trong tài liệu chính thức (strandsagents.com, docs.ag-ui.com, docs.aws.amazon.com).
- **[R]** đọc từ repo/mã nguồn/blog (repo FAST, repo ag-ui-protocol/ag-ui, PyPI, mã nguồn Strands trên GitHub).
- **[?]** suy đoán hoặc khuyến nghị của người viết, cần kiểm chứng.

## 1. Câu hỏi cần trả lời

1. Strands cơ bản: phiên bản, cài đặt, Agent + Bedrock, `@tool`, MCP client tới AgentCore Gateway, system prompt, model nhỏ/lớn, prompt caching.
2. Structured output theo Pydantic: API hiện hành, đổi tên, xử lý lỗi validate, dùng cho `IntentResult`, `Plan`, `ScenarioSpec`, `Roadmap`, `Verdict`.
3. Streaming: `stream_async`, các loại event, đẩy ra trình duyệt qua SSE.
4. Multi-agent: agents-as-tools, Graph, Swarm, workflow; router → orchestrator → specialist; gọi tool song song; giới hạn vòng/token.
5. Human in the loop: interrupt/resume, session manager, chạy trên AgentCore Runtime.
6. Hooks, guardrail, observability: verifier quanh tool call, Bedrock Guardrails, OpenTelemetry.
7. AG-UI: giao thức, danh sách event, adapter Strands, hỗ trợ của AgentCore Runtime, cách gửi khối UI JSON, interrupt/resume trong AG-UI.
8. Mẫu tối thiểu: agent Strands 1 tool + structured output + stream AG-UI.

## 2. Kết luận ngắn: làm thế này

1. **Ghim phiên bản**, đừng để pip chọn: tại 2026-11-21 `strands-agents` là **1.65.0** (ra 2026-11-13, Python >= 3.10), `ag-ui-strands` **1.0.4** (2026-11-12, cần `strands-agents>=1.55.0`, `ag-ui-protocol>=1.0.0`), `bedrock-agentcore` **1.27.0** (2026-11-20), `ag-ui-protocol` **1.0.0** (2026-09-17). [R: PyPI] Tài liệu AWS về AG-UI còn ghim `ag-ui-strands>=0.3,<0.4` và repo FAST ghim `strands-agents==1.48.0`, `ag-ui-strands==0.1.9`: cả hai **đã cũ** so với bản mới; dùng Python 3.12 (tutorial AWS yêu cầu >= 3.12). **[Đã chạy thử 2026-11-21]** Đúng: `uv pip install strands-agents ag-ui-strands ag-ui-protocol fastapi uvicorn httpx mcp` cài ra đúng 1.65.0 / 1.0.4 / 1.0.0 trên Python 3.12.13. Thiếu sót: `mcp` cài ra **2.3.0** (API khác 1.x, xem mục 3.1) và máy dùng credential `aws login` cần thêm `botocore[crt]`. Danh sách ghim: `spikes/strands-agui-local/requirements.lock.txt`.
2. **Structured output = tham số theo lần gọi**: `agent(msg, structured_output_model=Model)` rồi đọc `result.structured_output`; `invoke_async` và `stream_async` cùng tham số. Lỗi giá trị sai schema **không ném lỗi**, Strands trả lỗi validate cho model để nó tự sửa; chỉ khi hoàn toàn không ra object mới ném `StructuredOutputException`. Đặt `limits={"structured_output_attempts": 3}` để chặn vòng lặp. [D] **[Đã chạy thử 2026-11-21]** Cú pháp và `result.structured_output` đúng (cả `IntentResult`, `ScenarioSpec` lồng, `Literal`, `ge=0`: không gây lỗi 400). **Sai ở hai chỗ**: (1) khi thành công `stop_reason` là `"tool_use"`, không phải `"end_turn"`; (2) **không đặt `structured_output_attempts` thì với validator không thể thỏa, vòng lặp không dừng** (quan sát 6+ lần gọi model, phải cắt bằng `cancel_signal`); chưa thấy `StructuredOutputException` ném ra. Có `limits` thì dừng với `stop_reason == "limit_structured_output_attempts"` và `structured_output is None`. Lỗi validate trả cho model như `toolResult` có `status:"error"`; model có thể tự đổi dữ liệu người dùng để qua validator.
3. **Tránh trường `dict`, `tuple`, kiểu không định kiểu trong schema Pydantic** của `ScenarioSpec`/`Plan`: Strands bỏ bước ép gọi tool và chỉ làm "best effort" (có cảnh báo). Dùng model con lồng nhau, `Literal`, `list[Model]`. [D]
4. **Một Agent mỗi request**, dùng chung đối tượng model: gọi Agent đang chạy sẽ ném `ConcurrencyException`; hai Agent cùng `session_id` + `agent_id` ghi đè lịch sử của nhau không báo lỗi. [D]
5. **Specialist = Agent truyền thẳng vào `tools=[...]`** (hoặc `agent.as_tool(name=, description=, preserve_context=, delegate=)`), đặt `callback_handler=None` cho specialist. Mặc định mỗi lần gọi bắt đầu từ ngữ cảnh sạch, khớp với "cô lập ngữ cảnh" của L3. [D]
6. **Gọi tool song song có sẵn**: executor mặc định là `ConcurrentToolExecutor`, nhưng chỉ song song khi model trả nhiều `tool_use` trong **một** phản hồi; tool async cũng chạy đồng thời. Không có tham số giới hạn mức song song. Tool "delegate" (`delegate=True`) bắt buộc gọi một mình. [D]
7. **Giới hạn lượt**: `agent(msg, limits={"turns": 6, "output_tokens": 2000, "total_tokens": 20000})`; chạm giới hạn thì `result.stop_reason` là `limit_turns` / `limit_total_tokens` / `limit_output_tokens` / `limit_structured_output_attempts` (không ném lỗi); huỷ bằng `cancel_signal=` hoặc `agent.cancel()`. Dùng stop reason này để rẽ sang "thẻ số liệu tất định". [D] **[Đã chạy thử 2026-11-21]** Đúng: khóa `turns`/`output_tokens`/`total_tokens`/`structured_output_attempts`; khóa lạ (`max_turns`) ném `TypeError`; chạm giới hạn trả `limit_turns`/`limit_total_tokens`/`limit_output_tokens`, không ném. Lưu ý: giới hạn kiểm sau vòng đầu (tool đã chạy một lần) và `str(result)` là chuỗi rỗng (tin cuối là `toolResult`), nên phải tự dựng câu trả lời tất định.
8. **Graph của Strands không rẽ lỗi**: trong Python, node ném exception thì cả lệnh gọi graph ném và kết thúc; điều kiện cạnh chỉ rẽ theo kết quả node. Tài liệu Strands khuyên "workflow trong code của bạn" khi các bước cố định và bạn muốn tự xử lý lỗi. Với F3 (LLM lỗi vẫn phải trả thẻ số) nên viết **hàm Python tuần tự có try/except**, không dùng Graph (xem mục 5.2). [D] + [?]
9. **Human in the loop có 3 tầng** [D]: (a) `HumanInTheLoop` / action `Confirm` của interventions (mới, có `ask=` callback), (b) `event.interrupt(...)` trong hook `BeforeToolCallEvent`/`BeforeToolsEvent`, (c) `tool_context.interrupt(...)` trong tool `@tool(context=True)`. Dừng thì `result.stop_reason == "interrupt"`, tiếp tục bằng `agent([{"interruptResponse": {"interruptId": id, "response": ...}}])`. Server không giữ trạng thái thì **bắt buộc có session manager**.
10. **Với Yofina, xác nhận ghi nên đặt ngoài vòng LLM** [?]: agent chỉ đề xuất (khối `confirm`), nút bấm của người dùng gọi một đường xác nhận do backend kiểm soát, backend mới gọi tool ghi qua Gateway kèm cờ xác nhận do **server** gắn. Nếu cờ là tham số tool do LLM điền thì LLM có thể tự bật (xem 6.3).
11. **Hook làm verifier**: `AfterToolCallEvent` (ghi lại kết quả tool, sửa được `event.result`), `BeforeToolCallEvent` (`cancel_tool`, sửa `tool_use`, đổi `selected_tool`), `AfterModelCallEvent.retry`, `AfterInvocationEvent.resume` (gọi tiếp với input mới, hợp với evaluator-optimizer). Interventions (`Proceed/Deny/Guide/Confirm/Transform`) là lớp mới, có Cedar in-process. [D]
12. **Guardrails**: `BedrockModel(guardrail_id=, guardrail_version=, guardrail_trace=...)`; bị chặn thì `stop_reason == "guardrail_intervened"`; tin nhắn vào bị ghi đè trong lịch sử theo mặc định (`guardrail_redact_input=True`). [D]
13. **Prompt caching Bedrock**: `BedrockModel(model_id=..., cache_config=CacheConfig(strategy="auto"))`; TTL 5 phút hoặc 1 giờ (`ttl`, `system_prompt_ttl`, `tools_ttl`, `messages_ttl`); theo bảng Bedrock, Claude Haiku 5.5/Sonnet 5.5/Opus 5.5 cần tối thiểu **512 token** mỗi checkpoint, tối đa 4 checkpoint/request. `cache_prompt`/`cache_tools` đã deprecated. [D]
14. **AG-UI**: đặc tả 1.0 (SDK `ag-ui-protocol` 1.0.0), SSE là chính, event UPPER_SNAKE trên dây. Adapter chính thức: **`ag-ui-strands`** (`StrandsAgent`, `create_strands_app`, `StrandsAgentConfig`, `ToolBehavior`), nằm trong repo ag-ui-protocol/ag-ui, thư mục `integrations/aws-strands`. AgentCore Runtime hỗ trợ giao thức `AGUI`: cổng 8080, `POST /invocations`, `GET /ping`, container ARM64, header `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id`, auth SigV4 hoặc OAuth/JWT, lỗi thành `RUN_ERROR`. [D] + [R]
15. **Khối UI JSON xuống frontend**: khuyến nghị (suy ra từ mẫu chính thức) [?]: khối tất định đến từ **kết quả tool** (render theo `TOOL_CALL_RESULT`), khối do Composer ghép (`explain`, `options`, `confirm`) gửi bằng **`STATE_SNAPSHOT`** (phát lại được khi reload) kèm `CUSTOM` cho thứ tạm thời (tiến độ, trace_id). Không dùng A2UI cho MVP. **[Đã chạy thử 2026-11-21] Cần sửa**: `STATE_SNAPSHOT` từ tool async-generator (`yield {"state":...}`) và `STATE_DELTA` **bị `STATE_SNAPSHOT {}` cuối lượt xóa** (adapter không cập nhật `current_state` cho hai đường này); `state_from_result` thì giữ được. Cách chạy tốt nhất đã thử: tool async-generator + `ToolBehavior(tool_stream_event_handler=...)` phát **`ACTIVITY_SNAPSHOT`** (LLM chỉ thấy kết quả gọn); `ACTIVITY_SNAPSHOT`/`CUSTOM` **không nằm trong `MESSAGES_SNAPSHOT`** nên phải lưu khối phía server/DB để phát lại. Chi tiết và code: `spike-strands-agui-local.md` mục 2.5 và 3.1.

## 3. Chi tiết theo từng mục

### 3.1 Cơ bản Strands

**Phiên bản và cài đặt.** [R: PyPI] `pip install strands-agents` (1.65.0, Python >= 3.10). Phụ thuộc chính: `boto3`, `mcp>=1.23,<2.4`, `pydantic>=2.4`, `opentelemetry-*`. Extras đáng dùng: `strands-agents[otel]` (OpenTelemetry), `a2a`, `cedar`. Công cụ làm sẵn nay nằm ở `strands.vended_tools` (quickstart import `file_editor`, `notebook` từ đó); gói `strands-agents-tools` 0.9.0 vẫn còn trên PyPI. [D] https://strandsagents.com/docs/user-guide/sdk/quickstart/python/index.md

Lưu ý hạ tầng: repo SDK nay là monorepo `strands-agents/harness-sdk` (thư mục `strands-py`); tài liệu có thêm nhánh "harness" (agent hoàn chỉnh dựng sẵn) và "interventions". Đây là SDK `strands` bạn dùng, không phải harness. [R]

**Agent + Bedrock.** [D] Mặc định `Agent()` dùng Bedrock với Claude Sonnet 4.6 ở region của credentials (tài liệu hiện hành); luôn truyền `model_id` rõ ràng. Một số model cần tiền tố inference profile (`us.`, `eu.`, `global.`). Bảng cấu hình `BedrockModel`: `model_id`, `region_name`, `temperature`, `max_tokens` (đặt rõ khi tải cao: Bedrock giữ trước `input + max_tokens` trên quota TPM), `streaming`, `cache_config`, `guardrail_id`, `guardrail_version`, `guardrail_trace` (`enabled`/`disabled`/`enabled_full`), `guardrail_stream_processing_mode` (`sync`/`async`), `guardrail_redact_input` (mặc định True), `guardrail_redact_output` (mặc định False), `additional_request_fields` (thinking, effort), `boto_session`, `boto_client_config` (retry, `read_timeout`). Nguồn: https://strandsagents.com/docs/user-guide/sdk/model-providers/amazon-bedrock/index.md

Model có trong bảng prompt caching Bedrock hôm nay (đọc ở docs.aws.amazon.com): Claude Fable 5.2, Mythos 5.2 (gated), **Haiku 5.5**, **Sonnet 5.5**, **Opus 5.5** (ID gốc `anthropic.claude-haiku-5-5`, `anthropic.claude-sonnet-5-5`, `anthropic.claude-opus-5-5`; ví dụ tài liệu Strands dùng `global.anthropic.claude-sonnet-5-5`). [D] https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html Việc chọn model cụ thể cho router/orchestrator và kiểm tra khả dụng ở region của dự án thuộc mảng Bedrock, chưa kiểm ở đây.

**Định nghĩa tool.** [D] https://strandsagents.com/docs/user-guide/sdk/tools/custom-tools/index.md
- `@tool` tạo spec từ type hint và docstring (đoạn đầu = mô tả, phần `Args:` = mô tả tham số). Ghi đè bằng `@tool(name=..., description=..., inputSchema=...)`.
- Tool async chạy đồng thời. Tool là async generator thì mỗi `yield` là một `tool_stream_event`, giá trị yield cuối là kết quả.
- `@tool(context=True)` + tham số `tool_context: ToolContext` cho truy cập agent, `tool_use_id`, `invocation_state` (dữ liệu theo request như user id, không vào prompt) và `tool_context.interrupt(...)`.
- Tool ném exception thì model nhận kết quả lỗi và tự điều chỉnh (tài liệu lifecycle nói vậy; trang custom-tools không minh hoạ).

**Dùng tool MCP từ xa (AgentCore Gateway).**
- Cách trong tài liệu [D] https://strandsagents.com/docs/user-guide/sdk/tools/mcp-transports/index.md: `MCPClient(url="https://.../mcp", headers={"Authorization": f"Bearer {token}"})`; có `auth={"client_id","client_secret","scopes"}` cho OAuth client_credentials; IAM SigV4 qua gói `mcp-proxy-for-aws` (`aws_iam_streamablehttp_client`, `aws_service="bedrock-agentcore"`).
- Truyền thẳng `MCPClient` vào `Agent(tools=[client])` thì SDK tự quản vòng đời; cách thủ công là `with client: tools = client.list_tools_sync(); Agent(tools=tools)(...)` và **phải gọi agent bên trong `with`**. `tool_filters={"allowed": [...], "rejected": [...]}` (chuỗi hoặc regex), `prefix="gateway"` tránh đụng tên, `auto_reconnect=True` dựng lại phiên rớt và thử lại một lần. [D] https://strandsagents.com/docs/user-guide/sdk/tools/mcp-tools/index.md
- Mẫu FAST [R] https://github.com/awslabs/fullstack-solution-template-for-agentcore/blob/main/patterns/agui-strands-agent/tools/gateway.py : tạo token **bên trong lambda factory** để mỗi lần MCP kết nối lại có token mới:

```python
# Nguồn: FAST patterns/agui-strands-agent/tools/gateway.py (mcp==1.30.0)
from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp import MCPClient

def create_gateway_mcp_client(user_id: str) -> MCPClient:
    gateway_url = ...  # FAST đọc từ SSM
    return MCPClient(
        lambda: streamablehttp_client(
            url=gateway_url,
            headers={"Authorization": f"Bearer {get_gateway_access_token(user_id)}"},
        ),
        prefix="gateway",
    )
```
  Lưu ý: tài liệu Strands hiện nhắc tên `streamable_http_client` (trong `mcp.client.streamable_http`) còn FAST dùng `streamablehttp_client` với mcp 1.30.0; kiểm tên đúng theo bản `mcp` bạn ghim. [?] **[Đã chạy thử 2026-11-21]** Với `mcp 2.3.0` (bản mới nhất cài ra): chỉ có **`streamable_http_client`** (`from mcp.client.streamable_http import streamable_http_client`), **`streamablehttp_client` đã bị bỏ** (`AttributeError`), và chữ ký không còn `headers=` (header đặt trên `http_client`, hoặc dùng `MCPClient(url=..., headers=...)`). Mẫu FAST chỉ đúng khi ghim `mcp==1.30.0`. `FastMCP` cũng đổi thành `mcp.server.mcpserver.MCPServer` ở 2.x. Tên tool qua `MCPClient(prefix="gateway")` là **`gateway_<tên>`** (gạch dưới), còn `call_tool_sync` nhận tên gốc phía server (không tiền tố).
- Gọi tool trực tiếp không qua LLM (cho đường nhanh F3): `MCPClient` có `call_tool_sync(...)` và `call_tool_async(...)` (thấy trong mã nguồn `mcp_client.py`; chưa đọc chữ ký đầy đủ). [R]
- Tên tool qua Gateway thường có dạng `<target>___<tool>`; proposal viết `ledger.get_jar_balances` với dấu chấm. Chưa kiểm ở đây (thuộc mảng Gateway), nhưng cần thống nhất đặt tên để system prompt và Cedar khớp. [?]

**System prompt, model nhỏ/lớn.** Tạo hai đối tượng `BedrockModel` (nhỏ cho router/composer/Simulation, lớn cho orchestrator/analyst/roadmap) và truyền vào từng `Agent(model=...)`; `Agent(system_prompt=...)`. Không có khái niệm "model theo loại việc" riêng trong SDK. [D]

**Prompt caching.** [D] https://strandsagents.com/docs/user-guide/sdk/model-providers/amazon-bedrock-prompt-caching/index.md

```python
from strands import Agent
from strands.models import BedrockModel, CacheConfig

model = BedrockModel(
    model_id="global.anthropic.claude-sonnet-5-5",
    cache_config=CacheConfig(strategy="auto"),   # cache tools + system prompt + hội thoại
)
agent = Agent(model=model)
```
- `strategy="auto"`: điểm cache ở cuối system prompt và cuối tin nhắn user cuối (Claude). `system_prompt_ttl=False` nếu system prompt đổi mỗi request; TTL phải không tăng theo thứ tự tools → system → messages.
- Nội dung cache phải giữ nguyên giữa các request. Dưới ngưỡng token tối thiểu thì không cache. Trang Strands ghi 1.024 (Sonnet) và 4.096 (Haiku) nhưng bảng Bedrock hiện hành ghi **512** cho Haiku/Sonnet/Opus 5.5: tin bảng Bedrock, đo bằng số liệu. [D, hai nguồn lệch nhau]
- Đo: `result.metrics.accumulated_usage` có `cacheReadInputTokens`, `cacheWriteInputTokens`; trace OTel có `gen_ai.usage.cache_read.input_tokens`.
- Quan hệ với structured output: schema Pydantic biến thành tool nên nằm trong `tools`; schema cố định giữa các request thì nằm trong phần được cache. [?]

### 3.2 Structured output

Nguồn: https://strandsagents.com/docs/user-guide/sdk/agents/structured-output/index.md và https://strandsagents.com/docs/user-guide/sdk/agents/structured-output-behavior/index.md [D]

```python
# Nguồn: trang Structured output (cú pháp), schema là ví dụ của dự án
from pydantic import BaseModel, Field
result = agent(message, structured_output_model=TicketTriage)   # hoặc await agent.invoke_async(...)
obj = result.structured_output                                   # là instance của TicketTriage
```

- Cách hoạt động: Strands đổi schema thành một **tool** tên theo lớp Pydantic; model "trả object" bằng cách gọi tool đó; Strands validate, đạt thì kết thúc lượt, gỡ tool sau lệnh gọi. Mô tả trong `Field(description=...)` thành mô tả tham số tool, nên **đặt luật và hướng dẫn vào schema** hơn là vào prompt.
- Phạm vi theo lệnh gọi: schema chỉ áp cho lệnh gọi truyền nó. Cũng đặt được mặc định ở `Agent(structured_output_model=..., callback_handler=None)`; truyền theo lệnh gọi thì ghi đè.
- **Lỗi validate**: không ném. Lỗi (ví dụ ngày phải ở tương lai) trả về model như kết quả tool để nó gọi lại; viết thông điệp lỗi như chỉ dẫn (validator Pydantic với message rõ).
- **Model kết thúc bằng text mà không gọi tool**: Strands thử lại một lần với tool bị bắt buộc. Một số model Bedrock/Anthropic không ép được thì bỏ qua bước ép. Python thêm một tin user "You must format the previous response as structured output." (đổi bằng `structured_output_prompt`). Schema có `dict`/tuple/kiểu không định kiểu thì rơi xuống "best effort" kèm cảnh báo.
- **Giới hạn**: `limits={"structured_output_attempts": 3}`; vượt thì `stop_reason == "limit_structured_output_attempts"` và `structured_output` rỗng. Không đặt giới hạn mà ép lần cuối vẫn hỏng thì `StructuredOutputException` (`from strands.types.exceptions import StructuredOutputException`).
- **Đổi tên so với bản cũ?** Trang hiện hành chỉ nói về `structured_output_model` + `result.structured_output`. Phương thức cũ `agent.structured_output(Model, prompt)` **không được nhắc** trong hai trang trên; trang hook events còn nhắc `BeforeInvocationEvent.messages` là `None` khi bắn từ `structured_output`, nên phương thức cũ có vẻ còn tồn tại. Chưa tìm được thông báo deprecation; dùng API mới. [?] **[Đã chạy thử 2026-11-21]** Xác nhận: `agent.structured_output(Model, prompt)` và `structured_output_async` **còn chạy** nhưng phát `DeprecationWarning` ("pass in `structured_output_model` directly"). Dùng API mới.
- **Streaming**: `stream_async(..., structured_output_model=M)`: văn bản đến ở event `data`, object đến một lần ở event `result` cuối (`event["result"].structured_output`).
- **Sub-agent**: `Agent(structured_output_model=BillingResponse, ...)` làm specialist; với `as_tool(delegate=True)` orchestrator trả nguyên JSON có cấu trúc của specialist (không qua thêm một vòng model).
- Áp cho dự án: `IntentResult` (router, model nhỏ, không công cụ), `Plan`, `ScenarioSpec` (Simulation Agent), `Roadmap`, `Verdict`. Mỗi schema là model Pydantic **không có `dict`**; trường bảng tham số dùng `list[ParamItem]` hoặc các trường tường minh; `intent: Literal[...]`.

### 3.3 Streaming

Nguồn: https://strandsagents.com/docs/user-guide/sdk/streaming/events/index.md , https://strandsagents.com/docs/user-guide/sdk/streaming/async-iterators/index.md [D]

`async for event in agent.stream_async(prompt)`; event là `dict`, mỗi khoá là một loại:
- Vòng đời: `init_event_loop`, `start_event_loop`, `message` (tin nhắn mới), `event` (event thô của model), `force_stop` + `force_stop_reason`, `event_loop_throttled_delay`, `result` (`AgentResult`, có `stop_reason`, `structured_output`).
- Văn bản model: **`data`** (mẩu text), `delta` (delta thô), `reasoning` (+ `reasoningText`, `reasoning_signature`, `redactedContent`).
- Tool: **`current_tool_use`** (`toolUseId`, `name`, `input` đang tích luỹ), `tool_stream_event` (tool async-generator đẩy ra, có `tool_use` và `data`).
- Multi-agent (Graph/Swarm): `type` là `multiagent_node_start`, `multiagent_node_stream`, `multiagent_node_stop`, `multiagent_handoff`, `multiagent_result`.
- Đặt `callback_handler=None` để callback mặc định không in ra, vòng lặp của bạn điều khiển. Sub-agent chạy như tool: event của nó nổi lên **nguyên bản trong stream của orchestrator**. **[Đã chạy thử 2026-11-21]** Thứ tự thật cho lượt có tool: `init_event_loop, start, start_event_loop, event x3, current_tool_use(+delta,type="tool_use_stream"), event x3, message(assistant toolUse), message(user toolResult), start, start_event_loop, [event, data x N], event x3, message(assistant text), result`. Có khóa **`start`** không được tài liệu nhắc; event `data` mang theo cả `messages`, `model`, **`system_prompt`**, `tool_config` (lộ system prompt nếu serialize nguyên). `current_tool_use` đến một lần với `input` rỗng khi tool không tham số.

**Đẩy ra trình duyệt qua SSE.** Ví dụ FastAPI trong tài liệu trả `text/plain` dù tiêu đề ghi SSE (không đúng SSE). Hướng dẫn "Stream to the browser" https://strandsagents.com/docs/user-guide/sdk/streaming/streaming-to-the-browser-guide/index.md khuyên: **không serialize event Strands trực tiếp** (có thể chứa reasoning và input tool), dùng allowlist ánh xạ sang event công khai nhỏ (`text`, `redact`, `tool`, `final`), mỗi event có ID để `Last-Event-ID` phát lại (đệm 500 event), `: ping` mỗi 15 giây, tắt cache/buffer/nén, run tách khỏi kết nối trình duyệt, xác thực mọi route, dùng Redis Streams khi nhiều instance. Với dự án này, event công khai chính là **event AG-UI** (mục 3.7), nên tinh thần allowlist vẫn đúng: chỉ ánh xạ những gì cần ra ngoài.

Trên AgentCore Runtime: entrypoint `@app.entrypoint` là async generator `yield event` thì SDK stream ra [D https://strandsagents.com/docs/user-guide/sdk/deploy/deploy_to_bedrock_agentcore/python/index.md]; hoặc tự dựng FastAPI (mục 3.7).

### 3.4 Multi-agent

Nguồn: https://strandsagents.com/docs/user-guide/sdk/multi-agent/multi-agent-patterns/index.md [D]

Lời khuyên đầu tiên của tài liệu: **dùng một agent trước**; chỉ tách khi một prompt gánh quá nhiều việc, cần cô lập ngữ cảnh, hoặc cần lặp độc lập theo vai.

| Mẫu | Khi dùng (theo tài liệu) | Giới hạn | Áp cho Yofina |
|---|---|---|---|
| Agents-as-tools | Agent giao câu hỏi con cho chuyên gia, nhận câu trả lời gộp lại; bước nhỏ nhất trên một agent | Orchestrator tự quyết đường đi, không ép thứ tự | L2 → L3 (Analyst, Simulation, Roadmap, Ingestion) |
| Workflow trong code | Bước cố định, bạn tự gọi từng agent, chuyền kết quả, xử lý lỗi, tự vòng lặp | Bạn tự lập lịch song song | **Khung L0–L5, F3, vòng verifier** |
| Graph | Bạn nắm đường đi: tuần tự, nhánh song song, cạnh có điều kiện, vòng lặp | Cạnh điều kiện chỉ rẽ theo kết quả node, **lỗi thực thi không rẽ**; Python: node ném thì lệnh gọi graph ném; timeout kết thúc run | Tuỳ chọn cho luồng có STEP event |
| Swarm | Nhiều chuyên gia trao tay nhau, đường đi nổi lên từ công việc | Tuần tự, tự trị; `max_handoffs`=20, `max_iterations`=20, `execution_timeout`=900 s, `node_timeout`=300 s, `repetitive_handoff_detection_window` mặc định 0 | Không dùng |

Chi tiết cần biết:
- **Agents-as-tools** [D https://strandsagents.com/docs/user-guide/sdk/multi-agent/agents-as-tools/index.md]:

```python
# Nguồn: trang Choose a multi-agent pattern
from strands import Agent
weather_agent = Agent(name="weather_agent", description="Answers questions about the weather.",
                      system_prompt="You are a weather specialist.")
orchestrator = Agent(system_prompt="Route weather questions to weather_agent; answer the rest yourself.",
                     tools=[weather_agent])
```
  `name` và `description` của Agent thành tên/mô tả tool; `agent.as_tool(name=, description=, preserve_context=False, delegate=False)` để tuỳ biến. `preserve_context=True` giữ lịch sử specialist qua các lần gọi (cần session manager riêng cho interrupt). `delegate=True`: orchestrator trả nguyên đầu ra specialist, bỏ một vòng model; **phải là tool duy nhất trong lượt**, không dùng với model giữ hội thoại phía server. Không thấy giới hạn độ sâu lồng nhau trong tài liệu.
- **Graph** [D https://strandsagents.com/docs/user-guide/sdk/multi-agent/graph/index.md]: `GraphBuilder().add_node(agent, "id")`, `add_edge("a", "b", condition=fn)`, `set_entry_point`, `build()`. Giới hạn: `set_max_node_executions()`, `set_execution_timeout()`, `set_node_timeout()`, `reset_on_revisit(True)`. Nhiều cạnh vào một node: Python mặc định **OR** (chạy khi bất kỳ nguồn xong), muốn đợi tất cả phải gắn điều kiện kiểm trạng thái mọi nguồn. Node cùng nguồn, không phụ thuộc nhau thì chạy song song. `invocation_state` truyền ngữ cảnh (user id, cờ) không qua LLM và được giữ qua interrupt/resume. Node tuỳ biến tất định: kế thừa `MultiAgentBase`, cài `invoke_async`. Một Graph/Swarm có thể là node của Graph khác. Kết quả có `status`, `execution_order`, `results`, `accumulated_usage`.
  Repo ag-ui dặn: graph **dựng mới mỗi lần chạy** (factory), vì node agent giữ trạng thái và graph không snapshot/restore; dùng chung sẽ lẫn hội thoại giữa các request. [R]
- **Hạn chế khi chạy quá lâu**: trong Graph Python, `execution_timeout` chỉ kiểm tra trước mỗi lô node và không dừng node đang chạy. [D]
- **Router → orchestrator → specialist** [?]: tài liệu không có mẫu "router" riêng. Router chỉ là một `Agent` model nhỏ với `structured_output_model=IntentResult` được gọi bằng code trước; kết quả quyết định nhánh (đường nhanh một tool, hỏi lại, ngoài phạm vi, hay orchestrator đầy đủ).
- **Song song**: bước 1 của 10.1 (`get_forecast`, `get_obligations`, `get_fee_schedule`) song song được theo hai cách: (a) orchestrator phát ba `tool_use` trong một phản hồi (do prompt hướng dẫn; model có thể không làm), hoặc (b) code tự `asyncio.gather` gọi `call_tool_async` rồi đưa kết quả vào ngữ cảnh. (b) chắc chắn hơn và nhanh hơn. [?]
- **Giới hạn vòng/token** [D https://strandsagents.com/docs/user-guide/sdk/agents/lifecycle-controls/index.md]: `agent(prompt, limits={"turns": N, "output_tokens": N, "total_tokens": N})` (khoá là `turns`, không phải `max_turns`); kiểm tra ở đầu mỗi vòng lặp nên có thể vượt token một chút; reset mỗi lần gọi; thứ tự báo khi nhiều giới hạn cùng chạm: turns, total tokens, output tokens, structured output attempts. `cancel_signal=threading.Event()` hoặc `agent.cancel()` (hợp tác: kiểm tra trước khi chạy tool và ở biên vòng lặp; tool đã chạy phải tự kiểm). Quá giới hạn **kích thước đầu ra của một lần gọi model** ném `MaxTokensReachedException` (không phải stop reason). Lỗi throttling của model tự retry có backoff (đổi bằng retry strategy). Chưa rõ `limits` có tính cả token của sub-agent chạy như tool hay không (chỉ `structured_output_attempts` được nói rõ là tính cả sub-agent). [?]

### 3.5 Human in the loop

Nguồn: https://strandsagents.com/docs/user-guide/sdk/interrupts/index.md , https://strandsagents.com/docs/user-guide/sdk/agents/interventions/human-in-the-loop/index.md , https://strandsagents.com/docs/user-guide/sdk/agents/interventions/index.md [D]

**Ba cách, từ cao xuống thấp:**
1. **`HumanInTheLoop` (interventions)** gắn qua tuỳ chọn `interventions`: mặc định (không có `ask`) agent dừng với `stop_reason == "interrupt"` để app xử lý; `ask="stdio"` cho CLI; `ask=callable` (nhận chuỗi hỏi, trả lời người dùng) cho web/Slack. `allowed_tools` (tên cụ thể, `"*"`, hoặc `"!tên"` để buộc hỏi), `HumanInTheLoop("auto")` dùng bộ phân loại rủi ro (tài liệu cảnh báo "auto" có thể đổi ở bản minor, hãy ghim chiến lược), `enable_trust` ("t" để nhớ phê duyệt trong phiên). Handler tự viết: lớp con `InterventionHandler` trả `Proceed/Deny/Guide/Confirm/Transform` (`before_tool_call`, `after_tool_call`, `before_model_call`, `after_model_call`, `before_invocation`); `Deny` ngắt chuỗi; `on_error`: `"throw"` (mặc định), `"proceed"` (fail open), `"deny"` (fail closed: dùng cho handler bảo mật). Có Cedar in-process: https://strandsagents.com/docs/user-guide/sdk/agents/interventions/cedar-authorization/index.md (chưa đọc chi tiết).
2. **Hook interrupt**: `event.interrupt(name, reason={...})` trong callback `BeforeToolCallEvent` (một tool) hoặc `BeforeToolsEvent` (cả lô). Từ chối thì `event.cancel_tool = "lý do"` (hoặc `event.cancel = "..."` với lô).
3. **Interrupt trong tool**: `@tool(context=True)` + `tool_context.interrupt(name, reason={...})`. Không dùng được với `agent.tool.my_tool()` gọi trực tiếp.

```python
# Nguồn: trang Interrupts (rút gọn). Vòng dừng/tiếp tục:
result = agent(prompt)
while result.stop_reason == "interrupt":
    responses = []
    for interrupt in result.interrupts:        # mỗi cái có .name, .reason, .id
        answer = ask_user(interrupt.reason)    # lấy từ UI
        responses.append({"interruptResponse": {"interruptId": interrupt.id, "response": answer}})
    result = agent(responses)                  # tiếp tục: truyền danh sách thay cho prompt
```

Luật quan trọng [D]: tên interrupt của hook phải duy nhất trong cùng event (đặt tiền tố `yofina-`); `reason`/`response` phải JSON serializable; mỗi lúc chỉ một interrupt chờ trên một hook/tool; **khi resume, hook/tool chạy lại từ đầu** (đặt tác dụng phụ **sau** điểm interrupt); khi interrupt ở `BeforeToolCallEvent` thì `AfterToolCallEvent` không bắn cho tool đó nhưng `AfterToolsEvent` vẫn bắn và có thể bắn hai lần; interrupt cũng chạy trong Swarm/Graph (từ hook `BeforeNodeCallEvent` hoặc trong node).

**Session manager giữ trạng thái.** Server không giữ trạng thái (mỗi request một process) thì phải gắn `session_manager` để trạng thái interrupt sống qua request: ví dụ chính thức dùng `FileSessionManager(session_id=..., storage_dir=...)` rồi gọi lại `agent(responses)`. `agent.state` lưu được quyết định "tin cậy". [D] Các manager: `FileSessionManager`, `S3SessionManager` (`session_id`, `bucket`, `prefix`), `SnapshotSessionManager` (mới: lưu messages, state, conversation manager, **interrupt state**, model state, system prompt) và `AgentCoreMemorySessionManager` (gói `bedrock-agentcore`; kế thừa `RepositorySessionManager`). Đọc mã Strands: `RepositorySessionManager` có theo dõi `interrupt_state_version`, tức manager kiểu repository đồng bộ cả interrupt state. [R] Cảnh báo: **chưa tìm được** tài liệu nói `AgentCoreMemorySessionManager` khôi phục interrupt qua tiến trình khác; cần chạy thử (mục 5). Cảnh báo khác: manager không có khoá phân tán, hai agent cùng session id ghi đè nhau; multi-agent chỉ gắn manager ở orchestrator (Graph/Swarm), gắn cho agent bên trong thì Python ném `ValueError`. [D]

**Trên AgentCore Runtime.** Mỗi `runtimeSessionId` có một microVM riêng; mặc định `idleRuntimeSessionTimeout`=900 s, `maxLifetime`=28800 s (microVM), cấu hình qua `LifecycleConfiguration` khi tạo/cập nhật Runtime; hết hạn thì session có thể tiếp tục trên microVM mới (trạng thái trong bộ nhớ tiến trình mất). Mỗi microVM dùng đúng artifact tại thời điểm tạo. [D https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-lifecycle-settings.md] Hệ quả [?]: nếu người dùng bấm xác nhận trong vài phút, resume cùng `runtimeSessionId` rơi vào cùng microVM, trạng thái trong bộ nhớ còn (ag-ui-strands nói rõ: pause/resume trên cùng wrapper còn sống thì không cần SessionManager); để chịu được hết idle hoặc deploy mới thì phải có manager bền vững với `agent_id` ổn định, hoặc dùng thiết kế xác nhận ngoài vòng LLM (mục 6.3). Với AG-UI, frontend phải gửi lại **cùng** header `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` và **cùng `threadId`** khi resume.

**[Đã chạy thử 2026-11-21]** (thuần Strands + qua AG-UI, `FileSessionManager`): interrupt trong tool và `HumanInTheLoop` đều dừng với `stop_reason == "interrupt"` và tiếp tục bằng `[{"interruptResponse":{...}}]`; **code trước `interrupt()` chạy lại khi resume (xác nhận bằng log hai pid)**; interrupt state được ghi ở `agents/agent_<id>/agent.json` (`_internal_state.interrupt_state`) và resume trong **tiến trình mới** chạy được; không có session manager thì không resume được sau restart (`UNKNOWN_INTERRUPT_ID`). Xem `spike-strands-agui-local.md` mục 2.7.

Mẫu AG-UI cho interrupt xem 3.7.

### 3.6 Hooks, guardrail, observability

**Hooks** [D https://strandsagents.com/docs/user-guide/sdk/agents/hooks/index.md , https://strandsagents.com/docs/user-guide/sdk/agents/hooks-events/index.md]
- Đăng ký: `class X(HookProvider): def register_hooks(self, registry, **kw): registry.add_callback(EventClass, self.fn)`; `Agent(hooks=[X()])` hoặc `agent.hooks.add_hook(X())`; hàm rời `agent.add_hook(fn, order=HookOrder.SDK_FIRST)` (`SDK_FIRST`=-100, `DEFAULT`=0, `SDK_LAST`=100; Before chạy theo thứ tự đăng ký, After chạy ngược). Plugin: lớp `Plugin` + decorator `@hook`, `Agent(plugins=[...])`.
- Event ghi được: `BeforeToolCallEvent` (`cancel_tool`, `selected_tool`, `tool_use`), `AfterToolCallEvent` (`result` ghi được, `retry`, `exception` chỉ đọc), `BeforeToolsEvent` (`cancel`), `AfterToolsEvent` (`end_turn`), `AfterModelCallEvent` (`retry`), `BeforeInvocationEvent` (`messages`), `AfterInvocationEvent` (`resume`: gọi tiếp với input mới). Event multi-agent: `BeforeNodeCallEvent`, `AfterNodeCallEvent`, …
- Lệch tài liệu: có trang viết `event.tool_use.name`, trang khác `event.tool_use["name"]`; dùng dạng ngoặc vuông như ví dụ interrupts/interventions và kiểm khi chạy. [?]

**Verifier quanh tool call (L4)** [?, ghép từ API trên]:
- Một `HookProvider` giữ "sổ số" của lượt: ở `AfterToolCallEvent` ghi `(tool, input, result)`; sau khi Composer sinh khối UI thì code Python duyệt mọi con số trong `text` và `blocks` đối chiếu với sổ (NumericGrounding), chạy `planner.check_suitability`, ra `Verdict`.
- Sai thì trả lỗi có cấu trúc cho agent sửa, tối đa 2 vòng: đặt vòng lặp **trong code** (đếm vòng, rồi rơi xuống thẻ số tất định). `AfterInvocationEvent.resume` làm được trong hook nhưng khó đếm/ghi log hơn.
- `BeforeToolCallEvent.cancel_tool` để chặn tool vượt ngân sách số lần gọi (có mẫu cookbook "Limit Tool Counts").

**Guardrails** [D https://strandsagents.com/docs/user-guide/sdk/safety-security/guardrails/index.md]:
```python
BedrockModel(model_id=..., guardrail_id="...", guardrail_version="1", guardrail_trace="enabled")
```
- Tin nhắn vào bị chặn: mặc định thay nội dung tin user trong lịch sử (`guardrail_redact_input`, đổi thông điệp bằng `guardrail_redact_input_message`); đầu ra: `guardrail_redact_output` (mặc định tắt) + `guardrail_redact_output_message`. Phát hiện: `result.stop_reason == "guardrail_intervened"`.
- Chế độ "bóng" (chỉ ghi log, chưa chặn): hook gọi `ApplyGuardrail` ở `MessageAddedEvent` và `AfterInvocationEvent` để tinh chỉnh guardrail trước khi bật chặn; trùng ý "chạy chế độ chỉ ghi log trước" của proposal cho Cedar.
- `guardrail_stream_processing_mode` (`sync`/`async`): `sync` chờ guardrail đánh giá trước khi nhả chunk; ảnh hưởng ký tự đầu (NFR 1,5 giây). Trang guardrails của Strands không nói về tham số này; đặc tính của chế độ này thuộc tài liệu Bedrock, chưa đọc. [?]
- Che PII, prompt-attack, topic chứng khoán nằm ở cấu hình guardrail (mảng Bedrock, không thuộc báo cáo này). Automated Reasoning checks: chưa kiểm cách gắn vào Strands.

**Observability** [D https://strandsagents.com/docs/user-guide/sdk/observability-evaluation/traces/index.md]
- `pip install 'strands-agents[otel]'`; `StrandsTelemetry()` rồi `.setup_otlp_exporter()` / `.setup_console_exporter()` / `.setup_meter()`; hoặc dùng provider OTel đã cấu hình sẵn (Agent tự dùng). Biến: `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`, `OTEL_TRACES_SAMPLER(_ARG)`.
- Cấu trúc span: span agent → span cycle → span model (LLM) và span tool; thuộc tính `gen_ai.agent.name`, `gen_ai.request.model`, `gen_ai.tool.name`, `gen_ai.tool.call.id`, `tool.status`, `event_loop.cycle_id`, token (kể cả cache). `Agent(trace_attributes={"session.id": ..., "user.id": ...})` gắn thuộc tính lên span. Span riêng của dự án (router, verifier) tạo bằng `trace.get_tracer(__name__).start_as_current_span(...)`.
- Trên AgentCore: thêm `aws-opentelemetry-distro>=0.10.1` (AWS ghim `~=0.21.0` trong tutorial AG-UI), chạy `opentelemetry-instrument python agent.py`; truyền session id vào trace bằng OTEL baggage `session.id`; CloudWatch cần bật Transaction Search. [D https://strandsagents.com/docs/user-guide/sdk/deploy/deploy_to_bedrock_agentcore/python/index.md] Trong ví dụ FastAPI của AWS có `FastAPI(telemetry={"auto_configure": False})` để FastAPI không cấu hình exporter thứ hai. [D]
- Trả `trace_id` về giao diện: lấy từ span hiện tại (`opentelemetry.trace.get_current_span().get_span_context().trace_id`, định dạng hex) và lưu ánh xạ sang `audit_events`; `tr_8f2c` của proposal có thể là ID riêng của dự án. [?]

### 3.7 AG-UI

**Giao thức là gì.** [D https://docs.ag-ui.com/concepts/architecture] AG-UI (Agent User Interaction Protocol) là giao thức hướng sự kiện, nhẹ, giữa frontend và agent: agent phát chuỗi event chuẩn, client xử lý; truyền tải SSE (dễ debug) hoặc nhị phân HTTP, giao thức không bắt buộc kênh (cũng có WebSocket, webhook). Không phải đặc tả giao diện sinh động (generative UI): nó **chở** các đặc tả đó (A2UI của Google, Open-JSON-UI của OpenAI, MCP-UI) và cho phép định nghĩa chuẩn riêng. [D https://docs.ag-ui.com/concepts/generative-ui-specs] Phiên bản: SDK `ag-ui-protocol` 1.0.0 ra 2026-09-17 [R PyPI]; changelog nói 1.0 bổ sung `outcome` cho `RUN_FINISHED`, interrupt/resume, outcome `cancelled`, bỏ `THINKING_*` (thay bằng `REASONING_*`), thêm event subagent; bản nháp 1.1 chỉ thêm nhỏ. [D https://docs.ag-ui.com/spec/draft/changelog.md] (Một số trang khác trong docs vẫn gắn nhãn "draft" cho phần interrupt; nội dung 1.0 là thực tế hiện hành.)

**Danh sách event** [D https://docs.ag-ui.com/concepts/events] (tên trên dây là UPPER_SNAKE, ví dụ `RUN_STARTED`):
- Vòng đời: `RunStarted` (`threadId`, `runId`, `parentRunId?`, `input?`), `RunFinished` (`outcome?`, `result?`), `RunError` (`message`, `code?`), `StepStarted`/`StepFinished` (`stepName`).
- Tin nhắn text: `TextMessageStart` (`messageId`, `role`), `TextMessageContent` (`messageId`, `delta` khác rỗng), `TextMessageEnd`, `TextMessageChunk` (rút gọn).
- Tool call: `ToolCallStart` (`toolCallId`, `toolCallName`, `parentMessageId?`), `ToolCallArgs` (`delta`), `ToolCallEnd`, `ToolCallResult` (`messageId`, `toolCallId`, `content`, `role?`), `ToolCallChunk`.
- State: `StateSnapshot` (`snapshot`, thay toàn bộ), `StateDelta` (`delta` là JSON Patch RFC 6902), `MessagesSnapshot` (`messages`).
- Activity: `ActivitySnapshot`, `ActivityDelta`. Reasoning: `ReasoningStart/MessageStart/MessageContent/MessageEnd/MessageChunk/End`, `ReasoningEncryptedValue`.
- Subagent: `SubagentStarted/Finished/Error`. Đặc biệt: `Raw`, **`Custom`** (`name`, `value`, do ứng dụng định nghĩa). Nháp: `MetaEvent`.
- Hướng dẫn snapshot vs delta [D https://docs.ag-ui.com/concepts/state]: snapshot để dựng nền, khôi phục sau mất kết nối, thay đổi lớn; delta cho cập nhật nhỏ tần suất cao; không để dữ liệu nhạy cảm trong state; khi lệch thì xin snapshot mới.

**Đầu vào** `RunAgentInput`: `threadId`, `runId`, `messages`, `tools` (chỉ tool do **client** định nghĩa), `context`, `state`, `forwardedProps`, và (1.0) `resume`. [D https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-agui-protocol-contract.md , https://docs.ag-ui.com/concepts/tools]

**Interrupt/resume trong AG-UI** [D https://docs.ag-ui.com/concepts/interrupts]:
- `RUN_FINISHED` có `outcome`: bỏ trống hoặc `{type:"success"}` là hoàn tất; `{type:"interrupt", interrupts:[...]}` (không rỗng) là run dừng chờ người dùng.
- Mỗi interrupt: `id`, `reason` (lõi: `tool_call`, `input_required`, `confirmation`; tuỳ biến dạng `<framework>:<tên>`), `message?`, `toolCallId?` (bắt buộc khi `reason=tool_call`), `responseSchema?` (JSON Schema cho `resume.payload`), `expiresAt?`, `metadata?`, `subagentRunId?`.
- Tiếp tục = **một run mới cùng `threadId`**, `RunAgentInput.resume = [{interruptId, status: "resolved"|"cancelled", payload?}]`. Một mảng `resume` phải trả lời **mọi** interrupt đang mở (không resume từng phần); gửi lại cùng resume phải an toàn (idempotent); payload sai/hết hạn/id lạ thì `RunError`; trước khi interrupt agent phải phát `StateSnapshot` và `MessagesSnapshot` cần thiết. Từ chối đặt trong payload (ví dụ `{"approved": false}`), không phải status riêng.

**Adapter Strands chính thức: `ag-ui-strands`.** [R] https://pypi.org/project/ag-ui-strands/ , mã nguồn https://github.com/ag-ui-protocol/ag-ui/tree/main/integrations/aws-strands/python . Có thêm gói TypeScript `@ag-ui/aws-strands`. Trang tích hợp trong tài liệu Strands là cộng đồng/Python-only và chỉ giới thiệu CopilotKit [D https://strandsagents.com/docs/community/integrations/ag-ui/]. Tóm tắt API (từ README và mã nguồn):
- `StrandsAgent(agent=<Agent hoặc factory>, name=, description=, config=StrandsAgentConfig(...), hooks=[...], plugins=[...])`; `async for ev in agui_agent.run(run_input, invocation_state=...)`. Mỗi `thread` giữ một Agent riêng; run chồng nhau trên cùng thread bị từ chối `THREAD_BUSY`; thread còn interrupt chưa trả lời từ chối lượt mới `PENDING_INTERRUPTS`. Truyền **factory** (hàm tạo mới) cho Graph/Swarm.
- Truyền tải: `create_strands_app(agui_agent, "/invocations", "/ping", origins=[...], auth=dependency)` hoặc `add_strands_fastapi_endpoint(app, agui_agent, "/invocations")` + `add_ping(app, "/ping")`; route agent không có xác thực trừ khi truyền `auth`; mặc định CORS wildcard kèm `FutureWarning` (hãy truyền `origins` rõ); `invocation_state_provider(request, input_data)` cấp trạng thái request tin cậy cho hook/tool (lấy từ JWT đã xác thực, không lấy từ `forwarded_props`).
- `StrandsAgentConfig`: `tool_behaviors`, `state_context_builder`, `thread_agent_kwargs`, `session_manager_provider`, `emit_messages_snapshot`, `replay_history_into_strands`, `subagent_visibility` (`inline`/`attributed`/`hidden`), `a2ui`, …
- `ToolBehavior` (theo tên tool): `predict_state`, `state_from_args`, `state_from_result`, `custom_result_handler`, `tool_stream_event_handler`, `args_streamer`, `interrupt_on_call`, `continue_after_frontend_call`, `skip_messages_snapshot`, `stop_streaming_after_result`.
- **Ánh xạ** (ARCHITECTURE.md + mã): event có `data` → `TEXT_MESSAGE_*`; `current_tool_use` → `TOOL_CALL_START/ARGS/END`; `toolResult` → `TOOL_CALL_RESULT` rồi `MESSAGES_SNAPSHOT`; reasoning → `REASONING_*`; node Graph/Swarm → `STEP_STARTED/FINISHED` và event `CUSTOM` tên `MultiAgentHandoff` v.v.; event không ánh xạ → `RAW`; hook hỏng → `CUSTOM` `hook_error` mà không dừng run; tool async-generator `yield {"state": {...}}` → `STATE_SNAPSHOT`.
- **Interrupt**: `tool_context.interrupt()` trong tool → `RUN_FINISHED` với `outcome.type == "interrupt"` (mỗi interrupt Strands một `Interrupt` AG-UI); `ToolBehavior(interrupt_on_call=True)` sinh interrupt phê duyệt có `message`, schema `approved`, metadata `tool_name`, `tool_input`; resume bằng `resume=[{interruptId, status:"resolved", payload}]` trên cùng `thread_id`. Giá trị trả về của `interrupt()` bị **bọc**: `{"response": payload}` hoặc `{"cancelled": True}` (đọc bằng `.get("response")`, `.get("cancelled")`). Lại thêm kiểu "frontend tool chờ" (`continue_after_frontend_call=False`): run kết thúc bình thường sau `TOOL_CALL_*`, kết quả gửi lại như `ToolMessage`, không dùng `resume[]` (chỉ Python). Resume ở tiến trình khác cần `SessionManager` bền vững và `agent_id` ổn định. Tool chạy lại từ đầu sau resume. **[Đã chạy thử 2026-11-21]** Xác nhận hầu hết, kèm điểm khác: (1) `tool_context.interrupt(name, reason={...})` cho `outcome.interrupts[0]` có `reason == <name>` (không phải `"confirmation"`), dict `reason` nằm ở `metadata.reason`, **không có** `message`/`toolCallId`/`responseSchema`; (2) `interrupt_on_call=True` cho interrupt đầy đủ (`reason:"tool_call"`, `message`, `toolCallId`, `responseSchema {approved:boolean}`, `metadata.tool_input`) và **tool không chạy trước khi duyệt**, nên không dính bẫy chạy lại; (3) `{"response": payload}` / `{"cancelled": True}` đúng; (4) lỗi đường resume là `RUN_ERROR` (HTTP 200) mã `PENDING_INTERRUPTS`, `INTERRUPT_RESUME_ERROR`, `UNKNOWN_INTERRUPT_ID` (gửi lại resume đã xử lý cũng ra `UNKNOWN_INTERRUPT_ID`); (5) **`HumanInTheLoop` (interventions) không dùng được qua adapter**: payload luôn bị bọc `{"response": ...}` nên HITL trả `CONFIRMATION_FAILED` (fail-closed); (6) resume sau **restart tiến trình** chạy được với `FileSessionManager` (cả cách (1) và (2)).
- Hạn chế quan trọng (đọc mã): adapter **không xử lý riêng `structured_output_model`**; structured output chỉ dùng được ở các bước bạn tự gọi. [R, grep mã; ?] **[Đã chạy thử 2026-11-21] Cần sửa**: adapter **có chạy được** với `Agent(structured_output_model=...)` đặt ở hàm dựng (nó chép sang agent từng thread). Nhưng không xử lý riêng: object hiện ra chỉ như một tool call tên đúng bằng lớp Pydantic (`TOOL_CALL_START/ARGS/END`, `TOOL_CALL_RESULT` = "Successfully validated ... structured output"), không có event mang object, `RUN_FINISHED` không mang nó, model còn viết lời dẫn trước. Bắt được bằng `ToolBehavior` đặt theo tên lớp + `custom_result_handler` phát `CUSTOM` (mục 2.6 của file spike). Không có chỗ truyền model theo từng lượt.

**AgentCore Runtime hỗ trợ AG-UI.** [D https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-agui.md , https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-agui-protocol-contract.md]
- Release notes (mục tháng 3/2026): "Runtime: AG-UI Protocol Support" (stream text, reasoning, tool call, state sync, WebSocket hai chiều) và (mục tháng 4/2026) "AG-UI Partnership with CopilotKit" (AgentCore là nền tảng triển khai hạng nhất trong repo AG-UI). [D https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html]
- Hợp đồng: container ARM64, host `0.0.0.0`, cổng **8080** (hoặc `protocolConfiguration.port`), `POST /invocations` (SSE) hoặc `/ws` (WebSocket), `GET /ping` trả `{"status":"Healthy"}` hoặc `HealthyBusy` (giữ session sống; đừng đặt `time_of_last_update` = hiện tại mỗi lần ping). Runtime là **proxy** truyền nguyên payload `InvokeAgentRuntime`, lo xác thực (SigV4/OAuth 2.0), cách ly session, scale. Header `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` gắn tự động/bắt buộc ở client.
- CLI: `agentcore add runtime --protocol AGUI --authorizer-type CUSTOM_JWT --authorizer-configuration '{"customJwtAuthorizer":{"discoveryUrl":...,"allowedClients":[...]}}' --request-header-allowlist Authorization`; `agentcore dev` (chạy local cổng 8080), `agentcore build`, `agentcore deploy`.
- Lỗi: nền tảng trả mọi lỗi thành event `RUN_ERROR` (SSE) với mã `UNAUTHORIZED`/401, `ACCESS_DENIED`/403, `VALIDATION_ERROR`/400, `RATE_LIMIT_EXCEEDED`/429, `SESSION_BUSY`/409 (có `RetryableConflictException` cần tự retry backoff, client AG-UI không tự retry), `SERVICE_QUOTA_EXCEEDED`/429, `AGENT_ERROR`/200, `INTERNAL_ERROR`/500.
- FAST tự deploy pattern AG-UI bằng protocol `HTTP` (container tự phát event AG-UI) và dùng `BedrockAgentCoreApp` với `@app.entrypoint` yield dict `event.model_dump(mode="json", by_alias=True, exclude_none=True)`; khác biệt với `AGUI`: lỗi nền tảng thành `RUN_ERROR` thay vì mã HTTP. [R https://github.com/awslabs/fullstack-solution-template-for-agentcore/blob/main/docs/AGUI_INTEGRATION.md]
- Bài AWS ML Blog "Build generative UI for AI agents on Amazon Bedrock AgentCore with the AG-UI protocol" (https://aws.amazon.com/blogs/machine-learning/build-generative-ui-for-ai-agents-on-amazon-bedrock-agentcore-with-the-ag-ui-protocol/): **không đọc được nội dung** (WebFetch chỉ trả khung trang). Qua kết quả tìm kiếm: nói FAST v0.4.1 thêm template `agui-strands-agent`, AgentCore chạy như proxy trong suốt. Chưa xác nhận từng chi tiết. [?]

**Gửi khối UI dạng JSON xuống frontend: các lựa chọn.** Không có trang nào của docs.ag-ui.com đọc được nêu một cách "được khuyến nghị" duy nhất cho khối JSON tuỳ ý; các mẫu chính thức trong ag-ui-strands là:

| Cách | Cơ chế | Ưu | Nhược | Dùng cho |
|---|---|---|---|---|
| Kết quả tool (backend tool rendering) | `TOOL_CALL_RESULT` (+ `MESSAGES_SNAPSHOT`); frontend ánh xạ `toolCallName` → component | Không thêm code backend; khối đến ngay khi tool xong; đúng nguyên tắc "số do tool" | Gắn với hình dạng kết quả tool; vào lịch sử hội thoại | `forecast_timeline`, `obligation_impact` (kết quả `run_scenario`, `affordability_check`) |
| State (`STATE_SNAPSHOT`/`DELTA`) | tool async-generator `yield {"state": {...}}`, hoặc `state_from_args`/`state_from_result`, `PredictStateMapping` | Phát lại khi reload/kết nối lại, frontend đồng bộ hai chiều (`useCoAgent`) | State quay lại làm đầu vào lượt sau, cần `state_context_builder` để không nhồi vào ngữ cảnh | Khối do Composer ghép (`blocks[]` cuối cùng) |
| `CUSTOM` | `custom_result_handler` yield `CustomEvent(name=..., value=...)`; hoặc tự phát | Linh hoạt, không động vào state/lịch sử | Frontend phải tự xử lý; không tự phát lại | tiến độ, `trace_id`, cờ UI |
| A2UI/Open-JSON-UI | Đặc tả UI khai báo, adapter có `a2ui` | Chuẩn chung | Nặng, thêm phụ thuộc, chưa cần cho 5 loại khối | Bỏ qua cho MVP |

Khuyến nghị [?]: **kết hợp** (một) khối tất định lấy từ kết quả tool đến sớm (giảm độ trễ cảm nhận), (hai) bộ khối cuối `{"trace_id","intent","text","blocks":[...]}` gửi bằng một `STATE_SNAPSHOT` (khoá `composer`), (ba) `CUSTOM` cho tín hiệu tạm. Frontend ánh xạ `block.type` → component đúng hợp đồng JSON của proposal; thêm loại khối không phải đổi giao thức. Lưu ý `custom_result_handler` **cộng thêm** event của bạn, không thay `TOOL_CALL_RESULT` mặc định (đọc mã nguồn: handler chạy sau `state_from_result`). **[Đã chạy thử 2026-11-21]** Xác nhận bằng chạy thật: cả bốn đường (kết quả tool, `CUSTOM`, `ACTIVITY_SNAPSHOT`, `STATE_SNAPSHOT`/`STATE_DELTA`) phát được ở 1.0.4; `ctx.result_data` là dict đã parse. **Bác bỏ một phần**: khuyến nghị "`STATE_SNAPSHOT` cho khối cuối" có bẫy (xem mục 2 điểm 15); nên dùng `ACTIVITY_SNAPSHOT` qua `tool_stream_event_handler`. Bảng trên đúng về ưu/nhược, thêm: `ACTIVITY_SNAPSHOT`/`CUSTOM` không vào `MESSAGES_SNAPSHOT`.

### 3.8 Mẫu tối thiểu

**(a) Phần Strands: model, 1 tool, structured output.** Ghép từ [D] quickstart, custom-tools, structured-output; tên lớp là của dự án, **chưa chạy**.

```python
# strands_min.py — ghép từ tài liệu Strands (quickstart, custom-tools, structured-output)
from typing import Literal
from pydantic import BaseModel, Field
from strands import Agent, tool
from strands.models import BedrockModel, CacheConfig

SMALL = BedrockModel(model_id="global.anthropic.claude-haiku-5-5", temperature=0.0, max_tokens=512)
LARGE = BedrockModel(model_id="global.anthropic.claude-sonnet-5-5", temperature=0.1, max_tokens=2048,
                     cache_config=CacheConfig(strategy="auto"))
# (model_id Haiku 5.5 suy từ bảng Bedrock; kiểm tiền tố global./us. theo region)

class IntentResult(BaseModel):                       # không có trường dict
    intent: Literal["lookup", "what_if", "affordability", "roadmap", "ingest", "out_of_scope"]
    confidence: float = Field(ge=0, le=1)
    needs_clarification: bool = False
    clarification_question: str | None = None
    amount_vnd: int | None = Field(default=None, description="Số tiền VND, số nguyên")

@tool
def get_jar_balance(jar: str) -> dict:
    """Số dư một hũ.

    Args:
        jar: mã hũ, ví dụ an_uong
    """
    return {"jar": jar, "balance_vnd": 1_250_000}     # thực tế gọi Gateway/SQL

async def route(user_text: str) -> IntentResult:
    router = Agent(model=SMALL, system_prompt="Phân loại ý định tài chính. Chỉ trả IntentResult.",
                   tools=[], callback_handler=None)  # một Agent mỗi request
    result = await router.invoke_async(user_text, structured_output_model=IntentResult,
                                       limits={"turns": 2, "structured_output_attempts": 3})
    return result.structured_output                   # StructuredOutputException nếu không ra object

orchestrator = Agent(model=LARGE, system_prompt="...", tools=[get_jar_balance], callback_handler=None)
```

**(b) Phần AG-UI: stream ra SSE trên AgentCore Runtime.** Chép từ [D] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-agui.md (đã đọc đầy đủ), chỉ đổi `Agent` thành agent ở (a):

```python
# app/AguiAgent/main.py — nguồn: AWS docs "Deploy AG-UI servers" (rút gọn)
import os, uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from ag_ui_strands import StrandsAgent
from ag_ui.core import RunAgentInput
from ag_ui.encoder import EventEncoder

agui_agent = StrandsAgent(agent=orchestrator, name="yofina", description="Hũ nhìn trước")
app = FastAPI(telemetry={"auto_configure": False})

@app.post("/invocations")
async def invocations(input_data: dict, request: Request):
    encoder = EventEncoder(accept=request.headers.get("accept"))
    async def event_generator():
        run_input = RunAgentInput(**input_data)
        async for event in agui_agent.run(run_input):
            yield encoder.encode(event)
    return StreamingResponse(event_generator(), media_type=encoder.get_content_type())

@app.get("/ping")
async def ping():
    return JSONResponse({"status": "Healthy"})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
```
Thử cục bộ: `curl -N -X POST http://localhost:8080/invocations -H "Content-Type: application/json" -d '{"threadId":"t1","runId":"r1","state":{},"messages":[{"role":"user","content":"Hũ ăn uống còn bao nhiêu?","id":"m1"}],"tools":[],"context":[],"forwardedProps":{}}'` sẽ ra `RUN_STARTED`, `TOOL_CALL_*`, `TEXT_MESSAGE_CONTENT`, `RUN_FINISHED`. **[Đã chạy thử 2026-11-21]** Chạy được (bằng `create_strands_app` và `add_strands_fastapi_endpoint`; chưa chạy nguyên văn đoạn code này): 34 event gồm cả `STATE_SNAPSHOT`/`MESSAGES_SNAPSHOT`/`RAW` mà đoạn mô tả không liệt kê; dây là `data: {...}\n\n` không có `event:`/`id:`/ping; `GET /ping` trả `{"status":"healthy"}` **chữ thường** (hợp đồng AWS ghi `Healthy`). Thiếu xác thực: thêm `auth=` nếu dùng `create_strands_app`, hoặc dựa vào JWT authorizer của Runtime (cấu hình lúc `add runtime`).

**(c) Khối UI từ state** — mẫu chính thức "agentic generative UI" (rút gọn) [R https://github.com/ag-ui-protocol/ag-ui/blob/main/integrations/aws-strands/python/examples/server/api/agentic_generative_ui.py]:

```python
from ag_ui_strands import StrandsAgent, StrandsAgentConfig, ToolBehavior, PredictStateMapping

@tool
async def present_blocks(blocks: list[dict]) -> dict:   # (mẫu dùng List[Any]; kiểu dict ở tham số tool là ổn,
    """Hiển thị các khối UI."""                          #  chỉ schema structured_output mới nên tránh dict)
    yield {"state": {"composer": {"blocks": blocks}}}    # -> STATE_SNAPSHOT
    yield {"ok": True}                                   # giá trị cuối = kết quả tool

config = StrandsAgentConfig(tool_behaviors={"present_blocks": ToolBehavior(skip_messages_snapshot=True)})
```
Phần (c) là ghép của người viết từ mẫu; `skip_messages_snapshot` và cách phối hợp chưa kiểm. [?] **[Đã chạy thử 2026-11-21]** Cơ chế `yield {"state": ...}` từ tool async-generator **chạy** (ra `STATE_SNAPSHOT` trước `TOOL_CALL_RESULT`) nhưng `STATE_SNAPSHOT {}` cuối lượt ghi đè; đoạn `present_blocks` ở trên (LLM tự điền `blocks`) chưa chạy và đi ngược nguyên tắc "số do code dựng". Mẫu thay thế đã chạy: `spike-strands-agui-local.md` mục 3.1.

**(d) Lưu ý chung khi đóng gói** [R FAST]: tạo `Agent` + `StrandsAgent` **bên trong entrypoint mỗi request** (để MCP client và token Gateway luôn mới, session manager đúng), dùng `session_manager_provider` thay vì `session_manager` trên Agent mẫu ("A session_manager on the template Agent is ignored"), đặt `replay_history_into_strands=False` khi session manager giữ lịch sử, bọc `async for` trong try/except và phát `RunErrorEvent` khi lỗi.

## 4. Khuyến nghị cho Yofina

### 4.1 Ánh xạ harness L0–L5 sang Strands

| Tầng | Cấu trúc Strands/AG-UI cụ thể | Ghi chú |
|---|---|---|
| L0 Cổng vào | JWT authorizer của Runtime (`CUSTOM_JWT` + allowlist header `Authorization`); `BedrockModel(guardrail_id=...)` hoặc gọi `ApplyGuardrail` trong code trước khi vào model; `invocation_state_provider` rút `user_id` từ JWT đã xác thực | Tool chỉ đọc dữ liệu của chủ JWT: `user_id` đi bằng token Gateway (mẫu FAST `get_gateway_access_token(user_id)`), **không** để LLM điền |
| L1 Router | `Agent(model=SMALL, tools=[])` + `structured_output_model=IntentResult`, gọi bằng code, một Agent mỗi request; thiếu tham số thì `needs_clarification` | Không cần interrupt cho "hỏi lại 1 câu": kết thúc lượt bằng câu hỏi; interrupt `input_required` chỉ cần nếu muốn form có kiểu |
| L2 Orchestrator | `Agent(model=LARGE, tools=[specialist..., mcp_client])`, `limits=`, `cache_config`; `structured_output_model=Plan` ở lần gọi lập kế hoạch | Song song: prompt hướng dẫn hoặc code `asyncio.gather` + `call_tool_async` cho các lệnh đọc đã biết trước |
| L3 Specialist | 4 `Agent(name=, description=, callback_handler=None)` đặt vào `tools=`; Simulation dùng `structured_output_model=ScenarioSpec`; Roadmap dùng `Roadmap` | Cô lập ngữ cảnh là mặc định; `preserve_context=False` |
| L4 Verifier | Code Python + `HookProvider` ghi sổ số (`AfterToolCallEvent`); vòng tối đa 2 trong code; `Verdict` | `check_suitability` gọi qua Gateway |
| L5 Composer | `Agent(model=SMALL)` + structured output cho `text` + `blocks` (hoặc gộp vào khối); phát `STATE_SNAPSHOT`/`CUSTOM` | `trace_id` và nhãn "do AI tạo" thêm bằng code |
| Luồng cố định (F3) | **Hàm async tuần tự**: `affordability_check` qua `call_tool_async` → phát khối ngay → LLM nhỏ giải thích trong `asyncio.wait_for(…, 1.5)` có try/except | Không dùng Graph |
| Ghi dữ liệu | Đề xuất bằng khối `confirm`; thực thi ngoài vòng LLM (6.3) | |
| Quan sát | `StrandsTelemetry` hoặc `opentelemetry-instrument`; `trace_attributes={"session.id","user.id"}`; span riêng cho router/verifier | |

### 4.2 Hai cách nối AG-UI (chọn sớm)

**Cách A: bọc orchestrator bằng `StrandsAgent`** (mẫu 3.8b). Ít code (khoảng 15 dòng), được xử lý sẵn text/tool/state/interrupt/thread cache/reconcile. Nhưng router, verifier, composer và vòng sửa nằm *ngoài* Agent mà adapter điều khiển, nên khó chèn đúng chỗ (RUN_STARTED/RUN_FINISHED do adapter phát; không structured output).

**Cách B: tự viết generator pipeline phát event bằng `ag_ui.core` + `EventEncoder`** (như entrypoint của AWS doc nhưng thay `agui_agent.run`): `RunStarted` → `StepStarted("route")` → router → rẽ nhánh → stream orchestrator (ánh xạ `data` → `TextMessage*`, `current_tool_use` → `ToolCall*`) → verifier → `STATE_SNAPSHOT` composer → `RunFinished`. Linh hoạt, khớp L0–L5 và NFR (ký tự đầu < 1,5 s vì phát `RunStarted`/`StepStarted` ngay). Tốn công hơn: tự ánh xạ event và tự cài hợp đồng interrupt/resume AG-UI.

Khuyến nghị [?]: làm **A trong ngày đầu** để có luồng end-to-end với frontend (CopilotKit hoặc `@ag-ui/client` `HttpAgent`), rồi chuyển sang **B** cho đường chính khi gắn router/verifier. **[Đã chạy thử 2026-11-21]** Điều chỉnh: "Cách A" thực ra gói được cả structured output (đặt ở hàm dựng) và khối UI (`tool_stream_event_handler` -> `ACTIVITY_SNAPSHOT`) và interrupt/resume bền qua restart; Cách B chỉ cần khi cần router/verifier/composer ngoài vòng của adapter. Mã nguồn `ag_ui_strands/agent.py` là tài liệu tham chiếu tốt cho phần ánh xạ (8000 dòng, nhiều trường hợp biên: nên đọc có chọn lọc, không chép nguyên).

### 4.3 Chỗ proposal cần chỉnh hoặc làm rõ

1. **"Graph của Strands cho luồng cố định (F3)" mâu thuẫn với "LLM lỗi vẫn trả thẻ số"** (NFR độ tin cậy, §10.2). Graph Python không rẽ lỗi thực thi; node LLM ném exception thì cả graph hỏng. Nên đổi thành "workflow trong code (hàm tuần tự)"; giữ Graph chỉ khi cần event `STEP_*`/`multiagent_*` hoặc cho luồng không yêu cầu khả năng chịu lỗi.
2. **Cờ xác nhận cho tool ghi** (§9 Policy): nếu cờ là tham số tool do model sinh thì không phải bằng chứng người dùng đã bấm. Cần cờ/token do **server** gắn sau khi nhận `resume`/nút xác nhận (ví dụ token dùng một lần gắn bởi backend, hoặc claim trong JWT/header Gateway), và Cedar kiểm token đó. Cách cài cụ thể thuộc mảng Gateway/Policy; phía Strands, hook `BeforeToolCallEvent` sửa được `tool_use["input"]` nên chèn được từ server, nhưng cách nhất quán nhất là backend tự gọi tool ghi sau xác nhận. [?]
3. **"Composer trả một JSON duy nhất"** (§9): trên AG-UI văn bản đi theo `TEXT_MESSAGE_CONTENT` (stream) còn khối đi qua state/custom/tool result. JSON `{"trace_id","intent","text","blocks"}` vẫn dùng được như state cuối, nhưng đừng đợi Composer xong rồi mới stream chữ (NFR ký tự đầu 1,5 s).
4. **"Hỏi lại đúng 1 câu bằng interrupt"** (§10.1): làm được với interrupt AG-UI/Strands nhưng không bắt buộc; kết thúc lượt bằng câu hỏi (kèm `needs_clarification`) đơn giản và chịu được recycle microVM hơn. Interrupt chỉ đáng dùng khi muốn form có kiểu (`responseSchema`).
5. **Phiên bản trong đề xuất hạ tầng**: bỏ mọi ghim cũ (FAST: strands 1.48.0, ag-ui-strands 0.1.9; tài liệu AWS: ag-ui-strands 0.3.x). API đã thay đổi (1.0 có `resume`, `outcome`), ghim bản mới và chạy thử.
6. **Song song tool trong orchestrator** (§9 L2: "gọi specialist/tool song song"): với agents-as-tools việc song song là hành vi của model, không đảm bảo; các lệnh đọc đã biết trước nên song song bằng code. `delegate=True` không song song được.
7. **Giới hạn "ngân sách lượt"** (§9 quản lý ngữ cảnh): có sẵn `limits={"turns","output_tokens","total_tokens"}` theo lệnh gọi; ghi tên khoá thật vào thiết kế và rẽ theo `stop_reason`.
8. **Model**: nay có Claude Haiku 5.5/Sonnet 5.5/Opus 5.5 trên Bedrock; chọn lại model nhỏ/lớn theo bảng Bedrock, không theo cái tên trong proposal (nếu có).

## 5. Điều chưa chắc / cần chạy thử

1. `AgentCoreMemorySessionManager` có lưu và khôi phục **interrupt state** qua tiến trình/microVM khác không? Chưa tìm được tài liệu; mã cho thấy nó kế thừa `RepositorySessionManager` (có theo dõi interrupt state). Cần thử: gây interrupt, giết tiến trình, resume ở tiến trình mới. **[Đã chạy thử 2026-11-21]** Đã làm đúng kịch bản này với `FileSessionManager`: chạy được (mục 2.7 file spike). `AgentCoreMemorySessionManager`, `S3SessionManager` vẫn chưa thử; và khẳng định "cùng wrapper còn sống thì không cần SessionManager" cũng chưa thử riêng (chỉ thấy: không có manager + restart = `UNKNOWN_INTERRUPT_ID`).
2. Cách `ag-ui-strands` 1.0.4 cư xử với **`structured_output_model`** trên Agent mẫu, và với tool structured-output (tên theo lớp Pydantic): có phát `TOOL_CALL_*` gây nhiễu frontend không? Chưa kiểm. **[Đã chạy thử 2026-11-21]** Đã trả lời: chạy được, có phát `TOOL_CALL_*` với tên tool = tên lớp Pydantic và không có event mang object (xem mục 3.7, mục "Hạn chế quan trọng").
3. `limits=` có tính token của sub-agent chạy như tool và của các lượt retry không? Chưa rõ.
4. Tên đúng của factory transport MCP (`streamablehttp_client` vs `streamable_http_client`) theo bản `mcp` được ghim, và ký tự tên tool qua Gateway (dấu chấm, `___`). **[Đã chạy thử 2026-11-21]** Với `mcp 2.3.0`: tên đúng là `streamable_http_client`; tiền tố `MCPClient(prefix="gateway")` cho tên `gateway_<tên>`. Tên Gateway thật (`___`) vẫn chưa kiểm.
5. Ảnh hưởng `guardrail_stream_processing_mode` (`sync`/`async`) tới độ trễ ký tự đầu và tới việc phát text bị chặn; chưa đọc tài liệu Bedrock tương ứng.
6. Mức song song thực tế của `ConcurrentToolExecutor` (không có tham số giới hạn): thử với 3 tool Gateway, đo.
7. CORS khi trình duyệt gọi **trực tiếp** endpoint AgentCore Runtime (header `Authorization` + `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id`): chưa tìm được. FAST và release notes có OAuth cho WebSocket từ trình duyệt; với SSE nên thử, nếu CORS chặn thì cần một lớp trung gian (proxy). **[Đã chạy thử 2026-11-21]** Chỉ kiểm local: `create_strands_app(origins=[...], allow_headers=[...])` trả preflight 200 với đúng các header đó, origin/header lạ bị 400, luồng SSE có `access-control-allow-origin` + `cache-control: no-cache`, không có `x-accel-buffering`. Trên AgentCore thật vẫn chưa biết. Frontend nên dùng `fetch`-based client (`@ag-ui/client` `HttpAgent`), không dùng `EventSource` (không đặt được header).
8. Bài AWS ML Blog về AG-UI + AgentCore: không đọc được nội dung (chỉ khung trang); cần mở thủ công để đối chiếu.
9. Lệch tài liệu: `event.tool_use.name` vs `event.tool_use["name"]`; ngưỡng token cache Strands (1.024/4.096) vs Bedrock (512).
10. Tương tác `Confirm`/`HumanInTheLoop` mới với adapter ag-ui-strands: adapter nói về `tool_context.interrupt` và `interrupt_on_call`; interventions mới (Strands >= ~1.6x) chưa thấy được nhắc. Cần thử trước khi dựa vào. **[Đã chạy thử 2026-11-21]** Đã thử: `HumanInTheLoop` hiện interrupt qua adapter nhưng **resume hỏng** (payload bị bọc `{"response":...}` -> `CONFIRMATION_FAILED`, tool không chạy). Dùng `interrupt_on_call` hoặc `tool_context.interrupt`.
11. Strands nhắc các Agent "harness", "Box", Cedar in-process, Dogwood: đã thấy trong `llms.txt` nhưng chưa đọc kỹ (Cedar authorization chỉ biết tồn tại). Có thể là lớp thứ hai bên cạnh Cedar tại Gateway.
12. **[Đã chạy thử 2026-11-21]** Phần (a) đã chạy với biến thể (model Haiku 4.5 ở `ap-southeast-1`; `IntentResult` chạy nguyên văn; chưa thử `CacheConfig`), (c) đã thay bằng mẫu khác chạy được; `ag_ui.core` có `CustomEvent`, `ActivitySnapshotEvent`, `ActivityDeltaEvent`, `StateDeltaEvent`, `ToolCallResultEvent`... (đủ 31 loại `EventType`). Mọi đoạn code ghép (mục 3.8 a, c) chưa chạy [bản gốc]; tên lớp event của `ag_ui.core` ngoài các tên đã thấy trong mã nguồn (`TextMessageEndEvent`, `StateSnapshotEvent`, `MessagesSnapshotEvent`, `StepFinishedEvent`, `CustomEvent`, `RunErrorEvent`) chưa kiểm.

## 6. Nguồn (truy cập 2026-11-21)

Strands (tài liệu, `.md` là bản Markdown của cùng trang):
- Mục lục: https://strandsagents.com/llms.txt
- Quickstart: https://strandsagents.com/docs/user-guide/sdk/quickstart/python/index.md
- Structured output: https://strandsagents.com/docs/user-guide/sdk/agents/structured-output/index.md ; hành vi: https://strandsagents.com/docs/user-guide/sdk/agents/structured-output-behavior/index.md
- Streaming: https://strandsagents.com/docs/user-guide/sdk/streaming/async-iterators/index.md ; events: https://strandsagents.com/docs/user-guide/sdk/streaming/events/index.md ; trình duyệt: https://strandsagents.com/docs/user-guide/sdk/streaming/streaming-to-the-browser-guide/index.md
- Multi-agent: https://strandsagents.com/docs/user-guide/sdk/multi-agent/multi-agent-patterns/index.md ; graph: .../multi-agent/graph/index.md ; swarm: .../multi-agent/swarm/index.md ; agents-as-tools: .../multi-agent/agents-as-tools/index.md
- Interrupts: https://strandsagents.com/docs/user-guide/sdk/interrupts/index.md ; HITL: https://strandsagents.com/docs/user-guide/sdk/agents/interventions/human-in-the-loop/index.md ; interventions: https://strandsagents.com/docs/user-guide/sdk/agents/interventions/index.md
- Session: https://strandsagents.com/docs/user-guide/sdk/agents/session-management/index.md
- Hooks: https://strandsagents.com/docs/user-guide/sdk/agents/hooks/index.md ; events: https://strandsagents.com/docs/user-guide/sdk/agents/hooks-events/index.md
- Lifecycle/limits: https://strandsagents.com/docs/user-guide/sdk/agents/lifecycle-controls/index.md ; executors: https://strandsagents.com/docs/user-guide/sdk/tools/executors/index.md ; custom tools: https://strandsagents.com/docs/user-guide/sdk/tools/custom-tools/index.md
- MCP: https://strandsagents.com/docs/user-guide/sdk/tools/mcp-tools/index.md ; transports: https://strandsagents.com/docs/user-guide/sdk/tools/mcp-transports/index.md
- Bedrock model: https://strandsagents.com/docs/user-guide/sdk/model-providers/amazon-bedrock/index.md ; caching: https://strandsagents.com/docs/user-guide/sdk/model-providers/amazon-bedrock-prompt-caching/index.md ; guardrails: https://strandsagents.com/docs/user-guide/sdk/safety-security/guardrails/index.md
- Observability: https://strandsagents.com/docs/user-guide/sdk/observability-evaluation/traces/index.md
- Deploy AgentCore: https://strandsagents.com/docs/user-guide/sdk/deploy/deploy_to_bedrock_agentcore/python/index.md
- Tích hợp AG-UI (cộng đồng): https://strandsagents.com/docs/community/integrations/ag-ui/
- Mã nguồn SDK (monorepo): https://github.com/strands-agents/harness-sdk (`strands-py/src/strands/session/repository_session_manager.py`, `strands-py/src/strands/tools/mcp/mcp_client.py`)

AG-UI:
- Events: https://docs.ag-ui.com/concepts/events ; Interrupts: https://docs.ag-ui.com/concepts/interrupts ; State: https://docs.ag-ui.com/concepts/state ; Tools: https://docs.ag-ui.com/concepts/tools ; Kiến trúc: https://docs.ag-ui.com/concepts/architecture ; Generative UI specs: https://docs.ag-ui.com/concepts/generative-ui-specs ; Changelog: https://docs.ag-ui.com/spec/draft/changelog.md
- Repo: https://github.com/ag-ui-protocol/ag-ui (`integrations/aws-strands/python`: README.md, ARCHITECTURE.md, `src/ag_ui_strands/{agent,config,endpoint}.py`, `examples/server/api/{agentic_generative_ui,backend_tool_rendering,interrupt,multi_agent}.py`)
- PyPI: https://pypi.org/project/ag-ui-strands/ ; https://pypi.org/project/strands-agents/ ; https://pypi.org/project/ag-ui-protocol/ ; https://pypi.org/project/bedrock-agentcore/

AWS:
- Deploy AG-UI servers: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-agui.md
- AG-UI protocol contract: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-agui-protocol-contract.md
- Lifecycle settings: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-lifecycle-settings.md
- Strands + AgentCore Memory: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/strands-sdk-memory.md
- Release notes: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html (mục "Runtime: AG-UI Protocol Support" và "Integrations: AG-UI Partnership with CopilotKit")
- Bedrock prompt caching (bảng model): https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html
- Blog (chưa đọc được nội dung): https://aws.amazon.com/blogs/machine-learning/build-generative-ui-for-ai-agents-on-amazon-bedrock-agentcore-with-the-ag-ui-protocol/

Repo FAST (mẫu tham khảo, không kéo về):
- https://github.com/awslabs/fullstack-solution-template-for-agentcore (`patterns/agui-strands-agent/{agent.py,requirements.txt,tools/gateway.py}`, `docs/AGUI_INTEGRATION.md`)
