"""Phát hiện đổi hành vi trên PostgreSQL thật cục bộ: SQL thật của `behavior_flags` (migration 0052: CHECK, chỉ mục duy nhất một phần, RLS),
chuỗi chi tiêu thật từ `app_get_forecast_context` của persona `minh`, PELT thật (`ruptures`) và sự kiện `behavior.changed` đúng hợp đồng.

Persona `minh` có sẵn bước nhảy ở Ăn uống (chi tuần 514.000 -> 1.220.500 đồng, giữ 2 tuần, từ 7/11/2026): xem `data/personas/README.md`.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from pipeline_helpers import make_settings

from yofina_forecast import change
from yofina_forecast.events import ForecastEventPublisher
from yofina_forecast.repo import ForecastRepo
from yofina_forecast.runner import Pipeline

MINH, LAN, KHOA = "sub-minh", "sub-lan", "sub-khoa"


class FakeEvents:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def put_events(self, Entries):
        self.entries.extend(Entries)
        return {"FailedEntryCount": 0}


def event_validator():
    """Validator của schema `behavior.changed` với registry của mọi schema trong contracts/ ($ref liên file)."""
    from pathlib import Path

    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    contracts = Path(__file__).resolve().parents[2] / "contracts"
    reg = Registry()
    for path in sorted(contracts.glob("*/*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        reg = reg.with_resource(schema["$id"], Resource.from_contents(schema))
    ref = "https://contracts.yofina.invalid/events/behavior.changed.schema.json"
    return Draft202012Validator({"$ref": ref}, registry=reg)


def pipe(env):
    ev = FakeEvents()
    p = Pipeline(
        ForecastRepo(env.db),
        make_settings(n_paths_full=600, n_paths_fast=400),
        ForecastEventPublisher("bus", ev),
        clock=env.clock,
    )
    return p, ev


def flags(env, user: str, status: str | None = None):
    return env.db.query(
        "SELECT * FROM app_list_behavior_flags(CAST(:u AS text), CAST(:s AS text), 50)",
        {"u": user, "s": status},
    )


def clear_flags(env, user: str) -> None:
    """Bỏ dấu hiệu nạp sẵn của persona (nếu có) để kiểm bộ phát hiện từ trạng thái trống."""
    with env.master() as c:
        c.execute("DELETE FROM behavior_flags WHERE user_id = %s", (user,))


@pytest.fixture()
def minh(env):
    env.reset(MINH)
    clear_flags(env, MINH)
    return env


def test_minh_pelt_xac_nhan_an_uong_ghi_dau_hieu_that_va_phat_su_kien(minh):

    p, ev = pipe(minh)
    out = change.detect_and_store(p, MINH, minh.clock.now)
    assert out.confirmed == ["an_uong"] and out.errors == [] and out.app_date == "2026-11-21"
    assert set(out.skipped) >= {"di_lai", "hoa_don", "giai_tri"}  # thưa hoặc thiếu lịch sử
    (f,) = flags(minh, MINH)
    assert (f["jar_code"], f["status"], f["method"], f["direction"]) == (
        "an_uong",
        "confirmed",
        "pelt",
        "up",
    )
    assert f["weeks_held"] == 2 and f["change_point_date"] == date(2026, 11, 7)
    assert f["confirmed_app_date"] == date(2026, 11, 21) and f["suspected_app_date"] == date(
        2026, 11, 21
    )
    assert (
        450_000 < int(f["old_weekly_vnd"]) < 600_000
        and 1_100_000 < int(f["new_weekly_vnd"]) < 1_300_000
    )
    d = f["detail"]
    assert (
        d["detector"] == "pelt" and d["cost"] == "l2" and d["calibration"]["synthetic_only"] is True
    )
    assert d["params"]["pelt_penalty_c"] > 0 and "event_published_at" in d
    (e,) = ev.entries
    detail = json.loads(e["Detail"])
    assert detail["event_id"] == detail["flag_id"] == str(f["id"])
    assert list(event_validator().iter_errors(detail)) == []
    # chạy lại: không dấu hiệu thứ hai, không sự kiện thứ hai
    again = change.detect_and_store(p, MINH, minh.clock.now + timedelta(hours=24))
    assert again.confirmed == [] and again.published == [] and len(flags(minh, MINH)) == 1
    assert len(ev.entries) == 1


def test_nghi_roi_xac_nhan_cung_mot_dong(minh):
    p, ev = pipe(minh)
    sus = change.suspect_and_store(p, MINH, minh.clock.now, ["an_uong"])
    assert sus.suspected == ["an_uong"] and ev.entries == []
    (s,) = flags(minh, MINH)
    assert (s["status"], s["method"], s["confirmed_app_date"]) == ("suspected", "cusum", None)
    out = change.detect_and_store(p, MINH, minh.clock.now)
    assert out.confirmed == ["an_uong"]
    (c,) = flags(minh, MINH)
    assert c["id"] == s["id"] and (c["status"], c["method"]) == ("confirmed", "pelt")
    assert c["detail"]["suspected"]["detector"] == "cusum"
    assert json.loads(ev.entries[0]["Detail"])["event_id"] == str(s["id"])


def test_chi_muc_mot_dau_hieu_mo_moi_hu_chi_muc_duy_nhat_that(minh):
    p, _ = pipe(minh)
    change.detect_and_store(p, MINH, minh.clock.now)
    store = change.store_for(p)
    assert store is not None
    row = {
        "id": "00000000-0000-4000-8000-0000000000aa",
        "jar_code": "an_uong",
        "status": "confirmed",
        "method": "pelt",
        "direction": "up",
        "old_weekly_vnd": 1,
        "new_weekly_vnd": 2,
        "suspected_app_date": date(2026, 11, 21),
        "change_point_date": date(2026, 11, 1),
        "confirmed_app_date": date(2026, 11, 21),
        "weeks_held": 2,
        "detail": {},
    }
    assert store.insert(MINH, row) is False  # ON CONFLICT DO NOTHING trên chỉ mục một phần
    assert len(flags(minh, MINH)) == 1


def test_dau_hieu_da_dung_o_gan_diem_gay_thi_khong_tao_lai(minh):
    p, _ = pipe(minh)
    change.detect_and_store(p, MINH, minh.clock.now)
    with minh.master() as c:
        c.execute(
            "UPDATE behavior_flags SET status = 'applied', applied_at = now() WHERE user_id = %s",
            (MINH,),
        )
    out = change.detect_and_store(p, MINH, minh.clock.now + timedelta(days=1))
    assert out.confirmed == [] and [f["status"] for f in flags(minh, MINH)] == ["applied"]


def test_rls_nguoi_dung_khac_khong_thay_dau_hieu(minh):
    p, _ = pipe(minh)
    change.detect_and_store(p, MINH, minh.clock.now)
    minh.reset(LAN)
    assert flags(minh, LAN) == []
    assert len(flags(minh, MINH)) == 1


def test_lan_va_khoa_khong_co_dau_hieu(env):
    for user in (LAN, KHOA):
        env.reset(user)
        clear_flags(env, user)
        p, ev = pipe(env)
        out = change.detect_and_store(p, user, env.clock.now)
        assert out.confirmed == [] and flags(env, user) == [] and ev.entries == []
        assert change.suspect_and_store(p, user, env.clock.now).suspected == []
