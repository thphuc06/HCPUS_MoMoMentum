"""Gộp kịch bản what-if trong một cuộc chat: `run_scenario` nhận `with_scenarios` và `conversation_id`, `list_scenarios` trả các
kịch bản đã chạy của cuộc chat. Chạy engine ML THẬT trên dữ liệu dựng sẵn (như `test_scenario.py`); kho `scenarios` là một bản
trong bộ nhớ thay `save_scenario` và `list_conversation_scenarios` (cùng hình dạng dòng mà hàm DB trả)."""

from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from conftest import BASE, build_registry
from jsonschema import Draft202012Validator
from phase3_helpers import APP_DATE, USER, build

from yofina_core.errors import ErrorCode, YofinaError
from yofina_forecast import scenario as scenario_mod
from yofina_forecast.scenario import ScenarioEngine
from yofina_forecast.tool import handle_gateway

REGISTRY = build_registry()
RUN_RESULT = Draft202012Validator(
    {"$ref": f"{BASE}/tools/forecast.results.schema.json#/$defs/RunScenarioResult"}, registry=REGISTRY
)
LIST_RESULT = Draft202012Validator(
    {"$ref": f"{BASE}/tools/forecast.results.schema.json#/$defs/ListScenariosResult"}, registry=REGISTRY
)
CONV = "c" * 40  # session id của AgentCore Runtime dài 33 tới 256 ký tự


def shoes(amount: int = 300_000, **kw):
    return {"kind": "one_time_purchase", "amount_vnd": amount, "funding_source": "jar", "jar_code": "giai_tri", "label": "giày", **kw}


def sandals(amount: int = 200_000, **kw):
    return {"kind": "one_time_purchase", "amount_vnd": amount, "funding_source": "jar", "jar_code": "giai_tri", "label": "dép", **kw}


def bnpl(amount: int = 1_200_000, **kw):
    return {"kind": "bnpl_purchase", "amount_vnd": amount, "funding_source": "credit", "label": "tai nghe", **kw}


