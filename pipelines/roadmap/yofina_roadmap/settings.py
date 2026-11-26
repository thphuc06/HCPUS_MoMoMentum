"""Cấu hình Lambda, đọc từ env hoặc SSM qua yofina_core."""

from __future__ import annotations

from dataclasses import dataclass

from yofina_core.config import Config, ConfigError
from yofina_core.roadmap import JobStage

STAGES: tuple[JobStage, ...] = ("context", "draft", "allocate", "suitability", "save")
ALLOWED_TOOLS = {
    "ledger": frozenset({"get_jar_balances", "get_obligations"}),
    "forecast": frozenset({"get_resilience_score"}),
    "planner": frozenset(
        {"get_roadmap", "check_suitability", "optimize_allocation", "save_roadmap"}
    ),
    # ngày nhắc theo mốc của bước lộ trình (`StepOutline.nudge_on_spec`): tool tính ngày chạy trong Lambda ledger
    "knowledge": frozenset({"resolve_date"}),
}


@dataclass(frozen=True)
class RoadmapSettings:
    ledger_function_name: str
    forecast_function_name: str
    event_bus_name: str
    invoke_connect_timeout_seconds: int
    invoke_read_timeout_seconds: int
    running_lease_seconds: int
    stage_progress: dict[JobStage, int]

    @classmethod
    def from_config(cls, cfg: Config) -> RoadmapSettings:
        progress = cfg.get(
            "roadmap_stage_progress", cast=lambda raw: [int(part) for part in raw.split(",")]
        )
        if (
            len(progress) != len(STAGES)
            or progress != sorted(set(progress))
            or not 0 <= progress[0] <= progress[-1] < 100
        ):
            raise ConfigError("roadmap_stage_progress cần năm mốc tăng dần, từ 0 đến 99")

        def positive_seconds(name: str) -> int:
            seconds = cfg.get_int(name)
            if seconds <= 0:
                raise ConfigError(f"{name} phải lớn hơn 0")
            return seconds

        return cls(
            ledger_function_name=cfg.get("roadmap_ledger_function_name"),
            forecast_function_name=cfg.get("roadmap_forecast_function_name"),
            event_bus_name=cfg.get("event_bus_name"),
            invoke_connect_timeout_seconds=positive_seconds(
                "roadmap_invoke_connect_timeout_seconds"
            ),
            invoke_read_timeout_seconds=positive_seconds("roadmap_invoke_read_timeout_seconds"),
            running_lease_seconds=positive_seconds("roadmap_running_lease_seconds"),
            stage_progress=dict(zip(STAGES, progress, strict=True)),
        )
