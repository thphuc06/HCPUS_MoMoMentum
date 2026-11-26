"""`run_scenario`: sáu loại kịch bản chạy bằng engine ML THẬT trên dữ liệu dựng sẵn (không dùng model giả), kiểm các bất biến của
hợp đồng: số liệu chi phí Trả sau, "common random numbers" (chênh lệch SAU - TRƯỚC chính xác, không nhiễu mẫu), kết quả khớp JSON Schema."""

from __future__ import annotations

from datetime import date

import pytest
from conftest import BASE, build_registry
from jsonschema import Draft202012Validator
from phase3_helpers import APP_DATE, USER, build
from pipeline_helpers import jar_row

from yofina_core.errors import ErrorCode, YofinaError
from yofina_forecast import scenario as scenario_mod
from yofina_forecast.scenario import ScenarioEngine

REGISTRY = build_registry()
RESULT = Draft202012Validator(
    {"$ref": f"{BASE}/tools/forecast.results.schema.json#/$defs/RunScenarioResult"}, registry=REGISTRY
)


@pytest.fixture
def saved(monkeypatch):
    rows: list[dict] = []

    def fake_save(repo, user_id, **kw):
        rows.append({"user_id": user_id, **kw})

    monkeypatch.setattr(scenario_mod.forecast_repo, "save_scenario", fake_save)
    return rows


def engine(**kw):
    pipeline, mem, repo, ref, settings = build(**kw)
    return ScenarioEngine(pipeline, repo, ref, settings), mem


def run(eng, scenario, saved):
    res = eng.run(USER, scenario, trace_id="t1")
    errs = [f"{list(e.path)}: {e.message}" for e in RESULT.iter_errors(res)]
    assert not errs, errs
    return res["data"]


def test_mua_mot_lan_chenh_lech_chinh_xac_nho_cung_day_so_ngau_nhien(saved):
    eng, _ = engine()
    d = run(eng, {"kind": "one_time_purchase", "amount_vnd": 123_000, "funding_source": "jar", "jar_code": "an_uong", "label": "tai nghe"}, saved)
    tl = d["timelines"][0]
    assert tl["jar"]["code"] == "an_uong" and tl["compare"]["kind"] == "one_time_purchase"
    assert tl["compare"]["common_random_numbers"] is True and tl["compare"]["n_paths"] == 600
    # mọi phân vị số dư dịch ĐÚNG số tiền chi: chênh lệch không nhiễu
    before, after = tl["days"], tl["compare"]["after"]["days"]
    assert all(a["p50_vnd"] == b["p50_vnd"] - 123_000 for a, b in zip(after, before, strict=True))
    assert all(a["p10_vnd"] == b["p10_vnd"] - 123_000 for a, b in zip(after, before, strict=True))
    assert tl["compare"]["delta"]["min_balance_delta_vnd"] == -123_000
    assert d["spec"]["date"] == APP_DATE.isoformat() and d["common_random_numbers"] is True
    assert d["effects"][0]["min_balance_delta_vnd"] == -123_000
    assert tl["compare"]["label"] == "mua tai nghe 123 nghìn"
    assert len(saved) == 1 and saved[0]["kind"] == "one_time_purchase" and saved[0]["n_paths"] == 600


