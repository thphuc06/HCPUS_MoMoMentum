# UI/UX best practice cho hệ agentic + generative UI từ JSON

> Ghi chú nghiên cứu cho Yofina Foresight. Truy cập nguồn ngày **2026-11-21**. Lĩnh vực này đổi theo tháng: mọi tên hook, phiên bản, giấy phép bên dưới cần đối chiếu lại trước khi `npm install`.
>
> Quy ước nhãn nguồn dùng xuyên suốt:
> - **[CT]** đã đọc trong tài liệu chính thức / repo chính thức (qua WebFetch, nội dung do công cụ tóm tắt lại, không phải đọc nguyên văn từng dòng).
> - **[BLOG]** blog, bài viết, bài của bên thứ ba.
> - **[ĐX]** đề xuất của người viết ghi chú này, chưa chạy thử.
> - **[?]** chưa kiểm chứng được / chưa tìm được.

## 1. Câu hỏi cần trả lời

1. Các cách làm generative UI hiện nay (danh mục cố định + JSON `type`; tool call ánh xạ component; đặc tả khai báo A2UI / json-render / Open-JSON-UI / MCP Apps / Thesys; HTML tự do), so sánh, và cách nào hợp Yofina (AG-UI + Strands + AgentCore).
2. Phía frontend của AG-UI: SDK, các loại event, dựng UI dần khi stream; CopilotKit (runtime, giấy phép) so với assistant-ui so với client mỏng tự viết; bài AWS ML Blog nói gì.
3. Thiết kế hợp đồng JSON cho khối UI: union phân biệt theo `type`, versioning, validate hai đầu, fallback khối lạ, render khi JSON stream dở, nguồn số liệu, khối tương tác gửi ngược về agent; bộ `type` cụ thể + schema phác thảo.
4. Mẫu UX agentic: tiến trình tool, streaming, human-in-the-loop cho đổi số dư, hỏi lại, minh bạch, lỗi, chỗ đặt chat, gợi ý câu hỏi, nhắc chủ động.
5. Riêng tài chính: app ngân hàng/fintech thật làm gì, nên tránh gì.
6. An toàn: không render HTML của model, sanitize, giới hạn hành động của khối UI.

## 2. Kết luận ngắn: làm thế này

1. **Chọn cách (a)+(b) gộp: danh mục khối cố định, mỗi khối có `type`, frontend giữ bảng `type → component`; khối đến qua event AG-UI, không dùng A2UI / json-render / MCP Apps / HTML tự do trong MVP.** Lý do cốt lõi: số liệu phải do tool tất định tạo, LLM không được "thiết kế" giao diện chứa số. (§3.6)
2. **Khối mang số do code backend dựng, không phải do LLM viết.** Tool tất định trả `result`; một lớp "block builder" bằng Pydantic dựng khối từ `result`; LLM chỉ chọn gọi tool nào và viết lời. LLM chỉ được tạo trực tiếp một số khối không chứa số liệu tài chính (`options`, `clarify`, câu hỏi tiếp theo), và các khối đó đi qua validator. (§5.3)
3. **Chỉnh hợp đồng của proposal**: "một JSON duy nhất `{trace_id, intent, text, blocks[]}`" không khớp với cách AG-UI + Strands phát dữ liệu (event rời, văn bản và khối đến lệch thời điểm). Giữ JSON đó làm **bản ghi cả lượt** (lưu DB, phát lại lịch sử, đường dự phòng tất định), còn trên đường truyền thì **mỗi khối là một event**. (§6.2)
4. **Frontend: client mỏng tự viết trên `@ag-ui/client` (`HttpAgent` + `AgentSubscriber`) + store (zustand) + registry `type → component`.** Không bắt buộc CopilotKit: tài liệu CopilotKit ghi `selfManagedAgents` (kết nối thẳng tới agent AG-UI không qua runtime) thuộc gói Enterprise "Intelligence"; còn đi qua CopilotKit Runtime thì phải dựng thêm một Lambda Node. assistant-ui là phương án dự phòng nếu muốn có sẵn khung thread/composer. (§4.4)
5. **Hiển thị khối "đến trước chữ" bằng skeleton theo `TOOL_CALL_START`**, thay bằng khối thật khi có kết quả. Khối do server dựng thì đến nguyên vẹn, không cần xử lý partial JSON; partial JSON chỉ cần cho khối do LLM viết (`TOOL_CALL_ARGS`). (§5.4)
6. **Contract hai đầu: Pydantic là nguồn sự thật, xuất JSON Schema, sinh Zod/TS; kèm bộ fixtures JSON dùng chung để CI kiểm cả hai phía.** Server `extra="forbid"`; client bỏ qua khóa lạ nhưng nghiêm ngặt với `type`/`v`/trường bắt buộc. Khối không nhận ra hoặc `v` cao hơn hỗ trợ → render `fallback_text`. (§5.1, §5.2)
7. **Tiền là số nguyên đồng (`*_vnd: int`), ngày ISO 8601, xác suất 0–1; định dạng hiển thị (1.200.000đ, "1,2 triệu") làm ở client.** Evaluator `NumericGrounding` phải chuẩn hóa được cả cách viết tiếng Việt. (§5.3)
8. **Đổi số dư = Intent Preview → xác nhận → biên nhận → hoàn tác được (nếu thuộc loại đảo ngược được).** Dùng interrupt của AG-UI (`RUN_FINISHED.outcome = interrupt`, resume bằng `resume[]`); Strands adapter có hỗ trợ (`interrupt_on_call`). Nút bấm chỉ gửi `interruptId` + quyết định; server phát và kiểm token xác nhận gắn với hash tham số, một lần dùng, có hạn. (§6.4)
9. **Hỏi lại tối đa một câu**, kèm chip trả lời nhanh và giả định hiển thị; với việc rủi ro thấp thì ưu tiên "giả định rõ ràng + nút đổi" thay vì chặn người dùng bằng câu hỏi. (§6.5)
10. **Minh bạch ở ba lớp**: nhãn "Do AI tạo" cố định ở header chat và chip nhỏ trên khối; bảng "Vì sao" (dữ liệu đã dùng kèm thời điểm, luật đã kiểm, độ tin cậy dạng nhóm cao/vừa/thấp + lý do, độ phủ dữ liệu); `trace_id` ở chân bảng cho giám khảo. Tránh hiển thị độ tin cậy dạng phần trăm do LLM đưa ra (PAIR cảnh báo). (§6.6)
11. **Suy giảm có kiểm soát theo bậc**: thử lại một lần → hiển thị phần đã có + `notice` → LLM lỗi/chậm thì khối tất định + câu mẫu do server dựng → agent không với tới được thì màn Home vẫn dùng được (số liệu Home lấy bằng REST, không qua LLM). Không bao giờ để bong bóng trống. (§6.7)
12. **Chat là bottom sheet toàn chiều cao mở từ thanh "Hỏi Yofina" cố định ở Home, cộng điểm vào theo ngữ cảnh ở từng màn hình** (chi tiết hũ, màn chuyển tiền). Ngữ cảnh màn hình truyền qua `state`, không qua `context` (adapter Strands bỏ qua `context`). (§6.8)
13. **Gợi ý câu hỏi sinh từ trạng thái tất định** (hũ sắp cạn, nghĩa vụ sắp đến hạn), không để LLM nghĩ ra chip ở màn hình đầu. (§6.8)
14. **An toàn UI: không có `dangerouslySetInnerHTML`; text hiển thị dạng text node hoặc markdown tối giản (không HTML thô, không ảnh, không link ngoài allowlist); khối chỉ mang `action_id` do server đăng ký, không bao giờ mang URL hay tên tool; CSP chặt.** (§8)
15. **Làm 4 spike trong tuần 1** trước khi khóa kiến trúc: (i) `ToolBehavior.custom_result_handler` có phát được `ActivitySnapshot`/`CUSTOM` không; (ii) trình duyệt gọi thẳng AgentCore (JWT + CORS + header session id); (iii) interrupt end-to-end với Strands; (iv) fixtures Pydantic↔Zod. (§9)

## 3. Các cách làm generative UI và so sánh

### 3.1 Bản đồ chung

