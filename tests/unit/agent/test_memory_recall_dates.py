"""Lượt hỏi bộ nhớ hiện đúng ngày tháng người dùng tự kể (#39, lỗi 3 của báo cáo NN).

Ca thật (Runtime v32, 26/11): "bạn đang lưu những thông tin nào về mình" liệt kê "Muốn để dành tiền trong Hũ Dự phòng trước Tết âm lịch
[số], hạn [số]" trong khi màn Bộ nhớ của tôi (`GET /memory`) có đủ "2027" và "05/02/2027". Chữ hiện cho người dùng giữ ngày tháng; số
tiền vẫn che; chữ vào prompt (người viết, Analyst) vẫn che mọi con số trừ giờ (bộ nhớ không là căn cứ cho con số hay ngày).
"""

from __future__ import annotations

import asyncio

import pytest
from test_memory import FakeMemoryClient, ns, rec, run_memory_turn, settings
from yofina_agent import memory as m

from agent_helpers import route_response

FACT = "Muốn để dành 5 triệu trong Hũ Dự phòng trước Tết âm lịch 2027, hạn 05/02/2027"


@pytest.mark.parametrize(
    "raw, kept, gone",
    [
        (FACT, ["Tết âm lịch 2027", "hạn 05/02/2027"], ["5 triệu"]),
        ("Lương về ngày 5 hằng tháng, đóng tiền trọ trước mùng 10 tháng 2", ["ngày 5", "mùng 10 tháng 2"], []),
        ("Đi Đà Lạt từ 24-12 đến 26/12 năm 2026", ["24-12", "26/12", "năm 2026"], []),
        # số đếm, phần trăm (bản ghi cũ chép từ lời trợ lý) vẫn không hiện; số tiền vẫn che
        ("Cuối tuần chi 37% tổng chi, trong 47 ngày, 1.200.000 ₫", [], ["37", "47", "1.200.000"]),
    ],
)
def test_chu_hien_cho_nguoi_dung_giu_ngay_thang_van_che_so_tien(raw, kept, gone):
    shown = m.sanitize_recalled(raw, 300, keep_dates=True)
    for k in kept:
        assert k in shown, shown
    for g in gone:
        assert g not in shown, shown
    if "triệu" in raw or "₫" in raw:
        assert m.AMOUNT_PLACEHOLDER in shown
    # chữ vào prompt không đổi: mọi con số trừ giờ thành [số]
    prompt = m.sanitize_recalled(raw, 300)
    assert not any(ch.isdigit() for ch in prompt), prompt


def test_luot_hoi_bo_nho_liet_ke_ngay_thang_dung_nhu_nguoi_dung_ke():
    client = FakeMemoryClient(
        {
            ns("preference"): [rec(ns("preference"), "Đừng nhắc trước 9 giờ sáng")],
            ns("fact"): [rec(ns("fact"), FACT, rid="mem-" + "e" * 40)],
        }
    )
    events, _ = run_memory_turn(
        [route_response(intent="memory", memory_action="recall")], client, text="bạn đang lưu những thông tin nào về mình"
    )
    said = "".join(e.delta for e in events if e.type.value == "TEXT_MESSAGE_CONTENT")
    assert said.startswith(m.TEXT_RECALL_HEAD)
    assert "trước Tết âm lịch 2027, hạn 05/02/2027" in said and m.NUMBER_PLACEHOLDER not in said
    assert "5 triệu" not in said and m.AMOUNT_PLACEHOLDER in said  # không nới quy tắc che số tiền
    assert "9 giờ" in said
    assert client.ingests == []


def test_khoi_prompt_van_che_ngay_thang():
    async def go() -> str:
        tm = m.TurnMemory(m.AgentMemory(settings(), FakeMemoryClient({ns("fact"): [rec(ns("fact"), FACT)]})))
        tm.start("3f2a9c10-1b2c-4d5e-8f90-a1b2c3d4e5f6", "Tết")
        return await tm.prompt_block()

    block = asyncio.run(go())
    assert "05/02/2027" not in block and "2027" not in block and m.NUMBER_PLACEHOLDER in block