def test_hu_thua_khong_neu_ngay_can_trong_what_if(saved):
    """#25: Giải trí là hũ thưa trong dữ liệu này (hiệu chỉnh mặc định ghi `show_runout_date` sai cho nó). Mua gần hết hũ thì hũ
    hụt nhưng kết quả không nêu ngày cạn cụ thể ở đâu cả; câu thay thế của khối nói "có thể cạn trước ngày lương"."""
    from datetime import UTC, datetime

    from yofina_core.blocks import build_forecast_timeline_from_data

    eng, _ = engine()
    d = run(eng, {"kind": "one_time_purchase", "amount_vnd": 740_000, "funding_source": "jar", "jar_code": "giai_tri"}, saved)
    tl = d["timelines"][0]
    assert tl["jar"]["code"] == "giai_tri" and tl["compare"]["after"]["status"] == "short"
    assert tl["runout_date_shown"] is False and "runout_date" not in tl
    assert "runout_date" not in tl["compare"]["after"] and "runout_shift_days" not in tl["compare"]["delta"]
    eff = {e["jar"]["code"]: e for e in d["effects"]}
    assert not {"runout_date_before", "runout_date_after"} & set(eff["giai_tri"])
    assert eff["giai_tri"]["status_after"] == "short"
    block = build_forecast_timeline_from_data(
        data=tl, trace_id="t1", source_tool="forecast___run_scenario", as_of=datetime(2026, 12, 10, tzinfo=UTC),
        app_date=APP_DATE,
    )  # fmt: skip
    assert "Hũ Giải trí có thể cạn trước ngày lương" in block.fallback_text
    # hũ dày vẫn nêu ngày như cũ
    d2 = run(eng, {"kind": "one_time_purchase", "amount_vnd": 50_000, "funding_source": "jar", "jar_code": "an_uong"}, saved)
    assert "runout_date" in d2["timelines"][0] and "runout_date_shown" not in d2["timelines"][0]
    assert "runout_date_before" in d2["effects"][0]


def test_mua_tra_sau_chi_phi_cua_mon_tach_khoi_tong_phai_tra_ngay_den_han(saved):
    eng, _ = engine()
    d = run(eng, {"kind": "bnpl_purchase", "amount_vnd": 1_200_000, "funding_source": "credit", "label": "tai nghe"}, saved)
    c = d["obligation_impact"]["cost"]
    # đã có nghĩa vụ Trả sau 1.000.000 ₫ ngày 05/12 (phí đã nằm trong đó) nên phí phát sinh thêm là 0
    assert (c["principal_vnd"], c["fee_added_vnd"], c["item_cost_vnd"]) == (1_200_000, 0, 1_200_000)
    assert (c["existing_due_vnd"], c["total_due_vnd"]) == (1_000_000, 2_200_000)
    assert c["due_date"] == "2026-12-05" and "fee" not in c
    assert c["available_before_vnd"] - c["available_after_vnd"] == 1_200_000  # hạn mức chỉ giảm theo gốc
    imp = d["obligation_impact"]
    assert imp["at_due"][0]["jar"]["code"] == "nghia_vu" and imp["at_due"][0]["due_vnd"] == 2_200_000
    assert imp["headline"].startswith(("Đủ", "Sát", "Hụt"))  # luôn có chữ, không chỉ màu
    assert d["timelines"][0]["jar"]["code"] == "nghia_vu"
    assert d["timelines"][0]["compare"]["after"]["events"][0]["amount_vnd"] == 1_200_000
    # tỷ lệ: tiền điện 375.000 + Trả sau đã có 1.000.000 + món mới 1.200.000 trên lương 9.000.000
    assert imp["ratio"]["obligations_vnd"] == 2_575_000 and imp["ratio"]["income_vnd"] == 9_000_000
    assert imp["ratio"]["exceeds"] is False
    # người dùng tự hỏi mua tùy ý bằng tín dụng: luật "không khuyên vay để tiêu" chỉ là cảnh báo (warn), không chặn what-if
    assert [c["rule_id"] for c in imp["cautions"]] == ["no_borrow_to_spend"]


def test_nghia_vu_vuot_nguong_thu_nhap_la_do_kem_canh_bao_khong_khuyen_khich(saved):
    eng, _ = engine(user={"id": USER, "monthly_salary_vnd": 5_000_000, "payday_day": 5, "risk_tolerance": "medium", "clock_offset_days": -19})
    d = run(eng, {"kind": "bnpl_purchase", "amount_vnd": 1_200_000, "funding_source": "credit"}, saved)
    imp = d["obligation_impact"]
    # engine đọc thu nhập từ hồ sơ trong ngữ cảnh dự báo (context_rows); ở đây dùng lương của context nên kiểm theo số của nó
    assert imp["ratio"]["income_vnd"] == 9_000_000


