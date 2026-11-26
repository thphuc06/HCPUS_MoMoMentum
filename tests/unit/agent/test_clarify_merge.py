"""Ghép câu trả lời (chip hoặc câu gõ) của khối `clarify` với câu đang chờ bằng mã: tham số đã có không mất qua lượt hỏi lại.

Lỗi phase 3 (đi cảnh 2, tiêu chí 4): "Chuyển 250 nghìn cho người nhận demo có ổn không?" -> hỏi hũ nguồn -> bấm chip hũ -> agent lại
hỏi số tiền, vì router (model) trả `amount_vnd` null cho câu "Hũ Hóa đơn" và mã chỉ trông vào model nhớ.

V3 (#39): mã chỉ ghép khi router nói câu này trả lời câu hỏi đang chờ (`answers_pending`) hoặc câu đúng là chip của câu hỏi mã đã
đặt, không theo độ dài câu (trước đây "tối đa 6 từ"); câu trả lời chỉ điền ô đã hỏi; yêu cầu mới, dù ngắn, không kế thừa ô của câu cũ.
Router giả, không gọi model. Các câu "diễn đạt khác" số 6, 7, 8 của báo cáo rà soát RR ở cuối tệp.
"""

from __future__ import annotations

from typing import Any

import pytest
from agent_helpers import blocks_of, check_agui_order, make_llm, route_response, run_turn
from test_infer_pay_jar import DEMO_8, _calls, _tools, _types
from yofina_agent import notices
from yofina_agent.clarify import PAY_QUESTION, UNKNOWN_PROMPT, is_asking, recognize_prompt
from yofina_agent.router import ROUTER_SYSTEM, merge_pending, pending_params
from yofina_agent.schemas import ClarifyChipIn, ClarifyRequest, IntentParams, IntentResult
from yofina_agent.textutil import parse_amount_vnd
from yofina_agent.turn import _readable_amount_chip

ASK = "Chuyển 250 nghìn cho người nhận demo có ổn không?"
JAR_Q = notices.CLARIFY["pay_jar"]["question"]  # fallback_text của khối clarify (frontend gửi trong lịch sử)
AMOUNT_Q = notices.CLARIFY["amount"]["question"]
JARS = ("Hóa đơn", "Giải trí", "Nghĩa vụ", "Ăn uống")


def _msgs(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"id": f"m{i}", "role": role, "content": text} for i, (role, text) in enumerate(pairs, start=1)]


def _ir(intent: str, **params: object) -> IntentResult:
    return IntentResult(intent=intent, params=IntentParams(**params), confidence=0.9, needs_clarification=False)  # type: ignore[arg-type]


def _pending(*pairs: tuple[str, str]) -> dict[str, Any] | None:
    return pending_params(list(pairs), jar_names=JARS)


# --- router: cờ có cấu trúc thay cho ngưỡng số từ --------------------------------------------------------
def test_router_tra_co_answers_pending_dung_sai_hoac_null():
    assert IntentParams(answers_pending=True).answers_pending is True
    assert IntentParams(answers_pending=False).answers_pending is False
    for bad in ("true", 1, None, "có"):
        assert IntentParams(answers_pending=bad).answers_pending is None  # type: ignore[arg-type]


def test_prompt_router_mo_ta_answers_pending_theo_nghia_khong_theo_do_dai():
    """Nghĩa của cờ (true, false, null) ở mô tả của trường trong schema, một chỗ (#39); lời nhắc hệ thống nói cách GHÉP câu trả lời và
    cách xử lý yêu cầu mới, không định nghĩa lại cờ."""
    from yofina_core.llm import bedrock_json_schema

    rule = next(line for line in ROUTER_SYSTEM.splitlines() if "answers_pending" in line and "<cau_moi>" in line)
    assert "answers_pending=true" in rule and "answers_pending=false" in rule and "mô tả của trường" in rule
    assert "dù câu ngắn hay dài" in rule and "kể cả câu rất ngắn" in rule
    assert "KHÔNG lấy số tiền, cách trả (funding)" in rule
    described = bedrock_json_schema(IntentResult)["properties"]["params"]["properties"]["answers_pending"]["description"]
    assert "true nếu" in described and "false nếu" in described and "Null khi" in described
    assert "Null khi" not in rule  # không định nghĩa cờ hai lần


