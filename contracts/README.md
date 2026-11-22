# contracts/

Nguồn duy nhất cho **hợp đồng** giữa frontend, agent, Lambda tool, REST, sự kiện và ML. Mọi bên đọc từ đây; muốn đổi hợp đồng thì sửa ở đây trước, rồi sinh lại và chạy test. Kế hoạch: [phase 1 mục "Bước 0"](../docs/plan/phases/phase-1-nen-va-lat-doc.md), [phase 2 mục "Bước 0"](../docs/plan/phases/phase-2-vi-va-du-bao.md); quyết định liên quan: [ADR-0002](../docs/decisions/0002-xac-nhan-truoc-khi-ghi.md) (xác nhận trước khi ghi), [ADR-0003](../docs/decisions/0003-dong-ho-mo-phong.md) (đồng hồ mô phỏng); các lựa chọn thiết kế của phase 2 (hũ hệ thống, nguồn trả, tổng số dư...) ở mục "Quyết định hợp đồng phase 2" cuối [file phase 2](../docs/plan/phases/phase-2-vi-va-du-bao.md).

| Thư mục / file | Nội dung | Ai dùng |
|---|---|---|
| `blocks/envelope.schema.json` | Phong bì chung của khối UI và các kiểu cơ bản (`Vnd`, `VndSigned`, `Ratio`, `JarCode`, `IsoDate`...) | tất cả |
| `blocks/{jar_summary,confirm,receipt,notice}.schema.json` | Bốn khối của phase 1 (`confirm` và `receipt` chỉ cho chuyển hũ) | agent (dựng), frontend (vẽ) |
| `blocks/forecast_timeline.schema.json` | Dự báo 30 ngày của một hũ, dùng chung màn Chi tiết hũ và chat | luồng C (dựng), D (vẽ), agent |
| `blocks/proactive_card.schema.json` | Thẻ chủ động (một việc) trên Tổng quan | luồng A (dựng), D (vẽ) |
| `blocks/{confirm_action,receipt_action}.schema.json` | Xác nhận và biên nhận của MỌI tool ghi khác chuyển hũ | luồng A, agent (dựng), D (vẽ) |
| `blocks/block.schema.json` | Hợp của tám khối, phân biệt theo `type` | kiểm tra |
| `tools/ledger.json` | Mười tool của target `ledger` (chín tool của overview và `save_turn`) đúng định dạng `inlinePayload` của AgentCore Gateway (Lambda target) | luồng A (cài), agent |
| `tools/forecast.json` | Tool `get_forecast` của target `forecast` | luồng C (cài), agent |
| `tools/{ledger,forecast}.results.schema.json` | Kết quả JSON Lambda trả về cho từng tool; `ledger.results` còn chứa các $defs dùng chung với REST (`Transaction`, `Obligation`, `CreditLine`, `Payee`, `SalaryEvent`) | luồng A, C (trả), agent (đọc) |
| `rest/openapi.yaml` | OpenAPI 3.1: 17 endpoint (xem mục "REST") | luồng A, C (cài), D (gọi) |
| `events/*.schema.json` | `detail` của sự kiện trên EventBridge bus `yofina-bus`: `transaction.recorded`, `salary.confirmed`, `obligation.changed`, `profile.updated`, `forecast.updated` | luồng A (phát), C (nghe) |
| `ml/forecast_io.schema.json` | Dạng JSON của đầu vào và đầu ra `yofina_ml.forecast_user` | luồng B, C |
| `fixtures/` | Ví dụ JSON dùng chung cho test Python và TypeScript (`blocks/`, `tools/`, `rest/`, `events/`, `ml/`) | test |

