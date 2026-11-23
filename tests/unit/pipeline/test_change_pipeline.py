"""Phát hiện đổi hành vi ở pipeline: `suspect_and_store` (đường sự kiện), `detect_and_store` (N2, batch đêm) và bước nghi trong consumer.

Dùng kho `behavior_flags` trong bộ nhớ (cùng luật CHECK và chỉ mục duy nhất một phần của migration 0052) và `MemoryRepo`; SQL thật và RLS
được kiểm ở `tests/local_pg/test_change_flow.py`.
"""

from __future__ import annotations

import copy
import json
import uuid
from datetime import date, timedelta
from typing import Any

import numpy as np
import pytest
from conftest import BASE, CONTRACTS, load_json
from jsonschema import Draft202012Validator
from memory_repo import MemoryRepo
from pipeline_helpers import APP_DATE, NOW, FakeDynamo, context_rows, jar_row, make_settings

from yofina_forecast import change
from yofina_forecast.consumer import process_records
from yofina_forecast.events import ForecastEventPublisher
from yofina_forecast.idempotency import IdempotencyStore
from yofina_forecast.runner import Pipeline
from yofina_ml import change as ml

USER = "u"
P = ml.load_params()


# --- dữ liệu --------------------------------------------------------------------------------------------------
def weeks_to_daily(weeks, seed: int = 0, noise: float = 0.35) -> list[int]:
    rng = np.random.default_rng(seed)
    out: list[int] = []
    for w in weeks:
        v = np.exp(rng.normal(0, noise, 7))
        v = v / v.sum() * w
        out.extend(round(x) for x in v)
    return out


def flat_weeks(level: float, n: int, seed: int = 0) -> list[float]:
    rng = np.random.default_rng(seed)
    return [float(max(level * (1 + 0.1 * rng.standard_normal()), 10_000)) for _ in range(n)]


SHIFTED = [
    *flat_weeks(500_000, 10, seed=1),
    1_300_000,
    1_250_000,
    1_350_000,
]  # 13 tuần, bước nhảy ở tuần 10
FLAT = flat_weeks(500_000, 13, seed=2)


def make_pipeline(
    spend: list[int], *, publisher=None, extra_jars=(), **ctx
) -> tuple[Pipeline, MemoryRepo]:
    jars = [
        jar_row("an_uong", "spending", 380_000, 60, 1, spend),
        *extra_jars,
        jar_row("nghia_vu", "obligation", 1_000_000, 20, 9, [0] * len(spend)),
    ]
    repo = MemoryRepo(context_rows(days=len(spend), jars=jars, **ctx))
    pipe = Pipeline(repo, make_settings(), publisher, clock=lambda: NOW)
    return pipe, repo


class FlagStore:
    """`behavior_flags` trong bộ nhớ: CHECK và chỉ mục duy nhất một phần y như migration 0052."""

    def __init__(self, seed: list[dict[str, Any]] | None = None) -> None:
        self.rows: list[dict[str, Any]] = [self._full(r) for r in (seed or [])]
        self.fail_list = False

    @staticmethod
    def _full(r: dict[str, Any]) -> dict[str, Any]:
        base = {
            "id": str(uuid.uuid4()),
            "method": "pelt",
            "suspected_app_date": APP_DATE,
            "change_point_date": None,
            "confirmed_app_date": None,
            "weeks_held": None,
            "detail": {},
            "roadmap_job_id": None,
            "applied_at": None,
        }
        base.update(r)
        return base

    @staticmethod
    def check(r: dict[str, Any]) -> None:
        assert int(r["new_weekly_vnd"]) != int(r["old_weekly_vnd"])
        assert (r["direction"] == "up") == (int(r["new_weekly_vnd"]) > int(r["old_weekly_vnd"]))
        assert (r["status"] in ("confirmed", "applied")) == (r["confirmed_app_date"] is not None)
        assert r["status"] in ("suspected", "confirmed", "dismissed", "applied")
        assert r["method"] in ("cusum", "page_hinkley", "pelt")
        json.dumps(r["detail"], default=str)  # jsonb phải serialize được

    def list(self, user_id):
        if self.fail_list:
            raise RuntimeError("Aurora lỗi")
        return [copy.deepcopy(r) for r in sorted(self.rows, key=lambda r: str(r["id"]))]

    def insert(self, user_id, flag) -> bool:
        row = self._full({k: v for k, v in flag.items() if k != "jar"})
        row["id"] = str(flag["id"])
        self.check(row)
        if row["status"] in ("suspected", "confirmed") and any(
            r["jar_code"] == row["jar_code"] and r["status"] in ("suspected", "confirmed")
            for r in self.rows
        ):
            return False  # ON CONFLICT DO NOTHING
        self.rows.append(row)
        return True

    def update(self, user_id, flag, expected) -> bool:
        for r in self.rows:
            if str(r["id"]) == str(flag["id"]) and r["status"] == expected:
                r.update({k: v for k, v in flag.items() if k != "id"})
                self.check(r)
                return True
        return False

    def dismiss(self, user_id, flag_id, detail) -> bool:
        for r in self.rows:
            if str(r["id"]) == flag_id and r["status"] == "suspected":
                r.update(status="dismissed", detail=dict(detail))
                return True
        return False

    def mark_published(self, user_id, flag_id, patch) -> bool:
        for r in self.rows:
            if str(r["id"]) == flag_id and r["status"] == "confirmed":
                r["detail"] = {**r["detail"], **patch}
                return True
        return False

    def by_jar(self, jar, status=None):
        return [
            r
            for r in self.rows
            if r["jar_code"] == jar and (status is None or r["status"] == status)
        ]


