"""Mục 7 (thuần Strands, chưa qua AG-UI): tool_context.interrupt + FileSessionManager, và HumanInTheLoop (interventions).

Chạy: python s7a_native_interrupt.py tool|hitl
"""
import json, shutil, sys, tempfile
from pathlib import Path
from strands import Agent, tool
from strands.session.file_session_manager import FileSessionManager
from common import model

SIDE = []


@tool(context=True)
def move_between_jars(from_jar: str, to_jar: str, amount_vnd: int, tool_context) -> dict:
    """Chuyển tiền giữa hai hũ (GHI, cần xác nhận).

    Args:
        from_jar: hũ nguồn
        to_jar: hũ đích
        amount_vnd: số tiền VND
    """
    SIDE.append("pre-interrupt code ran")
    ans = tool_context.interrupt("yofina-confirm-move", reason={"amount_vnd": amount_vnd})
    SIDE.append(f"post-interrupt, ans={ans!r}")
    if ans != "approve":
        return {"status": "cancelled"}
    return {"status": "done", "amount_vnd": amount_vnd}


mode = sys.argv[1]
tmp = Path(tempfile.mkdtemp(prefix="sess_"))
try:
    if mode == "tool":
        sm = FileSessionManager(session_id="n1", storage_dir=str(tmp))
        a = Agent(model=model(512), tools=[move_between_jars], agent_id="n-agent", session_manager=sm, callback_handler=None)
        r = a("Chuyển 200000 từ giai_tri sang an_uong")
        print("stop_reason:", r.stop_reason)
        for i in r.interrupts:
            print("interrupt:", i.id, i.name, i.reason)
        # Agent MỚI (mô phỏng tiến trình mới) cùng session_id + agent_id
        sm2 = FileSessionManager(session_id="n1", storage_dir=str(tmp))
        b = Agent(model=model(512), tools=[move_between_jars], agent_id="n-agent", session_manager=sm2, callback_handler=None)
        r2 = b([{"interruptResponse": {"interruptId": r.interrupts[0].id, "response": "approve"}}])
        print("resume stop_reason:", r2.stop_reason, "| text:", str(r2).strip()[:120])
        print("side effects:", SIDE)
    else:
        from strands.vended_interventions import HumanInTheLoop

        @tool
        def get_jar_balances() -> dict:
            """Số dư các hũ."""
            return {"an_uong": 1250000}

        @tool
        def move_plain(from_jar: str, to_jar: str, amount_vnd: int) -> dict:
            """Chuyển tiền giữa hai hũ (GHI).

            Args:
                from_jar: hũ nguồn
                to_jar: hũ đích
                amount_vnd: số tiền
            """
            SIDE.append("move_plain ran")
            return {"status": "done"}

        sm = FileSessionManager(session_id="n2", storage_dir=str(tmp))
        a = Agent(model=model(512), tools=[get_jar_balances, move_plain], agent_id="h-agent", session_manager=sm,
                  interventions=[HumanInTheLoop(allowed_tools=["get_jar_balances"])], callback_handler=None)
        r = a("Chuyển 200000 từ giai_tri sang an_uong")
        print("stop_reason:", r.stop_reason)
        for i in r.interrupts:
            print("interrupt:", i.id, "| name:", i.name, "| reason:", json.dumps(i.reason, ensure_ascii=False, default=str)[:300])
        r2 = a([{"interruptResponse": {"interruptId": r.interrupts[0].id, "response": "y"}}])
        print("resume (response='y') stop_reason:", r2.stop_reason, "| side:", SIDE, "|", str(r2).strip()[:100])
finally:
    shutil.rmtree(tmp, ignore_errors=True)
