"""Hũ tiết kiệm 0 ₫ không lịch sử (Đầu tư của ví demo, issue #39) trên PostgreSQL cục bộ, engine thật: không nơi nào đọc dự báo theo
hũ nêu hũ đó là "sắp cạn" hay "đã cạn", và không có thẻ cảnh báo nào cho nó.

Hũ được chọn theo dữ liệu (loại `saving`, số dư 0, không có dòng chi nào), không theo mã. Trước khi sửa, engine đặt ngày cạn là ngày mai
(số dư P50 nằm đúng ngưỡng cạn từ ngày đầu) dù xác suất hụt là 0; chỉ cờ `runout_date_shown` của hũ thưa che ngày đó ở Tổng quan, còn
what-if suy trạng thái từ ngày cạn nên báo hũ "hụt". Các nơi kiểm: tóm tắt dự báo (bảng), Tổng quan (danh sách hũ, thẻ chủ động), cổng
bản tin chủ động, tool `get_forecast` và bản gọn của agent (`compact.py`, câu "hũ nào sắp cạn?"), what-if, kiểm tra trước khi chi, điểm
chống chịu và cú sốc, bộ phân bổ của lộ trình.
"""

from __future__ import annotations

import sys

import pytest
from conftest import REPO
from ledger_fakes import http_event
from pipeline_helpers import make_settings

from yofina_forecast.afford import AffordabilityEngine
from yofina_forecast.allocation import AllocationEngine
from yofina_forecast.repo import ForecastRepo
from yofina_forecast.resilience import ResilienceEngine
from yofina_forecast.runner import Pipeline
from yofina_forecast.scenario import ScenarioEngine
from yofina_forecast.stress import StressEngine
from yofina_forecast.tool import ForecastReader, ReadSettings, get_forecast
from yofina_ledger import proactive
from yofina_ledger.rest_api import handle_http

AGENT_SRC = str(REPO / "agent" / "src")
if AGENT_SRC not in sys.path:
    sys.path.insert(0, AGENT_SRC)

from yofina_agent.compact import compact_forecast, compact_forecast_overview  # noqa: E402

USER = "sub-minh"
TRACE = "hurong00"


@pytest.fixture()
def demo(env):
    settings = make_settings(n_paths_full=2000, n_paths_fast=1000, scenario_n_paths=1000)
    p = Pipeline(ForecastRepo(env.db), settings, None, clock=env.clock)
    r = handle_http(http_event("POST", "/demo/reset", sub=USER, groups="persona-minh"), env.svc)
    assert r["statusCode"] == 200, r
    assert p.run_user(USER, trigger="reset").status == "ok"
    with env.master() as m:
        spent = {c for (c,) in m.execute(
            "SELECT DISTINCT jar_code FROM transactions WHERE user_id = %s AND kind = 'expense'", [USER]
        ).fetchall()}  # fmt: skip
    jars = [j for j in env.repo.jar_view(USER).jars if j["kind"] != "system"]
    empty = [j["code"] for j in jars if j["kind"] == "saving" and int(j["balance_vnd"]) == 0 and j["code"] not in spent]
    assert empty, "ví demo phải có một hũ tiết kiệm 0 ₫ không lịch sử (Đầu tư)"
    return env, p, empty


def test_du_bao_khong_co_ngay_can_va_trang_thai_du(demo):
    env, _, empty = demo
    rows = {r["jar_code"]: r for r in env.repo.forecast_summaries(USER)}
    for code in empty:
        s = rows[code]
        assert s["runout_date"] is None and s["status"] == "ok", s
        assert s["p_shortfall"] is None or float(s["p_shortfall"]) == 0
    # hũ thật sự cạn vẫn có ngày cạn (cảnh 1): sửa không chạm hũ có chi tiêu
    assert rows["an_uong"]["status"] == "short" and rows["an_uong"]["runout_date"] is not None


def test_tong_quan_va_the_chu_dong_khong_neu_hu_rong(demo):
    env, _, empty = demo
    ov = env.svc.overview_response(USER)
    by_code = {j["code"]: j for j in ov["jars"]}
    for code in empty:
        assert by_code[code]["status"] == "ok" and "runout_date" not in by_code[code]
    card = ov["proactive_card"]
    assert card is None or card["data"].get("jar_code") not in empty
    # chỉ còn hũ rỗng trong dữ liệu dự báo: không có thẻ cảnh báo cạn nào
    forecasts = {r["jar_code"]: r for r in env.repo.forecast_summaries(USER) if r["jar_code"] in empty}
    jars = [j for j in env.repo.jar_view(USER).jars if j["kind"] != "system"]
    only = proactive.choose_proactive_card(
        today=env.clock().date(), jars=jars, forecasts=forecasts, salary_event=None, obligations_due=[],
        review_count=0, obligation_days=3, trace_id="t" * 32, as_of=env.clock(), source_tool="test",
    )  # fmt: skip
    assert only is None or only.data.kind != "runout_warning"


