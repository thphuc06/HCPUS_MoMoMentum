"""Chạy Roadmap agent và chốt kết quả để frontend polling."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError
from yofina_agent import notices
from yofina_agent.roadmap_agent import RegenerationContext, build_roadmap
from yofina_agent.settings import AgentSettings
from yofina_agent.tools import ToolKind, ToolOutcome

from yofina_core.blocks import ResilienceScoreData
from yofina_core.db import Row
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.llm import LlmGateway, ModelBudgetExceeded, TurnScope, get_gateway
from yofina_core.roadmap import JobStage, Roadmap
from yofina_core.suitability import SuitabilityVerdict
from yofina_roadmap.events import RoadmapEvent
from yofina_roadmap.repo import RoadmapRepo
from yofina_roadmap.settings import RoadmapSettings
from yofina_roadmap.tool_caller import LambdaTools

log = logging.getLogger(__name__)
_HANDLED_TOOL_ERRORS = {
    "get_roadmap": {ErrorCode.ROADMAP_NOT_FOUND},
    "save_roadmap": {ErrorCode.ROADMAP_VERSION_CONFLICT, ErrorCode.ROADMAP_INVALID},
}
_REQUIRED_RESULT_MODELS = {
    "get_resilience_score": ResilienceScoreData,
    "check_suitability": SuitabilityVerdict,
}


def _tool_failure(outcome: ToolOutcome) -> YofinaError:
    if outcome.kind is ToolKind.NEEDS_CONFIRMATION:
        code = ErrorCode.NEEDS_CONFIRMATION
    else:
        try:
            code = ErrorCode(outcome.code)
        except ValueError:
            code = ErrorCode.INTERNAL_ERROR
    # ToolOutcome.message là thông điệp người dùng theo hợp đồng, detail chỉ để chẩn đoán.
    return YofinaError(code, outcome.message or notices.GENERIC_ERROR_MESSAGE)


class RoadmapRunner:
    def __init__(
        self,
        repo: RoadmapRepo,
        settings: RoadmapSettings,
        agent_settings: AgentSettings,
        lambda_client: Any,
        llm_factory: Callable[[], LlmGateway] = get_gateway,
    ) -> None:
        self._repo = repo
        self._settings = settings
        self._agent_settings = agent_settings
        self._client = lambda_client
        self._llm_factory = llm_factory

    def process(self, event: RoadmapEvent) -> str:
        if event.job_id is None and event.trigger is None:
            return "skipped"
        job = self._repo.claim(event)
        if job is None:
            return "skipped"
        uid, job_id = event.user_id, job["id"]
        roadmap = None
        error = YofinaError(ErrorCode.INTERNAL_ERROR, notices.GENERIC_ERROR_MESSAGE)
        try:
            roadmap = asyncio.run(self._build(uid, job))
        except YofinaError as exc:
            error = exc
        except Exception as exc:
            log.error("roadmap_job_error job=%s type=%s", job_id, type(exc).__name__)
        finally:
            # Lỗi ghi trạng thái phải thoát ra cho SQS retry. Lease xử lý lần chạy bị Lambda dừng cứng.
            if roadmap is None:
                message = error.message.replace("\x00", "").strip() or notices.GENERIC_ERROR_MESSAGE
                self._repo.failed(uid, job_id, error.code, message)
            else:
                self._repo.done(uid, job_id, roadmap)
        return "failed" if roadmap is None else "done"

    async def _build(self, uid: str, job: Row) -> Roadmap:
        ledger = self._settings.ledger_function_name
        tools = LambdaTools(
            self._client,
            {
                "ledger": ledger,
                "planner": ledger,
                "forecast": self._settings.forecast_function_name,
            },
            uid,
        )

        async def call_tool(name: str, args: dict[str, Any], target: str) -> ToolOutcome:
            outcome = await tools(name, args, target)
            if outcome.kind is ToolKind.OK:
                # Chat có thể bỏ qua ngữ cảnh thiếu hoặc bỏ bước chưa kiểm. Job báo lỗi tool.
                if (model := _REQUIRED_RESULT_MODELS.get(name)) is not None:
                    try:
                        model.model_validate((outcome.payload or {}).get("data"))
                    except ValidationError:
                        raise YofinaError(
                            ErrorCode.INTERNAL_ERROR, notices.GENERIC_ERROR_MESSAGE
                        ) from None
            elif outcome.code not in _HANDLED_TOOL_ERRORS.get(name, ()):
                raise _tool_failure(outcome)
            return outcome

        def stage(stage: JobStage, _progress: int) -> None:
            self._repo.stage(uid, job["id"], stage, self._settings.stage_progress[stage])

        result = await build_roadmap(
            tools=call_tool,
            llm=self._llm_factory(),
            settings=self._agent_settings,
            scope=TurnScope(self._agent_settings.max_model_calls_per_turn),
            reason_code=job["trigger"],
            behavior_flag_id=job["behavior_flag_id"],
            regeneration=RegenerationContext(
                based_on_version=job["based_on_version"],
                alternative_id=job["alternative_id"],
                note=job["note"],
            ),
            on_stage=stage,
        )
        if result.model_budget_exhausted or isinstance(result.model_error, ModelBudgetExceeded):
            raise YofinaError(
                ErrorCode.MODEL_BUDGET_EXCEEDED, "Đã hết lượt gọi AI để sinh lại lộ trình."
            )
        if result.model_error is not None:
            log.warning(
                "roadmap_model_error job=%s type=%s error=%s",
                job["id"],
                type(result.model_error).__name__,
                str(result.model_error)[:500],  # đường dẫn field lỗi, không chứa dữ liệu người dùng
            )
            raise YofinaError(ErrorCode.INTERNAL_ERROR, notices.GENERIC_ERROR_MESSAGE)
        if result.outcome is None:
            raise YofinaError(ErrorCode.ROADMAP_INVALID, "Chưa tạo được bản nháp lộ trình hợp lệ.")
        if result.outcome.kind is not ToolKind.OK:
            raise _tool_failure(result.outcome)
        return Roadmap.model_validate((result.outcome.payload or {}).get("data"))
