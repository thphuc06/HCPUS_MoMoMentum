"""Lambda batch (các op), idempotency store, phong bì sự kiện phát đi và tool `forecast___get_forecast` (lỗi, tính lại khi cũ)."""

from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from memory_repo import MemoryRepo
from pipeline_helpers import NOW, FakeDynamo, context_rows, make_settings

from yofina_core.errors import ErrorCode, YofinaError
from yofina_forecast.batch import (
    DatabaseUnavailable,
    ForecastFailed,
    NightlyHadFailures,
    handle_batch,
)
from yofina_forecast.events import ForecastEventPublisher
from yofina_forecast.idempotency import Claim, IdempotencyStore
from yofina_forecast.runner import Pipeline
from yofina_forecast.tool import error_result, get_forecast, handle_gateway, tool_name


def pipe(rows=None):
    repo = MemoryRepo(rows if rows is not None else context_rows())
    return Pipeline(repo, make_settings(), None, clock=lambda: NOW), repo


# --- batch ----------------------------------------------------------------------------------------
def test_batch_list_users_run_user_va_run_users():
    p, repo = pipe()
    assert handle_batch({"op": "list_users"}, p) == {"user_ids": ["u1", "u2"], "count": 2}
    out = handle_batch({"op": "run_user", "user_id": "u1", "trigger": "nightly"}, p)
    assert out["status"] == "ok" and out["mode"] == "full" and repo.saves == 1
    many = handle_batch({"op": "run_users", "user_ids": ["u1", "u2"], "trigger": "manual"}, p)
    assert [r["status"] for r in many["results"]] == ["ok", "ok"]


def test_batch_ho_so_thieu_la_skipped_khong_phai_loi():
    p, _ = pipe(context_rows(salary=None))
    out = handle_batch({"op": "run_user", "user_id": "u1", "trigger": "nightly"}, p)
    assert out["status"] == "skipped" and out["reason"] == "PROFILE_INCOMPLETE"


def test_batch_loi_nem_ten_lop_on_dinh_de_step_functions_retry():
    p, repo = pipe()
    repo.fail_save = True
    with pytest.raises(ForecastFailed):
        handle_batch({"op": "run_user", "user_id": "u1", "trigger": "nightly"}, p)

    def unavailable(*a):
        raise YofinaError(ErrorCode.DATABASE_UNAVAILABLE, "đang dậy")

    repo.context = unavailable  # type: ignore[method-assign]
    with pytest.raises(DatabaseUnavailable):
        handle_batch({"op": "run_user", "user_id": "u1", "trigger": "nightly"}, p)
    # run_users nuốt lỗi từng người, người khác vẫn chạy
    p2, repo2 = pipe()
    real = repo2.context

    def ctx(uid, *a):
        if uid == "bad":
            raise RuntimeError("x")
        return real(uid, *a)

    repo2.context = ctx  # type: ignore[method-assign]
    res = handle_batch({"op": "run_users", "user_ids": ["bad", "ok"], "trigger": "nightly"}, p2)[
        "results"
    ]
    assert [r["status"] for r in res] == ["failed", "ok"]
    with pytest.raises(ForecastFailed):
        handle_batch({"op": "run_user"}, p2)  # thiếu user_id
    with pytest.raises(ForecastFailed):
        handle_batch({"op": "run_user", "user_id": "u", "trigger": "khac"}, p2)
    with pytest.raises(ForecastFailed):
        handle_batch({"op": "la"}, p2)


def test_batch_summarize_co_loi_thi_nem_de_execution_that_bai():
    p, _ = pipe()
    ok = handle_batch({"op": "summarize", "results": [{"status": "ok"}, {"status": "skipped"}]}, p)
    assert ok == {"total": 2, "ok": 1, "skipped": 1, "failed": 0}
    with pytest.raises(NightlyHadFailures) as e:
        handle_batch(
            {"op": "summarize", "results": [{"status": "ok"}, {"status": "failed", "error": "ForecastFailed"}]}, p
        )  # fmt: skip
    assert json.loads(str(e.value))["failed"] == 1


