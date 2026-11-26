"""Chạy agent cục bộ (uvicorn) để thử trước khi lên Runtime.

    uv run python scripts/agent_run_local.py --mock                      # kèm MCP giả (tests/support) ở cổng 8201
    uv run python scripts/agent_run_local.py --gateway-url https://.../mcp  # trỏ Gateway thật
    uv run python scripts/agent_run_local.py --mock --cap-router 0 --cap-small 0 --cap-planner 0   # thử đường suy giảm

Gọi Bedrock THẬT (Region ap-southeast-1, profile mặc định) và đếm lượt gọi vào DynamoDB `yofina-usage` THẬT
(tên bảng đọc từ SSM `/yofina/dynamodb/usage-table`). `--cap-*` chỉ đặt trần bằng biến môi trường của tiến
trình này (YOFINA_LLM_DAILY_CAP_<VAI>), không sửa bảng hay SSM nào.

`--mock` khởi động `tests/support/mock_ledger_mcp.py` trong cùng tiến trình: CHỈ để dev, không thuộc gói sản phẩm.
Cần môi trường dự án (uv run python, không dùng metadata nội tuyến). Gọi thử: `uv run scripts/agent_call_local.py --message "số dư các hũ của mình"`.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--gateway-url", help="URL MCP của Gateway (mặc định: biến YOFINA_GATEWAY_URL)")
    ap.add_argument(
        "--mock", action="store_true", help="chạy MCP giả của tests/support và trỏ agent vào đó"
    )
    ap.add_argument("--mock-port", type=int, default=8201)
    ap.add_argument(
        "--cap-planner", type=int, help="đặt trần ngày vai planner (0 = chặn mọi lượt gọi)"
    )
    ap.add_argument("--cap-small", type=int, help="đặt trần ngày vai small (0 = chặn mọi lượt gọi)")
    ap.add_argument("--cap-router", type=int, help="đặt trần ngày vai router (0 = chặn mọi lượt gọi)")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()

    # Region tường minh; SSM để đọc tên bảng yofina-usage và (nếu có) /yofina/llm/...
    os.environ.setdefault("YOFINA_REGION", "ap-southeast-1")
    os.environ.setdefault("AWS_REGION", "ap-southeast-1")
    os.environ.setdefault("YOFINA_SSM_PREFIX", "/yofina")
    if args.cap_planner is not None:
        os.environ["YOFINA_LLM_DAILY_CAP_PLANNER"] = str(args.cap_planner)
    if args.cap_small is not None:
        os.environ["YOFINA_LLM_DAILY_CAP_SMALL"] = str(args.cap_small)
    if args.cap_router is not None:
        os.environ["YOFINA_LLM_DAILY_CAP_ROUTER"] = str(args.cap_router)

    logging.basicConfig(
        level=args.log_level.upper(), format="%(message)s", stream=sys.stdout, force=True
    )
    for noisy in ("strands", "botocore", "urllib3", "httpx", "httpcore", "mcp", "httpx2"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("strands.tools.mcp.mcp_client").setLevel(
        logging.CRITICAL
    )  # từ chối Cedar đã có log của agent

    if args.mock:
        sys.path.insert(0, str(ROOT / "tests" / "support"))
        from mock_ledger_mcp import RunningMock

        mock = RunningMock(args.mock_port).start()
        os.environ["YOFINA_GATEWAY_URL"] = mock.url
        print(f"[mock] MCP giả (CHỈ để dev) tại {mock.url}", flush=True)
    elif args.gateway_url:
        os.environ["YOFINA_GATEWAY_URL"] = args.gateway_url
    if not os.environ.get("YOFINA_GATEWAY_URL"):
        print(
            "Thiếu Gateway: dùng --mock, --gateway-url hoặc biến YOFINA_GATEWAY_URL",
            file=sys.stderr,
        )
        return 2

    import uvicorn

    print(f"[agent] http://{args.host}:{args.port}  (POST /invocations, GET /ping)", flush=True)
    uvicorn.run("yofina_agent.app:app", host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
