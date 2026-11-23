"""Cú sốc (phase 4, F4): định nghĩa đọc từ `shocks.json`, biến đổi đầu vào điểm và lịch dự báo, Monte Carlo CÙNG dãy số ngẫu nhiên với
nền, tool `forecast___stress_test` và REST `POST /resilience/stress`. Engine ML THẬT."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest
from conftest import BASE, build_registry
from jsonschema import Draft202012Validator
from pipeline_helpers import APP_DATE, NOW, make_settings
from test_resilience import (
    CFG,
    RENT,
    USER,
    _Afford,
    errors_of,
    http_event,
    inputs,
    pipe,
    world,
)

from yofina_core.blocks import StressResultData, block_to_wire, build_stress_result
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.resilience import ShockDefinition, load_shock_set, parse_shock_set
from yofina_forecast import tool as tool_mod
from yofina_forecast.inputs import build_inputs
from yofina_forecast.resilience import ResilienceEngine, score_of
from yofina_forecast.stress import StressEngine, find_shock, list_shocks
from yofina_ml.resilience import GoalFact
from yofina_ml.stress import (
    income_factor,
    shock_forecast_inputs,
    shock_score_inputs,
    simulate_stress,
    summarize_stress,
)

REGISTRY = build_registry()
TOOL_RESULT = Draft202012Validator(
    {"$ref": f"{BASE}/tools/forecast.results.schema.json#/$defs/StressTestResult"},
    registry=REGISTRY,
)
REST_BLOCK = Draft202012Validator(
    {"$ref": f"{BASE}/rest/openapi.yaml#/components/schemas/StressResultResponse"},
    registry=REGISTRY,
)
SHOCKS = load_shock_set()
IDS = [s.shock_id for s in SHOCKS.shocks]
MONTH = 30


def shock(sid: str) -> ShockDefinition:
    s = SHOCKS.get(sid)
    assert s is not None
    return s


def custom(**params) -> ShockDefinition:
    kind = "income_loss"
    if "extra_cost_vnd" in params:
        kind = "health_event"
    elif "expense_increase_percent" in params:
        kind = "expense_increase"
    return parse_shock_set(
        {
            "version": "t",
            "note": "t",
            "shocks": [
                {
                    "shock_id": "thu",
                    "kind": kind,
                    "label": "Thử",
                    "description": "Cú sốc thử",
                    "params": params,
                    "source": "test",
                }
            ],
        }
    ).shocks[0]


# =====================================================================================
# Điểm trước và sau (hàm thuần trên ResilienceInputs)
# =====================================================================================
def test_cu_soc_doc_tu_file_va_chi_nhan_shock_id():
    assert IDS == ["mat_viec_2_thang", "tien_tro_tang", "om_mot_tuan"]
    assert (
        find_shock("om_mot_tuan").params.extra_cost_vnd
        == SHOCKS.get("om_mot_tuan").params.extra_cost_vnd
    )
    for bad in ("khong_co", "", None, 5):
        with pytest.raises(YofinaError) as e:
            find_shock(bad)
        assert e.value.code in (ErrorCode.SHOCK_NOT_FOUND, ErrorCode.PARAMS_INVALID)
    with pytest.raises(YofinaError) as e:
        find_shock("khong_co")
    assert e.value.code == ErrorCode.SHOCK_NOT_FOUND and all(i in e.value.message for i in IDS)
    assert [s["shock_id"] for s in list_shocks()["shocks"]] == IDS


def test_mat_thu_nhap_ca_ky_dua_thu_nhap_va_dong_gop_muc_tieu_ve_khong():
    before = inputs()
    after = shock_score_inputs(before, shock("mat_viec_2_thang"))  # 100% trong 60 ngày >= một kỳ
    assert income_factor(shock("mat_viec_2_thang"), 30) == 0
    assert after.income_vnd == 0 and after.goals[0].monthly_contribution_vnd == 0
    assert after.goals[0].monthly_needed_vnd == before.goals[0].monthly_needed_vnd
    assert (
        after.liquid_balance_vnd == before.liquid_balance_vnd
    )  # số dư và mức chi không đổi: Save giữ nguyên
    assert (
        score_of(after, CFG).component("save").score
        == score_of(before, CFG).component("save").score
    )
    assert score_of(after, CFG).score < score_of(before, CFG).score


def test_om_mot_tuan_mat_mot_phan_thu_nhap_va_co_khoan_chi_mot_lan():
    s = shock("om_mot_tuan")
    p = s.params
    before = inputs()
    after = shock_score_inputs(before, s)
    assert income_factor(s, 30) == pytest.approx(
        1 - p.income_loss_percent / 100 * p.duration_days / 30
    )
    assert after.income_vnd == round(before.income_vnd * income_factor(s, 30))
    assert after.liquid_balance_vnd == before.liquid_balance_vnd - p.extra_cost_vnd
    assert after.one_off_spend_vnd == p.extra_cost_vnd
    assert (
        after.daily_burn_vnd == before.daily_burn_vnd
    )  # khoản một lần không làm mức chi mỗi ngày tăng


def test_tien_tro_tang_chi_dung_loai_nghia_vu_bi_tang_gia():
    s = shock("tien_tro_tang")
    before = inputs()
    after = shock_score_inputs(before, s)
    extra = round(2_000_000 * s.params.expense_increase_percent / 100)  # 90 ngày >= một kỳ: tăng đủ
    assert after.obligations_vnd == before.obligations_vnd + extra
    assert (
        after.obligations_by_kind["rent"] == 2_000_000 + extra
        and after.obligations_by_kind["bill"] == 400_000
    )
    assert after.income_vnd == before.income_vnd
    # không có khoản thuê nhà nào thì cú sốc không đổi gì ở nghĩa vụ
    none = shock_score_inputs(inputs(obligations_by_kind={"bill": 400_000}), s)
    assert none.obligations_vnd == before.obligations_vnd


def test_diem_sau_khong_bao_gio_cao_hon_diem_truoc():
    rng = np.random.default_rng(3)
    for _ in range(100):
        i = inputs(
            liquid_balance_vnd=int(rng.integers(0, 30_000_000)),
            income_vnd=int(rng.integers(1_000_000, 30_000_000)),
            variable_spend_vnd=int(rng.integers(0, 15_000_000)),
            obligations_vnd=int(rng.integers(0, 12_000_000)),
            obligations_by_kind={"rent": int(rng.integers(0, 3_000_000))},
            goals=(
                GoalFact("g", int(rng.integers(1, 2_000_000)), int(rng.integers(0, 2_000_000))),
            ),
        )
        base = score_of(i, CFG).score
        for s in SHOCKS.shocks:
            assert score_of(shock_score_inputs(i, s), CFG).score <= base


# =====================================================================================
# Lịch của ForecastInputs
# =====================================================================================
def built(w=None, horizon: int = 90):
    from dataclasses import replace

    w = w or world()
    p = pipe(w)
    g = ResilienceEngine(p).gather(USER, NOW)
    b = build_inputs(g.ctx, replace(p.settings, horizon_days=horizon), USER, n_paths=300)
    kinds = {str(o["id"]): str(o["kind"]) for o in g.obligations}
    return w, p, g, b, kinds


def salary_by_date(inp) -> dict[date, int]:
    out: dict[date, int] = {}
    for j in inp.jars:
        for f in j.inflows:
            out[f.date] = out.get(f.date, 0) + f.amount_vnd
    return out


def test_mat_viec_60_ngay_mat_dung_hai_ngay_luong_lien_tiep():
    _, _, _, b, kinds = built()
    s = shock("mat_viec_2_thang")
    after = shock_forecast_inputs(
        b.inputs, s, obligation_kinds=kinds, cost_jar=None, extra_cost_label="x", month_days=MONTH
    )
    before_sal, after_sal = salary_by_date(b.inputs), salary_by_date(after)
    paydays = sorted(before_sal)
    assert len(paydays) == 3
    assert [after_sal.get(d, 0) for d in paydays[:2]] == [0, 0] and after_sal[
        paydays[2]
    ] == before_sal[paydays[2]]
    assert [j.outflows for j in after.jars] == [
        j.outflows for j in b.inputs.jars
    ]  # nghĩa vụ vẫn như cũ


def test_om_mot_tuan_mat_mot_phan_ngay_luong_ke_tiep_va_them_khoan_chi_vao_hu_du_phong():
    _, _, _, b, kinds = built()
    s = shock("om_mot_tuan")
    after = shock_forecast_inputs(
        b.inputs,
        s,
        obligation_kinds=kinds,
        cost_jar="du_phong",
        extra_cost_label="Khám bệnh",
        month_days=MONTH,
    )
    before_sal, after_sal = salary_by_date(b.inputs), salary_by_date(after)
    first = min(before_sal)
    lost = s.params.income_loss_percent / 100 * s.params.duration_days / MONTH
    assert abs(after_sal[first] - before_sal[first] * (1 - lost)) <= len(
        b.inputs.jars
    )  # làm tròn từng hũ
    assert all(after_sal[d] == before_sal[d] for d in before_sal if d != first)
    em = next(j for j in after.jars if j.code == "du_phong")
    extra = [f for f in em.outflows if f.label == "Khám bệnh"]
    assert len(extra) == 1 and extra[0].amount_vnd == s.params.extra_cost_vnd
    assert extra[0].date == APP_DATE + timedelta(days=1)
    # không có hũ nào để trả khoản chi một lần thì lỗi rõ ràng
    with pytest.raises(ValueError):
        shock_forecast_inputs(
            b.inputs,
            s,
            obligation_kinds=kinds,
            cost_jar=None,
            extra_cost_label="x",
            month_days=MONTH,
        )


def test_tien_tro_tang_chi_tang_dung_khoan_thue_trong_thoi_gian_soc():
    _, _, _, b, kinds = built()
    s = shock("tien_tro_tang")
    after = shock_forecast_inputs(
        b.inputs, s, obligation_kinds=kinds, cost_jar=None, extra_cost_label="x", month_days=MONTH
    )
    factor = 1 + s.params.expense_increase_percent / 100
    end = APP_DATE + timedelta(days=s.params.duration_days)
    rent_id = RENT["id"]
    changed = 0
    for jb, ja in zip(b.inputs.jars, after.jars, strict=True):
        assert ja.inflows == jb.inflows
        for fb, fa in zip(jb.outflows, ja.outflows, strict=True):
            if fb.ref_id == rent_id and fb.date <= end:
                assert fa.amount_vnd == round(fb.amount_vnd * factor)
                changed += 1
            else:
                assert fa == fb
    assert changed >= 2  # 6/12, 6/1 (và 6/2 nếu trong 90 ngày)


# =====================================================================================
# Monte Carlo cùng dãy số ngẫu nhiên
# =====================================================================================
def sim_for(sid_or_def, **kw):
    _w, p, g, b, kinds = built(kw.pop("w", None))
    s = shock(sid_or_def) if isinstance(sid_or_def, str) else sid_or_def
    cost = "du_phong"
    after = shock_forecast_inputs(
        b.inputs, s, obligation_kinds=kinds, cost_jar=cost, extra_cost_label="x", month_days=MONTH
    )
    st = StressEngine(p, ResilienceEngine(p))
    prev = st._previous(USER, b.inputs, b.jar_codes)
    return simulate_stress(b.inputs, after, prev, n_paths=400), s, g


def test_common_random_numbers_cu_soc_khong_tac_dong_thi_hai_duong_trung_nhau_tuyet_doi():
    none = custom(duration_days=7, income_loss_percent=0)
    sim, *_ = sim_for(none)
    assert np.array_equal(sim.base_total_p50, sim.shocked_total_p50)
    assert np.array_equal(sim.base_outflow_cum, sim.shocked_outflow_cum)


def test_mat_viec_chenh_lech_chi_xuat_hien_tu_ngay_luong_bi_mat_khong_co_nhieu_mau():
    sim, _s, _g = sim_for("mat_viec_2_thang")
    first_payday = min(salary_by_date(built()[3].inputs))
    idx = (first_payday - APP_DATE).days - 1
    # trước ngày lương đầu tiên hai kịch bản y hệt (cùng dãy số ngẫu nhiên), từ đó trở đi số dư sốc không cao hơn
    assert np.array_equal(sim.base_total_p50[:idx], sim.shocked_total_p50[:idx])
    assert np.all(sim.shocked_total_p50 <= sim.base_total_p50)
    assert sim.shocked_total_p50[idx] < sim.base_total_p50[idx]
    assert np.array_equal(
        sim.base_outflow_cum, sim.shocked_outflow_cum
    )  # mất việc không đổi chi tiêu
    assert sim.n_paths == 400 and sim.horizon_days == 90


def test_chi_phi_mot_lan_dich_dung_phan_phoi_di_mot_khoan_co_dinh_tu_ngay_do():
    s = shock("om_mot_tuan")
    sim, *_ = sim_for(
        custom(duration_days=7, income_loss_percent=0, extra_cost_vnd=s.params.extra_cost_vnd)
    )
    diff = sim.base_total_p50 - sim.shocked_total_p50
    assert np.allclose(
        diff, s.params.extra_cost_vnd, atol=1e-3
    )  # mọi phân vị dịch đúng khoản chi: không nhiễu mẫu
    assert sim.shocked_outflow_cum[-1] - sim.base_outflow_cum[-1] == pytest.approx(
        s.params.extra_cost_vnd
    )


def test_tom_tat_so_ngay_tru_duoc_khoan_thieu_va_trang_thai():
    n = 10
    p50 = np.array([500, 300, 100, -50, -400, -200, 100, 300, 300, 300], dtype=float)
    from yofina_ml.stress import StressSim

    sim = StressSim(
        n_paths=5, horizon_days=n, base_total_p50=np.full(n, 1000.0), shocked_total_p50=p50,
        shocked_total_p10=p50 - 10, shocked_outflow_cum=np.cumsum(np.full(n, 200.0)),
        base_outflow_cum=np.cumsum(np.full(n, 100.0)),
    )  # fmt: skip
    out = summarize_stress(
        sim,
        duration_days=5,
        emergency_balance_vnd=450,
        runout_threshold_vnd=0,
        short_shortfall_ratio=0.25,
    )
    assert out.runway_days_total == 3 and out.shortfall_index == 3
    assert out.shortfall_vnd == 400 and out.need_vnd == 1000
    assert out.runway_days_emergency == 2 and out.status == "short"  # 400/1000 = 0,4 >= 0,25
    # ngưỡng trong cấu hình quyết định short hay tight
    again = summarize_stress(
        sim,
        duration_days=5,
        emergency_balance_vnd=None,
        runout_threshold_vnd=0,
        short_shortfall_ratio=0.5,
    )
    assert again.status == "tight" and again.runway_days_emergency is None
    low = summarize_stress(
        sim,
        duration_days=5,
        emergency_balance_vnd=None,
        runout_threshold_vnd=0,
        short_shortfall_ratio=0.3,
    )
    assert low.status == "short"
    fine = StressSim(
        n_paths=5, horizon_days=n, base_total_p50=np.full(n, 1000.0), shocked_total_p50=np.full(n, 10.0),
        shocked_total_p10=np.full(n, 0.0), shocked_outflow_cum=np.cumsum(np.full(n, 5.0)),
        base_outflow_cum=np.cumsum(np.full(n, 5.0)),
    )  # fmt: skip
    ok = summarize_stress(
        fine,
        duration_days=5,
        emergency_balance_vnd=10_000,
        runout_threshold_vnd=0,
        short_shortfall_ratio=0.25,
    )
    assert ok.runway_days_total is None and ok.shortfall_vnd == 0 and ok.status == "ok"
    assert ok.runway_days_emergency == n  # hũ Dự phòng đủ trả hết khoảng dự báo


# =====================================================================================
# Engine: tool và REST
# =====================================================================================
@pytest.mark.parametrize("sid", IDS)
def test_stress_test_khop_hop_dong_va_bat_bien(sid):
    w = world()
    p = pipe(w)
    eng = StressEngine(p, ResilienceEngine(p))
    res = eng.run(USER, sid)
    assert not errors_of(TOOL_RESULT, res), errors_of(TOOL_RESULT, res)
    d = StressResultData.model_validate(res["data"])
    assert d.shock.shock_id == sid and d.shock.label == shock(sid).label
    assert d.method == "monte_carlo" and d.common_random_numbers is True
    assert d.n_paths == int(CFG.stress.n_paths.value) and d.horizon_days == int(
        CFG.stress.horizon_days.value
    )
    assert d.score_after <= d.score_before and d.score_delta == d.score_after - d.score_before
    # điểm trước chính là điểm đang hiện ở màn "Nhìn trước"
    now_score = ResilienceEngine(p).get(USER)["data"]["score"]
    assert d.score_before == now_score
    assert d.emergency_jar is not None and d.emergency_jar.code == "du_phong"
    assert d.runway_days_emergency is not None and d.runway_days_emergency <= d.horizon_days
    assert [c.key for c in d.components] == ["save", "spend", "borrow", "plan"]
    assert d.headline.startswith(shock(sid).label)
    assert w.score_saves == 1  # chỉ lần đọc điểm ở trên ghi; cú sốc không ghi gì (kể cả bảng điểm)


def test_ba_cu_soc_cho_ket_qua_khac_nhau_va_tat_dinh():
    w = world()
    p = pipe(w)
    eng = StressEngine(p, ResilienceEngine(p))
    results = {sid: eng.run(USER, sid)["data"] for sid in IDS}
    assert results["mat_viec_2_thang"]["score_after"] < results["mat_viec_2_thang"]["score_before"]
    assert (
        results["mat_viec_2_thang"].get("runway_days_total") is not None
        or results["mat_viec_2_thang"]["shortfall_vnd"] >= 0
    )
    assert len({json.dumps(r["components"]) for r in results.values()}) == 3
    again = eng.run(USER, "mat_viec_2_thang")["data"]
    assert again == results["mat_viec_2_thang"]  # cùng dữ liệu, cùng hạt giống: cùng kết quả
    assert w.runs and len(w.runs) == 1  # dùng lại nền dự báo đã có, không tính lại mỗi lần


def test_mat_viec_nang_hon_om_mot_tuan_o_so_ngay_tru_duoc_va_khoan_thieu():
    w = world()
    p = pipe(w)
    eng = StressEngine(p, ResilienceEngine(p))
    job, sick = eng.run(USER, "mat_viec_2_thang")["data"], eng.run(USER, "om_mot_tuan")["data"]
    assert job["shortfall_vnd"] >= sick["shortfall_vnd"]
    job_runway = job.get("runway_days_total", 10**6)
    sick_runway = sick.get("runway_days_total", 10**6)
    assert job_runway <= sick_runway
    assert job["score_after"] <= sick["score_after"]


def test_ma_cu_soc_la_va_thieu_du_lieu():
    p = pipe(world())
    eng = StressEngine(p, ResilienceEngine(p))
    with pytest.raises(YofinaError) as e:
        eng.run(USER, "mat_viec_6_thang")
    assert e.value.code == ErrorCode.SHOCK_NOT_FOUND
    bad = pipe(world(salary=None))
    with pytest.raises(YofinaError) as e:
        StressEngine(bad, ResilienceEngine(bad)).run(USER, "om_mot_tuan")
    assert e.value.code == ErrorCode.PROFILE_INCOMPLETE


def test_gateway_tool_stress_test_va_loi_co_phong_bi_chuan():
    w = world()
    p = pipe(w)
    res_eng = ResilienceEngine(p)
    eng = StressEngine(p, res_eng)
    ctx = SimpleNamespace(
        client_context=SimpleNamespace(
            custom={"bedrockAgentCoreToolName": "forecast___stress_test"}
        )
    )
    ok = tool_mod.handle_gateway(
        {"user_id": USER, "shock_id": "tien_tro_tang"}, ctx, None, p, None, None, res_eng, eng
    )  # type: ignore[arg-type]
    assert ok["status"] == "OK" and not errors_of(TOOL_RESULT, ok)
    nf = tool_mod.handle_gateway(
        {"user_id": USER, "shock_id": "nghi_viec"}, ctx, None, p, None, None, res_eng, eng
    )  # type: ignore[arg-type]
    assert (
        nf["status"] == "ERROR"
        and nf["code"] == "SHOCK_NOT_FOUND"
        and not errors_of(TOOL_RESULT, nf)
    )
    missing = tool_mod.handle_gateway({"user_id": USER}, ctx, None, p, None, None, res_eng, eng)  # type: ignore[arg-type]
    assert missing["status"] == "ERROR" and missing["code"] == "PARAMS_INVALID"


def test_rest_post_stress_tra_khoi_stress_result_va_chi_nhan_shock_id():
    w = world()
    p = pipe(w)
    res_eng = ResilienceEngine(p)
    eng = StressEngine(p, res_eng)
    out = tool_mod.handle_http(
        http_event("POST", "/resilience/stress", body={"shock_id": "mat_viec_2_thang"}),
        _Afford(),
        res_eng,
        eng,
    )  # type: ignore[arg-type]
    assert out["statusCode"] == 200
    body = json.loads(out["body"])
    assert body["type"] == "stress_result" and not errors_of(REST_BLOCK, body), errors_of(
        REST_BLOCK, body
    )
    assert body["source"]["tool"] == "rest:POST /resilience/stress"
    # cùng số với tool
    tool = eng.run(USER, "mat_viec_2_thang")
    assert body["data"] == tool["data"]
    block = build_stress_result(
        data=tool["data"], trace_id="b" * 32, source_tool="x",
        as_of=datetime.fromisoformat(tool["as_of"].replace("Z", "+00:00")), app_date=date.fromisoformat(tool["app_date"]),
    )  # fmt: skip
    assert block_to_wire(block)["data"] == body["data"]
    # trường lạ (không cho tự đưa số của cú sốc hay user_id) -> 400
    for extra in (
        {"shock_id": "om_mot_tuan", "extra_cost_vnd": 1},
        {"shock_id": "om_mot_tuan", "user_id": "u2"},
    ):
        bad = tool_mod.handle_http(
            http_event("POST", "/resilience/stress", body=extra), _Afford(), res_eng, eng
        )  # type: ignore[arg-type]
        assert bad["statusCode"] == 400
    nf = tool_mod.handle_http(
        http_event("POST", "/resilience/stress", body={"shock_id": "la"}), _Afford(), res_eng, eng
    )  # type: ignore[arg-type]
    assert nf["statusCode"] == 404 and json.loads(nf["body"])["error"]["code"] == "SHOCK_NOT_FOUND"
    nojwt = tool_mod.handle_http(
        http_event("POST", "/resilience/stress", sub=None, body={"shock_id": "om_mot_tuan"}),
        _Afford(),
        res_eng,
        eng,
    )  # type: ignore[arg-type]
    assert nojwt["statusCode"] == 401
    unknown = tool_mod.handle_http(http_event("GET", "/khong-co"), _Afford(), res_eng, eng)  # type: ignore[arg-type]
    assert unknown["statusCode"] == 400


def test_cau_hinh_stress_quyet_dinh_khoang_va_so_duong():
    assert make_settings().resilience_window_days >= 1
    cfg_h = int(CFG.stress.horizon_days.value)
    assert 1 <= cfg_h <= 90  # hợp đồng ML
    assert min(s.params.duration_days for s in SHOCKS.shocks) >= 1
    assert max(s.params.duration_days for s in SHOCKS.shocks) <= cfg_h
