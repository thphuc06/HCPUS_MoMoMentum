"""Mức nền bền của chi theo hũ (#39, chủ dự án chốt 26/11): trung vị chi theo tuần trên cửa sổ dài, quy về tháng; chưa đủ tuần hoặc hũ thưa
thì lùi về chi trung bình của cửa sổ gần nhất (cách tính trước 26/11). Dùng chung cho LP phân bổ và đề xuất tỷ lệ của ledger."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from yofina_core.spend_baseline import (
    DEFAULT_BASELINE_MIN_WEEKS,
    DEFAULT_BASELINE_WEEKS,
    BaselineSettings,
    SpendLevel,
    baseline_monthly,
    recent_monthly,
    typical_monthly,
    week_start,
    weekly_totals,
)

S = BaselineSettings(weeks=12, min_weeks=6, month_days=30, fallback_days=30)


def days(*weeks: int) -> list[int]:
    """Chuỗi ngày (cũ tới mới) mà mỗi tuần chi đều `w` mỗi tuần, chia đều 7 ngày."""
    return [w // 7 for w in weeks for _ in range(7)]


def test_tuan_cat_lui_tu_ngay_cuoi_va_bo_cac_tuan_dau_chua_co_chi():
    # 3 ngày lẻ ở đầu không đủ một tuần thì bỏ; tuần mới nhất kết thúc ngày cuối
    daily = [5, 5, 5] + [1] * 7 + [2] * 7
    assert weekly_totals(daily, 12) == [7, 14]
    # tuần đầu chưa có chi (hũ mới tạo) bị bỏ; tuần không chi ở giữa vẫn tính
    assert weekly_totals([0] * 14 + [7] * 7 + [0] * 7 + [7] * 7, 12) == [49, 0, 49]
    assert weekly_totals([0] * 14 + [7] * 7, 12, skip_leading_zero=False) == [0, 0, 49]
    # chỉ lấy tối đa `weeks` tuần gần nhất; giá trị âm, None, Decimal, chuỗi số đều đọc được
    assert weekly_totals([1] * 7 * 20, 12) == [7] * 12
    assert weekly_totals([-5, None, Decimal("3"), "4", 0, 0, 0], 12) == [7]
    assert week_start(date(2026, 11, 20), 2, 0) == date(2026, 11, 7)
    assert week_start(date(2026, 11, 20), 2, 1) == date(2026, 11, 14)


def test_muc_nen_la_trung_vi_theo_tuan_quy_ve_thang():
    assert baseline_monthly(days(*[700_000] * 12), weeks=12, min_weeks=6, month_days=30) == 3_000_000
    # trung vị chẵn: trung bình hai tuần giữa
    daily = days(700_000, 700_000, 700_000, 1_400_000, 1_400_000, 1_400_000)
    assert baseline_monthly(daily, weeks=12, min_weeks=6, month_days=30) == round(1_050_000 * 30 / 7)


def test_dot_tang_hai_tuan_khong_keo_muc_nen_len_con_nhip_moi_giu_qua_nua_cua_so_thi_thanh_muc_nen():
    spike = days(*[840_000] * 10, 2_650_000, 2_650_000)
    base = baseline_monthly(spike, weeks=12, min_weeks=6, month_days=30)
    assert base == 3_600_000
    # chi trung bình 30 ngày gần nhất (cách cũ) bị đợt tăng kéo gần gấp đôi
    assert recent_monthly(spike, 30, 30) > 1.9 * base
    # tháng Tết bốn tuần vẫn chưa thành mức nền với cửa sổ 12 tuần
    assert baseline_monthly(days(*[840_000] * 8, *[2_650_000] * 4), weeks=12, min_weeks=6, month_days=30) == 3_600_000
    # nhịp mới giữ bảy trên mười hai tuần: thành mức nền mới
    assert baseline_monthly(days(*[840_000] * 5, *[2_100_000] * 7), weeks=12, min_weeks=6, month_days=30) == 9_000_000


def test_chua_du_tuan_hoac_hu_thua_thi_lui_ve_chi_trung_binh_gan_day():
    five = days(*[700_000] * 5)
    assert baseline_monthly(five, weeks=12, min_weeks=6, month_days=30) is None
    assert typical_monthly(five, S) == SpendLevel(recent_monthly(five, 30, 30), robust=False)
    # hũ mới tạo: tuần đầu chưa chi không tính vào số tuần tối thiểu
    young = [0] * 7 * 8 + days(*[700_000] * 4)
    assert typical_monthly(young, S) == SpendLevel(recent_monthly(young, 30, 30), robust=False)
    # hũ thưa: một khoản mỗi bốn tuần thì trung vị theo tuần là 0, không phải mức chi của hũ
    sparse = days(*[400_000, 0, 0, 0] * 3)
    assert baseline_monthly(sparse, weeks=12, min_weeks=6, month_days=30) is None
    assert typical_monthly(sparse, S).robust is False
    assert typical_monthly(days(*[700_000] * 12), S) == SpendLevel(3_000_000, robust=True)
    assert typical_monthly([], S) == SpendLevel(0, robust=False)


def test_mac_dinh_va_tham_so_hop_le():
    assert (DEFAULT_BASELINE_WEEKS, DEFAULT_BASELINE_MIN_WEEKS) == (12, 6)
    assert S.window_days == 84
    for bad in ({"weeks": 0}, {"min_weeks": 0}, {"min_weeks": 13}, {"month_days": 0}, {"fallback_days": 0}):
        with pytest.raises(ValueError):
            BaselineSettings(**{"weeks": 12, "min_weeks": 6, "month_days": 30, "fallback_days": 30, **bad})