class FakeEvents:
    """Client EventBridge giả ghi lại `put_events`."""

    def __init__(self, *, fail_times: int = 0) -> None:
        self.entries: list[dict[str, Any]] = []
        self.fail_times = fail_times

    def put_events(self, Entries):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("EventBridge lỗi")
        self.entries.extend(Entries)
        return {"FailedEntryCount": 0}

    @property
    def details(self):
        return [json.loads(e["Detail"]) for e in self.entries]


def publisher(events: FakeEvents | None = None) -> tuple[ForecastEventPublisher, FakeEvents]:
    ev = events or FakeEvents()
    return ForecastEventPublisher("yofina-bus", ev), ev


@pytest.fixture()
def validator(registry):
    ref = f"{BASE}/events/behavior.changed.schema.json"
    return Draft202012Validator({"$ref": ref}, registry=registry)


# --- N2: batch đêm ----------------------------------------------------------------------------------------------
def test_pelt_xac_nhan_ghi_dau_hieu_va_phat_su_kien_dung_hop_dong(validator):
    pub, ev = publisher()
    pipe, _ = make_pipeline(weeks_to_daily(SHIFTED), publisher=pub)
    store = FlagStore()
    out = change.detect_and_store(pipe, USER, NOW, store=store)
    assert out.confirmed == ["an_uong"] and out.errors == [] and out.app_date == "2026-11-21"
    (flag,) = store.rows
    assert (flag["status"], flag["method"], flag["direction"]) == ("confirmed", "pelt", "up")
    assert flag["weeks_held"] == 3 and flag["confirmed_app_date"] == APP_DATE
    assert 400_000 < flag["old_weekly_vnd"] < 650_000 and flag["new_weekly_vnd"] > 1_100_000
    # tuần 10 của 13 tuần cắt lùi từ hôm qua (20/11): bắt đầu 31/10
    assert flag["change_point_date"] == date(2026, 10, 31)
    d = flag["detail"]
    assert d["detector"] == "pelt" and d["cost"] == "l2" and d["params_version"] == P.version
    assert d["params"]["pelt_penalty_c"] == P.pelt_penalty_c and d["weeks_total"] == 13
    assert d["calibration"]["detector"] == "confirm_pelt" and "fa_per_jar_year" in d["calibration"]
    assert d["calibration"]["synthetic_only"] is True
    assert "event_published_at" in d  # đã phát và đánh dấu
    # sự kiện: event_id = flag_id, đúng schema, không PII
    (detail,) = ev.details
    assert detail["event_id"] == detail["flag_id"] == flag["id"]
    assert list(validator.iter_errors(detail)) == []
    assert (detail["jar_code"], detail["direction"], detail["method"]) == ("an_uong", "up", "pelt")
    assert detail["old_weekly_vnd"] == flag["old_weekly_vnd"] and detail["weeks_held"] == 3
    assert detail["change_point_date"] == "2026-10-31" and detail["app_date"] == "2026-11-21"
    assert (
        ev.entries[0]["Source"] == "yofina.forecast"
        and ev.entries[0]["DetailType"] == "behavior.changed"
    )


