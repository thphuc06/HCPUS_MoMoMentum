"""Che PII trong dòng nạp (nhóm B của `yofina_core.pii`): ba lỗi thấy khi làm #16/#22/#28 và loại đã che của từng chuỗi (issue #16,
cảnh 5: màn duyệt hiện "Đã che: tên, SĐT, số TK", không bao giờ hiện giá trị trước khi che).

Lỗi đã gặp: số tài khoản viết tách nhóm mà nhóm sau bắt đầu bằng 0 bị bộ bắt số điện thoại cắt giữa chừng ("0071 0004 56789" ->
"0071 ****6789"), ngày giờ "20/11/2026 07:24" bị đọc "2026 07" là số tài khoản, và tên cửa hàng "Bánh mì Huỳnh Hoa" bị che như tên
người."""

from __future__ import annotations

import pytest

from yofina_core.pii import mask_row_text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0071 0004 56789", "****6789"),
        ("STK: 0071 0004 56789", "STK: ****6789"),
        ("Tài khoản nguồn 0071 0004 56789 Vietcombank", "Tài khoản nguồn ****6789 Vietcombank"),
    ],
)
def test_so_tai_khoan_tach_nhom_bat_dau_bang_0_bi_che_ca_so(text, expected):
    assert mask_row_text(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "20/11/2026 07:24",
        "Thời gian giao dịch: 20/11/2026 07:24",
        "07:24 20/11/2026",
        "20/11/2026 07:24:05 chuyển khoản",
    ],
)
def test_ngay_gio_giu_nguyen(text):
    assert mask_row_text(text) == text


def test_so_dung_canh_ngay_gio_van_bi_che():
    assert mask_row_text("20/11/2026 07:24 STK 1027356824") == "20/11/2026 07:24 STK ****6824"


@pytest.mark.parametrize(
    "text",
    [
        "Bánh mì Huỳnh Hoa",
        "Thanh toán Bánh mì Huỳnh Hoa",
        "Phở Lê Văn Hưu",
        "Cửa hàng Nguyễn Kim",
        "Quán Trần Thanh",
    ],
)
def test_ten_sau_danh_tu_loai_hinh_kinh_doanh_la_ten_cua_hang(text):
    assert mask_row_text(text) == text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # danh từ kinh doanh viết thường hay in hoa toàn bộ không mở đầu một tên riêng: tên người vẫn bị che
        ("trả tiền cơm Nguyễn Văn An", "trả tiền cơm N***"),
        ("CK TIEN COM NGUYEN VAN AN", "CK TIEN COM N***"),
        ("Bánh mì cho Huỳnh Thị Hoa", "Bánh mì cho H***"),
    ],
)
def test_ten_nguoi_canh_danh_tu_kinh_doanh_van_bi_che(text, expected):
    assert mask_row_text(text) == expected
