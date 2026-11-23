"""Gộp kịch bản trong một cuộc trò chuyện, chạy thật qua Runtime (Gateway, Lambda forecast, Aurora, Bedrock thật).

Cùng một phiên: hỏi giày -> hỏi dép cùng hũ -> agent hỏi giữ hay bỏ giày -> bấm "Vẫn giữ" -> MỘT mô phỏng gộp cả hai.
Lịch sử gửi đi dựng giống frontend: tin trợ lý = `fallback_text` của các khối rồi phần chữ (frontend/src/chat/session.ts).
Chạy: `uv run pytest tests/integration/test_whatif_bundle_live.py -m integration`.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import pytest
from agentcore_helpers import invoke_agent, new_session_id

pytestmark = pytest.mark.usefixtures("fresh")

GIAY_Q = "Nếu mua giày 400 nghìn từ hũ Giải trí thì sao"
DEP_Q = "Nếu mua dép 200 nghìn từ hũ Giải trí thì sao"
KEEP_CHIP = "Vẫn giữ khoản trước, tính gộp cả hai"
DROP_CHIP = "Bỏ khoản trước, chỉ tính khoản mới"
PACE = 8


def ask(agent_url: str, token: str, messages: list[dict[str, Any]], sid: str):
    run = invoke_agent(agent_url, token, None, messages=messages, session_id=sid, timeout=150)
    assert run.status == 200, (run.status, run.raw[:500])
    assert run.finished is not None and "RUN_ERROR" not in run.types, run.types
    return run


def assistant_history(run) -> str:
    """Giống `assistantHistoryText` của frontend."""
    parts = [b["fallback_text"].strip() for b in run.blocks if (b.get("fallback_text") or "").strip()]
    if run.text.strip():
        parts.append(run.text.strip())
    return "\n".join(parts)


def tool_args(run, short: str) -> list[dict[str, Any]]:
    names = {e["toolCallId"]: e.get("toolCallName", "") for e in run.events if e.get("type") == "TOOL_CALL_START"}
    out: dict[str, str] = {}
    for e in run.events:
        if e.get("type") == "TOOL_CALL_ARGS" and names.get(e["toolCallId"], "").endswith(f"___{short}"):
            out[e["toolCallId"]] = out.get(e["toolCallId"], "") + e.get("delta", "")
    return [json.loads(v) for v in out.values()]


def msg(role: str, content: str) -> dict[str, Any]:
    return {"id": f"{role[0]}-{uuid.uuid4().hex[:8]}", "role": role, "content": content}


def _two_questions(agent_url: str, tokens: dict[str, str]):
    sid = new_session_id()
    history = [msg("user", GIAY_Q)]
    r1 = ask(agent_url, tokens["minh"], history, sid)
    assert r1.blocks_of("forecast_timeline"), r1.types
    (a1,) = tool_args(r1, "run_scenario")
    assert a1["conversation_id"] == sid and "with_scenarios" not in a1
    history += [msg("assistant", assistant_history(r1)), msg("user", DEP_Q)]
    time.sleep(PACE)
    r2 = ask(agent_url, tokens["minh"], history, sid)
    return sid, history, r2


def test_hoi_giu_hay_bo_roi_giu_thi_mo_phong_gop(agent_url, tokens):
    sid, history, r2 = _two_questions(agent_url, tokens)
    (clarify,) = r2.blocks_of("clarify")
    q = clarify["data"]["question"]
    assert "Bạn vẫn giữ ý định đó chứ?" in q and "giày" in q and "dép" in q, q
    assert not tool_args(r2, "run_scenario"), "chưa trả lời giữ hay bỏ thì chưa chạy mô phỏng"
    assert [c["value"] for c in clarify["data"]["chips"]] == [KEEP_CHIP, DROP_CHIP]

    history += [msg("assistant", assistant_history(r2)), msg("user", KEEP_CHIP)]
    time.sleep(PACE)
    r3 = ask(agent_url, tokens["minh"], history, sid)
    (a3,) = tool_args(r3, "run_scenario")
    assert a3["scenario"]["amount_vnd"] == 200_000, a3
    assert [s["amount_vnd"] for s in a3["with_scenarios"]] == [400_000], a3
    assert a3["conversation_id"] == sid
    assert r3.blocks_of("forecast_timeline"), r3.types
    assert r3.finished["result"]["intent"] == "what_if"
    # xem bằng `pytest -s`: câu hỏi giữ/bỏ và câu trả lời gộp đúng như người dùng thấy
    print("\n[lượt 2]", q, "\n[lượt 3]", assistant_history(r3).replace("\n", " | "))
    print("[lượt 3 khối]", [b["type"] for b in r3.blocks], "[kết quả]", r3.finished.get("result"))


def test_bo_khoan_truoc_thi_chi_tinh_khoan_moi_va_lan_sau_khong_hoi_lai_khoan_da_bo(agent_url, tokens):
    sid, history, r2 = _two_questions(agent_url, tokens)
    assert r2.blocks_of("clarify")
    history += [msg("assistant", assistant_history(r2)), msg("user", DROP_CHIP)]
    time.sleep(PACE)
    r3 = ask(agent_url, tokens["minh"], history, sid)
    (a3,) = tool_args(r3, "run_scenario")
    assert a3["scenario"]["amount_vnd"] == 200_000 and "with_scenarios" not in a3

    # khoản thứ ba cùng hũ: chỉ còn dép để hỏi (giày đã bỏ)
    history += [msg("assistant", assistant_history(r3)), msg("user", "Nếu mua áo 150 nghìn từ hũ Giải trí thì sao")]
    time.sleep(PACE)
    r4 = ask(agent_url, tokens["minh"], history, sid)
    (clarify,) = r4.blocks_of("clarify")
    q = clarify["data"]["question"]
    assert "dép" in q and "giày" not in q, q
