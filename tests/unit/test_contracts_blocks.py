"""Hợp đồng khối UI: JSON Schema <-> Pydantic <-> fixture dùng chung với test TypeScript."""

from __future__ import annotations

import pytest
from conftest import BASE, CONTRACTS, REPO, fixture_files, load_json
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from yofina_core import blocks as b
from yofina_core.confirm import params_hash

BLOCK_TYPES = ["jar_summary", "confirm", "receipt", "notice"]
BLOCK_SCHEMA_FILES = {t: CONTRACTS / "blocks" / f"{t}.schema.json" for t in BLOCK_TYPES}


def validator(registry, ref: str) -> Draft202012Validator:
    return Draft202012Validator({"$ref": f"{BASE}/blocks/{ref}"}, registry=registry)


def errors(registry, ref, instance):
    return list(validator(registry, ref).iter_errors(instance))


def prefix_of(path) -> str:
    return path.name.split(".")[0]


# --- bản thân schema ----------------------------------------------------------------------
@pytest.mark.parametrize("path", sorted(CONTRACTS.glob("*/*.schema.json")), ids=lambda p: p.name)
def test_schema_hop_le_theo_metaschema_2020_12(path):
    schema = load_json(path)
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"].startswith(BASE + "/")


def test_union_dung_bon_khoi_theo_thu_tu():
    union = load_json(CONTRACTS / "blocks" / "block.schema.json")
    refs = [m["$ref"] for m in union["oneOf"]]
    assert refs == [f"{t}.schema.json" for t in BLOCK_TYPES]
    assert list(b.BLOCK_MODELS) == BLOCK_TYPES


