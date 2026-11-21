"""Client httpx chung cho các phép đo (không ghi token ra file)."""
import json, os, time, urllib.parse, uuid
import httpx

R = "ap-southeast-1"
def load_state(path):
    d = {}
    for line in open(path, encoding="utf-8"):
        if "=" in line:
            k, v = line.strip().split("=", 1); d[k] = v.strip("'")
    return d

STATE = load_state(os.environ["SPIKE_STATE"])
TOKENS = json.load(open(os.environ["SPIKE_TOKENS"]))
ARN = f"arn:aws:bedrock-agentcore:{R}:{STATE['ACC']}:runtime/{os.environ.get('SPIKE_RT', STATE['RT'])}"
URL = f"https://bedrock-agentcore.{R}.amazonaws.com/runtimes/{urllib.parse.quote(ARN, safe='')}/invocations?qualifier=DEFAULT"
SESSION_HDR = "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"

def body(fp=None, thread=None, prompt="hi"):
    return {"threadId": thread or "t-" + uuid.uuid4().hex[:6], "runId": "r-" + uuid.uuid4().hex[:6], "state": {},
            "messages": [{"id": "m1", "role": "user", "content": prompt}], "tools": [], "context": [],
            "forwardedProps": fp or {"chunks": 3, "delay": 0.3}}

def call(session=None, token_key="a", fp=None, extra=None, thread=None, prompt="hi", no_auth=False, timeout=120, client=None):
    """Trả về dict: status, ttfb (tới byte đầu), t_first_event, events[(t,type)], info (CUSTOM spike.info), hdrs, total, raw."""
    h = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if not no_auth:
        h["Authorization"] = "Bearer " + TOKENS[token_key]
    if session is not None:
        h[SESSION_HDR] = session
    h.update(extra or {})
    t0 = time.perf_counter(); out = {"events": [], "info": None}
    c = client or httpx.Client(timeout=timeout)
    with c.stream("POST", URL, headers=h, json=body(fp, thread, prompt)) as r:
        out["status"] = r.status_code
        out["hdrs"] = {k.lower(): v for k, v in r.headers.items()}
        out["t_headers"] = time.perf_counter() - t0
        buf = ""
        for chunk in r.iter_text():
            if "ttfb" not in out: out["ttfb"] = time.perf_counter() - t0
            buf += chunk
            while "\n\n" in buf:
                frame, buf = buf.split("\n\n", 1)
                for line in frame.split("\n"):
                    if line.startswith("data:"):
                        try: ev = json.loads(line[5:])
                        except Exception: ev = {"type": "UNPARSEABLE"}
                        t = time.perf_counter() - t0
                        out["events"].append((round(t, 3), ev.get("type"), ev.get("delta") or ev.get("code") or ev.get("message")))
                        if ev.get("name") == "spike.info": out["info"] = ev["value"]
                        if "t_first_event" not in out: out["t_first_event"] = t
        if buf.strip(): out["raw"] = buf[:300]
    out["total"] = time.perf_counter() - t0
    return out
