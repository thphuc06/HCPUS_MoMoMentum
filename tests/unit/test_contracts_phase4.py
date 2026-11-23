"""Hợp đồng phase 4 (chống chịu, lộ trình, phân hũ tự động): kiểu dùng chung, cấu hình và cú sốc dạng dữ liệu, năm khối mới, bảy tool mới,
REST mới, sự kiện mới.

Phần schema và fixture dùng chung của năm khối nằm ở test_contracts_blocks.py (BLOCK_TYPES), tool ở test_contracts_tools.py, REST ở
test_contracts_rest.py, sự kiện ở test_contracts_events.py, migration ở test_migration_0052.py. File này kiểm thứ chỉ phase 4 có: bất biến
liên trường mà JSON Schema (tập con của repo) không diễn đạt được (Pydantic quyết định), nhất quán số trong fixture, khớp giữa các nơi
nói cùng một tập giá trị, cấu hình có nguồn, quy tắc "không qua token", "một đường ghi".
"""

from __future__ import annotations

import copy
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
from yofina_core import resilience, roadmap, wallet
from yofina_core.errors import HTTP_STATUS, ErrorCode

SPEC = yaml.safe_load((CONTRACTS / "rest" / "openapi.yaml").read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]
FORECAST = {t["name"]: t for t in load_json(CONTRACTS / "tools" / "forecast.json")}
PLANNER = {t["name"]: t for t in load_json(CONTRACTS / "tools" / "planner.json")}
KW = dict(
    trace_id="8f3a21c94b7e4d0aa1c25e6f7b8c9d01",
    source_tool="agent",
    as_of=datetime(2026, 12, 10, 3, 0, tzinfo=UTC),
    app_date=date(2026, 11, 21),
)
NEW_BLOCKS = ("resilience_score", "stress_result", "roadmap", "roadmap_diff", "review_list")
NEW_TOOLS = ("get_resilience_score", "stress_test", "optimize_allocation", "save_roadmap", "get_roadmap")
NEW_ERRORS = {
    "ROADMAP_NOT_FOUND": 404,
    "ROADMAP_INVALID": 422,
    "ROADMAP_VERSION_CONFLICT": 409,
    "SHOCK_NOT_FOUND": 404,
}


def block(name: str) -> dict:
    return load_json(CONTRACTS / "fixtures" / "blocks" / "valid" / f"{name}.json")


def broken(name: str, *edits):
    """Bản sao của fixture hợp lệ sau khi sửa (mỗi edit: (đường dẫn, giá trị) hoặc (đường dẫn, DEL)); phải bị Pydantic từ chối."""
    obj = copy.deepcopy(block(name))
    for path, value in edits:
        node = obj
        for key in path[:-1]:
            node = node[key]
        if value is DEL:
            del node[path[-1]]
        else:
            node[path[-1]] = value
    return obj


DEL = object()


def rejected(name: str, *edits):
    with pytest.raises(ValidationError):
        b.parse_block(broken(name, *edits))


# =====================================================================================
# Tập giá trị khớp giữa các nơi
# =====================================================================================
def schema_enum(file: str, *path: str) -> tuple[str, ...]:
    node = load_json(CONTRACTS / "blocks" / f"{file}.schema.json")
    for key in path:
        node = node[key]
    return tuple(node["enum"])


def test_cac_tap_gia_tri_khop_hang_so():
    assert schema_enum("resilience_score", "$defs", "ResilienceBand") == wallet.RESILIENCE_BANDS == b.ResilienceBand.__args__
    assert (
        schema_enum("resilience_score", "$defs", "ResilienceComponentKey")
        == wallet.RESILIENCE_COMPONENTS
        == b.ResilienceComponentKey.__args__
        == b.RESILIENCE_ORDER
    )
    assert schema_enum("stress_result", "$defs", "ShockSummary", "properties", "kind") == wallet.SHOCK_KINDS == b.ShockKind.__args__
    assert schema_enum("roadmap", "$defs", "RoadmapReasonCode") == wallet.ROADMAP_REASON_CODES == b.RoadmapReasonCode.__args__
    assert schema_enum("roadmap", "$defs", "RoadmapVersionStatus") == wallet.ROADMAP_VERSION_STATUSES == b.RoadmapVersionStatus.__args__
    assert schema_enum("roadmap", "$defs", "RoadmapStepStatus") == wallet.ROADMAP_STEP_STATUSES == b.RoadmapStepStatus.__args__
    assert schema_enum("roadmap", "$defs", "RoadmapStep", "properties", "kind") == wallet.ROADMAP_STEP_KINDS == b.RoadmapStepKind.__args__
    assert (
        schema_enum("roadmap", "$defs", "RoadmapStepAction", "properties", "tool")
        == wallet.ROADMAP_STEP_ACTION_TOOLS
        == b.RoadmapStepActionTool.__args__
    )
    assert schema_enum("roadmap", "$defs", "RoadmapData", "properties", "feasibility") == wallet.ROADMAP_FEASIBILITIES == b.RoadmapFeasibility.__args__
    assert (
        schema_enum("roadmap", "$defs", "RoadmapAlternative", "properties", "kind")
        == wallet.ALTERNATIVE_KINDS
        == b.AlternativeKind.__args__
    )
    assert wallet.ALLOCATION_STATUSES == roadmap.AllocationStatus.__args__ == ("optimal", "relaxed", "infeasible")
    assert roadmap.RelaxationKind.__args__ == wallet.ALLOCATION_RELAXATION_KINDS
    assert roadmap.JobStatus.__args__ == wallet.ROADMAP_JOB_STATUSES
    assert roadmap.JobStage.__args__ == wallet.ROADMAP_JOB_STAGES
    assert roadmap.JobTrigger.__args__ == wallet.ROADMAP_JOB_TRIGGERS
    assert schema_enum("review_list", "$defs", "ReviewItem", "properties", "tier") == wallet.CLASSIFICATION_TIERS == b.ClassificationTier.__args__
    assert schema_enum("review_list", "$defs", "ReviewItem", "properties", "classified_by") == wallet.CLASSIFIED_BY == b.ClassifiedByName.__args__
    assert schema_enum("review_list", "$defs", "ReviewListData", "properties", "mode") == wallet.REVIEW_MODES == b.ReviewMode.__args__
    assert schema_enum("review_list", "$defs", "ReviewAsk", "properties", "status") == wallet.REVIEW_ASK_STATUSES == b.ReviewAskStatus.__args__
    assert set(wallet.ROADMAP_ACTIVE_REASONS) <= set(wallet.ROADMAP_REASON_CODES)
    assert set(wallet.ROADMAP_STEP_ACTION_TOOLS) <= set(wallet.ACTION_TOOLS)  # bước chỉ dẫn tới tool ghi đã có (đường ghi duy nhất)
    assert wallet.ROADMAP_STEP_ACTION_TOOLS == ("move_between_jars", "save_jars", "schedule_nudge")
    assert wallet.RESILIENCE_SOURCES == ("nightly", "reset", "event", "read")
    assert len(wallet.INTENTS) == 10 and wallet.INTENTS[7:] == ("resilience", "stress", "roadmap")


