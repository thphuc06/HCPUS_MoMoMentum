# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3[crt]>=1.43,<2"]
# ///
"""Sinh biến môi trường từ SSM Parameter Store (`/yofina/...`) do CDK ghi.

    uv run scripts/print_env.py frontend --write     # ghi frontend/.env.local (không commit)
    uv run scripts/print_env.py python               # in ra stdout dạng KEY=VALUE
    uv run scripts/print_env.py python --write       # ghi .env.local ở gốc repo

Frontend: chỉ các giá trị công khai/không nhạy cảm, tiền tố VITE_.
Python: mọi tham số, `/yofina/db/cluster-arn` → `YOFINA_DB_CLUSTER_ARN`; có thêm AWS_REGION.
`.env.local` đã nằm trong .gitignore; không đưa file này (hay nội dung) vào repo.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _yofina import REGION, session, ssm_all

ROOT = Path(__file__).resolve().parent.parent

# SSM key → biến Vite. Chỉ khóa có trong SSM mới được in (khóa của phase sau sẽ tự xuất hiện).
FRONTEND_MAP = {
    "auth/user-pool-id": "VITE_COGNITO_USER_POOL_ID",
    "auth/client-id": "VITE_COGNITO_CLIENT_ID",
    "api/url": "VITE_API_URL",
    "agent/runtime-arn": "VITE_AGENT_RUNTIME_ARN",
    "agent/runtime-url": "VITE_AGENT_RUNTIME_URL",
    "frontend/amplify-url": "VITE_APP_URL",
}


def to_env_name(key: str) -> str:
    return "YOFINA_" + re.sub(r"[^A-Za-z0-9]+", "_", key).upper()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", choices=["frontend", "python"])
    ap.add_argument("--write", action="store_true", help="ghi file .env.local thay vì in ra stdout")
    args = ap.parse_args()

    params = ssm_all(sess=session())
    lines: list[str] = []
    if args.target == "frontend":
        lines.append(f"VITE_AWS_REGION={REGION}")
        lines += [f"{var}={params[k]}" for k, var in FRONTEND_MAP.items() if k in params]
        out = ROOT / "frontend" / ".env.local"
    else:
        lines.append(f"AWS_REGION={REGION}")
        lines.append(f"AWS_DEFAULT_REGION={REGION}")
        lines += [f"{to_env_name(k)}={v}" for k, v in sorted(params.items())]
        out = ROOT / ".env.local"
    text = "\n".join(lines) + "\n"
    if args.write:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"đã ghi {out} ({len(lines)} biến)", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
