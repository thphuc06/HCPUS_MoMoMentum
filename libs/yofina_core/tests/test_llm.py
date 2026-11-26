"""Unit test của yofina_core.llm. Client Bedrock, bộ đếm và đồng hồ giả chỉ có ở đây."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import pytest
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field

from yofina_core.config import Config, ConfigError
from yofina_core.llm import (
    AllModelsFailed,
    BudgetCapReached,
    DynamoUsageStore,
    LlmGateway,
    LlmSettings,
    ModelBudgetExceeded,
    ModelSpec,
    RateLimiter,
    StructuredOutputError,
    TurnScope,
    bedrock_json_schema,
    load_settings,
    user_message,
)


def client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "x"}}, "Converse")


def ok_response(text: str = "xin chào", tin: int = 10, tout: int = 5) -> dict[str, Any]:
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "usage": {"inputTokens": tin, "outputTokens": tout},
        "stopReason": "end_turn",
    }


def tool_response(name: str, payload: dict[str, Any], tid: str = "t1") -> dict[str, Any]:
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"toolUse": {"toolUseId": tid, "name": name, "input": payload}}],
            }
        },
        "usage": {"inputTokens": 20, "outputTokens": 8},
        "stopReason": "tool_use",
    }


class FakeClient:
    """Mỗi phần tử của `script` là phản hồi (dict) hoặc ngoại lệ, tiêu thụ lần lượt."""

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(kw)
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class FakeUsage:
    def __init__(self, fail: Exception | None = None, caps_hit: set[str] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail, self.caps_hit = fail, caps_hit or set()
        self.counts: dict[tuple[str, str], int] = {}

    def consume(self, *, day: str, model: str, cap: int, ttl_epoch: int) -> int:
        self.calls.append({"day": day, "model": model, "cap": cap, "ttl": ttl_epoch})
        if self.fail:
            raise self.fail
        if model in self.caps_hit or self.counts.get((day, model), 0) >= cap:
            raise BudgetCapReached(model)
        self.counts[(day, model)] = self.counts.get((day, model), 0) + 1
        return self.counts[(day, model)]


def settings(**over: Any) -> LlmSettings:
    roles = {
        "planner": (
            ModelSpec("m-plan-a", rpm=8, daily_cap=3),
            ModelSpec("m-plan-b", rpm=8, daily_cap=3, temperature=False),
        ),
        "small": (
            ModelSpec("m-small-a", rpm=0, daily_cap=100),
            ModelSpec("m-small-b", rpm=0, daily_cap=100),
        ),
    }
    return LlmSettings(roles=over.pop("roles", roles), **over)


FIXED_NOW = datetime(2026, 11, 21, 15, 0, tzinfo=UTC)


def gateway(client: FakeClient, usage: FakeUsage | None = None, **kw: Any) -> LlmGateway:
    return LlmGateway(
        kw.pop("settings", settings()),
        config=Config({}),
        client=client,
        usage=usage or FakeUsage(),
        now=lambda: FIXED_NOW,
        sleep=kw.pop("sleep", lambda s: None),
        **kw,
    )


# --- cấu hình -------------------------------------------------------------------------------
def test_mac_dinh_dong_goi_co_cac_vai_va_tran():
    s = load_settings(Config({}), env={})
    assert set(s.roles) == {"planner", "ingest", "ingest_columns", "small", "router", "embedding"}
    # vai nạp dữ liệu (F6): đọc ảnh bằng Sonnet 4.6 rồi Kimi K3; ánh xạ cột/phân loại CSV bằng model nhỏ; mỗi vai có trần riêng
    assert next(m.id for m in s.roles["ingest"]).endswith("claude-sonnet-4-6")
    assert s.roles["ingest"][1].temperature is False
    assert s.roles["ingest"][0].daily_cap == 300 and s.roles["ingest_columns"][0].daily_cap == 600
    assert next(m.id for m in s.roles["planner"]).endswith("claude-sonnet-4-6")
    assert s.roles["planner"][0].daily_cap == 400
    assert s.roles["small"][0].daily_cap == 2000
    assert s.roles["embedding"][0].daily_cap == 3000
    assert s.roles["planner"][0].rpm == 8
    assert s.roles["planner"][1].temperature is False  # Kimi K3 không nhận temperature


HAIKU = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
NOVA = "global.amazon.nova-2-lite-v1:0"


def test_vai_router_haiku_truoc_nova_du_phong_va_vai_small_khong_doi():
    """#39 (chủ dự án 26/11): router chạy Claude Haiku 4.5, Nova 2 Lite dự phòng, bằng một vai riêng; vai `small` (writer, what-if,
    phân loại, hồ sơ hành vi) giữ Nova trước. Bộ giới hạn tốc độ và bộ đếm ngày theo MODEL id nên Haiku của router và Haiku dự phòng
    của `small` dùng chung một cửa sổ và một bộ đếm: tốc độ và trần của Haiku giữ đúng mức đang đặt (quota 10 RPM dùng chung với
    Memory), không thêm chỗ mới."""
    s = load_settings(Config({}), env={})
    router, small = s.roles["router"], s.roles["small"]
    assert [m.id for m in router] == [HAIKU, NOVA]
    assert [m.id for m in small] == [NOVA, HAIKU]
    assert (router[0].rpm, router[0].daily_cap) == (small[1].rpm, small[1].daily_cap) == (8, 2000)
    assert (router[1].rpm, router[1].daily_cap) == (small[0].rpm, small[0].daily_cap) == (18, 2000)
    assert router[0].prompt_cache is True and router[1].prompt_cache is False
    assert not any(m.prompt_cache for m in small)


def test_mac_dinh_dong_goi_bat_cache_chi_cho_sonnet_4_6_va_haiku_cua_router():
    """#24: Sonnet 4.6 của vai planner (Orchestrator, Analyst, phác thảo lộ trình) bật cache (tài liệu xác nhận cachePoint ở system và
    tools). #39: Claude Haiku 4.5 của vai router cũng bật (cùng ba trường nhận cachePoint, tối thiểu 4.096 token cho tiền tố: system và
    schema của router khoảng 12.000 token). Haiku ở vai khác, Nova (không nhận cachePoint ở tools) và Kimi K3 tắt."""
    s = load_settings(Config({}), env={})
    on = {(role, m.id) for role, chain in s.roles.items() for m in chain if m.prompt_cache}
    assert on == {
        ("planner", "global.anthropic.claude-sonnet-4-6"),
        ("router", "global.anthropic.claude-haiku-4-5-20251001-v1:0"),
    }
    assert all(not m.prompt_cache for chain in s.roles.values() for m in chain if "kimi" in m.id)
    # cấu hình vai ghi đè bằng JSON (env/SSM) cũng đọc được cờ
    env = {
        "YOFINA_LLM_ROLES": json.dumps({"planner": {"models": [{"id": "x", "prompt_cache": True}]}})
    }
    assert load_settings(Config(env), env=env).roles["planner"][0].prompt_cache is True


def test_env_ghi_de_tran_theo_vai_va_roles_json():
    env = {
        "YOFINA_LLM_DAILY_CAP_PLANNER": "0",
        "YOFINA_LLM_ROLES": json.dumps(
            {"small": {"daily_cap": 7, "models": [{"id": "x", "rpm": 3}]}}
        ),
    }
    s = load_settings(Config(env), env=env)
    assert {m.daily_cap for m in s.roles["planner"]} == {0}  # ghi đè mọi model của vai
    assert s.roles["small"] == (ModelSpec("x", rpm=3, daily_cap=7),)
    assert s.roles["embedding"][0].daily_cap == 3000  # vai khác giữ mặc định


def test_doc_tran_tu_ssm_duong_dan_llm():
    class Ssm:
        class ParameterNotFound(Exception):
            pass

        def get_parameter(self, *, Name, WithDecryption):
            if Name == "/yofina/llm/daily_cap_small":
                return {"Parameter": {"Value": "12"}}
            raise self.ParameterNotFound(Name)

    env = {"YOFINA_SSM_PREFIX": "/yofina"}
    s = load_settings(Config(env, Ssm()), env=env)
    assert {m.daily_cap for m in s.roles["small"]} == {12}
    assert s.roles["planner"][0].daily_cap == 400


def test_roles_json_hong_thi_bao_loi_cau_hinh():
    env = {"YOFINA_LLM_ROLES": "{khong phai json"}
    with pytest.raises(ConfigError, match="roles"):
        load_settings(Config(env), env=env)


# --- giới hạn tốc độ ------------------------------------------------------------------------
def test_cua_so_truot():
    t = [0.0]
    rl = RateLimiter(clock=lambda: t[0])
    assert [rl.try_acquire("m", 2) for _ in range(2)] == [0.0, 0.0]
    wait = rl.try_acquire("m", 2)
    assert wait == pytest.approx(60.0)
    t[0] = 59.0
    assert rl.try_acquire("m", 2) == pytest.approx(1.0)
    t[0] = 60.0
    assert rl.try_acquire("m", 2) == 0.0
    assert rl.try_acquire("khac", 2) == 0.0  # mỗi model một xô
    assert rl.try_acquire("m", 0) == 0.0  # 0 = không giới hạn


def test_cho_toi_da_roi_chuyen_model_ke_tiep():
    t = [0.0]
    sleeps: list[float] = []
    limiter = RateLimiter(clock=lambda: t[0])
    limiter.try_acquire("m-plan-a", 8)  # chiếm 1 chỗ, ta đặt rpm=1 để hết chỗ ngay
    s = settings(
        roles={
            "planner": (
                ModelSpec("m-plan-a", rpm=1, daily_cap=9),
                ModelSpec("m-plan-b", rpm=0, daily_cap=9),
            )
        },
        rate_limit_max_wait_seconds=5,
    )
    client = FakeClient([ok_response("từ b")])
    gw = gateway(client, settings=s, limiter=limiter, sleep=sleeps.append)
    res = gw.converse("planner", messages=[user_message("hi")])
    assert res.model_id == "m-plan-b"
    assert res.attempts == [("m-plan-a", "RateLimitWaitTooLong")]
    assert sleeps == []  # 60 giây > 5 giây nên không chờ


def test_cho_trong_gioi_han_thi_ngu_roi_goi():
    t = [0.0]
    sleeps: list[float] = []

    def fake_sleep(sec: float) -> None:
        sleeps.append(sec)
        t[0] += sec

    limiter = RateLimiter(clock=lambda: t[0])
    limiter.try_acquire("m-plan-a", 1)
    t[0] = 55.0  # còn 5 giây tới khi có chỗ
    s = settings(
        roles={"planner": (ModelSpec("m-plan-a", rpm=1, daily_cap=9),)},
        rate_limit_max_wait_seconds=10,
    )
    gw = gateway(FakeClient([ok_response()]), settings=s, limiter=limiter, sleep=fake_sleep)
    res = gw.converse("planner", messages=[user_message("hi")])
    assert res.model_id == "m-plan-a"
    assert sleeps == [pytest.approx(5.0)]


# --- bộ đếm DynamoDB ------------------------------------------------------------------------
class FakeDdb:
    def __init__(self, error_code: str | None = None) -> None:
        self.kw: dict[str, Any] | None = None
        self.error_code = error_code

    def update_item(self, **kw: Any) -> dict[str, Any]:
        self.kw = kw
        if self.error_code:
            raise ClientError({"Error": {"Code": self.error_code, "Message": "x"}}, "UpdateItem")
        return {"Attributes": {"count": {"N": "4"}}}


def test_dynamo_update_item_co_dieu_kien_va_ten_gia():
    ddb = FakeDdb()
    store = DynamoUsageStore("yofina-usage", ddb)
    n = store.consume(day="2026-11-21", model="m", cap=400, ttl_epoch=123)
    assert n == 4
    kw = ddb.kw
    assert kw["TableName"] == "yofina-usage"
    assert kw["Key"] == {"day": {"S": "2026-11-21"}, "model": {"S": "m"}}
    assert kw["ConditionExpression"] == "attribute_not_exists(#c) OR #c < :cap"
    assert kw["ExpressionAttributeNames"] == {"#c": "count", "#t": "ttl"}  # từ khóa dành riêng
    assert kw["ExpressionAttributeValues"][":cap"] == {"N": "400"}
    assert "ADD #c :one" in kw["UpdateExpression"]


def test_dynamo_cham_tran_thanh_budget_cap_reached():
    store = DynamoUsageStore("t", FakeDdb("ConditionalCheckFailedException"))
    with pytest.raises(BudgetCapReached):
        store.consume(day="d", model="m", cap=1, ttl_epoch=1)


def test_dynamo_loi_khac_khong_bi_nuot():
    store = DynamoUsageStore("t", FakeDdb("ProvisionedThroughputExceededException"))
    with pytest.raises(ClientError):
        store.consume(day="d", model="m", cap=1, ttl_epoch=1)


# --- converse -------------------------------------------------------------------------------
def test_converse_thanh_cong_dem_log_token(caplog):
    usage = FakeUsage()
    scope = TurnScope()
    gw = gateway(FakeClient([ok_response("chào", 11, 7)]), usage)
    with caplog.at_level("INFO", logger="yofina.llm"):
        res = gw.converse("planner", messages=[user_message("hi")], system="s", scope=scope)
    assert res.text == "chào" and res.input_tokens == 11 and res.output_tokens == 7
    assert [(c["day"], c["model"], c["cap"]) for c in usage.calls] == [
        ("2026-11-21", "m-plan-a", 3)
    ]
    assert usage.calls[0]["ttl"] > FIXED_NOW.timestamp()
    line = next(json.loads(r.message) for r in caplog.records if r.name == "yofina.llm")
    assert line["event"] == "llm_call" and line["input_tokens"] == 11 and line["output_tokens"] == 7
    assert line["role"] == "planner" and line["model"] == "m-plan-a" and "latency_ms" in line
    assert scope.calls == 1 and scope.usage_by_model()[0]["totalTokens"] == 18


def test_ngay_dem_theo_mui_gio_ngan_sach():
    usage = FakeUsage()
    gw = LlmGateway(
        settings(),
        config=Config({}),
        client=FakeClient([ok_response()]),
        usage=usage,
        now=lambda: datetime(2026, 11, 21, 20, 0, tzinfo=UTC),  # 03:00 ngày 22 giờ Việt Nam
    )
    gw.converse("small", messages=[user_message("hi")])
    assert usage.calls[0]["day"] == "2026-11-22"


@pytest.mark.parametrize("code", ["ThrottlingException", "AccessDeniedException"])
def test_chuoi_du_phong_bat_throttling_va_access_denied(code):
    client = FakeClient([client_error(code), ok_response("từ b")])
    usage = FakeUsage()
    scope = TurnScope()
    gw = gateway(client, usage)
    res = gw.converse("planner", messages=[user_message("hi")], scope=scope)
    assert res.model_id == "m-plan-b" and res.text == "từ b"
    assert res.attempts == [("m-plan-a", code)]
    assert [c["modelId"] for c in client.calls] == ["m-plan-a", "m-plan-b"]
    # trần ngày đếm cả lần bị từ chối; trần lượt chỉ đếm lời gọi tới model (AG-03)
    assert [c["model"] for c in usage.calls] == ["m-plan-a", "m-plan-b"]
    assert scope.calls == 1
    assert [r.outcome for r in scope.records] == [code, "ok"]
    assert "temperature" in client.calls[0]["inferenceConfig"]
    assert "temperature" not in client.calls[1]["inferenceConfig"]  # model b không nhận temperature


def test_loi_khong_thuoc_chuoi_du_phong_ra_thang():
    gw = gateway(FakeClient([client_error("ValidationException")]))
    with pytest.raises(ClientError):
        gw.converse("planner", messages=[user_message("hi")])


def test_het_chuoi_thi_bao_all_models_failed():
    gw = gateway(
        FakeClient([client_error("ThrottlingException"), client_error("AccessDeniedException")])
    )
    with pytest.raises(AllModelsFailed) as e:
        gw.converse("planner", messages=[user_message("hi")])
    assert e.value.attempts == (
        ("m-plan-a", "ThrottlingException"),
        ("m-plan-b", "AccessDeniedException"),
    )


def test_cham_tran_ngay_khong_roi_sang_model_du_phong():
    usage = FakeUsage(caps_hit={"m-plan-a"})
    client = FakeClient([ok_response()])
    gw = gateway(client, usage)
    with pytest.raises(ModelBudgetExceeded) as e:
        gw.converse("planner", messages=[user_message("hi")])
    assert e.value.model == "m-plan-a" and e.value.reason == "daily_cap" and e.value.cap == 3
    assert client.calls == []  # không gọi model
    assert [c["model"] for c in usage.calls] == ["m-plan-a"]  # không thử model b


def test_tran_bang_0_khong_goi_dynamodb_va_khong_goi_model():
    s = settings(roles={"small": (ModelSpec("x", rpm=0, daily_cap=0),)})
    usage, client = FakeUsage(), FakeClient([ok_response()])
    gw = gateway(client, usage, settings=s)
    with pytest.raises(ModelBudgetExceeded):
        gw.converse("small", messages=[user_message("hi")])
    assert usage.calls == [] and client.calls == []


def test_khong_doc_duoc_bo_dem_thi_dong_cua_an_toan():
    usage = FakeUsage(fail=RuntimeError("DDB sập"))
    client = FakeClient([ok_response()])
    gw = gateway(client, usage)
    with pytest.raises(ModelBudgetExceeded) as e:
        gw.converse("small", messages=[user_message("hi")])
    assert e.value.reason == "usage_store_unavailable"
    assert client.calls == []


def test_tran_moi_luot_hoi_thoai():
    scope = TurnScope(max_calls=1)
    gw = gateway(FakeClient([ok_response(), ok_response()]))
    gw.converse("small", messages=[user_message("hi")], scope=scope)
    with pytest.raises(ModelBudgetExceeded) as e:
        gw.converse("small", messages=[user_message("hi")], scope=scope)
    assert e.value.reason == "turn_limit"


# --- trần lượt và throttle (AG-03, issue #10) -----------------------------------------------
def test_sonnet_throttle_analyst_van_chay_tren_model_du_phong_trong_tran_luot():
    """Kịch bản audit §3.2: router, Orchestrator và Analyst trong trần 4; Sonnet (m-plan-a) throttle cả hai lần."""
    scope = TurnScope(max_calls=4)
    client = FakeClient(
        [
            tool_response("report", {"intent": "what_if"}),  # router (vai small)
            client_error("ThrottlingException"),  # Orchestrator trên Sonnet
            tool_response("report", {"intent": "spec"}),  # Orchestrator trên Kimi
            client_error("ThrottlingException"),  # Analyst trên Sonnet
            tool_response("report", {"intent": "giai_thich"}),  # Analyst trên Kimi
        ]
    )
    gw = gateway(client)
    msgs = [user_message("mua xe 30 triệu được không")]
    gw.structured_json("small", output_model=Out, messages=msgs, scope=scope)
    gw.structured_json("planner", output_model=Out, messages=msgs, scope=scope)
    analyst = asyncio.run(
        gw.astructured_json("planner", output_model=Out, messages=msgs, max_attempts=1, scope=scope)
    )
    assert analyst.model_id == "m-plan-b" and analyst.value.intent == "giai_thich"
    assert scope.calls == 3  # hai lần bị throttle không tính vào trần lượt
    assert [r.outcome for r in scope.records].count("ThrottlingException") == 2  # vẫn ghi lại


def test_bo_gioi_han_toc_do_bo_qua_model_khong_tinh_vao_tran_luot():
    limiter = RateLimiter(clock=lambda: 0.0)
    limiter.try_acquire("m-plan-a", 1)  # hết chỗ, phải chờ 60 s > 5 s
    s = settings(
        roles={
            "planner": (
                ModelSpec("m-plan-a", rpm=1, daily_cap=9),
                ModelSpec("m-plan-b", rpm=0, daily_cap=9),
            )
        },
        rate_limit_max_wait_seconds=5,
    )
    scope, usage = TurnScope(max_calls=1), FakeUsage()
    gw = gateway(FakeClient([ok_response("từ b")]), usage, settings=s, limiter=limiter)
    res = gw.converse("planner", messages=[user_message("hi")], scope=scope)
    assert res.model_id == "m-plan-b" and res.attempts == [("m-plan-a", "RateLimitWaitTooLong")]
    assert scope.calls == 1
    assert [c["model"] for c in usage.calls] == ["m-plan-b"]  # trần ngày cũng không bị đếm


def test_loi_goi_thanh_cong_thu_5_van_cham_tran_4_du_co_throttle():
    scope = TurnScope(max_calls=4)
    client = FakeClient(
        [
            ok_response(),
            client_error("ThrottlingException"),
            ok_response(),
            ok_response(),
            ok_response(),
        ]
    )
    gw = gateway(client)
    for _ in range(4):
        gw.converse("small", messages=[user_message("hi")], scope=scope)
    assert scope.calls == 4 and len(client.calls) == 5
    with pytest.raises(ModelBudgetExceeded) as e:
        gw.converse("small", messages=[user_message("hi")], scope=scope)
    assert e.value.reason == "turn_limit" and len(client.calls) == 5  # không gửi lời gọi thứ 5


def test_strands_throttle_qua_reserve_va_record_tra_lai_cho_trong_luot():
    """Đường của `MeteredModel`: `reserve_async` rồi `record` với tên lỗi của Strands."""
    scope = TurnScope(max_calls=1)
    gw = gateway(FakeClient([]))
    a, b = gw.chain("planner")
    asyncio.run(gw.reserve_async("planner", a, scope))
    gw.record(
        "planner",
        a.id,
        input_tokens=0,
        output_tokens=0,
        latency_ms=3,
        outcome="ModelThrottledException",
        scope=scope,
    )
    asyncio.run(gw.reserve_async("planner", b, scope))  # còn chỗ cho model dự phòng
    gw.record(
        "planner", b.id, input_tokens=5, output_tokens=2, latency_ms=9, outcome="ok", scope=scope
    )
    assert scope.calls == 1
    with pytest.raises(ModelBudgetExceeded):
        asyncio.run(gw.reserve_async("planner", b, scope))


def test_vai_la_khong_co_thi_bao_loi_cau_hinh():
    with pytest.raises(ConfigError):
        gateway(FakeClient([])).chain("khong_co")


# --- JSON có cấu trúc -----------------------------------------------------------------------
class Out(BaseModel):
    intent: str = Field(description="ý định")
    amount: int | None = None


def test_structured_json_hop_le_lan_dau():
    client = FakeClient([tool_response("report", {"intent": "a", "amount": 5})])
    gw = gateway(client)
    r = gw.structured_json("small", output_model=Out, messages=[user_message("hi")], system="s")
    assert r.value == Out(intent="a", amount=5) and r.attempts == 1 and r.model_id == "m-small-a"
    req = client.calls[0]
    assert req["toolConfig"]["toolChoice"] == {"tool": {"name": "report"}}
    assert "outputConfig" not in req  # Nova không hỗ trợ outputConfig


def test_structured_json_sai_schema_thi_gui_loi_va_thu_lai():
    client = FakeClient(
        [tool_response("report", {"amount": "abc"}), tool_response("report", {"intent": "b"})]
    )
    usage = FakeUsage()
    gw = gateway(client, usage)
    r = gw.structured_json("small", output_model=Out, messages=[user_message("hi")], max_attempts=3)
    assert r.value.intent == "b" and r.attempts == 2
    retry_msgs = client.calls[1]["messages"]
    assert retry_msgs[-1]["content"][0]["toolResult"]["status"] == "error"
    assert len(usage.calls) == 2  # mỗi lần thử là một lượt được đếm


def test_structured_json_model_khong_goi_tool_thi_nhac_lai():
    client = FakeClient([ok_response("trả lời chữ"), tool_response("report", {"intent": "c"})])
    gw = gateway(client)
    r = gw.structured_json("small", output_model=Out, messages=[user_message("hi")])
    assert r.attempts == 2 and r.value.intent == "c"


def test_structured_json_het_so_lan_thu():
    client = FakeClient([tool_response("report", {}), tool_response("report", {})])
    gw = gateway(client)
    with pytest.raises(StructuredOutputError) as e:
        gw.structured_json("small", output_model=Out, messages=[user_message("hi")], max_attempts=2)
    assert e.value.attempts == 2 and "intent" in e.value.last_error
    assert len(client.calls) == 2  # chặn vòng lặp không đáy


def test_structured_json_tran_ngay_di_thang_ra_ngoai():
    gw = gateway(FakeClient([]), FakeUsage(caps_hit={"m-small-a"}))
    with pytest.raises(ModelBudgetExceeded):
        gw.structured_json("small", output_model=Out, messages=[user_message("hi")])


def truncated(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Phản hồi dừng ở trần token đầu ra (`stopReason` max_tokens): Bedrock vẫn trả phần đầu vào tool đã sinh được (đo ở #39: lời đáp
    của câu chào mất hẳn, đối tượng `params` dở dang bị bỏ), có thể vẫn khớp schema vì trường cuối là tùy chọn."""
    resp = ok_response("đang viết dở") if payload is None else tool_response("report", payload)
    resp["stopReason"] = "max_tokens"
    return resp


