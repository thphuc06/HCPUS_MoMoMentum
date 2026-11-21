from decimal import Decimal

import pytest

from yofina_core.money import format_vnd, format_vnd_short, to_vnd


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1_200_000, "1.200.000 ₫"),
        (Decimal("1200000"), "1.200.000 ₫"),
        ("8260000", "8.260.000 ₫"),
        (Decimal("380000.0000"), "380.000 ₫"),
        (0, "0 ₫"),
        (999, "999 ₫"),
        (1000, "1.000 ₫"),
        (-250_000, "-250.000 ₫"),
        (99_999_999_999_999, "99.999.999.999.999 ₫"),
    ],
)
def test_format_vnd(value, expected):
    assert format_vnd(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1_200_000, "1,2 triệu"),
        (2_000_000, "2 triệu"),
        (1_233_000, "1,2 triệu"),
        (1_250_000, "1,3 triệu"),  # làm tròn nửa lên
        (9_000_000, "9 triệu"),
        (250_000, "250 nghìn"),
        (100_000, "100 nghìn"),
        (1_500, "1,5 nghìn"),
        (999_999, "1 triệu"),  # chạm 1.000 nghìn thì nhảy đơn vị
        (999_500, "999,5 nghìn"),
        (1_000_000_000, "1 tỷ"),
        (2_500_000_000, "2,5 tỷ"),
        (999_999_999, "1 tỷ"),
        (500, "500 ₫"),
        (0, "0 ₫"),
        (-1_200_000, "-1,2 triệu"),
        (Decimal("9740000"), "9,7 triệu"),
    ],
)
def test_format_vnd_short(value, expected):
    assert format_vnd_short(value) == expected


def test_tien_lon_khong_vo_dinh_dang():
    assert format_vnd_short(1_500_000_000_000) == "1.500 tỷ"


def test_to_vnd_chi_nhan_so_nguyen():
    assert to_vnd(Decimal("5")) == 5
    assert to_vnd(" 100000 ") == 100000
    with pytest.raises(ValueError):
        to_vnd(Decimal("100.5"))
    with pytest.raises(ValueError):
        to_vnd("abc")
    with pytest.raises(ValueError):
        to_vnd(Decimal("NaN"))


@pytest.mark.parametrize("bad", [1.5, 100000.0, True, None, [1]])
def test_to_vnd_tu_choi_float_bool_va_kieu_la(bad):
    with pytest.raises(TypeError):
        to_vnd(bad)