def test_mua_tra_sau_khi_chua_co_nghia_vu_tinh_them_phi_mot_lan(saved):
    only_electric = [{**__import__("phase3_helpers").OBLIGATION_ROWS[0]}]
    ctx_obl = [
        {
            "id": o["id"], "kind": o["kind"], "name": o["name"], "amount_vnd": int(o["amount_vnd"]),
            "amount_min_vnd": 300_000, "amount_max_vnd": 450_000, "due_date": "2026-11-26",
            "cycle": o["cycle"], "due_day": o["due_day"], "pay_jar_code": o["pay_jar_code"],
        }
        for o in only_electric
    ]
    eng, _ = engine(obligations=only_electric, context={"obligations": ctx_obl})
    d = run(eng, {"kind": "bnpl_purchase", "amount_vnd": 300_000, "funding_source": "credit"}, saved)
    c = d["obligation_impact"]["cost"]
    assert (c["fee_added_vnd"], c["item_cost_vnd"], c["total_due_vnd"]) == (33_000, 333_000, 333_000)
    assert c["fee"]["amount_vnd"] == 33_000 and c["fee"]["source_name"]


def test_tra_sau_vuot_han_muc_bi_tu_choi(saved):
    eng, _ = engine()
    with pytest.raises(YofinaError) as e:
        eng.run(USER, {"kind": "bnpl_purchase", "amount_vnd": 4_500_000, "funding_source": "credit"}, trace_id="t")
    assert e.value.code == ErrorCode.CREDIT_LIMIT_EXCEEDED


def test_doi_thu_nhap_tang_luong_cai_thien_cac_hu_co_chia_luong(saved):
    eng, _ = engine()
    d = run(eng, {"kind": "income_change", "new_monthly_salary_vnd": 12_000_000}, saved)
    assert d["spec"]["date"] == "2026-12-05"  # ngày lương kế tiếp
    assert all(e["min_balance_delta_vnd"] >= 0 for e in d["effects"])
    # lương mới có hiệu lực từ 05/12: số dư cuối kỳ dự báo của các hũ được chia lương cao hơn đúng phần chênh
    for tl in d["timelines"]:
        gain = tl["compare"]["after"]["days"][-1]["p50_vnd"] - tl["days"][-1]["p50_vnd"]
        assert gain > 0


def test_doi_thu_nhap_bang_luong_hien_tai_la_vo_ly(saved):
    eng, _ = engine()
    with pytest.raises(YofinaError) as e:
        eng.run(USER, {"kind": "income_change", "new_monthly_salary_vnd": 9_000_000}, trace_id="t")
    assert e.value.code == ErrorCode.SCENARIO_INVALID


def test_khoan_chi_dinh_ky_them_moc_theo_chu_ky(saved):
    eng, _ = engine()
    d = run(
        eng,
        {"kind": "recurring_expense", "amount_vnd": 50_000, "cycle": "weekly", "date": "2026-11-25", "jar_code": "giai_tri", "label": "gói tập"},
        saved,
    )
    ev = d["timelines"][0]["compare"]["after"]["events"]
    assert [e["date"] for e in ev][:3] == ["2026-11-25", "2026-12-02", "2026-12-09"]
    assert d["effects"][0]["min_balance_delta_vnd"] < 0


def test_chuyen_giua_hu_tru_hu_nguon_cong_hu_dich(saved):
    eng, _ = engine()
    d = run(eng, {"kind": "jar_transfer", "amount_vnd": 100_000, "from_jar": "giai_tri", "to_jar": "an_uong"}, saved)
    by = {e["jar"]["code"]: e for e in d["effects"]}
    assert by["giai_tri"]["min_balance_delta_vnd"] == -100_000
    assert by["an_uong"]["min_balance_delta_vnd"] == 100_000


