"""Cảnh 4 đầu cuối không cần model thật (issue #19): đặt lại ví demo của `minh` (`POST /demo/reset`), nạp tệp sao kê hai tuần qua đúng
đường nạp, PELT xác nhận đổi hành vi hũ Ăn uống, rồi Lambda sinh lại lộ trình (`RoadmapRunner` thật, Roadmap agent thật) chạy với hai
Lambda tool thật trên PostgreSQL cục bộ (ledger `handle_gateway`, forecast `handle_gateway`, LP `optimize_allocation` của Lambda forecast)
và một model planner giả TẤT ĐỊNH. Model giả chọn từ đúng dữ liệu model thật nhận (bảng tham chiếu tiền, hũ nguồn của giai đoạn đầu,
nghĩa vụ trong ngữ cảnh) như bản lộ trình thấy trên app tối 25/11: một bước chuyển tiền làm ngay có lý do nêu nghĩa vụ sớm nhất bằng
chữ của ngữ cảnh, một bước "Đổi tỷ lệ chia lương" cho hũ Ăn uống lấy MỨC chia mới làm số tiền, một bước giảm chi, một lời nhắc. Ở vòng
sửa nó làm theo phản hồi của chương trình.

Khẳng định trên CẤU TRÚC bản lộ trình đã lưu:
- nghĩa vụ model thấy mang nhãn tiếng Việt của bảng chung, không mang mã loại; chữ do mã dựng không có mã loại thô;
- giai đoạn đầu là từ hôm nay tới ngày lương kế (khoản đến hạn 23/11 nằm trong đó); mọi bước có hạn nằm trong khoảng ngày của giai đoạn;
- số tiền mỗi bước không vượt tiền có thể chuyển (số dư hũ nguồn với bước làm ngay, khoản hũ nguồn nhận mỗi tháng với bước sau kỳ lương)
  và không vượt phần hũ nhận cần thêm trong kỳ theo phương án tối ưu.

Chạy riêng (in bản lộ trình với `-s`):

    uv run --python 3.12 --no-project --with pgserver --with "psycopg[binary]" --with pydantic --with pytest --with jsonschema \
        --with pyyaml --with referencing --with numpy --with boto3 --with scipy --with ruptures \
        pytest tests/local_pg/test_roadmap_regen_scene4.py -p no:cacheprovider -s
"""

from __future__ import annotations

import base64
import io
import json
import re
import sys
from datetime import date
from typing import Any

from conftest import ANCHOR, REPO
from ledger_fakes import gateway_context, http_event
from pipeline_helpers import make_settings

for _extra in ("agent/src", "pipelines/roadmap"):
    if str(REPO / _extra) not in sys.path:
        sys.path.insert(0, str(REPO / _extra))

from test_change_flow import FakeEvents, upload_scene4  # noqa: E402
from yofina_agent.settings import AgentSettings  # noqa: E402
from yofina_roadmap.events import parse_event  # noqa: E402
from yofina_roadmap.repo import RoadmapRepo  # noqa: E402
from yofina_roadmap.runner import RoadmapRunner  # noqa: E402
from yofina_roadmap.settings import STAGES, RoadmapSettings  # noqa: E402

from yofina_core.clock import next_payday  # noqa: E402
from yofina_core.config import Config  # noqa: E402
from yofina_core.llm import LlmGateway, LlmSettings, ModelSpec  # noqa: E402
from yofina_core.wallet import OBLIGATION_KIND_LABELS, OBLIGATION_KINDS  # noqa: E402
from yofina_forecast import change  # noqa: E402
from yofina_forecast.allocation import AllocationEngine  # noqa: E402
from yofina_forecast.events import ForecastEventPublisher  # noqa: E402
from yofina_forecast.repo import ForecastRepo  # noqa: E402
from yofina_forecast.resilience import ResilienceEngine  # noqa: E402
from yofina_forecast.runner import Pipeline  # noqa: E402
from yofina_forecast.tool import ForecastReader, ReadSettings  # noqa: E402
from yofina_forecast.tool import handle_gateway as forecast_gateway  # noqa: E402
from yofina_ledger.gateway_api import handle_gateway as ledger_gateway  # noqa: E402
from yofina_ledger.rest_api import handle_http  # noqa: E402

USER = "sub-canh4-lotrinh"  # người dùng riêng mang persona minh (lần nạp ghi audit không xóa khi đặt lại)
LEDGER, FORECAST = "ledger-local", "forecast-local"
STEP_KINDS = ("set_aside", "adjust_split", "pay_obligation", "cut_spending", "review_goal", "remind")
RAW_CODE = re.compile(r"\b(" + "|".join((*OBLIGATION_KINDS, *STEP_KINDS)) + r")\b", re.IGNORECASE)


