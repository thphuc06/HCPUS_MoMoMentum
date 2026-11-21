# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3[crt]>=1.43,<2", "pycognito>=2024.5"]
# ///
"""Đăng nhập một tài khoản demo bằng SRP (đúng luồng của SPA) và in access token ra stdout.

    uv run scripts/get_token.py minh            # in access token (JWT, sống 60 phút)
    uv run scripts/get_token.py minh --check    # chỉ báo đăng nhập được hay không, không in token

Mật khẩu lấy từ secret `yofina-demo-accounts` trong bộ nhớ, không in, không ghi file.
Dùng cho test tích hợp: TOKEN=$(uv run scripts/get_token.py lan)
"""

from __future__ import annotations

import argparse
import json
import sys

from _yofina import REGION, session, ssm_param
from pycognito.aws_srp import AWSSRP


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name", help="minh, lan, khoa, giamkhao1..3")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    sess = session()
    secret = json.loads(
        sess.client("secretsmanager").get_secret_value(SecretId="yofina-demo-accounts")[
            "SecretString"
        ]
    )
    acct = secret[args.name]
    srp = AWSSRP(
        username=acct["email"],
        password=acct["password"],
        pool_id=ssm_param("auth/user-pool-id", sess=sess),
        client_id=ssm_param("auth/client-id", sess=sess),
        pool_region=REGION,
    )
    tokens = srp.authenticate_user()["AuthenticationResult"]
    if args.check:
        print(
            f"đăng nhập SRP {args.name}: OK (có AccessToken={bool(tokens.get('AccessToken'))}, "
            f"hết hạn sau {tokens['ExpiresIn']}s, loại {tokens['TokenType']})",
            file=sys.stderr,
        )
    else:
        print(tokens["AccessToken"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
