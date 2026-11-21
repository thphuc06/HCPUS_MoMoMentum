"""Lambda `yofina-migrator`: chạy trên master secret qua RDS Data API (Lambda nằm ngoài VPC).

Việc làm mỗi lần gọi:
1. Tạo hoặc đổi mật khẩu role ứng dụng (mặc định `yofina_app`, NOBYPASSRLS, không phải owner) từ secret của nó.
2. Tạo bảng `schema_migrations` nếu chưa có.
3. Chạy các migration chưa chạy, theo thứ tự `version`; mỗi file trong một transaction (DDL của PostgreSQL
   có transaction nên lỗi thì rollback sạch). Migration đã chạy mà nội dung đổi thì dừng, báo lỗi checksum.

Tách câu lệnh: theo dòng `-- @@` nếu file có (quy ước của db/migrations), nếu không thì theo dấu `;` (sqlsplit.py).
Tham số có tên trong SQL (`:app_password`, `:app_username`) lấy từ secret của role ứng dụng và chỉ gửi cho câu lệnh dùng nó.

Sự kiện vào: {"migrations": [{"version": "0001_core", "sql": "..."}], "dry_run": false}
`scripts/migrate.py` đọc `db/migrations/*.sql` rồi gọi hàm này.
Mọi lời gọi Data API retry khi DatabaseResumingException (cluster vừa được đánh thức).
"""
from __future__ import annotations

import json
import os
import re
import time

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from sqlsplit import checksum, named_params, split_migration

CLUSTER_ARN = os.environ["CLUSTER_ARN"]
DB_NAME = os.environ["DB_NAME"]
MASTER_SECRET_ARN = os.environ["MASTER_SECRET_ARN"]
APP_SECRET_ARN = os.environ["APP_SECRET_ARN"]
APP_ROLE = os.environ.get("APP_ROLE", "yofina_app")

_rds = boto3.client("rds-data", config=Config(retries={"max_attempts": 3, "mode": "standard"}))
_sm = boto3.client("secretsmanager")

_RESUME_DEADLINE_S = 120
_VERSION_RE = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")


def _retryable(err: ClientError) -> bool:
    code = err.response.get("Error", {}).get("Code", "")
    msg = err.response.get("Error", {}).get("Message", "")
    return code == "DatabaseResumingException" or "resuming after being auto paused" in msg or (
        code == "BadRequestException" and "Communications link failure" in msg
    )


def _call(fn, **kwargs):
    """Gọi Data API, retry khi cluster đang resume (tối đa ~2 phút)."""
    start = time.monotonic()
    delay = 1.0
    while True:
        try:
            return fn(**kwargs)
        except ClientError as e:
            if not _retryable(e) or time.monotonic() - start > _RESUME_DEADLINE_S:
                raise
            time.sleep(delay)
            delay = min(delay * 1.5, 5.0)


def _param(name: str, value: str) -> dict:
    return {"name": name, "value": {"stringValue": value}}


def _exec(sql: str, params: list | None = None, tx: str | None = None) -> dict:
    kwargs = dict(resourceArn=CLUSTER_ARN, secretArn=MASTER_SECRET_ARN, database=DB_NAME, sql=sql)
    if params:
        kwargs["parameters"] = params
    if tx:
        kwargs["transactionId"] = tx
    return _call(_rds.execute_statement, **kwargs)


def _app_secret() -> dict:
    secret = json.loads(_sm.get_secret_value(SecretId=APP_SECRET_ARN)["SecretString"])
    if secret["username"] != APP_ROLE:
        raise RuntimeError(f"secret của role ứng dụng có username {secret['username']!r}, mong đợi {APP_ROLE!r}")
    return secret


