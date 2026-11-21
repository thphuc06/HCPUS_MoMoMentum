"""2f chi tiết: không đặt limits, validator không thể thỏa -> đếm số lần gọi model (dừng cưỡng bức sau 6 lần)."""
import threading
from pydantic import BaseModel, field_validator
from strands import Agent
from strands.hooks import AfterModelCallEvent
from common import model

class Impossible(BaseModel):
    x: int
    @field_validator("x")
    @classmethod
    def never(cls, v):
        raise ValueError("luôn sai")

n = 0
cancel = threading.Event()
def on_model(ev):
    global n
    n += 1
    print("model call", n)
    if n >= 6:
        cancel.set()
ag = Agent(model=model(256), callback_handler=None)
ag.add_hook(on_model, AfterModelCallEvent)
try:
    r = ag("x = 5", structured_output_model=Impossible, cancel_signal=cancel)
    print("stop_reason:", r.stop_reason, "so:", r.structured_output)
except Exception as e:
    print("EXC", type(e).__name__, str(e)[:300])
print("total model calls:", n)
