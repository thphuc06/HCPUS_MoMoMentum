# contracts/

Nguồn duy nhất cho **hợp đồng** giữa frontend, agent, Lambda tool, REST, sự kiện và ML. Mọi bên đọc từ đây; muốn đổi hợp đồng thì sửa ở đây trước, rồi sinh lại và chạy test. Kế hoạch: [phase 1 mục "Bước 0"](../docs/plan/phases/phase-1-nen-va-lat-doc.md), [phase 2 mục "Bước 0"](../docs/plan/phases/phase-2-vi-va-du-bao.md), [phase 3 mục "Bước 0"](../docs/plan/phases/phase-3-what-if-va-kiem-tra.md), [phase 4 mục "Bước 0"](../docs/plan/phases/phase-4-chong-chiu-lo-trinh.md); quyết định liên quan: [ADR-0002](../docs/decisions/0002-xac-nhan-truoc-khi-ghi.md) (xác nhận trước khi ghi), [ADR-0003](../docs/decisions/0003-dong-ho-mo-phong.md) (đồng hồ mô phỏng); các lựa chọn thiết kế của phase 2 (hũ hệ thống, nguồn trả, tổng số dư...) ở mục "Quyết định hợp đồng phase 2" cuối [file phase 2](../docs/plan/phases/phase-2-vi-va-du-bao.md); của phase 3 (what-if, kiểm tra trước khi quẹt, luật suitability) ở "Quyết định hợp đồng phase 3" cuối [file phase 3](../docs/plan/phases/phase-3-what-if-va-kiem-tra.md); của phase 4 (điểm chống chịu, cú sốc, lộ trình, phân hũ tự động) ở "Quyết định hợp đồng phase 4" cuối [file phase 4](../docs/plan/phases/phase-4-chong-chiu-lo-trinh.md); của phase 5 (hồ sơ hành vi, bản tin, bộ nhớ, trích dẫn biểu phí, xóa dữ liệu, trace) ở "Quyết định hợp đồng phase 5" trong [file phase 5](../docs/plan/phases/phase-5-nap-du-lieu-ho-so-trace.md).

| Thư mục / file | Nội dung | Ai dùng |
|---|---|---|
| `blocks/envelope.schema.json` | Phong bì chung của khối UI và các kiểu cơ bản (`Vnd`, `VndSigned`, `Ratio`, `JarCode`, `IsoDate`...) | tất cả |
| `blocks/{jar_summary,confirm,receipt,notice}.schema.json` | Bốn khối của phase 1 (`confirm` và `receipt` chỉ cho chuyển hũ) | agent (dựng), frontend (vẽ) |
| `blocks/forecast_timeline.schema.json` | Dự báo 30 ngày của một hũ, dùng chung màn Chi tiết hũ và chat | luồng C (dựng), D (vẽ), agent |
| `blocks/proactive_card.schema.json` | Thẻ chủ động (một việc) trên Tổng quan | luồng A (dựng), D (vẽ) |
| `blocks/{confirm_action,receipt_action}.schema.json` | Xác nhận và biên nhận của MỌI tool ghi khác chuyển hũ | luồng A, agent (dựng), D (vẽ) |
| `blocks/{affordability_card,obligation_impact,options,explain,clarify,suggestions}.schema.json` | Sáu khối phase 3 (xem mục "Phase 3"); `notice` và `forecast_timeline` được mở rộng tương thích ngược | luồng A (dựng số), agent, C (vẽ) |
| `blocks/{ingest_review,coverage_change}.schema.json` | Bảng duyệt một lần nạp ảnh hoặc CSV và độ phủ dữ liệu trước/sau (phase 5) | luồng A phase 5 (dựng), frontend (vẽ) |
| `blocks/{resilience_score,stress_result,roadmap,roadmap_diff,review_list}.schema.json` | Năm khối phase 4 (xem mục "Phase 4") | luồng A, B (dựng số), agent, D (vẽ) |
| `blocks/{behavior_insight,citation}.schema.json` | Hai khối phase 5: nhận xét hành vi kèm bằng chứng số và một việc cần làm (`$defs` cũng là hình dạng hồ sơ hành vi), trích dẫn nguồn biểu phí dựng từ `get_fee_schedule`; `proactive_card` mở rộng cho bản tin (xem mục "Phase 5 (F7, trích dẫn biểu phí, quyền riêng tư, trace)") | luồng p5-behavior, agent (dựng), p5-frontend (vẽ) |
| `blocks/block.schema.json` | Hợp của hai mươi ba khối, phân biệt theo `type` | kiểm tra |
| `tools/ledger.json` | Mười tool của target `ledger` (chín tool của overview và `save_turn`) đúng định dạng `inlinePayload` của AgentCore Gateway (Lambda target) | luồng A (cài), agent |
| `tools/forecast.json` | Bảy tool của target `forecast`: `get_forecast` (phase 2), `run_scenario`, `list_scenarios` (gộp kịch bản trong một cuộc chat), `affordability_check` (phase 3), `get_resilience_score`, `stress_test` (phase 4), `get_behavior_profile` (phase 5) | luồng C phase 2, A phase 3 và 4, p5-behavior (cài), agent |
| `tools/{knowledge,planner,audit}.json` | Target mới của phase 3: `get_fee_schedule`; `check_suitability`, `schedule_nudge` (tool GHI qua token); `get_trace`, `record_turn` (ghi bản ghi lượt, không qua token). Phase 4 thêm vào `planner`: `optimize_allocation`, `save_roadmap` (GHI không qua token), `get_roadmap`. Phase 5 không thêm tool tìm kiếm vào `knowledge` (RAG đã cắt 24/11); 25/11 thêm `get_exchange_rate` (tỷ giá ngoại tệ, cùng hàm với pipeline nạp) | luồng A (cài), agent |
| `tools/ingest.json`, `tools/ingest.results.schema.json` | Ba tool của target `ingest` (phase 5) và kết quả | luồng A phase 5 (cài), agent |
| `scenario/scenario_spec.schema.json` | `ScenarioSpec`: sáu loại kịch bản what-if (FR5), nguồn chung cho `run_scenario`, bảng `scenarios`, `yofina_core.scenario` | agent (dựng), luồng A (kiểm, chạy) |
| `tools/{ledger,forecast,knowledge,planner,audit}.results.schema.json` | Kết quả JSON Lambda trả về cho từng tool; `ledger.results` còn chứa các $defs dùng chung với REST (`Transaction`, `Obligation`, `CreditLine`, `Payee`, `SalaryEvent`) | luồng A, C (trả), agent (đọc) |
| `rest/openapi.yaml` | OpenAPI 3.1: 52 thao tác (xem mục "REST", "Phase 3", "Phase 5", "Phase 4" và "Biểu đồ chi tiêu") | luồng A, C (cài), D (gọi) |
| `events/*.schema.json` | `detail` của sự kiện trên EventBridge bus `yofina-bus`: `transaction.recorded`, `salary.confirmed`, `obligation.changed`, `profile.updated`, `forecast.updated`; phase 4 thêm `behavior.changed`, `roadmap.regeneration_requested` | luồng A (phát), C (nghe) |
| `ml/forecast_io.schema.json` | Dạng JSON của đầu vào và đầu ra `yofina_ml.forecast_user` | luồng B, C |
| `ml/{resilience_config,shock_set}.schema.json` | Định dạng của `resilience_defaults.json` (trọng số, ngưỡng điểm chống chịu) và `shocks.json` (ba cú sốc mẫu), hai file dữ liệu nằm trong `libs/yofina_core/src/yofina_core/` | luồng A (đọc) |
| `fixtures/` | Ví dụ JSON dùng chung cho test Python và TypeScript (`blocks/`, `tools/`, `rest/`, `events/`, `ml/`, `scenario/`) | test |

Sinh và kiểm: [scripts/gen_contracts.mjs](../scripts/gen_contracts.mjs). Mã tương ứng: Pydantic ở [libs/yofina_core](../libs/yofina_core/README.md) (`blocks.py`, `wallet.py`, `errors.py`, `clock.py`, `scenario.py`, `suitability.py`, `resilience.py`, `roadmap.py`; phase 5 thêm `memory.py`, `privacy.py`), Zod ở `frontend/src/contracts/blocks.ts` (file sinh ra, không sửa tay), kiểu ML ở [ml/yofina_ml](../ml/README.md).

## Quy ước

### Số tiền, ngày, giờ

- **Tiền là số nguyên VND** ở mọi nơi: JSON, tham số tool, REST, cột `numeric(14,0)`. Không có float, không có chuỗi, không có phần thập phân. Trong Python dùng `int`/`Decimal`; Aurora trả `numeric` dạng chuỗi nên đổi bằng `yofina_core.money.to_vnd`. Số nguyên tối đa 99.999.999.999.999 (khớp `numeric(14,0)`). Số tiền có dấu chỉ xuất hiện ở dòng sổ cái (`Transaction.amount_vnd`: âm là tiền ra khỏi hũ); chỗ khác dùng số dương, hướng nằm ở tên trường.
- **Hiển thị**: `1.200.000 ₫` ở thẻ, `1,2 triệu` ở câu hỏi và lời giải thích (`format_vnd`, `format_vnd_short`). Frontend tự định dạng từ số nguyên; `fallback_text` do code dựng sẵn.
- **Ngày** (`IsoDate`, `YYYY-MM-DD`) là **ngày mô phỏng** của người dùng (ADR-0003), trừ khi trường nói khác. **Thời điểm** (`IsoDateTime`, RFC 3339) là thời gian thật, server phát ở UTC với hậu tố `Z`: `as_of`, `occurred_at`, `expires_at`.
- Phần trăm (`split_percent`) là số thực 0..100, không phải tiền.

### Khối UI

- **Phong bì**: `v`, `id`, `type`, `trace_id`, `fallback_text`, `source`, `data`, đủ cả bảy trường.
  - `v`: phiên bản hợp đồng của khối, hiện là `1`. Chỉ tăng khi đổi không tương thích ngược (đổi nghĩa, bỏ, đổi kiểu hoặc thêm trường bắt buộc). Thêm trường tùy chọn thì không tăng `v`.
  - `id`: ổn định trong lượt; cùng `id` thì khối sau **thay** khối trước (`ACTIVITY_SNAPSHOT` với `replace: true`). Quy tắc dựng: `jar_summary:{trace_id}`; `confirm:{trace_id}:{params_hash[:12]}`; `receipt:{transaction_id}`; `notice:{trace_id}:{code hoặc kind}`.
  - `trace_id`: của lượt, lấy từ `traceparent` (`trace_id_from_traceparent`); REST không có thì server sinh (`new_trace_id`).
  - `fallback_text`: một câu tiếng Việt để hiện khi frontend không vẽ được khối. Do **code** dựng từ số liệu thật; LLM không viết.
  - `source`: `tool` (hoặc `rest:<method> <path>`), `as_of` (lúc đọc), `app_date` (ngày mô phỏng lúc đó).
- **Số trong khối do code dựng từ kết quả tool**, qua `yofina_core.blocks.build_*`; LLM không thấy khối.
- **Phía sinh chặt, phía đọc dễ tính.** JSON Schema và Pydantic dùng `additionalProperties: false`/`extra="forbid"` để lỗi của producer lộ ngay. Zod sinh ra dùng `z.object` thường (trường lạ bị bỏ), nên producer thêm trường tùy chọn thì frontend cũ vẫn chạy. Frontend parse **từng khối riêng** bằng `blockSchemas[type]`; `type` lạ hoặc sai schema thì hiện `fallback_text` (lấy được nhờ `BlockEnvelope`).
- **`confirm` chứa đúng thứ sẽ được ký**: `tool`, `params` (đã chuẩn hóa, không có `user_id`), `params_hash`; phần `summary`, `preview` (số dư hai hũ trước → sau) và `expires_at` chỉ để hiển thị. `params_hash = sha256(canonical_json({"tool", "params"}))`, cách tính ở `yofina_core.confirm`. `expires_at` là hạn của *đề nghị* (quá hạn thì hỏi lại); hạn của *token* (`ttl_seconds`) chỉ bắt đầu khi người dùng bấm và nằm trong cấu hình.
- **`receipt`**: `transaction_id` (UUID; với chuyển hũ là `transfer_id` chung của hai dòng sổ cái), `occurred_at`, `app_date`, số dư sau của hai hũ.
- **`notice`**: `kind` ∈ `out_of_scope` | `degraded` | `low_data` | `error` | `info` (phase 4: trạng thái trống hoặc chỉ mang thông tin, không phải lỗi; giao diện vẽ màu trung tính); không chứa số liệu tài chính.
- **Thêm một loại khối**: tạo `blocks/<type>.schema.json` (theo mẫu: phong bì + `data`), thêm vào `block.schema.json` và `FILES` trong `scripts/gen_contracts.mjs`, viết model Pydantic và `build_*` trong `blocks.py`, thêm fixture hợp lệ và không hợp lệ, chạy `uv run pytest` và `node scripts/gen_contracts.mjs`.
- **`BLOCK_TYPES` của Zod chỉ gồm khối mà registry frontend đã đăng ký.** `frontend/src/contracts/blocks.ts` xuất `blockSchemas`, `ALL_BLOCK_TYPES` và `Block` cho MỌI khối trong `block.schema.json` (hai mươi ba khối sau bước 0 của phase 5), nhưng `BLOCK_TYPES` và kiểu `BlockType` chỉ liệt kê khối đã có view (nay hai mươi mốt; `behavior_insight` và `citation` chưa có view) (hằng `REGISTERED_BY_FRONTEND` trong `scripts/gen_contracts.mjs`), vì `registry.tsx` dùng `Record<BlockType, Entry>` phải đủ khóa. Khối chưa đăng ký hiện `fallback_text` (không vỡ trang). **Luồng frontend thêm khối mới vào `REGISTERED_BY_FRONTEND` cùng lúc với việc đăng ký view trong `registry.tsx`** (phase 2 đã làm cho `forecast_timeline`, `proactive_card`, `confirm_action`, `receipt_action`; phase 3 làm cho `affordability_card`, `obligation_impact`, `options`, `explain`, `clarify`, `suggestions`; phase 5 làm cho `ingest_review`, `coverage_change`; năm khối phase 4 CHƯA có view nên chưa vào danh sách, luồng D thêm khi đăng ký).

### Tool `ledger` (AgentCore Gateway)

- Target tên `ledger`; tên đầy đủ qua Gateway là `ledger___<tool>`. Giữ ngắn vì Bedrock Converse giới hạn 64 ký tự.
- `tools/ledger.json` là mảng `ToolDefinition` đúng như truyền vào `toolSchema.inlinePayload`: `{"name", "description", "inputSchema"}`. Gateway chỉ nhận ở mỗi thuộc tính các khóa `type`, `description`, `items`, `properties`, `required`; **không có `enum`, `minimum`, `pattern`** (test kiểm). Mọi ràng buộc nghiệp vụ nằm ở Lambda và Cedar; mô tả cho LLM nói rõ ràng buộc.
- `user_id` là tham số tùy chọn, mô tả "hệ thống tự điền, để trống". Interceptor luôn ghi đè từ JWT; Cedar viết `context.input has user_id && context.input.user_id == principal.id` (spike Gateway §8). Tham số thừa không bị Gateway từ chối nên Lambda bỏ qua tham số lạ.
- `save_turn` (chỉ agent gọi, không nằm trong lời gọi của LLM): lưu lượt hội thoại, xem "Đọc lại hội thoại" bên dưới. `user_id` do interceptor ghi đè; từ chối khối chứa token.
- `move_between_jars` không có `confirm_token` thì **không ghi**, trả `NEEDS_CONFIRMATION`. Token chỉ do `POST /confirmations` cấp sau khi người dùng bấm; LLM không bao giờ tạo hay điền token.
- **Kết quả tool** (`tools/ledger.results.schema.json`): `{"status": "OK" | "NEEDS_CONFIRMATION" | "ERROR", ...}`.
  - `OK` và `NEEDS_CONFIRMATION` mang `as_of`, `app_date` và `data`. `data` dùng lại **đúng** `data` của khối tương ứng: `JarSummaryData` (get_jar_balances), `ConfirmData` (NEEDS_CONFIRMATION), `ReceiptData` (move OK), nên agent chỉ việc bọc bằng `build_*`. `query_transactions` trả `{transactions, has_more}`.
  - `ERROR` mang `code` (thuộc `ErrorCode`) và `message` tiếng Việt. Lỗi nghiệp vụ là kết quả thành công của Lambda; agent đọc `status`.
  - Với tool ghi, Lambda dựng `data` từ số dư thật trong cùng transaction; `build_confirm`/`build_receipt` chạy ở agent (đường chat) hoặc ở Lambda (đường REST).

### REST