CopilotKit chia thành ba nhóm theo mức "agent được tự do đến đâu" [BLOG, tác giả CopilotKit, đăng 2026-01-29, sửa 2026-03-11] ([dev.to](https://dev.to/copilotkit/the-developers-guide-to-generative-ui-in-2026-1bh3)); trang tài liệu CopilotKit cũng dùng cách chia này [CT] ([docs.copilotkit.ai/generative-ui/specs](https://docs.copilotkit.ai/generative-ui/specs)):

| Nhóm | Ai sở hữu giao diện | Ví dụ |
|---|---|---|
| Controlled / static | Frontend sở hữu component; agent chọn component nào và điền dữ liệu | `useComponent`, `useRenderTool`, `useFrontendTool` (CopilotKit); tool UI (assistant-ui); tool parts (AI SDK) |
| Declarative | Agent trả mô tả giao diện có cấu trúc; frontend vẽ bằng danh mục của mình | A2UI, Open-JSON-UI, json-render |
| Open-ended | Agent trả cả bề mặt giao diện (HTML/iframe); frontend chỉ chứa | MCP Apps / MCP-UI, "Open Generative UI" của CopilotKit |

AG-UI **không phải đặc tả giao diện**; nó là lớp vận chuyển hai chiều giữa agent và app và "natively supports" cả ba nhóm [CT] ([docs.ag-ui.com/concepts/generative-ui-specs](https://docs.ag-ui.com/concepts/generative-ui-specs)).

### 3.2 Bảng so sánh

| Cách | Trạng thái hiện hành (đã đọc) | Mức chín | An toàn | Hợp AG-UI + Strands + AgentCore? |
|---|---|---|---|---|
| **(a) Danh mục cố định + JSON có `type`** (hợp đồng của proposal) | Là một mẫu thiết kế, không phải thư viện. Về bản chất trùng với "controlled" của CopilotKit | Cao: kỹ thuật cũ, không phụ thuộc thư viện | Cao nhất: agent chỉ chọn trong tập đã biết, dữ liệu đi qua schema | **Rất hợp.** Khối đi qua `TOOL_CALL_RESULT`, `ACTIVITY_SNAPSHOT/DELTA`, `STATE_*` hoặc `CUSTOM`. Không cần thư viện thứ ba |
| **(b) Tool call → component** | CopilotKit: `useComponent`, `useRenderTool`, `useHumanInTheLoop` (đọc được `useComponent` và `useRenderTool` ở docs; `useHumanInTheLoop` trong bài blog CopilotKit) [CT/BLOG]. assistant-ui: `makeAssistantToolUI` [CT, README]. AI SDK: tool part `tool-<name>` với state `input-available` / `output-available` / `output-error` [CT] | Cao: cơ chế phổ biến nhất | Cao: agent chỉ chọn tên tool và tham số theo schema | CopilotKit và assistant-ui **đọc thẳng event `TOOL_CALL_*` của AG-UI**. AI SDK có giao thức stream riêng (UI message stream), **không nói AG-UI**, nên ghép với Strands/AgentCore cần adapter tự viết: không khuyến nghị |
| **(c1) A2UI** | Google, **v1.0** (spec "v1.0-a2ui"), Apache-2.0, ~17,7k sao, roadmap ghi protocol v1.1 đang thu thập yêu cầu; renderer React/Lit/Angular/Flutter/SwiftUI; catalog Basic gồm Text, Card, Row, Column, List, Tabs, Modal, Button, TextField, ChoicePicker, Slider... Catalog VegaChart ghi "chưa publish" [CT] ([a2ui.org](https://a2ui.org/), [spec v1.0](https://a2ui.org/specification/v1.0-a2ui/), [github.com/google/A2UI](https://github.com/google/A2UI)) | Trung bình: v1.0 mới, hệ sinh thái đang hình thành. Một người dùng AWS Community Builders gọi nó "tricky" khi ghép với Strands: khó cân độ hạt của component, adapter Strands bỏ qua `context` nên phải nhét hướng dẫn qua Strands Skill [BLOG] ([dev.to](https://dev.to/aws-builders/a2ui-x-ag-ui-building-an-ai-agent-that-supports-a2ui-v09-with-copilotkit-and-strands-agents-37k1)) | Cao: truyền dữ liệu khai báo, không mã chạy được; hàm có `allowedCallers`, `requiresUserActivation`; regex bị giới hạn [CT] | Hợp về vận chuyển: A2UI nêu AG-UI là một binding; CopilotKit mang A2UI qua activity event (`a2ui-surface`) [BLOG]. Nhưng LLM phải sinh cả cấu trúc giao diện, trong khi Yofina cần số do tool tạo |
| **(c2) json-render** (Vercel Labs) | Apache-2.0, ~19,8k sao; catalog định nghĩa bằng Zod; LLM sinh spec phẳng `root` + `elements`; stream bằng JSONL patch RFC 6902; renderer React, Vue, Svelte, React Native... [CT] ([github](https://github.com/vercel-labs/json-render), [docs streaming](https://json-render.dev/docs/streaming)). Không thấy số phiên bản ổn định trên trang đã đọc | Trung bình-thấp: dự án nằm ở "vercel-labs"; **[?]** chưa thấy tài liệu về fallback cho `type` lạ | Trung bình-cao: giới hạn trong catalog | Không có tích hợp AG-UI/Strands được ghi nhận trong tài liệu đã đọc [?]. Có thể bọc qua `ACTIVITY_*` |
| **(c3) Open-JSON-UI** | "Chuẩn hóa mở của schema khai báo nội bộ của OpenAI" [BLOG/CT repo CopilotKit/generative-ui] | **[?]** chưa tìm được tài liệu đặc tả riêng | Như (c) | AG-UI nêu hỗ trợ; ít thông tin hơn A2UI |
| **(c4) Thesys C1 → OpenUI** | `docs.thesys.dev` hiện **chuyển hướng** sang openui.com; "OpenUI Lang" gọn hơn JSON, Gateway là API **được host**; trang không nêu giấy phép [CT] ([openui.com/docs](https://www.openui.com/docs)) | Thấp-trung bình, đổi thương hiệu gần đây | **[?]** | Không khuyến nghị: phụ thuộc dịch vụ ngoài AWS, trái ràng buộc "toàn bộ trên AWS" của proposal |
| **(c5) MCP Apps / MCP-UI** | Phần mở rộng của MCP, spec ngày 2026-01-26; tool khai báo `_meta.ui.resourceUri` tới tài nguyên `ui://` (HTML), host render trong **iframe sandbox**, giao tiếp JSON-RPC qua `postMessage`; được Claude, VS Code Copilot, Microsoft 365 Copilot, Goose... hỗ trợ [CT] ([modelcontextprotocol.io/extensions/apps/overview](https://modelcontextprotocol.io/extensions/apps/overview)) | Trung bình: chuẩn có thật nhưng nhắm vào host kiểu Claude Desktop | Cao nếu host làm đúng sandbox + CSP | Có thể (CopilotKit có `MCPAppsMiddleware`), nhưng nặng cho web app di động tự làm chủ giao diện; phải tự cài App Bridge |
| **(d) Agent sinh HTML/code tự do** | CopilotKit "Open Generative UI": HTML/CSS/JS sinh ra stream vào iframe sandbox [CT repo] | Thấp: demo | Thấp nhất: CopilotKit tự ghi "accessibility, branding, security khó đảm bảo" [CT] | Có thể về kỹ thuật, **không dùng cho tài chính** |

### 3.3 Vì sao cách (a)+(b) cho Yofina

- **Số liệu phải đến từ tool.** Ràng buộc NFR "100% con số khớp kết quả tool" (§5 proposal). Với declarative/free-form, LLM là tác giả của cấu trúc *và* thường là tác giả của giá trị bên trong; muốn đảm bảo phải thêm một lớp kiểm tra tốn kém hơn nhiều so với việc cho code dựng khối.
- **Danh mục khối của Yofina nhỏ và đã biết** (khoảng 14 loại, §6.1 dưới). Giá trị của declarative là LLM bố cục sáng tạo; ở đây bố cục là thiết kế sản phẩm, không nên để model thay đổi giữa các lần chạy.
- **Giao diện đẹp** đến từ component do đội thiết kế (biểu đồ, thẻ, hũ), không từ catalog chung của A2UI/json-render (catalog Basic của A2UI là Text/Card/Row/Column…, không có biểu đồ dự báo p10–p90).
- **3 tuần**: mỗi lớp đặc tả thêm vào là một nguồn lỗi (độ hạt component, tính nhất quán giữa các lần chạy theo bài AWS Community Builders).
- **Đường tiến vẫn mở**: nếu mỗi khối của ta là một component phẳng có schema JSON, sau này có thể khai báo như một **custom catalog của A2UI** hoặc catalog json-render mà không đổi component. **[ĐX]**

### 3.4 Điều "cách (a)" thật sự là

Cách (a) và (b) khác nhau chủ yếu về **nơi giữ ánh xạ**:

- (b) khóa theo tên tool: `TOOL_CALL_START{toolCallName}` → component.
- (a) khóa theo `block.type` nằm trong payload.

Ta dùng cả hai: khi tool bắt đầu, client biết tên tool → hiện skeleton của khối dự kiến (xem §5.4); khi kết quả về, payload mang `type` và client dùng `type` để chọn component. **[ĐX]**

## 4. AG-UI phía frontend

### 4.1 Event [CT] ([docs.ag-ui.com/concepts/events](https://docs.ag-ui.com/concepts/events))

Doc không ghi số phiên bản hay ngày; ghi chú đáng chú ý: `THINKING_*` đã **deprecated**, thay bằng `REASONING_*`, sẽ bỏ ở 1.0.0; các trường mở rộng của `RunStarted`/`RunFinished` (`parentRunId`, `input`, `outcome`) và Meta events đánh dấu **DRAFT**.

| Nhóm | Event | Trường chính |
|---|---|---|
| Vòng đời | `RunStarted`, `RunFinished`, `RunError`, `StepStarted/Finished` | `threadId`, `runId`; `RunFinished.outcome` = `{type:"success"}` hoặc `{type:"interrupt", interrupts:[...]}`; `RunError.message/code` |
| Văn bản | `TextMessageStart/Content/End` (+ `Chunk`) | `messageId`, `role`, `delta` |
| Tool | `ToolCallStart`, `ToolCallArgs`, `ToolCallEnd`, `ToolCallResult` (+ `Chunk`) | `toolCallId`, `toolCallName`, `delta` (JSON từng mảnh), `content` |
| Trạng thái | `StateSnapshot`, `StateDelta` (JSON Patch RFC 6902), `MessagesSnapshot` | |
| Activity | `ActivitySnapshot`, `ActivityDelta` | `messageId`, `activityType`, `content`, `replace` (mặc định true); `patch` (JSON Patch) |
| Subagent | `SubagentStarted/Finished/Error` | `subagentRunId`, `name` |
| Reasoning | `ReasoningStart/End`, `ReasoningMessage*`, `ReasoningEncryptedValue` | |
| Khác | `Raw`, `Custom` (`name`, `value`) | |

Cách frontend nên xử lý theo doc: nối `delta` theo thứ tự đến, gom theo `messageId`/`toolCallId`; thay trạng thái khi `StateSnapshot`, áp patch tuần tự khi `StateDelta`, xin snapshot mới nếu lệch; activity message render snapshot rồi áp patch; chịu được đến không đúng thứ tự [CT].

### 4.2 Client SDK chính thức [CT] ([docs.ag-ui.com/sdk/js/client/overview](https://docs.ag-ui.com/sdk/js/client/overview), [subscriber](https://docs.ag-ui.com/sdk/js/client/subscriber))

- `npm install @ag-ui/client`. `HttpAgent` (cấu hình `url`, `headers`; dùng được với agent qua HTTP), `AbstractAgent` (tự viết kết nối), `AgentSubscriber`, middleware (ví dụ `FilterToolCallsMiddleware`).
- `AgentSubscriber` có callback cho mọi event: `onTextMessageContentEvent` (nhận `textMessageBuffer`), `onToolCallArgsEvent` (nhận `toolCallBuffer`, `toolCallName` và **`partialToolCallArgs`** đã parse dở), `onToolCallEndEvent` (`toolCallArgs` cuối), `onToolCallResultEvent`, `onActivitySnapshotEvent`, `onActivityDeltaEvent`, `onStateSnapshotEvent`, `onStateDeltaEvent`, `onCustomEvent`, `onRunFailed`...; cùng các handler thay đổi: `onMessagesChanged`, `onStateChanged`, `onNewMessage`, `onNewToolCall`.
- Doc dặn `messages` và `state` là chỉ đọc; copy trước khi sửa.
- Python SDK `ag-ui-protocol` (phía server) và adapter Strands `ag_ui_strands` nằm trong repo `ag-ui-protocol/ag-ui` (`integrations/aws-strands`). Adapter yêu cầu `strands-agents>=1.55.0`, `ag-ui-protocol>=1.0.0`, Python 3.10–3.14 [CT, README repo].

### 4.3 Phía server: Strands → AG-UI [CT] ([README adapter](https://github.com/ag-ui-protocol/ag-ui/tree/main/integrations/aws-strands), [ARCHITECTURE.md](https://raw.githubusercontent.com/ag-ui-protocol/ag-ui/main/integrations/aws-strands/ARCHITECTURE.md))

Các điểm quyết định cho thiết kế:

- Adapter dịch `stream_async` của Strands sang event; tool call → `TOOL_CALL_START/ARGS/END`; kết quả tool → `TOOL_CALL_RESULT` rồi `MESSAGES_SNAPSHOT` (bật mặc định).
- `ToolBehavior` theo từng tool: `state_from_args`, `state_from_result` (ra `STATE_SNAPSHOT`), `custom_result_handler` (phát event tùy ý, kể cả `STATE_DELTA`), `args_streamer`, `skip_messages_snapshot`, `interrupt_on_call`, `continue_after_frontend_call`...
- **Interrupt**: tool gọi `tool_context.interrupt(...)` hoặc `interrupt_on_call=True` (chỉ với tool chạy ở server) → `RUN_FINISHED` mang `outcome.interrupt`; client resume trên cùng `threadId` bằng `resume[]`. Tool nhận `{"response": ...}` hoặc `{"cancelled": True}`. **Tác dụng phụ trước `interrupt()` sẽ chạy lại khi resume**, nên đặt ghi dữ liệu *sau* điểm dừng. Thread còn interrupt chưa trả lời sẽ từ chối lượt mới với `PENDING_INTERRUPTS`.
- **Structured output không được mô tả như tính năng được hỗ trợ**; lỗi structured output báo `STRANDS_ERROR`. Hệ quả: đừng dựa vào việc "Composer trả một JSON structured output" qua adapter này (xem §6.2).
- `state_context_builder` là **đường duy nhất** để `RunAgentInput.state` đi vào model. `context` bị adapter bỏ qua (theo bài của người dùng AWS Community Builders; [BLOG]).
- Bài đăng công bố AG-UI trên AgentCore Runtime (2026-03-13): hỗ trợ cả SSE và WebSocket; 14 Region, **có Singapore** [CT] ([What's New](https://aws.amazon.com/about-aws/whats-new/2026/03/amazon-bedrock-agentcore-runtime-ag-ui-protocol)). Hợp đồng giao thức: cổng 8080, `/invocations` (SSE) hoặc `/ws` (WebSocket), `GET /ping` [CT qua tìm kiếm; trang đầy đủ chưa đọc: [docs.aws.amazon.com/.../runtime-agui-protocol-contract.html](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-agui-protocol-contract.html)].

### 4.4 Ba lựa chọn client

| | **Client mỏng tự viết** (`@ag-ui/client`) | **CopilotKit** | **assistant-ui** |
|---|---|---|---|
| Giấy phép | `@ag-ui/client`: **[?]** chưa kiểm giấy phép của gói npm | Repo **MIT**, ~38,9k sao [CT] | Repo **MIT**, ~13,4k sao; có "Assistant Cloud" tùy chọn [CT] |
| Cần runtime trung gian? | Không. `HttpAgent` gọi thẳng endpoint AgentCore | Mặc định **có**: frontend → `runtimeUrl` → CopilotKit Runtime → agent. Bài mẫu AWS/CopilotKit dùng một Lambda làm Runtime, chuyển tiếp token Cognito [BLOG, CopilotKit 2026-06-30]. Nối thẳng: prop `selfManagedAgents`, nhưng docs ghi nó thuộc "CopilotKit Intelligence", **gói Enterprise**, hỏi kỹ sư về giấy phép khi chạy production; `agents__unsafe_dev_only` chỉ để dev [CT, docs.copilotkit.ai/backend/self-managed-agents] | Không bắt buộc; `@assistant-ui/react-ag-ui` bọc một `HttpAgent` [CT, README/search] |
| Generative UI | Tự viết registry `type → component` | `useComponent`, `useRenderTool`, `useHumanInTheLoop`, `useDefaultRenderTool` (không đăng ký thì tool call vô hình) [CT] | Tool UI; interrupt qua `unstable_getPendingInterrupts`, `unstable_submitInterruptResponses` (tiền tố `unstable_`) [CT, search] |
| Giao diện | Toàn quyền | Component chat mặc định, tùy biến được; đầu ra của ta là component riêng nên giá trị thêm ít | Primitive chat không áp style sẵn (theo hiểu biết, **[?]** chưa kiểm trong phiên này) |
| Rủi ro | Tự lo cuộn, resize composer, xử lý reconnect | Giấy phép `selfManagedAgents` mập mờ; thêm Lambda Node; bài AWS phải vá `AgentCoreRunner` vì replay lịch sử của AgentCore thiếu kết quả tool và thread lạ gây lỗi [BLOG] | Interrupt chưa ổn định; thread list adapter experimental [CT] |

Ngoài ra: AWS Labs Nx plugin có generator nối React với agent AG-UI, dùng `CopilotKitProvider` + `selfManagedAgents` + `HttpAgent`, xác thực bằng SigV4 (IAM) hoặc **Bearer JWT Cognito**, và suy ra header session id của AgentCore bằng cách **đệm `threadId` cho đủ 33 ký tự** [CT] ([awslabs.github.io/nx-plugin-for-aws](https://awslabs.github.io/nx-plugin-for-aws/en/guides/connection/react-agui)). Template FAST không dùng CopilotKit mà tự có parser AG-UI trong `agui.ts`, chỉ xử lý 4 loại event (`TEXT_MESSAGE_CONTENT`, `TOOL_CALL_START`, `TOOL_CALL_RESULT`, `RUN_FINISHED`) [BLOG, CopilotKit 2026-06-30]: bằng chứng rằng client mỏng khả thi.

**Khuyến nghị [ĐX]**: client mỏng. Phần cần viết: một `AgentSubscriber` đẩy event vào store (khoảng vài trăm dòng), registry khối, màn chat. Nếu sau 1 ngày thấy composer/cuộn/thread tốn công, thử `assistant-ui` làm khung thread (vẫn dùng registry khối của ta). Chỉ chọn CopilotKit nếu đội chấp nhận dựng Runtime Lambda và đã xác nhận giấy phép.

### 4.5 Bài AWS ML Blog

"Build generative UI for AI agents on Amazon Bedrock AgentCore with the AG-UI protocol", đăng khoảng **2026-06-30** ([aws.amazon.com/blogs/machine-learning/...](https://aws.amazon.com/blogs/machine-learning/build-generative-ui-for-ai-agents-on-amazon-bedrock-agentcore-with-the-ag-ui-protocol/)). **Phần thân bài gốc không lấy được qua WebFetch** (chỉ có phần đầu trang); nội dung dưới đây dựa trên bài đồng hành của CopilotKit cùng ngày ([copilotkit.ai/blog/generative-ui-on-agentcore-with-copilotkit](https://www.copilotkit.ai/blog/generative-ui-on-agentcore-with-copilotkit)) và các bản tóm tắt: [BLOG]

- Hai mẫu triển khai: **FAST** (parser AG-UI tự viết, dùng chung cho backend Strands và LangGraph) và **CopilotKit** (`useComponent` vẽ biểu đồ từ tool call, `useAgent` cho state dùng chung, `useHumanInTheLoop` cho bộ chọn giờ họp).
- Bản CopilotKit chèn một **Runtime Lambda** giữa trình duyệt và AgentCore để chuyển tiếp token Cognito; trình duyệt không gọi thẳng AgentCore.
- Strands entrypoint của FAST: `StrandsAgent(... StrandsAgentConfig(session_manager_provider=..., replay_history_into_strands=False))`, vòng `async for event in agui_agent.run(input_data): yield event.model_dump(mode="json", by_alias=True, exclude_none=True)`.
- Hạn chế (suy ra từ mã, **[ĐX]**): agent chỉ chọn component đã đăng ký; human-in-the-loop vô hình với agent (agent chỉ thấy kết quả tool); phải tự xử lý kết nối lại (thread lạ, kết quả tool bị rơi khi replay).

## 5. Thiết kế hợp đồng JSON cho khối UI

### 5.1 Union phân biệt theo `type`, versioning, validate hai đầu

**Phong bì chung của mọi khối** **[ĐX]**:

```json
{
  "type": "forecast_timeline",
  "v": 1,
  "id": "ft:an_uong:run_1120",
  "trace_id": "tr_8f2c",
  "source": {"tool": "forecast.get_forecast", "call_id": "tc_01",
             "as_of": "2026-11-21T02:14:00+07:00"},
  "fallback_text": "Hũ Ăn uống dự kiến cạn ngày 23/11, trước kỳ lương 5/12.",
  "data": { }
}
```

- `type`: chuỗi phân biệt (union theo `type`). `v`: số nguyên phiên bản **của riêng khối đó**.
- `id`: ổn định và có nghĩa (`loại:khóa`), dùng làm `messageId` của `ActivitySnapshot` để cập nhật/thay thế khối đúng chỗ, cũng là khóa khử trùng khi tool bị gọi lặp.
- `source`: tool tạo ra, `as_of` (độ tươi của số). `fallback_text` ≤ 280 ký tự, **do server dựng bằng khuôn**, dùng cho screen reader, khối lạ, và chế độ rút gọn.
- `data` tách khỏi phong bì để đổi `data` không chạm vào quy tắc chung.

**Versioning [ĐX]**: chỉ thay đổi **cộng thêm** (thêm trường tùy chọn) trong cùng `v`; đổi nghĩa hoặc xóa trường → tăng `v`. Server có thể phát `v` mới chỉ khi client đã khai báo hỗ trợ (gửi danh sách `{type: maxV}` trong `state` hoặc `forwardedProps` khi chạy). Client hỗ trợ `v` và `v-1` cho đến khi bản mới được phát hành đủ rộng. Trong hackathon (client và server cùng deploy) chỉ cần đảm bảo "không crash khi lạ".

**Validate hai đầu [ĐX]**:

- Pydantic v2 là nguồn sự thật: `Annotated[Union[...], Field(discriminator="type")]`, `model_config = ConfigDict(extra="forbid")`, `TypeAdapter(Block).json_schema()` xuất `contracts/blocks.schema.json`.
- TypeScript: sinh type từ JSON Schema; Zod sinh từ JSON Schema bằng mã sinh hoặc `z.fromJSONSchema()` (có từ Zod 4.2; **docs Zod ghi là experimental và không thuộc API ổn định**, hỗ trợ draft-2020-12/draft-7/draft-4, "không đảm bảo round-trip") [CT] ([zod.dev/json-schema](https://zod.dev/json-schema)). Union có `discriminator` của Pydantic xuất ra `oneOf` kèm `discriminator`; **chưa kiểm** mỗi bộ chuyển đổi có xử lý tốt không, nên chuẩn bị phương án viết Zod tay cho 14 khối nếu mã sinh trục trặc.
- **Biện pháp chống lệch rẻ và chắc nhất, bất kể công cụ sinh**: thư mục `contracts/fixtures/*.json` (mỗi khối vài mẫu hợp lệ + vài mẫu cố ý sai); CI chạy fixtures qua Pydantic (Python) và Zod (Node) và so khớp kết quả đạt/không đạt.
- Server: `forbid` (khóa thừa là lỗi code). Client: bỏ qua khóa lạ (`.passthrough()` hoặc `.strip()`), nghiêm ngặt với `type`, `v`, trường bắt buộc. (Nguyên tắc tolerant-reader.)

### 5.2 Khối không nhận ra: fallback

Thứ tự **[ĐX]**, khớp với yêu cầu của AG-UI cho interrupt ("lạ thì quay về `message`/schema, không báo lỗi" [CT]):

1. `type` lạ hoặc `v` > hỗ trợ → `UnknownBlock`: hiện `fallback_text` trong thẻ trung tính, kèm nhãn nhỏ "Cập nhật ứng dụng để xem đầy đủ" (khi `v` cao) và ghi telemetry.
2. Khối qua Zod hỏng → cùng `UnknownBlock`, **không** vẽ dữ liệu nửa vời; log `trace_id`/`block.id`.
3. Một khối hỏng không được làm hỏng cả tin nhắn: mỗi khối nằm trong error boundary riêng.
4. Không có `fallback_text` → hiện thông báo chung ("Mình chưa hiển thị được phần này"), vẫn giữ văn bản.

### 5.3 Ai là nguồn số liệu

Nguyên tắc: **khối chứa số = tool tất định + block builder bằng code; LLM chỉ chọn và viết lời**. **[ĐX]**

| Loại khối | Tác giả | Kiểm tra |
|---|---|---|
| `forecast_timeline`, `jar_summary`, `affordability_card`, `obligation_impact`, `resilience_score`, `roadmap` (số), `explain`, `confirm` (phần preview), biên nhận | **Code** (builder nhận kết quả tool) | Pydantic khi dựng; không đi qua LLM |
| `options`, `clarify`, `suggestions`, lời trong `roadmap` | **LLM** gọi tool trình bày (ví dụ `ui.present_options(items=[...])`), tool chỉ validate rồi phát | Giới hạn độ dài, bỏ markup; **`NumericGrounding` áp lên nhãn**: số xuất hiện trong nhãn phải thuộc tập "sự kiện" của lượt (kết quả tool); sai → trả lỗi có cấu trúc cho LLM sửa (Verifier tối đa 2 vòng như proposal), hết lượt thì bỏ khối |
| Văn bản `text` | LLM | `NumericGrounding` như proposal; chuẩn hóa được "1,2 triệu", "1.200.000đ", "1tr2", "450k" về số nguyên trước khi so khớp |

Chi tiết thực tế:

- **Tiền = số nguyên đồng** (`amount_vnd: int`), đặt tên có đơn vị, không dùng float; ngày ISO 8601 (`2026-11-23`), thời điểm có múi giờ `+07:00`; xác suất là số 0–1. Định dạng tiền tệ, "triệu/nghìn" làm bằng `Intl.NumberFormat('vi-VN')` ở client, nhất quán giữa khối và Home.
- **Tùy chọn mạnh hơn [ĐX, cần thử]**: LLM viết số bằng *tham chiếu sự kiện* (`{{fact:runout_date}}`) và server thay thế sau khi kiểm; số không có trong tập sự kiện không thể xuất hiện. Đổi lại cần LLM tuân thủ cú pháp; có thể thử ở Analyst sau khi MVP chạy.
- **Chống trùng khối**: tool bị gọi lặp trong một lượt cho cùng khóa → cùng `id` khối → `ActivitySnapshot` với `replace: true` thay thế tại chỗ.

**Vì sao không dùng structured-output "một JSON của Composer"?** Ngoài việc adapter Strands không mô tả structured output như tính năng được hỗ trợ [CT], còn một lý do UX: một JSON duy nhất chỉ xuất hiện khi LLM Composer xong, trong khi proposal muốn khối dòng thời gian hiện ở giây thứ 2 và văn bản kết thúc trước giây thứ 8. Khối dựng sẵn từ tool cho phép hiện ngay.

### 5.4 Render từng phần khi đang stream

Có ba trường hợp khác nhau **[ĐX]**:

1. **Khối do server dựng (đa số)**: đến nguyên vẹn khi tool xong. Trước đó chỉ cần **skeleton**: khi nhận `TOOL_CALL_START{toolCallName}` client tra bảng `tên tool → loại khối dự kiến` và vẽ skeleton đúng kích thước (tránh giật bố cục), đồng thời hiện dòng tiến trình ("Đang đọc dự báo hũ Ăn uống…"). Khi khối thật về → thay thế (cross-fade ngắn). Không cần parser JSON dở.
2. **Khối do LLM viết** (`options`, `clarify`): đi qua tool call có schema → `TOOL_CALL_ARGS` stream JSON dở. `AgentSubscriber.onToolCallArgsEvent` cho sẵn `partialToolCallArgs` (đã parse dở) [CT]. Quy tắc render: chỉ vẽ phần tử mảng khi đã đóng; không vẽ số/chuỗi dang dở; hoặc đơn giản hơn: **chờ `TOOL_CALL_END` rồi mới hiện** (các khối này nhỏ, độ trễ không đáng kể). Phần lớn bài viết về parser JSON dở nhấn mạnh việc "JSON trông xong nhưng chưa xong" và parser sửa-lỗi không thay thế được quy tắc render an toàn [BLOG] ([dev.to](https://dev.to/james_oconnor_dev/-the-partial-json-looked-done-it-wasnt-heres-what-streaming-structured-output-actually-j0e), [tianpan.co](https://tianpan.co/blog/2026/04/27/streaming-json-parser-typed-object-gap)).
3. **Khối cập nhật liên tục** (`ingest_progress`, nạp sao kê; xác nhận chuyển từ "đang chờ" sang "xong"): dùng `ACTIVITY_SNAPSHOT` lần đầu rồi `ACTIVITY_DELTA` (JSON Patch) [CT]; mỗi lần nhận, kiểm tra lại bằng Zod trên bản đã vá.

Nếu sau này dùng json-render: nó stream JSONL patch RFC 6902 và có `createSpecStreamCompiler` [CT]; hợp cho trường hợp (2) nếu thấy cần.

### 5.5 Khối tương tác gửi ngược về agent

Ba kênh, chọn theo bản chất hành động **[ĐX]**:

| Hành động | Kênh | Ví dụ |
|---|---|---|
| Trả lời một interrupt (xác nhận, hỏi lại, duyệt dòng) | `RunAgentInput.resume[]` với `{interruptId, status: "resolved"/"cancelled", payload}` trên cùng `threadId` [CT] | Nút "Xác nhận", chip trả lời của `clarify` |
| Chọn một phương án trong `options` | Gửi **một tin nhắn người dùng mới** kèm `option_id` trong `state` (hoặc `forwardedProps`; **[?]** theo trí nhớ về `RunAgentInput`, chưa kiểm trong phiên này). Không thực thi trực tiếp | "Hoãn 2 tuần" → lượt mới; nếu phương án đổi số dư thì lượt đó kết thúc bằng khối `confirm` |
| Điều khiển cục bộ (mở bảng "Vì sao", thu gọn, phản hồi 👍/👎) | Không đi qua agent; gọi REST của ứng dụng (`POST /feedback`, `GET /trace/{id}`) | |

Quy tắc: khối không bao giờ mang URL, tên tool hay tham số thực thi do LLM đặt. Nó mang `action_id` (do server đăng ký trong lượt, có hạn) và id của interrupt. Phần an toàn xem §8.

## 6. Mẫu UX cho agentic system, áp dụng vào Yofina

### 6.1 Bộ `type` đề xuất cho Yofina **[ĐX]**

| `type` | Nguồn | Tác giả khối | Ghi chú |
|---|---|---|---|
| `forecast_timeline` | `forecast.get_forecast`, `run_scenario` | Code | Đường p10/p50/p90, ngày cạn, sự kiện lương/nghĩa vụ; có `scenario` tùy chọn để so trước/sau |
| `jar_summary` | `ledger.get_jar_balances` | Code | Vòng/thanh cho 7 hũ, hũ tạm "Chưa phân loại", ô "Tiền vào khác" |
| `affordability_card` | `forecast.affordability_check` | Code | Đủ/sát/hụt, tổng chi phí thật, luật đã kiểm |
| `obligation_impact` | `run_scenario` + `knowledge.get_fee_schedule` | Code | Gốc + phí + hạn + hũ sẽ hụt tháng sau |
| `resilience_score` | `forecast.get_resilience_score`, `stress_test` | Code | Điểm 0–100, 4 thành phần Save/Spend/Borrow/Plan, số ngày trụ được; trước/sau cú sốc |
| `roadmap` | `planner.*` | Code (số) + LLM (lý do từng bước) | Mỗi bước có Chấp nhận / Sửa / Bỏ (các bước ghi dữ liệu đi qua `confirm`) |
| `options` | LLM qua `ui.present_options` | LLM (validate) | Mỗi phương án có `effect: read_only \| proposes_write` |
| `explain` ("Vì sao") | `audit.get_trace` | Code | Dữ liệu đã dùng + thời điểm, luật đã kiểm, độ tin cậy nhóm, độ phủ, phương án đã cân nhắc |
| `confirm` | Interrupt từ tool ghi | Code (preview) | Xem trước → xác nhận; xem §6.4 |
| `receipt` | Kết quả tool ghi | Code | Biên nhận, nút Hoàn tác có đếm ngược nếu hoàn tác được |
| `clarify` | Interrupt `input_required` | LLM (câu hỏi) + code (lựa chọn mặc định) | Một câu hỏi, chip trả lời, ô gõ tự do |
| `ingest_progress` / `ingest_review` | `ingest.*` | Code | Tiến độ job nền; danh sách dòng chưa chắc, mỗi dòng có 2 gợi ý hũ, duyệt từng dòng; độ phủ dữ liệu tăng |
| `notice` | Server | Code | `kind`: `info`/`low_data`/`degraded`/`out_of_scope`/`error`; kèm hành động gợi ý |
| `suggestions` | Code (mặc định) hoặc LLM (câu tiếp theo, validate) | | ≤ 3 chip; mỗi chip là một tin nhắn mẫu |

Cùng một component dùng ở **hai nơi**: trong chat và trên màn hình Home/chi tiết hũ. Home lấy khối bằng REST/trực tiếp từ tool đọc (không qua LLM): Cảnh 1 của demo ("mở app: dòng thời gian báo hũ Ăn uống cạn ngày 23") không phụ thuộc agent, nên không thể chết vì agent chết.

### 6.2 Điều chỉnh hợp đồng của proposal

Hợp đồng gốc (§9, `overview.md`) là một JSON `{trace_id, intent, text, blocks[]}`. Với AG-UI:

- Các thành phần vẫn cần, nhưng nên tách: `trace_id`, `intent`, cờ `degraded` → một sự kiện `CUSTOM` `yofina.turn_meta` phát **ngay đầu lượt** (client gắn "Vì sao" vào mọi khối của lượt). `text` → `TEXT_MESSAGE_*` bình thường. Mỗi `blocks[i]` → một event riêng.
- **Giữ nguyên JSON gốc làm `TurnResult`**: ghép lại phía server khi lượt kết thúc và lưu DB (`chat_turns`) để (i) hiện lại lịch sử khi tải lại trang mà không phụ thuộc replay của AgentCore (bài AWS ghi nhận replay thiếu kết quả tool [BLOG]), (ii) là nơi `SchemaValidity` evaluator làm việc, (iii) đường dự phòng: khi LLM lỗi, server dựng thẳng `TurnResult` tất định (khối + câu mẫu) và phát qua cùng các event.
- **Chọn event nào để chở khối?** Phương án khuyến nghị **[ĐX, cần spike]**: `ACTIVITY_SNAPSHOT` với `activityType = "yofina.block"`, `messageId = block.id`, `content = block`. Lý do: không đi vào ngữ cảnh LLM (không tốn token), thay thế tại chỗ được, vá được bằng `ACTIVITY_DELTA`. Khi tool trả kết quả cho LLM, chỉ trả bản **tóm tắt sự kiện gọn** để LLM viết lời (và để đối chiếu số). Phương án dự phòng nếu adapter không phát được Activity: `CUSTOM` `yofina.block`, hoặc nhét khối vào `TOOL_CALL_RESULT.content` (đơn giản nhất, khớp mọi thư viện, nhưng đưa cả khối vào ngữ cảnh model). Adapter có `custom_result_handler` phát "event tùy ý" [CT]: **chưa kiểm** nó chấp nhận `ActivitySnapshotEvent`.
- Chỉnh các khối trong ví dụ của proposal: thêm `v`, `id`, `source`, `fallback_text`; `confirm` hiện chỉ có `{"action": "schedule_nudge", "requires_user": true}` — thiếu preview, hạn, token xác nhận, phân loại đảo ngược (xem §7.3); `options.items` thiếu `effect`; số tiền đổi sang `*_vnd` nguyên; `explain.coverage` là chỉ số có định nghĩa (phần trăm dữ liệu được giải thích) nên có thể hiển thị dạng thanh, còn `confidence` giữ dạng nhóm.

### 6.3 Tiến trình tool, streaming chữ, khối đến trước chữ

Thứ tự trong một lượt **[ĐX]**:

```
[dòng trạng thái tool]  →  [skeleton → khối thật]  →  [chữ stream]  →  [options / confirm / clarify]  →  [chân: nhãn AI · Vì sao · 👍👎]
```

- Dòng trạng thái: bảng nhãn tiếng Việt ở client (`forecast.get_forecast` → "Đang đọc dự báo", `forecast.run_scenario` → "Đang mô phỏng"), không bao giờ hiện tên tool thô. Tool song song gộp thành một dòng. Xong thì thu gọn thành "Đã dùng: dự báo · nghĩa vụ · biểu phí" (mẫu Footprints / Stream of Thought của Shape of AI: [shapeof.ai](https://www.shapeof.ai/) [CT]; Anthropic cũng nêu "hiển thị các bước lập kế hoạch" như nguyên tắc minh bạch [CT] ([building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents))).
- Quá ~4 giây chưa có gì: đổi nhãn sang câu có thông tin ("Vẫn đang mô phỏng, phép tính này hơi lâu") và hiện nút **Dừng** (`HttpAgent` có abort [CT]). Ngân sách proposal: khối dòng thời gian ở khoảng giây 2, văn bản xong trước giây 8.
- Văn bản: markdown tối giản, cuộn tự động chỉ khi người dùng đang ở cuối; khối chiếm chỗ bằng skeleton để chữ không nhảy.
- Reasoning: nếu bật, hiển thị `REASONING_*` dạng thu gọn; **không** là mặc định trong demo tài chính (nhiễu). **[ĐX]**

### 6.4 Human-in-the-loop cho hành động đổi số dư

Luồng đề xuất, ánh xạ vào AG-UI interrupt **[ĐX]**; mẫu "Intent Preview" của Smashing Magazine coi là "bắt buộc" với mọi giao dịch tài chính bất kể số tiền, gồm ba lựa chọn Tiến hành / Sửa kế hoạch / Tự xử lý, và gợi ý tính tỷ lệ chấp nhận không sửa (mục tiêu > 85%), tỷ lệ ghi đè (> 10% cần xem lại mô hình) [BLOG] ([smashingmagazine.com](https://smashingmagazine.com/2026/02/designing-agentic-ai-practical-ux-patterns/)):

```
1. Người dùng: "chuyển 300k từ Giải trí sang Ăn uống"
2. Router → tool xem trước KHÔNG GHI (dry-run): tính trước/sau số dư hai hũ và ngày cạn mới (forecast tất định)
3. Tool ghi (ledger.move_between_jars) đặt interrupt_on_call → RUN_FINISHED.outcome = interrupt
     Interrupt{id, reason:"confirmation", message, toolCallId, responseSchema, expiresAt, metadata}
4. UI: khối `confirm` = Trước/Sau từng hũ + tác động lên dự báo + hạn hoàn tác
     [Xác nhận chuyển 300.000đ]  [Sửa số tiền]  [Huỷ]       (nhãn nút do server dựng, có số tiền)
5. (Số tiền vượt ngưỡng) bước tăng cường: PIN/sinh trắc học mô phỏng
6. resume[{interruptId, status:"resolved", payload:{decision:"approve", confirmation_token}}]
7. Server kiểm token → ghi → khối `receipt` (+ Hoàn tác trong N phút) → ghi audit (trace_id)
```

Quy tắc cụ thể:

- **Không tin nút bấm trần.** Khi phát interrupt, server cấp `confirmation_token` gắn với (user, hash tham số hành động, hạn, dùng một lần). Cedar (AgentCore Policy) chỉ cho tool ghi chạy khi tham số mang token hợp lệ — phù hợp với "cờ xác nhận" trong proposal (§9). Resume bị lặp → idempotent (adapter Strands bỏ qua câu trả lời giống hệt và trả lỗi `FRONTEND_TOOL_RESULT_CONFLICT` với câu khác [CT]).
- **Kiểm lại lúc thực thi**: nếu số dư đã đổi so với `as_of` của bản xem trước, không ghi; phát `confirm` mới ("Số dư đã thay đổi, xem lại").
- **Nhãn nút nêu hành động và số tiền**, không dùng "OK/Đồng ý"; vô hiệu nút đến khi bản xem trước tải xong; chống bấm đúp; đếm ngược khi sắp hết hạn (`expiresAt`).
- **Một interrupt chưa trả lời chặn lượt mới** (`PENDING_INTERRUPTS`): khi người dùng gõ tin khác, UI hỏi "Huỷ yêu cầu chuyển tiền đang chờ?" và gửi `cancelled`, thay vì để lỗi.
- **Tác dụng phụ chạy lại khi resume** [CT]: trong tool ghi, đặt `interrupt()` trước mọi ghi dữ liệu; bước xem trước phải thuần tuý (không ghi).
- **Hoàn tác** — phân loại theo hành động:

| Hành động | Đảo ngược? | Cách làm |
|---|---|---|
| `move_between_jars`, `assign_jar` | Có | Giao dịch bù (compensating), cửa sổ hoàn tác ~10 phút hiển thị rõ; nút trên `receipt` và trong lịch sử |
| `update_profile` (lương, chi phí cố định) | Có | Lưu phiên bản; "Khôi phục phiên bản trước" |
| `record_transaction` trên ví mô phỏng | Một phần | Cho phép huỷ trong cửa sổ ngắn; ghi rõ khi hết hạn |
| Chuyển tiền ra ngoài ví (nếu sau này có) | **Không** | Cổng mạnh hơn: tăng cường xác thực, hiển thị "không thể hoàn tác" trước khi xác nhận |

  Smashing khuyên hiển thị cửa sổ hoàn tác (ví dụ 15 phút) cho tới lúc hành động thành vĩnh viễn, và theo dõi tỷ lệ hoàn tác (hơn 5% cho một tác vụ → cân nhắc tắt tự động hóa) [BLOG]. Với Yofina agent không tự thực thi, nhưng chỉ số này vẫn dùng được cho độ chính xác của đề xuất.

Phản diện cần tránh (từ phân tích Revolut AIR): trợ lý chuẩn bị mọi yêu cầu nhưng **mọi giao dịch tài chính đều cần xác nhận sinh trắc học**, vừa là trấn an người dùng vừa là yêu cầu quy định ở châu Âu [BLOG] ([ergomania.eu](https://ergomania.eu/revolut-air-ai-banking-assistant-ux/)). Ở Yofina bản demo có thể mô phỏng bước PIN/Face ID để giám khảo thấy cùng mẫu.

### 6.5 Hỏi lại một câu khi thiếu tham số

- Dùng interrupt `reason: "input_required"` với `responseSchema` (enum + tuỳ chọn gõ tự do) [CT]; client **kiểm tra câu trả lời theo schema** trước khi gửi.
- Tối đa **một** câu, nêu phần đã hiểu ("Mình hiểu: mua tai nghe 1,2 triệu. Bạn định trả bằng gì?"), chip trả lời nhanh (Ví Trả Sau / Hũ Giải trí / Hũ Ăn uống) và ô gõ tự do; chip mặc định được làm nổi.
- **Với việc rủi ro thấp (không ghi), ưu tiên giả định hiển thị** ("Mình giả định trả bằng Ví Trả Sau — đổi?") thay vì chặn: khớp nguyên tắc HAX #10 "Scope services when in doubt" [CT] ([Microsoft Research](https://www.microsoft.com/en-us/research/articles/guidelines-for-human-ai-interaction-eighteen-best-practices-for-human-centered-ai-design/)) và "Escalation Pathway: hỏi hoặc chuyển giao thay vì đoán, tần suất lành mạnh 5–15%" của Smashing [BLOG]. Với việc ghi (đổi số dư) thì luôn hỏi/xác nhận.
- Ngưỡng độ tin cậy dưới ngưỡng ở §7 của proposal ("thiếu dữ liệu thì hỏi lại") dùng cùng `clarify`.

### 6.6 Minh bạch và giải thích

Điều các hướng dẫn thống nhất, áp vào bảng "Vì sao" **[ĐX]**:

- PAIR: "Don't say 'what' without saying 'why' in a high stakes scenario"; giải thích **một phần** thường tốt nhất; chỉ rõ **khoảng trống dữ liệu**; **tránh độ tin cậy số** vì "giả định người dùng có nền tảng xác suất" [CT] ([pair.withgoogle.com/chapter/explainability-trust](https://pair.withgoogle.com/chapter/explainability-trust/)). → `confidence` ∈ {cao, vừa, thấp} kèm lý do ("mới có 18 ngày dữ liệu"), không phần trăm do LLM đưa.
  - Với **xác suất của dự báo** (`p_shortfall`) thì đây là số thật từ Monte Carlo, vẫn nên diễn đạt dễ hiểu ("khoảng 7 trong 10 kịch bản hụt trước kỳ lương"). Đây là gợi ý trình bày **[ĐX, nên thử với vài người dùng]**, không phải khẳng định từ nguồn đã đọc.
- Microsoft HAX: #1 làm rõ hệ thống làm được gì, #2 làm tốt đến đâu, #11 giải thích vì sao hệ thống làm vậy, #15 khuyến khích phản hồi chi tiết, #16 nêu hậu quả hành động của người dùng, #17 điều khiển toàn cục, #18 thông báo thay đổi [CT]. → màn mở đầu chat liệt kê "Mình làm được / chưa làm được".
- Mẫu Shape of AI: **Disclosure** (đánh dấu nội dung do AI), **Caveat**, **Footprints**, **Citations**, **Action plan**, **Verification** [CT].
- Nội dung bảng "Vì sao" (đã khớp FR11): dữ liệu đã dùng **kèm `as_of`**, luật đã kiểm (đạt/không đạt), độ tin cậy nhóm + lý do, độ phủ dữ liệu (thanh), phương án đã cân nhắc, `trace_id` ở chân (sao chép được, dành cho Cảnh 6 của demo).
- Nhãn AI: chip "Do AI tạo" nhỏ trên mỗi khối + câu cố định ở header chat. Không lặp thành đoạn miễn trừ dài trong mỗi tin.

### 6.7 Xử lý lỗi và suy giảm có kiểm soát

PAIR phân loại lỗi (context error, failstate, background error...) và dặn: nêu giới hạn cụ thể, đưa **lối đi tiếp**, trả quyền kiểm soát, giọng "người chứ không phải máy" [CT] ([pair.withgoogle.com/chapter/errors-failing](https://pair.withgoogle.com/chapter/errors-failing/)). CFPB (06/2023) liệt kê hại của chatbot tài chính: **"doom loop"** (lặp mãi không ra lối), thông tin sai gây phí sai, không nhận ra tranh chấp, **cản đường tới người thật**, sự cố, rò rỉ riêng tư [CT] ([consumerfinance.gov](https://www.consumerfinance.gov/data-research/research-reports/chatbots-in-consumer-finance/chatbots-in-consumer-finance/)).

Thang suy giảm **[ĐX]** (khớp NFR "LLM lỗi thì vẫn trả thẻ số liệu tất định"):

| Bậc | Tình huống | Hiển thị |
|---|---|---|
| 0 | Bình thường | Khối + chữ |
| 1 | Tool lỗi | Thử lại im lặng một lần |
| 2 | Tool vẫn lỗi / thiếu một phần | Hiện khối đã có + `notice{kind:"error"}` nêu **phần thiếu cụ thể** ("chưa tính được biểu phí Ví Trả Sau") |
| 3 | LLM quá ~2s hoặc lỗi (đặc biệt `affordability_check`) | Server phát khối tất định + `fallback_text` làm câu giải thích; chip nhỏ "Chế độ rút gọn" |
| 4 | Agent không với tới (`RUN_ERROR`, mất mạng) | Bong bóng báo lỗi có tên lỗi dễ hiểu + **Thử lại** + `trace_id`; chat khoá mềm; **Home và các màn khác vẫn dùng được** vì số liệu Home đi đường REST |
| 5 | Lặp lỗi hai lần | Đổi lối: gợi ý màn hình thay thế ("Xem trực tiếp ở màn Hũ"), đường liên hệ hỗ trợ (liên kết giả lập cho demo). Không để doom loop |

- `RUN_ERROR` ngăn xử lý tiếp trong lượt [CT]: client phải đóng mọi dòng text/tool đang mở, đánh dấu khối dở là "chưa hoàn tất", không để bong bóng trống.
- Thử lại luôn mang **khóa idempotency**, để không ghi hai lần.

### 6.8 Chat nằm ở đâu, gợi ý câu hỏi

- Bằng chứng từ sản phẩm thật: Revolut AIR là **overlay** truy cập nhanh các chức năng khó tìm, không thay thế điều hướng; tác giả phân tích nhắc "navigation will disappear" là hứa quá, và cảnh báo "không có đường tới người thật thì chỉ là ngõ cụt đẹp hơn" [BLOG, ergomania]. NN/g (State of UX 2026) mô tả chuyển dịch sang "uỷ thác" cho một lớp nằm trên giao diện, nhưng nhấn mạnh minh bạch, kiểm soát, nhất quán và hỗ trợ khi hỏng [CT] ([nngroup.com/articles/state-of-ux-2026](https://www.nngroup.com/articles/state-of-ux-2026/)).
- **Đề xuất [ĐX]**:
  - Thanh nhập "Hỏi Yofina…" cố định phía trên thanh điều hướng ở Home; chạm → bottom sheet kéo lên toàn chiều cao, vẫn thấy ngữ cảnh phía dưới.
  - **Điểm vào theo ngữ cảnh**: chi tiết hũ ("Vì sao hũ này cạn?"), màn chuyển tiền/thanh toán ("Kiểm tra trước khi quẹt" là thẻ F3 ngay trước nút Xác nhận chuyển), màn điểm chống chịu ("Nếu mất việc 2 tháng?"). Mỗi điểm vào mở sheet với chip ngữ cảnh.
  - **Ngữ cảnh màn hình đi qua `state`** (`{screen, jar_id, ...}`) và vào model qua `state_context_builder` [CT]; **không** đưa qua `context` (bị adapter Strands bỏ qua [BLOG]). Server coi nó là dữ liệu không đáng tin cho phân quyền (assistant-ui cũng cảnh báo `getRunContext` không được dùng để uỷ quyền [CT]); mọi tool vẫn kiểm theo JWT.
  - Cú sốc "mất việc 2 tháng" là **nút**, không bắt gõ: nút → gửi tin nhắn mẫu hoặc gọi thẳng `stress_test` rồi kể chuyện bằng chữ.
- **Gợi ý câu hỏi**: màn đầu sinh **từ trạng thái tất định** (hũ sắp cạn dưới ngưỡng, nghĩa vụ sắp đến hạn, độ phủ thấp → "Nạp thêm sao kê"), không để LLM tự nghĩ. Sau mỗi câu trả lời, `suggestions` ≤ 3 chip; chip là tin nhắn mẫu có thể sửa trước khi gửi (Cảnh 2 của demo gõ tay). Mẫu "Wayfinders" ở Shape of AI nói về việc giúp người dùng bắt đầu [CT].

### 6.9 Chủ động nhắc mà không làm phiền

- Proposal FR13: tối đa **một nhắc mỗi ngày**, chỉ khi vượt ngưỡng giá trị.
- UX **[ĐX]**: hiển thị là một thẻ "Việc cần làm hôm nay" ở Home (không push trong bản web demo), có nút **Để sau** và **Ít nhắc loại này**, và dòng "Vì sao tôi thấy mục này?". Bấm bỏ qua nhiều lần → giảm tần suất loại đó (khớp §10.2 proposal).
- Căn cứ: HAX #3 "Time services based on context", #14 "Update and adapt cautiously", #17 "Provide global controls", #18 "Notify users about changes" [CT]. Bank of America cho biết Erica đã giao hơn 1,7 tỷ insight chủ động; và các bộ phận pháp lý, rủi ro, quy định **cùng thiết kế khả năng của Erica từ đầu** thay vì duyệt cuối [BLOG, CMSWire; [newsroom BofA](https://newsroom.bankofamerica.com/content/newsroom/press-releases/2026/03/bofa-ai-and-digital-innovations-fuel-30-billion-client-interacti.html)]; tôi **chưa tìm được** mô tả cách Erica trình bày thẻ insight trong giao diện.

## 7. Riêng cho tài chính

### 7.1 App thật làm gì (những gì tìm được)

| Sản phẩm | Quan sát | Nguồn |
|---|---|---|
| Revolut AIR (trợ lý AI trong app) | Overlay trên điều hướng sẵn có; mọi giao dịch tài chính đòi sinh trắc học; điều khoản ghi rõ đây là dịch vụ tự động, không phải người; người dùng tự đánh giá thông tin và đối chiếu chi tiết giao dịch trong app; chat thường được ghi lại và xem lại để kiểm soát chất lượng; dữ liệu có thể chia sẻ với đối tác công nghệ; dữ liệu tài chính không nằm trong ngữ cảnh model (theo phân tích bên thứ ba) | [BLOG](https://ergomania.eu/revolut-air-ai-banking-assistant-ux/); điều khoản [Revolut](https://www.revolut.com/legal/rita-disclaimer/) (tôi **không đọc trực tiếp** được trang này, chỉ thấy tóm tắt từ công cụ tìm kiếm) |
| Bank of America Erica | Rất nhiều insight chủ động (1,7 tỷ); pháp lý/rủi ro cùng thiết kế từ đầu | [BLOG](https://www.cmswire.com/digital-experience/bank-of-americas-ai-playbook-what-cx-leaders-can-learn-from-ericas-long-game/) |
| Cleo | Giọng cá tính; một bài phân tích nhấn mạnh "thực hiện giao dịch/chuyển tiền cần nhiều tin cậy hơn nhiều so với giải thích khái niệm" | [BLOG] qua tìm kiếm, chưa đọc nguyên bài |
| Monzo, Nubank, ví Việt (kể cả MoMo) | **Chưa tìm được** thông tin đủ cụ thể về thiết kế xác nhận/miễn trừ | [?] |

### 7.2 Cách trình bày lời khuyên và miễn trừ **[ĐX]**

- Mức cố định, ngắn: "Do AI tạo · Tham khảo, không phải tư vấn đầu tư hay tín dụng" ở header chat + chip nhỏ trên khối; chi tiết hơn nằm trong màn "Về trợ lý này" (nêu dữ liệu nào được dùng, giới hạn). Đừng lặp đoạn miễn trừ dài sau mỗi tin.
- **Ngôn ngữ**: nói về hũ và kế hoạch của chính người dùng ("hũ Ăn uống của bạn dự kiến cạn…"), không đưa lời khuyên chung chung kiểu đầu tư. Khi bị hỏi mã cổ phiếu (Cảnh 4): `notice{kind:"out_of_scope"}` nêu rõ giới hạn + gợi ý việc làm được ("Mình có thể kiểm tra hũ Dự phòng đã đủ chưa") — khớp §10.1 proposal.
- **Tổng chi phí thật** luôn đặt cạnh giá khi dùng trả sau (đây chính là khác biệt của sản phẩm); đừng làm tròn che phí.
- Xác nhận: xem §6.4.
- Pháp lý: proposal ghi chưa xác minh việc phân loại theo Luật Trí tuệ nhân tạo và Luật Bảo vệ dữ liệu cá nhân của Việt Nam; tôi **không** kiểm chứng thêm ở đây [?].

### 7.3 Nên tránh

- **Doom loop** và chặn đường tới người thật (CFPB; phân tích Revolut) [CT/BLOG].
- **Giả danh người thật**: không để trợ lý nhận là người (ghi nhận trong phân tích AIR về các ca AI hỗ trợ khách hàng nhận là người) [BLOG].
- **Upsell cải trang thành giúp đỡ** (phân tích AIR cảnh báo việc giới thiệu tính năng cao cấp đúng lúc ngữ cảnh có thể thành chào bán) [BLOG]. Yofina không bán gì, nhưng đừng đưa phương án nào có lợi cho đối tác tín dụng lên đầu.
- **Số tự tin giả**: phần trăm độ tin cậy do LLM nêu; PAIR cảnh báo [CT].
- **Hành động ngầm / tự chạy**: mọi đổi số dư qua xác nhận (FR12).
- Hù doạ ("bạn sắp cháy túi!") thay vì đưa lối đi; tông "nhân văn, không máy móc" của PAIR [CT].
- Hiển thị khối khi dữ liệu cũ: luôn có `as_of`; quá hạn thì tính lại trước khi trả lời (cổng "độ tươi" của proposal).

## 8. An toàn

| Rủi ro | Biện pháp **[ĐX]**, căn cứ OWASP LLM05 (Improper Output Handling) |
|---|---|
| HTML/JS từ model | **Không bao giờ** `dangerouslySetInnerHTML`; văn bản qua text node hoặc markdown tối giản (không HTML thô: không bật `rehype-raw`; không ảnh; liên kết chỉ khi trong allowlist, hoặc tắt hẳn). OWASP: "treat the model as any other user", mã hóa đầu ra theo ngữ cảnh đích, CSP chặt; ví dụ nêu XSS từ Markdown/JS được render [CT] ([genai.owasp.org LLM05](https://genai.owasp.org/llmrisk/llm052025-improper-output-handling/)) |
| Markdown ảnh để rò dữ liệu | Không render ảnh từ model; CSP `img-src` chỉ origin của app |
| Dữ liệu độc từ tệp nạp (tên đối tác trong ảnh/CSV chứa chỉ dẫn hay liên kết) | Mọi chuỗi lấy từ bên ngoài hiển thị dạng text; cắt độ dài; không tạo liên kết; không đưa vào `label` của nút hành động |
| Khối "kích hoạt hành động" ngoài ý | Khối chỉ mang `action_id` do server đăng ký (gắn user, lượt, hạn) và `interruptId`; client có **bảng cố định `type → hành động được phép`** (`options` → gửi tin nhắn; `confirm`/`clarify`/`ingest_review` → `resume`); không có khối nào mang URL, tên tool hay tham số thực thi; không `window.open` từ dữ liệu khối |
| Giả mạo trong resume | Token xác nhận gắn hash tham số, dùng một lần, có hạn; Cedar kiểm tham số + token (§6.4) |
| Zod bỏ lọt | Giới hạn: độ dài chuỗi, số phần tử mảng (ví dụ `series` ≤ 400), độ sâu; phát hiện số âm/NaN/Infinity ở chỗ không cho phép |
| Quyền | `state`/ngữ cảnh màn hình từ client không đáng tin để phân quyền; JWT mới là nguồn danh tính ở mọi tool (khớp NFR bảo mật) |
| A2UI (nếu dùng sau này) | Chỉ dữ liệu khai báo; hàm có `allowedCallers` và `requiresUserActivation`; regex bị giới hạn chống catastrophic backtracking [CT] |
| MCP Apps (nếu dùng sau này) | iframe sandbox, CSP, quyền do host cấp; mọi giao tiếp qua `postMessage` [CT] |
| Khả năng tiếp cận | Mỗi khối có `fallback_text`; biểu đồ có bảng số thay thế; xanh/vàng/đỏ luôn kèm biểu tượng và chữ |

## 9. Khuyến nghị cho Yofina

### 9.1 Kiến trúc generative UI đề xuất

```
Tool tất định (Lambda sau Gateway)  ──result──▶ block builder (Pydantic)  ──Block──▶ ACTIVITY_SNAPSHOT yofina.block
         ▲                                              │                                   │
Strands Orchestrator (LLM) ──chọn tool, viết lời         └─ tóm tắt sự kiện gọn ─▶ LLM      │  (AG-UI qua SSE, Bearer JWT, AgentCore Runtime)
         │                                                                                   ▼
Verifier (số khớp? luật suitability?)                                       @ag-ui/client HttpAgent + AgentSubscriber
Composer: text (TEXT_MESSAGE_*), options/clarify (tool ui.*), meta (CUSTOM yofina.turn_meta)   │
Tool ghi: interrupt_on_call ─▶ RUN_FINISHED.outcome=interrupt ─▶ khối `confirm` ─▶ resume[]    ▼
Lưu `TurnResult` (JSON gốc của proposal) vào DB                       zustand store ─▶ registry type→component (Zod) ─▶ UI di động
```

- Số liệu Home/biểu đồ màn hình: gọi tool đọc qua REST của app, **không qua LLM**, dùng cùng component.
- Lịch sử chat: đọc từ DB (`TurnResult`), không dựa vào replay của AgentCore.
- Phiên: `threadId` do client sinh; header session id của AgentCore cần ≥ 33 ký tự (Nx plugin đệm `threadId` cho đủ [CT]); xác thực Bearer JWT Cognito.

### 9.2 Luồng cho các cảnh demo (đối chiếu `demo-script.md`)

- **Cảnh 1**: Home gọi REST `get_forecast` → `forecast_timeline` + `jar_summary`; không agent.
- **Cảnh 2** ("nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau"): `TOOL_CALL_START(run_scenario)` → skeleton `forecast_timeline` + dòng "Đang mô phỏng" → khối `forecast_timeline` (có `scenario`) + `obligation_impact` + `affordability_card` (~giây 2) → chữ stream → `options` (2 phương án) → chân: "Vì sao".
- **Cảnh 3** (nút "mất việc 2 tháng"): nút gọi `stress_test` → `resilience_score` có trước/sau, số ngày trụ.
- **Cảnh 4**: `roadmap` mới + `explain`; "nên mua cổ phiếu nào" → `notice{out_of_scope}`.
- **Cảnh 5**: tải ảnh → `ingest_progress` (Activity delta) → `ingest_review` cho dòng chưa chắc → độ phủ tăng, `forecast_timeline` cập nhật.
- **Cảnh 6**: `explain` mở màn trace theo `trace_id`.

### 9.3 Chỗ hợp đồng JSON trong proposal cần chỉnh (tóm tắt)

1. Từ "một JSON duy nhất" sang "một luồng event, JSON gốc là bản ghi `TurnResult`" (§6.2).
2. Thêm vào mỗi khối: `v`, `id`, `source{tool,call_id,as_of}`, `fallback_text`.
3. `confirm` phải mang preview, `interrupt_id`, hạn, `reversible`/`undo_window_s`, và token xác nhận ở phía server; nhãn nút do server dựng.
4. `options.items[].effect` (`read_only` | `proposes_write`); chọn phương án = tin nhắn mới, không thực thi trực tiếp.
5. Tiền `*_vnd` số nguyên; ngày ISO; xác suất 0–1; không chuỗi đã định dạng trong dữ liệu.
6. Bổ sung các `type` còn thiếu so với danh sách proposal: `jar_summary`, `affordability_card`, `resilience_score`, `roadmap`, `receipt`, `clarify`, `ingest_progress`/`ingest_review`, `notice`, `suggestions`.
7. `trace_id` và `intent` nên phát đầu lượt qua `CUSTOM` để mọi khối bám vào.
8. Evaluator mới: `BlockSchemaValidity` (mọi khối qua Pydantic), `NumericGrounding` mở rộng cho nhãn khối LLM viết và cách viết số tiếng Việt.

### 9.4 Schema phác thảo cho các khối quan trọng nhất **[ĐX, chưa chạy thử]**

**Pydantic (nguồn sự thật):**

```python
from datetime import date, datetime
from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Source(Strict):
    tool: str
    call_id: str
    as_of: datetime            # có múi giờ +07:00

class BlockBase(Strict):
    v: int = 1
    id: str
    trace_id: str
    source: Source | None = None
    fallback_text: str = Field(max_length=280)

# ---- forecast_timeline
class Band(Strict):
    date: date
    p10: int; p50: int; p90: int            # số dư hũ, VND

class Event(Strict):
    date: date
    kind: Literal["payday", "obligation", "scenario"]
    label: str = Field(max_length=60)
    amount_vnd: int                          # âm = tiền ra

class Runout(Strict):
    date_p50: date | None                    # None = không cạn trong kỳ
    p_shortfall_before_payday: float = Field(ge=0, le=1)

class ForecastTimelineData(Strict):
    jar_id: str
    jar_name: str
    today: date
    payday: date
    series: list[Band] = Field(max_length=400)
    events: list[Event] = Field(max_length=40)
    runout: Runout
    scenario: "ScenarioOverlay | None" = None
    data_quality: Literal["high", "medium", "low"]
    data_quality_reasons: list[str] = Field(default_factory=list, max_length=3)

class ScenarioOverlay(Strict):
    label: str = Field(max_length=80)
    series: list[Band] = Field(max_length=400)
    runout: Runout

class ForecastTimeline(BlockBase):
    type: Literal["forecast_timeline"] = "forecast_timeline"
    data: ForecastTimelineData

# ---- affordability_card
class CostLine(Strict):
    label: str = Field(max_length=60)
    amount_vnd: int

class RuleResult(Strict):
    id: str
    passed: bool
    label: str = Field(max_length=80)

class AffordabilityData(Strict):
    verdict: Literal["enough", "tight", "short"]     # xanh / vàng / đỏ (kèm icon + chữ)
    item_label: str = Field(max_length=60)
    pay_with: Literal["jar", "bnpl", "loan"]
    pay_with_label: str = Field(max_length=40)
    cost_lines: list[CostLine] = Field(max_length=6)  # giá, phí, phạt nếu trễ...
    total_real_cost_vnd: int
    gap: "Gap | None" = None                         # hũ nào hụt bao nhiêu, khi nào
    runout_shift_days: int | None = None
    rules: list[RuleResult] = Field(max_length=6)

class Gap(Strict):
    jar_id: str
    amount_vnd: int
    when: date

class AffordabilityCard(BlockBase):
    type: Literal["affordability_card"] = "affordability_card"
    data: AffordabilityData

# ---- confirm (đi kèm interrupt AG-UI)
class JarDelta(Strict):
    jar_id: str; jar_name: str
    before_vnd: int; after_vnd: int

class ConfirmData(Strict):
    interrupt_id: str                                 # = Interrupt.id của AG-UI
    action_kind: Literal["move_between_jars", "assign_jar", "update_profile", "record_transaction"]
    summary: str = Field(max_length=120)              # do server dựng, không do LLM
    jars: list[JarDelta] = Field(max_length=4)
    runout_before: date | None = None
    runout_after: date | None = None
    reversible: bool
    undo_window_s: int | None = None
    requires_step_up: bool = False                    # PIN/sinh trắc học (mô phỏng)
    expires_at: datetime
    approve_label: str = Field(max_length=60)         # có số tiền, vd "Xác nhận chuyển 300.000đ"

class Confirm(BlockBase):
    type: Literal["confirm"] = "confirm"
    data: ConfirmData

# ---- options (LLM viết, qua validator)
class OptionItem(Strict):
    id: str = Field(max_length=32)
    label: str = Field(max_length=80)                 # NumericGrounding áp lên chuỗi này
    effect: Literal["read_only", "proposes_write"]

class OptionsData(Strict):
    prompt: str = Field(max_length=120)
    items: list[OptionItem] = Field(min_length=1, max_length=3)

class Options(BlockBase):
    type: Literal["options"] = "options"
    data: OptionsData

Block = Annotated[
    Union[ForecastTimeline, AffordabilityCard, Confirm, Options],  # + các khối còn lại
    Field(discriminator="type"),
]
```

**Mẫu JSON `affordability_card` (số minh họa của proposal):**

```json
{
  "type": "affordability_card", "v": 1, "id": "af:tai_nghe:run_1120", "trace_id": "tr_8f2c",
  "source": {"tool": "forecast.affordability_check", "call_id": "tc_03", "as_of": "2026-11-21T02:14:00+07:00"},
  "fallback_text": "Mua tai nghe 1.200.000đ bằng Ví Trả Sau: sát. Tổng chi phí thật 1.233.000đ, hũ Giải trí hụt 410.000đ trước ngày 5/12.",
  "data": {
    "verdict": "tight", "item_label": "Tai nghe", "pay_with": "bnpl", "pay_with_label": "Ví Trả Sau",
    "cost_lines": [{"label": "Giá", "amount_vnd": 1200000}, {"label": "Phí dịch vụ tháng", "amount_vnd": 33000}],
    "total_real_cost_vnd": 1233000,
    "gap": {"jar_id": "giai_tri", "amount_vnd": 410000, "when": "2026-12-05"},
    "runout_shift_days": 0,
    "rules": [{"id": "obligation_ratio", "passed": true, "label": "Nghĩa vụ trên thu nhập trong ngưỡng"},
              {"id": "emergency_buffer", "passed": true, "label": "Hũ Dự phòng không bị động tới"}]
  }
}
```

**Zod phía client (viết tay hoặc sinh từ JSON Schema; chỉ là dạng ý tưởng):**

```ts
import { z } from "zod";

const Base = z.object({
  v: z.number().int(), id: z.string(), trace_id: z.string(),
  source: z.object({ tool: z.string(), call_id: z.string(), as_of: z.string() }).nullish(),
  fallback_text: z.string().max(280),
});

export const Confirm = Base.extend({
  type: z.literal("confirm"),
  data: z.object({
    interrupt_id: z.string(),
    action_kind: z.enum(["move_between_jars", "assign_jar", "update_profile", "record_transaction"]),
    summary: z.string().max(120),
    jars: z.array(z.object({ jar_id: z.string(), jar_name: z.string(), before_vnd: z.number().int(), after_vnd: z.number().int() })).max(4),
    reversible: z.boolean(), undo_window_s: z.number().int().nullish(),
    requires_step_up: z.boolean(), expires_at: z.string(), approve_label: z.string().max(60),
  }),
}); // object() mặc định bỏ khóa lạ (tolerant reader); chặt ở type/v/trường bắt buộc

// Parse an toàn: lỗi → null → UnknownBlock
export function parseBlock(raw: unknown) {
  const r = BlockUnion.safeParse(raw);        // z.discriminatedUnion("type", [...])
  return r.success ? r.data : null;
}
```

**Client AG-UI mỏng (phác thảo, chưa chạy):**

```ts
import { HttpAgent, type AgentSubscriber } from "@ag-ui/client";

const agent = new HttpAgent({
  url: AGENTCORE_INVOKE_URL,                       // .../invocations
  headers: { Authorization: `Bearer ${jwt}`,
             "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": sessionId /* >= 33 ký tự */ },
  threadId,
});

const sub: AgentSubscriber = {
  onToolCallStartEvent: ({ event }) => ui.showSkeleton(SKELETON_BY_TOOL[event.toolCallName], event.toolCallId),
  onActivitySnapshotEvent: ({ event }) => {
    if (event.activityType === "yofina.block") ui.upsertBlock(parseBlock(event.content) ?? unknown(event));
  },
  onTextMessageContentEvent: ({ event, textMessageBuffer }) => ui.setText(event.messageId, textMessageBuffer),
  onRunFinishedEvent: ({ event }) => event.outcome?.type === "interrupt" ? ui.openInterrupts(event.outcome.interrupts) : ui.endTurn(),
  onRunFailed: ({ error }) => ui.showDegraded(error),
};
agent.subscribe(sub);
// Trả lời interrupt: agent.runAgent({ resume: [{ interruptId, status: "resolved", payload }] })
```

(Tên tham số của `runAgent`/`resume` ở client JS **chưa kiểm** trong phiên này; doc interrupts mô tả `resume` nằm trong `RunAgentInput`.)

## 10. Điều chưa chắc / cần thử

1. **`custom_result_handler` có phát được `ActivitySnapshotEvent`?** README adapter chỉ nói "event tùy ý (ví dụ STATE_DELTA)". Phương án dự phòng `CUSTOM` hoặc nhét khối vào `TOOL_CALL_RESULT` (spike tuần 1).
2. **Trình duyệt gọi thẳng AgentCore**: CORS, header session id, độ trễ, hành vi SSE qua mạng di động và khi màn hình khóa (iOS Safari có thể ngắt stream; cần kết nối lại bằng đọc `TurnResult` từ DB). Template FAST và Nx plugin cho thấy nối thẳng khả thi, nhưng tôi **không** kiểm tra CORS.
3. **Giấy phép CopilotKit `selfManagedAgents`**: docs ghi thuộc "Intelligence/Enterprise" nhưng AWS Labs Nx plugin vẫn dùng; không rõ mức độ thực thi. Nếu muốn dùng CopilotKit hãy hỏi trực tiếp hoặc dùng Runtime Lambda.
4. **Chất lượng Zod từ JSON Schema** (`z.fromJSONSchema` đang experimental; union `discriminator` của Pydantic). Có thể phải viết Zod tay cho 14 khối; fixtures chung vẫn cần.
5. **Giấy phép `@ag-ui/client`, `ag_ui_strands`** (chưa kiểm). Số phiên bản AI SDK (docs đã đọc dùng `isStepCount`, tên model "claude-sonnet-5.5"; tôi không xác định được số phiên bản chính xác); không dùng AI SDK trong thiết kế này nên không ảnh hưởng.
6. **Độ hạt khối và độ ổn định khi LLM chọn khối**: bài AWS Community Builders về A2UI nói khó; với thiết kế "tool tạo khối" rủi ro này nhỏ hơn, nhưng "tool nào phát khối nào, khi nào" vẫn phải thử bằng bộ 50 câu.
7. **Cửa sổ hoàn tác ~10 phút, ngưỡng bước tăng cường, ngưỡng suy giảm 2 giây** là số của tôi, cần chỉnh theo thử nghiệm.
8. **Cách trình bày xác suất** ("7 trong 10 kịch bản") là gợi ý, chưa có nguồn đã đọc; nên thử với 3–5 người dùng 18–30 tuổi.
9. **Thời hạn phiên của AgentCore khi đang chờ interrupt** (người dùng đi pha cà phê rồi quay lại bấm xác nhận): chưa kiểm; thiết kế `expiresAt` ngắn (vài phút) và xin xác nhận lại là an toàn hơn.
10. **Bài AWS ML Blog gốc**: không đọc được phần thân; kết luận về nó dựa trên bài CopilotKit đồng hành cùng ngày và các bản tóm tắt.
11. **Nielsen Norman Group**: tìm được "State of UX 2026" (trust, transparency, control) và danh sách bài về agent (tháng 4–5/2026), nhưng **chưa đọc** bài nào chuyên về mẫu tương tác agent; một con số "tăng 40% giữ chân nhờ giải thích" trên blog ParallelHQ gán cho NN/g **không kiểm chứng được**, đừng trích.
12. Một số trang kỹ thuật được đọc qua công cụ tóm tắt tự động; chi tiết chữ (tên trường, tên hook) cần mở docs gốc khi viết code.

## 11. Nguồn (truy cập 2026-11-21)

**AG-UI / AWS / Strands**
- AG-UI Events: https://docs.ag-ui.com/concepts/events [CT]
- AG-UI Interrupts: https://docs.ag-ui.com/concepts/interrupts [CT]
- AG-UI Tools (frontend tools): https://docs.ag-ui.com/concepts/tools [CT]
- AG-UI Generative UI specs: https://docs.ag-ui.com/concepts/generative-ui-specs [CT]
- `@ag-ui/client` overview: https://docs.ag-ui.com/sdk/js/client/overview ; AgentSubscriber: https://docs.ag-ui.com/sdk/js/client/subscriber [CT]
- Adapter Strands (repo): https://github.com/ag-ui-protocol/ag-ui/tree/main/integrations/aws-strands ; README/ARCHITECTURE qua raw.githubusercontent.com (`integrations/aws-strands/python/README.md`, `integrations/aws-strands/ARCHITECTURE.md`) [CT]
- AWS What's New, AG-UI trên AgentCore Runtime (2026-03-13): https://aws.amazon.com/about-aws/whats-new/2026/03/amazon-bedrock-agentcore-runtime-ag-ui-protocol [CT]
- AgentCore AG-UI docs: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-agui.html ; contract: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-agui-protocol-contract.html (chỉ thấy qua kết quả tìm kiếm)
- AWS ML Blog (≈2026-06-30), thân bài chưa đọc được: https://aws.amazon.com/blogs/machine-learning/build-generative-ui-for-ai-agents-on-amazon-bedrock-agentcore-with-the-ag-ui-protocol/
- CopilotKit, bài đồng hành (2026-06-30): https://www.copilotkit.ai/blog/generative-ui-on-agentcore-with-copilotkit [BLOG]
- Strands community integration AG-UI: https://strandsagents.com/docs/community/integrations/ag-ui/ [CT]
- AWS Labs Nx plugin, React ↔ AG-UI: https://awslabs.github.io/nx-plugin-for-aws/en/guides/connection/react-agui [CT]
- AWS Builder Center, CopilotKit nối AgentCore harness: https://builder.aws.com/content/3GbKQ818IeQUpt9yHfsAQvXMpFF/wiring-copilot-kit-to-a-managed-bedrock-agent-core-harness [BLOG]
- A2UI × AG-UI × Strands (AWS Community Builders): https://dev.to/aws-builders/a2ui-x-ag-ui-building-an-ai-agent-that-supports-a2ui-v09-with-copilotkit-and-strands-agents-37k1 [BLOG]

**Thư viện giao diện / đặc tả**
- CopilotKit repo: https://github.com/CopilotKit/CopilotKit (MIT, ~38,9k sao) [CT]
- CopilotKit self-managed agents: https://docs.copilotkit.ai/backend/self-managed-agents [CT]
- CopilotKit generative UI / `useComponent`: https://docs.copilotkit.ai/generative-ui ; specs: https://docs.copilotkit.ai/generative-ui/specs ; tool rendering: https://docs.copilotkit.ai/generative-ui/tool-rendering [CT]
- CopilotKit generative-ui repo: https://github.com/CopilotKit/generative-ui [CT]
- CopilotKit, "The developer's guide to generative UI in 2026": https://dev.to/copilotkit/the-developers-guide-to-generative-ui-in-2026-1bh3 [BLOG]
- assistant-ui repo: https://github.com/assistant-ui/assistant-ui (MIT) ; AG-UI runtime docs (qua tìm kiếm): https://www.assistant-ui.com/docs/runtimes/ag-ui [CT/search]
- A2UI: https://a2ui.org/ ; spec v1.0: https://a2ui.org/specification/v1.0-a2ui/ ; repo: https://github.com/google/A2UI [CT]
- json-render: https://github.com/vercel-labs/json-render ; streaming: https://json-render.dev/docs/streaming [CT]
- OpenUI (trước là Thesys C1): https://www.openui.com/docs [CT]
- MCP Apps: https://modelcontextprotocol.io/extensions/apps/overview [CT]
- Vercel AI SDK, generative UI: https://ai-sdk.dev/docs/ai-sdk-ui/generative-user-interfaces ; RSC (experimental): https://ai-sdk.dev/docs/ai-sdk-rsc/overview [CT]
- Zod JSON Schema: https://zod.dev/json-schema [CT]
- Partial JSON streaming (tổng hợp): https://dev.to/james_oconnor_dev/-the-partial-json-looked-done-it-wasnt-heres-what-streaming-structured-output-actually-j0e ; https://tianpan.co/blog/2026/04/27/streaming-json-parser-typed-object-gap [BLOG]

**UX / tài chính / an toàn**
- Microsoft, 18 Guidelines for Human-AI Interaction: https://www.microsoft.com/en-us/research/articles/guidelines-for-human-ai-interaction-eighteen-best-practices-for-human-centered-ai-design/ [CT]
- Google PAIR, Explainability + Trust: https://pair.withgoogle.com/chapter/explainability-trust/ ; Errors + Graceful Failure: https://pair.withgoogle.com/chapter/errors-failing/ [CT]
- Shape of AI: https://www.shapeof.ai/ [CT]
- Smashing Magazine, Designing for Agentic AI (02/2026): https://smashingmagazine.com/2026/02/designing-agentic-ai-practical-ux-patterns/ [BLOG]
- NN/g, State of UX in 2026: https://www.nngroup.com/articles/state-of-ux-2026/ [CT]
- Anthropic, Building effective agents: https://www.anthropic.com/engineering/building-effective-agents [CT]
- CFPB, Chatbots in consumer finance (2023-06-06): https://www.consumerfinance.gov/data-research/research-reports/chatbots-in-consumer-finance/chatbots-in-consumer-finance/ [CT]
- Revolut AIR, phân tích UX: https://ergomania.eu/revolut-air-ai-banking-assistant-ux/ [BLOG]; điều khoản: https://www.revolut.com/legal/rita-disclaimer/ (không đọc trực tiếp; 403)
- Bank of America Erica: https://newsroom.bankofamerica.com/content/newsroom/press-releases/2026/03/bofa-ai-and-digital-innovations-fuel-30-billion-client-interacti.html ; CMSWire: https://www.cmswire.com/digital-experience/bank-of-americas-ai-playbook-what-cx-leaders-can-learn-from-ericas-long-game/ [BLOG]
- OWASP LLM05:2025 Improper Output Handling: https://genai.owasp.org/llmrisk/llm052025-improper-output-handling/ [CT]
- Markswebb, AI in digital banking: https://markswebb.com/insights/ai-in-digital-banking-from-smart-feature-to-trusted-interface/ (403, chỉ thấy tóm tắt tìm kiếm) [?]
