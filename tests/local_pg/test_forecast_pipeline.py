"""Pipeline dự báo trên PostgreSQL thật cục bộ: SQL thật (migration 0009), RLS thật, engine `yofina_ml` thật, sổ cái thật.

Kiểm cả chuỗi: đặt lại persona -> `Pipeline.run_user` -> bảng dự báo -> `GET /forecasts` (khối) và consumer sự kiện của ledger.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from conftest import ANCHOR
from pipeline_helpers import FakeDynamo, make_settings

from personas import generate
from yofina_core.blocks import block_to_wire
from yofina_forecast.consumer import process_records
from yofina_forecast.idempotency import IdempotencyStore
from yofina_forecast.repo import ForecastRepo
from yofina_forecast.runner import Pipeline
from yofina_forecast.tool import ForecastReader, ReadSettings, get_forecast
from yofina_ledger.events import Event

MINH, LAN, KHOA = "sub-minh", "sub-lan", "sub-khoa"


def pipeline(env, **kw) -> Pipeline:
    return Pipeline(
        ForecastRepo(env.db),
        make_settings(n_paths_full=10000, n_paths_fast=5000, **kw),
        None,
        clock=env.clock,
    )


def summaries(env, user):
    return {r["jar_code"]: r for r in env.repo.forecast_summaries(user)}


def envelope(ev: Event, i: int) -> dict:
    return {
        "messageId": f"m{i}",
        "body": json.dumps(
            {"source": "yofina.ledger", "detail-type": ev.detail_type, "detail": ev.detail}
        ),
    }


def idem() -> IdempotencyStore:
    return IdempotencyStore("t", FakeDynamo(), ttl_seconds=3600, lease_seconds=120)


# --- tiêu chí 1: cảnh 1 của demo -------------------------------------------------------------------------
def test_reset_minh_an_uong_can_ngay_23_11_voi_engine_that(env):
    env.reset(MINH)
    out = pipeline(env).run_user(MINH, trigger="reset")
    assert out.status == "ok" and out.mode == "full" and out.app_date == "2026-11-21"
    s = summaries(env, MINH)
    assert set(s) == {"an_uong", "di_lai", "hoa_don", "giai_tri", "du_lich", "du_phong", "nghia_vu"}
    a = s["an_uong"]
    assert a["runout_date"] == date(2026, 11, 23)
    assert a["status"] == "short" and a["payday_date"] == date(2026, 12, 5)
    assert a["days_to_payday"] == 14 and int(a["start_balance_vnd"]) == 380_000
    # còn 12 ngày nữa mới tới kỳ lương tính từ ngày cạn (23/11 -> 5/12)
    assert (a["payday_date"] - a["runout_date"]).days == 12
    assert s["hoa_don"]["status"] in ("tight", "ok") and s["du_lich"]["status"] == "ok"
    assert s["di_lai"]["status"] == "ok" and s["giai_tri"]["status"] == "ok"
    assert all(r["series_kind"] in ("dense", "sparse") for r in s.values())
    assert a["forecast_floor_vnd"] is not None and int(a["forecast_floor_vnd"]) < 0


def test_ket_qua_on_dinh_qua_nhieu_lan_dat_lai(env):
    seen = []
    for _ in range(3):
        env.reset(MINH)
        pipeline(env).run_user(MINH, trigger="reset")
        s = summaries(env, MINH)
        seen.append(
            {
                c: (r["runout_date"], r["status"], r["p_shortfall"], r["forecast_floor_vnd"])
                for c, r in s.items()
            }
        )
    assert seen[0] == seen[1] == seen[2]


def test_khoa_la_uoc_luong_ban_dau_khong_co_xac_suat(env):
    env.reset(KHOA)
    out = pipeline(env).run_user(KHOA, trigger="reset")
    assert out.is_initial_estimate is True and out.history_days == 18
    for r in summaries(env, KHOA).values():
        assert r["is_initial_estimate"] is True and r["confidence_band"] == "low"
        assert r["show_probability"] is False and r["p_shortfall"] is None
        assert r["series_kind"] == "cold_start"


# --- đọc: khối của ledger và của tool là MỘT --------------------------------------------------------------
def test_tool_va_rest_tra_cung_mot_khoi_so_lieu(env):
    env.reset(MINH)
    p = pipeline(env)
    reader = ForecastReader(
        env.repo,
        ReadSettings(env.svc.settings.forecast_freshness_seconds, "Asia/Ho_Chi_Minh"),
        env.clock,
    )
    tool = get_forecast(
        reader, p, MINH, "an_uong", trace_id="t" * 8
    )  # chưa có dự báo: tool tự tính
    rest = env.svc.forecast_response(MINH, "an_uong", trace_id="t" * 8)
    assert tool["status"] == "OK" and tool["data"] == rest["data"]
    assert tool["data"]["runout_date"] == "2026-11-23" and tool["data"]["stale"] is False
    kinds = {(e["kind"], e["date"]) for e in tool["data"]["events"]}
    assert ("salary", "2026-12-05") in kinds and ("obligation", "2026-11-23") in kinds


def test_doc_cu_thi_stale_va_tool_tinh_lai(env):
    env.reset(MINH)
    p = pipeline(env)
    p.run_user(MINH, trigger="nightly")
    reader = ForecastReader(env.repo, ReadSettings(900, "Asia/Ho_Chi_Minh"), env.clock)
    assert (
        reader.forecast_block(MINH, "an_uong", trace_id="t" * 8, source_tool="x").data.stale
        is False
    )
    env.clock.now += timedelta(hours=2)  # quá độ tươi 900 giây
    assert (
        reader.forecast_block(MINH, "an_uong", trace_id="t" * 8, source_tool="x").data.stale is True
    )
    out = get_forecast(reader, p, MINH, "an_uong", trace_id="t" * 8)
    assert out["data"]["stale"] is False  # tool đã tính lại rồi đọc lại


# --- tiêu chí 2, 9: giao dịch -> chỉnh nhanh, gửi trùng ---------------------------------------------------
def test_giao_dich_200k_chinh_nhanh_hu_an_uong_va_gui_trung_khong_tinh_hai_lan(env):
    env.reset(MINH)
    p = pipeline(env)
    full = p.run_user(MINH, trigger="nightly")
    before = summaries(env, MINH)
    env.events.sent.clear()
    env.act(
        MINH,
        "record_transaction",
        {"kind": "expense", "amount_vnd": 200_000, "jar": "an_uong", "tx_type": "food_drink", "counterparty": "Cơm tấm"},
    )  # fmt: skip
    evs = [e for e in env.events.sent if e.detail_type == "transaction.recorded"]
    assert len(evs) == 1
    store = idem()
    env.clock.now += timedelta(minutes=1)
    rep = process_records([envelope(evs[0], 1)], p, store)
    assert rep.failures == [] and rep.processed == 1
    assert rep.runs[0]["mode"] == "fast" and rep.runs[0]["jar_codes"] == ["an_uong"]
    after = summaries(env, MINH)
    assert int(after["an_uong"]["start_balance_vnd"]) == 180_000
    assert after["an_uong"]["run_id"] != before["an_uong"]["run_id"]
    assert after["an_uong"]["runout_date"] <= date(
        2026, 11, 23
    )  # còn 180.000: không muộn hơn lúc trước
    latest = env.repo.forecast_series(MINH, "an_uong")  # chuỗi của lần chạy nhanh mới nhất
    assert int(latest[0]["balance_p50_vnd"]) < 180_000
    assert (
        after["di_lai"]["run_id"] == before["di_lai"]["run_id"] == full.run_id
    )  # hũ khác giữ dự báo cũ
    with env.master() as m:
        n = m.execute(
            "SELECT count(*) FROM forecast_runs WHERE source_event_id = %s",
            (evs[0].detail["event_id"],),
        ).fetchone()[0]
    assert n == 1
    again = process_records([envelope(evs[0], 2)], p, store)  # gửi trùng cùng event_id
    assert again.duplicates == 1 and again.processed == 0
    with env.master() as m:
        n2 = m.execute(
            "SELECT count(*) FROM forecast_runs WHERE source_event_id = %s",
            (evs[0].detail["event_id"],),
        ).fetchone()[0]
    assert n2 == 1


# --- tiêu chí 6: Trả sau hiện thành mốc ---------------------------------------------------------------
def test_mua_tra_sau_300k_thanh_moc_tren_bieu_do_hu_nghia_vu(env):
    env.reset(MINH)
    p = pipeline(env)
    p.run_user(MINH, trigger="nightly")
    reader = ForecastReader(env.repo, ReadSettings(900, "Asia/Ho_Chi_Minh"), env.clock)

    def bnpl_mark():
        b = reader.forecast_block(MINH, "nghia_vu", trace_id="t" * 8, source_tool="x")
        return next(e for e in b.data.events if e.kind == "obligation" and e.date == "2026-12-05")

    assert bnpl_mark().amount_vnd == 1_000_000
    env.events.sent.clear()
    env.act(
        MINH,
        "record_transaction",
        {"kind": "expense", "amount_vnd": 300_000, "jar": "giai_tri", "tx_type": "entertainment",
         "funding": "credit", "counterparty": "Tiki"},
    )  # fmt: skip
    rep = process_records(
        [
            envelope(e, i)
            for i, e in enumerate(env.events.sent)
            if e.detail_type != "forecast.updated"
        ],
        p,
        idem(),
    )
    assert rep.failures == []
    assert (
        bnpl_mark().amount_vnd == 1_300_000
    )  # mua thêm cộng dồn vào nghĩa vụ trả sau đang có (phí đã tính một lần)


# --- hạ tầng DB: hàm liệt kê người dùng, RLS, dọn lần chạy -----------------------------------------------
def test_ham_liet_ke_nguoi_dung_va_rls(env):
    for u in (MINH, LAN, KHOA):
        env.reset(u)
    repo = ForecastRepo(env.db)
    users = repo.users(100)
    assert {MINH, LAN, KHOA} <= set(users)
    assert repo.context("nguoi-la", env.clock.now, "Asia/Ho_Chi_Minh", 330) == []
    p = pipeline(env)
    p.run_user(MINH, trigger="nightly")
    assert summaries(env, LAN) == {} and len(summaries(env, MINH)) == 7  # RLS: không thấy của nhau


def test_don_lan_chay_cu_khong_lam_mat_du_bao_cua_hu_khac(env):
    env.reset(MINH)
    p = pipeline(env, keep_runs=2)
    p.run_user(MINH, trigger="nightly")
    for i in range(5):
        env.clock.now += timedelta(seconds=60)
        out = p.run_user(MINH, trigger="event", jar_codes=["an_uong"], source_event_id=f"e{i}")
        assert out.mode == "fast"
    s = summaries(env, MINH)
    assert len(s) == 7  # lần chạy đầy đủ vẫn còn vì là lần mới nhất của sáu hũ kia
    with env.master() as m:
        # chỉ lần chạy của MINH: Postgres cục bộ dùng chung cả phiên, test khác để lại lần chạy của người dùng khác
        runs = m.execute("SELECT count(*) FROM forecast_runs WHERE user_id = %s", [MINH]).fetchone()[0]
    assert runs <= 4
    assert env.repo.forecast_series(MINH, "di_lai")  # chuỗi ngày của hũ khác còn nguyên


def test_hai_lan_chay_cung_du_lieu_cung_ket_qua_va_ghi_dung_cot(env):
    env.reset(MINH)
    p = pipeline(env)
    p.run_user(MINH, trigger="manual")
    first = {c: env.repo.forecast_series(MINH, c) for c in ("an_uong", "du_lich")}
    env.clock.now += timedelta(seconds=1)
    run_id = p.run_user(MINH, trigger="manual").run_id
    second = {c: env.repo.forecast_series(MINH, c) for c in ("an_uong", "du_lich")}
    strip = lambda rows: [{k: v for k, v in r.items() if k != "run_id"} for r in rows]  # noqa: E731
    assert strip(first["an_uong"]) == strip(second["an_uong"])
    assert strip(first["du_lich"]) == strip(second["du_lich"])
    with env.master() as m:
        run = m.execute(
            "SELECT trigger, model, history_days, n_paths, seed, params->'pipeline'->>'mode' "
            "FROM forecast_runs WHERE id = %s", [run_id]
        ).fetchone()
    # số ngày lịch sử của lần chạy là số ngày lịch sử mà bộ sinh persona tạo cho minh (120 ngày từ issue #8), không chép số
    assert run[0] == "manual" and run[1] == "hurdle_calendar" and run[2] == generate("minh", anchor=ANCHOR).history_days
    assert run[3] == 10000 and run[4] is not None and run[5] == "full"


def test_khoi_dung_hop_dong_va_so_trong_khoi_khop_bang(env):
    env.reset(MINH)
    pipeline(env).run_user(MINH, trigger="nightly")
    wire = block_to_wire(env.svc.forecast_block(MINH, "an_uong", trace_id="t" * 8, source_tool="x"))
    series = env.repo.forecast_series(MINH, "an_uong")
    assert [d["p50_vnd"] for d in wire["data"]["days"]] == [
        int(r["balance_p50_vnd"]) for r in series
    ]
    assert wire["data"]["days"][0]["date"] == "2026-11-22" and len(wire["data"]["days"]) == 30


@pytest.mark.parametrize("persona", ["lan"])
def test_persona_khac_chay_duoc_va_co_xac_suat_khi_du_lich_su(env, persona):
    env.reset(f"sub-{persona}")
    out = pipeline(env).run_user(f"sub-{persona}", trigger="reset")
    assert out.status == "ok" and out.history_days == 47 and out.is_initial_estimate is False


# --- ledger gọi pipeline: đặt lại đồng bộ, Tổng quan kích hoạt nền, Chi tiết hũ tính lại khi cũ -----------------
class InProcessForecast:
    """Thay `ForecastClient` (gọi Lambda) bằng gọi thẳng `Pipeline` cùng tiến trình; ghi lại các lần gọi."""

    def __init__(self, pipeline: Pipeline) -> None:
        self.pipeline = pipeline
        self.computed: list[tuple[str, str]] = []
        self.requested: list[tuple[str, str]] = []

    def compute(self, user_id: str, trigger: str) -> bool:
        self.computed.append((user_id, trigger))
        return self.pipeline.run_user(user_id, trigger=trigger).status in ("ok", "skipped")

    def request(self, user_id: str, trigger: str = "read") -> bool:
        self.requested.append((user_id, trigger))
        return True


def test_dat_lai_tinh_du_bao_dong_bo_va_tra_forecast_ready_true(env):
    env.svc.forecast = fc = InProcessForecast(pipeline(env))
    r = env.svc.reset_demo(MINH, "minh", trace_id="t" * 8)
    assert r["forecast_ready"] is True and fc.computed == [(MINH, "reset")]
    ov = env.svc.overview_response(MINH)
    assert ov["forecast"] is not None and ov["forecast"]["stale"] is False and fc.requested == []
    an = next(j for j in ov["jars"] if j["code"] == "an_uong")
    assert an["status"] == "short" and an["runout_date"] == "2026-11-23"
    assert ov["proactive_card"]["data"]["kind"] == "runout_warning"
    assert "23/11" in ov["proactive_card"]["fallback_text"] or "2026-11-23" in json.dumps(
        ov["proactive_card"]
    )


def test_tong_quan_chua_co_du_bao_hoac_cu_thi_kich_hoat_nen_khong_cho(env):
    env.svc.forecast = fc = InProcessForecast(pipeline(env))
    env.svc.forecast = None
    env.reset(MINH)  # đặt lại KHÔNG tính (forecast None)
    env.svc.forecast = fc
    ov = env.svc.overview_response(MINH)
    assert ov["forecast"] is None and fc.requested == [(MINH, "read")] and fc.computed == []
    fc.pipeline.run_user(MINH, trigger="nightly")
    fc.requested.clear()
    assert env.svc.overview_response(MINH)["forecast"]["stale"] is False and fc.requested == []
    env.clock.now += timedelta(hours=2)
    ov2 = env.svc.overview_response(MINH)
    assert ov2["forecast"]["stale"] is True and fc.requested == [(MINH, "read")]


def test_get_forecasts_tinh_lai_dong_bo_khi_chua_co_hoac_cu(env):
    env.svc.forecast = fc = InProcessForecast(pipeline(env))
    env.svc.forecast = None
    env.reset(MINH)
    env.svc.forecast = fc
    first = env.svc.forecast_response(MINH, "an_uong", trace_id="t" * 8)  # chưa có: tính ngay
    assert fc.computed == [(MINH, "read")] and first["data"]["stale"] is False
    fc.computed.clear()
    env.svc.forecast_response(MINH, "an_uong", trace_id="t" * 8)  # còn tươi: không tính
    assert fc.computed == []
    env.clock.now += timedelta(hours=2)
    again = env.svc.forecast_response(
        MINH, "an_uong", trace_id="t" * 8
    )  # cũ: tính lại rồi trả bản mới
    assert fc.computed == [(MINH, "read")] and again["data"]["stale"] is False
    assert again["data"]["computed_at"] > first["data"]["computed_at"]


def test_get_forecasts_khong_co_pipeline_thi_503_nhu_cu(env):
    from yofina_core.errors import ErrorCode, YofinaError

    env.reset(MINH)
    with pytest.raises(YofinaError) as e:
        env.svc.forecast_response(MINH, "an_uong", trace_id="t" * 8)
    assert e.value.code == ErrorCode.FORECAST_UNAVAILABLE
