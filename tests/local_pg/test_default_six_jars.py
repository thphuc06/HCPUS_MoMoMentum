"""End-to-end six-jar tests using local PostgreSQL and deterministic engines."""

from __future__ import annotations

import json
from datetime import date

import psycopg
import pytest
from conftest import REPO, _load
from ledger_fakes import http_event
from pipeline_helpers import make_settings

from yofina_core.errors import ErrorCode, YofinaError
from yofina_forecast.allocation import AllocationEngine
from yofina_forecast.inputs import build_inputs
from yofina_forecast.repo import ForecastRepo
from yofina_forecast.resilience import ResilienceEngine
from yofina_forecast.runner import Pipeline
from yofina_forecast.scenario import ScenarioEngine
from yofina_forecast.stress import StressEngine
from yofina_ledger.rest_api import handle_http
from yofina_planner.facts import facts_from_rows

EXPECTED = {
    "chi_hang_ngay": ("spending", None, 35),
    "nghia_vu": ("obligation", None, 35),
    "du_phong": ("saving", "buffer", 15),
    "quy_don": ("saving", "sinking", 5),
    "muc_tieu": ("saving", "goal", 5),
    "tich_luy_dai_han": ("saving", "long_term", 5),
}
TRACE = "sixjars"


def _read_jars(env, user):
    return env.svc.jars_response(user, trace_id=TRACE)["jars"]


def _layout(jars):
    return {j["code"]: (j["kind"], j.get("purpose"), j["split_percent"]) for j in jars}


def _editable(jars):
    keys = (
        "code",
        "name",
        "color_key",
        "icon_key",
        "kind",
        "split_percent",
        "purpose",
        "goal_vnd",
        "goal_date",
    )
    return [{k: j[k] for k in keys if k in j} for j in jars]


def _reset(env, user, groups):
    return handle_http(http_event("POST", "/demo/reset", sub=user, groups=groups), env.svc)


def test_migration_and_catalogue_seed_preserve_preexisting_jar_rows(tmp_path):
    import pgserver

    splitter = _load("sqlsplit", REPO / "infra-cdk/lambdas/migrator/sqlsplit.py")
    migration = REPO / "db/migrations/0055_default_six_jars.sql"
    seed = REPO / "db/seed/jar_templates.sql"
    server = pgserver.get_server(str(tmp_path / "pg"), cleanup_mode="stop")
    try:
        with psycopg.connect(server.get_uri(), autocommit=True) as conn:

            def apply(path):
                with conn.transaction():
                    for sql in splitter.split_migration(path.read_text(encoding="utf-8")):
                        conn.execute(sql)

            for path in sorted(migration.parent.glob("*.sql")):
                if path == migration:
                    break
                apply(path)

            conn.execute("INSERT INTO users(id, display_name) VALUES ('existing', 'Existing')")
            conn.execute(
                "INSERT INTO jars(user_id, code, name, color_key, icon_key, balance_vnd, split_percent, kind) "
                "VALUES ('existing', 'du_phong', 'Original buffer', 'blue', 'shield', 321000, 37.25, 'saving'), "
                "('existing', 'an_uong', 'Original food', 'teal', 'utensils', 127000, 62.75, 'spending')"
            )
            select = "SELECT code, name, balance_vnd, split_percent FROM jars ORDER BY code"
            before = conn.execute(select).fetchall()
            apply(migration)
            apply(seed)
            apply(seed)
            assert conn.execute(select).fetchall() == before
            assert conn.execute("SELECT count(purpose) FROM jars").fetchone() == (0,)
            assert conn.execute(
                "SELECT count(*), sum(default_split_percent) FROM jar_templates WHERE is_default"
            ).fetchone() == (6, 100)
    finally:
        server.cleanup()


