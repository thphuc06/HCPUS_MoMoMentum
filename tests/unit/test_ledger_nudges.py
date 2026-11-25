"""Bản tin chủ động (FR13, phase 5 luồng B): cổng giá trị (`proactive.select_nudge`, `gather_candidates`), sở thích giờ im lặng (điểm móc
cho bộ nhớ), `GET /nudges/today` và `POST /nudges/{nudge_id}/feedback` với bảng `nudges` giả trong bộ nhớ. Đồng hồ cố định 10/12/2026
03:00 UTC (10 giờ sáng giờ Việt Nam), offset -19: ngày mô phỏng 21/11/2026."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from conftest import OPENAPI_URI, build_registry
from jsonschema import Draft202012Validator
from ledger_fakes import http_event, make_service

from yofina_core.blocks import ProactiveCardBlock
from yofina_core.wallet import NUDGE_GATE_ORDER
from yofina_ledger import proactive as P
from yofina_ledger.repo import RESET_DELETES
from yofina_ledger.rest_api import handle_http

MINH = "sub-minh"
TODAY = date(2026, 11, 21)
NID = "2d4e6f80-1a3c-4e5b-8d7f-9a1b3c5d7e9f"
TRACE = "8f3a21c94b7e4d0aa1c25e6f7b8c9d01"
REGISTRY = build_registry()


def api(name: str) -> Draft202012Validator:
    return Draft202012Validator({"$ref": f"{OPENAPI_URI}#/components/schemas/{name}"}, registry=REGISTRY)


def cand(kind: str, score: float = 1.5, **kw: Any) -> P.GateCandidate:
    return P.GateCandidate(kind=kind, score=score, title=f"Việc {kind}", body="Lý do.", **kw)


# =====================================================================================================
# Cổng giá trị
# =====================================================================================================
def test_thu_tu_uu_tien_dung_de_xuat_cua_hoc():
    assert NUDGE_GATE_ORDER[:5] == ("runout_warning", "obligation_due", "roadmap_proposed", "review_needed", "resilience_drop")
    all_kinds = [cand(k) for k in reversed(NUDGE_GATE_ORDER)]
    d = P.select_nudge(all_kinds)
    assert d.chosen.kind == "runout_warning" and d.gate == {"rank": 1, "score": 1.5, "threshold": 1.0, "candidates": 6}
    assert [s["reason"] for s in d.suppressed] == ["lower_rank"] * 5


def test_toi_da_mot_viec_va_chi_khi_vuot_nguong():
    d = P.select_nudge([cand("runout_warning", 0.5), cand("review_needed", 0.9)])
    assert d.chosen is None and d.gate is None
    assert d.suppressed == [
        {"kind": "runout_warning", "reason": "below_threshold"},
        {"kind": "review_needed", "reason": "below_threshold"},
    ]
    d = P.select_nudge([cand("runout_warning", 0.5), cand("review_needed", 1.2)])
    assert d.chosen.kind == "review_needed" and d.gate["rank"] == 4
    assert d.suppressed == [{"kind": "runout_warning", "reason": "below_threshold"}]


def test_it_nhac_loai_nay_ha_dung_mot_bac():
    assert P.effective_order(["runout_warning"])[:3] == ["obligation_due", "runout_warning", "roadmap_proposed"]
    d = P.select_nudge([cand("runout_warning"), cand("obligation_due"), cand("roadmap_proposed")], demoted=["runout_warning"])
    assert d.chosen.kind == "obligation_due" and d.gate["rank"] == 1
    assert {"kind": "runout_warning", "reason": "demoted"} in d.suppressed
    # hạ một bậc chứ không xuống cuối: vẫn thắng loại xếp sau đó hai bậc
    d = P.select_nudge([cand("runout_warning"), cand("roadmap_proposed")], demoted=["runout_warning"])
    assert d.chosen.kind == "runout_warning" and d.gate == {**d.gate, "rank": 2, "demoted": True}


def test_cung_loai_lay_diem_cao_hon():
    d = P.select_nudge([cand("runout_warning", 1.2, jar_code="di_lai"), cand("runout_warning", 2.0, jar_code="an_uong")])
    assert d.chosen.jar_code == "an_uong" and d.suppressed == []


JARS = [
    {"code": "an_uong", "name": "Ăn uống", "kind": "spending", "balance_vnd": 80_000},
    {"code": "hoa_don", "name": "Hóa đơn", "kind": "spending", "balance_vnd": 150_000},
    {"code": "giai_tri", "name": "Giải trí", "kind": "spending", "balance_vnd": 20_000},
]


def gather(**over: Any) -> list[P.GateCandidate]:
    base: dict[str, Any] = dict(
        today=TODAY,
        jars=JARS,
        forecasts={},
        essential_jar_codes=("an_uong", "di_lai", "hoa_don"),
        avg_daily_spend={"an_uong": 95_000},
        obligations=[],
        roadmap=None,
        review_ask=None,
        resilience_today=None,
        resilience_before=None,
        behavior=None,
        recent_kinds={},
    )
    return P.gather_candidates(**{**base, **over})


def test_ung_vien_hu_thiet_yeu_can_truoc_ky_luong():
    f = {"status": "short", "runout_date": "2026-11-28", "payday_date": "2026-12-05"}
    out = gather(forecasts={"an_uong": f, "giai_tri": f})
    (c,) = out  # giải trí không thiết yếu
    assert c.kind == "runout_warning" and c.status == "short" and c.value_vnd == 95_000 * 7
    assert c.title == "Hũ Ăn uống dự kiến cạn ngày 28/11" and "7 ngày" in c.body and "05/12" in c.body
    (tight,) = gather(forecasts={"an_uong": {"status": "tight", "payday_date": "2026-12-05"}})
    assert tight.score < 1.0  # sát thì chưa vượt ngưỡng


def test_ung_vien_hu_thua_khong_neu_ngay_can():
    """#25: hũ thưa (`runout_date_shown` sai) vẫn là ứng viên cạn trước kỳ lương nhưng chữ không có ngày cạn hay số ngày suy ra."""
    f = {"status": "short", "runout_date": "2026-11-28", "payday_date": "2026-12-05", "runout_date_shown": False,
         "show_probability": True, "p_shortfall": 0.62}  # fmt: skip
    (c,) = gather(forecasts={"an_uong": f})
    assert c.kind == "runout_warning" and c.status == "short" and c.value_vnd == 95_000 * 7
    assert c.title == "Hũ Ăn uống có thể cạn trước ngày lương"
    assert c.body == "Còn 80.000 ₫, còn 14 ngày tới kỳ lương 05/12. Khả năng hụt: 60%."
    (shown,) = gather(forecasts={"an_uong": {**f, "runout_date_shown": True}})
    assert shown.title == "Hũ Ăn uống dự kiến cạn ngày 28/11"


