"""Test chéo #41 × #44 trên ví Minh (chạy local_pg với `-s` để in hai bảng)."""

import pytest
from ledger_fakes import gateway_context
from test_default_six_jars import _allocation, _read_jars, _reset
from test_roadmap_regen_scene4 import FORECAST, LEDGER, LocalAllocation, LocalLambda, Planner, _llm
from yofina_agent.settings import AgentSettings
from yofina_roadmap.events import parse_event
from yofina_roadmap.repo import RoadmapRepo
from yofina_roadmap.runner import RoadmapRunner
from yofina_roadmap.settings import STAGES, RoadmapSettings

from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.roadmap import AllocationPlanData
from yofina_ledger.events import SOURCE
from yofina_ledger.gateway_api import handle_gateway

APP_DATE = "2026-11-21"
TET = {"name": "Tết", "amount_vnd": 5_000_000, "needed_date": "2027-02-05"}
EXPECTED_SPLITS = {
    "chi_hang_ngay": (3, 0),
    "nghia_vu": (33, 30),
    "du_phong": (10, 10),
    "an_uong": (30, 23),
    "di_lai": (7, 7),
    "giai_tri": (7, 2),
    "muc_tieu": (10, 0),
    "dau_tu": (0, 0),
    "quy_don": (0, 28),
}


def _regenerate(env, user, update, monkeypatch):
    pipeline, _, _ = _allocation(env, user)
    allocation = LocalAllocation(pipeline)
    monkeypatch.setattr(env.svc, "forecast", allocation)
    event = parse_event({"detail-type": update.detail_type, "source": SOURCE, "detail": update.detail})
    assert event.trigger == "goal_changed"
    planner = Planner()
    runner = RoadmapRunner(
        RoadmapRepo(env.db, 360),
        RoadmapSettings(
            LEDGER,
            FORECAST,
            "bus",
            5,
            65,
            360,
            dict(zip(STAGES, (5, 25, 45, 65, 85), strict=True)),
        ),
        AgentSettings.load({"YOFINA_GATEWAY_URL": "http://gateway.invalid/mcp"}),
        LocalLambda(env, pipeline),
        llm_factory=lambda: _llm(planner),
    )
    assert runner.process(event) == "done"
    result = handle_gateway(
        {"user_id": user, "which": "latest"}, gateway_context("planner___get_roadmap"), env.svc
    )
    assert result["status"] == "OK", result
    assert result["data"]["reason"]["code"] == "goal_changed"
    assert allocation.last is not None and allocation.last["status"] == "OK", allocation.last
    assert allocation.last["app_date"] == APP_DATE
    return AllocationPlanData.model_validate(allocation.last["data"])


def _sinking_preview(env, user, item):
    result = handle_gateway(
        {"user_id": user, "sinking_items": [item]},
        gateway_context("ledger___propose_jar_split"),
        env.svc,
    )
    assert result["status"] == "OK", result
    assert result["data"]["status"] == "proposed", result
    return result["data"]["confirm"]


def _sinking_jar(env, user):
    return next(jar for jar in _read_jars(env, user) if jar["code"] == "quy_don")


def _apply_save_jars(env, user, params, token):
    return env.svc.apply_action(
        user,
        "save_jars",
        params,
        token,
        trace_id="b1test123",
        channel="rest",
        source_tool="rest:POST /actions",
    )


def test_save_jars_rejects_stale_sinking_preview_and_accepts_fresh_preview(env):
    user = "minh-sinking-preview-version"
    assert _reset(env, user, "persona-minh")["statusCode"] == 200
    books = {"name": "Tiền sách", "amount_vnd": 100_000, "needed_date": "2027-05-15"}
    first = _sinking_preview(env, user, TET)
    second = _sinking_preview(env, user, books)
    signed_second = env.svc.issue_confirmation(
        user,
        tool="save_jars",
        params=second["params"],
        client_params_hash=second["params_hash"],
        trace_id="b1test123",
    )

    env.act(user, "save_jars", first["params"])
    with pytest.raises(YofinaError) as exc:
        _apply_save_jars(env, user, signed_second.params, signed_second.token)
    assert exc.value.code == ErrorCode.PARAMS_MISMATCH
    assert exc.value.message == "Danh sách hũ đã thay đổi sau khi tạo thẻ này, hãy xem lại."
    assert _sinking_jar(env, user)["sinking_items"] == [TET]

    refreshed = _sinking_preview(env, user, books)
    env.act(user, "save_jars", refreshed["params"])
    assert _sinking_jar(env, user)["sinking_items"] == [TET, books]


def test_save_jars_accepts_legacy_signed_params_without_base_version(env):
    user = "minh-sinking-preview-legacy"
    assert _reset(env, user, "persona-minh")["statusCode"] == 200
    preview = _sinking_preview(env, user, TET)
    legacy = {key: value for key, value in preview["params"].items() if key != "base_version"}
    signed = env.svc.confirm.issue(user, "save_jars", legacy)

    _apply_save_jars(env, user, legacy, signed.token)

    assert _sinking_jar(env, user)["sinking_items"] == [TET]