def test_structured_json_bi_cat_o_tran_token_thi_khong_nhan_va_thu_lai():
    client = FakeClient([truncated({"intent": "a"}), tool_response("report", {"intent": "a", "amount": 5})])
    r = gateway(client).structured_json(
        "small", output_model=Out, messages=[user_message("hi")], max_attempts=2, reject_truncated=True
    )
    assert r.value == Out(intent="a", amount=5) and r.attempts == 2
    feedback = client.calls[1]["messages"][-1]["content"][0]["toolResult"]
    assert feedback["status"] == "error" and "bị cắt" in feedback["content"][0]["text"]


def test_structured_json_bi_cat_khong_co_tool_thi_nhac_bang_chu():
    client = FakeClient([truncated(None), tool_response("report", {"intent": "b"})])
    r = gateway(client).structured_json("small", output_model=Out, messages=[user_message("hi")], reject_truncated=True)
    assert r.value.intent == "b"
    assert "bị cắt" in client.calls[1]["messages"][-1]["content"][0]["text"]


def test_structured_json_lan_nao_cung_bi_cat_thi_loi_co_kieu():
    client = FakeClient([truncated({"intent": "a"}), truncated({"intent": "a"})])
    with pytest.raises(StructuredOutputError) as e:
        gateway(client).structured_json(
            "small", output_model=Out, messages=[user_message("hi")], max_attempts=2, reject_truncated=True
        )
    assert e.value.attempts == 2 and "max_tokens" in e.value.last_error


