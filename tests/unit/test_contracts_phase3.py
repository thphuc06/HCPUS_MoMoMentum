"""Hợp đồng phase 3 (what-if, kiểm tra trước khi quẹt, harness): ScenarioSpec, khối mới, tool mới, REST mới, luật suitability.

Phần schema và fixture dùng chung của các khối nằm ở test_contracts_blocks.py (mọi khối trong BLOCK_TYPES, kể cả sáu khối
mới); tool ở test_contracts_tools.py; REST ở test_contracts_rest.py. File này kiểm thứ chỉ phase 3 có: hình dạng ScenarioSpec,
bất biến liên trường mà JSON Schema không diễn đạt được, nhất quán số trong fixture, khớp giữa các nơi nói cùng một tập giá trị."""

from __future__ import annotations

import copy
import json
from datetime import UTC, date, datetime

import pytest
import yaml
from conftest import BASE, CONTRACTS, REPO, fixture_files, load_json
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from test_contracts_blocks import normalize, pydantic_tree

from yofina_core import blocks as b
from yofina_core import scenario, suitability, wallet
from yofina_core.confirm import hash_normalized_params
from yofina_core.errors import HTTP_STATUS, ErrorCode

SPEC = yaml.safe_load((CONTRACTS / "rest" / "openapi.yaml").read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]
SCENARIO_SCHEMA = load_json(CONTRACTS / "scenario" / "scenario_spec.schema.json")
PLANNER = {t["name"]: t for t in load_json(CONTRACTS / "tools" / "planner.json")}
FORECAST = {t["name"]: t for t in load_json(CONTRACTS / "tools" / "forecast.json")}
KW = dict(
    trace_id="8f3a21c94b7e4d0aa1c25e6f7b8c9d01",
    source_tool="agent",
    as_of=datetime(2026, 12, 10, 3, 0, tzinfo=UTC),
    app_date=date(2026, 11, 21),
)


def scenario_files(sub):
    files = sorted((CONTRACTS / "fixtures" / "scenario" / sub).glob("*.json"))
    assert files
    return files


def scenario_validator(registry):
    return Draft202012Validator(
        {"$ref": f"{BASE}/scenario/scenario_spec.schema.json"}, registry=registry
    )


# =====================================================================================
# ScenarioSpec
# =====================================================================================
def test_scenario_co_dung_sau_loai_theo_fr5():
    refs = [m["$ref"].split("/")[-1] for m in SCENARIO_SCHEMA["oneOf"]]
    assert len(refs) == 6
    kinds = [SCENARIO_SCHEMA["$defs"][r]["properties"]["kind"]["const"] for r in refs]
    assert tuple(kinds) == wallet.SCENARIO_KINDS == tuple(scenario.SCENARIO_MODELS)
    assert tuple(SCENARIO_SCHEMA["$defs"]["ScenarioKind"]["enum"]) == wallet.SCENARIO_KINDS


@pytest.mark.parametrize("kind", wallet.SCENARIO_KINDS)
def test_model_pydantic_cua_tung_loai_khop_hinh_dang_json_schema(registry, kind):
    ref = {m["$ref"].split("/")[-1] for m in SCENARIO_SCHEMA["oneOf"]}
    name = next(
        r for r in ref if SCENARIO_SCHEMA["$defs"][r]["properties"]["kind"]["const"] == kind
    )
    resolver = registry.resolver(base_uri=f"{BASE}/scenario/")
    hit = resolver.lookup(f"scenario_spec.schema.json#/$defs/{name}")
    assert pydantic_tree(scenario.SCENARIO_MODELS[kind]) == normalize(hit.contents, hit.resolver)


@pytest.mark.parametrize("path", scenario_files("valid"), ids=lambda p: p.name)
def test_scenario_hop_le_qua_schema_va_pydantic_khu_hoi_khong_doi(registry, path):
    obj = load_json(path)
    assert path.name.split(".")[0] == obj["kind"]
    assert list(scenario_validator(registry).iter_errors(obj)) == []
    parsed = scenario.parse_scenario(obj)
    assert isinstance(parsed, scenario.SCENARIO_MODELS[obj["kind"]])
    assert scenario.scenario_to_wire(parsed) == obj


@pytest.mark.parametrize("path", scenario_files("invalid"), ids=lambda p: p.name)
def test_scenario_sai_bi_ca_json_schema_lan_pydantic_tu_choi(registry, path):
    obj = load_json(path)
    assert not scenario_validator(registry).is_valid(obj)
    with pytest.raises(ValidationError):
        scenario.parse_scenario(obj)


@pytest.mark.parametrize("path", scenario_files("python_only_invalid"), ids=lambda p: p.name)
def test_luat_lien_truong_chi_pydantic_kiem_json_schema_khong_dien_dat_duoc(registry, path):
    """Hai luật liên trường (cùng hũ, end_date trước date) và ngày lịch thật: JSON Schema (tập con của repo) chấp nhận,
    Pydantic từ chối. Hợp đồng ghi rõ Pydantic là nơi quyết định."""
    obj = load_json(path)
    assert scenario_validator(registry).is_valid(obj)
    with pytest.raises(ValidationError):
        scenario.parse_scenario(obj)
    assert "Pydantic" in SCENARIO_SCHEMA["description"]


