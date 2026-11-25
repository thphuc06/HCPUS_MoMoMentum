"""Kê khai ở bước 3 của onboarding và xác nhận mọi thay đổi tỷ lệ (docs/plan/default-six-jars-rollout.md, "Bước 3", "Bước 4")
trên PostgreSQL cục bộ: đề xuất từ nghĩa vụ đã khai và khoản biết trước, bỏ qua kê khai, nghĩa vụ vượt số chia được, lương lệch
BR-12, bản xem trước `save_jars` (lý do bằng số đo, tỷ lệ và tiền mỗi kỳ trước và sau), lương đang chờ khi đổi tỷ lệ."""

from __future__ import annotations

import json
import math
from datetime import timedelta
from fractions import Fraction

from ledger_fakes import http_event

from yofina_core.clock import payday_dates
from yofina_ledger.rest_api import handle_http
from yofina_ledger.split_proposal import months_later

SALARY = 9_000_000
PAYDAY = 5
TRACE = "abc12345"


def _onboard(env, user, salary=SALARY):
    env.act(user, "update_profile", {"monthly_salary_vnd": salary, "payday_day": PAYDAY})


def _declare(env, user, kind, name, amount, due_day):
    env.act(
        user,
        "update_profile",
        {
            "obligation": {
                "op": "upsert",
                "kind": kind,
                "name": name,
                "amount_vnd": amount,
                "due_day": due_day,
                "is_essential": True,
            }
        },
    )


def _shares(env, user):
    return {j["code"]: j["split_percent"] for j in env.svc.jars_response(user, trace_id=TRACE)["jars"]}


def _today(env, user):
    return env.svc._load_state(user).today


def _preview(env, user, params):
    _, preview = env.svc.issue_confirmation_with_preview(
        user, tool="save_jars", params=params, client_params_hash=None, trace_id=TRACE
    )
    return preview


def _balances(env, user):
    return {j["code"]: j["balance_vnd"] for j in env.svc.jars_response(user, trace_id=TRACE)["jars"]}


def test_declared_obligations_and_known_item_are_proposed_then_saved_only_after_confirmation(env):
    user = "declare-propose"
    _onboard(env, user)
    _declare(env, user, "rent", "Tiền trọ", 2_500_000, 1)
    _declare(env, user, "bill", "Tiền điện", 600_000, 26)
    today = _today(env, user)
    needed = months_later(today, 3)
    paydays = len(payday_dates(PAYDAY, today, needed - timedelta(days=1)))
    sinking_share = math.ceil(Fraction(3_000_000, paydays) * 100 / SALARY)
    items = [{"name": "Tết", "amount_vnd": 3_000_000, "needed_date": needed.isoformat()}]
    before = _shares(env, user)

    result = env.svc.split_proposal_response(user, {"sinking_items": items})
    assert result["status"] == "proposed"
    assert result["obligations_monthly_vnd"] == 3_100_000  # 34,44% lương -> 35
    proposed = {j["code"]: j["split_percent"] for j in result["params"]["jars"]}
    assert proposed["nghia_vu"] == 35 and proposed["du_phong"] == 25
    assert proposed["quy_don"] == sinking_share
    assert proposed["chi_hang_ngay"] == 100 - 35 - 25 - sinking_share
    assert _shares(env, user) == before  # đề xuất không ghi gì

    preview = _preview(env, user, result["params"])
    changes = {c["label"]: c for c in preview["changes"]}
    assert changes["Lý do: hũ Nghĩa vụ"]["after"] == (
        "Nghĩa vụ đã khai 3.100.000 ₫/tháng = 34,4% lương 9.000.000 ₫"
    )
    assert changes["Hũ Nghĩa vụ"]["before"] == "33% · 2.970.000 ₫/kỳ"
    assert changes["Hũ Nghĩa vụ"]["after"] == "35% · 3.150.000 ₫/kỳ (+180.000 ₫)"
    template = next(t for t in env.svc.jar_templates_response()["templates"] if t["code"] == "quy_don")
    assert changes[f"Hũ mới: {template['name']}"]["after"].startswith(f"{sinking_share}% · ")
    assert any(label.startswith(f"Lý do: hũ {template['name']}") for label in changes)
    assert any("Dự báo tính lại ngay" in w for w in preview["warnings"])
    assert not any("đang chờ chia" in w for w in preview["warnings"])
    assert _shares(env, user) == before

    env.events.sent.clear()
    env.act(user, "save_jars", result["params"])
    jars = {j["code"]: j for j in env.svc.jars_response(user, trace_id=TRACE)["jars"]}
    assert {c: j["split_percent"] for c, j in jars.items()} == proposed
    detail = env.svc.jar_detail_response(user, "quy_don")["jar"]
    assert detail["purpose"] == "sinking" and detail["sinking_items"] == items
    # dự báo tính lại ngay: save_jars phát profile.updated (fields jars) cho pipeline sự kiện
    assert [e.detail["fields"] for e in env.events.sent if e.detail_type == "profile.updated"] == [["jars"]]

    again = env.svc.split_proposal_response(user, {})
    assert again["status"] == "aligned" and "params" not in again


