# gateway/tools/ingest/

Tool `ingest___*` (target `ingest`): `start_job`, `get_job_status`, `confirm_rows` (job bất đồng bộ, S3 + SQS; ảnh chụp và CSV ở MVP; PDF là mở rộng, đọc bằng model, không dùng Bedrock Data Automation vì không liệt kê tiếng Việt). Proposal §9, §10.6; FR9.

Đọc ảnh: Sonnet 4.6 và Kimi K3 đúng cả bốn trường trên 3 ảnh dựng, Haiku 4.5 tự sửa sai nội dung không dấu ([spike-bedrock-models.md](../../../docs/research/spike-bedrock-models.md) mục 5); che PII ở bước nạp vì Guardrails không che kết quả tool.

## Mã nguồn (phase 5)

- `handler_api.py` (Lambda `yofina-ingest-api`): sáu route `/ingest/*` của HTTP API `yofina-api` (`POST /ingest/uploads`, `GET /ingest/jobs`, `GET /ingest/jobs/{job_id}`, `POST /ingest/rows/{row_id}/jar`, `POST /ingest/confirmations`, `POST /ingest/actions`).
- `handler_worker.py` (Lambda `yofina-ingest`): bản tin SQS (S3 ObjectCreated) và op `eval_extract` (gọi trực tiếp, không DB).
- Logic ở gói `pipelines/ingest/yofina_ingest/` (đóng kèm bằng `--extra`, xem `scripts/build_lambda.py`): `extract.py` (trích, che PII, gán hũ; điểm vào `extract` của `scripts/eval_ingest.py`), `csvparse.py`, `worker.py`, `api.py`, `rest.py`, `repo.py` (toàn bộ SQL).
- Chưa có handler cho target Gateway `ingest` (tool `start_job`, `get_job_status`, `confirm_rows` của agent): luồng ghép thêm khi tạo target.