def test_ung_vien_tai_khoan_0_dong_khong_co_ban_tin_can_va_hu_het_tien_noi_da_het():
    """Lỗi P12-08 ở cổng bản tin: tài khoản chưa có tiền không nhận "dự kiến cạn … Còn 0 ₫"."""
    f = {"status": "short", "runout_date": TODAY.isoformat(), "payday_date": "2026-12-05"}
    empty = [{**j, "balance_vnd": 0} for j in JARS]
    assert gather(jars=empty, forecasts={"an_uong": f, "hoa_don": f}) == []
    funded = [{**JARS[0], "balance_vnd": 0}, *JARS[1:]]
    (c,) = gather(jars=funded, forecasts={"an_uong": f})
    assert c.kind == "runout_warning" and c.status == "short"
    assert c.title == "Hũ Ăn uống đã hết tiền" and "0 ₫" not in c.body and "05/12" in c.body


def test_ung_vien_nghia_vu_ba_ngay_ma_hu_khong_du():
    obs = [
        {"name": "Tiền điện", "amount_vnd": 375_000, "due_date": "2026-11-23", "pay_jar_code": "hoa_don", "status": "active"},
        {"name": "Internet", "amount_vnd": 100_000, "due_date": "2026-11-22", "pay_jar_code": "hoa_don", "status": "active"},
        {"name": "Netflix", "amount_vnd": 180_000, "due_date": "2026-11-25", "pay_jar_code": "giai_tri", "status": "active"},
    ]
    out = gather(obligations=obs)
    by_name = {c.title.split(" đến hạn")[0]: c for c in out}
    assert by_name["Tiền điện"].value_vnd == 225_000 and by_name["Tiền điện"].score > 1
    assert by_name["Internet"].score == 0.0  # hũ đủ tiền thì không nhắc
    assert "Netflix" not in by_name  # quá 3 ngày


