"""Khai khoản một lần qua chat, từ router tới đề xuất chỉ đọc của ledger."""

from __future__ import annotations

import json

import pytest
from agent_helpers import (
    FakeTools,
    FakeWriter,
    blocks_of,
    check_agui_order,
    fixture,
    make_llm,
    mcp_ok,
    route_response,
    run_turn,
    tool_response,
)
from pydantic import ValidationError
from yofina_agent import notices
from yofina_agent.clarify import missing_slot
from yofina_agent.router import checked_route
from yofina_agent.schemas import IntentParams, IntentResult
from yofina_agent.tools import classify_result

from yofina_core.confirm import hash_normalized_params

NAME = "Phí dự thi"
AMOUNT = 5_000_000
DATE_SPEC = {"anchor": "date", "day": 5, "month": 2, "year": 2027}


def profile_route(**params):
    return IntentResult(
        intent="profile_update",
        params=IntentParams(**params),
        confidence=0.9,
        needs_clarification=False,
    )


def test_known_item_name_is_a_short_verbatim_text_field():
    assert IntentParams().model_dump()["known_item_name"] is None
    name = "Phí Dự Thi"
    assert IntentParams(known_item_name=name).known_item_name == name
    for value in ("a" * 81, 123, ["Phí"]):
        for field in ("known_item_name", "obligation_name", "label"):
            with pytest.raises(ValidationError):
                IntentParams.model_validate({field: value})


@pytest.mark.parametrize(
    ("params", "slot"),
    [
        ({"amount_vnd": AMOUNT, "date_spec": DATE_SPEC}, None),
        ({"date_spec": DATE_SPEC}, "amount"),
        ({"amount_vnd": AMOUNT, "date_text": "05/02/2027"}, "date"),
        ({}, "amount"),
        ({"salary_vnd": AMOUNT}, None),
        ({"payday_day": 8}, None),
        ({"obligation_name": "Tiền trọ"}, "amount"),
    ],
)
def test_known_item_required_slots_respect_existing_profile_fields(params, slot):
    assert missing_slot(profile_route(known_item_name=NAME, **params)) == slot


def test_known_item_amount_uses_router_grounding():
    routed = profile_route(known_item_name=NAME, amount_vnd=99_000_000, date_spec=DATE_SPEC)
    corrected = checked_route(routed, "Phí dự thi là 5 triệu.", "", None)
    assert corrected.params.amount_vnd == AMOUNT
    dropped = checked_route(routed, "Phí dự thi tầm 4 triệu hay 5 triệu?", "", None)
    assert dropped.params.amount_vnd is None
    assert missing_slot(dropped) == "amount"


ITEM = {"name": "Tết", "amount_vnd": AMOUNT, "needed_date": "2027-02-05"}
FULL = {"known_item_name": "Tết", "amount_vnd": AMOUNT, "date_spec": DATE_SPEC}
ASK = "Mình cần đóng khoản Tết 5 triệu vào 05/02/2027."
READS = ["get_jar_balances", "propose_jar_split"]


def model_route(*, intent="profile_update", **params):
    return tool_response(
        "route",
        {"intent": intent, "params": params, "confidence": 0.9, "needs_clarification": False},
    )


def tools_with_payload(payload):
    return FakeTools({"propose_jar_split": lambda _: classify_result("x", mcp_ok(payload))})


def proposal_fixture(status):
    return fixture(f"propose_jar_split.{status}.json")


