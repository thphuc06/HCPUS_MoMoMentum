# yofina_core

Gói Python dùng chung cho agent, Lambda tool và pipeline (workspace uv ở gốc repo). Python 3.12 và 3.13 (khớp runtime Lambda và AgentCore Runtime). Phụ thuộc: `pydantic`, `tzdata`; `boto3` là extra `aws`. Bản boto3 có sẵn trong runtime Lambda tùy phiên bản runtime và Region, nên Lambda cần API mới thì tự ghim SDK trong zip: Lambda ledger ghim `boto3==1.44.9` (`gateway/tools/ledger/requirements.txt`, build `--keep-boto`, vì `memory` cần `namespacePath` của AgentCore Memory), agent ghim cùng bản trong `agent/pyproject.toml`.

| Module | Trạng thái | Nội dung |
|---|---|---|
| `blocks` | cài (phase 1 tới 5) | Model Pydantic của hai mươi ba khối UI khớp `contracts/blocks` (`parse_block`, `block_to_wire`, `trace_id_from_traceparent`, `new_trace_id`) và hàm dựng `build_*`. Phase 1: `build_jar_summary`, `build_confirm`, `build_receipt`, `build_notice`. Phase 2: `build_forecast_timeline`, `build_proactive_card`, `build_confirm_action`, `build_receipt_action`. Phase 3, 4: khối what-if, kiểm tra trước khi quẹt, chống chịu, cú sốc, lộ trình, hỏi gộp. Phase 5: `behavior_insight_data` rồi `build_behavior_insight`, `citation_data` rồi `build_citation` (khối `ingest_review`, `coverage_change` của F6 dựng ở module `ingest`); `build_proactive_card(nudge_id=...)` cho bản tin của cổng giá trị (id dòng `nudges`, để "Để sau" và "Ít nhắc loại này" gửi `POST /nudges/{nudge_id}/feedback`; thẻ theo luật của Tổng quan không có) |
| `wallet` | cài (phase 2 tới 5) | Hằng số của ví mô phỏng (mã hũ hệ thống, `kind`, `funding_source`, nghĩa vụ, trạng thái, tên tool), khớp enum trong `contracts/` và CHECK trong migration (test chống lệch); `split_amount`; `transaction_jar` (hũ của ví cho một loại giao dịch, dùng chung cho ghi giao dịch, `/tx-types`, nạp dữ liệu, bộ phân loại, nhãn seed: hũ riêng khớp loại, kể cả qua `LEGACY_JAR_ALIASES`, thắng hũ chung Chi hằng ngày, Nghĩa vụ; issue #39). Ý định: `INTENTS` mười bốn giá trị (`INTENTS_PHASE4` cộng `PHASE5_INTENTS`: `behavior`, `knowledge`, `ingest`, `memory`), trùng `AUDIT_INTENTS` (CHECK `audit_events.intent` của 0053); bản tin: `NUDGE_KINDS`, `ALL_NUDGE_KINDS`, `NUDGE_GATE_ORDER`, `NUDGE_OUTCOMES`; `DELETE_MY_DATA` |
| `money` | cài | `to_vnd` (chỉ nhận số nguyên: `int`, `Decimal`, `str`; từ chối `float`), `format_vnd` ("1.200.000 ₫"), `format_vnd_short` ("1,2 triệu") |
| `clock` | cài | `app_today(clock_offset_days, now, tz)` và `clock_offset_for(target, now, tz)`: thuần hàm, `now` phải có múi giờ ([ADR-0003](../../docs/decisions/0003-dong-ho-mo-phong.md)); phase 2 thêm `next_payday`, `latest_payday`, `payday_dates`, `payday_in_month` (ngày lương lớn hơn số ngày của tháng thì lấy ngày cuối tháng) |
| `config` | cài | `Config`: biến môi trường `YOFINA_<TEN>` rồi SSM `<YOFINA_SSM_PREFIX>/<ten>`; thiếu thì `ConfigError`; Region tường minh, không mặc định |
| `errors` | cài | `ErrorCode` (khớp OpenAPI; phase 5 thêm `NUDGE_NOT_FOUND`, `MEMORY_RECORD_NOT_FOUND`, `MEMORY_UNAVAILABLE`...), `HTTP_STATUS`, `ToolStatus`, `YofinaError(code, message)` |
| `params` | cài | Chuẩn hóa `params` của tool ghi (`normalize_params(tool, params, ctx)`, `NormContext`, `TxTypeInfo`; phase 5 thêm `normalize_delete_my_data`), khóa khử trùng (`compute_dedupe_key`), mã hũ từ tên (`unique_jar_code`); tất định và idempotent |
| `schedule` | cài | Lịch nghĩa vụ: `advance_due`, `expand_due_dates`, `first_due_from_day`, `bnpl_due_date`, mốc biểu đồ `build_timeline_events` (dùng chung ledger và pipeline dự báo) |
| `confirm` | cài | Chuẩn hóa tham số (re-export từ `params`), băm (`params_hash`, `hash_normalized_params`); cấp và kiểm token HMAC `{sub, tool, h, exp, jti}` (`issue_token`, `decode_token`, `ConfirmService`), `jti` dùng một lần (`DynamoJtiStore`), khóa từ Secrets Manager (`SecretKeyProvider`) ([ADR-0002](../../docs/decisions/0002-xac-nhan-truoc-khi-ghi.md)) |
| `db` | cài | Client RDS Data API: `DataApi.query` (hàm đọc `app_*`), `DataApi.transaction(user_id)` (Begin → `set_config` → câu lệnh → Commit, rollback trong `finally`), retry `DatabaseResumingException`, `numeric` → `Decimal`. Lỗi SQL khác (kể cả `RAISE EXCEPTION 'PARAMS_INVALID: ...'` của hàm DB) thành `YofinaError(INTERNAL_ERROR)` không lộ chi tiết, chi tiết ở log `data_api_error`: lỗi nghiệp vụ phải được kiểm ở Python TRƯỚC khi gọi hàm |
| `llm` | cài | `LlmGateway`: chuỗi dự phòng theo vai (bắt Throttling và AccessDenied), giới hạn tốc độ mỗi model, trần ngày ở DynamoDB `yofina-usage` (`ModelBudgetExceeded`), trần mỗi lượt (`TurnScope`), log token, `structured_json` (ép tool, giới hạn lần thử), `embed` (Cohere qua `InvokeModel`, gom lô 96). Cấu hình mặc định ở `llm_defaults.json`, ghi đè bằng `YOFINA_LLM_*` hoặc SSM `/yofina/llm/*` |
| `pii` | cài (phase 5) | Che PII trước log, bộ nhớ, prompt (`mask_pii`, `mask_names`, `fold`, `PiiPolicy`) |
| `scenario`, `suitability` | cài (phase 3) | `ScenarioSpec` của what-if; đề xuất, kết luận và định dạng file luật suitability |
| `resilience`, `roadmap` | cài (phase 4) | Kiểu và cấu hình của điểm chống chịu, cú sốc (`shocks.json`, `resilience_defaults.json`); lộ trình, bước, bộ tối ưu phân bổ |
| `ingest` | cài (phase 5, F6) | Hằng số, cấu hình, khóa khử trùng dòng nạp, độ phủ dữ liệu, kết quả ba tool `ingest___*`, `build_ingest_review`, `build_coverage_change` |
| `memory` | cài (phase 5) | Namespace AgentCore Memory theo người dùng (`/yofina/users/{actorId}/...`, `namespace_for`, `user_root`, `kind_of_namespace` trả None cho namespace không thuộc người gọi), loại bản ghi, kiểu REST `/memory*` |
| `privacy` | cài (phase 5) | Kiểu của "Xóa dữ liệu của tôi" (`DataDeletion`, `DATA_DELETION_STEPS`: s3, memory, aurora) và nhật ký `data_deletions` (migration 0053) |

Hợp đồng nằm ở [contracts/](../../contracts/README.md). Kiểm trên PostgreSQL thật (SQL của các migration qua `db`): [tests/local_pg/](../../tests/local_pg/conftest.py).

```
uv sync
uv run pytest libs        # unit test của gói này
```
