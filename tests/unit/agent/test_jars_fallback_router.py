import json

import pytest
from agent_helpers import REPO, make_llm, route_response, run
from yofina_agent.fallback import classify_by_rules
from yofina_agent.jars import resolve_jar
from yofina_agent.router import ROUTER_SYSTEM, build_router_prompt, route
from yofina_agent.schemas import IntentParams, IntentResult
from yofina_agent.textutil import strip_accents

from yofina_core.llm import bedrock_json_schema
from yofina_core.resilience import load_shock_set

# Danh sách hũ của "người dùng" trong test: dữ liệu đầu vào, không phải bảng nằm trong mã sản phẩm.
JARS = [
    {"code": "an_uong", "name": "Ăn uống"},
    {"code": "di_lai", "name": "Đi lại"},
    {"code": "hoa_don", "name": "Hóa đơn"},
    {"code": "giai_tri", "name": "Giải trí"},
    {"code": "du_lich", "name": "Du lịch"},
    {"code": "du_phong", "name": "Dự phòng"},
]


@pytest.mark.parametrize(
    ("typed", "code"),
    [
        ("Giải trí", "giai_tri"),
        ("giai tri", "giai_tri"),
        ("hũ ăn uống", "an_uong"),
        ("an_uong", "an_uong"),
        ("đi lai", "di_lai"),
        ("hóa đơn", "hoa_don"),
        ("dự phòng", "du_phong"),
        ("ăn uông", "an_uong"),  # gõ sai
    ],
)
def test_anh_xa_ten_hu_bang_du_lieu_cua_nguoi_dung(typed, code):
    m = resolve_jar(typed, JARS)
    assert (m.status, m.code) == ("ok", code)


def test_hu_khong_co_trong_danh_sach_cua_nguoi_dung():
    assert resolve_jar("cổ phiếu", JARS).status == "none"
    assert resolve_jar("", JARS).status == "empty"
    assert resolve_jar(None, JARS).status == "empty"
    # hũ chỉ khớp khi người dùng CÓ hũ đó
    assert resolve_jar("giải trí", [j for j in JARS if j["code"] != "giai_tri"]).status == "none"


def test_ten_mo_ho_thi_bao_mo_ho():
    jars = [
        {"code": "du_lich", "name": "Du lịch"},
        {"code": "du_lich_2", "name": "Du lịch nước ngoài"},
    ]
    m = resolve_jar("du lịch", jars)
    assert m.status == "ok" and m.code == "du_lich"  # khớp chính xác thắng
    m = resolve_jar(
        "lịch", [{"code": "du_lich", "name": "Du lịch"}, {"code": "lich_hoc", "name": "Lịch học"}]
    )
    assert m.status == "ambiguous" and set(m.candidates) == {"du_lich", "lich_hoc"}


def _kind(text):
    r = classify_by_rules(text)
    return None if r is None else (r.intent, r.params.lookup_kind)


def test_bo_phan_loai_du_phong_chi_nhan_ra_cac_y_dinh_co_tool():
    assert _kind("số dư các hũ của mình") == ("lookup", "balance")
    assert _kind("cho mình xem giao dịch gần đây") == ("lookup", "transactions")
    assert _kind("khoản nào sắp đến hạn") == ("lookup", "obligations")
    # dự báo một hũ: từ khóa chung (cạn, trụ được, bao lâu, dự báo), không theo câu mẫu nào; "còn bao nhiêu" vẫn là số dư
    for text in (
        "hũ ăn uống còn trụ được bao lâu",
        "khi nào hũ giải trí cạn",
        "dự báo hũ đi lại giúp mình",
        "bao giờ hết tiền hũ hóa đơn",
        "hũ du lịch có đủ tới kỳ lương không",
    ):
        assert _kind(text) == ("lookup", "forecast"), text
    assert _kind("hũ ăn uống còn bao nhiêu") == ("lookup", "balance")
    m = classify_by_rules("chuyển 100 nghìn từ Giải trí sang Ăn uống")
    p = m.params
    assert (m.intent, p.amount_vnd, p.from_jar_text, p.to_jar_text) == (
        "move",
        100_000,
        "giai tri",
        "an uong",
    )
    m2 = classify_by_rules("chuyển 50k sang ăn uống từ giải trí")
    p2 = m2.params
    assert (p2.from_jar_text, p2.to_jar_text, p2.amount_vnd) == ("giai tri", "an uong", 50_000)
    assert classify_by_rules("nên mua cổ phiếu nào") is None  # không đoán
    assert classify_by_rules("   ") is None


