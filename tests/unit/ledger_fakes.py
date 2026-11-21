"""Đồ giả CHỈ dành cho unit test của ledger: kho dữ liệu trong bộ nhớ thay Aurora, kho `jti` giả,
đồng hồ cố định. Không được import từ mã sản phẩm (master-plan: "Không hardcode, không giả lập")."""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from yofina_core.clock import app_today
from yofina_core.confirm import ConfirmService
from yofina_core.errors import ErrorCode, YofinaError
from yofina_ledger.repo import JarView, MoveResult, ResetCounts
from yofina_ledger.service import LedgerService
from yofina_ledger.settings import LedgerSettings

KEY = b"khoa-unit-test-ledger"
NOW = datetime(
    2026, 12, 10, 3, 0, tzinfo=UTC
)  # giờ thật; với offset -19 thì ngày mô phỏng 21/11/2026

SETTINGS = LedgerSettings(
    offer_ttl_seconds=600,
    move_max_amount_vnd=50_000_000,
    transactions_default_limit=20,
    transactions_max_limit=50,
    app_timezone="Asia/Ho_Chi_Minh",
    demo_anchor_date=date(2026, 11, 21),
)

JARS = [
    ("an_uong", "Ăn uống", "violet", "utensils", 380_000, 30),
    ("giai_tri", "Giải trí", "orchid", "gamepad", 760_000, 7),
    ("di_lai", "Đi lại", "sky", "bus", 640_000, 7),
]


class Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class MemoryJtiStore:
    def __init__(self) -> None:
        self.used: set[str] = set()
        self._lock = threading.Lock()

    def consume(self, jti: str, exp: int) -> None:
        with self._lock:
            if jti in self.used:
                raise YofinaError(ErrorCode.TOKEN_REUSED, "Token xác nhận đã được dùng.")
            self.used.add(jti)


