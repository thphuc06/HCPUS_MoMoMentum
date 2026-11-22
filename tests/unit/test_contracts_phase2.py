"""Chống lệch giữa các nơi cùng nói một tập giá trị của phase 2: hằng số `yofina_core.wallet`, JSON Schema, OpenAPI,
CHECK của DB; cộng các quy ước toàn dự án (tiền là số nguyên, không đồng hồ hệ thống, không nhãn cấm)."""

from __future__ import annotations

import re

import pytest
import yaml
from conftest import CONTRACTS, REPO, load_json

from yofina_core import wallet

SPEC = yaml.safe_load((CONTRACTS / "rest" / "openapi.yaml").read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]
RESULTS = load_json(CONTRACTS / "tools" / "ledger.results.schema.json")["$defs"]
FORECAST_BLOCK = load_json(CONTRACTS / "blocks" / "forecast_timeline.schema.json")["$defs"]
PROACTIVE = load_json(CONTRACTS / "blocks" / "proactive_card.schema.json")["$defs"]
CONFIRM_ACTION = load_json(CONTRACTS / "blocks" / "confirm_action.schema.json")["$defs"]
RECEIPT_ACTION = load_json(CONTRACTS / "blocks" / "receipt_action.schema.json")["$defs"]
FORECAST_IO = load_json(CONTRACTS / "ml" / "forecast_io.schema.json")["$defs"]


def event(name):
    return load_json(CONTRACTS / "events" / f"{name}.schema.json")["properties"]


def enum_of(node) -> tuple[str, ...]:
    return tuple(node["enum"])


def test_hu_kind_va_vai_tro_he_thong():
    assert enum_of(SCHEMAS["JarKind"]) == wallet.JAR_KINDS
    assert enum_of(SCHEMAS["JarFull"]["properties"]["system_role"]) == wallet.SYSTEM_ROLES
    assert enum_of(SCHEMAS["JarSpec"]["properties"]["kind"]) == wallet.USER_JAR_KINDS
    assert enum_of(SCHEMAS["JarTemplate"]["properties"]["kind"]) == wallet.USER_JAR_KINDS
    assert (
        enum_of(FORECAST_IO["JarInput"]["properties"]["kind"]) == wallet.USER_JAR_KINDS
    )  # hũ hệ thống không dự báo
    assert wallet.SYSTEM_JAR_CODES == {
        "other_income": wallet.OTHER_INCOME_JAR_CODE,
        "unclassified": wallet.UNCLASSIFIED_JAR_CODE,
    }


def test_nghia_vu():
    assert enum_of(RESULTS["Obligation"]["properties"]["kind"]) == wallet.OBLIGATION_KINDS
    assert enum_of(event("obligation.changed")["kind"]) == wallet.OBLIGATION_KINDS
    assert (
        enum_of(SCHEMAS["ObligationChange"]["properties"]["kind"])
        == wallet.DECLARABLE_OBLIGATION_KINDS
    )
    assert enum_of(RESULTS["Obligation"]["properties"]["cycle"]) == wallet.OBLIGATION_CYCLES
    assert enum_of(SCHEMAS["ObligationChange"]["properties"]["cycle"]) == wallet.OBLIGATION_CYCLES
    assert enum_of(RESULTS["Obligation"]["properties"]["status"]) == wallet.OBLIGATION_STATUSES
    assert enum_of(RESULTS["Obligation"]["properties"]["source"]) == wallet.OBLIGATION_SOURCES
    assert enum_of(SPEC["paths"]["/obligations"]["get"]["parameters"][1]["schema"]) == (
        *wallet.OBLIGATION_STATUSES,
        "all",
    )


def test_giao_dich_va_nguon_tra():
    assert enum_of(RESULTS["Transaction"]["properties"]["kind"]) == wallet.TRANSACTION_KINDS
    assert enum_of(RESULTS["Transaction"]["properties"]["funding_source"]) == wallet.FUNDING_SOURCES
    assert enum_of(event("transaction.recorded")["funding_source"]) == wallet.FUNDING_SOURCES
    assert enum_of(event("transaction.recorded")["kind"]) == wallet.TRANSACTION_KINDS
    assert (
        enum_of(SCHEMAS["RecordTransactionParams"]["properties"]["funding"])
        == wallet.FUNDING_SOURCES
    )
    assert enum_of(SCHEMAS["RecordTransactionParams"]["properties"]["kind"]) == (
        "expense",
        "income",
    )


def test_luong_va_luat_phan_loai():
    assert enum_of(RESULTS["SalaryEvent"]["properties"]["status"]) == wallet.SALARY_EVENT_STATUSES
    assert (
        enum_of(SCHEMAS["ConfirmSalaryParams"]["properties"]["decision"]) == wallet.SALARY_DECISIONS
    )
    assert enum_of(event("salary.confirmed")["decision"]) == wallet.SALARY_DECISIONS
    assert enum_of(SCHEMAS["AssignJarParams"]["properties"]["remember"]) == wallet.RULE_SCOPES


def test_du_bao():
    assert enum_of(FORECAST_BLOCK["JarStatus"]) == wallet.JAR_STATUSES
    assert enum_of(FORECAST_BLOCK["ConfidenceBand"]) == wallet.CONFIDENCE_BANDS
    assert (
        enum_of(FORECAST_BLOCK["ForecastEvent"]["properties"]["kind"])
        == wallet.FORECAST_EVENT_KINDS
    )
    assert enum_of(event("forecast.updated")["trigger"]) == wallet.FORECAST_TRIGGERS
    assert (
        enum_of(FORECAST_IO["JarSummary"]["properties"]["series_kind"])
        == wallet.FORECAST_SERIES_KINDS
    )
    status_ref = PROACTIVE["ProactiveCardData"]["properties"]["status"]["$ref"]
    assert (
        status_ref == "forecast_timeline.schema.json#/$defs/JarStatus"
    )  # thẻ chủ động dùng cùng đủ/sát/hụt


