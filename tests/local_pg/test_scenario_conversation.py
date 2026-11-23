"""Migration 0051 trên PostgreSQL thật cục bộ: hai cột mới của `scenarios` (conversation_id, bundle), ghi bằng `save_scenario` thật,
hàm `app_list_conversation_scenarios` (mới nhất trước, giới hạn, RLS: người khác không đọc được), dòng cũ NULL, đặt lại demo dọn.

Chạy cùng bộ local_pg (lệnh ở docstring của conftest.py)."""

from __future__ import annotations

import json
import uuid
from datetime import date

import psycopg
import pytest

from yofina_core.errors import YofinaError
from yofina_forecast.repo import ForecastRepo, list_conversation_scenarios, save_scenario

MINH, LAN = "sub-minh", "sub-lan"
CONV = "session-" + "a" * 30
DB_ERRORS = (psycopg.Error, YofinaError)
SPEC_A = {"kind": "one_time_purchase", "amount_vnd": 800_000, "funding_source": "jar", "jar_code": "giai_tri", "label": "giày", "date": "2026-11-21"}
SPEC_B = {**SPEC_A, "amount_vnd": 300_000, "label": "dép"}


def result(label: str, bundle: list[dict] | None = None) -> dict:
    out = {
        "n_paths": 600,
        "effects": [],
        "basis": {},
        "timelines": [{"compare": {"label": label, "kind": "one_time_purchase"}}],
    }
    if bundle is not None:
        out["bundle"] = bundle
    return out


def save(env, user, spec, *, conv=CONV, bundle=None, label="mua giày 800 nghìn", summary=None, keep=50):
    sid = str(uuid.uuid4())
    save_scenario(
        ForecastRepo(env.db),
        user,
        scenario_id=sid,
        trace_id="t" * 8,
        kind=spec["kind"],
        spec=spec,
        spec_hash="0" * 64,
        app_date=date(2026, 11, 21),
        baseline_run_id=None,
        n_paths=600,
        seed=7,
        result=result(label, summary),
        keep=keep,
        conversation_id=conv,
        bundle=bundle,
    )
    return sid


def listing(env, user, conv=CONV, limit=5):
    return list_conversation_scenarios(ForecastRepo(env.db), user, conv, limit)


@pytest.fixture
def minh(env):
    env.reset(MINH)
    env.reset(LAN)
    return MINH


def test_luu_conversation_id_va_bundle_roi_doc_lai_moi_nhat_truoc(env, minh):
    summary = [
        {"kind": "one_time_purchase", "label": "mua giày 800 nghìn", "amount_vnd": 800_000, "jar_code": "giai_tri", "spec": SPEC_A},
        {"kind": "one_time_purchase", "label": "mua dép 300 nghìn", "amount_vnd": 300_000, "jar_code": "giai_tri", "spec": SPEC_B},
    ]
    first = save(env, minh, SPEC_A, bundle=[SPEC_A])
    second = save(env, minh, SPEC_B, bundle=[SPEC_A, SPEC_B], label="mua giày 800 nghìn + mua dép 300 nghìn", summary=summary)
    rows = listing(env, minh)
    assert [str(r["id"]) for r in rows] == [second, first]  # mới nhất trước
    new, old = rows
    assert new["kind"] == "one_time_purchase" and new["spec"] == SPEC_B
    assert new["bundle"] == [SPEC_A, SPEC_B] and new["result_bundle"] == summary
    assert new["result_label"] == "mua giày 800 nghìn + mua dép 300 nghìn"
    assert old["bundle"] == [SPEC_A] and old["result_bundle"] is None and old["result_label"] == "mua giày 800 nghìn"
    assert new["created_at"] >= old["created_at"]


def test_cuoc_chat_khac_va_dong_khong_gan_cuoc_chat_khong_lot_vao(env, minh):
    mine = save(env, minh, SPEC_A, bundle=[SPEC_A])
    save(env, minh, SPEC_B, conv="session-" + "b" * 30, bundle=[SPEC_B])
    save(env, minh, SPEC_B, conv=None, bundle=None)  # như dòng trước 0051 hoặc gọi không truyền conversation_id
    assert [str(r["id"]) for r in listing(env, minh)] == [mine]
    assert listing(env, minh, conv="khong-co-cuoc-chat-nay") == []


def test_gioi_han_mac_dinh_5_kep_trong_1_den_10(env, minh):
    for i in range(12):
        save(env, minh, {**SPEC_B, "amount_vnd": 1000 * (i + 1)}, bundle=None, keep=50)
    assert len(listing(env, minh)) == 5
    assert len(listing(env, minh, limit=2)) == 2
    assert len(listing(env, minh, limit=0)) == 1  # kẹp xuống 1
    assert len(listing(env, minh, limit=99)) == 10  # kẹp lên 10
    amounts = [r["spec"]["amount_vnd"] for r in listing(env, minh, limit=3)]
    assert amounts == [12_000, 11_000, 10_000]


