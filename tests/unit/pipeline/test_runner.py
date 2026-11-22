"""Lõi pipeline: chọn đường chỉnh nhanh hay đầy đủ, kiểm kết quả trước khi ghi, bảo vệ chống bão tính lại, phát sự kiện."""

from __future__ import annotations

from datetime import timedelta

import pytest
from memory_repo import MemoryRepo
from pipeline_helpers import NOW, context_rows, jar_row, make_settings

from yofina_core.errors import ErrorCode, YofinaError
from yofina_forecast.events import ForecastEventPublisher
from yofina_forecast.runner import Pipeline
from yofina_ml.api import forecast_user, update_forecast


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self):
        return self.now


class CapturePublisher(ForecastEventPublisher):
    def __init__(self) -> None:
        super().__init__("bus")
        self.sent: list[dict] = []

    def forecast_updated(self, **kw):  # type: ignore[override]
        self.sent.append(kw)
        return True


def make(rows=None, **settings):
    repo = MemoryRepo(rows if rows is not None else context_rows())
    clock = Clock()
    pub = CapturePublisher()
    calls = {"full": 0, "fast": 0}

    def full(inp):
        calls["full"] += 1
        return forecast_user(inp)

    def fast(inp, prev, jars):
        calls["fast"] += 1
        return update_forecast(inp, prev, jars)

    p = Pipeline(
        repo, make_settings(**settings), pub, clock=clock, forecast_fn=full, update_fn=fast
    )
    return p, repo, clock, pub, calls


def test_nightly_chay_day_du_ghi_mot_lan_va_phat_su_kien():
    p, repo, _clock, pub, calls = make()
    out = p.run_user("u", trigger="nightly")
    assert out.status == "ok" and out.mode == "full" and calls == {"full": 1, "fast": 0}
    assert out.jar_codes == ["an_uong", "giai_tri", "nghia_vu"]
    run = repo.runs[0]
    assert run["trigger"] == "nightly" and run["result"].run.n_paths == 600  # n_paths_full
    assert run["params"]["pipeline"]["mode"] == "full"
    assert "jar_state" in run["params"] and set(run["params"]["jar_state"]) == set(out.jar_codes)
    assert len(pub.sent) == 1 and pub.sent[0]["run_id"] == out.run_id
    assert pub.sent[0]["trigger"] == "nightly" and pub.sent[0]["jar_codes"] == out.jar_codes


def test_su_kien_giao_dich_chinh_nhanh_hu_lien_quan_voi_n_paths_fast():
    p, repo, clock, pub, calls = make()
    first = p.run_user("u", trigger="nightly")
    clock.now += timedelta(minutes=5)
    out = p.run_user("u", trigger="event", jar_codes=["an_uong"], source_event_id="evt-1")
    assert out.mode == "fast" and out.jar_codes == ["an_uong"] and calls["fast"] == 1
    run = repo.runs[-1]
    assert run["parent"] == first.run_id and run["source_event_id"] == "evt-1"
    assert run["result"].run.n_paths == 400  # n_paths_fast
    assert list(run["params"]["jar_state"]) == ["an_uong"]
    assert pub.sent[-1]["parent_event_id"] == "evt-1" and pub.sent[-1]["jar_codes"] == ["an_uong"]
    # các hũ khác vẫn dùng dự báo của lần chạy đầy đủ
    latest = {r["jar_code"]: r["run_id"] for r in repo.summaries("u")}
    assert latest["an_uong"] == out.run_id
    assert latest["giai_tri"] == first.run_id == latest["nghia_vu"]


def test_chinh_nhanh_hai_lan_lien_tiep_van_doc_duoc_trang_thai_tu_lan_chay_nhanh():
    p, repo, clock, _pub, calls = make()
    p.run_user("u", trigger="nightly")
    for i in range(2):
        clock.now += timedelta(minutes=1)
        out = p.run_user("u", trigger="event", jar_codes=["an_uong"], source_event_id=f"e{i}")
        assert out.mode == "fast"
    assert calls["fast"] == 2 and len(repo.runs) == 3


def test_so_du_doi_thi_phan_vi_so_du_doi_dung_chenh_lech():
    rows = context_rows()
    p, repo, clock, _pub, _calls = make(
        rows, n_paths_fast=600
    )  # cùng số đường thì cùng dãy ngẫu nhiên
    p.run_user("u", trigger="nightly")
    before = repo.runs[-1]["result"].jars[0].days
    for r in rows:
        if r["section"] == "jar" and r["jar_code"] == "an_uong":
            r["payload"]["balance_vnd"] -= 200_000
    clock.now += timedelta(minutes=1)
    out = p.run_user("u", trigger="event", jar_codes=["an_uong"])
    assert out.mode == "fast"
    after = repo.runs[-1]["result"].jars[0].days
    assert after[0].balance_p50_vnd == before[0].balance_p50_vnd - 200_000


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        ("none", "no_previous"),
        ("old", "previous_too_old"),
        ("date", "app_date_changed"),
    ],
)
def test_ly_do_roi_ve_chay_day_du(setup, reason):
    p, repo, clock, _pub, calls = make(fast_max_age_seconds=3600)
    if setup != "none":
        p.run_user("u", trigger="nightly")
    if setup == "old":
        clock.now += timedelta(hours=2)
    if setup == "date":
        for r in repo.context_rows:
            if r["section"] == "meta":
                r["payload"]["app_date"] = "2026-11-22"
                r["payload"]["history_start"] = "2026-10-05"
    out = p.run_user("u", trigger="event", jar_codes=["an_uong"])
    assert out.mode == "full" and out.fast_fallback == reason and calls["fast"] == 0
    assert repo.runs[-1]["params"]["pipeline"]["fast_fallback"] == reason
    assert out.jar_codes == ["an_uong", "giai_tri", "nghia_vu"]  # rơi về chạy đủ mọi hũ


