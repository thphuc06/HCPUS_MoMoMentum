"""Luật dự phòng khi model không dùng được (trần = 0, model id sai) cho what-if và kiểm tra trước khi chi.

Chứng minh bằng mã (không cần model): câu what-if/kiểm tra có đủ số tiền, cách trả và hũ thì đi hết đường tất định
(`classify_by_rules` -> `resolve_clarify` -> `deterministic_spec` -> `validate_spec`), không rơi vào câu hỏi lại hay "chưa dựng được".
Danh sách hũ là dữ liệu đầu vào của test, không nằm trong mã sản phẩm.
"""

from __future__ import annotations

import pytest
from yofina_agent.clarify import missing_slot, resolve_clarify
from yofina_agent.fallback import classify_by_rules
from yofina_agent.jars import resolve_jar
from yofina_agent.whatif import deterministic_spec, validate_spec

JARS = [
    {"code": "an_uong", "name": "Ăn uống"},
    {"code": "di_lai", "name": "Đi lại"},
    {"code": "hoa_don", "name": "Hóa đơn"},
    {"code": "giai_tri", "name": "Giải trí"},
    {"code": "du_lich", "name": "Du lịch"},
    {"code": "du_phong", "name": "Dự phòng"},
]


def spec_for(text: str):
    r = classify_by_rules(text)
    assert r is not None and r.intent == "what_if", (text, r)
    assert resolve_clarify(r) is None, f"không được hỏi lại: {text}"
    return validate_spec(deterministic_spec(r, JARS) or {})


def test_what_if_du_so_tien_cach_tra_va_hu_dung_spec_tat_dinh():
    spec = spec_for("Nếu mua tai nghe 500 nghìn từ hũ Giải trí thì sao")
    assert spec is not None
    assert (spec["kind"], spec["amount_vnd"], spec["funding_source"], spec["jar_code"]) == (
        "one_time_purchase",
        500_000,
        "jar",
        "giai_tri",
    )
    assert spec["label"] == "tai nghe"


@pytest.mark.parametrize(
    ("text", "amount", "jar"),
    [
        ("giả sử mua laptop 15 triệu trong hũ Du lịch thì sao", 15_000_000, "du_lich"),
        ("Nếu mua giày 400k bằng tiền hũ ăn uống thì sao", 400_000, "an_uong"),
        ("nếu tôi mua quà 1tr2 từ Đi lại thì sao", 1_200_000, "di_lai"),
    ],
)
def test_what_if_mua_bang_tien_hu_nhieu_cach_noi(text, amount, jar):
    spec = spec_for(text)
    assert spec is not None
    assert (spec["kind"], spec["amount_vnd"], spec["jar_code"]) == (
        "one_time_purchase",
        amount,
        jar,
    )


def test_what_if_tra_sau_khong_can_hu():
    spec = spec_for("Nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao")
    assert spec is not None
    assert (spec["kind"], spec["amount_vnd"], spec["funding_source"]) == (
        "bnpl_purchase",
        1_200_000,
        "credit",
    )
    assert "jar_code" not in spec


def test_what_if_tra_sau_kem_hu_tinh_chi_tieu():
    spec = spec_for("Nếu mua tai nghe 1,2 triệu bằng Trả Sau tính vào hũ Giải trí thì sao")
    assert spec is not None and spec["kind"] == "bnpl_purchase" and spec["jar_code"] == "giai_tri"


def test_what_if_chuyen_hu_la_kich_ban_chu_khong_phai_lenh_chuyen():
    r = classify_by_rules("Nếu chuyển 300k từ Giải trí sang Ăn uống thì sao")
    assert r.intent == "what_if" and r.params.scenario_kind == "jar_transfer"
    assert (r.params.from_jar_text, r.params.to_jar_text, r.params.amount_vnd) == (
        "giai tri",
        "an uong",
        300_000,
    )
    spec = validate_spec(deterministic_spec(r, JARS) or {})
    assert spec is not None
    assert (spec["kind"], spec["amount_vnd"], spec["from_jar"], spec["to_jar"]) == (
        "jar_transfer",
        300_000,
        "giai_tri",
        "an_uong",
    )
    # câu lệnh chuyển thật (không "thì sao") vẫn là move
    assert classify_by_rules("chuyển 300k từ Giải trí sang Ăn uống").intent == "move"


def test_kiem_tra_truoc_khi_chi_co_hu_nguon_va_ten_nguoi_nhan():
    r = classify_by_rules("Chuyển 250 nghìn từ hũ Hóa đơn cho người nhận demo có ổn không")
    assert r.intent == "affordability"
    p = r.params
    assert (p.amount_vnd, p.funding, p.label) == (250_000, "jar", "người nhận demo")
    assert resolve_jar(p.jar_text, JARS).code == "hoa_don"
    assert missing_slot(r) is None and resolve_clarify(r) is None


@pytest.mark.parametrize(
    ("text", "amount", "jar"),
    [
        (
            "kiểm tra giúp mình mua laptop 15 triệu trong hũ Du lịch được không",
            15_000_000,
            "du_lich",
        ),
        ("quẹt 90k từ hũ Ăn uống có ổn không", 90_000, "an_uong"),
    ],
)
def test_kiem_tra_truoc_khi_chi_nhieu_cach_noi(text, amount, jar):
    r = classify_by_rules(text)
    assert r.intent == "affordability" and r.params.amount_vnd == amount
    assert resolve_jar(r.params.jar_text, JARS).code == jar
    assert missing_slot(r) is None


def test_thieu_du_kien_thi_de_luong_chinh_hoi_lai_khong_doan():
    # thiếu số tiền
    r = classify_by_rules("nếu mua cái điện thoại thì sao")
    assert r.intent == "what_if" and r.params.amount_vnd is None and missing_slot(r) == "amount"
    # có tiền nhưng không nói trả bằng gì
    r = classify_by_rules("Nếu mua tai nghe 500 nghìn thì sao")
    assert (
        r.params.funding is None
        and r.params.jar_text is None
        and missing_slot(r) == "funding_source"
    )
    # "từ tháng sau" là thời gian, không phải tên hũ
    r = classify_by_rules("Nếu mua áo 300k từ tháng sau thì sao")
    assert r.params.jar_text is None and missing_slot(r) == "funding_source"
    # kiểm tra trước khi chi mà không có hũ nguồn: hỏi hũ nào
    r = classify_by_rules("chuyển 250k cho bạn có ổn không")
    assert (
        r.intent == "affordability" and r.params.jar_text is None and missing_slot(r) == "pay_jar"
    )


@pytest.mark.parametrize(
    "text",
    [
        "nên mua cổ phiếu nào",
        "Nếu mua cổ phiếu VNM 5 triệu thì sao",
        "kiểm tra giúp mình mua bitcoin 2 triệu từ hũ Giải trí được không",
        "chuyển 5 triệu mua chứng khoán có ổn không",
        "xin chào",
        "chào bạn, hôm nay bạn khỏe không",
        "cảm ơn nhé",
        "bạn là ai",
        "   ",
    ],
)
def test_cau_ngoai_pham_vi_hoac_chao_hoi_khong_bi_nhan_nham(text):
    assert classify_by_rules(text) is None