def test_rls_nguoi_khac_khong_doc_duoc_cuoc_chat_cua_minh(env, minh):
    save(env, minh, SPEC_A, bundle=[SPEC_A])
    assert len(listing(env, MINH)) == 1
    assert listing(env, LAN) == []  # cùng conversation_id nhưng khác người dùng
    # và lan không ghi được dòng mang user_id của minh (WITH CHECK của RLS)
    with pytest.raises(DB_ERRORS), env.db.transaction(LAN) as tx:
        tx.execute(
            "INSERT INTO scenarios (user_id, kind, spec, spec_hash, app_date, n_paths, result, conversation_id) "
            "VALUES (:uid, 'one_time_purchase', CAST(:spec AS jsonb), :h, CAST(:d AS date), 1, CAST(:r AS jsonb), :c)",
            {"uid": MINH, "spec": json.dumps(SPEC_A), "h": "0" * 64, "d": date(2026, 11, 21), "r": "{}", "c": CONV},
        )


def test_check_do_dai_conversation_id_va_bundle_phai_la_mang(env, minh):
    with pytest.raises(DB_ERRORS):
        save(env, minh, SPEC_A, conv="x" * 257)
    with pytest.raises(DB_ERRORS):
        save(env, minh, SPEC_A, conv="")  # rỗng không hợp lệ ở DB (engine đổi thành NULL trước khi ghi)
    with pytest.raises(DB_ERRORS), env.db.transaction(MINH) as tx:  # bundle phải là mảng JSON
        tx.execute(
            "INSERT INTO scenarios (user_id, kind, spec, spec_hash, app_date, n_paths, result, bundle) "
            "VALUES (:uid, 'one_time_purchase', CAST(:spec AS jsonb), :h, CAST(:d AS date), 1, CAST(:r AS jsonb), CAST(:b AS jsonb))",
            {"uid": MINH, "spec": json.dumps(SPEC_A), "h": "0" * 64, "d": date(2026, 11, 21), "r": "{}", "b": '{"a":1}'},
        )
    ok = save(env, minh, SPEC_A, conv="x" * 256, bundle=[SPEC_A])
    assert [str(r["id"]) for r in listing(env, minh, conv="x" * 256)] == [ok]


def test_dat_lai_demo_don_kich_ban_theo_cuoc_chat(env, minh):
    save(env, minh, SPEC_A, bundle=[SPEC_A])
    assert len(listing(env, minh)) == 1
    env.reset(MINH)
    assert listing(env, minh) == []


# --- engine thật trên Postgres thật: run_scenario gộp rồi list_scenarios ------------------------------------
def test_engine_that_chay_gop_roi_list_scenarios_tren_postgres(env, minh):
    from pipeline_helpers import make_settings

    from yofina_forecast.runner import Pipeline
    from yofina_forecast.scenario import ScenarioEngine
    from yofina_ledger.refdata import ReferenceData

    settings = make_settings(n_paths_full=2000, scenario_n_paths=600, scenario_keep=50)
    pipeline = Pipeline(ForecastRepo(env.db), settings, None, clock=env.clock)
    eng = ScenarioEngine(pipeline, env.repo, ReferenceData(env.repo, 300), settings)
    pipeline.run_user(MINH, trigger="reset")
    shoes = {"kind": "one_time_purchase", "amount_vnd": 800_000, "funding_source": "jar", "jar_code": "giai_tri", "label": "giày"}
    sandals = {**shoes, "amount_vnd": 300_000, "label": "dép"}
    first = eng.run(MINH, shoes, trace_id="t" * 8, conversation_id=CONV)
    both = eng.run(MINH, sandals, trace_id="u" * 8, conversation_id=CONV, with_scenarios=[shoes])
    d = both["data"]
    assert d["bundle_total_vnd"] == 1_100_000 and [b["amount_vnd"] for b in d["bundle"]] == [800_000, 300_000]
    assert d["timelines"][0]["compare"]["delta"]["min_balance_delta_vnd"] == -1_100_000
    res = eng.list_scenarios(MINH, conversation_id=CONV)
    assert res["app_date"] == "2026-11-21"
    items = res["data"]["scenarios"]
    assert [i["scenario_id"] for i in items] == [d["scenario_id"], first["data"]["scenario_id"]]
    assert items[0]["label"] == d["timelines"][0]["compare"]["label"] == "mua giày 800 nghìn + mua dép 300 nghìn"
    assert items[0]["bundle"] == d["bundle"] and items[0]["spec"] == d["spec"]
    assert len(items[1]["bundle"]) == 1
    assert eng.list_scenarios(LAN, conversation_id=CONV)["data"]["scenarios"] == []  # RLS: lan không thấy
