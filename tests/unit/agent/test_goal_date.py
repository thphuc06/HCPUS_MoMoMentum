"""Hạn mục tiêu lộ trình (V1, #39): router viết hạn thành đặc tả `date_spec`, mã tính ngày bằng `yofina_core.dates.resolve_date`.

Đặc tả cùng định nghĩa với đầu vào tool `knowledge___resolve_date` (schema sinh từ `dates.DateSpec`, không chép). Hàm chạy trong tiến
trình (không qua mạng); chỉ mốc ngày lương mới gọi tool qua Gateway vì lượt không có ngày lương đã khai. Hàm là nguồn tính duy nhất:
không còn phép đối chiếu "lệch 7 ngày" với cách đọc bằng mã. Cách đọc cụm chỉ hạn bằng mã (`textutil.parse_goal_date`, chỉ khi đọc
TRỌN cụm) chỉ là đường lùi khi router không trả đặc tả. Đặc tả sai, ngày đã qua, năm Tết ngoài bảng, hoặc không có gì đọc được thì hỏi
đúng một câu. Router giả, không gọi model. Câu số 10, 11 của báo cáo rà soát RR. Ngày mô phỏng của fixture là 21/11/2026.
"""

from __future__ import annotations

import json
import logging
from datetime import date

import pytest
from agent_helpers import (
    REPO,
    blocks_of,
    check_agui_order,
    fixture,
    make_llm,
    mcp_ok,
    route_response,
    run_turn,
    tool_response,
    types,
)
from test_live_pay_jar_chips import _events_of
from test_roadmap_create_turn import DEMO_JARS, answer_turn, calls_of, outline, roadmap_tools
from yofina_agent.clarify import GOAL_DATE_QUESTION, goal_jar_question
from yofina_agent.notices import GOAL_DATE_IS_TODAY
from yofina_agent.router import ROUTER_SYSTEM, build_router_prompt
from yofina_agent.schemas import DATE_SPEC_DESCRIPTION, IntentParams, IntentResult, date_spec_args
from yofina_agent.textutil import parse_goal_date
from yofina_agent.tools import classify_result

from yofina_core import dates as D
from yofina_core.llm import bedrock_json_schema

TODAY = date(2026, 11, 21)
RR10 = "Lập kế hoạch để dành 12 triệu đi Nhật, hạn đầu năm sau, đừng cắt hũ Giải trí"  # câu số 10 của báo cáo RR
RR11 = "muon de danh 5 trieu trong hai thang nua"  # câu số 11 của báo cáo RR
TOOL = next(t for t in json.loads((REPO / "contracts/tools/knowledge.json").read_text(encoding="utf-8")) if t["name"] == "resolve_date")


def _goal_turn(monkeypatch, question, *, tools=None, draft_jar="muc_tieu", **router):
    llm = make_llm([route_response(intent="roadmap", **router), tool_response("draft_roadmap", outline(draft_jar))])
    events, tools, _ = run_turn(question, llm=llm, tools=tools or roadmap_tools(DEMO_JARS), monkeypatch=monkeypatch)
    check_agui_order(events)
    return events, tools, llm


def _goals(tools):
    return calls_of(tools, "optimize_allocation")


def _create(date_text, date_spec=None, **extra):
    router = {"roadmap_action": "create", "amount_vnd": 3_000_000, "jar_text": "Du lịch", "date_text": date_text, **extra}
    if date_spec is not None:
        router["date_spec"] = date_spec
    return router


# --- trường có cấu trúc: cùng định nghĩa với đầu vào của tool ---------------------------------------------------------
def test_schema_date_spec_cua_router_dung_la_dau_vao_tool_tru_user_id():
    schema = bedrock_json_schema(IntentResult)["properties"]["params"]["properties"]["date_spec"]
    tool = TOOL["inputSchema"]["properties"]
    assert list(schema["properties"]) == [k for k in tool if k != "user_id"] == list(D.SPEC_FIELDS)
    for name, prop in schema["properties"].items():
        kinds = prop["type"] if isinstance(prop["type"], list) else [prop["type"]]
        assert tool[name]["type"] in kinds, name
    assert list(schema["properties"]["offset"]["properties"]) == list(tool["offset"]["properties"]) == list(D.OFFSET_UNITS)
    assert all(
        "number" in p["type"] and "string" not in p["type"] for p in schema["properties"]["offset"]["properties"].values()
    )
    assert schema["properties"]["anchor"]["enum"] == list(D.ANCHORS)
    assert schema["type"] == ["object", "null"] and DATE_SPEC_DESCRIPTION in schema["description"]


