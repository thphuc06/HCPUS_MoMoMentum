# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3[crt]>=1.43,<2", "pycognito>=2024.5"]
# ///
"""Nạp dữ liệu persona cho 6 tài khoản demo: gán nhóm Cognito theo persona rồi gọi POST /demo/reset.

    uv run scripts/seed_demo.py                 # cả 6 tài khoản
    uv run scripts/seed_demo.py minh lan        # chỉ một số tài khoản

Việc làm (idempotent, chạy lại bao nhiêu lần cũng được):
1. Đọc bảng ánh xạ `data/personas/accounts.json` (tài khoản -> persona, tiền tố nhóm).
2. Bảo đảm nhóm Cognito `<tiền tố><persona>` tồn tại trong user pool `yofina-users`; đặt mỗi tài khoản
   vào đúng nhóm (và gỡ khỏi nhóm persona khác). Persona của người gọi ở API lấy từ nhóm này
   (claim `cognito:groups` của access token), không rẽ nhánh theo email trong mã.
   Nhóm `ops` (xem trace của mọi người dùng): chỉ tài khoản vận hành trong `ops_accounts` của accounts.json;
   tài khoản khác đang có `ops` bị GỠ ra; danh sách có tài khoản `giamkhao*` thì dừng trước mọi lệnh ghi.
3. Đăng nhập SRP từng tài khoản (mật khẩu từ secret trong bộ nhớ) và gọi `POST /demo/reset`
   (xóa dữ liệu của CHÍNH tài khoản đó, sinh lại persona, đặt đồng hồ mô phỏng về ngày neo).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Collection
from pathlib import Path

from _demo_auth import api_url, call_api, demo_accounts, login_access_token
from _yofina import session, ssm_param
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent.parent
ACCOUNTS_FILE = ROOT / "data" / "personas" / "accounts.json"
# Nhóm xem bảng vận hành và trace của mọi người dùng (infra-cdk/lib/identity-stack.ts tạo nhóm, script chỉ gán thành viên).
OPS_GROUP = "ops"
JUDGE_PREFIX = "giamkhao"  # tài khoản đưa giám khảo: không bao giờ thuộc OPS_GROUP


def ensure_groups(
    sess,
    mapping: dict[str, str],
    prefix: str,
    accounts: dict,
    *,
    ops_accounts: Collection[str],
) -> None:
    """Đặt mỗi tài khoản của `mapping` vào đúng nhóm persona; tài khoản trong `ops_accounts` vào OPS_GROUP, tài khoản khác bị gỡ khỏi nó."""
    judges = sorted(n for n in ops_accounts if n.startswith(JUDGE_PREFIX))
    if judges:
        raise SystemExit(f"tài khoản giám khảo không được thuộc nhóm {OPS_GROUP}: {judges}")
    idp = sess.client("cognito-idp")
    pool = ssm_param("auth/user-pool-id", sess=sess)
    wanted_groups = {prefix + persona for persona in mapping.values()}
    for g in sorted(wanted_groups):
        try:
            idp.create_group(
                UserPoolId=pool, GroupName=g, Description="Persona demo (Yofina): xem data/personas"
            )
            print(f"đã tạo nhóm {g}", file=sys.stderr)
        except ClientError as e:
            if e.response["Error"]["Code"] != "GroupExistsException":
                raise
    for name, persona in mapping.items():
        email = accounts[name]["email"]
        target = prefix + persona
        current = {
            g["GroupName"]
            for g in idp.admin_list_groups_for_user(UserPoolId=pool, Username=email)["Groups"]
        }
        for g in current:
            if g.startswith(prefix) and g != target:
                idp.admin_remove_user_from_group(UserPoolId=pool, Username=email, GroupName=g)
        if target not in current:
            idp.admin_add_user_to_group(UserPoolId=pool, Username=email, GroupName=target)
            print(f"{name}: thêm vào nhóm {target}", file=sys.stderr)
        if name in ops_accounts and OPS_GROUP not in current:
            idp.admin_add_user_to_group(UserPoolId=pool, Username=email, GroupName=OPS_GROUP)
            print(f"{name}: thêm vào nhóm {OPS_GROUP}", file=sys.stderr)
        elif name not in ops_accounts and OPS_GROUP in current:
            idp.admin_remove_user_from_group(UserPoolId=pool, Username=email, GroupName=OPS_GROUP)
            print(f"{name}: gỡ khỏi nhóm {OPS_GROUP}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "names", nargs="*", help="tài khoản cần nạp (mặc định: tất cả trong accounts.json)"
    )
    args = ap.parse_args()

    cfg = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
    mapping: dict[str, str] = cfg["demo_accounts"]
    names = args.names or list(mapping)
    unknown = [n for n in names if n not in mapping]
    if unknown:
        raise SystemExit(f"không có trong accounts.json: {unknown}")

    sess = session()
    accounts = demo_accounts(sess)
    ensure_groups(
        sess,
        {n: mapping[n] for n in names},
        cfg["group_prefix"],
        accounts,
        ops_accounts=cfg["ops_accounts"],
    )

    base = api_url(sess)
    failed = 0
    for name in names:
        token = login_access_token(name, sess=sess, accounts=accounts)
        status, body, ms = call_api(base, "POST", "/demo/reset", token, timeout=60)
        if status == 200:
            print(
                f"{name:10s} persona={mapping[name]:5s} app_date={body['app_date']} "
                f"offset={body['clock_offset_days']} hũ={body['jars_count']} "
                f"giao dịch={body['transactions_count']} ({ms:.0f} ms)"
            )
        else:
            failed += 1
            print(f"{name:10s} LỖI {status}: {body}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
