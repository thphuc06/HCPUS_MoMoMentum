"""BR-65 (#44) trên ví demo Minh, qua lưu hũ thật và bộ tối ưu mặc định trên PostgreSQL cục bộ.

Dùng cách chạy ở `tests/local_pg/conftest.py` với riêng file này và `-s` để in bảng phân bổ.
"""

from __future__ import annotations

from test_default_six_jars import _allocation, _build, _reset

from yofina_core.roadmap import AllocationPlanData

TET = {"name": "Tết", "amount_vnd": 5_000_000, "needed_date": "2027-02-05"}
OUTSIDE_WINDOW = {**TET, "needed_date": "2027-03-05"}
TRAVEL_CODE = "muc_tieu"
BUFFER_CODE = "du_phong"


def _plan(env, user, commitments, *, held):
    reset = _reset(env, user, "persona-minh")
    assert reset["statusCode"] == 200, reset
    # Tính phần chia ban đầu từ cùng một đề xuất ở cả ba ví. Endpoint chỉ đọc và gọi build_proposal.
    proposal = env.svc.split_proposal_response(user, {"sinking_items": [TET]})
    assert proposal["status"] == "proposed", proposal
    jars = proposal["params"]["jars"]
    sinking = next(j for j in jars if j.get("purpose") == "sinking")
    assert sinking["split_percent"] > 0
    sinking["sinking_items"] = commitments
    env.act(user, "save_jars", {"jars": jars})

    _, gathered, engine = _allocation(env, user)
    sink_row = next(j for j in gathered.jar_rows if j["code"] == sinking["code"])
    assert sink_row["sinking_items"] == commitments and sink_row["balance_vnd"] == 0
    specs = {j.code: j for j in _build(engine, gathered).problem.jars}
    assert specs[sinking["code"]].hold_current is held
    assert specs[BUFFER_CODE].hold_current

    response = engine.optimize(user, {})
    assert response["status"] == "OK", response
    return AllocationPlanData.model_validate(response["data"]), sinking["code"]


def _print_plan(label, plan):
    goal = next(g for g in plan.goals if g.jar.code == TRAVEL_CODE)
    print(f"\n{label} | {plan.status} | vòng nới: {plan.solver.relaxation_rounds}")
    print(f"{'Hũ':<20} {'Chia cũ':>10} {'Chia mới':>10} {'Cũ đ/tháng':>12} {'Mới đ/tháng':>12}")
    for line in plan.lines:
        print(
            f"{line.jar.name:<20} {line.split_percent_current:>9.2f}% "
            f"{line.split_percent_proposed:>9.2f}% {line.current_monthly_vnd:>12,} "
            f"{line.proposed_monthly_vnd:>12,}"
        )
    print(
        f"Du lịch: hạn {goal.target_date}, dự kiến {goal.projected_date or 'chưa có'}, "
        f"{'kịp hạn' if goal.on_track else 'lùi hạn hoặc chưa khả thi'}"
    )


def test_roadmap_minh_giu_phan_chia_quy_don_tet_trong_ky(env):
    near, code = _plan(env, "minh-tet-trong-ky", [TET], held=True)
    far, far_code = _plan(env, "minh-tet-ngoai-ky", [OUTSIDE_WINDOW], held=False)
    empty, empty_code = _plan(env, "minh-tet-khong-khoan", [], held=False)
    assert code == far_code == empty_code
    for label, plan in (("Trong kỳ", near), ("Ngoài kỳ", far), ("Không có khoản", empty)):
        _print_plan(label, plan)

    near_lines = {line.jar.code: line for line in near.lines}
    assert near_lines[code].proposed_monthly_vnd >= near_lines[code].current_monthly_vnd > 0
    buffer = near_lines[BUFFER_CODE]
    assert buffer.proposed_monthly_vnd >= buffer.current_monthly_vnd
    assert all(g.jar.code != code for g in near.goals)

    travel = next(g for g in near.goals if g.jar.code == TRAVEL_CODE)
    assert travel.target_date == "2027-04-01"
    if travel.on_track:
        assert travel.projected_date and travel.projected_date <= travel.target_date
    else:
        assert travel.projected_date is None or travel.projected_date > travel.target_date
        assert any(r.kind == "goal_delayed" and r.jar_code == TRAVEL_CODE for r in near.relaxations)
        if near.status == "infeasible":
            assert {a.kind for a in near.alternatives} == {"delay_goal", "reduce_goal"}
        else:
            assert near.status == "relaxed" and near.solver.relaxation_rounds == 1

    assert {line.jar.code: line.current_monthly_vnd for line in far.lines} == {
        jar: line.current_monthly_vnd for jar, line in near_lines.items()
    }
    assert (far.status, far.solver.relaxation_rounds) == (
        empty.status,
        empty.solver.relaxation_rounds,
    )
    # Dự báo ngày cạn dùng hạt theo tài khoản, nên chỉ so phần phân bổ của mỗi dòng.
    assert [line.model_dump(exclude={"recent_spend"}) for line in far.lines] == [
        line.model_dump(exclude={"recent_spend"}) for line in empty.lines
    ]
    assert far.unallocated_vnd == empty.unallocated_vnd
    assert far.goals == empty.goals and far.relaxations == empty.relaxations