def test_loi_roadmap_va_cu_soc_khop_ba_noi():
    schema = SCHEMAS["ErrorCode"]
    for code, status in NEW_ERRORS.items():
        assert HTTP_STATUS[ErrorCode(code)] == status == schema["x-http-status"][code]
        assert schema["x-meaning"][code]
    assert schema["enum"][-len(NEW_ERRORS) :] == list(NEW_ERRORS)  # thêm cuối, không đổi thứ tự mã cũ
    front = (REPO / "frontend/src/api/errors.ts").read_text(encoding="utf-8")
    for code, status in NEW_ERRORS.items():
        assert f"'{code}'," in front and f"{code}: {status}," in front


def test_mo_ta_ket_qua_tool_nem_ma_loi_co_the_gap():
    text = "".join((CONTRACTS / "tools" / f"{n}.schema.json").read_text(encoding="utf-8") for n in ("forecast.results", "planner.results"))
    for code in NEW_ERRORS:
        assert code in text, code


# =====================================================================================
# Cấu hình điểm chống chịu và cú sốc dạng dữ liệu
# =====================================================================================
ML = CONTRACTS / "ml"


def ml_validator(registry, name: str) -> Draft202012Validator:
    return Draft202012Validator({"$ref": f"{BASE}/ml/{name}.schema.json"}, registry=registry)


def shape(registry, file: str, name: str, base: str = "ml"):
    hit = registry.resolver(base_uri=f"{BASE}/{base}/").lookup(f"{file}.schema.json#/$defs/{name}")
    return normalize(hit.contents, hit.resolver)


def root_shape(registry, file: str):
    hit = registry.resolver(base_uri=f"{BASE}/ml/").lookup(f"{file}.schema.json")
    return normalize(hit.contents, hit.resolver)


RESILIENCE_FILE = REPO / "libs/yofina_core/src/yofina_core/resilience_defaults.json"
SHOCKS_FILE = REPO / "libs/yofina_core/src/yofina_core/shocks.json"


def test_cau_hinh_hop_le_qua_json_schema_va_pydantic_va_model_khop_schema(registry):
    obj = load_json(RESILIENCE_FILE)
    assert list(ml_validator(registry, "resilience_config").iter_errors(obj)) == []
    cfg = resilience.parse_config(obj)
    assert cfg == resilience.load_resilience_config()
    assert pydantic_tree(resilience.ResilienceConfig) == root_shape(registry, "resilience_config")


def test_cu_soc_hop_le_qua_json_schema_va_pydantic_va_model_khop_schema(registry):
    obj = load_json(SHOCKS_FILE)
    assert list(ml_validator(registry, "shock_set").iter_errors(obj)) == []
    assert resilience.parse_shock_set(obj) == resilience.load_shock_set()
    assert pydantic_tree(resilience.ShockSet) == root_shape(registry, "shock_set")


def test_moi_so_trong_cau_hinh_co_don_vi_ghi_chu_va_nguon():
    obj = load_json(RESILIENCE_FILE)

    def walk(node, path):
        if isinstance(node, dict) and "value" in node:
            assert {"value", "unit", "note", "source"} <= set(node), path
            assert node["note"].strip() and node["source"].strip(), path
            assert node["source"].startswith("Quy ước") or "mô phỏng" in node["source"], path  # hoặc là quy ước, hoặc nêu rõ là giá trị mô phỏng
            return
        if isinstance(node, dict):
            for k, v in node.items():
                if k not in ("version", "note", "disclaimer", "label", "explanation_template"):
                    walk(v, f"{path}.{k}")

    walk({k: obj[k] for k in ("weights", "bands", "components", "stress")}, "cfg")


def test_trong_so_cong_bang_mot_va_nhom_diem_tang_dan_va_dung_thu_tu_bon_thanh_phan():
    cfg = resilience.load_resilience_config()
    assert tuple(wallet.RESILIENCE_COMPONENTS) == tuple(type(cfg.weights).model_fields)
    assert abs(sum(getattr(cfg.weights, k).value for k in wallet.RESILIENCE_COMPONENTS) - 1) < 1e-9
    assert 0 < cfg.bands.weak_max_score.value < cfg.bands.fair_max_score.value < 100
    for key, names in resilience.REQUIRED_THRESHOLDS.items():
        assert set(names) <= set(getattr(cfg.components, key).thresholds), key
    assert tuple(resilience.REQUIRED_THRESHOLDS) == wallet.RESILIENCE_COMPONENTS
    # nhóm điểm tính từ cấu hình, không có số gắn cứng ở nơi khác
    assert [resilience.band_for_score(s) for s in (0, 39, 40, 69, 70, 100)] == ["weak", "weak", "fair", "fair", "strong", "strong"]


def test_mau_cau_giai_thich_chi_dung_cho_dien_hop_le():
    cfg = resilience.load_resilience_config()
    for key, names in resilience.EXPLANATION_PLACEHOLDERS.items():
        template = getattr(cfg.components, key).explanation_template
        found = set(re.findall(r"\{([a-z_]+)\}", template))
        assert found and found <= set(names), key
        filled = template.format(**{n: 999 for n in names})
        assert 1 <= len(filled) <= 200
    bad = load_json(RESILIENCE_FILE)
    bad["components"]["save"]["explanation_template"] = "Đủ sống {so_ngay_la} ngày."
    with pytest.raises(ValidationError):
        resilience.parse_config(bad)


def test_cau_hinh_sai_bi_pydantic_chan():
    base = load_json(RESILIENCE_FILE)

    def bad(mutate):
        obj = copy.deepcopy(base)
        mutate(obj)
        with pytest.raises(ValidationError):
            resilience.parse_config(obj)

    bad(lambda o: o["weights"]["save"].update(value=0.5))  # tổng khác 1
    bad(lambda o: o["bands"]["weak_max_score"].update(value=80))  # nhóm không tăng dần
    bad(lambda o: o["components"]["save"]["thresholds"].pop("full_score_days"))  # thiếu ngưỡng bắt buộc
    bad(lambda o: o["components"]["borrow"]["thresholds"]["full_score_obligation_ratio"].update(value=0.9))  # mốc ngược
    bad(lambda o: o["stress"]["short_shortfall_ratio"].update(value=0))
    bad(lambda o: o["weights"]["plan"].pop("source"))  # thiếu nguồn


