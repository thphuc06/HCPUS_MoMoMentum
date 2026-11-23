"""Điểm chống chịu (phase 4, F4): công thức bốn thành phần đọc từ `resilience_defaults.json`, engine phía Lambda forecast (đọc dữ liệu,
chấm, ghi `resilience_scores`, trả tool và REST), hàm batch N2. Engine ML THẬT, kho dữ liệu trong bộ nhớ (xem `World`).

Số trong test đến từ cấu hình đã nạp (`load_resilience_config`) hoặc được tính tay từ chính các mốc đó, không gắn cứng điểm mong đợi."""

from __future__ import annotations

import copy
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
import pytest
from conftest import BASE, build_registry
from jsonschema import Draft202012Validator
from memory_repo import MemoryRepo
from phase3_helpers import OBLIGATION_ROWS
from pipeline_helpers import APP_DATE, NOW, context_rows, jar_row, make_settings

from yofina_core.blocks import ResilienceScoreData, block_to_wire, build_resilience_score
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.resilience import (
    band_for_score,
    load_resilience_config,
    parse_config,
)
from yofina_forecast import tool as tool_mod
from yofina_forecast.resilience import (
    Gathered,
    ResilienceEngine,
    compute_and_store,
    emergency_jar,
    score_of,
    window_obligations,
)
from yofina_forecast.runner import Pipeline
from yofina_ml.resilience import (
    BAND_WORD,
    GoalFact,
    ResilienceInputs,
    goal_progress,
    interpolate,
    monthly_needed_vnd,
)

REGISTRY = build_registry()
TOOL_RESULT = Draft202012Validator(
    {"$ref": f"{BASE}/tools/forecast.results.schema.json#/$defs/GetResilienceScoreResult"},
    registry=REGISTRY,
)
REST_BLOCK = Draft202012Validator(
    {"$ref": f"{BASE}/rest/openapi.yaml#/components/schemas/ResilienceScoreResponse"},
    registry=REGISTRY,
)
USER = "u1"
CFG = load_resilience_config()


def errors_of(validator: Draft202012Validator, doc: Any) -> list[str]:
    return [f"{list(e.path)}: {e.message}" for e in validator.iter_errors(doc)]


# =====================================================================================
# Thế giới thử: kho trong bộ nhớ có đủ hàm mà engine đọc (hũ kèm mục tiêu, nghĩa vụ, điểm đã lưu)
# =====================================================================================
JARS = [
    # code, kind, balance, split, order, goal_vnd, goal_date
    ("an_uong", "spending", 900_000, 30, 1, None, None),
    ("di_lai", "spending", 300_000, 10, 2, None, None),
    ("giai_tri", "spending", 500_000, 10, 3, None, None),
    ("du_lich", "saving", 1_200_000, 10, 4, 6_000_000, date(2027, 4, 1)),
    ("du_phong", "saving", 2_000_000, 20, 5, None, None),
    ("nghia_vu", "obligation", 700_000, 20, 6, None, None),
]
RENT = {
    "id": "00000000-0000-0000-0000-0000000000a1",
    "kind": "rent",
    "name": "Tiền thuê phòng",
    "amount_vnd": 2_000_000,
    "amount_min_vnd": None,
    "amount_max_vnd": None,
    "due_date": "2026-12-06",
    "cycle": "monthly",
    "due_day": 6,
    "pay_jar_code": "nghia_vu",
}


def _ledger_obligation(o: dict[str, Any]) -> dict[str, Any]:
    return {
        **o,
        "amount_vnd": Decimal(o["amount_vnd"]),
        "due_date": o["due_date"]
        if isinstance(o["due_date"], date)
        else date.fromisoformat(o["due_date"]),
        "status": "active",
        "is_essential": o["kind"] in ("rent", "bill"),
    }


