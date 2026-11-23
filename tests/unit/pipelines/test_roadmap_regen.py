"""Kiểm đường EventBridge/SQS → job → Roadmap agent với client AWS giả."""

from __future__ import annotations

import asyncio
import base64
import json
from contextlib import contextmanager
from importlib import import_module
from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import boto3
import pytest
from botocore.exceptions import ReadTimeoutError
from yofina_agent.settings import AgentSettings
from yofina_agent.tools import ToolKind

from yofina_core.config import Config
from yofina_core.errors import ErrorCode
from yofina_core.llm import LlmGateway, LlmSettings, ModelSpec

# handler.py của Lambda regen trùng tên với handler.py của ledger (cùng nằm trong pythonpath),
# nên nạp theo đường dẫn file với tên module riêng.
_HANDLER_PATH = Path(__file__).resolve().parents[3] / "pipelines" / "roadmap" / "handler.py"


def _load_handler():
    spec = spec_from_file_location("yofina_roadmap_handler", _HANDLER_PATH)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SETTINGS = {
    "YOFINA_ROADMAP_LEDGER_FUNCTION_NAME": "ledger-test",
    "YOFINA_ROADMAP_FORECAST_FUNCTION_NAME": "forecast-tool-test",
    "YOFINA_EVENT_BUS_NAME": "bus-test",
    "YOFINA_ROADMAP_INVOKE_CONNECT_TIMEOUT_SECONDS": "3",
    "YOFINA_ROADMAP_INVOKE_READ_TIMEOUT_SECONDS": "15",
    "YOFINA_ROADMAP_RUNNING_LEASE_SECONDS": "120",
    "YOFINA_ROADMAP_STAGE_PROGRESS": "5,25,45,65,85",
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class FakeDataApi:
    def __init__(self):
        self.jobs = {}
        self.calls = []
        self.expired = set()
        self.fail_claims = set()
        self.inserts = 0

    def seed(self, user_id, job_id=None, **changes):
        job_id = job_id or str(uuid4())
        self.jobs[user_id, job_id] = {
            "id": job_id,
            "status": "queued",
            "trigger": "user_request",
            "behavior_flag_id": None,
            "based_on_version": None,
            "alternative_id": None,
            "note": None,
            "dedupe_key": None,
            **changes,
        }
        return self.jobs[user_id, job_id]

    @contextmanager
    def transaction(self, user_id):
        class Tx:
            def execute(_, sql, params):
                return self.execute(user_id, " ".join(sql.split()), params)

        yield Tx()

    def execute(self, user_id, sql, p):
        assert p["uid"] == user_id
        self.calls.append((sql, p))
        if user_id in self.fail_claims:
            raise RuntimeError("Data API lỗi tạm thời")
        jobs = [job for (uid, _), job in self.jobs.items() if uid == user_id]
        if "make_interval" in sql:
            assert "AND status = 'running'" in sql
            for job in jobs:
                if job["status"] == "running" and job["id"] in self.expired:
                    job.update(status="failed", error_code=p["code"], finished_at=True)
            return []
        if sql.startswith("INSERT"):
            assert "ON CONFLICT DO NOTHING" in sql
            if any(
                job["dedupe_key"] == p["event_id"] or job["status"] in ("queued", "running")
                for job in jobs
            ):
                return []
            self.inserts += 1
            return [
                self.seed(
                    user_id,
                    trigger=p["trigger"],
                    behavior_flag_id=p["flag_id"],
                    dedupe_key=p["event_id"],
                )
            ]
        if "dedupe_key = :event_id" in sql:
            return [job for job in jobs if job["dedupe_key"] == p["event_id"]]
        job = self.jobs.get((user_id, p["job_id"]))
        if sql.startswith("SELECT"):
            return [job] if job else []
        if "SET status = 'running'" in sql:
            assert "started_at = now()" in sql and "AND status = 'queued'" in sql
            if job and job["status"] == "queued":
                job["status"] = "running"
                return [job]
            return []
        assert "AND status = 'running'" in sql and job["status"] == "running"
        if "SET stage" in sql:
            job["stage"], job["progress"] = p["stage"], p["progress"]
        else:
            assert "finished_at = now()" in sql
            job["finished_at"] = True
            if "SET status = 'done'" in sql:
                assert "progress = 100" in sql
                job.update(
                    status="done",
                    progress=100,
                    version=p["version"],
                    roadmap_id=p["roadmap_id"],
                    based_on_version=p["based_on_version"],
                )
            else:
                assert "SET status = 'failed'" in sql
                job.update(status="failed", error_code=p["code"], error_message=p["message"])
        return []


class FakeLambda:
    def __init__(self, folder):
        self.folder = folder
        self.overrides = {}
        self.calls = []

    def invoke(self, **kwargs):
        assert kwargs["InvocationType"] == "RequestResponse"
        context = json.loads(base64.b64decode(kwargs["ClientContext"], validate=True))
        name = context["custom"]["bedrockAgentCoreToolName"]
        assert context == {"custom": {"bedrockAgentCoreToolName": name}}
        target, tool = name.split("___")
        function = "forecast-tool-test" if target == "forecast" else "ledger-test"
        assert kwargs["FunctionName"] == function
        self.calls.append((name, json.loads(kwargs["Payload"])))
        result = self.overrides.get(tool, "ok")
        if isinstance(result, Exception):
            raise result
        if result == "FunctionError":
            return {"StatusCode": 200, "FunctionError": "Unhandled", "Payload": BytesIO(b"{}")}
        payload = load(self.folder / f"{tool}.{result}.json") if isinstance(result, str) else result
        return {"StatusCode": 200, "Payload": BytesIO(json.dumps(payload).encode())}

    def arguments(self, target, name):
        return [payload for tool, payload in self.calls if tool == f"{target}___{name}"]


class FakeBedrock:
    def __init__(self):
        self.prompts = []
        self.fail_on_call = None
        self.repair_needed = False

    def converse(self, **kwargs):
        self.prompts.append(json.loads(kwargs["messages"][0]["content"][0]["text"]))
        if len(self.prompts) == self.fail_on_call:
            raise RuntimeError("Model hỏng")
        step = {
            "step_id": "bu_du_phong",
            "kind": "set_aside",
            "title": "Bù hũ dự phòng",
            "reason": "Tăng khoản dự phòng từ phần có thể chuyển",
            "jar_code": "giai_tri",
            "to_jar_code": "du_phong",
            "amount_ref": {"jar_code": "du_phong", "field": "proposed_increase"},
            "action": "move_between_jars",
        }
        steps = [step]
        if self.repair_needed:
            steps.append({**step, "step_id": "loi_so", "title": "Số 9912345678"})
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "toolUse": {
                                "toolUseId": "t-draft",
                                "name": "draft_roadmap",
                                "input": {
                                    "phases": [
                                        {"phase_id": "on_dinh", "title": "Ổn định", "steps": steps}
                                    ],
                                },
                            },
                        }
                    ],
                },
            },
            "stopReason": "tool_use",
            "usage": {"inputTokens": 30, "outputTokens": 20},
        }


