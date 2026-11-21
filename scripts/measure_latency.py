# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3[crt]>=1.43,<2", "pycognito>=2024.5"]
# ///
"""Đo độ trễ REST từ máy này (qua Internet tới API Gateway): GET /jars và luồng chuyển hũ.

    uv run scripts/measure_latency.py                 # 40 lần GET /jars, 20 lượt chuyển hũ
    uv run scripts/measure_latency.py --gets 100 --moves 30 --who minh

Mỗi lượt chuyển hũ = POST /confirmations + POST /actions; chuyển đi rồi chuyển lại (số dư không trôi),
cuối cùng đặt lại tài khoản. Số đo gồm độ trễ mạng từ máy chạy script, không phải độ trễ trong Region.
"""

from __future__ import annotations

import argparse
import statistics
import sys

from _demo_auth import api_url, call_api, demo_accounts, login_access_token
from _yofina import session


def pct(xs: list[float], p: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, round(p / 100 * (len(s) - 1)))]


def line(name: str, xs: list[float]) -> str:
    return (
        f"{name:34s} n={len(xs):3d} min={min(xs):6.0f} p50={pct(xs, 50):6.0f} "
        f"p95={pct(xs, 95):6.0f} max={max(xs):6.0f} mean={statistics.mean(xs):6.0f} ms"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", default="minh")
    ap.add_argument("--gets", type=int, default=40)
    ap.add_argument("--moves", type=int, default=20)
    args = ap.parse_args()

    sess = session()
    base = api_url(sess)
    token = login_access_token(args.who, sess=sess, accounts=demo_accounts(sess))

    status, _, cold = call_api(base, "POST", "/demo/reset", token, timeout=60)
    assert status == 200, status
    print(f"đặt lại dữ liệu: {cold:.0f} ms")

    for _ in range(3):  # làm ấm Lambda và kết nối
        call_api(base, "GET", "/jars", token)

    gets: list[float] = []
    for _ in range(args.gets):
        status, _, ms = call_api(base, "GET", "/jars", token)
        assert status == 200, status
        gets.append(ms)

    confirms: list[float] = []
    actions: list[float] = []
    flows: list[float] = []
    legs = [
        {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100_000},
        {"from_jar": "an_uong", "to_jar": "giai_tri", "amount_vnd": 100_000},
    ]
    for i in range(args.moves):
        params = legs[i % 2]
        body = {"tool": "move_between_jars", "params": params}
        s1, conf, m1 = call_api(base, "POST", "/confirmations", token, body)
        assert s1 == 200, conf
        s2, rec, m2 = call_api(
            base, "POST", "/actions", token, {**body, "confirm_token": conf["confirm_token"]}
        )
        assert s2 == 200, rec
        confirms.append(m1)
        actions.append(m2)
        flows.append(m1 + m2)

    call_api(base, "POST", "/demo/reset", token, timeout=60)
    print(line("GET /jars", gets))
    print(line("POST /confirmations", confirms))
    print(line("POST /actions (ghi 2 dòng + số dư)", actions))
    print(line("luồng chuyển hũ (hai bước)", flows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
