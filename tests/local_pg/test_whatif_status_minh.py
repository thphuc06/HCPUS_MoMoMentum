"""Trạng thái trên thẻ what-if của persona `minh` phải khớp số liệu (PostgreSQL thật cục bộ, engine ML thật, sổ cái persona thật).

Bốn lỗi thấy khi đi cảnh 2 ngày 23/11 (file phase 3, mục "Kết quả đi cảnh 2"):

1. What-if "tai nghe 1,2 triệu Trả sau": thẻ `forecast_timeline` ghi "Sau: Đủ, khả năng hụt 0%" trong khi cùng thẻ ghi số dư thấp
   nhất -750.000 ₫ và cạn 05/12 (khoản Trả sau đến hạn đúng ngày lương, nằm ngoài cửa sổ xác suất "trước kỳ lương").
2. Phương án "Dùng hũ Dự phòng" cho khoản 15 triệu được kiểm luật là sạch (agent hiện "Đủ") dù hũ chỉ có 2.700.000 ₫.
3. Phương án "Hoãn tới kỳ lương" vẫn "Hụt": số dư dùng để chi là số dư ngày TRƯỚC ngày lương (lương chưa về).
4. `check_suitability` có `scenario_id` cộng nghĩa vụ Trả sau của kịch bản cho MỌI đề xuất, kể cả phương án hoãn không vay gì.

Mọi số kỳ vọng suy từ kết quả engine trong chính test (không gắn cứng đầu ra)."""

from __future__ import annotations

from datetime import date

import pytest
from pipeline_helpers import make_settings

from yofina_forecast.afford import AffordabilityEngine
from yofina_forecast.repo import ForecastRepo
from yofina_forecast.runner import Pipeline
from yofina_forecast.scenario import ScenarioEngine
from yofina_ledger.refdata import ReferenceData

MINH = "sub-minh"
TRACE = "t" * 8
HEADPHONES = {"kind": "bnpl_purchase", "amount_vnd": 1_200_000, "funding_source": "credit", "label": "tai nghe"}


@pytest.fixture()
def minh(env):
    env.reset(MINH)
    settings = make_settings(n_paths_full=2000, scenario_n_paths=600, scenario_keep=50)
    pipeline = Pipeline(ForecastRepo(env.db), settings, None, clock=env.clock)
    pipeline.run_user(MINH, trigger="reset")
    ref = ReferenceData(env.repo, 300)
    return env, ScenarioEngine(pipeline, env.repo, ref, settings), AffordabilityEngine(pipeline, env.repo, ref, settings)


# --- lỗi 1 -------------------------------------------------------------------------------------------
def test_tra_sau_tai_nghe_trang_thai_sau_khop_so_du_thap_nhat_va_ngay_can(minh):
    _env, eng, _af = minh
    d = eng.run(MINH, HEADPHONES, trace_id=TRACE)["data"]
    tl = d["timelines"][0]
    after = tl["compare"]["after"]
    payday = tl["payday"]["date"]
    assert tl["jar"]["code"] == "nghia_vu"
    # tiền đề của ca lỗi: sau kịch bản hũ Nghĩa vụ âm và cạn ngay ngày lương (khoản Trả sau đến hạn 05/12)
    assert after["min_balance_p50_vnd"] < 0 and after["runout_date"] <= payday
    assert after["status"] == "short", after["status"]
    # không nói "khả năng hụt 0%" cạnh chữ "Hụt": xác suất (tính trước ngày lương) không có hoặc khớp trạng thái
    assert after.get("p_shortfall") is None or after["p_shortfall"] >= 0.5
    eff = next(e for e in d["effects"] if e["jar"]["code"] == "nghia_vu")
    assert eff["status_after"] == "short"
    assert eff.get("p_shortfall_after") is None or eff["p_shortfall_after"] >= 0.5
    # trước kịch bản hũ không cạn tới kỳ lương nên vẫn "đủ" như màn Chi tiết hũ
    assert tl["status"] == "ok" and "runout_date" not in tl


# --- lỗi 2 -------------------------------------------------------------------------------------------
def test_phuong_an_dung_hu_du_phong_cho_15_trieu_khong_duoc_coi_la_du(minh):
    env, _eng, _af = minh
    balance = next(int(j["balance_vnd"]) for j in env.repo.jar_view(MINH).jars if j["code"] == "du_phong")
    assert balance < 15_000_000  # Dự phòng của minh 2.700.000 ₫
    proposal = {
        "kind": "switch_jar", "amount_vnd": 15_000_000, "funding_source": "jar", "jar_code": "du_phong",
        "is_essential": False, "category": "spending", "risk_level": "low", "origin": "recommendation",
    }  # fmt: skip
    v = env.svc.check_suitability_result(MINH, proposal=proposal)["data"]
    assert v["ok"] is False, v
    bad = [x for x in v["violations"] if x["severity"] == "block"]
    assert bad, v["violations"]
    # khoản vừa số dư thì qua luật này
    ok = env.svc.check_suitability_result(MINH, proposal={**proposal, "amount_vnd": balance})["data"]
    assert {x["rule_id"] for x in ok["violations"]}.isdisjoint({x["rule_id"] for x in bad})


# --- lỗi 3 -------------------------------------------------------------------------------------------
def test_hoan_toi_ky_luong_chi_sau_khi_luong_ve(minh):
    env, _eng, af = minh
    card = af.check(MINH, amount_vnd=250_000, jar="hoa_don")["data"]
    assert card["verdict"] == "short"  # chi hôm nay thì hụt (tiền điện 26/11)
    defer = next(o for o in card["options"] if o["option_id"] == "defer_payday")
    series = {r["day"]: int(r["balance_p50_vnd"]) for r in env.repo.forecast_series(MINH, "hoa_don")}
    payday = date(2026, 12, 5)
    after_payday = [v - 250_000 for d, v in series.items() if d >= payday]
    # lương về hũ Hóa đơn ngày 05/12: chi 250.000 ₫ sau khi lương về thì số dư dự báo không âm ngày nào sau đó
    assert min(after_payday) >= 0
    assert defer["status"] == "ok", defer
    assert defer["summary"].startswith("Đủ")


# --- lỗi 4 -------------------------------------------------------------------------------------------
def test_check_suitability_khong_cong_nghia_vu_tra_sau_cho_phuong_an_hoan(minh):
    env, eng, _af = minh
    sid = eng.run(MINH, HEADPHONES, trace_id=TRACE)["data"]["scenario_id"]
    defer = {"kind": "defer", "funding_source": "jar", "is_essential": False, "category": "spending",
             "risk_level": "low", "origin": "recommendation"}  # fmt: skip
    v = env.svc.check_suitability_result(MINH, proposal=defer, scenario_id=sid)["data"]
    by = {c["rule_id"]: c["outcome"] for c in v["checked"]}
    assert by["obligation_to_income"] == "skipped", by
    assert v["ok"] is True, v["violations"]
    # phương án vẫn vay đúng khoản của kịch bản thì vẫn bị kiểm bằng nghĩa vụ thật của kịch bản
    credit = {**defer, "kind": "use_credit", "amount_vnd": 1_200_000, "funding_source": "credit"}
    vc = env.svc.check_suitability_result(MINH, proposal=credit, scenario_id=sid)["data"]
    assert {c["rule_id"]: c["outcome"] for c in vc["checked"]}["obligation_to_income"] in ("fail", "warn")
