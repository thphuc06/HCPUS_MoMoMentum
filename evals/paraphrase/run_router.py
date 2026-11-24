"""Bộ câu diễn đạt lại cho ROUTER (kiểm toán prompt, mục 4): mỗi câu một ý định, cách nói khác hẳn câu golden và ví dụ trong lời nhắc.

Chỉ chấm router: mỗi câu gọi `yofina_agent.router.route` đúng MỘT lần (vai `small`, qua `yofina_core.llm` nên bị đếm vào trần ngày như mọi
lượt), không gọi Runtime, tool hay writer. Chấm bằng mã: ý định đúng, và mỗi tham số ghi trong `params` của ca có đúng giá trị (giá trị
`null` nghĩa là router phải để trống ô đó). Tham số không ghi trong ca thì không chấm.

    $env:AWS_REGION='ap-southeast-1'; $env:YOFINA_USAGE_TABLE='yofina-usage'
    uv run python evals/paraphrase/run_router.py                 # cả bộ, nghỉ 4 giây giữa hai câu
    uv run python evals/paraphrase/run_router.py --only pr-behavior-time pr-roadmap-edit-step

Kết quả ghi `evals/results/paraphrase-router.jsonl` (gitignored), tóm tắt in ra màn hình. Mã thoát 0 khi mọi ca đạt, 1 khi có ca trượt.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CASES = HERE / "router.jsonl"
RESULTS = HERE.parent / "results" / "paraphrase-router.jsonl"
DEFAULTS = HERE.parents[1] / "agent" / "src" / "yofina_agent" / "defaults.json"
#: khóa được phép trong một ca (test CI kiểm)
CASE_KEYS = frozenset({"id", "question", "intent", "params", "paraphrases", "note"})


def load(path: Path = CASES) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def score(case: Mapping[str, Any], result: Any | None, error: str | None = None) -> dict[str, Any]:
    """Chấm một câu. `result` là `IntentResult` của router (None khi router lỗi)."""
    out: dict[str, Any] = {"id": case["id"], "expect_intent": case["intent"]}
    if result is None:
        return out | {"ok": False, "intent_ok": False, "params_ok": False, "error": error or "no_result"}
    got = result.params.model_dump()
    wrong = {k: {"expect": v, "got": got.get(k)} for k, v in (case.get("params") or {}).items() if got.get(k) != v}
    intent_ok = result.intent == case["intent"]
    return out | {
        "ok": intent_ok and not wrong,
        "intent_ok": intent_ok,
        "params_ok": not wrong,
        "got_intent": result.intent,
        "wrong_params": wrong,
    }


def summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    n = len(rows)
    by_intent: dict[str, list[bool]] = {}
    for r in rows:
        by_intent.setdefault(r["expect_intent"], []).append(bool(r["intent_ok"]))
    return {
        "cases": n,
        "ok": sum(r["ok"] for r in rows),
        "intent_accuracy": round(sum(r["intent_ok"] for r in rows) / n, 3) if n else None,
        "params_accuracy": round(sum(r["params_ok"] for r in rows) / n, 3) if n else None,
        "intent_by_expected": {k: f"{sum(v)}/{len(v)}" for k, v in sorted(by_intent.items())},
        "failed": [r["id"] for r in rows if not r["ok"]],
    }


async def run_cases(
    cases: list[dict[str, Any]],
    route_one: Callable[[str], Awaitable[Any]],
    *,
    min_interval: float = 0.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> list[dict[str, Any]]:
    """Gọi router một lần mỗi câu (không lịch sử), tuần tự, nghỉ `min_interval` giây giữa hai câu."""
    rows = []
    for i, case in enumerate(cases):
        if i and min_interval > 0:
            await sleep(min_interval)
        try:
            result, error = await route_one(case["question"]), None
        except Exception as exc:  # lỗi model hay hết trần: ghi nhận, không chạy lại
            result, error = None, f"{type(exc).__name__}: {str(exc)[:200]}"
        rows.append(score(case, result, error))
    return rows


def _router(max_attempts: int, max_tokens: int) -> Callable[[str], Awaitable[Any]]:
    from yofina_agent.router import route

    from yofina_core.llm import LlmGateway

    gateway = LlmGateway()

    async def one(question: str) -> Any:
        res = await route(gateway, question, "", max_attempts=max_attempts, max_tokens=max_tokens)
        return res.value

    return one


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="*", help="chỉ chạy các id này")
    ap.add_argument("--min-interval", type=float, default=4.0, help="giây nghỉ giữa hai câu (quota của vai small)")
    args = ap.parse_args(argv)
    cases = load()
    if args.only:
        cases = [c for c in cases if c["id"] in set(args.only)]
    defaults = json.loads(DEFAULTS.read_text(encoding="utf-8"))
    route_one = _router(defaults["router_max_attempts"], defaults["router_max_tokens"])
    started = time.time()
    rows = asyncio.run(run_cases(cases, route_one, min_interval=args.min_interval))
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    report = summary(rows) | {"seconds": round(time.time() - started, 1), "results": str(RESULTS)}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not report["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