# --- nhận ra câu hỏi mã đã đặt ----------------------------------------------------------------------------
def test_cau_hoi_ma_dat_duoc_nhan_ra_o_da_hoi_va_chip():
    pay = recognize_prompt(JAR_Q)
    assert pay is not None and pay.keys == ("jar_text",)
    assert pay.chip("Hũ Hóa đơn", JARS) == {"jar_text": "Hóa đơn"}
    assert pay.chip("Hũ Quỹ lạ", JARS) is None and pay.chip("hũ hóa đơn nhé", JARS) is None
    unified = recognize_prompt(f"{PAY_QUESTION}\n")
    assert unified is not None and unified.keys == ("jar_text", "funding")
    assert unified.chip("Trả bằng Trả sau (mô phỏng)", JARS) == {"funding": "credit"}
    amount = recognize_prompt(AMOUNT_Q)
    assert amount is not None and amount.keys == ("amount_vnd",) and amount.chip("1 triệu") == {}
    unknown_jar = recognize_prompt(notices.UNKNOWN_JAR_QUESTION.format(name="Quỹ nhà"))
    assert unknown_jar is not None and unknown_jar.keys == ("jar_text",)
    # câu hỏi router tự đặt: không nhận ra, nhưng vẫn là tin đang chờ trả lời
    assert recognize_prompt("Bạn định chi bao nhiêu?") is None and is_asking("Bạn định chi bao nhiêu?")
    assert not is_asking("Đã xong.")


# --- đọc câu đang chờ từ lịch sử ---------------------------------------------------------------------------
def test_cau_dang_cho_lay_so_tien_va_nguoi_nhan_tu_cau_dau():
    p = _pending(("user", ASK), ("assistant", JAR_Q))
    assert p is not None
    assert (p["amount_vnd"], p["label"], p["_intent"]) == (250000, "người nhận demo", "affordability")
    assert p["_prompt"] is recognize_prompt(JAR_Q)


def test_khong_co_cau_hoi_cua_yofina_thi_khong_co_cau_dang_cho():
    assert pending_params([("user", ASK)]) is None
    assert pending_params([("user", ASK), ("assistant", "Đã xong.")]) is None
    assert pending_params([]) is None


def test_chuoi_hoi_lai_nhieu_luot_gop_tham_so_cu_truoc_moi_sau():
    p = _pending(
        ("user", "Nếu mua tai nghe 1,2 triệu thì sao"),
        ("assistant", notices.CLARIFY["funding_source"]["question"]),
        ("user", "Trả bằng tiền trong hũ"),  # chip của câu hỏi cách trả
        ("assistant", JAR_Q),
    )
    assert p is not None
    assert (p["amount_vnd"], p["label"], p["_intent"], p["funding"]) == (1200000, "tai nghe", "what_if", "jar")


def test_cau_hoi_giu_bo_khoan_truoc_khong_di_duong_nay():
    marker = "Bạn vẫn giữ ý định đó chứ?"
    msgs = [("user", "Nếu mua dép 300 nghìn từ hũ Giải trí thì sao"), ("assistant", f"Trước đó ... {marker} ...")]
    assert pending_params(msgs, marker_excluded=marker) is None


def test_cau_hoi_router_tu_dat_van_co_cau_dang_cho_khong_ro_o():
    p = _pending(("user", ASK), ("assistant", "Bạn định chi khoản này lúc nào?"))
    assert p is not None and p["_prompt"] is UNKNOWN_PROMPT and p["amount_vnd"] == 250000


