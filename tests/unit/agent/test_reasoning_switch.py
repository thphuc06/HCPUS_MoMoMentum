"""Công tắc khối `reasoning` (#7): SSM `<prefix>/agent/reasoning_enabled`, biến môi trường `YOFINA_REASONING_ENABLED` ghi đè, mặc
định bật. Đọc lười, ngoài event loop, nhớ một chu kỳ rồi đọc lại. SSM là đồ giả, không gọi AWS."""

from __future__ import annotations

import json
import threading
from typing import Any

from agent_helpers import agent_settings, blocks_of, run, run_turn, tool_response
from test_advisor import advised
from test_memory_wiring import raw_prompt
from test_roadmap_agent import build, outline, review, scripted_tools, step
from test_whatif import WHAT_IF_Q, block_types, result_of, text_of, what_if_llm
from yofina_agent.settings import AgentSettings, ReasoningSwitch

ENV = {"YOFINA_SSM_PREFIX": "/yofina", "YOFINA_REGION": "ap-southeast-1"}


class ParameterNotFound(Exception):
    pass


class FakeSsm:
    """SSM giả: trả `value` (hoặc ném `error`), ghi tên khóa và luồng của mỗi lần đọc."""

    def __init__(self, value: str | None = None, error: Exception | None = None) -> None:
        self.value, self.error = value, error
        self.calls: list[str] = []
        self.threads: list[int] = []

    def get_parameter(self, *, Name: str, WithDecryption: bool) -> dict[str, Any]:
        self.calls.append(Name)
        self.threads.append(threading.get_ident())
        if self.error is not None:
            raise self.error
        return {"Parameter": {"Name": Name, "Value": self.value}}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def switch(
    ssm: FakeSsm, env: dict[str, str] | None = None, clock: Clock | None = None
) -> ReasoningSwitch:
    return ReasoningSwitch(
        {**ENV, **(env or {})}, default=True, refresh_seconds=300, ssm=ssm, clock=clock or Clock()
    )


def test_vang_khoa_hoac_loi_doc_ssm_thi_van_bat():
    assert run(switch(FakeSsm(error=ParameterNotFound("x"))).enabled()) is True
    assert run(switch(FakeSsm(error=RuntimeError("AccessDeniedException"))).enabled()) is True
    assert run(switch(FakeSsm("không phải bool")).enabled()) is True


def test_ssm_tat_thi_tat_nho_mot_chu_ky_roi_doc_lai_ngoai_event_loop():
    ssm, clock = FakeSsm("false"), Clock()
    s = switch(ssm, clock=clock)
    assert run(s.enabled()) is False
    assert ssm.calls == ["/yofina/agent/reasoning_enabled"]
    assert (
        threading.main_thread().ident not in ssm.threads
    )  # tra SSM trong luồng nền, không chặn event loop
    ssm.value = "true"
    clock.now += 299
    assert run(s.enabled()) is False and len(ssm.calls) == 1  # còn trong chu kỳ nhớ: không đọc lại
    clock.now += 2
    assert (
        run(s.enabled()) is True and len(ssm.calls) == 2
    )  # hết chu kỳ: đọc lại, đổi không cần deploy


def test_bien_moi_truong_ghi_de_ssm():
    ssm = FakeSsm("true")
    assert run(switch(ssm, {"YOFINA_REASONING_ENABLED": "false"}).enabled()) is False
    assert ssm.calls == []


def test_nap_cau_hinh_khong_tra_ssm_cua_cong_tac(monkeypatch):
    """RUN_STARTED của phiên lạnh không chờ SSM: nạp cấu hình không tạo client SSM, chỉ lượt đầu cần tới công tắc mới đọc."""
    made: list[str] = []
    ssm = FakeSsm("false")

    def client(name: str, **_kw: Any) -> FakeSsm:
        made.append(name)
        return ssm

    monkeypatch.setattr("boto3.client", client)
    settings = AgentSettings.load(
        {
            **ENV,
            "YOFINA_GATEWAY_URL": "http://gateway.invalid/mcp",
            "YOFINA_GUARDRAIL_ID": "g",
            "YOFINA_GUARDRAIL_VERSION": "1",
        }
    )
    assert made == []
    assert run(settings.reasoning_switch.enabled()) is False and made == ["ssm"]
    # không có tiền tố SSM (test, chạy tại máy): mặc định đóng gói, không tạo client
    assert run(AgentSettings.load({}).reasoning_switch.enabled()) is True and made == ["ssm"]


# --- công tắc tắt: what-if và lộ trình chạy như trước luồng K ------------------------------------------------------------
def settings_with(s: ReasoningSwitch) -> AgentSettings:
    return agent_settings(reasoning_switch=s)


def switched_off() -> AgentSettings:
    return settings_with(
        ReasoningSwitch({"YOFINA_REASONING_ENABLED": "false"}, default=True, refresh_seconds=300)
    )


def reasoning_of(events: list[Any]) -> list[dict[str, Any]]:
    return [b for b in blocks_of(events) if b["type"] == "reasoning"]


def test_tat_thi_what_if_khong_co_khoi_va_analyst_khong_duoc_xin_lap_luan(monkeypatch):
    # model giả vẫn trả lập luận: mã không phát, và prompt/schema đã không xin
    llm = what_if_llm(tool_response("analyze", advised()))
    events, tools, _ = run_turn(
        WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch, settings=switched_off()
    )
    assert reasoning_of(events) == []
    assert block_types(events) == ["forecast_timeline", "obligation_impact", "options", "confirm"]
    call = llm[1].calls[2]  # router, Orchestrator, Analyst
    system = json.dumps(call["system"], ensure_ascii=False)
    schema = json.dumps(call["toolConfig"], ensure_ascii=False)
    assert "reasoning" not in system and "conclusion" not in system
    assert '"reasoning"' not in schema and '"conclusion"' not in schema
    assert '"narrative"' in schema and '"options"' in schema
    assert "<can_cu>" not in raw_prompt(call)
    assert "get_behavior_profile" not in [
        n for n, _ in tools.calls
    ]  # thói quen chỉ để cá nhân hóa kết luận
    assert text_of(events).startswith("Nếu mua tai nghe") and result_of(events)["degraded"] is False


def test_loi_doc_ssm_thi_what_if_van_co_lap_luan(monkeypatch):
    on = settings_with(switch(FakeSsm(error=RuntimeError("AccessDeniedException"))))
    llm = what_if_llm(tool_response("analyze", advised()))
    events, _, _ = run_turn(WHAT_IF_Q, llm=llm, monkeypatch=monkeypatch, settings=on)
    assert reasoning_of(events) and "reasoning" in json.dumps(llm[1].calls[2]["toolConfig"])


def test_tat_thi_lo_trinh_khong_co_lap_luan_nhu_job_sinh_lai():
    tools = scripted_tools(checks=("ok", "ok", "ok"))
    result, client, scope = build(
        tools, outline(step(), review()), advise=True, settings=switched_off()
    )
    assert result.outcome.ok and result.advice is None and scope.calls == 1
    assert "get_behavior_profile" not in [n for n, _ in tools.calls]
    call = client.calls[0]
    assert "reasoning" not in json.dumps(call["system"], ensure_ascii=False)
    assert '"reasoning"' not in json.dumps(call["toolConfig"], ensure_ascii=False)
    assert "can_cu" not in json.loads(call["messages"][0]["content"][0]["text"])