def test_skipping_step_three_keeps_template_shares_and_marks_no_declarations(env):
    user = "declare-skip"
    _onboard(env, user)
    before = _shares(env, user)
    result = env.svc.split_proposal_response(user, {})
    assert result["status"] == "no_declarations"
    assert result["obligation_basis"] == "template"
    assert {j["code"]: j["split_after"] for j in result["jars"]} == before
    assert "params" not in result


def test_obligations_above_splittable_share_save_nothing_and_list_priority(env):
    user = "declare-over"
    _onboard(env, user)
    env.act(
        user,
        "update_profile",
        {"obligation": {"op": "upsert", "kind": "loan", "name": "Khoản vay", "amount_vnd": 1_500_000, "due_day": 10}},
    )
    _declare(env, user, "rent", "Tiền trọ", 8_000_000, 1)
    before = _shares(env, user)
    result = env.svc.split_proposal_response(user, {})
    assert result["status"] == "infeasible"
    assert result["required_percent"] == 116  # 9.500.000 = 105,6% -> 106, cộng sàn Dự phòng 10
    assert [o["name"] for o in result["priority_obligations"]] == ["Tiền trọ", "Khoản vay"]
    assert "params" not in result
    assert _shares(env, user) == before


def test_received_salary_far_from_declared_asks_to_update_salary_first(env):
    user = "declare-salary"
    _onboard(env, user)
    _declare(env, user, "rent", "Tiền trọ", 2_500_000, 1)
    env.act(user, "record_transaction", {"kind": "income", "amount_vnd": 7_000_000, "tx_type": "salary"})
    result = env.svc.split_proposal_response(user, {})
    assert result["status"] == "salary_mismatch"
    assert (result["salary_check"]["received_vnd"], result["salary_check"]["declared_vnd"]) == (7_000_000, SALARY)
    assert "params" not in result
    event = env.svc.salary_events_response(user, status="pending")["salary_events"][0]
    env.act(
        user,
        "confirm_salary",
        {"salary_event_id": event["id"], "decision": "split", "update_declared_salary": True},
    )
    updated = env.svc.split_proposal_response(user, {})
    assert updated["status"] == "proposed"
    assert updated["salary_vnd"] == 7_000_000  # mẫu số chỉ là lương đã khai
    assert {j["code"]: j["split_percent"] for j in updated["params"]["jars"]}["nghia_vu"] == 36  # 35,7% -> 36


def test_pending_salary_split_uses_shares_saved_before_its_confirmation(env):
    changed = None
    for user, order in (("declare-this-period", "save_first"), ("declare-next-period", "salary_first")):
        _onboard(env, user)
        _declare(env, user, "rent", "Tiền trọ", 2_700_000, 1)  # 30% -> Nghĩa vụ 30
        env.act(user, "record_transaction", {"kind": "income", "amount_vnd": SALARY, "tx_type": "salary"})
        event = env.svc.salary_events_response(user, status="pending")["salary_events"][0]
        result = env.svc.split_proposal_response(user, {})
        assert result["pending_salary"] == {"salary_event_id": event["id"], "amount_vnd": SALARY}
        changed = result["params"]
        preview = _preview(env, user, changed)
        assert any("đang chờ chia" in w and "kỳ này" in w and "kỳ sau" in w for w in preview["warnings"])
        split = {"salary_event_id": event["id"], "decision": "split"}
        if order == "save_first":  # "áp cho kỳ này": lưu trước, lương chờ chia theo tỷ lệ mới
            env.act(user, "save_jars", changed)
            env.act(user, "confirm_salary", split)
            assert _balances(env, user)["nghia_vu"] == 2_700_000
        else:  # "từ kỳ sau": chia lương chờ theo tỷ lệ cũ rồi mới lưu
            env.act(user, "confirm_salary", split)
            env.act(user, "save_jars", changed)
            assert _balances(env, user)["nghia_vu"] == 2_970_000
        assert _shares(env, user)["nghia_vu"] == 30
    assert changed is not None


def test_rest_route_reads_only_and_validates_known_items(env):
    user = "declare-rest"
    _onboard(env, user)
    today = _today(env, user)
    ok = handle_http(
        http_event(
            "POST",
            "/jars/split-proposal",
            sub=user,
            body={"sinking_items": [{"name": "Học phí", "amount_vnd": 1_200_000, "needed_date": months_later(today, 2).isoformat()}]},
        ),
        env.svc,
    )
    assert ok["statusCode"] == 200, ok
    body = json.loads(ok["body"])
    assert body["status"] == "proposed" and body["app_date"] == today.isoformat()
    assert "quy_don" not in _shares(env, user)
    for bad in (
        {"sinking_items": [{"name": "Học phí", "amount_vnd": 1, "needed_date": months_later(today, 13).isoformat()}]},
        {"sinking_items": [{"name": "Học phí", "amount_vnd": 1, "needed_date": today.isoformat()}]},
        {"jars": []},
    ):
        res = handle_http(http_event("POST", "/jars/split-proposal", sub=user, body=bad), env.svc)
        assert json.loads(res["body"])["error"]["code"] == "PARAMS_INVALID", res
