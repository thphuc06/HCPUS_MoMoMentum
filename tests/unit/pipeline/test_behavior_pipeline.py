"""Hồ sơ hành vi phía Lambda forecast (phase 5 luồng B): batch đêm tính, model nhỏ viết câu qua kiểm căn cứ, ghi `behavior_profiles`;
tool `forecast___get_behavior_profile` và `GET /profile/behavior` chỉ đọc; cổng bản tin cuối batch."""

from __future__ import annotations

import contextlib
import copy
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from conftest import BASE, build_registry
from jsonschema import Draft202012Validator
from pipeline_helpers import make_settings

from personas.generator import generate, materialize
from yofina_core.blocks import BehaviorProfileData
from yofina_core.config import Config
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.llm import BudgetCapReached, LlmGateway, LlmSettings, ModelSpec
from yofina_forecast import batch
from yofina_forecast import behavior as beh
from yofina_forecast.inputs import Context
from yofina_forecast.tool import handle_gateway, handle_http

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
ANCHOR = date(2026, 11, 21)
NOW = datetime(2026, 12, 10, 3, 0, tzinfo=UTC)  # app_today(-19, NOW) = 21/11/2026
OFFSET = -19
REGISTRY = build_registry()


def result_validator() -> Draft202012Validator:
    return Draft202012Validator(
        {"$ref": f"{BASE}/tools/forecast.results.schema.json#/$defs/GetBehaviorProfileResult"}, registry=REGISTRY
    )


# --- dữ liệu persona minh dưới dạng hàng DB -----------------------------------------------------------------
def minh_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = generate("minh", anchor=ANCHOR)
    m = materialize(data, anchor=ANCHOR, now=NOW, tz=TZ)
    spend = [
        {
            "app_date": r["app_date"],
            "occurred_at": r["occurred_at"],
            "jar_code": r["jar_code"],
            "amount_vnd": r["amount"],
            "funding_source": r["funding_source"],
            "is_obligation": r["obligation_id"] is not None,
        }
        for r in m.transaction_rows
        if r["kind"] == "expense" and r["app_date"] < ANCHOR
    ]
    jars = [
        {"code": j["code"], "name": j["name"], "kind": j["kind"], "balance_vnd": 500_000, "clock_offset_days": OFFSET}
        for j in m.jars
    ] + [{"code": "chua_phan_loai", "name": "Chưa phân loại", "kind": "system", "balance_vnd": 0}]
    return spend, jars


SPEND, JARS = minh_rows()


@dataclass
class FakeRepo:
    """Thay `BehaviorRepo` (cùng tên phương thức)."""

    spend: list[dict[str, Any]] = field(default_factory=lambda: copy.deepcopy(SPEND))
    user_row: dict[str, Any] | None = field(
        default_factory=lambda: {"clock_offset_days": OFFSET, "monthly_salary_vnd": 9_000_000, "payday_day": 5}
    )
    saved: list[tuple[dict[str, Any], str, str | None]] = field(default_factory=list)
    row: dict[str, Any] | None = None
    roadmap: dict[str, Any] | None = None
    ask: dict[str, Any] | None = None
    stats: list[dict[str, Any]] = field(default_factory=list)
    today: dict[str, Any] | None = None
    inserted: list[dict[str, Any]] = field(default_factory=list)

    def user(self, user_id):
        return self.user_row

    def spend_rows(self, user_id, since, today):
        return [r for r in self.spend if since <= r["app_date"] < today]

    def save_profile(self, user_id, data, *, source, model):
        self.saved.append((data, source, model))
        self.row = {
            "id": "x",
            "app_date": date.fromisoformat(data["app_date"]),
            "ready": data["ready"],
            "config_version": data["config_version"],
            "history_days": data["history_days"],
            "headline": data["headline"],
            "features": data.get("features") or {},
            "segment": data.get("segment"),
            "insights": data.get("insights") or [],
            "next_step": data.get("next_step"),
            "source": source,
            "model": model,
            "computed_at": datetime.fromisoformat(data["computed_at"].replace("Z", "+00:00")),
        }

    def profile(self, user_id, app_date):
        return self.row if self.row and self.row["app_date"] <= app_date else None

    def proposed_roadmap(self, user_id):
        return self.roadmap

    def review_ask(self, user_id, day):
        return self.ask

    def nudge_stats(self, user_id, since):
        return self.stats

    def today_nudge(self, user_id, day):
        return self.today

    def insert_nudge(self, user_id, **kw):
        self.inserted.append(kw)
        return True


