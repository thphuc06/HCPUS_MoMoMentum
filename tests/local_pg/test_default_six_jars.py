"""Jar layout rollout and reset tests using local PostgreSQL."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, timedelta

import psycopg
import pytest
from conftest import NOW, REPO, _load
from ledger_fakes import http_event
from pipeline_helpers import make_settings

from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.wallet import DEFAULT_SPENDING_JAR
from yofina_forecast.allocation import AllocationEngine
from yofina_forecast.inputs import build_inputs
from yofina_forecast.repo import ForecastRepo
from yofina_forecast.resilience import ResilienceEngine, variable_monthly_spend
from yofina_forecast.runner import Pipeline
from yofina_forecast.scenario import ScenarioEngine
from yofina_forecast.stress import StressEngine
from yofina_ledger.rest_api import handle_http
from yofina_planner.facts import facts_from_rows

ONBOARDING = {
    "chi_hang_ngay": ("spending", None, 42),
    "nghia_vu": ("obligation", None, 33),
    "du_phong": ("saving", "buffer", 25),
}
# Bộ hũ demo (issue #39, đổi 26/11 sáng): ba hũ mặc định (Chi hằng ngày, Nghĩa vụ, Dự phòng) rồi các hũ người dùng tự thêm; tỷ lệ là
# tỷ lệ của hũ nguồn trong spec persona, hũ Chi hằng ngày lấy số điểm `split_from` của khối `demo_jars` từ hũ nguồn của nó.
DEMO_SOURCES = {
    "chi_hang_ngay": ("spending", None, ()),
    "nghia_vu": ("obligation", None, ("nghia_vu", "hoa_don")),
    "du_phong": ("saving", "buffer", ("du_phong",)),
    "an_uong": ("spending", None, ("an_uong",)),
    "di_lai": ("spending", None, ("di_lai",)),
    "giai_tri": ("spending", None, ("giai_tri",)),
    "muc_tieu": ("saving", "goal", ("du_lich",)),
    "dau_tu": ("saving", "long_term", ()),
}
DEMO = {  # minh: 3 / 31+5-3 / 10 / 30 / 7 / 7 / 10 / 0
    "chi_hang_ngay": ("spending", None, 3),
    "nghia_vu": ("obligation", None, 33),
    "du_phong": ("saving", "buffer", 10),
    "an_uong": ("spending", None, 30),
    "di_lai": ("spending", None, 7),
    "giai_tri": ("spending", None, 7),
    "muc_tieu": ("saving", "goal", 10),
    "dau_tu": ("saving", "long_term", 0),
}


def _daily_spec(persona):
    """Khối hũ Chi hằng ngày của ví demo trong spec persona."""
    spec = json.loads((REPO / "data" / "personas" / "specs" / f"{persona}.json").read_text("utf-8"))
    return next(j for j in spec["demo_jars"] if j["code"] == DEFAULT_SPENDING_JAR)


def _demo_layout(persona):
    """Bộ hũ demo kỳ vọng của persona, suy từ spec qua ánh xạ của test: hũ mục tiêu chỉ có khi persona có hũ Du lịch."""
    from personas import generate

    old = {j.code: j for j in generate(persona, anchor=date(2026, 11, 21)).jars}
    taken = _daily_spec(persona)["split_from"]
    out = {
        code: (kind, purpose, sum(old[s].split_percent for s in sources if s in old) - taken.get(code, 0))
        for code, (kind, purpose, sources) in DEMO_SOURCES.items()
        if code != "muc_tieu" or "du_lich" in old
    }
    out[DEFAULT_SPENDING_JAR] = ("spending", None, sum(taken.values()))
    return out
LEGACY = {
    "an_uong": ("spending", None, 25),
    "di_lai": ("spending", None, 10),
    "hoa_don": ("spending", None, 30),
    "giai_tri": ("spending", None, 10),
    "du_lich": ("saving", None, 5),
    "du_phong": ("saving", None, 15),
    "nghia_vu": ("obligation", None, 5),
}
TRACE = "jarlayout"


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
        "sinking_items",
        "goal_vnd",
        "goal_date",
    )
    return [{k: j[k] for k in keys if k in j} for j in jars]


def _reset(env, user, groups):
    return handle_http(http_event("POST", "/demo/reset", sub=user, groups=groups), env.svc)


def test_migration_and_seed_preserve_legacy_wallet_and_read_contract(tmp_path):
    import pgserver

    splitter = _load("sqlsplit", REPO / "infra-cdk/lambdas/migrator/sqlsplit.py")
    migration = REPO / "db/migrations/0057_default_six_jars.sql"
    commitments = migration.with_name("0058_sinking_commitments.sql")
    activation = migration.with_name("0059_activate_onboarding_jar_layout.sql")
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

            def legacy_init(user):
                # SQL used by the previous Ledger, which has no purpose parameter.
                with conn.transaction():
                    conn.execute("SET LOCAL ROLE yofina_app")
                    conn.execute("SELECT set_config('app.user_id', %s, true)", [user])
                    conn.execute(
                        "INSERT INTO users(id, display_name) VALUES (%s, 'Legacy')", [user]
                    )
                    conn.execute("SELECT app_ensure_system_jars(%s)", [user])
                    return conn.execute(
                        "INSERT INTO jars (user_id, code, name, color_key, icon_key, balance_vnd, "
                        "split_percent, sort_order, kind) "
                        "SELECT %s, t.code, t.name, t.color_key, t.icon_key, 0, t.default_split_percent, "
                        "t.sort_order, t.kind FROM jar_templates t WHERE t.is_default AND NOT EXISTS "
                        "(SELECT 1 FROM jars j WHERE j.user_id = %s AND j.kind <> 'system') "
                        "RETURNING code, kind, split_percent",
                        [user, user],
                    ).fetchall()

            def snapshot():
                return {
                    table: conn.execute(
                        f"SELECT to_jsonb(t) - 'purpose' - 'sinking_items' AS snapshot_row FROM {table} t "
                        "WHERE user_id = 'existing' ORDER BY snapshot_row"
                    ).fetchall()
                    for table in ("jars", "transactions", "salary_events", "obligations")
                }

            def legacy_reads():
                with conn.transaction():
                    conn.execute("SET LOCAL ROLE yofina_app")
                    results = [
                        conn.execute("SELECT * FROM app_list_jars('existing')"),
                        conn.execute("SELECT * FROM app_get_jar_state('existing')"),
                        conn.execute("SELECT app_get_overview('existing', %s, 'UTC')", [NOW]),
                        conn.execute(
                            "SELECT app_get_jar_detail('existing', 'an_uong', %s, 'UTC')", [NOW]
                        ),
                        conn.execute(
                            "SELECT * FROM app_get_forecast_context('existing', %s, 'UTC')", [NOW]
                        ),
                    ]
                    assert conn.execute("SELECT DISTINCT user_id FROM jars").fetchall() == [
                        ("existing",)
                    ]
                    return [
                        ([col.name for col in result.description], result.fetchall())
                        for result in results
                    ]

            apply(seed)
            assert {c: (k, None, p) for c, k, p in legacy_init("existing")} == LEGACY
            conn.execute(
                "UPDATE jars SET name = 'Original food', balance_vnd = 127000, split_percent = 22.5 "
                "WHERE user_id = 'existing' AND code = 'an_uong'"
            )
            conn.execute(
                "UPDATE jars SET balance_vnd = 321000, split_percent = 17.5 "
                "WHERE user_id = 'existing' AND code = 'du_phong'"
            )
            tx_id = conn.execute(
                "INSERT INTO transactions (user_id, occurred_at, app_date, kind, jar_code, amount_vnd, tx_type) "
                "VALUES ('existing', %s, DATE '2026-12-05', 'income', 'tien_vao_khac', 448000, 'salary') "
                "RETURNING id",
                [NOW],
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO salary_events (user_id, period_date, transaction_id, received_on, amount_vnd, "
                "status, split, confirmed_at) VALUES ('existing', DATE '2026-12-05', %s, DATE '2026-12-05', "
                """448000, 'confirmed', '[{"jar":"an_uong","amount_vnd":127000},
                {"jar":"du_phong","amount_vnd":321000}]', %s)""",
                [tx_id, NOW],
            )
            conn.execute(
                "INSERT INTO obligations (user_id, kind, name, amount_vnd, due_date, pay_jar_code) "
                "VALUES ('existing', 'bill', 'Electricity', 90000, DATE '2026-12-15', 'hoa_don')"
            )
            before, reads_before = snapshot(), legacy_reads()
            apply(migration)
            apply(commitments)  # cả hai phần schema chạy trước, bộ bảy vẫn bật (Bước 7 bước 1)
            apply(seed)
            assert {c: (k, None, p) for c, k, p in legacy_init("old-ledger")} == LEGACY
            assert snapshot() == before and legacy_reads() == reads_before
            assert conn.execute("SELECT count(purpose) FROM jars").fetchone() == (0,)
            apply(activation)
            apply(seed)
            assert snapshot() == before and legacy_reads() == reads_before
            assert conn.execute("SELECT count(purpose) FROM jars").fetchone() == (0,)
            assert {
                code: (kind, purpose, rate)
                for code, kind, purpose, rate in conn.execute(
                    "SELECT code, kind, purpose, default_split_percent FROM jar_templates WHERE is_default"
                )
            } == ONBOARDING
    finally:
        server.cleanup()