class FakeUsage:
    def consume(self, **kwargs):
        return 1


@pytest.fixture
def pipeline(monkeypatch, contracts_dir):
    def forbid_aws(*args, **kwargs):
        pytest.fail("Unit test vừa thử tạo AWS client thật")

    monkeypatch.setattr(boto3, "client", forbid_aws)
    handler = _load_handler()
    settings_type = import_module("yofina_roadmap.settings").RoadmapSettings
    repo_type = import_module("yofina_roadmap.repo").RoadmapRepo
    runner_type = import_module("yofina_roadmap.runner").RoadmapRunner
    settings = settings_type.from_config(Config(SETTINGS))
    db = FakeDataApi()
    tools = FakeLambda(contracts_dir / "fixtures" / "tools")
    model = FakeBedrock()
    llm = LlmGateway(
        LlmSettings(roles={"planner": (ModelSpec("planner-test", 0, 100),)}),
        config=Config({}),
        client=model,
        usage=FakeUsage(),
    )
    runner = runner_type(
        repo_type(db, settings.running_lease_seconds),
        settings,
        AgentSettings.load({}),
        tools,
        lambda: llm,
    )
    monkeypatch.setattr(handler.bootstrap, "runner", lambda: runner)

    def event(kind, name, **changes):
        detail = load(contracts_dir / "fixtures" / "events" / f"{kind}.{name}.json")
        detail.update(changes)
        source = "yofina.forecast" if kind == "behavior.changed" else "yofina.ledger"
        return {"source": source, "detail-type": kind, "detail": detail}

    return handler.lambda_handler, db, tools, model, event


def sqs_record(message_id, envelope):
    return {"messageId": message_id, "body": json.dumps(envelope)}


