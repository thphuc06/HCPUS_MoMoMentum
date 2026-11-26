"""Lộ trình có đích là số dư hũ Dự phòng (`buffer`, issue #39 26/11) trên ví demo của `minh`, PostgreSQL cục bộ, không gọi AWS, không gọi
model thật. Câu "lập giúp mình lộ trình xây quỹ dự phòng 3 triệu trong 3 tháng" sau khi chọn hũ Dự phòng thành mục tiêu của lượt
(`UserGoal(du_phong, 3.000.000, hạn 21/02/2027)`, đổi bằng mã ở `turn.roadmap_user_goal`). `build_roadmap` của agent chạy với hai Lambda tool
THẬT trong tiến trình (ledger `handle_gateway`, forecast `handle_gateway`, LP `optimize_allocation` của Lambda forecast) và model planner giả
tất định của cảnh 4 (`test_roadmap_regen_scene4.Planner`).

Khẳng định trên phương án LP và bản đã lưu: mục tiêu là hũ Dự phòng (mục đích `buffer`) với đúng số tiền và hạn, hũ giữ vai đệm (thiết yếu
với model), mức cần mỗi kỳ và khả thi hay không; hũ không bị ghi goal_vnd. Đích không khả thi (30 triệu trong một tháng) lưu "chưa khả
thi" với hai lựa chọn lùi hạn, giảm mục tiêu của chính hũ Dự phòng. Số đo in ra với `-s`:

    uv run --python 3.12 --no-project --with pgserver --with "psycopg[binary]" --with pydantic --with pytest --with jsonschema \
        --with pyyaml --with referencing --with numpy --with boto3 --with scipy --with ruptures \
        pytest tests/local_pg/test_roadmap_buffer_goal.py -p no:cacheprovider -s
"""

from __future__ import annotations

import asyncio
from typing import Any

from ledger_fakes import gateway_context, http_event
from pipeline_helpers import make_settings
from test_roadmap_regen_scene4 import FORECAST, LEDGER, LocalAllocation, LocalLambda, Planner, _llm
from yofina_agent.roadmap_agent import UserGoal, build_roadmap
from yofina_agent.settings import AgentSettings
from yofina_roadmap.tool_caller import LambdaTools

from yofina_core.llm import TurnScope
from yofina_forecast.repo import ForecastRepo
from yofina_forecast.runner import Pipeline
from yofina_ledger.gateway_api import handle_gateway as ledger_gateway
from yofina_ledger.rest_api import handle_http

USER = "sub-lotrinh-du-phong"  # người dùng riêng mang persona minh
#: ngày mô phỏng 21/11/2026: "trong 3 tháng" là 21/02/2027 (`textutil.parse_goal_date`), "trong 1 tháng" là 21/12/2026
THREE_MONTHS, ONE_MONTH = "2027-02-21", "2026-12-21"


def _tool(env, name: str, **args: Any) -> dict[str, Any]:
    out = ledger_gateway({"user_id": USER, **args}, gateway_context(name), env.svc)
    assert out["status"] == "OK", out
    return out


def _build(env, goal: UserGoal) -> dict[str, Any]:
    """Đặt lại ví demo, dự báo, rồi lập lộ trình theo mục tiêu `goal` như lượt chat (lưu bản đề xuất dựa trên bản đang dùng)."""
    pipeline = Pipeline(ForecastRepo(env.db), make_settings(n_paths_full=600, n_paths_fast=400), None, clock=env.clock)
    r = handle_http(http_event("POST", "/demo/reset", sub=USER, groups="persona-minh"), env.svc)
    assert r["statusCode"] == 200, r
    assert pipeline.run_user(USER, trigger="reset").status == "ok"
    before = {j["code"]: j for j in _tool(env, "ledger___get_jar_balances")["data"]["jars"]}
    allocation, planner = LocalAllocation(pipeline), Planner()
    env.svc.forecast = allocation
    settings = AgentSettings.load({"YOFINA_GATEWAY_URL": "http://gateway.invalid/mcp"})
    tools = LambdaTools(LocalLambda(env, pipeline), {"ledger": LEDGER, "planner": LEDGER, "forecast": FORECAST}, USER)
    try:
        result = asyncio.run(
            build_roadmap(
                tools, _llm(planner), settings, TurnScope(settings.max_model_calls_per_turn),
                reason_code="user_request", user_goal=goal,
            )
        )  # fmt: skip
    finally:
        env.svc.forecast = None
    assert result.outcome is not None and result.outcome.ok, result
    after = {j["code"]: j for j in _tool(env, "ledger___get_jar_balances")["data"]["jars"]}
    assert allocation.last is not None
    return {
        "roadmap": _tool(env, "planner___get_roadmap", which="latest")["data"],
        "plan": allocation.last["data"],
        "planner": planner,
        "before": before,
        "after": after,
    }


