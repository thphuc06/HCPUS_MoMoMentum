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


def test_mo_ta_no_outflow_expected_theo_nghia_du_lieu_khop_loi_giao_dien():
    """#39: cờ `no_outflow_expected` mô tả theo nghĩa dữ liệu như lời mới của giao diện cho hũ để dành: số dư không xuống dưới mức hôm
    nay, giữ nguyên hoặc chỉ tăng khi lương về. Không mô tả cờ thành "không có khoản chi" hay "số dư không giảm" (hũ để dành còn tiền
    có thể có khoản rút tay mà dự báo không tính)."""
    text = writer.TASKS["forecast"]
    field = text[text.index("no_outflow_expected") :]
    assert "giữ nguyên" in field and "lương về" in field
    assert "số dư không giảm" not in field and "không có khoản chi" not in field


def _new_account_credit_check() -> dict:
    """Kiểm tra trước khi chi trên tài khoản mới (lượt thấy trên app 26/11, #39): món 200.000 ₫, nếu trả sau thì món tốn 233.000 ₫ gồm
    phí 33.000 ₫; không có ngoại tệ."""
    from agent_helpers import fixture

    payload = fixture("affordability_check.ok.json")
    cost = payload["data"]["credit"]["cost"]
    cost.update(principal_vnd=200_000, fee_added_vnd=33_000, item_cost_vnd=233_000, existing_due_vnd=0, total_due_vnd=233_000)
    return payload


def test_phan_tra_sau_cua_kiem_tra_truoc_khi_chi_tach_goc_va_phi():
    from yofina_agent.compact import compact_affordability

    credit = compact_affordability(_new_account_credit_check())["credit"]
    assert (credit["principal_text"], credit["fee_added_text"], credit["item_cost_text"]) == ("200.000 ₫", "33.000 ₫", "233.000 ₫")
    task = writer.TASKS["affordability"]
    for field in ("item_cost_text", "principal_text", "fee_added_text", "total_due_text", "existing_due_text"):
        assert field in task  # nghĩa của từng con số Trả sau nói rõ ở nhiệm vụ


def test_cau_ve_ty_gia_chi_co_khi_ban_gon_co_ty_gia():
    from yofina_agent.compact import compact_affordability

    compact = compact_affordability(_new_account_credit_check())
    plain = writer.build_writer_prompt("affordability", "ăn tối 200k có ổn không", compact)
    assert "chuyển đổi" not in plain and "tỷ giá" not in plain
    with_fx = writer.build_writer_prompt("affordability", "q", {**compact, "exchange_rate": {"currency": "USD"}})
    assert writer.FX_GUIDE in with_fx and "phí chuyển đổi ngoại tệ" in with_fx