def test_structured_json_mac_dinh_van_nhan_ket_qua_bi_cat_hop_le():
    """Vai khác giữ hành vi cũ (chỉ router bật `reject_truncated`): đổi cho cả vai nạp hay phân loại cần đo riêng."""
    client = FakeClient([truncated({"intent": "a"})])
    r = gateway(client).structured_json("small", output_model=Out, messages=[user_message("hi")])
    assert r.value == Out(intent="a") and r.attempts == 1


# --- prompt caching (#24) ---------------------------------------------------------------------
CACHE_POINT = {"cachePoint": {"type": "default"}}


def cached_settings() -> LlmSettings:
    """Vai planner: model a bật cache (như Sonnet 4.6), model b tắt (như Kimi K3)."""
    return settings(
        roles={
            "planner": (
                ModelSpec("m-plan-a", rpm=0, daily_cap=9, prompt_cache=True),
                ModelSpec("m-plan-b", rpm=0, daily_cap=9, temperature=False),
            )
        }
    )


def test_cache_bat_thi_co_cache_point_sau_system_va_sau_tool():
    client = FakeClient([tool_response("report", {"intent": "a"})])
    gw = gateway(client, settings=cached_settings())
    gw.structured_json("planner", output_model=Out, messages=[user_message("hi")], system="quy tắc")
    req = client.calls[0]
    assert req["system"] == [{"text": "quy tắc"}, CACHE_POINT]
    tools = req["toolConfig"]["tools"]
    assert [next(iter(t)) for t in tools] == ["toolSpec", "cachePoint"] and tools[-1] == CACHE_POINT
    assert tools[0]["toolSpec"]["name"] == "report"
    assert req["toolConfig"]["toolChoice"] == {"tool": {"name": "report"}}
    assert "cachePoint" not in json.dumps(
        req["messages"]
    )  # phần thay đổi theo lượt không bị đánh dấu


