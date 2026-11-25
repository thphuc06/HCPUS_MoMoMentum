"""Phát hiện đổi hành vi trên PostgreSQL thật cục bộ: SQL thật của `behavior_flags` (migration 0052: CHECK, chỉ mục duy nhất một phần, RLS),
chuỗi chi tiêu thật từ `app_get_forecast_context` của persona `minh`, PELT thật (`ruptures`) và sự kiện `behavior.changed` đúng hợp đồng.

Persona `minh` KHÔNG có điểm gãy cài sẵn (issue #8: 120 ngày lịch sử; issue #22: seed không có dấu hiệu): sau khi đặt lại không có dấu
hiệu nào. Đổi hành vi đến từ cảnh 4 chạy thật: nạp tệp `data/personas/samples/minh_sao_ke_2_tuan.csv` qua đúng đường nạp (REST
`/ingest/*`, worker, `confirm_rows`, như `test_ingest_flow.py`), các dòng chi vào hũ Ăn uống (funding `external`), rồi PELT xác nhận. Số
kỳ vọng của dấu hiệu (mức cũ, mức mới, số tuần giữ, ngày gãy) tính bằng chính bộ phát hiện (`yofina_ml.change`) trên chuỗi chi của bộ
sinh persona cộng các dòng vừa nạp, không chép số.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pytest
from conftest import ANCHOR, REPO
from pipeline_helpers import make_settings
from test_ingest_flow import Ctx, ThrottledBedrock

from yofina_forecast import change
from yofina_forecast.events import ForecastEventPublisher
from yofina_forecast.repo import ForecastRepo
from yofina_forecast.runner import Pipeline
from yofina_ml import change as ch
from yofina_ml.backtest.change_calibration import persona_daily_spend

# người dùng riêng mang persona minh: lần nạp ghi audit `confirm_rows` (không xóa khi đặt lại), không được lẫn vào ca của `sub-minh`
MINH, LAN, KHOA = "sub-canh4-minh", "sub-lan", "sub-khoa"
SCENE4_CSV = REPO / "data" / "personas" / "samples" / "minh_sao_ke_2_tuan.csv"


class FakeEvents:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def put_events(self, Entries):
        self.entries.extend(Entries)
        return {"FailedEntryCount": 0}


def event_validator():
    """Validator của schema `behavior.changed` với registry của mọi schema trong contracts/ ($ref liên file)."""
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    contracts = REPO / "contracts"
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


def upload_scene4(env, user: str = MINH) -> list[tuple[date, int]]:
    """Cảnh 4: tải tệp sao kê hai tuần qua REST nạp, worker đọc và phân loại, chốt mọi dòng đã tự chọn hũ bằng `confirm_rows`.
    Trả (ngày mô phỏng, số tiền chi) của các dòng đã ghi vào sổ cái."""
    ing = Ctx(env)
    up = ing.upload(user, kind="csv", mime="text/csv")
    ing.run_worker(up, SCENE4_CSV.read_bytes(), ThrottledBedrock())
    job = ing.job(up["job_id"], user=user)
    assert job["status"] == "review", job
    rows = job["review"]["data"]["rows"]
    # mọi dòng tự chọn sẵn hũ Ăn uống, không cần model (cảnh 4 trên app)
    assert rows and {r["suggested_jar"]["code"] for r in rows} == {"an_uong"}
    code, receipt = ing.confirm({"job_id": up["job_id"], "rows": [{"row_id": r["row_id"]} for r in rows]}, user=user)
    assert code == 200, receipt
    with env.master() as m:
        ext = m.execute(
            "SELECT app_date, amount_vnd FROM transactions WHERE user_id = %s AND funding_source = 'external' "
            "AND kind = 'expense' AND jar_code = 'an_uong'",
            [user],
        ).fetchall()
    assert len(ext) == len(rows)
    return [(d, -int(a)) for d, a in ext]


def expected_confirmed(loaded: list[tuple[date, int]]) -> tuple[ch.Confirmed, date]:
    """Dấu hiệu mà bộ phát hiện phải tìm: chuỗi chi Ăn uống của bộ sinh persona (đúng định nghĩa của sổ cái) cộng các dòng vừa nạp,
    tuần mới nhất kết thúc hôm qua. Trả kết quả PELT và ngày đầu của đoạn mới."""
    params = ch.load_params()
    daily = np.array(persona_daily_spend("minh", ANCHOR)["an_uong"], dtype=float)
    for day, amount in loaded:
        daily[len(daily) - (ANCHOR - day).days] += amount
    series = ch.prepare_weekly(daily, params)
    hit = ch.detect_confirmed(series, params)
    assert hit is not None and hit.direction == "up"
    return hit, ch.week_start_date(ANCHOR - timedelta(days=1), series.n_weeks, hit.change_index)


@pytest.fixture()
def minh(env):
    env.reset(MINH, "minh")
    return env


def test_dat_lai_khong_co_dau_hieu_nao_va_bo_phat_hien_khong_tao(minh):
    """Seed không cài dấu hiệu, lịch sử 120 ngày không có điểm gãy: không bảng dấu hiệu, không xác nhận, không nghi, không sự kiện."""
    assert flags(minh, MINH) == []
    p, ev = pipe(minh)
    out = change.detect_and_store(p, MINH, minh.clock.now)
    assert out.confirmed == [] and out.errors == [] and out.app_date == ANCHOR.isoformat()
    assert change.suspect_and_store(p, MINH, minh.clock.now, ["an_uong"]).suspected == []
    assert flags(minh, MINH) == [] and ev.entries == []


def test_nap_sao_ke_canh_4_thi_pelt_xac_nhan_an_uong_ghi_dau_hieu_that_va_phat_su_kien(minh):
    loaded = upload_scene4(minh)
    hit, start = expected_confirmed(loaded)
    p, ev = pipe(minh)
    out = change.detect_and_store(p, MINH, minh.clock.now)
    assert out.confirmed == ["an_uong"] and out.errors == [] and out.app_date == ANCHOR.isoformat()
    (f,) = flags(minh, MINH)
    assert (f["jar_code"], f["status"], f["method"], f["direction"]) == ("an_uong", "confirmed", "pelt", "up")
    assert f["weeks_held"] == hit.weeks_held and f["change_point_date"] == start
    assert (int(f["old_weekly_vnd"]), int(f["new_weekly_vnd"])) == (hit.old_weekly_vnd, hit.new_weekly_vnd)
    # đoạn mới bắt đầu không sau dòng sớm nhất của tệp (tệp phủ hai tuần cuối, tuần mới nhất kết thúc hôm qua)
    assert start <= min(d for d, _ in loaded)
    assert f["confirmed_app_date"] == ANCHOR and f["suspected_app_date"] == ANCHOR
    d = f["detail"]
    assert d["detector"] == "pelt" and d["cost"] == "l2" and d["calibration"]["synthetic_only"] is True
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
    upload_scene4(minh)
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
    upload_scene4(minh)
    p, _ = pipe(minh)
    assert change.detect_and_store(p, MINH, minh.clock.now).confirmed == ["an_uong"]
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
        "suspected_app_date": ANCHOR,
        "change_point_date": ANCHOR - timedelta(days=20),
        "confirmed_app_date": ANCHOR,
        "weeks_held": 2,
        "detail": {},
    }
    assert store.insert(MINH, row) is False  # ON CONFLICT DO NOTHING trên chỉ mục một phần
    assert len(flags(minh, MINH)) == 1


def test_dau_hieu_da_dung_o_gan_diem_gay_thi_khong_tao_lai(minh):
    upload_scene4(minh)
    p, _ = pipe(minh)
    assert change.detect_and_store(p, MINH, minh.clock.now).confirmed == ["an_uong"]
    with minh.master() as c:
        c.execute(
            "UPDATE behavior_flags SET status = 'applied', applied_at = now() WHERE user_id = %s",
            (MINH,),
        )
    out = change.detect_and_store(p, MINH, minh.clock.now + timedelta(days=1))
    assert out.confirmed == [] and [f["status"] for f in flags(minh, MINH)] == ["applied"]


def test_rls_nguoi_dung_khac_khong_thay_dau_hieu(minh):
    upload_scene4(minh)
    p, _ = pipe(minh)
    assert change.detect_and_store(p, MINH, minh.clock.now).confirmed == ["an_uong"]
    minh.reset(LAN)
    assert flags(minh, LAN) == []
    assert len(flags(minh, MINH)) == 1


def test_lan_va_khoa_khong_co_dau_hieu(env):
    for user in (LAN, KHOA):
        env.reset(user)
        assert flags(env, user) == []
        p, ev = pipe(env)
        out = change.detect_and_store(p, user, env.clock.now)
        assert out.confirmed == [] and flags(env, user) == [] and ev.entries == []
        assert change.suspect_and_store(p, user, env.clock.now).suspected == []