# --- cổng ghép: cờ của router hoặc chip -----------------------------------------------------------------------
def test_router_noi_tra_loi_thi_ghep_giu_so_tien():
    pending = _pending(("user", ASK), ("assistant", JAR_Q))
    merged = merge_pending(_ir("affordability", jar_text="Hóa đơn", answers_pending=True), "hóa đơn nha", pending)
    p = merged.params
    assert (merged.intent, p.amount_vnd, p.jar_text, p.label) == ("affordability", 250000, "Hóa đơn", "người nhận demo")
    assert merged.clarify is None


def test_bam_chip_hu_thi_ghep_du_router_khong_noi_la_cau_tra_loi():
    pending = _pending(("user", ASK), ("assistant", JAR_Q))
    merged = merge_pending(_ir("affordability"), "Hũ Hóa đơn", pending)  # router để trống cờ và cả hũ
    assert (merged.params.amount_vnd, merged.params.jar_text) == (250000, "Hóa đơn")  # tên hũ đúng của chip


@pytest.mark.parametrize("flag", [False, None])
def test_cau_moi_ngan_khong_ke_thua_o_cua_cau_cu(flag):
    """Câu số 6 của báo cáo RR: sau câu Trả sau 900k đang chờ hỏi hũ, câu mới ngắn (5 từ) là khoản kiểm tra mới 55.000 ₫."""
    pending = _pending(("user", "Mua giày 900k bằng Trả sau thì sao?"), ("assistant", JAR_Q))
    assert pending is not None and pending["funding"] == "credit" and pending["amount_vnd"] == 900000
    routed = _ir("affordability", amount_vnd=55000, answers_pending=flag)
    assert merge_pending(routed, "cafe 55k co sao ko", pending) is routed


def test_cau_tra_loi_dai_van_ghep_khi_router_noi_la_cau_tra_loi():
    """Câu số 8 của báo cáo RR (9 từ, quá ngưỡng 6 từ cũ): dùng hũ Giải trí với số tiền của câu trước."""
    pending = _pending(("user", "Gửi mẹ 2 triệu tiền thuốc có ổn không"), ("assistant", JAR_Q))
    routed = _ir("affordability", jar_text="hu giai tri", answers_pending=True)
    merged = merge_pending(routed, "thoi lay tien hu giai tri tra giup minh nha", pending)
    assert (merged.intent, merged.params.amount_vnd, merged.params.jar_text) == ("affordability", 2_000_000, "hu giai tri")


def test_cau_tra_loi_chi_dien_o_da_hoi():
    """Hỏi hũ mà câu trả lời có thêm số tiền: mã chỉ điền ô hũ từ câu trả lời; số tiền giữ của câu đang chờ (router nói khác thì router
    thắng, vì router đọc câu mới)."""
    pending = _pending(("user", ASK), ("assistant", JAR_Q))
    merged = merge_pending(_ir("affordability", answers_pending=True), "lấy hũ Giải trí 500k nhé", pending)
    assert (merged.params.amount_vnd, merged.params.jar_text) == (250000, "giai tri")
    told = merge_pending(_ir("affordability", amount_vnd=500000, answers_pending=True), "lấy hũ Giải trí 500k nhé", pending)
    assert told.params.amount_vnd == 500000


def test_hoi_so_tien_thi_cau_tra_loi_dien_so_tien():
    pending = _pending(("user", ASK), ("assistant", AMOUNT_Q))
    assert merge_pending(_ir("affordability", answers_pending=True), "300 nghìn", pending).params.amount_vnd == 300000
    merged = merge_pending(_ir("affordability", amount_vnd=400000, answers_pending=True), "400 nghìn", pending)
    assert merged.params.amount_vnd == 400000  # router đọc câu mới cũng thắng


def test_tra_loi_cau_hoi_hu_la_khong_giu_ten_hu_cu():
    ask = "Chuyển 250 nghìn từ hũ Quỹ cưới cho bạn có ổn không"
    pending = _pending(("user", ask), ("assistant", notices.UNKNOWN_JAR_QUESTION.format(name="quy cuoi")))
    assert pending is not None and pending["jar_text"] == "quy cuoi"
    merged = merge_pending(_ir("affordability"), "Hũ Nghĩa vụ", pending)
    assert (merged.params.jar_text, merged.params.amount_vnd) == ("Nghĩa vụ", 250000)