def test_cache_tat_hoac_kimi_du_phong_thi_khong_co_cache_point():
    """Sonnet bị throttle, rẽ sang model tắt cache (Kimi K3 trả ValidationException nếu thấy cachePoint): request thứ hai sạch."""
    client = FakeClient(
        [client_error("ThrottlingException"), tool_response("report", {"intent": "b"})]
    )
    gw = gateway(client, settings=cached_settings())
    r = gw.structured_json(
        "planner", output_model=Out, messages=[user_message("hi")], system="quy tắc"
    )
    assert r.model_id == "m-plan-b"
    first, second = client.calls
    assert "cachePoint" in json.dumps(first["system"]) and "cachePoint" in json.dumps(
        first["toolConfig"]
    )
    assert "cachePoint" not in json.dumps(second)
    assert second["system"] == [{"text": "quy tắc"}]
    # model tắt cache ngay từ đầu chuỗi (mặc định của ModelSpec) cũng không có
    plain = FakeClient([ok_response()])
    gateway(plain).converse("small", messages=[user_message("hi")], system="s")
    assert "cachePoint" not in json.dumps(plain.calls[0])


def cached_usage_response(tin: int, tout: int, read: int, write: int) -> dict[str, Any]:
    resp = ok_response("chào", tin, tout)
    resp["usage"].update({"cacheReadInputTokens": read, "cacheWriteInputTokens": write})
    return resp


