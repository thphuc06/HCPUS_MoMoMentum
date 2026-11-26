"""Hợp đồng của tool `knowledge___resolve_date` (#39): đầu vào cho Gateway, kết quả, mã lỗi, fixture, Cedar.

Kết quả là `yofina_core.dates.ResolvedDate.to_wire()`; test kiểm JSON Schema và model Pydantic nói cùng một hình dạng, fixture đúng là
thứ hàm thuần trả, và hai mã lỗi mới khớp ba nơi (Python, OpenAPI, frontend)."""

from __future__ import annotations

import re
from datetime import date

import pytest
import yaml
from conftest import BASE, CONTRACTS, REPO, load_json
from jsonschema import Draft202012Validator

from yofina_core import dates as D
from yofina_core import wallet
from yofina_core.errors import HTTP_STATUS, ErrorCode

KNOWLEDGE = {t["name"]: t for t in load_json(CONTRACTS / "tools" / "knowledge.json")}
TOOL = KNOWLEDGE["resolve_date"]
RESULTS = load_json(CONTRACTS / "tools" / "knowledge.results.schema.json")["$defs"]
FIX = CONTRACTS / "fixtures" / "tools"
TODAY = date(2026, 11, 26)
NEW_ERRORS = {"DATE_IN_PAST": 422, "LUNAR_YEAR_UNSUPPORTED": 422}


def validator(registry, name: str) -> Draft202012Validator:
    return Draft202012Validator(
        {"$ref": f"{BASE}/tools/knowledge.results.schema.json#/$defs/{name}"}, registry=registry
    )


# --- đầu vào -------------------------------------------------------------------------------------------------
def test_tool_o_cuoi_target_knowledge_khop_hang_so():
    assert (
        list(KNOWLEDGE)
        == list(wallet.KNOWLEDGE_TOOLS)
        == ["get_fee_schedule", "get_exchange_rate", "resolve_date"]
    )
    assert len("knowledge___resolve_date") <= 64


def test_tham_so_tool_dung_la_truong_cua_dac_ta_khong_nhan_hom_nay():
    props = TOOL["inputSchema"]["properties"]
    assert list(props) == ["user_id", *D.SPEC_FIELDS]
    assert TOOL["inputSchema"]["required"] == ["anchor"]
    assert list(props["offset"]["properties"]) == list(D.OFFSET_UNITS)
    # hôm nay và ngày lương lấy phía server theo người gọi, model không điền
    assert not {"today", "app_date", "payday_day", "now"} & set(props)
    types = {
        "anchor": "string", "period": "string", "period_offset": "integer", "lunar_year": "integer", "day": "integer",
        "month": "integer", "year": "integer", "offset": "object", "before": "boolean",
    }  # fmt: skip
    assert {k: props[k]["type"] for k in D.SPEC_FIELDS} == types
    assert all(props["offset"]["properties"][u]["type"] == "number" for u in D.OFFSET_UNITS)


def test_mo_ta_neu_du_gia_tri_hop_le_vi_gateway_khong_co_enum():
    props = TOOL["inputSchema"]["properties"]
    for anchor in D.ANCHORS:
        assert anchor in props["anchor"]["description"], anchor
    for period in D.PERIODS:
        assert period in props["period"]["description"], period
    desc = TOOL["description"]
    assert (
        "Chỉ đọc, không ghi gì" in desc
        and "DATE_IN_PAST" in desc
        and "LUNAR_YEAR_UNSUPPORTED" in desc
    )
    assert (
        "30 ngày" in props["offset"]["description"] and "12 tháng" in props["offset"]["description"]
    )


def test_mo_ta_khong_liet_ke_cau_noi_cua_nguoi_dung():
    """Schema mô tả trường theo nghĩa: không có câu nói mẫu trong ngoặc kép (cách nói do model hiểu, không do bảng câu)."""
    text = str(TOOL)
    assert not re.search(r"[\"“”‘’]", text.replace("'", "")), "mô tả không chép câu nói mẫu"


# --- kết quả -------------------------------------------------------------------------------------------------
def test_enum_cua_schema_ket_qua_khop_model():
    data = RESULTS["ResolvedDateData"]
    assert tuple(data["properties"]["anchor"]["enum"]) == D.ANCHORS
    assert tuple(data["properties"]["period"]["enum"]) == D.PERIODS
    assert set(data["properties"]) == set(D.ResolvedDate.model_fields)
    required = {k for k, f in D.ResolvedDate.model_fields.items() if f.is_required()}
    assert set(data["required"]) == required
    assert set(RESULTS["LunarNewYear"]["properties"]) == set(D.LunarNewYear.model_fields)
    assert set(RESULTS["NormalizedDateOffset"]["properties"]) == set(
        D.NormalizedOffset.model_fields
    )


SPECS = [
    ({"anchor": "today"}, None),
    ({"anchor": "lunar_new_year", "before": True}, None),
    ({"anchor": "lunar_new_year", "lunar_year": 2030}, None),
    ({"anchor": "lunar_new_year", "period": "year", "period_offset": 2}, None),
    ({"anchor": "next_payday", "offset": {"months": 2}}, 5),
    (
        {"anchor": "start_of", "period": "quarter", "period_offset": 1, "offset": {"years": 1.5}},
        None,
    ),
    ({"anchor": "end_of", "period": "week", "period_offset": 1, "before": True}, None),
    ({"anchor": "date", "day": 31}, None),
    ({"anchor": "date", "day": 15, "month": 3}, None),
    ({"anchor": "date", "day": 31, "period": "month", "period_offset": 3}, None),
    ({"anchor": "today", "offset": {"months": -1.5, "years": 1}}, None),
]


