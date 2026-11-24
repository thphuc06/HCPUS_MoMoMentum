"""Ý định `knowledge` (trích dẫn biểu phí, không RAG): router -> `knowledge___get_fee_schedule` -> khối `citation` dựng từ chính các
trường nguồn của dòng phí (`build_citation`) -> câu trả lời dựng bằng mã với số của bảng phí. Gateway giả với fixture hợp đồng."""

from __future__ import annotations

import json
import re

from agent_helpers import (
    FakeTools,
    blocks_of,
    check_agui_order,
    fixture,
    make_llm,
    mcp_ok,
    route_response,
    run_turn,
    types,
)
from yofina_agent.fee_citation import answer_text, select_fees
from yofina_agent.tools import classify_result

from yofina_core import blocks as B


def ok(payload):
    return lambda args: classify_result("x", mcp_ok(payload))


def turn_with(question, payload, *, monkeypatch, topic=None):
    # loại phí do router trích (fee_topic), không đoán bằng cụm từ trên chữ
    llm = make_llm([route_response(intent="knowledge", fee_topic=topic)])
    events, tools, writer = run_turn(
        question,
        llm=llm,
        tools=FakeTools({"get_fee_schedule": ok(payload)}),
        monkeypatch=monkeypatch,
    )
    return events, tools, writer, llm


def text_of(events):
    return "".join(e.delta for e in events if e.type.value == "TEXT_MESSAGE_CONTENT")


def citations(events):
    return [b for b in blocks_of(events) if b["type"] == "citation"]


def test_phi_dich_vu_moi_thang_co_so_tu_bang_va_trich_dan_dung_nguon(monkeypatch):
    payload = fixture("get_fee_schedule.ok.json")
    fee = payload["data"]["fees"][0]
    events, tools, writer, (_, client, _) = turn_with(
        "Phí dịch vụ Trả sau mỗi tháng là bao nhiêu, nguồn ở đâu?", payload, monkeypatch=monkeypatch, topic="monthly"
    )
    check_agui_order(events)
    assert [e.tool_call_name for e in events if e.type.value == "TOOL_CALL_START"] == [
        "knowledge___get_fee_schedule"
    ]
    assert tools.calls == [("get_fee_schedule", {})]
    (cit,) = citations(events)
    B.CitationBlock.model_validate(cit)
    (item,) = cit["data"]["items"]
    assert item["fee_types"] == ["monthly_service_fee"]
    assert (item["source_name"], item["source_url"], item["effective_from"]) == (
        fee["source_name"],
        fee["source_url"],
        fee["effective_from"],
    )
    assert item["excerpt"] == fee["condition_note"]  # chép từ bảng, model không viết
    assert (
        cit["source"]["tool"] == "knowledge___get_fee_schedule"
        and cit["source"]["app_date"] == payload["app_date"]
    )
    assert "amount_vnd" not in json.dumps(cit)  # khối không mang số tiền
    t = types(events)
    assert t.index("ACTIVITY_SNAPSHOT") < t.index("TOOL_CALL_RESULT")
    text = text_of(events)
    assert (
        "33.000 ₫ mỗi tháng" in text
        and "hiệu lực từ 31/03/2026" in text
        and fee["source_name"] in text
    )
    assert writer.calls == [] and len(client.calls) == 1  # số và nguồn không qua model


def test_hoi_phi_tra_cham_ma_bang_khong_co_thi_khong_bia(monkeypatch):
    payload = fixture("get_fee_schedule.ok.json")
    events, _, _, _ = turn_with(
        "Trả sau có phí trả chậm không? Nguồn ở đâu?", payload, monkeypatch=monkeypatch, topic="late"
    )
    check_agui_order(events)
    text = text_of(events)
    assert "chưa có phí trả chậm" in text and "không đưa số hay nguồn cho khoản đó" in text
    # mọi con số trong câu là số của bảng phí (số tiền, ngày hiệu lực)
    assert set(re.findall(r"\d+(?:\.\d+)*", text)) <= {"33.000", "31", "03", "2026"}
    (cit,) = citations(events)
    returned = {f["fee_type"] for f in payload["data"]["fees"]}
    assert {t for i in cit["data"]["items"] for t in i["fee_types"]} <= returned


