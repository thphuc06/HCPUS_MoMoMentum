"""scripts/seed_persona.py: chạy thử không gọi AWS, kế hoạch khớp bộ sinh, đường `--apply` nối đúng mã đặt lại của ledger (bằng đối tượng giả)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from conftest import REPO
from persona_coverage import AFTER_RANGE, BEFORE_RANGE

ANCHOR = date(2026, 11, 21)
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = datetime(2026, 12, 10, 3, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def sp():
    scripts = str(REPO / "scripts")
    sys.path.insert(0, scripts)  # seed_persona nạp _yofina, create_demo_users, seed_demo theo tên
    try:
        spec = importlib.util.spec_from_file_location(
            "seed_persona", REPO / "scripts" / "seed_persona.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.path.remove(scripts)


def test_ke_hoach_vy_co_dong_external_so_du_hu_khop_va_do_phu_trong_dai(sp):
    p = sp.plan("vy", anchor=ANCHOR, now=NOW, tz=TZ, user_id="u1")
    assert p["counts"][("income", "external")] == 2
    assert BEFORE_RANGE[0] <= p["coverage"] <= BEFORE_RANGE[1]
    mat = p["materialized"]
    ext = [r for r in mat.transaction_rows if r["funding_source"] == "external"]
    assert all(r["jar_code"] is None and r["kind"] == "income" for r in ext)
    # số dư mỗi hũ dựng từ dòng trả bằng hũ, không có dòng external nào trong đó
    assert {c: v for c, v in p["balances"].items() if c != "tien_vao_khac"} == {
        j["code"]: sum(
            r["amount"]
            for r in mat.transaction_rows
            if r["jar_code"] == j["code"] and r["funding_source"] == "jar"
        )
        for j in mat.jars
    }
    assert p["balances"]["tien_vao_khac"] == 0  # hũ hệ thống: lương vào rồi chia hết
    assert AFTER_RANGE[0] > p["coverage"]  # chưa nạp tệp thì dưới dải "sau"


def test_ke_hoach_minh_khong_co_dong_external_va_phu_tron(sp):
    p = sp.plan("minh", anchor=ANCHOR, now=NOW, tz=TZ)
    assert not [k for k in p["counts"] if k[1] == "external"]
    assert p["coverage"] == 1.0


def test_chay_thu_la_mac_dinh_khong_goi_apply(sp, monkeypatch, capsys):
    called = []
    monkeypatch.setattr(sp, "apply", lambda *a, **k: called.append(a) or 0)
    for argv in (["giamkhao3"], ["giamkhao3", "--dry-run"], ["giamkhao3", "--dry-run", "--apply"]):
        monkeypatch.setattr(sys, "argv", ["seed_persona.py", *argv])
        assert sp.main() == 0
    assert called == []
    assert "CHẠY THỬ" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["seed_persona.py", "giamkhao3", "--apply"])
    assert sp.main() == 0 and len(called) == 1
    assert called[0][1:3] == ("giamkhao3", "vy")  # apply(args, tài khoản, persona, tiền tố nhóm)


def test_tai_khoan_la_persona_la_bi_tu_choi(sp, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["seed_persona.py", "khong_co"])
    with pytest.raises(SystemExit):
        sp.main()
    monkeypatch.setattr(sys, "argv", ["seed_persona.py", "giamkhao3", "--persona", "khong_co"])
    with pytest.raises(SystemExit):
        sp.main()


def test_apply_noi_dung_mach_dat_lai_cua_ledger_voi_sub_cua_tai_khoan(sp, monkeypatch):
    """Không gọi AWS: thay boto3, Data API và LedgerService bằng đối tượng giả, kiểm dây nối (tài khoản -> sub -> reset_demo)."""
    import _yofina
    import seed_demo

    import yofina_core.db as core_db
    import yofina_ledger.events as events_mod
    import yofina_ledger.service as service_mod

    env = {
        "YOFINA_CONFIRM_OFFER_TTL_SECONDS": "600", "YOFINA_MOVE_MAX_AMOUNT_VND": "50000000",
        "YOFINA_TRANSACTIONS_DEFAULT_LIMIT": "20", "YOFINA_TRANSACTIONS_MAX_LIMIT": "50",
        "YOFINA_APP_TIMEZONE": "Asia/Ho_Chi_Minh", "YOFINA_DEMO_ANCHOR_DATE": "2026-11-21",
        "YOFINA_TRANSACTION_MAX_AMOUNT_VND": "50000000", "YOFINA_SALARY_DEVIATION_ASK_PERCENT": "10",
        "YOFINA_DEFAULT_CREDIT_LIMIT_VND": "3000000", "YOFINA_DEFAULT_DISPLAY_NAME": "Bạn",
        "YOFINA_FORECAST_FRESHNESS_SECONDS": "900", "YOFINA_PROACTIVE_OBLIGATION_DAYS": "3",
        "YOFINA_REFERENCE_CACHE_SECONDS": "300", "YOFINA_EVENT_BUS_NAME": "bus",
        "YOFINA_FORECAST_FUNCTION_NAME": "fc", "YOFINA_SUITABILITY_WINDOW_DAYS": "30",
    }  # fmt: skip

    class FakeClient:
        def __init__(self, name):
            self.name = name

        def admin_get_user(self, **kw):
            assert kw["Username"].startswith("giamkhao3@")
            return {"UserAttributes": [{"Name": "sub", "Value": "sub-giamkhao3"}]}

        def get_function_configuration(self, **kw):
            assert kw["FunctionName"] == "yofina-ledger"
            return {"Environment": {"Variables": env}}

    class FakeSession:
        def client(self, name):
            return FakeClient(name)

    seen: dict = {}

    class FakeDb:
        def __init__(self, settings, region=None):
            seen["db_settings"] = settings

        def query(self, sql, params=None, max_rows=None):
            seen.setdefault("queries", []).append((sql, params))
            return []

    class FakeService:
        def __init__(self, repo, confirm, settings, *, events=None, forecast=None):
            seen["settings"], seen["forecast"], seen["events"] = settings, forecast, events

        def reset_demo(self, user_id, persona, *, trace_id):
            seen["reset"] = (user_id, persona, trace_id)
            return {"app_date": "2026-11-21", "transactions_count": 147}

    monkeypatch.setattr(_yofina, "session", lambda: FakeSession())
    monkeypatch.setattr(_yofina, "ssm_param", lambda name, sess=None: f"ssm:{name}")
    monkeypatch.setattr(seed_demo, "ensure_groups", lambda *a: seen.setdefault("groups", a[1:]))
    monkeypatch.setattr(core_db, "DataApi", FakeDb)
    monkeypatch.setattr(service_mod, "LedgerService", FakeService)
    monkeypatch.setattr(events_mod, "EventPublisher", lambda bus, region=None: ("pub", bus))
    monkeypatch.setattr(sys, "argv", ["seed_persona.py", "giamkhao3", "--apply", "--forecast"])
    assert sp.main() == 0
    assert seen["reset"][:2] == ("sub-giamkhao3", "vy")
    assert seen["groups"] == (
        {"giamkhao3": "vy"},
        "persona-",
        {"giamkhao3": {"email": "giamkhao3@demo.yofina.example"}},
    )
    assert seen["settings"].demo_anchor_date == ANCHOR and seen["forecast"] is not None
    assert (
        seen["db_settings"].secret_arn == "ssm:db/app-secret-arn"
    )  # role yofina_app, không phải secret master
    assert seen["events"] == ("pub", "bus")
    assert "app_get_data_coverage" in seen["queries"][0][0]