class World(MemoryRepo):
    """`MemoryRepo` cộng các hàm đọc/ghi mà `ResilienceEngine` cần (cùng hình dạng hàng của hàm DB thật)."""

    def __init__(self, rows, jars, obligations, *, paid: int = 3) -> None:
        super().__init__(rows)
        self.jars = jars
        self.obl = obligations
        self.paid = paid
        self.scores: list[dict[str, Any]] = []
        self.score_saves = 0

    def jar_state(self, user_id):
        out = []
        for code, kind, bal, split, order, gv, gd in self.jars:
            out.append(
                {
                    "clock_offset_days": -19,
                    "code": code,
                    "name": code.replace("_", " ").title(),
                    "color_key": "blue",
                    "icon_key": "shield",
                    "balance_vnd": Decimal(bal),
                    "split_percent": Decimal(split),
                    "sort_order": order,
                    "kind": kind,
                    "system_role": None,
                    "goal_vnd": Decimal(gv) if gv else None,
                    "goal_date": gd,
                }
            )
        return out

    def obligations(self, user_id, status="active"):
        return [o for o in self.obl if status == "all" or o["status"] == status]

    def paid_obligation_count(self, user_id, since):
        return self.paid

    def resilience(self, user_id, app_date=None):
        rows = [r for r in self.scores if app_date is None or r["app_date"] <= app_date]
        if not rows:
            return None
        row = max(rows, key=lambda r: r["app_date"])
        earlier = [r for r in self.scores if r["app_date"] < row["app_date"]]
        prev = max(earlier, key=lambda r: r["app_date"])["score"] if earlier else None
        return {**row, "previous_score": prev}

    def save_resilience(self, user_id, **kw):
        self.score_saves += 1
        self.scores = [r for r in self.scores if r["app_date"] != kw["app_date"]]
        self.scores.append(
            json.loads(json.dumps(kw, default=str))
            | {"app_date": kw["app_date"], "computed_at": kw["computed_at"]}
        )


def world(
    *, goal: bool = True, rent: bool = True, salary: int = 9_000_000, days: int = 47, **kw
) -> World:
    jars = [j if goal or j[0] != "du_lich" else (*j[:5], None, None) for j in JARS]
    spend = {
        "an_uong": [90_000 + 25_000 * (i % 5) for i in range(days)],
        "di_lai": [30_000 if i % 3 == 0 else 0 for i in range(days)],
        "giai_tri": [60_000 if i % 6 == 0 else 0 for i in range(days)],
    }
    ctx_jars = [
        jar_row(code, kind, bal, split, order, spend.get(code, [0] * days))
        for code, kind, bal, split, order, _gv, _gd in jars
    ]
    ctx_obl = [dict(o) for o in OBLIGATION_ROWS_CTX] + ([dict(RENT)] if rent else [])
    led_obl = [_ledger_obligation(o) for o in ctx_obl]
    return World(
        context_rows(days=days, salary=salary, jars=ctx_jars, obligations=ctx_obl),
        jars,
        led_obl,
        **kw,
    )


OBLIGATION_ROWS_CTX = [
    {
        "id": o["id"],
        "kind": o["kind"],
        "name": o["name"],
        "amount_vnd": int(o["amount_vnd"]),
        "amount_min_vnd": int(o["amount_min_vnd"]) if o["amount_min_vnd"] else None,
        "amount_max_vnd": int(o["amount_max_vnd"]) if o["amount_max_vnd"] else None,
        "due_date": o["due_date"].isoformat(),
        "cycle": o["cycle"],
        "due_day": o["due_day"],
        "pay_jar_code": o["pay_jar_code"] or "nghia_vu",
    }
    for o in OBLIGATION_ROWS
]


def pipe(w: World, *, now=lambda: NOW, **settings) -> Pipeline:
    return Pipeline(w, make_settings(**settings), None, clock=now)


# =====================================================================================
# Công thức (hàm thuần)
# =====================================================================================
def inputs(**kw) -> ResilienceInputs:
    base = dict(
        liquid_balance_vnd=5_400_000,
        income_vnd=9_000_000,
        variable_spend_vnd=3_000_000,
        obligations_vnd=2_400_000,
        window_days=30,
        on_time_share=1.0,
        goals=(GoalFact("du_lich", 1_000_000, 750_000),),
        obligations_by_kind={"rent": 2_000_000, "bill": 400_000},
    )
    base.update(kw)
    return ResilienceInputs(**base)


