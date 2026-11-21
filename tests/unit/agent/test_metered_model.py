import asyncio

import pytest
from agent_helpers import FakeUsage, make_llm
from botocore.exceptions import ClientError
from yofina_agent.metered_model import MeteredModel
from yofina_agent.writer import write_stream

from yofina_core.config import Config
from yofina_core.llm import (
    AllModelsFailed,
    LlmGateway,
    LlmSettings,
    ModelBudgetExceeded,
    ModelSpec,
    TurnScope,
)


def text_events(text: str, tin: int = 30, tout: int = 7):
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"start": {}}},
        {"contentBlockDelta": {"delta": {"text": text}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": "end_turn"}},
        {
            "metadata": {
                "usage": {"inputTokens": tin, "outputTokens": tout, "totalTokens": tin + tout},
                "metrics": {"latencyMs": 5},
            }
        },
    ]


class FakeModelStream:
    """Thay BedrockModel của Strands: phát các event cho trước, có thể ném lỗi trước hoặc giữa luồng."""

    def __init__(self, events=None, error=None, error_after=None):
        self.events, self.error, self.error_after = events or [], error, error_after
        self.calls = 0

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kw):
        self.calls += 1
        if self.error and self.error_after is None:
            raise self.error
        for i, e in enumerate(self.events):
            if self.error and i == self.error_after:
                raise self.error
            yield e


def throttle():
    return ClientError({"Error": {"Code": "ThrottlingException", "Message": "x"}}, "ConverseStream")


def denied():
    return ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "x"}}, "ConverseStream"
    )


def metered(fakes: dict, usage=None, scope=None):
    settings = LlmSettings(roles={"small": tuple(ModelSpec(k, rpm=0, daily_cap=50) for k in fakes)})
    gw = LlmGateway(settings, config=Config({}), client=object(), usage=usage or FakeUsage())
    m = MeteredModel(gw, "small", scope=scope, region="ap-southeast-1")
    m._bedrock = lambda spec: fakes[spec.id]  # type: ignore[method-assign]
    return m


async def drain(m, **kw):
    return [
        e
        async for e in m.stream([{"role": "user", "content": [{"text": "hi"}]}], None, "sys", **kw)
    ]


def test_dem_moi_loi_goi_va_ghi_token():
    usage, scope = FakeUsage(), TurnScope()
    m = metered({"a": FakeModelStream(text_events("chào"))}, usage, scope)
    events = asyncio.run(drain(m))
    assert any("contentBlockDelta" in e for e in events)
    assert usage.calls == ["a"] and scope.calls == 1
    rec = scope.records[0]
    assert (rec.input_tokens, rec.output_tokens, rec.outcome) == (30, 7, "ok")


def test_du_phong_khi_throttle_hoac_bi_chan_truoc_event_dau():
    for err in (throttle(), denied()):
        usage = FakeUsage()
        m = metered(
            {"a": FakeModelStream(error=err), "b": FakeModelStream(text_events("từ b"))}, usage
        )
        events = asyncio.run(drain(m))
        texts = [e.get("contentBlockDelta", {}).get("delta", {}).get("text") for e in events]
        assert "từ b" in texts
        assert usage.calls == ["a", "b"]  # cả hai lời gọi đều bị đếm


def test_loi_sau_event_dau_khong_chuyen_du_phong():
    a = FakeModelStream(text_events("x"), error=throttle(), error_after=3)
    b = FakeModelStream(text_events("y"))
    m = metered({"a": a, "b": b})
    with pytest.raises(ClientError):
        asyncio.run(drain(m))
    assert b.calls == 0  # tránh phát chữ lặp hai lần


def test_het_chuoi_thi_all_models_failed_khong_phai_throttled():
    m = metered({"a": FakeModelStream(error=throttle()), "b": FakeModelStream(error=denied())})
    with pytest.raises(AllModelsFailed) as e:
        asyncio.run(drain(m))
    assert [x[1] for x in e.value.attempts] == ["ThrottlingException", "AccessDeniedException"]


def test_cham_tran_thi_khong_goi_model_nao():
    a = FakeModelStream(text_events("x"))
    m = metered({"a": a, "b": FakeModelStream(text_events("y"))}, FakeUsage(caps_hit={"a"}))
    with pytest.raises(ModelBudgetExceeded):
        asyncio.run(drain(m))
    assert a.calls == 0


def test_tran_so_luot_gom_ca_lan_strands_tu_goi_lai():
    scope = TurnScope(max_calls=2)
    m = metered({"a": FakeModelStream(text_events("x"))}, scope=scope)
    asyncio.run(drain(m))
    asyncio.run(drain(m))
    with pytest.raises(ModelBudgetExceeded) as e:
        asyncio.run(drain(m))
    assert e.value.reason == "turn_limit"


def test_strands_agent_dung_chung_lop_kiem_va_write_stream_chay_that(monkeypatch):
    """`write_stream` chạy một strands.Agent thật với MeteredModel (BedrockModel được thay bằng bản giả)."""
    usage = FakeUsage()
    llm, _, _ = make_llm([], usage)
    fake = FakeModelStream(text_events("Xin chào bạn"))
    monkeypatch.setattr(MeteredModel, "_bedrock", lambda self, spec: fake)
    monkeypatch.setenv("YOFINA_REGION", "ap-southeast-1")
    scope = TurnScope()

    async def go():
        chunks = []
        async for c in write_stream(
            llm,
            task="chitchat",
            question="chào",
            compact={},
            scope=scope,
            max_tokens=100,
            turn_limit=2,
            output_token_limit=100,
        ):
            chunks.append(c)
        return "".join(chunks)

    assert asyncio.run(go()) == "Xin chào bạn"
    assert (
        usage.calls == ["m-small-a"] and scope.calls == 1
    )  # đúng một lượt, được đếm qua cùng lớp kiểm
