"""Router chạy bằng vai model riêng `router` (#39, quyết định của chủ dự án 26/11): Claude Haiku 4.5 trước, Nova 2 Lite dự phòng; vai
`small` (writer, what-if, phân loại, hồ sơ hành vi) không đổi.

Kiểm bằng client Bedrock giả: router gọi đúng vai, rơi về model dự phòng khi model đầu bị throttle hay chạm giới hạn tốc độ (cơ chế dự
phòng sẵn có của `yofina_core.llm`), điểm cache đặt sau phần tĩnh (schema tool, lời nhắc hệ thống) và không đặt trong tin người dùng
(ngày, hũ của ví, lịch sử, câu mới), model dự phòng không nhận điểm cache, kết quả bị cắt ở trần token được thử lại.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from agent_helpers import (
    FakeBedrock,
    FakeUsage,
    agent_settings,
    make_llm,
    route_response,
    run,
    run_turn,
)
from botocore.exceptions import ClientError
from yofina_agent.router import build_router_system, route, router_jar_list
from yofina_agent.settings import AgentSettings

from yofina_core.config import Config
from yofina_core.llm import LlmGateway, LlmSettings, ModelSpec, RateLimiter

CACHE_POINT = {"cachePoint": {"type": "default"}}
JARS = router_jar_list(
    [
        {"code": "an_uong", "name": "Ăn uống", "kind": "spending"},
        {"code": "hu_7k2q", "name": "Quỹ Đà Lạt", "kind": "saving", "purpose": "goal"},
    ]
)
TODAY = date(2026, 11, 20)
QUESTION = "trưa nay ăn bún 60k được không"
HISTORY = "Người dùng: chào\nYofina: Chào bạn!"


def _gateway(script: list[Any], *, haiku_rpm: int = 0, limiter: RateLimiter | None = None) -> tuple[LlmGateway, FakeBedrock]:
    settings = LlmSettings(
        roles={
            "router": (
                ModelSpec("m-haiku", rpm=haiku_rpm, daily_cap=100, prompt_cache=True),
                ModelSpec("m-nova", rpm=0, daily_cap=100),
            ),
            "small": (ModelSpec("m-small-a", rpm=0, daily_cap=100), ModelSpec("m-small-b", rpm=0, daily_cap=100)),
        },
        rate_limit_max_wait_seconds=0,
    )
    client = FakeBedrock(script)
    gw = LlmGateway(settings, config=Config({}), client=client, usage=FakeUsage(), limiter=limiter, sleep=lambda s: None)
    return gw, client


def _route(gw: LlmGateway, max_attempts: int = 2) -> Any:
    return run(route(gw, QUESTION, HISTORY, max_attempts=max_attempts, max_tokens=800, jars=JARS, today=TODAY))


def _ok() -> dict[str, Any]:
    return route_response(intent="affordability", amount_vnd=60_000, spend_jar_code="an_uong")


def test_router_goi_vai_router_va_dat_diem_cache_sau_phan_tinh():
    gw, client = _gateway([_ok()])
    res = _route(gw)
    assert res.role == "router" and res.model_id == "m-haiku"
    (req,) = client.calls
    assert req["modelId"] == "m-haiku" and req["inferenceConfig"]["maxTokens"] == 800
    # phần tĩnh: lời nhắc hệ thống rồi điểm cache; schema tool rồi điểm cache
    assert req["system"] == [{"text": build_router_system()}, CACHE_POINT]
    tools = req["toolConfig"]["tools"]
    assert [next(iter(t)) for t in tools] == ["toolSpec", "cachePoint"] and tools[-1] == CACHE_POINT
    # phần đổi theo lượt chỉ nằm trong tin người dùng, sau mọi điểm cache, và không có điểm cache nào
    (message,) = req["messages"]
    text = message["content"][0]["text"]
    assert "cachePoint" not in json.dumps(req["messages"])
    for tag in ("<ngay_hom_nay>", "<hu_cua_vi>", "<lich_su>", "<cau_moi>"):
        assert tag in text  # lời nhắc hệ thống chỉ nhắc tên thẻ, nội dung thẻ nằm ở đây
    for dynamic in ("2026-11-20", "Quỹ Đà Lạt", HISTORY, QUESTION):
        assert dynamic in text and dynamic not in req["system"][0]["text"]
    assert text.index("<hu_cua_vi>") < text.index("<lich_su>") < text.index("<cau_moi>")


def test_router_bi_throttle_thi_roi_ve_nova_khong_co_diem_cache():
    throttled = ClientError({"Error": {"Code": "ThrottlingException", "Message": "x"}}, "Converse")
    gw, client = _gateway([throttled, _ok()])
    res = _route(gw)
    assert res.model_id == "m-nova" and res.value.params.spend_jar_code == "an_uong"
    first, second = client.calls
    assert first["modelId"] == "m-haiku" and "cachePoint" in json.dumps(first)
    assert second["modelId"] == "m-nova" and "cachePoint" not in json.dumps(second)
    assert second["system"] == [{"text": build_router_system()}]


def test_router_cham_gioi_han_toc_do_cua_haiku_thi_goi_nova_ngay():
    """Cửa sổ tốc độ của Haiku đã đầy (chung với Haiku dự phòng của vai small, cùng khóa model id): không gọi Haiku, rơi về Nova."""
    limiter = RateLimiter(clock=lambda: 100.0)
    assert limiter.try_acquire("m-haiku", 1) == 0.0
    gw, client = _gateway([_ok()], haiku_rpm=1, limiter=limiter)
    res = _route(gw)
    assert res.model_id == "m-nova" and [c["modelId"] for c in client.calls] == ["m-nova"]


def test_router_bi_cat_o_tran_token_thi_khong_nhan_va_thu_lai():
    cut = route_response(intent="chitchat")  # câu chào bị cắt trước khi viết xong lời đáp: phần còn lại vẫn khớp schema
    cut["stopReason"] = "max_tokens"
    gw, client = _gateway([cut, route_response(intent="chitchat", reply="Chào bạn!")])
    res = _route(gw)
    assert res.attempts == 2 and res.value.reply == "Chào bạn!"
    assert "bị cắt" in json.dumps(client.calls[1]["messages"][-1], ensure_ascii=False)


def test_luot_chat_goi_router_voi_tran_token_mac_dinh():
    """Trần token đầu ra của router theo đo ở #39: một lời gọi hợp lệ dài nhất khoảng 310 token, lời đáp câu chào chạm 400; đặt 800."""
    assert AgentSettings.load({"YOFINA_GATEWAY_URL": "http://gateway.invalid/mcp"}).router_max_tokens == 800
    llm = make_llm([route_response(intent="chitchat", reply="Chào bạn!")])
    run_turn("chào", llm=llm, settings=agent_settings())
    assert llm[1].calls[0]["inferenceConfig"]["maxTokens"] == 800