def test_scenario_hash_khong_phu_thuoc_thu_tu_khoa_hay_null():
    a = scenario.scenario_hash(
        {"kind": "bnpl_purchase", "amount_vnd": 1200000, "funding_source": "credit", "label": "x"}
    )
    b_ = scenario.scenario_hash(
        {"label": "x", "funding_source": "credit", "amount_vnd": 1200000, "kind": "bnpl_purchase"}
    )
    c = scenario.scenario_hash(
        scenario.parse_scenario(
            {"kind": "bnpl_purchase", "amount_vnd": 1200000, "funding_source": "credit"}
        )
    )
    assert a == b_ and len(a) == 64 and a != c


def test_moi_loai_co_nguon_tra_dung_voi_fr5():
    one = scenario.parse_scenario(
        load_json(CONTRACTS / "fixtures/scenario/valid/one_time_purchase.tai_nghe.json")
    )
    bnpl = scenario.parse_scenario(
        load_json(CONTRACTS / "fixtures/scenario/valid/bnpl_purchase.minh.json")
    )
    assert one.funding_source == "jar" and one.jar_code  # mua một lần: tiền hũ, bắt buộc có hũ
    assert bnpl.funding_source == "credit"  # mua trả sau: hạn mức


def test_scenario_khong_chua_tien_dang_chuoi_hay_so_thuc():
    # test_contracts_phase2 kiểm mọi *_vnd là số nguyên cho cả scenario/; ở đây thử thật bằng Pydantic
    for bad in (1.5, "100", True):
        with pytest.raises(ValidationError):
            scenario.parse_scenario(
                {"kind": "jar_transfer", "amount_vnd": bad, "from_jar": "a", "to_jar": "b"}
            )


# =====================================================================================
# Tool: tham số khớp ScenarioSpec, khớp hằng số
# =====================================================================================
def spec_property_names() -> set[str]:
    names: set[str] = set()
    for model in scenario.SCENARIO_MODELS.values():
        names |= set(model.model_fields)
    return names


def test_run_scenario_nhan_dung_cac_truong_cua_scenario_spec():
    props = FORECAST["run_scenario"]["inputSchema"]["properties"]["scenario"]
    assert set(props["properties"]) == spec_property_names()
    assert props["required"] == ["kind"]
    assert FORECAST["run_scenario"]["inputSchema"]["required"] == ["scenario"]
    kind_desc = props["properties"]["kind"]["description"]
    for k in wallet.SCENARIO_KINDS:
        assert k in kind_desc
    assert "Không bịa" in props["properties"]["amount_vnd"]["description"]


def test_run_scenario_nhan_with_scenarios_cung_dang_voi_scenario_va_conversation_id():
    props = FORECAST["run_scenario"]["inputSchema"]["properties"]
    assert set(props) == {"user_id", "scenario", "conversation_id", "with_scenarios"}
    assert FORECAST["run_scenario"]["inputSchema"]["required"] == ["scenario"]  # hai trường mới tùy chọn
    assert props["conversation_id"]["type"] == "string"
    ws = props["with_scenarios"]
    assert ws["type"] == "array" and ws["items"]["type"] == "object"
    assert set(ws["items"]["properties"]) == set(props["scenario"]["properties"]) == spec_property_names()
    assert ws["items"]["required"] == ["kind"]
    for kind in ("one_time_purchase", "recurring_expense", "bnpl_purchase"):
        assert kind in ws["description"]
    assert "Tối đa 4" in ws["description"] and "MỘT bnpl_purchase" in ws["description"]
    desc = FORECAST["run_scenario"]["description"]
    assert "with_scenarios" in desc and "list_scenarios" in desc and "bundle_total_vnd" in desc


def test_list_scenarios_la_tool_doc_can_conversation_id():
    tool = FORECAST["list_scenarios"]
    props = tool["inputSchema"]["properties"]
    assert set(props) == {"user_id", "conversation_id", "limit"}
    assert tool["inputSchema"]["required"] == ["conversation_id"]
    assert props["conversation_id"]["type"] == "string" and props["limit"]["type"] == "integer"
    assert "1 đến 10" in props["limit"]["description"] and "5" in props["limit"]["description"]
    assert "không cần xác nhận" in tool["description"] and "confirm_token" not in props