def test_chay_lai_khong_tao_dau_hieu_hay_su_kien_thu_hai():
    pub, ev = publisher()
    pipe, _ = make_pipeline(weeks_to_daily(SHIFTED), publisher=pub)
    store = FlagStore()
    change.detect_and_store(pipe, USER, NOW, store=store)
    again = change.detect_and_store(pipe, USER, NOW + timedelta(hours=24), store=store)
    assert (
        again.confirmed == []
        and again.published == []
        and len(store.rows) == 1
        and len(ev.entries) == 1
    )


def test_diem_gay_cu_da_dung_khong_tao_lai_dau_hieu():
    pipe, _ = make_pipeline(weeks_to_daily(SHIFTED))
    store = FlagStore(
        [
            {
                "jar_code": "an_uong",
                "status": "applied",
                "direction": "up",
                "old_weekly_vnd": 500_000,
                "new_weekly_vnd": 1_300_000,
                "change_point_date": date(2026, 10, 25),  # lệch 6 ngày so với 31/10
                "confirmed_app_date": date(2026, 11, 2),
                "applied_at": NOW,
            }
        ]
    )
    out = change.detect_and_store(pipe, USER, NOW, store=store)
    assert out.confirmed == [] and len(store.rows) == 1


def test_diem_gay_moi_cach_dau_hieu_da_dung_hon_hai_tuan_thi_tao_moi():
    pipe, _ = make_pipeline(weeks_to_daily(SHIFTED))
    store = FlagStore(
        [
            {
                "jar_code": "an_uong",
                "status": "applied",
                "direction": "down",
                "old_weekly_vnd": 900_000,
                "new_weekly_vnd": 500_000,
                "change_point_date": date(2026, 8, 1),
                "confirmed_app_date": date(2026, 8, 20),
                "applied_at": NOW,
            }
        ]
    )
    out = change.detect_and_store(pipe, USER, NOW, store=store)
    assert out.confirmed == ["an_uong"] and len(store.by_jar("an_uong", "confirmed")) == 1


def test_dau_hieu_da_xac_nhan_dang_cho_dung_thi_khong_tao_hay_phat_them():
    pub, ev = publisher()
    pipe, _ = make_pipeline(weeks_to_daily(SHIFTED), publisher=pub)
    store = FlagStore(
        [
            {
                "jar_code": "an_uong",
                "status": "confirmed",
                "direction": "up",
                "old_weekly_vnd": 520_000,
                "new_weekly_vnd": 810_000,
                "change_point_date": date(2026, 11, 4),
                "confirmed_app_date": date(2026, 11, 20),
                "weeks_held": 2,
                "detail": {"event_published_at": "2026-11-20T00:00:00+00:00"},
            }
        ]
    )
    out = change.detect_and_store(pipe, USER, NOW, store=store)
    assert out.confirmed == [] and len(store.rows) == 1 and ev.entries == []


def test_mot_khoan_lon_don_le_khong_tao_dau_hieu_va_khong_phat_su_kien():
    """Tiêu chí 3 của phase 4: một khoản lớn đơn lẻ không làm sinh lại lộ trình."""
    daily = weeks_to_daily(FLAT)
    for day in (10, 45, 80, len(daily) - 3):  # giữa chuỗi và hai ngày gần hôm qua
        d = list(daily)
        d[day] += 9_000_000
        pub, ev = publisher()
        pipe, _ = make_pipeline(d, publisher=pub)
        store = FlagStore()
        out = change.detect_and_store(pipe, USER, NOW, store=store)
        assert out.confirmed == [] and store.rows == [] and ev.entries == [], day
        sus = change.suspect_and_store(pipe, USER, NOW, store=store)
        assert sus.suspected == [] and store.rows == [], day


def test_chuoi_phang_khong_co_dau_hieu():
    pipe, _ = make_pipeline(weeks_to_daily(FLAT))
    store = FlagStore()
    assert change.detect_and_store(pipe, USER, NOW, store=store).to_dict().get("confirmed") is None
    assert store.rows == []


