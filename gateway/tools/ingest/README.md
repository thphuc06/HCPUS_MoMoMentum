# gateway/tools/ingest/

Tool `ingest___*` (target `ingest`): `start_job`, `get_job_status`, `confirm_rows` (job bất đồng bộ, S3 + SQS; ảnh chụp và CSV ở MVP; PDF là mở rộng, đọc bằng model, không dùng Bedrock Data Automation vì không liệt kê tiếng Việt). Proposal §9, §10.6; FR9.

Đọc ảnh: Sonnet 4.6 và Kimi K3 đúng cả bốn trường trên 3 ảnh dựng, Haiku 4.5 tự sửa sai nội dung không dấu ([spike-bedrock-models.md](../../../docs/research/spike-bedrock-models.md) mục 5); che PII ở bước nạp vì Guardrails không che kết quả tool.

## Mã nguồn (phase 5)

- `handler_api.py` (Lambda `yofina-ingest-api`), hai đường vào:
  - HTTP API `yofina-api`: sáu route `/ingest/*` (`POST /ingest/uploads`, `GET /ingest/jobs`, `GET /ingest/jobs/{job_id}`, `POST /ingest/rows/{row_id}/jar`, `POST /ingest/confirmations`, `POST /ingest/actions`).
  - AgentCore Gateway, target `ingest` (`infra-cdk/lib/agent-stack.ts`, `addIngestTarget`): ba tool của [contracts/tools/ingest.json](../../../contracts/tools/ingest.json), logic ở `yofina_ingest/gateway_api.py`. Tên tool lấy từ `context.client_context.custom["bedrockAgentCoreToolName"]` (`ingest___<tool>`), `user_id` do interceptor ghi đè, Cedar `gateway/policies/{start_job,get_job_status,confirm_rows}.cedar` ép `user_id`. `start_job` không tạo job (tệp chỉ tải lên từ màn hình); `get_job_status` trả `review` là đúng `data` của khối `ingest_review`; `confirm_rows` không token chỉ trả `NEEDS_CONFIRMATION`, có token thì đi đúng `IngestApi.apply_action` của `POST /ingest/actions` (cùng khóa HMAC, cùng bảng `jti`).
- `handler_worker.py` (Lambda `yofina-ingest`): bản tin SQS (S3 ObjectCreated) và op `eval_extract` (gọi trực tiếp, không DB).
- Logic ở gói `pipelines/ingest/yofina_ingest/` (đóng kèm bằng `--extra`, xem `INGEST_BUILD_COMMAND` trong `infra-cdk/lib/ingest-stack.ts`): `extract.py` (trích, che PII; điểm vào `extract` của `scripts/eval_ingest.py`), `classify.py` (gán hũ bằng bộ phân loại phase 4 `yofina_classify`: luật, bảng loại giao dịch, embedding k-NN trên nhãn của người dùng, model nhỏ; chỉ mức `auto` được chọn sẵn), `csvparse.py`, `worker.py`, `api.py`, `gateway_api.py`, `rest.py`, `repo.py` (toàn bộ SQL).
- Zip cần thêm `pipelines/classify/yofina_classify` (đã có trong `INGEST_BUILD_COMMAND`) và worker cần quyền model của vai `embedding` (`ingestLlmRoles` mặc định có `embedding`).
