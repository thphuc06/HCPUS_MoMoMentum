# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.28"]
# ///
"""Gửi một request AG-UI tới agent đang chạy và in các event SSE kèm mốc thời gian.

    uv run scripts/agent_call_local.py --message "số dư các hũ của mình"
    uv run scripts/agent_call_local.py --url https://bedrock-agentcore.../invocations?qualifier=DEFAULT --token <access token> --message "..."
    uv run scripts/agent_call_local.py --warmup                     # request làm nóng (không gọi model)
    uv run scripts/agent_call_local.py --history history.json --message "..."   # gửi lại các tin trước (mảng AG-UI messages)

Không có `--token` thì tự tạo một JWT KHÔNG KÝ có `sub` = `--sub` (chỉ dùng khi chạy local, nơi không có
JWT authorizer của Runtime; agent chỉ giải mã `sub`, không kiểm chữ ký). Đầu ra: từng event, rồi tóm tắt
(thời gian tới event đầu, tổng thời gian, đếm theo loại, số lượt gọi model của lượt).
"""

from __future__ import annotations

import argparse
import base64
import collections
import json
import pathlib
import sys
import time
import uuid

import httpx

for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace")


def unsigned_jwt(sub: str) -> str:
    def seg(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{seg({'alg': 'none', 'typ': 'JWT'})}.{seg({'sub': sub, 'token_use': 'access'})}.local"


def describe(ev: dict) -> str:
    t = ev["type"]
    if t == "ACTIVITY_SNAPSHOT":
        c = ev["content"]
        d = c.get("data", {})
        extra = ""
        if c["type"] == "jar_summary":
            extra = f"{len(d['jars'])} hũ, tổng {d['jars_total_vnd']:,} VND".replace(",", ".")
        elif c["type"] == "confirm":
            extra = d["summary"]
        elif c["type"] == "notice":
            extra = f"{d['kind']}/{d.get('code')}: {d['message'][:70]}"
        return f"block={c['type']} id={ev['messageId'][:40]} {extra}"
    if t == "TOOL_CALL_START":
        return ev["toolCallName"]
    if t == "TOOL_CALL_ARGS":
        return ev["delta"]
    if t == "TOOL_CALL_RESULT":
        return ev["content"][:150]
    if t == "TEXT_MESSAGE_CONTENT":
        return repr(ev["delta"])
    if t == "RUN_FINISHED":
        return (
            "result="
            + json.dumps(ev.get("result"), ensure_ascii=False)
            + " usage="
            + json.dumps(
                [
                    (u["model"].split(".")[-1], u["inputTokens"], u["outputTokens"])
                    for u in ev.get("usage") or []
                ],
                ensure_ascii=False,
            )
        )
    if t == "RUN_ERROR":
        return f"{ev.get('code')}: {ev['message']}"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--url", default="http://127.0.0.1:8080/invocations")
    ap.add_argument("--message", default="")
    ap.add_argument("--history", help="file JSON: mảng messages AG-UI đứng trước câu hỏi")
    ap.add_argument("--token", help="access token Cognito (mặc định: JWT không ký chỉ dùng local)")
    ap.add_argument("--sub", default="local-dev-user")
    ap.add_argument(
        "--session", default=str(uuid.uuid4()), help="session id (>= 33 ký tự theo Runtime)"
    )
    ap.add_argument("--warmup", action="store_true")
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("--quiet", action="store_true", help="chỉ in tóm tắt")
    args = ap.parse_args()

    messages = (
        json.loads(pathlib.Path(args.history).read_text(encoding="utf-8")) if args.history else []
    )
    if args.message:
        messages.append(
            {"id": f"u-{uuid.uuid4().hex[:8]}", "role": "user", "content": args.message}
        )
    body = {
        "threadId": args.session,
        "runId": f"run-{uuid.uuid4().hex[:8]}",
        "state": {},
        "messages": messages,
        "tools": [],
        "context": [],
        "forwardedProps": {"warmup": True} if args.warmup else {},
    }
    headers = {
        "Authorization": f"Bearer {args.token or unsigned_jwt(args.sub)}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": args.session,
        "traceparent": f"00-{uuid.uuid4().hex}-{uuid.uuid4().hex[:16]}-01",
    }
    counts: collections.Counter[str] = collections.Counter()
    first_ms = None
    t0 = time.perf_counter()
    last: dict = {}
    with (
        httpx.Client(timeout=args.timeout) as client,
        client.stream("POST", args.url, json=body, headers=headers) as resp,
    ):
        print(f"HTTP {resp.status_code} {resp.headers.get('content-type')}")
        if resp.status_code != 200:
            print(resp.read().decode("utf-8", "replace"))
            return 1
        buf = ""
        for chunk in resp.iter_text():
            buf += chunk
            while "\n\n" in buf:
                raw, buf = buf.split("\n\n", 1)
                if not raw.startswith("data: "):
                    continue
                ev = json.loads(raw[6:])
                ms = int((time.perf_counter() - t0) * 1000)
                first_ms = ms if first_ms is None else first_ms
                counts[ev["type"]] += 1
                last = ev
                if not args.quiet:
                    print(f"{ms:6d} ms  {ev['type']:<22} {describe(ev)}")
    total = int((time.perf_counter() - t0) * 1000)
    print(
        f"\nevent đầu sau {first_ms} ms, xong sau {total} ms, {sum(counts.values())} event: {dict(counts)}"
    )
    ok = last.get("type") in {"RUN_FINISHED", "RUN_ERROR"} and sum(counts.values()) > 0
    if not ok:
        print("LỖI: luồng rỗng hoặc không có sự kiện kết thúc", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
