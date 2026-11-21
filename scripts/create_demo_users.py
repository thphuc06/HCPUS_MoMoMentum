# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3[crt]>=1.43,<2"]
# ///
"""Tạo 6 tài khoản demo trong Cognito và lưu mật khẩu vào MỘT secret Secrets Manager `yofina-demo-accounts`.

    uv run scripts/create_demo_users.py            # tạo user còn thiếu, giữ mật khẩu đã có
    uv run scripts/create_demo_users.py --rotate   # đặt lại mật khẩu mới cho cả 6 tài khoản

Mật khẩu sinh ngẫu nhiên, đặt permanent, KHÔNG in ra console và KHÔNG ghi vào file. Đọc lại:
    aws secretsmanager get-secret-value --secret-id yofina-demo-accounts --region ap-southeast-1 --query SecretString --output text

Secret có dạng {"minh": {"email": "...", "password": "..."}, ...}. Đăng nhập Cognito bằng email.
Không dùng email thật: miền demo.yofina.example không nhận thư; email được đánh dấu đã xác minh nên không cần mail.
"""

from __future__ import annotations

import argparse
import json
import secrets
import string
import sys

from _yofina import session, ssm_param
from botocore.exceptions import ClientError

SECRET_NAME = "yofina-demo-accounts"
EMAIL_DOMAIN = "demo.yofina.example"
USERS = ["minh", "lan", "khoa", "giamkhao1", "giamkhao2", "giamkhao3"]


def gen_password() -> str:
    """32 ký tự, đủ chữ hoa, chữ thường, số, ký hiệu (thỏa chính sách của pool)."""
    sym = "!#$%^&*()-_=+"
    chars = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice(sym),
    ]
    pool = string.ascii_letters + string.digits + sym
    chars += [secrets.choice(pool) for _ in range(28)]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def load_secret(sm) -> dict | None:
    try:
        return json.loads(sm.get_secret_value(SecretId=SECRET_NAME)["SecretString"])
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return None
        raise


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rotate", action="store_true", help="đặt mật khẩu mới cho mọi tài khoản")
    args = ap.parse_args()

    sess = session()
    pool_id = ssm_param("auth/user-pool-id", sess=sess)
    idp = sess.client("cognito-idp")
    sm = sess.client("secretsmanager")

    accounts = load_secret(sm) or {}
    changed = False
    for name in USERS:
        email = f"{name}@{EMAIL_DOMAIN}"
        entry = accounts.get(name) or {}
        need_password = args.rotate or not entry.get("password")
        try:
            idp.admin_get_user(UserPoolId=pool_id, Username=email)
            exists = True
        except ClientError as e:
            if e.response["Error"]["Code"] != "UserNotFoundException":
                raise
            exists = False
        if not exists:
            idp.admin_create_user(
                UserPoolId=pool_id,
                Username=email,
                UserAttributes=[
                    {"Name": "email", "Value": email},
                    {"Name": "email_verified", "Value": "true"},
                ],
                MessageAction="SUPPRESS",
            )
            need_password = True
        if need_password:
            password = gen_password()
            # Lưu secret TRƯỚC khi đặt mật khẩu: nếu bước sau lỗi thì không bao giờ mất mật khẩu đang dùng.
            accounts[name] = {"email": email, "password": password}
            _save(sm, accounts)
            idp.admin_set_user_password(
                UserPoolId=pool_id, Username=email, Password=password, Permanent=True
            )
            changed = True
            print(f"{name}: {'tạo mới' if not exists else 'đặt lại mật khẩu'} ({email})")
        else:
            print(f"{name}: đã có, giữ nguyên ({email})")
    if not changed:
        print("không có thay đổi")
    print(f"mật khẩu nằm ở secret {SECRET_NAME} (Secrets Manager)")
    return 0


def _save(sm, accounts: dict) -> None:
    body = json.dumps(accounts)
    try:
        sm.put_secret_value(SecretId=SECRET_NAME, SecretString=body)
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        sm.create_secret(
            Name=SECRET_NAME,
            Description="Tai khoan demo Yofina (Cognito). Mat khau sinh ngau nhien.",
            SecretString=body,
            Tags=[{"Key": "project", "Value": "yofina"}],
        )


if __name__ == "__main__":
    sys.exit(main())
