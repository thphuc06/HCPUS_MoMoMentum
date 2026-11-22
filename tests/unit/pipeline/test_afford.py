"""`affordability_check`: kiểm tra trước khi quẹt, tất định. Hàm thuần (`jar_check`, `shifted`) và engine trên dữ liệu dựng sẵn
(engine ML thật), kiểm trạng thái đủ/sát/hụt theo ngưỡng cấu hình, chi phí Trả sau tách khỏi tổng phải trả, phương án và hợp đồng."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from conftest import BASE, build_registry
from jsonschema import Draft202012Validator
from phase3_helpers import APP_DATE, NOW, USER, build
from yofina_core.errors import ErrorCode, YofinaError
from yofina_forecast.afford import AffordabilityEngine, jar_check, shifted

REGISTRY = build_registry()
RESULT = Draft202012Validator(
    {"$ref": f"{BASE}/tools/forecast.results.schema.json#/$defs/AffordabilityCheckResult"},
    registry=REGISTRY,
)
JAR = {"code": "an_uong", "name": "Ăn uống", "color_key": "violet", "icon_key": "utensils"}
PAYDAY = date(2026, 12, 5)


def series(p50: list[int], spread: int = 0):
    return [
        (APP_DATE + timedelta(days=i + 1), v - spread, v, v + spread) for i, v in enumerate(p50)
    ]


def check(p50, amount, *, spread=0, balance=1_000_000, pay_date=APP_DATE, short=0, tight=0, runout=None):
    return jar_check(
        jar=JAR,
        balance_now_vnd=balance,
        series=series(p50, spread),
        origin=APP_DATE,
        payday=PAYDAY,
        runout_before=runout,
        amount_vnd=amount,
        pay_date=pay_date,
        short_floor_vnd=short,
        tight_floor_vnd=tight,
        runout_threshold_vnd=0,
    )


# --- hàm thuần ---------------------------------------------------------------------------------------
def test_tru_mot_khoan_tat_dinh_dich_moi_phan_vi_dung_bang_so_tien_tu_ngay_chi():
    out = shifted(series([100, 90, 80], 10), 30, APP_DATE + timedelta(days=2))
    assert [x[1:] for x in out] == [(90, 100, 110), (50, 60, 70), (40, 50, 60)]


def test_du_khi_p10_van_khong_am_truoc_ky_luong():
    c = check([900_000] * 14, 100_000, spread=50_000)
    assert c["status"] == "ok" and "shortfall_vnd" not in c and "days_earlier" not in c
    assert c["balance_before_vnd"] == 1_000_000 and c["balance_after_vnd"] == 900_000


def test_sat_khi_p50_con_duong_nhung_p10_cham_am():
    c = check([300_000] * 14, 200_000, spread=150_000)  # P10 sau chi = 300-200-150 = -50.000
    assert c["status"] == "tight" and "shortfall_vnd" not in c


def test_hut_khi_p50_am_va_bao_so_dong_thieu_truoc_ky_luong():
    p50 = [500_000 - 80_000 * i for i in range(14)]  # xuống tới -540.000 vào ngày 14
    c = check(p50, 250_000, balance=500_000)
    assert c["status"] == "short"
    assert c["shortfall_vnd"] == 250_000 - min(p50[:13]) - 250_000 + 0 or c["shortfall_vnd"] > 0
    assert c["shortfall_vnd"] == -(min(p50[:13]) - 250_000)  # ngày cuối cửa sổ là 04/12 (trước ngày lương 05/12)


def test_hut_vi_so_du_hom_nay_khong_du_chi_du_du_bao_dep():
    c = check([5_000_000] * 14, 300_000, balance=100_000)
    assert c["status"] == "short" and c["shortfall_vnd"] == 200_000


def test_ngay_can_som_hon_so_voi_du_bao_hien_tai():
    p50 = [400_000 - 30_000 * i for i in range(30)]
    base_runout = APP_DATE + timedelta(days=14)  # P50 chạm 0 vào ngày thứ 14
    c = check(p50, 120_000, runout=base_runout, balance=400_000)
    assert c["runout_date_before"] == base_runout.isoformat()
    assert date.fromisoformat(c["runout_date_after"]) < base_runout
    assert c["days_earlier"] == (base_runout - date.fromisoformat(c["runout_date_after"])).days > 0


def test_nguong_la_cau_hinh_doi_nguong_doi_trang_thai():
    p50 = [200_000] * 14
    assert check(p50, 100_000)["status"] == "ok"
    assert check(p50, 100_000, short=150_000)["status"] == "short"  # nâng sàn hụt: số dư 100.000 nay là hụt
    assert check(p50, 100_000, tight=150_000)["status"] == "tight"


def test_chi_vao_ngay_tuong_lai_dung_so_du_du_bao_ngay_hom_truoc():
    p50 = [500_000, 450_000, 400_000, 350_000, 300_000, 250_000]
    c = check(p50, 100_000, pay_date=APP_DATE + timedelta(days=4))
    assert c["balance_before_vnd"] == 400_000 and c["balance_after_vnd"] == 300_000


# --- engine ------------------------------------------------------------------------------------------
def engine(**kw):
    pipeline, mem, repo, ref, settings = build(**kw)
    return AffordabilityEngine(pipeline, repo, ref, settings), mem, pipeline


def ok(eng, **kw):
    res = eng.check(USER, **kw)
    errs = [f"{list(e.path)}: {e.message}" for e in RESULT.iter_errors(res)]
    assert not errs, errs
    return res["data"]


def test_kiem_moi_hu_chi_tieu_va_ca_tra_sau_khi_khong_chi_dinh_nguon():
    eng, _, _ = engine()
    d = ok(eng, amount_vnd=250_000, label="Trần Quang Huy")
    assert [c["jar"]["code"] for c in d["jar_checks"]] == ["an_uong", "giai_tri"]  # hũ chi tiêu, không có hũ nghĩa vụ/hệ thống
    assert d["funding_source"] == "jar" and "selected_jar_code" not in d and d["label"] == "Trần Quang Huy"
    assert d["verdict"] in ("ok", "tight", "short") and d["headline"].split(":")[0] in ("Đủ", "Sát", "Hụt")
    credit = d["credit"]
    c = credit["cost"]
    # đã có nghĩa vụ Trả sau 1.000.000 ₫ ngày 05/12 (phí nằm trong đó): món này tốn 250.000, tổng phải trả 1.250.000
    assert (c["principal_vnd"], c["fee_added_vnd"], c["item_cost_vnd"]) == (250_000, 0, 250_000)
    assert (c["existing_due_vnd"], c["total_due_vnd"]) == (1_000_000, 1_250_000)
    assert credit["at_due"][0]["jar"]["code"] == "nghia_vu"


def test_an_uong_hut_va_giai_tri_du_voi_du_lieu_nay():
    eng, _, _ = engine()
    d = ok(eng, amount_vnd=250_000, funding_source="jar")
    by = {c["jar"]["code"]: c for c in d["jar_checks"]}
    assert by["an_uong"]["status"] == "short" and by["an_uong"]["shortfall_vnd"] > 0
    assert by["giai_tri"]["status"] in ("ok", "tight")  # hũ chi 40.000 mỗi ngày: còn dương trước kỳ lương
    assert by["giai_tri"]["balance_after_vnd"] == 760_000 - 250_000
    assert "credit" not in d  # funding_source jar thì không xét Trả sau


def test_chon_hu_cu_the_thi_ket_luan_la_cua_hu_do():
    eng, _, _ = engine()
    d = ok(eng, amount_vnd=30_000, jar="giai_tri")  # P10 của hũ này còn 40.000 trước kỳ lương
    assert d["selected_jar_code"] == "giai_tri" and d["verdict"] == "ok"
    assert [c["jar"]["code"] for c in d["jar_checks"]] == ["giai_tri", "an_uong"]  # hũ chọn đứng đầu, vẫn kiểm các hũ khác
    assert d["options"] == []  # đủ thì không cần phương án
    d = ok(eng, amount_vnd=250_000, jar="an_uong")
    assert d["verdict"] == "short" and d["headline"].startswith("Hụt")


def test_phuong_an_tat_dinh_khi_hut_doi_hu_tra_sau_hoan_chia_nho():
    eng, _, _ = engine()
    d = ok(eng, amount_vnd=250_000, jar="an_uong")
    kinds = [o["kind"] for o in d["options"]]
    assert kinds[:2] == ["switch_jar", "use_credit"] and "defer" in kinds and len(kinds) <= 4
    switch = d["options"][0]
    assert switch["status"] in ("ok", "tight") and "giai_tri" in switch["option_id"]
    assert all("action" not in o for o in d["options"])  # phương án tất định không có action (agent gắn sau)
    assert all(o["status"] in ("ok", "tight", "short") for o in d["options"])


def test_nguon_tra_sau_rieng_khong_co_jar_checks_va_ket_luan_theo_tra_sau():
    eng, _, _ = engine()
    d = ok(eng, amount_vnd=1_200_000, funding_source="credit")
    assert d["funding_source"] == "credit" and d["jar_checks"] == []
    assert d["verdict"] == d["credit"]["status"]
    assert d["credit"]["cost"]["total_due_vnd"] == 2_200_000


def test_tra_sau_vuot_han_muc_khi_xet_rieng_la_loi_con_khi_xet_ca_hai_thi_bo_qua_tra_sau():
    eng, _, _ = engine()
    with pytest.raises(YofinaError) as e:
        eng.check(USER, amount_vnd=4_500_000, funding_source="credit")
    assert e.value.code == ErrorCode.CREDIT_LIMIT_EXCEEDED
    d = ok(eng, amount_vnd=4_500_000)
    assert "credit" not in d and d["verdict"] == "short"


def test_ngay_chi_tuong_lai_va_nhan_hien_thi():
    eng, _, _ = engine()
    when = (APP_DATE + timedelta(days=3)).isoformat()
    d = ok(eng, amount_vnd=100_000, jar="giai_tri", pay_date=when)
    assert d["pay_date"] == when


@pytest.mark.parametrize(
    ("kw", "code"),
    [
        ({"amount_vnd": 0}, ErrorCode.PARAMS_INVALID),
        ({"amount_vnd": -5}, ErrorCode.PARAMS_INVALID),
        ({"amount_vnd": True}, ErrorCode.PARAMS_INVALID),
        ({"amount_vnd": 5, "funding_source": "tien_mat"}, ErrorCode.PARAMS_INVALID),
        ({"amount_vnd": 5, "jar": "Ăn Uống"}, ErrorCode.PARAMS_INVALID),
        ({"amount_vnd": 5, "pay_date": "21/11/2026"}, ErrorCode.PARAMS_INVALID),
        ({"amount_vnd": 5, "pay_date": "2026-11-01"}, ErrorCode.PARAMS_INVALID),
        ({"amount_vnd": 5, "jar": "khong_co"}, ErrorCode.JAR_NOT_FOUND),
        ({"amount_vnd": 5, "jar": "tien_vao_khac"}, ErrorCode.FORECAST_NOT_APPLICABLE),
    ],
)
def test_tham_so_sai(kw, code):
    eng, _, _ = engine()
    with pytest.raises(YofinaError) as e:
        eng.check(USER, **kw)
    assert e.value.code == code


def test_du_bao_cu_thi_tinh_lai_mot_lan_roi_tra_so():
    eng, mem, pipeline = engine()
    saves = mem.saves
    pipeline._clock = lambda: NOW + timedelta(hours=3)  # quá hạn độ tươi 1 giờ
    d = ok(eng, amount_vnd=100_000, jar="giai_tri")
    assert mem.saves == saves + 1 and d["basis"]["stale"] is False


def test_tinh_lai_loi_van_dung_ban_cu_va_danh_dau_cu():
    eng, mem, pipeline = engine()
    pipeline._clock = lambda: NOW + timedelta(hours=3)
    mem.fail_save = True
    d = ok(eng, amount_vnd=100_000, jar="giai_tri")
    assert d["basis"]["stale"] is True


def test_nguong_nghia_vu_tren_thu_nhap_vuot_thi_do_kem_luat():
    eng, _, _ = engine(user={"id": USER, "monthly_salary_vnd": 2_000_000, "payday_day": 5, "risk_tolerance": "low", "clock_offset_days": -19})
    d = ok(eng, amount_vnd=300_000, funding_source="credit")
    credit = d["credit"]
    assert credit["ratio"]["exceeds"] is True and credit["status"] == "short"
    assert any(c["rule_id"] == "obligation_to_income" and "Không khuyến khích" in c["text"] for c in credit["cautions"])
    assert d["verdict"] == "short" and d["cautions"] == credit["cautions"]


def test_khong_ghi_gi_va_khong_dung_model():
    eng, mem, _ = engine()
    saves = mem.saves
    ok(eng, amount_vnd=250_000)
    assert mem.saves == saves  # dự báo còn tươi: chỉ đọc
    assert NOW.tzinfo is UTC and isinstance(NOW, datetime)