def test_router_xep_cau_tra_loi_la_tra_so_du_thi_van_ve_y_dinh_dang_cho():
    pending = _pending(("user", ASK), ("assistant", JAR_Q))
    merged = merge_pending(_ir("lookup", lookup_kind="balance", jar_text="Hóa đơn"), "Hũ Hóa đơn", pending)
    assert merged.intent == "affordability" and merged.params.amount_vnd == 250000
    assert merged.params.jar_text == "Hóa đơn" and merged.params.lookup_kind is None


def test_cau_moi_tu_du_nghia_hoac_chitchat_thi_khong_ghep():
    pending = _pending(("user", ASK), ("assistant", JAR_Q))
    new_q = _ir("what_if", amount_vnd=5000000, scenario_kind="one_time_purchase", label="du lịch", answers_pending=False)
    assert merge_pending(new_q, "Nếu 10 ngày sau tôi đi du lịch 5 triệu thì sao", pending) is new_q
    chat = _ir("chitchat", answers_pending=True)
    assert merge_pending(chat, "cảm ơn", pending) is chat


def test_cau_hoi_lai_cua_router_cho_o_da_du_thi_bo():
    pending = _pending(("user", ASK), ("assistant", JAR_Q))
    wrong = IntentResult(
        intent="affordability",
        params=IntentParams(jar_text="Hóa đơn"),
        confidence=0.9,
        needs_clarification=True,
        clarify=ClarifyRequest(slot="amount", question="Khoản này bao nhiêu tiền?", chips=[]),
    )
    merged = merge_pending(wrong, "Hũ Hóa đơn", pending)
    assert merged.clarify is None and merged.needs_clarification is False and merged.params.amount_vnd == 250000


# --- cả lượt (router giả, không gọi model thật) -------------------------------------------------
def test_luot_tra_loi_chip_hu_chay_kiem_tra_voi_so_tien_cua_cau_dau(monkeypatch):
    # router giả mô phỏng đúng lỗi đã gặp: "Hũ Hóa đơn" ra affordability nhưng amount_vnd null (và không nói là câu trả lời)
    llm = make_llm([route_response(intent="affordability", jar_text="Hóa đơn")])
    msgs = _msgs(("user", ASK), ("assistant", JAR_Q), ("user", "Hũ Hóa đơn"))
    events, tools, _ = run_turn(None, llm=llm, monkeypatch=monkeypatch, messages=msgs)
    check_agui_order(events)
    assert [b for b in blocks_of(events) if b["type"] == "clarify"] == []  # không hỏi lại số tiền
    (args,) = [a for name, a in tools.calls if name == "affordability_check"]
    assert args["amount_vnd"] == 250000 and args["jar"] == "hoa_don" and args["label"] == "người nhận demo"


def test_luot_dau_van_hoi_hu_nguon_va_chip_la_hu_that(monkeypatch):
    llm = make_llm([route_response(intent="affordability", amount_vnd=250000, label="người nhận demo")])
    events, tools, _ = run_turn(ASK, llm=llm, monkeypatch=monkeypatch)
    (clarify,) = [b for b in blocks_of(events) if b["type"] == "clarify"]
    assert clarify["data"]["slot"] == "jar" and "affordability_check" not in [c[0] for c in tools.calls]


MOTHER_Q = "Gửi mẹ 2 triệu tiền thuốc có ổn không"  # câu số 7 của báo cáo RR