def test_gop_kich_ban_khop_hang_so_cua_engine_va_co_cedar():
    from yofina_forecast import scenario as engine

    assert set(engine.BUNDLE_PRIOR_KINDS) <= set(wallet.SCENARIO_KINDS)
    assert set(engine.BUNDLE_TOTAL_KINDS) <= set(engine.BUNDLE_PRIOR_KINDS)
    assert set(engine.KIND_VN) == set(wallet.SCENARIO_KINDS)
    assert engine.MAX_PRIOR_SCENARIOS == 4 and engine.LIST_LIMIT_DEFAULT == 5 and engine.LIST_LIMIT_MAX == 10
    ws = FORECAST["run_scenario"]["inputSchema"]["properties"]["with_scenarios"]["description"]
    assert f"Tối đa {engine.MAX_PRIOR_SCENARIOS}" in ws
    cedar = (CONTRACTS.parent / "gateway" / "policies" / "list_scenarios.cedar").read_text(encoding="utf-8")
    assert 'action == AgentCore::Action::"forecast___list_scenarios"' in cedar
    assert "context.input has user_id && context.input.user_id == principal.id" in cedar


def test_run_scenario_va_affordability_la_tool_doc_khong_xac_nhan():
    for name in ("run_scenario", "list_scenarios", "affordability_check"):
        props = FORECAST[name]["inputSchema"]["properties"]
        assert "confirm_token" not in props
        assert (
            "KHÔNG cần xác nhận" in FORECAST[name]["description"]
            or "không cần xác nhận" in FORECAST[name]["description"]
        )
    assert FORECAST["affordability_check"]["inputSchema"]["required"] == ["amount_vnd"]
    assert (
        FORECAST["affordability_check"]["inputSchema"]["properties"]["amount_vnd"]["type"]
        == "integer"
    )


def test_schedule_nudge_la_tool_ghi_di_qua_token():
    tool = PLANNER["schedule_nudge"]
    props = tool["inputSchema"]["properties"]
    assert props["confirm_token"]["type"] == "string"
    assert "confirm_token" not in tool["inputSchema"].get(
        "required", []
    )  # thiếu token -> NEEDS_CONFIRMATION
    assert "KHÔNG ghi gì" in tool["description"] and "bịa" in tool["description"]
    assert "TUYỆT ĐỐI không tự tạo" in props["confirm_token"]["description"]
    for k in wallet.NUDGE_KINDS:
        assert k in props["kind"]["description"]
    for op in wallet.NUDGE_OPS:
        assert op in props["op"]["description"]
    assert set(props) == {
        "user_id", "op", "kind", "fire_on", "jar_code", "note", "scenario_id", "nudge_id", "confirm_token",
    }  # fmt: skip
    # schedule_nudge là tool ghi thứ năm của agent nhưng nằm ở target planner
    assert wallet.PLANNER_WRITE_TOOLS == ("schedule_nudge",)
    assert (
        "schedule_nudge" in wallet.ACTION_TOOLS and "schedule_nudge" not in wallet.AGENT_WRITE_TOOLS
    )


def test_check_suitability_nhan_de_xuat_khop_model_proposal():
    prop = PLANNER["check_suitability"]["inputSchema"]["properties"]["proposal"]
    assert set(prop["properties"]) == set(suitability.Proposal.model_fields)
    assert prop["required"] == ["kind"]
    assert PLANNER["check_suitability"]["inputSchema"]["required"] == ["proposal"]
    assert "confirm_token" not in PLANNER["check_suitability"]["inputSchema"]["properties"]


def test_get_fee_schedule_khong_di_qua_rag_va_khop_feeline_cua_openapi():
    results = load_json(CONTRACTS / "tools" / "knowledge.results.schema.json")["$defs"]
    assert set(results["FeeLine"]["properties"]) == set(SCHEMAS["FeeLine"]["properties"])
    assert results["FeeLine"]["required"] == SCHEMAS["FeeLine"]["required"]
    desc = load_json(CONTRACTS / "tools" / "knowledge.json")[0]["description"]
    assert "CÓ CẤU TRÚC" in desc and "nguồn" in desc


def test_get_trace_chi_cua_chinh_nguoi_dung():
    tool = load_json(CONTRACTS / "tools" / "audit.json")[0]
    assert tool["inputSchema"]["required"] == ["trace_id"]
    assert "TRACE_NOT_FOUND" in tool["description"]
    fx = load_json(CONTRACTS / "fixtures/tools/get_trace.error_not_found.json")
    assert fx["code"] == "TRACE_NOT_FOUND"


# =====================================================================================
# Mã lỗi mới
# =====================================================================================
def test_ma_loi_phase_3_co_trong_openapi_voi_dung_http_status():
    schema = SCHEMAS["ErrorCode"]
    expected = {
        "OFFER_EXPIRED": 410, "TRACE_NOT_FOUND": 404, "NUDGE_NOT_FOUND": 404,
        "FEE_SCHEDULE_NOT_FOUND": 404, "FORECAST_NOT_APPLICABLE": 404, "SCENARIO_INVALID": 422,
    }  # fmt: skip
    for code, status in expected.items():
        assert code in schema["enum"] and schema["x-http-status"][code] == status
        assert HTTP_STATUS[ErrorCode(code)] == status
    # thêm SAU mã cũ, không đổi thứ tự mã cũ; sáu mã phase 3 liền nhau (phase 5 thêm mã ingest ngay sau chúng)
    enum = schema["enum"]
    start = enum.index("OFFER_EXPIRED")
    assert enum[start : start + 6] == list(expected)
    assert enum[start - 1] == "FORECAST_UNAVAILABLE"


