# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3[crt]>=1.43,<2", "pycognito>=2024.5"]
# ///
"""Đo độ trễ của ví mô phỏng (phase 2): `GET /overview` và luồng ghi (xác nhận rồi thực hiện), CẢ phía máy gọi LẪN phía Lambda.

    uv run scripts/measure_wallet.py                  # 60 lần GET /overview, 20 lượt ghi, tài khoản minh
    uv run scripts/measure_wallet.py --gets 100 --writes 30

Phía Lambda lấy từ log `rest_request` (trường `ms`: thời gian xử lý trong handler, gồm các lệnh gọi Data API và việc phát sự
kiện, KHÔNG gồm khởi động lạnh và mạng tới API Gateway), lọc theo khoảng thời gian chạy này. Mục tiêu: p95 của `GET /overview`
phía Lambda dưới 300 ms. Sau khi đo, tài khoản được đặt lại. Mỗi lượt ghi chi 1.000 ₫ từ hũ Đi lại.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time

from _demo_auth import api_url, call_api, demo_accounts, login_access_token
from _yofina import session, ssm_param


def pct(xs: list[float], p: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, round(p / 100 * (len(s) - 1)))]


def line(name: str, xs: list[float]) -> str:
    if not xs:
        return f"{name:44s} (không có số liệu)"
    return (
        f"{name:44s} n={len(xs):3d} min={min(xs):6.0f} p50={pct(xs, 50):6.0f} "
        f"p95={pct(xs, 95):6.0f} max={max(xs):6.0f} mean={statistics.mean(xs):6.0f} ms"
    )


def lambda_side(sess, since_ms: int, until_ms: int) -> dict[str, list[float]]:
    """`ms` của mọi dòng `rest_request` trong khoảng thời gian, gom theo route."""
    logs = sess.client("logs")
    group = f"/aws/lambda/{ssm_param('ledger/function-name', sess=sess)}"
    out: dict[str, list[float]] = {}
    kwargs = {
        "logGroupName": group,
        "startTime": since_ms,
        "endTime": until_ms,
        "filterPattern": '{ $.msg = "rest_request" }',
    }
    while True:
        resp = logs.filter_log_events(**kwargs)
        for ev in resp.get("events", []):
            text = ev["message"]
            start = text.find("{")
            if start < 0:
                continue
            try:
                rec = json.loads(text[start:])
            except ValueError:
                continue
            if rec.get("outcome") == "200":
                out.setdefault(rec["route"], []).append(float(rec["ms"]))
        token = resp.get("nextToken")
        if not token:
            return out
        kwargs["nextToken"] = token


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--who", default="minh")
    ap.add_argument("--gets", type=int, default=60)
    ap.add_argument("--writes", type=int, default=20)
    args = ap.parse_args()

    sess = session()
    base = api_url(sess)
    token = login_access_token(args.who, sess=sess, accounts=demo_accounts(sess))
    status, _, cold = call_api(base, "POST", "/demo/reset", token, timeout=60)
    assert status == 200, status
    print(f"đặt lại dữ liệu: {cold:.0f} ms")
    for _ in range(4):  # làm ấm Lambda, kết nối và bộ nhớ đệm bảng tra
        call_api(base, "GET", "/overview", token)
    time.sleep(2)

    started = int(time.time() * 1000)
    overview: list[float] = []
    for _ in range(args.gets):
        status, body, ms = call_api(base, "GET", "/overview", token)
        assert status == 200, body
        overview.append(ms)

    confirms: list[float] = []
    actions: list[float] = []
    params = {
        "kind": "expense",
        "amount_vnd": 1_000,
        "jar": "di_lai",
        "tx_type": "public_transport",
    }
    for i in range(args.writes):
        p = {**params, "client_ref": f"measure-{started}-{i}"}
        s1, conf, m1 = call_api(
            base, "POST", "/confirmations", token, {"tool": "record_transaction", "params": p}
        )
        assert s1 == 200, conf
        s2, rec, m2 = call_api(
            base, "POST", "/actions", token,
            {"tool": "record_transaction", "params": conf["params"], "confirm_token": conf["confirm_token"]},
        )  # fmt: skip
        assert s2 == 200, rec
        confirms.append(m1)
        actions.append(m2)
    finished = int(time.time() * 1000)

    call_api(base, "POST", "/demo/reset", token, timeout=60)
    print("--- phía máy gọi (qua Internet tới API Gateway) ---")
    print(line("GET /overview", overview))
    print(line("POST /confirmations (record_transaction)", confirms))
    print(line("POST /actions (record_transaction)", actions))
    print(line("luồng ghi (hai bước)", [a + b for a, b in zip(confirms, actions, strict=True)]))
    time.sleep(8)  # log CloudWatch có độ trễ vài giây
    side = lambda_side(sess, started - 1000, finished + 1000)
    print("--- phía Lambda (log rest_request, ms trong handler) ---")
    for route in ("GET /overview", "POST /confirmations", "POST /actions"):
        print(line(route, side.get(route, [])))
    ov = side.get("GET /overview", [])
    if ov:
        verdict = "ĐẠT" if pct(ov, 95) < 300 else "CHƯA ĐẠT"
        print(f"mục tiêu p95 GET /overview < 300 ms phía Lambda: {pct(ov, 95):.0f} ms -> {verdict}")
        return 0 if pct(ov, 95) < 300 else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