def test_ba_cu_soc_mau_dung_id_va_tham_so_theo_loai():
    shocks = resilience.load_shock_set()
    assert [s.shock_id for s in shocks.shocks] == ["mat_viec_2_thang", "tien_tro_tang", "om_mot_tuan"]
    assert [s.kind for s in shocks.shocks] == ["income_loss", "expense_increase", "health_event"]
    assert tuple(resilience.SHOCK_PARAMS_BY_KIND) == wallet.SHOCK_KINDS
    by_id = {s.shock_id: s for s in shocks.shocks}
    assert by_id["mat_viec_2_thang"].params.duration_days == 60 and by_id["mat_viec_2_thang"].params.income_loss_percent == 100
    assert by_id["tien_tro_tang"].params.target_obligation_kind == "rent"
    assert by_id["om_mot_tuan"].params.duration_days == 7
    for s in shocks.shocks:
        assert not any(ch.isdigit() for ch in s.description), s.shock_id  # mô tả không chứa số (số nằm ở params)
        assert "mô phỏng" in s.source
        summary = s.summary()
        assert summary.duration_days == s.params.duration_days
    assert shocks.get("khong_co") is None


def test_cu_soc_sai_tham_so_theo_loai_bi_chan():
    base = load_json(SHOCKS_FILE)["shocks"][0]
    for params in (
        {"duration_days": 60},  # thiếu income_loss_percent
        {"duration_days": 60, "income_loss_percent": 100, "extra_cost_vnd": 1},  # thừa
        {"duration_days": 60, "income_loss_percent": 150},  # ngoài 0..100
    ):
        with pytest.raises(ValidationError):
            resilience.ShockDefinition.model_validate({**base, "params": params}, strict=False)
    dup = load_json(SHOCKS_FILE)
    dup["shocks"].append(dup["shocks"][0])
    with pytest.raises(ValidationError):
        resilience.parse_shock_set(dup)


def test_mo_ta_tool_nhac_dung_ma_cu_soc_cua_file_du_lieu():
    ids = [s.shock_id for s in resilience.load_shock_set().shocks]
    for tool, key in ((FORECAST["stress_test"], "shock_id"), (PLANNER["optimize_allocation"], "shock_id")):
        text = tool["inputSchema"]["properties"][key]["description"]
        assert all(i in text for i in ids), tool["name"]
    assert FORECAST["stress_test"]["inputSchema"]["required"] == ["shock_id"]
    for shock in resilience.load_shock_set().shocks:
        assert shock.label  # nhãn hiển thị lấy từ dữ liệu


# =====================================================================================
# Khối: bất biến mà JSON Schema không diễn đạt được
# =====================================================================================
def test_diem_tong_bang_trung_binh_co_trong_so_va_thanh_phan_yeu_nhat():
    ok = block("resilience_score.minh")["data"]
    assert ok["score"] == 58 and ok["weakest"] == "save"
    assert ok["components"][0]["inputs"][0]["unit"] == "vnd"
    rejected("resilience_score.minh", (["data", "score"], 90))  # lệch quá 1 so với trung bình có trọng số
    rejected("resilience_score.minh", (["data", "weakest"], "plan"))  # không phải thành phần thấp nhất
    rejected("resilience_score.minh", (["data", "components", 0, "weight"], 0.9))  # tổng trọng số khác 1
    rejected("resilience_score.minh", (["data", "components", 1, "key"], "borrow"))  # sai thứ tự và trùng khóa
    rejected("resilience_score.minh", (["data", "components", 0, "applicable"], False))  # applicable khớp score và band
    rejected("resilience_score.minh", (["data", "components", 0, "inputs", 0, "value"], 7310000.5))  # tiền là số nguyên
    rejected("resilience_score.minh", (["data", "components", 0, "inputs", 2, "value"], -3))  # ngày không âm


def test_thanh_phan_khong_ap_dung_co_trong_so_khong_va_trong_so_con_lai_chuan_hoa():
    d = block("resilience_score.no_goal")["data"]
    plan = next(c for c in d["components"] if c["key"] == "plan")
    assert plan["applicable"] is False and plan["weight"] == 0 and "score" not in plan and "band" not in plan
    assert abs(sum(c["weight"] for c in d["components"]) - 1) < 0.005
    rejected("resilience_score.no_goal", (["data", "components", 3, "weight"], 0.15))  # thành phần không áp dụng phải weight 0
    # điểm trước và sau khi chuẩn hóa bằng đúng công thức
    assert round(sum(c["weight"] * c["score"] for c in d["components"] if c["applicable"])) == d["score"]


def test_ket_qua_cu_soc_bat_bien():
    d = block("stress_result.mat_viec")["data"]
    assert (d["score_before"], d["score_after"], d["runway_days_total"], d["runway_days_emergency"]) == (58, 34, 27, 9)
    rejected("stress_result.mat_viec", (["data", "score_after"], 70), (["data", "score_delta"], 12))  # sốc không làm điểm tăng
    rejected("stress_result.mat_viec", (["data", "score_delta"], -10))  # delta phải bằng sau trừ trước
    rejected("stress_result.mat_viec", (["data", "status"], "ok"))  # có khoản thiếu thì không thể là "đủ"
    rejected("stress_result.mat_viec", (["data", "shortfall_from"], DEL))  # có khoản thiếu thì phải có ngày bắt đầu thiếu
    rejected("stress_result.mat_viec", (["data", "emergency_jar"], DEL))  # số ngày hũ Dự phòng cần hũ Dự phòng
    rejected("stress_result.mat_viec", (["data", "components", 0, "key"], "plan"))
    rejected("stress_result.tien_tro_tang", (["data", "shortfall_vnd"], 100000))  # thiếu mà không có ngày
    assert "emergency_jar" not in block("stress_result.om_mot_tuan_khong_co_hu_du_phong")["data"]  # tài khoản không có hũ Dự phòng
    assert "runway_days_total" not in block("stress_result.tien_tro_tang")["data"]  # trụ hết khoảng dự báo


def test_ba_trang_thai_cua_cu_soc_luon_co_chu_trong_headline_va_dung_chung_jar_status():
    text = (CONTRACTS / "blocks" / "stress_result.schema.json").read_text(encoding="utf-8")
    assert "forecast_timeline.schema.json#/$defs/JarStatus" in text and '"ok", "tight", "short"' not in text
    for name, word in (("mat_viec", "34"), ("tien_tro_tang", "52"), ("om_mot_tuan_khong_co_hu_du_phong", "50")):
        obj = block(f"stress_result.{name}")
        assert word in obj["data"]["headline"] and obj["fallback_text"] == obj["data"]["headline"]