def test_chuyen_hu_he_thong_chi_tinh_hu_con_lai_va_hai_hu_he_thong_la_khong_ap_dung(saved):
    eng, _ = engine()
    d = run(eng, {"kind": "jar_transfer", "amount_vnd": 100_000, "from_jar": "tien_vao_khac", "to_jar": "an_uong"}, saved)
    assert [e["jar"]["code"] for e in d["effects"]] == ["an_uong"]
    with pytest.raises(YofinaError) as e:
        eng.run(USER, {"kind": "one_time_purchase", "amount_vnd": 1, "funding_source": "jar", "jar_code": "tien_vao_khac"}, trace_id="t")
    assert e.value.code == ErrorCode.FORECAST_NOT_APPLICABLE


def test_lui_muc_tieu_tinh_so_tien_can_de_danh_moi_thang(saved):
    eng, _ = engine(goal=True)
    d = run(eng, {"kind": "goal_delay", "jar_code": "giai_tri", "delay_months": 2}, saved)
    label = d["timelines"][0]["compare"]["label"]
    assert label.startswith("lùi mục tiêu Giải trí 2 tháng: cần") and "thay vì" in label
    assert d["effects"][0]["min_balance_delta_vnd"] == 0  # không đụng số dư, chỉ đổi nhịp để dành


def test_lui_muc_tieu_hu_chua_co_muc_tieu_la_vo_ly(saved):
    eng, _ = engine()
    with pytest.raises(YofinaError) as e:
        eng.run(USER, {"kind": "goal_delay", "jar_code": "an_uong", "delay_months": 1}, trace_id="t")
    assert e.value.code == ErrorCode.SCENARIO_INVALID


@pytest.mark.parametrize(
    ("spec", "code"),
    [
        ({"kind": "nope", "amount_vnd": 1}, ErrorCode.PARAMS_INVALID),
        ({"amount_vnd": 1}, ErrorCode.PARAMS_INVALID),
        ({"kind": "one_time_purchase", "funding_source": "jar", "jar_code": "an_uong"}, ErrorCode.PARAMS_INVALID),
        ({"kind": "one_time_purchase", "amount_vnd": 5, "funding_source": "jar", "jar_code": "khong_co"}, ErrorCode.JAR_NOT_FOUND),
        ({"kind": "one_time_purchase", "amount_vnd": 5, "funding_source": "jar", "jar_code": "an_uong", "date": "2026-11-01"}, ErrorCode.SCENARIO_INVALID),
        ({"kind": "one_time_purchase", "amount_vnd": 5, "funding_source": "jar", "jar_code": "an_uong", "date": "2027-06-01"}, ErrorCode.SCENARIO_INVALID),
        ({"kind": "jar_transfer", "amount_vnd": 5, "from_jar": "an_uong", "to_jar": "an_uong"}, ErrorCode.SCENARIO_INVALID),
    ],
)
def test_dau_vao_sai_tra_ma_loi_dung(saved, spec, code):
    eng, _ = engine()
    with pytest.raises(YofinaError) as e:
        eng.run(USER, spec, trace_id="t")
    assert e.value.code == code
    assert not saved  # lỗi thì không ghi kịch bản


def test_khong_co_nen_du_bao_thi_tinh_day_du_mot_lan_roi_chay(saved):
    eng, mem = engine()
    mem.runs.clear()  # mất nền
    d = run(eng, {"kind": "one_time_purchase", "amount_vnd": 10_000, "funding_source": "jar", "jar_code": "an_uong"}, saved)
    assert d["effects"] and mem.saves == 1 + 1  # lần dựng nền của test + một lần tính lại


def test_hu_khac_khong_bi_tinh_lai_chi_hu_bi_tac_dong(saved):
    eng, _ = engine()
    d = run(eng, {"kind": "one_time_purchase", "amount_vnd": 10_000, "funding_source": "jar", "jar_code": "an_uong"}, saved)
    assert [e["jar"]["code"] for e in d["effects"]] == ["an_uong"]
    assert date.fromisoformat(d["timelines"][0]["origin_date"]) == APP_DATE