def test_proposed_confirms_exact_tool_params_and_writes_with_two_model_calls(monkeypatch):
    from yofina_agent.metered_model import MeteredModel

    writer_calls = []

    class WriterBackend:
        async def stream(self, messages, *args, **kwargs):
            writer_calls.append(messages)
            yield {"messageStart": {"role": "assistant"}}
            yield {
                "contentBlockDelta": {
                    "delta": {"text": "Bạn xem đề xuất trước khi xác nhận."},
                    "contentBlockIndex": 0,
                }
            }
            yield {"contentBlockStop": {"contentBlockIndex": 0}}
            yield {"messageStop": {"stopReason": "end_turn"}}
            yield {
                "metadata": {
                    "usage": {"inputTokens": 50, "outputTokens": 10, "totalTokens": 60},
                    "metrics": {"latencyMs": 1},
                }
            }

    monkeypatch.setenv("YOFINA_REGION", "ap-southeast-1")
    monkeypatch.setattr(MeteredModel, "_bedrock", lambda *args: WriterBackend())
    payload = proposal_fixture("proposed")
    llm = make_llm([model_route(**FULL)])
    events, tools, _ = run_turn(ASK, llm=llm, tools=tools_with_payload(payload))
    check_agui_order(events)
    assert [b["type"] for b in blocks_of(events)] == ["confirm_action"]
    block = blocks_of(events)[0]
    assert block["source"]["tool"] == "ledger___propose_jar_split"
    preview = payload["data"]["confirm"]
    assert block["data"]["tool"] == "save_jars"
    assert block["data"]["params_hash"] == preview["params_hash"]
    assert (
        json.dumps(block["data"]["params"], ensure_ascii=False).encode()
        == json.dumps(preview["params"], ensure_ascii=False).encode()
    )
    assert tools.calls == [
        ("get_jar_balances", {}),
        ("propose_jar_split", {"sinking_items": [ITEM]}),
    ]
    assert len(llm[1].calls) == len(writer_calls) == 1
    assert events[-1].result["model_calls"] == 2
    prompt = writer_calls[0][0]["content"][0]["text"]
    facts = json.loads(prompt.split("<du_lieu>\n", 1)[1].split("\n</du_lieu>", 1)[0])
    assert facts["sinking_items"][0]["per_payday_text"] == "2.500.000 ₫"
    assert facts["reduced_jars"] == [
        {
            "name": "Chi hằng ngày",
            "split_before_text": "42%",
            "split_after_text": "14%",
            "amount_before_text": "3.780.000 ₫",
            "amount_after_text": "1.260.000 ₫",
            "delta_text": "2.520.000 ₫",
        }
    ]
    assert preview["params_hash"] not in prompt and '"params":' not in prompt


TUITION = {"name": "Học phí", "amount_vnd": 1_100_000, "needed_date": "2026-11-30"}
TUITION_PLAN = {**TUITION, "remaining_vnd": 700_000, "paydays": 0}
TUITION_FACTS = {
    "name": "Học phí",
    "needed_date_text": "30/11",
    "amount_text": "1.100.000 ₫",
    "remaining_text": "700.000 ₫",
    "status": "before_next_payday",
}
TUITION_REPLY = "Học phí còn thiếu 700.000 ₫ và đến hạn 30/11 trước kỳ lương kế tiếp."


