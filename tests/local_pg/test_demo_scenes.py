"""Cảnh 1–3 của kịch bản demo trên ví demo (issue #39), engine thật trên PostgreSQL cục bộ: `POST /demo/reset` của `minh` (bộ hũ demo:
Nghĩa vụ, Dự phòng cộng Ăn uống, Đi lại, Giải trí, Mục tiêu, Đầu tư), ngày mô phỏng 21/11/2026, pipeline dự báo, what-if, cú sốc với
cùng số đường như cấu hình CDK (10.000 đường đầy đủ, 5.000 đường cho what-if). Không gọi AWS, không gọi model.

Test chỉ khẳng định điều bộ hũ demo phải giữ: hũ Ăn uống, Đi lại, Giải trí dự báo Y HỆT ví persona (cùng người dùng, cùng hạt), Ăn uống
cạn trước kỳ lương (mốc 23/11 đã hiệu chỉnh ở phase 2); what-if Trả sau liệt kê khoản đến hạn trước lương ở hũ Nghĩa vụ và khoản thiếu
đầu tiên; cú sốc làm điểm tụt. Số đo in ra khi chạy với `-s` (báo cáo #39):

    uv run --python 3.12 --no-project --with pgserver --with "psycopg[binary]" --with pydantic --with pytest --with jsonschema \
        --with pyyaml --with referencing --with numpy --with boto3 --with scipy --with ruptures \
        pytest tests/local_pg/test_demo_scenes.py -p no:cacheprovider -s
"""

from __future__ import annotations

from datetime import date

from conftest import ANCHOR
from ledger_fakes import http_event
from pipeline_helpers import make_settings

from yofina_forecast.repo import ForecastRepo
from yofina_forecast.resilience import ResilienceEngine
from yofina_forecast.runner import Pipeline
from yofina_forecast.scenario import ScenarioEngine
from yofina_forecast.stress import StressEngine
from yofina_ledger.rest_api import handle_http

USER = "sub-minh"
SPENDING = ("an_uong", "di_lai", "giai_tri")
SUMMARY_KEYS = (
    "start_balance_vnd", "status", "runout_date", "runout_date_shown", "days_to_payday", "p_shortfall",
    "confidence_band", "payday_date",
)  # fmt: skip
TRACE = "democanh"


def _pipeline(env) -> Pipeline:
    settings = make_settings(n_paths_full=10000, n_paths_fast=5000, scenario_n_paths=5000)
    return Pipeline(ForecastRepo(env.db), settings, None, clock=env.clock)


def _reset_demo(env, p: Pipeline) -> None:
    r = handle_http(http_event("POST", "/demo/reset", sub=USER, groups="persona-minh"), env.svc)
    assert r["statusCode"] == 200, r
    assert p.run_user(USER, trigger="reset").status == "ok"


def _summaries(env) -> dict[str, dict]:
    rows = {r["jar_code"]: r for r in env.repo.forecast_summaries(USER)}
    return {code: {k: rows[code].get(k) for k in SUMMARY_KEYS} for code in rows}


def test_canh_1_hu_chi_tieu_cua_vi_demo_du_bao_y_het_vi_persona(env):
    p = _pipeline(env)
    env.reset(USER, "minh")  # ví persona như trên `main`
    assert p.run_user(USER, trigger="reset").status == "ok"
    persona = _summaries(env)
    _reset_demo(env, p)
    demo = _summaries(env)
    print("\n[cảnh 1] ví demo, ngày mô phỏng", ANCHOR)
    for code, s in demo.items():
        print(f"  {code}: {s}")
    assert {c: demo[c] for c in SPENDING} == {c: persona[c] for c in SPENDING}
    an = demo["an_uong"]
    assert an["status"] == "short" and an["runout_date"] == date(2026, 11, 23)
    assert an["runout_date"] < an["payday_date"]
    card = env.svc.overview_response(USER)["proactive_card"]
    print("  thẻ chủ động:", card["data"]["kind"], "|", card["fallback_text"])
    assert card["data"]["kind"] == "runout_warning"


def test_canh_2_mua_tai_nghe_tra_sau_hu_nghia_vu_liet_ke_khoan_den_han_truoc_luong(env):
    p = _pipeline(env)
    _reset_demo(env, p)
    engine = ScenarioEngine(p, env.repo, env.svc.ref, p.settings)
    data = engine.run(
        USER,
        {"kind": "bnpl_purchase", "amount_vnd": 1_200_000, "funding_source": "credit", "label": "tai nghe"},
        trace_id=TRACE,
    )["data"]
    impact = data["obligation_impact"]
    (tl,) = [t for t in data["timelines"] if t["jar"]["code"] == "nghia_vu"]
    before, after = tl["obligations_before_payday"], tl["compare"]["after"]["obligations_before_payday"]
    print("\n[cảnh 2] chi phí:", impact["cost"], "| hũ trả:", impact["at_due"][0])
    print("  trước khi mua:", tl.get("status"), tl.get("runout_date"), before)
    print("  sau khi mua:", tl["compare"]["after"].get("status"), tl["compare"]["after"].get("runout_date"), after)
    assert impact["at_due"][0]["jar"]["code"] == "nghia_vu"
    assert impact["cost"]["total_due_vnd"] == 2_200_000 and impact["cost"]["due_date"] == "2026-12-03"
    bnpl = [row for row in after["items"] if row["amount_vnd"] == 2_200_000]
    assert [row["date"] for row in bnpl] == ["2026-12-03"]
    assert after["first_shortfall"]["shortfall_vnd"] > 0
    assert all(row["date"] < tl["payday"]["date"] for row in after["items"])


def test_canh_3_mat_viec_hai_thang_diem_tut_va_so_ngay_tru(env):
    p = _pipeline(env)
    _reset_demo(env, p)
    score = ResilienceEngine(p).get(USER)["data"]
    d = StressEngine(p).run(USER, "mat_viec_2_thang")["data"]
    print(
        f"\n[cảnh 3] điểm hiện tại {score['score']} ({score['band']}); mất việc 2 tháng: {d['score_before']} -> "
        f"{d['score_after']} ({d['band_after']}), trụ {d['runway_days_total']} ngày; quỹ dự phòng {d['emergency_jar']}"
    )
    assert d["score_before"] == score["score"] and d["score_after"] < d["score_before"]
    assert d["emergency_jar"]["code"] == "du_phong"