def test_phat_su_kien_that_bai_khong_lam_hong_va_lan_sau_phat_lai():
    ev = FakeEvents(fail_times=1)
    pub, _ = publisher(ev)
    pipe, _ = make_pipeline(weeks_to_daily(SHIFTED), publisher=pub)
    store = FlagStore()
    first = change.detect_and_store(pipe, USER, NOW, store=store)
    assert first.confirmed == ["an_uong"] and first.published == [] and ev.entries == []
    assert "event_published_at" not in store.rows[0]["detail"]  # chưa tới bus: để lần sau
    second = change.detect_and_store(pipe, USER, NOW + timedelta(hours=24), store=store)
    assert second.confirmed == [] and second.published == [store.rows[0]["id"]]
    assert len(ev.entries) == 1 and ev.details[0]["event_id"] == store.rows[0]["id"]
    third = change.detect_and_store(pipe, USER, NOW + timedelta(hours=48), store=store)
    assert third.published == [] and len(ev.entries) == 1


def test_khong_co_publisher_thi_van_ghi_dau_hieu():
    pipe, _ = make_pipeline(weeks_to_daily(SHIFTED), publisher=None)
    store = FlagStore()
    out = change.detect_and_store(pipe, USER, NOW, store=store)
    assert out.confirmed == ["an_uong"] and out.published == []


def test_nang_dau_hieu_nghi_thanh_xac_nhan_cung_flag_id():
    pub, ev = publisher()
    pipe, _ = make_pipeline(weeks_to_daily(SHIFTED), publisher=pub)
    store = FlagStore()
    sus = change.suspect_and_store(pipe, USER, NOW, store=store)
    assert sus.suspected == ["an_uong"] and ev.entries == []  # nghi: KHÔNG phát sự kiện
    (s,) = store.rows
    assert (s["status"], s["method"]) == ("suspected", "cusum") and s["confirmed_app_date"] is None
    assert (
        s["detail"]["detector"] == "cusum"
        and s["detail"]["calibration"]["detector"] == "suspect_cusum"
    )
    flag_id = s["id"]
    out = change.detect_and_store(pipe, USER, NOW, store=store)
    assert out.confirmed == ["an_uong"] and len(store.rows) == 1
    (c,) = store.rows
    assert c["id"] == flag_id and (c["status"], c["method"]) == ("confirmed", "pelt")
    assert c["detail"]["suspected"]["detector"] == "cusum"
    assert [d["event_id"] for d in ev.details] == [flag_id]


def test_dau_hieu_nghi_chua_xac_nhan_qua_han_thi_bao_nham():
    pipe, _ = make_pipeline(weeks_to_daily(FLAT))
    old = APP_DATE - timedelta(days=P.suspect_expire_weeks * 7 + 1)
    young = APP_DATE - timedelta(days=P.suspect_expire_weeks * 7 - 1)
    for when, expect in ((old, "dismissed"), (young, "suspected")):
        store = FlagStore(
            [
                {
                    "jar_code": "an_uong",
                    "status": "suspected",
                    "method": "cusum",
                    "direction": "up",
                    "old_weekly_vnd": 500_000,
                    "new_weekly_vnd": 800_000,
                    "suspected_app_date": when,
                    "detail": {"detector": "cusum"},
                }
            ]
        )
        out = change.detect_and_store(pipe, USER, NOW, store=store)
        assert store.rows[0]["status"] == expect
        assert (out.dismissed == ["an_uong"]) == (expect == "dismissed")
        if expect == "dismissed":
            assert store.rows[0]["detail"]["dismissed"]["reason"] == "not_confirmed"


def test_chi_phan_tich_hu_chi_tieu_va_ghi_ly_do_bo_qua():
    sparse = [0, 0, 300_000, 0, 0, 0, 0, 0, 0, 0] * 9
    other = jar_row(
        "giai_tri", "spending", 760_000, 20, 2, sparse[: len(weeks_to_daily(SHIFTED))] + [0] * 5
    )
    daily = weeks_to_daily(SHIFTED)
    other["spend"] = (sparse * 10)[: len(daily)]
    saving = jar_row("du_phong", "saving", 1_000_000, 10, 3, [500_000] * len(daily))
    pipe, _ = make_pipeline(daily, extra_jars=(other, saving))
    store = FlagStore()
    out = change.detect_and_store(pipe, USER, NOW, store=store)
    assert out.checked == ["an_uong"] and out.skipped == {"giai_tri": "sparse"}
    assert {r["jar_code"] for r in store.rows} == {
        "an_uong"
    }  # hũ tiết kiệm, nghĩa vụ không có "thói quen chi"


