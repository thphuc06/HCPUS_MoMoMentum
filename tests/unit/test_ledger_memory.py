"""REST quyền riêng tư của ledger (phase 5, luồng B): `/memory*` và "Xóa dữ liệu của tôi" `/me/delete-data*`.

Client AgentCore Memory, S3 và kho `data_deletions` là đồ giả; tham số gửi AgentCore được kiểm bằng model dịch vụ thật của botocore
(Stubber). Kiểm: chỉ thấy và chỉ xóa được bản ghi của chính mình (namespace theo `sub` của JWT), xóa theo lô <= 100, idempotent, xóa
dữ liệu đúng người, token bắt buộc, chạy lại sau lỗi giữa chừng vẫn xong, `quiet_hours` cho cổng bản tin."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from conftest import OPENAPI_URI
from jsonschema import Draft202012Validator
from ledger_fakes import http_event, make_service

from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.memory import namespace_for, user_root
from yofina_core.privacy import DataDeletion
from yofina_ledger import privacy_rest
from yofina_ledger.memory_store import (
    MemoryStore,
    QuietHours,
    display_text,
    load_defaults,
    parse_quiet_hours,
    quiet_hours,
)
from yofina_ledger.privacy_rest import PrivacyService, S3Deleter
from yofina_ledger.rest_api import handle_http

MINH = "3f2a9c10-1b2c-4d5e-8f90-a1b2c3d4e5f6"
LAN = "9e8d7c6b-5a49-4382-9170-6f5e4d3c2b1a"
MEMORY_ID = "yofina_memory-AbCdEf1234"
T0 = datetime(2026, 11, 24, 3, 0, tzinfo=UTC)


def rid(n: int) -> str:
    return f"mem-{n:040d}"


class ClientError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeMemoryApi:
    """AgentCore Memory giả: bản ghi (id -> namespace, chữ), sự kiện theo (actor, session). Lọc theo namespace/namespacePath như dịch
    vụ; `leak` cố tình trả thêm bản ghi của người khác để kiểm mã tự lọc lại."""

    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.events: dict[tuple[str, str], list[str]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.leak: list[str] = []
        self.error: str | None = None
        self.op_errors: dict[str, str] = {}  # lỗi riêng một thao tác: tên thao tác -> mã lỗi
        self.fail_ids: set[str] = set()

    def add(
        self,
        n: int,
        kind: str,
        sub: str,
        text: str,
        session: str | None = None,
        record_type: str | None = None,
    ) -> str:
        r = rid(n)
        ns = (
            namespace_for(kind, sub, session)
            if kind == "session_summary"
            else namespace_for(kind, sub)
        )
        self.records[r] = {
            "ns": ns,
            "text": text,
            "created": T0 + timedelta(minutes=n),
            "record_type": record_type,
        }
        return r

    def _summary(self, r: str) -> dict[str, Any]:
        x = self.records[r]
        out = {
            "memoryRecordId": r,
            "content": {"text": x["text"]},
            "namespaces": [x["ns"]],
            "createdAt": x["created"],
            "memoryStrategyId": "s",
        }
        if x.get("record_type"):  # metadata hệ thống như dịch vụ thật trả (BASE hoặc FULL_SESSION)
            out["metadata"] = {
                "x-amz-agentcore-memory-recordType": {"stringValue": x["record_type"]}
            }
        return out

    def _maybe_fail(self, op: str, kw: dict[str, Any]) -> None:
        self.calls.append((op, kw))
        if self.error:
            raise ClientError(self.error)
        if op in self.op_errors:
            raise ClientError(self.op_errors[op])

    def list_memory_records(self, **kw: Any) -> dict[str, Any]:
        self._maybe_fail("list_memory_records", kw)
        if "namespace" in kw:
            ids = [r for r, x in self.records.items() if x["ns"] == kw["namespace"]]
        else:
            ids = [r for r, x in self.records.items() if x["ns"].startswith(kw["namespacePath"])]
        ids = sorted(ids) + [r for r in self.leak if r in self.records]
        start = int(kw.get("nextToken") or 0)
        page = ids[start : start + kw.get("maxResults", 20)]
        nxt = start + len(page)
        return {
            "memoryRecordSummaries": [self._summary(r) for r in page],
            **({"nextToken": str(nxt)} if nxt < len(ids) else {}),
        }

    def get_memory_record(self, **kw: Any) -> dict[str, Any]:
        self._maybe_fail("get_memory_record", kw)
        if kw["memoryRecordId"] not in self.records:
            raise ClientError("ResourceNotFoundException")
        return {"memoryRecord": self._summary(kw["memoryRecordId"])}

    def delete_memory_record(self, **kw: Any) -> dict[str, Any]:
        self._maybe_fail("delete_memory_record", kw)
        self.records.pop(kw["memoryRecordId"])
        return {"memoryRecordId": kw["memoryRecordId"]}

    def batch_delete_memory_records(self, **kw: Any) -> dict[str, Any]:
        self._maybe_fail("batch_delete_memory_records", kw)
        assert len(kw["records"]) <= 100
        ok, bad = [], []
        for r in kw["records"]:
            if r["memoryRecordId"] in self.fail_ids:
                bad.append(
                    {"memoryRecordId": r["memoryRecordId"], "status": "FAILED", "errorCode": 500}
                )
                continue
            assert self.records[r["memoryRecordId"]]["ns"] == r["namespace"]
            self.records.pop(r["memoryRecordId"], None)
            ok.append({"memoryRecordId": r["memoryRecordId"], "status": "SUCCEEDED"})
        return {"successfulRecords": ok, "failedRecords": bad}

    def list_sessions(self, **kw: Any) -> dict[str, Any]:
        self._maybe_fail("list_sessions", kw)
        sessions = sorted({s for (a, s) in self.events if a == kw["actorId"]})
        if not sessions:
            # Như dịch vụ thật (log yofina-ledger 24/11): actor chưa từng có sự kiện ngắn hạn thì "Actor ... not found".
            raise ClientError("ResourceNotFoundException")
        return {
            "sessionSummaries": [
                {"sessionId": s, "actorId": kw["actorId"], "createdAt": T0} for s in sessions
            ]
        }

    def list_events(self, **kw: Any) -> dict[str, Any]:
        self._maybe_fail("list_events", kw)
        ids = self.events.get((kw["actorId"], kw["sessionId"]), [])
        return {
            "events": [
                {
                    "eventId": e,
                    "memoryId": MEMORY_ID,
                    "actorId": kw["actorId"],
                    "sessionId": kw["sessionId"],
                    "eventTimestamp": T0,
                    "payload": [],
                }
                for e in ids
            ]
        }

    def delete_event(self, **kw: Any) -> dict[str, Any]:
        self._maybe_fail("delete_event", kw)
        self.events[(kw["actorId"], kw["sessionId"])].remove(kw["eventId"])
        return {"eventId": kw["eventId"]}


class FakeS3:
    def __init__(self, keys: list[str]) -> None:
        self.keys = set(keys)
        self.fail = False

    def list_objects_v2(self, **kw: Any) -> dict[str, Any]:
        if self.fail:
            raise ClientError("AccessDenied")
        found = sorted(k for k in self.keys if k.startswith(kw["Prefix"]))
        start = int(kw.get("ContinuationToken") or 0)
        page = found[start : start + kw["MaxKeys"]]
        more = start + len(page) < len(found)
        return {
            "Contents": [{"Key": k} for k in page],
            "IsTruncated": more,
            **({"NextContinuationToken": str(start + len(page))} if more else {}),
        }

    def delete_objects(self, **kw: Any) -> dict[str, Any]:
        for o in kw["Delete"]["Objects"]:
            self.keys.discard(o["Key"])
        return {}


class FakeDeletionRepo:
    """`data_deletions` và các bảng Aurora trong bộ nhớ: dữ liệu theo user_id, xóa như `app_delete_user_data` (chỉ khi có lần running
    của chính người đó), aurora + chốt nhật ký là một thao tác."""

    def __init__(self, clock: Any) -> None:
        self.clock = clock
        self.rows: dict[str, dict[str, Any]] = {}
        self.aurora: dict[str, int] = {MINH: 42, LAN: 17}
        self.crash_on_save: int | None = None
        self.fail_aurora = False
        self._n = 0
        self.saves = 0

    def running(self, uid: str) -> dict[str, Any] | None:
        return next(
            (dict(r) for r in self.rows.values() if r["uid"] == uid and r["status"] == "running"),
            None,
        )

    def create(self, uid: str, steps: dict[str, Any], trace_id: str) -> dict[str, Any]:
        assert self.running(uid) is None
        self._n += 1
        did = f"00000000-0000-4000-8000-{self._n:012d}"
        now = self.clock()
        self.rows[did] = {
            "id": did,
            "uid": uid,
            "status": "running",
            "steps": json.loads(json.dumps(steps)),
            "requested_at": now,
            "finished_at": None,
            "updated_at": now,
        }
        return dict(self.rows[did])

    def save(
        self, uid: str, did: str, steps: dict[str, Any], status: str, finished_at: Any
    ) -> dict[str, Any]:
        self.saves += 1
        if self.crash_on_save is not None and self.saves >= self.crash_on_save:
            raise RuntimeError("Lambda hết giờ giữa chừng")
        row = self.rows[did]
        assert row["uid"] == uid
        row.update(
            steps=json.loads(json.dumps(steps)),
            status=status,
            finished_at=finished_at,
            updated_at=self.clock(),
        )
        return dict(row)

    def delete_aurora_and_finish(self, uid: str, did: str, finish: Any) -> dict[str, Any]:
        row = self.rows[did]
        if row["uid"] != uid or row["status"] != "running":
            raise YofinaError(ErrorCode.PARAMS_INVALID, "không có lần xóa đang chạy")
        if self.fail_aurora:
            raise YofinaError(ErrorCode.DATABASE_UNAVAILABLE, "Aurora đang ngủ")
        n = self.aurora.pop(uid, 0)
        steps, status, fin = finish(n)
        row.update(
            steps=json.loads(json.dumps(steps)),
            status=status,
            finished_at=fin,
            updated_at=self.clock(),
        )
        return dict(row)


@pytest.fixture
def world(monkeypatch):
    svc, _repo, clock = make_service(users=(MINH, LAN))
    api = FakeMemoryApi()
    api.add(
        1,
        "preference",
        MINH,
        '{"context":"c","preference":"Đừng nhắc mình buổi sáng","categories":["nhắc"]}',
    )
    api.add(2, "fact", MINH, "Làm kỹ sư, sđt 0912345678")
    api.add(
        3,
        "session_summary",
        MINH,
        '<topic name="Du lịch">Hỏi về chuyến Đà Lạt</topic>',
        session="sess-1",
    )
    api.add(4, "preference", LAN, "Sở thích của Lan")
    api.events[(MINH, "sess-old")] = ["e1", "e2"]
    api.events[(LAN, "sess-lan")] = ["e9"]
    s3 = FakeS3([f"u/{MINH}/job-1", f"u/{MINH}/job-2", f"u/{LAN}/job-3", f"u/{MINH}x/job-4"])
    repo = FakeDeletionRepo(clock)
    store = MemoryStore(MEMORY_ID, client=api)
    privacy = PrivacyService(
        repo=repo,
        confirm=svc.confirm,
        memory=store,
        s3=S3Deleter("yofina-ingest-test", "u/", client=s3),
        lease_seconds=120,
        now=clock,
    )
    monkeypatch.setattr(privacy_rest, "_SERVICE", privacy)
    return {
        "svc": svc,
        "api": api,
        "s3": s3,
        "repo": repo,
        "clock": clock,
        "privacy": privacy,
        "store": store,
    }


def req(world, method, path, **kw):
    res = handle_http(http_event(method, path, **kw), world["svc"])
    return res["statusCode"], json.loads(res["body"])


@pytest.fixture
def schema_ok(registry):
    def run(name: str, instance):
        v = Draft202012Validator(
            {"$ref": f"{OPENAPI_URI}#/components/schemas/{name}"}, registry=registry
        )
        errors = [f"{list(e.path)}: {e.message}" for e in v.iter_errors(instance)]
        assert not errors, errors

    return run


# --- GET /memory --------------------------------------------------------------------------------------
def test_liet_ke_chi_ban_ghi_cua_chinh_minh_da_che(world, schema_ok):
    world["api"].leak = [rid(4)]  # dịch vụ lọc sai, trả cả bản ghi của Lan
    status, body = req(world, "GET", "/memory", sub=MINH)
    assert status == 200, body
    schema_ok("MemoryListResponse", body)
    texts = {r["kind"]: r["text"] for r in body["records"]}
    assert set(texts) == {"preference", "fact", "session_summary"}
    assert texts["preference"] == "Đừng nhắc mình buổi sáng"
    assert "0912345678" not in texts["fact"] and "[SĐT]" in texts["fact"]
    assert texts["session_summary"] == "Du lịch: Hỏi về chuyến Đà Lạt"
    assert "Lan" not in json.dumps(body, ensure_ascii=False)
    assert all(r["source"] == "conversation" for r in body["records"])
    assert [r["record_id"] for r in body["records"]] == [rid(3), rid(2), rid(1)]  # mới nhất trước
    op, kw = world["api"].calls[0]
    assert (
        op == "list_memory_records"
        and kw["namespacePath"] == user_root(MINH)
        and kw["memoryId"] == MEMORY_ID
    )


def test_sub_chi_tu_jwt_khong_tu_query(world):
    ev = http_event("GET", "/memory", sub=LAN, query={"user_id": MINH, "sub": MINH})
    body = json.loads(handle_http(ev, world["svc"])["body"])
    assert [r["text"] for r in body["records"]] == ["Sở thích của Lan"]


def test_loc_theo_kind_va_phan_trang(world, schema_ok):
    status, body = req(world, "GET", "/memory", sub=MINH, query={"kind": "session_summary"})
    assert status == 200 and [r["kind"] for r in body["records"]] == ["session_summary"]
    assert world["api"].calls[-1][1]["namespacePath"] == f"/yofina/users/{MINH}/sessions/"
    status, body = req(world, "GET", "/memory", sub=MINH, query={"limit": "1"})
    schema_ok("MemoryListResponse", body)
    assert len(body["records"]) == 1 and body["next_cursor"] == "1"
    status, body2 = req(
        world, "GET", "/memory", sub=MINH, query={"limit": "1", "cursor": body["next_cursor"]}
    )
    assert body2["records"][0]["record_id"] != body["records"][0]["record_id"]


@pytest.mark.parametrize(
    "query", [{"kind": "khac"}, {"limit": "0"}, {"limit": "101"}, {"limit": "x"}]
)
def test_tham_so_sai_400(world, query):
    status, body = req(world, "GET", "/memory", sub=MINH, query=query)
    assert status == 400 and body["error"]["code"] == "PARAMS_INVALID"


def test_memory_loi_thi_503(world, schema_ok):
    world["api"].error = "AccessDeniedException"
    status, body = req(world, "GET", "/memory", sub=MINH)
    assert status == 503 and body["error"]["code"] == "MEMORY_UNAVAILABLE"
    schema_ok("ErrorResponse", body)


def test_chua_cau_hinh_memory_thi_503(world, monkeypatch):
    world["privacy"].memory = MemoryStore(None, client=world["api"])
    status, body = req(world, "GET", "/memory", sub=MINH)
    assert status == 503 and body["error"]["code"] == "MEMORY_UNAVAILABLE"


# --- DELETE /memory/{record_id} -----------------------------------------------------------------------
def test_xoa_mot_ban_ghi_cua_minh(world, schema_ok):
    status, body = req(
        world, "DELETE", f"/memory/{rid(2)}", sub=MINH, path_params={"record_id": rid(2)}
    )
    assert status == 200 and body == {"record_id": rid(2), "deleted": True}
    schema_ok("MemoryRecordDeleteResponse", body)
    deletes = [kw for op, kw in world["api"].calls if op == "delete_memory_record"]
    assert deletes == [
        {"memoryId": MEMORY_ID, "memoryRecordId": rid(2), "namespace": namespace_for("fact", MINH)}
    ]
    assert rid(2) not in world["api"].records


def test_xoa_ban_ghi_cua_nguoi_khac_bi_404_va_khong_goi_xoa(world):
    status, body = req(
        world, "DELETE", f"/memory/{rid(4)}", sub=MINH, path_params={"record_id": rid(4)}
    )
    assert status == 404 and body["error"]["code"] == "MEMORY_RECORD_NOT_FOUND"
    assert rid(4) in world["api"].records
    assert not [c for c in world["api"].calls if c[0] == "delete_memory_record"]
    status, body2 = req(
        world, "DELETE", f"/memory/{rid(99)}", sub=MINH, path_params={"record_id": rid(99)}
    )
    assert (
        status == 404 and body2["error"]["code"] == body["error"]["code"]
    )  # của người khác cũng như không có


def test_xoa_mot_ban_ghi_id_sai_400(world):
    status, _body = req(world, "DELETE", "/memory/abc", sub=MINH, path_params={"record_id": "abc"})
    assert status == 400


# --- DELETE /memory ---------------------------------------------------------------------------------
def test_xoa_het_bo_nho_theo_lo_100_dung_nguoi_va_idempotent(world, schema_ok):
    api = world["api"]
    for i in range(10, 160):
        api.add(i, "preference", MINH, f"sở thích {i}")
    status, body = req(world, "DELETE", "/memory", sub=MINH)
    assert status == 200, body
    schema_ok("MemoryClearResponse", body)
    assert body == {"deleted_records": 153, "deleted_events": 2, "failed": 0}
    batches = [kw for op, kw in api.calls if op == "batch_delete_memory_records"]
    assert [len(b["records"]) for b in batches] == [100, 53]
    assert all(r["namespace"].startswith(user_root(MINH)) for b in batches for r in b["records"])
    assert {r for r, x in api.records.items()} == {rid(4)} and api.events[(LAN, "sess-lan")] == [
        "e9"
    ]  # của Lan còn nguyên
    status, again = req(world, "DELETE", "/memory", sub=MINH)
    assert again == {"deleted_records": 0, "deleted_events": 0, "failed": 0}


def test_xoa_het_loi_mot_phan_thi_bao_failed_goi_lai_xoa_not(world):
    api = world["api"]
    api.fail_ids = {rid(1)}
    _, body = req(world, "DELETE", "/memory", sub=MINH)
    assert body["failed"] == 1 and rid(1) in api.records
    api.fail_ids = set()
    _, body = req(world, "DELETE", "/memory", sub=MINH)
    assert body["deleted_records"] == 1 and body["failed"] == 0


def test_cors_va_method_delete_di_vao_dung_route(world):
    status, _ = req(world, "DELETE", "/memory/", sub=MINH)  # dấu / thừa bị bỏ như các route khác
    assert status == 200


def test_xoa_het_khi_chua_tung_co_su_kien_ngan_han_thi_200_khong_phai_500(world, schema_ok):
    """Nghiệm thu 24/11, lỗi 2: agent ghi bằng IngestData nên actor thường chưa có sự kiện nào, và ListSessions ném
    ResourceNotFoundException ("Actor ... not found"); trước đây lỗi thô này làm `DELETE /memory` trả 500 sau khi đã xóa bản ghi."""
    api = world["api"]
    api.events.clear()
    status, body = req(world, "DELETE", "/memory", sub=MINH)
    assert status == 200, body
    schema_ok("MemoryClearResponse", body)
    assert body == {"deleted_records": 3, "deleted_events": 0, "failed": 0}
    assert [op for op, _ in api.calls].count("list_sessions") == 1
    assert not any(op == "list_events" for op, _ in api.calls)


@pytest.mark.parametrize("op", ["list_sessions", "list_memory_records"])
def test_xoa_het_loi_khac_cua_dich_vu_thi_503_khong_phai_500(world, schema_ok, op):
    world["api"].op_errors[op] = (
        "ValidationException" if op == "list_memory_records" else "ThrottledException"
    )
    status, body = req(world, "DELETE", "/memory", sub=MINH)
    assert status == 503 and body["error"]["code"] == "MEMORY_UNAVAILABLE", body
    schema_ok("ErrorResponse", body)


def test_phien_het_su_kien_giua_chung_khong_tinh_la_loi(world):
    world["api"].op_errors["list_events"] = "ResourceNotFoundException"
    status, body = req(world, "DELETE", "/memory", sub=MINH)
    assert status == 200 and body["failed"] == 0 and body["deleted_events"] == 0


def test_tom_tat_phien_chi_hien_ban_ca_phien_khong_hien_hai_lan(world, schema_ok):
    """Nghiệm thu 24/11: mỗi tóm tắt phiên xuất hiện hai lần. Không phải ghi trùng: strategy tóm tắt sinh các đoạn (BASE, XML) VÀ một
    bản tóm tắt cả phiên (FULL_SESSION, markdown) cùng namespace (devguide summary-strategy, "Full session summary")."""
    api = world["api"]
    api.records.clear()
    chunk = api.add(
        5,
        "session_summary",
        MINH,
        '<topic name="Mô phỏng">\n- Người dùng hỏi mua tai nghe.\n</topic>\n<topic name="Thời gian">\n'
        "- Timestamp bản ghi: 1795505552861.\n</topic>",
        session="sess-2",
        record_type="BASE",
    )
    full = api.add(
        6,
        "session_summary",
        MINH,
        "## Mô phỏng mua tai nghe\n\n- **Yêu cầu:** Người dùng hỏi mua tai nghe. *(Nguồn: timestamp 1795505552861)*\n"
        "- Timestamp của bản ghi: 1795505552861.",
        session="sess-2",
        record_type="FULL_SESSION",
    )
    status, body = req(world, "GET", "/memory", sub=MINH)
    assert status == 200, body
    schema_ok("MemoryListResponse", body)
    assert [r["record_id"] for r in body["records"]] == [full]
    text = body["records"][0]["text"]
    assert text == "Mô phỏng mua tai nghe: - Yêu cầu: Người dùng hỏi mua tai nghe."
    assert "[STK]" not in text and "1795" not in text and "**" not in text and "#" not in text
    # xóa hết vẫn xóa cả đoạn tóm tắt lẫn bản cả phiên
    api.events.clear()
    _, cleared = req(world, "DELETE", "/memory", sub=MINH)
    assert cleared["deleted_records"] == 2 and chunk not in api.records and full not in api.records


# --- tham số khớp model dịch vụ thật (botocore Stubber) ----------------------------------------------
def test_tham_so_list_get_delete_batch_khop_model_botocore():
    import boto3
    from botocore.stub import Stubber

    client = boto3.client(
        "bedrock-agentcore",
        region_name="ap-southeast-1",
        aws_access_key_id="x",
        aws_secret_access_key="x",
    )
    stub = Stubber(client)
    ns = namespace_for("preference", MINH)
    summary = {
        "memoryRecordId": rid(1),
        "content": {"text": "x"},
        "memoryStrategyId": "s",
        "namespaces": [ns],
        "createdAt": T0,
    }
    stub.add_response(
        "list_memory_records",
        {"memoryRecordSummaries": [summary]},
        {"memoryId": MEMORY_ID, "maxResults": 100, "namespacePath": user_root(MINH)},
    )
    stub.add_response(
        "batch_delete_memory_records",
        {
            "successfulRecords": [{"memoryRecordId": rid(1), "status": "SUCCEEDED"}],
            "failedRecords": [],
        },
        {"memoryId": MEMORY_ID, "records": [{"memoryRecordId": rid(1), "namespace": ns}]},
    )
    stub.add_response(
        "list_sessions",
        {"sessionSummaries": []},
        {"memoryId": MEMORY_ID, "actorId": MINH, "maxResults": 100},
    )
    stub.add_response(
        "get_memory_record",
        {"memoryRecord": {**summary, "memoryRecordId": rid(2)}},
        {"memoryId": MEMORY_ID, "memoryRecordId": rid(2)},
    )
    stub.add_response(
        "delete_memory_record",
        {"memoryRecordId": rid(2)},
        {"memoryId": MEMORY_ID, "memoryRecordId": rid(2), "namespace": ns},
    )
    store = MemoryStore(MEMORY_ID, client=client)
    with stub:
        assert store.clear(MINH).deleted_records == 1
        assert store.delete_record(MINH, rid(2)).deleted
    stub.assert_no_pending_responses()


# --- quiet_hours ----------------------------------------------------------------------------------
DAY = load_defaults()["day_parts"]


@pytest.mark.parametrize(
    ("text", "windows"),
    [
        ("Đừng nhắc mình buổi sáng", [(5, 11)]),
        ("Người dùng không muốn được nhắc nhở vào buổi sáng", [(5, 11)]),
        ("Không thông báo sau 22h nhé", [(22, 24)]),
        ("đừng gửi gì từ 22 giờ đến 7 giờ", [(22, 7)]),
        ("đừng nhắc trước 9 giờ sáng", [(0, 9)]),
        ("tránh nhắc sau 9 giờ tối", [(21, 24)]),
        ("Đừng nhắc tôi ban đêm", [(22, 5)]),
        ("Ưu tiên hũ Du lịch", []),
        ("không sao, nhắc mình buổi tối cũng được", []),
    ],
)
def test_doc_gio_im_lang_tu_cau_so_thich(text, windows):
    assert list(parse_quiet_hours([text], DAY).windows) == windows


def test_khung_gio_vat_qua_nua_dem():
    q = QuietHours(windows=((22, 7), (12, 13)))
    assert q.contains(23) and q.contains(3) and q.contains(12)
    assert not q.contains(7) and not q.contains(15)


def test_quiet_hours_doc_dung_namespace_so_thich_cua_sub(world):
    world["api"].add(
        20, "fact", MINH, "Không nhắc buổi tối"
    )  # sự thật, không phải sở thích: không dùng
    q = quiet_hours(MINH, store=world["store"])
    assert q.available and q.windows == ((5, 11),) and q.contains(8) and not q.contains(19)
    kw = world["api"].calls[-1][1]
    assert kw["namespace"] == namespace_for("preference", MINH)
    assert quiet_hours(LAN, store=world["store"]).windows == ()


def test_quiet_hours_khong_nem_loi_khi_memory_hong():
    api = FakeMemoryApi()
    api.error = "ThrottledException"
    assert quiet_hours(MINH, store=MemoryStore(MEMORY_ID, client=api)) == QuietHours(
        available=False
    )
    assert quiet_hours(MINH, store=MemoryStore(None, client=api)) == QuietHours(available=False)


def test_display_text_bo_the_va_che():
    assert display_text({"text": "<b>xin</b> chào 0912345678"}) == "xin chào [SĐT]"
    assert display_text(None) == ""


# --- POST /me/delete-data/confirmations, POST /me/delete-data ------------------------------------------
BODY = {"tool": "delete_my_data", "params": {"scope": "all"}}


def token_for(world, sub=MINH) -> str:
    status, body = req(world, "POST", "/me/delete-data/confirmations", sub=sub, body=BODY)
    assert status == 200, body
    return body["confirm_token"]


def test_cap_token_dung_hop_dong(world, schema_ok):
    status, body = req(
        world, "POST", "/me/delete-data/confirmations", sub=MINH, body={**BODY, "params": {}}
    )
    assert status == 200, body
    schema_ok("ConfirmationResponse", body)
    assert body["tool"] == "delete_my_data" and body["params"] == {"scope": "all"}
    assert body["preview"]["warnings"]


@pytest.mark.parametrize(
    "body",
    [
        {"tool": "move_between_jars", "params": {}},
        {"tool": "delete_my_data", "params": {"scope": "memory"}},
        {"tool": "delete_my_data"},
    ],
)
def test_cap_token_tham_so_sai_400(world, body):
    status, out = req(world, "POST", "/me/delete-data/confirmations", sub=MINH, body=body)
    assert status == 400 and out["error"]["code"] == "PARAMS_INVALID"


def test_thieu_token_428_khong_xoa_gi(world):
    status, body = req(world, "POST", "/me/delete-data", sub=MINH, body=BODY)
    assert status == 428 and body["error"]["code"] == "NEEDS_CONFIRMATION"
    assert (
        world["repo"].rows == {} and world["repo"].aurora[MINH] == 42 and len(world["s3"].keys) == 4
    )


def test_xoa_du_lieu_dung_nguoi_ca_ba_noi(world, schema_ok):
    token = token_for(world)
    status, body = req(
        world, "POST", "/me/delete-data", sub=MINH, body={**BODY, "confirm_token": token}
    )
    assert status == 200, body
    schema_ok("DataDeletion", body)
    DataDeletion.model_validate(body)
    assert body["status"] == "done" and body["finished_at"]
    assert body["steps"] == {
        "s3": {"status": "done", "deleted": 2},
        "memory": {"status": "done", "deleted": 5},
        "aurora": {"status": "done", "deleted": 42},
    }
    assert world["s3"].keys == {
        f"u/{LAN}/job-3",
        f"u/{MINH}x/job-4",
    }  # tiền tố có `/` cuối: không đụng người có sub dài hơn
    assert {x["ns"] for x in world["api"].records.values()} == {namespace_for("preference", LAN)}
    assert world["repo"].aurora == {LAN: 17}
    # token dùng một lần
    status, again = req(
        world, "POST", "/me/delete-data", sub=MINH, body={**BODY, "confirm_token": token}
    )
    assert status == 409 and again["error"]["code"] == "TOKEN_REUSED"


def test_xoa_du_lieu_khi_chua_co_su_kien_ngan_han_buoc_memory_done(world):
    """Nghiệm thu 24/11 (`khoa`): bước Memory bị đánh `failed` `MEMORY_UNAVAILABLE` dù đã xóa hết bản ghi, vì ListSessions ném
    ResourceNotFoundException cho actor chưa có sự kiện."""
    world["api"].events.clear()
    status, body = req(
        world, "POST", "/me/delete-data", sub=MINH, body={**BODY, "confirm_token": token_for(world)}
    )
    assert status == 200 and body["status"] == "done", body
    assert body["steps"]["memory"] == {"status": "done", "deleted": 3}
    assert {x["ns"] for x in world["api"].records.values()} == {namespace_for("preference", LAN)}


def test_token_cua_nguoi_khac_khong_dung_duoc(world):
    token = token_for(world, sub=LAN)
    status, body = req(
        world, "POST", "/me/delete-data", sub=MINH, body={**BODY, "confirm_token": token}
    )
    assert status == 403 and body["error"]["code"] == "TOKEN_INVALID"
    assert world["repo"].aurora == {MINH: 42, LAN: 17}


def test_idempotent_chay_lai_van_done(world):
    for _ in range(2):
        status, body = req(
            world,
            "POST",
            "/me/delete-data",
            sub=MINH,
            body={**BODY, "confirm_token": token_for(world)},
        )
        assert status == 200 and body["status"] == "done"
    assert body["steps"]["aurora"] == {"status": "done", "deleted": 0}
    assert len(world["repo"].rows) == 2


def test_s3_loi_thi_partial_goi_lai_thi_xong(world):
    world["s3"].fail = True
    _, body = req(
        world, "POST", "/me/delete-data", sub=MINH, body={**BODY, "confirm_token": token_for(world)}
    )
    assert (
        body["status"] == "partial"
        and body["steps"]["s3"]["status"] == "failed"
        and body["steps"]["aurora"]["status"] == "done"
    )
    DataDeletion.model_validate(body)
    world["s3"].fail = False
    _, body = req(
        world, "POST", "/me/delete-data", sub=MINH, body={**BODY, "confirm_token": token_for(world)}
    )
    assert body["status"] == "done" and body["steps"]["s3"] == {"status": "done", "deleted": 2}
    assert not any(k.startswith(f"u/{MINH}/") for k in world["s3"].keys)


def test_aurora_loi_thi_failed_chay_lai_thi_xong(world):
    world["repo"].fail_aurora = True
    _, body = req(
        world, "POST", "/me/delete-data", sub=MINH, body={**BODY, "confirm_token": token_for(world)}
    )
    assert body["status"] == "failed" and body["steps"]["aurora"] == {
        "status": "failed",
        "error_code": "DATABASE_UNAVAILABLE",
    }
    assert world["repo"].aurora[MINH] == 42
    world["repo"].fail_aurora = False
    _, body = req(
        world, "POST", "/me/delete-data", sub=MINH, body={**BODY, "confirm_token": token_for(world)}
    )
    assert body["status"] == "done" and world["repo"].aurora == {LAN: 17}


def test_chet_giua_chung_thi_lan_sau_lam_tiep_sau_han_thue(world):
    repo, clock = world["repo"], world["clock"]
    repo.crash_on_save = 2  # S3 xong và đã ghi tiến độ, chết khi ghi bước Memory
    status, body = req(
        world, "POST", "/me/delete-data", sub=MINH, body={**BODY, "confirm_token": token_for(world)}
    )
    assert status == 500
    running = repo.running(MINH)
    assert (
        running["steps"]["s3"]["status"] == "done"
        and running["steps"]["memory"]["status"] == "pending"
    )
    repo.crash_on_save = None
    # còn trong hạn thuê: trả lần đang chạy, không chạy song song
    _, body = req(
        world, "POST", "/me/delete-data", sub=MINH, body={**BODY, "confirm_token": token_for(world)}
    )
    assert body["status"] == "running" and "finished_at" not in body
    DataDeletion.model_validate(body)
    clock.advance(121)
    _, body = req(
        world, "POST", "/me/delete-data", sub=MINH, body={**BODY, "confirm_token": token_for(world)}
    )
    assert body["status"] == "done" and body["deletion_id"] == running["id"]
    assert body["steps"]["s3"]["deleted"] == 2 and body["steps"]["memory"]["status"] == "done"
    assert world["repo"].aurora == {LAN: 17} and len(repo.rows) == 1


def test_khong_co_memory_va_bucket_thi_skipped(world):
    p = world["privacy"]
    p.memory = MemoryStore(None)
    p.s3 = S3Deleter(None, "u/")
    _, body = req(
        world, "POST", "/me/delete-data", sub=MINH, body={**BODY, "confirm_token": token_for(world)}
    )
    assert (
        body["status"] == "done"
        and body["steps"]["s3"] == {"status": "skipped"}
        and body["steps"]["memory"] == {"status": "skipped"}
    )


# --- kho data_deletions thật: câu SQL luôn ép user_id, Aurora và chốt nhật ký chung một transaction ---------------------
class RecordingDb:
    def __init__(self) -> None:
        self.txs: list[list[tuple[str, dict[str, Any]]]] = []

    def transaction(self, uid: str):
        import contextlib

        db = self

        @contextlib.contextmanager
        def cm():
            stmts: list[tuple[str, dict[str, Any]]] = []
            db.txs.append(stmts)

            class Tx:
                def execute(self, sql: str, params: dict[str, Any] | None = None):
                    stmts.append((sql, dict(params or {}, _uid=uid)))
                    if sql.startswith("SELECT relname"):
                        return [
                            {"relname": "jars", "deleted": 3},
                            {"relname": "users", "deleted": 1},
                        ]
                    return [
                        {
                            "id": "00000000-0000-4000-8000-000000000001",
                            "status": "done",
                            "steps": {},
                            "requested_at": T0,
                            "finished_at": T0,
                            "updated_at": T0,
                        }
                    ]

            yield Tx()

        return cm()


def test_deletion_repo_ep_user_id_va_aurora_cung_transaction_voi_nhat_ky():
    db = RecordingDb()
    repo = privacy_rest.DeletionRepo(db)  # type: ignore[arg-type]
    repo.create(MINH, {"s3": {"status": "pending"}}, "t" * 80)
    seen: list[int] = []
    repo.delete_aurora_and_finish(
        MINH, "00000000-0000-4000-8000-000000000001", lambda n: seen.append(n) or ({}, "done", T0)
    )
    assert seen == [4]
    for stmts in db.txs:
        for sql, params in stmts:
            assert ":uid" in sql and params["uid"] == params["_uid"] == MINH
    last = db.txs[-1]
    assert [s.split()[0] for s, _ in last] == [
        "SELECT",
        "UPDATE",
    ]  # một transaction: xóa rồi chốt nhật ký
    assert len(db.txs[0][0][1]["trace"]) == 64