def _report(tag: str, got: dict[str, Any]) -> None:
    plan, rm = got["plan"], got["roadmap"]
    lines = {line["jar"]["code"]: line for line in plan["lines"]}
    print(f"\n[{tag}] LP {plan['status']} | {plan['headline']}")
    for g in plan["goals"]:
        print(f"  mục tiêu {g['jar']['code']}: {g}")
    print("  Dự phòng:", {k: lines["du_phong"][k] for k in ("current_monthly_vnd", "proposed_monthly_vnd", "floor_vnd")})
    print(f"  bản đã lưu v{rm['version']} {rm['status']}, feasibility {rm['feasibility']}, {rm['headline']}")
    for alt in rm["alternatives"]:
        print(f"  lựa chọn {alt['kind']} {alt.get('jar_code')}: {alt['label']} | {alt['summary']}")


def test_lo_trinh_xay_quy_du_phong_3_trieu_trong_3_thang_tinh_dich_so_du(env):
    got = _build(env, UserGoal("du_phong", 3_000_000, THREE_MONTHS))
    _report("đích Dự phòng 3 triệu trong 3 tháng", got)
    plan, rm, before = got["plan"], got["roadmap"], got["before"]
    goal = next(g for g in plan["goals"] if g["jar"]["code"] == "du_phong")
    assert goal["jar"]["purpose"] == "buffer"
    assert (goal["target_vnd"], goal["target_date"]) == (3_000_000, THREE_MONTHS)
    # mức cần mỗi kỳ tính từ số dư hiện có của hũ Dự phòng tới đích
    remaining = 3_000_000 - before["du_phong"]["balance_vnd"]
    assert remaining > 0 and 0 < goal["monthly_needed_vnd"] <= remaining
    line = next(x for x in plan["lines"] if x["jar"]["code"] == "du_phong")
    assert line["is_essential"]  # vẫn là hũ đệm với model
    assert goal["on_track"] and line["proposed_monthly_vnd"] >= goal["monthly_needed_vnd"]
    # số dư 2.700.000 ₫ chưa tới đích 3.000.000 ₫: Dự phòng giữ phần chia hiện tại (BR-65, 26/11 trưa). Trước đó LP "optimal" cắt Dự phòng
    # 900.000 → 831.400 ₫ để Du lịch kịp hạn. Từ 26/11 chiều (#39) Chi hằng ngày, Giải trí chỉ xuống tới sàn chi (nửa mức chi thật gần
    # đây) nên Du lịch không còn kịp hạn gốc mà lùi hạn (trước: cắt Chi hằng ngày còn 42.600 ₫ để Du lịch kịp hạn); bản lưu vẫn là "kịp
    # hạn sau khi điều chỉnh"
    assert line["proposed_monthly_vnd"] >= line["current_monthly_vnd"]
    assert plan["status"] == "relaxed"
    assert {r["kind"] for r in plan["relaxations"]} == {"discretionary_reduced", "goal_delayed"}
    assert [g["jar"]["code"] for g in plan["goals"] if not g["on_track"]] == ["muc_tieu"]
    lines = {x["jar"]["code"]: x for x in plan["lines"]}
    for code in ("chi_hang_ngay", "giai_tri"):
        # sàn chi (sàn mềm, C3 của báo cáo rà soát #39) báo ở `recent_spend`; LP vẫn giữ nó như ràng buộc mềm
        assert 0 < lines[code]["recent_spend"]["keep_floor_vnd"] <= lines[code]["proposed_monthly_vnd"], code
    # bản đã lưu mang đúng mục tiêu đó; model thấy mục tiêu người dùng nói trong ngữ cảnh
    saved = next(g for g in rm["goals"] if g["jar"]["code"] == "du_phong")
    assert saved["target_vnd"] == 3_000_000 and saved["on_track"]
    assert rm["feasibility"] == "relaxed" and rm["reason"]["code"] == "user_request"
    assert got["planner"].contexts[0]["context"]["user_goal"]["jar_code"] == "du_phong"
    # không ghi gì vào hũ: mục đích, mục tiêu, tỷ lệ như trước
    keys = ("purpose", "goal_vnd", "goal_date", "split_percent", "balance_vnd")
    assert {k: got["after"]["du_phong"].get(k) for k in keys} == {k: before["du_phong"].get(k) for k in keys}


def test_dich_du_phong_khong_kha_thi_luu_chua_kha_thi_kem_hai_lua_chon(env):
    got = _build(env, UserGoal("du_phong", 30_000_000, ONE_MONTH))
    _report("đích Dự phòng 30 triệu trong 1 tháng", got)
    plan, rm = got["plan"], got["roadmap"]
    assert plan["status"] == "infeasible" and plan["headline"].startswith("Chưa khả thi")
    goal = next(g for g in rm["goals"] if g["jar"]["code"] == "du_phong")
    assert not goal["on_track"] and goal["shortfall_vnd"] > 0
    assert rm["feasibility"] == "infeasible"
    assert {a["kind"] for a in rm["alternatives"]} == {"delay_goal", "reduce_goal"}
    assert all(a["jar_code"] == "du_phong" for a in rm["alternatives"])
