"""Consumer SQS của Lambda phân loại: phong bì sự kiện, idempotency, suy giảm theo lần giao (phase 4 luồng B)."""

from __future__ import annotations

import json
from typing import Any

import classify_helpers  # noqa: F401  (đặt đường nhập cho pipelines/classify, evals/classification)
import pytest
from yofina_classify.consumer import parse_event, process_records
from yofina_classify.idempotency import Claim, IdempotencyStore
from yofina_classify.service import Outcome


def body(**over: Any) -> str:
    detail = {
        "v": 1,
        "event_id": "tx-1",
        "user_id": "u1",
        "transaction_id": "tx-1",
        "needs_classification": True,
        "trace_id": "a" * 32,
    }
    detail.update(over.pop("detail", {}))
    env = {"source": "yofina.ledger", "detail-type": "transaction.recorded", "detail": detail}
    env.update(over)
    return json.dumps(env)


def rec(mid: str = "m1", **kw: Any) -> dict[str, Any]:
    return {
        "messageId": mid,
        "body": body(**kw),
        "attributes": {"ApproximateReceiveCount": kw.pop("receive", "1")},
    }


class FakeService:
    def __init__(self, outcome: Outcome | Exception | None = None) -> None:
        self.outcome, self.calls = outcome or Outcome("assigned"), []

    def run(self, user_id, transaction_id, *, trace_id, degrade_on_transient):
        self.calls.append((user_id, transaction_id, trace_id, degrade_on_transient))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class FakeIdem:
    def __init__(self, state: Claim = Claim.CLAIMED) -> None:
        self.state, self.done, self.released = state, [], []

    def claim(self, event_id, *, user_id=None):
        return self.state

    def complete(self, event_id):
        self.done.append(event_id)

    def release(self, event_id):
        self.released.append(event_id)


def test_parse_event_hop_le_va_tu_choi_phong_bi_sai():
    ev = parse_event(body())
    assert (ev.user_id, ev.transaction_id, ev.needs_classification) == ("u1", "tx-1", True)
    from yofina_classify.consumer import BadEvent

    for bad in (
        "khong json",
        "[]",
        body(source="khac"),
        body(**{"detail-type": "salary.confirmed"}),
        body(detail={"user_id": ""}),
    ):
        with pytest.raises(BadEvent):
            parse_event(bad)


def test_xu_ly_binh_thuong_goi_service_va_danh_dau_xong():
    svc, idem = FakeService(), FakeIdem()
    r = process_records([rec()], svc, idem, max_receive_count=3)
    assert svc.calls == [("u1", "tx-1", "a" * 32, False)] and idem.done == ["tx-1"]
    assert r.assigned == 1 and r.failures == [] and r.sqs_response() == {"batchItemFailures": []}


def test_lan_giao_cuoi_thi_cho_phep_suy_giam():
    svc = FakeService(Outcome("asked"))
    r = process_records(
        [{**rec(), "attributes": {"ApproximateReceiveCount": "3"}}],
        svc,
        FakeIdem(),
        max_receive_count=3,
    )
    assert svc.calls[0][3] is True and r.asked == 1


def test_su_kien_trung_bi_bo_qua_khong_goi_model():
    svc = FakeService()
    r = process_records([rec()], svc, FakeIdem(Claim.DUPLICATE), max_receive_count=3)
    assert svc.calls == [] and r.duplicates == 1 and r.failures == []


def test_dang_xu_ly_o_noi_khac_thi_bao_loi_de_sqs_giao_lai():
    r = process_records([rec("m9")], FakeService(), FakeIdem(Claim.BUSY), max_receive_count=3)
    assert r.sqs_response() == {"batchItemFailures": [{"itemIdentifier": "m9"}]}


def test_loi_xu_ly_thi_nha_khoa_va_bao_loi_tung_muc_khong_lam_hong_muc_khac():
    svc = FakeService(RuntimeError("DB"))
    idem = FakeIdem()
    r = process_records(
        [rec("m1"), rec("m2", detail={"event_id": "tx-2", "transaction_id": "tx-2"})],
        svc,
        idem,
        max_receive_count=3,
    )
    assert [f["itemIdentifier"] for f in r.sqs_response()["batchItemFailures"]] == ["m1", "m2"]
    assert idem.released == ["tx-1", "tx-2"] and idem.done == []


def test_ban_tin_sai_hoac_khong_can_phan_loai():
    svc = FakeService()
    r = process_records(
        [
            {"messageId": "bad", "body": "xxx"},
            rec("m2", detail={"needs_classification": False, "event_id": "tx-9"}),
        ],
        svc,
        FakeIdem(),
        max_receive_count=3,
    )
    assert r.failures == ["bad"] and r.skipped == 1 and svc.calls == []


def test_cung_event_id_trong_mot_lo_chi_xu_ly_mot_lan():
    svc = FakeService()
    r = process_records([rec("m1"), rec("m2")], svc, FakeIdem(), max_receive_count=3)
    assert len(svc.calls) == 1 and r.duplicates == 1


class FakeDynamo:
    """DynamoDB giả tối thiểu cho IdempotencyStore (chỉ có ở test)."""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}

    def put_item(
        self,
        TableName,
        Item,
        ConditionExpression,
        ExpressionAttributeNames,
        ExpressionAttributeValues,
    ):
        key = Item["event_id"]["S"]
        cur = self.items.get(key)
        now = int(ExpressionAttributeValues[":now"]["N"])
        if cur is not None and not (
            cur["status"]["S"] == "in_progress" and int(cur["lease_until"]["N"]) < now
        ):
            err = Exception("cond")
            err.response = {"Error": {"Code": "ConditionalCheckFailedException"}}  # type: ignore[attr-defined]
            raise err
        self.items[key] = Item

    def get_item(self, TableName, Key, ConsistentRead):
        return (
            {"Item": self.items[Key["event_id"]["S"]]} if Key["event_id"]["S"] in self.items else {}
        )

    def update_item(
        self, TableName, Key, UpdateExpression, ExpressionAttributeNames, ExpressionAttributeValues
    ):
        item = self.items[Key["event_id"]["S"]]
        item["status"] = {"S": "done"}
        item.pop("lease_until", None)

    def delete_item(
        self,
        TableName,
        Key,
        ConditionExpression,
        ExpressionAttributeNames,
        ExpressionAttributeValues,
    ):
        key = Key["event_id"]["S"]
        if self.items.get(key, {}).get("status", {}).get("S") != "in_progress":
            err = Exception("cond")
            err.response = {"Error": {"Code": "ConditionalCheckFailedException"}}  # type: ignore[attr-defined]
            raise err
        del self.items[key]


def test_idempotency_claim_done_release_va_khoa_thue_het_han():
    t = [1000.0]
    ddb = FakeDynamo()
    s = IdempotencyStore("tbl", ddb, ttl_seconds=100, lease_seconds=60, clock=lambda: t[0])
    assert s.claim("e1") is Claim.CLAIMED
    assert "classify:e1" in ddb.items  # khóa có tiền tố, không đè khóa của dự báo
    assert s.claim("e1") is Claim.BUSY
    t[0] += 61  # khóa thuê hết hạn: tiến trình trước chết giữa chừng
    assert s.claim("e1") is Claim.CLAIMED
    s.complete("e1")
    assert s.claim("e1") is Claim.DUPLICATE
    s.release("e1")  # không bao giờ xóa mục đã done
    assert s.claim("e1") is Claim.DUPLICATE
    assert s.claim("e2") is Claim.CLAIMED
    s.release("e2")
    assert s.claim("e2") is Claim.CLAIMED
