"""Cấu hình của agent: mặc định đóng gói (`defaults.json`), ghi đè bằng env/SSM qua `yofina_core.config`.

Không có URL, tên tài nguyên hay model id nào nằm trong code. Model id, tốc độ và trần ngày do
`yofina_core.llm` quản (vai `planner`, `small`).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import resources
from typing import Any

from yofina_core.config import SSM_PREFIX_ENV, Config

log = logging.getLogger("yofina.agent.settings")


def _defaults() -> dict[str, Any]:
    text = resources.files("yofina_agent").joinpath("defaults.json").read_text(encoding="utf-8")
    return json.loads(text)


def _as_bool(raw: str) -> bool:
    v = str(raw).strip().lower()
    if v in {"1", "true", "yes", "on"}:
        return True
    if v in {"0", "false", "no", "off"}:
        return False
    raise ValueError(raw)


def _ssm_get(cfg: Config, name: str) -> str | None:
    """Tra SSM một khóa lười; lỗi quyền/mạng không làm hỏng việc nạp cấu hình (guardrail sẽ tự tắt và ghi log)."""
    try:
        return cfg.get(name, default=None) or None
    except Exception:  # noqa: BLE001
        return None


class ReasoningSwitch:
    """Công tắc khối `reasoning` của người tư vấn (luồng K, #7), đổi được không cần deploy. Mặc định bật.

    Thứ tự: biến môi trường `YOFINA_REASONING_ENABLED` (ghi đè, không tra SSM), rồi SSM `<YOFINA_SSM_PREFIX>/agent/reasoning_enabled`
    (String `true`/`false`), rồi mặc định đóng gói `reasoning_enabled`. Vắng khóa, lỗi quyền hay mạng, giá trị sai dạng: dùng mặc
    định (giữ hành vi hiện tại); lỗi thì ghi log (chỉ tên lỗi).

    Đọc lười: nạp cấu hình không tra khóa này (mỗi khóa SSM là một lời gọi, tốn cả giây ở phiên lạnh, xem `AgentSettings.load`), lượt
    đầu tiên cần tới mới đọc, trong luồng nền (`asyncio.to_thread`) để không chặn event loop. Kết quả, kể cả mặc định khi lỗi, nhớ
    `refresh_seconds` giây rồi mới đọc lại. Không có `YOFINA_SSM_PREFIX` (test, chạy tại máy) thì không tra SSM.
    """

    KEY = "agent/reasoning_enabled"

    def __init__(
        self,
        env: Mapping[str, str],
        *,
        default: bool,
        refresh_seconds: float,
        ssm: Any | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._env = dict(env)
        self._default = default
        self._refresh_seconds = refresh_seconds
        self._ssm = ssm
        self._clock = clock
        self._lock = threading.Lock()
        self._value: bool | None = None
        self._read_at = 0.0
        prefix = self._env.get(SSM_PREFIX_ENV)
        self._path = f"{prefix.rstrip('/')}/{self.KEY}" if prefix else None
        self._override = self._env_override()

    def _env_override(self) -> bool | None:
        raw = Config({k: v for k, v in self._env.items() if k != SSM_PREFIX_ENV}).get(
            "reasoning_enabled", default=None
        )
        if raw is None:
            return None
        try:
            return _as_bool(raw)
        except ValueError:
            log.warning(json.dumps({"event": "reasoning_switch_invalid", "source": "env"}))
            return None

    def _fresh(self) -> bool:
        return self._value is not None and self._clock() - self._read_at < self._refresh_seconds

    async def enabled(self) -> bool:
        """Khối `reasoning` có bật không (không bao giờ ném lỗi)."""
        if self._override is not None:
            return self._override
        if self._path is None:
            return self._default
        if self._fresh():
            return bool(self._value)
        return await asyncio.to_thread(self._load)

    def _load(self) -> bool:
        with self._lock:  # nhiều lượt cùng hết chu kỳ: chỉ một lần đọc
            if not self._fresh():
                self._value, self._read_at = self._read(), self._clock()
            return bool(self._value)

    def _read(self) -> bool:
        try:
            if self._ssm is None:
                import boto3  # chỉ import khi thật sự tra SSM

                self._ssm = boto3.client("ssm", region_name=Config(self._env).region())
            resp = self._ssm.get_parameter(Name=self._path, WithDecryption=False)
            return _as_bool(str(resp["Parameter"]["Value"]))
        except Exception as exc:  # vắng khóa, quyền, mạng, sai dạng: giữ mặc định
            if type(exc).__name__ != "ParameterNotFound":
                log.warning(
                    json.dumps(
                        {"event": "reasoning_switch_unreadable", "error": type(exc).__name__}
                    )
                )
            return self._default


@dataclass(frozen=True)
class AgentSettings:
    gateway_url: str | None
    gateway_tool_prefix: str
    forecast_tool_prefix: str
    planner_tool_prefix: str
    roadmap_default_which: str
    roadmap_fix_max_rounds: int
    roadmap_max_steps: int
    roadmap_max_tool_calls_per_turn: int
    roadmap_draft_max_tokens: int
    # bước đạt đủ khuôn (số giai đoạn, số bước) thì lưu, bỏ bước bị loại thay vì thêm vòng sửa; 0 là luôn sửa
    roadmap_accept_min_phases: int
    roadmap_accept_min_steps: int
    knowledge_tool_prefix: str
    audit_tool_prefix: str
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
    # Harness phase 3
    guardrail_enabled: bool
    guardrail_timeout_seconds: float
    guardrail_fail_open: bool
    guardrail_id: str | None
    guardrail_version: str | None
    tool_retry_attempts: int
    orchestrator_max_tokens: int
    analyst_max_tokens: int
    verifier_max_rounds: int
    plan_max_tokens: int
    affordability_text_timeout_seconds: float
    affordability_text_max_tokens: int
    low_data_days: int
    low_coverage_threshold: float
    turn_record_tool: str
    turn_record_timeout_seconds: float
    # Luồng K: khối `reasoning` còn ít hơn số bước này sau khi bỏ bước mâu thuẫn với kết quả đã lưu thì bỏ cả khối (#7)
    reasoning_min_steps: int
    # Luồng K: công tắc bật/tắt khối `reasoning` (SSM, đọc lười, #7)
    reasoning_switch: ReasoningSwitch

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
            planner_tool_prefix=get("planner_tool_prefix"),
            roadmap_default_which=get("roadmap_default_which"),
            roadmap_fix_max_rounds=get("roadmap_fix_max_rounds", int),
            roadmap_max_steps=get("roadmap_max_steps", int),
            roadmap_max_tool_calls_per_turn=get("roadmap_max_tool_calls_per_turn", int),
            roadmap_draft_max_tokens=get("roadmap_draft_max_tokens", int),
            roadmap_accept_min_phases=get("roadmap_accept_min_phases", int),
            roadmap_accept_min_steps=get("roadmap_accept_min_steps", int),
            knowledge_tool_prefix=get("knowledge_tool_prefix"),
            audit_tool_prefix=get("audit_tool_prefix"),
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
            guardrail_enabled=get("guardrail_enabled", _as_bool),
            guardrail_timeout_seconds=get("guardrail_timeout_seconds", float),
            guardrail_fail_open=get("guardrail_fail_open", _as_bool),
            # id/version: biến môi trường, rồi SSM `<prefix>/guardrail/id` và `/guardrail/version` (CDK `guardrail.ts` ghi)
            guardrail_id=env_only.get("guardrail_id", default=None) or _ssm_get(cfg, "guardrail/id"),
            guardrail_version=env_only.get("guardrail_version", default=None)
            or _ssm_get(cfg, "guardrail/version"),
            tool_retry_attempts=get("tool_retry_attempts", int),
            orchestrator_max_tokens=get("orchestrator_max_tokens", int),
            analyst_max_tokens=get("analyst_max_tokens", int),
            verifier_max_rounds=get("verifier_max_rounds", int),
            plan_max_tokens=get("plan_max_tokens", int),
            affordability_text_timeout_seconds=get("affordability_text_timeout_seconds", float),
            affordability_text_max_tokens=get("affordability_text_max_tokens", int),
            low_data_days=get("low_data_days", int),
            low_coverage_threshold=get("low_coverage_threshold", float),
            turn_record_tool=get("turn_record_tool"),
            turn_record_timeout_seconds=get("turn_record_timeout_seconds", float),
            reasoning_min_steps=get("reasoning_min_steps", int),
            # không tra SSM lúc nạp: công tắc đọc lười ở lượt đầu tiên cần tới
            reasoning_switch=ReasoningSwitch(
                env,
                default=bool(d["reasoning_enabled"]),
                refresh_seconds=get("reasoning_refresh_seconds", float),
            ),
        )

    def tool(self, short_name: str, *, target: str = "ledger") -> str:
        """Tên tool trên Gateway: `<target>___<tool>` (ví dụ `ledger___get_jar_balances`, `forecast___get_forecast`)."""
        prefix = {
            "ledger": self.gateway_tool_prefix,
            "forecast": self.forecast_tool_prefix,
            "planner": self.planner_tool_prefix,
            "knowledge": self.knowledge_tool_prefix,
            "audit": self.audit_tool_prefix,
        }[target]
        return f"{prefix}{short_name}"