def test_offer_expired_tach_khoi_token_expired_trong_mo_ta_va_phan_hoi_410():
    schema = SCHEMAS["ErrorCode"]
    assert "quá 2 phút" in schema["x-meaning"]["TOKEN_EXPIRED"]
    assert "TOKEN_EXPIRED" in schema["x-meaning"]["OFFER_EXPIRED"]  # nói rõ khác nhau
    for path, method in (("/confirmations", "post"), ("/actions", "post")):
        assert "410" in SPEC["paths"][path][method]["responses"], path
    assert "OFFER_EXPIRED" in SPEC["paths"]["/confirmations"]["post"]["description"]


def test_hu_he_thong_khong_co_du_bao_la_404_khong_phai_503():
    desc = SPEC["paths"]["/forecasts/{jar_code}"]["get"]["description"]
    assert "FORECAST_NOT_APPLICABLE" in desc and "404" in desc
    assert HTTP_STATUS[ErrorCode.FORECAST_NOT_APPLICABLE] == 404
    assert HTTP_STATUS[ErrorCode.FORECAST_UNAVAILABLE] == 503  # 503 chỉ còn là lỗi tạm thời


# =====================================================================================
# REST mới
# =====================================================================================
def test_post_affordability_la_doc_tat_dinh_tra_dung_khoi_affordability_card(registry):
    op = SPEC["paths"]["/affordability"]["post"]
    assert op["x-lambda"] == "forecast"
    assert "KHÔNG qua LLM" in op["description"]
    assert SCHEMAS["AffordabilityResponse"]["$ref"] == "../blocks/affordability_card.schema.json"
    props = SCHEMAS["AffordabilityRequest"]["properties"]
    assert (
        "user_id" not in props and SCHEMAS["AffordabilityRequest"]["additionalProperties"] is False
    )
    # cùng khối với tool trong chat
    tool = load_json(CONTRACTS / "fixtures/tools/affordability_check.ok.json")["data"]
    rest = load_json(CONTRACTS / "fixtures/rest/AffordabilityResponse.transfer.json")["data"]
    assert tool == rest


def test_get_traces_va_feedback_khong_di_qua_token_xac_nhan():
    assert SPEC["paths"]["/traces/{trace_id}"]["get"]["x-lambda"] == "ledger"
    assert "404" in SPEC["paths"]["/traces/{trace_id}"]["get"]["responses"]
    assert "TRACE_NOT_FOUND" in SPEC["paths"]["/traces/{trace_id}"]["get"]["description"]
    fb = SPEC["paths"]["/feedback"]["post"]
    assert fb["x-lambda"] == "ledger" and "KHÔNG đi qua token" in fb["description"]
    assert (
        tuple(SCHEMAS["FeedbackRequest"]["properties"]["decision"]["enum"])
        == wallet.FEEDBACK_DECISIONS
    )


def test_schedule_nudge_qua_confirmations_actions_khong_co_endpoint_rieng(registry):
    assert "schedule_nudge" in SCHEMAS["ToolName"]["enum"]
    params = SCHEMAS["ScheduleNudgeParams"]
    assert tuple(params["properties"]["kind"]["enum"]) == wallet.NUDGE_KINDS
    assert tuple(params["properties"]["op"]["enum"]) == wallet.NUDGE_OPS
    v = Draft202012Validator(
        {"$ref": f"{BASE}/rest/openapi.yaml#/components/schemas/ScheduleNudgeParams"},
        registry=registry,
    )
    create = {"kind": "purchase_review", "fire_on": "2026-11-26"}
    assert v.is_valid(create) and v.is_valid({"op": "create", **create})
    assert not v.is_valid({"op": "create", "kind": "purchase_review"})  # thiếu fire_on
    assert not v.is_valid(
        {"op": "create", **create, "nudge_id": "7d2e5c4a-6b1f-4e93-a0d8-3f9b1c2e7a45"}
    )
    cancel = {"op": "cancel", "nudge_id": "7d2e5c4a-6b1f-4e93-a0d8-3f9b1c2e7a45"}
    assert v.is_valid(cancel)
    assert not v.is_valid({"op": "cancel"})  # thiếu nudge_id
    assert not v.is_valid({**cancel, "fire_on": "2026-11-26"})
    assert not v.is_valid({"op": "pause", "nudge_id": cancel["nudge_id"]})