class FakeRepo:
    """Cùng giao diện với `LedgerRepo`, dữ liệu theo từng user_id (tách người dùng như RLS)."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.users: dict[str, dict[str, Any]] = {}
        self.audits: list[dict[str, Any]] = []
        self.moves: list[MoveResult] = []
        self.resets: list[dict[str, Any]] = []
        self.transactions: dict[str, list[dict[str, Any]]] = {}
        self.turns: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
        self._turn_seq = 0
        # confirm_resolutions: (user_id, confirm_block_id) là khóa unique như bảng thật
        self.resolved: dict[str, dict[str, dict[str, Any]]] = {}

    def add_user(self, uid: str, offset: int = -19, jars=JARS) -> None:
        self.users[uid] = {
            "offset": offset,
            "jars": {
                code: {
                    "code": code,
                    "name": name,
                    "color_key": color,
                    "icon_key": icon,
                    "balance_vnd": Decimal(bal),
                    "split_percent": Decimal(pct),
                    "sort_order": i,
                }
                for i, (code, name, color, icon, bal, pct) in enumerate(jars)
            },
        }
        self.transactions[uid] = []

    def jar_view(self, uid: str) -> JarView:
        u = self.users.get(uid)
        if not u:
            return JarView(None, ())
        jars = sorted(u["jars"].values(), key=lambda j: (j["sort_order"], j["code"]))
        return JarView(u["offset"], tuple(jars))

    def clock_offset(self, uid: str) -> int:
        return self.users[uid]["offset"] if uid in self.users else 0

    def query_transactions(self, uid, *, jar, from_date, to_date, limit):
        rows = [
            t
            for t in self.transactions.get(uid, [])
            if (jar is None or t["jar_code"] == jar)
            and (from_date is None or t["app_date"] >= from_date)
            and (to_date is None or t["app_date"] <= to_date)
        ]
        rows.sort(key=lambda t: t["occurred_at"], reverse=True)
        return rows[:limit]

    def apply_move(
        self,
        uid,
        *,
        from_jar,
        to_jar,
        amount_vnd,
        now,
        tz,
        trace_id,
        channel,
        jti=None,
        claim=None,
    ):
        u = self.users.get(uid)
        if not u or from_jar not in u["jars"] or to_jar not in u["jars"]:
            raise YofinaError(ErrorCode.JAR_NOT_FOUND, "Không tìm thấy hũ bạn chọn.")
        src, dst = u["jars"][from_jar], u["jars"][to_jar]
        if src["balance_vnd"] < amount_vnd:
            raise YofinaError(ErrorCode.INSUFFICIENT_FUNDS, "Không đủ số dư.")
        if claim and claim.confirm_block_id in self.resolved.get(uid, {}):
            # bảng thật: INSERT ... ON CONFLICT DO NOTHING không ra dòng -> rollback cả transaction
            raise YofinaError(ErrorCode.ALREADY_APPLIED, "Đề nghị này đã được thực hiện rồi.")
        src["balance_vnd"] -= amount_vnd
        dst["balance_vnd"] += amount_vnd
        tid = str(uuid.uuid4())
        app_date = app_today(u["offset"], now, tz)
        for code, sign in ((from_jar, -1), (to_jar, 1)):
            self.transactions[uid].append(
                {
                    "id": str(uuid.uuid4()),
                    "occurred_at": now,
                    "app_date": app_date,
                    "kind": "transfer",
                    "jar_code": code,
                    "amount_vnd": Decimal(sign * amount_vnd),
                    "merchant": None,
                    "note": "chuyển hũ",
                    "transfer_id": tid,
                }
            )
        self.audits.append({"uid": uid, "outcome": "ok", "channel": channel, "jti": jti})
        res = MoveResult(
            transfer_id=tid,
            occurred_at=now,
            app_date=app_date,
            amount_vnd=amount_vnd,
            from_jar={
                "code": from_jar,
                "name": src["name"],
                "balance_vnd": int(src["balance_vnd"]),
            },
            to_jar={"code": to_jar, "name": dst["name"], "balance_vnd": int(dst["balance_vnd"])},
        )
        self.moves.append(res)
        if claim:
            self.resolved.setdefault(uid, {})[claim.confirm_block_id] = {
                "confirm_block_id": claim.confirm_block_id,
                "conversation_id": claim.conversation_id,
                "transfer_id": tid,
                "receipt": claim.receipt_for(res),
                "resolved_at": now,
            }
        return res

    def resolution(self, uid, confirm_block_id):
        return self.resolved.get(uid, {}).get(confirm_block_id)

    def resolutions(self, uid, conversation_id):
        return [
            r
            for r in self.resolved.get(uid, {}).values()
            if r["conversation_id"] == conversation_id
        ]

    # --- lượt hội thoại (tách theo user_id như RLS) ---
    def save_turn(self, uid, *, conversation_id, trace_id, user_text, assistant_text, blocks):
        self._turn_seq += 1
        store = self.turns.setdefault(uid, {})
        key = (conversation_id, trace_id)
        prev = store.get(key)
        store[key] = {
            "id": prev["id"] if prev else self._turn_seq,
            "conversation_id": conversation_id,
            "trace_id": trace_id,
            "user_text": user_text,
            "assistant_text": assistant_text,
            "created_at": self.clock(),
            "blocks": [(seq, dict(block)) for seq, block in blocks],
        }
        return len(blocks)

    def conversation(self, uid, conversation_id):
        rows = sorted(
            (
                t
                for t in self.turns.get(uid, {}).values()
                if t["conversation_id"] == conversation_id
            ),
            key=lambda t: t["id"],
        )
        blocks = [
            {"trace_id": t["trace_id"], "seq": seq, "block": block}
            for t in rows
            for seq, block in t["blocks"]
        ]
        return rows, blocks

    def list_conversations(self, uid, *, limit):
        groups: dict[str, list[dict[str, Any]]] = {}
        for t in sorted(self.turns.get(uid, {}).values(), key=lambda t: t["id"]):
            groups.setdefault(t["conversation_id"], []).append(t)
        out = [
            {
                "conversation_id": cid,
                "turns": len(ts),
                "last_activity_at": max(t["created_at"] for t in ts),
                "preview": ts[0]["user_text"],
            }
            for cid, ts in groups.items()
        ]
        out.sort(key=lambda r: r["last_activity_at"], reverse=True)
        return out[:limit]

    def audit(
        self, uid, *, trace_id, event_type, tool, outcome, code=None, params=None, details=None
    ):
        self.audits.append({"uid": uid, "outcome": outcome, "code": code, "params": params})

    def reset_user(self, uid, *, profile, jars, transactions, trace_id, details):
        self.resets.append(
            {"uid": uid, "profile": profile, "jars": jars, "transactions": transactions}
        )
        self.users[uid] = {
            "offset": profile["clock_offset_days"],
            "jars": {
                j["code"]: {
                    "code": j["code"],
                    "name": j["name"],
                    "color_key": j["color_key"],
                    "icon_key": j["icon_key"],
                    "balance_vnd": Decimal(j["balance"]),
                    "split_percent": Decimal(j["split"]),
                    "sort_order": j["sort_order"],
                }
                for j in jars
            },
        }
        self.transactions[uid] = []
        self.turns[uid] = {}
        self.resolved[uid] = {}
        return ResetCounts(len(jars), len(transactions))


def make_service(
    users: tuple[str, ...] = ("sub-minh", "sub-lan"),
) -> tuple[LedgerService, FakeRepo, Clock]:
    clock = Clock()
    repo = FakeRepo(clock)
    for u in users:
        repo.add_user(u)
    confirm = ConfirmService(
        lambda: KEY, MemoryJtiStore(), ttl_seconds=120, max_ttl_seconds=120, clock=clock
    )
    return LedgerService(repo, confirm, SETTINGS, clock=clock), repo, clock  # type: ignore[arg-type]


def gateway_context(tool: str | None) -> Any:
    custom = {"bedrockAgentCoreToolName": tool} if tool else {}
    return SimpleNamespace(client_context=SimpleNamespace(custom=custom))


def http_event(
    method: str,
    path: str,
    *,
    sub: str | None,
    body: Any = None,
    groups: str | None = None,
    headers: dict[str, str] | None = None,
    path_params: dict[str, str] | None = None,
    query: dict[str, str] | None = None,
) -> dict[str, Any]:
    import json

    claims: dict[str, str] = {}
    if sub:
        claims["sub"] = sub
    if groups:
        claims["cognito:groups"] = groups
    event: dict[str, Any] = {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "headers": headers or {},
        "requestContext": {
            "http": {"method": method, "path": path},
            "authorizer": {"jwt": {"claims": claims}},
        },
    }
    if body is not None:
        event["body"] = json.dumps(body)
    if path_params:
        event["pathParameters"] = path_params
    if query:
        event["queryStringParameters"] = query
    return event
