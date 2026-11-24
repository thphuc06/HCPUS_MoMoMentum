"""Lời nhắc của writer: độ dài nói một lần ở `WRITER_SYSTEM`, mỗi việc chỉ mô tả dữ liệu và ràng buộc nghiệp vụ (kiểm toán prompt, đợt 2)."""

from __future__ import annotations

import re

from yofina_agent import writer
from yofina_agent.textutil import normalize

#: khuôn số câu cố định ("đúng 1 câu", "1 đến 2 câu", "ĐÚNG 2 câu", "Câu 1 nêu ...")
_SENTENCE_TEMPLATE = re.compile(r"\b(?:dung\s+)?\d+(?:\s+den\s+\d+)?\s+cau\b|\bcau\s+\d+\b")


def test_khong_viec_nao_co_khuon_so_cau():
    for task, text in writer.TASKS.items():
        assert not _SENTENCE_TEMPLATE.search(normalize(text)), task
    assert not _SENTENCE_TEMPLATE.search(normalize(writer.WRITER_SYSTEM))


def test_gioi_han_do_dai_noi_mot_lan_o_he_thong():
    assert "viết ngắn" in writer.WRITER_SYSTEM
    for task, text in writer.TASKS.items():
        assert "ngắn gọn" not in text and "viết ngắn" not in text, task


def test_rang_buoc_nghiep_vu_van_con():
    # điều model không tự biết: không phải điểm tín dụng; thẻ xác nhận chưa chuyển hay lưu gì
    for task in ("resilience", "stress"):
        assert "không phải điểm tín dụng" in writer.TASKS[task]
    assert "Chưa có khoản tiền nào được chuyển" in writer.TASKS["confirm_move"]
    assert "Chưa lưu gì" in writer.TASKS["confirm_action"]


def test_xa_giao_khong_bi_buoc_chem_danh_sach_viec():
    text = writer.TASKS["chitchat"]
    assert "viec_lam_duoc" in text  # danh sách đến từ dữ liệu, không chép trong lời nhắc
    for word in ("xem số dư", "chuyển tiền giữa các hũ"):
        assert word not in text


def test_moi_viec_ghi_trong_turn_deu_co_loi_nhac():
    import inspect

    from yofina_agent import behavior_chat, fee_citation, ingest_chat, memory, turn

    used: set[str] = set()
    for mod in (turn, behavior_chat, fee_citation, ingest_chat, memory):
        src = inspect.getsource(mod)
        used |= set(re.findall(r"\.write(?:_buffered)?\(\s*\"([a-z_]+)\"", src))
    assert used and used <= set(writer.TASKS)
