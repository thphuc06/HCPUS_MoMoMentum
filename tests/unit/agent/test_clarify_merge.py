"""Ghép câu trả lời cụt (chip của khối `clarify`) với câu đang chờ bằng mã: tham số đã có không mất qua lượt hỏi lại.

Lỗi phase 3 (đi cảnh 2, tiêu chí 4): "Chuyển 250 nghìn cho người nhận demo có ổn không?" -> hỏi hũ nguồn -> bấm chip hũ -> agent lại
hỏi số tiền, vì router (model) trả `amount_vnd` null cho câu cụt "Hũ Hóa đơn" và mã chỉ trông vào model nhớ.
"""

from __future__ import annotations

from agent_helpers import blocks_of, check_agui_order, make_llm, route_response, run_turn
from yofina_agent.router import is_fragment, merge_pending, pending_params
from yofina_agent.schemas import ClarifyChipIn, ClarifyRequest, IntentParams, IntentResult
from yofina_agent.textutil import parse_amount_vnd
from yofina_agent.turn import _readable_amount_chip

ASK = "Chuyển 250 nghìn cho người nhận demo có ổn không?"
JAR_Q = "Bạn định trả bằng tiền của hũ nào?"  # fallback_text của khối clarify (frontend gửi trong lịch sử)


def _msgs(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [
        {"id": f"m{i}", "role": role, "content": text}
        for i, (role, text) in enumerate(pairs, start=1)
    ]


def _ir(intent: str, **params: object) -> IntentResult:
    return IntentResult(
        intent=intent, params=IntentParams(**params), confidence=0.9, needs_clarification=False
    )  # type: ignore[arg-type]


# --- đọc câu đang chờ từ lịch sử ---------------------------------------------------------------
def test_cau_dang_cho_lay_so_tien_va_nguoi_nhan_tu_cau_dau():
    p = pending_params([("user", ASK), ("assistant", JAR_Q)])
    assert p is not None
    assert (
        p["amount_vnd"] == 250000
        and p["label"] == "người nhận demo"
        and p["_intent"] == "affordability"
    )


def test_khong_co_cau_hoi_cua_yofina_thi_khong_co_cau_dang_cho():
    assert pending_params([("user", ASK)]) is None
    assert pending_params([("user", ASK), ("assistant", "Đã xong.")]) is None
    assert pending_params([]) is None


def test_chuoi_hoi_lai_nhieu_luot_gop_tham_so_cu_truoc_moi_sau():
    msgs = [
        ("user", "Nếu mua tai nghe 1,2 triệu thì sao"),
        ("assistant", "Bạn định trả bằng tiền trong hũ hay bằng Trả sau (mô phỏng)?"),
        ("user", "Trả bằng tiền trong hũ"),
        ("assistant", JAR_Q),
    ]
    p = pending_params(msgs)
    assert (
        p is not None
        and p["amount_vnd"] == 1200000
        and p["label"] == "tai nghe"
        and p["_intent"] == "what_if"
    )


def test_cau_hoi_giu_bo_khoan_truoc_khong_di_duong_nay():
    marker = "Bạn vẫn giữ ý định đó chứ?"
    msgs = [
        ("user", "Nếu mua dép 300 nghìn từ hũ Giải trí thì sao"),
        ("assistant", f"Trước đó ... {marker} ..."),
    ]
    assert pending_params(msgs, marker_excluded=marker) is None


def test_cau_cut_va_cau_tu_du_nghia():
    for t in ("Hũ Hóa đơn", "250 nghìn", "250.000 ₫", "Trả sau", "Trả bằng tiền trong hũ"):
        assert is_fragment(t), t
    for t in (ASK, "Nếu 10 ngày sau tôi đi du lịch 5 triệu thì sao", "Số dư các hũ của mình", ""):
        assert not is_fragment(t), t


# --- ghép -------------------------------------------------------------------------------------
def test_ghep_giu_so_tien_khi_router_quen():
    pending = pending_params([("user", ASK), ("assistant", JAR_Q)])
    merged = merge_pending(_ir("affordability", jar_text="Hóa đơn"), "Hũ Hóa đơn", pending)
    p = merged.params
    assert (merged.intent, p.amount_vnd, p.jar_text, p.label) == (
        "affordability",
        250000,
        "Hóa đơn",
        "người nhận demo",
    )
    assert merged.clarify is None


def test_tham_so_moi_co_gia_tri_thi_ghi_de_so_cu():
    pending = pending_params([("user", ASK), ("assistant", "Khoản này khoảng bao nhiêu tiền?")])
    merged = merge_pending(_ir("affordability"), "300 nghìn", pending)
    assert merged.params.amount_vnd == 300000  # mã đọc câu mới thắng câu đang chờ
    merged = merge_pending(_ir("affordability", amount_vnd=400000), "400 nghìn", pending)
    assert merged.params.amount_vnd == 400000  # router đọc câu mới cũng thắng


def test_router_xep_cau_cut_la_tra_so_du_thi_van_ve_y_dinh_dang_cho():
    pending = pending_params([("user", ASK), ("assistant", JAR_Q)])
    merged = merge_pending(
        _ir("lookup", lookup_kind="balance", jar_text="Hóa đơn"), "Hũ Hóa đơn", pending
    )
    assert merged.intent == "affordability" and merged.params.amount_vnd == 250000
    assert (
        merged.params.jar_text == "hoa don"
    )  # mã đọc chữ hũ (bỏ dấu); ánh xạ ra mã hũ vẫn bằng dữ liệu tool


def test_cau_moi_tu_du_nghia_hoac_chitchat_thi_khong_ghep():
    pending = pending_params([("user", ASK), ("assistant", JAR_Q)])
    new_q = _ir("what_if", amount_vnd=5000000, scenario_kind="one_time_purchase", label="du lịch")
    assert merge_pending(new_q, "Nếu 10 ngày sau tôi đi du lịch 5 triệu thì sao", pending) is new_q
    chat = _ir("chitchat")
    assert merge_pending(chat, "cảm ơn", pending) is chat


def test_cau_hoi_lai_cua_router_cho_o_da_du_thi_bo():
    pending = pending_params([("user", ASK), ("assistant", JAR_Q)])
    wrong = IntentResult(
        intent="affordability",
        params=IntentParams(jar_text="Hóa đơn"),
        confidence=0.9,
        needs_clarification=True,
        clarify=ClarifyRequest(slot="amount", question="Khoản này bao nhiêu tiền?", chips=[]),
    )
    merged = merge_pending(wrong, "Hũ Hóa đơn", pending)
    assert (
        merged.clarify is None
        and merged.needs_clarification is False
        and merged.params.amount_vnd == 250000
    )


# --- cả lượt (router giả, không gọi model thật) -------------------------------------------------
def test_luot_tra_loi_chip_hu_chay_kiem_tra_voi_so_tien_cua_cau_dau(monkeypatch):
    # router giả mô phỏng đúng lỗi đã gặp: câu cụt "Hũ Hóa đơn" ra affordability nhưng amount_vnd null
    llm = make_llm([route_response(intent="affordability", jar_text="Hóa đơn")])
    msgs = _msgs(("user", ASK), ("assistant", JAR_Q), ("user", "Hũ Hóa đơn"))
    events, tools, _ = run_turn(None, llm=llm, monkeypatch=monkeypatch, messages=msgs)
    check_agui_order(events)
    assert [b for b in blocks_of(events) if b["type"] == "clarify"] == []  # không hỏi lại số tiền
    (args,) = [a for name, a in tools.calls if name == "affordability_check"]
    assert (
        args["amount_vnd"] == 250000
        and args["jar"] == "hoa_don"
        and args["label"] == "người nhận demo"
    )


def test_luot_dau_van_hoi_hu_nguon_va_chip_la_hu_that(monkeypatch):
    llm = make_llm(
        [route_response(intent="affordability", amount_vnd=250000, label="người nhận demo")]
    )
    events, tools, _ = run_turn(ASK, llm=llm, monkeypatch=monkeypatch)
    (clarify,) = [b for b in blocks_of(events) if b["type"] == "clarify"]
    assert clarify["data"]["slot"] == "jar" and "affordability_check" not in [
        c[0] for c in tools.calls
    ]


# --- chip số tiền đọc được ----------------------------------------------------------------------
def test_chip_so_tien_so_tran_doi_sang_chu():
    c = _readable_amount_chip(ClarifyChipIn(label="250000", value="250000"))
    assert (c.label, c.value) == ("250 nghìn", "250 nghìn")
    c = _readable_amount_chip(ClarifyChipIn(label="1,2 triệu", value="1200000"))
    assert (c.label, c.value) == ("1,2 triệu", "1,2 triệu")
    c = _readable_amount_chip(ClarifyChipIn(label="1250000", value="1250000"))
    assert (
        c.value == "1.250.000 ₫" and parse_amount_vnd(c.value) == 1250000
    )  # "1,3 triệu" sẽ đổi số tiền
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
                clarify={
                    "slot": "amount",
                    "question": "Bạn định chi bao nhiêu?",
                    "chips": [{"label": "250000", "value": "250000"}],
                },
            )
        ]
    )
    events, _, _ = run_turn("mình chi khoản này có ổn không", llm=llm, monkeypatch=monkeypatch)
    (clarify,) = [b for b in blocks_of(events) if b["type"] == "clarify"]
    assert [(c["label"], c["value"]) for c in clarify["data"]["chips"]] == [
        ("250 nghìn", "250 nghìn")
    ]
