# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3[crt]>=1.43,<2"]
# ///
"""Deploy thủ công frontend lên Amplify Hosting bằng zip (không nối GitHub).

    uv run scripts/deploy_frontend.py frontend/dist

Thư mục build phải có index.html ở gốc. Các bước: zip thư mục → amplify create-deployment →
PUT zip lên URL được cấp → start-deployment → chờ job SUCCEED. App id, branch lấy từ SSM `/yofina/frontend/*`.
"""

from __future__ import annotations

import argparse
import http.client
import io
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from _yofina import session, ssm_param


def make_zip(src: Path) -> bytes:
    if not (src / "index.html").is_file():
        raise SystemExit(f"{src} không có index.html ở gốc")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(src).as_posix())
    return buf.getvalue()


def put_zip(url: str, data: bytes) -> None:
    u = urllib.parse.urlsplit(url)
    conn = http.client.HTTPSConnection(u.netloc, timeout=120)
    # Không đặt Content-Type: URL được ký không kèm header đó (giống `curl -T`).
    conn.request(
        "PUT",
        u.path + ("?" + u.query if u.query else ""),
        body=data,
        headers={"Content-Length": str(len(data))},
    )
    resp = conn.getresponse()
    body = resp.read()
    if resp.status >= 300:
        raise SystemExit(f"upload thất bại: HTTP {resp.status} {body[:300]!r}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("build_dir", type=Path, help="thư mục build của frontend (có index.html ở gốc)")
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()

    sess = session()
    app_id = ssm_param("frontend/amplify-app-id", sess=sess)
    branch = ssm_param("frontend/amplify-branch", sess=sess)
    url = ssm_param("frontend/amplify-url", sess=sess)
    amp = sess.client("amplify")

    data = make_zip(args.build_dir)
    print(f"zip {len(data) / 1024:.0f} KB từ {args.build_dir}")
    dep = amp.create_deployment(appId=app_id, branchName=branch)
    put_zip(dep["zipUploadUrl"], data)
    job_id = dep["jobId"]
    amp.start_deployment(appId=app_id, branchName=branch, jobId=job_id)
    t0 = time.monotonic()
    while True:
        status = amp.get_job(appId=app_id, branchName=branch, jobId=job_id)["job"]["summary"][
            "status"
        ]
        print(f"job {job_id}: {status} ({time.monotonic() - t0:.0f}s)")
        if status == "SUCCEED":
            break
        if status in ("FAILED", "CANCELLED"):
            return 1
        if time.monotonic() - t0 > args.timeout:
            print("quá thời gian chờ")
            return 1
        time.sleep(3)
    print(f"đã deploy: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