def test_onboarding_and_edit_purpose_amount_date_and_split(env):
    user = "six-onboarding"
    env.act(user, "update_profile", {"monthly_salary_vnd": 9_000_000, "payday_day": 5})
    before = _read_jars(env, user)
    assert _layout(before) == ONBOARDING
    assert sum(j["split_percent"] for j in before) == 100
    assert all(j["balance_vnd"] == 0 for j in before)
    overview = env.svc.overview_response(user)
    assert _layout(overview["jars"]) == ONBOARDING
    types = {row["tx_type"]: row for row in env.svc.tx_types_response(user)["tx_types"]}
    assert types["rent"]["default_jar"] == "nghia_vu"
    assert types["food_drink"]["default_jar"] == "chi_hang_ngay"
    assert {j["code"] for j in overview["system_jars"]} == {"tien_vao_khac", "chua_phan_loai"}
    templates = {t["code"]: t for t in env.svc.jar_templates_response()["templates"]}
    assert {code: t.get("purpose") for code, t in templates.items() if t["is_default"]} == {
        code: info[1] for code, info in ONBOARDING.items()
    }

    patch = {j["code"]: j for j in _editable(before)}
    for code in ("quy_don", "tich_luy_dai_han", "muc_tieu"):
        patch[code] = _editable([{**templates[code], "split_percent": 0}])[0]
    patch["quy_don"].update(goal_vnd=920_000, goal_date="2027-01-03", split_percent=6)
    commitments = [
        {"name": "Học phí", "amount_vnd": 400_000, "needed_date": "2027-02-15"},
        {"name": "Bảo hiểm", "amount_vnd": 800_000, "needed_date": "2027-03-15"},
    ]
    patch["quy_don"]["sinking_items"] = commitments
    patch["chi_hang_ngay"]["split_percent"] -= 6
    patch["tich_luy_dai_han"]["goal_date"] = "2029-01-01"
    patch["muc_tieu"].update(goal_vnd=4_000_000, goal_date="2027-04-01")
    env.act(user, "save_jars", {"jars": list(patch.values())})
    jars = {j["code"]: j for j in _read_jars(env, user)}
    assert sum(j["split_percent"] for j in jars.values()) == 100
    assert jars["quy_don"]["goal_date"] == "2027-01-03"
    assert jars["quy_don"]["goal_vnd"] == 920_000
    assert jars["quy_don"]["sinking_items"] == commitments
    assert env.svc.jar_detail_response(user, "quy_don")["jar"]["sinking_items"] == commitments
    detail = env.svc.jar_detail_response(user, "tich_luy_dai_han")["jar"]
    assert detail["purpose"] == "long_term" and detail["goal_date"] == "2029-01-01"

    older_request = [
        {k: v for k, v in j.items() if k not in ("purpose", "goal_date", "goal_vnd", "sinking_items")}
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
    dated["sinking_items"] = [{**commitments[0], "needed_date": "2027-03-01"}, commitments[1]]
    with pytest.raises(YofinaError) as error:
        env.act(user, "save_jars", {"jars": older_request})
    assert error.value.code == ErrorCode.PARAMS_INVALID
    dated.pop("sinking_items")
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
    jars = _read_jars(env, user)
    assert _layout(jars) == DEMO
    # hũ goal là hũ người dùng tự thêm cho mục tiêu Du lịch: tên theo hũ nguồn (lộ trình seed nói "hũ Du lịch")
    assert {j["code"]: j["name"] for j in jars}["muc_tieu"] == "Du lịch"
    # Ăn uống, Đi lại, Giải trí giữ số dư của ví persona; Nghĩa vụ = Nghĩa vụ + Hóa đơn; Mục tiêu = Du lịch; Đầu tư mới; Chi hằng
    # ngày là số dư cần đạt trong khối `demo_jars` của spec
    assert {j["code"]: j["balance_vnd"] for j in jars} == {
        "chi_hang_ngay": 300_000,
        "nghia_vu": 1_450_000,
        "du_phong": 2_700_000,
        "an_uong": 380_000,
        "di_lai": 640_000,
        "giai_tri": 760_000,
        "muc_tieu": 1_800_000,
        "dau_tu": 0,
    }
    assert [j["code"] for j in jars][:3] == ["chi_hang_ngay", "nghia_vu", "du_phong"]  # ba hũ mặc định trước
    assert sum(j["balance_vnd"] for j in jars) == sum(j["balance_vnd"] for j in before) + _daily_spec("minh")[
        "target_vnd"
    ]
    assert _reset(env, user, "persona-minh")["statusCode"] == 200
    assert _read_jars(env, user) == jars and _read_jars(env, other) == other_before
    rows = env.repo.jar_view(user).jars
    assert len(rows) == 10
    pay = {o["name"]: o["pay_jar_code"] for o in env.repo.list_obligations(user, status="active", limit=100)}
    # hũ trả theo cùng ánh xạ: cơm văn phòng vẫn trả từ Ăn uống (cảnh 1), Netflix từ Giải trí, hóa đơn và Trả sau từ Nghĩa vụ
    assert pay["Tiền cơm văn phòng"] == "an_uong" and pay["Netflix"] == "giai_tri"
    assert {pay[n] for n in ("Tiền điện", "Tiền thuê phòng", "Internet FPT", "Cước điện thoại")} == {"nghia_vu"}
    assert [c for n, c in pay.items() if n not in (
        "Tiền cơm văn phòng", "Netflix", "Tiền điện", "Tiền thuê phòng", "Internet FPT", "Cước điện thoại"
    )] == ["nghia_vu"]  # fmt: skip
    roadmaps = handle_http(http_event("GET", "/roadmap/versions", sub=user), env.svc)
    assert roadmaps["statusCode"] == 200
    versions = json.loads(roadmaps["body"])["versions"]
    assert sorted(v["version"] for v in versions) == [1, 2]  # v1 đã thay, v2 đang dùng, như ví persona (#22)
    # khối lộ trình (tên hũ của mục tiêu) và So với bản cũ (tên hũ đọc từ bảng jars) dùng đúng tên hũ của ví demo, không mã thô
    names = {j["code"]: j["name"] for j in jars}
    block = json.loads(handle_http(http_event("GET", "/roadmap", sub=user), env.svc)["body"])
    data = block["data"]
    assert [(g["jar"]["code"], g["jar"]["name"]) for g in data["goals"]] == [("muc_tieu", names["muc_tieu"])]
    diff = handle_http(
        http_event("GET", "/roadmap/diff", sub=user, query={"from_version": "1", "to_version": "2"}), env.svc
    )
    assert diff["statusCode"] == 200, diff
    text = diff["body"]
    assert not any(f'"{code}"' in text for code in ("du_lich", "hoa_don"))
    for field in (f for c in json.loads(text)["data"]["changes"] for f in c.get("fields", [])):
        if field["label"] in ("Hũ nguồn", "Hũ nhận"):
            assert {field["before"], field["after"]} <= {*names.values(), "(chưa có)", "(bỏ)"}


@pytest.mark.parametrize("persona", ["minh", "khoa", "lan", "vy"])
def test_reset_uses_demo_layout_for_each_persona(env, persona):
    from personas import generate

    user = f"layout-demo-{persona}"
    response = _reset(env, user, f"persona-{persona}")
    assert response["statusCode"] == 200, response
    expected = _demo_layout(persona)
    assert json.loads(response["body"])["jars_count"] == len(expected)
    jars = _read_jars(env, user)
    assert _layout(jars) == expected and DEFAULT_SPENDING_JAR in {j["code"] for j in jars}
    assert sum(j["split_percent"] for j in jars) == 100
    data = generate(persona, anchor=date(2026, 11, 21))
    old = {j.code: j for j in data.jars}
    assert sum(j["balance_vnd"] for j in jars) == sum(j.balance_vnd for j in data.jars) + _daily_spec(persona)[
        "target_vnd"
    ]
    if "du_lich" in old:
        goal = next(j for j in jars if j["code"] == "muc_tieu")
        assert (goal["goal_vnd"], goal["goal_date"]) == (
            old["du_lich"].goal_vnd, old["du_lich"].goal_date.isoformat()
        )
    codes = {j["code"] for j in jars}
    obligations = env.repo.list_obligations(user, status="active", limit=100)
    assert {o["pay_jar_code"] for o in obligations} <= codes
    assert {o["pay_jar_code"] for o in obligations if o["kind"] == "bnpl"} <= {"nghia_vu"}
    assert _reset(env, user, f"persona-{persona}")["statusCode"] == 200
    assert _read_jars(env, user) == jars


def test_demo_and_three_jar_wallets_route_new_transactions_by_type(env):
    """Giao dịch mới vào hũ theo loại (issue #39, 26/11): hũ riêng khớp loại thắng hũ chung. Ví demo 8 hũ (có cả Chi hằng ngày): ăn
    uống, đi lại, giải trí vào hũ riêng, hóa đơn vào Nghĩa vụ, du lịch vào hũ goal; ví ba hũ mới: chi vào Chi hằng ngày, hóa đơn vào
    Nghĩa vụ; ví ba hũ người dùng thêm Ăn uống: ăn uống vào Ăn uống, phần còn lại như ví ba hũ. Cùng một quy tắc cho `/tx-types`
    (hũ gợi ý) và ghi giao dịch không kèm hũ."""
    demo, fresh, food = "route-demo", "route-three", "route-three-food"
    assert _reset(env, demo, "persona-minh")["statusCode"] == 200
    for user in (fresh, food):
        env.act(user, "update_profile", {"monthly_salary_vnd": 9_000_000, "payday_day": 5})
    templates = {t["code"]: t for t in env.svc.jar_templates_response()["templates"]}
    jars = {j["code"]: j for j in _editable(_read_jars(env, food))}
    jars[DEFAULT_SPENDING_JAR]["split_percent"] -= 20
    added = _editable([{**templates["an_uong"], "split_percent": 20}])[0]
    env.act(food, "save_jars", {"jars": [*jars.values(), added]})
    assert {j["code"] for j in _read_jars(env, food)} == {*ONBOARDING, "an_uong"}
    for user in (fresh, food):
        env.act(user, "record_transaction", {"kind": "income", "amount_vnd": 9_000_000, "tx_type": "salary"})
        salary = env.svc.salary_events_response(user, status="pending")["salary_events"][0]
        env.act(user, "confirm_salary", {"salary_event_id": salary["id"], "decision": "split"})
    three = {
        "food_drink": "chi_hang_ngay", "grocery": "chi_hang_ngay", "ride_hailing": "chi_hang_ngay",
        "fuel": "chi_hang_ngay", "entertainment": "chi_hang_ngay", "bill_electricity": "nghia_vu",
        "bill_water": "nghia_vu", "phone_topup": "nghia_vu", "rent": "nghia_vu", "travel": "chi_hang_ngay",
    }  # fmt: skip
    expected = {
        demo: {
            "food_drink": "an_uong", "grocery": "an_uong", "ride_hailing": "di_lai", "fuel": "di_lai",
            "entertainment": "giai_tri", "bill_electricity": "nghia_vu", "bill_water": "nghia_vu",
            "phone_topup": "nghia_vu", "rent": "nghia_vu",
            "travel": "muc_tieu",  # hũ goal dựng từ hũ Du lịch thắng Chi hằng ngày
        },
        fresh: three,
        food: {**three, "food_drink": "an_uong", "grocery": "an_uong"},
    }  # fmt: skip
    for user, routes in expected.items():
        types = {row["tx_type"]: row for row in env.svc.tx_types_response(user)["tx_types"]}
        assert {k: types[k]["default_jar"] for k in routes} == routes
        for tx_type, jar in routes.items():
            before = {j["code"]: j["balance_vnd"] for j in _read_jars(env, user)}
            env.act(user, "record_transaction", {"kind": "expense", "amount_vnd": 1_000, "tx_type": tx_type})
            after = {j["code"]: j["balance_vnd"] for j in _read_jars(env, user)}
            assert after == {**before, jar: before[jar] - 1_000}, tx_type


def test_rollback_uses_legacy_onboarding_and_keeps_demo_layout(env, monkeypatch):
    monkeypatch.setenv("YOFINA_ONBOARDING_JAR_LAYOUT", "legacy")
    user = "layout-rollback"
    env.act(user, "update_profile", {"monthly_salary_vnd": 9_000_000, "payday_day": 5})
    assert _layout(_read_jars(env, user)) == LEGACY
    assert {
        t["code"]: (t["kind"], t.get("purpose"), t["default_split_percent"])
        for t in env.svc.jar_templates_response()["templates"]
        if t["is_default"]
    } == LEGACY
    assert _reset(env, "layout-rollback-demo", "persona-lan")["statusCode"] == 200
    assert _layout(_read_jars(env, "layout-rollback-demo")) == _demo_layout("lan")


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
    assert set(summaries) == set(DEMO)
    daily = summaries["an_uong"]
    print("Runout demo", daily["start_balance_vnd"], daily["runout_date"], daily["payday_date"])
    assert daily["status"] == "short" and daily["runout_date"] < daily["payday_date"]

    ctx = pipeline.load_context(user, env.clock())
    # chuỗi chi thiết yếu theo loại chỉ có ở Chi hằng ngày và hũ obligation (Nghĩa vụ: hóa đơn trả lẻ). Chi hằng ngày của ví demo chỉ
    # có chi lặt vặt (loại không thuộc nhóm thiết yếu) nên chuỗi đó bằng 0 dù hũ có chi; Ăn uống, Đi lại là hũ thiết yếu theo mã và
    # không bị đếm lại ở Chi hằng ngày
    assert {j["code"] for j in ctx.jars if "essential_spend" in j} == {DEFAULT_SPENDING_JAR, "nghia_vu"}
    chn = next(j for j in ctx.jars if j["code"] == DEFAULT_SPENDING_JAR)
    assert sum(chn["spend"]) > 0 and set(chn["essential_spend"]) == {0}
    built = build_inputs(ctx, settings, user, n_paths=1000)
    source = next(j for j in built.inputs.jars if j.code == "nghia_vu")
    bnpl = next(o for o in ctx.obligations if o["kind"] == "bnpl")
    (due,) = [flow for flow in source.outflows if flow.ref_id == bnpl["id"]]
    assert due.amount_vnd == 1_000_000
    assert due.date == date(2026, 12, 3)  # ngày đến hạn 3 của ví demo, trước lương 05/12
    assert all(
        flow.ref_id != bnpl["id"] for j in built.inputs.jars if j.code != source.code for flow in j.outflows
    )

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
    window = after["obligations_before_payday"]
    assert [row["date"] for row in window["items"]] == sorted(row["date"] for row in window["items"])
    assert [row["amount_vnd"] for row in window["items"] if row["label"] == bnpl["name"]] == [
        2_200_000
    ]
    assert window["first_shortfall"]["shortfall_vnd"] > 0
    assert after["runout_date"] < daily["payday_date"].isoformat()

    gathered = ResilienceEngine(pipeline).gather(user, env.clock())
    # điểm chống chịu: mỗi hũ tính một lần (Chi hằng ngày cộng số dư và chi lặt vặt của chính nó, không đếm lại chi của Ăn uống)
    demo_jars = _read_jars(env, user)
    assert gathered.inputs.liquid_balance_vnd == sum(j["balance_vnd"] for j in demo_jars)
    window, month_days = settings.resilience_window_days, settings.allocation.month_days
    per_jar = {j["code"]: variable_monthly_spend(j.get("spend") or [], window, month_days) for j in ctx.jars}
    assert per_jar[DEFAULT_SPENDING_JAR] > 0
    assert gathered.inputs.variable_spend_vnd == round(
        sum(per_jar[j["code"]] for j in demo_jars) * window / month_days
    )
    facts = facts_from_rows(
        today=gathered.app_date,
        user=env.repo.user_row(user),
        jars=gathered.jar_rows,
        obligations=gathered.obligations,
        window_days=30,
    )
    assert facts.emergency_fund_vnd() == 2_700_000  # quỹ dự phòng chỉ là hũ `buffer`, không cộng Chi hằng ngày
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
    assert {c: roles[c] for c in (
        DEFAULT_SPENDING_JAR, "an_uong", "di_lai", "giai_tri", "du_phong", "muc_tieu", "dau_tu",
    )} == {
        # Chi hằng ngày của ví demo không có chi loại thiết yếu: không thiết yếu, không sàn (không coi cả hũ chung là thiết yếu)
        DEFAULT_SPENDING_JAR: "discretionary",
        "an_uong": "essential",
        "di_lai": "essential",
        "giai_tri": "discretionary",
        "du_phong": "emergency",
        "muc_tieu": "goal",
        "dau_tu": "saving",
    }  # fmt: skip
    floors = {j.code: j.floor_vnd for j in allocation.problem.jars}
    assert floors[DEFAULT_SPENDING_JAR] == 0 and floors["an_uong"] > 0 and floors["di_lai"] > 0
    assert allocation.goals["muc_tieu"].target_date == date(2027, 4, 1)


def test_forecast_context_counts_only_essential_types_in_daily_jar(env):
    user = "six-essential"
    env.act(user, "update_profile", {"monthly_salary_vnd": 9_000_000, "payday_day": 5})
    env.act(user, "record_transaction", {"kind": "income", "amount_vnd": 9_000_000, "tx_type": "salary"})
    salary = env.svc.salary_events_response(user, status="pending")["salary_events"][0]
    env.act(user, "confirm_salary", {"salary_event_id": salary["id"], "decision": "split"})
    for tx_type, amount in (("food_drink", 45_000), ("public_transport", 12_000), ("entertainment", 74_000)):
        env.act(user, "record_transaction", {
            "kind": "expense", "tx_type": tx_type, "jar": "chi_hang_ngay", "amount_vnd": amount,
        })
    pipeline = Pipeline(ForecastRepo(env.db), make_settings(), None, clock=env.clock)
    ctx = pipeline.load_context(user, env.clock() + timedelta(days=1))
    daily = next(j for j in ctx.jars if j["code"] == "chi_hang_ngay")
    assert daily["spend"][-1] == 131_000
    assert daily["essential_spend"][-1] == 57_000


def _allocation(env, user):
    settings = make_settings(n_paths_full=500, scenario_n_paths=500)
    pipeline = Pipeline(ForecastRepo(env.db), settings, None, clock=env.clock)
    assert pipeline.run_user(user, trigger="reset").status == "ok"
    gathered = ResilienceEngine(pipeline).gather(user, env.clock())
    engine = AllocationEngine(pipeline)
    return pipeline, gathered, engine


def _build(engine, gathered, shock_id=None):
    return engine.build(
        gathered, horizon_months=3, goal_args=[], shock_id=shock_id, allow_relaxation=True
    )


def test_bill_floor_of_obligation_jar_on_demo_wallet_matches_legacy_bill_jar(env):
    """Hóa đơn của ví demo vào hũ Nghĩa vụ (gộp Hóa đơn và Nghĩa vụ của ví bảy hũ). Sàn của hũ này phải gồm phần chi hóa đơn trả lẻ
    theo loại giao dịch như sàn hũ Hóa đơn của ví cũ, nên lộ trình không hạ tỷ lệ Nghĩa vụ xuống dưới mức chi hóa đơn thật."""
    demo, legacy = "bill-floor-demo", "bill-floor-legacy"
    assert _reset(env, demo, "persona-minh")["statusCode"] == 200
    env.reset(legacy, "minh")
    _, g_demo, engine = _allocation(env, demo)
    _, g_legacy, engine_legacy = _allocation(env, legacy)

    # chuỗi chi thiết yếu của Nghĩa vụ = chi loại hóa đơn không gắn nghĩa vụ trong cửa sổ lịch sử (cùng nguồn với Chi hằng ngày)
    nv = next(j for j in g_demo.ctx.jars if j["code"] == "nghia_vu")
    first = date.fromisoformat(g_demo.ctx.meta["history_start"])
    with env.master() as c:
        (bills,) = c.execute(
            "SELECT coalesce(sum(-t.amount_vnd), 0) FROM transactions t JOIN tx_type_map m ON m.tx_type = t.tx_type "
            "WHERE t.user_id = %s AND t.jar_code = 'nghia_vu' AND t.kind = 'expense' AND t.obligation_id IS NULL "
            "AND t.funding_source IN ('jar', 'external') AND m.default_jar_code = 'hoa_don' "
            "AND t.app_date BETWEEN %s AND %s",
            [demo, first, g_demo.app_date - timedelta(days=1)],
        ).fetchone()
    assert bills > 0 and sum(nv["essential_spend"]) == bills

    for shock in (None, "tien_tro_tang"):
        d = {j.code: j for j in _build(engine, g_demo, shock).problem.jars}
        old = {j.code: j for j in _build(engine_legacy, g_legacy, shock).problem.jars}
        assert d["nghia_vu"].role == "obligation"
        assert d["nghia_vu"].floor_vnd == old["hoa_don"].floor_vnd + old["nghia_vu"].floor_vnd

    plan = engine.optimize(demo, {"horizon_months": 3})["data"]
    line = next(x for x in plan["lines"] if x["jar"]["code"] == "nghia_vu")
    floor = next(j for j in _build(engine, g_demo).problem.jars if j.code == "nghia_vu").floor_vnd
    print("Bill floor demo", line["split_percent_current"], line["split_percent_proposed"], floor, line["proposed_monthly_vnd"])
    assert line["floor_vnd"] == floor and line["proposed_monthly_vnd"] >= floor


def test_legacy_seven_jar_allocation_unchanged_by_obligation_bill_floor(env):
    """Ví bảy hũ cũ: hũ Nghĩa vụ không có chi loại thiết yếu nào ngoài nghĩa vụ đã khai, nên kết quả như khi chưa có chuỗi
    `essential_spend` cho hũ obligation (hành vi trước)."""
    user = "bill-floor-legacy-only"
    env.reset(user, "minh")
    _, gathered, engine = _allocation(env, user)
    nv = next(j for j in gathered.ctx.jars if j["code"] == "nghia_vu")
    assert set(nv["essential_spend"]) <= {0}
    before_ctx = replace(gathered.ctx, jars=tuple(
        {k: v for k, v in j.items() if k != "essential_spend"} if j["code"] != DEFAULT_SPENDING_JAR else j
        for j in gathered.ctx.jars
    ))
    for shock in (None, "tien_tro_tang", "om_mot_tuan"):
        now = _build(engine, gathered, shock).problem
        before = _build(engine, replace(gathered, ctx=before_ctx), shock).problem
        assert now == before


def test_long_term_jar_with_money_is_not_emergency_fund_anywhere(env):
    """Hũ Đầu tư (`long_term`) của ví demo có tiền: dữ kiện suitability, điểm chống chịu, cú sốc và LP phân bổ chỉ coi hũ `buffer`
    là quỹ dự phòng (đọc hũ kèm `purpose`), không cộng Đầu tư vào."""
    user = "long-term-funded"
    assert _reset(env, user, "persona-minh")["statusCode"] == 200
    env.act(user, "move_between_jars", {"from_jar": "giai_tri", "to_jar": "dau_tu", "amount_vnd": 300_000})
    jars = {j["code"]: j for j in _read_jars(env, user)}
    assert jars["dau_tu"]["balance_vnd"] == 300_000
    settings = make_settings(n_paths_full=500, scenario_n_paths=500)
    pipeline = Pipeline(ForecastRepo(env.db), settings, None, clock=env.clock)
    assert pipeline.run_user(user, trigger="reset").status == "ok"
    gathered = ResilienceEngine(pipeline).gather(user, env.clock())
    assert gathered.emergency_jar_code == "du_phong"
    view = env.repo.jar_view(user)
    facts = facts_from_rows(
        today=gathered.app_date, user=env.repo.user_row(user), jars=view.jars,
        obligations=gathered.obligations, window_days=30,
    )  # fmt: skip
    assert facts.emergency_fund_vnd() == jars["du_phong"]["balance_vnd"]
    assert StressEngine(pipeline).run(user, "om_mot_tuan")["data"]["emergency_jar"]["code"] == "du_phong"
    roles = {j.code: j.role for j in _build(AllocationEngine(pipeline), gathered).problem.jars}
    assert (roles["du_phong"], roles["dau_tu"]) == ("emergency", "saving")


def test_chi_hang_ngay_khac_mau_va_bieu_tuong_an_uong_tren_danh_muc_va_vi_demo(env):
    """Issue #39 (26/11): migration 0059 tạo hàng Chi hằng ngày với màu và biểu tượng của Ăn uống; seed chạy sau ghi đè hai cột đó, nên
    danh mục (tài khoản mới) và ví demo sau đặt lại cùng có màu, biểu tượng riêng cho Chi hằng ngày. Hũ đã tạo trước đó giữ màu cũ."""
    templates = {t["code"]: t for t in env.svc.jar_templates_response()["templates"]}
    theme = {code: (t["color_key"], t["icon_key"]) for code, t in templates.items()}
    assert theme[DEFAULT_SPENDING_JAR] != theme["an_uong"]
    assert theme[DEFAULT_SPENDING_JAR][1] not in {icon for code, (_, icon) in theme.items() if code != DEFAULT_SPENDING_JAR}
    assert templates[DEFAULT_SPENDING_JAR]["is_default"] and templates[DEFAULT_SPENDING_JAR]["default_split_percent"] == 42
    user = "six-daily-theme"
    assert _reset(env, user, "persona-minh")["statusCode"] == 200
    jars = {j["code"]: (j["color_key"], j["icon_key"]) for j in _read_jars(env, user)}
    assert jars[DEFAULT_SPENDING_JAR] == theme[DEFAULT_SPENDING_JAR] != jars["an_uong"]