def test_onboarding_and_edit_purpose_amount_date_and_split(env):
    user = "six-onboarding"
    env.act(user, "update_profile", {"monthly_salary_vnd": 9_000_000, "payday_day": 5})
    before = _read_jars(env, user)
    assert _layout(before) == EXPECTED
    assert all(j["balance_vnd"] == 0 for j in before)
    overview = env.svc.overview_response(user)
    assert _layout(overview["jars"]) == EXPECTED
    types = {row["tx_type"]: row for row in env.svc.tx_types_response(user)["tx_types"]}
    assert types["rent"]["default_jar"] == "nghia_vu"
    assert types["food_drink"]["default_jar"] == "chi_hang_ngay"
    assert {j["code"] for j in overview["system_jars"]} == {"tien_vao_khac", "chua_phan_loai"}
    assert {
        t["code"]: t.get("purpose")
        for t in env.svc.jar_templates_response()["templates"]
        if t["is_default"]
    } == {code: info[1] for code, info in EXPECTED.items()}

    patch = {j["code"]: j for j in _editable(before)}
    patch["quy_don"].update(goal_vnd=920_000, goal_date="2027-01-03", split_percent=6)
    patch["chi_hang_ngay"]["split_percent"] = 34
    patch["tich_luy_dai_han"]["goal_date"] = "2029-01-01"
    patch["muc_tieu"].update(goal_vnd=4_000_000, goal_date="2027-04-01")
    env.act(user, "save_jars", {"jars": list(patch.values())})
    jars = {j["code"]: j for j in _read_jars(env, user)}
    assert sum(j["split_percent"] for j in jars.values()) == 100
    assert jars["quy_don"]["goal_date"] == "2027-01-03"
    assert jars["quy_don"]["goal_vnd"] == 920_000
    detail = env.svc.jar_detail_response(user, "tich_luy_dai_han")["jar"]
    assert detail["purpose"] == "long_term" and detail["goal_date"] == "2029-01-01"

    older_request = [
        {k: v for k, v in j.items() if k not in ("purpose", "goal_date", "goal_vnd")}
        if j["code"] in ("quy_don", "tich_luy_dai_han")
        else j
        for j in _editable(jars.values())
    ]
    env.act(user, "save_jars", {"jars": older_request})
    assert env.svc.jar_detail_response(user, "quy_don")["jar"]["goal_date"] == "2027-01-03"
    assert env.svc.jar_detail_response(user, "tich_luy_dai_han")["jar"]["goal_date"] == "2029-01-01"
    dated = next(j for j in older_request if j["code"] == "quy_don")
    dated.update(purpose="sinking", goal_date="2027-02-01")
    with pytest.raises(YofinaError) as error:
        env.act(user, "save_jars", {"jars": older_request})
    assert error.value.code == ErrorCode.PARAMS_INVALID
    dated.pop("goal_date")
    older_request[0]["split_percent"] += 1
    with pytest.raises(YofinaError) as error:
        env.act(user, "save_jars", {"jars": older_request})
    assert error.value.code == ErrorCode.PARAMS_INVALID


def test_reset_preserves_legacy_until_allowed_and_is_repeatable(env):
    user, other = "six-existing", "six-other"
    env.reset(user, "minh")
    env.reset(other, "lan")
    before, other_before = _read_jars(env, user), _read_jars(env, other)
    assert len(before) == 7 and all("purpose" not in j for j in before)
    env.act(user, "update_profile", {"display_name": "Existing"})
    assert _read_jars(env, user) == before
    assert _reset(env, user, "ops")["statusCode"] == 403
    assert _read_jars(env, user) == before

    first = _reset(env, user, "persona-minh")
    assert first["statusCode"] == 200, first
    body = json.loads(first["body"])
    jars = _read_jars(env, user)
    assert body["jars_count"] == 6 and _layout(jars) == EXPECTED
    assert sum(j["balance_vnd"] for j in jars) == sum(j["balance_vnd"] for j in before)
    assert next(j for j in jars if j["code"] == "muc_tieu")["goal_date"] == "2027-04-01"
    assert _reset(env, user, "persona-minh")["statusCode"] == 200
    assert _read_jars(env, user) == jars and _read_jars(env, other) == other_before
    rows = env.repo.jar_view(user).jars
    assert len(rows) == 8
    assert {
        o["pay_jar_code"] for o in env.repo.list_obligations(user, status="active", limit=100)
    } == {"nghia_vu"}
    roadmaps = handle_http(http_event("GET", "/roadmap/versions", sub=user), env.svc)
    assert roadmaps["statusCode"] == 200
    assert len(json.loads(roadmaps["body"])["versions"]) == 3


