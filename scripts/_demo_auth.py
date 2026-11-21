"""Đăng nhập tài khoản demo bằng SRP và gọi REST API (dùng chung cho seed_demo.py, đo độ trễ và test tích hợp).

Mật khẩu lấy từ secret `yofina-demo-accounts` trong bộ nhớ: không in, không ghi file. Chỉ dùng thư viện
chuẩn cho HTTP (urllib) để khỏi thêm phụ thuộc; `pycognito` cho SRP (giống scripts/get_token.py).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from _yofina import REGION, session, ssm_param

SECRET_NAME = "yofina-demo-accounts"


def demo_accounts(sess=None) -> dict[str, dict[str, str]]:
    sess = sess or session()
    return json.loads(
        sess.client("secretsmanager").get_secret_value(SecretId=SECRET_NAME)["SecretString"]
    )


def login_access_token(name: str, *, sess=None, accounts: dict | None = None) -> str:
    """Access token Cognito của tài khoản demo `name` (đăng nhập SRP như SPA)."""
    from pycognito.aws_srp import AWSSRP

    sess = sess or session()
    acct = (accounts or demo_accounts(sess))[name]
    srp = AWSSRP(
        username=acct["email"],
        password=acct["password"],
        pool_id=ssm_param("auth/user-pool-id", sess=sess),
        client_id=ssm_param("auth/client-id", sess=sess),
        pool_region=REGION,
    )
    return srp.authenticate_user()["AuthenticationResult"]["AccessToken"]


def api_url(sess=None) -> str:
    return ssm_param("api/url", sess=sess or session()).rstrip("/")


def call_api(
    base: str,
    method: str,
    path: str,
    token: str | None,
    body: Any = None,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 40.0,
) -> tuple[int, Any, float]:
    """Gọi REST, trả (status, JSON hoặc văn bản, mili giây). Không ném lỗi theo mã HTTP."""
    hdrs = {"content-type": "application/json", **(headers or {})}
    if token:
        hdrs["authorization"] = f"Bearer {token}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(base + path, data=data, method=method, headers=hdrs)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    ms = (time.perf_counter() - t0) * 1000
    text = raw.decode("utf-8", errors="replace")
    try:
        return status, json.loads(text) if text else None, ms
    except ValueError:
        return status, text, ms