def test_doc_token_cache_doc_ghi_vao_ket_qua_log_va_luot(caplog):
    """Bedrock: có cache thì `inputTokens` chỉ còn phần không qua cache. Tổng token vào giữ nghĩa cũ (đủ mọi token đã gửi, như
    AG-UI `TokenUsage.inputTokens`), phần đọc/ghi cache tách riêng để log và trace đếm được."""
    scope = TurnScope()
    client = FakeClient(
        [cached_usage_response(40, 9, 0, 1_500), cached_usage_response(45, 7, 1_500, 0)]
    )
    gw = gateway(client, settings=cached_settings())
    with caplog.at_level("INFO", logger="yofina.llm"):
        first = gw.converse("planner", messages=[user_message("a")], system="s", scope=scope)
        second = gw.converse("planner", messages=[user_message("b")], system="s", scope=scope)
    assert (first.input_tokens, first.cache_write_tokens, first.cache_read_tokens) == (
        1_540,
        1_500,
        0,
    )
    assert (second.input_tokens, second.cache_read_tokens, second.cache_write_tokens) == (
        1_545,
        1_500,
        0,
    )
    lines = [json.loads(r.message) for r in caplog.records if r.name == "yofina.llm"]
    calls = [ln for ln in lines if ln["event"] == "llm_call"]
    assert [
        (c["input_tokens"], c["cache_read_tokens"], c["cache_write_tokens"]) for c in calls
    ] == [
        (1_540, 0, 1_500),
        (1_545, 1_500, 0),
    ]
    (u,) = scope.usage_by_model()
    assert u["inputTokens"] == 3_085 and u["outputTokens"] == 16 and u["totalTokens"] == 3_101
    assert u["cachedInputTokens"] == 1_500 and u["cacheWriteInputTokens"] == 1_500