def test_lo_trinh_bat_bien():
    v3 = block("roadmap.minh_v3_proposed")["data"]
    assert (v3["version"], v3["status"], v3["reason"]["code"], v3["based_on_version"]) == (3, "proposed", "behavior_changed", 2)
    assert v3["counts"] == {"pending": 5, "accepted": 0, "rejected": 0}
    rejected("roadmap.minh_v3_proposed", (["data", "counts", "pending"], 4))
    rejected("roadmap.minh_v3_proposed", (["data", "phases", 0, "steps", 1, "step_id"], "giu_san_tra_sau"))  # trùng step_id
    rejected("roadmap.minh_v3_proposed", (["data", "phases", 1, "phase_id"], "on_dinh_thang_nay"))  # trùng phase_id
    rejected("roadmap.minh_v3_proposed", (["data", "based_on_version"], 3))  # bản gốc phải cũ hơn
    rejected("roadmap.minh_v3_proposed", (["data", "phases", 0, "steps", 0, "status"], "accepted"))  # đã quyết mà thiếu decided_at
    rejected("roadmap.minh_v3_proposed", (["data", "phases", 0, "steps", 0, "decided_at"], "2026-11-22T08:10:00Z"))  # chờ mà có decided_at
    rejected("roadmap.minh_v3_proposed", (["data", "phases", 0, "steps", 0, "action", "params", "confirm_token"], "a.b"))
    rejected("roadmap.minh_v3_proposed", (["data", "phases", 0, "steps", 0, "action", "params", "user_id"], "x"))
    rejected("roadmap.minh_v3_proposed", (["data", "phases", 0, "start_date"], "2027-03-01"))  # giai đoạn không xếp theo thời gian
    rejected("roadmap.minh_v3_proposed", (["data", "phases", 0, "end_date"], "2026-11-01"))  # kết thúc trước bắt đầu
    rejected("roadmap.minh_v3_proposed", (["data", "feasibility"], "infeasible"))  # infeasible mà không có hai lựa chọn
    rejected("roadmap.minh_v3_proposed", (["data", "goals", 0, "shortfall_vnd"], 100000))  # kịp hạn thì không thiếu


def test_noi_thang_khi_muc_tieu_khong_kha_thi_dung_hai_lua_chon():
    d = block("roadmap.infeasible_two_options")["data"]
    assert d["feasibility"] == "infeasible" and len(d["alternatives"]) == 2
    assert {a["kind"] for a in d["alternatives"]} <= set(wallet.ALTERNATIVE_KINDS)
    assert not all(g["on_track"] for g in d["goals"])
    rejected("roadmap.infeasible_two_options", (["data", "feasibility"], "on_track"))  # còn lựa chọn mà nói kịp
    rejected("roadmap.infeasible_two_options", (["data", "goals", 0, "on_track"], True), (["data", "goals", 0, "shortfall_vnd"], 0))
    one = copy.deepcopy(block("roadmap.infeasible_two_options"))
    one["data"]["alternatives"].pop()
    with pytest.raises(ValidationError):
        b.parse_block(one)
    same = copy.deepcopy(block("roadmap.infeasible_two_options"))
    same["data"]["alternatives"][1]["option_id"] = same["data"]["alternatives"][0]["option_id"]
    with pytest.raises(ValidationError):
        b.parse_block(same)


def test_buoc_co_hanh_dong_doi_tien_chi_dan_toi_tool_ghi_co_san_va_khong_chua_bi_mat():
    seen = set()
    for name in ("roadmap.minh_v3_proposed", "roadmap.active_edited", "roadmap.infeasible_two_options"):
        for ph in block(name)["data"]["phases"]:
            for st in ph["steps"]:
                action = st.get("action")
                if action:
                    seen.add(action["tool"])
                    assert action["tool"] in wallet.ACTION_TOOLS
                    assert not {"user_id", "confirm_token"} & set(action["params"])
                    assert "confirm_token" not in json.dumps(st) and "user_id" not in json.dumps(st)
    assert {"move_between_jars", "schedule_nudge"} <= seen <= set(wallet.ROADMAP_STEP_ACTION_TOOLS)
    # lý do từng bước có chữ; số trong lý do có trong metrics hoặc trường số của bước (NumericGrounding ở harness)
    for ph in block("roadmap.minh_v3_proposed")["data"]["phases"]:
        for st in ph["steps"]:
            assert st["reason"].strip()


def test_phien_ban_hai_dang_dung_co_buoc_da_quyet_va_buoc_da_sua():
    d = block("roadmap.active_edited")["data"]
    assert d["status"] == "active" and d["reason"]["code"] == "step_edited" and d["counts"] == {"pending": 2, "accepted": 2, "rejected": 1}
    steps = {s["step_id"]: s for p in d["phases"] for s in p["steps"]}
    assert steps["bu_an_uong"]["edited"] is True and steps["bu_an_uong"]["status"] == "accepted"
    assert steps["cat_giai_tri"]["status"] == "rejected"


def test_so_sanh_phien_ban_khop_hai_lo_trinh_trong_fixture():
    diff = block("roadmap_diff.v2_v3")["data"]
    v2, v3 = block("roadmap.active_edited")["data"], block("roadmap.minh_v3_proposed")["data"]
    assert (diff["from_roadmap_id"], diff["to_roadmap_id"]) == (v2["roadmap_id"], v3["roadmap_id"])
    assert diff["reason"] == v3["reason"] and diff["can_adopt"] is (v3["status"] == "proposed")
    old = {s["step_id"]: s for p in v2["phases"] for s in p["steps"]}
    new = {s["step_id"]: s for p in v3["phases"] for s in p["steps"]}
    expected = {
        "added": sorted(set(new) - set(old)),
        "removed": sorted(set(old) - set(new)),
        "changed": sorted(
            k for k in set(old) & set(new) if old[k].get("amount_vnd") != new[k].get("amount_vnd")
        ),
    }
    got = {k: sorted(c["step_id"] for c in diff["changes"] if c["kind"] == k) for k in ("added", "removed", "changed")}
    assert got == expected
    assert diff["counts"]["unchanged"] == len(set(old) & set(new)) - len(expected["changed"])
    rejected("roadmap_diff.v2_v3", (["data", "counts", "added"], 2))
    rejected("roadmap_diff.v2_v3", (["data", "to_version"], 2))  # hai phiên bản phải khác nhau
    rejected("roadmap_diff.v2_v3", (["data", "can_adopt"], False))
    rejected("roadmap_diff.v2_v3", (["data", "changes", 1, "step_id"], "bu_an_uong"))  # mỗi bước tối đa một thay đổi


