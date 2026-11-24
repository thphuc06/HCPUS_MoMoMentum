"""Bộ câu diễn đạt lại cho router (`evals/paraphrase/`): định dạng ca, khác hẳn golden và đối kháng, phần chấm bằng mã. Không gọi model thật."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import get_args

import pytest
from agent_helpers import make_llm, route_response, run
from yofina_agent.router import route
from yofina_agent.schemas import Intent, IntentParams, IntentResult

REPO = Path(__file__).resolve().parents[3]


def _module():
    spec = importlib.util.spec_from_file_location("_paraphrase_run_router", REPO / "evals/paraphrase/run_router.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pr = _module()
CASES = pr.load()


def result(intent: str, **params) -> IntentResult:
    return IntentResult(intent=intent, params=IntentParams(**params), confidence=0.8, needs_clarification=False)  # type: ignore[arg-type]


def test_bo_cau_dung_dinh_dang_va_phu_nhieu_y_dinh():
    assert 12 <= len(CASES) <= 25
    ids = [c["id"] for c in CASES]
    assert len(set(ids)) == len(ids)
    for c in CASES:
        assert set(c) <= pr.CASE_KEYS and c["question"].strip(), c["id"]
        assert c["intent"] in get_args(Intent), c["id"]
        IntentParams(**(c.get("params") or {}))  # tên và giá trị tham số đúng schema router
    assert len({c["intent"] for c in CASES}) >= 12


def test_cau_dien_dat_lai_khong_trung_cum_5_tu_voi_golden_va_doi_khang():
    from test_prompt_eval_overlap import eval_questions, ngrams

    others = [(case, q) for case, q in eval_questions() if not case.startswith("paraphrase/")]
    golden_ids = {case.split("/", 1)[1] for case, _ in others}
    for c in CASES:
        hits = {g for _, q in others for g in ngrams(q) & ngrams(c["question"])}
        assert not hits, (c["id"], sorted(hits)[:3])
        assert c["paraphrases"] in golden_ids, c["id"]


def test_cham_y_dinh_va_tham_so_ghi_trong_ca():
    case = {"id": "x", "question": "q", "intent": "behavior", "params": {"insight_kind": "time_of_day"}}
    ok = pr.score(case, result("behavior", insight_kind="time_of_day", jar_text="lạ"))
    assert ok["ok"] and ok["intent_ok"] and ok["params_ok"]  # tham số không ghi trong ca thì không chấm
    wrong_param = pr.score(case, result("behavior"))
    assert not wrong_param["ok"] and wrong_param["intent_ok"] and wrong_param["wrong_params"] == {
        "insight_kind": {"expect": "time_of_day", "got": None}
    }
    wrong_intent = pr.score(case, result("lookup", lookup_kind="balance", insight_kind="time_of_day"))
    assert not wrong_intent["ok"] and not wrong_intent["intent_ok"] and wrong_intent["params_ok"]
    must_be_null = {"id": "y", "question": "q", "intent": "lookup", "params": {"lookup_kind": "forecast", "jar_text": None}}
    assert not pr.score(must_be_null, result("lookup", lookup_kind="forecast", jar_text="Ăn uống"))["ok"]
    failed = pr.score(case, None, "ModelBudgetExceeded: hết trần")
    assert not failed["ok"] and failed["error"].startswith("ModelBudgetExceeded")


def test_tom_tat():
    rows = [
        pr.score({"id": "a", "intent": "lookup", "params": {}}, result("lookup")),
        pr.score({"id": "b", "intent": "memory", "params": {}}, result("chitchat")),
    ]
    s = pr.summary(rows)
    assert (s["cases"], s["ok"], s["intent_accuracy"], s["failed"]) == (2, 1, 0.5, ["b"])
    assert s["intent_by_expected"] == {"lookup": "1/1", "memory": "0/1"}


def test_moi_cau_goi_router_dung_mot_lan_va_loi_thi_ghi_nhan():
    cases = CASES[:3]
    script = [route_response(intent=c["intent"], **(c.get("params") or {})) for c in cases[:2]]
    llm, client, _ = make_llm(script)  # câu thứ ba hết kịch bản: router lỗi, ghi nhận, không chạy lại

    async def one(question: str):
        return (await route(llm, question, "", max_attempts=1, max_tokens=400)).value

    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    rows = run(pr.run_cases(cases, one, min_interval=4.0, sleep=sleep))
    assert [r["ok"] for r in rows] == [True, True, False] and rows[2]["error"]
    assert len(client.calls) == 3 and slept == [4.0, 4.0]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_tham_so_ky_vong_la_y_dinh_phu_cua_dung_y_dinh(case):
    # insight_kind chỉ cho behavior, fee_topic cho knowledge, ingest_action cho ingest, roadmap_action cho roadmap
    owners = {"insight_kind": "behavior", "fee_topic": "knowledge", "ingest_action": "ingest", "roadmap_action": "roadmap"}
    for key in case.get("params") or {}:
        if key in owners:
            assert case["intent"] == owners[key]
