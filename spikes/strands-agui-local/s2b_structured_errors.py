"""Mục 2 (tiếp): lỗi validate, giới hạn attempts, API cũ. Chạy: python s2b_structured_errors.py <d|e|f|g>"""
import sys, json, warnings
from datetime import date
from pydantic import BaseModel, field_validator
from strands import Agent
from strands.types.exceptions import StructuredOutputException
from common import model
from schemas import IntentResult

WHICH = sys.argv[1]

class FutureSpec(BaseModel):
    start_date: str
    amount_vnd: int
    @field_validator("start_date")
    @classmethod
    def future(cls, v):
        if date.fromisoformat(v) <= date(2026, 11, 21):
            raise ValueError("start_date phải SAU 2026-11-21; hãy chọn ngày sau đó")
        return v

class Impossible(BaseModel):
    x: int
    @field_validator("x")
    @classmethod
    def never(cls, v):
        raise ValueError("luôn sai")

def dump(ag):
    for m in ag.messages:
        print("  ", m["role"], json.dumps(m["content"], ensure_ascii=False)[:300])

if WHICH == "d":
    print("== 2d: validator Pydantic: ngày phải ở tương lai, người dùng nói ngày quá khứ")
    ag = Agent(model=model(512), system_prompt="Dựng spec. Dùng đúng ngày người dùng nói trừ khi bị báo lỗi.", callback_handler=None)
    try:
        r = ag("Khoản chi 1 triệu bắt đầu ngày 2026-01-05", structured_output_model=FutureSpec, limits={"structured_output_attempts": 3})
        print("stop_reason:", r.stop_reason, "so:", r.structured_output)
    except Exception as e:
        print("EXC", type(e).__name__, str(e)[:300])
    dump(ag)
elif WHICH == "e":
    print("== 2e: validator không thể thỏa, attempts=2")
    ag = Agent(model=model(256), callback_handler=None)
    try:
        r = ag("x = 5", structured_output_model=Impossible, limits={"structured_output_attempts": 2})
        print("stop_reason:", r.stop_reason, "so:", r.structured_output)
    except Exception as e:
        print("EXC", type(e).__name__, str(e)[:300])
    dump(ag)
elif WHICH == "f":
    print("== 2f: validator không thể thỏa, KHÔNG đặt limits (cần timeout cứng)")
    ag = Agent(model=model(256), callback_handler=None)
    try:
        r = ag("x = 5", structured_output_model=Impossible)
        print("stop_reason:", r.stop_reason, "so:", r.structured_output)
    except Exception as e:
        print("EXC", type(e).__name__, str(e)[:300])
    print("số message:", len(ag.messages))
elif WHICH == "g":
    print("== 2g: API cũ agent.structured_output()")
    ag = Agent(model=model(256), callback_handler=None)
    print("hasattr structured_output:", hasattr(ag, "structured_output"), "| structured_output_async:", hasattr(ag, "structured_output_async"))
    if hasattr(ag, "structured_output"):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            try:
                o = ag.structured_output(IntentResult, "Mình muốn chuyển 300k từ giải trí sang ăn uống")
                print("OK", o)
            except Exception as e:
                print("EXC", type(e).__name__, str(e)[:300])
            print("warnings:", [(x.category.__name__, str(x.message)[:200]) for x in w])
