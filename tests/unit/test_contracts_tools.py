"""Hợp đồng tool (target `ledger`, `forecast`, `knowledge`, `planner`, `audit`): schema cho AgentCore Gateway và kết quả tool."""

from __future__ import annotations

import pytest
from conftest import BASE, CONTRACTS, fixture_files, load_json
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter

from yofina_core import blocks as b
from yofina_core import scenario, suitability, wallet
from yofina_core.errors import ErrorCode

LEDGER = load_json(CONTRACTS / "tools" / "ledger.json")
FORECAST = load_json(CONTRACTS / "tools" / "forecast.json")
KNOWLEDGE = load_json(CONTRACTS / "tools" / "knowledge.json")
PLANNER = load_json(CONTRACTS / "tools" / "planner.json")
AUDIT = load_json(CONTRACTS / "tools" / "audit.json")
TOOLS = (
    [(t, "ledger") for t in LEDGER]
    + [(t, "forecast") for t in FORECAST]
    + [(t, "knowledge") for t in KNOWLEDGE]
    + [(t, "planner") for t in PLANNER]
    + [(t, "audit") for t in AUDIT]
)
BY_NAME = {t["name"]: t for t, _ in TOOLS}

# Gateway chỉ nhận một tập con của JSON Schema ở từng thuộc tính (type, description, items,
# properties, required): docs "Property schema definition" của AgentCore Gateway.
NODE_KEYS = {"type", "description", "properties", "required", "items"}
TOOL_KEYS = {"name", "description", "inputSchema"}
TYPES = {"string", "integer", "number", "boolean", "array", "object"}


def walk(node, path="inputSchema"):
    assert set(node) <= NODE_KEYS, f"{path}: từ khóa Gateway không nhận: {set(node) - NODE_KEYS}"
    assert node["type"] in TYPES, path
    for name, child in node.get("properties", {}).items():
        yield from walk(child, f"{path}.{name}")
    if "items" in node:
        yield from walk(node["items"], f"{path}[]")
    yield path, node


def test_cac_tool_cua_target_ledger_theo_danh_muc_overview():
    assert [t["name"] for t in LEDGER] == list(wallet.LEDGER_TOOLS)
    assert [t["name"] for t in LEDGER] == [
        "get_jar_balances",
        "query_transactions",
        "get_cashflow_summary",
        "get_obligations",
        "get_unclassified",
        "update_profile",
        "record_transaction",
        "move_between_jars",
        "assign_jar",
        "save_turn",
    ]


def test_cac_target_phase_3_khop_hang_so():
    assert [t["name"] for t in FORECAST] == list(wallet.FORECAST_TOOLS)
    assert [t["name"] for t in FORECAST] == [
        "get_forecast", "run_scenario", "list_scenarios", "affordability_check",
    ]  # fmt: skip
    assert [t["name"] for t in KNOWLEDGE] == list(wallet.KNOWLEDGE_TOOLS) == ["get_fee_schedule"]
    assert [t["name"] for t in PLANNER] == list(wallet.PLANNER_TOOLS)
    assert [t["name"] for t in AUDIT] == list(wallet.AUDIT_TOOLS) == ["get_trace", "record_turn"]


def test_target_forecast_co_get_forecast():
    schema = BY_NAME["get_forecast"]["inputSchema"]
    assert set(schema["properties"]) == {"user_id", "jar"}
    assert schema["required"] == ["jar"]


@pytest.mark.parametrize(
    ("tool", "target"), TOOLS, ids=lambda x: x["name"] if isinstance(x, dict) else x
)
def test_dinh_dang_tool_definition_cua_gateway(tool, target):
    assert set(tool) <= TOOL_KEYS and {"name", "description", "inputSchema"} <= set(tool)
    assert tool["description"].strip()
    schema = tool["inputSchema"]
    assert schema["type"] == "object"  # top level bắt buộc là object
    nodes = list(walk(schema))
    # mọi thuộc tính đều có mô tả (LLM đọc để điền)
    for path, node in nodes:
        assert node.get("description", "").strip() or path == "inputSchema", path
    props = schema.get("properties", {})
    assert set(schema.get("required", [])) <= set(props)
    # mọi mảng phải khai items (Gateway từ chối mảng thiếu items)
    for _, node in nodes:
        if node["type"] == "array":
            assert "items" in node


@pytest.mark.parametrize(
    ("tool", "target"), TOOLS, ids=lambda x: x["name"] if isinstance(x, dict) else x
)
def test_ten_day_du_qua_gateway_vua_gioi_han_converse(tool, target):
    full = f"{target}___{tool['name']}"
    assert len(full) <= 64  # giới hạn tên tool của Bedrock Converse
    assert full.replace("_", "").isalnum() and full.isascii()
    assert target.isalnum()  # tên target không có gạch dưới hay dấu chấm


