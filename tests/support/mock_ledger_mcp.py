"""MCP server local CHỈ để dev/test agent khi chưa có Gateway thật. KHÔNG nằm trong gói sản phẩm.

Mô phỏng đúng *dáng* của Gateway + Lambda `ledger`, không phải logic nghiệp vụ thật:
- tên tool có tiền tố target như Gateway: `ledger___get_jar_balances`, `ledger___query_transactions`,
  `ledger___move_between_jars`;
- yêu cầu header `Authorization: Bearer <jwt>` (thiếu thì 401 như JWT authorizer của Gateway) và ghi lại
  `sub` của token để kiểm chứng agent chuyển token nguyên vẹn;
- kết quả đúng `contracts/tools/ledger.results.schema.json`, dữ liệu hũ lấy từ fixture
  `contracts/fixtures/tools/get_jar_balances.ok.json` (số dư của hũ KHÔNG đổi: mock không ghi gì);
- `move_between_jars` không token -> `NEEDS_CONFIRMATION` (tính bản xem trước và `params_hash` bằng
  `yofina_core`); có token -> `ERROR TOKEN_INVALID` (mock không kiểm token); số tiền vượt hạn mức
  `YOFINA_MOCK_MAX_AMOUNT` -> lỗi giao thức JSON-RPC -32002 như Cedar `ENFORCE` từ chối.

Chạy:  uv run python tests/support/mock_ledger_mcp.py --port 8201   ->  http://127.0.0.1:8201/mcp
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError

from yofina_core.confirm import ParamsError, normalize_move_params, params_hash
from yofina_core.money import format_vnd

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "contracts" / "fixtures" / "tools"
DENIED_CODE = -32002

# Ghi lại những gì server thấy (để test kiểm chứng): sub của từng request và tham số của từng lần gọi tool.
SEEN: dict[str, list[Any]] = {"subs": [], "calls": []}


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _jwt_sub(authorization: str) -> str | None:
    try:
        seg = authorization.split(" ", 1)[1].split(".")[1]
        return json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))).get("sub")
    except (IndexError, ValueError):
        return None


server = MCPServer("yofina-ledger-dev")


def _jars() -> dict[str, Any]:
    base = _load("get_jar_balances.ok.json")
    return {"as_of": _iso(_now()), "app_date": base["app_date"], "data": base["data"]}


@server.tool(name="ledger___get_jar_balances")
def get_jar_balances(user_id: str | None = None) -> dict[str, Any]:
    """Số dư các hũ (dữ liệu fixture)."""
    SEEN["calls"].append(("get_jar_balances", {"user_id": user_id}))
    return {"status": "OK", **_jars()}


@server.tool(name="ledger___query_transactions")
def query_transactions(
    user_id: str | None = None,
    jar: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Giao dịch gần đây (dữ liệu fixture)."""
    SEEN["calls"].append(
        (
            "query_transactions",
            {"jar": jar, "from_date": from_date, "to_date": to_date, "limit": limit},
        )
    )
    base = _load("query_transactions.ok.json")
    rows = [t for t in base["data"]["transactions"] if jar in (None, t.get("jar"))]
    rows = [
        t
        for t in rows
        if (not from_date or t["app_date"] >= from_date)
        and (not to_date or t["app_date"] <= to_date)
    ]
    cap = limit or 20
    return {
        "status": "OK",
        "as_of": _iso(_now()),
        "app_date": base["app_date"],
        "data": {"transactions": rows[:cap], "has_more": len(rows) > cap},
    }


def _error(code: str, message: str) -> dict[str, Any]:
    return {"status": "ERROR", "code": code, "message": message}


