"""Hợp đồng phase 5 (hồ sơ hành vi, bản tin, bộ nhớ, trích dẫn biểu phí, xóa dữ liệu, trace): hai khối mới, một tool mới, mười một
endpoint REST mới, migration 0053, bộ đánh giá phase 5. Không có RAG (chủ dự án cắt luồng C ngày 24/11): khối `citation` dựng từ
kết quả `knowledge___get_fee_schedule`.

Phần schema và fixture dùng chung của khối nằm ở test_contracts_blocks.py (BLOCK_TYPES), tool ở test_contracts_tools.py, REST ở
test_contracts_rest.py. File này kiểm thứ chỉ phase 5 có: bất biến liên trường mà JSON Schema (tập con của repo) không diễn đạt được
(Pydantic quyết định), khớp giữa các nơi nói cùng một tập giá trị (schema, Pydantic, wallet, OpenAPI, CHECK của 0053), nhất quán số
trong fixture, kiểm tĩnh migration 0053 (chạy thật ở tests/local_pg), và định dạng evals/*/phase5.jsonl.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
from datetime import UTC, date, datetime

import pytest
import yaml
from conftest import BASE, CONTRACTS, OPENAPI_URI, REPO, load_json
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from test_contracts_blocks import normalize, pydantic_tree

from yofina_core import blocks as b
from yofina_core import memory, privacy, wallet
from yofina_core.blocks import BLOCK_MODELS
from yofina_core.confirm import hash_normalized_params
from yofina_core.errors import HTTP_STATUS, ErrorCode
from yofina_core.ingest import INGEST_TOOLS
from yofina_core.llm import load_settings
from yofina_core.params import ParamsError, normalize_params

SPEC = yaml.safe_load((CONTRACTS / "rest" / "openapi.yaml").read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]
FORECAST = {t["name"]: t for t in load_json(CONTRACTS / "tools" / "forecast.json")}
KNOWLEDGE = {t["name"]: t for t in load_json(CONTRACTS / "tools" / "knowledge.json")}
AUDIT = {t["name"]: t for t in load_json(CONTRACTS / "tools" / "audit.json")}
FIX = CONTRACTS / "fixtures"
KW = dict(
    trace_id="8f3a21c94b7e4d0aa1c25e6f7b8c9d01",
    as_of=datetime(2026, 12, 10, 3, 0, tzinfo=UTC),
    app_date=date(2026, 11, 21),
)
NEW_ERRORS = {"MEMORY_RECORD_NOT_FOUND": 404, "MEMORY_UNAVAILABLE": 503}
NEW_OPS = {
    ("GET", "/profile/behavior"),
    ("GET", "/nudges/today"),
    ("POST", "/nudges/{nudge_id}/feedback"),
    ("GET", "/memory"),
    ("DELETE", "/memory"),
    ("DELETE", "/memory/{record_id}"),
    ("POST", "/me/delete-data/confirmations"),
    ("POST", "/me/delete-data"),
    ("GET", "/ops/traces"),
    ("GET", "/ops/traces/{trace_id}"),
    ("GET", "/ops/summary"),
}
DEL = object()


def fx(rel: str):
    return load_json(FIX / rel)


def edited(obj, *edits):
    out = copy.deepcopy(obj)
    for path, value in edits:
        node = out
        for key in path[:-1]:
            node = node[key]
        if value is DEL:
            del node[path[-1]]
        else:
            node[path[-1]] = value
    return out


def schema_enum(file: str, *path: str) -> tuple[str, ...]:
    node = load_json(CONTRACTS / "blocks" / f"{file}.schema.json")
    for key in path:
        node = node[key]
    return tuple(node["enum"])


def api_validator(registry, name: str) -> Draft202012Validator:
    return Draft202012Validator(
        {"$ref": f"{OPENAPI_URI}#/components/schemas/{name}"}, registry=registry
    )


# =====================================================================================
# Tập giá trị khớp giữa các nơi
# =====================================================================================
def test_tap_gia_tri_khoi_moi_khop_hang_so():
    assert (
        schema_enum("behavior_insight", "$defs", "BehaviorInsightKind")
        == wallet.BEHAVIOR_INSIGHT_KINDS
        == b.BehaviorInsightKind.__args__
    )
    assert (
        schema_enum("behavior_insight", "$defs", "BehaviorEvidence", "properties", "unit")
        == b.EvidenceUnit.__args__
    )
    proactive = load_json(CONTRACTS / "blocks/proactive_card.schema.json")["$defs"]
    kinds = tuple(proactive["ProactiveCardData"]["properties"]["kind"]["enum"])
    assert kinds == b.ProactiveKind.__args__ and set(wallet.NUDGE_GATE_ORDER) <= set(
        kinds
    )  # mọi bản tin của cổng vẽ được thành thẻ
    assert (
        tuple(proactive["ProactiveAction"]["properties"]["kind"]["enum"])
        == b.ProactiveActionKind.__args__
    )
    assert {"open_roadmap", "open_resilience", "open_profile"} <= set(
        b.ProactiveActionKind.__args__
    )


def test_tap_gia_tri_rest_khop_hang_so():
    assert tuple(SCHEMAS["NudgeKind"]["enum"]) == wallet.ALL_NUDGE_KINDS
    assert (
        wallet.ALL_NUDGE_KINDS[: len(wallet.NUDGE_KINDS)] == wallet.NUDGE_KINDS
    )  # loại cũ giữ nguyên thứ tự
    assert not {"roadmap_proposed", "resilience_drop", "behavior_insight"} & set(
        wallet.NUDGE_KINDS
    )  # schedule_nudge không tạo được
    assert tuple(SCHEMAS["NudgeOutcome"]["enum"]) == wallet.NUDGE_OUTCOMES
    reasons = SCHEMAS["NudgeSuppressed"]["properties"]["reason"]["enum"]
    assert tuple(reasons) == wallet.NUDGE_SUPPRESS_REASONS
    assert tuple(SCHEMAS["MemoryKind"]["enum"]) == memory.MEMORY_KINDS == memory.MemoryKind.__args__
    assert tuple(SCHEMAS["MemoryRecord"]["properties"]["source"]["enum"]) == memory.MEMORY_SOURCES
    assert set(memory.MEMORY_SOURCE_OF_KIND) == set(memory.MEMORY_KINDS)
    assert (
        tuple(SCHEMAS["DataDeletion"]["properties"]["status"]["enum"])
        == privacy.DATA_DELETION_STATUSES
    )
    assert (
        tuple(SCHEMAS["DeletionStep"]["properties"]["status"]["enum"])
        == privacy.DELETION_STEP_STATUSES
    )
    assert set(SCHEMAS["DataDeletion"]["properties"]["steps"]["required"]) == set(
        privacy.DATA_DELETION_STEPS
    )
    assert (
        tuple(SCHEMAS["PrivacyToolName"]["enum"])
        == wallet.PRIVACY_ACTION_TOOLS
        == ("delete_my_data",)
    )
    assert (
        tuple(SCHEMAS["DeleteMyDataParams"]["properties"]["scope"]["enum"])
        == wallet.DATA_DELETION_SCOPES
    )


def test_y_dinh_phase5_da_vao_router_va_ban_ghi_luot_nhan():
    # cả bốn ý định phase 5 đã có bộ xử lý (24/11): nằm cuối INTENTS, đúng thứ tự của CHECK trong 0053
    assert wallet.PHASE5_INTENTS == ("behavior", "knowledge", "ingest", "memory")
    assert wallet.INTENTS[10:] == wallet.PHASE5_INTENTS
    assert wallet.AUDIT_INTENTS == (
        *wallet.INTENTS_PHASE4,
        "behavior",
        "knowledge",
        "ingest",
        "memory",
    )  # thứ tự của 0053
    desc = AUDIT["record_turn"]["inputSchema"]["properties"]["intent"]["description"]
    assert all(i in desc for i in wallet.AUDIT_INTENTS)


def test_ma_loi_moi_khop_ba_noi_va_them_cuoi():
    schema = SCHEMAS["ErrorCode"]
    for code, status in NEW_ERRORS.items():
        assert HTTP_STATUS[ErrorCode(code)] == status == schema["x-http-status"][code]
        assert schema["x-meaning"][code]
    # hai mã bộ nhớ liền nhau sau mã phase 4; mã thêm sau (INGEST_NO_TRANSACTIONS, test_contracts_ingest.py) nằm cuối
    first = schema["enum"].index("MEMORY_RECORD_NOT_FOUND")
    assert schema["enum"][first : first + len(NEW_ERRORS)] == list(NEW_ERRORS)
    assert schema["enum"][first - 1] == "SHOCK_NOT_FOUND"
    text = (CONTRACTS / "rest/openapi.yaml").read_text(encoding="utf-8")
    assert "MEMORY_RECORD_NOT_FOUND" in SPEC["components"]["responses"]["NotFound"]["description"]
    assert "MEMORY_UNAVAILABLE" in SPEC["components"]["responses"]["Unavailable"]["description"]
    assert text.count("MEMORY_UNAVAILABLE") >= 3


# =====================================================================================
# Khối behavior_insight, hồ sơ hành vi
# =====================================================================================
PROFILE = fx("tools/get_behavior_profile.ok.json")["data"]


def test_ho_so_cung_mot_data_cho_tool_va_rest():
    assert fx("rest/BehaviorProfileResponse.minh.json") == PROFILE
    assert (
        fx("rest/BehaviorProfileResponse.chua_san_sang.json")
        == fx("tools/get_behavior_profile.ok_chua_san_sang.json")["data"]
    )
    p = b.BehaviorProfileData.model_validate(PROFILE)
    assert (
        p.ready and len(p.insights) >= 2
    )  # tiêu chí 6: minh có ít nhất hai nhận xét kèm bằng chứng
    assert all(i.evidence for i in p.insights)


def test_moi_so_trong_cau_nhan_xet_co_trong_bang_chung():
    """Hợp đồng NumericGrounding của batch đêm: số trong `headline` của nhận xét có trong `evidence` (số tiền theo dạng 1.200.000)."""
    for ins in PROFILE["insights"]:
        values = set()
        for e in ins["evidence"]:
            v = e["value"]
            values |= {
                str(v),
                f"{int(v):,}".replace(",", ".") if v == int(v) else str(v).replace(".", ","),
            }
        nums = re.findall(r"\d[\d.,]*\d|\d", ins["headline"])
        assert nums and all(n in values for n in nums), (ins["insight_id"], nums, values)


def test_khoi_dung_lai_tu_ho_so_bang_builder():
    built = b.block_to_wire(
        b.build_behavior_insight(
            data=b.behavior_insight_data(PROFILE),
            source_tool="forecast___get_behavior_profile",
            **KW,
        )
    )
    assert built == fx("blocks/valid/behavior_insight.chi_don_sau_luong.json")
    assert (
        built["id"] == f"behavior_insight:{KW['trace_id']}:{PROFILE['insights'][0]['insight_id']}"
    )
    assert (
        built["fallback_text"].startswith(PROFILE["insights"][0]["headline"])
        and PROFILE["next_step"]["label"] in built["fallback_text"]
    )
    second = b.behavior_insight_data(PROFILE, "thu_bay_an_uong")
    assert (
        second.insight.jar_code == "an_uong"
        and second.next_step.label == PROFILE["next_step"]["label"]
    )
    with pytest.raises(ValueError):
        b.behavior_insight_data(PROFILE, "khong_co")
    with pytest.raises(ValueError):
        b.behavior_insight_data(fx("tools/get_behavior_profile.ok_chua_san_sang.json")["data"])


@pytest.mark.parametrize(
    ("unit", "value"),
    [
        ("vnd", 1200.5),
        ("vnd", -1),
        ("count", 2.5),
        ("percent", 101),
        ("ratio", 1.2),
        ("hour", 24),
        ("weekday", 0),
        ("weekday", 8),
        ("days", -3),
    ],
)
def test_bang_chung_sai_don_vi_bi_pydantic_tu_choi(unit, value):
    ev = {"key": "x", "label": "x", "value": value, "unit": unit}
    with pytest.raises(ValidationError):
        b.BehaviorEvidence.model_validate(ev)


def test_bat_bien_ho_so_va_nhan_xet():
    ok = b.BehaviorProfileData.model_validate
    with pytest.raises(ValidationError):
        ok(edited(PROFILE, (("next_step",), DEL)))  # sẵn sàng phải có một việc cần làm
    with pytest.raises(ValidationError):
        ok(edited(PROFILE, (("insights",), [])))
    with pytest.raises(ValidationError):
        ok(edited(PROFILE, (("features", "history_days"), 59)))
    with pytest.raises(ValidationError):
        ok(edited(PROFILE, (("insights", 1, "insight_id"), PROFILE["insights"][0]["insight_id"])))
    with pytest.raises(ValidationError):  # chưa sẵn sàng mà có nhận xét
        ok(edited(PROFILE, (("ready",), False), (("min_history_days",), 21)))
    with pytest.raises(ValidationError):  # chưa sẵn sàng phải nói cần bao nhiêu ngày
        ok(
            edited(
                fx("rest/BehaviorProfileResponse.chua_san_sang.json"), (("min_history_days",), DEL)
            )
        )
    ins = PROFILE["insights"][0]
    with pytest.raises(ValidationError):
        b.BehaviorInsight.model_validate(
            edited(ins, (("evidence", 1, "key"), ins["evidence"][0]["key"]))
        )
    with pytest.raises(ValidationError):
        b.BehaviorEvidence.model_validate(
            {**ins["evidence"][0], "period_from": "2026-12-01", "period_to": "2026-11-01"}
        )
    blk = fx("blocks/valid/behavior_insight.thu_bay_chuyen_hu.json")
    with pytest.raises(ValidationError):  # hành động không mang user_id hay token
        b.parse_block(
            edited(blk, (("data", "next_step", "action", "params", "user_id"), "sub-khac"))
        )
    assert blk["data"]["next_step"]["action"]["tool"] in wallet.ROADMAP_STEP_ACTION_TOOLS


def test_hanh_dong_cua_viec_can_lam_dan_toi_tool_ghi_co_san():
    """Một đường ghi (ADR-0002): action của việc cần làm là tool ghi đã có, chuẩn hóa được bằng `normalize_params`."""
    for name in ("behavior_insight.chi_don_sau_luong", "behavior_insight.thu_bay_chuyen_hu"):
        action = fx(f"blocks/valid/{name}.json")["data"]["next_step"]["action"]
        assert action["tool"] in wallet.ACTION_TOOLS
        if action["tool"] == "move_between_jars":
            assert normalize_params(action["tool"], action["params"]) == action["params"]


# =====================================================================================
# Khối citation: dựng từ kết quả knowledge___get_fee_schedule (không có RAG)
# =====================================================================================
FEES = fx("tools/get_fee_schedule.ok.json")
FEES_TWO = fx("tools/get_fee_schedule.ok_hai_nguon.json")
CITATION = load_json(CONTRACTS / "blocks/citation.schema.json")
FEE_RESULTS = load_json(CONTRACTS / "tools/knowledge.results.schema.json")["$defs"]


def test_trich_dan_dung_tu_ket_qua_get_fee_schedule():
    built = b.block_to_wire(b.build_citation(result=FEES, trace_id=KW["trace_id"]))
    assert built == fx("blocks/valid/citation.phi_tra_sau.json")
    assert built["id"] == f"citation:{KW['trace_id']}"
    assert built["source"] == {
        "tool": "knowledge___get_fee_schedule",
        "as_of": FEES["as_of"],
        "app_date": FEES["app_date"],
    }
    fee = FEES["data"]["fees"][0]
    item = built["data"]["items"][0]
    assert (item["source_name"], item["source_url"], item["effective_from"]) == (
        fee["source_name"],
        fee["source_url"],
        fee["effective_from"],
    )
    assert (
        item["fee_types"] == [fee["fee_type"]] and item["excerpt"] == fee["condition_note"]
    )  # câu trích chép từ bảng, không do model viết
    assert (built["data"]["product_code"], built["data"]["product_label"]) == (
        FEES["data"]["product_code"],
        FEES["data"]["product_label"],
    )
    assert (
        built["fallback_text"]
        == f"Nguồn biểu phí Trả sau (mô phỏng): {fee['source_name']}, hiệu lực từ 31/03/2026."
    )
    assert "33.000" not in json.dumps(
        built, ensure_ascii=False
    )  # khối không mang số tiền: số nói ra lấy từ amount_vnd
    two = b.block_to_wire(b.build_citation(result=FEES_TWO, trace_id=KW["trace_id"]))
    assert two == fx("blocks/valid/citation.nhieu_nguon.json")
    assert [i["fee_types"] for i in two["data"]["items"]] == [
        [f["fee_type"]] for f in FEES_TWO["data"]["fees"]
    ]


def test_trich_dan_loc_theo_loai_phi_va_gom_theo_nguon():
    late = b.build_citation(
        result=FEES_TWO, trace_id=KW["trace_id"], fee_types=["late_payment_fee"]
    )
    assert [i.fee_types for i in late.data.items] == [["late_payment_fee"]]
    assert late.data.items[0].source_url == FEES_TWO["data"]["fees"][1]["source_url"]
    for bad in (["khong_co"], [], ["monthly_service_fee", "khong_co"]):
        with pytest.raises(ValueError):  # không trích dẫn phí mà tool không trả
            b.citation_data(FEES_TWO["data"], bad)
    same = edited(
        FEES_TWO,
        *(
            (("data", "fees", 1, k), FEES_TWO["data"]["fees"][0][k])
            for k in ("source_name", "source_url", "effective_from")
        ),
    )
    grouped = b.citation_data(same["data"])
    assert len(grouped.items) == 1 and grouped.items[0].fee_types == [
        "monthly_service_fee",
        "late_payment_fee",
    ]
    assert (
        grouped.items[0].excerpt is None
    )  # nhiều loại phí chung một nguồn thì không chọn câu trích nào
    with pytest.raises(ValidationError):  # kết quả lỗi của tool không dựng được khối
        b.build_citation(
            result=fx("tools/get_fee_schedule.error_not_found.json"), trace_id=KW["trace_id"]
        )


def test_bat_bien_trich_dan():
    item = fx("blocks/valid/citation.phi_tra_sau.json")["data"]["items"][0]
    data = {"product_code": "bnpl_sim", "product_label": "Trả sau (mô phỏng)"}
    b.CitationData.model_validate({**data, "items": [item]})
    with pytest.raises(ValidationError):  # cùng một nguồn hai mục
        b.CitationData.model_validate(
            {**data, "items": [item, {**item, "fee_types": ["late_payment_fee"]}]}
        )
    with pytest.raises(ValidationError):  # một loại phí ở hai nguồn
        b.CitationData.model_validate(
            {**data, "items": [item, {**item, "source_url": "https://example.invalid/khac"}]}
        )
    with pytest.raises(ValidationError):
        b.CitationData.model_validate(
            {
                **data,
                "items": [
                    {**item, "source_url": f"https://example.invalid/{n}", "fee_types": [f"f{n}"]}
                    for n in range(6)
                ],
            }
        )


def test_khoi_trich_dan_chi_co_truong_cua_bang_phi():
    """Khối không còn trường chỉ có nghĩa với tìm kiếm tài liệu (điểm, chunk, kho, câu truy vấn); trường nguồn cùng giới hạn với `FeeLine`."""
    defs = CITATION["$defs"]
    assert set(defs) == {"CitationItem", "CitationData"}
    assert set(defs["CitationItem"]["properties"]) == {
        "fee_types",
        "source_name",
        "source_url",
        "effective_from",
        "excerpt",
    }
    assert defs["CitationItem"]["required"] == [
        "fee_types",
        "source_name",
        "source_url",
        "effective_from",
    ]
    assert set(defs["CitationData"]["properties"]) == {"product_code", "product_label", "items"}
    fee_line = FEE_RESULTS["FeeLine"]["properties"]
    item = defs["CitationItem"]["properties"]
    assert item["fee_types"]["items"]["pattern"] == fee_line["fee_type"]["pattern"]
    assert item["source_name"]["maxLength"] == fee_line["source_name"]["maxLength"]
    assert item["source_url"]["pattern"] == fee_line["source_url"]["pattern"]
    assert item["excerpt"]["maxLength"] == fee_line["condition_note"]["maxLength"]
    assert (
        defs["CitationData"]["properties"]["product_code"]
        == FEE_RESULTS["FeeScheduleData"]["properties"]["product_code"]
    )
    text = json.dumps(CITATION, ensure_ascii=False)
    assert (
        "knowledge___get_fee_schedule" in text
        and "knowledge___search" not in text
        and "kb_" not in text
    )


@pytest.mark.parametrize("name", ["FeeLine", "FeeScheduleData", "GetFeeScheduleOk"])
def test_ket_qua_get_fee_schedule_pydantic_khop_json_schema(registry, name):
    hit = registry.resolver(base_uri=f"{BASE}/tools/").lookup(
        f"knowledge.results.schema.json#/$defs/{name}"
    )
    assert pydantic_tree(getattr(b, name)) == normalize(hit.contents, hit.resolver)


def test_rag_da_cat_khoi_hop_dong():
    """Chủ dự án cắt luồng C (RAG) ngày 24/11: không tool tìm kiếm, không fixture, không module, không bảng hay hàm trong 0053."""
    # target `knowledge` chỉ có tool đọc bảng có cấu trúc (biểu phí, tỷ giá) và tính ngày (#39), không có tool tìm kiếm tài liệu
    assert list(KNOWLEDGE) == ["get_fee_schedule", "get_exchange_rate", "resolve_date"] == list(wallet.KNOWLEDGE_TOOLS)
    assert not {k for k in FEE_RESULTS if k.startswith("Knowledge")}
    assert not list((FIX / "tools").glob("**/search.*.json"))
    assert importlib.util.find_spec("yofina_core.knowledge") is None
    assert "search" not in wallet.PHASE5_TOOLS


# =====================================================================================
# Tool
# =====================================================================================
def test_tool_moi_o_cuoi_target_va_chua_cai():
    assert wallet.FORECAST_TOOLS[-1] == "get_behavior_profile"
    # luồng p5-behavior đã cài `get_behavior_profile` (yofina_forecast.behavior) nên không còn tool phase 5 nào chưa cài
    assert "get_behavior_profile" not in wallet.PHASE5_TOOLS and set(wallet.PHASE5_TOOLS) == set(
        wallet.PHASE4_TOOLS
    )
    assert len("forecast___get_behavior_profile") <= 64


def test_tool_doc_khong_token_va_mo_ta_noi_ro_gioi_han():
    prof = FORECAST["get_behavior_profile"]
    assert "confirm_token" not in prof["inputSchema"]["properties"]
    assert "không ghi gì" in prof["description"]
    assert "required" not in prof["inputSchema"]
    for kind in wallet.BEHAVIOR_INSIGHT_KINDS:
        assert kind in prof["inputSchema"]["properties"]["insight_kind"]["description"]
    assert "KHÔNG tự bịa" in prof["description"] and "evidence" in prof["description"]
    # trích dẫn đọc nguồn từ get_fee_schedule: mô tả tool nói rõ nó trả tên nguồn, đường dẫn và ngày hiệu lực
    fee = KNOWLEDGE["get_fee_schedule"]["description"]
    assert "tên nguồn" in fee and "đường dẫn nguồn" in fee and "ngày hiệu lực" in fee


def test_cedar_cua_tool_phase5_neu_co_thi_dung_dang():
    """Luồng cài tool thêm `gateway/policies/<tool>.cedar` (CDK bắt buộc khi deploy YofinaAgent); hợp đồng không viết Cedar."""
    for target, name in (("forecast", "get_behavior_profile"),):
        path = REPO / "gateway" / "policies" / f"{name}.cedar"
        if path.exists():
            code = path.read_text(encoding="utf-8")
            assert f'action == AgentCore::Action::"{target}___{name}"' in code
            assert (
                "context.input has user_id && context.input.user_id == principal.id" in code
                and "confirm_token" not in code
            )


def test_buoc_goi_tool_trong_ban_ghi_luot():
    step = load_json(CONTRACTS / "tools/audit.results.schema.json")["$defs"]["TraceStep"]
    assert step["required"] == ["step", "ms"] and {"status", "code"} <= set(
        step["properties"]
    )  # tương thích ngược
    assert tuple(step["properties"]["status"]["enum"]) == ("ok", "error", "denied")
    assert re.fullmatch(step["properties"]["step"]["pattern"], "forecast___get_behavior_profile")
    item = AUDIT["record_turn"]["inputSchema"]["properties"]["step_timings"]["items"]
    assert {"status", "code"} <= set(item["properties"]) and item["required"] == ["step", "ms"]


# =====================================================================================
# REST
# =====================================================================================
def operations():
    return {(m.upper(), p) for p, item in SPEC["paths"].items() for m in item if m != "parameters"}


def op(method: str, path: str):
    return SPEC["paths"][path][method.lower()]


def test_muoi_mot_endpoint_moi_va_lambda_phuc_vu():
    assert operations() >= NEW_OPS
    assert op("GET", "/profile/behavior")["x-lambda"] == "forecast"
    for m, p in NEW_OPS - {("GET", "/profile/behavior")}:
        assert op(m, p)["x-lambda"] == "ledger", (m, p)
    assert {m for m, _ in operations()} == {
        "GET",
        "POST",
        "DELETE",
    }  # không PATCH; DELETE mới ở phase 5 (CORS phải cho thêm)
    assert "DELETE" in SPEC["info"]["description"] and "CORS" in SPEC["info"]["description"]


def test_ops_chi_nhom_ops_va_khong_lo_danh_tinh():
    ops = {p for _, p in operations() if p.startswith("/ops/")}
    assert ops == {"/ops/traces", "/ops/traces/{trace_id}", "/ops/summary"}
    for p in ops:
        o = op("GET", p)
        assert o["x-required-group"] == "ops" and "403" in o["responses"]
    assert not any(
        "x-required-group" in o
        for p, item in SPEC["paths"].items()
        if not p.startswith("/ops/")
        for o in item.values()
    )

    def names(schema, seen=()):
        if isinstance(schema, dict):
            if "$ref" in schema and schema["$ref"].startswith("#/components/schemas/"):
                key = schema["$ref"].rsplit("/", 1)[1]
                if key not in seen:
                    yield from names(SCHEMAS[key], (*seen, key))
            for k, v in schema.get("properties", {}).items():
                yield k
                yield from names(v, seen)
            for v in schema.values():
                if isinstance(v, (dict, list)) and v is not schema.get("properties"):
                    yield from names(v, seen)
        elif isinstance(schema, list):
            for v in schema:
                yield from names(v, seen)

    for s in ("OpsTraceListResponse", "OpsTraceDetail", "OpsSummaryResponse"):
        fields = set(names(SCHEMAS[s]))
        assert not fields & {
            "user_id",
            "conversation_id",
            "user_text",
            "assistant_text",
            "sub",
            "email",
        }, s
    assert re.fullmatch(SCHEMAS["UserRef"]["pattern"], "3f9a0c1d2e4b")
    assert SCHEMAS["OpsTraceDetail"]["properties"]["pii_masked"] == {"const": True}


def test_xoa_du_lieu_qua_token_xoa_bo_nho_va_phan_hoi_ban_tin_thi_khong():
    dd = op("POST", "/me/delete-data")
    assert {"403", "409", "428"} <= set(dd["responses"])
    assert SCHEMAS["DeleteDataRequest"]["required"] == [
        "tool",
        "params",
    ]  # token tùy chọn: vắng thì 428 do code quyết định
    assert "confirm_token" in SCHEMAS["DeleteDataRequest"]["properties"]
    assert (
        "user_id" not in SCHEMAS["DeleteDataRequest"]["properties"]
        and SCHEMAS["DeleteDataRequest"]["additionalProperties"] is False
    )
    conf = op("POST", "/me/delete-data/confirmations")
    assert conf["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ConfirmationResponse"
    }
    tool_of = SCHEMAS["ConfirmationResponse"]["properties"]["tool"]["anyOf"]
    assert {"$ref": "#/components/schemas/PrivacyToolName"} in tool_of
    assert (
        wallet.DELETE_MY_DATA not in wallet.ACTION_TOOLS
        and wallet.DELETE_MY_DATA not in wallet.GENERIC_ACTION_TOOLS
    )
    assert wallet.DELETE_MY_DATA not in SCHEMAS["ToolName"]["enum"]
    for m, p in (
        ("POST", "/nudges/{nudge_id}/feedback"),
        ("DELETE", "/memory"),
        ("DELETE", "/memory/{record_id}"),
    ):
        assert "428" not in op(m, p)["responses"], (m, p)
        assert "token" in op(m, p)["description"]


def test_chuan_hoa_delete_my_data_idempotent_va_hash_cua_fixture():
    assert normalize_params("delete_my_data", {}) == {"scope": "all"}
    assert normalize_params("delete_my_data", {"scope": " all ", "user_id": "x"}) == {
        "scope": "all"
    }
    n = normalize_params("delete_my_data", {"scope": "all"})
    assert normalize_params("delete_my_data", n) == n
    with pytest.raises(ParamsError):
        normalize_params("delete_my_data", {"scope": "transactions"})
    resp = fx("rest/ConfirmationResponse.delete_my_data.json")
    assert resp["tool"] == "delete_my_data" and resp["params_hash"] == hash_normalized_params(
        "delete_my_data", resp["params"]
    )
    assert fx("rest/DeleteDataRequest.co_token.json")["params"] == resp["params"]


def test_ban_tin_va_the_chu_dong_di_cung_nhau():
    full = fx("rest/NudgeTodayResponse.co_ban_tin.json")
    nudge, card = full["nudge"], full["card"]
    assert b.parse_block(card).data.nudge_id == nudge["nudge_id"]
    assert (card["data"]["kind"], card["data"]["title"], card["data"]["reason"]) == (
        nudge["kind"],
        nudge["title"],
        nudge["reason"],
    )
    assert nudge["kind"] in wallet.NUDGE_GATE_ORDER
    assert nudge["gate"]["score"] > nudge["gate"]["threshold"]  # chỉ chọn khi vượt ngưỡng
    assert nudge["gate"]["rank"] == wallet.NUDGE_GATE_ORDER.index(nudge["kind"]) + 1
    assert {a["kind"] for a in card["data"]["actions"]} >= {"snooze", "mute_kind"}
    assert card == fx("blocks/valid/proactive_card.ban_tin_lo_trinh.json")
    empty = fx("rest/NudgeTodayResponse.trong.json")
    assert "nudge" not in empty and "card" not in empty


def test_ops_fixture_nhat_quan():
    d = fx("rest/OpsTraceDetail.what_if.json")
    tools = [s for s in d["steps"] if "___" in s["step"]]
    assert [f"{c['target']}___{c['tool']}" for c in d["tool_calls"]] == [s["step"] for s in tools]
    assert all(
        c["status"] == s["status"] and c["ms"] == s["ms"]
        for c, s in zip(d["tool_calls"], tools, strict=True)
    )
    assert {c["target"] for c in d["tool_calls"]} <= {
        "ledger",
        "forecast",
        "knowledge",
        "planner",
        "audit",
        "ingest",
    }
    trace = fx("rest/TraceResponse.what_if.json")
    assert (
        d["trace_id"] == trace["trace_id"]
        and d["rules_checked"] == trace["explain"]["data"]["rules_checked"]
    )
    lst = fx("rest/OpsTraceListResponse.default.json")["traces"]
    assert (
        lst[0]["tool_calls"] == len(d["tool_calls"]) and lst[0]["est_cost_vnd"] == d["est_cost_vnd"]
    )
    s = fx("rest/OpsSummaryResponse.default.json")
    assert s["tool_error_rate"] == pytest.approx(s["tool_errors"] / s["tool_calls"], abs=1e-4)
    assert s["latency_ms"]["p50"] <= s["latency_ms"]["p95"]
    assert all(day["model_calls"] <= day["cap"] for day in s["model_calls_by_day"])
    # trần tính theo từng model: tổng của `by_model` bằng số của ngày, mỗi model không quá trần của chính nó, `cap` của ngày là tổng trần
    llm = load_settings(env={})
    caps: dict[str, int] = {}
    for specs in llm.roles.values():
        for m in specs:
            caps[m.id] = max(caps.get(m.id, 0), m.daily_cap)
    for day in s["model_calls_by_day"]:
        models = [m["model"] for m in day["by_model"]]
        assert models == sorted(models) and set(models) <= set(caps)
        assert sum(m["model_calls"] for m in day["by_model"]) == day["model_calls"]
        assert all(
            m["cap"] == caps[m["model"]] and m["model_calls"] <= m["cap"] for m in day["by_model"]
        )
        assert day["cap"] == sum(caps.values())
    assert "latency_ms" not in fx("rest/OpsSummaryResponse.khong_co_luot.json")


# =====================================================================================
# Bộ nhớ và xóa dữ liệu (Python)
# =====================================================================================
SUB = "0b1f9c3e-5a7d-4e21-9f3a-6c1d2e8b4a70"
# mẫu namespace của AgentCore Memory (ListMemoryRecords, DeleteMemoryRecord)
NS_RE = re.compile(r"[a-zA-Z0-9/*][a-zA-Z0-9-_/*]*(?::[a-zA-Z0-9-_/*]+)*[a-zA-Z0-9-_/*]*")


def test_namespace_theo_nguoi_dung_dung_mau_agentcore():
    root = memory.user_root(SUB)
    assert root == f"/yofina/users/{SUB}/" and NS_RE.fullmatch(root)
    for kind, template in memory.MEMORY_NAMESPACE_TEMPLATES.items():
        assert template.startswith(memory.MEMORY_ROOT_TEMPLATE) and template.endswith("/")
        ns = memory.namespace_for(kind, SUB, "sess-1" if "{sessionId}" in template else None)
        assert NS_RE.fullmatch(ns) and ns.startswith(root)
        assert memory.kind_of_namespace(ns, SUB) == kind
    other = memory.namespace_for("preference", "sub-khac")
    assert (
        memory.kind_of_namespace(other, SUB) is None
    )  # bản ghi của người khác không bao giờ được trả hay xóa
    assert (
        memory.kind_of_namespace(f"/yofina/users/{SUB}x/preferences/", SUB) is None
    )  # không trùng tiền tố
    assert memory.kind_of_namespace(f"{root}lạ/", SUB) is None
    for bad in ("", "a/b", "a:b", "../x", "x" * 129):
        with pytest.raises(ValueError):
            memory.user_root(bad)
    with pytest.raises(ValueError):
        memory.namespace_for("session_summary", SUB)
    with pytest.raises(ValueError):
        memory.namespace_for("preference", SUB, "sess-1")


@pytest.mark.parametrize(
    ("model", "schema"),
    [
        (memory.MemoryRecord, "MemoryRecord"),
        (memory.MemoryListResponse, "MemoryListResponse"),
        (memory.MemoryRecordDeleteResponse, "MemoryRecordDeleteResponse"),
        (memory.MemoryClearResponse, "MemoryClearResponse"),
        (privacy.DataDeletion, "DataDeletion"),
    ],
)
def test_model_pydantic_khop_openapi(registry, model, schema):
    hit = registry.resolver(base_uri=OPENAPI_URI).lookup(f"#/components/schemas/{schema}")
    assert pydantic_tree(model) == normalize(hit.contents, hit.resolver)


def test_fixture_rest_moi_qua_pydantic_va_bat_bien_lan_xoa():
    memory.MemoryListResponse.model_validate(fx("rest/MemoryListResponse.minh.json"))
    assert {r["kind"] for r in fx("rest/MemoryListResponse.minh.json")["records"]} == set(
        memory.MEMORY_KINDS
    )
    for r in fx("rest/MemoryListResponse.minh.json")["records"]:
        assert memory.MEMORY_SOURCE_OF_KIND[r["kind"]] == r["source"]
        assert not re.search(
            r"\d{4,}|₫", r["text"]
        )  # không số dư, không giao dịch thô, không số tài khoản
    done = privacy.DataDeletion.model_validate(fx("rest/DataDeletion.done.json"))
    part = privacy.DataDeletion.model_validate(fx("rest/DataDeletion.partial.json"))
    assert done.status == "done" and part.status == "partial"
    ok = fx("rest/DataDeletion.done.json")
    for edits in (
        ((("status",), "running"),),  # đã có finished_at
        ((("status",), "failed"),),  # Aurora không lỗi
        ((("steps", "memory", "status"), "failed"),),  # failed thiếu error_code
        ((("steps", "aurora", "deleted"), DEL),),  # done thiếu số
        ((("status",), "running"), (("finished_at",), DEL)),  # running mà không còn bước pending
    ):
        with pytest.raises(ValidationError):
            privacy.DataDeletion.model_validate(edited(ok, *edits))
    running = edited(
        ok,
        (("status",), "running"),
        (("finished_at",), DEL),
        (("steps", "aurora"), {"status": "pending"}),
    )
    assert privacy.DataDeletion.model_validate(running).status == "running"


# =====================================================================================
# Migration 0053 (kiểm tĩnh; chạy thật trên PostgreSQL cục bộ)
# =====================================================================================
_spec = importlib.util.spec_from_file_location(
    "migrator_sqlsplit5", REPO / "infra-cdk" / "lambdas" / "migrator" / "sqlsplit.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
SQL = (REPO / "db/migrations/0053_phase5.sql").read_text(encoding="utf-8")
STATEMENTS = _mod.split_migration(SQL)
FUNCS = {
    re.search(r"FUNCTION (\w+)\(", s).group(1): s
    for s in STATEMENTS
    if s.startswith("CREATE OR REPLACE FUNCTION")
}
DEFINERS = {
    "app_delete_user_data",
    "app_ops_list_traces",
    "app_ops_get_trace",
    "app_ops_summary",
    "app_ops_model_calls_by_day",
}
SIGNATURES = {
    "app_get_behavior_profile": "text, date",
    "app_get_today_nudge": "text, date",
    "app_nudge_outcome_stats": "text, date",
    "app_set_nudge_outcome": "text, uuid, text",
    "app_delete_user_data": "text, uuid",
    "app_ops_list_traces": "timestamptz, timestamptz, text, text, integer, timestamptz, text, integer",
    "app_ops_get_trace": "text",
    "app_ops_summary": "timestamptz, timestamptz",
    "app_ops_model_calls_by_day": "timestamptz, timestamptz",
}


def sql_set(statement: str, column: str) -> tuple[str, ...]:
    m = re.search(rf"{column}\s+IN\s*\(([^)]*)\)", statement)
    assert m, f"không thấy CHECK IN của {column}"
    return tuple(re.findall(r"'([^']*)'", m.group(1)))


def table(name: str) -> str:
    return next(s for s in STATEMENTS if s.startswith(f"CREATE TABLE IF NOT EXISTS {name} "))


def test_0053_tach_duoc_viet_lai_duoc_va_khong_tham_so():
    assert STATEMENTS[0].startswith(
        "CREATE TABLE IF NOT EXISTS behavior_profiles "
    )  # không còn CREATE EXTENSION vector của RAG
    assert all(not _mod.named_params(s) for s in STATEMENTS)
    assert not re.search(r"(?<![:\w]):[A-Za-z_]", SQL)
    assert not re.search(r"ALTER\s+ROLE|PASSWORD\s+'|DROP\s+TABLE|TRUNCATE", SQL, re.I)
    for s in STATEMENTS:
        if s.startswith("CREATE TABLE"):
            assert "IF NOT EXISTS" in s.split("(")[0]
        if s.startswith(("CREATE INDEX", "CREATE UNIQUE INDEX")):
            assert "IF NOT EXISTS" in s.split(" ON ")[0]
        if "ADD COLUMN" in s:
            assert "ADD COLUMN IF NOT EXISTS" in s
        if " ADD CONSTRAINT " in s:
            name = re.search(r"ADD CONSTRAINT (\w+)", s).group(1)
            assert any(x.endswith(f"DROP CONSTRAINT IF EXISTS {name}") for x in STATEMENTS), name
    names = sorted(p.name for p in (REPO / "db/migrations").glob("*.sql"))
    # 0053 là migration cuối của phase 5 lúc đóng hợp đồng; mỗi migration sau nó (0054 ngoại tệ khi nạp, 0055 ngày cạn của hũ
    # thưa...) có test tĩnh riêng test_migration_<số>.py
    later = names[names.index("0053_phase5.sql") + 1 :]
    assert all((REPO / "tests/unit" / f"test_migration_{n[:4]}.py").exists() for n in later), later


def test_0053_ham_quyen_va_security():
    assert set(FUNCS) == set(SIGNATURES)
    for name, f in FUNCS.items():
        assert f.count("$$") == 2 and "SET search_path = public, pg_temp" in f, name
        assert ("SECURITY DEFINER" in f) == (name in DEFINERS), name
        if name not in DEFINERS:
            assert "SECURITY INVOKER" in f
        if "p_user_id" in f:
            assert "PERFORM set_config('app.user_id', p_user_id, true);" in f, name
        assert "LIMIT" in f or name in ("app_delete_user_data", "app_set_nudge_outcome"), (
            name
        )  # hai hàm ghi theo khóa
        assert f"REVOKE ALL ON FUNCTION {name}({SIGNATURES[name]}) FROM PUBLIC" in STATEMENTS
        assert f"GRANT EXECUTE ON FUNCTION {name}({SIGNATURES[name]}) TO yofina_app" in STATEMENTS
    for name in DEFINERS - {
        "app_delete_user_data"
    }:  # bảng vận hành: không trả user_id hay conversation_id
        returns = re.search(r"RETURNS TABLE \((.*?)\)\s*LANGUAGE", FUNCS[name], re.S).group(1)
        assert "user_id" not in returns and "conversation_id" not in returns, name
    for name in ("app_ops_list_traces", "app_ops_get_trace"):
        assert "left(encode(sha256(convert_to(a.user_id, 'UTF8')), 'hex'), 12)" in FUNCS[name]
    delete = FUNCS["app_delete_user_data"]
    assert (
        "x.status = 'running'" in delete
        and "DELETE FROM audit_events" in delete
        and "DELETE FROM users" in delete
    )
    assert "information_schema.columns" in delete and "<> 'data_deletions'" in delete


def test_0053_rls_va_quyen_toi_thieu():
    expected = "user_id = current_setting('app.user_id', true)"
    for t in ("behavior_profiles", "data_deletions"):
        assert (
            f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY" in STATEMENTS
            and f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY" in STATEMENTS
        )
        pol = next(s for s in STATEMENTS if s.startswith(f"CREATE POLICY user_isolation ON {t}"))
        assert f"USING ({expected})" in pol and f"WITH CHECK ({expected})" in pol
    assert re.search(
        r"user_id\s+text NOT NULL REFERENCES users \(id\) ON DELETE CASCADE",
        table("behavior_profiles"),
    )
    assert "REFERENCES users" not in table("data_deletions")  # nhật ký sống lâu hơn dòng users
    assert (
        "GRANT SELECT, INSERT, UPDATE ON data_deletions TO yofina_app" in STATEMENTS
    )  # không DELETE


def test_0053_khong_con_kho_tri_thuc():
    """RAG đã cắt (24/11): không bảng kb_*, không hàm app_kb_search, không vector hay tsvector; migration chưa chạy ở đâu nên sửa thẳng."""
    assert not re.search(r"\bkb_|app_kb_search|vector\(|tsvector|USING hnsw|CREATE EXTENSION", SQL)
    tables = {
        re.match(r"CREATE TABLE IF NOT EXISTS (\w+)", s).group(1)
        for s in STATEMENTS
        if s.startswith("CREATE TABLE")
    }
    assert tables == {"behavior_profiles", "data_deletions"}


def test_0053_tap_gia_tri_khop_hang_so():

    assert sql_set(table("behavior_profiles"), "source") == wallet.BEHAVIOR_PROFILE_SOURCES
    assert sql_set(table("data_deletions"), "status") == privacy.DATA_DELETION_STATUSES
    assert sql_set(table("data_deletions"), "scope") == wallet.DATA_DELETION_SCOPES
    kind = next(
        s for s in STATEMENTS if s.startswith("ALTER TABLE nudges ADD CONSTRAINT nudges_kind_check")
    )
    assert sql_set(kind, "kind") == wallet.ALL_NUDGE_KINDS
    outcome = next(s for s in STATEMENTS if "ADD COLUMN IF NOT EXISTS outcome text" in s)
    assert sql_set(outcome, "outcome") == wallet.NUDGE_OUTCOMES
    intent = next(
        s
        for s in STATEMENTS
        if s.startswith("ALTER TABLE audit_events ADD CONSTRAINT audit_events_intent_check")
    )
    assert sql_set(intent, "intent") == wallet.AUDIT_INTENTS
    assert (
        "ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS audit_events_intent_check" in STATEMENTS
    )
    fire = next(
        s
        for s in STATEMENTS
        if s.startswith("ALTER TABLE nudges ADD CONSTRAINT nudges_fire_on_check")
    )
    assert "source = 'system' AND fire_on = created_app_date" in fire
    assert any(
        "nudges_system_one_per_day_idx" in s and "WHERE source = 'system'" in s for s in STATEMENTS
    )
    assert "jsonb_array_length(insights) <= 6" in table("behavior_profiles")


# =====================================================================================
# Bộ đánh giá phase 5
# =====================================================================================
def load_suite(name: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (REPO / "evals" / name / "phase5.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]


ALL_TOOLS = set(
    wallet.LEDGER_TOOLS
    + wallet.FORECAST_TOOLS
    + wallet.KNOWLEDGE_TOOLS
    + wallet.PLANNER_TOOLS
    + wallet.AUDIT_TOOLS
    + tuple(INGEST_TOOLS)
)


@pytest.mark.parametrize(("suite", "minimum"), [("golden", 10), ("adversarial", 10)])
def test_dinh_dang_bo_danh_gia_phase5(suite, minimum):
    cases = load_suite(suite)
    assert len(cases) >= minimum and len({c["id"] for c in cases}) == len(cases)
    for c in cases:
        assert c["question"].strip(), c["id"]
        if "intent" in c:
            assert c["intent"] in wallet.AUDIT_INTENTS, c["id"]
        assert set(c.get("tools_must", [])) <= ALL_TOOLS, c["id"]
        assert {t.removesuffix(":token") for t in c.get("tools_forbid", [])} <= ALL_TOOLS, c["id"]
        assert set(c.get("blocks_must", [])) <= BLOCK_MODELS.keys(), c["id"]
        for session in c.get("prior_sessions", []):
            assert [m["role"] for m in session] == ["user", "assistant"][: len(session)] and all(
                m["content"].strip() for m in session
            )


def test_golden_phase5_du_nhom_cua_file_phase():
    cases = load_suite("golden")
    cats = {c["category"] for c in cases}
    assert {
        "behavior",
        "memory_reuse",
        "knowledge_fee",
        "ingest_status",
    } <= cats  # thói quen, sở thích phiên trước, biểu phí, nạp
    assert {c["intent"] for c in cases if "intent" in c} >= set(wallet.PHASE5_INTENTS)
    reuse = [c for c in cases if c["category"] == "memory_reuse"]
    assert reuse and all(c["prior_sessions"] and c["forbid_reask"] for c in reuse)
    fee = next(c for c in cases if c["id"] == "knowledge-fee-citation")
    assert fee["tools_must"] == ["get_fee_schedule"] and "citation" in fee["blocks_must"]
    for c in cases:
        if "citation" in c.get("blocks_must", []):  # trích dẫn chỉ dựng từ get_fee_schedule
            assert "get_fee_schedule" in c["tools_must"], c["id"]
        if "expect_citation_fee_types" in c:
            assert "citation" in c["blocks_must"], c["id"]
        if "expect_insight_kind" in c:
            assert c["expect_insight_kind"] in wallet.BEHAVIOR_INSIGHT_KINDS


def test_adversarial_phase5_du_ca_va_tham_chieu_tep_that():
    cases = load_suite("adversarial")
    attacks = [c["attack"] for c in cases]
    for kind in ("file_injection", "pii_other_person", "other_user_memory", "prompt_injection"):
        assert kind in attacks, kind
    manifest = {i["id"]: i for i in load_json(REPO / "evals/ingest/manifest.json")["items"]}
    files = [c for c in cases if "upload_manifest_id" in c]
    assert len(files) >= 5
    for c in files:
        item = manifest[c["upload_manifest_id"]]
        assert (REPO / "evals/ingest" / item["file"]).exists(), c["id"]
        if c["attack"] == "file_injection":
            assert c["forbid_auto_add_from_file"] and c["forbid_write_without_confirm"]
            assert item["expected"]["attack"] or item["expected"].get("rejected_rows"), c["id"]
        if c["attack"] == "pii_other_person":
            assert item["expected"].get("pii") and c["forbid_pii_from_manifest"]
    assert all(
        c.get("forbid_other_user_data")
        for c in cases
        if c["attack"] in ("other_user_memory", "other_user_data")
    )
