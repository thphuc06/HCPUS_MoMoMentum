"""Chi phí đọc ví trước router (task 7, #39; báo cáo DD).

Từ d43a044 mọi lượt đọc `get_jar_balances` trước router (+0,2–0,4 s, thẻ tool "Số dư các hũ" cả ở lượt xã giao; Aurora ngủ thì lượt xã
giao cũng chờ). Nay: (a) frontend gửi danh sách hũ (mã, tên, kind, purpose) và ngày mô phỏng trong `context` AG-UI của lượt, mục
`router.WALLET_CONTEXT`; agent dùng cho router (vẫn là dữ liệu, không phải chỉ dẫn) và chỉ đọc ví khi thiếu; mọi tính toán sau đó vẫn
dùng tool phía server. (b) Lần đọc ví chỉ để dựng danh sách cho router thì im lặng (không thẻ tool), phát thẻ khi phần sau của lượt dùng
kết quả. Router giả, không gọi model.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from agent_helpers import (
    JARS_READ,
    blocks_of,
    check_agui_order,
    make_llm,
    route_response,
    run_turn,
    types,
)
from test_infer_pay_jar import DEMO_8, _calls, _inferred_notice, _tools, _types
from yofina_agent.router import WALLET_CONTEXT, wallet_context

from yofina_core.wallet import UNCLASSIFIED_JAR_CODE

CLIENT_JARS = [{"code": j["code"], "name": j["name"], "kind": j["kind"], **({"purpose": j["purpose"]} if "purpose" in j else {})}
               for j in DEMO_8]  # fmt: skip


class _Ctx:
    def __init__(self, description: str, value: str) -> None:
        self.description, self.value = description, value


def _context(jars: list[dict[str, Any]] | None = None, app_date: str = "2026-11-21", **extra: Any) -> list[dict[str, str]]:
    return [{"description": WALLET_CONTEXT, "value": json.dumps({"app_date": app_date, "jars": jars or CLIENT_JARS, **extra})}]


def _router_text(llm: Any) -> str:
    return llm[1].calls[0]["messages"][0]["content"][0]["text"]


def _tool_cards(events: list[Any]) -> list[str]:
    return [e.tool_call_name for e in events if e.type.value == "TOOL_CALL_START"]


# --- đọc mục context: kiểm chặt, sai một chỗ là bỏ cả mục ---------------------------------------------------------
def test_doc_danh_sach_hu_cua_frontend_bo_hu_he_thong():
    rows = [*CLIENT_JARS, {"code": UNCLASSIFIED_JAR_CODE, "name": "Chưa phân loại", "kind": "system"}]
    found = wallet_context([_Ctx(WALLET_CONTEXT, json.dumps({"app_date": "2026-11-21", "jars": rows}))])
    assert found is not None and str(found.app_date) == "2026-11-21"
    assert list(found.jars) == CLIENT_JARS


@pytest.mark.parametrize(
    "value",
    [
        "không phải JSON",
        json.dumps({"jars": CLIENT_JARS}),  # thiếu ngày
        json.dumps({"app_date": "21/11/2026", "jars": CLIENT_JARS}),
        json.dumps({"app_date": "2026-11-21", "jars": []}),
        json.dumps({"app_date": "2026-11-21", "jars": [{"code": "Ăn uống", "name": "Ăn uống", "kind": "spending"}]}),
        json.dumps({"app_date": "2026-11-21", "jars": [{"code": "an_uong", "name": "", "kind": "spending"}]}),
        json.dumps({"app_date": "2026-11-21", "jars": [{"code": "an_uong", "name": "Ăn uống", "kind": "khac"}]}),
        json.dumps({"app_date": "2026-11-21", "jars": [{"code": "a", "name": "A", "kind": "saving", "purpose": "x"}]}),
        json.dumps({"app_date": "2026-11-21", "jars": [{"code": "a", "name": "A", "kind": "saving", "balance_vnd": 1}]}),
        json.dumps({"app_date": "2026-11-21", "jars": [{"code": f"h{i}", "name": "H", "kind": "spending"} for i in range(21)]}),
    ],
)
def test_muc_context_sai_thi_bo_ca_muc(value):
    assert wallet_context([_Ctx(WALLET_CONTEXT, value)]) is None
    assert wallet_context([_Ctx("khác", json.dumps({"app_date": "2026-11-21", "jars": CLIENT_JARS}))]) is None
    assert wallet_context(None) is None and wallet_context([]) is None


# --- (a) có danh sách hũ của frontend: không đọc ví trước router ---------------------------------------------------
def test_luot_xa_giao_co_danh_sach_hu_khong_goi_tool_nao(monkeypatch):
    llm = make_llm([route_response(intent="chitchat", reply="Chào bạn!")])
    events, tools, _ = run_turn("chào bạn", llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch, context=_context())
    check_agui_order(events)
    assert tools.calls == [] and "TOOL_CALL_START" not in types(events)
    text = _router_text(llm)
    # router vẫn có danh sách hũ (dữ liệu, không số dư) và ngày mô phỏng để đổi hạn ra ngày
    assert text.startswith("<ngay_hom_nay>2026-11-21</ngay_hom_nay>\n<hu_cua_vi>")
    assert json.loads(text.split("<hu_cua_vi>\n", 1)[1].split("\n", 1)[0]) == CLIENT_JARS[0]
    assert events[-1].result["tool_calls"] == 0


def test_tra_so_du_co_danh_sach_hu_doc_vi_sau_router_khoi_truoc_ket_qua(monkeypatch):
    llm = make_llm([route_response(intent="lookup", lookup_kind="balance")])
    events, tools, _ = run_turn("ví còn bao nhiêu", llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch, context=_context())
    check_agui_order(events)
    assert tools.calls == [JARS_READ]
    t = types(events)
    assert t.index("ACTIVITY_SNAPSHOT") < t.index("TOOL_CALL_RESULT")
    assert _tool_cards(events) == ["ledger___get_jar_balances"]


def test_tinh_toan_van_dung_vi_phia_server_khong_tin_danh_sach_cua_frontend(monkeypatch):
    """Danh sách của frontend có hũ ví không có (cũ, hoặc bị sửa): router chọn hũ đó thì qua kiểm danh sách của lượt, nhưng hũ trả quyết
    theo lần đọc ví phía server: không có thì hỏi, không tính theo hũ đó."""
    fake = [*CLIENT_JARS, {"code": "hu_la", "name": "Quỹ lạ", "kind": "spending"}]
    llm = make_llm([route_response(intent="affordability", amount_vnd=200_000, spend_jar_code="hu_la")])
    events, tools, _ = run_turn("chi 200k có sao không", llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch, context=_context(fake))
    assert _types(events) == ["clarify"] and not _calls(tools, "affordability_check")
    assert "Quỹ lạ" not in [c["label"] for c in blocks_of(events)[0]["data"]["chips"]]  # chip từ ví phía server


def test_kiem_tra_co_danh_sach_hu_tinh_theo_hu_router_chon_bang_vi_server(monkeypatch):
    llm = make_llm([route_response(intent="affordability", amount_vnd=2_000_000, spend_jar_code="muc_tieu")])
    events, tools, _ = run_turn("đi chơi xa 2 triệu ổn không", llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch, context=_context())
    check_agui_order(events)
    assert [n for n, _ in tools.calls] == ["get_jar_balances", "affordability_check"]
    assert _calls(tools, "affordability_check")[0]["jar"] == "muc_tieu"
    assert _inferred_notice(events)["title"] == "Tính theo hũ Du lịch"  # type: ignore[index]
    assert _tool_cards(events) == ["ledger___get_jar_balances", "forecast___affordability_check"]


# --- (b) không có danh sách (frontend cũ, mục sai): đọc ví im lặng trước router -------------------------------------
@pytest.mark.parametrize("context", [None, [{"description": WALLET_CONTEXT, "value": "{}"}]], ids=["khong-co", "muc-sai"])
def test_luot_xa_giao_khong_co_danh_sach_doc_vi_im_lang(monkeypatch, context):
    llm = make_llm([route_response(intent="chitchat", reply="Chào bạn!")])
    events, tools, _ = run_turn("chào bạn", llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch, context=context)
    check_agui_order(events)
    assert tools.calls == [JARS_READ]  # vẫn là một tool call thật (đếm trần, bản ghi lượt)
    assert "TOOL_CALL_START" not in types(events)  # nhưng không có thẻ tool "Số dư các hũ" trên UI
    assert "<hu_cua_vi>" in _router_text(llm) and events[-1].result["tool_calls"] == 1


def test_luot_dung_ket_qua_doc_vi_thi_phat_the_tool_khi_dung(monkeypatch):
    llm = make_llm([route_response(intent="affordability", amount_vnd=2_000_000, spend_jar_code="muc_tieu")])
    events, tools, _ = run_turn("đi chơi xa 2 triệu ổn không", llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch)
    check_agui_order(events)
    assert [n for n, _ in tools.calls] == ["get_jar_balances", "affordability_check"]
    assert _tool_cards(events) == ["ledger___get_jar_balances", "forecast___affordability_check"]