def test_nudge_params_chuan_hoa_khong_chua_user_id_va_hash_on_dinh():
    params = load_json(CONTRACTS / "fixtures/blocks/valid/confirm_action.schedule_nudge.json")[
        "data"
    ]["params"]
    assert "user_id" not in params
    shuffled = dict(reversed(list(params.items())))
    assert hash_normalized_params("schedule_nudge", params) == hash_normalized_params(
        "schedule_nudge", shuffled
    )


# =====================================================================================
# Khối: bất biến mà JSON Schema không diễn đạt
# =====================================================================================
def block(name):
    return load_json(CONTRACTS / "fixtures/blocks/valid" / f"{name}.json")


@pytest.mark.parametrize(
    "name", ["obligation_impact.minh_headphones", "obligation_impact.first_of_month"]
)
def test_obligation_impact_tach_chi_phi_cua_mon_khoi_tong_phai_tra(name):
    d = block(name)["data"]
    cost = d["cost"]
    assert cost["item_cost_vnd"] == cost["principal_vnd"] + cost["fee_added_vnd"]
    assert cost["total_due_vnd"] == cost["existing_due_vnd"] + cost["item_cost_vnd"]
    assert d["shortfall_vnd"] == sum(x["shortfall_vnd"] for x in d["at_due"])
    for x in d["at_due"]:
        assert x["shortfall_vnd"] == max(0, x["due_vnd"] - x["balance_before_due_vnd"])
        assert (x["status"] == "short") == (x["shortfall_vnd"] > 0)
    assert (d["status"] == "short") == (d["shortfall_vnd"] > 0)
    if "available_after_vnd" in cost:
        assert (
            cost["available_before_vnd"] - cost["available_after_vnd"] == cost["principal_vnd"]
        )  # phí không trừ hạn mức
    if "ratio" in d:
        r = d["ratio"]
        assert r["exceeds"] == (r["ratio"] > r["threshold"])
        assert abs(r["ratio"] - r["obligations_vnd"] / r["income_vnd"]) < 0.0001
        assert (
            d["cautions"] and d["status"] == "short"
        )  # vượt ngưỡng thì đỏ kèm 'không khuyến khích'


def test_minh_mua_tai_nghe_1_2_trieu_phi_phat_sinh_them_bang_0_vi_thang_da_co_giao_dich():
    """Lệch so với câu chữ tiêu chí 1 của phase 3 (1.233.000 ₫): theo quyết định số 5 của phase 2, phí 33.000 ₫ tính MỘT lần mỗi
    nghĩa vụ và `minh` đã có nghĩa vụ Trả sau 1.000.000 ₫ (phí nằm trong đó). Hợp đồng nói thật bằng hai con số tách nhau."""
    cost = block("obligation_impact.minh_headphones")["data"]["cost"]
    assert (cost["principal_vnd"], cost["fee_added_vnd"], cost["item_cost_vnd"]) == (
        1200000,
        0,
        1200000,
    )
    assert (cost["existing_due_vnd"], cost["total_due_vnd"]) == (1000000, 2200000)
    assert cost["due_date"] == "2026-12-05"
    # nghĩa vụ chưa có thì phí phát sinh thêm: 300.000 + 33.000 = 333.000 (tiêu chí 6 của phase 2)
    first = block("obligation_impact.first_of_month")["data"]["cost"]
    assert (first["fee_added_vnd"], first["item_cost_vnd"], first["total_due_vnd"]) == (
        33000,
        333000,
        333000,
    )
    assert first["fee"]["amount_vnd"] == first["fee_added_vnd"]


def test_credit_cost_bat_bien_bi_pydantic_chan():
    cost = copy.deepcopy(block("obligation_impact.minh_headphones")["data"]["cost"])
    for field in ("item_cost_vnd", "total_due_vnd"):
        bad = {**cost, field: cost[field] + 1}
        with pytest.raises(ValidationError):
            b.CreditCost.model_validate(bad)


@pytest.mark.parametrize(
    "name",
    [
        "affordability_card.transfer_250k",
        "affordability_card.transfer_an_uong_short",
        "affordability_card.credit_only",
    ],
)
def test_affordability_card_nhat_quan(name):
    d = block(name)["data"]
    assert block(name)["id"] == f"affordability_card:{block(name)['trace_id']}"
    checks = {c["jar"]["code"]: c for c in d["jar_checks"]}
    assert all(
        c["balance_before_vnd"] - c["balance_after_vnd"] == d["amount_vnd"] for c in d["jar_checks"]
    )
    for c in d["jar_checks"]:
        if c["status"] == "short":
            assert "shortfall_vnd" in c  # hụt M đồng trước kỳ lương
        if "days_earlier" in c:
            before = date.fromisoformat(c["runout_date_before"])
            after = date.fromisoformat(c["runout_date_after"])
            assert c["days_earlier"] == (before - after).days  # cạn sớm N ngày
    order = {"ok": 0, "tight": 1, "short": 2}
    if d["funding_source"] == "jar":
        if "selected_jar_code" in d:
            assert d["verdict"] == checks[d["selected_jar_code"]]["status"]
        else:
            assert d["verdict"] == min((c["status"] for c in d["jar_checks"]), key=order.get)
    else:
        assert d["verdict"] == d["credit"]["status"]
    # ba trạng thái luôn có chữ: headline không rỗng và hiện lại ở fallback_text
    assert d["headline"] and block(name)["fallback_text"] == d["headline"]
    for o in d["options"]:
        assert (
            "action" not in o
        )  # phương án tất định của engine chưa có hành động; agent gắn khi dựng khối options


