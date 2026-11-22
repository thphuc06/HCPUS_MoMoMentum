"""Khói: đặt lại persona trên Postgres thật rồi đọc các màn hình."""

from __future__ import annotations

U = "sub-minh"


def test_reset_minh_va_tong_quan(env):
    r = env.reset(U)
    assert r["jars_count"] == 7 and r["obligations_count"] == 7
    ov = env.svc.overview_response(U)
    assert ov["balance"] == {
        "total_vnd": 7_900_000,
        "jars_total_vnd": 7_730_000,
        "other_income_vnd": 350_000,
        "unclassified_vnd": -180_000,
    }
    assert {j["code"]: j["balance_vnd"] for j in ov["jars"]} == {
        "an_uong": 380_000,
        "di_lai": 640_000,
        "hoa_don": 450_000,
        "giai_tri": 760_000,
        "du_lich": 1_800_000,
        "du_phong": 2_700_000,
        "nghia_vu": 1_000_000,
    }
    assert ov["profile"]["onboarded"] and ov["next_payday"]["date"] == "2026-12-05"
    assert ov["forecast"] is None and ov["proactive_card"] is not None
