"""Hợp đồng khối UI: JSON Schema <-> Pydantic <-> fixture dùng chung với test TypeScript."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime

import pytest
from conftest import BASE, CONTRACTS, REPO, fixture_files, load_json
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from yofina_core import blocks as b
from yofina_core.confirm import canonical_json, hash_normalized_params, params_hash

BLOCK_TYPES = [
    "jar_summary",
    "confirm",
    "receipt",
    "notice",
    "forecast_timeline",
    "proactive_card",
    "confirm_action",
    "receipt_action",
    # phase 3
    "affordability_card",
    "obligation_impact",
    "options",
    "explain",
    "clarify",
    "suggestions",
    # phase 5 (F6)
    "ingest_review",
    "coverage_change",
    # phase 4
    "resilience_score",
    "stress_result",
    "roadmap",
    "roadmap_diff",
    "review_list",
]
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


def test_union_dung_hai_muoi_mot_khoi_theo_thu_tu():
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
    elif obj["type"] == "confirm_action":
        d = obj["data"]
        digest = hashlib.sha256(
            canonical_json({"tool": d["tool"], "params": d["params"]}).encode("utf-8")
        ).hexdigest()
        assert d["params_hash"] == digest == hash_normalized_params(d["tool"], d["params"])
        assert obj["id"] == f"confirm:{obj['trace_id']}:{digest[:12]}"
        assert d["tool"] != "move_between_jars"  # chuyển hũ dùng khối confirm
        assert "user_id" not in d["params"]
    elif obj["type"] == "receipt_action":
        data = obj["data"]
        assert obj["id"] == f"receipt:{data['tool']}:{data.get('reference_id', obj['trace_id'])}"
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


# --- dự báo và thẻ chủ động: nhất quán nội bộ của khối ---------------------------------------
FORECAST_FIXTURES = [
    p for p in fixture_files("blocks/valid") if p.name.startswith("forecast_timeline.")
]


@pytest.mark.parametrize("path", FORECAST_FIXTURES, ids=lambda p: p.name)
def test_forecast_timeline_nhat_quan(path):
    obj = load_json(path)
    d = obj["data"]
    suffix = (
        ":what_if" if "compare" in d else ""
    )  # khối trước-sau có hậu tố để không đè khối baseline
    assert obj["id"] == f"forecast_timeline:{obj['trace_id']}:{d['jar']['code']}{suffix}"
    days = d["days"]
    assert [x["date"] for x in days] == sorted(x["date"] for x in days)  # tăng dần
    assert len({x["date"] for x in days}) == len(days)  # không trùng ngày
    assert days[0]["date"] > d["origin_date"]  # ngày đầu là origin_date + 1 trở đi
    assert all(x["p10_vnd"] <= x["p50_vnd"] <= x["p90_vnd"] for x in days)
    assert len(days) <= d["horizon_days"]
    if "runout_date" in d:
        assert d["origin_date"] < d["runout_date"] <= days[-1]["date"]
        assert d["status"] in ("short", "tight")
    if "p_shortfall" in d:  # xác suất không đi cùng ước lượng ban đầu
        assert not d["is_initial_estimate"]
    else:
        assert "p_shortfall_se" not in d
    ev = [e["date"] for e in d["events"]]
    assert ev == sorted(ev)
    assert all(days[0]["date"] <= e <= days[-1]["date"] for e in ev)
    if "compare" in d:
        cmp = d["compare"]
        after = cmp["after"]
        assert [x["date"] for x in after["days"]] == [
            x["date"] for x in days
        ]  # cùng ngày với baseline
        assert all(x["p10_vnd"] <= x["p50_vnd"] <= x["p90_vnd"] for x in after["days"])
        assert cmp["common_random_numbers"] is True and cmp["n_paths"] >= 1
        assert after["min_balance_p50_vnd"] == min(x["p50_vnd"] for x in after["days"])
        base_min = min(x["p50_vnd"] for x in days)
        assert cmp["delta"]["min_balance_delta_vnd"] == after["min_balance_p50_vnd"] - base_min
        if "runout_date" in after:
            assert after["status"] in ("short", "tight")
        if "p_shortfall" in after:  # xác suất sau chỉ có khi trước cũng có
            assert "p_shortfall" in d
        aev = [e["date"] for e in after.get("events", [])]
        assert aev == sorted(aev) and all(days[0]["date"] <= e <= days[-1]["date"] for e in aev)


def test_xac_suat_hut_la_ty_le_0_den_1_khong_phai_phan_tram(registry):
    obj = load_json(CONTRACTS / "fixtures/blocks/valid/forecast_timeline.short.json")
    assert 0 <= obj["data"]["p_shortfall"] <= 1
    obj["data"]["p_shortfall"] = 71
    assert errors(registry, "forecast_timeline.schema.json", obj)


def _forecast_kwargs():
    return dict(
        jar={"code": "an_uong", "name": "Ăn uống", "color_key": "violet", "icon_key": "utensils"},
        events=[],
        trace_id="t1",
        source_tool="forecast___get_forecast",
        as_of=datetime(2026, 12, 10, 3, 0, tzinfo=UTC),
        app_date=date(2026, 11, 21),
    )


def _forecast_summary(**over):
    base = {
        "computed_at": "2026-11-21 19:00:03.512000",
        "run_app_date": "2026-11-21",
        "model": "hurdle_calendar",
        "horizon_days": "30",
        "history_days": "47",
        "data_coverage": "0.620",
        "is_initial_estimate": False,
        "start_balance_vnd": "380000",
        "payday_date": "2026-12-05",
        "days_to_payday": "14",
        "runout_date": "2026-11-29",
        "p_shortfall": "0.7100",
        "p_shortfall_se": "0.00600",
        "status": "short",
        "confidence_band": "medium",
        "show_probability": True,
    }
    return {**base, **over}


def test_builder_forecast_nhan_hang_data_api_dang_chuoi_va_giu_dau_am():
    days = [
        {
            "day": "2026-11-22",
            "balance_p10_vnd": "-5000",
            "balance_p50_vnd": "100",
            "balance_p90_vnd": "9000",
        }
    ]
    block = b.build_forecast_timeline(
        summary=_forecast_summary(), days=days, stale=False, **_forecast_kwargs()
    )
    d = block.data
    assert d.computed_at == "2026-11-21T19:00:03Z" and d.p_shortfall == 0.71
    assert d.horizon_days == 30 and d.payday.days_until == 14
    assert d.days[0].p10_vnd == -5000
    assert (
        block.fallback_text == "Hũ Ăn uống dự kiến cạn ngày 29/11, còn 6 ngày tới kỳ lương 05/12."
    )


def test_builder_forecast_khong_phat_xac_suat_khi_show_probability_sai():
    days = [{"day": "2026-11-22", "balance_p10_vnd": 1, "balance_p50_vnd": 2, "balance_p90_vnd": 3}]
    summary = _forecast_summary(
        show_probability=False, runout_date=None, status="ok", is_initial_estimate=True,
        data_coverage=None, confidence_band="low",
    )  # fmt: skip
    block = b.build_forecast_timeline(summary=summary, days=days, stale=True, **_forecast_kwargs())
    d = block.data
    assert d.p_shortfall is None and d.p_shortfall_se is None and d.coverage is None
    wire = b.block_to_wire(block)["data"]
    assert "p_shortfall" not in wire and "runout_date" not in wire and "coverage" not in wire
    assert "ước lượng ban đầu" in block.fallback_text and "đã cũ" in block.fallback_text


def test_builders_confirm_action_va_receipt_action_chi_nhan_tool_khac_chuyen_hu():
    kw = dict(trace_id="t1", source_tool="x", app_date=date(2026, 11, 21))
    now = datetime(2026, 12, 10, tzinfo=UTC)
    with pytest.raises(ValueError):
        b.build_confirm_action(
            tool="move_between_jars", params={}, summary="x", changes=[{"label": "a", "after": "b"}],
            as_of=now, expires_at=now, **kw,
        )  # fmt: skip
    with pytest.raises(ValueError):
        b.build_receipt_action(tool="move_between_jars", occurred_at=now, summary="x", **kw)
    rec = b.build_receipt_action(tool="assign_jar", occurred_at=now, summary="Đã gán", **kw)
    assert rec.id == "receipt:assign_jar:t1"  # không có reference_id thì dùng trace_id


def test_builder_proactive_card_cat_van_ban_dai_trong_fallback():
    card = b.build_proactive_card(
        kind="low_data", status="ok", title="T" * 70, reason="R" * 190,
        actions=[{"kind": "snooze", "label": "Để sau"}], trace_id="t1", source_tool="x",
        as_of=datetime(2026, 12, 10, tzinfo=UTC), app_date=date(2026, 11, 21),
    )  # fmt: skip
    assert len(card.fallback_text) <= 280 and card.id == "proactive_card:t1:low_data"