def test_affordability_the_chuyen_250k_dung_ba_trang_thai_nhu_tieu_chi_3():
    checks = {
        c["jar"]["code"]: c["status"]
        for c in block("affordability_card.transfer_250k")["data"]["jar_checks"]
    }
    assert checks == {"hoa_don": "tight", "di_lai": "ok", "an_uong": "short"}  # vàng, xanh, đỏ
    credit = block("affordability_card.transfer_250k")["data"]["credit"]["cost"]
    # tiêu chí 3 ghi 283.000 ₫: lệch cùng lý do với mục 10 (phí đã tính trong nghĩa vụ có sẵn của `minh`)
    assert (credit["item_cost_vnd"], credit["fee_added_vnd"], credit["total_due_vnd"]) == (
        250000,
        0,
        1250000,
    )


def test_options_hanh_dong_tro_toi_khoi_xac_nhan_co_that():
    opts = block("options.move_remind_skip")["data"]["options"]
    confirms = {
        f["id"]: f
        for f in (
            load_json(p)
            for p in fixture_files("blocks/valid")
            if p.name.startswith(("confirm.", "confirm_action."))
        )
    }
    with_action = [o for o in opts if "action" in o]
    assert len(with_action) == 2 and any("action" not in o for o in opts)
    for o in with_action:
        target = confirms[o["action"]["block_id"]]
        assert target["data"]["tool"] == o["action"]["tool"]
        assert target["type"] == o["action"]["kind"]
    assert sum(1 for o in opts if o.get("recommended")) <= 1
    assert len({o["option_id"] for o in opts}) == len(opts)


def test_option_action_kind_phai_khop_tool():
    base = {"tool": "schedule_nudge", "block_id": "confirm:t1:" + "a" * 12}
    assert b.OptionAction(kind="confirm_action", **base)
    with pytest.raises(ValidationError):
        b.OptionAction(kind="confirm", **base)  # confirm chỉ cho chuyển hũ
    with pytest.raises(ValidationError):
        b.OptionAction(kind="confirm_action", tool="move_between_jars", block_id=base["block_id"])


def test_options_khong_trung_id_va_toi_da_mot_de_xuat():
    data = copy.deepcopy(block("options.move_remind_skip")["data"])
    dup = copy.deepcopy(data)
    dup["options"][1]["option_id"] = dup["options"][0]["option_id"]
    with pytest.raises(ValidationError):
        b.OptionsData.model_validate(dup)
    two = copy.deepcopy(data)
    for o in two["options"]:
        o["recommended"] = True
    with pytest.raises(ValidationError):
        b.OptionsData.model_validate(two)


def test_clarify_dung_mot_cau_hoi():
    d = copy.deepcopy(block("clarify.amount")["data"])
    assert d["question"].count("?") == 1
    d["question"] = "Bao nhiêu? Bằng gì?"
    with pytest.raises(ValidationError):
        b.ClarifyData.model_validate(d)


def test_explain_nhom_tin_cay_co_ly_do_va_luat_khop_file_luat():
    d = block("explain.what_if")["data"]
    assert d["confidence"]["band"] in wallet.CONFIDENCE_BANDS and d["confidence"]["reasons"]
    rule_ids = {r.stem for r in RULE_FILES}
    for r in d["rules_checked"]:
        assert r["rule_id"] in rule_ids | {"numeric_grounding", "schema_validity"}
    assert block("explain.what_if")["id"] == f"explain:{d['subject_trace_id']}"


def test_forecast_what_if_cu_van_ve_duoc_baseline_va_id_khong_de_len():
    obj = block("forecast_timeline.what_if")
    assert obj["id"].endswith(":what_if")
    # bỏ `compare` thì vẫn là khối hợp lệ như phase 2 (frontend cũ vẽ baseline)
    legacy = copy.deepcopy(obj)
    del legacy["data"]["compare"]
    legacy["id"] = legacy["id"].removesuffix(":what_if")
    assert b.parse_block(legacy).data.compare is None
    assert (
        tuple(b.ForecastCompare.model_fields["kind"].annotation.__args__) == wallet.SCENARIO_KINDS
    )


