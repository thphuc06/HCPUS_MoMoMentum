"""Hợp đồng tool ledger: schema cho AgentCore Gateway (Lambda target) và kết quả tool."""

from __future__ import annotations

import pytest
from conftest import BASE, CONTRACTS, fixture_files, load_json
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter

from yofina_core import blocks as b
from yofina_core.errors import ErrorCode

TOOLS = load_json(CONTRACTS / "tools" / "ledger.json")
BY_NAME = {t["name"]: t for t in TOOLS}

# Gateway chỉ nhận một tập con của JSON Schema ở từng thuộc tính (type, description, items,
# properties, required): docs "Property schema definition" của AgentCore Gateway.
NODE_KEYS = {"type", "description", "properties", "required", "items"}
TOOL_KEYS = {"name", "description", "inputSchema"}
TYPES = {"string", "integer", "number", "boolean", "array", "object"}
TARGET = "ledger"


def walk(node, path="inputSchema"):
    assert set(node) <= NODE_KEYS, f"{path}: từ khóa Gateway không nhận: {set(node) - NODE_KEYS}"
    assert node["type"] in TYPES, path
    for name, child in node.get("properties", {}).items():
        yield from walk(child, f"{path}.{name}")
    if "items" in node:
        yield from walk(node["items"], f"{path}[]")
    yield path, node


def test_cac_tool_cua_phase_1():
    assert [t["name"] for t in TOOLS] == [
        "get_jar_balances",
        "query_transactions",
        "move_between_jars",
        "save_turn",
    ]


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t["name"])
def test_dinh_dang_tool_definition_cua_gateway(tool):
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


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t["name"])
def test_ten_day_du_qua_gateway_vua_gioi_han_converse(tool):
    full = f"{TARGET}___{tool['name']}"
    assert len(full) <= 64  # giới hạn tên tool của Bedrock Converse
    assert full.replace("_", "").isalnum() and full.isascii()


@pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t["name"])
def test_user_id_la_tham_so_tuy_chon_he_thong_tu_dien(tool):
    props = tool["inputSchema"]["properties"]
    assert props["user_id"]["type"] == "string"
    assert "user_id" not in tool["inputSchema"].get("required", [])
    assert "tự điền" in props["user_id"]["description"]


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
    assert (
        "confirm_token" not in schema["required"]
    )  # thiếu token -> NEEDS_CONFIRMATION, không phải lỗi schema


def test_save_turn_theo_dac_ta():
    schema = BY_NAME["save_turn"]["inputSchema"]
    assert set(schema["properties"]) == {
        "user_id",
        "conversation_id",
        "trace_id",
        "user_text",
        "assistant_text",
        "blocks",
    }
    assert set(schema["required"]) == {"conversation_id", "trace_id"}
    item = schema["properties"]["blocks"]["items"]
    assert item["properties"]["seq"]["type"] == "integer"
    assert item["properties"]["block"]["type"] == "object"
    assert set(item["required"]) == {"seq", "block"}


def test_query_transactions_khong_co_tham_so_bat_buoc():
    assert "required" not in BY_NAME["query_transactions"]["inputSchema"]


# --- kết quả tool ---------------------------------------------------------------------------
def result_validator(registry, name):
    ref = f"{BASE}/tools/ledger.results.schema.json#/$defs/{name}"
    return Draft202012Validator({"$ref": ref}, registry=registry)


RESULT_FOR = {
    "get_jar_balances": "GetJarBalancesResult",
    "query_transactions": "QueryTransactionsResult",
    "move_between_jars": "MoveBetweenJarsResult",
    "save_turn": "SaveTurnResult",
}


@pytest.mark.parametrize("path", fixture_files("tools"), ids=lambda p: p.name)
def test_ket_qua_tool_fixture_hop_le(registry, path):
    tool = path.name.split(".")[0]
    obj = load_json(path)
    errs = list(result_validator(registry, RESULT_FOR[tool]).iter_errors(obj))
    assert errs == []
    if obj["status"] == "OK" and tool == "get_jar_balances":
        b.JarSummaryData.model_validate(obj["data"])
    if obj["status"] == "NEEDS_CONFIRMATION":
        b.ConfirmData.model_validate(obj["data"])
    if obj["status"] == "OK" and tool == "move_between_jars":
        b.ReceiptData.model_validate(obj["data"])
    if obj["status"] == "ERROR":
        assert obj["code"] in {c.value for c in ErrorCode}


def test_ket_qua_sai_bi_tu_choi(registry):
    v = result_validator(registry, "MoveBetweenJarsResult")
    needs = load_json(CONTRACTS / "fixtures/tools/move_between_jars.needs_confirmation.json")
    assert not v.is_valid({**needs, "status": "OK"})  # data của confirm không phải receipt
    assert not v.is_valid({"status": "MOVED"})
    assert not v.is_valid({"status": "ERROR", "code": "token reused", "message": "x"})
    assert not v.is_valid({k: val for k, val in needs.items() if k != "app_date"})


def test_pydantic_type_adapter_dung_duoc_cho_data():
    # đảm bảo model dữ liệu của khối dùng lại được cho kết quả tool (không cần model riêng)
    TypeAdapter(b.ConfirmData)
    TypeAdapter(b.ReceiptData)
    TypeAdapter(b.JarSummaryData)
