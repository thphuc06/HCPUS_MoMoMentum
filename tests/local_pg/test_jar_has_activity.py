"""Hũ 0 ₫ chưa từng có tiền và hũ đã tiêu hết (issue #39, lỗi 4c) trên PostgreSQL cục bộ, Ledger thật: `JarFull.has_activity` cho biết
hũ người dùng có số dư ≤ 0 đã từng có dòng sổ cái nào chưa, để chip trạng thái không nói "đang hết tiền" về hũ chưa từng có tiền vào.

Quyết theo dữ liệu (số dòng sổ cái của hũ, `app_get_jar_usage`; ở Chi tiết hũ là các giao dịch gần đây của chính hũ), không theo mã hũ:
cùng hũ Chi hằng ngày là "chưa có tiền" trên tài khoản mới và là "đã tiêu hết" sau khi có tiền vào rồi chi hết.
"""

from __future__ import annotations

import importlib.util

import pytest
from conftest import REPO
from ledger_fakes import http_event

from yofina_ledger.rest_api import handle_http

MINH = "sub-minh"
NEW = "sub-moi-has-activity"


def _unit_conftest():
    spec = importlib.util.spec_from_file_location("unit_conftest", REPO / "tests/unit/conftest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def schema():
    from jsonschema import Draft202012Validator

    uc = _unit_conftest()
    reg = uc.build_registry()

    def check(ref: str, instance):
        v = Draft202012Validator({"$ref": f"{uc.BASE}/{ref}"}, registry=reg)
        errors = [f"{list(e.path)}: {e.message}" for e in v.iter_errors(instance)]
        assert not errors, errors

    return check


def _ledger_rows(env, user):
    """Số dòng sổ cái của từng hũ, đọc thẳng bằng master (không qua mã đang kiểm)."""
    with env.master() as m:
        return dict(
            m.execute(
                "SELECT jar_code, count(*) FROM transactions WHERE user_id = %s GROUP BY jar_code", [user]
            ).fetchall()
        )


def test_tai_khoan_moi_moi_hu_0d_chua_tung_co_tien(env, schema):
    env.act(NEW, "update_profile", {"monthly_salary_vnd": 9_000_000, "payday_day": 5})
    ov = env.svc.overview_response(NEW)
    schema("rest/openapi.yaml#/components/schemas/OverviewResponse", ov)
    assert ov["jars"] and all(j["balance_vnd"] == 0 for j in ov["jars"])
    assert not _ledger_rows(env, NEW)
    for j in ov["jars"]:
        assert j["has_activity"] is False, j
    for j in ov["system_jars"]:  # hũ hệ thống không mang chip trạng thái
        assert "has_activity" not in j, j
    code = ov["jars"][0]["code"]
    d = env.svc.jar_detail_response(NEW, code)
    schema("rest/openapi.yaml#/components/schemas/JarDetailResponse", d)
    assert d["jar"]["has_activity"] is False and d["recent_transactions"] == []


def test_hu_da_tieu_het_khac_hu_chua_tung_co_tien(env, schema):
    # ví demo 8 hũ (đặt lại như trên app, nhóm persona-minh): có hũ Đầu tư 0 ₫ chưa từng có dòng nào
    r = handle_http(http_event("POST", "/demo/reset", sub=MINH, groups="persona-minh"), env.svc)
    assert r["statusCode"] == 200, r
    before = {j["code"]: j for j in env.svc.overview_response(MINH)["jars"]}
    spend = next(c for c, j in before.items() if j["kind"] == "spending" and j["balance_vnd"] > 0)
    env.act(
        MINH, "record_transaction", {"kind": "expense", "amount_vnd": before[spend]["balance_vnd"], "jar": spend}
    )
    ov = env.svc.overview_response(MINH)
    schema("rest/openapi.yaml#/components/schemas/OverviewResponse", ov)
    rows = _ledger_rows(env, MINH)
    jars = {j["code"]: j for j in ov["jars"]}
    assert jars[spend]["balance_vnd"] == 0 and jars[spend]["has_activity"] is True
    never = [c for c, j in jars.items() if j["balance_vnd"] <= 0 and not rows.get(c)]
    assert never, "ví demo phải có một hũ 0 ₫ chưa từng có dòng sổ cái (Đầu tư)"
    for c in never:
        assert jars[c]["has_activity"] is False, jars[c]
    for c, j in jars.items():
        if j["balance_vnd"] > 0:  # hũ còn tiền: không cần trường này
            assert "has_activity" not in j, j
    d = env.svc.jar_detail_response(MINH, spend)
    schema("rest/openapi.yaml#/components/schemas/JarDetailResponse", d)
    assert d["jar"]["has_activity"] is True
    d = env.svc.jar_detail_response(MINH, never[0])
    assert d["jar"]["has_activity"] is False
    assert "has_activity" not in env.svc.jar_detail_response(MINH, "chua_phan_loai")["jar"]
