"""Lộ trình phía ledger (phase 4, gói 2), phần KHÔNG cần DB: logic thuần (`roadmap_logic`), proxy `optimize_allocation` của
`ForecastClient`, sự kiện, phân tuyến và kiểm đầu vào của tám REST `/roadmap*`, ba tool Gateway, và `RoadmapOps` trên kho dữ liệu giả
trong bộ nhớ (đồ giả CHỈ ở test). SQL thật, RLS thật và seed persona được kiểm ở `tests/local_pg/test_roadmap_flow.py`."""

from __future__ import annotations

import copy
import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from conftest import CONTRACTS, build_registry, load_json
from jsonschema import Draft202012Validator
from ledger_fakes import SETTINGS, gateway_context, http_event, make_service

from yofina_core.clock import app_today
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.roadmap import status_for_new_version
from yofina_ledger import events
from yofina_ledger import roadmap_logic as rl
from yofina_ledger.forecast_client import ForecastClient
from yofina_ledger.gateway_api import _ARG_KEYS, ROADMAP_TOOLS, handle_gateway
from yofina_ledger.repo import JarView
from yofina_ledger.rest_api import handle_http
from yofina_ledger.roadmap_rest import dispatch, match_route
from yofina_ledger.roadmap_service import RoadmapOps, roadmap_ops
from yofina_planner.facts import facts_from_rows
from yofina_planner.rules import cached_rules

U = "sub-minh"
V = "sub-lan"
TODAY = date(2026, 11, 21)
NOW = datetime(2026, 12, 10, 3, 0, tzinfo=UTC)
FIXTURES = CONTRACTS / "fixtures"


def make_row(version: int, status: str, **over: Any) -> dict[str, Any]:
    """Dòng `app_get_roadmap` dựng từ fixture hợp đồng `tools/get_roadmap.ok.json` (phiên bản 2 đang dùng)."""
    data = load_json(FIXTURES / "tools" / "get_roadmap.ok.json")["data"]
    phases = copy.deepcopy(data["phases"])
    states: dict[str, Any] = {}
    for ph in phases:
        for st in ph["steps"]:
            if st["status"] != "pending":
                states[st["step_id"]] = {
                    "status": st["status"],
                    "decided_at": st["decided_at"],
                    **({"edited": True} if st.get("edited") else {}),
                }
            for k in ("status", "decided_at", "edited"):
                st.pop(k, None)
    plan = {
        "headline": "3 giai đoạn, 4 bước, kịp hạn.",
        "horizon": data["horizon"],
        "goals": data["goals"],
        "phases": phases,
        "alternatives": [],
        "basis": data["basis"],
    }
    row = {
        "id": str(uuid.uuid4()),
        "version": version,
        "status": status,
        "reason_code": "user_request",
        "reason_text": "Bạn yêu cầu lập lại lộ trình.",
        "reason_detail": None,
        "behavior_flag_id": None,
        "based_on_version": version - 1 if version > 1 else None,
        "feasibility": "on_track",
        "app_date": TODAY,
        "plan": plan,
        "step_states": states,
        "rules_version": "v1.1.1.1.1",
        "trace_id": "abc",
        "created_at": NOW,
        "updated_at": NOW,
    }
    row.update(over)
    return row


# =====================================================================================================
# Lỗi từ DB
# =====================================================================================================
def test_db_business_error_doc_ma_tu_thong_diep_va_nguyen_nhan():
    class Pg(Exception):
        pass

    inner = Pg(
        "ROADMAP_VERSION_CONFLICT: bản gốc đã bị thay\nCONTEXT: PL/pgSQL function app_save_roadmap"
    )
    wrapped = YofinaError(ErrorCode.INTERNAL_ERROR, "Lỗi hệ thống khi truy cập dữ liệu.")
    wrapped.__cause__ = inner
    err = rl.db_business_error(wrapped)
    assert err is not None and err.code == ErrorCode.ROADMAP_VERSION_CONFLICT
    assert err.message == "bản gốc đã bị thay"  # chỉ dòng đầu, không CONTEXT
    boto = Pg(
        "An error occurred (BadRequestException) when calling the ExecuteStatement operation: ERROR: ROADMAP_NOT_FOUND: không có phiên bản này"
    )
    assert rl.db_business_error(boto).code == ErrorCode.ROADMAP_NOT_FOUND  # type: ignore[union-attr]
    assert rl.db_business_error(Pg("PROFILE_INCOMPLETE: x")).code == ErrorCode.PROFILE_INCOMPLETE  # type: ignore[union-attr]
    assert rl.db_business_error(Pg("duplicate key value")) is None
    assert rl.db_business_error(wrapped.__class__(ErrorCode.INTERNAL_ERROR, "x")) is None


def test_db_business_error_thong_diep_hong_dau_thi_dung_cau_chuan_cua_ma():
    """Data API trả chữ có dấu trong thông điệp RAISE bị hỏng từng byte (U+FFFD): đã thấy trên Aurora thật (`ROADMAP_VERSION_CONFLICT`)."""

    class Pg(Exception):
        pass

    broken = "ROADMAP_VERSION_CONFLICT: b���n n��y kh��ng c��n; SQLState: P0001"
    err = rl.db_business_error(Pg(broken))
    assert err is not None and err.code == ErrorCode.ROADMAP_VERSION_CONFLICT
    assert "�" not in err.message and err.message == rl.DB_ERROR_FALLBACK["ROADMAP_VERSION_CONFLICT"]
    assert set(rl.DB_ERROR_FALLBACK) == {
        "ROADMAP_NOT_FOUND",
        "ROADMAP_INVALID",
        "ROADMAP_VERSION_CONFLICT",
        "PROFILE_INCOMPLETE",
    }


# =====================================================================================================
# Bản nháp, lý do, tiêu đề
# =====================================================================================================
def ok_args(**over: Any) -> dict[str, Any]:
    data = load_json(FIXTURES / "tools" / "get_roadmap.ok.json")["data"]
    steps = [
        {
            k: v
            for k, v in st.items()
            if k not in ("status", "decided_at", "edited", "checked_rules")
        }
        for st in data["phases"][0]["steps"]
    ]
    args: dict[str, Any] = {
        "reason_code": "user_request",
        "based_on_version": 2,
        "feasibility": "on_track",
        "goals": data["goals"],
        "alternatives": [],
        "phases": [
            {**{k: v for k, v in data["phases"][0].items() if k != "steps"}, "steps": steps}
        ],
    }
    args.update(over)
    return args


def test_parse_draft_phan_biet_params_invalid_va_roadmap_invalid():
    assert rl.parse_draft(ok_args()).reason_code == "user_request"
    for bad in (ok_args(phases=[]), ok_args(reason_code="bat_ky"), {"feasibility": "on_track"}):
        with pytest.raises(YofinaError) as e:
            rl.parse_draft(bad)
        assert e.value.code == ErrorCode.PARAMS_INVALID
    for bad in (
        ok_args(feasibility="infeasible"),  # infeasible cần đúng hai lựa chọn
        ok_args(reason_code="behavior_changed"),  # thiếu behavior_flag_id
        ok_args(reason_code="initial"),  # bản đầu tiên không có based_on_version
    ):
        with pytest.raises(YofinaError) as e:
            rl.parse_draft(bad)
        assert e.value.code == ErrorCode.ROADMAP_INVALID, bad
        assert e.value.message.startswith("Lộ trình không hợp lệ:")
    # giá trị rỗng và None bị bỏ như tham số vắng (Gateway gửi trường trống)
    assert (
        rl.parse_draft(
            {**ok_args(), "behavior_flag_id": None, "based_on_version": ""}
        ).based_on_version
        is None
    )


FLAG = {
    "jar_code": "an_uong",
    "old_weekly_vnd": 520_000,
    "new_weekly_vnd": 810_000,
    "weeks_held": 2,
}


def test_reason_for_dung_cau_tu_su_kien():
    assert rl.reason_for("initial") == ("Lộ trình đầu tiên của bạn.", None)
    text, detail = rl.reason_for("behavior_changed", flag=FLAG, jar_name="Ăn uống")
    assert text == "Chi Ăn uống mỗi tuần tăng từ 520.000 ₫ lên 810.000 ₫ và giữ mức đó 2 tuần."
    assert detail == [
        {"label": "Chi Ăn uống mỗi tuần", "before": "520.000 ₫", "after": "810.000 ₫"}
    ]
    text, detail = rl.reason_for(
        "behavior_changed",
        flag={**FLAG, "new_weekly_vnd": 300_000, "weeks_held": None},
        jar_name="Ăn uống",
    )
    assert text == "Chi Ăn uống mỗi tuần giảm từ 520.000 ₫ xuống 300.000 ₫."
    with pytest.raises(YofinaError):
        rl.reason_for("behavior_changed")
    text, detail = rl.reason_for(
        "step_edited",
        step_title="Bù 120.000 ₫ mỗi tuần cho Ăn uống",
        changes=[{"label": "Số tiền", "before": "100.000 ₫", "after": "120.000 ₫"}],
    )
    assert (
        text
        == "Bạn đã sửa bước 'Bù 120.000 ₫ mỗi tuần cho Ăn uống' (số tiền 120.000 ₫) và lưu thành phiên bản mới."
    )
    assert detail == [{"label": "Số tiền", "before": "100.000 ₫", "after": "120.000 ₫"}]
    for code in ("goal_changed", "income_changed", "forecast_drift", "user_request"):
        assert rl.reason_for(code)[0].endswith(".")
    with pytest.raises(YofinaError):
        rl.reason_for("khong_co")
    long = rl.reason_for("step_edited", step_title="x" * 500, changes=[])[0]
    assert len(long) <= 160