def test_danh_sach_xem_lai_hai_che_do_khong_tron_muc():
    review, ask = block("review_list.review")["data"], block("review_list.daily_ask")["data"]
    assert {i["tier"] for i in review["items"]} == {"review"} and "ask" not in review
    assert {i["tier"] for i in ask["items"]} == {"ask"} and ask["ask"]["status"] == "open"
    assert all(len(i["suggestions"]) <= 2 for i in ask["items"])  # hỏi gộp kèm tối đa 2 gợi ý
    assert ask["pending_total_vnd"] == sum(i["amount_vnd"] for i in ask["items"])
    assert review["pending_total_vnd"] == sum(i["amount_vnd"] for i in review["items"])
    rejected("review_list.review", (["data", "items", 0, "tier"], "ask"))  # A1 chỉ nhận mức review
    rejected("review_list.daily_ask", (["data", "ask"], DEL))  # hỏi gộp phải kèm trạng thái câu hỏi
    rejected("review_list.review", (["data", "ask"], {"ask_date": "2026-11-21", "status": "open"}))
    rejected("review_list.review", (["data", "count"], 1))  # count không nhỏ hơn số mục đang hiện
    rejected("review_list.review", (["data", "items", 1, "transaction_id"], block("review_list.review")["data"]["items"][0]["transaction_id"]))
    assert block("review_list.empty")["data"]["count"] == 0  # trạng thái rỗng vẫn có chữ
    assert block("review_list.empty")["fallback_text"]


@pytest.mark.parametrize(
    ("builder", "name", "tool", "block_id"),
    [
        (b.build_resilience_score, "resilience_score.minh", "forecast___get_resilience_score", None),
        (b.build_stress_result, "stress_result.mat_viec", "forecast___stress_test", None),
        (b.build_roadmap, "roadmap.minh_v3_proposed", "planner___get_roadmap", None),
        (b.build_roadmap_diff, "roadmap_diff.v2_v3", "rest:GET /roadmap/diff", None),
        (b.build_review_list, "review_list.daily_ask", "rest:GET /review", None),
        (b.build_review_list, "review_list.review", "rest:GET /review", None),
    ],
)
def test_builder_boc_data_dung_id_va_fallback_do_code_viet(builder, name, tool, block_id):
    fixture = block(name)
    built = builder(data=fixture["data"], **{**KW, "source_tool": tool, "trace_id": fixture["trace_id"]})
    wire = b.block_to_wire(built)
    assert wire["id"] == fixture["id"] and wire["fallback_text"] == fixture["fallback_text"]
    assert wire["data"] == fixture["data"] and wire["type"] == fixture["type"]
    assert wire["fallback_text"] == fixture["data"]["headline"]


def test_id_khoi_theo_quy_tac():
    trace = "8f3a21c94b7e4d0aa1c25e6f7b8c9d01"
    assert block("resilience_score.minh")["id"] == f"resilience_score:{trace}"
    assert block("stress_result.mat_viec")["id"] == f"stress_result:{trace}:mat_viec_2_thang"
    assert block("roadmap.minh_v3_proposed")["id"] == f"roadmap:{trace}:v3"
    assert block("roadmap_diff.v2_v3")["id"] == f"roadmap_diff:{trace}:v2-v3"
    assert block("review_list.review")["id"] == f"review_list:{trace}:review"
    assert block("review_list.daily_ask")["id"] == f"review_list:{trace}:daily_ask"
    # A1 và A2 trong cùng một lượt không đè nhau
    assert block("review_list.review")["id"] != block("review_list.daily_ask")["id"]


def test_so_trong_khoi_phase_4_co_basis_va_khoi_khong_co_so_uoc_luong_thi_khong():
    for name in ("resilience_score.minh", "stress_result.mat_viec", "roadmap.minh_v3_proposed"):
        basis = block(name)["data"]["basis"]
        assert {"computed_at", "stale", "confidence_band", "is_initial_estimate", "history_days"} <= set(basis)
    assert "basis" not in block("review_list.review")["data"]  # số của sổ cái, không phải ước lượng
    text = (CONTRACTS / "blocks" / "review_list.schema.json").read_text(encoding="utf-8")
    assert "không có `basis`" in text