def test_khong_co_cache_thi_dang_usage_cua_luot_khong_doi():
    scope = TurnScope()
    gateway(FakeClient([ok_response("chào", 11, 7)])).converse(
        "small", messages=[user_message("hi")], scope=scope
    )
    assert scope.usage_by_model() == [
        {
            "provider": "bedrock",
            "model": "m-small-a",
            "inputTokens": 11,
            "outputTokens": 7,
            "totalTokens": 18,
        }
    ]


def test_schema_phang_khong_con_ref_va_moi_truong_la_required():
    class Inner(BaseModel):
        k: int

    class Outer(BaseModel):
        name: str
        maybe: int | None = None
        inner: Inner
        kind: str | None = Field(default=None, description="mô tả")

    schema = bedrock_json_schema(Outer)
    text = json.dumps(schema)
    assert (
        "$ref" not in text and "$defs" not in text and "anyOf" not in text and "title" not in text
    )
    assert schema["required"] == ["name", "maybe", "inner", "kind"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["maybe"]["type"] == ["integer", "null"]
    assert schema["properties"]["inner"]["properties"]["k"]["type"] == "integer"
    assert schema["properties"]["kind"]["description"] == "mô tả"


def test_schema_require_all_false_chi_bat_buoc_truong_khong_co_mac_dinh():
    """Router (#39): schema chỉ bắt buộc trường không có mặc định, ở mọi tầng; vẫn phẳng, vẫn cấm trường lạ."""

    class Inner(BaseModel):
        k: int
        opt: str | None = None

    class Outer(BaseModel):
        name: str
        maybe: int | None = None
        inner: Inner | None = None

    schema = bedrock_json_schema(Outer, require_all=False)
    assert schema["required"] == ["name"]
    assert schema["additionalProperties"] is False
    inner = schema["properties"]["inner"]
    assert inner["type"] == ["object", "null"] and inner["required"] == ["k"]
    assert inner["additionalProperties"] is False
    assert "$ref" not in json.dumps(schema) and "anyOf" not in json.dumps(schema)
    default = bedrock_json_schema(Outer)
    assert default["required"] == ["name", "maybe", "inner"]  # mặc định không đổi


def test_structured_json_require_all_fields_false_gui_schema_khong_bat_buoc_moi_truong():
    client = FakeClient([tool_response("report", {"intent": "a"})])
    r = gateway(client).structured_json(
        "small", output_model=Out, messages=[user_message("x")], require_all_fields=False
    )
    assert r.value == Out(intent="a")
    tool = client.calls[0]["toolConfig"]["tools"][0]["toolSpec"]
    assert tool["inputSchema"]["json"]["required"] == ["intent"]


def test_schema_giu_field_ten_title_va_default():
    """Field tên `title`/`default` là dữ liệu (vd. dàn ý lộ trình), không phải khóa mô tả của pydantic: phải còn trong schema,
    nếu không model không gửi được field bắt buộc và mọi lần gọi đều hỏng xác thực."""

    class Step(BaseModel):
        title: str
        default: int | None = None

    class Phase(BaseModel):
        title: str = Field(min_length=1)
        steps: list[Step]

    schema = bedrock_json_schema(Phase)
    assert schema["required"] == ["title", "steps"]
    assert schema["properties"]["title"] == {"minLength": 1, "type": "string"}
    step = schema["properties"]["steps"]["items"]
    assert step["required"] == ["title", "default"]
    assert step["properties"]["default"]["type"] == ["integer", "null"]
    assert "title" not in step and "title" not in schema  # khóa mô tả của model vẫn bị bỏ


# --- nguồn SSM gộp ---------------------------------------------------------------------------
class FakeSsmBulk:
    def __init__(self, params: dict[str, str], fail: bool = False) -> None:
        self.params, self.fail = params, fail
        self.path_calls: list[dict[str, Any]] = []
        self.single_calls: list[str] = []

    def get_parameters_by_path(self, **kw: Any) -> dict[str, Any]:
        self.path_calls.append(kw)
        if self.fail:
            raise RuntimeError("AccessDenied")
        names = sorted(n for n in self.params if n.startswith(kw["Path"] + "/"))
        start = int(kw.get("NextToken", 0))
        page = names[start : start + 1]  # mỗi trang một khóa: kiểm phân trang
        out: dict[str, Any] = {"Parameters": [{"Name": n, "Value": self.params[n]} for n in page]}
        if start + 1 < len(names):
            out["NextToken"] = str(start + 1)
        return out

    def get_parameter(self, *, Name: str, WithDecryption: bool) -> dict[str, Any]:
        self.single_calls.append(Name)
        return {"Parameter": {"Value": self.params[Name]}}


def test_ssm_gop_mot_loi_goi_cho_ca_nhanh_llm_va_phan_trang():
    from yofina_core.llm import BulkSsm

    ssm = FakeSsmBulk(
        {
            "/yofina/llm/daily_cap_small": "5",
            "/yofina/llm/usage_ttl_days": "9",
            "/yofina/other": "x",
        }
    )
    env = {"YOFINA_SSM_PREFIX": "/yofina"}
    s = load_settings(Config(env, BulkSsm("/yofina", "ap-southeast-1", client=ssm)), env=env)
    assert {m.daily_cap for m in s.roles["small"]} == {5} and s.usage_ttl_days == 9
    assert s.roles["planner"][0].daily_cap == 400  # khóa vắng: mặc định
    assert (
        len(ssm.path_calls) == 2 and ssm.single_calls == []
    )  # 2 trang, không GetParameter nào cho khóa llm


def test_ssm_khoa_ngoai_nhanh_llm_di_thang_get_parameter():
    from yofina_core.llm import BulkSsm

    ssm = FakeSsmBulk({"/yofina/dynamodb/usage-table": "yofina-usage"})
    cfg = Config({"YOFINA_SSM_PREFIX": "/yofina"}, BulkSsm("/yofina", "ap-southeast-1", client=ssm))
    assert cfg.get("dynamodb/usage-table") == "yofina-usage"
    assert ssm.single_calls == ["/yofina/dynamodb/usage-table"] and ssm.path_calls == []


def test_khong_doc_duoc_nhanh_llm_thi_dung_mac_dinh_va_ghi_log_loi(caplog):
    from yofina_core.llm import BulkSsm

    ssm = FakeSsmBulk({}, fail=True)
    env = {"YOFINA_SSM_PREFIX": "/yofina"}
    with caplog.at_level("ERROR", logger="yofina.llm"):
        s = load_settings(Config(env, BulkSsm("/yofina", "ap-southeast-1", client=ssm)), env=env)
    assert s.roles["small"][0].daily_cap == 2000  # trần mặc định vẫn có hiệu lực
    assert any("llm_ssm_unreadable" in r.message for r in caplog.records)
    assert len(ssm.path_calls) == 1  # chỉ thử một lần
