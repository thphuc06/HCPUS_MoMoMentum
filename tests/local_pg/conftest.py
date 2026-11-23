"""Hạ tầng test với PostgreSQL thật cục bộ (pgserver): chạy migration 0001..cuối + seed như migrator, rồi dựng `LedgerService`
thật (repo thật, SQL thật, RLS thật) với đồng hồ cố định, kho `jti` trong bộ nhớ và EventBridge giả ghi lại sự kiện.

Chạy (Python 3.12, tách khỏi `.venv` của dự án):

    uv run --python 3.12 --no-project --with pgserver --with "psycopg[binary]" --with pydantic --with pytest \
        --with jsonschema --with pyyaml --with referencing --with numpy --with scipy --with ruptures \
        pytest tests/local_pg -p no:cacheprovider

Đặt `PYTHONPATH` tới libs/yofina_core/src, gateway/tools/ledger và data (pytest.ini của thư mục này lo).
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import threading
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import psycopg
import pytest

REPO = Path(__file__).resolve().parents[2]
for extra in (
    "libs/yofina_core/src",
    "gateway/tools/ledger",
    "data",
    "pipelines/forecast",
    "ml",
    "tests/local_pg",
    "tests/unit",
    "tests/unit/pipeline",
):
    p = str(REPO / extra)
    if p not in sys.path:
        sys.path.insert(0, p)

from local_data_api import LocalRdsData  # noqa: E402

from yofina_core.confirm import ConfirmService  # noqa: E402
from yofina_core.db import DataApi, DataApiSettings  # noqa: E402
from yofina_core.errors import ErrorCode, YofinaError  # noqa: E402
from yofina_ledger.events import Event, EventPublisher  # noqa: E402
from yofina_ledger.repo import LedgerRepo  # noqa: E402
from yofina_ledger.service import LedgerService  # noqa: E402
from yofina_ledger.settings import LedgerSettings  # noqa: E402

KEY = b"khoa-local-pg"
NOW = datetime(
    2026, 12, 10, 3, 0, tzinfo=UTC
)  # giờ thật; offset -19 thì ngày mô phỏng là 21/11/2026
ANCHOR = date(2026, 11, 21)
APP_PASSWORD = "local-test-only"

SETTINGS = LedgerSettings(
    offer_ttl_seconds=600,
    move_max_amount_vnd=50_000_000,
    transactions_default_limit=20,
    transactions_max_limit=50,
    app_timezone="Asia/Ho_Chi_Minh",
    demo_anchor_date=ANCHOR,
    transaction_max_amount_vnd=50_000_000,
    salary_deviation_ask_percent=__import__("decimal").Decimal("10"),
    default_credit_limit_vnd=3_000_000,
    default_display_name="Bạn",
    forecast_freshness_seconds=900,
    proactive_obligation_days=3,
    reference_cache_seconds=300,
    event_bus_name="test-bus",
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RecordingEvents(EventPublisher):
    """Publisher giả: ghi lại sự kiện thay vì gọi EventBridge (chỉ dùng trong test)."""

    def __init__(self) -> None:
        super().__init__("test-bus")
        self.sent: list[Event] = []
        self.fail = False

    def publish(self, events, *, trace_id=None) -> bool:  # type: ignore[override]
        items = list(events)
        if self.fail:
            return False
        self.sent.extend(items)
        return True


class MemoryJti:
    def __init__(self) -> None:
        self.used: set[str] = set()
        self._lock = threading.Lock()

    def consume(self, jti: str, exp: int) -> None:
        with self._lock:
            if jti in self.used:
                raise YofinaError(ErrorCode.TOKEN_REUSED, "Token xác nhận đã được dùng.")
            self.used.add(jti)


class Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture(scope="session")
def pg():
    """Postgres cục bộ đã có schema, seed và role `yofina_app`; trả DSN của role ứng dụng."""
    import pgserver

    sqlsplit = _load("sqlsplit", REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py")
    data_dir = tempfile.mkdtemp(prefix="pgdata_ledger_")
    srv = pgserver.get_server(data_dir, cleanup_mode="stop")
    uri = srv.get_uri()
    with psycopg.connect(uri, autocommit=True) as master:
        for f in [
            *sorted((REPO / "db/migrations").glob("*.sql")),
            *sorted((REPO / "db/seed").glob("*.sql")),
        ]:
            stmts = sqlsplit.split_migration(f.read_text(encoding="utf-8"))
            with master.transaction():
                for s in stmts:
                    master.execute(s)
            if f.parent.name == "migrations" and f.name.startswith("0001"):
                master.execute(f"ALTER ROLE yofina_app WITH PASSWORD '{APP_PASSWORD}'")
    host_port = uri.split("@")[-1].split("/")[0] if "@" in uri else None
    base = psycopg.conninfo.conninfo_to_dict(uri)
    dsn = psycopg.conninfo.make_conninfo(
        **{
            **base,
            "user": "yofina_app",
            "password": APP_PASSWORD,
            "dbname": base.get("dbname", "postgres"),
        }
    )
    del host_port
    yield {"dsn": dsn, "master": uri}
    srv.cleanup()


@pytest.fixture()
def env(pg):
    """Mỗi test một môi trường: dịch vụ ledger thật trên Postgres, đồng hồ cố định, sự kiện ghi lại."""
    client = LocalRdsData(pg["dsn"])
    db = DataApi(DataApiSettings("arn:cluster", "arn:secret", "db"), client=client)  # type: ignore[arg-type]
    repo = LedgerRepo(db)
    clock = Clock()
    ev = RecordingEvents()
    confirm = ConfirmService(
        lambda: KEY, MemoryJti(), ttl_seconds=120, max_ttl_seconds=120, clock=clock
    )
    svc = LedgerService(repo, confirm, SETTINGS, clock=clock, events=ev)
    return Env(svc, repo, db, client, clock, ev, pg)


class Env:
    def __init__(self, svc, repo, db, client, clock, events, pg) -> None:
        self.svc: LedgerService = svc
        self.repo: LedgerRepo = repo
        self.db: DataApi = db
        self.client = client
        self.clock = clock
        self.events: RecordingEvents = events
        self.pg: dict[str, Any] = pg

    def master(self):
        return psycopg.connect(self.pg["master"], autocommit=True)

    def reset(self, user: str, persona: str | None = None) -> dict[str, Any]:
        """Đặt lại về persona; mặc định lấy từ tên người dùng thử (`sub-lan` là persona lan, còn lại minh)."""
        name = persona or user.removeprefix("sub-")
        return self.svc.reset_demo(
            user, name if name in ("minh", "lan", "khoa") else "minh", trace_id="t" * 8
        )

    def act(self, user: str, tool: str, params: dict[str, Any], **kw: Any):
        """Luồng đủ: cấp token rồi thực hiện. Trả khối biên nhận (dict gửi ra ngoài)."""
        from yofina_core.blocks import block_to_wire

        issued = self.svc.issue_confirmation(
            user, tool=tool, params=params, client_params_hash=None, trace_id="abc12345", **kw
        )
        block = self.svc.apply_action(
            user,
            tool,
            issued.params,
            issued.token,
            trace_id="abc12345",
            channel="rest",
            source_tool="rest:POST /actions",
            **kw,
        )
        return block_to_wire(block)