def test_khong_co_tien_dang_chuoi_hay_so_thuc_trong_fixture_phase_4():
    files = [
        p
        for sub in ("blocks/valid", "tools", "rest")
        for p in (CONTRACTS / "fixtures" / sub).glob("*.json")
        if any(k in p.name for k in (*NEW_BLOCKS, *NEW_TOOLS, "Roadmap", "Resilience", "Stress", "Review", "Shocks"))
    ]
    assert len(files) > 25

    def scan(node, where):
        if isinstance(node, dict):
            for k, v in node.items():
                if k.endswith("_vnd") and v is not None:
                    assert isinstance(v, int) and not isinstance(v, bool), f"{where}.{k}={v!r}"
                scan(v, f"{where}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                scan(v, f"{where}[{i}]")

    for p in files:
        scan(load_json(p), p.name)


def test_hop_dong_phase_4_khong_dung_nhan_cam_va_khong_co_thong_tin_nhay_cam():
    banned = ("ví trả sau", "momo", "finhealth")
    for root in (CONTRACTS, REPO / "libs/yofina_core/src/yofina_core"):
        for path in root.rglob("*"):
            if path.suffix in {".json", ".yaml"} and path.name.split(".")[0] in {*NEW_BLOCKS, "shocks", "resilience_defaults", "shock_set", "resilience_config", "behavior", "roadmap"}:
                text = "\n".join(line for line in path.read_text(encoding="utf-8").lower().splitlines() if "http" not in line)
                assert not any(w in text for w in banned), path.name
    for path in (CONTRACTS / "fixtures").rglob("*.json"):
        if any(k in path.name for k in (*NEW_BLOCKS, "Roadmap", "Resilience", "Stress", "Review", "behavior", "roadmap", *NEW_TOOLS)):
            text = path.read_text(encoding="utf-8").lower()
            assert not any(s in text for s in ("@", "password", "secret", "arn:aws")), path.name


# =====================================================================================
# Tool
# =====================================================================================
def test_tool_phase_4_nam_o_dung_target_va_khop_hang_so():
    assert wallet.FORECAST_TOOLS[-2:] == ("get_resilience_score", "stress_test")
    assert wallet.PLANNER_TOOLS[-3:] == ("optimize_allocation", "save_roadmap", "get_roadmap")
    assert set(wallet.PHASE4_TOOLS) == set(NEW_TOOLS)
    for name in ("get_resilience_score", "stress_test"):
        assert len(f"forecast___{name}") <= 64
    for name in ("optimize_allocation", "save_roadmap", "get_roadmap"):
        assert len(f"planner___{name}") <= 64


def test_tool_doc_khong_co_token_va_tool_ghi_lo_trinh_khong_qua_token():
    for tool in (FORECAST["get_resilience_score"], FORECAST["stress_test"], PLANNER["optimize_allocation"], PLANNER["get_roadmap"]):
        assert "confirm_token" not in tool["inputSchema"]["properties"], tool["name"]
    save = PLANNER["save_roadmap"]
    assert "confirm_token" not in save["inputSchema"]["properties"]
    assert "KHÔNG đổi số dư" in save["description"] and "không cần confirm_token" in save["description"]
    # quyết định số 3: save_roadmap không thuộc tool ghi qua token
    assert "save_roadmap" not in wallet.PLANNER_WRITE_TOOLS and "save_roadmap" not in wallet.ACTION_TOOLS
    assert wallet.PLANNER_WRITE_TOOLS == ("schedule_nudge",) and "optimize_allocation" not in wallet.ACTION_TOOLS


def test_save_roadmap_khop_model_roadmap_draft():
    props = PLANNER["save_roadmap"]["inputSchema"]["properties"]
    assert set(props) - {"user_id"} == set(roadmap.RoadmapDraft.model_fields)
    assert set(PLANNER["save_roadmap"]["inputSchema"]["required"]) == {"reason_code", "feasibility", "phases"}
    phase = props["phases"]["items"]
    assert set(phase["properties"]) == set(roadmap.RoadmapDraftPhase.model_fields)
    step = phase["properties"]["steps"]["items"]
    assert set(step["properties"]) == set(roadmap.RoadmapDraftStep.model_fields)
    assert set(props["goals"]["items"]["properties"]) == set(b.GoalProjection.model_fields)
    assert set(props["alternatives"]["items"]["properties"]) == set(b.RoadmapAlternative.model_fields)
    assert set(step["properties"]["action"]["properties"]) == {"tool", "params"}
    # bản nháp là phần của lộ trình đã lưu: bỏ status, decided_at, edited thì khối hợp lệ thành bản nháp hợp lệ
    saved = block("roadmap.minh_v3_proposed")["data"]
    draft = {
        "reason_code": saved["reason"]["code"],
        "based_on_version": saved["based_on_version"],
        "behavior_flag_id": saved["reason"]["behavior_flag_id"],
        "feasibility": saved["feasibility"],
        "goals": saved["goals"],
        "alternatives": saved["alternatives"],
        "phases": [
            {**ph, "steps": [{k: v for k, v in st.items() if k not in ("status", "decided_at", "edited")} for st in ph["steps"]]}
            for ph in saved["phases"]
        ],
    }
    parsed = roadmap.RoadmapDraft.model_validate(draft, strict=False)
    assert len(parsed.phases) == 3
    for mutate in (
        lambda d: d.update(reason_code="behavior_changed", behavior_flag_id=None),
        lambda d: d.update(reason_code="initial"),  # bản đầu tiên không có based_on_version
        lambda d: d.update(feasibility="infeasible"),
        lambda d: d["phases"][0]["steps"][0].update(status="accepted"),  # bản nháp không có status
        lambda d: d["phases"][0]["steps"][1].update(step_id=d["phases"][0]["steps"][0]["step_id"]),
    ):
        bad = copy.deepcopy(draft)
        mutate(bad)
        with pytest.raises(ValidationError):
            roadmap.RoadmapDraft.model_validate(bad, strict=False)


def test_mo_ta_tool_nhac_dung_gia_tri_hop_le_cua_hang_so():
    props = PLANNER["save_roadmap"]["inputSchema"]["properties"]
    for v in wallet.ROADMAP_REASON_CODES:
        assert v in props["reason_code"]["description"]
    for v in wallet.ROADMAP_FEASIBILITIES:
        assert v in props["feasibility"]["description"]
    step = props["phases"]["items"]["properties"]["steps"]["items"]["properties"]
    for v in wallet.ROADMAP_STEP_KINDS:
        assert v in step["kind"]["description"]
    for v in wallet.ROADMAP_STEP_ACTION_TOOLS:
        assert v in step["action"]["properties"]["tool"]["description"]
    for v in wallet.ALTERNATIVE_KINDS:
        assert v in props["alternatives"]["items"]["properties"]["kind"]["description"]
    get = PLANNER["get_roadmap"]["inputSchema"]["properties"]
    for v in wallet.ROADMAP_WHICH:
        assert v in get["which"]["description"]


def test_allocation_plan_khop_json_schema_va_bat_bien(registry):
    assert pydantic_tree(roadmap.AllocationPlanData) == shape(registry, "planner.results", "AllocationPlanData", "tools")
    optimal = load_json(CONTRACTS / "fixtures/tools/optimize_allocation.ok.json")["data"]
    relaxed = load_json(CONTRACTS / "fixtures/tools/optimize_allocation.ok_relaxed.json")["data"]
    infeasible = load_json(CONTRACTS / "fixtures/tools/optimize_allocation.ok_infeasible.json")["data"]
    assert [d["status"] for d in (optimal, relaxed, infeasible)] == list(wallet.ALLOCATION_STATUSES)
    assert not optimal["relaxations"] and relaxed["relaxations"] and len(infeasible["alternatives"]) == 2
    for d in (optimal, relaxed, infeasible):
        assert sum(x["proposed_monthly_vnd"] for x in d["lines"]) + d["unallocated_vnd"] == d["income_monthly_vnd"]
        assert d["solver"]["name"] == "scipy.optimize.linprog"
    assert any(x["floor_gap_vnd"] for x in infeasible["lines"]) and not any(x["floor_gap_vnd"] for x in relaxed["lines"])

    def bad(src, mutate):
        obj = copy.deepcopy(src)
        mutate(obj)
        with pytest.raises(ValidationError):
            roadmap.AllocationPlanData.model_validate(obj, strict=False)

    bad(optimal, lambda o: o["lines"][0].update(proposed_monthly_vnd=o["lines"][0]["proposed_monthly_vnd"] + 1))  # tiền không bảo toàn
    bad(optimal, lambda o: o["lines"][0].update(floor_gap_vnd=1))  # optimal phải đạt mọi sàn
    bad(optimal, lambda o: o["solver"].update(relaxation_rounds=1))
    bad(relaxed, lambda o: o.update(relaxations=[]))  # relaxed phải ghi điều đã nới
    bad(relaxed, lambda o: o["solver"].update(relaxation_rounds=0))
    bad(infeasible, lambda o: o["alternatives"].pop())  # infeasible phải có đúng hai lựa chọn
    bad(optimal, lambda o: o.update(alternatives=infeasible["alternatives"]))  # lựa chọn chỉ có khi infeasible
    bad(optimal, lambda o: o["lines"].append(copy.deepcopy(o["lines"][0])))  # mỗi hũ một dòng


def test_roadmap_job_va_phien_ban_khop_openapi(registry):
    for name, model in (("RoadmapJob", roadmap.RoadmapJob), ("RoadmapVersionSummary", roadmap.RoadmapVersionSummary)):
        hit = registry.resolver(base_uri=OPENAPI_URI).lookup(f"{OPENAPI_URI}#/components/schemas/{name}")
        assert pydantic_tree(model) == normalize(hit.contents, hit.resolver), name
    queued = load_json(CONTRACTS / "fixtures/rest/RoadmapJob.queued.json")
    assert roadmap.RoadmapJob.model_validate(queued, strict=False).status == "queued"

    def bad(mutate):
        obj = load_json(CONTRACTS / "fixtures/rest/RoadmapJob.done.json")
        mutate(obj)
        with pytest.raises(ValidationError):
            roadmap.RoadmapJob.model_validate(obj, strict=False)

    bad(lambda o: o.pop("version"))  # done phải có version và roadmap_id
    bad(lambda o: o.update(progress=80))  # done thì progress 100
    bad(lambda o: o.pop("finished_at"))
    bad(lambda o: o.update(status="running"))  # running mà có finished_at và version
    failed = load_json(CONTRACTS / "fixtures/rest/RoadmapJob.failed.json")
    assert roadmap.RoadmapJob.model_validate(failed, strict=False).error_code == "ROADMAP_INVALID"
    broken_failed = {k: v for k, v in failed.items() if k != "error_message"}
    with pytest.raises(ValidationError):
        roadmap.RoadmapJob.model_validate(broken_failed, strict=False)


def test_trang_thai_phien_ban_moi_theo_ly_do():
    f = roadmap.status_for_new_version
    assert f("initial", False) == "active" and f("step_edited", True) == "active"
    assert f("behavior_changed", True) == "proposed" and f("user_request", True) == "proposed"
    assert f("goal_changed", True) == "proposed" and f("forecast_drift", True) == "proposed"
    assert f("behavior_changed", False) == "active"  # chưa có bản đang dùng thì bản nào cũng dùng ngay


def test_cedar_cua_tool_moi_dung_dang_va_save_roadmap_khong_chan_theo_token():
    policies = REPO / "gateway" / "policies"
    for target, name in (
        ("forecast", "get_resilience_score"),
        ("forecast", "stress_test"),
        ("planner", "optimize_allocation"),
        ("planner", "save_roadmap"),
        ("planner", "get_roadmap"),
    ):
        text = (policies / f"{name}.cedar").read_text(encoding="utf-8")
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))
        assert f'action == AgentCore::Action::"{target}___{name}"' in code, name
        assert "context.input has user_id && context.input.user_id == principal.id" in code
        assert "confirm_token" not in code and not re.search(r"\b[0-9]{6,}\b", code)  # không token, không số gắn cứng
    contract_tools = set()
    for target in ("ledger", "forecast", "knowledge", "planner", "audit"):
        contract_tools |= {t["name"] for t in load_json(CONTRACTS / "tools" / f"{target}.json")}
    assert {p.stem for p in policies.glob("*.cedar")} == contract_tools  # mỗi tool đúng một policy (CDK bắt buộc)