@dataclass
class FakeForecastRepo:
    summaries_rows: list[dict[str, Any]] = field(default_factory=list)
    obligations_rows: list[dict[str, Any]] = field(default_factory=list)
    scores: dict[date, dict[str, Any]] = field(default_factory=dict)
    db: Any = None

    def jar_state(self, user_id):
        return copy.deepcopy(JARS)

    def summaries(self, user_id, jar=None):
        return self.summaries_rows

    def obligations(self, user_id, status="active"):
        return self.obligations_rows

    def resilience(self, user_id, app_date=None):
        keys = sorted(d for d in self.scores if app_date is None or d <= app_date)
        return self.scores[keys[-1]] if keys else None


class FakePipeline:
    def __init__(self, frepo: FakeForecastRepo | None = None) -> None:
        self.settings = make_settings()
        self.repo = frepo or FakeForecastRepo()

    def now(self):
        return NOW

    def load_context(self, user_id, now):
        return Context(
            meta={"app_date": ANCHOR.isoformat(), "profile": {"monthly_salary_vnd": 9_000_000, "payday_day": 5}},
            jars=({"code": "an_uong", "kind": "spending", "spend": [120_000] * 30},),
            obligations=(),
        )


# --- model giả ---------------------------------------------------------------------------------------------
class FakeBedrock:
    def __init__(self, script: list[Any]) -> None:
        self.script, self.calls = list(script), []

    def converse(self, **kw):
        self.calls.append(kw)
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class FakeUsage:
    def __init__(self, cap_hit: bool = False) -> None:
        self.cap_hit, self.calls = cap_hit, 0

    def consume(self, *, day, model, cap, ttl_epoch):
        self.calls += 1
        if self.cap_hit:
            raise BudgetCapReached(model)
        return self.calls


def summary_response(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"toolUse": {"toolUseId": "t1", "name": "behavior_summary", "input": payload}}],
            }
        },
        "usage": {"inputTokens": 300, "outputTokens": 120},
        "stopReason": "tool_use",
    }


def make_llm(script: list[Any], *, cap_hit: bool = False) -> tuple[LlmGateway, FakeBedrock]:
    client = FakeBedrock(script)
    gw = LlmGateway(
        LlmSettings(roles={"small": (ModelSpec("m-small", rpm=0, daily_cap=100),)}),
        config=Config({"YOFINA_REGION": "ap-southeast-1"}),
        client=client,
        usage=FakeUsage(cap_hit),
    )
    return gw, client


def engine(repo: FakeRepo, llm: LlmGateway | None = None, pipeline: FakePipeline | None = None) -> beh.BehaviorEngine:
    return beh.BehaviorEngine(pipeline or FakePipeline(), repo, llm=(lambda: llm) if llm else None)


def template_profile() -> dict[str, Any]:
    repo = FakeRepo()
    data, model, _ = engine(repo).compute("u", NOW, use_model=False)
    assert model is None
    return data


TEMPLATE = template_profile()


def rewrite(**over: str | None) -> dict[str, Any]:
    """Câu của model: chép lại câu mẫu (có căn cứ), thay câu của các nhận xét trong `over`."""
    items = []
    for i in TEMPLATE["insights"]:
        headline = over.get(i["insight_id"], f"Nhận xét: {i['headline']}")
        items.append({"insight_id": i["insight_id"], "headline": headline, "detail": i.get("detail")})
    return {"headline": f"Tóm lại: {TEMPLATE['insights'][0]['headline']}", "insights": items}


# =====================================================================================================
# Tính và lưu
# =====================================================================================================
def test_dat_lai_dung_cau_mau_khong_goi_model_va_ghi_ho_so():
    repo = FakeRepo()
    llm, client = make_llm([])
    data = engine(repo, llm).compute_and_store("u", NOW, trigger="reset")
    assert not client.calls
    (saved, source, model), = repo.saved
    assert source == "reset" and model is None and saved == data
    assert data["ready"] and len(data["insights"]) >= 2 and data["app_date"] == ANCHOR.isoformat()
    assert all(not i["ai_generated"] for i in data["insights"])
    BehaviorProfileData.model_validate(data)


