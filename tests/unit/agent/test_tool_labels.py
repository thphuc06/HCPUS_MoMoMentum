"""Mọi tool và mọi bước agent ghi đều có nhãn tiếng Việt (đi cảnh 24/11: lượt lập lộ trình hiện nhiều dòng "Đã xử lý").

Lỗi gốc: nhãn tiến độ của thẻ "Yofina đã làm" (`frontend/src/chat/errors.ts`) và nhãn nguồn dữ liệu của bảng "Vì sao" (`trace.TOOL_LABELS`)
chỉ có các tool tới phase 3; tool phase 4–5 (`get_roadmap`, `optimize_allocation`, `save_roadmap`, `stress_test`, `get_resilience_score`,
`get_behavior_profile`, `ingest___*`...) rơi về "Đã xử lý" hoặc mã thô, và bước `roadmap_<chặng>` hiện mã thô ("Bước roadmap_draft").
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import get_args

from yofina_agent import trace

from yofina_core.roadmap import JobStage

REPO = Path(__file__).resolve().parents[3]
FRONT_TOOLS = REPO / "frontend/src/chat/errors.ts"
FRONT_STEPS = REPO / "frontend/src/features/explain/stepLabels.ts"
AGENT_SRC = REPO / "agent/src/yofina_agent"


def contract_tools() -> set[str]:
    names: set[str] = set()
    for f in (REPO / "contracts/tools").glob("*.json"):
        if f.name.endswith(".results.schema.json"):
            continue
        names |= {t["name"] for t in json.loads(f.read_text(encoding="utf-8"))}
    return names


def agent_steps() -> set[str]:
    """Tên bước không phải tool mà agent ghi: `.step("x")` trong mã, và `roadmap_<chặng>` cho mỗi `JobStage`."""
    found: set[str] = set()
    for f in AGENT_SRC.glob("*.py"):
        found |= set(re.findall(r"\.step\(\"([a-z][a-z0-9_]*)\"\)", f.read_text(encoding="utf-8")))
    return found | {f"roadmap_{s}" for s in get_args(JobStage)}


def _keys(ts_file: Path, table: str) -> set[str]:
    text = ts_file.read_text(encoding="utf-8").replace("\r\n", "\n")
    body = text.split(f"const {table}", 1)[1].split("\n}\n", 1)[0]
    return set(re.findall(r"^\s+([a-z][a-z0-9_]*):", body, re.M))


def test_co_du_tool_trong_hop_dong():
    tools = contract_tools()
    assert {
        "get_roadmap",
        "optimize_allocation",
        "save_roadmap",
        "stress_test",
        "get_behavior_profile",
        "start_job",
    } <= tools
    assert len(tools) >= 28


#: tool đã có trên Gateway nhưng agent chưa gọi (#39, brief JJ: phần nối vào agent làm sau, cùng lúc thêm nhãn vào
#: `trace.TOOL_LABELS` và bỏ tên ở đây). Nhãn tiến độ của frontend đã có.
NOT_YET_CALLED_BY_AGENT = {"resolve_date"}


def test_moi_tool_co_nhan_nguon_du_lieu_cua_bang_vi_sao():
    missing = contract_tools() - set(trace.TOOL_LABELS)
    assert missing <= NOT_YET_CALLED_BY_AGENT, missing
    # miễn trừ chỉ đúng khi agent chưa gọi tool qua Gateway: nối tool vào agent thì phải thêm nhãn cùng lúc
    sources = "".join(f.read_text(encoding="utf-8") for f in AGENT_SRC.glob("*.py"))
    for name in missing:
        assert f"knowledge___{name}" not in sources and f'"{name}"' not in sources, name


def test_moi_tool_co_nhan_tien_do_o_the_yofina_da_lam():
    assert contract_tools() - _keys(FRONT_TOOLS, "TOOL_LABELS") == set()


def test_moi_buoc_cua_agent_co_nhan():
    steps = agent_steps()
    assert {"router", "analyst", "verifier", "roadmap_draft", "roadmap_save"} <= steps
    assert steps - _keys(FRONT_STEPS, "STEP_LABELS") == set()