def test_tieu_de_theo_kha_thi_va_ghep_so_phien_ban():
    phases = [{"steps": [1, 2]}, {"steps": [3]}]
    on = [{"jar": {"code": "du_lich", "name": "Du lịch"}, "on_track": True}]
    off = [{"jar": {"code": "du_lich", "name": "Du lịch"}, "on_track": False}]
    assert rl.plan_headline("on_track", phases, on) == "2 giai đoạn, 3 bước, kịp hạn."
    assert rl.plan_headline("on_track", phases, []) == "2 giai đoạn, 3 bước."
    assert (
        rl.plan_headline("relaxed", phases, on)
        == "2 giai đoạn, 3 bước, kịp hạn sau khi điều chỉnh các hũ."
    )
    assert (
        rl.plan_headline("infeasible", phases, off)
        == "mục tiêu Du lịch chưa khả thi, có 2 lựa chọn."
    )
    assert (
        rl.compose_headline(3, "2 giai đoạn, 3 bước, kịp hạn.")
        == "Lộ trình phiên bản 3: 2 giai đoạn, 3 bước, kịp hạn."
    )


# =====================================================================================================
# Luật suitability cho từng bước
# =====================================================================================================
def facts(*, hoa_don: int = 450_000, giai_tri: int = 760_000):
    jars = [
        {
            "code": "hoa_don",
            "name": "Hóa đơn",
            "kind": "obligation",
            "balance_vnd": Decimal(hoa_don),
        },
        {
            "code": "giai_tri",
            "name": "Giải trí",
            "kind": "spending",
            "balance_vnd": Decimal(giai_tri),
        },
        {"code": "an_uong", "name": "Ăn uống", "kind": "spending", "balance_vnd": Decimal(380_000)},
        {
            "code": "du_phong",
            "name": "Dự phòng",
            "kind": "saving",
            "balance_vnd": Decimal(2_700_000),
        },
    ]
    obligations = [
        {
            "kind": "bill", "name": "Tiền điện", "amount_vnd": Decimal(375_000), "due_date": date(2026, 11, 26),
            "cycle": "monthly", "due_day": 26, "pay_jar_code": "hoa_don", "is_essential": True, "status": "active",
        }
    ]  # fmt: skip
    user = {"monthly_salary_vnd": Decimal(9_000_000), "payday_day": 5, "risk_tolerance": "medium"}
    return facts_from_rows(
        today=TODAY, user=user, jars=jars, obligations=obligations, window_days=30
    )


def step(kind: str, **over: Any) -> dict[str, Any]:
    s = {"step_id": "buoc_thu", "kind": kind, "title": "t", "reason": "r"}
    s.update(over)
    return s


def test_proposal_for_step_chi_buoc_keo_tien_khoi_hu_moi_co_nguon_hu():
    move = step("set_aside", amount_vnd=100_000, jar_code="giai_tri", to_jar_code="an_uong")
    p = rl.proposal_for_step(move)
    assert (p.funding_source, p.jar_code, p.is_essential, p.category, p.origin, p.kind) == (
        "jar", "giai_tri", False, "saving", "recommendation", "roadmap_set_aside",
    )  # fmt: skip
    pay = rl.proposal_for_step(
        step("pay_obligation", amount_vnd=1, jar_code="giai_tri", to_jar_code="hoa_don")
    )
    assert (
        pay.is_essential is True and pay.category == "debt_payment" and pay.funding_source == "jar"
    )
    cut = rl.proposal_for_step(step("cut_spending", amount_vnd=50_000, jar_code="giai_tri"))
    assert cut.funding_source is None and cut.jar_code is None and cut.category == "spending"
    remind = rl.proposal_for_step(step("remind", jar_code="du_lich"))
    assert remind.amount_vnd is None and remind.funding_source is None and remind.category is None
    # đặt vào một hũ (không có hũ nguồn) thì không rút tiền khỏi hũ nào
    into = rl.proposal_for_step(step("set_aside", amount_vnd=100_000, jar_code="du_phong"))
    assert into.funding_source is None


def phases_of(*steps: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "phase_id": "p1",
            "title": "G",
            "start_date": "2026-11-21",
            "end_date": "2026-12-05",
            "steps": list(steps),
        }
    ]


def test_check_steps_obligations_first_chan_rut_tien_khoi_hu_gánh_nghia_vu():
    rules = cached_rules()
    safe = step("set_aside", amount_vnd=50_000, jar_code="hoa_don", to_jar_code="an_uong")
    bad = step(
        "set_aside",
        step_id="rut_nhieu",
        amount_vnd=200_000,
        jar_code="hoa_don",
        to_jar_code="an_uong",
    )
    v, checked = rl.check_steps(phases_of(safe), facts(), rules)
    assert v == [] and checked["buoc_thu"] == ["obligations_first"]
    v, checked = rl.check_steps(phases_of(safe, bad), facts(), rules)
    assert [(s, r) for s, r, _m in v] == [("rut_nhieu", "obligations_first")]
    err = rl.violation_error(v)
    assert err.code == ErrorCode.ROADMAP_INVALID
    assert (
        "rut_nhieu" in err.message
        and "obligations_first" in err.message
        and "Hãy bỏ hoặc đổi" in err.message
    )
    # chỉ kiểm riêng một bước
    v, checked = rl.check_steps(phases_of(safe, bad), facts(), rules, only_step="buoc_thu")
    assert v == [] and set(checked) == {"buoc_thu"}
    # bước trả nghĩa vụ (thiết yếu) và bước không rút tiền thì không bị luật này chặn
    pay = step(
        "pay_obligation",
        step_id="tra",
        amount_vnd=400_000,
        jar_code="hoa_don",
        to_jar_code="giai_tri",
    )
    v, checked = rl.check_steps(
        phases_of(pay, step("remind", step_id="nhac", jar_code="an_uong")), facts(), rules
    )
    assert v == [] and checked["tra"] == [] and checked["nhac"] == []
    two = rl.violation_error([("a", "obligations_first", "m."), ("b", "obligations_first", "m.")])
    assert "và 1 bước khác" in two.message


def test_validate_jar_refs_chan_hu_la_va_hanh_dong_lech_buoc():
    jars = {"giai_tri", "an_uong", "du_lich"}
    good = step(
        "set_aside", amount_vnd=100_000, jar_code="giai_tri", to_jar_code="an_uong",
        action={"tool": "move_between_jars", "params": {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100_000}},
    )  # fmt: skip
    goal = {"jar": {"code": "du_lich", "name": "Du lịch", "color_key": "teal", "icon_key": "plane"}}
    rl.validate_jar_refs(phases_of(good), [goal], [{"jar_code": "du_lich"}], jars)
    cases = [
        (step("set_aside", jar_code="khong_co"), [], []),
        (step("set_aside", to_jar_code="chua_phan_loai"), [], []),  # hũ hệ thống không nằm trong tập hũ người dùng
        (good, [{"jar": {"code": "la"}}], []),
        (good, [], [{"jar_code": "la"}]),
        (
            {**good, "action": {"tool": "move_between_jars", "params": {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 999}}},
            [], [],
        ),  # số tiền hành động khác số tiền bước
        (
            {**good, "action": {"tool": "move_between_jars", "params": {"from_jar": "du_lich", "to_jar": "an_uong"}}},
            [], [],
        ),  # hũ nguồn hành động khác hũ nguồn của bước
        (
            step("remind", action={"tool": "schedule_nudge", "params": {"op": "create", "jar_code": "la"}}),
            [], [],
        ),
    ]  # fmt: skip
    for st, goals, alts in cases:
        with pytest.raises(YofinaError) as e:
            rl.validate_jar_refs(phases_of(st), goals, alts, jars)
        assert e.value.code == ErrorCode.ROADMAP_INVALID


# =====================================================================================================
# Dựng plan, đọc lại, đếm
# =====================================================================================================
def test_build_plan_ghi_luat_da_kiem_thay_gia_tri_agent_tu_khai_va_horizon():
    d = rl.parse_draft(ok_args())
    phases = rl.draft_phases(d)
    phases[0]["steps"][0]["checked_rules"] = ["emergency_before_investing"]  # agent tự khai
    basis = {"computed_at": "2026-12-10T03:00:00Z", "stale": False, "confidence_band": "medium",
             "is_initial_estimate": False, "history_days": 47}  # fmt: skip
    first = phases[0]["steps"][0]["step_id"]
    plan = rl.build_plan(
        feasibility="on_track", goals=[], phases=phases, alternatives=[],
        checked={first: ["obligations_first"]}, basis=basis,
    )  # fmt: skip
    st = plan["phases"][0]["steps"][0]
    assert st["checked_rules"] == ["obligations_first"] and st["status"] == "pending"
    assert all("checked_rules" not in s for s in plan["phases"][0]["steps"][1:])
    assert plan["horizon"] == {
        "start_date": phases[0]["start_date"],
        "end_date": phases[0]["end_date"],
    }
    assert plan["headline"].endswith(".") and plan["basis"] == basis