@pytest.mark.parametrize("type_", BLOCK_TYPES)
def test_moi_khoi_dung_chung_phong_bi(type_):
    env = load_json(CONTRACTS / "blocks" / "envelope.schema.json")
    schema = load_json(BLOCK_SCHEMA_FILES[type_])
    assert schema["required"] == env["required"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["type"] == {"const": type_}
    for key in ("v", "id", "trace_id", "fallback_text", "source"):
        env_ref = env["properties"][key]["$ref"].replace("#/", "envelope.schema.json#/")
        assert schema["properties"][key]["$ref"] == env_ref, key


# --- fixture ------------------------------------------------------------------------------
@pytest.mark.parametrize("path", fixture_files("blocks/valid"), ids=lambda p: p.name)
def test_fixture_hop_le_qua_schema_rieng_hop_va_pydantic(registry, path):
    obj = load_json(path)
    type_ = prefix_of(path)
    assert obj["type"] == type_
    assert errors(registry, f"{type_}.schema.json", obj) == []
    assert errors(registry, "block.schema.json", obj) == []
    assert errors(registry, "envelope.schema.json", obj) == []
    parsed = b.parse_block(obj)
    assert isinstance(parsed, b.BLOCK_MODELS[type_])
    assert b.block_to_wire(parsed) == obj  # khứ hồi không đổi dữ liệu


@pytest.mark.parametrize("path", fixture_files("blocks/invalid"), ids=lambda p: p.name)
def test_fixture_sai_bi_ca_json_schema_lan_pydantic_tu_choi(registry, path):
    obj = load_json(path)
    ref = "block.schema.json" if prefix_of(path) == "block" else f"{prefix_of(path)}.schema.json"
    assert errors(registry, ref, obj), "JSON Schema lẽ ra phải từ chối"
    with pytest.raises(ValidationError):
        b.parse_block(obj)


@pytest.mark.parametrize("path", fixture_files("blocks/schema_only_invalid"), ids=lambda p: p.name)
def test_truong_thua_bi_phia_sinh_du_lieu_tu_choi(registry, path):
    obj = load_json(path)
    assert errors(registry, f"{prefix_of(path)}.schema.json", obj)
    with pytest.raises(ValidationError):
        b.parse_block(obj)


def test_fixture_unknown_type_van_qua_phong_bi(registry):
    obj = load_json(CONTRACTS / "fixtures/blocks/invalid/block.unknown_type.json")
    assert errors(registry, "envelope.schema.json", obj) == []


@pytest.mark.parametrize("path", fixture_files("blocks/valid"), ids=lambda p: p.name)
def test_confirm_fixture_co_hash_dung_va_id_theo_quy_tac(path):
    obj = load_json(path)
    if obj["type"] == "confirm":
        d = obj["data"]
        assert d["params_hash"] == params_hash(d["tool"], d["params"])
        assert obj["id"] == f"confirm:{obj['trace_id']}:{d['params_hash'][:12]}"
        # xem trước nhất quán với số tiền
        amount = d["params"]["amount_vnd"]
        f, t = d["preview"]["from"], d["preview"]["to"]
        assert f["code"] == d["params"]["from_jar"] and t["code"] == d["params"]["to_jar"]
        assert f["before_vnd"] - f["after_vnd"] == amount
        assert t["after_vnd"] - t["before_vnd"] == amount
    elif obj["type"] == "receipt":
        assert obj["id"] == f"receipt:{obj['data']['transaction_id']}"
    elif obj["type"] == "jar_summary" and obj["data"]["jars"]:
        assert obj["data"]["jars_total_vnd"] == sum(j["balance_vnd"] for j in obj["data"]["jars"])


# --- hình dạng Pydantic khớp JSON Schema ---------------------------------------------------
_KEEP = (
    "const", "enum", "pattern", "minLength", "maxLength", "minimum", "maximum",
    "exclusiveMinimum", "minItems", "maxItems",
)  # fmt: skip


def normalize(schema, resolver):
    """Cây chuẩn hóa chỉ giữ thứ có nghĩa với hợp đồng (bỏ title, description, format, default)."""
    if "$ref" in schema:
        hit = resolver.lookup(schema["$ref"])
        return normalize(hit.contents, hit.resolver)
    if "anyOf" in schema:  # Pydantic: Optional[X] -> anyOf [X, null]
        non_null = [s for s in schema["anyOf"] if s.get("type") != "null"]
        assert len(non_null) == 1, schema
        return normalize(non_null[0], resolver)
    out = {k: schema[k] for k in _KEEP if k in schema}
    if "enum" in out and len(out["enum"]) == 1:  # enum một giá trị == const
        out["const"] = out.pop("enum")[0]
    if "const" not in out and "enum" not in out and "type" in schema:
        out["type"] = schema["type"]
    if "properties" in schema:
        out["properties"] = {k: normalize(v, resolver) for k, v in schema["properties"].items()}
        out["required"] = sorted(schema.get("required", []))
        out["additionalProperties"] = schema.get("additionalProperties")
    if "items" in schema:
        out["items"] = normalize(schema["items"], resolver)
    return out


def contract_tree(registry, type_):
    resolver = registry.resolver(base_uri=f"{BASE}/blocks/")
    hit = resolver.lookup(f"{type_}.schema.json")
    return normalize(hit.contents, hit.resolver)


def pydantic_tree(model):
    schema = model.model_json_schema(by_alias=True)
    reg = Registry().with_resource("urn:pyd", Resource.from_contents(schema, DRAFT202012))
    resolver = reg.resolver(base_uri="urn:pyd")
    return normalize(schema, resolver)


@pytest.mark.parametrize("type_", BLOCK_TYPES)
def test_model_pydantic_khop_hinh_dang_json_schema(registry, type_):
    assert pydantic_tree(b.BLOCK_MODELS[type_]) == contract_tree(registry, type_)


def test_phep_so_sanh_hinh_dang_co_bat_duoc_lech(registry):
    """Đảm bảo test trên không vô tác dụng: sửa một giới hạn thì phải thấy lệch."""
    tree = contract_tree(registry, "jar_summary")
    tampered = pydantic_tree(b.JarSummaryBlock)
    tampered["properties"]["data"]["properties"]["jars_total_vnd"]["maximum"] = 1
    assert tampered != tree


def test_khong_con_tham_chieu_toi_file_ngoai_thu_muc_contracts():
    for path in CONTRACTS.glob("**/*.schema.json"):
        text = path.read_text(encoding="utf-8")
        assert "http://" not in text and str(REPO) not in text