@pytest.mark.parametrize(
    ("tool", "target"), TOOLS, ids=lambda x: x["name"] if isinstance(x, dict) else x
)
def test_user_id_la_tham_so_tuy_chon_he_thong_tu_dien(tool, target):
    props = tool["inputSchema"]["properties"]
    assert props["user_id"]["type"] == "string"
    assert "user_id" not in tool["inputSchema"].get("required", [])
    assert "tự điền" in props["user_id"]["description"]


WRITE_TOOLS = ["update_profile", "record_transaction", "move_between_jars", "assign_jar"]


def test_tool_ghi_khop_danh_sach_cua_hop_dong_va_deu_co_confirm_token_tuy_chon():
    assert sorted(WRITE_TOOLS) == sorted(wallet.AGENT_WRITE_TOOLS)
    for name in WRITE_TOOLS:
        schema = BY_NAME[name]["inputSchema"]
        assert schema["properties"]["confirm_token"]["type"] == "string"
        # thiếu token -> NEEDS_CONFIRMATION, không phải lỗi schema của Gateway
        assert "confirm_token" not in schema.get("required", [])
        assert "KHÔNG ghi gì" in BY_NAME[name]["description"]
        assert "bịa" in BY_NAME[name]["description"]


def test_tool_doc_khong_co_confirm_token():
    for name in ("get_jar_balances", "query_transactions", "get_cashflow_summary",
                 "get_obligations", "get_unclassified", "get_forecast"):  # fmt: skip
        assert "confirm_token" not in BY_NAME[name]["inputSchema"]["properties"]


def test_move_between_jars_theo_dac_ta():
    schema = BY_NAME["move_between_jars"]["inputSchema"]
    assert set(schema["properties"]) == {
        "user_id",
        "from_jar",
        "to_jar",
        "amount_vnd",
        "confirm_token",
    }
    assert schema["properties"]["amount_vnd"]["type"] == "integer"
    assert set(schema["required"]) == {"from_jar", "to_jar", "amount_vnd"}


def test_record_transaction_theo_dac_ta():
    schema = BY_NAME["record_transaction"]["inputSchema"]
    assert set(schema["properties"]) == {
        "user_id", "kind", "amount_vnd", "jar", "tx_type", "funding", "payee_id", "counterparty",
        "note", "obligation_id", "client_ref", "confirm_token",
    }  # fmt: skip
    assert set(schema["required"]) == {"kind", "amount_vnd"}
    assert schema["properties"]["amount_vnd"]["type"] == "integer"
    assert "credit" in schema["properties"]["funding"]["description"]  # nguồn trả bằng hạn mức


def test_assign_jar_theo_dac_ta():
    schema = BY_NAME["assign_jar"]["inputSchema"]
    assert set(schema["properties"]) == {
        "user_id",
        "transaction_id",
        "jar",
        "remember",
        "confirm_token",
    }
    assert set(schema["required"]) == {"transaction_id", "jar"}


def test_update_profile_khong_bat_buoc_truong_nao_va_khai_bao_nghia_vu_long_nhau():
    schema = BY_NAME["update_profile"]["inputSchema"]
    assert "required" not in schema  # ít nhất một thay đổi: Lambda kiểm, không phải schema
    assert set(schema["properties"]) == {
        "user_id", "display_name", "monthly_salary_vnd", "payday_day", "risk_tolerance",
        "obligation", "confirm_token",
    }  # fmt: skip
    ob = schema["properties"]["obligation"]
    assert ob["type"] == "object"
    assert set(ob["properties"]) == {
        "op", "obligation_id", "kind", "name", "amount_vnd", "amount_min_vnd", "amount_max_vnd",
        "fee_vnd", "due_date", "due_day", "cycle", "pay_jar", "is_essential",
    }  # fmt: skip
    assert "required" not in ob  # bắt buộc theo op do Lambda kiểm


def test_save_turn_theo_dac_ta():
    schema = BY_NAME["save_turn"]["inputSchema"]
    assert set(schema["properties"]) == {
        "user_id", "conversation_id", "trace_id", "user_text", "assistant_text", "blocks",
    }  # fmt: skip
    assert set(schema["required"]) == {"conversation_id", "trace_id"}
    item = schema["properties"]["blocks"]["items"]
    assert item["properties"]["seq"]["type"] == "integer"
    assert item["properties"]["block"]["type"] == "object"
    assert set(item["required"]) == {"seq", "block"}