- JWT Bearer của Cognito (access token). Không endpoint nào nhận `user_id`.
- Lỗi: `{"error": {"code", "message", "trace_id"?}}`, `code` thuộc `ErrorCode`; ánh xạ HTTP status ở `x-http-status` trong `components.schemas.ErrorCode` và ở `yofina_core.errors.HTTP_STATUS` (test kiểm hai nơi khớp nhau). Mã token: `NEEDS_CONFIRMATION` (428), `TOKEN_INVALID` và `TOKEN_EXPIRED` (403), `TOKEN_REUSED`, `PARAMS_MISMATCH` và `ALREADY_APPLIED` (409). JWT authorizer của HTTP API có thể trả 401 thân rỗng trước khi tới Lambda.
- `POST /actions` không có `confirm_token` thì trả 428 (token là trường tùy chọn của yêu cầu để mã lỗi do code của chúng ta quyết định, không phải do kiểm schema).
- **Một đề nghị chỉ được thực hiện một lần, server giữ trạng thái** (migration 0004, bảng `confirm_resolutions`). `POST /confirmations` và `POST /actions` nhận thêm hai trường tùy chọn đi cùng nhau: `conversation_id` (session id của chat) và `confirm_block_id` (`id` của khối `confirm` đang được thực hiện, dạng `confirm:{trace_id}:{params_hash[:12]}`; 12 ký tự cuối phải khớp hash của `params` đang gửi, nếu không `PARAMS_MISMATCH`). Có hai trường này thì: (1) `POST /actions` lưu khối `receipt` gắn với `confirm_block_id` trong **cùng transaction** với sổ cái; (2) đề nghị đã thực hiện rồi thì `POST /confirmations` và `POST /actions` trả **409 `ALREADY_APPLIED`** và không ghi gì, kể cả khi có token mới hợp lệ (khóa unique `(user_id, confirm_block_id)` là đường chắc chắn khi hai yêu cầu chạy song song). Không gửi hai trường này (gọi REST trực tiếp, đường Gateway của agent) thì hành vi như cũ, không có kiểm tra này.

### Đọc lại hội thoại khi tải lại trang (`GET /conversations`)

`ACTIVITY_SNAPSHOT` không nằm trong `MESSAGES_SNAPSHOT`, nên khối UI không tự "phát lại" được. Agent lưu **mọi lượt** (kể cả lượt suy giảm hoặc chỉ có chữ) vào Aurora sau khi phát xong nội dung, ngay trước `RUN_FINISHED`, bằng tool `ledger___save_turn` (tham số `conversation_id`, `trace_id`, `user_text`, `assistant_text`, `blocks[{seq, block}]`; `user_id` do interceptor tiêm; token không bao giờ được lưu). Lỗi lưu không làm hỏng lượt (chỉ log). Frontend đọc lại bằng REST (JWT access token như các endpoint khác, không cần model):

- `conversation_id` **chính là session id** frontend đặt ở header `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` (UUID v4, giữ ổn định trong `localStorage` suốt cuộc hội thoại). Tải lại trang thì gọi lại với cùng id.
- `GET /conversations/{conversation_id}` -> `{"conversation_id", "turns": [{"trace_id", "created_at", "user_text", "assistant_text", "blocks": [<khối nguyên văn theo thứ tự phát>], "resolutions": [...]}]}`: tối đa 50 lượt gần nhất, cũ tới mới. Mỗi khối có đúng phong bì và `id` như lúc phát, vẽ bằng cùng registry; cùng `id` trong nhiều lượt thì lấy khối của lượt sau. Hội thoại không có hoặc **không thuộc người gọi: 200 với `turns` rỗng** (không phân biệt, để không lộ sự tồn tại).
- `GET /conversations?limit=20` (1 đến 50) -> `{"conversations": [{"conversation_id", "turns", "last_activity_at", "preview"}]}`, mới nhất trước; `preview` là câu hỏi đầu tiên (tối đa 120 ký tự).
- Khối `confirm` được lưu như lúc phát (nguyên văn, trong `blocks`). Trạng thái của nó do server giữ và trả ở `resolutions` của lượt: mảng, mỗi khối `confirm` trong `blocks` một phần tử `{block_id, status, resolved_at?, receipt?}` với `status` là `done` (đã thực hiện qua `POST /actions` có `confirm_block_id`; kèm `resolved_at` và `receipt` là đúng khối biên nhận đã trả), `cancelled`, `expired` (chưa thực hiện và quá `expires_at` của đề nghị lúc đọc) hoặc `pending`. `done` thắng `expired`. Frontend vẽ `receipt` thay chỗ khối `confirm` đã `done`, hiện "hết hạn" không nút cho `expired`, còn `pending` thì vẫn bấm được (và tự đếm ngược theo `expires_at`). `cancelled` (người dùng đã bấm "Không": frontend gọi `POST /confirmations/cancel` với `conversation_id` và `confirm_block_id`; phần tử có `resolved_at`, không có `receipt`). `resolutions` cũng có phần tử cho khối `confirm_action`, không chỉ `confirm`. Đã xử lý (`done`, `cancelled`) luôn thắng `expired`.
- Dựng lại luồng chat sau khi tải trang: vẽ từng `turns[i]` (`user_text` là tin người dùng; `assistant_text` và `blocks` là phía agent), (khối `confirm` đã `done` thì vẽ `receipt` của nó; đề nghị đã thực hiện còn nên được báo cho agent bằng một dòng hệ thống trong lịch sử, như lúc bấm), và gửi lại `messages` rút gọn từ `user_text`/`assistant_text` khi người dùng hỏi tiếp (Runtime không giữ lịch sử trong phiên).

### Tập con JSON Schema được dùng

Schema chỉ dùng: `$schema`, `$id`, `$ref`, `$defs`, `type` (`object`, `string`, `integer`, `number`, `boolean`, `array`), `const`, `enum`, `properties`, `required`, `additionalProperties`, `items`, `minItems`, `maxItems`, `minLength`, `maxLength`, `pattern`, `minimum`, `maximum`, `oneOf` (chỉ gồm `$ref`, phân biệt theo `type`), và chú thích `title`, `description`, `$comment`, `examples`, `format`. Bộ sinh Zod **báo lỗi** nếu gặp từ khóa khác.
`oneOf` của `contracts/scenario/scenario_spec.schema.json` phân biệt theo `kind` (không phải `type`) và không đi qua bộ sinh Zod. `pattern` dùng `[0-9]` thay `\d` (Python khớp cả chữ số Unicode). `format` (`date`, `date-time`) chỉ là chú thích; `pattern` mới là thứ được kiểm. `$id` dùng miền `contracts.yofina.invalid` (miền dành riêng, không phân giải được) và các `$ref` là đường dẫn tương đối.

## Phase 2: ví mô phỏng và dự báo

Phần này là hợp đồng mà bốn luồng của phase 2 (sổ cái và REST, ML, pipeline và tool forecast, frontend) cùng code theo. Số liệu và thiết kế chi tiết: mục "Quyết định hợp đồng phase 2" cuối [file phase 2](../docs/plan/phases/phase-2-vi-va-du-bao.md).

### Hũ hệ thống và tổng số dư

- Mỗi người dùng có **hai hũ hệ thống** (`jars.kind = 'system'`), tạo bằng hàm DB `app_ensure_system_jars(user_id)` (gọi ở onboarding, đặt lại demo, nạp seed):
  - **Tiền vào khác** (`system_role = other_income`, mã `tien_vao_khac`): mọi tiền vào chưa gán đều nằm đây. Số dư không âm. Nằm trong tổng số dư nhưng **không phải thu nhập** (`get_cashflow_summary` tách `salary_income_vnd` khỏi `other_income_vnd`).
  - **Chưa phân loại** (`system_role = unclassified`, mã `chua_phan_loai`): khoản chi mà hệ thống chưa xếp được hũ. **Số dư được phép ÂM** (tiền đã thật sự ra khỏi ví nhưng chưa trừ vào hũ nào): `assign_jar` chuyển phần chi đó sang hũ được chọn (hũ này giảm, Chưa phân loại tăng về 0). Giao diện ghi "đã chi, chưa xếp hũ" theo giá trị tuyệt đối. Bảng số Figma ghi +180.000 ₫ cho "Chưa phân loại"; hợp đồng này cho số dư có dấu để tổng số dư luôn đúng bằng tiền thật trong ví, nên số engine có thể khác Figma (ghi vào "Kết quả thực hiện" của phase 2).
- **Tổng số dư** = tổng `balance_vnd` của MỌI hũ (kể cả hai hũ hệ thống). `GET /overview` trả `balance.total_vnd = jars_total_vnd + other_income_vnd + unclassified_vnd`. Hũ hệ thống không có tỷ lệ chia lương, không có mục tiêu, không có dự báo.
- **`GET /jars` và tool `get_jar_balances` KHÔNG gồm hũ hệ thống** (sáu trường bắt buộc của phase 1 giữ nguyên). Phase 4 thêm vào `JarBalance` ba trường TÙY CHỌN, không tăng `v`: `kind` (chỉ `spending`, `saving`, `obligation`; ledger luôn điền), `goal_vnd` và `goal_date` (mục tiêu GỐC đọc từ cột `jars.goal_vnd`, `jars.goal_date` qua `app_get_jar_state`; VẮNG khi hũ không có mục tiêu, `goal_date` chỉ có khi có `goal_vnd`). Roadmap agent dùng các trường này để dựng `params` của `save_jars` cho bước `adjust_split` mà không làm mất mục tiêu. Hũ hệ thống xuất hiện ở `GET /overview` (`system_jars`) và `GET /jars/{jar_code}`.
- Hũ người dùng có `kind` ∈ `spending`, `saving`, `obligation`; mục tiêu (`goal_vnd`) và hạn (`goal_date`) tùy chọn. Tổng `split_percent` của hũ người dùng bằng 100 (`save_jars` kiểm).
- Khóa giao diện của hũ hệ thống: `color_key` `gray`, `icon_key` `inbox` (Tiền vào khác) và `help` (Chưa phân loại). Frontend cần biểu tượng và màu cho hai khóa này (các khóa của 7 hũ mặc định: `violet utensils`, `sky bus`, `brown receipt`, `orchid gamepad`, `teal plane`, `blue shield`, `slate wallet`).

### Nguồn trả và sổ cái

- Mỗi dòng `transactions` có `funding_source`: `jar` (trừ số dư hũ, như phase 1) hoặc `credit` (mua bằng hạn mức Trả sau (mô phỏng)). **Dòng `credit` là chi tiêu nhưng KHÔNG đổi số dư hũ**: `jar_code` là hũ để tính chi tiêu và lịch sử dự báo của hành vi; tiền thật rời hũ khi nghĩa vụ trả sau được thanh toán. Bất biến: số dư mỗi hũ = tổng `amount_vnd` các dòng `funding_source = 'jar'` của hũ đó.
- Cột `merchant` là **đối tác** (tên hiển thị tối đa 120 ký tự) và `note` là **lời nhắn**; `payee_id` trỏ tới người nhận đã lưu; `obligation_id` là nghĩa vụ mà dòng này thanh toán; `tx_type` là loại giao dịch (bảng tra `tx_type_map`, bước 0 của phân loại); `needs_review`, `classified_by`, `classification_confidence`, `suggested_jars` phục vụ "Xem lại" (phase 4 điền).
- **Trả sau (mô phỏng)**: mua `funding = credit` sinh hoặc cộng dồn vào một nghĩa vụ `bnpl` hoạt động có `due_date` = ngày `credit_lines.due_day` (mặc định 5) **kế tiếp sau ngày mua** (mua đúng ngày 5 thì tính sang tháng sau). Nghĩa vụ: `principal_vnd` = tổng gốc, `fee_vnd` = phí từ bảng `fee_schedules` (`monthly_service_fee` 33.000 ₫, tính MỘT lần cho mỗi nghĩa vụ vì mỗi nghĩa vụ ứng với một tháng có giao dịch), `amount_vnd = principal_vnd + fee_vnd`. Hạn mức: `outstanding_vnd` cộng gốc (không cộng phí), vượt `limit_vnd` thì 422 `CREDIT_LIMIT_EXCEEDED`. Trả nghĩa vụ = `record_transaction` chi từ một hũ với `obligation_id`: nghĩa vụ một lần thành `paid`, nghĩa vụ lặp dời `due_date` theo chu kỳ, `outstanding_vnd` giảm theo gốc.
- **Khử trùng**: `transactions.dedupe_key` (sha256 hex) duy nhất theo người dùng khi có giá trị. Công thức: `sha256("{app_date}|{abs(amount_vnd)}|{payee_id hoặc đối tác chuẩn hóa}|{client_ref}")`, đối tác chuẩn hóa = chữ thường, bỏ dấu, gộp khoảng trắng. `record_transaction` chỉ đặt khóa khi có `client_ref` (hai lần chi giống hệt nhau trong ngày là hợp lệ nếu không gửi `client_ref`; gửi lại đúng `client_ref` thì không ghi hai lần: server trả 409 `DUPLICATE_TRANSACTION`). Dòng nạp từ tệp (phase 5) luôn đặt khóa, phần cuối là số thứ tự trong lô.
- **Tiền vào**: `record_transaction` với `kind = income` ghi vào hũ Tiền vào khác. `tx_type = salary` luôn sinh một `salary_events` đang `pending`; `tx_type` khác thì không. Số nhận so với lương đã khai: `deviation_percent = round((nhận - khai) / khai * 100, 2)`, `ask_update_salary` đúng khi `|deviation_percent|` vượt ngưỡng cấu hình `salary_deviation_ask_percent`. `confirm_salary` với `decision = split` chia số nhận vào hũ bằng `yofina_core.wallet.split_amount` (làm tròn xuống từng hũ, phần dư vào hũ có tỷ lệ lớn nhất), ghi các dòng chuyển (`tx_type = salary_split`, cùng `transfer_id`, trừ Tiền vào khác, cộng các hũ), đặt `status = confirmed`; `keep_as_other` thì `kept_other` và tiền ở lại Tiền vào khác.
- **Kỳ lương kế**: `yofina_core.clock.next_payday(payday_day, app_today)` (ngày lương sau hôm nay; ngày lương lớn hơn số ngày của tháng thì lấy ngày cuối tháng). `GET /overview` trả `next_payday.state` theo mô tả của endpoint.

### Khối xác nhận và biên nhận: `confirm`/`receipt` và `confirm_action`/`receipt_action`

Hai cặp khối cùng cơ chế ADR-0002, cùng quy tắc id `confirm:{trace_id}:{params_hash[:12]}`, cùng `POST /confirmations` rồi `POST /actions`:

| Tool | Khối xác nhận | Khối biên nhận |
|---|---|---|
| `move_between_jars` | `confirm` (phase 1, **không đổi**: `preview.from/to`, `params` có kiểu) | `receipt` (phase 1, không đổi) |
| `record_transaction`, `assign_jar`, `update_profile`, `save_jars`, `confirm_salary` | `confirm_action` (`params` là object chuẩn hóa, `changes` là các dòng trước/sau đã định dạng, `warnings`) | `receipt_action` (`reference_id`, `jars_after` có dấu, `details`, `follow_up`) |

Lý do tách thay vì nới `confirm`: nới `ConfirmData` thành hợp theo `tool` làm đổi kiểu TypeScript của `preview.from` và `receipt.from_jar` mà code phase 1 đang dùng; hai khối mới thêm vào mà không động tới code cũ. `POST /actions` trả `receipt` (chuyển hũ) hoặc `receipt_action` (phân biệt bằng `type`). `confirm_resolutions` (migration 0004) lưu cả hai loại biên nhận; cột `transfer_id` nay có thể rỗng.

**Giao diện không có khối `confirm`** (màn hình tự dựng bản xem lại từ `params` đã nhập) gọi `POST /confirmations` với `tool` + `params` và không gửi `conversation_id`, `confirm_block_id`, `params_hash`; rồi `POST /actions` với token.

### Chuẩn hóa tham số (`params` được ký)

`params_hash = sha256(canonical_json({"tool", "params"}))` với `params` ĐÃ chuẩn hóa (cách tính: `yofina_core.confirm.hash_normalized_params`). Chuẩn hóa cài ở tầng ledger (`normalize_params` trong `yofina_core.confirm`, luồng A), phải **idempotent** (`normalize(normalize(x)) == normalize(x)`: client gửi lại đúng bản đã chuẩn hóa thì ra cùng hash). Quy tắc chung: bỏ `user_id`, `confirm_token`, `conversation_id`, `confirm_block_id`, `params_hash` và khóa lạ; bỏ khóa có giá trị null; chuỗi cắt khoảng trắng đầu cuối, chuỗi rỗng là vắng; mã hũ chữ thường; uuid chữ thường; tiền là số nguyên; ngày `YYYY-MM-DD` hợp lệ; mảng giữ thứ tự. Bản chuẩn hóa điền các mặc định phụ thuộc trạng thái server để thứ ký là thứ đã hiển thị:

| Tool | Dạng chuẩn hóa |
|---|---|
| `move_between_jars` | Như phase 1: `from_jar`, `to_jar`, `amount_vnd`. Hũ nguồn có thể là `tien_vao_khac` (cách gán "Tiền vào khác" vào hũ) |
| `record_transaction` | Luôn có `kind`, `amount_vnd`, `jar`, `tx_type`, `funding`; có thể có `payee_id`, `counterparty`, `note`, `obligation_id`, `client_ref`. `funding` mặc định `jar`; `tx_type` mặc định `other_expense` (chi; **`obligation_payment` khi có `obligation_id`**) hoặc `income_other` (tiền vào); tiền vào luôn có `jar = tien_vao_khac`; chi thiếu `jar` thì suy từ `tx_type_map` (`default_jar_code` nếu người dùng có hũ đó, `system_role` thì mã hũ hệ thống), không suy được thì `chua_phan_loai`. Lỗi `PARAMS_INVALID`: `funding = credit` hoặc `obligation_id` với tiền vào, `tx_type` không tồn tại hoặc ngược hướng với `kind`, `tx_type = salary` với chi |
| `assign_jar` | `transaction_id`, `jar`, `remember` (mặc định `once`) |
| `update_profile` | Chỉ các trường có mặt. `obligation`: `op`; với `upsert` **thêm mới (không có `obligation_id`)** điền `cycle` (mặc định `monthly`), `fee_vnd` (0), `is_essential` (false), `amount_vnd` (trung điểm làm tròn xuống nếu chỉ có khoảng), `due_date` (từ `due_day`: ngày đó sớm nhất không trước hôm nay mô phỏng), `pay_jar` (hũ `obligation` đầu tiên, nếu không có thì bỏ) |
| `save_jars` | `jars` theo thứ tự hiển thị; mỗi hũ luôn có `code` (hũ mới được sinh từ tên: chữ thường, bỏ dấu, ký tự khác chữ số thành `_`, tối đa 32 ký tự, bắt đầu bằng chữ cái, trùng thì thêm `_2`, `_3`), `split_percent` làm tròn 2 chữ số, tổng bằng đúng 100 |
| `confirm_salary` | `salary_event_id`, `decision`, `update_declared_salary` (mặc định false; ép false khi `keep_as_other`) |

**Ghi chú cài đặt (luồng A, phase 2)**: (1) `normalize_params(tool, params, ctx=None)` ở `yofina_core.params` (re-export từ `yofina_core.confirm`); phần điền mặc định phụ thuộc trạng thái chỉ chạy khi có `NormContext`, còn chuẩn hóa lại bản ĐÃ đầy đủ mà không có ngữ cảnh thì không đổi gì (nên `ConfirmService.issue` và `verify` không cần trạng thái server). (2) Sửa một nghĩa vụ có sẵn (`upsert` kèm `obligation_id`) KHÔNG điền mặc định, để không ghi đè trường đã khai. (3) `app_get_overview` (migration 0007) gộp hồ sơ, hũ, tóm tắt dự báo, hạn mức, nghĩa vụ sắp đến hạn, lương chờ và giao dịch gần đây vào MỘT lệnh gọi Data API thay vì ba. (4) Server ép hạn của đề nghị: quá `expires_at` của khối `confirm` hoặc `confirm_action` đã lưu thì `POST /confirmations` và `POST /actions` có `confirm_block_id` trả 403 `TOKEN_EXPIRED`; đề nghị đã thực hiện hoặc đã hủy thì 409 `ALREADY_APPLIED` (thông điệp phân biệt). (5) `POST /confirmations/cancel` (thêm ở luồng A): body `{conversation_id, confirm_block_id}`, trả `{block_id, status: "cancelled", resolved_at}`. (6) **`POST /confirmations` trả thêm `preview`** `{summary, changes, warnings?}` do SERVER tính, `changes` cùng hình dạng `ActionChange` của khối `confirm_action` (`label`, `before?`, `after`): số dư trước và sau của từng hũ; với Trả sau (mô phỏng) thì dòng "Phải trả ngày dd/mm" (`before` là "chưa có" hoặc số phải trả hiện có, `after` là tổng gồm phí lấy từ `fee_schedules`), "Hạn mức còn lại" trước và sau; với lương thì phần chia vào từng hũ; `warnings` có ví dụ phí dịch vụ. Frontend không tự tính phí hay số dư; chuyển hũ cũng có `preview` (hai dòng hũ). Không ghi gì. (7) **`GET /tx-types` mỗi loại có `is_person_transfer`** (đúng với `transfer_person`; cột `tx_type_map.is_person_transfer`, migration 0008). (8) **`JarFull.forecast_floor_vnd`** (tùy chọn, có dấu): số dư dự báo P50 thấp nhất từ ngày dự báo đầu tiên tới trước kỳ lương của lần chạy mới nhất có chứa hũ; vắng khi hũ chưa có dự báo hoặc chưa có ngày nào trước kỳ lương. Server tính từ bảng `forecasts` (hàm `app_get_forecast_summaries` thêm cột cùng tên, migration 0008): **pipeline dự báo (luồng C) không cần ghi thêm gì**, chỉ cần ghi `forecasts` như đã thiết kế. (9) **`due_day` và `due_date` của nghĩa vụ**: xem mô tả `ObligationChange` trong OpenAPI (tóm tắt: `due_day` là ngày trong tháng của khoản lặp, `due_date` là ngày đến hạn cụ thể kế tiếp; `once` và `weekly` cần `due_date`; `monthly` cần một trong hai; sửa không điền mặc định). (10) **Hai nghĩa của `TOKEN_EXPIRED`**: hiện dùng cho cả token quá 2 phút lúc áp dụng lẫn đề nghị quá `expires_at` lúc xin token hoặc áp dụng (phân biệt bằng thông điệp "đã hết hạn, hãy hỏi lại" của đề nghị). Chưa tách thành mã riêng vì thêm mã làm test `openapi.test.ts` của frontend (so `ERROR_CODES` với OpenAPI) đỏ cho tới khi frontend thêm mã; đề xuất `OFFER_EXPIRED` (HTTP 410) ở bước ghép khi sửa cả hai phía.

### Tool `ledger` (phase 2) và `forecast`

- `tools/ledger.json` có đúng mười tool theo thứ tự `yofina_core.wallet.LEDGER_TOOLS`: năm tool đọc (`get_jar_balances`, `query_transactions`, `get_cashflow_summary`, `get_obligations`, `get_unclassified`), bốn tool ghi (`update_profile`, `record_transaction`, `move_between_jars`, `assign_jar`) và `save_turn`. `save_jars` và `confirm_salary` **chỉ có ở REST**, không lộ cho agent qua Gateway (Cedar và schema không có chúng).
- Tool ghi không có `confirm_token` thì không ghi, trả `NEEDS_CONFIRMATION` với `data` = `ConfirmActionData` (`move_between_jars` giữ `ConfirmData`); có token hợp lệ thì ghi và trả `ReceiptActionData`. Agent dựng khối bằng `build_confirm_action` và `build_receipt_action`. Schema Gateway không có `enum`: mô tả của từng tham số liệt kê giá trị hợp lệ (test khớp với `yofina_core.wallet`).
- `query_transactions` thêm `kind`, `tx_type`, `cursor` và trả `next_cursor` (con trỏ mờ, mã hóa `(occurred_at, id)` của dòng cuối trang); trường mới của `Transaction` đều tùy chọn nên fixture phase 1 vẫn hợp lệ.
- `get_cashflow_summary` không có tham số thì lấy kỳ lương hiện tại (từ `latest_payday` tới hôm nay mô phỏng). Không tính dòng chuyển hũ và chia lương.
- `forecast___get_forecast {jar}` (target `forecast`, tên đầy đủ 23 ký tự) trả `GetForecastResult`: `data` = `ForecastTimelineData`. Quá hạn độ tươi thì tính lại trước khi trả (`stale` true nếu không tính lại được). Mã lỗi: `JAR_NOT_FOUND`, `PROFILE_INCOMPLETE`, `FORECAST_UNAVAILABLE`.
- **Cedar** (luồng A và C cập nhật `gateway/policies/`): mỗi tool mới một policy `context.input has user_id && context.input.user_id == principal.id`; tool ghi thêm `has confirm_token` và hạn mức `amount_vnd` (với `update_profile` không có số tiền một lần nên chỉ kiểm `has confirm_token`).

### Dự báo: khối `forecast_timeline` và quy tắc hiển thị

- `GET /forecasts/{jar_code}` và tool `get_forecast` trả CÙNG một khối `forecast_timeline` (criterion 8: chat và màn Chi tiết hũ cùng số). Id khối `forecast_timeline:{trace_id}:{jar_code}`.
- **Ngày dự báo bắt đầu từ `origin_date + 1`** (origin là ngày mô phỏng của lần chạy). `days` là phân vị SỐ DƯ cuối ngày (P10 kịch bản xấu, P90 kịch bản tốt, âm là hụt). Phân vị chi tiêu ngày lưu ở bảng `forecasts` nhưng không đưa vào khối.
- **Xác suất hay nhóm tin cậy**: `confidence_band` (Cao, Vừa, Thấp) luôn có. `p_shortfall` (tỷ lệ 0..1, KHÔNG phải phần trăm) chỉ có khi `show_probability` đúng ở DB, tức khi backtest tuần gần nhất đạt độ phủ khoảng 80% của tổng 30 ngày trong [0,75; 0,85] (`ForecastConfig.probability_enabled`) và lần chạy không phải ước lượng ban đầu. Vắng thì giao diện chỉ hiện nhóm. `is_initial_estimate` đúng khi lịch sử cả tài khoản dưới `cold_start_min_days` (21); khi đó nhóm là Thấp.
- `p_shortfall` là xác suất số dư hũ xuống dưới 0 ít nhất một ngày từ `origin_date + 1` tới trước `next_payday` (hoặc hết horizon nếu ngày lương xa hơn). `status` (đủ/sát/hụt): `short` nếu `p >= short_threshold`, `tight` nếu `p >= tight_threshold`, còn lại `ok`; ngưỡng ở cấu hình. `runout_date`: ngày đầu tiên số dư P50 chạm 0 hoặc thấp hơn trong horizon, vắng nếu không cạn.
- **Độ tươi**: `computed_at` (thời điểm thật) và `stale`. Dự báo là cũ khi `run_app_date != app_today(người dùng)` hoặc `now - computed_at` vượt `forecast_freshness_seconds` (cấu hình). Lambda `forecast` tính lại trước khi trả, không tính được thì trả bản cũ với `stale: true`.
- **Mốc trên biểu đồ** (`events`) ghép lúc đọc, không lưu: nghĩa vụ đang hoạt động trả bằng hũ này (mỗi lần đến hạn trong horizon một mốc; nghĩa vụ quá hạn tính vào ngày `origin_date + 1`) và phần lương của hũ (`split_amount(lương, tỷ lệ)` tại mỗi ngày lương trong horizon). Nghĩa vụ không có `pay_jar_code` được gán cho hũ `obligation` đầu tiên (theo `sort_order`); không có hũ như vậy thì không mô phỏng (ghi `unassigned_obligations` vào `forecast_runs.params`). Mở rộng chu kỳ: `weekly` cộng 7 ngày, `monthly` theo `due_day` (kẹp ngày cuối tháng), `yearly` cộng một năm, `once` chỉ `due_date`.
- Thẻ chủ động (`proactive_card`) phase 2 do `GET /overview` chọn bằng luật tất định (thứ tự ưu tiên ở mô tả của endpoint), không dùng LLM.

### REST (phase 2)

Mười bảy endpoint (`rest/openapi.yaml`), đều Bearer JWT, `x-lambda` cho biết Lambda phục vụ (`forecast` chỉ cho `/forecasts/{jar_code}`):

| Endpoint | Việc |
|---|---|
| `GET /overview` | Một lần gọi cho Tổng quan (hồ sơ, tổng số dư, hũ kèm đủ/sát/hụt, thẻ chủ động, kỳ lương, nghĩa vụ, hạn mức, giao dịch gần đây) |
| `GET /profile` | Hồ sơ đã khai |
| `GET /jars`, `GET /jars/{jar_code}` | Danh sách hũ (phase 1, không đổi) và chi tiết một hũ |
| `GET /transactions` | Hoạt động: lọc, phân trang con trỏ |
| `GET /tx-types`, `GET /payees`, `GET /jar-templates` | Dữ liệu cho form ghi giao dịch, chọn người nhận, onboarding |
| `GET /obligations`, `GET /credit-line`, `GET /salary-events` | Nghĩa vụ, hạn mức kèm biểu phí có nguồn, lương chờ xác nhận |
| `GET /forecasts/{jar_code}` | Khối `forecast_timeline` |
| `POST /confirmations`, `POST /actions` | MỌI thao tác ghi (bảng `tool` -> việc ở mô tả của `POST /actions`) |
| `POST /demo/reset` | Đặt lại demo; phase 2 còn seed nghĩa vụ, người nhận, hạn mức và tính dự báo đồng bộ (`forecast_ready`) |

Không có đường ghi tắt: không `PUT /profile`, `POST /jars`, `POST /transactions`... Tài khoản trắng: `GET /overview` có `profile.onboarded = false`; onboarding là `update_profile` với `monthly_salary_vnd` và `payday_day` (bắt buộc cả hai), server tạo hồ sơ, hai hũ hệ thống và hũ `is_default` của `jar_templates`. Mã lỗi mới: `PROFILE_INCOMPLETE` (422), `TRANSACTION_NOT_FOUND`, `OBLIGATION_NOT_FOUND`, `PAYEE_NOT_FOUND`, `SALARY_EVENT_NOT_FOUND` (404), `JAR_PROTECTED`, `CREDIT_LIMIT_EXCEEDED` (422), `DUPLICATE_TRANSACTION` (409), `FORECAST_UNAVAILABLE` (503).

### Sự kiện (EventBridge bus `yofina-bus`)

- Mỗi sự kiện có `Source`, `DetailType` và `Detail` (JSON theo `events/<detail-type>.schema.json`). `Source` ∈ `yofina.ledger` (Lambda ledger phát) và `yofina.forecast` (Lambda forecast phát); `DetailType` đúng tên sự kiện: `transaction.recorded`, `salary.confirmed`, `obligation.changed`, `profile.updated` (Source `yofina.ledger`), `forecast.updated` (Source `yofina.forecast`). Luật bus lọc theo `{"source": [...], "detail-type": [...]}`; consumer đầu tiên là Lambda `yofina-on-transaction` nghe cả bốn sự kiện của ledger.
- **Phát SAU khi transaction DB commit**, mỗi lần ghi một sự kiện. Phát thất bại không làm hỏng thao tác ghi (ghi log và `audit_events` mã `error`); nightly bù mọi sự kiện lỡ vì dự báo luôn tính lại từ sổ cái.
- **Idempotency**: EventBridge giao ít nhất một lần. `event_id` là khóa dedupe (DynamoDB `PutItem` có điều kiện, có TTL). `transaction.recorded.event_id` = `transaction_id` (id dòng sổ cái, hoặc `transfer_id` với chuyển hũ và chia lương), nên gửi lại cùng một lần ghi thì cùng `event_id`; `salary.confirmed.event_id` = `salary_event_id`; `forecast.updated.event_id` = `run_id`; `obligation.changed` và `profile.updated` sinh `event_id` mới mỗi lần (consumer chỉ tính lại, không cộng dồn nên xử lý hai lần cũng không sai).
- **Không PII**: chỉ id, mã hũ và số tiền; không tên người nhận, không số tài khoản, không token (test kiểm). `user_id` là `sub` của Cognito; consumer chạy bằng danh tính dịch vụ kèm `user_id` này và đặt `app.user_id` khi truy cập DB (RLS). Ngày trong sự kiện là ngày mô phỏng của người dùng; consumer không dùng đồng hồ hệ thống.
- Một lần ghi chạm nhiều hũ (chuyển hũ, chia lương) dùng `jar_codes` và `effects` để consumer chạy lại dự báo đúng các hũ liên quan; `profile.updated` yêu cầu tính lại mọi hũ.

### Hợp đồng ML và pipeline