def test_new_obligations_and_bnpl_choose_and_charge_the_explicit_source(env):
    user = "six-payments"
    env.act(user, "update_profile", {"monthly_salary_vnd": 9_000_000, "payday_day": 5})
    env.act(
        user, "record_transaction", {"kind": "income", "amount_vnd": 9_000_000, "tx_type": "salary"}
    )
    salary = env.svc.salary_events_response(user, status="pending")["salary_events"][0]
    env.act(user, "confirm_salary", {"salary_event_id": salary["id"], "decision": "split"})
    jars = _editable(_read_jars(env, user))
    env.act(
        user,
        "save_jars",
        {
            "jars": [
                {
                    "name": "Alternate",
                    "kind": "obligation",
                    "split_percent": 0,
                    "color_key": "slate",
                    "icon_key": "wallet",
                },
                *jars,
            ]
        },
    )
    for kind in ("rent", "bill", "loan"):
        env.act(
            user,
            "update_profile",
            {
                "obligation": {
                    "op": "upsert",
                    "kind": kind,
                    "name": kind,
                    "amount_vnd": 125_000,
                    "due_day": 25,
                    **({"pay_jar": "chi_hang_ngay"} if kind == "bill" else {}),
                }
            },
        )
    pay = {
        o["kind"]: o["pay_jar_code"]
        for o in env.repo.list_obligations(user, status="active", limit=100)
    }
    assert pay == {"rent": "nghia_vu", "loan": "nghia_vu", "bill": "chi_hang_ngay"}
    for amount in (400_000, 500_000):
        env.act(
            user,
            "record_transaction",
            {
                "kind": "expense",
                "funding": "credit",
                "amount_vnd": amount,
                "jar": "chi_hang_ngay",
            },
        )
    obligations = env.repo.list_obligations(user, status="active", limit=100)
    (bnpl,) = [o for o in obligations if o["kind"] == "bnpl"]
    assert (bnpl["pay_jar_code"], bnpl["principal_vnd"], bnpl["fee_vnd"], bnpl["amount_vnd"]) == (
        "nghia_vu",
        900_000,
        33_000,
        933_000,
    )
    before = {j["code"]: j["balance_vnd"] for j in _read_jars(env, user)}
    # An immediate purchase has one amount inclusive of its already-paid fee.
    env.act(
        user,
        "record_transaction",
        {
            "kind": "expense",
            "jar": "chi_hang_ngay",
            "amount_vnd": 103_000,
            "funding": "jar",
        },
    )
    before["chi_hang_ngay"] -= 103_000
    assert env.repo.list_obligations(user, status="active", limit=100) == obligations
    env.act(
        user,
        "record_transaction",
        {"kind": "expense", "obligation_id": str(bnpl["id"]), "amount_vnd": 933_000},
    )
    after = {j["code"]: j["balance_vnd"] for j in _read_jars(env, user)}
    assert after == {**before, "nghia_vu": before["nghia_vu"] - 933_000}
    assert not any(
        o["kind"] == "bnpl" for o in env.repo.list_obligations(user, status="active", limit=100)
    )
    with env.master() as conn:
        debits = conn.execute(
            "SELECT jar_code, amount_vnd FROM transactions WHERE user_id = %s AND obligation_id = %s",
            [user, bnpl["id"]],
        ).fetchall()
    assert debits == [("nghia_vu", -933_000)]


def test_demo_runout_and_bnpl_with_local_engines(env):
    user = "six-demo-minh"
    assert _reset(env, user, "persona-minh")["statusCode"] == 200
    settings = make_settings(n_paths_full=2000, scenario_n_paths=1000)
    pipeline = Pipeline(ForecastRepo(env.db), settings, None, clock=env.clock)
    assert pipeline.run_user(user, trigger="reset").status == "ok"
    summaries = {row["jar_code"]: row for row in env.repo.forecast_summaries(user)}
    assert set(summaries) == set(EXPECTED)
    daily = summaries["chi_hang_ngay"]
    print("Runout demo", daily["start_balance_vnd"], daily["runout_date"], daily["payday_date"])
    assert daily["status"] == "short" and daily["runout_date"] < daily["payday_date"]

    ctx = pipeline.load_context(user, env.clock())
    built = build_inputs(ctx, settings, user, n_paths=1000)
    source = next(j for j in built.inputs.jars if j.code == "nghia_vu")
    bnpl = next(o for o in ctx.obligations if o["kind"] == "bnpl")
    (due,) = [flow for flow in source.outflows if flow.ref_id == bnpl["id"]]
    assert due.amount_vnd == 1_000_000
    assert all(not j.outflows for j in built.inputs.jars if j.code != source.code)

    engine = ScenarioEngine(pipeline, env.repo, env.svc.ref, settings)
    data = engine.run(
        user,
        {
            "kind": "bnpl_purchase",
            "amount_vnd": 1_200_000,
            "funding_source": "credit",
            "label": "tai nghe",
        },
        trace_id=TRACE,
    )["data"]
    impact = data["obligation_impact"]
    assert (impact["cost"]["total_due_vnd"], impact["cost"]["fee_added_vnd"]) == (2_200_000, 0)
    assert impact["at_due"][0]["jar"]["code"] == "nghia_vu"
    assert impact["at_due"][0]["due_vnd"] == 2_200_000
    after = data["timelines"][0]["compare"]["after"]
    print(
        "BNPL demo", impact["cost"]["due_date"], after["runout_date"], after["min_balance_p50_vnd"]
    )
    assert after["status"] == "short"
    assert after["runout_date"] < daily["payday_date"].isoformat()

    gathered = ResilienceEngine(pipeline).gather(user, env.clock())
    facts = facts_from_rows(
        today=gathered.app_date,
        user=env.repo.user_row(user),
        jars=gathered.jar_rows,
        obligations=gathered.obligations,
        window_days=30,
    )
    assert facts.emergency_fund_vnd() == 2_700_000
    assert gathered.emergency_jar_code == "du_phong"
    stress = StressEngine(pipeline).run(user, "om_mot_tuan")["data"]
    assert stress["emergency_jar"]["code"] == "du_phong"
    allocation = AllocationEngine(pipeline).build(
        gathered,
        horizon_months=3,
        goal_args=[],
        shock_id=None,
        allow_relaxation=True,
    )
    roles = {j.code: j.role for j in allocation.problem.jars}
    assert (roles["du_phong"], roles["quy_don"], roles["muc_tieu"], roles["tich_luy_dai_han"]) == (
        "emergency",
        "saving",
        "goal",
        "saving",
    )
    assert allocation.goals["muc_tieu"].target_date == date(2027, 4, 1)
