"""Số tiền ngoại tệ trong chat: router trích `currency` và `amount_original` (không quy đổi), mã gọi `knowledge___get_exchange_rate`
TRƯỚC khi vào ý định, số VND của what-if và kiểm tra trước khi chi lấy từ kết quả tool, và mọi con số nói ra qua kiểm căn cứ.

Gateway giả chạy ĐÚNG hàm của Lambda (`yofina_knowledge.fx_rates.exchange_rate_data`) với nguồn tỷ giá giả; không gọi mạng.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from agent_helpers import (
    JARS_READ,
    FakeRecords,
    FakeTools,
    FakeWriter,
    blocks_of,
    check_agui_order,
    make_llm,
    mcp_ok,
    route_response,
    run_turn,
    tool_response,
)
from test_whatif import NARRATIVE, analysis
from yofina_agent.fx_chat import compact_exchange_rate, decimal_vi
from yofina_agent.router import build_router_system
from yofina_agent.schemas import IntentParams
from yofina_agent.tools import classify_result
from yofina_agent.whatif import with_converted_amount

from yofina_core import fx
from yofina_core.errors import YofinaError
from yofina_knowledge.fx_rates import exchange_rate_data

APP_DATE = date(2026, 11, 21)  # app_date của các fixture agent
RATES = {
    date(2026, 11, 21): {"USD": Decimal("25790.00")},
    date(2026, 11, 20): {"USD": Decimal("25780.00"), "EUR": Decimal("29506.30")},
}


class FakeRates:
    """Nguồn tỷ giá giả: bảng theo ngày (vắng là chưa có bảng); `fail` thì như mất mạng."""

    def __init__(self, tables: dict[date, dict[str, Decimal]], fail: bool = False) -> None:
        self.tables, self.fail = tables, fail

    def fetch(self, day: date) -> fx.RateTable | None:
        if self.fail:
            raise fx.RateUnavailable("network")
        rates = self.tables.get(day)
        return None if rates is None else fx.RateTable(day=day, rates=rates)


def rate_tool(*, fail: bool = False, tables: dict[date, dict[str, Decimal]] | None = None):
    """Tool `get_exchange_rate` giả: chạy hàm thật của Lambda, ngày mặc định là ngày mô phỏng của fixture."""
    conv = fx.FxConverter(
        FakeRates(RATES if tables is None else tables, fail),
        now=lambda: datetime(2026, 11, 24, 11, 30, tzinfo=UTC),
    )

    def call(args: dict[str, Any]):
        try:
            data = exchange_rate_data(
                conv,
                APP_DATE,
                currency=args.get("currency"),
                day=args.get("date"),
                amount=args.get("amount"),
            )
            payload = {
                "status": "OK",
                "as_of": "2026-11-24T11:30:00Z",
                "app_date": APP_DATE.isoformat(),
                "data": data,
            }
        except YofinaError as exc:
            payload = {"status": "ERROR", "code": str(exc.code), "message": exc.message}
        return classify_result("x", mcp_ok(payload))

    return call


def text_of(events: list[Any]) -> str:
    return "".join(e.delta for e in events if e.type.value == "TEXT_MESSAGE_CONTENT")


def started(events: list[Any]) -> list[str]:
    return [e.tool_call_name for e in events if e.type.value == "TOOL_CALL_START"]


# --- router: tham số ngoại tệ ------------------------------------------------------------------------------------------------
def test_tham_so_ngoai_te_cua_router_chuan_hoa_ma_va_vnd_khong_phai_ngoai_te():
    assert IntentParams(currency=" usd ", amount_original=111.11).currency == "USD"
    assert IntentParams(currency="VND").currency is None  # VND là số tiền thường, không qua tỷ giá
    assert (
        IntentParams(currency="đô la").currency is None
    )  # không phải mã: bỏ, không làm hỏng cả kết quả router
    with pytest.raises(ValueError):
        IntentParams(amount_original=0)


def test_router_biet_tool_ty_gia_qua_dinh_nghia_tham_so_khong_qua_cau_mau():
    system = build_router_system()
    assert "amount_original" in system and "currency" in system and "ISO 4217" in system
    assert "KHÔNG tự quy đổi" in system


# --- hỏi tỷ giá hay quy đổi (ý định knowledge) -------------------------------------------------------------------------------
def test_quy_doi_so_tien_ngoai_te_cau_tra_loi_tu_ket_qua_tool_va_qua_kiem_can_cu(monkeypatch):
    records = FakeRecords()
    llm = make_llm([route_response(intent="knowledge", currency="USD", amount_original=111.11)])
    events, tools, writer = run_turn(
        "111,11 USD là bao nhiêu tiền Việt?",
        llm=llm,
        tools=FakeTools({"get_exchange_rate": rate_tool()}),
        monkeypatch=monkeypatch,
        records=records,
    )
    check_agui_order(events)
    assert started(events) == ["knowledge___get_exchange_rate"]  # lần đọc ví cho router im lặng
    assert tools.calls == [JARS_READ, ("get_exchange_rate", {"currency": "USD", "amount": 111.11})]
    text = text_of(events)
    # 111,11 × 25.790 = 2.865.526,9 -> 2.865.527 ₫ (làm tròn tới đồng ở Lambda, không ở agent)
    assert "111,11 USD" in text and "2.865.527 ₫" in text and "25.790 ₫ cho 1 USD" in text
    assert "Vietcombank" in text and "21/11/2026" in text and "ước tính" in text
    assert writer.calls == []  # câu dựng bằng mã, không có lượt model nào ngoài router
    rec = records.saved[0]
    rules = {r["rule_id"]: r["outcome"] for r in rec["rules_checked"]}
    assert rules["numeric_grounding"] == "pass" and events[-1].result["degraded"] is False
    assert any(
        d["tool"] == "knowledge___get_exchange_rate" and d.get("value") == "USD"
        for d in rec["data_used"]
    )


def test_hoi_ty_gia_khong_so_tien_va_ngay_chua_co_bang_thi_noi_bang_gan_nhat(monkeypatch):
    llm = make_llm([route_response(intent="knowledge", currency="eur")])
    events, tools, _ = run_turn(
        "Tỷ giá euro hôm nay?",
        llm=llm,
        tools=FakeTools(
            {"get_exchange_rate": rate_tool(tables={date(2026, 11, 20): RATES[date(2026, 11, 20)]})}
        ),
        monkeypatch=monkeypatch,
    )
    assert tools.calls == [JARS_READ, ("get_exchange_rate", {"currency": "EUR"})]
    text = text_of(events)
    assert "29.506,3 ₫ cho 1 EUR" in text and "20/11/2026" in text and "21/11/2026" in text
    assert "₫" not in text.replace("29.506,3 ₫", "")  # không có số VND nào khác


def test_nguon_ty_gia_loi_thi_bao_loi_cua_tool_khong_doan_so(monkeypatch):
    llm = make_llm(
        [
            route_response(
                intent="affordability",
                currency="USD",
                amount_original=40,
                label="tai nghe",
                jar_text="Giải trí",
            )
        ]
    )
    events, tools, writer = run_turn(
        "Mua tai nghe 40 USD có ổn không?",
        llm=llm,
        tools=FakeTools({"get_exchange_rate": rate_tool(fail=True)}),
        monkeypatch=monkeypatch,
    )
    check_agui_order(events)
    names = [n for n, _ in tools.calls]
    # đọc ví đầu lượt một lần; không kiểm tra với số đoán, không hỏi lại số tiền
    assert set(names) == {"get_jar_balances", "get_exchange_rate"} and names.count("get_jar_balances") == 1
    (notice,) = [b for b in blocks_of(events) if b["type"] == "notice"]
    assert notice["data"]["code"] == "INTERNAL_ERROR" and "tỷ giá" in notice["data"]["message"]
    assert not [b for b in blocks_of(events) if b["type"] == "clarify"] and writer.calls == []


# --- kiểm tra trước khi chi với giá ngoại tệ --------------------------------------------------------------------------------
def test_kiem_tra_truoc_khi_chi_dung_so_vnd_cua_tool_ty_gia(monkeypatch):
    # router lỡ đặt số theo ngoại tệ vào amount_vnd: mã vẫn coi đó là số gốc (quy tắc: số ngoại tệ không bao giờ là VND)
    llm = make_llm(
        [
            route_response(
                intent="affordability",
                currency="USD",
                amount_vnd=40,
                label="tai nghe",
                jar_text="Giải trí",
            )
        ]
    )
    writer = FakeWriter("Khoảng 1.031.600 ₫ cho tai nghe thì hũ vẫn đủ.")
    events, tools, _ = run_turn(
        "Mua tai nghe 40 USD có ổn không?",
        llm=llm,
        tools=FakeTools({"get_exchange_rate": rate_tool()}),
        monkeypatch=monkeypatch,
        writer=writer,
    )
    check_agui_order(events)
    names = [n for n, _ in tools.calls]
    # đọc ví đầu lượt (dùng lại cho cả lượt), rồi tỷ giá trước mọi tool khác
    assert names[:2] == ["get_jar_balances", "get_exchange_rate"] and names.count("affordability_check") == 1
    assert names.count("get_jar_balances") == 1
    assert tools.calls[1][1] == {"currency": "USD", "amount": 40}
    assert (
        dict(tools.calls)["affordability_check"]["amount_vnd"] == 1_031_600
    )  # 40 × 25.790, từ kết quả tool
    (call,) = writer.calls
    assert (
        call["task"] == "affordability"
        and call["compact"]["exchange_rate"]["amount_vnd_text"] == "1.031.600 ₫"
    )
    assert "1.031.600 ₫" in text_of(
        events
    )  # số của người viết có căn cứ (bản gọn có tỷ giá) nên được phát


def test_nguoi_viet_bia_so_vnd_khac_ket_qua_tool_thi_bi_bo(monkeypatch):
    llm = make_llm(
        [
            route_response(
                intent="affordability",
                currency="USD",
                amount_original=40,
                label="tai nghe",
                jar_text="Giải trí",
            )
        ]
    )
    writer = FakeWriter(
        "Khoảng 1.100.000 ₫ cho tai nghe."
    )  # tự nhân tỷ giá khác: không có trong kết quả tool nào
    events, _, _ = run_turn(
        "Mua tai nghe 40 USD có ổn không?",
        llm=llm,
        tools=FakeTools({"get_exchange_rate": rate_tool()}),
        monkeypatch=monkeypatch,
        writer=writer,
    )
    assert len(writer.calls) == 1 and "1.100.000" not in text_of(events)


# --- what-if với giá ngoại tệ -----------------------------------------------------------------------------------------------
def test_what_if_so_vnd_cua_kich_ban_la_so_cua_tool_ty_gia_va_analyst_duoc_kiem_can_cu(monkeypatch):
    route = {"intent": "what_if", "currency": "USD", "amount_original": 50, "funding": "credit",
             "scenario_kind": "bnpl_purchase", "label": "tai nghe"}  # fmt: skip
    # Orchestrator đọc nhầm số theo ngoại tệ (50) làm số VND: mã thay bằng số đã quy đổi
    scenario = {"scenario": {"kind": "bnpl_purchase", "amount_vnd": 50, "funding_source": "credit", "jar_code": None,
                             "date": None, "label": "tai nghe"}}  # fmt: skip
    narrative = NARRATIVE + " Khoản 50 USD được tính là 1.289.500 ₫ theo tỷ giá bán 25.790 ₫."
    llm = make_llm(
        [
            route_response(**route),
            tool_response("plan_scenario", scenario),
            tool_response("analyze", analysis(narrative)),
        ]
    )
    events, tools, _ = run_turn(
        "Nếu mua tai nghe 50 USD bằng Ví Trả Sau thì sao",
        llm=llm,
        tools=FakeTools({"get_exchange_rate": rate_tool()}),
        monkeypatch=monkeypatch,
    )
    check_agui_order(events)
    names = [n for n, _ in tools.calls]
    assert names[:2] == ["get_jar_balances", "get_exchange_rate"] and names.count("get_jar_balances") == 1
    run_args = next(a for n, a in tools.calls if n == "run_scenario")
    assert run_args["scenario"]["amount_vnd"] == 1_289_500  # 50 × 25.790
    analyst_prompt = json.dumps(llm[1].calls[-1]["messages"], ensure_ascii=False)
    assert "exchange_rate" in analyst_prompt and "25.790 ₫" in analyst_prompt
    # lời giải thích nêu số VND và tỷ giá: Verifier thấy cả hai trong kết quả tool nên qua ngay vòng đầu
    r = events[-1].result
    assert r["verifier_rounds"] == 1 and r["degraded"] is False
    assert "1.289.500 ₫" in text_of(events)


def test_doi_so_cua_kich_ban_chi_khi_co_ngoai_te():
    spec = {
        "kind": "one_time_purchase",
        "amount_vnd": 50,
        "funding_source": "jar",
        "jar_code": "an_uong",
    }
    usd = route_response(intent="what_if", currency="USD", amount_vnd=1_289_500)["output"][
        "message"
    ]["content"][0]["toolUse"]
    from yofina_agent.schemas import IntentResult

    r = IntentResult.model_validate(usd["input"])
    assert with_converted_amount(spec, r)["amount_vnd"] == 1_289_500
    vnd = IntentResult.model_validate({**usd["input"], "params": {"amount_vnd": 2_000_000}})
    assert with_converted_amount(spec, vnd) == spec
    salary = {"kind": "income_change", "new_monthly_salary_vnd": 3000}
    assert with_converted_amount(salary, r)["new_monthly_salary_vnd"] == 1_289_500


# --- bản gọn -------------------------------------------------------------------------------------------------------------
def test_ban_gon_viet_so_kieu_viet_nam_tu_chuoi_thap_phan_cua_hop_dong():
    assert (
        decimal_vi("25790.00") == "25.790"
        and decimal_vi("111.11") == "111,11"
        and decimal_vi("176.8400") == "176,84"
    )
    payload = {
        "status": "OK",
        "data": {
            "currency": "USD", "rate": "25790.00", "rate_type": "sell", "rate_source": "vietcombank",
            "rate_date": "2026-11-10", "requested_date": "2026-11-10", "amount_original": "1200", "amount_vnd": 30_948_000,
        },
    }  # fmt: skip
    c = compact_exchange_rate(payload)
    assert (
        c["amount_original_text"] == "1.200 USD"
        and c["amount_vnd_text"] == "30.948.000 ₫"
        and c["rate_text"] == "25.790 ₫"
    )
    assert c["source"] == "Vietcombank" and c["rate_date_text"] == "10/11/2026"