def test_builder_forecast_what_if_dung_cau_thay_the_cho_phan_sau():
    obj = block("forecast_timeline.what_if")
    built = b.build_forecast_timeline_from_data(
        data=obj["data"], **{**KW, "source_tool": "forecast___run_scenario"}
    )
    assert built.id == f"forecast_timeline:{KW['trace_id']}:giai_tri:what_if"
    assert built.fallback_text.startswith("Nếu Mua tai nghe 500.000 ₫ từ hũ Giải trí: ")
    assert "sát" in built.fallback_text  # trạng thái SAU là tight, có chữ
    assert (
        built.data.status == "ok" and built.data.compare.after.status == "tight"
    )  # trước và sau phân biệt


def test_builders_phase_3_dung_id_va_fallback_do_code_viet():
    clarify = b.build_clarify(
        question="Bạn định mua với giá khoảng bao nhiêu?", slot="amount", chips=[], **KW
    )
    assert (
        clarify.id == f"clarify:{KW['trace_id']}" and clarify.fallback_text == clarify.data.question
    )
    sug = b.build_suggestions(
        context="after_answer",
        items=[{"id": "a", "label": "Hũ nào cạn?", "prompt": "Hũ nào cạn?"}],
        **KW,
    )
    assert sug.id == f"suggestions:{KW['trace_id']}:after_answer"
    exp = b.build_explain(data=block("explain.what_if")["data"], **KW)
    assert "Độ tin cậy: Vừa" in exp.fallback_text
    assert exp.id == f"explain:{exp.data.subject_trace_id}"
    notice = b.build_notice(
        kind="error", title="Lỗi", message="Thử lại nhé.", code="INTERNAL_ERROR", retryable=True,
        suggestions=[{"id": "a", "label": "x", "prompt": "y"}], **KW,
    )  # fmt: skip
    assert notice.data.retryable is True and notice.data.suggestions[0].id == "a"
    plain = b.build_notice(kind="degraded", title="t", message="m", **KW)
    assert (
        "retryable" not in b.block_to_wire(plain)["data"]
    )  # trường tùy chọn vắng thì không phát null


def test_notice_cu_cua_phase_1_van_hop_le_khong_tang_phien_ban():
    for name in ("notice.degraded", "notice.out_of_scope"):
        obj = block(name)
        assert obj["v"] == 1 and b.parse_block(obj).data.retryable is None


def test_notice_kind_co_du_bon_loai_va_loi_co_thu_lai():
    assert set(b.NoticeKind.__args__) == {"out_of_scope", "degraded", "low_data", "error"}
    retry = block("notice.error_retry")["data"]
    assert retry["kind"] == "error" and retry["retryable"] is True
    assert block("notice.out_of_scope_suggestions")["data"]["suggestions"]
    assert block("notice.low_data")["data"]["degraded_reason"] == "short_history"


def test_cac_tap_gia_tri_phase_3_khop_hang_so():
    opt = load_json(CONTRACTS / "blocks" / "options.schema.json")["$defs"]
    assert tuple(opt["OptionItem"]["properties"]["kind"]["enum"]) == wallet.OPTION_KINDS
    # phương án chỉ dẫn tới tool của ledger/planner (phase 1 tới 3); confirm_rows (phase 5) không thuộc ACTION_TOOLS
    option_tools = wallet.ACTION_TOOLS
    assert tuple(opt["OptionAction"]["properties"]["tool"]["enum"]) == option_tools
    assert tuple(b.OptionKind.__args__) == wallet.OPTION_KINDS
    assert tuple(b.ActionToolName.__args__) == option_tools
    notice = load_json(CONTRACTS / "blocks" / "notice.schema.json")["$defs"]["NoticeData"][
        "properties"
    ]
    assert tuple(notice["degraded_reason"]["enum"]) == b.DegradedReason.__args__
    clarify = load_json(CONTRACTS / "blocks" / "clarify.schema.json")["$defs"]["ClarifyData"][
        "properties"
    ]
    assert tuple(clarify["slot"]["enum"]) == b.ClarifySlot.__args__
    explain = load_json(CONTRACTS / "blocks" / "explain.schema.json")["$defs"]
    assert (
        tuple(explain["RuleCheck"]["properties"]["outcome"]["enum"]) == b.RuleOutcomeName.__args__
    )
    assert tuple(explain["ExplainConfidence"]["properties"]["band"]["$ref"].split("/")[-1:]) == (
        "ConfidenceBand",
    )
    nudge = SCHEMAS["ScheduleNudgeParams"]["properties"]["kind"]["enum"]
    assert tuple(nudge) == wallet.NUDGE_KINDS
    cmp_kinds = load_json(CONTRACTS / "blocks" / "forecast_timeline.schema.json")["$defs"][
        "ForecastCompare"
    ]["properties"]["kind"]["enum"]
    assert tuple(cmp_kinds) == wallet.SCENARIO_KINDS


def test_ba_trang_thai_du_sat_hut_dung_chung_mot_dinh_nghia():
    for name in ("affordability_card", "obligation_impact", "options"):
        text = (CONTRACTS / "blocks" / f"{name}.schema.json").read_text(encoding="utf-8")
        assert "forecast_timeline.schema.json#/$defs/JarStatus" in text
        assert '"ok", "tight", "short"' not in text  # không định nghĩa lại enum