def test_it_lich_su_thi_bo_qua_va_ho_so_chua_du_thi_khong_lam_gi():
    pipe, _ = make_pipeline(weeks_to_daily(SHIFTED[:4]))
    out = change.detect_and_store(pipe, USER, NOW, store=FlagStore())
    assert out.skipped == {"an_uong": "insufficient_history"} and out.checked == []
    pipe2 = Pipeline(
        MemoryRepo([]), make_settings(), None, clock=lambda: NOW
    )  # người dùng chưa có hồ sơ
    store = FlagStore()
    out2 = change.detect_and_store(pipe2, USER, NOW, store=store)
    assert out2.confirmed == [] and store.rows == [] and out2.reason == "PROFILE_INCOMPLETE"


def test_loi_mot_hu_khong_lam_hong_hu_khac(monkeypatch):
    other = jar_row("di_lai", "spending", 640_000, 7, 2, weeks_to_daily(SHIFTED, seed=5))
    pipe, _ = make_pipeline(weeks_to_daily(SHIFTED), extra_jars=(other,))
    real = ml.detect_confirmed

    def flaky(series, params, **kw):
        if series.raw[0] == pytest.approx(ml.weekly_totals(np.asarray(other["spend"], float))[0]):
            raise ValueError("boom")
        return real(series, params, **kw)

    monkeypatch.setattr(ml, "detect_confirmed", flaky)
    store = FlagStore()
    out = change.detect_and_store(pipe, USER, NOW, store=store)
    assert out.confirmed == ["an_uong"] and out.errors == ["di_lai: ValueError"]


def test_khong_co_kho_thi_bo_qua_va_repo_khong_db_khong_gay_loi():
    pipe, _ = make_pipeline(weeks_to_daily(SHIFTED))
    assert change.store_for(pipe) is None
    assert change.detect_and_store(pipe, USER, NOW).reason == "no_store"
    assert change.suspect_and_store(pipe, USER, NOW).reason == "no_store"


# --- đường sự kiện: nghi ------------------------------------------------------------------------------------------
def test_nghi_chi_nhin_cac_hu_trong_su_kien():
    other = jar_row("di_lai", "spending", 640_000, 7, 2, weeks_to_daily(SHIFTED, seed=5))
    pipe, _ = make_pipeline(weeks_to_daily(SHIFTED), extra_jars=(other,))
    store = FlagStore()
    out = change.suspect_and_store(pipe, USER, NOW, ["di_lai"], store=store)
    assert out.checked == ["di_lai"] and {r["jar_code"] for r in store.rows} == {"di_lai"}


def test_nghi_cap_nhat_so_cua_dau_hieu_nghi_dang_mo_va_khong_dong_vao_dau_hieu_da_xac_nhan():
    pipe, _ = make_pipeline(weeks_to_daily(SHIFTED))
    store = FlagStore()
    change.suspect_and_store(pipe, USER, NOW, store=store)
    first = copy.deepcopy(store.rows[0])
    again = change.suspect_and_store(pipe, USER, NOW + timedelta(hours=1), store=store)
    assert again.suspected == [] and len(store.rows) == 1
    assert (
        store.rows[0]["id"] == first["id"]
        and store.rows[0]["suspected_app_date"] == first["suspected_app_date"]
    )
    store.rows[0]["status"] = "confirmed"
    store.rows[0]["confirmed_app_date"] = APP_DATE
    snapshot = copy.deepcopy(store.rows)
    change.suspect_and_store(pipe, USER, NOW + timedelta(hours=2), store=store)
    assert store.rows == snapshot


# --- consumer ----------------------------------------------------------------------------------------------------------
def tx_record(i="m1", event_id="e1", jars=("an_uong",)) -> dict:
    detail = {
        "v": 1,
        "event_id": event_id,
        "user_id": USER,
        "kind": "expense",
        "funding_source": "jar",
        "jar_codes": list(jars),
    }
    return {
        "messageId": i,
        "body": json.dumps(
            {"source": "yofina.ledger", "detail-type": "transaction.recorded", "detail": detail}
        ),
    }