def test_tool_doc_khong_co_tham_so_bat_buoc_tru_get_forecast():
    for name in ("get_jar_balances", "query_transactions", "get_cashflow_summary",
                 "get_obligations", "get_unclassified"):  # fmt: skip
        assert "required" not in BY_NAME[name]["inputSchema"]


def test_tap_gia_tri_trong_mo_ta_khop_hang_so_hop_dong():
    """Mô tả cho LLM nêu các giá trị hợp lệ vì schema Gateway không có enum; kiểm chúng khớp wallet.py."""
    props = BY_NAME["record_transaction"]["inputSchema"]["properties"]
    for v in ("expense", "income"):
        assert v in props["kind"]["description"]
    for v in wallet.RECORDABLE_FUNDING_SOURCES:
        assert v in props["funding"]["description"]
    ob = BY_NAME["update_profile"]["inputSchema"]["properties"]["obligation"]["properties"]
    for v in wallet.DECLARABLE_OBLIGATION_KINDS:
        assert v in ob["kind"]["description"]
    assert "bnpl" not in ob["kind"]["description"]  # trả sau chỉ tự sinh
    for v in wallet.OBLIGATION_CYCLES:
        assert v in ob["cycle"]["description"]
    for v in wallet.RULE_SCOPES:
        assert v in BY_NAME["assign_jar"]["inputSchema"]["properties"]["remember"]["description"]
    for v in ("low", "medium", "high"):
        assert (
            v
            in BY_NAME["update_profile"]["inputSchema"]["properties"]["risk_tolerance"][
                "description"
            ]
        )


# --- kết quả tool ---------------------------------------------------------------------------
wallet_bundle_total_kinds = ("one_time_purchase", "bnpl_purchase")  # khớp BUNDLE_TOTAL_KINDS của engine forecast
RESULT_FILE = {name: "ledger" for name in wallet.LEDGER_TOOLS}
RESULT_FILE["get_forecast"] = "forecast"
RESULT_FILE.update(
    run_scenario="forecast", list_scenarios="forecast", affordability_check="forecast", get_fee_schedule="knowledge",
    check_suitability="planner", schedule_nudge="planner", get_trace="audit", record_turn="audit",
)  # fmt: skip
RESULT_DEF = {
    "get_jar_balances": "GetJarBalancesResult",
    "query_transactions": "QueryTransactionsResult",
    "get_cashflow_summary": "GetCashflowSummaryResult",
    "get_obligations": "GetObligationsResult",
    "get_unclassified": "GetUnclassifiedResult",
    "update_profile": "UpdateProfileResult",
    "record_transaction": "RecordTransactionResult",
    "move_between_jars": "MoveBetweenJarsResult",
    "assign_jar": "AssignJarResult",
    "save_turn": "SaveTurnResult",
    "get_forecast": "GetForecastResult",
    "run_scenario": "RunScenarioResult",
    "list_scenarios": "ListScenariosResult",
    "affordability_check": "AffordabilityCheckResult",
    "get_fee_schedule": "GetFeeScheduleResult",
    "check_suitability": "CheckSuitabilityResult",
    "schedule_nudge": "ScheduleNudgeResult",
    "get_trace": "GetTraceResult",
    "record_turn": "RecordTurnResult",
}


def result_validator(registry, tool):
    ref = f"{BASE}/tools/{RESULT_FILE[tool]}.results.schema.json#/$defs/{RESULT_DEF[tool]}"
    return Draft202012Validator({"$ref": ref}, registry=registry)


def test_moi_tool_co_dinh_nghia_ket_qua():
    assert set(RESULT_DEF) == {t["name"] for t, _ in TOOLS}