def test_minh_sinking_chat_then_regen(env, monkeypatch):
    user = "minh-tet-chat-regen"
    reset = _reset(env, user, "persona-minh")
    assert reset["statusCode"] == 200, reset
    before = {jar["code"]: jar["split_percent"] for jar in _read_jars(env, user)}

    result = handle_gateway(
        {"user_id": user, "sinking_items": [TET]},
        gateway_context("ledger___propose_jar_split"),
        env.svc,
    )
    assert result["status"] == "OK", result
    proposal = result["data"]
    assert proposal["app_date"] == APP_DATE
    assert proposal["status"] == "proposed", proposal
    confirm = proposal["confirm"]
    assert confirm["tool"] == "save_jars"
    assert confirm["params"] == proposal["params"]

    print("\nĐề xuất chia lương cho khoản Tết")
    print(f"{'Hũ':<20} {'Trước':>8} {'Sau':>8}")
    for jar in proposal["jars"]:
        print(f"{jar['name']:<20} {jar['split_before']:>7g}% {jar['split_after']:>7g}%")
    splits = {jar["code"]: (jar["split_before"], jar["split_after"]) for jar in proposal["jars"]}
    assert before == {code: old for code, (old, _) in splits.items() if code != "quy_don"}
    # Nghĩa vụ về mức khai báo. Chi hằng ngày, Giải trí, Du lịch và Ăn uống nhường phần chia theo BR-65.
    assert splits == EXPECTED_SPLITS
    decreased = {code for code, (old, new) in splits.items() if new < old}

    event_count = len(env.events.sent)
    env.act(user, "save_jars", confirm["params"])
    saved = {jar["code"]: jar for jar in _read_jars(env, user)}
    assert {code: jar["split_percent"] for code, jar in saved.items()} == {
        code: new for code, (_, new) in splits.items()
    }
    assert saved["quy_don"]["purpose"] == "sinking"
    assert saved["quy_don"]["sinking_items"] == [TET]
    (update,) = [
        event for event in env.events.sent[event_count:] if event.detail_type == "profile.updated"
    ]
    plan = _regenerate(env, user, update, monkeypatch)

    lines = {line.jar.code: line for line in plan.lines}
    print(f"\nPhân bổ sau khi sinh lại lộ trình ({plan.status})")
    print(
        f"{'Hũ':<20} {'Chia cũ':>9} {'Chia mới':>9} "
        f"{'Cũ đ/tháng':>12} {'Mới đ/tháng':>12} {'Sàn đ/tháng':>12}"
    )
    for line in plan.lines:
        print(
            f"{line.jar.name:<20} {line.split_percent_current:>8.2f}% "
            f"{line.split_percent_proposed:>8.2f}% {line.current_monthly_vnd:>12,} "
            f"{line.proposed_monthly_vnd:>12,} {line.floor_vnd:>12,}"
        )
    (travel,) = [goal for goal in plan.goals if goal.jar.code == "muc_tieu"]
    print(
        f"Du lịch | hạn {travel.target_date} | dự kiến {travel.projected_date or 'chưa có'} | "
        f"{'kịp hạn' if travel.on_track else 'lùi hạn hoặc chưa khả thi'}"
    )

    assert {code: line.split_percent_current for code, line in lines.items()} == {
        code: jar["split_percent"] for code, jar in saved.items()
    }
    sinking = lines["quy_don"]
    buffer = lines["du_phong"]
    assert sinking.proposed_monthly_vnd > 0
    assert buffer.proposed_monthly_vnd >= buffer.current_monthly_vnd

    hard_floor_deficits = {
        code
        for code, line in lines.items()
        if (line.kind == "obligation" or line.is_essential)
        and line.floor_vnd > line.current_monthly_vnd
    }
    increases = {
        code: line.proposed_monthly_vnd - line.current_monthly_vnd
        for code, line in lines.items()
        if line.proposed_monthly_vnd > line.current_monthly_vnd
    }
    assert (decreased & increases.keys()) <= hard_floor_deficits
    assert increases.keys().isdisjoint({"muc_tieu", "giai_tri", "dau_tu"})
    sinking_cut = max(0, sinking.current_monthly_vnd - sinking.proposed_monthly_vnd)
    assert sinking_cut <= sum(increases.get(code, 0) for code in hard_floor_deficits)

    assert travel.target_date == "2027-04-01"
    if travel.on_track:
        assert travel.projected_date is not None and travel.projected_date <= travel.target_date
    elif plan.status == "infeasible":
        assert {alt.kind for alt in plan.alternatives if alt.jar_code == "muc_tieu"} == {
            "delay_goal", "reduce_goal"
        }
    else:
        assert plan.status == "relaxed"
        assert any(r.kind == "goal_delayed" and r.jar_code == "muc_tieu" for r in plan.relaxations)