def test_tra_sau_den_han_dung_ngay_luong_lam_hu_can_thi_trang_thai_sau_la_hut(saved):
    """Lỗi đi cảnh 2: khoản Trả sau đến hạn đúng ngày lương (05/12) làm hũ Nghĩa vụ âm và cạn ngày đó, nhưng xác suất hụt của engine
    chỉ xét các ngày TRƯỚC ngày lương nên trạng thái SAU là "đủ, 0%". Dữ liệu dựng sẵn chia 20% lương (1.800.000 ₫) cho hũ Nghĩa vụ
    (minh chỉ 5%), nên dùng khoản 3.000.000 ₫ (trong hạn mức còn 4.033.000 ₫) để tổng đến hạn 05/12 vượt số dư cộng phần lương."""
    eng, _ = engine()
    d = run(eng, {"kind": "bnpl_purchase", "amount_vnd": 3_000_000, "funding_source": "credit", "label": "tai nghe"}, saved)
    tl = d["timelines"][0]
    after = tl["compare"]["after"]
    assert tl["jar"]["code"] == "nghia_vu"
    assert after["min_balance_p50_vnd"] < 0 and after["runout_date"] <= tl["payday"]["date"]
    assert after["status"] == "short" and "p_shortfall" not in after and "p_shortfall_se" not in after
    assert "p_shortfall_delta" not in tl["compare"]["delta"]
    eff = d["effects"][0]
    assert eff["status_after"] == "short" and "p_shortfall_after" not in eff
    assert tl["status"] == eff["status_before"]  # TRƯỚC giữ đúng trạng thái của dự báo nền


def test_tra_sau_den_han_dung_ngay_luong_tra_bang_so_du_truoc_khi_luong_ve(saved):
    """Chốt 26/11 (BR-22, phương án B): khoản đến hạn ĐÚNG ngày lương là đến hạn trước lương, và tiền để trả nó không gồm lương về
    cùng ngày. Dữ liệu dựng sẵn: hũ Nghĩa vụ 1.000.000 ₫, tiền điện 375.000 ₫ ngày 26/11, Trả sau 1.000.000 ₫ ngày 05/12, lương chia
    vào hũ ngày 05/12. Mua thêm 1.200.000 ₫: cuối ngày 05/12 (đã cộng lương) hũ vẫn dương, nên quy tắc cũ (số dư cuối ngày) nói "đủ";
    trước khi lương về thì thiếu. Danh sách, khoản thiếu đầu tiên, hũ hụt khi đến hạn và trạng thái SAU cùng một mốc."""
    from datetime import UTC, datetime

    from yofina_core.blocks import build_forecast_timeline_from_data

    eng, _ = engine()
    d = run(eng, {"kind": "bnpl_purchase", "amount_vnd": 1_200_000, "funding_source": "credit", "label": "tai nghe"}, saved)
    tl = d["timelines"][0]
    payday = tl["payday"]["date"]
    after = tl["compare"]["after"]
    assert tl["jar"]["code"] == "nghia_vu" and d["obligation_impact"]["cost"]["due_date"] == payday
    salary = next(e["amount_vnd"] for e in tl["events"] if e["kind"] == "salary" and e["date"] == payday)
    end_of_day = next(x["p50_vnd"] for x in after["days"] if x["date"] == payday)
    assert end_of_day >= 0 and "runout_date" not in after  # tiền đề: lương cùng ngày che được khoản theo số dư cuối ngày
    before_salary = end_of_day + 2_200_000 - salary  # tiền có để trả khoản ngày lương
    window = after["obligations_before_payday"]
    assert [(i["date"], i["amount_vnd"]) for i in window["items"]][-1] == (payday, 2_200_000)
    assert window["first_shortfall"] == {
        "date": payday, "label": "Trả sau (mô phỏng)", "shortfall_vnd": 2_200_000 - before_salary,
    }  # fmt: skip
    at = d["obligation_impact"]["at_due"][0]
    assert (at["status"], at["balance_before_due_vnd"], at["shortfall_vnd"]) == (
        "short", before_salary, 2_200_000 - before_salary,
    )  # fmt: skip
    assert d["obligation_impact"]["status"] == "short"
    # trạng thái SAU là hụt, không kèm xác suất của engine (chỉ xét các ngày trước ngày lương, nói ngược với chữ "Hụt")
    assert after["status"] == "short" and "p_shortfall" not in after and "p_shortfall_delta" not in tl["compare"]["delta"]
    eff = next(e for e in d["effects"] if e["jar"]["code"] == "nghia_vu")
    assert eff["status_after"] == "short" and "p_shortfall_after" not in eff
    block = build_forecast_timeline_from_data(
        data=tl, trace_id="t1", source_tool="forecast___run_scenario", as_of=datetime(2026, 12, 10, tzinfo=UTC),
        app_date=APP_DATE,
    )  # fmt: skip
    assert "đủ tới kỳ lương" not in block.fallback_text and "Hũ Nghĩa vụ dự kiến hụt" in block.fallback_text


