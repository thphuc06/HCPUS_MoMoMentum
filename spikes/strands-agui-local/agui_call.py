"""Gọi một route AG-UI, lưu nguyên SSE ra file, in danh sách event.

Dùng: python agui_call.py <route> "<câu hỏi>" [--thread T] [--resume JSON] [--port P] [--out file] [--state JSON]
"""
import argparse, json, time, uuid
import httpx

ap = argparse.ArgumentParser()
ap.add_argument("route")
ap.add_argument("text", nargs="?", default="")
ap.add_argument("--thread", default="t-" + uuid.uuid4().hex[:6])
ap.add_argument("--port", type=int, default=8101)
ap.add_argument("--resume", default=None)
ap.add_argument("--state", default="{}")
ap.add_argument("--out", default=None)
ap.add_argument("--quiet", action="store_true")
a = ap.parse_args()

body = {"threadId": a.thread, "runId": "r-" + uuid.uuid4().hex[:6], "state": json.loads(a.state),
        "messages": [{"id": "m-" + uuid.uuid4().hex[:6], "role": "user", "content": a.text}] if a.text else [],
        "tools": [], "context": [], "forwardedProps": {}}
if a.resume:
    body["resume"] = json.loads(a.resume)
out = a.out or f"sse_{a.route.strip('/')}.txt"
raw = []
t0 = time.time()
with httpx.stream("POST", f"http://127.0.0.1:{a.port}/{a.route.strip(chr(47))}", json=body,
                  headers={"accept": "text/event-stream"}, timeout=180) as r:
    print("HTTP", r.status_code, r.headers.get("content-type"))
    for line in r.iter_lines():
        raw.append(line)
open(out, "w", encoding="utf-8").write("\n".join(raw) + "\n")
events = []
for line in raw:
    if line.startswith("data:"):
        try:
            events.append(json.loads(line[5:].strip()))
        except Exception:
            pass
print(f"{len(events)} events in {time.time()-t0:.1f}s -> {out}  (thread={a.thread})")
if not a.quiet:
    last = None
    n = 0
    for e in events + [{"type": None}]:
        if e["type"] == last:
            n += 1
            continue
        if last is not None:
            print(f"  {last} x{n}")
        last, n = e["type"], 1
