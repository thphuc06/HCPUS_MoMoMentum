"""Consumer SQS: luật sự kiện -> việc, gộp theo người dùng, idempotency theo event_id, partial batch response."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from memory_repo import MemoryRepo
from pipeline_helpers import NOW, FakeDynamo, context_rows, make_settings

from yofina_forecast.consumer import Plan, merge_plans, plan_event, process_records
from yofina_forecast.events import BadEvent, LedgerEvent, parse_envelope
from yofina_forecast.idempotency import Claim, IdempotencyStore
from yofina_forecast.runner import Pipeline


def envelope(detail_type: str, **detail) -> dict:
    d = {
        "v": 1,
        "event_id": detail.pop("event_id", "e1"),
        "user_id": detail.pop("user_id", "u"),
        **detail,
    }
    return {"source": "yofina.ledger", "detail-type": detail_type, "detail": d}


def rec(i: str, detail_type: str, **detail) -> dict:
    return {"messageId": i, "body": json.dumps(envelope(detail_type, **detail))}


def txn(event_id="t1", jars=("an_uong",), **kw) -> dict:
    return {
        "event_id": event_id,
        "kind": "expense",
        "funding_source": "jar",
        "jar_codes": list(jars),
        **kw,
    }


@pytest.fixture()
def env():
    repo = MemoryRepo(context_rows())
    clock = [NOW]
    pipe = Pipeline(repo, make_settings(), None, clock=lambda: clock[0])
    dyn = FakeDynamo()
    now = [1_000_000.0]
    idem = IdempotencyStore("t", dyn, ttl_seconds=3600, lease_seconds=120, clock=lambda: now[0])
    return pipe, repo, idem, dyn, clock, now


def prime(pipe):
    pipe.run_user("u", trigger="nightly")


def ledger_event(detail_type, **detail) -> LedgerEvent:
    return parse_envelope(envelope(detail_type, **detail))


def test_luat_su_kien():
    assert plan_event(
        ledger_event("transaction.recorded", **txn(jars=("an_uong", "di_lai")))
    ) == Plan(False, ("an_uong", "di_lai"))
    assert plan_event(ledger_event("transaction.recorded", **txn(funding_source="credit"))).nothing
    assert plan_event(ledger_event("transaction.recorded", **txn(obligation_id="o1"))).full
    for t in ("salary.confirmed", "obligation.changed", "profile.updated"):
        assert plan_event(ledger_event(t)).full
    merged = merge_plans([Plan(False, ("a",)), Plan(False, ("b", "a")), Plan(True, ())])
    assert merged == Plan(True, ("a", "b"))


def test_phong_bi_sai_bi_tu_choi():
    for body in ("khong json", "[]", json.dumps({"source": "khac", "detail-type": "x", "detail": {}}),
                 json.dumps({"source": "yofina.ledger", "detail-type": "transaction.recorded", "detail": {"user_id": "u"}})):  # fmt: skip
        with pytest.raises(BadEvent):
            parse_envelope(body)


def test_giao_dich_chinh_nhanh_roi_danh_dau_done(env):
    pipe, repo, idem, dyn, clock, _ = env
    prime(pipe)
    clock[0] += timedelta(minutes=2)
    rep = process_records([rec("m1", "transaction.recorded", **txn("t1"))], pipe, idem)
    assert rep.failures == [] and rep.processed == 1
    assert rep.runs[0]["mode"] == "fast" and rep.runs[0]["jar_codes"] == ["an_uong"]
    assert repo.runs[-1]["source_event_id"] == "t1"
    assert (
        dyn.items["t1"]["status"]["S"] == "done"
        and dyn.items["t1"]["run_id"]["S"] == rep.runs[0]["run_id"]
    )


def test_gui_trung_cung_event_id_khong_tinh_hai_lan(env):
    pipe, repo, idem, _dyn, _clock, _ = env
    prime(pipe)
    saves = repo.saves
    first = process_records([rec("m1", "transaction.recorded", **txn("t1"))], pipe, idem)
    assert first.processed == 1 and repo.saves == saves + 1
    again = process_records([rec("m2", "transaction.recorded", **txn("t1"))], pipe, idem)
    assert again.duplicates == 1 and again.processed == 0 and again.failures == []
    assert repo.saves == saves + 1  # lần giao trùng không tạo lần chạy mới
    # trùng ngay trong một lô
    same = process_records(
        [rec("m3", "transaction.recorded", **txn("t2")), rec("m4", "transaction.recorded", **txn("t2"))],
        pipe, idem,
    )  # fmt: skip
    assert same.processed == 1 and same.duplicates == 1 and repo.saves == saves + 2


def test_nhieu_su_kien_cua_mot_nguoi_gop_thanh_mot_lan_chay(env):
    pipe, repo, idem, _dyn, _clock, _ = env
    prime(pipe)
    saves = repo.saves
    rep = process_records(
        [
            rec("m1", "transaction.recorded", **txn("t1", jars=("an_uong",))),
            rec("m2", "transaction.recorded", **txn("t2", jars=("giai_tri",))),
        ],
        pipe, idem,
    )  # fmt: skip
    assert rep.processed == 2 and repo.saves == saves + 1
    assert (
        sorted(rep.runs[0]["jar_codes"]) == ["an_uong", "giai_tri"]
        and rep.runs[0]["mode"] == "fast"
    )


def test_mot_su_kien_doi_hoi_chay_day_du_thi_ca_nhom_chay_day_du(env):
    pipe, _repo, idem, _dyn, _clock, _ = env
    prime(pipe)
    rep = process_records(
        [rec("m1", "transaction.recorded", **txn("t1")), rec("m2", "obligation.changed", event_id="o1", obligation_id="x")],
        pipe, idem,
    )  # fmt: skip
    assert rep.runs[0]["mode"] == "full" and rep.processed == 2


def test_khoan_mua_tra_sau_khong_tinh_lai_nhung_van_danh_dau_done(env):
    pipe, repo, idem, dyn, _clock, _ = env
    prime(pipe)
    saves = repo.saves
    rep = process_records(
        [rec("m1", "transaction.recorded", **txn("c1", funding_source="credit", jars=("giai_tri",)))],
        pipe, idem,
    )  # fmt: skip
    assert rep.processed == 1 and repo.saves == saves and rep.skipped == 1
    assert dyn.items["c1"]["status"]["S"] == "done"


def test_loi_tinh_nha_khoa_va_bao_loi_tung_muc(env):
    pipe, repo, idem, dyn, _clock, _ = env
    repo.fail_save = True
    rep = process_records(
        [rec("m1", "transaction.recorded", **txn("t1")), rec("m2", "salary.confirmed", event_id="s1", user_id="v")],
        pipe, idem,
    )  # fmt: skip
    # người dùng u lỗi khi ghi; người dùng v cũng lỗi vì dùng chung repo giả: cả hai được báo, khóa nhả để giao lại
    assert sorted(rep.failures) == ["m1", "m2"] and dyn.items == {}
    assert rep.sqs_response() == {
        "batchItemFailures": [{"itemIdentifier": "m1"}, {"itemIdentifier": "m2"}]
    }
    repo.fail_save = False
    ok = process_records([rec("m1", "transaction.recorded", **txn("t1"))], pipe, idem)
    assert ok.processed == 1 and ok.failures == []  # giao lại thì xử lý được (khóa đã nhả)


def test_loi_cua_mot_nguoi_khong_lam_hong_nguoi_khac(env):
    pipe, repo, idem, _dyn, _clock, _ = env
    real = repo.context

    def ctx(user_id, *a):
        if user_id == "bad":
            raise RuntimeError("hỏng")
        return real(user_id, *a)

    repo.context = ctx  # type: ignore[method-assign]
    rep = process_records(
        [rec("m1", "salary.confirmed", event_id="s1", user_id="bad"), rec("m2", "salary.confirmed", event_id="s2", user_id="good")],
        pipe, idem,
    )  # fmt: skip
    assert rep.failures == ["m1"] and rep.processed == 1


def test_tin_nhan_sai_dinh_dang_bao_loi_de_vao_dlq(env):
    pipe, _repo, idem, _dyn, _clock, _ = env
    rep = process_records([{"messageId": "bad", "body": "không phải json"}], pipe, idem)
    assert rep.failures == ["bad"]


def test_dang_xu_ly_o_noi_khac_thi_giao_lai_sau_va_khoa_het_han_thi_gianh_lai(env):
    pipe, _repo, idem, dyn, _clock, now = env
    prime(pipe)
    assert idem.claim("t1") is Claim.CLAIMED  # tiến trình khác đang giữ
    rep = process_records([rec("m1", "transaction.recorded", **txn("t1"))], pipe, idem)
    assert rep.failures == ["m1"] and dyn.items["t1"]["status"]["S"] == "in_progress"
    now[0] += 500  # khóa thuê quá hạn (tiến trình trước chết)
    rep2 = process_records([rec("m1", "transaction.recorded", **txn("t1"))], pipe, idem)
    assert rep2.processed == 1 and rep2.failures == []


def test_ho_so_chua_khai_thi_bo_qua_khong_phai_loi(env):
    _pipe, _repo, idem, dyn, _clock, _ = env
    repo2 = MemoryRepo(context_rows(salary=None))
    pipe2 = Pipeline(repo2, make_settings())
    rep = process_records([rec("m1", "profile.updated", event_id="p1")], pipe2, idem)
    assert rep.failures == [] and rep.skipped == 1 and dyn.items["p1"]["status"]["S"] == "done"