def test_batch_dem_goi_model_nho_va_giu_cau_co_can_cu():
    repo = FakeRepo()
    llm, client = make_llm([summary_response(rewrite())])
    data = engine(repo, llm).compute_and_store("u", NOW, trigger="nightly")
    (call,) = client.calls
    assert call["modelId"] == "m-small" and call["toolConfig"]["toolChoice"] == {"tool": {"name": "behavior_summary"}}
    prompt = call["messages"][0]["content"][0]["text"]
    # model chỉ thấy câu mẫu và chuỗi hiển thị của bằng chứng: không có tên đối tác, lời nhắn
    assert "<du_lieu>" in prompt and "967.000 ₫" in prompt
    assert "Lazada" not in prompt and "Highlands" not in prompt and "Cơm tấm" not in prompt
    assert all(i["ai_generated"] for i in data["insights"])
    assert data["headline"].startswith("Tóm lại:")
    assert repo.saved[0][1:] == ("nightly", "m-small")


def test_cau_cua_model_co_so_khong_can_cu_thi_bo_nhan_xet_do():
    repo = FakeRepo()
    top = TEMPLATE["insights"][0]["insight_id"]
    llm, _ = make_llm([summary_response(rewrite(**{top: "Bạn dùng Trả sau khoảng 1 triệu mỗi tháng."}))])
    data = engine(repo, llm).compute_and_store("u", NOW, trigger="nightly")
    ids = [i["insight_id"] for i in data["insights"]]
    assert top not in ids and len(ids) == len(TEMPLATE["insights"]) - 1
    # việc cần làm đi theo nhận xét quan trọng nhất CÒN LẠI
    assert data["next_step"] != TEMPLATE["next_step"]
    # câu mở đầu của model nhắc số của nhận xét đã bỏ nên không dùng: lấy câu của nhận xét đầu còn lại
    assert data["headline"] == data["insights"][0]["headline"]


def test_cau_cua_model_co_pii_thi_bo():
    repo = FakeRepo()
    second = TEMPLATE["insights"][1]["insight_id"]
    llm, _ = make_llm([summary_response(rewrite(**{second: "Bạn chuyển cho Nguyễn Văn An nhiều nhất vào cuối tuần."}))])
    data = engine(repo, llm).compute_and_store("u", NOW, trigger="nightly")
    assert second not in [i["insight_id"] for i in data["insights"]]


def test_moi_cau_cua_model_deu_hong_thi_dung_cau_mau():
    repo = FakeRepo()
    bad = {i["insight_id"]: "Bạn chi 99% vào ngày 01/01." for i in TEMPLATE["insights"]}
    llm, _ = make_llm([summary_response(rewrite(**bad))])
    data = engine(repo, llm).compute_and_store("u", NOW, trigger="nightly")
    assert data == {**TEMPLATE, "computed_at": data["computed_at"]}
    assert repo.saved[0][2] is None  # không ghi tên model khi không dùng câu nào của model


@pytest.mark.parametrize("failure", ["budget", "throttle", "schema"])
def test_model_loi_thi_dung_cau_mau_khong_lam_hong_batch(failure):
    repo = FakeRepo()
    if failure == "budget":
        llm, _ = make_llm([], cap_hit=True)
    elif failure == "throttle":
        exc = Exception("throttled")
        exc.response = {"Error": {"Code": "ThrottlingException"}}  # type: ignore[attr-defined]
        llm, _ = make_llm([exc])
    else:
        llm, _ = make_llm([summary_response({"headline": ""})] * 2)
    data = engine(repo, llm).compute_and_store("u", NOW, trigger="manual")
    assert data["ready"] and all(not i["ai_generated"] for i in data["insights"])
    assert repo.saved[0][1:] == ("manual", None)


def test_chua_khai_luong_la_profile_incomplete():
    repo = FakeRepo(user_row={"clock_offset_days": OFFSET, "monthly_salary_vnd": None, "payday_day": None})
    with pytest.raises(YofinaError) as e:
        engine(repo).compute_and_store("u", NOW, trigger="reset")
    assert e.value.code == ErrorCode.PROFILE_INCOMPLETE