@pytest.mark.parametrize(
    ("item", "plan", "saved_vnd", "facts", "reply"),
    [
        pytest.param(TUITION, [TUITION_PLAN], 400_000, [TUITION_FACTS], TUITION_REPLY, id="before-next-payday"),
        pytest.param(
            ITEM,
            [{**ITEM, "remaining_vnd": 0, "paydays": 2}],
            AMOUNT,
            [{
                "name": "Tết",
                "needed_date_text": "05/02",
                "amount_text": "5.000.000 ₫",
                "remaining_text": "0 ₫",
                "status": "funded",
            }],
            "Quỹ dồn đã đủ 5.000.000 ₫ cho khoản Tết.",
            id="funded",
        ),
        pytest.param(
            ITEM,
            [TUITION_PLAN, {**ITEM, "remaining_vnd": AMOUNT, "paydays": 2, "per_payday_vnd": 2_500_000}],
            400_000,
            [TUITION_FACTS, {
                "name": "Tết",
                "needed_date_text": "05/02",
                "amount_text": "5.000.000 ₫",
                "remaining_text": "5.000.000 ₫",
                "status": "per_payday",
                "per_payday_text": "2.500.000 ₫",
            }],
            f"{TUITION_REPLY} Khoản Tết cần dành 2.500.000 ₫ mỗi kỳ lương.",
            id="mixed",
        ),
    ],
)
def test_sinking_items_keep_confirmation_and_grounded_explanation(item, plan, saved_vnd, facts, reply, monkeypatch):
    payload = proposal_fixture("proposed")
    payload["data"]["sinking_items"] = plan
    preview = payload["data"]["confirm"]
    preview["params"]["jars"][-1]["sinking_items"] = [
        {key: row[key] for key in ("name", "amount_vnd", "needed_date")} for row in plan
    ]
    preview["params_hash"] = hash_normalized_params("save_jars", preview["params"])
    wallet = fixture("get_jar_balances.ok.json")
    wallet["data"]["jars"].append({
        **preview["params"]["jars"][-1],
        "balance_vnd": saved_vnd,
    })
    tools = tools_with_payload(payload)
    tools.results["get_jar_balances"] = lambda _: classify_result("x", mcp_ok(wallet))
    year, month, day = map(int, item["needed_date"].split("-"))
    events, tools, writer = run_turn(
        f"Mình cần đóng {item['name']} {item['amount_vnd']:,} đồng vào {day:02d}/{month:02d}/{year}.".replace(",", "."),
        llm=make_llm([model_route(
            known_item_name=item["name"],
            amount_vnd=item["amount_vnd"],
            date_spec={"anchor": "date", "day": day, "month": month, "year": year},
        )]),
        tools=tools,
        writer=FakeWriter(reply),
        monkeypatch=monkeypatch,
    )
    assert tools.calls[-1] == ("propose_jar_split", {"sinking_items": [item]})
    check_agui_order(events)
    (block,) = blocks_of(events)
    assert block["type"] == "confirm_action"
    assert block["data"]["tool"] == "save_jars"
    assert block["data"]["params"] == preview["params"]
    assert block["data"]["params_hash"] == preview["params_hash"]
    text = "".join(e.delta for e in events if e.type.value == "TEXT_MESSAGE_CONTENT")
    assert notices.GENERIC_ERROR_MESSAGE not in text
    assert text == reply
    (call,) = writer.calls
    assert call["task"] == "known_item_split"
    assert sorted(call["compact"]["sinking_items"], key=lambda row: row["name"]) == facts


@pytest.mark.parametrize(
    "status", ["aligned", "infeasible", "salary_mismatch", "no_salary", "no_obligation_jar"]
)
def test_non_proposed_status_uses_writer_without_a_confirmation(status, monkeypatch):
    payload = proposal_fixture("infeasible")
    data = payload["data"]
    data["status"] = status
    if status == "infeasible":
        data["priority_obligations"] = [
            {
                "name": "Phí nội trú",
                "id": "2fd10242-f3a8-4052-b6d9-569d89580690",
                "kind": "rent",
                "cycle": "monthly",
                "amount_vnd": 600_000,
                "monthly_vnd": 600_000,
                "is_essential": True,
            },
        ]
    if status == "salary_mismatch":
        data["salary_check"] = {
            "declared_vnd": 2_000_000,
            "received_vnd": 3_000_000,
            "deviation_percent": 50,
        }
    events, tools, writer = run_turn(
        ASK,
        llm=make_llm([model_route(**FULL)]),
        tools=tools_with_payload(payload),
        monkeypatch=monkeypatch,
    )
    assert blocks_of(events) == []
    assert [name for name, _ in tools.calls] == READS
    assert len(writer.calls) == 1 and writer.calls[0]["task"] == "known_item_split"
    facts = writer.calls[0]["compact"]
    assert facts["status"] == status
    if status == "infeasible":
        assert facts["priority_obligations"] == [
            {"name": "Phí nội trú", "monthly_text": "600.000 ₫"}
        ]