def test_roadmap_data_phu_trang_thai_tung_buoc_va_dem():
    row = make_row(2, "active")
    data = rl.roadmap_data(row)
    assert data["version"] == 2 and data["headline"].startswith("Lộ trình phiên bản 2: ")
    assert data["counts"] == {"pending": 2, "accepted": 2, "rejected": 1}
    steps = {s["step_id"]: s for p in data["phases"] for s in p["steps"]}
    assert steps["bu_an_uong"]["edited"] is True and steps["bu_an_uong"]["decided_at"].endswith("Z")
    assert (
        steps["nhac_du_lich"]["status"] == "pending" and "decided_at" not in steps["nhac_du_lich"]
    )
    # decided_at từ jsonb của Postgres có thể là "+00:00" hoặc micro giây: đều về dạng Z
    row["step_states"]["cat_giai_tri"]["decided_at"] = "2026-11-22T15:13:00.123456+07:00"
    assert rl.roadmap_data(row)["phases"][0]["steps"][2]["decided_at"] == "2026-11-22T08:13:00Z"
    # người đọc không bị lộ trạng thái của bước không còn trong plan
    row["step_states"]["buoc_la"] = {"status": "accepted", "decided_at": "2026-11-22T08:13:00Z"}
    assert rl.roadmap_data(row)["counts"] == data["counts"]


def test_version_summary_va_job_data():
    s = rl.version_summary(
        {
            "id": uuid.uuid4(), "version": 3, "status": "proposed", "reason_code": "user_request", "reason_text": "x",
            "based_on_version": 2, "feasibility": "on_track", "app_date": TODAY, "created_at": NOW,
            "steps_total": 5, "accepted_count": 1, "rejected_count": 1,
        }
    )  # fmt: skip
    assert (
        s["counts"] == {"pending": 3, "accepted": 1, "rejected": 1} and s["based_on_version"] == 2
    )
    base = {"id": uuid.uuid4(), "status": "queued", "trigger": "user_request", "progress": 0, "requested_at": NOW, "stage": None,
            "finished_at": None, "version": None, "roadmap_id": None, "error_code": None, "error_message": None}  # fmt: skip
    assert rl.job_data(base) == {
        "job_id": str(base["id"]), "status": "queued", "trigger": "user_request", "progress": 0,
        "requested_at": "2026-12-10T03:00:00Z",
    }  # fmt: skip
    done = {
        **base,
        "status": "done",
        "progress": 100,
        "stage": "save",
        "finished_at": NOW,
        "version": 3,
        "roadmap_id": uuid.uuid4(),
    }
    assert rl.job_data(done)["version"] == 3
    failed = {
        **base,
        "status": "failed",
        "finished_at": NOW,
        "error_code": "ROADMAP_INVALID",
        "error_message": "m",
    }
    assert rl.job_data(failed)["error_code"] == "ROADMAP_INVALID"


# =====================================================================================================
# Sửa một bước, so hai phiên bản
# =====================================================================================================
def test_apply_step_edit_doi_so_trong_tieu_de_hanh_dong_va_ngay():
    plan = make_row(2, "active")["plan"]
    _new, st, changes = rl.apply_step_edit(plan, "bu_an_uong", amount_vnd=120_000, due_date=None)
    assert st["amount_vnd"] == 120_000 and st["title"] == "Bù 120.000 ₫ mỗi tuần cho Ăn uống"
    assert st["action"]["params"]["amount_vnd"] == 120_000
    assert changes == [{"label": "Số tiền", "before": "100.000 ₫", "after": "120.000 ₫"}]
    assert (
        st["reason"]
        == next(s for p in plan["phases"] for s in p["steps"] if s["step_id"] == "bu_an_uong")[
            "reason"
        ]
    )
    old = next(s for p in plan["phases"] for s in p["steps"] if s["step_id"] == "bu_an_uong")
    assert old["amount_vnd"] == 100_000  # plan gốc không bị đổi
    _n2, st2, ch2 = rl.apply_step_edit(plan, "nhac_du_lich", amount_vnd=None, due_date="2027-01-10")
    assert st2["due_date"] == "2027-01-10" and st2["action"]["params"]["fire_on"] == "2027-01-10"
    assert (
        "05/01" not in st2["title"]
        and ch2[0]["before"] == "05/01/2027"
        and ch2[0]["after"] == "10/01/2027"
    )
    for kw in (
        {"amount_vnd": 1000},
        {"due_date": "2027-01-10"},
    ):  # nhac_du_lich không có tiền, bu_an_uong không có ngày
        sid = "nhac_du_lich" if "amount_vnd" in kw else "bu_an_uong"
        with pytest.raises(YofinaError) as e:
            rl.apply_step_edit(plan, sid, **{"amount_vnd": None, "due_date": None, **kw})
        assert e.value.code == ErrorCode.PARAMS_INVALID
    with pytest.raises(YofinaError) as e:
        rl.apply_step_edit(plan, "bu_an_uong", amount_vnd=100_000, due_date=None)  # trùng giá trị
    assert e.value.code == ErrorCode.PARAMS_INVALID
    with pytest.raises(YofinaError) as e:
        rl.apply_step_edit(plan, "khong_co", amount_vnd=1, due_date=None)
    assert e.value.code == ErrorCode.ROADMAP_NOT_FOUND
    with pytest.raises(YofinaError) as e:  # vượt trần số tiền của hợp đồng
        rl.apply_step_edit(plan, "bu_an_uong", amount_vnd=10**15, due_date=None)
    assert e.value.code == ErrorCode.PARAMS_INVALID


def test_diff_roadmaps_them_bo_doi_va_khong_doi():
    old = rl.roadmap_data(make_row(2, "active"))
    row3 = make_row(
        3, "proposed", based_on_version=2, reason_code="behavior_changed", reason_text="lý do"
    )
    plan3 = row3["plan"]
    steps = plan3["phases"][0]["steps"]
    steps[1]["amount_vnd"] = 150_000  # bu_an_uong: đổi số tiền
    steps[1]["reason"] = "lý do mới"
    plan3["phases"][0]["steps"] = [
        s for s in steps if s["step_id"] != "cat_giai_tri"
    ]  # bỏ một bước
    plan3["phases"][1]["steps"].append(
        {
            "step_id": "buoc_moi",
            "kind": "remind",
            "title": "Mới",
            "reason": "r",
            "status": "pending",
        }
    )
    row3["step_states"] = {}
    new = rl.roadmap_data(row3)
    d = rl.diff_roadmaps(old, new, {"giai_tri": "Giải trí"})
    by = {c["step_id"]: c for c in d["changes"]}
    assert by["bu_an_uong"]["kind"] == "changed"
    assert by["bu_an_uong"]["fields"] == [
        {"label": "Số tiền", "before": "100.000 ₫", "after": "150.000 ₫"}
    ]
    assert by["bu_an_uong"]["reason_after"] == "lý do mới"
    assert by["buoc_moi"]["kind"] == "added" and by["cat_giai_tri"]["kind"] == "removed"
    assert d["counts"] == {"added": 1, "removed": 1, "changed": 1, "unchanged": 3}
    assert d["headline"] == "Phiên bản 3 khác phiên bản 2 ở 3 bước: thêm 1, bỏ 1, đổi 1."
    assert d["can_adopt"] is True and d["from_version"] == 2 and d["to_version"] == 3
    # không khác gì
    same = rl.diff_roadmaps(
        old, {**old, "version": 3, "roadmap_id": str(uuid.uuid4()), "status": "active"}, {}
    )
    assert same["changes"] == [] and same["can_adopt"] is False
    assert same["headline"] == "Phiên bản 3 không khác phiên bản 2 ở bước nào."
    # hũ nguồn đổi: nhãn dùng tên hũ
    row4 = make_row(4, "proposed", based_on_version=2)
    row4["plan"]["phases"][0]["steps"][1]["jar_code"] = "di_lai"
    row4["step_states"] = {}
    d4 = rl.diff_roadmaps(old, rl.roadmap_data(row4), {"giai_tri": "Giải trí", "di_lai": "Đi lại"})
    f = next(c for c in d4["changes"] if c["step_id"] == "bu_an_uong")["fields"][0]
    assert f == {"label": "Hũ nguồn", "before": "Giải trí", "after": "Đi lại"}


# =====================================================================================================
# ForecastClient.optimize_allocation (N1)
# =====================================================================================================
class FakeLambda:
    def __init__(self, response=None, exc: Exception | None = None):
        self.calls: list[dict[str, Any]] = []
        self.response = response
        self.exc = exc

    def invoke(self, **kw):
        self.calls.append(kw)
        if self.exc:
            raise self.exc
        return self.response


def payload_response(body: Any, *, function_error: str | None = None):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    out = {"StatusCode": 200, "Payload": SimpleNamespace(read=lambda: raw)}
    if function_error:
        out["FunctionError"] = function_error
    return out


