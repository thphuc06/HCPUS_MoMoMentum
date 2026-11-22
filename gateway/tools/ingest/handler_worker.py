"""Điểm vào của Lambda `yofina-ingest` (worker): bản tin SQS (thông báo S3 ObjectCreated) và op `eval_extract`.

- SQS: `batchItemFailures` theo từng bản tin; lỗi tạm thời thì giao lại, lần cuối thì job được đánh dấu `failed` rồi bản tin vào DLQ.
- `{"op": "eval_extract", "filename", "content_type", "data_b64"}` (gọi trực tiếp, cho `scripts/eval_ingest.py --via-lambda`): chỉ trích và
  phân loại, KHÔNG đọc hay ghi DB, KHÔNG đọc S3.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

from yofina_ingest.extract import extract
from yofina_ingest.repo import IngestRepo
from yofina_ingest.settings import IngestRuntime
from yofina_ingest.worker import Storage, Worker, handle_sqs

from yofina_core.config import Config
from yofina_core.db import DataApi

logging.getLogger().setLevel(os.environ.get("YOFINA_LOG_LEVEL", "INFO"))

_WORKER: tuple[Worker, IngestRuntime] | None = None


def get_worker() -> tuple[Worker, IngestRuntime]:
    global _WORKER
    if _WORKER is None:
        cfg = Config()
        rt = IngestRuntime.from_config(cfg)
        _WORKER = (
            Worker(IngestRepo(DataApi.from_config(cfg)), Storage(region=cfg.region()), rt),
            rt,
        )
    return _WORKER


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    if event.get("op") == "eval_extract":
        data = base64.b64decode(event["data_b64"])
        return extract(
            data,
            filename=str(event.get("filename", "")),
            content_type=str(event.get("content_type", "")),
            mode=str(event.get("mode", "eval")),
        )
    worker, rt = get_worker()
    return handle_sqs(event, worker, max_receive_count=rt.max_receive_count)
