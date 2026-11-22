# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3[crt]>=1.43,<2"]
# ///
"""Gọi Lambda `yofina-migrator`: đồng bộ role `yofina_app` và chạy các file db/migrations/*.sql chưa chạy.

    uv run scripts/migrate.py                 # dùng db/migrations/
    uv run scripts/migrate.py --dry-run       # chỉ liệt kê migration chờ chạy
    uv run scripts/migrate.py --dir <thư mục> # thư mục khác (ví dụ migration thử)
    uv run scripts/migrate.py --seed          # nạp db/seed/*.sql (bảng tra: tx_type_map, fee_schedules, jar_templates)

Tên file (bỏ đuôi .sql) là `version`, sắp xếp theo thứ tự chữ. Migration đã chạy mà nội dung đổi thì migrator từ chối.
Với --seed, `version` là `seed_<tên file>_<8 ký tự đầu của sha256 nội dung>`: sửa file seed thì ra version mới và được
nạp lại (file seed viết lại được: INSERT ... ON CONFLICT DO UPDATE), không sửa được file seed đã nạp mà bị từ chối.
Chạy `--seed` SAU khi migration đã chạy (các bảng tra do 0005 tạo).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from _yofina import session, ssm_param
from botocore.config import Config

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=ROOT / "db" / "migrations")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--seed",
        action="store_true",
        help="nạp db/seed/*.sql (viết lại được) thay vì db/migrations/*.sql",
    )
    args = ap.parse_args()

    src = ROOT / "db" / "seed" if args.seed else args.dir
    files = sorted(src.glob("*.sql"))
    migrations = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        version = f.stem
        if args.seed:
            digest = hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()[:8]
            version = f"seed_{f.stem}_{digest}"
        migrations.append({"version": version, "sql": text})
    print(
        f"{len(migrations)} migration trong {src}: {[m['version'] for m in migrations]}",
        file=sys.stderr,
    )

    sess = session()
    fn = ssm_param("db/migrator-function", sess=sess)
    client = sess.client(
        "lambda", config=Config(read_timeout=900, connect_timeout=10, retries={"max_attempts": 1})
    )
    resp = client.invoke(
        FunctionName=fn,
        Payload=json.dumps({"migrations": migrations, "dry_run": args.dry_run}).encode("utf-8"),
    )
    body = json.loads(resp["Payload"].read())
    print(json.dumps(body, indent=2, ensure_ascii=False))
    if resp.get("FunctionError"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
