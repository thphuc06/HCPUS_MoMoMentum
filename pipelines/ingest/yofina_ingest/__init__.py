"""Nạp dữ liệu ngoài ví từ ảnh và CSV (F6, phase 5): trích dòng, che PII, khử trùng, đề xuất hũ, và REST của Lambda `yofina-ingest-api`.

Cách chia (mọi lời gọi model đi qua `yofina_core.llm`):

- `extract.py`: trích dòng từ một tệp (ảnh qua Bedrock Converse, CSV bằng bộ đọc tất định). KHÔNG chạm DB; `extract(...)` là
  điểm vào của `scripts/eval_ingest.py`.
- `worker.py`: một job SQS: đọc S3, gọi `extract`, khử trùng với sổ cái, ghi `ingest_rows`, chuyển trạng thái job.
- `api.py`, `rest.py`: các route `/ingest/*` (presigned POST, tiến độ, đổi hũ, xác nhận, chốt `confirm_rows`).
- `repo.py`: toàn bộ SQL (hàm `app_*` của migration 0050 và một transaction ghi sổ cái).
"""