def ensure_app_role(secret: dict) -> str:
    """Tạo role ứng dụng nếu chưa có, đặt/đổi mật khẩu từ secret.

    Thuộc tính (NOSUPERUSER, NOBYPASSRLS...) chỉ đặt lúc CREATE: trên Aurora, master (rds_superuser) bị từ chối
    ALTER ROLE khi câu lệnh nhắc tới SUPERUSER/BYPASSRLS, kể cả để gỡ. Sau đó kiểm lại thuộc tính thật sự.
    Mật khẩu đi qua format(%L) nên được trích dẫn đúng, không ghép chuỗi tay.
    """
    password = secret["password"]
    exists = _exec("SELECT 1 FROM pg_roles WHERE rolname = :r", [_param("r", APP_ROLE)])["records"]
    template = (
        "ALTER ROLE %I WITH PASSWORD %L"
        if exists
        else "CREATE ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
    )
    ddl = _exec(
        "SELECT format(:t, CAST(:r AS text), CAST(:p AS text))",
        [_param("t", template), _param("r", APP_ROLE), _param("p", password)],
    )
    _exec(ddl["records"][0][0]["stringValue"])
    attrs = _exec(
        "SELECT rolcanlogin, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = :r", [_param("r", APP_ROLE)]
    )["records"][0]
    can_login, is_super, bypass = (attrs[0].get("booleanValue"), attrs[1].get("booleanValue"), attrs[2].get("booleanValue"))
    if is_super or bypass or not can_login:
        raise RuntimeError(f"role {APP_ROLE} có thuộc tính sai (login={can_login}, super={is_super}, bypassrls={bypass}); sửa tay bằng master")
    return "updated" if exists else "created"


def _applied() -> dict[str, str]:
    _exec(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())"
    )
    rows = _exec("SELECT version, checksum FROM schema_migrations ORDER BY version")["records"]
    return {r[0]["stringValue"]: r[1]["stringValue"] for r in rows}


def _apply_one(version: str, digest: str, statements: list[str], known_params: dict[str, str]) -> None:
    tx = _call(_rds.begin_transaction, resourceArn=CLUSTER_ARN, secretArn=MASTER_SECRET_ARN, database=DB_NAME)["transactionId"]
    try:
        for idx, stmt in enumerate(statements, 1):
            names = named_params(stmt)
            unknown = [n for n in names if n not in known_params]
            if unknown:
                raise RuntimeError(f"migration {version}, câu lệnh {idx}: tham số {unknown} migrator không cung cấp (có: {sorted(known_params)})")
            try:
                _exec(stmt, [_param(n, known_params[n]) for n in names], tx=tx)
            except ClientError as e:
                raise RuntimeError(f"migration {version}, câu lệnh {idx}/{len(statements)} lỗi: {e}\n--- {stmt[:300]}") from e
        _exec(
            "INSERT INTO schema_migrations (version, checksum) VALUES (:v, :c)",
            [_param("v", version), _param("c", digest)],
            tx=tx,
        )
        _call(_rds.commit_transaction, resourceArn=CLUSTER_ARN, secretArn=MASTER_SECRET_ARN, transactionId=tx)
    except BaseException:
        try:
            _rds.rollback_transaction(resourceArn=CLUSTER_ARN, secretArn=MASTER_SECRET_ARN, transactionId=tx)
        except ClientError:
            pass
        raise


def handler(event, context):
    migrations = sorted(event.get("migrations", []), key=lambda m: m["version"])
    dry_run = bool(event.get("dry_run", False))
    for m in migrations:
        if not _VERSION_RE.match(m["version"]):
            raise ValueError(f"version không hợp lệ: {m['version']!r}")

    secret = _app_secret()
    role_state = "dry_run" if dry_run else ensure_app_role(secret)
    # Tham số có tên mà file migration được phép dùng (chỉ gửi cho câu lệnh thật sự dùng nó).
    known_params = {"app_password": secret["password"], "app_username": secret["username"]}
    applied = _applied()
    result = {"role": role_state, "applied": [], "skipped": [], "pending": []}

    for m in migrations:
        version, sql = m["version"], m["sql"]
        digest = checksum(sql)
        if version in applied:
            if applied[version] != digest:
                raise RuntimeError(f"migration {version} đã chạy nhưng nội dung đã đổi (checksum khác); hãy thêm migration mới thay vì sửa file cũ")
            result["skipped"].append(version)
            continue
        statements = split_migration(sql)
        if dry_run:
            result["pending"].append({"version": version, "statements": len(statements)})
            continue
        started = time.monotonic()
        _apply_one(version, digest, statements, known_params)
        result["applied"].append({"version": version, "statements": len(statements), "seconds": round(time.monotonic() - started, 2)})
        print(json.dumps({"applied": version, "statements": len(statements)}))
    return result