# --- idempotency ----------------------------------------------------------------------------------
def test_idempotency_claim_complete_release():
    dyn = FakeDynamo()
    t = [100.0]
    s = IdempotencyStore("t", dyn, ttl_seconds=1000, lease_seconds=50, clock=lambda: t[0])
    assert s.claim("a", user_id="u") is Claim.CLAIMED
    assert s.claim("a") is Claim.BUSY
    s.complete("a", run_id="r1")
    assert s.claim("a") is Claim.DUPLICATE
    assert dyn.items["a"]["status"]["S"] == "done" and "lease_until" not in dyn.items["a"]
    s.release("a")  # không bao giờ xóa mục đã done
    assert "a" in dyn.items
    assert s.claim("b") is Claim.CLAIMED
    s.release("b")
    assert "b" not in dyn.items and s.claim("b") is Claim.CLAIMED
    t[0] += 100  # khóa thuê hết hạn
    assert s.claim("b") is Claim.CLAIMED


# --- sự kiện phát đi ------------------------------------------------------------------------------
class FakeEvents:
    def __init__(self, fail: Exception | None = None) -> None:
        self.entries: list[dict[str, Any]] = []
        self.fail = fail

    def put_events(self, Entries):
        if self.fail:
            raise self.fail
        self.entries += Entries
        return {"FailedEntryCount": 0}


def test_phat_forecast_updated_dung_hop_dong_khong_pii(registry, schema_validator=None):
    from datetime import date

    client = FakeEvents()
    pub = ForecastEventPublisher("bus", client)
    ok = pub.forecast_updated(
        user_id="sub-1", run_id="11111111-1111-4111-8111-111111111111", computed_at=NOW,
        app_date=date(2026, 11, 21), trigger="event", jar_codes=["a", "a", "b"],
        is_initial_estimate=False, confidence_label="medium", parent_event_id="22222222-2222-4222-8222-222222222222",
    )  # fmt: skip
    assert ok
    e = client.entries[0]
    assert e["Source"] == "yofina.forecast" and e["DetailType"] == "forecast.updated"
    d = json.loads(e["Detail"])
    assert d["event_id"] == d["run_id"] and d["jar_codes"] == ["a", "b"] and d["v"] == 1
    from jsonschema import Draft202012Validator

    errors = list(
        Draft202012Validator(
            {"$ref": "https://contracts.yofina.invalid/events/forecast.updated.schema.json"},
            registry=registry,
        ).iter_errors(d)
    )
    assert not errors, errors


def test_phat_that_bai_khong_nem_ra_ngoai():
    pub = ForecastEventPublisher("bus", FakeEvents(RuntimeError("mạng")))
    assert pub.forecast_updated(
        user_id="u", run_id="r", computed_at=NOW, app_date=NOW.date(), trigger="nightly",
        jar_codes=["a"], is_initial_estimate=False, confidence_label="low",
    ) is False  # fmt: skip
    assert ForecastEventPublisher("").forecast_updated(
        user_id="u", run_id="r", computed_at=NOW, app_date=NOW.date(), trigger="nightly",
        jar_codes=["a"], is_initial_estimate=False, confidence_label="low",
    ) is False  # fmt: skip


# --- tool -----------------------------------------------------------------------------------------
class FakeReader:
    """`ForecastReader.forecast_block` giả: trả khối có `stale` theo kịch bản, hoặc ném FORECAST_UNAVAILABLE."""

    def __init__(self, script: list[Any]) -> None:
        self.script = script
        self.calls = 0

    def forecast_block_or_none(self, user_id, jar, *, trace_id, source_tool):
        item = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        if item is None:
            return None
        return SimpleNamespace(
            data=SimpleNamespace(
                stale=item, model_dump=lambda **kw: {"stale": item, "kw": sorted(kw)}
            ),
            source=SimpleNamespace(as_of="2026-12-10T03:00:00Z", app_date="2026-11-21"),
        )


UNAVAILABLE = None  # chưa có dự báo nào


