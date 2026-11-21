"""Entrypoint của AgentCore Runtime (CodeZip: `entryPoint: ["main.py"]`): chạy ASGI trên cổng 8080.

Runtime gọi `POST /invocations` và `GET /ping` trên 0.0.0.0:8080 (giao thức AGUI). Mã nguồn của gói nằm ở
`src/yofina_agent`; `scripts/agent_build_zip.py` chép gói này vào gốc zip cùng `yofina_core`.
"""

import logging
import os
import sys

import uvicorn
from yofina_agent.app import app


def configure_logging() -> None:
    level = os.environ.get("YOFINA_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=level, format="%(message)s", stream=sys.stdout, force=True)
    for noisy in ("strands", "botocore", "urllib3", "httpx", "httpcore", "mcp"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


if __name__ == "__main__":
    configure_logging()
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), log_level="warning")