@pytest.mark.parametrize(("spec", "payday"), SPECS, ids=lambda x: str(x))
def test_ket_qua_cua_ham_thuan_hop_le_voi_schema(registry, spec, payday):
    wire = D.resolve_date(spec, TODAY, payday_day=payday).to_wire()
    errors = [
        f"{list(e.path)}: {e.message}"
        for e in validator(registry, "ResolvedDateData").iter_errors(wire)
    ]
    assert errors == []
    ok = {
        "status": "OK",
        "as_of": "2026-12-15T03:00:00Z",
        "app_date": TODAY.isoformat(),
        "data": wire,
    }
    assert validator(registry, "ResolveDateResult").is_valid(ok)
    assert D.ResolvedDate.model_validate(wire) == D.resolve_date(spec, TODAY, payday_day=payday)


def test_schema_tu_choi_ket_qua_sai(registry):
    good = load_json(FIX / "resolve_date.ok.json")
    v = validator(registry, "ResolveDateResult")
    assert v.is_valid(good)
    for bad in (
        {**good["data"], "weekday": 0},
        {**good["data"], "anchor": "tomorrow"},
        {**good["data"], "next_occurrence": False},  # chỉ có khi đúng
        {**good["data"], "today_text": "x"},
        {k: val for k, val in good["data"].items() if k != "anchor_date"},
        {**good["data"], "lunar_new_year": {"year": 2027, "date": "2027-02-06"}},
    ):
        assert not v.is_valid({**good, "data": bad}), bad


#: fixture -> (đặc tả, ngày lương) mà hàm thuần dùng để ra đúng fixture đó
FIXTURE_SPECS = {
    "resolve_date.ok.json": ({"anchor": "lunar_new_year", "before": True}, None),
    "resolve_date.ok_quarter.json": (
        {"anchor": "start_of", "period": "quarter", "period_offset": 1, "offset": {"years": 1.5}},
        None,
    ),
    "resolve_date.ok_payday.json": ({"anchor": "next_payday", "offset": {"months": 2}}, 5),
    "resolve_date.error_in_past.json": (
        {"anchor": "lunar_new_year", "lunar_year": 2026, "before": True},
        None,
    ),
    "resolve_date.error_lunar_year.json": ({"anchor": "lunar_new_year", "lunar_year": 2036}, None),
}


def test_moi_fixture_cua_tool_co_dac_ta():
    assert {p.name for p in FIX.glob("resolve_date.*.json")} == set(FIXTURE_SPECS)


@pytest.mark.parametrize("name", sorted(FIXTURE_SPECS))
def test_fixture_dung_la_ket_qua_cua_ham_thuan(registry, name):
    obj = load_json(FIX / name)
    assert validator(registry, "ResolveDateResult").is_valid(obj)
    spec, payday = FIXTURE_SPECS[name]
    if obj["status"] == "OK":
        assert obj["app_date"] == obj["data"]["today"] == TODAY.isoformat()
        assert D.resolve_date(spec, TODAY, payday_day=payday).to_wire() == obj["data"]
        return
    with pytest.raises(D.DateResolveError) as e:
        D.resolve_date(spec, TODAY, payday_day=payday)
    assert e.value.tool_result() == obj


# --- mã lỗi mới khớp ba nơi ------------------------------------------------------------------------------------
def test_ma_loi_moi_khop_python_openapi_frontend_va_them_cuoi():
    schema = yaml.safe_load((CONTRACTS / "rest" / "openapi.yaml").read_text(encoding="utf-8"))[
        "components"
    ]["schemas"]["ErrorCode"]
    names = [c.value for c in ErrorCode]
    assert names[-len(NEW_ERRORS) :] == list(NEW_ERRORS) == schema["enum"][-len(NEW_ERRORS) :]
    assert (
        names.index("DATE_IN_PAST") == names.index("DAILY_QUOTA_EXCEEDED") + 1
    )  # thêm sau mã cũ, không đổi thứ tự
    front = (REPO / "frontend/src/api/errors.ts").read_text(encoding="utf-8")
    for code, status in NEW_ERRORS.items():
        assert HTTP_STATUS[ErrorCode(code)] == status == schema["x-http-status"][code]
        assert schema["x-meaning"][code]
        assert f"'{code}'," in front and f"{code}: {status}," in front and f"{code}: '" in front
        assert code in RESULTS["ResolveDateResult"]["description"]


# --- Cedar ---------------------------------------------------------------------------------------------------
def test_cedar_cua_resolve_date_chi_ep_user_id():
    text = (REPO / "gateway" / "policies" / "resolve_date.cedar").read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))
    assert 'action == AgentCore::Action::"knowledge___resolve_date"' in code
    assert 'resource == AgentCore::Gateway::"${GATEWAY_ARN}"' in code
    assert "context.input has user_id && context.input.user_id == principal.id" in code
    assert "confirm_token" not in code and not re.search(r"\b[0-9]{4,}\b", code)
    assert code.count("permit(") == 1 and "forbid" not in code
    exchange = (REPO / "gateway" / "policies" / "get_exchange_rate.cedar").read_text(
        encoding="utf-8"
    )
    strip = lambda t: "\n".join(x for x in t.splitlines() if not x.lstrip().startswith("//"))  # noqa: E731
    assert strip(text).replace("resolve_date", "X") == strip(exchange).replace(
        "get_exchange_rate", "X"
    )