class Store:
    """`scenarios` trong bộ nhớ: `save` thay `forecast_repo.save_scenario`, `list` thay `list_conversation_scenarios`."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.clock = datetime(2026, 12, 10, 3, 0, tzinfo=UTC)

    def save(self, repo, user_id, **kw):
        self.clock += timedelta(seconds=5)
        self.rows.append({"user_id": user_id, "id": uuid.uuid4(), "created_at": self.clock, **kw})

    def list(self, repo, user_id, conversation_id, limit):
        mine = [r for r in self.rows if r["user_id"] == user_id and r["conversation_id"] == conversation_id]
        mine.sort(key=lambda r: r["created_at"], reverse=True)
        out = []
        for r in mine[: min(max(limit, 1), 10)]:
            res = r["result"]
            out.append(
                {
                    "id": r["id"],
                    "kind": r["kind"],
                    "spec": r["spec"],
                    "bundle": r["bundle"],
                    "result_label": res["timelines"][0]["compare"]["label"],
                    "result_bundle": res.get("bundle"),
                    "created_at": r["created_at"],
                }
            )
        return out


@pytest.fixture
def store(monkeypatch):
    s = Store()
    monkeypatch.setattr(scenario_mod.forecast_repo, "save_scenario", s.save)
    monkeypatch.setattr(scenario_mod.forecast_repo, "list_conversation_scenarios", s.list)
    return s


def engine(**kw):
    pipeline, mem, repo, ref, settings = build(**kw)
    return ScenarioEngine(pipeline, repo, ref, settings), mem


def run(eng, scenario, **kw):
    res = eng.run(USER, scenario, trace_id="t1", **kw)
    errs = [f"{list(e.path)}: {e.message}" for e in RUN_RESULT.iter_errors(res)]
    assert not errs, errs
    return res["data"]


def listing(eng, **kw):
    res = eng.list_scenarios(USER, **kw)
    errs = [f"{list(e.path)}: {e.message}" for e in LIST_RESULT.iter_errors(res)]
    assert not errs, errs
    return res


# --- gộp -------------------------------------------------------------------------------------------------
def test_gop_hai_mua_mot_lan_cung_hu_sau_thap_hon_truoc_dung_tong_hai_khoan(store):
    eng, _ = engine()
    d = run(eng, sandals(), with_scenarios=[shoes()], conversation_id=CONV)
    tl = d["timelines"][0]
    assert tl["jar"]["code"] == "giai_tri" and tl["compare"]["kind"] == "one_time_purchase"
    before, after = tl["days"], tl["compare"]["after"]["days"]
    # cùng dãy số ngẫu nhiên: mọi phân vị số dư dịch ĐÚNG tổng hai khoản, không nhiễu mẫu
    assert all(a["p50_vnd"] == b["p50_vnd"] - 500_000 for a, b in zip(after, before, strict=True))
    assert all(a["p10_vnd"] == b["p10_vnd"] - 500_000 for a, b in zip(after, before, strict=True))
    assert tl["compare"]["delta"]["min_balance_delta_vnd"] == -500_000
    assert d["effects"][0]["min_balance_delta_vnd"] == -500_000
    assert [e["jar"]["code"] for e in d["effects"]] == ["giai_tri"]  # hũ khác không bị tính lại
    assert tl["compare"]["label"] == "mua giày 300 nghìn + mua dép 200 nghìn"
    # kịch bản chính (dép) ở spec; bundle theo thứ tự áp (with_scenarios rồi scenario), mỗi khoản có nhãn riêng
    assert d["spec"]["label"] == "dép" and d["spec"]["amount_vnd"] == 200_000
    assert [(b["kind"], b["label"], b["amount_vnd"], b["jar_code"]) for b in d["bundle"]] == [
        ("one_time_purchase", "mua giày 300 nghìn", 300_000, "giai_tri"),
        ("one_time_purchase", "mua dép 200 nghìn", 200_000, "giai_tri"),
    ]
    assert d["bundle"][0]["spec"]["label"] == "giày" and d["bundle"][1]["spec"] == d["spec"]
    assert d["bundle_total_vnd"] == 500_000
    assert d["bundle"][0]["spec"]["date"] == APP_DATE.isoformat()  # spec đã chuẩn hóa như engine chạy


def test_gop_theo_vi_du_giay_800k_va_dep_300k_du_vuot_so_du_hu(store):
    eng, _ = engine()
    d = run(eng, sandals(300_000), with_scenarios=[shoes(800_000)], conversation_id=CONV)
    assert d["bundle_total_vnd"] == 1_100_000
    assert d["timelines"][0]["compare"]["delta"]["min_balance_delta_vnd"] == -1_100_000
    assert d["timelines"][0]["compare"]["label"] == "mua giày 800 nghìn + mua dép 300 nghìn"
    assert d["effects"][0]["status_after"] == "short"  # 760k trong hũ không đủ 1,1 triệu


def test_luu_dong_scenarios_kem_conversation_id_va_bundle(store):
    eng, _ = engine()
    run(eng, sandals(), with_scenarios=[shoes()], conversation_id=CONV)
    (row,) = store.rows
    assert row["conversation_id"] == CONV
    assert row["kind"] == "one_time_purchase" and row["spec"]["label"] == "dép"
    assert [b["label"] for b in row["bundle"]] == ["giày", "dép"] and row["bundle"][-1] == row["spec"]
    assert row["result"]["bundle_total_vnd"] == 500_000 and len(row["result"]["bundle"]) == 2


def test_gop_tra_sau_va_mua_mot_lan_chi_phi_lay_tu_khoan_tra_sau_duy_nhat(store):
    eng, _ = engine()
    d = run(eng, bnpl(), with_scenarios=[shoes()], conversation_id=CONV)
    c = d["obligation_impact"]["cost"]
    assert (c["principal_vnd"], c["item_cost_vnd"], c["total_due_vnd"]) == (1_200_000, 1_200_000, 2_200_000)
    assert d["obligation_impact"]["at_due"][0]["jar"]["code"] == "nghia_vu"
    assert [b["kind"] for b in d["bundle"]] == ["one_time_purchase", "bnpl_purchase"]
    assert d["bundle_total_vnd"] == 1_500_000  # 300k mua một lần + 1,2 triệu Trả sau
    assert d["spec"]["kind"] == "bnpl_purchase" and d["timelines"][0]["compare"]["kind"] == "bnpl_purchase"
    assert {e["jar"]["code"] for e in d["effects"]} == {"giai_tri", "nghia_vu"}
    assert {t["jar"]["code"] for t in d["timelines"]} == {"giai_tri", "nghia_vu"}  # xếp theo mức bị tác động như trước
    assert d["timelines"][0]["compare"]["label"].startswith("mua giày 300 nghìn + mua tai nghe 1,2 triệu bằng")


def test_tra_sau_o_with_scenarios_va_mua_mot_lan_la_kich_ban_chinh(store):
    eng, _ = engine()
    d = run(eng, shoes(), with_scenarios=[bnpl()], conversation_id=CONV)
    assert d["obligation_impact"]["cost"]["item_cost_vnd"] == 1_200_000
    assert [b["kind"] for b in d["bundle"]] == ["bnpl_purchase", "one_time_purchase"]
    assert d["spec"]["kind"] == "one_time_purchase" and d["bundle_total_vnd"] == 1_500_000


def test_khoan_tra_sau_thay_cac_khoan_chi_cung_ngay_den_han_cua_bo(store):
    """Khoản Trả sau được áp sau cùng nên `due_vnd` của hũ trả gồm cả khoản mua một lần của bó rơi đúng ngày đến hạn 05/12."""
    eng, _ = engine()
    pay_day = {"kind": "one_time_purchase", "amount_vnd": 100_000, "funding_source": "jar", "jar_code": "nghia_vu", "date": "2026-12-05"}
    alone = run(eng, bnpl())
    bundled = run(eng, pay_day, with_scenarios=[bnpl()])
    assert alone["obligation_impact"]["at_due"][0]["due_vnd"] == 2_200_000
    assert bundled["obligation_impact"]["at_due"][0]["due_vnd"] == 2_300_000


def test_gop_khoan_chi_dinh_ky_gop_su_kien_va_cong_don_nghia_vu(store):
    eng, _ = engine()
    gym = {"kind": "recurring_expense", "amount_vnd": 50_000, "cycle": "weekly", "date": "2026-11-25", "jar_code": "giai_tri", "label": "gói tập"}
    d = run(eng, shoes(date="2026-11-23"), with_scenarios=[gym], conversation_id=CONV)
    ev = d["timelines"][0]["compare"]["after"]["events"]
    assert [e["date"] for e in ev][:3] == ["2026-11-23", "2026-11-25", "2026-12-02"]  # sự kiện gộp, theo ngày
    assert d["bundle_total_vnd"] == 300_000  # khoản chi định kỳ không vào tổng mua
    assert d["bundle"][0]["amount_vnd"] == 50_000 and d["bundle"][0]["kind"] == "recurring_expense"


def test_bon_khoan_truoc_cong_kich_ban_chinh_la_nam_khoan(store):
    eng, _ = engine()
    prior = [shoes(10_000, label=f"món {i}") for i in range(4)]
    d = run(eng, sandals(10_000), with_scenarios=prior, conversation_id=CONV)
    assert len(d["bundle"]) == 5 and d["bundle_total_vnd"] == 50_000
    assert d["timelines"][0]["compare"]["delta"]["min_balance_delta_vnd"] == -50_000
    assert len(d["timelines"][0]["compare"]["label"]) <= 80


def test_kich_ban_chinh_la_doi_luong_van_gop_duoc_voi_khoan_da_giu(store):
    eng, _ = engine()
    d = run(eng, {"kind": "income_change", "new_monthly_salary_vnd": 12_000_000}, with_scenarios=[shoes()], conversation_id=CONV)
    assert d["spec"]["kind"] == "income_change" and [b["kind"] for b in d["bundle"]] == ["one_time_purchase", "income_change"]
    assert "bundle_total_vnd" in d and d["bundle_total_vnd"] == 300_000
    assert "amount_vnd" not in d["bundle"][1]  # đổi lương không có amount_vnd


# --- bị từ chối ------------------------------------------------------------------------------------------
def test_hai_khoan_tra_sau_trong_mot_bo_bi_tu_choi(store):
    eng, _ = engine()
    with pytest.raises(YofinaError) as e:
        eng.run(USER, bnpl(), with_scenarios=[bnpl(500_000, label="loa")], trace_id="t", conversation_id=CONV)
    assert e.value.code == ErrorCode.SCENARIO_INVALID and "hai khoản Trả sau" in e.value.message
    with pytest.raises(YofinaError) as e2:  # hai khoản Trả sau cùng nằm ở with_scenarios
        eng.run(USER, shoes(), with_scenarios=[bnpl(), bnpl(500_000)], trace_id="t")
    assert e2.value.code == ErrorCode.SCENARIO_INVALID and "hai khoản Trả sau" in e2.value.message
    assert not store.rows  # lỗi thì không ghi kịch bản


@pytest.mark.parametrize(
    ("bad", "word"),
    [
        ({"kind": "income_change", "new_monthly_salary_vnd": 12_000_000}, "đổi lương"),
        ({"kind": "jar_transfer", "amount_vnd": 100_000, "from_jar": "giai_tri", "to_jar": "an_uong"}, "chuyển hũ"),
        ({"kind": "goal_delay", "jar_code": "giai_tri", "delay_months": 2}, "lùi mục tiêu"),
    ],
)
def test_loai_khong_cho_gop_trong_with_scenarios_bi_tu_choi(store, bad, word):
    eng, _ = engine()
    with pytest.raises(YofinaError) as e:
        eng.run(USER, shoes(), with_scenarios=[bad], trace_id="t")
    assert e.value.code == ErrorCode.SCENARIO_INVALID and word in e.value.message
    assert not store.rows


def test_qua_bon_khoan_truoc_bi_tu_choi(store):
    eng, _ = engine()
    with pytest.raises(YofinaError) as e:
        eng.run(USER, shoes(), with_scenarios=[sandals(10_000)] * 5, trace_id="t")
    assert e.value.code == ErrorCode.SCENARIO_INVALID and "4" in e.value.message
    assert not store.rows


@pytest.mark.parametrize(
    "bad",
    ["giày", {"kind": "one_time_purchase"}, [None], [{"amount_vnd": 5}], [{"kind": "nope"}], [[1, 2]]],
)
def test_with_scenarios_sai_hinh_dang_la_params_invalid(store, bad):
    eng, _ = engine()
    with pytest.raises(YofinaError) as e:
        eng.run(USER, shoes(), with_scenarios=bad, trace_id="t")
    assert e.value.code == ErrorCode.PARAMS_INVALID
    assert not store.rows


def test_loi_o_khoan_da_giu_noi_ro_la_khoan_truoc_do(store):
    eng, _ = engine()
    with pytest.raises(YofinaError) as e:
        eng.run(USER, sandals(), with_scenarios=[shoes(date="2026-11-01")], trace_id="t")
    assert e.value.code == ErrorCode.SCENARIO_INVALID
    assert e.value.message.startswith("Khoản đã giữ từ trước (mua một lần):")
    with pytest.raises(YofinaError) as e2:  # lỗi của kịch bản chính giữ nguyên thông điệp
        eng.run(USER, sandals(date="2026-11-01"), with_scenarios=[shoes()], trace_id="t")
    assert e2.value.code == ErrorCode.SCENARIO_INVALID and not e2.value.message.startswith("Khoản")


@pytest.mark.parametrize("bad", [123, "x" * 257, ["a"], {"id": "a"}, True])
def test_conversation_id_sai_kieu_hoac_qua_dai_la_params_invalid(store, bad):
    eng, _ = engine()
    with pytest.raises(YofinaError) as e:
        eng.run(USER, shoes(), conversation_id=bad, trace_id="t")
    assert e.value.code == ErrorCode.PARAMS_INVALID and not store.rows


# --- tương thích ngược ---------------------------------------------------------------------------------
def test_khong_truyen_truong_moi_hanh_vi_nhu_cu_bundle_mot_phan_tu(store):
    eng, _ = engine()
    d = run(eng, shoes(123_000))
    assert [b["kind"] for b in d["bundle"]] == ["one_time_purchase"] and len(d["bundle"]) == 1
    assert d["bundle"][0]["spec"] == d["spec"] and d["bundle"][0]["label"] == "mua giày 123 nghìn"
    assert "bundle_total_vnd" not in d
    assert d["timelines"][0]["compare"]["label"] == "mua giày 123 nghìn"
    assert d["timelines"][0]["compare"]["delta"]["min_balance_delta_vnd"] == -123_000
    (row,) = store.rows
    assert row["conversation_id"] is None and row["bundle"] == [row["spec"]]


def test_with_scenarios_rong_hoac_none_giong_khong_truyen(store):
    eng, _ = engine()
    a = run(eng, shoes())
    b = run(eng, shoes(), with_scenarios=[])
    c = run(eng, shoes(), with_scenarios=None, conversation_id="")
    def same(x):  # mỗi lần chạy có scenario_id riêng
        return [{**t, "compare": {**t["compare"], "scenario_id": None}} for t in x["timelines"]]

    for x in (b, c):
        assert same(x) == same(a) and x["effects"] == a["effects"] and x["bundle"] == a["bundle"]
        assert "bundle_total_vnd" not in x
    assert store.rows[-1]["conversation_id"] is None  # chuỗi rỗng coi như vắng


def test_gop_mot_khoan_giong_chay_tung_khoan_tren_cung_hu_cung_day_so(store):
    """Hai lần chạy đơn, mỗi lần mất một khoản, cộng chênh lệch lại bằng đúng lần chạy gộp (cùng dãy số ngẫu nhiên)."""
    eng, _ = engine()
    s1 = run(eng, shoes())["timelines"][0]["compare"]["delta"]["min_balance_delta_vnd"]
    s2 = run(eng, sandals())["timelines"][0]["compare"]["delta"]["min_balance_delta_vnd"]
    both = run(eng, sandals(), with_scenarios=[shoes()])["timelines"][0]["compare"]["delta"]["min_balance_delta_vnd"]
    assert both == s1 + s2


# --- hàm thuần -------------------------------------------------------------------------------------------
def test_apply_bundle_targets_dat_hu_cua_kich_ban_chinh_len_dau_va_khong_trung():
    from yofina_core.scenario import parse_scenario
    from yofina_forecast.inputs import build_inputs
    from yofina_forecast.scenario import JarMeta, apply_bundle

    pipeline, _, repo, _, settings = build()
    ctx = pipeline.load_context(USER, pipeline.now())
    inputs = build_inputs(ctx, settings, USER, n_paths=100).inputs
    metas = {r["code"]: JarMeta.from_row(r) for r in repo.jar_view(USER).jars}
    kw = dict(today=APP_DATE, horizon=30, shares=[], salary_vnd=0, obligations=[], credit=None)
    eating = {**shoes(50_000), "jar_code": "an_uong"}
    applied = apply_bundle([parse_scenario(shoes()), parse_scenario(eating), parse_scenario(sandals())], inputs, metas, **kw)
    assert applied.targets == ["giai_tri", "an_uong"] and len(applied.parts) == 3
    assert applied.added_obligation_vnd == 0 and applied.cost is None
    one = apply_bundle([parse_scenario(shoes())], inputs, metas, **kw)
    assert one.parts == () and one.targets == ["giai_tri"]


# --- list_scenarios --------------------------------------------------------------------------------------
def test_list_scenarios_chi_lay_cuoc_chat_nay_moi_nhat_truoc(store):
    eng, _ = engine()
    run(eng, shoes(), conversation_id=CONV)
    run(eng, shoes(), conversation_id="other-" + "z" * 30)  # cuộc chat khác
    run(eng, sandals(), with_scenarios=[shoes()], conversation_id=CONV)
    run(eng, bnpl())  # không gắn cuộc chat nào
    res = listing(eng, conversation_id=CONV)
    items = res["data"]["scenarios"]
    assert res["app_date"] == APP_DATE.isoformat() and res["as_of"].endswith("Z")
    assert [i["label"] for i in items] == ["mua giày 300 nghìn + mua dép 200 nghìn", "mua giày 300 nghìn"]
    newest, oldest = items
    assert newest["kind"] == "one_time_purchase" and newest["spec"]["label"] == "dép"
    assert [b["label"] for b in newest["bundle"]] == ["mua giày 300 nghìn", "mua dép 200 nghìn"]
    assert newest["bundle"][0] == {
        "kind": "one_time_purchase", "label": "mua giày 300 nghìn", "amount_vnd": 300_000,
        "jar_code": "giai_tri", "spec": newest["bundle"][0]["spec"],
    }  # fmt: skip
    assert len(oldest["bundle"]) == 1 and oldest["bundle"][0]["spec"] == oldest["spec"]
    assert newest["created_at"] > oldest["created_at"] and newest["scenario_id"] != oldest["scenario_id"]
    assert listing(eng, conversation_id="khong-co-" + "x" * 30)["data"]["scenarios"] == []


def test_list_scenarios_limit_mac_dinh_5_kep_trong_1_den_10(store):
    eng, _ = engine()
    for _i in range(7):
        run(eng, shoes(10_000), conversation_id=CONV)
    n = lambda **kw: len(listing(eng, conversation_id=CONV, **kw)["data"]["scenarios"])  # noqa: E731
    assert n() == 5 and n(limit=2) == 2 and n(limit=0) == 1 and n(limit=99) == 7 and n(limit=10) == 7


@pytest.mark.parametrize("cid", [None, "", 5, "x" * 257])
def test_list_scenarios_thieu_hoac_sai_conversation_id(store, cid):
    eng, _ = engine()
    with pytest.raises(YofinaError) as e:
        eng.list_scenarios(USER, conversation_id=cid)
    assert e.value.code == ErrorCode.PARAMS_INVALID


@pytest.mark.parametrize("limit", ["3", 2.5, True, [1]])
def test_list_scenarios_limit_sai_kieu(store, limit):
    eng, _ = engine()
    with pytest.raises(YofinaError) as e:
        eng.list_scenarios(USER, conversation_id=CONV, limit=limit)
    assert e.value.code == ErrorCode.PARAMS_INVALID


def test_list_scenarios_dong_cu_khong_co_bundle_thi_bundle_la_spec_chinh(store):
    eng, _ = engine()
    run(eng, shoes(), conversation_id=CONV)
    old = copy.deepcopy(store.rows[0])
    old["bundle"] = None
    old["result"] = {k: v for k, v in old["result"].items() if k not in ("bundle", "bundle_total_vnd")}  # như dòng trước 0051
    store.rows[:] = [old]
    (item,) = listing(eng, conversation_id=CONV)["data"]["scenarios"]
    assert item["label"] == "mua giày 300 nghìn"
    assert item["bundle"] == [
        {"kind": "one_time_purchase", "label": "mua giày 300 nghìn", "amount_vnd": 300_000, "jar_code": "giai_tri", "spec": item["spec"]}
    ]


def test_list_scenarios_lay_ngay_mo_phong_cua_nguoi_dung(store):
    eng, _ = engine(user={"id": USER, "monthly_salary_vnd": 9_000_000, "payday_day": 5, "risk_tolerance": "medium", "clock_offset_days": -19})
    assert listing(eng, conversation_id=CONV)["app_date"] == APP_DATE.isoformat()
    eng.repo.jar_view = lambda uid: SimpleNamespace(clock_offset_days=None, jars=())  # chưa có hồ sơ
    with pytest.raises(YofinaError) as e:
        eng.list_scenarios(USER, conversation_id=CONV)
    assert e.value.code == ErrorCode.PROFILE_INCOMPLETE


# --- Gateway ---------------------------------------------------------------------------------------------
def ctx_for(name: str):
    return SimpleNamespace(client_context=SimpleNamespace(custom={"bedrockAgentCoreToolName": name}))


def test_handle_gateway_chuyen_tham_so_moi_cho_run_scenario_va_list_scenarios(store):
    eng, _ = engine()
    pipeline = eng.pipeline
    run_res = handle_gateway(
        {"user_id": USER, "scenario": sandals(), "with_scenarios": [shoes()], "conversation_id": CONV},
        ctx_for("forecast___run_scenario"), None, pipeline, eng,  # type: ignore[arg-type]
    )  # fmt: skip
    assert run_res["status"] == "OK" and run_res["data"]["bundle_total_vnd"] == 500_000
    list_res = handle_gateway(
        {"user_id": USER, "conversation_id": CONV, "limit": 3}, ctx_for("forecast___list_scenarios"), None, pipeline, eng  # type: ignore[arg-type]
    )
    assert list_res["status"] == "OK" and len(list_res["data"]["scenarios"]) == 1
    missing = handle_gateway({"user_id": USER}, ctx_for("forecast___list_scenarios"), None, pipeline, eng)  # type: ignore[arg-type]
    assert missing["status"] == "ERROR" and missing["code"] == "PARAMS_INVALID"
    bnpl_twice = handle_gateway(
        {"user_id": USER, "scenario": bnpl(), "with_scenarios": [bnpl()]}, ctx_for("forecast___run_scenario"), None, pipeline, eng  # type: ignore[arg-type]
    )
    assert bnpl_twice["code"] == "SCENARIO_INVALID" and "hai khoản Trả sau" in bnpl_twice["message"]
    no_user = handle_gateway({"conversation_id": CONV}, ctx_for("forecast___list_scenarios"), None, pipeline, eng)  # type: ignore[arg-type]
    assert no_user["code"] == "UNAUTHENTICATED"


def test_ten_mon_bo_chu_mua_dung_dau():
    from yofina_forecast.scenario import item_name

    assert item_name("Mua dép") == "dép"
    assert item_name("mua  giày ") == "giày"
    assert item_name("muachung") == "muachung"
    assert item_name(None) is None and item_name("mua ") is None