def test_date_spec_giu_dang_tho_bo_null_doi_tuong_rong_la_khong_co():
    raw = {"anchor": "today", "period": None, "offset": {"years": 1.5, "months": None}, "before": False}
    assert IntentParams(date_spec=raw).date_spec == {"anchor": "today", "offset": {"years": 1.5}}
    empty = {k: None for k in D.SPEC_FIELDS} | {"before": False, "offset": {u: None for u in D.OFFSET_UNITS}}
    assert IntentParams(date_spec=empty).date_spec is None
    assert IntentParams(date_spec="đầu năm sau").date_spec is None  # type: ignore[arg-type]
    # đặc tả sai không bắt router thử lại: giữ nguyên, phép tính báo lỗi lúc dùng
    assert IntentParams(date_spec={"anchor": "start_of"}).date_spec == {"anchor": "start_of"}
    assert date_spec_args({"anchor": "today", "offset": {"years": 1.5, "months": 2}}) == {
        "anchor": "today", "offset": {"years": 1.5, "months": 2},
    }  # fmt: skip


def test_prompt_router_mo_ta_date_spec_theo_nghia_khong_tu_tinh_ngay():
    assert "target_date" not in ROUTER_SYSTEM and "YYYY-MM-DD" not in ROUTER_SYSTEM
    assert "date_spec" in ROUTER_SYSTEM and "<ngay_hom_nay>" in ROUTER_SYSTEM
    for word in ("mốc", "trước", "kỳ"):
        assert word in DATE_SPEC_DESCRIPTION
    assert not any(q in DATE_SPEC_DESCRIPTION for q in "\"“”")  # không chép câu nói mẫu
    text = build_router_prompt("q", "Người dùng: a", None, TODAY)
    assert text.startswith("<ngay_hom_nay>2026-11-21</ngay_hom_nay>\n")


def test_router_nhan_ngay_mo_phong_cua_lan_doc_vi(monkeypatch):
    _, _, llm = _goal_turn(monkeypatch, RR11, roadmap_action="create", amount_vnd=5_000_000)
    prompt = llm[1].calls[0]["messages"][0]["content"][0]["text"]
    assert prompt.startswith("<ngay_hom_nay>2026-11-21</ngay_hom_nay>")


# --- đo nhanh: router giả trả đặc tả, hàm tính ngày ----------------------------------------------------------------
@pytest.mark.parametrize(
    ("said", "spec", "due"),
    [
        ("hai tháng nữa", {"anchor": "today", "offset": {"months": 2}}, "2027-01-21"),
        ("đầu quý sau", {"anchor": "start_of", "period": "quarter", "period_offset": 1}, "2027-01-01"),
        ("trước Tết", {"anchor": "lunar_new_year", "before": True}, "2027-02-05"),  # Tết Đinh Mùi 06/02/2027
        ("ngày 15 tháng sau", {"anchor": "date", "day": 15, "period": "month", "period_offset": 1}, "2026-12-15"),
        ("1 năm rưỡi nữa", {"anchor": "today", "offset": {"years": 1.5}}, "2028-05-21"),
        ("cuối năm", {"anchor": "end_of", "period": "year"}, "2026-12-31"),
    ],
)
def test_dac_ta_cua_router_thanh_han_bang_ham_trong_tien_trinh(monkeypatch, caplog, said, spec, due):
    caplog.set_level(logging.INFO)
    events, tools, _ = _goal_turn(monkeypatch, f"gom 3 triệu vào hũ Du lịch {said}", **_create(said, spec))
    assert _goals(tools) == [{"goals": [{"jar": "muc_tieu", "target_vnd": 3_000_000, "target_date": due}]}]
    assert [b["type"] for b in blocks_of(events)] == ["roadmap"]
    assert not calls_of(tools, "resolve_date")  # trong tiến trình, không qua Gateway
    (decided,) = _events_of(caplog, "goal_date")
    assert decided == {"event": "goal_date", "source": "spec", "anchor": spec["anchor"], "date": due}


def test_dac_ta_la_nguon_tinh_khong_doi_chieu_voi_cach_doc_bang_ma(monkeypatch):
    # luật đọc "cuối tháng sau" là 31/12/2026; đặc tả của router ra 01/03/2027: dùng đặc tả, không hỏi lại vì "lệch"
    router = _create("cuối tháng sau", {"anchor": "date", "day": 1, "month": 3})
    events, tools, _ = _goal_turn(monkeypatch, "gom 3 triệu cuối tháng sau", **router)
    assert _goals(tools) == [{"goals": [{"jar": "muc_tieu", "target_vnd": 3_000_000, "target_date": "2027-03-01"}]}]
    assert "clarify" not in [b["type"] for b in blocks_of(events)]