def test_get_unclassified_mo_rong_tuong_thich_nguoc():
    ledger = load_json(CONTRACTS / "tools" / "ledger.results.schema.json")["$defs"]
    item = ledger["UnclassifiedItem"]
    assert item["required"] == ["transaction", "suggested_jars"]  # trường bắt buộc cũ không đổi
    assert {"tier", "classified_by", "confidence"} <= set(item["properties"])
    assert not {"tier", "classified_by", "confidence"} & set(item["required"])
    sugg = ledger["JarSuggestion"]
    assert sugg["required"] == ["code", "name"] and {"confidence", "reason"} <= set(sugg["properties"])
    assert tuple(item["properties"]["tier"]["enum"]) == wallet.CLASSIFICATION_TIERS[1:]  # review, ask (auto không vào danh sách)
    assert tuple(item["properties"]["classified_by"]["enum"]) == wallet.CLASSIFIED_BY
    tool = {t["name"]: t for t in load_json(CONTRACTS / "tools" / "ledger.json")}["get_unclassified"]
    assert set(tool["inputSchema"]["properties"]) == {"user_id", "limit"}  # đầu vào không đổi (Lambda ledger chưa đổi)
    assign = {t["name"]: t for t in load_json(CONTRACTS / "tools" / "ledger.json")}["assign_jar"]
    assert set(assign["inputSchema"]["properties"]) == {"user_id", "transaction_id", "jar", "remember", "confirm_token"}


# =====================================================================================
# REST
# =====================================================================================
PHASE4_PATHS = {
    ("GET", "/resilience"): "forecast",
    ("GET", "/resilience/shocks"): "forecast",
    ("POST", "/resilience/stress"): "forecast",
    ("GET", "/roadmap"): "ledger",
    ("GET", "/roadmap/versions"): "ledger",
    ("GET", "/roadmap/diff"): "ledger",
    ("POST", "/roadmap/steps/{step_id}/decision"): "ledger",
    ("POST", "/roadmap/steps/{step_id}/edit"): "ledger",
    ("POST", "/roadmap/versions/{version}/decision"): "ledger",
    ("POST", "/roadmap/regenerate"): "ledger",
    ("GET", "/roadmap/jobs/{job_id}"): "ledger",
    ("GET", "/review"): "ledger",
    ("POST", "/review/daily-ask/skip"): "ledger",
}


def test_ba_muoi_hai_endpoint_phase_4_dung_lambda_va_khong_qua_token():
    assert len(PHASE4_PATHS) == 13
    for (method, path), lam in PHASE4_PATHS.items():
        op = SPEC["paths"][path][method.lower()]
        assert op.get("x-lambda", "ledger") == lam, path
        assert op["tags"][0] in {"resilience", "roadmap", "review"}
        assert "428" not in op["responses"], path  # không đổi số dư nên không đòi token
        text = json.dumps(op, ensure_ascii=False)
        assert "confirm_token" not in text, path
    # POST của điểm chống chịu chỉ để có thân yêu cầu
    assert "không ghi gì" in SPEC["paths"]["/resilience/stress"]["post"]["description"]
    assert not any(p.startswith(("/assign", "/review/assign", "/roadmap/confirm")) for p in SPEC["paths"])


def test_sua_hu_dung_lai_assign_jar_qua_confirmations_khong_co_duong_ghi_thu_hai():
    for _, path in PHASE4_PATHS:
        assert not any(w in path for w in ("assign", "jar", "confirm")), path  # không endpoint gán hũ hay xác nhận riêng
    desc = SPEC["paths"]["/review"]["get"]["description"]
    assert "assign_jar" in desc and "POST /confirmations" in desc and "always" in desc
    assert "assign_jar" in SPEC["info"]["description"]
    assert "assign_jar" in SCHEMAS["ToolName"]["enum"]  # đường ghi hũ có sẵn từ phase 2
    assert "assign_jar" in wallet.ACTION_TOOLS and "assign_jar" in wallet.AGENT_WRITE_TOOLS