def test_cua_so_va_sql_chi_doc_cot_can_thiet():
    sql = beh.SQL_SPEND.lower()
    assert "user_id = :uid" in sql and "kind = 'expense'" in sql and "limit" in sql
    for col in ("merchant", "note", "payee_id"):
        assert col not in sql
    assert "on conflict (user_id, app_date) do update" in beh.SQL_UPSERT_PROFILE.lower()


class _Tx:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=None):
        self.log.append((sql, params))
        return []


class _Db:
    def __init__(self):
        self.log: list[tuple[str, Any]] = []
        self.users: list[str] = []

    @contextlib.contextmanager
    def transaction(self, user_id):
        self.users.append(user_id)
        yield _Tx(self.log)

    def query(self, sql, params=None, *, max_rows=None):
        self.log.append((sql, params))
        return []


def test_repo_ghi_ho_so_trong_transaction_cua_dung_nguoi_dung():
    db = _Db()
    data = {**TEMPLATE, "computed_at": "2026-12-10T03:00:00Z"}
    beh.BehaviorRepo(db).save_profile("u-1", data, source="nightly", model="m-small")
    (_sql, params), = db.log
    assert db.users == ["u-1"] and params["uid"] == "u-1"
    assert params["app_date"] == ANCHOR and params["computed_at"] == NOW
    assert json.loads(params["insights"]) == data["insights"] and json.loads(params["next_step"]) == data["next_step"]


# =====================================================================================================
# Đọc: tool và REST
# =====================================================================================================
def ctx(name: str):
    return SimpleNamespace(client_context=SimpleNamespace(custom={"bedrockAgentCoreToolName": f"forecast___{name}"}))


def stored_repo() -> FakeRepo:
    repo = FakeRepo()
    engine(repo).compute_and_store("u", NOW, trigger="reset")
    return repo


def test_tool_tra_ho_so_da_luu_dung_hop_dong():
    repo = stored_repo()
    pipe = FakePipeline()
    out = handle_gateway({"user_id": "u"}, ctx("get_behavior_profile"), None, pipe, behavior=engine(repo, pipeline=pipe))  # type: ignore[arg-type]
    result_validator().validate(out)
    assert out["status"] == "OK" and out["app_date"] == ANCHOR.isoformat()
    assert out["data"]["insights"] == repo.saved[0][0]["insights"]


def test_tool_loc_theo_loai_va_hu():
    repo = stored_repo()
    e = engine(repo)
    only = e.get("u", insight_kind="bnpl_usage")["data"]
    assert [i["kind"] for i in only["insights"]] == ["bnpl_usage"] and only["ready"]
    jar = only["insights"][0]["jar_code"]
    assert all(i.get("jar_code") == jar for i in e.get("u", jar=jar)["data"]["insights"])
    none = e.get("u", insight_kind="time_of_day")
    result_validator().validate(none)
    assert not none["data"]["ready"] and none["data"]["insights"] == [] and none["data"]["min_history_days"] >= 1
    with pytest.raises(YofinaError) as err:
        e.get("u", insight_kind="khong_co")
    assert err.value.code == ErrorCode.PARAMS_INVALID


def test_chua_co_ho_so_la_ok_ready_sai():
    out = engine(FakeRepo()).get("u")
    result_validator().validate(out)
    assert out["data"]["ready"] is False and out["data"]["insights"] == []


def test_tool_loi_nghiep_vu_tra_phong_bi_loi():
    repo = FakeRepo(user_row=None)
    pipe = FakePipeline()
    out = handle_gateway({"user_id": "u"}, ctx("get_behavior_profile"), None, pipe, behavior=engine(repo, pipeline=pipe))  # type: ignore[arg-type]
    assert out == {"status": "ERROR", "code": "PROFILE_INCOMPLETE", "message": "Người dùng chưa có hồ sơ."}


def http_event(route: str, sub: str = "u") -> dict[str, Any]:
    method, path = route.split(" ", 1)
    return {
        "rawPath": path,
        "requestContext": {"http": {"method": method, "path": path}, "authorizer": {"jwt": {"claims": {"sub": sub}}}},
        "headers": {},
    }