# =====================================================================================
# Luật suitability dạng dữ liệu
# =====================================================================================
RULES_DIR = REPO / "gateway" / "tools" / "planner" / "rules"
RULE_FILES = sorted(RULES_DIR.glob("*.yaml"))
RULE_SCHEMA = json.loads((RULES_DIR / "rule.schema.json").read_text(encoding="utf-8"))


def load_rule(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_co_du_nam_luat_cua_phase_3():
    assert {p.stem for p in RULE_FILES} == {
        "obligations_first", "emergency_before_investing", "risk_within_tolerance",
        "no_borrow_to_spend", "obligation_to_income",
    }  # fmt: skip


@pytest.mark.parametrize("path", RULE_FILES, ids=lambda p: p.name)
def test_file_luat_hop_le_qua_json_schema_va_pydantic(path):
    Draft202012Validator.check_schema(RULE_SCHEMA)
    obj = load_rule(path)
    assert list(Draft202012Validator(RULE_SCHEMA).iter_errors(obj)) == []
    rule = suitability.parse_rule(obj)
    assert rule.id == path.stem
    for name, t in rule.thresholds.items():
        assert t.note and t.source, (
            f"{path.name}:{name} thiếu ghi chú hoặc nguồn"
        )  # ngưỡng là dữ liệu có nguồn


def test_moi_evaluator_dung_dung_mot_lan_va_khop_enum():
    used = [load_rule(p)["evaluator"] for p in RULE_FILES]
    assert sorted(used) == sorted(suitability.EVALUATORS) and len(set(used)) == len(used)
    assert RULE_SCHEMA["properties"]["evaluator"]["enum"] == list(suitability.EVALUATORS)


def test_luat_khong_gan_cung_so_trong_loi_nhan():
    """Số nằm ở `thresholds`, không rải trong câu hiển thị (câu hiển thị không chứa số liệu)."""
    for p in RULE_FILES:
        rule = load_rule(p)
        assert not any(ch.isdigit() for ch in rule["message"]), p.name


def test_nguong_nghia_vu_tren_thu_nhap_la_ty_le_trong_0_1():
    rule = suitability.parse_rule(load_rule(RULES_DIR / "obligation_to_income.yaml"))
    t = rule.thresholds["max_ratio"]
    assert t.unit == "ratio" and 0 < float(t.value) < 1
    assert (
        rule.severity_for("user_request") == "warn"
        and rule.severity_for("recommendation") == "block"
    )


def test_luat_khong_khuyen_vay_de_tieu_chi_chan_khuyen_nghi_cua_he_thong():
    rule = suitability.parse_rule(load_rule(RULES_DIR / "no_borrow_to_spend.yaml"))
    assert rule.severity_for("recommendation") == "block"
    assert rule.applies_when.funding_sources == ["credit"] and rule.applies_when.essential is False


def test_ket_luan_suitability_bat_bien():
    ok = load_json(CONTRACTS / "fixtures/tools/check_suitability.ok.json")["data"]
    bad = load_json(CONTRACTS / "fixtures/tools/check_suitability.violation.json")["data"]
    assert suitability.SuitabilityVerdict.model_validate(ok).ok is True
    assert suitability.SuitabilityVerdict.model_validate(bad).ok is False
    broken = {**bad, "ok": True}  # có vi phạm block mà ok đúng
    with pytest.raises(ValidationError):
        suitability.SuitabilityVerdict.model_validate(broken)
    orphan = {**bad, "checked": ok["checked"]}  # vi phạm không có trong checked ở mức warn/fail
    with pytest.raises(ValidationError):
        suitability.SuitabilityVerdict.model_validate(orphan)
    rule_ids = {p.stem for p in RULE_FILES}
    assert {c["rule_id"] for c in ok["checked"]} == rule_ids  # kiểm đủ năm luật


# =====================================================================================
# Chống lệch giữa các nơi nói cùng một tập giá trị
# =====================================================================================
def test_toan_bo_phase_3_khong_dung_nhan_cam_va_khong_co_tien_dang_chuoi():
    banned = ("ví trả sau", "momo", "finhealth")
    roots = [CONTRACTS, RULES_DIR]
    for root in roots:
        for path in root.rglob("*"):
            if path.suffix in {".json", ".yaml"}:
                text = path.read_text(encoding="utf-8").lower()
                text = "\n".join(line for line in text.splitlines() if "http" not in line)
                assert not any(w in text for w in banned), path.relative_to(REPO)


def test_fixture_phase_3_khong_chua_thong_tin_nhay_cam():
    secrets = ("@", "password", "secret", "arn:aws")
    for path in (CONTRACTS / "fixtures").rglob("*.json"):
        text = path.read_text(encoding="utf-8").lower()
        for s in secrets:
            assert s not in text, f"{path.relative_to(REPO)} chứa {s!r}"