@pytest.mark.parametrize(
    ("spec", "call_expected"),
    [
        ({"anchor": "date", "day": 20, "month": 11, "year": 2026}, False),
        ({"anchor": "date", "day": 21, "month": 11, "year": 2026}, False),
        ({"anchor": "date", "day": 31, "month": 2, "year": 2027}, False),
        ({"anchor": "date", "day": 5, "month": 2, "year": 2028}, True),
    ],
)
def test_bad_deadline_asks_one_date_question(spec, call_expected, monkeypatch):
    payload = proposal_fixture("error_params")
    events, tools, writer = run_turn(
        "Khoản Tết là 5 triệu.",
        llm=make_llm([model_route(**(FULL | {"date_spec": spec}))]),
        tools=tools_with_payload(payload),
        monkeypatch=monkeypatch,
    )
    (block,) = blocks_of(events)
    assert block["type"] == "clarify" and block["data"]["slot"] == "date"
    assert block["data"]["question"].count("?") == 1
    assert [name for name, _ in tools.calls] == (READS if call_expected else READS[:1])
    assert not writer.calls


@pytest.mark.parametrize("code", ["FORBIDDEN", "PARAMS_INVALID", "PROFILE_INCOMPLETE"])
def test_proposal_tool_errors_use_standard_notice(code, monkeypatch):
    data = {"status": "ERROR", "code": code, "message": "Chưa thể lập đề xuất."}
    if code == "PARAMS_INVALID":
        data["field"] = "amount_vnd"
    events, _, writer = run_turn(
        ASK,
        llm=make_llm([model_route(**FULL)]),
        tools=tools_with_payload(data),
        monkeypatch=monkeypatch,
    )
    (block,) = blocks_of(events)
    assert block["type"] == "notice"
    assert block["data"]["code"] == code and block["data"]["message"] == data["message"]
    assert not writer.calls


@pytest.mark.parametrize(
    ("initial", "opening", "slot", "reply", "answer"),
    [
        (
            {"amount_vnd": AMOUNT, "date_spec": DATE_SPEC},
            "Mình phải đóng 5 triệu vào 05/02/2027.",
            "other",
            "Tết",
            {"known_item_name": "Tết"},
        ),
        (
            {"known_item_name": "Tết", "date_spec": DATE_SPEC},
            "Tết mình cần nộp tiền vào 05/02/2027.",
            "amount",
            "5 triệu",
            {"amount_vnd": AMOUNT},
        ),
        (
            {"known_item_name": "Tết", "amount_vnd": AMOUNT},
            "Khoản Tết mất 5 triệu.",
            "date",
            "05/02/2027",
            {"date_spec": DATE_SPEC},
        ),
    ],
)
def test_only_the_requested_slot_is_enough_to_resume(
    initial, opening, slot, reply, answer, monkeypatch
):
    first, initial_tools, writer = run_turn(
        opening, llm=make_llm([model_route(**initial)]), monkeypatch=monkeypatch
    )
    (clarify,) = blocks_of(first)
    assert clarify["type"] == "clarify" and clarify["data"]["slot"] == slot
    assert clarify["data"]["question"].count("?") == 1
    assert [name for name, _ in initial_tools.calls] == READS[:1] and not writer.calls
    messages = [
        {"id": "m1", "role": "user", "content": opening},
        {"id": "m2", "role": "assistant", "content": clarify["fallback_text"]},
        {"id": "m3", "role": "user", "content": reply},
    ]
    events, tools, _ = run_turn(
        None,
        llm=make_llm([model_route(**answer, answers_pending=True)]),
        tools=tools_with_payload(proposal_fixture("proposed")),
        messages=messages,
        monkeypatch=monkeypatch,
    )
    assert tools.calls[-1] == ("propose_jar_split", {"sinking_items": [ITEM]})
    assert [b["type"] for b in blocks_of(events)] == ["confirm_action"]