def consumer_env(spend, **kw):
    pipe, repo = make_pipeline(spend, **kw)
    idem = IdempotencyStore(
        "t", FakeDynamo(), ttl_seconds=3600, lease_seconds=120, clock=lambda: 1_000_000.0
    )
    return pipe, repo, idem


def test_consumer_ghi_dau_hieu_nghi_sau_du_bao_va_khong_phat_su_kien():
    pub, ev = publisher()
    pipe, repo, idem = consumer_env(weeks_to_daily(SHIFTED), publisher=pub)
    store = FlagStore()
    report = process_records([tx_record()], pipe, idem, change_store=store)
    assert report.processed == 1 and report.failures == [] and repo.saves == 1
    assert [r["status"] for r in store.rows] == ["suspected"] and store.rows[0]["method"] == "cusum"
    assert report.changes and report.changes[0]["suspected"] == ["an_uong"]
    assert [e["DetailType"] for e in ev.entries] == [
        "forecast.updated"
    ]  # không có behavior.changed


def test_loi_o_buoc_nghi_khong_lam_hong_cap_nhat_du_bao(caplog):
    pipe, repo, idem = consumer_env(weeks_to_daily(SHIFTED))
    store = FlagStore()
    store.fail_list = True
    report = process_records([tx_record()], pipe, idem, change_store=store)
    assert report.processed == 1 and report.failures == [] and repo.saves == 1
    assert report.changes == []
    assert any("change_suspect_failed" in r.message for r in caplog.records)
    # sự kiện đã `done`: giao lại thì bị coi là trùng, không tính lại
    again = process_records([tx_record()], pipe, idem, change_store=store)
    assert again.duplicates == 1 and repo.saves == 1


def test_consumer_khong_nghi_khi_khong_co_gi_de_lam_hoac_chuoi_phang():
    pipe, _repo, idem = consumer_env(weeks_to_daily(FLAT))
    store = FlagStore()
    report = process_records([tx_record()], pipe, idem, change_store=store)
    assert report.processed == 1 and store.rows == []
    credit = {
        "messageId": "m2",
        "body": json.dumps(
            {
                "source": "yofina.ledger",
                "detail-type": "transaction.recorded",
                "detail": {"v": 1, "event_id": "e2", "user_id": USER, "funding_source": "credit"},
            }
        ),
    }
    pipe2, _, idem2 = consumer_env(weeks_to_daily(SHIFTED))
    store2 = FlagStore()
    r2 = process_records([credit], pipe2, idem2, change_store=store2)
    assert r2.skipped == 1 and store2.rows == []  # mua bằng hạn mức: không có việc, không nghi


def test_consumer_repo_khong_db_van_chay_binh_thuong():
    pipe, _repo, idem = consumer_env(weeks_to_daily(SHIFTED))
    report = process_records([tx_record()], pipe, idem)  # không kho, repo trong bộ nhớ không có db
    assert report.processed == 1 and report.failures == [] and report.changes == []


def test_thu_tu_va_hop_dong_hang_so():
    assert change.SPENDING_KIND == "spending" and set(change.OPEN_STATUSES) == {
        "suspected",
        "confirmed",
    }
    schema = load_json(CONTRACTS / "events" / "behavior.changed.schema.json")
    assert schema["properties"]["method"] == {
        "const": "pelt",
        "description": schema["properties"]["method"]["description"],
    }


def test_dau_hieu_nap_san_cua_persona_khong_bi_phat_lai_su_kien():
    """Dấu hiệu `confirmed` do seed persona (không phải do PELT này tạo) không được phát `behavior.changed` ở batch đêm."""
    pub, ev = publisher()
    pipe, _ = make_pipeline(weeks_to_daily(FLAT), publisher=pub)
    store = FlagStore(
        [
            {
                "jar_code": "an_uong",
                "status": "confirmed",
                "direction": "up",
                "old_weekly_vnd": 520_000,
                "new_weekly_vnd": 810_000,
                "change_point_date": date(2026, 11, 4),
                "confirmed_app_date": date(2026, 11, 20),
                "weeks_held": 2,
                "detail": {"source": "persona_seed"},
            }
        ]
    )
    out = change.detect_and_store(pipe, USER, NOW, store=store)
    assert out.published == [] and ev.entries == []
