"""Đường lùi của harness khi router trả thiếu hay sai (#39, 26/11): mã kiểm phần kiểm được bằng dữ liệu, phần còn lại lùi an toàn (hỏi
lại đúng một câu, hoặc đường cũ), không ghi gì sai và không lộ lỗi thô cho người dùng. Router giả, không gọi model.

- Hũ model chọn và hũ người dùng nêu là hai thứ khác nhau: `spend_jar_named` (trường có cấu trúc của router) nói người dùng có tự nêu
  hũ không. Model ghi tên hũ nó chọn vào `jar_text` mà nói người dùng không nêu hũ nào thì mã bỏ bản chép đó, lượt tính theo
  `spend_jar_code` và người dùng thấy dòng "Tính theo hũ X" (đo ở #39: Claude Haiku 4.5 vẫn ghi tên hũ đã chọn vào jar_text).
- Số tiền VND router trả phải là số có trong hội thoại (mã đọc được bằng `textutil.extract_amounts`); không có thì dùng số duy nhất
  của câu mới, hoặc bỏ để hỏi lại (đo ở #39: Nova 2 Lite đọc "45 nghin" thành 450.000).
- Kết quả bị cắt ở trần token, và các trường mới trả sai (mã hũ ngoài danh sách, cờ sai kiểu) không làm hỏng lượt.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from agent_helpers import (
    blocks_of,
    check_agui_order,
    make_llm,
    route_response,
    run,
    run_turn,
)
from test_infer_pay_jar import DEMO_8, _calls, _inferred_notice, _tools, _types
from test_live_pay_jar_chips import _events_of
from yofina_agent import notices
from yofina_agent.router import checked_route, route, router_jar_list
from yofina_agent.schemas import IntentParams, IntentResult

from yofina_core.llm import bedrock_json_schema

JARS = router_jar_list(DEMO_8)
TRIP = "toi muon di choi xa thang sau tam 3 trieu co du khong"  # câu của test, không trùng câu eval hay câu trên app


def _ir(intent: str = "affordability", **params: Any) -> IntentResult:
    return IntentResult(intent=intent, params=IntentParams(**params), confidence=0.9, needs_clarification=False)  # type: ignore[arg-type]


# --- hũ người dùng nêu và hũ model chọn: trường có cấu trúc ---------------------------------------------------------------
def test_schema_co_co_spend_jar_named_canh_spend_jar_code():
    props = bedrock_json_schema(IntentResult, require_all=False)["properties"]["params"]["properties"]
    keys = list(props)
    assert keys.index("spend_jar_named") == keys.index("spend_jar_code") + 1
    assert props["spend_jar_named"]["type"] == ["boolean", "null"]
    described = props["spend_jar_named"]["description"]
    assert "true" in described and "false" in described and "spend_jar_code" in described


@pytest.mark.parametrize("bad", ["false", 0, "không", ["x"]])
def test_spend_jar_named_sai_kieu_thi_coi_nhu_khong_noi(bad):
    assert IntentParams(spend_jar_named=bad).spend_jar_named is None  # type: ignore[arg-type]


def test_model_chep_ten_hu_da_chon_vao_jar_text_thi_ma_bo_ban_chep(caplog):
    caplog.set_level(logging.INFO)
    r = _ir(amount_vnd=3_000_000, jar_text="Du lịch", spend_jar_code="muc_tieu", spend_jar_named=False)
    out = checked_route(r, TRIP, "", JARS)
    assert out.params.jar_text is None and out.params.spend_jar_code == "muc_tieu"
    (event,) = _events_of(caplog, "router_jar_text_inferred")
    assert event["spend_jar_code"] == "muc_tieu"


@pytest.mark.parametrize(
    ("named", "jar_text", "code"),
    [
        pytest.param(True, "Du lịch", "muc_tieu", id="nguoi-dung-neu"),
        pytest.param(None, "Du lịch", "muc_tieu", id="model-khong-noi"),
        pytest.param(False, "hũ Ăn uống", "muc_tieu", id="chu-chi-hu-khac"),
        pytest.param(False, "Quỹ cưới", "muc_tieu", id="chu-khong-ra-hu-nao"),
    ],
)
def test_chi_bo_jar_text_khi_dung_la_ban_chep_cua_hu_model_chon(named, jar_text, code):
    """Người dùng nêu hũ, model không nói, hay chữ chỉ một hũ khác hũ model chọn: giữ chữ (tên hũ người dùng nêu thắng hũ router chọn;
    chữ không ra hũ nào thì luồng hỏi hũ lạ như cũ)."""
    r = _ir(amount_vnd=3_000_000, jar_text=jar_text, spend_jar_code=code, spend_jar_named=named)
    assert checked_route(r, TRIP, "", JARS).params.jar_text == jar_text


def test_khong_phai_khoan_chi_thi_khong_dung_toi_jar_text():
    r = _ir("roadmap", roadmap_action="create", amount_vnd=3_000_000, jar_text="Du lịch", spend_jar_code="muc_tieu", spend_jar_named=False)
    assert checked_route(r, TRIP, "", JARS).params.jar_text == "Du lịch"


def test_luot_hu_model_chon_bi_chep_vao_jar_text_van_noi_ro_tinh_theo_hu_nao(monkeypatch):
    route_out = route_response(
        intent="affordability", amount_vnd=3_000_000, jar_text="Du lịch", spend_jar_code="muc_tieu", spend_jar_named=False
    )
    events, tools, _ = run_turn(TRIP, llm=make_llm([route_out]), tools=_tools(DEMO_8), monkeypatch=monkeypatch)
    check_agui_order(events)
    assert _calls(tools, "affordability_check")[0]["jar"] == "muc_tieu"
    notice = _inferred_notice(events)
    assert notice is not None and notice["title"] == "Tính theo hũ Du lịch"


def test_luot_nguoi_dung_neu_hu_thi_khong_them_dong_tinh_theo_hu(monkeypatch):
    route_out = route_response(
        intent="affordability", amount_vnd=600_000, jar_text="Chi hằng ngày", spend_jar_code="chi_hang_ngay", spend_jar_named=True
    )
    events, tools, _ = run_turn("lấy hũ Chi hằng ngày mua quạt 600k được không", llm=make_llm([route_out]), tools=_tools(DEMO_8), monkeypatch=monkeypatch)
    assert _calls(tools, "affordability_check")[0]["jar"] == "chi_hang_ngay"
    assert _inferred_notice(events) is None


# --- số tiền: số có trong hội thoại ----------------------------------------------------------------------------------------
def test_so_tien_khong_co_trong_cau_thi_dung_so_ma_doc_duoc(caplog):
    caplog.set_level(logging.INFO)
    r = _ir(amount_vnd=450_000, spend_jar_code="an_uong")
    out = checked_route(r, "sang nay uong ca phe 45 nghin co duoc khong", "", JARS)
    assert out.params.amount_vnd == 45_000
    (event,) = _events_of(caplog, "router_amount_ungrounded")
    assert event == {"event": "router_amount_ungrounded", "field": "amount_vnd", "action": "code_read"}  # không ghi số tiền vào log


@pytest.mark.parametrize(
    ("question", "history", "amount"),
    [
        pytest.param("mua tai nghe 1,2 triệu ổn không", "", 1_200_000, id="dung-so-cua-cau"),
        pytest.param("lấy hũ Giải trí nhé", "Người dùng: mua boardgame 850 nghìn có ổn không\nYofina: Bạn định trả bằng hũ nào?", 850_000, id="so-cua-cau-dang-cho"),
        pytest.param("mua quạt năm trăm nghìn ổn không", "", 500_000, id="ma-khong-doc-duoc-so-nao"),
    ],
)  # fmt: skip
def test_so_tien_co_can_cu_hoac_khong_kiem_duoc_thi_giu(question, history, amount):
    assert checked_route(_ir(amount_vnd=amount), question, history, JARS).params.amount_vnd == amount


def test_so_tien_khong_can_cu_ma_cau_co_nhieu_so_thi_bo_de_hoi_lai():
    out = checked_route(_ir(amount_vnd=700_000), "vé 350k, phí 20k, có ổn không", "", JARS)
    assert out.params.amount_vnd is None


def test_luong_cung_kiem_nhu_so_tien():
    out = checked_route(_ir("profile_update", salary_vnd=150_000_000), "luong cua minh 15 trieu", "", JARS)
    assert out.params.salary_vnd == 15_000_000


def test_luot_so_tien_khong_can_cu_thi_hoi_mot_cau_khong_kiem_tra(monkeypatch):
    route_out = route_response(intent="affordability", amount_vnd=700_000, spend_jar_code="giai_tri")
    events, tools, _ = run_turn("vé 350k, phí 20k, có ổn không", llm=make_llm([route_out]), tools=_tools(DEMO_8), monkeypatch=monkeypatch)
    check_agui_order(events)
    assert _types(events) == ["clarify"] and blocks_of(events)[0]["data"]["slot"] == "amount"
    assert blocks_of(events)[0]["data"]["question"].count("?") == 1
    assert not _calls(tools, "affordability_check")


def test_route_tra_ket_qua_da_kiem():
    """route() là chỗ duy nhất các bước kiểm chạy (lượt gọi rồi mới dùng giá trị): eval và lượt chat thấy cùng một kết quả."""
    llm, _, _ = make_llm([route_response(intent="affordability", amount_vnd=450_000, jar_text="Ăn uống", spend_jar_code="an_uong", spend_jar_named=False)])
    res = run(route(llm, "trua nay an bun 45 nghin", "", max_attempts=1, max_tokens=800, jars=JARS))
    assert (res.value.params.amount_vnd, res.value.params.jar_text, res.value.params.spend_jar_code) == (45_000, None, "an_uong")


# --- kết quả hỏng hay bị cắt: luật dự phòng, không lộ lỗi thô ------------------------------------------------------------------
def test_router_bi_cat_ca_hai_lan_thi_dung_luat_va_khong_lo_loi_tho(monkeypatch):
    cut = route_response(intent="lookup", lookup_kind="balance")
    cut["stopReason"] = "max_tokens"
    llm = make_llm([cut, cut])
    events, _, _ = run_turn("số dư các hũ", llm=llm, monkeypatch=monkeypatch)
    check_agui_order(events)
    assert len(llm[1].calls) == 2  # đúng router_max_attempts, không lặp thêm
    assert "jar_summary" in _types(events)  # luật dự phòng vẫn trả số dư
    shown = " ".join(str(b["data"].get("title", "")) + str(b["data"].get("message", "")) for b in blocks_of(events) if b["type"] == "notice")
    for raw in ("max_tokens", "StructuredOutputError", "Traceback", "route"):
        assert raw not in shown
    assert result_of(events)["intent"] == "lookup"


def result_of(events: list[Any]) -> dict[str, Any]:
    return events[-1].result


def test_co_answers_pending_sai_tren_yeu_cau_chuyen_tien_moi_van_phai_xac_nhan_so_moi(monkeypatch):
    """Cờ trả lời sai (router nói câu mới là câu trả lời cho câu hỏi hũ đang chờ): ô router đọc từ câu mới thắng ô của câu cũ, và lượt
    ghi vẫn chỉ ra khối xác nhận, không ghi gì khi người dùng chưa bấm."""
    from test_clarify_merge import ASK, JAR_Q, _msgs

    llm = make_llm(
        [
            route_response(
                intent="move", amount_vnd=100_000, from_jar_text="Giải trí", to_jar_text="Ăn uống", answers_pending=True
            )
        ]
    )
    msgs = _msgs(("user", ASK), ("assistant", JAR_Q), ("user", "chuyển 100 nghìn từ Giải trí sang Ăn uống"))
    events, tools, _ = run_turn(None, llm=llm, monkeypatch=monkeypatch, messages=msgs)
    check_agui_order(events)
    (args,) = _calls(tools, "move_between_jars")
    assert args == {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100_000}
    assert "confirm" in _types(events) and "receipt" not in _types(events)


def test_thong_bao_suy_giam_cua_router_la_chuoi_san_pham():
    """Chữ người dùng thấy khi router hỏng là chuỗi sản phẩm cố định (notices.DEGRADED), không chứa mã lỗi thô."""
    for title, message in notices.DEGRADED.values():
        for raw in ("Exception", "max_tokens", "Traceback"):
            assert raw not in title and raw not in message