@pytest.mark.parametrize(
    ("said", "spec", "note"),
    [
        # kết quả ở quá khứ: lời của phép tính (nêu ngày đã tính) đứng trước câu hỏi, không tự dời
        ("đầu tháng này", {"anchor": "start_of", "period": "month"}, "Ngày tính ra là 01/11/2026, đã qua so với hôm nay (21/11/2026)."),
        # năm Tết ngoài bảng
        ("trước Tết 2040", {"anchor": "lunar_new_year", "lunar_year": 2040, "before": True}, "Chưa tra được ngày Tết năm 2040: lịch Tết của Yofina chỉ có các năm 2026–2035."),
        # hạn tính ra đúng hôm nay
        ("hôm nay", {"anchor": "today"}, GOAL_DATE_IS_TODAY.format(date="21/11/2026")),
    ],
)  # fmt: skip
def test_dac_ta_khong_tinh_duoc_thi_hoi_mot_cau_khong_lap(monkeypatch, said, spec, note):
    events, tools, _ = _goal_turn(monkeypatch, f"gom 3 triệu {said}", **_create(said, spec))
    (block,) = blocks_of(events)
    data = block["data"]
    assert block["type"] == "clarify" and data["slot"] == "date"
    assert data["question"] == f"{note} {GOAL_DATE_QUESTION}" and data["question"].count("?") == 1
    assert data["chips"] == []
    assert not _goals(tools) and not calls_of(tools, "save_roadmap")
    assert "TEXT_MESSAGE_CONTENT" not in types(events)


def test_dac_ta_sai_dang_thi_hoi_chip_la_ngay_ma_doc_duoc(monkeypatch):
    # start_of thiếu period: lỗi của router (PARAMS_INVALID), không nói lời kỹ thuật; ngày đọc trọn cụm bằng mã là chip ứng viên
    events, tools, _ = _goal_turn(monkeypatch, "gom 3 triệu trong 3 tháng", **_create("trong 3 tháng", {"anchor": "start_of"}))
    (block,) = blocks_of(events)
    data = block["data"]
    assert data["slot"] == "date" and data["question"] == GOAL_DATE_QUESTION
    assert [(c["label"], c["value"]) for c in data["chips"]] == [("Trước 21/02/2027", "Hạn 21/02/2027")]
    assert not _goals(tools)
    # bấm chip: router không nói gì thêm; chip là đặc tả của đúng ngày đó, mục tiêu của câu trước giữ nguyên
    messages = [
        {"id": "m1", "role": "user", "content": "gom 3 triệu vào hũ Du lịch trong 3 tháng"},
        {"id": "m2", "role": "assistant", "content": block["fallback_text"]},
        {"id": "m3", "role": "user", "content": "Hạn 21/02/2027"},
    ]
    llm = make_llm([route_response(intent="roadmap"), tool_response("draft_roadmap", outline("muc_tieu"))])
    events, tools, _ = run_turn(None, llm=llm, tools=roadmap_tools(DEMO_JARS), monkeypatch=monkeypatch, messages=messages)
    check_agui_order(events)
    assert _goals(tools) == [{"goals": [{"jar": "muc_tieu", "target_vnd": 3_000_000, "target_date": "2027-02-21"}]}]


# --- mốc ngày lương: lượt không có ngày lương đã khai, nên đi qua tool Gateway ---------------------------------------------
def test_moc_ngay_luong_goi_tool_gateway_mot_lan(monkeypatch):
    tools = roadmap_tools(DEMO_JARS)
    tools.results["resolve_date"] = lambda _a: classify_result("resolve_date", mcp_ok(fixture("resolve_date.ok_payday.json")))
    spec = {"anchor": "next_payday", "offset": {"months": 2}}
    events, tools, _ = _goal_turn(monkeypatch, "gom 3 triệu", tools=tools, **_create("hai kỳ lương nữa", spec))
    assert calls_of(tools, "resolve_date") == [{"anchor": "next_payday", "offset": {"months": 2}}]
    assert _goals(tools) == [{"goals": [{"jar": "muc_tieu", "target_vnd": 3_000_000, "target_date": "2027-02-05"}]}]
    names = [e.tool_call_name for e in events if e.type.value == "TOOL_CALL_START"]
    assert "knowledge___resolve_date" in names


def test_moc_ngay_luong_chua_khai_thi_hoi_mot_cau_kem_loi_cua_tool(monkeypatch):
    message = "Bạn chưa khai ngày nhận lương nên chưa tính được ngày lương kế tiếp."
    error = {"status": "ERROR", "code": "PROFILE_INCOMPLETE", "message": message}
    tools = roadmap_tools(DEMO_JARS)
    tools.results["resolve_date"] = lambda _a: classify_result("resolve_date", mcp_ok(error))
    events, tools, _ = _goal_turn(monkeypatch, "gom 3 triệu", tools=tools, **_create("kỳ lương tới", {"anchor": "next_payday"}))
    (block,) = [b for b in blocks_of(events) if b["type"] == "clarify"]
    assert block["data"]["question"] == f"{message} {GOAL_DATE_QUESTION}"
    assert not _goals(tools)