def test_cong_ban_tin_khong_co_ung_vien_cho_hu_rong(demo):
    env, p, empty = demo
    forecasts = {r["jar_code"]: r for r in env.repo.forecast_summaries(USER)}
    jars = [j for j in p.repo.jar_state(USER) if j.get("kind") != "system"]
    candidates = proactive.gather_candidates(
        today=env.clock().date(), jars=jars, forecasts=forecasts,
        essential_jar_codes={j["code"] for j in jars},  # kể cả coi mọi hũ là thiết yếu
        avg_daily_spend={}, obligations=[], roadmap=None, review_ask=None, resilience_today=None,
        resilience_before=None, behavior=None, recent_kinds={},
    )  # fmt: skip
    assert not [c for c in candidates if c.jar_code in empty]
    assert any(c.kind == "runout_warning" and c.jar_code == "an_uong" for c in candidates)


def test_tool_get_forecast_va_ban_gon_cua_agent_xep_hu_rong_vao_nhom_du(demo):
    env, p, empty = demo
    reader = ForecastReader(env.repo, ReadSettings(900, "Asia/Ho_Chi_Minh"), env.clock)
    compacts = []
    for code in [*empty, "an_uong"]:
        out = get_forecast(reader, p, USER, code, trace_id=TRACE)
        if code in empty:
            assert out["data"]["status"] == "ok" and "runout_date" not in out["data"]
        compacts.append(compact_forecast(out))
    for c in compacts[: len(empty)]:
        assert c["status"] == "đủ" and c["runout"] is None
    overview = compact_forecast_overview(compacts)
    names = {c["jar"] for c in compacts[: len(empty)]}
    assert names <= set(overview["enough"])
    assert not names & {r["jar"] for r in overview["runout_before_payday"]} and not names & set(overview["tight"])


def test_what_if_va_kiem_tra_truoc_khi_chi_khong_bao_hu_rong_hut(demo):
    env, p, empty = demo
    engine = ScenarioEngine(p, env.repo, env.svc.ref, p.settings)
    for code in empty:
        data = engine.run(
            USER,
            {"kind": "jar_transfer", "amount_vnd": 100_000, "from_jar": "du_phong", "to_jar": code, "label": "chuyển"},
            trace_id=TRACE,
        )["data"]
        (effect,) = [e for e in data["effects"] if e["jar"]["code"] == code]
        assert effect["status_before"] == "ok" and "runout_date_before" not in effect
        (tl,) = [t for t in data["timelines"] if t["jar"]["code"] == code]
        assert tl["status"] == "ok" and "runout_date" not in tl
    card = AffordabilityEngine(p, env.repo, env.svc.ref, p.settings).check(USER, amount_vnd=50_000, jar="an_uong")["data"]

    def mentions(node):  # mọi chỗ trong thẻ nói tới hũ rỗng
        if isinstance(node, dict):
            jar = node.get("jar")
            if (isinstance(jar, dict) and jar.get("code") in empty) or node.get("jar_code") in empty:
                yield node
            for v in node.values():
                yield from mentions(v)
        elif isinstance(node, list):
            for v in node:
                yield from mentions(v)

    for node in mentions(card):
        assert not any(k.startswith("runout") for k in node) and node.get("status") in (None, "ok"), node


def test_diem_chong_chiu_cu_soc_va_phan_bo_lo_trinh_khong_coi_hu_rong_la_can(demo):
    env, p, empty = demo
    gathered = ResilienceEngine(p).gather(USER, env.clock())
    score = ResilienceEngine(p).get(USER)["data"]
    text = " ".join([score["headline"], *(c["explanation"] for c in score["components"])])
    stress = StressEngine(p).run(USER, "mat_viec_2_thang")["data"]
    names = {j["name"] for j in env.repo.jar_view(USER).jars if j["code"] in empty}
    for name in names:
        assert name not in text and name not in stress["headline"]
    assert stress["emergency_jar"]["code"] not in empty
    allocation = AllocationEngine(p).build(
        gathered, horizon_months=3, goal_args=[], shock_id=None, allow_relaxation=True
    )
    roles = {j.code: j.role for j in allocation.problem.jars}
    assert all(roles[c] == "saving" for c in empty)
