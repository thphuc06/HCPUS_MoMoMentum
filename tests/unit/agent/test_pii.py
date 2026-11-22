"""PII: che SĐT, CCCD/CMND, số tài khoản, thẻ, email; không che số tiền."""

from __future__ import annotations

import pytest

from yofina_core.pii import mask_pii, mask_text


@pytest.mark.parametrize(
    "raw,placeholder",
    [
        ("gọi mình số 0912345678 nhé", "[SĐT]"),
        ("sđt +84 912 345 678", "[SĐT]"),
        ("zalo 091.234.5678", "[SĐT]"),
        ("số 84912345678", "[SĐT]"),
        ("cccd 079203001234", "[CCCD]"),
        ("của mình là 079203001234", "[CCCD]"),
        ("cmnd số 025123456", "[CCCD]"),
        ("stk 1234567890123", "[STK]"),
        ("số tài khoản: 9704123456", "[STK]"),
        ("chuyển vào 19036789012345", "[STK]"),
        ("thẻ 4111 1111 1111 1111", "[THẺ]"),
        ("mail an.nguyen@example.com đi", "[EMAIL]"),
    ],
)
def test_che_pii(raw: str, placeholder: str) -> None:
    res = mask_pii(raw)
    assert placeholder in res.text
    assert res.changed
    digits = [c for c in res.text if c.isdigit()]
    assert len(digits) <= 3  # không còn dãy số định danh


@pytest.mark.parametrize(
    "raw",
    [
        "nếu mua tai nghe 1.200.000 ₫ bằng trả sau thì sao",
        "tiền trọ 2,5 triệu đóng ngày 1",
        "chuyển 250000 từ hũ giải trí sang hóa đơn",
        "lương 15000000 về ngày 5",
        "mua điện thoại 15tr",
        "tài khoản ăn uống còn 500000",
        "ngày 05/12/2026 đến hạn",
        "hũ ăn uống 12000000",
    ],
)
def test_khong_che_so_tien(raw: str) -> None:
    res = mask_pii(raw)
    assert res.text == raw
    assert not res.changed


def test_giu_tu_khoa_va_dem_theo_loai() -> None:
    res = mask_pii("stk 1234567890123, sđt 0912345678, mail a@b.co")
    assert res.text == "stk [STK], sđt [SĐT], mail [EMAIL]"
    assert dict(res.counts) == {"account": 1, "phone": 1, "email": 1}


def test_mask_text_la_ham_rut_gon() -> None:
    assert mask_text("0912345678") == "[SĐT]"
    assert mask_text("") == ""
