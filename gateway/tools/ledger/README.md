# gateway/tools/ledger/

Lambda `yofina-ledger` (Python 3.13, arm64, ngoài VPC): sổ cái và số dư hũ trên Aurora qua Data API. **Một mã, hai đường vào**; mã nghiệp vụ không biết đường nào gọi mình. Proposal §9; FR1, FR12. Quyết định: [ADR-0002](../../../docs/decisions/0002-xac-nhan-truoc-khi-ghi.md) (xác nhận bằng token một lần), [ADR-0003](../../../docs/decisions/0003-dong-ho-mo-phong.md) (đồng hồ mô phỏng).

| Đường vào | Danh tính (`user_id`) lấy từ | Dùng bởi |
|---|---|---|
| **HTTP API** (payload v2, `yofina-api`) | claim `sub` của JWT authorizer, **không bao giờ** từ thân yêu cầu hay query | frontend: `GET /jars`, `POST /confirmations`, `POST /actions`, `POST /demo/reset`, `GET /conversations`, `GET /conversations/{conversation_id}` ([openapi.yaml](../../../contracts/rest/openapi.yaml)) |
| **AgentCore Gateway** (Lambda target) | trường `user_id` của sự kiện, do interceptor ghi đè bằng `sub` của JWT (luồng C); tên tool ở `context.client_context.custom["bedrockAgentCoreToolName"]`, cắt tiền tố `ledger___`; tham số lạ bị bỏ qua | agent: `get_jar_balances`, `query_transactions`, `move_between_jars`, `save_turn` ([ledger.json](../../../contracts/tools/ledger.json), kết quả theo [ledger.results.schema.json](../../../contracts/tools/ledger.results.schema.json)) |

## Cấu trúc

```
handler.py                 điểm vào: nhận diện HTTP (requestContext.http) hay Gateway, dựng dịch vụ một lần
yofina_ledger/
  settings.py              cấu hình từ biến môi trường YOFINA_* (CDK đặt); thiếu thì báo lỗi, không mặc định
  service.py               nghiệp vụ (không biết Lambda/HTTP): đọc số dư, đề nghị, cấp token, ghi, đặt lại
  repo.py                  toàn bộ SQL (đọc qua hàm app_*, ghi trong transaction), qua yofina_core.db
  rest_api.py              định tuyến HTTP, lỗi {"error": {code, message, trace_id}}, status theo HTTP_STATUS
  gateway_api.py           định tuyến tool, kết quả {"status": OK | NEEDS_CONFIRMATION | ERROR, ...}
```

Dùng chung `yofina_core`: `db` (Data API), `confirm` (token), `blocks` (dựng khối `jar_summary`, `confirm`, `receipt`), `clock` (`app_today`), `errors`. Dữ liệu persona (`data/personas`) được đóng kèm vào zip.

## Lưu và đọc lại lượt hội thoại

Tool `save_turn` (agent gọi sau khi phát xong nội dung, trước `RUN_FINISHED`) ghi một lượt vào `conversation_turns` (câu hỏi, câu trả lời, tối đa 4000 và 8000 ký tự) và `turn_blocks` (tối đa 20 khối, mỗi khối tối đa 64 KB) trong MỘT transaction, ghi đè nếu cùng `(conversation_id, trace_id)` nên gọi lại an toàn. Từ chối khối có khóa nhạy cảm (`confirm_token`, `token`, `authorization`...) hoặc chuỗi giống JWT; văn bản lượt bị che chuỗi giống JWT/token xác nhận. REST `GET /conversations/{conversation_id}` và `GET /conversations` đọc lại qua các hàm `app_get_conversation_turns`, `app_get_conversation_blocks`, `app_list_conversations` (RLS: hội thoại của người khác ra rỗng). Đặt lại demo (`POST /demo/reset`) xóa cả hai bảng. Migration: [0003_conversation_turns.sql](../../../db/migrations/0003_conversation_turns.sql); hợp đồng và cách frontend dùng: [contracts/README.md](../../../contracts/README.md).

## Luồng chuyển hũ

