"""Che tên người trong văn bản tự do (`mask_names`, `mask_row_text`, `looks_like_person`) và dấu thời gian trong bản ghi bộ nhớ.

Lỗi đã gặp (phase 5, 24/11): vòng gom tên dừng ở từ thông dụng, mà tập đó có "thi", "an", "tien"..., nên "NGUYEN THI A;nop tien;"
giữ nguyên tên và "NGUYEN VAN AN" thành "N*** AN"; ngược lại "nhắc đến họ buổi sáng" (bản ghi sở thích) bị che thành "H*** sáng",
và "timestamp 1795505552861" của tóm tắt phiên bị che thành "[STK]"."""

from __future__ import annotations

import pytest

from yofina_core.pii import (
    PiiPolicy,
    looks_like_person,
    mask_counterparty,
    mask_names,
    mask_pii,
    mask_row_text,
    strip_epoch_timestamps,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # không dấu, in hoa, có tên lót THI/VAN (trùng từ thông dụng "thi", tên "AN" trùng "ăn")
        ("NGUYEN THI A;nop tien;", "N***;nop tien;"),
        ("chuyen tien cho NGUYEN VAN AN", "chuyen tien cho N***"),
        ("NGUYEN VAN A THANH TOAN HOA DON", "N*** THANH TOAN HOA DON"),
        ("PHAM THI THU HUONG CK TIEN NHA", "P*** CK TIEN NHA"),
        # có dấu, viết kiểu tên riêng
        ("chuyển tiền cho Nguyễn Thị An", "chuyển tiền cho N***"),
        ("Nguyễn Văn An chuyển tiền", "N*** chuyển tiền"),
        ("Trần Thị Thanh Hoa", "T***"),
        ("chuyển cho Lê Thanh Toàn", "chuyển cho L***"),
        # tên một chữ sau họ (chữ cái hoặc tên trùng từ thông dụng)
        ("TRAN B chuyen khoan", "T*** chuyen khoan"),
        ("Lê An", "L***"),
        ("LE AN", "L***"),
        # viết thường ngay sau từ dẫn
        ("chuyen tien cho nguyen van an", "chuyen tien cho N***"),
        ("chuyen cho tran minh khoa tien nha", "chuyen cho T*** tien nha"),
        ("chuyen cho mai thi lan", "chuyen cho M***"),
    ],
)
def test_che_ten_nguoi(text, expected):
    assert mask_row_text(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Người dùng không muốn nhắc đến họ buổi sáng.",  # "họ" là đại từ, "buổi" không phải tên
        "Không nhắc người dùng vào buổi sáng.",
        "Đừng nhắc mình vào buổi sáng, ưu tiên hũ Du lịch.",
        "mua cho đồ ăn trưa",  # "đồ" trùng họ Đỗ khi bỏ dấu
        "gửi cho mai đi chợ",  # "mai" trùng họ Mai
        "ăn uống ở Hà Nội",
        "Siêu thị Co.op",
        "Hũ Du lịch",
        "nop tien",
    ],
)
def test_khong_che_nham_tu_thuong(text):
    assert mask_names(text) == text


def test_ten_nguoi_ca_chuoi_va_doi_tac():
    assert looks_like_person("NGUYEN VAN AN") and looks_like_person("Nguyễn Thị A")
    assert not looks_like_person("Siêu thị Co.op")
    assert mask_counterparty("NGUYEN THI AN") == "N***"
    assert (
        mask_counterparty("TRAN VAN A", policy=PiiPolicy.build(self_names=["Tran Van A"]))
        == "TRAN VAN A"
    )


def test_dau_thoi_gian_unix_khong_bi_che_thanh_so_tai_khoan():
    out = mask_pii("Timestamp bản ghi: 1795505552861 (timestamp 1795505552).").text
    assert "[STK]" not in out and "1795505552861" in out
    # số dài không có từ khóa vẫn là số tài khoản
    assert mask_pii("stk 1795505552861").text == "stk [STK]"
    assert mask_pii("chuyển vào 0123456789012 nhé").text == "chuyển vào [STK] nhé"


def test_bo_dau_thoi_gian_cua_tom_tat_phien():
    raw = (
        '<topic name="Lộ trình">\n'
        "- Thời điểm: timestamp 1795505692694 (ms), tương đương khoảng 2026-11-24 07:34 UTC.\n"
        "- Người dùng yêu cầu lập lại lộ trình.\n"
        "</topic>\n"
        "- **Yêu cầu:** Người dùng hỏi. *(Nguồn: timestamp 1795505552861)*\n"
        "- Timestamp của bản ghi: 1795505552861.\n"
        "- Người dùng hỏi liệu ổn không (timestamp 1795506169868).\n"
        "- Lập lại lộ trình (thời điểm ghi nhận: timestamp 1795505692694 ms, tương đương khoảng 2026-11-24 07:34 UTC)."
    )
    assert strip_epoch_timestamps(raw) == (
        '<topic name="Lộ trình">\n'
        "- Người dùng yêu cầu lập lại lộ trình.\n"
        "</topic>\n"
        "- **Yêu cầu:** Người dùng hỏi.\n"
        "- Người dùng hỏi liệu ổn không.\n"
        "- Lập lại lộ trình."
    )
    assert strip_epoch_timestamps("Không có gì 12/05.") == "Không có gì 12/05."
