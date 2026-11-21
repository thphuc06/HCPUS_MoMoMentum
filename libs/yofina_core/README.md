# yofina_core

Gói Python dùng chung cho agent, Lambda tool và pipeline (workspace uv ở gốc repo). Python 3.12 và 3.13 (khớp runtime Lambda và AgentCore Runtime). Phụ thuộc: `pydantic`, `tzdata`; `boto3` là extra `aws` (runtime Lambda đã có sẵn).

| Module | Trạng thái | Nội dung |
|---|---|---|
| `blocks` | cài (bước 0) | Model Pydantic của bốn khối UI khớp `contracts/blocks`; `build_jar_summary`, `build_confirm`, `build_receipt`, `build_notice`; `parse_block`, `block_to_wire`; `trace_id_from_traceparent`, `new_trace_id` |
| `money` | cài | `to_vnd` (chỉ nhận số nguyên: `int`, `Decimal`, `str`; từ chối `float`), `format_vnd` ("1.200.000 ₫"), `format_vnd_short` ("1,2 triệu") |
| `clock` | cài | `app_today(clock_offset_days, now, tz)` và `clock_offset_for(target, now, tz)`: thuần hàm, `now` phải có múi giờ ([ADR-0003](../../docs/decisions/0003-dong-ho-mo-phong.md)) |
| `config` | cài | `Config`: biến môi trường `YOFINA_<TEN>` rồi SSM `<YOFINA_SSM_PREFIX>/<ten>`; thiếu thì `ConfigError`; Region tường minh, không mặc định |
| `errors` | cài | `ErrorCode`, `HTTP_STATUS`, `ToolStatus` (khớp OpenAPI), `YofinaError(code, message)` |
| `confirm` | cài | Chuẩn hóa tham số (`normalize_params`), băm (`params_hash`); cấp và kiểm token HMAC `{sub, tool, h, exp, jti}` (`issue_token`, `decode_token`, `ConfirmService`), `jti` dùng một lần (`DynamoJtiStore`), khóa từ Secrets Manager (`SecretKeyProvider`) ([ADR-0002](../../docs/decisions/0002-xac-nhan-truoc-khi-ghi.md)); 13 ca của spike thành unit test |
| `db` | cài | Client RDS Data API: `DataApi.query` (hàm đọc `app_*`), `DataApi.transaction(user_id)` (Begin → `set_config` → câu lệnh → Commit, rollback trong `finally`), retry `DatabaseResumingException`, `numeric` → `Decimal`, cấu hình từ biến môi trường |
| `llm` | cài (luồng D) | `LlmGateway`: chuỗi dự phòng theo vai (bắt Throttling và AccessDenied), giới hạn tốc độ mỗi model, trần ngày ở DynamoDB `yofina-usage` (`ModelBudgetExceeded`), trần mỗi lượt (`TurnScope`), log token, `structured_json` (ép tool, giới hạn lần thử). Cấu hình mặc định ở `llm_defaults.json`, ghi đè bằng `YOFINA_LLM_*` hoặc SSM `/yofina/llm/*` |
| `pii` | stub (phase 5) | Che PII trước log, bộ nhớ, prompt |

Stub chỉ có docstring nói luồng nào sẽ cài; không có mã giả. Hợp đồng nằm ở [contracts/](../../contracts/README.md).

```
uv sync
uv run pytest libs        # unit test của gói này
```
