"""Mục 3: stream_async, liệt kê khóa event theo thứ tự."""
import asyncio, json
from strands import Agent, tool
from common import model, JARS

@tool
def get_jar_balances() -> dict:
    """Lấy số dư hiện tại của các hũ chi tiêu của người dùng (VND)."""
    return JARS

async def main():
    a = Agent(model=model(512), system_prompt="Trợ lý Yofina, trả lời ngắn tiếng Việt, dùng tool lấy số.",
              tools=[get_jar_balances], callback_handler=None)
    seq = []          # (khóa, tóm tắt)
    async for ev in a.stream_async("Hũ ăn uống còn bao nhiêu?"):
        keys = sorted(ev.keys())
        # gom liên tiếp cùng nhóm khóa
        sig = tuple(k for k in keys if k not in ("agent", "event_loop_cycle_id", "request_state", "event_loop_cycle_span", "event_loop_parent_cycle_id", "event_loop_cycle_trace"))
        brief = {}
        for k in sig:
            v = ev[k]
            if k == "event":
                brief[k] = list(v.keys())[0] if isinstance(v, dict) else str(type(v))
            elif k == "delta":
                brief[k] = list(v.keys()) if isinstance(v, dict) else str(v)[:30]
            elif k == "message":
                brief[k] = {"role": v["role"], "content_types": [list(c.keys())[0] for c in v["content"]]}
            elif k == "current_tool_use":
                brief[k] = {"name": v.get("name"), "input": v.get("input")}
            elif k == "result":
                brief[k] = {"stop_reason": v.stop_reason}
            elif isinstance(v, str):
                brief[k] = v[:30]
            else:
                brief[k] = type(v).__name__
        seq.append((sig, brief))
    # nén các dòng liên tiếp giống nhau
    out = []
    for sig, brief in seq:
        key = json.dumps(brief, ensure_ascii=False, sort_keys=True, default=str)
        if out and out[-1][0] == sig and out[-1][2] == "same":
            pass
        out.append([sig, brief, ""])
    prev = None; cnt = 0; lines = []
    for sig, brief, _ in out:
        k = sig
        if k == prev:
            cnt += 1
        else:
            if prev is not None: lines.append((prev, cnt, last))
            prev = k; cnt = 1
        last = brief
    lines.append((prev, cnt, last))
    for sig, cnt, b in lines:
        print(f"x{cnt:<3} {list(sig)} {json.dumps(b, ensure_ascii=False, default=str)[:200]}")

    print("\n-- chuỗi đầy đủ khóa (không gộp), 60 đầu:")
    for sig, brief in seq[:60]:
        print(list(sig))
asyncio.run(main())
