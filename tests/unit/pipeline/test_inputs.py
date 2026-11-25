"""Dựng `ForecastInputs` từ dữ liệu một người dùng (hàm thuần): lịch sử, lương chia theo hũ, mở rộng nghĩa vụ, độ phủ, cấu hình."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import phase3_helpers
import pytest
from ledger_fakes import FakeRepo, make_service
from pipeline_helpers import APP_DATE, context_rows, jar_row, make_settings

from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.wallet import RECORD_TRANSACTION, split_amount
from yofina_forecast import scenario as scenario_mod
from yofina_forecast.afford import AffordabilityEngine
from yofina_forecast.inputs import Context, build_inputs, expand_obligations, user_seed
from yofina_forecast.scenario import ScenarioEngine
from yofina_ledger.refdata import ReferenceData
from yofina_ledger.repo_wallet import WriteResult
from yofina_ml.api import forecast_user
from yofina_ml.calibration import calibrated_config
from yofina_ml.contract import check_inputs


def build(rows=None, **kw):
    ctx = Context.from_rows(rows if rows is not None else context_rows())
    assert ctx is not None
    return build_inputs(ctx, make_settings(**kw), "user-a", n_paths=500)


def test_inputs_dung_hop_dong_va_ngay_goc():
    built = build()
    inp = built.inputs
    assert check_inputs(inp) == []
    assert inp.app_date == APP_DATE and inp.horizon_days == 30
    assert inp.next_payday == date(2026, 12, 5) and inp.payday_day == 5
    assert inp.payday_dates == (date(2026, 12, 5),)
    assert built.jar_codes == ("an_uong", "giai_tri", "nghia_vu")
    for j in inp.jars:
        assert j.history_start + timedelta(days=j.history_days) == APP_DATE and j.history_days == 47
        assert all(isinstance(v, int) and v >= 0 for v in j.daily_spend_vnd)
    assert inp.coverage is not None and inp.coverage.income_vnd == 18_000_000


def test_luong_chia_theo_hu_bang_split_amount_vao_dung_ngay_luong():
    inp = build().inputs
    want = split_amount(9_000_000, [("an_uong", 60), ("giai_tri", 20), ("nghia_vu", 20)])
    for j in inp.jars:
        assert [(f.date, f.amount_vnd, f.kind) for f in j.inflows] == [
            (date(2026, 12, 5), want[j.code], "salary")
        ]


def test_nghia_vu_mo_rong_chu_ky_va_gan_hu_mac_dinh():
    inp = build().inputs
    nv = next(j for j in inp.jars if j.code == "nghia_vu")
    got = [(f.date, f.amount_vnd, f.label) for f in nv.outflows]
    # tiền điện hằng tháng ngày 26 (26/11; 26/12 vượt horizon 30 ngày), trả sau một lần ngày 5/12 gán cho hũ nghĩa vụ đầu tiên
    assert got == [
        (date(2026, 11, 26), 375_000, "Tiền điện"),
        (date(2026, 12, 5), 1_000_000, "Trả sau (mô phỏng)"),
    ]
    elec = nv.outflows[0]
    assert (elec.amount_min_vnd, elec.amount_max_vnd) == (300_000, 450_000)
    assert elec.ref_id == "00000000-0000-0000-0000-000000000001"
    assert all(not j.outflows for j in inp.jars if j.code != "nghia_vu")


def test_nghia_vu_qua_han_tinh_vao_ngay_dau_va_bo_nghia_vu_khong_gan_duoc():
    flows, unassigned = expand_obligations(
        [
            {"id": "a", "name": "Quá hạn", "amount_vnd": 100, "due_date": "2026-11-10",
             "cycle": "once", "due_day": None, "pay_jar_code": "x"},
            {"id": "b", "name": "Mồ côi", "amount_vnd": 50, "due_date": "2026-11-25",
             "cycle": "once", "due_day": None, "pay_jar_code": None},
        ],
        ["x"],
        None,  # không có hũ nghĩa vụ mặc định
        APP_DATE,
        30,
    )  # fmt: skip
    assert [f.date for f in flows["x"]] == [APP_DATE + timedelta(days=1)]
    assert unassigned == ["Mồ côi"]


def test_ghi_chu_nghia_vu_khong_gan_duoc_vao_notes():
    rows = context_rows(jars=[jar_row("an_uong", "spending", 1, 100, 1, [1] * 47)])
    built = build(rows)
    assert built.notes["unassigned_obligations"] == ["Tiền điện"]  # hũ trả `nghia_vu` không còn


def test_tra_sau_chua_co_hu_tra_khong_co_hu_nghia_vu_tinh_vao_hu_chi_tieu_dau_tien():
    # dòng Trả sau ghi trước #15 (hũ trả NULL) trên tài khoản như `lan`: không bỏ khỏi dự báo, tính như what-if khi không chọn hũ
    jars = [
        jar_row("du_phong", "saving", 1, 20, 1, [0] * 47),
        jar_row("an_uong", "spending", 1, 50, 2, [1] * 47),
        jar_row("giai_tri", "spending", 1, 30, 3, [1] * 47),
    ]
    built = build(context_rows(jars=jars))
    flows = {
        j.code: [(f.date, f.amount_vnd, f.label) for f in j.outflows] for j in built.inputs.jars
    }
    assert flows == {
        "du_phong": [],
        "an_uong": [(date(2026, 12, 5), 1_000_000, "Trả sau (mô phỏng)")],
        "giai_tri": [],
    }
    assert built.notes["unassigned_obligations"] == ["Tiền điện"]


def test_hat_ngau_nhien_tat_dinh_theo_nguoi_dung():
    assert user_seed("a") == user_seed("a") != user_seed("b")
    assert 0 <= user_seed("sub-xyz") < 2**31
    assert build().inputs == build().inputs  # cùng dữ liệu cho cùng đầu vào, kể cả hạt


def test_cau_hinh_lay_tu_settings_va_cong_tac_xac_suat():
    on = build().inputs.config
    assert on.n_paths == 500 and on.seed == user_seed("user-a")
    assert on.cold_start_min_days == 21 and on.short_threshold == 0.5 and on.tight_threshold == 0.2
    assert on.probability_enabled is calibrated_config().probability_enabled
    off = build(probability_enabled=False).inputs.config
    assert off.probability_enabled is False  # công tắc cấu hình tắt được dù hiệu chỉnh cho phép
    custom = build(short_threshold=0.6, tight_threshold=0.3, cold_start_min_days=10).inputs.config
    assert (custom.short_threshold, custom.tight_threshold, custom.cold_start_min_days) == (
        0.6,
        0.3,
        10,
    )


def test_lich_su_ngan_va_dem_so_0():
    rows = context_rows(days=5)
    for r in rows:
        if r["section"] == "jar":
            r["payload"]["spend"] = [10, 20]  # thiếu so với 5 ngày: đệm 0 ở đầu
    inp = build(rows).inputs
    assert inp.jars[0].daily_spend_vnd == (0, 0, 0, 10, 20)
    zero = build(context_rows(days=0)).inputs
    assert all(j.history_days == 0 for j in zero.jars)


def test_ho_so_chua_khai_luong_thi_profile_incomplete():
    for kw in ({"salary": None}, {"payday": None}):
        with pytest.raises(YofinaError) as e:
            build(context_rows(**kw))
        assert e.value.code == ErrorCode.PROFILE_INCOMPLETE


def test_ty_le_chia_khong_du_100_khong_mo_phong_luong():
    jars = [
        jar_row("a", "spending", 10, 40, 1, [1] * 47),
        jar_row("b", "spending", 10, 40, 2, [1] * 47),
    ]
    built = build(context_rows(jars=jars, obligations=[]))
    assert built.notes["salary_split_invalid"] is True
    assert all(not j.inflows for j in built.inputs.jars)


def test_chi_hu_nguoi_dung_duoc_du_bao_hu_he_thong_bi_loai():
    jars = [
        jar_row("an_uong", "spending", 100, 100, 1, [1] * 47),
        jar_row("tien_vao_khac", "system", 5, 0, 1000, [0] * 47),
        jar_row("chua_phan_loai", "system", -180, 0, 1001, [0] * 47),
    ]
    built = build(context_rows(jars=jars, obligations=[]))
    assert built.jar_codes == ("an_uong",)


def test_co_truncated_khi_ham_db_cham_tran():
    assert build(context_rows(spend_rows=5000)).notes["spend_truncated"] is True
    assert "spend_truncated" not in build().notes


def test_khong_co_hu_nao_thi_forecast_unavailable():
    with pytest.raises(YofinaError) as e:
        build(context_rows(jars=[jar_row("tien_vao_khac", "system", 0, 0, 1, [])]))
    assert e.value.code == ErrorCode.FORECAST_UNAVAILABLE


def test_context_rong_la_none():
    assert Context.from_rows([]) is None


# --- Trả sau trên tài khoản không có hũ Nghĩa vụ (#15) ---------------------------------------------------------------
LAN = "sub-lan"
#: như `lan`, `khoa`: hũ chi tiêu và tiết kiệm, không có hũ loại `obligation`
LAN_JARS = [
    # code, name, color, icon, kind, balance, split, order, goal_vnd, goal_date (dạng của phase3_helpers.JARS)
    ("an_uong", "Ăn uống", "violet", "utensils", "spending", 380_000, 50, 1, None, None),
    ("giai_tri", "Giải trí", "orchid", "gamepad", "spending", 760_000, 30, 2, None, None),
    ("du_phong", "Dự phòng", "blue", "shield", "saving", 1_000_000, 20, 3, None, None),
]
UNCLASSIFIED = {
    "code": "chua_phan_loai", "name": "Chưa phân loại", "color_key": "gray", "icon_key": "inbox",
    "balance_vnd": Decimal(0), "split_percent": Decimal(0), "sort_order": 99, "kind": "system",
    "system_role": "unclassified",
}  # fmt: skip


class LanWallet(FakeRepo):
    """Sổ cái giả của một tài khoản không có hũ Nghĩa vụ, đủ cho luồng mua bằng Trả sau; giữ nghĩa vụ vừa sinh như bảng thật."""

    def __init__(self, clock) -> None:
        super().__init__(clock)
        self.obligations: list[dict] = []

    def add_lan(self, uid: str) -> None:
        self.add_user(
            uid, jars=[(c, n, col, i, bal, pct) for c, n, col, i, _, bal, pct, *_ in LAN_JARS]
        )
        kinds = {j[0]: j[4] for j in LAN_JARS}
        for code, j in self.users[uid]["jars"].items():
            j.update(kind=kinds[code], system_role=None)
        self.users[uid]["jars"]["chua_phan_loai"] = dict(UNCLASSIFIED)

    def credit_line(self, uid):
        return {"product_code": "bnpl_sim", "limit_vnd": Decimal(3_000_000), "outstanding_vnd": Decimal(0), "due_day": 5, "status": "active"}  # fmt: skip

    def list_obligations(self, uid, *, status="active", due_before=None, limit=50):
        return [o for o in self.obligations if status == "all" or o["status"] == status]

    def reference_fees(self):
        return phase3_helpers.FEE_ROWS

    def write_credit_purchase(self, uid, *, tx, fee, pay_jar, audit, claim, tool, due_date_for, limit_check):  # fmt: skip
        line = self.credit_line(uid)
        limit_check(line)
        principal, fee_vnd = abs(int(tx["signed"])), int(fee["amount_vnd"])
        ob = {
            "id": "00000000-0000-0000-0000-0000000000b1", "kind": "bnpl", "name": fee["name"],
            "amount_vnd": principal + fee_vnd, "amount_min_vnd": None, "amount_max_vnd": None,
            "due_date": due_date_for(int(line["due_day"])), "cycle": "once", "due_day": None,
            "status": "active", "pay_jar_code": pay_jar,
        }  # fmt: skip
        self.obligations.append(ob)
        facts = {
            "obligation_id": ob["id"], "obligation_created": True, "principal_vnd": principal, "fee_vnd": fee_vnd,
            "amount_vnd": ob["amount_vnd"], "due_date": ob["due_date"], "outstanding_vnd": principal,
            "limit_vnd": 3_000_000, "jar": tx["jar"],
        }  # fmt: skip
        return WriteResult(tool, tx["tx_id"], tx["occurred_at"], tx["app_date"], facts=facts)


def lan_context_jars():
    return [
        jar_row(c, k, bal, pct, order, [50_000] * 47)
        for c, _, _, _, k, bal, pct, order, *_ in LAN_JARS
    ]


def buy_with_bnpl(jar: str, pay_jar: str | None) -> dict:
    """Mua 1.200.000 ₫ bằng Trả sau qua luồng ghi thật của ledger (xem trước rồi ghi); trả nghĩa vụ đã lưu. `pay_jar` vắng thì không
    truyền hũ trả (bước xem trước của ví không có hũ obligation phải từ chối)."""
    service, _, clock = make_service(())
    repo = LanWallet(clock)
    repo.add_lan(LAN)
    service.repo, service.ref = repo, ReferenceData(repo, 300)  # type: ignore[assignment]
    params = {
        "kind": "expense",
        "amount_vnd": 1_200_000,
        "jar": jar,
        "funding": "credit",
        "counterparty": "Tiki",
        **({"pay_jar": pay_jar} if pay_jar else {}),
    }
    trace = "a" * 32
    prep, _ = service.prepare_action(
        LAN, RECORD_TRANSACTION, params, trace_id=trace, source_tool="ledger"
    )
    service.apply_generic(
        LAN, prep, None, trace_id=trace, channel="chat", source_tool="ledger", claim_ref=None
    )
    (ob,) = repo.obligations
    return ob


def forecast_jars_charged(ob: dict) -> list[str]:
    """Hũ nào của dự báo thật có khoản Trả sau vừa sinh (nghĩa vụ đọc lại từ DB như `app_get_forecast_context`)."""
    stored = {**ob, "due_date": ob["due_date"].isoformat()}
    inp = build(context_rows(jars=lan_context_jars(), obligations=[stored])).inputs
    return [j.code for j in inp.jars for f in j.outflows if f.label == ob["name"]]


def what_if_and_check_jars(monkeypatch, jar: str | None, pay_jar: str) -> tuple[str, str]:
    """Hũ phải trả mà what-if và kiểm tra trước khi chi báo cho cùng món mua đó (cùng hũ trả đã chọn), trên cùng tài khoản trước khi
    mua."""
    monkeypatch.setattr(phase3_helpers, "JARS", LAN_JARS)
    monkeypatch.setattr(scenario_mod.forecast_repo, "save_scenario", lambda *a, **k: None)
    pipeline, _, repo, ref, settings = phase3_helpers.build(
        obligations=[], context={"jars": lan_context_jars(), "obligations": []}
    )
    spec = {
        "kind": "bnpl_purchase", "amount_vnd": 1_200_000, "funding_source": "credit", "pay_jar": pay_jar,
    }  # fmt: skip
    if jar:
        spec["jar_code"] = jar
    what_if = ScenarioEngine(pipeline, repo, ref, settings).run(
        phase3_helpers.USER, spec, trace_id="t1"
    )
    check = AffordabilityEngine(pipeline, repo, ref, settings).check(
        phase3_helpers.USER, amount_vnd=1_200_000, funding_source="credit", jar=jar, pay_jar=pay_jar
    )
    return (
        what_if["data"]["obligation_impact"]["at_due"][0]["jar"]["code"],
        check["data"]["credit"]["at_due"][0]["jar"]["code"],
    )


@pytest.mark.parametrize(
    ("chosen", "pay_jar"),
    [
        ("giai_tri", "giai_tri"),  # mua vào hũ Giải trí, trả từ chính hũ đó
        (None, "an_uong"),  # khoản chi nằm ở Chưa phân loại, người dùng chọn trả từ hũ Ăn uống
    ],
)
def test_tra_sau_khong_co_hu_nghia_vu_du_bao_what_if_va_kiem_truoc_khi_chi_cung_mot_hu(
    monkeypatch, chosen, pay_jar
):
    # quy tắc đã chốt (#39): ví không có hũ obligation mà không truyền hũ trả thì bước xem trước hỏi lại (PARAMS_INVALID)
    with pytest.raises(YofinaError) as e:
        buy_with_bnpl(chosen or "chua_phan_loai", None)
    assert e.value.code == ErrorCode.PARAMS_INVALID
    # có hũ trả: sổ cái, dự báo, what-if và kiểm tra trước khi chi tính khoản nợ vào CÙNG một hũ (#15)
    ob = buy_with_bnpl(chosen or "chua_phan_loai", pay_jar)
    assert ob["pay_jar_code"] == pay_jar
    assert forecast_jars_charged(ob) == [pay_jar]  # dự báo thật không bỏ khoản nợ
    assert what_if_and_check_jars(monkeypatch, chosen, pay_jar) == (pay_jar, pay_jar)


def test_tra_sau_ghi_tu_truoc_khong_co_hu_tra_van_nam_trong_du_bao():
    """Khoản Trả sau ghi từ trước khi có quy tắc hỏi hũ trả (không lưu hũ trả, ví không có hũ obligation) vẫn vào dự báo: lùi về hũ
    chi tiêu đầu tiên (`bnpl_pay_jar`, #15), không rơi khỏi dự báo."""
    ob = {**buy_with_bnpl("giai_tri", "giai_tri"), "pay_jar_code": None}
    assert forecast_jars_charged(ob) == ["an_uong"]


def test_nguong_lich_su_cua_cong_xac_suat_ghi_de_duoc_qua_cau_hinh():
    # BR-31: ngưỡng số ngày lịch sử để hiện % theo loại hũ, mặc định theo backtest, cấu hình ghi đè được
    strict = build(
        probability_min_history_days_dense=400, probability_min_history_days_sparse=400
    ).inputs
    res = forecast_user(strict)
    assert all(not jf.summary.show_probability and jf.summary.p_shortfall is None for jf in res.jars)
    assert all(jf.summary.confidence_band in ("low", "medium", "high") for jf in res.jars)
    loose = build(probability_min_history_days_dense=21, probability_min_history_days_sparse=21).inputs
    shown = [jf.summary for jf in forecast_user(loose).jars if jf.summary.show_probability]
    assert shown and all(s.p_shortfall is not None for s in shown)  # 47 ngày >= 21: được hiện %