def test_requested_job_runs_and_finishes_with_saved_version(pipeline):
    handle, db, tools, model, event = pipeline
    envelope = event("roadmap.regeneration_requested", "user_request", trigger="income_changed")
    uid, job_id = envelope["detail"]["user_id"], envelope["detail"]["job_id"]
    job = db.seed(uid, job_id, alternative_id="lui_han", note="Ưu tiên quỹ dự phòng")
    db.seed("another-user", job_id)

    assert handle(envelope, None) == {"status": "done"}
    assert handle(envelope, None) == {"status": "skipped"}
    saved = load(tools.folder / "save_roadmap.ok.json")["data"]
    assert job["status"] == "done" and job["finished_at"]
    assert (job["roadmap_id"], job["version"], job["progress"]) == (
        saved["roadmap_id"],
        saved["version"],
        100,
    )
    assert db.jobs["another-user", job_id]["status"] == "queued"
    assert db.inserts == 0
    assert [(p["stage"], p["progress"]) for _, p in db.calls if "stage" in p] == [
        ("context", 5),
        ("draft", 25),
        ("allocate", 45),
        ("suitability", 65),
        ("save", 85),
    ]
    assert tools.arguments("planner", "get_roadmap") == [{"which": "active", "user_id": uid}]
    (draft,) = tools.arguments("planner", "save_roadmap")
    assert draft["reason_code"] == "user_request"
    assert draft["based_on_version"] == 2
    assert "move_between_jars" not in [name.split("___")[1] for name, _ in tools.calls]
    assert all(args["user_id"] == uid for _, args in tools.calls)
    assert model.prompts[0]["regeneration_preferences"] == {
        "alternative_id": "lui_han",
        "note": "Ưu tiên quỹ dự phòng",
    }


def test_explicit_base_version_reads_exact_version(pipeline):
    handle, db, tools, _, event = pipeline
    envelope = event("roadmap.regeneration_requested", "user_request")
    uid, job_id = envelope["detail"]["user_id"], envelope["detail"]["job_id"]
    db.seed(uid, job_id, based_on_version=2)
    assert handle(envelope, None) == {"status": "done"}
    assert tools.arguments("planner", "get_roadmap") == [{"user_id": uid, "version": 2}]


def test_missing_active_roadmap_can_generate_first_version(pipeline):
    handle, _, tools, _, event = pipeline
    tools.overrides["get_roadmap"] = "error_not_found"
    assert handle(event("profile.updated", "onboarding", fields=["jars"]), None) == {
        "status": "done"
    }
    assert "based_on_version" not in tools.arguments("planner", "save_roadmap")[0]


def test_behavior_change_dedupes_after_redelivery(pipeline):
    handle, db, tools, _, event = pipeline
    envelope = event("behavior.changed", "confirmed")
    batch = {"Records": [sqs_record("a", envelope), sqs_record("b", envelope)]}
    assert handle(batch, None) == {"batchItemFailures": []}
    assert handle(batch, None) == {"batchItemFailures": []}
    assert db.inserts == 1
    (job,) = db.jobs.values()
    assert job["trigger"] == "behavior_changed" and job["status"] == "done"
    assert job["dedupe_key"] == envelope["detail"]["event_id"]
    (draft,) = tools.arguments("planner", "save_roadmap")
    assert draft["behavior_flag_id"] == envelope["detail"]["flag_id"]


@pytest.mark.parametrize(
    ("fields", "trigger"),
    [
        (["salary"], "income_changed"),
        (["jars"], "goal_changed"),
        (["jars", "salary"], "income_changed"),
        (["risk"], None),
        # đặt lại demo và onboarding: không sinh lại (giữ lộ trình seed)
        (["onboarding", "salary", "payday", "jars"], None),
    ],
)
def test_profile_updated_fields(pipeline, fields, trigger):
    handle, db, tools, _, event = pipeline
    output = handle(event("profile.updated", "onboarding", fields=fields), None)
    if trigger is None:
        assert output == {"status": "skipped"} and not db.calls and not tools.calls
    else:
        assert output == {"status": "done"}
        assert next(iter(db.jobs.values()))["trigger"] == trigger
        assert tools.arguments("planner", "save_roadmap")[0]["reason_code"] == trigger


def test_sqs_reports_busy_and_transient_records_only(pipeline):
    handle, db, tools, _, event = pipeline
    busy = event("profile.updated", "onboarding", user_id="busy", fields=["salary"])
    db.seed("busy", status="running")
    unavailable = event("profile.updated", "onboarding", user_id="unavailable", fields=["salary"])
    db.fail_claims.add("unavailable")
    eligible = event("behavior.changed", "confirmed", user_id="eligible")
    assert handle(
        {
            "Records": [
                sqs_record("busy", busy),
                sqs_record("unavailable", unavailable),
                sqs_record("eligible", eligible),
            ]
        },
        None,
    ) == {"batchItemFailures": [{"itemIdentifier": "busy"}, {"itemIdentifier": "unavailable"}]}
    assert all(args["user_id"] == "eligible" for _, args in tools.calls)