def test_optimize_allocation_goi_invoke_dong_bo_va_tra_nguyen_van_phong_bi():
    ok = load_json(FIXTURES / "tools" / "optimize_allocation.ok.json")
    fake = FakeLambda(payload_response(ok))
    client = ForecastClient("yofina-forecast-batch", client=fake)
    out = client.optimize_allocation("sub-1", {"horizon_months": 3, "shock_id": "tien_tro_tang"})
    assert out == ok
    (call,) = fake.calls
    assert (
        call["FunctionName"] == "yofina-forecast-batch"
        and call["InvocationType"] == "RequestResponse"
    )
    assert json.loads(call["Payload"]) == {
        "op": "optimize_allocation",
        "user_id": "sub-1",
        "args": {"horizon_months": 3, "shock_id": "tien_tro_tang"},
    }
    # phong bì lỗi nghiệp vụ (vd. thiếu hồ sơ) là kết quả thành công của Lambda: giữ nguyên
    err = load_json(FIXTURES / "tools" / "optimize_allocation.error_profile_incomplete.json")
    assert (
        ForecastClient("f", client=FakeLambda(payload_response(err))).optimize_allocation("u", {})
        == err
    )


@pytest.mark.parametrize(
    "fake",
    [
        FakeLambda(payload_response({"errorMessage": "boom"}, function_error="Unhandled")),
        FakeLambda(exc=TimeoutError("read timeout")),
        FakeLambda(payload_response(b"khong phai json")),
        FakeLambda(payload_response({"status": "ok-nhung-sai"})),
        FakeLambda(payload_response([1, 2])),
        FakeLambda(payload_response(b"")),
    ],
)
def test_optimize_allocation_loi_goi_la_forecast_unavailable(fake):
    with pytest.raises(YofinaError) as e:
        ForecastClient("f", client=fake).optimize_allocation("u", {})
    assert e.value.code == ErrorCode.FORECAST_UNAVAILABLE


# =====================================================================================================
# Sự kiện roadmap.regeneration_requested
# =====================================================================================================
def test_su_kien_yeu_cau_sinh_lai_khop_hop_dong_va_khong_co_ghi_chu():
    job = str(uuid.uuid4())
    ev = events.roadmap_regeneration_requested(
        user_id="sub-1", trace_id="a" * 32, job_id=job, occurred_at=NOW, app_date=TODAY,
        trigger="user_request", based_on_version=2, alternative_id="lui_han",
    )  # fmt: skip
    schema = load_json(CONTRACTS / "events" / "roadmap.regeneration_requested.schema.json")
    errors = list(Draft202012Validator(schema, registry=build_registry()).iter_errors(ev.detail))
    assert not errors, [e.message for e in errors]
    assert ev.detail_type == "roadmap.regeneration_requested"
    assert ev.detail["event_id"] == ev.detail["job_id"] == job
    minimal = events.roadmap_regeneration_requested(
        user_id="sub-1",
        trace_id=None,
        job_id=job,
        occurred_at=NOW,
        app_date=TODAY,
        trigger="behavior_changed",
    )
    assert set(minimal.detail) == {
        "v",
        "event_id",
        "user_id",
        "occurred_at",
        "app_date",
        "job_id",
        "trigger",
    }
    assert not list(
        Draft202012Validator(schema, registry=build_registry()).iter_errors(minimal.detail)
    )


# =====================================================================================================
# Phân tuyến và kiểm đầu vào REST (kho dữ liệu thay bằng Stub ghi lại lời gọi)
# =====================================================================================================
class StubOps:
    def __init__(self):
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __getattr__(self, name: str):
        def fn(user_id: str, *args: Any, **kw: Any):
            extra = {"args": args} if args else {}
            self.calls.append((name, {"user": user_id, **extra, **kw}))
            return {"status": "OK", "stub": name}

        return fn


def rest_with_stub(method, path, *, body=None, query=None, sub=U):
    svc, _repo, _clock = make_service()
    stub = StubOps()
    svc.__dict__["_roadmap_ops"] = stub
    out = handle_http(http_event(method, path, sub=sub, body=body, query=query), svc)
    return out["statusCode"], json.loads(out["body"]), stub


def test_match_route_tam_route_va_tham_so_duong_dan():
    assert match_route("GET /roadmap") == ("roadmap", {})
    assert match_route("GET /roadmap/versions") == ("versions", {})
    assert match_route("GET /roadmap/diff") == ("diff", {})
    assert match_route("GET /roadmap/jobs/abc") == ("job", {"job_id": "abc"})
    assert match_route("POST /roadmap/steps/bu_an_uong/decision") == (
        "step_decision",
        {"step_id": "bu_an_uong"},
    )
    assert match_route("POST /roadmap/steps/bu_an_uong/edit") == (
        "step_edit",
        {"step_id": "bu_an_uong"},
    )
    assert match_route("POST /roadmap/versions/3/decision") == (
        "version_decision",
        {"version": "3"},
    )
    assert match_route("POST /roadmap/regenerate") == ("regenerate", {})
    for no in ("POST /roadmap", "GET /roadmap/regenerate", "GET /roadmap/steps/x/decision", "GET /roadmapx",
               "POST /roadmap/steps/x/y/decision", "DELETE /roadmap"):  # fmt: skip
        assert match_route(no) is None


def test_rest_chuyen_tiep_dung_ham_va_danh_tinh_chi_tu_jwt():
    status, body, stub = rest_with_stub(
        "GET", "/roadmap", query={"version": "3", "which": "latest"}
    )
    assert status == 200 and body == {"status": "OK", "stub": "roadmap_response"}
    name, kw = stub.calls[0]
    assert (
        name == "roadmap_response"
        and kw["user"] == U
        and kw["version"] == 3
        and kw["which"] == "latest"
    )
    assert kw["trace_id"]
    _, _, stub = rest_with_stub("GET", "/roadmap")
    assert stub.calls[0][1]["version"] is None and stub.calls[0][1]["which"] == "active"
    _, _, stub = rest_with_stub("GET", "/roadmap/versions", query={"limit": "5"})
    assert stub.calls == [("versions_response", {"user": U, "limit": 5})]
    _, _, stub = rest_with_stub("GET", "/roadmap/versions")
    assert stub.calls[0][1]["limit"] == 20
    _, _, stub = rest_with_stub(
        "GET", "/roadmap/diff", query={"from_version": "2", "to_version": "3"}
    )
    assert stub.calls[0][1]["from_version"] == 2 and stub.calls[0][1]["to_version"] == 3
    _, _, stub = rest_with_stub(
        "POST",
        "/roadmap/steps/bu_an_uong/decision",
        body={"version": 3, "decision": "rejected", "reason": " cần tiền "},
    )
    assert stub.calls[0] == (
        "decide_step_response",
        {"user": U, "step_id": "bu_an_uong", "version": 3, "decision": "rejected", "reason": "cần tiền",
         "trace_id": stub.calls[0][1]["trace_id"]},
    )  # fmt: skip
    _, _, stub = rest_with_stub(
        "POST",
        "/roadmap/steps/bu_an_uong/edit",
        body={"version": 2, "amount_vnd": 120000, "due_date": "2026-12-01"},
    )
    kw = stub.calls[0][1]
    assert (kw["version"], kw["amount_vnd"], kw["due_date"]) == (2, 120000, "2026-12-01")
    _, _, stub = rest_with_stub("POST", "/roadmap/versions/3/decision", body={"decision": "adopt"})
    assert stub.calls[0][1]["version"] == 3 and stub.calls[0][1]["decision"] == "adopt"
    _, _, stub = rest_with_stub(
        "POST",
        "/roadmap/regenerate",
        body={"note": "đi sau Tết", "alternative_id": "lui_han", "based_on_version": 1},
    )
    kw = stub.calls[0][1]
    assert (kw["note"], kw["alternative_id"], kw["based_on_version"]) == (
        "đi sau Tết",
        "lui_han",
        1,
    )
    _, _, stub = rest_with_stub("POST", "/roadmap/regenerate")  # thân rỗng được phép
    assert stub.calls[0][1]["note"] is None and stub.calls[0][1]["based_on_version"] is None
    uid = str(uuid.uuid4())
    _, _, stub = rest_with_stub("GET", f"/roadmap/jobs/{uid.upper()}")
    assert stub.calls == [("job_response", {"user": U, "args": (uid,)})]


