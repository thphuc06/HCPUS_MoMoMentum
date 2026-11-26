# agent/

Agent Strands chạy trên AgentCore Runtime (giao thức AG-UI qua SSE). Phase 1 (luồng D) đã cài: router, đường nhanh một tool, khối UI, xác nhận chuyển hũ bằng khối `confirm`, đường suy giảm, đóng zip ARM64. Phase 2 (luồng C) thêm ý định `forecast_lookup` (hỏi dự báo một hũ) với tool `forecast___get_forecast` và khối `forecast_timeline`. Harness đầy đủ L0–L5 (Orchestrator, specialist, Verifier, Composer) là việc của phase 3.

- Proposal: §9, §10.1–§10.6, §12. Tool agent gọi nằm ở [../gateway/tools/](../gateway/tools/README.md); agent không chứa logic số.
- Mẫu và bẫy đã chạy thật: [spike Strands](../docs/research/spike-strands-agui-local.md), [spike Runtime](../docs/research/spike-agentcore-runtime-cors.md). Quyết định xác nhận: [ADR-0002](../docs/decisions/0002-xac-nhan-truoc-khi-ghi.md).

## Kiến trúc

"Cách B": mã điều khiển thứ tự và tự phát event AG-UI (`ag_ui.core` + `EventEncoder`), không dùng `StrandsAgent` của `ag-ui-strands` (router, khối UI, suy giảm và `turn_blocks` nằm ngoài vòng lặp của một Agent; cần giữ đúng thứ tự event). Strands được dùng cho `MCPClient` (tool qua Gateway), `Agent` viết câu trả lời và `Model` đo đếm.

```
POST /invocations ──> app.py: sub từ Authorization (identity.py), trace_id từ traceparent, conversation_id = session id
   RUN_STARTED (đi ngay, trước khi nạp cấu hình)
   turn.py ──> danh sách hũ cho router: mục `yofina.wallet` trong `context` của lượt (frontend gửi), hợp lệ thì không đọc ví;
               không có thì get_jar_balances IM LẶNG (chưa phát TOOL_CALL_*), phát khi phần sau của lượt dùng kết quả
       ──> router.py (vai `small`, JSON bằng ép tool, tối đa router_max_attempts lần)
        └ lỗi/chạm trần ──> fallback.py (luật tối thiểu; suy giảm có kiểm soát)
      balance_lookup      get_jar_balances ──ACTIVITY_SNAPSHOT(jar_summary)──> TOOL_CALL_RESULT(bản gọn) ──> writer.py (1 câu)
      transactions_lookup get_jar_balances (ánh xạ tên hũ) + query_transactions ──> writer.py
      forecast_lookup     get_jar_balances (ánh xạ tên hũ) + forecast___get_forecast ──ACTIVITY_SNAPSHOT(forecast_timeline)──> writer.py (1 đến 2 câu)
      move_between_jars   get_jar_balances (ánh xạ tên hũ) + move_between_jars KHÔNG token
                          ──NEEDS_CONFIRMATION──> ACTIVITY_SNAPSHOT(confirm) ──> writer.py (nhắc bấm Xác nhận)
      out_of_scope        khối notice + câu nói rõ giới hạn
      chitchat            câu trả lời của router
   [notice nếu suy giảm] ──> lưu turn_blocks (store.py) ──> RUN_FINISHED (result + usage token)
```

| File | Việc |
|---|---|
| `src/yofina_agent/app.py` | ASGI: `POST /invocations`, `GET /ping` (`Healthy`); làm nóng bằng `forwardedProps.warmup` (không gọi model/tool) |
| `identity.py` | Bóc `sub` từ JWT đã được Runtime xác minh; không nhận `user_id` từ payload; giữ token để chuyển cho Gateway |
| `turn.py` | Một lượt: thứ tự event, ánh xạ ý định, đường suy giảm, giới hạn (thời gian, số lượt gọi model, số tool call) |
| `router.py`, `fallback.py` | Router LLM (năm ý định: số dư, giao dịch, dự báo một hũ, chuyển hũ, ngoài phạm vi/xã giao); bộ phân loại luật dự phòng (từ khóa chung: cạn, trụ được, bao lâu, dự báo; không theo câu mẫu nào) |
| `jars.py` | Ánh xạ "giải trí" -> `giai_tri` bằng danh sách hũ của chính người dùng (từ tool), không bảng gắn cứng |
| `tools.py` | `GatewayTools` (Strands `MCPClient`, header `Authorization` nguyên vẹn), phân loại kết quả/lỗi (Cedar -32002), dựng khối bằng `yofina_core.blocks` |
| `compact.py`, `writer.py` | Bản gọn model được thấy (`compact_forecast`: trạng thái, ngày cạn `dd/mm`, số ngày tới kỳ lương, nhóm tin cậy hoặc xác suất, ước lượng ban đầu, cũ hay không, ba mốc sắp tới, mỗi số tiền kèm `*_text`); model nhỏ viết 1 đến 2 câu; kiểm số tiền model viết có căn cứ không |
| `metered_model.py` | `Model` của Strands đi qua cùng lớp đếm/giới hạn/dự phòng của `yofina_core.llm` |
| `store.py` | Cổng lưu `turn_blocks` (xem "Việc cho bước ghép") |
| `notices.py`, `defaults.json`, `settings.py` | Chuỗi nội dung `notice` theo mã lỗi; mặc định và đọc cấu hình |
| `main.py` | Entrypoint của Runtime (uvicorn :8080) |