def test_noi_suy_tuyen_tinh_giua_hai_moc_va_ke_o_ngoai():
    assert interpolate(0, 0, 180) == 0 and interpolate(180, 0, 180) == 100
    assert interpolate(90, 0, 180) == pytest.approx(50)
    assert interpolate(-5, 0, 180) == 0 and interpolate(500, 0, 180) == 100
    # mốc ngược (tỷ lệ càng thấp càng tốt)
    assert interpolate(0.15, 0.5, 0.15) == 100 and interpolate(0.5, 0.5, 0.15) == 0
    assert interpolate(0.325, 0.5, 0.15) == pytest.approx(50)
    assert interpolate(float("inf"), 0.5, 0.15) == 0
    with pytest.raises(ValueError):
        interpolate(1, 2, 2)


def test_bon_thanh_phan_tinh_tu_cac_moc_cua_cau_hinh():
    r = score_of(inputs(), CFG)
    save_t = CFG.components.save.thresholds
    spend_t = CFG.components.spend.thresholds
    borrow_t = CFG.components.borrow.thresholds
    plan_t = CFG.components.plan.thresholds
    burn = (3_000_000 + 2_400_000) / 30
    runway = 5_400_000 / burn
    want_save = round(
        interpolate(runway, save_t["zero_score_days"].value, save_t["full_score_days"].value)
    )
    ratio = 5_400_000 / 9_000_000
    spend_part = interpolate(
        ratio, spend_t["zero_score_spend_ratio"].value, spend_t["full_score_spend_ratio"].value
    )
    w = spend_t["on_time_share_weight"].value
    want_spend = round((1 - w) * spend_part + w * 100)
    want_borrow = round(
        interpolate(
            2_400_000 / 9_000_000,
            borrow_t["zero_score_obligation_ratio"].value,
            borrow_t["full_score_obligation_ratio"].value,
        )
    )
    want_plan = round(
        interpolate(
            0.75,
            plan_t["zero_score_progress_ratio"].value,
            plan_t["full_score_progress_ratio"].value,
        )
    )
    assert r.scores() == {
        "save": want_save,
        "spend": want_spend,
        "borrow": want_borrow,
        "plan": want_plan,
    }
    weights = {c.key: c.weight for c in r.components}
    assert weights == {k: pytest.approx(getattr(CFG.weights, k).value) for k in weights}
    # điểm tổng là trung bình có trọng số của các điểm thành phần ĐÃ làm tròn
    assert r.score == round(sum(weights[k] * s for k, s in r.scores().items()))
    assert r.weakest == min(
        r.scores(),
        key=lambda k: (r.scores()[k], list(["save", "spend", "borrow", "plan"]).index(k)),
    )
    assert r.band == band_for_score(r.score, CFG)


def test_thanh_phan_khong_ap_dung_bi_bo_va_trong_so_chuan_hoa():
    r = score_of(inputs(goals=()), CFG)
    plan = r.component("plan")
    assert (
        plan.applicable is False and plan.score is None and plan.band is None and plan.weight == 0
    )
    live = [c for c in r.components if c.applicable]
    assert sum(c.weight for c in live) == pytest.approx(1.0)
    total = sum(getattr(CFG.weights, k).value for k in ("save", "spend", "borrow"))
    assert r.component("save").weight == pytest.approx(CFG.weights.save.value / total, abs=1e-4)
    # mọi mục tiêu đã đủ tiền (mức cần 0) cũng không áp dụng
    done = score_of(inputs(goals=(GoalFact("du_lich", 0, 500_000),)), CFG)
    assert done.component("plan").applicable is False