class LocalLambda:
    """Client Lambda chạy hai handler tool THẬT trong tiến trình (ledger, forecast) trên Postgres cục bộ, cùng phong bì `Invoke` mà
    `LambdaTools` đọc. Không giả kết quả tool."""

    def __init__(self, env, pipeline: Pipeline) -> None:
        self.env, self.pipeline = env, pipeline
        self.reader = ForecastReader(env.repo, ReadSettings(900, "Asia/Ho_Chi_Minh"), env.clock)

    def invoke(self, FunctionName, InvocationType, ClientContext, Payload):
        name = json.loads(base64.b64decode(ClientContext))["custom"]["bedrockAgentCoreToolName"]
        event, context = json.loads(Payload), gateway_context(name)
        if FunctionName == LEDGER:
            out = ledger_gateway(event, context, self.env.svc)
        else:
            out = forecast_gateway(
                event, context, self.reader, self.pipeline, resilience=ResilienceEngine(self.pipeline)
            )
        return {"StatusCode": 200, "Payload": io.BytesIO(json.dumps(out, ensure_ascii=False).encode())}


class LocalAllocation:
    """`ForecastClient` của ledger: op `optimize_allocation` của Lambda forecast chạy trong tiến trình (LP thật). Giữ kết quả cuối."""

    def __init__(self, pipeline: Pipeline) -> None:
        self.pipeline = pipeline
        self.last: dict[str, Any] | None = None

    def optimize_allocation(self, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
        self.last = AllocationEngine(self.pipeline).optimize(user_id, dict(args))
        return self.last


class Planner:
    """Model planner giả, tất định (xem docstring của module). Ghi lại mọi ngữ cảnh nhận được."""

    def __init__(self) -> None:
        self.contexts: list[dict[str, Any]] = []

    def converse(self, **kw: Any) -> dict[str, Any]:
        ctx = json.loads(kw["messages"][0]["content"][0]["text"])
        self.contexts.append(ctx)
        content = [{"toolUse": {"toolUseId": "t", "name": "draft_roadmap", "input": self.outline(ctx)}}]
        return {
            "output": {"message": {"role": "assistant", "content": content}},
            "usage": {"inputTokens": 300, "outputTokens": 80},
            "stopReason": "tool_use",
        }

    @staticmethod
    def outline(model_context: dict[str, Any]) -> dict[str, Any]:
        ctx = model_context["context"]
        refs: dict[str, dict[str, str]] = ctx["amount_refs"]
        flagged = {item["step_id"] for item in model_context.get("feedback", []) if item.get("step_id")}
        first = min(ctx["obligations"], key=lambda o: o["due_date_text"].split("/")[::-1])
        # model chép chữ có trong ngữ cảnh để gọi tên khoản (tên khoản không có trong ngữ cảnh)
        what = first.get("kind_label") or first.get("kind")
        steps_now: list[dict[str, Any]] = []
        for source, entry in ctx["first_phase_sources"].items():
            ref = next((r for r in entry["refs"] if not r.startswith(f"{source}.")), None)
            if ref is not None:
                jar, field = ref.split(".")
                steps_now.append(
                    {
                        "step_id": "chuyen_truoc_luong",
                        "kind": "set_aside",
                        "title": "Chuyển tiền sang hũ cần thêm trước kỳ lương",
                        "reason": f"{what} {first['amount_text']} đến hạn {first['due_date_text']}.",
                        "jar_code": source,
                        "to_jar_code": jar,
                        "amount_ref": {"jar_code": jar, "field": field},
                        "action": "move_between_jars",
                    }
                )
                break
        if "an_uong" in refs:
            # như bản trên app: mức chia mới làm số tiền; sau phản hồi của vòng sửa thì dùng phần tăng
            field = "proposed_increase" if "doi_ty_le_an_uong" in flagged else "proposed_monthly_vnd"
            steps_now.append(
                {
                    "step_id": "doi_ty_le_an_uong",
                    "kind": "adjust_split",
                    "title": "Đổi tỷ lệ chia lương cho hũ Ăn uống",
                    "reason": "Chi Ăn uống đã tăng so với trước.",
                    "jar_code": "an_uong",
                    "amount_ref": {"jar_code": "an_uong", "field": field},
                }
            )
        later = [
            {
                "step_id": f"giam_{jar}",
                "kind": "cut_spending",
                "title": "Giảm chi hũ không thiết yếu",
                "reason": "Giữ tiền cho khoản thiết yếu.",
                "jar_code": jar,
                "amount_ref": {"jar_code": jar, "field": "proposed_decrease"},
            }
            for jar, fields in refs.items()
            if "proposed_decrease" in fields and not ctx["allocation"]["lines"][jar]["is_essential"]
        ][:1]
        remind = {
            "step_id": "nhac_xem_lai",
            "kind": "remind",
            "title": "Đặt nhắc xem lại các hũ",
            "reason": "Xem lại sau khi chạy lộ trình.",
            "action": "schedule_nudge",
        }
        return {
            "phases": [
                {"phase_id": "truoc_ky_luong", "title": "Tuần này, trước kỳ lương kế", "steps": steps_now},
                {"phase_id": "sau_ky_luong", "title": "Sau kỳ lương", "steps": later},
                {"phase_id": "ve_dich", "title": "Về đích", "steps": [remind]},
            ]
        }


def _llm(planner: Planner) -> LlmGateway:
    class Usage:
        def consume(self, **_: Any) -> int:
            return 1

    settings = LlmSettings(roles={"planner": (ModelSpec("m-plan", rpm=0, daily_cap=100),)})
    return LlmGateway(settings, config=Config({"YOFINA_REGION": "ap-southeast-1"}), client=planner, usage=Usage())


def _tool(env, name: str, **args: Any) -> dict[str, Any]:
    out = ledger_gateway({"user_id": USER, **args}, gateway_context(name), env.svc)
    assert out["status"] == "OK", out
    return out


def _run_scene4(env) -> dict[str, Any]:
    """Đặt lại ví demo, dự báo, nạp tệp cảnh 4, PELT xác nhận, rồi chạy job sinh lại từ sự kiện `behavior.changed`."""
    pipeline = Pipeline(ForecastRepo(env.db), make_settings(n_paths_full=600, n_paths_fast=400), None, clock=env.clock)
    r = handle_http(http_event("POST", "/demo/reset", sub=USER, groups="persona-minh"), env.svc)
    assert r["statusCode"] == 200, r
    assert pipeline.run_user(USER, trigger="reset").status == "ok"
    upload_scene4(env, USER)
    events = FakeEvents()
    detector = Pipeline(
        ForecastRepo(env.db), make_settings(n_paths_full=600, n_paths_fast=400),
        ForecastEventPublisher("bus", events), clock=env.clock,
    )  # fmt: skip
    assert change.detect_and_store(detector, USER, env.clock.now).confirmed == ["an_uong"]
    assert pipeline.run_user(USER, trigger="event").status == "ok"
    (entry,) = events.entries
    event = parse_event(
        {"detail-type": entry["DetailType"], "source": entry["Source"], "detail": json.loads(entry["Detail"])}
    )
    balances = _tool(env, "ledger___get_jar_balances")["data"]["jars"]
    obligations = _tool(env, "ledger___get_obligations")["data"]["obligations"]
    allocation, planner = LocalAllocation(pipeline), Planner()
    env.svc.forecast = allocation
    runner = RoadmapRunner(
        RoadmapRepo(env.db, 360),
        RoadmapSettings(LEDGER, FORECAST, "bus", 5, 65, 360, dict(zip(STAGES, (5, 25, 45, 65, 85), strict=True))),
        AgentSettings.load({"YOFINA_GATEWAY_URL": "http://gateway.invalid/mcp"}),
        LocalLambda(env, pipeline),
        llm_factory=lambda: _llm(planner),
    )
    try:
        assert runner.process(event) == "done"
    finally:
        env.svc.forecast = None
    roadmap = _tool(env, "planner___get_roadmap", which="latest")["data"]
    assert allocation.last is not None
    return {
        "roadmap": roadmap,
        "planner": planner,
        "balances": {j["code"]: j for j in balances},
        "obligations": obligations,
        "lines": {line["jar"]["code"]: line for line in allocation.last["data"]["lines"]},
    }


def _code_built_texts(rm: dict[str, Any]) -> list[str]:
    """Chữ hiển thị do mã dựng (không phải title/reason model viết): lý do bản mới, tiêu đề bản, mục tiêu, lựa chọn, số trước/sau."""
    texts = [rm["headline"], rm["reason"]["text"]]
    texts += [v for d in rm["reason"].get("detail", []) for v in d.values()]
    texts += [g["jar"]["name"] for g in rm["goals"]]
    for alt in rm["alternatives"]:
        texts += [alt["label"], alt["summary"], *(v for m in alt.get("metrics", []) for v in m.values())]
    for phase in rm["phases"]:
        for step in phase["steps"]:
            texts += [v for m in step.get("metrics", []) for v in m.values()]
    return [t for t in texts if isinstance(t, str)]


def test_canh_4_lo_trinh_sinh_lai_dung_nhan_ngay_va_so_tien(env):
    got = _run_scene4(env)
    rm, lines, balances = got["roadmap"], got["lines"], got["balances"]
    print("\n[cảnh 4] bản sinh lại:", json.dumps(rm["phases"], ensure_ascii=False, indent=1))
    assert (rm["version"], rm["status"], rm["reason"]["code"]) == (3, "proposed", "behavior_changed")
    today = date.fromisoformat(rm["app_date"])
    assert today == ANCHOR

    # (a) nhãn loại nghĩa vụ: model thấy nhãn của bảng chung, không thấy mã; chữ do mã dựng không có mã thô
    for ctx in got["planner"].contexts:
        seen = ctx["context"]["obligations"]
        assert [o["kind_label"] for o in seen] == [OBLIGATION_KIND_LABELS[o["kind"]] for o in got["obligations"]][: len(seen)]
        assert all("kind" not in o for o in seen)
    leaked = [t for t in _code_built_texts(rm) if RAW_CODE.search(t)]
    assert leaked == []
    steps = {s["step_id"]: (phase, s) for phase in rm["phases"] for s in phase["steps"]}
    assert not RAW_CODE.search(steps["chuyen_truoc_luong"][1]["reason"])  # model chép nhãn có trong ngữ cảnh

    # (b) ngày: giai đoạn đầu là từ hôm nay tới ngày lương kế; giai đoạn nối liền; bước có hạn nằm trong giai đoạn của nó
    spec = json.loads((REPO / "data/personas/specs/minh.json").read_text(encoding="utf-8"))
    payday = next_payday(int(spec["payday_day"]), today)
    first = rm["phases"][0]
    assert (first["start_date"], first["end_date"]) == (today.isoformat(), payday.isoformat())
    earliest = min(date.fromisoformat(o["due_date"]) for o in got["obligations"])
    assert today <= earliest <= payday  # khoản đến hạn 23/11 mà lý do bước đầu nhắc nằm trong giai đoạn đầu
    for prev, nxt in zip(rm["phases"], rm["phases"][1:], strict=False):
        assert prev["end_date"] == nxt["start_date"]
    for phase in rm["phases"]:
        for step in phase["steps"]:
            if "due_date" in step:
                assert phase["start_date"] <= step["due_date"] <= phase["end_date"], step
    assert rm["horizon"]["start_date"] == today.isoformat()

    # (c) số tiền: không vượt tiền có thể chuyển, không vượt phần hũ nhận cần thêm trong kỳ (theo LP đã chạy)
    def need(code: str) -> int:
        line = lines[code]
        return max(line["proposed_monthly_vnd"] - line["current_monthly_vnd"], line["floor_gap_vnd"], 0)

    for phase in rm["phases"]:
        now = phase["start_date"] <= today.isoformat()
        for step in phase["steps"]:
            amount = step.get("amount_vnd")
            if amount is None:
                continue
            if step["kind"] in ("set_aside", "pay_obligation"):
                assert amount <= need(step["to_jar_code"]), step
                cap = balances[step["jar_code"]]["balance_vnd"] if now else lines[step["jar_code"]]["current_monthly_vnd"]
                assert amount <= cap, step
            elif step["kind"] == "adjust_split":
                assert amount <= need(step["jar_code"]), step
            elif step["kind"] == "cut_spending":
                assert amount <= lines[step["jar_code"]]["current_monthly_vnd"], step
    split = steps["doi_ty_le_an_uong"][1]
    line = lines["an_uong"]
    assert split["amount_vnd"] == line["proposed_monthly_vnd"] - line["current_monthly_vnd"]
    assert split["metrics"][0]["after"].replace(".", "").split()[0] == str(line["proposed_monthly_vnd"])

    # (d) phương án LP của bản sinh lại không đưa hũ nào xuống dưới khoản định kỳ trả từ nó (#39, 26/11): Giải trí giữ phần Netflix,
    # Ăn uống giữ phần Tiền cơm văn phòng; bước giảm chi hay đổi tỷ lệ không cắt hũ dưới sàn
    print("[cảnh 4] phân bổ LP:", {c: (x["current_monthly_vnd"], x["proposed_monthly_vnd"], x["floor_vnd"]) for c, x in lines.items()})
    owed: dict[str, int] = {}
    for o in got["obligations"]:
        if o["cycle"] == "monthly" and o.get("pay_jar") in lines:
            owed[o["pay_jar"]] = owed.get(o["pay_jar"], 0) + o["amount_vnd"]
    assert owed["giai_tri"] > 0 and owed["an_uong"] > 0
    for code, amount in owed.items():
        assert lines[code]["floor_vnd"] >= amount and lines[code]["proposed_monthly_vnd"] >= amount, code
    for phase in rm["phases"]:
        for step in phase["steps"]:
            if step["kind"] == "cut_spending" and step.get("amount_vnd"):
                jar = lines[step["jar_code"]]
                assert jar["current_monthly_vnd"] - step["amount_vnd"] >= jar["floor_vnd"], step