def test_ung_vien_lo_trinh_hoi_gop_diem_tut_va_nhan_xet():
    out = gather(
        roadmap={"status": "proposed", "version": 4, "app_date": TODAY - timedelta(days=1), "reason_text": "Chi ăn uống tăng."},
        review_ask={"status": "open", "item_count": 3, "pending_total_vnd": 180_000},
        resilience_today={"band": "weak", "score": 30},
        resilience_before={"band": "fair", "score": 45},
        behavior={"ready": True, "insights": [{"headline": "Cuối tuần bạn chi 37% tổng chi.", "jar_code": "an_uong"}]},
    )
    kinds = {c.kind: c for c in out}
    assert list(kinds) == ["roadmap_proposed", "review_needed", "resilience_drop", "behavior_insight"]
    assert kinds["roadmap_proposed"].body == "Bản đề xuất phiên bản 4: Chi ăn uống tăng."
    assert kinds["review_needed"].value_vnd == 180_000 and kinds["review_needed"].score >= 1
    assert kinds["resilience_drop"].title.endswith("Yếu") and kinds["resilience_drop"].score == 1.0
    old = gather(roadmap={"status": "proposed", "version": 4, "app_date": TODAY - timedelta(days=30), "reason_text": "x"})
    assert old == []
    again = gather(behavior={"ready": True, "insights": [{"headline": "x"}]}, recent_kinds={"behavior_insight": 1})
    assert again[0].score == 0.0  # vừa nhắc trong 7 ngày


# =====================================================================================================
# Sở thích giờ im lặng (điểm móc cho bộ nhớ dài hạn)
# =====================================================================================================
@pytest.mark.parametrize(
    ("texts", "quiet"),
    [
        (["Đừng nhắc mình buổi sáng"], ((5, 11),)),
        (["dung nhac minh buoi sang nhe"], ((5, 11),)),
        (["Đừng nhắc tôi buổi sáng, ưu tiên hũ Du lịch"], ((5, 11),)),  # "tôi" không phải "tối"
        (["Không muốn nhận thông báo vào buổi tối và ban đêm"], ((0, 5), (18, 22), (22, 24))),
        (["Mình hay dùng Trả sau buổi tối"], ()),  # không phải lời dặn đừng nhắc
        (["Nhắc mình buổi sáng nhé"], ()),
        ([], ()),
    ],
)
def test_so_thich_tu_cau_trong_bo_nho(texts, quiet):
    assert P.preferences_from_texts(texts).quiet_hours == quiet


def test_doc_so_thich_qua_diem_moc_nguon_loi_thi_khong_co_so_thich():
    class Broken:
        def nudge_preferences(self, user_id):
            raise TimeoutError

    class Memory:
        def __init__(self):
            self.asked: list[str] = []

        def nudge_preferences(self, user_id):
            self.asked.append(user_id)
            return P.preferences_from_texts(["đừng nhắc buổi sáng"])

    assert P.read_preferences(None, "u") is P.NO_PREFERENCES
    assert P.read_preferences(Broken(), "u") is P.NO_PREFERENCES
    mem = Memory()
    prefs = P.read_preferences(mem, "u-1")
    assert mem.asked == ["u-1"] and prefs.is_quiet(10) and not prefs.is_quiet(11)


# =====================================================================================================
# REST /nudges/*
# =====================================================================================================
class FakeNudgesDb:
    """Bảng `nudges` và `feedback` giả cho các câu lệnh của `nudges_rest` và `proactive.insert_gate_nudge`."""

    def __init__(self) -> None:
        self.nudges: dict[str, dict[str, Any]] = {}
        self.feedback: dict[tuple, dict[str, Any]] = {}
        self.uid: str | None = None

    @contextmanager
    def transaction(self, user_id: str):
        self.uid = user_id
        yield self

    def query(self, sql: str, params: dict[str, Any], *, max_rows: int | None = None):
        assert sql == P.SQL_TODAY_NUDGE
        return [
            dict(n)
            for n in self.nudges.values()
            if n["user_id"] == params["uid"] and n["fire_on"] == params["d"] and n["status"] != "cancelled"
        ][:1]

    def execute(self, sql: str, params: dict[str, Any]):
        assert params["uid"] == self.uid  # mọi câu lệnh chạy trong transaction của đúng người dùng
        if sql.startswith("INSERT INTO nudges"):
            if any(n["user_id"] == params["uid"] and n["fire_on"] == params["d"] for n in self.nudges.values()):
                return []
            self.nudges[params["id"]] = {
                "id": params["id"], "user_id": params["uid"], "kind": params["kind"], "fire_on": params["d"],
                "jar_code": params["jar_code"], "title": params["title"], "body": params["body"],
                "value_vnd": params["value"], "gate_reason": json.loads(params["gate"]), "status": "scheduled",
                "outcome": None, "outcome_at": None, "trace_id": params["trace_id"],
            }  # fmt: skip
            return [{"id": params["id"]}]
        if sql.startswith("SELECT kind, trace_id FROM nudges"):
            n = self.nudges.get(params["id"])
            return [{"kind": n["kind"], "trace_id": n["trace_id"]}] if n and n["user_id"] == params["uid"] else []
        if sql.startswith("SELECT * FROM app_set_nudge_outcome"):
            n = self.nudges.get(params["id"])
            if not n or n["user_id"] != params["uid"]:
                return []
            if n["outcome"] != params["outcome"]:
                n["outcome"], n["outcome_at"] = params["outcome"], datetime(2026, 12, 10, 3, 5, tzinfo=UTC)
            if params["outcome"] == "dismissed":
                n["status"] = "dismissed"
            return [{"id": n["id"], "outcome": n["outcome"], "outcome_at": n["outcome_at"]}]
        if sql.startswith("INSERT INTO feedback"):
            key = (params["uid"], params["trace_id"], params["block_id"], params["option_id"])
            self.feedback[key] = {"decision": params["decision"], "reason": params["reason"]}
            return []
        raise AssertionError(f"câu lệnh ngoài dự kiến: {sql}")


