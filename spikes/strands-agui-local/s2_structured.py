"""Mục 2: structured output."""
import asyncio, json, inspect
from strands import Agent
from strands.types.exceptions import StructuredOutputException
from common import model
from schemas import IntentResult, ScenarioSpec

print("== 2a: IntentResult qua structured_output_model")
a = Agent(model=model(512), system_prompt="Phân loại ý định tài chính.", callback_handler=None)
r = a("Mình muốn chuyển 300k từ giải trí sang ăn uống", structured_output_model=IntentResult, limits={"turns": 3, "structured_output_attempts": 3})
print("stop_reason:", r.stop_reason, "type:", type(r.structured_output).__name__)
print(r.structured_output.model_dump_json())
print("text của result:", repr(str(r))[:150])
print("usage:", r.metrics.accumulated_usage)

print("\n== 2b: ScenarioSpec (lồng, Literal, ge=0) -- invoke_async")
async def main():
    ag = Agent(model=model(512), system_prompt="Dựng ScenarioSpec từ mô tả. Hôm nay là 2026-11-21.", callback_handler=None)
    r = await ag.invoke_async("Mua laptop 18 triệu, trả góp 6 tháng, trừ hũ giải trí, bắt đầu từ đầu tháng sau, không được làm hụt hũ ăn uống",
                              structured_output_model=ScenarioSpec, limits={"structured_output_attempts": 3})
    print("stop_reason:", r.stop_reason)
    print(r.structured_output.model_dump_json(indent=None))
    return r
asyncio.run(main())

print("\n== 2c: JSON schema của tool structured output (có gây lỗi 400 không?) -> đã chạy ở 2b, không lỗi")
print(json.dumps(ScenarioSpec.model_json_schema(), ensure_ascii=False)[:600])

print("\n== 2d: lỗi validate: validator Pydantic buộc ngày ở tương lai, model đưa ngày quá khứ")
from pydantic import BaseModel, field_validator
from datetime import date
class FutureSpec(BaseModel):
    start_date: str
    amount_vnd: int
    @field_validator("start_date")
    @classmethod
    def future(cls, v):
        if date.fromisoformat(v) <= date(2026, 11, 21):
            raise ValueError("start_date phải SAU 2026-11-21; hãy chọn ngày sau đó")
        return v
ag = Agent(model=model(512), system_prompt="Dựng spec. Dùng đúng ngày người dùng nói.", callback_handler=None)
try:
    r = ag("Khoản chi 1 triệu bắt đầu ngày 2026-01-05", structured_output_model=FutureSpec, limits={"structured_output_attempts": 3})
    print("stop_reason:", r.stop_reason, "so:", r.structured_output)
    for m in ag.messages:
        print(m["role"], json.dumps(m["content"], ensure_ascii=False)[:260])
except Exception as e:
    print("EXC", type(e).__name__, str(e)[:300])
    for m in ag.messages:
        print(m["role"], json.dumps(m["content"], ensure_ascii=False)[:260])

print("\n== 2e: attempts=1 với validator không thể thỏa")
class Impossible(BaseModel):
    x: int
    @field_validator("x")
    @classmethod
    def never(cls, v):
        raise ValueError("luôn sai")
ag = Agent(model=model(256), callback_handler=None)
try:
    r = ag("x = 5", structured_output_model=Impossible, limits={"structured_output_attempts": 2})
    print("stop_reason:", r.stop_reason, "so:", r.structured_output)
except Exception as e:
    print("EXC", type(e).__name__, str(e)[:300])

print("\n== 2f: không đặt limits, validator không thể thỏa")
ag = Agent(model=model(256), callback_handler=None)
try:
    r = ag("x = 5", structured_output_model=Impossible)
    print("stop_reason:", r.stop_reason, "so:", r.structured_output)
except Exception as e:
    print("EXC", type(e).__name__, str(e)[:300])

print("\n== 2g: agent.structured_output() cũ còn không?")
ag = Agent(model=model(256), callback_handler=None)
print("hasattr structured_output:", hasattr(ag, "structured_output"), "hasattr structured_output_async:", hasattr(ag, "structured_output_async"))
if hasattr(ag, "structured_output"):
    import warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            o = ag.structured_output(IntentResult, "Mình muốn chuyển 300k từ giải trí sang ăn uống")
            print("OK", o)
        except Exception as e:
            print("EXC", type(e).__name__, str(e)[:300])
        print("warnings:", [(x.category.__name__, str(x.message)[:200]) for x in w])
