"""Kiểm tra trước khi chi có ngày chi (#39, câu b sau Runtime v33): router trả `date_spec` của thời điểm chi ("tháng sau"), nhưng lượt gọi
`affordability_check` không có `date` nên engine tính như chi hôm nay. Ngày tính bằng `yofina_core.dates` trong tiến trình (như hạn của
mục tiêu lộ trình); ngày sau hôm nay thì đi vào tool (tham số `date` sẵn có của engine) và vào dữ kiện của writer. Đặc tả không tính được
hoặc không sau hôm nay thì tính như cũ (chi hôm nay). Router và writer giả.
"""

from __future__ import annotations

import copy
from typing import Any

from agent_helpers import fixture, make_llm, route_response, run_turn
from test_infer_pay_jar import DEMO_8, _tools
from yofina_agent.compact import compact_affordability
from yofina_agent.writer import TASKS

#: câu của test, không trùng câu eval hay câu người dùng trên app
Q = "dau thang sau minh muon mua ve xem phim 300k bang hu giai tri duoc khong"


def _checks(tools: Any) -> list[dict[str, Any]]:
    return [a for n, a in tools.calls if n == "affordability_check"]


def _route(**extra: Any) -> dict[str, Any]:
    return {"intent": "affordability", "amount_vnd": 300_000, "funding": "jar", "jar_text": "giải trí", "label": "vé xem phim", **extra}


def test_dac_ta_ngay_chi_sau_hom_nay_thi_kiem_tra_theo_ngay_do(monkeypatch):
    spec = {"anchor": "start_of", "period": "month", "period_offset": 1}
    llm = make_llm([route_response(**_route(date_text="đầu tháng sau", date_spec=spec))])
    _, tools, _ = run_turn(Q, llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch)
    (args,) = _checks(tools)
    assert args["date"] == "2026-12-01" and args["jar"] == "giai_tri"  # hôm nay mô phỏng 21/11/2026


def test_khong_co_dac_ta_hoac_dac_ta_khong_sau_hom_nay_thi_tinh_nhu_chi_hom_nay(monkeypatch):
    for extra in ({}, {"date_spec": {"anchor": "today"}}, {"date_spec": {"anchor": "hom_qua"}}):
        llm = make_llm([route_response(**_route(**extra))])
        _, tools, _ = run_turn(Q, llm=llm, tools=_tools(DEMO_8), monkeypatch=monkeypatch)
        (args,) = _checks(tools)
        assert "date" not in args, extra


def test_ban_gon_co_ngay_chi_khi_engine_tinh_cho_ngay_sau_hom_nay():
    payload = copy.deepcopy(fixture("affordability_check.ok.json"))
    assert "pay_date_text" not in compact_affordability(payload)  # ngày chi là hôm nay: như cũ
    payload["data"]["pay_date"] = "2026-12-01"
    assert compact_affordability(payload)["pay_date_text"] == "01/12/2026"
    assert "pay_date_text" in TASKS["affordability"]
