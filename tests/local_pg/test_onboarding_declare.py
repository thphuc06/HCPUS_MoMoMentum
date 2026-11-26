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


def _spend_floor_percent(env, user, code):
    """Sàn chi của hũ theo đúng số LP phân bổ dùng (chuỗi chi của ngữ cảnh dự báo, mức nền bền `typical_monthly` của
    `yofina_core.spend_baseline` từ 26/11 tối, tỷ lệ giữ của bộ tối ưu), quy ra điểm lương làm tròn lên."""
    from yofina_core.spend_baseline import BaselineSettings, typical_monthly
    from yofina_forecast.inputs import Context
    from yofina_forecast.repo import ForecastRepo
    from yofina_forecast.settings import DEFAULT_ALLOCATION_PARAMS as P

    ctx = Context.from_rows(ForecastRepo(env.db).context(user, env.clock(), "Asia/Ho_Chi_Minh", 330))
    spend = next(j["spend"] for j in ctx.jars if j["code"] == code)
    base = BaselineSettings(P.spend_baseline_weeks, P.spend_baseline_min_weeks, P.month_days, 30)
    typical = typical_monthly(spend, base).monthly_vnd
    return typical, math.ceil(Fraction(round(P.spending_keep_ratio * typical) * 100, SALARY))


def test_demo_wallet_proposal_keeps_essential_jars_and_takes_from_entertainment_first(env):
    """Ví demo (Chi hằng ngày cạnh Ăn uống, Đi lại, Giải trí): khai thêm khoản vay thì phần chênh lấy từ Chi hằng ngày rồi Giải trí (hũ
    chi không thiết yếu theo loại giao dịch của bảng tra thật), không từ Ăn uống hay Đi lại (BR-21, BR-54); Giải trí không xuống dưới
    phần lương của khoản định kỳ trả từ nó (Netflix của `minh`, #39 26/11). Từ 26/11 chiều (#39) hai hũ chi đó chỉ xuống tới sàn chi
    (nửa mức chi thật gần đây, cùng số của LP), phần còn thiếu lấy tiếp từ hũ mục tiêu (trước: Chi hằng ngày về 0, Giải trí 2%)."""
    user = "declare-demo"
    assert handle_http(http_event("POST", "/demo/reset", sub=user, groups="persona-minh"), env.svc)["statusCode"] == 200
    before = _shares(env, user)
    obligations = env.svc.obligations_response(user)["obligations"]
    paid_by_fun = sum(int(o["amount_vnd"]) for o in obligations if o.get("pay_jar") == "giai_tri")
    assert paid_by_fun > 0  # Netflix
    fun_floor = math.ceil(Fraction(paid_by_fun * 100, SALARY))
    _, daily_keep = _spend_floor_percent(env, user, "chi_hang_ngay")
    _, fun_keep = _spend_floor_percent(env, user, "giai_tri")
    assert 0 < daily_keep < before["chi_hang_ngay"] and fun_floor < fun_keep < before["giai_tri"]
    _declare(env, user, "loan", "Khoản vay", 1_500_000, 10)
    result = env.svc.split_proposal_response(user, {})
    assert result["status"] == "proposed"
    after = {j["code"]: j["split_after"] for j in result["jars"]}
    gained = after["nghia_vu"] - before["nghia_vu"]
    assert gained > before["chi_hang_ngay"] + before["giai_tri"] - daily_keep - fun_keep  # đủ lớn để chạm sàn chi của cả hai
    assert after["an_uong"] == before["an_uong"] and after["di_lai"] == before["di_lai"]
    assert after["chi_hang_ngay"] == daily_keep and after["giai_tri"] == fun_keep
    assert after["muc_tieu"] < before["muc_tieu"]
    assert sum(after.values()) == 100


def test_demo_wallet_proposal_with_loan_1_8_million(env):
    """Số đo cho báo cáo #39 (in với `-s`): khoản vay 1.800.000 ₫ trên ví demo của `minh`. Hũ mục tiêu về 0 trước khi sàn chi nhường;
    sàn chi chỉ nhường đúng phần nghĩa vụ còn thiếu."""
    user = "declare-demo-18"
    assert handle_http(http_event("POST", "/demo/reset", sub=user, groups="persona-minh"), env.svc)["statusCode"] == 200
    before = _shares(env, user)
    keeps = {code: _spend_floor_percent(env, user, code) for code in ("chi_hang_ngay", "giai_tri")}
    _declare(env, user, "loan", "Khoản vay", 1_800_000, 10)
    result = env.svc.split_proposal_response(user, {})
    after = {j["code"]: j["split_after"] for j in result["jars"]}
    print(f"\n[đề xuất tỷ lệ, khoản vay 1,8 triệu] {result['status']}; sàn chi (mức chi điển hình, điểm): {keeps}")
    for code, pct in after.items():
        print(f"  {code}: {before[code]} -> {pct}")
    assert result["status"] == "proposed" and sum(after.values()) == 100
    assert after["muc_tieu"] == 0 and after["giai_tri"] == keeps["giai_tri"][1]
    assert after["an_uong"] == before["an_uong"] and after["di_lai"] == before["di_lai"]