def test_doi_cau_hinh_doi_diem_khong_co_so_gan_cung_trong_ma():
    raw = json.loads(json.dumps(CFG.model_dump(mode="json")))
    raw["weights"]["save"]["value"] = 0.1
    raw["weights"]["spend"]["value"] = 0.1
    raw["weights"]["borrow"]["value"] = 0.7
    raw["weights"]["plan"]["value"] = 0.1
    raw["components"]["save"]["thresholds"]["full_score_days"]["value"] = 60
    raw["bands"]["weak_max_score"]["value"] = 10
    raw["bands"]["fair_max_score"]["value"] = 20
    other = parse_config(raw)
    a, b = score_of(inputs(), CFG), score_of(inputs(), other)
    assert a.score != b.score
    assert b.component("save").score == round(
        interpolate(5_400_000 / ((3_000_000 + 2_400_000) / 30), 0, 60)
    )
    assert b.component("borrow").weight == pytest.approx(0.7)
    assert b.band == band_for_score(b.score, other) == "strong"


def test_cau_giai_thich_dung_mau_cua_cau_hinh_va_nhom_bang_chu():
    r = score_of(inputs(), CFG)
    save = r.component("save")
    assert save.explanation == CFG.components.save.explanation_template.format(
        runway_days=30, full_score_days=int(CFG.components.save.thresholds["full_score_days"].value)
    )
    assert r.component("spend").explanation == CFG.components.spend.explanation_template.format(
        spend_ratio_percent=60, on_time_percent=100
    )
    assert r.component("borrow").explanation == CFG.components.borrow.explanation_template.format(
        obligation_ratio_percent=27,
        full_score_percent=int(
            100 * CFG.components.borrow.thresholds["full_score_obligation_ratio"].value
        ),
    )
    assert r.component("plan").explanation == CFG.components.plan.explanation_template.format(
        progress_percent=75
    )
    assert BAND_WORD[r.band] in r.headline and f"{r.score}/100" in r.headline
    assert CFG.label_of(r.weakest) in r.headline


def test_hang_so_thu_tu_khop_hop_dong():
    from yofina_core.blocks import RESILIENCE_ORDER
    from yofina_ml.resilience import RESILIENCE_ORDER as ML_ORDER

    assert ML_ORDER == RESILIENCE_ORDER


def test_nhom_diem_dung_nguong_cau_hinh():
    weak, fair = int(CFG.bands.weak_max_score.value), int(CFG.bands.fair_max_score.value)
    assert [band_for_score(s, CFG) for s in (0, weak, weak + 1, fair, fair + 1, 100)] == [
        "weak", "weak", "fair", "fair", "strong", "strong"
    ]  # fmt: skip


def test_khong_thu_nhap_thi_chi_trên_thu_va_nghia_vu_tren_thu_ve_khong():
    r = score_of(inputs(income_vnd=0), CFG)
    assert r.component("spend").score == round(
        CFG.components.spend.thresholds["on_time_share_weight"].value * 100
    )
    assert r.component("borrow").score == 0
    assert "hơn 100" in r.component("borrow").explanation
    assert 0 <= r.score <= 100


def test_tien_do_muc_tieu_va_muc_can():
    assert goal_progress(()) is None
    assert goal_progress((GoalFact("a", 100, 150), GoalFact("b", 300, 100))) == pytest.approx(
        200 / 400
    )
    assert monthly_needed_vnd(remaining_vnd=0, days_left=10, month_days=30) == 0
    assert monthly_needed_vnd(remaining_vnd=6_000_000, days_left=60, month_days=30) == 3_000_000
    # quá hạn: coi như còn một ngày, không chia cho 0
    assert monthly_needed_vnd(remaining_vnd=1000, days_left=-5, month_days=30) == 30_000


