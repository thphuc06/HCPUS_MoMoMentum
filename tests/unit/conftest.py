"""Tiện ích dùng chung cho test hợp đồng (contracts/): nạp JSON Schema vào một registry để
$ref liên file (kể cả từ OpenAPI) được giải quyết như khi dùng thật."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

REPO = Path(__file__).resolve().parents[2]
CONTRACTS = REPO / "contracts"
BASE = "https://contracts.yofina.invalid"
OPENAPI_URI = f"{BASE}/rest/openapi.yaml"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_registry() -> Registry:
    reg = Registry()
    for path in sorted(CONTRACTS.glob("*/*.schema.json")):
        schema = load_json(path)
        reg = reg.with_resource(schema["$id"], Resource.from_contents(schema))
    spec = yaml.safe_load((CONTRACTS / "rest" / "openapi.yaml").read_text(encoding="utf-8"))
    return reg.with_resource(
        OPENAPI_URI, Resource.from_contents(spec, default_specification=DRAFT202012)
    )


@pytest.fixture(scope="session")
def registry() -> Registry:
    return build_registry()


@pytest.fixture(scope="session")
def contracts_dir() -> Path:
    return CONTRACTS


def fixture_files(sub: str) -> list[Path]:
    files = sorted((CONTRACTS / "fixtures" / sub).glob("*.json"))
    assert files, f"không có fixture trong {sub}"
    return files
