"""Q5: header session id: độ dài, ký tự, vắng mặt, giữ trạng thái, đồng thời, khác người dùng."""
import uuid, json, threading, time, os, subprocess
from common_client import call, TOKENS, STATE, R
import httpx

def brief(r):
    i = r.get("info") or {}
    return {"status": r["status"], "pid": i.get("pid"), "n": i.get("invocation_n"),
            "resp_session_hdr": r["hdrs"].get("x-amzn-bedrock-agentcore-runtime-session-id"),
            "err": [e[1:] for e in r["events"] if e[1] == "RUN_ERROR"] or None}
print("== a. độ dài / ký tự session id")
for label, sid in [("1 ký tự", "a"), ("10 ký tự", "0123456789"), ("32 ký tự", "x" * 32), ("33 ký tự", "y" * 33),
                   ("36 (uuid)", str(uuid.uuid4())), ("100 ký tự", "z" * 100), ("256 ký tự", "w" * 256), ("257 ký tự", "v" * 257),
                   ("33 ký tự có khoảng trắng", "a b" * 11), ("33 ký tự có dấu / : _ -", "ab/cd:ef_gh-" * 3), ("33 ký tự unicode", "é" * 33)]:
    try:
        r = call(session=sid, fp={"chunks": 1, "delay": 0.05})
        b = brief(r); b["echoed_same"] = b["resp_session_hdr"] == sid
        print(f"  {label:28s}", b)
    except Exception as e:
        print(f"  {label:28s} EXC {type(e).__name__}: {str(e)[:120]}")
print("== b. không gửi session header")
rs = [call(session=None, fp={"chunks": 1, "delay": 0.05}) for _ in range(2)]
for r in rs: print("  ", brief(r))
print("== c. cùng session, gọi lại: trạng thái trong RAM")
sid = str(uuid.uuid4())
for k in range(4):
    r = call(session=sid, fp={"chunks": 1, "delay": 0.05}); print("  ", brief(r), "uptime", r["info"]["uptime_s"])
sid2 = str(uuid.uuid4()); r = call(session=sid2, fp={"chunks": 1, "delay": 0.05}); print("   session khác:", brief(r))
print("== d. song song cùng session (delay dài)")
sid = str(uuid.uuid4()); out = {}
def go(name, delay):
    out[name] = call(session=sid, fp={"chunks": 3, "delay": delay})
t1 = threading.Thread(target=go, args=("A", 2.0)); t1.start(); time.sleep(1.0)
t2 = threading.Thread(target=go, args=("B", 0.1)); t2.start(); t1.join(); t2.join()
for k, r in out.items(): print("  ", k, brief(r), "total", round(r["total"], 2))
print("== e. session do người dùng A tạo, người dùng B (token khác) dùng lại")
tokB = os.environ.get("SPIKE_TOKENS_B")
if tokB:
    TOKENS["b"] = json.load(open(tokB))["a"]
    sid = str(uuid.uuid4())
    ra = call(session=sid, fp={"chunks": 1, "delay": 0.05}); print("   A:", brief(ra))
    rb = call(session=sid, token_key="b", fp={"chunks": 1, "delay": 0.05}); print("   B cùng session:", brief(rb), rb["events"][:2])
    rb2 = call(session=str(uuid.uuid4()), token_key="b", fp={"chunks": 1, "delay": 0.05}); print("   B session mới:", brief(rb2))
    ra2 = call(session=sid, fp={"chunks": 1, "delay": 0.05}); print("   A quay lại:", brief(ra2))
