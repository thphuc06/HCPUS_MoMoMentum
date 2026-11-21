# contracts/

Nguồn duy nhất cho **hợp đồng** giữa frontend, agent, Lambda tool và REST. Mọi bên đọc từ đây; muốn đổi hợp đồng thì sửa ở đây trước, rồi sinh lại và chạy test. Kế hoạch: [phase 1 mục "Bước 0"](../docs/plan/phases/phase-1-nen-va-lat-doc.md); quyết định liên quan: [ADR-0002](../docs/decisions/0002-xac-nhan-truoc-khi-ghi.md) (xác nhận trước khi ghi), [ADR-0003](../docs/decisions/0003-dong-ho-mo-phong.md) (đồng hồ mô phỏng).

| Thư mục / file | Nội dung | Ai dùng |
|---|---|---|
| `blocks/envelope.schema.json` | Phong bì chung của khối UI và các kiểu cơ bản (`Vnd`, `JarCode`, `IsoDate`...) | tất cả |
| `blocks/{jar_summary,confirm,receipt,notice}.schema.json` | Bốn khối của phase 1 | agent (dựng), frontend (vẽ) |
| `blocks/block.schema.json` | Hợp của các khối đã biết, phân biệt theo `type` | kiểm tra |
| `tools/ledger.json` | Ba tool `get_jar_balances`, `query_transactions`, `move_between_jars` đúng định dạng `inlinePayload` của AgentCore Gateway (Lambda target) | luồng C (tạo target), D (agent) |
| `tools/ledger.results.schema.json` | Kết quả JSON Lambda `ledger` trả về cho từng tool | luồng B (trả), D (đọc) |
| `rest/openapi.yaml` | OpenAPI 3.1: `GET /jars`, `POST /confirmations`, `POST /actions`, `POST /demo/reset` | luồng B (cài), E (gọi) |
| `fixtures/` | Ví dụ JSON dùng chung cho test Python và TypeScript | test |

Sinh và kiểm: [scripts/gen_contracts.mjs](../scripts/gen_contracts.mjs). Mã tương ứng: Pydantic ở [libs/yofina_core](../libs/yofina_core/README.md) (`blocks.py`), Zod ở `frontend/src/contracts/blocks.ts` (file sinh ra, không sửa tay).

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

### Tool `ledger` (AgentCore Gateway)

- Target tên `ledger`; tên đầy đủ qua Gateway là `ledger___<tool>`. Giữ ngắn vì Bedrock Converse giới hạn 64 ký tự.
- `tools/ledger.json` là mảng `ToolDefinition` đúng như truyền vào `toolSchema.inlinePayload`: `{"name", "description", "inputSchema"}`. Gateway chỉ nhận ở mỗi thuộc tính các khóa `type`, `description`, `items`, `properties`, `required`; **không có `enum`, `minimum`, `pattern`** (test kiểm). Mọi ràng buộc nghiệp vụ nằm ở Lambda và Cedar; mô tả cho LLM nói rõ ràng buộc.
- `user_id` là tham số tùy chọn, mô tả "hệ thống tự điền, để trống". Interceptor luôn ghi đè từ JWT; Cedar viết `context.input has user_id && context.input.user_id == principal.id` (spike Gateway §8). Tham số thừa không bị Gateway từ chối nên Lambda bỏ qua tham số lạ.
- `move_between_jars` không có `confirm_token` thì **không ghi**, trả `NEEDS_CONFIRMATION`. Token chỉ do `POST /confirmations` cấp sau khi người dùng bấm; LLM không bao giờ tạo hay điền token.
- **Kết quả tool** (`tools/ledger.results.schema.json`): `{"status": "OK" | "NEEDS_CONFIRMATION" | "ERROR", ...}`.
  - `OK` và `NEEDS_CONFIRMATION` mang `as_of`, `app_date` và `data`. `data` dùng lại **đúng** `data` của khối tương ứng: `JarSummaryData` (get_jar_balances), `ConfirmData` (NEEDS_CONFIRMATION), `ReceiptData` (move OK), nên agent chỉ việc bọc bằng `build_*`. `query_transactions` trả `{transactions, has_more}`.
  - `ERROR` mang `code` (thuộc `ErrorCode`) và `message` tiếng Việt. Lỗi nghiệp vụ là kết quả thành công của Lambda; agent đọc `status`.
  - Với tool ghi, Lambda dựng `data` từ số dư thật trong cùng transaction; `build_confirm`/`build_receipt` chạy ở agent (đường chat) hoặc ở Lambda (đường REST).

### REST

- JWT Bearer của Cognito (access token). Không endpoint nào nhận `user_id`.
- Lỗi: `{"error": {"code", "message", "trace_id"?}}`, `code` thuộc `ErrorCode`; ánh xạ HTTP status ở `x-http-status` trong `components.schemas.ErrorCode` và ở `yofina_core.errors.HTTP_STATUS` (test kiểm hai nơi khớp nhau). Mã token: `NEEDS_CONFIRMATION` (428), `TOKEN_INVALID` và `TOKEN_EXPIRED` (403), `TOKEN_REUSED` và `PARAMS_MISMATCH` (409). JWT authorizer của HTTP API có thể trả 401 thân rỗng trước khi tới Lambda.
- `POST /actions` không có `confirm_token` thì trả 428 (token là trường tùy chọn của yêu cầu để mã lỗi do code của chúng ta quyết định, không phải do kiểm schema).

### Tập con JSON Schema được dùng

Schema chỉ dùng: `$schema`, `$id`, `$ref`, `$defs`, `type` (`object`, `string`, `integer`, `number`, `boolean`, `array`), `const`, `enum`, `properties`, `required`, `additionalProperties`, `items`, `minItems`, `maxItems`, `minLength`, `maxLength`, `pattern`, `minimum`, `maximum`, `oneOf` (chỉ gồm `$ref`, phân biệt theo `type`), và chú thích `title`, `description`, `$comment`, `examples`, `format`. Bộ sinh Zod **báo lỗi** nếu gặp từ khóa khác.
`pattern` dùng `[0-9]` thay `\d` (Python khớp cả chữ số Unicode). `format` (`date`, `date-time`) chỉ là chú thích; `pattern` mới là thứ được kiểm. `$id` dùng miền `contracts.yofina.invalid` (miền dành riêng, không phân giải được) và các `$ref` là đường dẫn tương đối.

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
```

`npm` ở gốc repo chỉ phục vụ công cụ hợp đồng (`package.json` có một devDependency là `zod`); không phải project frontend, `frontend/` sẽ có `package.json` riêng khi luồng E dựng.