1. Tool `move_between_jars` **không có `confirm_token`** → không ghi gì; kiểm nghiệp vụ (hũ tồn tại, đủ số dư, hạn mức), trả `NEEDS_CONFIRMATION` với `data` của khối `confirm` (tham số đã chuẩn hóa, `params_hash`, xem trước hai hũ, hạn của đề nghị).
2. Người dùng bấm xác nhận → frontend `POST /confirmations` → server kiểm lại, ký token HMAC-SHA256 `{sub, tool, h, exp, jti}` (hạn 2 phút, khóa ở Secrets Manager).
3. `POST /actions` (hoặc tool có `confirm_token`) → kiểm chữ ký, hạn, người, tool, hash tham số, rồi **mới** tiêu `jti` (`PutItem` có điều kiện vào `yofina-confirm-jti`) → một transaction Data API: khóa hai hũ (`FOR UPDATE`), một câu lệnh CTE cập nhật hai số dư + hai dòng sổ cái cùng `transfer_id` + một dòng `audit_events`. Trả khối `receipt`.
4. Tham số sai (hash lệch) **không** làm mất token; token sai, hết hạn hoặc đã dùng thì từ chối và ghi một dòng `audit_events` kết quả `rejected`.

Mã lỗi: `NEEDS_CONFIRMATION` (428), `TOKEN_INVALID` / `TOKEN_EXPIRED` (403), `TOKEN_REUSED` / `PARAMS_MISMATCH` (409), `INSUFFICIENT_FUNDS` / `AMOUNT_LIMIT_EXCEEDED` (422), `JAR_NOT_FOUND` (404), `PARAMS_INVALID` (400), `DATABASE_UNAVAILABLE` (503; Aurora đang thức dậy, đã retry trong Lambda).

## Cấu hình (biến môi trường, do `infra-cdk/lib/tools-stack.ts` đặt)

`YOFINA_REGION`, `YOFINA_DB_CLUSTER_ARN`, `YOFINA_DB_APP_SECRET_ARN` (secret của role `yofina_app`, **không** phải master), `YOFINA_DB_NAME`, `YOFINA_DB_RESUME_MAX_WAIT_SECONDS`, `YOFINA_CONFIRM_JTI_TABLE`, `YOFINA_CONFIRM_HMAC_SECRET_ARN`, `YOFINA_CONFIRM_TOKEN_TTL_SECONDS`, `YOFINA_CONFIRM_TOKEN_MAX_TTL_SECONDS`, `YOFINA_CONFIRM_OFFER_TTL_SECONDS`, `YOFINA_MOVE_MAX_AMOUNT_VND`, `YOFINA_TRANSACTIONS_DEFAULT_LIMIT`, `YOFINA_TRANSACTIONS_MAX_LIMIT`, `YOFINA_APP_TIMEZONE`, `YOFINA_DEMO_ANCHOR_DATE`, `YOFINA_LOG_LEVEL`. Giá trị mặc định ở `ToolsConfig` của stack, đổi bằng context (`-c moveMaxAmountVnd=...`).

## Đóng gói, deploy, kiểm

```bash
uv run scripts/build_lambda.py gateway/tools/ledger --arch arm64 --extra data/personas:personas
uv run scripts/cdk.py deploy YofinaTools --require-approval never      # cần zip ở build/lambda/ledger-arm64.zip
uv run scripts/seed_demo.py                                            # nạp persona cho 6 tài khoản demo
uv run pytest libs tests/unit/test_ledger_service.py tests/unit/test_ledger_rest.py   # unit (kho giả)
uv run pytest tests/integration -m integration                         # thật: REST, Gateway-event, RLS, đua jti
uv run scripts/measure_latency.py                                      # p50/p95 GET /jars và luồng chuyển hũ
```

Giới hạn đã biết: tool ghi chỉ có `move_between_jars` (phase 2 thêm `record_transaction`...); `query_transactions` đọc tối đa 50 dòng mỗi lần (giới hạn 1 MiB của Data API); tin vào `user_id` của sự kiện Gateway nghĩa là interceptor (luồng C) bắt buộc phải ghi đè nó — Lambda không thấy JWT.
