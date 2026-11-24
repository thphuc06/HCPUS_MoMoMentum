"""Tiêu chí 9 phase 5 ("Xóa dữ liệu của tôi") chạy thật trên PostgreSQL với KIỂU THAM SỐ như RDS Data API.

Bản giả `LocalRdsData` gửi chuỗi cho psycopg với kiểu `unknown`, nên Postgres tự ép sang kiểu của cột và câu `finished_at = :fin`
chạy được ở cục bộ. Data API thì gửi mọi `stringValue` không có `typeHint` dưới dạng `text` (datetime của `yofina_core.db` cũng là
`stringValue`), nên trên Aurora câu đó hỏng với SQLState 42804 (log `yofina-ledger` 24/11: `column "finished_at" is of type
timestamp with time zone but expression is of type text`) và cả lần xóa lùi ở bước Aurora. `TypedLocalRdsData` dưới đây gửi chuỗi
với kiểu `text` như Data API, để bắt đúng lớp lỗi này trước khi deploy.

Chạy cùng bộ local_pg (lệnh ở docstring của conftest.py): `pytest tests/local_pg/test_privacy_data_api_types.py`.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

import psycopg
import pytest
from conftest import NOW
from ledger_fakes import http_event
from local_data_api import LocalRdsData
from psycopg.types.string import StrBinaryDumper, StrDumper

from yofina_core.db import DataApi, DataApiSettings
from yofina_core.errors import YofinaError
from yofina_ledger import privacy_rest
from yofina_ledger.memory_store import MemoryStore
from yofina_ledger.privacy_rest import DeletionRepo, PrivacyService, S3Deleter
from yofina_ledger.rest_api import handle_http

MINH, LAN = "sub-minh", "sub-lan"
MEMORY_ID = "yofina_memory-AbCdEf1234"


class TypedLocalRdsData(LocalRdsData):
    """Như `LocalRdsData` nhưng chuỗi đi với kiểu `text` (không phải `unknown`), giống RDS Data API khi tham số không có `typeHint`:
    cột không phải text phải được `CAST` tường minh trong câu SQL."""

    def _connect(self, autocommit: bool) -> psycopg.Connection:
        conn = super()._connect(autocommit)
        conn.adapters.register_dumper(str, StrDumper)
        conn.adapters.register_dumper(str, StrBinaryDumper)
        return conn


class ClientError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.response = {"Error": {"Code": code, "Message": message}}


class NoEventsMemoryApi:
    """AgentCore Memory giả của một người chưa từng có sự kiện ngắn hạn (agent ghi bằng IngestData): có bản ghi dài hạn, còn
    ListSessions ném ResourceNotFoundException "Actor ... not found" như dịch vụ thật (log `yofina-ledger` 24/11)."""

    def __init__(self, records: dict[str, str]) -> None:
        self.records = dict(records)  # id -> namespace

    def list_memory_records(self, **kw: Any) -> dict[str, Any]:
        ids = sorted(r for r, ns in self.records.items() if ns.startswith(kw["namespacePath"]))
        return {
            "memoryRecordSummaries": [
                {
                    "memoryRecordId": r,
                    "namespaces": [self.records[r]],
                    "content": {"text": "x"},
                    "createdAt": NOW,
                }
                for r in ids
            ]
        }

    def batch_delete_memory_records(self, **kw: Any) -> dict[str, Any]:
        for r in kw["records"]:
            assert self.records.pop(r["memoryRecordId"]) == r["namespace"]
        return {
            "successfulRecords": [
                {"memoryRecordId": r["memoryRecordId"], "status": "SUCCEEDED"}
                for r in kw["records"]
            ]
        }

    def list_sessions(self, **kw: Any) -> dict[str, Any]:
        raise ClientError("ResourceNotFoundException", f"Actor {kw['actorId']} not found")


class FakeS3:
    def __init__(self, keys: list[str]) -> None:
        self.keys = list(keys)

    def list_objects_v2(self, **kw: Any) -> dict[str, Any]:
        return {
            "Contents": [{"Key": k} for k in self.keys if k.startswith(kw["Prefix"])],
            "IsTruncated": False,
        }

    def delete_objects(self, **kw: Any) -> dict[str, Any]:
        gone = {o["Key"] for o in kw["Delete"]["Objects"]}
        self.keys = [k for k in self.keys if k not in gone]
        return {}


def q(env, sql: str, *args) -> list[tuple]:
    with env.master() as m:
        return m.execute(sql, args).fetchall()


def snapshot(env, user: str) -> dict[str, int]:
    """Số dòng của `user` ở mọi bảng public có cột user_id (cùng cách duyệt của app_delete_user_data), trừ nhật ký xóa, và users."""
    tables = [
        r[0]
        for r in q(
            env,
            "SELECT c.table_name FROM information_schema.columns c JOIN information_schema.tables s "
            "ON s.table_schema = c.table_schema AND s.table_name = c.table_name "
            "WHERE c.table_schema = 'public' AND c.column_name = 'user_id' AND s.table_type = 'BASE TABLE' "
            "AND c.table_name <> 'data_deletions' ORDER BY 1",
        )
    ]
    out = {t: q(env, f"SELECT count(*) FROM {t} WHERE user_id = %s", user)[0][0] for t in tables}
    out["users"] = q(env, "SELECT count(*) FROM users WHERE id = %s", user)[0][0]
    return out


@pytest.fixture()
def typed(env, monkeypatch):
    """`minh` và `lan` vừa đặt lại; dịch vụ xóa dữ liệu đi qua DataApi có kiểu tham số như Data API thật."""
    env.reset(MINH)
    env.reset(LAN)
    with (
        env.master() as m
    ):  # nhật ký xóa không bị đặt lại; dòng do test khác để lại (kể cả `running`) làm lệch kết quả
        m.execute("DELETE FROM data_deletions WHERE user_id = ANY(%s)", ([MINH, LAN],))
    db = DataApi(
        DataApiSettings("arn:cluster", "arn:secret", "db"), client=TypedLocalRdsData(env.pg["dsn"])
    )  # type: ignore[arg-type]
    mem = NoEventsMemoryApi(
        {
            "mem-" + "a" * 40: f"/yofina/users/{MINH}/preferences/",
            "mem-" + "b" * 40: f"/yofina/users/{MINH}/sessions/s1/",
            "mem-" + "c" * 40: f"/yofina/users/{LAN}/preferences/",
        }
    )
    s3 = FakeS3([f"u/{MINH}/a.png", f"u/{LAN}/b.png"])
    svc = PrivacyService(
        repo=DeletionRepo(db),
        confirm=env.svc.confirm,
        memory=MemoryStore(MEMORY_ID, client=mem),
        s3=S3Deleter("yofina-ingest-test", "u/", client=s3),
        lease_seconds=120,
        now=env.clock,
    )
    monkeypatch.setattr(privacy_rest, "_SERVICE", svc)
    return env, db, mem, s3


def rest(env, method: str, path: str, sub: str, body=None) -> tuple[int, dict[str, Any]]:
    out = handle_http(http_event(method, path, sub=sub, body=body, headers={}), env.svc)
    return out["statusCode"], json.loads(out["body"])


def test_ban_gia_co_kieu_bat_duoc_loi_42804_cua_aurora(typed, caplog):
    """Bộ kiểm có ý nghĩa: đúng câu UPDATE cũ (không CAST) hỏng trên bản giả có kiểu, như trên Aurora; bản giả cũ thì cho qua."""
    env, db, *_ = typed
    old_sql = "UPDATE data_deletions SET finished_at = :fin WHERE user_id = :uid"
    with pytest.raises(YofinaError), db.transaction(MINH) as tx:
        tx.execute(old_sql, {"fin": NOW, "uid": MINH})
    assert any(
        "42804" in r.getMessage() or "is of type timestamp" in r.getMessage()
        for r in caplog.records
    )
    untyped = DataApi(
        DataApiSettings("arn:cluster", "arn:secret", "db"), client=LocalRdsData(env.pg["dsn"])
    )  # type: ignore[arg-type]
    with untyped.transaction(MINH) as tx:
        tx.execute(
            old_sql, {"fin": NOW, "uid": MINH}
        )  # bản giả cũ không thấy lỗi (đó là vì sao lỗi lọt tới Aurora)


def test_xoa_du_lieu_cua_toi_chay_that_tren_kieu_tham_so_cua_data_api(typed):
    """Tiêu chí 9: token -> S3 -> Memory (actor chưa có sự kiện) -> Aurora và chốt nhật ký, trên SQL thật với kiểu tham số thật."""
    env, _db, mem, s3 = typed
    before_minh, before_lan = snapshot(env, MINH), snapshot(env, LAN)
    assert before_minh["transactions"] > 0 and before_minh["users"] == 1
    req = {"tool": "delete_my_data", "params": {"scope": "all"}}

    status, issued = rest(env, "POST", "/me/delete-data/confirmations", MINH, req)
    assert status == 200, issued
    status, body = rest(
        env, "POST", "/me/delete-data", MINH, {**req, "confirm_token": issued["confirm_token"]}
    )
    assert status == 200, body
    assert body["status"] == "done" and body["finished_at"], body
    assert body["steps"] == {
        "s3": {"status": "done", "deleted": 1},
        "memory": {"status": "done", "deleted": 2},
        "aurora": {"status": "done", "deleted": sum(before_minh.values())},
    }
    after = snapshot(env, MINH)
    assert all(v == 0 for v in after.values()), {k: v for k, v in after.items() if v}
    assert snapshot(env, LAN) == before_lan
    assert s3.keys == [f"u/{LAN}/b.png"] and list(mem.records.values()) == [
        f"/yofina/users/{LAN}/preferences/"
    ]
    log = q(
        env,
        "SELECT id::text, status, finished_at, steps FROM data_deletions WHERE user_id = %s",
        MINH,
    )
    assert len(log) == 1 and log[0][0] == body["deletion_id"] and log[0][1] == "done"
    assert log[0][2] == NOW and log[0][3]["aurora"]["deleted"] == sum(before_minh.values())


def test_luu_tien_do_va_ket_thuc_loi_deu_chay_voi_kieu_tham_so_cua_data_api(typed):
    """Mọi câu của `DeletionRepo` (tạo, đọc lần đang chạy, lưu tiến độ với `finished_at` rỗng, chốt `failed` có `finished_at`):
    nhánh ghi lỗi trước đây gặp đúng lỗi 42804 nên dòng nhật ký kẹt `running` tới hết hạn thuê."""
    env, db, *_ = typed
    repo = DeletionRepo(db)
    steps = {k: {"status": "pending"} for k in ("s3", "memory", "aurora")}
    row = repo.create(MINH, steps, "t" * 32)
    assert row["status"] == "running" and row["finished_at"] is None
    assert repo.running(MINH)["id"] == row["id"]
    steps["s3"] = {"status": "done", "deleted": 0}
    row = repo.save(MINH, row["id"], steps, "running", None)
    assert row["status"] == "running" and row["finished_at"] is None
    steps["aurora"] = {"status": "failed", "error_code": "DATABASE_UNAVAILABLE"}
    fin = NOW + timedelta(seconds=5)
    row = repo.save(MINH, row["id"], steps, "failed", fin)
    assert row["status"] == "failed" and row["finished_at"] == fin
    assert repo.running(MINH) is None
    with pytest.raises(YofinaError):  # id của người khác hay không tồn tại: không cập nhật được
        repo.save(LAN, row["id"], steps, "failed", fin)
    assert (
        q(env, "SELECT count(*) FROM data_deletions WHERE id = %s", uuid.UUID(row["id"]))[0][0] == 1
    )
