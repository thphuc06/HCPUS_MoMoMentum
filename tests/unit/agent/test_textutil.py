from datetime import date

import pytest
from yofina_agent.textutil import (
    extract_amounts,
    goal_date_phrase,
    normalize,
    parse_amount_vnd,
    parse_goal_date,
    ungrounded_amounts,
)


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

# --- hạn mục tiêu (chuyển từ test_phase4_handlers cùng hàm `_roadmap_goal_date` cũ của turn.py) ---------------
TODAY = date(2026, 11, 21)  # ngày mô phỏng của test


@pytest.mark.parametrize(
    "text, expected",
    [
        ("cuối tháng này", date(2026, 11, 30)),
        ("trước cuối tháng này", date(2026, 11, 30)),
        ("cuối tháng sau", date(2026, 12, 31)),
        ("31/12", date(2026, 12, 31)),
        ("15/3", date(2027, 3, 15)),
        ("20/11", date(2027, 11, 20)),  # không có năm và đã qua: năm sau
        ("15/01/2027", date(2027, 1, 15)),
        ("ngày 5 tháng 1 năm 2027", date(2027, 1, 5)),
        ("6 tháng nữa", date(2027, 5, 21)),
        ("2 tuần nữa", date(2026, 12, 5)),
        ("tháng 3 năm sau", date(2027, 3, 31)),
        ("cuối tháng 12 năm sau", date(2027, 12, 31)),
        ("cuối năm", date(2026, 12, 31)),
        ("2027-02-28", date(2027, 2, 28)),
        ("20/11/2026", None),  # đã qua
        ("31/02", None),
        ("sớm nhất có thể", None),
    ],
)
def test_doi_han_muc_tieu_theo_ngay_mo_phong(text, expected):
    assert parse_goal_date(text, TODAY) == expected


@pytest.mark.parametrize(
    "sentence, phrase",
    [
        ("Lập giúp mình lộ trình gom đủ 1 tỷ đồng trong hũ Du lịch trước cuối tháng này", "cuối tháng này"),
        ("Lộ trình để dành 15 triệu ở hũ Mua xe trong 6 tháng nữa nhé", "6 tháng nữa"),
        ("lộ trình gom 20tr hũ Du lịch trước 31/12", "31/12"),
        ("Lộ trình gom 5 triệu vào hũ Tết, hạn Tháng 3 năm sau!", "Tháng 3 năm sau"),
        ("lộ trình 2 triệu cho hũ Quà, xong cuối tháng sau", "cuối tháng sau"),
        ("lộ trình 2 triệu hũ Quà ngày 5  tháng 1 năm 2027", "ngày 5  tháng 1 năm 2027"),
    ],
)
def test_cum_han_giu_nguyen_chu_go_va_doi_cung_ngay_voi_ca_cau(sentence, phrase):
    assert goal_date_phrase(sentence) == phrase
    assert parse_goal_date(phrase, TODAY) == parse_goal_date(sentence, TODAY) is not None


@pytest.mark.parametrize(
    "text",
    ["lộ trình gom 1.5 triệu ở hũ Du lịch", "để dành 1.5tr", "gom đủ 15 triệu ở hũ Mua xe", "sớm nhất có thể", ""],
)
def test_so_tien_khong_bi_doc_thanh_han(text):
    assert goal_date_phrase(text) is None
    assert parse_goal_date(text, TODAY) is None