`yofina_core.llm` (libs): mọi lời gọi Bedrock đi qua `LlmGateway`: chuỗi dự phòng theo vai (bắt `ThrottlingException` và `AccessDeniedException`), giới hạn tốc độ mỗi model (cửa sổ 60 giây), trần ngày đếm nguyên tử ở DynamoDB `yofina-usage` (chạm trần: `ModelBudgetExceeded`, không rơi sang model dự phòng), trần mỗi lượt hội thoại, log token. Cấu hình ở `libs/yofina_core/src/yofina_core/llm_defaults.json`.

## Danh sách hũ cho router (`context` của lượt, #39)

Router chọn hũ chi theo danh sách hũ của ví (`<hu_cua_vi>`) và đổi hạn mục tiêu ra ngày theo ngày mô phỏng (`<ngay_hom_nay>`). Frontend gửi hai thứ đó trong `context` của `RunAgentInput` (trường sẵn có của AG-UI), một mục tùy chọn:

```
{"description": "yofina.wallet", "value": "{\"app_date\": \"2026-11-21\", \"jars\": [{\"code\": \"an_uong\", \"name\": \"Ăn uống\", \"kind\": \"spending\"}, ...]}"}
```

`jars`: hũ người dùng từ `GET /overview` (mã, tên, `kind`, `purpose` nếu có; không số dư, không hũ hệ thống), tối đa 20; frontend không gửi khi dữ liệu đang tải hay đang tải lại sau một lần ghi. Agent kiểm chặt (`router.wallet_context`), sai một chỗ là bỏ cả mục và đọc ví như cũ. Danh sách này chỉ vào prompt router, đánh dấu là dữ liệu; mọi tính toán sau đó (hũ trả, số dư, kịch bản, lộ trình) đọc ví bằng tool phía server, mã hũ router chọn phải có trong lần đọc đó. Thứ tự deploy: đổi được theo thứ tự nào cũng chạy (Runtime cũ bỏ qua `context`; frontend cũ không gửi thì Runtime mới đọc ví im lặng), nên deploy frontend và Runtime cùng đợt.

## Ý định `forecast_lookup` (phase 2)

"Hũ ăn uống còn trụ được bao lâu", "khi nào hũ giải trí cạn": router (model nhỏ, JSON ép tool) trả `forecast_lookup` kèm `jar_text`; `turn.on_forecast` ánh xạ tên hũ bằng danh sách hũ của chính người dùng (`get_jar_balances`, không bảng gắn cứng), gọi `forecast___get_forecast {jar}` qua Gateway (target `forecast`, tên tool lấy tiền tố từ `forecast_tool_prefix`), bọc `data` của tool thành khối `forecast_timeline` bằng `yofina_core.blocks.build_forecast_timeline_from_data` (số của tool, không tính lại: cùng số với `GET /forecasts/{jar}`) rồi để model nhỏ viết 1 đến 2 câu từ bản gọn; số tiền trong câu phải có trong bản gọn (bộ kiểm số sẵn có `check_grounding`; ngày `dd/mm` và số ngày do bản gọn cho sẵn). Không nêu hũ nào thì hỏi lại (hiện thẻ số dư thật); hũ không có thì hỏi lại kèm danh sách hũ. Router lỗi hoặc chạm trần thì bộ phân loại dự phòng vẫn nhận ra ý định bằng từ khóa chung, tên hũ vẫn ánh xạ bằng dữ liệu tool, và người dùng vẫn nhận khối `forecast_timeline` thật kèm khối `notice` suy giảm. Lỗi của tool (`FORECAST_UNAVAILABLE`, `PROFILE_INCOMPLETE`...) thành khối `notice` với tiêu đề theo mã. Một lượt tốn tối đa 2 lượt gọi model (router và viết câu) và 2 tool call.

## Hợp đồng đầu ra