def test_rest_profile_behavior_cung_data_voi_tool():
    repo = stored_repo()
    e = engine(repo)
    res = handle_http(http_event("GET /profile/behavior"), SimpleNamespace(pipeline=e.pipeline), behavior=e)  # type: ignore[arg-type]
    assert res["statusCode"] == 200
    body = json.loads(res["body"])
    Draft202012Validator(
        {"$ref": f"{BASE}/rest/openapi.yaml#/components/schemas/BehaviorProfileResponse"}, registry=REGISTRY
    ).validate(body)
    assert body == e.get("u")["data"]


# =====================================================================================================
# Batch đêm: bước behavior rồi nudge_gate, mỗi bước bọc lỗi riêng
# =====================================================================================================
def test_after_forecast_them_buoc_ho_so_va_cong_ban_tin(monkeypatch):
    calls: list[str] = []
    from yofina_forecast import change, resilience

    monkeypatch.setattr(resilience, "compute_and_store", lambda p, u, n, source: SimpleNamespace(score=40))
    monkeypatch.setattr(change, "detect_and_store", lambda p, u, n: SimpleNamespace(to_dict=lambda: {}))

    def fake_profile(p, u, n, *, trigger):
        calls.append(f"behavior:{trigger}")
        return {"ready": True, "insights": [{"x": 1}]}

    def fake_gate(p, u, n, *, profile):
        calls.append(f"gate:{profile['ready']}")
        return {"status": "ok", "chosen": "behavior_insight"}

    monkeypatch.setattr(beh, "compute_and_store", fake_profile)
    monkeypatch.setattr(beh, "run_nudge_gate", fake_gate)
    steps = batch.after_forecast(SimpleNamespace(now=lambda: NOW), "u", "nightly")  # type: ignore[arg-type]
    assert calls == ["behavior:nightly", "gate:True"]
    assert steps["behavior"] == {"status": "ok", "ready": True, "insights": 1}
    assert steps["nudge_gate"]["chosen"] == "behavior_insight"