@server.tool(name="ledger___move_between_jars")
def move_between_jars(
    from_jar: str,
    to_jar: str,
    amount_vnd: int,
    confirm_token: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Chuyển tiền giữa hai hũ: không token thì chỉ trả NEEDS_CONFIRMATION."""
    SEEN["calls"].append(
        (
            "move_between_jars",
            {
                "from_jar": from_jar,
                "to_jar": to_jar,
                "amount_vnd": amount_vnd,
                "confirm_token": confirm_token,
                "user_id": user_id,
            },
        )
    )
    limit = int(os.environ.get("YOFINA_MOCK_MAX_AMOUNT", "5000000"))
    if (
        amount_vnd > limit
    ):  # mô phỏng Cedar ENFORCE: từ chối bằng lỗi giao thức, không phải kết quả tool
        raise MCPError(
            DENIED_CODE,
            "Tool Execution Denied: Tool call not allowed due to policy enforcement "
            "[Policy evaluation denied due to forbid_amount_limit]",
        )
    try:
        params = normalize_move_params(
            {"from_jar": from_jar, "to_jar": to_jar, "amount_vnd": amount_vnd}
        )
    except ParamsError as exc:
        return _error("PARAMS_INVALID", str(exc))
    if confirm_token:
        return _error("TOKEN_INVALID", "Mock dev không kiểm token xác nhận.")
    base = _jars()
    jars = {j["code"]: j for j in base["data"]["jars"]}
    for code in (params["from_jar"], params["to_jar"]):
        if code not in jars:
            return _error("JAR_NOT_FOUND", f"Không tìm thấy hũ '{code}'.")
    src, dst = jars[params["from_jar"]], jars[params["to_jar"]]
    if src["balance_vnd"] < params["amount_vnd"]:
        return _error("INSUFFICIENT_FUNDS", f"Hũ {src['name']} không đủ số dư để chuyển.")
    amount = params["amount_vnd"]
    return {
        "status": "NEEDS_CONFIRMATION",
        "as_of": base["as_of"],
        "app_date": base["app_date"],
        "data": {
            "tool": "move_between_jars",
            "params": params,
            "params_hash": params_hash("move_between_jars", params),
            "summary": f"Chuyển {format_vnd(amount)} từ {src['name']} sang {dst['name']}",
            "preview": {
                "from": {
                    "code": src["code"],
                    "name": src["name"],
                    "before_vnd": src["balance_vnd"],
                    "after_vnd": src["balance_vnd"] - amount,
                },
                "to": {
                    "code": dst["code"],
                    "name": dst["name"],
                    "before_vnd": dst["balance_vnd"],
                    "after_vnd": dst["balance_vnd"] + amount,
                },
            },
            "expires_at": _iso(_now() + timedelta(minutes=10)),
        },
    }


class AuthGate:
    """ASGI middleware: như JWT authorizer của Gateway, thiếu `Authorization: Bearer` thì 401."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
            auth = headers.get("authorization", "")
            if not auth.startswith("Bearer ") or _jwt_sub(auth) is None:
                body = json.dumps({"error": "Missing or invalid Authorization"}).encode()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
            SEEN["subs"].append(_jwt_sub(auth))
        await self.app(scope, receive, send)


def build_app() -> Any:
    return AuthGate(server.streamable_http_app())


class RunningMock:
    """Chạy mock trong một luồng nền (cho test); `stop()` để dừng."""

    def __init__(self, port: int) -> None:
        import uvicorn

        self.url = f"http://127.0.0.1:{port}/mcp"
        self._server = uvicorn.Server(
            uvicorn.Config(build_app(), host="127.0.0.1", port=port, log_level="error")
        )
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def start(self) -> RunningMock:
        self._thread.start()
        deadline = time.time() + 15
        while not self._server.started:
            if time.time() > deadline:
                raise RuntimeError("mock MCP không khởi động được")
            time.sleep(0.05)
        return self

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=10)


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8201)
    args = ap.parse_args()
    print(f"mock ledger MCP (CHỈ để dev) tại http://127.0.0.1:{args.port}/mcp", file=sys.stderr)
    uvicorn.run(build_app(), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