- Khối UI phát bằng `ACTIVITY_SNAPSHOT` (`activityType: "yofina.block"`, `messageId` = `block.id`, `replace: true`) **trước** `TOOL_CALL_RESULT` của tool sinh ra nó; `TOOL_CALL_RESULT` chỉ mang bản gọn.
- Lần đọc ví chỉ để dựng danh sách hũ cho router (khi lượt không có mục `yofina.wallet`) là một tool call thật (đếm trần, bản ghi lượt) nhưng **im lặng**: `TOOL_CALL_START/ARGS/END/RESULT` của nó giữ lại, chỉ phát khi phần sau của lượt dùng kết quả (tra số dư, ánh xạ tên hũ, suy hũ trả, lập lộ trình...), và khối số dư khi đó vẫn đứng trước `TOOL_CALL_RESULT`. Lượt xã giao, ngoài phạm vi, phí, tỷ giá, thói quen, nạp, điểm không có thẻ tool "Số dư các hũ".
- Agent không bao giờ điền cờ xác nhận hay token; khối `confirm` chứa đúng dữ liệu tool trả (đã kiểm `params_hash` bằng `build_confirm`). Đường ghi thật do frontend gọi REST.
- Chạm giới hạn, model lỗi hay `ModelBudgetExceeded`: vẫn trả khối số liệu từ tool + khối `notice` (`kind: degraded`), kết thúc `RUN_FINISHED`; lỗi giữa lượt thành `notice` + `RUN_FINISHED`. `RUN_ERROR` chỉ xuất hiện khi lỗi xảy ra trước khi lượt dựng xong.
- `RUN_FINISHED.result`: `trace_id`, `intent`, `degraded`, `model_calls`, `tool_calls`; `usage`: token theo model.
- Request sai (thiếu/sai token, payload hỏng): HTTP 401/422 với `{"error": {code, message}}`.

## Biến môi trường

| Biến | Bắt buộc | Ý nghĩa |
|---|---|---|
| `YOFINA_GATEWAY_URL` | có | URL MCP của AgentCore Gateway (bước ghép đặt; hoặc SSM `<prefix>/gateway_url`) |
| `YOFINA_REGION` hoặc `AWS_REGION` | có | Region tường minh (Runtime tự đặt `AWS_REGION`) |
| `YOFINA_SSM_PREFIX` | khuyến nghị | `/yofina`: đọc tên bảng usage (`/yofina/dynamodb/usage-table`), nhánh `/yofina/llm/*` (một lời gọi `GetParametersByPath`), `gateway_url` |
| `YOFINA_USAGE_TABLE` | không | Ghi đè tên bảng đếm lượt gọi |
| `YOFINA_LLM_ROLES` (JSON), `YOFINA_LLM_DAILY_CAP_<VAI>`, `YOFINA_LLM_RATE_LIMIT_MAX_WAIT_SECONDS`, `YOFINA_LLM_BUDGET_TIMEZONE`... | không | Ghi đè cấu hình model/trần/tốc độ (SSM tương ứng: `/yofina/llm/roles`, `/yofina/llm/daily_cap_planner`...) |
| `YOFINA_RUN_TIMEOUT_SECONDS`, `YOFINA_MAX_MODEL_CALLS_PER_TURN`, `YOFINA_MAX_TOOL_CALLS_PER_TURN`, `YOFINA_TOOL_TIMEOUT_SECONDS`, `YOFINA_ROUTER_MAX_ATTEMPTS`, `YOFINA_HISTORY_MESSAGES`, ... | không | Tham số của agent (mặc định ở `src/yofina_agent/defaults.json`; chỉ đọc từ env, không tra SSM từng khóa) |
| `YOFINA_TURN_BLOCKS_TOOL` | không | Tên tool Gateway để lưu `turn_blocks` (rỗng = chưa lưu) |
| `YOFINA_TURN_RECORD_TOOL` | không | Tên tool Gateway để ghi bản ghi lượt `agent_turn` (Runtime đặt `audit___record_turn`; rỗng = chưa ghi, "Vì sao" và `POST /feedback` sẽ 404) |
| `YOFINA_LOG_LEVEL` | không | Mặc định INFO |

## Chạy cục bộ

```bash
uv sync
uv run pytest tests/unit/agent libs                          # unit test
uv run python scripts/agent_run_local.py --mock               # agent + MCP giả (tests/support) ở :8080/:8201
uv run scripts/agent_call_local.py --message "số dư các hũ của mình"
uv run python scripts/agent_run_local.py --mock --cap-small 0 --cap-planner 0   # thử đường suy giảm
```