def test_roi_ve_day_du_khi_params_thieu_phan_phoi_cua_hu():
    p, repo, _clock, _pub, calls = make()
    p.run_user("u", trigger="nightly")
    repo.runs[0]["params"]["jar_state"].pop("an_uong")
    out = p.run_user("u", trigger="event", jar_codes=["an_uong"])
    assert out.mode == "full" and out.fast_fallback == "no_jar_state" and calls["fast"] == 0


def test_vuot_nguong_khoi_dau_lanh_thi_chay_day_du():
    rows = context_rows(days=10)  # ước lượng ban đầu (dưới 21 ngày)
    p, _repo, _clock, _pub, calls = make(rows)
    first = p.run_user("u", trigger="nightly")
    assert first.is_initial_estimate is True
    for r in rows:
        if r["section"] == "meta":
            r["payload"]["history_start"] = "2026-09-01"
        if r["section"] == "jar":
            r["payload"]["spend"] = [50_000] * 81
    out = p.run_user("u", trigger="event", jar_codes=["an_uong"])
    assert out.mode == "full" and out.fast_fallback == "left_cold_start" and calls["fast"] == 0


def test_su_kien_hu_khong_du_bao_duoc_thi_bo_qua_khong_ghi():
    p, repo, _clock, pub, _calls = make()
    out = p.run_user("u", trigger="event", jar_codes=["tien_vao_khac"])
    assert out.status == "skipped" and out.reason == "no_forecastable_jar"
    assert repo.saves == 0 and pub.sent == []


def test_trigger_read_bi_chan_khi_vua_co_lan_chay_tre():
    p, repo, clock, _pub, calls = make(recompute_guard_seconds=20)
    p.run_user("u", trigger="nightly")
    clock.now = repo.tick + timedelta(seconds=5)
    out = p.run_user("u", trigger="read")
    assert out.status == "skipped" and out.reason == "fresh" and calls["full"] == 1
    clock.now = repo.tick + timedelta(seconds=30)
    assert p.run_user("u", trigger="read").status == "ok" and calls["full"] == 2
    # chưa có lần chạy nào thì chạy luôn
    p2, _r2, _c2, _p2, calls2 = make()
    assert p2.run_user("u", trigger="read").status == "ok" and calls2["full"] == 1


def test_ket_qua_sai_hop_dong_khong_duoc_ghi():
    p, repo, _clock, pub, _calls = make()

    def bad(inp):
        res = forecast_user(inp)
        from dataclasses import replace

        j0 = res.jars[0]
        broken = replace(j0.summary, start_balance_vnd=j0.summary.start_balance_vnd + 1)
        return replace(res, jars=(replace(j0, summary=broken), *res.jars[1:]))

    p._forecast = bad
    with pytest.raises(YofinaError) as e:
        p.run_user("u", trigger="nightly")
    assert e.value.code == ErrorCode.INTERNAL_ERROR
    assert repo.saves == 0 and pub.sent == []


def test_loi_ghi_khong_phat_su_kien_va_ho_so_thieu_bao_profile_incomplete():
    p, repo, _clock, pub, _calls = make()
    repo.fail_save = True
    with pytest.raises(RuntimeError):
        p.run_user("u", trigger="nightly")
    assert pub.sent == []
    p2, *_ = make(context_rows(salary=None))
    with pytest.raises(YofinaError) as e:
        p2.run_user("u", trigger="manual")
    assert e.value.code == ErrorCode.PROFILE_INCOMPLETE


def test_nguoi_dung_khong_co_ho_so_thi_profile_incomplete():
    p, *_ = make([])
    with pytest.raises(YofinaError) as e:
        p.run_user("u", trigger="nightly")
    assert e.value.code == ErrorCode.PROFILE_INCOMPLETE


def test_trigger_la_khong_hop_le():
    p, *_ = make()
    with pytest.raises(ValueError):
        p.run_user("u", trigger="khac")


def test_tai_khoan_18_ngay_la_uoc_luong_ban_dau_khong_co_xac_suat():
    rows = context_rows(
        days=18,
        jars=[
            jar_row("an_uong", "spending", 380_000, 100, 1, [80_000] * 18),
        ],
        obligations=[],
    )
    p, repo, _clock, _pub, _calls = make(rows)
    out = p.run_user("khoa", trigger="reset")
    assert out.is_initial_estimate is True and out.history_days == 18
    res = repo.runs[-1]["result"]
    assert res.run.confidence_label == "low"
    assert all(not j.summary.show_probability and j.summary.p_shortfall is None for j in res.jars)
    assert repo.runs[-1]["trigger"] == "reset"