Sinh và kiểm: [scripts/gen_contracts.mjs](../scripts/gen_contracts.mjs). Mã tương ứng: Pydantic ở [libs/yofina_core](../libs/yofina_core/README.md) (`blocks.py`, `wallet.py`, `errors.py`, `clock.py`), Zod ở `frontend/src/contracts/blocks.ts` (file sinh ra, không sửa tay), kiểu ML ở [ml/yofina_ml](../ml/README.md).

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
- **`notice`**: `kind` ∈ `out_of_scope` | `degraded` | `low_data` | `error`; không chứa số liệu tài chính.
- **Thêm một loại khối**: tạo `blocks/<type>.schema.json` (theo mẫu: phong bì + `data`), thêm vào `block.schema.json` và `FILES` trong `scripts/gen_contracts.mjs`, viết model Pydantic và `build_*` trong `blocks.py`, thêm fixture hợp lệ và không hợp lệ, chạy `uv run pytest` và `node scripts/gen_contracts.mjs`.
- **`BLOCK_TYPES` của Zod chỉ gồm khối mà registry frontend đã đăng ký.** `frontend/src/contracts/blocks.ts` xuất `blockSchemas`, `ALL_BLOCK_TYPES` và `Block` cho MỌI khối trong `block.schema.json` (tám khối), nhưng `BLOCK_TYPES` và kiểu `BlockType` chỉ liệt kê bốn khối phase 1 (hằng `REGISTERED_BY_FRONTEND` trong `scripts/gen_contracts.mjs`), vì `registry.tsx` dùng `Record<BlockType, Entry>` phải đủ khóa. Khối chưa đăng ký hiện `fallback_text` (không vỡ trang). **Luồng frontend thêm `forecast_timeline`, `proactive_card`, `confirm_action`, `receipt_action` vào `REGISTERED_BY_FRONTEND` cùng lúc với việc đăng ký view trong `registry.tsx`.**

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
`pattern` dùng `[0-9]` thay `\d` (Python khớp cả chữ số Unicode). `format` (`date`, `date-time`) chỉ là chú thích; `pattern` mới là thứ được kiểm. `$id` dùng miền `contracts.yofina.invalid` (miền dành riêng, không phân giải được) và các `$ref` là đường dẫn tương đối.

## Phase 2: ví mô phỏng và dự báo

Phần này là hợp đồng mà bốn luồng của phase 2 (sổ cái và REST, ML, pipeline và tool forecast, frontend) cùng code theo. Số liệu và thiết kế chi tiết: mục "Quyết định hợp đồng phase 2" cuối [file phase 2](../docs/plan/phases/phase-2-vi-va-du-bao.md).

### Hũ hệ thống và tổng số dư

- Mỗi người dùng có **hai hũ hệ thống** (`jars.kind = 'system'`), tạo bằng hàm DB `app_ensure_system_jars(user_id)` (gọi ở onboarding, đặt lại demo, nạp seed):
  - **Tiền vào khác** (`system_role = other_income`, mã `tien_vao_khac`): mọi tiền vào chưa gán đều nằm đây. Số dư không âm. Nằm trong tổng số dư nhưng **không phải thu nhập** (`get_cashflow_summary` tách `salary_income_vnd` khỏi `other_income_vnd`).
  - **Chưa phân loại** (`system_role = unclassified`, mã `chua_phan_loai`): khoản chi mà hệ thống chưa xếp được hũ. **Số dư được phép ÂM** (tiền đã thật sự ra khỏi ví nhưng chưa trừ vào hũ nào): `assign_jar` chuyển phần chi đó sang hũ được chọn (hũ này giảm, Chưa phân loại tăng về 0). Giao diện ghi "đã chi, chưa xếp hũ" theo giá trị tuyệt đối. Bảng số Figma ghi +180.000 ₫ cho "Chưa phân loại"; hợp đồng này cho số dư có dấu để tổng số dư luôn đúng bằng tiền thật trong ví, nên số engine có thể khác Figma (ghi vào "Kết quả thực hiện" của phase 2).
- **Tổng số dư** = tổng `balance_vnd` của MỌI hũ (kể cả hai hũ hệ thống). `GET /overview` trả `balance.total_vnd = jars_total_vnd + other_income_vnd + unclassified_vnd`. Hũ hệ thống không có tỷ lệ chia lương, không có mục tiêu, không có dự báo.
- **`GET /jars` và tool `get_jar_balances` KHÔNG gồm hũ hệ thống** (giữ nguyên hình dạng phase 1, `JarBalance` không có `kind`). Hũ hệ thống xuất hiện ở `GET /overview` (`system_jars`) và `GET /jars/{jar_code}`.
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