def test_luu_lo_trinh_khong_qua_token_va_hanh_dong_doi_tien_van_qua_confirm():
    info = SPEC["info"]["description"]
    assert "KHÔNG qua" in info and "token" in info and "POST /confirmations" in info
    decision = SPEC["paths"]["/roadmap/steps/{step_id}/decision"]["post"]["description"]
    assert "KHÔNG đổi số dư" in decision and "KHÔNG tự thực hiện" in decision
    edit = SPEC["paths"]["/roadmap/steps/{step_id}/edit"]["post"]["description"]
    assert "KHÔNG sinh lại toàn bộ" in edit and "feedback" in edit and "step_edited" in edit
    regen = SPEC["paths"]["/roadmap/regenerate"]["post"]["description"]
    assert "CHÍNH job đó" in regen and "GET /roadmap/jobs/{job_id}" in regen
    for ref in ("RoadmapStepDecisionRequest", "RoadmapStepEditRequest", "RoadmapVersionDecisionRequest", "RegenerateRoadmapRequest", "StressRequest"):
        assert SCHEMAS[ref]["additionalProperties"] is False and "user_id" not in SCHEMAS[ref]["properties"]


def test_enum_rest_khop_hang_so():
    assert tuple(SCHEMAS["RoadmapStepDecisionRequest"]["properties"]["decision"]["enum"]) == wallet.ROADMAP_DECISIONS
    assert tuple(SCHEMAS["RoadmapVersionDecisionRequest"]["properties"]["decision"]["enum"]) == wallet.ROADMAP_VERSION_DECISIONS
    which = next(p for p in SPEC["paths"]["/roadmap"]["get"]["parameters"] if p.get("name") == "which")
    assert tuple(which["schema"]["enum"]) == wallet.ROADMAP_WHICH
    mode = next(p for p in SPEC["paths"]["/review"]["get"]["parameters"] if p.get("name") == "mode")
    assert tuple(mode["schema"]["enum"]) == wallet.REVIEW_MODES
    job = SCHEMAS["RoadmapJob"]["properties"]
    assert tuple(job["status"]["enum"]) == wallet.ROADMAP_JOB_STATUSES
    assert tuple(job["trigger"]["enum"]) == wallet.ROADMAP_JOB_TRIGGERS
    assert tuple(job["stage"]["enum"]) == wallet.ROADMAP_JOB_STAGES
    assert SCHEMAS["RoadmapStepEditRequest"]["anyOf"] == [{"required": ["amount_vnd"]}, {"required": ["due_date"]}]


def test_regenerate_tra_http_200_khong_202_de_khop_bang_ma_trang_thai():
    codes = SPEC["paths"]["/roadmap/regenerate"]["post"]["responses"]
    assert "200" in codes and "202" not in codes
    assert not any(m == "patch" for item in SPEC["paths"].values() for m in item)  # CORS chỉ GET, POST, OPTIONS


def test_cac_khoi_phan_hoi_rest_la_cung_khoi_voi_tool_va_chat():
    refs = {
        "ResilienceScoreResponse": "../blocks/resilience_score.schema.json",
        "StressResultResponse": "../blocks/stress_result.schema.json",
        "RoadmapResponse": "../blocks/roadmap.schema.json",
        "RoadmapDiffResponse": "../blocks/roadmap_diff.schema.json",
        "ReviewListResponse": "../blocks/review_list.schema.json",
    }
    for name, ref in refs.items():
        assert SCHEMAS[name]["$ref"] == ref, name
    assert SCHEMAS["ShocksResponse"]["$ref"] == "../tools/forecast.results.schema.json#/$defs/ListShocksData"


def test_fixture_shocks_response_khop_file_du_lieu():
    resp = load_json(CONTRACTS / "fixtures/rest/ShocksResponse.default.json")
    assert resp["shocks"] == [
        json.loads(s.summary().model_dump_json(exclude_none=True)) for s in resp_shocks()
    ]


def resp_shocks():
    return resilience.load_shock_set().shocks


# =====================================================================================
# Sự kiện
# =====================================================================================
def test_su_kien_phase_4_event_id_bang_id_doi_tuong_va_khong_co_pii():
    flag = load_json(CONTRACTS / "fixtures/events/behavior.changed.confirmed.json")
    assert flag["event_id"] == flag["flag_id"] and flag["method"] == "pelt"
    assert (flag["new_weekly_vnd"] > flag["old_weekly_vnd"]) == (flag["direction"] == "up")
    for p in (CONTRACTS / "fixtures/events").glob("roadmap.regeneration_requested.*.json"):
        d = load_json(p)
        assert d["event_id"] == d["job_id"] and "note" not in d
        assert d["trigger"] in wallet.ROADMAP_JOB_TRIGGERS
    behavior = load_json(CONTRACTS / "events/behavior.changed.schema.json")
    assert set(behavior["properties"]["direction"]["enum"]) == set(wallet.BEHAVIOR_DIRECTIONS)
    regen = load_json(CONTRACTS / "events/roadmap.regeneration_requested.schema.json")
    assert tuple(regen["properties"]["trigger"]["enum"]) == wallet.ROADMAP_JOB_TRIGGERS


def test_phuong_phap_phat_hien_dung_cho_dung_giai_doan():
    # CUSUM và PageHinkley chỉ để "nghi" (không phát sự kiện), PELT xác nhận (phát behavior.changed); bảng có đủ ba phương pháp
    assert wallet.BEHAVIOR_METHODS == ("cusum", "page_hinkley", "pelt")
    assert wallet.BEHAVIOR_FLAG_STATUSES == ("suspected", "confirmed", "dismissed", "applied")
    assert load_json(CONTRACTS / "events/behavior.changed.schema.json")["properties"]["method"] == {
        "description": "Phương pháp xác nhận: luôn là pelt.",
        "const": "pelt",
    }


# =====================================================================================
# Tài liệu
# =====================================================================================
def test_file_phase_co_muc_quyet_dinh_hop_dong_va_cho_cac_luong_sau():
    text = (REPO / "docs/plan/phases/phase-4-chong-chiu-lo-trinh.md").read_text(encoding="utf-8")
    assert "## Quyết định hợp đồng phase 4" in text and "### Cho các luồng sau" in text
    for who in ("Luồng A", "Luồng B", "Luồng C", "Luồng D"):
        assert who in text.split("### Cho các luồng sau", 1)[1]
    assert "0052" in text
