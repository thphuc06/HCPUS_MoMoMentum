# yofina_core

Gói Python dùng chung cho agent, Lambda tool và pipeline (workspace uv ở gốc repo). Python 3.12 và 3.13 (khớp runtime Lambda và AgentCore Runtime). Phụ thuộc: `pydantic`, `tzdata`; `boto3` là extra `aws` (runtime Lambda đã có sẵn).

| Module | Trạng thái | Nội dung |
|---|---|---|
| `blocks` | cài (bước 0) | Model Pydantic của bốn khối UI khớp `contracts/blocks`; `build_jar_summary`, `build_confirm`, `build_receipt`, `build_notice`; `parse_block`, `block_to_wire`; `trace_id_from_traceparent`, `new_trace_id` |
| `money` | cài | `to_vnd` (chỉ nhận số nguyên: `int`, `Decimal`, `str`; từ chối `float`), `format_vnd` ("1.200.000 ₫"), `format_vnd_short` ("1,2 triệu") |
| `clock` | cài | `app_today(clock_offset_days, now, tz)` và `clock_offset_for(target, now, tz)`: thuần hàm, `now` phải có múi giờ ([ADR-0003](../../docs/decisions/0003-dong-ho-mo-phong.md)) |
| `config` | cài | `Config`: biến môi trường `YOFINA_<TEN>` rồi SSM `<YOFINA_SSM_PREFIX>/<ten>`; thiếu thì `ConfigError`; Region tường minh, không mặc định |
| `errors` | cài | `ErrorCode`, `HTTP_STATUS`, `ToolStatus` (khớp OpenAPI) |
| `confirm` | một phần | Đã có: chuẩn hóa tham số (`normalize_params`) và băm (`params_hash`). Luồng B thêm cấp và kiểm token ([ADR-0002](../../docs/decisions/0002-xac-nhan-truoc-khi-ghi.md)) |
| `db` | stub (luồng B) | Client Data API: hàm đọc, transaction ghi, retry resume |
| `llm` | stub (luồng D) | Bọc mọi lời gọi Bedrock: giới hạn tốc độ, trần ngày, chuỗi dự phòng |
| `pii` | stub (phase 5) | Che PII trước log, bộ nhớ, prompt |

Stub chỉ có docstring nói luồng nào sẽ cài; không có mã giả. Hợp đồng nằm ở [contracts/](../../contracts/README.md).

```
uv sync
uv run pytest libs        # unit test của gói này
```
