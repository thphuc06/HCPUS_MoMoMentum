# gateway/tools/ingest/

Tool `ingest___*` (target `ingest`): `start_job`, `get_job_status`, `confirm_rows` (job bất đồng bộ, S3 + SQS; ảnh chụp và CSV ở MVP; PDF là mở rộng, đọc bằng model, không dùng Bedrock Data Automation vì không liệt kê tiếng Việt). Proposal §9, §10.6; FR9.

Đọc ảnh: Sonnet 4.6 và Kimi K3 đúng cả bốn trường trên 3 ảnh dựng, Haiku 4.5 tự sửa sai nội dung không dấu ([spike-bedrock-models.md](../../../docs/research/spike-bedrock-models.md) mục 5); che PII ở bước nạp vì Guardrails không che kết quả tool.
