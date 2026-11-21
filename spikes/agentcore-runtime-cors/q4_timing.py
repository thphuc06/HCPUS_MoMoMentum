"""Q4: độ trễ tới event đầu: cold (session mới = microVM mới) vs warm (cùng session)."""
import sys, time, uuid, json, statistics as st
from common_client import call
N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
res = {"cold": [], "warm": []}
for i in range(N):
    sid = str(uuid.uuid4())
    r = call(session=sid, fp={"chunks": 3, "delay": 0.3})
    res["cold"].append({"ttfb": r["ttfb"], "first_event": r["t_first_event"], "pid": r["info"]["pid"], "n": r["info"]["invocation_n"], "uptime_s": r["info"]["uptime_s"]})
    for j in range(N):
        r2 = call(session=sid, fp={"chunks": 3, "delay": 0.3})
        res["warm"].append({"ttfb": r2["ttfb"], "first_event": r2["t_first_event"], "pid": r2["info"]["pid"], "n": r2["info"]["invocation_n"]})
        if j == N - 1 and i == 0:
            print("example events (last warm call):", r2["events"])
    time.sleep(1)
for k, v in res.items():
    xs = [x["first_event"] for x in v]
    print(k, "first_event s:", [round(x, 2) for x in xs], "median", round(st.median(xs), 2), "min", round(min(xs), 2), "max", round(max(xs), 2))
print("cold pids", [x["pid"] for x in res["cold"]], "uptime at first call", [x["uptime_s"] for x in res["cold"]])
json.dump(res, open(sys.argv[2] if len(sys.argv) > 2 else "out/q4_timing.json", "w"), indent=1)