def test_buoc_ho_so_hong_cong_van_chay(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")

    seen: dict[str, Any] = {}
    monkeypatch.setattr(beh, "compute_and_store", boom)
    monkeypatch.setattr(beh, "run_nudge_gate", lambda p, u, n, *, profile: seen.setdefault("profile", profile) or {"status": "ok"})
    steps = batch.phase5_steps(SimpleNamespace(), "u", "reset", NOW, beh)  # type: ignore[arg-type]
    assert steps["behavior"] == {"status": "failed", "error": "RuntimeError"}
    assert "profile" in seen and seen["profile"] is None and steps["nudge_gate"] == {"status": "ok"}


# =====================================================================================================
# Cổng bản tin trên dữ liệu đã đọc
# =====================================================================================================
def gate_pipeline(**kw: Any) -> FakePipeline:
    return FakePipeline(FakeForecastRepo(**kw))


def test_cong_chon_hu_thiet_yeu_sap_can_va_ghi_mot_ban_tin():
    pipe = gate_pipeline(
        summaries_rows=[
            {"jar_code": "an_uong", "status": "short", "runout_date": date(2026, 11, 28), "payday_date": date(2026, 12, 5)},
            {"jar_code": "giai_tri", "status": "short", "runout_date": date(2026, 11, 22), "payday_date": date(2026, 12, 5)},
        ],
    )
    repo = FakeRepo(ask={"status": "open", "item_count": 3, "pending_total_vnd": 180_000})
    out = beh.run_nudge_gate(pipe, "u", NOW, repo=repo, profile=TEMPLATE)
    assert out["chosen"] == "runout_warning" and out["written"]
    (kw,) = repo.inserted
    c = kw["decision"].chosen
    # giai_tri không thiết yếu nên không vào; phần hụt ước tính = chi trung bình mỗi ngày x số ngày từ lúc cạn tới lương
    assert c.jar_code == "an_uong" and c.value_vnd == 120_000 * 7 and kw["app_date"] == ANCHOR
    assert {s["kind"]: s["reason"] for s in out["suppressed"]} == {
        "review_needed": "lower_rank",
        "behavior_insight": "lower_rank",
    }


@pytest.mark.parametrize(("daily_essential", "chosen"), [(0, "an_uong"), (40_000, "chi_hang_ngay")])
def test_cong_tren_vi_co_ca_chi_hang_ngay_va_hu_rieng(monkeypatch, daily_essential, chosen):
    """Ví demo từ 26/11 (issue #39): Chi hằng ngày cạnh Ăn uống. Hũ chung chỉ là hũ thiết yếu của cổng khi chính nó có chi loại thiết
    yếu (`essential_spend`); chi lặt vặt thì không, nên hũ này cạn cũng không chen lên trước cảnh báo Ăn uống (cảnh 1). Chi của Ăn uống
    không bị đếm lại ở Chi hằng ngày: phần hụt ước tính của mỗi hũ theo chuỗi của chính nó."""
    daily_row = {"code": "chi_hang_ngay", "name": "Chi hằng ngày", "kind": "spending", "balance_vnd": 60_000,
                 "clock_offset_days": OFFSET}  # fmt: skip
    monkeypatch.setattr(FakeForecastRepo, "jar_state", lambda self, user_id: [*copy.deepcopy(JARS), daily_row])
    pipe = gate_pipeline(
        summaries_rows=[
            {"jar_code": "an_uong", "status": "short", "runout_date": date(2026, 11, 28), "payday_date": date(2026, 12, 5)},
            {"jar_code": "chi_hang_ngay", "status": "short", "runout_date": date(2026, 11, 22),
             "payday_date": date(2026, 12, 5)},
        ],
    )  # fmt: skip
    ctx = Context(
        meta={"app_date": ANCHOR.isoformat(), "profile": {"monthly_salary_vnd": 9_000_000, "payday_day": 5}},
        jars=(
            {"code": "an_uong", "kind": "spending", "spend": [120_000] * 30},
            {"code": "chi_hang_ngay", "kind": "spending", "spend": [70_000] * 30, "essential_spend": [daily_essential] * 30},
        ),
        obligations=(),
    )
    monkeypatch.setattr(pipe, "load_context", lambda user_id, now: ctx)
    repo = FakeRepo()
    out = beh.run_nudge_gate(pipe, "u", NOW, repo=repo, profile=TEMPLATE)
    c = repo.inserted[0]["decision"].chosen
    assert out["chosen"] == "runout_warning" and c.jar_code == chosen
    assert c.value_vnd == (120_000 * 7 if chosen == "an_uong" else daily_essential * 13)


def test_cong_da_co_ban_tin_hom_nay_thi_khong_chon_lai():
    repo = FakeRepo(today={"id": "n1"})
    out = beh.run_nudge_gate(gate_pipeline(), "u", NOW, repo=repo, profile=TEMPLATE)
    assert out == {"status": "ok", "chosen": None, "reason": "already_chosen"} and not repo.inserted


def test_cong_ha_bac_loai_bi_it_nhac_va_diem_tut_nhom():
    pipe = gate_pipeline(
        scores={
            ANCHOR - timedelta(days=1): {"app_date": ANCHOR - timedelta(days=1), "band": "fair", "score": 45},
            ANCHOR: {"app_date": ANCHOR, "band": "weak", "score": 30},
        }
    )
    repo = FakeRepo(
        ask={"status": "open", "item_count": 2, "pending_total_vnd": 90_000},
        stats=[{"kind": "review_needed", "shown": 3, "less_like_this": 1}],
    )
    out = beh.run_nudge_gate(pipe, "u", NOW, repo=repo, profile=TEMPLATE)
    # review_needed (hạng 4) bị hạ xuống sau resilience_drop (hạng 5)
    assert out["chosen"] == "resilience_drop"
    assert {"kind": "review_needed", "reason": "demoted"} in out["suppressed"]


def test_cong_khong_lay_diem_cu_lam_diem_hom_nay():
    pipe = gate_pipeline(
        scores={ANCHOR - timedelta(days=2): {"app_date": ANCHOR - timedelta(days=2), "band": "strong", "score": 80},
                ANCHOR - timedelta(days=1): {"app_date": ANCHOR - timedelta(days=1), "band": "weak", "score": 20}}
    )  # fmt: skip
    out = beh.run_nudge_gate(pipe, "u", NOW, repo=FakeRepo(stats=[{"kind": "behavior_insight", "shown": 1}]), profile=TEMPLATE)
    assert out["chosen"] is None and out["candidates"] == 1  # chỉ còn nhận xét hành vi, đã nhắc trong 7 ngày nên dưới ngưỡng