Chạy local gọi Bedrock thật (Region `ap-southeast-1`, profile mặc định; máy dùng `aws login` cần `awscrt`, đã có trong nhóm dev) và đếm vào `yofina-usage` thật. `tests/support/mock_ledger_mcp.py` chỉ để dev/test: không nằm trong gói sản phẩm và `agent/` không import nó. Trỏ Gateway thật bằng `--gateway-url` hoặc `YOFINA_GATEWAY_URL`.

## Đóng gói

```bash
uv run scripts/agent_build_zip.py        # -> build/agent/agent-arm64.zip (khoảng 31 MB nén, 65 MB giải nén)
```

Cài wheel Linux ARM64 ngay trên Windows bằng `uv` (không Docker) từ danh sách đã khóa trong `uv.lock`; chép `main.py`, `yofina_agent`, `yofina_core`. Chỉ build, không upload. Tạo Runtime: `entryPoint: ["main.py"]`, `runtime: PYTHON_3_13`, `serverProtocol: AGUI`, platform V2, `requestHeaderAllowlist` có `Authorization` (và `traceparent` đã được chuyển tiếp không cần khai).

## Deploy lên AgentCore Runtime

Stack `YofinaAgent` ([infra-cdk/lib/agent-stack.ts](../infra-cdk/lib/agent-stack.ts)) tạo Runtime `yofina_agent` (CodeZip ARM64 `PYTHON_3_13`, `entryPoint ["main.py"]`, `serverProtocol AGUI`, platform **V2**, `customJWTAuthorizer` với `allowedClients` = app client `yofina-web`, `requestHeaderAllowlist ["Authorization"]`, mạng PUBLIC), vai IAM `yofina-agent-runtime` (quyền tối thiểu: `bedrock:InvokeModel*` chỉ cho các model/inference profile trong `llm_defaults.json`, `dynamodb:UpdateItem` trên `yofina-usage`, `ssm:GetParameter(sByPath)` trên `/yofina/gateway_url`, `/yofina/dynamodb/usage-table`, `/yofina/llm/*`, `s3:GetObject` trên `builds/*`, log, X-Ray, `PutMetricData` namespace `bedrock-agentcore`, workload identity) và biến môi trường `YOFINA_REGION`, `YOFINA_SSM_PREFIX=/yofina`, `YOFINA_GATEWAY_URL`, `YOFINA_USAGE_TABLE`, `YOFINA_TURN_BLOCKS_TOOL=ledger___save_turn`, `YOFINA_LOG_LEVEL`. ARN, id và URL invoke ghi vào SSM `/yofina/agent/runtime-arn`, `runtime-id`, `runtime-url`.

```bash
uv run scripts/agent_deploy.py                  # build zip -> upload builds/agent-<sha>.zip -> ghi SSM /yofina/agent/zip-key -> cdk deploy YofinaAgent -> chờ READY
uv run scripts/agent_deploy.py --skip-build     # dùng build/agent/agent-arm64.zip đã có
uv run scripts/agent_deploy.py -c policyMode=LOG_ONLY    # tham số sau -c chuyển cho CDK
uv run scripts/print_env.py frontend --write    # frontend/.env.local: VITE_AGENT_RUNTIME_URL, VITE_AGENT_RUNTIME_ARN, ...
```

- Cập nhật Runtime V2 mất khoảng 5 phút mỗi lần (tạo mới cũng ~5 phút): gom thay đổi rồi deploy một lần. Zip đặt tên theo hash nội dung nên cùng mã thì không làm gì. Đổi Gateway/Cedar không đụng Runtime.
- Phiên mới ở lượt đầu mất khoảng 2 giây tới event đầu (cold start microVM), lượt hai trong cùng phiên khoảng 0,3 giây ([spike-vertical-slice.md](../docs/research/spike-vertical-slice.md) mục 7). Frontend nên gửi một lượt `forwardedProps.warmup: true` khi mở chat.
- `conversation_id` = session id (header `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id`, 33 đến 256 ký tự). Mọi lượt (kể cả suy giảm) được lưu bằng tool `ledger___save_turn` ngay trước `RUN_FINISHED`; frontend đọc lại bằng `GET /conversations/{id}` ([contracts/README.md](../contracts/README.md)). Lưu thêm khoảng 0,3 giây trước `RUN_FINISHED`; lỗi lưu chỉ ghi log.
- Token hết hạn lúc mở phiên MCP tới Gateway (JSON-RPC `-32001 Invalid Bearer token`) ra `notice` "Cần đăng nhập lại"; Cedar từ chối (`-32002`) ra "Không có quyền thực hiện".
- Kiểm thật (cần Runtime đã deploy): `uv run pytest tests/integration/test_agent_runtime.py -m integration`.