def test_stale_running_job_is_finished_without_a_second_save(pipeline):
    handle, db, tools, _, event = pipeline
    envelope = event("roadmap.regeneration_requested", "user_request")
    uid, job_id = envelope["detail"]["user_id"], envelope["detail"]["job_id"]
    job = db.seed(uid, job_id, status="running")
    db.expired.add(job_id)
    assert handle(envelope, None) == {"status": "skipped"}
    assert not tools.calls
    assert job["status"] == "failed" and job["finished_at"]


def test_tool_error_fails_job_and_sets_finished_at(pipeline):
    handle, db, tools, _, event = pipeline
    tools.overrides["optimize_allocation"] = "error_profile_incomplete"
    assert handle(event("behavior.changed", "confirmed"), None) == {"status": "failed"}
    (job,) = db.jobs.values()
    assert job["status"] == "failed" and job["finished_at"]
    assert job["error_code"] == ErrorCode.PROFILE_INCOMPLETE
    assert 0 < len(job["error_message"]) <= 280
    assert not tools.arguments("planner", "save_roadmap")


@pytest.mark.parametrize("fail_on_call", [1, 2])
def test_model_failure_never_saves(pipeline, fail_on_call):
    handle, db, tools, model, event = pipeline
    model.fail_on_call = fail_on_call
    model.repair_needed = fail_on_call == 2
    assert handle(event("behavior.changed", "confirmed"), None) == {"status": "failed"}
    assert len(model.prompts) == fail_on_call
    (job,) = db.jobs.values()
    assert job["status"] == "failed" and job["finished_at"]
    assert job["error_code"] == ErrorCode.INTERNAL_ERROR
    assert not tools.arguments("planner", "save_roadmap")


def test_unconfirmed_behavior_cannot_run(pipeline):
    handle, db, tools, _, event = pipeline
    envelope = event("behavior.changed", "confirmed", method="cusum")
    assert handle({"Records": [sqs_record("bad", envelope)]}, None) == {
        "batchItemFailures": [{"itemIdentifier": "bad"}]
    }
    assert not db.calls and not tools.calls


def test_tool_caller_denies_writes_and_uses_event_user(pipeline):
    _, _, client, _, _ = pipeline
    lambda_tools = import_module("yofina_roadmap.tool_caller").LambdaTools
    tools = lambda_tools(client, {"ledger": "ledger-test", "planner": "ledger-test"}, "event-user")
    moved = asyncio.run(tools("move_between_jars", {"confirm_token": "unused"}, "ledger"))
    nudged = asyncio.run(tools("schedule_nudge", {}, "planner"))
    token = asyncio.run(tools("save_roadmap", {"confirm_token": "unused"}, "planner"))
    assert all(outcome.kind is ToolKind.DENIED for outcome in (moved, nudged, token))
    assert not client.calls
    read = asyncio.run(tools("get_jar_balances", {"user_id": "other-user"}, "ledger"))
    assert read.kind is ToolKind.OK
    assert client.arguments("ledger", "get_jar_balances") == [{"user_id": "event-user"}]


@pytest.mark.parametrize(
    "failure",
    [
        "FunctionError",
        ReadTimeoutError(endpoint_url="lambda-test"),
    ],
)
def test_transport_failures_are_unavailable(pipeline, failure):
    _, _, client, _, _ = pipeline
    client.overrides["get_jar_balances"] = failure
    lambda_tools = import_module("yofina_roadmap.tool_caller").LambdaTools
    tools = lambda_tools(client, {"ledger": "ledger-test"}, "event-user")
    outcome = asyncio.run(tools("get_jar_balances", {}, "ledger"))
    assert outcome.kind is ToolKind.UNAVAILABLE


@pytest.mark.parametrize(
    ("payload", "kind"),
    [
        ({"status": "NEEDS_CONFIRMATION"}, ToolKind.NEEDS_CONFIRMATION),
        ({"status": "UNKNOWN"}, ToolKind.BAD_RESULT),
    ],
)
def test_tool_caller_classifies_result_envelopes(pipeline, payload, kind):
    _, _, client, _, _ = pipeline
    client.overrides["get_jar_balances"] = payload
    lambda_tools = import_module("yofina_roadmap.tool_caller").LambdaTools
    tools = lambda_tools(client, {"ledger": "ledger-test"}, "event-user")
    assert asyncio.run(tools("get_jar_balances", {}, "ledger")).kind is kind