def test_ket_qua_ngau_nhien_luon_khop_bat_bien_cua_hop_dong():
    rng = np.random.default_rng(7)
    eng = ResilienceEngine(pipe(world()))
    stub = Gathered(
        now=NOW, ctx=None, app_date=APP_DATE, jar_rows=(), obligations=(), inputs=inputs(),  # type: ignore[arg-type]
        basis=_basis(), emergency_jar_code=None,
    )  # fmt: skip
    for _ in range(200):
        goals = tuple(
            GoalFact(f"g{i}", int(rng.integers(0, 3_000_000)), int(rng.integers(0, 3_000_000)))
            for i in range(int(rng.integers(0, 3)))
        )
        i = inputs(
            liquid_balance_vnd=int(rng.integers(0, 40_000_000)),
            income_vnd=int(rng.integers(0, 30_000_000)),
            variable_spend_vnd=int(rng.integers(0, 20_000_000)),
            obligations_vnd=int(rng.integers(0, 20_000_000)),
            on_time_share=float(rng.random()),
            goals=goals,
        )
        res = score_of(i, CFG)
        data = eng.to_data(stub, res, previous_score=None)  # Pydantic kiểm tổng, trọng số, weakest
        assert isinstance(data, ResilienceScoreData)


def _basis():
    from yofina_core.blocks import ForecastBasis

    return ForecastBasis.model_validate(
        {
            "computed_at": "2026-11-21T19:00:00Z",
            "stale": False,
            "confidence_band": "medium",
            "is_initial_estimate": False,
            "history_days": 47,
        }
    )


# =====================================================================================
# Đầu vào từ dữ liệu
# =====================================================================================
def test_nghia_vu_trong_ky_tinh_tung_lan_den_han_nhu_planner():
    today = APP_DATE
    obl = [_ledger_obligation(o) for o in OBLIGATION_ROWS_CTX] + [_ledger_obligation(RENT)]
    total, by_kind = window_obligations(obl, today, 30)
    # điện 26/11 (monthly), Trả sau 5/12 (once), thuê phòng 6/12 (monthly): cả ba trong (21/11, 21/12]
    assert by_kind == {"bill": 375_000, "bnpl": 1_000_000, "rent": 2_000_000}
    assert total == sum(by_kind.values())
    assert window_obligations(obl, today, 3)[0] == 0


def test_hu_du_phong_la_hu_tiet_kiem_khong_muc_tieu():
    w = world()
    assert emergency_jar(w.jar_state(USER))["code"] == "du_phong"
    assert emergency_jar([j for j in w.jar_state(USER) if j["code"] != "du_phong"]) is None