def test_tool_ghi():
    assert enum_of(SCHEMAS["ToolName"]) == wallet.ACTION_TOOLS
    assert enum_of(CONFIRM_ACTION["ConfirmActionTool"]) == wallet.GENERIC_ACTION_TOOLS
    tool_ref = RECEIPT_ACTION["ReceiptActionData"]["properties"]["tool"]["$ref"]
    assert (
        tool_ref == "confirm_action.schema.json#/$defs/ConfirmActionTool"
    )  # biên nhận dùng chung tập tool
    ledger = {t["name"] for t in load_json(CONTRACTS / "tools" / "ledger.json")}
    planner = {t["name"] for t in load_json(CONTRACTS / "tools" / "planner.json")}
    assert set(wallet.AGENT_WRITE_TOOLS) <= ledger
    assert set(wallet.PLANNER_WRITE_TOOLS) <= planner  # phase 3: schedule_nudge ở target planner
    # tool chỉ có ở màn hình thì KHÔNG được lộ cho agent qua Gateway
    assert not ({"save_jars", "confirm_salary"} & ledger)
    assert set(wallet.ACTION_TOOLS) - set(wallet.AGENT_WRITE_TOOLS) == {
        "save_jars",
        "confirm_salary",
        "schedule_nudge",
    }


def test_so_khoi_mot_nguon_su_that_cho_ma_hu_he_thong_trong_sql():
    sql = (REPO / "db" / "migrations" / "0005_wallet.sql").read_text(encoding="utf-8")
    for role, code in wallet.SYSTEM_JAR_CODES.items():
        assert f"'{code}'" in sql and f"'{role}'" in sql


# --- quy ước toàn dự án -----------------------------------------------------------------------
def walk_properties(node, path=""):
    """Duyệt mọi cặp (đường dẫn, thuộc tính) có tên kết thúc bằng _vnd trong một cây JSON Schema hoặc OpenAPI."""
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            for name, child in props.items():
                if name.endswith("_vnd") and isinstance(child, dict):
                    yield f"{path}.{name}", child
        for key, child in node.items():
            yield from walk_properties(child, f"{path}.{key}")
    elif isinstance(node, list):
        for i, child in enumerate(node):
            yield from walk_properties(child, f"{path}[{i}]")


SCHEMA_FILES = [
    *sorted(CONTRACTS.glob("*/*.schema.json")),
    CONTRACTS / "tools" / "ledger.json",
    CONTRACTS / "tools" / "forecast.json",
    CONTRACTS / "tools" / "knowledge.json",
    CONTRACTS / "tools" / "planner.json",
    CONTRACTS / "tools" / "audit.json",
]
MONEY_REFS = ("Vnd", "VndPositive", "VndSigned")


@pytest.mark.parametrize("path", SCHEMA_FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_moi_truong_vnd_la_so_nguyen(path):
    for where, node in walk_properties(load_json(path)):
        node = node.get("items", node)  # mảng số tiền (ví dụ daily_spend_vnd): kiểm kiểu phần tử
        ref = node.get("$ref", "")
        assert ref.rsplit("/", 1)[-1] in MONEY_REFS or node.get("type") == "integer", (
            f"{path.name}{where}"
        )


def test_moi_truong_vnd_cua_openapi_la_so_nguyen():
    for where, node in walk_properties(SPEC):
        ref = node.get("$ref", "")
        assert ref.rsplit("/", 1)[-1] in MONEY_REFS or node.get("type") == "integer", where


def test_ty_le_khong_dung_phan_tram_o_xac_suat_va_do_phu():
    block = FORECAST_BLOCK["ForecastTimelineData"]["properties"]
    for name in ("p_shortfall", "p_shortfall_se", "coverage"):
        assert block[name]["$ref"].endswith("#/$defs/Ratio"), name  # 0..1, không phải 0..100


BANNED = re.compile(r"ví\s+trả\s+sau|momo|finhealth", re.I)
URL = re.compile(r"https?://\S+")


def test_khong_dung_nhan_cam_trong_hop_dong_va_thu_vien():
    """Master-plan: không 'Ví Trả Sau', 'MoMo', 'FinHealth' trên nhãn hiển thị. Chỉ được xuất hiện trong URL trích nguồn."""
    roots = [
        CONTRACTS,
        REPO / "libs" / "yofina_core" / "src",
        REPO / "ml" / "yofina_ml",
        REPO / "db" / "seed",
    ]
    offenders = []
    for root in roots:
        for path in root.rglob("*"):
            if path.suffix not in {".json", ".yaml", ".py", ".sql"}:
                continue
            text = URL.sub("", path.read_text(encoding="utf-8"))
            if BANNED.search(text):
                offenders.append(str(path.relative_to(REPO)))
    # README.md của contracts/ giải thích quy ước nên được phép nhắc tên cấm; chỉ kiểm file mã và dữ liệu
    assert offenders == []


def test_ma_moi_cua_phase_2_khong_doc_dong_ho_he_thong():
    for rel in (
        "libs/yofina_core/src/yofina_core/wallet.py",
        "libs/yofina_core/src/yofina_core/blocks.py",
    ):
        text = (REPO / rel).read_text(encoding="utf-8")
        assert (
            "date.today(" not in text
            and "datetime.now(" not in text
            and "datetime.utcnow(" not in text
        ), rel
    clock = (REPO / "libs/yofina_core/src/yofina_core/clock.py").read_text(encoding="utf-8")
    assert "date.today(" not in clock and "datetime.now(" not in clock
