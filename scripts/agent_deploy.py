# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3[crt]>=1.43,<2"]
# ///
"""Cập nhật agent trên AgentCore Runtime bằng một lệnh: build zip ARM64 -> upload S3 -> deploy `YofinaAgent` -> chờ READY.

    uv run scripts/agent_deploy.py                         # build + upload + cdk deploy YofinaAgent + chờ READY
    uv run scripts/agent_deploy.py --skip-build            # dùng build/agent/agent-arm64.zip đã có
    uv run scripts/agent_deploy.py -c policyMode=LOG_ONLY  # các tham số sau -c chuyển nguyên cho CDK

Cách chạy: zip được đặt tên theo nội dung (`builds/agent-<sha256 12 ký tự>.zip`) trong bucket artifact (SSM
`/yofina/s3/artifact-bucket`), khóa ghi vào SSM `/yofina/agent/zip-key`; stack `YofinaAgent` đọc khóa đó lúc deploy nên
CloudFormation thấy `prefix` đổi và tạo version Runtime mới (platform V2 cập nhật mất khoảng 5 phút; gom thay đổi
rồi deploy một lần). Cùng nội dung thì khóa không đổi và CDK không làm gì.
Credential: profile mặc định của AWS CLI, Region `ap-southeast-1` (đặt tường minh trong `_yofina`).
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import time
from pathlib import Path

from _yofina import REGION, session, ssm_param

ROOT = Path(__file__).resolve().parent.parent
ZIP = ROOT / "build" / "agent" / "agent-arm64.zip"
ZIP_KEY_PARAM = "/yofina/agent/zip-key"


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), file=sys.stderr)
    subprocess.run(cmd, check=True, cwd=ROOT)


def sha12(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def wait_ready(runtime_id: str, timeout: int = 900) -> dict:
    client = session().client("bedrock-agentcore-control")
    t0 = time.time()
    while True:
        rt = client.get_agent_runtime(agentRuntimeId=runtime_id)
        if rt["status"] not in ("CREATING", "UPDATING"):
            return rt
        if time.time() - t0 > timeout:
            raise TimeoutError(f"Runtime vẫn {rt['status']} sau {timeout}s")
        time.sleep(10)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--skip-build", action="store_true", help="dùng zip đã build")
    ap.add_argument("--zip", type=Path, default=ZIP)
    ap.add_argument(
        "-c", "--context", action="append", default=[], help="khóa=giá trị chuyển cho CDK"
    )
    args = ap.parse_args()

    if not args.skip_build:
        run(["uv", "run", "scripts/agent_build_zip.py"])
    zip_path: Path = args.zip if args.zip.is_absolute() else ROOT / args.zip
    if not zip_path.exists():
        print(f"Không thấy {zip_path}", file=sys.stderr)
        return 1

    sess = session()
    bucket = ssm_param("s3/artifact-bucket", sess=sess)
    key = f"builds/agent-{sha12(zip_path)}.zip"
    s3 = sess.client("s3")
    try:
        s3.head_object(Bucket=bucket, Key=key)
        print(f"đã có s3://<bucket>/{key}, bỏ qua upload", file=sys.stderr)
    except s3.exceptions.ClientError:
        print(
            f"upload {zip_path.stat().st_size / 1e6:.1f} MB -> s3://<bucket>/{key}", file=sys.stderr
        )
        s3.upload_file(str(zip_path), bucket, key)
    sess.client("ssm").put_parameter(Name=ZIP_KEY_PARAM, Value=key, Type="String", Overwrite=True)

    cdk_cmd = [
        "uv",
        "run",
        "scripts/cdk.py",
        "deploy",
        "YofinaAgent",
        "--require-approval",
        "never",
    ]
    for kv in args.context:
        cdk_cmd += ["-c", kv]
    run(cdk_cmd)

    runtime_id = ssm_param("agent/runtime-id", sess=sess)
    rt = wait_ready(runtime_id)
    print(f"Runtime {rt['status']} (version {rt.get('agentRuntimeVersion')}), vùng {REGION}")
    return 0 if rt["status"] == "READY" else 1


if __name__ == "__main__":
    sys.exit(main())