@pytest.mark.parametrize(
    ("method", "path", "body", "query"),
    [
        ("GET", "/roadmap", None, {"version": "0"}),
        ("GET", "/roadmap", None, {"version": "10001"}),
        ("GET", "/roadmap", None, {"version": "a"}),
        ("GET", "/roadmap", None, {"which": "xxx"}),
        ("GET", "/roadmap/versions", None, {"limit": "0"}),
        ("GET", "/roadmap/versions", None, {"limit": "51"}),
        ("GET", "/roadmap/diff", None, {"from_version": "x"}),
        ("POST", "/roadmap/steps/Bad-Id/decision", {"version": 1, "decision": "accepted"}, None),
        ("POST", "/roadmap/steps/a/decision", {"decision": "accepted"}, None),
        ("POST", "/roadmap/steps/a/decision", {"version": True, "decision": "accepted"}, None),
        (
            "POST",
            "/roadmap/steps/a/decision",
            {"version": 1, "decision": "accepted", "user_id": "sub-lan"},
            None,
        ),
        (
            "POST",
            "/roadmap/steps/a/decision",
            {"version": 1, "decision": "accepted", "reason": "x" * 201},
            None,
        ),
        ("POST", "/roadmap/steps/a/decision", None, None),
        ("POST", "/roadmap/steps/a/edit", {"version": 1}, None),
        ("POST", "/roadmap/steps/a/edit", {"version": 1, "amount_vnd": -5}, None),
        ("POST", "/roadmap/steps/a/edit", {"version": 1, "amount_vnd": "100"}, None),
        ("POST", "/roadmap/steps/a/edit", {"version": 1, "due_date": "2026-02-30"}, None),
        ("POST", "/roadmap/steps/a/edit", {"version": 1, "due_date": "30/11/2026"}, None),
        ("POST", "/roadmap/steps/a/edit", {"amount_vnd": 5}, None),
        ("POST", "/roadmap/versions/0/decision", {"decision": "adopt"}, None),
        ("POST", "/roadmap/versions/abc/decision", {"decision": "adopt"}, None),
        ("POST", "/roadmap/versions/1/decision", {"decision": "adopt", "x": 1}, None),
        ("POST", "/roadmap/regenerate", {"alternative_id": "Có-Dấu"}, None),
        ("POST", "/roadmap/regenerate", {"note": 5}, None),
        ("POST", "/roadmap/regenerate", {"based_on_version": 0}, None),
        ("POST", "/roadmap/regenerate", {"user_id": "x"}, None),
        ("GET", "/roadmapx", None, None),
        ("POST", "/roadmap", None, None),
    ],
)
def test_rest_kiem_dau_vao_truoc_khi_cham_dich_vu(method, path, body, query):
    status, out, stub = rest_with_stub(method, path, body=body, query=query)
    assert status == 400 and out["error"]["code"] == "PARAMS_INVALID", out
    assert stub.calls == []  # đầu vào sai không chạm kho dữ liệu


def test_rest_job_id_sai_dang_la_404_nhu_khong_ton_tai_va_can_jwt():
    status, out, stub = rest_with_stub("GET", "/roadmap/jobs/khong-phai-uuid")
    assert status == 404 and out["error"]["code"] == "ROADMAP_NOT_FOUND" and stub.calls == []
    status, out, stub = rest_with_stub("GET", "/roadmap", sub=None)
    assert status == 401 and out["error"]["code"] == "UNAUTHENTICATED"


def test_dispatch_route_la_nem_params_invalid():
    with pytest.raises(YofinaError) as e:
        dispatch(
            "GET /roadmap/nope",
            {},
            U,
            "t" * 8,
            SimpleNamespace(__dict__={"_roadmap_ops": StubOps()}),
        )
    assert e.value.code == ErrorCode.PARAMS_INVALID


# =====================================================================================================
# Tool Gateway
# =====================================================================================================
def test_tool_gateway_chi_nhan_tham_so_dung_va_chuyen_dung_ham():
    assert ROADMAP_TOOLS == ("optimize_allocation", "save_roadmap", "get_roadmap")
    planner = {t["name"]: t for t in load_json(CONTRACTS / "tools" / "planner.json")}
    for name in ROADMAP_TOOLS:
        assert set(planner[name]["inputSchema"]["properties"]) - {"user_id"} == set(
            _ARG_KEYS[name]
        ), name
    assert "confirm_token" not in _ARG_KEYS["save_roadmap"]  # lưu lộ trình KHÔNG qua token

    svc, _r, _c = make_service()
    stub = StubOps()
    svc.__dict__["_roadmap_ops"] = stub
    out = handle_gateway(
        {"user_id": U, "version": 3, "which": "proposed", "la": 1},
        gateway_context("planner___get_roadmap"),
        svc,
    )
    assert out == {"status": "OK", "stub": "get_roadmap_result"}
    assert stub.calls[0] == ("get_roadmap_result", {"user": U, "version": 3, "which": "proposed"})
    handle_gateway(
        {"user_id": U, "horizon_months": 3, "goals": [{"jar": "du_lich"}], "bo_qua": 1},
        gateway_context("planner___optimize_allocation"),
        svc,
    )
    assert stub.calls[1] == (
        "optimize_allocation_result",
        {"user": U, "horizon_months": 3, "goals": [{"jar": "du_lich"}]},
    )
    handle_gateway(
        {"user_id": U, "reason_code": "user_request"},
        gateway_context("planner___save_roadmap"),
        svc,
    )
    name, kw = stub.calls[2]
    assert name == "save_roadmap_result" and kw["reason_code"] == "user_request" and kw["trace_id"]
    # thiếu user_id: UNAUTHENTICATED; lỗi nghiệp vụ trong tool đổi thành phong bì lỗi
    out = handle_gateway({"version": 1}, gateway_context("planner___get_roadmap"), svc)
    assert out["status"] == "ERROR" and out["code"] == "UNAUTHENTICATED"


# =====================================================================================================
# RoadmapOps trên kho giả (logic của dịch vụ; SQL thật ở local_pg)
# =====================================================================================================
class FakeRoadmapRepo:
    """Giống ngữ nghĩa các hàm `app_*` của migration 0052 (phiên bản, trạng thái, xung đột), dữ liệu trong bộ nhớ."""

    def __init__(self):
        self.rows: list[dict[str, Any]] = []
        self.flags: list[dict[str, Any]] = []
        self.jobs: list[dict[str, Any]] = []
        self.audits: list[dict[str, Any]] = []
        self.feedback: list[dict[str, Any]] = []

    def _find(self, version):
        return next((r for r in self.rows if r["version"] == version), None)

    def get_roadmap(self, user_id, version=None, which="active"):
        if version is not None:
            return self._find(version)
        if which == "proposed":
            return next((r for r in self.rows if r["status"] == "proposed"), None)
        if which == "latest":
            return max(self.rows, key=lambda r: r["version"], default=None)
        active = next((r for r in self.rows if r["status"] == "active"), None)
        return active or max(self.rows, key=lambda r: r["version"], default=None)

    def list_versions(self, user_id, limit=20):
        out = []
        for r in sorted(self.rows, key=lambda r: -r["version"])[:limit]:
            total = sum(len(p["steps"]) for p in r["plan"]["phases"])
            states = r["step_states"].values()
            out.append({**r, "steps_total": total,
                        "accepted_count": sum(s["status"] == "accepted" for s in states),
                        "rejected_count": sum(s["status"] == "rejected" for s in states)})  # fmt: skip
        return out

    def get_job(self, user_id, job_id=None):
        jobs = [j for j in self.jobs if job_id is None or str(j["id"]) == job_id]
        return jobs[-1] if jobs else None

    def list_behavior_flags(self, user_id, status=None):
        return [f for f in self.flags if status is None or f["status"] == status]

    def save_roadmap(self, user_id, *, reason_code, reason_text, reason_detail, behavior_flag_id, based_on_version,
                     feasibility, app_date, plan, rules_version, status, trace_id, step_states=None,
                     audit=None, feedback=None):  # fmt: skip
        if status not in ("active", "proposed"):
            raise YofinaError(ErrorCode.ROADMAP_INVALID, "status")
        if reason_code == "initial" and self.rows:
            raise YofinaError(ErrorCode.ROADMAP_VERSION_CONFLICT, "đã có lộ trình")
        if based_on_version is not None:
            base = self._find(based_on_version)
            if base is None or base["status"] not in ("active", "proposed"):
                raise YofinaError(ErrorCode.ROADMAP_VERSION_CONFLICT, "bản gốc đã bị thay")
        if status == "active":
            for r in self.rows:
                if r["status"] == "active":
                    r["status"] = "superseded"
        for r in self.rows:
            if r["status"] == "proposed":
                r["status"] = "discarded"
        row = {
            "id": str(uuid.uuid4()), "version": len(self.rows) + 1, "status": status, "reason_code": reason_code,
            "reason_text": reason_text, "reason_detail": list(reason_detail) if reason_detail else None,
            "behavior_flag_id": behavior_flag_id, "based_on_version": based_on_version, "feasibility": feasibility,
            "app_date": app_date, "plan": copy.deepcopy(dict(plan)), "step_states": copy.deepcopy(dict(step_states or {})),
            "rules_version": rules_version, "trace_id": trace_id, "created_at": NOW, "updated_at": NOW,
        }  # fmt: skip
        self.rows.append(row)
        if behavior_flag_id:
            for f in self.flags:
                if str(f["id"]) == behavior_flag_id and f["status"] == "confirmed":
                    f["status"] = "applied"
        self.audits.append(audit or {})
        if feedback:
            self.feedback.append({**feedback, "version": row["version"]})
        return {"id": row["id"], "version": row["version"], "status": status, "created_at": NOW}

    def set_step_state(
        self, user_id, *, version, step_id, status, edited, trace_id, audit, feedback
    ):
        row = self._find(version)
        if row is None:
            raise YofinaError(ErrorCode.ROADMAP_NOT_FOUND, "no")
        if row["status"] not in ("active", "proposed"):
            raise YofinaError(ErrorCode.ROADMAP_VERSION_CONFLICT, "no")
        if status == "pending":
            row["step_states"].pop(step_id, None)
        else:
            row["step_states"][step_id] = {"status": status, "decided_at": NOW.isoformat(),
                                           **({"edited": True} if edited else {})}  # fmt: skip
        self.audits.append(audit)
        if feedback:
            self.feedback.append({**feedback, "version": version})
        return {"id": row["id"], "version": version, "step_states": row["step_states"]}

    def decide_version(self, user_id, *, version, decision, trace_id, audit, feedback):
        row = self._find(version)
        if row is None:
            raise YofinaError(ErrorCode.ROADMAP_NOT_FOUND, "no")
        if decision == "adopt" and row["status"] == "proposed":
            for r in self.rows:
                if r["status"] == "active":
                    r["status"] = "superseded"
            row["status"] = "active"
        elif decision == "keep_previous" and row["status"] == "proposed":
            row["status"] = "discarded"
        else:
            raise YofinaError(ErrorCode.ROADMAP_VERSION_CONFLICT, "không còn chờ chọn")
        self.audits.append(audit)
        self.feedback.append({**feedback, "version": version})
        return {"id": row["id"], "version": version, "status": row["status"]}

    def create_job(self, user_id, *, alternative_id, note, based_on_version, trace_id, audit):
        if any(j["status"] in ("queued", "running") for j in self.jobs):
            return None
        job = {"id": str(uuid.uuid4()), "status": "queued", "trigger": "user_request", "stage": None, "progress": 0,
               "alternative_id": alternative_id, "based_on_version": based_on_version, "note": note,
               "requested_at": NOW, "finished_at": None, "version": None, "roadmap_id": None,
               "error_code": None, "error_message": None}  # fmt: skip
        self.jobs.append(job)
        self.audits.append(audit)
        return job["id"]


