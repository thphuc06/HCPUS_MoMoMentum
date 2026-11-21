import pytest
from yofina_agent.textutil import extract_amounts, normalize, parse_amount_vnd, ungrounded_amounts


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("chuyển 100 nghìn từ A sang B", 100_000),
        ("chuyển 100k", 100_000),
        ("chuyển 250.000 đồng", 250_000),
        ("1.200.000đ", 1_200_000),
        ("1,2 triệu", 1_200_000),
        ("1.5 tr", 1_500_000),
        ("1tr5", 1_500_000),
        ("2 triệu rưỡi", 2_500_000),
        ("hai trăm", None),
        ("hũ 3 còn ít", None),
        ("ngày 2026-11-21 và 23/11", None),
        ("2 tỷ", 2_000_000_000),
    ],
)
def test_doc_so_tien_viet(text, expected):
    assert parse_amount_vnd(text) == expected


def test_normalize_bo_dau_va_dau_cau():
    assert normalize("Giải trí!") == "giai tri"
    assert normalize("  Đi  lại, ĐÂY ") == "di lai day"


def test_sai_so_theo_do_chinh_xac_hien_thi():
    assert extract_amounts("1,2 triệu")[0] == (1_200_000, pytest.approx(50_000))
    assert extract_amounts("380.000 ₫")[0] == (380_000, 0.5)
    assert extract_amounts("380 nghìn")[0][1] == pytest.approx(50)


def test_kiem_can_cu_so_tien():
    allowed = {380_000, 7_730_000}
    assert ungrounded_amounts("Hũ ăn uống còn 380.000 ₫, tổng 7,7 triệu.", allowed) == []
    assert ungrounded_amounts("Tổng là 8 triệu.", allowed) == [8_000_000]
    assert ungrounded_amounts("Bạn có 7 hũ, 30% là ăn uống, tính đến 2026-11-21.", allowed) == []
    assert ungrounded_amounts("còn 390.000 ₫", allowed) == [390_000]
