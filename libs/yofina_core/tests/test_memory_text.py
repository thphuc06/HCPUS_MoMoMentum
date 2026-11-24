"""Chữ bản ghi bộ nhớ dùng chung cho agent và Lambda ledger: chữ chính, khử trùng giữa sở thích và sự thật, mẩu nhãn rỗng."""

from __future__ import annotations

import json

import pytest

from yofina_core.memory_text import dedupe_by_meaning, drop_empty_labels, record_text, same_meaning


def test_record_text_lay_truong_noi_dung_cua_json():
    pref = {
        "context": "Người dùng nói rõ",
        "preference": "Ưu tiên hũ Du lịch",
        "categories": ["tiết kiệm"],
    }
    assert record_text({"text": json.dumps(pref, ensure_ascii=False)}) == "Ưu tiên hũ Du lịch"
    assert (
        record_text({"text": json.dumps({"fact": "Làm giáo viên"}, ensure_ascii=False)})
        == "Làm giáo viên"
    )
    assert record_text({"text": "  chữ thường  "}) == "chữ thường"
    assert record_text({"text": "{không phải json"}) == "{không phải json"
    assert record_text(None) == "" and record_text({"text": 3}) == ""


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        (
            "Ưu tiên để dành tiền cho hũ Du lịch",
            "Người dùng muốn ưu tiên để dành tiền vào hũ Du lịch.",
            True,
        ),
        (
            "Không nhắc mình vào buổi sáng",
            "Người dùng yêu cầu không nhắc mình vào buổi sáng.",
            True,
        ),
        ("Không nhắc buổi sáng", "Không nhắc buổi tối", False),
        ("Ưu tiên hũ Du lịch", "Đang để dành cho chuyến đi Đà Lạt bằng hũ Du lịch", False),
    ],
)
def test_same_meaning(a, b, same):
    assert same_meaning(a, b) is same


def test_dedupe_giu_thu_tu_goc_va_uu_tien_so_thich():
    rows = [
        (
            "fact",
            "Người dùng muốn ưu tiên để dành tiền vào hũ Du lịch.",
        ),  # mới nhất, nhưng trùng ý sở thích
        ("session_summary", "Ưu tiên để dành tiền cho hũ Du lịch"),  # loại khác: không so
        ("preference", "Ưu tiên để dành tiền cho hũ Du lịch"),
        ("fact", "Làm giáo viên ở Đà Nẵng"),
        ("preference", "Ưu tiên để dành tiền cho hũ Du lịch"),  # cùng loại, giống hệt
    ]
    out = dedupe_by_meaning(rows, text=lambda r: r[1], kind=lambda r: r[0])
    assert out == [rows[1], rows[2], rows[3]]


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        (
            "Thời điểm: , ước tính khoảng 24/11/2026 (UTC). Người dùng hỏi về hũ Du lịch.",
            "Người dùng hỏi về hũ Du lịch.",
        ),
        ("Thời điểm: (mili giây). Hỏi số dư hũ Ăn uống.", "Hỏi số dư hũ Ăn uống."),
        ("Chủ đề: Du lịch. Thời điểm: .", "Chủ đề: Du lịch."),
        ("Tóm tắt:\n- Thời điểm: ,\n- Nội dung: hỏi số dư", "Tóm tắt:\n- Nội dung: hỏi số dư"),
        ("Ưu tiên hũ Du lịch", "Ưu tiên hũ Du lịch"),
        ("Đừng nhắc trước 9:30 sáng.", "Đừng nhắc trước 9:30 sáng."),
        ("Số dư 1.200.000 ₫. Lưu ý: hũ sát.", "Số dư 1.200.000 ₫. Lưu ý: hũ sát."),
    ],
)
def test_drop_empty_labels(raw, want):
    assert drop_empty_labels(raw) == want


def test_drop_empty_labels_chu_rong():
    assert drop_empty_labels("") == "" and drop_empty_labels("Thời điểm: .") == ""