# --- đường lùi bằng mã: chỉ khi router không trả đặc tả, và chỉ khi đọc được trọn cụm ---------------------------------------
@pytest.mark.parametrize(
    ("text", "whole"),
    [
        ("trong 3 tháng", date(2027, 2, 21)),
        ("trong 5 tháng tới", None),  # luật đọc "5 tháng tới", còn chữ "trong": không dùng
        ("cuối tháng sau", date(2026, 12, 31)),
        ("31/12", date(2026, 12, 31)),
        ("đầu năm sau", None),  # luật chỉ hiểu "năm sau" (31/12 năm sau): không đọc trọn cụm thì không dùng
        ("ngày 15 tháng sau", None),
        ("hai tháng nữa", None),
        ("trước Tết", None),
    ],
)
def test_doc_han_bang_ma_chi_nhan_khi_doc_tron_cum(text, whole):
    assert parse_goal_date(text, TODAY, whole=True) == whole
    if text == "đầu năm sau":
        assert parse_goal_date(text, TODAY) == date(2027, 12, 31)  # cách đọc cũ (sai) vẫn còn cho người gọi khác


def test_router_khong_tra_dac_ta_thi_lui_ve_cach_doc_tron_cum(monkeypatch):
    _, tools, _ = _goal_turn(monkeypatch, "gom 3 triệu trong 3 tháng", **_create("trong 3 tháng"))
    assert _goals(tools) == [{"goals": [{"jar": "muc_tieu", "target_vnd": 3_000_000, "target_date": "2027-02-21"}]}]


# --- câu số 10: "hạn đầu năm sau" -----------------------------------------------------------------------------
def test_rr10_dac_ta_dau_nam_sau_khong_phai_31_12(monkeypatch):
    spec = {"anchor": "start_of", "period": "year", "period_offset": 1}
    events, tools, _ = _goal_turn(
        monkeypatch, RR10, roadmap_action="create", amount_vnd=12_000_000, jar_text="Du lịch", date_text="đầu năm sau", date_spec=spec
    )
    assert _goals(tools) == [{"goals": [{"jar": "muc_tieu", "target_vnd": 12_000_000, "target_date": "2027-01-01"}]}]
    assert [b["type"] for b in blocks_of(events)] == ["roadmap"]


def test_rr10_router_khong_tra_dac_ta_thi_hoi_mot_cau_khong_lap(monkeypatch):
    events, tools, _ = _goal_turn(
        monkeypatch, RR10, roadmap_action="create", amount_vnd=12_000_000, jar_text="Du lịch", date_text="đầu năm sau"
    )
    (block,) = blocks_of(events)
    assert block["type"] == "clarify" and block["data"]["slot"] == "date"
    assert block["data"]["question"] == GOAL_DATE_QUESTION and block["data"]["chips"] == []
    assert not _goals(tools) and not calls_of(tools, "save_roadmap")
    assert "TEXT_MESSAGE_CONTENT" not in types(events)  # không câu "dùng hạn đã khai, nếu có"


# --- câu số 11: "trong hai tháng nữa", rồi trả lời câu hỏi hũ ------------------------------------------------------
def test_rr11_hoi_hu_roi_lap_giu_so_tien_va_han(monkeypatch):
    spec = {"anchor": "today", "offset": {"months": 2}}
    first, _, _ = _goal_turn(
        monkeypatch, RR11, roadmap_action="create", amount_vnd=5_000_000, date_text="trong hai tháng nữa", date_spec=spec
    )
    (clarify,) = blocks_of(first)
    assert clarify["data"]["slot"] == "jar"
    assert clarify["data"]["question"] == goal_jar_question(5_000_000, date(2027, 1, 21))
    # lượt trả lời: router chỉ trích hũ (không nhắc lại số tiền hay hạn); mã đọc lại đúng hai giá trị từ câu hỏi
    events, tools, _, _ = answer_turn(
        monkeypatch, DEMO_JARS, clarify, "Dự phòng",
        route_response(intent="roadmap", jar_text="Hũ Dự phòng", answers_pending=True), draft_jar="du_phong",
    )  # fmt: skip
    check_agui_order(events)
    assert _goals(tools) == [{"goals": [{"jar": "du_phong", "target_vnd": 5_000_000, "target_date": "2027-01-21"}]}]
    assert len(calls_of(tools, "save_roadmap")) == 1