def test_recurring_obligation_defaults_to_shared_jar(saved):
    eng, _ = engine()
    data = run(eng, {
        "kind": "recurring_expense", "amount_vnd": 250_000, "cycle": "monthly",
        "date": "2026-12-01", "label": "Tiền nhà",
    }, saved)
    assert data["spec"]["jar_code"] == "nghia_vu"
    window = data["timelines"][0]["compare"]["after"]["obligations_before_payday"]
    assert any(due["label"] == "Tiền nhà" for due in window["items"])


def test_bnpl_legacy_wallet_requires_explicit_source_when_none_saved(saved):
    eng, _ = engine(
        context={
            "jars": [jar_row("an_uong", "spending", 1_000_000, 100, 1, [0] * 47)],
            "obligations": [],
        },
        obligations=[],
    )
    spec = {"kind": "bnpl_purchase", "amount_vnd": 500_000, "funding_source": "credit"}
    with pytest.raises(YofinaError) as error:
        run(eng, {**spec, "jar_code": "an_uong"}, saved)
    assert error.value.code == ErrorCode.SCENARIO_INVALID
    data = run(eng, {**spec, "pay_jar": "an_uong"}, saved)
    assert data["obligation_impact"]["at_due"][0]["jar"]["code"] == "an_uong"
    assert data["obligation_impact"]["cost"]["total_due_vnd"] == 533_000


def test_recurring_without_shared_jar_names_jar_code_not_pay_jar(saved):
    """Khoản định kỳ trên ví không có hũ Nghĩa vụ: lỗi gắn đúng tham số của kịch bản (`jar_code`, `RecurringExpense` không có
    `pay_jar`). Gắn `pay_jar` thì agent hỏi hũ trả rồi gọi lại với `pay_jar`, kịch bản bị từ chối lần nữa."""
    eng, _ = engine(
        context={
            "jars": [jar_row("an_uong", "spending", 1_000_000, 100, 1, [0] * 47)],
            "obligations": [],
        },
        obligations=[],
    )
    spec = {"kind": "recurring_expense", "amount_vnd": 250_000, "cycle": "monthly", "date": "2026-12-01", "label": "Tiền nhà"}
    with pytest.raises(YofinaError) as error:
        run(eng, spec, saved)
    assert (error.value.code, error.value.field) == (ErrorCode.SCENARIO_INVALID, "jar_code")
    with pytest.raises(YofinaError) as error:
        run(eng, {**spec, "pay_jar": "an_uong"}, saved)  # thứ agent sẽ gửi nếu lỗi nói thiếu pay_jar: sai hợp đồng kịch bản
    assert error.value.code == ErrorCode.PARAMS_INVALID and error.value.field is None
    data = run(eng, {**spec, "jar_code": "an_uong"}, saved)
    assert data["spec"]["jar_code"] == "an_uong"