def test_tool_tinh_lai_khi_chua_co_hoac_cu_roi_doc_lai():
    p, repo = pipe()
    r = FakeReader([UNAVAILABLE, False])
    out = get_forecast(r, p, "u", "an_uong", trace_id="t")
    assert (
        out["status"] == "OK" and out["data"]["stale"] is False and r.calls == 2 and repo.saves == 1
    )
    r2 = FakeReader([True, False])
    p2, repo2 = pipe()
    assert (
        get_forecast(r2, p2, "u", "an_uong", trace_id="t")["data"]["stale"] is False
        and repo2.saves == 1
    )
    r3 = FakeReader([False])  # còn tươi: không tính lại
    p3, repo3 = pipe()
    get_forecast(r3, p3, "u", "an_uong", trace_id="t")
    assert repo3.saves == 0 and r3.calls == 1


def test_tool_khong_tinh_lai_duoc_thi_tra_ban_cu_hoac_bao_khong_san_sang():
    _p, repo = pipe()
    repo.fail_save = True

    class Boom(Pipeline):
        def run_user(self, *a, **k):
            raise YofinaError(ErrorCode.DATABASE_UNAVAILABLE, "x")

    boom = Boom(repo, make_settings())
    out = get_forecast(FakeReader([True]), boom, "u", "an_uong", trace_id="t")
    assert out["data"]["stale"] is True  # giữ bản cũ, đánh dấu cũ
    with pytest.raises(YofinaError) as e:
        get_forecast(FakeReader([UNAVAILABLE]), boom, "u", "an_uong", trace_id="t")
    assert e.value.code == ErrorCode.FORECAST_UNAVAILABLE


def test_tool_loi_nghiep_vu_khac_duoc_truyen_va_tham_so_bi_kiem():
    p, _ = pipe()
    with pytest.raises(YofinaError) as e:
        get_forecast(
            FakeReader([YofinaError(ErrorCode.JAR_NOT_FOUND, "x")]), p, "u", "zzz", trace_id="t"
        )
    assert e.value.code == ErrorCode.JAR_NOT_FOUND
    with pytest.raises(YofinaError) as e2:
        get_forecast(FakeReader([False]), p, "u", None, trace_id="t")
    assert e2.value.code == ErrorCode.PARAMS_INVALID


def ctx_for(name: str):
    return SimpleNamespace(
        client_context=SimpleNamespace(custom={"bedrockAgentCoreToolName": name})
    )


def test_handle_gateway_doc_ten_tool_va_user_id_va_tra_loi_co_cau_truc():
    p, _ = pipe()
    assert tool_name(ctx_for("forecast___get_forecast")) == "get_forecast"
    ok = handle_gateway(
        {"user_id": "u", "jar": "an_uong"},
        ctx_for("forecast___get_forecast"),
        FakeReader([False]),
        p,
    )
    assert ok["status"] == "OK"
    no_user = handle_gateway(
        {"jar": "x"}, ctx_for("forecast___get_forecast"), FakeReader([False]), p
    )
    assert no_user == error_result(ErrorCode.UNAUTHENTICATED, "Thiếu thông tin người dùng.")
    other = handle_gateway(
        {"user_id": "u", "jar": "x"}, ctx_for("forecast___run_scenario"), FakeReader([False]), p
    )
    assert other["status"] == "ERROR" and other["code"] == "PARAMS_INVALID"
    boom = handle_gateway({"user_id": "u", "jar": "x"}, ctx_for("forecast___get_forecast"), SimpleNamespace(
        forecast_block_or_none=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))), p)  # fmt: skip
    assert boom["code"] == "INTERNAL_ERROR"


def test_thoi_gian_chay_khong_doi_do_dong_ho_he_thong():
    # run_user chỉ dùng đồng hồ được tiêm; chạy hai lần với đồng hồ khác nhau không đổi kết quả dự báo (ngày gốc từ DB)
    p1, r1 = pipe()
    p2, r2 = pipe()
    p2._clock = lambda: NOW + timedelta(days=3)
    p1.run_user("u", trigger="nightly")
    p2.run_user("u", trigger="nightly")
    a, b = r1.runs[0]["result"], r2.runs[0]["result"]
    assert a == b
