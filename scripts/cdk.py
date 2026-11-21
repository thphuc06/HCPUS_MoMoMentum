# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3[crt]>=1.43,<2"]
# ///
"""Chạy `cdk` trong infra-cdk/ với account/region đúng và email cảnh báo đọc từ SSM.

    uv run scripts/cdk.py synth --strict
    uv run scripts/cdk.py diff
    uv run scripts/cdk.py deploy YofinaFoundation --require-approval never

Email cảnh báo ngân sách KHÔNG nằm trong repo: nó lưu ở SSM SecureString `/yofina/alert-email`
và được truyền cho CDK qua `-c alertEmail=...` mỗi lần chạy (để subscription SNS không bị gỡ khi deploy lại).
Chưa có tham số đó thì bỏ qua, stack vẫn deploy (không có subscription email).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

for _stream in (sys.stdout, sys.stderr):
    _stream.reconfigure(encoding="utf-8", errors="replace")

REGION = "ap-southeast-1"
ROOT = Path(__file__).resolve().parent.parent
INFRA = ROOT / "infra-cdk"


def main() -> int:
    session = boto3.Session(region_name=REGION)
    account = session.client("sts").get_caller_identity()["Account"]
    env = dict(
        os.environ,
        CDK_DEFAULT_ACCOUNT=account,
        CDK_DEFAULT_REGION=REGION,
        AWS_REGION=REGION,
        AWS_DEFAULT_REGION=REGION,
    )
    args = sys.argv[1:]
    context: list[str] = []
    try:
        email = session.client("ssm").get_parameter(
            Name="/yofina/alert-email", WithDecryption=True
        )["Parameter"]["Value"]
        context = ["-c", f"alertEmail={email}"]
    except ClientError as e:
        if e.response["Error"]["Code"] != "ParameterNotFound":
            raise
    npx = shutil.which("npx") or "npx"
    return subprocess.call([npx, "cdk", *args, *context], cwd=INFRA, env=env)


if __name__ == "__main__":
    sys.exit(main())
