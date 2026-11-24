"""Lời nhắc của agent và ingest không chép câu của bộ eval (kiểm toán prompt, mục 4 và đợt 3).

Ví dụ trong lời nhắc mà trùng câu hỏi của bộ đo thì golden đo khả năng nhớ ví dụ, không đo khả năng hiểu câu mới. Test so mọi cụm
5 từ liên tiếp (chữ đã bỏ dấu, hạ thường) của câu hỏi trong `evals/golden`, `evals/adversarial` và `evals/paraphrase` với mọi chuỗi
gửi cho model của agent (router, writer, Orchestrator, Analyst, lộ trình, bộ nhớ) và của luồng nạp dữ liệu (ảnh, CSV).
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from yofina_agent import memory, roadmap_agent, router, whatif, writer
from yofina_agent.textutil import normalize

REPO = Path(__file__).resolve().parents[3]
EVAL_DIRS = ("golden", "adversarial", "paraphrase")
N = 5


def _strings(node: Any, key: str | None = None) -> Iterator[str]:
    """Câu người dùng trong một ca: `question`, `content` của lịch sử hay phiên trước, ở mọi độ sâu."""
    if isinstance(node, str):
        if key in ("question", "content"):
            yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, k)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v, key)


def eval_questions() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for sub in EVAL_DIRS:
        for path in sorted((REPO / "evals" / sub).glob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    case = json.loads(line)
                    out += [(f"{sub}/{case['id']}", q) for q in _strings(case)]
    return out


def _ingest_prompts() -> dict[str, str]:
    # nạp thẳng tệp (chỉ dùng thư viện chuẩn), không thêm gói nạp dữ liệu vào sys.path của cả phiên test
    spec = importlib.util.spec_from_file_location(
        "_ingest_prompts_for_overlap", REPO / "pipelines/ingest/yofina_ingest/prompts.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    jars = [{"code": "an_uong", "name": "Ăn uống"}]
    return {
        "ingest.image_system": mod.image_system(jars, {}, date(2026, 11, 25)),
        "ingest.image_user_text": mod.image_user_text(),
        "ingest.columns_system": mod.columns_system(),
        "ingest.labels_system": mod.labels_system(jars, {}),
    }


def agent_prompts() -> dict[str, str]:
    prompts = {
        "router": router.build_router_system(),
        "writer.WRITER_SYSTEM": writer.WRITER_SYSTEM,
        "writer.MEMORY_GUIDE": writer.MEMORY_GUIDE,
        "whatif.ORCHESTRATOR_SYSTEM": whatif.ORCHESTRATOR_SYSTEM,
        "whatif.ANALYST_SYSTEM": whatif.ANALYST_SYSTEM,
        "roadmap.ROADMAP_SYSTEM": roadmap_agent.ROADMAP_SYSTEM,
        "roadmap.ROADMAP_ADVICE_GUIDE": roadmap_agent.ROADMAP_ADVICE_GUIDE,
        "whatif.ANALYST_MEMORY_GUIDE": whatif.ANALYST_MEMORY_GUIDE,
        "memory.PROMPT_NOTICE": memory.PROMPT_NOTICE,
    }
    prompts |= {f"writer.TASKS[{k}]": v for k, v in writer.TASKS.items()}
    prompts |= {f"roadmap._REPAIR_HINTS[{k}]": v for k, v in roadmap_agent._REPAIR_HINTS.items()}
    return prompts | _ingest_prompts()


def ngrams(text: str, n: int = N) -> set[tuple[str, ...]]:
    words = normalize(text).split()
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def test_tim_duoc_cau_eval_va_loi_nhac():
    questions = eval_questions()
    assert len(questions) > 80 and any(q.startswith("paraphrase/") for q, _ in questions)
    assert len(agent_prompts()) > 15


def test_ngrams_bat_duoc_cum_trung_bat_ke_dau_va_hoa_thuong():
    assert ngrams("Mình có đang dùng Trả sau nhiều quá không?") & ngrams("ví dụ: MINH CO DANG DUNG tra sau")


@pytest.mark.parametrize("name", sorted(agent_prompts()))
def test_loi_nhac_khong_chep_cum_5_tu_cua_cau_eval(name):
    grams = ngrams(agent_prompts()[name])
    hits = sorted(
        {(case, " ".join(g)) for case, q in eval_questions() for g in ngrams(q) & grams}
    )
    assert not hits, f"{name} chép câu eval: {hits[:5]}"