def gate_decision(kind: str = "roadmap_proposed") -> P.GateDecision:
    return P.select_nudge([cand(kind, 1.6, value_vnd=210_000, status="tight"), cand("review_needed", 1.2)])


@pytest.fixture()
def env():
    svc, repo, clock = make_service()
    repo.db = FakeNudgesDb()
    return svc, repo.db, clock


def get_today(svc, sub: str = MINH) -> dict[str, Any]:
    out = handle_http(http_event("GET", "/nudges/today", sub=sub), svc)
    assert out["statusCode"] == 200, out["body"]
    body = json.loads(out["body"])
    api("NudgeTodayResponse").validate(body)
    return body


def feedback(svc, nudge_id: str, body: Any, sub: str = MINH) -> tuple[int, dict[str, Any]]:
    out = handle_http(
        http_event("POST", f"/nudges/{nudge_id}/feedback", sub=sub, body=body, path_params={"nudge_id": nudge_id}), svc
    )
    return out["statusCode"], json.loads(out["body"])


def test_chua_co_ban_tin_thi_trong(env):
    svc, _, _ = env
    assert get_today(svc) == {"app_date": "2026-11-21", "suppressed": []}


def test_ban_tin_hom_nay_co_the_va_nudge_id(env):
    svc, db, _ = env
    assert P.insert_gate_nudge(db, MINH, nudge_id=NID, app_date=TODAY, decision=gate_decision(), trace_id=TRACE)
    assert not P.insert_gate_nudge(db, MINH, nudge_id=NID.replace("2d", "3d"), app_date=TODAY, decision=gate_decision(), trace_id=TRACE)
    body = get_today(svc)
    assert body["nudge"] == {
        "nudge_id": NID, "kind": "roadmap_proposed", "app_date": "2026-11-21", "title": "Việc roadmap_proposed",
        "reason": "Lý do.", "value_vnd": 210_000, "gate": {"rank": 3, "score": 1.6, "threshold": 1.0, "candidates": 2},
    }  # fmt: skip
    card = ProactiveCardBlock.model_validate(body["card"])
    assert card.data.nudge_id == NID and card.data.kind == "roadmap_proposed" and card.data.status == "tight"
    assert card.id == f"proactive_card:{TRACE}:roadmap_proposed" and card.source.tool == "rest:GET /nudges/today"
    assert [a.kind for a in card.data.actions] == ["open_roadmap", "snooze", "mute_kind"]
    assert body["suppressed"] == [{"kind": "review_needed", "reason": "lower_rank"}]
    # người khác không thấy bản tin này
    assert get_today(svc, "sub-lan") == {"app_date": "2026-11-21", "suppressed": []}