def test_rr7_rr8_tra_loi_dai_dung_hu_giai_tri_giu_so_tien_cua_cau_truoc(monkeypatch):
    llm = make_llm([route_response(intent="affordability", amount_vnd=2_000_000, label="mẹ")])
    first, _, _ = run_turn(MOTHER_Q, llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch)
    (ask,) = blocks_of(first)
    assert ask["type"] == "clarify" and ask["data"]["slot"] == "jar"
    labels = [c["label"] for c in ask["data"]["chips"]]
    assert labels[: len(DEMO_8)] == [j["name"] for j in DEMO_8]  # mọi hũ của ví
    reply = "thoi lay tien hu giai tri tra giup minh nha"
    llm = make_llm([route_response(intent="affordability", jar_text="hu giai tri", answers_pending=True)])
    msgs = _msgs(("user", MOTHER_Q), ("assistant", ask["fallback_text"]), ("user", reply))
    events, tools, _ = run_turn(None, llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch, messages=msgs)
    check_agui_order(events)
    (args,) = _calls(tools, "affordability_check")
    assert args["amount_vnd"] == 2_000_000 and args["jar"] == "giai_tri"
    assert "clarify" not in _types(events)


def test_cau_tra_loi_khong_co_co_va_khong_phai_chip_thi_khong_ghep(monkeypatch):
    """Router không nói là câu trả lời và câu không phải chip: mã không đoán, chạy đúng như router trả (thiếu số tiền thì hỏi số tiền)."""
    llm = make_llm([route_response(intent="affordability", jar_text="hu giai tri")])
    msgs = _msgs(("user", MOTHER_Q), ("assistant", JAR_Q), ("user", "thoi lay tien hu giai tri tra giup minh nha"))
    events, tools, _ = run_turn(None, llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch, messages=msgs)
    assert _types(events) == ["clarify"] and blocks_of(events)[0]["data"]["slot"] == "amount"
    assert not _calls(tools, "affordability_check")


@pytest.mark.parametrize("flag", [False, None])
def test_rr6_cau_cafe_sau_cau_tra_sau_la_khoan_moi(monkeypatch, flag):
    msgs = _msgs(("user", "Mua giày 900k bằng Trả sau thì sao?"), ("assistant", JAR_Q), ("user", "cafe 55k co sao ko"))
    llm = make_llm([route_response(intent="affordability", amount_vnd=55_000, spend_jar_code="an_uong", answers_pending=flag)])
    events, tools, _ = run_turn(None, llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch, messages=msgs)
    check_agui_order(events)
    (args,) = _calls(tools, "affordability_check")
    assert args == {"amount_vnd": 55_000, "jar": "an_uong"}  # không Trả sau, không 900k


# --- chip số tiền đọc được ----------------------------------------------------------------------
def test_chip_so_tien_so_tran_doi_sang_chu():
    c = _readable_amount_chip(ClarifyChipIn(label="250000", value="250000"))
    assert (c.label, c.value) == ("250 nghìn", "250 nghìn")
    c = _readable_amount_chip(ClarifyChipIn(label="1,2 triệu", value="1200000"))
    assert (c.label, c.value) == ("1,2 triệu", "1,2 triệu")
    c = _readable_amount_chip(ClarifyChipIn(label="1250000", value="1250000"))
    assert c.value == "1.250.000 ₫" and parse_amount_vnd(c.value) == 1250000  # "1,3 triệu" sẽ đổi số tiền
    keep = ClarifyChipIn(label="Hóa đơn", value="Hũ Hóa đơn")
    assert _readable_amount_chip(keep) == keep


def test_parser_hieu_ca_chu_va_dinh_dang_tien():
    for text in ("250 nghìn", "250000", "250.000 ₫", "250.000\u00a0₫", "250k", "250.000đ"):
        assert parse_amount_vnd(text) == 250000, text
    assert parse_amount_vnd("1,2 triệu") == parse_amount_vnd("1.200.000 ₫") == 1200000


def test_khoi_clarify_so_tien_phat_chip_chu(monkeypatch):
    llm = make_llm(
        [
            route_response(
                intent="affordability",
                clarify={"slot": "amount", "question": "Bạn định chi bao nhiêu?", "chips": [{"label": "250000", "value": "250000"}]},
            )
        ]
    )
    events, _, _ = run_turn("mình chi khoản này có ổn không", llm=llm, monkeypatch=monkeypatch)
    (clarify,) = [b for b in blocks_of(events) if b["type"] == "clarify"]
    assert [(c["label"], c["value"]) for c in clarify["data"]["chips"]] == [("250 nghìn", "250 nghìn")]
