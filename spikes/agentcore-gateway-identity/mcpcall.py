"""Client MCP (streamable HTTP) + lấy JWT Cognito. Mật khẩu user sinh ngẫu nhiên MỖI LẦN chạy, không lưu."""
import asyncio, base64, json, secrets, string, time
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from common import *

cog = client("cognito-idp")


def _pw():
    a = string.ascii_letters + string.digits
    return "Aa1!" + "".join(secrets.choice(a) for _ in range(16))


def tokens(users=("user-a", "user-b")):
    st = load_state()
    out = {}
    for u in users:
        pw = _pw()
        cog.admin_set_user_password(UserPoolId=st["pool_id"], Username=u, Password=pw, Permanent=True)
        r = cog.initiate_auth(ClientId=st["client_id"], AuthFlow="USER_PASSWORD_AUTH",
                              AuthParameters={"USERNAME": u, "PASSWORD": pw})["AuthenticationResult"]
        out[u] = {"access": r["AccessToken"], "id": r["IdToken"], "sub": claims(r["AccessToken"])["sub"]}
    return out


def claims(tok):
    p = tok.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))


class Gw:
    """Mở một phiên MCP tới gateway với Bearer token, gọi list/call, đo thời gian."""
    def __init__(self, url, token, extra_headers=None):
        self.url, self.h = url, {"Authorization": f"Bearer {token}", **(extra_headers or {})}

    async def _run(self, fn):
        async with streamablehttp_client(self.url, headers=self.h) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                return await fn(s)

    def list_tools(self):
        async def f(s):
            res = await s.list_tools()
            return res
        return asyncio.run(self._run(f))

    def call(self, name, args):
        async def f(s):
            return await s.call_tool(name, args)
        return asyncio.run(self._run(f))

    def timed_calls(self, name, args, n=5):
        """1 phiên, n lần call_tool liên tiếp: trả list ms (tools/call HTTP round trip). Gồm cả initialize."""
        async def f(s):
            ts = []
            for _ in range(n):
                t0 = time.perf_counter()
                await s.call_tool(name, args)
                ts.append((time.perf_counter() - t0) * 1000)
            return ts
        async def g():
            t0 = time.perf_counter()
            async with streamablehttp_client(self.url, headers=self.h) as (r, w, _):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    init = (time.perf_counter() - t0) * 1000
                    return init, await f(s)
        return asyncio.run(g())


def raw_post(url, token, body, extra=None):
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
         "Accept": "application/json, text/event-stream", **(extra or {})}
    t0 = time.perf_counter()
    r = httpx.post(url, headers=h, json=body, timeout=60)
    return r.status_code, r.text, (time.perf_counter() - t0) * 1000
