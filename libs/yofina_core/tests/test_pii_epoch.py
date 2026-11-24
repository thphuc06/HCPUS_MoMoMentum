"""Dấu thời gian trong bản ghi bộ nhớ không bị che thành `[STK]`, số tài khoản thật vẫn bị che (kiểm lại Runtime v22, 24/11).

Lỗi gốc: tóm tắt phiên mới của `minh` hiện "Vào thời điểm [STK] (ước tính khoảng 2026-11-24, 08:43 UTC)". Strategy tóm tắt của AgentCore
Memory thấy `contentTimestamp` (số, bắt buộc của `IngestData`) cạnh mỗi lượt và được dặn "Consider the timestamps", nên chép epoch mili
giây vào bản ghi. Bản sửa trước chỉ nhận dạng có chữ "timestamp"; dạng "thời điểm <13 chữ số>" rơi vào luật "từ 10 chữ số liền là số
tài khoản".
"""

from __future__ import annotations

import pytest

from yofina_core.pii import is_epoch_at, mask_pii, strip_epoch_timestamps

LIVE = "Vào thời điểm 1795508600000 (ước tính khoảng 2026-11-24, 08:43 UTC), người dùng hỏi về hũ Giải trí."


def _epoch(text: str, digits: str) -> bool:
    i = text.index(digits)
    return is_epoch_at(text, i, i + len(digits))


def test_ca_that_khong_con_stk_va_bo_ca_cum_thoi_diem():
    assert "[STK]" not in mask_pii(LIVE).text
    assert strip_epoch_timestamps(LIVE) == "Người dùng hỏi về hũ Giải trí."
    # cách ledger dựng chữ cho GET /memory: bỏ dấu thời gian rồi mới che PII
    assert mask_pii(strip_epoch_timestamps(LIVE)).text == "Người dùng hỏi về hũ Giải trí."


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Người dùng hỏi vào thời điểm 1795508600000 (khoảng 2026-11-24 08:43 UTC) về hũ.",
            "Người dùng hỏi về hũ.",
        ),
        ("- Lúc 1795508600 người dùng nhờ lập lộ trình.", "- Người dùng nhờ lập lộ trình."),
        ("- Mốc thời gian: 1795505552861 ms.", None),  # dòng chỉ còn dấu câu thì bỏ
        ("At 1795508600000 (approximately 2026-11-24 08:43 UTC) the user asked", "The user asked"),
        ("The user asked (epoch 1795508600000 ms).", "The user asked."),
        ("Người dùng hỏi 1795508600000 (ước tính 2026-11-24).", "Người dùng hỏi."),
    ],
)
def test_bo_dau_thoi_gian_khong_co_chu_timestamp(raw: str, expected: str | None):
    out = strip_epoch_timestamps(raw)
    assert out == ("" if expected is None else expected)
    assert "[STK]" not in mask_pii(raw).text


@pytest.mark.parametrize(
    "text",
    [
        "Lúc 2026-11-24T08:43:12.861Z người dùng hỏi",
        "Lúc 2026-11-24T08:43:12+07:00 người dùng hỏi",
        "Lúc 20261124T084312Z người dùng hỏi",
        "Ngày 2026-11-24 08:43:12 UTC",
    ],
)
def test_iso_8601_giu_nguyen(text: str):
    assert mask_pii(text).text == text
    assert strip_epoch_timestamps(text) == text


@pytest.mark.parametrize(
    "text",
    [
        "stk 1795508600000",  # có từ khóa: luôn che
        "số tài khoản 12345678",
        "chuyển vào 0123456789012 nhé",
        "chuyển tiền tới 1780205123456 hôm nay",  # 13 chữ số trong khoảng epoch nhưng không có ngữ cảnh thời gian
        "tài khoản 1780205123456 (2026-11-24)",  # ngoặc ngày giờ sau một số tài khoản: vẫn che
        "lúc chuyển khoản tới 1795508600000 (ước tính 2026-11-24)",  # từ khóa tài khoản đứng trước thắng
        "tk lúc 1795508600000",
        "chuyển vào 19036789012345",  # 14 chữ số: không phải epoch
        "lúc 9999999999999",  # ngoài khoảng 2000–2100
    ],
)
def test_so_tai_khoan_that_van_bi_che(text: str):
    assert "[STK]" in mask_pii(text).text
    assert "[STK]" in mask_pii(strip_epoch_timestamps(text)).text


def test_is_epoch_at():
    assert _epoch(LIVE, "1795508600000")
    assert _epoch("timestamp 1795505552", "1795505552")
    assert not _epoch("stk 1795505552861", "1795505552861")
    assert not _epoch("gửi 1795505552861", "1795505552861")
    assert not _epoch("lúc 179550555286", "179550555286")  # 12 chữ số