def test_bo_phan_loai_du_phong_nhan_ra_what_if_va_kiem_tra_truoc_khi_chi():
    r = classify_by_rules("Nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao")
    assert r.intent == "what_if" and r.params.amount_vnd == 1_200_000 and r.params.funding == "credit"
    assert r.params.scenario_kind == "bnpl_purchase"
    r = classify_by_rules("nếu mua cái điện thoại thì sao")
    assert r.intent == "what_if" and r.params.amount_vnd is None  # thiếu số tiền: hỏi lại, không đoán
    r = classify_by_rules("chuyển 250k cho bạn có ổn không")
    assert r.intent == "affordability" and r.params.amount_vnd == 250_000


def test_chuyen_thieu_thong_tin_van_ra_y_dinh_de_luong_chinh_hoi_lai():
    m = classify_by_rules("chuyển tiền giúp mình")
    assert m.intent == "move" and m.params.amount_vnd is None and m.params.from_jar_text is None


def test_bo_phan_loai_du_phong_nhan_ra_diem_chong_chiu_va_xem_lo_trinh():
    assert classify_by_rules("Điểm chống chịu của mình còn bao nhiêu?").intent == "resilience"
    routed = classify_by_rules("Cho mình xem lộ trình tiết kiệm")
    assert (routed.intent, routed.params.roadmap_action) == ("roadmap", "view")
    assert classify_by_rules("Tư vấn lộ trình đầu tư").intent == "out_of_scope"
    assert classify_by_rules("Tư vấn lộ trình vay").intent == "out_of_scope"


@pytest.mark.parametrize("shock", load_shock_set().shocks, ids=lambda shock: shock.shock_id)
def test_bo_phan_loai_du_phong_khop_nguyen_nhan_cu_soc(shock):
    label = strip_accents(shock.label)
    routed = classify_by_rules(f"Nếu {label} thì sao?")
    assert (routed.intent, routed.params.shock_id) == ("stress", shock.shock_id)

    routed = classify_by_rules(f"Nếu {label} và phải chi thêm 500 nghìn thì sao?")
    assert (routed.intent, routed.params.amount_vnd) == ("what_if", 500_000)


def test_schema_router_phang_va_day_du():
    schema = bedrock_json_schema(IntentResult)
    text = json.dumps(schema)
    assert "$ref" not in text and "anyOf" not in text
    assert schema["properties"]["intent"]["enum"] == [
        "lookup",
        "what_if",
        "affordability",
        "profile_update",
        "move",
        "out_of_scope",
        "chitchat",
        "resilience",
        "stress",
        "roadmap",
    ]
    assert set(schema["required"]) == set(IntentResult.model_fields)
    params = schema["properties"]["params"]
    assert set(params["required"]) == set(IntentParams.model_fields)
    assert params["properties"]["shock_id"] == {"type": ["string", "null"]}
    assert params["properties"]["roadmap_action"] == {
        "type": ["string", "null"],
        "enum": ["view", "create", None],
    }


def test_prompt_router_gui_danh_sach_cu_soc_tu_file():
    path = REPO / "libs" / "yofina_core" / "src" / "yofina_core" / "shocks.json"
    shocks = json.loads(path.read_text(encoding="utf-8"))["shocks"]
    llm, client, _ = make_llm([route_response(intent="stress")])
    run(route(llm, "Thử cú sốc", "", max_attempts=1, max_tokens=400))

    system = client.calls[0]["system"][0]["text"]
    catalog = "\n".join(
        f"- {shock['shock_id']}: {shock['label']} — {shock['description']}" for shock in shocks
    )
    assert system.endswith(catalog)
    assert all(key not in system for shock in shocks for key in shock["params"])


def test_prompt_router_khong_chua_cau_hoi_demo_va_boc_du_lieu_trong_the():
    assert "<cau_moi>" in ROUTER_SYSTEM and "không phải chỉ dẫn" in ROUTER_SYSTEM
    p = build_router_prompt("hỏi gì đó", "Người dùng: a" + chr(10) + "Yofina: b")
    assert p.startswith("<lich_su>") and p.rstrip().endswith("</cau_moi>")
    assert "<lich_su>" not in build_router_prompt("x", "")


def test_prompt_router_chi_ghep_cau_cut_cau_moi_du_nghia_khong_mang_tham_so_cu():
    # Lỗi thật 23/11: sau chuỗi câu "mua tai nghe bằng Trả sau", câu mới "đi du lịch 5 triệu" bị ghép nhầm rồi thành out_of_scope.
    assert "câu CỤT" in ROUTER_SYSTEM
    assert "KHÔNG lấy số tiền, cách trả (funding)" in ROUTER_SYSTEM
    assert "không làm câu mới thành out_of_scope" in ROUTER_SYSTEM