class FakeJars:
    """Kho đọc của `LedgerService` mà `RoadmapOps` cần (không dùng `ledger_fakes.FakeRepo` vì cần hũ có `kind` và mục tiêu)."""

    def __init__(self):
        self.profile: dict[str, Any] | None = {"monthly_salary_vnd": Decimal(9_000_000), "payday_day": 5,
                                               "risk_tolerance": "medium", "clock_offset_days": -19}  # fmt: skip
        self.summaries: list[dict[str, Any]] = [
            {"jar_code": "an_uong", "run_id": "r1", "computed_at": NOW, "run_app_date": TODAY, "history_days": 47,
             "data_coverage": Decimal("0.620"), "confidence_label": "medium", "is_initial_estimate": False}
        ]  # fmt: skip
        self.jars = tuple(
            {
                "code": c,
                "name": n,
                "kind": k,
                "balance_vnd": Decimal(b),
                "goal_vnd": g,
                "color_key": "teal",
                "icon_key": "x",
            }
            for c, n, k, b, g in (
                ("hoa_don", "Hóa đơn", "obligation", 450_000, None),
                ("nghia_vu", "Nghĩa vụ", "obligation", 1_000_000, None),
                ("du_phong", "Dự phòng", "saving", 2_700_000, None),
                ("giai_tri", "Giải trí", "spending", 760_000, None),
                ("an_uong", "Ăn uống", "spending", 380_000, None),
                ("du_lich", "Du lịch", "saving", 1_800_000, 6_000_000),
                ("chua_phan_loai", "Chưa phân loại", "system", -180_000, None),
            )
        )

    def jar_view(self, uid):
        return JarView(-19, self.jars)

    def clock_offset(self, uid):
        return -19

    def user_row(self, uid):
        return self.profile

    def list_obligations(self, uid, *, status="active", limit=100):
        return [
            {"kind": "bill", "name": "Tiền điện", "amount_vnd": Decimal(375_000), "due_date": date(2026, 11, 26),
             "cycle": "monthly", "due_day": 26, "pay_jar_code": "hoa_don", "is_essential": True, "status": "active"}
        ]  # fmt: skip

    def forecast_summaries(self, uid, jar=None):
        return self.summaries


class FakeLedgerService:
    def __init__(self):
        self.repo = FakeJars()
        self.settings = SETTINGS
        self.forecast = None
        self.published: list[Any] = []

    def now(self):
        return NOW

    def _app_date(self, offset, now):
        return app_today(offset or 0, now, ZoneInfo("Asia/Ho_Chi_Minh"))

    def _is_stale(self, summary, today, computed, now):
        return False

    def _publish(self, user_id, trace_id, evs):
        self.published.extend(evs)


@pytest.fixture
def ops():
    svc = FakeLedgerService()
    repo = FakeRoadmapRepo()
    o = RoadmapOps(svc, repo)  # type: ignore[arg-type]
    o.fake = (svc, repo)  # type: ignore[attr-defined]
    return o


def seed(ops_: RoadmapOps) -> FakeRoadmapRepo:
    repo = ops_.repo  # type: ignore[assignment]
    repo.rows.extend([make_row(1, "superseded", reason_code="initial", reason_text="Lộ trình đầu tiên của bạn."),
                      make_row(2, "active")])  # fmt: skip
    return repo  # type: ignore[return-value]


def test_save_roadmap_ban_dau_tien_active_va_dien_cac_truong_he_thong(ops):
    out = ops.save_roadmap_result(
        U, trace_id="t" * 8, **ok_args(reason_code="initial", based_on_version=None)
    )
    assert (
        out["status"] == "OK"
        and out["app_date"] == "2026-11-21"
        and out["as_of"] == "2026-12-10T03:00:00Z"
    )
    d = out["data"]
    assert d["version"] == 1 and d["status"] == "active" and "based_on_version" not in d
    assert d["reason"] == {"code": "initial", "text": "Lộ trình đầu tiên của bạn."}
    assert (
        d["basis"]["coverage"] == 0.62
        and d["basis"]["stale"] is False
        and d["basis"]["history_days"] == 47
    )
    assert d["rules_version"].startswith("v") and d["counts"] == {
        "pending": 3,
        "accepted": 0,
        "rejected": 0,
    }
    assert all(s["status"] == "pending" for p in d["phases"] for s in p["steps"])
    repo = ops.repo
    assert (
        repo.audits[0]["event_type"] == "roadmap_saved"
        and repo.audits[0]["params"]["reason_code"] == "initial"
    )


def test_save_roadmap_ban_sau_la_cho_chon_va_cac_tu_choi(ops):
    repo = seed(ops)
    out = ops.save_roadmap_result(U, trace_id="t" * 8, **ok_args())
    assert out["data"]["status"] == "proposed" and out["data"]["version"] == 3
    assert [r["status"] for r in repo.rows] == ["superseded", "active", "proposed"]
    for bad, code in (
        (ok_args(reason_code="step_edited"), ErrorCode.ROADMAP_INVALID),
        (ok_args(behavior_flag_id=str(uuid.uuid4())), ErrorCode.ROADMAP_INVALID),
        (ok_args(based_on_version=1), ErrorCode.ROADMAP_VERSION_CONFLICT),
        (ok_args(phases=[]), ErrorCode.PARAMS_INVALID),
    ):
        with pytest.raises(YofinaError) as e:
            ops.save_roadmap_result(U, trace_id="t" * 8, **bad)
        assert e.value.code == code
    # thiếu hồ sơ, thiếu dự báo
    ops.svc.repo.profile = {**ops.svc.repo.profile, "monthly_salary_vnd": None}
    with pytest.raises(YofinaError) as e:
        ops.save_roadmap_result(U, trace_id="t" * 8, **ok_args())
    assert e.value.code == ErrorCode.PROFILE_INCOMPLETE
    ops.svc.repo.profile = {**ops.svc.repo.profile, "monthly_salary_vnd": Decimal(9_000_000)}
    ops.svc.repo.summaries = []
    with pytest.raises(YofinaError) as e:
        ops.save_roadmap_result(U, trace_id="t" * 8, **ok_args())
    assert e.value.code == ErrorCode.FORECAST_UNAVAILABLE
    assert len(repo.rows) == 3


def test_save_roadmap_vi_pham_block_khong_luu(ops):
    repo = seed(ops)
    args = ok_args()
    st = args["phases"][0]["steps"][
        1
    ]  # bu_an_uong: rút từ Giải trí; đổi sang Hóa đơn và rút quá tay
    st.update(jar_code="hoa_don", amount_vnd=300_000)
    st["action"]["params"].update(from_jar="hoa_don", amount_vnd=300_000)
    with pytest.raises(YofinaError) as e:
        ops.save_roadmap_result(U, trace_id="t" * 8, **args)
    assert e.value.code == ErrorCode.ROADMAP_INVALID and "obligations_first" in e.value.message
    assert len(repo.rows) == 2 and repo.audits == []