Chữ ký `forecast_user(inputs: ForecastInputs) -> ForecastResult` và `update_forecast(inputs, previous, jar_codes)`, kiểu dữ liệu, ánh xạ sang bảng và các bất biến ở [ml/README.md mục "Giao diện"](../ml/README.md#giao-diện). Dạng JSON: `ml/forecast_io.schema.json`; bộ kiểm bất biến: `yofina_ml.contract.check_inputs` và `check_result`. Lịch sử chi tiêu do hàm DB `app_get_daily_spend` trả (chỉ chi trừ tiền hũ, không gắn nghĩa vụ).

## Phase 3: what-if, kiểm tra trước khi quẹt, harness

Hợp đồng mà ba luồng của phase 3 (A engine, B harness, C frontend) cùng code theo. Lý do từng lựa chọn: mục "Quyết định hợp đồng phase 3" cuối [file phase 3](../docs/plan/phases/phase-3-what-if-va-kiem-tra.md). Migration `0010` và các tool mới **chưa chạy / chưa deploy**.

### ScenarioSpec (`scenario/scenario_spec.schema.json`)

Sáu loại của FR5, phân biệt theo `kind` (`oneOf` các `$defs`): `one_time_purchase` (mua một lần bằng tiền hũ), `bnpl_purchase` (mua bằng Trả sau (mô phỏng)), `income_change`, `recurring_expense`, `jar_transfer`, `goal_delay`. Mỗi loại có trường bắt buộc riêng; trường chung tùy chọn: `date` (vắng là hôm nay mô phỏng, engine điền), `label` (≤80 ký tự, chỉ để hiển thị).

| `kind` | Bắt buộc | Tùy chọn |
|---|---|---|
| `one_time_purchase` | `amount_vnd`, `funding_source` = `jar`, `jar_code` | `date`, `label` |
| `bnpl_purchase` | `amount_vnd`, `funding_source` = `credit` | `jar_code` (hũ tính chi tiêu), `date`, `label` |
| `income_change` | `new_monthly_salary_vnd` (lương MỚI, không phải mức chênh) | `date` (vắng: kỳ lương kế), `label` |
| `recurring_expense` | `amount_vnd`, `cycle` (`weekly`, `monthly`, `yearly`), `date` (lần đầu), `jar_code` | `end_date`, `label` |
| `jar_transfer` | `amount_vnd`, `from_jar`, `to_jar` | `date`, `label` |
| `goal_delay` | `jar_code`, `delay_months` (1 đến 60) | `label` |

**Luật liên trường mà JSON Schema (tập con của repo) không diễn đạt được, nên Pydantic quyết định** (`yofina_core.scenario`, test `test_contracts_phase3.py` có ca "python_only_invalid"): `jar_transfer` có `from_jar` khác `to_jar`; `recurring_expense` có `end_date` không trước `date`; mọi `date` là ngày lịch thật. Lambda `run_scenario` luôn kiểm bằng `scenario.parse_scenario`. `scenario_hash` (sha256 của dạng JSON chuẩn, cùng `canonical_json` với `params_hash`) là khóa cho bảng `scenarios`. `contracts/scenario/` không sinh Zod (không khối nào nhúng spec; frontend chỉ thấy nhãn `compare.label` và `compare.kind`).

### Khối mới và khối mở rộng

Mười bốn khối trong `block.schema.json`. Sáu khối mới (`blocks/*.schema.json`; model và `build_*` ở `yofina_core.blocks`):

| Khối | Việc | Id | Do ai dựng |
|---|---|---|---|
| `affordability_card` | Thẻ đủ/sát/hụt: `verdict`, `headline` (luôn có chữ), `jar_checks` (từng hũ), `credit` (`ObligationImpactData` nếu xét Trả sau), `options` tất định, `basis` (độ tươi, nhóm tin cậy) | `affordability_card:{trace_id}` | Engine (`affordability_check`, `POST /affordability`); agent chỉ bọc |
| `obligation_impact` | Tác động nghĩa vụ của món Trả sau: `cost` (chi phí của món này TÁCH khỏi tổng phải trả ngày đến hạn), `at_due` (hũ nào hụt khi đến hạn), `shortfall_vnd`, `ratio` so ngưỡng luật, `cautions` | `obligation_impact:{trace_id}:{due_date}` | Engine (`run_scenario`) |
| `options` | 2 đến 3 `OptionItem`: nhãn, `status` nếu chọn, `metrics`, `checked_rules`, `action` tùy chọn | `options:{trace_id}` | Agent (lời Analyst, trạng thái và `checked_rules` do Verifier điền) |
| `explain` | "Vì sao": `data_used`, `rules_checked`, `confidence` (Cao/Vừa/Thấp + lý do), `subject_trace_id` | `explain:{subject_trace_id}` | Code từ bản ghi lượt (`audit___get_trace`, `GET /traces/{id}`) |
| `clarify` | Đúng một câu hỏi (`question`, một dấu hỏi) + `slot` + chip (0 đến 6) | `clarify:{trace_id}` | Agent (router) |
| `suggestions` | Chip gợi ý, kèm `can_do`/`cannot_do` ở mở đầu | `suggestions:{trace_id}:{context}` | Cấu hình hoặc code |

- **`ForecastBasis`** (trong `forecast_timeline.schema.json`) là cơ sở của mọi con số tính từ dự báo: `computed_at`, `stale`, `confidence_band`, `is_initial_estimate`, `history_days`, `coverage`. `JarStatus` (đủ/sát/hụt) vẫn định nghĩa MỘT chỗ; khối mới `$ref` tới nó (test kiểm không định nghĩa lại). Ba trạng thái luôn có chữ (`headline`, `status` kèm nhãn ở giao diện), không chỉ màu.
- **`forecast_timeline` trước-sau** là mở rộng tương thích ngược: thêm trường tùy chọn `compare` (không tăng `v`). Trường cấp trên (`status`, `days`, `events`, `runout_date`, `p_shortfall`) là **TRƯỚC** (baseline), `compare.after` là **SAU** (`status`, `days` cùng ngày với baseline, `runout_date?`, `p_shortfall?`, `min_balance_p50_vnd`, `events?` mốc phát sinh thêm), kèm `delta`, `n_paths`, `common_random_numbers` (luôn đúng), `scenario_id`, `label`, `kind`. Frontend cũ bỏ `compare` và vẫn vẽ đúng baseline. **Id của khối what-if có hậu tố `:what_if`** (`forecast_timeline:{trace_id}:{jar}:what_if`) để không đè khối baseline cùng hũ trong một lượt; `build_forecast_timeline_from_data` tự đặt hậu tố và viết câu thay thế "Nếu {label}: ..." nói về phần SAU.
- **`options.action`** = `{kind, tool, block_id}`: tham chiếu **theo id** tới khối `confirm` (chuyển hũ) hoặc `confirm_action` (mọi tool ghi khác, kể cả `schedule_nudge`) mà agent đã phát trong cùng lượt. Agent gọi tool ghi KHÔNG token để lấy `NEEDS_CONFIRMATION`, dựng khối bằng `build_confirm`/`build_confirm_action`, phát, rồi tham chiếu. Bấm "Chọn" thì giao diện hiện khối đã tham chiếu (không gọi tool ghi, không tạo token); từ đó chạy luồng xác nhận phase 1 và 2. `kind` = `confirm` đi với `move_between_jars`, `confirm_action` với tool khác (Pydantic kiểm). Phương án không có `action` chỉ để cân nhắc.
- **`notice`** (mở rộng, không tăng `v`): thêm tùy chọn `retryable` (nút "Thử lại", gửi lại tin nhắn cuối), `degraded_reason` (`model_budget`, `model_error`, `tool_error`, `tool_timeout`, `verifier_failed`, `low_coverage`, `short_history`), `missing` (phần còn thiếu khi trả một phần), `suggestions` (việc làm được, dùng cho H7). Bốn `kind` giữ nguyên (`out_of_scope`, `degraded`, `low_data`, `error`); phase 4 thêm `kind` thứ năm `info` (tương thích ngược, không tăng `v`; frontend cũ không biết `info` thì hiện `fallback_text`).

### Chi phí của món này và tổng phải trả ngày đến hạn

Phí Trả sau (mô phỏng) tính MỘT lần cho mỗi nghĩa vụ (quyết định số 5 phase 2), nên "món này tốn thêm bao nhiêu" và "ngày đến hạn phải đưa ra bao nhiêu" là hai số khác nhau. `CreditCost` (dùng ở `obligation_impact.cost`, kết quả `run_scenario`, `affordability_card.credit.cost`) tách chúng và có hai bất biến (Pydantic và test kiểm):

```
item_cost_vnd = principal_vnd + fee_added_vnd          # chi phí của món này
total_due_vnd = existing_due_vnd + item_cost_vnd       # tổng phải trả ngày đến hạn, cộng dồn
```

`fee_added_vnd` là 0 khi nghĩa vụ ở ngày đến hạn đó đã có phí. Với `minh` (đã có nghĩa vụ Trả sau 1.000.000 ₫ hạn 05/12, phí 33.000 ₫ nằm trong đó) mua 1.200.000 ₫: `principal` 1.200.000, `fee_added` 0, `item_cost` 1.200.000, `existing_due` 1.000.000, `total_due` 2.200.000. Tài khoản chưa có nghĩa vụ mua 300.000 ₫: `fee_added` 33.000, `item_cost` 333.000, `total_due` 333.000. Hạn mức chỉ giảm theo gốc (`available_before_vnd - available_after_vnd = principal_vnd`). `late_penalty_vnd` chỉ có khi biểu phí có nguồn (không bịa phí trễ hạn). Con số này **lệch câu chữ** của tiêu chí 1 và 3 phase 3 (1.233.000 ₫, 283.000 ₫); xem mục quyết định số 10.

### Tool phase 3 (target `forecast` mở rộng, ba target mới)

Tên đầy đủ qua Gateway `<target>___<tool>`. `user_id` giống mọi tool: tham số tùy chọn "hệ thống tự điền", interceptor ghi đè từ JWT, Cedar `context.input.user_id == principal.id`. Schema Gateway không có `enum`: mô tả của từng tham số liệt kê giá trị hợp lệ (test khớp với `yofina_core.wallet`).

| Tool | Loại | Bắt buộc | Kết quả (`tools/*.results.schema.json`) |
|---|---|---|---|
| `forecast___run_scenario` | ĐỌC và tính (ghi `scenarios` là dữ liệu dẫn xuất, không cần xác nhận) | `scenario` (có `kind`); tùy chọn `conversation_id`, `with_scenarios` | `RunScenarioResult`: `scenario_id`, `spec` đã chuẩn hóa, `bundle`, `bundle_total_vnd?`, `effects`, `timelines` (1 đến 3, mỗi `data` có `compare`), `obligation_impact?`, `basis` |
| `forecast___list_scenarios` | ĐỌC (chỉ của chính người dùng) | `conversation_id` (tùy chọn `limit` 1 đến 10, mặc định 5) | `ListScenariosResult`: `data.scenarios[]` (`scenario_id`, `created_at`, `kind`, `label`, `spec`, `bundle[]`), mới nhất trước |
| `forecast___affordability_check` | ĐỌC, tất định, không model | `amount_vnd` | `AffordabilityCheckResult`: `data` là đúng `AffordabilityCardData` |
| `knowledge___get_fee_schedule` | ĐỌC bảng `fee_schedules` (không qua RAG) | không | `GetFeeScheduleResult`: `product_label`, `fees[]` (`FeeLine`, cùng hình dạng OpenAPI) |
| `knowledge___get_exchange_rate` | ĐỌC tỷ giá BÁN theo ngày của Vietcombank (cùng hàm `yofina_core.fx` với pipeline nạp chứng từ), không ghi gì | `currency` (ISO 4217, khác VND); tùy chọn `date` (YYYY-MM-DD, mặc định ngày mô phỏng `app_today`), `amount` (số theo ngoại tệ, tối đa 4 chữ số lẻ) | `GetExchangeRateResult`: `ExchangeRateData` (`currency`, `rate` và `amount_original` là chuỗi thập phân như `IngestFx`, `rate_type` sell, `rate_source` vietcombank, `rate_date` là ngày của bảng đã dùng, `requested_date`, `amount_vnd` làm tròn tới đồng khi có `amount`). Lỗi: `PARAMS_INVALID` (tham số sai, ngoại tệ không có trong bảng), `INTERNAL_ERROR` (nguồn không trả lời, tạm thời) |
| `planner___check_suitability` | ĐỌC, tất định | `proposal` (có `kind`) | `CheckSuitabilityResult`: `SuitabilityVerdict` (`ok`, `violations`, `checked`, `rules_version`) |
| `planner___schedule_nudge` | **GHI** (qua token) | không (Lambda kiểm theo `op`) | `ScheduleNudgeResult`: `NEEDS_CONFIRMATION` (`ConfirmActionData`), `OK` (`ReceiptActionData`, `reference_id` = id nhắc) |
| `audit___get_trace` | ĐỌC, chỉ của chính người dùng | `trace_id` | `GetTraceResult`: `TraceData` (`explain` đã dựng + `detail`) |
| `audit___record_turn` | GHI một lần mỗi lượt (không qua token, không đụng tiền), chỉ của chính người dùng | `trace_id` + các trường của bản ghi lượt (không có `user_id`) | `RecordTurnResult`: `{trace_id, recorded}` (`recorded` false nếu lượt đã có bản ghi) |

- `run_scenario` nhận `scenario` là object phẳng gộp mọi trường của sáu loại (Gateway không có `oneOf`); mô tả nói trường nào bắt buộc theo loại, Lambda kiểm lại bằng `parse_scenario` và trả `SCENARIO_INVALID` hoặc `PARAMS_INVALID`. Thiếu số tiền hay cách trả thì agent KHÔNG gọi tool mà phát `clarify`.
- **Gộp kịch bản trong một cuộc chat** (migration 0051). Người dùng hỏi "nếu mua giày 800 nghìn từ hũ Giải trí", lát sau "nếu mua dép 300 nghìn từ hũ Giải trí": agent gọi `list_scenarios` (`conversation_id` = session id của Runtime, 1 đến 256 ký tự) để biết đã hỏi gì, hỏi lại "bạn vẫn giữ ý định mua giày chứ?", nếu giữ thì chạy MỘT mô phỏng bằng `run_scenario` với `scenario` = dép và `with_scenarios` = [giày]. Luật (engine kiểm, Gateway không kiểm được `maxItems`): `with_scenarios` tối đa 4 phần tử, mỗi phần tử cùng dạng `scenario` nhưng `kind` chỉ `one_time_purchase`, `recurring_expense` hoặc `bnpl_purchase`; cả bó (kể cả `scenario`) có tối đa MỘT `bnpl_purchase`. Vi phạm là `SCENARIO_INVALID` (câu tiếng Việt, ví dụ "Chưa gộp được hai khoản Trả sau trong một mô phỏng."); `with_scenarios` hoặc `conversation_id` sai kiểu, quá 256 ký tự, hoặc phần tử không parse được là `PARAMS_INVALID`; lỗi của một khoản đã giữ (ví dụ ngày quá khứ) mang tiền tố "Khoản đã giữ từ trước (…)". TRƯỚC vẫn là thực tế hiện tại; SAU là thực tế cộng mọi kịch bản của bó (áp nối tiếp, khoản Trả sau áp cuối vì kết quả không phụ thuộc thứ tự; dùng chung dãy số ngẫu nhiên nên SAU thấp hơn TRƯỚC đúng tổng các khoản chi). Kết quả thêm `data.bundle` (luôn có, ít nhất một phần tử: `kind`, `label` riêng, `amount_vnd?`, `jar_code?`, `spec` dạng wire theo thứ tự `with_scenarios` rồi `scenario`) và `data.bundle_total_vnd` (tổng `amount_vnd` các khoản `one_time_purchase` và `bnpl_purchase`; CHỈ khi bó có từ hai khoản). `spec` vẫn là kịch bản chính; nhãn gộp ("mua giày 800 nghìn + mua dép 300 nghìn", cắt 80 ký tự) ở `timelines[].compare.label`; `effects` và `timelines` là hợp các hũ bị tác động (xếp theo mức bị tác động như trước); `obligation_impact` chỉ từ khoản Trả sau duy nhất. Dòng `scenarios` lưu thêm `conversation_id` (KHÔNG dùng `trace_id`: Lambda tự sinh, khác trace của lượt chat) và `bundle` (mảng spec wire của cả bó). Không truyền trường mới thì hành vi như cũ (chỉ thêm `data.bundle` một phần tử).
- `schedule_nudge` có `confirm_token` tùy chọn (không có thì không ghi, trả `NEEDS_CONFIRMATION`), mô tả nói "KHÔNG tự tạo token", đúng mẫu tool ghi của `ledger`. `wallet.PLANNER_WRITE_TOOLS = ("schedule_nudge",)`; `ACTION_TOOLS` (REST) có thêm `schedule_nudge` ở CUỐI.
- `check_suitability.proposal` khớp model `yofina_core.suitability.Proposal` (`kind`, `amount_vnd`, `funding_source`, `jar_code`, `is_essential`, `category`, `risk_level`, `origin`, `start_date`). `origin` = `recommendation` cho phương án HỆ THỐNG đề xuất, `user_request` cho thứ người dùng tự hỏi. `start_date` (ngày có thật, tùy chọn) là ngày khoản tiền bắt đầu rời hũ nguồn, chỉ có nghĩa với bước lộ trình (`kind` `roadmap_*`); bước lộ trình kéo tiền khỏi hũ gửi ngày bắt đầu giai đoạn của bước (agent và `save_roadmap` dựng cùng một đề xuất). Từ kỳ lương kế trở đi, luật `source_jar_covers` so khoản hằng tháng với thu nhập tháng thay vì số dư hiện có, và `obligations_first` không trừ khoản đó khỏi số dư trước kỳ lương; vắng là làm ngay. Đề xuất what-if luôn kiểm như làm ngay, và trường này không có trong JSON Schema của `Proposal` (model what-if không thấy).

**`schedule_nudge` qua luồng token** (không endpoint ghi riêng): `tool` = `schedule_nudge` đi `POST /confirmations` rồi `POST /actions`, khối `confirm_action` và `receipt_action`. Chuẩn hóa `params` (luồng A cài, idempotent, như bảng ở mục phase 2): `op` mặc định `create`; `create` bắt buộc `kind` (`runout_warning`, `obligation_due`, `salary_pending`, `review_needed`, `low_data`, `purchase_review`) và `fire_on` (ngày mô phỏng, sau hôm nay), tùy chọn `jar_code`, `note` (≤120), `scenario_id`; `cancel` chỉ có `nudge_id`. Hoàn tác = `schedule_nudge` `op` `cancel` với `nudge_id` = `reference_id` của biên nhận, cũng qua token. Phase 3 chỉ LƯU và hủy lời nhắc (bảng `nudges`, `status` `scheduled`/`cancelled`); gửi nhắc theo ngày là phase 4 và 5.

### REST mới

| Endpoint | `x-lambda` | Việc |
|---|---|---|
| `POST /affordability` | `forecast` | Thân `AffordabilityRequest` (`amount_vnd` bắt buộc; `funding_source?`, `jar?`, `label?`, `date?`). Trả khối `affordability_card` (cả phong bì), CÙNG khối với tool trong chat. Không LLM, không ghi. POST chỉ để có thân yêu cầu |
| `GET /traces/{trace_id}` | `audit` | `TraceResponse` = `TraceData`. Chỉ của chính người dùng: của người khác và không tồn tại đều 404 `TRACE_NOT_FOUND` như nhau |
| `POST /feedback` | `audit` | `FeedbackRequest` (`trace_id`, `option_id`, `decision` `accepted`/`rejected`, `block_id?`, `scenario_id?`, `reason?`), trả `FeedbackResponse`. Idempotent theo (`trace_id`, `block_id`, `option_id`); KHÔNG qua token vì không đụng tiền |

`x-lambda` nay có ba giá trị: `ledger` (mặc định), `forecast`, `audit`. `POST /confirmations` thêm phản hồi 410 `OFFER_EXPIRED`; `POST /actions` cũng có 410.

### Mã lỗi mới (thêm CUỐI danh sách)

`OFFER_EXPIRED` (410, đề nghị quá `expires_at`; tách khỏi `TOKEN_EXPIRED` 403 nay chỉ là token quá 2 phút), `TRACE_NOT_FOUND` (404), `NUDGE_NOT_FOUND` (404), `FEE_SCHEDULE_NOT_FOUND` (404), `FORECAST_NOT_APPLICABLE` (404, hũ hệ thống không có dự báo; thay 503 `FORECAST_UNAVAILABLE` cho riêng ca này), `SCENARIO_INVALID` (422). Hiện ledger vẫn trả `TOKEN_EXPIRED` cho đề nghị quá hạn và `GET /forecasts/{hũ hệ thống}` vẫn 503 cho tới khi luồng A đổi cả mã lẫn test tích hợp cùng lúc.

### Bản ghi lượt và `GET /traces`

Migration `0010` thêm cột có kiểu vào `audit_events` cho bản ghi lượt (`event_type = 'agent_turn'`, đúng một dòng mỗi `trace_id`, chỉ thêm): `conversation_id`, `intent`, `data_used`, `rules_checked`, `confidence`, `blocks_emitted`, `token_usage`, `step_timings` (jsonb có kiểu), `duration_ms`. `app_get_trace(p_user_id, p_trace_id)` đọc dòng đó; `p_user_id` PHẢI là `sub` của JWT (như mọi hàm `app_*`), không bao giờ nhận từ client. Khối `explain` do code dựng từ các cột này (`rules_checked` là danh sách `RuleCheck`, `confidence.reasons` do code viết). Chi tiết ở [db/README.md](../db/README.md#schema-phase-3-0010).

### Luật suitability dạng dữ liệu

`gateway/tools/planner/rules/*.yaml` (mỗi file một luật, tên file = `id`), định dạng ở `rules/rule.schema.json` và `yofina_core.suitability.SuitabilityRule`: `evaluator` (tên bộ đánh giá luồng A cài), `severity`, `recommendation_severity?`, `applies_when?`, `thresholds` (mỗi ngưỡng có `value`, `unit`, `note`, `source`), `message` (không chứa số). Bảy luật: `obligations_first`, `emergency_before_investing`, `risk_within_tolerance`, `no_borrow_to_spend`, `obligation_to_income` (phase 3), `source_jar_covers` (hũ nguồn đủ tiền, phase 4) và `emergency_not_for_discretionary` (giữ quỹ dự phòng cho việc gấp, phase 5). `checked` của `check_suitability` liệt kê đủ bảy luật; `rules_version` nối phiên bản từng luật theo thứ tự `evaluator` của `yofina_core.suitability.EVALUATORS`.

`emergency_not_for_discretionary` (bộ đánh giá `emergency_fund_not_for_discretionary`, `severity: warn` cho mọi nguồn, không có ngưỡng) áp khi đề xuất là chi tiêu (`category` `spending`), lấy tiền hũ (`funding_source` `jar`) và không thiết yếu (`is_essential` false, hoặc vắng với `kind` mua sắm). Kết quả `fail` (thành `warn` trong `checked`) khi hũ nguồn là quỹ dự phòng: hũ tiết kiệm không gắn mục tiêu, cùng định nghĩa với quỹ dự phòng của `emergency_before_investing`. Hũ khác là `pass`; đề xuất không lấy số tiền cụ thể là `skipped`. Mức warn không loại phương án: agent vẫn đưa phương án đó, nhưng không đặt `recommended` và tóm tắt nói rõ tiền lấy từ quỹ dự phòng. Ngưỡng nêu rõ là giá trị mô phỏng chưa hiệu chỉnh. Không có rule engine ở bước hợp đồng.

### Kiểu của agent

`agent/src/yofina_agent/schemas.py`: `IntentResult` (bảy ý định `wallet.INTENTS`), `Plan` (spec + bước tool đọc, `limits` không có mặc định), `Analysis` (2 đến 3 phương án), `Verdict` (grounding + suitability từng phương án, `action` `pass`/`retry`/`fallback`). Chỉ định nghĩa kiểu và kiểm bất biến; router phase 1 (`router.RouterOutput`) chưa dùng chúng.

### Kiểm

```
uv run pytest tests/unit/test_contracts_phase3.py tests/unit/test_migration_0010.py tests/unit/agent/test_schemas.py
```

Hai test cũ đã sửa cho phase 3: `test_contracts_rest.py` (tập endpoint, `x-lambda`) và `test_contracts_phase2.py` (tool ghi có thêm `schedule_nudge`). Frontend: `frontend/src/api/errors.ts` thêm sáu mã lỗi và `api/schemas.ts` thêm `schedule_nudge` vào `TOOL_NAMES` (để `openapi.test.ts` xanh); sáu khối mới đã có Zod trong `blocks.ts` nhưng CHƯA ở `REGISTERED_BY_FRONTEND`. Luồng C thêm chúng vào danh sách đó trong `scripts/gen_contracts.mjs` rồi sinh lại, cùng lúc đăng ký view trong `registry.tsx`.

## Phase 5 (F6): nạp dữ liệu

Hợp đồng cho luồng A của [phase 5](../docs/plan/phases/phase-5-nap-du-lieu-ho-so-trace.md): nạp chi tiêu và thu nhập NGOÀI ví (ngân hàng khác, thẻ) từ ảnh chụp màn hình hoặc CSV. Ví mô phỏng khép kín nên độ phủ dữ liệu của nó luôn đầy đủ; dữ liệu nạp thêm phần ngoài ví ("phương án A" đã chốt với chủ dự án). Migration: [db/migrations/0050_ingest.sql](../db/migrations/0050_ingest.sql) (đánh số 0050 vì 0010 tới 0049 để cho luồng khác). **0050 đã thay hàm `app_get_daily_spend` (của 0005) và `app_get_forecast_context` (của 0009)**, cùng chữ ký và cùng hình dạng kết quả, để Lambda dự báo đã deploy nhận công thức mới mà không phải deploy lại.

### Nguồn trả `external`

- `transactions.funding_source` có thêm `external`: chi (`kind = expense`, bắt buộc có `jar_code`) hoặc thu (`kind = income`) ngoài ví. **Không bao giờ đổi số dư hũ** (như `credit`). Không có dòng chuyển hũ external, không gắn nghĩa vụ (ràng buộc `transactions_funding_check` mới, DROP rồi ADD trong 0050). Bất biến của sổ cái giữ nguyên: số dư mỗi hũ = tổng `amount_vnd` các dòng `jar` của hũ đó.
- Chỉ `confirm_rows` ghi dòng external. `record_transaction` không nhận `funding = external` (`yofina_core.wallet.RECORDABLE_FUNDING_SOURCES`; `FUNDING_SOURCES` có cả ba giá trị). Dòng do `confirm_rows` ghi có `source = 'ingest'`, `needs_review = false`, `occurred_at` là thời điểm thật lúc chốt, `app_date` là ngày trên tệp.
- Đây là thay đổi tương thích ngược (thêm giá trị enum ở `Transaction.funding_source` của `tools/ledger.results.schema.json`, `events/transaction.recorded.schema.json`, Zod frontend `api/schemas.ts`).

### Độ phủ dữ liệu

Công thức không đổi (`yofina_ml.quality.data_coverage`): `clamp((spend + balance_end - balance_start) / income, 0, 1)`. Đổi là các thành phần, tính trong SQL (`app_coverage_facts`, dùng chung cho `app_get_forecast_context` và `app_get_data_coverage`), trong cửa sổ từ `history_start`:

| Thành phần | 0009 | 0050 |
|---|---|---|
| `income_vnd` | lương vào ví (`income`, `tx_type = salary`) | lương vào ví (`income`, `salary`, `jar`) + mọi thu nhập ngoài ví (`income`, `external`) |
| `spend_vnd` | chi dòng `jar` | chi dòng `jar` + chi dòng `external` |
| `balance_start_vnd`, `balance_end_vnd` | số dư hũ trong ví | như cũ (chỉ dòng `jar`) |

Không thêm cột hồ sơ: thu nhập ngoài ví lấy từ chính dòng `income`/`external` đã nạp. **Bất biến**: người dùng không có dòng external thì mọi số của `coverage`, mọi dòng `jar` (kể cả `spend`) và mọi nghĩa vụ của `app_get_forecast_context` Y HỆT bản 0009 (test chạy bản 0009 dưới tên khác trên minh, lan, khoa); nhãn tin cậy và `is_initial_estimate` cũng không đổi. `app_get_data_coverage` trả các thành phần thô (cùng ngày mô phỏng, cùng `history_start` với `p_window_days = forecast_history_window_days`) và phần ngoài ví; Python tính tỷ lệ bằng `yofina_core.ingest.coverage_ratio` (test khóa nó bằng chính `quality.data_coverage`), nên `coverage_change.before/after` khớp dải độ phủ của dự báo.

### Rà mọi đường đọc sổ cái với `external`

Test: `tests/local_pg/test_external_funding.py` (PostgreSQL 16 cục bộ, role `yofina_app`, RLS thật). Ca chuẩn: chèn một dòng chi external 150.000 ₫ vào hũ `an_uong` của minh ngày 19/11.

| Đường đọc | Hành vi với `external` | Test |
|---|---|---|
| `SQL_RECOMPUTE_BALANCES` (đặt lại demo), `app_get_jar_state`, `app_list_jars`, tool `get_jar_balances` | Chỉ cộng dòng `jar`: số dư hũ không đổi | `test_so_du_hu_va_dung_lai_so_du_khong_doi` |
| `app_get_overview` (tổng ví, `recent_transactions`, `review_count`) | Tổng ví = tổng số dư hũ, không đổi. **Thay trong 0050**: giao dịch gần đây của Tổng quan là của VÍ, bỏ dòng external. Số cần xem lại không đổi (dòng external có `needs_review = false`, hũ người dùng) | `test_tong_quan_tong_so_du_gan_day_va_can_xem_lai_khong_doi` |
| `app_get_overview_extras` (0005, không còn mã gọi) | Thay trong 0050 cho khớp `app_get_overview`: bỏ dòng external khỏi gần đây | cùng test trên |
| `app_get_review_stats`, `app_get_unclassified` | Không đổi (không gồm dòng external vì chúng không cần xem lại và không ở Chưa phân loại) | cùng test trên |
| `app_list_transactions` (Hoạt động, `query_transactions`), `app_get_jar_detail`, `app_get_transaction` | CÓ dòng external, kèm `funding_source = external` (frontend hiện nhãn nguồn, như "Trả sau") | `test_lich_su_va_chi_tiet_hu_co_dong_external_kem_nguon` |
| `app_get_cashflow_summary`, tool `get_cashflow_summary` | **Thay trong 0050**: `by_jar` và `income_by_type` chỉ là luồng tiền CỦA VÍ (`jar`, `credit`), không gồm external; khóa mới `external {spent_vnd, income_vnd, tx_count}` tách riêng. Lý do: cộng chi ngoài ví vào "đã chi" làm số lớn hơn tiền thật rời ví; tool giữ nguyên hình dạng nên agent không đổi | `test_dong_tien_cua_vi_khong_gom_external_va_tach_rieng` |
| `app_get_daily_spend` | **Thay trong 0050**: tính chi `jar` và `external` (vẫn bỏ dòng gắn nghĩa vụ, hũ hệ thống, dòng `credit`); chi của hũ đổi đúng bằng số tiền | `test_daily_spend_va_spend_cua_context_doi_dung_so_tien`, `test_credit_va_dong_gan_nghia_vu_van_khong_vao_lich_su_chi` |
| `app_get_forecast_context` | **Thay trong 0050**: `spend` của hũ (qua `app_get_daily_spend`) và `coverage` theo bảng trên; `balance_vnd` của hũ không đổi | cùng test trên, `test_thu_nhap_ngoai_vi_vao_do_phu_khong_doi_so_du_tien_vao_khac`, `test_khong_co_external_thi_context_y_het_ban_0009`, `test_khong_co_external_thi_nhan_tin_cay_va_uoc_luong_ban_dau_khong_doi` |
| `assign_jar` (`moves_money = funding_source == 'jar'`) | Dòng external đổi hũ thì KHÔNG chuyển tiền (như `credit`). Sự kiện `transaction.recorded` nay mang nguồn trả THẬT của dòng (sửa `wallet_writes.py`, `repo_wallet.py`: bản cũ ghi `credit` cho mọi dòng không chuyển tiền) | `test_assign_jar_dong_external_khong_chuyen_tien_va_su_kien_chay_day_du` |
| Consumer `yofina-on-transaction` (`plan_event`) | `funding_source = external` thì chạy dự báo ĐẦY ĐỦ (fit lại lịch sử chi), không chỉnh nhanh, không trừ số dư. **Chỉ có hiệu lực khi deploy lúc ghép**; trước đó backend ingest không phụ thuộc vào nó: sau `confirm_rows` gọi tính lại đầy đủ (`yofina-forecast-batch`, như đặt lại demo) hoặc phát `profile.updated` | `test_consumer_external_luon_chay_day_du`, `tests/unit/pipeline` |
| `RESET_DELETES` (đặt lại demo) | Xóa `ingest_rows`, `ingest_jobs`, `consents` TRƯỚC `transactions` (dòng external bị xóa cùng sổ cái). `consents` xóa vì đặt lại đưa tài khoản demo về trạng thái chưa từng nạp; bằng chứng đồng ý vẫn ở `audit_events` (chỉ thêm) | `test_dat_lai_xoa_external_va_du_lieu_nap_dung_nguoi` |
| `record_transaction` | Không ghi được external (PARAMS_INVALID) | `test_record_transaction_khong_ghi_duoc_external` |
| `app_query_transactions` (0001, không còn mã gọi), `app_get_jar_usage` (đếm dòng của hũ) | Không đổi: dòng external hiện ở lịch sử; hũ có dòng external (kể cả số dư 0) không bỏ được, như hũ có dòng `credit` | rà tay |

### Bảng và hàm (0050)

- `ingest_jobs`: một lần nạp một tệp. `source_kind` (`image`, `csv`), `s3_key` (`{user_id}/{job_id}`, không có tên tệp gốc), `content_sha256`, `mime`, `size_bytes`, `status` (`awaiting_upload`, `queued`, `processing`, `review`, `done`, `failed`, `rejected`), `error_code`, `error_message`, `progress` 0..100, bốn bộ đếm dòng, `coverage_before`/`coverage_after` (`numeric(4,3)`), `model`. Cùng `content_sha256` chỉ một job còn sống mỗi người dùng.
- `ingest_rows`: dòng ĐÃ che PII. `kind` (`expense`, `income`), `amount_vnd` dương, `counterparty`, `description`, `extract_confidence`, `suggested_jar_code`, `jar_confidence`, `jar_source` (`type_map`, `rule`, `model`, `user`), `tx_type`, `review_status` (`auto_added`, `pending`, `approved`, `rejected`, `duplicate`), `duplicate_of_transaction_id`, `transaction_id` (không khóa ngoại cứng), `dedupe_key` duy nhất theo người dùng. Không cột nào chứa ảnh hay văn bản thô.
- `consents`: `(user_id, source)` với `source` ∈ `image_upload`, `csv_upload`; `granted_at`, `revoked_at`, `version`.
- Hàm (SECURITY INVOKER, tự đặt `app.user_id`, có LIMIT): `app_create_ingest_job`, `app_find_ingest_job_by_content`, `app_update_ingest_job` (chuyển trạng thái hợp lệ, tiến độ không lùi; `failed`/`rejected` xóa dòng chưa chốt để nạp lại được), `app_insert_ingest_rows` (tối đa 500, trùng khóa thì bỏ qua), `app_get_ingest_job` (dòng `job` rồi các dòng `row`, tối đa 500), `app_list_ingest_jobs`, `app_set_ingest_row_jar` (chỉ đổi đề xuất), `app_grant_consent`, `app_get_consents`, `app_get_data_coverage`, `app_find_ingest_matches`, `app_fold_text` (khớp `params.fold_text`). Ghi sổ cái của `confirm_rows` là câu INSERT trong transaction của Lambda (như ledger), không phải hàm DB.
- **`auto_added` không ghi sổ cái** (đã chốt với chủ dự án): dòng tin cậy cao chỉ được CHỌN SẴN trong khối duyệt; mọi dòng vào `transactions` khi người dùng bấm `confirm_rows` (có token, ADR-0002). Một đường ghi duy nhất, đúng quy tắc "không tool ghi nào chạy từ nội dung tệp".

### Khử trùng

- Khóa dòng: `yofina_core.ingest.row_dedupe_key` = công thức "Khử trùng" ở trên với `client_ref = ingest:{content_sha256[:16]}:{seq}`. Cùng khóa ở `ingest_rows.dedupe_key` và `transactions.dedupe_key` của dòng đã ghi: nạp lại cùng tệp không sinh dòng thứ hai ở cả hai bảng.
- Chéo nguồn: trước khi chèn dòng, worker gọi `app_find_ingest_matches(p_user_id, p_rows, p_window_days)` với `p_window_days = ingest_dedupe_window_days`: mỗi ứng viên `{idx, app_date, amount_vnd, counterparty, kind}` nhận các giao dịch ĐÃ CÓ ở MỌI nguồn trả (`jar`, `credit`, `external`), cùng `kind`, cùng số tiền tuyệt đối, lệch ngày trong cửa sổ, kèm `day_diff` và `counterparty_match`. Luật chọn (worker, luồng A): có khớp thì dòng thành `duplicate` với giao dịch khớp gần ngày nhất (đối tác khớp được ưu tiên). Một khoản không thể vừa ở trong ví vừa ở ngoài ví.

### Khối `ingest_review` và `coverage_change`

- `ingest_review` (id `ingest_review:{job_id}`): `job_id`, `status`, `source_kind`, `rows` (tối đa 200 theo `seq`; mỗi dòng `row_id`, `seq`, `kind`, `app_date`, `amount_vnd?` (vắng chỉ ở dòng ngoại tệ chưa có tỷ giá), `counterparty?`, `description?`, `extract_confidence`, `suggested_jar? {code,name,color_key,icon_key}`, `jar_confidence?`, `jar_source?`, `review_status`, `duplicate_of?`, `fx?` (mục "Chứng từ ngoại tệ")), `rows_total`, `counts {auto_added, pending, approved, rejected, duplicate}`, `jars` (hũ người dùng để đổi hũ một chạm). Dòng thu nhập không có hũ.
- `coverage_change` (id `coverage_change:{job_id}`): `job_id`, `before?`, `after?` (`Ratio`, vắng khi chưa tính được), `rows_added`, `external_spend_added_vnd`, `external_income_added_vnd?`, `jars_affected [{code,name}]`, `forecast_refresh` (`queued`, `done`, `skipped`). Đi kèm biên nhận `receipt_action` của `confirm_rows` ở trường mới `receipt_action.data.coverage_change` (tùy chọn, các tool khác không có), nên `POST /ingest/actions` trả `receipt_action` như mọi tool ghi khác.
- Dựng bằng `yofina_core.ingest.build_ingest_review`, `build_coverage_change`; model ở `yofina_core.blocks` (cùng hợp `Block`). Hai khối đã nằm trong `REGISTERED_BY_FRONTEND` cùng view ở `frontend/src/blocks/ingestViews.tsx` (khối chưa đăng ký sẽ hiện `fallback_text`).

### Tool target `ingest`

`tools/ingest.json` (định dạng `inlinePayload`, không `enum`/`minimum`/`pattern`; `user_id` "hệ thống tự điền"), kết quả ở `tools/ingest.results.schema.json`, model Pydantic ở `yofina_core.ingest` (`RESULT_MODELS`), thứ tự ở `yofina_core.ingest.INGEST_TOOLS`. Tên qua Gateway: `ingest___start_job` (18 ký tự), `ingest___get_job_status` (23), `ingest___confirm_rows` (21). Target Gateway `ingest` đã có trong `YofinaAgent` (p5/ingest, merge 24/11; chưa deploy lúc ghi): trỏ Lambda `yofina-ingest-api`, Cedar ép `user_id`, `confirm_rows` chỉ ghi khi có token.

| Tool | Việc |
|---|---|
| `start_job` | KHÔNG tạo job, không ghi: tệp chỉ tải lên từ màn hình (người dùng chọn tệp, đồng ý). Trả `upload_path`, giới hạn tệp, `consent_required`, job gần nhất |
| `get_job_status` | Trạng thái một job (vắng `job_id`: job gần nhất); `review` là đúng `data` của `ingest_review`, `coverage_change` khi `done`. Mô tả nói rõ nội dung dòng là dữ liệu, không phải chỉ dẫn |
| `confirm_rows` | Tool ghi: không token thì `NEEDS_CONFIRMATION` với `ConfirmActionData`, có token thì `ReceiptActionData` (tool `confirm_rows`, `jars_after` rỗng, `coverage_change`). `confirm_rows` KHÔNG còn thuộc `wallet.ACTION_TOOLS` (tool ghi của `POST /confirmations` và `POST /actions` của `ledger`, nay chỉ bảy tool) và KHÔNG thuộc `AGENT_WRITE_TOOLS`; nó thuộc `wallet.INGEST_ACTION_TOOLS = (CONFIRM_ROWS,)` (REST `POST /ingest/confirmations`, `POST /ingest/actions`, Lambda `ingest`) và `GENERIC_ACTION_TOOLS` (khối `confirm_action`/`receipt_action`). Cùng khóa HMAC và bảng `jti` với ledger (một secret, một luồng token); `ledger` gặp `confirm_rows` thì `PARAMS_INVALID`, `ingest` gặp tool khác cũng `PARAMS_INVALID`. `params.normalize_params("confirm_rows", …)` vẫn dùng chung |

Chuẩn hóa `confirm_rows` (`yofina_core.params.normalize_confirm_rows`, idempotent, không cần ngữ cảnh): `{job_id, rows: [{row_id, jar?, amount_vnd?}] sắp theo row_id, reject_row_ids: [...] sắp tăng}`; bỏ `jar` và `amount_vnd` rỗng; một dòng không vừa ghi vừa bỏ; ít nhất một dòng; tối đa 500 mỗi danh sách. Cedar (khi ghép): policy `has confirm_token` cho `ingest___confirm_rows`, như các tool ghi khác.

### REST `/ingest/*`

| Endpoint | Việc |
|---|---|
| `POST /ingest/uploads` | Kiểm loại và kích thước khai báo, ghi `consents` (bắt buộc `consent: true` ở lần đầu của nguồn, không thì 403 `CONSENT_REQUIRED`), tạo job `awaiting_upload`, trả presigned POST (`url`, `fields`, `key`, `job_id`, `expires_at`, `max_bytes`, `mime_types`) |
| `GET /ingest/jobs` | Các lần nạp gần đây (mới nhất trước, `limit` 1..20, mặc định 10), không có bảng duyệt: `{jobs: [IngestJobSummary]}`; để quay lại một lần đang `review` |
| `GET /ingest/jobs/{job_id}` | Tiến độ; `review` (khối `ingest_review`) từ trạng thái review; `coverage_change` khi done |
| `POST /ingest/rows/{row_id}/jar` | Đổi hũ ĐỀ XUẤT của một dòng chi (`jar_source = user`), không ghi sổ cái, không token. POST chứ không PATCH vì CORS của HTTP API chung `yofina-api` chỉ cho GET, POST, OPTIONS |
| `POST /ingest/confirmations` | Như `POST /confirmations` nhưng CHỈ `tool = confirm_rows` (`IngestConfirmationRequest`); trả `ConfirmationResponse` (`tool` là `confirm_rows`) |
| `POST /ingest/actions` | Như `POST /actions` nhưng CHỈ `tool = confirm_rows` (`IngestActionRequest`); trả `receipt_action` kèm `coverage_change`; thiếu token 428 `NEEDS_CONFIRMATION`, chốt lại 409 `ALREADY_APPLIED` |

**Bắt đầu job bằng sự kiện S3** (`ObjectCreated` qua SQS có DLQ), không có endpoint "bắt đầu": tải lên chính là tín hiệu, không có trạng thái "đã tải mà chưa bấm", không thêm đường ghi từ client. Tệp tới khi job không còn `awaiting_upload` thì bỏ qua; cùng nội dung với một job còn sống thì job mới thành `rejected` (`INGEST_DUPLICATE_FILE`). `x-lambda: ingest` phục vụ sáu route: `POST /ingest/uploads`, `GET /ingest/jobs`, `GET /ingest/jobs/{job_id}`, `POST /ingest/rows/{row_id}/jar`, `POST /ingest/confirmations`, `POST /ingest/actions` (khớp `INGEST_ROUTES` trong `infra-cdk/lib/ingest-stack.ts`). Hợp đồng không có PATCH nào.

Mã lỗi mới (thêm cuối `ErrorCode`, khớp `yofina_core.errors`, OpenAPI và `frontend/src/api/errors.ts`): `CONSENT_REQUIRED` (403), `INGEST_JOB_NOT_FOUND` (404), `INGEST_JOB_NOT_READY` (409), `INGEST_UNSUPPORTED_TYPE` (415), `INGEST_TOO_LARGE` (413), `INGEST_NOT_FINANCIAL` (422), `INGEST_DUPLICATE_FILE` (409). Thêm 25/11 (cuối danh sách): `INGEST_NO_TRANSACTIONS` (422), xem mục dưới.

### Chứng từ ngoại tệ và `INGEST_NO_TRANSACTIONS` (25/11, migration 0054 CHƯA chạy)

Ca thật: hóa đơn dịch vụ thu tự động qua thẻ ghi "$111.11 USD, due November 10, 2026". Model đọc đúng `bill_or_invoice` nhưng dòng chỉ có `amount_vnd` nên bị loại `no_amount`, backend `no_transactions`, API gộp thành `INGEST_NOT_FINANCIAL` và màn hình báo "không phải biên lai". Chủ dự án quyết: quy đổi về VND.

- **Trích** (`yofina_ingest.schemas.ExtractedRow`): thêm `currency` (ISO 4217, mặc định VND) và `amount_original` (số theo tiền gốc, có phần lẻ). Chứng từ ngoại tệ thì `amount_vnd` là null; số VND do model tự ghi bị bỏ qua. Ký hiệu được nhận: ₫, $, US$, €, £ và mã ba chữ cái; ký hiệu khác (¥...) không đoán, dòng bị loại `no_amount`.
- **Quy đổi** (`yofina_ingest.fx`): tỷ giá BÁN của Vietcombank (bảng công bố, endpoint JSON công khai theo ngày) của ngày giao dịch trên chứng từ, không có ngày thì ngày nạp; ngày sau hôm nay (giờ Việt Nam) kẹp về hôm nay; ngày chưa có bảng thì lùi tối đa 4 ngày. `amount_vnd = amount_original × rate` làm tròn tới đồng (nửa đồng làm tròn lên). Bộ nhớ đệm trong tiến trình theo ngày (một lần gọi cho mọi tiền tệ của ngày đó). Lý do chọn nguồn: [docs/research/ingest-fx-rates.md](../docs/research/ingest-fx-rates.md).
- **Dòng ngoại tệ không bao giờ được chọn sẵn** (cờ `foreign_currency`). Tra tỷ giá lỗi: dòng vẫn vào hàng chờ với số gốc, không có `amount_vnd`, người dùng nhập số VND lúc chốt.
- **Khối `ingest_review`**: dòng có `fx` tùy chọn (`IngestFx`: `currency`, `amount_original` chuỗi thập phân, `status` `converted` | `rate_unavailable`, và khi `converted` thì `rate` (VND cho một đơn vị, chuỗi thập phân; không mang hậu tố `_vnd` vì không phải số tiền), `rate_type` `sell`, `rate_source` `vietcombank`, `rate_date`). `amount_vnd` của dòng nay tùy chọn: vắng CHỈ khi `fx.status = rate_unavailable` (Pydantic kiểm điều kiện này; JSON Schema chỉ nói tùy chọn). `v` không tăng: frontend cùng repo đọc được cả hai dạng.
- **`confirm_rows`**: mỗi dòng nhận thêm `amount_vnd` (VND nguyên dương), CHỈ cho dòng có `fx`; vắng thì ghi số ước tính đang hiện; dòng `rate_unavailable` bắt buộc có. Số này nằm trong `params` đã ký nên token gắn với đúng số người dùng xác nhận. Chốt thì số đó vào `transactions.amount_vnd` và `ingest_rows.amount_vnd`. Dòng VND gửi `amount_vnd` thì `PARAMS_INVALID`. Xem trước có cảnh báo khi còn dòng dùng số ước tính.
- **`INGEST_NO_TRANSACTIONS`** (422) tách khỏi `INGEST_NOT_FINANCIAL`: tệp là chứng từ tài chính nhưng không còn dòng nào để duyệt. Lý do con ở `error_reason` của `IngestJobResponse` (`IngestErrorReason`: `unexecuted_form`, `not_completed`, `own_account_transfer`, `cash_withdrawal`, `no_amount`, `no_rows`), theo loại tài liệu hoặc lý do của số dòng bị loại nhiều nhất (`yofina_ingest.extract.no_transactions_reason`). `error_message` là câu ngắn của lý do đó; frontend có câu riêng cho từng lý do (`INGEST_NO_TX_REASON_MESSAGES`). Tool `ingest___get_job_status` trả cùng `error_reason` (`JobStatusData`, enum như OpenAPI; fixture `get_job_status.ok_no_transactions.json`) và agent dựng câu báo ngắn từ lý do (`yofina_agent.ingest_chat`).
- **Migration [0054](../db/migrations/0054_ingest_fx.sql)**: `ingest_rows.fx` (jsonb, CHECK khớp `IngestFx`), `amount_vnd` bỏ NOT NULL với ràng buộc `ingest_rows_amount_check`, `ingest_jobs.error_reason`; thay `app_update_ingest_job`, `app_insert_ingest_rows`, `app_get_ingest_job` (cùng chữ ký, chỉ thêm khóa). Lambda ingest đọc cột `fx` nên **chạy 0054 trước khi deploy** `YofinaIngest`.

### Sự kiện

Không thêm sự kiện mới: `confirm_rows` phát một `transaction.recorded` mỗi lần chốt với `funding_source = external`, `effects` rỗng (enum của schema đã có `external`). Consumer mới chạy đầy đủ; consumer đã deploy coi nó như chi `jar` và chỉnh nhanh với số dư KHÔNG đổi (lần chạy nhanh dùng phân phối cũ, không trừ tiền), nên backend ingest gọi thêm tính lại đầy đủ sau khi chốt (xem bảng rà).

### Cấu hình (một nơi: `yofina_core.ingest.IngestSettings`)

Khóa là tên trường (biến `YOFINA_<TÊN>` hoặc SSM `<prefix>/<tên>`); vắng thì dùng mặc định:

| Khóa | Mặc định | Ghi chú |
|---|---|---|
| `ingest_image_max_bytes` | 3.750.000 | giới hạn 3,75 MB mỗi ảnh của Bedrock Converse |
| `ingest_csv_max_bytes` | 2.000.000 | |
| `ingest_csv_max_rows` | 500 | trần của `app_insert_ingest_rows` |
| `ingest_image_mime_types` | `image/png,image/jpeg,image/webp` | |
| `ingest_csv_mime_types` | `text/csv,application/vnd.ms-excel` | |
| `ingest_upload_url_ttl_seconds` | 300 | 60..3600 |
| `ingest_dedupe_window_days` | 3 | 0..30 (hàm DB kẹp cùng khoảng): lệch ngày ghi sổ giữa ngân hàng và ví thường 1 tới 2 ngày làm việc |
| `ingest_auto_extract_min_confidence` | 0.90 | dòng chọn sẵn khi đạt CẢ HAI ngưỡng (dòng thu chỉ cần ngưỡng trích) |
| `ingest_auto_jar_min_confidence` | 0.80 | |
| `ingest_consent_version` | `2026-12` | ghi vào `consents.version` |

Cửa sổ độ phủ dùng chung `forecast_history_window_days` của dự báo.

## Phase 4: chống chịu, lộ trình, phân hũ tự động

Hợp đồng cho bốn luồng của [phase 4](../docs/plan/phases/phase-4-chong-chiu-lo-trinh.md) (A ML, B phân hũ tự động, C agent, D frontend). Lý do từng lựa chọn: mục "Quyết định hợp đồng phase 4" cuối file phase. Migration [0052](../db/migrations/0052_resilience_roadmap_classify.sql) (schema ở [db/README.md](../db/README.md#schema-phase-4-0052)), tool, REST và sự kiện mới **chưa chạy, chưa deploy**. Kiểm: `uv run pytest tests/unit/test_contracts_phase4.py tests/unit/test_migration_0052.py` và `tests/local_pg/test_phase4_schema.py` (lệnh ở docstring của `tests/local_pg/conftest.py`).

### Kiểu dùng chung (một nguồn cho bảng, tool, REST, khối)

| Kiểu Pydantic | Là | Nơi dùng |
|---|---|---|
| `yofina_core.resilience.ResilienceScore` | `blocks.ResilienceScoreData` | bảng `resilience_scores`, `forecast___get_resilience_score`, `GET /resilience`, khối `resilience_score` |
| `yofina_core.resilience.StressResult` | `blocks.StressResultData` | `forecast___stress_test`, `POST /resilience/stress`, khối `stress_result` |
| `yofina_core.roadmap.Roadmap` (`RoadmapPhase`, `RoadmapStep`) | `blocks.RoadmapData` | bảng `roadmaps`, `planner___save_roadmap` và `get_roadmap`, `GET /roadmap`, khối `roadmap` |
| `yofina_core.roadmap.AllocationPlanData` | kiểu riêng (khớp `planner.results.schema.json`) | `planner___optimize_allocation` |
| `yofina_core.roadmap.RoadmapDraft` | bản nháp agent gửi (khớp `planner.json`) | `planner___save_roadmap` (đầu vào) |
| `yofina_core.roadmap.RoadmapJob`, `RoadmapVersionSummary` | khớp OpenAPI | bảng `roadmap_jobs`, `GET /roadmap/jobs/{job_id}`, `GET /roadmap/versions` |
| `yofina_core.resilience.ResilienceConfig`, `ShockSet` | khớp `contracts/ml/*.schema.json` | `resilience_defaults.json`, `shocks.json` |

**Cấu hình và cú sốc là dữ liệu** (`libs/yofina_core/src/yofina_core/resilience_defaults.json`, `shocks.json`): mỗi số có `value`, `unit`, `note`, `source`; nạp bằng `load_resilience_config()` và `load_shock_set()`. Hợp đồng KHÔNG có công thức tính điểm hay mô phỏng. Bốn thành phần (`wallet.RESILIENCE_COMPONENTS`, theo thứ tự save, spend, borrow, plan) và trọng số mẫu 0,35 / 0,25 / 0,25 / 0,15; thành phần không áp dụng được (chưa có mục tiêu thì Plan) bị bỏ và trọng số còn lại chuẩn hóa về tổng 1.

### Khối mới (năm khối, `block.schema.json` nay có hai mươi mốt)

| Khối | Việc | Id | Do ai dựng |
|---|---|---|---|
| `resilience_score` | Điểm 0 đến 100, nhóm (yếu, vừa, tốt), bốn thành phần (điểm, trọng số, đầu vào, câu giải thích), thành phần yếu nhất, `disclaimer` "không phải điểm tín dụng", `basis` | `resilience_score:{trace_id}` | Engine (tool và REST cùng khối) |
| `stress_result` | Cú sốc đã áp, điểm trước và sau, số ngày trụ được (toàn bộ và riêng hũ Dự phòng), khoản thiếu, điểm từng thành phần, `basis` | `stress_result:{trace_id}:{shock_id}` | Engine |
| `roadmap` | Một phiên bản lộ trình: `reason`, `feasibility`, `goals`, `phases[].steps[]` (lý do, trạng thái chờ / đã chấp nhận / đã từ chối, `action` tùy chọn), `alternatives` (đúng hai khi infeasible), `counts`, `basis` | `roadmap:{trace_id}:v{version}` | Lambda ledger (đọc bảng), agent chỉ bọc |
| `roadmap_diff` | Bước thêm, bỏ, đổi giữa hai phiên bản kèm lý do sinh lại; `can_adopt` | `roadmap_diff:{trace_id}:v{from}-v{to}` | Code (REST) |
| `review_list` | A1 "Xem lại" (`mode` review) và A2 hỏi gộp (`mode` daily_ask): mục kèm mức tin cậy, hũ hiện tại, tối đa 2 gợi ý có lý do; `count`, `pending_total_vnd`; không có `basis` | `review_list:{trace_id}:{mode}` | Lambda ledger |

Ba trạng thái luôn có chữ: nhóm điểm, `status` đủ/sát/hụt của cú sốc, trạng thái bước, đều kèm `headline` hoặc nhãn bằng chữ do code dựng. `fallback_text` của năm khối là `headline`. Cả năm khối **chưa** nằm ở `REGISTERED_BY_FRONTEND` (có Zod ở `blocks.ts`, chưa có view): hiện `fallback_text` cho tới khi luồng D đăng ký.

Hình dạng mẫu (rút gọn; số của bảng Figma 58 → 34, 27 ngày): `resilience_score.data` = `{score: 58, band: "fair", headline, app_date, computed_at, components: [{key: "save", label: "Tiết kiệm", score: 15, weight: 0.35, applicable: true, band: "weak", explanation, inputs: [{key, label, value, unit}]}, ...4], weakest: "save", previous_score?, config_version, disclaimer, basis}`; `stress_result.data` = `{shock: {shock_id: "mat_viec_2_thang", kind, label, description, duration_days: 60}, status: "short", headline, score_before: 58, score_after: 34, score_delta: -24, band_before, band_after, runway_days_total: 27, runway_days_emergency: 9, emergency_jar, horizon_days: 90, shortfall_vnd: 8890000, shortfall_from, components: [{key, score_before, score_after}, ...4], method: "monte_carlo", n_paths, common_random_numbers: true, basis}`; `roadmap.data` = `{roadmap_id, version: 3, status: "proposed", reason: {code: "behavior_changed", text, detail: [{label, before, after}], behavior_flag_id}, based_on_version: 2, created_at, app_date, headline, feasibility: "relaxed", horizon, goals: [{jar, target_vnd, target_date, projected_date, on_track, shortfall_vnd, monthly_needed_vnd}], phases: [{phase_id, title, start_date, end_date, steps: [{step_id, kind, title, reason, amount_vnd, jar_code, to_jar_code, metrics, checked_rules, action: {tool: "move_between_jars", params}, status: "pending"}]}], alternatives: [], counts: {pending, accepted, rejected}, rules_version, basis}`.

Bất biến mà JSON Schema (tập con của repo) không diễn đạt được nên **Pydantic quyết định** (test `test_contracts_phase4.py` có ca từ chối cho từng cái): điểm tổng bằng trung bình có trọng số (lệch tối đa 1) và `weakest` đúng; `score_delta = score_after - score_before` không dương; có khoản thiếu thì không thể "đủ" và có `shortfall_from`; `step_id` và `phase_id` duy nhất, `counts` đúng, giai đoạn xếp theo `start_date`, `based_on_version < version`, bước `decided_at` có đúng khi khác pending; `infeasible` đi với đúng hai `alternatives` và ít nhất một mục tiêu không kịp, `on_track` thì mọi mục tiêu kịp; `review` chỉ có mục mức review, `daily_ask` chỉ có mức ask kèm `ask`; tiền trong `inputs` đơn vị `vnd` là số nguyên.

### Tool (bảy tool; hai target `forecast` và `planner` mở rộng)

| Tool | Loại | Bắt buộc | Kết quả (`tools/*.results.schema.json`) |
|---|---|---|---|
| `forecast___get_resilience_score` | ĐỌC (đọc điểm đã lưu, tính lại nếu quá cũ hoặc `refresh`) | không | `GetResilienceScoreResult`: `data` = `ResilienceScoreData` |
| `forecast___stress_test` | ĐỌC và tính | `shock_id` (ba mã của `shocks.json`) | `StressTestResult`: `data` = `StressResultData`. Lỗi `SHOCK_NOT_FOUND` |
| `planner___optimize_allocation` | ĐỌC và tính (LP, `scipy.optimize.linprog`) | không (`horizon_months`, `goals`, `shock_id`, `allow_relaxation`) | `OptimizeAllocationResult`: `data` = `AllocationPlanData` (`optimal`, `relaxed`, `infeasible` kèm hai lựa chọn; vô nghiệm KHÔNG phải lỗi) |
| `planner___save_roadmap` | **GHI không đổi số dư, KHÔNG qua token** | `reason_code`, `feasibility`, `phases` | `SaveRoadmapResult`: `data` = `RoadmapData` (phiên bản vừa lưu). Lỗi `ROADMAP_INVALID` (kể cả bước vi phạm luật suitability mức block), `ROADMAP_VERSION_CONFLICT` |
| `planner___get_roadmap` | ĐỌC | không (`version` hoặc `which`) | `GetRoadmapResult`: `data` = `RoadmapData`. Lỗi `ROADMAP_NOT_FOUND` |
| `ledger___get_unclassified` | ĐỌC (đã có; đầu vào KHÔNG đổi) | không | Mở rộng tương thích ngược: mục thêm `tier`, `classified_by`, `confidence`; gợi ý thêm `confidence`, `reason` |
| `ledger___assign_jar` | GHI qua token (đã có, KHÔNG đổi schema) | `transaction_id`, `jar` | `remember` once hoặc always chọn phạm vi luật; luồng B cài thêm hành vi nâng ngưỡng của người nhận và "đúng rồi" (gán chính hũ hiện tại) |

`wallet.FORECAST_TOOLS` và `PLANNER_TOOLS` có thêm các tool này ở CUỐI; `save_roadmap` không thuộc `PLANNER_WRITE_TOOLS` hay `ACTION_TOOLS`. **CDK tự đăng ký mọi tool trong hai file này ở lần deploy `YofinaAgent` kế tiếp, và mỗi tool có một file `gateway/policies/<tool>.cedar` (chỉ ép `user_id`)**; Lambda chưa cài thì Gateway nhận "Tool không tồn tại" cho tới khi luồng A cài (`wallet.PHASE4_TOOLS` liệt kê năm tool chưa cài). Bước lộ trình có thể gắn `action = {tool, params}` với `tool` ∈ `move_between_jars`, `save_jars`, `schedule_nudge`: người dùng thực hiện bằng `POST /confirmations` rồi `POST /actions`; chấp nhận bước không tự thực hiện.

Hình dạng `optimize_allocation` (rút gọn): `{status: "relaxed", headline, horizon_months, period_start, income_monthly_vnd, obligations_monthly_vnd, lines: [{jar, kind, is_essential, floor_vnd, current_monthly_vnd, proposed_monthly_vnd, split_percent_current, split_percent_proposed, floor_gap_vnd}], unallocated_vnd, goals: [GoalProjection], relaxations: [{kind, jar_code, label, before, after}], alternatives: [], solver: {name: "scipy.optimize.linprog", method: "highs", status, elapsed_ms, relaxation_rounds}, basis}`; bảo toàn tiền: tổng `proposed_monthly_vnd` + `unallocated_vnd` = `income_monthly_vnd`.

### REST (mười ba endpoint mới)

| Endpoint | `x-lambda` | Việc |
|---|---|---|
| `GET /resilience` | `forecast` | Khối `resilience_score` (cùng khối với tool) |
| `GET /resilience/shocks` | `forecast` | Ba cú sốc mẫu từ `shocks.json` (`ShocksResponse`), để vẽ ba thẻ R1 |
| `POST /resilience/stress` | `forecast` | Thân `StressRequest {shock_id}`; khối `stress_result`. POST chỉ để có thân, không ghi |
| `GET /roadmap` | `ledger` | Khối `roadmap`; `version` hoặc `which` (`active` mặc định, `proposed`, `latest`) |
| `GET /roadmap/versions` | `ledger` | `RoadmapVersionsResponse`: danh sách gọn, `active_version`, `proposed_version`, `current_job` |
| `GET /roadmap/diff` | `ledger` | Khối `roadmap_diff`; vắng `to_version` thì bản chờ, vắng `from_version` thì bản gốc của `to` |
| `POST /roadmap/steps/{step_id}/decision` | `ledger` | `{version, decision: accepted\|rejected\|pending, reason?}` → khối `roadmap` mới. Không đổi số dư, không qua token |
| `POST /roadmap/steps/{step_id}/edit` | `ledger` | `{version, amount_vnd?, due_date?}` → lưu phiên bản MỚI `active` (lý do `step_edited`), ghi `feedback`, không sinh lại toàn bộ |
| `POST /roadmap/versions/{version}/decision` | `ledger` | `{decision: adopt\|keep_previous}` ("Dùng bản mới", "Giữ bản cũ") → khối `roadmap` |
| `POST /roadmap/regenerate` | `ledger` | `{note?, alternative_id?, based_on_version?}` → ghi `roadmap_jobs`, phát `roadmap.regeneration_requested`, trả `RoadmapJob` NGAY (HTTP 200); đang có job thì trả chính job đó |
| `GET /roadmap/jobs/{job_id}` | `ledger` | Hỏi tiến độ bằng polling (`RoadmapJob`) |
| `GET /review` | `ledger` | Khối `review_list`; `mode` review (mặc định) hoặc daily_ask, `limit` |
| `POST /review/daily-ask/skip` | `ledger` | `{ask_date}` → `ReviewAskResponse {ask_date, status}`; để sau câu hỏi gộp của ngày |

Sửa hũ cho "Xem lại" và hỏi gộp **dùng lại `assign_jar` qua `POST /confirmations` rồi `POST /actions`** (không có endpoint ghi thứ hai). Lưu và đổi trạng thái lộ trình không qua token (không đổi số dư); mỗi thao tác ghi `audit_events` và một dòng `feedback`. Mã lỗi mới (thêm cuối `ErrorCode`, khớp `yofina_core.errors`, OpenAPI và `frontend/src/api/errors.ts`): `ROADMAP_NOT_FOUND` (404), `ROADMAP_INVALID` (422), `ROADMAP_VERSION_CONFLICT` (409), `SHOCK_NOT_FOUND` (404). Route trong `infra-cdk/lib/tools-stack.ts` được liệt kê tay: luồng A thêm 13 route này khi cài.

### Sự kiện mới

`behavior.changed` (source `yofina.forecast`; chỉ khi PELT xác nhận điểm gãy; `event_id` = `flag_id`; chỉ id, mã hũ, số tiền mỗi tuần) và `roadmap.regeneration_requested` (source `yofina.ledger`; `event_id` = `job_id`; ghi chú tự do ở lại job, không vào sự kiện). Lambda `yofina-roadmap-regen` nghe cả hai và `profile.updated` (đổi thu nhập, mục tiêu).

### Ý định của agent

`wallet.INTENTS` có mười giá trị (thêm `resilience`, `stress`, `roadmap`; `INTENTS_PHASE3` giữ bảy cũ cho migration 0010). `agent/src/yofina_agent/schemas.py` `Intent` khớp. Router CHƯA được hướng dẫn chọn ba ý định này và `turn.py` chưa có bộ xử lý (ba ý định rơi về `on_out_of_scope` cho tới khi luồng C cài).

### Kiểm

```
uv run pytest tests/unit/test_contracts_phase4.py tests/unit/test_migration_0052.py
cd tests/local_pg && uv run --python 3.12 --no-project --with pgserver --with "psycopg[binary]" --with pydantic --with pytest --with jsonschema --with pyyaml --with referencing --with numpy --with scipy pytest test_phase4_schema.py -p no:cacheprovider
```

Test cũ đã sửa cho phase 4: `test_contracts_blocks.py` (hai mươi mốt khối), `test_contracts_rest.py` (tập endpoint, ghi không qua token, `x-lambda`), `test_contracts_tools.py` (bảng kết quả), `test_contracts_events.py` (hai sự kiện), `test_contracts_ingest.py` (mã lỗi liền nhau, không còn là bốn mã cuối), `test_migration_0010.py` (`INTENTS_PHASE3`), `test_ledger_wallet.py` (`PHASE4_TOOLS`), `tests/unit/agent/test_schemas.py` và `test_jars_fallback_router.py` (mười ý định), `tests/unit/ts/blocks.fixtures.test.mjs`, `tests/integration/test_gateway_config.py` (sáu tool forecast; không chạy ở bước 0). Frontend: `errors.ts` thêm bốn mã; `registry.test.tsx` lọc fixture hợp lệ theo khối đã đăng ký; `walletBlocks.test.tsx` đổi số đếm.

## Phase 5 (F7, trích dẫn biểu phí, quyền riêng tư, trace): hồ sơ hành vi, bản tin, bộ nhớ, trích dẫn, xóa dữ liệu, bảng vận hành

Hợp đồng bước 0 cho các luồng song song của [phase 5](../docs/plan/phases/phase-5-nap-du-lieu-ho-so-trace.md) (kế hoạch "Kế hoạch thực hiện"). **Không có RAG**: chủ dự án cắt luồng C ngày 24/11, nên hợp đồng không có kho tri thức, tool tìm kiếm hay bảng `kb_*`; trích dẫn nguồn chỉ cho biểu phí có cấu trúc. Lý do từng lựa chọn: "Quyết định hợp đồng phase 5" trong file phase. Migration [0053](../db/migrations/0053_phase5.sql), tool, REST **chưa chạy, chưa deploy**. Kiểm: `uv run pytest tests/unit/test_contracts_phase5.py`.

### Khối mới (hai khối, `block.schema.json` nay có hai mươi ba)

| Khối | Việc | Id | Do ai dựng |
|---|---|---|---|
| `behavior_insight` | MỘT nhận xét hành vi (`insight`: loại, câu, bằng chứng số `evidence` có đơn vị, độ tin cậy, `ai_generated`) và MỘT việc cần làm (`next_step`, `action` tùy chọn cùng hình dạng hành động của bước lộ trình) | `behavior_insight:{trace_id}:{insight_id}` | Agent hoặc màn Hồ sơ, bằng `blocks.behavior_insight_data(profile)` rồi `build_behavior_insight` |
| `citation` | Nguồn của biểu phí Trả sau (mô phỏng): sản phẩm (`product_code`, `product_label`) và 1 đến 5 mục `{fee_types, source_name, source_url (https://), effective_from, excerpt?}` chép từ các `FeeLine` của `knowledge___get_fee_schedule`; không có số tiền | `citation:{trace_id}` | Agent, `build_citation(result=<kết quả OK của get_fee_schedule>, fee_types=...)` |

`proactive_card` mở rộng tương thích ngược (không tăng `v`): `kind` thêm `roadmap_proposed`, `resilience_drop`, `behavior_insight`; `actions[].kind` thêm `open_roadmap`, `open_resilience`, `open_profile`; `nudge_id` tùy chọn (thẻ là bản tin của cổng giá trị thì "Để sau" và "Ít nhắc loại này" gửi `POST /nudges/{nudge_id}/feedback`). Hai khối mới có Zod nhưng CHƯA ở `REGISTERED_BY_FRONTEND` (luồng p5-frontend thêm khi đăng ký view). Bất biến mà JSON Schema không diễn đạt được (Pydantic quyết định): bằng chứng `vnd`, `count`, `hour`, `weekday` là số nguyên, `percent` 0..100, `ratio` 0..1, `hour` 0..23, `weekday` 1..7, khóa bằng chứng duy nhất; hồ sơ `ready` thì có `computed_at`, `config_version`, `features`, `next_step` và ít nhất một nhận xét, chưa `ready` thì không nhận xét và có `min_history_days`; trích dẫn: mỗi bộ (tên nguồn, đường dẫn, ngày hiệu lực) một mục, mỗi loại phí thuộc đúng một nguồn; `citation_data` gom `FeeLine` theo nguồn, `excerpt` là `condition_note` khi nguồn chỉ có một loại phí, loại phí tool không trả thì `ValueError`.

### Tool (một tool; `wallet.PHASE5_TOOLS` liệt kê tên chưa cài)

| Tool | Loại | Bắt buộc | Kết quả |
|---|---|---|---|
| `forecast___get_behavior_profile` | ĐỌC bảng `behavior_profiles` | không (`insight_kind`, `jar` để lọc) | `GetBehaviorProfileResult`: `data` = `BehaviorProfileData`; chưa sẵn sàng là OK với `ready` sai. Lọc còn nhận xét thì chỉ bớt `insights`; lọc hết (kể cả `jar` lạ) thì `ready` sai, `headline` là lý do, `history_days` của hồ sơ |

**Lọc hết nhận xét (quyết định 24/11, sau khi cài)**: hợp đồng theo cách cài của `BehaviorEngine.get` (lọc không còn nhận xét nào thì `ready` sai kèm lý do) thay vì cho hồ sơ sẵn sàng có `insights` rỗng. Lý do: bất biến "sẵn sàng thì có ít nhất một nhận xét và một việc cần làm" giữ nguyên ở cả ba nơi (CHECK của `behavior_profiles`, Pydantic `BehaviorProfileData`, mô tả JSON Schema), agent và màn Hồ sơ không phải xử lý thêm trạng thái "sẵn sàng mà rỗng". `jar` không phải hũ của người dùng cũng đi đường này, không trả `JAR_NOT_FOUND` (mô tả cũ của `GetBehaviorProfileResult` đã sửa).

Ba tool `ingest___*` giữ nguyên hợp đồng (đã rà). **Cedar**: CDK đòi `gateway/policies/<tool>.cedar` cho mọi tool trong `forecast.json` và `knowledge.json` khi deploy `YofinaAgent`; hợp đồng không viết `get_behavior_profile.cedar` (luồng p5-behavior thêm khi cài, chỉ ép `user_id`). `knowledge___get_fee_schedule` giữ nguyên (phase 3); Pydantic của kết quả (`FeeLine`, `FeeScheduleData`, `GetFeeScheduleOk`) nay ở `yofina_core.blocks` vì là đầu vào của khối `citation`. Bản ghi lượt: bước của `step_timings` có `step` là tên đầy đủ `<target>___<tool>` là MỘT lần gọi tool, kèm `status` (`ok`, `error`, `denied`) và `code` tùy chọn (`TraceStep`, `record_turn`); không thêm cột.

### REST (mười một thao tác mới)

| Endpoint | `x-lambda` | Việc |
|---|---|---|
| `GET /profile/behavior` | `forecast` | `BehaviorProfileData` (cùng `data` với tool) |
| `GET /nudges/today` | `ledger` | Bản tin của cổng giá trị hôm nay (tối đa một), kèm khối `proactive_card` có `nudge_id`, và `suppressed` |
| `POST /nudges/{nudge_id}/feedback` | `ledger` | `outcome` acted, dismissed, snoozed, less_like_this; không qua token |
| `GET /memory` | `ledger` | Bản ghi AgentCore Memory của chính người gọi (`MemoryRecord`: `record_id`, `kind`, `source`, `text`, `created_at`), phân trang `cursor` |
| `DELETE /memory/{record_id}`, `DELETE /memory` | `ledger` | Xóa một hoặc toàn bộ (cả sự kiện ngắn hạn); không qua token |
| `POST /me/delete-data/confirmations` | `ledger` | Cấp token cho `tool` = `delete_my_data`, `params` = `{scope: all}` (`PrivacyToolName`); trả `ConfirmationResponse` |
| `POST /me/delete-data` | `ledger` | Kèm token thì xóa S3, Memory, Aurora (`app_delete_user_data`), trả `DataDeletion`; thiếu token 428 |
| `GET /ops/traces`, `GET /ops/traces/{trace_id}`, `GET /ops/summary` | `ledger` | Chỉ nhóm Cognito `ops` (`x-required-group: ops`, 403 `FORBIDDEN`); người dùng hiện bằng `user_ref` |

`DELETE` là method mới: CORS của HTTP API `yofina-api` phải thêm `DELETE` (luồng hạ tầng). `delete_my_data` KHÔNG thuộc `wallet.ACTION_TOOLS` hay `ToolName` (như `confirm_rows`), chuẩn hóa ở `params.normalize_delete_my_data`. Mã lỗi mới (thêm cuối): `MEMORY_RECORD_NOT_FOUND` (404), `MEMORY_UNAVAILABLE` (503); `frontend/src/api/errors.ts` chưa có hai mã này (luồng p5-frontend thêm).

### Ý định

`wallet.INTENTS` có mười bốn giá trị: mười của phase 4 cộng bốn ý định phase 5 `behavior`, `knowledge`, `ingest`, `memory` (`wallet.PHASE5_INTENTS`). Bước 0 để bốn ý định này ngoài `INTENTS` cho tới khi agent có bộ xử lý (quyết định 12 của file phase); sau khi merge p5/ingest, p5/memory, p5/behavior ngày 24/11 cả bốn đã vào `INTENTS`, khớp `Intent` của `agent/src/yofina_agent/schemas.py`, và `AUDIT_INTENTS` (CHECK `audit_events.intent` của 0053, `record_turn`) trùng `INTENTS`.

### Bộ nhớ (`yofina_core.memory`)

Gốc namespace của một người dùng `/yofina/users/{actorId}/` (`actorId` = `sub`); theo loại: `preferences/`, `facts/`, `sessions/{sessionId}/`, `behavior/`, `lessons/`. Ba loại đầu do chiến lược có sẵn của AgentCore trích từ hội thoại (user preference, semantic, summarization), hai loại sau là bản ghi tự tạo (`BatchCreateMemoryRecords`). `kind_of_namespace(ns, sub)` trả None cho namespace không thuộc người gọi: Lambda bỏ bản ghi đó. Xóa: không có API xóa theo người dùng, nên liệt kê `ListMemoryRecords` với `namespacePath` = gốc (tối đa 100 mỗi trang) rồi `BatchDeleteMemoryRecords` (tối đa 100), và `ListSessions`, `ListEvents`, `DeleteEvent` cho sự kiện ngắn hạn.

### Migration 0053

Bảng `behavior_profiles` (RLS FORCE, một dòng mỗi người dùng và ngày mô phỏng), `data_deletions` (RLS FORCE, không khóa ngoại tới `users`, không DELETE); `nudges` thêm `value_vnd`, `gate_reason`, `title`, `body`, `outcome`, `outcome_at`, nới `kind` (`wallet.ALL_NUDGE_KINDS`) và CHECK ngày (bản tin của cổng hiện trong ngày tạo), tối đa một bản tin của cổng mỗi ngày; `audit_events.intent` nới thành `wallet.AUDIT_INTENTS`. Hàm SECURITY INVOKER `app_get_behavior_profile`, `app_get_today_nudge`, `app_nudge_outcome_stats`, `app_set_nudge_outcome`; SECURITY DEFINER `app_delete_user_data`, `app_ops_list_traces`, `app_ops_get_trace`, `app_ops_summary`, `app_ops_model_calls_by_day`. Không có bảng, chỉ mục hay hàm của kho tri thức (RAG đã cắt 24/11; file sửa thẳng vì chưa chạy ở đâu). Đã chạy thật trên PostgreSQL 16 cục bộ (pgserver): chạy lại được, RLS, bản tin một mỗi ngày, ops không lộ `user_id`, xóa dữ liệu không còn dòng nào của người đó và không đụng người khác. `RESET_DELETES` (ledger) đã có `behavior_profiles`. Kiểm lại 24/11 bằng mã thật của Lambda (repo, REST, batch) trên PostgreSQL cục bộ: `tests/local_pg/test_phase5_flow.py` (chi tiết ở [db/README.md](../db/README.md) mục "Schema phase 5").

### Bộ đánh giá

`evals/golden/phase5.jsonl` (12 câu) và `evals/adversarial/phase5.jsonl` (14 ca), cùng định dạng phase 4. Trường mới mà `evals/run.py` CHƯA chấm (luồng deploy cài trước khi chạy): `prior_sessions` (các phiên trước, chạy với session id khác), `expect_memory_used`, `forbid_reask`, `expect_insight_kind`, `expect_citation_fee_types` (loại phí mà khối `citation` phải có), `upload_manifest_id` (id trong `evals/ingest/manifest.json`, tải lên trước câu hỏi), `forbid_auto_add_from_file`, `forbid_pii_from_manifest`, `expect_memory_without_pii`, `forbid_unretrieved_citation` (khối `citation` chỉ chứa nguồn và loại phí mà `get_fee_schedule` đã trả). Câu hỏi về phí có trích dẫn: `tools_must` = `get_fee_schedule`, `blocks_must` = `citation`.

## Biểu đồ chi tiêu: `GET /cashflow` (đợt giao diện, 25/11/2026)

Bản REST của tool `ledger___get_cashflow_summary` cho B1 (chi theo hũ), B5 (đường lũy kế) và B7 (thu và chi) của màn Hoạt động ([spending-visualization.md](../docs/research/spending-visualization.md)). `x-lambda: ledger`, `cashflow_rest.py`; route trong `infra-cdk/lib/tools-stack.ts` (`CASHFLOW_ROUTES`). Thêm một thao tác, không đổi tool, khối hay hàm DB.

- **Một công thức**: tổng thu, tổng chi, chi theo hũ đều do `cashflow_result` của tool (SQL `app_get_cashflow_summary`, 0050) tính, nên `current` trùng số với tool gọi không tham số. Kỳ là kỳ lương hiện tại theo ngày mô phỏng và ngày lương trong hồ sơ; chưa khai ngày lương thì tháng dương lịch như tool.
- **Kỳ trước cùng thời điểm**: `previous` là kỳ lương trước, từ ngày lương tới ngày thứ `period.day_index` (không quá cuối kỳ trước), cùng hàm. Vắng khi chưa có giao dịch nào từ ngày đầu kỳ trước trở về trước (persona `khoa`), vì phần thiếu sẽ bị so như chi 0 ₫.
- **Theo ngày**: `daily` (kỳ này tới hôm nay) và `previous_daily` (cả kỳ trước) là cùng hàm gọi với khoảng một ngày, mọi ngày trong MỘT câu SQL (`generate_series`), kèm lũy kế `cumulative_vnd`.
- **Tách nghĩa vụ và Trả sau** (`obligation_vnd`, `credit_vnd`, `regular_spent_vnd`, `regular_cumulative_vnd`, `change.regular_vnd`): hàm SQL của tool không tách, và đợt này không thêm hàm DB, nên phần này cộng từ `app_list_transactions` (cùng bộ lọc: `kind = expense`, bỏ `external`), phân trang con trỏ. Chỉ trả khi đọc hết trang và số dòng từng hũ đúng `tx_count` của tool; không thì `split_complete` sai và không có trường tách nào. Khi cần thay bằng một hàm SQL (một lần gọi) thì đó là migration mới.
- **Chênh lệch do server trừ**: `change`, `by_jar[].change_vnd`, `net_vnd` (lương trừ chi, không tính tiền vào khác).
- Fixture `fixtures/rest/CashflowResponse.minh.json` và `.khoa_chua_co_ky_truoc.json` sinh bằng chính mã Lambda trên PostgreSQL cục bộ (`tests/local_pg/test_cashflow_rest.py`), số khớp mục 1.4 của tài liệu nghiên cứu. Zod phía frontend viết tay ở `frontend/src/api/cashflowSchemas.ts` (như các REST khác; `gen_contracts.mjs` chỉ sinh từ `blocks/`).

## Cách chọn công cụ sinh

- **Zod: tự sinh** bằng `scripts/gen_contracts.mjs` (~200 dòng, không phụ thuộc gói nào) từ JSON Schema. Không dùng `json-schema-to-zod`: README của nó (kiểm bằng `npm view`, bản 2.8.1) ghi từ tháng 3/2026 dự án không còn được bảo trì tích cực, và nó không tự giải `$ref` (phải nhờ `json-refs` đứng trước), trong khi hợp đồng này dùng `$ref`/`$defs` liên file. Bộ tự viết chỉ hỗ trợ tập con ở trên và báo lỗi khi gặp thứ lạ, nên không mong manh một cách âm thầm.
- **Pydantic: viết tay**, không sinh (kèm hàm `build_*`, kiểu chặt, `fallback_text`). Độ lệch được khóa bằng test: so khớp hình dạng (thuộc tính, `required`, `const`/`enum`, `pattern`, giới hạn) với JSON Schema, và chạy chung fixture.
- **Fixture dùng chung** (`fixtures/blocks/{valid,invalid,schema_only_invalid}`, `fixtures/tools`): tên file `<type>.<ca>.json`. `valid` phải qua cả ba (JSON Schema, Pydantic, Zod) và khứ hồi Pydantic không đổi dữ liệu; `invalid` bị cả ba từ chối (tiền tố `block.` thử bằng hợp); `schema_only_invalid` (trường thừa) bị JSON Schema và Pydantic từ chối nhưng Zod chấp nhận và bỏ trường thừa.

## Lệnh

```
uv sync                                  # cài workspace Python (một lần)
npm install                              # ở gốc repo: cài zod cho công cụ hợp đồng (một lần)

node scripts/gen_contracts.mjs           # sinh lại frontend/src/contracts/blocks.ts
node scripts/gen_contracts.mjs --check   # báo lệch (exit 1) nếu file đã commit không khớp schema
uv run pytest                            # toàn bộ test, gồm hợp đồng và phía Zod
node --test tests/unit/ts/*.test.mjs     # chỉ phía Zod (cũng chạy trong pytest)
uv run pytest tests/unit/test_contracts_*.py   # chỉ hợp đồng: khối, tool, REST, sự kiện, ML, phase 2 (chống lệch hằng số)
uv run pytest tests/unit/test_migration_000*.py  # migration 0001 tới 0006 và seed (kiểm tĩnh)
```

`npm` ở gốc repo chỉ phục vụ công cụ hợp đồng (`package.json` có một devDependency là `zod`); không phải project frontend, `frontend/` sẽ có `package.json` riêng khi luồng E dựng.