def test_dau_vao_lay_tu_du_lieu_nguoi_dung():
    w = world()
    eng = ResilienceEngine(pipe(w))
    g = eng.gather(USER, NOW)
    i = g.inputs
    assert i.liquid_balance_vnd == sum(j[2] for j in JARS)
    assert i.income_vnd == 9_000_000 and i.window_days == make_settings().resilience_window_days
    assert i.obligations_vnd == 3_375_000 and i.on_time_share == 1.0
    assert [x.jar_code for x in i.goals] == ["du_lich"]
    goal = i.goals[0]
    assert goal.monthly_contribution_vnd == 900_000  # lương x tỷ lệ chia 10%
    days_left = (date(2027, 4, 1) - APP_DATE).days
    assert goal.monthly_needed_vnd == -(-(6_000_000 - 1_200_000) * 30 // days_left)
    assert g.emergency_jar_code == "du_phong" and w.saves == 1  # chưa có dự báo nên đã chạy một lần


def test_tra_dung_han_tinh_tu_khoan_da_tra_va_khoan_qua_han():
    w = world(paid=3)
    w.obl[0] = {**w.obl[0], "due_date": APP_DATE - timedelta(days=2)}  # tiền điện quá hạn
    i = ResilienceEngine(pipe(w)).gather(USER, NOW).inputs
    assert i.on_time_share == pytest.approx(3 / 4)
    nothing = world(paid=0)
    nothing.obl = []
    assert ResilienceEngine(pipe(nothing)).gather(USER, NOW).inputs.on_time_share == 1.0


def test_chua_khai_luong_thi_profile_incomplete():
    w = world(salary=None)
    with pytest.raises(YofinaError) as e:
        ResilienceEngine(pipe(w)).get(USER)
    assert e.value.code == ErrorCode.PROFILE_INCOMPLETE


# =====================================================================================
# Tool, REST, lưu và đọc lại, N2
# =====================================================================================
def test_tool_tra_dung_hop_dong_va_luu_mot_dong_moi_ngay():
    w = world()
    eng = ResilienceEngine(pipe(w))
    res = eng.get(USER)
    assert not errors_of(TOOL_RESULT, res), errors_of(TOOL_RESULT, res)
    d = res["data"]
    assert [c["key"] for c in d["components"]] == ["save", "spend", "borrow", "plan"]
    assert d["config_version"] == CFG.version and d["disclaimer"] == CFG.disclaimer
    assert res["app_date"] == APP_DATE.isoformat() == d["app_date"]
    assert w.score_saves == 1 and w.scores[0]["source"] == "read"
    stored = w.scores[0]
    assert stored["score"] == d["score"] and len(stored["components"]) == 4
    assert stored["inputs"]["obligations_vnd"] == 3_375_000


def test_doc_lai_diem_da_luu_khong_tinh_lai_roi_tinh_lai_khi_cu_hoac_doi_cau_hinh_hoac_refresh():
    clock = {"now": NOW}
    w = world()
    p = pipe(w, now=lambda: clock["now"])
    eng = ResilienceEngine(p)
    first = eng.get(USER)
    assert w.score_saves == 1
    again = eng.get(USER)
    assert w.score_saves == 1 and again["data"]["score"] == first["data"]["score"]
    assert again["data"]["components"] == first["data"]["components"]
    eng.get(USER, refresh=True)
    assert w.score_saves == 2
    clock["now"] = NOW + timedelta(seconds=p.settings.freshness_seconds + 5)
    w.runs.clear()  # dự báo cũng cần tính lại (độ tươi của basis)
    eng.get(USER)
    assert w.score_saves == 3
    other = copy.deepcopy(CFG.model_dump(mode="json"))
    other["version"] = "v-khac"
    eng2 = ResilienceEngine(p, parse_config(other))
    eng2.get(USER)
    assert w.score_saves == 4 and w.scores[-1]["config_version"] == "v-khac"
    with pytest.raises(YofinaError) as e:
        eng.get(USER, refresh="co")
    assert e.value.code == ErrorCode.PARAMS_INVALID


def test_diem_lan_truoc_la_diem_cua_ngay_mo_phong_truoc():
    w = world()
    p = pipe(w)
    eng = ResilienceEngine(p)
    yesterday = {
        "app_date": APP_DATE - timedelta(days=1),
        "score": 61,
        "computed_at": NOW - timedelta(days=1),
    }
    w.scores.append(yesterday)
    d = eng.get(USER)["data"]
    assert d["previous_score"] == 61


def test_N2_compute_and_store_ghi_nguon_nightly_va_tra_du_lieu_dung_hop_dong():
    w = world()
    p = pipe(w)
    data = compute_and_store(p, USER, NOW)
    assert isinstance(data, ResilienceScoreData)
    assert w.scores[0]["source"] == "nightly" and w.scores[0]["app_date"] == APP_DATE
    assert w.scores[0]["weakest"] == data.weakest and w.scores[0]["band"] == data.band
    # cùng đầu vào, tính hai lần cho cùng điểm (tất định)
    again = compute_and_store(p, USER, NOW)
    assert (
        again.score == data.score and w.score_saves == 2 and len(w.scores) == 1
    )  # ghi đè, một dòng mỗi ngày
    with pytest.raises(ValueError):
        ResilienceEngine(p).compute_and_store(USER, NOW, source="la")


def test_chua_co_muc_tieu_thi_plan_bo_va_trong_so_cong_bang_mot():
    d = ResilienceEngine(pipe(world(goal=False))).get(USER)["data"]
    plan = next(c for c in d["components"] if c["key"] == "plan")
    assert plan["applicable"] is False and "score" not in plan and plan["weight"] == 0
    assert sum(c["weight"] for c in d["components"]) == pytest.approx(1.0, abs=0.005)


def test_khoi_rest_khop_schema_va_cung_so_voi_tool():
    w = world()
    eng = ResilienceEngine(pipe(w))
    res = eng.get(USER)
    block = build_resilience_score(
        data=res["data"],
        trace_id="a" * 32,
        source_tool="rest:GET /resilience",
        as_of=datetime.fromisoformat(res["as_of"].replace("Z", "+00:00")),
        app_date=date.fromisoformat(res["app_date"]),
    )
    wire = block_to_wire(block)
    assert not errors_of(REST_BLOCK, wire), errors_of(REST_BLOCK, wire)
    assert wire["data"] == res["data"]


def http_event(
    method: str, path: str, *, sub: str | None = USER, body: dict | None = None
) -> dict[str, Any]:
    claims = {"sub": sub} if sub else {}
    ev: dict[str, Any] = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method, "path": path},
            "authorizer": {"jwt": {"claims": claims}},
        },
        "headers": {},
    }
    if body is not None:
        ev["body"] = json.dumps(body)
    return ev


