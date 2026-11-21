"""Model của Strands dùng chung lớp kiểm của `yofina_core.llm`.

Mọi lời gọi model của một `strands.Agent` đều đi qua `Model.stream`; lớp này bọc ở đúng chỗ đó nên đếm
được **mọi** lời gọi (kể cả lượt chạy lại do Strands tự retry):

1. trần lượt hội thoại (`TurnScope`) -> giới hạn tốc độ của model -> trần ngày ở DynamoDB;
2. chuỗi dự phòng của vai (`planner`, `small`): lỗi `ThrottlingException` / `AccessDeniedException` (và vài lỗi
   tạm thời khác, xem `LlmGateway.is_fallback_error`) **trước khi** model phát event đầu thì rẽ sang model kế;
3. ghi log token vào/ra và thời lượng.

Hết chuỗi thì ném `AllModelsFailed` (không phải `ModelThrottledException`, để vòng retry riêng của Strands
không chờ thêm hàng chục giây trước khi agent chuyển sang đường suy giảm).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from botocore.config import Config as BotoConfig
from strands.models import BedrockModel, Model

from yofina_core.config import Config
from yofina_core.llm import (
    AllModelsFailed,
    LlmGateway,
    ModelSpec,
    RateLimitWaitTooLong,
    TurnScope,
)

log = logging.getLogger("yofina.agent.model")


class MeteredModel(Model):
    def __init__(
        self,
        gateway: LlmGateway,
        role: str,
        *,
        scope: TurnScope | None = None,
        region: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.0,
        config: Config | None = None,
    ) -> None:
        self._gw, self._role, self._scope = gateway, role, scope
        self._region = region or (config or Config()).region()
        self._max_tokens, self._temperature = max_tokens, temperature
        self._models: dict[str, BedrockModel] = {}
        self._chain = gateway.chain(role)
        # cấu hình nhẹ cho Strands đọc (không dựng BedrockModel/boto client trước khi cần gọi)
        self._config: dict[str, Any] = {"model_id": self._chain[0].id, "max_tokens": max_tokens}

    def _bedrock(self, spec: ModelSpec) -> BedrockModel:
        if spec.id not in self._models:
            self._models[spec.id] = BedrockModel(
                model_id=spec.id,
                region_name=self._region,
                max_tokens=self._max_tokens,
                temperature=self._temperature if spec.temperature else None,
                # Không retry ngầm: chuỗi dự phòng và bộ đếm của gateway quyết định.
                boto_client_config=BotoConfig(
                    retries={"max_attempts": 1},
                    read_timeout=self._gw.settings.read_timeout_seconds,
                    connect_timeout=5,
                ),
            )
        return self._models[spec.id]

    def update_config(self, **model_config: Any) -> None:
        model_config.pop("model_id", None)  # model do chuỗi dự phòng của vai quyết định
        self._config.update(model_config)
        for m in self._models.values():
            m.update_config(**model_config)

    def get_config(self) -> Any:
        return dict(self._config)

    def structured_output(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(
            "Dùng `structured_output_model` ở lời gọi agent hoặc `LlmGateway.structured_json`."
        )

    async def stream(
        self,
        messages: Any,
        tool_specs: Any = None,
        system_prompt: Any = None,
        **kwargs: Any,
    ) -> AsyncGenerator[Any, None]:
        skipped: list[tuple[str, str]] = []
        for spec in self._chain:
            try:
                await self._gw.reserve_async(self._role, spec, self._scope)
            except RateLimitWaitTooLong:
                skipped.append((spec.id, "RateLimitWaitTooLong"))
                continue
            started = time.perf_counter()
            tin = tout = 0
            yielded = False
            try:
                async for event in (await asyncio.to_thread(self._bedrock, spec)).stream(
                    messages, tool_specs, system_prompt, **kwargs
                ):
                    yielded = True
                    usage = (
                        event.get("metadata", {}).get("usage") if isinstance(event, dict) else None
                    )
                    if usage:
                        tin, tout = (
                            int(usage.get("inputTokens", 0)),
                            int(usage.get("outputTokens", 0)),
                        )
                    yield event
            except Exception as exc:
                latency = int((time.perf_counter() - started) * 1000)
                outcome = LlmGateway.error_code(exc) or type(exc).__name__
                self._gw.record(
                    self._role,
                    spec.id,
                    input_tokens=tin,
                    output_tokens=tout,
                    latency_ms=latency,
                    outcome=outcome,
                    scope=self._scope,
                )
                if not yielded and self._gw.is_fallback_error(exc):
                    skipped.append((spec.id, outcome))
                    continue
                raise
            self._gw.record(
                self._role,
                spec.id,
                input_tokens=tin,
                output_tokens=tout,
                latency_ms=int((time.perf_counter() - started) * 1000),
                outcome="ok",
                scope=self._scope,
            )
            return
        raise AllModelsFailed(self._role, skipped)