def test_save_roadmap_behavior_changed_can_co_da_xac_nhan(ops):
    repo = seed(ops)
    fid = str(uuid.uuid4())
    repo.flags.append({"id": fid, "jar_code": "an_uong", "status": "confirmed", "old_weekly_vnd": Decimal(520_000),
                       "new_weekly_vnd": Decimal(810_000), "weeks_held": 2})  # fmt: skip
    args = ok_args(reason_code="behavior_changed", behavior_flag_id=fid)
    out = ops.save_roadmap_result(U, trace_id="t" * 8, **args)
    assert (
        out["data"]["reason"]["text"]
        == "Chi Ăn uống mỗi tuần tăng từ 520.000 ₫ lên 810.000 ₫ và giữ mức đó 2 tuần."
    )
    assert out["data"]["reason"]["behavior_flag_id"] == fid
    assert repo.flags[0]["status"] == "applied"
    repo.flags[0]["status"] = "suspected"
    with pytest.raises(YofinaError) as e:
        ops.save_roadmap_result(U, trace_id="t" * 8, **{**args, "based_on_version": 2})
    assert e.value.code == ErrorCode.ROADMAP_INVALID and "chưa được xác nhận" in e.value.message


def test_get_roadmap_va_diff_va_phien_ban(ops):
    seed(ops)
    ops.repo.rows.append(
        make_row(3, "proposed", reason_code="behavior_changed", reason_text="lý do")
    )
    out = ops.get_roadmap_result(U)
    assert out["data"]["version"] == 2 and out["data"]["status"] == "active"
    assert ops.get_roadmap_result(U, which="proposed")["data"]["version"] == 3
    assert ops.get_roadmap_result(U, version="1")["data"]["version"] == 1
    for kw, code in (
        ({"version": 9}, ErrorCode.ROADMAP_NOT_FOUND),
        ({"version": 0}, ErrorCode.PARAMS_INVALID),
        ({"which": "x"}, ErrorCode.PARAMS_INVALID),
    ):
        with pytest.raises(YofinaError) as e:
            ops.get_roadmap_result(U, **kw)
        assert e.value.code == code
    v = ops.versions_response(U, limit=20)
    assert (
        v["active_version"] == 2
        and v["proposed_version"] == 3
        and [x["version"] for x in v["versions"]] == [3, 2, 1]
    )
    block = ops.diff_response(U, from_version=None, to_version=None, trace_id="t" * 8)
    assert (
        block["type"] == "roadmap_diff"
        and block["data"]["to_version"] == 3
        and block["data"]["from_version"] == 2
    )
    with pytest.raises(YofinaError) as e:  # v1 không có bản gốc
        ops.diff_response(U, from_version=None, to_version=1, trace_id="t" * 8)
    assert e.value.code == ErrorCode.PARAMS_INVALID
    empty = RoadmapOps(FakeLedgerService(), FakeRoadmapRepo())  # type: ignore[arg-type]
    with pytest.raises(YofinaError) as e:
        empty.get_roadmap_result(U)
    assert e.value.code == ErrorCode.ROADMAP_NOT_FOUND and "chưa có lộ trình" in e.value.message
    assert empty.versions_response(U, limit=20) == {"versions": []}


def test_quyet_dinh_buoc_idempotent_va_loi(ops):
    repo = seed(ops)
    kw = {"step_id": "nhac_du_lich", "version": 2, "reason": None, "trace_id": "t" * 8}
    block = ops.decide_step_response(U, decision="rejected", **kw)
    assert block["type"] == "roadmap" and block["id"] == f"roadmap:{'t' * 8}:v2"
    assert (
        len(repo.feedback) == 1
        and repo.feedback[0]["decision"] == "rejected"
        and len(repo.audits) == 1
    )
    again = ops.decide_step_response(U, decision="rejected", **kw)
    assert (
        again["data"] == block["data"] and len(repo.feedback) == 1 and len(repo.audits) == 1
    )  # không ghi thêm
    ops.decide_step_response(U, decision="pending", **kw)  # hoàn tác: audit có, feedback không
    assert len(repo.feedback) == 1 and len(repo.audits) == 2
    ops.decide_step_response(U, decision="rejected", **{**kw, "reason": "đắt"})
    assert repo.feedback[-1]["reason"] == "đắt"
    ops.decide_step_response(
        U, decision="accepted", **{**kw, "reason": "bỏ qua vì không phải rejected"}
    )
    assert repo.feedback[-1]["reason"] is None
    for kwargs, code in (
        ({**kw, "step_id": "khong_co"}, ErrorCode.ROADMAP_NOT_FOUND),
        ({**kw, "version": 1}, ErrorCode.ROADMAP_VERSION_CONFLICT),
        ({**kw, "version": 7}, ErrorCode.ROADMAP_NOT_FOUND),
    ):
        with pytest.raises(YofinaError) as e:
            ops.decide_step_response(U, decision="accepted", **kwargs)
        assert e.value.code == code
    with pytest.raises(YofinaError) as e:
        ops.decide_step_response(U, decision="maybe", **kw)
    assert e.value.code == ErrorCode.PARAMS_INVALID


def test_sua_buoc_luu_ban_moi_va_giu_trang_thai(ops):
    repo = seed(ops)
    block = ops.edit_step_response(
        U, step_id="bu_an_uong", version=2, amount_vnd=120_000, due_date=None, trace_id="t" * 8
    )
    d = block["data"]
    assert d["version"] == 3 and d["status"] == "active" and d["reason"]["code"] == "step_edited"
    assert [r["status"] for r in repo.rows] == ["superseded", "superseded", "active"]
    assert d["counts"] == {"pending": 2, "accepted": 2, "rejected": 1}
    step = next(s for p in d["phases"] for s in p["steps"] if s["step_id"] == "bu_an_uong")
    assert step["amount_vnd"] == 120_000 and step["edited"] is True and step["status"] == "accepted"
    assert repo.feedback[-1] == {
        "option_id": "bu_an_uong",
        "decision": "accepted",
        "reason": "edited",
        "version": 3,
    }
    assert repo.audits[-1]["event_type"] == "roadmap_step_edited"
    # bản gốc đã bị thay
    with pytest.raises(YofinaError) as e:
        ops.edit_step_response(
            U, step_id="bu_an_uong", version=2, amount_vnd=130_000, due_date=None, trace_id="t" * 8
        )
    assert e.value.code == ErrorCode.ROADMAP_VERSION_CONFLICT
    with pytest.raises(YofinaError) as e:  # ngày trước hôm nay
        ops.edit_step_response(
            U,
            step_id="nhac_du_lich",
            version=3,
            amount_vnd=None,
            due_date="2026-11-01",
            trace_id="t" * 8,
        )
    assert e.value.code == ErrorCode.PARAMS_INVALID
    assert len(repo.rows) == 3


def test_sua_buoc_vi_pham_luat_khong_luu(ops):
    repo = seed(ops)
    step = next(
        s
        for p in repo.rows[1]["plan"]["phases"]
        for s in p["steps"]
        if s["step_id"] == "bu_an_uong"
    )
    step["jar_code"] = "hoa_don"  # rút từ hũ gánh nghĩa vụ thiết yếu
    step["action"]["params"]["from_jar"] = "hoa_don"
    with pytest.raises(YofinaError) as e:
        ops.edit_step_response(
            U, step_id="bu_an_uong", version=2, amount_vnd=300_000, due_date=None, trace_id="t" * 8
        )
    assert e.value.code == ErrorCode.ROADMAP_INVALID and "obligations_first" in e.value.message
    assert len(repo.rows) == 2


def test_quyet_dinh_phien_ban(ops):
    repo = seed(ops)
    repo.rows.append(make_row(3, "proposed"))
    block = ops.decide_version_response(U, version=3, decision="adopt", trace_id="t" * 8)
    assert block["data"]["status"] == "active" and [r["status"] for r in repo.rows] == [
        "superseded",
        "superseded",
        "active",
    ]
    n = len(repo.audits)
    again = ops.decide_version_response(U, version=3, decision="adopt", trace_id="t" * 8)
    assert again["data"] == block["data"] and len(repo.audits) == n  # idempotent
    with pytest.raises(YofinaError) as e:
        ops.decide_version_response(U, version=3, decision="keep_previous", trace_id="t" * 8)
    assert e.value.code == ErrorCode.ROADMAP_VERSION_CONFLICT
    with pytest.raises(YofinaError) as e:
        ops.decide_version_response(U, version=1, decision="adopt", trace_id="t" * 8)
    assert e.value.code == ErrorCode.ROADMAP_VERSION_CONFLICT  # bản đã thay không dùng lại được
    with pytest.raises(YofinaError) as e:
        ops.decide_version_response(U, version=9, decision="adopt", trace_id="t" * 8)
    assert e.value.code == ErrorCode.ROADMAP_NOT_FOUND
    with pytest.raises(YofinaError) as e:
        ops.decide_version_response(U, version=3, decision="x", trace_id="t" * 8)
    assert e.value.code == ErrorCode.PARAMS_INVALID
    assert (
        repo.feedback[-1]["option_id"] == "version_adopt"
        and repo.feedback[-1]["decision"] == "accepted"
    )