@pytest.mark.parametrize(
    ("reply", "date_text", "keeps_deadline"),
    [
        ("5 triệu", "trước Tết", True),
        ("5 triệu", "  TRƯỚC  TẾT  ", True),
        ("5 triệu, đổi sang sau Tết", "sau Tết", False),
    ],
    ids=["echo", "normalized-echo", "changed-date"],
)
def test_amount_reply_with_date_text_keeps_only_an_unchanged_lunar_deadline(
    reply, date_text, keeps_deadline, monkeypatch
):
    opening = "Khoản Tết mình cần đóng trước Tết."
    first, initial_tools, writer = run_turn(
        opening,
        llm=make_llm([model_route(
            known_item_name="Tết",
            date_text="trước Tết",
            date_spec={"anchor": "lunar_new_year", "before": True},
        )]),
        monkeypatch=monkeypatch,
    )
    (clarify,) = blocks_of(first)
    assert clarify["type"] == "clarify" and clarify["data"]["slot"] == "amount"
    assert "05/02/2027" in clarify["fallback_text"]
    assert [name for name, _ in initial_tools.calls] == READS[:1] and not writer.calls

    events, tools, _ = run_turn(
        None,
        llm=make_llm([model_route(amount_vnd=AMOUNT, date_text=date_text, answers_pending=True)]),
        tools=tools_with_payload(proposal_fixture("proposed")),
        messages=[
            {"id": "m1", "role": "user", "content": opening},
            {"id": "m2", "role": "assistant", "content": clarify["fallback_text"]},
            {"id": "m3", "role": "user", "content": reply},
        ],
        monkeypatch=monkeypatch,
    )
    (block,) = blocks_of(events)
    if keeps_deadline:
        assert tools.calls == [("get_jar_balances", {}), ("propose_jar_split", {"sinking_items": [ITEM]})]
        assert block["type"] == "confirm_action" and block["data"]["tool"] == "save_jars"
    else:
        assert tools.calls == [("get_jar_balances", {})]
        assert block["type"] == "clarify" and block["data"]["slot"] == "date"


def test_interruption_does_not_reuse_pending_known_item_slots(monkeypatch):
    events, _, _ = run_turn(
        "Tết mình phải nộp tiền vào 05/02/2027.",
        llm=make_llm([model_route(known_item_name="Tết", date_spec=DATE_SPEC)]),
        monkeypatch=monkeypatch,
    )
    (clarify,) = blocks_of(events)
    messages = [
        {"id": "m1", "role": "user", "content": "Tết mình phải nộp tiền vào 05/02/2027."},
        {"id": "m2", "role": "assistant", "content": clarify["fallback_text"]},
        {"id": "m3", "role": "user", "content": "Mình cần nộp lệ phí 5 triệu."},
    ]
    events, tools, _ = run_turn(
        None,
        llm=make_llm(
            [model_route(known_item_name="lệ phí", amount_vnd=AMOUNT, answers_pending=False)]
        ),
        messages=messages,
        monkeypatch=monkeypatch,
    )
    assert [name for name, _ in tools.calls] == READS[:1]
    (block,) = blocks_of(events)
    assert block["type"] == "clarify" and block["data"]["slot"] == "date"


@pytest.mark.parametrize(
    ("text", "profile", "expected_tools"),
    [
        (
            "Lương mình 9 triệu, nhận ngày 5.",
            {"salary_vnd": 9_000_000, "payday_day": 5},
            ["get_jar_balances", "update_profile"],
        ),
        (
            "Tiền trọ mỗi tháng 5 triệu, đóng ngày 1.",
            {
                "obligation_name": "Tiền trọ",
                "obligation_kind": "rent",
                "amount_vnd": AMOUNT,
                "due_day": 1,
            },
            ["get_jar_balances", "get_obligations", "update_profile"],
        ),
    ],
)
def test_existing_profile_preview_takes_priority_over_known_item(
    text, profile, expected_tools, monkeypatch
):
    def run(script):
        return run_turn(text, llm=make_llm([script]), monkeypatch=monkeypatch)[:2]

    baseline, baseline_tools = run(route_response(intent="profile_update", **profile))
    mixed, mixed_tools = run(model_route(known_item_name="Tết", **profile))
    assert [name for name, _ in mixed_tools.calls] == expected_tools
    assert mixed_tools.calls == baseline_tools.calls
    assert [b["data"] for b in blocks_of(mixed)] == [b["data"] for b in blocks_of(baseline)]