class _Afford:  # `POST /affordability` không dùng ở đây
    def check(self, *a, **k):  # pragma: no cover
        raise AssertionError


def test_rest_get_resilience_va_shocks_qua_handle_http():
    w = world()
    eng = ResilienceEngine(pipe(w))
    out = tool_mod.handle_http(http_event("GET", "/resilience"), _Afford(), eng, None)  # type: ignore[arg-type]
    assert out["statusCode"] == 200
    body = json.loads(out["body"])
    assert body["type"] == "resilience_score" and not errors_of(REST_BLOCK, body)
    assert body["source"]["tool"] == "rest:GET /resilience"
    shocks = tool_mod.handle_http(http_event("GET", "/resilience/shocks"), _Afford(), eng, None)  # type: ignore[arg-type]
    fixture = json.loads(
        (
            __import__("pathlib").Path(__file__).resolve().parents[3]
            / "contracts/fixtures/rest/ShocksResponse.default.json"
        ).read_text(encoding="utf-8")
    )
    assert json.loads(shocks["body"]) == fixture  # nhãn và mô tả đọc từ shocks.json, không gắn cứng
    # không có JWT thì 401
    nojwt = tool_mod.handle_http(http_event("GET", "/resilience", sub=None), _Afford(), eng, None)  # type: ignore[arg-type]
    assert nojwt["statusCode"] == 401
    # hồ sơ chưa khai lương: 422 PROFILE_INCOMPLETE
    bad = ResilienceEngine(pipe(world(salary=None)))
    out = tool_mod.handle_http(http_event("GET", "/resilience"), _Afford(), bad, None)  # type: ignore[arg-type]
    assert (
        out["statusCode"] == 422
        and json.loads(out["body"])["error"]["code"] == "PROFILE_INCOMPLETE"
    )


def test_gateway_tool_get_resilience_score():
    from types import SimpleNamespace

    w = world()
    p = pipe(w)
    eng = ResilienceEngine(p)
    ctx = SimpleNamespace(
        client_context=SimpleNamespace(
            custom={"bedrockAgentCoreToolName": "forecast___get_resilience_score"}
        )
    )
    out = tool_mod.handle_gateway({"user_id": USER}, ctx, None, p, None, None, eng, None)  # type: ignore[arg-type]
    assert out["status"] == "OK" and not errors_of(TOOL_RESULT, out)
    again = tool_mod.handle_gateway(
        {"user_id": USER, "refresh": True}, ctx, None, p, None, None, eng, None
    )  # type: ignore[arg-type]
    assert again["data"]["score"] == out["data"]["score"]
    missing = tool_mod.handle_gateway({}, ctx, None, p, None, None, eng, None)  # type: ignore[arg-type]
    assert missing["status"] == "ERROR" and missing["code"] == "UNAUTHENTICATED"
    w2 = world(salary=None)
    err = tool_mod.handle_gateway(
        {"user_id": USER}, ctx, None, pipe(w2), None, None, ResilienceEngine(pipe(w2)), None
    )  # type: ignore[arg-type]
    assert (
        err["status"] == "ERROR"
        and err["code"] == "PROFILE_INCOMPLETE"
        and not errors_of(TOOL_RESULT, err)
    )