def test_gio_im_lang_trong_so_thich_an_the(env):
    svc, db, clock = env
    P.insert_gate_nudge(db, MINH, nudge_id=NID, app_date=TODAY, decision=gate_decision(), trace_id=TRACE)

    class Memory:
        def nudge_preferences(self, user_id):
            return P.preferences_from_texts(["Đừng nhắc mình buổi sáng"] if user_id == MINH else [])

    svc.nudge_preferences = Memory()  # điểm móc của luồng bộ nhớ
    body = get_today(svc)  # 10 giờ sáng giờ Việt Nam
    assert "nudge" not in body and "card" not in body
    assert body["suppressed"][0] == {"kind": "roadmap_proposed", "reason": "quiet_hours"}
    clock.advance(4 * 3600)  # 14 giờ: hết buổi sáng
    assert get_today(svc)["nudge"]["nudge_id"] == NID


def test_phan_hoi_ban_tin_ghi_outcome_va_feedback_idempotent(env):
    svc, db, _ = env
    P.insert_gate_nudge(db, MINH, nudge_id=NID, app_date=TODAY, decision=gate_decision(), trace_id=TRACE)
    status, body = feedback(svc, NID, {"outcome": "less_like_this"})
    assert status == 200
    api("NudgeFeedbackResponse").validate(body)
    assert body["nudge_id"] == NID and body["outcome"] == "less_like_this"
    first = body["recorded_at"]
    assert feedback(svc, NID, {"outcome": "less_like_this"})[1]["recorded_at"] == first
    key = (MINH, TRACE, f"proactive_card:{TRACE}:roadmap_proposed", "roadmap_proposed")
    assert db.feedback[key] == {"decision": "rejected", "reason": "less_like_this"}
    feedback(svc, NID, {"outcome": "acted", "reason": "Đã xem lộ trình"})
    assert db.feedback[key] == {"decision": "accepted", "reason": "Đã xem lộ trình"}


def test_da_bo_qua_thi_hom_nay_khong_hien_lai(env):
    svc, db, _ = env
    P.insert_gate_nudge(db, MINH, nudge_id=NID, app_date=TODAY, decision=gate_decision(), trace_id=TRACE)
    feedback(svc, NID, {"outcome": "snoozed"})
    assert "card" not in get_today(svc)


@pytest.mark.parametrize(
    ("nudge_id", "body", "status", "code"),
    [
        (NID, {"outcome": "la"}, 400, "PARAMS_INVALID"),
        (NID, {"outcome": "acted", "user_id": "sub-lan"}, 400, "PARAMS_INVALID"),
        ("khong-phai-uuid", {"outcome": "acted"}, 404, "NUDGE_NOT_FOUND"),
        ("5d4e6f80-1a3c-4e5b-8d7f-9a1b3c5d7e9f", {"outcome": "acted"}, 404, "NUDGE_NOT_FOUND"),
    ],
)
def test_phan_hoi_sai_hoac_khong_co(env, nudge_id, body, status, code):
    svc, db, _ = env
    P.insert_gate_nudge(db, MINH, nudge_id=NID, app_date=TODAY, decision=gate_decision(), trace_id=TRACE)
    got, out = feedback(svc, nudge_id, body)
    assert (got, out["error"]["code"]) == (status, code)


def test_ban_tin_cua_nguoi_khac_la_404(env):
    svc, db, _ = env
    P.insert_gate_nudge(db, MINH, nudge_id=NID, app_date=TODAY, decision=gate_decision(), trace_id=TRACE)
    got, out = feedback(svc, NID, {"outcome": "dismissed"}, sub="sub-lan")
    assert (got, out["error"]["code"]) == (404, "NUDGE_NOT_FOUND")
    assert db.nudges[NID]["outcome"] is None


@pytest.mark.parametrize("kind", NUDGE_GATE_ORDER)
def test_the_cua_moi_loai_dung_hop_dong(kind):
    row = {
        "id": NID, "kind": kind, "title": "Tiêu đề", "body": "Lý do.", "jar_code": "an_uong",
        "gate_reason": {"rank": 1, "score": 1.0, "threshold": 1.0, "candidates": 1, "status": "short"}, "trace_id": TRACE,
    }  # fmt: skip
    card = P.gate_card(row, as_of=datetime(2026, 12, 10, 3, 0, tzinfo=UTC), app_date=TODAY)
    Draft202012Validator(
        {"$ref": "https://contracts.yofina.invalid/blocks/proactive_card.schema.json"}, registry=REGISTRY
    ).validate(json.loads(card.model_dump_json(exclude_none=True)))
    assert card.data.nudge_id == NID and card.data.status == "short"


def test_dat_lai_demo_xoa_ho_so_hanh_vi():
    tables = [s.split()[2] for s in RESET_DELETES]
    assert "behavior_profiles" in tables and tables.index("behavior_profiles") < tables.index("jars")
