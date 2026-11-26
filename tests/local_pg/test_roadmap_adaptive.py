"""Lộ trình thích ứng (brief GG, issue #39) trên ví demo của `minh`, PostgreSQL cục bộ, không gọi AWS, không gọi model thật. `build_roadmap`
của agent chạy với hai Lambda tool THẬT trong tiến trình (ledger, forecast, LP `optimize_allocation`) như `test_roadmap_buffer_goal`.

- Chuyển ngay theo lời người dùng (C3, C4): câu "chuyển ngay 3 triệu từ Chi hằng ngày sang Dự phòng" tới planner (đã che PII), số tiền
  đọc bằng mã thành `user_amounts`; model giả dựng đúng một bước chuyển làm ngay theo số đó. Số dư đủ thì bước 3.000.000 ₫ được lưu (trần
  là số dư hũ nguồn trừ khoản nó phải trả trước kỳ lương, không so với phần tăng mỗi tháng của LP); số dư không đủ thì bước vào vòng sửa với
  phản hồi nêu trần.
- Mục tiêu không hạn (V2): "quỹ cưới 150 triệu" trên một hũ mục tiêu chưa có hạn: LP không đặt mức cần, không gán hạn 3 tháng, bản lưu
  mang mục tiêu không có `target_date` và lời kết nói chưa có hạn.

Số đo in ra với `-s`:

    uv run --python 3.12 --no-project --with pgserver --with "psycopg[binary]" --with pydantic --with pytest --with jsonschema \
        --with pyyaml --with referencing --with numpy --with boto3 --with scipy --with ruptures \
        pytest tests/local_pg/test_roadmap_adaptive.py -p no:cacheprovider -s
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from ledger_fakes import gateway_context, http_event
from pipeline_helpers import make_settings
from test_roadmap_regen_scene4 import FORECAST, LEDGER, LocalAllocation, LocalLambda, Planner, _llm, rejected_steps
from yofina_agent import notices
from yofina_agent.roadmap_agent import UserGoal, build_roadmap
from yofina_agent.settings import AgentSettings
from yofina_roadmap.tool_caller import LambdaTools

from yofina_core import blocks as B
from yofina_core.llm import TurnScope
from yofina_forecast.allocation import AllocationEngine
from yofina_forecast.repo import ForecastRepo
from yofina_forecast.runner import Pipeline
from yofina_ledger.gateway_api import handle_gateway as ledger_gateway
from yofina_ledger.rest_api import handle_http

USER = "sub-lotrinh-thich-ung"  # người dùng riêng mang persona minh
MOVE_NOW = "Mình muốn chuyển ngay 3 triệu từ Chi hằng ngày sang Dự phòng, lập lộ trình theo vậy, số mình 0901234567"
#: ngày mô phỏng 21/11/2026 cộng ba tháng: cách tính cũ của mục tiêu không hạn (hết `allocation_horizon_months`)
THREE_MONTHS = "2027-02-21"


class NowPlanner(Planner):
    """Model giả: một bước chuyển làm ngay từ Chi hằng ngày sang Dự phòng theo số tiền người dùng nêu (`user_amount`) và một lời nhắc; ở
    vòng sửa thì bỏ bước bị phản hồi (chỉ còn lời nhắc)."""

    @staticmethod
    def outline(model_context: dict[str, Any]) -> dict[str, Any]:
        flagged = {item["step_id"] for item in model_context.get("feedback", []) if item.get("step_id")}
        move = {
            "step_id": "chuyen_ngay", "kind": "set_aside", "title": "Chuyển từ Chi hằng ngày sang Dự phòng ngay",
            "reason": "Bạn muốn dồn tiền vào quỹ dự phòng ngay.", "jar_code": "chi_hang_ngay", "to_jar_code": "du_phong",
            "amount_ref": {"jar_code": "du_phong", "field": "user_amount", "index": 0}, "action": "move_between_jars",
        }  # fmt: skip
        remind = {
            "step_id": "nhac_xem_lai", "kind": "remind", "title": "Đặt nhắc xem lại các hũ", "reason": "Xem lại sau kỳ lương.",
            "action": "schedule_nudge",
        }  # fmt: skip
        now = [] if "chuyen_ngay" in flagged else [move]
        return {
            "phases": [
                {"phase_id": "truoc_ky_luong", "title": "Trước kỳ lương kế", "steps": now or [dict(remind, step_id="nhac_som")]},
                {"phase_id": "ve_dich", "title": "Về đích", "steps": [remind]},
            ]
        }


def _tool(env, name: str, **args: Any) -> dict[str, Any]:
    out = ledger_gateway({"user_id": USER, **args}, gateway_context(name), env.svc)
    assert out["status"] == "OK", out
    return out


def _reset(env) -> Pipeline:
    pipeline = Pipeline(ForecastRepo(env.db), make_settings(n_paths_full=600, n_paths_fast=400), None, clock=env.clock)
    r = handle_http(http_event("POST", "/demo/reset", sub=USER, groups="persona-minh"), env.svc)
    assert r["statusCode"] == 200, r
    assert pipeline.run_user(USER, trigger="reset").status == "ok"
    return pipeline


def _build(env, pipeline: Pipeline, planner: Planner, **kwargs: Any) -> dict[str, Any]:
    allocation = LocalAllocation(pipeline)
    env.svc.forecast = allocation
    settings = AgentSettings.load({"YOFINA_GATEWAY_URL": "http://gateway.invalid/mcp"})
    tools = LambdaTools(LocalLambda(env, pipeline), {"ledger": LEDGER, "planner": LEDGER, "forecast": FORECAST}, USER)
    try:
        result = asyncio.run(
            build_roadmap(
                tools, _llm(planner), settings, TurnScope(settings.max_model_calls_per_turn),
                reason_code="user_request", **kwargs,
            )
        )  # fmt: skip
    finally:
        env.svc.forecast = None
    assert result.outcome is not None and result.outcome.ok, result
    assert allocation.last is not None
    return {"roadmap": _tool(env, "planner___get_roadmap", which="latest")["data"], "plan": allocation.last["data"]}


def test_chuyen_ngay_3_trieu_theo_loi_nguoi_dung_khi_so_du_du(env, caplog):
    caplog.set_level("WARNING", logger="yofina.agent.roadmap")
    pipeline = _reset(env)
    # đưa Chi hằng ngày lên trên 3 triệu bằng hai lần chuyển đã xác nhận (luồng token như người dùng làm)
    env.act(USER, "move_between_jars", {"from_jar": "muc_tieu", "to_jar": "chi_hang_ngay", "amount_vnd": 1_800_000})
    env.act(USER, "move_between_jars", {"from_jar": "du_phong", "to_jar": "chi_hang_ngay", "amount_vnd": 1_000_000})
    assert pipeline.run_user(USER, trigger="event").status == "ok"
    before = {j["code"]: j["balance_vnd"] for j in _tool(env, "ledger___get_jar_balances")["data"]["jars"]}
    planner = NowPlanner()
    got = _build(env, pipeline, planner, user_request=MOVE_NOW)
    sent = planner.contexts[0]
    print("\n[chuyển ngay 3 triệu] số dư trước:", {c: before[c] for c in ("chi_hang_ngay", "du_phong")})
    print("  lời người dùng tới planner:", sent["user_request"]["text"])
    print("  nguồn giai đoạn đầu:", sent["context"]["first_phase_sources"].get("chi_hang_ngay"))
    steps = [s for p in got["roadmap"]["phases"] for s in p["steps"]]
    print("  bản đã lưu:", json.dumps([(s["step_id"], s["kind"], s.get("amount_vnd"), s.get("metrics")) for s in steps], ensure_ascii=False))
    print("  bước bị từ chối:", len(rejected_steps(caplog)))
    assert "0901234567" not in sent["user_request"]["text"]
    assert sent["context"]["user_amounts"] == [{"amount_text": "3.000.000 ₫"}]
    move = next(s for s in steps if s["step_id"] == "chuyen_ngay")
    assert (move["jar_code"], move["to_jar_code"], move["amount_vnd"]) == ("chi_hang_ngay", "du_phong", 3_000_000)
    assert got["roadmap"]["phases"][0]["start_date"] == got["roadmap"]["app_date"]  # bước làm ngay
    assert move["metrics"][0]["before"] == f"{before['chi_hang_ngay']:,} ₫".replace(",", ".")
    assert rejected_steps(caplog) == []


def test_chuyen_ngay_3_trieu_khi_so_du_khong_du_thi_vao_vong_sua_neu_tran(env, caplog):
    caplog.set_level("WARNING", logger="yofina.agent.roadmap")
    pipeline = _reset(env)
    planner = NowPlanner()
    got = _build(env, pipeline, planner, user_request=MOVE_NOW)
    (feedback,) = planner.contexts[1]["feedback"]
    print("\n[chuyển ngay 3 triệu, số dư 300.000 ₫] phản hồi:", feedback["message"])
    assert feedback["step_id"] == "chuyen_ngay" and "300.000 ₫" in feedback["message"]
    assert [r["detail"] for r in rejected_steps(caplog)] == ["amount_over_available"]
    assert all(s["step_id"] != "chuyen_ngay" for p in got["roadmap"]["phases"] for s in p["steps"])


def test_quy_cuoi_150_trieu_chua_co_han_khong_dat_muc_can_cung(env):
    pipeline = _reset(env)
    with env.master() as conn:  # hũ mục tiêu chưa có mục tiêu và hạn (người dùng mới thêm hũ cho đám cưới)
        conn.execute(
            "UPDATE jars SET name = 'Quỹ cưới', goal_vnd = NULL, goal_date = NULL WHERE user_id = %s AND code = 'muc_tieu'", [USER]
        )
    got = _build(env, pipeline, Planner(), user_goal=UserGoal("muc_tieu", 150_000_000), user_request="Quỹ cưới 150 triệu")
    plan, rm = got["plan"], got["roadmap"]
    goal = next(g for g in plan["goals"] if g["jar"]["code"] == "muc_tieu")
    lines = {x["jar"]["code"]: x for x in plan["lines"]}
    print(f"\n[quỹ cưới 150 triệu, không hạn] LP {plan['status']} | {plan['headline']}")
    print("  mục tiêu:", goal)
    print("  phân bổ:", {c: (x["current_monthly_vnd"], x["proposed_monthly_vnd"]) for c, x in lines.items()})
    data = B.RoadmapData.model_validate(rm)
    print("  bản đã lưu:", rm["feasibility"], "| lời kết:", " ".join(notices.roadmap_outlook(data)))
    assert "target_date" not in goal and goal["monthly_needed_vnd"] == 0 and goal["on_track"]
    assert not any(r["kind"] == "goal_delayed" and r["jar_code"] == "muc_tieu" for r in plan["relaxations"])
    assert "chưa có hạn" in plan["headline"]
    # không ép mọi hũ xuống sàn: phương án không phải nới gì, hũ chi giữ ít nhất mức nên giữ; hũ mục tiêu chỉ nhận phần còn lại sau chi
    # thiết yếu (thứ tự ưu tiên)
    assert plan["status"] == "optimal" and plan["relaxations"] == []
    for code, line in lines.items():
        if "recent_spend" in line:
            assert line["proposed_monthly_vnd"] >= line["recent_spend"]["keep_floor_vnd"], code
    # cách tính cũ (coi như hạn 3 tháng): cần khoảng 50 triệu mỗi tháng, chưa khả thi và ép các hũ xuống
    dated = AllocationEngine(pipeline).optimize(
        USER, {"goals": [{"jar": "muc_tieu", "target_vnd": 150_000_000, "target_date": THREE_MONTHS}]}
    )["data"]
    print(f"  so sánh hạn 3 tháng: LP {dated['status']} | {dated['headline']}")
    assert dated["status"] == "infeasible"
    saved = next(g for g in rm["goals"] if g["jar"]["code"] == "muc_tieu")
    assert "target_date" not in saved
    assert any("chưa có hạn" in line and "Quỹ cưới" in line for line in notices.roadmap_outlook(data))
