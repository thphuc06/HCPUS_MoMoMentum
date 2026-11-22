"""Cấu hình của agent: mặc định đóng gói (`defaults.json`), ghi đè bằng env/SSM qua `yofina_core.config`.

Không có URL, tên tài nguyên hay model id nào nằm trong code. Model id, tốc độ và trần ngày do
`yofina_core.llm` quản (vai `planner`, `small`).
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from typing import Any

from yofina_core.config import SSM_PREFIX_ENV, Config


def _defaults() -> dict[str, Any]:
    text = resources.files("yofina_agent").joinpath("defaults.json").read_text(encoding="utf-8")
    return json.loads(text)


@dataclass(frozen=True)
class AgentSettings:
    gateway_url: str | None
    gateway_tool_prefix: str
    forecast_tool_prefix: str
    run_timeout_seconds: float
    max_model_calls_per_turn: int
    max_tool_calls_per_turn: int
    history_messages: int
    history_chars_per_message: int
    tool_timeout_seconds: float
    tool_startup_timeout_seconds: float
    router_max_attempts: int
    router_max_tokens: int
    writer_max_tokens: int
    writer_turn_limit: int
    writer_output_token_limit: int
    transactions_default_limit: int
    transactions_max_limit: int
    turn_blocks_tool: str
    turn_blocks_timeout_seconds: float
    log_level: str

    @classmethod
    def load(cls, env: Mapping[str, str] | None = None) -> AgentSettings:
        env = os.environ if env is None else env
        cfg = Config(env)
        d = _defaults()
        # Các tham số chỉnh được (trần, thời gian...) chỉ đọc từ biến môi trường: không tra SSM từng khóa
        # (mỗi khóa vắng là một lời gọi SSM, tốn cả giây ở phiên lạnh). Chỉ `gateway_url` được tra thêm ở SSM.
        env_only = Config({k: v for k, v in env.items() if k != SSM_PREFIX_ENV})

        def get(name: str, cast: Any = str) -> Any:
            return env_only.get(name, default=d[name], cast=cast)

        return cls(
            gateway_url=cfg.get("gateway_url", default=None) or None,
            gateway_tool_prefix=get("gateway_tool_prefix"),
            forecast_tool_prefix=get("forecast_tool_prefix"),
            run_timeout_seconds=get("run_timeout_seconds", float),
            max_model_calls_per_turn=get("max_model_calls_per_turn", int),
            max_tool_calls_per_turn=get("max_tool_calls_per_turn", int),
            history_messages=get("history_messages", int),
            history_chars_per_message=get("history_chars_per_message", int),
            tool_timeout_seconds=get("tool_timeout_seconds", float),
            tool_startup_timeout_seconds=get("tool_startup_timeout_seconds", float),
            router_max_attempts=get("router_max_attempts", int),
            router_max_tokens=get("router_max_tokens", int),
            writer_max_tokens=get("writer_max_tokens", int),
            writer_turn_limit=get("writer_turn_limit", int),
            writer_output_token_limit=get("writer_output_token_limit", int),
            transactions_default_limit=get("transactions_default_limit", int),
            transactions_max_limit=get("transactions_max_limit", int),
            turn_blocks_tool=get("turn_blocks_tool"),
            turn_blocks_timeout_seconds=get("turn_blocks_timeout_seconds", float),
            log_level=get("log_level"),
        )

    def tool(self, short_name: str, *, target: str = "ledger") -> str:
        """Tên tool trên Gateway: `<target>___<tool>` (ví dụ `ledger___get_jar_balances`, `forecast___get_forecast`)."""
        prefix = self.forecast_tool_prefix if target == "forecast" else self.gateway_tool_prefix
        return f"{prefix}{short_name}"
