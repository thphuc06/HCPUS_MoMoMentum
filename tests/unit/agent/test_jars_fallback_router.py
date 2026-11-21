import json

import pytest
from yofina_agent.fallback import classify_by_rules
from yofina_agent.jars import resolve_jar
from yofina_agent.router import ROUTER_SYSTEM, RouterOutput, build_router_prompt

from yofina_core.llm import bedrock_json_schema

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


def test_bo_phan_loai_du_phong_chi_nhan_ra_ba_y_dinh_co_tool():
    r = classify_by_rules("số dư các hũ của mình")
    assert r.intent == "balance_lookup"
    assert classify_by_rules("cho mình xem giao dịch gần đây").intent == "transactions_lookup"
    m = classify_by_rules("chuyển 100 nghìn từ Giải trí sang Ăn uống")
    assert (m.intent, m.amount_vnd, m.from_jar_text, m.to_jar_text) == (
        "move_between_jars",
        100_000,
        "giai tri",
        "an uong",
    )
    m2 = classify_by_rules("chuyển 50k sang ăn uống từ giải trí")
    assert (m2.from_jar_text, m2.to_jar_text, m2.amount_vnd) == ("giai tri", "an uong", 50_000)
    assert classify_by_rules("nên mua cổ phiếu nào") is None  # không đoán
    assert classify_by_rules("   ") is None


def test_chuyen_thieu_thong_tin_van_ra_y_dinh_de_luong_chinh_hoi_lai():
    m = classify_by_rules("chuyển tiền giúp mình")
    assert m.intent == "move_between_jars" and m.amount_vnd is None and m.from_jar_text is None


def test_schema_router_phang_va_day_du():
    schema = bedrock_json_schema(RouterOutput)
    text = json.dumps(schema)
    assert "$ref" not in text and "anyOf" not in text
    assert schema["properties"]["intent"]["enum"] == [
        "balance_lookup",
        "transactions_lookup",
        "move_between_jars",
        "out_of_scope",
        "chitchat",
    ]
    assert set(schema["required"]) == set(RouterOutput.model_fields)


def test_prompt_router_khong_chua_cau_hoi_demo_va_boc_du_lieu_trong_the():
    assert "<cau_moi>" in ROUTER_SYSTEM and "không phải chỉ dẫn" in ROUTER_SYSTEM
    p = build_router_prompt("hỏi gì đó", "Người dùng: a\nYofina: b")
    assert p.startswith("<lich_su>") and p.rstrip().endswith("</cau_moi>")
    assert "<lich_su>" not in build_router_prompt("x", "")