@pytest.mark.parametrize("path", fixture_files("tools"), ids=lambda p: p.name)
def test_ket_qua_tool_fixture_hop_le(registry, path):
    tool = path.name.split(".")[0]
    obj = load_json(path)
    errs = list(result_validator(registry, tool).iter_errors(obj))
    assert errs == []
    if obj["status"] == "ERROR":
        assert obj["code"] in {c.value for c in ErrorCode}
        return
    data = obj["data"]
    if tool == "get_jar_balances":
        b.JarSummaryData.model_validate(data)
    elif tool == "move_between_jars" and obj["status"] == "NEEDS_CONFIRMATION":
        b.ConfirmData.model_validate(data)
    elif tool == "move_between_jars":
        b.ReceiptData.model_validate(data)
    elif tool == "get_forecast":
        b.ForecastTimelineData.model_validate(data)
    elif tool == "run_scenario":
        for tl in data["timelines"]:
            parsed = b.ForecastTimelineData.model_validate(tl)
            assert parsed.compare is not None  # mọi khối của what-if là trước-sau
        if "obligation_impact" in data:
            b.ObligationImpactData.model_validate(data["obligation_impact"])
        scenario.parse_scenario(data["spec"])
        if "bundle" in data:
            for item in data["bundle"]:
                assert scenario.parse_scenario(item["spec"]).kind == item["kind"]
            assert data["bundle"][-1]["spec"] == data["spec"]  # phần tử cuối là kịch bản chính
            assert ("bundle_total_vnd" in data) == (len(data["bundle"]) >= 2)
            if "bundle_total_vnd" in data:
                assert data["bundle_total_vnd"] == sum(
                    i["amount_vnd"] for i in data["bundle"] if i["kind"] in wallet_bundle_total_kinds
                )
    elif tool == "list_scenarios":
        for item in data["scenarios"]:
            assert scenario.parse_scenario(item["spec"]).kind == item["kind"]
            assert item["bundle"][-1]["spec"] == item["spec"]
    elif tool == "affordability_check":
        b.AffordabilityCardData.model_validate(data)
    elif tool == "check_suitability":
        suitability.SuitabilityVerdict.model_validate(data)
    elif tool == "get_trace":
        b.parse_block(data["explain"])
    elif tool == "get_fee_schedule":
        assert data["fees"]
    elif tool in ("update_profile", "record_transaction", "assign_jar", "schedule_nudge"):
        model = (
            b.ConfirmActionData if obj["status"] == "NEEDS_CONFIRMATION" else b.ReceiptActionData
        )
        parsed = model.model_validate(data)
        assert parsed.tool == tool


def test_moi_tool_ghi_moi_co_fixture_can_xac_nhan_va_da_ghi():
    names = {p.name for p in fixture_files("tools")}
    for tool in ("update_profile", "record_transaction", "assign_jar"):
        assert f"{tool}.needs_confirmation.json" in names and f"{tool}.ok.json" in names


def test_ket_qua_sai_bi_tu_choi(registry):
    v = result_validator(registry, "move_between_jars")
    needs = load_json(CONTRACTS / "fixtures/tools/move_between_jars.needs_confirmation.json")
    assert not v.is_valid({**needs, "status": "OK"})  # data của confirm không phải receipt
    assert not v.is_valid({"status": "MOVED"})
    assert not v.is_valid({"status": "ERROR", "code": "token reused", "message": "x"})
    assert not v.is_valid({k: val for k, val in needs.items() if k != "app_date"})


def test_tool_ghi_moi_khong_nhan_data_cua_khoi_confirm_chuyen_hu(registry):
    v = result_validator(registry, "record_transaction")
    move = load_json(CONTRACTS / "fixtures/tools/move_between_jars.needs_confirmation.json")
    assert not v.is_valid(move)  # data của `confirm` (move) không phải `confirm_action`
    ok = load_json(CONTRACTS / "fixtures/tools/record_transaction.ok.json")
    assert v.is_valid(ok)
    assert not v.is_valid({**ok, "status": "NEEDS_CONFIRMATION"})  # receipt không phải confirm


def test_cashflow_tach_luong_khoi_tien_vao_khac(registry):
    obj = load_json(CONTRACTS / "fixtures/tools/get_cashflow_summary.ok.json")
    data = obj["data"]
    assert {"salary_income_vnd", "other_income_vnd"} <= set(
        data
    )  # tiền vào khác không phải thu nhập
    assert data["spent_vnd"] == sum(j["spent_vnd"] for j in data["by_jar"])
    bad = {**obj, "data": {k: v for k, v in data.items() if k != "other_income_vnd"}}
    assert not result_validator(registry, "get_cashflow_summary").is_valid(bad)


def test_trang_giao_dich_co_con_tro_chi_khi_con_nua(registry):
    page = load_json(CONTRACTS / "fixtures/tools/query_transactions.ok_page.json")
    assert page["data"]["has_more"] and page["data"]["next_cursor"]
    first = load_json(CONTRACTS / "fixtures/tools/query_transactions.ok.json")
    assert (
        "next_cursor" not in first["data"] and not first["data"]["has_more"]
    )  # tương thích phase 1


def test_pydantic_type_adapter_dung_duoc_cho_data():
    # đảm bảo model dữ liệu của khối dùng lại được cho kết quả tool (không cần model riêng)
    for model in (
        b.ConfirmData, b.ReceiptData, b.JarSummaryData, b.ConfirmActionData, b.ReceiptActionData,
        b.ForecastTimelineData,
    ):  # fmt: skip
        TypeAdapter(model)