def test_dieu_khoan_ngoai_bon_loai_phi_thi_noi_chua_co_nguon(monkeypatch):
    # mọi chủ đề không có dòng phí khớp (router: fee_topic="other") đi chung một câu, không có nhánh riêng cho "miễn phí"
    payload = fixture("get_fee_schedule.ok.json")
    events, _, _, _ = turn_with(
        "Điều khoản hoàn phí khi hủy Trả sau nằm ở đâu?",
        payload,
        monkeypatch=monkeypatch,
        topic="other",
    )
    text = text_of(events)
    assert "chưa có khoản bạn hỏi" in text and "không đưa số hay nguồn cho khoản đó" in text and "33.000 ₫" in text
    (cit,) = citations(events)
    assert [i["source_url"] for i in cit["data"]["items"]] == [
        payload["data"]["fees"][0]["source_url"]
    ]


def test_hai_nguon_chi_trich_dan_loai_phi_duoc_hoi(monkeypatch):
    payload = fixture("get_fee_schedule.ok_hai_nguon.json")
    events, _, _, _ = turn_with(
        "Nếu quá hạn thì Trả sau tính phí gì?", payload, monkeypatch=monkeypatch, topic="late"
    )
    (cit,) = citations(events)
    (item,) = cit["data"]["items"]
    assert item["fee_types"] == ["late_payment_fee"] and item["source_url"].endswith(
        "dieu-khoan-tra-sau"
    )
    text = text_of(events)
    assert "0 ₫ một lần" in text and "01/11/2026" in text and "33.000" not in text
    # không hỏi loại cụ thể: trích dẫn mọi nguồn
    events, _, _, _ = turn_with(
        "Biểu phí Trả sau gồm những gì, nguồn ở đâu?", payload, monkeypatch=monkeypatch
    )
    (cit,) = citations(events)
    assert [i["fee_types"] for i in cit["data"]["items"]] == [
        ["monthly_service_fee"],
        ["late_payment_fee"],
    ]


def test_khong_co_bieu_phi_la_notice_info_khong_co_trich_dan(monkeypatch):
    payload = fixture("get_fee_schedule.error_not_found.json")
    events, _, _, _ = turn_with("Phí Trả sau bao nhiêu?", payload, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert citations(events) == []
    (notice,) = [b for b in blocks_of(events) if b["type"] == "notice"]
    assert (notice["data"]["kind"], notice["data"]["code"]) == ("info", "FEE_SCHEDULE_NOT_FOUND")


def test_chon_dong_phi_theo_thuoc_tinh_dong_khong_theo_ma():
    fees = fixture("get_fee_schedule.ok_hai_nguon.json")["data"]["fees"]
    assert select_fees(fees, ["late"]) == (["late_payment_fee"], [])
    assert select_fees(fees, ["monthly"]) == (["monthly_service_fee"], [])
    assert select_fees(fees, ["per_transaction"]) == ([], ["per_transaction"])
    assert select_fees(fees, ["other"]) == ([], ["other"])
    assert select_fees(fees, []) == (["monthly_service_fee", "late_payment_fee"], [])
    data = fixture("get_fee_schedule.ok.json")["data"]
    assert answer_text(data, [], ["late"]).startswith(
        "Biểu phí Trả sau (mô phỏng) mình có hiện chưa có phí trả chậm"
    )


def test_router_co_tham_so_loai_phi_khop_tap_cua_ma():
    from typing import get_args

    from yofina_agent.router import ROUTER_SYSTEM
    from yofina_agent.schemas import IntentParams

    topics = get_args(get_args(IntentParams.model_fields["fee_topic"].annotation)[0])
    assert set(topics) == {"monthly", "per_transaction", "once", "late", "other"}
    assert "fee_topic" in ROUTER_SYSTEM