def test_sinh_lai_ghi_job_phat_su_kien_va_tra_lai_job_dang_chay(ops):
    repo = seed(ops)
    job = ops.regenerate_response(
        U, note="ghi chú", alternative_id=None, based_on_version=None, trace_id="t" * 8
    )
    assert job["status"] == "queued" and job["trigger"] == "user_request"
    (ev,) = ops.svc.published
    assert (
        ev.detail_type == "roadmap.regeneration_requested" and ev.detail["job_id"] == job["job_id"]
    )
    assert ev.detail["based_on_version"] == 2 and "note" not in ev.detail
    assert repo.jobs[0]["note"] == "ghi chú" and repo.jobs[0]["based_on_version"] == 2
    again = ops.regenerate_response(
        U, note=None, alternative_id=None, based_on_version=None, trace_id="u" * 8
    )
    assert again["job_id"] == job["job_id"] and len(ops.svc.published) == 1 and len(repo.jobs) == 1
    assert ops.versions_response(U, limit=20)["current_job"]["job_id"] == job["job_id"]
    assert ops.job_response(U, job["job_id"]) == job
    with pytest.raises(YofinaError) as e:
        ops.job_response(U, str(uuid.uuid4()))
    assert e.value.code == ErrorCode.ROADMAP_NOT_FOUND


def test_sinh_lai_kiem_ban_goc_va_lua_chon(ops):
    repo = seed(ops)
    fresh = lambda: dict(note=None, alternative_id=None, based_on_version=None, trace_id="t" * 8)  # noqa: E731
    with pytest.raises(YofinaError) as e:
        ops.regenerate_response(U, **{**fresh(), "based_on_version": 1})
    assert e.value.code == ErrorCode.ROADMAP_VERSION_CONFLICT
    with pytest.raises(YofinaError) as e:
        ops.regenerate_response(U, **{**fresh(), "based_on_version": 8})
    assert e.value.code == ErrorCode.ROADMAP_NOT_FOUND
    with pytest.raises(YofinaError) as e:  # bản gốc on_track không có lựa chọn nào
        ops.regenerate_response(U, **{**fresh(), "alternative_id": "lui_han"})
    assert e.value.code == ErrorCode.PARAMS_INVALID
    assert repo.jobs == [] and ops.svc.published == []
    repo.rows[1]["plan"]["alternatives"] = [
        {"option_id": "lui_han", "kind": "delay_goal", "label": "a", "summary": "b"},
        {"option_id": "giam_muc_tieu", "kind": "reduce_goal", "label": "c", "summary": "d"},
    ]
    job = ops.regenerate_response(U, **{**fresh(), "alternative_id": "lui_han"})
    assert (
        repo.jobs[0]["alternative_id"] == "lui_han"
        and ops.svc.published[0].detail["alternative_id"] == "lui_han"
    )
    assert job["status"] == "queued"


def test_sinh_lai_chua_co_lo_trinh_thi_job_khong_co_ban_goc(ops):
    job = ops.regenerate_response(
        U, note=None, alternative_id=None, based_on_version=None, trace_id="t" * 8
    )
    assert job["status"] == "queued" and ops.repo.jobs[0]["based_on_version"] is None
    assert "based_on_version" not in ops.svc.published[0].detail


def test_optimize_allocation_proxy_va_roadmap_ops_cho_service(ops):
    with pytest.raises(YofinaError) as e:  # chưa cấu hình Lambda forecast
        ops.optimize_allocation_result(U, horizon_months=3)
    assert e.value.code == ErrorCode.FORECAST_UNAVAILABLE
    ok = load_json(FIXTURES / "tools" / "optimize_allocation.ok_infeasible.json")
    seen: list[Any] = []

    class Forecast:
        def optimize_allocation(self, user_id, args):
            seen.append((user_id, dict(args)))
            return ok

    ops.svc.forecast = Forecast()
    assert (
        ops.optimize_allocation_result(U, horizon_months=3, goals=None, shock_id="om_mot_tuan")
        == ok
    )
    assert seen == [(U, {"horizon_months": 3, "shock_id": "om_mot_tuan"})]  # bỏ None
    # roadmap_ops(service): dựng một lần, nhớ trên service; test thay kho bằng `service.roadmap_repo`
    svc = SimpleNamespace(repo=SimpleNamespace(db=None))
    fake_repo = FakeRoadmapRepo()
    svc.roadmap_repo = fake_repo
    first = roadmap_ops(svc)
    assert first is roadmap_ops(svc) and first.repo is fake_repo


def test_trang_thai_ban_moi_theo_ly_do_khop_hop_dong():
    assert status_for_new_version("initial", False) == "active"
    assert status_for_new_version("step_edited", True) == "active"
    for code in (
        "behavior_changed",
        "goal_changed",
        "income_changed",
        "forecast_drift",
        "user_request",
    ):
        assert status_for_new_version(code, True) == "proposed"
        assert status_for_new_version(code, False) == "active"


# =====================================================================================================
# Seed persona (phần thuần; nạp vào DB ở local_pg)
# =====================================================================================================
def test_seed_minh_dung_dinh_dang_va_quy_chieu_nhat_quan():
    from yofina_core.money import format_vnd
    from yofina_core.roadmap import RoadmapDraft
    from yofina_ledger import roadmap_seed as rs

    seed = rs.load_seed("minh")
    assert seed is not None and seed["persona"] == "minh"
    assert rs.load_seed("khong_co_persona") is None
    assert (
        rs.load_seed("../minh") is None and rs.load_seed("") is None and rs.load_seed(None) is None
    )
    assert "DỮ LIỆU SEED" in seed["nguon"]  # nguồn của con số được ghi rõ
    versions = seed["versions"]
    assert [v["version"] for v in versions] == [1, 2, 3]
    assert [v["reason_code"] for v in versions] == ["initial", "step_edited", "behavior_changed"]
    first_steps = {s["step_id"] for p in versions[0]["phases"] for s in p["steps"]}
    assert (
        versions[1]["edit"]["step_id"] in first_steps
        and set(versions[0]["decisions"]) <= first_steps
    )
    flag = seed["behavior_flag"]
    assert flag["old_weekly_vnd"] != flag["new_weekly_vnd"] and flag["jar"] == "an_uong"
    for v in (versions[0], versions[2]):
        phases = rs._resolve_phases(v["phases"], TODAY)
        draft = RoadmapDraft.model_validate(
            {
                "reason_code": v["reason_code"],
                "based_on_version": None if v["reason_code"] == "initial" else 2,
                "behavior_flag_id": str(uuid.uuid4())
                if v["reason_code"] == "behavior_changed"
                else None,
                "feasibility": v["feasibility"],
                "goals": [],
                "alternatives": [],
                "phases": phases,
            },
            strict=False,
        )
        for ph in draft.phases:
            for st in ph.steps:
                if st.amount_vnd and st.kind in ("set_aside", "cut_spending"):
                    assert format_vnd(st.amount_vnd) in st.title, (
                        st.step_id
                    )  # số trong tiêu đề khớp số tiền của bước
                if st.action and st.action.tool == "move_between_jars":
                    assert st.action.params == {
                        "from_jar": st.jar_code, "to_jar": st.to_jar_code, "amount_vnd": st.amount_vnd,
                    }  # fmt: skip
                if st.action and st.action.tool == "schedule_nudge":
                    assert (
                        st.action.params["fire_on"] == st.due_date
                    )  # `fire_on_day` đã đổi thành ngày ISO
        assert phases[0]["start_date"] == TODAY.isoformat()  # ngày tính từ ngày neo
    # tiêu đề v1 và v3 của cùng một bước khác nhau ở đúng chỗ seed muốn (số tiền bù Ăn uống đổi qua v2 rồi về lại)
    v3 = {s["step_id"]: s for p in versions[2]["phases"] for s in p["steps"]}
    assert (
        v3["bu_an_uong"]["amount_vnd"] == 150_000
        and "danh_cho_du_phong" in v3
        and "cat_giai_tri" not in v3
    )


def test_project_goal_chieu_muc_tieu_theo_muc_danh_moi_thang():
    from yofina_ledger import roadmap_seed as rs

    jar = {"code": "du_lich", "name": "Du lịch", "color_key": "teal", "icon_key": "plane",
           "goal_vnd": 6_000_000, "goal_date": date(2027, 4, 1)}  # fmt: skip
    # còn thiếu 4.200.000 ₫, hạn còn 131 ngày
    ok = rs.project_goal(jar, 1_800_000, 1_000_000, TODAY)
    assert ok["on_track"] is True and ok["shortfall_vnd"] == 0
    assert ok["projected_date"] == "2027-03-27" and ok["target_date"] == "2027-04-01"
    assert ok["monthly_needed_vnd"] == 961_833 and ok["jar"]["code"] == "du_lich"
    late = rs.project_goal(jar, 1_800_000, 700_000, TODAY)
    assert late["on_track"] is False and late["projected_date"] == "2027-05-20"
    assert late["shortfall_vnd"] == 1_143_334 and late["monthly_needed_vnd"] == 961_833
    done = rs.project_goal(jar, 6_500_000, 1, TODAY)  # đã đủ tiền
    assert (
        done["on_track"] is True
        and done["monthly_needed_vnd"] == 0
        and done["projected_date"] == TODAY.isoformat()
    )
    nodate = rs.project_goal({**jar, "goal_date": None}, 1_800_000, 1_000_000, TODAY)
    assert nodate["on_track"] is True and "target_date" not in nodate
