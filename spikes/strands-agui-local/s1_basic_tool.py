"""Mục 1: agent + @tool tất định + limits."""
import json
from strands import Agent, tool
from common import model, JARS

CALLS = []

@tool
def get_jar_balances() -> dict:
    """Lấy số dư hiện tại của các hũ chi tiêu của người dùng (VND)."""
    CALLS.append("get_jar_balances")
    return JARS

SYS = "Bạn là trợ lý tài chính Yofina. Trả lời ngắn gọn bằng tiếng Việt. Số liệu lấy từ tool."

print("== 1a: bình thường")
a = Agent(model=model(512), system_prompt=SYS, tools=[get_jar_balances], callback_handler=None)
r = a("Hũ ăn uống còn bao nhiêu?")
print("stop_reason:", r.stop_reason)
print("text:", str(r).strip())
print("calls:", CALLS, "usage:", r.metrics.accumulated_usage, "cycles:", r.metrics.cycle_count)
print("limits kwarg signature check:")
import inspect
print(inspect.signature(a.__call__))

print("\n== 1b: limits turns=1 (cần 2 vòng: tool + trả lời)")
CALLS.clear()
a = Agent(model=model(512), system_prompt=SYS, tools=[get_jar_balances], callback_handler=None)
try:
    r = a("Hũ ăn uống còn bao nhiêu?", limits={"turns": 1})
    print("stop_reason:", r.stop_reason)
    print("text:", repr(str(r))[:200])
    print("last message:", json.dumps(r.message, ensure_ascii=False)[:300])
    print("calls:", CALLS)
except Exception as e:
    print("EXC", type(e).__name__, e)

print("\n== 1c: limits total_tokens=50")
CALLS.clear()
a = Agent(model=model(512), system_prompt=SYS, tools=[get_jar_balances], callback_handler=None)
try:
    r = a("Hũ ăn uống còn bao nhiêu?", limits={"total_tokens": 50})
    print("stop_reason:", r.stop_reason, "text:", repr(str(r))[:200], "calls:", CALLS, r.metrics.accumulated_usage)
except Exception as e:
    print("EXC", type(e).__name__, e)

print("\n== 1d: limits output_tokens=5")
CALLS.clear()
a = Agent(model=model(512), system_prompt=SYS, tools=[get_jar_balances], callback_handler=None)
try:
    r = a("Hũ ăn uống còn bao nhiêu?", limits={"output_tokens": 5})
    print("stop_reason:", r.stop_reason, "text:", repr(str(r))[:200], "calls:", CALLS, r.metrics.accumulated_usage)
except Exception as e:
    print("EXC", type(e).__name__, e)

print("\n== 1e: khóa limits sai")
a = Agent(model=model(64), callback_handler=None)
try:
    r = a("hi", limits={"max_turns": 1})
    print("stop_reason:", r.stop_reason)
except Exception as e:
    print("EXC", type(e).__name__, e)
