# gateway/tools/ledger/

Lambda `yofina-ledger` (Python 3.13, arm64, ngoài VPC): ví mô phỏng trên Aurora qua Data API. **Một mã, hai đường vào**; mã nghiệp vụ không biết đường nào gọi mình. Proposal §9; FR1, FR3 (phần đọc), FR4, FR12. Quyết định: [ADR-0002](../../../docs/decisions/0002-xac-nhan-truoc-khi-ghi.md) (xác nhận bằng token một lần), [ADR-0003](../../../docs/decisions/0003-dong-ho-mo-phong.md) (đồng hồ mô phỏng); thiết kế hợp đồng phase 2: [contracts/README.md](../../../contracts/README.md#phase-2-ví-mô-phỏng-và-dự-báo).

| Đường vào | Danh tính (`user_id`) lấy từ | Dùng bởi |
|---|---|---|
| **HTTP API** (payload v2, `yofina-api`) | claim `sub` của JWT authorizer, **không bao giờ** từ thân yêu cầu hay query | frontend: 18 route của [openapi.yaml](../../../contracts/rest/openapi.yaml) (mục "Route") |
| **AgentCore Gateway** (Lambda target) | trường `user_id` của sự kiện, do interceptor ghi đè bằng `sub` của JWT; tên tool ở `context.client_context.custom["bedrockAgentCoreToolName"]`, cắt tiền tố `ledger___`; tham số lạ bị bỏ qua | agent: mười tool của [ledger.json](../../../contracts/tools/ledger.json) (năm đọc, bốn ghi, `save_turn`), kết quả theo [ledger.results.schema.json](../../../contracts/tools/ledger.results.schema.json) |

## Cấu trúc

```
handler.py                 điểm vào: nhận diện HTTP (requestContext.http) hay Gateway, dựng dịch vụ một lần
yofina_ledger/
  settings.py              cấu hình từ biến môi trường YOFINA_* (CDK đặt); thiếu thì báo lỗi, không mặc định theo môi trường
  service.py               LedgerService: token (cấp, kiểm, tiêu), chuyển hũ, hội thoại, đặt lại demo; ghép hai mixin dưới
  wallet_reads.py          mixin ĐỌC: Tổng quan, chi tiết hũ, giao dịch (con trỏ), nghĩa vụ, hạn mức, lương, dòng tiền, chưa phân loại, dự báo
  wallet_writes.py         mixin GHI: chuẩn hóa, kiểm nghiệp vụ, xem trước (confirm_action), biên nhận (receipt_action), sự kiện
  repo.py                  SQL phase 1 (số dư, chuyển hũ, hội thoại, đề nghị đã xử lý, audit) và đặt lại demo
  repo_wallet.py           SQL ví: hàm đọc gộp, bảng tra, và các thao tác ghi (mỗi thao tác MỘT transaction)
  refdata.py               bảng tra dùng chung (loại giao dịch, biểu phí, hũ mẫu) đọc từ Aurora, giữ trong bộ nhớ vài phút
  proactive.py             chọn thẻ chủ động bằng luật tất định (không LLM)
  convert.py               dòng DB (Python hoặc jsonb) -> JSON của hợp đồng
  events.py                dựng và phát sự kiện lên EventBridge sau commit (lỗi không làm hỏng việc ghi)
  rest_api.py              định tuyến HTTP, lỗi {"error": {code, message, trace_id}}, status theo HTTP_STATUS
  gateway_api.py           định tuyến tool, kết quả {"status": OK | NEEDS_CONFIRMATION | ERROR, ...}
```

Dùng chung `yofina_core`: `db` (Data API), `confirm` (token), `params` (chuẩn hóa tham số), `schedule` (chu kỳ nghĩa vụ, mốc biểu đồ), `blocks` (dựng khối), `clock` (`app_today`), `wallet` (hằng số, `split_amount`), `errors`. Dữ liệu persona (`data/personas`) được đóng kèm vào zip.

## Route (HTTP API) và tool (Gateway)

| REST | Việc | Tool Gateway |
|---|---|---|
| `GET /overview` | Tổng quan: **một lệnh gọi** hàm `app_get_overview` (hồ sơ, mọi hũ, tóm tắt dự báo, hạn mức, nghĩa vụ sắp đến hạn, lương chờ, 5 giao dịch gần nhất, số cần xem lại); tổng số dư = mọi hũ kể cả hai hũ hệ thống; kỳ lương kế; thẻ chủ động | |
| `GET /profile`, `GET /jars`, `GET /jars/{jar_code}`, `GET /transactions`, `GET /obligations`, `GET /credit-line`, `GET /salary-events`, `GET /payees`, `GET /tx-types`, `GET /jar-templates` | Đọc cho màn hình. `GET /jars` không gồm hũ hệ thống; `GET /transactions` lọc theo hũ, loại, khoảng ngày, cần xem lại và phân trang bằng con trỏ mờ (LIMIT cứng ở SQL) | `get_jar_balances`, `query_transactions` (kind, tx_type, cursor), `get_cashflow_summary`, `get_obligations`, `get_unclassified` |
| `GET /forecasts/{jar_code}` | Khối `forecast_timeline`: CHỈ đọc `forecasts`, `forecast_runs`, `forecast_jar_summaries` qua hàm `app_*`, ghép mốc nghĩa vụ và lương lúc đọc; chưa có lần chạy nào thì 503 `FORECAST_UNAVAILABLE`. Việc tính dự báo là của pipeline (luồng C) | |
| `POST /confirmations` rồi `POST /actions` | Mọi thao tác ghi, sáu `tool`: `move_between_jars`, `record_transaction`, `assign_jar`, `update_profile`, `save_jars`, `confirm_salary` | bốn tool ghi đầu (không token thì `NEEDS_CONFIRMATION`); `save_jars` và `confirm_salary` chỉ có ở REST |
| `POST /confirmations/cancel` | Ghi việc người dùng bấm "Không" (`cancelled`) | |
| `GET /conversations`, `GET /conversations/{id}`, `POST /demo/reset` | Hội thoại đã lưu (kèm `resolutions`), đặt lại demo | `save_turn` |

## Luồng ghi (mọi tool)

1. `normalize_params(tool, params, ctx)` ([yofina_core/params.py](../../../libs/yofina_core/src/yofina_core/params.py)): bản chuẩn hóa tất định và idempotent; điền mặc định phụ thuộc trạng thái (hũ từ `tx_type_map`, hũ trả của nghĩa vụ, `due_date` từ `due_day`, mã hũ mới) bằng `NormContext` dựng từ DB và bảng tra. Thứ ký là thứ hiển thị.
2. Kiểm nghiệp vụ và dựng khối `confirm_action` (hoặc `confirm` cho chuyển hũ): hũ tồn tại, đủ số dư, hạn mức giao dịch, hạn mức Trả sau, người nhận và nghĩa vụ thuộc người gọi, lương và đề nghị chưa xử lý...
3. `POST /confirmations` kiểm lại rồi ký token HMAC (hạn 2 phút, `jti`) và trả kèm `preview` (`summary`, `changes`, `warnings`) do server tính, không ghi gì: số dư hũ trước và sau, với Trả sau thì khoản phải trả ngày đến hạn gồm phí từ `fee_schedules` và hạn mức còn lại. Màn "Xem lại" chỉ hiển thị, không tự tính.
4. `POST /actions` (hoặc tool có `confirm_token`): kiểm chữ ký, hạn, người, tool, hash; kiểm đề nghị (đã thực hiện, đã hủy, hết hạn); kiểm nghiệp vụ; **rồi mới** tiêu `jti` (nghiệp vụ sai không làm mất token); một transaction Data API khóa dòng liên quan (`FOR UPDATE`) rồi một câu CTE ghi sổ cái, số dư, nghĩa vụ, audit và (có `conversation_id` + `confirm_block_id`) biên nhận vào `confirm_resolutions`; **sau commit** phát sự kiện.

| Tool | Việc ghi |
|---|---|
| `record_transaction` chi bằng hũ | Dòng chi `funding_source jar` + trừ số dư (hũ Chưa phân loại được âm; hũ khác không). Không chọn hũ thì bước 0 `tx_type_map`, không khớp thì Chưa phân loại (`needs_review`). Người nhận (`payee_id`) cập nhật `last_used_at`, tên người nhận thành đối tác của dòng |
| `record_transaction` chi bằng Trả sau (`funding credit`) | Dòng chi `funding_source credit` (KHÔNG đổi số dư hũ) + nghĩa vụ `bnpl` sinh hoặc cộng dồn (ON CONFLICT trên chỉ mục duy nhất một phần theo ngày đến hạn) + dư nợ gốc tăng. Ngày đến hạn là `credit_lines.due_day` kế tiếp sau ngày mua; phí lấy từ `fee_schedules` (`ReferenceData.bnpl_monthly_fee`), tính MỘT lần cho mỗi nghĩa vụ; hạn mức kiểm trên dòng `credit_lines` đã khóa nên hai lần mua song song không vượt hạn mức |
| `record_transaction` trả nghĩa vụ (`obligation_id`) | Dòng chi gắn `obligation_id` từ một hũ; nghĩa vụ một lần thành `paid`, nghĩa vụ lặp dời `due_date` theo chu kỳ; trả sau giảm dư nợ gốc |
| `record_transaction` tiền vào | Vào hũ Tiền vào khác (không phải thu nhập). `tx_type salary` thêm `salary_events` `pending` kèm `deviation_percent` và cờ hỏi cập nhật lương theo ngưỡng cấu hình |
| `confirm_salary` | `split`: chia số nhận vào hũ bằng `split_amount` (dòng chuyển `salary_split`, cùng `transfer_id`); `keep_as_other`: giữ ở Tiền vào khác. `update_declared_salary` đặt lương đã khai bằng số nhận. Xử lý lần hai: 409 `ALREADY_APPLIED` |
| `assign_jar` | Dòng sổ cái chuyển sang hũ mới (UPDATE cột phân loại), số dư hai hũ đổi tương ứng; `remember` ghi `category_rules` (`once` hoặc `always`, theo người nhận hoặc đối tác) |
| `update_profile` | Lương, ngày nhận, mức rủi ro, tên, và MỘT nghĩa vụ mỗi lần (thêm, sửa, hủy; trả sau không khai, không sửa). Onboarding (chưa có hồ sơ): cần cả lương và ngày nhận, server tạo hồ sơ, hai hũ hệ thống, hũ `is_default` của `jar_templates` và hạn mức mặc định |
| `save_jars` | Thay cả danh sách hũ người dùng (tổng tỷ lệ bằng 100); hũ bị bỏ chỉ khi số dư 0, không nghĩa vụ trả bằng nó và chưa có dòng sổ cái nào (khóa ngoại), nếu không `JAR_PROTECTED` |
| `move_between_jars` | Như phase 1; hũ nguồn có thể là Tiền vào khác (cách gán tiền vào hũ) |

Mã lỗi: `NEEDS_CONFIRMATION` (428), `TOKEN_INVALID` / `TOKEN_EXPIRED` (403), `TOKEN_REUSED` / `PARAMS_MISMATCH` / `ALREADY_APPLIED` / `DUPLICATE_TRANSACTION` (409), `INSUFFICIENT_FUNDS` / `AMOUNT_LIMIT_EXCEEDED` / `CREDIT_LIMIT_EXCEEDED` / `JAR_PROTECTED` / `PROFILE_INCOMPLETE` (422), `JAR_NOT_FOUND` / `TRANSACTION_NOT_FOUND` / `OBLIGATION_NOT_FOUND` / `PAYEE_NOT_FOUND` / `SALARY_EVENT_NOT_FOUND` (404), `PARAMS_INVALID` (400), `FORECAST_UNAVAILABLE` / `DATABASE_UNAVAILABLE` (503; Aurora đang thức dậy, đã retry trong Lambda).

## Một đề nghị chỉ được thực hiện một lần, hủy được, và có hạn (migration 0004 và 0007)

`POST /confirmations` và `POST /actions` nhận thêm hai trường tùy chọn đi cùng nhau, `conversation_id` và `confirm_block_id` (id của khối `confirm` hoặc `confirm_action`, dạng `confirm:{trace_id}:{params_hash[:12]}`; `parse_confirm_ref` kiểm định dạng và 12 ký tự cuối phải khớp hash của tham số đang thực hiện, nếu không `PARAMS_MISMATCH`). Có hai trường này:

1. **Đã thực hiện hoặc đã hủy**: `repo.resolution` có dòng thì từ chối 409 `ALREADY_APPLIED` (thông điệp nói "đã thực hiện" hoặc "đã bị hủy"), trước khi tiêu `jti` và trước kiểm số dư; ghi một dòng `audit_events` `rejected`.
2. **Hết hạn** (server ép, không chỉ giao diện): `repo.confirm_block` đọc khối đã lưu (`turn_blocks`, do `save_turn` ghi) và so `data.expires_at` với giờ hiện tại; quá hạn thì 403 `TOKEN_EXPIRED` ("đề nghị đã hết hạn, hãy hỏi lại"). Khối chưa lưu được (lỗi lưu lượt) thì không có hạn để ép; token 2 phút dùng một lần vẫn là lớp bảo vệ. Chỉ khi có `confirm_block_id`: gọi REST trực tiếp và đường Gateway của agent không có kiểm tra này.
3. Cùng transaction ghi sổ cái chèn một dòng `confirm_resolutions` (khóa unique `(user_id, confirm_block_id)`, kèm biên nhận đã dựng): trùng khóa thì ném `ALREADY_APPLIED` và **cả transaction rollback**. Đây là lưới chắc chắn khi hai yêu cầu chạy song song (đã thử thật, kể cả hai lần xác nhận lương song song và hai lần mua Trả sau song song).
4. **Bấm "Không"**: `POST /confirmations/cancel` ghi dòng `status = 'cancelled'` (không biên nhận, không sổ cái). `GET /conversations/{id}` trả `resolutions` có `cancelled` (kèm `resolved_at`), `done` (kèm `receipt`), `expired`, `pending`; đã xử lý luôn thắng hết hạn. Hủy lại thì trả đúng kết quả cũ; đề nghị đã thực hiện thì không hủy được; đề nghị không thuộc người gọi: 400 (không lộ sự tồn tại).

Khóa theo `(user_id, confirm_block_id)` nên id của người khác chỉ tạo dòng của chính người gọi (RLS), không đánh dấu hay chặn đề nghị của ai. Đặt lại demo xóa `confirm_resolutions`.

## Sự kiện (EventBridge bus `yofina-bus`)

Sau MỖI lần ghi commit: `transaction.recorded` (chi, tiền vào, chuyển hũ, chia lương, gán hũ, trả nghĩa vụ; `event_id` = id dòng sổ cái hoặc `transfer_id`; gán hũ dùng `event_id` mới vì cùng giao dịch đã có sự kiện lúc ghi), `salary.confirmed` (cùng `transaction.recorded` của lần chia), `obligation.changed` (khai, sửa, hủy, trả, trả sau mới sinh hoặc cộng dồn), `profile.updated` (onboarding, lương, ngày nhận, hũ, mức rủi ro, tên, và đặt lại demo). Chi tiết đúng [contracts/events/](../../../contracts/events/); test kiểm từng sự kiện bằng JSON Schema. Không PII: chỉ id, mã hũ, số tiền. Lỗi phát (kể cả thất bại một phần) **không** làm hỏng việc ghi: log JSON + metric EMF `EventPublishFailed` (namespace `Yofina/Ledger`, có alarm `yofina-ledger-event-publish-failed` gửi SNS `yofina-alerts`), và một dòng `audit_events` mã `EVENT_PUBLISH_FAILED` để nightly bù. Chưa có consumer (đợt sau: `yofina-on-transaction`).

## Hiệu năng (đo thật, 2026-11-22, `uv run scripts/measure_wallet.py`)

Phía Lambda (log `rest_request`, ms trong handler, tài khoản `minh`, Lambda 512 MB đã ấm): `GET /overview` n=54 p50 15 ms, p95 16 ms, max 95 ms (một lệnh gọi Data API) so với mục tiêu p95 < 300 ms; `POST /confirmations` p50 14, p95 18 ms; `POST /actions` (chi 1.000 ₫: khóa hũ, ghi CTE, tiêu `jti` ở DynamoDB, phát sự kiện) p50 213, p95 236 ms. Phía máy gọi qua Internet: `GET /overview` p50 133, p95 215 ms; luồng ghi hai bước p50 475, p95 500 ms.

## Cấu hình (biến môi trường, do `infra-cdk/lib/tools-stack.ts` đặt)

`YOFINA_REGION`, `YOFINA_DB_CLUSTER_ARN`, `YOFINA_DB_APP_SECRET_ARN` (secret của role `yofina_app`, **không** phải master), `YOFINA_DB_NAME`, `YOFINA_DB_RESUME_MAX_WAIT_SECONDS`, `YOFINA_CONFIRM_JTI_TABLE`, `YOFINA_CONFIRM_HMAC_SECRET_ARN`, `YOFINA_CONFIRM_TOKEN_TTL_SECONDS`, `YOFINA_CONFIRM_TOKEN_MAX_TTL_SECONDS`, `YOFINA_CONFIRM_OFFER_TTL_SECONDS`, `YOFINA_MOVE_MAX_AMOUNT_VND`, `YOFINA_TRANSACTION_MAX_AMOUNT_VND`, `YOFINA_TRANSACTIONS_DEFAULT_LIMIT`, `YOFINA_TRANSACTIONS_MAX_LIMIT`, `YOFINA_SALARY_DEVIATION_ASK_PERCENT`, `YOFINA_DEFAULT_CREDIT_LIMIT_VND`, `YOFINA_DEFAULT_DISPLAY_NAME`, `YOFINA_FORECAST_FRESHNESS_SECONDS`, `YOFINA_PROACTIVE_OBLIGATION_DAYS`, `YOFINA_REFERENCE_CACHE_SECONDS`, `YOFINA_EVENT_BUS_NAME`, `YOFINA_APP_TIMEZONE`, `YOFINA_DEMO_ANCHOR_DATE`, `YOFINA_LOG_LEVEL`. Giá trị mặc định ở `ToolsConfig` của stack, đổi bằng context (`-c transactionMaxAmountVnd=...`). Biểu phí và loại giao dịch không ở đây mà ở bảng DB (`fee_schedules`, `tx_type_map`).

## Đóng gói, deploy, kiểm

```bash
uv run scripts/build_lambda.py gateway/tools/ledger --arch arm64 --extra data/personas:personas
uv run scripts/migrate.py                                              # 0007_wallet_ops (và --seed khi đổi bảng tra)
uv run scripts/cdk.py deploy YofinaTools --require-approval never      # cần zip ở build/lambda/ledger-arm64.zip
uv run scripts/cdk.py deploy YofinaAgent --require-approval never      # target 10 tool + Cedar mỗi tool (khi đổi contracts/tools/ledger.json)
uv run scripts/seed_demo.py                                            # nạp persona cho 6 tài khoản demo
uv run pytest libs tests/unit                                          # unit (kho giả, hàm thuần, hợp đồng, sự kiện theo JSON Schema)
uv run --python 3.12 --no-project --with pgserver --with "psycopg[binary]" --with pydantic --with pytest --with jsonschema --with pyyaml --with referencing --with numpy --with boto3 pytest tests/local_pg -p no:cacheprovider
uv run pytest tests/integration -m integration                         # thật: REST, Gateway, RLS, sự kiện, onboarding (tạo rồi dọn tài khoản thử)
uv run scripts/measure_wallet.py                                       # p50/p95 GET /overview và luồng ghi (cả phía Lambda)
```

`tests/local_pg/` chạy NGUYÊN `DataApi` và `LedgerRepo` trên PostgreSQL thật cục bộ (pgserver, role `yofina_app` không phải owner nên RLS và quyền được kiểm thật; bản giả của client `rds-data` ở `local_data_api.py`): nhanh hơn deploy để bắt lỗi SQL, và là nơi thử đua song song bằng nhiều luồng.

Giới hạn đã biết: `query_transactions` đọc tối đa 50 dòng mỗi lần (giới hạn 1 MiB của Data API); tin vào `user_id` của sự kiện Gateway nghĩa là interceptor bắt buộc phải ghi đè nó (Lambda không thấy JWT); hũ có lịch sử giao dịch không xóa được qua `save_jars` (khóa ngoại của sổ cái; chỉ hũ mới tạo chưa dùng mới bỏ được); phí Trả sau chỉ hỗ trợ dạng số tiền cố định (`amount_vnd`), chưa có dạng phần trăm vì chưa có nguồn.
